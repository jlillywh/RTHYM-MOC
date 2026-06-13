"""Phase 4: sparse interior DVCM at user-listed chainage watchpoints."""

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


def _sloping_downsurge_solver(
    *,
    chainages_ft: list[float] | None = None,
) -> m.MOCSolver:
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
        flow_gpm=0.0,
    )
    pipe.elevation_profile = survey
    if chainages_ft is not None:
        pipe.interior_dvcm_chainages_ft = chainages_ft
    solver.add_pipe(pipe)
    solver.set_head_schedule("R1", [(0.0, 320.0), (0.001, 200.0)])
    return solver


def test_pipe_input_interior_dvcm_chainages_defaults_empty() -> None:
    pipe = m.PipeInput()
    assert pipe.interior_dvcm_chainages_ft == []


def test_chainages_snap_to_nearest_grid_index() -> None:
    length_ft = 1000.0
    dt = 0.01
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", elevation=0.0, head=100.0))
    solver.add_node(_make_node("R2", "PressureBoundary", elevation=0.0, head=100.0))
    pipe = _make_pipe("P1", "R1", "R2", length=length_ft, diameter=12.0, roughness=130.0)
    pipe.interior_dvcm_chainages_ft = [480.0, 520.0, 999.0]
    solver.add_pipe(pipe)
    solver.set_enable_interior_dvcm(True)

    results = solver.run(
        total_time=0.01,
        dt=dt,
        cavitation_model=m.CavitationModel.DVCM,
    )

    n_seg = results["pipe_num_segments"]["P1"]
    dx = length_ft / n_seg
    expected = sorted(
        {
            max(1, min(round(chainage / dx), n_seg - 1))
            for chainage in pipe.interior_dvcm_chainages_ft
        }
    )
    snapped = results["pipe_interior_dvcm_grid_indices"]["P1"]
    assert snapped == expected
    assert all(1 <= j <= n_seg - 1 for j in snapped)


def test_sparse_dvcm_cavity_only_at_summit_watchpoint() -> None:
    solver = _sloping_downsurge_solver(chainages_ft=[1000.0])
    results = solver.run(
        total_time=0.5,
        dt=0.001,
        cavitation_model=m.CavitationModel.DVCM,
        record_pipe_profiles=True,
        enable_interior_dvcm=True,
    )

    chainage = np.asarray(results["pipe_profile_chainage_ft"]["P1"], dtype=float)
    cavity_active = np.asarray(results["pipe_profile_cavity_active"]["P1"], dtype=int)
    summit_idx = int(np.argmin(np.abs(chainage - 1000.0)))
    upstream_idx = int(np.argmin(np.abs(chainage - 200.0)))

    assert np.any(cavity_active[:, summit_idx] > 0)
    assert not np.any(cavity_active[:, upstream_idx] > 0)


def test_sparse_matches_full_when_watchpoints_cover_interior() -> None:
    solver_full = _sloping_downsurge_solver(chainages_ft=None)
    full = solver_full.run(
        total_time=0.5,
        dt=0.001,
        cavitation_model=m.CavitationModel.DVCM,
        record_pipe_profiles=True,
        enable_interior_dvcm=True,
    )

    n_seg = full["pipe_num_segments"]["P1"]
    length_ft = 2000.0
    dx = length_ft / n_seg
    all_chainages = [j * dx for j in range(1, n_seg)]

    solver_sparse = _sloping_downsurge_solver(chainages_ft=all_chainages)
    sparse = solver_sparse.run(
        total_time=0.5,
        dt=0.001,
        cavitation_model=m.CavitationModel.DVCM,
        record_pipe_profiles=True,
        enable_interior_dvcm=True,
    )

    vol_full = np.asarray(full["pipe_profile_cavity_volume"]["P1"], dtype=float)
    vol_sparse = np.asarray(sparse["pipe_profile_cavity_volume"]["P1"], dtype=float)
    np.testing.assert_allclose(vol_sparse, vol_full, rtol=1e-4, atol=1e-6)

    head_full = np.asarray(full["pipe_profile_head"]["P1"], dtype=float)
    head_sparse = np.asarray(sparse["pipe_profile_head"]["P1"], dtype=float)
    np.testing.assert_allclose(head_sparse, head_full, rtol=1e-4, atol=1e-3)


def test_full_interior_omits_sparse_index_export_key() -> None:
    solver = _sloping_downsurge_solver(chainages_ft=None)
    results = solver.run(
        total_time=0.05,
        dt=0.001,
        cavitation_model=m.CavitationModel.DVCM,
        enable_interior_dvcm=True,
    )
    assert "pipe_interior_dvcm_grid_indices" not in results
