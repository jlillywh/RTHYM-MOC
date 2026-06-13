"""Phase 7: canonical multi-mile sloping long-pipeline surge validation.

Combines elevation survey (Phase 2), interior DVCM (Phase 3), grid scaling
(Phase 4), and profile export (Phase 1) on a junction-free transmission reach.
Maps to validation cases LP-02 (summit static minimum), LP-03 (interior cavity),
and LP-04 (collapse secondary spike) in docs/long_pipeline_surge_roadmap.md.
"""

from __future__ import annotations

import numpy as np
import pytest

import rthym_moc as m
from long_pipeline_surge_utils import (
    CASE_ID,
    DEFAULT_DT_S,
    DEFAULT_GRID_CAP,
    DEFAULT_LENGTH_FT,
    DEFAULT_LENGTH_MI,
    DEFAULT_TOTAL_TIME_S,
    P_VAPOR_PSI,
    SUMMIT_CHAINAGE_FT,
    SUMMIT_ELEVATION_FT,
    build_long_pipeline_solver,
    default_survey,
    expected_grid_distortion_pct,
    run_long_pipeline_case,
    survey_z_ft,
)
from rthym_moc.report import summarize_study

pytestmark = pytest.mark.dvcm

MIN_COLLAPSE_SPIKE_FT = 2.5
PEAK_WINDOW_STEPS = 30
VOLUME_COLLAPSE_EPS_FT3 = 1e-9


def _summit_index(chainage: np.ndarray) -> int:
    return int(np.argmin(np.abs(chainage - SUMMIT_CHAINAGE_FT)))


def _vapor_head_ft(elevation_ft: float) -> float:
    return elevation_ft + P_VAPOR_PSI * m.PSI_TO_FT


def _volume_collapse_steps(volume_col: np.ndarray) -> list[int]:
    steps: list[int] = []
    for step in range(1, volume_col.shape[0]):
        if (
            volume_col[step - 1] > VOLUME_COLLAPSE_EPS_FT3
            and volume_col[step] < volume_col[step - 1] - VOLUME_COLLAPSE_EPS_FT3
        ):
            steps.append(step)
    return steps


def test_long_pipeline_case_metadata_and_grid_cap() -> None:
    """LP-SURGE-01: multi-mile reach runs with capped grid and documented distortion."""
    exp_n, exp_dist = expected_grid_distortion_pct()
    solver = build_long_pipeline_solver()
    results = run_long_pipeline_case(solver, total_time_s=0.02)

    assert results["pipe_num_segments"]["Pmain"] == exp_n
    assert results["pipe_num_segments"]["Pmain"] <= DEFAULT_GRID_CAP
    assert results["pipe_distortion_pct"]["Pmain"] == pytest.approx(exp_dist, rel=1e-9)
    assert "pipe_profile_chainage_ft" in results
    chainage = results["pipe_profile_chainage_ft"]["Pmain"]
    assert len(chainage) == exp_n + 1
    assert chainage[-1] == pytest.approx(
        DEFAULT_LENGTH_FT,
        rel=1e-3,
    )


def test_long_pipeline_static_minimum_at_summit_lp02() -> None:
    """LP-02: on a multi-mile sloping pipe, static min gauge P is at the survey summit."""
    survey = default_survey()
    solver = build_long_pipeline_solver()
    results = run_long_pipeline_case(
        solver,
        total_time_s=0.01,
        enable_interior_dvcm=False,
    )

    chainage = np.asarray(results["pipe_profile_chainage_ft"]["Pmain"])
    pressure = np.asarray(results["pipe_profile_pressure"]["Pmain"])

    summit_idx = _summit_index(chainage)
    min_idx = int(np.argmin(pressure[0]))

    assert min_idx == summit_idx
    z_summit = survey_z_ft(float(chainage[summit_idx]), survey)
    expected_psi = (520.0 - z_summit) / m.PSI_TO_FT
    assert pressure[0, summit_idx] == pytest.approx(expected_psi, rel=1e-5)
    assert pressure[0, min_idx] < pressure[0, 0]
    assert pressure[0, min_idx] < pressure[0, -1]


def test_long_pipeline_interior_cavity_at_summit_lp03() -> None:
    """LP-03: downsurge opens interior cavity at the summit, not at pipe terminals."""
    solver = build_long_pipeline_solver()
    results = run_long_pipeline_case(solver)

    chainage = np.asarray(results["pipe_profile_chainage_ft"]["Pmain"])
    volume = np.asarray(results["pipe_profile_cavity_volume"]["Pmain"])
    active = np.asarray(results["pipe_profile_cavity_active"]["Pmain"])

    summit_idx = _summit_index(chainage)
    assert int(active[:, summit_idx].sum()) > 0
    assert float(volume[:, summit_idx].max()) > 0.0
    assert int(active[:, 0].sum()) == 0
    assert int(active[:, -1].sum()) == 0
    assert float(volume[:, 0].max()) == 0.0
    assert float(volume[:, -1].max()) == 0.0


