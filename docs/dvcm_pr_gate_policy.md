# DVCM PR Gate Policy

Date: 2026-06-01
Scope: Pull requests that implement or modify DVCM-related behavior.

## Required gate conditions

A DVCM PR is merge-ready only when all of the following are true:

- CI is green for the PR.
- The targeted DVCM benchmark gate check passes.

## Required checks

Configure branch protection so the following status checks are required for `main`:

- `pytest`
- `coverage`
- `lint-and-types`
- `dvcm-targeted-benchmark`

## Targeted benchmark gate definition

The targeted DVCM gate is implemented in `.github/workflows/tests.yml` as the
`dvcm-targeted-benchmark` job. It runs the two cross-engine pressure-trace
regressions that anchor cavitation behavior and wave timing:

```bash
pytest -q tests/test_joukowsky_rthym.py tests/test_long_pipe_valve.py
```

## PR author checklist (DVCM work)

- Include links to relevant roadmap phase issue(s) under Epic #52.
- Confirm all required checks above are green before requesting merge.
- If cavitation behavior changes intentionally, update baseline/validation
  artifacts and document rationale in the PR description.
