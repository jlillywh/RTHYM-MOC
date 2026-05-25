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
    export_study_json,
    format_study_table,
    series_extrema,
    summarize_study,
)


def test_series_extrema_finds_times():
    t = np.array([0.0, 1.0, 2.0, 3.0])
    y = np.array([10.0, 5.0, 20.0, 12.0])
    ext = series_extrema(t, y)
    assert ext["min"] == pytest.approx(5.0)
    assert ext["min_time_s"] == pytest.approx(1.0)
    assert ext["max"] == pytest.approx(20.0)
    assert ext["max_time_s"] == pytest.approx(2.0)


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
