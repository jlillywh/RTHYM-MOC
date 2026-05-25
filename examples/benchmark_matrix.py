# Copyright (c) 2026 Jason Lillywhite <jason@lillywhitewater.com>
# SPDX-License-Identifier: MIT
"""
Performance matrix: rthym_moc vs TSNet on the Joukowsky instant-closure case.

Sweeps time step and simulation duration so each row reports wall-clock time for
a different grid size (step count and MOC segment count). Use this for papers,
README speed claims, or local hardware checks.

Usage (from repository root):
    pip install tsnet==0.3.1
    python examples/benchmark_matrix.py

Optional flags:
    --warmup 2       discard this many runs before timing (default 1)
    --repeat 3       median over this many timed runs (default 3)
    --cases 0,1,2    comma-separated indices into the built-in case list
    --skip-tsnet     rthym_moc timings only
"""

from __future__ import annotations

import argparse
import math
import os
import platform
import statistics
import sys
import tempfile
import time
from dataclasses import dataclass

import numpy as np

import rthym_moc as m

FT_TO_M = 0.3048
IN_TO_MM = 25.4
GPM_TO_M3S = 6.309e-5
GPM_TO_CFS = 0.002228
G_SI = 9.81

H_RES_FT = 150.0
L_FT = 3000.0
D_IN = 12.0
HW_C = 130.0
Q0_GPM = 500.0
A_WAVE_FT = 4000.0

D_FT = D_IN / 12.0
A_PIPE_FT2 = math.pi * (D_FT / 2.0) ** 2
V0_FT = Q0_GPM * GPM_TO_CFS / A_PIPE_FT2

H_RES_M = H_RES_FT * FT_TO_M
L_M = L_FT * FT_TO_M
D_MM = D_IN * IN_TO_MM
A_WAVE_M = A_WAVE_FT * FT_TO_M
V0_M = V0_FT * FT_TO_M
Q0_M3S = Q0_GPM * GPM_TO_M3S
D_M = D_FT * FT_TO_M
Hf_M = 10.67 * L_M * Q0_M3S**1.852 / (HW_C**1.852 * D_M**4.87)
H_DN_M = H_RES_M - Hf_M
H_DN_FT = H_DN_M / FT_TO_M


@dataclass(frozen=True)
class MatrixCase:
    """One grid-resolution row in the performance matrix."""

    label: str
    dt_s: float
    total_s: float

    @property
    def n_steps(self) -> int:
        return int(round(self.total_s / self.dt_s))

    @property
    def n_segments_p1(self) -> int:
        """Approximate MOC segments on the 3000 ft main pipe (Courant ≈ 1)."""
        return max(1, int(round(L_FT / (A_WAVE_FT * self.dt_s))))


MATRIX_CASES: list[MatrixCase] = [
    MatrixCase("coarse", 0.02, 3.0),
    MatrixCase("standard", 0.01, 3.0),
    MatrixCase("fine", 0.005, 3.0),
    MatrixCase("standard-long", 0.01, 6.0),
    MatrixCase("standard-extended", 0.01, 10.0),
    MatrixCase("fine-long", 0.005, 6.0),
]


def _median_seconds(run_fn, warmup: int, repeat: int) -> float:
    for _ in range(warmup):
        run_fn()
    samples = [run_fn() for _ in range(repeat)]
    return statistics.median(samples)


def _build_rthym_solver(dt_s: float) -> m.MOCSolver:
    solver = m.MOCSolver()

    r1 = m.NodeInput()
    r1.id = "R1"
    r1.type = "PressureBoundary"
    r1.head = H_RES_FT

    v1 = m.NodeInput()
    v1.id = "V1"
    v1.type = "Valve"
    v1.diameter = D_IN
    v1.current_setting = 0.0
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
    p2.length = A_WAVE_FT * dt_s
    p2.diameter = D_IN
    p2.roughness = HW_C
    p2.flow_gpm = 0.0

    solver.add_node(r1)
    solver.add_node(v1)
    solver.add_node(r2)
    solver.add_pipe(p1)
    solver.add_pipe(p2)
    return solver


