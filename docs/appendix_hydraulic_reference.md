# Appendix: Hydraulic Reference

**R-THYM — Method of Characteristics Transient Solver**
**Author: Jason Lillywhite, jason@lillywhitewater.com**

---

This appendix documents the mathematical foundation of the R-THYM transient
hydraulic engine. The solver uses the **Method of Characteristics (MOC)**, a
well-established numerical technique for propagating pressure waves through
pressurized pipe networks. The implementation is directly equivalent in both the
JavaScript (R-THYM web application) and C++/Python (`rthym_moc`) engines.

All quantities are in **US customary units** internally:

| Quantity | Unit |
|---|---|
| Length, diameter | ft |
| Piezometric head | ft |
| Velocity | ft/s |
| Flow | ft³/s (CFS) internally; GPM at the API boundary |
| Pressure | ft HGL internally; psi at the API boundary |
| Gravitational acceleration *g* | 32.2 ft/s² |

---

## 1. Governing Equations

### 1.1 The Waterhammer Partial Differential Equations

Transient flow in a pressurized elastic pipe is governed by two coupled PDEs
derived from conservation of momentum and conservation of mass (Wylie &
Streeter, 1993, §2):

**Momentum equation:**

$$\frac{\partial V}{\partial t} + g\frac{\partial H}{\partial x} + \frac{f}{2D}V|V| = 0$$

**Continuity equation:**

$$\frac{\partial H}{\partial t} + \frac{a^2}{g}\frac{\partial V}{\partial x} = 0$$

Where:

- $H$ = piezometric head (ft)
- $V$ = cross-sectional average velocity (ft/s)
- $a$ = pressure wave speed (ft/s)
- $f$ = Darcy-Weisbach friction factor (dimensionless)
- $D$ = pipe internal diameter (ft)
- $g$ = gravitational acceleration = 32.2 ft/s²
- $x$ = distance along the pipe (ft), $t$ = time (s)

These equations are valid for:

- 1-D flow (cross-sectional average velocities)
- Elastic pipe walls and slightly compressible water
- Fully turbulent, single-phase liquid
- Relatively small velocity changes (acoustic approximation)

### 1.2 Joukowsky Relation

For an instantaneous flow stoppage the pressure change is given by the
**Joukowsky equation**:

$$\Delta H = -\frac{a}{g} \Delta V$$

This is the theoretical maximum pressure surge and is the primary benchmark used
to validate the solver. For a complete instantaneous valve closure from initial
velocity $V_0$:

$$\Delta H = \frac{a \cdot V_0}{g}$$

---

## 2. Method of Characteristics Transformation

### 2.1 Characteristic Lines

The MOC transforms the hyperbolic PDE system into two families of ordinary
differential equations (ODEs) along characteristic lines in the $x$-$t$ plane.

Along the **C+ characteristic** (forward wave, slope $dx/dt = +a$):

$$\frac{dH}{dt} + \frac{a}{g}\frac{dV}{dt} + \frac{fa}{2gD}V|V| = 0$$

Along the **C− characteristic** (backward wave, slope $dx/dt = -a$):

$$\frac{dH}{dt} - \frac{a}{g}\frac{dV}{dt} - \frac{fa}{2gD}V|V| = 0$$

### 2.2 Finite-Difference Form

Integrating each ODE over one time step $\Delta t$ from the known state at time
$t$ to the unknown state at time $t + \Delta t$, and applying steady friction
over the reach, yields the algebraic **compatibility equations**:

**C+ equation** (from upstream node A to interior node P):

$$H_P = C_+ - B \cdot V_P$$

$$C_+ = H_A + B \cdot V_A - R \cdot V_A |V_A|$$

**C− equation** (from downstream node B to interior node P):

$$H_P = C_- + B \cdot V_P$$

$$C_- = H_B - B \cdot V_B + R \cdot V_B |V_B|$$

The two **pipe characteristic constants** are:

$$B = \frac{a}{g} \quad \text{(pipe impedance, ft}\cdot\text{s/ft}^{2}\text{ = s)}$$

$$R = \frac{f \cdot \Delta x}{2gD} \quad \text{(steady-friction resistance, s}^{2}\text{/ft)}$$

where $\Delta x = a \cdot \Delta t$ is the spatial grid spacing.

### 2.3 Solution at Interior Nodes

