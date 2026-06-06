# Test Coverage Matrix

This document tracks the public feature and scenario surface that backs the
checklist item "All features/scenarios have automated tests".

Status meanings:

- `Direct`: a test exercises the feature explicitly and asserts its behavior.
- `Indirect`: the feature is exercised as part of a larger benchmark or import
  path, but not via a focused unit/regression assertion for that feature alone.
- `Gap`: documented or public surface with no current automated coverage.

## Public API Matrix

| Surface | Status | Primary automated coverage | Notes |
|---|---|---|---|
| `MOCSolver.add_node()` / `add_pipe()` | Direct | Many test modules | Base network construction path used throughout the suite. |
| `MOCSolver.clear()` | Direct | `tests/test_boundary_variations_and_losses.py` | Verifies topology and schedules are removed before the next `run()`. |
| `MOCSolver.run()` | Direct | Many test modules | Core execution path exercised across all transient and benchmark tests. |
| `MOCSolver.set_valve_setting()` | Direct | `tests/test_boundary_variations_and_losses.py` | Verified to persist across separate `run()` calls. |
| `MOCSolver.set_pump_speed()` | Direct | `tests/test_boundary_variations_and_losses.py` | Verified to persist across separate `run()` calls. |
| `MOCSolver.set_node_demand()` | Direct | `tests/test_boundary_variations_and_losses.py` | Verified for both `Junction` and `InflowNode` use. |
| `MOCSolver.set_valve_schedule()` | Direct | `tests/test_boundary_variations_and_losses.py`, valve benchmarks | Covered by closure and throttling transients. |
| `MOCSolver.set_pump_schedule()` | Direct | `tests/test_pump_valve_transients_from_inp.py`, pump-trip benchmarks | Covered by trip / restart scenarios. |
| `MOCSolver.set_demand_schedule()` | Direct | `tests/test_boundary_variations_and_losses.py` | Covered by a within-run junction demand step. |
| `MOCSolver.set_head_schedule()` | Direct | `tests/test_boundary_variations_and_losses.py` | Covered by a within-run pressure-boundary head step. |
| `load_inp()` | Direct | `tests/test_complex_topology_from_inp.py`, `tests/test_pump_valve_transients_from_inp.py`, `tests/test_pipe_minor_losses.py` | Includes both `use_wntr=True` and `use_wntr=False` flows. |
| `PipeInput.elevation_profile` | Direct | `tests/test_pipe_elevation_profile.py` | Piecewise-linear survey table; linear fallback between node elevations when empty. |
| `run(..., record_pipe_profiles=..., profile_stride=...)` | Direct | `tests/test_pipe_profile_export.py`, `tests/test_report.py` | Opt-in interior H/P/V export; legacy `run()` output unchanged when flag is false. |
| `pipe_profile_*` / interior cavity profile keys | Direct | `tests/test_pipe_profile_export.py`, `tests/test_interior_dvcm_state.py` | Cavity volume/active keys appear only when `enable_interior_dvcm=True`. |
| `MOCSolver.set_enable_interior_dvcm()` / `run(..., enable_interior_dvcm=...)` | Direct | `tests/test_interior_dvcm_state.py`, `tests/test_interior_dvcm_sloping_pipe.py` | Default off; junction-only DVCM unchanged when interior mode is off. |
| `PipeInput.interior_dvcm_chainages_ft` (sparse watchpoints) | Direct | `tests/test_sparse_interior_dvcm.py` | Full MOC grid with cavity state at flagged chainages only. |
| `MOCSolver.set_max_segments_per_pipe()` / wave-speed distortion controls | Direct | `tests/test_grid_scaling_long_pipe.py` | Caps segment count; reports `pipe_num_segments` and `pipe_distortion_pct`. |
| `MOCSolver.set_friction_model()` / `TransientFrictionModel` / `run(..., friction_model=...)` | Direct | `tests/test_transient_friction_model.py`, `tests/test_units_si.py` | Default BrunoneIIR unchanged for existing tests. |
| `summarize_study()` chainage envelope / grid-scaling meta | Direct | `tests/test_report.py`, `tests/test_grid_scaling_long_pipe.py`, `tests/test_long_pipeline_surge.py` | Per-pipe min/max vs chainage when profile keys are present. |
| `rthym_moc.chainage_air_valve` | Direct | `tests/test_chainage_air_valve.py`, `tests/test_dvcm_air_valve.py` | Split pipe at chainage; attach air valve at survey high point. |

## Node-Type Matrix

