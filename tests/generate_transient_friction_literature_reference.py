"""Generate archived reference metrics for transient friction literature cross-check."""
import json
import math
from pathlib import Path

import numpy as np
import rthym_moc as m

GPM_TO_CFS = 0.002228
G_US = 32.2

# Wave reflection case (examples/test_wave_reflections.py / Wylie & Streeter Ch. 9)
WAVE = dict(
    h_res_ft=300.0,
    l_ft=3000.0,
    d_in=12.0,
    hw_c=130.0,
    q0_gpm=500.0,
    a_wave_ft=4000.0,
    dt_s=0.01,
    total_s=9.0,
)


def hf_hw_ft(q_gpm, l_ft, d_in, hw_c):
    return (10.44 * l_ft * (q_gpm ** 1.852)) / ((hw_c ** 1.852) * (d_in ** 4.871))


def find_plateau_peaks(head_ft, time_s, threshold_h):
    """One peak per positive plateau (examples/test_wave_reflections.py)."""
    peaks: list[tuple[float, float]] = []
    in_seg = False
    seg_max_h = -np.inf
    seg_max_idx = -1
    for i, h in enumerate(head_ft):
        if h > threshold_h:
            if not in_seg:
                in_seg = True
            if h > seg_max_h:
                seg_max_h = float(h)
                seg_max_idx = i
        else:
            if in_seg and seg_max_idx >= 0:
                peaks.append((float(time_s[seg_max_idx]), seg_max_h))
                in_seg = False
                seg_max_h = -np.inf
                seg_max_idx = -1
    if in_seg and seg_max_idx >= 0:
        peaks.append((float(time_s[seg_max_idx]), seg_max_h))
    return peaks


def run_wave_reflection(*, friction_model: m.TransientFrictionModel | None = None, usf_tau: float | None = None):
    v0 = WAVE["q0_gpm"] * GPM_TO_CFS / (math.pi * ((WAVE["d_in"] / 12.0) / 2.0) ** 2)
    hf = hf_hw_ft(WAVE["q0_gpm"], WAVE["l_ft"], WAVE["d_in"], WAVE["hw_c"])
    h_dn = WAVE["h_res_ft"] - hf
    dh_j = WAVE["a_wave_ft"] * v0 / G_US
    threshold = h_dn + 0.4 * dh_j
    solver = m.MOCSolver()
    r1 = m.NodeInput()
    r1.id = "R1"
    r1.type = "PressureBoundary"
    r1.head = WAVE["h_res_ft"]
    de = m.NodeInput()
    de.id = "DE"
    de.type = "Junction"
    de.demand = 0.0
    de.head = h_dn
    p1 = m.PipeInput()
    p1.id = "P1"
    p1.from_node = "R1"
    p1.to_node = "DE"
    p1.length = WAVE["l_ft"]
    p1.diameter = WAVE["d_in"]
    p1.roughness = WAVE["hw_c"]
    p1.flow_gpm = WAVE["q0_gpm"]
    solver.add_node(r1)
    solver.add_node(de)
    solver.add_pipe(p1)
    run_kw: dict = {}
    if friction_model is not None:
        run_kw["friction_model"] = friction_model
    if usf_tau is not None:
        run_kw["usf_tau"] = usf_tau
    res = solver.run(WAVE["total_s"], WAVE["dt_s"], -14.0, **run_kw)
    t = np.asarray(res["time"], dtype=float)
    h = np.asarray(res["node_head"]["DE"], dtype=float)
    peaks = find_plateau_peaks(h, t, threshold)
    periods = [peaks[i + 1][0] - peaks[i][0] for i in range(len(peaks) - 1)]
    decays = [peaks[i][1] - peaks[i + 1][1] for i in range(len(peaks) - 1)]
    peak_heads = [p[1] for p in peaks]
    total_decay = peak_heads[0] - peak_heads[-1] if len(peak_heads) >= 2 else 0.0
    return dict(
        hf_hw_ft=hf,
        two_hf_ft=2.0 * hf,
        threshold_ft=threshold,
        peak_heads_ft=peak_heads,
        peak_times_s=[p[0] for p in peaks],
        period_s=periods,
        mean_period_s=float(np.mean(periods)) if periods else None,
        peak_decays_ft=decays,
        mean_decay_ft=float(np.mean(decays)) if decays else None,
        total_peak_decay_ft=total_decay,
    )


