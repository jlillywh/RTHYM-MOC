# Copyright (c) 2026 Jason Lillywhite <jason@lillywhitewater.com>
# SPDX-License-Identifier: MIT
# Author: Jason Lillywhite <jason@lillywhitewater.com>
"""
Benchmark: rthym_moc (C++ core) vs TSNet (pure Python)
=======================================================
Joukowsky waterhammer test: instant valve closure at the dead end of a
single pipe fed from a constant-head reservoir.

Both solvers are given identical physics:
  - Reservoir head  : 150 ft (45.72 m)
  - Pipe             : 3000 ft (914.4 m) long, 12 in (304.8 mm) diam, HW C=130
  - Wave speed       : 4000 ft/s (1219.2 m/s)
  - Initial flow     : 500 GPM  =>  V0 = 1.418 ft/s (0.4324 m/s)
  - Transient event  : instant valve closure at t = 0
  - Analytical check : Joukowsky peak = H_res + a*V0/g

TSNet requires an EPANET .inp file and uses SI units (meters, LPS).
rthym_moc uses US customary (ft, GPM) internally.
Both results are compared in meters.

Usage:
    python examples/benchmark_vs_tsnet.py
"""

import math
import os
import tempfile
import time

import numpy as np

# ── Unit conversions ──────────────────────────────────────────────────────────
FT_TO_M    = 0.3048
IN_TO_MM   = 25.4
GPM_TO_M3S = 6.309e-5   # 1 US gal/min = 6.309e-5 m³/s
G_SI       = 9.81        # m/s²
G_US       = 32.2        # ft/s²
GPM_TO_CFS = 0.002228

# ── Shared test parameters ────────────────────────────────────────────────────
H_RES_FT   = 150.0                         # reservoir head [ft]
L_FT       = 3000.0                        # pipe length [ft]
D_IN       = 12.0                          # pipe diameter [in]
HW_C       = 130.0                         # Hazen-Williams C
Q0_GPM     = 500.0                         # initial flow [GPM]
A_WAVE_FT  = 4000.0                        # wave speed [ft/s]
TOTAL_S    = 3.0                           # simulation period [s]
DT_S       = 0.01                          # time step [s]

# Derived
D_FT       = D_IN / 12.0
A_PIPE_FT2 = math.pi * (D_FT / 2.0) ** 2
V0_FT      = Q0_GPM * GPM_TO_CFS / A_PIPE_FT2

# SI equivalents (for INP file and TSNet)
H_RES_M    = H_RES_FT * FT_TO_M
L_M        = L_FT     * FT_TO_M
D_MM       = D_IN     * IN_TO_MM
A_WAVE_M   = A_WAVE_FT * FT_TO_M
V0_M       = V0_FT * FT_TO_M

# Hazen-Williams friction loss (SI): Hf = 10.67 * L * Q^1.852 / (C^1.852 * D^4.87)
Q0_M3S     = Q0_GPM * GPM_TO_M3S
D_M        = D_IN * FT_TO_M / 12.0 * 12.0 * FT_TO_M  # D_FT → D_M
D_M        = D_FT * FT_TO_M
Hf_M       = (10.67 * L_M * Q0_M3S**1.852
              / (HW_C**1.852 * D_M**4.87))
H_DN_M     = H_RES_M - Hf_M  # downstream reservoir head for ~500 GPM steady state
H_DN_FT    = H_DN_M / FT_TO_M

# Joukowsky analytical peak: ΔH = a·V0/g, baseline = pre-closure head at valve
dH_M       = A_WAVE_M * V0_M / G_SI
H_jouk_M   = H_DN_M  + dH_M   # first-step Joukowsky: baseline = H_DN
H_exp_M    = H_RES_M + dH_M   # transient maximum:    baseline = H_RES (wave sweeps full HGL)

print("=" * 60)
print("  Joukowsky Benchmark Parameters")
print("=" * 60)
print(f"  V0              : {V0_FT:.4f} ft/s  ({V0_M:.4f} m/s)")
print(f"  Wave speed a    : {A_WAVE_FT:.0f} ft/s  ({A_WAVE_M:.1f} m/s)")
print(f"  Friction Hf     : {Hf_M/FT_TO_M:.3f} ft  ({Hf_M:.3f} m)")
print(f"  Downstream H    : {H_DN_M/FT_TO_M:.3f} ft  ({H_DN_M:.3f} m)")
print(f"  Joukowsky ΔH    : {dH_M/FT_TO_M:.2f} ft  ({dH_M:.2f} m)")
print(f"  Joukowsky peak  : {H_jouk_M/FT_TO_M:.2f} ft  ({H_jouk_M:.2f} m)  [H_DN + ΔH, first-step]")
print(f"  Transient max   : {H_exp_M/FT_TO_M:.2f} ft  ({H_exp_M:.2f} m)  [H_RES + ΔH, wave sweeps HGL]")
print()

