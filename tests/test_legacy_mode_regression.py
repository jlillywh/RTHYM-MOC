import numpy as np
import rthym_moc


def _build_reference_solver() -> rthym_moc.MOCSolver:
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


def test_legacy_mode_snapshot_regression() -> None:
    solver = _build_reference_solver()

    results = solver.run(
        total_time=0.1,
        dt=0.01,
        cavitation_model=rthym_moc.CavitationModel.LegacyClamp,
    )

    sample_idx = np.array([0, 1, 2, 5, 9], dtype=int)

    np.testing.assert_allclose(
        np.asarray(results["time"])[sample_idx],
        np.array([0.01, 0.02, 0.03, 0.06, 0.10]),
        rtol=0.0,
        atol=1e-12,
    )
    np.testing.assert_allclose(
        np.asarray(results["node_head"]["J1"])[sample_idx],
        np.array([
            99.63164598778812,
            99.63164598778812,
            99.63164598778808,
            99.63164598778812,
            99.63164598778816,
        ]),
        rtol=0.0,
        atol=1e-10,
    )
    np.testing.assert_allclose(
        np.asarray(results["node_pressure"]["J1"])[sample_idx],
        np.array([
            43.13058267869616,
            43.13058267869616,
            43.130582678696136,
            43.13058267869616,
            43.13058267869617,
        ]),
        rtol=0.0,
        atol=1e-10,
    )
    np.testing.assert_allclose(
        np.asarray(results["pipe_flow_gpm"]["P1"])[sample_idx],
        np.array([
            200.7762846454881,
            201.52239202558363,
            202.18208744688368,
            203.93340094179825,
            205.7415539395172,
        ]),
        rtol=0.0,
        atol=1e-9,
    )
    np.testing.assert_allclose(
        np.asarray(results["pipe_flow_gpm"]["P2"])[sample_idx],
        np.array([
            201.00270100042215,
            201.96642303304554,
            202.81852961889155,
            205.08064288315623,
            207.41617383854333,
        ]),
        rtol=0.0,
        atol=1e-9,
    )

    np.testing.assert_array_equal(
        np.asarray(results["node_cavitation"]["J1"])[sample_idx],
        np.array([0, 0, 0, 0, 0], dtype=int),
    )
    np.testing.assert_array_equal(
        np.asarray(results["node_cavity_active"]["J1"])[sample_idx],
        np.array([0, 0, 0, 0, 0], dtype=int),
    )
    np.testing.assert_array_equal(
        np.asarray(results["node_cavity_collapse_count"]["J1"])[sample_idx],
        np.array([0, 0, 0, 0, 0], dtype=int),
    )
    np.testing.assert_allclose(
        np.asarray(results["node_cavity_volume"]["J1"])[sample_idx],
        np.array([0.0, 0.0, 0.0, 0.0, 0.0]),
        rtol=0.0,
        atol=1e-12,
    )


def test_legacy_default_and_explicit_outputs_match() -> None:
    solver_default = _build_reference_solver()
    out_default = solver_default.run(total_time=0.1, dt=0.01)

    solver_explicit = _build_reference_solver()
    out_explicit = solver_explicit.run(
        total_time=0.1,
        dt=0.01,
        cavitation_model=rthym_moc.CavitationModel.LegacyClamp,
    )

    for key in ("node_head", "node_pressure", "node_cavitation", "pipe_flow_gpm"):
        for node_or_pipe_id in out_default[key]:
            np.testing.assert_allclose(
                np.asarray(out_default[key][node_or_pipe_id]),
                np.asarray(out_explicit[key][node_or_pipe_id]),
                rtol=0.0,
                atol=1e-12,
            )
