"""Phase 2: per-pipe elevation survey on the MOC grid."""

from __future__ import annotations

import numpy as np
import pytest

import rthym_moc as m

PSI_TO_FT = m.PSI_TO_FT


def _linear_z_ft(chainage_ft: float, z_from: float, z_to: float, length_ft: float) -> float:
    if length_ft <= 0.0:
        return z_from
    frac = chainage_ft / length_ft
    return z_from + frac * (z_to - z_from)


def _survey_z_ft(
    chainage_ft: float,
    profile: list[tuple[float, float]],
) -> float:
    ordered = sorted(profile, key=lambda pair: pair[0])
    if chainage_ft <= ordered[0][0]:
        return ordered[0][1]
    if chainage_ft >= ordered[-1][0]:
        return ordered[-1][1]
    for (x0, z0), (x1, z1) in zip(ordered, ordered[1:]):
        if chainage_ft <= x1:
            frac = (chainage_ft - x0) / (x1 - x0)
            return z0 + frac * (z1 - z0)
    return ordered[-1][1]


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


def test_pipe_input_elevation_profile_defaults_empty() -> None:
    pipe = m.PipeInput()
    assert pipe.elevation_profile == []


def test_empty_elevation_profile_linear_between_node_elevations() -> None:
    """No survey table → z(x) linear between endpoint node elevations."""
    length_ft = 1000.0
    head_ft = 350.0
    z_from = 100.0
    z_to = 200.0

    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", elevation=z_from, head=head_ft))
    solver.add_node(_make_node("R2", "PressureBoundary", elevation=z_to, head=head_ft))
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

    results = solver.run(total_time=0.05, dt=0.01, record_pipe_profiles=True)
    chainage = np.asarray(results["pipe_profile_chainage_ft"]["P1"])
    pressure = np.asarray(results["pipe_profile_pressure"]["P1"])

    mid_idx = int(np.argmin(np.abs(chainage - length_ft / 2.0)))
    z_at_sample = _linear_z_ft(float(chainage[mid_idx]), z_from, z_to, length_ft)
    expected_pressure_psi = (head_ft - z_at_sample) / PSI_TO_FT

    assert pressure[0, mid_idx] == pytest.approx(expected_pressure_psi, rel=1e-6)


def test_survey_elevation_profile_overrides_linear_interpolation() -> None:
    """Piecewise survey sets summit elevation at interior chainage."""
    length_ft = 1000.0
    head_ft = 350.0
    z_summit = 300.0

    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", elevation=100.0, head=head_ft))
    solver.add_node(_make_node("R2", "PressureBoundary", elevation=200.0, head=head_ft))
    pipe = _make_pipe(
        "P1",
        "R1",
        "R2",
        length=length_ft,
        diameter=12.0,
        roughness=130.0,
        flow_gpm=0.0,
    )
    survey = [(0.0, 100.0), (500.0, z_summit), (1000.0, 200.0)]
    pipe.elevation_profile = survey
    solver.add_pipe(pipe)

    results = solver.run(total_time=0.05, dt=0.01, record_pipe_profiles=True)
    chainage = np.asarray(results["pipe_profile_chainage_ft"]["P1"])
    pressure = np.asarray(results["pipe_profile_pressure"]["P1"])

    summit_idx = int(np.argmin(np.abs(chainage - 500.0)))
    z_at_sample = _survey_z_ft(float(chainage[summit_idx]), survey)
    expected_pressure_psi = (head_ft - z_at_sample) / PSI_TO_FT

    linear_z_at_sample = _linear_z_ft(float(chainage[summit_idx]), 100.0, 200.0, length_ft)
    linear_pressure_psi = (head_ft - linear_z_at_sample) / PSI_TO_FT

    assert pressure[0, summit_idx] == pytest.approx(expected_pressure_psi, rel=1e-6)
    assert pressure[0, summit_idx] < linear_pressure_psi


def test_elevation_profile_requires_two_points() -> None:
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=100.0))
    solver.add_node(_make_node("R2", "PressureBoundary", head=90.0))
    pipe = _make_pipe("P1", "R1", "R2", length=100.0, diameter=12.0, roughness=130.0)
    pipe.elevation_profile = [(0.0, 100.0)]
    solver.add_pipe(pipe)

    with pytest.raises(ValueError, match="elevation_profile requires at least 2"):
        solver.run(total_time=0.01, dt=0.01)


def test_pipe_si_accepts_elevation_profile_m() -> None:
    pipe = m.pipe_si(
        id="P1",
        from_node="R1",
        to_node="R2",
        length_m=304.8,
        diameter_mm=304.8,
        roughness=130.0,
        elevation_profile_m=[(0.0, 30.48), (152.4, 91.44), (304.8, 60.96)],
    )
    assert len(pipe.elevation_profile) == 3
    assert pipe.elevation_profile[0][0] == pytest.approx(0.0, abs=1e-6)
    assert pipe.elevation_profile[1][0] == pytest.approx(500.0, rel=1e-3)
    assert pipe.elevation_profile[1][1] == pytest.approx(300.0, rel=1e-3)
