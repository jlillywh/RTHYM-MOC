"""
TSNet cross-engine benchmark — Joukowsky instant-closure test
=============================================================
Verifies that the C++/Python ``rthym_moc`` engine and the pure-Python
``TSNet`` library both reproduce the analytical Joukowsky surge for an
instant valve closure at the downstream end of a single-pipe network,
and that the two engines agree with each other within tight tolerances.

Test network
------------
  R1 (H = 150 ft) ──[P1: 3000 ft, 12 in, HW C=130]──► V1 (closed) ──[P2: stub]──► R2

Both engines are run with:
  * Wave speed  a  = 4000 ft/s
  * Initial flow    Q₀ = 500 GPM  →  V₀ = 1.418 ft/s
  * Instant valve closure at t = 0
  * No unsteady-friction correction (pure steady-friction MOC)

Analytical reference (Joukowsky equation)
  ΔH = a · V₀ / g
  First-step peak at valve ≈ H_DN + ΔH = 324.18 ft
  Theoretical maximum     ≈ H_RES + ΔH = 326.28 ft  (after wave sweeps full HGL)

Skip behaviour
  The entire module is skipped when TSNet is not installed.
"""

import math
import os
import tempfile

import numpy as np
import pytest

tsnet = pytest.importorskip("tsnet", reason="TSNet not installed")

import rthym_moc as m  # noqa: E402  (after importorskip guard)

# ── Unit conversions ─────────────────────────────────────────────────────────
_FT_TO_M    = 0.3048
_GPM_TO_CFS = 0.002228
_G_SI       = 9.81   # m/s²

# ── Network / simulation parameters ─────────────────────────────────────────
_H_RES_FT  = 150.0        # upstream reservoir head [ft]
_L_FT      = 3000.0       # pipe length [ft]
_D_IN      = 12.0         # pipe inside diameter [in]
_HW_C      = 130.0        # Hazen-Williams roughness
_Q0_GPM    = 500.0        # initial steady-state flow [GPM]
_A_FPS     = 4000.0       # wave speed [ft/s]
_TOTAL_S   = 3.0          # simulation duration [s]
_DT_S      = 0.01         # time step [s]

# ── Derived quantities ───────────────────────────────────────────────────────
_D_FT      = _D_IN / 12.0
_A_PIPE    = math.pi * (_D_FT / 2.0) ** 2    # cross-sectional area [ft²]
_V0_FPS    = _Q0_GPM * _GPM_TO_CFS / _A_PIPE # initial velocity [ft/s]

# SI equivalents used by TSNet
_H_RES_M   = _H_RES_FT * _FT_TO_M
_L_M       = _L_FT     * _FT_TO_M
_D_MM      = _D_IN     * 25.4
_D_M       = _D_FT     * _FT_TO_M
_A_M       = _A_FPS    * _FT_TO_M
_V0_M      = _V0_FPS   * _FT_TO_M
_Q0_M3S    = _Q0_GPM   * 6.309e-5

# Steady-state friction loss (Hazen-Williams SI: Hf = 10.67 L Q^1.852 / (C^1.852 D^4.87))
_Hf_M      = (10.67 * _L_M * _Q0_M3S ** 1.852
              / (_HW_C ** 1.852 * _D_M ** 4.87))
_H_DN_FT   = (_H_RES_M - _Hf_M) / _FT_TO_M   # downstream head (at valve, pre-closure) [ft]
_H_DN_M    = _H_DN_FT * _FT_TO_M

# Joukowsky analytical peaks [ft]
_DH_FPS    = _A_FPS * _V0_FPS / 32.2           # Joukowsky ΔH in US units
_H_JOUK_FT = _H_DN_FT + _DH_FPS               # first-step: baseline = H_DN
_H_MAX_FT  = _H_RES_FT + _DH_FPS              # theoretical max: wave sweeps full HGL

# Test tolerances
_TOL_ANALYTICAL_FT = 1.0    # each engine vs analytical Joukowsky [ft]
_TOL_RMS_FT        = 0.5    # rthym_moc vs TSNet RMS over 0–1.5 s [ft]
_COMPARE_WINDOW_S  = 1.5    # wave-cycle comparison window [s]


# ── Shared fixtures ───────────────────────────────────────────────────────────

