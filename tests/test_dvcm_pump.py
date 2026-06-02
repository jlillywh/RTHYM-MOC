import pytest
import numpy as np
import rthym_moc

pytestmark = pytest.mark.dvcm


def _build_pump_solver() -> rthym_moc.MOCSolver:
    solver = rthym_moc.MOCSolver()

    r1 = rthym_moc.NodeInput()
    r1.id = "R1"
    r1.type = "Tank"
    r1.head = 100.0

    p1 = rthym_moc.NodeInput()
    p1.id = "Pump1"
    p1.type = "Pump"
    p1.design_head = 80.0
    p1.design_flow = 1500.0
    p1.current_speed = 100.0
    p1.inertia_wr2 = 50.0  # significant inertia
    p1.speed_rpm = 1750.0
    p1.has_power = True

    r2 = rthym_moc.NodeInput()
    r2.id = "R2"
    r2.type = "Tank"
    r2.head = 120.0

    pipe1 = rthym_moc.PipeInput()
    pipe1.id = "P1"
    pipe1.from_node = "R1"
    pipe1.to_node = "Pump1"
    pipe1.length = 40.0
    pipe1.diameter = 8.0
    pipe1.roughness = 120.0

    pipe2 = rthym_moc.PipeInput()
    pipe2.id = "P2"
    pipe2.from_node = "Pump1"
    pipe2.to_node = "R2"
    pipe2.length = 40.0
    pipe2.diameter = 8.0
    pipe2.roughness = 120.0

    solver.add_node(r1)
    solver.add_node(p1)
    solver.add_node(r2)
    solver.add_pipe(pipe1)
    solver.add_pipe(pipe2)

    return solver


def test_dvcm_pump_trip_inertia_cavity_initiates_and_collapses() -> None:
    solver = _build_pump_solver()

    # Trigger a power trip at t = 0
    solver.set_pump_power("Pump1", False)
    
    # Schedule boundary heads to drop then rise to force cavitation and recovery
    solver.set_head_schedule("R1", [(0.0, 100.0), (0.02, 10.0), (0.10, 300.0)])
    solver.set_head_schedule("R2", [(0.0, 120.0), (0.02, 10.0), (0.10, 300.0)])

    results = solver.run(
        total_time=0.30,
        dt=0.01,
        p_vapor_psi=50.0,
        cavitation_model=rthym_moc.CavitationModel.DVCM,
    )

    active = np.asarray(results["node_cavity_active"]["Pump1"], dtype=int)
    collapse_flag = np.asarray(results["node_cavity_collapse_flag"]["Pump1"], dtype=int)
    collapse_count = np.asarray(results["node_cavity_collapse_count"]["Pump1"], dtype=int)
    volume = np.asarray(results["node_cavity_volume"]["Pump1"], dtype=float)
    speed = np.asarray(results["pump_speed"]["Pump1"], dtype=float)

    # Pump speed should decay over time due to trip + inertia
    assert speed[-1] < speed[0]
    assert np.all(np.diff(speed) <= 1e-5)

    # Cavity should activate and then collapse
    assert active[0] == 1
    assert active[-1] == 0
    assert np.any(active == 1)
    assert np.any(active == 0)
    assert np.any(volume > 0.0)
    assert volume[-1] == 0.0
    assert int(collapse_flag.sum()) >= 1
    assert int(collapse_count[-1]) >= 1


def test_dvcm_stopped_pump_dead_end_cavitation() -> None:
    solver = _build_pump_solver()

    # Set pump starting speed to 0.0 (stopped dead-end state)
    solver.set_pump_speed("Pump1", 0.0)

    # Schedule boundary heads to force cavitation and recovery
    solver.set_head_schedule("R1", [(0.0, 100.0), (0.02, 10.0), (0.10, 300.0)])
    solver.set_head_schedule("R2", [(0.0, 120.0), (0.02, 10.0), (0.10, 300.0)])

    results = solver.run(
        total_time=0.30,
        dt=0.01,
        p_vapor_psi=50.0,
        cavitation_model=rthym_moc.CavitationModel.DVCM,
    )

    active = np.asarray(results["node_cavity_active"]["Pump1"], dtype=int)
    collapse_flag = np.asarray(results["node_cavity_collapse_flag"]["Pump1"], dtype=int)
    collapse_count = np.asarray(results["node_cavity_collapse_count"]["Pump1"], dtype=int)
    volume = np.asarray(results["node_cavity_volume"]["Pump1"], dtype=float)

    assert active[0] == 1
    assert active[-1] == 0
    assert np.any(volume > 0.0)
    assert volume[-1] == 0.0
    assert int(collapse_flag.sum()) >= 1
    assert int(collapse_count[-1]) >= 1


def test_legacy_clamp_behavior_preserved_for_pump() -> None:
    solver_legacy = _build_pump_solver()
    solver_legacy.set_head_schedule("R1", [(0.0, 100.0), (0.05, 10.0)])
    solver_legacy.set_head_schedule("R2", [(0.0, 120.0), (0.05, 10.0)])

    res_legacy = solver_legacy.run(
        total_time=0.05,
        dt=0.01,
        p_vapor_psi=50.0,
        cavitation_model=rthym_moc.CavitationModel.LegacyClamp,
    )

    assert np.any(np.asarray(res_legacy["node_cavitation"]["Pump1"]) == 1)
    assert np.all(np.asarray(res_legacy["node_cavity_volume"]["Pump1"]) == 0.0)
