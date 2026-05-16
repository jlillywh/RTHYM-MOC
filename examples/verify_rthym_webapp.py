"""examples/verify_rthym_webapp.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Verify R-THYM web-application results for a long pipeline with a TCV valve.

Network topology (from the exported .inp)
-----------------------------------------
PressureBoundary_A (H=100 ft)
  --[Pipe_1: 1000 ft, 36"]-->  Junction_A  (elev=66 ft)
  --[Pipe_2: 1000 ft, 36"]-->  Junction_B  (elev=76 ft)
  --[Pipe_3: 1000 ft, 36"]-->  Valve_A_in  (elev=0 ft)
  --[Valve_A: TCV K=56.25, 24"]-->  Valve_A_out  (elev=0 ft)
  --[Pipe_4: 500  ft, 36"]-->  Junction_C  (elev=0 ft)
  --[Pipe_5: 500  ft, 36"]-->  PressureBoundary_B (H=25 ft)

After load_inp(), rthym_moc expands the EPANET valve link into:
  Valve_A_in  --[_P_Valve_A_up: 800 ft stub]-->  _VALVE_Valve_A
              --[_P_Valve_A_dn: 800 ft stub]-->  Valve_A_out

Transient
---------
The EPANET TCV setting of 56.250 (minor-loss coefficient K_m) converts to
% open via  s = 100 / sqrt(K_m + 1) ≈ 13.2 %.
A linear schedule closes the valve from that initial opening to 0 %
over T_CLOSURE = 1 second.

R-THYM reference results (from the web application)
----------------------------------------------------
  Valve_A upstream peak pressure  :  173.7 psi
  Junction_C minimum pressure     :  −12.68 psi
  Junction_A minimum pressure     :  −14 psi  (vapour / column separation)

Usage
-----
    pip install wntr matplotlib
    python examples/verify_rthym_webapp.py
"""

import json
import math
import os
import tempfile

import numpy as np
import rthym_moc

# ── Load R-THYM reference JSON ────────────────────────────────────────────────
_REF_JSON = os.path.join(os.path.dirname(__file__), "..", "tests",
                         "R-THYM_MOC_Verification.json")
with open(_REF_JSON) as _f:
    _REF = json.load(_f)

REF_Q0_GPM     = _REF["steadyState"]["pipes"]["Pipe_1"]["Q_gpm"]   # 4 882.78
REF_WAVE_SPEED = _REF["waveSpeeds"]["Pipe_1"]                        # 4 000 ft/s
# Peak / min reference values (scalar)
REF_VALVE_A_UPSTREAM_PEAK_PSI = _REF["peaks"]["Valve_A"]["max"]
REF_JUNCTION_C_MIN_PSI        = _REF["peaks"]["Junction_C"]["min"]
REF_JUNCTION_A_MIN_PSI        = _REF["peaks"]["Junction_A"]["min"]
# Native-dt trace from R-THYM worker (Valve_A node, upstream face)
_REF_TRACE_PTS = _REF["traces"]["Valve_A"]

# ── Exported .inp content ─────────────────────────────────────────────────────
INP_CONTENT = """\
[TITLE]
Exported from Hydro-Ops Digital Twin

[JUNCTIONS]
;ID             Elevation  Demand
Valve_A_in      0          0
Valve_A_out     0          0
Junction_A      66         0
Junction_B      76         0
Junction_C      0          0

[RESERVOIRS]
;ID                   Head
PressureBoundary_A    100
PressureBoundary_B    25

[PIPES]
;ID      Node1               Node2               Length  Diameter  Roughness  MinorLoss  Status
Pipe_1   PressureBoundary_A  Junction_A          1000    36        150        0          Open
Pipe_2   Junction_A          Junction_B          1000    36        150        0          Open
Pipe_3   Junction_B          Valve_A_in          1000    36        150        0          Open
Pipe_4   Valve_A_out         Junction_C          500     36        150        0          Open
Pipe_5   Junction_C          PressureBoundary_B  500     36        150        0          Open

[VALVES]
;ID       Node1        Node2         Diameter  Type  Setting   MinorLoss
Valve_A   Valve_A_in   Valve_A_out   24        TCV   56.250    0

[END]
"""

