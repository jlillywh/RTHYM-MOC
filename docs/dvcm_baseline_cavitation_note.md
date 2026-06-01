# Baseline Cavitation Design Note (Pre-DVCM)

Date: 2026-06-01
Branch context: `chore/dvcm-phase0-baseline`
Purpose: Document the current cavitation behavior before introducing DVCM logic.

## Current model summary

RTHYM-MOC currently uses a first-order cavitation limiter at interior
junction-like nodes:

- Solve node head from Kirchhoff continuity and characteristic contributions.
- If computed node head is below vapor head, clamp it to vapor head.
- Continue MOC update using that clamped head.

In implementation terms, this is a vapor-pressure floor on head, not a
discrete cavity-volume model.

## Code locations

- Clamp logic and model note: `src/moc_solver.cpp` (junction branch in `stepMOC()`)
- Telemetry recording (`node_cavitation` as 0/1 flag): `src/moc_solver.cpp` (`recordStep()`)
- Result schema field: `src/moc_solver.hpp` (`SimResults.node_cavitation`)
- Python export of cavitation flag: `src/bindings.cpp` (`results_to_dict`)

## Operational behavior (baseline)

- Cavitation is represented as a boolean event per node per time step:
  `node_cavitation[node_id][k]` is `1` when pressure is at/below vapor pressure,
  otherwise `0`.
- No persistent vapor cavity state is stored in `NodeState`.
- No cavity volume is integrated over time.
- No explicit cavity-collapse event model is present.

## Known limitations

- Cannot represent cavity growth and collapse dynamics explicitly.
- Cannot directly model water-column collision spikes from cavity collapse.
- Provides a practical pressure-floor safeguard, but not full column-separation
  physics fidelity for severe cavitation events.

## Why this matters for DVCM

This baseline establishes the exact legacy behavior that must remain available
as a compatibility mode while DVCM is introduced. All Phase 1 scaffolding and
later DVCM implementation should preserve this mode as a selectable reference.
