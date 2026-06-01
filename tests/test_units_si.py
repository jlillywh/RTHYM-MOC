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
        ramp_time_s=10.0,
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
    assert node.ramp_time == pytest.approx(10.0)


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


def test_control_rule_si_threshold_pressure():
    rule = m.control_rule_si(
        "rule1",
        m.ControlType.Threshold,
        monitored_node="J1",
        controlled_node="V1",
        monitored_quantity="pressure",
        condition="gt",
        threshold_kpa=m.pressure_psi_to_kpa(45.0),
        target_pct=0.0,
    )

    assert rule.threshold == pytest.approx(45.0)
    assert rule.target == pytest.approx(0.0)


def test_control_rule_si_deadband_level():
    rule = m.control_rule_si(
        "db_fill",
        m.ControlType.Deadband,
        monitored_node="T1",
        controlled_node="Pmp1",
        monitored_quantity="level",
        threshold_pct=40.0,
        deadband_pct=20.0,
        action="fill",
    )

    assert rule.threshold == pytest.approx(40.0)
    assert rule.deadband == pytest.approx(20.0)


def test_control_rule_si_pid_pressure_setpoint():
    rule = m.control_rule_si(
        "pressure_reg",
        m.ControlType.PID,
        monitored_node="J2",
        controlled_node="Pmp2",
        monitored_quantity="pressure",
        setpoint_kpa=m.pressure_psi_to_kpa(30.0),
        kp=2.0,
        ki=1.0,
        kd=0.1,
    )

    assert rule.target == pytest.approx(30.0)
    assert rule.kp == pytest.approx(2.0)


def test_control_rule_si_pcv_uses_seconds():
    rule = m.control_rule_si(
        "pump_valve_seq",
        m.ControlType.PCV,
        monitored_node="Pmp1",
        controlled_node="V1",
        threshold_s=10.0,
        deadband_s=15.0,
    )

    assert rule.threshold == pytest.approx(10.0)
    assert rule.deadband == pytest.approx(15.0)


def test_control_rule_si_threshold_head_and_flow():
    head_rule = m.control_rule_si(
        "head_rule",
        m.ControlType.Threshold,
        monitored_node="J1",
        controlled_node="V1",
        monitored_quantity="head",
        threshold_m=15.24,
        target_pct=0.0,
    )
    assert head_rule.threshold == pytest.approx(50.0)

    flow_rule = m.control_rule_si(
        "flow_rule",
        m.ControlType.Threshold,
        monitored_node="J1",
        controlled_node="V1",
        monitored_quantity="flow",
        monitored_pipe="P1",
        threshold_m3s=m.flow_gpm_to_m3s(100.0),
        target_pct=50.0,
    )
    assert flow_rule.threshold == pytest.approx(100.0)
    assert flow_rule.target == pytest.approx(50.0)


def test_control_rule_si_deadband_and_setpoint_si_quantities():
    deadband_rule = m.control_rule_si(
        "db_pressure",
        m.ControlType.Deadband,
        monitored_node="J1",
        controlled_node="Pmp1",
        monitored_quantity="pressure",
        threshold_kpa=m.pressure_psi_to_kpa(40.0),
        deadband_kpa=m.pressure_psi_to_kpa(5.0),
        action="fill",
    )
    assert deadband_rule.threshold == pytest.approx(40.0)
    assert deadband_rule.deadband == pytest.approx(5.0)

    head_deadband = m.control_rule_si(
        "db_head",
        m.ControlType.Deadband,
        monitored_node="T1",
        controlled_node="Pmp1",
        monitored_quantity="head",
        threshold_m=30.48,
        deadband_m=1.524,
        action="fill",
    )
    assert head_deadband.deadband == pytest.approx(5.0)

    flow_deadband = m.control_rule_si(
        "db_flow",
        m.ControlType.Deadband,
        monitored_node="J1",
        controlled_node="Pmp1",
        monitored_quantity="flow",
        monitored_pipe="P1",
        threshold_m3s=m.flow_gpm_to_m3s(100.0),
        deadband_m3s=m.flow_gpm_to_m3s(10.0),
        action="fill",
    )
    assert flow_deadband.deadband == pytest.approx(10.0)

    pid_rule = m.control_rule_si(
        "pid_head",
        m.ControlType.PID,
        monitored_node="J1",
        controlled_node="Pmp1",
        monitored_quantity="head",
        setpoint_m=30.48,
        kp=1.0,
    )
    assert pid_rule.target == pytest.approx(100.0)

    pid_flow = m.control_rule_si(
        "pid_flow",
        m.ControlType.PID,
        monitored_node="J1",
        controlled_node="Pmp1",
        monitored_quantity="flow",
        monitored_pipe="P1",
        setpoint_m3s=m.flow_gpm_to_m3s(200.0),
        kp=1.0,
    )
    assert pid_flow.target == pytest.approx(200.0)

    pid_level = m.control_rule_si(
        "pid_level",
        m.ControlType.PID,
        monitored_node="T1",
        controlled_node="Pmp1",
        monitored_quantity="level",
        setpoint_pct=75.0,
        kp=1.0,
    )
    assert pid_level.target == pytest.approx(75.0)


