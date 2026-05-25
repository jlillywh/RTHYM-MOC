# Benchmark Guide

This document captures the benchmark structure used in RTHYM-MOC and maps the
current benchmark suite to the validation recommendations used for hydraulic
transient solvers.

## Structure Rules

Each benchmark should provide the following where practical:

- a documented scenario with network description, schematic, and expected outcome
- one or more trusted references: analytical solution, EPANET/wntr steady state,
  TSNet, the R-THYM web app, or another stored reference artifact
- explicit quantitative tolerances such as peak error, RMS trace error, or
  steady-state deviation
- automated regression checks in pytest
- stored reference artifacts in the repository when external replay data is used
- parameter sweeps when the governing behavior depends on a control parameter
  such as closure time, tank size, or pipe length

## Current Benchmark Map

| Benchmark | Scenario / expected outcome | Reference solution | Automated checks | Stored artifacts | Parameterized coverage | Cross-engine |
|---|---|---|---|---|---|---|
| `tests/test_joukowsky_rthym.py` | Instant closure with downstream stub and column-separation dynamics should match R-THYM export | R-THYM web app + analytical Joukowsky constraints | wave speed, steady state, first-step surge, trace RMS, min/max pressure | `tests/R-THYM_Joukowsky_Verification.json`, `tests/R-THYM_Joukowsky_Traces.csv` | no | R-THYM web app |
| `tests/test_long_pipe_valve.py` | Equal-percentage closure network should match R-THYM heads, peaks, and pressure traces | R-THYM web app export | wave speed, steady heads, peak pressures, RMS traces | `tests/R-THYM_MOC_Verification.json`, `tests/R-THYM_MOC_Traces.csv` | nodes and trace quantities only | R-THYM web app |
| `tests/test_complex_topology_from_inp.py` | Imported complex network should match EPANET operating point and pump-trip directionality | EPANET/wntr steady state | per-node head tolerances, per-pipe flow tolerances, transient direction checks | `tests/networks/complex_topology.inp` | per-node and per-pipe parametrization | wntr / EPANET |
| `tests/test_gradual_closure_benchmark.py` | Closure-time sweep should reproduce rapid-closure Joukowsky behavior and slow-closure suppression | Analytical Joukowsky / Allievi regime expectations | parameterized peak-rise bounds by closure time | none needed | closure time (`0.5 s`, `3.0 s`, `150 s`) | no |
| `tests/test_tank_size_benchmark.py` | Increasing standpipe size should monotonically reduce the protected-node closure peak | Internal benchmark geometry anchored to the existing standpipe protection case | parameterized peak caps by area, monotonic peak reduction, cavitation suppression | none needed | standpipe area (`1`, `2`, `5`, `10`, `20 ft²`) | no |
| `tests/test_hydropneumatic_size_benchmark.py` | Increasing hydropneumatic vessel size at fixed precharge ratio should improve pump-trip head recovery and reduce negative-head exposure | Internal benchmark geometry anchored to the existing pump-trip protection case | parameterized trip-head floors, negative-head exposure limits, monotonic recovery | none needed | vessel size at fixed `gas_volume / tank_volume = 0.4` (`2`, `4`, `6`, `10`, `20 ft³`) | no |
| `tests/test_device_placement_benchmark.py` | Moving hydropneumatic protection farther from pump discharge should weaken trip-pressure protection | Internal benchmark geometry anchored to the existing pump-trip protection case | parameterized trip-head floors, negative-head exposure limits, monotonic placement trend | none needed | vessel distance from pump discharge (`40`, `120`, `300`, `600 ft`) | no |
| `tests/test_pipe_length_benchmark.py` | Changing discharge-main length should shift how effectively a fixed near-pump hydropneumatic vessel suppresses pump-trip low pressure | Internal benchmark geometry anchored to the existing pump-trip protection case | parameterized trip-head floors, negative-head exposure limits, monotonic recovery trend | none needed | discharge-main length (`500`, `1000`, `2000`, `4000`, `8000 ft`) | no |
| `tests/test_multi_device_placement_benchmark.py` | Splitting fixed hydropneumatic capacity across two vessels should work well only if at least one vessel stays near pump discharge | Internal benchmark geometry anchored to the existing pump-trip protection case | parameterized trip-head floors, negative-head exposure limits, and near-versus-remote split-vessel interaction checks | none needed | two-vessel placement pairs (`40/300`, `40/1200`, `300/1200`, `600/1200 ft`) | no |
| `tests/test_mixed_device_interaction_benchmark.py` | A small surge vessel plus a nearby air valve should reduce aggregate low-pressure exposure better than either device alone | Internal benchmark geometry anchored to the existing pump-trip protection case | explicit aggregate negative-head/cavitation bounds and combined-versus-single-device interaction checks | none needed | protection mode (`none`, `air`, `vessel`, `both`) on a fixed mixed-device layout | no |
| `tests/test_air_valve_dominant_mixed_layout_benchmark.py` | A near-pump air valve should dominate low-pressure protection while a tiny downstream vessel adds only secondary damping | Internal benchmark geometry anchored to the existing pump-trip protection case | explicit protected-region mean-head/exposure bounds plus air-dominant ordering checks | none needed | protection mode (`none`, `air`, `vessel`, `both`) on a fixed air-valve-dominant layout | no |
| `tests/test_air_valve_dominant_layout_sensitivity_benchmark.py` | With the air valve fixed near pump discharge, moving the tiny downstream vessel should change only the secondary damping contribution | Internal benchmark geometry anchored to the existing pump-trip protection case | parameterized protected-region mean-head/exposure bounds plus monotonic distance-sweep checks | none needed | downstream vessel distance (`300`, `600`, `1200`, `2000`, `3000 ft`) with fixed air-valve placement | no |
| `tests/test_air_valve_dominant_size_sweep_benchmark.py` | With the air valve fixed near pump discharge and the downstream vessel location fixed, increasing tiny vessel size should change only the secondary damping contribution | Internal benchmark geometry anchored to the existing pump-trip protection case | parameterized protected-region mean-head/exposure bounds plus monotonic size-sweep checks | none needed | downstream vessel size (`0.3`, `0.6`, `1.2`, `2.4`, `4.8 ft³`) with fixed air-valve placement | no |

