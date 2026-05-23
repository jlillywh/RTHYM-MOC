"""Benchmark the distributed pipe minor-loss approximation against a lumped loss."""

import numpy as np

import rthym_moc as m


DT_S = 0.005
TOTAL_TIME_S = 1.5
LUMPED_K = 100.0
SHORT_DT_S = 0.001
SHORT_TOTAL_TIME_S = 0.35


def _make_node(node_id, node_type, **kwargs):
    node = m.NodeInput()
    node.id = node_id
    node.type = node_type
    for key, value in kwargs.items():
        setattr(node, key, value)
    return node


def _make_pipe(pipe_id, from_node, to_node, **kwargs):
    pipe = m.PipeInput()
    pipe.id = pipe_id
    pipe.from_node = from_node
    pipe.to_node = to_node
    for key, value in kwargs.items():
        setattr(pipe, key, value)
    return pipe


def _equivalent_valve_setting_pct(loss_coeff):
    return 100.0 / np.sqrt(loss_coeff + 1.0)


def _rms_difference(lhs, rhs):
    lhs_values = np.asarray(lhs)
    rhs_values = np.asarray(rhs)
    return float(np.sqrt(np.mean((lhs_values - rhs_values) ** 2)))


def _mean_over_window(time_s, values, start_s, end_s):
    mask = (time_s >= start_s) & (time_s <= end_s)
    assert np.any(mask), f"No samples found in window [{start_s}, {end_s}] s"
    return float(np.asarray(values)[mask].mean())


def _run_distributed_minor_loss_case(
    lengths_ft=(550.0, 275.0, 275.0),
    dt_s=DT_S,
    total_time_s=TOTAL_TIME_S,
    valve_step_time_s=0.5,
    youngs_modulus_psi=0.0,
):
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=150.0))
    solver.add_node(_make_node("J1", "Junction"))
    solver.add_node(_make_node("V2", "Valve", diameter=12.0, current_setting=100.0))
    solver.add_node(_make_node("R2", "PressureBoundary", head=120.0))
    solver.add_pipe(
        _make_pipe(
            "P1",
            "R1",
            "J1",
            length=lengths_ft[0],
            diameter=12.0,
            roughness=130.0,
            flow_gpm=800.0,
            minor_loss=LUMPED_K,
            youngs_modulus=youngs_modulus_psi,
        )
    )
    solver.add_pipe(
        _make_pipe(
            "P2",
            "J1",
            "V2",
            length=lengths_ft[1],
            diameter=12.0,
            roughness=130.0,
            flow_gpm=800.0,
            youngs_modulus=youngs_modulus_psi,
        )
    )
    solver.add_pipe(
        _make_pipe(
            "P3",
            "V2",
            "R2",
            length=lengths_ft[2],
            diameter=12.0,
            roughness=130.0,
            flow_gpm=800.0,
            youngs_modulus=youngs_modulus_psi,
        )
    )
    solver.set_valve_schedule(
        "V2",
        [
            (0.0, 100.0),
            (valve_step_time_s - 0.01, 100.0),
            (valve_step_time_s, 70.0),
            (total_time_s, 70.0),
        ],
    )
    return solver.run(total_time=total_time_s, dt=dt_s)


def _run_equivalent_lumped_loss_case(
    lengths_ft=(550.0, 275.0, 275.0),
    dt_s=DT_S,
    total_time_s=TOTAL_TIME_S,
    valve_step_time_s=0.5,
    youngs_modulus_psi=0.0,
):
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=150.0))
    solver.add_node(
        _make_node(
            "V1",
            "Valve",
            diameter=12.0,
            current_setting=_equivalent_valve_setting_pct(LUMPED_K),
        )
    )
    solver.add_node(_make_node("V2", "Valve", diameter=12.0, current_setting=100.0))
    solver.add_node(_make_node("R2", "PressureBoundary", head=120.0))
    solver.add_pipe(
        _make_pipe(
            "P1",
            "R1",
            "V1",
            length=lengths_ft[0],
            diameter=12.0,
            roughness=130.0,
            flow_gpm=800.0,
            youngs_modulus=youngs_modulus_psi,
        )
    )
    solver.add_pipe(
        _make_pipe(
            "P2",
            "V1",
            "V2",
            length=lengths_ft[1],
            diameter=12.0,
            roughness=130.0,
            flow_gpm=800.0,
            youngs_modulus=youngs_modulus_psi,
        )
    )
    solver.add_pipe(
        _make_pipe(
            "P3",
            "V2",
            "R2",
            length=lengths_ft[2],
            diameter=12.0,
            roughness=130.0,
            flow_gpm=800.0,
            youngs_modulus=youngs_modulus_psi,
        )
    )
    solver.set_valve_schedule(
        "V2",
        [
            (0.0, 100.0),
            (valve_step_time_s - 0.01, 100.0),
            (valve_step_time_s, 70.0),
            (total_time_s, 70.0),
        ],
    )
    return solver.run(total_time=total_time_s, dt=dt_s)


