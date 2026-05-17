# R-THYM MOC — JS / C++ / Python Engine Alignment Guide

**Version:** 2.0 — Decisions Finalized  
**Author:** Jason Lillywhite, jason@lillywhitewater.com  
**Purpose:** Definitive reference for aligning `transientWorker.js` with the C++/Python `rthym_moc` engine and the Hydraulic Reference appendix. All discrepancies below have been reviewed and resolved. The **C++/Python implementation is the canonical reference**; where differences exist the JavaScript engine must be updated to match.

Files reviewed:
- `src/moc_solver.cpp` / `src/moc_solver.hpp` — C++ engine (canonical)
- `tests/transientWorker.js` — JavaScript web engine
- `docs/appendix_hydraulic_reference.md` — user manual appendix

---

## Resolution Summary

| # | Topic | Status | Action |
|---|---|---|---|
| 1 | PDEs & MOC discretization | ✅ Match | None |
| 2 | Wave speed & steady friction | ✅ Match | None |
| 3 | Unsteady friction (USF) | ✅ Resolved | **C++ updated to dynamic Vardy-Brown (matches JS)** |
| 4 | Valve/Turbine 3-pipe fallback | ✅ Match | Document only |
| 5 | HPT atmospheric constant | ⚠️ Discrepancy | **Update JS: `34` → `33.9`** |
| 6 | Valve closure schedules | ✅ Match | None |
| 7 | Node type naming | ⚠️ Discrepancy | **Update JS to C++ names** |
| 8 | Turbine hardcoded diameter | ⚠️ Discrepancy | **Update JS to use `n.diameter`** |
| 9 | HPT orifice parameterization | ⚠️ Discrepancy | **Correct JS defaults to $C_d = 0.7$** |
| 10 | FuelTank | ✅ Not hydraulic | None — fuel system only |

---

## Detailed Findings

### 1. PDEs and MOC Discretization
- **Decision:** ✅ **No change required.**
- **Details:** The C+ and C− compatibility equations, pipe impedance $B = a/g$, resistance $R$, and Courant rounding are implemented identically in both engines.

### 2. Wave Speed and Steady Friction
- **Decision:** ✅ **No change required.**
- **Details:** Korteweg formula ($K = 319{,}000$ psi, $a_0 = 4860$ ft/s) and Hazen-Williams → Darcy-Weisbach conversion are identical.

### 3. Unsteady Friction (USF)
- **Decision:** ✅ **Resolved — C++ updated to match JS (dynamic Vardy-Brown).**
- **Change made to C++:** `k_Bru` is now computed automatically each timestep per pipe from the instantaneous Reynolds number (Vardy-Brown 1996). The `k_bru` parameter default changed from `0.0` to `-1.0` (sentinel for "auto"). Both engines now produce identical physically realistic damping without user calibration.

**Vardy-Brown formula (now in both engines):**

$$Re = \frac{|V_\text{mid}| \cdot D}{\nu}, \quad \nu = 1.07 \times 10^{-5}\ \text{ft}^2/\text{s}$$

$$C^* = \frac{7.41}{Re^{0.352}} \quad (Re > 100, \text{ else } 0)$$

$$k_\text{Bru} = \frac{C^*}{\sqrt{\pi}}$$

**Override behaviour:**
- `k_bru = -1` (default): dynamic Vardy-Brown per timestep per pipe
- `k_bru = 0`: steady friction only (disables USF)
- `k_bru > 0`: user-supplied static coefficient

**Files changed:** `src/moc_solver.hpp`, `src/moc_solver.cpp`, `src/bindings.cpp`, `docs/appendix_hydraulic_reference.md §6.2.1`

### 4. Valve & Turbine — 3-Pipe Fallback
- **Decision:** ✅ **No change required. Document only.**
- **Details:** Both engines implement the same fallback: when a Valve or Turbine is connected to more than 2 pipes, the solver falls back to an approximate fixed-head boundary. Valves and turbines should only be placed in series on a single pipe run. The appendix §7.3 should note this constraint.

### 5. Hydropneumatic Tank — Atmospheric Pressure Constant
- **Decision:** ✅ **Update JS.**
- **C++ value:** `H_ATM_FT = 33.9` ft (1 atm = 14.696 psi — correct)
- **JS value:** `Hb = 34` ft (rounded — incorrect)
- **JS change required:**
  ```javascript
  // Before:
  const Hb = 34;
  // After:
  const Hb = 33.9; // 1 atm = 14.696 psi = 33.9 ft of water
  ```

