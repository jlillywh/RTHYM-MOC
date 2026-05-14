"""
basic_example.py – Classic Joukowsky waterhammer benchmark.

Topology
--------
  Tank (H=150 ft)  ──────────  P1 (3000 ft, 12 in)  ──────────  Valve ──  Tank (H=0)

The valve is suddenly closed at t=0 from fully open.  The expected Joukowsky
pressure rise at the valve is:

    ΔH = a·ΔV / g  ≈ 4000 ft/s × (V_0 / 32.2)

For V_0 ≈ 1.5 ft/s this gives ΔH ≈ 186 ft, so the valve head spikes from
~150 ft to ~336 ft before the wave reflects from the reservoir.
"""
import numpy as np
import rthym_moc

# ── Network topology ──────────────────────────────────────────────────────────
solver = rthym_moc.MOCSolver()

solver.add_node(rthym_moc.NodeInput(id="R1",   type="PressureBoundary",
                                     elevation=0.0, head=150.0))
solver.add_node(rthym_moc.NodeInput(id="V1",   type="Valve",
                                     elevation=0.0, diameter=12.0,
                                     current_setting=0.0))   # <-- slammed shut
solver.add_node(rthym_moc.NodeInput(id="R2",   type="PressureBoundary",
                                     elevation=0.0, head=0.0))

# Initial steady-state flow through a 12-in pipe, 3000 ft long, C=130 HW
# Estimated from Hazen-Williams: Q ≈ 500 GPM gives ~150 ft Hf → ≈ correct
solver.add_pipe(rthym_moc.PipeInput(
    id="P1",
    from_node="R1", to_node="V1",
    length=3000.0, diameter=12.0,
    roughness=130.0, flow_gpm=500.0,
))
solver.add_pipe(rthym_moc.PipeInput(
    id="P2",
    from_node="V1", to_node="R2",
    length=100.0, diameter=12.0,
    roughness=130.0, flow_gpm=500.0,
))

# ── Run 4 seconds of transient ────────────────────────────────────────────────
results = solver.run(total_time=4.0, dt=0.01)

time   = results["time"]
# Upstream face of valve (last node of P1)
H_up   = results["node_head"]["V1"]
P_up   = results["node_pressure"]["V1"]
Q_P1   = results["pipe_flow_gpm"]["P1"]

# ── Expected Joukowsky peak ───────────────────────────────────────────────────
# V_0 = Q_0 / A   (ft/s)
D_ft   = 12.0 / 12.0               # ft
A_pipe = np.pi * (D_ft / 2.0) ** 2 # ft²
Q0_cfs = 500.0 * rthym_moc.GPM_TO_CFS
V0     = Q0_cfs / A_pipe
# Adjusted wave speed (grid-dependent, ~4000 ft/s for rigid pipe)
a_approx = 4000.0                   # ft/s
dH_joukowsky = a_approx * V0 / rthym_moc.G_FT_S2
H_expected = 150.0 + dH_joukowsky   # initial head + Joukowsky rise

print("=" * 56)
print("  Classic Joukowsky Waterhammer Benchmark")
print("=" * 56)
print(f"  Initial velocity V0       : {V0:.3f} ft/s")
print(f"  Wave speed (approx)       : {a_approx:.0f} ft/s")
print(f"  Joukowsky ΔH              : {dH_joukowsky:.1f} ft")
print(f"  Expected peak head        : {H_expected:.1f} ft")
print(f"  Simulated peak head       : {np.max(H_up):.1f} ft")
print(f"  Time steps                : {len(time)}")
print("=" * 56)

# ── Optional: plot ────────────────────────────────────────────────────────────
try:
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 1, figsize=(9, 6), sharex=True)

    axes[0].plot(time, H_up,  label="Head at valve (ft)", color="steelblue")
    axes[0].axhline(H_expected, ls="--", color="crimson",
                    label=f"Joukowsky peak = {H_expected:.0f} ft")
    axes[0].set_ylabel("Head (ft)")
    axes[0].legend()
    axes[0].set_title("Waterhammer: Instantaneous Valve Closure")
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(time, Q_P1, label="Flow in P1 (GPM)", color="forestgreen")
    axes[1].set_ylabel("Flow (GPM)")
    axes[1].set_xlabel("Time (s)")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig("waterhammer_result.png", dpi=150)
    print("  Plot saved to waterhammer_result.png")
except ImportError:
    print("  (matplotlib not available – skipping plot)")
