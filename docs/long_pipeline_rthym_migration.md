# R-THYM Migration: Long-Pipeline Profiles & Interior DVCM

This guide helps **R-THYM web-app integrators** adopt long-pipeline features shipped
in Phases 1–5 of [long_pipeline_surge_roadmap.md](long_pipeline_surge_roadmap.md):
per-pipe profile export, terrain surveys, interior-point DVCM, grid scaling, and
chainage air valves.

It is a **migration checklist**. Field-level API reference, JSON naming, and UI
patterns live in [dvcm_web_integration.md](dvcm_web_integration.md). Junction-only
DVCM migration (timestep, node telemetry) remains in
[dvcm_migration.md](dvcm_migration.md).

---

## 1. Zero-change default

Upgrading the solver package does **not** change existing R-THYM studies:

| Setting | Default | Effect on legacy UI |
|---|---|---|
| `record_pipe_profiles` | `False` | No new keys in `run()` results |
| `enable_interior_dvcm` | `False` | Junction-only DVCM (or LegacyClamp) unchanged |
| `PipeInput.elevation_profile` | empty | Linear interpolation between endpoint node elevations |
| `set_max_segments_per_pipe()` | `0` (uncapped) | Same grid as pre–Phase 4 |
| WASM `get_step_results()` | unchanged | Still node/link gauges only (§6 below) |

No backend or frontend changes are required until the product enables long-line
views.

---

## 2. Before vs after (what R-THYM can show)

| User need | Pre–long-pipeline R-THYM | After migration |
|---|---|---|
| HGL / pressure **along** a multi-mile pipe | Not available (node heads only) | Batch `run(record_pipe_profiles=True)` → chainage grids or `summarize_study()` envelopes |
| Worst pressure at a **summit** between junctions | Missed (flat pipe between terminals) | `elevation_profile` + profiles → `profile_peak.pressure_min` |
| Column separation **mid-reach** | Hidden by LegacyClamp or junction-only DVCM | `enable_interior_dvcm=True` → `pipe_profile_cavity_*` |
| Quick subatmospheric map (screening) | `node_cavitation` at junctions only | `pipe_profile_cavitation` along the line (not physical cavity volume) |
| Summit vacuum breaker placement | Manual junction in schematic | `attach_air_valve_at_survey_high_point()` (topology split) |
| 10–20 mile run within interactive budget | Often impractical at fine `dt` | `set_grid_policy(max_segments_per_pipe=2000, …)` |

---

## 3. Recommended rollout (incremental)

Adopt in order so each layer builds on the previous one.

### Step A — Survey data on pipes (Phase 2)

**Backend / model editor**

1. Persist `elevation_profile` on each long transmission pipe — at least two
   `(chainage_ft, elevation_ft)` pairs from the upstream end.
2. Optional: import from EPANET INP `[RTHYM] PipeElevation` rows (see README
   *EPANET import*).
3. SI projects: use `pipe_si(..., elevation_profile_m=...)`.

**UI**

- Add a survey table or GIS import path; no change to `run()` yet.
- Static preview: min gauge pressure at summit chainage before transient (see
  `tests/test_pipe_elevation_profile.py`).

**No new result keys** until Step B.

### Step B — Profile export for charts (Phase 1)

**Backend batch run** (after study completes or on “Analyze line” action):

```python
results = solver.run(
    total_time=total_time_s,
    dt=dt_s,
    record_pipe_profiles=True,
    profile_stride=profile_stride,  # see §5
)
summary = summarize_study(results, dt_s=dt_s)
```

