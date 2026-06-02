# DVCM Implementation Roadmap

This document provides a full-scale, staged plan for adding a Discrete Vapor Cavity Model (DVCM) to RTHYM-MOC while protecting current behavior.

## Goals

- Add physically meaningful cavitation dynamics (cavity formation, growth, collapse).
- Preserve current solver behavior by default during rollout.
- Avoid regressions in existing transient features (controls, valves, pumps, surge devices, INP import).
- Provide clear validation evidence before enabling DVCM as a recommended mode.

## Non-goals (initial rollout)

- Perfect parity with every commercial implementation detail.
- Immediate support for every boundary type in the first implementation.
- Simultaneous introduction of DGCM and advanced entrained-gas models.

## Delivery strategy

Use gated phases with explicit exit criteria. Legacy clamp stays default until DVCM meets stability and validation gates.

## Phase 0: Baseline and Governance

### Deliverables

- Freeze current cavitation behavior as the baseline reference mode.
- Define ownership for solver core, bindings, tests, and docs.
- Define branch and PR policy for DVCM work.

### Checklist

- [x] Capture baseline metrics from current tests (runtime, failures, key pressure traces). See `docs/dvcm_phase0_baseline.md`.
- [x] Record baseline cavitation behavior in a short design note. See `docs/dvcm_baseline_cavitation_note.md`.
- [x] Create DVCM epic with linked issues for each phase. Epic: https://github.com/jlillywh/RTHYM-MOC/issues/52
- [x] Require CI green and targeted benchmark pass for each DVCM PR. Policy: `docs/dvcm_pr_gate_policy.md`; CI gate: `.github/workflows/tests.yml` job `dvcm-targeted-benchmark`.

### Exit criteria

- Baseline snapshot committed and linked in issue tracker.
- Team agrees on staged rollout and acceptance criteria.

## Phase 1: Safe Scaffolding (No Physics Change)

### Deliverables

- Cavitation mode selector added, defaulting to legacy clamp behavior.
- Internal state placeholders for cavity metrics.
- Backward-compatible result schema extension.

### Checklist

- [x] Add `CavitationModel` enum (for example: `LegacyClamp`, `DVCM`).
- [x] Add solver parameter/plumbing to select model.
- [x] Keep default mode as `LegacyClamp`.
- [x] Add `NodeState` fields for cavity state (active flag, cavity volume, collapse counters).
- [x] Add optional output channels (for example `node_cavity_volume`) without changing existing keys.
- [x] Update bindings and type hints for new optional outputs.
- [x] Add regression tests proving legacy mode output is unchanged.

### Exit criteria

- Zero behavior change in legacy mode across existing tests. Verified by full suite + explicit legacy regressions in `tests/test_legacy_mode_regression.py` and `tests/test_phase1_e2e_contract.py`.
- New schema fields available and documented as experimental. Implemented in solver/bindings and documented in `README.md` Results dictionary section.

## Phase 2: Junction-Only DVCM MVP

### Deliverables

- DVCM equations and regime switching for junction-like nodes only.
- Numerically stable cavity growth/collapse handling for this subset.

### Checklist

- [x] Implement regime logic: liquid-full, cavity-active, collapse transition.
- [x] Enforce non-negative cavity volume and physically bounded updates.
- [x] Add hysteresis/tolerances to prevent mode-chatter near vapor threshold.
- [x] Preserve current behavior for unsupported node types.
- [x] Record cavity diagnostics per step (volume, active state, collapse flag).
- [x] Add unit tests for cavity initiation and collapse at junction nodes.

### Exit criteria

- Junction DVCM passes dedicated tests and does not destabilize legacy suite. Verified by `tests/test_dvcm_junction_regime.py`, `tests/test_dvcm_unsupported_nodes.py`, and full-suite validation (`306 passed, 2 deselected`) with `pytest -q --cov=rthym_moc --cov-report=term-missing` at 100% package coverage.

## Phase 3: Validation Harness and Reference Cases

### Deliverables

- Reference DVCM cases with quantitative acceptance thresholds.
- Clear comparison workflow against legacy clamp and known references.

### Checklist

- [x] Add at least 3 canonical cavitation scenarios:
- [x] Rapid closure with cavity formation and collapse spike.
- [x] Reopening/pressure recovery case.
- [x] Long-run stability case with repeated events.
- [x] Define acceptance metrics (peak error, timing of collapse, RMS trace error).
- [x] Store reference artifacts for reproducible regression.
- [x] Add CI jobs/markers for DVCM tests.

### Exit criteria

- Validation metrics documented and reproducible in CI.

## Phase 4: Boundary Expansion

### Deliverables

- DVCM interactions extended to major boundary/device categories.

### Checklist

