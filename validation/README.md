# Empirical validation suite

This directory holds **laboratory-anchored reference data** and **Binder-ready
notebooks** that mirror the automated pytest verification modules under `tests/`.

Pytest remains the CI source of truth. Notebooks here are interactive walkthroughs
with the same pass/fail metrics where noted. See
[`docs/validation.md`](../docs/validation.md) for trust models (independent /
snapshot / design-rule).

## Layout

```
validation/
├── datasets/           # CSV / JSON reference artifacts with provenance READMEs
│   └── bergant_adelaide/
└── notebooks/          # Jupyter verification notebooks (Binder entry points)
```

## Binder quick start

Open the notebook index on Binder:

[![Launch Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/jlillywh/RTHYM-MOC/main?labpath=validation%2Fnotebooks%2Fvalidation_notebooks_index.ipynb)

Recommended first notebooks:

| Notebook | Laboratory / reference | Pytest mirror |
|----------|------------------------|---------------|
| [`grid_scaling_verification.ipynb`](notebooks/grid_scaling_verification.ipynb) | Courant grid policy (analytical) | `tests/test_grid_scaling_long_pipe.py` |
| [`bergant_adelaide_verification.ipynb`](notebooks/bergant_adelaide_verification.ipynb) | Bergant–Simpson Adelaide column separation | `tests/test_dvcm_bergant_adelaide_*.py` |

Legacy copies of several notebooks also remain under `examples/` for backward-compatible
Binder URLs. New validation work should land here first.

## Shared helpers

Python utilities consumed by both pytest and notebooks live in `tests/*_verification_utils.py`.
Dataset paths resolve through `validation/datasets/` (see each dataset README).