**Forward to frontend** (camelCase suggested in
[dvcm_web_integration.md §4.2](dvcm_web_integration.md#42-results-keys-us-customary)):

- Full time–distance: `profileChainageFt`, `profileHeadFt`, `profilePressurePsi`, …
- Envelope-only (smaller payload): `summary["pipes"][pipe_id]["chainage_envelope"]`
- Worst point on schematic: `summary["pipes"][pipe_id]["profile_peak"]["pressure_min"]`

**Frontend**

- Add profile chart tab (distance on x-axis).
- Keep existing node time-series views; profiles are **additive**.

### Step C — Interior DVCM on long reaches (Phase 3)

Required when the product must show **physical** vapor cavities between junctions
(LP-03 / LP-04 class studies).

**Backend**

```python
results = solver.run(
    total_time=total_time_s,
    dt=dt_s,  # <= 0.001 s when DVCM is on — enforce in UI (§7)
    cavitation_model=rthym_moc.CavitationModel.DVCM,
    record_pipe_profiles=True,
    enable_interior_dvcm=True,
    profile_stride=profile_stride,
)
```

**New result keys** (only when both `record_pipe_profiles=True` and
`enable_interior_dvcm=True`):

- `pipe_profile_cavity_volume`
- `pipe_profile_cavity_active`
- `pipe_interior_dvcm_grid_indices` (non-empty when sparse watchpoints are used)

**UI distinction** (do not conflate):

| Key | Meaning |
|---|---|
| `profileCavitationScreen` | Gauge P ≤ vapor at local `z(x)` — screening only |
| `profileCavityVolumeFt3` / `profileCavityActive` | DVCM vapor pocket state |

**Sparse mode (recommended for multi-mile runs):** set watchpoints at summits only:

```python
pipe.interior_dvcm_chainages_ft = [summit_chainage_ft]
```

See `tests/long_pipeline_surge_utils.py` and
`tests/test_sparse_interior_dvcm.py`.

### Step D — Grid cap for runtime (Phase 4)

Before enabling profiles + interior DVCM on **10+ mile** pipes, cap the MOC grid:

```python
solver.set_grid_policy(
    max_segments_per_pipe=2000,
    max_wave_speed_distortion=0.15,
    distortion_action="warn",
)
```

Surface `pipe_num_segments`, `pipe_distortion_pct`, and
`summarize_study()["meta"]` / per-pipe grid fields so the UI can warn when
distortion is high. Reference budget: **LP-PERF-01** (< 30 s wall clock for
20 mi / `dt=0.001` / 60 s simulated — see
[long_pipeline_phase0_baseline.md §4](long_pipeline_phase0_baseline.md#reference-case-lp-perf-01)).

### Step E — Summit air valves (Phase 5, optional)

When users add a vacuum breaker on a long reach:

1. Call `attach_air_valve_at_survey_high_point(net, pipe_id)` (or explicit
   chainage).
2. **Persist topology mapping** `{original_id → (upstream_id, valve_id, downstream_id, chainage_ft)}`
   — link ids change after split.
3. Re-run Step C on the protected network; compare max cavity volume at the summit
   chainage vs an unprotected baseline ([dvcm_web_integration.md §2.2](dvcm_web_integration.md#22-summit-air-valves-at-a-chainage-phase-5)).

---

## 4. End-to-end backend example

Canonical pattern used in Phase 7 validation (`tests/long_pipeline_surge_utils.py`):

```python
import rthym_moc as m
from rthym_moc.report import summarize_study

solver = m.MOCSolver()
# … add nodes, pipe with elevation_profile …
solver.set_grid_policy(
    max_segments_per_pipe=2000,
    max_wave_speed_distortion=0.15,
    distortion_action="warn",
)

results = solver.run(
    total_time=8.0,
    dt=0.001,
    cavitation_model=m.CavitationModel.DVCM,
    record_pipe_profiles=True,
    enable_interior_dvcm=True,
)

summary = summarize_study(results, dt_s=0.001)
envelope = summary["pipes"]["Pmain"]["chainage_envelope"]
peak = summary["pipes"]["Pmain"]["profile_peak"]["pressure_min"]
# Forward envelope / peak / optional full profiles to R-THYM JSON API
```

Notebook mirror: `examples/long_pipeline_surge_verification.ipynb`.

---

## 5. Payload and performance guardrails

| Run length | Suggested `profile_stride` | Suggested API to UI |
|---|---|---|
| < 1 mile | `1` | Full `(N, M)` profiles acceptable |
| 1–5 mile | `2`–`4` | Profiles or `chainage_envelope` |
| 5–20 mile | `4`–`8` | Prefer `summarize_study()` envelopes; full grid on demand only |
| Any + interior DVCM | Same stride rules | Cavity heatmaps use same chainage axis as head/pressure |

Rules of thumb:

1. Default **`record_pipe_profiles=False`** for quick node-only reruns.
2. Enable profiles only when the user opens a line chart or export.
3. Do not ship raw `(N, M)` arrays to the browser for 20-mile / minute-long runs
   without stride or envelope downsampling.

---

## 6. WASM vs batch API (do not merge code paths yet)

| Feature | WASM stepping (`get_step_results()`) | Python batch `run()` |
|---|---|---|
| Node head, link flow | Yes | Yes |
| Junction `cavityVolume` (DVCM) | Yes | Yes (`node_cavity_*`) |
| Air-valve `gasVolume` | Yes | Yes (node telemetry) |
| Interior profile head/pressure | **No** | Yes (`pipe_profile_*`) |
| Interior cavity volume | **No** | Yes (`pipe_profile_cavity_*`) |

Long-line profile and interior-cavity charts require a **backend re-run** (or a
future WASM extension — tracked in
[dvcm_web_integration.md §4.4](dvcm_web_integration.md#44-r-thym-ui-integration-patterns)).
Do not assume profile keys exist in browser step results.

---

## 7. UI guardrails (carry over from junction DVCM)

When the user enables interior DVCM or long-line DVCM studies:

1. Recommend or enforce **`dt ≤ 0.001 s`** (see [dvcm_timestep_guidance.md](dvcm_timestep_guidance.md)).
2. Warn when `dt > 0.001 s` and `CavitationModel.DVCM` is selected.
3. On `RuntimeError` (NaN/Inf guards), prompt to halve `dt`.
4. When grid cap is active, show **distortion %** from run metadata.

---

## 8. Migration checklist (R-THYM team)

**Model / persistence**

- [ ] Store `elevation_profile` per long pipe (or INP `[RTHYM] PipeElevation`).
- [ ] Optional: store `interior_dvcm_chainages_ft` for sparse summit watchpoints.
- [ ] After air-valve placement: persist split-pipe id mapping.

**Backend**

- [ ] Add batch endpoint or worker path calling `run(record_pipe_profiles=True, …)`.
- [ ] Pass `enable_interior_dvcm=True` only for long-line DVCM studies.
- [ ] Apply `set_grid_policy()` when pipe length × `1/dt` exceeds budget.
- [ ] Serialize profile keys or `summarize_study()` envelopes (see
      [dvcm_web_integration.md §4.2–4.3](dvcm_web_integration.md#42-results-keys-us-customary)).

**Frontend**

- [ ] Profile chart (chainage vs head/pressure).
- [ ] Distinguish cavitation **screen** vs **cavity volume** series.
- [ ] Envelope ribbon and `profile_peak` marker on schematic.
- [ ] Optional: before/after summit mitigation view (baseline vs air-valve run).
- [ ] Timestep and grid-distortion warnings.

**Testing**

- [ ] Parity with `tests/test_long_pipeline_surge.py` metrics on a sloping reach.
- [ ] Regression: legacy studies still pass with all new flags left at defaults.

---

## 9. Related documents

| Document | Use |
|---|---|
| [dvcm_web_integration.md](dvcm_web_integration.md) | Telemetry keys, JSON names, UI patterns |
| [dvcm_migration.md](dvcm_migration.md) | Junction DVCM opt-in and timestep |
| [long_pipeline_surge_roadmap.md](long_pipeline_surge_roadmap.md) | Phase scope and validation cases LP-01–LP-08 |
| [dvcm_timestep_guidance.md](dvcm_timestep_guidance.md) | Courant, grid cap, interior DVCM `dt` |
| [validation.md](validation.md) | Independent checks for long-pipeline pytest modules |

Reference tests: `tests/test_pipe_profile_export.py`,
`tests/test_interior_dvcm_sloping_pipe.py`, `tests/test_long_pipeline_surge.py`,
`tests/test_chainage_air_valve.py`, `tests/test_dvcm_air_valve.py`.