def _run_rthym(case: MatrixCase, warmup: int, repeat: int) -> tuple[float, np.ndarray]:
    solver = _build_rthym_solver(case.dt_s)
    last_results: dict | None = None

    def _timed_run() -> float:
        nonlocal last_results
        t0 = time.perf_counter()
        last_results = solver.run(case.total_s, case.dt_s, -14.0, case.dt_s)
        return time.perf_counter() - t0

    elapsed = _median_seconds(_timed_run, warmup=warmup, repeat=repeat)
    assert last_results is not None
    h_ft = np.array(last_results["node_head"]["V1"])
    return elapsed, h_ft


def _inp_content() -> str:
    return f"""[TITLE]
Joukowsky Benchmark Matrix

[OPTIONS]
 Units                LPS
 Headloss             H-W
 Trials               40
 Accuracy             0.001
 Unbalanced           Continue 10
 Quality              None

[JUNCTIONS]
 J1   0.000   0.000   ;

[RESERVOIRS]
 R1   {H_RES_M:.5f}   ;
 R2   {H_DN_M:.5f}   ;

[PIPES]
 P1  R1     J1     {L_M:.3f}  {D_MM:.3f}  {HW_C:.0f}    0      Open

[VALVES]
 V1  J1     R2     {D_MM:.3f}  TCV   0.001    0

[REPORT]
 Status  No
 Summary No

[END]
"""


def _run_tsnet(case: MatrixCase, warmup: int, repeat: int) -> tuple[float, np.ndarray, np.ndarray]:
    import tsnet

    # TSNet mutates the model in place; rebuild for each timed repeat.
    def _prepare() -> object:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".inp", delete=False) as f:
            f.write(_inp_content())
            path = f.name
        try:
            model = tsnet.network.TransientModel(path)
        finally:
            os.unlink(path)
        model.set_wavespeed(A_WAVE_M)
        model.set_time(case.total_s, case.dt_s)
        dtc = model.time_step
        model.valve_closure("V1", [dtc, 0.0, 0.0, 1])
        return tsnet.simulation.Initializer(model, 0.0, "DD")

    def _timed_run_clean() -> float:
        prepared = _prepare()
        t0 = time.perf_counter()
        finished = tsnet.simulation.MOCSimulator(prepared)
        return time.perf_counter() - t0

    for _ in range(warmup):
        _timed_run_clean()

    samples = []
    last_heads: np.ndarray | None = None
    last_times: np.ndarray | None = None
    for _ in range(repeat):
        prepared = _prepare()
        t0 = time.perf_counter()
        finished = tsnet.simulation.MOCSimulator(prepared)
        samples.append(time.perf_counter() - t0)
        last_heads = np.array(finished.get_node("J1")._head)
        last_times = np.array(finished.simulation_timestamps)

    elapsed = statistics.median(samples)
    assert last_heads is not None and last_times is not None
    return elapsed, last_heads, last_times


def _rms_first_cycle(
    h_rthym_ft: np.ndarray,
    h_tsnet_m: np.ndarray,
    dt_s: float,
    t_tsnet_s: np.ndarray,
) -> float:
    t_axis = np.arange(1, len(h_rthym_ft) + 1) * dt_s
    h_rthym_m = h_rthym_ft * FT_TO_M
    h_interp = np.interp(t_axis, t_tsnet_s, h_tsnet_m)
    mask = t_axis <= 1.5
    return float(np.sqrt(np.mean((h_rthym_m[mask] - h_interp[mask]) ** 2)) / FT_TO_M)


@dataclass
class MatrixRow:
    case: MatrixCase
    rthym_ms: float
    tsnet_ms: float | None
    speedup: float | None
    rms_ft: float | None
    err_step1_pct: float


def _run_row(
    case: MatrixCase,
    *,
    warmup: int,
    repeat: int,
    run_tsnet: bool,
) -> MatrixRow:
    rthym_s, h_rthym = _run_rthym(case, warmup=warmup, repeat=repeat)
    dH_m = A_WAVE_M * V0_M / G_SI
    h_jouk_m = H_DN_M + dH_m
    err_step1 = abs(float(h_rthym[0]) * FT_TO_M - h_jouk_m) / h_jouk_m * 100.0

    tsnet_ms = None
    speedup = None
    rms_ft = None
    if run_tsnet:
        try:
            tsnet_s, h_tsnet, t_tsnet = _run_tsnet(case, warmup=warmup, repeat=repeat)
            tsnet_ms = tsnet_s * 1000.0
            if rthym_s > 0:
                speedup = tsnet_s / rthym_s
            rms_ft = _rms_first_cycle(h_rthym, h_tsnet, case.dt_s, t_tsnet)
        except Exception as exc:
            print(f"  [{case.label}] TSNet failed: {exc}", file=sys.stderr)

    return MatrixRow(
        case=case,
        rthym_ms=rthym_s * 1000.0,
        tsnet_ms=tsnet_ms,
        speedup=speedup,
        rms_ft=rms_ft,
        err_step1_pct=err_step1,
    )


