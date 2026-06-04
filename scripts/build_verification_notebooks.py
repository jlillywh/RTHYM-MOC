#!/usr/bin/env python3
"""Regenerate Binder verification notebooks from templates (dev helper)."""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EX = REPO / "examples"

SETUP = '''import matplotlib.pyplot as plt
import numpy as np
import rthym_moc
from _verification_notebook_setup import bootstrap_verification_notebook

REPO_ROOT, TESTS_DIR = bootstrap_verification_notebook()
print(f"Repository root: {REPO_ROOT}")
print(f"rthym_moc: {getattr(rthym_moc, '__version__', 'unknown')}")'''

SETUP_INP = '''import matplotlib.pyplot as plt
import numpy as np
import rthym_moc
from _verification_notebook_setup import bootstrap_verification_notebook

REPO_ROOT, TESTS_DIR = bootstrap_verification_notebook(require_wntr=True)
print(f"Repository root: {REPO_ROOT}")
print(f"rthym_moc: {getattr(rthym_moc, '__version__', 'unknown')}")'''


def nb(cells: list[dict]) -> dict:
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3 (ipykernel)", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.12.0"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": [text]}


def code(text: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "outputs": [], "execution_count": None, "source": [text]}


def write(name: str, cells: list[dict]) -> None:
    path = EX / name
    path.write_text(json.dumps(nb(cells), indent=1) + "\n")
    print(f"wrote {path}")


write(
    "long_pipe_valve_verification.ipynb",
    [
        md(
            "# Long Pipe Valve — R-THYM Cross-Engine Verification\n\n"
            "Mirrors **`tests/test_long_pipe_valve.py`** and Appendix B.1–B.5: five-pipe equal-percentage "
            "closure vs `tests/R-THYM_MOC_Verification.json` and `tests/R-THYM_MOC_Traces.csv`.\n\n"
            "> **Runtime:** full re-simulation is ~2–3 minutes (warmup + 232 s transient). Set `RUN_SIMULATION = False` "
            "to plot reference traces only.\n\n"
            "[![Launch Binder](https://mybinder.org/badge_logo.svg)]"
            "(https://mybinder.org/v2/gh/jlillywh/RTHYM-MOC/main?labpath=examples%2Flong_pipe_valve_verification.ipynb)"
        ),
        md("## 1. Setup"),
        code(SETUP),
        md("## 2. Run (optional) and metrics"),
        code(
            "from long_pipe_valve_verification_utils import (\n"
            "    TRACE_PSI_TOL_RMS,\n"
            "    load_reference,\n"
            "    run_and_evaluate_long_pipe,\n"
            ")\n\n"
            "RUN_SIMULATION = True  # False = reference CSV only\n\n"
            "ref, csv = load_reference()\n"
            "if RUN_SIMULATION:\n"
            "    results, ref, csv, metrics = run_and_evaluate_long_pipe()\n"
            "    print(f\"Overall PASS: {metrics.passed}\")\n"
            "else:\n"
            "    results = None\n"
            "    metrics = None\n"
            "    print(\"Skipped simulation; plotting R-THYM reference only.\")"
        ),
        md("## 3. Pressure trace overlay"),
        code(
            "mask = (csv[\"t\"] >= 35.0) & (csv[\"t\"] <= 65.0)\n"
            "t_ref = csv[\"t\"][mask]\n"
            "fig, ax = plt.subplots(figsize=(12, 4))\n"
            "ax.plot(t_ref, csv[\"vp\"][mask], \"k-\", label=\"R-THYM reference (Valve_B)\")\n"
            "if results is not None:\n"
            "    from long_pipe_valve_verification_utils import _WARMUP_S, interp_to_ref\n"
            "    sim_t = np.asarray(results[\"time\"])\n"
            "    sim_p = interp_to_ref(t_ref + _WARMUP_S, sim_t, np.asarray(results[\"node_pressure\"][\"Valve_B\"]))\n"
            "    ax.plot(t_ref, sim_p, \"r--\", label=\"RTHYM-MOC\")\n"
            "    rms = metrics.trace_rms_psi[\"Valve_B\"]\n"
            "    ax.set_title(f\"Post-closure window — RMS err {rms:.2f} psi (tol {TRACE_PSI_TOL_RMS})\")\n"
            "ax.set_xlabel(\"R-THYM time (s)\")\n"
            "ax.set_ylabel(\"Pressure (psi)\")\n"
            "ax.legend()\n"
            "ax.grid(True, alpha=0.3)\n"
            "fig.tight_layout()\n"
            "plt.show()"
        ),
    ],
)

