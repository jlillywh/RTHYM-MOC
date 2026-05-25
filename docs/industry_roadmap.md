# Industry Readiness Roadmap

This roadmap turns the current gap analysis into an execution plan for making
RTHYM-MOC more useful to practicing surge-analysis engineers.

Priority labels:

- `P0`: highest-priority items that most directly improve industry readiness.
- `P1`: high-value workflow and engineering-output improvements.
- `P2`: broader platform and differentiation work.

Status labels:

- `Not started`
- `In progress`
- `Done`

## P0: Core Industry Gaps

These are the first items to chip away at. They close the most important gaps
between the current solver and what an engineer expects from a practical surge
analysis tool.

### 1. Check-valve behavior and reverse-flow protection

- Priority: `P0`
- Status: `Done`
- Why it matters: check valves are fundamental surge devices in pump systems,
  and treating them as regular pipes is not acceptable for many real studies.
- Current gap: `load_inp()` does not enforce EPANET `CV` behavior and the core
  solver does not expose a dedicated check-valve boundary/device.
- Deliverables:
  - add a dedicated check-valve device/boundary model
  - enforce reverse-flow prevention in both direct API models and imported INP
    models
  - document supported assumptions and limitations
  - add automated benchmarks for pump-trip and reverse-flow cases
- Exit criteria:
  - imported check valves are no longer treated as ordinary pipes
  - a reverse-flow regression test passes in CI
  - README documents the behavior explicitly

### 2. Controlled valve behavior for pressure-control devices

- Priority: `P0`
- Status: `Done`
- Why it matters: PRVs, PSVs, and PBVs are common in industry models and are
  currently imported without real control behavior.
- Current gap: imported pressure-control valves are initialized conservatively,
  but their setpoint logic is not modeled as an active transient control law.
- Deliverables:
  - define a transient control model for PRV/PSV/PBV behavior
  - preserve meaningful steady-state initialization when importing INP models
  - add direct tests for setpoint holding, relief behavior, and control
    transitions
  - document where the solver matches or intentionally deviates from EPANET
- Exit criteria:
  - PRV/PSV/PBV support is described as supported, not downgraded/approximate
  - imported benchmark cases with pressure-control valves have automated
    acceptance tests

### 3. Operational controls and event logic

- Priority: `P0`
- Status: `Done`
- Why it matters: real projects rely on event logic, not just precomputed
  schedules.
- Current gap: the solver supports explicit schedules, but not rule-driven
  controls, triggers, or interlocks.
- Deliverables:
  - design a control/event API for threshold and state-based actions
  - support at least common actions such as pump trip/start, delayed restart,
    and valve action triggered by head/pressure/time conditions
  - import a minimal useful subset of EPANET `[CONTROLS]` / `[RULES]`
  - add deterministic control-sequence regression tests
- Exit criteria:
  - an engineer can define at least one transient with event-triggered behavior
    without hand-building a full time schedule
  - imported control cases have documented supported and unsupported patterns

### 4. Industry-ready import fidelity

- Priority: `P0`
- Status: `In progress`
- Why it matters: many engineers begin from an EPANET or utility hydraulic
  model, then want to move directly into surge analysis.
- Current gap: base topology import is useful, but patterns, rules, and some
  device semantics are still dropped or approximated.
- Deliverables:
  - improve `load_inp()` parity for imported operating conditions
  - support a documented subset of demand patterns and controls
  - tighten valve/pump initialization against imported steady-state conditions
  - add import parity benchmarks with explicit acceptance bands
- Exit criteria:
  - imported models require materially fewer manual fixes before transient use
  - README limitations list gets shorter and more specific
- Progress (2026-05):
  - `[PATTERNS]`, `[DEMANDS]`, simple `[CONTROLS]` LINK/STATUS/AT TIME → schedules
  - Inline pump/valve head init uses upstream and downstream wntr heads
  - `docs/import_fidelity.md` + `tests/test_inp_import_fidelity.py`
  - Remaining: `[RULES]`, NODE controls, SETTINGS controls, broader parity INPs

## P1: Engineering Workflow Improvements

These items do not change the core solver as much, but they make the package
much more usable for engineering studies and client-facing work.

### 5. Engineering post-processing and report outputs

- Priority: `P1`
- Status: `Not started`
- Why it matters: engineers need envelopes, maxima/minima, event summaries, and
  study-ready outputs, not only raw time-series arrays.
- Deliverables:
  - helper functions for min/max pressure and head envelopes
  - cavitation duration / occurrence summaries
  - automatic peak-event summaries by node and pipe
  - export helpers for CSV/JSON study packages
  - a notebook or example script showing a report workflow
- Exit criteria:
  - common engineering summary plots/tables can be produced without bespoke
    one-off analysis code in every study

### 6. Scenario comparison workflow

- Priority: `P1`
- Status: `Not started`
- Why it matters: surge work is usually comparative, not single-run.
- Deliverables:
  - define a lightweight scenario container or comparison helper API
  - support side-by-side peak comparisons and acceptance checks
  - add examples for device sizing and closure-time alternatives
- Exit criteria:
  - common “base vs protected” and “option A vs option B” studies are concise
    and repeatable

### 7. Automated engineering acceptance checks

- Priority: `P1`
- Status: `Not started`
- Why it matters: practical studies often reduce to questions like “did any
  node exceed the pressure limit?”
- Deliverables:
  - helper functions for allowable max/min pressure checks
  - helper functions for cavitation / subatmospheric exposure checks
  - reusable acceptance-report objects for scripted studies
- Exit criteria:
  - engineers can script pass/fail design screening without manually inspecting
    every trace

## P2: Broader Model Scope and Differentiation

These items are valuable, but should come after the core device/control/import
gaps are closed.

### 8. More detailed air-valve and gas-handling physics

- Priority: `P2`
- Status: `Not started`
- Why it matters: advanced vacuum and air-management studies need more than the
  current surrogate model.
- Deliverables:
  - evaluate choked/compressible airflow support
  - evaluate float-mechanics behavior and richer air-mass thermodynamics
  - add validation cases if the model scope expands

### 9. Additional surge devices and specialty outputs

- Priority: `P2`
- Status: `Not started`
- Why it matters: industrial tools often distinguish themselves with dedicated
  device libraries and specialty calculations.
- Deliverables:
  - evaluate relief valves / surge anticipation valves
  - evaluate pipe-force / thrust-related output summaries
  - evaluate device sizing assistants for common protection strategies

### 10. Packaging and delivery improvements for broader adoption

- Priority: `P2`
- Status: `Done`
- Why it matters: accessibility matters for students, researchers, and
  practitioners evaluating the tool.
- Deliverables:
  - publish and verify PyPI distribution
  - improve wheel coverage to reduce install friction
  - validate Binder startup/runtime for the quickstart notebook
- Exit criteria:
  - first-time users can install or launch the project with minimal local build
    friction

## Suggested Execution Order

If working one item at a time, use this sequence:

1. Check-valve behavior and reverse-flow protection
2. Controlled valve behavior for pressure-control devices
3. Operational controls and event logic
4. Industry-ready import fidelity
5. Engineering post-processing and report outputs
6. Scenario comparison workflow
7. Automated engineering acceptance checks

## How To Use This Roadmap

- Open one GitHub issue per roadmap item.
- Keep each issue scoped to a single deliverable set.
- Link merged PRs back to the roadmap item.
- Update the status labels here as work advances.
- Re-rank items only when user feedback or project goals change materially.