### 6. Valve Closure Schedules
- **Decision:** ✅ **No change required.**
- **Details:** Loss coefficient $K = (1/\tau)^2 - 1$ is identical. Equal-percentage geometric decay to 0.05 % before final step to 0 % is a correct numerical implementation.

### 7. Node Type Naming
- **Decision:** ✅ **Update JS to use C++/Python canonical names.**
- **Rationale:** The C++/Python names are the standard engineering terminology and match the appendix. JS will be updated to adopt these names for consistency.

| Current JS Name | Canonical C++/Python Name | Description |
|---|---|---|
| `SurgeControl` | `Standpipe` | Open free-surface surge tank / standpipe |
| `SurgeTank` | `HydropneumaticTank` | Closed pressurized vessel with gas cushion |

- **JS change required:** Rename node type strings in `transientWorker.js` and all associated UI/data layers. The internal logic (physics) does not change — only the string identifiers.

### 8. Turbine — Hardcoded Diameter
- **Decision:** ✅ **Update JS to use user-defined diameter.**
- **C++ behavior:** Uses `n.diameter` (inches) to compute the runner area $A_t = \pi (d/24)^2$ and thereby the design-point velocity $V_d$.
- **JS bug:** Ignores `n.diameter` and uses a hardcoded `diam = 8` for all turbines:
  ```javascript
  const diam = 8; // ← bug: should be n.diameter ?? 8
  ```
- **JS change required:**
  ```javascript
  // Before:
  const diam = 8;
  // After:
  const diam = n.diameter ?? 8; // use configured diameter, fall back to 8 in
  const A_pipe = Math.PI * Math.pow(diam / 24, 2);
  ```

### 9. Hydropneumatic Tank — Orifice Parameterization
- **Decision:** ✅ **Correct JS defaults to match C++ discharge-coefficient convention.**
- **C++ convention:** `loss_coeff_in` / `loss_coeff_out` are dimensionless discharge coefficients $C_d \in (0, 1)$. The orifice loss is:
  $$K = \frac{1}{2g\,(C_d \cdot A_\text{ori})^2}$$
  Default: $C_d = 0.7$ for both directions.
- **JS convention:** `inflowCoeff` / `outflowCoeff` are direct loss multipliers applied as $K = \text{coeff} / (2g A^2)$, i.e., they represent $1/C_d^2$.
- **Relationship:** $K_\text{JS coeff} = 1/C_d^2$, so $C_d = 0.7 \Rightarrow K_\text{coeff} \approx 2.04$.
- **Current JS defaults are wrong:**
  - `inflowCoeff = 5.0` → equivalent to $C_d \approx 0.45$ (too restrictive)
  - `outflowCoeff = 1.0` → equivalent to $C_d = 1.0$ (physically impossible — implies no loss)
- **JS change required:** Update defaults to match the C++ $C_d = 0.7$ convention:
  ```javascript
  // Before:
  let K_user = RHS > 0 ? (n.inflowCoeff ?? 5.0) : (n.outflowCoeff ?? 1.0);
  // After:
  let K_user = RHS > 0 ? (n.inflowCoeff ?? 2.04) : (n.outflowCoeff ?? 2.04);
  // Note: 2.04 = 1 / (0.7)^2 = equivalent to Cd = 0.7
  ```

### 10. FuelTank — Not a Hydraulic Node
- **Decision:** ✅ **No change required.**
- **Note:** FuelTank nodes supply fuel to power generators and have no connection to the water hydraulic system. They carry no hydraulic pipes and are correctly skipped by the `stepMOC` early-exit guard. This is not a discrepancy.

---

## Required JS Changes — Implementation Checklist

The following changes must be made to `transientWorker.js` (and any associated data/UI layers) to bring the JS engine into full alignment with the canonical C++/Python engine:

- [ ] **§5** — Change `const Hb = 34` to `const Hb = 33.9` in the `HydropneumaticTank` (`SurgeTank`) block.
- [ ] **§7** — Rename node type `SurgeControl` → `Standpipe` throughout JS and UI.
- [ ] **§7** — Rename node type `SurgeTank` → `HydropneumaticTank` throughout JS and UI.
- [ ] **§8** — Replace hardcoded `const diam = 8` with `const diam = n.diameter ?? 8` in the Turbine boundary block.
- [ ] **§9** — Change HPT orifice defaults: `inflowCoeff ?? 5.0` → `2.04`; `outflowCoeff ?? 1.0` → `2.04`.
- [ ] **§4** — Add note to appendix §7.3 documenting the 2-pipe topology constraint for Valve and Turbine nodes.
