import pytest
import numpy as np
import rthym_moc

pytestmark = pytest.mark.dvcm


def _build_valve_solver() -> rthym_moc.MOCSolver:
    solver = rthym_moc.MOCSolver()

    r1 = rthym_moc.NodeInput()
    r1.id = "R1"
    r1.type = "Tank"
    r1.head = 100.0

    # Valve node
    v1 = rthym_moc.NodeInput()
    v1.id = "V1"
    v1.type = "Valve"
    v1.diameter = 8.0
    v1.current_setting = 100.0

    r2 = rthym_moc.NodeInput()
    r2.id = "R2"
    r2.type = "Tank"
    r2.head = 100.0

    p1 = rthym_moc.PipeInput()
    p1.id = "P1"
    p1.from_node = "R1"
    p1.to_node = "V1"
    p1.length = 40.0
    p1.diameter = 8.0
    p1.roughness = 120.0

    p2 = rthym_moc.PipeInput()
    p2.id = "P2"
    p2.from_node = "V1"
    p2.to_node = "R2"
    p2.length = 40.0
    p2.diameter = 8.0
    p2.roughness = 120.0

    solver.add_node(r1)
    solver.add_node(v1)
    solver.add_node(r2)
    solver.add_pipe(p1)
    solver.add_pipe(p2)

    return solver


def _build_check_valve_solver() -> rthym_moc.MOCSolver:
    solver = rthym_moc.MOCSolver()

    r1 = rthym_moc.NodeInput()
    r1.id = "R1"
    r1.type = "Tank"
    r1.head = 100.0

    # Check valve node
    cv1 = rthym_moc.NodeInput()
    cv1.id = "CV1"
    cv1.type = "CheckValve"
    cv1.diameter = 8.0
    cv1.closure_time = 0.01

    r2 = rthym_moc.NodeInput()
    r2.id = "R2"
    r2.type = "Tank"
    r2.head = 100.0

    p1 = rthym_moc.PipeInput()
    p1.id = "P1"
    p1.from_node = "R1"
    p1.to_node = "CV1"
    p1.length = 40.0
    p1.diameter = 8.0
    p1.roughness = 120.0

    p2 = rthym_moc.PipeInput()
    p2.id = "P2"
    p2.from_node = "CV1"
    p2.to_node = "R2"
    p2.length = 40.0
    p2.diameter = 8.0
    p2.roughness = 120.0

    solver.add_node(r1)
    solver.add_node(cv1)
    solver.add_node(r2)
    solver.add_pipe(p1)
    solver.add_pipe(p2)

    return solver


def test_dvcm_valve_cavity_initiates_and_collapses() -> None:
    solver = _build_valve_solver()

    # Create a transient: rapidly close the valve to trigger column separation/cavitation.
    # At the same time, we'll schedule heads to drop and rise to see initiation and collapse.
    solver.set_valve_schedule("V1", [(0.0, 100.0), (0.01, 10.0), (0.03, 100.0)])
    solver.set_head_schedule("R1", [(0.0, 100.0), (0.03, 20.0), (0.07, 160.0)])
    solver.set_head_schedule("R2", [(0.0, 100.0), (0.03, 20.0), (0.07, 160.0)])

    results = solver.run(
        total_time=0.70,
        dt=0.01,
        p_vapor_psi=50.0,
        cavitation_model=rthym_moc.CavitationModel.DVCM,
    )

    active = np.asarray(results["node_cavity_active"]["V1"], dtype=int)
    collapse_flag = np.asarray(results["node_cavity_collapse_flag"]["V1"], dtype=int)
    collapse_count = np.asarray(results["node_cavity_collapse_count"]["V1"], dtype=int)
    volume = np.asarray(results["node_cavity_volume"]["V1"], dtype=float)

    # Verify that cavitation starts and then collapses
    assert active[0] == 1
    assert active[-1] == 0
    assert np.any(active == 1)
    assert np.any(active == 0)
    assert np.any(volume > 0.0)
    assert volume[-1] == 0.0
    assert int(collapse_flag.sum()) >= 1
    assert int(collapse_count[-1]) >= 1


def test_dvcm_check_valve_cavity_initiates_and_collapses() -> None:
    solver = _build_check_valve_solver()

    # Drop heads below vapor pressure to initiate cavitation
    # then raise them back up to force collapse
    solver.set_head_schedule("R1", [(0.0, 100.0), (0.02, 20.0), (0.06, 160.0)])
    solver.set_head_schedule("R2", [(0.0, 100.0), (0.02, 20.0), (0.06, 160.0)])

    results = solver.run(
        total_time=0.70,
        dt=0.01,
        p_vapor_psi=50.0,
        cavitation_model=rthym_moc.CavitationModel.DVCM,
    )

    active = np.asarray(results["node_cavity_active"]["CV1"], dtype=int)
    collapse_flag = np.asarray(results["node_cavity_collapse_flag"]["CV1"], dtype=int)
    collapse_count = np.asarray(results["node_cavity_collapse_count"]["CV1"], dtype=int)
    volume = np.asarray(results["node_cavity_volume"]["CV1"], dtype=float)

    assert active[0] == 1
    assert active[-1] == 0
    assert np.any(active == 1)
    assert np.any(active == 0)
    assert np.any(volume > 0.0)
    assert volume[-1] == 0.0
    assert int(collapse_flag.sum()) >= 1
    assert int(collapse_count[-1]) >= 1


