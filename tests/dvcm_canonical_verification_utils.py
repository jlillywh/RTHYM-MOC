"""Shared helpers for DVCM canonical junction scenarios (tests + notebook)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import rthym_moc as m

_HERE = Path(__file__).resolve().parent

PEAK_ERROR_MAX_FT = 0.05
COLLAPSE_TIME_ERROR_MAX_S = 1e-9
RMS_TRACE_ERROR_MAX_FT = 1e-9

CANONICAL_DT_S = 0.01
CANONICAL_P_VAPOR_PSI = 50.0

CASES: dict[str, str] = {
    "rapid_closure": "dvcm_rapid_closure_reference.json",
    "pressure_recovery": "dvcm_pressure_recovery_reference.json",
    "long_run": "dvcm_long_run_reference.json",
}

CASE_LABELS: dict[str, str] = {
    "rapid_closure": "Rapid closure",
    "pressure_recovery": "Pressure recovery",
    "long_run": "Long run (repeated events)",
}


def reference_path(case_id: str) -> Path:
    return _HERE / CASES[case_id]


def load_reference(case_id: str) -> dict[str, Any]:
    if case_id not in CASES:
        raise KeyError(f"Unknown case_id {case_id!r}; expected one of {sorted(CASES)}")
    return json.loads((_HERE / CASES[case_id]).read_text())


def build_junction_solver() -> m.MOCSolver:
    solver = m.MOCSolver()
    for nid, ntype, head in [("R1", "Tank", 100.0), ("J1", "Junction", 100.0), ("R2", "Tank", 100.0)]:
        node = m.NodeInput()
        node.id, node.type, node.head = nid, ntype, head
        solver.add_node(node)
    for pid, fn, tn in [("P1", "R1", "J1"), ("P2", "J1", "R2")]:
        pipe = m.PipeInput()
        pipe.id, pipe.from_node, pipe.to_node = pid, fn, tn
        pipe.length, pipe.diameter, pipe.roughness = 40.0, 8.0, 120.0
        solver.add_pipe(pipe)
    return solver


def schedule_from_reference(reference: dict[str, Any]) -> list[tuple[float, float]]:
    return [(float(e["t"]), float(e["head_ft"])) for e in reference["schedule"]]


def run_canonical_case(reference: dict[str, Any]) -> dict:
    solver = build_junction_solver()
    schedule = schedule_from_reference(reference)
    solver.set_head_schedule("R1", schedule)
    solver.set_head_schedule("R2", schedule)
    return solver.run(
        total_time=float(reference["total_time_s"]),
        dt=CANONICAL_DT_S,
        p_vapor_psi=CANONICAL_P_VAPOR_PSI,
        cavitation_model=m.CavitationModel.DVCM,
    )


def collapse_time_s(results: dict) -> float:
    time_s = np.asarray(results["time"], dtype=float)
    collapse_flag = np.asarray(results["node_cavity_collapse_flag"]["J1"], dtype=int)
    return float(time_s[np.flatnonzero(collapse_flag)[0]])


def rms_trace_error_ft(actual: np.ndarray, reference: np.ndarray) -> float:
    n = min(actual.size, reference.size)
    return float(np.sqrt(np.mean(np.square(actual[:n] - reference[:n]))))


@dataclass(frozen=True)
class CanonicalCaseMetrics:
    case_id: str
    peak_head_ft: float
    peak_head_error_ft: float
    collapse_time_s: float
    collapse_time_error_s: float
    rms_head_error_ft: float
    collapse_events: int
    reference_collapse_events: int
    passed_peak: bool
    passed_collapse_time: bool
    passed_rms: bool
    passed_extra: bool
    passed: bool


def evaluate_canonical_case(case_id: str, results: dict, reference: dict[str, Any]) -> CanonicalCaseMetrics:
    head = np.asarray(results["node_head"]["J1"], dtype=float)
    ref_head = np.asarray(reference["head_ft"], dtype=float)
    collapse_flag = np.asarray(results["node_cavity_collapse_flag"]["J1"], dtype=int)
    ref_collapse_flag = np.asarray(reference["collapse_flag"], dtype=int)

    peak_err = abs(float(head.max()) - float(reference["peak_head_ft"]))
    t_coll = collapse_time_s(results)
    t_coll_err = abs(t_coll - float(reference["collapse_time_s"]))
    rms = rms_trace_error_ft(head, ref_head)

    passed_peak = peak_err <= PEAK_ERROR_MAX_FT
    passed_coll_time = t_coll_err <= COLLAPSE_TIME_ERROR_MAX_S
    passed_rms = rms <= RMS_TRACE_ERROR_MAX_FT
    passed_extra = _evaluate_case_specific(results, reference, case_id)

    return CanonicalCaseMetrics(
        case_id=case_id,
        peak_head_ft=float(head.max()),
        peak_head_error_ft=peak_err,
        collapse_time_s=t_coll,
        collapse_time_error_s=t_coll_err,
        rms_head_error_ft=rms,
        collapse_events=int(collapse_flag.sum()),
        reference_collapse_events=int(ref_collapse_flag.sum()),
        passed_peak=passed_peak,
        passed_collapse_time=passed_coll_time,
        passed_rms=passed_rms,
        passed_extra=passed_extra,
        passed=passed_peak and passed_coll_time and passed_rms and passed_extra,
    )


def _evaluate_case_specific(results: dict, reference: dict[str, Any], case_id: str) -> bool:
    active = np.asarray(results["node_cavity_active"]["J1"], dtype=int)
    volume = np.asarray(results["node_cavity_volume"]["J1"], dtype=float)
    head = np.asarray(results["node_head"]["J1"], dtype=float)
    collapse_flag = np.asarray(results["node_cavity_collapse_flag"]["J1"], dtype=int)
    collapse_count = np.asarray(results["node_cavity_collapse_count"]["J1"], dtype=int)
    ref_collapse_flag = np.asarray(reference["collapse_flag"], dtype=int)

    if case_id == "rapid_closure":
        return active[0] == 1 and int(collapse_count[-1]) == 1 and float(volume.max()) > 0.0 and float(volume[-1]) == 0.0

    if case_id == "pressure_recovery":
        collapse_idx = int(np.flatnonzero(collapse_flag)[0])
        return (
            bool(np.all(active[collapse_idx:] == 0))
            and float(volume[-1]) == 0.0
            and float(head[-1]) > 125.0
            and float(head[-3:].mean()) > 130.0
        )

    if case_id == "long_run":
        return (
            int(collapse_flag.sum()) == int(ref_collapse_flag.sum())
            and int(collapse_count[-1]) == int(reference["collapse_count"][-1])
            and bool(np.all(np.diff(collapse_count) >= 0))
            and bool(np.isfinite(head).all())
            and bool(np.isfinite(volume).all())
            and bool(np.all(volume >= 0.0))
            and float(volume[-1]) == 0.0
            and int(active[-1]) == 0
        )

    return True


def run_and_evaluate(case_id: str) -> tuple[dict, dict[str, Any], CanonicalCaseMetrics]:
    reference = load_reference(case_id)
    results = run_canonical_case(reference)
    metrics = evaluate_canonical_case(case_id, results, reference)
    return results, reference, metrics
