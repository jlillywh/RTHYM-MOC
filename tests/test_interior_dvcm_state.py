"""Phase 3: interior-point DVCM segment state scaffolding."""

from __future__ import annotations

import numpy as np
import pytest

import rthym_moc as m

pytestmark = pytest.mark.dvcm


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


def _sloping_pipe_solver(*, flow_gpm: float = 0.0) -> m.MOCSolver:
    length_ft = 2000.0
    survey = [(0.0, 100.0), (1000.0, 280.0), (length_ft, 120.0)]
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", elevation=100.0, head=320.0))
    solver.add_node(_make_node("R2", "PressureBoundary", elevation=120.0, head=320.0))
    pipe = _make_pipe(
        "P1",
        "R1",
        "R2",
        length=length_ft,
        diameter=12.0,
        roughness=130.0,
        flow_gpm=flow_gpm,
    )
    pipe.elevation_profile = survey
    solver.add_pipe(pipe)
    return solver


def test_interior_dvcm_defaults_off() -> None:
    solver = m.MOCSolver()
    assert solver.get_enable_interior_dvcm() is False


def test_interior_dvcm_flag_persists_on_solver() -> None:
    solver = m.MOCSolver()
    solver.set_enable_interior_dvcm(True)
    assert solver.get_enable_interior_dvcm() is True


def test_interior_dvcm_off_omits_profile_cavity_keys() -> None:
    solver = _sloping_pipe_solver()
    results = solver.run(
        total_time=0.05,
        dt=0.01,
        cavitation_model=m.CavitationModel.DVCM,
        record_pipe_profiles=True,
    )
    assert "pipe_profile_cavity_volume" not in results
    assert "pipe_profile_cavity_active" not in results


def test_interior_dvcm_zero_flow_stays_liquid_full() -> None:
    """Uniform static head with no transient leaves all segment cavities empty."""
    solver = _sloping_pipe_solver()
    results = solver.run(
        total_time=0.05,
        dt=0.01,
        cavitation_model=m.CavitationModel.DVCM,
        record_pipe_profiles=True,
        enable_interior_dvcm=True,
    )
    chainage = np.asarray(results["pipe_profile_chainage_ft"]["P1"])
    volume = np.asarray(results["pipe_profile_cavity_volume"]["P1"])
    active = np.asarray(results["pipe_profile_cavity_active"]["P1"])

    assert volume.shape == active.shape
    assert volume.shape[1] == len(chainage)
    assert np.all(volume == 0.0)
    assert np.all(active == 0)


def _summit_downsurge_solver() -> m.MOCSolver:
    length_ft = 2000.0
    survey = [(0.0, 100.0), (1000.0, 250.0), (length_ft, 50.0)]
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", elevation=100.0, head=280.0))
    solver.add_node(_make_node("R2", "PressureBoundary", elevation=50.0, head=280.0))
    pipe = _make_pipe(
        "P1",
        "R1",
        "R2",
        length=length_ft,
        diameter=12.0,
        roughness=130.0,
        flow_gpm=500.0,
    )
    pipe.elevation_profile = survey
    solver.add_pipe(pipe)
    solver.set_head_schedule("R2", [(0.0, 280.0), (0.02, 60.0)])
    return solver


def test_interior_dvcm_regime_activates_cavity_at_survey_summit() -> None:
    """Downsurge on a sloping main should grow interior cavity volume at the high point."""
    solver = _summit_downsurge_solver()
    results = solver.run(
        total_time=0.8,
        dt=0.001,
        p_vapor_psi=-14.0,
        cavitation_model=m.CavitationModel.DVCM,
        record_pipe_profiles=True,
        enable_interior_dvcm=True,
    )

    chainage = np.asarray(results["pipe_profile_chainage_ft"]["P1"])
    volume = np.asarray(results["pipe_profile_cavity_volume"]["P1"])
    active = np.asarray(results["pipe_profile_cavity_active"]["P1"])
    head = np.asarray(results["pipe_profile_head"]["P1"])

    summit_idx = int(np.argmin(np.abs(chainage - 1000.0)))
    upstream_idx = 0
    downstream_idx = len(chainage) - 1

    assert int(active[:, summit_idx].sum()) > 0
    assert float(volume[:, summit_idx].max()) > 0.0
    assert int(active[:, upstream_idx].sum()) == 0
    assert int(active[:, downstream_idx].sum()) == 0
    assert float(volume[:, upstream_idx].max()) == 0.0
    assert float(volume[:, downstream_idx].max()) == 0.0

    p_vapor_ft = -14.0 * m.PSI_TO_FT
    z_summit = 250.0
    h_vap_summit = z_summit + p_vapor_ft
    active_steps = np.flatnonzero(active[:, summit_idx] == 1)
    assert active_steps.size > 0
    assert np.all(head[active_steps, summit_idx] >= h_vap_summit - 1e-3)


