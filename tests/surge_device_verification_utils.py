"""Surge-device verification helpers (tests + ``surge_device_verification.ipynb``)."""

from __future__ import annotations

import math
import os
import tempfile
from dataclasses import dataclass
from typing import Any

import numpy as np
import rthym_moc as m

# ── Appendix B.8 standpipe (valve closure) ───────────────────────────────────
_GPM_TO_CFS = 0.002228
_G_US = 32.2

H_RES_FT = 150.0
L_FT = 3000.0
D_IN = 12.0
HW_C = 130.0
Q0_GPM = 500.0
A_WAVE_FT = 4000.0
DT_S = 0.01
TOTAL_B8_S = 25.0
A_S_FT2 = 1.0

_D_FT = D_IN / 12.0
_A_PIPE = math.pi * (_D_FT / 2.0) ** 2
_V0_FPS = Q0_GPM * _GPM_TO_CFS / _A_PIPE
_L_SHORT_FT = A_WAVE_FT * DT_S
_HF_P1_FT = 10.44 * L_FT * Q0_GPM**1.852 / (HW_C**1.852 * D_IN**4.871)
H_SP1_SS_FT = H_RES_FT - _HF_P1_FT
H_R2_FT = H_SP1_SS_FT

DH_JOUK_FT = A_WAVE_FT * _V0_FPS / _G_US
SP_H_JOUK_PEAK_FT = H_SP1_SS_FT + DH_JOUK_FT
SP_H_SS_FT = H_SP1_SS_FT

_OMEGA = math.sqrt(_G_US * _A_PIPE / (A_S_FT2 * L_FT))
SP_T_OSC_S = 2.0 * math.pi / _OMEGA
SP_Z_MAX_FT = _V0_FPS * math.sqrt(_A_PIPE * L_FT / (_G_US * A_S_FT2))
SP_H_PEAK_ANALYTICAL_FT = H_SP1_SS_FT + SP_Z_MAX_FT

TOL_JOUK_FT = 5.0
TOL_STANDPIPE_UP_FT = 170.0
TOL_PEAK_ANAL_FT = 15.0
TOL_MITIGATION_PCT = 0.80

# ── TSNet documented reference (Appendix B.8.5; not default CI) ───────────────
TSNET_STANDPIPE_SS_HEAD_FT = 147.95
TSNET_STANDPIPE_PEAK_HEAD_FT = 160.64
TSNET_PEAK_DIFF_FT = 0.14
TSNET_RMS_0_20_FT = 0.10
TSNET_COMPARE_WINDOW_S = 20.0
RTHYM_B85_PEAK_HEAD_FT = 160.78
RTHYM_B85_SS_HEAD_FT = 147.90

# ── Pump trip / air valve windows ───────────────────────────────────────────
TRIP_START_S = 5.2
TRIP_END_S = 6.0
PUMP_TRIP_TOTAL_S = 12.0

AIR_PRE_START_S = 1.0
AIR_PRE_END_S = 4.0
AIR_RESTART_EARLY_START_S = 8.2
AIR_RESTART_EARLY_END_S = 9.0
AIR_RESTART_LATE_START_S = 10.5
AIR_RESTART_LATE_END_S = 11.5

VALVE_CLOSURE_TOTAL_S = 12.0
VALVE_PEAK_LIMIT_FT = {"Standpipe": 170.0, "HydropneumaticTank": 350.0}
PUMP_TRIP_FLOOR_FT = {"Standpipe": 50.0, "HydropneumaticTank": 150.0}

HPT_TRIP_FLOOR_FT = 100.0
HPT_IMPROVEMENT_MIN_FT = 100.0
HPT_TANK_VOLUME_FT3 = 10.0
HPT_PRECHARGE_RATIO = 0.4


def _mean_over_window(time_s, values, start_s: float, end_s: float) -> float:
    mask = (np.asarray(time_s) >= start_s) & (np.asarray(time_s) <= end_s)
    if not np.any(mask):
        raise ValueError(f"No samples in [{start_s}, {end_s}] s")
    return float(np.asarray(values)[mask].mean())


