# Changelog

This project tracks public package versions in `rthym_moc/_version.py` and
records release-level changes here.

The format is based on Keep a Changelog, and this project uses semantic
versioning for package releases.

## [Unreleased]

### Added
- DVCM independent physical verification (`tests/test_dvcm_physical_verification.py`) for junction mass-balance step checks and post-collapse head-rise estimates.
- Binder-ready notebook `examples/dvcm_physical_verification.ipynb` with charts and pass/fail metrics aligned to the pytest tolerances.

## [0.4.0] - 2026-06-02

### Added
- **Discrete Vapor Cavity Model (DVCM)**: A physically consistent cavitation model that tracks vapor cavity volume growth and collapse at interior junctions, valves, check valves, pumps, and turbines.
- **WASM Bindings Extension**: Exposed DVCM telemetry parameters (active cavity, cavity volume, collapse counts/flags) to Emscripten/WASM bindings.
- **Jupyter Showcase Notebook**: Added `examples/dvcm_showcase.ipynb` to demonstrate column separation dynamics, timing shifts, and comparison against legacy clamping.
- **Comprehensive Validation & Robustness Suite**: Added targeted unit/integration tests (`test_dvcm_*.py`) for the new physics model, along with timestep and stability guidance.
- documented maintainer/internal Emscripten/WASM binding build path (`build_wasm.sh`) and CI smoke-test coverage
- `examples/benchmark_matrix.py` performance matrix sweeping time step and duration on the standard Joukowsky case (median timings vs TSNet)

### Changed
- **Unsteady Friction Correction**: Scaled the unsteady friction damping coefficient `k_u` with `dt_` to ensure numerical convergence under grid refinement and timestep-independence.
- migrated Python extension builds from legacy `setup.py` scaffolding to the pyproject-native `scikit-build-core` backend
- split correctness documentation (`docs/validation.md`) from TSNet performance benchmarking (`docs/benchmarking.md`) and restructured README Validation and Benchmarking sections accordingly

## [0.2.0] - 2026-05-24

### Added
- quickstart notebook validation section that overlays the checked-in R-THYM pressure trace, reports RMS/peak benchmark metrics, and documents the benchmark tolerances used by the automated test suite
- quickstart notebook exploratory plots for the shortened 2-second closure case, including valve-side pressure, flow, closure schedule, peak-check annotations, and reloaded persisted artifacts
- Binder configuration and README launch path so the quickstart notebook can be opened in a hosted Jupyter environment without a local notebook install

### Changed
- package metadata now marks the public release line as beta instead of alpha
- quickstart notebook structure now separates formal benchmark validation from exploratory scenario visualization and keeps the persisted-output workflow reusable from disk

## [0.1.0] - 2026-05-23

### Added
- initial public alpha release of the RTHYM-MOC Python package and C++ core
- pybind11-based transient hydraulic solver API with benchmark and validation coverage
- direct public-surface regressions for `Tank`, `OutflowNode`, and turbine startup behavior
- focused invalid-input coverage for unknown node types, unknown ids, wrong node kinds, empty schedules, and unsorted schedules
- benchmark and coverage documentation under `docs/`

### Changed
- CMake, setuptools, and the Python API now read the package version from the shared `rthym_moc/_version.py` source
- public docs and coverage tracking now reflect the supported hydraulic boundary/device surface
