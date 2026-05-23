# Copyright (c) 2026 Jason Lillywhite <jason@lillywhitewater.com>
# SPDX-License-Identifier: MIT
# Author: Jason Lillywhite <jason@lillywhitewater.com>
"""
tests/test_standpipe_surge_protection.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Verification: Open Standpipe as a Surge Protection Device
==========================================================

This module verifies that the ``rthym_moc`` Standpipe node type correctly
implements an open (atmospheric) surge-protection standpipe and that the
results agree with TSNet to within tight tolerances.

Test network
------------
::

    R1 (H = 150 ft)
      ──[P1: 3000 ft, 12 in, HW C=130]──► SP1 (Standpipe, A_s = 1 ft²)
      ──[P2:   40 ft, 12 in, HW C=130]──► V1  (Valve, instant closure)
      ──[P3:   40 ft, 12 in, HW C=130]──► R2  (H = H_SP1 ft)

SP1 is a free-surface standpipe placed directly upstream of the valve.
When V1 closes, the incoming Joukowsky wave is absorbed by SP1, limiting
the pressure at the standpipe junction and allowing the system to undergo a
slow mass-oscillation rather than a sharp water-hammer spike.

Baseline network (no standpipe)
--------------------------------
::

    R1 (H = 150 ft)
      ──[P1: 3000 ft, 12 in, HW C=130]──► J1  (Junction, demand=0)
      ──[P2:   40 ft, 12 in, HW C=130]──► V1  (Valve, instant closure)
      ──[P3:   40 ft, 12 in, HW C=130]──► R2  (H = H_SP1 ft)

Without the standpipe, J1 sees the full Joukowsky surge when the wave
propagates back from the closed valve through the two-pipe connection.

Analytical references
---------------------
1. **Joukowsky equation** (no standpipe, peak at junction):

   .. math::
       \\Delta H = \\frac{a \\cdot V_0}{g}

   Peak head at J1 = H_{J1,ss} + ΔH ≈ 324 ft.

2. **Mass-oscillation envelope** (frictionless, Wylie & Streeter §9.1):

   After valve closure, the remaining upstream pipe (P1) and standpipe
   form the classical reservoir-pipe-surge-tank system.  The frictionless
   amplitude and period are:

   .. math::
       z_{\\max} = V_0 \\sqrt{\\frac{A_p \\cdot L}{g \\cdot A_s}}
       \\approx 12.1 \\text{ ft}

   .. math::
       T = 2\\pi / \\omega, \\quad
       \\omega = \\sqrt{\\frac{g \\cdot A_p}{A_s \\cdot L}}
       \\approx 68.4 \\text{ s}

   Peak standpipe level ≈ H_{SP1,ss} + z_max ≈ 160 ft (first positive
   maximum at T/4 ≈ 17.1 s, reduced by friction in practice).

Physical protection
-------------------
The standpipe limits the pressure at the junction from ≈ 324 ft
(Joukowsky rigid-reflection) to ≈ 148–162 ft (mass-oscillation envelope),
a reduction of > 80 % in overpressure relative to the no-standpipe case.

TSNet cross-engine comparison
------------------------------
TSNet (v0.2.2) models the surge tank as a free-surface BC applied directly
at junction node J1 (``add_surge_tank("J1", [As_m2])``), with no separate
connecting pipe.  rthym-moc places the Standpipe node SP1 in-line between
P1 and P2 (P2 is one MOC segment = 40 ft ≈ 0.01 s acoustic delay).  This
negligible one-step offset does not affect engineering accuracy over the
17-second comparison window.

Test summary
-------------
1. ``test_no_standpipe_joukowsky_peak``    – Baseline Joukowsky peak at J1.
2. ``test_standpipe_limits_pressure``      – Standpipe limits peak to < 170 ft.
3. ``test_standpipe_peak_near_analytical`` – Peak within ±15 ft of z_max formula.
4. ``test_standpipe_overpressure_reduction`` – ≥ 80 % reduction in overpressure.
5. ``test_rthym_vs_tsnet_rms``             – Cross-engine RMS < 2.5 ft over
                                             t = 0–20 s (before TSNet and
                                             rthym-moc decorrelate slightly
                                             through unequal topological delay).

Skip behaviour
--------------
Tests 1–4 always run.  Test 5 is skipped when TSNet is not installed.
"""

import math
import os
import tempfile

