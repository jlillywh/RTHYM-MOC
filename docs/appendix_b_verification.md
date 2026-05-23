# Appendix B — Cross-Engine Verification

This appendix documents three independent verification studies comparing
RTHYM-MOC against the R-THYM web app, TSNet, and the analytical Joukowsky
solution:

1. **Long Pipe Valve** (§B.1–B.5): RTHYM-MOC vs R-THYM web app on a
   5-pipe equal-percentage valve closure network.  All 18 automated tests pass.

2. **TSNet Joukowsky Benchmark** (§B.6): three-way comparison of RTHYM-MOC,
   TSNet, and the analytical Joukowsky formula for an instant valve
   closure on a single-pipe network.  All 5 automated tests pass.

3. **R-THYM Joukowsky** (§B.7): RTHYM-MOC vs R-THYM web app on an
   instant valve closure with column separation and downstream stub-pipe
   resonance.  All 7 automated tests pass.

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
t ≈ 22.63 s to t ≈ 32.77 s (R-THYM web app frame).

---

## B.2 Reference Data

The EPANET network file below defines the steady-state network used to
initialise both engines.  Transient reference data (peak pressures, wave
speeds, time-series traces) were exported from the R-THYM web app.

**Long Pipe Valve network (EPANET INP format)**

```
[TITLE]
Exported from Hydro-Ops Digital Twin

[JUNCTIONS]
;ID              Elevation  Demand
Junction_A       66         0
Junction_B       76         0
Junction_C       0          0
Valve_B_in       0          0
Valve_B_out      0          0

[RESERVOIRS]
;ID                    Head
PressureBoundary_A     100
PressureBoundary_B     25

[PIPES]
;ID      Node1                Node2           Length  Diameter  Roughness  MinorLoss  Status
Pipe_1   PressureBoundary_A   Junction_A      1000    36        150        0          Open
Pipe_2   Junction_A           Junction_B      1000    36        150        0          Open
Pipe_3   Junction_B           Valve_B_in      1000    36        150        0          Open
Pipe_4   Valve_B_out          Junction_C       500    36        150        0          Open
Pipe_5   Junction_C           PressureBoundary_B  500  36      150        0          Open

[VALVES]
;ID       Node1        Node2         Diameter  Type  Setting  MinorLoss
Valve_B   Valve_B_in   Valve_B_out   8         TCV   90.250   0

[END]
```

---

## B.3 Simulation Setup

RTHYM-MOC is run with a 60-second **warmup period** prepended to the
reference valve schedule.  This allows any numerical initialization
transients to damp before the closure begins.

Key parameters:

| Parameter | Value |
|---|---|
| `_WARMUP_S` | 60 s |
| `_SIM_TIME` | 232 s |
| `_DT` | 0.01 s |
| Valve schedule (RTHYM-MOC frame) | hold at 5 % until t = 82.62 s, then close to 0 % by t = 92.77 s |

The shifted schedule includes an explicit hold-point at
`(_CLOSURE_START_SIM − dt, 5 %)` to prevent RTHYM-MOC (which linearly
interpolates between adjacent schedule entries) from drifting below the
initial 5 % opening during the pre-closure warmup period.

---

## B.4 Test Metrics and Results

### B.4.1 Wave Speed

The Korteweg formula gives a = 746.67 ft/s, matching the R-THYM web app exactly.

| | Value |
|---|---|
| R-THYM web app | 746.67 ft/s |
| RTHYM-MOC | 746.67 ft/s |
| Error | 0.00 ft/s |
| Tolerance | ± 5 ft/s |
| **Result** | **PASS** |

### B.4.2 Pre-Closure Steady-State Heads

Averaged over the R-THYM web app window t = 5–18 s (RTHYM-MOC frame t = 65–78 s),
well before the valve begins closing at t = 22.63 s.

