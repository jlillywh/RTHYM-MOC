# Validation Notebook Coverage Map

**New users:** start with [validation_notebooks.md](validation_notebooks.md) or [examples/validation_notebooks_index.ipynb](../examples/validation_notebooks_index.ipynb) (recommended order, runtimes, pytest mirrors).

Pytest is the **CI source of truth**. Jupyter notebooks are **interactive mirrors** with the same pass/fail metrics where noted. Each notebook is labeled by **trust model** — see [validation.md § Verification vs regression](validation.md#verification-vs-regression-read-this-first):

| Trust model | Meaning |
|---|---|
| **Independent** | Compared to theory or another engine (not a prior rthym-moc snapshot) |
| **Snapshot** | Compared to golden JSON from an earlier rthym-moc run |
| **Design-rule** | Monotonic or bounded trends on a fixed geometry |

**Legend (coverage)**

| Status | Meaning |
|--------|---------|
| **Full** | Notebook overlays the same references and reports the same pass/fail metrics as pytest |
| **Partial** | Notebook covers one case or a subset of a parameterized sweep |
| **Script** | Runnable example under `examples/` but not a notebook |
| **None** | Automated in pytest only; see module docstrings |

## Binder verification notebooks

| Notebook | Trust model | Primary pytest mirror | Status |
|----------|-------------|----------------------|--------|
| [examples/quickstart_notebook.ipynb](../examples/quickstart_notebook.ipynb) | Independent | `test_joukowsky_rthym.py` | **Partial** — R-THYM cross-engine |
| [examples/long_pipe_valve_verification.ipynb](../examples/long_pipe_valve_verification.ipynb) | Independent | `test_long_pipe_valve.py` | **Full** — R-THYM (Appendix B.1–B.5) |
| [examples/epanet_import_verification.ipynb](../examples/epanet_import_verification.ipynb) | Independent | `test_complex_topology_from_inp.py` | **Full** — requires `wntr` |
| [examples/cross_engine_surge_verification.ipynb](../examples/cross_engine_surge_verification.ipynb) | Independent | `test_tsnet_standpipe_cross_engine.py`, `test_epanet_complex_topology_cross_engine.py` | **Full** — TSNet B.8 + EPANET pre-trip |
| [examples/gradual_closure_verification.ipynb](../examples/gradual_closure_verification.ipynb) | Independent | `test_gradual_closure_benchmark.py` | **Full** — closure-time sweep |
| [examples/dvcm_physical_verification.ipynb](../examples/dvcm_physical_verification.ipynb) | Independent | `test_dvcm_physical_verification.py` | **Full** — formula checks |
| [examples/bergant_adelaide_verification.ipynb](../examples/bergant_adelaide_verification.ipynb) | Independent | `test_dvcm_bergant_adelaide_experiment.py`, `test_dvcm_bergant_adelaide_trace.py` | **Full** — peaks + digitized trace overlay |
| [validation/notebooks/bergant_adelaide_verification.ipynb](../validation/notebooks/bergant_adelaide_verification.ipynb) | Independent | same | **Full** — preferred Binder path |
| [validation/notebooks/grid_scaling_verification.ipynb](../validation/notebooks/grid_scaling_verification.ipynb) | Analytical | `test_grid_scaling_long_pipe.py` | **Full** |
| [examples/surge_device_verification.ipynb](../examples/surge_device_verification.ipynb) | Independent | `test_surge_device_verification.py`, … | **Full** — Joukowsky / B.8 / device laws |
| [examples/long_pipeline_surge_verification.ipynb](../examples/long_pipeline_surge_verification.ipynb) | Independent (directional) | `test_long_pipeline_surge.py`, `test_long_pipeline_surge_verification.py` | **Full** — LP-02–04 on LP-SURGE-01 |
| [examples/dvcm_canonical_verification.ipynb](../examples/dvcm_canonical_verification.ipynb) | **Snapshot** | `test_dvcm_canonical_scenarios.py` | **Full** — golden `tests/dvcm_*_reference.json` |
| [examples/surge_design_rules_verification.ipynb](../examples/surge_design_rules_verification.ipynb) | Design-rule | `test_tank_size_benchmark.py`, … | **Partial** — size + placement sweeps |
| [examples/dvcm_showcase.ipynb](../examples/dvcm_showcase.ipynb) | — | — | **Partial** — pedagogy only |

## Cross-engine and analytical (independent verification)

| Test module | Trust model | Notebook mirror | Status |
|-------------|-------------|-----------------|--------|
| `test_joukowsky_rthym.py` | Independent | `quickstart_notebook.ipynb` | **Partial** |
| `test_long_pipe_valve.py` | Independent | `long_pipe_valve_verification.ipynb` | **Full** |
| `test_complex_topology_from_inp.py` | Independent | `epanet_import_verification.ipynb` | **Full** |
| `test_gradual_closure_benchmark.py` | Independent | `gradual_closure_verification.ipynb` | **Full** |
| `examples/test_gradual_closure.py` | Independent | `gradual_closure_verification.ipynb` | **Script** |
| `examples/test_wave_reflections.py` | Independent | — | **Script** |
| `examples/test_surge_tank.py` | Independent | `surge_device_verification.ipynb` | **Partial** |

## DVCM

| Test module | Trust model | Notebook mirror | Status |
|-------------|-------------|-----------------|--------|
| `test_dvcm_canonical_scenarios.py` | **Snapshot** | `dvcm_canonical_verification.ipynb` | **Full** |
| `test_dvcm_physical_verification.py` | Independent | `dvcm_physical_verification.ipynb` | **Full** |
| `test_dvcm_bergant_adelaide_experiment.py`, `test_dvcm_bergant_adelaide_trace.py` | Independent | `bergant_adelaide_verification.ipynb` | **Full** |
| `test_dvcm_junction_regime.py`, `test_dvcm_valve_check_valve.py`, … | — | — | **None** |

## Surge design-rule sweeps

| Test module | Trust model | Notebook mirror | Status |
|-------------|-------------|-----------------|--------|
| `test_tank_size_benchmark.py` | Design-rule | `surge_design_rules_verification.ipynb` | **Partial** |
| `test_device_placement_benchmark.py` | Design-rule | `surge_design_rules_verification.ipynb` | **Partial** |
| `test_hydropneumatic_size_benchmark.py` | Design-rule | — | **None** |
| `test_pipe_length_benchmark.py` | Design-rule | — | **None** |
| `test_multi_device_placement_benchmark.py` | Design-rule | — | **None** |
| `test_mixed_device_interaction_benchmark.py` | Design-rule | — | **None** |
| `test_air_valve_dominant_*.py` | Design-rule | — | **None** |
| `test_surge_device_verification.py` | Independent | `surge_device_verification.ipynb` | **Full** |

## Long pipeline surge (Phase 7)

| Test module | Trust model | Notebook mirror | Status |
|-------------|-------------|-----------------|--------|
| `test_long_pipeline_surge.py` | Independent (directional) | `long_pipeline_surge_verification.ipynb` | **Full** — LP-02–04 |
| `test_long_pipeline_surge_verification.py` | Independent (directional) | `long_pipeline_surge_verification.ipynb` | **Full** — notebook parity |
| `test_pipe_elevation_profile.py` | — | — | **None** — covered indirectly via LP-02 |
| `test_interior_dvcm_sloping_pipe.py` | Independent (directional) | — | **None** — short-pipe DVCM exit tests |
| `test_grid_scaling_long_pipe.py` | — | `validation/notebooks/grid_scaling_verification.ipynb` | **Full** |
| `test_chainage_air_valve.py` | — | — | **None** |
| `test_transient_friction_model.py` | Independent (directional) | — | **None** — see [transient_friction_verification.md](transient_friction_verification.md) |
| `test_long_pipeline_perf.py` | — | — | **PR CI** — LP-PERF-01 (`@pytest.mark.slow`, `long-pipeline-perf` job) |

## Controls, devices, materials, SI (pytest-only today)

| Area | Representative tests | Notebook |
|------|---------------------|----------|
| Threshold / Deadband / PID | `test_operational_controls.py` | **None** |
| VFD ramping | `test_pump_ramping.py` | **None** |
| Check valves | `test_check_valve.py`, `test_dvcm_valve_check_valve.py` | **None** |
| PRV / PSV | `test_pressure_control_valves.py` | **None** |
| Pump / turbine inertia | `test_pump_inertia.py`, `test_turbine_inertia.py` | **None** |
| SI units / `load_inp` SI | `test_units_si.py`, `test_load_inp_si.py`, `test_rthym_si_units.py` | **None** |
| INP fidelity / pump-valve INP | `test_inp_import_fidelity.py`, `test_pump_valve_transients_from_inp.py` | **None** |
| Pipe materials / minor losses | `test_pipe_materials.py`, `test_pipe_minor_losses.py` | **None** |
| Boundary variations | `test_boundary_variations_and_losses.py` | **None** |

## Shared helpers (tests + notebooks)

| Utils module | Used by |
|--------------|---------|
| `tests/long_pipe_valve_verification_utils.py` | Long-pipe notebook |
| `tests/complex_topology_verification_utils.py` | EPANET import notebook |
| `tests/gradual_closure_verification_utils.py` | Gradual-closure notebook |
| `tests/dvcm_canonical_verification_utils.py` | Canonical DVCM notebook + pytest |
| `tests/surge_design_rules_verification_utils.py` | Surge design-rules notebook |
| `tests/surge_device_verification_utils.py` | Surge device notebook + `test_surge_device_verification.py` |
| `tests/long_pipeline_surge_utils.py` | LP-SURGE-01 case builder (`test_long_pipeline_surge.py`) |
| `tests/long_pipeline_surge_verification_utils.py` | Long-pipeline surge notebook + `test_long_pipeline_surge_verification.py` |
| `tests/cross_engine_verification_utils.py` | Cross-engine surge notebook + TSNet/EPANET pytest |

## Policy

1. **New studies** should declare a trust model (independent / snapshot / design-rule) in this table and in [validation.md](validation.md).
2. **Independent verification** should add pytest and a notebook when reviewer-facing.
2. **Parameterized sweeps** may start as a partial notebook (one chart per sweep family) rather than duplicating every `@pytest.mark.parametrize` id.
3. **Binder runtime**: `long_pipe_valve_verification.ipynb` runs a ~230 s simulation; `long_pipeline_surge_verification.ipynb` runs two ~8 s capped-grid transients (~15–20 s); other notebooks are typically under 30 s.
4. **Optional deps**: EPANET import notebook requires `wntr` (`pip install 'rthym-moc[inp]'` or `pip install wntr`).
5. **Drift control**: shared logic lives in `tests/*_verification_utils.py`; notebooks are regenerated with `scripts/build_verification_notebooks.py`. PR CI runs `tests/test_verification_notebooks_smoke.py` (headless executor). Maintainers can run `scripts/verify_verification_notebooks.py --include-slow` weekly or on demand — see [validation_notebooks.md](validation_notebooks.md#operational-quality).

## Suggested next mirrors (priority)

1. `test_hydropneumatic_size_benchmark.py` — extend surge design-rules notebook
2. `test_operational_controls.py` — single controls demo notebook
3. `test_pump_valve_transients_from_inp.py` — second INP walkthrough
4. Papermill smoke of Full notebooks in CI (optional)