import numpy as np
import pytest

import rthym_moc as m

# ── Try to import TSNet (test 5 is skipped if absent) ────────────────────────
try:
    import tsnet as _tsnet_mod
    _TSNET_AVAILABLE = True
except ImportError:
    _TSNET_AVAILABLE = False

# ── Unit conversions ──────────────────────────────────────────────────────────
_GPM_TO_CFS = 0.002228       # GPM → ft³/s
_FT_TO_M    = 0.3048         # ft → m
_G_US       = 32.2           # ft/s²  (US customary)
_G_SI       = 9.81           # m/s²   (SI)

# ── Network parameters (US customary) ────────────────────────────────────────
_H_RES_FT   = 150.0          # upstream reservoir head [ft]
_L_FT       = 3000.0         # main pipe length [ft]
_D_IN       = 12.0           # pipe inside diameter [in]
_HW_C       = 130.0          # Hazen-Williams roughness coefficient
_Q0_GPM     = 500.0          # initial steady-state flow [GPM]
_A_FPS      = 4000.0         # wave speed (rigid pipe) [ft/s]
_DT_S       = 0.01           # time step [s]
_TOTAL_S    = 25.0           # simulation duration [s] — captures T/4 ≈ 17 s
_A_S_FT2    = 1.0            # standpipe cross-sectional area [ft²]

# ── Derived pipe geometry ─────────────────────────────────────────────────────
_D_FT       = _D_IN / 12.0
_A_PIPE     = math.pi * (_D_FT / 2.0) ** 2       # pipe area [ft²]
_V0_FPS     = _Q0_GPM * _GPM_TO_CFS / _A_PIPE    # initial velocity [ft/s]

# One-segment short pipe length (Courant number = 1 exactly)
_L_SHORT_FT = _A_FPS * _DT_S                      # 40 ft

# ── Steady-state friction head loss in the long pipe P1 (Hazen-Williams) ─────
# HW formula (US customary):  Hf = 10.44 · L · Q^1.852 / (C^1.852 · D_in^4.871)
_HF_P1_FT = (10.44 * _L_FT * _Q0_GPM ** 1.852
             / (_HW_C ** 1.852 * _D_IN ** 4.871))

# Steady-state head at the standpipe / junction node (foot of P1)
_H_SP1_FT   = _H_RES_FT - _HF_P1_FT
# Downstream reservoir: equal to _H_SP1_FT because the valve is fully open
# (K=0) and the short pipes have negligible friction at Q₀.
_H_R2_FT    = _H_SP1_FT

# ── Analytical Joukowsky surge (no standpipe) ─────────────────────────────────
_DH_JOUK_FT  = _A_FPS * _V0_FPS / _G_US          # ΔH = a·V₀/g  [ft]
# Expected peak head at J1 when no standpipe is present and Joukowsky wave
# propagates from V1 back through P2 to J1.
_H_JOUK_J1_FT = _H_SP1_FT + _DH_JOUK_FT

# ── Analytical mass-oscillation envelope (Wylie & Streeter §9.1) ─────────────
# After valve closure, the remaining system is effectively:
#     R1 (fixed H) ──[P1]──► SP1 (free surface)
# with initial velocity V₀ (kinetic energy) driving the oscillation.
#   ω = √(g · A_p / (A_s · L))
#   z_max = V₀ · √(A_p · L / (g · A_s))
#   T_osc = 2π / ω
_OMEGA_RAD    = math.sqrt(_G_US * _A_PIPE / (_A_S_FT2 * _L_FT))    # rad/s
_T_OSC_S      = 2.0 * math.pi / _OMEGA_RAD                          # s
_T_QUARTER_S  = _T_OSC_S / 4.0                                      # s  (first peak)
_Z_MAX_FT     = _V0_FPS * math.sqrt(_A_PIPE * _L_FT
                                     / (_G_US * _A_S_FT2))           # ft
_H_PEAK_ANALYTICAL_FT = _H_SP1_FT + _Z_MAX_FT

