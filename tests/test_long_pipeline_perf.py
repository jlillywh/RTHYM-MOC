"""LP-PERF-01 performance gate for Phase 4 grid scaling (Phase 7 CI guard)."""

from __future__ import annotations

import pytest

from long_pipeline_perf_utils import (
    BASELINE_REGRESSION_FRACTION,
    DEFAULT_BUDGET_S,
    DEFAULT_MAX_SEGMENTS,
    LP_PERF_01_ID,
    LpPerfMetrics,
    baseline_regression_limit_s,
    format_lp_perf_report,
    load_lp_perf_baseline,
    run_lp_perf_01_benchmark,
)


@pytest.mark.slow
def test_lp_perf_01_capped_grid_meets_phase4_budget() -> None:
    """LP-PERF-01: capped 20-mile grid completes within budget and baseline band."""
    baseline = load_lp_perf_baseline()
    metrics = run_lp_perf_01_benchmark(
        apply_grid_cap=True,
        max_segments_per_pipe=DEFAULT_MAX_SEGMENTS,
        budget_s=DEFAULT_BUDGET_S,
        num_warmup=1,
        num_runs=3,
    )

    assert metrics.num_segments == baseline["num_segments"]
    assert metrics.num_steps == baseline["num_steps"]
    assert metrics.segment_steps == baseline["segment_steps"]
    assert metrics.num_segments <= DEFAULT_MAX_SEGMENTS

    assert metrics.budget_met, (
        f"{LP_PERF_01_ID} exceeded {DEFAULT_BUDGET_S}s budget: "
        f"median={metrics.elapsed_median_s:.3f}s  N={metrics.num_segments}"
    )

    regression_limit_s = baseline_regression_limit_s(baseline)
    assert metrics.elapsed_median_s <= regression_limit_s, (
        f"{LP_PERF_01_ID} regressed beyond "
        f"{100.0 * BASELINE_REGRESSION_FRACTION:.0f}% of checked-in baseline "
        f"({baseline['elapsed_median_s']:.3f}s): "
        f"median={metrics.elapsed_median_s:.3f}s  limit={regression_limit_s:.3f}s"
    )


def test_load_lp_perf_baseline_unknown_key_raises() -> None:
    with pytest.raises(KeyError, match="missing"):
        load_lp_perf_baseline(key="missing")


def test_format_lp_perf_report_documents_budget_met() -> None:
    baseline = load_lp_perf_baseline()
    metrics = LpPerfMetrics(
        case_id=LP_PERF_01_ID,
        length_ft=float(baseline["length_ft"]),
        dt_s=float(baseline["dt_s"]),
        total_time_s=float(baseline["total_time_s"]),
        num_segments=int(baseline["num_segments"]),
        num_steps=int(baseline["num_steps"]),
        segment_steps=int(baseline["segment_steps"]),
        wave_speed_design_fps=4000.0,
        wave_speed_adjusted_fps=52800.0,
        distortion_pct=1220.0,
        elapsed_s=1.2,
        elapsed_median_s=float(baseline["elapsed_median_s"]),
        budget_s=DEFAULT_BUDGET_S,
        max_segments_per_pipe=DEFAULT_MAX_SEGMENTS,
        grid_cap_enabled=True,
        budget_met=True,
    )
    report = format_lp_perf_report(metrics)
    assert LP_PERF_01_ID in report
    assert "budget_met=True" in report
    assert baseline_regression_limit_s(baseline) > float(baseline["elapsed_median_s"])
