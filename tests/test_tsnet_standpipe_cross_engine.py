"""RTHYM-MOC vs checked-in TSNet standpipe trace (Appendix B.8.5).

Uses archived ``tests/TSNet_Standpipe_B8_*`` artifacts (not a live TSNet import in CI).
"""
import pytest


from cross_engine_verification_utils import (
    TSNET_PEAK_DIFF_TOL_FT,
    TSNET_RMS_TOL_FT,
    evaluate_tsnet_standpipe_cross_engine,
    load_tsnet_standpipe_verification,
)


def test_tsnet_standpipe_reference_artifacts_present() -> None:
    ref = load_tsnet_standpipe_verification()
    assert "peak_head_ft" in ref
    assert "rms_head_ft" in ref


def test_rthym_standpipe_peak_matches_tsnet_reference() -> None:
    _, _, _, metrics = evaluate_tsnet_standpipe_cross_engine()
    assert metrics.passed_peak, (
        f"TSNet peak cross-engine: diff={metrics.peak_diff_ft:.3f} ft "
        f"(tol {TSNET_PEAK_DIFF_TOL_FT}); rthym={metrics.rthym_peak_ft:.2f} "
        f"tsnet={metrics.tsnet_peak_ft:.2f}"
    )


def test_rthym_standpipe_rms_matches_tsnet_trace_when_csv_present() -> None:
    from pathlib import Path

    csv_path = Path(__file__).resolve().parent / "TSNet_Standpipe_B8_Traces.csv"
    if not csv_path.is_file():
        pytest.skip("TSNet trace CSV missing; run scripts/export_tsnet_standpipe_reference.py")
    _, _, _, metrics = evaluate_tsnet_standpipe_cross_engine()
    assert metrics.passed_rms, (
        f"TSNet trace RMS={metrics.rms_head_ft:.3f} ft exceeds tol {TSNET_RMS_TOL_FT}"
    )
