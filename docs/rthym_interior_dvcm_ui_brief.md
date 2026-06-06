# R-THYM UI Brief: Interior DVCM on Long Pipelines

**Audience:** R-THYM web application developers (frontend, backend, product)  
**Solver reference:** rthym-moc long-pipeline Phases 1–7 (interior-point DVCM)  
**API / JSON naming:** [dvcm_web_integration.md](dvcm_web_integration.md)  
**Backend rollout:** [long_pipeline_rthym_migration.md](long_pipeline_rthym_migration.md)

---

## 1. What changed (plain language)

Previously, R-THYM could show **vapor cavities only at network nodes** (junctions, valves, pumps) when DVCM was enabled. On a multi-mile pipe with only two end nodes, column separation at a **terrain summit between junctions** was invisible — LegacyClamp flattened it, and junction-only DVCM had nowhere to attach a cavity.

The solver now supports **interior-point DVCM**: discrete vapor pockets tracked at MOC grid stations **along the pipe**, using local ground elevation from a survey table. The UI can answer:

- *Where along the line did column separation occur?*
- *How large was the vapor pocket, and when did it collapse?*
- *Did a summit air valve prevent the cavity?*

This is **opt-in**. Legacy studies unchanged until the product enables profile export and interior DVCM on batch runs.

---

## 2. What the backend must send (minimum contract)

Interior cavity data exists **only** when all of the following are true on the Python batch `run()`:

| Backend flag | Required value |
|---|---|
| `cavitation_model` | `CavitationModel.DVCM` |
| `record_pipe_profiles` | `True` |
| `enable_interior_dvcm` | `True` |
| `PipeInput.elevation_profile` | Non-empty survey (≥ 2 chainage/elevation pairs) |

**WASM stepping (`get_step_results()`) does not expose interior profiles today.** Long-line cavity maps require a **post-run batch re-run** (or future WASM extension). Do not expect cavity ribbons from live step playback until that lands.

### 2.1 Primary payload (per pipe)

| Python key | Suggested JSON | Shape | Meaning |
|---|---|---|---|
| `pipe_profile_chainage_ft` | `profileChainageFt` | `(M,)` | Distance from upstream pipe end, ft |
| `pipe_profile_cavity_volume` | `profileCavityVolumeFt3` | `(N, M)` | Physical vapor volume at each station, ft³ |
| `pipe_profile_cavity_active` | `profileCavityActive` | `(N, M)` | `1` while a cavity is open at that station |
| `pipe_profile_pressure` | `profilePressurePsi` | `(N, M)` | Gauge pressure (context for collapse spikes) |
| `time` | `timeS` | `(N,)` | Simulation time axis |

Optional context keys: `pipe_num_segments`, `pipe_distortion_pct`, `pipe_interior_dvcm_grid_indices`.

### 2.2 Lighter payload (schematic overlays)

When full `(N, M)` arrays are too large, use `summarize_study(results)` and send:

| Summary path | Use on schematic |
|---|---|
| `pipes[id].profile_peak.pressure_min` | `{ value, time_s, chainage_ft }` — worst subatmospheric point |
| `pipes[id].chainage_envelope` | Min/max pressure vs chainage ribbon on profile chart |

For cavity-specific peaks, compute on the backend once:

```python
vol = np.asarray(results["pipe_profile_cavity_volume"][pipe_id])  # (N, M)
x = np.asarray(results["pipe_profile_chainage_ft"][pipe_id])      # (M,)
t = np.asarray(results["time"])

peak_vol = float(vol.max())
ti, mi = np.unravel_index(vol.argmax(), vol.shape)
cavity_peak = {
    "maxVolumeFt3": peak_vol,
    "timeS": float(t[ti]),
    "chainageFt": float(x[mi]),
}
# Extent along line while any cavity active:
active = np.asarray(results["pipe_profile_cavity_active"][pipe_id]) > 0
if active.any():
    cols = np.where(active.any(axis=0))[0]
    cavity_extent = {
        "chainageStartFt": float(x[cols[0]]),
        "chainageEndFt": float(x[cols[-1]]),
    }
```

Forward `cavity_peak` and `cavity_extent` for schematic highlighting without shipping the full grid.

### 2.3 Do not conflate these two series

| Series | JSON name | Physical meaning | UI treatment |
|---|---|---|---|
| `pipe_profile_cavitation` | `profileCavitationScreen` | Gauge P ≤ vapor at local `z(x)` | Yellow “at risk” screening; may be true without a DVCM pocket |
| `pipe_profile_cavity_volume` | `profileCavityVolumeFt3` | Integrated vapor pocket volume | Red / purple “void active”; use for mitigation proof |