# ═══════════════════════════════════════════════════════════════════════════════
# 1.  rthym_moc  (C++ core)
# ═══════════════════════════════════════════════════════════════════════════════
print("─" * 60)
print("  1. rthym_moc  (C++ core, R1→P1→V1[closed]→P_stub→R2)")
print("─" * 60)

import rthym_moc as m

solver = m.MOCSolver()

r1 = m.NodeInput()
r1.id = "R1";  r1.type = "PressureBoundary";  r1.head = H_RES_FT

# Inline valve: diameter matches pipe, instantly closed from t=0
v1 = m.NodeInput()
v1.id = "V1";  v1.type = "Valve"
v1.diameter        = D_IN
v1.current_setting = 0.0     # fully closed → K→∞ → Q=0, mirrors TSNet's TCV slam
v1.head            = H_DN_FT # initial pre-closure head at valve location

r2 = m.NodeInput()
r2.id = "R2";  r2.type = "PressureBoundary";  r2.head = H_DN_FT

p1 = m.PipeInput()
p1.id = "P1";  p1.from_node = "R1";  p1.to_node = "V1"
p1.length = L_FT;  p1.diameter = D_IN;  p1.roughness = HW_C
p1.flow_gpm = Q0_GPM  # initial steady-state flow (valve stops it at step 1)

# One-segment stub pipe V1→R2 (same role as TSNet's J1→R2 via TCV)
L_stub_ft = A_WAVE_FT * DT_S   # exactly one MOC segment
p2 = m.PipeInput()
p2.id = "P2";  p2.from_node = "V1";  p2.to_node = "R2"
p2.length = L_stub_ft;  p2.diameter = D_IN;  p2.roughness = HW_C
p2.flow_gpm = 0.0              # no flow through closed valve

solver.add_node(r1);  solver.add_node(v1);  solver.add_node(r2)
solver.add_pipe(p1);  solver.add_pipe(p2)

t0 = time.perf_counter()
# usf_tau = DT_S → alpha=dt/tau=1 → V_bar tracks V instantly → k_u*(V-V_bar)=0
# Disables the Brunone USF filter so this is pure steady-friction MOC,
# matching TSNet which has no unsteady-friction correction.
results = solver.run(TOTAL_S, DT_S, -14.0, DT_S)
t_rthym = time.perf_counter() - t0

H_v1_ft = np.array(results["node_head"]["V1"])
H_v1_m  = H_v1_ft * FT_TO_M

H_step1_rthym  = float(H_v1_ft[0])           # t=dt  (first Joukowsky step)
H_max_rthym    = float(H_v1_ft.max())
err_step1      = abs(H_step1_rthym*FT_TO_M - H_jouk_M) / H_jouk_M * 100.0
err_max        = abs(H_max_rthym  *FT_TO_M - H_exp_M)  / H_exp_M  * 100.0

print(f"  First-step (t=dt)  : {H_step1_rthym:.2f} ft  ({H_step1_rthym*FT_TO_M:.2f} m)  err={err_step1:.2f}% vs Joukowsky")
print(f"  Transient max      : {H_max_rthym:.2f} ft  ({H_max_rthym*FT_TO_M:.2f} m)  err={err_max:.2f}% vs theoretical max")
print(f"  Execution time     : {t_rthym*1000:.2f} ms  ({len(H_v1_ft)} time steps)")
print()

# ═══════════════════════════════════════════════════════════════════════════════
# 2.  TSNet  (pure Python MOC)
# ═══════════════════════════════════════════════════════════════════════════════
print("─" * 60)
print("  2. TSNet  (pure Python, TCV instant closure)")
print("─" * 60)

