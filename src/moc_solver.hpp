// moc_solver.hpp
// Copyright (c) 2026 Jason Lillywhite <jason@lillywhitewater.com>
// SPDX-License-Identifier: MIT
// Author: Jason Lillywhite <jason@lillywhitewater.com>
//
#pragma once

#include <string>
#include <vector>
#include <unordered_map>
#include <cmath>
#include <stdexcept>

#if defined(EMSCRIPTEN) || defined(__EMSCRIPTEN__)
#include <emscripten/val.h>
#endif

namespace rthym {

// ── Physical constants (US customary units) ──────────────────────────────────
constexpr double G_FT_S2    = 32.2;        // ft/s²
constexpr double GPM_TO_CFS = 0.002228;    // GPM → ft³/s
constexpr double PSI_TO_FT  = 2.31;        // psi → ft of water
constexpr double M_PI_      = 3.14159265358979323846;
constexpr double NU_FT2_S   = 1.07e-5;    // kinematic viscosity of water at ~60°F, ft²/s

// ── Node type enumeration ────────────────────────────────────────────────────
enum class NodeType {
    Junction,            // Interior demand node (Kirchhoff balance)
    Tank,                // Fixed-level reservoir
    PressureBoundary,    // Fixed-head pressure source
    AirValve,            // Air-admission / vacuum-break valve (clamps to atmosphere when open)
    CheckValve,          // Inline one-way valve (forward flow only)
    PRV,                 // Pressure Reducing Valve (maintain downstream setpoint)
    PSV,                 // Pressure Sustaining Valve (maintain upstream setpoint)
    PBV,                 // Pressure Breaker Valve (maintain fixed pressure drop)
    Valve,               // Inline throttling device  (K quadratic)
    Turbine,             // Inline turbine            (K quadratic, design-curve K)
    Pump,                // Inline centrifugal pump   (3-coeff affinity curve)
    Standpipe,           // Open surge tank — free surface (R-THYM SurgeControl)
    HydropneumaticTank,  // Closed pressurized vessel — polytropic gas + orifice (R-THYM SurgeTank)
    InflowNode,          // Demand node that injects flow (demand sign is negative)
    OutflowNode,         // Standard demand node
};

// Convert string → NodeType (unknown strings become Junction)
NodeType parseNodeType(const std::string& s);
std::string nodeTypeToStr(NodeType t);

// ── User-facing input structs ────────────────────────────────────────────────

struct NodeInput {
        // CheckValve closure dynamics
        double closure_time = 0.03;      // s, time to fully close from open (default: 0.03s, tuned for minimal reverse flow)
        double closure_damping = 0.0;    // dimensionless, damping ratio (0 = none, >0 = damped)
    std::string id;
    NodeType    type            = NodeType::Junction;

    // Geometry / steady-state
    double  elevation           = 0.0;   // ft above datum
    double  head                = 100.0; // ft HGL  (Tank, PressureBoundary)
    double  level               = 100.0; // % full   (Tank, derived/legacy compatibility)
    double  max_level           = 20.0;  // ft depth at 100% full (Tank)

    // Demand
    double  demand              = 0.0;   // GPM (Junction / OutflowNode / InflowNode)

    // Pump fields
    double  current_speed       = 100.0; // % rated speed
    double  design_head         = 0.0;   // ft shut-off/design head
    double  design_flow         = 0.0;   // GPM at BEP
    bool    has_power           = true;  // electrical power (PCV shutdown vs outage)

    // Valve / Turbine fields
    double  current_setting     = 100.0; // % open (100 = fully open)
    double  diameter            = 8.0;   // inches (valve orifice / turbine runner)
    double  design_velocity     = 0.0;   // ft/s  (Turbine; computed from design_flow if 0)
    double  air_release_head    = 0.0;   // ft above elevation where AirValve vent is referenced (default = atmosphere)
    double  air_release_diameter = 0.25; // inches (AirValve small-orifice release port)

    // Open surge tank (Standpipe)
    double  tank_area           = 10.0;  // ft² cross-section of standpipe

    // Hydropneumatic (closed pressurized) surge tank
    // Orifice area is derived from the existing `diameter` field (inches).
    double  gas_volume          = 10.0;  // ft³  initial trapped gas volume
    double  tank_volume         = 30.0;  // ft³  total vessel volume (gas + water)
    double  polytropic_n        = 1.2;   // polytropic exponent (1.0=isothermal, 1.4=adiabatic)
    double  loss_coeff_in       = 0.7;   // C_in  orifice discharge coeff for inflow (water entering)
    double  loss_coeff_out      = 0.7;   // C_out orifice discharge coeff for outflow (water leaving)
    bool    flipped             = false; // check valve direction flipped
};

struct PipeInput {
    std::string id;
    std::string from_node;   // upstream node id
    std::string to_node;     // downstream node id

