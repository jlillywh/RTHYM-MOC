# Timestep Selection Guidance for DVCM Mode

This document provides practical, mathematical, and physical guidelines for selecting appropriate timesteps ($dt$) when simulating hydraulic transients using the **Discrete Vapor Cavity Model (DVCM)** mode in RTHYM-MOC.

---

## 1. Mathematical & Discretization Constraints

Like all Method of Characteristics (MOC) solvers, RTHYM-MOC discretizes the pipeline network into spatial grid nodes and temporal steps. This grid must satisfy the **Courant Condition** to ensure waves propagate at the physical speed:
$$Cr = \frac{a \cdot dt}{dx} = 1.0$$

Where:
* $a$ is the wave speed ($\text{ft/s}$ or $\text{m/s}$).
* $dt$ is the simulation timestep ($\text{s}$).
* $dx$ is the spatial grid segment length ($\text{ft}$ or $\text{m}$).

### Wave Speed Adjustment & Distortion
For a pipe $i$ of physical length $L_i$ and design wave speed $a_i$, the solver must partition the pipe into an integer number of reaches $N_i$:
$$N_i = \text{round}\left(\frac{L_i}{a_i \cdot dt}\right)$$

This integer requirement forces the solver to adjust the wave speed used in numerical calculations to:
$$a'_i = \frac{L_i}{N_i \cdot dt}$$

#### Recommended Guidelines:
* **Wave Speed Deviation**: The difference between physical wave speed $a_i$ and numerical wave speed $a'_i$ should not exceed **$\pm 15\%$** (and ideally should remain within **$\pm 10\%$**). Excessive wave speed adjustments distort transient travel times, phase alignment, and peak pressure reflections.
* **Selection Procedure**:
  1. Identify the shortest pipe length $L_{\text{min}}$ in the system.
  2. Estimate a trial timestep $dt \approx L_{\text{min}} / a$.
  3. Perform a quick parameter sweep of candidate $dt$ values near this trial value.
  4. Select a $dt$ that minimizes wave speed distortion across all pipes in the network.

---

## 2. Physics of Cavitation & Column Separation

Vapor cavitation in pipelines is a highly localized, high-speed physical process:
1. **Cavity Growth**: When the pressure drops to the vapor pressure floor ($P_{\text{vap}}$), a vapor pocket forms. The pocket's volume $V_c$ is integrated over time:
   $$V_c(t) = \int_{t_0}^{t} (Q_{\text{out}} - Q_{\text{in}}) \, dt$$
2. **Cavity Collapse**: When the surrounding hydraulic conditions increase the pressure, the vapor pocket shrinks.
3. **Collision Pressure Spike**: The instantaneous disappearance of the vapor cavity causes the separating water columns to collide, generating a massive secondary pressure spike (water hammer):
   $$\Delta H \approx \frac{a \cdot \Delta V}{2 g A}$$

### Why Coarse Timesteps Fail
If the timestep $dt$ is too large (e.g., $dt \ge 0.01\text{ s}$):
* **Integration Overshoot**: The integrated cavity volume $V_c$ can change too abruptly in a single step, resulting in non-physical negative volume spikes.
* **Numerical Chatter / Mode Switching**: The solver may oscillate rapidly between the liquid-full and vapor-cavity regimes, triggering numerical instabilities, `NaN` or `Inf` propagation, and solver crashes.
* **Loss of Peak Resolution**: High-frequency collision wavefronts and pressure spikes are mathematically smeared, underrepresenting the true peak pressure.

---

## 3. Recommended Timestep Guidelines

Depending on the intensity of the transient and the presence of cavitation, use the following guidelines:

| Simulation Scenario | Recommended Timestep ($dt$) | Grid Density / Focus |
|---|---|---|
| **Standard Transients (No Cavitation)** | $10^{-3}\text{ s}$ to $10^{-2}\text{ s}$ | Fast runtimes, standard controls/valves. |
| **Mild Cavitation / Boundary Checks** | $10^{-4}\text{ s}$ to $10^{-3}\text{ s}$ | Basic cavity volume tracking. |
| **Severe Column Separation & Collapse** | $10^{-5}\text{ s}$ to $10^{-4}\text{ s}$ (default: $0.0001\text{ s}$) | High-accuracy resolution of secondary water-hammer collision spikes. |

### Practical Operational Steps:
1. **Start with $dt = 0.0001\text{ s}$ ($10^{-4}\text{ s}$)**: This is the recommended baseline for DVCM. It provides an optimal balance between resolving cavitation collapse transients and CPU overhead.
2. **Fast-Acting Boundaries**: Ensure that $dt$ is at least **an order of magnitude smaller** than the fastest boundary excitation time (e.g. valve closure time $T_c$, pump shutdown ramp).
   * E.g., if $T_c = 0.1\text{ s}$, choose $dt \le 0.005\text{ s}$.
