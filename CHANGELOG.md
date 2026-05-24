# Changelog

This project tracks public package versions in `rthym_moc/_version.py` and
records release-level changes here.

The format is based on Keep a Changelog, and this project uses semantic
versioning for package releases.

## [Unreleased]

## [0.2.0] - 2026-05-24

### Added
- quickstart notebook validation section that overlays the checked-in R-THYM pressure trace, reports RMS/peak benchmark metrics, and documents the benchmark tolerances used by the automated test suite
- quickstart notebook exploratory plots for the shortened 2-second closure case, including valve-side pressure, flow, closure schedule, peak-check annotations, and reloaded persisted artifacts

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
