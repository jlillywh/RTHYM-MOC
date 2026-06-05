"""Canonical DVCM cavitation scenarios — **snapshot regression** (not independent verification).

Three junction-only cases replay checked-in golden traces in
``tests/dvcm_*_reference.json``. These detect drift from a prior accepted
rthym-moc run; they do **not** compare against textbook physics or another
engine. For independent DVCM checks see ``test_dvcm_physical_verification.py``.

Interactive overlays: ``examples/dvcm_canonical_verification.ipynb``.
Trust model: [docs/validation.md](../docs/validation.md#verification-vs-regression-read-this-first).
"""

import pytest

from dvcm_canonical_verification_utils import run_and_evaluate

pytestmark = pytest.mark.dvcm


def test_dvcm_canonical_rapid_closure_case_forms_cavity_then_collapse_spike() -> None:
    _, _, metrics = run_and_evaluate("rapid_closure")
    assert metrics.passed, (
        f"rapid_closure failed: peak_err={metrics.peak_head_error_ft:.3e} ft, "
        f"rms={metrics.rms_head_error_ft:.3e} ft, collapse_dt={metrics.collapse_time_error_s:.3e} s"
    )


def test_dvcm_canonical_pressure_recovery_case_recovers_above_vapor_floor() -> None:
    _, _, metrics = run_and_evaluate("pressure_recovery")
    assert metrics.passed, (
        f"pressure_recovery failed: peak_err={metrics.peak_head_error_ft:.3e} ft, "
        f"rms={metrics.rms_head_error_ft:.3e} ft"
    )


def test_dvcm_canonical_long_run_case_remains_stable_across_repeated_events() -> None:
    _, _, metrics = run_and_evaluate("long_run")
    assert metrics.passed, (
        f"long_run failed: peak_err={metrics.peak_head_error_ft:.3e} ft, "
        f"rms={metrics.rms_head_error_ft:.3e} ft, "
        f"collapses {metrics.collapse_events} vs ref {metrics.reference_collapse_events}"
    )
