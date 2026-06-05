"""Phase 3 exit tests: interior DVCM on a sloping uninterrupted pipe reach."""

from __future__ import annotations

import numpy as np
import pytest

import rthym_moc as m
from rthym_moc.report import envelope_vs_chainage

pytestmark = pytest.mark.dvcm

TOTAL_TIME_S = 1.0
DT_S = 0.001
DT_FINE_S = DT_S / 2.0
ENVELOPE_RTOL = 0.01
INTERIOR_CHAINAGE_MIN_FT = 200.0
INTERIOR_CHAINAGE_MAX_FT = 1800.0
P_VAPOR_PSI = -14.0
SUMMIT_CHAINAGE_FT = 1000.0
SUMMIT_ELEVATION_FT = 250.0
MIN_COLLAPSE_SPIKE_FT = 5.0
PEAK_WINDOW_STEPS = 20
VOLUME_COLLAPSE_EPS_FT3 = 1e-9


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


def build_sloping_downsurge_solver() -> m.MOCSolver:
    """Junction-free sloping main with rapid downstream reservoir drop."""
    length_ft = 2000.0
    survey = [(0.0, 100.0), (SUMMIT_CHAINAGE_FT, SUMMIT_ELEVATION_FT), (length_ft, 50.0)]

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


def _run_interior_case(*, dt: float = DT_S) -> dict:
    return build_sloping_downsurge_solver().run(
        total_time=TOTAL_TIME_S,
        dt=dt,
        p_vapor_psi=P_VAPOR_PSI,
        cavitation_model=m.CavitationModel.DVCM,
        record_pipe_profiles=True,
        enable_interior_dvcm=True,
    )


def _interior_chainage_mask(chainage: np.ndarray) -> np.ndarray:
    return (chainage >= INTERIOR_CHAINAGE_MIN_FT) & (chainage <= INTERIOR_CHAINAGE_MAX_FT)


def _envelope_relative_error(
    coarse_chainage: np.ndarray,
    coarse_envelope: list[float],
    fine_chainage: np.ndarray,
    fine_envelope: list[float],
    interior_mask: np.ndarray,
) -> np.ndarray:
    fine_interp = np.interp(coarse_chainage, fine_chainage, fine_envelope)
    coarse_arr = np.asarray(coarse_envelope, dtype=float)
    denom = np.maximum(np.abs(fine_interp), 1e-9)
    rel = np.abs(coarse_arr - fine_interp) / denom
    return rel[interior_mask]


def _summit_index(chainage: np.ndarray) -> int:
    return int(np.argmin(np.abs(chainage - SUMMIT_CHAINAGE_FT)))


def _vapor_head_ft(elevation_ft: float, p_vapor_psi: float = P_VAPOR_PSI) -> float:
    return elevation_ft + p_vapor_psi * m.PSI_TO_FT


def _survey_z_ft(chainage_ft: float) -> float:
    survey = [(0.0, 100.0), (SUMMIT_CHAINAGE_FT, SUMMIT_ELEVATION_FT), (2000.0, 50.0)]
    if chainage_ft <= survey[0][0]:
        return survey[0][1]
    if chainage_ft >= survey[-1][0]:
        return survey[-1][1]
    for (x0, z0), (x1, z1) in zip(survey, survey[1:]):
        if chainage_ft <= x1:
            frac = (chainage_ft - x0) / (x1 - x0)
            return z0 + frac * (z1 - z0)
    return survey[-1][1]


def _volume_collapse_steps(volume_col: np.ndarray) -> list[int]:
    steps: list[int] = []
    for step in range(1, volume_col.shape[0]):
        if (
            volume_col[step - 1] > VOLUME_COLLAPSE_EPS_FT3
            and volume_col[step] < volume_col[step - 1] - VOLUME_COLLAPSE_EPS_FT3
        ):
            steps.append(step)
    return steps


def test_interior_cavity_initiates_at_summit_not_terminals() -> None:
    """Downsurge should open an interior cavity at the survey high point only."""
    results = _run_interior_case()

    chainage = np.asarray(results["pipe_profile_chainage_ft"]["P1"])
    volume = np.asarray(results["pipe_profile_cavity_volume"]["P1"])
    active = np.asarray(results["pipe_profile_cavity_active"]["P1"])

    summit_idx = _summit_index(chainage)
    upstream_idx = 0
    downstream_idx = len(chainage) - 1

    assert int(active[:, summit_idx].sum()) > 0
    assert float(volume[:, summit_idx].max()) > 0.0
    assert int(active[:, upstream_idx].sum()) == 0
    assert int(active[:, downstream_idx].sum()) == 0
    assert float(volume[:, upstream_idx].max()) == 0.0
    assert float(volume[:, downstream_idx].max()) == 0.0

    near_summit_mask = np.abs(chainage - SUMMIT_CHAINAGE_FT) <= 200.0
    near_summit_cols = np.flatnonzero(near_summit_mask)
    assert near_summit_cols.size > 0
    assert float(volume[:, near_summit_cols].max()) > 0.0
    assert int(active[:, near_summit_cols].sum()) > 0


