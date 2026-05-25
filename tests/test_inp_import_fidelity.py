"""Regression tests for EPANET import fidelity (roadmap item 4)."""

from __future__ import annotations

import unittest.mock as mock
from pathlib import Path

import pytest

import rthym_moc as m
from rthym_moc.epanet import (
    _apply_pattern_demands,
    _attach_import_schedules,
    _build_step_schedule,
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


def test_pattern_timestep_defaults_and_invalid_row():
    assert _pattern_timestep_seconds({}) == 3600.0
    assert _pattern_timestep_seconds({"TIMES": [["PATTERN", "TIMESTEP", "bad"]]}) == 3600.0


def test_parse_patterns_skips_malformed_rows():
    sec = {
        "PATTERNS": [
            ["ONLY"],
            ["P2", "not-a-number", "2.0"],
            ["P3"],
        ]
    }
    assert _parse_patterns(sec) == {"P2": [2.0]}


def test_parse_link_controls_open_and_skip_invalid_rows():
    sec = {
        "CONTROLS": [
            ["LINK", "P1", "STATUS", "OPEN", "AT", "TIME", "1"],
            ["LINK", "P2", "SETTING", "10", "AT", "TIME", "1"],
            ["LINK", "P3", "STATUS", "HALF", "AT", "TIME", "1"],
            ["LINK", "P4", "STATUS", "CLOSED", "AT", "CLOCKTIME", "1"],
            ["LINK", "P5", "STATUS", "CLOSED", "AT", "TIME", "x"],
            ["SHORT"],
        ]
    }
    assert _parse_link_controls(sec) == [("P1", "OPEN", 3600.0)]


def test_build_step_schedule_empty_and_duplicate_times():
    assert _build_step_schedule(50.0, []) == [(0.0, 50.0)]
    sched = _build_step_schedule(
        100.0,
        [(10.0, 0.0), (5.0, 50.0), (10.0, 0.0)],
    )
    assert sched == [(0.0, 100.0), (5.0, 50.0), (10.0, 0.0)]


def test_apply_pattern_demands_skips_non_junctions():
    r1 = m.NodeInput()
    r1.id = "R1"
    r1.type = "PressureBoundary"
    j1 = m.NodeInput()
    j1.id = "J1"
    j1.type = "Junction"
    j1.demand = 0.0
    nodes = {"R1": r1, "J1": j1}
    _apply_pattern_demands(
        nodes,
        {"P1": [3.0]},
        {"R1": 5.0, "J1": 4.0, "GHOST": 1.0},
        {"J1": "P1", "GHOST": "P1"},
    )
    assert j1.demand == pytest.approx(12.0)
    assert r1.type == "PressureBoundary"


def test_attach_import_schedules_rules_warning():
    solver = m.MOCSolver()
    with pytest.warns(UserWarning, match="RULES"):
        _attach_import_schedules(
            solver,
            {"RULES": [["IF", "TANK", "LEVEL", "BELOW", "1"]]},
            {},
            {},
            {},
            [],
            [],
            {},
            {},
        )


def test_load_inp_warns_on_rules_and_non_link_controls(tmp_path: Path):
    inp_path = tmp_path / "minimal.inp"
    inp_path.write_text(
        """[JUNCTIONS]
J1 0 10

[RESERVOIRS]
R1 100
R2 80

[PIPES]
P1 R1 J1 100 12 130 0 OPEN
P2 J1 R2 100 12 130 0 OPEN

[RULES]
IF TANK LEVEL BELOW 1 THEN PUMP P1 STATUS IS CLOSED

[CONTROLS]
NODE J1 STATUS OPEN AT TIME 1
LINK P99 STATUS CLOSED AT TIME 0.01

[OPTIONS]
UNITS GPM
HEADLOSS H-W
""",
        encoding="utf-8",
    )
    with pytest.warns(UserWarning) as caught:
        m.load_inp(str(inp_path), use_wntr=False, initial_flows={"P1": 10.0, "P2": 10.0})
    messages = " ".join(str(w.message) for w in caught)
    assert "RULES" in messages
    assert "unsupported object types" in messages


def test_load_inp_skips_invalid_demands_row(tmp_path: Path):
    inp_path = tmp_path / "demands.inp"
    inp_path.write_text(
        """[JUNCTIONS]
J1 0 10
J2 0 0

[RESERVOIRS]
R1 100
R2 80

[PIPES]
P1 R1 J1 100 12 130 0 OPEN
P2 J1 J2 100 12 130 0 OPEN
P3 J2 R2 100 12 130 0 OPEN

[DEMANDS]
J2 bad

[OPTIONS]
UNITS GPM
HEADLOSS H-W
""",
        encoding="utf-8",
    )
    added: dict[str, m.NodeInput] = {}
    original = m.MOCSolver.add_node

    def capture(self, node):
        added[node.id] = node
        return original(self, node)

    with mock.patch.object(m.MOCSolver, "add_node", capture):
        m.load_inp(str(inp_path), use_wntr=False, initial_flows={"P1": 10.0, "P2": 10.0, "P3": 10.0})
    assert added["J2"].demand == 0.0


def test_load_inp_pump_open_control_schedule(tmp_path: Path):
    inp_path = tmp_path / "pump_open.inp"
    inp_path.write_text(
        """[JUNCTIONS]
J1 0 0
J2 0 0

[RESERVOIRS]
R1 120
R2 80

[PIPES]
P3 J2 R2 200 12 130 0 OPEN

[PUMPS]
PU1 R1 J1 HEAD C1

[VALVES]
V1 J1 J2 12 TCV 100

[CURVES]
C1 0 80

[CONTROLS]
LINK PU1 STATUS OPEN AT TIME 0.01

[OPTIONS]
UNITS GPM
HEADLOSS H-W
""",
        encoding="utf-8",
    )
    pump_schedules: list[tuple[str, list]] = []

    def capture_pump(self, node_id, schedule):
        pump_schedules.append((node_id, list(schedule)))

    with mock.patch.object(m.MOCSolver, "set_pump_schedule", capture_pump):
        m.load_inp(str(inp_path), use_wntr=False, initial_flows={"P3": 50.0, "PU1": 50.0, "V1": 50.0})

    pump = next(s for nid, s in pump_schedules if nid == "_PUMP_PU1")
    assert pump[-1] == (pytest.approx(0.01 * 3600.0), 100.0)


def test_load_inp_single_point_pattern_no_demand_schedule(tmp_path: Path):
    inp_path = tmp_path / "single_pat.inp"
    inp_path.write_text(
        """[JUNCTIONS]
J1 0 10 PAT1

[RESERVOIRS]
R1 100
R2 80

[PIPES]
P1 R1 J1 100 12 130 0 OPEN
P2 J1 R2 100 12 130 0 OPEN

[PATTERNS]
PAT1 1.5

[OPTIONS]
UNITS GPM
HEADLOSS H-W
""",
        encoding="utf-8",
    )
    demand_schedules: list[str] = []

    def capture_demand(self, node_id, schedule):
        demand_schedules.append(node_id)

    with mock.patch.object(m.MOCSolver, "set_demand_schedule", capture_demand):
        m.load_inp(str(inp_path), use_wntr=False, initial_flows={"P1": 10.0, "P2": 10.0})
    assert demand_schedules == []


def test_load_inp_valve_head_falls_back_to_downstream_junction(tmp_path: Path):
    inp_path = tmp_path / "valve_heads.inp"
    inp_path.write_text(
        """[JUNCTIONS]
J1 0 0
J2 0 0

[RESERVOIRS]
R1 100
R2 80

[PIPES]
P1 R1 J1 100 12 130 0 OPEN
P2 J1 J2 100 12 130 0 OPEN
P3 J2 R2 100 12 130 0 OPEN

[VALVES]
V1 J1 J2 12 TCV 50

[OPTIONS]
UNITS GPM
HEADLOSS H-W
""",
        encoding="utf-8",
    )
    added: dict[str, m.NodeInput] = {}
    original = m.MOCSolver.add_node

    def capture(self, node):
        added[node.id] = node
        return original(self, node)

    with mock.patch.object(m.MOCSolver, "add_node", capture):
        m.load_inp(
            str(inp_path),
            use_wntr=False,
            initial_flows={"P1": 10.0, "P2": 10.0, "P3": 10.0, "V1": 10.0},
            initial_heads={"J2": 95.0},
        )
    assert added["_VALVE_V1"].head == pytest.approx(95.0)
