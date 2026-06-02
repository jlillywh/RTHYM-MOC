import pytest
import numpy as np
import rthym_moc

pytestmark = pytest.mark.dvcm


def _build_standpipe_solver() -> rthym_moc.MOCSolver:
    solver = rthym_moc.MOCSolver()

    r1 = rthym_moc.NodeInput()
    r1.id = "R1"
    r1.type = "PressureBoundary"
    r1.head = 150.0

    r2 = rthym_moc.NodeInput()
    r2.id = "R2"
    r2.type = "PressureBoundary"
    r2.head = 143.5

    sp1 = rthym_moc.NodeInput()
    sp1.id = "SP1"
    sp1.type = "Standpipe"
    sp1.head = 143.5
    sp1.tank_area = 1.0

    v1 = rthym_moc.NodeInput()
    v1.id = "V1"
    v1.type = "Valve"
    v1.diameter = 12.0
    v1.current_setting = 100.0

    p1 = rthym_moc.PipeInput()
    p1.id = "P1"
    p1.from_node = "R1"
    p1.to_node = "SP1"
    p1.length = 3000.0
    p1.diameter = 12.0
    p1.roughness = 130.0
    p1.flow_gpm = 500.0

    p2 = rthym_moc.PipeInput()
    p2.id = "P2"
    p2.from_node = "SP1"
    p2.to_node = "V1"
    p2.length = 40.0
    p2.diameter = 12.0
    p2.roughness = 130.0
    p2.flow_gpm = 500.0

    p3 = rthym_moc.PipeInput()
    p3.id = "P3"
    p3.from_node = "V1"
    p3.to_node = "R2"
    p3.length = 40.0
    p3.diameter = 12.0
    p3.roughness = 130.0
    p3.flow_gpm = 0.0

    solver.add_node(r1)
    solver.add_node(sp1)
    solver.add_node(v1)
    solver.add_node(r2)
    solver.add_pipe(p1)
    solver.add_pipe(p2)
    solver.add_pipe(p3)

    return solver


def test_dvcm_standpipe_regression() -> None:
    # 1. Run with LegacyClamp
    solver_legacy = _build_standpipe_solver()
    solver_legacy.set_valve_schedule("V1", [(0.0, 100.0), (0.05, 0.0)])
    res_legacy = solver_legacy.run(
        total_time=2.0,
        dt=0.01,
        p_vapor_psi=-14.0,
        cavitation_model=rthym_moc.CavitationModel.LegacyClamp,
    )

    # 2. Run with DVCM
    solver_dvcm = _build_standpipe_solver()
    solver_dvcm.set_valve_schedule("V1", [(0.0, 100.0), (0.05, 0.0)])
    res_dvcm = solver_dvcm.run(
        total_time=2.0,
        dt=0.01,
        p_vapor_psi=-14.0,
        cavitation_model=rthym_moc.CavitationModel.DVCM,
    )

    # 3. Assert exact equivalence of all output variables
    np.testing.assert_allclose(res_legacy["time"], res_dvcm["time"], rtol=0.0, atol=0.0)
    for key in ("node_head", "node_pressure", "node_cavitation"):
        for node_id in ("R1", "SP1", "V1", "R2"):
            np.testing.assert_allclose(
                res_legacy[key][node_id],
                res_dvcm[key][node_id],
                rtol=0.0,
                atol=1e-12,
                err_msg=f"Mismatch in {key} for {node_id}"
            )
    for pipe_id in ("P1", "P2", "P3"):
        np.testing.assert_allclose(
            res_legacy["pipe_flow_gpm"][pipe_id],
            res_dvcm["pipe_flow_gpm"][pipe_id],
            rtol=0.0,
            atol=1e-12,
            err_msg=f"Mismatch in pipe_flow_gpm for {pipe_id}"
        )


