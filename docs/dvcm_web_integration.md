# R-THYM Web App Integration Guide: DVCM & Air Telemetry

This document provides developer reference details for integrating version `0.4.0` WebAssembly (WASM) solvers into the proprietary **R-THYM** web application frontend. It covers output keys, engineering benefits, and UI configuration guardrails.

---

## 1. WebAssembly (WASM) Output Keys

When running the MOC solver step-by-step in the browser via WebAssembly (`get_step_results()`), the step results dictionary contains the following telemetry properties per node:

### A. Vapor Cavity Telemetry (DVCM)
These fields are populated when `cavitation_model` is set to `DVCM` (value `1` in the enum):
* **`cavityVolume`** ($\text{ft}^3$): The current volume of the water vapor pocket.
* **`cavityActive`** (`true`/`false`): Whether column separation is currently active at this node.
* **`cavityCollapseFlag`** (`true`/`false`): Set to `true` on the exact timestep the cavity transitions into the collapse regime.
* **`cavityCollapseCount`** (`int`): Cumulative count of cavity collapse events for this node.

### B. Gas/Air Pocket Telemetry (Air Valves & Tanks)
These fields are populated when surge devices (like `AirValve` or `HydropneumaticTank`) are present:
* **`gasVolume`** ($\text{ft}^3$): The volume of the air pocket currently admitted or trapped at the device.
* **`gasPressure`** ($\text{psi}$): The pneumatic pressure of the air pocket.
* **`airLossRate`** ($\text{gpm}$): The current venting rate of air.
* **`airCumulativeLoss`** ($\text{gal}$): The cumulative volume of air vented.

---

## 2. Engineering Benefits: Coexistence & Mitigation Analysis

Exposing both DVCM and Air Valve telemetry in the R-THYM UI enables users to perform **surge mitigation effectiveness analysis**:

* **Concurrent Modeling**: Users can place an `AirValve` at a high point in their system and track how much air it admits (`gasVolume`). Simultaneously, they can monitor neighboring junctions using DVCM (`cavityVolume`).
* **Visualizing Effectiveness**: In the UI chart:
  - If the `AirValve` is sized correctly, the neighboring junctions will show `cavityVolume = 0` (column separation prevented).
  - If the `AirValve` is undersized, the UI will show secondary vapor cavities (`cavityVolume > 0`) forming and collapsing downstream.
  - Without DVCM, secondary vapor pockets are flat-lined by legacy clamping, making it impossible to see if they were truly mitigated.

---

## 3. UI Guardrails & Timestep Enforcement

Because the DVCM is a physical model requiring integration of small volume increments over time:

1. **Timestep Alert**: When a user selects `DVCM` in the UI, the frontend should recommend or enforce a timestep **`dt <= 0.001s`** (ideally `0.0001s`).
2. **Coarse Timestep Warning**: If the user runs the simulation with `dt > 0.001s` and `DVCM` enabled, a warning should be displayed stating that numerical volume overshoot may occur.
