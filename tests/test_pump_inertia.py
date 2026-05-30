"""Unit tests for pump rotational inertia and dynamic deceleration transients."""

import numpy as np
import pytest
import rthym_moc as m


def test_pump_inertia_properties():
    """Verify that the new inertia-related properties are exposed on NodeInput and node_si."""
    # Direct NodeInput API
    node = m.NodeInput()
    node.id = "Pump1"
    node.type = "Pump"
    node.inertia_wr2 = 45.5
    node.speed_rpm = 1800.0
    node.efficiency = 0.82

    assert node.inertia_wr2 == 45.5
    assert node.speed_rpm == 1800.0
    assert node.efficiency == 0.82

    # SI node helper
    node_si = m.node_si(
        "Pump2",
        "Pump",
        inertia_wr2_kg_m2=2.0,  # 2.0 * 23.73036 = 47.46072 lb-ft^2
        speed_rpm=1500.0,
        efficiency=0.75
    )
    assert abs(node_si.inertia_wr2 - 47.46072) < 1e-4
    assert node_si.speed_rpm == 1500.0
    assert node_si.efficiency == 0.75


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


def _build_test_network(inertia_wr2=0.0, speed_rpm=1750.0, efficiency=0.80):
    """Build a simple 3-node, 2-pipe network with a pump for testing."""
    solver = m.MOCSolver()
    
    # Low-pressure reservoir
    solver.add_node(_make_node("R1", "PressureBoundary", head=100.0))
    
    # Tripped pump (has_power=False initially to trigger inertia decay)
    solver.add_node(_make_node(
        "Pump_A",
        "Pump",
        current_speed=100.0,
        has_power=False,
        design_head=120.0,
        design_flow=500.0,
        inertia_wr2=inertia_wr2,
        speed_rpm=speed_rpm,
        efficiency=efficiency,
        head=220.0
    ))
    
    # High-pressure reservoir
    solver.add_node(_make_node("R2", "PressureBoundary", head=160.0))
    
    # Suction and discharge pipes
    solver.add_pipe(_make_pipe(
        "P1",
        "R1",
        "Pump_A",
        length=500.0,
        diameter=12.0,
        roughness=130.0,
        flow_gpm=800.0
    ))
    solver.add_pipe(_make_pipe(
        "P2",
        "Pump_A",
        "R2",
        length=1000.0,
        diameter=12.0,
        roughness=130.0,
        flow_gpm=800.0
    ))
    
    return solver


def test_pump_inertia_telemetry():
    """Verify that pump_speed telemetry is recorded in simulation results."""
    solver = _build_test_network(inertia_wr2=50.0)
    results = solver.run(total_time=1.0, dt=0.01)
    
    assert "pump_speed" in results
    assert "Pump_A" in results["pump_speed"]
    
    speeds = np.asarray(results["pump_speed"]["Pump_A"])
    assert len(speeds) > 0
    assert speeds[0] < 100.0  # Decays immediately from initial 100% speed
    assert np.all(speeds >= 0.0)
    assert np.all(speeds <= 100.0)


def test_pump_inertia_decay_comparison():
    """Verify that a pump with inertia decays gradually, whereas zero inertia stops instantly."""
    # Case 1: No inertia
    solver_no_inertia = _build_test_network(inertia_wr2=0.0)
    results_no_inertia = solver_no_inertia.run(total_time=1.0, dt=0.01)
    speeds_no_inertia = np.asarray(results_no_inertia["pump_speed"]["Pump_A"])
    
    # Case 2: Substantial inertia
    solver_with_inertia = _build_test_network(inertia_wr2=50.0)
    results_with_inertia = solver_with_inertia.run(total_time=1.0, dt=0.01)
    speeds_with_inertia = np.asarray(results_with_inertia["pump_speed"]["Pump_A"])
    
    # Instant stop for zero inertia
    assert speeds_no_inertia[0] == 0.0
    assert speeds_no_inertia[50] == 0.0
    
    # Gradual decay for finite inertia
    assert speeds_with_inertia[0] > 90.0
    assert speeds_with_inertia[0] < 100.0
    assert speeds_with_inertia[50] > 0.0
    assert speeds_with_inertia[50] < speeds_with_inertia[0]
    
    # Flow comparison: discharge head/flow collapses faster for zero inertia
    q_no_inertia = np.asarray(results_no_inertia["pipe_flow_gpm"]["P2"])
    q_with_inertia = np.asarray(results_with_inertia["pipe_flow_gpm"]["P2"])
    assert q_no_inertia[10] < q_with_inertia[10]


def test_pump_inertia_sensitivity():
    """Verify that larger inertia slows the rate of pump speed decay."""
    # Small inertia
    solver_small = _build_test_network(inertia_wr2=10.0)
    results_small = solver_small.run(total_time=2.0, dt=0.01)
    speeds_small = np.asarray(results_small["pump_speed"]["Pump_A"])
    
    # Large inertia
    solver_large = _build_test_network(inertia_wr2=100.0)
    results_large = solver_large.run(total_time=2.0, dt=0.01)
    speeds_large = np.asarray(results_large["pump_speed"]["Pump_A"])
    
    # Larger inertia must decay slower
    for i in range(1, len(speeds_small)):
        if speeds_small[i] > 0.0:
            assert speeds_large[i] > speeds_small[i], f"Mismatch at step {i}: large={speeds_large[i]:.2f}, small={speeds_small[i]:.2f}"
