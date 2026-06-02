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
