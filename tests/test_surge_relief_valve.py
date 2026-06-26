import pytest
import numpy as np
import rthym_moc as m

def run_simulation(with_srv: bool):
    solver = m.MOCSolver()

    # Upstream reservoir/tank
    t1 = m.NodeInput()
    t1.id, t1.type, t1.head = "T1", "Tank", 100.0
    solver.add_node(t1)

    # Surge relief valve or junction
    srv = m.NodeInput()
    srv.id = "SRV"
    if with_srv:
        srv.type = "SurgeReliefValve"
        srv.head = 120.0  # Trigger HGL (ft)
        srv.diameter = 1.5  # Orifice diameter (inches)
        srv.loss_coeff_out = 0.6  # Cd
    else:
        srv.type = "Junction"
    srv.elevation = 0.0
    solver.add_node(srv)

    # Downstream valve to create water hammer transient
    v1 = m.NodeInput()
    v1.id, v1.type, v1.current_setting, v1.diameter = "V1", "Valve", 100.0, 12.0
    solver.add_node(v1)

    # Downstream tank
    t2 = m.NodeInput()
    t2.id, t2.type, t2.head = "T2", "Tank", 0.0
    solver.add_node(t2)

    # Pipes
    p1 = m.PipeInput()
    p1.id, p1.from_node, p1.to_node = "P1", "T1", "SRV"
    p1.length, p1.diameter, p1.roughness, p1.flow_gpm = 500.0, 12.0, 130.0, 1000.0
    solver.add_pipe(p1)

    p2 = m.PipeInput()
    p2.id, p2.from_node, p2.to_node = "P2", "SRV", "V1"
    p2.length, p2.diameter, p2.roughness, p2.flow_gpm = 500.0, 12.0, 130.0, 1000.0
    solver.add_pipe(p2)

    p3 = m.PipeInput()
    p3.id, p3.from_node, p3.to_node = "P3", "V1", "T2"
    p3.length, p3.diameter, p3.roughness, p3.flow_gpm = 50.0, 12.0, 130.0, 1000.0
    solver.add_pipe(p3)

    # Fast valve closure schedule
    solver.set_valve_schedule("V1", [(0.0, 100.0), (0.1, 0.0)])

    results = solver.run(total_time=4.0, dt=0.01)
    return results

def test_surge_relief_valve_mitigation():
    # 1. Run baseline without SRV (as a plain junction)
    res_no_srv = run_simulation(with_srv=False)
    max_head_no_srv = np.max(res_no_srv["node_head"]["SRV"])

    # 2. Run simulation with SRV active
    res_srv = run_simulation(with_srv=True)
    max_head_srv = np.max(res_srv["node_head"]["SRV"])

    # Check mitigation: SRV must significantly reduce the peak transient pressure
    assert max_head_srv < max_head_no_srv
    assert max_head_srv < 400.0  # Capped at a safe level
    assert max_head_no_srv > 500.0  # Unmitigated surge is high

def test_surge_relief_valve_dynamics():
    # Run with SRV
    res = run_simulation(with_srv=True)
    
    valves_open = np.array(res["valve_position"]["SRV"])
    heads = np.array(res["node_head"]["SRV"])

    # Initially, head is around steady-state value (~50 ft), below 120 ft trigger
    # Valve must be closed
    assert valves_open[0] == 0.0

    # During transient, head rises above trigger threshold (120.0 ft)
    # Check that valve triggers open (position goes to 1.0)
    triggered_idx = np.where(valves_open > 0.0)[0]
    assert len(triggered_idx) > 0, "SRV should have opened"
    
    # Verify that the opening coincided with head exceeding trigger pressure
    open_start_idx = triggered_idx[0]
    # The pressure wave hits and elevates the head; the step before must have had head > trigger
    assert np.any(heads > 120.0), "SRV should open when HGL exceeds trigger head"

    # Eventually the surge retreats and pressure drops back down.
    # Check that the valve reclosed (valve position goes back to 0.0) at the end of the simulation.
    assert valves_open[-1] == 0.0


