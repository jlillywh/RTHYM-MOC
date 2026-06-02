---
name: DVCM Cavitation Model Feedback
about: Provide feedback or report issues when testing the experimental Discrete Vapor Cavity Model (DVCM).
title: '[DVCM Feedback] '
labels: dvcm, feedback
assignees: ''

---

## DVCM Feedback & Test Report

Thank you for testing the experimental **Discrete Vapor Cavity Model (DVCM)**! Your feedback helps us transition DVCM to a stable default.

### 1. Test Case Geometry & Topology
Please describe the pipeline layout (e.g., Tank -> Pump -> Valve -> Tank) or attach an EPANET `.inp` file.
* **Nodes / Devices involved**: (e.g., Valve V1, Pump Pump1)
* **Pipe Lengths & Diameters**: (e.g., 2000 ft, 12 in)
* **Wave Speed**: (e.g., 4000 ft/s)

### 2. Simulation Configuration
* **Timestep size ($dt$)**: (e.g., 0.0001 s)
* **Total duration**: (e.g., 10.0 s)
* **Vapor pressure ($p_{\text{vapor}}$)**: (e.g., -14.2 psi)
* **API used**: `solver.run(...)` or `run_si(...)`

### 3. Stability & Performance
* **Did the simulation run to completion?** (Yes / No)
* **If it failed, what was the error?** (e.g., `RuntimeError: Numerical instability: NaN/Inf detected...` or `Non-physical state: Negative cavity volume...`)
* **How did you resolve it?** (e.g., did halving the timestep resolve the issue?)

### 4. Observations & Findings
* **Pressure Peaks**: Did the secondary pressure spike (water-column collision hammer) feel physically reasonable or match your expectations?
* **Comparison**: How did the DVCM pressure trace compare to the `LegacyClamp` HGL trace?
* **Telemetry**: Did you find the new diagnostic keys (`node_cavity_volume`, `node_cavity_active`, `node_cavity_collapse_flag`, `node_cavity_collapse_count`) easy to interpret?

### 5. Plots & Logs
(If possible, please drag-and-drop HGL head or cavity volume plots here to help us visualize the transient).

### 6. Additional Comments or Suggestions
(Any other feedback, feature requests, or notes on documentation clarity).
