"""
Test: Surge Tank — Mass Oscillation (Analytical) and Pressure Mitigation
=========================================================================
Validates the SurgeTank node type against the classical lumped-parameter
mass-oscillation solution for a reservoir → pipe → surge-tank system.

Analytical reference (frictionless, small-amplitude):
  Wylie & Streeter, "Fluid Transients in Systems" (1993), §9.1

  The frictionless governing equation for a surge tank connected to a
  constant-head reservoir via a horizontal pipe is:

      A_p · L
      ──────── · H_ST''(t) + A_s · (H_ST − H_res) = 0
         g

  with initial conditions H_ST(0) = H_res, H_ST'(0) = Q₀ / A_s

  Solution:
      z(t) = H_ST(t) − H_res = z_max · sin(ω · t)

  where
      ω       = √( g · A_p / (A_s · L) )       [rad/s]
      T       = 2π / ω                           [s]
      z_max   = V₀ · √( A_p · L / (g · A_s) )  [ft]

  and V₀ = Q₀ / A_p is the initial pipe velocity.

This test is deliberately kept frictionless (HW C = 10000) so the
analytical solution applies without damping corrections.  The ratio of
the acoustic (waterhammer) period to the surge-oscillation period is
T_wh / T_surge ≈ 2L/a / T ≈ 0.5 / 88 ≈ 0.006, so acoustic effects
introduce negligible distortion of the surge envelope.

Two checks are performed:
  1. Amplitude: simulated z_max within 5 % of analytical prediction.
  2. Period:    simulated T within 3 % of analytical prediction.

A second test then demonstrates that the surge tank reduces the
Joukowsky over-pressure by > 80 % compared with a rigid dead-end
boundary, confirming the protective function of the device.

Network topologies
  Test 1 – mass oscillation:
      R1 (PressureBoundary, H = 100 ft) ──[P1: 1000 ft, 12 in, HW C = 10000]──
      ST1 (SurgeTank, A_s = 5 ft², initial level = H_res)

      Initial pipe flow Q₀ = 500 GPM supplies the initial kinetic energy
      that drives the surge oscillation.

  Test 2 – pressure mitigation:
      Network A: R1 ──[P1]── J1 (dead-end Junction, demand = 0)
          → rigid zero-flow reflection → Joukowsky head spike

      Network B: R1 ──[P1]── ST1 (SurgeTank, same parameters)
          → surge tank absorbs incoming flow → head rise limited to z_max

Usage:
    python examples/test_surge_tank.py
"""

import math
import time

import numpy as np

import rthym_moc as m

# ── Physical constants ────────────────────────────────────────────────────────
GPM_TO_CFS = 0.002228
G_US       = 32.2          # ft/s²

# ── Shared test parameters ────────────────────────────────────────────────────
H_RES_FT         = 100.0   # reservoir / initial surge-tank head [ft]
L_FT             = 1000.0  # pipe length [ft]
D_IN             = 12.0    # pipe diameter [in]
HW_C_FRICTIONLESS = 10000.0  # Hazen-Williams C ≈ frictionless (Hf < 0.001 ft)
Q0_GPM           = 500.0   # initial pipe flow [GPM]
A_S_FT2          = 5.0     # surge-tank standpipe area [ft²]
DT_S             = 0.01    # time step [s]

# ── Derived quantities ────────────────────────────────────────────────────────
D_FT   = D_IN / 12.0
A_PIPE = math.pi * (D_FT / 2.0) ** 2         # pipe cross-section [ft²]
V0_FT  = Q0_GPM * GPM_TO_CFS / A_PIPE        # initial velocity [ft/s]

# Courant-adjusted wave speed for P1 (rigid-pipe default 4000 ft/s)
N_SEGS_P1 = max(1, round(L_FT / (4000.0 * DT_S)))
A_ADJ_FT  = L_FT / (N_SEGS_P1 * DT_S)        # ft/s

# ── Analytical mass-oscillation solution (Wylie & Streeter §9.1) ──────────────
OMEGA_RAD   = math.sqrt(G_US * A_PIPE / (A_S_FT2 * L_FT))  # [rad/s]
T_SURGE_S   = 2.0 * math.pi / OMEGA_RAD                     # [s]
Z_MAX_FT    = V0_FT * math.sqrt(A_PIPE * L_FT / (G_US * A_S_FT2))  # [ft]
H_ST_MAX_FT = H_RES_FT + Z_MAX_FT

