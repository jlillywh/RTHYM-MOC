"""Unit tests for transient operational controls in the MOC solver."""

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

def test_threshold_pressure_valve():
    """Verify that threshold-based controls can trigger valve closure on high pressure."""
    solver = rthym_moc.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=100.0))
    solver.add_node(_make_node("J1", "Junction", elevation=0.0, head=100.0))
    solver.add_node(_make_node("V1", "Valve", diameter=12.0, current_setting=100.0))
    solver.add_node(_make_node("R2", "PressureBoundary", head=50.0))
    
    solver.add_pipe(_make_pipe("P1", "R1", "J1", length=100.0, diameter=12.0, flow_gpm=100.0))
    solver.add_pipe(_make_pipe("P2", "J1", "V1", length=100.0, diameter=12.0, flow_gpm=100.0))
    solver.add_pipe(_make_pipe("P3", "V1", "R2", length=100.0, diameter=12.0, flow_gpm=100.0))
    
    # Register rule: if J1 pressure > 45 psi, slam V1 shut (setting = 0.0)
    rule = rthym_moc.ControlRuleInput()
    rule.id = "rule1"
    rule.type = rthym_moc.ControlType.Threshold
    rule.monitored_node = "J1"
    rule.controlled_node = "V1"
    rule.monitored_quantity = "pressure"
    rule.condition = "gt"
    rule.threshold = 45.0 # psi (initial: 100 ft = 43.3 psi)
    rule.target = 0.0
    
    solver.add_control_rule(rule)
    
    # Increase R1 head schedule to 150 ft (64.9 psi) halfway through
    solver.set_head_schedule("R1", [(0.0, 100.0), (0.2, 100.0), (0.4, 150.0)])
    
    res = solver.run(total_time=5.0, dt=0.01)
    
    # Verify that the flow has dropped to zero due to valve shutting
    final_flow = res["pipe_flow_gpm"]["P1"][-1]
    assert abs(final_flow) < 1.0, f"Expected flow to drop to 0, got {final_flow}"


def test_threshold_pressure_valve_lt():
    """Verify that threshold-based controls can trigger valve opening on low pressure."""
    solver = rthym_moc.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=100.0))
    solver.add_node(_make_node("J1", "Junction", elevation=0.0, head=100.0))
    solver.add_node(_make_node("V1", "Valve", diameter=12.0, current_setting=0.0))
    solver.add_node(_make_node("R2", "PressureBoundary", head=50.0))
    
    solver.add_pipe(_make_pipe("P1", "R1", "J1", length=100.0, diameter=12.0, flow_gpm=0.0))
    solver.add_pipe(_make_pipe("P2", "J1", "V1", length=100.0, diameter=12.0, flow_gpm=0.0))
    solver.add_pipe(_make_pipe("P3", "V1", "R2", length=100.0, diameter=12.0, flow_gpm=0.0))
    
    # Register rule: if J1 pressure < 40 psi, open V1 (setting = 100.0)
    rule = rthym_moc.ControlRuleInput()
    rule.id = "rule_lt"
    rule.type = rthym_moc.ControlType.Threshold
    rule.monitored_node = "J1"
    rule.controlled_node = "V1"
    rule.monitored_quantity = "pressure"
    rule.condition = "lt"
    rule.threshold = 40.0 # psi (initial: 100 ft = 43.3 psi, drops if R1 head decreases)
    rule.target = 100.0
    
    solver.add_control_rule(rule)
    solver.set_head_schedule("R1", [(0.0, 100.0), (0.2, 100.0), (0.4, 80.0)]) # 80 ft = 34.6 psi
    
    res = solver.run(total_time=0.6, dt=0.01)
    
    # Verify that the flow is now positive since the valve opened
    final_flow = res["pipe_flow_gpm"]["P1"][-1]
    assert final_flow > 10.0, f"Expected flow to be positive after valve opens, got {final_flow}"


