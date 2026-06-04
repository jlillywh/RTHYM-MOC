"""Long Pipe Valve cross-engine verification vs R-THYM exports (notebook + optional reuse)."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rthym_moc

_HERE = Path(__file__).resolve().parent
_JSON = _HERE / "R-THYM_MOC_Verification.json"
_CSV = _HERE / "R-THYM_MOC_Traces.csv"

WAVE_SPEED_TOL_FPS = 5.0
SS_HEAD_TOL_FT = 0.5
PEAK_PSI_TOL = 1.5
TRACE_PSI_TOL_RMS = 2.0
TRACE_GPM_TOL_RMS = 10.0

_K_WATER_PSI = 319_000.0
_A0_FPS = 4_860.0
_E_PIPE_PSI = 400_000.0
_D_PIPE_IN = 36.0

_WARMUP_S = 60.0
_DT = 0.01

_TRACE_T_START = 35.0
_TRACE_T_END = 65.0
_TRACE_Q_T_START = 5.0
_TRACE_Q_T_END = 18.0


def load_reference() -> tuple[dict, dict[str, np.ndarray]]:
    ref = json.loads(_JSON.read_text())
    cols = {
        "t": "Time(s)",
        "vp": "Valve_B_P(psi)",
        "p3q": "Pipe_3_Q(gpm)",
        "jb_p": "Junction_B_P(psi)",
        "p2q": "Pipe_2_Q(gpm)",
        "jc_p": "Junction_C_P(psi)",
        "p4q": "Pipe_4_Q(gpm)",
    }
    arrs = {k: [] for k in cols}
    with _CSV.open() as f:
        for row in csv.DictReader(f):
            if not all(row.get(v, "").strip() for v in cols.values()):
                continue
            for k, col in cols.items():
                arrs[k].append(float(row[col]))
    return ref, {k: np.array(v) for k, v in arrs.items()}


def _wall_thickness_for_wave_speed(target_fps: float) -> tuple[float, float]:
    ratio = (_A0_FPS / target_fps) ** 2 - 1.0
    wall = _D_PIPE_IN * _K_WATER_PSI / (_E_PIPE_PSI * ratio)
    a_check = _A0_FPS / math.sqrt(1.0 + _D_PIPE_IN * _K_WATER_PSI / (_E_PIPE_PSI * wall))
    return wall, a_check


def _make_node(id_, type_, **kwargs):
    n = rthym_moc.NodeInput()
    n.id, n.type = id_, type_
    for k, v in kwargs.items():
        setattr(n, k, v)
    return n


def _make_pipe(id_, from_node, to_node, length, **kwargs):
    p = rthym_moc.PipeInput()
    p.id, p.from_node, p.to_node, p.length = id_, from_node, to_node, length
    for k, v in kwargs.items():
        setattr(p, v)
    return p


def build_and_run_long_pipe_case(ref: dict | None = None) -> dict:
    if ref is None:
        ref, _ = load_reference()
    ref_q0 = ref["steadyState"]["pipes"]["Pipe_1"]["Q_gpm"]
    ref_wave = ref["waveSpeeds"]["Pipe_1"]
    valve_sched = [(s["t"], s["pct"]) for s in ref["valveSchedules"]["Valve_B"]]
    init_pct = valve_sched[0][1]
    closure_start_js = next(t for t, pct in valve_sched if pct < init_pct)
    closure_start_sim = closure_start_js + _WARMUP_S
    wall, _ = _wall_thickness_for_wave_speed(ref_wave)
    sim_time = 172.0 + _WARMUP_S

    solver = rthym_moc.MOCSolver()
    solver.add_node(_make_node("PressureBoundary_A", "PressureBoundary", elevation=0.0, head=100.0))
    solver.add_node(_make_node("Junction_A", "Junction", elevation=66.0, head=100.0))
    solver.add_node(_make_node("Junction_B", "Junction", elevation=76.0, head=100.0))
    solver.add_node(_make_node("Valve_B", "Valve", elevation=0.0, diameter=8.0, current_setting=5.0))
    solver.add_node(_make_node("Junction_C", "Junction", elevation=0.0, head=25.0))
    solver.add_node(_make_node("PressureBoundary_B", "PressureBoundary", elevation=0.0, head=25.0))

    pipe_defaults = dict(
        diameter=_D_PIPE_IN,
        roughness=150.0,
        flow_gpm=ref_q0,
        wall_thickness=wall,
        youngs_modulus=_E_PIPE_PSI,
        poissons_ratio=0.3,
    )
    for pid, fn, tn, L in [
        ("Pipe_1", "PressureBoundary_A", "Junction_A", 1000.0),
        ("Pipe_2", "Junction_A", "Junction_B", 1000.0),
        ("Pipe_3", "Junction_B", "Valve_B", 1000.0),
        ("Pipe_4", "Valve_B", "Junction_C", 500.0),
        ("Pipe_5", "Junction_C", "PressureBoundary_B", 500.0),
    ]:
        solver.add_pipe(_make_pipe(pid, fn, tn, L, **pipe_defaults))

    shifted = (
        [(0.0, init_pct), (closure_start_sim - _DT, init_pct)]
        + [(t + _WARMUP_S, pct) for t, pct in valve_sched[1:]]
    )
    solver.set_valve_schedule("Valve_B", shifted)
    return solver.run(total_time=sim_time, dt=_DT)


def interp_to_ref(ref_times, sim_times, sim_vals):
    return np.interp(ref_times, sim_times, sim_vals)


@dataclass(frozen=True)
class LongPipeMetrics:
    wave_speed_error_fps: float
    wave_speed_passed: bool
    ss_head_errors: dict[str, float]
    ss_head_passed: bool
    peak_max_errors_psi: dict[str, float]
    peak_min_errors_psi: dict[str, float]
    peaks_passed: bool
    trace_rms_psi: dict[str, float]
    trace_rms_gpm: dict[str, float]
    traces_passed: bool
    passed: bool


def evaluate_long_pipe(results: dict, ref: dict, csv: dict[str, np.ndarray]) -> LongPipeMetrics:
    ref_wave = ref["waveSpeeds"]["Pipe_1"]
    _, a_check = _wall_thickness_for_wave_speed(ref_wave)
    wave_err = abs(a_check - ref_wave)
    wave_ok = wave_err <= WAVE_SPEED_TOL_FPS

    sim_t = np.asarray(results["time"], dtype=float)
    ss_start = 5.0 + _WARMUP_S
    ss_end = 18.0 + _WARMUP_S
    ss_heads = ref["steadyState"]["nodes"]
    ss_errors = {}
    for nid, node in ss_heads.items():
        mask = (sim_t >= ss_start) & (sim_t < ss_end)
        sim_mean = float(np.mean(np.asarray(results["node_head"][nid])[mask]))
        ss_errors[nid] = abs(sim_mean - float(node["head"]))
    ss_ok = all(e <= SS_HEAD_TOL_FT for e in ss_errors.values())

    peak_max_err = {}
    peak_min_err = {}
    for nid in ["Junction_A", "Junction_B", "Junction_C", "Valve_B"]:
        sim_psi = np.asarray(results["node_pressure"][nid], dtype=float)
        peak_max_err[nid] = abs(float(sim_psi.max()) - ref["peaks"][nid]["max"])
        peak_min_err[nid] = abs(float(sim_psi.min()) - ref["peaks"][nid]["min"])
    peaks_ok = all(e <= PEAK_PSI_TOL for e in peak_max_err.values()) and all(
        e <= PEAK_PSI_TOL for e in peak_min_err.values()
    )

    def sim_at_ref(ref_t, key, sid):
        return interp_to_ref(np.asarray(ref_t) + _WARMUP_S, sim_t, np.asarray(results[key][sid]))

    mask_p = (csv["t"] >= _TRACE_T_START) & (csv["t"] <= _TRACE_T_END)
    ref_t_p = csv["t"][mask_p]
    trace_rms = {
        "Valve_B": float(np.sqrt(np.mean((sim_at_ref(ref_t_p, "node_pressure", "Valve_B") - csv["vp"][mask_p]) ** 2))),
        "Junction_B": float(np.sqrt(np.mean((sim_at_ref(ref_t_p, "node_pressure", "Junction_B") - csv["jb_p"][mask_p]) ** 2))),
        "Junction_C": float(np.sqrt(np.mean((sim_at_ref(ref_t_p, "node_pressure", "Junction_C") - csv["jc_p"][mask_p]) ** 2))),
    }
    mask_q = (csv["t"] >= _TRACE_Q_T_START) & (csv["t"] <= _TRACE_Q_T_END)
    ref_t_q = csv["t"][mask_q]
    trace_gpm = {
        "Pipe_3": float(np.sqrt(np.mean((sim_at_ref(ref_t_q, "pipe_flow_gpm", "Pipe_3") - csv["p3q"][mask_q]) ** 2))),
    }
    traces_ok = all(v <= TRACE_PSI_TOL_RMS for v in trace_rms.values()) and all(
        v <= TRACE_GPM_TOL_RMS for v in trace_gpm.values()
    )

    return LongPipeMetrics(
        wave_speed_error_fps=wave_err,
        wave_speed_passed=wave_ok,
        ss_head_errors=ss_errors,
        ss_head_passed=ss_ok,
        peak_max_errors_psi=peak_max_err,
        peak_min_errors_psi=peak_min_err,
        peaks_passed=peaks_ok,
        trace_rms_psi=trace_rms,
        trace_rms_gpm=trace_gpm,
        traces_passed=traces_ok,
        passed=wave_ok and ss_ok and peaks_ok and traces_ok,
    )


def run_and_evaluate_long_pipe() -> tuple[dict, dict, dict[str, np.ndarray], LongPipeMetrics]:
    ref, csv = load_reference()
    results = build_and_run_long_pipe_case(ref)
    metrics = evaluate_long_pipe(results, ref, csv)
    return results, ref, csv, metrics
