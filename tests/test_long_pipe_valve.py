# Copyright (c) 2026 Jason Lillywhite <jason@lillywhitewater.com>
# SPDX-License-Identifier: MIT
# Author: Jason Lillywhite <jason@lillywhitewater.com>
"""
tests/test_long_pipe_valve.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Cross-engine verification: R-THYM web app (JavaScript) vs rthym-moc C++/Python.

Network: "Long Pipe Valve"
  PressureBoundary_A (H=100 ft)
    --[Pipe_1: 1000 ft, 36 in, HW C=150]--> Junction_A  (elev=66 ft)
    --[Pipe_2: 1000 ft, 36 in, HW C=150]--> Junction_B  (elev=76 ft)
    --[Pipe_3: 1000 ft, 36 in, HW C=150]--> Valve_B     (elev=0 ft, diam=8 in)
    --[Pipe_4:  500 ft, 36 in, HW C=150]--> Junction_C  (elev=0 ft)
    --[Pipe_5:  500 ft, 36 in, HW C=150]--> PressureBoundary_B (H=25 ft)

Transient: Valve_B closes from 5 % open to 0 % using an equal-percentage
schedule beginning at t ≈ 22.63 s, completing at t ≈ 32.77 s.

Reference data (R-THYM web app, JavaScript engine):
  tests/R-THYM_MOC_Verification.json  – steady-state, wave speeds, peak pressures
  tests/R-THYM_MOC_Traces.csv         – time series (psi / GPM) from t=0.01 s

Test metrics
------------
1. Wave speed:        C++ computed value vs JS reference (tolerance ±5 ft/s)
2. Steady-state head: Pre-closure junction heads (tolerance ±0.5 ft)
3. Peak pressures:    Min/max pressure at each node (tolerance ±1.5 psi)
4. Time series:       RMS error over the post-closure window 35.0–65.0 s
                      (tolerance ±2.0 psi for pressure, ±10 GPM for flow)
"""

import csv
import json
import math
import os

import numpy as np
import pytest

import rthym_moc

# ── Paths ─────────────────────────────────────────────────────────────────────
_HERE   = os.path.dirname(__file__)
_JSON   = os.path.join(_HERE, "R-THYM_MOC_Verification.json")
_CSV    = os.path.join(_HERE, "R-THYM_MOC_Traces.csv")
_INP    = os.path.join(_HERE, "Long Pipe Valve.inp")

# ── Load reference data ───────────────────────────────────────────────────────
with open(_JSON) as _f:
    REF = json.load(_f)

REF_DT          = REF["dt"]                    # 0.01 s
REF_Q0_GPM      = REF["steadyState"]["pipes"]["Pipe_1"]["Q_gpm"]   # ~544.84 GPM
REF_WAVE_FPS    = REF["waveSpeeds"]["Pipe_1"]  # ~746.67 ft/s
REF_SS_HEADS    = {k: v["head"] for k, v in REF["steadyState"]["nodes"].items()}
REF_PEAKS       = REF["peaks"]                 # psi values keyed by node id
REF_VALVE_SCHED = [(s["t"], s["pct"]) for s in REF["valveSchedules"]["Valve_B"]]

def _load_csv():
    """Return numpy arrays (time, Valve_B_psi, Valve_B_gpm, JB_psi, JB_gpm,
    JC_psi, JC_gpm) from the reference CSV, skipping blank/partial rows."""
    cols = {
        "t":    "Time(s)",
        "vp":   "Valve_B_P(psi)",
        "p3q":  "Pipe_3_Q(gpm)",
        "jb_p": "Junction_B_P(psi)",
        "p2q":  "Pipe_2_Q(gpm)",
        "jc_p": "Junction_C_P(psi)",
        "p4q":  "Pipe_4_Q(gpm)",
    }
    arrs = {k: [] for k in cols}
    with open(_CSV) as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not all(row.get(v, "").strip() for v in cols.values()):
                continue
            for k, col in cols.items():
                arrs[k].append(float(row[col]))
    return {k: np.array(v) for k, v in arrs.items()}


