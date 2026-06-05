#!/usr/bin/env python3
"""Overlay digitized He Fig. 4 trace on rthym-moc DVCM simulation (completion helper)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TESTS = REPO / "tests"
sys.path.insert(0, str(TESTS))

from bergant_adelaide_verification_utils import (  # noqa: E402
    CASE_LABELS,
    SEVERE_VALVE_TRACE_CSV,
    evaluate_bergant_valve_trace,
    load_reference,
    load_valve_trace_csv,
    run_bergant_case,
    validate_valve_trace_csv,
    valve_gauge_pressure_kpa,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv",
        type=Path,
        default=SEVERE_VALVE_TRACE_CSV,
        help="Digitized trace CSV",
    )
    parser.add_argument("--save", type=Path, default=None, help="Optional PNG output path")
    args = parser.parse_args()

    if not args.csv.is_file():
        print(f"Missing {args.csv}")
        print("Complete WebPlotDigitizer export first — see docs/bergant_adelaide_verification.md")
        return 1

    errors = validate_valve_trace_csv(args.csv)
    if errors:
        print("CSV validation failed:")
        for e in errors:
            print(f"  - {e}")
        return 1

    ref = load_reference("severe_cavitation")
    trace = load_valve_trace_csv(args.csv)
    print(f"Loaded {len(trace['t_s'])} points from {args.csv.name}")
    print(f"  metadata: {trace.get('metadata', {})}")

    results = run_bergant_case(ref)
    metrics = evaluate_bergant_valve_trace("severe_cavitation", results, ref, trace)
    label = CASE_LABELS["severe_cavitation"]
    print(f"\n{label}")
    print(f"  compare unit: {metrics.pressure_unit}")
    print(f"  RMS: {metrics.rms_kpa:.1f} kPa (limit {metrics.rms_limit_kpa:.1f})")
    print(f"  max|err|: {metrics.max_abs_kpa:.1f} kPa (limit {metrics.max_abs_limit_kpa:.1f})")
    print(f"  points used: {metrics.n_points} in [{metrics.t_start_s:.3f}, {metrics.t_end_s:.3f}] s")
    print(f"  peak ({metrics.peak_window_label}): exp={metrics.exp_peak_gauge_kpa:.1f} sim={metrics.sim_peak_gauge_kpa:.1f} kPa gauge, rel_err={metrics.peak_rel_err:.3f}")
    print(f"  pytest peak check: {'PASS' if metrics.passed_peak else 'FAIL'}")
    print(f"  RMS (informational): {metrics.rms_kpa:.1f} kPa — {'PASS' if metrics.passed_rms else 'FAIL'}")

    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("\nInstall matplotlib to render overlay plot.")
        return 0

    t_sim, p_sim_g = valve_gauge_pressure_kpa(results)
    t_exp = trace["t_s"]
    p_exp_g = trace["p_gauge_kPa"]

    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(t_exp, p_exp_g, "o", ms=2, color="C1", label="Digitized experiment (gauge)")
    ax.plot(t_sim, p_sim_g, "-", lw=1.2, color="C0", label="rthym-moc DVCM (gauge)")
    ax.set_xlabel("t (s)")
    ax.set_ylabel("P gauge (kPa)")
    ax.set_title("Bergant Adelaide severe — valve pressure")
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    if args.save:
        fig.savefig(args.save, dpi=150)
        print(f"\nWrote {args.save}")
    else:
        out = REPO / "bergant_trace_overlay.png"
        fig.savefig(out, dpi=150)
        print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
