import pytest
import numpy as np
import rthym_moc
from rthym_moc.chainage_air_valve import (
    PipeNetwork,
    attach_air_valve_at_survey_high_point,
)

pytestmark = pytest.mark.dvcm


def _make_node(node_id, node_type, **kwargs):
    node = rthym_moc.NodeInput()
    node.id = node_id
    node.type = node_type
    for key, value in kwargs.items():
        setattr(node, key, value)
    return node


def _make_pipe(pipe_id, from_node, to_node, length_ft, flow_gpm):
    pipe = rthym_moc.PipeInput()
    pipe.id = pipe_id
    pipe.from_node = from_node
    pipe.to_node = to_node
    pipe.length = length_ft
    pipe.diameter = 12.0
    pipe.roughness = 130.0
    pipe.flow_gpm = flow_gpm
    return pipe


def _build_air_valve_solver(with_restart=False) -> rthym_moc.MOCSolver:
    solver = rthym_moc.MOCSolver()
    solver.add_node(_make_node("Rlow", "PressureBoundary", head=100.0))
    solver.add_node(_make_node("PumpIn", "Junction", head=100.0))
    solver.add_node(
        _make_node(
            "Pump_A",
            "Pump",
            design_head=120.0,
            design_flow=500.0,
            current_speed=100.0,
            head=220.0,
        )
    )
    solver.add_node(_make_node("Jd", "Junction", head=220.0))
    solver.add_node(
        _make_node(
            "Vent",
            "AirValve",
            elevation=0.0,
            head=160.0,
            diameter=6.0,
            air_release_diameter=0.25,
            gas_volume=0.05,
            tank_volume=2.0,
            loss_coeff_in=0.8,
            loss_coeff_out=0.7,
        )
    )
    solver.add_node(_make_node("Rhigh", "PressureBoundary", head=160.0))

    solver.add_pipe(_make_pipe("Ps", "Rlow", "PumpIn", 500.0, 800.0))
    solver.add_pipe(_make_pipe("Psuction", "PumpIn", "Pump_A", 40.0, 800.0))
    solver.add_pipe(_make_pipe("Ppump", "Pump_A", "Jd", 40.0, 800.0))
    solver.add_pipe(_make_pipe("Pstub", "Jd", "Vent", 40.0, 800.0))
    solver.add_pipe(_make_pipe("Pmain", "Vent", "Rhigh", 4000.0, 800.0))

    solver.set_pump_schedule(
        "Pump_A",
        [
            (0.0, 100.0),
            (4.99, 100.0),
            (5.0, 0.0),
            (7.99, 0.0),
            (8.0, 100.0 if with_restart else 0.0),
            (12.0, 100.0 if with_restart else 0.0),
        ],
    )
    return solver


def test_dvcm_air_valve_regression() -> None:
    # Run with LegacyClamp
    solver_legacy = _build_air_valve_solver(with_restart=True)
    res_legacy = solver_legacy.run(
        total_time=12.0,
        dt=0.01,
        p_vapor_psi=-14.0,
        cavitation_model=rthym_moc.CavitationModel.LegacyClamp,
    )

    # Run with DVCM
    solver_dvcm = _build_air_valve_solver(with_restart=True)
    res_dvcm = solver_dvcm.run(
        total_time=12.0,
        dt=0.01,
        p_vapor_psi=-14.0,
        cavitation_model=rthym_moc.CavitationModel.DVCM,
    )

    # Assert exact equivalence of all output variables
    np.testing.assert_allclose(res_legacy["time"], res_dvcm["time"], rtol=0.0, atol=0.0)
    for key in ("node_head", "node_pressure", "node_cavitation"):
        for node_id in ("Rlow", "PumpIn", "Pump_A", "Jd", "Vent", "Rhigh"):
            np.testing.assert_allclose(
                res_legacy[key][node_id],
                res_dvcm[key][node_id],
                rtol=0.0,
                atol=1e-12,
                err_msg=f"Mismatch in {key} for {node_id}"
            )
    for pipe_id in ("Ps", "Psuction", "Ppump", "Pstub", "Pmain"):
        np.testing.assert_allclose(
            res_legacy["pipe_flow_gpm"][pipe_id],
            res_dvcm["pipe_flow_gpm"][pipe_id],
            rtol=0.0,
            atol=1e-12,
            err_msg=f"Mismatch in pipe_flow_gpm for {pipe_id}"
        )