def _make_node(node_id, node_type, **kwargs):
    node = m.NodeInput()
    node.id, node.type = node_id, node_type
    for key, value in kwargs.items():
        setattr(node, key, value)
    return node


def _make_pipe(pipe_id, from_node, to_node, length_ft, flow_gpm):
    pipe = m.PipeInput()
    pipe.id, pipe.from_node, pipe.to_node = pipe_id, from_node, to_node
    pipe.length, pipe.diameter, pipe.roughness, pipe.flow_gpm = length_ft, D_IN, HW_C, flow_gpm
    return pipe


# ── B.8 standpipe ────────────────────────────────────────────────────────────

def run_b8_no_standpipe() -> dict:
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=H_RES_FT))
    solver.add_node(_make_node("J1", "Junction", demand=0.0, head=H_SP1_SS_FT))
    solver.add_node(_make_node("V1", "Valve", diameter=D_IN, current_setting=0.0, head=H_SP1_SS_FT))
    solver.add_node(_make_node("R2", "PressureBoundary", head=H_R2_FT))
    solver.add_pipe(_make_pipe("P1", "R1", "J1", L_FT, Q0_GPM))
    solver.add_pipe(_make_pipe("P2", "J1", "V1", _L_SHORT_FT, Q0_GPM))
    solver.add_pipe(_make_pipe("P3", "V1", "R2", _L_SHORT_FT, 0.0))
    return solver.run(TOTAL_B8_S, DT_S, -14.0, DT_S, 0.0)


def run_b8_with_standpipe() -> dict:
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=H_RES_FT))
    solver.add_node(_make_node("SP1", "Standpipe", head=H_SP1_SS_FT, tank_area=A_S_FT2))
    solver.add_node(_make_node("V1", "Valve", diameter=D_IN, current_setting=0.0, head=H_SP1_SS_FT))
    solver.add_node(_make_node("R2", "PressureBoundary", head=H_R2_FT))
    solver.add_pipe(_make_pipe("P1", "R1", "SP1", L_FT, Q0_GPM))
    solver.add_pipe(_make_pipe("P2", "SP1", "V1", _L_SHORT_FT, Q0_GPM))
    solver.add_pipe(_make_pipe("P3", "V1", "R2", _L_SHORT_FT, 0.0))
    return solver.run(TOTAL_B8_S, DT_S, -14.0, DT_S, 0.0)


@dataclass(frozen=True)
class StandpipeMetrics:
    peak_no_standpipe_ft: float
    peak_with_standpipe_ft: float
    joukowsky_reference_ft: float
    joukowsky_error_ft: float
    mass_osc_peak_reference_ft: float
    mitigation_fraction: float
    passed: bool


def evaluate_standpipe() -> tuple[dict, dict, StandpipeMetrics]:
    res_none = run_b8_no_standpipe()
    res_sp = run_b8_with_standpipe()
    peak_none = float(np.max(np.asarray(res_none["node_head"]["J1"])))
    peak_sp = float(np.max(np.asarray(res_sp["node_head"]["SP1"])))
    jouk_err = abs(peak_none - SP_H_JOUK_PEAK_FT)
    mitigation = 1.0 - (peak_sp - H_SP1_SS_FT) / max(peak_none - H_SP1_SS_FT, 1e-6)
    passed = (
        jouk_err <= TOL_JOUK_FT
        and peak_sp < TOL_STANDPIPE_UP_FT
        and abs(peak_sp - SP_H_PEAK_ANALYTICAL_FT) <= TOL_PEAK_ANAL_FT
        and mitigation >= TOL_MITIGATION_PCT
    )
    metrics = StandpipeMetrics(
        peak_no_standpipe_ft=peak_none,
        peak_with_standpipe_ft=peak_sp,
        joukowsky_reference_ft=SP_H_JOUK_PEAK_FT,
        joukowsky_error_ft=jouk_err,
        mass_osc_peak_reference_ft=SP_H_PEAK_ANALYTICAL_FT,
        mitigation_fraction=mitigation,
        passed=passed,
    )
    return res_none, res_sp, metrics


# ── Valve-side protection (test_surge_device_mitigation) ─────────────────────