# Acoustic (waterhammer) period for P1
T_ACOUSTIC_S = 2.0 * L_FT / A_ADJ_FT          # 2L/a [s]

# ── Analytical Joukowsky peak for the dead-end (Test 2) ──────────────────────
DH_JOUK_FT      = A_ADJ_FT * V0_FT / G_US     # a·V₀/g [ft]
H_DEADEND_PEAK  = H_RES_FT + DH_JOUK_FT       # expected Joukowsky peak [ft]

print("=" * 65)
print("  Surge Tank Validation Test")
print("=" * 65)
print(f"  Pipe      : L = {L_FT:.0f} ft, D = {D_IN:.0f} in, a = {A_ADJ_FT:.0f} ft/s")
print(f"  A_pipe    : {A_PIPE:.4f} ft²     A_s = {A_S_FT2:.1f} ft²")
print(f"  Q₀        : {Q0_GPM:.0f} GPM   → V₀ = {V0_FT:.4f} ft/s")
print(f"  T_acoustic: 2L/a = {T_ACOUSTIC_S:.3f} s  "
      f"(ratio T_surge/T_acoustic = {T_SURGE_S/T_ACOUSTIC_S:.0f})")
print()
print(f"  Analytical ω     : {OMEGA_RAD:.5f} rad/s")
print(f"  Analytical T     : {T_SURGE_S:.2f} s")
print(f"  Analytical z_max : {Z_MAX_FT:.3f} ft  →  H_ST_max = {H_ST_MAX_FT:.3f} ft")
print(f"  Joukowsky ΔH     : {DH_JOUK_FT:.1f} ft  →  dead-end peak ≈ {H_DEADEND_PEAK:.1f} ft")
print()


# ═══════════════════════════════════════════════════════════════════════════════
# Utility: numpy-only peak finder
# ═══════════════════════════════════════════════════════════════════════════════

def _first_n_peaks(arr, min_height, min_sep_samples, n=2):
    """Return indices of first *n* local maxima above *min_height* that are
    separated by at least *min_sep_samples* samples.  Uses numpy only."""
    peaks = []
    for i in range(1, len(arr) - 1):
        if arr[i] >= min_height and arr[i] > arr[i - 1] and arr[i] > arr[i + 1]:
            if not peaks or (i - peaks[-1]) >= min_sep_samples:
                peaks.append(i)
                if len(peaks) == n:
                    break
    return peaks


# ═══════════════════════════════════════════════════════════════════════════════
# Test 1: Mass Oscillation — Analytical Comparison
# ═══════════════════════════════════════════════════════════════════════════════
#
# Network:  R1 ──[P1: near-frictionless]── ST1 (SurgeTank)
#
# The pipe carries Q₀ toward the surge tank whose initial level equals the
# reservoir head.  This non-equilibrium initial condition is the classical
# "initial velocity" mode of mass oscillation (z(0)=0, ż(0)=Q₀/A_s).
# ═══════════════════════════════════════════════════════════════════════════════

print("─" * 65)
print("  Test 1: Mass Oscillation  R1 ──[P1, frictionless]── ST1")
print("─" * 65)

solver1 = m.MOCSolver()

r1_t1 = m.NodeInput()
r1_t1.id   = "R1"
r1_t1.type = "PressureBoundary"
r1_t1.head = H_RES_FT

st1 = m.NodeInput()
st1.id        = "ST1"
st1.type      = "SurgeTank"
st1.head      = H_RES_FT     # initial water-surface = reservoir head
st1.tank_area = A_S_FT2      # standpipe cross-section [ft²]

p1_t1 = m.PipeInput()
p1_t1.id        = "P1"
p1_t1.from_node = "R1"
p1_t1.to_node   = "ST1"
p1_t1.length    = L_FT
p1_t1.diameter  = D_IN
p1_t1.roughness = HW_C_FRICTIONLESS
p1_t1.flow_gpm  = Q0_GPM      # initial kinetic energy drives oscillation

solver1.add_node(r1_t1)
solver1.add_node(st1)
solver1.add_pipe(p1_t1)

# Simulate for 3.5 surge periods so at least 3 positive peaks are observable
TOTAL_T1_S = math.ceil(3.5 * T_SURGE_S / 10.0) * 10.0   # round up to 10 s

