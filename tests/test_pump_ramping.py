"""Unit tests for VFD pump speed ramping in the MOC solver."""

import pytest
import rthym_moc
import numpy as np

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

def test_pump_ramping_threshold():
    """Verify that a pump under threshold control respects its ramp_time limit."""
    # Build a simple network: R1 -> Pump -> J1 -> R2
    solver = rthym_moc.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=100.0))
    # Pump starts at 0% speed, has a VFD ramp time of 2.0 seconds
    solver.add_node(_make_node("Pmp1", "Pump", design_head=50.0, design_flow=100.0, current_speed=0.0, ramp_time=2.0))
    solver.add_node(_make_node("J1", "Junction", elevation=0.0, head=100.0))
    solver.add_node(_make_node("R2", "PressureBoundary", head=50.0))

    solver.add_pipe(_make_pipe("P1", "R1", "Pmp1", length=100.0, diameter=12.0, flow_gpm=0.0))
    solver.add_pipe(_make_pipe("P2", "Pmp1", "J1", length=100.0, diameter=12.0, flow_gpm=0.0))
    solver.add_pipe(_make_pipe("P3", "J1", "R2", length=100.0, diameter=12.0, flow_gpm=0.0))

    # Threshold rule: if J1 pressure is less than 100 psi (which is true), set pump speed to 100%
    rule = rthym_moc.ControlRuleInput()
    rule.id = "ramp_rule"
    rule.type = rthym_moc.ControlType.Threshold
    rule.monitored_node = "J1"
    rule.controlled_node = "Pmp1"
    rule.monitored_quantity = "pressure"
    rule.condition = "lt"
    rule.threshold = 100.0
    rule.target = 100.0

    solver.add_control_rule(rule)

    # Run for 1.0 second, dt=0.01. VFD ramp rate: 100% / 2s = 50%/s.
    # At t=1.0s, the speed should be exactly 50%.
    res = solver.run(total_time=1.0, dt=0.01)
    
    speeds = res["pump_speed"]["Pmp1"]
    
    # Speed should start at 0, ramp up, and end around 50%
    assert speeds[0] == pytest.approx(0.5)  # first step updates speed: (100 / 2.0) * 0.01 = 0.5%
    assert speeds[-1] == pytest.approx(50.0, abs=1e-3)
    
    # Check intermediate steps
    for i in range(1, len(speeds)):
        diff = speeds[i] - speeds[i-1]
        assert diff <= 0.5 + 1e-6  # maximum increase per timestep (0.01s * 50%/s = 0.5%)

def test_pump_ramping_instant():
    """Verify that a pump under threshold control with ramp_time <= 0 changes speed instantly."""
    solver = rthym_moc.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=100.0))
    solver.add_node(_make_node("Pmp1", "Pump", design_head=50.0, design_flow=100.0, current_speed=0.0, ramp_time=0.0))
    solver.add_node(_make_node("J1", "Junction", elevation=0.0, head=100.0))
    solver.add_node(_make_node("R2", "PressureBoundary", head=50.0))

    solver.add_pipe(_make_pipe("P1", "R1", "Pmp1", length=100.0, diameter=12.0, flow_gpm=0.0))
    solver.add_pipe(_make_pipe("P2", "Pmp1", "J1", length=100.0, diameter=12.0, flow_gpm=0.0))
    solver.add_pipe(_make_pipe("P3", "J1", "R2", length=100.0, diameter=12.0, flow_gpm=0.0))

    rule = rthym_moc.ControlRuleInput()
    rule.id = "ramp_rule"
    rule.type = rthym_moc.ControlType.Threshold
    rule.monitored_node = "J1"
    rule.controlled_node = "Pmp1"
    rule.monitored_quantity = "pressure"
    rule.condition = "lt"
    rule.threshold = 100.0
    rule.target = 100.0

    solver.add_control_rule(rule)

    res = solver.run(total_time=0.1, dt=0.01)
    
    speeds = res["pump_speed"]["Pmp1"]
    
    # Speed should jump to 100% on the very first step and stay there
    assert all(s == 100.0 for s in speeds)

def test_pump_ramping_schedule():
    """Verify that a pump schedule also respects the VFD ramp_time limit."""
    solver = rthym_moc.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=100.0))
    solver.add_node(_make_node("Pmp1", "Pump", design_head=50.0, design_flow=100.0, current_speed=0.0, ramp_time=4.0))
    solver.add_node(_make_node("R2", "PressureBoundary", head=50.0))
    solver.add_pipe(_make_pipe("P1", "R1", "Pmp1", length=100.0, diameter=12.0, flow_gpm=0.0))
    solver.add_pipe(_make_pipe("P2", "Pmp1", "R2", length=100.0, diameter=12.0, flow_gpm=0.0))

    # Schedule: instantly set target to 100% at t=0
    solver.set_pump_schedule("Pmp1", [(0.0, 100.0), (10.0, 100.0)])

    # Run for 1.0 second, dt=0.01. VFD ramp rate: 100% / 4s = 25%/s.
    # At t=1.0s, the speed should be exactly 25%.
    res = solver.run(total_time=1.0, dt=0.01)
    
    speeds = res["pump_speed"]["Pmp1"]
    assert speeds[-1] == pytest.approx(25.0, abs=1e-3)
    for i in range(1, len(speeds)):
        diff = speeds[i] - speeds[i-1]
        assert diff <= 0.25 + 1e-6  # maximum increase per timestep (0.01s * 25%/s = 0.25%)