def _add_protection_node(solver, kind: str, *, node_id: str, head_ft: float) -> None:
    if kind == "none":
        solver.add_node(_make_node(node_id, "Junction", head=head_ft))
    elif kind == "Standpipe":
        area = 10.0 if node_id == "Prot" else 1.0
        solver.add_node(_make_node(node_id, "Standpipe", head=head_ft, tank_area=area))
    elif kind == "HydropneumaticTank":
        solver.add_node(
            _make_node(
                node_id,
                "HydropneumaticTank",
                head=head_ft,
                diameter=4.0,
                gas_volume=12.0 if head_ft >= 160.0 else 10.0,
                tank_volume=30.0,
                polytropic_n=1.2,
                loss_coeff_in=0.7,
                loss_coeff_out=0.7,
            )
        )
    else:
        raise ValueError(kind)


def run_valve_closure_case(kind: str) -> dict:
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=150.0))
    _add_protection_node(solver, kind, node_id="Prot", head_ft=145.8)
    solver.add_node(_make_node("Valve_A", "Valve", diameter=12.0, current_setting=100.0, head=145.8))
    solver.add_node(_make_node("R2", "PressureBoundary", head=145.8))
    solver.add_pipe(_make_pipe("P1", "R1", "Prot", 3000.0, 500.0))
    solver.add_pipe(_make_pipe("P2", "Prot", "Valve_A", 40.0, 500.0))
    solver.add_pipe(_make_pipe("P3", "Valve_A", "R2", 40.0, 0.0))
    solver.set_valve_schedule("Valve_A", [(0.0, 100.0), (DT_S, 0.0), (VALVE_CLOSURE_TOTAL_S, 0.0)])
    return solver.run(total_time=VALVE_CLOSURE_TOTAL_S, dt=DT_S)


@dataclass(frozen=True)
class ValveClosureDeviceMetrics:
    kind: str
    peak_head_ft: float
    peak_reduction_ft: float
    cavitation_steps: int
    passed: bool


def evaluate_valve_closure_mitigation() -> tuple[dict, dict[str, dict], list[ValveClosureDeviceMetrics]]:
    baseline = run_valve_closure_case("none")
    baseline_peak = float(np.max(np.asarray(baseline["node_head"]["Prot"])))
    out: dict[str, dict] = {"none": baseline}
    metrics = []
    for kind in ("Standpipe", "HydropneumaticTank"):
        data = run_valve_closure_case(kind)
        out[kind] = data
        peak = float(np.max(np.asarray(data["node_head"]["Prot"])))
        cav = int(np.asarray(data["node_cavitation"]["Prot"]).sum())
        reduction = baseline_peak - peak
        passed = (
            reduction >= 200.0
            and peak <= VALVE_PEAK_LIMIT_FT[kind]
            and cav == 0
        )
        metrics.append(
            ValveClosureDeviceMetrics(kind, peak, reduction, cav, passed)
        )
    return baseline, out, metrics


# ── Pump trip — hydropneumatic (size-benchmark geometry) ─────────────────────

def run_hpt_pump_trip_unprotected() -> dict:
    solver = m.MOCSolver()
    solver.add_node(_make_node("Rlow", "PressureBoundary", head=100.0))
    solver.add_node(_make_node("PumpIn", "Junction", head=100.0))
    solver.add_node(_make_node("Pump_A", "Pump", design_head=120.0, design_flow=500.0, current_speed=100.0, head=220.0))
    solver.add_node(_make_node("Jd", "Junction", head=220.0))
    solver.add_node(_make_node("JunctionBypass", "Junction", head=160.0))
    solver.add_node(_make_node("Rhigh", "PressureBoundary", head=160.0))
    solver.add_pipe(_make_pipe("Ps", "Rlow", "PumpIn", 500.0, 800.0))
    solver.add_pipe(_make_pipe("Ppump", "Pump_A", "Jd", 40.0, 800.0))
    solver.add_pipe(_make_pipe("Pstub", "Jd", "JunctionBypass", 40.0, 800.0))
    solver.add_pipe(_make_pipe("Pmain", "JunctionBypass", "Rhigh", 4000.0, 800.0))
    solver.set_pump_schedule("Pump_A", [(0.0, 100.0), (4.99, 100.0), (5.0, 0.0), (PUMP_TRIP_TOTAL_S, 0.0)])
    return solver.run(total_time=PUMP_TRIP_TOTAL_S, dt=DT_S)


