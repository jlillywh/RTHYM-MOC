"""Optional valve pressure trace check vs digitized experimental curve.

Until ``validation/datasets/bergant_adelaide/severe_valve_trace_reference.csv`` exists, this
module is skipped (scalar peak tests still run in ``test_dvcm_bergant_adelaide_experiment.py``).

To enable: copy the ``.csv.example`` file, digitize He et al. (2025) Fig. 4, validate
with ``python scripts/validate_bergant_trace_csv.py``, then re-run pytest.
"""

from __future__ import annotations

import pytest

from bergant_adelaide_verification_utils import (
    CASE_LABELS,
    SEVERE_VALVE_TRACE_CSV,
    run_and_evaluate_trace,
    validate_valve_trace_csv,
    valve_trace_csv_exists,
)

pytestmark = pytest.mark.dvcm

_CASE = "severe_cavitation"
_SKIP_REASON = (
    "Digitized trace not found. Copy validation/datasets/bergant_adelaide/"
    "severe_valve_trace_reference.csv.example to severe_valve_trace_reference.csv "
    "and add points from He et al. (2025) Fig. 4 — see docs/bergant_adelaide_verification.md"
)


@pytest.mark.skipif(not valve_trace_csv_exists(_CASE), reason=_SKIP_REASON)
def test_dvcm_bergant_adelaide_severe_valve_trace_rms() -> None:
    errors = validate_valve_trace_csv(SEVERE_VALVE_TRACE_CSV)
    assert not errors, "Trace CSV validation failed:\n  " + "\n  ".join(errors)

    _, ref, trace, metrics = run_and_evaluate_trace(_CASE)
    label = CASE_LABELS.get(_CASE, _CASE)
    meta = trace.get("metadata", {})
    source = meta.get("source", trace["path"].name)

    assert metrics.passed_peak, (
        f"{label}: digitized vs simulation peak mismatch in {metrics.peak_window_label} — "
        f"exp_peak={metrics.exp_peak_gauge_kpa:.1f} kPa gauge, "
        f"sim_peak={metrics.sim_peak_gauge_kpa:.1f} kPa gauge, "
        f"rel_err={metrics.peak_rel_err:.3f} (limit {metrics.peak_rel_limit:.2f}); "
        f"RMS={metrics.rms_kpa:.1f} kPa (informational, limit {metrics.rms_limit_kpa:.1f})"
    )
