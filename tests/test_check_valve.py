"""Check-valve regressions for reverse-flow protection."""

import numpy as np
from pathlib import Path

import rthym_moc as m


DT_S = 0.01
TOTAL_TIME_S = 0.4


def _make_node(node_id, node_type, **kwargs):
    node = m.NodeInput()
    node.id = node_id
    node.type = node_type
    for key, value in kwargs.items():
        setattr(node, key, value)
    return node


def _make_pipe(pipe_id, from_node, to_node, flow_gpm):
    pipe = m.PipeInput()
    pipe.id = pipe_id
    pipe.from_node = from_node
    pipe.to_node = to_node
    pipe.length = 40.0
    pipe.diameter = 12.0
    pipe.roughness = 130.0
    pipe.flow_gpm = flow_gpm
    return pipe


def _run_reversal_case(mid_node_type):
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=160.0))
    solver.add_node(_make_node("X1", mid_node_type, head=150.0, diameter=12.0, current_setting=100.0))
    solver.add_node(_make_node("R2", "PressureBoundary", head=140.0))
    solver.add_pipe(_make_pipe("P1", "R1", "X1", 500.0))
    solver.add_pipe(_make_pipe("P2", "X1", "R2", 500.0))
    solver.set_head_schedule(
        "R2",
        [
            (0.0, 140.0),
            (0.09, 140.0),
            (0.1, 260.0),
            (TOTAL_TIME_S, 260.0),
        ],
    )
    return solver.run(total_time=TOTAL_TIME_S, dt=DT_S)


def test_check_valve_blocks_reverse_flow_when_downstream_head_exceeds_upstream():
    """An inline CheckValve should clamp reverse through-flow that a plain junction allows."""
    protected = _run_reversal_case("CheckValve")
    unprotected = _run_reversal_case("Junction")

    time_s = np.asarray(protected["time"])
    protected_flow_gpm = np.asarray(protected["pipe_flow_gpm"]["P2"])
    unprotected_flow_gpm = np.asarray(unprotected["pipe_flow_gpm"]["P2"])
    window = (time_s >= 0.22) & (time_s <= 0.34)

    assert np.any(window), "Expected a non-empty post-reversal comparison window"

    protected_window_mean_gpm = float(protected_flow_gpm[window].mean())
    unprotected_window_mean_gpm = float(unprotected_flow_gpm[window].mean())

    # Exponential closure allows some reverse flow during closure_time
    assert protected_window_mean_gpm >= -6.0, (
        f"Expected the check valve to block most reverse through-flow (exponential closure), got mean {protected_window_mean_gpm:.2f} GPM"
    )
    assert unprotected_window_mean_gpm <= -200.0, (
        f"Expected the plain junction case to reverse materially, got mean {unprotected_window_mean_gpm:.2f} GPM"
    )


def _write_inp_case(path: Path, p2_status: str) -> None:
    path.write_text(
        f"""[TITLE]
Check valve import regression

[JUNCTIONS]
;ID  Elevation  Demand
J1   0          0

[RESERVOIRS]
;ID  Head
R1   160
R2   140

[PIPES]
;ID  Node1  Node2  Length  Diameter  Roughness  MinorLoss  Status
P1   R1     J1     40      12        130        0          OPEN
P2   J1     R2     40      12        130        0          {p2_status}

[OPTIONS]
UNITS GPM
HEADLOSS H-W

[END]
""",
        encoding="utf-8",
    )


