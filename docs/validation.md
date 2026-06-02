# Validation Guide

This document describes how RTHYM-MOC proves **solver correctness**: trusted
references, quantitative tolerances, automated pytest regressions, and versioned
artifacts. It does not cover **runtime performance** comparisons; those live in
[docs/benchmarking.md](benchmarking.md).

## Structure Rules

Each validation case should provide the following where practical:

- a documented scenario with network description, schematic, and expected outcome
- one or more trusted references: analytical solution, EPANET/wntr steady state,
  the R-THYM web app, or another stored reference artifact
- explicit quantitative tolerances such as peak error, RMS trace error, or
  steady-state deviation
- automated regression checks in pytest
- stored reference artifacts in the repository when external replay data is used
- parameter sweeps when the governing behavior depends on a control parameter
  such as closure time, tank size, or pipe length

## Validation Summary

| Category | What it proves | Primary tests | Reference |
|---|---|---|---|
| Cross-engine (R-THYM) | Heads, peaks, and traces match the production web-app engine | `test_joukowsky_rthym.py`, `test_long_pipe_valve.py` | Checked-in JSON/CSV exports |
| Cross-engine (EPANET) | Imported steady state and trip directionality | `test_complex_topology_from_inp.py` | `tests/networks/complex_topology.inp` |
| Analytical / regime | Joukowsky and slow-closure behavior vs theory | `test_gradual_closure_benchmark.py` | Joukowsky / Allievi expectations |
| DVCM canonical cavitation | Junction-only cavity initiation, collapse/recovery, and repeated-event stability | `test_dvcm_canonical_scenarios.py` | Internal anchored junction geometries |
| Surge-device physics | Monotonic sizing, placement, and mixed-device trends | `test_tank_size_benchmark.py`, `test_hydropneumatic_size_benchmark.py`, `test_device_placement_benchmark.py`, `test_pipe_length_benchmark.py`, `test_multi_device_placement_benchmark.py`, `test_mixed_device_interaction_benchmark.py`, `test_air_valve_dominant_*.py` | Internal anchored geometries |
| Broader regression | Cavitation, controls, INP import, materials, losses | `test_column_separation_and_stability.py`, `test_operational_controls.py`, `test_pump_valve_transients_from_inp.py`, and others under `tests/` | Module docstrings |

Representative headline results (automated in CI):

- Joukowsky first-step surge vs analytical: **< 0.05 %** (`test_joukowsky_rthym.py`, appendix §B.6)
- Wave oscillation period vs $T_0 = 4L/a$: **< 0.2 %** (see `examples/test_wave_reflections.py` and overview claims)
- R-THYM trace RMS (Joukowsky): **≤ 4 psi** over the early post-closure window (`test_joukowsky_rthym.py`)

## Validation Test Map

| Test module | Scenario / expected outcome | Reference solution | Parameterized coverage | Cross-engine |
|---|---|---|---|---|
| `tests/test_joukowsky_rthym.py` | Instant closure with downstream stub and column-separation dynamics should match R-THYM export | R-THYM web app + analytical Joukowsky constraints | no | R-THYM web app |
| `tests/test_long_pipe_valve.py` | Equal-percentage closure network should match R-THYM heads, peaks, and pressure traces | R-THYM web app export | nodes and trace quantities only | R-THYM web app |
| `tests/test_complex_topology_from_inp.py` | Imported complex network should match EPANET operating point and pump-trip directionality | EPANET/wntr steady state | per-node and per-pipe parametrization | wntr / EPANET |
| `tests/test_gradual_closure_benchmark.py` | Closure-time sweep should reproduce rapid-closure Joukowsky behavior and slow-closure suppression | Analytical Joukowsky / Allievi regime expectations | closure time (`0.5 s`, `3.0 s`, `150 s`) | no |
| `tests/test_dvcm_canonical_scenarios.py` | Rapid collapse-spike, pressure-recovery, and repeated-event junction cavitation scenarios should remain stable and quantitatively match anchored DVCM traces | Internal anchored junction geometries | three canonical schedules with peak-head, collapse-timing, and RMS-trace tolerances | no |
| `tests/test_tank_size_benchmark.py` | Increasing standpipe size should monotonically reduce the protected-node closure peak | Internal anchored geometry | standpipe area (`1`, `2`, `5`, `10`, `20 ft²`) | no |
| `tests/test_hydropneumatic_size_benchmark.py` | Larger vessels at fixed precharge ratio should improve trip recovery | Internal anchored geometry | vessel size (`2`–`20 ft³`, `gas_volume/tank_volume = 0.4`) | no |
| `tests/test_device_placement_benchmark.py` | Moving protection farther from pump discharge should weaken trip protection | Internal anchored geometry | distance (`40`, `120`, `300`, `600 ft`) | no |
| `tests/test_pipe_length_benchmark.py` | Discharge-main length should shift near-pump vessel effectiveness | Internal anchored geometry | length (`500`–`8000 ft`) | no |
| `tests/test_multi_device_placement_benchmark.py` | Split capacity protects well only if one vessel stays near the pump | Internal anchored geometry | two-vessel placement pairs | no |
| `tests/test_mixed_device_interaction_benchmark.py` | Vessel + air valve should beat either device alone on low-pressure exposure | Internal anchored geometry | protection mode (`none`, `air`, `vessel`, `both`) | no |
| `tests/test_air_valve_dominant_mixed_layout_benchmark.py` | Air valve dominates; tiny vessel adds secondary damping | Internal anchored geometry | protection mode (`none`, `air`, `vessel`, `both`) | no |
| `tests/test_air_valve_dominant_layout_sensitivity_benchmark.py` | Downstream vessel distance changes secondary damping only | Internal anchored geometry | distance (`300`–`3000 ft`) | no |
| `tests/test_air_valve_dominant_size_sweep_benchmark.py` | Larger downstream vessel recovers more regional mean trip head | Internal anchored geometry | size (`0.3`–`4.8 ft³`) | no |

