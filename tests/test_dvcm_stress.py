import pytest
import numpy as np
import rthym_moc

pytestmark = pytest.mark.dvcm


def _build_junction_solver(pipe_length=40.0) -> rthym_moc.MOCSolver:
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
    p1.length = pipe_length
    p1.diameter = 8.0
    p1.roughness = 120.0

    p2 = rthym_moc.PipeInput()
    p2.id = "P2"
    p2.from_node = "J1"
    p2.to_node = "R2"
    p2.length = pipe_length
    p2.diameter = 8.0
    p2.roughness = 120.0

    solver.add_node(r1)
    solver.add_node(j1)
    solver.add_node(r2)
    solver.add_pipe(p1)
    solver.add_pipe(p2)
    return solver


def _build_multi_device_solver() -> rthym_moc.MOCSolver:
    solver = rthym_moc.MOCSolver()

    # Reservoirs
    r1 = rthym_moc.NodeInput()
    r1.id = "R1"
    r1.type = "Tank"
    r1.head = 100.0

    r2 = rthym_moc.NodeInput()
    r2.id = "R2"
    r2.type = "Tank"
    r2.head = 80.0

    # Junctions
    j1 = rthym_moc.NodeInput()
    j1.id = "J1"
    j1.type = "Junction"
    j1.head = 95.0

    j2 = rthym_moc.NodeInput()
    j2.id = "J2"
    j2.type = "Junction"
    j2.head = 90.0

    # Standard Valve
    v1 = rthym_moc.NodeInput()
    v1.id = "V1"
    v1.type = "Valve"
    v1.diameter = 8.0
    v1.current_setting = 100.0
    v1.head = 92.0

    # Check Valve
    cv1 = rthym_moc.NodeInput()
    cv1.id = "CV1"
    cv1.type = "CheckValve"
    cv1.diameter = 8.0
    cv1.closure_time = 0.01
    cv1.head = 91.0

    # Pump (inline centrifugal pump with trip)
    pmp1 = rthym_moc.NodeInput()
    pmp1.id = "PMP1"
    pmp1.type = "Pump"
    pmp1.design_head = 80.0
    pmp1.design_flow = 1500.0
    pmp1.current_speed = 100.0
    pmp1.inertia_wr2 = 50.0
    pmp1.speed_rpm = 1750.0
    pmp1.has_power = True
    pmp1.head = 93.0

    # Air Valve (unsupported node falling back to legacy clamp, but adjacent to cavitating junction)
    av1 = rthym_moc.NodeInput()
    av1.id = "AV1"
    av1.type = "AirValve"
    av1.elevation = 0.0
    av1.diameter = 2.0
    av1.air_release_diameter = 0.25
    av1.gas_volume = 0.05
    av1.tank_volume = 2.0
    av1.loss_coeff_in = 0.8
    av1.loss_coeff_out = 0.7
    av1.head = 94.0

    # Standpipe (unsupported node falling back to legacy clamp)
    sp1 = rthym_moc.NodeInput()
    sp1.id = "SP1"
    sp1.type = "Standpipe"
    sp1.tank_area = 10.0
    sp1.head = 96.0

    # Add Nodes
    for node in [r1, r2, j1, j2, v1, cv1, pmp1, av1, sp1]:
        solver.add_node(node)

    # Pipes
    pipes = [
        ("P1", "R1", "PMP1", 50.0),
        ("P2", "PMP1", "J1", 40.0),
        ("P3", "J1", "CV1", 30.0),
        ("P4", "CV1", "SP1", 35.0),
        ("P5", "SP1", "AV1", 25.0),
        ("P6", "AV1", "V1", 45.0),
        ("P7", "V1", "J2", 20.0),
        ("P8", "J2", "R2", 60.0),
    ]

    for pid, from_n, to_n, length in pipes:
        p = rthym_moc.PipeInput()
        p.id = pid
        p.from_node = from_n
        p.to_node = to_n
        p.length = length
        p.diameter = 8.0
        p.roughness = 120.0
        solver.add_pipe(p)

    return solver