| Node | R-THYM (ft) | RTHYM-MOC (ft) | Error (ft) | Tol | Result |
|---|---:|---:|---:|---|---|
| PressureBoundary_A | 100.000 | 100.000 | +0.000 | ±0.5 ft | **PASS** |
| Junction_A         | 100.028 |  99.998 | −0.030 | ±0.5 ft | **PASS** |
| Junction_B         | 100.016 |  99.996 | −0.020 | ±0.5 ft | **PASS** |
| Junction_C         |  25.025 |  25.001 | −0.023 | ±0.5 ft | **PASS** |
| PressureBoundary_B |  25.000 |  25.000 | +0.000 | ±0.5 ft | **PASS** |

The small residual (~0.03 ft) reflects the difference between the EPANET
initial condition used as the R-THYM web app steady state and the MOC-settled value in
RTHYM-MOC.

### B.4.3 Peak Pressures

Peak min/max pressures over the full simulation (232 s).

| Node | R-THYM max (psi) | RTHYM-MOC max (psi) | Error | R-THYM min (psi) | RTHYM-MOC min (psi) | Error | Tol | Result |
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

Pressure traces are compared over the post-closure window (R-THYM web app t = 35–65 s,
RTHYM-MOC t = 95–125 s).  Flow is compared in the pre-closure steady-state window
(R-THYM web app t = 5–18 s, RTHYM-MOC t = 65–78 s) where both engines record the same
physical pipe flow without wave decorrelation.

| Quantity | Window (R-THYM frame) | RMS Error | Tolerance | Result |
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

## B.5 Summary (Long Pipe Valve)

All 18 test cases pass.  RTHYM-MOC reproduces the R-THYM web app to within:

- **Wave speed:** 0.00 ft/s
- **Steady-state heads:** ≤ 0.030 ft
- **Peak pressures:** ≤ 0.264 psi (< 0.6 % of peak)
- **Post-closure pressure traces (RMS):** ≤ 0.531 psi
- **Pre-closure steady-state flow (RMS):** 0.151 GPM

These results confirm that the two independent implementations of the
Method of Characteristics are in excellent agreement for this representative
water-hammer scenario.

---

## B.6 TSNet Joukowsky Benchmark

### B.6.1 Purpose

This section provides an independent validation of `rthym-moc` against the
`TSNet` open-source Python MOC library (v0.2.2) using the classical Joukowsky
instant-closure test, for which an exact analytical solution exists.  The
three-way comparison (analytical formula, `rthym-moc`, `TSNet`) confirms that
both MOC implementations correctly propagate the initial pressure wave and
that `rthym-moc` produces results statistically indistinguishable from a
widely-used reference solver.

### B.6.2 Network

```
R1 (H = 150 ft) ──[P1: 3000 ft, 12 in, HW C=130]──► V1 (closed) ──[P2: stub]──► R2
```

| Parameter | Value |
|---|---|
| Upstream reservoir head | 150 ft |
| Pipe length | 3000 ft |
| Pipe diameter | 12 in |
| Hazen-Williams C | 130 |
| Initial flow Q₀ | 500 GPM |
| Initial velocity V₀ | 1.418 ft/s |
| Wave speed *a* | 4000 ft/s |
| Time step *dt* | 0.01 s |
| Simulation duration | 3.0 s |

**Transient event:** The valve V1 is slammed shut at t = 0 (closure in one
time step) in both solvers.

**Unsteady-friction correction:** Disabled in both solvers (pure
steady-friction MOC) so that results are directly comparable.

### B.6.3 Analytical Reference (Joukowsky Equation)

The Joukowsky pressure rise is:

$$\Delta H = \frac{a \cdot V_0}{g} = \frac{4000 \times 1.418}{32.2} = 176.3 \text{ ft}$$

With steady-state friction loss $H_f = 2.10$ ft, the pre-closure head at the
valve is $H_{DN} = 147.90$ ft.

