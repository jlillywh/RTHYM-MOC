# Changelog

This project tracks public package versions in `rthym_moc/_version.py` and
records release-level changes here.

The format is based on Keep a Changelog, and this project uses semantic
versioning for package releases.

## [Unreleased]

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
