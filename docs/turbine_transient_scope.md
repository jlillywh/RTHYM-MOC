# Turbine Transient Scope

This document defines the minimum physically credible turbine-transient
scenarios that RTHYM-MOC should support in its current beta phase.

The goal is not to model the full electromechanical behavior of a hydro unit.
The current `Turbine` boundary in RTHYM-MOC is a hydraulic-only,
variable-`K` inline device. It is therefore appropriate for modeling the
hydraulic consequences of wicket-gate or flow-passage opening changes, but not
yet the full generator-governor-rotor system.

## Current Physical Model

RTHYM-MOC currently models a turbine as a variable-`K` orifice:

$$K = \frac{K_\text{base}}{\tau^2}$$

where:

- $\tau = \text{current_setting}/100$ is the fractional opening
- $K_\text{base}$ is derived from the turbine design head and design velocity
- the turbine must be placed in series with exactly one inflow pipe and one
  outflow pipe

That means the current turbine model can credibly represent:

- increased hydraulic resistance during shutdown or gate closure
- decreased hydraulic resistance during startup or gate opening
- the resulting penstock pressure and flow transients

It does **not** yet credibly represent:

- shaft inertia or rotational speed dynamics
- generator torque and electrical load coupling
- governor logic or closed-loop control
- runaway speed, four-quadrant pump-turbine behavior, or full hill charts
- draft-tube instability or detailed machine internal dynamics

## Minimum Credible Beta Scenarios

The following scenarios are the minimum set worth supporting and testing before
claiming turbine-transient coverage.

### 1. Steady Opening Sensitivity

**Purpose:** confirm the turbine behaves as a hydraulic resistance rather than a
placeholder node.

**Network:**

- upstream reservoir
- long penstock
- inline `Turbine`
- downstream reservoir / tailrace boundary

**Expected behavior:**

- smaller turbine opening reduces through-flow
- smaller turbine opening raises upstream turbine-node head
- larger turbine opening restores flow toward the baseline condition

**Why it matters:** this is the simplest direct proof that the turbine boundary
is hydraulically active and scaled correctly with opening.

### 2. Turbine Shutdown / Load-Rejection Transient

**Purpose:** capture the most important real-world surge event for hydropower
penstocks.

**Network:**

- upstream reservoir
- long penstock
- inline `Turbine`
- downstream tailrace boundary

**Transient:** turbine opening drops from operating value toward a lower value
or to near-closed.

**Expected behavior:**

- penstock flow decreases sharply after shutdown begins
- upstream turbine-node head rises above the pre-event operating point
- a faster shutdown produces a larger pressure rise than a slower shutdown

**Why it matters:** this is the core waterhammer case associated with turbine
trip or rapid gate closure.

### 3. Turbine Startup / Gate-Opening Transient

**Purpose:** cover the opposite operating regime from shutdown.

**Network:** same as Scenario 2.

**Transient:** turbine opening increases from a throttled or near-closed state
toward an operating value.

**Expected behavior:**

- through-flow increases after the opening event
- upstream turbine-node head drops relative to the throttled initial condition
- a faster opening produces a larger low-pressure excursion than a slower
  opening

**Why it matters:** startup is the natural complement to shutdown and is one of
the main use cases you identified for R-THYM.

### 4. Surge-Control Interaction With Turbine Shutdown

**Purpose:** confirm turbine transients interact sensibly with surge protection.

**Network:**

- upstream reservoir
- penstock
- `Standpipe` or `HydropneumaticTank`
- inline `Turbine`
- downstream tailrace boundary

**Transient:** same shutdown event as Scenario 2.

**Expected behavior:**

- the surge-control device reduces the shutdown peak pressure versus the
  unprotected case
- the protection effect is monotonic with larger standpipe area or more useful
  hydropneumatic capacity

**Why it matters:** in practice, turbine-surge studies are often about whether
the protection system is adequate during gate movement or trip events.

## Recommended Test Priority

For the current beta stage, the minimum direct automated coverage should be:

1. a direct steady-opening sensitivity regression
2. a shutdown transient regression with fast-vs-slow closure ordering
3. a startup transient regression with fast-vs-slow opening ordering

Scenario 4 is highly valuable, but it can follow after the first three direct
turbine regressions are in place.

## Suggested Acceptance Shape

For the first direct turbine tests, prefer robust monotonic or ordering-based
assertions over fragile exact-pressure snapshots:

- reduced opening => lower flow
- reduced opening => higher upstream head
- faster shutdown => larger peak head than slower shutdown
- faster startup => deeper low-pressure excursion than slower startup

These checks match the current model fidelity and are less likely to become
false failures from small numerical changes.

## Out Of Scope For The Current Beta Claim

RTHYM-MOC should **not** yet claim full hydro-turbine transient simulation in
the following sense:

- coupled turbine-generator-governor dynamic simulation
- power output prediction during transient operation
- rotational overspeed / runaway prediction
- full hydropower unit commissioning studies

The current credible claim is narrower:

> RTHYM-MOC can model hydraulic surge caused by turbine opening and closing
> events in a penstock-style system, using a hydraulic resistance surrogate for
> the turbine.