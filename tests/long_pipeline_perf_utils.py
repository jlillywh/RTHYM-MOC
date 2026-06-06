"""LP-PERF-01 long-pipeline performance probe (see docs/long_pipeline_phase0_baseline.md §4)."""

from __future__ import annotations

import json
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import rthym_moc as m

LP_PERF_01_ID = "LP-PERF-01"
BASELINE_PATH = Path(__file__).resolve().parent / "long_pipeline_perf_baseline.json"
# Checked-in baseline is calibrated on a dev laptop; CI runners vary. The 30 s
# budget is the hard ceiling; this band catches multiplicative regressions.
BASELINE_REGRESSION_FRACTION = 0.50
FT_PER_MILE = 5280.0
DEFAULT_LENGTH_MI = 20.0
DEFAULT_LENGTH_FT = DEFAULT_LENGTH_MI * FT_PER_MILE
DEFAULT_DT_S = 0.001
DEFAULT_TOTAL_TIME_S = 60.0
DEFAULT_BUDGET_S = 30.0
DEFAULT_MAX_SEGMENTS = 2000
DEFAULT_MAX_DISTORTION = 0.15


@dataclass(frozen=True)
class LpPerfMetrics:
    case_id: str
    length_ft: float
    dt_s: float
    total_time_s: float
    num_segments: int
    num_steps: int
    segment_steps: int
    wave_speed_design_fps: float
    wave_speed_adjusted_fps: float
    distortion_pct: float
    elapsed_s: float
    elapsed_median_s: float
    budget_s: float
    max_segments_per_pipe: int
    grid_cap_enabled: bool
    budget_met: bool


def _make_node(node_id: str, node_type: str, **kwargs) -> m.NodeInput:
    node = m.NodeInput()
    node.id = node_id
    node.type = node_type
    for key, value in kwargs.items():
        setattr(node, key, value)
    return node


def _make_pipe(pipe_id: str, from_node: str, to_node: str, **kwargs) -> m.PipeInput:
    pipe = m.PipeInput()
    pipe.id = pipe_id
    pipe.from_node = from_node
    pipe.to_node = to_node
    for key, value in kwargs.items():
        setattr(pipe, key, value)
    return pipe


def build_lp_perf_01_solver(
    *,
    length_ft: float = DEFAULT_LENGTH_FT,
    max_segments_per_pipe: int = DEFAULT_MAX_SEGMENTS,
    max_wave_speed_distortion: float = DEFAULT_MAX_DISTORTION,
    apply_grid_cap: bool = True,
) -> m.MOCSolver:
    """Build the canonical LP-PERF-01 two-reservoir long-line case."""
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", elevation=0.0, head=500.0))
    solver.add_node(_make_node("R2", "PressureBoundary", elevation=0.0, head=100.0))
    solver.add_pipe(
        _make_pipe(
            "P1",
            "R1",
            "R2",
            length=length_ft,
            diameter=24.0,
            roughness=130.0,
            flow_gpm=3000.0,
            youngs_modulus=0.0,
        )
    )
    if apply_grid_cap:
        solver.set_grid_policy(
            max_segments_per_pipe=max_segments_per_pipe,
            max_wave_speed_distortion=max_wave_speed_distortion,
            distortion_action="warn",
        )
    return solver


def run_lp_perf_01_benchmark(
    *,
    length_mi: float = DEFAULT_LENGTH_MI,
    dt_s: float = DEFAULT_DT_S,
    total_time_s: float = DEFAULT_TOTAL_TIME_S,
    budget_s: float = DEFAULT_BUDGET_S,
    max_segments_per_pipe: int = DEFAULT_MAX_SEGMENTS,
    max_wave_speed_distortion: float = DEFAULT_MAX_DISTORTION,
    apply_grid_cap: bool = True,
    num_runs: int = 3,
    num_warmup: int = 1,
) -> LpPerfMetrics:
    """Time LP-PERF-01 and return grid/performance metrics."""
    length_ft = length_mi * FT_PER_MILE
    solver = build_lp_perf_01_solver(
        length_ft=length_ft,
        max_segments_per_pipe=max_segments_per_pipe,
        max_wave_speed_distortion=max_wave_speed_distortion,
        apply_grid_cap=apply_grid_cap,
    )

    for _ in range(num_warmup):
        solver.run(total_time=0.01, dt=dt_s)

    elapsed_samples: list[float] = []
    results = None
    for _ in range(num_runs):
        t0 = time.perf_counter()
        results = solver.run(total_time=total_time_s, dt=dt_s)
        elapsed_samples.append(time.perf_counter() - t0)

    assert results is not None
    num_segments = int(results["pipe_num_segments"]["P1"])
    num_steps = int(len(results["time"]))
    segment_steps = num_segments * num_steps
    elapsed_median = float(statistics.median(elapsed_samples))
    elapsed_last = float(elapsed_samples[-1])

    return LpPerfMetrics(
        case_id=LP_PERF_01_ID,
        length_ft=length_ft,
        dt_s=dt_s,
        total_time_s=total_time_s,
        num_segments=num_segments,
        num_steps=num_steps,
        segment_steps=segment_steps,
        wave_speed_design_fps=float(results["pipe_wave_speed_design_fps"]["P1"]),
        wave_speed_adjusted_fps=float(results["pipe_wave_speed_adjusted_fps"]["P1"]),
        distortion_pct=float(results["pipe_distortion_pct"]["P1"]),
        elapsed_s=elapsed_last,
        elapsed_median_s=elapsed_median,
        budget_s=budget_s,
        max_segments_per_pipe=max_segments_per_pipe if apply_grid_cap else 0,
        grid_cap_enabled=apply_grid_cap,
        budget_met=elapsed_median <= budget_s,
    )


def load_lp_perf_baseline(*, key: str = "capped") -> dict[str, Any]:
    """Load checked-in LP-PERF-01 timing baseline (see docs/long_pipeline_phase0_baseline.md §4)."""
    with BASELINE_PATH.open(encoding="utf-8") as fp:
        data = json.load(fp)
    if key not in data:
        raise KeyError(f"baseline key {key!r} not found in {BASELINE_PATH.name}")
    return data[key]


def baseline_regression_limit_s(baseline: dict[str, Any]) -> float:
    """Maximum allowed median elapsed time vs the checked-in baseline."""
    return float(baseline["elapsed_median_s"]) * (1.0 + BASELINE_REGRESSION_FRACTION)


def format_lp_perf_report(metrics: LpPerfMetrics) -> str:
    cap = metrics.max_segments_per_pipe if metrics.grid_cap_enabled else "none"
    return (
        f"{metrics.case_id}: L={metrics.length_ft:.0f} ft  dt={metrics.dt_s} s  "
        f"T={metrics.total_time_s:.0f} s\n"
        f"  N={metrics.num_segments}  steps={metrics.num_steps}  "
        f"segment-steps={metrics.segment_steps:,}\n"
        f"  a_design={metrics.wave_speed_design_fps:.1f} ft/s  "
        f"a_adj={metrics.wave_speed_adjusted_fps:.1f} ft/s  "
        f"distortion={metrics.distortion_pct:.2f}%\n"
        f"  elapsed={metrics.elapsed_s:.3f} s  median({metrics.elapsed_median_s:.3f} s)  "
        f"budget={metrics.budget_s:.0f} s  cap={cap}\n"
        f"  budget_met={metrics.budget_met}"
    )