- [x] Integrate with valve boundary logic (standard valves and check valves).
- [x] Integrate with pump trip/start and inertia behavior.
- [x] Evaluate interactions with standpipe and hydropneumatic tank dynamics.
- [x] Evaluate interactions with air valve compressible model.
- [x] Add targeted tests per boundary/device integration.

### Exit criteria

- No major instability in mixed-device benchmark networks.

## Phase 5: Numerical Robustness and Performance

### Deliverables

- Stable behavior under aggressive events and practical timestep ranges.
- Acceptable runtime overhead relative to baseline.

### Checklist

- [x] 1. Stress test with small/large `dt`, short/long pipes, stiff networks.
- [x] 2. Add guards for NaN/Inf propagation and non-physical states.
- [x] 3. Profile DVCM hot paths and optimize key loops.
- [x] 4. Set runtime overhead target (for example <= 25% on selected benchmarks).
- [x] 5. Document recommended timestep guidance for DVCM mode. See [docs/dvcm_timestep_guidance.md](file:///wsl.localhost/Ubuntu/home/jason/RTHYM-MOC/docs/dvcm_timestep_guidance.md).

### Exit criteria

- Robustness and performance targets met on defined benchmark matrix.

## Phase 6: API and Documentation Hardening

### Deliverables

- Public API support finalized and documented.
- User guidance for choosing cavitation model.

### Checklist

- [x] 6. Finalize public parameter names and defaults.
- [x] 7. Update README cavitation section with explicit model options.
- [x] 8. Add docs page comparing Legacy Clamp vs DVCM behavior and cost. See [docs/dvcm_comparison.md](file:///wsl.localhost/Ubuntu/home/jason/RTHYM-MOC/docs/dvcm_comparison.md).
- [x] 9. Add migration notes for existing users. See [docs/dvcm_migration.md](file:///wsl.localhost/Ubuntu/home/jason/RTHYM-MOC/docs/dvcm_migration.md).
- [x] 10. Add notebook/example showcasing DVCM scenarios and interpretation. See [examples/dvcm_showcase.ipynb](file:///wsl.localhost/Ubuntu/home/jason/RTHYM-MOC/examples/dvcm_showcase.ipynb).

### Exit criteria

- Docs, API reference, and examples fully aligned.

## Phase 7: Controlled Rollout

### Deliverables

- DVCM released as opt-in with monitoring period.

### Checklist

- [x] 11. Release as experimental or opt-in mode.
- [x] 12. Collect feedback from internal and external users. See [.github/ISSUE_TEMPLATE/dvcm_feedback.md](file:///wsl.localhost/Ubuntu/home/jason/RTHYM-MOC/.github/ISSUE_TEMPLATE/dvcm_feedback.md).
- [ ] 13. Track defect reports and edge-case failures.
- [ ] 14. Patch high-severity issues before broader recommendation.

### Exit criteria

- No unresolved critical defects in opt-in period.

## Phase 8: Default-Mode Decision

### Deliverables

- Decision whether to keep legacy default or promote DVCM default.

### Checklist

- [ ] 15. Review validation, stability, and performance evidence.
- [ ] 16. Confirm backward compatibility impact and migration burden.
- [ ] 17. Decide default mode and deprecation timeline (if any).
- [ ] 18. Publish release notes and upgrade guide.

### Exit criteria

- Decision documented with rationale and implementation plan.

## Risk register

- Numerical chatter at regime boundaries.
- Non-physical cavity behavior under coarse timestep.
- Hidden interactions with control rules and device models.
- Performance regression in large networks.
- User confusion from multiple cavitation modes.

## Mitigations

- Keep legacy mode default through Phase 7.
- Use strict invariants and assertion-backed debug builds.
- Add targeted mixed-device regression suites early.
- Track performance budgets per phase.
- Provide clear mode-selection guidance and examples.

## Test strategy summary

- Unit tests: regime transitions, cavity volume integration, invariants.
- Regression tests: legacy equivalence in `LegacyClamp` mode.
- Physics validation tests: cavity formation/collapse against reference traces.
- Integration tests: DVCM with controls, pumps, valves, and surge devices.
- Stability tests: long-run and repeated-event transients.

## Master checklist

- [x] Phase 0 complete
- [x] Phase 1 complete
- [x] Phase 2 complete
- [x] Phase 3 complete
- [x] Phase 4 complete
- [x] 19. Phase 5 complete
- [x] 20. Phase 6 complete
- [ ] 21. Phase 7 complete
- [ ] 22. Phase 8 complete
- [ ] 23. Legacy mode unchanged and verified throughout rollout
- [ ] 24. DVCM validation artifacts committed and reproducible
- [x] 25. User-facing docs and examples complete
- [ ] 26. Final release decision documented
