# Copyright (c) 2026 Jason Lillywhite <jason@lillywhitewater.com>
# SPDX-License-Identifier: MIT
"""SI convenience helpers for the US-customary solver API.

The C++ solver stores and reports the historical RTHYM-MOC units at the public
boundary: ft, psi, GPM, inches, and ft/s.  This module keeps that stable API but
lets SI users build inputs and post-process results without hand-written
conversion code.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from ._rthym_moc import ControlRuleInput, ControlType, MOCSolver, NodeInput, PipeInput

TimeSeriesSchedule = Sequence[tuple[float, float]]

FT_TO_M = 0.3048
M_TO_FT = 1.0 / FT_TO_M
IN_TO_MM = 25.4
MM_TO_IN = 1.0 / IN_TO_MM
GPM_TO_M3S = 0.003785411784 / 60.0
M3S_TO_GPM = 1.0 / GPM_TO_M3S
PSI_TO_KPA = 6.894757293168361
KPA_TO_PSI = 1.0 / PSI_TO_KPA
PA_TO_PSI = 1.0 / 6894.757293168361
FT2_TO_M2 = FT_TO_M**2
M2_TO_FT2 = M_TO_FT**2
FT3_TO_M3 = FT_TO_M**3
M3_TO_FT3 = M_TO_FT**3
FTS_TO_MS = FT_TO_M
MS_TO_FTS = M_TO_FT


def length_m_to_ft(value_m: float) -> float:
    return float(value_m) * M_TO_FT


def length_ft_to_m(value_ft: float) -> float:
    return float(value_ft) * FT_TO_M


def diameter_mm_to_in(value_mm: float) -> float:
    return float(value_mm) * MM_TO_IN


def diameter_in_to_mm(value_in: float) -> float:
    return float(value_in) * IN_TO_MM


def flow_m3s_to_gpm(value_m3s: float) -> float:
    return float(value_m3s) * M3S_TO_GPM


def flow_gpm_to_m3s(value_gpm: float) -> float:
    return float(value_gpm) * GPM_TO_M3S


def pressure_kpa_to_psi(value_kpa: float) -> float:
    return float(value_kpa) * KPA_TO_PSI


def pressure_psi_to_kpa(value_psi: float) -> float:
    return float(value_psi) * PSI_TO_KPA


DEFAULT_P_VAPOR_KPA = pressure_psi_to_kpa(-14.0)


def velocity_ms_to_fts(value_m_s: float) -> float:
    return float(value_m_s) * MS_TO_FTS


def velocity_fts_to_ms(value_ft_s: float) -> float:
    return float(value_ft_s) * FTS_TO_MS


def area_m2_to_ft2(value_m2: float) -> float:
    return float(value_m2) * M2_TO_FT2


def area_ft2_to_m2(value_ft2: float) -> float:
    return float(value_ft2) * FT2_TO_M2


def volume_m3_to_ft3(value_m3: float) -> float:
    return float(value_m3) * M3_TO_FT3


def volume_ft3_to_m3(value_ft3: float) -> float:
    return float(value_ft3) * FT3_TO_M3


def node_si(
    id: str,
    type: str,
    *,
    elevation_m: float | None = None,
    head_m: float | None = None,
    level: float | None = None,
    max_level_m: float | None = None,
    demand_m3s: float | None = None,
    current_speed: float | None = None,
    has_power: bool | None = None,
    current_setting: float | None = None,
    design_head_m: float | None = None,
    design_flow_m3s: float | None = None,
    diameter_mm: float | None = None,
    air_release_head_m: float | None = None,
    air_release_diameter_mm: float | None = None,
    design_velocity_m_s: float | None = None,
    tank_area_m2: float | None = None,
    gas_volume_m3: float | None = None,
    tank_volume_m3: float | None = None,
    polytropic_n: float | None = None,
    loss_coeff_in: float | None = None,
    loss_coeff_out: float | None = None,
    closure_time: float | None = None,
    closure_damping: float | None = None,
    flipped: bool | None = None,
    inertia_wr2_kg_m2: float | None = None,
    speed_rpm: float | None = None,
    efficiency: float | None = None,
) -> NodeInput:
    """Create a :class:`NodeInput` from SI-unit keyword arguments.

    Dimensionless fields such as valve settings, pump speed, tank level, loss
    coefficients, and polytropic exponent use the same values as the core API.
    """

    node = NodeInput()
    node.id = id
    node.type = type

    if elevation_m is not None:
        node.elevation = length_m_to_ft(elevation_m)
    if head_m is not None:
        node.head = length_m_to_ft(head_m)
    if level is not None:
        node.level = float(level)
    if max_level_m is not None:
        node.max_level = length_m_to_ft(max_level_m)
    if demand_m3s is not None:
        node.demand = flow_m3s_to_gpm(demand_m3s)
    if current_speed is not None:
        node.current_speed = float(current_speed)
    if has_power is not None:
        node.has_power = bool(has_power)
    if current_setting is not None:
        node.current_setting = float(current_setting)
    if design_head_m is not None:
        node.design_head = length_m_to_ft(design_head_m)
    if design_flow_m3s is not None:
        node.design_flow = flow_m3s_to_gpm(design_flow_m3s)
    if diameter_mm is not None:
        node.diameter = diameter_mm_to_in(diameter_mm)
    if air_release_head_m is not None:
        node.air_release_head = length_m_to_ft(air_release_head_m)
    if air_release_diameter_mm is not None:
        node.air_release_diameter = diameter_mm_to_in(air_release_diameter_mm)
    if design_velocity_m_s is not None:
        node.design_velocity = velocity_ms_to_fts(design_velocity_m_s)
    if tank_area_m2 is not None:
        node.tank_area = area_m2_to_ft2(tank_area_m2)
    if gas_volume_m3 is not None:
        node.gas_volume = volume_m3_to_ft3(gas_volume_m3)
    if tank_volume_m3 is not None:
        node.tank_volume = volume_m3_to_ft3(tank_volume_m3)
    if polytropic_n is not None:
        node.polytropic_n = float(polytropic_n)
    if loss_coeff_in is not None:
        node.loss_coeff_in = float(loss_coeff_in)
    if loss_coeff_out is not None:
        node.loss_coeff_out = float(loss_coeff_out)
    if closure_time is not None:
        node.closure_time = float(closure_time)
    if closure_damping is not None:
        node.closure_damping = float(closure_damping)
    if flipped is not None:
        node.flipped = bool(flipped)
    if inertia_wr2_kg_m2 is not None:
        node.inertia_wr2 = float(inertia_wr2_kg_m2) * 23.73036
    if speed_rpm is not None:
        node.speed_rpm = float(speed_rpm)
    if efficiency is not None:
        node.efficiency = float(efficiency)

    return node


def pipe_si(
    id: str,
    from_node: str,
    to_node: str,
    *,
    length_m: float,
    diameter_mm: float,
    roughness: float,
    flow_m3s: float = 0.0,
    minor_loss: float | None = None,
    wall_thickness_mm: float | None = None,
    youngs_modulus_pa: float | None = None,
    poissons_ratio: float | None = None,
) -> PipeInput:
    """Create a :class:`PipeInput` from SI-unit keyword arguments."""

    pipe = PipeInput()
    pipe.id = id
    pipe.from_node = from_node
    pipe.to_node = to_node
    pipe.length = length_m_to_ft(length_m)
    pipe.diameter = diameter_mm_to_in(diameter_mm)
    pipe.roughness = float(roughness)
    pipe.flow_gpm = flow_m3s_to_gpm(flow_m3s)

    if minor_loss is not None:
        pipe.minor_loss = float(minor_loss)
    if wall_thickness_mm is not None:
        pipe.wall_thickness = diameter_mm_to_in(wall_thickness_mm)
    if youngs_modulus_pa is not None:
        pipe.youngs_modulus = float(youngs_modulus_pa) * PA_TO_PSI
    if poissons_ratio is not None:
        pipe.poissons_ratio = float(poissons_ratio)

    return pipe


def _convert_series_dict(series: Mapping[str, Any], factor: float) -> dict[str, np.ndarray]:
    return {str(key): np.asarray(value, dtype=float) * factor for key, value in series.items()}


def _apply_si_threshold(rule: ControlRuleInput, monitored_quantity: str, value: float) -> None:
    if monitored_quantity == "pressure":
        rule.threshold = pressure_kpa_to_psi(value)
    elif monitored_quantity == "head":
        rule.threshold = length_m_to_ft(value)
    elif monitored_quantity == "flow":
        rule.threshold = flow_m3s_to_gpm(value)
    elif monitored_quantity == "level":
        rule.threshold = float(value)
    else:
        raise ValueError(f"unsupported monitored_quantity for SI threshold: {monitored_quantity!r}")


def _apply_si_deadband(rule: ControlRuleInput, monitored_quantity: str, value: float) -> None:
    if monitored_quantity == "level":
        rule.deadband = float(value)
    elif monitored_quantity == "pressure":
        rule.deadband = pressure_kpa_to_psi(value)
    elif monitored_quantity == "head":
        rule.deadband = length_m_to_ft(value)
    elif monitored_quantity == "flow":
        rule.deadband = flow_m3s_to_gpm(value)
    else:
        raise ValueError(f"unsupported monitored_quantity for SI deadband: {monitored_quantity!r}")


def _apply_si_setpoint(rule: ControlRuleInput, monitored_quantity: str, value: float) -> None:
    if monitored_quantity == "pressure":
        rule.target = pressure_kpa_to_psi(value)
    elif monitored_quantity == "head":
        rule.target = length_m_to_ft(value)
    elif monitored_quantity == "flow":
        rule.target = flow_m3s_to_gpm(value)
    elif monitored_quantity == "level":
        rule.target = float(value)
    else:
        raise ValueError(f"unsupported monitored_quantity for SI setpoint: {monitored_quantity!r}")


def control_rule_si(
    id: str,
    rule_type: ControlType,
    *,
    monitored_node: str = "",
    controlled_node: str = "",
    monitored_quantity: str = "pressure",
    monitored_pipe: str = "",
    condition: str = "lt",
    threshold_kpa: float | None = None,
    threshold_m: float | None = None,
    threshold_m3s: float | None = None,
    threshold_pct: float | None = None,
    threshold_s: float | None = None,
    target_pct: float | None = None,
    setpoint_kpa: float | None = None,
    setpoint_m: float | None = None,
    setpoint_m3s: float | None = None,
    setpoint_pct: float | None = None,
    deadband_kpa: float | None = None,
    deadband_m: float | None = None,
    deadband_m3s: float | None = None,
    deadband_pct: float | None = None,
    deadband_s: float | None = None,
    action: str = "fill",
    kp: float | None = None,
    ki: float | None = None,
    kd: float | None = None,
) -> ControlRuleInput:
    """Create a :class:`ControlRuleInput` from SI-unit keyword arguments.

    Use the threshold/setpoint/deadband keyword that matches ``monitored_quantity``:

    - ``pressure`` → ``*_kpa``
    - ``head`` → ``*_m``
    - ``flow`` → ``*_m3s`` (also set ``monitored_pipe``)
    - ``level`` → ``*_pct``

    For :class:`ControlType.Threshold`, ``target_pct`` is the controlled pump speed
    or valve opening (0–100).  For :class:`ControlType.PID`, use ``setpoint_*`` for
    the feedback setpoint.  For :class:`ControlType.PCV`, ``threshold_s`` and
    ``deadband_s`` are valve ramp times in seconds.  PID gains are passed through
    unchanged; retune them when switching from US-customary rules.
    """

    rule = ControlRuleInput()
    rule.id = id
    rule.type = rule_type
    rule.monitored_node = monitored_node
    rule.controlled_node = controlled_node
    rule.monitored_quantity = monitored_quantity
    rule.monitored_pipe = monitored_pipe
    rule.condition = condition
    rule.action = action

    if rule_type == ControlType.PCV:
        if threshold_s is not None:
            rule.threshold = float(threshold_s)
        if deadband_s is not None:
            rule.deadband = float(deadband_s)
    else:
        threshold_si = {
            "pressure": threshold_kpa,
            "head": threshold_m,
            "flow": threshold_m3s,
            "level": threshold_pct,
        }.get(monitored_quantity)
        if threshold_si is not None:
            _apply_si_threshold(rule, monitored_quantity, threshold_si)

        deadband_si = {
            "pressure": deadband_kpa,
            "head": deadband_m,
            "flow": deadband_m3s,
            "level": deadband_pct,
        }.get(monitored_quantity)
        if deadband_si is not None:
            _apply_si_deadband(rule, monitored_quantity, deadband_si)

        if target_pct is not None:
            rule.target = float(target_pct)

        setpoint_si = {
            "pressure": setpoint_kpa,
            "head": setpoint_m,
            "flow": setpoint_m3s,
            "level": setpoint_pct,
        }.get(monitored_quantity)
        if setpoint_si is not None:
            _apply_si_setpoint(rule, monitored_quantity, setpoint_si)

    if kp is not None:
        rule.kp = float(kp)
    if ki is not None:
        rule.ki = float(ki)
    if kd is not None:
        rule.kd = float(kd)

    return rule


def convert_head_schedule_si(schedule: TimeSeriesSchedule) -> list[tuple[float, float]]:
    """Convert ``(time_s, head_m)`` breakpoints to ``(time_s, head_ft)``."""

    return [(float(time_s), length_m_to_ft(head_m)) for time_s, head_m in schedule]


def convert_demand_schedule_si(schedule: TimeSeriesSchedule) -> list[tuple[float, float]]:
    """Convert ``(time_s, demand_m3s)`` breakpoints to ``(time_s, demand_gpm)``."""

    return [(float(time_s), flow_m3s_to_gpm(demand_m3s)) for time_s, demand_m3s in schedule]


def set_head_schedule_si(
    solver: MOCSolver,
    node_id: str,
    schedule: TimeSeriesSchedule,
) -> None:
    """Register a time-varying head schedule using ``(time_s, head_m)`` pairs."""

    solver.set_head_schedule(node_id, convert_head_schedule_si(schedule))


def set_demand_schedule_si(
    solver: MOCSolver,
    node_id: str,
    schedule: TimeSeriesSchedule,
) -> None:
    """Register a time-varying demand schedule using ``(time_s, demand_m3s)`` pairs."""

    solver.set_demand_schedule(node_id, convert_demand_schedule_si(schedule))


def set_node_head_si(solver: MOCSolver, node_id: str, head_m: float) -> None:
    """Update a fixed-head boundary node's stored head in metres."""

    solver.set_node_head(node_id, length_m_to_ft(head_m))


