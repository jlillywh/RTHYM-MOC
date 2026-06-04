"""Canonical DVCM cavitation scenarios for Phase 3 validation.

Three junction-only cases anchored to ``tests/dvcm_*_reference.json``:

- rapid closure analogue with cavity formation followed by a collapse spike
- pressure-recovery analogue where the cavity collapses and the junction
  settles back above vapor pressure
- long-run repeated-event analogue that exercises multiple collapse cycles

Interactive overlays: ``examples/dvcm_canonical_verification.ipynb``.
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
