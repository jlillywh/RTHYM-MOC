"""Bergant & Simpson Adelaide column-separation rig (independent verification).

Experimental apparatus (University of Adelaide), documented in:

- Bergant & Simpson (1999), *J. Hydraul. Eng.* 125(8):835–848
- Bergant & Simpson (1995), Research Report R128, University of Adelaide
- Karadžić et al. (2014), *Stroj. vestn.* — layout and water-hammer cases
- He, Li & Guo (2025), *Processes* 13:3510 — published experimental pressure peaks
  for moderate (0.3 m/s) and severe (1.4 m/s) vaporous cavitation

Downstream ball-valve closure in ~0.009 s on a 37.23 m × 22.1 mm copper pipe
(inclined +5.6%, a ≈ 1319 m/s). Reference pressures are **laboratory measurements**,
not rthym-moc snapshots.

Full trace acquisition, grid-sensitivity notes, and contact paths for raw lab data:
see ``docs/bergant_adelaide_verification.md``.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import rthym_moc as m

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
_DATASET_DIR = _REPO_ROOT / "validation" / "datasets" / "bergant_adelaide"


def _dataset_dir() -> Path:
    if _DATASET_DIR.is_dir():
        return _DATASET_DIR
    return _HERE

# ── Published geometry (SI) ───────────────────────────────────────────────────
PIPE_LENGTH_M = 37.23
PIPE_DIAMETER_MM = 22.1
WALL_THICKNESS_MM = 1.63
WAVE_SPEED_M_S = 1319.0
SLOPE = 0.056  # Δz/L ≈ 2.03 m / 37.23 m
ELEV_DOWNSTREAM_M = SLOPE * PIPE_LENGTH_M
VALVE_CLOSURE_TIME_S = 0.009

COPPER_E_PA = 117.0e9
COPPER_HW_C = 130.0  # smooth copper; tuned with Darcy f from steady run

# Vapor at ~15 °C (Bergant lab): absolute ≈ 1.7 kPa → gage well below atm.
P_VAPOR_KPA = 1.7
P_ATM_KPA = 101.325

CASES: dict[str, str] = {
    "moderate_cavitation": "moderate_reference.json",
    "severe_cavitation": "severe_reference.json",
}

CASE_LABELS: dict[str, str] = {
    "moderate_cavitation": "Moderate cavitation (V₀ = 0.3 m/s)",
    "severe_cavitation": "Severe cavitation (V₀ = 1.4 m/s)",
}

# Digitized experimental valve trace (optional). Copy from .csv.example after WebPlotDigitizer.
SEVERE_VALVE_TRACE_CSV = _dataset_dir() / "severe_valve_trace_reference.csv"
SEVERE_VALVE_TRACE_CSV_EXAMPLE = _dataset_dir() / "severe_valve_trace_reference.csv.example"
TRACE_REQUIRED_COLUMNS = ("t_s", "p_abs_kPa")
TRACE_ALT_COLUMNS = ("t_s", "p_gauge_kPa")  # He Fig. 4: cavity drawn at 0 kPa gauge


def reference_path(case_id: str) -> Path:
    if case_id not in CASES:
        raise KeyError(f"Unknown case_id {case_id!r}; expected one of {sorted(CASES)}")
    return _dataset_dir() / CASES[case_id]


def load_reference(case_id: str) -> dict[str, Any]:
    return json.loads(reference_path(case_id).read_text())


def _m_to_ft(x: float) -> float:
    return x / 0.3048


def _mm_to_in(x: float) -> float:
    return x / 25.4


def _m3s_to_gpm(q: float) -> float:
    return q * 15850.323141


def _kpa_gauge_from_head_ft(head_ft: float, elevation_ft: float) -> float:
    """Gauge pressure (kPa) from piezometric head and node elevation (both ft)."""
    psi_g = (head_ft - elevation_ft) / m.PSI_TO_FT
    return psi_g * 6.894757


def _kpa_gauge_from_head_m(head_m: float, elevation_m: float) -> float:
    return _kpa_gauge_from_head_ft(_m_to_ft(head_m), _m_to_ft(elevation_m))


def _p_vapor_psi_gage() -> float:
    return (P_VAPOR_KPA - P_ATM_KPA) / 6.894757


def _linear_valve_schedule(closure_time_s: float, *, dt: float, n_pre: int = 5) -> list[tuple[float, float]]:
    """100% → 0% linear closure starting at t = 0 (Bergant fast ball valve)."""
    steps = max(int(closure_time_s / dt) + 1, 2)
    sched: list[tuple[float, float]] = [(0.0, 100.0)]
    for i in range(1, steps + 1):
        t = i * dt
        pct = max(0.0, 100.0 * (1.0 - t / closure_time_s))
        sched.append((t, pct))
    # Hold closed
    sched.append((sched[-1][0] + 10.0 * dt, 0.0))
    return sched


def _steady_downstream_head_m(
    upstream_head_m: float,
    velocity_m_s: float,
    *,
    length_m: float = PIPE_LENGTH_M,
    diameter_mm: float = PIPE_DIAMETER_MM,
    hw_c: float = COPPER_HW_C,
) -> float:
    """Invert steady DW head loss to find downstream tank HGL for target velocity."""
    d_ft = _mm_to_in(diameter_mm)
    l_ft = _m_to_ft(length_m)
    q_gpm = _m3s_to_gpm(velocity_m_s * np.pi * (diameter_mm * 1e-3 / 2.0) ** 2)
    hf_ft = (10.44 * l_ft * abs(q_gpm) ** 1.852) / (hw_c ** 1.852 * d_ft ** 4.871)
    hf_m = hf_ft * 0.3048
    # Uphill flow: H_up - hf = H_dn + (z_dn - z_up)
    return upstream_head_m - hf_m - ELEV_DOWNSTREAM_M


def _make_node(node_id: str, node_type: str, **kwargs: Any) -> m.NodeInput:
    node = m.NodeInput()
    node.id = node_id
    node.type = node_type
    for key, value in kwargs.items():
        setattr(node, key, value)
    return node


def _make_pipe(pipe_id: str, from_node: str, to_node: str, length_ft: float, **kwargs: Any) -> m.PipeInput:
    pipe = m.PipeInput()
    pipe.id = pipe_id
    pipe.from_node = from_node
    pipe.to_node = to_node
    pipe.length = length_ft
    for key, value in kwargs.items():
        setattr(pipe, key, value)
    return pipe


def build_bergant_solver(
    *,
    upstream_head_m: float,
    steady_velocity_m_s: float,
    downstream_head_m: float | None = None,
) -> m.MOCSolver:
    h_dn = (
        downstream_head_m
        if downstream_head_m is not None
        else _steady_downstream_head_m(upstream_head_m, steady_velocity_m_s)
    )

    solver = m.MOCSolver()
    solver.add_node(
        _make_node(
            "T_UP",
            "Tank",
            elevation=_m_to_ft(0.0),
            head=_m_to_ft(upstream_head_m),
        )
    )
    valve_head_m = h_dn  # piezometric at downstream end in steady flow
    solver.add_node(
        _make_node(
            "V_DN",
            "Valve",
            elevation=_m_to_ft(ELEV_DOWNSTREAM_M),
            diameter=_mm_to_in(PIPE_DIAMETER_MM),
            current_setting=100.0,
            head=_m_to_ft(valve_head_m),
        )
    )
    solver.add_node(
        _make_node(
            "T_DN",
            "Tank",
            elevation=_m_to_ft(ELEV_DOWNSTREAM_M),
            head=_m_to_ft(h_dn),
        )
    )

    q_gpm = _m3s_to_gpm(steady_velocity_m_s * np.pi * (PIPE_DIAMETER_MM * 1e-3 / 2.0) ** 2)
    pipe_kw = dict(
        diameter=_mm_to_in(PIPE_DIAMETER_MM),
        wall_thickness=_mm_to_in(WALL_THICKNESS_MM),
        youngs_modulus=COPPER_E_PA * 0.000145038,
        poissons_ratio=0.34,
        roughness=COPPER_HW_C,
        flow_gpm=q_gpm,
    )
    stub_len_ft = max(_m_to_ft(WAVE_SPEED_M_S * 1e-4), _m_to_ft(0.5))
    solver.add_pipe(_make_pipe("P_MAIN", "T_UP", "V_DN", _m_to_ft(PIPE_LENGTH_M), **pipe_kw))
    solver.add_pipe(
        _make_pipe(
            "P_STUB",
            "V_DN",
            "T_DN",
            stub_len_ft,
            **{**pipe_kw, "flow_gpm": 0.0},
        )
    )
    return solver


def run_bergant_case(
    reference: dict[str, Any],
    *,
    dt: float | None = None,
    total_time: float | None = None,
) -> dict:
    dt_s = float(dt if dt is not None else reference.get("solver", {}).get("dt_s", 1e-4))
    t_end = float(total_time if total_time is not None else reference.get("solver", {}).get("total_time_s", 0.8))
    v0 = float(reference["steady_velocity_m_s"])
    h_up = float(reference["upstream_head_m"])
    h_dn = float(reference.get("downstream_head_m", _steady_downstream_head_m(h_up, v0)))

    solver = build_bergant_solver(
        upstream_head_m=h_up,
        steady_velocity_m_s=v0,
        downstream_head_m=h_dn,
    )
    solver.set_valve_schedule("V_DN", _linear_valve_schedule(VALVE_CLOSURE_TIME_S, dt=dt_s))

    return solver.run(
        total_time=t_end,
        dt=dt_s,
        p_vapor_psi=_p_vapor_psi_gage(),
        cavitation_model=m.CavitationModel.DVCM,
    )


def valve_gauge_pressure_kpa(results: dict) -> tuple[np.ndarray, np.ndarray]:
    t = np.asarray(results["time"], dtype=float)
    head_ft = np.asarray(results["node_head"]["V_DN"], dtype=float)
    elev_ft = _m_to_ft(ELEV_DOWNSTREAM_M)
    p_kpa = np.array([_kpa_gauge_from_head_ft(h, elev_ft) for h in head_ft], dtype=float)
    return t, p_kpa


def _kpa_absolute_from_head_ft(head_ft: float, elevation_ft: float) -> float:
    return _kpa_gauge_from_head_ft(head_ft, elevation_ft) + P_ATM_KPA


def valve_absolute_pressure_kpa(results: dict) -> tuple[np.ndarray, np.ndarray]:
    t, p_g = valve_gauge_pressure_kpa(results)
    return t, p_g + P_ATM_KPA


def midpoint_gauge_pressure_kpa(results: dict) -> tuple[np.ndarray, np.ndarray]:
    t = np.asarray(results["time"], dtype=float)
    head_v_ft = np.asarray(results["node_head"]["V_DN"], dtype=float)
    head_up_ft = np.asarray(results["node_head"]["T_UP"], dtype=float)
    z_mid_ft = _m_to_ft(ELEV_DOWNSTREAM_M / 2.0)
    h_mid_ft = head_up_ft * 0.5 + head_v_ft * 0.5
    p_kpa = np.array([_kpa_gauge_from_head_ft(h, z_mid_ft) for h in h_mid_ft], dtype=float)
    return t, p_kpa


def _skip_startup(t: np.ndarray, p_kpa: np.ndarray, *, t_min_s: float) -> tuple[np.ndarray, np.ndarray]:
    mask = t >= t_min_s
    return t[mask], p_kpa[mask]


def _max_absolute_peak(
    t: np.ndarray,
    p_abs_kpa: np.ndarray,
    *,
    t_min_s: float,
) -> tuple[float, float]:
    t_w, p_w = _skip_startup(t, p_abs_kpa, t_min_s=t_min_s)
    if len(p_w) == 0:
        return float("nan"), float("nan")
    i = int(np.argmax(p_w))
    return float(t_w[i]), float(p_w[i])


def _second_peak_after_cavity(
    t: np.ndarray,
    p_abs_kpa: np.ndarray,
    *,
    t_min_s: float,
) -> tuple[float, float]:
    """Collapse rebound peak after the deepest cavity pressure (Fu et al. 2025 Fig. 4)."""
    t_w, p_w = _skip_startup(t, p_abs_kpa, t_min_s=t_min_s)
    if len(p_w) < 3:
        return float("nan"), float("nan")
    i_min = int(np.argmin(p_w))
    sub_t = t_w[i_min:]
    sub_p = p_w[i_min:]
    i_peak = int(np.argmax(sub_p))
    return float(sub_t[i_peak]), float(sub_p[i_peak])


@dataclass(frozen=True)
class BergantCaseMetrics:
    case_id: str
    peak_metric: str
    sim_peak_kpa: float
    sim_peak_time_s: float
    exp_peak_kpa: float
    peak_rel_err: float
    passed_peak: bool
    min_gauge_kpa: float
    passed_cavity: bool
    passed: bool


def evaluate_bergant_case(case_id: str, results: dict, reference: dict[str, Any]) -> BergantCaseMetrics:
    t, p_abs = valve_absolute_pressure_kpa(results)
    _, p_gauge = valve_gauge_pressure_kpa(results)

    exp = reference["experimental_valve_kPa"]
    peak_metric = reference.get("peak_metric", "maximum_absolute_kPa")
    tol = reference.get("tolerances", {})
    t_min = float(reference.get("analysis", {}).get("ignore_before_s", 0.02))

    if peak_metric == "second_peak_after_cavity_absolute_kPa":
        exp_peak = float(exp["second_peak_kPa"])
        tol_rel = float(tol.get("second_peak_rel", 0.15))
        peak_t, peak_p = _second_peak_after_cavity(t, p_abs, t_min_s=t_min)
    else:
        exp_peak = float(exp["maximum_peak_kPa"])
        tol_rel = float(tol.get("maximum_peak_rel", 0.15))
        peak_t, peak_p = _max_absolute_peak(t, p_abs, t_min_s=t_min)

    peak_rel = abs(peak_p - exp_peak) / max(abs(exp_peak), 1.0)
    passed_peak = peak_rel <= tol_rel

    min_gauge = float(np.min(p_gauge))
    require_cavity = bool(reference.get("analysis", {}).get("require_cavity", True))
    min_required = float(reference.get("analysis", {}).get("min_gauge_kpa_for_cavity", -50.0))
    passed_cavity = (min_gauge <= min_required) if require_cavity else True

    return BergantCaseMetrics(
        case_id=case_id,
        peak_metric=peak_metric,
        sim_peak_kpa=peak_p,
        sim_peak_time_s=peak_t,
        exp_peak_kpa=exp_peak,
        peak_rel_err=peak_rel,
        passed_peak=passed_peak,
        min_gauge_kpa=min_gauge,
        passed_cavity=passed_cavity,
        passed=passed_peak and passed_cavity,
    )


def run_and_evaluate(case_id: str) -> tuple[dict, dict[str, Any], BergantCaseMetrics]:
    ref = load_reference(case_id)
    res = run_bergant_case(ref)
    metrics = evaluate_bergant_case(case_id, res, ref)
    return res, ref, metrics


def valve_trace_csv_path(case_id: str) -> Path | None:
    """Return the optional digitized trace path for ``case_id``, if configured."""
    ref = load_reference(case_id)
    name = ref.get("trace_artifact")
    if not name:
        return None
    path = _HERE / str(name)
    return path


def valve_trace_csv_exists(case_id: str) -> bool:
    path = valve_trace_csv_path(case_id)
    return path is not None and path.is_file()


def _parse_trace_comment(line: str) -> dict[str, str]:
    """Parse ``# key: value`` metadata lines at the top of a trace CSV."""
    body = line.strip()
    if not body.startswith("#"):
        return {}
    body = body.lstrip("#").strip()
    if ":" not in body:
        return {}
    key, value = body.split(":", 1)
    return {key.strip(): value.strip()}