write(
    "epanet_import_verification.ipynb",
    [
        md(
            "# EPANET Import — Complex Topology Verification\n\n"
            "Mirrors **`tests/test_complex_topology_from_inp.py`**: `load_inp()` on "
            "`tests/networks/complex_topology.inp`, pre-trip heads/flows vs **wntr/EPANET**, "
            "then Pump_A trip checks.\n\n"
            "Requires **`wntr`** (`pip install wntr` or `pip install 'rthym-moc[inp]'`).\n\n"
            "> **Related:** [`quickstart_notebook.ipynb`](quickstart_notebook.ipynb) (Joukowsky R-THYM case)."
        ),
        md("## 1. Setup"),
        code(SETUP_INP),
        md("## 2. Evaluate"),
        code(
            "from complex_topology_verification_utils import evaluate_complex_topology, HEAD_NODES\n\n"
            "bundle = evaluate_complex_topology()\n"
            "head_pass = sum(1 for m in bundle.pretrip_head_metrics if m.passed)\n"
            "flow_pass = sum(1 for m in bundle.pretrip_flow_metrics if m.passed)\n"
            "print(f\"Pre-trip heads: {head_pass}/{len(bundle.pretrip_head_metrics)} passed\")\n"
            "print(f\"Pre-trip flows: {flow_pass}/{len(bundle.pretrip_flow_metrics)} passed\")\n"
            "for chk in bundle.trip_checks:\n"
            "    print(f\"  {chk.name}: PASS={chk.passed} ({chk.detail})\")"
        ),
        md("## 3. Pre-trip head errors"),
        code(
            "nodes = [m.id for m in bundle.pretrip_head_metrics]\n"
            "errs = [m.error for m in bundle.pretrip_head_metrics]\n"
            "colors = [\"seagreen\" if m.passed else \"crimson\" for m in bundle.pretrip_head_metrics]\n"
            "fig, ax = plt.subplots(figsize=(12, 4))\n"
            "ax.bar(range(len(nodes)), errs, color=colors)\n"
            "ax.axhline(0.5, color=\"gray\", linestyle=\"--\", label=\"tol 0.5 ft\")\n"
            "ax.set_xticks(range(len(nodes)), nodes, rotation=45, ha=\"right\")\n"
            "ax.set_ylabel(\"|sim − EPANET| (ft)\")\n"
            "ax.set_title(\"Pre-trip junction head error\")\n"
            "ax.legend()\n"
            "fig.tight_layout()\n"
            "plt.show()"
        ),
        md("## 4. Pump trip at Junction_E"),
        code(
            "t = bundle.time_s\n"
            "h = np.asarray(bundle.node_head[\"Junction_E\"])\n"
            "fig, ax = plt.subplots(figsize=(10, 3))\n"
            "ax.plot(t, h, color=\"steelblue\")\n"
            "ax.axvline(10.0, color=\"orange\", linestyle=\"--\", label=\"Pump trip\")\n"
            "ax.set_xlabel(\"Time (s)\")\n"
            "ax.set_ylabel(\"Junction_E head (ft)\")\n"
            "ax.legend()\n"
            "ax.grid(True, alpha=0.3)\n"
            "plt.show()"
        ),
    ],
)

write(
    "gradual_closure_verification.ipynb",
    [
        md(
            "# Gradual Closure — Joukowsky / Allievi Sweep\n\n"
            "Mirrors **`tests/test_gradual_closure_benchmark.py`**: closure times 0.5 s, 3 s, 150 s "
            "vs expected peak-rise fractions of the Joukowsky head.\n\n"
            "> **Related:** `examples/test_gradual_closure.py` (same physics, script form)."
        ),
        md("## 1. Setup"),
        code(SETUP),
        md("## 2. Run sweep"),
        code(
            "from gradual_closure_verification_utils import (\n"
            "    JOUKOWSKY_DH_FT,\n"
            "    T_WAVE_S,\n"
            "    run_all_closure_cases,\n"
            ")\n\n"
            "cases = run_all_closure_cases()\n"
            "print(f\"2L/a = {T_WAVE_S:.2f} s, Joukowsky dH = {JOUKOWSKY_DH_FT:.1f} ft\")\n"
            "for c in cases:\n"
            "    print(f\"  {c.label}: fraction={c.observed_fraction:.3f} PASS={c.passed}\")"
        ),
        md("## 3. Valve head traces"),
        code(
            "fig, axes = plt.subplots(len(cases), 1, figsize=(12, 3 * len(cases)), sharex=False)\n"
            "if len(cases) == 1:\n"
            "    axes = [axes]\n"
            "for ax, c in zip(axes, cases):\n"
            "    ax.plot(c.time_s, c.valve_head_ft, label=\"V1 head\")\n"
            "    ax.axhline(c.observed_dh_ft + c.valve_head_ft.min(), color=\"gray\", linestyle=\":\", alpha=0.5)\n"
            "    ax.set_title(f\"{c.label}: dH fraction {c.observed_fraction:.2f} (PASS={c.passed})\")\n"
            "    ax.set_ylabel(\"Head (ft)\")\n"
            "    ax.grid(True, alpha=0.3)\n"
            "axes[-1].set_xlabel(\"Time (s)\")\n"
            "fig.tight_layout()\n"
            "plt.show()"
        ),
    ],
)

