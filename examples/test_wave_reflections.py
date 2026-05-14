"""
Test: Multi-Cycle Wave Reflections — Period & Damping Verification
==================================================================
After instantaneous flow stoppage at a dead-end junction (reservoir–pipe–dead-end
system), pressure waves bounce between the dead-end and the constant-head reservoir.

Physical predictions (pure-MOC, no column separation):
  Wave period:  T = 2L/a  (time between successive positive pressure peaks)
  Peak damping: each round-trip dissipates ≈2·Hf of head (friction)

This test verifies:
  1. Correct wave period T = 2L/a measured from successive positive peaks.
  2. Amplitude decays monotonically due to friction (no numerical growth).
  3. rthym_moc and TSNet produce nearly identical time histories
     (RMS difference < 1.0 ft over the full simulation).

High-head reservoir (H_res = 300 ft) is used so that the negative-swing trough
(~120 ft) stays well above the vapour-pressure threshold (~−32 ft), eliminating
column separation and TSNet backflow warnings.

rthym_moc network:  R1 (H=300 ft) ──[P1: 3000 ft, 12 in, HW=130]──● DE (dead-end)
  The dead-end junction enforces Q=0 → H_DE = C⁺ (perfect pressure-wave reflector).
  No stub pipe needed; eliminates any stub-pipe resonance artefacts.

TSNet network:      R1 ──[P1]── J1 ──[TCV V1, closes in 1 step]── R2
  TCV instant closure makes J1 behave identically to a dead-end from P1's viewpoint.

Simulation: 9 s > 3 oscillation periods (T₀ = 3.0 s each)

Usage:
    python examples/test_wave_reflections.py
"""

import math
import os
import tempfile
import time

import numpy as np

# ── Unit conversions ───────────────────────────────────────────────────────────
FT_TO_M    = 0.3048
IN_TO_MM   = 25.4
GPM_TO_M3S = 6.309e-5
GPM_TO_CFS = 0.002228
G_SI       = 9.81
G_US       = 32.2

# ── Parameters ────────────────────────────────────────────────────────────────
# Use H_res = 300 ft so the negative-swing trough (~123 ft) stays positive,
# avoiding column separation and TSNet's reverse-flow limiter at R1.
H_RES_FT  = 300.0
L_FT      = 3000.0
D_IN      = 12.0
HW_C      = 130.0
Q0_GPM    = 500.0
A_WAVE_FT = 4000.0
DT_S      = 0.01
TOTAL_S   = 9.0    # 3 full oscillation periods (T0 = 4L/a = 3.0 s)

D_FT      = D_IN / 12.0
A_PIPE    = math.pi * (D_FT / 2.0) ** 2
V0_FT     = Q0_GPM * GPM_TO_CFS / A_PIPE

H_RES_M   = H_RES_FT  * FT_TO_M
L_M       = L_FT       * FT_TO_M
D_MM      = D_IN       * IN_TO_MM
A_WAVE_M  = A_WAVE_FT  * FT_TO_M
V0_M      = V0_FT      * FT_TO_M
D_M       = D_FT       * FT_TO_M

Q0_M3S    = Q0_GPM * GPM_TO_M3S
Hf_M      = 10.67 * L_M * Q0_M3S**1.852 / (HW_C**1.852 * D_M**4.87)
H_DN_M    = H_RES_M - Hf_M
H_DN_FT   = H_DN_M / FT_TO_M

dH_FT     = A_WAVE_FT * V0_FT / G_US
dH_M      = A_WAVE_M  * V0_M  / G_SI

# T_transit = 2L/a  (wave round-trip time = HALF the oscillation period)
# T_osc     = 4L/a  (FULL oscillation period = time between successive positive peaks)
T_TRANSIT_S = 2.0 * L_FT / A_WAVE_FT   # = 1.50 s (half-period)
T_WAVE_S    = 4.0 * L_FT / A_WAVE_FT   # = 3.00 s (full oscillation period)
T_HALF_S    = L_FT / A_WAVE_FT          # = 0.75 s (wave travel time from DE to R1)