def test_threshold_resets_controlled_device_when_condition_clears():
    """Threshold controls must release to 0% when condition is no longer met."""
    solver = rthym_moc.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=150.0))
    solver.add_node(_make_node("J1", "Junction", elevation=0.0, head=150.0))
    solver.add_node(_make_node("V1", "Valve", diameter=12.0, current_setting=0.0))
    solver.add_node(_make_node("R2", "PressureBoundary", head=50.0))

    solver.add_pipe(_make_pipe("P1", "R1", "J1", length=100.0, diameter=12.0, flow_gpm=100.0))
    solver.add_pipe(_make_pipe("P2", "J1", "V1", length=100.0, diameter=12.0, flow_gpm=100.0))
    solver.add_pipe(_make_pipe("P3", "V1", "R2", length=100.0, diameter=12.0, flow_gpm=100.0))

    rule = rthym_moc.ControlRuleInput()
    rule.id = "rule_reset"
    rule.type = rthym_moc.ControlType.Threshold
    rule.monitored_node = "J1"
    rule.controlled_node = "V1"
    rule.monitored_quantity = "pressure"
    rule.condition = "gt"
    rule.threshold = 45.0
    rule.target = 100.0
    solver.add_control_rule(rule)

    # Start above threshold (opens valve), then drop below threshold (must reset to 0%).
    solver.set_head_schedule("R1", [(0.0, 150.0), (0.2, 150.0), (0.3, 80.0)])

    res = solver.run(total_time=0.6, dt=0.01)
    assert res["valve_setting"]["V1"][-1] < 1.0


def test_deadband_preserves_initial_on_state_inside_band():
    """Deadband startup should keep an initially ON pump ON when level starts in-band."""
    solver = rthym_moc.MOCSolver()
    solver.add_node(_make_node("T1", "Tank", elevation=0.0, head=10.0, max_level=20.0, tank_area=0.05))
    solver.add_node(_make_node("Pmp1", "Pump", design_head=50.0, design_flow=100.0, current_speed=100.0))
    solver.add_node(_make_node("R1", "PressureBoundary", head=50.0))
    solver.add_pipe(_make_pipe("P1", "R1", "Pmp1", length=50.0, diameter=6.0, flow_gpm=50.0))
    solver.add_pipe(_make_pipe("P2", "Pmp1", "T1", length=50.0, diameter=6.0, flow_gpm=50.0))

    rule = rthym_moc.ControlRuleInput()
    rule.id = "db_fill_inband"
    rule.type = rthym_moc.ControlType.Deadband
    rule.monitored_node = "T1"
    rule.controlled_node = "Pmp1"
    rule.monitored_quantity = "level"
    rule.threshold = 40.0
    rule.deadband = 20.0
    rule.action = "fill"
    solver.add_control_rule(rule)

    res = solver.run(total_time=0.1, dt=0.01)
    assert res["pipe_flow_gpm"]["P1"][-1] > 10.0


def test_deadband_level_pump_fill():
    """Verify deadband control with fill action."""
    # Scenario 1: Initial level is 35% (below 40% threshold), pump should start and run (ON)
    solver1 = rthym_moc.MOCSolver()
    solver1.add_node(_make_node("T1", "Tank", elevation=0.0, head=7.0, max_level=20.0, tank_area=0.05))
    solver1.add_node(_make_node("Pmp1", "Pump", design_head=50.0, design_flow=100.0, current_speed=0.0))
    solver1.add_node(_make_node("R1", "PressureBoundary", head=50.0))
    solver1.add_pipe(_make_pipe("P1", "R1", "Pmp1", length=50.0, diameter=6.0, flow_gpm=0.0))
    solver1.add_pipe(_make_pipe("P2", "Pmp1", "T1", length=50.0, diameter=6.0, flow_gpm=0.0))
    
    rule = rthym_moc.ControlRuleInput()
    rule.id = "db_fill"
    rule.type = rthym_moc.ControlType.Deadband
    rule.monitored_node = "T1"
    rule.controlled_node = "Pmp1"
    rule.monitored_quantity = "level"
    rule.threshold = 40.0 # low limit
    rule.deadband = 20.0  # range (high limit = 60.0%)
    rule.action = "fill"
    solver1.add_control_rule(rule)
    
    res1 = solver1.run(total_time=0.1, dt=0.01)
    assert res1["pipe_flow_gpm"]["P1"][-1] > 10.0, "Expected pump to turn ON under fill logic when level < 40%"

    # Scenario 2: Initial level is 65% (above 60% high limit), pump should stay OFF
    solver2 = rthym_moc.MOCSolver()
    solver2.add_node(_make_node("T1", "Tank", elevation=0.0, head=13.0, max_level=20.0, tank_area=0.05))
    solver2.add_node(_make_node("Pmp1", "Pump", design_head=50.0, design_flow=100.0, current_speed=100.0))
    solver2.add_node(_make_node("R1", "PressureBoundary", head=50.0))
    solver2.add_pipe(_make_pipe("P1", "R1", "Pmp1", length=50.0, diameter=6.0, flow_gpm=50.0))
    solver2.add_pipe(_make_pipe("P2", "Pmp1", "T1", length=50.0, diameter=6.0, flow_gpm=50.0))
    solver2.add_control_rule(rule)
    
    res2 = solver2.run(total_time=0.1, dt=0.01)
    assert res2["pipe_flow_gpm"]["P1"][-1] < 1.0, "Expected pump to turn OFF under fill logic when level > 60%"