## Scenario Documentation

Scenario documentation is provided in two layers:

- benchmark test-module docstrings describe the network, schematic, references,
  and expected metrics directly beside the automated checks
- [docs/appendix_b_verification.md](appendix_b_verification.md)
  provides the long-form narrative for the three primary cross-engine studies

## Quantitative Tolerances

The suite uses explicit numeric tolerances rather than pass/fail eyeballing.
Current metrics include:

- wave-speed error in `ft/s`
- steady-state head and flow deviation in `ft` and `GPM`
- first-step and peak-pressure error in `ft` or `psi`
- RMS trace mismatch over a declared time window
- bounded late-time envelopes for stability-focused transients

Tolerance values are expressed in one of three explicit forms in the suite:

- named module-level constants for reusable cross-engine or analytical checks,
  such as wave-speed, RMS, head, flow, and pressure-error limits
- parameter matrices for benchmark sweeps, where each input case carries its own
  acceptance floor, cap, or maximum exposure count
- inline acceptance bands in direct behavior regressions when the threshold is
  scenario-specific and not reused elsewhere

For direct behavior regressions, these numbers are still part of the documented
test contract: the test docstring describes the intended behavior, and the
assertion message states the exact quantitative band being enforced. This is
used deliberately for local hydraulic ordering checks such as:

- minimum head-drop or flow-change bands after a control action
- maximum allowed negative-head or cavitation exposure counts
- minimum separation between fast and slow transients in startup/shutdown tests
- monotonic improvement or degradation floors across placement and sizing sweeps

In short, the project policy is that every numerical acceptance rule should be
visible either as a named tolerance constant, a parameterized case bound, or an
explicit numeric band in the assertion itself.

## Regression Tracking