# ── Simulation parameters ─────────────────────────────────────────────────────
# T_CLOSURE is derived from the JSON schedule (first-step to last-step time).
_VS_RAW    = _REF["valveSchedules"]["Valve_A"]   # list of {t, pct} dicts
_T_TRIGGER = _VS_RAW[1]["t"]                      # R-THYM trigger time (4.26 s)
T_CLOSURE  = round(_VS_RAW[-1]["t"] - _T_TRIGGER, 6)  # 0.35 s (geometric, 8 steps)
TOTAL_TIME = 20.0   # seconds  — simulation window
DT         = 0.01   # seconds  — time step
P_VAPOR    = -14.0  # psi      — vapour pressure threshold (p_vapor_psi in run())
USF_TAU    = 0.5    # seconds  — unsteady-friction time constant

# ── EPANET TCV setting (for reference) ──────────────────────────────────────
KM = 56.250    # EPANET minor-loss coefficient exported by R-THYM
# NOTE: R-THYM's transient valve model yields Q₀ = REF_Q0_GPM, which does NOT
# match the flow predicted by rthym_moc when it applies K_m=56.25 to a 24"
# orifice area (that would give ≈12 700 GPM).  The discrepancy reflects a
# difference in valve-model conventions between the two engines.  We therefore
# take Q₀ from the R-THYM JSON and invert rthym_moc's valve formula to find
# the equivalent % open that reproduces R-THYM's initial conditions.


def _hw_hf_ft(q_gpm: float, length_ft: float, diam_in: float, hw_c: float) -> float:
    """Hazen-Williams head loss in ft."""
    q = q_gpm * 6.309e-5
    L = length_ft * 0.3048
    D = diam_in * 0.0254
    return 10.67 * L * q ** 1.852 / (hw_c ** 1.852 * D ** 4.87) / 0.3048


def _solve_pct_open_from_q(
    q_gpm: float,
    dH_ft: float,
    total_pipe_len_ft: float,
    pipe_diam_in: float,
    hw_c: float,
    valve_diam_in: float,
) -> float:
    """Invert rthym_moc's valve model K=(100/s)²−1, ΔH=K·Q²/(2g·A_v²)
    to find the % open that gives *q_gpm* in steady state.
    Reference area A_v uses the valve diameter (same as moc_solver.cpp).
    """
    q_cfs  = q_gpm * 0.002228
    hf_ft  = _hw_hf_ft(q_gpm, total_pipe_len_ft, pipe_diam_in, hw_c)
    h_v    = dH_ft - hf_ft
    A_v_ft = math.pi * (valve_diam_in / 24.0) ** 2   # ft²  (diam_in / 12 / 2)²·π
    K_eq   = h_v / (q_cfs ** 2)                       # ft / (ft³/s)²
    K      = K_eq * 2.0 * 32.2 * A_v_ft ** 2
    return 100.0 / math.sqrt(K + 1.0)


# Q₀ taken directly from R-THYM JSON (ground truth for initial conditions)
Q0_GPM = REF_Q0_GPM   # 4 882.78 GPM

# Equivalent rthym_moc % open that reproduces R-THYM's Q₀
PCT_INITIAL = _solve_pct_open_from_q(
    q_gpm            = Q0_GPM,
    dH_ft            = 75.0,
    total_pipe_len_ft= 4000.0,
    pipe_diam_in     = 36.0,
    hw_c             = 150.0,
    valve_diam_in    = 24.0,
)   # ≈ 5.0 %

# ─────────────────────────────────────────────────────────────────────────────
print("=" * 62)
print("  RTHYM-MOC  ↔  R-THYM web app verification")
print("=" * 62)
print(f"  R-THYM Q₀ = {Q0_GPM:,.2f} GPM  (from verification JSON)")
print(f"  Equivalent rthym_moc valve opening = {PCT_INITIAL:.2f} %")
print(f"  (EPANET K_m = {KM} → rthym_moc 24\" model gives different Q₀)")
print(f"  Wave speed = {REF_WAVE_SPEED:.0f} ft/s  (R-THYM reported; rthym_moc default)")
print(f"  Closure: {PCT_INITIAL:.2f} % → 0 % in {T_CLOSURE} s  "
      f"(geometric ×0.75/step, Δt=0.05 s — from R-THYM JSON schedule)")
