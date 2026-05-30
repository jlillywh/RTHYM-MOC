"""Unit tests for turbine rotational inertia and runaway/startup dynamics."""

import numpy as np
import pytest
import rthym_moc as m


def test_turbine_inertia_properties():
    """Verify that the new inertia-related properties are exposed on NodeInput and node_si."""
    # Direct NodeInput API
    node = m.NodeInput()
    node.id = "Turbine1"
    node.type = "Turbine"
    node.inertia_wr2 = 45.5
    node.speed_rpm = 1800.0
    node.efficiency = 0.82

    assert node.inertia_wr2 == 45.5
    assert node.speed_rpm == 1800.0
    assert node.efficiency == 0.82

    # SI node helper
    node_si = m.node_si(
        "Turbine2",
        "Turbine",
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


def _build_test_network(inertia_wr2=0.0, speed_rpm=1800.0, efficiency=0.80, has_power=False):
    """Build a simple 3-node, 2-pipe network with a turbine for testing."""
    solver = m.MOCSolver()

    # Upstream high-pressure reservoir
    solver.add_node(_make_node("R1", "PressureBoundary", head=220.0))

    # Turbine (has_power=False initially to trigger runaway dynamics unless has_power is overridden)
    solver.add_node(_make_node(
        "Turbine_A",
        "Turbine",
        current_speed=100.0,
        current_setting=100.0,
        has_power=has_power,
        design_head=120.0,
        design_flow=500.0,
        inertia_wr2=inertia_wr2,
        speed_rpm=speed_rpm,
        efficiency=efficiency,
        diameter=8.0,
        head=100.0
    ))

    # Downstream reservoir
    solver.add_node(_make_node("R2", "PressureBoundary", head=100.0))

    # Suction and discharge pipes
    solver.add_pipe(_make_pipe(
        "P1",
        "R1",
        "Turbine_A",
        length=500.0,
        diameter=8.0,
        roughness=130.0,
        flow_gpm=500.0
    ))
    solver.add_pipe(_make_pipe(
        "P2",
        "Turbine_A",
        "R2",
        length=500.0,
        diameter=8.0,
        roughness=130.0,
        flow_gpm=500.0
    ))

    return solver


def test_turbine_inertia_telemetry():
    """Verify that turbine_speed telemetry is recorded in simulation results."""
    solver = _build_test_network(inertia_wr2=50.0, has_power=False)
    results = solver.run(total_time=1.0, dt=0.01)

    assert "turbine_speed" in results
    assert "Turbine_A" in results["turbine_speed"]

    speeds = np.asarray(results["turbine_speed"]["Turbine_A"])
    assert len(speeds) > 0
    assert speeds[0] > 100.0  # Decoupled turbine accelerates from initial 100% speed
    assert np.all(speeds >= 100.0)


def test_turbine_synchronous_connected():
    """Verify that a synchronized turbine (has_power=True) locks its speed at 100%."""
    solver = _build_test_network(inertia_wr2=50.0, has_power=True)
    results = solver.run(total_time=1.0, dt=0.01)

    speeds = np.asarray(results["turbine_speed"]["Turbine_A"])
    assert len(speeds) > 0
    # Every step should be exactly 100% speed
    assert np.allclose(speeds, 100.0)


def test_set_generator_connected_api():
    """Verify that set_generator_connected updates has_power state correctly."""
    solver = _build_test_network(inertia_wr2=50.0, has_power=True)

    # Verify initial connected state locks speed to 100%
    results = solver.run(total_time=0.1, dt=0.01)
    assert np.allclose(results["turbine_speed"]["Turbine_A"], 100.0)

    # Disconnect mid-run via set_generator_connected
    solver.set_generator_connected("Turbine_A", False)
    results_tripped = solver.run(total_time=0.5, dt=0.01)
    speeds_tripped = np.asarray(results_tripped["turbine_speed"]["Turbine_A"])

    assert speeds_tripped[0] > 100.0


def test_turbine_zero_inertia_instant_runaway():
    """Verify that a turbine with zero inertia instantly jumps to runaway speed."""
    solver = _build_test_network(inertia_wr2=0.0, has_power=False)
    results = solver.run(total_time=0.5, dt=0.01)
    speeds = np.asarray(results["turbine_speed"]["Turbine_A"])

    # Instant runaway speed should be ~180.0% of rated at design head difference (120ft)
    assert speeds[0] > 175.0
    assert speeds[0] < 185.0
    # Over time, speeds remain constant if heads are constant
    assert abs(speeds[-1] - speeds[0]) < 2.0


def test_turbine_inertia_acceleration_comparison():
    """Verify that a turbine with larger inertia accelerates more slowly."""
    # Case 1: Small inertia
    solver_small = _build_test_network(inertia_wr2=10.0, has_power=False)
    results_small = solver_small.run(total_time=0.5, dt=0.01)
    speeds_small = np.asarray(results_small["turbine_speed"]["Turbine_A"])

    # Case 2: Large inertia
    solver_large = _build_test_network(inertia_wr2=100.0, has_power=False)
    results_large = solver_large.run(total_time=0.5, dt=0.01)
    speeds_large = np.asarray(results_large["turbine_speed"]["Turbine_A"])

    # Both must accelerate, but small inertia accelerates faster
    assert speeds_small[0] > 100.0
    assert speeds_large[0] > 100.0
    # Small inertia must be faster than large inertia at all transient steps
    for i in range(len(speeds_small)):
        assert speeds_small[i] >= speeds_large[i]

    # Verify that the runaway limit is respected (they don't accelerate infinitely)
    assert np.all(speeds_small < 185.0)
    assert np.all(speeds_large < 185.0)


def test_turbine_si_interface():
    """Verify that SI wrapper functions work correctly with turbine speed telemetry."""
    # Build SI network
    solver = m.MOCSolver()
    solver.add_node(m.node_si("R1", "PressureBoundary", head_m=67.056))  # ~220 ft
    solver.add_node(m.node_si(
        "Turbine_A",
        "Turbine",
        current_speed=100.0,
        current_setting=100.0,
        has_power=False,
        design_head_m=36.576,  # ~120 ft
        design_flow_m3s=0.031545,  # ~500 GPM
        inertia_wr2_kg_m2=2.107,  # ~50 lb-ft^2
        speed_rpm=1800.0,
        efficiency=0.80,
        diameter_mm=203.2,  # ~8 inches
    ))
    solver.add_node(m.node_si("R2", "PressureBoundary", head_m=30.48))  # ~100 ft

    solver.add_pipe(m.pipe_si(
        "P1", "R1", "Turbine_A",
        length_m=152.4, diameter_mm=203.2, roughness=130.0, flow_m3s=0.031545
    ))
    solver.add_pipe(m.pipe_si(
        "P2", "Turbine_A", "R2",
        length_m=152.4, diameter_mm=203.2, roughness=130.0, flow_m3s=0.031545
    ))

    # Run with SI wrapper
    results = m.run_si(solver, total_time=0.5, dt=0.01)

    assert "turbine_speed" in results
    assert "Turbine_A" in results["turbine_speed"]
    speeds = results["turbine_speed"]["Turbine_A"]
    assert speeds[0] > 100.0
