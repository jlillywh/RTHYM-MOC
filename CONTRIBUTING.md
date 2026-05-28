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

## Development Setup

Use Python 3.9+ and install the package in editable mode with development
dependencies:

```bash
pip install -e '.[dev,inp]'
```

The optional `inp` extra installs `wntr`, which is used by INP-based tests and
steady-state initialization paths.

## Build Notes

If you change the C++ core under `src/`, rebuild the extension before running
tests:

```bash
pip install -e .
```

The standalone C++ test binary can be built with:

```bash
cmake -B build -DBUILD_TESTS=ON
cmake --build build
./build/moc_test
```

The experimental browser/node WASM build uses Emscripten:

```bash
./build_wasm.sh
RTHYM_ENABLE_WASM_RUNTIME_TESTS=1 pytest -q tests/test_wasm_check_valve.py
```

See the README **Experimental WASM build** section for scope and limitations.

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