def _run_rthym() -> np.ndarray:
    """Return rthym_moc valve-node head time series [ft] for the benchmark."""
    solver = m.MOCSolver()

    r1 = m.NodeInput(); r1.id = "R1"; r1.type = "PressureBoundary"; r1.head = _H_RES_FT
    r2 = m.NodeInput(); r2.id = "R2"; r2.type = "PressureBoundary"; r2.head = _H_DN_FT

    v1 = m.NodeInput()
    v1.id              = "V1"
    v1.type            = "Valve"
    v1.diameter        = _D_IN
    v1.current_setting = 0.0       # fully closed at t=0
    v1.head            = _H_DN_FT

    p1 = m.PipeInput()
    p1.id = "P1"; p1.from_node = "R1"; p1.to_node = "V1"
    p1.length   = _L_FT;  p1.diameter = _D_IN;  p1.roughness = _HW_C
    p1.flow_gpm = _Q0_GPM

    # One-segment stub pipe: ensures V1 has a downstream connection
    p2 = m.PipeInput()
    p2.id = "P2"; p2.from_node = "V1"; p2.to_node = "R2"
    p2.length   = _A_FPS * _DT_S  # exactly one MOC cell
    p2.diameter = _D_IN;  p2.roughness = _HW_C;  p2.flow_gpm = 0.0

    solver.add_node(r1); solver.add_node(v1); solver.add_node(r2)
    solver.add_pipe(p1); solver.add_pipe(p2)

    # usf_tau = _DT_S → alpha = dt/tau = 1 → V_bar tracks V instantly
    # → Brunone k_u * (V – V_bar) = 0  ⟹  pure steady-friction MOC
    results = solver.run(_TOTAL_S, _DT_S, -14.0, _DT_S)
    return np.array(results["node_head"]["V1"])