def test_dvcm_dt_sensitivity_sweep() -> None:
    """Stress test the solver under a wide range of timesteps (dt) to ensure numerical stability."""
    dts = [0.0001, 0.001, 0.01, 0.05, 0.1, 0.2, 0.5]
    for dt in dts:
        solver = _build_junction_solver()
        solver.set_head_schedule("R1", [(0.0, 100.0), (0.05, 160.0)])
        solver.set_head_schedule("R2", [(0.0, 100.0), (0.05, 160.0)])

        results = solver.run(
            total_time=0.5,
            dt=dt,
            p_vapor_psi=50.0,
            cavitation_model=rthym_moc.CavitationModel.DVCM,
        )

        head = np.asarray(results["node_head"]["J1"], dtype=float)
        volume = np.asarray(results["node_cavity_volume"]["J1"], dtype=float)

        # Assert no NaNs or Infs
        assert np.isfinite(head).all(), f"NaN or Inf found in head for dt={dt}"
        assert np.isfinite(volume).all(), f"NaN or Inf found in cavity volume for dt={dt}"

        # Assert cavity volume is always non-negative
        assert (volume >= -1e-12).all(), f"Negative cavity volume detected for dt={dt}"


def test_dvcm_pipe_length_extremes() -> None:
    """Stress test the solver under extremely short and extremely long pipes to verify numerical stability."""
    lengths = [0.1, 1.0, 5.0, 100.0, 1000.0, 10000.0, 50000.0]
    for length in lengths:
        solver = _build_junction_solver(pipe_length=length)
        solver.set_head_schedule("R1", [(0.0, 100.0), (0.05, 160.0)])
        solver.set_head_schedule("R2", [(0.0, 100.0), (0.05, 160.0)])

        results = solver.run(
            total_time=0.5,
            dt=0.01,
            p_vapor_psi=50.0,
            cavitation_model=rthym_moc.CavitationModel.DVCM,
        )

        head = np.asarray(results["node_head"]["J1"], dtype=float)
        volume = np.asarray(results["node_cavity_volume"]["J1"], dtype=float)

        # Assert no NaNs or Infs
        assert np.isfinite(head).all(), f"NaN or Inf found in head for pipe length={length}"
        assert np.isfinite(volume).all(), f"NaN or Inf found in cavity volume for pipe length={length}"

        # Assert cavity volume is always non-negative
        assert (volume >= -1e-12).all(), f"Negative cavity volume detected for pipe length={length}"


def test_dvcm_stiff_network_multi_device() -> None:
    """Stress test a complex, multi-device network under severe transient cavitation events."""
    dts = [0.001, 0.005, 0.01, 0.02, 0.05]
    for dt in dts:
        solver = _build_multi_device_solver()
        # Severe transient: pump trips, valve closes rapidly
        solver.set_pump_power("PMP1", False)
        solver.set_valve_schedule("V1", [(0.0, 100.0), (0.02, 100.0), (0.12, 0.0)])

        results = solver.run(
            total_time=0.5,
            dt=dt,
            p_vapor_psi=50.0,
            cavitation_model=rthym_moc.CavitationModel.DVCM,
        )

        # Verify key nodes are stable and finite
        for node_id in ("J1", "PMP1", "V1", "CV1", "SP1", "AV1"):
            head = np.asarray(results["node_head"][node_id], dtype=float)
            volume = np.asarray(results["node_cavity_volume"][node_id], dtype=float)

            assert np.isfinite(head).all(), f"NaN/Inf found in node {node_id} head for dt={dt}"
            assert np.isfinite(volume).all(), f"NaN/Inf found in node {node_id} cavity volume for dt={dt}"
            assert (volume >= -1e-12).all(), f"Negative cavity volume detected in node {node_id} for dt={dt}"