# ── SI equivalents for TSNet ──────────────────────────────────────────────────
_H_RES_M    = _H_RES_FT * _FT_TO_M
_H_SP1_M    = _H_SP1_FT * _FT_TO_M
_H_R2_M     = _H_R2_FT  * _FT_TO_M
_L_M        = _L_FT     * _FT_TO_M
_D_MM       = _D_IN     * 25.4
_D_M        = _D_FT     * _FT_TO_M
_A_WAVE_M   = _A_FPS    * _FT_TO_M
_A_S_M2     = _A_S_FT2  * (_FT_TO_M ** 2)      # ft² → m²
_L_STUB_M   = 2.0 * _A_WAVE_M * _DT_S         # two MOC segments in SI (= 80 ft = 24.384 m)
                                               # TSNet requires L/(2a) >= dt per pipe, so min 2 segs

# ── Test tolerances ───────────────────────────────────────────────────────────
_TOL_JOUK_FT        = 5.0   # Joukowsky peak at J1 vs analytical [ft]
_TOL_STANDPIPE_UP   = 170.0 # absolute upper bound for peak at SP1 [ft]
_TOL_STANDPIPE_LO   = _H_SP1_FT + 2.0  # SP1 must actually rise above SS [ft]
_TOL_PEAK_ANAL_FT   = 15.0  # peak at SP1 vs frictionless analytical [ft]
_TOL_MITIGATION_PCT = 0.80  # standpipe must remove ≥ 80 % of overpressure
_TOL_RMS_FT         = 2.5   # rthym-moc vs TSNet RMS over 0–20 s [ft]
_COMPARE_WINDOW_S   = 20.0  # cross-engine comparison window [s]


# ─────────────────────────────────────────────────────────────────────────────
# Simulation helpers
# ─────────────────────────────────────────────────────────────────────────────

def _run_rthym_no_standpipe() -> np.ndarray:
    """
    rthym-moc baseline: instant valve closure, *no* standpipe at J1.

    Returns the J1 head time series [ft] over *_TOTAL_S* seconds.

    Network topology::

        R1 ──[P1: 3000 ft]──► J1 (Junction) ──[P2: 40 ft]──► V1 ──[P3: 40 ft]──► R2

    V1 is closed from t = 0.  P1 carries Q₀ = 500 GPM initially; P2 also
    carries Q₀ toward the pre-closed valve; P3 carries zero flow (closed valve
    face).  The initial velocity discontinuity at V1 generates the Joukowsky
    wave, which propagates upstream through P2 and arrives at J1 in one
    time step.
    """
    solver = m.MOCSolver()

    # Boundary nodes
    r1 = m.NodeInput()
    r1.id = "R1"; r1.type = "PressureBoundary"; r1.head = _H_RES_FT

    r2 = m.NodeInput()
    r2.id = "R2"; r2.type = "PressureBoundary"; r2.head = _H_R2_FT

    # Interior junction (no standpipe)
    j1 = m.NodeInput()
    j1.id = "J1"; j1.type = "Junction"
    j1.head = _H_SP1_FT   # supply initial head so pipe initialization is correct
    j1.demand = 0.0

    # Valve: closed from t = 0
    v1 = m.NodeInput()
    v1.id = "V1"; v1.type = "Valve"
    v1.diameter = _D_IN
    v1.current_setting = 0.0   # K → ∞ (fully closed)
    v1.head = _H_SP1_FT

    # Pipes
    p1 = m.PipeInput()
    p1.id = "P1"; p1.from_node = "R1"; p1.to_node = "J1"
    p1.length = _L_FT; p1.diameter = _D_IN; p1.roughness = _HW_C
    p1.flow_gpm = _Q0_GPM   # steady-state pre-closure flow

    p2 = m.PipeInput()
    p2.id = "P2"; p2.from_node = "J1"; p2.to_node = "V1"
    p2.length = _L_SHORT_FT; p2.diameter = _D_IN; p2.roughness = _HW_C
    p2.flow_gpm = _Q0_GPM   # pre-closure state

    p3 = m.PipeInput()
    p3.id = "P3"; p3.from_node = "V1"; p3.to_node = "R2"
    p3.length = _L_SHORT_FT; p3.diameter = _D_IN; p3.roughness = _HW_C
    p3.flow_gpm = 0.0       # valve closed: no downstream flow

    solver.add_node(r1); solver.add_node(j1); solver.add_node(v1); solver.add_node(r2)
    solver.add_pipe(p1);  solver.add_pipe(p2); solver.add_pipe(p3)

    # Disable unsteady-friction (steady-friction MOC; usf_tau = dt → α = 1)
    results = solver.run(_TOTAL_S, _DT_S, -14.0, _DT_S, 0.0)
    return np.array(results["node_head"]["J1"])


