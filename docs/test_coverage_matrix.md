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
| Instant valve closure / Joukowsky | Direct | `tests/test_tsnet_benchmark.py`, `tests/test_joukowsky_rthym.py` | Analytical and cross-engine validation. |
| Gradual closure regimes | Direct | `tests/test_gradual_closure_benchmark.py` | Closure-time sweep. |
| Pipe material / wave speed sensitivity | Direct | `tests/test_pipe_materials.py` | Wave-speed effect on surge magnitude. |
| Pipe minor loss import and response | Direct | `tests/test_pipe_minor_losses.py` | Direct and INP-loaded variants. |
| Unsteady friction toggle | Direct | `tests/test_boundary_variations_and_losses.py` | Late-time damping comparison. |
| Pump trip / restart | Direct | `tests/test_pump_valve_transients_from_inp.py` | Imported network transient regression. |
| Complex imported topology | Direct | `tests/test_complex_topology_from_inp.py` | EPANET/wntr operating-point and transient checks. |
| Standpipe protection | Direct | `tests/test_standpipe_surge_protection.py`, `tests/test_tank_size_benchmark.py` | Analytical and sweep coverage. |
| Hydropneumatic protection | Direct | `tests/test_surge_device_mitigation.py`, size / placement benchmarks | Size, placement, and pipe-length effects. |
| Air-valve protection | Direct | `tests/test_air_valve.py`, air-dominant benchmarks | Single-device and mixed-device regimes. |
| Mixed protection layouts | Direct | `tests/test_mixed_device_interaction_benchmark.py`, related sweeps | Combined-device interaction coverage. |
| Long-run stability / column separation | Direct | `tests/test_column_separation_and_stability.py` | Stability and cavitation-oriented regression. |

## Current Gaps To Close

No known feature/surface coverage gaps remain in the current public API matrix.