def test_long_pipeline_collapse_secondary_spike_lp04() -> None:
    """LP-04: refill after downsurge collapses the summit cavity with a head spike."""
    solver = build_long_pipeline_solver(with_refill=True)
    results = run_long_pipeline_case(solver)

    chainage = np.asarray(results["pipe_profile_chainage_ft"]["Pmain"])
    head = np.asarray(results["pipe_profile_head"]["Pmain"])
    volume = np.asarray(results["pipe_profile_cavity_volume"]["Pmain"])

    summit_idx = _summit_index(chainage)
    h_vap_summit = _vapor_head_ft(SUMMIT_ELEVATION_FT)

    collapse_steps = _volume_collapse_steps(volume[:, summit_idx])
    assert collapse_steps, "Expected interior cavity collapse at the multi-mile summit"
    collapse_step = collapse_steps[0]

    window_end = min(head.shape[0], collapse_step + PEAK_WINDOW_STEPS)
    pre_collapse_head = head[collapse_step - 1, summit_idx]
    post_peak_summit = float(head[collapse_step:window_end, summit_idx].max())
    rise_ft = post_peak_summit - pre_collapse_head

    assert rise_ft >= MIN_COLLAPSE_SPIKE_FT
    assert post_peak_summit - h_vap_summit >= MIN_COLLAPSE_SPIKE_FT
    assert abs(float(chainage[summit_idx]) - SUMMIT_CHAINAGE_FT) <= 200.0


def test_long_pipeline_sparse_dvcm_at_summit_watchpoint() -> None:
    """Sparse interior DVCM at the summit chainage captures cavity activity."""
    full = build_long_pipeline_solver(sparse_dvcm_at_summit=False)
    sparse = build_long_pipeline_solver(sparse_dvcm_at_summit=True)

    full_results = run_long_pipeline_case(full)
    sparse_results = run_long_pipeline_case(sparse)

    full_vol = np.asarray(full_results["pipe_profile_cavity_volume"]["Pmain"])
    sparse_vol = np.asarray(sparse_results["pipe_profile_cavity_volume"]["Pmain"])
    chainage = np.asarray(full_results["pipe_profile_chainage_ft"]["Pmain"])
    summit_idx = _summit_index(chainage)

    assert float(sparse_vol[:, summit_idx].max()) > 0.0
    assert float(full_vol[:, summit_idx].max()) > 0.0

    sparse_indices = sparse_results["pipe_interior_dvcm_grid_indices"]["Pmain"]
    assert len(sparse_indices) == 1
    assert sparse_indices[0] == summit_idx

    interior_cols = np.arange(1, len(chainage) - 1)
    non_watch = [j for j in interior_cols if j != summit_idx]
    assert float(sparse_vol[:, non_watch].max()) == 0.0


def test_long_pipeline_summarize_study_chainage_envelope() -> None:
    """Study report includes grid scaling and per-pipe chainage envelopes."""
    exp_n, exp_dist = expected_grid_distortion_pct()
    solver = build_long_pipeline_solver()
    results = run_long_pipeline_case(solver, total_time_s=2.0)
    summary = summarize_study(results, dt_s=DEFAULT_DT_S)

    pipe = summary["pipes"]["Pmain"]
    assert pipe["num_segments"] == exp_n
    assert pipe["distortion_pct"] == pytest.approx(exp_dist, rel=1e-9)
    assert "chainage_envelope" in pipe
    envelope = pipe["chainage_envelope"]
    assert len(envelope["chainage_ft"]) == len(results["pipe_profile_chainage_ft"]["Pmain"])
    assert len(envelope["head_min_ft"]) == len(envelope["chainage_ft"])
    assert len(envelope["head_max_ft"]) == len(envelope["chainage_ft"])

    summit_idx = _summit_index(np.asarray(envelope["chainage_ft"]))
    assert envelope["pressure_min_psi"][summit_idx] <= envelope["pressure_min_psi"][0]
    assert envelope["pressure_min_psi"][summit_idx] <= envelope["pressure_min_psi"][-1]


@pytest.mark.slow
def test_long_pipeline_full_transient_window_completes() -> None:
    """End-to-end multi-mile sloping interior-DVCM run for the canonical window."""
    solver = build_long_pipeline_solver()
    results = run_long_pipeline_case(solver, total_time_s=DEFAULT_TOTAL_TIME_S)

    assert len(results["time"]) == int(DEFAULT_TOTAL_TIME_S / DEFAULT_DT_S)
    assert results["pipe_num_segments"]["Pmain"] == DEFAULT_GRID_CAP
    assert float(np.max(results["pipe_profile_cavity_volume"]["Pmain"])) > 0.0
    assert CASE_ID == "LP-SURGE-01"
    assert DEFAULT_LENGTH_MI >= 5.0
