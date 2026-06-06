# R-THYM Web App Integration Guide

This document provides developer reference details for integrating version `0.4.0+` solvers into the proprietary **R-THYM** web application frontend. It covers:

- **Step telemetry** — per-timestep keys from WebAssembly (`get_step_results()`): DVCM cavities, air-valve gas pockets, and link summaries.
- **Batch profile export** — optional per-pipe interior head/pressure/velocity grids from the Python `run()` API (long-pipeline profile charts and envelope views).
- **Interior DVCM & cavity prevention UX** — profile-level vapor-cavity telemetry on long reaches, summit air-valve placement, and before/after mitigation views (Phases 3–5).

**Migration checklist (R-THYM):** [long_pipeline_rthym_migration.md](long_pipeline_rthym_migration.md) — incremental rollout for profile export and interior DVCM.

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

### 2.1 Long-line interior cavities (Phase 3)

On uninterrupted pipe reaches with an `elevation_profile`, vapor cavities can form **between** network junctions at local high points or low-pressure zones. Junction-only DVCM telemetry (`cavityVolume` on nodes) misses these events.

Enable interior-point DVCM on batch runs:

```python
results = solver.run(
    total_time=10.0,
    dt=0.001,
    cavitation_model=rthym_moc.CavitationModel.DVCM,
    record_pipe_profiles=True,
    enable_interior_dvcm=True,
)
```

When `enable_interior_dvcm=True` and profiles are recorded, the backend adds:

| Python key | Shape | R-THYM JSON (suggested) | Meaning |
|---|---|---|---|
| `pipe_profile_cavity_volume` | `(N, M)` per pipe | `profileCavityVolumeFt3` | DVCM vapor pocket volume at each chainage station, ft³ |
| `pipe_profile_cavity_active` | `(N, M)` per pipe | `profileCavityActive` | `1` when interior column separation is active at that station |
| `pipe_interior_dvcm_grid_indices` | `(K,)` per pipe | `interiorDvcmGridIndices` | MOC grid indices where sparse watchpoints were snapped (empty → full interior grid) |

**UI distinction:** `pipe_profile_cavitation` (always present when profiles are on) is a **pre-DVCM screening flag** — gauge pressure at local `z(x)` ≤ vapor pressure. Use it for quick subatmospheric maps. `pipe_profile_cavity_*` is the **physical DVCM state** and is the correct series for mitigation effectiveness on long lines.

Sparse watchpoints: set `PipeInput.interior_dvcm_chainages_ft` to limit interior DVCM to user-selected chainages (summits, low points). The backend snaps each chainage to the nearest MOC grid index and exports the resolved indices in `pipe_interior_dvcm_grid_indices`.

### 2.2 Summit air valves at a chainage (Phase 5)

R-THYM can place vacuum breakers on a long reach **without** asking the user to add a manual graph junction. The Python helpers (`attach_air_valve_at_survey_high_point`, `attach_air_valve_at_chainage`; see README *Surge control components*) split the pipe and insert an `AirValve` node that reuses the same compressible-air telemetry as §1.B (`gasVolume`, `gasPressure`, …).

**Recommended editor workflow**

1. User draws or imports a pipe with `elevation_profile` (or `[RTHYM] PipeElevation` from EPANET).
2. UI offers **“Add summit air valve”** → call `attach_air_valve_at_survey_high_point(net, pipe_id)` (or explicit chainage picker).
3. Refresh the schematic: the original pipe id is replaced by `{pipe_id}_up` and `{pipe_id}_dn` with a new node (e.g. `AV_summit`) at the split.
4. Re-run with `enable_interior_dvcm=True` and compare cavity profiles at the summit chainage.

**Topology note for the frontend:** Option A (current implementation) **changes link ids** after placement. Persist the mapping `{original_pipe_id → (upstream_id, valve_node_id, downstream_id, chainage_ft)}` so undo/redo and study comparison views stay consistent.

**Cavity / prevention UX patterns**

| View | Data source | What “good” looks like |
|---|---|---|
| Summit gas admission | WASM `gasVolume` / `gasPressure` on the air-valve node | Rises during low-pressure transient; finite, stable head at the valve |
| Interior cavity at summit | Batch `profileCavityVolumeFt3` at summit chainage on the **unprotected** baseline run | Peak volume > 0 while `profileCavityActive` is true |
| Mitigation check (same transient, valve added) | Batch profiles on `{pipe_id}_up` / `{pipe_id}_dn` at stations adjacent to the valve | Peak `profileCavityVolumeFt3` at the summit **eliminated or sharply reduced** vs baseline (reference: `tests/test_dvcm_air_valve.py::test_dvcm_long_line_summit_air_valve_prevents_cavity`) |
| Side-by-side schematic | Overlay baseline vs protected `profile_peak` or time–distance heatmap | User sees cavity ribbon disappear at the high point when the valve is sized adequately |

**Before/after comparison mode (suggested UI):**

1. Run A — no summit valve, `enable_interior_dvcm=True`, store profiles.
2. Run B — same network after `attach_air_valve_at_survey_high_point`, same transient.
3. Plot Δ max cavity volume vs chainage, or highlight summit chainage where Run A peak > 0 and Run B peak ≈ 0.

Interior watchpoints exactly **at** the split chainage are omitted (the valve node handles the summit). Rebased watchpoints on upstream/downstream reaches appear under the new pipe ids in `pipe_interior_dvcm_grid_indices`.