def _trace_pressure_unit(metadata: dict[str, str], reference: dict[str, Any]) -> str:
    """Return ``gauge`` or ``absolute`` for trace–simulation comparison."""
    cfg = reference.get("trace_comparison", {})
    unit = metadata.get("pressure_unit") or cfg.get("pressure_compare", "gauge")
    unit = unit.lower().replace(" ", "_")
    if unit in ("gauge", "gauge_kpa", "gauge_as_plotted", "gage"):
        return "gauge"
    return "absolute"


def _align_trace_pressures(
    trace: dict[str, Any],
    reference: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, str]:
    """Return (t, p, unit) for experimental pressures in the comparison unit."""
    unit = _trace_pressure_unit(trace.get("metadata", {}), reference)
    t = trace["t_s"]
    if unit == "gauge":
        return t, trace["p_gauge_kPa"], unit
    return t, trace["p_abs_kPa"], unit


def load_valve_trace_csv(path: Path) -> dict[str, Any]:
    """Load digitized experimental valve pressure from ``path``.

    Expected format: see ``bergant_adelaide_severe_valve_trace_reference.csv.example``.
    """
    if not path.is_file():
        raise FileNotFoundError(path)

    metadata: dict[str, str] = {}
    rows: list[dict[str, str]] = []
    header: list[str] | None = None
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        for raw in reader:
            if not raw or all(not cell.strip() for cell in raw):
                continue
            if raw[0].strip().startswith("#"):
                metadata.update(_parse_trace_comment(raw[0]))
                continue
            if header is None:
                header = [cell.strip() for cell in raw]
                has_abs = all(c in header for c in TRACE_REQUIRED_COLUMNS)
                has_gauge = all(c in header for c in TRACE_ALT_COLUMNS)
                if not has_abs and not has_gauge:
                    raise ValueError(
                        f"{path.name}: need columns {TRACE_REQUIRED_COLUMNS} or {TRACE_ALT_COLUMNS}; got {header}"
                    )
                continue
            rows.append(dict(zip(header, raw)))

    if not rows:
        raise ValueError(f"{path.name}: no data rows")

    if header is None:
        raise ValueError(f"{path.name}: no header row")

    t = np.array([float(r["t_s"]) for r in rows], dtype=float)
    if "p_gauge_kPa" in header:
        p_gauge = np.array([float(r["p_gauge_kPa"]) for r in rows], dtype=float)
        p_abs = p_gauge + P_ATM_KPA
    else:
        p_abs = np.array([float(r["p_abs_kPa"]) for r in rows], dtype=float)
        p_gauge = p_abs - P_ATM_KPA
    order = np.argsort(t)
    t = t[order]
    p_abs = p_abs[order]
    p_gauge = p_gauge[order]
    if np.any(np.diff(t) <= 0):
        # Pen extraction can yield duplicate timestamps; average pressures at the same t.
        buckets: dict[float, list[float]] = {}
        for ti, pi in zip(t, p_abs):
            buckets.setdefault(float(ti), []).append(float(pi))
        keys = sorted(buckets)
        t = np.array(keys, dtype=float)
        p_abs = np.array([float(np.mean(buckets[k])) for k in keys], dtype=float)
        p_gauge = p_abs - P_ATM_KPA
    if np.any(np.diff(t) <= 0):
        raise ValueError(f"{path.name}: t_s must be strictly increasing")

    return {
        "metadata": metadata,
        "t_s": t,
        "p_abs_kPa": p_abs,
        "p_gauge_kPa": p_gauge,
        "path": path,
    }


