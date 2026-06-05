"""LP-PERF-01 performance gate for Phase 4 grid scaling."""

from __future__ import annotations

import pytest

from long_pipeline_perf_utils import (
    DEFAULT_BUDGET_S,
    DEFAULT_MAX_SEGMENTS,
    LP_PERF_01_ID,
    run_lp_perf_01_benchmark,
)

pytestmark = pytest.mark.slow


@pytest.mark.slow
def test_lp_perf_01_capped_grid_meets_phase4_budget() -> None:
    """Phase 4 exit criterion: capped LP-PERF-01 completes in < 30 s."""
    metrics = run_lp_perf_01_benchmark(
        apply_grid_cap=True,
        max_segments_per_pipe=DEFAULT_MAX_SEGMENTS,
        budget_s=DEFAULT_BUDGET_S,
        num_warmup=1,
        num_runs=3,
    )
    assert metrics.num_segments <= DEFAULT_MAX_SEGMENTS
    assert metrics.budget_met, (
        f"{LP_PERF_01_ID} exceeded {DEFAULT_BUDGET_S}s budget: "
        f"median={metrics.elapsed_median_s:.3f}s  N={metrics.num_segments}"
    )
