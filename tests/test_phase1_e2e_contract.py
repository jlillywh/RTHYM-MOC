import numpy as np
import rthym_moc


def _build_solver() -> rthym_moc.MOCSolver:
    solver = rthym_moc.MOCSolver()

    r1 = rthym_moc.NodeInput()
    r1.id = "R1"
    r1.type = "Tank"
    r1.head = 120.0

    j1 = rthym_moc.NodeInput()
    j1.id = "J1"
    j1.type = "Junction"
    j1.head = 100.0

    r2 = rthym_moc.NodeInput()
    r2.id = "R2"
    r2.type = "Tank"
    r2.head = 80.0

    p1 = rthym_moc.PipeInput()
    p1.id = "P1"
    p1.from_node = "R1"
    p1.to_node = "J1"
    p1.length = 1200.0
    p1.diameter = 8.0
    p1.roughness = 120.0
    p1.flow_gpm = 200.0

    p2 = rthym_moc.PipeInput()
    p2.id = "P2"
    p2.from_node = "J1"
    p2.to_node = "R2"
    p2.length = 900.0
    p2.diameter = 8.0
    p2.roughness = 120.0
    p2.flow_gpm = 200.0

    solver.add_node(r1)
    solver.add_node(j1)
    solver.add_node(r2)
    solver.add_pipe(p1)
    solver.add_pipe(p2)
    return solver


def test_phase1_e2e_contract_legacy_mode_stable_and_additive() -> None:
    solver = _build_solver()
    results = solver.run(total_time=0.1, dt=0.01)

    # Core legacy channels must remain present.
    for key in ("time", "node_head", "node_pressure", "node_cavitation", "pipe_flow_gpm"):
        assert key in results

    # Phase 1 additive channels must be available and aligned.
    for key in ("node_cavity_volume", "node_cavity_active", "node_cavity_collapse_count"):
        assert key in results

    n = len(results["time"])
    assert len(results["node_head"]["J1"]) == n
    assert len(results["node_pressure"]["J1"]) == n
    assert len(results["node_cavitation"]["J1"]) == n
    assert len(results["node_cavity_volume"]["J1"]) == n
    assert len(results["node_cavity_active"]["J1"]) == n
    assert len(results["node_cavity_collapse_count"]["J1"]) == n

    # Legacy mode should remain equivalent to explicit LegacyClamp selection.
    solver_explicit = _build_solver()
    explicit = solver_explicit.run(
        total_time=0.1,
        dt=0.01,
        cavitation_model=rthym_moc.CavitationModel.LegacyClamp,
    )

    for key in ("node_head", "node_pressure", "node_cavitation", "pipe_flow_gpm"):
        for name in results[key]:
            np.testing.assert_allclose(
                np.asarray(results[key][name]),
                np.asarray(explicit[key][name]),
                rtol=0.0,
                atol=1e-12,
            )

    # SI conversion path should preserve/add mapped cavity channels.
    si_results = rthym_moc.results_to_si(results)
    assert "node_head_m" in si_results
    assert "node_pressure_kpa" in si_results
    assert "pipe_flow_m3s" in si_results
    assert "node_cavity_volume_m3" in si_results
    assert "node_cavity_active" in si_results
    assert "node_cavity_collapse_count" in si_results
