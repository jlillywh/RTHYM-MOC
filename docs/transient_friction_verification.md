# Transient friction verification (Phase 6)

Cross-checks for `TransientFrictionModel` against published literature and
archived reference metrics. Automated tests:
`tests/test_transient_friction_literature.py`.

Reference artifact: `tests/transient_friction_literature_reference.json`
(regenerate with `tests/generate_transient_friction_literature_reference.py`).

## 1. Steady-friction wave reflections (Wylie & Streeter)

**Source:** Wylie & Streeter (1993), *Fluid Transients in Systems* — multi-cycle
reflections on a reservoir–pipe–dead-end line dissipate roughly **2·H<sub>f</sub>**
of head per wave round-trip under steady Darcy friction.

**Implementation check:** Same network as `examples/test_wave_reflections.py`
(3000 ft, 12 in, HW 130, 500 GPM, *a* = 4000 ft/s) with USF disabled
(`usf_tau = dt`).

**Acceptance:** Mean positive-plateau decay per period within **35%** of
2·H<sub>f</sub>; oscillation period within **2%** of 4*L*/*a* = 3.0 s.

This is a **literature-anchored** check (textbook approximation), not a
digitized lab trace.

## 2. Long-pipe envelope ordering (Bergant et al.)

**Sources:**

- Bergant, Simpson & Vitkovsky (2001), *J. Hydraul. Res.* 39(3):249–257 —
  compares quasi-steady, Zielke, and Brunone models to laboratory water-hammer data.
- Vitkovsky et al. (2006), *J. Hydraul. Eng.* 132(7):696–708 — systematic
  evaluation showing **unsteady friction models attenuate peaks more** than
  quasi-steady friction on simple pipeline transients.

**Implementation check:** LP-07 reference case (5-mile line, partial valve
throttle, capped grid) from Phase 6 roadmap — mid-pipe period-bucket peak
envelope compared for `QuasiSteady` vs `Vitkovsky`.

**Acceptance (directional):** Vitkovsky late envelope mean **≥ 5 ft** below
quasi-steady; Vitkovsky envelope decay ratio lower than quasi-steady. Archived
metrics in the JSON file provide regression anchors (±5%).

Exact peak-by-peak match to external MOC software (HAMMER, WANDA, etc.) is **not**
claimed; third-party TSNet exports for this friction sweep were not stable in CI.

## Related tests

| Test | Type |
|------|------|
| `test_transient_friction_literature.py` | Literature / archived reference |
| `test_transient_friction_model.py` | Selector plumbing and LP-07 damping (`@pytest.mark.slow`) |
| `examples/test_wave_reflections.py` | Tutorial script (period + optional TSNet overlay) |

See also [appendix_hydraulic_reference.md](appendix_hydraulic_reference.md) §6 and
[long_pipeline_surge_roadmap.md](long_pipeline_surge_roadmap.md) Phase 6.