try:
    import tsnet

    # Build a minimal EPANET INP file (SI / LPS units).
    # Network: R1 ---[P1]--- J1 ---[V1:TCV]--- R2
    # V1 is fully open at t=0, slams shut in one time step.
    # J1 head pre-closure ≈ H_DN_M;  post-closure jumps by a*V0/g.
    inp_content = f"""[TITLE]
Joukowsky Benchmark (rthym_moc vs TSNet)

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

    with tempfile.NamedTemporaryFile(mode='w', suffix='.inp',
                                     delete=False) as f:
        f.write(inp_content)
        inp_path = f.name

    tm = tsnet.network.TransientModel(inp_path)
    os.unlink(inp_path)

    tm.set_wavespeed(A_WAVE_M)   # m/s  (same wave speed as rthym_moc)
    tm.set_time(TOTAL_S, DT_S)   # pass DT_S so TSNet uses ~75 segments not 1

    dt_tsnet = tm.time_step
    print(f"  TSNet time step    : {dt_tsnet:.5f} s")

    # Instant closure: close in one TSNet time step starting at t=0
    tc = dt_tsnet     # closure duration
    ts = 0.0          # start time
    se = 0.0          # end setting (fully closed)
    mc = 1            # linear closure shape
    tm.valve_closure('V1', [tc, ts, se, mc])

    # Steady-state initial conditions
    tm = tsnet.simulation.Initializer(tm, 0.0, 'DD')

    # Transient simulation
    t0 = time.perf_counter()
    tm = tsnet.simulation.MOCSimulator(tm)
    t_tsnet = time.perf_counter() - t0

    # J1 head history (in meters)
    node_J1   = tm.get_node('J1')
    H_J1_m    = np.array(node_J1._head)

    H_step1_tsnet  = float(H_J1_m[1])         # t=dt  (index 0 = initial, 1 = first transient step)
    H_max_tsnet    = float(H_J1_m.max())
    err_ts_step1   = abs(H_step1_tsnet - H_jouk_M) / H_jouk_M * 100.0
    err_ts_max     = abs(H_max_tsnet   - H_exp_M)  / H_exp_M  * 100.0

    print(f"  First-step (t=dt)  : {H_step1_tsnet/FT_TO_M:.2f} ft  ({H_step1_tsnet:.2f} m)  err={err_ts_step1:.2f}% vs Joukowsky")
    print(f"  Transient max      : {H_max_tsnet/FT_TO_M:.2f} ft  ({H_max_tsnet:.2f} m)  err={err_ts_max:.2f}% vs theoretical max")
    print(f"  Execution time     : {t_tsnet*1000:.2f} ms  ({len(H_J1_m)-1} time steps)")
    print()

    # ── Comparison ────────────────────────────────────────────────────────────
    print("=" * 60)
    print("  Comparison Summary")
    print("=" * 60)
    print(f"  Network            : R1 -[P1]- V1[closed] -[P_stub]- R2  (both)")
    print(f"  USF correction     : disabled for both (pure steady-friction MOC)")
    print()
    print(f"  Joukowsky first-step  ({H_jouk_M/FT_TO_M:.2f} ft analytical):")
    print(f"    rthym_moc  {H_step1_rthym:.2f} ft   err={err_step1:.2f}%")
    print(f"    TSNet      {H_step1_tsnet/FT_TO_M:.2f} ft   err={err_ts_step1:.2f}%")
    print()
    print(f"  Transient max ({H_exp_M/FT_TO_M:.2f} ft theoretical):")
    print(f"    rthym_moc  {H_max_rthym:.2f} ft   err={err_max:.2f}%")
    print(f"    TSNet      {H_max_tsnet/FT_TO_M:.2f} ft   err={err_ts_max:.2f}%")
    print()
    if t_rthym > 0:
        ratio = t_tsnet / t_rthym
        print(f"  Speed ratio        : {ratio:.0f}x  (rthym_moc vs TSNet)")
    print()

    # ── Time-history RMS comparison (first wave cycle) ────────────────────────
    t_rthym_axis   = np.arange(1, len(H_v1_m) + 1) * DT_S
    t_tsnet_axis   = np.array(tm.simulation_timestamps)
    H_tsnet_interp = np.interp(t_rthym_axis, t_tsnet_axis, H_J1_m)
    mask           = t_rthym_axis <= 1.5
    rms_diff_m     = float(np.sqrt(np.mean((H_v1_m[mask] - H_tsnet_interp[mask])**2)))
    print(f"  RMS head diff (0–1.5 s): {rms_diff_m/FT_TO_M:.3f} ft  ({rms_diff_m:.3f} m)")

except Exception as exc:
    print(f"  TSNet run failed: {exc}")
    import traceback
    traceback.print_exc()
