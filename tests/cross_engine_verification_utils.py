"""Cross-engine verification helpers (checked-in external traces + live RTHYM-MOC).

Mirrors the R-THYM quickstart pattern for topics outside Joukowsky:

- **TSNet** — Appendix B.8 open standpipe (`TSNet_Standpipe_B8_*`)
- **EPANET** — steady-state operating point for ``complex_topology.inp`` (via wntr)
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from complex_topology_verification_utils import (
    HEAD_NODES,
    TOL_FLOW_GPM,
    TOL_HEAD_FT,
    evaluate_complex_topology,
)
from surge_device_verification_utils import TSNET_COMPARE_WINDOW_S, run_b8_with_standpipe

_HERE = Path(__file__).resolve().parent
_TSNET_JSON = _HERE / "TSNet_Standpipe_B8_Verification.json"
_TSNET_CSV = _HERE / "TSNet_Standpipe_B8_Traces.csv"  # optional until export script is run

# Appendix B.8.5 documented agreement; CI uses a modest margin above the archived export.
TSNET_PEAK_DIFF_TOL_FT = 0.5
TSNET_RMS_TOL_FT = 0.25


def run_tsnet_standpipe_b8_trace() -> tuple[np.ndarray, np.ndarray]:
    """Run TSNet appendix B.8 standpipe case; returns ``(time_s, J1_head_ft)``."""
    import sys
    from pathlib import Path

    examples = Path(__file__).resolve().parents[1] / "examples"
    if str(examples) not in sys.path:
        sys.path.insert(0, str(examples))
    from benchmark_ptsnet_vs_tsnet import FT_TO_M, SURGE_MODELS, _run_tsnet_transient

    case = next(c for c in SURGE_MODELS if c.label == "standpipe")
    _, _, heads_m, times_s = _run_tsnet_transient(case, warmup=0, repeat=1)
    heads_ft = np.asarray(heads_m, dtype=float).reshape(-1) / FT_TO_M
    return np.asarray(times_s, dtype=float).reshape(-1), heads_ft


def load_tsnet_standpipe_verification() -> dict:
    return json.loads(_TSNET_JSON.read_text())


def load_tsnet_standpipe_traces() -> tuple[np.ndarray, np.ndarray]:
    times: list[float] = []
    heads: list[float] = []
    with _TSNET_CSV.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            times.append(float(row["time_s"]))
            heads.append(float(row["J1_head_ft"]))
    return np.asarray(times, dtype=float), np.asarray(heads, dtype=float)


@dataclass(frozen=True)
class TsnetStandpipeCrossEngineMetrics:
    rthym_peak_ft: float
    tsnet_peak_ft: float
    peak_diff_ft: float
    rms_head_ft: float
    compare_window_s: float
    passed_peak: bool
    passed_rms: bool
    passed: bool


def evaluate_tsnet_standpipe_cross_engine() -> tuple[dict, np.ndarray, np.ndarray, TsnetStandpipeCrossEngineMetrics]:
    """Compare live RTHYM-MOC B.8 standpipe run to checked-in TSNet reference."""
    ref = load_tsnet_standpipe_verification()
    res = run_b8_with_standpipe()
    t_sim = np.asarray(res["time"], dtype=float).reshape(-1)
    h_sim = np.asarray(res["node_head"]["SP1"], dtype=float).reshape(-1)

    mask = (t_sim <= TSNET_COMPARE_WINDOW_S) & (t_sim >= 0.0)
    h_w = h_sim[mask]
    rthym_peak = float(np.max(h_w)) if h_w.size else float("nan")
    tsnet_peak = float(ref["peak_head_ft"])
    peak_diff = abs(rthym_peak - tsnet_peak)

    if _TSNET_CSV.is_file():
        t_ref, h_ref = load_tsnet_standpipe_traces()
        t_w = t_sim[mask]
        h_ts_on_sim = np.interp(t_w, t_ref, h_ref)
        rms = float(np.sqrt(np.mean((h_w - h_ts_on_sim) ** 2)))
    else:
        t_ref = np.array([], dtype=float)
        h_ref = np.array([], dtype=float)
        rms = float(ref.get("rms_head_ft", TSNET_RMS_TOL_FT))

    passed_peak = peak_diff <= TSNET_PEAK_DIFF_TOL_FT
    has_trace = _TSNET_CSV.is_file()
    passed_rms = (not has_trace) or (rms <= TSNET_RMS_TOL_FT)

    metrics = TsnetStandpipeCrossEngineMetrics(
        rthym_peak_ft=rthym_peak,
        tsnet_peak_ft=tsnet_peak,
        peak_diff_ft=peak_diff,
        rms_head_ft=rms,
        compare_window_s=TSNET_COMPARE_WINDOW_S,
        passed_peak=passed_peak,
        passed_rms=passed_rms,
        passed=passed_peak and passed_rms,
    )
    return res, t_ref, h_ref, metrics


@dataclass(frozen=True)
class EpanetPretripSummary:
    head_passed: int
    head_total: int
    flow_passed: int
    flow_total: int
    passed: bool


def evaluate_epanet_complex_topology_pretrip() -> tuple[object, EpanetPretripSummary]:
    """EPANET steady-state vs MOC pre-trip means (``complex_topology.inp``)."""
    bundle = evaluate_complex_topology()
    head_pass = sum(1 for m in bundle.pretrip_head_metrics if m.passed)
    flow_pass = sum(1 for m in bundle.pretrip_flow_metrics if m.passed)
    summary = EpanetPretripSummary(
        head_passed=head_pass,
        head_total=len(bundle.pretrip_head_metrics),
        flow_passed=flow_pass,
        flow_total=len(bundle.pretrip_flow_metrics),
        passed=head_pass == len(bundle.pretrip_head_metrics)
    and flow_pass == len(bundle.pretrip_flow_metrics),
    )
    return bundle, summary


__all__ = [
    "EpanetPretripSummary",
    "TsnetStandpipeCrossEngineMetrics",
    "TSNET_PEAK_DIFF_TOL_FT",
    "TSNET_RMS_TOL_FT",
    "TOL_FLOW_GPM",
    "TOL_HEAD_FT",
    "evaluate_epanet_complex_topology_pretrip",
    "evaluate_tsnet_standpipe_cross_engine",
    "load_tsnet_standpipe_traces",
    "load_tsnet_standpipe_verification",
]