Reference outputs are stored in-repo for benchmarks that depend on external or
cross-engine replay data:

- `tests/R-THYM_Joukowsky_Verification.json`
- `tests/R-THYM_Joukowsky_Traces.csv`
- `tests/R-THYM_MOC_Verification.json`
- `tests/R-THYM_MOC_Traces.csv`
- benchmark INP fixtures under `tests/networks/`

This means code changes are checked against fixed reference outputs rather than
only against relative trends.

## Reference Artifact Inventory

The following checked-in artifacts are the repository's current versioned
reference dataset for regression and import validation. Because these files are
 committed to git beside the tests that consume them, any change to a reference
artifact is reviewable in normal code review and tied to the benchmark update
that required it.

| Artifact | Type | Source / meaning | Primary automated consumer |
|---|---|---|---|
| `tests/R-THYM_Joukowsky_Verification.json` | JSON | R-THYM web-app export of steady-state values, valve schedule, peaks, and wave speeds for the instant-closure Joukowsky case | `tests/test_joukowsky_rthym.py` |
| `tests/R-THYM_Joukowsky_Traces.csv` | CSV | R-THYM web-app time-series trace for the same Joukowsky benchmark | `tests/test_joukowsky_rthym.py` |
| `tests/R-THYM_MOC_Verification.json` | JSON | R-THYM web-app export of steady-state values, valve schedule, peaks, and wave speeds for the long-pipe valve benchmark | `tests/test_long_pipe_valve.py` |
| `tests/R-THYM_MOC_Traces.csv` | CSV | R-THYM web-app time-series trace for the long-pipe valve benchmark | `tests/test_long_pipe_valve.py` |
| `tests/Joukowsky Benchmark.inp` | INP | EPANET-style network definition for the single-pipe Joukowsky benchmark geometry referenced by the cross-engine study | benchmark geometry reference for `tests/test_joukowsky_rthym.py` |
| `tests/Long Pipe Valve.inp` | INP | EPANET-style network definition for the long-pipe valve benchmark geometry | `tests/test_long_pipe_valve.py` |
| `tests/networks/complex_topology.inp` | INP | Imported multi-node network used to validate EPANET/wntr-aligned operating points and transient directionality | `tests/test_complex_topology_from_inp.py` |
| `tests/networks/pump_valve_benchmark.inp` | INP | Imported pump/valve benchmark network used for trip, restart, and closure regression coverage | `tests/test_pump_valve_transients_from_inp.py` |

## Reference Data Policy

Reference artifacts are treated as first-class test inputs rather than ad hoc
attachments:

- CSV and JSON artifacts remain checked into the repository so regressions run
  against fixed external outputs, not regenerated files from the local machine.
- INP fixtures remain checked into the repository so import-based tests run
  against stable hydraulic layouts.
- When a reference artifact changes intentionally, the consuming test and this
  guide should be updated in the same change so reviewers can see both the data
  delta and the expected behavioral delta.
- Benchmark-oriented documentation in this guide and
  `docs/appendix_b_verification.md` should continue to explain the provenance of
  any new external reference dataset added to the suite.

TSNet comparisons remain documented benchmark studies rather than default test
dependencies. The published Joukowsky performance comparison lives in
`examples/benchmark_vs_tsnet.py` and the long-form verification appendix.

## Gaps And Current Policy

- Not every validation study is cross-engine; analytical and EPANET-based
  references are used where they are the stronger oracle.
- Parameter sweeps are now present in the automated suite for closure time,
  standpipe tank size, hydropneumatic vessel size at fixed precharge ratio,
  hydropneumatic device placement, protected pipe length, split-vessel
  multi-device placement, mixed surge-vessel / air-valve interaction, and an
  air-valve-dominant mixed-device layout. Further benchmark-style sweeps for
  alternative mixed-device operating regimes and alternate air-valve settings
  within the air-dominant regime remain good future additions.
- Long-form documentation currently focuses on the three main cross-engine
  studies. Newer benchmark-style regressions are documented primarily in module
  docstrings and this guide.
