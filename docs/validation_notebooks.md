# Validation Notebooks Index

**Start here on Binder:** [`examples/validation_notebooks_index.ipynb`](../examples/validation_notebooks_index.ipynb) (no simulations — navigation only).

Pytest under `tests/` is the **CI source of truth**. Notebooks replay the same cases
where a Binder walkthrough helps. Each notebook is labeled by **trust model** —
see [validation.md § Verification vs regression](validation.md#verification-vs-regression-read-this-first):

- **Independent** — theory or another engine (R-THYM, EPANET/wntr, TSNet export, formulas)
- **Snapshot** — golden trace from an earlier rthym-moc run (drift detection only)
- **Design-rule** — expected trends on fixed geometries (sizing/placement sweeps)

Full pytest↔notebook matrix: [validation_notebook_coverage.md](validation_notebook_coverage.md).

## Recommended order for new users

| Step | Notebook | Why |
|------|----------|-----|
| 0 | [`validation_notebooks_index.ipynb`](../examples/validation_notebooks_index.ipynb) | Pick the right walkthrough (this page in notebook form) |
| 1 | [`quickstart_notebook.ipynb`](../examples/quickstart_notebook.ipynb) | R-THYM Joukowsky cross-engine + reproducibility pattern |
| 2 | Pick a topic below | DVCM, surge, EPANET, or second R-THYM study |

## Verification notebooks (at a glance)

| Notebook | Trust model | What it proves | Primary pytest mirror(s) | Binder runtime |
|----------|-------------|----------------|---------------------------|----------------|
| [`quickstart_notebook.ipynb`](../examples/quickstart_notebook.ipynb) | Independent | R-THYM Joukowsky cross-engine | `test_joukowsky_rthym.py` | **~1 min** |
| [`cross_engine_surge_verification.ipynb`](../examples/cross_engine_surge_verification.ipynb) | Independent | TSNet B.8 + EPANET pre-trip | `test_tsnet_standpipe_cross_engine.py`, `test_epanet_complex_topology_cross_engine.py` | **~25 s** |
| [`long_pipe_valve_verification.ipynb`](../examples/long_pipe_valve_verification.ipynb) | Independent | R-THYM long-pipe valve study | `test_long_pipe_valve.py` | **~3 min** |
| [`epanet_import_verification.ipynb`](../examples/epanet_import_verification.ipynb) | Independent | EPANET steady state + trip | `test_complex_topology_from_inp.py` | **~15 s** |
| [`gradual_closure_verification.ipynb`](../examples/gradual_closure_verification.ipynb) | Independent | Joukowsky / Allievi sweep | `test_gradual_closure_benchmark.py` | **~30 s** |
| [`dvcm_physical_verification.ipynb`](../examples/dvcm_physical_verification.ipynb) | Independent | Mass step + collapse ΔH formulas | `test_dvcm_physical_verification.py` | **~15 s** |
| [`bergant_adelaide_verification.ipynb`](../examples/bergant_adelaide_verification.ipynb) | Independent | Bergant lab peaks + digitized He Fig. 4 trace | `test_dvcm_bergant_adelaide_experiment.py`, `test_dvcm_bergant_adelaide_trace.py` | **~5 s** |
| [`surge_device_verification.ipynb`](../examples/surge_device_verification.ipynb) | Independent | Standpipe, HPT, air valve vs analytical refs | `test_surge_device_verification.py`, … | **~20 s** |
| [`dvcm_canonical_verification.ipynb`](../examples/dvcm_canonical_verification.ipynb) | **Snapshot** | Replay golden `tests/dvcm_*_reference.json` | `test_dvcm_canonical_scenarios.py` | **~5 s** |
| [`surge_design_rules_verification.ipynb`](../examples/surge_design_rules_verification.ipynb) | Design-rule | Size + placement sweeps | `test_tank_size_benchmark.py`, … | **~45 s** |
| [`dvcm_showcase.ipynb`](../examples/dvcm_showcase.ipynb) | — | Pedagogy (Legacy vs DVCM) | — | **~5–15 min** |

## DVCM: which notebook?

| Question | Open | Trust model |
|----------|------|-------------|
| Does my build still match the checked-in golden JSON traces? | **`dvcm_canonical_verification.ipynb`** | Snapshot |
| Do cavity volume steps and collapse ΔH match theory? | `dvcm_physical_verification.ipynb` | Independent |
| Does DVCM match Bergant Adelaide lab data (peaks + digitized trace)? | `bergant_adelaide_verification.ipynb` | Independent |
| How does DVCM differ from Legacy on a valve network? | `dvcm_showcase.ipynb` (slow — exploratory) | — |

## Surge: which notebook?

| Question | Open |
|----------|------|
| Cross-engine confidence (TSNet trace + EPANET steady state)? | **`cross_engine_surge_verification.ipynb`** |
| Device physics (standpipe Joukowsky, HPT trip, air valve restart)? | `surge_device_verification.ipynb` |
| Sizing and placement trends? | `surge_design_rules_verification.ipynb` |

## Local quick gates (no Jupyter)

```bash
.venv/bin/python3 scripts/verify_dvcm_canonical.py      # ~5 s
.venv/bin/python3 scripts/verify_surge_bundle.py --skip-notebook  # ~10 s
pytest tests/test_dvcm_canonical_scenarios.py -q
pytest tests/test_surge_device_verification.py -q
```

## Binder links

| Notebook | Launch |
|----------|--------|
| **Index (start here)** | [![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/jlillywh/RTHYM-MOC/main?labpath=examples%2Fvalidation_notebooks_index.ipynb) |
| Quickstart | [![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/jlillywh/RTHYM-MOC/main?labpath=examples%2Fquickstart_notebook.ipynb) |
| DVCM regression | [![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/jlillywh/RTHYM-MOC/main?labpath=examples%2Fdvcm_canonical_verification.ipynb) |
| Surge devices | [![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/jlillywh/RTHYM-MOC/main?labpath=examples%2Fsurge_device_verification.ipynb) |

All Binder badges are also listed in the [README Examples section](../README.md#examples).

## Not covered by notebooks (pytest only)

Operational controls, check valves, PRV/PSV, pump inertia, most INP fidelity tests, SI-only regressions, and many surge parameter sweeps — see [validation_notebook_coverage.md](validation_notebook_coverage.md).

## Operational quality

### CI vs Binder

| Layer | What runs | Purpose |
|-------|-----------|---------|
| **PR CI (`verification-notebooks` job)** | `scripts/build_verification_notebooks.py` then `tests/test_verification_notebooks_smoke.py` | Catches notebook cells that diverge from `tests/*_verification_utils.py` without Jupyter CLI |
| **Pytest (all jobs)** | `tests/test_*.py` | Regression source of truth |
| **Maintainer / weekly** | `scripts/verify_verification_notebooks.py --include-slow` | Adds `long_pipe_valve_verification.ipynb` and `dvcm_showcase.ipynb` (~minutes) |

We use a small headless cell executor (`scripts/execute_notebook_headless.py`, `Agg` backend), not papermill/nbmake, to keep CI fast and dependency-light.

### Binder and `sys.path`

- Install **`pip install 'rthym-moc[inp]'`** (or `pip install wntr`) before **Run All** if you need INP import, EPANET mirrors, or the full quickstart INP path.
- Verification notebooks should start with `bootstrap_verification_notebook()` from `examples/_verification_notebook_setup.py` (also called automatically by the headless executor). That puts `tests/` on `sys.path` so `*_verification_utils` imports work from `examples/` or the repo root. **Do not copy cells into another folder** without the bootstrap — imports will break.

### Pass / fail semantics

| Notebook style | Examples | How to read results |
|----------------|----------|---------------------|
| **Assert-style (Full)** | `dvcm_canonical_verification`, `surge_device_verification`, `long_pipe_valve_verification`, … | Printed **PASS/FAIL** tables use the same tolerances as pytest |
| **Interpretive / pedagogy** | `dvcm_showcase` | Explains Legacy vs DVCM; **not** a CI regression gate |
| **Mixed** | `quickstart_notebook` | Formal R-THYM Joukowsky benchmark section + exploratory shortened schedule |

For DVCM regression, prefer **`dvcm_canonical_verification.ipynb`** over showcase.

### Cross-engine confidence (beyond R-THYM Joukowsky)

| Engine | Checked-in reference | Notebook |
|--------|---------------------|----------|
| R-THYM | `tests/R-THYM_Joukowsky_*`, `tests/R-THYM_MOC_*` | `quickstart_notebook`, `long_pipe_valve_verification` |
| TSNet | `tests/TSNet_Standpipe_B8_Verification.json` (+ `TSNet_Standpipe_B8_Traces.csv` after export) | **`cross_engine_surge_verification`** |
| EPANET (wntr) | live steady-state on `complex_topology.inp` | **`cross_engine_surge_verification`**, `epanet_import_verification` |

Regenerate the TSNet time series: `python scripts/export_tsnet_standpipe_reference.py` (requires `tsnet`; uses `examples/benchmark_ptsnet_vs_tsnet.py`).

### Analytical demos (scripts only)

Strong frictionless / wave-period studies that are **not** Binder notebooks today:

| Script | Topic |
|--------|--------|
| [`examples/test_wave_reflections.py`](../examples/test_wave_reflections.py) | Wave period and reflections |
| [`examples/test_surge_tank.py`](../examples/test_surge_tank.py) | Frictionless surge-tank mass oscillation |

Run locally: `python examples/test_wave_reflections.py` (see script docstrings). Partial overlap with surge device notebooks is noted in [validation_notebook_coverage.md](validation_notebook_coverage.md).