def _print_header(version: str) -> None:
    print("=" * 88)
    print("  RTHYM-MOC vs TSNet — Joukowsky performance matrix")
    print("=" * 88)
    print(f"  rthym_moc {version}")
    print(f"  Platform  {platform.platform()}")
    print(f"  Python    {sys.version.split()[0]}")
    print(
        "  Physics   instant closure; USF disabled (usf_tau = dt); "
        f"a = {A_WAVE_FT:.0f} ft/s; L = {L_FT:.0f} ft"
    )
    print()


def _print_table(rows: list[MatrixRow], *, include_tsnet: bool) -> None:
    if include_tsnet:
        header = (
            f"{'Case':<18} {'dt(s)':>7} {'T(s)':>6} {'Steps':>6} {'Segs':>5} "
            f"{'rthym(ms)':>10} {'TSNet(ms)':>10} {'Speedup':>8} "
            f"{'RMS(ft)':>8} {'Step1%':>7}"
        )
    else:
        header = (
            f"{'Case':<18} {'dt(s)':>7} {'T(s)':>6} {'Steps':>6} {'Segs':>5} "
            f"{'rthym(ms)':>10} {'Step1%':>7}"
        )
    print(header)
    print("-" * len(header))

    speedups: list[float] = []
    for row in rows:
        c = row.case
        if include_tsnet and row.tsnet_ms is not None:
            sp = f"{row.speedup:.0f}x" if row.speedup is not None else "n/a"
            rms = f"{row.rms_ft:.3f}" if row.rms_ft is not None else "n/a"
            print(
                f"{c.label:<18} {c.dt_s:7.4f} {c.total_s:6.1f} {c.n_steps:6d} "
                f"{c.n_segments_p1:5d} {row.rthym_ms:10.2f} {row.tsnet_ms:10.2f} "
                f"{sp:>8} {rms:>8} {row.err_step1_pct:7.2f}"
            )
            if row.speedup is not None:
                speedups.append(row.speedup)
        else:
            print(
                f"{c.label:<18} {c.dt_s:7.4f} {c.total_s:6.1f} {c.n_steps:6d} "
                f"{c.n_segments_p1:5d} {row.rthym_ms:10.2f} {row.err_step1_pct:7.2f}"
            )

    print()
    if speedups:
        print(
            f"  Speedup range: {min(speedups):.0f}x – {max(speedups):.0f}x "
            f"(median {statistics.median(speedups):.0f}x)"
        )
    print("  Step1% = first-step Joukowsky head error vs analytical (physics sanity).")
    print("  Segs   ≈ round(L / (a·dt)) on the 3000 ft main pipe.")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warmup", type=int, default=1, help="warm-up runs per case")
    parser.add_argument("--repeat", type=int, default=3, help="timed runs per case (median)")
    parser.add_argument(
        "--cases",
        type=str,
        default="",
        help="comma-separated case indices (default: all)",
    )
    parser.add_argument("--skip-tsnet", action="store_true", help="rthym_moc only")
    args = parser.parse_args()

    if args.cases.strip():
        indices = [int(x.strip()) for x in args.cases.split(",")]
        cases = [MATRIX_CASES[i] for i in indices]
    else:
        cases = list(MATRIX_CASES)

    version = getattr(m, "__version__", "unknown")
    _print_header(version)

    run_tsnet = not args.skip_tsnet
    if run_tsnet:
        try:
            import tsnet  # noqa: F401
        except ImportError:
            print("  TSNet not installed; use: pip install tsnet==0.3.1", file=sys.stderr)
            print("  Continuing with rthym_moc timings only.\n")
            run_tsnet = False

    rows: list[MatrixRow] = []
    for case in cases:
        print(f"  Running {case.label} (dt={case.dt_s} s, T={case.total_s} s) …")
        row = _run_row(case, warmup=args.warmup, repeat=args.repeat, run_tsnet=run_tsnet)
        rows.append(row)

    print()
    _print_table(rows, include_tsnet=run_tsnet)


if __name__ == "__main__":
    main()
