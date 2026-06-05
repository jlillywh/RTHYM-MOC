"""Independent DVCM verification against the Bergant–Simpson Adelaide laboratory rig.

Pressure peaks are compared to **published experimental measurements** (He et al.
2025 citing Bergant), not to prior rthym-moc snapshot JSON.

Optional full trace: add ``bergant_adelaide_severe_valve_trace_reference.csv`` and run
``test_dvcm_bergant_adelaide_trace.py`` — see ``docs/bergant_adelaide_verification.md``.
"""

from __future__ import annotations

import pytest

from bergant_adelaide_verification_utils import (
    CASE_LABELS,
    CASES,
    run_and_evaluate,
)

pytestmark = pytest.mark.dvcm


@pytest.mark.parametrize("case_id", sorted(CASES))
def test_dvcm_bergant_adelaide_valve_pressure_matches_experiment(case_id: str) -> None:
    _, ref, metrics = run_and_evaluate(case_id)
    label = CASE_LABELS.get(case_id, case_id)

    assert metrics.passed_cavity, (
        f"{label}: expected vaporous cavity at the valve "
        f"(gauge ≤ {ref['analysis'].get('min_gauge_kpa_for_cavity', 'vapor')} kPa); "
        f"min gauge = {metrics.min_gauge_kpa:.1f} kPa"
    )
    assert metrics.passed_peak, (
        f"{label}: {metrics.peak_metric} mismatch — "
        f"sim={metrics.sim_peak_kpa:.1f} kPa at t={metrics.sim_peak_time_s:.4f} s, "
        f"exp={metrics.exp_peak_kpa:.1f} kPa, rel_err={metrics.peak_rel_err:.3f}"
    )
