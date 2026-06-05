#!/usr/bin/env python3
"""Probe long-pipeline performance for Phase 0 budget calibration.

Usage (from repo root, after ``pip install -e .``):

    python scripts/benchmark_long_pipeline_budget.py
    python scripts/benchmark_long_pipeline_budget.py --length-mi 20 --dt 0.001 --total-time 60

Prints segment count, step count, wall time, and whether the run meets the
documented budget in docs/long_pipeline_phase0_baseline.md §4.
"""

from __future__ import annotations

import argparse
import time

import rthym_moc as m

MILE_FT = 5280.0
BUDGET_S = 30.0


def _adjusted_segments(length_ft: float, dt: float, a0: float = 4000.0) -> int:
    return max(1, round(length_ft / (a0 * dt)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--length-mi", type=float, default=20.0)
    parser.add_argument("--dt", type=float, default=0.001)
    parser.add_argument("--total-time", type=float, default=60.0)
    parser.add_argument("--budget-s", type=float, default=BUDGET_S)
    args = parser.parse_args()

    length_ft = args.length_mi * MILE_FT
    n_seg = _adjusted_segments(length_ft, args.dt)
    n_steps = int(args.total_time / args.dt)

    solver = m.MOCSolver()
    r1 = m.NodeInput()
    r1.id = "R1"
    r1.type = "PressureBoundary"
    r1.head = 500.0
    r2 = m.NodeInput()
    r2.id = "R2"
    r2.type = "PressureBoundary"
    r2.head = 100.0
    pipe = m.PipeInput()
    pipe.id = "P1"
    pipe.from_node = "R1"
    pipe.to_node = "R2"
    pipe.length = length_ft
    pipe.diameter = 24.0
    pipe.roughness = 130.0
    pipe.flow_gpm = 3000.0
    pipe.youngs_modulus = 0.0
    solver.add_node(r1)
    solver.add_node(r2)
    solver.add_pipe(pipe)
    # Steady run — measures raw MOC step cost (no valve / transient event required).

    # Warmup (grid build + one short run)
    solver.run(total_time=args.dt * 10, dt=args.dt)

    t0 = time.perf_counter()
    results = solver.run(total_time=args.total_time, dt=args.dt)
    elapsed = time.perf_counter() - t0

    ok = elapsed <= args.budget_s
    print("Long-pipeline performance probe")
    print(f"  length_mi     : {args.length_mi}")
    print(f"  length_ft     : {length_ft:.0f}")
    print(f"  dt_s          : {args.dt}")
    print(f"  segments N    : {n_seg}  (interior points {max(0, n_seg - 1)})")
    print(f"  time steps    : {len(results['time'])} (expected ~{n_steps})")
    print(f"  elapsed_s     : {elapsed:.3f}")
    print(f"  budget_s      : {args.budget_s}")
    print(f"  budget_met    : {ok}")
    if not ok:
        ratio = n_seg / 2000.0
        print(f"  note          : Phase 4 grid cap (~2000 segs) may cut runtime ~{ratio:.0f}x")


if __name__ == "__main__":
    main()