# ── Pipe material: solve for wall_thickness to match the JS wave speed ────────
#
# Korteweg formula:  a = a0 / sqrt(1 + D * K_w / (E * e))
#   a0      = 4860 ft/s  (speed of sound in water)
#   D       = pipe inside diameter, inches
#   K_w     = 319 000 psi (bulk modulus of water)
#   E       = Young's modulus of pipe wall, psi
#   e       = wall thickness, inches
#
# Solving for e given E = E_PIPE_PSI and target a = REF_WAVE_FPS:
#   e = D * K_w / (E * ((a0 / a)^2 - 1))
#
# We choose E_PIPE_PSI = 400 000 psi (stiff PVC / composite), which gives a
# wall thickness typical for large-diameter plastic pressure pipe.

_K_WATER_PSI = 319_000.0
_A0_FPS      = 4_860.0
_E_PIPE_PSI  = 400_000.0   # stiff PVC
_D_PIPE_IN   = 36.0

_ratio       = (_A0_FPS / REF_WAVE_FPS) ** 2 - 1.0
_WALL_THICK  = _D_PIPE_IN * _K_WATER_PSI / (_E_PIPE_PSI * _ratio)
# For the test: also compute the wave speed that the solver will actually produce
_A_CHECK     = _A0_FPS / math.sqrt(1.0 + _D_PIPE_IN * _K_WATER_PSI
                                        / (_E_PIPE_PSI * _WALL_THICK))

# ── Build solver and run once (module-level fixture) ──────────────────────────
# Add a warmup period so MOC numerical oscillations damp to true steady state
# before the valve closure begins.  All valve-schedule times and the
# time-series comparison window are shifted by this offset.
_WARMUP_S = 60.0    # seconds of quiet pre-run before valve closure
_SIM_TIME = 172.0 + _WARMUP_S   # covers warmup + full CSV trace window
_DT       = 0.01    # matches JS dt

# Derive closure timing from the valve schedule.
# The JS engine holds the valve at _INIT_PCT until the first closure entry;
# use these to build the shifted schedule and the SS/flow comparison windows.
_INIT_PCT          = REF_VALVE_SCHED[0][1]   # initial valve opening (5.0 %)
_CLOSURE_START_JS  = next(t for t, pct in REF_VALVE_SCHED if pct < _INIT_PCT)
_CLOSURE_START_SIM = _CLOSURE_START_JS + _WARMUP_S  # =  82.63 s in C++ frame

def _make_node(id_, type_, **kwargs):
    """Construct a NodeInput using attribute assignment (binary has no kwargs ctor)."""
    n = rthym_moc.NodeInput()
    n.id   = id_
    n.type = type_
    for k, v in kwargs.items():
        setattr(n, k, v)
    return n


def _make_pipe(id_, from_node, to_node, length, **kwargs):
    """Construct a PipeInput using attribute assignment."""
    p = rthym_moc.PipeInput()
    p.id        = id_
    p.from_node = from_node
    p.to_node   = to_node
    p.length    = length
    for k, v in kwargs.items():
        setattr(p, k, v)
    return p