def test_pump_ramping_coastdown_precedence():
    """Verify that inertia coast-down decay takes precedence over VFD ramp when has_power is False."""
    solver = rthym_moc.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=100.0))
    # Pump has WR^2 = 50.0 and a slow VFD ramp_time of 10.0 seconds
    solver.add_node(
        _make_node(
            "Pmp1",
            "Pump",
            design_head=120.0,
            design_flow=500.0,
            current_speed=100.0,
            ramp_time=10.0,
            has_power=False,
            inertia_wr2=10.0,
            speed_rpm=1750.0
        )
    )
    solver.add_node(_make_node("R2", "PressureBoundary", head=50.0))
    solver.add_pipe(_make_pipe("P1", "R1", "Pmp1", length=100.0, diameter=12.0, flow_gpm=50.0))
    solver.add_pipe(_make_pipe("P2", "Pmp1", "R2", length=100.0, diameter=12.0, flow_gpm=50.0))

    # Even though command is 100%, and has_power is False,
    # the pump should decelerate based on hydraulic torque/inertia decay, NOT the VFD limit.
    # The hydraulic decay is typically much faster than a 10s VFD ramp.
    res = solver.run(total_time=0.5, dt=0.01)
    
    speeds = res["pump_speed"]["Pmp1"]
    # With a 10s ramp, maximum speed change per timestep is 0.1%.
    # In 0.5s (50 steps), VFD ramp would drop speed by at most 5% (to 95%).
    # The inertia decay should spin it down much further.
    assert speeds[-1] < 90.0, f"Inertia decay did not take precedence (final speed = {speeds[-1]}%)"

def test_pump_ramping_inp_override():
    """Verify that pump ramp_time can be parsed from EPANET [RTHYM] overrides."""
    inp_content = """[TITLE]
Ramping Test

[JUNCTIONS]
J1 0 0

[RESERVOIRS]
R1 100 
R2 50

[PIPES]
P1 R1 J1 100 12 130 0 OPEN
P2 J1 R2 100 12 130 0 OPEN

[PUMPS]
Pmp1 R1 J1 HEAD Curve1

[CURVES]
Curve1 100 100

[RTHYM]
_PUMP_Pmp1 Pump ramp_time=5.5

[STATUS]
Pmp1 OPEN
"""
    import tempfile
    import os
    
    with tempfile.NamedTemporaryFile(mode="w", suffix=".inp", delete=False) as f:
        f.write(inp_content)
        temp_name = f.name
        
    try:
        # Load the solver using load_inp
        solver = rthym_moc.load_inp(temp_name, use_wntr=False)
        
        # Verify that the pump node has the parsed ramp_time
        pump_node = None
        for i in range(100):  # find the pump node
            try:
                # Add check or retrieve node info if possible
                pass
            except:
                break
        
        # We can also verify by query or checking the underlying list of nodes
        # Let's inspect the solver's nodes
        found = False
        # Since node_inputs_ is not directly exposed as list, we can test it by running a schedule
        # that targets it, or checking if ramp_time is correct by running a schedule and checking speed
        solver.set_pump_schedule("_PUMP_Pmp1", [(0.0, 100.0), (10.0, 100.0)])
        res = solver.run(total_time=1.0, dt=0.01)
        speeds = res["pump_speed"]["_PUMP_Pmp1"]
        # Initial speed was 100%, but it was Pmp1 OPEN, let's see.
        # Wait, Pmp1 starts at 100%. In 1.0s, it's 100%.
        # Let's start the schedule at 0% and ramp to 100%:
        solver.clear()
        solver = rthym_moc.load_inp(temp_name, use_wntr=False)
        # Verify the parsed node property directly via python bindings if available:
        # Wait, the bindings expose the node inputs? No, but we can check if it is parsed.
        # Let's verify by setting speed to 0 first:
        solver.set_pump_speed("_PUMP_Pmp1", 0.0)
        solver.set_pump_schedule("_PUMP_Pmp1", [(0.0, 100.0), (10.0, 100.0)])
        res = solver.run(total_time=1.0, dt=0.01)
        speeds = res["pump_speed"]["_PUMP_Pmp1"]
        # VFD ramp rate: 100% / 5.5s = 18.18%/s. In 1.0s, it should reach 18.18%.
        assert speeds[-1] == pytest.approx(18.18, abs=0.1)
    finally:
        os.remove(temp_name)