write(
    "dvcm_canonical_verification.ipynb",
    [
        md(
            "# DVCM Regression — Canonical Junction Traces\n\n"
            "This is the **formal DVCM regression notebook** (same role as the R-THYM section in "
            "[`quickstart_notebook.ipynb`](quickstart_notebook.ipynb)). It replays the three "
            "checked-in anchors in `tests/dvcm_*_reference.json` and applies the **same tolerances** "
            "as **`tests/test_dvcm_canonical_scenarios.py`**.\n\n"
            "| Notebook | Purpose | Source of truth |\n"
            "|----------|---------|------------------|\n"
            "| **This notebook** | JSON trace regression (peak, collapse time, RMS) | `dvcm_*_reference.json` |\n"
            "| [`dvcm_physical_verification.ipynb`](dvcm_physical_verification.ipynb) | Independent physics formulas (mass step, collapse ΔH) | Wylie / collision estimate |\n"
            "| [`dvcm_showcase.ipynb`](dvcm_showcase.ipynb) | Pedagogy: Legacy vs DVCM on a valve network | Exploratory (heavy `dt`, slow on Binder) |\n\n"
            "**CI tolerances:** peak ≤ 0.05 ft, first collapse time ≤ 1e−9 s, RMS head ≤ 1e−9 ft.\n\n"
            "[![Launch Binder](https://mybinder.org/badge_logo.svg)]"
            "(https://mybinder.org/v2/gh/jlillywh/RTHYM-MOC/main?labpath=examples%2Fdvcm_canonical_verification.ipynb)"
        ),
        md("## 1. Setup and reference assets"),
        code(
            SETUP
            + "\nfrom dvcm_canonical_verification_utils import (\n"
            "    CANONICAL_DT_S,\n"
            "    CANONICAL_P_VAPOR_PSI,\n"
            "    CASES,\n"
            "    CASE_LABELS,\n"
            "    COLLAPSE_TIME_ERROR_MAX_S,\n"
            "    PEAK_ERROR_MAX_FT,\n"
            "    RMS_TRACE_ERROR_MAX_FT,\n"
            "    reference_path,\n"
            "    run_and_evaluate,\n"
            ")\n\n"
            "for case_id, fname in CASES.items():\n"
            "    print(f\"  {CASE_LABELS[case_id]:<42} {reference_path(case_id)}\")\n"
            "print(f\"Solver: dt={CANONICAL_DT_S} s, p_vapor={CANONICAL_P_VAPOR_PSI} psi, model=DVCM\")"
        ),
        md(
            "## 2. Run canonical scenarios\n\n"
            "Symmetric reservoir–junction–reservoir geometry; boundary heads follow each JSON `schedule`."
        ),
        code(
            "case_results = {}\n"
            "for case_id in CASES:\n"
            "    case_results[case_id] = run_and_evaluate(case_id)\n"
            "print(\"Simulations complete.\")"
        ),
        md(
            "## 3. Validate against checked-in JSON traces\n\n"
            "Overlays match the quickstart pattern: reference trace, simulation, and pointwise error."
        ),
        code(
            "fig, axes = plt.subplots(len(CASES), 1, figsize=(11, 3.4 * len(CASES)), sharex=False)\n"
            "if len(CASES) == 1:\n"
            "    axes = [axes]\n"
            "for ax, case_id in zip(axes, CASES):\n"
            "    res, ref, m = case_results[case_id]\n"
            "    t_ref = np.asarray(ref[\"time_s\"], dtype=float)\n"
            "    h_ref = np.asarray(ref[\"head_ft\"], dtype=float)\n"
            "    t_sim = np.asarray(res[\"time\"], dtype=float)\n"
            "    h_sim = np.asarray(res[\"node_head\"][\"J1\"], dtype=float)\n"
            "    ax.plot(t_ref, h_ref, \"o-\", color=\"black\", markersize=5, linewidth=1.2, label=\"JSON reference (J1)\")\n"
            "    ax.plot(t_sim, h_sim, \"--\", color=\"tab:red\", linewidth=1.8, label=\"rthym_moc simulation\")\n"
            "    ax.axvline(m.collapse_time_s, color=\"darkorange\", linestyle=\":\", alpha=0.8, label=\"First collapse (sim)\")\n"
            "    ax.axhline(float(ref[\"peak_head_ft\"]), color=\"seagreen\", linestyle=\"-.\", alpha=0.7, label=\"Ref peak\")\n"
            "    ok = \"PASS\" if m.passed else \"FAIL\"\n"
            "    ax.set_title(f\"{CASE_LABELS[case_id]} — RMS {m.rms_head_error_ft:.2e} ft [{ok}]\")\n"
            "    ax.set_ylabel(\"J1 head (ft)\")\n"
            "    ax.legend(loc=\"best\", fontsize=8)\n"
            "    ax.grid(True, alpha=0.3)\n"
            "axes[-1].set_xlabel(\"Time (s)\")\n"
            "fig.suptitle(\"DVCM canonical regression: simulated vs checked-in reference heads\", fontweight=\"bold\", y=1.01)\n"
            "fig.tight_layout()\n"
            "plt.show()"
        ),
        md("### 3a. Pointwise head error (sim − reference)"),
        code(
            "for case_id in CASES:\n"
            "    res, ref, m = case_results[case_id]\n"
            "    t_ref = np.asarray(ref[\"time_s\"], dtype=float)\n"
            "    h_sim = np.asarray(res[\"node_head\"][\"J1\"], dtype=float)\n"
            "    err = h_sim[: t_ref.size] - np.asarray(ref[\"head_ft\"], dtype=float)\n"
            "    fig, ax = plt.subplots(figsize=(10, 2.8))\n"
            "    ax.plot(t_ref, err, color=\"firebrick\", linewidth=1.2)\n"
            "    ax.axhline(0.0, color=\"black\", linewidth=0.8)\n"
            "    ax.set_title(f\"{CASE_LABELS[case_id]} — max |error| {np.max(np.abs(err)):.2e} ft\")\n"
            "    ax.set_xlabel(\"Time (s)\")\n"
            "    ax.set_ylabel(\"Error (ft)\")\n"
            "    ax.grid(True, alpha=0.3)\n"
            "    fig.tight_layout()\n"
            "    plt.show()"
        ),
        md("## 4. Cavity volume and collapse flags (reference fields in JSON)"),
        code(
            "case_id = \"rapid_closure\"\n"
            "res, ref, m = case_results[case_id]\n"
            "t = np.asarray(res[\"time\"], dtype=float)\n"
            "fig, axes = plt.subplots(2, 1, figsize=(10, 5), sharex=True)\n"
            "axes[0].plot(ref[\"time_s\"], ref[\"cavity_volume_ft3\"], \"o--\", color=\"gray\", label=\"Reference volume\")\n"
            "axes[0].plot(t, res[\"node_cavity_volume\"][\"J1\"], color=\"darkcyan\", label=\"Simulated volume\")\n"
            "axes[0].set_ylabel(\"Cavity volume (ft³)\")\n"
            "axes[0].legend()\n"
            "axes[0].grid(True, alpha=0.3)\n"
            "axes[1].step(ref[\"time_s\"], ref[\"collapse_flag\"], where=\"mid\", color=\"gray\", label=\"Reference collapse\")\n"
            "axes[1].step(t, res[\"node_cavity_collapse_flag\"][\"J1\"], where=\"mid\", color=\"crimson\", label=\"Sim collapse\")\n"
            "axes[1].set_xlabel(\"Time (s)\")\n"
            "axes[1].set_ylabel(\"Collapse flag\")\n"
            "axes[1].legend()\n"
            "axes[1].grid(True, alpha=0.3)\n"
            "fig.tight_layout()\n"
            "plt.show()"
        ),
        code(
            "res, ref, m = case_results[\"long_run\"]\n"
            "t = np.asarray(res[\"time\"], dtype=float)\n"
            "fig, ax = plt.subplots(figsize=(10, 2.8))\n"
            "ax.step(ref[\"time_s\"], ref[\"collapse_flag\"], where=\"mid\", color=\"gray\", label=\"Reference\")\n"
            "ax.step(t, res[\"node_cavity_collapse_flag\"][\"J1\"], where=\"mid\", color=\"crimson\", label=\"Simulation\")\n"
            "ax.set_title(f\"Long run — {m.collapse_events} sim collapses vs {m.reference_collapse_events} reference\")\n"
            "ax.set_xlabel(\"Time (s)\")\n"
            "ax.legend()\n"
            "ax.grid(True, alpha=0.3)\n"
            "fig.tight_layout()\n"
            "plt.show()"
        ),
        md("## 5. Pass/fail summary (pytest tolerances)"),
        code(
            "print(f\"{'Case':<44} {'Peak err':>10} {'dt_coll':>12} {'RMS err':>12} {'Extra':>6} {'PASS':>6}\")\n"
            "print(\"-\" * 92)\n"
            "for case_id in CASES:\n"
            "    m = case_results[case_id][2]\n"
            "    print(\n"
            "        f\"{CASE_LABELS[case_id]:<44} {m.peak_head_error_ft:10.3e} {m.collapse_time_error_s:12.3e} \"\n"
            "        f\"{m.rms_head_error_ft:12.3e} {str(m.passed_extra):>6} {str(m.passed):>6}\"\n"
            "    )\n"
            "print(f\"\\nTolerances: peak <= {PEAK_ERROR_MAX_FT} ft, collapse time <= {COLLAPSE_TIME_ERROR_MAX_S:g} s, RMS <= {RMS_TRACE_ERROR_MAX_FT:g} ft\")\n"
            "all_pass = all(case_results[c][2].passed for c in CASES)\n"
            "print(\"Overall:\", \"PASS\" if all_pass else \"FAIL\")"
        ),
    ],
)

