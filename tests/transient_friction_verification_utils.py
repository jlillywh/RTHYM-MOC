"""Literature / archived-reference helpers for Phase 6 transient friction checks."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import rthym_moc as m

_HERE = Path(__file__).resolve().parent
_REFERENCE_JSON = _HERE / "transient_friction_literature_reference.json"
GPM_TO_CFS = 0.002228
G_US = 32.2


def load_transient_friction_literature_reference() -> dict[str, Any]:
    return json.loads(_REFERENCE_JSON.read_text())


def hf_hw_ft(*, q_gpm: float, l_ft: float, d_in: float, hw_c: float) -> float:
    return (10.44 * l_ft * (q_gpm ** 1.852)) / ((hw_c ** 1.852) * (d_in ** 4.871))


def find_plateau_peaks(
    head_ft: np.ndarray | list[float],
    time_s: np.ndarray | list[float],
    threshold_h: float,
) -> list[tuple[float, float]]:
    """Return (time_s, head_ft) for each positive plateau maximum."""
    peaks: list[tuple[float, float]] = []
    in_seg = False
    seg_max_h = -np.inf
    seg_max_idx = -1
    t = np.asarray(time_s, dtype=float)
    h = np.asarray(head_ft, dtype=float)
    for i, value in enumerate(h):
        if value > threshold_h:
            if not in_seg:
                in_seg = True
            if value > seg_max_h:
                seg_max_h = float(value)
                seg_max_idx = i
        else:
            if in_seg and seg_max_idx >= 0:
                peaks.append((float(t[seg_max_idx]), seg_max_h))
                in_seg = False
                seg_max_h = -np.inf
                seg_max_idx = -1
    if in_seg and seg_max_idx >= 0:
        peaks.append((float(t[seg_max_idx]), seg_max_h))
    return peaks


@dataclass(frozen=True)
class WaveReflectionMetrics:
    peak_heads_ft: list[float]
    peak_times_s: list[float]
    mean_period_s: float
    mean_decay_ft: float
    total_peak_decay_ft: float
    two_hf_ft: float


def run_wave_reflection_case(
    *,
    friction_model: m.TransientFrictionModel | None = None,
    usf_tau: float | None = None,
) -> WaveReflectionMetrics:
    """Reservoir–pipe–dead-end reflections (``examples/test_wave_reflections.py``)."""
    ref = load_transient_friction_literature_reference()
    params = ref["wave_reflection_steady"]["parameters"]
    q_gpm = float(params["q0_gpm"])
    l_ft = float(params["l_ft"])
    d_in = float(params["d_in"])
    hw_c = float(params["hw_c"])
    h_res = float(params["h_res_ft"])
    a_wave = float(params["a_wave_ft"])
    dt_s = float(params["dt_s"])
    total_s = float(params["total_s"])

    v0 = q_gpm * GPM_TO_CFS / (math.pi * ((d_in / 12.0) / 2.0) ** 2)
    hf = hf_hw_ft(q_gpm=q_gpm, l_ft=l_ft, d_in=d_in, hw_c=hw_c)
    h_dn = h_res - hf
    threshold = h_dn + 0.4 * (a_wave * v0 / G_US)

    solver = m.MOCSolver()
    r1 = m.NodeInput()
    r1.id = "R1"
    r1.type = "PressureBoundary"
    r1.head = h_res
    de = m.NodeInput()
    de.id = "DE"
    de.type = "Junction"
    de.demand = 0.0
    de.head = h_dn
    pipe = m.PipeInput()
    pipe.id = "P1"
    pipe.from_node = "R1"
    pipe.to_node = "DE"
    pipe.length = l_ft
    pipe.diameter = d_in
    pipe.roughness = hw_c
    pipe.flow_gpm = q_gpm
    solver.add_node(r1)
    solver.add_node(de)
    solver.add_pipe(pipe)

    run_kw: dict[str, Any] = {}
    if friction_model is not None:
        run_kw["friction_model"] = friction_model
    if usf_tau is not None:
        run_kw["usf_tau"] = usf_tau
    res = solver.run(total_s, dt_s, -14.0, **run_kw)

    peaks = find_plateau_peaks(res["node_head"]["DE"], res["time"], threshold)
    peak_heads = [p[1] for p in peaks]
    peak_times = [p[0] for p in peaks]
    periods = [peak_times[i + 1] - peak_times[i] for i in range(len(peak_times) - 1)]
    decays = [peak_heads[i] - peak_heads[i + 1] for i in range(len(peak_heads) - 1)]
    total_decay = peak_heads[0] - peak_heads[-1] if len(peak_heads) >= 2 else 0.0
    return WaveReflectionMetrics(
        peak_heads_ft=peak_heads,
        peak_times_s=peak_times,
        mean_period_s=float(np.mean(periods)) if periods else float("nan"),
        mean_decay_ft=float(np.mean(decays)) if decays else float("nan"),
        total_peak_decay_ft=total_decay,
        two_hf_ft=2.0 * hf,
    )


@dataclass(frozen=True)
class Lp07EnvelopeMetrics:
    quasi_envelope_ft: list[float]
    vit_envelope_ft: list[float]
    quasi_late_mean_ft: float
    vit_late_mean_ft: float
    quasi_decay_ratio: float
    vit_decay_ratio: float


def run_lp07_envelope_case() -> Lp07EnvelopeMetrics:
    from test_transient_friction_model import (
        _LONG_PIPE_PERIOD_S,
        _period_peak_envelope,
        _run_long_pipe_friction_case,
    )

    res_quasi = _run_long_pipe_friction_case(m.TransientFrictionModel.QuasiSteady)
    res_vit = _run_long_pipe_friction_case(m.TransientFrictionModel.Vitkovsky)
    mid = len(res_quasi["pipe_profile_chainage_ft"]["P1"]) // 2
    mid_h_q = np.asarray(res_quasi["pipe_profile_head"]["P1"][:, mid], dtype=float)
    mid_h_v = np.asarray(res_vit["pipe_profile_head"]["P1"][:, mid], dtype=float)
    _, env_q = _period_peak_envelope(res_quasi["time"], mid_h_q, _LONG_PIPE_PERIOD_S)
    _, env_v = _period_peak_envelope(res_vit["time"], mid_h_v, _LONG_PIPE_PERIOD_S)
    return Lp07EnvelopeMetrics(
        quasi_envelope_ft=env_q,
        vit_envelope_ft=env_v,
        quasi_late_mean_ft=float(np.mean(env_q[-3:])),
        vit_late_mean_ft=float(np.mean(env_v[-3:])),
        quasi_decay_ratio=env_q[-1] / env_q[0],
        vit_decay_ratio=env_v[-1] / env_v[0],
    )
