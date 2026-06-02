"""Canonical DVCM cavitation scenarios for Phase 3 validation.

This module adds three small, stable junction-only cavitation cases that can be
used as anchors while the broader DVCM validation harness grows:

- rapid closure analogue with cavity formation followed by a collapse spike
- pressure-recovery analogue where the cavity collapses and the junction
  settles back above vapor pressure
- long-run repeated-event analogue that exercises multiple collapse cycles

These are internal anchored geometries for now, not external-reference studies.
They intentionally reuse the current Phase 2 junction-only DVCM scope.
"""

import json
from pathlib import Path

import pytest
import numpy as np

import rthym_moc


pytestmark = pytest.mark.dvcm

PEAK_ERROR_MAX_FT = 0.05
COLLAPSE_TIME_ERROR_MAX_S = 1e-9
RMS_TRACE_ERROR_MAX_FT = 1e-9

_HERE = Path(__file__).resolve().parent
_RAPID_REFERENCE = json.loads((_HERE / "dvcm_rapid_closure_reference.json").read_text())
_RECOVERY_REFERENCE = json.loads((_HERE / "dvcm_pressure_recovery_reference.json").read_text())
_LONG_RUN_REFERENCE = json.loads((_HERE / "dvcm_long_run_reference.json").read_text())


def _build_junction_solver() -> rthym_moc.MOCSolver:
    solver = rthym_moc.MOCSolver()

    r1 = rthym_moc.NodeInput()
    r1.id = "R1"
    r1.type = "Tank"
    r1.head = 100.0

    j1 = rthym_moc.NodeInput()
    j1.id = "J1"
    j1.type = "Junction"
    j1.head = 100.0

    r2 = rthym_moc.NodeInput()
    r2.id = "R2"
    r2.type = "Tank"
    r2.head = 100.0

    p1 = rthym_moc.PipeInput()
    p1.id = "P1"
    p1.from_node = "R1"
    p1.to_node = "J1"
    p1.length = 40.0
    p1.diameter = 8.0
    p1.roughness = 120.0

    p2 = rthym_moc.PipeInput()
    p2.id = "P2"
    p2.from_node = "J1"
    p2.to_node = "R2"
    p2.length = 40.0
    p2.diameter = 8.0
    p2.roughness = 120.0

    solver.add_node(r1)
    solver.add_node(j1)
    solver.add_node(r2)
    solver.add_pipe(p1)
    solver.add_pipe(p2)
    return solver


def _run_case(schedule: list[tuple[float, float]], *, total_time: float) -> dict:
    solver = _build_junction_solver()
    solver.set_head_schedule("R1", schedule)
    solver.set_head_schedule("R2", schedule)
    return solver.run(
        total_time=total_time,
        dt=0.01,
        p_vapor_psi=50.0,
        cavitation_model=rthym_moc.CavitationModel.DVCM,
    )


def _reference_head(reference: dict) -> np.ndarray:
    return np.asarray(reference["head_ft"], dtype=float)


def _collapse_time_s(results: dict) -> float:
    time_s = np.asarray(results["time"], dtype=float)
    collapse_flag = np.asarray(results["node_cavity_collapse_flag"]["J1"], dtype=int)
    return float(time_s[np.flatnonzero(collapse_flag)[0]])


def _rms_trace_error_ft(actual: np.ndarray, reference: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(actual - reference))))