t_wall0 = time.perf_counter()
# usf_tau = DT_S disables the Brunone unsteady-friction filter, matching
# the frictionless analytical model exactly.
results1  = solver1.run(TOTAL_T1_S, DT_S, -14.0, DT_S)
t_wall1   = time.perf_counter()

t_arr  = np.array(results1["time"])
H_st   = np.array(results1["node_head"]["ST1"])

# ── Peak detection ─────────────────────────────────────────────────────────────
# Decimate to suppress acoustic ripple (period T_acoustic = 0.5 s).
# One sample per acoustic half-period keeps the decimated series well above
# the Nyquist limit for the surge oscillation (T_surge / 2 >> T_acoustic).
dec     = max(1, int(T_ACOUSTIC_S / DT_S))   # ~50 samples = 0.5 s
H_dec   = H_st[::dec]
t_dec   = t_arr[::dec]

# Peaks must exceed 90 % of the expected amplitude above the reservoir head,
# and be separated by at least 30 % of the expected surge period.
min_peak_h   = H_RES_FT + 0.90 * Z_MAX_FT
min_sep_dec  = max(1, int(0.30 * T_SURGE_S / (dec * DT_S)))

peak_idx = _first_n_peaks(H_dec, min_height=min_peak_h,
                          min_sep_samples=min_sep_dec, n=2)

assert len(peak_idx) >= 2, (
    f"Expected at least 2 surge peaks above {min_peak_h:.2f} ft in "
    f"{TOTAL_T1_S:.0f} s; found {len(peak_idx)}.  "
    f"Check network setup or simulation duration."
)

t_pk1, t_pk2 = float(t_dec[peak_idx[0]]), float(t_dec[peak_idx[1]])
T_measured   = t_pk2 - t_pk1            # simulated period [s]
z_measured   = float(H_dec[peak_idx[0]]) - H_RES_FT  # simulated amplitude [ft]

amp_err = abs(z_measured - Z_MAX_FT)  / Z_MAX_FT
per_err = abs(T_measured  - T_SURGE_S) / T_SURGE_S

t_elapsed_ms = (t_wall1 - t_wall0) * 1000.0

print(f"  Simulation: {TOTAL_T1_S:.0f} s, {len(t_arr)} steps, "
      f"wall-time {t_elapsed_ms:.1f} ms")
print(f"  First peak  at t = {t_pk1:.2f} s  "
      f"(expected T/4 = {T_SURGE_S/4:.2f} s)")
print(f"  Second peak at t = {t_pk2:.2f} s  "
      f"(expected 5T/4 = {T_SURGE_S*1.25:.2f} s)")
print(f"  Simulated period  : {T_measured:.2f} s  "
      f"(analytical {T_SURGE_S:.2f} s,  err {per_err*100:.1f}%)")
print(f"  Simulated z_max   : {z_measured:.3f} ft  "
      f"(analytical {Z_MAX_FT:.3f} ft,  err {amp_err*100:.1f}%)")
print(f"  Peak head at ST1  : {H_RES_FT + z_measured:.3f} ft  "
      f"(analytical {H_ST_MAX_FT:.3f} ft)")

AMP_TOL = 0.05   # 5 % tolerance on surge amplitude
PER_TOL = 0.03   # 3 % tolerance on surge period

assert amp_err < AMP_TOL, (
    f"Surge amplitude error {amp_err*100:.1f}% exceeds {AMP_TOL*100:.0f}% tolerance "
    f"(simulated {z_measured:.3f} ft vs analytical {Z_MAX_FT:.3f} ft)"
)
assert per_err < PER_TOL, (
    f"Surge period error {per_err*100:.1f}% exceeds {PER_TOL*100:.0f}% tolerance "
    f"(simulated {T_measured:.2f} s vs analytical {T_SURGE_S:.2f} s)"
)

print(f"  ✓ Amplitude within {AMP_TOL*100:.0f}%  (analytical benchmark)")
print(f"  ✓ Period    within {PER_TOL*100:.0f}%  (analytical benchmark)")
print()


