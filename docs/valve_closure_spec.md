# R-THYM — Valve Closure Redesign Specification

**Version**: 1.0  
**Date**: 2026-05-15  
**Prepared for**: R-THYM Dev Team  
**Context**: Coordinated with rthym_moc engine (C++/Python MOC solver)

---

## 1. Background

### 1.1 How valve closure works today

R-THYM is a real-time interactive hydraulic model. The user triggers valve closure
by clicking the **ON/OFF button** on the valve component in the canvas during a live
simulation. R-THYM records the trigger time `t_trigger` and immediately begins
applying the pre-configured actuator response — the user does **not** select a
closure profile at click time; they configure it in advance in Valve Properties.

The underlying MOC engine (`rthym_moc`) receives a `(t, pct_open)` schedule array
and linearly interpolates between breakpoints to determine the valve opening at each
time step (`dt = 0.01 s`). All four proposed closure types map to this same array.

### 1.2 Current limitation

R-THYM currently hard-codes a **geometric (equal-percentage)** closure at 75 % of
remaining opening per 0.05 s step. This is correct for equal-percentage trim control
valves but is not offered as a choice and is not visible to the user.

---

## 2. Proposed UI Changes — Valve Properties Dialog

### 2.1 Existing fields (unchanged)

| Field | Notes |
|---|---|
| Component ID | unchanged |
| Valve Type | unchanged (TCV, PRV, PSV, …) |
| Percent Open (%) | initial operating point |
| Max Open (%) | unchanged |
| Elevation (ft) | unchanged |
| Diameter (in) | unchanged |

### 2.2 New / modified fields

Add **Closure Type** as a dropdown immediately to the right of **Stroke Time**,
or on the same row as a label–dropdown pair:

```
[ Stroke Time (sec)  |_1___ ]    [ Closure Type  | Linear ▾ ]
```

**Stroke Time** is shown or hidden depending on the closure type (see §3).

Below the Stroke Time row, conditionally render additional parameter inputs
depending on the selected Closure Type.

---

## 3. Closure Types

### 3.1 Linear

**Description**: Valve closes at a constant rate from the current opening to fully
closed over the stroke time. This models motor-operated gate valves and ball valves
driven at constant actuator speed.

**Visible fields**:
- Stroke Time (sec) — total closure duration

**Hidden fields**: *(none)*

**Schedule generation** (relative to trigger, `s0` = Percent Open at trigger):

```
t_offset:  [0,          stroke_time]
pct_open:  [s0,         0.0        ]
```

**Example** (s0 = 7 %, stroke_time = 1.0 s):
```
t=0.00 → 7.00 %
t=1.00 → 0.00 %
```

---

### 3.2 Equal-Percentage (EP)

**Description**: Each closure step removes a fixed *fraction* of the remaining
opening (geometric series). Models control valves with equal-percentage trim running
at constant actuator speed. This is R-THYM's current behaviour.

**Visible fields**:
- Stroke Time (sec) — total closure duration (= N × step interval)
- Step Interval (sec) — time between steps; default **0.05 s**

*(Reduction ratio per step is derived automatically — see below.)*

**Hidden fields**: *(none)*

**Derivation**:

```
N     = round(stroke_time / step_interval)   # number of steps
ratio = (pct_min / s0) ^ (1 / (N - 1))      # pct_min ≈ 0.05 % (one step before 0)
```

In practice the final step always jumps straight to 0 regardless of ratio, so
`ratio` only needs to produce a smooth geometric decay toward near-zero.

**Schedule generation**:

```python
steps = [s0 * ratio**i for i in range(N)]   # geometric series
steps.append(0.0)                            # final step: fully closed
t_offsets = [i * step_interval for i in range(N + 1)]
```

**Example** (s0 = 7 %, stroke_time = 0.35 s, step_interval = 0.05 s → N = 7):
```
t=0.00 → 7.000 %
t=0.05 → 5.250 %
t=0.10 → 3.938 %
t=0.15 → 2.953 %
t=0.20 → 2.215 %
t=0.25 → 1.661 %
t=0.30 → 1.246 %
t=0.35 → 0.000 %
```

---

### 3.3 Two-Stage

**Description**: A programmed actuator changes closure rate at a pre-set transition
opening. Used for surge protection: Stage 1 closes quickly from the initial opening
to a transition point (low-risk portion); Stage 2 closes slowly from the transition
point to fully closed (high-risk portion near zero flow).

**Key design rule**: Stage 2 time should satisfy:

```
T_stage2 ≥ 2 × L_upstream / a
```

where `L_upstream` is the length of the pipe immediately upstream of the valve and
`a` is the wave speed. This allows the Joukowsky wave to travel to the nearest
boundary and return before closure completes, reducing peak pressure.

**Stroke Time field**: **hidden** (total time is derived: Stage 1 + Stage 2).

**Replace Stroke Time row with**:

```
[ Transition Point (%)  |_15__ ]
[ Stage 1 Time (sec)    |_3.0_ ]    (fast: initial open → transition)
[ Stage 2 Time (sec)    |_30.0 ]    (slow: transition → fully closed)
```

**Schedule generation**:

```
t_offset:  [0,             stage1_time,             stage1_time + stage2_time]
pct_open:  [s0,            transition_pct,           0.0                      ]
```

