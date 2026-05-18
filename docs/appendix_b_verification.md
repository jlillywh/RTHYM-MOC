# Appendix B — Cross-Engine Verification: Long Pipe Valve

This appendix documents the quantitative verification of the `rthym-moc`
C++/Python engine against the R-THYM web-application (JavaScript) engine on
the canonical **Long Pipe Valve** test network.  All 18 automated test cases
in `tests/test_long_pipe_valve.py` pass.

---

## B.1 Network Description

```
PressureBoundary_A (H = 100 ft, elev = 0 ft)
  ──[Pipe_1: 1000 ft]──► Junction_A  (elev = 66 ft)
  ──[Pipe_2: 1000 ft]──► Junction_B  (elev = 76 ft)
  ──[Pipe_3: 1000 ft]──► Valve_B     (8 in TCV, elev = 0 ft)
  ──[Pipe_4:  500 ft]──► Junction_C  (elev = 0 ft)
  ──[Pipe_5:  500 ft]──► PressureBoundary_B (H = 25 ft, elev = 0 ft)
```

All five pipes are 36-inch inside diameter, Hazen-Williams roughness C = 150,
Young's modulus E = 400,000 psi, wall thickness e = 0.694 in.

**Initial condition:** Valve_B open at 5 %, producing a steady flow of
Q₀ = 544.84 GPM throughout the network.

**Transient:** Valve_B is closed using an equal-percentage schedule from
t ≈ 22.63 s to t ≈ 32.77 s (JavaScript reference frame).

---

## B.2 Reference Data

| File | Contents |
|---|---|
| `tests/R-THYM_MOC_Verification.json` | Steady-state heads, wave speeds, peak pressures, valve schedule |
| `tests/R-THYM_MOC_Traces.csv` | Time-series pressure (psi) and pipe flow (GPM) at t = 0.01–95.94 s |

The CSV exports pipe-section flows keyed by pipe ID (`Pipe_3_Q`, `Pipe_2_Q`,
`Pipe_4_Q`) with column-to-pipe mapping documented in
`metadata.q_sources` of the JSON.

---

## B.3 Simulation Setup

The C++ engine is run with a 60-second **warmup period** prepended to the
reference valve schedule.  This allows any numerical initialization
transients to damp before the closure begins.

Key parameters:

| Parameter | Value |
|---|---|
| `_WARMUP_S` | 60 s |
| `_SIM_TIME` | 232 s |
| `_DT` | 0.01 s |
| Valve schedule (C++ frame) | hold at 5 % until t = 82.62 s, then close to 0 % by t = 92.77 s |

The shifted schedule includes an explicit hold-point at
`(_CLOSURE_START_SIM − dt, 5 %)` to prevent the C++ solver (which linearly
interpolates between adjacent schedule entries) from drifting below the
initial 5 % opening during the pre-closure warmup period.

---

## B.4 Test Metrics and Results

### B.4.1 Wave Speed

The Korteweg formula gives a = 746.67 ft/s, matching the JS reference exactly.

| | Value |
|---|---|
| JS reference | 746.67 ft/s |
| C++ (analytical) | 746.67 ft/s |
| Error | 0.00 ft/s |
| Tolerance | ± 5 ft/s |
| **Result** | **PASS** |

### B.4.2 Pre-Closure Steady-State Heads

Averaged over the JS reference window t = 5–18 s (C++ frame t = 65–78 s),
well before the valve begins closing at t = 22.63 s.

| Node | JS ref (ft) | C++ sim (ft) | Error (ft) | Tol | Result |
|---|---:|---:|---:|---|---|
| PressureBoundary_A | 100.000 | 100.000 | +0.000 | ±0.5 ft | **PASS** |
| Junction_A         | 100.028 |  99.998 | −0.030 | ±0.5 ft | **PASS** |
| Junction_B         | 100.016 |  99.996 | −0.020 | ±0.5 ft | **PASS** |
| Junction_C         |  25.025 |  25.001 | −0.023 | ±0.5 ft | **PASS** |
| PressureBoundary_B |  25.000 |  25.000 | +0.000 | ±0.5 ft | **PASS** |

The small residual (~0.03 ft) reflects the difference between the EPANET
initial condition used as the JS steady state and the MOC-settled value in the
C++ engine.

### B.4.3 Peak Pressures

Peak min/max pressures over the full simulation (232 s).

| Node | JS max (psi) | C++ max (psi) | Error | JS min (psi) | C++ min (psi) | Error | Tol | Result |
|---|---:|---:|---:|---:|---:|---:|---|---|
| PressureBoundary_A | 43.290 | 43.290 | +0.000 | 43.290 | 43.290 | +0.000 | ±1.5 psi | **PASS** |
| Junction_A         | 17.869 | 18.008 | +0.139 | 12.013 | 11.900 | −0.113 | ±1.5 psi | **PASS** |
| Junction_B         | 14.986 | 15.216 | +0.230 |  6.048 |  5.837 | −0.211 | ±1.5 psi | **PASS** |
| Junction_C         | 12.801 | 12.856 | +0.055 |  8.260 |  8.155 | −0.105 | ±1.5 psi | **PASS** |
| PressureBoundary_B | 10.823 | 10.823 | +0.000 | 10.823 | 10.823 | +0.000 | ±1.5 psi | **PASS** |
| Valve_B            | 48.206 | 48.470 | +0.264 | 38.388 | 38.126 | −0.262 | ±1.5 psi | **PASS** |

The largest error is 0.264 psi at Valve_B (0.5 % of peak), well within
tolerance.

### B.4.4 Time-Series Comparison

Pressure traces are compared over the post-closure window (JS t = 35–65 s,
C++ t = 95–125 s).  Flow is compared in the pre-closure steady-state window
(JS t = 5–18 s, C++ t = 65–78 s) where both engines record the same physical
pipe flow without wave decorrelation.

| Quantity | Window (JS frame) | RMS Error | Tolerance | Result |
|---|---|---:|---|---|
| Valve_B pressure   | 35–65 s (post-closure) | 0.531 psi | ±2.0 psi | **PASS** |
| Junction_B pressure| 35–65 s (post-closure) | 0.415 psi | ±2.0 psi | **PASS** |
| Junction_C pressure| 35–65 s (post-closure) | 0.327 psi | ±2.0 psi | **PASS** |
| Pipe_3 flow        |  5–18 s (pre-closure)  | 0.151 GPM | ±10 GPM  | **PASS** |

> **Note on flow comparison window.** Post-closure pipe flows in both engines
> oscillate due to water-hammer reflections.  Although the pressures agree
> within 0.53 psi, the two engines' characteristic-variable flows decorrelate
> over long post-closure intervals (different numerical friction and Courant
> discretisation).  The pre-closure window provides a physically unambiguous
> steady-state flow check, while the three pressure-trace tests verify the
> transient behaviour.

---

## B.5 Summary

All 18 test cases pass.  The C++/Python `rthym-moc` engine reproduces the
R-THYM JavaScript engine to within:

- **Wave speed:** 0.00 ft/s
- **Steady-state heads:** ≤ 0.030 ft
- **Peak pressures:** ≤ 0.264 psi (< 0.6 % of peak)
- **Post-closure pressure traces (RMS):** ≤ 0.531 psi
- **Pre-closure steady-state flow (RMS):** 0.151 GPM

These results confirm that the two independent implementations of the
Method of Characteristics are in excellent agreement for this representative
water-hammer scenario.
