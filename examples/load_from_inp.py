"""
examples/load_from_inp.py
~~~~~~~~~~~~~~~~~~~~~~~~~
Load a network from an EPANET .inp file and run a waterhammer transient.

Creates temporary .inp files on the fly — no external files required.

This script demonstrates two patterns:

Part 1 — Dead-end wave reflection
  Network: R1 (H=150 ft) --[P1: 3000 ft, 12 in, HW=130]--> J1 (demand=0)
  J1 has no outflow pipe -> the MOC dead-end BC (Q=0 forced at t=0+)
  produces an immediate Joukowsky pressure rise.  Expected peak ~324 ft.

Part 2 — TCV valve closure (demonstrates VALVE section loading)
  Network: R1 (H=150 ft) --[P1: 3000 ft]--> J1 --[V1 TCV]--> R2 (H=148 ft)
  R2 head is set to match friction losses so Q0=500 GPM is the steady state.
  A linear closure schedule (T_c=0.5 s) drives the valve to full shut.
  Expected Joukowsky peak ~324–326 ft at _VALVE_V1.

Note: both simulations use default run() settings (k_bru=0, steady-friction only).
Unsteady friction (Brunone) can be enabled via k_bru=<0.02..0.15>.

Usage
-----
    python examples/load_from_inp.py

Install wntr for automatic steady-state initial flows:
    pip install wntr   or   pip install 'rthym-moc[inp]'
"""

import math
import os
import tempfile

import numpy as np

import rthym_moc

# Shared physical parameters
H_RES_FT  = 150.0
L_FT      = 3000.0
D_IN      = 12.0
HW_C      = 130.0
Q0_GPM    = 500.0
A_WAVE_FT = 4000.0
DT        = 0.01

D_FT   = D_IN / 12.0
A_PIPE = math.pi * (D_FT / 2.0) ** 2
V0_FT  = Q0_GPM * rthym_moc.GPM_TO_CFS / A_PIPE
DH_JOUKOWSKY = A_WAVE_FT * V0_FT / rthym_moc.G_FT_S2

# Friction head loss in P1 at Q0 (Hazen-Williams)
Q0_M3S = Q0_GPM * 6.309e-5
L_M    = L_FT * 0.3048
D_M    = D_FT * 0.3048
Hf_M   = 10.67 * L_M * Q0_M3S**1.852 / (HW_C**1.852 * D_M**4.87)
Hf_FT  = Hf_M / 0.3048           # ~2.1 ft
H_DN_FT = H_RES_FT - Hf_FT       # downstream head for steady-state balance


# =============================================================================
# Part 1 -- Dead-end wave reflection
# =============================================================================
INP_DEAD_END = """[TITLE]
Dead-end wave reflection

[JUNCTIONS]
;ID   Elev   BaseDemand
J1    0      0

[RESERVOIRS]
;ID   Head
R1    150.0

[TANKS]
[PIPES]
;ID   Node1  Node2  Length  Diameter  Roughness  MinorLoss  Status
P1    R1     J1     3000    12        130        0          Open

[PUMPS]
[VALVES]
[CURVES]

[OPTIONS]
 Units      GPM
 Headloss   H-W

[END]
"""

print("=" * 62)
print("  EPANET .inp Import -- Part 1: Dead-end Wave Reflection")
print("=" * 62)
print(f"  Q0 = {Q0_GPM:.0f} GPM  |  V0 = {V0_FT:.3f} ft/s  |  a = {A_WAVE_FT:.0f} ft/s")
print(f"  Joukowsky dH = {DH_JOUKOWSKY:.2f} ft")
# The MOC peak slightly exceeds H_DN+ΔH because the wave sweeps the full
# pipe HGL (H_RES side) before the relief wave returns; theoretical max
# = H_RES + ΔH.  We compare against H_DN + ΔH as the lower-bound estimate.
print(f"  Expected Joukowsky peak at J1 ≥ {H_RES_FT - Hf_FT + DH_JOUKOWSKY:.1f} ft")
print()

with tempfile.NamedTemporaryFile(mode="w", suffix=".inp", delete=False) as f:
    f.write(INP_DEAD_END)
    path1 = f.name

try:
    solver1 = rthym_moc.load_inp(path1, use_wntr=True,
                                  initial_flows={"P1": Q0_GPM})
    results1 = solver1.run(total_time=9.0, dt=DT)
    t1   = np.array(results1["time"])
    H_J1 = np.array(results1["node_head"]["J1"])
    Q_P1 = np.array(results1["pipe_flow_gpm"]["P1"])

    print(f"  Nodes  : {sorted(results1['node_head'].keys())}")
    print(f"  Pipes  : {sorted(results1['pipe_flow_gpm'].keys())}")
    print(f"  Initial head  J1 : {H_J1[0]:.2f} ft")
    print(f"  Peak head     J1 : {H_J1.max():.2f} ft  at t = {t1[H_J1.argmax()]:.3f} s")
    print(f"  Initial flow  P1 : {Q_P1[0]:.1f} GPM")
    err1 = abs(H_J1.max() - (H_RES_FT - Hf_FT + DH_JOUKOWSKY)) / DH_JOUKOWSKY * 100.0
    print(f"  Joukowsky error  : {err1:.2f} %  [{'PASS' if err1 < 5.0 else 'NOTE'}]")
    print()