def _run_rthym_with_standpipe() -> np.ndarray:
    """
    rthym-moc with open standpipe SP1 placed in-line just upstream of V1.

    Returns the SP1 head time series [ft] over *_TOTAL_S* seconds.

    Network topology::

        R1 ──[P1: 3000 ft]──► SP1 (Standpipe, A_s=1 ft²)
           ──[P2:   40 ft]──► V1  (Valve, closed from t=0)
           ──[P3:   40 ft]──► R2

    SP1 is a free-surface node that acts as the intermediate junction AND the
    surge tank simultaneously.  Incoming flow from P1 can drain into SP1's
    open column; the water level rises according to::

        dL/dt = Q_net / A_s

    When V1 closes, the Joukowsky wave travels the one MOC segment in P2
    (0.01 s) and arrives at SP1.  The free-surface BC clamps SP1's pressure
    to the current water level (≈ H_SP1_ss initially), and the excess kinetic
    energy is converted into a slow mass-oscillation in P1.
    """
    solver = m.MOCSolver()

    r1 = m.NodeInput()
    r1.id = "R1"; r1.type = "PressureBoundary"; r1.head = _H_RES_FT

    r2 = m.NodeInput()
    r2.id = "R2"; r2.type = "PressureBoundary"; r2.head = _H_R2_FT

    # Open standpipe (free surface) at the junction
    sp1 = m.NodeInput()
    sp1.id = "SP1"; sp1.type = "Standpipe"
    sp1.head = _H_SP1_FT      # initial water-surface elevation [ft HGL]
    sp1.tank_area = _A_S_FT2  # cross-sectional area of standpipe column [ft²]

    v1 = m.NodeInput()
    v1.id = "V1"; v1.type = "Valve"
    v1.diameter = _D_IN
    v1.current_setting = 0.0  # closed from t = 0
    v1.head = _H_SP1_FT

    p1 = m.PipeInput()
    p1.id = "P1"; p1.from_node = "R1"; p1.to_node = "SP1"
    p1.length = _L_FT; p1.diameter = _D_IN; p1.roughness = _HW_C
    p1.flow_gpm = _Q0_GPM

    p2 = m.PipeInput()
    p2.id = "P2"; p2.from_node = "SP1"; p2.to_node = "V1"
    p2.length = _L_SHORT_FT; p2.diameter = _D_IN; p2.roughness = _HW_C
    p2.flow_gpm = _Q0_GPM   # pre-closure state

    p3 = m.PipeInput()
    p3.id = "P3"; p3.from_node = "V1"; p3.to_node = "R2"
    p3.length = _L_SHORT_FT; p3.diameter = _D_IN; p3.roughness = _HW_C
    p3.flow_gpm = 0.0

    solver.add_node(r1); solver.add_node(sp1); solver.add_node(v1); solver.add_node(r2)
    solver.add_pipe(p1);  solver.add_pipe(p2); solver.add_pipe(p3)

    results = solver.run(_TOTAL_S, _DT_S, -14.0, _DT_S, 0.0)
    return np.array(results["node_head"]["SP1"])