def _build_and_run():
    solver = rthym_moc.MOCSolver()

    # ── Nodes ──────────────────────────────────────────────────────────────
    solver.add_node(_make_node("PressureBoundary_A", "PressureBoundary",
                               elevation=0.0, head=100.0))
    # Junction initial heads must be set so the pipe grids initialise at the
    # correct piezometric head; omitting them defaults to 0 ft and fires a
    # Joukowsky shock at t=0 that takes many seconds to damp out.
    solver.add_node(_make_node("Junction_A", "Junction",
                               elevation=66.0, head=100.0))
    solver.add_node(_make_node("Junction_B", "Junction",
                               elevation=76.0, head=100.0))
    solver.add_node(_make_node("Valve_B", "Valve",
                               elevation=0.0, diameter=8.0,
                               current_setting=5.0))   # 5 % open
    solver.add_node(_make_node("Junction_C", "Junction",
                               elevation=0.0, head=25.0))
    solver.add_node(_make_node("PressureBoundary_B", "PressureBoundary",
                               elevation=0.0, head=25.0))

    # ── Pipes (material properties matched to reproduce JS wave speed) ─────
    pipe_defaults = dict(
        diameter        = _D_PIPE_IN,
        roughness       = 150.0,
        flow_gpm        = REF_Q0_GPM,
        wall_thickness  = _WALL_THICK,
        youngs_modulus  = _E_PIPE_PSI,
        poissons_ratio  = 0.3,
    )
    solver.add_pipe(_make_pipe("Pipe_1", "PressureBoundary_A", "Junction_A",
                               1000.0, **pipe_defaults))
    solver.add_pipe(_make_pipe("Pipe_2", "Junction_A", "Junction_B",
                               1000.0, **pipe_defaults))
    solver.add_pipe(_make_pipe("Pipe_3", "Junction_B", "Valve_B",
                               1000.0, **pipe_defaults))
    solver.add_pipe(_make_pipe("Pipe_4", "Valve_B", "Junction_C",
                               500.0,  **pipe_defaults))
    solver.add_pipe(_make_pipe("Pipe_5", "Junction_C", "PressureBoundary_B",
                               500.0,  **pipe_defaults))

    # ── Valve schedule (equal-percentage closure from JS reference) ────────
    # The JS engine holds the valve at _INIT_PCT until the first closure entry
    # (step-function semantics).  The C++ solver linearly interpolates between
    # adjacent schedule entries, so without an explicit hold-point it would
    # slowly drift from _INIT_PCT toward the first closure value over the whole
    # warmup period, altering the pre-closure steady state and peak pressures.
    # Inserting (0, _INIT_PCT) and (_CLOSURE_START_SIM - _DT, _INIT_PCT) pins
    # the valve at its initial opening until the actual closure begins.
    shifted_sched = (
        [(0.0, _INIT_PCT), (_CLOSURE_START_SIM - _DT, _INIT_PCT)]
        + [(t + _WARMUP_S, pct) for t, pct in REF_VALVE_SCHED[1:]]
    )
    solver.set_valve_schedule("Valve_B", shifted_sched)

    # ── Run – dynamic Vardy-Brown USF is on by default (k_bru=-1) ─────────
    results = solver.run(total_time=_SIM_TIME, dt=_DT)
    return results


# Run once at import time; reuse across all tests
print("\nRunning C++ MOC simulation …")
_RESULTS = _build_and_run()
print(f"  Simulation complete: {len(_RESULTS['time'])} time steps "
      f"({_SIM_TIME:.0f} s at dt={_DT} s, warmup={_WARMUP_S:.0f} s)")

# ── Helper: interpolate a result array to reference times ─────────────────────
def _interp_to_ref(ref_times, sim_times, sim_vals):
    return np.interp(ref_times, sim_times, sim_vals)


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 1 – Wave speed
# ═══════════════════════════════════════════════════════════════════════════════
WAVE_SPEED_TOL_FPS = 5.0   # ft/s

def test_wave_speed():
    """Computed Korteweg wave speed matches the JS reference within ±5 ft/s."""
    # The C++ solver adjusts wave speed for Courant rounding; we compare the
    # analytical Korteweg value (a_check) against the JS reference.
    err = abs(_A_CHECK - REF_WAVE_FPS)
    print(f"\n[Wave speed]  JS={REF_WAVE_FPS:.3f}  C++={_A_CHECK:.3f}  "
          f"err={err:.3f} ft/s  tol={WAVE_SPEED_TOL_FPS} ft/s")
    assert err <= WAVE_SPEED_TOL_FPS, (
        f"Wave speed mismatch: JS={REF_WAVE_FPS:.2f} ft/s, "
        f"C++={_A_CHECK:.2f} ft/s  (Δ={err:.2f} ft/s > tol={WAVE_SPEED_TOL_FPS})")


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 2 – Steady-state heads (pre-closure window, after warmup)
# ═══════════════════════════════════════════════════════════════════════════════
SS_HEAD_TOL_FT = 0.5   # ft
# Sample the pre-closure steady-state window: JS t=5–18 s (well before the
# actual closure that begins at _CLOSURE_START_JS ≈22.63 s).
_SS_T_START = 5.0  + _WARMUP_S   # = 65.0 s  (JS frame t=5 s)
_SS_T_END   = 18.0 + _WARMUP_S   # = 78.0 s  (JS frame t=18 s)