def run_hpt_pump_trip_protected(tank_volume_ft3: float = HPT_TANK_VOLUME_FT3) -> dict:
    gas_vol = HPT_PRECHARGE_RATIO * tank_volume_ft3
    solver = m.MOCSolver()
    solver.add_node(_make_node("Rlow", "PressureBoundary", head=100.0))
    solver.add_node(_make_node("PumpIn", "Junction", head=100.0))
    solver.add_node(_make_node("Pump_A", "Pump", design_head=120.0, design_flow=500.0, current_speed=100.0, head=220.0))
    solver.add_node(_make_node("Jd", "Junction", head=220.0))
    solver.add_node(
        _make_node(
            "HPT1",
            "HydropneumaticTank",
            head=160.0,
            diameter=4.0,
            gas_volume=gas_vol,
            tank_volume=tank_volume_ft3,
            polytropic_n=1.2,
            loss_coeff_in=0.7,
            loss_coeff_out=0.7,
        )
    )
    solver.add_node(_make_node("Rhigh", "PressureBoundary", head=160.0))
    solver.add_pipe(_make_pipe("Ps", "Rlow", "PumpIn", 500.0, 800.0))
    solver.add_pipe(_make_pipe("Ppump", "Pump_A", "Jd", 40.0, 800.0))
    solver.add_pipe(_make_pipe("Pstub", "Jd", "HPT1", 40.0, 800.0))
    solver.add_pipe(_make_pipe("Pmain", "HPT1", "Rhigh", 4000.0, 800.0))
    solver.set_pump_schedule("Pump_A", [(0.0, 100.0), (4.99, 100.0), (5.0, 0.0), (PUMP_TRIP_TOTAL_S, 0.0)])
    return solver.run(total_time=PUMP_TRIP_TOTAL_S, dt=DT_S)


@dataclass(frozen=True)
class HptTripMetrics:
    jd_trip_mean_ft: float
    improvement_vs_none_ft: float
    reference_floor_ft: float
    passed: bool


@dataclass(frozen=True)
class HptPrechargeMetrics:
    design_head_ft: float
    polytropic_head_ft: float
    passed: bool


def evaluate_hydropneumatic_precharge() -> tuple[dict, dict, HptTripMetrics, HptPrechargeMetrics]:
    res_none = run_hpt_pump_trip_unprotected()
    res_hpt = run_hpt_pump_trip_protected()
    t0 = np.asarray(res_none["time"])
    t1 = np.asarray(res_hpt["time"])
    jd_none = _mean_over_window(t0, res_none["node_head"]["Jd"], TRIP_START_S, TRIP_END_S)
    jd_hpt = _mean_over_window(t1, res_hpt["node_head"]["Jd"], TRIP_START_S, TRIP_END_S)
    improvement = jd_hpt - jd_none
    trip = HptTripMetrics(jd_hpt, improvement, HPT_TRIP_FLOOR_FT, jd_hpt >= HPT_TRIP_FLOOR_FT and improvement >= HPT_IMPROVEMENT_MIN_FT)
    design_h = 160.0 - 33.9  # README polytropic reference form at precharge
    poly_h = float(np.asarray(res_hpt["node_head"]["HPT1"])[0])
    pre = HptPrechargeMetrics(design_h, poly_h, abs(poly_h - design_h) < 5.0)
    return res_none, res_hpt, trip, pre


# ── Air valve (test_air_valve.py) ────────────────────────────────────────────