print(f"  Total simulation: {TOTAL_TIME} s,  dt = {DT} s")
print()

# Steady-state HGL at each node  (used to seed the MOC grid).
# The network is a simple series chain; we walk it from both ends.
_hf_P1  = _hw_hf_ft(Q0_GPM, 1000, 36, 150)
_hf_P2  = _hw_hf_ft(Q0_GPM, 1000, 36, 150)
_hf_P3  = _hw_hf_ft(Q0_GPM, 1000, 36, 150)
_hf_P4  = _hw_hf_ft(Q0_GPM,  500, 36, 150)
_hf_P5  = _hw_hf_ft(Q0_GPM,  500, 36, 150)
# Stub length: must be ≥ a*T_closure/2 so reflected waves from the stub/pipe
# diameter change don't return during closure.  ceil(4000*0.35/2/40)*40 = 720 ft.
_STUB_LEN_FT = math.ceil(4000.0 * T_CLOSURE / 2.0 / (4000.0 * DT)) * (4000.0 * DT)
_STUB_LEN_FT = max(_STUB_LEN_FT, 800.0)   # round up to a safe value

# Stub pipes use the valve diameter (24") — friction over _STUB_LEN_FT ft.
_hf_stub = _hw_hf_ft(Q0_GPM, _STUB_LEN_FT, 24, 130)

H0 = {
    "Junction_A":  100.0 - _hf_P1,
    "Junction_B":  100.0 - _hf_P1 - _hf_P2,
    "Valve_A_in":  100.0 - _hf_P1 - _hf_P2 - _hf_P3,
    # _VALVE_Valve_A falls back to Valve_A_in head inside load_inp
    "Valve_A_out": 25.0  + _hf_P4 + _hf_P5 + _hf_stub,
    "Junction_C":  25.0  + _hf_P5,
}

# ── Write .inp to a temporary file and load ───────────────────────────────────
with tempfile.NamedTemporaryFile(
    mode="w", suffix=".inp", delete=False, encoding="utf-8"
) as f:
    f.write(INP_CONTENT)
    inp_path = f.name

try:
    # Provide initial flows explicitly — wntr may fail on some installs.
    # Q0_GPM is computed analytically from the energy equation above.
    # The valve link "Valve_A" sets both stub pipe flows (_P_Valve_A_up/_dn).
    _all_pipe_ids = ["Pipe_1", "Pipe_2", "Pipe_3", "Pipe_4", "Pipe_5"]
    _initial_flows = {pid: Q0_GPM for pid in _all_pipe_ids}
    _initial_flows["Valve_A"] = Q0_GPM   # sets both stub pipes
    solver = rthym_moc.load_inp(
        inp_path, use_wntr=True,
        initial_flows=_initial_flows,
        initial_heads=H0,
        stub_length_ft=_STUB_LEN_FT,
    )
finally:
    os.unlink(inp_path)

# ── Register the valve closure schedule ──────────────────────────────────────
# Replicate R-THYM's geometric (equal-percentage) closure schedule from JSON.
# Each PCT step is applied over one DT ramp (near-instantaneous) to model the
# step-function changes that R-THYM applies at every 0.05 s interval.
t_sched: list = [0.0]
s_sched: list = [PCT_INITIAL]
_prev_pct = PCT_INITIAL
for _entry in _VS_RAW[1:]:
    _t_rel = round(_entry["t"] - _T_TRIGGER, 6)  # time relative to closure start
    _pct   = _entry["pct"]
    if _t_rel > 0:
        # Hold the previous pct until one DT before the next step
        t_sched.append(_t_rel - DT)
        s_sched.append(_prev_pct)
    # Apply the new pct (ramp over one DT from the previous value)
    t_sched.append(max(_t_rel, DT))
    s_sched.append(_pct)
    _prev_pct = _pct
t_sched.append(TOTAL_TIME)
s_sched.append(0.0)
solver.set_valve_schedule("_VALVE_Valve_A", list(zip(t_sched, s_sched)))

