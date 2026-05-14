# RTHYM-MOC

A high-performance 1-D Method of Characteristics (MOC) transient hydraulic solver with a C++17 core and a Python API via PyBind11.  Originally developed as the engine behind the [R-THYM](https://lillywhitewater.com/products/r-thym/) web application, it is released here as a standalone, open-source library suitable for research scripting, parametric studies, and automated validation pipelines.

## Contents

- [Overview](#overview)
- [Installation](#installation)
- [Quickstart](#quickstart)
- [API Reference](#api-reference)
  - [NodeInput](#nodeinput)
  - [PipeInput](#pipeinput)
  - [MOCSolver](#mocsolver)
  - [Results dictionary](#results-dictionary)
- [Unit conventions](#unit-conventions)
- [Valve model](#valve-model)
- [Gradual closure schedules](#gradual-closure-schedules)
- [Scripted multi-event transients](#scripted-multi-event-transients)
- [Loading from EPANET (.inp)](#loading-from-epanet-inp)
- [Numerical method](#numerical-method)
- [Validation](#validation)
- [Repository layout](#repository-layout)
- [Dependencies](#dependencies)

---

## Overview

RTHYM-MOC solves the 1-D water-hammer equations using the Method of Characteristics with a fixed Courant number of 1.  Key characteristics:

- **Network-capable**: arbitrary topologies of pipes, junctions, reservoirs, valves, pumps, surge tanks, and turbines.
- **Time-varying events**: valve schedules, pump trip/start, demand changes — specified either as discrete step changes between `run()` calls or as continuous piecewise-linear schedules registered before `run()`.
- **Cavitation detection**: integrates a column-separation flag (pressure < vapour pressure) at each node.
- **Speed**: the C++ core solves a 900-step, 75-segment single-pipe case in under 1 ms; roughly **370× faster** than the equivalent TSNet (pure Python) simulation.
- **Validated**: Joukowsky first-step error < 0.02 % against the analytical formula $\Delta H = aV_0/g$; wave oscillation period error < 0.2 % against $T_0 = 4L/a$.

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

## API Reference

### NodeInput

Describes a single network node.  All fields have defaults; only `id` and `type` are strictly required.

```python
node = rthym_moc.NodeInput()
node.id               = "J1"          # str — unique identifier
node.type             = "Junction"    # str — see table below
node.elevation        = 0.0           # ft above datum
node.head             = 100.0         # ft HGL  (Tank, PressureBoundary)
node.level            = 100.0         # % full  (Tank)
node.max_level        = 20.0          # ft depth at 100 % full (Tank)
node.demand           = 0.0           # GPM withdrawal (Junction, OutflowNode)
node.current_setting  = 100.0         # % open (Valve, Turbine; 100 = fully open)
node.diameter         = 8.0           # inches (Valve orifice / Turbine runner)
node.current_speed    = 100.0         # % rated speed (Pump)
node.design_head      = 50.0          # ft at BEP (Pump)
node.design_flow      = 100.0         # GPM at BEP (Pump)
node.design_velocity  = 0.0           # ft/s (Turbine; derived from design_flow if 0)
node.tank_area        = 10.0          # ft² cross-section (SurgeTank standpipe)
```

**Node types**

| `type` string | Boundary condition | Key fields |
|---|---|---|
| `"Junction"` | Kirchhoff continuity (demand sink) | `demand` |
| `"OutflowNode"` | As Junction, sign convention explicit | `demand` |
| `"InflowNode"` | Injects flow (demand treated as negative) | `demand` |
| `"PressureBoundary"` | Fixed total head at all times | `head` |
| `"Tank"` | Fixed HGL (level not updated in current version) | `head`, `level`, `max_level` |
| `"FuelTank"` | Fixed-head boundary at H = 0 | — |
| `"Valve"` | Quadratic loss, $K = (100/s)^2 - 1$ | `current_setting`, `diameter` |
| `"Turbine"` | Quadratic loss (design-curve K) | `current_setting`, `design_velocity`, `diameter` |
| `"Pump"` | Three-coefficient affinity curve | `current_speed`, `design_head`, `design_flow` |
| `"SurgeTank"` | Free-surface standpipe (level tracked each step) | `head`, `tank_area` |

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
pipe.flow_gpm       = 500.0    # GPM, initial steady-state flow (+ = from→to)
pipe.wall_thickness = 0.25     # inches (used only if youngs_modulus > 0)
pipe.youngs_modulus = 0.0      # psi (0 = rigid pipe, default wave speed ~4000 ft/s)
pipe.poissons_ratio = 0.3      # (used only if youngs_modulus > 0)
```

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
| `solver.set_valve_setting(id, pct_open)` | Change a valve's opening immediately (used between `run()` calls). |
| `solver.set_pump_speed(id, pct_speed)` | Change a pump speed immediately. |
| `solver.set_node_demand(id, demand_gpm)` | Change a junction demand immediately. |
| `solver.set_valve_schedule(id, schedule)` | Register a time-varying valve schedule (see below). |
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

## Gradual closure schedules

For any `Valve` node, register a piecewise-linear opening schedule before calling `run()`:

```python
# Linear closure from 100 % to 0 % over 3 seconds
T_c = 3.0
dt  = 0.01
import numpy as np

t_vals  = np.arange(0.0, T_c + dt, dt)
pct_open = np.clip(100.0 * (1.0 - t_vals / T_c), 0.0, 100.0)
schedule = list(zip(t_vals.tolist(), pct_open.tolist()))

solver.set_valve_schedule("V1", schedule)
results = solver.run(total_time=5.0, dt=dt)
```

The schedule is a `list[tuple[float, float]]` of `(time_s, pct_open)` pairs in ascending time order.  The solver linearly interpolates between control points at each time step.  Any time beyond the last control point holds the final value.

Schedules can represent any profile — abrupt, linear, S-curve, or empirically measured field data.

---

## Scripted multi-event transients

`run()` resets the MOC grid to the steady-state initial conditions each call, so multi-event sequences are best handled with `set_valve_schedule()` covering the full duration, or by rebuilding `NodeInput` objects between calls:

```python
# Example: valve closes at t=1 s, pump trips at t=2 s
import numpy as np

# Build schedule covering the full 5-second window
t_close  = np.array([0.0, 1.0, 1.01, 5.0])
s_close  = np.array([100.0, 100.0, 0.0, 0.0])
solver.set_valve_schedule("V1", list(zip(t_close, s_close)))

# For the pump: step changes between run() calls
solver.run(total_time=2.0, dt=0.01)         # first 2 s
solver.set_pump_speed("PMP1", 0.0)          # trip pump
solver.run(total_time=3.0, dt=0.01)         # next 3 s
```

Note that the second `run()` call re-initialises from the `NodeInput` steady-state values, not from the final state of the first call.  If you need to chain transient states, manually update the relevant `NodeInput` fields before the second `run()`.

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
| `[PIPES]` | `PipeInput` (H-W, D-W, and C-M roughness converted to H-W C) |
| `[PUMPS]` | `Pump` node + two stub pipes; design point read from `[CURVES]` |
| `[VALVES]` | `Valve` node + two stub pipes (TCV, PRV, PSV, PBV) |
| `[OPTIONS]` | `Units`, `Headloss` formula |

All US customary unit variants (GPM, CFS, MGD, IMGD, AFD) and SI metric variants (LPS, LPM, MLD, CMH, CMD) are supported.

### Pump and valve node IDs

Because EPANET treats pumps and valves as *links* (not nodes), `load_inp()` injects an intermediate node and two 50 ft stub pipes for each one.  The generated IDs follow a predictable pattern:

| EPANET link `V1` | Generated node | Generated pipes |
|---|---|---|
| Pump | `_PUMP_V1` | `_P_V1_up`, `_P_V1_dn` |
| Valve | `_VALVE_V1` | `_P_V1_up`, `_P_V1_dn` |

Use these IDs when calling `set_valve_schedule()`, `set_pump_speed()`, or accessing results.

### Limitations

- **PRV / PSV / PBV** pressure setpoints cannot be converted to a % open without system-wide hydraulic information; these valves are initialised fully open with a `UserWarning`.
- **FCV / GPV** valve types are not supported and are treated as fully-open valves.
- **Minor losses** (`[PIPES]` column 7) are currently ignored.
- **Demand patterns** (`[PATTERNS]`, `[CONTROLS]`, `[RULES]`) are not applied; only base demands are used.
- **Check valves** (Status = CV) are treated as regular pipes; reverse-flow prevention is not enforced.

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
- *SurgeTank*: $H$ updated from the standpipe continuity equation each step.

**Unsteady friction.**  An optional IIR low-pass filter on pipe velocity (time constant `usf_tau`) approximates the Brunone–Vítkovský unsteady friction correction.  Set `usf_tau = dt` to disable (quasi-steady friction only).

---

## Validation

Three independent validation benchmarks are included under `examples/`:

### 1. Joukowsky single-pipe benchmark (`benchmark_vs_tsnet.py`)

Instantaneous valve closure at the end of a 3000 ft, 12-inch pipe fed by a 150 ft constant-head reservoir (Q₀ = 500 GPM, a = 4000 ft/s).

| Metric | Result |
|--------|--------|
| Analytical $\Delta H = aV_0/g$ | 176.20 ft |
| rthym-moc first-step $\Delta H$ | 176.17 ft |
| Error | **0.02 %** |
| RMS head diff vs TSNet (3 s) | **0.175 ft** |
| Speed vs TSNet (pure Python) | **~370×** |

### 2. Wave period and damping (`test_wave_reflections.py`)

Multi-cycle oscillation in a reservoir–pipe–dead-end system.  Measures the full oscillation period $T_0 = 4L/a$ and verifies monotonic amplitude decay due to friction.

| Metric | rthym-moc | TSNet | Analytical |
|--------|-----------|-------|-----------|
| Oscillation period $T_0$ | 3.0050 s | 3.0000 s | $4L/a = 3.0000$ s |
| Period error | **+0.17 %** | 0.00 % | — |
| Peak decay over 2 periods | 7.93 ft | 7.94 ft | $\approx 4H_f = 8.4$ ft |
| Monotonic decay | YES | YES | — |

### 3. Joukowsky criterion — gradual closure (`test_gradual_closure.py`)

Linear-setting closure schedule; tests the $K = (100/s)^2 - 1$ valve model across three closure times.

| $T_c$ | $T_\text{eff}$ | vs $2L/a$ | $\Delta H$ | % Joukowsky |
|-------|---------------|-----------|-----------|-------------|
| 0.5 s | 0.060 s | $\ll 2L/a$ | 177.8 ft | **100.9 %** |
| 3.0 s | 0.363 s | $\ll 2L/a$ | 176.5 ft | **100.2 %** |
| 150 s | 18.1 s | $\gg 2L/a$ | 88.1 ft | **50.0 %** |

The ultra-slow case ($T_c = 150$ s) falls in the Allievi slow-closure regime, confirming that the solver correctly captures the suppression of the waterhammer peak when the wave period is short compared with the effective closure time.

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
│   └── _rthym_moc*.so     # Compiled extension (generated by build)
├── examples/
│   ├── basic_example.py            # Minimal Joukowsky quickstart
│   ├── benchmark_vs_tsnet.py       # Side-by-side comparison with TSNet
│   ├── test_wave_reflections.py    # Wave period & damping verification
│   ├── test_gradual_closure.py     # Joukowsky criterion, K-model valve
│   └── load_from_inp.py            # EPANET .inp import example
├── tests/
│   └── test_waterhammer.cpp        # Standalone C++ unit test (BUILD_TESTS=ON)
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
| TSNet 0.3.1 | Cross-validation in benchmark and test scripts |
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
