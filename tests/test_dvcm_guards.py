import pytest
import rthym_moc

pytestmark = pytest.mark.dvcm


def _build_junction_solver() -> rthym_moc.MOCSolver:
    solver = rthym_moc.MOCSolver()

    r1 = rthym_moc.NodeInput()
    r1.id = "R1"
    r1.type = "Tank"
    r1.head = 100.0

    j1 = rthym_moc.NodeInput()
    j1.id = "J1"
    j1.type = "Junction"
    j1.head = 100.0

    r2 = rthym_moc.NodeInput()
    r2.id = "R2"
    r2.type = "Tank"
    r2.head = 100.0

    p1 = rthym_moc.PipeInput()
    p1.id = "P1"
    p1.from_node = "R1"
    p1.to_node = "J1"
    p1.length = 40.0
    p1.diameter = 8.0
    p1.roughness = 120.0

    p2 = rthym_moc.PipeInput()
    p2.id = "P2"
    p2.from_node = "J1"
    p2.to_node = "R2"
    p2.length = 40.0
    p2.diameter = 8.0
    p2.roughness = 120.0

    solver.add_node(r1)
    solver.add_node(j1)
    solver.add_node(r2)
    solver.add_pipe(p1)
    solver.add_pipe(p2)
    return solver


def test_solver_run_rejects_invalid_dt() -> None:
    """Verifies that the solver rejects zero or negative dt."""
    solver = _build_junction_solver()

    with pytest.raises(ValueError, match="Timestep dt must be strictly positive"):
        solver.run(total_time=1.0, dt=0.0)

    with pytest.raises(ValueError, match="Timestep dt must be strictly positive"):
        solver.run(total_time=1.0, dt=-0.01)


def test_solver_run_rejects_invalid_total_time() -> None:
    """Verifies that the solver rejects negative total_time_s."""
    solver = _build_junction_solver()

    with pytest.raises(ValueError, match="Total simulation time must be non-negative"):
        solver.run(total_time=-0.5, dt=0.01)


def test_solver_run_rejects_invalid_usf_tau() -> None:
    """Verifies that the solver rejects zero or negative filter constant usf_tau."""
    solver = _build_junction_solver()

    with pytest.raises(ValueError, match="Filter time constant usf_tau must be strictly positive"):
        solver.run(total_time=1.0, dt=0.01, usf_tau=0.0)

    with pytest.raises(ValueError, match="Filter time constant usf_tau must be strictly positive"):
        solver.run(total_time=1.0, dt=0.01, usf_tau=-0.5)


def test_solver_run_detects_nan_blowup() -> None:
    """Verifies that the solver raises a RuntimeError when numerical instability/overflow occurs."""
    solver = _build_junction_solver()
    
    # Set extreme initial heads to force immediate arithmetic overflow and NaN/Inf propagation
    solver.set_head_schedule("R1", [(0.0, 1e300)])
    solver.set_head_schedule("R2", [(0.0, -1e300)])

    with pytest.raises(RuntimeError, match="Numerical instability"):
        solver.run(total_time=0.1, dt=0.01)