def test_load_inp_maps_cv_pipe_to_generated_check_valve_and_blocks_reversal(tmp_path: Path):
    """EPANET CV pipes should import as generated CheckValve devices rather than ordinary pipes."""
    inp_path = tmp_path / "cv_pipe.inp"
    _write_inp_case(inp_path, "CV")

    solver = m.load_inp(
        str(inp_path),
        use_wntr=False,
        initial_flows={"P1": 500.0, "P2": 500.0},
        initial_heads={"J1": 150.0},
    )
    solver.set_head_schedule(
        "R2",
        [
            (0.0, 140.0),
            (0.09, 140.0),
            (0.1, 260.0),
            (TOTAL_TIME_S, 260.0),
        ],
    )
    results = solver.run(total_time=TOTAL_TIME_S, dt=DT_S)

    assert "_CHECKVALVE_P2" in results["node_head"], "Expected load_inp() to generate an inline CheckValve node for CV pipe P2"
    assert "_CV_P2_up" in results["pipe_flow_gpm"], "Expected load_inp() to split the CV pipe into an upstream check-valve stub"
    assert "_CV_P2_dn" in results["pipe_flow_gpm"], "Expected load_inp() to split the CV pipe into a downstream check-valve stub"
    assert "P2" not in results["pipe_flow_gpm"], "Expected the original CV pipe id to be replaced by generated check-valve stubs"

    time_s = np.asarray(results["time"])
    protected_flow_gpm = np.asarray(results["pipe_flow_gpm"]["_CV_P2_dn"])
    window = (time_s >= 0.22) & (time_s <= 0.34)
    protected_window_mean_gpm = float(protected_flow_gpm[window].mean())

    open_inp_path = tmp_path / "open_pipe.inp"
    _write_inp_case(open_inp_path, "OPEN")
    open_solver = m.load_inp(
        str(open_inp_path),
        use_wntr=False,
        initial_flows={"P1": 500.0, "P2": 500.0},
        initial_heads={"J1": 150.0},
    )
    open_solver.set_head_schedule(
        "R2",
        [
            (0.0, 140.0),
            (0.09, 140.0),
            (0.1, 260.0),
            (TOTAL_TIME_S, 260.0),
        ],
    )
    open_results = open_solver.run(total_time=TOTAL_TIME_S, dt=DT_S)
    open_flow_gpm = np.asarray(open_results["pipe_flow_gpm"]["P2"])
    open_window_mean_gpm = float(open_flow_gpm[window].mean())

    # Exponential closure allows some reverse flow during closure_time
    assert protected_window_mean_gpm >= -40.0, (
        f"Expected imported CV protection to keep mean reverse through-flow within exponential closure range, got mean {protected_window_mean_gpm:.2f} GPM"
    )
    assert open_window_mean_gpm <= -200.0, (
        f"Expected the imported open-pipe comparison case to reverse materially, got mean {open_window_mean_gpm:.2f} GPM"
    )
    assert protected_window_mean_gpm - open_window_mean_gpm >= 500.0, (
        f"Expected imported CV protection to materially reduce reverse flow relative to the open pipe, got protected {protected_window_mean_gpm:.2f} GPM and open {open_window_mean_gpm:.2f} GPM"
    )


def test_check_valve_closure_dynamics():
    """CheckValve with closure_time > 0 closes gradually, not instantly, and valve_position transitions from 1 to 0."""
    solver = m.MOCSolver()
    # Upstream reservoir, check valve, downstream reservoir
    solver.add_node(_make_node("R1", "PressureBoundary", head=160.0))
    solver.add_node(_make_node("X1", "CheckValve", head=150.0, diameter=12.0, closure_time=0.1))
    solver.add_node(_make_node("R2", "PressureBoundary", head=140.0))
    solver.add_pipe(_make_pipe("P1", "R1", "X1", 500.0))
    solver.add_pipe(_make_pipe("P2", "X1", "R2", 500.0))
    solver.set_head_schedule(
        "R2",
        [
            (0.0, 140.0),
            (0.09, 140.0),
            (0.1, 260.0),  # At t=0.1s, force reversal
            (TOTAL_TIME_S, 260.0),
        ],
    )
    results = solver.run(total_time=TOTAL_TIME_S, dt=DT_S)
    # The valve should not close instantly: valve_position should decrease gradually
    time_s = np.asarray(results["time"])
    try:
        valve_pos = np.asarray(results["valve_position"]["X1"])
    except KeyError:
        raise AssertionError("valve_position telemetry not exposed in results; closure dynamics not testable")
    # Find when closure is actually triggered (first time valve_position < 1.0)
    trigger_indices = np.where(valve_pos < 0.999)[0]
    assert trigger_indices.size > 0, "Valve never started closing!"
    idx_trigger = trigger_indices[0]
    t_trigger = time_s[idx_trigger]
    # Valve should be open before closure trigger
    assert valve_pos[idx_trigger-1] > 0.95, f"Valve should be open before closure trigger, got {valve_pos[idx_trigger-1]}"
    # Valve should close exponentially: after closure_time, pos ≈ exp(-1) ≈ 0.37
    closure_time = 0.1
    idx_end = np.searchsorted(time_s, t_trigger + closure_time)
    expected_exp = np.exp(-1)
    assert abs(valve_pos[idx_end] - expected_exp) < 0.1, (
        f"Valve should be exponentially closed after closure_time from trigger, expected ≈{expected_exp:.2f}, got {valve_pos[idx_end]:.5f}"
    )
    # Should not close instantly
    assert valve_pos[idx_trigger] > 0.5, f"Valve should not close instantly at trigger, got {valve_pos[idx_trigger]}"
    # If flow resumes forward, valve should reopen (optional, not forced here)