| Quantity | Value |
|---|---|
| First-step peak at valve | $H_{DN} + \Delta H$ = **324.18 ft** |
| Theoretical maximum (after wave sweeps HGL) | $H_{RES} + \Delta H$ = **326.28 ft** |

### B.6.4 Results

| Quantity | Analytical (ft) | rthym-moc (ft) | TSNet (ft) |
|---|---:|---:|---:|
| First-step peak at valve | 324.18 | **324.10** | **324.30** |
| Transient maximum | 326.28 | **326.17** | **326.34** |

| Engine | Error vs analytical (first-step) | Error vs analytical (max) |
|---|---|---|
| rthym-moc | 0.02 % | 0.03 % |
| TSNet | 0.04 % | 0.02 % |

**Cross-engine time-series comparison** (RMS of head difference over 0–1.5 s,
spanning the first wave cycle):

| Metric | Value | Tolerance | Result |
|---|---:|---|---|
| rthym-moc vs TSNet RMS | **0.175 ft** | ≤ 0.5 ft | **PASS** |

### B.6.5 Performance

`rthym-moc` completed the same 300-step simulation in **< 1 ms**, compared to
**~65 ms** for TSNet (pure Python), a speedup of roughly **200–400×** on
typical hardware.

### B.6.6 Benchmark Summary

This comparison is now maintained as a documented benchmark study rather than a
default pytest module. The reproducible TSNet side-by-side script lives in
`examples/benchmark_vs_tsnet.py`, while the automated regression suite keeps the
analytical and stored-reference Joukowsky checks under `tests/`.

Both `rthym-moc` and `TSNet` reproduce the Joukowsky analytical solution to
within 0.05 %, and agree with each other within 0.175 ft RMS over the first
wave cycle.  This confirms that the C++ engine implements the Method of
Characteristics correctly at the most fundamental level.

---

## B.7 R-THYM Joukowsky Cross-Engine Verification

### B.7.1 Purpose

This section compares `rthym-moc` directly against the R-THYM web-application
JavaScript engine on an **instant valve closure** scenario that exercises
column-separation (vapor-pressure clamping) and downstream stub-pipe
resonance.  Unlike §B.6, which disabled unsteady friction for a clean
analytical comparison, this test runs both engines with their default settings
(Vardy-Brown unsteady-skin-friction enabled) and uses the R-THYM export as the
reference.

### B.7.2 Network

```
PressureBoundary_A (H = 150 ft)
  ──[Pipe_1: 3000 ft, 12 in, HW C=120]──► Valve_A (12 in TCV, elev = 125 ft)
  ──[Pipe_2: 100 ft stub, 12 in]──► PressureBoundary_B (H = 147.9 ft)
```

| Parameter | Value |
|---|---|
| Upstream reservoir head | 150 ft |
| Downstream reservoir head | 147.9 ft |
| Pipe_1 length | 3000 ft |
| Pipe_2 length (stub) | 100 ft |
| Pipe diameter | 12 in |
| Hazen-Williams C | 120 |
| Pipe material | Steel (E = 29 Mpsi, e = 0.298 in) |
| Wave speed *a* | 4052.26 ft/s |
| Initial flow Q₀ | 451.92 GPM |
| Initial velocity V₀ | 1.282 ft/s |
| Time step *dt* | 0.01 s |
| Simulation duration | 20.0 s |

**Transient event:** Valve_A closes from 100 % to 0 % in one time step
(t = 5.96 s) — effectively an instant closure.

The short downstream stub pipe (Pipe_2) creates rapid pressure reflections
(period ≈ 2 × 100/4052 ≈ 0.049 s) that interact with the vapor cavity
that forms on the downstream face of the valve upon closure.

### B.7.3 Analytical First-Step Check (Joukowsky Equation)

$$\Delta H = \frac{a \cdot V_0}{g} = \frac{4052.26 \times 1.282}{32.2} \approx 161.3 \text{ ft}$$

