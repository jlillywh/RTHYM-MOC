"""Boundary-condition, unsteady-friction, and local-loss regressions.

These tests cover a set of basic but important transient controls:

- sudden junction-demand changes within a single run
- sudden fixed-head boundary changes representing reservoir / pressure-boundary steps
- the effect of enabling an unsteady-friction correction versus steady friction only
- the effect of stronger local loss at a throttled valve
"""

import numpy as np

import rthym_moc as m

DT_S = 0.01
DEMAND_TOTAL_TIME_S = 10.0
HEAD_TOTAL_TIME_S = 10.0
LOSS_TOTAL_TIME_S = 2.0
USF_TOTAL_TIME_S = 8.0


def _make_node(node_id, node_type, **kwargs):
    node = m.NodeInput()
    node.id = node_id
    node.type = node_type
    for key, value in kwargs.items():
        setattr(node, key, value)
    return node


def _make_pipe(pipe_id, from_node, to_node, length_ft, flow_gpm, diameter_in=12.0):
    pipe = m.PipeInput()
    pipe.id = pipe_id
    pipe.from_node = from_node
    pipe.to_node = to_node
    pipe.length = length_ft
    pipe.flow_gpm = flow_gpm
    pipe.diameter = diameter_in
    pipe.roughness = 130.0
    return pipe


def _mean_over_window(time_s, values, start_s, end_s):
    mask = (time_s >= start_s) & (time_s <= end_s)
    assert np.any(mask), f"No samples found in window [{start_s}, {end_s}] s"
    return float(np.asarray(values)[mask].mean())


def _run_demand_step_case():
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=150.0))
    solver.add_node(_make_node("J1", "Junction", head=145.0, demand=500.0))
    solver.add_pipe(_make_pipe("P1", "R1", "J1", 3000.0, 500.0))
    solver.set_demand_schedule(
        "J1",
        [
            (0.0, 500.0),
            (4.99, 500.0),
            (5.0, 700.0),
            (DEMAND_TOTAL_TIME_S, 700.0),
        ],
    )
    return solver.run(total_time=DEMAND_TOTAL_TIME_S, dt=DT_S)


def _run_boundary_head_step_case():
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=150.0))
    solver.add_node(_make_node("R2", "PressureBoundary", head=145.0))
    solver.add_pipe(_make_pipe("P1", "R1", "R2", 3000.0, 500.0))
    solver.set_head_schedule(
        "R2",
        [
            (0.0, 145.0),
            (4.99, 145.0),
            (5.0, 130.0),
            (HEAD_TOTAL_TIME_S, 130.0),
        ],
    )
    return solver.run(total_time=HEAD_TOTAL_TIME_S, dt=DT_S)


def _run_usf_case(k_bru, usf_tau):
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=150.0))
    solver.add_node(_make_node("V1", "Valve", diameter=12.0, current_setting=100.0, head=148.0))
    solver.add_node(_make_node("R2", "PressureBoundary", head=147.9))
    solver.add_pipe(_make_pipe("P1", "R1", "V1", 3000.0, 500.0))
    solver.add_pipe(_make_pipe("P2", "V1", "R2", 40.0, 500.0))
    solver.set_valve_schedule(
        "V1",
        [
            (0.0, 100.0),
            (0.09, 100.0),
            (0.1, 0.0),
            (USF_TOTAL_TIME_S, 0.0),
        ],
    )
    return solver.run(total_time=USF_TOTAL_TIME_S, dt=DT_S, p_vapor_psi=-14.0, usf_tau=usf_tau, k_bru=k_bru)


def _run_valve_loss_case(setting_pct):
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=150.0))
    solver.add_node(_make_node("V1", "Valve", diameter=12.0, current_setting=setting_pct, head=148.0))
    solver.add_node(_make_node("R2", "PressureBoundary", head=120.0))
    solver.add_pipe(_make_pipe("P1", "R1", "V1", 1000.0, 800.0))
    solver.add_pipe(_make_pipe("P2", "V1", "R2", 100.0, 800.0))
    return solver.run(total_time=LOSS_TOTAL_TIME_S, dt=DT_S)


