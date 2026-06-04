"""Gradual valve-closure Joukowsky / Allievi sweep (tests + notebook)."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import rthym_moc as m

H_RES_FT = 150.0
L_FT = 3000.0
D_IN = 12.0
HW_C = 130.0
Q0_GPM = 500.0
A_WAVE_FT = 4000.0
DT_S = 0.01

D_FT = D_IN / 12.0
A_PIPE = math.pi * (D_FT / 2.0) ** 2
V0_FT = Q0_GPM * 0.002228 / A_PIPE
JOUKOWSKY_DH_FT = A_WAVE_FT * V0_FT / 32.2

L_M = L_FT * 0.3048
D_M = D_FT * 0.3048
Q0_M3S = Q0_GPM * 6.309e-5
H_RES_M = H_RES_FT * 0.3048
Hf_M = 10.67 * L_M * Q0_M3S**1.852 / (HW_C**1.852 * D_M**4.87)
H_DN_FT = (H_RES_M - Hf_M) / 0.3048

T_WAVE_S = 2.0 * L_FT / A_WAVE_FT

CLOSURE_CASES: tuple[tuple[str, float, float, float, float], ...] = (
    ("rapid", 0.5, 3.0, 0.98, 1.03),
    ("three_second", 3.0, 6.0, 0.98, 1.03),
    ("ultra_slow", 150.0, 160.0, 0.47, 0.53),
)


def build_solver() -> m.MOCSolver:
    solver = m.MOCSolver()
    r1 = m.NodeInput()
    r1.id, r1.type, r1.head = "R1", "PressureBoundary", H_RES_FT
    v1 = m.NodeInput()
    v1.id, v1.type = "V1", "Valve"
    v1.diameter, v1.current_setting, v1.head = D_IN, 100.0, H_DN_FT
    r2 = m.NodeInput()
    r2.id, r2.type, r2.head = "R2", "PressureBoundary", H_DN_FT
    p1 = m.PipeInput()
    p1.id, p1.from_node, p1.to_node = "P1", "R1", "V1"
    p1.length, p1.diameter, p1.roughness, p1.flow_gpm = L_FT, D_IN, HW_C, Q0_GPM
    p2 = m.PipeInput()
    p2.id, p2.from_node, p2.to_node = "P2", "V1", "R2"
    p2.length, p2.diameter, p2.roughness, p2.flow_gpm = A_WAVE_FT * DT_S, D_IN, HW_C, 0.0
    solver.add_node(r1)
    solver.add_node(v1)
    solver.add_node(r2)
    solver.add_pipe(p1)
    solver.add_pipe(p2)
    return solver


def linear_valve_schedule(closure_time_s: float, total_time_s: float) -> list[tuple[float, float]]:
    time_s = np.arange(0.0, total_time_s + DT_S, DT_S)
    pct_open = np.clip(100.0 * (1.0 - time_s / closure_time_s), 0.0, 100.0)
    return list(zip(time_s.tolist(), pct_open.tolist()))


@dataclass(frozen=True)
class ClosureCaseResult:
    label: str
    closure_time_s: float
    total_time_s: float
    min_fraction: float
    max_fraction: float
    observed_dh_ft: float
    observed_fraction: float
    passed: bool
    time_s: np.ndarray
    valve_head_ft: np.ndarray


def run_closure_case(label: str, closure_time_s: float, total_time_s: float, min_fraction: float, max_fraction: float) -> ClosureCaseResult:
    solver = build_solver()
    solver.set_valve_schedule("V1", linear_valve_schedule(closure_time_s, total_time_s))
    results = solver.run(total_time_s, DT_S, -14.0, DT_S)
    valve_head_ft = np.asarray(results["node_head"]["V1"], dtype=float)
    observed_dh_ft = float(np.max(valve_head_ft) - H_DN_FT)
    observed_fraction = observed_dh_ft / JOUKOWSKY_DH_FT
    passed = min_fraction <= observed_fraction <= max_fraction
    return ClosureCaseResult(
        label=label,
        closure_time_s=closure_time_s,
        total_time_s=total_time_s,
        min_fraction=min_fraction,
        max_fraction=max_fraction,
        observed_dh_ft=observed_dh_ft,
        observed_fraction=observed_fraction,
        passed=passed,
        time_s=np.asarray(results["time"], dtype=float),
        valve_head_ft=valve_head_ft,
    )


def run_all_closure_cases() -> list[ClosureCaseResult]:
    return [run_closure_case(*args) for args in CLOSURE_CASES]