def _benchmark_metrics(distributed, lumped, steady_window_s):
    time_s = np.asarray(distributed["time"])
    distributed_steady_flow_gpm = _mean_over_window(
        time_s, distributed["pipe_flow_gpm"]["P1"], steady_window_s[0], steady_window_s[1]
    )
    lumped_steady_flow_gpm = _mean_over_window(
        time_s, lumped["pipe_flow_gpm"]["P1"], steady_window_s[0], steady_window_s[1]
    )
    return {
        "steady_flow_diff_gpm": abs(distributed_steady_flow_gpm - lumped_steady_flow_gpm),
        "downstream_head_rms_ft": _rms_difference(distributed["node_head"]["V2"], lumped["node_head"]["V2"]),
        "upstream_flow_rms_gpm": _rms_difference(distributed["pipe_flow_gpm"]["P1"], lumped["pipe_flow_gpm"]["P1"]),
    }


def test_pipe_minor_loss_matches_equivalent_lumped_loss_benchmark():
    """Distributed pipe minor loss should track an equivalent explicit lumped-loss case closely."""
    distributed = _run_distributed_minor_loss_case()
    lumped = _run_equivalent_lumped_loss_case()
    metrics = _benchmark_metrics(distributed, lumped, steady_window_s=(0.2, 0.45))

    assert metrics["steady_flow_diff_gpm"] <= 1.0, (
        "Expected the distributed pipe minor-loss approximation to match the equivalent lumped-loss "
        f"steady flow within 1 GPM, got {metrics['steady_flow_diff_gpm']:.3f} GPM"
    )
    assert metrics["downstream_head_rms_ft"] <= 0.2, (
        "Expected the distributed pipe minor-loss approximation to keep the downstream control-node head "
        f"within 0.2 ft RMS of the equivalent lumped-loss case, got {metrics['downstream_head_rms_ft']:.3f} ft"
    )
    assert metrics["upstream_flow_rms_gpm"] <= 0.25, (
        "Expected the distributed pipe minor-loss approximation to keep the upstream pipe flow waveform "
        f"within 0.25 GPM RMS of the equivalent lumped-loss case, got {metrics['upstream_flow_rms_gpm']:.3f} GPM"
    )


def test_pipe_minor_loss_short_rigid_benchmark_shows_more_visible_lumping_error():
    """A shorter rigid-pipe case should still track the lumped-loss reference, but with a larger visible mismatch."""
    baseline_metrics = _benchmark_metrics(
        _run_distributed_minor_loss_case(),
        _run_equivalent_lumped_loss_case(),
        steady_window_s=(0.2, 0.45),
    )
    short_rigid_metrics = _benchmark_metrics(
        _run_distributed_minor_loss_case(
            lengths_ft=(60.0, 30.0, 30.0),
            dt_s=SHORT_DT_S,
            total_time_s=SHORT_TOTAL_TIME_S,
            valve_step_time_s=0.08,
            youngs_modulus_psi=0.0,
        ),
        _run_equivalent_lumped_loss_case(
            lengths_ft=(60.0, 30.0, 30.0),
            dt_s=SHORT_DT_S,
            total_time_s=SHORT_TOTAL_TIME_S,
            valve_step_time_s=0.08,
            youngs_modulus_psi=0.0,
        ),
        steady_window_s=(0.02, 0.06),
    )

    assert short_rigid_metrics["steady_flow_diff_gpm"] <= 0.25, (
        "Expected the short rigid distributed pipe minor-loss approximation to remain close to the equivalent "
        f"lumped-loss steady flow, got {short_rigid_metrics['steady_flow_diff_gpm']:.3f} GPM"
    )
    assert short_rigid_metrics["downstream_head_rms_ft"] <= 0.12, (
        "Expected the short rigid distributed pipe minor-loss approximation to keep the downstream control-node "
        f"head within 0.12 ft RMS of the equivalent lumped-loss case, got {short_rigid_metrics['downstream_head_rms_ft']:.3f} ft"
    )
    assert short_rigid_metrics["upstream_flow_rms_gpm"] <= 0.2, (
        "Expected the short rigid distributed pipe minor-loss approximation to keep the upstream pipe flow waveform "
        f"within 0.2 GPM RMS of the equivalent lumped-loss case, got {short_rigid_metrics['upstream_flow_rms_gpm']:.3f} GPM"
    )
    assert short_rigid_metrics["upstream_flow_rms_gpm"] >= baseline_metrics["upstream_flow_rms_gpm"] + 0.02, (
        "Expected the shorter rigid-pipe benchmark to show a more visible lumping mismatch than the longer baseline, "
        f"got baseline RMS {baseline_metrics['upstream_flow_rms_gpm']:.3f} GPM and short-case RMS {short_rigid_metrics['upstream_flow_rms_gpm']:.3f} GPM"
    )