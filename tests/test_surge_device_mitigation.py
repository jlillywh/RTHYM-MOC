"""Surge-control device regressions for high- and low-pressure transients.

This module exercises the two implemented passive protection devices in
different placements:

- a standpipe or hydropneumatic vessel placed near a closing valve to limit
  overpressure and suppress cavitation during a rapid closure event
- a standpipe or hydropneumatic vessel placed near pump discharge to limit
    the low-pressure collapse after a pump trip

Air-valve coverage now lives in ``tests/test_air_valve.py`` because the vacuum-
break behavior is exercised with a different acceptance criterion than the
surge-vessel devices.
"""

import numpy as np
import pytest

import rthym_moc as m

DT_S = 0.01
VALVE_TOTAL_TIME_S = 12.0
PUMP_TOTAL_TIME_S = 12.0

VALVE_PRE_START_S = 0.1
VALVE_PRE_END_S = 0.5
PUMP_PRE_START_S = 1.0
PUMP_PRE_END_S = 4.0
PUMP_TRIP_START_S = 5.2
PUMP_TRIP_END_S = 6.0

VALVE_PEAK_HEAD_LIMIT_FT = {
    "Standpipe": 170.0,
    "HydropneumaticTank": 350.0,
}
PUMP_TRIP_HEAD_FLOOR_FT = {
    "Standpipe": 50.0,
    "HydropneumaticTank": 150.0,
}
PUMP_TRIP_CAVITATION_MAX = {
    "Standpipe": 5,
    "HydropneumaticTank": 0,
}


def _make_node(node_id, node_type, **kwargs):
    node = m.NodeInput()
    node.id = node_id
    node.type = node_type
    for key, value in kwargs.items():
        setattr(node, key, value)
    return node


def _make_pipe(pipe_id, from_node, to_node, length_ft, flow_gpm):
    pipe = m.PipeInput()
    pipe.id = pipe_id
    pipe.from_node = from_node
    pipe.to_node = to_node
    pipe.length = length_ft
    pipe.diameter = 12.0
    pipe.roughness = 130.0
    pipe.flow_gpm = flow_gpm
    return pipe


def _mean_over_window(time_s, values, start_s, end_s):
    mask = (time_s >= start_s) & (time_s <= end_s)
    assert np.any(mask), f"No samples found in window [{start_s}, {end_s}] s"
    return float(np.asarray(values)[mask].mean())


def _add_protection_node(solver, kind, *, node_id, head_ft):
    if kind == "none":
        solver.add_node(_make_node(node_id, "Junction", head=head_ft))
        return

    if kind == "Standpipe":
        solver.add_node(
            _make_node(node_id, "Standpipe", head=head_ft, tank_area=10.0 if node_id == "Prot" else 1.0)
        )
        return

    if kind == "HydropneumaticTank":
        solver.add_node(
            _make_node(
                node_id,
                "HydropneumaticTank",
                head=head_ft,
                diameter=4.0,
                gas_volume=12.0 if head_ft >= 160.0 else 10.0,
                tank_volume=30.0,
                polytropic_n=1.2,
                loss_coeff_in=0.7,
                loss_coeff_out=0.7,
            )
        )
        return

    raise ValueError(f"Unknown protection kind: {kind}")


def _run_valve_closure_case(kind):
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=150.0))
    _add_protection_node(solver, kind, node_id="Prot", head_ft=145.8)
    solver.add_node(
        _make_node(
            "Valve_A",
            "Valve",
            diameter=12.0,
            current_setting=100.0,
            head=145.8,
        )
    )
    solver.add_node(_make_node("R2", "PressureBoundary", head=145.8))

    solver.add_pipe(_make_pipe("P1", "R1", "Prot", 3000.0, 500.0))
    solver.add_pipe(_make_pipe("P2", "Prot", "Valve_A", 40.0, 500.0))
    solver.add_pipe(_make_pipe("P3", "Valve_A", "R2", 40.0, 0.0))

    solver.set_valve_schedule(
        "Valve_A",
        [
            (0.0, 100.0),
            (DT_S, 0.0),
            (VALVE_TOTAL_TIME_S, 0.0),
        ],
    )
    return solver.run(total_time=VALVE_TOTAL_TIME_S, dt=DT_S)


def _run_pump_trip_case(kind):
    solver = m.MOCSolver()
    solver.add_node(_make_node("Rlow", "PressureBoundary", head=100.0))
    solver.add_node(_make_node("PumpIn", "Junction", head=100.0))
    solver.add_node(
        _make_node(
            "Pump_A",
            "Pump",
            design_head=120.0,
            design_flow=500.0,
            current_speed=100.0,
            head=220.0,
        )
    )
    solver.add_node(_make_node("Jd", "Junction", head=220.0))
    _add_protection_node(solver, kind, node_id="Prot", head_ft=160.0)
    solver.add_node(_make_node("Rhigh", "PressureBoundary", head=160.0))

    solver.add_pipe(_make_pipe("Ps", "Rlow", "PumpIn", 500.0, 800.0))
    solver.add_pipe(_make_pipe("Ppump", "Pump_A", "Jd", 40.0, 800.0))
    solver.add_pipe(_make_pipe("Pstub", "Jd", "Prot", 40.0, 800.0))
    solver.add_pipe(_make_pipe("Pmain", "Prot", "Rhigh", 4000.0, 800.0))

    solver.set_pump_schedule(
        "Pump_A",
        [
            (0.0, 100.0),
            (4.99, 100.0),
            (5.0, 0.0),
            (PUMP_TOTAL_TIME_S, 0.0),
        ],
    )
    return solver.run(total_time=PUMP_TOTAL_TIME_S, dt=DT_S)


