"""Regression tests for EPANET import fidelity (roadmap item 4)."""

from __future__ import annotations

import unittest.mock as mock
from pathlib import Path

import pytest

import rthym_moc as m
import numpy as np

from rthym_moc.epanet import (
    _apply_pattern_demands,
    _attach_import_schedules,
    _build_step_schedule,
    _parse_link_controls,
    _parse_patterns,
    _parse_rthym_pipe_elevation_profiles,
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


def test_parse_rthym_pipe_elevation_profiles_us_and_si() -> None:
    sec = {
        "RTHYM": [
            ["P1", "PipeElevation", "0=100", "500=250", "1000=200"],
            ["J1", "Standpipe", "tank_area=1.0"],
        ]
    }
    us = _parse_rthym_pipe_elevation_profiles(sec, "GPM")
    assert us == {"P1": [(0.0, 100.0), (500.0, 250.0), (1000.0, 200.0)]}

    sec_si = {
        "RTHYM": [
            ["P1", "PipeElevation", "0=30.48", "152.4=91.44", "304.8=60.96"],
        ]
    }
    si = _parse_rthym_pipe_elevation_profiles(sec_si, "LPS")
    assert si["P1"][0][0] == pytest.approx(0.0, abs=1e-6)
    assert si["P1"][1][0] == pytest.approx(500.0, rel=1e-3)
    assert si["P1"][1][1] == pytest.approx(300.0, rel=1e-3)


def test_load_inp_applies_rthym_pipe_elevation_profile(tmp_path: Path) -> None:
    inp_path = tmp_path / "rthym_pipe_elev.inp"
    inp_path.write_text(
        """[TITLE]
Pipe elevation survey

[JUNCTIONS]
J1   100        0
J2   200        0

[RESERVOIRS]
R1   350
R2   350

[PIPES]
P1   R1  J1  1000    12        130        0
P2   J1  J2  1000    12        130        0
P3   J2  R2  1000    12        130        0

[RTHYM]
P2   PipeElevation   0=100   500=300   1000=200

[OPTIONS]
UNITS GPM
HEADLOSS H-W

[END]
""",
        encoding="utf-8",
    )

    added_pipes: dict[str, m.PipeInput] = {}
    original_add_pipe = m.MOCSolver.add_pipe

    def capture_pipe(self, pipe):
        added_pipes[pipe.id] = pipe
        return original_add_pipe(self, pipe)

    with mock.patch.object(m.MOCSolver, "add_pipe", capture_pipe):
        solver = m.load_inp(
            str(inp_path),
            use_wntr=False,
            initial_flows={"P1": 0.0, "P2": 0.0, "P3": 0.0},
        )

    assert added_pipes["P1"].elevation_profile == []
    assert added_pipes["P2"].elevation_profile == [(0.0, 100.0), (500.0, 300.0), (1000.0, 200.0)]
    assert added_pipes["P3"].elevation_profile == []

    survey = added_pipes["P2"].elevation_profile
    results = solver.run(total_time=0.05, dt=0.01, record_pipe_profiles=True)
    chainage = np.asarray(results["pipe_profile_chainage_ft"]["P2"])
    head = np.asarray(results["pipe_profile_head"]["P2"])
    pressure = np.asarray(results["pipe_profile_pressure"]["P2"])
    summit_idx = int(np.argmin(np.abs(chainage - 500.0)))
    x_ft = float(chainage[summit_idx])

    def _survey_z_ft(chainage_ft: float) -> float:
        ordered = sorted(survey, key=lambda pair: pair[0])
        if chainage_ft <= ordered[0][0]:
            return ordered[0][1]
        if chainage_ft >= ordered[-1][0]:
            return ordered[-1][1]
        for (x0, z0), (x1, z1) in zip(ordered, ordered[1:]):
            if chainage_ft <= x1:
                frac = (chainage_ft - x0) / (x1 - x0)
                return z0 + frac * (z1 - z0)
        return ordered[-1][1]

    z_at = _survey_z_ft(x_ft)
    z_linear = 100.0 + (x_ft / 1000.0) * (200.0 - 100.0)

    assert pressure[0, summit_idx] == pytest.approx(
        (head[0, summit_idx] - z_at) / m.PSI_TO_FT,
        rel=1e-6,
    )
    assert pressure[0, summit_idx] < (head[0, summit_idx] - z_linear) / m.PSI_TO_FT


def test_parse_rthym_pipe_elevation_requires_two_points_warns() -> None:
    sec = {"RTHYM": [["P1", "PipeElevation", "0=10"]]}
    with pytest.warns(UserWarning, match="at least two chainage=elevation"):
        assert _parse_rthym_pipe_elevation_profiles(sec, "GPM") == {}


def test_load_inp_rthym_pipe_elevation_unknown_pipe_warns(tmp_path: Path) -> None:
    inp_path = tmp_path / "missing_pipe_elev.inp"
    inp_path.write_text(
        """[JUNCTIONS]
J1   0   0
J2   0   0
[RESERVOIRS]
R1   100
R2   100
[PIPES]
P1   R1  J1  100   12   130   0
P2   J1  R2  100   12   130   0
[RTHYM]
PX   PipeElevation   0=0   100=10
[OPTIONS]
UNITS GPM
HEADLOSS H-W
[END]
""",
        encoding="utf-8",
    )

    with pytest.warns(UserWarning, match="unknown \\[PIPES\\] link"):
        m.load_inp(str(inp_path), use_wntr=False, initial_flows={"P1": 0.0, "P2": 0.0})