def test_load_inp_with_rthym_check_valve_overrides(tmp_path: Path):
    """It should parse closure_time and flipped parameters from [RTHYM] for CheckValves."""
    inp_path = tmp_path / "rthym_cv.inp"
    inp_path.write_text(
        """[TITLE]
Check valve override test

[JUNCTIONS]
J1   0          0
J2   0          0

[RESERVOIRS]
R1   160
R2   140

[PUMPS]
PU1  R1  J1  100

[VALVES]
VA1  J1  J2  12  TCV  10

[PIPES]
P2   J2  R2  40      12        130        0          CV

[RTHYM]
_CHECKVALVE_P2 CheckValve closure_time=2.5 flipped=1
_PUMP_PU1 Pump
_VALVE_VA1 Valve
INVALID_NODE Standpipe

[OPTIONS]
UNITS GPM
HEADLOSS H-W

[END]
""",
        encoding="utf-8",
    )

    solver = m.load_inp(
        str(inp_path),
        use_wntr=False,
        initial_flows={"P1": 500.0, "P2": 500.0},
        initial_heads={"J1": 150.0},
    )

    results = solver.run(total_time=TOTAL_TIME_S, dt=DT_S)

    assert "_CHECKVALVE_P2" in results["valve_position"], "Expected check valve node in valve_position telemetry"
    valve_pos = np.asarray(results["valve_position"]["_CHECKVALVE_P2"])

    # Since flipped=True and we have positive initial flow, it will immediately experience
    # a reverse-flow tendency and begin closing from t=0.
    # At the end of the simulation (0.4s), position should be roughly exp(-0.4/2.5) ≈ 0.852.
    assert 0.80 < valve_pos[-1] < 0.90, f"Expected final position around 0.85, got {valve_pos[-1]:.4f}"


def test_load_inp_with_all_rthym_overrides(tmp_path: Path):
    """It should parse all override types (CheckValve, Standpipe, HydropneumaticTank, AirValve)
    and look them up correctly in junctions/nodes, pump_nodes, and valve_nodes.
    """
    import unittest.mock as mock

    inp_path = tmp_path / "rthym_all_overrides.inp"
    inp_path.write_text(
        """[TITLE]
All overrides test

[JUNCTIONS]
J1   0          0
J2   0          0

[RESERVOIRS]
R1   160
R2   140

[PUMPS]
PU1  R1  J1  100

[VALVES]
VA1  J1  J2  12  TCV  10

[PIPES]
P2   J2  R2  40      12        130        0          CV

[RTHYM]
_CHECKVALVE_P2 CheckValve closure_time=2.5 flipped=1
_PUMP_PU1 AirValve diameter=2.0 air_release_head=10.0 air_release_diameter=0.5 gas_volume=0.1 tank_volume=1.0 loss_coeff_in=0.6 loss_coeff_out=0.8
_VALVE_VA1 HydropneumaticTank gas_volume=5.0 tank_volume=50.0 polytropic_n=1.3 loss_coeff_in=0.5 loss_coeff_out=0.6 diameter=4.0
J1 Standpipe tank_area=1.5
INVALID_NODE Standpipe
MALFORMED_ROW CheckValve closure_time=abc

[OPTIONS]
UNITS GPM
HEADLOSS H-W

[END]
""",
        encoding="utf-8",
    )

    added_nodes = {}
    original_add_node = m.MOCSolver.add_node

    def mock_add_node(self, node):
        added_nodes[node.id] = node
        return original_add_node(self, node)

    with mock.patch.object(m.MOCSolver, "add_node", mock_add_node):
        solver = m.load_inp(
            str(inp_path),
            use_wntr=False,
            initial_flows={"P1": 500.0, "P2": 500.0},
            initial_heads={"J1": 150.0},
        )

    # 1. Check check valve overrides
    cv_node = added_nodes["_CHECKVALVE_P2"]
    assert cv_node.type == "CheckValve"
    assert cv_node.closure_time == 2.5
    assert cv_node.flipped is True

    # 2. Check pump override to AirValve and its properties
    pump_node = added_nodes["_PUMP_PU1"]
    assert pump_node.type == "AirValve"
    assert pump_node.diameter == 2.0
    assert pump_node.air_release_head == 10.0
    assert pump_node.air_release_diameter == 0.5
    assert pump_node.gas_volume == 0.1
    assert pump_node.tank_volume == 1.0
    assert pump_node.loss_coeff_in == 0.6
    assert pump_node.loss_coeff_out == 0.8

    # 3. Check valve override to HydropneumaticTank and its properties
    valve_node = added_nodes["_VALVE_VA1"]
    assert valve_node.type == "HydropneumaticTank"
    assert valve_node.gas_volume == 5.0
    assert valve_node.tank_volume == 50.0
    assert valve_node.polytropic_n == 1.3
    assert valve_node.loss_coeff_in == 0.5
    assert valve_node.loss_coeff_out == 0.6
    assert valve_node.diameter == 4.0

    # 4. Check junction override to Standpipe and its properties
    j1_node = added_nodes["J1"]
    assert j1_node.type == "Standpipe"
    assert j1_node.tank_area == 1.5