def validate_valve_trace_csv(path: Path, *, min_points: int = 40) -> list[str]:
    """Return a list of validation errors (empty if the file is usable)."""
    errors: list[str] = []
    try:
        data = load_valve_trace_csv(path)
    except (OSError, ValueError) as exc:
        return [str(exc)]

    t = data["t_s"]
    p_g = data["p_gauge_kPa"]
    if len(t) < min_points:
        errors.append(f"expected at least {min_points} points, got {len(t)}")
    if float(np.min(p_g)) < -500.0 or float(np.max(p_g)) > 3000.0:
        errors.append(
            f"p_gauge_kPa outside plausible range -500–3000 kPa: [{p_g.min():.1f}, {p_g.max():.1f}]"
        )
    span = float(t[-1] - t[0])
    if span < 0.05:
        errors.append(f"time span {span:.4f} s is very short; check axis calibration")
    return errors


@dataclass(frozen=True)
class BergantTraceMetrics:
    case_id: str
    pressure_unit: str
    n_points: int
    t_start_s: float
    t_end_s: float
    rms_kpa: float
    max_abs_kpa: float
    rms_limit_kpa: float
    max_abs_limit_kpa: float
    exp_peak_gauge_kpa: float
    sim_peak_gauge_kpa: float
    peak_window_label: str
    peak_rel_err: float
    peak_rel_limit: float
    passed_peak: bool
    passed_rms: bool
    passed: bool