Pre-closure head at valve: $H_{valve} = 147.99$ ft  (gauge pressure at
elev = 125 ft: $P = (147.99 - 125) \times 0.4335 \approx 9.94$ psi).

First-step head after instant closure:
$H_{valve} + \Delta H = 147.99 + 161.3 = 309.3$ ft → gauge pressure at
elev = 125 ft:

$$P_{surge} = \frac{309.3 - 125}{2.308} \approx 79.8 \text{ psi}$$

This matches the R-THYM CSV value of **79.82 psi** at t = 5.96 s.

### B.7.4 Column Separation

When the valve closes, the downstream face of Valve_A (outlet of Pipe_1)
experiences a negative Joukowsky wave equal in magnitude to the positive
surge.  The resulting head drop:

$$H_{valve} - \Delta H = 147.99 - 161.3 = -13.3 \text{ ft}$$

falls below the vapor-pressure limit (≈ 0 ft absolute ≈ −14 psi gauge),
so both engines clamp the pressure at the vapor threshold and track a
discrete vapor cavity.  When the cavity collapses it produces a secondary
pressure spike that grows via stub-pipe resonance to a peak of ≈ 185–190 psi
at t ≈ 8.3 s.

### B.7.5 Timing Convention

`rthym-moc` advances pipe state and then records; R-THYM records and then
advances.  For an instant closure this creates a systematic one-step
(0.01 s) offset: the post-closure state appears at t = 5.97 s in `rthym-moc`
versus t = 5.96 s in R-THYM.  All post-closure comparisons apply a +dt
shift to the simulation side so that physically equivalent states are
compared.

### B.7.6 Results

#### Wave speed

| | Value |
|---|---|
| R-THYM web app | 4052.26 ft/s |
| RTHYM-MOC | 4052.26 ft/s |
| Error | 0.00 ft/s |
| Tolerance | ±5 ft/s |
| **Result** | **PASS** |

#### Pre-closure steady state

| Quantity | R-THYM | RTHYM-MOC | Error | Tolerance | Result |
|---|---:|---:|---:|---|---|
| Pipe_1 mean flow | 451.920 GPM | 451.965 GPM | +0.045 GPM | ±2 GPM | **PASS** |
| Valve_A mean head | 147.989 ft | 147.968 ft | −0.021 ft | ±0.5 ft | **PASS** |

#### Post-closure pressures at Valve_A

| Quantity | R-THYM | RTHYM-MOC | Error | Tolerance | Result |
|---|---:|---:|---:|---|---|
| First-step Joukowsky surge (t = 5.96 s) | 79.82 psi | 80.78 psi | +0.96 psi | ±2 psi | **PASS** |
| Minimum pressure (vapor clamp) | −14.00 psi | −14.00 psi | 0.00 psi | ±1 psi | **PASS** |
| Maximum pressure (cavity-collapse peak) | 185.57 psi | 189.91 psi | +4.34 psi | ±15 psi | **PASS** |

#### Time-series pressure trace

Comparison window: t = 5.96–7.44 s (first upstream wave round-trip,
2 × 3000/4052 ≈ 1.48 s).

| Metric | Value | Tolerance | Result |
|---|---:|---|---|
| Valve_A pressure RMS | 3.47 psi | ≤4.0 psi | **PASS** |

> **Note on the growing RMS.** The pressure at Valve_A rises from ~80 psi
> to ~175 psi during this window due to stub-pipe resonance and cavity
> collapse.  The two engines agree closely on the first-step surge (0.96 psi
> difference) but accumulate a ~3–4 psi systematic offset over the 1.48 s
> window because their column-separation routines handle the vapor cavity in
> the 100 ft downstream stub pipe slightly differently.  This is physically
> expected for engines with different numerical schemes.

### B.7.7 Test Summary

All 7 test cases pass.