write(
    "dvcm_physical_verification.ipynb",
    [
        md(
            "# DVCM Physical Verification\n\n"
            "Independent checks (not JSON trace replay): mass-conservation growth steps and "
            "post-collapse head rise vs discrete collision estimate. Mirrors "
            "**`tests/test_dvcm_physical_verification.py`**.\n\n"
            "> **DVCM regression traces:** [`dvcm_canonical_verification.ipynb`](dvcm_canonical_verification.ipynb)"
        ),
        md("## 1. Setup"),
        code(SETUP),
        md("## 2. Run canonical rapid-recovery transient"),
        code(
            "from dvcm_physical_verification_utils import (\n"
            "    COLLAPSE_SPIKE_RTOL,\n"
            "    DEFAULT_DT_S,\n"
            "    MASS_STEP_ATOL_FT3,\n"
            "    evaluate_collapse_spike,\n"
            "    evaluate_mass_conservation,\n"
            "    run_physical_verification_case,\n"
            ")\n\n"
            "results = run_physical_verification_case(dt=DEFAULT_DT_S)\n"
            "mass = evaluate_mass_conservation(results, dt=DEFAULT_DT_S, atol_ft3=MASS_STEP_ATOL_FT3)\n"
            "spike = evaluate_collapse_spike(results, dt=DEFAULT_DT_S, rtol=COLLAPSE_SPIKE_RTOL)\n"
            "print(f\"Mass conservation: PASS={mass.passed} ({mass.n_steps_checked} steps, max err {mass.max_abs_step_error_ft3:.3e} ft^3)\")\n"
            "print(f\"Collapse spike: PASS={spike.passed} rel_err={spike.relative_error:.3f}\")"
        ),
        md("## 3. Cavity volume and junction head"),
        code(
            "t = np.asarray(results[\"time\"], dtype=float)\n"
            "vol = np.asarray(results[\"node_cavity_volume\"][\"J1\"], dtype=float)\n"
            "head = np.asarray(results[\"node_head\"][\"J1\"], dtype=float)\n"
            "fig, axes = plt.subplots(2, 1, figsize=(10, 5), sharex=True)\n"
            "axes[0].plot(t, vol, color=\"darkcyan\")\n"
            "axes[0].set_ylabel(\"Cavity volume (ft³)\")\n"
            "axes[0].grid(True, alpha=0.3)\n"
            "axes[1].plot(t, head, color=\"firebrick\")\n"
            "axes[1].axvline(spike.collapse_step * DEFAULT_DT_S, color=\"orange\", linestyle=\":\", label=\"Primary collapse\")\n"
            "axes[1].set_xlabel(\"Time (s)\")\n"
            "axes[1].set_ylabel(\"J1 head (ft)\")\n"
            "axes[1].legend()\n"
            "axes[1].grid(True, alpha=0.3)\n"
            "fig.tight_layout()\n"
            "plt.show()"
        ),
        md("## 4. Summary"),
        code(
            "overall = mass.passed and spike.passed\n"
            "print(\"Overall:\", \"PASS\" if overall else \"FAIL\")"
        ),
    ],
)

