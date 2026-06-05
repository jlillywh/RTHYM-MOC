# R-THYM Web App Integration Guide

This document provides developer reference details for integrating version `0.4.0+` solvers into the proprietary **R-THYM** web application frontend. It covers:

- **Step telemetry** — per-timestep keys from WebAssembly (`get_step_results()`): DVCM cavities, air-valve gas pockets, and link summaries.
- **Batch profile export** — optional per-pipe interior head/pressure/velocity grids from the Python `run()` API (long-pipeline profile charts and envelope views).

---

## 1. WebAssembly (WASM) step telemetry

When running the MOC solver step-by-step in the browser via WebAssembly (`get_step_results()`), the step results dictionary contains the following telemetry properties per node:

### A. Vapor Cavity Telemetry (DVCM)
These fields are populated when `cavitation_model` is set to `DVCM` (value `1` in the enum):
* **`cavityVolume`** ($\text{ft}^3$): The current volume of the water vapor pocket.
* **`cavityActive`** (`true`/`false`): Whether column separation is currently active at this node.
* **`cavityCollapseFlag`** (`true`/`false`): Set to `true` on the exact timestep the cavity transitions into the collapse regime.
* **`cavityCollapseCount`** (`int`): Cumulative count of cavity collapse events for this node.

### B. Gas/Air Pocket Telemetry (Air Valves & Tanks)
These fields are populated when surge devices (like `AirValve` or `HydropneumaticTank`) are present:
* **`gasVolume`** ($\text{ft}^3$): The volume of the air pocket currently admitted or trapped at the device.
* **`gasPressure`** ($\text{psi}$): The pneumatic pressure of the air pocket.
* **`airLossRate`** ($\text{gpm}$): The current venting rate of air.
* **`airCumulativeLoss`** ($\text{gal}$): The cumulative volume of air vented.

### C. Link (pipe) step telemetry (current WASM schema)

Each entry under `links[<pipe_id>]` today exposes aggregate link state only:

| Key | Type | Unit | Description |
|---|---|---|---|
| `flowGPM` | `number` | GPM | Pipe flow (area-weighted mean velocity × area) |
| `headloss` | `number` | ft | Absolute head difference across the pipe (`|H_upstream − H_downstream|`) |

**Interior MOC grid profiles are not yet exposed in `get_step_results()`.** Long-pipeline profile charts must use the batch Python API (§4) or a backend service that calls `run(record_pipe_profiles=True)` and forwards the payload to the UI. A future WASM extension would add profile arrays under `links` (see §4.4).

---

## 2. Engineering Benefits: Coexistence & Mitigation Analysis

Exposing both DVCM and Air Valve telemetry in the R-THYM UI enables users to perform **surge mitigation effectiveness analysis**:

* **Concurrent Modeling**: Users can place an `AirValve` at a high point in their system and track how much air it admits (`gasVolume`). Simultaneously, they can monitor neighboring junctions using DVCM (`cavityVolume`).
* **Visualizing Effectiveness**: In the UI chart:
  - If the `AirValve` is sized correctly, the neighboring junctions will show `cavityVolume = 0` (column separation prevented).
  - If the `AirValve` is undersized, the UI will show secondary vapor cavities (`cavityVolume > 0`) forming and collapsing downstream.
  - Without DVCM, secondary vapor pockets are flat-lined by legacy clamping, making it impossible to see if they were truly mitigated.

---

## 3. UI Guardrails & Timestep Enforcement

Because the DVCM is a physical model requiring integration of small volume increments over time:

1. **Timestep Alert**: When a user selects `DVCM` in the UI, the frontend should recommend or enforce a timestep **`dt <= 0.001s`** (ideally `0.0001s`).
2. **Coarse Timestep Warning**: If the user runs the simulation with `dt > 0.001s` and `DVCM` enabled, a warning should be displayed stating that numerical volume overshoot may occur.

---

## 4. Per-pipe MOC profiles (Python batch API)

Phase 1 pipe profile export is **opt-in** on `MOCSolver.run()` and is intended for R-THYM long-pipeline visualization (HGL/pressure/velocity vs chainage, and time–distance heatmaps). It does **not** change WASM step telemetry in §1.

### 4.1 Enabling export

