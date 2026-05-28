# Copyright (c) 2026 Jason Lillywhite <jason@lillywhitewater.com>
# SPDX-License-Identifier: MIT
"""SI-unit quickstart for rthym_moc.

The solver core still uses US customary units internally.  The helpers in
``rthym_moc.units`` convert SI inputs at construction time and convert result
series back to SI after ``solver.run()``.
"""

import numpy as np

import rthym_moc


solver = rthym_moc.MOCSolver()

solver.add_node(rthym_moc.node_si("R1", "PressureBoundary", head_m=45.72))
solver.add_node(
    rthym_moc.node_si(
        "V1",
        "Valve",
        elevation_m=0.0,
        diameter_mm=304.8,
        current_setting=0.0,
    )
)
solver.add_node(rthym_moc.node_si("R2", "PressureBoundary", head_m=0.0))

solver.add_pipe(
    rthym_moc.pipe_si(
        "P1",
        "R1",
        "V1",
        length_m=914.4,
        diameter_mm=304.8,
        roughness=130.0,
        flow_m3s=rthym_moc.flow_gpm_to_m3s(500.0),
    )
)
solver.add_pipe(
    rthym_moc.pipe_si(
        "P2",
        "V1",
        "R2",
        length_m=30.48,
        diameter_mm=304.8,
        roughness=130.0,
        flow_m3s=rthym_moc.flow_gpm_to_m3s(500.0),
    )
)

results_si = rthym_moc.results_to_si(solver.run(total_time=4.0, dt=0.01))

time_s = results_si["time"]
head_m = results_si["node_head_m"]["V1"]
pressure_kpa = results_si["node_pressure_kpa"]["V1"]
flow_m3s = results_si["pipe_flow_m3s"]["P1"]

print("=" * 56)
print("  SI Quickstart")
print("=" * 56)
print(f"  Time steps             : {len(time_s)}")
print(f"  Peak valve head        : {np.max(head_m):.2f} m")
print(f"  Peak valve pressure    : {np.max(pressure_kpa):.2f} kPa")
print(f"  Minimum P1 flow        : {np.min(flow_m3s):.4f} m^3/s")
print("=" * 56)