At any interior pipe node $j$ (not at a boundary), adding and subtracting the
two compatibility equations gives the explicit update:

$$H_P = \frac{C_+ + C_-}{2}$$

$$V_P = \frac{C_+ - C_-}{2B}$$

This explicit update requires no iteration and is the key computational
advantage of the MOC over implicit methods.

---

## 3. Spatial Grid and the Courant Condition

### 3.1 Courant Number

The MOC requires the **Courant–Friedrichs–Lewy (CFL) condition** to be exactly
satisfied for the explicit scheme to be stable and free of numerical dispersion:

$$C_r = \frac{a \cdot \Delta t}{\Delta x} = 1$$

This means the characteristic lines must align exactly with the grid lines. In
practice, each pipe is divided into an integer number of segments $N_s$, and the
wave speed is adjusted slightly so that $C_r = 1$ exactly.

### 3.2 Grid Discretization Procedure

Given a user-specified wave speed $a_0$, time step $\Delta t$, and pipe length
$L$:

1. Compute the target spatial step: $\Delta x_\text{target} = a_0 \cdot \Delta t$
2. Round to the nearest integer number of segments: $N_s = \text{round}(L / \Delta x_\text{target})$
3. Back-compute the adjusted wave speed: $a = (L / N_s) / \Delta t$

The adjusted wave speed $a$ satisfies $C_r = 1$ exactly for the chosen $N_s$.
The small correction to $a$ is typically less than 1–2 % and is physically
justified because the true wave speed in real pipes is uncertain by a similar
margin.

---

## 4. Pressure Wave Speed

### 4.1 Korteweg Formula for Elastic Pipes

The pressure wave speed in an elastic pipe filled with liquid is given by the
**Korteweg–Joukowsky formula** (Wylie & Streeter §1.4):

$$a = \frac{a_0}{\sqrt{1 + \dfrac{K}{E} \cdot \dfrac{D}{e} \cdot c}}$$

Where:

- $a_0 = 4{,}860$ ft/s — acoustic wave speed in bulk water (rigid-pipe limit)
- $K = 319{,}000$ psi — bulk modulus of elasticity of water
- $E$ — Young's modulus of the pipe wall material (psi)
- $D$ — pipe internal diameter (in)
- $e$ — pipe wall thickness (in)
- $c = 1 - \nu^2$ — pipe restraint factor; $\nu$ = Poisson's ratio of pipe material

### 4.2 Default Rigid-Pipe Approximation

When no pipe material properties are specified ($E = 0$), the solver defaults to
$a = 4{,}000$ ft/s, a conservative approximation for steel and ductile-iron
water mains.

**Typical wave speeds by material:**

| Pipe Material | Young's Modulus (psi) | Typical $a$ (ft/s) |
|---|---|---|
| Steel | 30,000,000 | 3,500–4,200 |
| Ductile Iron | 24,000,000 | 3,200–4,000 |
| PVC (AWWA C900) | 400,000 | 1,200–1,500 |
| HDPE | 130,000 | 600–1,000 |
| Rigid (default) | — | 4,000 |

---

## 5. Friction

### 5.1 Darcy-Weisbach Equation

Internal calculations use the **Darcy-Weisbach** friction formulation:

$$h_f = f \cdot \frac{L}{D} \cdot \frac{V^2}{2g}$$

The Darcy-Weisbach friction factor $f$ appears directly in the MOC compatibility
equations as the resistance coefficient $R$.

### 5.2 Hazen-Williams to Darcy-Weisbach Conversion

User input uses the more familiar **Hazen-Williams roughness coefficient** $C_{HW}$.
The steady-state head loss is first computed from Hazen-Williams:

$$h_f = \frac{10.44 \cdot L \cdot Q^{1.852}}{C_{HW}^{1.852} \cdot D_{in}^{4.871}}$$

Where $Q$ is in GPM, $D_{in}$ is in inches, $L$ in feet, and $h_f$ in feet.

The equivalent Darcy-Weisbach friction factor is then back-calculated from the
initial steady-state velocity $V_0$:

$$f = \frac{h_f \cdot D \cdot 2g}{L \cdot V_0^2}$$

This single value of $f$ is held constant throughout the transient simulation
(a standard approximation valid for fully turbulent flow, where $f$ varies
weakly with Reynolds number). Physically reasonable bounds of $0.001 \leq f
\leq 0.5$ are enforced.

---