def test_apply_si_helpers_reject_unsupported_quantity():
    from rthym_moc.units import ControlRuleInput, _apply_si_deadband, _apply_si_setpoint, _apply_si_threshold

    rule = ControlRuleInput()
    with pytest.raises(ValueError, match="unsupported monitored_quantity for SI threshold"):
        _apply_si_threshold(rule, "temperature", 1.0)
    with pytest.raises(ValueError, match="unsupported monitored_quantity for SI deadband"):
        _apply_si_deadband(rule, "temperature", 1.0)
    with pytest.raises(ValueError, match="unsupported monitored_quantity for SI setpoint"):
        _apply_si_setpoint(rule, "temperature", 1.0)


def test_control_rule_si_threshold_pressure_triggers_like_us_rule():
    """SI threshold rule should behave like an equivalent US-customary rule."""

    def _run_with_rule(rule):
        solver = m.MOCSolver()
        solver.add_node(m.node_si("R1", "PressureBoundary", head_m=30.48))
        solver.add_node(m.node_si("J1", "Junction", elevation_m=0.0, head_m=30.48))
        solver.add_node(m.node_si("V1", "Valve", diameter_mm=304.8, current_setting=100.0))
        solver.add_node(m.node_si("R2", "PressureBoundary", head_m=15.24))
        for pipe_id, frm, to in [("P1", "R1", "J1"), ("P2", "J1", "V1"), ("P3", "V1", "R2")]:
            solver.add_pipe(
                m.pipe_si(
                    pipe_id,
                    frm,
                    to,
                    length_m=30.48,
                    diameter_mm=304.8,
                    roughness=130.0,
                    flow_m3s=m.flow_gpm_to_m3s(100.0),
                )
            )
        solver.add_control_rule(rule)
        m.set_head_schedule_si(solver, "R1", [(0.0, 30.48), (0.2, 30.48), (0.4, 45.72)])
        return solver.run(total_time=5.0, dt=0.01)

    us_rule = m.ControlRuleInput()
    us_rule.id = "rule1"
    us_rule.type = m.ControlType.Threshold
    us_rule.monitored_node = "J1"
    us_rule.controlled_node = "V1"
    us_rule.monitored_quantity = "pressure"
    us_rule.condition = "gt"
    us_rule.threshold = 45.0
    us_rule.target = 0.0

    si_rule = m.control_rule_si(
        "rule1",
        m.ControlType.Threshold,
        monitored_node="J1",
        controlled_node="V1",
        monitored_quantity="pressure",
        condition="gt",
        threshold_kpa=m.pressure_psi_to_kpa(45.0),
        target_pct=0.0,
    )

    assert abs(_run_with_rule(us_rule)["pipe_flow_gpm"]["P1"][-1]) < 1.0
    assert abs(_run_with_rule(si_rule)["pipe_flow_gpm"]["P1"][-1]) < 1.0


def test_convert_head_schedule_si():
    converted = m.convert_head_schedule_si([(0.0, 30.48), (1.0, 45.72)])
    assert converted[0] == (0.0, pytest.approx(100.0))
    assert converted[1] == (1.0, pytest.approx(150.0))


def test_convert_demand_schedule_si():
    demand_m3s = m.flow_gpm_to_m3s(100.0)
    converted = m.convert_demand_schedule_si([(0.0, 0.0), (2.0, demand_m3s)])
    assert converted[0] == (0.0, pytest.approx(0.0))
    assert converted[1][0] == pytest.approx(2.0)
    assert converted[1][1] == pytest.approx(100.0)


class _RecordingSolver:
    def __init__(self) -> None:
        self.head_schedule: tuple[str, list[tuple[float, float]]] | None = None
        self.demand_schedule: tuple[str, list[tuple[float, float]]] | None = None
        self.head_ft: tuple[str, float] | None = None
        self.demand_gpm: tuple[str, float] | None = None

    def set_head_schedule(self, node_id: str, schedule: list[tuple[float, float]]) -> None:
        self.head_schedule = (node_id, schedule)

    def set_demand_schedule(self, node_id: str, schedule: list[tuple[float, float]]) -> None:
        self.demand_schedule = (node_id, schedule)

    def set_node_head(self, node_id: str, head_ft: float) -> None:
        self.head_ft = (node_id, head_ft)

    def set_node_demand(self, node_id: str, demand_gpm: float) -> None:
        self.demand_gpm = (node_id, demand_gpm)