# ── Run simulation ────────────────────────────────────────────────────────────
results = solver.run(
    total_time=TOTAL_TIME,
    dt=DT,
    p_vapor_psi=P_VAPOR,
    usf_tau=USF_TAU,
)

t = np.array(results["time"])

# Collect pressures for all nodes of interest.
# Valve_A_in  → R-THYM "Valve_A upstreamPressure"
# Valve_A_out → R-THYM "Valve_A downstreamPressure"
NODE_IDS = [
    "Junction_A",
    "Junction_B",
    "_VALVE_Valve_A",   # internal valve node  ↔  R-THYM "Valve_A"
    "Valve_A_in",      # upstream junction    ↔  R-THYM "Valve_A_in" (if reported)
    "Valve_A_out",     # downstream junction
    "Junction_C",
]
P = {nid: np.array(results["node_pressure"][nid]) for nid in NODE_IDS}

# ── Print comparison table ────────────────────────────────────────────────────
print(f"  Steady-state pressures at t=0:")
for nid in NODE_IDS:
    print(f"    {nid:20s}: {P[nid][0]:7.2f} psi")

print()
print(f"  {'Metric':<45}  {'rthym-moc':>10}  {'R-THYM':>10}  {'Error':>8}")
print(f"  {'-'*45}  {'-'*10}  {'-'*10}  {'-'*8}")

# Peak upstream pressure at _VALVE_Valve_A  (= R-THYM "Valve_A")
peak_up = P["_VALVE_Valve_A"].max()
t_peak  = t[P["_VALVE_Valve_A"].argmax()]
err_up  = abs(peak_up - REF_VALVE_A_UPSTREAM_PEAK_PSI) / abs(REF_VALVE_A_UPSTREAM_PEAK_PSI) * 100
print(f"  {'Valve_A upstream peak (psi)':<45}  {peak_up:10.1f}  {REF_VALVE_A_UPSTREAM_PEAK_PSI:10.1f}  {err_up:7.1f}%")
print(f"    → peak occurs at t = {t_peak:.3f} s")

# Minimum pressure at Junction_C
min_jc  = P["Junction_C"].min()
t_jc    = t[P["Junction_C"].argmin()]
err_jc  = abs(min_jc - REF_JUNCTION_C_MIN_PSI) / abs(REF_JUNCTION_C_MIN_PSI) * 100
print(f"  {'Junction_C minimum (psi)':<45}  {min_jc:10.2f}  {REF_JUNCTION_C_MIN_PSI:10.2f}  {err_jc:7.1f}%")
print(f"    → minimum at t = {t_jc:.3f} s")

# Minimum pressure at Junction_A
min_ja  = P["Junction_A"].min()
t_ja    = t[P["Junction_A"].argmin()]
print(f"  {'Junction_A minimum (psi)':<45}  {min_ja:10.2f}  {REF_JUNCTION_A_MIN_PSI:10.2f}")
print(f"    → minimum at t = {t_ja:.3f} s")

# Cavitation summary
print()
print("  Cavitation (pressure < p_vapor = {:.0f} psi):".format(P_VAPOR))
cav = results.get("node_cavitation", {})
any_cav = False
for nid in NODE_IDS:
    if nid in cav:
        flag = np.array(cav[nid])
        if flag.any():
            t_first = t[np.argmax(flag > 0)]
            print(f"    {nid:20s}: YES  (first at t = {t_first:.3f} s, "
                  f"{int(flag.sum())} steps, {flag.sum()*DT:.2f} s total)")
            any_cav = True
if not any_cav:
    print("    (none detected)")

print()

# ── Trace comparison: Valve_A pressure ───────────────────────────────────────
# Find the closure-start time in the R-THYM trace (first jump > 2 psi)
_t_close_offset = None
for _i in range(1, len(_REF_TRACE_PTS)):
    if _REF_TRACE_PTS[_i]["p"] > _REF_TRACE_PTS[_i - 1]["p"] + 2.0:
        _t_close_offset = _REF_TRACE_PTS[_i]["t"] - DT
        break