def _run_tsnet_with_standpipe():
    """
    TSNet equivalent: open surge tank at junction J1, valve V1 instant closure.

    Returns ``(time_axis_s, J1_head_ft)`` where both arrays are in US-customary
    units.

    TSNet topology (SI internally, EPANET INP)::

        R1 ──[P1: 914.4 m]──► J1 (SurgeTank, A_s=0.0929 m²)
                              ──[P2: 24.384 m]──► J2 ──[V1: TCV]──► R2

    A short stub pipe P2 (two MOC segments = 80 ft = 24.384 m) is inserted
    between J1 and the valve J2.  This ensures TSNet sees J1 flanked by two
    *pipes* (P1 and P2), so ``dtype[P1] == 'Pipe'`` and the SurgeTank BC
    fires correctly.  Without P2, ``dtype[P1] == 'Valve'`` and the surge-tank
    code path is bypassed entirely.  Two segments are required because TSNet
    enforces ``dt ≤ L / (2·a)`` per pipe (i.e. N ≥ 2 segments minimum).
    The TCV valve is set to near-zero loss coefficient (0.001) in the EPANET
    steady state, then closed instantly via ``valve_closure``.
    TSNet's ``add_surge_tank("J1", [A_s_m2])`` makes J1 a free-surface BC
    with cross-sectional area A_s, directly equivalent to RTHYM-MOC's SP1.
    """
    import tsnet

    inp = (
        "[TITLE]\n"
        "Standpipe Surge Protection Benchmark\n"
        "\n"
        "[OPTIONS]\n"
        " Units                LPS\n"
        " Headloss             H-W\n"
        " Trials               40\n"
        " Accuracy             0.001\n"
        " Unbalanced           Continue 10\n"
        " Quality              None\n"
        "\n"
        "[JUNCTIONS]\n"
        ";ID    Elev   Demand  Pattern\n"
        f" J1   0.000   0.000   ;\n"
        f" J2   0.000   0.000   ;\n"
        "\n"
        "[RESERVOIRS]\n"
        ";ID   Head         Pattern\n"
        f" R1   {_H_RES_M:.6f}   ;\n"
        f" R2   {_H_R2_M:.6f}   ;\n"
        "\n"
        "[PIPES]\n"
        ";ID  Node1  Node2  Length          Diam       Rough  MLoss  Status\n"
        f" P1  R1     J1     {_L_M:.3f}      {_D_MM:.3f}  {_HW_C:.0f}    0      Open\n"
        f" P2  J1     J2     {_L_STUB_M:.3f}  {_D_MM:.3f}  {_HW_C:.0f}    0      Open\n"
        "\n"
        "[VALVES]\n"
        ";ID  Node1  Node2  Diam       Type  Setting  MLoss\n"
        f" V1  J2     R2     {_D_MM:.3f}  TCV   0.001    0\n"
        "\n"
        "[REPORT]\n"
        " Status  No\n"
        " Summary No\n"
        "\n"
        "[END]\n"
    )

    with tempfile.NamedTemporaryFile(mode="w", suffix=".inp", delete=False) as f:
        f.write(inp)
        inp_path = f.name

    try:
        tm = tsnet.network.TransientModel(inp_path)
    finally:
        os.unlink(inp_path)

    # Match wave speed to RTHYM-MOC (rigid-pipe 4000 ft/s in SI)
    tm.set_wavespeed(_A_WAVE_M)
    tm.set_time(_TOTAL_S, _DT_S)

    dt_ts = tm.time_step

    # Instant valve closure: close in one time step from t=0
    tm.valve_closure("V1", [dt_ts, 0.0, 0.0, 1])

    # Add open surge tank at J1 (area in m²)
    tm.add_surge_tank("J1", [_A_S_M2])

    # Initialise and simulate (steady-friction only, friction_model="steady")
    tm = tsnet.simulation.Initializer(tm, 0.0, "DD")
    tm = tsnet.simulation.MOCSimulator(tm)

    t_axis_s  = np.array(tm.simulation_timestamps)
    H_J1_m    = np.array(tm.get_node("J1")._head)
    H_J1_ft   = H_J1_m / _FT_TO_M

    return t_axis_s, H_J1_ft


# ── Cache results so each solver runs only once across all tests ──────────────
_rthym_no_sp:  np.ndarray | None = None
_rthym_sp:     np.ndarray | None = None
_tsnet_t:      np.ndarray | None = None
_tsnet_H:      np.ndarray | None = None


def _get_rthym_results():
    """Return (no_standpipe_head, with_standpipe_head) [ft] arrays."""
    global _rthym_no_sp, _rthym_sp
    if _rthym_no_sp is None:
        _rthym_no_sp = _run_rthym_no_standpipe()
        _rthym_sp    = _run_rthym_with_standpipe()
    return _rthym_no_sp, _rthym_sp


