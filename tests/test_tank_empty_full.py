"""Unit tests for hydropneumatic tank empty and full boundaries."""

import pytest
import rthym_moc as m


def _make_node(node_id, node_type, **kwargs):
    node = m.NodeInput()
    node.id = node_id
    node.type = node_type
    for key, value in kwargs.items():
        setattr(node, key, value)
    return node


def _make_pipe(pipe_id, from_node, to_node, **kwargs):
    pipe = m.PipeInput()
    pipe.id = pipe_id
    pipe.from_node = from_node
    pipe.to_node = to_node
    for key, value in kwargs.items():
        setattr(pipe, key, value)
    return pipe


def test_tank_empty_boundary():
    """Verify that a hydropneumatic tank that becomes empty halts outflow and stabilizes HGL."""
    solver = m.MOCSolver()

    solver.add_node(_make_node("R1", "PressureBoundary", head=100.0))
    solver.add_node(
        _make_node(
            "HPT",
            "HydropneumaticTank",
            head=100.0,
            elevation=0.0,
            diameter=4.0,
            gas_volume=9.8,  # Starts almost empty (V_tank = 10.0)
            tank_volume=10.0,
            polytropic_n=1.2,
            loss_coeff_in=0.7,
            loss_coeff_out=0.7,
        )
    )
    solver.add_node(_make_node("R2", "PressureBoundary", head=50.0))

    solver.add_pipe(_make_pipe("P1", "R1", "HPT", length=100.0, diameter=6.0, roughness=130.0, flow_gpm=100.0))
    solver.add_pipe(_make_pipe("P2", "HPT", "R2", length=100.0, diameter=6.0, roughness=130.0, flow_gpm=100.0))

    # Run simulation - water should leave HPT, hitting empty boundary
    solver.run(total_time=2.0, dt=0.01)

    final_vol = solver.get_node_gas_volume("HPT")
    final_flow = solver.get_node_tank_flow_gpm("HPT")

    # Should be clamped exactly to tank volume (10.0 ft3)
    assert final_vol <= 10.0
    assert final_vol >= 10.0 - 1e-4
    assert abs(final_flow) < 1e-3


def test_tank_full_boundary_clamping():
    """Verify that a flooded (gas_volume = 0) tank immediately blocks inflow."""
    solver = m.MOCSolver()

    solver.add_node(_make_node("R1", "PressureBoundary", head=150.0))
    solver.add_node(
        _make_node(
            "HPT",
            "HydropneumaticTank",
            head=100.0,
            elevation=0.0,
            diameter=4.0,
            gas_volume=0.0,  # Flooded
            tank_volume=10.0,
            polytropic_n=1.2,
            loss_coeff_in=0.7,
            loss_coeff_out=0.7,
        )
    )
    solver.add_node(_make_node("R2", "PressureBoundary", head=100.0))

    solver.add_pipe(_make_pipe("P1", "R1", "HPT", length=100.0, diameter=6.0, roughness=130.0, flow_gpm=100.0))
    solver.add_pipe(_make_pipe("P2", "HPT", "R2", length=100.0, diameter=6.0, roughness=130.0, flow_gpm=100.0))

    # Run simulation - high upstream pressure would normally push water in, but it is blocked
    solver.run(total_time=2.0, dt=0.01)

    final_vol = solver.get_node_gas_volume("HPT")
    final_flow = solver.get_node_tank_flow_gpm("HPT")

    # Volume should remain 0, and flow should be 0
    assert final_vol == 0.0
    assert abs(final_flow) < 1e-3


def test_tank_full_boundary_recovery():
    """Verify that a tank that becomes flooded during a transient can still recover and discharge water."""
    solver = m.MOCSolver()

    solver.add_node(_make_node("R1", "PressureBoundary", head=100.0))
    solver.add_node(
        _make_node(
            "HPT",
            "HydropneumaticTank",
            head=100.0,
            elevation=0.0,
            diameter=4.0,
            gas_volume=0.05,  # Starts almost full (V_tank = 10.0)
            tank_volume=10.0,
            polytropic_n=1.2,
            loss_coeff_in=0.7,
            loss_coeff_out=0.7,
        )
    )
    solver.add_node(_make_node("R2", "PressureBoundary", head=100.0))

    solver.add_pipe(_make_pipe("P1", "R1", "HPT", length=100.0, diameter=6.0, roughness=130.0, flow_gpm=0.0))
    solver.add_pipe(_make_pipe("P2", "HPT", "R2", length=100.0, diameter=6.0, roughness=130.0, flow_gpm=0.0))

    # Set up schedules to flood and then recover the tank
    solver.set_head_schedule("R1", [
        (0.0, 1000.0),
        (0.5, 1000.0),
        (0.6, 50.0),
        (2.0, 50.0)
    ])
    solver.set_head_schedule("R2", [
        (0.0, 1000.0),
        (0.5, 1000.0),
        (0.6, 50.0),
        (2.0, 50.0)
    ])

    # Run simulation
    solver.run(total_time=2.0, dt=0.01)

    final_vol = solver.get_node_gas_volume("HPT")

    # Gas volume should have grown again after dropping R1/R2 head to 50.0 ft
    assert final_vol > 0.05
    assert final_vol <= 10.0