write(
    "surge_design_rules_verification.ipynb",
    [
        md(
            "# Surge Design-Rule Sweeps\n\n"
            "Partial mirror of parameterized surge benchmarks:\n\n"
            "- **`test_tank_size_benchmark.py`** — standpipe area sweep\n"
            "- **`test_device_placement_benchmark.py`** — hydropneumatic placement\n\n"
            "> **Related:** [`surge_device_verification.ipynb`](surge_device_verification.ipynb) (single-point physics)."
        ),
        md("## 1. Setup"),
        code(SETUP),
        md("## 2. Standpipe size sweep"),
        code(
            "from surge_design_rules_verification_utils import (\n"
            "    evaluate_standpipe_sweep,\n"
            "    standpipe_sweep_monotonic,\n"
            ")\n\n"
            "standpipe = evaluate_standpipe_sweep()\n"
            "areas = [p.area_ft2 for p in standpipe]\n"
            "peaks = [p.peak_head_ft for p in standpipe]\n"
            "limits = [p.peak_limit_ft for p in standpipe]\n"
            "print(f\"Monotonic: {standpipe_sweep_monotonic(standpipe)}\")\n"
            "for p in standpipe:\n"
            "    print(f\"  {p.area_ft2:4.0f} ft²: peak={p.peak_head_ft:.1f} ft limit={p.peak_limit_ft:.0f} PASS={p.passed}\")\n\n"
            "fig, ax = plt.subplots(figsize=(8, 4))\n"
            "ax.plot(areas, peaks, \"o-\", label=\"Simulated peak\")\n"
            "ax.plot(areas, limits, \"s--\", color=\"gray\", label=\"pytest upper bound\")\n"
            "ax.set_xlabel(\"Standpipe area (ft²)\")\n"
            "ax.set_ylabel(\"SP1 peak head (ft)\")\n"
            "ax.set_title(\"Closure peak vs standpipe size\")\n"
            "ax.legend()\n"
            "ax.grid(True, alpha=0.3)\n"
            "plt.show()"
        ),
        md("## 3. Hydropneumatic placement"),
        code(
            "from surge_design_rules_verification_utils import evaluate_placement_sweep\n\n"
            "placement = evaluate_placement_sweep()\n"
            "dists = [p.distance_ft for p in placement]\n"
            "trip_h = [p.trip_mean_head_ft for p in placement]\n"
            "for p in placement:\n"
            "    print(f\"  {p.distance_ft:.0f} ft: trip mean={p.trip_mean_head_ft:.1f} ft floor={p.trip_head_floor_ft:.0f} PASS={p.passed}\")\n\n"
            "fig, ax = plt.subplots(figsize=(8, 4))\n"
            "ax.plot(dists, trip_h, \"o-\", color=\"darkcyan\")\n"
            "ax.set_xlabel(\"Distance from pump to HPT (ft)\")\n"
            "ax.set_ylabel(\"Trip-window mean head at Jd (ft)\")\n"
            "ax.set_title(\"Protection weakens as vessel moves downstream\")\n"
            "ax.grid(True, alpha=0.3)\n"
            "plt.show()"
        ),
    ],
)

