# DVCM Phase 0 Baseline Metrics

Date: 2026-06-01
Branch: `chore/dvcm-phase0-baseline`
Purpose: Baseline capture before any DVCM physics changes.

## Environment

- Workspace: `RTHYM-MOC`
- Python environment: `.venv`
- Platform: Linux (per active workspace context)

## Commands Run

```bash
pytest -q --maxfail=1 --durations=20
pytest -q -s tests/test_joukowsky_rthym.py tests/test_long_pipe_valve.py
```

## Baseline Summary

### Full suite runtime and failures

- Result: `288 passed, 2 deselected in 4.05s`
- Failures: `0`
- Notes: slowest individual tests were all <= 0.05s (see command output).

### Key pressure-trace baseline metrics

#### Joukowsky cross-engine benchmark (`tests/test_joukowsky_rthym.py`)

- Wave speed error: `0.0000 ft/s` (tol `5.0`)
- Steady-state flow error (Pipe_1): `0.045 GPM` (tol `2.0`)
- Steady-state head error (Valve_A): `0.021 ft` (tol `0.5`)
- First-step pressure error: `0.9619 psi` (tol `2.0`)
- Minimum pressure error (Valve_A): `0.000 psi` (tol `1.0`)
- Maximum pressure error (Valve_A): `4.342 psi` (tol `15.0`)
- Pressure trace RMS (Valve_A, 5.96-7.44 s): `3.4703 psi` (tol `4.0`)

#### Long-pipe valve cross-engine benchmark (`tests/test_long_pipe_valve.py`)

- Wave speed error: `0.000 ft/s` (tol `5.0`)
- Pressure peak max error:
  - Junction_A: `0.139 psi` (tol `1.5`)
  - Junction_B: `0.230 psi` (tol `1.5`)
  - Junction_C: `0.055 psi` (tol `1.5`)
  - Valve_B: `0.264 psi` (tol `1.5`)
- Pressure peak min error:
  - Junction_A: `0.113 psi` (tol `1.5`)
  - Junction_B: `0.211 psi` (tol `1.5`)
  - Junction_C: `0.105 psi` (tol `1.5`)
  - Valve_B: `0.262 psi` (tol `1.5`)
- Time-series RMS:
  - Valve_B pressure: `0.531 psi` (tol `2.0`)
  - Junction_B pressure: `0.415 psi` (tol `2.0`)
  - Junction_C pressure: `0.327 psi` (tol `2.0`)
  - Pipe_3 flow: `0.151 GPM` (tol `10.0`)

## Acceptance snapshot

- Baseline status: PASS
- Existing cavitation model behavior remains stable against current reference tests.
- This document should be used as the comparison point for all upcoming DVCM PRs.
