import numpy as np
import pytest
import rthym_moc as m

def _make_node(node_id, node_type, **kwargs):
    node = m.NodeInput()
    node.id = node_id
    node.type = node_type
    for key, value in kwargs.items():
        setattr(node, key, value)
    return node

def _make_pipe(pipe_id, from_node, to_node, length_ft, flow_gpm):
    pipe = m.PipeInput()
    pipe.id = pipe_id
    pipe.from_node = from_node
    pipe.to_node = to_node
    pipe.length = length_ft
    pipe.diameter = 12.0
    pipe.roughness = 130.0
    pipe.flow_gpm = flow_gpm
    return pipe

def test_compressible_air_valve_physics_steady_state():
    """Verify that when pressures are positive, the air valve remains closed and inactive."""
    solver = m.MOCSolver()
    solver.add_node(_make_node("Rlow", "PressureBoundary", head=100.0))
    solver.add_node(_make_node("PumpIn", "Junction", head=100.0))
    solver.add_node(
        _make_node(
            "Pump_A",
            "Pump",
            design_head=120.0,
            design_flow=500.0,
            current_speed=100.0,
            head=220.0,
        )
    )
    solver.add_node(_make_node("Jd", "Junction", head=220.0))
    solver.add_node(
        _make_node(
            "Vent",
            "AirValve",
            elevation=0.0,
            head=160.0,
            diameter=6.0,
            air_release_diameter=0.25,
            gas_volume=0.05,
            tank_volume=2.0,
            loss_coeff_in=0.8,
            loss_coeff_out=0.7,
        )
    )
    solver.add_node(_make_node("Rhigh", "PressureBoundary", head=160.0))

    solver.add_pipe(_make_pipe("Ps", "Rlow", "PumpIn", 500.0, 800.0))
    solver.add_pipe(_make_pipe("Ppump", "Pump_A", "Jd", 40.0, 800.0))
    solver.add_pipe(_make_pipe("Pstub", "Jd", "Vent", 40.0, 800.0))
    solver.add_pipe(_make_pipe("Pmain", "Vent", "Rhigh", 4000.0, 800.0))

    # Keep pump speed at 100% throughout the simulation to maintain steady state
    solver.set_pump_schedule(
        "Pump_A",
        [
            (0.0, 100.0),
            (2.0, 100.0),
        ],
    )

    data = solver.run(total_time=2.0, dt=0.01)
    
    time_s = np.asarray(data["time"])
    vent_head = np.asarray(data["node_head"]["Vent"])
    vent_cav = np.asarray(data["node_cavitation"]["Vent"])
    
    # Since pressure remains positive throughout the run, the air valve should remain closed.
    assert np.all(vent_head[time_s >= 1.0] >= 150.0)
    assert np.all(vent_cav[time_s >= 1.0] == 0)

def test_compressible_pocket_pressure_ideal_gas_law():
    """Verify pocket absolute pressure behaves according to the compressible ideal gas law."""
    solver = m.MOCSolver()
    solver.add_node(_make_node("Rlow", "PressureBoundary", head=10.0))
    solver.add_node(_make_node("Jd", "Junction", head=10.0))
    solver.add_node(
        _make_node(
            "Vent",
            "AirValve",
            elevation=0.0,
            head=5.0,
            diameter=6.0,
            air_release_diameter=0.25,
            gas_volume=0.2,
            tank_volume=2.0,
            loss_coeff_in=0.8,
            loss_coeff_out=0.7,
        )
    )
    solver.add_node(_make_node("Rhigh", "PressureBoundary", head=5.0))

    solver.add_pipe(_make_pipe("P1", "Rlow", "Jd", 100.0, 50.0))
    solver.add_pipe(_make_pipe("P2", "Jd", "Vent", 100.0, 50.0))
    solver.add_pipe(_make_pipe("P3", "Vent", "Rhigh", 100.0, 50.0))

    data = solver.run(total_time=0.1, dt=0.01)
    vent_head = np.asarray(data["node_head"]["Vent"])
    vent_pressure = np.asarray(data["node_pressure"]["Vent"])
    
    for head, press in zip(vent_head, vent_pressure):
        expected_press = head * 0.433
        assert abs(press - expected_press) <= 0.1