Show both in a legend. Users will misread mitigation if only the screening flag is colored.

---

## 3. Recommended UI surfaces

### Tier 1 — Profile chart (primary, ship first)

**Time–distance heatmap** or **chainage line chart** for the selected pipe:

| Chart | X-axis | Y-axis / color | Data |
|---|---|---|---|
| Pressure envelope | Chainage | Min/max psi vs distance | `chainage_envelope` |
| Cavity volume heatmap | Chainage | Time | `profileCavityVolumeFt3` |
| Cavity active ribbon | Chainage | Binary band | `profileCavityActive` |

Interaction: scrubbing time on the heatmap updates the schematic highlight (§4).

Reference validation notebook: `examples/long_pipeline_surge_verification.ipynb` (LP-02–LP-04 checks: summit static min, interior cavity, collapse spike).

### Tier 2 — Schematic map overlay (your pipe-link highlight idea)

**Yes — highlighting the pipe link in the void region is a good pattern**, with these constraints:

1. **Map chainage → geometry, not “whole link on/off.”**  
   A cavity is a **segment of the link** from `chainageStartFt` to `chainageEndFt` (time-varying). Color only the sub-polyline between those chainages.

2. **Use the elevation survey for placement.**  
   If the schematic draws the pipe as a straight line between nodes, place the highlight by linear interpolation:  
   `fraction = chainage_ft / pipe.length_ft`  
   If GIS/survey polyline exists, walk accumulated distance along vertices using `elevation_profile` / stored survey points.

3. **Encode severity, not just presence.**

   | Visual | Condition |
   |---|---|
   | Dashed amber outline | `profileCavitationScreen` true, volume ≈ 0 |
   | Solid orange stroke | `profileCavityActive` true, volume > 0 |
   | Stroke width or glow ∝ `volume / maxVolume` | Pocket growing |
   | Magenta flash on collapse | `volume[step] < volume[step-1]` at station (secondary hammer) |

4. **Animate with time slider.**  
   At each timestep `n`, highlight stations where `profileCavityActive[n, m] == 1`. The void “moves” along the link as pockets open and close — a static full-link highlight misrepresents the physics.

5. **Multi-pipe networks.**  
   Each pipe id has its own `(N, M)` grid. After summit air-valve placement, the original link becomes `{id}_up` and `{id}_dn`; highlights follow the new ids.

**ASCII schematic (side view + map):**

```
  Elevation profile          Schematic (plan)
       summit                      R1 ●━━━━━━━━━━━━━━● R2
        /\                        ↑ orange segment = cavity extent
       /  \                           at chainage 40–60% 
  ────/────\────
      ^ cavity here (not at R1 or R2)
```

### Tier 3 — Mitigation / before–after (air valve workflow)

1. **Run A (baseline):** no summit valve, interior DVCM on → store profiles.  
2. **Run B (protected):** `attach_air_valve_at_survey_high_point` → split topology → interior DVCM on.  
3. UI: side-by-side heatmaps or Δ badge at summit chainage:  
   *“Peak cavity 0.08 ft³ → 0.00 ft³ after AV_summit”*

Node-level air telemetry (`gasVolume`, `gasPressure` on the valve) still comes from WASM stepping on the valve node; interior cavity proof is batch-only.

### Tier 4 — Inspector / summary panel

When user selects a pipe or cavity highlight:

- Peak cavity volume (ft³) and time  
- Chainage range while active  
- Collapse count (derive from volume drops)  
- Link to profile chart tab  
- Grid metadata: segment count, distortion % (warn if cap was used)

---

## 4. Implementation recipe: chainage highlight on a link

Assuming the frontend already draws pipe `Pmain` from node `from` to `to`:

```javascript
// Precomputed on backend or once after run loads:
// profileChainageFt[M], profileCavityActive[N][M], timeS[N]

function cavityExtentAtTime(n, activeGrid, chainageFt) {
  const activeCols = [];
  for (let m = 0; m < chainageFt.length; m++) {
    if (activeGrid[n][m]) activeCols.push(m);
  }
  if (activeCols.length === 0) return null;
  return {
    startFt: chainageFt[activeCols[0]],
    endFt: chainageFt[activeCols[activeCols.length - 1]],
  };
}

function chainageToPoint(fromXY, toXY, chainageFt, pipeLengthFt) {
  const t = chainageFt / pipeLengthFt; // 0 = from_node end
  return {
    x: fromXY.x + t * (toXY.x - fromXY.x),
    y: fromXY.y + t * (toXY.y - fromXY.y),
  };
}

// Draw partial highlight:
// const ext = cavityExtentAtTime(timeIndex, profileCavityActive, profileChainageFt);
// if (ext) drawLinkSegment(from, to, ext.startFt, ext.endFt, { color: '#e85d04', width: 6 });
```

