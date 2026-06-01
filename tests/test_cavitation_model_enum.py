import rthym_moc
from rthym_moc.units import run_si


def test_cavitation_model_enum_exposed() -> None:
    assert hasattr(rthym_moc, "CavitationModel")
    assert rthym_moc.CavitationModel.LegacyClamp != rthym_moc.CavitationModel.DVCM


def test_run_accepts_cavitation_model_kwarg() -> None:
    solver = rthym_moc.MOCSolver()

    r1 = rthym_moc.NodeInput()
    r1.id = "R1"
    r1.type = "Tank"
    r1.head = 120.0

    j1 = rthym_moc.NodeInput()
    j1.id = "J1"
    j1.type = "Junction"

    r2 = rthym_moc.NodeInput()
    r2.id = "R2"
    r2.type = "Tank"
    r2.head = 80.0

    p1 = rthym_moc.PipeInput()
    p1.id = "P1"
    p1.from_node = "R1"
    p1.to_node = "J1"
    p1.length = 1000.0
    p1.diameter = 8.0
    p1.roughness = 120.0

    p2 = rthym_moc.PipeInput()
    p2.id = "P2"
    p2.from_node = "J1"
    p2.to_node = "R2"
    p2.length = 1000.0
    p2.diameter = 8.0
    p2.roughness = 120.0

    solver.add_node(r1)
    solver.add_node(j1)
    solver.add_node(r2)
    solver.add_pipe(p1)
    solver.add_pipe(p2)

    results = solver.run(
        total_time=0.05,
        dt=0.01,
        cavitation_model=rthym_moc.CavitationModel.LegacyClamp,
    )

    assert "time" in results
    assert len(results["time"]) == 5


def test_solver_set_get_cavitation_model_roundtrip() -> None:
    solver = rthym_moc.MOCSolver()
    assert solver.get_cavitation_model() == rthym_moc.CavitationModel.LegacyClamp

    solver.set_cavitation_model(rthym_moc.CavitationModel.DVCM)
    assert solver.get_cavitation_model() == rthym_moc.CavitationModel.DVCM


def test_run_si_accepts_cavitation_model_kwarg() -> None:
    solver = rthym_moc.MOCSolver()

    r1 = rthym_moc.NodeInput()
    r1.id = "R1"
    r1.type = "Tank"
    r1.head = 120.0

    j1 = rthym_moc.NodeInput()
    j1.id = "J1"
    j1.type = "Junction"

    r2 = rthym_moc.NodeInput()
    r2.id = "R2"
    r2.type = "Tank"
    r2.head = 80.0

    p1 = rthym_moc.PipeInput()
    p1.id = "P1"
    p1.from_node = "R1"
    p1.to_node = "J1"
    p1.length = 1000.0
    p1.diameter = 8.0
    p1.roughness = 120.0

    p2 = rthym_moc.PipeInput()
    p2.id = "P2"
    p2.from_node = "J1"
    p2.to_node = "R2"
    p2.length = 1000.0
    p2.diameter = 8.0
    p2.roughness = 120.0

    solver.add_node(r1)
    solver.add_node(j1)
    solver.add_node(r2)
    solver.add_pipe(p1)
    solver.add_pipe(p2)

    results = run_si(
        solver,
        total_time=0.05,
        dt=0.01,
        cavitation_model=rthym_moc.CavitationModel.LegacyClamp,
    )

    assert "time" in results
    assert len(results["time"]) == 5


def test_default_mode_stays_legacy_clamp_without_override() -> None:
    def build_solver() -> rthym_moc.MOCSolver:
        solver = rthym_moc.MOCSolver()

        r1 = rthym_moc.NodeInput()
        r1.id = "R1"
        r1.type = "Tank"
        r1.head = 120.0

        j1 = rthym_moc.NodeInput()
        j1.id = "J1"
        j1.type = "Junction"

        r2 = rthym_moc.NodeInput()
        r2.id = "R2"
        r2.type = "Tank"
        r2.head = 80.0

        p1 = rthym_moc.PipeInput()
        p1.id = "P1"
        p1.from_node = "R1"
        p1.to_node = "J1"
        p1.length = 1000.0
        p1.diameter = 8.0
        p1.roughness = 120.0

        p2 = rthym_moc.PipeInput()
        p2.id = "P2"
        p2.from_node = "J1"
        p2.to_node = "R2"
        p2.length = 1000.0
        p2.diameter = 8.0
        p2.roughness = 120.0

        solver.add_node(r1)
        solver.add_node(j1)
        solver.add_node(r2)
        solver.add_pipe(p1)
        solver.add_pipe(p2)
        return solver

    solver_default = build_solver()
    assert solver_default.get_cavitation_model() == rthym_moc.CavitationModel.LegacyClamp
    default_results = solver_default.run(total_time=0.05, dt=0.01)
    assert solver_default.get_cavitation_model() == rthym_moc.CavitationModel.LegacyClamp

    solver_explicit = build_solver()
    explicit_results = solver_explicit.run(
        total_time=0.05,
        dt=0.01,
        cavitation_model=rthym_moc.CavitationModel.LegacyClamp,
    )

    assert default_results["node_head"]["J1"].tolist() == explicit_results["node_head"]["J1"].tolist()
    assert default_results["node_pressure"]["J1"].tolist() == explicit_results["node_pressure"]["J1"].tolist()

    solver_si = build_solver()
    si_results = run_si(solver_si, total_time=0.05, dt=0.01)
    assert solver_si.get_cavitation_model() == rthym_moc.CavitationModel.LegacyClamp
    assert "time" in si_results
    assert len(si_results["time"]) == 5


def test_cavity_output_channels_are_additive() -> None:
    solver = rthym_moc.MOCSolver()

    r1 = rthym_moc.NodeInput()
    r1.id = "R1"
    r1.type = "Tank"
    r1.head = 120.0

    j1 = rthym_moc.NodeInput()
    j1.id = "J1"
    j1.type = "Junction"

    r2 = rthym_moc.NodeInput()
    r2.id = "R2"
    r2.type = "Tank"
    r2.head = 80.0

    p1 = rthym_moc.PipeInput()
    p1.id = "P1"
    p1.from_node = "R1"
    p1.to_node = "J1"
    p1.length = 1000.0
    p1.diameter = 8.0
    p1.roughness = 120.0

    p2 = rthym_moc.PipeInput()
    p2.id = "P2"
    p2.from_node = "J1"
    p2.to_node = "R2"
    p2.length = 1000.0
    p2.diameter = 8.0
    p2.roughness = 120.0

    solver.add_node(r1)
    solver.add_node(j1)
    solver.add_node(r2)
    solver.add_pipe(p1)
    solver.add_pipe(p2)

    results = solver.run(total_time=0.05, dt=0.01)

    # Existing channels are still present.
    assert "node_head" in results
    assert "node_pressure" in results
    assert "node_cavitation" in results
    assert "pipe_flow_gpm" in results

    # New additive channels are present and aligned in length.
    assert "node_cavity_volume" in results
    assert "node_cavity_active" in results
    assert "node_cavity_collapse_flag" in results
    assert "node_cavity_collapse_count" in results
    assert len(results["node_cavity_volume"]["J1"]) == len(results["time"])
    assert len(results["node_cavity_active"]["J1"]) == len(results["time"])
    assert len(results["node_cavity_collapse_flag"]["J1"]) == len(results["time"])
    assert len(results["node_cavity_collapse_count"]["J1"]) == len(results["time"])