@pytest.mark.parametrize("node_id", [
    "PressureBoundary_A", "Junction_A", "Junction_B",
    "Junction_C", "PressureBoundary_B",
])
def test_steady_state_head(node_id):
    """Pre-closure piezometric heads match the JS reference within ±0.5 ft."""
    sim_times = np.array(_RESULTS["time"])
    sim_heads = np.array(_RESULTS["node_head"][node_id])

    mask     = (sim_times >= _SS_T_START) & (sim_times < _SS_T_END)
    sim_mean = float(np.mean(sim_heads[mask]))
    ref_val  = REF_SS_HEADS[node_id]
    err      = abs(sim_mean - ref_val)

    print(f"\n[SS head {node_id}]  ref={ref_val:.3f} ft  "
          f"sim={sim_mean:.3f} ft  err={err:.3f} ft  tol={SS_HEAD_TOL_FT} ft")
    assert err <= SS_HEAD_TOL_FT, (
        f"Steady-state head mismatch at {node_id}: "
        f"ref={ref_val:.3f} ft, sim={sim_mean:.3f} ft  "
        f"(Δ={err:.3f} ft > tol={SS_HEAD_TOL_FT})")


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 3 – Peak pressures (min and max over full simulation)
# ═══════════════════════════════════════════════════════════════════════════════
PEAK_PSI_TOL = 1.5   # psi

@pytest.mark.parametrize("node_id", [
    "Junction_A", "Junction_B", "Junction_C", "Valve_B",
])
def test_peak_pressure_max(node_id):
    """Maximum pressure at dynamic nodes matches JS reference within ±1.5 psi."""
    sim_psi = np.array(_RESULTS["node_pressure"][node_id])
    sim_max  = float(np.max(sim_psi))
    ref_max  = REF_PEAKS[node_id]["max"]
    err      = abs(sim_max - ref_max)

    print(f"\n[Peak max {node_id}]  ref={ref_max:.3f} psi  "
          f"sim={sim_max:.3f} psi  err={err:.3f} psi  tol={PEAK_PSI_TOL}")
    assert err <= PEAK_PSI_TOL, (
        f"Max pressure mismatch at {node_id}: "
        f"ref={ref_max:.3f} psi, sim={sim_max:.3f} psi  "
        f"(Δ={err:.3f} psi > tol={PEAK_PSI_TOL})")


@pytest.mark.parametrize("node_id", [
    "Junction_A", "Junction_B", "Junction_C", "Valve_B",
])
def test_peak_pressure_min(node_id):
    """Minimum pressure at dynamic nodes matches JS reference within ±1.5 psi."""
    sim_psi = np.array(_RESULTS["node_pressure"][node_id])
    sim_min  = float(np.min(sim_psi))
    ref_min  = REF_PEAKS[node_id]["min"]
    err      = abs(sim_min - ref_min)

    print(f"\n[Peak min {node_id}]  ref={ref_min:.3f} psi  "
          f"sim={sim_min:.3f} psi  err={err:.3f} psi  tol={PEAK_PSI_TOL}")
    assert err <= PEAK_PSI_TOL, (
        f"Min pressure mismatch at {node_id}: "
        f"ref={ref_min:.3f} psi, sim={sim_min:.3f} psi  "
        f"(Δ={err:.3f} psi > tol={PEAK_PSI_TOL})")


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 4 – Time-series comparison (surge window, relative to JS closure start)
# ═══════════════════════════════════════════════════════════════════════════════
TRACE_PSI_TOL_RMS  = 2.0   # psi  (RMS error over window)
TRACE_GPM_TOL_RMS  = 10.0  # GPM  (RMS error over window)

# CSV times are in the JS reference frame (closure ends at ~32.77 s).
# Our simulation runs in a shifted frame (+_WARMUP_S).  To align the two,
# add _WARMUP_S to each CSV reference time before interpolating.
# Pressure window: post-closure (JS t=35–65 s), within CSV range (0–95.94 s).
_TRACE_T_START   = 35.0   # JS reference time – start of pressure window
_TRACE_T_END     = 65.0   # JS reference time – end   of pressure window
# Flow window: pre-closure steady state, same JS frame as the SS head test.
_TRACE_Q_T_START = 5.0    # JS reference time – start of flow window
_TRACE_Q_T_END   = 18.0   # JS reference time – end   of flow window


def _sim_interp_at_ref(ref_t_arr, result_key, node_or_pipe_id):
    """Interpolate a sim result at the shifted equivalent of ref_t_arr."""
    sim_t   = np.array(_RESULTS["time"])
    sim_arr = np.array(_RESULTS[result_key][node_or_pipe_id])
    return _interp_to_ref(ref_t_arr + _WARMUP_S, sim_t, sim_arr)


