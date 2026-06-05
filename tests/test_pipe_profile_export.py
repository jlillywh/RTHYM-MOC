"""Phase 1: optional per-pipe MOC grid profile export."""

import math
import time

import numpy as np
import pytest

import rthym_moc as m

G_FT_S2 = m.G_FT_S2
GPM_TO_CFS = m.GPM_TO_CFS
MIDPIPE_JOUKOWSKY_TOL_FT = 25.0


def _make_node(node_id: str, node_type: str, **kwargs: float | str | bool) -> m.NodeInput:
    node = m.NodeInput()
    node.id = node_id
    node.type = node_type
    for key, value in kwargs.items():
        setattr(node, key, value)
    return node


def _make_pipe(pipe_id: str, from_node: str, to_node: str, **kwargs: float | str) -> m.PipeInput:
    pipe = m.PipeInput()
    pipe.id = pipe_id
    pipe.from_node = from_node
    pipe.to_node = to_node
    for key, value in kwargs.items():
        setattr(pipe, key, value)
    return pipe


def _single_pipe_solver() -> m.MOCSolver:
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", elevation=0.0, head=150.0))
    solver.add_node(_make_node("R2", "PressureBoundary", elevation=0.0, head=0.0))
    solver.add_pipe(
        _make_pipe(
            "P1",
            "R1",
            "R2",
            length=3000.0,
            diameter=12.0,
            roughness=130.0,
            flow_gpm=500.0,
        )
    )
    return solver


def test_profile_export_disabled_by_default() -> None:
    results = _single_pipe_solver().run(total_time=0.2, dt=0.01)
    assert "pipe_profile_chainage_ft" not in results
    assert "pipe_profile_head" not in results
    assert "pipe_profile_pressure" not in results
    assert "pipe_profile_velocity_fps" not in results


def test_profile_export_shapes_and_endpoints() -> None:
    solver = _single_pipe_solver()
    dt = 0.01
    total_time = 0.2
    results = solver.run(total_time=total_time, dt=dt, record_pipe_profiles=True)

    chainage = np.asarray(results["pipe_profile_chainage_ft"]["P1"])
    head_profile = np.asarray(results["pipe_profile_head"]["P1"])
    pressure_profile = np.asarray(results["pipe_profile_pressure"]["P1"])
    velocity_profile = np.asarray(results["pipe_profile_velocity_fps"]["P1"])
    time_s = np.asarray(results["time"])

    assert chainage.ndim == 1
    assert chainage[0] == pytest.approx(0.0)
    assert chainage[-1] == pytest.approx(3000.0, rel=1e-3)

    assert head_profile.shape == (time_s.size, chainage.size)
    assert pressure_profile.shape == head_profile.shape
    assert velocity_profile.shape == head_profile.shape

    # Pipe-end grid heads should match upstream/downstream node telemetry.
    np.testing.assert_allclose(
        head_profile[:, 0],
        np.asarray(results["node_head"]["R1"]),
        rtol=0.0,
        atol=1e-9,
    )
    np.testing.assert_allclose(
        head_profile[:, -1],
        np.asarray(results["node_head"]["R2"]),
        rtol=0.0,
        atol=1e-9,
    )


def test_profile_stride_downsamples_spatial_points() -> None:
    solver = _single_pipe_solver()
    full = solver.run(total_time=0.1, dt=0.01, record_pipe_profiles=True, profile_stride=1)
    sparse = solver.run(total_time=0.1, dt=0.01, record_pipe_profiles=True, profile_stride=4)

    n_full = np.asarray(full["pipe_profile_chainage_ft"]["P1"]).size
    n_sparse = np.asarray(sparse["pipe_profile_chainage_ft"]["P1"]).size
    assert n_sparse < n_full
    assert np.asarray(sparse["pipe_profile_head"]["P1"]).shape[1] == n_sparse


def test_profile_stride_invalid() -> None:
    solver = _single_pipe_solver()
    with pytest.raises(ValueError, match="profile_stride"):
        solver.run(total_time=0.1, dt=0.01, record_pipe_profiles=True, profile_stride=0)


def test_profile_valve_end_matches_node_head() -> None:
    """Downstream pipe-end grid head should match inline valve node telemetry."""
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", elevation=0.0, head=150.0))
    solver.add_node(_make_node("V1", "Valve", elevation=0.0, diameter=12.0, current_setting=0.0))
    solver.add_node(_make_node("R2", "PressureBoundary", elevation=0.0, head=0.0))
    solver.add_pipe(
        _make_pipe(
            "P1",
            "R1",
            "V1",
            length=3000.0,
            diameter=12.0,
            roughness=130.0,
            flow_gpm=500.0,
        )
    )
    solver.add_pipe(
        _make_pipe(
            "P2",
            "V1",
            "R2",
            length=40.0,
            diameter=12.0,
            roughness=130.0,
            flow_gpm=500.0,
        )
    )

    dt = 0.01
    results = solver.run(total_time=dt, dt=dt, record_pipe_profiles=True)
    head_p1 = np.asarray(results["pipe_profile_head"]["P1"])

    np.testing.assert_allclose(
        head_p1[:, -1],
        np.asarray(results["node_head"]["V1"]),
        rtol=0.0,
        atol=1e-9,
    )


