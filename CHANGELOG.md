# Changelog

This project tracks public package versions in `rthym_moc/_version.py` and
records release-level changes here.

The format is based on Keep a Changelog, and this project uses semantic
versioning for package releases.

## [Unreleased]

### Added
- **Long-pipeline Phase 2 — pipe elevation profiles**: optional `PipeInput.elevation_profile` survey tables populate per-grid `z[j]`; profile gauge pressure and `pipe_profile_cavitation` screening use local elevation; terrain reaches get interior `LegacyClamp` at local vapor head; EPANET `[RTHYM] PipeElevation` import rows; `pipe_si(..., elevation_profile_m=...)`.
- DVCM independent physical verification (`tests/test_dvcm_physical_verification.py`) for junction mass-balance step checks and post-collapse head-rise estimates.
- Binder-ready notebook `examples/dvcm_physical_verification.ipynb` with charts and pass/fail metrics aligned to the pytest tolerances.
- DVCM regression notebook `examples/dvcm_canonical_verification.ipynb` (quickstart-style overlays vs all three `tests/dvcm_*_reference.json` anchors); shared `tests/dvcm_canonical_verification_utils.py`; gate `scripts/verify_dvcm_canonical.py`.
- Validation notebooks index: `docs/validation_notebooks.md` and Binder entry `examples/validation_notebooks_index.ipynb` (start here, pytest mirrors, expected runtimes).
- Validation notebook coverage map (`docs/validation_notebook_coverage.md`) and Binder mirrors for long-pipe R-THYM, EPANET `complex_topology.inp`, gradual-closure sweep, and partial surge design-rule sweeps (`examples/*_verification.ipynb` + `tests/*_verification_utils.py`).
- Expanded `examples/surge_device_verification.ipynb` and `tests/surge_device_verification_utils.py`: valve-side standpipe/HPT closure, air-valve restart, TSNet §B.8.5 overlay (optional), sizing preview; `tests/test_surge_device_verification.py`; local gate `scripts/verify_surge_bundle.py` (~90 s smoke + pytest).
- Operational quality: PR CI `verification-notebooks` job (regenerate notebooks + `tests/test_verification_notebooks_smoke.py`), weekly slow-notebook workflow, `examples/_verification_notebook_setup.py` bootstrap, and operational guidance in `docs/validation_notebooks.md` (Binder `[inp]`, pass/fail semantics, script-only wave/surge-tank demos).
- Cross-engine surge notebook `examples/cross_engine_surge_verification.ipynb` with checked-in `tests/TSNet_Standpipe_B8_*` (TSNet B.8 standpipe) and EPANET pre-trip vs MOC; `tests/cross_engine_verification_utils.py`, `scripts/export_tsnet_standpipe_reference.py`.

## [0.4.1] - 2026-06-03

### Added
- **Regulating Valve Throttling & Closure**: Added support for mechanical closure (GPM = 0) and dynamic throttling for regulating valves (PRV, PSV, PBV) when settings drop below 99.9%.
- **Dynamic Node Switching**: Added `set_node_type` method to `MOCSolver` to allow dynamically switching node types (e.g. PRV to TCV) mid-simulation.
- Added comprehensive unit tests for regulating valve mechanical closure and dynamic type switching.

### Fixed
- **Windows GHA Timeout**: Fixed Windows GitHub Actions build timeouts by disabling Windows Defender real-time scanning on Windows runner environments.

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
