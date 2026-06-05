"""Phase 4: MOC grid scaling cap and wave-speed distortion reporting."""

from __future__ import annotations

import warnings

import pytest

import rthym_moc as m
from rthym_moc.report import summarize_study, summarize_study_si


def _make_node(node_id: str, node_type: str, **kwargs) -> m.NodeInput:
    node = m.NodeInput()
    node.id = node_id
    node.type = node_type
    for key, value in kwargs.items():
        setattr(node, key, value)
    return node


def _make_pipe(pipe_id: str, from_node: str, to_node: str, **kwargs) -> m.PipeInput:
    pipe = m.PipeInput()
    pipe.id = pipe_id
    pipe.from_node = from_node
    pipe.to_node = to_node
    for key, value in kwargs.items():
        setattr(pipe, key, value)
    return pipe


def _two_reservoir_solver(*, length_ft: float = 4000.0) -> m.MOCSolver:
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", elevation=100.0, head=320.0))
    solver.add_node(_make_node("R2", "PressureBoundary", elevation=100.0, head=320.0))
    solver.add_pipe(
        _make_pipe(
            "P1",
            "R1",
            "R2",
            length=length_ft,
            diameter=12.0,
            roughness=130.0,
            flow_gpm=0.0,
        )
    )
    return solver


def _expected_grid_scaling(
    *,
    length_ft: float,
    dt: float,
    design_a_fps: float = 4000.0,
    max_segments: int = 0,
) -> tuple[int, float, float, float]:
    """Hand calculation mirroring MOCSolver::initGrid() segment logic."""
    n = max(1, round(length_ft / (design_a_fps * dt)))
    if max_segments > 0:
        n = min(n, max_segments)
        n = max(n, 2)
    a_adj = length_ft / (n * dt)
    distortion_pct = abs(a_adj - design_a_fps) / design_a_fps * 100.0
    return n, design_a_fps, a_adj, distortion_pct


def test_max_segments_default_uncapped() -> None:
    solver = m.MOCSolver()
    assert solver.get_max_segments_per_pipe() == 0


def test_set_max_segments_negative_raises() -> None:
    solver = m.MOCSolver()
    with pytest.raises(ValueError, match="max_segments_per_pipe"):
        solver.set_max_segments_per_pipe(-1)


def test_max_segments_cap_coarsens_grid() -> None:
    length_ft = 4000.0
    dt = 0.01
    cap = 50
    exp_n, exp_design, exp_adj, exp_dist = _expected_grid_scaling(
        length_ft=length_ft,
        dt=dt,
        max_segments=cap,
    )
    assert exp_n == cap

    solver = _two_reservoir_solver(length_ft=length_ft)
    solver.set_max_segments_per_pipe(cap)
    results = solver.run(total_time=0.02, dt=dt)

    assert results["pipe_num_segments"]["P1"] == exp_n
    assert results["pipe_wave_speed_design_fps"]["P1"] == pytest.approx(exp_design)
    assert results["pipe_wave_speed_adjusted_fps"]["P1"] == pytest.approx(exp_adj)
    assert results["pipe_distortion_pct"]["P1"] == pytest.approx(exp_dist)


def test_minimum_two_segments_when_cap_active() -> None:
    length_ft = 50.0
    dt = 0.01
    exp_n, _, exp_adj, exp_dist = _expected_grid_scaling(
        length_ft=length_ft,
        dt=dt,
        max_segments=2000,
    )
    assert exp_n == 2

    solver = _two_reservoir_solver(length_ft=length_ft)
    solver.set_max_segments_per_pipe(2000)
    results = solver.run(total_time=0.02, dt=dt)

    assert results["pipe_num_segments"]["P1"] == 2
    assert results["pipe_wave_speed_adjusted_fps"]["P1"] == pytest.approx(exp_adj)
    assert results["pipe_distortion_pct"]["P1"] == pytest.approx(exp_dist)