| Test | Metric | Result |
|---|---|---|
| `test_wave_speed` | Korteweg *a* vs R-THYM web app | **PASS** |
| `test_steady_state_flow` | Pre-closure Pipe_1 flow | **PASS** |
| `test_steady_state_head_valve` | Pre-closure Valve_A head | **PASS** |
| `test_first_step_joukowsky_pressure` | Surge at t = 5.96 s | **PASS** |
| `test_minimum_pressure` | Vapor-pressure clamp | **PASS** |
| `test_maximum_pressure` | Cavity-collapse peak | **PASS** |
| `test_time_series_pressure_rms` | Post-closure trace RMS | **PASS** |

### B.7.8 Summary

`rthym-moc` reproduces the R-THYM JavaScript engine for instant valve closure
with column separation to within:

- **Wave speed:** 0.00 ft/s
- **Steady-state flow:** 0.045 GPM (< 0.01 %)
- **Steady-state head:** 0.021 ft
- **First-step Joukowsky surge:** 0.96 psi (1.2 % of surge value)
- **Vapor-pressure minimum:** 0.00 psi (exact match at clamp value)
- **Cavity-collapse peak:** 4.34 psi (2.3 % of peak)
- **Post-closure pressure trace RMS:** 3.47 psi over first wave cycle

These results confirm that `rthym-moc` correctly models instant valve closure,
column separation, and downstream stub-pipe resonance in agreement with the
R-THYM JavaScript reference engine.

---

## B.8 Open Standpipe Surge Protection

### B.8.1 Purpose

This section verifies that the `Standpipe` boundary condition in `rthym-moc`
correctly limits transient pressures following a sudden valve closure.  It
then cross-validates the RTHYM-MOC result against the independently developed
TSNet 0.2.2 MOC engine (Python, SI units) to confirm that both engines agree
on the water-column oscillation history.

### B.8.2 Network Description

#### Without surge protection (baseline)

```
PressureBoundary R1 (H = 150 ft)
  ──[P1: 3000 ft, 12 in, HW C=130]──► Junction J1
  ──[P2: 40 ft, 12 in]──► Valve V1 (TCV, instant closure)
  ──[P3: 40 ft, 12 in]──► PressureBoundary R2 (H = 147.9 ft)
```

#### With open standpipe at J1

```
PressureBoundary R1 (H = 150 ft)
  ──[P1: 3000 ft, 12 in, HW C=130]──► Standpipe SP1 (A_s = 1 ft²)
  ──[P2: 40 ft, 12 in]──► Valve V1 (TCV, instant closure)
  ──[P3: 40 ft, 12 in]──► PressureBoundary R2 (H = 147.9 ft)
```

The standpipe cross-sectional area $A_s = 1\ \text{ft}^2$ is intentionally
small so that the water column oscillation is clearly observable within a
25-second simulation.

| Parameter | Value |
|---|---|
| Upstream reservoir head | 150.00 ft |
| Pipe length (P1) | 3 000 ft |
| Pipe diameter | 12 in |
| Hazen-Williams C | 130 |
| Wave speed *a* | 4 000 ft/s |
| Initial flow Q₀ | 500 GPM |
| Standpipe area A_s | 1.00 ft² |
| Time step *dt* | 0.01 s |
| Simulation duration | 25 s |

### B.8.3 Analytical Reference

#### Steady-state head at SP1

Hazen-Williams head loss over P1:

$$h_f = \frac{10.44 \, L \, Q^{1.852}}{C^{1.852} \, D^{4.871}} = \frac{10.44 \times 3000 \times 500^{1.852}}{130^{1.852} \times 12^{4.871}} \approx 2.10\ \text{ft}$$

$$H_{SP1,ss} = 150.00 - 2.10 = 147.90\ \text{ft}$$

#### Baseline Joukowsky surge (no standpipe)

$$V_0 = \frac{Q_0}{A_{pipe}} = \frac{500 \times 0.002228}{\pi (0.5)^2} \approx 1.418\ \text{ft/s}$$