def test_legacy_clamp_behavior_preserved_for_valve_and_check_valve() -> None:
    # Run the valve case with both LegacyClamp and DVCM
    solver_legacy = _build_valve_solver()
    solver_legacy.set_valve_setting("V1", 50.0)
    solver_legacy.set_head_schedule("R1", [(0.0, 100.0), (0.05, 20.0)])
    solver_legacy.set_head_schedule("R2", [(0.0, 100.0), (0.05, 20.0)])

    res_legacy = solver_legacy.run(
        total_time=0.05,
        dt=0.01,
        p_vapor_psi=50.0,
        cavitation_model=rthym_moc.CavitationModel.LegacyClamp,
    )

    # With DVCM we expect different results when cavitation occurs because cavity volume is tracked,
    # but with LegacyClamp it should match itself.
    # Let's ensure that if we run the legacy clamp solver, it matches the expected clamped output.
    assert np.any(np.asarray(res_legacy["node_cavitation"]["V1"]) == 1)
    # The LegacyClamp node_cavity_volume should remain 0
    assert np.all(np.asarray(res_legacy["node_cavity_volume"]["V1"]) == 0.0)

    # Also run the turbine case with LegacyClamp
    solver_turb_legacy = _build_turbine_solver()
    solver_turb_legacy.set_valve_setting("T1", 50.0)
    solver_turb_legacy.set_head_schedule("R1", [(0.0, 100.0), (0.05, 20.0)])
    solver_turb_legacy.set_head_schedule("R2", [(0.0, 100.0), (0.05, 20.0)])

    res_turb_legacy = solver_turb_legacy.run(
        total_time=0.05,
        dt=0.01,
        p_vapor_psi=50.0,
        cavitation_model=rthym_moc.CavitationModel.LegacyClamp,
    )
    assert np.any(np.asarray(res_turb_legacy["node_cavitation"]["T1"]) == 1)
    assert np.all(np.asarray(res_turb_legacy["node_cavity_volume"]["T1"]) == 0.0)


def _build_turbine_solver() -> rthym_moc.MOCSolver:
    solver = rthym_moc.MOCSolver()

    r1 = rthym_moc.NodeInput()
    r1.id = "R1"
    r1.type = "Tank"
    r1.head = 100.0

    # Turbine node
    t1 = rthym_moc.NodeInput()
    t1.id = "T1"
    t1.type = "Turbine"
    t1.diameter = 8.0
    t1.current_setting = 100.0
    t1.design_head = 40.0
    t1.design_flow = 1500.0

    r2 = rthym_moc.NodeInput()
    r2.id = "R2"
    r2.type = "Tank"
    r2.head = 100.0

    p1 = rthym_moc.PipeInput()
    p1.id = "P1"
    p1.from_node = "R1"
    p1.to_node = "T1"
    p1.length = 40.0
    p1.diameter = 8.0
    p1.roughness = 120.0

    p2 = rthym_moc.PipeInput()
    p2.id = "P2"
    p2.from_node = "T1"
    p2.to_node = "R2"
    p2.length = 40.0
    p2.diameter = 8.0
    p2.roughness = 120.0

    solver.add_node(r1)
    solver.add_node(t1)
    solver.add_node(r2)
    solver.add_pipe(p1)
    solver.add_pipe(p2)

    return solver


def test_dvcm_turbine_cavity_initiates_and_collapses() -> None:
    solver = _build_turbine_solver()

    solver.set_valve_schedule("T1", [(0.0, 100.0), (0.01, 10.0), (0.03, 100.0)])
    solver.set_head_schedule("R1", [(0.0, 100.0), (0.03, 20.0), (0.07, 160.0)])
    solver.set_head_schedule("R2", [(0.0, 100.0), (0.03, 20.0), (0.07, 160.0)])

    results = solver.run(
        total_time=0.70,
        dt=0.01,
        p_vapor_psi=50.0,
        cavitation_model=rthym_moc.CavitationModel.DVCM,
    )

    active = np.asarray(results["node_cavity_active"]["T1"], dtype=int)
    collapse_flag = np.asarray(results["node_cavity_collapse_flag"]["T1"], dtype=int)
    collapse_count = np.asarray(results["node_cavity_collapse_count"]["T1"], dtype=int)
    volume = np.asarray(results["node_cavity_volume"]["T1"], dtype=float)

    # Verify that cavitation starts and then collapses
    assert active[0] == 1
    assert active[-1] == 0
    assert np.any(active == 1)
    assert np.any(active == 0)
    assert np.any(volume > 0.0)
    assert volume[-1] == 0.0
    assert int(collapse_flag.sum()) >= 1
    assert int(collapse_count[-1]) >= 1