def test_midpipe_head_rises_after_wave_arrival() -> None:
    """Interior midpoint should upsurge once the wave transits half the penstock."""
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", elevation=0.0, head=150.0))
    solver.add_node(_make_node("V1", "Valve", elevation=0.0, diameter=12.0, current_setting=0.0))
    solver.add_node(_make_node("R2", "PressureBoundary", elevation=0.0, head=0.0))
    solver.add_pipe(
        _make_pipe(
            "P1",
            "R1",
            "V1",
            length=3000.0,
            diameter=12.0,
            roughness=130.0,
            flow_gpm=500.0,
        )
    )
    solver.add_pipe(
        _make_pipe(
            "P2",
            "V1",
            "R2",
            length=40.0,
            diameter=12.0,
            roughness=130.0,
            flow_gpm=500.0,
        )
    )

    dt = 0.01
    a_fps = 4000.0
    half_length_ft = 1500.0
    arrival_s = half_length_ft / a_fps
    total_time = arrival_s + 2.0 * dt
    results = solver.run(total_time=total_time, dt=dt, record_pipe_profiles=True)

    chainage = np.asarray(results["pipe_profile_chainage_ft"]["P1"])
    head_p1 = np.asarray(results["pipe_profile_head"]["P1"])
    mid_idx = int(np.argmin(np.abs(chainage - half_length_ft)))

    assert head_p1[-1, mid_idx] > head_p1[0, mid_idx]


def test_midpipe_head_matches_joukowsky_after_downstream_closure() -> None:
    """Interior midpoint upsurge should match ΔH = a·V₀/g within project tolerances."""
    length_ft = 3000.0
    diameter_in = 12.0
    flow_gpm = 500.0
    wave_speed_fps = 4000.0
    dt = 0.01

    area_ft2 = math.pi * (diameter_in / 12.0 / 2.0) ** 2
    v0_fps = flow_gpm * GPM_TO_CFS / area_ft2
    dh_jouk_ft = wave_speed_fps * v0_fps / G_FT_S2

    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", elevation=0.0, head=150.0))
    solver.add_node(_make_node("V1", "Valve", elevation=0.0, diameter=diameter_in, current_setting=0.0))
    solver.add_node(_make_node("R2", "PressureBoundary", elevation=0.0, head=0.0))
    solver.add_pipe(
        _make_pipe(
            "P1",
            "R1",
            "V1",
            length=length_ft,
            diameter=diameter_in,
            roughness=130.0,
            flow_gpm=flow_gpm,
        )
    )
    solver.add_pipe(
        _make_pipe(
            "P2",
            "V1",
            "R2",
            length=40.0,
            diameter=diameter_in,
            roughness=130.0,
            flow_gpm=flow_gpm,
        )
    )

    arrival_s = (length_ft / 2.0) / wave_speed_fps
    total_time = arrival_s + 1.0
    results = solver.run(total_time=total_time, dt=dt, record_pipe_profiles=True)

    time_s = np.asarray(results["time"])
    chainage = np.asarray(results["pipe_profile_chainage_ft"]["P1"])
    head_p1 = np.asarray(results["pipe_profile_head"]["P1"])
    mid_idx = int(np.argmin(np.abs(chainage - length_ft / 2.0)))

    delta_series_ft = head_p1[:, mid_idx] - head_p1[0, mid_idx]
    first_transit_mask = time_s <= arrival_s + 0.5
    peak_delta_ft = float(np.max(delta_series_ft[first_transit_mask]))
    assert peak_delta_ft == pytest.approx(dh_jouk_ft, abs=MIDPIPE_JOUKOWSKY_TOL_FT)


def test_profile_stride_preserves_pipe_end_chainage() -> None:
    solver = _single_pipe_solver()
    sparse = solver.run(total_time=0.1, dt=0.01, record_pipe_profiles=True, profile_stride=4)
    chainage = np.asarray(sparse["pipe_profile_chainage_ft"]["P1"])

    assert chainage[0] == pytest.approx(0.0)
    assert chainage[-1] == pytest.approx(3000.0, rel=1e-3)


def test_multi_pipe_profile_export() -> None:
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=120.0))
    solver.add_node(_make_node("J1", "Junction", elevation=0.0, head=100.0))
    solver.add_node(_make_node("R2", "PressureBoundary", head=80.0))
    solver.add_pipe(_make_pipe("P1", "R1", "J1", length=1200.0, diameter=12.0, roughness=130.0, flow_gpm=200.0))
    solver.add_pipe(_make_pipe("P2", "J1", "R2", length=900.0, diameter=12.0, roughness=130.0, flow_gpm=200.0))

    results = solver.run(total_time=0.1, dt=0.01, record_pipe_profiles=True)

    expected_lengths = {"P1": 1200.0, "P2": 900.0}
    for pipe_id, length_ft in expected_lengths.items():
        chainage = np.asarray(results["pipe_profile_chainage_ft"][pipe_id])
        head_profile = np.asarray(results["pipe_profile_head"][pipe_id])
        assert chainage.ndim == 1
        assert head_profile.shape == (len(results["time"]), chainage.size)
        assert chainage[0] == pytest.approx(0.0)
        assert chainage[-1] == pytest.approx(length_ft, rel=1e-3)


def test_profile_export_disabled_faster_than_enabled() -> None:
    """Phase 1 exit: disabled export must not dominate runtime vs enabled runs."""
    solver = _single_pipe_solver()
    reps = 4

    def _elapsed(record: bool) -> float:
        start = time.perf_counter()
        for _ in range(reps):
            solver.run(total_time=0.2, dt=0.01, record_pipe_profiles=record)
        return time.perf_counter() - start

    t_disabled = _elapsed(False)
    t_enabled = _elapsed(True)
    assert t_disabled < t_enabled
    assert t_enabled / t_disabled > 1.0