def _build_hydropneumatic_solver() -> rthym_moc.MOCSolver:
    solver = rthym_moc.MOCSolver()

    rlow = rthym_moc.NodeInput()
    rlow.id = "Rlow"
    rlow.type = "PressureBoundary"
    rlow.head = 100.0

    pumpin = rthym_moc.NodeInput()
    pumpin.id = "PumpIn"
    pumpin.type = "Junction"

    pump = rthym_moc.NodeInput()
    pump.id = "Pump_A"
    pump.type = "Pump"
    pump.design_head = 120.0
    pump.design_flow = 500.0
    pump.current_speed = 100.0

    jd = rthym_moc.NodeInput()
    jd.id = "Jd"
    jd.type = "Junction"

    hpt = rthym_moc.NodeInput()
    hpt.id = "HPT1"
    hpt.type = "HydropneumaticTank"
    hpt.head = 160.0
    hpt.diameter = 4.0
    hpt.gas_volume = 4.0
    hpt.tank_volume = 10.0
    hpt.polytropic_n = 1.2
    hpt.loss_coeff_in = 0.7
    hpt.loss_coeff_out = 0.7

    rhigh = rthym_moc.NodeInput()
    rhigh.id = "Rhigh"
    rhigh.type = "PressureBoundary"
    rhigh.head = 160.0

    ps = rthym_moc.PipeInput()
    ps.id = "Ps"
    ps.from_node = "Rlow"
    ps.to_node = "PumpIn"
    ps.length = 500.0
    ps.diameter = 12.0
    ps.roughness = 130.0
    ps.flow_gpm = 800.0

    ppump = rthym_moc.PipeInput()
    ppump.id = "Ppump"
    ppump.from_node = "Pump_A"
    ppump.to_node = "Jd"
    ppump.length = 40.0
    ppump.diameter = 12.0
    ppump.roughness = 130.0
    ppump.flow_gpm = 800.0

    pstub = rthym_moc.PipeInput()
    pstub.id = "Pstub"
    pstub.from_node = "Jd"
    pstub.to_node = "HPT1"
    pstub.length = 40.0
    pstub.diameter = 12.0
    pstub.roughness = 130.0
    pstub.flow_gpm = 800.0

    pmain = rthym_moc.PipeInput()
    pmain.id = "Pmain"
    pmain.from_node = "HPT1"
    pmain.to_node = "Rhigh"
    pmain.length = 4000.0
    pmain.diameter = 12.0
    pmain.roughness = 130.0
    pmain.flow_gpm = 800.0

    solver.add_node(rlow)
    solver.add_node(pumpin)
    solver.add_node(pump)
    solver.add_node(jd)
    solver.add_node(hpt)
    solver.add_node(rhigh)

    solver.add_pipe(ps)
    solver.add_pipe(ppump)
    solver.add_pipe(pstub)
    solver.add_pipe(pmain)

    return solver


def test_dvcm_hydropneumatic_regression() -> None:
    solver_legacy = _build_hydropneumatic_solver()
    solver_legacy.set_pump_schedule("Pump_A", [(0.0, 100.0), (0.10, 0.0)])
    res_legacy = solver_legacy.run(
        total_time=1.5,
        dt=0.01,
        p_vapor_psi=-14.0,
        cavitation_model=rthym_moc.CavitationModel.LegacyClamp,
    )

    solver_dvcm = _build_hydropneumatic_solver()
    solver_dvcm.set_pump_schedule("Pump_A", [(0.0, 100.0), (0.10, 0.0)])
    res_dvcm = solver_dvcm.run(
        total_time=1.5,
        dt=0.01,
        p_vapor_psi=-14.0,
        cavitation_model=rthym_moc.CavitationModel.DVCM,
    )

    np.testing.assert_allclose(res_legacy["time"], res_dvcm["time"], rtol=0.0, atol=0.0)
    for key in ("node_head", "node_pressure", "node_cavitation"):
        for node_id in ("Rlow", "PumpIn", "Pump_A", "Jd", "HPT1", "Rhigh"):
            np.testing.assert_allclose(
                res_legacy[key][node_id],
                res_dvcm[key][node_id],
                rtol=0.0,
                atol=1e-12,
                err_msg=f"Mismatch in {key} for {node_id}"
            )
    for pipe_id in ("Ps", "Ppump", "Pstub", "Pmain"):
        np.testing.assert_allclose(
            res_legacy["pipe_flow_gpm"][pipe_id],
            res_dvcm["pipe_flow_gpm"][pipe_id],
            rtol=0.0,
            atol=1e-12,
            err_msg=f"Mismatch in pipe_flow_gpm for {pipe_id}"
        )