def test_dvcm_air_valve_interaction() -> None:
    solver = rthym_moc.MOCSolver()

    r1 = rthym_moc.NodeInput()
    r1.id = "R1"
    r1.type = "PressureBoundary"
    r1.head = 100.0

    j1 = rthym_moc.NodeInput()
    j1.id = "J1"
    j1.type = "Junction"

    av1 = rthym_moc.NodeInput()
    av1.id = "AV1"
    av1.type = "AirValve"
    av1.elevation = 0.0
    av1.head = 100.0
    av1.diameter = 6.0
    av1.air_release_head = 0.0
    av1.air_release_diameter = 0.25
    av1.gas_volume = 0.01
    av1.tank_volume = 2.0
    av1.loss_coeff_in = 0.8
    av1.loss_coeff_out = 0.7

    v1 = rthym_moc.NodeInput()
    v1.id = "V1"
    v1.type = "Valve"
    v1.diameter = 8.0
    v1.current_setting = 100.0

    r2 = rthym_moc.NodeInput()
    r2.id = "R2"
    r2.type = "PressureBoundary"
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
    p2.to_node = "AV1"
    p2.length = 40.0
    p2.diameter = 8.0
    p2.roughness = 120.0

    p3 = rthym_moc.PipeInput()
    p3.id = "P3"
    p3.from_node = "AV1"
    p3.to_node = "V1"
    p3.length = 40.0
    p3.diameter = 8.0
    p3.roughness = 120.0

    p4 = rthym_moc.PipeInput()
    p4.id = "P4"
    p4.from_node = "V1"
    p4.to_node = "R2"
    p4.length = 40.0
    p4.diameter = 8.0
    p4.roughness = 120.0

    solver.add_node(r1)
    solver.add_node(j1)
    solver.add_node(av1)
    solver.add_node(v1)
    solver.add_node(r2)

    solver.add_pipe(p1)
    solver.add_pipe(p2)
    solver.add_pipe(p3)
    solver.add_pipe(p4)

    # Severe transient: drop reservoir heads, then recover.
    # This triggers both DVCM cavitation at J1 and air pocket admission/release at AV1.
    solver.set_head_schedule("R1", [(0.0, 100.0), (0.02, 10.0), (0.10, 300.0)])
    solver.set_head_schedule("R2", [(0.0, 100.0), (0.02, 10.0), (0.10, 300.0)])

    res = solver.run(
        total_time=0.40,
        dt=0.01,
        p_vapor_psi=50.0,
        cavitation_model=rthym_moc.CavitationModel.DVCM,
    )

    # J1 is DVCM-supported, so its cavity should activate, grow, and collapse
    active_j1 = np.asarray(res["node_cavity_active"]["J1"], dtype=int)
    vol_j1 = np.asarray(res["node_cavity_volume"]["J1"], dtype=float)
    collapse_count_j1 = np.asarray(res["node_cavity_collapse_count"]["J1"], dtype=int)

    assert np.any(active_j1 == 1)
    assert np.any(vol_j1 > 0.0)
    # The cavity should collapse at least once during the simulation
    assert collapse_count_j1[-1] >= 1
    # Ensure there are some steps where it has collapsed back to 0.0
    assert np.any(vol_j1 == 0.0)

    # AV1 is an AirValve, so it should behave stably and physically
    head_av1 = np.asarray(res["node_head"]["AV1"], dtype=float)
    assert not np.isnan(head_av1).any()
    assert not np.isinf(head_av1).any()


def _build_long_line_network(
    *,
    with_summit_air_valve: bool,
    interior_dvcm_chainages_ft: list[float],
) -> PipeNetwork:
    """Sloping long-line reach with optional summit air valve and interior watchpoints."""
    length_ft = 4000.0
    survey = [(0.0, 100.0), (2000.0, 320.0), (length_ft, 120.0)]
    net = PipeNetwork()
    net.add_node(_make_node("R1", "PressureBoundary", elevation=100.0, head=400.0))
    net.add_node(_make_node("R2", "PressureBoundary", elevation=120.0, head=400.0))

    pipe = rthym_moc.PipeInput()
    pipe.id = "Pmain"
    pipe.from_node = "R1"
    pipe.to_node = "R2"
    pipe.length = length_ft
    pipe.diameter = 12.0
    pipe.roughness = 130.0
    pipe.flow_gpm = 800.0
    pipe.elevation_profile = survey
    pipe.interior_dvcm_chainages_ft = interior_dvcm_chainages_ft
    net.add_pipe(pipe)

    if with_summit_air_valve:
        attach_air_valve_at_survey_high_point(
            net,
            "Pmain",
            valve_node_id="AV_summit",
            gas_volume=0.05,
            tank_volume=2.0,
        )
    return net


def _build_long_line_summit_air_valve_network() -> PipeNetwork:
    return _build_long_line_network(
        with_summit_air_valve=True,
        interior_dvcm_chainages_ft=[1000.0, 3000.0],
    )


def _run_chainage_air_valve_interior_dvcm_case(
    net: PipeNetwork,
) -> dict[str, object]:
    solver = rthym_moc.MOCSolver()
    net.apply_to(solver)
    solver.set_head_schedule("R1", [(0.0, 400.0), (0.05, 50.0), (0.30, 400.0)])
    solver.set_head_schedule("R2", [(0.0, 400.0), (0.05, 50.0), (0.30, 400.0)])
    return solver.run(
        total_time=0.40,
        dt=0.001,
        p_vapor_psi=50.0,
        cavitation_model=rthym_moc.CavitationModel.DVCM,
        record_pipe_profiles=True,
        enable_interior_dvcm=True,
    )


