# Validation notebooks

Interactive mirrors of pytest verification modules. Run locally from this directory
or on Binder via [`validation_notebooks_index.ipynb`](validation_notebooks_index.ipynb).

Each notebook imports shared helpers from `tests/` (added to `sys.path` by
`_notebook_setup.py`).

## Binder URLs

Replace `main` with your branch when testing a PR.

| Notebook | Binder |
|----------|--------|
| Index | `labpath=validation/notebooks/validation_notebooks_index.ipynb` |
| Grid scaling | `labpath=validation/notebooks/grid_scaling_verification.ipynb` |
| Bergant Adelaide | `labpath=validation/notebooks/bergant_adelaide_verification.ipynb` |