if _t_close_offset is not None:
    _rt_t = np.array([pt["t"] - _t_close_offset for pt in _REF_TRACE_PTS])
    _rt_p = np.array([pt["p"]                   for pt in _REF_TRACE_PTS])
    _mask = _rt_t >= -2.0
    _rt_t, _rt_p = _rt_t[_mask], _rt_p[_mask]

    print(f"  Trace comparison: _VALVE_Valve_A (internal) vs R-THYM Valve_A")
    print(f"    R-THYM closure start detected at t_trace = {_t_close_offset:.3f} s")
    # Compare peak in aligned trace window
    _rt_peak = _rt_p[_rt_t >= 0].max() if (_rt_t >= 0).any() else float('nan')
    _moc_peak = P["_VALVE_Valve_A"].max()
    print(f"    R-THYM trace peak  : {_rt_peak:.2f} psi")
    print(f"    rthym_moc peak     : {_moc_peak:.2f} psi")
    print(f"    Difference         : {_moc_peak - _rt_peak:+.2f} psi  "
          f"({abs(_moc_peak - _rt_peak) / _rt_peak * 100:.1f} %)")
else:
    _rt_t, _rt_p = None, None
    print("  (Could not detect closure start in R-THYM trace)")

print()

# ── Plot ──────────────────────────────────────────────────────────────────────
try:
    import matplotlib.pyplot as plt

    COLORS = {
        "Junction_A":    "#4f9bd5",
        "Junction_B":    "#2ca872",
        "_VALVE_Valve_A": "#e8840c",
        "Valve_A_in":    "#e8840c",
        "Valve_A_out":   "#e03030",
        "Junction_C":    "#9b59b6",
    }
    LABELS = {
        "Junction_A":    "Junction_A pressure",
        "Junction_B":    "Junction_B pressure",
        "_VALVE_Valve_A": "Valve_A upstreamPressure (internal)",
        "Valve_A_in":    "Valve_A_in junction",
        "Valve_A_out":   "Valve_A downstreamPressure",
        "Junction_C":    "Junction_C pressure",
    }

    fig, ax = plt.subplots(figsize=(11, 5))

    for nid in NODE_IDS:
        ax.plot(t, P[nid], color=COLORS[nid], lw=1.4, label=LABELS[nid])

    ax.axhline(P_VAPOR, color="black", lw=0.9, ls="--", alpha=0.6,
               label=f"Vapour pressure ({P_VAPOR:.0f} psi)")
    ax.axvline(T_CLOSURE, color="gray", lw=0.8, ls=":", alpha=0.7,
               label=f"Valve fully closed (t = {T_CLOSURE} s)")

    # Overlay R-THYM trace (aligned to t=0 at closure start)
    if _rt_t is not None:
        ax.plot(_rt_t, _rt_p, color=COLORS["Valve_A_in"],
                lw=1.0, ls="--", alpha=0.65,
                label="Valve_A upstream — R-THYM (trace)")

    # Annotate peak
    ax.annotate(
        f"rthym_moc: {peak_up:.1f} psi\nR-THYM:    {REF_VALVE_A_UPSTREAM_PEAK_PSI:.1f} psi",
        xy=(t_peak, peak_up),
        xytext=(t_peak + 1.0, peak_up - 40),
        arrowprops=dict(arrowstyle="->", color=COLORS["Valve_A_in"]),
        color=COLORS["Valve_A_in"], fontsize=8,
    )

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Pressure (psi)")
    ax.set_title(
        "RTHYM-MOC — pipeline valve closure verification\n"
        f"(geometric closure: {PCT_INITIAL:.1f}% → 0% in {T_CLOSURE} s "
        f"[×0.75/step, Δt=0.05 s], vs R-THYM web app)"
    )
    ax.legend(loc="upper right", fontsize=8, ncol=2)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, TOTAL_TIME)

    out_png = os.path.join(os.path.dirname(__file__), "rthym_verification.png")
    plt.tight_layout()
    plt.savefig(out_png, dpi=150)
    print(f"  Plot saved to {out_png}")
    plt.show()

except ImportError:
    print("  (matplotlib not installed — skipping plot)")