def test_distortion_report_matches_hand_calculation() -> None:
    length_ft = 4000.0
    dt = 0.01
    _, exp_design, exp_adj, exp_dist = _expected_grid_scaling(length_ft=length_ft, dt=dt)

    solver = _two_reservoir_solver(length_ft=length_ft)
    results = solver.run(total_time=0.02, dt=dt)

    assert results["pipe_wave_speed_design_fps"]["P1"] == pytest.approx(exp_design)
    assert results["pipe_wave_speed_adjusted_fps"]["P1"] == pytest.approx(exp_adj)
    assert results["pipe_distortion_pct"]["P1"] == pytest.approx(exp_dist, rel=0.0, abs=1e-9)


def test_summarize_study_includes_per_pipe_grid_scaling() -> None:
    length_ft = 4000.0
    dt = 0.01
    cap = 50
    exp_n, exp_design, exp_adj, exp_dist = _expected_grid_scaling(
        length_ft=length_ft,
        dt=dt,
        max_segments=cap,
    )

    solver = _two_reservoir_solver(length_ft=length_ft)
    solver.set_max_segments_per_pipe(cap)
    results = solver.run(total_time=0.02, dt=dt)
    summary = summarize_study(results, dt_s=dt)
    pipe = summary["pipes"]["P1"]

    assert pipe["num_segments"] == exp_n
    assert pipe["wave_speed_design_fps"] == pytest.approx(exp_design)
    assert pipe["wave_speed_adjusted_fps"] == pytest.approx(exp_adj)
    assert pipe["distortion_pct"] == pytest.approx(exp_dist)

    summary_si = summarize_study_si(results, dt_s=dt)
    pipe_si = summary_si["pipes"]["P1"]
    assert pipe_si["wave_speed_design_m_s"] == pytest.approx(exp_design * m.FTS_TO_MS)
    assert pipe_si["wave_speed_adjusted_m_s"] == pytest.approx(exp_adj * m.FTS_TO_MS)
    assert pipe_si["distortion_pct"] == pytest.approx(exp_dist)


def test_distortion_threshold_disabled_by_default() -> None:
    solver = m.MOCSolver()
    assert solver.get_max_wave_speed_distortion() < 0.0


def test_distortion_no_action_when_under_threshold() -> None:
    solver = _two_reservoir_solver(length_ft=4000.0)
    solver.set_max_wave_speed_distortion(0.15)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        solver.run(total_time=0.02, dt=0.01)
    assert not any(
        issubclass(item.category, UserWarning) and "Wave-speed distortion" in str(item.message)
        for item in caught
    )


def test_distortion_warns_when_exceeds_threshold() -> None:
    solver = _two_reservoir_solver(length_ft=4000.0)
    solver.set_grid_policy(
        max_segments_per_pipe=50,
        max_wave_speed_distortion=0.15,
        distortion_action="warn",
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        solver.run(total_time=0.02, dt=0.01)
    distortion_warnings = [
        item for item in caught
        if issubclass(item.category, UserWarning) and "Wave-speed distortion" in str(item.message)
    ]
    assert len(distortion_warnings) == 1
    assert "P1" in str(distortion_warnings[0].message)


def test_distortion_error_raises_when_exceeds_threshold() -> None:
    solver = _two_reservoir_solver(length_ft=4000.0)
    solver.set_grid_policy(
        max_segments_per_pipe=50,
        max_wave_speed_distortion=0.15,
        distortion_action="error",
    )
    with pytest.raises(RuntimeError, match="Wave-speed distortion limit exceeded"):
        solver.run(total_time=0.02, dt=0.01)


def test_set_max_wave_speed_distortion_invalid_raises() -> None:
    solver = m.MOCSolver()
    with pytest.raises(ValueError, match="max_wave_speed_distortion"):
        solver.set_max_wave_speed_distortion(1.5)


def test_set_wave_speed_distortion_action_invalid_raises() -> None:
    solver = m.MOCSolver()
    with pytest.raises(ValueError, match="wave_speed_distortion_action"):
        solver.set_wave_speed_distortion_action("ignore")


def test_disable_distortion_threshold_with_negative_value() -> None:
    solver = _two_reservoir_solver(length_ft=4000.0)
    solver.set_max_wave_speed_distortion(0.15)
    solver.set_max_wave_speed_distortion(-1.0)
    solver.set_grid_policy(max_segments_per_pipe=50)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        solver.run(total_time=0.02, dt=0.01)
    assert not any("Wave-speed distortion" in str(item.message) for item in caught)
