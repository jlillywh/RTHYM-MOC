"""Column-separation and long-run stability regressions."""

import numpy as np

import rthym_moc as m


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


def _run_column_separation_case(total_time_s, *, k_bru=-1.0, usf_tau=0.5):
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
            (total_time_s, 0.0),
        ],
    )
    return solver.run(total_time=total_time_s, dt=0.01, p_vapor_psi=-14.0, usf_tau=usf_tau, k_bru=k_bru)


def test_column_separation_forms_then_rejoins_after_valve_closure():
    """A severe valve closure should create a vapor-pocket episode that later collapses and clears."""
    data = _run_column_separation_case(total_time_s=10.0)
    time_s = np.asarray(data["time"])
    valve_head_ft = np.asarray(data["node_head"]["V1"])
    valve_cavitation = np.asarray(data["node_cavitation"]["V1"])

    trip_window = (time_s >= 4.8) & (time_s <= 5.5)
    recovery_window = (time_s >= 9.0) & (time_s <= 10.0)

    assert int(valve_cavitation.sum()) >= 200, (
        f"Expected an extended cavitation episode at V1, got only {int(valve_cavitation.sum())} cavitating steps"
    )
    assert int(valve_cavitation[trip_window].sum()) >= 50, (
        f"Expected strong trip-window column separation at V1, got {int(valve_cavitation[trip_window].sum())} cavitating steps"
    )
    assert float(np.min(valve_head_ft[trip_window])) <= -30.0, (
        f"Expected deep subatmospheric collapse during separation, got minimum head {float(np.min(valve_head_ft[trip_window])):.2f} ft"
    )
    assert int(valve_cavitation[recovery_window].sum()) == 0, (
        f"Expected the vapor pocket to collapse and clear by the late recovery window, got {int(valve_cavitation[recovery_window].sum())} cavitating steps"
    )
    assert _mean_over_window(time_s, valve_head_ft, 9.0, 10.0) >= 140.0, (
        f"Expected the valve-node head to recover close to the upstream boundary after rejoining, got {_mean_over_window(time_s, valve_head_ft, 9.0, 10.0):.2f} ft"
    )


def test_extended_damped_transient_remains_finite_and_does_not_drift_late():
    """An extended damped run should stay finite and show a decaying late-time envelope rather than numerical growth."""
    data = _run_column_separation_case(total_time_s=20.0, k_bru=0.02, usf_tau=0.5)
    time_s = np.asarray(data["time"])
    valve_head_ft = np.asarray(data["node_head"]["V1"])
    upstream_flow_gpm = np.asarray(data["pipe_flow_gpm"]["P1"])

    mid_window = (time_s >= 8.0) & (time_s <= 12.0)
    late_window = (time_s >= 16.0) & (time_s <= 20.0)

    mid_head_abs_ft = float(np.mean(np.abs(valve_head_ft[mid_window] - 150.0)))
    late_head_abs_ft = float(np.mean(np.abs(valve_head_ft[late_window] - 150.0)))
    mid_flow_std_gpm = float(np.std(upstream_flow_gpm[mid_window]))
    late_flow_std_gpm = float(np.std(upstream_flow_gpm[late_window]))
    late_flow_mean_gpm = float(np.mean(upstream_flow_gpm[late_window]))

    assert np.isfinite(valve_head_ft).all(), "Expected the extended transient head trace to remain finite throughout the run"
    assert np.isfinite(upstream_flow_gpm).all(), "Expected the extended transient flow trace to remain finite throughout the run"
    assert late_head_abs_ft <= 3.0, (
        f"Expected the late-time head envelope to stay small after damping, got {late_head_abs_ft:.2f} ft mean absolute deviation"
    )
    assert late_flow_std_gpm <= 5.0, (
        f"Expected the late-time flow oscillation to remain bounded, got {late_flow_std_gpm:.2f} GPM standard deviation"
    )
    assert abs(late_flow_mean_gpm) <= 1.0, (
        f"Expected negligible late-time mean flow drift after damping, got {late_flow_mean_gpm:.2f} GPM"
    )
    assert late_head_abs_ft <= mid_head_abs_ft * 0.25, (
        f"Expected the late head envelope to decay materially relative to the mid-run window, got late={late_head_abs_ft:.2f} ft and mid={mid_head_abs_ft:.2f} ft"
    )
    assert late_flow_std_gpm <= mid_flow_std_gpm * 0.25, (
        f"Expected the late flow envelope to decay materially relative to the mid-run window, got late={late_flow_std_gpm:.2f} GPM and mid={mid_flow_std_gpm:.2f} GPM"
    )