write(
    "surge_device_verification.ipynb",
    [
        md(
            "# Surge Control Device Verification\n\n"
            "Mirrors **`tests/test_surge_device_verification.py`** and related surge regressions. "
            "Passive devices are shown in **both** transient roles they are used for in production:\n\n"
            "| Device | Overpressure (valve closure) | Low pressure (pump trip) | Other |\n"
            "|--------|------------------------------|--------------------------|-------|\n"
            "| **Standpipe** | §2 B.8 + §4 valve-side (`test_surge_device_mitigation`) | §5 pump trip (mitigation) | §3 TSNet §B.8.5 |\n"
            "| **HydropneumaticTank** | §4 fast closure | §5 pump trip + §8 sizing link | — |\n"
            "| **AirValve** | — | §6 trip vacuum floor | §7 restart / trapped air |\n\n"
            "> **Sizing sweeps:** [`surge_design_rules_verification.ipynb`](surge_design_rules_verification.ipynb)\n\n"
            "[![Launch Binder](https://mybinder.org/badge_logo.svg)]"
            "(https://mybinder.org/v2/gh/jlillywh/RTHYM-MOC/main?labpath=examples%2Fsurge_device_verification.ipynb)"
        ),
        md("## 1. Setup"),
        code(
            SETUP
            + "\nfrom surge_device_verification_utils import (\n"
            "    SP_H_JOUK_PEAK_FT, SP_H_PEAK_ANALYTICAL_FT, SP_H_SS_FT, SP_T_OSC_S,\n"
            "    TRIP_START_S, TRIP_END_S, TSNET_PEAK_DIFF_FT, TSNET_RMS_0_20_FT,\n"
            "    evaluate_air_valve_restart, evaluate_air_valve_vs_unprotected,\n"
            "    evaluate_hydropneumatic_precharge, evaluate_standpipe,\n"
            "    evaluate_valve_closure_mitigation, try_tsnet_standpipe_overlay,\n"
            ")\n"
            "from surge_design_rules_verification_utils import evaluate_standpipe_sweep"
        ),
        md("## 2. Standpipe — B.8 valve closure (Joukowsky + mass oscillation)"),
        code(
            'res_none, res_sp, sp_metrics = evaluate_standpipe()\n'
            "t_none = np.asarray(res_none[\"time\"])\n"
            "t_sp = np.asarray(res_sp[\"time\"])\n"
            "fig, ax = plt.subplots(figsize=(12, 5))\n"
            "ax.plot(t_none, res_none[\"node_head\"][\"J1\"], \"--\", color=\"gray\", label=\"No standpipe (J1)\")\n"
            "ax.plot(t_sp, res_sp[\"node_head\"][\"SP1\"], color=\"teal\", label=\"With standpipe (SP1)\")\n"
            "ax.axhline(SP_H_JOUK_PEAK_FT, color=\"seagreen\", linestyle=\"-.\", label=\"Joukowsky ref.\")\n"
            "ax.axhline(SP_H_PEAK_ANALYTICAL_FT, color=\"darkorange\", linestyle=\":\", label=\"Mass-osc. ref.\")\n"
            "ax.set_xlim(0, SP_T_OSC_S / 2)\n"
            "ax.set_ylabel(\"Head (ft)\")\n"
            "ax.legend(fontsize=9)\n"
            "ax.grid(True, alpha=0.3)\n"
            "plt.show()\n"
            "print(f\"Standpipe B.8 PASS={sp_metrics.passed}  mitigation={sp_metrics.mitigation_fraction:.1%}\")"
        ),
        md(
            "## 3. TSNet standpipe overlay (Appendix B.8.5)\n\n"
            "Default: **checked-in** `tests/TSNet_Standpipe_B8_Traces.csv` (same pattern as R-THYM quickstart). "
            "Set `RUN_TSNET = True` only to regenerate the archive (requires `pip install tsnet`). "
            "See [`cross_engine_surge_verification.ipynb`](cross_engine_surge_verification.ipynb)."
        ),
        code(
            "RUN_TSNET = False\n"
            "overlay = try_tsnet_standpipe_overlay(run_tsnet=RUN_TSNET)\n"
            "fig, ax = plt.subplots(figsize=(12, 4))\n"
            "mask = overlay.rthym_time_s <= 20.0\n"
            "ax.plot(overlay.rthym_time_s[mask], overlay.rthym_head_ft[mask], label=\"RTHYM-MOC SP1\")\n"
            "if RUN_TSNET and overlay.ran_tsnet and overlay.tsnet_time_s is not None:\n"
            "    m = overlay.tsnet_time_s <= 20.0\n"
            "    ax.plot(overlay.tsnet_time_s[m], overlay.tsnet_head_ft[m], \"--\", label=\"TSNet J1\")\n"
            "ax.set_title(\"Standpipe peak comparison (0–20 s)\")\n"
            "ax.set_ylabel(\"Head (ft)\")\n"
            "ax.legend()\n"
            "ax.grid(True, alpha=0.3)\n"
            "plt.show()\n"
            "print(f\"Documented: peak diff {overlay.documented_peak_diff_ft:.2f} ft, RMS {overlay.documented_rms_ft:.2f} ft\")\n"
            "if overlay.ran_tsnet:\n"
            "    print(f\"This run: peak diff {overlay.peak_diff_ft:.2f} ft, RMS {overlay.rms_ft:.2f} ft\")\n"
            "elif overlay.tsnet_error:\n"
            "    print(f\"TSNet skipped/error: {overlay.tsnet_error}\")"
        ),
        md("## 4. Valve-side protection on fast closure (`test_surge_device_mitigation`)"),
        code(
            "base_valve, valve_cases, valve_metrics = evaluate_valve_closure_mitigation()\n"
            "t_b = np.asarray(base_valve[\"time\"])\n"
            "h_b = np.asarray(base_valve[\"node_head\"][\"Prot\"])\n"
            "fig, ax = plt.subplots(figsize=(12, 5))\n"
            "ax.plot(t_b, h_b, \"k--\", label=\"Unprotected\")\n"
            "colors = {\"Standpipe\": \"teal\", \"HydropneumaticTank\": \"purple\"}\n"
            "for kind, color in colors.items():\n"
            "    d = valve_cases[kind]\n"
            "    ax.plot(d[\"time\"], d[\"node_head\"][\"Prot\"], color=color, label=kind)\n"
            "ax.set_ylabel(\"Protected node head (ft)\")\n"
            "ax.set_title(\"Fast valve closure: standpipe and HPT at the valve\")\n"
            "ax.legend()\n"
            "ax.grid(True, alpha=0.3)\n"
            "plt.show()\n"
            "for m in valve_metrics:\n"
            "    print(f\"  {m.kind}: peak={m.peak_head_ft:.0f} ft, cut={m.peak_reduction_ft:.0f} ft, PASS={m.passed}\")"
        ),
        md("## 5. Hydropneumatic tank — pump trip"),
        code(
            "res_none_hpt, res_hpt, hpt_trip, hpt_pre = evaluate_hydropneumatic_precharge()\n"
            "fig, ax = plt.subplots(figsize=(12, 5))\n"
            "ax.plot(res_none_hpt[\"time\"], res_none_hpt[\"node_head\"][\"Jd\"], \"--\", color=\"gray\", label=\"Unprotected\")\n"
            "ax.plot(res_hpt[\"time\"], res_hpt[\"node_head\"][\"Jd\"], color=\"purple\", label=\"HPT 10 ft³\")\n"
            "ax.axhline(hpt_trip.reference_floor_ft, color=\"orange\", linestyle=\":\", label=\"Anchored floor\")\n"
            "ax.axvspan(TRIP_START_S, TRIP_END_S, color=\"gold\", alpha=0.15)\n"
            "ax.set_xlim(4.5, 8.5)\n"
            "ax.set_ylabel(\"Jd head (ft)\")\n"
            "ax.legend()\n"
            "ax.grid(True, alpha=0.3)\n"
            "plt.show()\n"
            "print(f\"HPT trip PASS={hpt_trip.passed}  improvement={hpt_trip.improvement_vs_none_ft:.1f} ft\")"
        ),
        md("## 6. Air valve — pump trip vacuum floor"),
        code(
            "res_base_av, res_av, av_metrics = evaluate_air_valve_vs_unprotected()\n"
            "fig, ax = plt.subplots(figsize=(12, 5))\n"
            "ax.plot(res_base_av[\"time\"], res_base_av[\"node_head\"][\"Vent\"], \"--\", color=\"gray\", label=\"Unprotected\")\n"
            "ax.plot(res_av[\"time\"], res_av[\"node_head\"][\"Vent\"], color=\"steelblue\", label=\"Air valve\")\n"
            "ax.axhline(-5.0, color=\"orange\", linestyle=\":\", label=\"Protected floor\")\n"
            "ax.axvspan(TRIP_START_S, TRIP_END_S, color=\"gold\", alpha=0.15)\n"
            "ax.set_xlim(4.5, 8.5)\n"
            "ax.set_ylabel(\"Vent head (ft)\")\n"
            "ax.legend()\n"
            "ax.grid(True, alpha=0.3)\n"
            "plt.show()\n"
            "print(f\"Air-valve trip PASS={av_metrics.passed}\")"
        ),
        md("## 7. Air valve — restart and trapped-air release (`test_air_valve`)"),
        code(
            "res_restart, restart_metrics = evaluate_air_valve_restart()\n"
            "t = np.asarray(res_restart[\"time\"])\n"
            "h = np.asarray(res_restart[\"node_head\"][\"Vent\"])\n"
            "fig, ax = plt.subplots(figsize=(12, 4))\n"
            "ax.plot(t, h, color=\"steelblue\")\n"
            "ax.axvline(5.0, color=\"gray\", linestyle=\"--\", alpha=0.5, label=\"Trip\")\n"
            "ax.axvline(8.0, color=\"green\", linestyle=\"--\", alpha=0.5, label=\"Restart\")\n"
            "ax.set_ylabel(\"Vent head (ft)\")\n"
            "ax.set_title(\"Trapped-air cushion then gradual release\")\n"
            "ax.legend()\n"
            "ax.grid(True, alpha=0.3)\n"
            "plt.show()\n"
            "print(f\"Restart PASS={restart_metrics.passed}\")\n"
            "print(f\"  pre={restart_metrics.pretrip_head_ft:.1f} early={restart_metrics.early_restart_head_ft:.1f} late={restart_metrics.late_restart_head_ft:.1f} ft\")"
        ),
        md("## 8. Why bigger tank / closer placement helps (preview)"),
        code(
            "sweep = evaluate_standpipe_sweep()\n"
            "areas = [p.area_ft2 for p in sweep]\n"
            "peaks = [p.peak_head_ft for p in sweep]\n"
            "fig, ax = plt.subplots(figsize=(8, 3.5))\n"
            "ax.plot(areas, peaks, \"o-\")\n"
            "ax.set_xlabel(\"Standpipe area (ft²)\")\n"
            "ax.set_ylabel(\"Closure peak at SP1 (ft)\")\n"
            "ax.set_title(\"Larger standpipe → lower peak (see surge_design_rules notebook)\")\n"
            "ax.grid(True, alpha=0.3)\n"
            "plt.show()"
        ),
        md("## 9. Summary"),
        code(
            "rows = [\n"
            "    (\"Standpipe B.8\", sp_metrics.passed),\n"
            "    (\"Valve-side SP/HPT\", all(m.passed for m in valve_metrics)),\n"
            "    (\"HPT pump trip\", hpt_trip.passed),\n"
            "    (\"Air valve trip\", av_metrics.passed),\n"
            "    (\"Air valve restart\", restart_metrics.passed),\n"
            "]\n"
            "for name, ok in rows:\n"
            "    print(f\"{name:<24} {'PASS' if ok else 'FAIL'}\")\n"
            "print(\"Overall:\", \"PASS\" if all(r[1] for r in rows) else \"FAIL\")"
        ),
    ],
)