    double  length           = 100.0;  // ft
    double  diameter         = 8.0;    // inches
    double  roughness        = 120.0;  // Hazen-Williams C
    double  minor_loss       = 0.0;    // dimensionless local-loss coefficient K
    double  flow_gpm         = 0.0;    // initial steady-state flow (GPM, + = from→to)

    // Elastic pipe wave-speed (leave youngs_modulus = 0 for rigid pipe → 4000 ft/s)
    double  wall_thickness   = 0.25;   // inches
    double  youngs_modulus   = 0.0;    // psi  (0 = rigid, default wave speed)
    double  poissons_ratio   = 0.3;
};

// ── Simulation results ───────────────────────────────────────────────────────

struct SimResults {
    std::vector<double>                               time;            // s  (num_steps)
    std::unordered_map<std::string, std::vector<double>> node_head;    // ft
    std::unordered_map<std::string, std::vector<double>> node_pressure;// psi
    std::unordered_map<std::string, std::vector<double>> pipe_flow_gpm;// GPM
    std::unordered_map<std::string, std::vector<int>>    node_cavitation; // 0/1
    // CheckValve closure dynamics telemetry
    std::unordered_map<std::string, std::vector<double>> valve_position;
    std::unordered_map<std::string, std::vector<double>> valve_velocity;
    // Throttling valve / turbine % open (from control rules and schedules)
    std::unordered_map<std::string, std::vector<double>> valve_setting;
};

enum class ControlType {
    Threshold,
    Deadband,
    PID,
    PCV
};

struct ControlRuleInput {
    std::string id;
    ControlType type = ControlType::Threshold;
    
    std::string monitored_node;   // Node ID (Junction, Tank, Standpipe, etc.)
    std::string controlled_node;  // Node ID (Pump, Valve)
    
    std::string monitored_quantity = "pressure"; // "pressure", "level", "head", "flow"
    std::string monitored_pipe;                  // Pipe ID (used if quantity is "flow")
    
    // Threshold / Deadband Parameters
    std::string condition = "lt"; // "lt" or "gt"
    double threshold      = 0.0;
    double target         = 0.0;
    double deadband       = 0.0;
    std::string action    = "fill"; // "fill" or "drain"

    // PID Parameters
    double kp = 0.5;
    double ki = 0.01;
    double kd = 0.01;
};

struct ControlRuleState {
    ControlRuleInput input;
    // PID state
    double integral_error = 0.0;
    double previous_error = 0.0;
    bool has_prev_error = false;
    
    // Deadband/Threshold state
    bool last_active = false;
    
    // PCV state
    double pcv_timer = -1.0;
    std::string pcv_phase = "idle";
};

// ── Internal pipe runtime state ──────────────────────────────────────────────

struct PipeState {
    std::string from_id, to_id;
    int    num_nodes = 2;
    double L         = 100.0;  // ft
    double D         = 8.0/12; // ft
    double area      = 0.0;    // ft²
    double a_wave    = 4000.0; // ft/s  (Courant-adjusted)
    double f         = 0.02;   // Darcy-Weisbach friction factor
    double k_minor   = 0.0;    // dimensionless local-loss K distributed across the pipe

    std::vector<double> H;          // head (ft)          [num_nodes]
    std::vector<double> V;          // velocity (ft/s)    [num_nodes]
    std::vector<double> V_filtered; // IIR-filtered V for unsteady friction
};

// ── Internal node runtime state ──────────────────────────────────────────────

struct NodeState {
        // CheckValve closure dynamics state
        double valve_position = 1.0;     // 1.0 = fully open, 0.0 = fully closed
        double valve_velocity = 0.0;     // rate of closure/opening (1/s)
        bool is_closing = false;         // true if closure is in progress
    NodeInput input;
    // Pump: commanded target speed (%) separate from input.current_speed, which
    // PCV and other rules may override transiently during valve ramping.
    double command_speed = 100.0;
    double surge_level_ft   = 0.0;  // Standpipe current water surface (ft)
    double actual_demand    = 0.0;  // GPM  (updated by solver, Junction/OutflowNode)
    double gas_volume_ft3   = 0.0;  // HydropneumaticTank / AirValve current gas volume (ft³)
    double gas_constant     = 0.0;  // HydropneumaticTank: C = H_g_abs * V_g^n; AirValve: M = H_g_abs * V_g

    // Additional transient metrics for UI compatibility
    double air_loss_rate_gpm = 0.0;
    double air_cumulative_loss_gal = 0.0;
    double gas_pressure_psi = 0.0;
    double tank_flow_gpm = 0.0;
};

// ── Main MOC solver class ────────────────────────────────────────────────────

class MOCSolver {
public:
    void add_node(const NodeInput& n);
    void add_pipe(const PipeInput& p);
    void clear();