def test_time_series_valve_pressure():
    """Valve_B pressure trace RMS error ≤ 2.0 psi over the surge window."""
    ref  = _load_csv()
    mask = (ref["t"] >= _TRACE_T_START) & (ref["t"] <= _TRACE_T_END)
    ref_t, ref_p = ref["t"][mask], ref["vp"][mask]
    sim_p = _sim_interp_at_ref(ref_t, "node_pressure", "Valve_B")
    rms   = float(np.sqrt(np.mean((sim_p - ref_p) ** 2)))

    print(f"\n[Trace Valve_B P]  RMS={rms:.3f} psi  tol={TRACE_PSI_TOL_RMS} psi")
    assert rms <= TRACE_PSI_TOL_RMS, (
        f"Valve_B pressure trace RMS={rms:.3f} psi > tol={TRACE_PSI_TOL_RMS}")


def test_time_series_junction_b_pressure():
    """Junction_B pressure trace RMS error ≤ 2.0 psi over the surge window."""
    ref  = _load_csv()
    mask = (ref["t"] >= _TRACE_T_START) & (ref["t"] <= _TRACE_T_END)
    ref_t, ref_p = ref["t"][mask], ref["jb_p"][mask]
    sim_p = _sim_interp_at_ref(ref_t, "node_pressure", "Junction_B")
    rms   = float(np.sqrt(np.mean((sim_p - ref_p) ** 2)))

    print(f"\n[Trace Junction_B P]  RMS={rms:.3f} psi  tol={TRACE_PSI_TOL_RMS} psi")
    assert rms <= TRACE_PSI_TOL_RMS, (
        f"Junction_B pressure trace RMS={rms:.3f} psi > tol={TRACE_PSI_TOL_RMS}")


def test_time_series_junction_c_pressure():
    """Junction_C pressure trace RMS error ≤ 2.0 psi over the surge window."""
    ref  = _load_csv()
    mask = (ref["t"] >= _TRACE_T_START) & (ref["t"] <= _TRACE_T_END)
    ref_t, ref_p = ref["t"][mask], ref["jc_p"][mask]
    sim_p = _sim_interp_at_ref(ref_t, "node_pressure", "Junction_C")
    rms   = float(np.sqrt(np.mean((sim_p - ref_p) ** 2)))

    print(f"\n[Trace Junction_C P]  RMS={rms:.3f} psi  tol={TRACE_PSI_TOL_RMS} psi")
    assert rms <= TRACE_PSI_TOL_RMS, (
        f"Junction_C pressure trace RMS={rms:.3f} psi > tol={TRACE_PSI_TOL_RMS}")


def test_time_series_valve_flow():
    """Pipe_3 pre-closure steady-state flow matches JS reference within ±10 GPM."""
    ref  = _load_csv()
    mask = (ref["t"] >= _TRACE_Q_T_START) & (ref["t"] <= _TRACE_Q_T_END)
    ref_t, ref_q = ref["t"][mask], ref["p3q"][mask]
    sim_q = _sim_interp_at_ref(ref_t, "pipe_flow_gpm", "Pipe_3")
    rms   = float(np.sqrt(np.mean((sim_q - ref_q) ** 2)))

    print(f"\n[Trace Pipe_3 Q]  RMS={rms:.3f} GPM  tol={TRACE_GPM_TOL_RMS} GPM")
    assert rms <= TRACE_GPM_TOL_RMS, (
        f"Pipe_3 pre-closure flow trace RMS={rms:.3f} GPM > tol={TRACE_GPM_TOL_RMS}")


