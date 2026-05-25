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

    assert protected_window_mean_gpm >= -1.0, (
        f"Expected the check valve to block reverse through-flow, got mean {protected_window_mean_gpm:.2f} GPM"
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

    assert protected_window_mean_gpm >= -10.0, (
        f"Expected imported CV protection to keep mean reverse through-flow near zero, got mean {protected_window_mean_gpm:.2f} GPM"
    )
    assert open_window_mean_gpm <= -200.0, (
        f"Expected the imported open-pipe comparison case to reverse materially, got mean {open_window_mean_gpm:.2f} GPM"
    )
    assert protected_window_mean_gpm - open_window_mean_gpm >= 500.0, (
        f"Expected imported CV protection to materially reduce reverse flow relative to the open pipe, got protected {protected_window_mean_gpm:.2f} GPM and open {open_window_mean_gpm:.2f} GPM"
    )