def test_dvcm_canonical_rapid_closure_case_forms_cavity_then_collapse_spike() -> None:
    results = _run_case(
        [(entry["t"], entry["head_ft"]) for entry in _RAPID_REFERENCE["schedule"]],
        total_time=_RAPID_REFERENCE["total_time_s"],
    )

    active = np.asarray(results["node_cavity_active"]["J1"], dtype=int)
    collapse_count = np.asarray(results["node_cavity_collapse_count"]["J1"], dtype=int)
    volume = np.asarray(results["node_cavity_volume"]["J1"], dtype=float)
    head = np.asarray(results["node_head"]["J1"], dtype=float)

    assert active[0] == 1
    assert int(collapse_count[-1]) == 1
    assert float(volume.max()) > 0.0
    assert float(volume[-1]) == 0.0
    assert abs(float(head.max()) - float(_RAPID_REFERENCE["peak_head_ft"])) <= PEAK_ERROR_MAX_FT
    assert abs(_collapse_time_s(results) - float(_RAPID_REFERENCE["collapse_time_s"])) <= COLLAPSE_TIME_ERROR_MAX_S
    assert _rms_trace_error_ft(head, _reference_head(_RAPID_REFERENCE)) <= RMS_TRACE_ERROR_MAX_FT


def test_dvcm_canonical_pressure_recovery_case_recovers_above_vapor_floor() -> None:
    results = _run_case(
        [(entry["t"], entry["head_ft"]) for entry in _RECOVERY_REFERENCE["schedule"]],
        total_time=_RECOVERY_REFERENCE["total_time_s"],
    )

    active = np.asarray(results["node_cavity_active"]["J1"], dtype=int)
    volume = np.asarray(results["node_cavity_volume"]["J1"], dtype=float)
    head = np.asarray(results["node_head"]["J1"], dtype=float)
    reference_head = _reference_head(_RECOVERY_REFERENCE)

    collapse_idx = int(np.flatnonzero(np.asarray(results["node_cavity_collapse_flag"]["J1"], dtype=int))[0])

    assert np.all(active[collapse_idx:] == 0)
    assert float(volume[-1]) == 0.0
    assert float(head[-1]) > 125.0
    assert float(head[-3:].mean()) > 130.0
    assert abs(float(head.max()) - float(_RECOVERY_REFERENCE["peak_head_ft"])) <= PEAK_ERROR_MAX_FT
    assert abs(_collapse_time_s(results) - float(_RECOVERY_REFERENCE["collapse_time_s"])) <= COLLAPSE_TIME_ERROR_MAX_S
    assert _rms_trace_error_ft(head, reference_head) <= RMS_TRACE_ERROR_MAX_FT


def test_dvcm_canonical_long_run_case_remains_stable_across_repeated_events() -> None:
    results = _run_case(
        [(entry["t"], entry["head_ft"]) for entry in _LONG_RUN_REFERENCE["schedule"]],
        total_time=_LONG_RUN_REFERENCE["total_time_s"],
    )

    active = np.asarray(results["node_cavity_active"]["J1"], dtype=int)
    collapse_flag = np.asarray(results["node_cavity_collapse_flag"]["J1"], dtype=int)
    collapse_count = np.asarray(results["node_cavity_collapse_count"]["J1"], dtype=int)
    volume = np.asarray(results["node_cavity_volume"]["J1"], dtype=float)
    head = np.asarray(results["node_head"]["J1"], dtype=float)
    reference_head = _reference_head(_LONG_RUN_REFERENCE)

    assert int(collapse_flag.sum()) == int(np.asarray(_LONG_RUN_REFERENCE["collapse_flag"], dtype=int).sum())
    assert int(collapse_count[-1]) == int(_LONG_RUN_REFERENCE["collapse_count"][-1])
    assert np.all(np.diff(collapse_count) >= 0)
    assert np.isfinite(head).all()
    assert np.isfinite(volume).all()
    assert np.all(volume >= 0.0)
    assert float(volume[-1]) == 0.0
    assert int(active[-1]) == 0
    assert abs(float(head.max()) - float(_LONG_RUN_REFERENCE["peak_head_ft"])) <= PEAK_ERROR_MAX_FT
    assert abs(_collapse_time_s(results) - float(_LONG_RUN_REFERENCE["collapse_time_s"])) <= COLLAPSE_TIME_ERROR_MAX_S
    assert _rms_trace_error_ft(head, reference_head) <= RMS_TRACE_ERROR_MAX_FT
