"""Regression tests for EPANET import fidelity (roadmap item 4)."""

from __future__ import annotations

import unittest.mock as mock
from pathlib import Path

import pytest

import rthym_moc as m
from rthym_moc.epanet import (
    _parse_link_controls,
    _parse_patterns,
    _pattern_timestep_seconds,
)


NETWORK_PATH = Path(__file__).resolve().parent / "networks" / "import_fidelity.inp"


def test_parse_patterns_and_controls_helpers():
    sec = {
        "PATTERNS": [["PAT1", "2.0", "1.0", "0.5"]],
        "CONTROLS": [
            ["LINK", "PU1", "STATUS", "CLOSED", "AT", "TIME", "0.02"],
            ["NODE", "J1", "STATUS", "OPEN", "AT", "TIME", "1"],
        ],
        "TIMES": [["PATTERN", "TIMESTEP", "0.01"]],
    }
    assert _parse_patterns(sec) == {"PAT1": [2.0, 1.0, 0.5]}
    assert _pattern_timestep_seconds(sec) == pytest.approx(0.01 * 3600.0)
    events = _parse_link_controls(sec)
    assert events == [("PU1", "CLOSED", pytest.approx(0.02 * 3600.0))]


def test_load_inp_applies_pattern_multiplier_to_junction_demand():
    added: dict[str, m.NodeInput] = {}
    original = m.MOCSolver.add_node

    def capture(self, node):
        added[node.id] = node
        return original(self, node)

    with mock.patch.object(m.MOCSolver, "add_node", capture):
        m.load_inp(
            str(NETWORK_PATH),
            use_wntr=False,
            initial_flows={
                "P3": 50.0,
                "PU1": 50.0,
                "V1": 50.0,
                "_P_PU1_up": 50.0,
                "_P_PU1_dn": 50.0,
                "_P_V1_up": 50.0,
                "_P_V1_dn": 50.0,
            },
        )

    assert added["J1"].demand == pytest.approx(20.0)  # 10 * PAT1[0]=2.0
    assert added["J2"].demand == pytest.approx(10.0)  # (0+5) * 2.0


def test_load_inp_attaches_pattern_and_control_schedules():
    pump_schedules: list[tuple[str, list]] = []
    valve_schedules: list[tuple[str, list]] = []
    demand_schedules: list[tuple[str, list]] = []

    def capture_pump(self, node_id, schedule):
        pump_schedules.append((node_id, list(schedule)))

    def capture_valve(self, node_id, schedule):
        valve_schedules.append((node_id, list(schedule)))

    def capture_demand(self, node_id, schedule):
        demand_schedules.append((node_id, list(schedule)))

    with (
        mock.patch.object(m.MOCSolver, "set_pump_schedule", capture_pump),
        mock.patch.object(m.MOCSolver, "set_valve_schedule", capture_valve),
        mock.patch.object(m.MOCSolver, "set_demand_schedule", capture_demand),
    ):
        m.load_inp(
            str(NETWORK_PATH),
            use_wntr=False,
            initial_flows={"P3": 50.0, "PU1": 50.0, "V1": 50.0},
        )

    assert demand_schedules, "Expected demand schedules from multi-point PAT1"
    j1_sched = next(s for nid, s in demand_schedules if nid == "J1")
    assert j1_sched[0] == (0.0, pytest.approx(20.0))
    assert j1_sched[1][1] == pytest.approx(10.0)

    assert any(nid == "_PUMP_PU1" for nid, _ in pump_schedules)
    pump = next(s for nid, s in pump_schedules if nid == "_PUMP_PU1")
    assert pump[-1] == (pytest.approx(0.02 * 3600.0), 0.0)

    assert any(nid == "_VALVE_V1" for nid, _ in valve_schedules)
    valve = next(s for nid, s in valve_schedules if nid == "_VALVE_V1")
    assert valve[-1] == (pytest.approx(0.03 * 3600.0), 0.0)