def test_demand_step_increases_flow_and_drops_junction_head():
    """A sudden demand increase should pull down the junction head and increase inflow."""
    data = _run_demand_step_case()
    time_s = np.asarray(data["time"])
    pre_head_ft = _mean_over_window(time_s, data["node_head"]["J1"], 1.0, 4.0)
    post_head_ft = _mean_over_window(time_s, data["node_head"]["J1"], 5.2, 6.0)
    pre_flow_gpm = _mean_over_window(time_s, data["pipe_flow_gpm"]["P1"], 1.0, 4.0)
    post_flow_gpm = _mean_over_window(time_s, data["pipe_flow_gpm"]["P1"], 5.2, 6.0)

    assert pre_head_ft - post_head_ft >= 100.0, (
        f"Expected the demand step to drop J1 head by at least 100 ft, got {pre_head_ft - post_head_ft:.2f} ft"
    )
    assert post_flow_gpm - pre_flow_gpm >= 80.0, (
        f"Expected the demand step to increase inflow by at least 80 GPM, got {post_flow_gpm - pre_flow_gpm:.2f} GPM"
    )


def test_fixed_head_step_updates_boundary_head_and_increases_pipe_flow():
    """A sudden fixed-head change should be honored directly and alter the through-flow."""
    data = _run_boundary_head_step_case()
    time_s = np.asarray(data["time"])
    pre_downstream_head_ft = _mean_over_window(time_s, data["node_head"]["R2"], 1.0, 4.0)
    post_downstream_head_ft = _mean_over_window(time_s, data["node_head"]["R2"], 5.2, 6.0)
    pre_flow_gpm = _mean_over_window(time_s, data["pipe_flow_gpm"]["P1"], 1.0, 4.0)
    post_flow_gpm = _mean_over_window(time_s, data["pipe_flow_gpm"]["P1"], 5.2, 6.0)

    assert abs(pre_downstream_head_ft - 145.0) <= 0.5, (
        f"Expected the scheduled pre-step boundary head to stay near 145 ft, got {pre_downstream_head_ft:.2f} ft"
    )
    assert abs(post_downstream_head_ft - 130.0) <= 0.5, (
        f"Expected the scheduled post-step boundary head to stay near 130 ft, got {post_downstream_head_ft:.2f} ft"
    )
    assert post_flow_gpm - pre_flow_gpm >= 15.0, (
        f"Expected the downstream head drop to increase pipe flow by at least 15 GPM, got {post_flow_gpm - pre_flow_gpm:.2f} GPM"
    )


def test_unsteady_friction_changes_late_time_oscillation_damping():
    """Turning on a static Brunone term should materially change the late oscillation envelope."""
    steady = _run_usf_case(k_bru=0.0, usf_tau=DT_S)
    unsteady = _run_usf_case(k_bru=0.02, usf_tau=0.5)
    time_s = np.asarray(steady["time"])
    steady_head_ft = np.asarray(steady["node_head"]["V1"])
    unsteady_head_ft = np.asarray(unsteady["node_head"]["V1"])

    steady_late_abs_ft = float(np.mean(np.abs(steady_head_ft[(time_s >= 4.0) & (time_s <= 6.0)] - 150.0)))
    unsteady_late_abs_ft = float(np.mean(np.abs(unsteady_head_ft[(time_s >= 4.0) & (time_s <= 6.0)] - 150.0)))

    assert steady_late_abs_ft - unsteady_late_abs_ft >= 80.0, (
        f"Expected the unsteady-friction model to change the late oscillation envelope by at least 80 ft, got {steady_late_abs_ft - unsteady_late_abs_ft:.2f} ft"
    )


def test_stronger_valve_local_loss_reduces_flow_and_raises_upstream_head():
    """A more throttled valve should impose a stronger local loss at the same boundaries."""
    open_case = _run_valve_loss_case(setting_pct=100.0)
    throttled_case = _run_valve_loss_case(setting_pct=5.0)
    time_s = np.asarray(open_case["time"])
    open_flow_gpm = _mean_over_window(time_s, open_case["pipe_flow_gpm"]["P1"], 0.5, 1.5)
    throttled_flow_gpm = _mean_over_window(time_s, throttled_case["pipe_flow_gpm"]["P1"], 0.5, 1.5)
    open_valve_head_ft = _mean_over_window(time_s, open_case["node_head"]["V1"], 0.5, 1.5)
    throttled_valve_head_ft = _mean_over_window(time_s, throttled_case["node_head"]["V1"], 0.5, 1.5)

    assert open_flow_gpm - throttled_flow_gpm >= 100.0, (
        f"Expected the stronger valve loss to reduce steady flow by at least 100 GPM, got {open_flow_gpm - throttled_flow_gpm:.2f} GPM"
    )
    assert throttled_valve_head_ft - open_valve_head_ft >= 20.0, (
        f"Expected the stronger valve loss to raise upstream valve-node head by at least 20 ft, got {throttled_valve_head_ft - open_valve_head_ft:.2f} ft"
    )