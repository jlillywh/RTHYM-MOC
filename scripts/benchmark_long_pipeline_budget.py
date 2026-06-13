#!/usr/bin/env python3
"""Run LP-PERF-01 wall-clock benchmark for long-pipeline grid scaling (Phase 4).

See docs/long_pipeline_phase0_baseline.md §4.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests"))

from long_pipeline_perf_utils import (  # noqa: E402
    DEFAULT_BUDGET_S,
    DEFAULT_DT_S,
    DEFAULT_LENGTH_MI,
    DEFAULT_MAX_DISTORTION,
    DEFAULT_MAX_SEGMENTS,
    DEFAULT_TOTAL_TIME_S,
    format_lp_perf_report,
    run_lp_perf_01_benchmark,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LP-PERF-01 long-pipeline performance probe")
    parser.add_argument("--length-mi", type=float, default=DEFAULT_LENGTH_MI)
    parser.add_argument("--dt", type=float, default=DEFAULT_DT_S)
    parser.add_argument("--total-time", type=float, default=DEFAULT_TOTAL_TIME_S)
    parser.add_argument("--budget-s", type=float, default=DEFAULT_BUDGET_S)
    parser.add_argument("--max-segments", type=int, default=DEFAULT_MAX_SEGMENTS)
    parser.add_argument("--max-distortion", type=float, default=DEFAULT_MAX_DISTORTION)
    parser.add_argument("--runs", type=int, default=3, help="Timed runs (median reported)")
    parser.add_argument("--warmup", type=int, default=1, help="Untimed warmup runs")
    parser.add_argument(
        "--uncapped",
        action="store_true",
        help="Disable max_segments_per_pipe (informational timing only)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 when budget_met is False (Phase 4 release gate)",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    metrics = run_lp_perf_01_benchmark(
        length_mi=args.length_mi,
        dt_s=args.dt,
        total_time_s=args.total_time,
        budget_s=args.budget_s,
        max_segments_per_pipe=args.max_segments,
        max_wave_speed_distortion=args.max_distortion,
        apply_grid_cap=not args.uncapped,
        num_runs=max(1, args.runs),
        num_warmup=max(0, args.warmup),
    )
    print(format_lp_perf_report(metrics))
    if args.strict and not metrics.budget_met:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
