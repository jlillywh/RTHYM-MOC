import pytest
import numpy as np
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


def test_dvcm_junction_cavity_initiates_when_head_drops_below_vapor_threshold() -> None:
    solver = _build_junction_solver()

    results = solver.run(
        total_time=0.05,
        dt=0.01,
        p_vapor_psi=50.0,
        cavitation_model=rthym_moc.CavitationModel.DVCM,
    )

    active = np.asarray(results["node_cavity_active"]["J1"], dtype=int)
    collapse_flag = np.asarray(results["node_cavity_collapse_flag"]["J1"], dtype=int)
    collapse_count = np.asarray(results["node_cavity_collapse_count"]["J1"], dtype=int)
    volume = np.asarray(results["node_cavity_volume"]["J1"], dtype=float)

    assert active[0] == 1
    assert np.all(active == 1)
    assert np.all(collapse_flag == 0)
    assert np.all(collapse_count == 0)
    assert np.all(volume >= 0.0)
    assert np.any(volume > 0.0)


def test_dvcm_regime_transitions_for_junction_node() -> None:
    solver = _build_junction_solver()

    # Raise both boundary heads over time so J1 transitions from below-vapor
    # (cavity active) to above-vapor (collapse transition/liquid full).
    solver.set_head_schedule("R1", [(0.0, 100.0), (0.05, 160.0)])
    solver.set_head_schedule("R2", [(0.0, 100.0), (0.05, 160.0)])

    results = solver.run(
        total_time=0.10,
        dt=0.01,
        p_vapor_psi=50.0,
        cavitation_model=rthym_moc.CavitationModel.DVCM,
    )

    active = np.asarray(results["node_cavity_active"]["J1"], dtype=int)
    collapse_flag = np.asarray(results["node_cavity_collapse_flag"]["J1"], dtype=int)
    collapse_count = np.asarray(results["node_cavity_collapse_count"]["J1"], dtype=int)

    assert active[0] == 1
    assert active[-1] == 0
    assert np.any(active == 1)
    assert np.any(active == 0)
    assert int(collapse_flag.sum()) >= 1
    assert int(collapse_count[-1]) >= 1


def test_dvcm_junction_collapse_sets_single_step_flag_and_count() -> None:
    solver = _build_junction_solver()

    solver.set_head_schedule("R1", [(0.0, 100.0), (0.05, 160.0)])
    solver.set_head_schedule("R2", [(0.0, 100.0), (0.05, 160.0)])

    results = solver.run(
        total_time=0.10,
        dt=0.01,
        p_vapor_psi=50.0,
        cavitation_model=rthym_moc.CavitationModel.DVCM,
    )

    active = np.asarray(results["node_cavity_active"]["J1"], dtype=int)
    collapse_flag = np.asarray(results["node_cavity_collapse_flag"]["J1"], dtype=int)
    collapse_count = np.asarray(results["node_cavity_collapse_count"]["J1"], dtype=int)

    flagged_steps = np.flatnonzero(collapse_flag)

    assert flagged_steps.size == 1
    collapse_idx = int(flagged_steps[0])
    assert active[collapse_idx - 1] == 1
    assert active[collapse_idx] == 0
    assert int(collapse_count[collapse_idx]) == 1
    assert np.all(np.diff(collapse_count) >= 0)
    assert int(collapse_count[-1]) == int(collapse_flag.sum())


def test_dvcm_cavity_volume_is_non_negative_and_bounded() -> None:
    solver = _build_junction_solver()

    solver.set_head_schedule("R1", [(0.0, 100.0), (0.05, 160.0)])
    solver.set_head_schedule("R2", [(0.0, 100.0), (0.05, 160.0)])

    results = solver.run(
        total_time=0.10,
        dt=0.01,
        p_vapor_psi=50.0,
        cavitation_model=rthym_moc.CavitationModel.DVCM,
    )

    volume = np.asarray(results["node_cavity_volume"]["J1"], dtype=float)
    assert np.all(volume >= -1e-12)
    assert np.any(volume > 0.0)

    diam_ft = 8.0 / 12.0
    area_ft2 = np.pi * (diam_ft / 2.0) ** 2
    cavity_capacity_ft3 = (0.5 * area_ft2 * 40.0) + (0.5 * area_ft2 * 40.0)
    max_step_delta_ft3 = 0.25 * cavity_capacity_ft3

    assert float(volume.max()) <= cavity_capacity_ft3 + 1e-9
    if len(volume) > 1:
        step_delta = np.abs(np.diff(volume))
        assert float(step_delta.max()) <= max_step_delta_ft3 + 1e-9


def test_dvcm_regime_logic_is_scoped_to_junction_like_nodes() -> None:
    solver = _build_junction_solver()

    results = solver.run(
        total_time=0.05,
        dt=0.01,
        p_vapor_psi=50.0,
        cavitation_model=rthym_moc.CavitationModel.DVCM,
    )

    # Tank nodes should still report cavity channels but remain in the baseline
    # scaffold path (no junction-only regime transitions expected).
    r1_collapse = np.asarray(results["node_cavity_collapse_count"]["R1"], dtype=int)
    r2_collapse = np.asarray(results["node_cavity_collapse_count"]["R2"], dtype=int)

    assert int(r1_collapse[-1]) == 0
    assert int(r2_collapse[-1]) == 0


def test_dvcm_hysteresis_reduces_mode_chatter_near_threshold() -> None:
    solver = _build_junction_solver()

    # Oscillate both boundary heads inside a narrow band around the vapor head.
    # DVCM should enter cavity once, then resist repeated collapse/reactivation
    # while the candidate head remains within the hysteresis window.
    schedule = [
        (0.0, 121.8),
        (0.01, 122.7),
        (0.02, 121.9),
        (0.03, 122.8),
        (0.04, 121.8),
        (0.05, 122.7),
    ]
    solver.set_head_schedule("R1", schedule)
    solver.set_head_schedule("R2", schedule)

    results = solver.run(
        total_time=0.05,
        dt=0.01,
        p_vapor_psi=53.0,
        cavitation_model=rthym_moc.CavitationModel.DVCM,
    )

    active = np.asarray(results["node_cavity_active"]["J1"], dtype=int)
    collapse_count = np.asarray(results["node_cavity_collapse_count"]["J1"], dtype=int)

    transitions = int(np.sum(np.diff(active) != 0))
    assert transitions <= 1
    assert int(collapse_count[-1]) <= 1