def test_interior_collapse_produces_mid_pipe_secondary_spike() -> None:
    """Cavity collapse at the summit should produce a detectable head rise on the profile."""
    results = _run_interior_case()

    chainage = np.asarray(results["pipe_profile_chainage_ft"]["P1"])
    head = np.asarray(results["pipe_profile_head"]["P1"])
    volume = np.asarray(results["pipe_profile_cavity_volume"]["P1"])

    summit_idx = _summit_index(chainage)
    h_vap_summit = _vapor_head_ft(SUMMIT_ELEVATION_FT)

    collapse_steps = _volume_collapse_steps(volume[:, summit_idx])
    assert collapse_steps, "Expected at least one interior cavity collapse at the summit"
    collapse_step = collapse_steps[0]
    assert volume[collapse_step - 1, summit_idx] > VOLUME_COLLAPSE_EPS_FT3

    window_end = min(head.shape[0], collapse_step + PEAK_WINDOW_STEPS)
    pre_collapse_head = head[collapse_step - 1]
    post_collapse = head[collapse_step:window_end]
    post_peak_by_col = post_collapse.max(axis=0)
    rise_by_col = post_peak_by_col - pre_collapse_head

    summit_head_peak = float(post_peak_by_col[summit_idx])
    summit_rise_ft = float(rise_by_col[summit_idx])
    observed_spike_ft = summit_head_peak - h_vap_summit

    assert summit_rise_ft >= MIN_COLLAPSE_SPIKE_FT, (
        f"Expected post-collapse summit head rise >= {MIN_COLLAPSE_SPIKE_FT} ft, "
        f"got {summit_rise_ft:.2f} ft"
    )
    assert observed_spike_ft >= MIN_COLLAPSE_SPIKE_FT

    max_rise_col = int(rise_by_col.argmax())
    assert abs(float(chainage[max_rise_col]) - SUMMIT_CHAINAGE_FT) <= 50.0
    assert float(rise_by_col[0]) < MIN_COLLAPSE_SPIKE_FT
    assert float(rise_by_col[-1]) < MIN_COLLAPSE_SPIKE_FT

    junction_only = build_sloping_downsurge_solver().run(
        total_time=TOTAL_TIME_S,
        dt=DT_S,
        p_vapor_psi=P_VAPOR_PSI,
        cavitation_model=m.CavitationModel.DVCM,
        record_pipe_profiles=True,
        enable_interior_dvcm=False,
    )
    assert "pipe_profile_cavity_volume" not in junction_only
    junction_head = np.asarray(junction_only["pipe_profile_head"]["P1"])
    junction_min_summit = float(junction_head[collapse_step:window_end, summit_idx].min())
    assert junction_min_summit < h_vap_summit - 1.0


def test_interior_dvcm_dt_halving_chainage_envelope_converges() -> None:
    """Halving dt should change interior chainage envelopes by less than 1%."""
    coarse = _run_interior_case(dt=DT_S)
    fine = _run_interior_case(dt=DT_FINE_S)

    chainage_coarse = np.asarray(coarse["pipe_profile_chainage_ft"]["P1"])
    chainage_fine = np.asarray(fine["pipe_profile_chainage_ft"]["P1"])
    interior_mask = _interior_chainage_mask(chainage_coarse)

    pressure_coarse = np.asarray(coarse["pipe_profile_pressure"]["P1"])
    pressure_fine = np.asarray(fine["pipe_profile_pressure"]["P1"])
    head_coarse = np.asarray(coarse["pipe_profile_head"]["P1"])
    head_fine = np.asarray(fine["pipe_profile_head"]["P1"])

    _, pressure_max_coarse = envelope_vs_chainage(pressure_coarse)
    _, pressure_max_fine = envelope_vs_chainage(pressure_fine)
    head_min_coarse, head_max_coarse = envelope_vs_chainage(head_coarse)
    head_min_fine, head_max_fine = envelope_vs_chainage(head_fine)

    pressure_rel = _envelope_relative_error(
        chainage_coarse,
        pressure_max_coarse,
        chainage_fine,
        pressure_max_fine,
        interior_mask,
    )
    head_min_rel = _envelope_relative_error(
        chainage_coarse,
        head_min_coarse,
        chainage_fine,
        head_min_fine,
        interior_mask,
    )
    head_max_rel = _envelope_relative_error(
        chainage_coarse,
        head_max_coarse,
        chainage_fine,
        head_max_fine,
        interior_mask,
    )

    assert float(pressure_rel.max()) <= ENVELOPE_RTOL
    assert float(head_min_rel.max()) <= ENVELOPE_RTOL
    assert float(head_max_rel.max()) <= ENVELOPE_RTOL

    global_pressure_peak_rel = abs(max(pressure_max_coarse) - max(pressure_max_fine)) / max(
        pressure_max_fine
    )
    assert global_pressure_peak_rel <= ENVELOPE_RTOL
