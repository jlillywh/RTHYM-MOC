"""Parameterized closure-time benchmark for the Joukowsky criterion.

This benchmark converts the existing gradual-closure study into an automated
pytest module. It exercises the same reservoir-pipe-valve geometry at three
closure times so the benchmark suite explicitly covers a parameter sweep rather
than only single-point comparisons.

Network:
  R1 (150 ft) --[3000 ft, 12 in, HW 130]--> V1 --[one-cell stub]--> R2

Expected outcomes:
- rapid closure (`0.5 s`) should produce the full Joukowsky head rise
- nominal 3 s closure should still behave like rapid closure because the
  quadratic valve model concentrates restriction near the final stroke
- ultra-slow closure (`150 s`) should suppress the peak to about 50 % of the
  Joukowsky rise (Allievi slow-closure regime)
"""

import math

import numpy as np
import pytest

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


def _build_solver():
    solver = m.MOCSolver()

    r1 = m.NodeInput()
    r1.id = "R1"
    r1.type = "PressureBoundary"
    r1.head = H_RES_FT

    v1 = m.NodeInput()
    v1.id = "V1"
    v1.type = "Valve"
    v1.diameter = D_IN
    v1.current_setting = 100.0
    v1.head = H_DN_FT

    r2 = m.NodeInput()
    r2.id = "R2"
    r2.type = "PressureBoundary"
    r2.head = H_DN_FT

    p1 = m.PipeInput()
    p1.id = "P1"
    p1.from_node = "R1"
    p1.to_node = "V1"
    p1.length = L_FT
    p1.diameter = D_IN
    p1.roughness = HW_C
    p1.flow_gpm = Q0_GPM

    p2 = m.PipeInput()
    p2.id = "P2"
    p2.from_node = "V1"
    p2.to_node = "R2"
    p2.length = A_WAVE_FT * DT_S
    p2.diameter = D_IN
    p2.roughness = HW_C
    p2.flow_gpm = 0.0

    solver.add_node(r1)
    solver.add_node(v1)
    solver.add_node(r2)
    solver.add_pipe(p1)
    solver.add_pipe(p2)
    return solver


def _make_linear_schedule(closure_time_s, total_time_s):
    time_s = np.arange(0.0, total_time_s + DT_S, DT_S)
    pct_open = np.clip(100.0 * (1.0 - time_s / closure_time_s), 0.0, 100.0)
    return list(zip(time_s.tolist(), pct_open.tolist()))


@pytest.mark.parametrize(
    ("label", "closure_time_s", "total_time_s", "min_fraction", "max_fraction"),
    [
        ("rapid", 0.5, 3.0, 0.98, 1.03),
        ("three_second", 3.0, 6.0, 0.98, 1.03),
        ("ultra_slow", 150.0, 160.0, 0.47, 0.53),
    ],
)
def test_gradual_closure_benchmark_matches_expected_peak_regime(
    label,
    closure_time_s,
    total_time_s,
    min_fraction,
    max_fraction,
):
    """Closure-time sweep should reproduce the expected rapid- and slow-closure peak regimes."""
    solver = _build_solver()
    solver.set_valve_schedule("V1", _make_linear_schedule(closure_time_s, total_time_s))
    results = solver.run(total_time_s, DT_S, -14.0, DT_S)

    valve_head_ft = np.asarray(results["node_head"]["V1"])
    observed_dh_ft = float(np.max(valve_head_ft) - H_DN_FT)
    observed_fraction = observed_dh_ft / JOUKOWSKY_DH_FT

    assert min_fraction <= observed_fraction <= max_fraction, (
        f"{label}: expected peak-rise fraction in [{min_fraction:.2f}, {max_fraction:.2f}] of Joukowsky, "
        f"got {observed_fraction:.3f} (ΔH={observed_dh_ft:.2f} ft, Joukowsky={JOUKOWSKY_DH_FT:.2f} ft)"
    )