def test_interior_dvcm_off_matches_junction_only_dvcm_regression() -> None:
    """Default-off interior DVCM must not change junction DVCM telemetry."""
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", elevation=100.0, head=350.0))
    solver.add_node(_make_node("V1", "Valve", elevation=100.0, current_setting=100.0, diameter=8.0))
    solver.add_node(_make_node("R2", "PressureBoundary", elevation=100.0, head=200.0))
    solver.add_pipe(
        _make_pipe("P1", "R1", "V1", length=500.0, diameter=12.0, roughness=130.0, flow_gpm=500.0)
    )
    solver.add_pipe(
        _make_pipe("P2", "V1", "R2", length=500.0, diameter=12.0, roughness=130.0, flow_gpm=500.0)
    )
    solver.set_valve_schedule("V1", [(0.0, 100.0), (0.05, 0.0)])

    baseline = solver.run(
        total_time=0.2,
        dt=0.01,
        cavitation_model=m.CavitationModel.DVCM,
        enable_interior_dvcm=False,
    )
    with_interior_flag = solver.run(
        total_time=0.2,
        dt=0.01,
        cavitation_model=m.CavitationModel.DVCM,
        enable_interior_dvcm=False,
    )
    np.testing.assert_array_equal(
        baseline["node_cavity_active"]["V1"],
        with_interior_flag["node_cavity_active"]["V1"],
    )


def test_interior_dvcm_detects_nan_blowup() -> None:
    """Interior DVCM guards fail fast on arithmetic overflow like junction DVCM."""
    solver = _sloping_pipe_solver()
    solver.set_head_schedule("R1", [(0.0, 1e300)])
    solver.set_head_schedule("R2", [(0.0, -1e300)])

    with pytest.raises(RuntimeError, match="Numerical instability"):
        solver.run(
            total_time=0.1,
            dt=0.01,
            cavitation_model=m.CavitationModel.DVCM,
            record_pipe_profiles=True,
            enable_interior_dvcm=True,
        )


def test_interior_dvcm_segment_volumes_finite_and_bounded() -> None:
    """Committed interior cavity state stays finite and within dx·A capacity."""
    solver = _summit_downsurge_solver()
    results = solver.run(
        total_time=0.8,
        dt=0.001,
        p_vapor_psi=-14.0,
        cavitation_model=m.CavitationModel.DVCM,
        record_pipe_profiles=True,
        enable_interior_dvcm=True,
    )

    volume = np.asarray(results["pipe_profile_cavity_volume"]["P1"], dtype=float)
    head = np.asarray(results["pipe_profile_head"]["P1"], dtype=float)
    velocity = np.asarray(results["pipe_profile_velocity_fps"]["P1"], dtype=float)

    assert np.isfinite(volume).all()
    assert np.isfinite(head).all()
    assert np.isfinite(velocity).all()
    assert (volume >= -1e-12).all()

    length_ft = 2000.0
    diameter_ft = 12.0 / 12.0
    area_ft2 = np.pi * (diameter_ft / 2.0) ** 2
    dt_s = 0.001
    n_reaches = max(1, int(round(length_ft / (4000.0 * dt_s))))
    dx_ft = length_ft / n_reaches
    capacity_ft3 = dx_ft * area_ft2
    assert float(volume.max()) <= capacity_ft3 + 1e-6


def test_results_to_si_converts_interior_cavity_profile_volume() -> None:
    solver = _sloping_pipe_solver()
    results = solver.run(
        total_time=0.02,
        dt=0.01,
        record_pipe_profiles=True,
        enable_interior_dvcm=True,
        cavitation_model=m.CavitationModel.DVCM,
    )
    si = m.results_to_si(results)
    np.testing.assert_allclose(
        si["pipe_profile_cavity_volume_m3"]["P1"],
        results["pipe_profile_cavity_volume"]["P1"] * m.FT3_TO_M3,
    )
    np.testing.assert_array_equal(
        si["pipe_profile_cavity_active"]["P1"],
        results["pipe_profile_cavity_active"]["P1"],
    )