**WASM stepping:** Air-valve gas telemetry (§1.B) is available per step on the valve node. Interior profile cavities remain **batch-only** until WASM mirrors §4.2/§4.6; use a backend re-run for long-line prevention charts.

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
    dt=0.001,                   # use <= 0.001 s when DVCM is on (§3)
    cavitation_model=rthym_moc.CavitationModel.DVCM,
    record_pipe_profiles=True,  # default False — omit keys when False
    profile_stride=1,           # spatial downsampling; pipe ends always kept
    enable_interior_dvcm=True,  # default False — required for pipe_profile_cavity_* keys
)
```

| Parameter | Default | R-THYM notes |
|---|---|---|
| `record_pipe_profiles` | `False` | Enable when the UI needs interior pipe grids or chainage envelopes. Leave off for legacy node-only charts. |
| `profile_stride` | `1` | Use `2`–`8` on multi-mile pipes to cap JSON payload size. End stations are always retained regardless of stride. |
| `enable_interior_dvcm` | `False` | Enable for long-line **physical** cavity maps (`pipe_profile_cavity_*`). Requires `cavitation_model=DVCM` and `record_pipe_profiles=True`. |

SI projects: pass the same flags to `run_si()`; profile keys are `pipe_profile_chainage_m`, `pipe_profile_head_m`, `pipe_profile_pressure_kpa`, and `pipe_profile_velocity_m_s`.

### 4.2 Results keys (US customary)

Absent unless `record_pipe_profiles=True`.

| Python key | Per-pipe shape | Unit | Description |
|---|---|---|---|
| `pipe_profile_chainage_ft` | `(M,)` | ft | Distance from upstream pipe end (`from_node`) |
| `pipe_profile_head` | `(N, M)` | ft | Piezometric head at each chainage station |
| `pipe_profile_pressure` | `(N, M)` | psi | Gauge pressure (linear elevation interpolation between endpoint node elevations) |
| `pipe_profile_velocity_fps` | `(N, M)` | ft/s | Velocity at each chainage station |
| `pipe_profile_cavitation` | `(N, M)` | 0/1 | Screening flag: gauge pressure ≤ vapor at local `z(x)` (not DVCM volume) |
| `pipe_profile_cavity_volume` | `(N, M)` | ft³ | Interior DVCM vapor volume (only when `enable_interior_dvcm=True`) |
| `pipe_profile_cavity_active` | `(N, M)` | 0/1 | Interior DVCM active flag (only when `enable_interior_dvcm=True`) |
| `pipe_interior_dvcm_grid_indices` | `(K,)` | — | Snapped MOC indices for sparse `interior_dvcm_chainages_ft` watchpoints |

`N` = number of recorded time steps (`len(results["time"])`). `M` = profile points along the pipe after downsampling. Index `0` / `M−1` are the upstream and downstream pipe ends; those heads match `node_head` at the boundary nodes.

Suggested R-THYM JSON field names when serializing for the frontend (camelCase, consistent with §1):

| Python key | Suggested R-THYM JSON key |
|---|---|
| `pipe_profile_chainage_ft` | `profileChainageFt` |
| `pipe_profile_head` | `profileHeadFt` |
| `pipe_profile_pressure` | `profilePressurePsi` |
| `pipe_profile_velocity_fps` | `profileVelocityFps` |
| `pipe_profile_cavitation` | `profileCavitationScreen` |
| `pipe_profile_cavity_volume` | `profileCavityVolumeFt3` |
| `pipe_profile_cavity_active` | `profileCavityActive` |
| `pipe_interior_dvcm_grid_indices` | `interiorDvcmGridIndices` |

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
| Interior DVCM cavity heatmap / summit mitigation check | Backend `run(..., enable_interior_dvcm=True)` → `profileCavityVolumeFt3` / `profileCavityActive` (§2.1–2.2) |
| Place summit air valve from survey | Backend `attach_air_valve_at_survey_high_point` → refresh schematic pipe ids (§2.2) |
| Envelope ribbon (min/max HGL vs distance) | `summarize_study()` → `chainage_envelope` (§4.3) |
| Mark worst pressure location on schematic | `summarize_study()` → `profile_peak.pressure_min` |
| Before/after cavity prevention | Two batch runs (baseline vs protected) → compare max `profileCavityVolumeFt3` at summit chainage (§2.2) |

**WASM gap (tracked):** `src/wasm_bindings.cpp` does not yet mirror §4.2 under `links`. When added, expect nested arrays on each link object using the camelCase names in §4.2; until then, do not assume profile keys exist in browser step results.

### 4.5 Payload sizing guardrails

For a 20-mile pipe with `dt = 0.01 s` and a 10-minute run, a full `(N, M)` profile can be large. R-THYM should:

1. Default `profile_stride` ≥ 4 for runs longer than ~5 miles unless the user explicitly requests full resolution.
2. Prefer `chainage_envelope` for static report exports and schematic overlays.
3. Downsample time in the frontend or backend if animating heatmaps (profile data is dense along both axes).

See [long_pipeline_surge_roadmap.md](long_pipeline_surge_roadmap.md) Phase 1 for performance and memory context.

### 4.6 Example: serializing summit mitigation payload

After placing a summit valve and running with interior DVCM, a minimal backend JSON fragment for the prevention chart might look like:

```json
{
  "pipeId": "Pmain_up",
  "profileChainageFt": [0.0, 500.0, 1000.0],
  "profileCavityVolumeFt3": [[0, 0, 0], [0, 0.02, 0.04], [0, 0, 0]],
  "interiorDvcmGridIndices": [250],
  "summitValveNodeId": "AV_summit",
  "summitChainageFt": 2000.0
}
```

Pair with a baseline run on the unsplit pipe at the same `summitChainageFt` to populate a Δ volume badge in the UI (§2.2).
