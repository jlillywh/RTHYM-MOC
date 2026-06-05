# Validation Guide

This document describes how RTHYM-MOC proves **solver correctness** and tracks
**behavioral stability**: trusted references, quantitative tolerances, automated
pytest checks, and versioned artifacts. It does not cover **runtime performance**
comparisons; those live in [docs/benchmarking.md](benchmarking.md).

## Verification vs regression (read this first)

Not every test under `tests/` is a **verification** test in the sense users care
about. We distinguish four trust models:

| Trust model | Question it answers | Reference | User-facing claim |
|---|---|---|---|
| **Independent verification** | Does rthym-moc match physics, EPANET/**wntr**, TSNet, or published measurements? | Analytical formula, **wntr**, TSNet export, lab peaks/traces, continuity/collision invariants | “Checked against a source of truth outside this Python port” |
| **Maintainer parity** | Does the Python port still match the author's R-THYM web-app exports? | Checked-in R-THYM JSON/CSV from the JS engine | “Author regression during port — **not** third-party proof” |
| **Snapshot regression** | Did we accidentally change a previously accepted answer? | Checked-in JSON/CSV from an earlier rthym-moc run | “Locked to a baseline trace — detects drift, not absolute correctness” |
| **Design-rule / behavioral** | Do sizing, placement, or control sweeps behave as expected? | Fixed internal geometry + monotonic or bounded expectations | “Design trends hold — not a cross-check against external truth” |

**Verification** for external reviewers requires a reference **outside the current solver
run and outside the same author's other implementation** — theory, **wntr**, TSNet,
published lab data, or another team's engine. R-THYM web-app comparisons are still
valuable CI gates for the maintainer but should not be headline evidence in docs or
papers.

Pytest runs the **full suite** (`pytest -q`); the tables below label which modules
are which.

### Independent verification (automated in CI unless noted)

| Test module | Independent reference | Notebook mirror |
|---|---|---|
| `tests/test_complex_topology_from_inp.py` | EPANET steady state via **wntr** | `epanet_import_verification.ipynb` |
| `tests/test_epanet_complex_topology_cross_engine.py` | Same EPANET pre-trip check | `cross_engine_surge_verification.ipynb` |
| `tests/test_gradual_closure_benchmark.py` | Joukowsky / Allievi closure-regime expectations | `gradual_closure_verification.ipynb` |
| `tests/test_dvcm_physical_verification.py` | Wylie continuity step + discrete collapse ΔH | `dvcm_physical_verification.ipynb` |
| `tests/test_dvcm_bergant_adelaide_experiment.py` | Bergant–Simpson Adelaide lab peaks (He et al. 2025 / Bergant 1999); see [bergant_adelaide_verification.md](bergant_adelaide_verification.md) | — |
| `tests/test_dvcm_bergant_adelaide_trace.py` | Digitized He et al. (2025) Fig. 4 CSV; peak-window gauge check | `bergant_adelaide_verification.ipynb` |
| `tests/test_standpipe_surge_protection.py` | Joukowsky peak + standpipe mass-oscillation formula | (partial) `surge_device_verification.ipynb` |
| `tests/test_surge_device_verification.py` | Joukowsky, polytropic precharge law, Appendix B.8 refs | `surge_device_verification.ipynb` |
| `tests/test_tsnet_standpipe_cross_engine.py` | Checked-in **TSNet** B.8 trace (exported independently) | `cross_engine_surge_verification.ipynb` |
| `tests/test_pipe_materials.py` | Analytical Korteweg wave speed | — |

### Maintainer parity (R-THYM web app — author cross-check)

| Test module | Reference | Notebook mirror |
|---|---|---|
| `tests/test_joukowsky_rthym.py` | R-THYM web app export **+** analytical Joukowsky (external part is the formula check) | `quickstart_notebook.ipynb` (§3 = parity; §2 = analytical) |
| `tests/test_long_pipe_valve.py` | R-THYM web app export | `long_pipe_valve_verification.ipynb` |

**Documented but optional / manual:** TSNet Joukowsky three-way study (Appendix
§B.6, `examples/benchmark_vs_tsnet.py`) — not a default pytest dependency.

**Tutorial script (not CI):** `examples/test_wave_reflections.py` — wave period
$T_0 = 4L/a$ vs simulation.

### Snapshot regression (prior rthym-moc baseline)

| Test module | Baseline artifact | Notebook mirror |
|---|---|---|
| `tests/test_dvcm_canonical_scenarios.py` | `tests/dvcm_*_reference.json` (golden J1 traces) | `dvcm_canonical_verification.ipynb` |

These files store **inputs** (`schedule`, `total_time_s`) and **expected outputs**
(`head_ft`, collapse flags) from an earlier accepted rthym-moc run. A passing test
means “still matches the snapshot,” not “verified against textbook physics.”

### Design-rule and behavioral regressions (fixed geometry, no external oracle)

Monotonic sizing/placement sweeps and similar modules prove **expected trends** on
anchored networks — useful for design studies and CI stability, but not independent
verification:

`test_tank_size_benchmark.py`, `test_hydropneumatic_size_benchmark.py`,
`test_device_placement_benchmark.py`, `test_pipe_length_benchmark.py`,
`test_multi_device_placement_benchmark.py`, `test_mixed_device_interaction_benchmark.py`,
`test_air_valve_dominant_*.py`, and related surge benchmarks.
Notebook: partial mirror in `surge_design_rules_verification.ipynb`.

### Broader pytest (API, import, controls, smoke)

Remaining modules under `tests/` cover import fidelity, operational controls,
check valves, materials, invalid inputs, WASM smoke, etc. They guard **product
behavior and regressions** but are not headline physics-verification studies.
See module docstrings and the [Validation Test Map](#validation-test-map) below.

## Notebook mirrors vs pytest

The full automated validation program lives under `tests/`. Binder notebooks are
an **interactive sampler**, not a complete map of every regression.

- **Navigation (new users):** [validation_notebooks.md](validation_notebooks.md) and
  [examples/validation_notebooks_index.ipynb](../examples/validation_notebooks_index.ipynb)
  (includes [operational quality](validation_notebooks.md#operational-quality): CI notebook smoke, Binder bootstrap, pass/fail semantics)
- **Full matrix:** [validation_notebook_coverage.md](validation_notebook_coverage.md)
  (Full / Partial / Script / None) and shared `tests/*_verification_utils.py` helpers

## Structure Rules

Each **independent verification** case should provide the following where practical:

- a documented scenario with network description, schematic, and expected outcome
- one or more **independent** trusted references: analytical solution,
  EPANET/wntr steady state, TSNet export, published lab data, or another team's
  engine — not a prior rthym-moc snapshot alone and not the author's R-THYM web
  app when the audience is external (label that as **maintainer parity** instead)
- explicit quantitative tolerances such as peak error, RMS trace error, or
  steady-state deviation
- automated checks in pytest
- stored reference artifacts in the repository when external replay data is used
- parameter sweeps when the governing behavior depends on a control parameter
  such as closure time, tank size, or pipe length

Snapshot regressions and design-rule sweeps should be labeled as such in docs
and notebooks (see [Verification vs regression](#verification-vs-regression-read-this-first)).

## Validation Summary

| Category | Trust model | What it proves | Primary tests |
|---|---|---|---|
| Analytical / regime | **Independent** | Joukowsky and slow-closure behavior vs theory | `test_gradual_closure_benchmark.py`, `test_standpipe_surge_protection.py` |
| Cross-engine (EPANET / TSNet) | **Independent** | Imported steady state; standpipe trace vs TSNet export | `test_complex_topology_from_inp.py`, `test_tsnet_standpipe_cross_engine.py` |
| DVCM physics invariants | **Independent** | Mass step and collapse ΔH vs formulas | `test_dvcm_physical_verification.py` |
| DVCM Bergant Adelaide rig | **Independent** | Literature peaks + digitized Fig. 4 trace (peak window) | `test_dvcm_bergant_adelaide_experiment.py`, `test_dvcm_bergant_adelaide_trace.py` |
| Surge-device verification | **Independent** (mixed) | Joukowsky / B.8 / device laws on anchored cases | `test_surge_device_verification.py` |
| R-THYM web app parity | **Maintainer** | Heads, peaks, and traces match author's JS engine | `test_joukowsky_rthym.py`, `test_long_pipe_valve.py` |
| DVCM canonical traces | **Snapshot** | Junction traces match checked-in golden JSON | `test_dvcm_canonical_scenarios.py` |
| Surge sizing / placement | **Design-rule** | Monotonic sizing, placement, mixed-device trends | `test_tank_size_benchmark.py`, `test_hydropneumatic_size_benchmark.py`, … |
| Broader pytest | **Mixed** | Cavitation, controls, INP import, materials, API smoke | remaining modules under `tests/` |

Representative headline results (automated in CI):

- Joukowsky first-step surge vs analytical: **< 0.05 %** (`test_joukowsky_rthym.py`, appendix §B.6)
- Wave oscillation period vs $T_0 = 4L/a$: **< 0.2 %** (see `examples/test_wave_reflections.py` and overview claims)
- R-THYM trace RMS (Joukowsky): **≤ 4 psi** over the early post-closure window (`test_joukowsky_rthym.py`)

## Validation Test Map

| Test module | Trust model | Scenario / expected outcome | Reference solution | Notebook |
|---|---|---|---|---|
| `tests/test_joukowsky_rthym.py` | Independent | Instant closure with column-separation dynamics | R-THYM web app + analytical Joukowsky | `quickstart_notebook.ipynb` |
| `tests/test_long_pipe_valve.py` | Independent | Equal-% closure vs R-THYM heads, peaks, traces | R-THYM web app export | `long_pipe_valve_verification.ipynb` |
| `tests/test_complex_topology_from_inp.py` | Independent | Pre-trip operating point + pump-trip directionality | EPANET/wntr steady state | `epanet_import_verification.ipynb` |
| `tests/test_epanet_complex_topology_cross_engine.py` | Independent | EPANET pre-trip heads and flows | wntr `EpanetSimulator` | `cross_engine_surge_verification.ipynb` |
| `tests/test_tsnet_standpipe_cross_engine.py` | Independent | Standpipe peak/RMS vs TSNet B.8 export | `tests/TSNet_Standpipe_B8_*` | `cross_engine_surge_verification.ipynb` |
| `tests/test_gradual_closure_benchmark.py` | Independent | Closure-time sweep vs Joukowsky / Allievi | Analytical regime expectations | `gradual_closure_verification.ipynb` |
| `tests/test_dvcm_physical_verification.py` | Independent | Mass step + collapse ΔH | Wylie + collision formula | `dvcm_physical_verification.ipynb` |
| `tests/test_standpipe_surge_protection.py` | Independent | Standpipe vs Joukowsky + mass oscillation | Analytical Appendix B.8 | partial → `surge_device_verification.ipynb` |
| `tests/test_surge_device_verification.py` | Independent | Standpipe, HPT, air-valve cases | Joukowsky, polytropic law, B.8 | `surge_device_verification.ipynb` |
| `tests/test_dvcm_canonical_scenarios.py` | **Snapshot** | J1 traces match golden JSON | `tests/dvcm_*_reference.json` | `dvcm_canonical_verification.ipynb` |
| `tests/test_tank_size_benchmark.py` | Design-rule | Larger standpipe → lower closure peak | Monotonic trend on fixed geometry | partial → `surge_design_rules_verification.ipynb` |
| `tests/test_hydropneumatic_size_benchmark.py` | Design-rule | Larger vessel → better trip recovery | Monotonic trend | — |
| `tests/test_device_placement_benchmark.py` | Design-rule | Farther protection → weaker trip mitigation | Monotonic trend | partial → `surge_design_rules_verification.ipynb` |
| `tests/test_pipe_length_benchmark.py` | Design-rule | Main length shifts vessel effectiveness | Param sweep bounds | — |
| `tests/test_multi_device_placement_benchmark.py` | Design-rule | Split capacity placement rules | Fixed geometry pairs | — |
| `tests/test_mixed_device_interaction_benchmark.py` | Design-rule | Combined devices vs single device | Relative exposure counts | — |
| `tests/test_air_valve_dominant_*.py` | Design-rule | Air-valve dominance / layout sensitivity | Fixed geometry sweeps | — |

Independent rows answer “is the physics right?” Snapshot and design-rule rows
answer “did we drift?” or “do design trends hold?”

## Scenario Documentation

Scenario documentation is provided in two layers:

- test-module docstrings describe the network, schematic, references, and
  expected metrics directly beside the automated checks
- [docs/appendix_b_verification.md](appendix_b_verification.md)
  provides the long-form narrative for the primary cross-engine studies and
  §B.9 for DVCM junction physics verification

## Quantitative Tolerances

The suite uses explicit numeric tolerances rather than pass/fail eyeballing.
Current metrics include:

- wave-speed error in `ft/s`
- steady-state head and flow deviation in `ft` and `GPM`
- first-step and peak-pressure error in `ft` or `psi`
- RMS trace mismatch over a declared time window
- bounded late-time envelopes for stability-focused transients
- DVCM collapse timing error in `s` for anchored junction cavitation cases

For `tests/test_dvcm_canonical_scenarios.py` (**snapshot regression**, not
independent verification), the explicit acceptance metrics are:

- peak-head error `<= 0.05 ft` against the anchored case peak
- first collapse timing error `<= 1e-9 s`
- RMS trace error `<= 1e-9 ft` against the anchored junction-head trace

Tolerance values are expressed in one of three explicit forms in the suite:

- named module-level constants for reusable cross-engine or analytical checks
- parameter matrices for validation sweeps, where each input case carries its
  own acceptance floor, cap, or maximum exposure count
- inline acceptance bands in direct behavior regressions when the threshold is
  scenario-specific and not reused elsewhere

Every numerical acceptance rule should be visible either as a named tolerance
constant, a parameterized case bound, or an explicit numeric band in the
assertion itself.

## Regression Tracking

Reference outputs are stored in-repo so tests can replay fixed answers:

- **Independent verification artifacts** — exports from R-THYM, TSNet, or EPANET
  runs that predate the pytest check (e.g. `tests/R-THYM_*.json`, `tests/TSNet_Standpipe_B8_*`)
- **Snapshot baselines** — golden rthym-moc traces (e.g. `tests/dvcm_*_reference.json`)
- **Network fixtures** — INP files under `tests/networks/` and study INPs

Code changes are checked against these stored outputs rather than only against
relative trends.

## Reference Artifact Inventory

| Artifact | Trust model | Source / meaning | Primary consumer |
|---|---|---|---|
| `tests/R-THYM_Joukowsky_Verification.json` | Independent | R-THYM web-app export (Joukowsky case) | `test_joukowsky_rthym.py` |
| `tests/R-THYM_Joukowsky_Traces.csv` | Independent | R-THYM time series (same case) | `test_joukowsky_rthym.py` |
| `tests/R-THYM_MOC_Verification.json` | Independent | R-THYM web-app export (long-pipe valve) | `test_long_pipe_valve.py` |
| `tests/R-THYM_MOC_Traces.csv` | Independent | R-THYM time series (long-pipe valve) | `test_long_pipe_valve.py` |
| `tests/TSNet_Standpipe_B8_Verification.json` | Independent | TSNet B.8.5 standpipe peaks / RMS | `test_tsnet_standpipe_cross_engine.py` |
| `tests/TSNet_Standpipe_B8_Traces.csv` | Independent | TSNet J1 head time series (B.8) | `test_tsnet_standpipe_cross_engine.py` |
| `tests/dvcm_rapid_closure_reference.json` | **Snapshot** | Golden rthym-moc J1 trace (rapid closure) | `test_dvcm_canonical_scenarios.py` |
| `tests/dvcm_pressure_recovery_reference.json` | **Snapshot** | Golden rthym-moc J1 trace (recovery) | `test_dvcm_canonical_scenarios.py` |
| `tests/dvcm_long_run_reference.json` | **Snapshot** | Golden rthym-moc J1 trace (long run) | `test_dvcm_canonical_scenarios.py` |
| `tests/Joukowsky Benchmark.inp` | Input fixture | Network geometry for Joukowsky study | `test_joukowsky_rthym.py` |
| `tests/Long Pipe Valve.inp` | Input fixture | Network geometry for long-pipe study | `test_long_pipe_valve.py` |
| `tests/networks/complex_topology.inp` | Input fixture | Multi-node network for EPANET/wntr checks | `test_complex_topology_from_inp.py` |
| `tests/networks/pump_valve_benchmark.inp` | Input fixture | Pump/valve trip and closure regressions | `test_pump_valve_transients_from_inp.py` |

## Reference Data Policy

- CSV and JSON artifacts remain checked into the repository so regressions run
  against fixed external outputs, not regenerated files from the local machine.
- INP fixtures remain checked into the repository so import-based tests run
  against stable hydraulic layouts.
- When a reference artifact changes intentionally, the consuming test and this
  guide should be updated in the same change so reviewers can see both the data
  delta and the expected behavioral delta.

## TSNet And Performance

TSNet is used as an **optional physics cross-check** on the standard Joukowsky
case (results agree within ~0.2 ft RMS over the first wave cycle; see appendix
§B.6). It is **not** a default pytest dependency.

Wall-clock performance comparisons against TSNet are documented separately in
[docs/benchmarking.md](benchmarking.md) and
`examples/benchmark_vs_tsnet.py`.

## Gaps And Current Policy

- Label new tests and notebooks with a **trust model** (independent / snapshot /
  design-rule) in this guide and in module docstrings.
- Not every pytest module is independent verification; analytical and EPANET-based
  references are used where they are the stronger oracle.
- Parameter sweeps cover closure time, standpipe size, hydropneumatic sizing and
  placement, pipe length, split vessels, and mixed air-valve layouts. Further
  sweeps for alternate air-valve settings remain good future additions.
- Long-form documentation focuses on the main cross-engine studies; newer
  validation regressions are documented primarily in module docstrings and this
  guide.
- **Local surge bundle check** (smoke + pytest + optional notebook exec, ~1–2 min):
  ``.venv/bin/python3 scripts/verify_surge_bundle.py`` (add ``--smoke-only`` or
  ``--skip-notebook`` to shorten). TSNet overlay in the surge notebook stays
  off by default (`RUN_TSNET = False`).
- **Notebook coverage** is tracked explicitly in
  [validation_notebook_coverage.md](validation_notebook_coverage.md). Major
  gaps filled by Binder walkthroughs include the long-pipe R-THYM study,
  EPANET `complex_topology.inp` import, gradual-closure sweep, DVCM canonical
  JSON traces, and partial surge design-rule sweeps. Operational controls,
  check valves, PRV/PSV, pump inertia, and SI-only regressions remain
  pytest-only until dedicated notebooks are added.
