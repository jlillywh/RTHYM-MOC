"""Shared helpers for LP-PERF-01 long-pipeline performance regression."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import rthym_moc as m

_HERE = Path(__file__).resolve().parent
_BASELINE_PATH = _HERE / "long_pipeline_perf_baseline.json"

MILE_FT = 5280.0
LP_PERF_01_LENGTH_MI = 20.0
LP_PERF_01_LENGTH_FT = LP_PERF_01_LENGTH_MI * MILE_FT
LP_PERF_01_DT_S = 0.001
LP_PERF_01_TOTAL_TIME_S = 60.0
LP_PERF_01_DESIGN_WAVE_SPEED_FT_S = 4000.0


def build_lp_perf_01_solver() -> m.MOCSolver:
    """LP-PERF-01 topology from docs/long_pipeline_phase0_baseline.md §4."""
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
    pipe.length = LP_PERF_01_LENGTH_FT
    pipe.diameter = 24.0
    pipe.roughness = 130.0
    pipe.flow_gpm = 3000.0
    pipe.youngs_modulus = 0.0
    solver.add_node(r1)
    solver.add_node(r2)
    solver.add_pipe(pipe)
    return solver


def expected_lp_perf_01_segments() -> int:
    return max(
        1,
        round(
            LP_PERF_01_LENGTH_FT
            / (LP_PERF_01_DESIGN_WAVE_SPEED_FT_S * LP_PERF_01_DT_S)
        ),
    )


def load_lp_perf_baseline() -> dict[str, Any]:
    return json.loads(_BASELINE_PATH.read_text())