$$\Delta H = \frac{a \, V_0}{g} = \frac{4000 \times 1.418}{32.2} \approx 176.2\ \text{ft}$$

$$H_{peak,\,\text{no SP}} = 147.90 + 176.2 \approx 324.1\ \text{ft}$$

#### Open standpipe — frictionless lumped oscillation

For a standpipe of area $A_s$ at the mid-point of a pipe of area $A_p$ and
length $L$, the natural angular frequency and maximum water-surface rise are
(Wylie & Streeter, 1993, §4.7):

$$\omega = \sqrt{\frac{g \, A_p}{A_s \, L}} \quad\Rightarrow\quad \omega \approx 0.0918\ \text{rad/s},\quad T_{osc} \approx 68.4\ \text{s}$$

$$z_{max} = V_0 \sqrt{\frac{A_p \, L}{g \, A_s}} \approx 12.1\ \text{ft}$$

$$H_{peak,\,\text{analytical}} = H_{SP1,ss} + z_{max} \approx 147.90 + 12.1 = 160.0\ \text{ft}$$

### B.8.4 RTHYM-MOC Results

| Quantity | Value |
|---|---|
| Steady-state head SP1 | 147.90 ft |
| No-standpipe peak at J1 | 326.2 ft |
| Standpipe peak at SP1 | **160.78 ft** |
| Water-surface rise $z_{max}$ | 12.88 ft |
| Analytical $z_{max}$ | 12.13 ft |
| Error vs. analytical | +0.75 ft (+6.2 %) |
| Overpressure mitigation | **92.8 %** |

### B.8.5 Cross-Engine Comparison (RTHYM-MOC vs TSNet)

TSNet models the standpipe as a `SurgeTank` node at J1 with the matching
cross-sectional area (converted to SI).  The network uses a short downstream
stub pipe (P2, 24.4 m) to satisfy TSNet's requirement that the boundary node
be adjacent to a pipe rather than a valve.

| Quantity | RTHYM-MOC (SP1) | TSNet (J1) |
|---|---:|---:|
| Steady-state head | 147.90 ft | 147.95 ft |
| Peak transient head | 160.78 ft | 160.64 ft |
| Peak difference | — | 0.14 ft |

**Time-series RMS (0–20 s window):** 0.10 ft — well within the 2.5 ft
tolerance.

The two engines agree to within 0.14 ft on peak head and 0.10 ft RMS across
the 20-second comparison window, confirming that the RTHYM-MOC `Standpipe`
implementation is consistent with TSNet's `SurgeTank` boundary condition.

### B.8.6 Test Summary

Five automated test cases cover this scenario
(`tests/test_standpipe_surge_protection.py`):

| Test | Assertion | Result |
|---|---|---|
| `test_no_standpipe_joukowsky_peak` | Baseline peak ≈ 324 ft (Joukowsky, ±20 ft) | **PASS** |
| `test_standpipe_limits_pressure` | SP1 peak < 170 ft | **PASS** |
| `test_standpipe_peak_near_analytical` | SP1 peak within ±15 ft of 160.0 ft | **PASS** |
| `test_standpipe_overpressure_reduction` | Mitigation ≥ 80 % | **PASS** |

The TSNet cross-engine standpipe comparison in §B.8.5 remains documented here
as a benchmark study rather than a default pytest dependency.

### B.8.7 Summary

`rthym-moc` correctly models an open standpipe as a surge-protection device:

- **Peak pressure reduction:** 160.78 ft vs 326.2 ft baseline (92.8 % reduction).
- **Agreement with frictionless analytical oscillation theory:** peak rise
  within 6.2 % of the lumped-parameter prediction.
- **Cross-engine agreement with TSNet:** 0.14 ft peak difference, 0.10 ft
  time-series RMS over 20 s.

These results confirm that the `Standpipe` boundary condition in `rthym-moc`
is physically correct and cross-validated against an independent MOC solver.