```python
results = solver.run(
    total_time=10.0,
    dt=0.01,
    record_pipe_profiles=True,  # default False — omit keys when False
    profile_stride=1,           # spatial downsampling; pipe ends always kept
)
```

| Parameter | Default | R-THYM notes |
|---|---|---|
| `record_pipe_profiles` | `False` | Enable when the UI needs interior pipe grids or chainage envelopes. Leave off for legacy node-only charts. |
| `profile_stride` | `1` | Use `2`–`8` on multi-mile pipes to cap JSON payload size. End stations are always retained regardless of stride. |

SI projects: pass the same flags to `run_si()`; profile keys are `pipe_profile_chainage_m`, `pipe_profile_head_m`, `pipe_profile_pressure_kpa`, and `pipe_profile_velocity_m_s`.

### 4.2 Results keys (US customary)

Absent unless `record_pipe_profiles=True`.

| Python key | Per-pipe shape | Unit | Description |
|---|---|---|---|
| `pipe_profile_chainage_ft` | `(M,)` | ft | Distance from upstream pipe end (`from_node`) |
| `pipe_profile_head` | `(N, M)` | ft | Piezometric head at each chainage station |
| `pipe_profile_pressure` | `(N, M)` | psi | Gauge pressure (linear elevation interpolation between endpoint node elevations) |
| `pipe_profile_velocity_fps` | `(N, M)` | ft/s | Velocity at each chainage station |

`N` = number of recorded time steps (`len(results["time"])`). `M` = profile points along the pipe after downsampling. Index `0` / `M−1` are the upstream and downstream pipe ends; those heads match `node_head` at the boundary nodes.

Suggested R-THYM JSON field names when serializing for the frontend (camelCase, consistent with §1):

| Python key | Suggested R-THYM JSON key |
|---|---|
| `pipe_profile_chainage_ft` | `profileChainageFt` |
| `pipe_profile_head` | `profileHeadFt` |
| `pipe_profile_pressure` | `profilePressurePsi` |
| `pipe_profile_velocity_fps` | `profileVelocityFps` |

### 4.3 Study envelopes (smaller payload)

When the UI only needs min/max head or pressure **vs chainage** (not the full time–distance grid), call `summarize_study(results)` after `run()` and read `summary["pipes"][pipe_id]`:

| Key | Description |
|---|---|
| `chainage_envelope` | `chainage_ft` plus `head_min_ft` / `head_max_ft`, `pressure_min_psi` / `pressure_max_psi`, and velocity min/max when recorded |
| `profile_peak` | Global worst point on the `(time × chainage)` surface per quantity (`value`, `time_s`, `chainage_ft`) — e.g. `pressure_min` for subatmospheric location |

Use `summarize_study_si()` for `chainage_m`, `head_min_m`, `pressure_min_kpa`, etc. This path matches the roadmap memory guardrail: envelope-only views avoid shipping `(N, M)` arrays to the browser.

### 4.4 R-THYM UI integration patterns

| Use case | Recommended source |
|---|---|
| Real-time node/link gauges during interactive stepping | WASM `get_step_results()` — §1 only |
| Long-pipeline profile chart after run completes | Backend `run(record_pipe_profiles=True)` → forward §4.2 keys (optionally downsampled with `profile_stride`) |
| Envelope ribbon (min/max HGL vs distance) | `summarize_study()` → `chainage_envelope` (§4.3) |
| Mark worst pressure location on schematic | `summarize_study()` → `profile_peak.pressure_min` |

**WASM gap (tracked):** `src/wasm_bindings.cpp` does not yet mirror §4.2 under `links`. When added, expect nested arrays on each link object using the camelCase names in §4.2; until then, do not assume profile keys exist in browser step results.

### 4.5 Payload sizing guardrails

For a 20-mile pipe with `dt = 0.01 s` and a 10-minute run, a full `(N, M)` profile can be large. R-THYM should:

1. Default `profile_stride` ≥ 4 for runs longer than ~5 miles unless the user explicitly requests full resolution.
2. Prefer `chainage_envelope` for static report exports and schematic overlays.
3. Downsample time in the frontend or backend if animating heatmaps (profile data is dense along both axes).

See [long_pipeline_surge_roadmap.md](long_pipeline_surge_roadmap.md) Phase 1 for performance and memory context.