def _watchpoint_cavity_peak(
    results: dict[str, object],
    pipe_id: str,
    grid_index: int,
) -> tuple[float, bool]:
    volume = np.asarray(
        results["pipe_profile_cavity_volume"][pipe_id][:, grid_index],
        dtype=float,
    )
    active = np.asarray(
        results["pipe_profile_cavity_active"][pipe_id][:, grid_index],
        dtype=int,
    )
    return float(volume.max()), bool(np.any(active == 1))


def _peak_cavity_at_chainage(
    results: dict[str, object],
    pipe_id: str,
    chainage_ft: float,
) -> tuple[float, float, bool]:
    chainages = np.asarray(results["pipe_profile_chainage_ft"][pipe_id], dtype=float)
    grid_index = int(np.argmin(np.abs(chainages - chainage_ft)))
    peak_volume, any_active = _watchpoint_cavity_peak(results, pipe_id, grid_index)
    return float(chainages[grid_index]), peak_volume, any_active


def test_dvcm_chainage_air_valve_interior_dvcm_interaction() -> None:
    """Summit air valve coexists with sparse interior DVCM on split pipe reaches."""
    net = _build_long_line_summit_air_valve_network()
    results = _run_chainage_air_valve_interior_dvcm_case(net)

    assert "pipe_profile_cavity_volume" in results
    assert "pipe_profile_cavity_active" in results
    assert "pipe_interior_dvcm_grid_indices" in results

    grid_indices = results["pipe_interior_dvcm_grid_indices"]
    for pipe_id in ("Pmain_up", "Pmain_dn"):
        assert pipe_id in grid_indices
        assert len(grid_indices[pipe_id]) == 1

        watch_index = int(grid_indices[pipe_id][0])
        chainage = float(results["pipe_profile_chainage_ft"][pipe_id][watch_index])
        assert chainage == pytest.approx(1000.0)

        peak_volume, any_active = _watchpoint_cavity_peak(results, pipe_id, watch_index)
        assert any_active
        assert peak_volume > 0.0

    head_av = np.asarray(results["node_head"]["AV_summit"], dtype=float)
    assert not np.isnan(head_av).any()
    assert not np.isinf(head_av).any()


def test_dvcm_chainage_air_valve_interior_dvcm_rebases_watchpoints() -> None:
    """Splitting at the survey high point preserves rebased interior watchpoints."""
    net = _build_long_line_summit_air_valve_network()

    assert net.pipes["Pmain_up"].interior_dvcm_chainages_ft == [1000.0]
    assert net.pipes["Pmain_dn"].interior_dvcm_chainages_ft == [1000.0]

    results = _run_chainage_air_valve_interior_dvcm_case(net)
    up_idx = int(results["pipe_interior_dvcm_grid_indices"]["Pmain_up"][0])
    dn_idx = int(results["pipe_interior_dvcm_grid_indices"]["Pmain_dn"][0])

    up_peak, _ = _watchpoint_cavity_peak(results, "Pmain_up", up_idx)
    dn_peak, _ = _watchpoint_cavity_peak(results, "Pmain_dn", dn_idx)
    assert up_peak > 0.0
    assert dn_peak > 0.0


def test_dvcm_long_line_summit_air_valve_prevents_cavity() -> None:
    """Summit air valve eliminates interior cavity at the survey high point vs bare pipe."""
    summit_chainage_ft = 2000.0
    watchpoints = [summit_chainage_ft]

    unprotected = _run_chainage_air_valve_interior_dvcm_case(
        _build_long_line_network(
            with_summit_air_valve=False,
            interior_dvcm_chainages_ft=watchpoints,
        )
    )
    protected = _run_chainage_air_valve_interior_dvcm_case(
        _build_long_line_network(
            with_summit_air_valve=True,
            interior_dvcm_chainages_ft=watchpoints,
        )
    )

    bare_chain, bare_peak, bare_active = _peak_cavity_at_chainage(
        unprotected,
        "Pmain",
        summit_chainage_ft,
    )
    assert bare_chain == pytest.approx(summit_chainage_ft)
    assert bare_active
    assert bare_peak > 0.05

    up_chain, up_peak, up_active = _peak_cavity_at_chainage(
        protected,
        "Pmain_up",
        summit_chainage_ft,
    )
    dn_chain, dn_peak, dn_active = _peak_cavity_at_chainage(
        protected,
        "Pmain_dn",
        0.0,
    )
    assert up_chain == pytest.approx(summit_chainage_ft)
    assert dn_chain == pytest.approx(0.0)
    assert up_peak == pytest.approx(0.0)
    assert dn_peak == pytest.approx(0.0)
    assert not up_active
    assert not dn_active
    assert bare_peak > max(up_peak, dn_peak)

    head_av = np.asarray(protected["node_head"]["AV_summit"], dtype=float)
    assert not np.isnan(head_av).any()
    assert not np.isinf(head_av).any()
