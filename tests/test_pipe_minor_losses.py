"""Pipe/link minor-loss regressions for direct and INP-loaded models."""

from pathlib import Path

import numpy as np
import pytest
import rthym_moc


def _make_node(node_id, node_type, **kwargs):
    node = rthym_moc.NodeInput()
    node.id = node_id
    node.type = node_type
    for key, value in kwargs.items():
        setattr(node, key, value)
    return node


def _make_pipe(pipe_id, from_node, to_node, **kwargs):
    pipe = rthym_moc.PipeInput()
    pipe.id = pipe_id
    pipe.from_node = from_node
    pipe.to_node = to_node
    for key, value in kwargs.items():
        setattr(pipe, key, value)
    return pipe


def _mean_over_window(time_s, values, start_s, end_s):
    mask = (time_s >= start_s) & (time_s <= end_s)
    assert np.any(mask), f"No samples found in window [{start_s}, {end_s}] s"
    return float(np.asarray(values)[mask].mean())


def _run_direct_case(minor_loss):
    solver = rthym_moc.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=150.0))
    solver.add_node(_make_node("R2", "PressureBoundary", head=120.0))
    solver.add_pipe(
        _make_pipe(
            "P1",
            "R1",
            "R2",
            length=1100.0,
            diameter=12.0,
            roughness=130.0,
            minor_loss=minor_loss,
            flow_gpm=800.0,
        )
    )
    return solver.run(total_time=2.0, dt=0.01)


def test_pipe_minor_loss_reduces_steady_through_flow_in_direct_solver():
    """A larger pipe minor-loss coefficient should reduce through-flow at fixed heads."""
    low_loss = _run_direct_case(minor_loss=0.0)
    high_loss = _run_direct_case(minor_loss=100.0)
    time_s = np.asarray(low_loss["time"])
    low_flow_gpm = _mean_over_window(time_s, low_loss["pipe_flow_gpm"]["P1"], 0.5, 1.5)
    high_flow_gpm = _mean_over_window(time_s, high_loss["pipe_flow_gpm"]["P1"], 0.5, 1.5)

    assert low_flow_gpm - high_flow_gpm >= 25.0, (
        f"Expected a larger pipe minor-loss coefficient to reduce steady flow by at least 25 GPM, got {low_flow_gpm - high_flow_gpm:.2f} GPM"
    )


def test_load_inp_imports_pipe_minor_loss(tmp_path):
    """EPANET pipe minor-loss coefficients should affect the imported pipe response."""
    def run_case(minor_loss):
        inp = f"""
[TITLE]
Pipe Minor Loss Import

[OPTIONS]
UNITS GPM
HEADLOSS H-W

[RESERVOIRS]
R1 150
R2 120

[PIPES]
P1 R1 R2 1100 12 130 {minor_loss} Open

[END]
""".strip()
        path = Path(tmp_path) / f"minor_loss_case_{int(minor_loss)}.inp"
        path.write_text(inp, encoding="utf-8")

        solver = rthym_moc.load_inp(str(path), use_wntr=False, initial_flows={"P1": 800.0})
        results = solver.run(total_time=2.0, dt=0.01)
        time_s = np.asarray(results["time"])
        return _mean_over_window(time_s, results["pipe_flow_gpm"]["P1"], 0.5, 1.5)

    low_loss_flow_gpm = run_case(0.0)
    high_loss_flow_gpm = run_case(100.0)

    assert low_loss_flow_gpm - high_loss_flow_gpm >= 25.0, (
        f"Expected the imported pipe minor loss to reduce steady flow by at least 25 GPM, got {low_loss_flow_gpm - high_loss_flow_gpm:.2f} GPM"
    )
