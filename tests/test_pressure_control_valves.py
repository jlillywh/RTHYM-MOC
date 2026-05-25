"""Regressions for PRV, PSV, and PBV pressure-control valve behavior."""

from pathlib import Path

import numpy as np
import pytest

import rthym_moc as m


DT_S = 0.01
TOTAL_TIME_S = 0.5


def _make_node(node_id, node_type, **kwargs):
    node = m.NodeInput()
    node.id = node_id
    node.type = node_type
    for key, value in kwargs.items():
        setattr(node, key, value)
    return node


def _make_pipe(pipe_id, from_node, to_node, flow_gpm, length_ft=80.0):
    pipe = m.PipeInput()
    pipe.id = pipe_id
    pipe.from_node = from_node
    pipe.to_node = to_node
    pipe.length = length_ft
    pipe.diameter = 12.0
    pipe.roughness = 130.0
    pipe.flow_gpm = flow_gpm
    return pipe


def _run_upstream_surge(valve_type: str, setpoint_head: float):
    """Upstream reservoir surge against a fixed downstream head boundary."""
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=200.0))
    solver.add_node(
        _make_node(
            "PCV1",
            valve_type,
            head=setpoint_head,
            diameter=12.0,
            current_setting=100.0,
        )
    )
    solver.add_node(_make_node("R2", "PressureBoundary", head=120.0))
    solver.add_pipe(_make_pipe("P1", "R1", "PCV1", 400.0))
    solver.add_pipe(_make_pipe("P2", "PCV1", "R2", 400.0))
    solver.set_head_schedule(
        "R1",
        [
            (0.0, 200.0),
            (0.08, 200.0),
            (0.09, 350.0),
            (TOTAL_TIME_S, 350.0),
        ],
    )
    return solver.run(total_time=TOTAL_TIME_S, dt=DT_S)


def test_prv_limits_downstream_head_during_upstream_surge():
    """A PRV should cap its regulated (downstream) face when an upstream surge arrives."""
    setpoint_ft = 155.0
    protected = _run_upstream_surge("PRV", setpoint_ft)
    open_valve = _run_upstream_surge("Valve", setpoint_ft)

    time_s = np.asarray(protected["time"])
    window = (time_s >= 0.2) & (time_s <= 0.45)

    # node_head at a PRV records the downstream regulated face
    protected_head = np.asarray(protected["node_head"]["PCV1"])
    open_head = np.asarray(open_valve["node_head"]["PCV1"])

    assert np.any(window)
    assert float(protected_head[window].max()) <= setpoint_ft + 2.0, (
        f"PRV should regulate downstream head near {setpoint_ft} ft, "
        f"got max {float(protected_head[window].max()):.1f} ft"
    )
    assert float(open_head[window].max()) > setpoint_ft + 15.0, (
        "A fully open throttling valve should not enforce the PRV setpoint"
    )


def test_psv_sustains_upstream_head_when_downstream_drops():
    """A PSV should hold upstream head near its setpoint when the downstream boundary falls."""
    setpoint_ft = 165.0
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=200.0))
    solver.add_node(
        _make_node("PSV1", "PSV", head=setpoint_ft, diameter=12.0, current_setting=100.0)
    )
    solver.add_node(_make_node("R2", "PressureBoundary", head=140.0))
    solver.add_pipe(_make_pipe("P1", "R1", "PSV1", 400.0))
    solver.add_pipe(_make_pipe("P2", "PSV1", "R2", 400.0))
    solver.set_head_schedule(
        "R2",
        [
            (0.0, 140.0),
            (0.08, 140.0),
            (0.09, 40.0),
            (TOTAL_TIME_S, 40.0),
        ],
    )
    results = solver.run(total_time=TOTAL_TIME_S, dt=DT_S)

    time_s = np.asarray(results["time"])
    window = (time_s >= 0.2) & (time_s <= 0.45)
    upstream_head = np.asarray(results["node_head"]["PSV1"])

    assert float(upstream_head[window].min()) >= setpoint_ft - 2.0, (
        "PSV should sustain upstream head near the setpoint when downstream pressure falls"
    )


def _pbv_downstream_mean(delta_ft: float) -> float:
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=200.0))
    solver.add_node(
        _make_node("PBV1", "PBV", head=delta_ft, diameter=12.0, current_setting=100.0)
    )
    solver.add_node(_make_node("R2", "PressureBoundary", head=120.0))
    solver.add_pipe(_make_pipe("P1", "R1", "PBV1", 350.0))
    solver.add_pipe(_make_pipe("P2", "PBV1", "R2", 350.0))
    results = solver.run(total_time=0.2, dt=DT_S)

    time_s = np.asarray(results["time"])
    window = (time_s >= 0.05) & (time_s <= 0.18)
    return float(np.asarray(results["node_head"]["PBV1"])[window].mean())


def test_pbv_delta_setting_shifts_operating_head():
    """Increasing PBV differential head should lower the downstream regulated face."""
    mean_20 = _pbv_downstream_mean(20.0)
    mean_40 = _pbv_downstream_mean(40.0)

    drop_ft = mean_20 - mean_40
    assert drop_ft >= 8.0, (
        f"PBV downstream head should fall when differential increases "
        f"(20 ft -> {mean_20:.1f} ft, 40 ft -> {mean_40:.1f} ft, drop {drop_ft:.1f} ft)"
    )


def test_inp_import_maps_prv_to_pressure_control_node(tmp_path: Path):
    """Imported PRV links run without downgrade warnings and produce valve-node output."""
    inp_path = tmp_path / "prv.inp"
    inp_path.write_text(
        """[JUNCTIONS]
J1   0   0
J2   0   0

[RESERVOIRS]
R1   200
R2   120

[PIPES]
P1   R1   J1   500   12   130   0   OPEN
P2   J1   J2   500   12   130   0   OPEN

[VALVES]
V1   J1   J2   12   PRV   50

[OPTIONS]
UNITS GPM
HEADLOSS H-W
""",
        encoding="utf-8",
    )

    solver = m.load_inp(
        str(inp_path),
        use_wntr=False,
        initial_flows={"P1": 300.0, "P2": 300.0, "_P_V1_up": 300.0, "_P_V1_dn": 300.0},
        initial_heads={"J1": 180.0, "J2": 150.0},
    )
    results = solver.run(total_time=0.15, dt=DT_S)

    assert "_VALVE_V1" in results["node_head"]
    # PRV setpoint for GPM: 50 psi -> 115.5 ft HGL at elevation 0 on downstream side
    prv_setpoint_ft = 50.0 * m.PSI_TO_FT
    downstream_head = float(np.max(np.asarray(results["node_head"]["_VALVE_V1"])))
    assert downstream_head <= prv_setpoint_ft + 5.0, (
        f"Imported PRV should regulate downstream head near {prv_setpoint_ft:.1f} ft, "
        f"got max {downstream_head:.1f} ft"
    )