def run_air_valve_case(with_air_valve: bool, *, restart: bool = False) -> dict:
    solver = m.MOCSolver()
    solver.add_node(_make_node("Rlow", "PressureBoundary", head=100.0))
    solver.add_node(_make_node("PumpIn", "Junction", head=100.0))
    solver.add_node(_make_node("Pump_A", "Pump", design_head=120.0, design_flow=500.0, current_speed=100.0, head=220.0))
    solver.add_node(_make_node("Jd", "Junction", head=220.0))
    if with_air_valve:
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
    else:
        solver.add_node(_make_node("Vent", "Junction", elevation=0.0, head=160.0))
    solver.add_node(_make_node("Rhigh", "PressureBoundary", head=160.0))
    solver.add_pipe(_make_pipe("Ps", "Rlow", "PumpIn", 500.0, 800.0))
    solver.add_pipe(_make_pipe("Ppump", "Pump_A", "Jd", 40.0, 800.0))
    solver.add_pipe(_make_pipe("Pstub", "Jd", "Vent", 40.0, 800.0))
    solver.add_pipe(_make_pipe("Pmain", "Vent", "Rhigh", 4000.0, 800.0))
    speed_after = 100.0 if restart else 0.0
    solver.set_pump_schedule(
        "Pump_A",
        [(0.0, 100.0), (4.99, 100.0), (5.0, 0.0), (7.99, 0.0), (8.0, speed_after), (PUMP_TRIP_TOTAL_S, speed_after)],
    )
    return solver.run(total_time=PUMP_TRIP_TOTAL_S, dt=DT_S)


@dataclass(frozen=True)
class AirValveTripMetrics:
    unprotected_trip_min_ft: float
    protected_trip_min_ft: float
    jd_improvement_ft: float
    atmospheric_reference_ft: float
    passed: bool


def evaluate_air_valve_vs_unprotected() -> tuple[dict, dict, AirValveTripMetrics]:
    unprot = run_air_valve_case(False)
    prot = run_air_valve_case(True)
    tb = np.asarray(unprot["time"])
    tp = np.asarray(prot["time"])
    base_trip = _mean_over_window(tb, unprot["node_head"]["Vent"], TRIP_START_S, TRIP_END_S)
    prot_trip = _mean_over_window(tp, prot["node_head"]["Vent"], TRIP_START_S, TRIP_END_S)
    jd_base = _mean_over_window(tb, unprot["node_head"]["Jd"], TRIP_START_S, TRIP_END_S)
    jd_prot = _mean_over_window(tp, prot["node_head"]["Jd"], TRIP_START_S, TRIP_END_S)
    trip_mask = (tp >= TRIP_START_S) & (tp <= TRIP_END_S)
    prot_min = float(np.min(np.asarray(prot["node_head"]["Vent"])[trip_mask]))
    unprot_min = float(np.min(np.asarray(unprot["node_head"]["Vent"])))
    improvement = jd_prot - jd_base
    passed = (
        base_trip < 0.0
        and prot_trip >= -5.0
        and prot_min >= -5.0
        and unprot_min <= -30.0
        and improvement >= 10.0
    )
    return unprot, prot, AirValveTripMetrics(unprot_min, prot_min, improvement, 0.0, passed)


@dataclass(frozen=True)
class AirValveRestartMetrics:
    pretrip_head_ft: float
    early_restart_head_ft: float
    late_restart_head_ft: float
    passed: bool


def evaluate_air_valve_restart() -> tuple[dict, AirValveRestartMetrics]:
    data = run_air_valve_case(True, restart=True)
    t = np.asarray(data["time"])
    vent = np.asarray(data["node_head"]["Vent"])
    pretrip = _mean_over_window(t, vent, AIR_PRE_START_S, AIR_PRE_END_S)
    early = _mean_over_window(t, vent, AIR_RESTART_EARLY_START_S, AIR_RESTART_EARLY_END_S)
    late = _mean_over_window(t, vent, AIR_RESTART_LATE_START_S, AIR_RESTART_LATE_END_S)
    passed = early >= pretrip + 30.0 and early >= late + 30.0 and abs(late - pretrip) <= 10.0
    return data, AirValveRestartMetrics(pretrip, early, late, passed)


# ── Optional TSNet standpipe overlay ─────────────────────────────────────────

@dataclass(frozen=True)
class TsnetStandpipeOverlay:
    rthym_time_s: np.ndarray
    rthym_head_ft: np.ndarray
    tsnet_time_s: np.ndarray | None
    tsnet_head_ft: np.ndarray | None
    rthym_peak_ft: float
    tsnet_peak_ft: float | None
    peak_diff_ft: float | None
    rms_ft: float | None
    documented_peak_diff_ft: float
    documented_rms_ft: float
    ran_tsnet: bool
    tsnet_error: str | None