def test_dvcm_standpipe_interaction() -> None:
    solver = rthym_moc.MOCSolver()

    r1 = rthym_moc.NodeInput()
    r1.id = "R1"
    r1.type = "PressureBoundary"
    r1.head = 100.0

    j1 = rthym_moc.NodeInput()
    j1.id = "J1"
    j1.type = "Junction"

    sp1 = rthym_moc.NodeInput()
    sp1.id = "SP1"
    sp1.type = "Standpipe"
    sp1.head = 100.0
    sp1.tank_area = 1.0

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
    p2.to_node = "SP1"
    p2.length = 40.0
    p2.diameter = 8.0
    p2.roughness = 120.0

    p3 = rthym_moc.PipeInput()
    p3.id = "P3"
    p3.from_node = "SP1"
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
    solver.add_node(sp1)
    solver.add_node(v1)
    solver.add_node(r2)

    solver.add_pipe(p1)
    solver.add_pipe(p2)
    solver.add_pipe(p3)
    solver.add_pipe(p4)

    # Force a severe transient on reservoir heads to induce cavitation at J1
    solver.set_head_schedule("R1", [(0.0, 100.0), (0.02, 10.0), (0.10, 300.0)])
    solver.set_head_schedule("R2", [(0.0, 100.0), (0.02, 10.0), (0.10, 300.0)])

    res = solver.run(
        total_time=0.40,
        dt=0.01,
        p_vapor_psi=50.0,  # high vapor pressure floor to guarantee cavitation
        cavitation_model=rthym_moc.CavitationModel.DVCM,
    )

    active = np.asarray(res["node_cavity_active"]["J1"], dtype=int)
    volume = np.asarray(res["node_cavity_volume"]["J1"], dtype=float)
    head_sp1 = np.asarray(res["node_head"]["SP1"], dtype=float)

    # Verify J1 undergoes cavitation and collapse
    assert np.any(active == 1)
    assert np.any(volume > 0.0)
    assert active[-1] == 0
    assert volume[-1] == 0.0

    # Verify Standpipe level updates stably and physically (rises and falls)
    assert not np.isnan(head_sp1).any()
    assert not np.isinf(head_sp1).any()
    assert np.any(head_sp1 > 100.0)  # should rise above initial level during recovery


def test_dvcm_hydropneumatic_interaction() -> None:
    solver = rthym_moc.MOCSolver()

    r1 = rthym_moc.NodeInput()
    r1.id = "R1"
    r1.type = "PressureBoundary"
    r1.head = 100.0

    j1 = rthym_moc.NodeInput()
    j1.id = "J1"
    j1.type = "Junction"

    hpt = rthym_moc.NodeInput()
    hpt.id = "HPT1"
    hpt.type = "HydropneumaticTank"
    hpt.head = 100.0
    hpt.diameter = 4.0
    hpt.gas_volume = 4.0
    hpt.tank_volume = 10.0
    hpt.polytropic_n = 1.2
    hpt.loss_coeff_in = 0.7
    hpt.loss_coeff_out = 0.7

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
    p2.to_node = "HPT1"
    p2.length = 40.0
    p2.diameter = 8.0
    p2.roughness = 120.0

    p3 = rthym_moc.PipeInput()
    p3.id = "P3"
    p3.from_node = "HPT1"
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
    solver.add_node(hpt)
    solver.add_node(v1)
    solver.add_node(r2)

    solver.add_pipe(p1)
    solver.add_pipe(p2)
    solver.add_pipe(p3)
    solver.add_pipe(p4)

    # Force a severe transient to trigger cavitation at J1
    solver.set_head_schedule("R1", [(0.0, 100.0), (0.02, 10.0), (0.10, 300.0)])
    solver.set_head_schedule("R2", [(0.0, 100.0), (0.02, 10.0), (0.10, 300.0)])

    res = solver.run(
        total_time=0.40,
        dt=0.01,
        p_vapor_psi=50.0,
        cavitation_model=rthym_moc.CavitationModel.DVCM,
    )

    active = np.asarray(res["node_cavity_active"]["J1"], dtype=int)
    volume = np.asarray(res["node_cavity_volume"]["J1"], dtype=float)
    head_hpt = np.asarray(res["node_head"]["HPT1"], dtype=float)

    # J1 undergoes cavitation and collapse
    assert np.any(active == 1)
    assert np.any(volume > 0.0)
    assert active[-1] == 0
    assert volume[-1] == 0.0

    # Hydropneumatic tank head/pressure responds stably
    assert not np.isnan(head_hpt).any()
    assert not np.isinf(head_hpt).any()