# ═══════════════════════════════════════════════════════════════════════════════
# Test 2: Pressure Mitigation — Dead End vs. Surge Tank
# ═══════════════════════════════════════════════════════════════════════════════
#
# Compares the peak piezometric head at the far end of P1 for two boundary
# conditions applied to the same pipe/initial-flow setup:
#
#   Network A — Dead end (Junction, demand = 0, no outflow pipe):
#       The MOC enforces Q = 0 exactly (H = C⁺), producing an immediate
#       Joukowsky head spike of ΔH = a·V₀/g at the first time step.
#
#   Network B — Surge tank (SurgeTank, same geometry as Test 1):
#       The surge tank admits the incoming flow, so the head at the pipe
#       terminus rises slowly at the mass-oscillation rate rather than
#       jumping instantaneously.
#
# Expected outcome: over-pressure reduction > 80 % (actual ≈ 98 %).
# ═══════════════════════════════════════════════════════════════════════════════

print("─" * 65)
print("  Test 2: Pressure Mitigation — dead end vs. surge tank")
print("─" * 65)

MITIGATION_RUN_S = 1.5 * T_SURGE_S   # long enough to capture ST peak at T/4

# ── Network A: dead-end reflection ────────────────────────────────────────────
solver_nd = m.MOCSolver()

r1_nd = m.NodeInput()
r1_nd.id   = "R1"
r1_nd.type = "PressureBoundary"
r1_nd.head = H_RES_FT

j1 = m.NodeInput()
j1.id     = "J1"
j1.type   = "Junction"
j1.demand = 0.0            # zero demand → zero-flow dead-end BC (H = C⁺)

p1_nd = m.PipeInput()
p1_nd.id        = "P1"
p1_nd.from_node = "R1"
p1_nd.to_node   = "J1"
p1_nd.length    = L_FT
p1_nd.diameter  = D_IN
p1_nd.roughness = HW_C_FRICTIONLESS
p1_nd.flow_gpm  = Q0_GPM

solver_nd.add_node(r1_nd)
solver_nd.add_node(j1)
solver_nd.add_pipe(p1_nd)

# 5 seconds is sufficient to capture the first Joukowsky peak (occurs at dt)
res_nd       = solver_nd.run(5.0, DT_S, -14.0, DT_S)
H_j1         = np.array(res_nd["node_head"]["J1"])
H_peak_deadend = float(H_j1.max())

# ── Network B: surge-tank terminus ────────────────────────────────────────────
solver_st = m.MOCSolver()

r1_st = m.NodeInput()
r1_st.id   = "R1"
r1_st.type = "PressureBoundary"
r1_st.head = H_RES_FT

st2 = m.NodeInput()
st2.id        = "ST1"
st2.type      = "SurgeTank"
st2.head      = H_RES_FT
st2.tank_area = A_S_FT2

p1_st = m.PipeInput()
p1_st.id        = "P1"
p1_st.from_node = "R1"
p1_st.to_node   = "ST1"
p1_st.length    = L_FT
p1_st.diameter  = D_IN
p1_st.roughness = HW_C_FRICTIONLESS
p1_st.flow_gpm  = Q0_GPM

solver_st.add_node(r1_st)
solver_st.add_node(st2)
solver_st.add_pipe(p1_st)

res_st       = solver_st.run(MITIGATION_RUN_S, DT_S, -14.0, DT_S)
H_st2        = np.array(res_st["node_head"]["ST1"])
H_peak_st    = float(H_st2.max())

# ── Over-pressure reduction ───────────────────────────────────────────────────
over_p_deadend = H_peak_deadend - H_RES_FT    # [ft]
over_p_st      = H_peak_st      - H_RES_FT    # [ft]
reduction_pct  = (over_p_deadend - over_p_st) / over_p_deadend * 100.0

print(f"  Dead-end peak head   : {H_peak_deadend:.1f} ft  "
      f"(over-pressure {over_p_deadend:.1f} ft;  "
      f"analytical Joukowsky ΔH = {DH_JOUK_FT:.1f} ft,  "
      f"err {abs(H_peak_deadend - H_DEADEND_PEAK)/DH_JOUK_FT*100:.1f}%)")
print(f"  Surge-tank peak head : {H_peak_st:.1f} ft  "
      f"(over-pressure {over_p_st:.1f} ft;  "
      f"analytical z_max = {Z_MAX_FT:.3f} ft)")
print(f"  Over-pressure reduction: {reduction_pct:.0f}%")

