"""Tests for engineering post-processing helpers (roadmap item 5)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

import rthym_moc as m
from rthym_moc.report import (
    cavitation_summary,
    export_study_csv,
    export_study_csv_si,
    export_study_json,
    format_study_table,
    format_study_table_si,
    head_to_pressure_kpa,
    series_extrema,
    study_summary_to_si,
    summarize_study,
    summarize_study_si,
)


def test_series_extrema_finds_times():
    t = np.array([0.0, 1.0, 2.0, 3.0])
    y = np.array([10.0, 5.0, 20.0, 12.0])
    ext = series_extrema(t, y)
    assert ext["min"] == pytest.approx(5.0)
    assert ext["min_time_s"] == pytest.approx(1.0)
    assert ext["max"] == pytest.approx(20.0)
    assert ext["max_time_s"] == pytest.approx(2.0)


def test_series_extrema_empty_series():
    ext = series_extrema(np.array([]), np.array([]))
    assert np.isnan(ext["min"])
    assert np.isnan(ext["max"])


def test_summarize_study_infers_dt_edge_cases():
    single_step = summarize_study(
        {
            "time": np.array([0.0]),
            "node_head": {"J1": np.array([100.0])},
            "pipe_flow_gpm": {"P1": np.array([50.0])},
        }
    )
    assert single_step["meta"]["dt_s"] == pytest.approx(0.0)

    flat_time = summarize_study(
        {
            "time": np.array([0.0, 0.0, 0.0]),
            "node_head": {"J1": np.array([100.0, 90.0, 95.0])},
            "pipe_flow_gpm": {"P1": np.array([50.0, 40.0, 45.0])},
        }
    )
    assert flat_time["meta"]["dt_s"] == pytest.approx(0.0)


def test_cavitation_summary_duration():
    t = np.linspace(0.0, 0.09, 10)
    flags = np.array([0, 0, 1, 1, 1, 0, 0, 0, 0, 0])
    summary = cavitation_summary(t, flags, dt_s=0.01)
    assert summary["occurred"] is True
    assert summary["first_time_s"] == pytest.approx(0.02)
    assert summary["steps"] == 3
    assert summary["duration_s"] == pytest.approx(0.03)


def _node(node_id: str, node_type: str, **kwargs) -> m.NodeInput:
    node = m.NodeInput()
    node.id = node_id
    node.type = node_type
    for key, value in kwargs.items():
        setattr(node, key, value)
    return node


def _pipe(pipe_id: str, frm: str, to: str, **kwargs) -> m.PipeInput:
    pipe = m.PipeInput()
    pipe.id = pipe_id
    pipe.from_node = frm
    pipe.to_node = to
    for key, value in kwargs.items():
        setattr(pipe, key, value)
    return pipe


def test_summarize_study_on_solver_results():
    solver = m.MOCSolver()
    solver.add_node(_node("R1", "PressureBoundary", head=120.0))
    solver.add_node(_node("J1", "Junction", elevation=0.0, head=100.0))
    solver.add_node(_node("R2", "PressureBoundary", head=80.0))
    solver.add_pipe(
        _pipe("P1", "R1", "J1", length=200.0, diameter=12.0, roughness=130.0, flow_gpm=200.0)
    )
    solver.add_pipe(
        _pipe("P2", "J1", "R2", length=200.0, diameter=12.0, roughness=130.0, flow_gpm=200.0)
    )
    results = solver.run(total_time=0.2, dt=0.01, p_vapor_psi=-14.0)
    summary = summarize_study(results)

    assert summary["meta"]["num_steps"] == 20
    assert "J1" in summary["nodes"]
    assert "P1" in summary["pipes"]
    assert "head_ft" in summary["nodes"]["J1"]
    assert "pressure_psi" in summary["nodes"]["J1"]
    assert summary["nodes"]["J1"]["head_ft"]["max"] >= summary["nodes"]["J1"]["head_ft"]["min"]

    table = format_study_table(summary)
    assert "Node envelopes" in table
    assert "J1" in table


def test_export_study_json_and_csv(tmp_path: Path):
    time_s = np.array([0.0, 0.01, 0.02])
    results = {
        "time": time_s,
        "node_head": {"J1": np.array([100.0, 90.0, 95.0])},
        "node_pressure": {"J1": np.array([43.0, 39.0, 41.0])},
        "node_cavitation": {"J1": np.array([0, 1, 0])},
        "pipe_flow_gpm": {"P1": np.array([100.0, -20.0, 50.0])},
    }
    summary = summarize_study(results, dt_s=0.01)

    json_path = export_study_json(tmp_path / "study.json", summary)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["nodes"]["J1"]["head_ft"]["min"] == pytest.approx(90.0)

    written = export_study_csv(tmp_path / "csv", summary)
    assert written["nodes"].exists()
    assert written["pipes"].exists()
    assert "node_id" in written["nodes"].read_text(encoding="utf-8")


def test_summarize_study_si_matches_us_summary():
    time_s = np.array([0.0, 0.01, 0.02])
    results = {
        "time": time_s,
        "node_head": {"J1": np.array([100.0, 90.0, 95.0])},
        "node_pressure": {"J1": np.array([43.0, 39.0, 41.0])},
        "node_cavitation": {"J1": np.array([0, 1, 0])},
        "pipe_flow_gpm": {"P1": np.array([100.0, -20.0, 50.0])},
    }
    us = summarize_study(results, dt_s=0.01)
    si = summarize_study_si(results, dt_s=0.01)
    converted = study_summary_to_si(us)

    assert si == converted
    assert si["nodes"]["J1"]["head_m"]["min"] == pytest.approx(90.0 * m.FT_TO_M)
    assert si["nodes"]["J1"]["pressure_kpa"]["max"] == pytest.approx(43.0 * m.PSI_TO_KPA)
    assert si["pipes"]["P1"]["flow_m3s"]["min"] == pytest.approx(-20.0 * m.GPM_TO_M3S)


def test_format_and_export_study_si(tmp_path: Path):
    time_s = np.array([0.0, 0.01, 0.02])
    results = {
        "time": time_s,
        "node_head": {"J1": np.array([100.0, 90.0, 95.0])},
        "node_pressure": {"J1": np.array([43.0, 39.0, 41.0])},
        "pipe_flow_gpm": {"P1": np.array([100.0, -20.0, 50.0])},
    }
    summary = summarize_study_si(results, dt_s=0.01)

    table = format_study_table_si(summary)
    assert "Transient study summary (SI)" in table
    assert "m^3/s" in table

    written = export_study_csv_si(tmp_path / "csv_si", summary)
    assert written["nodes"].name == "node_envelopes_si.csv"
    assert "head_min_m" in written["nodes"].read_text(encoding="utf-8")
    assert written["pipes"].name == "pipe_flow_envelopes_si.csv"
    assert "flow_min_m3s" in written["pipes"].read_text(encoding="utf-8")


def test_head_to_pressure_kpa():
    head_m = 30.48
    assert head_to_pressure_kpa(head_m, 0.0) == pytest.approx(
        m.pressure_psi_to_kpa(m.length_m_to_ft(head_m) / m.PSI_TO_FT)
    )


def test_summarize_study_with_acceptance_limits():
    time_s = np.array([0.0, 0.01, 0.02])
    results = {
        "time": time_s,
        "node_head": {"J1": np.array([100.0, 90.0, 95.0])},
        "node_pressure": {"J1": np.array([43.0, 39.0, 41.0])},
        "node_cavitation": {"J1": np.array([0, 1, 0])},
        "pipe_flow_gpm": {"P1": np.array([100.0, -20.0, 50.0])},
    }
    # Test passed max_pressure, min_pressure, allow_cavitation, max_cavitation_duration_s
    summary = summarize_study(
        results,
        dt_s=0.01,
        max_pressure=50.0,
        min_pressure=30.0,
        allow_cavitation=True,
        max_cavitation_duration_s=0.05,
    )
    assert "acceptance" in summary
    assert summary["acceptance"]["passed"] is True

    # Test failed min_pressure
    summary_failed_min = summarize_study(results, dt_s=0.01, min_pressure=40.0)
    assert summary_failed_min["acceptance"]["passed"] is False

    # Test failed cavitation duration
    summary_failed_cav = summarize_study(
        results,
        dt_s=0.01,
        allow_cavitation=True,
        max_cavitation_duration_s=0.005,
    )
    assert summary_failed_cav["acceptance"]["passed"] is False

    # Test failed max_pressure
    summary_failed = summarize_study(
        results,
        dt_s=0.01,
        max_pressure=40.0,
        allow_cavitation=True,
        max_cavitation_duration_s=0.05,
    )
    assert "acceptance" in summary_failed
    assert summary_failed["acceptance"]["passed"] is False
    assert len(summary_failed["acceptance"]["violations"]) == 1
    assert summary_failed["acceptance"]["violations"][0]["check"] == "max_pressure"


def test_summarize_study_si_with_acceptance_limits():
    time_s = np.array([0.0, 0.01, 0.02])
    results = {
        "time": time_s,
        "node_head": {"J1": np.array([100.0, 90.0, 95.0])},
        "node_pressure": {"J1": np.array([43.0, 39.0, 41.0])},
        "node_cavitation": {"J1": np.array([0, 1, 0])},
        "pipe_flow_gpm": {"P1": np.array([100.0, -20.0, 50.0])},
    }
    # Test passed max_pressure, min_pressure, allow_cavitation, max_cavitation_duration_s in SI
    summary = summarize_study_si(
        results,
        dt_s=0.01,
        max_pressure=350.0,
        min_pressure=200.0,
        allow_cavitation=True,
        max_cavitation_duration_s=0.05,
    )
    assert "acceptance" in summary
    assert summary["acceptance"]["passed"] is True
    assert summary["acceptance"]["is_si"] is True

    # Test failed min_pressure in SI
    summary_failed_min = summarize_study_si(results, dt_s=0.01, min_pressure=280.0)
    assert summary_failed_min["acceptance"]["passed"] is False

    # Test failed cavitation duration in SI
    summary_failed_cav = summarize_study_si(
        results,
        dt_s=0.01,
        allow_cavitation=True,
        max_cavitation_duration_s=0.005,
    )
    assert summary_failed_cav["acceptance"]["passed"] is False

    # Test failed max_pressure in kPa
    summary_failed = summarize_study_si(
        results,
        dt_s=0.01,
        max_pressure=250.0,
        allow_cavitation=True,
        max_cavitation_duration_s=0.05,
    )
    assert "acceptance" in summary_failed
    assert summary_failed["acceptance"]["passed"] is False
    assert summary_failed["acceptance"]["violations"][0]["check"] == "max_pressure"


def test_study_summary_to_si_converts_acceptance():
    time_s = np.array([0.0, 0.01, 0.02])
    results = {
        "time": time_s,
        "node_head": {"J1": np.array([100.0, 90.0, 95.0])},
        "node_pressure": {"J1": np.array([43.0, 39.0, 41.0])},
        "node_cavitation": {"J1": np.array([0, 0, 0])},
        "pipe_flow_gpm": {"P1": np.array([100.0, -20.0, 50.0])},
    }
    # Run US checks that will fail (actual max 43.0 psi, limit 40.0 psi)
    summary_us = summarize_study(results, dt_s=0.01, max_pressure=40.0, min_pressure=10.0)
    # Convert to SI
    summary_si = study_summary_to_si(summary_us)

    assert "acceptance" in summary_si
    acc_si = summary_si["acceptance"]
    assert acc_si["is_si"] is True
    assert acc_si["passed"] is False
    assert len(acc_si["violations"]) == 1

    v = acc_si["violations"][0]
    assert v["check"] == "max_pressure"
    assert v["limit"] == pytest.approx(40.0 * m.PSI_TO_KPA)
    assert v["actual"] == pytest.approx(43.0 * m.PSI_TO_KPA)
    assert "kPa" in v["message"]

    # Also test subatmospheric/min pressure conversion
    summary_us_min = summarize_study(results, dt_s=0.01, min_pressure=45.0)
    summary_si_min = study_summary_to_si(summary_us_min)
    v_min = summary_si_min["acceptance"]["violations"][0]
    assert v_min["check"] == "min_pressure"
    assert v_min["limit"] == pytest.approx(45.0 * m.PSI_TO_KPA)
    assert v_min["actual"] == pytest.approx(39.0 * m.PSI_TO_KPA)
    assert "subatmospheric minimum pressure violation" in v_min["message"]
    assert "kPa" in v_min["message"]


def test_format_study_table_with_acceptance():
    time_s = np.array([0.0, 0.01, 0.02])
    results = {
        "time": time_s,
        "node_head": {"J1": np.array([100.0, 90.0, 95.0])},
        "node_pressure": {"J1": np.array([43.0, 39.0, 41.0])},
        "node_cavitation": {"J1": np.array([0, 0, 0])},
        "pipe_flow_gpm": {"P1": np.array([100.0, -20.0, 50.0])},
    }
    # US
    summary_us = summarize_study(results, dt_s=0.01, max_pressure=40.0)
    table_us = format_study_table(summary_us)
    assert "ENGINEERING SURGE ANALYSIS ACCEPTANCE REPORT" in table_us
    assert "FAILED" in table_us

    # SI
    summary_si = summarize_study_si(results, dt_s=0.01, max_pressure=250.0)
    table_si = format_study_table_si(summary_si)
    assert "ENGINEERING SURGE ANALYSIS ACCEPTANCE REPORT" in table_si
    assert "FAILED" in table_si