def _run_tsnet():
    """Return (time_axis [s], J1 head [m]) from TSNet for the same benchmark."""
    inp = f"""[TITLE]
Joukowsky Benchmark

[OPTIONS]
 Units                LPS
 Headloss             H-W
 Trials               40
 Accuracy             0.001
 Unbalanced           Continue 10
 Quality              None

[JUNCTIONS]
;ID    Elev   Demand  Pattern
 J1   0.000   0.000   ;

[RESERVOIRS]
;ID   Head         Pattern
 R1   {_H_RES_M:.6f}   ;
 R2   {_H_DN_M:.6f}   ;

[PIPES]
;ID  Node1  Node2  Length      Diam      Rough  MLoss  Status
 P1  R1     J1     {_L_M:.3f}  {_D_MM:.3f}  {_HW_C:.0f}    0      Open

[VALVES]
;ID  Node1  Node2  Diam      Type  Setting  MLoss
 V1  J1     R2     {_D_MM:.3f}  TCV   0.001    0

[REPORT]
 Status  No
 Summary No

[END]
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".inp", delete=False) as f:
        f.write(inp)
        inp_path = f.name
    try:
        tm = tsnet.network.TransientModel(inp_path)
    finally:
        os.unlink(inp_path)

    tm.set_wavespeed(_A_M)
    tm.set_time(_TOTAL_S, _DT_S)

    dt_ts = tm.time_step
    tm.valve_closure("V1", [dt_ts, 0.0, 0.0, 1])  # instant (one time-step) closure

    tm = tsnet.simulation.Initializer(tm, 0.0, "DD")
    tm = tsnet.simulation.MOCSimulator(tm)

    t_axis = np.array(tm.simulation_timestamps)
    H_J1_m = np.array(tm.get_node("J1")._head)
    return t_axis, H_J1_m


# Cache results so the solvers run only once across all tests in this module
_rthym_head: np.ndarray | None = None
_tsnet_t: np.ndarray | None = None
_tsnet_H: np.ndarray | None = None


def _get_results():
    global _rthym_head, _tsnet_t, _tsnet_H
    if _rthym_head is None:
        _rthym_head = _run_rthym()
        _tsnet_t, _tsnet_H = _run_tsnet()
    return _rthym_head, _tsnet_t, _tsnet_H


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_rthym_joukowsky_first_step():
    """rthym_moc first-step peak is within ±1 ft of the Joukowsky analytical value."""
    h, _, _ = _get_results()
    assert abs(float(h[0]) - _H_JOUK_FT) <= _TOL_ANALYTICAL_FT, (
        f"rthym first-step {h[0]:.3f} ft vs analytical {_H_JOUK_FT:.3f} ft "
        f"(tol ±{_TOL_ANALYTICAL_FT} ft)"
    )


def test_rthym_transient_max():
    """rthym_moc transient maximum head is within ±1 ft of the theoretical maximum."""
    h, _, _ = _get_results()
    assert abs(float(h.max()) - _H_MAX_FT) <= _TOL_ANALYTICAL_FT, (
        f"rthym max {h.max():.3f} ft vs theoretical {_H_MAX_FT:.3f} ft "
        f"(tol ±{_TOL_ANALYTICAL_FT} ft)"
    )


def test_tsnet_joukowsky_first_step():
    """TSNet first-step peak is within ±1 ft of the Joukowsky analytical value."""
    _, t_ts, H_ts = _get_results()
    step1_ft = float(H_ts[1]) / _FT_TO_M   # index 0 = initial, 1 = first transient step
    assert abs(step1_ft - _H_JOUK_FT) <= _TOL_ANALYTICAL_FT, (
        f"TSNet first-step {step1_ft:.3f} ft vs analytical {_H_JOUK_FT:.3f} ft "
        f"(tol ±{_TOL_ANALYTICAL_FT} ft)"
    )


def test_tsnet_transient_max():
    """TSNet transient maximum head is within ±1 ft of the theoretical maximum."""
    _, _, H_ts = _get_results()
    max_ft = float(H_ts.max()) / _FT_TO_M
    assert abs(max_ft - _H_MAX_FT) <= _TOL_ANALYTICAL_FT, (
        f"TSNet max {max_ft:.3f} ft vs theoretical {_H_MAX_FT:.3f} ft "
        f"(tol ±{_TOL_ANALYTICAL_FT} ft)"
    )


def test_cross_engine_rms():
    """rthym_moc and TSNet head time-series RMS ≤ 0.5 ft over the first wave cycle."""
    h_r, t_ts, H_ts = _get_results()
    t_r    = np.arange(1, len(h_r) + 1) * _DT_S
    H_ts_ft = np.interp(t_r, t_ts, H_ts) / _FT_TO_M   # interpolate TSNet onto rthym grid
    mask    = t_r <= _COMPARE_WINDOW_S
    rms     = float(np.sqrt(np.mean((h_r[mask] - H_ts_ft[mask]) ** 2)))
    assert rms <= _TOL_RMS_FT, (
        f"Cross-engine RMS over 0–{_COMPARE_WINDOW_S} s: {rms:.3f} ft "
        f"(tol ≤ {_TOL_RMS_FT} ft)"
    )


if __name__ == "__main__":
    h_r, t_ts, H_ts = _get_results()

    step1_r  = float(h_r[0])
    max_r    = float(h_r.max())
    step1_ts = float(H_ts[1]) / _FT_TO_M
    max_ts   = float(H_ts.max()) / _FT_TO_M

    t_r     = np.arange(1, len(h_r) + 1) * _DT_S
    H_ts_ft = np.interp(t_r, t_ts, H_ts) / _FT_TO_M
    mask    = t_r <= _COMPARE_WINDOW_S
    rms     = float(np.sqrt(np.mean((h_r[mask] - H_ts_ft[mask]) ** 2)))

    print("=" * 60)
    print("  Joukowsky Benchmark — rthym_moc vs TSNet")
    print("=" * 60)
    print(f"  {'Quantity':<30}  {'Analytical':>10}  {'rthym_moc':>10}  {'TSNet':>10}")
    print(f"  {'-'*30}  {'-'*10}  {'-'*10}  {'-'*10}")
    print(f"  {'First-step peak (ft)':<30}  {_H_JOUK_FT:>10.3f}  {step1_r:>10.3f}  {step1_ts:>10.3f}")
    print(f"  {'Transient max (ft)':<30}  {_H_MAX_FT:>10.3f}  {max_r:>10.3f}  {max_ts:>10.3f}")
    print(f"  {'Cross-engine RMS (ft)':<30}  {'—':>10}  {'':>10}  {rms:>10.3f}")
    print("=" * 60)
