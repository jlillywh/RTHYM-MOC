"""Long-pipeline surge verification helpers (tests + ``long_pipeline_surge_verification.ipynb``)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
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

MIN_COLLAPSE_SPIKE_FT = 2.5
PEAK_WINDOW_STEPS = 30
VOLUME_COLLAPSE_EPS_FT3 = 1e-9
STATIC_HEAD_FT = 520.0


def summit_index(chainage: np.ndarray) -> int:
    return int(np.argmin(np.abs(chainage - SUMMIT_CHAINAGE_FT)))


def vapor_head_ft(elevation_ft: float) -> float:
    return elevation_ft + P_VAPOR_PSI * m.PSI_TO_FT


def volume_collapse_steps(volume_col: np.ndarray) -> list[int]:
    steps: list[int] = []
    for step in range(1, volume_col.shape[0]):
        if (
            volume_col[step - 1] > VOLUME_COLLAPSE_EPS_FT3
            and volume_col[step] < volume_col[step - 1] - VOLUME_COLLAPSE_EPS_FT3
        ):
            steps.append(step)
    return steps


@dataclass(frozen=True)
class GridCapMetrics:
    case_id: str
    length_mi: float
    num_segments: int
    distortion_pct: float
    passed: bool


@dataclass(frozen=True)
class SummitStaticMetrics:
    summit_chainage_ft: float
    min_pressure_psi: float
    min_at_summit: bool
    passed: bool


@dataclass(frozen=True)
class SummitCavityMetrics:
    summit_max_volume_ft3: float
    summit_active_steps: int
    terminal_cavity_steps: int
    passed: bool


@dataclass(frozen=True)
class CollapseSpikeMetrics:
    collapse_step: int
    rise_ft: float
    peak_above_vapor_ft: float
    passed: bool


def evaluate_grid_cap(results: dict) -> GridCapMetrics:
    exp_n, exp_dist = expected_grid_distortion_pct()
    n = int(results["pipe_num_segments"]["Pmain"])
    dist = float(results["pipe_distortion_pct"]["Pmain"])
    chainage = results["pipe_profile_chainage_ft"]["Pmain"]
    passed = (
        n == exp_n
        and n <= DEFAULT_GRID_CAP
        and abs(dist - exp_dist) < 1e-6
        and len(chainage) == exp_n + 1
        and abs(float(chainage[-1]) - DEFAULT_LENGTH_FT) < 1.0
    )
    return GridCapMetrics(CASE_ID, DEFAULT_LENGTH_MI, n, dist, passed)


def evaluate_summit_static(results: dict) -> SummitStaticMetrics:
    survey = default_survey()
    chainage = np.asarray(results["pipe_profile_chainage_ft"]["Pmain"])
    pressure = np.asarray(results["pipe_profile_pressure"]["Pmain"])
    idx = summit_index(chainage)
    min_idx = int(np.argmin(pressure[0]))
    z_summit = survey_z_ft(float(chainage[idx]), survey)
    expected_psi = (STATIC_HEAD_FT - z_summit) / m.PSI_TO_FT
    passed = (
        min_idx == idx
        and abs(float(pressure[0, idx]) - expected_psi) < 1e-4
        and pressure[0, idx] < pressure[0, 0]
        and pressure[0, idx] < pressure[0, -1]
    )
    return SummitStaticMetrics(
        float(chainage[idx]),
        float(pressure[0, idx]),
        min_idx == idx,
        passed,
    )


def evaluate_summit_cavity(results: dict) -> SummitCavityMetrics:
    chainage = np.asarray(results["pipe_profile_chainage_ft"]["Pmain"])
    volume = np.asarray(results["pipe_profile_cavity_volume"]["Pmain"])
    active = np.asarray(results["pipe_profile_cavity_active"]["Pmain"])
    idx = summit_index(chainage)
    terminal = int(active[:, 0].sum()) + int(active[:, -1].sum())
    passed = (
        int(active[:, idx].sum()) > 0
        and float(volume[:, idx].max()) > 0.0
        and terminal == 0
        and float(volume[:, 0].max()) == 0.0
        and float(volume[:, -1].max()) == 0.0
    )
    return SummitCavityMetrics(
        float(volume[:, idx].max()),
        int(active[:, idx].sum()),
        terminal,
        passed,
    )


def evaluate_collapse_spike(results: dict) -> CollapseSpikeMetrics:
    chainage = np.asarray(results["pipe_profile_chainage_ft"]["Pmain"])
    head = np.asarray(results["pipe_profile_head"]["Pmain"])
    volume = np.asarray(results["pipe_profile_cavity_volume"]["Pmain"])
    idx = summit_index(chainage)
    h_vap = vapor_head_ft(SUMMIT_ELEVATION_FT)
    collapses = volume_collapse_steps(volume[:, idx])
    if not collapses:
        return CollapseSpikeMetrics(-1, 0.0, 0.0, False)
    collapse_step = collapses[0]
    window_end = min(head.shape[0], collapse_step + PEAK_WINDOW_STEPS)
    pre = float(head[collapse_step - 1, idx])
    post_peak = float(head[collapse_step:window_end, idx].max())
    rise = post_peak - pre
    above_vap = post_peak - h_vap
    passed = (
        rise >= MIN_COLLAPSE_SPIKE_FT
        and above_vap >= MIN_COLLAPSE_SPIKE_FT
        and abs(float(chainage[idx]) - SUMMIT_CHAINAGE_FT) <= 200.0
    )
    return CollapseSpikeMetrics(collapse_step, rise, above_vap, passed)


def run_downsurge_case(
    *,
    total_time_s: float = DEFAULT_TOTAL_TIME_S,
) -> dict:
    solver = build_long_pipeline_solver()
    return run_long_pipeline_case(solver, total_time_s=total_time_s)


def run_static_preview() -> dict:
    solver = build_long_pipeline_solver()
    return run_long_pipeline_case(
        solver,
        total_time_s=0.01,
        enable_interior_dvcm=False,
    )


def run_refill_collapse_case(
    *,
    total_time_s: float = DEFAULT_TOTAL_TIME_S,
) -> dict:
    solver = build_long_pipeline_solver(with_refill=True)
    return run_long_pipeline_case(solver, total_time_s=total_time_s)