write(
    "cross_engine_surge_verification.ipynb",
    [
        md(
            "# Cross-Engine Surge & INP Verification\n\n"
            "Same **checked-in reference** pattern as [`quickstart_notebook.ipynb`](quickstart_notebook.ipynb) "
            "(R-THYM JSON/CSV), but for surge and EPANET topics:\n\n"
            "| Engine | Artifact | This notebook |\n"
            "|--------|----------|---------------|\n"
            "| **R-THYM** | `tests/R-THYM_Joukowsky_*`, `tests/R-THYM_MOC_*` | See quickstart / long-pipe notebooks |\n"
            "| **TSNet** | `tests/TSNet_Standpipe_B8_Verification.json`, `tests/TSNet_Standpipe_B8_Traces.csv` | §2 overlay (Appendix B.8.5) |\n"
            "| **EPANET** | live steady-state via **wntr** on `tests/networks/complex_topology.inp` | §3 pre-trip bars |\n\n"
            "Requires **`pip install 'rthym-moc[inp]'`** for §3."
        ),
        md("## 1. Setup"),
        code(SETUP_INP),
        md("## 2. TSNet standpipe B.8 — checked-in trace vs RTHYM-MOC"),
        code(
            "from cross_engine_verification_utils import (\n"
            "    TSNET_PEAK_DIFF_TOL_FT,\n"
            "    TSNET_RMS_TOL_FT,\n"
            "    evaluate_tsnet_standpipe_cross_engine,\n"
            "    load_tsnet_standpipe_verification,\n"
            ")\n\n"
            "ref = load_tsnet_standpipe_verification()\n"
            "print(f\"TSNet reference: {ref['source']}\")\n"
            "print(f\"  peak={ref['peak_head_ft']:.2f} ft  archived RMS={ref.get('rms_head_ft', 'n/a')}\")\n\n"
            "from pathlib import Path\n\n"
            "res, t_ref, h_ref, m = evaluate_tsnet_standpipe_cross_engine()\n"
            "t_sim = np.asarray(res[\"time\"], dtype=float)\n"
            "h_sim = np.asarray(res[\"node_head\"][\"SP1\"], dtype=float)\n"
            "mask = t_sim <= m.compare_window_s\n"
            "fig, ax = plt.subplots(figsize=(12, 5))\n"
            "csv_path = TESTS_DIR / \"TSNet_Standpipe_B8_Traces.csv\"\n"
            "if csv_path.is_file() and t_ref.size:\n"
            "    ax.plot(t_ref, h_ref, \"--\", color=\"gray\", linewidth=1.2, label=\"TSNet reference (J1)\")\n"
            "else:\n"
            "    ax.axhline(ref[\"peak_head_ft\"], color=\"gray\", linestyle=\"--\", label=\"TSNet peak (archived)\")\n"
            "    ax.axhline(ref[\"steady_state_head_ft\"], color=\"silver\", linestyle=\":\", label=\"TSNet SS (archived)\")\n"
            "    print(\"Tip: run scripts/export_tsnet_standpipe_reference.py to add the full TSNet trace CSV.\")\n"
            "ax.plot(t_sim[mask], h_sim[mask], color=\"teal\", linewidth=1.8, label=\"RTHYM-MOC (SP1)\")\n"
            "ax.set_xlim(0, m.compare_window_s)\n"
            "ax.set_ylabel(\"Head (ft)\")\n"
            "ax.set_title(f\"B.8 standpipe — peak diff {m.peak_diff_ft:.2f} ft [{ 'PASS' if m.passed_peak else 'FAIL' }]\")\n"
            "ax.legend()\n"
            "ax.grid(True, alpha=0.3)\n"
            "plt.show()\n"
            "print(f\"Peak PASS={m.passed_peak} (tol {TSNET_PEAK_DIFF_TOL_FT} ft)\")"
        ),
        md(
            "## 3. EPANET steady state vs MOC (`complex_topology.inp`)\n\n"
            "Full walkthrough: [`epanet_import_verification.ipynb`](epanet_import_verification.ipynb)."
        ),
        code(
            "from cross_engine_verification_utils import evaluate_epanet_complex_topology_pretrip\n\n"
            "bundle, summary = evaluate_epanet_complex_topology_pretrip()\n"
            "nodes = [x.id for x in bundle.pretrip_head_metrics]\n"
            "errs = [x.error for x in bundle.pretrip_head_metrics]\n"
            "colors = [\"seagreen\" if x.passed else \"crimson\" for x in bundle.pretrip_head_metrics]\n"
            "fig, ax = plt.subplots(figsize=(12, 4))\n"
            "ax.bar(range(len(nodes)), errs, color=colors)\n"
            "ax.axhline(0.5, color=\"gray\", linestyle=\"--\", label=\"tol 0.5 ft\")\n"
            "ax.set_xticks(range(len(nodes)), nodes, rotation=45, ha=\"right\")\n"
            "ax.set_ylabel(\"|MOC − EPANET| mean head (ft)\")\n"
            "ax.set_title(f\"Pre-trip heads {summary.head_passed}/{summary.head_total} PASS\")\n"
            "ax.legend()\n"
            "fig.tight_layout()\n"
            "plt.show()\n"
            "print(f\"Flows {summary.flow_passed}/{summary.flow_total} PASS - overall {summary.passed}\")"
        ),
    ],
)