def _trace_comparison_mask(
    t_ref: np.ndarray,
    p_ref: np.ndarray,
    cfg: dict[str, Any],
) -> np.ndarray:
    """Build boolean mask for points used in RMS (windows, optional cavity exclusion)."""
    windows = cfg.get("trace_windows")
    if windows:
        mask = np.zeros_like(t_ref, dtype=bool)
        for win in windows:
            t0 = float(win["t_start_s"])
            t1 = float(win["t_end_s"])
            mask |= (t_ref >= t0) & (t_ref <= t1)
    else:
        t0 = float(cfg.get("t_start_s", 0.02))
        t1 = float(cfg.get("t_end_s", 0.5))
        mask = (t_ref >= t0) & (t_ref <= t1)

    floor = cfg.get("exclude_below_gauge_kpa")
    if floor is not None:
        mask &= p_ref >= float(floor)
    return mask


def evaluate_bergant_valve_trace(
    case_id: str,
    results: dict,
    reference: dict[str, Any],
    trace: dict[str, Any],
) -> BergantTraceMetrics:
    cfg = reference.get("trace_comparison", {})
    rms_limit = float(cfg.get("rms_kpa_max", 180.0))
    max_limit = float(cfg.get("max_abs_kpa", 350.0))

    t_ref, p_ref, unit = _align_trace_pressures(trace, reference)
    mask = _trace_comparison_mask(t_ref, p_ref, cfg)
    t_w = t_ref[mask]
    p_w = p_ref[mask]
    if len(t_w) < 5:
        raise ValueError("Fewer than 5 trace points in comparison mask; widen trace_windows")

    if unit == "gauge":
        t_sim, p_sim = valve_gauge_pressure_kpa(results)
    else:
        t_sim, p_sim = valve_absolute_pressure_kpa(results)

    p_on_ref = np.interp(t_w, t_sim, p_sim)
    err = p_on_ref - p_w
    rms = float(np.sqrt(np.mean(err**2)))
    max_abs = float(np.max(np.abs(err)))

    t0 = float(np.min(t_w))
    t1 = float(np.max(t_w))

    # Peak comparison on the primary rebound window (Fig. 4 second surge).
    peak_windows = cfg.get("peak_windows") or [{"t_start_s": 0.33, "t_end_s": 0.47, "label": "second_rebound"}]
    primary = peak_windows[0]
    pt0 = float(primary["t_start_s"])
    pt1 = float(primary["t_end_s"])
    peak_label = str(primary.get("label", "primary"))
    m_exp = (t_ref >= pt0) & (t_ref <= pt1)
    m_sim = (t_sim >= pt0) & (t_sim <= pt1)
    exp_peak = float(np.max(p_ref[m_exp])) if np.any(m_exp) else float("nan")
    sim_peak = float(np.max(p_sim[m_sim])) if np.any(m_sim) else float("nan")
    peak_rel = abs(sim_peak - exp_peak) / max(abs(exp_peak), 1.0)
    peak_rel_limit = float(cfg.get("peak_rel_limit", 0.40))
    passed_peak = peak_rel <= peak_rel_limit
    passed_rms = rms <= rms_limit and max_abs <= max_limit

    return BergantTraceMetrics(
        case_id=case_id,
        pressure_unit=unit,
        n_points=int(len(t_w)),
        t_start_s=t0,
        t_end_s=t1,
        rms_kpa=rms,
        max_abs_kpa=max_abs,
        rms_limit_kpa=rms_limit,
        max_abs_limit_kpa=max_limit,
        exp_peak_gauge_kpa=exp_peak,
        sim_peak_gauge_kpa=sim_peak,
        peak_window_label=peak_label,
        peak_rel_err=peak_rel,
        peak_rel_limit=peak_rel_limit,
        passed_peak=passed_peak,
        passed_rms=passed_rms,
        passed=passed_peak,
    )


def run_and_evaluate_trace(case_id: str) -> tuple[dict, dict[str, Any], dict[str, Any], BergantTraceMetrics]:
    ref = load_reference(case_id)
    path = valve_trace_csv_path(case_id)
    if path is None:
        raise FileNotFoundError(f"No trace_artifact configured for {case_id!r}")
    trace = load_valve_trace_csv(path)
    res = run_bergant_case(ref)
    metrics = evaluate_bergant_valve_trace(case_id, res, ref, trace)
    return res, ref, trace, metrics
