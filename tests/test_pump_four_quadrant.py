import numpy as np
import pytest
import rthym_moc as m

DT_S = 0.01
TOTAL_TIME_S = 8.0

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

def _run_trip_case(*, has_cv=False, inertia_wr2=1.0, specific_speed=1800.0):
    solver = m.MOCSolver()
    solver.add_node(_make_node("Rlow", "PressureBoundary", head=100.0))
    solver.add_node(
        _make_node(
            "Pump1",
            "Pump",
            design_head=120.0,
            design_flow=500.0,
            current_speed=100.0,
            has_power=False,  # Power is lost at t=0
            inertia_wr2=inertia_wr2,
            speed_rpm=1750.0,
            specific_speed=specific_speed,
        )
    )
    if has_cv:
        solver.add_node(_make_node("CV1", "CheckValve", diameter=12.0, head=220.0))
        solver.add_node(_make_node("Rhigh", "PressureBoundary", head=160.0))
        solver.add_pipe(_make_pipe("P1", "Rlow", "Pump1", 500.0, 500.0))
        solver.add_pipe(_make_pipe("P2", "Pump1", "CV1", 40.0, 500.0))
        solver.add_pipe(_make_pipe("P3", "CV1", "Rhigh", 1000.0, 500.0))
    else:
        solver.add_node(_make_node("Rhigh", "PressureBoundary", head=160.0))
        solver.add_pipe(_make_pipe("P1", "Rlow", "Pump1", 500.0, 500.0))
        solver.add_pipe(_make_pipe("P2", "Pump1", "Rhigh", 1000.0, 500.0))

    return solver.run(total_time=TOTAL_TIME_S, dt=DT_S)

def test_trip_with_check_valve():
    """Verify that a check valve in series stops reverse flow while pump speed decays."""
    res = _run_trip_case(has_cv=True, inertia_wr2=1.0)
    time = np.asarray(res["time"])
    flow = np.asarray(res["pipe_flow_gpm"]["P3"])
    speed = np.asarray(res["pump_speed"]["Pump1"])

    # At the first steps, speed is decaying but still close to 100%
    assert speed[0] > 90.0
    assert flow[0] > 400.0

    # Post-trip: flow decays to near zero and check valve closes
    last_flow = flow[-1]
    assert abs(last_flow) < 5.0, f"Expected check valve to clamp flow near 0, got {last_flow:.2f} GPM"

    # Speed decays gradually due to inertia
    assert speed[10] < 99.0
    assert speed[-1] < 30.0, f"Expected speed to decay significantly, got {speed[-1]:.2f}%"

def test_trip_without_check_valve_windmilling():
    """Without a check valve, flow should reverse and pump should windmill backward."""
    res = _run_trip_case(has_cv=False, inertia_wr2=1.0)
    time = np.asarray(res["time"])
    flow = np.asarray(res["pipe_flow_gpm"]["P2"])
    speed = np.asarray(res["pump_speed"]["Pump1"])

    # Flow should reverse (go negative)
    assert np.any(flow < -10.0), f"Expected reverse flow, minimum flow was {np.min(flow):.2f} GPM"
    
    # Speed should eventually go negative (backward rotation / windmilling as a turbine)
    assert np.any(speed < 0.0), f"Expected backward rotation, minimum speed was {np.min(speed):.2f}%"

def test_inertia_sensitivity():
    """Deceleration rate should be slower for a pump with higher inertia."""
    res_low = _run_trip_case(has_cv=True, inertia_wr2=1.0)
    res_high = _run_trip_case(has_cv=True, inertia_wr2=10.0)

    time = np.asarray(res_low["time"])
    speed_low = np.asarray(res_low["pump_speed"]["Pump1"])
    speed_high = np.asarray(res_high["pump_speed"]["Pump1"])

    # At t = 2.0 s, speed of high inertia pump should be higher than low inertia pump
    eval_idx = np.argmin(np.abs(time - 2.0))
    assert speed_high[eval_idx] > speed_low[eval_idx] + 5.0, (
        f"Expected slower decay for high inertia: high={speed_high[eval_idx]:.2f}%, low={speed_low[eval_idx]:.2f}%"
    )

def test_specific_speed_influence():
    """Specific speed mapping should use different tables and yield different trajectories."""
    res_rad = _run_trip_case(has_cv=False, specific_speed=1800.0)
    res_axi = _run_trip_case(has_cv=False, specific_speed=7500.0)

    time = np.asarray(res_rad["time"])
    speed_rad = np.asarray(res_rad["pump_speed"]["Pump1"])
    speed_axi = np.asarray(res_axi["pump_speed"]["Pump1"])

    # Radial vs Axial pumps have different torque characteristics in Suter tables,
    # leading to different coast-down rates.
    eval_idx = np.argmin(np.abs(time - 3.0))
    assert abs(speed_rad[eval_idx] - speed_axi[eval_idx]) > 2.0, (
        f"Expected specific speed to influence decay curve: rad={speed_rad[eval_idx]:.2f}%, axi={speed_axi[eval_idx]:.2f}%"
    )

