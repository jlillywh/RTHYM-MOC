#!/usr/bin/env python3
"""Validate a digitized Bergant Adelaide valve trace CSV before committing or running pytest."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TESTS = REPO / "tests"
sys.path.insert(0, str(TESTS))

from bergant_adelaide_verification_utils import (  # noqa: E402
    SEVERE_VALVE_TRACE_CSV,
    load_valve_trace_csv,
    validate_valve_trace_csv,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "csv",
        nargs="?",
        type=Path,
        default=SEVERE_VALVE_TRACE_CSV,
        help="Path to trace CSV (default: tests/bergant_adelaide_severe_valve_trace_reference.csv)",
    )
    parser.add_argument("--min-points", type=int, default=40)
    args = parser.parse_args()

    if not args.csv.is_file():
        print(f"File not found: {args.csv}")
        print("Copy tests/bergant_adelaide_severe_valve_trace_reference.csv.example and digitize Fig. 4.")
        print("See docs/bergant_adelaide_verification.md")
        return 1

    errors = validate_valve_trace_csv(args.csv, min_points=args.min_points)
    if errors:
        print("Validation FAILED:")
        for err in errors:
            print(f"  - {err}")
        return 1

    data = load_valve_trace_csv(args.csv)
    t = data["t_s"]
    p = data["p_gauge_kPa"]
    print(f"OK: {args.csv.name}")
    print(f"  points: {len(t)}")
    print(f"  time: {t[0]:.4f} – {t[-1]:.4f} s")
    print(f"  p_gauge: {data['p_gauge_kPa'].min():.1f} – {data['p_gauge_kPa'].max():.1f} kPa")
    if data["metadata"]:
        print("  metadata:")
        for key, value in data["metadata"].items():
            print(f"    {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