def test_deadband_level_pump_drain():
    """Verify deadband control with drain action."""
    # Scenario 1: Initial level is 65% (above 60% high limit), pump should turn ON (drain)
    solver1 = rthym_moc.MOCSolver()
    solver1.add_node(_make_node("T1", "Tank", elevation=0.0, head=13.0, max_level=20.0, tank_area=0.05))
    solver1.add_node(_make_node("Pmp1", "Pump", design_head=50.0, design_flow=100.0, current_speed=0.0))
    solver1.add_node(_make_node("R1", "PressureBoundary", head=50.0))
    solver1.add_pipe(_make_pipe("P1", "T1", "Pmp1", length=50.0, diameter=6.0, flow_gpm=0.0))
    solver1.add_pipe(_make_pipe("P2", "Pmp1", "R1", length=50.0, diameter=6.0, flow_gpm=0.0))
    
    rule = rthym_moc.ControlRuleInput()
    rule.id = "db_drain"
    rule.type = rthym_moc.ControlType.Deadband
    rule.monitored_node = "T1"
    rule.controlled_node = "Pmp1"
    rule.monitored_quantity = "level"
    rule.threshold = 40.0 # low limit
    rule.deadband = 20.0  # range (high limit = 60.0%)
    rule.action = "drain"
    solver1.add_control_rule(rule)
    
    res1 = solver1.run(total_time=0.1, dt=0.01)
    assert res1["pipe_flow_gpm"]["P1"][-1] > 10.0, "Expected pump to turn ON under drain logic when level > 60%"

    # Scenario 2: Initial level is 35% (below 40% low limit), pump should stay OFF
    solver2 = rthym_moc.MOCSolver()
    solver2.add_node(_make_node("T1", "Tank", elevation=0.0, head=7.0, max_level=20.0, tank_area=0.05))
    solver2.add_node(_make_node("Pmp1", "Pump", design_head=50.0, design_flow=100.0, current_speed=100.0))
    solver2.add_node(_make_node("R1", "PressureBoundary", head=50.0))
    solver2.add_pipe(_make_pipe("P1", "T1", "Pmp1", length=50.0, diameter=6.0, flow_gpm=50.0))
    solver2.add_pipe(_make_pipe("P2", "Pmp1", "R1", length=50.0, diameter=6.0, flow_gpm=50.0))
    solver2.add_control_rule(rule)
    
    res2 = solver2.run(total_time=0.1, dt=0.01)
    assert res2["pipe_flow_gpm"]["P1"][-1] < 1.0, "Expected pump to turn OFF under drain logic when level < 40%"


def test_pid_control_pump():
    """Verify PID feedback control of a variable speed pump."""
    solver = rthym_moc.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=20.0))
    solver.add_node(_make_node("J1", "Junction", elevation=0.0, head=25.0))
    solver.add_node(_make_node("Pmp1", "Pump", design_head=50.0, design_flow=100.0, current_speed=50.0))
    solver.add_node(_make_node("R2", "PressureBoundary", head=10.0))
    
    solver.add_pipe(_make_pipe("P1", "R1", "Pmp1", length=50.0, diameter=6.0, flow_gpm=50.0))
    solver.add_pipe(_make_pipe("P2", "Pmp1", "J1", length=50.0, diameter=6.0, flow_gpm=50.0))
    solver.add_pipe(_make_pipe("P3", "J1", "R2", length=50.0, diameter=6.0, flow_gpm=50.0))
    
    rule = rthym_moc.ControlRuleInput()
    rule.id = "pid_rule"
    rule.type = rthym_moc.ControlType.PID
    rule.monitored_node = "J1"
    rule.controlled_node = "Pmp1"
    rule.monitored_quantity = "pressure"
    rule.target = 30.0 # psi (initial head = 25 ft = 10.8 psi; needs pump speed to increase)
    rule.kp = 2.0
    rule.ki = 1.0
    rule.kd = 0.1
    
    solver.add_control_rule(rule)
    res = solver.run(total_time=0.15, dt=0.01)
    
    # Test head quantity support for PID as well
    rule.monitored_quantity = "head"
    rule.target = 80.0
    solver.clear()
    solver.add_node(_make_node("R1", "PressureBoundary", head=20.0))
    solver.add_node(_make_node("J1", "Junction", elevation=0.0, head=25.0))
    solver.add_node(_make_node("Pmp1", "Pump", design_head=50.0, design_flow=100.0, current_speed=50.0))
    solver.add_node(_make_node("R2", "PressureBoundary", head=10.0))
    solver.add_pipe(_make_pipe("P1", "R1", "Pmp1", length=50.0, diameter=6.0, flow_gpm=50.0))
    solver.add_pipe(_make_pipe("P2", "Pmp1", "J1", length=50.0, diameter=6.0, flow_gpm=50.0))
    solver.add_pipe(_make_pipe("P3", "J1", "R2", length=50.0, diameter=6.0, flow_gpm=50.0))
    solver.add_control_rule(rule)
    
    res_head = solver.run(total_time=0.15, dt=0.01)
    assert len(res_head["time"]) > 0


