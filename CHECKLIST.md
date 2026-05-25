# RTHYM-MOC Open Source Best Practices Checklist

This checklist will help you systematically improve the quality, reliability, and community readiness of your library.

## Testing
- [x] All features/scenarios have automated tests
	Coverage tracked in `docs/test_coverage_matrix.md`
- [x] Edge cases and invalid input are tested
- [x] Parametrized tests for input variations
	Covered by existing `pytest.mark.parametrize` sweeps across materials, imported topology checks, and benchmark/input matrices.
- [x] Regression tests with reference outputs
	Covered by checked-in JSON/CSV/INP reference assets and cross-engine regression tests documented in `docs/validation.md`.
- [x] All assertions have clear, descriptive messages
	Verified by test-suite audit: current `assert` statements in `tests/` include explicit failure messages.
- [x] Numerical tolerances are explicit and documented
	Documented in `docs/validation.md`; tests use named tolerance constants, parameterized case bounds, or explicit numeric acceptance bands.
- [x] Tests are isolated (no shared state)
	Verified by audit: shared fixtures cache read-only result data from fresh solver runs, with no writes back into shared fixture/result objects.
- [x] Random seeds set for reproducibility (if needed)
	Verified by audit: the current solver and tests do not use RNG-driven inputs or stochastic code paths, so no explicit seed control is needed.

## Continuous Integration (CI)
- [x] GitHub Actions (or similar) runs tests on all pushes/PRs
	Configured in `.github/workflows/tests.yml` to run the test suite on pushes to `main` and on pull requests.
- [ ] CI covers all supported OSes and Python versions
	Blocked on GitHub-side verification: the local repo contains `.github/workflows/tests.yml`, but GitHub currently reports no workflows on the default branch, so the cross-OS/Python matrix has not yet been observed running remotely.
- [x] Test coverage is measured (pytest-cov)
	Configured in `.github/workflows/tests.yml` with a dedicated coverage job using `pytest --cov=rthym_moc --cov-report=term-missing --cov-report=xml`.
- [x] Coverage is uploaded to Codecov/Coveralls
	Configured in `.github/workflows/tests.yml` to upload `coverage.xml` to Codecov from the dedicated coverage job.
- [x] CI runs linting and type checks
	Configured in `.github/workflows/tests.yml` with a dedicated Ruff + mypy job for the Python package surface.

## Linting & Type Checking
- [x] Code style enforced (black, flake8, or ruff)
	Ruff is configured in `pyproject.toml` and enforced in CI for the Python package surface.
- [x] All functions have type hints
	Verified by audit and validation: the pure-Python package code is annotated and the compiled extension surface now ships `rthym_moc/_rthym_moc.pyi`; `mypy rthym_moc` passes without ignoring the extension module.
- [x] mypy or similar runs in CI
	mypy is configured in `pyproject.toml` and runs in the CI lint/type job.
- [x] Pre-commit hooks for style and linting
	Configured in `.pre-commit-config.yaml` with basic file-sanity hooks plus Ruff and mypy for the Python package surface.

## Documentation
- [x] All public functions/classes have docstrings
	Verified by audit: the public Python module surface is documented in `rthym_moc/__init__.py` and `rthym_moc/epanet.py`, and the compiled `MOCSolver` / `NodeInput` / `PipeInput` API exposes class and method docstrings via `src/bindings.cpp`.
- [x] Each test has a docstring explaining its purpose
	Verified by AST audit across `tests/test_*.py`; the last missing case in `tests/test_pipe_materials.py` now has an explicit per-test purpose docstring.
- [x] Example scripts and notebooks are provided
	Documented in `README.md`; the repo now includes runnable script examples under `examples/` plus `examples/quickstart_notebook.ipynb` for an interactive deterministic/reproducibility walkthrough.
- [x] Reference data (CSV/JSON) is versioned and documented
	Documented in `docs/validation.md` with an explicit inventory of checked-in CSV/JSON/INP assets, their provenance, and the tests that consume them.
- [x] README includes usage, install, and test instructions
	Documented in `README.md` with installation, quickstart usage, and explicit local test / lint / pre-commit commands.
- [x] Badges for build, coverage, PyPI, etc.
	README now includes GitHub Actions test-status and Codecov coverage badges; a PyPI badge can be added once a published package exists.
- [x] CONTRIBUTING.md with test/contribution instructions
	Documented in `CONTRIBUTING.md` with setup, rebuild, test, lint, pre-commit, and pull request guidance.

## Community & Maintenance
- [x] GitHub Issues/Projects used to track progress
	Active GitHub issues now track remaining repository work, including [#1](https://github.com/jlillywh/RTHYM-MOC/issues/1) for default-branch CI verification and [#2](https://github.com/jlillywh/RTHYM-MOC/issues/2) for ongoing maintenance/process tracking.
- [x] Regular review/refactor schedule
	Documented in `MAINTENANCE.md` with an ongoing triage expectation, a monthly review pass, pre-release checks, and explicit triggers for focused refactors.
- [x] Encourage and document community contributions
	Documented in `README.md` and `CONTRIBUTING.md` with an explicit invitation for bug reports, benchmark ideas, documentation fixes, and pull requests, plus guidance on what information contributors should include.
- [x] Use pytest skip/xfail for optional/known issues
	Verified by audit: the optional `wntr`-dependent INP benchmark modules use `pytest.importorskip(...)` so they skip cleanly when that dependency is not installed instead of failing the suite.

---

**How to use:**
- Work through one section at a time
- Check off items as you complete them
- Review regularly and update as needed
