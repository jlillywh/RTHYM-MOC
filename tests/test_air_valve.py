"""Air-valve regressions for finite admission, release, and trapped-air effects."""

import numpy as np

import rthym_moc as m

DT_S = 0.01
TOTAL_TIME_S = 12.0
PRE_EVENT_START_S = 1.0
PRE_EVENT_END_S = 4.0
TRIP_START_S = 5.2
TRIP_END_S = 6.0
RESTART_EARLY_START_S = 8.2
RESTART_EARLY_END_S = 9.0
RESTART_LATE_START_S = 10.5
RESTART_LATE_END_S = 11.5


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


def _run_case(with_air_valve, restart=False):
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
    if with_air_valve:
        solver.add_node(
            _make_node(
                "Vent",
                "AirValve",
                elevation=0.0,
                head=160.0,
                diameter=6.0,
                air_release_diameter=0.25,
                gas_volume=0.05,
                tank_volume=2.0,
                loss_coeff_in=0.8,
                loss_coeff_out=0.7,
            )
        )
    else:
        solver.add_node(_make_node("Vent", "Junction", elevation=0.0, head=160.0))
    solver.add_node(_make_node("Rhigh", "PressureBoundary", head=160.0))

    solver.add_pipe(_make_pipe("Ps", "Rlow", "PumpIn", 500.0, 800.0))
    solver.add_pipe(_make_pipe("Ppump", "Pump_A", "Jd", 40.0, 800.0))
    solver.add_pipe(_make_pipe("Pstub", "Jd", "Vent", 40.0, 800.0))
    solver.add_pipe(_make_pipe("Pmain", "Vent", "Rhigh", 4000.0, 800.0))

    solver.set_pump_schedule(
        "Pump_A",
        [
            (0.0, 100.0),
            (4.99, 100.0),
            (5.0, 0.0),
            (7.99, 0.0),
            (8.0, 100.0 if restart else 0.0),
            (TOTAL_TIME_S, 100.0 if restart else 0.0),
        ],
    )
    return solver.run(total_time=TOTAL_TIME_S, dt=DT_S)


def test_air_valve_stays_closed_during_positive_pressure_initial_state():
    """Before the trip, the vent node should stay highly pressurised and inactive."""
    data = _run_case(with_air_valve=True)
    time_s = np.asarray(data["time"])
    vent_head = np.asarray(data["node_head"]["Vent"])
    vent_cav = np.asarray(data["node_cavitation"]["Vent"])
    pre_head_ft = _mean_over_window(time_s, vent_head, PRE_EVENT_START_S, PRE_EVENT_END_S)

    pre_mask = (time_s >= PRE_EVENT_START_S) & (time_s <= PRE_EVENT_END_S)

    assert pre_head_ft >= 150.0, f"Expected the air valve to remain closed in the loaded pre-trip state, got {pre_head_ft:.2f} ft"
    assert int(vent_cav[pre_mask].sum()) == 0, "Air valve should not cavitate during the pre-trip operating window"


def test_air_valve_prevents_subatmospheric_collapse_after_pump_trip():
    """Finite air admission should keep the vent much higher than the unprotected vacuum collapse."""
    unprotected = _run_case(with_air_valve=False)
    protected = _run_case(with_air_valve=True)

    base_time = np.asarray(unprotected["time"])
    protected_time = np.asarray(protected["time"])

    base_vent_trip_ft = _mean_over_window(base_time, unprotected["node_head"]["Vent"], TRIP_START_S, TRIP_END_S)
    protected_vent_trip_ft = _mean_over_window(protected_time, protected["node_head"]["Vent"], TRIP_START_S, TRIP_END_S)
    base_jd_trip_ft = _mean_over_window(base_time, unprotected["node_head"]["Jd"], TRIP_START_S, TRIP_END_S)
    protected_jd_trip_ft = _mean_over_window(protected_time, protected["node_head"]["Jd"], TRIP_START_S, TRIP_END_S)

    base_vent_min_ft = float(np.min(np.asarray(unprotected["node_head"]["Vent"])))
    protected_trip_min_ft = float(np.min(np.asarray(protected["node_head"]["Vent"])[(protected_time >= TRIP_START_S) & (protected_time <= TRIP_END_S)]))
    protected_trip_cav_steps = int(np.asarray(protected["node_cavitation"]["Vent"])[(protected_time >= TRIP_START_S) & (protected_time <= TRIP_END_S)].sum())

    assert base_vent_trip_ft < 0.0, f"Expected the unprotected vent node to go subatmospheric after trip, got {base_vent_trip_ft:.2f} ft"
    assert protected_vent_trip_ft >= -5.0, f"Expected finite air admission to keep the vent near atmosphere on average, got {protected_vent_trip_ft:.2f} ft"
    assert protected_trip_min_ft >= -5.0, f"Expected the finite-rate air valve to avoid a deep trip-window vacuum collapse, got {protected_trip_min_ft:.2f} ft"
    assert base_vent_min_ft <= -30.0, f"Expected deep vacuum without protection, got minimum head {base_vent_min_ft:.2f} ft"
    assert protected_trip_cav_steps == 0, f"Expected no trip-window cavitation at the air-valve node, got {protected_trip_cav_steps} cavitating steps"
    assert protected_jd_trip_ft - base_jd_trip_ft >= 10.0, (
        f"Expected the air valve to improve the nearby discharge-node trip head by at least 10 ft, got {protected_jd_trip_ft - base_jd_trip_ft:.2f} ft"
    )


def test_air_valve_trapped_air_releases_gradually_after_pump_restart():
    """A small release orifice should leave a temporary air cushion after restart."""
    restarted = _run_case(with_air_valve=True, restart=True)
    time_s = np.asarray(restarted["time"])
    vent_head = np.asarray(restarted["node_head"]["Vent"])

    pretrip_head_ft = _mean_over_window(time_s, vent_head, PRE_EVENT_START_S, PRE_EVENT_END_S)
    early_restart_head_ft = _mean_over_window(time_s, vent_head, RESTART_EARLY_START_S, RESTART_EARLY_END_S)
    late_restart_head_ft = _mean_over_window(time_s, vent_head, RESTART_LATE_START_S, RESTART_LATE_END_S)

    assert early_restart_head_ft >= pretrip_head_ft + 30.0, (
        f"Expected trapped-air compression to create an early restart overshoot above the pre-trip state, got early={early_restart_head_ft:.2f} ft vs pre={pretrip_head_ft:.2f} ft"
    )
    assert early_restart_head_ft >= late_restart_head_ft + 30.0, (
        f"Expected gradual air release to decay the early restart overshoot, got early={early_restart_head_ft:.2f} ft and late={late_restart_head_ft:.2f} ft"
    )
    assert abs(late_restart_head_ft - pretrip_head_ft) <= 10.0, (
        f"Expected the vent head to settle back near the pre-trip level after air release, got late={late_restart_head_ft:.2f} ft vs pre={pretrip_head_ft:.2f} ft"
    )