@pytest.fixture(scope="module")
def valve_closure_data():
    return {
        kind: _run_valve_closure_case(kind)
        for kind in ["none", "Standpipe", "HydropneumaticTank"]
    }


@pytest.fixture(scope="module")
def pump_trip_data():
    return {
        kind: _run_pump_trip_case(kind)
        for kind in ["none", "Standpipe", "HydropneumaticTank"]
    }


def test_unprotected_valve_closure_generates_large_overpressure_and_cavitation(valve_closure_data):
    """The unprotected fast closure should spike sharply and hit vapor pressure."""
    data = valve_closure_data["none"]
    prot_head = np.asarray(data["node_head"]["Prot"])
    prot_cav = np.asarray(data["node_cavitation"]["Prot"])
    time_s = np.asarray(data["time"])
    pre_head_ft = _mean_over_window(time_s, prot_head, VALVE_PRE_START_S, VALVE_PRE_END_S)
    peak_head_ft = float(prot_head.max())

    assert pre_head_ft >= 400.0, f"Expected the unprotected closure case to initialize with a high loaded head, got {pre_head_ft:.2f} ft"
    assert peak_head_ft >= 550.0, f"Expected a severe unprotected closure surge, got {peak_head_ft:.2f} ft"
    assert int(prot_cav.sum()) >= 100, f"Expected extended cavitation in the unprotected closure case, got {int(prot_cav.sum())} cavitating steps"


@pytest.mark.parametrize("kind", ["Standpipe", "HydropneumaticTank"])
def test_valve_side_protection_devices_limit_overpressure_and_suppress_cavitation(
    valve_closure_data,
    kind,
):
    """Protection devices near the valve should cap the closure surge and prevent cavitation."""
    baseline = valve_closure_data["none"]
    protected = valve_closure_data[kind]
    baseline_peak_ft = float(np.max(np.asarray(baseline["node_head"]["Prot"])))
    protected_peak_ft = float(np.max(np.asarray(protected["node_head"]["Prot"])))
    protected_cav_steps = int(np.asarray(protected["node_cavitation"]["Prot"]).sum())

    assert baseline_peak_ft - protected_peak_ft >= 200.0, (
        f"Expected {kind} to cut at least 200 ft from the closure peak, got {baseline_peak_ft - protected_peak_ft:.2f} ft"
    )
    assert protected_peak_ft <= VALVE_PEAK_HEAD_LIMIT_FT[kind], (
        f"Expected {kind} peak to stay below {VALVE_PEAK_HEAD_LIMIT_FT[kind]:.0f} ft, got {protected_peak_ft:.2f} ft"
    )
    assert protected_cav_steps == 0, f"Expected {kind} to suppress cavitation at the protected node, got {protected_cav_steps} cavitating steps"


def test_unprotected_pump_trip_drives_discharge_node_subatmospheric(pump_trip_data):
    """Without protection, the discharge-side junction should collapse into cavitation after trip."""
    data = pump_trip_data["none"]
    time_s = np.asarray(data["time"])
    jd_head = np.asarray(data["node_head"]["Jd"])
    jd_cav = np.asarray(data["node_cavitation"]["Jd"])
    tripped_head_ft = _mean_over_window(time_s, jd_head, PUMP_TRIP_START_S, PUMP_TRIP_END_S)

    assert tripped_head_ft < 0.0, f"Expected the unprotected pump-trip head to go subatmospheric, got {tripped_head_ft:.2f} ft"
    assert int(jd_cav.sum()) >= 100, f"Expected sustained cavitation at Jd after trip, got {int(jd_cav.sum())} cavitating steps"


@pytest.mark.parametrize("kind", ["Standpipe", "HydropneumaticTank"])
def test_discharge_side_protection_devices_limit_pump_trip_low_pressure(
    pump_trip_data,
    kind,
):
    """Protection near pump discharge should keep the trip response above the unprotected collapse."""
    baseline = pump_trip_data["none"]
    protected = pump_trip_data[kind]
    time_s = np.asarray(protected["time"])
    baseline_trip_head_ft = _mean_over_window(
        np.asarray(baseline["time"]),
        baseline["node_head"]["Jd"],
        PUMP_TRIP_START_S,
        PUMP_TRIP_END_S,
    )
    protected_trip_head_ft = _mean_over_window(
        time_s,
        protected["node_head"]["Jd"],
        PUMP_TRIP_START_S,
        PUMP_TRIP_END_S,
    )
    protected_cav_steps = int(np.asarray(protected["node_cavitation"]["Jd"]).sum())

    assert protected_trip_head_ft - baseline_trip_head_ft >= 100.0, (
        f"Expected {kind} to recover at least 100 ft of trip head, got {protected_trip_head_ft - baseline_trip_head_ft:.2f} ft"
    )
    assert protected_trip_head_ft >= PUMP_TRIP_HEAD_FLOOR_FT[kind], (
        f"Expected {kind} trip head to stay above {PUMP_TRIP_HEAD_FLOOR_FT[kind]:.0f} ft, got {protected_trip_head_ft:.2f} ft"
    )
    assert protected_cav_steps <= PUMP_TRIP_CAVITATION_MAX[kind], (
        f"Expected {kind} to limit discharge-node cavitation to {PUMP_TRIP_CAVITATION_MAX[kind]} steps, got {protected_cav_steps}"
    )