def test_pcv_sequencing():
    """Verify Pump Control Valve (PCV) ramp sequencing."""
    solver = rthym_moc.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=100.0))
    solver.add_node(_make_node("Pmp1", "Pump", design_head=50.0, design_flow=100.0, current_speed=100.0))
    solver.add_node(_make_node("V1", "Valve", diameter=12.0, current_setting=100.0))
    solver.add_node(_make_node("R2", "PressureBoundary", head=50.0))
    
    solver.add_pipe(_make_pipe("P1", "R1", "Pmp1", length=50.0, diameter=12.0, flow_gpm=100.0))
    solver.add_pipe(_make_pipe("P2", "Pmp1", "V1", length=50.0, diameter=12.0, flow_gpm=100.0))
    solver.add_pipe(_make_pipe("P3", "V1", "R2", length=50.0, diameter=12.0, flow_gpm=100.0))
    
    rule = rthym_moc.ControlRuleInput()
    rule.id = "pcv_rule"
    rule.type = rthym_moc.ControlType.PCV
    rule.monitored_node = "Pmp1"
    rule.controlled_node = "V1"
    rule.threshold = 0.2  # ramp open time (seconds)
    rule.deadband = 0.2   # ramp close time (seconds)
    
    solver.add_control_rule(rule)
    
    # Pump starts ON (100) and is scheduled to turn OFF (0) at 0.1s
    solver.set_pump_schedule("Pmp1", [(0.0, 100.0), (0.09, 100.0), (0.1, 0.0)])
    
    res = solver.run(total_time=0.4, dt=0.01)
    
    # Flow should gradually shut down
    assert res["pipe_flow_gpm"]["P1"][-1] < 1.0


def test_pcv_shutdown_does_not_reopen_valve_after_pump_off_command():
    """PCV must read command_speed, not transient current_speed, during valve ramp-down.

    Regression for oscillation when shutdown sets pump command to 0% while PCV
    temporarily holds physical speed at 100% during the closing ramp.
    """
    solver = rthym_moc.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=100.0))
    solver.add_node(_make_node("Pmp1", "Pump", design_head=50.0, design_flow=100.0, current_speed=100.0))
    solver.add_node(_make_node("V1", "Valve", diameter=12.0, current_setting=100.0))
    solver.add_node(_make_node("R2", "PressureBoundary", head=50.0))

    solver.add_pipe(_make_pipe("P1", "R1", "Pmp1", length=50.0, diameter=12.0, flow_gpm=100.0))
    solver.add_pipe(_make_pipe("P2", "Pmp1", "V1", length=50.0, diameter=12.0, flow_gpm=100.0))
    solver.add_pipe(_make_pipe("P3", "V1", "R2", length=50.0, diameter=12.0, flow_gpm=100.0))

    rule = rthym_moc.ControlRuleInput()
    rule.id = "pcv_rule"
    rule.type = rthym_moc.ControlType.PCV
    rule.monitored_node = "Pmp1"
    rule.controlled_node = "V1"
    rule.threshold = 0.2
    rule.deadband = 0.2
    solver.add_control_rule(rule)

    solver.set_pump_schedule("Pmp1", [(0.0, 100.0), (0.09, 100.0), (0.1, 0.0)])
    res = solver.run(total_time=0.4, dt=0.01)

    time_s = res["time"]
    flow_gpm = res["pipe_flow_gpm"]["P1"]
    valve_pct = res["valve_setting"]["V1"]
    off_idx = next(i for i, t in enumerate(time_s) if t >= 0.11)
    after_off = valve_pct[off_idx:]

    assert flow_gpm[-1] < 1.0, "Pump line flow should end near zero after shutdown"
    assert after_off[-1] < 5.0, (
        f"PCV valve should finish closed after shutdown, got {after_off[-1]:.2f}%"
    )
    # Buggy PCV reads transient pump speed and re-enters "opening", increasing % open.
    for i in range(1, len(after_off)):
        assert after_off[i] <= after_off[i - 1] + 0.5, (
            f"Valve reopened during shutdown ramp at t={time_s[off_idx + i]:.3f}s: "
            f"{after_off[i - 1]:.2f}% -> {after_off[i]:.2f}%"
        )