finally:
    os.unlink(path1)


# =============================================================================
# Part 2 -- TCV valve closure (VALVE section loading)
# =============================================================================
# R2 head = R1 - Hf(P1) so Q0=500 GPM is the steady state.
# The TCV valve carries negligible head loss at Km=0.001.
INP_VALVE = f"""[TITLE]
TCV valve closure

[JUNCTIONS]
;ID   Elev   BaseDemand
J1    0      0

[RESERVOIRS]
;ID   Head
R1    {H_RES_FT:.3f}
R2    {H_DN_FT:.3f}

[TANKS]
[PIPES]
;ID   Node1  Node2  Length  Diameter  Roughness  MinorLoss  Status
P1    R1     J1     3000    12        130        0          Open

[PUMPS]
[VALVES]
;ID   Node1  Node2  Diameter  Type  Setting  MinorLoss
V1    J1     R2     12        TCV   0.001    0

[CURVES]

[OPTIONS]
 Units      GPM
 Headloss   H-W

[END]
"""

print("=" * 62)
print("  EPANET .inp Import -- Part 2: TCV Valve Closure")
print("=" * 62)
print(f"  R1={H_RES_FT:.1f} ft  R2={H_DN_FT:.2f} ft  (balanced for Q0={Q0_GPM:.0f} GPM)")
print(f"  T_c=0.5 s  (<2L/a=1.5 s -> rapid closure)")
print(f"  Expected Joukowsky peak at _VALVE_V1 = {H_DN_FT + DH_JOUKOWSKY:.1f} ft")
print()

with tempfile.NamedTemporaryFile(mode="w", suffix=".inp", delete=False) as f:
    f.write(INP_VALVE)
    path2 = f.name

try:
    # Valve stub flows use the *original EPANET link ID* "V1" as the key,
    # not the generated pipe IDs (_P_V1_up / _P_V1_dn).
    solver2 = rthym_moc.load_inp(
        path2,
        use_wntr=True,
        initial_flows={"P1": Q0_GPM, "V1": Q0_GPM},
    )

    # load_inp() maps EPANET valve "V1" -> rthym_moc node "_VALVE_V1"
    T_c     = 0.5
    t_sched = np.arange(0.0, 5.0 + DT, DT)
    pct     = np.clip(100.0 * (1.0 - t_sched / T_c), 0.0, 100.0)
    solver2.set_valve_schedule("_VALVE_V1", list(zip(t_sched.tolist(), pct.tolist())))

    results2 = solver2.run(total_time=5.0, dt=DT)
    t2   = np.array(results2["time"])
    H_V1 = np.array(results2["node_head"]["_VALVE_V1"])
    Q2P1 = np.array(results2["pipe_flow_gpm"]["P1"])

    print(f"  Nodes  : {sorted(results2['node_head'].keys())}")
    print(f"  Pipes  : {sorted(results2['pipe_flow_gpm'].keys())}")
    print(f"  Initial head _VALVE_V1 : {H_V1[0]:.2f} ft")
    print(f"  Peak head   _VALVE_V1  : {H_V1.max():.2f} ft  at t = {t2[H_V1.argmax()]:.3f} s")
    print(f"  Initial flow P1        : {Q2P1[0]:.1f} GPM")
    err2 = abs(H_V1.max() - (H_DN_FT + DH_JOUKOWSKY)) / DH_JOUKOWSKY * 100.0
    print(f"  Joukowsky error        : {err2:.2f} %  [{'PASS' if err2 < 5.0 else 'NOTE'}]")

    try:
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(2, 2, figsize=(12, 7), sharex="col")
        axes[0, 0].plot(t1, H_J1)
        axes[0, 0].axhline(H_RES_FT - Hf_FT + DH_JOUKOWSKY, color="r",
                            ls="--", label="Joukowsky peak")
        axes[0, 0].set_title("Part 1 -- Dead-end J1 head (ft)")
        axes[0, 0].legend(fontsize=8)
        axes[1, 0].plot(t1, Q_P1, color="tab:orange")
        axes[1, 0].set_ylabel("Flow P1 (GPM)")
        axes[1, 0].set_xlabel("Time (s)")
        axes[0, 1].plot(t2, H_V1)
        axes[0, 1].axhline(H_DN_FT + DH_JOUKOWSKY, color="r",
                            ls="--", label="Joukowsky peak")
        axes[0, 1].set_title("Part 2 -- Valve _VALVE_V1 head (ft)")
        axes[0, 1].legend(fontsize=8)
        axes[1, 1].plot(t2, Q2P1, color="tab:orange")
        axes[1, 1].set_xlabel("Time (s)")
        plt.tight_layout()
        plt.savefig("load_from_inp_result.png", dpi=120)
        print("\n  Plot saved to load_from_inp_result.png")
    except ImportError:
        pass

    print("=" * 62)
finally:
    os.unlink(path2)