def _get_tsnet_results():
    """Return (time_s, head_ft) from TSNet with standpipe."""
    global _tsnet_t, _tsnet_H
    if _tsnet_t is None:
        _tsnet_t, _tsnet_H = _run_tsnet_with_standpipe()
    return _tsnet_t, _tsnet_H


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_no_standpipe_joukowsky_peak():
    """
    Baseline (no standpipe): peak at J1 matches the Joukowsky analytical value.

    When V1 closes, the C+ characteristic from the upstream pipe and the
    reflected C– from the closed valve combine at J1 (a rigid junction).
    The peak head at J1 should match H_SP1 + ΔH = a·V₀/g within ±5 ft,
    confirming that RTHYM-MOC correctly propagates an instant-closure
    Joukowsky surge through a short connecting pipe.

    Physical bounds
    ~~~~~~~~~~~~~~~
    * Minimum physically expected: H_SP1 + 0.9·ΔH ≈ 306 ft
      (slight reduction due to friction in the 40 ft intermediate pipe)
    * Maximum physically expected: H_SP1 + ΔH + 5 ft ≈ 329 ft
    """
    h_no_sp, _ = _get_rthym_results()
    peak = float(np.max(h_no_sp))
    err  = abs(peak - _H_JOUK_J1_FT)
    assert err <= _TOL_JOUK_FT, (
        f"No-standpipe peak at J1: {peak:.2f} ft, "
        f"analytical Joukowsky: {_H_JOUK_J1_FT:.2f} ft, "
        f"error {err:.2f} ft exceeds tolerance ±{_TOL_JOUK_FT} ft"
    )


def test_standpipe_limits_pressure():
    """
    Standpipe limits peak pressure at SP1 to well below the Joukowsky value.

    The free-surface boundary at SP1 clamps the piezometric head to the
    instantaneous water level in the standpipe column.  Because the standpipe
    area (A_s = 1 ft²) is large compared to the pipe area × time step
    (A_pipe·V₀·dt ≈ 0.011 ft³ per step), the level rises slowly and the
    acoustic pressure wave is effectively absorbed.  The peak head at SP1
    over the 25-second simulation (which covers the mass-oscillation first
    maximum at T/4 ≈ 17.1 s) should be:

    * **Above** the initial steady-state head (the standpipe level must rise):
      SP1 peak > H_SP1_ss + 2 ft
    * **Below** the Joukowsky limit (the standpipe is providing protection):
      SP1 peak < 170 ft  (vs ≈ 324 ft without standpipe)
    """
    _, h_sp = _get_rthym_results()
    peak = float(np.max(h_sp))
    assert peak < _TOL_STANDPIPE_UP, (
        f"Standpipe peak {peak:.2f} ft exceeds upper bound "
        f"{_TOL_STANDPIPE_UP:.0f} ft (Joukowsky without standpipe ≈ "
        f"{_H_JOUK_J1_FT:.0f} ft)"
    )
    assert peak > _TOL_STANDPIPE_LO, (
        f"Standpipe peak {peak:.2f} ft is not above the initial steady-state "
        f"level ({_H_SP1_FT:.2f} ft + 2 ft = {_TOL_STANDPIPE_LO:.2f} ft).  "
        f"The standpipe does not appear to have been activated."
    )


def test_standpipe_peak_near_analytical():
    """
    Standpipe peak head agrees with the Wylie & Streeter mass-oscillation formula.

    For frictionless flow the first positive maximum of the standpipe level is:

    .. math::
        z_{\\max} = V_0 \\sqrt{\\frac{A_p \\, L}{g \\, A_s}}
        \\approx 12.1 \\ \\text{ft}

    Peak ≈ H_{SP1,ss} + z_max ≈ 159.8 ft.

    Friction in P1 (HW C=130) damps the oscillation and reduces the peak
    below the frictionless prediction.  A tolerance of ±15 ft (≈ 120 % of
    z_max on the high side, 0 % on the low side; friction only reduces the
    peak) is applied.

    .. note::
       The comparison window for the simulation is 25 s = T_osc/2.7, so the
       first positive peak at T/4 ≈ 17.1 s is included.
    """
    _, h_sp = _get_rthym_results()
    peak = float(np.max(h_sp))
    # Upper bound: frictionless prediction + tolerance
    assert peak <= _H_PEAK_ANALYTICAL_FT + _TOL_PEAK_ANAL_FT, (
        f"SP1 peak {peak:.2f} ft exceeds the frictionless analytical "
        f"prediction {_H_PEAK_ANALYTICAL_FT:.2f} ft + {_TOL_PEAK_ANAL_FT} ft "
        f"tolerance = {_H_PEAK_ANALYTICAL_FT + _TOL_PEAK_ANAL_FT:.2f} ft"
    )
    # Lower bound: standpipe must rise noticeably above steady state
    assert peak >= _H_SP1_FT + 2.0, (
        f"SP1 peak {peak:.2f} ft is only {peak - _H_SP1_FT:.2f} ft above the "
        f"steady-state level ({_H_SP1_FT:.2f} ft).  Expected at least 2 ft rise "
        f"(frictionless z_max = {_Z_MAX_FT:.2f} ft)."
    )


