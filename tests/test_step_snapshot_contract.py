"""Contract tests for plain C++ StepSnapshot telemetry (PR 2 decoupling)."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOLVER_DIR = REPO_ROOT / "src" / "solver"
TYPES_HPP = SOLVER_DIR / "types.hpp"
MOC_SOLVER_HPP = SOLVER_DIR / "moc_solver.hpp"
MOC_SOLVER_CPP = SOLVER_DIR / "moc_solver.cpp"
WASM_BINDINGS_CPP = REPO_ROOT / "bindings" / "wasm" / "wasm_bindings.cpp"


def test_step_snapshot_types_live_in_solver_core() -> None:
    """Core should expose plain StepSnapshot POD types with no binding headers."""
    types_source = TYPES_HPP.read_text(encoding="utf-8")
    header_source = MOC_SOLVER_HPP.read_text(encoding="utf-8")

    assert "struct NodeStepSnapshot" in types_source
    assert "struct LinkStepSnapshot" in types_source
    assert "struct StepSnapshot" in types_source
    assert "emscripten" not in types_source.lower()
    assert "StepSnapshot capture_step_snapshot() const;" in header_source
    assert "emscripten" not in header_source.lower()
    assert "#if defined(EMSCRIPTEN" not in header_source


def test_capture_step_snapshot_is_implemented_in_core() -> None:
    """Telemetry assembly should live in moc_solver.cpp, not wasm bindings."""
    core_source = MOC_SOLVER_CPP.read_text(encoding="utf-8")
    wasm_source = WASM_BINDINGS_CPP.read_text(encoding="utf-8")

    assert "StepSnapshot MOCSolver::capture_step_snapshot() const" in core_source
    assert "reverse_flow_blocked" in core_source
    assert "MOCSolver::get_step_results" not in core_source
    assert "convert_snapshot_to_val" in wasm_source
    assert "capture_step_snapshot()" in wasm_source