## 6. Unsteady Friction

### 6.1 Physical Background

Steady friction ($R \cdot V|V|$ in the compatibility equations) underestimates
energy dissipation during rapid transients because it ignores the oscillating
boundary layer. **Unsteady friction (USF)** corrections improve agreement with
field measurements, especially for the damping of pressure oscillation peaks.

### 6.2 Brunone Model

The solver implements the **Brunone (1991)** instantaneous acceleration model, a
computationally efficient $O(N)$ approximation:

$$\text{USF term} = k_u \cdot (V_j - \bar{V}_j)$$

Where:

- $k_u = k_\text{Bru} \cdot B$ is the unsteady-friction scale (units: s)
- $k_\text{Bru}$ is the dimensionless **Brunone coefficient** (typical range: 0.02–0.15)
- $V_j$ is the instantaneous velocity at node $j$
- $\bar{V}_j$ is the low-pass (time-averaged) velocity, obtained from a
  first-order **IIR (infinite impulse response) filter**

### 6.2.1 Vardy-Brown Dynamic Coefficient (Default)

By default, $k_\text{Bru}$ is **computed automatically each time step** per pipe
from the instantaneous Reynolds number using the **Vardy & Brown (1996)**
formula for turbulent flow in smooth pipes:

$$C^* = \frac{7.41}{Re^{0.352}} \quad (Re > 100)$$

$$k_\text{Bru} = \frac{C^*}{\sqrt{\pi}}$$

$$Re = \frac{|V_\text{mid}| \cdot D}{\nu}$$

Where $V_\text{mid}$ is the velocity at the pipe midpoint, $D$ is the internal
diameter (ft), and $\nu = 1.07 \times 10^{-5}$ ft²/s is the kinematic viscosity
of water at 60°F. At $Re \leq 100$ the coefficient is set to zero.

This approach requires no user calibration and automatically provides
physically realistic damping across the simulated Reynolds number range.

To disable USF entirely, pass `k_bru = 0`. To supply a manually calibrated
static value, pass any positive `k_bru` value; the dynamic calculation is
bypassed.

### 6.3 IIR Low-Pass Filter

The filtered velocity $\bar{V}$ is updated each time step by a discrete
exponential (leaky integrator):

$$\bar{V}_j^{n+1} = \bar{V}_j^n + \alpha \cdot (V_j^n - \bar{V}_j^n)$$

$$\alpha = \frac{\Delta t}{\tau_{BL}}$$

Where $\tau_{BL}$ is the **boundary-layer relaxation time constant** (seconds),
a user-adjustable parameter (default: 0.5 s). The residual $(V_j - \bar{V}_j)$
approximates the high-frequency (transient) velocity fluctuation that drives the
additional boundary-layer shear.

### 6.4 Full Compatibility Equations with USF

Including the Brunone USF term, the compatibility equations become:

$$C_+ = H_A + B \cdot V_A - R \cdot V_A|V_A| - k_u(V_A - \bar{V}_A)$$

$$C_- = H_B - B \cdot V_B + R \cdot V_B|V_B| + k_u(V_B - \bar{V}_B)$$

Setting $k_\text{Bru} = 0$ (the default) reduces these to the standard
steady-friction equations.

---

## 7. Boundary Conditions

Boundary nodes are updated after all interior pipe nodes. Each boundary type
imposes a constraint equation that is solved simultaneously with the arriving
characteristic from the adjacent pipe.

### 7.1 Fixed-Head Boundary (Reservoir / Pressure Boundary)

**Applies to:** Tank, PressureBoundary, FuelTank

The piezometric head $H_P$ is held constant at the user-specified value
throughout the simulation. The velocity at the pipe end is determined from the
arriving characteristic:

$$H_P = H_0 \quad \text{(constant)}$$

$$V_P = \frac{C_\pm - H_P}{B} \quad \text{(from C+ or C− respectively)}$$

**Tank head** (accounts for fill level):

$$H_\text{tank} = z_\text{bottom} + \frac{\text{level\%}}{100} \cdot h_\text{max}$$

Where $z_\text{bottom}$ is the tank base elevation and $h_\text{max}$ is the
maximum depth at 100 % full.

### 7.2 Interior Junction / Demand Node

**Applies to:** Junction, InflowNode, OutflowNode

The Kirchhoff continuity equation requires that the net flow into the node
equals the nodal demand:

$$\sum Q_\text{in} - \sum Q_\text{out} = Q_\text{demand}$$

Each connected pipe contributes a flow term derived from its arriving
characteristic:

$$Q_i = \frac{A_i}{B_i}(C_{+,i} - H_P) \quad \text{(inflow pipe)}$$

$$Q_i = \frac{A_i}{B_i}(H_P - C_{-,i}) \quad \text{(outflow pipe)}$$

Summing over all pipes and solving for the junction head $H_P$:

$$H_P = \frac{\displaystyle\sum_\text{in}\frac{A_i}{B_i}C_{+,i} + \sum_\text{out}\frac{A_i}{B_i}C_{-,i} - Q_\text{demand}}{\displaystyle\sum_\text{in}\frac{A_i}{B_i} + \sum_\text{out}\frac{A_i}{B_i}}$$

For an **InflowNode** (supply source), the demand sign is reversed: $Q_\text{demand}
\rightarrow -Q_\text{demand}$.

### 7.3 Valve

**Applies to:** Valve (inline throttle), TCV (throttle control valve)

A valve is modelled as a **quadratic head loss device**:

$$\Delta H = H_\text{up} - H_\text{dn} = K_{eq} \cdot Q^2$$

The equivalent loss coefficient is:

$$K_{eq} = \frac{K}{2g A_v^2}$$

Where $A_v = \pi (D_v/2)^2$ is the valve orifice area and the dimensionless
loss coefficient $K$ is related to the fractional opening $\tau \in (0, 1]$
($\tau = \text{setting\%}/100$):

$$K = \left(\frac{1}{\tau}\right)^2 - 1$$

This formulation gives $K \rightarrow 0$ at full open and $K \rightarrow \infty$
as the valve closes, which is physically correct. At full open ($\tau = 1$),
$K = 0$ and the valve is hydraulically invisible.

**Combined with the pipe characteristics**, the valve boundary gives a quadratic
equation in $Q$:

$$K_{eq} \cdot Q^2 + B_{eq} \cdot Q - C_{eq} = 0$$

$$B_{eq} = \frac{B_\text{in}}{A_\text{in}} + \frac{B_\text{out}}{A_\text{out}}, \qquad C_{eq} = C_{+,\text{in}} - C_{-,\text{out}}$$

Solving with the positive root (flow in the normal direction):

$$Q = \frac{-B_{eq} + \sqrt{B_{eq}^2 + 4 K_{eq} C_{eq}}}{2 K_{eq}}$$

The upstream and downstream heads at the valve faces are then recovered:

$$H_\text{up} = C_{+,\text{in}} - \frac{B_\text{in}}{A_\text{in}} \cdot Q$$

$$H_\text{dn} = C_{-,\text{out}} + \frac{B_\text{out}}{A_\text{out}} \cdot Q$$

### 7.4 Turbine

**Applies to:** Turbine

A turbine is modelled as a variable-$K$ orifice, where the dimensionless loss
coefficient is derived from the design operating point (design head $H_D$ and
design velocity $V_D$) and scaled by the fractional gate opening $\tau$:

$$K_\text{base} = \frac{H_D \cdot 2g}{V_D^2}$$

$$K = \frac{K_\text{base}}{\tau^2}$$

The boundary condition then follows the same quadratic formulation as the valve.

### 7.5 Centrifugal Pump

**Applies to:** Pump

The pump is modelled using a **three-coefficient affinity-law head curve**:

$$\Delta H = \alpha s^2 - \beta_\text{cfs} \cdot Q^2$$

Where $s = \text{speed\%}/100$ is the fractional speed ratio, and the curve
coefficients are derived from the design point ($H_D$, $Q_D$ in GPM):

$$\alpha = \frac{4}{3} H_D \quad \text{(shutoff head at rated speed, ft)}$$

$$\beta = \frac{1}{3} \frac{H_D}{Q_D^2} \quad \text{(in GPM units)}$$

$$\beta_\text{cfs} = \beta \times 448.831^2 \approx \beta \times 201{,}449 \quad \text{(converted to CFS)}$$

The affinity laws scale both the head and flow by the speed ratio:
at speed $s$, the shutoff head scales as $s^2$ and the design flow scales as $s$.

**Combined with the pipe characteristics**, the pump boundary gives:

$$\beta_\text{cfs} s^2 Q^2 + B_{eq} Q - (C_{eq} + \alpha s^2) = 0$$

