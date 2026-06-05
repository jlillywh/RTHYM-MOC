"""LP-PERF-01: long-pipeline performance regression (profile export disabled)."""

from __future__ import annotations

import statistics
import time

import pytest

from tests.long_pipeline_perf_utils import (
    LP_PERF_01_DT_S,
    LP_PERF_01_TOTAL_TIME_S,
    build_lp_perf_01_solver,
    expected_lp_perf_01_segments,
    load_lp_perf_baseline,
)

_LP_PERF_01_REPS = 3


@pytest.mark.slow
def test_lp_perf_01_disabled_runtime_within_baseline() -> None:
    """Default run() path must not regress more than 5% vs checked-in LP-PERF-01 baseline."""
    baseline = load_lp_perf_baseline()
    solver = build_lp_perf_01_solver()

    # Warmup: grid build + short run (mirrors scripts/benchmark_long_pipeline_budget.py).
    solver.run(total_time=LP_PERF_01_DT_S * 10, dt=LP_PERF_01_DT_S)

    elapsed_samples_s: list[float] = []
    results = None
    for _ in range(_LP_PERF_01_REPS):
        t0 = time.perf_counter()
        results = solver.run(
            total_time=LP_PERF_01_TOTAL_TIME_S,
            dt=LP_PERF_01_DT_S,
            record_pipe_profiles=False,
        )
        elapsed_samples_s.append(time.perf_counter() - t0)

    elapsed_s = statistics.median(elapsed_samples_s)
    baseline_s = float(baseline["elapsed_s"])
    tolerance_ratio = float(baseline["tolerance_ratio"])
    ceiling_s = baseline_s * (1.0 + tolerance_ratio)

    assert results is not None
    assert len(results["time"]) == int(LP_PERF_01_TOTAL_TIME_S / LP_PERF_01_DT_S)
    assert expected_lp_perf_01_segments() == int(baseline["segments"])
    assert elapsed_s <= ceiling_s, (
        f"LP-PERF-01 disabled median runtime {elapsed_s:.3f}s "
        f"(samples={[round(t, 3) for t in elapsed_samples_s]}) exceeds baseline "
        f"{baseline_s:.3f}s + {100 * tolerance_ratio:.0f}% ({ceiling_s:.3f}s)"
    )