write(
    "validation_notebooks_index.ipynb",
    [
        md(
            "# Validation Notebooks — Start Here\n\n"
            "Navigation only (no simulations). Full tables and pytest mirrors: "
            "[`docs/validation_notebooks.md`](../docs/validation_notebooks.md).\n\n"
            "**Binder:** install `pip install 'rthym-moc[inp]'` for INP/EPANET notebooks.\n\n"
            "**Recommended path:** this index → [`quickstart_notebook.ipynb`](quickstart_notebook.ipynb) "
            "→ topic notebook (e.g. `dvcm_canonical_verification` for DVCM regression, not `dvcm_showcase` first)."
        ),
        code(
            SETUP
            + "\n\n"
            "NOTEBOOKS = [\n"
            "    ('quickstart_notebook.ipynb', 'R-THYM Joukowsky cross-engine'),\n"
            "    ('dvcm_canonical_verification.ipynb', 'DVCM JSON regression'),\n"
            "    ('dvcm_physical_verification.ipynb', 'DVCM mass step + collapse dH'),\n"
            "    ('cross_engine_surge_verification.ipynb', 'TSNet + EPANET cross-engine'),\n"
            "    ('surge_device_verification.ipynb', 'Standpipe / HPT / air valve'),\n"
            "    ('epanet_import_verification.ipynb', 'complex_topology.inp + pump trip'),\n"
            "]\n"
            "print(f'Repository: {REPO_ROOT}')\n"
            "for nb, desc in NOTEBOOKS:\n"
            "    print(f'  {nb:<42} {desc}')"
        ),
    ],
)

if __name__ == "__main__":
    print("Notebooks written under examples/")