def run_lp07():
    from test_transient_friction_model import (
        _LONG_PIPE_PERIOD_S,
        _period_peak_envelope,
        _run_long_pipe_friction_case,
    )

    res_q = _run_long_pipe_friction_case(m.TransientFrictionModel.QuasiSteady)
    res_v = _run_long_pipe_friction_case(m.TransientFrictionModel.Vitkovsky)
    mid = len(res_q["pipe_profile_chainage_ft"]["P1"]) // 2
    mid_h_q = np.asarray(res_q["pipe_profile_head"]["P1"][:, mid], dtype=float)
    mid_h_v = np.asarray(res_v["pipe_profile_head"]["P1"][:, mid], dtype=float)
    _, env_q = _period_peak_envelope(res_q["time"], mid_h_q, _LONG_PIPE_PERIOD_S)
    _, env_v = _period_peak_envelope(res_v["time"], mid_h_v, _LONG_PIPE_PERIOD_S)
    return dict(
        mid_chainage_ft=float(res_q["pipe_profile_chainage_ft"]["P1"][mid]),
        quasi_envelope_ft=env_q,
        vit_envelope_ft=env_v,
        quasi_late_mean_ft=float(np.mean(env_q[-3:])),
        vit_late_mean_ft=float(np.mean(env_v[-3:])),
        quasi_decay_ratio=env_q[-1] / env_q[0],
        vit_decay_ratio=env_v[-1] / env_v[0],
    )


if __name__ == "__main__":
    # Match examples/test_wave_reflections.py: USF disabled via usf_tau = dt.
    steady = run_wave_reflection(usf_tau=WAVE["dt_s"])
    vit = run_wave_reflection(friction_model=m.TransientFrictionModel.Vitkovsky)
    lp07 = run_lp07()
    out = {
        "case_id": "transient-friction-literature",
        "sources": [
            {
                "citation": "Wylie, E.B. and Streeter, V.L. (1993). Fluid Transients in Systems.",
                "use": "Steady-friction peak envelope decay ~2·Hf per wave round-trip on reservoir–pipe–dead-end reflections.",
            },
            {
                "citation": "Vitkovsky, J.P. et al. (2006). Systematic Evaluation of One-Dimensional Unsteady Friction Models in Simple Pipelines. J. Hydraul. Eng. 132(7):696–708.",
                "use": "Unsteady friction (IAB/Vitkovsky) provides greater peak attenuation than quasi-steady friction on simple pipeline transients.",
            },
            {
                "citation": "Bergant, A., Simpson, A.R., Vitkovsky, J.P. (2001). Developments in unsteady pipe flow friction modelling. J. Hydraul. Res. 39(3):249–257.",
                "use": "Compares quasi-steady, Zielke, and Brunone models against laboratory water-hammer data.",
            },
        ],
        "wave_reflection_steady": {
            "parameters": WAVE,
            "run": {"usf_tau_s": WAVE["dt_s"], "note": "Same as examples/test_wave_reflections.py (USF disabled)."},
            "expected_mean_period_s": 4.0 * WAVE["l_ft"] / WAVE["a_wave_ft"],
            "expected_mean_decay_ft": steady["two_hf_ft"],
            "tolerances": {
                "period_rel": 0.02,
                "decay_rel": 0.35,
                "min_peaks": 3,
            },
            "archived": steady,
        },
        "wave_reflection_vitkovsky": {
            "archived": vit,
            "directional": "total_peak_decay_ft >= steady_total_peak_decay_ft",
        },
        "lp07_long_pipe": {
            "directional": "vit_late_mean_ft < quasi_late_mean_ft",
            "tolerances": {
                "min_envelope_buckets": 6,
                "min_late_advantage_ft": 5.0,
            },
            "archived": lp07,
        },
    }
    path = Path(__file__).resolve().parent / "transient_friction_literature_reference.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    print("wrote", path)
    print("steady decay", steady["mean_decay_ft"], "2Hf", steady["two_hf_ft"])
    print("lp07 quasi late", lp07["quasi_late_mean_ft"], "vit", lp07["vit_late_mean_ft"])