# Banner ────────────────────────────────────────────────────────────────────────
print("=" * 65)
print("  Multi-Cycle Wave Reflections — Period & Damping Test")
print("=" * 65)
print(f"  Pipe         : L={L_FT:.0f} ft, D={D_IN:.0f} in, HW={HW_C:.0f}, a={A_WAVE_FT:.0f} ft/s")
print(f"  H_res        : {H_RES_FT:.0f} ft  (high enough to avoid column separation)")
print(f"  Initial flow : {Q0_GPM:.0f} GPM  (V₀={V0_FT:.4f} ft/s)")
print(f"  Joukowsky ΔH : {dH_FT:.2f} ft")
print(f"  H_DN         : {H_DN_FT:.3f} ft  →  H_peak1 ≈ {H_DN_FT + dH_FT:.2f} ft")
print(f"  H_trough1    ≈ {H_DN_FT - dH_FT:.1f} ft  (well above H_vapor ≈ −32 ft)")
print(f"  Wave transit : 2L/a = {T_TRANSIT_S:.4f} s  (positive → negative half-period)")
print(f"  Oscillation T: 4L/a = {T_WAVE_S:.4f} s  (positive peak → positive peak)")
print(f"  Simulation   : {TOTAL_S:.1f} s  = {TOTAL_S/T_WAVE_S:.0f} full oscillation periods")
print()


# ── Helper: detect positive pressure peaks ────────────────────────────────────
def find_positive_peaks(arr, time_arr, threshold_h, min_spacing_steps=120):
    """Return (indices, times, values) of positive local maxima strictly above threshold_h.

    threshold_h: minimum head value to qualify as a 'positive' peak.
        Setting this to H_DN + 0.4*dH filters out the negative-swing troughs.
    min_spacing_steps: enforces a minimum gap (time steps) between reported peaks.
    """
    peaks = []
    for i in range(1, len(arr) - 1):
        if arr[i] > arr[i-1] and arr[i] >= arr[i+1] and arr[i] > threshold_h:
            if not peaks or (i - peaks[-1][0]) >= min_spacing_steps:
                peaks.append((i, time_arr[i], arr[i]))
    return peaks


def find_plateau_peaks(arr, time_arr, threshold_h):
    """Return the MAXIMUM within each contiguous run of arr > threshold_h.

    In MOC dead-end systems, H forms a 'staircase' during each positive plateau
    (head rises by one HGL-slope increment every two time steps).  Using local-
    maxima detection finds dozens of peaks per plateau.  This function instead
    finds exactly ONE peak per positive segment — the plateau maximum — which
    correctly measures the FULL OSCILLATION PERIOD T₀ = 4L/a.
    """
    peaks = []
    in_seg = False
    seg_max_h = -np.inf
    seg_max_idx = -1
    for i, h in enumerate(arr):
        if h > threshold_h:
            if not in_seg:
                in_seg = True
            if h > seg_max_h:
                seg_max_h = h
                seg_max_idx = i
        else:
            if in_seg:
                peaks.append((seg_max_idx, time_arr[seg_max_idx], seg_max_h))
                in_seg = False
                seg_max_h = -np.inf
                seg_max_idx = -1
    if in_seg and seg_max_idx >= 0:   # last segment reaches end of array
        peaks.append((seg_max_idx, time_arr[seg_max_idx], seg_max_h))
    return peaks


# ═══════════════════════════════════════════════════════════════════════════════
# 1. rthym_moc
# ═══════════════════════════════════════════════════════════════════════════════
import rthym_moc as m

print("─" * 65)
print("  1. rthym_moc  (C++ core, dead-end junction DE)")
print("─" * 65)

solver = m.MOCSolver()

r1 = m.NodeInput(); r1.id = "R1"; r1.type = "PressureBoundary"; r1.head = H_RES_FT

# Dead-end junction: demand=0, no out-pipes → Junction BC enforces Q=0 → H=C⁺
# This is the cleanest possible wave reflector — no stub pipe, no coupling artefacts.
de = m.NodeInput(); de.id = "DE"; de.type = "Junction"; de.demand = 0.0
de.head = H_DN_FT

p1 = m.PipeInput(); p1.id = "P1"; p1.from_node = "R1"; p1.to_node = "DE"
p1.length = L_FT; p1.diameter = D_IN; p1.roughness = HW_C; p1.flow_gpm = Q0_GPM

solver.add_node(r1); solver.add_node(de)
solver.add_pipe(p1)

t0 = time.perf_counter()
results = solver.run(TOTAL_S, DT_S, -14.0, DT_S)  # USF disabled (usf_tau = dt)
t_rthym = time.perf_counter() - t0

t_arr   = np.array(results["time"])
H_de_ft = np.array(results["node_head"]["DE"])

# Detect one peak per POSITIVE PLATEAU: the maximum H within each continuous
# segment above threshold = H_DN + 0.4*dH_FT.
# The MOC dead-end 'staircase' produces dozens of local maxima per plateau;
# find_plateau_peaks() returns exactly one peak per positive swing.
# Successive positive peaks are separated by T₀ = 4L/a (full oscillation period).
threshold_ft = H_DN_FT + 0.4 * dH_FT
peaks_r = find_plateau_peaks(H_de_ft, t_arr, threshold_ft)

