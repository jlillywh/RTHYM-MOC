"""Phase 6: cross-check transient friction against published literature references."""

from __future__ import annotations

import pytest

from transient_friction_verification_utils import (
    load_transient_friction_literature_reference,
    run_lp07_envelope_case,
    run_wave_reflection_case,
)


def test_transient_friction_literature_reference_present() -> None:
    ref = load_transient_friction_literature_reference()
    assert ref["case_id"] == "transient-friction-literature"
    assert len(ref["sources"]) >= 2
    assert "wave_reflection_steady" in ref
    assert "lp07_long_pipe" in ref


def test_wave_reflection_steady_friction_matches_wylie_streeter_decay() -> None:
    """Steady-friction peak decay ~2·Hf per period (Wylie & Streeter 1993).

    Uses the same reservoir–pipe–dead-end case as ``examples/test_wave_reflections.py``
    with USF disabled (``usf_tau = dt``).
    """
    ref = load_transient_friction_literature_reference()
    case = ref["wave_reflection_steady"]
    tol = case["tolerances"]
    archived = case["archived"]

    metrics = run_wave_reflection_case(usf_tau=float(case["run"]["usf_tau_s"]))

    assert len(metrics.peak_heads_ft) >= int(tol["min_peaks"]), (
        f"Expected at least {tol['min_peaks']} positive peaks, got {len(metrics.peak_heads_ft)}"
    )
    assert metrics.mean_period_s == pytest.approx(
        float(case["expected_mean_period_s"]),
        rel=float(tol["period_rel"]),
    )
    assert metrics.mean_decay_ft == pytest.approx(
        float(case["expected_mean_decay_ft"]),
        rel=float(tol["decay_rel"]),
    )
    assert metrics.peak_heads_ft[0] == pytest.approx(
        float(archived["peak_heads_ft"][0]),
        rel=0.0,
        abs=0.5,
    )
    assert metrics.total_peak_decay_ft == pytest.approx(
        float(archived["total_peak_decay_ft"]),
        rel=0.02,
    )


@pytest.mark.slow
def test_lp07_vitkovsky_envelope_matches_bergant_et_al_direction() -> None:
    """Vitkovsky damps long-pipe peaks more than quasi-steady (Bergant et al. 2006).

    Directional acceptance aligned with LP-07 / Phase 6 exit criteria — not an
    exact match to external engine exports.
    """
    ref = load_transient_friction_literature_reference()
    case = ref["lp07_long_pipe"]
    tol = case["tolerances"]
    archived = case["archived"]

    metrics = run_lp07_envelope_case()

    assert len(metrics.quasi_envelope_ft) >= int(tol["min_envelope_buckets"])
    assert len(metrics.vit_envelope_ft) >= int(tol["min_envelope_buckets"])
    assert metrics.vit_late_mean_ft < metrics.quasi_late_mean_ft
    assert metrics.quasi_late_mean_ft - metrics.vit_late_mean_ft >= float(
        tol["min_late_advantage_ft"]
    )
    assert metrics.vit_decay_ratio < metrics.quasi_decay_ratio
    assert metrics.vit_late_mean_ft == pytest.approx(
        float(archived["vit_late_mean_ft"]),
        rel=0.05,
    )
    assert metrics.quasi_late_mean_ft == pytest.approx(
        float(archived["quasi_late_mean_ft"]),
        rel=0.05,
    )


@pytest.mark.slow
def test_lp07_literature_reference_regression() -> None:
    """Regression guard for archived LP-07 envelope metrics used in literature doc."""
    ref = load_transient_friction_literature_reference()
    archived = ref["lp07_long_pipe"]["archived"]
    metrics = run_lp07_envelope_case()
    assert metrics.quasi_envelope_ft[-1] == pytest.approx(
        float(archived["quasi_envelope_ft"][-1]),
        rel=0.05,
    )
    assert metrics.vit_envelope_ft[-1] == pytest.approx(
        float(archived["vit_envelope_ft"][-1]),
        rel=0.05,
    )
