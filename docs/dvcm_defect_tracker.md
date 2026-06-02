# DVCM Defect & Edge-Case Tracker

This document is a living log to track, prioritize, and record resolutions for defect reports, numerical instabilities, and edge-case failures identified during the **Discrete Vapor Cavity Model (DVCM)** beta rollout phase (Phase 7).

---

## 1. Defect Log

| Defect ID | Date Reported | Severity | Status | Description | Trigger Scenario / Grid Setup | Resolution / PR |
|:---|:---|:---|:---|:---|:---|:---|
| *None* | | | | *No defects currently reported.* | | |

---

## 2. Severity Classification Matrix

Use the following guidelines to prioritize incoming issues:

* **Critical**: Complete numerical failure (`NaN`/`Inf` loop or crash) that cannot be resolved by standard timestep adjustments ($dt \ge 0.0001\text{ s}$), or severe physical inaccuracies (e.g., massive negative cavity volume).
* **High**: Numerical instability or volume integration overshoot that occurs on practical setups, but can be resolved by reducing the timestep. Requires C++ engine refinement to enhance robustness.
* **Medium**: Telemetry or result mapping discrepancy (e.g., missing keys, wrong unit translations in `run_si`), or minor numerical chatter at regime transition boundaries.
* **Low**: Typographical errors in documentation, stubs (`_rthym_moc.pyi`), or minor warnings improvements.

---

## 3. Known Numeric Limits & Expected Edge Cases

During initial internal testing, the following numerical constraints were identified. These are expected behaviors based on MOC physics, but should be monitored:

### A. Coarse Timestep Overshoot
* **Symptom**: `RuntimeError: Non-physical state: Negative cavity volume detected` or `NaN/Inf detected`.
* **Cause**: When $dt$ is too large (e.g., $dt \ge 0.005\text{ s}$), the integration step $V_c^{t+dt} = V_c^t + \Delta Q \cdot dt$ behaves like a coarse forward-Euler step. During rapid cavity collapse, the volume changes too quickly for the grid spacing, causing the calculated volume to overshoot past zero into negative values.
* **Standard Workaround**: Reduce timestep (e.g., to $dt = 0.0001\text{ s}$).

### B. High-Frequency Chatter near Vapor Threshold
* **Symptom**: Rapid switching back-and-forth between the Liquid-Full and Cavity-Active regimes over successive steps.
* **Cause**: High-frequency waves bouncing near the vapor pressure boundary can trigger regime switches repeatedly.
* **Mitigation (Phase 2)**: The C++ engine utilizes a small pressure hysteresis and volume tolerance to damp out chatter. If chatter persists and causes instability, report the setup.

---

## 4. How to Log a Defect

When a new issue is identified or reported (via a GitHub Issue using the **DVCM Feedback** template):
1. Assign a new Defect ID (`DF-00X`) in the table above.
2. Record the reporter, setup details, and reproduction steps.
3. Mark status as **Open** or **In Progress**.
4. Once resolved, reference the resolving commit or Pull Request and mark status as **Resolved**.
