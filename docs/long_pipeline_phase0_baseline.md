# Long Pipeline Surge — Phase 0 Baseline Notes

Date: 2026-06-05  
Purpose: Record pre-change solver behavior before [long_pipeline_surge_roadmap.md](long_pipeline_surge_roadmap.md) implementation.  
Use this document as the comparison point for Phase 1+ PRs.

**Tracking epic:** [GitHub #79](https://github.com/jlillywh/RTHYM-MOC/issues/79) (Phase 0 issue [#80](https://github.com/jlillywh/RTHYM-MOC/issues/80)).

---

## 1. Interior `H[j]` / `V[j]` computed but not exported

**Status:** Baseline recorded (Phase 0 checklist item 1).

### Summary

Each pipe maintains a full MOC grid in runtime state (`PipeState::H`, `PipeState::V`).
`stepMOC()` updates every grid index `j = 0 … N-1` each timestep, including interior
points `j = 1 … N-2`. `recordStep()` does **not** copy those arrays into `SimResults`;
Python `run()` therefore has no per-segment head, pressure, or velocity along a pipe.

### Runtime storage (`PipeState`)

```200:213:src/moc_solver.hpp
struct PipeState {
    ...
    int    num_nodes = 2;
    ...
    std::vector<double> H;          // head (ft)          [num_nodes]
    std::vector<double> V;          // velocity (ft/s)    [num_nodes]
    std::vector<double> V_filtered; // IIR-filtered V for unsteady friction
};
```

Grid count: `num_nodes = num_segs + 1`, where `num_segs = max(1, round(L / (a·dt)))`.
Indices `0` and `N-1` are pipe-end boundaries (coupled to network nodes); indices
`1 … N-2` are interior MOC solution points with no corresponding graph node.

### Interior update (`stepMOC`)

Interior heads and velocities are solved every step via characteristic pairing:

```836:848:src/moc_solver.cpp
        // ── Interior nodes  j = 1 … N-2  (C+ from left, C- from right) ───
        for (int j = 1; j < N - 1; ++j) {
            ...
            newH[i][j] = (C_P + C_M) / 2.0;
            newV[i][j] = (C_P - C_M) / (2.0 * B);
        }
```

After the node boundary-condition pass, `newH` / `newV` are copied back into
`pipes_[i].H[j]` and `pipes_[i].V[j]` for all `j`.

### Export schema (`SimResults`)

`SimResults` has no pipe-profile fields — only graph-node series and one scalar
flow per pipe:

```128:147:src/moc_solver.hpp
struct SimResults {
    ...
    std::unordered_map<std::string, std::vector<double>> node_head;    // ft
    std::unordered_map<std::string, std::vector<double>> node_pressure;// psi
    std::unordered_map<std::string, std::vector<double>> pipe_flow_gpm;// GPM
    ...
};
```

### What `recordStep()` actually records for pipes

For each pipe, `recordStep()` averages **all** segment velocities into a single
flow sample. Interior `H[j]` is never read for export:

```2261:2272:src/moc_solver.cpp
    for (int i = 0; i < static_cast<int>(pipes_.size()); ++i) {
        const auto& ps = pipes_[i];
        double avg_V = 0.0;
        for (double v : ps.V) {
            ...
            avg_V += v;
        }
        avg_V /= ps.num_nodes;
        results.pipe_flow_gpm[pipe_inputs_[i].id].push_back(avg_V * ps.area / GPM_TO_CFS);
    }
```

Node head telemetry uses pipe **end** faces only (`H.back()` / `H.front()`), not
interior indices — see `recordStep()` lines 2207–2220.

### Python bindings (`bindings.cpp`)

`results_to_dict()` mirrors `SimResults` exactly. Keys exported today:

| Key | Spatial resolution |
|-----|-------------------|
| `node_head` | One series per graph node |
| `node_pressure` | One series per graph node |
| `pipe_flow_gpm` | One cross-sectional-average series per pipe |
| `node_cavitation`, cavity_* | Per graph node only |

No `pipe_profile_*` keys exist in `bindings.cpp` or `_rthym_moc.pyi`.

### Implication for long pipelines

On a long uninterrupted reach (few graph nodes, many MOC segments):

- Wave propagation and friction damping along the line are computed correctly in
  `PipeState::H` / `V`.
- Users and R-THYM cannot read **where** along the line the minimum or maximum
  pressure occurs without adding junctions solely for telemetry.
- `pipe_flow_gpm` is a spatial mean and may differ from flow at a specific
  chainage during steep transients.

### Phase 1 target (from roadmap)

Add opt-in `pipe_profile_head`, `pipe_profile_pressure`, `pipe_profile_chainage_ft`
(and optionally `pipe_profile_velocity_fps`) populated from `pipes_[i].H[j]` /
`pipes_[i].V[j]` without changing default `run()` output when profiles are disabled.

### Reproducible check (current contract)

From repository root:

```bash
python -c "
import rthym_moc as m
s = m.MOCSolver()
s.add_node(m.NodeInput(id='R1', type='PressureBoundary', head=150.0))
s.add_node(m.NodeInput(id='R2', type='PressureBoundary', head=0.0))
s.add_pipe(m.PipeInput(id='P1', from_node='R1', to_node='R2',
                       length=3000.0, diameter=12.0, roughness=130.0, flow_gpm=500.0))
r = s.run(total_time=0.5, dt=0.01)
assert 'pipe_profile_head' not in r
assert 'pipe_profile_pressure' not in r
assert set(r.keys()) >= {'time', 'node_head', 'node_pressure', 'pipe_flow_gpm'}
print('OK: no pipe profile keys in run() results')
"
```

---

## 2. Vapor head uses node `elevation` only

**Status:** Baseline recorded (Phase 0 checklist item 2).

### Summary

Cavitation detection, LegacyClamp, and DVCM all key off a single vapor-grade
line per **graph node**:

$$H_\text{vap} = z_\text{node} + h_\text{vapor}$$

where `z_node` is `NodeInput::elevation` and `h_vapor` is the solver's stored
`p_vapor_` in **feet of head** (converted from the `p_vapor_psi` argument at
`run()` time). There is no per-chainage elevation on pipes, no interior
`H_vap(x)`, and no vapor logic on interior MOC indices `j = 1 … N-2`.

### Vapor threshold definition

Computed once per graph node at the start of the node boundary-condition loop in
`stepMOC()`:

```875:875:src/moc_solver.cpp
        const double H_vap = n.elevation + p_vapor_; // cavitation head (ft)
```

`p_vapor_` is initialized from the Python `p_vapor_psi` parameter (default
`-14.0` psi gauge) and stored internally as head:

```2291:2291:src/moc_solver.cpp
    p_vapor_ = p_vapor_psi * PSI_TO_FT; // convert psi → ft
```

```339:339:src/moc_solver.hpp
    double p_vapor_ = -14.0 * PSI_TO_FT; // ft (converted from psi at init)
```

Equivalent gauge-pressure form used in telemetry:

```2170:2171:src/moc_solver.cpp
        const double P_psi = (H - n.elevation) / PSI_TO_FT;
        const bool is_cavity_active = (P_psi <= P_vapor);
```

where `P_vapor = p_vapor_ / PSI_TO_FT` (line 2128).

### Where vapor logic applies (graph nodes only)

| Location | LegacyClamp (`H_P < H_vap`) | DVCM regime switching |
|----------|----------------------------|------------------------|
| `Junction` / `InflowNode` / `OutflowNode` | Yes (line 2108) | Yes (lines 2042–2099) |
| Inline `Valve` / `Pump` / `CheckValve` / `Turbine` (1 in + 1 out) | Yes | Yes (earlier in same switch) |
| `PressureBoundary` / `Tank` | No — fixed head BC | No |
| `Standpipe` / `HydropneumaticTank` / `AirValve` | Device-specific physics | Unsupported / preserved (see `test_dvcm_unsupported_nodes.py`) |
| **Interior MOC points** `j = 1 … N-2` | **No** | **No** |

Interior heads can fall below the physical vapor grade along a sloping reach;
the solver does not clamp or open a cavity there.

### `PipeInput` has no elevation data

```109:124:src/moc_solver.hpp
struct PipeInput {
    ...
    double  length           = 100.0;  // ft
    ...
    // no elevation, slope, or survey table fields
};
```

Initial head along a pipe is a **linear HGL** between endpoint boundary heads,
not a function of terrain elevation:

```615:623:src/moc_solver.cpp
        // ── Linear HGL + uniform velocity initial condition ───────────────
        ...
            ps.H[j] = H_start + (H_end - H_start) * t_frac;
```

Pipe endpoint **node** elevations are not used to set interior `H[j]` during
initialization or the MOC update.

### Junction / DVCM example

At a demand junction, cavity entry compares the solved head against the node's
single `H_vap`:

```2045:2046:src/moc_solver.cpp
                const bool enter_cavity = H_candidate <= (H_vap - H_CAVITY_ENTER_TOL);
                const bool leave_cavity = H_candidate >= (H_vap + H_CAVITY_LEAVE_TOL);
```

`H_vap` here is `Junction.elevation + p_vapor_`, not the elevation at the
high point of an adjacent pipe segment.

### Exported cavitation flag

`recordStep()` sets `node_cavitation` from gauge pressure at the node's
telemetry head, again using **node** elevation only:

```2223:2244:src/moc_solver.cpp
        const double P_psi   = (H - n.elevation) / PSI_TO_FT;
        const double P_vapor = p_vapor_ / PSI_TO_FT;
        ...
        results.node_cavitation[n.id].push_back(P_psi <= P_vapor ? 1 : 0);
```

No per-segment cavitation channel exists in `SimResults`.

### Implication for long sloping pipelines

Consider one pipe from terminal A (`z = 0`) to terminal B (`z = 0`) with a
physical high point at mid-length (`z = 300` ft) but **no graph node** at the
summit:

- Static gauge pressure is lowest at the summit, but the solver has no junction
  there and no `z(x)` along the pipe.
- Interior `H[j]` can imply subatmospheric gauge pressure at the true high point
  without triggering LegacyClamp or DVCM.
- Adding a junction at the summit is the only current workaround; its `elevation`
  field then sets `H_vap` for that point only, not for other chainages.

### Phase 2 target (from roadmap)

Add `PipeInput::elevation_profile` (or equivalent) and use interpolated `z[j]`
at each MOC grid point for:

- `H_vap(j) = z[j] + p_vapor_` in profile pressure export (Phase 1)
- Interior LegacyClamp / DVCM thresholds (Phase 3)

### Reproducible check (current contract)

From repository root:

```bash
python3 -c "
import rthym_moc as m

# PipeInput has no elevation / survey fields
pipe = m.PipeInput()
public = {k for k in dir(pipe) if not k.startswith('_')}
assert 'elevation' not in public
assert 'elevation_profile' not in public

# Uninterrupted two-reservoir line: no junction cavitation channel mid-line
s = m.MOCSolver()
s.add_node(m.NodeInput(id='R1', type='PressureBoundary', elevation=0.0, head=150.0))
s.add_node(m.NodeInput(id='R2', type='PressureBoundary', elevation=0.0, head=0.0))
s.add_pipe(m.PipeInput(id='P1', from_node='R1', to_node='R2',
                       length=30000.0, diameter=24.0, roughness=130.0, flow_gpm=2000.0))
r = s.run(total_time=2.0, dt=0.01, p_vapor_psi=-14.0,
          cavitation_model=m.CavitationModel.DVCM)
# Only boundary nodes exist; no interior graph node for cavity telemetry
assert set(r['node_cavity_volume'].keys()) == {'R1', 'R2'}
print('OK: vapor/cavity telemetry is node-only; PipeInput has no elevation profile')
"
```

---

## 3. Segment count and wave-speed adjustment (`initGrid()`)

**Status:** Baseline recorded (Phase 0 checklist item 3).

### Summary

Every `run()` call sets `dt_`, then rebuilds the MOC grid in `initGrid()`. For
each pipe the solver:

1. Computes a **design** wave speed `a_design` (rigid default or Korteweg).
2. Targets reach length `dx = a_design · dt`.
3. Rounds the segment count `N = max(1, round(L / dx))`.
4. **Back-adjusts** the wave speed to `a_adj = L / (N · dt)` so Courant number
   is exactly 1 on the stored grid.

There is **no** `max_segments_per_pipe` cap, no distortion report in results,
and no automatic `dt` selection — segment count grows linearly with `L / dt`.

### When the grid is built

```2290:2298:src/moc_solver.cpp
    dt_      = dt;
    ...
    initGrid();
```

`initGrid()` clears runtime `pipes_` / `nodes_` and reconstructs them from the
persistent `pipe_inputs_` / `node_inputs_` arrays. Changing `dt` between runs
changes `N` and `a_adj` even if the network topology is unchanged.

### Design wave speed (`a_design`)

```501:514:src/moc_solver.cpp
        double wave_speed = 4000.0; // ft/s  default (rigid pipe approximation)
        if (p.youngs_modulus > 0.0) {
            ...
            wave_speed = a0 / std::sqrt(
                1.0 + (K / p.youngs_modulus) * (d_in / t_in) * c);
        }
```

| Input | Result |
|-------|--------|
| `youngs_modulus = 0` | `a_design = 4000` ft/s (rigid-pipe default; README cites ~4720 ft/s before Courant adjust — implementation uses 4000 in `initGrid`) |
| `youngs_modulus > 0` | Korteweg–Joukowsky formula with `a₀ = 4860` ft/s, `K = 319 000` psi |

### Segment count and Courant adjustment

```516:523:src/moc_solver.cpp
        const double dx_target = wave_speed * dt_;
        const int    num_segs  = std::max(1, static_cast<int>(std::round(p.length / dx_target)));
        ps.a_wave    = (p.length / num_segs) / dt_; // adjusted wave speed
        ps.num_nodes = num_segs + 1;
        ps.k_minor   = std::max(0.0, p.minor_loss) / num_segs;
```

Let:

- `L` = `PipeInput::length` (ft)
- `Δt` = `run(..., dt=...)` (s)
- `a₀` = design wave speed (ft/s)
- `N` = `num_segs`
- `a` = `ps.a_wave` (adjusted, stored on `PipeState`)

Then:

$$N = \max\!\left(1,\ \mathrm{round}\!\left(\frac{L}{a_0 \Delta t}\right)\right)$$

$$a = \frac{L}{N \Delta t}$$

$$\Delta x = \frac{L}{N} = a \Delta t \qquad\Rightarrow\qquad \mathrm{Cr} = \frac{a \Delta t}{\Delta x} = 1$$

Grid indices: `num_nodes = N + 1` (endpoints plus `N − 1` interior points when
`N > 1`).

**Wave-speed distortion** (not exported today):

$$\text{distortion} = \frac{|a - a_0|}{a_0}$$

Rounding can yield zero distortion (when `L / (a₀ Δt)` is already an integer) or
nonzero distortion otherwise. Project guidance in
[dvcm_timestep_guidance.md](dvcm_timestep_guidance.md) recommends keeping
$|a - a_0| / a_0 \lesssim 15\%$ (ideally ≤ 10%) when choosing `dt`.

### Use of `a_wave` during integration

Each step uses the **adjusted** speed, not the design value:

```802:803:src/moc_solver.cpp
        const double dx = ps.a_wave * dt_;
        const double B  = ps.a_wave / g;
```

Characteristic impedance `B = a / g` and segment length `dx` therefore reflect
`a_adj`, not `a_design`.

### Minor losses

`PipeInput::minor_loss` (dimensionless `K`) is divided evenly across segments:
`k_minor = K / N`. This is independent of segment-count policy.

### Long-pipeline scaling (no cap today)

| Pipe length | `a₀` (ft/s) | `dt` (s) | `N = round(L/(a₀·dt))` | Interior points `N−1` |
|-------------|------------|----------|-------------------------|------------------------|
| 3 000 ft (Long Pipe Valve) | 747 | 0.01 | 402 | 401 |
| 20 mile (105 600 ft) | 4 000 | 0.01 | 2 640 | 2 639 |
| 20 mile | 4 000 | 0.001 | 26 400 | 26 399 |
| 20 mile | 4 000 | 0.0001 | 264 000 | 263 999 |

Memory and CPU scale roughly with **total segments across all pipes × time
steps**. A 20-mile uninterrupted reach at DVCM-grade `dt = 10⁻⁴ s` is therefore
~100× more expensive per mile than `dt = 0.01 s` with no engine-side relief.

### Existing test / utility references

| Artifact | Role |
|----------|------|
| `tests/dvcm_physical_verification_utils.py::adjusted_wave_speed_ft_s()` | Python mirror of `N` / `a_adj` formulas |
| `tests/test_pipe_materials.py` | Korteweg `a_design` vs material properties |
| `tests/test_long_pipe_valve.py::test_wave_speed` | Analytical `a_design` vs reference (±5 ft/s) |
| `tests/test_joukowsky_rthym.py::test_wave_speed` | Same Courant rounding behavior |

### Implication for long pipelines

- **`dt` is the sole user control** on grid density; long pipes need explicit
  planning for segment count and distortion.
- **Shortest pipe in a network** often dictates the `dt` that keeps distortion
  acceptable globally (see [dvcm_timestep_guidance.md](dvcm_timestep_guidance.md)).
- **Phase 4 roadmap** (`max_segments_per_pipe`, distortion meta) does not exist
  yet; there is no way to cap cost on a 20-mile reach without increasing `dt` or
  splitting the pipe into shorter graph links manually.

### Phase 4 target (from roadmap)

Add `set_grid_policy(max_segments_per_pipe=…, max_wave_speed_distortion=…)` and
emit per-pipe `wave_speed_design_fps`, `wave_speed_adjusted_fps`, `distortion_pct`
in study metadata.

### Reproducible check (current contract)

Standalone arithmetic mirroring `initGrid()` (no extension required):

```bash
python3 -c "
L = 105600.0   # 20 miles, ft
a0 = 4000.0
dt = 0.01
N = max(1, round(L / (a0 * dt)))
a_adj = L / (N * dt)
cr = a_adj * dt / (L / N)
dist = abs(a_adj - a0) / a0
assert abs(cr - 1.0) < 1e-12
print(f'N={N}  a_adj={a_adj:.4f}  Cr={cr:.6f}  distortion={100*dist:.4f}%')
"
```

Expected output (2026-06-05 baseline): `N=2640`, `a_adj=4000.0000`, `Cr=1.0`,
`distortion=0.0000%`.

With `pip install -e .`, the same formulas are exercised in
`tests/dvcm_physical_verification_utils.py::adjusted_wave_speed_ft_s`.

---

## 4. Performance budget (20-mile reference case)

**Status:** Budget defined (Phase 0 checklist item 4). First timed calibration
pending — run `scripts/benchmark_long_pipeline_budget.py` after `pip install -e .`.

### Reference case `LP-PERF-01`

Canonical probe for long-line engine performance (steady MOC stepping; no
transient event required for timing):

| Parameter | Value |
|-----------|-------|
| Topology | Single pipe: `R1` (PressureBoundary) → `P1` → `R2` (PressureBoundary) |
| Pipe length `L` | 20 mile = **105 600 ft** |
| Diameter | 24 in, HW `C = 130` |
| Initial flow | 3 000 GPM |
| Boundary heads | `R1 = 500` ft, `R2 = 100` ft |
| `youngs_modulus` | 0 (rigid `a₀ = 4000` ft/s) |
| Timestep `dt` | **0.001 s** |
| Duration `T` | **60 s** (~ one useful observation window; full round-trip ≈ `4L/a` ≈ 106 s) |
| Cavitation model | Default `LegacyClamp` (perf gate is orthogonal to DVCM) |

Uncapped grid today (§3): `N = 26 400` segments, **60 000** time steps, **≈ 1.58 × 10⁹**
segment-steps per run.

### Budget target (Phase 4 release gate)

| Metric | Target | When enforced |
|--------|--------|----------------|
| Wall-clock time | **&lt; 30 s** | After Phase 4 `max_segments_per_pipe` (or equivalent) is implemented |
| Hardware | Typical dev laptop: x86_64, 4+ cores, 16 GB RAM; native C++ extension (`pip install -e .`) | |
| Grid policy | `max_segments_per_pipe ≤ 2000` with `max_wave_speed_distortion ≤ 0.15` | Proposed default for `LP-PERF-01` |

**Rationale for 30 s:** Interactive R-THYM studies should remain usable without
batch/queue infrastructure. 60 s of simulated time at `dt = 0.001` is enough to
capture several wave transits on a capped grid while staying under a half-minute
wall clock on laptop-class hardware.

**Rationale for 2000-segment cap on 20 mi:** Reduces `N` from 26 400 → 2000
(≈ 13× fewer segment-steps). With ~0% wave-speed distortion when `L/(a₀·dt)`
is already nearly integral, distortion at the cap is dominated by reach-length
rounding — document in study meta and accept for screening studies (see Phase 4).

### Pre-Phase-4 expectation (uncapped grid)

The budget is **not** expected to pass today without grid scaling:

| Quantity | Uncapped (`N ≈ 26 400`) | Capped (`N = 2000`) |
|----------|-------------------------|---------------------|
| Segment-steps (`N × T/dt`) | ≈ 1.58 × 10⁹ | ≈ 1.20 × 10⁸ |
| Scaling vs Joukowsky microbench | See below | ≈ 13× faster than uncapped |

Joukowsky microbenchmark (README / `examples/benchmark_vs_tsnet.py`): ~3 000 ft
pipe, `dt = 0.01`, `N ≈ 75`, 300 steps → **&lt; 1 ms** wall time. Segment-steps
≈ 2.25 × 10⁴. Rough linear extrapolation to `LP-PERF-01` uncapped:

$$\text{time} \lesssim 1\ \text{ms} \times \frac{1.58 \times 10^{9}}{2.25 \times 10^{4}} \approx 70\ \text{s}$$

So the uncapped 20-mile / `dt = 0.001` case is expected to land in the **~30–90 s**
range on a laptop until Phase 4 ships. Treat uncapped timing as **informational
only**, not a CI failure.

### Calibration procedure

From repository root (extension built):

```bash
pip install -e .
python scripts/benchmark_long_pipeline_budget.py
python scripts/benchmark_long_pipeline_budget.py --length-mi 20 --dt 0.001 --total-time 60 --budget-s 30
```

Record results in the table below on first run. Re-run after Phase 4 grid policy
lands; `budget_met` should become `True`.

| Date | Git ref | `N` | Steps | Elapsed (s) | Grid cap | `budget_met` |
|------|---------|-----|-------|-------------|----------|--------------|
| 2026-06-05 | pre-Phase-1 | 26400 | 60000 | **3.438** (median, 5 runs) | none | yes (≪ 30 s) |
| — | — | 2000 | 60000 | *pending* | Phase 4 | *pending* |

### CI / regression policy

| Stage | Policy |
|-------|--------|
| **Now (Phases 0–3)** | Opt-in `pytest -m slow tests/test_long_pipeline_perf.py` vs `tests/long_pipeline_perf_baseline.json` (±5 %); default CI excludes `slow` |
| **Phase 4 complete** | Add `tests/test_long_pipeline_perf.py` with `@pytest.mark.slow`; fail if elapsed &gt; 30 s on capped grid |
| **DVCM long-line** | Separate budget at `dt ≤ 10⁻⁴` — out of scope for this 30 s gate |

### Phase 4 linkage

See [long_pipeline_surge_roadmap.md](long_pipeline_surge_roadmap.md) Phase 4:
`max_segments_per_pipe` and distortion reporting exist primarily to make
`LP-PERF-01` meet this budget without forcing users to coarsen `dt` globally.

---

## Revision history

| Date | Section | Change |
|------|---------|--------|
| 2026-06-05 | §1 | Interior H/V baseline recorded |
| 2026-06-05 | §2 | Vapor head / elevation baseline recorded |
| 2026-06-05 | §3 | Segment count / wave-speed adjustment baseline recorded |
| 2026-06-05 | §4 | Performance budget `LP-PERF-01` defined |