For **survey-following polylines**, replace linear `from→to` interpolation with distance-along-polyline using stored `(chainage, lat/lng or x/y)` vertices.

**Z-order:** draw cavity highlight above the base link, below node icons and air-valve symbols.

---

## 5. Product guardrails (show in UI)

| Rule | Rationale |
|---|---|
| Enforce or strongly recommend `dt ≤ 0.001 s` when DVCM + interior enabled | Volume integration stability |
| Warn when `dt > 0.001 s` and DVCM selected | Overshoot risk |
| Apply `max_segments_per_pipe` (e.g. 2000) on 10+ mile pipes | LP-PERF-01 budget (< 30 s) |
| Default `profile_stride ≥ 4` on long runs | JSON size |
| Show distortion % when grid cap active | User trust in coarsened grid |
| Label “Screening” vs “DVCM cavity” in legend | Prevent false mitigation reads |

---

## 6. Phased rollout (matches backend)

| Phase | User-visible feature | Backend |
|---|---|---|
| A | Survey table / GIS import on long pipes | Persist `elevation_profile` only |
| B | “Analyze line” profile chart (H, P vs chainage) | `record_pipe_profiles=True` |
| C | Cavity heatmap + **link segment highlight** | + `enable_interior_dvcm=True`, DVCM |
| D | Performance warnings, grid cap badge | `set_grid_policy(...)` |
| E | “Add summit air valve” + before/after | `attach_air_valve_at_survey_high_point` |

Ship B and C together if possible — pressure context without cavity volume invites misinterpretation on sloping lines.

---

## 7. Edge cases for frontend

| Case | Behavior |
|---|---|
| No `elevation_profile` | Interior DVCM uses endpoint elevation interpolation; summit cavities may be wrong — UI should prompt for survey on pipes > 1 mi |
| Sparse watchpoints (`interior_dvcm_chainages_ft`) | Cavity data only at snapped stations; highlight may be a **point** not a span — widen glyph slightly for visibility |
| Pipe split after air valve | Original id gone; use persisted `{original → up, valve, dn}` mapping |
| LegacyClamp cavitation model | No `profileCavityVolumeFt3`; only screening flag if profiles on |
| Single short pipe between valves | Interior + junction DVCM both active; node badges and link segment highlight complement each other |

---

## 8. Testing parity (acceptance)

Backend/UI integration tests should align with:

- `tests/test_long_pipeline_surge.py` — directional LP-02–LP-04  
- `tests/test_dvcm_air_valve.py` — summit cavity eliminated with air valve  
- `tests/test_interior_dvcm_sloping_pipe.py` — interior volume > 0 on sloping reach  

Manual QA: 5-mile sloping case (`tests/long_pipeline_surge_utils.py`) — cavity peak near mid-chainage summit, collapse spike after downstream refill.

---

## 9. Summary answer: pipe link highlighting

**Yes, highlight the pipe link — but as a chainage-bounded segment on that link, animated over time, with color/weight tied to `profileCavityVolumeFt3`.**  

Treat the profile chart (time × distance heatmap) as the authoritative view; use schematic segment highlighting as a spatial index that drives selection and communicates *where* on the line the user should look. Avoid coloring the entire link solid red for the whole run — cavities are localized and transient.

---

## 10. Related repo documents

| Document | Content |
|---|---|
| [dvcm_web_integration.md](dvcm_web_integration.md) | WASM vs batch, JSON field names, serialization example |
| [long_pipeline_rthym_migration.md](long_pipeline_rthym_migration.md) | Incremental backend checklist |
| [dvcm_timestep_guidance.md](dvcm_timestep_guidance.md) | Timestep and grid-cap tradeoffs |
| [README.md § Long-pipeline surge](../README.md#long-pipeline-surge--interior-dvcm) | Minimal Python example |

**Questions:** solver/API issues → rthym-moc maintainers; R-THYM product UX → Lillywhite Water Solutions web team.