Internal-reference sweeps prove **regression and design-rule behavior** on fixed
geometries. Cross-engine rows prove **independent correctness** against stored
exports or EPANET steady state.

## Scenario Documentation

Scenario documentation is provided in two layers:

- test-module docstrings describe the network, schematic, references, and
  expected metrics directly beside the automated checks
- [docs/appendix_b_verification.md](appendix_b_verification.md)
  provides the long-form narrative for the primary cross-engine studies

## Quantitative Tolerances

The suite uses explicit numeric tolerances rather than pass/fail eyeballing.
Current metrics include:

- wave-speed error in `ft/s`
- steady-state head and flow deviation in `ft` and `GPM`
- first-step and peak-pressure error in `ft` or `psi`
- RMS trace mismatch over a declared time window
- bounded late-time envelopes for stability-focused transients
- DVCM collapse timing error in `s` for anchored junction cavitation cases

For `tests/test_dvcm_canonical_scenarios.py`, the current explicit acceptance
metrics are:

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

Reference outputs are stored in-repo for validation cases that depend on
external or cross-engine replay data:

- `tests/R-THYM_Joukowsky_Verification.json`
- `tests/R-THYM_Joukowsky_Traces.csv`
- `tests/R-THYM_MOC_Verification.json`
- `tests/R-THYM_MOC_Traces.csv`
- INP fixtures under `tests/networks/`

Code changes are checked against fixed reference outputs rather than only
against relative trends.

## Reference Artifact Inventory

| Artifact | Type | Source / meaning | Primary automated consumer |
|---|---|---|---|
| `tests/R-THYM_Joukowsky_Verification.json` | JSON | R-THYM web-app export for the instant-closure Joukowsky case | `tests/test_joukowsky_rthym.py` |
| `tests/R-THYM_Joukowsky_Traces.csv` | CSV | R-THYM web-app time-series trace for the same case | `tests/test_joukowsky_rthym.py` |
| `tests/R-THYM_MOC_Verification.json` | JSON | R-THYM web-app export for the long-pipe valve case | `tests/test_long_pipe_valve.py` |
| `tests/R-THYM_MOC_Traces.csv` | CSV | R-THYM web-app time-series trace for the long-pipe valve case | `tests/test_long_pipe_valve.py` |
| `tests/dvcm_rapid_closure_reference.json` | JSON | Anchored DVCM rapid-collapse regression trace | `tests/test_dvcm_canonical_scenarios.py` |
| `tests/dvcm_pressure_recovery_reference.json` | JSON | Anchored DVCM pressure-recovery regression trace | `tests/test_dvcm_canonical_scenarios.py` |
| `tests/dvcm_long_run_reference.json` | JSON | Anchored DVCM repeated-event regression trace | `tests/test_dvcm_canonical_scenarios.py` |
| `tests/Joukowsky Benchmark.inp` | INP | EPANET-style geometry for the Joukowsky cross-engine study | `tests/test_joukowsky_rthym.py` |
| `tests/Long Pipe Valve.inp` | INP | EPANET-style geometry for the long-pipe valve study | `tests/test_long_pipe_valve.py` |
| `tests/networks/complex_topology.inp` | INP | Multi-node network for EPANET/wntr steady-state checks | `tests/test_complex_topology_from_inp.py` |
| `tests/networks/pump_valve_benchmark.inp` | INP | Pump/valve network for trip, restart, and closure regressions | `tests/test_pump_valve_transients_from_inp.py` |

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

- Not every validation study is cross-engine; analytical and EPANET-based
  references are used where they are the stronger oracle.
- Parameter sweeps cover closure time, standpipe size, hydropneumatic sizing and
  placement, pipe length, split vessels, and mixed air-valve layouts. Further
  sweeps for alternate air-valve settings remain good future additions.
- Long-form documentation focuses on the main cross-engine studies; newer
  validation regressions are documented primarily in module docstrings and this
  guide.
