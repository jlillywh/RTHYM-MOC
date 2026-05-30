"""Unit tests for the automated engineering acceptance checks."""

import pytest
from rthym_moc import format_acceptance_report, run_acceptance_checks


def test_acceptance_us_units():
    """Verify acceptance checks and reports using US Customary units."""
    # Mock StudySummary (US units)
    summary = {
        "meta": {"total_time_s": 10.0},
        "nodes": {
            "J1": {
                "pressure_psi": {"min": -5.0, "min_time_s": 1.2, "max": 140.0, "max_time_s": 3.4},
                "cavitation": {"occurred": False, "first_time_s": None, "steps": 0, "duration_s": 0.0},
            },
            "J2": {
                "pressure_psi": {"min": 10.0, "min_time_s": 0.5, "max": 160.0, "max_time_s": 2.5},
                "cavitation": {"occurred": True, "first_time_s": 2.5, "steps": 15, "duration_s": 0.15},
            },
        },
        "pipes": {},
    }

    # 1. Global max pressure: limit 150 psi. J2 has max 160.0, should fail.
    res = run_acceptance_checks(summary, max_pressure=150.0)
    assert not res["passed"]
    assert len(res["violations"]) == 2  # Max pressure J2 + Default Cavitation J2
    violation_checks = [v["check"] for v in res["violations"]]
    assert "max_pressure" in violation_checks
    assert "cavitation" in violation_checks

    # 2. Node-specific max pressure + allow cavitation: limit J1=150.0, J2=170.0. Should pass.
    res = run_acceptance_checks(
        summary,
        max_pressure={"J1": 150.0, "J2": 170.0},
        allow_cavitation=True,
        max_cavitation_duration_s=0.2,
    )
    assert res["passed"]
    assert len(res["violations"]) == 0

    # 3. Min pressure check: limit -2.0 psi. J1 has min -5.0 psi, should fail.
    res = run_acceptance_checks(
        summary,
        min_pressure=-2.0,
        allow_cavitation=True,
        max_cavitation_duration_s=0.2,
    )
    assert not res["passed"]
    assert len(res["violations"]) == 1
    assert res["violations"][0]["node_id"] == "J1"
    assert res["violations"][0]["check"] == "min_pressure"

    # Node-specific min pressure check: limit J1=-2.0, _default=-1.0.
    res = run_acceptance_checks(
        summary,
        min_pressure={"J1": -2.0, "_default": -1.0},
        allow_cavitation=True,
        max_cavitation_duration_s=0.2,
    )
    assert not res["passed"]
    assert len(res["violations"]) == 1
    assert res["violations"][0]["node_id"] == "J1"

    # 4. Cavitation duration limit: max_cavitation_duration_s = 0.1 s. J2 has 0.15 s, should fail.
    res = run_acceptance_checks(summary, allow_cavitation=True, max_cavitation_duration_s=0.1)
    assert not res["passed"]
    # Cavitation duration violation for J2
    assert len(res["violations"]) == 1
    assert res["violations"][0]["node_id"] == "J2"
    assert res["violations"][0]["check"] == "cavitation_duration"

    # 5. Node-specific limits with default fallback using '_default' key
    res = run_acceptance_checks(
        summary,
        max_pressure={"J1": 150.0, "_default": 130.0},
        allow_cavitation=True,
        max_cavitation_duration_s=0.2,
    )
    assert not res["passed"]
    assert len(res["violations"]) == 1
    assert res["violations"][0]["node_id"] == "J2"  # J2 uses fallback 130.0, actual 160.0

    # Test report formatting (Failed)
    report = format_acceptance_report(res)
    assert "ENGINEERING SURGE ANALYSIS ACCEPTANCE REPORT" in report
    assert "FAILED" in report
    assert "Node 'J2' maximum pressure violation" in report

    # Test report formatting (Passed)
    passed_res = run_acceptance_checks(summary, allow_cavitation=True, max_cavitation_duration_s=0.2)
    report_passed = format_acceptance_report(passed_res)
    assert "PASSED" in report_passed
    assert "All engineering transient acceptance criteria were MET." in report_passed


def test_acceptance_si_units():
    """Verify acceptance checks and reports using SI units."""
    # Mock StudySummarySI (SI units)
    summary = {
        "meta": {"total_time_s": 10.0},
        "nodes": {
            "J1": {
                "pressure_kpa": {"min": -34.0, "min_time_s": 1.2, "max": 900.0, "max_time_s": 3.4},
                "cavitation": {"occurred": False, "first_time_s": None, "steps": 0, "duration_s": 0.0},
            }
        },
        "pipes": {},
    }

    res = run_acceptance_checks(summary, max_pressure=800.0)
    assert not res["passed"]
    assert res["is_si"]
    assert res["violations"][0]["check"] == "max_pressure"
    assert "kPa" in res["violations"][0]["message"]

    res_min = run_acceptance_checks(summary, min_pressure=-20.0)
    assert not res_min["passed"]
    assert res_min["violations"][0]["check"] == "min_pressure"

    report = format_acceptance_report(res)
    assert "SI" in report