| Node type | Status | Primary automated coverage | Notes |
|---|---|---|---|
| `Junction` | Direct | `tests/test_boundary_variations_and_losses.py` | Explicit demand-step and setter coverage. |
| `OutflowNode` | Direct | `tests/test_boundary_variations_and_losses.py`, `tests/test_complex_topology_from_inp.py` | Direct demand-sign regression plus imported multi-outflow topology coverage. |
| `InflowNode` | Direct | `tests/test_boundary_variations_and_losses.py` | Explicit sign-convention regression verifies injection behavior. |
| `PressureBoundary` | Direct | `tests/test_boundary_variations_and_losses.py` | Fixed-head schedule and many transient baselines. |
| `Tank` | Direct | `tests/test_boundary_variations_and_losses.py`, `tests/test_complex_topology_from_inp.py` | Direct fixed-head schedule regression plus imported tanked topology checks. |
| `AirValve` | Direct | `tests/test_air_valve.py`, mixed-device benchmarks | Includes air-valve-only and mixed protection scenarios. |
| `Valve` | Direct | `tests/test_boundary_variations_and_losses.py`, closure benchmarks | Covered by immediate setter, schedule, and surge benchmarks. |
| `Turbine` | Direct | `tests/test_boundary_variations_and_losses.py` | Direct steady-opening sensitivity plus startup/gate-opening and shutdown/load-rejection ordering regressions. |
| `Pump` | Direct | `tests/test_pump_valve_transients_from_inp.py`, `tests/test_boundary_variations_and_losses.py` | Covered by schedules and immediate setter persistence. |
| `Standpipe` | Direct | `tests/test_standpipe_surge_protection.py`, `tests/test_tank_size_benchmark.py` | Covered by analytical and parameter-sweep regressions. |
| `HydropneumaticTank` | Direct | `tests/test_surge_device_mitigation.py`, size / placement benchmarks | Covered by protection and parameter-sweep scenarios. |

## Scenario Matrix

| Scenario family | Status | Primary automated coverage | Notes |
|---|---|---|---|
| Instant valve closure / Joukowsky | Direct | `tests/test_joukowsky_rthym.py` | Analytical constraints plus stored R-THYM reference validation. |
| Gradual closure regimes | Direct | `tests/test_gradual_closure_benchmark.py` | Closure-time sweep. |
| Pipe material / wave speed sensitivity | Direct | `tests/test_pipe_materials.py` | Wave-speed effect on surge magnitude. |
| Pipe minor loss import and response | Direct | `tests/test_pipe_minor_losses.py` | Direct and INP-loaded variants. |
| Unsteady friction toggle | Direct | `tests/test_boundary_variations_and_losses.py` | Late-time damping comparison. |
| Transient friction selector (Phase 6) | Direct | `tests/test_transient_friction_model.py`, `tests/test_transient_friction_literature.py` | Wylie & Streeter wave-decay + Bergant et al. LP-07 ordering; [transient_friction_verification.md](transient_friction_verification.md). |
| Pump trip / restart | Direct | `tests/test_pump_valve_transients_from_inp.py` | Imported network transient regression. |
| Complex imported topology | Direct | `tests/test_complex_topology_from_inp.py` | EPANET/wntr operating-point and transient checks. |
| Standpipe protection | Direct | `tests/test_standpipe_surge_protection.py`, `tests/test_tank_size_benchmark.py` | Analytical and sweep coverage. |
| Hydropneumatic protection | Direct | `tests/test_surge_device_mitigation.py`, size / placement benchmarks | Size, placement, and pipe-length effects. |
| Air-valve protection | Direct | `tests/test_air_valve.py`, air-dominant benchmarks | Single-device and mixed-device regimes. |
| Mixed protection layouts | Direct | `tests/test_mixed_device_interaction_benchmark.py`, related sweeps | Combined-device interaction coverage. |
| Long-run stability / column separation | Direct | `tests/test_column_separation_and_stability.py` | Stability and cavitation-oriented regression. |
| Long-pipe profile export (LP-01) | Direct | `tests/test_pipe_profile_export.py`, `tests/test_phase1_e2e_contract.py` | Mid-pipe Joukowsky after downstream closure; opt-in export contract. |
| Sloping pipe / summit static minimum (LP-02) | Direct | `tests/test_pipe_elevation_profile.py`, `tests/test_long_pipeline_surge.py` | Terrain-driven local vapor head; min static gauge P at survey high point. |
| Interior DVCM on uninterrupted reach (LP-03 / LP-04) | Direct | `tests/test_interior_dvcm_sloping_pipe.py`, `tests/test_long_pipeline_surge.py` | Cavity at summit under downsurge; collapse secondary spike at mid-pipe. |
| Grid scaling / distortion report (LP-05) | Direct | `tests/test_grid_scaling_long_pipe.py`, `tests/test_long_pipeline_surge.py` | Capped grid on multi-mile reach; distortion metadata in results and `summarize_study()`. |
| Summit air valve on chainage split (LP-06) | Direct | `tests/test_dvcm_air_valve.py`, `tests/test_chainage_air_valve.py` | Chainage split topology; air valve suppresses interior cavity at summit. |
| Long-pipeline canonical validation (Phase 7 / LP-SURGE-01) | Direct | `tests/test_long_pipeline_surge.py`, `tests/test_long_pipeline_surge_utils.py`, `tests/test_long_pipeline_surge_verification.py` | Multi-mile sloping reach combining Phases 1–4; notebook parity gate; 100 % helper-module coverage. See [long_pipeline_surge_roadmap.md](long_pipeline_surge_roadmap.md). |
| Long-pipe performance budget (LP-PERF-01) | Direct (slow) | `tests/test_long_pipeline_perf.py` | `@pytest.mark.slow`; 20-mile capped grid wall-clock guard vs checked-in baseline. |

## Current Gaps To Close

No known feature/surface coverage gaps remain in the current public API or scenario
matrices. Long-pipeline slow tests (`LP-PERF-01`, full transient window in
`test_long_pipeline_surge.py`) are excluded from default CI via `@pytest.mark.slow`;
`LP-PERF-01` runs in the PR `long-pipeline-perf` workflow job. See
[long_pipeline_surge_roadmap.md](long_pipeline_surge_roadmap.md) Phase 7.