3. **Verify via Convergence Sweep**:
   * Run the simulation with $dt$.
   * Halve the timestep ($dt / 2$) and rerun.
   * If the peak pressures and collapse timings change by less than $1\%$, the solution is grid-independent.
4. **Instability Guard Triggers**:
   * If the solver throws a `RuntimeError` due to NaN/Inf detection (e.g. via RTHYM-MOC's safety guards), it indicates that the timestep is too coarse for the severe pressure gradients.
   * **Resolution**: Decrease the timestep by a factor of 2 or 5 (e.g., from $0.001\text{ s}$ to $0.0002\text{ s}$ or $0.0001\text{ s}$) and rerun.

---

## 4. Legacy Clamp vs. DVCM Timestep Comparison

| Aspect | `LegacyClamp` Mode | `DVCM` Mode |
|---|---|---|
| **Timestep Sensitivity** | Low | High |
| **Pressure Floor** | Rigid clamping | Physical regime switching |
| **Pressure Spike Resolution** | Missing (no collision spike) | Fully resolved |
| **Typical Stable $dt$** | Up to $0.01\text{ s}$ | $\le 0.001\text{ s}$ |
| **Computational Cost** | ~22% slower per step | ~22% faster per step |

*Note: While `DVCM` runs faster per step than `LegacyClamp` due to optimized regime tracking, the overall CPU time may increase if a smaller timestep $dt$ is required to maintain numerical stability during severe cavity collapse.*

---

## 5. Long-Pipeline Interior DVCM Convergence

Phase 3 interior-point DVCM on uninterrupted sloping reaches uses the same $dt$ discipline as junction DVCM, with profile envelopes as the convergence metric (not a single junction time series).

### Reference case: `LP-INTERIOR-DVCM-CONV`

| Parameter | Value |
|---|---|
| Geometry | 2000 ft sloping pipe, survey summit at 1000 ft chainage, junction-free `PressureBoundary` ends |
| Transient | Downstream reservoir drop `280 → 60` ft at $t = 0.02$ s |
| Model | `CavitationModel.DVCM`, `enable_interior_dvcm=True`, `record_pipe_profiles=True` |
| Vapor pressure | $-14$ psi |
| Simulation time | 1.0 s |

### Recommended procedure

1. Run with baseline $dt = 0.001$ s.
2. Halve to $dt = 0.0005$ s and rerun (Courant grid refines automatically).
3. Build chainage envelopes from `pipe_profile_pressure` and `pipe_profile_head` (min/max over time at each profile station).
4. Interpolate the fine-grid envelopes onto the coarse chainage stations.
5. On interior chainage $200 \le x \le 1800$ ft (exclude boundary-dominated ends), require
   $$\max \left| \frac{E_{\text{coarse}}(x) - E_{\text{fine}}(x)}{E_{\text{fine}}(x)} \right| \le 1\%$$
   for `pressure_max_psi`, `head_min_ft`, and `head_max_ft` envelopes.
6. Also check the global peak of the `pressure_max` envelope changes by $\le 1\%$.

At $dt = 0.001$ s this case is grid-independent to well within 1% on interior gauge-pressure and head envelopes; finer $dt$ is still warranted for severe junction collapse spikes elsewhere in the network.

### Pytest mirror

`tests/test_interior_dvcm_sloping_pipe.py::test_interior_dvcm_dt_halving_chainage_envelope_converges`

---

## 6. Long-Pipeline Grid Scaling Tradeoffs (Phase 4)

On uninterrupted reaches (10+ mile lines, few graph nodes), choosing $dt$ for DVCM
grade resolution can yield tens of thousands of MOC segments per pipe. Phase 4 adds
**grid policy** controls that cap segment count independently of the Courant
rounding in §1, plus optional **sparse interior DVCM** so cavity physics runs only
at watchpoints (summits, user chainages) while the full wave grid still propagates
transients.

### When to use grid scaling

| Situation | Recommendation |
|---|---|
| Short network, junction-heavy | Leave `max_segments_per_pipe = 0` (uncapped); tune $dt$ per §1–§3 |
| Long line, screening / envelope study | `max_segments_per_pipe ≤ 2000`, review distortion in study meta |
| Long line, sign-off DVCM case | Prefer smaller $dt$ **or** uncapped grid; halve-$dt$ convergence per §5 |
| Interactive R-THYM / batch budget | Capped grid + sparse watchpoints at high points |

**Do not** treat a heavily capped grid as a substitute for $dt$ convergence on
severe column-separation cases. Capping reduces **spatial** resolution; it does not
fix coarse **temporal** integration of cavity volume (§2).

### Grid policy API

```python
solver.set_grid_policy(
    max_segments_per_pipe=2000,      # 0 = uncapped
    max_wave_speed_distortion=0.15,  # fraction |a' − a| / a
    distortion_action="warn",        # or "error"
)
```

Or set individually: `set_max_segments_per_pipe()`, `set_max_wave_speed_distortion()`,
`set_wave_speed_distortion_action()`.

When a cap is active, each pipe uses at least **two** segments. Uncapped pipes
may still use a single segment on very short links.

### Courant adjustment under a segment cap

Without a cap (§1):

$$N = \max\!\left(1,\ \mathrm{round}\!\left(\frac{L}{a_0 \Delta t}\right)\right), \qquad
a' = \frac{L}{N \Delta t}$$

With `max_segments_per_pipe = N_{\max} > 0`:

$$N = \max\!\left(2,\ \min\!\left(N_{\text{uncapped}},\ N_{\max}\right)\right), \qquad
a' = \frac{L}{N \Delta t}$$

Distortion reported per pipe after each `run()`:

$$\text{distortion\_pct} = 100 \times \frac{|a' - a_0|}{a_0}$$

Keys: `pipe_wave_speed_design_fps`, `pipe_wave_speed_adjusted_fps`, `pipe_distortion_pct`,
`pipe_num_segments`. `summarize_study()` copies these onto each pipe entry
(`wave_speed_design_fps`, `wave_speed_adjusted_fps`, `distortion_pct`, `num_segments`).

If `max_wave_speed_distortion` is set, the solver **warns** (default) or **raises**
when any pipe exceeds the limit—typical when a cap forces $a' \gg a_0$ on a long
reach at DVCM-grade $\Delta t$.

#### Worked example (20 mi, rigid pipe)

| Setting | $N$ | $a'$ (ft/s) | Distortion |
|---|---|---|---|
| $L = 105{,}600$ ft, $a_0 = 4000$, $\Delta t = 0.001$ s, uncapped | 26 400 | 4000 | 0% |
| Same with `max_segments_per_pipe = 2000` | 2000 | 52 800 | 1220% |

The capped case meets the **LP-PERF-01** wall-clock budget ($\ll 30$ s on a laptop;
see [long_pipeline_phase0_baseline.md](long_pipeline_phase0_baseline.md) §4) but
**does not** satisfy the §1 $\pm 15\%$ wave-speed guideline. Use capped runs for
screening; document distortion in study meta and tighten $dt$ or remove the cap
for validation.

Calibration:

```bash
pip install -e .
python scripts/benchmark_long_pipeline_budget.py
python scripts/benchmark_long_pipeline_budget.py --strict   # exit 1 if > 30 s
```

### Sparse interior DVCM

Full interior DVCM (`enable_interior_dvcm=True`, empty chainage list) updates cavity
state at every interior grid index $j = 1 \ldots N-2$. For long pipes this is
often unnecessary except at terrain high points.

```python
pipe.interior_dvcm_chainages_ft = [13200.0, 39600.0]  # ft from upstream end
solver.run(..., enable_interior_dvcm=True, cavitation_model=CavitationModel.DVCM)
```

Each chainage snaps to the nearest grid index (clamped to interior range). Results
include `pipe_interior_dvcm_grid_indices` when the list is non-empty.

| Mode | Cavity physics | Wave propagation | Cost |
|---|---|---|---|
| Junction DVCM only | End nodes | Full MOC grid | Baseline |
| Full interior DVCM | All interior $j$ | Full MOC grid | Higher per step |
| Sparse interior DVCM | Listed chainages only | Full MOC grid | Lower DVCM overhead |

Non-watchpoint interior cells use standard MOC (no cavity regime switching). On
short pipes with watchpoints covering all interior chainages, sparse and full
interior DVCM agree within test tolerance
(`tests/test_sparse_interior_dvcm.py`).

### Practical selection matrix

1. **Pick $dt$** from §3 (often $10^{-4}$–$10^{-3}$ s for DVCM).
2. **Check uncapped** $N$ and distortion via `run()` metadata or `summarize_study()`.
3. If $N$ is too large for runtime, apply `max_segments_per_pipe` and accept
   documented distortion **or** increase $\Delta t$ (which also coarsens time
   integration—different tradeoff).
4. For sloping long lines, set `interior_dvcm_chainages_ft` at survey summits
   instead of full interior DVCM when screening.
5. **Validate** critical cases: halve $\Delta t$ (§5) or remove the segment cap
   and confirm peak envelopes change $\le 1\%$.

### Pytest mirrors

| Test module | What it checks |
|---|---|
| `tests/test_grid_scaling_long_pipe.py` | Cap, distortion meta, warn/error thresholds |
| `tests/test_sparse_interior_dvcm.py` | Chainage snap, summit activation, sparse vs full |
| `tests/test_long_pipeline_perf.py` (`pytest -m slow`) | LP-PERF-01 budget with cap ≤ 2000; PR CI `long-pipeline-perf` job |