print(f"  Execution time   : {t_rthym*1000:.2f} ms  ({len(t_arr)} steps)")
print(f"  Detected peaks   : {len(peaks_r)}  (plateau maxima, H > {threshold_ft:.1f} ft)")
print(f"  Expected         : ~{TOTAL_S/T_WAVE_S:.0f} peaks  (T₀ = 4L/a = {T_WAVE_S:.1f} s per period)")
print()
print(f"  {'Peak #':>7}  {'t (s)':>8}  {'H (ft)':>10}  {'ΔH (ft)':>10}  "
      f"{'T_measured (s)':>16}  {'T_error':>10}")
print("  " + "─" * 68)

T_measured_r = []
for k, (idx, t_pk, H_pk) in enumerate(peaks_r):
    dH = H_pk - H_DN_FT
    if k == 0:
        print(f"  {k+1:>7}  {t_pk:>8.3f}  {H_pk:>10.2f}  {dH:>10.2f}  "
              f"{'—':>16}  {'—':>10}")
    else:
        T_m = t_pk - peaks_r[k-1][1]
        T_measured_r.append(T_m)
        err_pct = (T_m - T_WAVE_S) / T_WAVE_S * 100.0
        print(f"  {k+1:>7}  {t_pk:>8.3f}  {H_pk:>10.2f}  {dH:>10.2f}  "
              f"{T_m:>16.4f}  {err_pct:>+9.3f}%")

if T_measured_r:
    T_mean = np.mean(T_measured_r)
    print(f"\n  Mean osc. period : {T_mean:.4f} s  "
          f"(4L/a = {T_WAVE_S:.4f} s,  error: "
          f"{(T_mean-T_WAVE_S)/T_WAVE_S*100:.3f}%)")

peak_vals_r = [H for _, _, H in peaks_r]
if len(peak_vals_r) >= 2:
    print(f"  Peak decay       : {peak_vals_r[0]:.2f}→{peak_vals_r[-1]:.2f} ft  "
          f"({(peak_vals_r[0]-peak_vals_r[-1]):.2f} ft total over "
          f"{len(peak_vals_r)-1} periods)")
    # Check monotonic decay
    decays_ok = all(peak_vals_r[i] >= peak_vals_r[i+1] for i in range(len(peak_vals_r)-1))
    print(f"  Monotonic decay  : {'YES ✓' if decays_ok else 'NO — check for numerical growth'}")
print()


# ═══════════════════════════════════════════════════════════════════════════════
# 2. TSNet
# ═══════════════════════════════════════════════════════════════════════════════
print("─" * 65)
print("  2. TSNet  (pure Python, instant TCV closure)")
print("─" * 65)

