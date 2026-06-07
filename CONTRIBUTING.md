# Contributing to RTHYM-MOC

This project accepts improvements to the solver core, Python bindings, tests,
documentation, and benchmark coverage. Keep changes narrow, validated, and
consistent with the existing hydraulic modeling scope.

Community contributions are welcome. Small fixes, new regression cases,
documentation clarifications, and benchmark extensions are all useful so long
as they stay explicit about scope, validation, and numerical expectations.

Project maintenance cadence is documented in `MAINTENANCE.md`, including the
monthly review pass, pre-release checks, and the conditions that should trigger
a focused refactor instead of another local patch.

## Security

Report security issues privately — see [`SECURITY.md`](SECURITY.md). Do not
open public issues for vulnerabilities.

## Development Setup

Use Python 3.9+ inside a virtual environment (recommended on Ubuntu/WSL to
avoid PEP 668 “externally-managed-environment” errors from system Python):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip wheel 'setuptools>=65,<81'
pip install -e '.[dev,inp]'
```

Run commands from a **WSL/Linux shell** at the repo root (`~/RTHYM-MOC`).
If you use PowerShell on Windows, prefix with `wsl bash -lc '...'` or open a
WSL terminal instead of mixing path styles.

The optional `inp` extra installs `wntr`, which is used by INP-based tests and
steady-state initialization paths.

## Build Notes

If you change the C++ core under `src/solver/`, rebuild the extension before running
tests:

```bash
pip install -e .
```

The native C++ core tests can be built without Python or Emscripten:

```bash
cmake -B build -DCMAKE_BUILD_TYPE=Debug -DBUILD_TESTS=ON -DRTHYM_BUILD_PYTHON=OFF
cmake --build build --target rthym_core_tests -j
cd build && ctest --output-on-failure
```

The maintainer/internal WASM integration build uses Emscripten via `emcmake`:

```bash
bash build_wasm.sh
pytest -q bindings/wasm/tests --override-ini='addopts='
```

Use `bash build_wasm.sh` (not `./build_wasm.sh`) on WSL/Windows checkouts if
you see `Permission denied`; CI Linux runners preserve the executable bit.

See the README **Maintainer WASM integration (internal)** section for scope.

## Local verification (matches CI)

With the venv activated from the repo root:

```bash
cmake -B build -DCMAKE_BUILD_TYPE=Debug -DBUILD_TESTS=ON -DRTHYM_BUILD_PYTHON=OFF
cmake --build build --target rthym_core_tests -j
cd build && ctest --output-on-failure
pytest -q --cov=rthym_moc --cov-fail-under=100
bash build_wasm.sh
pytest -q bindings/wasm/tests --override-ini='addopts='
pytest -q --override-ini='addopts=' --cov=rthym_moc --cov-fail-under=100
```

The first block is native core CI (`test-core-cpp`). The next line is default Python CI parity
(477 tests, 100% `rthym_moc` coverage). WASM build + `bindings/wasm/tests` is the WASM CI job.
The final line adds slow Python tests (~485 total; one optional TSNet case may skip).

## Test and Quality Checks

Run the main Python test suite from the repository root:

```bash
pytest -q
```

Run the package lint and type checks that match CI:

```bash
ruff check rthym_moc
mypy rthym_moc
```

Run the configured pre-commit hooks before opening a pull request:

```bash
pre-commit run --all-files
```

## Contribution Expectations

- Add or update automated tests for behavioral changes.
- Prefer fixing the root cause instead of layering on narrow patches.
- Keep public API and solver-scope changes explicit in docs.
- Do not add new mandatory runtime dependencies without a clear need.
- Treat TSNet as an optional performance-benchmark dependency, not a default
  pytest dependency. Correctness regressions live under `tests/`; see
  `docs/validation.md` and `docs/benchmarking.md`.

## Pull Requests

When opening a pull request, include:

- a short description of the problem and the approach taken
- the commands you ran for validation
- any benchmark, tolerance, or scope changes that reviewers should notice

If a change affects numerical behavior, update the relevant validation
documentation under `docs/validation.md` (and `docs/benchmarking.md` if timing
methodology changes) and keep assertion tolerances explicit.

## Reporting Issues

When filing a bug, include:

- a minimal reproducible example or input network
- the expected behavior and actual behavior
- the commands used to run the case
- the Python version and platform

This helps separate solver defects from setup or input-data problems quickly.

Feature requests and benchmark ideas are also welcome when they explain the
hydraulic scenario, why it matters, and what acceptance criteria would make the
behavior reviewable.