import pytest
import numpy as np
import rthym_moc


pytestmark = pytest.mark.dvcm


def _build_air_valve_only_solver() -> rthym_moc.MOCSolver:
    solver = rthym_moc.MOCSolver()

    upstream = rthym_moc.NodeInput()
    upstream.id = "Upstream"
    upstream.type = "PressureBoundary"
    upstream.head = 135.0

    vent = rthym_moc.NodeInput()
    vent.id = "Vent"
    vent.type = "AirValve"
    vent.elevation = 0.0
    vent.head = 120.0
    vent.diameter = 6.0
    vent.air_release_head = 8.0
    vent.air_release_diameter = 0.25
    vent.gas_volume = 0.05
    vent.tank_volume = 2.0
    vent.loss_coeff_in = 0.8
    vent.loss_coeff_out = 0.7

    downstream = rthym_moc.NodeInput()
    downstream.id = "Downstream"
    downstream.type = "PressureBoundary"
    downstream.head = 120.0

    p1 = rthym_moc.PipeInput()
    p1.id = "P1"
    p1.from_node = "Upstream"
    p1.to_node = "Vent"
    p1.length = 80.0
    p1.diameter = 8.0
    p1.roughness = 120.0

    p2 = rthym_moc.PipeInput()
    p2.id = "P2"
    p2.from_node = "Vent"
    p2.to_node = "Downstream"
    p2.length = 240.0
    p2.diameter = 8.0
    p2.roughness = 120.0

    solver.add_node(upstream)
    solver.add_node(vent)
    solver.add_node(downstream)
    solver.add_pipe(p1)
    solver.add_pipe(p2)

    # Exercise the unsupported AirValve path with a transient, but do not
    # include any junction-like nodes that would legitimately enter DVCM.
    solver.set_head_schedule("Upstream", [(0.0, 135.0), (0.03, 90.0), (0.06, 135.0)])
    solver.set_head_schedule("Downstream", [(0.0, 120.0), (0.03, 70.0), (0.06, 120.0)])
    return solver


def _run_air_valve_only_case(model: rthym_moc.CavitationModel):
    solver = _build_air_valve_only_solver()
    return solver.run(
        total_time=0.06,
        dt=0.01,
        p_vapor_psi=50.0,
        cavitation_model=model,
    )


def test_dvcm_preserves_legacy_behavior_for_unsupported_air_valve_nodes() -> None:
    legacy = _run_air_valve_only_case(rthym_moc.CavitationModel.LegacyClamp)
    dvcm = _run_air_valve_only_case(rthym_moc.CavitationModel.DVCM)

    np.testing.assert_allclose(np.asarray(legacy["time"]), np.asarray(dvcm["time"]), rtol=0.0, atol=0.0)

    for key in ("node_head", "node_pressure", "node_cavitation", "node_cavity_active", "node_cavity_collapse_flag", "node_cavity_collapse_count"):
        np.testing.assert_allclose(
            np.asarray(legacy[key]["Vent"]),
            np.asarray(dvcm[key]["Vent"]),
            rtol=0.0,
            atol=0.0,
        )

    np.testing.assert_allclose(
        np.asarray(legacy["node_cavity_volume"]["Vent"]),
        np.asarray(dvcm["node_cavity_volume"]["Vent"]),
        rtol=0.0,
        atol=1e-12,
    )

    for pipe_id in ("P1", "P2"):
        np.testing.assert_allclose(
            np.asarray(legacy["pipe_flow_gpm"][pipe_id]),
            np.asarray(dvcm["pipe_flow_gpm"][pipe_id]),
            rtol=0.0,
            atol=0.0,
        )