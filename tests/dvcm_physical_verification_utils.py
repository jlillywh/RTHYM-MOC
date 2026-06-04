"""Shared helpers for DVCM independent physical verification (tests + notebook)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import rthym_moc


# Same transient used by tests/test_dvcm_physical_verification.py
DEFAULT_HEAD_SCHEDULE: list[tuple[float, float]] = [
    (0.0, 100.0),
    (0.02, 100.0),
    (0.03, 20.0),
    (0.5, 20.0),
    (0.51, 160.0),
    (3.0, 160.0),
]

DEFAULT_DT_S = 0.01
DEFAULT_TOTAL_TIME_S = 2.5
DEFAULT_P_VAPOR_PSI = 50.0
DEFAULT_PIPE_LENGTH_FT = 40.0
DEFAULT_PIPE_DIAMETER_IN = 8.0


def build_cavitation_network() -> rthym_moc.MOCSolver:
    """Symmetric reservoir–pipe–junction–pipe–reservoir column-separation geometry."""
    solver = rthym_moc.MOCSolver()

    r1 = rthym_moc.NodeInput()
    r1.id = "R1"
    r1.type = "Tank"
    r1.head = 100.0

    j1 = rthym_moc.NodeInput()
    j1.id = "J1"
    j1.type = "Junction"
    j1.head = 100.0

    r2 = rthym_moc.NodeInput()
    r2.id = "R2"
    r2.type = "Tank"
    r2.head = 100.0

    p1 = rthym_moc.PipeInput()
    p1.id = "P1"
    p1.from_node = "R1"
    p1.to_node = "J1"
    p1.length = DEFAULT_PIPE_LENGTH_FT
    p1.diameter = DEFAULT_PIPE_DIAMETER_IN
    p1.roughness = 120.0

    p2 = rthym_moc.PipeInput()
    p2.id = "P2"
    p2.from_node = "J1"
    p2.to_node = "R2"
    p2.length = DEFAULT_PIPE_LENGTH_FT
    p2.diameter = DEFAULT_PIPE_DIAMETER_IN
    p2.roughness = 120.0

    solver.add_node(r1)
    solver.add_node(j1)
    solver.add_node(r2)
    solver.add_pipe(p1)
    solver.add_pipe(p2)
    return solver


def run_physical_verification_case(
    *,
    dt: float = DEFAULT_DT_S,
    total_time: float = DEFAULT_TOTAL_TIME_S,
    p_vapor_psi: float = DEFAULT_P_VAPOR_PSI,
    schedule: Iterable[tuple[float, float]] | None = None,
) -> dict:
    solver = build_cavitation_network()
    head_schedule = list(schedule) if schedule is not None else DEFAULT_HEAD_SCHEDULE
    solver.set_head_schedule("R1", head_schedule)
    solver.set_head_schedule("R2", head_schedule)
    return solver.run(
        total_time=total_time,
        dt=dt,
        p_vapor_psi=p_vapor_psi,
        cavitation_model=rthym_moc.CavitationModel.DVCM,
    )


def junction_cavity_capacity_ft3(
    *,
    length_ft: float = DEFAULT_PIPE_LENGTH_FT,
    diameter_in: float = DEFAULT_PIPE_DIAMETER_IN,
) -> float:
    area_ft2 = np.pi * ((diameter_in / 12.0) / 2.0) ** 2
    return (0.5 * area_ft2 * length_ft) + (0.5 * area_ft2 * length_ft)


def adjusted_wave_speed_ft_s(
    *,
    length_ft: float = DEFAULT_PIPE_LENGTH_FT,
    dt: float = DEFAULT_DT_S,
    design_wave_speed_ft_s: float = 4000.0,
) -> float:
    """Courant grid adjustment used by MOCSolver (N = round(L / (a * dt)))."""
    n_reaches = int(round(length_ft / (design_wave_speed_ft_s * dt)))
    n_reaches = max(n_reaches, 1)
    return length_ft / (n_reaches * dt)


def vapor_head_ft(p_vapor_psi: float = DEFAULT_P_VAPOR_PSI) -> float:
    return p_vapor_psi * rthym_moc.PSI_TO_FT


@dataclass(frozen=True)
class MassConservationMetrics:
    max_abs_step_error_ft3: float
    max_rel_step_error: float
    n_steps_checked: int
    passed: bool


def evaluate_mass_conservation(
    results: dict,
    *,
    node_id: str = "J1",
    in_pipe_id: str = "P1",
    out_pipe_id: str = "P2",
    dt: float = DEFAULT_DT_S,
    rtol: float = 0.02,
    atol_ft3: float = 1e-5,
) -> MassConservationMetrics:
    """Check dV/dt = (Q_out - Q_in) with DVCM per-step volume cap."""
    volume = np.asarray(results["node_cavity_volume"][node_id], dtype=float)
    q_in_gpm = np.asarray(results["pipe_flow_gpm"][in_pipe_id], dtype=float)
    q_out_gpm = np.asarray(results["pipe_flow_gpm"][out_pipe_id], dtype=float)

    q_net_cfs = (q_out_gpm - q_in_gpm) * rthym_moc.GPM_TO_CFS
    max_step_delta_ft3 = 0.25 * junction_cavity_capacity_ft3()

    abs_errors: list[float] = []
    rel_errors: list[float] = []

    for i in range(1, len(volume)):
        delta_v = volume[i] - volume[i - 1]
        if abs(delta_v) <= 1e-12:
            continue

        expected = np.sign(delta_v) * min(abs(q_net_cfs[i]) * dt, max_step_delta_ft3)
        err = abs(delta_v - expected)
        abs_errors.append(err)
        denom = max(abs(expected), 1e-12)
        rel_errors.append(err / denom)

    if not abs_errors:
        return MassConservationMetrics(0.0, 0.0, 0, True)

    max_abs = float(max(abs_errors))
    max_rel = float(max(rel_errors))
    passed = max_abs <= atol_ft3 or max_rel <= rtol
    return MassConservationMetrics(max_abs, max_rel, len(abs_errors), passed)


@dataclass(frozen=True)
class CollapseSpikeMetrics:
    collapse_step: int
    v_before_ft3: float
    observed_dh_ft: float
    expected_dh_ft: float
    relative_error: float
    passed: bool


def evaluate_collapse_spike(
    results: dict,
    *,
    node_id: str = "J1",
    dt: float = DEFAULT_DT_S,
    p_vapor_psi: float = DEFAULT_P_VAPOR_PSI,
    diameter_in: float = DEFAULT_PIPE_DIAMETER_IN,
    length_ft: float = DEFAULT_PIPE_LENGTH_FT,
    peak_window_steps: int = 3,
    rtol: float = 0.15,
) -> CollapseSpikeMetrics:
    """Compare post-collapse head rise to discrete water-column collision estimate."""
    head = np.asarray(results["node_head"][node_id], dtype=float)
    volume = np.asarray(results["node_cavity_volume"][node_id], dtype=float)
    collapse_flag = np.asarray(results["node_cavity_collapse_flag"][node_id], dtype=int)

    collapse_steps = np.flatnonzero(collapse_flag)
    if collapse_steps.size == 0:
        raise AssertionError("No cavity collapse occurred in the transient.")

    step = int(collapse_steps[0])
    v_before = float(volume[step - 1])
    if v_before <= 0.0:
        raise AssertionError("Cavity volume before collapse must be positive.")

    area_ft2 = np.pi * ((diameter_in / 12.0) / 2.0) ** 2
    a_adj = adjusted_wave_speed_ft_s(length_ft=length_ft, dt=dt)
    g = rthym_moc.G_FT_S2
    h_vap = vapor_head_ft(p_vapor_psi)

    # Discrete collision head rise for symmetric columns (see docs/dvcm_timestep_guidance.md).
    expected_dh = a_adj * v_before / (g * area_ft2 * dt)

    end = min(len(head), step + peak_window_steps + 1)
    observed_peak = float(head[step:end].max())
    observed_dh = observed_peak - h_vap
    rel_err = abs(observed_dh - expected_dh) / max(expected_dh, 1e-9)

    return CollapseSpikeMetrics(
        collapse_step=step,
        v_before_ft3=v_before,
        observed_dh_ft=observed_dh,
        expected_dh_ft=expected_dh,
        relative_error=rel_err,
        passed=rel_err <= rtol,
    )