Which is solved using the standard quadratic formula for the positive (pumping)
root. Reverse flow is not permitted (simplified model; check-valve assumed).

### 7.6 Open Surge Tank / Standpipe

**Applies to:** SurgeTank, Standpipe

An open surge tank or standpipe is an **open-to-atmosphere free-surface vessel**
connected inline to the pipeline. It acts as a pressure-relief device by
accepting or releasing flow to limit transient pressure extremes.

The tank head at time $t$ equals the current water-surface elevation $L(t)$:

$$H_P(t) = L(t)$$

The free surface rises or falls according to continuity (Wylie & Streeter §7.3):

$$\frac{dL}{dt} = \frac{Q_\text{net}}{A_s}$$

In discretized form:

$$L^{n+1} = L^n + \frac{Q_\text{net}^n}{A_s} \cdot \Delta t$$

Where $A_s$ is the cross-sectional area of the standpipe (ft²) and $Q_\text{net}$
is the algebraic net inflow to the tank (positive = water entering = level rising).

At each time step the current surface elevation is used as a fixed-head boundary
for the connecting pipes, and $Q_\text{net}$ is computed from the resulting pipe
velocities.

### 7.7 Hydropneumatic Surge Tank (Closed Pressurized Vessel)

**Applies to:** HydropneumaticTank

A hydropneumatic tank is a **sealed pressurized vessel** containing a trapped
gas cushion above the water. As pipeline pressure rises, water enters and
compresses the gas; as pressure drops, the gas expands and drives water back.

#### 7.7.1 Polytropic Gas Law

The gas pressure follows the **polytropic process**:

$$C = H_{g,\text{abs}} \cdot V_g^n = \text{constant}$$

Where:

- $H_{g,\text{abs}}$ = absolute gas pressure head (ft), measured from absolute zero pressure
- $V_g$ = current gas volume (ft³)
- $n$ = polytropic exponent (1.0 = isothermal, 1.2 = typical, 1.4 = adiabatic)

The constant $C$ is determined at initialization from the steady-state condition
(no orifice flow):

$$H_{g,\text{abs},0} = (H_{P,0} - z) + H_\text{atm}$$

$$C = H_{g,\text{abs},0} \cdot V_{g,0}^n$$

Where $H_\text{atm} = 33.9$ ft (1 atm = 14.696 psi) and $z$ is the tank
elevation. At each time step, the current tank head is recovered explicitly:

$$H_\text{tank} = \frac{C}{V_g^n} - H_\text{atm} + z$$

#### 7.7.2 Orifice Head Loss

The connection between the tank and the pipeline includes a throttling orifice
that controls the rate of water exchange. The head loss across the orifice uses
an **asymmetric discharge coefficient** to account for flow direction:

$$H_P - H_\text{tank} = K \cdot Q_\text{net} |Q_\text{net}|$$

$$K = \frac{1}{2g (C_d A_\text{ori})^2}$$

Where $C_d$ is the discharge coefficient (separate values $C_\text{in}$ and
$C_\text{out}$ for inflow and outflow directions), and $A_\text{ori}$ is the
orifice area derived from the specified orifice diameter.

#### 7.7.3 Quadratic Solution

Combining the MOC characteristics from all connecting pipes with the orifice
equation yields a quadratic equation in the net tank inflow $Q_\text{net}$:

$$K \Sigma_{AB} \cdot Q_\text{net}^2 + Q_\text{net} - C_{eq} = 0$$

Where:

$$\Sigma_{AB} = \sum \frac{A_i}{B_i}, \qquad C_{eq} = \sum_{AB} C_\pm - \Sigma_{AB} H_\text{tank}$$

Solving for $Q_\text{net}$ and updating the pipeline head $H_P$, the gas volume
is then advanced by continuity:

$$V_g^{n+1} = V_g^n - Q_\text{net} \cdot \Delta t$$

Where the sign convention is: $Q_\text{net} > 0$ means water enters the tank,
gas is compressed, and $V_g$ decreases.

---

## 8. Cavitation Check

At each node and each time step, the computed piezometric head is checked against
the **vapor pressure head**:

$$H_\text{vap} = z + \frac{p_\text{vap}}{\gamma}$$