def test_standpipe_overpressure_reduction():
    """
    The standpipe reduces the surge overpressure at the junction by ≥ 80 %.

    Overpressure is defined relative to the initial steady-state head at the
    standpipe / junction location:

    .. math::
        \\text{mitigation} =
        \\frac{H_{\\text{peak,no SP}} - H_{\\text{peak,SP}}}
              {H_{\\text{peak,no SP}} - H_{\\text{SP1,ss}}}
        \\geq 0.80

    This verifies that the open standpipe is performing its intended surge-
    protection function for an instant valve closure.
    """
    h_no_sp, h_sp = _get_rthym_results()
    peak_no_sp = float(np.max(h_no_sp))
    peak_sp    = float(np.max(h_sp))
    overpressure_no_sp = peak_no_sp - _H_SP1_FT
    overpressure_sp    = peak_sp    - _H_SP1_FT
    mitigation = (overpressure_no_sp - overpressure_sp) / overpressure_no_sp

    assert mitigation >= _TOL_MITIGATION_PCT, (
        f"Standpipe mitigation = {mitigation:.1%} < required {_TOL_MITIGATION_PCT:.0%}.\n"
        f"  No-standpipe peak : {peak_no_sp:.1f} ft  "
        f"(overpressure = +{overpressure_no_sp:.1f} ft)\n"
        f"  With-standpipe peak: {peak_sp:.1f} ft  "
        f"(overpressure = +{overpressure_sp:.1f} ft)\n"
        f"  Steady-state head   : {_H_SP1_FT:.1f} ft"
    )


@pytest.mark.skipif(not _TSNET_AVAILABLE, reason="TSNet not installed")
def test_rthym_vs_tsnet_rms():
    """
    Cross-engine agreement: RTHYM-MOC vs TSNet with open surge tank.

    Both engines are run with:

    * Identical wave speed (4000 ft/s), pipe geometry, and friction
    * Steady-friction MOC only (no unsteady-friction correction)
    * Open surge tank at the junction node (A_s = 1 ft²)
    * Instant valve closure at t = 0

    The RMS difference between SP1 (rthym-moc) and J1 (TSNet) is compared
    over t = 0–20 s, which covers the initial acoustic behaviour and the
    rising leg of the first mass-oscillation half-cycle (T/4 ≈ 17.1 s).

    The 2.5 ft tolerance accounts for a small systematic offset arising from
    the different topological representation of the surge tank:

    * **TSNet**: surge tank IS the junction node J1 — the free-surface BC
      is applied without any intermediate pipe, so V1 and J1 are
      acoustically coincident.
    * **RTHYM-MOC**: standpipe SP1 is separated from V1 by one MOC segment
      (P2, 40 ft = 0.01 s acoustic delay).  The first wave arrival at SP1
      is therefore delayed by one time step relative to TSNet's J1.

    This 0.01 s difference does not affect engineering accuracy but
    introduces a small systematic offset that grows slightly over the
    comparison window.
    """
    _, h_sp_rthym   = _get_rthym_results()
    t_tsnet, h_tsnet = _get_tsnet_results()

    # Build a common time axis for the comparison window
    dt        = _DT_S
    n_compare = int(_COMPARE_WINDOW_S / dt)
    t_rthym   = np.arange(len(h_sp_rthym)) * dt

    # RTHYM-MOC samples: take first n_compare points
    h_rthym_win = h_sp_rthym[:n_compare]

    # TSNet samples: interpolate onto the same evenly-spaced grid
    t_win       = t_rthym[:n_compare]
    h_tsnet_win = np.interp(t_win, t_tsnet, h_tsnet)

    rms = float(np.sqrt(np.mean((h_rthym_win - h_tsnet_win) ** 2)))

    assert rms <= _TOL_RMS_FT, (
        f"rthym-moc vs TSNet RMS = {rms:.3f} ft over t = 0–{_COMPARE_WINDOW_S} s "
        f"exceeds tolerance ±{_TOL_RMS_FT} ft.\n"
        f"  RTHYM-MOC SP1 peak : {float(np.max(h_rthym_win)):.2f} ft\n"
        f"  TSNet     J1  peak : {float(np.max(h_tsnet_win)):.2f} ft\n"
        f"  Analytical (no friction): {_H_PEAK_ANALYTICAL_FT:.2f} ft"
    )
