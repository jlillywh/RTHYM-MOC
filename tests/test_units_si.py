"""Tests for SI unit conversion helpers."""

from __future__ import annotations

import numpy as np
import pytest

import rthym_moc as m


def test_scalar_si_conversions_round_trip():
    assert m.length_ft_to_m(m.length_m_to_ft(12.34)) == pytest.approx(12.34)
    assert m.diameter_in_to_mm(m.diameter_mm_to_in(304.8)) == pytest.approx(304.8)
    assert m.flow_gpm_to_m3s(m.flow_m3s_to_gpm(0.0315450982)) == pytest.approx(0.0315450982)
    assert m.pressure_psi_to_kpa(m.pressure_kpa_to_psi(250.0)) == pytest.approx(250.0)
    assert m.velocity_fts_to_ms(m.velocity_ms_to_fts(1.5)) == pytest.approx(1.5)
    assert m.area_ft2_to_m2(m.area_m2_to_ft2(2.0)) == pytest.approx(2.0)
    assert m.volume_ft3_to_m3(m.volume_m3_to_ft3(3.0)) == pytest.approx(3.0)


def test_node_si_sets_underlying_us_customary_fields():
    node = m.node_si(
        "V1",
        "Valve",
        elevation_m=3.048,
        head_m=30.48,
        demand_m3s=0.01,
        diameter_mm=304.8,
        current_setting=75.0,
        tank_area_m2=2.0,
        gas_volume_m3=1.0,
        closure_damping=0.2,
    )

    assert node.id == "V1"
    assert node.type == "Valve"
    assert node.elevation == pytest.approx(10.0)
    assert node.head == pytest.approx(100.0)
    assert node.demand == pytest.approx(m.flow_m3s_to_gpm(0.01))
    assert node.diameter == pytest.approx(12.0)
    assert node.current_setting == pytest.approx(75.0)
    assert node.tank_area == pytest.approx(m.area_m2_to_ft2(2.0))
    assert node.gas_volume == pytest.approx(m.volume_m3_to_ft3(1.0))
    assert node.closure_damping == pytest.approx(0.2)


def test_node_si_sets_all_optional_fields():
    node = m.node_si(
        "HP1",
        "HydropneumaticTank",
        level=80.0,
        max_level_m=6.096,
        current_speed=90.0,
        has_power=False,
        design_head_m=15.24,
        design_flow_m3s=0.02,
        air_release_head_m=1.524,
        air_release_diameter_mm=25.4,
        design_velocity_m_s=1.5,
        tank_volume_m3=3.0,
        polytropic_n=1.25,
        loss_coeff_in=0.8,
        loss_coeff_out=0.6,
        closure_time=0.15,
        flipped=True,
    )

    assert node.level == pytest.approx(80.0)
    assert node.max_level == pytest.approx(20.0)
    assert node.current_speed == pytest.approx(90.0)
    assert node.has_power is False
    assert node.design_head == pytest.approx(50.0)
    assert node.design_flow == pytest.approx(m.flow_m3s_to_gpm(0.02))
    assert node.air_release_head == pytest.approx(5.0)
    assert node.air_release_diameter == pytest.approx(1.0)
    assert node.design_velocity == pytest.approx(m.velocity_ms_to_fts(1.5))
    assert node.tank_volume == pytest.approx(m.volume_m3_to_ft3(3.0))
    assert node.polytropic_n == pytest.approx(1.25)
    assert node.loss_coeff_in == pytest.approx(0.8)
    assert node.loss_coeff_out == pytest.approx(0.6)
    assert node.closure_time == pytest.approx(0.15)
    assert node.flipped is True


def test_pipe_si_sets_underlying_us_customary_fields():
    pipe = m.pipe_si(
        "P1",
        "R1",
        "J1",
        length_m=914.4,
        diameter_mm=304.8,
        roughness=130.0,
        flow_m3s=m.flow_gpm_to_m3s(500.0),
        minor_loss=1.2,
        wall_thickness_mm=6.35,
        youngs_modulus_pa=2.0e11,
        poissons_ratio=0.29,
    )

    assert pipe.id == "P1"
    assert pipe.from_node == "R1"
    assert pipe.to_node == "J1"
    assert pipe.length == pytest.approx(3000.0)
    assert pipe.diameter == pytest.approx(12.0)
    assert pipe.roughness == pytest.approx(130.0)
    assert pipe.flow_gpm == pytest.approx(500.0)
    assert pipe.minor_loss == pytest.approx(1.2)
    assert pipe.wall_thickness == pytest.approx(0.25)
    assert pipe.youngs_modulus == pytest.approx(2.0e11 * m.PA_TO_PSI)
    assert pipe.poissons_ratio == pytest.approx(0.29)


def test_results_to_si_converts_result_series():
    results = {
        "time": np.array([0.0, 0.01]),
        "node_head": {"J1": np.array([100.0, 120.0])},
        "node_pressure": {"J1": np.array([10.0, 12.0])},
        "node_cavitation": {"J1": np.array([0, 1])},
        "pipe_flow_gpm": {"P1": np.array([100.0, -50.0])},
        "valve_velocity": {"V1": np.array([1.0, 2.0])},
        "valve_position": {"V1": np.array([1.0, 0.9])},
        "valve_setting": {"V1": np.array([100.0, 50.0])},
    }

    si = m.results_to_si(results)

    np.testing.assert_allclose(si["time"], results["time"])
    np.testing.assert_allclose(si["node_head_m"]["J1"], np.array([30.48, 36.576]))
    np.testing.assert_allclose(si["node_pressure_kpa"]["J1"], np.array([68.94757293, 82.73708752]))
    np.testing.assert_allclose(si["pipe_flow_m3s"]["P1"], np.array([100.0, -50.0]) * m.GPM_TO_M3S)
    np.testing.assert_allclose(si["valve_velocity_m_s"]["V1"], np.array([0.3048, 0.6096]))
    np.testing.assert_array_equal(si["node_cavitation"]["J1"], np.array([0, 1]))
    np.testing.assert_allclose(si["valve_position"]["V1"], np.array([1.0, 0.9]))
    np.testing.assert_allclose(si["valve_setting"]["V1"], np.array([100.0, 50.0]))


def test_results_to_si_accepts_minimal_results():
    si = m.results_to_si({})

    np.testing.assert_allclose(si["time"], np.array([]))
    assert set(si) == {"time"}


def test_si_helpers_build_and_run_small_model():
    solver = m.MOCSolver()
    solver.add_node(m.node_si("R1", "PressureBoundary", head_m=36.576))
    solver.add_node(m.node_si("J1", "Junction", elevation_m=0.0, head_m=30.48))
    solver.add_node(m.node_si("R2", "PressureBoundary", head_m=24.384))
    solver.add_pipe(
        m.pipe_si(
            "P1",
            "R1",
            "J1",
            length_m=60.96,
            diameter_mm=304.8,
            roughness=130.0,
            flow_m3s=m.flow_gpm_to_m3s(200.0),
        )
    )
    solver.add_pipe(
        m.pipe_si(
            "P2",
            "J1",
            "R2",
            length_m=60.96,
            diameter_mm=304.8,
            roughness=130.0,
            flow_m3s=m.flow_gpm_to_m3s(200.0),
        )
    )

    si = m.results_to_si(solver.run(total_time=0.2, dt=0.01))

    assert "J1" in si["node_head_m"]
    assert len(si["time"]) == 20
    assert np.max(si["node_head_m"]["J1"]) >= np.min(si["node_head_m"]["J1"])