def try_tsnet_standpipe_overlay(*, run_tsnet: bool = False) -> TsnetStandpipeOverlay:
    res = run_b8_with_standpipe()
    rthym_t = np.asarray(res["time"], dtype=float).reshape(-1)
    rthym_h = np.asarray(res["node_head"]["SP1"], dtype=float).reshape(-1)
    rthym_peak = float(np.max(rthym_h))

    tsnet_t = tsnet_h = None
    tsnet_peak = rms = peak_diff = None
    err_msg = None
    ran = False

    if not run_tsnet:
        try:
            from cross_engine_verification_utils import load_tsnet_standpipe_traces

            tsnet_t, tsnet_h = load_tsnet_standpipe_traces()
            tsnet_peak = float(tsnet_h[tsnet_t <= TSNET_COMPARE_WINDOW_S].max())
            mask = (rthym_t <= TSNET_COMPARE_WINDOW_S) & (np.isfinite(rthym_h))
            tw = rthym_t[mask]
            rthym_w = rthym_h[mask]
            ts_interp = np.interp(tw, tsnet_t, tsnet_h)
            rms = float(np.sqrt(np.mean((rthym_w - ts_interp) ** 2)))
            peak_diff = abs(rthym_peak - tsnet_peak)
            return TsnetStandpipeOverlay(
                rthym_time_s=rthym_t,
                rthym_head_ft=rthym_h,
                tsnet_time_s=tsnet_t,
                tsnet_head_ft=tsnet_h,
                rthym_peak_ft=rthym_peak,
                tsnet_peak_ft=tsnet_peak,
                peak_diff_ft=peak_diff,
                rms_ft=rms,
                documented_peak_diff_ft=TSNET_PEAK_DIFF_FT,
                documented_rms_ft=TSNET_RMS_0_20_FT,
                ran_tsnet=False,
                tsnet_error=None,
            )
        except FileNotFoundError:
            pass
        return TsnetStandpipeOverlay(
            rthym_time_s=rthym_t,
            rthym_head_ft=rthym_h,
            tsnet_time_s=None,
            tsnet_head_ft=None,
            rthym_peak_ft=rthym_peak,
            tsnet_peak_ft=TSNET_STANDPIPE_PEAK_HEAD_FT,
            peak_diff_ft=TSNET_PEAK_DIFF_FT,
            rms_ft=TSNET_RMS_0_20_FT,
            documented_peak_diff_ft=TSNET_PEAK_DIFF_FT,
            documented_rms_ft=TSNET_RMS_0_20_FT,
            ran_tsnet=False,
            tsnet_error="Checked-in TSNet trace missing; see tests/TSNet_Standpipe_B8_*",
        )

    try:
        from cross_engine_verification_utils import run_tsnet_standpipe_b8_trace

        tsnet_t, tsnet_h = run_tsnet_standpipe_b8_trace()
        ran = True
        tsnet_peak = float(np.max(tsnet_h))
        mask = (rthym_t <= TSNET_COMPARE_WINDOW_S) & (np.isfinite(rthym_h))
        rthym_w = rthym_h[mask]
        tw = rthym_t[mask]
        ts_interp = np.interp(tw, tsnet_t, tsnet_h)
        rms = float(np.sqrt(np.mean((rthym_w - ts_interp) ** 2)))
        peak_diff = abs(rthym_peak - tsnet_peak)
    except Exception as exc:
        err_msg = str(exc)

    return TsnetStandpipeOverlay(
        rthym_time_s=rthym_t,
        rthym_head_ft=rthym_h,
        tsnet_time_s=tsnet_t,
        tsnet_head_ft=tsnet_h,
        rthym_peak_ft=rthym_peak,
        tsnet_peak_ft=tsnet_peak,
        peak_diff_ft=peak_diff,
        rms_ft=rms,
        documented_peak_diff_ft=TSNET_PEAK_DIFF_FT,
        documented_rms_ft=TSNET_RMS_0_20_FT,
        ran_tsnet=ran,
        tsnet_error=err_msg,
    )