If $H_P < H_\text{vap}$, the head is clamped to $H_\text{vap}$ (column separation
is assumed). This is a simplified model of cavitation; it prevents non-physical
negative absolute pressures but does not simulate cavity collapse or re-joining.

The default vapor pressure is $p_\text{vap} = -14.0$ psi (below atmospheric), which
corresponds to near-vacuum conditions and is a conservative choice.

---

## 9. Initial Conditions

Before the transient simulation begins, every pipe is initialized with a
**linear hydraulic grade line (HGL)** between its endpoint heads, and a
**uniform velocity** equal to the user-supplied steady-state flow:

$$H_j = H_\text{start} + \frac{j}{N_s}(H_\text{end} - H_\text{start}), \quad j = 0,1,\ldots,N_s$$

$$V_j = V_0 = \frac{Q_0}{A}$$

Endpoint heads are determined from fixed-head source nodes where available; for
pipes connecting only junction nodes, the user-supplied `head` values at each
node are used. The friction head loss across the pipe is computed from the
Hazen-Williams equation and used to interpolate endpoint heads when only one
end is a fixed-head source.

---

## 10. Time-Varying Boundary Conditions

### 10.1 Valve Schedules

The valve opening at each time step is determined by **linear interpolation**
through a user-supplied schedule of $(t_i, \tau_i)$ breakpoints:

$$\tau(t) = \tau_j + \frac{t - t_j}{t_{j+1} - t_j}(\tau_{j+1} - \tau_j), \quad t_j \leq t < t_{j+1}$$

This allows any closure or opening profile to be defined: instantaneous, linear,
equal-percentage, sinusoidal, or custom actuator curves.

### 10.2 Closure Profile Types

| Profile | Description |
|---|---|
| **Instantaneous** | Single breakpoint at $t=0$; $\tau$ steps from open to 0 |
| **Linear** | Two breakpoints; $\tau$ decreases at constant rate over stroke time |
| **Equal-percentage** | Geometric series; each step removes a fixed fraction of remaining opening |
| **Slow/Fast two-stage** | Piecewise linear with a fast initial phase and slow final phase |

---

## 11. Unit Conversion Reference

The following constants are used at the API boundary to convert between
user-facing units and the internal US customary system:

| Conversion | Factor |
|---|---|
| GPM → ft³/s (CFS) | × 0.002228 |
| ft³/s → GPM | ÷ 0.002228 |
| psi → ft of water | × 2.31 |
| ft of water → psi | ÷ 2.31 |
| inches → ft | ÷ 12 |

---

## 12. Numerical Parameters Summary

| Parameter | Symbol | Default | Notes |
|---|---|---|---|
| Time step | $\Delta t$ | 0.01 s | Must satisfy Courant condition per pipe |
| Vapor pressure | $p_\text{vap}$ | −14.0 psi | Column separation threshold |
| Boundary-layer time constant | $\tau_{BL}$ | 0.5 s | IIR filter constant for USF |
| Brunone USF coefficient | $k_\text{Bru}$ | auto (Vardy-Brown) | −1 triggers dynamic Vardy-Brown; 0 = steady friction only; >0 = static value |
| Default wave speed (rigid) | $a$ | 4,000 ft/s | Used when no pipe material is specified |
| Atmospheric head | $H_\text{atm}$ | 33.9 ft | Used for absolute pressure in HPT gas law |

---

## 13. References

1. **Wylie, E.B. and Streeter, V.L.** (1993). *Fluid Transients in Systems.*
   Prentice Hall, Englewood Cliffs, NJ.

2. **Brunone, B., Golia, U.M., and Greco, M.** (1991). "Some remarks on the
   momentum equation for fast transients." *Proceedings of the International
   Conference on Hydraulic Transients with Water Column Separation*, IAHR,
   Valencia, Spain, pp. 201–209.

3. **Vardy, A.E. and Brown, J.M.B.** (1996). "On turbulent, unsteady,
   smooth-pipe flow." *Journal of Hydraulic Research*, 33(4), 435–456.

4. **Trikha, A.K.** (1975). "An efficient method for simulating frequency-
   dependent friction in transient liquid flow." *ASME Journal of Fluids
   Engineering*, 97(1), 97–105.

5. **Joukowsky, N.** (1898). "Über den hydraulischen Stoss in Wasserleitungsröhren."
   *Mémoires de l'Académie Impériale des Sciences de St.-Pétersbourg*, Series 8,
   9(5).