# ═══════════════════════════════════════════════════════════════════════════════
# Summary printer (runs last via conftest or direct execution)
# ═══════════════════════════════════════════════════════════════════════════════
def _print_summary():
    """Print a comparison table useful for Appendix B documentation."""
    ref  = _load_csv()
    sim_t   = np.array(_RESULTS["time"])

    print("\n" + "=" * 70)
    print("  R-THYM MOC Verification — Long Pipe Valve")
    print("  JS web app  vs  C++/Python rthym-moc engine")
    print("=" * 70)

    print(f"\n  Network parameters")
    print(f"    Pipes            : 5 × 36 in, HW C=150")
    print(f"    Pipe lengths     : 1000 / 1000 / 1000 / 500 / 500 ft")
    print(f"    Valve            : 8 in TCV, initial opening 5 %")
    print(f"    Initial flow Q₀  : {REF_Q0_GPM:.2f} GPM")
    print(f"    Pipe material    : E = {_E_PIPE_PSI:,.0f} psi, "
          f"e = {_WALL_THICK:.3f} in")

    print(f"\n  Wave speed comparison")
    print(f"    JS reference     : {REF_WAVE_FPS:.2f} ft/s")
    print(f"    C++ computed     : {_A_CHECK:.2f} ft/s")
    print(f"    Error            : {abs(_A_CHECK - REF_WAVE_FPS):.2f} ft/s")

    print(f"\n  Steady-state heads ({_SS_T_START:.0f}–{_SS_T_END:.0f} s window, ft)")
    print(f"    {'Node':<24}  {'JS ref':>9}  {'C++ sim':>9}  {'Error':>8}")
    print(f"    {'-'*24}  {'-'*9}  {'-'*9}  {'-'*8}")
    for nid in ["PressureBoundary_A", "Junction_A", "Junction_B",
                "Junction_C", "PressureBoundary_B"]:
        mask  = (sim_t >= _SS_T_START) & (sim_t < _SS_T_END)
        sim_h = float(np.mean(np.array(_RESULTS["node_head"][nid])[mask]))
        err   = sim_h - REF_SS_HEADS[nid]
        print(f"    {nid:<24}  {REF_SS_HEADS[nid]:>9.3f}  {sim_h:>9.3f}  {err:>+8.3f}")

    print(f"\n  Peak pressures (psi, full simulation)")
    print(f"    {'Node':<20}  {'JS max':>8}  {'C++ max':>8}  {'Err':>6}  "
          f"{'JS min':>8}  {'C++ min':>8}  {'Err':>6}")
    print(f"    {'-'*20}  {'-'*8}  {'-'*8}  {'-'*6}  {'-'*8}  {'-'*8}  {'-'*6}")
    for nid in ["PressureBoundary_A", "Junction_A", "Junction_B",
                "Junction_C", "PressureBoundary_B", "Valve_B"]:
        sim_psi = np.array(_RESULTS["node_pressure"][nid])
        c_max   = float(np.max(sim_psi))
        c_min   = float(np.min(sim_psi))
        r_max   = REF_PEAKS[nid]["max"]
        r_min   = REF_PEAKS[nid]["min"]
        print(f"    {nid:<20}  {r_max:>8.3f}  {c_max:>8.3f}  {c_max-r_max:>+6.3f}  "
              f"{r_min:>8.3f}  {c_min:>8.3f}  {c_min-r_min:>+6.3f}")

    print(f"\n  Time-series RMS errors (sim offset +{_WARMUP_S:.0f} s)")
    print(f"    Pressure: JS window {_TRACE_T_START}–{_TRACE_T_END} s (post-closure)")
    print(f"    Flow:     JS window {_TRACE_Q_T_START}–{_TRACE_Q_T_END} s (pre-closure)")
    mask_p  = (ref["t"] >= _TRACE_T_START)   & (ref["t"] <= _TRACE_T_END)
    mask_q  = (ref["t"] >= _TRACE_Q_T_START) & (ref["t"] <= _TRACE_Q_T_END)
    ref_t_p = ref["t"][mask_p]
    ref_t_q = ref["t"][mask_q]
    checks = [
        ("Valve_B psi",    ref["vp"][mask_p],   ref_t_p, "node_pressure", "Valve_B"),
        ("Junction_B psi", ref["jb_p"][mask_p], ref_t_p, "node_pressure", "Junction_B"),
        ("Junction_C psi", ref["jc_p"][mask_p], ref_t_p, "node_pressure", "Junction_C"),
        ("Pipe_3 GPM",     ref["p3q"][mask_q],  ref_t_q, "pipe_flow_gpm", "Pipe_3"),
    ]
    for label, ref_arr, ref_t_w, key, sid in checks:
        sim_arr = _sim_interp_at_ref(ref_t_w, key, sid)
        rms = float(np.sqrt(np.mean((sim_arr - ref_arr) ** 2)))
        print(f"    {label:<20}  RMS = {rms:.3f}")

    print("=" * 70)


if __name__ == "__main__":
    _print_summary()
