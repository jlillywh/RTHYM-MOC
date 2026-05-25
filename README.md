# RTHYM-MOC

[![Tests](https://github.com/jlillywh/RTHYM-MOC/actions/workflows/tests.yml/badge.svg)](https://github.com/jlillywh/RTHYM-MOC/actions/workflows/tests.yml)
[![Coverage](https://codecov.io/gh/jlillywh/RTHYM-MOC/branch/main/graph/badge.svg)](https://codecov.io/gh/jlillywh/RTHYM-MOC)
[![Launch Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/jlillywh/RTHYM-MOC/main?labpath=examples%2Fquickstart_notebook.ipynb)

A high-performance 1-D Method of Characteristics (MOC) transient hydraulic solver with a C++17 core and a Python API via PyBind11.  Originally developed as the engine behind the [R-THYM](https://lillywhitewater.com/products/r-thym/) web application, it is released here as a standalone, open-source library suitable for research scripting, parametric studies, and automated validation pipelines.

## Contents

- [Overview](#overview)
- [Installation](#installation)
- [Quickstart](#quickstart)
- [Testing](#testing)
- [Examples](#examples)
- [API Reference](#api-reference)
  - [NodeInput](#nodeinput)
  - [PipeInput](#pipeinput)
  - [MOCSolver](#mocsolver)
  - [Results dictionary](#results-dictionary)
- [Unit conventions](#unit-conventions)
- [Valve model](#valve-model)
- [Valve closure types](#valve-closure-types)
- [Surge control components](#surge-control-components)
- [Scripted multi-event transients](#scripted-multi-event-transients)
- [Loading from EPANET (.inp)](#loading-from-epanet-inp)
- [Numerical method](#numerical-method)
- [Validation](#validation)
- [Benchmarking](#benchmarking)
- [Repository layout](#repository-layout)
- [Dependencies](#dependencies)

---

## Overview

RTHYM-MOC solves the 1-D water-hammer equations using the Method of Characteristics with a fixed Courant number of 1.

### Key characteristics:

- **Network-capable**: arbitrary topologies of pipes, junctions, reservoirs, air valves, valves, pumps, standpipe surge tanks, hydropneumatic tanks, and turbines.
- **Time-varying events**: valve schedules, pump trip/start, demand changes — specified either as discrete step changes between `run()` calls or as continuous piecewise-linear schedules registered before `run()`.
- **Cavitation detection**: integrates a column-separation flag (pressure < vapour pressure) at each node.
- **Fast**: on the standard Joukowsky case, the C++ core is roughly **200–400× faster** than [TSNet](https://github.com/glorialulu/TSNet) (pure Python) on typical hardware — see [Benchmarking](#benchmarking).
- **Validated**: automated regressions against R-THYM exports, EPANET/wntr steady state, and analytical checks — Joukowsky first-step error < 0.05 %, wave period error < 0.2 % — see [Validation](#validation).

---

## Installation

### Requirements

| Component | Minimum version |
|-----------|----------------|
| Python    | 3.9            |
| NumPy     | 1.21           |
| pybind11  | 2.11           |
| C++ compiler | C++17 (GCC 9+, Clang 10+, MSVC 2019+) |
| CMake     | 3.15           |

### Build and install

```bash
pip install pybind11          # provides CMake integration
pip install --no-build-isolation -e .
```

This compiles the C++ extension `_rthym_moc` and installs the `rthym_moc` Python package in editable mode.  No additional runtime dependencies are needed beyond NumPy.

To build the standalone C++ unit-test binary:

```bash
cmake -B build -DBUILD_TESTS=ON
cmake --build build
./build/moc_test
```

---

## Quickstart

> [!TIP]
> You can run the quickstart and visual valve-closure verification interactively in your browser via Binder:
> [![Launch Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/jlillywh/RTHYM-MOC/main?labpath=examples%2Fquickstart_notebook.ipynb)

```python
import numpy as np
import rthym_moc

# ── 1. Build network topology ─────────────────────────────────────────────────
solver = rthym_moc.MOCSolver()

# Upstream constant-head reservoir
solver.add_node(rthym_moc.NodeInput(
    id="R1", type="PressureBoundary",
    elevation=0.0, head=150.0          # ft HGL
))

# Inline valve (fully open at t=0, will be slammed shut)
solver.add_node(rthym_moc.NodeInput(
    id="V1", type="Valve",
    elevation=0.0, diameter=12.0,      # inches
    current_setting=0.0                # % open (0 = slammed shut at t=0)
))

# Downstream reservoir
solver.add_node(rthym_moc.NodeInput(
    id="R2", type="PressureBoundary",
    elevation=0.0, head=0.0
))

# Pipe: 3000 ft, 12-inch diameter, Hazen-Williams C = 130
solver.add_pipe(rthym_moc.PipeInput(
    id="P1",
    from_node="R1", to_node="V1",
    length=3000.0, diameter=12.0,
    roughness=130.0, flow_gpm=500.0    # initial steady-state flow
))
solver.add_pipe(rthym_moc.PipeInput(
    id="P2",
    from_node="V1", to_node="R2",
    length=100.0, diameter=12.0,
    roughness=130.0, flow_gpm=500.0
))

# ── 2. Run transient simulation ───────────────────────────────────────────────
results = solver.run(
    total_time=4.0,    # seconds
    dt=0.01,           # time step (seconds)
    p_vapor=-14.0,     # vapour pressure threshold (psi; negative = below atm)
    usf_tau=0.5        # unsteady-friction relaxation time constant (s)
)

# ── 3. Extract results ────────────────────────────────────────────────────────
t      = np.array(results["time"])          # shape (N,)  seconds
H_V1   = np.array(results["node_head"]["V1"])      # ft
P_V1   = np.array(results["node_pressure"]["V1"])  # psi
Q_P1   = np.array(results["pipe_flow_gpm"]["P1"])  # GPM

print(f"Joukowsky peak at V1: {H_V1.max():.1f} ft  at t = {t[H_V1.argmax()]:.3f} s")
```

---

## Testing

Run the automated test suite from the repository root:

```bash
pytest -q
```

If you have changed the C++ core under `src/`, rebuild the extension before rerunning tests:

```bash
python3 setup.py build_ext --inplace
pytest -q
```

To run the CI-aligned package quality checks locally:

```bash
ruff check rthym_moc
mypy rthym_moc
```

If you install the development extras, you can also run the configured pre-commit hooks:

```bash
pip install -e '.[dev,inp]'
pre-commit run --all-files
```

---

## Examples

The repository includes runnable script examples under `examples/`, including
`basic_example.py`, `load_from_inp.py`, and `benchmark_vs_tsnet.py` (TSNet
speed comparison; see [Benchmarking](#benchmarking)).

For an interactive walkthrough focused on reproducibility and deterministic
solver behavior, see `examples/quickstart_notebook.ipynb`.

Students and first-time users can launch that notebook in a browser via Binder
without installing Jupyter locally:

[![Launch Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/jlillywh/RTHYM-MOC/main?labpath=examples%2Fquickstart_notebook.ipynb)

The first Binder launch can take a few minutes while the environment builds the
compiled extension. After it opens, users can run the notebook directly in
JupyterLab.

## Contributing

Contributions are welcome for solver behavior, validation coverage,
performance benchmarks, documentation, examples, and packaging improvements.

If you want to contribute, start with `CONTRIBUTING.md` for local setup,
validation commands, and pull request expectations. `MAINTENANCE.md` documents
the current review/refactor cadence. Bug reports are most useful when they
include a minimal reproducible network or input file plus the exact commands
and environment used to reproduce the issue.

---

## API Reference

### NodeInput

Describes a single network node.  All fields have defaults; only `id` and `type` are strictly required.

```python
node = rthym_moc.NodeInput()
node.id               = "J1"          # str — unique identifier
node.type             = "Junction"    # str — see table below
node.elevation        = 0.0           # ft above datum
node.head             = 100.0         # ft HGL  (Tank, PressureBoundary)
node.level            = 100.0         # % full  (Tank, derived/legacy compatibility)
node.max_level        = 20.0          # ft depth at 100 % full (Tank)
node.demand           = 0.0           # GPM withdrawal (Junction, OutflowNode)
node.current_setting  = 100.0         # % open (Valve, Turbine; 100 = fully open)
node.diameter         = 8.0           # inches (Valve orifice / Turbine runner)
node.current_speed    = 100.0         # % rated speed (Pump)
node.design_head      = 50.0          # ft at BEP (Pump)
node.design_flow      = 100.0         # GPM at BEP (Pump)
node.design_velocity  = 0.0           # ft/s (Turbine; derived from design_flow if 0)
node.air_release_head = 0.0           # ft vent reference above elevation (AirValve)
node.air_release_diameter = 0.25      # inches (AirValve small-orifice release port)
node.tank_area        = 10.0          # ft² cross-sectional area (Standpipe)
node.gas_volume       = 10.0          # ft³ initial trapped gas / air-pocket volume
node.tank_volume      = 30.0          # ft³ total vessel or chamber volume
node.polytropic_n     = 1.2           # polytropic exponent (1.0 = isothermal, 1.4 = adiabatic)
node.loss_coeff_in    = 0.7           # C_d orifice coefficient for inflow / air admission
node.loss_coeff_out   = 0.7           # C_d orifice coefficient for outflow / air release
```

**Node types**

| `type` string | Boundary condition | Key fields |
|---|---|---|
| `"Junction"` | Kirchhoff continuity (demand sink) | `demand` |
| `"OutflowNode"` | As Junction, sign convention explicit | `demand` |
| `"InflowNode"` | Injects flow (demand treated as negative) | `demand` |
| `"PressureBoundary"` | Fixed total head at all times | `head` |
| `"Tank"` | Fixed HGL; `head` is authoritative, `level` is compatibility state | `head`, `level`, `max_level` |
| `"CheckValve"` | Ideal inline one-way valve; forward flow only, reverse flow clamps shut | `diameter` |
| "AirValve" | Air-pocket valve with large admission port and small release port | `elevation`, `head`, `diameter`, `air_release_diameter`, `gas_volume`, `tank_volume`, `loss_coeff_in`, `loss_coeff_out`, `air_release_head` |

For `"Tank"`, prefer setting `head` directly. The `level` field is retained for
compatibility with older code paths and is derived from `head` and `max_level`
when EPANET networks are imported.
| `"Valve"` | Quadratic loss, $K = (100/s)^2 - 1$ | `current_setting`, `diameter` |
| `"Turbine"` | Quadratic loss (design-curve K) | `current_setting`, `design_velocity`, `diameter` |
| `"Pump"` | Three-coefficient affinity curve | `current_speed`, `design_head`, `design_flow` |
| `"Standpipe"` | Open free-surface surge tank (level tracked each step) | `head`, `tank_area` |
| `"HydropneumaticTank"` | Closed pressurised vessel; gas follows polytropic law | `head`, `diameter`, `gas_volume`, `tank_volume`, `polytropic_n`, `loss_coeff_in`, `loss_coeff_out` |

A dead-end boundary — equivalent to an instantaneously closed valve — is modelled as a `"Junction"` with `demand = 0` and no outflow pipe attached.  The MOC boundary condition then enforces $Q = 0$ exactly, giving $H = C^+$.

### PipeInput

Describes a single pipe segment connecting two nodes.

```python
pipe = rthym_moc.PipeInput()
pipe.id             = "P1"     # str — unique identifier
pipe.from_node      = "R1"     # str — upstream node id
pipe.to_node        = "J1"     # str — downstream node id
pipe.length         = 3000.0   # ft
pipe.diameter       = 12.0     # inches
pipe.roughness      = 120.0    # Hazen-Williams C (higher = smoother)
pipe.minor_loss     = 0.0      # dimensionless local-loss coefficient K
pipe.flow_gpm       = 500.0    # GPM, initial steady-state flow (+ = from→to)
pipe.wall_thickness = 0.25     # inches (used only if youngs_modulus > 0)
pipe.youngs_modulus = 0.0      # psi (0 = rigid pipe, default wave speed ~4000 ft/s)
pipe.poissons_ratio = 0.3      # (used only if youngs_modulus > 0)
```

`pipe.minor_loss` is a dimensionless local-loss coefficient $K$ for bends,
tees, fittings, entrance/exit losses, or any other concentrated resistance you
want associated with that pipe. During initialisation, the solver includes this
term in the steady headloss,

$$H_{f,minor} = K \frac{V^2}{2g}$$

and during the transient it is applied as an added resistance contribution
distributed across the pipe segments. That distribution is a practical MOC
approximation of a lumped local loss, and the test suite now includes explicit
benchmarks against an equivalent lumped-loss case.

**Wave speed** is computed internally from the Korteweg–Joukowsky elastic formula when `youngs_modulus > 0`:

$$a = \sqrt{\frac{K_f/\rho}{1 + (K_f D)/(E\,e)}}$$

where $K_f$ is the bulk modulus of water, $E$ is `youngs_modulus`, $D$ is the pipe diameter, and $e$ is `wall_thickness`.  When `youngs_modulus = 0`, a rigid-pipe wave speed of 4720 ft/s is used as the starting point before Courant adjustment.

The solver automatically adjusts the wave speed so that $a_\text{adj} = L / (N_\text{segs} \cdot dt)$ exactly (Courant = 1), where $N_\text{segs} = \text{round}(L / (a \cdot dt))$.

### MOCSolver

```python
solver = rthym_moc.MOCSolver()
```

| Method | Description |
|--------|-------------|
| `solver.add_node(node)` | Append a `NodeInput` to the network. |
| `solver.add_pipe(pipe)` | Append a `PipeInput` to the network. |
| `solver.clear()` | Remove all nodes, pipes, and schedules. |
| `solver.add_control_rule(rule)` | Register a dynamic operational control rule. |
| `solver.clear_control_rules()` | Clear all registered control rules. |
| `solver.get_node_head(id)` | Query the current piezometric HGL head (ft) of a node. |
| `solver.get_node_pressure(id)` | Query the current gauge pressure (psi) of a node. |
| `solver.set_valve_setting(id, pct_open)` | Change a valve's opening immediately (used between `run()` calls). |
| `solver.set_pump_speed(id, pct_speed)` | Change a pump speed immediately. |
| `solver.set_node_demand(id, demand_gpm)` | Change a junction demand immediately. |
| `solver.set_valve_schedule(id, schedule)` | Register a time-varying valve schedule (see below). |
| `solver.set_pump_schedule(id, schedule)` | Register a time-varying pump-speed schedule. |
| `solver.set_demand_schedule(id, schedule)` | Register a time-varying junction demand schedule. |
| `solver.set_head_schedule(id, schedule)` | Register a time-varying fixed-head schedule for a `PressureBoundary` or `Tank`. |
| `solver.run(total_time, dt, p_vapor, usf_tau)` | Execute the transient and return results. |

#### `run()` parameters

```python
results = solver.run(
    total_time = 10.0,    # float, seconds — simulation duration
    dt         = 0.01,    # float, seconds — time step
    p_vapor    = -14.0,   # float, psi     — vapour pressure (negative = subatmospheric)
    usf_tau    = 0.5,     # float, seconds — unsteady-friction IIR time constant
                          #   set to dt to disable unsteady friction entirely
)
```

Each call to `run()` rebuilds the MOC grid from the steady-state initial conditions stored in the `NodeInput` / `PipeInput` objects.  Node and pipe inputs persist across calls; call `set_valve_setting()` etc. *before* the next `run()` to change initial conditions for the next segment.

### Results dictionary

`run()` returns a Python `dict` whose values are NumPy arrays (zero-copy where possible):

```python
t           = np.array(results["time"])                     # (N,) float64, seconds
H_node      = np.array(results["node_head"]["NODE_ID"])     # (N,) float64, ft
P_node      = np.array(results["node_pressure"]["NODE_ID"]) # (N,) float64, psi
Q_pipe      = np.array(results["pipe_flow_gpm"]["PIPE_ID"]) # (N,) float64, GPM
cav_flag    = np.array(results["node_cavitation"]["NODE_ID"])# (N,) int32, 0 or 1
```

Every node and every pipe that was added to the solver has a corresponding key in the respective sub-dictionary.  `node_head` records the hydraulic grade line (HGL) at each node.  `node_cavitation` is 1 for any time step at which the computed pressure fell below `p_vapor`.

---

## Unit conventions

All quantities at the API boundary use US customary units:

| Quantity | Unit |
|----------|------|
| Heads, elevations, lengths | ft |
| Pressures | psi |
| Flows | GPM (US gallons per minute) |
| Pipe diameter, wall thickness | inches |
| Wave speed | ft/s |
| Time | s |
| Valve / pump settings | % (0 – 100) |

Two conversion constants are exported for convenience:

```python
rthym_moc.GPM_TO_CFS   # = 0.002228  (multiply GPM to get ft³/s)
rthym_moc.G_FT_S2      # = 32.2      (ft/s²)
```

---

## Valve model

The solver uses a quadratic loss model:

$$K(s) = \left(\frac{100}{s}\right)^2 - 1, \qquad s \in (0, 100]$$

where $s$ is the valve opening in percent.  This is consistent with a generic butterfly/globe valve where the discharge coefficient scales as $C_d \propto s/100$.  The minimum clamp is $s = 10^{-6}$%, giving $K \approx 10^{16}$ (effectively zero flow).

**Important implication for gradual-closure studies.**  Because $K$ grows as $1/s^2$, the valve does not significantly restrict flow until $s$ approaches a critical value

$$s_\text{crit} = \frac{100}{\sqrt{K_\text{pipe}+1}}$$

where $K_\text{pipe} = H_f / (V_0^2/2g)$ is the pipe's equivalent loss coefficient at the initial steady-state flow.  The *effective closure time*

$$T_\text{eff} \approx \frac{T_c}{\sqrt{K_\text{pipe}+1}}$$

is the interval during which most of the flow stoppage actually occurs.  A linear setting schedule satisfies the Joukowsky criterion ($\Delta H = aV_0/g$) whenever $T_\text{eff} < 2L/a$, regardless of the nominal stroke time $T_c$.

---

## Valve closure types

Four closure profiles are supported.  All are passed to the solver via `set_valve_schedule()` as a `list[tuple[float, float]]` of `(time_s, pct_open)` pairs.  The solver linearly interpolates between breakpoints at each time step; any time beyond the last point holds the final value.

| Type | Description | Required parameters |
|---|---|---|
| Linear | Constant-rate closure over a stroke time | `stroke_time` |
| Equal-Percentage | Geometric-series decay; each step removes a fixed fraction of remaining opening | `stroke_time`, `step_interval` |
| Two-Stage | Fast stage to a transition point, then slow stage to zero | `transition_pct`, `stage1_time`, `stage2_time` |
| Custom | Arbitrary piecewise-linear profile from a user-supplied `(t_offset, pct_open)` table | user-supplied table |

### Linear

Valve closes at a constant rate from the initial opening to fully closed over the stroke time.  Models motor-operated gate valves and ball valves driven at constant actuator speed.

```python
import numpy as np

s0, T_c, dt = 100.0, 3.0, 0.01
t_vals   = np.arange(0.0, T_c + dt, dt)
pct_open = np.clip(s0 * (1.0 - t_vals / T_c), 0.0, s0)
solver.set_valve_schedule("V1", list(zip(t_vals.tolist(), pct_open.tolist())))
```

### Equal-Percentage

Each closure step removes a fixed *fraction* of the remaining opening (geometric series).  Models equal-percentage trim control valves running at constant actuator speed.

```python
s0, stroke_time, step_interval = 100.0, 2.0, 0.05
N     = round(stroke_time / step_interval)
ratio = (0.05 / s0) ** (1.0 / (N - 1))      # geometric decay toward near-zero
steps     = [s0 * ratio**i for i in range(N)] + [0.0]
t_offsets = [i * step_interval for i in range(N + 1)]
solver.set_valve_schedule("V1", list(zip(t_offsets, steps)))
```

### Two-Stage

A programmed actuator changes its closure rate at a pre-set *transition opening*.  Stage 1 closes quickly from the initial opening to the transition point; Stage 2 closes slowly from the transition point to fully closed.

**Key design rule**: Stage 2 time should satisfy $T_{\text{stage2}} \geq 2L/a$ so that the Joukowsky wave returns before closure completes, reducing the peak pressure rise.

```python
s0, trans_pct = 100.0, 15.0
stage1_time, stage2_time = 3.0, 30.0        # stage2 >= 2L/a recommended
schedule = [
    (0.0,                           s0),
    (stage1_time,                   trans_pct),
    (stage1_time + stage2_time,     0.0),
]
solver.set_valve_schedule("V1", schedule)
```

### Custom

User-supplied arbitrary piecewise-linear closure profile.  Intended for importing actuator data sheets or field-measured closure curves.  Time values are absolute simulation times.

```python
schedule = [
    (0.00, 100.0),
    (0.20,  50.0),
    (0.80,  10.0),
    (1.50,   0.0),
]
solver.set_valve_schedule("V1", schedule)
results = solver.run(total_time=5.0, dt=0.01)
```

## Operational Controls & Event Logic

In addition to static time-varying schedules, the solver supports active, state-based operational controls evaluated at each time step ($dt$) inside the core engine. This allows simulating realistic system responses to dynamic transient events (e.g., pressure-relief valve opening, tank level control, variable speed pump modulation).

Control rules are registered using `ControlRuleInput` and added via `solver.add_control_rule()`.

### Control Types

The solver supports four control strategies (`rthym_moc.ControlType`):

1. **Threshold**: Switches a pump's speed or a valve's opening to a `target` value when a monitored quantity (pressure, head, level, or flow) crosses a `threshold` (with `"lt"` or `"gt"` conditions).
2. **Deadband**: Maintains a level or pressure within a range (`[threshold, threshold + deadband]`) using `"fill"` or `"drain"` logic, switching a controlled pump/valve ON ($100\%$) or OFF ($0\%$).
3. **PID**: Continuously modulates a pump's speed or valve's open percentage using a proportional-integral-derivative feedback loop. Includes bumpless transfer initialization and anti-windup clamping.
4. **PCV (Pump Control Valve)**: Interlocks a pump and its discharge control valve (ramping the valve open over `threshold` seconds when the pump starts; ramping the valve closed over `deadband` seconds when the pump stops while keeping the pump running, and finally shutting the pump off when the valve is fully closed).

### Example Configurations

#### 1. Threshold Control (Slam Valve Closed on High Pressure)
```python
rule = rthym_moc.ControlRuleInput()
rule.id = "valve_safety"
rule.type = rthym_moc.ControlType.Threshold
rule.monitored_node = "J1"
rule.controlled_node = "V1"
rule.monitored_quantity = "pressure"
rule.condition = "gt"
rule.threshold = 45.0  # psi
rule.target = 0.0      # slam shut (0% open)

solver.add_control_rule(rule)
```

#### 2. Deadband Control (Pump Fill Cycle on Tank Level)
```python
rule = rthym_moc.ControlRuleInput()
rule.id = "tank_fill"
rule.type = rthym_moc.ControlType.Deadband
rule.monitored_node = "T1"
rule.controlled_node = "Pmp1"
rule.monitored_quantity = "level"
rule.threshold = 40.0  # low limit (40% full)
rule.deadband = 20.0   # range (high limit = 40 + 20 = 60% full)
rule.action = "fill"   # start pump on low limit, stop on high limit

solver.add_control_rule(rule)
```

#### 3. PID Control (Variable Speed Pump Regulating Pressure)
```python
rule = rthym_moc.ControlRuleInput()
rule.id = "pressure_reg"
rule.type = rthym_moc.ControlType.PID
rule.monitored_node = "J2"
rule.controlled_node = "Pmp2"
rule.monitored_quantity = "pressure"
rule.target = 30.0     # target setpoint (30.0 psi)
rule.kp = 2.0
rule.ki = 1.0
rule.kd = 0.1

solver.add_control_rule(rule)
```

#### 4. PCV Sequencing (Pump & Valve Interlock)
```python
rule = rthym_moc.ControlRuleInput()
rule.id = "pump_valve_seq"
rule.type = rthym_moc.ControlType.PCV
rule.monitored_node = "Pmp1"   # pump to monitor
rule.controlled_node = "V1"    # control valve to sequence
rule.threshold = 10.0          # open ramp time (seconds)
rule.deadband = 15.0           # close ramp time (seconds)

solver.add_control_rule(rule)
```

---

## Surge control components

Three passive devices are available for transient pressure protection.

### AirValve (air-admission / air-release valve)

An `AirValve` behaves like a normal closed vent while the local piezometric head
stays positive and no trapped pocket is present. If a transient pulls the node
toward subatmospheric pressure, the valve admits air through a large orifice,
creating an air pocket. When the system repressurises, that pocket compresses
and is released gradually through a smaller discharge port, which lets the model
capture delayed venting and restart overshoot from trapped air.

This is not a binary atmospheric clamp. The current model tracks:

- a finite admission port using `diameter`
- a finite release port using `air_release_diameter`
- a local air-pocket / chamber volume using `gas_volume` and `tank_volume`
- asymmetric admission and release coefficients using `loss_coeff_in` and `loss_coeff_out`
- an optional vent datum offset using `air_release_head`

That makes the `AirValve` suitable for cases where vacuum protection, trapped-air
compression, and delayed re-venting materially affect the transient response.

```python
av = rthym_moc.NodeInput()
av.id               = "AV1"
av.type             = "AirValve"
av.elevation        = 0.0
av.head             = 160.0   # ft — steady-state pipeline head at the vent node
av.diameter         = 6.0     # inches — large admission port
av.air_release_diameter = 0.25  # inches — small release port
av.gas_volume       = 0.05    # ft³ — initial trapped air pocket (usually small)
av.tank_volume      = 2.0     # ft³ — local valve-body / riser chamber volume
av.loss_coeff_in    = 0.8     # admission discharge coefficient
av.loss_coeff_out   = 0.7     # release discharge coefficient
av.air_release_head = 0.0     # ft vent reference above elevation
solver.add_node(av)
```

The current model includes:

- finite large-orifice air admission
- finite small-orifice air release
- trapped-air compression and delayed venting using an isothermal ideal-gas surrogate

It does not yet include choked compressible airflow, float mechanics, or a more
detailed thermodynamic air-mass model.

### Standpipe (open surge tank)

An open-topped standpipe connected to the pipeline.  When a pressure wave arrives, water rises or falls inside the standpipe rather than propagating as a waterhammer spike, limiting peak pressures.

```python
st = rthym_moc.NodeInput()
st.id        = "ST1"
st.type      = "Standpipe"
st.elevation = 0.0
st.head      = 100.0         # ft — initial water-surface elevation (ft HGL)
st.tank_area = 5.0           # ft² — cross-sectional area of the standpipe
solver.add_node(st)
```

The water level is updated each time step using the standpipe continuity equation:

$$z^{n+1} = z^n + \frac{Q_\text{in} \, \Delta t}{A_s}$$

where $Q_\text{in}$ is the net inflow from the attached pipe and $A_s$ is `tank_area`.

**Design guidance**: larger `tank_area` produces a smaller maximum water-level swing ($z_\text{max} = V_0 \sqrt{A_p L / (g A_s)}$).  Place the standpipe at or near the pump discharge to protect against pump-trip low-pressure transients.

### HydropneumaticTank (closed pressurised vessel)

A sealed vessel containing a cushion of compressed air above the water column.  As the pipeline pressure fluctuates, water enters or leaves through an orifice and the gas volume changes according to the polytropic law:

$$P_g V_g^n = C \quad (n = 1.0 \text{ isothermal} \cdots 1.4 \text{ adiabatic; default } 1.2)$$

The gas constant $C$ is computed automatically at startup from `head` and `gas_volume`:

$$C = (H_0 - z_\text{elev} + 33.9) \cdot V_{g,0}^n$$

where 33.9 ft corresponds to 1 atm of absolute pressure head.

```python
hpt = rthym_moc.NodeInput()
hpt.id             = "HPT1"
hpt.type           = "HydropneumaticTank"
hpt.elevation      = 0.0
hpt.head           = 120.0    # ft — steady-state pipeline head at connection
hpt.diameter       = 4.0      # inches — connection orifice diameter
hpt.gas_volume     = 10.0     # ft³ — initial trapped gas volume
hpt.tank_volume    = 30.0     # ft³ — total vessel volume (gas + water)
hpt.polytropic_n   = 1.2      # 1.0 = isothermal, 1.4 = adiabatic (default 1.2)
hpt.loss_coeff_in  = 0.7      # C_d for inflow (water entering, gas compresses)
hpt.loss_coeff_out = 0.7      # C_d for outflow (water leaving, gas expands)
solver.add_node(hpt)
```

**Design guidance**: pre-charge the vessel so that `gas_volume / tank_volume` ≈ 0.33–0.50 at the steady-state operating pressure.  Separate `loss_coeff_in` and `loss_coeff_out` values allow modelling of a throttle or riser dip tube that damps re-filling surges more aggressively than the initial discharge.

---

## Scripted multi-event transients

`run()` resets the MOC grid to the steady-state initial conditions each call, so multi-event sequences are best handled with schedules covering the full duration, or by rebuilding `NodeInput` objects between calls:

```python
# Example: valve closes at t=1 s while a downstream demand increases at t=2 s
import numpy as np

# Build schedules covering the full 5-second window
t_close  = np.array([0.0, 1.0, 1.01, 5.0])
s_close  = np.array([100.0, 100.0, 0.0, 0.0])
solver.set_valve_schedule("V1", list(zip(t_close, s_close)))

demand_times = np.array([0.0, 2.0, 2.01, 5.0])
demand_vals  = np.array([500.0, 500.0, 700.0, 700.0])
solver.set_demand_schedule("J1", list(zip(demand_times, demand_vals)))

results = solver.run(total_time=5.0, dt=0.01)
```

To step a pump or boundary condition between separate `run()` calls, continue using `set_pump_speed()`, `set_node_demand()`, or direct `NodeInput.head` changes before the next `run()`. Each new `run()` call re-initialises from the stored steady-state values rather than the final state of the previous transient.

---

## Loading from EPANET (.inp)

Existing EPANET network files can be imported directly with `rthym_moc.load_inp()`.  The function parses the network topology and — when [wntr](https://wntr.readthedocs.io) is installed — runs a single-period hydraulic simulation to populate steady-state pipe flows automatically.

### Install the optional dependency

```bash
pip install wntr          # standalone
# or
pip install 'rthym-moc[inp]'   # together with rthym-moc
```

### Usage

```python
import rthym_moc

# Load topology and steady-state flows from an EPANET file
solver = rthym_moc.load_inp("network.inp")

# Apply a transient event (valve closure, pump trip, etc.) then run
solver.set_valve_schedule("_VALVE_V1", schedule)
results = solver.run(total_time=10.0, dt=0.01)
```

If wntr is not installed, or for a known operating condition, supply initial flows explicitly:

```python
solver = rthym_moc.load_inp(
    "network.inp",
    use_wntr=False,
    initial_flows={"P1": 500.0, "P2": 250.0},   # GPM, + = from_node → to_node
)
```

### `load_inp()` parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | `str` | — | Path to the EPANET `.inp` file |
| `use_wntr` | `bool` | `True` | Run wntr hydraulics for initial flows |
| `initial_flows` | `dict[str, float]` | `None` | Explicit `{pipe_id: GPM}` overrides (applied after wntr, if any) |

### Supported EPANET sections

| Section | Mapped to |
|---|---|
| `[JUNCTIONS]` | `Junction` nodes |
| `[RESERVOIRS]` | `PressureBoundary` nodes |
| `[TANKS]` | `Tank` nodes |
| `[PIPES]` | `PipeInput` (H-W, D-W, and C-M roughness converted to H-W C; `CV` pipes become generated `CheckValve` nodes plus split pipes) |
| `[PUMPS]` | `Pump` node + two stub pipes; design point read from `[CURVES]` |
| `[VALVES]` | `Valve` node + two stub pipes (TCV, PRV, PSV, PBV) |
| `[OPTIONS]` | `Units`, `Headloss` formula |

All US customary unit variants (GPM, CFS, MGD, IMGD, AFD) and SI metric variants (LPS, LPM, MLD, CMH, CMD) are supported.

### Pump, valve, and check-valve generated IDs

Because EPANET treats pumps and valves as *links* (not nodes), `load_inp()` injects an intermediate node and two 50 ft stub pipes for each one.  The generated IDs follow a predictable pattern:

| EPANET link `V1` | Generated node | Generated pipes |
|---|---|---|
| Pump | `_PUMP_V1` | `_P_V1_up`, `_P_V1_dn` |
| Valve | `_VALVE_V1` | `_P_V1_up`, `_P_V1_dn` |
| CV pipe | `_CHECKVALVE_V1` | `_CV_V1_up`, `_CV_V1_dn` |

Use these IDs when calling `set_valve_schedule()`, `set_pump_speed()`, or accessing results.

### Limitations

- **PRV / PSV / PBV** pressure setpoints cannot be converted to a % open without system-wide hydraulic information; these valves are initialised fully open with a `UserWarning`.
- **FCV / GPV** valve types are not supported and are treated as fully-open valves.
- **Minor losses** (`[PIPES]` column 7) are imported as a dimensionless local-loss coefficient `K`, included in the initial steady headloss, and then applied as distributed resistance across the pipe during the transient. This is an approximation of a truly lumped fitting loss, but dedicated regression benchmarks are included to quantify the mismatch.
- **Demand patterns** (`[PATTERNS]`) are not applied; only base demands are used.
- **Check valves** (`CV` status on a pipe) are imported as generated inline `CheckValve` nodes with split pipes. Phase 1 models them as ideal one-way devices: forward flow is allowed, while reverse-flow tendency closes the valve without detailed slam dynamics.

See `examples/load_from_inp.py` for a complete worked example.

---

## Numerical method

The solver implements the **fixed-grid, elastic Method of Characteristics** (Wylie & Streeter 1993; Chaudhry 2014).

**Grid setup.**  For each pipe of length $L$, the number of spatial segments is

$$N = \text{round}\!\left(\frac{L}{a \cdot \Delta t}\right)$$

and the wave speed is adjusted to $a_\text{adj} = L / (N \cdot \Delta t)$ to enforce Courant number $= 1$ exactly.

**Interior nodes.**  At each interior node $j$ the $C^+$ and $C^-$ characteristics give:

$$C^+ = H_{j-1}^n + B\,V_{j-1}^n - R\,V_{j-1}^n |V_{j-1}^n|$$
$$C^- = H_{j+1}^n - B\,V_{j+1}^n + R\,V_{j+1}^n |V_{j+1}^n|$$
$$H_j^{n+1} = \tfrac{1}{2}(C^+ + C^-), \qquad V_j^{n+1} = \frac{C^+ - C^-}{2B}$$

where $B = a/g$ (ft·s²/ft = s²) is the pipe impedance and $R = f \Delta x / (2g D)$ is the friction term (Darcy-Weisbach $f$ derived from Hazen-Williams $C$ via the Swamee-Jain approximation).

**Boundary nodes.**  Each node type implements its own BC:

- *PressureBoundary / Tank*: $H$ fixed; $V$ solved from the appropriate $C^\pm$.
- *Junction*: Kirchhoff continuity; $H$ solved from the combined $C^\pm$ of all incident pipes.
- *Dead-end (Junction, demand = 0, no outflow pipe)*: $H = C^+$ (zero-flow reflection).
- *Valve*: $K = (100/s)^2 - 1$ loss; combined with $C^\pm$ to solve $H$ and $V$.
- *Pump*: affinity-curve head-flow relationship combined with $C^\pm$.
- *Standpipe*: $H$ updated from the standpipe continuity equation each step.
- *HydropneumaticTank*: $H$ updated from the polytropic gas law combined with the orifice flow equation each step.

**Unsteady friction.**  An optional IIR low-pass filter on pipe velocity (time constant `usf_tau`) approximates the Brunone–Vítkovský unsteady friction correction.  Set `usf_tau = dt` to disable (quasi-steady friction only).

---

## Validation

Validation answers: **is the MOC solver producing the right physics?** The
automated suite under `tests/` uses explicit numeric tolerances, checked-in
reference artifacts, and module docstrings — not visual inspection.

Run the full regression suite:

```bash
pytest -q
```

Run the headline cross-engine checks:

```bash
pytest tests/test_joukowsky_rthym.py tests/test_long_pipe_valve.py -q
```

The [quickstart notebook](examples/quickstart_notebook.ipynb) overlays the
checked-in R-THYM Joukowsky trace with the same RMS/peak tolerances used in CI.

### Validation at a glance

| Category | What it proves | Key tests |
|---|---|---|
| Cross-engine (R-THYM) | Heads, peaks, and traces match the production web-app engine | `test_joukowsky_rthym.py`, `test_long_pipe_valve.py` |
| Cross-engine (EPANET) | Imported steady state and trip directionality | `test_complex_topology_from_inp.py` |
| Analytical / regime | Joukowsky and slow-closure behavior | `test_gradual_closure_benchmark.py` |
| Surge-device physics | Sizing, placement, and mixed-device trends | `test_tank_size_benchmark.py`, `test_hydropneumatic_size_benchmark.py`, `test_device_placement_benchmark.py`, `test_air_valve_dominant_*.py`, and related modules |
| Broader regression | Cavitation, controls, INP import, materials, losses | remaining modules under `tests/` |

Headline automated results:

- Joukowsky first-step surge vs analytical: **< 0.05 %** (`test_joukowsky_rthym.py`)
- R-THYM pressure trace RMS (early post-closure window): **≤ 4 psi** (`test_joukowsky_rthym.py`)
- Wave oscillation period vs $T_0 = 4L/a$: **< 0.2 %** (see `examples/test_wave_reflections.py`)

Full test map, tolerance policy, and reference-artifact inventory:
[docs/validation.md](docs/validation.md).

Long-form cross-engine narratives:
[docs/appendix_b_verification.md](docs/appendix_b_verification.md).

---

## Benchmarking

Benchmarking answers: **how much faster is the C++ core than TSNet?** TSNet is
the pure-Python MOC reference this project was built to outperform.

Reproduce timing on your hardware:

```bash
pip install tsnet==0.3.1
python examples/benchmark_vs_tsnet.py      # single standard case
python examples/benchmark_matrix.py        # grid-size performance matrix
```

The script reports wall-clock time for both engines on the same 300-step,
instant-closure case, plus a physics cross-check (RMS head difference over the
first wave cycle). Typical results on developer hardware are **< 1 ms** for
RTHYM-MOC vs **~50–70 ms** for TSNet — roughly **200–400×** speedup. Re-run the
script on your machine before citing a ratio.

| Topic | Documentation |
|---|---|
| How to run and interpret the comparison | [docs/benchmarking.md](docs/benchmarking.md), `examples/benchmark_matrix.py` |
| Tabulated physics + timing results | [docs/appendix_b_verification.md](docs/appendix_b_verification.md) §B.6 |
| Automated correctness regressions | [Validation](#validation) (TSNet is not a default pytest dependency) |

---

## Versioning

The project tracks its package version from a single source of truth in
`rthym_moc/_version.py`. The Python API exposes that value as
`rthym_moc.__version__`, and both the Python packaging metadata and CMake
project version read from the same source.

Release-level changes are tracked in [CHANGELOG.md](CHANGELOG.md).

---

## Repository layout

```
RTHYM-MOC/
├── src/
│   ├── moc_solver.hpp     # Type definitions, NodeInput, PipeInput, MOCSolver declaration
│   ├── moc_solver.cpp     # Full MOC physics implementation (C++17)
│   └── bindings.cpp       # PyBind11 bindings → _rthym_moc extension module
├── rthym_moc/
│   ├── __init__.py        # Re-exports public API from _rthym_moc
│   ├── _version.py        # Single source of truth for project version
│   └── _rthym_moc*.so     # Compiled extension (generated by build)
├── examples/
│   ├── basic_example.py            # Minimal Joukowsky quickstart
│   ├── benchmark_vs_tsnet.py       # Single-case TSNet timing comparison
│   ├── benchmark_matrix.py         # Multi grid-size TSNet performance matrix
│   ├── test_wave_reflections.py    # Wave period & damping verification
│   ├── test_gradual_closure.py     # Joukowsky criterion, K-model valve
│   ├── test_surge_tank.py          # Standpipe mass-oscillation & pressure mitigation
│   └── load_from_inp.py            # EPANET .inp import example
├── tests/
│   ├── test_joukowsky_rthym.py                 # R-THYM web-app vs solver benchmark
│   ├── test_long_pipe_valve.py                 # Cross-engine valve-closure benchmark
│   ├── test_complex_topology_from_inp.py       # EPANET/wntr import benchmark
│   ├── test_gradual_closure_benchmark.py       # Parameterized closure-time benchmark
│   ├── test_tank_size_benchmark.py             # Parameterized standpipe-size benchmark
│   ├── test_hydropneumatic_size_benchmark.py   # Fixed-ratio vessel-size benchmark
│   ├── test_device_placement_benchmark.py      # Hydropneumatic placement benchmark
│   ├── test_pipe_length_benchmark.py           # Protected pipe-length benchmark
│   ├── test_multi_device_placement_benchmark.py # Split-vessel placement benchmark
│   ├── test_mixed_device_interaction_benchmark.py # Surge-vessel + air-valve benchmark
│   ├── test_air_valve_dominant_mixed_layout_benchmark.py # Air-valve-dominant mixed layout
│   ├── test_air_valve_dominant_layout_sensitivity_benchmark.py # Air-dominant distance sweep
│   ├── test_air_valve_dominant_size_sweep_benchmark.py # Air-dominant size sweep
│   ├── test_column_separation_and_stability.py # Cavitation and long-run stability
│   ├── networks/                               # Benchmark INP fixtures
│   └── test_waterhammer.cpp                    # Standalone C++ unit test (BUILD_TESTS=ON)
├── docs/
│   ├── appendix_b_verification.md  # Long-form cross-engine verification appendix
│   ├── validation.md               # Correctness test map, tolerances, reference assets
│   ├── benchmarking.md             # TSNet performance comparison guide
│   └── appendix_hydraulic_reference.md
├── CMakeLists.txt
└── pyproject.toml
```

---

## Dependencies

**Runtime**

| Package | Minimum | Purpose |
|---------|---------|---------|
| Python  | 3.9     | |
| NumPy   | 1.21    | Result arrays |

**Build only**

| Package | Minimum | Purpose |
|---------|---------|---------|
| pybind11 | 2.11   | C++/Python bridge |
| CMake   | 3.15    | Build system |
| C++17 compiler | GCC 9 / Clang 10 / MSVC 2019 | |

**Optional (examples only)**

| Package | Purpose |
|---------|---------|
| matplotlib | Plotting in `basic_example.py` |
| TSNet 0.3.1 | Cross-validation in example benchmark scripts |
| wntr ≥ 0.4 | Steady-state initial flows for `load_inp()` (`pip install 'rthym-moc[inp]'`) |

---

## References

- Chaudhry, M. H. (2014). *Applied Hydraulic Transients*, 3rd ed. Springer.
- Wylie, E. B., & Streeter, V. L. (1993). *Fluid Transients in Systems*. Prentice Hall.
- Joukowsky, N. (1898). Über den hydraulischen Stoss in Wasserleitungsröhren. *Mémoires de l'Académie Impériale des Sciences de St.-Pétersbourg*, 9(5).

---

## License

**RTHYM-MOC** (this repository) is released under the [MIT License](https://opensource.org/licenses/MIT) and is free to use, modify, and distribute for any purpose, including commercial and academic work.  See `pyproject.toml` for the full license text.

**R-THYM** (the web application at [lillywhitewater.com/products/r-thym/](https://lillywhitewater.com/products/r-thym/)) is a separate, proprietary product and is not covered by this license.  The R-THYM application, its user interface, and its hosted infrastructure remain the intellectual property of Lillywhite Water Solutions LLC and are not open source.