**Example** (s0 = 7 %, transition = 3 %, stage1 = 0.5 s, stage2 = 2.0 s):
```
t=0.00 → 7.00 %   (trigger)
t=0.50 → 3.00 %   (transition: Stage 1 complete)
t=2.50 → 0.00 %   (Stage 2 complete)
```

---

### 3.4 Custom

**Description**: User enters an arbitrary piecewise-linear closure profile as a
table of (time offset, % open) pairs. Time offsets are relative to the trigger
moment (t_offset = 0 = click time). Intended for importing actuator data sheets or
field-measured closure curves.

**Stroke Time field**: **hidden** (defined by the last row of the table).

**Replace Stroke Time row with** an expandable table:

| Time offset (s) | % Open |
|---|---|
| 0.00 | 7.0 |
| 0.20 | 5.0 |
| 0.80 | 1.0 |
| 1.50 | 0.0 |
| *+ Add row* | |

**Validation rules**:
1. First row must have `t_offset = 0` and `pct_open = current Percent Open`
   (auto-populated, read-only).
2. Last row must have `pct_open = 0.0`.
3. `t_offset` values must be strictly increasing.
4. `pct_open` values must be non-increasing.
5. Minimum 2 rows.

---

## 4. Stroke Time Field Behaviour Summary

| Closure Type | Stroke Time field | Replacement inputs |
|---|---|---|
| Linear | **Shown** — "Stroke Time (sec)" | *(none)* |
| Equal-Percentage | **Shown** — "Stroke Time (sec)" | Step Interval (sec) |
| Two-Stage | **Hidden** | Transition Point (%), Stage 1 Time (sec), Stage 2 Time (sec) |
| Custom | **Hidden** | Editable (t, pct) table |

---

## 5. JSON Export Format (`valveSchedules`)

The existing `valveSchedules` export format is preserved. R-THYM converts the
configured closure profile to an absolute-time `(t, pct)` array at the moment the
trigger fires:

```json
"valveSchedules": {
  "Valve_A": [
    { "t": 0,    "pct": 7 },
    { "t": 4.26, "pct": 5.25  },
    { "t": 4.31, "pct": 3.938 },
    ...
    { "t": 4.61, "pct": 0 }
  ]
},
"closureProfiles": {
  "Valve_A": {
    "type": "equal_percentage",
    "strokeTime": 0.35,
    "stepInterval": 0.05
  }
}
```

**Add a new `closureProfiles` key** alongside `valveSchedules` so rthym_moc
(and future analysis tools) can reconstruct the intent without reverse-engineering
the schedule table. Fields per type:

| Type key | Fields |
|---|---|
| `"linear"` | `strokeTime` |
| `"equal_percentage"` | `strokeTime`, `stepInterval` |
| `"two_stage"` | `transitionPct`, `stage1Time`, `stage2Time` |
| `"custom"` | `table: [{t_offset, pct}, …]` |

---

## 6. rthym_moc Integration

All four closure types are fully supported by `rthym_moc.MOCSolver.set_valve_schedule()`
without any engine changes. The schedule array generated by R-THYM is passed directly:

```python
solver.set_valve_schedule("_VALVE_Valve_A", [(t, pct), ...])
```

The rthym_moc package will expose schedule generator utilities (matching this spec)
so R-THYM's backend and rthym_moc test scripts stay in sync:

```python
from rthym_moc.schedules import (
    valve_schedule_linear,
    valve_schedule_equal_pct,
    valve_schedule_two_stage,
)

sched = valve_schedule_two_stage(
    t_trigger      = 4.26,    # absolute simulation time of click
    s0             = 7.0,     # % open at trigger
    transition_pct = 3.0,
    stage1_time    = 0.5,
    stage2_time    = 2.0,
    dt             = 0.01,    # MOC time step (for step-snap rounding)
)
solver.set_valve_schedule("_VALVE_Valve_A", sched)
```

**Stub length note for the rthym_moc `load_inp` call**: when loading an EPANET
`.inp` that contains a valve with a known closure profile, pass `stub_length_ft`
computed from the fastest closure time to avoid pressure attenuation:

```python
stub_length_ft = max(800.0, math.ceil(a * T_close_min / 2 / dx) * dx)
solver = rthym_moc.load_inp("network.inp", stub_length_ft=stub_length_ft)
```

---

## 7. Acceptance Criteria

| # | Criterion |
|---|---|
| 1 | Valve Properties dialog shows Closure Type dropdown for all TCV valves |
| 2 | Selecting each type shows/hides the correct parameter fields per §4 |
| 3 | Generated schedule matches the formulas in §3 to within one `dt` step |
| 4 | `valveSchedules` export is unchanged in structure; `closureProfiles` key is added |
| 5 | `triggerFired: true` and `t_trigger` are present in exported JSON |
| 6 | rthym_moc `set_valve_schedule()` fed the exported array produces ≤ 1 % peak pressure error vs R-THYM for Linear and EP types |
| 7 | Two-Stage: peak pressure is measurably lower than single-stage closure at equivalent total stroke time when Stage 2 time ≥ 2L/a |
| 8 | Custom table validates per §3.4 rules; invalid input blocked with inline error message |