    void add_control_rule(const ControlRuleInput& rule);
    void clear_control_rules();
    double get_node_head(const std::string& id) const;
    double get_node_pressure(const std::string& id) const;

    // Adjust boundary conditions between calls to run() for scripted transients
    void set_valve_setting(const std::string& id, double pct_open);
    void set_pump_speed   (const std::string& id, double pct_speed);
    void set_pump_power   (const std::string& id, bool has_power);
    void set_node_demand  (const std::string& id, double demand_gpm);
    void set_node_head    (const std::string& id, double head_ft);

    // Time-varying valve schedule: list of (time_s, pct_open) pairs.
    // During run() the setting is linearly interpolated at each time step.
    // Replaces any constant setting on the named valve for the duration of run().
    void set_valve_schedule(const std::string& id,
                            const std::vector<std::pair<double,double>>& schedule);
    void set_pump_schedule(const std::string& id,
                           const std::vector<std::pair<double,double>>& schedule);
    void set_demand_schedule(const std::string& id,
                             const std::vector<std::pair<double,double>>& schedule);
    void set_head_schedule(const std::string& id,
                           const std::vector<std::pair<double,double>>& schedule);

    // Execute the full transient simulation
    SimResults run(double total_time_s,
                   double dt            = 0.01,
                   double p_vapor_psi   = -14.0,
                   double usf_tau       = 0.5,
                   double k_bru         = -1.0); // -1 = auto Vardy-Brown; 0 = no USF; >0 = static

    // Step-by-step API for WASM integration
    void   initGrid();
    void   stepMOC();
    void   set_dt(double dt) { dt_ = dt; }
    double get_dt() const { return dt_; }
    void   set_p_vapor_psi(double p_vapor_psi) { p_vapor_ = p_vapor_psi * PSI_TO_FT; }
    void   set_usf_tau(double usf_tau) { usf_tau_ = usf_tau; }
    void   set_k_bru(double k_bru) { k_Bru_ = k_bru; }

#if defined(EMSCRIPTEN) || defined(__EMSCRIPTEN__)
    emscripten::val get_step_results() const;
#endif

private:
    // User inputs (persistent across run() calls)
    std::vector<NodeInput> node_inputs_;
    std::vector<PipeInput> pipe_inputs_;

    // Runtime state (rebuilt each run())
    std::vector<PipeState>  pipes_;
    std::vector<NodeState>  nodes_;
    std::unordered_map<std::string, int> node_idx_map_;
    std::unordered_map<std::string, int> pipe_idx_map_;

    // Adjacency: node_id → list of pipe indices where pipe.to_id == node_id
    std::unordered_map<std::string, std::vector<int>> node_inflow_pipes_;
    // Adjacency: node_id → list of pipe indices where pipe.from_id == node_id
    std::unordered_map<std::string, std::vector<int>> node_outflow_pipes_;

    // Time-varying valve schedules  (id → sorted list of (t, pct_open) pairs)
    std::unordered_map<std::string,
                       std::vector<std::pair<double,double>>> valve_schedules_;
    // Time-varying pump speed schedules  (id → sorted list of (t, pct_speed) pairs)
    std::unordered_map<std::string,
                       std::vector<std::pair<double,double>>> pump_schedules_;
    // Time-varying node demand schedules (id → sorted list of (t, demand_gpm) pairs)
    std::unordered_map<std::string,
                       std::vector<std::pair<double,double>>> demand_schedules_;
    // Time-varying node head schedules (id → sorted list of (t, head_ft) pairs)
    std::unordered_map<std::string,
                       std::vector<std::pair<double,double>>> head_schedules_;

    // Simulation parameters
    double dt_      = 0.01;
    double p_vapor_ = -14.0 * PSI_TO_FT; // ft (converted from psi at init)
    double usf_tau_ = 0.5;               // s  boundary-layer relaxation time constant
    // Brunone (1991) dimensionless USF coefficient.
    //   < 0  (default -1): compute dynamically each timestep via Vardy-Brown (1996)
    //                       k_Bru = C*/√π,  C* = 7.41/Re^0.352  (turbulent, smooth)
    //   = 0  :  steady friction only (no USF damping)
    //   > 0  :  user-supplied static value (typical calibrated range: 0.02–0.15)
    double k_Bru_   = -1.0;

    // Operational control rules
    std::vector<ControlRuleInput> control_rules_;
    std::vector<ControlRuleState> control_rule_states_;
    double t_now_ = 0.0;

    void evaluateControlRules(double t_now);

    double getInitialHead(const NodeState& ns) const;
    void   recordStep(SimResults& results) const;
};

} // namespace rthym