def test_set_head_schedule_si_forwards_converted_schedule():
    solver = _RecordingSolver()
    m.set_head_schedule_si(solver, "R1", [(0.0, 30.48), (0.4, 45.72)])
    assert solver.head_schedule is not None
    node_id, schedule = solver.head_schedule
    assert node_id == "R1"
    assert schedule[0] == (0.0, pytest.approx(100.0))
    assert schedule[1] == (0.4, pytest.approx(150.0))


def test_set_demand_schedule_si_forwards_converted_schedule():
    solver = _RecordingSolver()
    demand_m3s = m.flow_gpm_to_m3s(250.0)
    m.set_demand_schedule_si(solver, "J1", [(0.0, 0.0), (1.0, demand_m3s)])
    assert solver.demand_schedule is not None
    node_id, schedule = solver.demand_schedule
    assert node_id == "J1"
    assert schedule[1][1] == pytest.approx(250.0)


def test_set_node_head_and_demand_si():
    solver = _RecordingSolver()
    m.set_node_head_si(solver, "R1", 30.48)
    m.set_node_demand_si(solver, "J1", m.flow_gpm_to_m3s(150.0))
    assert solver.head_ft == ("R1", pytest.approx(100.0))
    assert solver.demand_gpm == ("J1", pytest.approx(150.0))


def test_head_schedule_si_matches_us_schedule_in_run():
    def _run_head_schedule(set_schedule):
        solver = m.MOCSolver()
        solver.add_node(m.node_si("R1", "PressureBoundary", head_m=30.48))
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
        set_schedule(solver)
        return solver.run(total_time=0.4, dt=0.01)

    us = _run_head_schedule(
        lambda solver: solver.set_head_schedule("R1", [(0.0, 100.0), (0.2, 120.0), (0.4, 80.0)])
    )
    si = _run_head_schedule(
        lambda solver: m.set_head_schedule_si(
            solver,
            "R1",
            [(0.0, 30.48), (0.2, 36.576), (0.4, 24.384)],
        )
    )

    np.testing.assert_allclose(us["node_head"]["J1"], si["node_head"]["J1"], rtol=0.0, atol=1e-9)


class _RunRecordingSolver:
    def __init__(self) -> None:
        self.run_args: tuple[float, float, float, float, float] | None = None

    def run(self, total_time: float, dt: float, p_vapor_psi: float, usf_tau: float, k_bru: float):
        self.run_args = (total_time, dt, p_vapor_psi, usf_tau, k_bru)
        return {
            "time": np.array([0.0, 0.01]),
            "node_head": {"J1": np.array([100.0, 100.0])},
            "node_pressure": {"J1": np.array([43.0, 43.0])},
            "pipe_flow_gpm": {"P1": np.array([200.0, 200.0])},
        }


def test_run_si_converts_p_vapor_and_returns_si_keys():
    solver = _RunRecordingSolver()
    results = m.run_si(solver, 1.0, dt=0.02, p_vapor_kpa=-50.0)

    assert solver.run_args is not None
    assert solver.run_args[2] == pytest.approx(m.pressure_kpa_to_psi(-50.0))
    assert "node_head_m" in results
    assert "node_pressure_kpa" in results
    assert "pipe_flow_m3s" in results
    assert results["node_head_m"]["J1"][0] == pytest.approx(100.0 * m.FT_TO_M)


def test_run_si_default_p_vapor_matches_us_run_default():
    solver = _RunRecordingSolver()
    m.run_si(solver, 0.1)
    assert solver.run_args is not None
    assert solver.run_args[2] == pytest.approx(-14.0)


class _QueryRecordingSolver:
    def get_node_head(self, node_id: str) -> float:
        assert node_id == "J1"
        return 100.0

    def get_node_pressure(self, node_id: str) -> float:
        assert node_id == "J1"
        return 43.0


def test_get_node_head_and_pressure_si():
    solver = _QueryRecordingSolver()
    assert m.get_node_head_si(solver, "J1") == pytest.approx(30.48)
    assert m.get_node_pressure_si(solver, "J1") == pytest.approx(m.pressure_psi_to_kpa(43.0))


def test_run_si_integration_matches_run_plus_results_to_si():
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

    direct = m.results_to_si(solver.run(total_time=0.2, dt=0.01))
    wrapped = m.run_si(solver, total_time=0.2, dt=0.01)

    np.testing.assert_allclose(wrapped["time"], direct["time"])
    np.testing.assert_allclose(wrapped["node_head_m"]["J1"], direct["node_head_m"]["J1"])
    np.testing.assert_allclose(wrapped["pipe_flow_m3s"]["P1"], direct["pipe_flow_m3s"]["P1"])
