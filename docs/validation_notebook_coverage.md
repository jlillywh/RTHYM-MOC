# Validation Notebook Coverage Map

**New users:** start with [validation_notebooks.md](validation_notebooks.md) or [examples/validation_notebooks_index.ipynb](../examples/validation_notebooks_index.ipynb) (recommended order, runtimes, pytest mirrors).

Pytest is the **source of truth** for regression gates. Jupyter notebooks are **interactive mirrors**: they replay the same geometries, references, and tolerances where a Binder walkthrough adds review value. This map shows what is mirrored today and what remains pytest-only.

**Legend**

| Status | Meaning |
|--------|---------|
| **Full** | Notebook overlays the same references and reports the same pass/fail metrics as pytest |
| **Partial** | Notebook covers one case or a subset of a parameterized sweep |
| **Script** | Runnable example under `examples/` but not a notebook |
| **None** | Automated in pytest only; see module docstrings |

## Binder verification notebooks

| Notebook | Primary pytest mirror | Status |
|----------|----------------------|--------|
| [examples/quickstart_notebook.ipynb](../examples/quickstart_notebook.ipynb) | `test_joukowsky_rthym.py` | **Partial** — Joukowsky R-THYM cross-engine (not long-pipe) |
| [examples/long_pipe_valve_verification.ipynb](../examples/long_pipe_valve_verification.ipynb) | `test_long_pipe_valve.py` | **Full** — second major R-THYM study (Appendix B.1–B.5) |
| [examples/epanet_import_verification.ipynb](../examples/epanet_import_verification.ipynb) | `test_complex_topology_from_inp.py` | **Full** — requires `wntr` |
| [examples/gradual_closure_verification.ipynb](../examples/gradual_closure_verification.ipynb) | `test_gradual_closure_benchmark.py` | **Full** — closure-time sweep |
| [examples/dvcm_canonical_verification.ipynb](../examples/dvcm_canonical_verification.ipynb) | `test_dvcm_canonical_scenarios.py` | **Full** — **DVCM regression:** three `tests/dvcm_*_reference.json` traces (quickstart-style overlays) |
| [examples/dvcm_physical_verification.ipynb](../examples/dvcm_physical_verification.ipynb) | `test_dvcm_physical_verification.py` | **Full** — formula checks (not JSON trace replay) |
| [examples/dvcm_showcase.ipynb](../examples/dvcm_showcase.ipynb) | — | **Partial** — pedagogy (Legacy vs DVCM valve; not JSON regression) |
| [examples/cross_engine_surge_verification.ipynb](../examples/cross_engine_surge_verification.ipynb) | `test_tsnet_standpipe_cross_engine.py`, `test_epanet_complex_topology_cross_engine.py` | **Full** — checked-in TSNet B.8 trace + EPANET pre-trip vs MOC (wntr) |
| [examples/surge_device_verification.ipynb](../examples/surge_device_verification.ipynb) | `test_surge_device_verification.py`, `test_surge_device_mitigation.py`, `test_air_valve.py`, `test_standpipe_surge_protection.py` | **Full** — B.8 standpipe, valve-side SP/HPT closure, HPT & air-valve pump trip, air-valve restart; TSNet §B.8.5 uses checked-in trace (+ optional live re-export); sizing preview links to design-rules notebook |
| [examples/surge_design_rules_verification.ipynb](../examples/surge_design_rules_verification.ipynb) | `test_tank_size_benchmark.py`, `test_device_placement_benchmark.py`, … | **Partial** — standpipe size + HPT placement sweeps |

## Cross-engine and analytical

| Test module | Notebook mirror | Status |
|-------------|-----------------|--------|
| `test_joukowsky_rthym.py` | `quickstart_notebook.ipynb` | **Partial** |
| `test_long_pipe_valve.py` | `long_pipe_valve_verification.ipynb` | **Full** |
| `test_complex_topology_from_inp.py` | `epanet_import_verification.ipynb` | **Full** |
| `test_gradual_closure_benchmark.py` | `gradual_closure_verification.ipynb` | **Full** |
| `examples/test_gradual_closure.py` | `gradual_closure_verification.ipynb` | **Script** → superseded for Binder |
| `examples/test_wave_reflections.py` | — | **Script** |
| `examples/test_surge_tank.py` | `surge_device_verification.ipynb` | **Partial** |

## DVCM

| Test module | Notebook mirror | Status |
|-------------|-----------------|--------|
| `test_dvcm_canonical_scenarios.py` | `dvcm_canonical_verification.ipynb` | **Full** |
| `test_dvcm_physical_verification.py` | `dvcm_physical_verification.ipynb` | **Full** |
| `test_dvcm_junction_regime.py`, `test_dvcm_valve_check_valve.py`, … | — | **None** |

## Surge design-rule sweeps

| Test module | Notebook mirror | Status |
|-------------|-----------------|--------|
| `test_tank_size_benchmark.py` | `surge_design_rules_verification.ipynb` | **Partial** (size sweep) |
| `test_device_placement_benchmark.py` | `surge_design_rules_verification.ipynb` | **Partial** (placement sweep) |
| `test_hydropneumatic_size_benchmark.py` | — | **None** |
| `test_pipe_length_benchmark.py` | — | **None** |
| `test_multi_device_placement_benchmark.py` | — | **None** |
| `test_mixed_device_interaction_benchmark.py` | — | **None** |
| `test_air_valve_dominant_*.py` | — | **None** |
| `test_surge_device_verification.py` | `surge_device_verification.ipynb` | **Full** |

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
| `tests/cross_engine_verification_utils.py` | Cross-engine surge notebook + TSNet/EPANET pytest |

## Policy

1. **New cross-engine or anchored-trace studies** should add both pytest and a notebook row in this table when the scenario is reviewer-facing.
2. **Parameterized sweeps** may start as a partial notebook (one chart per sweep family) rather than duplicating every `@pytest.mark.parametrize` id.
3. **Binder runtime**: `long_pipe_valve_verification.ipynb` runs a ~230 s simulation; other notebooks are typically under 30 s.
4. **Optional deps**: EPANET import notebook requires `wntr` (`pip install 'rthym-moc[inp]'` or `pip install wntr`).
5. **Drift control**: shared logic lives in `tests/*_verification_utils.py`; notebooks are regenerated with `scripts/build_verification_notebooks.py`. PR CI runs `tests/test_verification_notebooks_smoke.py` (headless executor). Maintainers can run `scripts/verify_verification_notebooks.py --include-slow` weekly or on demand — see [validation_notebooks.md](validation_notebooks.md#operational-quality).

## Suggested next mirrors (priority)

1. `test_hydropneumatic_size_benchmark.py` — extend surge design-rules notebook
2. `test_operational_controls.py` — single controls demo notebook
3. `test_pump_valve_transients_from_inp.py` — second INP walkthrough
4. Papermill smoke of Full notebooks in CI (optional)
