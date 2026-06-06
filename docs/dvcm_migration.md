# Migration Guide: Upgrading to DVCM Support

This guide helps existing users of RTHYM-MOC upgrade to the new version that includes the **Discrete Vapor Cavity Model (DVCM)**.

---

## 1. Zero-Change Default (Backward Compatibility)

The default cavitation model in RTHYM-MOC remains **`LegacyClamp`**. 
* **Impact**: Upgrading the package will **not** alter your current simulation results, and no code changes are required to preserve existing baseline behavior.
* **Results**: The key `"node_cavitation"` in the results dictionary continues to report `1` when the pressure falls below vapor pressure and `0` otherwise, matching previous versions.

---

## 2. Opting into DVCM

To use the new physical column separation and cavity collapse dynamics, you must explicitly select the `DVCM` cavitation model.

### Code Update Examples:

#### A. Global Instance Selection
```python
import rthym_moc as m

solver = m.MOCSolver()
# Enable DVCM globally for this solver instance
solver.set_cavitation_model(m.CavitationModel.DVCM)

# Run simulations (uses DVCM by default)
results = solver.run(total_time=10.0, dt=0.0001)
```

#### B. Per-Simulation Run Override
```python
import rthym_moc as m

solver = m.MOCSolver()

# Override model type for a specific run call
results = solver.run(
    total_time=10.0,
    dt=0.0001,
    cavitation_model=m.CavitationModel.DVCM
)
```

---

## 3. Important Actions & Adjustments when using DVCM

If you opt-in to the `DVCM` model, please review the following requirements:

### A. Reduce Timestep Size ($dt$)
* **Why**: The Legacy Clamp is highly stable under coarse timesteps (e.g. $dt = 0.01\text{ s}$), but DVCM tracks physical cavity volumes that can change rapidly. Using a coarse timestep with DVCM will lead to numerical volume integration overshoot and instability.
* **Action**: When enabling DVCM, reduce your timestep to **$dt \le 0.001\text{ s}$** (we recommend **$0.0001\text{ s}$** for severe column separation).
* **See also**: [docs/dvcm_timestep_guidance.md](dvcm_timestep_guidance.md).

### B. Handle New Numerical Safety Guards
* **Why**: To prevent silent propagation of numerical blowups, RTHYM-MOC now implements runtime checks. If a simulation is unstable (e.g. because the timestep is too large for a severe cavity collapse), the solver will immediately throw a `RuntimeError` rather than completing with NaN values.
* **Action**: If your script encounters a `RuntimeError: Numerical instability: NaN/Inf detected...`, you must reduce the timestep $dt$ (try halving it) to resolve the high-pressure gradients.

### C. Update Downstream Parsing for New Results Keys
* **Why**: The results dictionary now includes four new optional diagnostic keys when `DVCM` is active:
  - `"node_cavity_volume"` / `"node_cavity_volume_m3"` (in SI mode)
  - `"node_cavity_active"` (unitless)
  - `"node_cavity_collapse_flag"` (unitless)
  - `"node_cavity_collapse_count"` (unitless)
* **Action**: Ensure that any downstream analysis or plotting scripts that iterate over result keys handle these new optional dictionary keys gracefully.

---

## 4. Long-pipeline profiles & interior DVCM (R-THYM)

Phases 1–5 add **opt-in** per-pipe profile export, terrain surveys, interior-point
DVCM, grid scaling, and chainage air valves. Defaults are unchanged; junction-only
workflows need no updates.

R-THYM integrators should follow the step-by-step rollout in
[long_pipeline_rthym_migration.md](long_pipeline_rthym_migration.md). API field
reference and JSON naming remain in
[dvcm_web_integration.md](dvcm_web_integration.md).