def _pcv_shutdown_fixture(has_power: bool):
    """Pump + PCV network with commanded shutdown at t=0.1 s."""
    solver = rthym_moc.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=100.0))
    solver.add_node(
        _make_node(
            "Pmp1",
            "Pump",
            design_head=50.0,
            design_flow=100.0,
            current_speed=100.0,
            has_power=has_power,
        )
    )
    solver.add_node(_make_node("V1", "Valve", diameter=12.0, current_setting=100.0))
    solver.add_node(_make_node("R2", "PressureBoundary", head=50.0))

    solver.add_pipe(_make_pipe("P1", "R1", "Pmp1", length=50.0, diameter=12.0, flow_gpm=100.0))
    solver.add_pipe(_make_pipe("P2", "Pmp1", "V1", length=50.0, diameter=12.0, flow_gpm=100.0))
    solver.add_pipe(_make_pipe("P3", "V1", "R2", length=50.0, diameter=12.0, flow_gpm=100.0))

    rule = rthym_moc.ControlRuleInput()
    rule.id = "pcv_rule"
    rule.type = rthym_moc.ControlType.PCV
    rule.monitored_node = "Pmp1"
    rule.controlled_node = "V1"
    rule.threshold = 0.2
    rule.deadband = 0.2
    solver.add_control_rule(rule)
    solver.set_pump_schedule("Pmp1", [(0.0, 100.0), (0.09, 100.0), (0.1, 0.0)])
    return solver.run(total_time=0.35, dt=0.01)


def test_pcv_power_outage_drops_pump_speed_during_valve_close():
    """Without electrical power, PCV closing must not hold pump speed at 100%."""
    powered = _pcv_shutdown_fixture(has_power=True)
    outage = _pcv_shutdown_fixture(has_power=False)

    def mean_suction_flow_during_close(res):
        time_s = res["time"]
        flow = res["pipe_flow_gpm"]["P1"]
        mask = (time_s >= 0.11) & (time_s <= 0.28)
        return float(abs(flow[mask]).mean())

    powered_mean = mean_suction_flow_during_close(powered)
    outage_mean = mean_suction_flow_during_close(outage)

    assert powered_mean > 30.0, f"Expected sustained flow during powered PCV close, got {powered_mean:.1f} GPM"
    assert outage_mean < powered_mean * 0.35, (
        f"Power outage should collapse pump delivery during valve ramp "
        f"(powered={powered_mean:.1f} GPM, outage={outage_mean:.1f} GPM)"
    )
    assert outage["pipe_flow_gpm"]["P1"][-1] < 1.0


def test_set_pump_power_rejects_non_pump_nodes():
    solver = rthym_moc.MOCSolver()
    solver.add_node(_make_node("V1", "Valve", diameter=12.0))
    with pytest.raises(ValueError, match="Pump"):
        solver.set_pump_power("V1", False)


def test_flow_monitoring_and_exceptions():
    """Verify pipe flow monitoring and solver exceptions."""
    solver = rthym_moc.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=100.0))
    solver.add_node(_make_node("R2", "PressureBoundary", head=50.0))
    solver.add_pipe(_make_pipe("P1", "R1", "R2", length=100.0, diameter=12.0, flow_gpm=100.0))
    
    rule = rthym_moc.ControlRuleInput()
    rule.id = "flow_rule"
    rule.type = rthym_moc.ControlType.Threshold
    rule.monitored_quantity = "flow"
    rule.monitored_pipe = "P1"
    rule.controlled_node = "R2"
    rule.threshold = 50.0
    rule.condition = "gt"
    rule.target = 0.0
    
    solver.add_control_rule(rule)
    solver.run(total_time=0.05, dt=0.01)
    
    # Test exceptions
    with pytest.raises(ValueError, match="Node not found"):
        solver.get_node_head("nonexistent")
        
    with pytest.raises(ValueError, match="Node not found"):
        solver.get_node_pressure("nonexistent")
        
    solver.clear_control_rules()