assert H_peak_st < H_peak_deadend, (
    f"Surge-tank peak ({H_peak_st:.1f} ft) is not less than "
    f"dead-end peak ({H_peak_deadend:.1f} ft)"
)
REDUCTION_MIN_PCT = 80.0
assert reduction_pct >= REDUCTION_MIN_PCT, (
    f"Over-pressure reduction {reduction_pct:.1f}% is below "
    f"the minimum expected {REDUCTION_MIN_PCT:.0f}%"
)

print(f"  ✓ Surge-tank peak < dead-end Joukowsky peak")
print(f"  ✓ Over-pressure reduction ≥ {REDUCTION_MIN_PCT:.0f}%  "
      f"({reduction_pct:.0f}% achieved)")
print()

# ═══════════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════════

print("=" * 65)
print("  All checks passed.")
print("=" * 65)
print(f"  Test 1 — Mass oscillation amplitude : "
      f"{z_measured:.3f} ft vs {Z_MAX_FT:.3f} ft analytical  "
      f"({amp_err*100:.1f}% error ≤ {AMP_TOL*100:.0f}%)")
print(f"  Test 1 — Oscillation period         : "
      f"{T_measured:.2f} s vs {T_SURGE_S:.2f} s analytical  "
      f"({per_err*100:.1f}% error ≤ {PER_TOL*100:.0f}%)")
print(f"  Test 2 — Over-pressure reduction    : "
      f"{reduction_pct:.0f}%  (surge tank vs dead end)")
print()

# ── Optional: plot surge-tank level and analytical curve ─────────────────────
try:
    import matplotlib.pyplot as plt

    t_analytical = np.linspace(0.0, TOTAL_T1_S, 4000)
    H_analytical = H_RES_FT + Z_MAX_FT * np.sin(OMEGA_RAD * t_analytical)

    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=False)

    # ── Upper panel: mass oscillation ────────────────────────────────────────
    ax1 = axes[0]
    ax1.plot(t_arr, H_st, color="steelblue", lw=0.8, alpha=0.7,
             label="rthym_moc (MOC)")
    ax1.plot(t_analytical, H_analytical, color="tomato", lw=1.5, ls="--",
             label="Analytical (frictionless lumped-parameter)")
    ax1.axhline(H_RES_FT, color="k", ls=":", lw=0.8, label="H_res = 100 ft")
    ax1.scatter([t_pk1, t_pk2],
                [H_RES_FT + z_measured, H_RES_FT + z_measured],
                color="steelblue", zorder=5, s=40, label="Detected peaks")
    ax1.set_xlabel("Time  [s]")
    ax1.set_ylabel("Surge-tank head  [ft]")
    ax1.set_title("Test 1 — Surge Tank Mass Oscillation")
    ax1.legend(fontsize=8)
    ax1.grid(True, alpha=0.3)
    ypad = max(Z_MAX_FT * 0.4, 2.0)
    ax1.set_ylim(H_RES_FT - Z_MAX_FT - ypad, H_RES_FT + Z_MAX_FT + ypad)

    # ── Lower panel: pressure mitigation ─────────────────────────────────────
    ax2 = axes[1]
    t_nd = np.array(res_nd["time"])
    t_st = np.array(res_st["time"])

    ax2.plot(t_nd, H_j1,  color="firebrick",  lw=1.2,
             label=f"Dead end (J1)  peak = {H_peak_deadend:.0f} ft")
    ax2.plot(t_st, H_st2, color="steelblue", lw=1.2,
             label=f"Surge tank (ST1)  peak = {H_peak_st:.1f} ft")
    ax2.axhline(H_DEADEND_PEAK, color="firebrick", ls=":", lw=0.8,
                label=f"Joukowsky analytical = {H_DEADEND_PEAK:.0f} ft")
    ax2.axhline(H_ST_MAX_FT, color="steelblue", ls=":", lw=0.8,
                label=f"z_max analytical = {H_ST_MAX_FT:.1f} ft")
    ax2.set_xlabel("Time  [s]")
    ax2.set_ylabel("Head at pipe terminus  [ft]")
    ax2.set_title("Test 2 — Pressure Mitigation: Dead End vs. Surge Tank")
    ax2.legend(fontsize=8)
    ax2.grid(True, alpha=0.3)
    ax2.set_xlim(0, min(MITIGATION_RUN_S, 50.0))   # first 50 s is illustrative

    plt.tight_layout()
    plt.savefig("surge_tank_test.png", dpi=150)
    print("  Plot saved to surge_tank_test.png")
    plt.show()
except ImportError:
    pass