def set_node_demand_si(solver: MOCSolver, node_id: str, demand_m3s: float) -> None:
    """Update a junction demand in m³/s."""

    solver.set_node_demand(node_id, flow_m3s_to_gpm(demand_m3s))


def get_node_head_si(solver: MOCSolver, node_id: str) -> float:
    """Return the current piezometric head at *node_id* in metres."""

    return length_ft_to_m(solver.get_node_head(node_id))


def get_node_pressure_si(solver: MOCSolver, node_id: str) -> float:
    """Return the current gauge pressure at *node_id* in kPa."""

    return pressure_psi_to_kpa(solver.get_node_pressure(node_id))


def run_si(
    solver: MOCSolver,
    total_time: float,
    dt: float = 0.01,
    *,
    p_vapor_kpa: float = DEFAULT_P_VAPOR_KPA,
    usf_tau: float = 0.5,
    k_bru: float = -1.0,
) -> dict[str, Any]:
    """Run a transient and return an SI-unit results dictionary."""

    results = solver.run(
        total_time,
        dt,
        pressure_kpa_to_psi(p_vapor_kpa),
        usf_tau,
        k_bru,
    )
    return results_to_si(results)


def results_to_si(results: Mapping[str, Any]) -> dict[str, Any]:
    """Return an SI-unit view of a ``MOCSolver.run()`` results dictionary.

    The returned dictionary uses explicit SI keys and leaves time, cavitation
    flags, and valve settings unchanged:

    - ``node_head_m``
    - ``node_pressure_kpa``
    - ``pipe_flow_m3s``
    - ``valve_velocity_m_s``
    """

    out: dict[str, Any] = {"time": np.asarray(results.get("time", []), dtype=float)}

    if "node_head" in results:
        out["node_head_m"] = _convert_series_dict(results["node_head"], FT_TO_M)
    if "node_pressure" in results:
        out["node_pressure_kpa"] = _convert_series_dict(results["node_pressure"], PSI_TO_KPA)
    if "pipe_flow_gpm" in results:
        out["pipe_flow_m3s"] = _convert_series_dict(results["pipe_flow_gpm"], GPM_TO_M3S)
    if "valve_velocity" in results:
        out["valve_velocity_m_s"] = _convert_series_dict(results["valve_velocity"], FTS_TO_MS)
    if "node_cavitation" in results:
        out["node_cavitation"] = {
            str(key): np.asarray(value, dtype=int) for key, value in results["node_cavitation"].items()
        }
    if "valve_position" in results:
        out["valve_position"] = {
            str(key): np.asarray(value, dtype=float) for key, value in results["valve_position"].items()
        }
    if "valve_setting" in results:
        out["valve_setting"] = {
            str(key): np.asarray(value, dtype=float) for key, value in results["valve_setting"].items()
        }
    if "pump_speed" in results:
        out["pump_speed"] = {
            str(key): np.asarray(value, dtype=float) for key, value in results["pump_speed"].items()
        }

    return out