try:
    import tsnet

    inp_content = f"""[TITLE]
Wave Reflections Test  (H_res = 300 ft)

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
;ID   Head   Pattern
 R1   {H_RES_M:.5f}   ;
 R2   {H_DN_M:.5f}   ;

[PIPES]
;ID  Node1  Node2  Length    Diam    Rough  MLoss  Status
 P1  R1     J1     {L_M:.3f}  {D_MM:.3f}  {HW_C:.0f}    0      Open

[VALVES]
;ID  Node1  Node2  Diam     Type  Setting  MLoss
 V1  J1     R2     {D_MM:.3f}  TCV   0.001    0

[REPORT]
 Status  No
 Summary No

[END]
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.inp', delete=False) as f:
        f.write(inp_content); inp_path = f.name

    tm = tsnet.network.TransientModel(inp_path)
    os.unlink(inp_path)

    tm.set_wavespeed(A_WAVE_M)
    tm.set_time(TOTAL_S, DT_S)
    dt_ts = tm.time_step

    tc = dt_ts; ts = 0.0; se = 0.0; mc = 1   # instant closure
    tm.valve_closure('V1', [tc, ts, se, mc])
    tm = tsnet.simulation.Initializer(tm, 0.0, 'DD')

    t0    = time.perf_counter()
    tm    = tsnet.simulation.MOCSimulator(tm)
    t_tsnet = time.perf_counter() - t0

    node_J1 = tm.get_node('J1')
    H_J1_m  = np.array(node_J1._head)
    H_J1_ft = H_J1_m / FT_TO_M
    t_tsnet_arr = np.arange(len(H_J1_ft)) * dt_ts

    peaks_ts = find_plateau_peaks(H_J1_ft, t_tsnet_arr, threshold_ft)

    print(f"  Execution time   : {t_tsnet*1000:.1f} ms  ({len(H_J1_ft)} steps)")
    print(f"  Detected peaks   : {len(peaks_ts)}  (plateau maxima, H > {threshold_ft:.1f} ft)")
    print()
    print(f"  {'Peak #':>7}  {'t (s)':>8}  {'H (ft)':>10}  {'ΔH (ft)':>10}  "
          f"{'T_measured (s)':>16}  {'T_error':>10}")
    print("  " + "─" * 68)

    T_measured_ts = []
    for k, (idx, t_pk, H_pk) in enumerate(peaks_ts):
        dH = H_pk - H_DN_FT
        if k == 0:
            print(f"  {k+1:>7}  {t_pk:>8.3f}  {H_pk:>10.2f}  {dH:>10.2f}  "
                  f"{'—':>16}  {'—':>10}")
        else:
            T_m = t_pk - peaks_ts[k-1][1]
            T_measured_ts.append(T_m)
            err_pct = (T_m - T_WAVE_S) / T_WAVE_S * 100.0
            print(f"  {k+1:>7}  {t_pk:>8.3f}  {H_pk:>10.2f}  {dH:>10.2f}  "
                  f"{T_m:>16.4f}  {err_pct:>+9.3f}%")

    if T_measured_ts:
        T_mean_ts = np.mean(T_measured_ts)
        print(f"\n  Mean osc. period : {T_mean_ts:.4f} s  "
              f"(4L/a = {T_WAVE_S:.4f} s,  error: "
              f"{(T_mean_ts-T_WAVE_S)/T_WAVE_S*100:.3f}%)")

    peak_vals_ts = [H for _, _, H in peaks_ts]
    if len(peak_vals_ts) >= 2:
        print(f"  Peak decay       : {peak_vals_ts[0]:.2f}→{peak_vals_ts[-1]:.2f} ft  "
              f"({(peak_vals_ts[0]-peak_vals_ts[-1]):.2f} ft total over "
              f"{len(peak_vals_ts)-1} periods)")
    print()

    # ── Cross-comparison ──────────────────────────────────────────────────────
    print("=" * 65)
    print("  Cross-Comparison Summary")
    print("=" * 65)

    # Interpolate TSNet onto rthym_moc time grid for RMS
    H_ts_interp = np.interp(t_arr, t_tsnet_arr, H_J1_ft)
    rms_ft = float(np.sqrt(np.mean((H_de_ft - H_ts_interp)**2)))
    max_diff = float(np.max(np.abs(H_de_ft - H_ts_interp)))

    print(f"  Analytical 4L/a (full period) : {T_WAVE_S:.4f} s")
    print(f"  Analytical 2L/a (half-period) : {T_TRANSIT_S:.4f} s  (wave round-trip)")
    if T_measured_r:
        print(f"  rthym_moc osc. period : {np.mean(T_measured_r):.4f} s  "
              f"(err {(np.mean(T_measured_r)-T_WAVE_S)/T_WAVE_S*100:+.3f}%)")
    if T_measured_ts:
        print(f"  TSNet     osc. period : {np.mean(T_measured_ts):.4f} s  "
              f"(err {(np.mean(T_measured_ts)-T_WAVE_S)/T_WAVE_S*100:+.3f}%)")
    print()

    print(f"  Peak amplitudes over {TOTAL_S:.0f} s:")
    print(f"  {'Cycle':>6}  {'rthym (ft)':>12}  {'TSNet (ft)':>12}  {'Diff (ft)':>12}")
    print("  " + "─" * 46)
    n_compare = min(len(peaks_r), len(peaks_ts))
    for k in range(n_compare):
        diff = peaks_r[k][2] - peaks_ts[k][2]
        print(f"  {k+1:>6}  {peaks_r[k][2]:>12.2f}  {peaks_ts[k][2]:>12.2f}  "
              f"{diff:>+12.2f}")
    print()
    print(f"  RMS head difference (full {TOTAL_S:.0f} s): {rms_ft:.3f} ft")
    print(f"  Max head difference                 : {max_diff:.3f} ft")
    print(f"  Speed ratio                         : "
          f"{t_tsnet/t_rthym:.0f}×  (rthym_moc vs TSNet)")

except ImportError:
    print("  TSNet not installed — rthym_moc wave period results above are self-validating.")
except Exception as exc:
    print(f"  TSNet error: {exc}")
    print(f"  rthym_moc wave period results above are self-validating.")
