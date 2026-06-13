# RTHYM-MOC

[![Tests](https://github.com/jlillywh/RTHYM-MOC/actions/workflows/tests.yml/badge.svg)](https://github.com/jlillywh/RTHYM-MOC/actions/workflows/tests.yml)
[![Coverage](https://codecov.io/gh/jlillywh/RTHYM-MOC/branch/main/graph/badge.svg)](https://codecov.io/gh/jlillywh/RTHYM-MOC)
[![PyPI](https://img.shields.io/pypi/v/rthym-moc)](https://pypi.org/project/rthym-moc/)
[![Launch Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/jlillywh/RTHYM-MOC/main?labpath=validation%2Fnotebooks%2Fvalidation_notebooks_index.ipynb)

A high-performance tool for simulating water hammer and other pressure surges
in pipe networks. It uses a C++17 core with a Python API, and it was originally
developed as the engine behind the [R-THYM](https://lillywhitewater.com/products/r-thym/)
web application. The project is released here as a standalone, open-source
library for research, design studies, and automated validation.

## Contents

- [Overview](#overview)
- [Installation](#installation)
- [Maintainer WASM integration (internal)](#maintainer-wasm-integration-internal)
- [Quickstart](#quickstart)
- [Long-pipeline surge & interior DVCM](#long-pipeline-surge--interior-dvcm)
- [Developing the C++ core](#developing-the-c-core)
- [Testing](#testing)
- [Examples](#examples)
- [Validation](#validation)
- [API Reference](#api-reference)
  - [NodeInput](#nodeinput)
  - [PipeInput](#pipeinput)
  - [MOCSolver](#mocsolver)
  - [ControlRuleInput](#controlruleinput)
  - [Results dictionary](#results-dictionary)
  - [Post-processing & study reports](#post-processing--study-reports)
- [Unit conventions](#unit-conventions)
- [Valve model](#valve-model)
- [Valve closure types](#valve-closure-types)
- [Operational Controls & Event Logic](#operational-controls--event-logic)
- [Surge control components](#surge-control-components)
- [Pump & Turbine Rotational Inertia](#pump--turbine-rotational-inertia)
- [Scripted multi-event transients](#scripted-multi-event-transients)
- [Loading from EPANET (.inp)](#loading-from-epanet-inp)
- [Numerical method](#numerical-method)
- [Benchmarking](#benchmarking)
- [Repository layout](#repository-layout)
- [Dependencies](#dependencies)

---

## Overview

RTHYM-MOC solves the 1-D water-hammer equations using the Method of Characteristics with a fixed Courant number of 1.

### Key characteristics:

- **Network-capable**: arbitrary topologies of pipes, junctions, reservoirs, air valves, valves, pumps, standpipe surge tanks, hydropneumatic tanks, and turbines.
- **Time-varying events**: valve schedules, pump trip/start, demand changes — specified either as discrete step changes between `run()` calls or as continuous piecewise-linear schedules registered before `run()`.
- **Cavitation detection**: supports two cavitation models (configured via `set_cavitation_model()` or the `cavitation_model` parameter):
  - **`LegacyClamp` (Default)**: A first-order head-clamping model. Clamps HGL at the vapor floor, best for mild transient systems where cavitation is minor.
  - **`DVCM`**: A Discrete Vapor Cavity Model. Tracks the growth, expansion, and collapse of discrete vapor cavities, simulating secondary pressure surges upon column collision (requires small timesteps, see [docs/dvcm_timestep_guidance.md](docs/dvcm_timestep_guidance.md)).
- **Long-pipeline surge**: optional terrain surveys (`elevation_profile`), per-pipe MOC profile export, interior-point DVCM between junctions, segment-count caps for multi-mile runs, and chainage air valves at survey summits — see [Long-pipeline surge & interior DVCM](#long-pipeline-surge--interior-dvcm).
- **Study summaries**: built-in helpers turn raw time series into node/pipe
  envelopes, cavitation duration, and CSV/JSON exports — see [Post-processing &
  study reports](#post-processing--study-reports).
- **Fast**: in the representative Joukowsky benchmark, the C++ core is much
  faster than [TSNet](https://github.com/glorialulu/TSNet) (pure Python) on
  typical hardware — see [Benchmarking](#benchmarking).
- **Validated**: automated regressions against R-THYM exports, EPANET/wntr steady state, and analytical checks — Joukowsky first-step error < 0.05 %, wave period error < 0.2 % — see [Validation](#validation).

---

## Installation

### Install from PyPI

```bash
pip install rthym-moc
```

Optional extras:

```bash
pip install 'rthym-moc[inp]'   # EPANET .inp import via wntr
pip install 'rthym-moc[dev]'    # pytest, ruff, mypy, etc.
```

Verify:

```bash
python -c "import rthym_moc; print(rthym_moc.__version__)"
```

**Platforms:** Linux, macOS, and **Windows** are supported (Python 3.9–3.12;
see CI). For most users, prebuilt wheels are published for the common
platform/Python combinations below, so no local C++ compiler is needed.

| OS | Wheel architecture | Python |
|----|--------------------|--------|
| Linux | x86_64 (`manylinux`) | CPython 3.9–3.12 |
| macOS | x86_64, arm64 | CPython 3.9–3.12 |
| Windows | AMD64 | CPython 3.9–3.12 |

If no wheel is available for your platform, `pip` falls back to the source
distribution and compiles the C++ extension locally. Source builds require a
**C++17 compiler**:

| OS | Compiler |
|----|----------|
| Linux | GCC 9+ or Clang 10+ (`build-essential` on Debian/Ubuntu) |
| macOS | Xcode Command Line Tools (Clang) |
| Windows | [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) with the **“Desktop development with C++”** workload (MSVC 2019 or newer). Use a normal **x64** Command Prompt or PowerShell, not WSL, when installing into Windows Python. |

On Windows, if `pip install rthym-moc` falls back to a source build and fails
with a compiler error, install the Build Tools, open a new terminal, and retry.

### Requirements

| Component | Minimum version | Notes |
|-----------|----------------|-------|
| Python    | 3.9            | |
| NumPy     | 1.21           | Installed automatically with `rthym-moc` |
| C++ compiler | C++17 (GCC 9+, Clang 10+, MSVC 2019+) | Only required when installing from source or when no wheel is available |
| CMake     | 3.15           | Only for the standalone C++ test binary below |
| pybind11  | 2.11           | Pulled automatically when building from PyPI or source |

### Install from source (development)

Clone the repository, then install in editable mode:

```bash
pip install -e .
# or with extras:
pip install -e '.[dev,inp]'
```

This compiles the C++ extension `_rthym_moc` and installs the `rthym_moc` package from your working tree.

**Changed `src/solver/`?** Use the [two-step verification loop](#developing-the-c-core) (native `ctest`, then editable install + `pytest`) before opening a PR.

---

## Maintainer WASM integration (internal)

The repository includes a **maintainer-only** Emscripten build path for validating
`bindings/wasm/wasm_bindings.cpp`. This is separate from the supported Python package API
and is not part of the public release workflow:

- pure C++ solver core lives in `src/solver/` (no pybind11, no Emscripten headers)
- Python bindings live in `bindings/python/`
- WASM bindings live in `bindings/wasm/wasm_bindings.cpp`
- the build script is `bindings/wasm/build_wasm.sh` (root `build_wasm.sh` delegates to it)
- CI runs a binding smoke test in `.github/workflows/wasm-regression.yml`

The WASM surface exposes a stepwise integration API (`initGrid`, `stepMOC`,
`get_step_results`) rather than the Python `MOCSolver.run()` batch workflow.
Treat it as internal maintainer tooling, not a semver-stable public contract.

### Build

Maintainers with [Emscripten](https://emscripten.org/docs/getting_started/downloads.html)
installed can run:

```bash
bash build_wasm.sh
```

By default this writes:

```
build/wasm/rthym_moc.js
build/wasm/rthym_moc.wasm
```

Optional environment variables:

| Variable | Purpose |
|----------|---------|
| `EMSDK_DIR` | Path to an emsdk checkout; the script sources `emsdk_env.sh` if `em++` is not already on `PATH` |
| `RTHYM_WASM_OUT_DIR` | Override artifact output directory (default: `build/wasm`) |
| `RTHYM_WASM_BUILD_DIR` | Override CMake build directory (default: `build_wasm`) |

### Maintainer smoke test

```bash
bash build_wasm.sh
pytest -q bindings/wasm/tests --override-ini='addopts='
```

This checks that CheckValve runtime fields are exposed through the WASM bindings.
It validates the binding contract only, not a downstream application integration.

---

## Quickstart

> [!TIP]
> The Python snippet below is the fastest way to try the solver. For an interactive
> cross-engine check against checked-in R-THYM traces (same tolerances as CI), see
> [Validation](#validation) and the Binder quickstart notebook there.

```python
import numpy as np
import rthym_moc

# ── 1. Build network topology ─────────────────────────────────────────────────
solver = rthym_moc.MOCSolver()

# Upstream constant-head reservoir
solver.add_node(rthym_moc.NodeInput(
    id="R1", type="PressureBoundary",
    elevation=0.0, head=150.0          # ft HGL
))

# Inline valve (fully open at t=0, will be slammed shut)
solver.add_node(rthym_moc.NodeInput(
    id="V1", type="Valve",
    elevation=0.0, diameter=12.0,      # inches
    current_setting=0.0                # % open (0 = slammed shut at t=0)
))

# Downstream reservoir
solver.add_node(rthym_moc.NodeInput(
    id="R2", type="PressureBoundary",
    elevation=0.0, head=0.0
))

# Pipe: 3000 ft, 12-inch diameter, Hazen-Williams C = 130
solver.add_pipe(rthym_moc.PipeInput(
    id="P1",
    from_node="R1", to_node="V1",
    length=3000.0, diameter=12.0,
    roughness=130.0, flow_gpm=500.0    # initial steady-state flow
))
solver.add_pipe(rthym_moc.PipeInput(
    id="P2",
    from_node="V1", to_node="R2",
    length=100.0, diameter=12.0,
    roughness=130.0, flow_gpm=500.0
))

# ── 2. Run transient simulation ───────────────────────────────────────────────
results = solver.run(
    total_time=4.0,    # seconds
    dt=0.01,           # time step (seconds)
    p_vapor=-14.0,     # vapour pressure threshold (psi; negative = below atm)
    usf_tau=0.5        # unsteady-friction relaxation time constant (s)
)

# ── 3. Extract results ────────────────────────────────────────────────────────
t      = np.array(results["time"])          # shape (N,)  seconds
H_V1   = np.array(results["node_head"]["V1"])      # ft
P_V1   = np.array(results["node_pressure"]["V1"])  # psi
Q_P1   = np.array(results["pipe_flow_gpm"]["P1"])  # GPM

print(f"Joukowsky peak at V1: {H_V1.max():.1f} ft  at t = {t[H_V1.argmax()]:.3f} s")
```

---

## Long-pipeline surge & interior DVCM

Use this workflow for **multi-mile transmission mains** where subatmospheric pressure and column separation can occur **between** network junctions — for example at a terrain summit on a sloping reach.

All long-pipeline features are **opt-in** and default off, so existing `run()` callers see unchanged output until you enable them.

| Layer | API | Purpose |
|---|---|---|
| Terrain | `PipeInput.elevation_profile` | Piecewise-linear ground survey along the pipe; local gauge pressure and cavitation screening use `z(x)` |
| Profiles | `run(..., record_pipe_profiles=True)` | Export head, pressure, velocity, and cavitation flags along the MOC grid |
| Interior DVCM | `CavitationModel.DVCM` + `enable_interior_dvcm=True` | Track vapor-cavity volume at interior grid points (not just junctions) |
| Grid scaling | `solver.set_grid_policy(...)`, `solver.get_grid_report(dt)` | Cap segments on 10–20 mile lines; preview Courant wave-speed adjustment before a long run |
| Summit protection | `attach_air_valve_at_survey_high_point()` | Split the pipe and insert an `AirValve` at the survey high point |

**Minimal example** — 5-mile sloping main, downstream head drop, interior DVCM at the summit:

```python
import numpy as np
import rthym_moc as m

L_FT = 5.0 * 5280.0  # 5 miles

solver = m.MOCSolver()
solver.add_node(m.NodeInput(id="R1", type="PressureBoundary", elevation=200.0, head=520.0))
solver.add_node(m.NodeInput(id="R2", type="PressureBoundary", elevation=150.0, head=520.0))

pipe = m.PipeInput()
pipe.id = "Pmain"
pipe.from_node = "R1"
pipe.to_node = "R2"
pipe.length = L_FT
pipe.diameter = 24.0
pipe.roughness = 130.0
pipe.flow_gpm = 2500.0
pipe.elevation_profile = [(0.0, 200.0), (L_FT / 2.0, 450.0), (L_FT, 150.0)]
solver.add_pipe(pipe)

# Downsurge at the downstream boundary (opens a summit cavity under DVCM)
solver.set_head_schedule("R2", [(0.0, 520.0), (0.05, 120.0)])

# Cap grid size for long reaches (Courant wave-speed adjustment still enforced)
solver.set_grid_policy(max_segments_per_pipe=2000, max_wave_speed_distortion=0.15)

results = solver.run(
    total_time=8.0,
    dt=0.001,
    p_vapor_psi=-14.0,
    cavitation_model=m.CavitationModel.DVCM,
    record_pipe_profiles=True,
    enable_interior_dvcm=True,
)

x_ft = np.array(results["pipe_profile_chainage_ft"]["Pmain"])
P_psi = np.array(results["pipe_profile_pressure"]["Pmain"])
V_cav = np.array(results["pipe_profile_cavity_volume"]["Pmain"])  # ft³, DVCM only

summit_idx = int(np.argmin(P_psi.min(axis=0)))  # chainage of worst min pressure
print(f"Summit chainage ≈ {x_ft[summit_idx]:.0f} ft, min P = {P_psi[:, summit_idx].min():.1f} psi")
print(f"Peak interior cavity volume = {V_cav.max():.4f} ft³")
print(f"MOC segments = {results['pipe_num_segments']['Pmain']}")
```

**When to enable what**

- **`record_pipe_profiles=True`** alone — HGL/pressure envelopes along the line; `pipe_profile_cavitation` is a screening flag (not physical cavity volume).
- **`enable_interior_dvcm=True`** — requires `CavitationModel.DVCM` and typically `record_pipe_profiles=True`; populates `pipe_profile_cavity_volume` and `pipe_profile_cavity_active`.
- **`interior_dvcm_chainages_ft`** on `PipeInput` — optional sparse watchpoints when full interior DVCM is too heavy; empty list with `enable_interior_dvcm=True` tracks all interior grid points.
- **`set_grid_policy(...)`** — recommended for multi-mile pipes; call **`get_grid_report(dt)`** to preview `pipe_num_segments`, `pipe_distortion_pct`, and `pipe_wave_speed_*` before integrating, or read the same keys from `run()` results afterward.

R-THYM integrators: incremental rollout checklist in [docs/long_pipeline_rthym_migration.md](docs/long_pipeline_rthym_migration.md). Validation: [long_pipeline_surge_verification.ipynb](examples/long_pipeline_surge_verification.ipynb) and `pytest tests/test_long_pipeline_surge.py -q`.

---

## Developing the C++ core

Most numerical work lives under **`src/solver/`** — the pure C++17 kernel with no
pybind11 or Emscripten headers. CI runs native tests in isolation (`test-core-cpp`)
before Python or WASM jobs. You do **not** need Emscripten, WASM tooling, or wheel
packaging details for typical solver contributions.

After editing the core, run this **two-step loop** from the repo root:

```bash
# 1. Native core only (seconds — no Python)
cmake -B build -DCMAKE_BUILD_TYPE=Debug -DBUILD_TESTS=ON -DRTHYM_BUILD_PYTHON=OFF \
  && cmake --build build --target rthym_core_tests -j \
  && ctest --test-dir build --output-on-failure

# 2. Rebuild bindings + Python regression
pip install -e ".[dev]" && pytest -q
```

| Step | What it checks | Where tests live |
|------|----------------|------------------|
| `ctest` | Solver logic, grid scaling, unit behavior | `tests/cpp/` (Doctest binary) |
| `pytest` | pybind11 surface, networks, validation harness | `tests/` |

Add or extend native cases in `tests/cpp/test_core.cpp` when changing behavior in
`src/solver/`; run `pytest` afterward for binding and integration coverage. Optional
`pip install -e '.[dev,inp]'` if you need INP/wntr tests locally.

Full CI parity (100% coverage gate, WASM smoke, pre-commit) is in
[`CONTRIBUTING.md`](CONTRIBUTING.md#local-verification-matches-ci).

---

## Testing

How to run checks locally. For **independent verification** vs **snapshot
regression** vs **design-rule** tests, see [Validation](#validation) and
[docs/validation.md](docs/validation.md#verification-vs-regression-read-this-first).

**Changed `src/solver/`?** Start with [Developing the C++ core](#developing-the-c-core) (`ctest`, then `pip install -e` + `pytest`).

Run the full Python suite from the repository root:

```bash
pytest -q
```

To run the CI-aligned package quality checks locally:

```bash
ruff check rthym_moc
mypy rthym_moc
```

If you install the development extras, you can also run the configured pre-commit hooks:

```bash
pip install -e '.[dev,inp]'
pre-commit run --all-files
```

---

## Examples

Runnable **demos and benchmarks** under `examples/` — how to call the API, explore
physics, compare speed to TSNet/PTSNet, and export study reports. These scripts are
for learning and ad hoc runs; they are **not** the CI regression suite.

> **Looking for correctness gates?** Pytest lives in `tests/`. Interactive
> walkthroughs that mirror those tests are listed under
> [Validation](#validation). New notebooks and lab datasets live under
> [`validation/`](validation/); legacy copies remain in `examples/` for older Binder URLs.

| Script | Purpose |
|---|---|
| `basic_example.py` | Minimal Joukowsky case with optional plotting |
| `load_from_inp.py` | EPANET `.inp` import and transient event |
| `transient_study_report.py` | Run a transient and export study summaries (CSV/JSON) |
| `benchmark_vs_tsnet.py` | Single-case TSNet timing comparison |
| `benchmark_matrix.py` | Multi grid-size TSNet performance matrix |
| `benchmark_ptsnet_vs_tsnet.py` | rthym_moc vs TSNet vs PTSNet (TNET3 + optional surge cases) |
| `test_wave_reflections.py` | Wave period and damping vs analytical $T_0 = 4L/a$ (tutorial script, not `tests/`) |
| `test_gradual_closure.py` | Joukowsky criterion and K-model valve closure (tutorial script, not `tests/`) |
| `test_surge_tank.py` | Standpipe mass oscillation and pressure mitigation (tutorial script, not `tests/`) |
| `verify_rthym_webapp.py` | Ad hoc cross-check against R-THYM web-app exports |

Pedagogy-only notebook (slow, not a pytest mirror): `dvcm_showcase.ipynb` — Legacy
vs DVCM at a valve. See [Validation](#validation) for regression-style DVCM notebooks.

---

## Validation

| If you want to… | Open / run | What you'll see |
|-----------------|------------|-----------------|
| **Textbook closure regimes** | [`gradual_closure_verification.ipynb`](examples/gradual_closure_verification.ipynb) | Instant / moderate / slow closure vs Joukowsky and Allievi expectations |
| **Another engine + EPANET** | [`cross_engine_surge_verification.ipynb`](examples/cross_engine_surge_verification.ipynb) | TSNet B.8 export + **wntr** steady state before trip |
| **Surge devices vs formulas** | [`surge_device_verification.ipynb`](examples/surge_device_verification.ipynb) | Standpipe, HPT, air valve vs analytical / Appendix B.8 refs |
| **DVCM vs continuity math** | [`dvcm_physical_verification.ipynb`](examples/dvcm_physical_verification.ipynb) | Mass-step and collapse ΔH **PASS/FAIL** metrics |
| **Long-pipeline surge (multi-mile sloping reach)** | [`long_pipeline_surge_verification.ipynb`](examples/long_pipeline_surge_verification.ipynb) | LP-02–LP-04 directional checks: summit static min, interior cavity, collapse spike |
| **Published lab benchmark** (loose; see doc) | [`bergant_adelaide_verification.ipynb`](examples/bergant_adelaide_verification.ipynb) | Digitized He Fig. 4 vs DVCM — [limitations](docs/bergant_adelaide_verification.md) |
| **Same checks, no Jupyter** | `pytest tests/test_gradual_closure_benchmark.py tests/test_tsnet_standpipe_cross_engine.py tests/test_dvcm_physical_verification.py -v` | CI gates on the rows above |

**Why quickstart feels like “only Joukowsky”:** [`quickstart_notebook.ipynb`](examples/quickstart_notebook.ipynb) is mainly a **tutorial**. §2 plots the first-step surge vs the analytical estimate; that is the externally meaningful part. §3 overlays the checked-in **R-THYM web-app CSV** — a **maintainer** cross-check, not something to cite to outside reviewers.

**What pytest covers but notebooks barely show:** EPANET import fidelity, Bergant scalar peaks, pipe-material wave speed, and dozens of regression modules — see [validation_notebook_coverage.md](docs/validation_notebook_coverage.md) for **Full / Partial / None**.

### Maintainer parity (R-THYM web app — author cross-check)

| Case | Open / run | Notes |
|------|------------|-------|
| Joukowsky benchmark | `pytest tests/test_joukowsky_rthym.py -v` | Also asserts analytical Joukowsky **< 0.05 %**; R-THYM trace RMS ≤ 4 psi is parity only |
| Long-pipe valve study | [`long_pipe_valve_verification.ipynb`](examples/long_pipe_valve_verification.ipynb) (~3 min) | Five-pipe equal-% closure vs checked-in R-THYM JSON/CSV |

---

Validation and regression live under `tests/` with explicit tolerances. This is
separate from [Examples](#examples): examples teach usage; the material below
states **what kind of check** each test is.

| Trust model | Question | Where |
|---|---|---|
| **Independent verification** | Does rthym-moc match theory, EPANET/**wntr**, TSNet, or published measurements? | Analytical, cross-engine (non-author), and lab-anchored tests — [docs/validation.md](docs/validation.md#verification-vs-regression-read-this-first) |
| **Maintainer parity** | Does the Python port still match the author's R-THYM web-app exports? | `test_joukowsky_rthym.py`, `test_long_pipe_valve.py`; quickstart §3, `long_pipe_valve_verification.ipynb` — **not** a third-party oracle |
| **Snapshot regression** | Did we drift from a prior accepted rthym-moc answer? | e.g. `tests/dvcm_*_reference.json` + `test_dvcm_canonical_scenarios.py` |
| **Design-rule / behavioral** | Do sizing and placement sweeps behave as expected? | Surge benchmark modules (monotonic trends on fixed geometries) |

| Layer | Role | Where |
|---|---|---|
| **Automated tests** | CI pass/fail (`pytest -q`) | `tests/` + [docs/validation.md](docs/validation.md) |
| **Interactive notebooks** | Same cases in Binder (labeled by trust model) | [`validation/notebooks/`](validation/notebooks/) (preferred) and `examples/*_verification*.ipynb` (legacy URLs) — [docs/validation_notebooks.md](docs/validation_notebooks.md) |
| **Reference datasets** | Published lab traces and literature anchors | [`validation/datasets/`](validation/datasets/) (e.g. Bergant–Simpson Adelaide) |

### Run tests

```bash
pytest -q
```

Headline **independent verification** checks (external references):

```bash
pytest tests/test_gradual_closure_benchmark.py tests/test_complex_topology_from_inp.py \
  tests/test_tsnet_standpipe_cross_engine.py tests/test_surge_device_verification.py \
  tests/test_dvcm_physical_verification.py \
  tests/test_dvcm_bergant_adelaide_experiment.py \
  tests/test_dvcm_bergant_adelaide_trace.py -q
```

Maintainer parity (R-THYM web app):

```bash
pytest tests/test_joukowsky_rthym.py tests/test_long_pipe_valve.py -q
```

Long-pipeline validation (Phase 7 — directional LP-02–LP-04 on multi-mile sloping reach):

```bash
pytest tests/test_long_pipeline_surge.py tests/test_long_pipeline_surge_utils.py \
  tests/test_long_pipeline_surge_verification.py -q
```

### Slow / long-pipeline tests

Default `pytest` **excludes** `@pytest.mark.slow` probes (see `pyproject.toml` `addopts`).
These run in a dedicated PR CI job or on demand:

| Test module | Marker | Purpose | Local command |
|---|---|---|---|
| `tests/test_long_pipeline_perf.py` | `slow` (benchmark only) | LP-PERF-01: 20-mile capped grid wall-clock budget + baseline regression | `pytest -m slow tests/test_long_pipeline_perf.py -v` |
| `tests/test_long_pipeline_surge.py` | `slow` (one test) | Full 8 s canonical transient window | `pytest tests/test_long_pipeline_surge.py -m slow -v` |
| `tests/test_transient_friction_model.py` | `slow` (subset) | Long-pipe Vitkovsky damping comparison | `pytest -m slow tests/test_transient_friction_model.py -v` |

Non-slow tests in `test_long_pipeline_perf.py` (`load_lp_perf_baseline`, `format_lp_perf_report`)
run in the default suite. See [long_pipeline_phase0_baseline.md](docs/long_pipeline_phase0_baseline.md) §4.

**Long-pipeline features are opt-in** — `record_pipe_profiles`, `enable_interior_dvcm`,
`elevation_profile`, and grid scaling default off or empty; legacy `run()` output is unchanged.
See [long_pipeline_rthym_migration.md](docs/long_pipeline_rthym_migration.md) and
[long_pipeline_surge_roadmap.md](docs/long_pipeline_surge_roadmap.md) Phase 7.

### Independent verification (source of truth outside rthym-moc)

| Category | Reference | Key tests / notebooks |
|---|---|---|
| Analytical hydraulics | Joukowsky / Allievi / B.8 formulas | `test_gradual_closure_benchmark.py`, `test_standpipe_surge_protection.py`, `test_surge_device_verification.py`; `gradual_closure_verification.ipynb`, `surge_device_verification.ipynb` |
| EPANET steady state | **wntr** on `complex_topology.inp` | `test_complex_topology_from_inp.py`; `epanet_import_verification.ipynb` |
| TSNet standpipe | Checked-in TSNet B.8 export | `test_tsnet_standpipe_cross_engine.py`; `cross_engine_surge_verification.ipynb` |
| DVCM physics | Wylie mass step + collapse ΔH | `test_dvcm_physical_verification.py`; `dvcm_physical_verification.ipynb` |
| DVCM Bergant Adelaide rig | Published lab peaks + digitized Fig. 4 (He et al. 2025) | `test_dvcm_bergant_adelaide_experiment.py`, `test_dvcm_bergant_adelaide_trace.py`; [bergant_adelaide_verification.md](docs/bergant_adelaide_verification.md), `bergant_adelaide_verification.ipynb` |
| Long-pipeline surge (LP-02–LP-04) | Directional multi-mile sloping reach with interior DVCM | `test_long_pipeline_surge.py`, `test_long_pipeline_surge_verification.py`; `long_pipeline_surge_verification.ipynb` |

### Maintainer parity (R-THYM web app — author cross-check)

| Category | Reference | Key tests / notebooks |
|---|---|---|
| R-THYM Joukowsky | Checked-in web-app JSON/CSV **+** analytical Joukowsky in same test | `test_joukowsky_rthym.py`; `quickstart_notebook.ipynb` (§3 = parity overlay; §2 = analytical) |
| R-THYM long-pipe valve | Checked-in web-app JSON/CSV | `test_long_pipe_valve.py`; `long_pipe_valve_verification.ipynb` |

Headline results (independent checks):

- Joukowsky first-step surge vs analytical: **< 0.05 %** (`test_joukowsky_rthym.py` — analytical assertion; same module also runs R-THYM parity)
- Wave oscillation period vs $T_0 = 4L/a$: **< 0.2 %** (`examples/test_wave_reflections.py`)
- Bergant Adelaide severe: literature second-peak **~2057 kPa** abs; pytest anchors peak
  ratio in a narrow window (**35%** limit) — full trace overlay is **not** a tight match
  (`test_dvcm_bergant_adelaide_*`; see [bergant doc](docs/bergant_adelaide_verification.md))

Maintainer parity (cite only for port regression, not external proof):

- R-THYM pressure trace RMS (early post-closure window): **≤ 4 psi** (`test_joukowsky_rthym.py`)

### Snapshot regression (detect drift, not absolute correctness)

| What | Baseline | Key tests / notebooks |
|---|---|---|
| DVCM junction traces | Golden `tests/dvcm_*_reference.json` from an earlier rthym-moc run | `test_dvcm_canonical_scenarios.py`; `dvcm_canonical_verification.ipynb` |

### Design-rule regressions (expected trends on fixed geometries)

Standpipe size, HPT placement, pipe length, and mixed-device sweeps —
`test_tank_size_benchmark.py`, `test_device_placement_benchmark.py`, and related
modules. Partial Binder mirror: `surge_design_rules_verification.ipynb`.

Full trust-model map, tolerance policy, and artifact inventory:
[docs/validation.md](docs/validation.md). Pytest↔notebook matrix:
[docs/validation_notebook_coverage.md](docs/validation_notebook_coverage.md).

Long-form cross-engine narratives:
[docs/appendix_b_verification.md](docs/appendix_b_verification.md).

### Interactive verification notebooks (Binder)

**Start here:** [`validation/notebooks/validation_notebooks_index.ipynb`](validation/notebooks/validation_notebooks_index.ipynb)
(preferred Binder entry) or [`docs/validation_notebooks.md`](docs/validation_notebooks.md)
(recommended order, runtimes, pytest mirrors). Legacy index:
[`examples/validation_notebooks_index.ipynb`](examples/validation_notebooks_index.ipynb).

| Notebook | Trust model | Purpose |
|---|---|---|
| `validation/notebooks/grid_scaling_verification.ipynb` | Analytical | Courant grid preview via `get_grid_report(dt)` |
| `validation/notebooks/bergant_adelaide_verification.ipynb` | Independent | Bergant lab peaks + digitized He Fig. 4 trace |
| `validation_notebooks_index.ipynb` | — | Navigation only — pick a walkthrough |
| `gradual_closure_verification.ipynb` | Independent | Closure-time sweep vs Joukowsky / Allievi |
| `cross_engine_surge_verification.ipynb` | Independent | TSNet B.8 + EPANET pre-trip vs MOC |
| `surge_device_verification.ipynb` | Independent | Standpipe, HPT, air valve vs analytical / B.8 refs |
| `epanet_import_verification.ipynb` | Independent | `complex_topology.inp` + steady-state overlay (`wntr`) |
| `dvcm_physical_verification.ipynb` | Independent | Mass-balance steps + collapse ΔH formulas |
| `long_pipeline_surge_verification.ipynb` | Independent | Multi-mile sloping reach, interior DVCM (LP-02–04) |
| `bergant_adelaide_verification.ipynb` | Independent | Same as `validation/notebooks/` copy (legacy Binder path under `examples/`) |
| `quickstart_notebook.ipynb` | Maintainer parity | Tutorial + optional R-THYM Joukowsky overlay (§3) |
| `long_pipe_valve_verification.ipynb` | Maintainer parity | Five-pipe equal-% closure vs R-THYM JSON/CSV (~3 min) |
| `dvcm_canonical_verification.ipynb` | **Snapshot** | Replay golden `tests/dvcm_*_reference.json` traces |
| `surge_design_rules_verification.ipynb` | Design-rule | Standpipe size + HPT placement sweeps |

[![Launch Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/jlillywh/RTHYM-MOC/main?labpath=validation%2Fnotebooks%2Fvalidation_notebooks_index.ipynb)
Index ·
[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/jlillywh/RTHYM-MOC/main?labpath=validation%2Fnotebooks%2Fgrid_scaling_verification.ipynb)
Grid scaling ·
[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/jlillywh/RTHYM-MOC/main?labpath=examples%2Fquickstart_notebook.ipynb)
Quickstart ·
[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/jlillywh/RTHYM-MOC/main?labpath=examples%2Fcross_engine_surge_verification.ipynb)
Cross-engine surge ·
[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/jlillywh/RTHYM-MOC/main?labpath=examples%2Fdvcm_canonical_verification.ipynb)
DVCM traces ·
[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/jlillywh/RTHYM-MOC/main?labpath=validation%2Fnotebooks%2Fbergant_adelaide_verification.ipynb)
Bergant Adelaide ·
[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/jlillywh/RTHYM-MOC/main?labpath=examples%2Fsurge_device_verification.ipynb)
Surge devices

The first Binder launch can take a few minutes while the environment builds the
compiled extension.

## Contributing

Contributions are welcome for solver behavior, validation coverage,
performance benchmarks, documentation, examples, and packaging improvements.

If you want to contribute, start with [Developing the C++ core](#developing-the-c-core)
when touching `src/solver/`, then `CONTRIBUTING.md` for local setup, full CI
parity, and pull request expectations. `MAINTENANCE.md` documents
the current review/refactor cadence. Report security issues privately via
[`SECURITY.md`](SECURITY.md) (GitHub private vulnerability reporting or email).
Bug reports are most useful when they include a minimal reproducible network or input file plus the exact commands
and environment used to reproduce the issue.

---

## API Reference

### NodeInput

Describes a single network node.  All fields have defaults; only `id` and `type` are strictly required.

```python
node = rthym_moc.NodeInput()
node.id               = "J1"          # str — unique identifier
node.type             = "Junction"    # str — see table below
node.elevation        = 0.0           # ft above datum
node.head             = 100.0         # ft HGL  (Tank, PressureBoundary)
node.level            = 100.0         # % full  (Tank, derived/legacy compatibility)
node.max_level        = 20.0          # ft depth at 100 % full (Tank)
node.demand           = 0.0           # GPM withdrawal (Junction, OutflowNode)
node.current_setting  = 100.0         # % open (Valve, Turbine; 100 = fully open)
node.diameter         = 8.0           # inches (Valve orifice / Turbine runner; <= 0 is sanitized to 0.01)
node.current_speed    = 100.0         # % rated speed (Pump)
node.ramp_time        = 0.0           # s — VFD pump speed acceleration/deceleration limit (0 = instant)
node.has_power        = True          # electrical power available (Pump/Turbine; grid sync logic)
node.design_head      = 50.0          # ft at BEP (Pump/Turbine design head; <= 0 is sanitized to 50.0)
node.design_flow      = 100.0         # GPM at BEP (Pump/Turbine design flow; <= 0 is sanitized to 100.0)
node.design_velocity  = 0.0           # ft/s (Turbine; derived from design_flow if 0)
node.inertia_wr2      = 45.0          # lb·ft² — pump runner & motor rotational inertia
node.speed_rpm        = 1750.0        # RPM — rated speed of pump or turbine
node.efficiency       = 0.80          # 0.0 to 1.0 — pump or turbine BEP efficiency
node.closure_time     = 0.03          # s — CheckValve exponential close time (default 0.03)
node.closure_damping  = 0.0           # dimensionless CheckValve damping (optional)
node.flipped          = False         # CheckValve: reverse installed direction
node.air_release_head = 0.0           # ft vent reference above elevation (AirValve)
node.air_release_diameter = 0.25      # inches (AirValve small-orifice release port; <= 0 is sanitized to 0.01)
node.tank_area        = 10.0          # ft² cross-sectional area (Standpipe; <= 0 is sanitized to 1e-4)
node.gas_volume       = 10.0          # ft³ initial trapped gas / air-pocket volume
node.tank_volume      = 30.0          # ft³ total vessel or chamber volume
node.polytropic_n     = 1.2           # polytropic exponent (1.0 = isothermal, 1.4 = adiabatic)
node.loss_coeff_in    = 0.7           # C_d orifice coefficient for inflow / air admission
node.loss_coeff_out   = 0.7           # C_d orifice coefficient for outflow / air release
```

**Node types**

| `type` string | Boundary condition | Key fields |
|---|---|---|
| `"Junction"` | Kirchhoff continuity (demand sink) | `demand` |
| `"OutflowNode"` | As Junction, sign convention explicit | `demand` |
| `"InflowNode"` | Injects flow (demand treated as negative) | `demand` |
| `"PressureBoundary"` | Fixed total head at all times | `head` |
| `"Tank"` | Fixed HGL; `head` is authoritative, `level` is compatibility state | `head`, `level`, `max_level` |
| `"CheckValve"` | Inline one-way valve with optional exponential slam dynamics | `diameter`, `closure_time`, `closure_damping`, `flipped` |
| `"AirValve"` | Air-pocket valve with large admission port and small release port | `elevation`, `head`, `diameter`, `air_release_diameter`, `gas_volume`, `tank_volume`, `loss_coeff_in`, `loss_coeff_out`, `air_release_head` |
| `"Valve"` | Quadratic loss, $K = (100/s)^2 - 1$ | `current_setting`, `diameter` |
| `"PRV"` | Pressure reducing — holds downstream `head` setpoint (ft HGL) when regulating | `head`, `diameter` |
| `"PSV"` | Pressure sustaining — holds upstream `head` setpoint (ft HGL) when regulating | `head`, `diameter` |
| `"PBV"` | Pressure breaker — maintains differential head `head` (ft) across the valve | `head`, `diameter` |
| `"Turbine"` | Quadratic loss (design-curve K) | `current_setting`, `design_velocity`, `diameter` |
| `"Pump"` | Three-coefficient affinity curve | `current_speed`, `has_power`, `design_head`, `design_flow` |
| `"Standpipe"` | Open free-surface surge tank (level tracked each step) | `head`, `tank_area` |
| `"HydropneumaticTank"` | Closed pressurised vessel; gas follows polytropic law | `head`, `diameter`, `gas_volume`, `tank_volume`, `polytropic_n`, `loss_coeff_in`, `loss_coeff_out` |

For `"Tank"`, prefer setting `head` directly. The `level` field is retained for
compatibility with older code paths and is derived from `head` and `max_level`
when EPANET networks are imported.

A dead-end boundary — equivalent to an instantaneously closed valve — is modelled as a `"Junction"` with `demand = 0` and no outflow pipe attached.  The MOC boundary condition then enforces $Q = 0$ exactly, giving $H = C^+$.

### PipeInput

Describes a single pipe segment connecting two nodes.

```python
pipe = rthym_moc.PipeInput()
pipe.id             = "P1"     # str — unique identifier
pipe.from_node      = "R1"     # str — upstream node id
pipe.to_node        = "J1"     # str — downstream node id
pipe.length         = 3000.0   # ft
pipe.diameter       = 12.0     # inches (<= 0 is sanitized to 0.01, and initial flow is overridden to 0)
pipe.roughness      = 120.0    # Hazen-Williams C (higher = smoother)
pipe.minor_loss     = 0.0      # dimensionless local-loss coefficient K
pipe.flow_gpm       = 500.0    # GPM, initial steady-state flow (+ = from→to)
pipe.wall_thickness = 0.25     # inches (used only if youngs_modulus > 0; <= 0 is sanitized to 0.01)
pipe.youngs_modulus = 0.0      # psi (0 = rigid pipe, default wave speed ~4000 ft/s)
pipe.poissons_ratio = 0.3      # (used only if youngs_modulus > 0)
pipe.elevation_profile = []    # optional [(chainage_ft, elevation_ft), ...] survey table
pipe.interior_dvcm_chainages_ft = []  # optional sparse interior DVCM watchpoints (ft from upstream end)
```

When `elevation_profile` is empty (default), each MOC grid point uses ground
elevation linearly interpolated between `from_node` and `to_node` elevations.
Provide at least two `(chainage_ft, elevation_ft)` pairs measured from the
upstream pipe end to override with a piecewise-linear survey. Local elevation
feeds profile gauge pressure, `pipe_profile_cavitation` screening, and interior
DVCM vapor-head limits when `enable_interior_dvcm=True`.

```python
pipe.elevation_profile = [(0.0, 120.0), (26400.0, 340.0), (52800.0, 95.0)]
pipe.interior_dvcm_chainages_ft = [26400.0]  # optional: DVCM only at listed chainages
```

SI helper: `pipe_si(..., elevation_profile_m=[(0.0, 36.6), ...])`.
When `enable_interior_dvcm=True` and `interior_dvcm_chainages_ft` is empty, every
interior MOC grid point on that pipe participates in DVCM. When the list is
non-empty, only the nearest grid indices to those chainages are tracked (sparse mode).

`pipe.minor_loss` is a dimensionless local-loss coefficient $K$ for bends,
tees, fittings, entrance/exit losses, or any other concentrated resistance you
want associated with that pipe. During initialisation, the solver includes this
term in the steady headloss,

$$H_{f,minor} = K \frac{V^2}{2g}$$

and during the transient it is applied as an added resistance contribution
distributed across the pipe segments. That distribution is a practical MOC
approximation of a lumped local loss, and the test suite now includes explicit
benchmarks against an equivalent lumped-loss case.

**Wave speed** is computed intenally from the Korteweg–Joukowsky elastic formula when `youngs_modulus > 0`:

$$a = \sqrt{\frac{K_f/\rho}{1 + (K_f D)/(E\,e)}}$$

where $K_f$ is the bulk modulus of water, $E$ is `youngs_modulus`, $D$ is the pipe diameter, and $e$ is `wall_thickness`.  When `youngs_modulus = 0`, a rigid-pipe wave speed of 4720 ft/s is used as the starting point before Courant adjustment.

The solver automatically adjusts the wave speed so that $a_\text{adj} = L / (N_\text{segs} \cdot dt)$ exactly (Courant = 1), where $N_\text{segs} = \text{round}(L / (a \cdot dt))$.

### MOCSolver

```python
solver = rthym_moc.MOCSolver()
```

| Method | Description |
|--------|-------------|
| `solver.add_node(node)` | Append a `NodeInput` to the network. |
| `solver.add_pipe(pipe)` | Append a `PipeInput` to the network. |
| `solver.clear()` | Remove all nodes, pipes, and schedules. |
| `solver.add_control_rule(rule)` | Register a dynamic operational control rule. |
| `solver.clear_control_rules()` | Clear all registered control rules. |
| `solver.get_node_head(id)` | Query the current piezometric HGL head (ft) of a node. |
| `solver.get_node_pressure(id)` | Query the current gauge pressure (psi) of a node. |
| `solver.set_valve_setting(id, pct_open)` | Change a valve's opening immediately (used between `run()` calls). |
| `solver.set_pump_speed(id, pct_speed)` | Change a pump speed immediately. |
| `solver.set_pump_power(id, has_power)` | Set pump electrical power (PCV shutdown vs outage). |
| `solver.set_node_demand(id, demand_gpm)` | Change a junction demand immediately. |
| `solver.set_node_head(id, head_ft)` | Change a fixed-head boundary's stored head between `run()` calls. |
| `solver.set_valve_schedule(id, schedule)` | Register a time-varying valve schedule (see below). |
| `solver.set_pump_schedule(id, schedule)` | Register a time-varying pump-speed schedule. |
| `solver.set_demand_schedule(id, schedule)` | Register a time-varying junction demand schedule. |
| `solver.set_head_schedule(id, schedule)` | Register a time-varying fixed-head schedule for a `PressureBoundary` or `Tank`. |
| `solver.set_friction_model(model)` | Set the transient friction selector (`TransientFrictionModel`; default `BrunoneIIR`). |
| `solver.get_friction_model()` | Return the current transient friction selector. |
| `solver.set_cavitation_model(model)` | Set persistent cavitation model (`LegacyClamp` or `DVCM`). |
| `solver.get_cavitation_model()` | Return the current cavitation model. |
| `solver.set_enable_interior_dvcm(enable)` | Persistently enable/disable interior-point DVCM (default `False`). |
| `solver.get_enable_interior_dvcm()` | Return whether interior DVCM is enabled. |
| `solver.set_grid_policy(...)` | Configure long-pipe grid cap and wave-speed distortion limits (see below). |
| `solver.get_grid_report(dt)` | Build the MOC grid for `dt` and return Courant metadata without time integration (see below). |
| `solver.get_grid_distortion_warning()` | Return the distortion-policy message from the last `run()` or `get_grid_report()`. |
| `solver.set_max_segments_per_pipe(n)` | Cap MOC segments per pipe (`0` = uncapped). |
| `solver.get_max_segments_per_pipe()` | Return the segment cap. |
| `solver.run(...)` | Execute the transient and return results (see below). |

Report helpers in `rthym_moc.report`: **`summarize_grid_report(report)`** (per-pipe table)
and **`format_grid_report(report)`** (human-readable text). Both accept `get_grid_report()`
output or compatible `run()` metadata.

**`set_grid_policy()`** (long-pipe grid scaling):

```python
solver.set_grid_policy(
    max_segments_per_pipe=2000,       # cap segments; 0 = uncapped (legacy behavior)
    max_wave_speed_distortion=0.15,   # warn/error if |a_adj − a_design| / a_design exceeds this
    distortion_action="warn",         # "warn" or "error"
)
```

When a cap is active, `initGrid()` coarsens the spatial grid and adjusts wave speed
to preserve Courant = 1. Per-pipe `pipe_num_segments`, `pipe_wave_speed_design_fps`,
`pipe_wave_speed_adjusted_fps`, and `pipe_distortion_pct` appear in `run()` results.

Preview the grid **before** a long transient with `get_grid_report(dt)` — same metadata
plus `pipe_dx_ft`, `pipe_courant_number` (expected ≈ 1.0), and optional distortion
warnings. Example:

```python
from rthym_moc import format_grid_report

report = solver.get_grid_report(dt=0.01)
print(format_grid_report(report))
results = solver.run(total_time=600.0, dt=0.01)  # same grid metadata in results
```

Walkthrough: [`validation/notebooks/grid_scaling_verification.ipynb`](validation/notebooks/grid_scaling_verification.ipynb).

#### `run()` parameters

```python
results = solver.run(
    total_time = 10.0,    # float, seconds — simulation duration
    dt         = 0.01,    # float, seconds — time step
    p_vapor    = -14.0,   # float, psi     — vapour pressure (negative = subatmospheric)
    usf_tau    = 0.5,     # float, seconds — unsteady-friction IIR time constant (BrunoneIIR only)
                          #   set to dt to disable the IIR filter (USF still active unless Steady)
    k_bru      = -1.0,    # float — Brunone USF coefficient (BrunoneIIR / Vitkovsky; see below)
    friction_model = None,  # TransientFrictionModel | None — override selector for this run
    cavitation_model = None,  # CavitationModel | None — override junction/interior cavitation model
    record_pipe_profiles = False,  # bool — export interior MOC grid H/P/V per pipe (optional)
    profile_stride       = 1,      # int  — spatial downsampling along each pipe (optional; ≥ 1)
    enable_interior_dvcm = False,  # bool — track vapor cavities at interior grid points (DVCM only)
)
```

**`friction_model` (transient friction selector).**  When `None` (default), the
solver uses the mode set by `set_friction_model()` (initially `BrunoneIIR`).
Pass an explicit value to override for a single `run()` without changing the
persistent setting.  See [Transient friction](#transient-friction) below.

**`k_bru` (Brunone unsteady friction).**

| Value | Behavior |
|---|---|
| `-1` (default) | Dynamic Vardy–Brown: coefficient computed each step from local Reynolds number |
| `0` | No USF term (same effect as `TransientFrictionModel.Steady` for the unsteady part) |
| `> 0` | User-supplied static coefficient (typical turbulent range: 0.02–0.15) |

Applies to **`BrunoneIIR`** and **`Vitkovsky`** only; `Steady` and `QuasiSteady` ignore
the unsteady term regardless of `k_bru`.

**`record_pipe_profiles` / `profile_stride` (optional interior pipe export).**

| Parameter | Default | Behavior |
|---|---|---|
| `record_pipe_profiles` | `False` | When `True`, populate optional per-pipe profile keys in the results dict (see [Optional per-pipe MOC profiles](#optional-per-pipe-moc-profiles)). When `False`, those keys are omitted and `run()` output matches legacy behavior. |
| `profile_stride` | `1` | Keep every `stride`-th interior MOC grid point along each pipe. Pipe-end stations are always retained. Must be ≥ 1. |

**`cavitation_model`.** When `None` (default), the solver uses the model set by
`set_cavitation_model()` (initially `LegacyClamp`). Pass `CavitationModel.DVCM` for
discrete vapor cavities at junctions and — with `enable_interior_dvcm=True` — at
interior grid points on pipes with terrain surveys. See [Cavitation models](#cavitation-models).

**`enable_interior_dvcm`.** Default `False`. When `True` and `cavitation_model=DVCM`,
the solver applies junction-style cavity regime switching at interior MOC stations
using local `z(x)` from `elevation_profile`. Requires `record_pipe_profiles=True`
to export `pipe_profile_cavity_volume` and `pipe_profile_cavity_active`. Use
`PipeInput.interior_dvcm_chainages_ft` for sparse watchpoints only. See
[Long-pipeline surge & interior DVCM](#long-pipeline-surge--interior-dvcm).

Each call to `run()` rebuilds the MOC grid from the steady-state initial conditions stored in the `NodeInput` / `PipeInput` objects.  Node and pipe inputs persist across calls; call `set_valve_setting()` etc. *before* the next `run()` to change initial conditions for the next segment.

### ControlRuleInput

Operational control rules are configured with `ControlRuleInput` and registered via `solver.add_control_rule()`. See [Operational Controls & Event Logic](#operational-controls--event-logic) for worked examples.

```python
rule = rthym_moc.ControlRuleInput()
rule.id                  = "rule_id"       # str — unique rule identifier
rule.type                = rthym_moc.ControlType.Threshold  # Threshold | Deadband | PID | PCV
rule.monitored_node      = "J1"            # node whose quantity is observed
rule.controlled_node     = "V1"            # pump or valve node to actuate
rule.monitored_quantity  = "pressure"      # "pressure" | "head" | "level" | "flow"
rule.monitored_pipe      = "P1"            # required when monitored_quantity == "flow"
rule.condition           = "gt"            # Threshold: "lt" or "gt"
rule.threshold           = 45.0            # Threshold/Deadband/PCV trigger or ramp time (s)
rule.target              = 0.0             # Threshold/PID setpoint
rule.deadband            = 15.0            # Deadband width or PCV close-ramp time (s)
rule.action              = "fill"          # Deadband: "fill" or "drain"
rule.kp                  = 2.0             # PID proportional gain
rule.ki                  = 1.0             # PID integral gain
rule.kd                  = 0.1             # PID derivative gain
```

### Results dictionary

`run()` retuns a Python `dict` whose values are NumPy arrays (zero-copy where possible):

```python
t           = np.array(results["time"])                     # (N,) float64, seconds
H_node      = np.array(results["node_head"]["NODE_ID"])     # (N,) float64, ft
P_node      = np.array(results["node_pressure"]["NODE_ID"]) # (N,) float64, psi
Q_pipe      = np.array(results["pipe_flow_gpm"]["PIPE_ID"]) # (N,) float64, GPM
cav_flag    = np.array(results["node_cavitation"]["NODE_ID"])# (N,) int32, 0 or 1
cav_vol     = np.array(results["node_cavity_volume"]["NODE_ID"])         # (N,) float64, ft^3 (populated when using DVCM)
cav_active  = np.array(results["node_cavity_active"]["NODE_ID"])         # (N,) int32, 0/1 (populated when using DVCM)
cav_coll_fl = np.array(results["node_cavity_collapse_flag"]["NODE_ID"])  # (N,) int32, 0/1 this step (populated when using DVCM)
cav_coll    = np.array(results["node_cavity_collapse_count"]["NODE_ID"]) # (N,) int32, cumulative (populated when using DVCM)
valve_pct   = np.array(results["valve_setting"]["V1"])      # (N,) float64, % open (Valve/Turbine)
valve_pos   = np.array(results["valve_position"]["CV1"])    # (N,) float64, 0–1 (CheckValve position)
valve_vel   = np.array(results["valve_velocity"]["CV1"])   # (N,) float64, ft/s (CheckValve disc velocity)
pump_speed  = np.array(results["pump_speed"]["P1"])         # (N,) float64, % rated speed (Pump)
turbine_speed = np.array(results["turbine_speed"]["T1"])    # (N,) float64, % rated speed (Turbine)
```

Every node and every pipe that was added to the solver has a corresponding key in the respective sub-dictionary.  `node_head` records the hydraulic grade line (HGL) at each node.  `node_cavitation` is 1 for any time step at which the computed pressure fell below `p_vapor`.

The cavity channels (`node_cavity_volume`, `node_cavity_active`, `node_cavity_collapse_flag`, `node_cavity_collapse_count`) are standard diagnostic outputs populated when simulating with the `DVCM` model.

`valve_setting` is recorded for `Valve` and `Turbine` nodes.  `valve_position` and `valve_velocity` are recorded for `CheckValve` nodes during slam dynamics.  `pump_speed` is recorded for `Pump` nodes.  `turbine_speed` is recorded for `Turbine` nodes.

#### Optional per-pipe MOC profiles

When `record_pipe_profiles=True`, five additional top-level keys appear.  They are **absent** when the flag is `False` (the default), so existing post-processing code is unaffected.

| Key | Type | Shape | Description |
|---|---|---|---|
| `pipe_profile_chainage_ft` | `dict[str, ndarray]` | `(M,)` per pipe | Distance from the upstream pipe end, ft |
| `pipe_profile_head` | `dict[str, ndarray]` | `(N, M)` per pipe | Piezometric head (HGL) at each chainage station, ft |
| `pipe_profile_pressure` | `dict[str, ndarray]` | `(N, M)` per pipe | Gauge pressure at each chainage station, psi (uses local `z(x)` from `elevation_profile` or endpoint interpolation) |
| `pipe_profile_velocity_fps` | `dict[str, ndarray]` | `(N, M)` per pipe | Flow velocity at each chainage station, ft/s |
| `pipe_profile_cavitation` | `dict[str, ndarray]` | `(N, M)` per pipe | `1` when gauge pressure ≤ vapor pressure at local `z(x)` (pre-DVCM screening) |
| `pipe_profile_cavity_volume` | `dict[str, ndarray]` | `(N, M)` per pipe | Integrated vapor-cavity volume at each station, ft³ (`DVCM` + `enable_interior_dvcm=True`) |
| `pipe_profile_cavity_active` | `dict[str, ndarray]` | `(N, M)` per pipe | `1` when an interior vapor cavity is active at that station (`DVCM` + interior DVCM) |

`N` is the number of recorded time steps (same as `len(results["time"])`).  `M` is the number of profile points along that pipe after spatial downsampling.  The first and last chainage values are the upstream and downstream pipe ends; the corresponding profile heads match `node_head` at those boundary nodes.

When grid scaling is active, these optional top-level keys also appear:

| Key | Type | Description |
|---|---|---|
| `pipe_num_segments` | `dict[str, int]` | MOC segment count per pipe after cap/adjustment |
| `pipe_wave_speed_design_fps` | `dict[str, float]` | Design wave speed before Courant adjustment, ft/s |
| `pipe_wave_speed_adjusted_fps` | `dict[str, float]` | Adjusted wave speed enforcing Courant = 1, ft/s |
| `pipe_distortion_pct` | `dict[str, float]` | Percent difference between design and adjusted wave speed |
| `pipe_interior_dvcm_grid_indices` | `dict[str, list[int]]` | Interior grid indices where DVCM is active (sparse or full) |

`get_grid_report(dt)` returns the keys above plus **`pipe_length_ft`**, **`pipe_dx_ft`**, **`pipe_courant_number`**, **`dt`**, and when a distortion limit is configured **`distortion_warning`** / **`distortion_limit_exceeded`**. It does not integrate the transient.

```python
results = solver.run(total_time=10.0, dt=0.01, record_pipe_profiles=True, profile_stride=2)

x_ft   = np.array(results["pipe_profile_chainage_ft"]["P1"])      # (M,) float64, ft
H_prof = np.array(results["pipe_profile_head"]["P1"])            # (N, M) float64, ft
P_prof = np.array(results["pipe_profile_pressure"]["P1"])        # (N, M) float64, psi
V_prof = np.array(results["pipe_profile_velocity_fps"]["P1"])    # (N, M) float64, ft/s
C_prof = np.array(results["pipe_profile_cavitation"]["P1"])      # (N, M) int, 0/1
```

`results_to_si()` and `run_si()` convert these to SI keys when present:

| US key | SI key (`results_to_si` / `run_si`) |
|---|---|
| `pipe_profile_chainage_ft` | `pipe_profile_chainage_m` |
| `pipe_profile_head` | `pipe_profile_head_m` |
| `pipe_profile_pressure` | `pipe_profile_pressure_kpa` |
| `pipe_profile_velocity_fps` | `pipe_profile_velocity_m_s` |
| `pipe_profile_cavity_volume` | `pipe_profile_cavity_volume_m3` |

Pass `record_pipe_profiles=True` (and optionally `profile_stride`) to `run_si()` the same way as `run()`. Interior cavity volume uses the SI key when `enable_interior_dvcm=True`.

### Post-processing & study reports

After `run()`, use the helpers in `rthym_moc.report` (re-exported at package root) to build engineering summaries without custom analysis code:

```python
summary = rthym_moc.summarize_study(results)
print(rthym_moc.format_study_table(summary))

rthym_moc.export_study_json("study_summary.json", summary)
rthym_moc.export_study_csv("study_output", summary)  # node_envelopes.csv, pipe_flow_envelopes.csv, study_meta.json
```

| Function | Description |
|---|---|
| `summarize_study(results, dt_s=None)` | Build a `StudySummary` dict with node head/pressure envelopes, pipe flow envelopes, optional per-pipe chainage envelopes (when profile keys are present), cavitation duration, and run metadata |
| `series_extrema(time_s, values)` | Min/max of any scalar series plus the times at which they occur |
| `cavitation_summary(time_s, flags, dt_s=None)` | First occurrence, step count, and estimated duration from cavitation flags |
| `format_study_table(summary)` | Plain-text table for logs or reports |
| `export_study_json(path, summary)` | Write the full summary dict to JSON |
| `export_study_csv(directory, summary)` | Write node and pipe envelope CSVs plus metadata JSON |
| `head_to_pressure_psi(head_ft, elevation_ft)` | Convert piezometric head to gauge pressure (psi) |
| `run_acceptance_checks(results, max_pressure_limit, min_pressure_limit, cavitation_time_threshold)` | Evaluate overpressure, subatmospheric, and cavitation duration limits |
| `format_acceptance_report(checks)` | Format acceptance check results into a clean, human-readable text report |
| `summarize_study_si(results, dt_s=None)` | Same as `summarize_study`, with `head_m`, `pressure_kpa`, and `flow_m3s` keys |
| `study_summary_to_si(summary)` | Convert an existing US-customary `StudySummary` to SI |
| `format_study_table_si(summary)` | Plain-text SI table for logs or reports |
| `export_study_csv_si(directory, summary)` | Write SI envelope CSVs plus metadata JSON |
| `head_to_pressure_kpa(head_m, elevation_m)` | Convert piezometric head to gauge pressure (kPa) |

A `StudySummary` has three top-level keys:

- `meta` — `duration_s`, `num_steps`, `dt_s`
- `nodes[id]` — `head_ft`, `pressure_psi` (each an extrema dict with `min`, `min_time_s`, `max`, `max_time_s`), and optional `cavitation` (`occurred`, `first_time_s`, `steps`, `duration_s`)
- `pipes[id]` — `flow_gpm` extrema and times; when `run()` included profile keys, also:
  - `chainage_envelope` — min/max over time at each chainage station (`chainage_ft`, `head_min_ft`, `head_max_ft`, `pressure_min_psi`, `pressure_max_psi`, and `velocity_min_fps` / `velocity_max_fps` when velocity profiles were recorded)
  - `profile_peak` — global worst points on the `(time × chainage)` grid; each quantity is a dict with `value`, `time_s`, and `chainage_ft` (e.g. `pressure_min`, `head_max`)

For SI summaries, use `summarize_study_si(results)` — the structure is the same but node keys are `head_m` / `pressure_kpa`, pipe flow keys are `flow_m3s`, and profile envelope keys use `chainage_m`, `head_min_m`, `pressure_min_kpa`, `velocity_min_m_s`, etc.  With `run_si()`, you can skip the separate `results_to_si()` step:

```python
results_si = rthym_moc.run_si(solver, total_time=10.0, dt=0.01)
summary_si = rthym_moc.summarize_study_si(results_si)
rthym_moc.export_study_csv_si("study_output", summary_si)
```

See `examples/transient_study_report.py` for a complete CLI workflow:

```bash
python examples/transient_study_report.py --out study_output
```

---

## Unit conventions

The solver's native API boundary uses US customary units:

| Quantity | Unit |
|----------|------|
| Heads, elevations, lengths | ft |
| Pressures | psi |
| Flows | GPM (US gallons per minute) |
| Pipe diameter, wall thickness | inches |
| Wave speed | ft/s |
| Time | s |
| Valve / pump settings | % (0 – 100) |

These native units remain the internal solver contract for backward
compatibility and for existing EPANET-derived workflows.  SI projects can use
the convenience helpers in `rthym_moc.units` (re-exported at package root) to
build models and read results in metric units without changing the C++ core.

```python
import rthym_moc as m

solver = m.MOCSolver()
solver.add_node(m.node_si("R1", "PressureBoundary", head_m=45.72))
solver.add_node(m.node_si("J1", "Junction", elevation_m=0.0, head_m=30.48))
solver.add_pipe(
    m.pipe_si(
        "P1",
        "R1",
        "J1",
        length_m=914.4,
        diameter_mm=304.8,
        roughness=130.0,
        flow_m3s=0.0315,
    )
)

results_si = m.results_to_si(solver.run(total_time=1.0, dt=0.01))
head_m = results_si["node_head_m"]["J1"]
flow_m3s = results_si["pipe_flow_m3s"]["P1"]
```

SI helper inputs use:

| Quantity | Helper unit |
|----------|-------------|
| Heads, elevations, lengths | m |
| Pressures retuned by `results_to_si()` | kPa |
| Flows | m^3/s |
| Pipe diameter, wall thickness | mm |
| Wave speed / valve velocity outputs | m/s |
| Optional per-pipe profiles (`record_pipe_profiles=True`) | `pipe_profile_chainage_m`, `pipe_profile_head_m`, `pipe_profile_pressure_kpa`, `pipe_profile_velocity_m_s` |
| Young's modulus in `pipe_si()` | Pa |
| Time and valve / pump settings | unchanged (`s`, `%`) |
| Head / demand schedules | m and m³/s via `set_head_schedule_si()` / `set_demand_schedule_si()` |
| Mid-simulation head / demand | m and m³/s via `set_node_head_si()` / `set_node_demand_si()` |
| Cavitation threshold in `run_si()` | kPa (`DEFAULT_P_VAPOR_KPA` ≈ −14 psi) |
| Live node queries | m / kPa via `get_node_head_si()` / `get_node_pressure_si()` |
| EPANET override kwargs | m / m³/s via `load_inp_si()` |
| `[RTHYM]` surge parameters | follow EPANET `Units` (m², m³, mm when `LPS`, etc.) |

SI API quick reference (all exported from `rthym_moc`):

| Function | Purpose |
|---|---|
| `node_si`, `pipe_si` | Build `NodeInput` / `PipeInput` from SI kwargs |
| `results_to_si` | Post-process a US `run()` results dict |
| `run_si` | Run transient and return SI results dict |
| `control_rule_si` | Build `ControlRuleInput` from SI thresholds/setpoints |
| `set_head_schedule_si`, `set_demand_schedule_si` | Time-varying head (m) / demand (m³/s) |
| `set_node_head_si`, `set_node_demand_si` | Point updates between runs |
| `get_node_head_si`, `get_node_pressure_si` | Query current head / pressure |
| `load_inp_si` | EPANET import with SI override kwargs |
| `summarize_study_si`, `export_study_csv_si`, … | SI study reports |
| `convert_head_schedule_si`, `convert_demand_schedule_si` | Convert schedule lists without calling the solver |
| `length_m_to_ft`, `flow_m3s_to_gpm`, … | Scalar conversion helpers |

Common conversion constants and helpers are exported for convenience:

```python
rthym_moc.GPM_TO_CFS   # = 0.002228  (multiply GPM to get ft³/s)
rthym_moc.G_FT_S2      # = 32.2      (ft/s²)
rthym_moc.PSI_TO_FT    # = 2.307692… (multiply psi to get ft of head)
rthym_moc.M_TO_FT
rthym_moc.GPM_TO_M3S
rthym_moc.PSI_TO_KPA
rthym_moc.length_m_to_ft(10.0)
rthym_moc.flow_gpm_to_m3s(500.0)
```

See `examples/si_quickstart.py` for a complete SI-first example.

SI control rules use `control_rule_si()` with quantity-specific keywords (`threshold_kpa`, `threshold_m`, `threshold_m3s`, `threshold_pct`, `setpoint_kpa`, …).  For `ControlType.Threshold`, pass the controlled device setting as `target_pct` (0–100).  For `ControlType.PCV`, use `threshold_s` and `deadband_s` for valve ramp times.  PID gains (`kp`, `ki`, `kd`) are passed through unchanged — retune when switching from US-customary rules.

SI time-varying boundaries:

```python
m.set_head_schedule_si(solver, "R1", [(0.0, 30.48), (0.4, 45.72)])      # head m
m.set_demand_schedule_si(solver, "J1", [(0.0, 0.0), (1.0, 0.0315)])    # demand m³/s
m.set_node_head_si(solver, "R1", 36.576)
m.set_node_demand_si(solver, "J1", 0.0126)
```

Valve and pump schedules remain dimensionless ``(time_s, pct)`` — use ``set_valve_schedule()`` and ``set_pump_schedule()`` directly.

Run, query, and EPANET overrides:

```python
results_si = m.run_si(solver, total_time=1.0, dt=0.01, p_vapor_kpa=-96.5)
head_m = m.get_node_head_si(solver, "J1")
pressure_kpa = m.get_node_pressure_si(solver, "J1")

solver = m.load_inp_si(
    "network.inp",
    initial_flows_m3s={"P1": 0.0315},
    initial_heads_m={"J1": 30.48},
    stub_length_m=12.192,
)
```

``run_si()`` defaults ``p_vapor_kpa`` to the same full-vacuum threshold as ``run(..., p_vapor_psi=-14.0)`` (see ``DEFAULT_P_VAPOR_KPA``).

---

## Valve model

The solver uses a quadratic loss model:

$$K(s) = \left(\frac{100}{s}\right)^2 - 1, \qquad s \in (0, 100]$$

where $s$ is the valve opening in percent.  This is consistent with a generic butterfly/globe valve where the discharge coefficient scales as $C_d \propto s/100$.  The minimum clamp is $s = 10^{-6}$%, giving $K \approx 10^{16}$ (effectively zero flow).

**Important implication for gradual-closure studies.**  Because $K$ grows as $1/s^2$, the valve does not significantly restrict flow until $s$ approaches a critical value

$$s_\text{crit} = \frac{100}{\sqrt{K_\text{pipe}+1}}$$

where $K_\text{pipe} = H_f / (V_0^2/2g)$ is the pipe's equivalent loss coefficient at the initial steady-state flow.  The *effective closure time*

$$T_\text{eff} \approx \frac{T_c}{\sqrt{K_\text{pipe}+1}}$$

is the interval during which most of the flow stoppage actually occurs.  A linear setting schedule satisfies the Joukowsky criterion ($\Delta H = aV_0/g$) whenever $T_\text{eff} < 2L/a$, regardless of the nominal stroke time $T_c$.

---

## Valve closure types

Four closure profiles are supported.  All are passed to the solver via `set_valve_schedule()` as a `list[tuple[float, float]]` of `(time_s, pct_open)` pairs.  The solver linearly interpolates between breakpoints at each time step; any time beyond the last point holds the final value.

| Type | Description | Required parameters |
|---|---|---|
| Linear | Constant-rate closure over a stroke time | `stroke_time` |
| Equal-Percentage | Geometric-series decay; each step removes a fixed fraction of remaining opening | `stroke_time`, `step_interval` |
| Two-Stage | Fast stage to a transition point, then slow stage to zero | `transition_pct`, `stage1_time`, `stage2_time` |
| Custom | Arbitrary piecewise-linear profile from a user-supplied `(t_offset, pct_open)` table | user-supplied table |

### Linear

Valve closes at a constant rate from the initial opening to fully closed over the stroke time.  Models motor-operated gate valves and ball valves driven at constant actuator speed.

```python
import numpy as np

s0, T_c, dt = 100.0, 3.0, 0.01
t_vals   = np.arange(0.0, T_c + dt, dt)
pct_open = np.clip(s0 * (1.0 - t_vals / T_c), 0.0, s0)
solver.set_valve_schedule("V1", list(zip(t_vals.tolist(), pct_open.tolist())))
```

### Equal-Percentage

Each closure step removes a fixed *fraction* of the remaining opening (geometric series).  Models equal-percentage trim control valves running at constant actuator speed.

```python
s0, stroke_time, step_interval = 100.0, 2.0, 0.05
N     = round(stroke_time / step_interval)
ratio = (0.05 / s0) ** (1.0 / (N - 1))      # geometric decay toward near-zero
steps     = [s0 * ratio**i for i in range(N)] + [0.0]
t_offsets = [i * step_interval for i in range(N + 1)]
solver.set_valve_schedule("V1", list(zip(t_offsets, steps)))
```

### Two-Stage

A programmed actuator changes its closure rate at a pre-set *transition opening*.  Stage 1 closes quickly from the initial opening to the transition point; Stage 2 closes slowly from the transition point to fully closed.

**Key design rule**: Stage 2 time should satisfy $T_{\text{stage2}} \geq 2L/a$ so that the Joukowsky wave retuns before closure completes, reducing the peak pressure rise.

```python
s0, trans_pct = 100.0, 15.0
stage1_time, stage2_time = 3.0, 30.0        # stage2 >= 2L/a recommended
schedule = [
    (0.0,                           s0),
    (stage1_time,                   trans_pct),
    (stage1_time + stage2_time,     0.0),
]
solver.set_valve_schedule("V1", schedule)
```

### Custom

User-supplied arbitrary piecewise-linear closure profile.  Intended for importing actuator data sheets or field-measured closure curves.  Time values are absolute simulation times.

```python
schedule = [
    (0.00, 100.0),
    (0.20,  50.0),
    (0.80,  10.0),
    (1.50,   0.0),
]
solver.set_valve_schedule("V1", schedule)
results = solver.run(total_time=5.0, dt=0.01)
```

## Operational Controls & Event Logic

In addition to static time-varying schedules, the solver supports active, state-based operational controls evaluated at each time step ($dt$) inside the core engine. This allows simulating realistic system responses to dynamic transient events (e.g., pressure-relief valve opening, tank level control, variable speed pump modulation).

Control rules are registered using `ControlRuleInput` and added via `solver.add_control_rule()`.  For SI thresholds and setpoints, use `control_rule_si()` instead — see [Unit conventions](#unit-conventions).

### Control Types

The solver supports four control strategies (`rthym_moc.ControlType`):

1. **Threshold**: Switches a pump's speed or a valve's opening to a `target` value when a monitored quantity (pressure, head, level, or flow) crosses a `threshold` (with `"lt"` or `"gt"` conditions). Use `monitored_pipe` when `monitored_quantity == "flow"`.
2. **Deadband**: Maintains a level or pressure within a range (`[threshold, threshold + deadband]`) using `"fill"` or `"drain"` logic, switching a controlled pump/valve ON ($100\%$) or OFF ($0\%$).
3. **PID**: Continuously modulates a pump's speed or valve's open percentage using a proportional-integral-derivative feedback loop. Includes bumpless transfer initialization and anti-windup clamping.
4. **PCV (Pump Control Valve)**: Interlocks a pump and its discharge control valve (ramping the valve open over `threshold` seconds when the pump starts and has power; ramping the valve closed over `deadband` seconds when the pump command stops. With `has_power=True` (default), the pump stays at command speed until the valve is closed; with `has_power=False`, physical speed drops to 0 immediately for a power-outage trip).

### Example Configurations

#### 1. Threshold Control (Slam Valve Closed on High Pressure)
```python
rule = rthym_moc.ControlRuleInput()
rule.id = "valve_safety"
rule.type = rthym_moc.ControlType.Threshold
rule.monitored_node = "J1"
rule.controlled_node = "V1"
rule.monitored_quantity = "pressure"
rule.condition = "gt"
rule.threshold = 45.0  # psi
rule.target = 0.0      # slam shut (0% open)

solver.add_control_rule(rule)
```

#### 2. Deadband Control (Pump Fill Cycle on Tank Level)
```python
rule = rthym_moc.ControlRuleInput()
rule.id = "tank_fill"
rule.type = rthym_moc.ControlType.Deadband
rule.monitored_node = "T1"
rule.controlled_node = "Pmp1"
rule.monitored_quantity = "level"
rule.threshold = 40.0  # low limit (40% full)
rule.deadband = 20.0   # range (high limit = 40 + 20 = 60% full)
rule.action = "fill"   # start pump on low limit, stop on high limit

solver.add_control_rule(rule)
```

#### 3. PID Control (Variable Speed Pump Regulating Pressure)
```python
rule = rthym_moc.ControlRuleInput()
rule.id = "pressure_reg"
rule.type = rthym_moc.ControlType.PID
rule.monitored_node = "J2"
rule.controlled_node = "Pmp2"
rule.monitored_quantity = "pressure"
rule.target = 30.0     # target setpoint (30.0 psi)
rule.kp = 2.0
rule.ki = 1.0
rule.kd = 0.1

solver.add_control_rule(rule)
```

#### 4. PCV Sequencing (Pump & Valve Interlock)
```python
rule = rthym_moc.ControlRuleInput()
rule.id = "pump_valve_seq"
rule.type = rthym_moc.ControlType.PCV
rule.monitored_node = "Pmp1"   # pump to monitor
rule.controlled_node = "V1"    # control valve to sequence
rule.threshold = 10.0          # open ramp time (seconds)
rule.deadband = 15.0           # close ramp time (seconds)

solver.add_control_rule(rule)

# Powered shutdown: pump keeps running until the valve finishes closing (default has_power=True).
# Power outage: drop pump speed immediately while the valve still ramps closed on backup power.
solver.set_pump_power("Pmp1", False)
```

### VFD Pump Speed Ramping

When a pump is controlled via an operational control rule (Threshold, Deadband, or PID) or a schedule, the computed target is written to the pump's `command_speed` rather than immediately altering its physical speed. The core solver then ramps `current_speed` toward `command_speed` at every timestep using the pump's VFD `ramp_time` (in seconds):

- If the pump has power (`has_power == True`) and `current_speed` differs from `command_speed`, the maximum speed change per timestep is:

$$\Delta s_{\max} = \frac{100}{t_{\mathrm{ramp}}} \cdot \Delta t$$

where $t_{\mathrm{ramp}}$ is `ramp_time` in seconds and $\Delta t$ is the solver timestep.

- If `ramp_time <= 0.0` (default), the speed changes instantly.
- If `has_power == False` (e.g., power lost), the pump's rotational inertia ($WR^2$) decay calculation takes precedence, and the pump spins down naturally under hydraulic loads.

---

## Surge control components

Three passive devices are available for transient pressure protection.

### AirValve (air-admission / air-release valve)

An `AirValve` behaves like a normal closed vent while the local piezometric head
stays positive and no trapped pocket is present. If a transient pulls the node
toward subatmospheric pressure, the valve admits air through a large orifice,
creating an air pocket. When the system repressurises, that pocket compresses
and is released gradually through a smaller discharge port, which lets the model
capture delayed venting and restart overshoot from trapped air.

This is not a binary atmospheric clamp. The current model tracks:

- a finite admission port using `diameter`
- a finite release port using `air_release_diameter`
- a local air-pocket / chamber volume using `gas_volume` and `tank_volume`
- asymmetric admission and release coefficients using `loss_coeff_in` and `loss_coeff_out`
- an optional vent datum offset using `air_release_head`

That makes the `AirValve` suitable for cases where vacuum protection, trapped-air
compression, and delayed re-venting materially affect the transient response.

```python
av = rthym_moc.NodeInput()
av.id               = "AV1"
av.type             = "AirValve"
av.elevation        = 0.0
av.head             = 160.0   # ft — steady-state pipeline head at the vent node
av.diameter         = 6.0     # inches — large admission port
av.air_release_diameter = 0.25  # inches — small release port
av.gas_volume       = 0.05    # ft³ — initial trapped air pocket (usually small)
av.tank_volume      = 2.0     # ft³ — local valve-body / riser chamber volume
av.loss_coeff_in    = 0.8     # admission discharge coefficient
av.loss_coeff_out   = 0.7     # release discharge coefficient
av.air_release_head = 0.0     # ft vent reference above elevation
solver.add_node(av)
```

The model simulates compressible air dynamics using isentropic nozzle flow equations:

- **Ideal Gas Law**: The air pocket pressure $P_g$ is determined by the ideal gas equation of state:
  $$P_g V_g = M R T_g$$
  where $M$ is the air mass inside the pocket, and the air temperature $T_g$ is assumed constant at atmospheric temperature ($T_{\text{atm}} = 518.67 \text{ °R}$).
- **Compressible Airflow**: Air mass flow rate $\dot{m}$ through the admission or release orifice is determined using standard compressible flow relations (with specific heat ratio $k = 1.4$):
  - If the pressure ratio $p_r = p_{\text{outlet}} / p_{\text{inlet}} \le 0.528$ (critical ratio), the flow is **sonic/choked**:
    $$\dot{m} = C_d A \frac{p_{\text{inlet}}}{\sqrt{T_{\text{inlet}}}} \sqrt{\frac{k}{R} \left(\frac{2}{k+1}\right)^{\frac{k+1}{k-1}}}$$
  - If $p_r > 0.528$, the flow is **subsonic**:
    $$\dot{m} = C_d A \frac{p_{\text{inlet}}}{\sqrt{T_{\text{inlet}}}} \sqrt{\frac{2k}{R(k-1)} \left( p_r^{\frac{2}{k}} - p_r^{\frac{k+1}{k}} \right)}$$
  For air admission (inflow), $p_{\text{inlet}} = P_{\text{atm}}$ and $p_r = P_g / P_{\text{atm}}$. For air release (outflow), $p_{\text{inlet}} = P_g$ and $p_r = P_{\text{atm}} / P_g$.
- **Vessel Limits**: To prevent physically impossible states, the pocket volume is capped at the local chamber/vent body volume (`tank_volume`).

#### Air valves at a pipe chainage (long-line summits)

On long uninterrupted reaches, vacuum breakers are often placed at the survey high
point rather than at an existing network junction.  The helpers in
`rthym_moc.chainage_air_valve` (also exported on the top-level package) split the
pipe topologically at the chosen chainage and insert an `AirValve` node that reuses
the compressible-air model above.  Elevation and piezometric head at the split are
taken from the pipe's `elevation_profile` survey table (or endpoint interpolation
when no survey is present).

Use `PipeNetwork` as a mutable node/pipe registry, attach the valve, then load the
solver:

```python
import rthym_moc as m

net = m.PipeNetwork()

r1 = m.NodeInput()
r1.id = "R1"
r1.type = "PressureBoundary"
r1.elevation = 100.0
r1.head = 400.0
net.add_node(r1)

r2 = m.NodeInput()
r2.id = "R2"
r2.type = "PressureBoundary"
r2.elevation = 120.0
r2.head = 400.0
net.add_node(r2)

pipe = m.PipeInput()
pipe.id = "Pmain"
pipe.from_node = "R1"
pipe.to_node = "R2"
pipe.length = 4000.0
pipe.diameter = 12.0
pipe.roughness = 130.0
pipe.flow_gpm = 800.0
pipe.elevation_profile = [(0.0, 100.0), (2000.0, 320.0), (4000.0, 120.0)]
net.add_pipe(pipe)

# Auto-detect summit from elevation_profile and insert AirValve there:
valve_id, chainage_ft = m.attach_air_valve_at_survey_high_point(
    net, "Pmain", valve_node_id="AV_summit",
)

# Or place at an explicit chainage (ft from from_node):
# valve_id = m.attach_air_valve_at_chainage(net, "Pmain", 1800.0)

solver = m.MOCSolver()
net.apply_to(solver)
results = solver.run(total_time=5.0, dt=0.01)
```

**API summary**

| Function | Purpose |
|---|---|
| `PipeNetwork` | Mutable `nodes` / `pipes` dicts with `apply_to(solver)` |
| `attach_air_valve_at_survey_high_point(net, pipe_id, …)` | Split at survey or endpoint high point; returns `(valve_node_id, chainage_ft)` |
| `attach_air_valve_at_chainage(net, pipe_id, chainage_ft, …)` | Split at an explicit chainage; returns `valve_node_id` |
| `split_pipe_at_chainage(pipe, nodes, chainage_ft, …)` | Low-level split → upstream/downstream `PipeInput` + `AirValve` `NodeInput` |
| `survey_high_point_chainage_ft`, `elevation_at_chainage_ft`, `head_at_chainage_ft` | Placement helpers from survey tables |

Optional `AirValve` fields (`gas_volume`, `tank_volume`, `diameter`,
`air_release_diameter`, `loss_coeff_in`, `loss_coeff_out`, `air_release_head`) can
be passed as keyword arguments to the attach helpers.

When a pipe is split, `elevation_profile` and sparse interior DVCM watchpoints
(`interior_dvcm_chainages_ft`) are rebased onto the upstream and downstream
reaches.  A watchpoint exactly at the split chainage is omitted (the valve node
handles the summit instead).  With `enable_interior_dvcm=True` and
`record_pipe_profiles=True`, interior cavity telemetry is exported on the split
pipe ids (e.g. `Pmain_up`, `Pmain_dn`).

Reference case: `tests/test_dvcm_air_valve.py::test_dvcm_long_line_summit_air_valve_prevents_cavity`
shows a summit air valve eliminating interior DVCM cavity volume at the high point
versus an unprotected run on the same reach.  See also `tests/test_chainage_air_valve.py`
and `docs/long_pipeline_surge_roadmap.md` (Phase 5).

### Standpipe (open surge tank)

An open-topped standpipe connected to the pipeline.  When a pressure wave arrives, water rises or falls inside the standpipe rather than propagating as a waterhammer spike, limiting peak pressures.

```python
st = rthym_moc.NodeInput()
st.id        = "ST1"
st.type      = "Standpipe"
st.elevation = 0.0
st.head      = 100.0         # ft — initial water-surface elevation (ft HGL)
st.tank_area = 5.0           # ft² — cross-sectional area of the standpipe
solver.add_node(st)
```

The water level is updated each time step using the standpipe continuity equation:

$$z^{n+1} = z^n + \frac{Q_\text{in} \, \Delta t}{A_s}$$

where $Q_\text{in}$ is the net inflow from the attached pipe and $A_s$ is `tank_area`.

**Design guidance**: larger `tank_area` produces a smaller maximum water-level swing ($z_\text{max} = V_0 \sqrt{A_p L / (g A_s)}$).  Place the standpipe at or near the pump discharge to protect against pump-trip low-pressure transients.

### HydropneumaticTank (closed pressurised vessel)

A sealed vessel containing a cushion of compressed air above the water column.  As the pipeline pressure fluctuates, water enters or leaves through an orifice and the gas volume changes according to the polytropic law:

$$P_g V_g^n = C \quad (n = 1.0 \text{ isothermal} \cdots 1.4 \text{ adiabatic; default } 1.2)$$

The gas constant $C$ is computed automatically at startup from `head` and `gas_volume`:

$$C = (H_0 - z_\text{elev} + 33.9) \cdot V_{g,0}^n$$

where 33.9 ft corresponds to 1 atm of absolute pressure head.

```python
hpt = rthym_moc.NodeInput()
hpt.id             = "HPT1"
hpt.type           = "HydropneumaticTank"
hpt.elevation      = 0.0
hpt.head           = 120.0    # ft — steady-state pipeline head at connection
hpt.diameter       = 4.0      # inches — connection orifice diameter
hpt.gas_volume     = 10.0     # ft³ — initial trapped gas volume
hpt.tank_volume    = 30.0     # ft³ — total vessel volume (gas + water)
hpt.polytropic_n   = 1.2      # 1.0 = isothermal, 1.4 = adiabatic (default 1.2)
hpt.loss_coeff_in  = 0.7      # C_d for inflow (water entering, gas compresses)
hpt.loss_coeff_out = 0.7      # C_d for outflow (water leaving, gas expands)
solver.add_node(hpt)
```

**Vessel Limits (Option C Clamping)**: To prevent physically impossible states (such as a negative gas volume or a gas pocket exceeding the total vessel size), the solver automatically clamps the net flow to zero when the tank becomes completely flooded ($V_g \le 0$) or completely dry ($V_g \ge V_{tank}$). The connection node head is dynamically calculated based on the clamped flow.

**Design guidance**: pre-charge the vessel so that `gas_volume / tank_volume` ≈ 0.33–0.50 at the steady-state operating pressure.  Separate `loss_coeff_in` and `loss_coeff_out` values allow modelling of a throttle or riser dip tube that damps re-filling surges more aggressively than the initial discharge.

---

## Pump & Turbine Rotational Inertia

For transient cases such as pump power failure (trip) or turbine grid disconnection, the solver models the dynamic change in rotational speed integrated over time based on the polar moment of inertia ($I = WR^2 / g$, where $WR^2$ is the rotational inertia `inertia_wr2`).

### Grid Synchronization States
- **Grid Synchronized (`has_power = True`)**: The node speed is locked at 100% of rated speed (`speed_rpm`). For pumps, this represents normal operation. For turbines, this represents synchronization to the electrical grid under load.
- **Tripped / Disconnected (`has_power = False`)**: The node is disconnected from the electrical source/sink. The runner is free to accelerate or decelerate based on the balance of torque.
  - If `inertia_wr2 <= 0.0`, the speed changes instantly. A tripped pump instantly stops ($s = 0$), while a tripped turbine instantly reaches runaway speed ($N = N_{\text{runaway}}$).
  - If `inertia_wr2 > 0.0`, the speed is integrated step-by-step.

### Pump Deceleration
When power is lost on a pump with inertia, the deceleration rate is governed by the torque-speed dynamics:

$$\Delta s = \frac{-T_h}{I \cdot \omega_0} \cdot \Delta t$$
$$s_{\text{new}} = \text{clamp}(s + \Delta s, 0.0, 1.0)$$

where:
- $s$ is the speed ratio ($N / N_{\text{rated}}$)
- $T_h$ is the hydraulic resistance torque (ft·lb), modeled as:
  $$T_h = T_{\text{rated}} \cdot (0.5 \cdot s^2 + 0.5 \cdot s \cdot q_{\text{ratio}})$$
- $q_{\text{ratio}} = Q_{\text{gpm}} / Q_{\text{design}}$
- $\omega_0 = 2\pi \cdot N_{\text{rated}} / 60$ is the rated angular velocity (rad/s)
- $I = WR^2 / g$ is the moment of inertia (slug·ft²), with $WR^2$ being the rotational inertia `inertia_wr2` (lb·ft²)

### Turbine Startup & Runaway Dynamics
When a turbine is disconnected from the grid under load, it accelerates or decelerates under the action of the hydraulic torque:

$$\Delta N_{\text{rpm}} = \frac{307.486 \cdot T_{\text{hydraulic}}}{WR^2} \cdot \Delta t$$
$$N_{\text{new}} = \max(0.0, N_{\text{current}} + \Delta N_{\text{rpm}})$$

where:
- $T_{\text{hydraulic}}$ is computed using a linear torque-speed simplification based on design head ($H_{\text{design}}$) and wicket gate opening ratio ($G = Y / 100.0$, where $Y$ is the wicket gate opening percentage `current_setting`):
  $$T_{\text{stall}} = 1.5 \cdot T_{\text{rated}} \cdot G \cdot \left(\frac{\Delta H}{H_{\text{design}}}\right)$$
  $$N_{\text{runaway}} = 1.8 \cdot N_{\text{rated}} \cdot \sqrt{\frac{\Delta H}{H_{\text{design}}}}$$
  $$T_{\text{hydraulic}} = T_{\text{stall}} \cdot \left(1.0 - \frac{N_{\text{current}}}{N_{\text{runaway}}}\right)$$
- $T_{\text{rated}}$ is the rated shaft torque at best efficiency point (BEP):

$$T_{\text{rated}} = \frac{5252.0 \cdot \text{BHP}_d}{N_{\text{rated}}}$$

$$\text{BHP}_d = \frac{Q_d \cdot H_d \cdot \eta}{3960.0}$$

with $Q_d$ = `design_flow` (GPM), $H_d$ = `design_head` (ft), and $\eta$ = `efficiency` (BEP fractional efficiency).


## Cavitation models

RTHYM-MOC supports two cavitation modeling strategies to simulate transient vapor pressure boundaries when local pressures drop to the vapor floor ($P_{\text{vap}}$).

### Cavitation Model Options (`rthym_moc.CavitationModel`)

1. **`LegacyClamp` (Default)**:
   - **Mechanism**: A first-order HGL clamping model. When the calculated hydraulic head at a node drops below the vapor head ($H_{\text{vap}} = z_{\text{elev}} + H_{\text{vapor}}$), the solver clamps it exactly to $H_{\text{vap}}$ for that timestep.
   - **Use Case**: Best for mild transient systems where cavitation is transient and minor, or for backward compatibility with previous versions.
   - **Limitation**: Does not track cavity volume or model secondary pressure spikes generated by water columns colliding during cavity collapse.

2. **`DVCM` (Discrete Vapor Cavity Model)**:
   - **Mechanism**: Tracks the physical growth, expansion, and collapse of discrete vapor cavities at nodes. When local pressure hits $P_{\text{vap}}$, a vapor cavity is initiated. The pocket's volume $V_c$ is integrated step-by-step using:
     $$V_c^{n+1} = V_c^n + (Q_{\text{out}} - Q_{\text{in}}) \cdot dt$$
     When $V_c$ collapses back to zero, the solver returns to the liquid-full regime, generating a secondary water-hammer collision pressure spike.
   - **Use Case**: Recommended for pump trip transients, fast valve closures, and systems vulnerable to column-separation and severe water hammer.
   - **Long pipelines**: Junction-only DVCM misses mid-reach summits on sloping transmission mains. Enable **`enable_interior_dvcm=True`** with `elevation_profile` surveys and `record_pipe_profiles=True` to track cavities along the line — see [Long-pipeline surge & interior DVCM](#long-pipeline-surge--interior-dvcm).
   - **Guidance**: Requires choosing a smaller timestep (typically $dt \le 0.001\text{ s}$ or $0.0001\text{ s}$) to prevent numerical volume integration overshoot. See [docs/dvcm_timestep_guidance.md](docs/dvcm_timestep_guidance.md).
   - **Showcase**: Run the showcase notebook interactively on Binder to see DVCM in action: [![Launch Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/jlillywh/RTHYM-MOC/main?labpath=examples%2Fdvcm_showcase.ipynb)

### Configuring the Cavitation Model

#### 1. Via Solver State Setup
You can set a persistent default model for the solver instance:
```python
import rthym_moc as m

solver = m.MOCSolver()
# Set to DVCM
solver.set_cavitation_model(m.CavitationModel.DVCM)

# Retrieve current configuration
current_model = solver.get_cavitation_model() # -> CavitationModel.DVCM
```

#### 2. Via `run()` or `run_si()` Arguments
You can override the cavitation model directly on a per-simulation basis:
```python
# US customary run
results = solver.run(
    total_time=12.0,
    dt=0.0001,
    p_vapor_psi=-14.0,
    cavitation_model=m.CavitationModel.DVCM
)

# SI convenience run
results_si = m.run_si(
    solver,
    total_time=12.0,
    dt=0.0001,
    p_vapor_kpa=-96.5,
    cavitation_model=m.CavitationModel.DVCM
)
```

### Cavitation-Specific Results
When `DVCM` is selected, the solver automatically records additional diagnostic fields in the results dictionary:

| Results Dict Key | SI Results Dict Key | Type | Description |
|---|---|---|---|
| `"node_cavity_volume"` | `"node_cavity_volume_m3"` | `dict[str] → ndarray` | Integrated volume of the vapor pocket (ft³ or m³). |
| `"node_cavity_active"` | `"node_cavity_active"` | `dict[str] → ndarray` | Binary flag (0/1) indicating if a vapor cavity is active at this step. |
| `"node_cavity_collapse_flag"` | `"node_cavity_collapse_flag"` | `dict[str] → ndarray` | Binary flag (0/1) indicating if a cavity collapsed on this specific step. |
| `"node_cavity_collapse_count"` | `"node_cavity_collapse_count"` | `dict[str] → ndarray` | Cumulative count of cavity collapses at each node. |

When **`enable_interior_dvcm=True`** and **`record_pipe_profiles=True`**, interior grid telemetry is exported per pipe:

| Results Dict Key | SI Results Dict Key | Type | Description |
|---|---|---|---|
| `"pipe_profile_cavity_volume"` | `"pipe_profile_cavity_volume_m3"` | `dict[str] → ndarray (N, M)` | Integrated cavity volume along chainage, ft³ or m³. |
| `"pipe_profile_cavity_active"` | `"pipe_profile_cavity_active"` | `dict[str] → ndarray (N, M)` | Binary flag (0/1) for active interior cavity at each profile station. |

See [Optional per-pipe MOC profiles](#optional-per-pipe-moc-profiles) for the full profile key list.

---

## Scripted multi-event transients

`run()` resets the MOC grid to the steady-state initial conditions each call, so multi-event sequences are best handled with schedules covering the full duration, or by rebuilding `NodeInput` objects between calls:

```python
# Example: valve closes at t=1 s while a downstream demand increases at t=2 s
import numpy as np

# Build schedules covering the full 5-second window
t_close  = np.array([0.0, 1.0, 1.01, 5.0])
s_close  = np.array([100.0, 100.0, 0.0, 0.0])
solver.set_valve_schedule("V1", list(zip(t_close, s_close)))

demand_times = np.array([0.0, 2.0, 2.01, 5.0])
demand_vals  = np.array([500.0, 500.0, 700.0, 700.0])
solver.set_demand_schedule("J1", list(zip(demand_times, demand_vals)))

results = solver.run(total_time=5.0, dt=0.01)
```

To step a pump, boundary head, or demand between separate `run()` calls, use `set_pump_speed()`, `set_node_head()`, `set_node_demand()`, or direct `NodeInput.head` changes before the next `run()`. Each new `run()` call re-initialises from the stored steady-state values rather than the final state of the previous transient.

---

## Loading from EPANET (.inp)

Existing EPANET network files can be imported directly with `rthym_moc.load_inp()`.  The function parses the network topology and — when [wntr](https://wntr.readthedocs.io) is installed — runs a single-period hydraulic simulation to populate steady-state pipe flows automatically.

### Install the optional dependency

```bash
pip install wntr          # standalone
# or
pip install 'rthym-moc[inp]'   # together with rthym-moc
```

### Usage

```python
import rthym_moc

# Load topology and steady-state flows from an EPANET file
solver = rthym_moc.load_inp("network.inp")

# Apply a transient event (valve closure, pump trip, etc.) then run
solver.set_valve_schedule("_VALVE_V1", schedule)
results = solver.run(total_time=10.0, dt=0.01)
```

If wntr is not installed, or for a known operating condition, supply initial flows explicitly:

```python
solver = rthym_moc.load_inp(
    "network.inp",
    use_wntr=False,
    initial_flows={"P1": 500.0, "P2": 250.0},   # GPM, + = from_node → to_node
)
```

For SI override kwargs, use `load_inp_si()` with `initial_flows_m3s`, `initial_heads_m`, and `stub_length_m` — see [Unit conventions](#unit-conventions).

### `load_inp()` parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | `str` | — | Path to the EPANET `.inp` file |
| `use_wntr` | `bool` | `True` | Run wntr hydraulics for initial flows and junction heads |
| `initial_flows` | `dict[str, float]` | `None` | Explicit `{link_id: GPM}` overrides (applied after wntr, if any) |
| `initial_heads` | `dict[str, float]` | `None` | Explicit `{node_id: head_ft}` overrides for junction and inline element heads |
| `stub_length_ft` | `float` | `40.0` | Length (ft) of fictitious stub pipes on each side of pumps and valves; must satisfy the Courant grid constraint |

### `load_inp_si()` parameters

Same as `load_inp()`, except override kwargs use SI units:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `initial_flows_m3s` | `dict[str, float]` | `None` | Explicit `{link_id: m³/s}` overrides |
| `initial_heads_m` | `dict[str, float]` | `None` | Explicit `{node_id: head_m}` overrides |
| `stub_length_m` | `float` | `None` | Stub pipe length in metres (default 40 ft when omitted) |

For `initial_flows`, use the original EPANET link ID for pumps and valves (e.g. `"V1"`), not the generated stub pipe IDs. For `initial_heads`, use EPANET junction IDs and generated `_VALVE_<id>` / `_PUMP_<id>` IDs for inline elements.

### Supported EPANET sections

| Section | Mapped to |
|---|---|
| `[JUNCTIONS]` | `Junction` nodes |
| `[RESERVOIRS]` | `PressureBoundary` nodes |
| `[TANKS]` | `Tank` nodes |
| `[PIPES]` | `PipeInput` (H-W, D-W, and C-M roughness converted to H-W C; `CV` pipes become generated `CheckValve` nodes plus split pipes) |
| `[PUMPS]` | `Pump` node + two stub pipes; design point read from `[CURVES]` |
| `[VALVES]` | `Valve` node + two stub pipes (TCV, PRV, PSV, PBV) |
| `[PATTERNS]` | Demand multipliers (see limitations) |
| `[DEMANDS]` | Junction demand with patten multiplier at index 0 |
| `[CONTROLS]` | Simple `LINK … STATUS OPEN\|CLOSED AT TIME …` rows → pump/valve schedules |
| `[TIMES]` | Patten timestep (hours → seconds) |
| `[CURVES]` | Pump design points |
| `[OPTIONS]` | `Units`, `Headloss` formula |
| `[RTHYM]` | Surge-device overrides (`Standpipe`, `HydropneumaticTank`, `AirValve`, `CheckValve`); optional `PipeID PipeElevation chainage=elevation …` survey rows; units follow `[OPTIONS] Units` |

All US customary unit variants (GPM, CFS, MGD, IMGD, AFD) and SI metric variants (LPS, LPM, MLD, CMH, CMD) are supported.

The custom ``[RTHYM]`` section uses the same ``Units`` setting: with ``UNITS LPS`` (or other SI variants), write standpipe areas in m², vessel volumes in m³, diameters in mm, vent offsets in m, and pipe-survey chainage/elevation in m.  With ``UNITS GPM`` (or other US variants), use ft², ft³, inches, ft, and ft for surveys.  Example pipe survey row::

    P_LONG   PipeElevation   0=120   26400=340   52800=95

No separate flag is required.

### Pump, valve, and check-valve generated IDs

Because EPANET treats pumps and valves as *links* (not nodes), `load_inp()` injects an intermediate node and two stub pipes (default 40 ft each; override with `stub_length_ft`) for each one.  The generated IDs follow a predictable patten:

| EPANET link `V1` | Generated node | Generated pipes |
|---|---|---|
| Pump | `_PUMP_V1` | `_P_V1_up`, `_P_V1_dn` |
| Valve | `_VALVE_V1` | `_P_V1_up`, `_P_V1_dn` |
| CV pipe | `_CHECKVALVE_V1` | `_CV_V1_up`, `_CV_V1_dn` |

Use these IDs when calling `set_valve_schedule()`, `set_pump_speed()`, or accessing results.

### Limitations

- **PRV / PSV / PBV** are modeled as active pressure-control valves during transients (`NodeInput.head` stores the setpoint in ft HGL, or differential ft for PBV). Imported EPANET settings are converted from pressure units to head. This is a simplified regulating model, not a full EPANET steady-state valve solve each step.
- **FCV / GPV** valve types are not supported and are treated as fully-open valves.
- **Minor losses** (`[PIPES]` column 7) are imported as a dimensionless local-loss coefficient `K`, included in the initial steady headloss, and then applied as distributed resistance across the pipe during the transient. This is an approximation of a truly lumped fitting loss, but dedicated regression benchmarks are included to quantify the mismatch.
- **Demand pattens** — `[PATTERNS]` with `[JUNCTIONS]` / `[DEMANDS]` apply multiplier at index 0 to initial demand; multi-point pattens become `set_demand_schedule()`. Patten timestep comes from `[TIMES]` (hours → seconds). See [`docs/import_fidelity.md`](docs/import_fidelity.md).
- **Simple controls** — `[CONTROLS]` rows of the form `LINK <id> STATUS OPEN|CLOSED AT TIME <hours>` map to pump/valve schedules on `_PUMP_<id>` / `_VALVE_<id>`. `[RULES]` and NODE-based controls are not imported.
- **Check valves** (`CV` status on a pipe) are imported as generated inline `CheckValve` nodes with split pipes. The model supports exponential slam dynamics via `closure_time` (default 0.03 s) and optional `flipped` orientation.

See `examples/load_from_inp.py` for a complete worked example. Import fidelity details and roadmap status: [`docs/import_fidelity.md`](docs/import_fidelity.md).

---

## Numerical method

The solver implements the **fixed-grid, elastic Method of Characteristics** (Wylie & Streeter 1993; Chaudhry 2014).

**Grid setup.**  For each pipe of length $L$, the number of spatial segments is

$$N = \text{round}\!\left(\frac{L}{a \cdot \Delta t}\right)$$

and the wave speed is adjusted to $a_\text{adj} = L / (N \cdot \Delta t)$ to enforce Courant number $= 1$ exactly.

**Interior nodes.**  At each interior node $j$ the $C^+$ and $C^-$ characteristics give:

$$C^+ = H_{j-1}^n + B\,V_{j-1}^n - R\,V_{j-1}^n |V_{j-1}^n|$$
$$C^- = H_{j+1}^n - B\,V_{j+1}^n + R\,V_{j+1}^n |V_{j+1}^n|$$
$$H_j^{n+1} = \tfrac{1}{2}(C^+ + C^-), \qquad V_j^{n+1} = \frac{C^+ - C^-}{2B}$$

where $B = a/g$ (ft·s²/ft = s²) is the pipe impedance and $R = f \Delta x / (2g D)$ is the friction term (Darcy-Weisbach $f$ derived from Hazen-Williams $C$ via the Swamee-Jain approximation).

**Boundary nodes.**  Each node type implements its own BC:

- *PressureBoundary / Tank*: $H$ fixed; $V$ solved from the appropriate $C^\pm$.
- *Junction*: Kirchhoff continuity; $H$ solved from the combined $C^\pm$ of all incident pipes.
- *Dead-end (Junction, demand = 0, no outflow pipe)*: $H = C^+$ (zero-flow reflection).
- *Valve / Turbine*: $K = (100/s)^2 - 1$ loss; combined with $C^\pm$ to solve $H$ and $V$. For turbines, when `has_power = False`, speed is integrated dynamically using its rotational inertia.
- *CheckValve*: one-way flow with optional exponential disc closure; position and velocity are recorded in results.
- *PRV / PSV / PBV*: simplified regulating pressure-control valves using the setpoint stored in `NodeInput.head`.
- *Pump*: affinity-curve head-flow relationship combined with $C^\pm$; `has_power` and `inertia_wr2` determine the speed decay behavior following power failure.
- *AirValve*: finite admission/release orifices with trapped-air compression and delayed venting.
- *Standpipe*: $H$ updated from the standpipe continuity equation each step.
- *HydropneumaticTank*: $H$ updated from the polytropic gas law combined with the orifice flow equation each step.

### Transient friction

The solver exposes four friction modes through `rthym_moc.TransientFrictionModel`.
**Default is `BrunoneIIR`**, which preserves pre–Phase 6 behavior (IIR-filtered
Brunone / Vardy–Brown unsteady friction with fixed Darcy $f$ from the initial
Hazen–Williams steady state).

```python
import rthym_moc

solver = rthym_moc.MOCSolver()

# Persist across runs:
solver.set_friction_model(rthym_moc.TransientFrictionModel.Vitkovsky)

# Or override for one run only:
results = solver.run(
    total_time=60.0,
    dt=0.001,
    friction_model=rthym_moc.TransientFrictionModel.QuasiSteady,
)
```

| Mode | Steady resistance $R$ | Unsteady term (USF) | Typical use |
|------|----------------------|---------------------|-------------|
| **`BrunoneIIR`** (default) | Fixed $f$ from initial $Q$ | IIR residual $(V - \bar V)$; `usf_tau` sets filter time constant | General transients; backward-compatible default |
| **`Steady`** | Fixed $f$ | None | Baseline without USF; equivalent to `k_bru = 0` for damping |
| **`QuasiSteady`** | Variable $f(V)$ recomputed from Hazen–Williams at each characteristic foot | None | Long lines where local velocity changes friction but USF is omitted |
| **`Vitkovsky`** | Fixed $f$ | Bergant acceleration: temporal $(V - V^{n-1})$ minus convective $a\,\mathrm{sign}(V)\,|\partial V/\partial x|\,\Delta t$ | Stronger multi-period envelope decay on long pipelines |

**Mode selection guidance.**

- Leave the default **`BrunoneIIR`** unless you are studying friction-model
  sensitivity or need long-line envelope decay (Phase 6 / LP-07).
- Use **`Steady`** for a fixed-$f$ reference with no unsteady correction.
- Use **`QuasiSteady`** when friction should track instantaneous local velocity
  (variable Darcy $f$) but you do not want an explicit USF term — common in
  screening studies on multi-mile pipes.
- Use **`Vitkovsky`** when late-time oscillation peaks should dissipate faster
  than quasi-steady on long transmission mains; validated directionally in
  `tests/test_transient_friction_model.py` (`@pytest.mark.slow`).

Legacy knobs **`k_bru`** and **`usf_tau`** remain available: `k_bru` scales the
USF coefficient for `BrunoneIIR` and `Vitkovsky`; `usf_tau` controls the IIR
low-pass filter on velocity for **`BrunoneIIR` only**.  Setting `usf_tau = dt`
disables the IIR filter but does not select quasi-steady friction — use
`TransientFrictionModel.QuasiSteady` for variable-$f$ without USF.

Formulation details and equations: [`docs/appendix_hydraulic_reference.md`](docs/appendix_hydraulic_reference.md) §6.4–6.6.
Long-pipeline context: [`docs/long_pipeline_surge_roadmap.md`](docs/long_pipeline_surge_roadmap.md) Phase 6.
Literature cross-checks: [`docs/transient_friction_verification.md`](docs/transient_friction_verification.md).

---

## Benchmarking

Benchmarking answers: **how much faster is the C++ core than TSNet and PTSNet?**
TSNet is the pure-Python MOC reference this project was built to outperform, and
PTSNet is the MPI-capable parallel reference.

Reproduce timing on your hardware:

```bash
pip install tsnet==0.3.1
pip install ptsnet==0.1.10 mpi4py h5py tqdm numba "numpy<2" "setuptools<81"
python examples/benchmark_vs_tsnet.py      # single standard case
python examples/benchmark_matrix.py        # grid-size performance matrix
mpiexec -n 4 python examples/benchmark_ptsnet_vs_tsnet.py --warmup 0 --repeat 1
# Optional rthym_moc throughput check:
mpiexec -n 4 python examples/benchmark_ptsnet_vs_tsnet.py --warmup 0 --repeat 1 --rthym-concurrency 4
```

Install `ptsnet==0.1.10`, `mpi4py`, `h5py`, `tqdm`, `numba`, `numpy<2`, and
`setuptools<81` before running `benchmark_ptsnet_vs_tsnet.py`.

`benchmark_vs_tsnet.py` reports wall-clock time on the same 300-step instant-closure
case for RTHYM-MOC vs TSNet, plus an RMS physics cross-check. Typical developer
hardware: **under 1 ms** for RTHYM-MOC vs **about 50–70 ms** for TSNet (order of
**200–400×** faster). Re-run before citing ratios.

`benchmark_ptsnet_vs_tsnet.py` adds PTSNet and prints **one table**: median ms for
each tool to **complete** a full run from a fresh model. The default is PTSNet's
TNET3 valve-closure network because it completes reliably under `mpiexec -n 4`;
the Joukowsky and standpipe microbenchmarks remain available with `--models 1,2`
or `--models all`. Add `--rthym-concurrency 4` to show batch throughput for four
independent rthym_moc runs in separate Python processes. See
[docs/benchmarking.md](docs/benchmarking.md).

| Topic | Documentation |
|---|---|
| How to run / interpret RTHYM vs TSNet | [docs/benchmarking.md](docs/benchmarking.md), `examples/benchmark_matrix.py` |
| Timestep selection for DVCM mode | [docs/dvcm_timestep_guidance.md](docs/dvcm_timestep_guidance.md) |
| Cavitation model comparison | [docs/dvcm_comparison.md](docs/dvcm_comparison.md) |
| Migration notes for upgrading users | [docs/dvcm_migration.md](docs/dvcm_migration.md) |
| R-THYM long-pipeline rollout (profiles, interior DVCM) | [docs/long_pipeline_rthym_migration.md](docs/long_pipeline_rthym_migration.md) |
| R-THYM API reference (telemetry, JSON keys) | [docs/dvcm_web_integration.md](docs/dvcm_web_integration.md) |
| DVCM defect and issue tracker | [docs/dvcm_defect_tracker.md](docs/dvcm_defect_tracker.md) |
| All three tools (time to complete the full run) | `examples/benchmark_ptsnet_vs_tsnet.py` |
| Tabulated physics + timing results | [docs/appendix_b_verification.md](docs/appendix_b_verification.md) §B.6 |
| Automated correctness regressions | [Validation](#validation) — `tests/` (TSNet is not a default pytest dependency) |

---

## Versioning

The project tracks its package version from a single source of truth in
`rthym_moc/_version.py`. The Python API exposes that value as
`rthym_moc.__version__`, and both the Python packaging metadata and CMake
project version read from the same source.

Release-level changes are tracked in [CHANGELOG.md](CHANGELOG.md).

---

## Repository layout

CI runs three isolated jobs: **native C++ core** (`test-core-cpp`), **Python wheel + pytest**, and **WASM regression** (`wasm-regression.yml`). Local solver work: [Developing the C++ core](#developing-the-c-core). Maintainer WASM build: [§ Maintainer WASM integration](#maintainer-wasm-integration-internal).

```
RTHYM-MOC/
├── CMakeLists.txt         # Builds rthym_core; enters bindings/python or bindings/wasm
├── build_wasm.sh          # Delegates to bindings/wasm/build_wasm.sh
├── src/
│   └── solver/
│       ├── types.hpp      # Plain C++ step telemetry snapshots (StepSnapshot)
│       ├── moc_solver.hpp # Type definitions, NodeInput, PipeInput, MOCSolver declaration
│       └── moc_solver.cpp # Full MOC physics implementation (pure C++17)
├── bindings/
│   ├── python/
│   │   ├── CMakeLists.txt
│   │   └── bindings.cpp   # PyBind11 bindings → _rthym_moc extension module
│   └── wasm/
│       ├── CMakeLists.txt
│       ├── build_wasm.sh  # emcmake driver (maintainer/internal)
│       ├── wasm_bindings.cpp
│       └── tests/         # WASM runtime pytest (not in default Python CI)
├── build/
│   └── wasm/              # Generated rthym_moc.js / rthym_moc.wasm (not committed)
├── rthym_moc/
│   ├── __init__.py        # Public API re-exports
│   ├── _version.py        # Single source of truth for project version
│   ├── epanet.py          # load_inp() EPANET importer
│   ├── report.py          # Study summaries and CSV/JSON export
│   └── _rthym_moc*.so     # Compiled extension (generated by build)
├── validation/
│   ├── README.md
│   ├── datasets/
│   │   └── bergant_adelaide/   # Adelaide column-separation lab references (JSON/CSV)
│   └── notebooks/
│       ├── validation_notebooks_index.ipynb  # Preferred Binder entry
│       ├── grid_scaling_verification.ipynb
│       └── bergant_adelaide_verification.ipynb
├── examples/
│   ├── …                           # Demo scripts (see README § Examples)
│   ├── *_verification*.ipynb       # Legacy Binder mirrors (see validation/notebooks/)
│   ├── quickstart_notebook.ipynb   # R-THYM cross-engine walkthrough (Validation)
│   └── validation_notebooks_index.ipynb
├── tests/
│   ├── test_joukowsky_rthym.py                 # R-THYM web-app vs solver benchmark
│   ├── test_long_pipe_valve.py                 # Cross-engine valve-closure benchmark
│   ├── test_complex_topology_from_inp.py       # EPANET/wntr import benchmark
│   ├── test_inp_import_fidelity.py             # Pattens, demands, simple controls
│   ├── test_report.py                          # Study summary and export helpers
│   ├── test_gradual_closure_benchmark.py       # Parameterized closure-time benchmark
│   ├── test_tank_size_benchmark.py             # Parameterized standpipe-size benchmark
│   ├── test_hydropneumatic_size_benchmark.py   # Fixed-ratio vessel-size benchmark
│   ├── test_device_placement_benchmark.py      # Hydropneumatic placement benchmark
│   ├── test_pipe_length_benchmark.py           # Protected pipe-length benchmark
│   ├── test_multi_device_placement_benchmark.py # Split-vessel placement benchmark
│   ├── test_mixed_device_interaction_benchmark.py # Surge-vessel + air-valve benchmark
│   ├── test_air_valve_dominant_mixed_layout_benchmark.py # Air-valve-dominant mixed layout
│   ├── test_air_valve_dominant_layout_sensitivity_benchmark.py # Air-dominant distance sweep
│   ├── test_air_valve_dominant_size_sweep_benchmark.py # Air-dominant size sweep
│   ├── test_column_separation_and_stability.py # Cavitation and long-run stability
│   ├── networks/                               # Benchmark INP fixtures
│   ├── cpp/
│   │   ├── CMakeLists.txt
│   │   └── test_core.cpp                       # Native C++ core tests (BUILD_TESTS=ON)
├── docs/
│   ├── dvcm_timestep_guidance.md   # Recommended timestep selection guidelines for DVCM mode
│   ├── dvcm_comparison.md          # Cavitation model comparison guide (Legacy vs DVCM)
│   ├── dvcm_migration.md           # Migration notes for upgrading users
│   ├── long_pipeline_rthym_migration.md  # R-THYM rollout for profiles & interior DVCM
│   ├── long_pipeline_surge_roadmap.md  # Phase scope and validation cases LP-01–LP-08
│   ├── long_pipeline_phase0_baseline.md  # Pre-change baseline and LP-PERF-01 budget
│   ├── dvcm_web_integration.md     # R-THYM telemetry and batch profile API reference
│   ├── dvcm_defect_tracker.md      # DVCM defect and issue tracker log
│   ├── appendix_b_verification.md  # Long-form cross-engine verification appendix
│   ├── validation.md               # Pytest map, tolerances, reference assets
│   ├── validation_notebooks.md     # Binder notebook index (mirrors tests/)
│   ├── validation_notebook_coverage.md  # Pytest ↔ notebook matrix
│   ├── benchmarking.md             # TSNet performance comparison guide
│   ├── import_fidelity.md          # EPANET import scope and limitations
│   └── appendix_hydraulic_reference.md
├── CMakeLists.txt
└── pyproject.toml
```

---

## Dependencies

**Runtime**

| Package | Minimum | Purpose |
|---------|---------|---------|
| Python  | 3.9     | |
| NumPy   | 1.21    | Result arrays |

**Build only**

| Package | Minimum | Purpose |
|---------|---------|---------|
| pybind11 | 2.11   | C++/Python bridge |
| CMake   | 3.15    | Build system |
| C++17 compiler | GCC 9 / Clang 10 / MSVC 2019 | |

**Optional (examples only)**

| Package | Purpose |
|---------|---------|
| matplotlib | Plotting in `basic_example.py` |
| TSNet 0.3.1 | Cross-validation in example benchmark scripts |
| wntr ≥ 0.4 | Steady-state initial flows for `load_inp()` (`pip install 'rthym-moc[inp]'`) |

---

## References

- Chaudhry, M. H. (2014). *Applied Hydraulic Transients*, 3rd ed. Springer.
- Wylie, E. B., & Streeter, V. L. (1993). *Fluid Transients in Systems*. Prentice Hall.
- Joukowsky, N. (1898). Über den hydraulischen Stoss in Wasserleitungsröhren. *Mémoires de l'Académie Impériale des Sciences de St.-Pétersbourg*, 9(5).

---

## License

**RTHYM-MOC** (this repository) is released under the [MIT License](https://opensource.org/licenses/MIT) and is free to use, modify, and distribute for any purpose, including commercial and academic work.  See `pyproject.toml` for the full license text.

**R-THYM** (the web application at [r-thym.com](https://www.r-thym.com)) is a separate, proprietary product and is not covered by this license.  The R-THYM application, its user interface, and its hosted infrastructure remain the intellectual property of Lillywhite Water Solutions LLC and are not open source.
