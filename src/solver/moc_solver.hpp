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
#include <optional>

#include "types.hpp"

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

enum class CavitationModel {
    LegacyClamp,
    DVCM,
};

enum class TransientFrictionModel {
    Steady = 0,
    QuasiSteady = 1,
    BrunoneIIR = 2,
    Vitkovsky = 3,
};

enum class WaveSpeedDistortionAction {
    Warn,
    Error,
};

enum class CavityRegime {
    LiquidFull,
    CavityActive,
    CollapseTransition,
};

// Convert string → NodeType (unknown strings become Junction)
NodeType parseNodeType(const std::string& s);
std::string nodeTypeToStr(NodeType t);

// ── User-facing input structs ────────────────────────────────────────────────

struct NodeInput {
        // CheckValve closure dynamics
        double closure_time = 0.03;      // s, time to fully close from open (default: 0.03s, tuned for minimal reverse flow)
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
    double  inertia_wr2         = 0.0;   // lb·ft² (rotational inertia, 0 = no inertia/falls back to schedule)
    double  speed_rpm           = 1750.0;// rated speed (RPM)
    double  efficiency          = 0.80;  // rated pump efficiency (0.0 to 1.0)
    double  ramp_time           = 0.0;   // s (VFD pump speed acceleration/deceleration limit, 0 = instant)

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

    // Optional piecewise-linear survey (chainage_ft from from_node, elevation_ft).
    // Empty → linear interpolation between from_node and to_node elevations.
    std::vector<std::pair<double, double>> elevation_profile;

    // Sparse interior DVCM watchpoints (chainage ft from from_node). When non-empty
    // and enable_interior_dvcm is on, cavity physics runs only at snapped grid indices.
    std::vector<double> interior_dvcm_chainages_ft;
};

// ── Simulation results ───────────────────────────────────────────────────────

struct SimResults {
    std::vector<double>                               time;            // s  (num_steps)
    std::unordered_map<std::string, std::vector<double>> node_head;    // ft
    std::unordered_map<std::string, std::vector<double>> node_pressure;// psi
    std::unordered_map<std::string, std::vector<double>> pipe_flow_gpm;// GPM
    std::unordered_map<std::string, std::vector<int>>    node_cavitation; // 0/1
    std::unordered_map<std::string, std::vector<double>> node_cavity_volume; // ft^3
    std::unordered_map<std::string, std::vector<int>>    node_cavity_active; // 0/1
    std::unordered_map<std::string, std::vector<int>>    node_cavity_collapse_flag; // 0/1, this step
    std::unordered_map<std::string, std::vector<int>>    node_cavity_collapse_count; // cumulative count
    // CheckValve closure dynamics telemetry
    std::unordered_map<std::string, std::vector<double>> valve_position;
    std::unordered_map<std::string, std::vector<double>> valve_velocity;
    // Throttling valve / turbine % open (from control rules and schedules)
    std::unordered_map<std::string, std::vector<double>> valve_setting;
    // Pump speed telemetry (%)
    std::unordered_map<std::string, std::vector<double>> pump_speed;
    // Turbine speed telemetry (%)
    std::unordered_map<std::string, std::vector<double>> turbine_speed;

    // Optional per-pipe MOC grid profiles (populated when record_pipe_profiles is enabled)
    // chainage_ft: (num_profile_points,) distances from upstream pipe end [ft]
    // head_ft / pressure_psi / velocity_fps: (num_steps, num_profile_points)
    std::unordered_map<std::string, std::vector<double>> pipe_profile_chainage_ft;
    std::unordered_map<std::string, std::vector<std::vector<double>>> pipe_profile_head_ft;
    std::unordered_map<std::string, std::vector<std::vector<double>>> pipe_profile_pressure_psi;
    std::unordered_map<std::string, std::vector<std::vector<double>>> pipe_profile_velocity_fps;
    // 0/1 vapor screening at profile points (H <= z(x) + H_vapor); mirrors node_cavitation
    std::unordered_map<std::string, std::vector<std::vector<int>>> pipe_profile_cavitation;
    // Interior DVCM diagnostics at profile points (enable_interior_dvcm + record_pipe_profiles)
    std::unordered_map<std::string, std::vector<std::vector<double>>> pipe_profile_cavity_volume;
    std::unordered_map<std::string, std::vector<std::vector<int>>>    pipe_profile_cavity_active;

    // Per-pipe MOC grid scaling (populated every run() after initGrid())
    std::unordered_map<std::string, double> pipe_wave_speed_design_fps;
    std::unordered_map<std::string, double> pipe_wave_speed_adjusted_fps;
    std::unordered_map<std::string, double> pipe_distortion_pct;
    std::unordered_map<std::string, int>    pipe_num_segments;
    // Snapped MOC grid indices for sparse interior DVCM (empty → full interior grid)
    std::unordered_map<std::string, std::vector<int>> pipe_interior_dvcm_grid_indices;
};

// Grid discretization report (initGrid() preview — no time integration).
struct GridReport {
    double dt_s = 0.0;
    std::unordered_map<std::string, double> pipe_length_ft;
    std::unordered_map<std::string, double> pipe_wave_speed_design_fps;
    std::unordered_map<std::string, double> pipe_wave_speed_adjusted_fps;
    std::unordered_map<std::string, double> pipe_distortion_pct;
    std::unordered_map<std::string, int>    pipe_num_segments;
    std::unordered_map<std::string, double> pipe_dx_ft;
    std::unordered_map<std::string, double> pipe_courant_number;
    std::unordered_map<std::string, std::vector<int>> pipe_interior_dvcm_grid_indices;
    std::string distortion_warning;
    bool distortion_limit_exceeded = false;
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

    int monitored_pipe_idx = -1;
    int monitored_node_idx = -1;
    int action_node_idx = -1;
};

// ── Per-grid-point interior DVCM state (Phase 3) ─────────────────────────────
// Indexed by MOC grid j; interior DVCM uses j = 1 … N-2 (endpoints use junction DVCM).

struct PipeSegmentState {
    bool cavity_active = false;
    double cavity_volume_ft3 = 0.0;
    bool cavity_collapsed_this_step = false;
    int cavity_collapse_count = 0;
    int cavity_consecutive_collapses = 0;
    CavityRegime cavity_regime = CavityRegime::LiquidFull;
};

// ── Internal pipe runtime state ──────────────────────────────────────────────

struct PipeState {
    std::string from_id, to_id;
    int    num_nodes = 2;
    double L         = 100.0;  // ft
    double D         = 8.0/12; // ft
    double area      = 0.0;    // ft²
    double a_wave_design = 4000.0; // ft/s  (Korteweg / rigid default before Courant rounding)
    double a_wave    = 4000.0; // ft/s  (Courant-adjusted)
    double f         = 0.02;   // Darcy-Weisbach friction factor
    double k_minor   = 0.0;    // dimensionless local-loss K distributed across the pipe

    std::vector<double> H;          // head (ft)          [num_nodes]
    std::vector<double> V;          // velocity (ft/s)    [num_nodes]
    std::vector<double> V_filtered; // IIR-filtered V for unsteady friction
    std::vector<double> V_prev;     // previous-step V for Vitkovsky dV/dt
    std::vector<double> z;          // ground elevation (ft) at each grid point [num_nodes]
    bool has_terrain_elevation = false; // survey table or sloping endpoint elevations
    std::vector<PipeSegmentState> segments; // cavity state per grid index [num_nodes]
    std::vector<int> interior_dvcm_indices; // sparse watchpoints; empty → all interior j
};

// ── Internal node runtime state ──────────────────────────────────────────────

struct NodeState {
        // CheckValve closure dynamics state
        double valve_position = 1.0;     // 1.0 = fully open, 0.0 = fully closed
        double valve_velocity = 0.0;     // rate of closure/opening (1/s)
        bool is_closing = false;         // true if closure is in progress
    // Cavitation scaffolding state (Phase 1; no DVCM physics yet)
    bool cavity_active = false;
    double cavity_volume_ft3 = 0.0;
    bool cavity_collapsed_this_step = false;
    int cavity_collapse_count = 0;
    int cavity_consecutive_collapses = 0;
    CavityRegime cavity_regime = CavityRegime::LiquidFull;
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
    double rated_torque_ftlb = 0.0; // steady-state design torque (lb·ft)

    std::vector<int> inflow_pipes;
    std::vector<int> outflow_pipes;
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
    double get_node_gas_volume(const std::string& id) const;
    double get_node_tank_flow_gpm(const std::string& id) const;

    // Adjust boundary conditions between calls to run() for scripted transients
    void set_valve_setting(const std::string& id, double pct_open);
    void set_node_type    (const std::string& id, const std::string& type_str);
    void set_pump_speed   (const std::string& id, double pct_speed);
    void set_pump_command_speed(const std::string& id, double pct_speed);
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
                   double k_bru         = -1.0,
                   std::optional<CavitationModel> cavitation_model = std::nullopt,
                   bool record_pipe_profiles = false,
                   int profile_stride = 1,
                   bool enable_interior_dvcm = false,
                   std::optional<TransientFrictionModel> friction_model = std::nullopt);

    // Step-by-step integration API (batch run() calls initGrid/stepMOC internally).
    void   initGrid();
    void   stepMOC();
    void   set_dt(double dt) { dt_ = dt; }
    double get_dt() const { return dt_; }
    void   set_p_vapor_psi(double p_vapor_psi) { p_vapor_ = p_vapor_psi * PSI_TO_FT; }
    void   set_usf_tau(double usf_tau) { usf_tau_ = usf_tau; }
    void   set_k_bru(double k_bru) { k_Bru_ = k_bru; }
    void   set_friction_model(TransientFrictionModel friction_model) {
        friction_model_ = friction_model;
    }
    TransientFrictionModel get_friction_model() const { return friction_model_; }
    void   set_cavitation_model(CavitationModel cavitation_model) { cavitation_model_ = cavitation_model; }
    CavitationModel get_cavitation_model() const { return cavitation_model_; }
    void   set_enable_interior_dvcm(bool enable) { enable_interior_dvcm_ = enable; }
    bool   get_enable_interior_dvcm() const { return enable_interior_dvcm_; }
    void   set_max_segments_per_pipe(int max_segments);
    int    get_max_segments_per_pipe() const { return max_segments_per_pipe_; }
    void   set_max_wave_speed_distortion(double max_fraction);
    double get_max_wave_speed_distortion() const { return max_wave_speed_distortion_; }
    void   set_wave_speed_distortion_action(WaveSpeedDistortionAction action);
    WaveSpeedDistortionAction get_wave_speed_distortion_action() const {
        return wave_speed_distortion_action_;
    }
    const std::string& get_grid_distortion_warning() const { return grid_distortion_warning_; }

    // Build the MOC grid for ``dt`` and return Courant-adjusted wave speeds without
    // integrating the transient. Applies the configured distortion warn/error policy.
    GridReport get_grid_report(double dt);

    StepSnapshot capture_step_snapshot() const;

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
    CavitationModel cavitation_model_ = CavitationModel::LegacyClamp;
    bool enable_interior_dvcm_ = false;
    int  max_segments_per_pipe_ = 0; // 0 = uncapped; minimum 2 segments enforced in initGrid()
    double max_wave_speed_distortion_ = -1.0; // fraction |a'-a|/a; <0 disables check
    WaveSpeedDistortionAction wave_speed_distortion_action_ = WaveSpeedDistortionAction::Warn;
    std::string grid_distortion_warning_;
    double usf_tau_ = 0.5;               // s  boundary-layer relaxation time constant
    // Brunone (1991) dimensionless USF coefficient.
    //   < 0  (default -1): compute dynamically each timestep via Vardy-Brown (1996)
    //                       k_Bru = C*/√π,  C* = 7.41/Re^0.352  (turbulent, smooth)
    //   = 0  :  steady friction only (no USF damping)
    //   > 0  :  user-supplied static value (typical calibrated range: 0.02–0.15)
    double k_Bru_   = -1.0;
    TransientFrictionModel friction_model_ = TransientFrictionModel::BrunoneIIR;

    // Operational control rules
    std::vector<ControlRuleInput> control_rules_;
    std::vector<ControlRuleState> control_rule_states_;
    double t_now_ = 0.0;

    struct PipeBndry {
        double area;   // ft²
        double B;      // a/g  (pipe impedance)
        double C_P;    // C+ at downstream end  (→ to_node)
        double C_M;    // C- at upstream end    (→ from_node)
    };
    std::vector<std::vector<double>> newH_;
    std::vector<std::vector<double>> newV_;
    std::vector<PipeBndry> bndry_;

    struct ResolvedSchedule {
        int node_idx;
        std::vector<std::pair<double, double>> schedule;
    };
    std::vector<ResolvedSchedule> resolved_valve_schedules_;
    std::vector<ResolvedSchedule> resolved_pump_schedules_;
    std::vector<ResolvedSchedule> resolved_demand_schedules_;
    std::vector<ResolvedSchedule> resolved_head_schedules_;

    void evaluateControlRules(double t_now);

    double get_node_head_by_idx(int idx) const;
    double get_node_pressure_by_idx(int idx) const;

    double getInitialHead(const NodeState& ns) const;
    void   recordStep(SimResults& results) const;

    bool record_pipe_profiles_ = false;
    int  profile_stride_       = 1;
    // Grid indices and chainage captured once per run() after initGrid()
    std::unordered_map<std::string, std::vector<int>>    profile_point_indices_;
    std::unordered_map<std::string, std::vector<double>> profile_chainage_ft_;

    double pipeGridElevationFt(const PipeState& ps, int grid_index) const;
    double pipeGridVaporHeadFt(const PipeState& ps, int grid_index) const;
    static std::vector<int> buildProfilePointIndices(int num_nodes, int stride);
    void initializePipeProfileCapture(SimResults& results);
    void buildPipeGridElevations(PipeState& ps, const PipeInput& p) const;
    static void buildInteriorDvcmIndices(PipeState& ps, const PipeInput& p);
    bool interiorDvcmActiveAt(const PipeState& ps, int grid_index) const;
    static void initializePipeSegmentStates(PipeState& ps);
    void enforceWaveSpeedDistortionPolicy();
    GridReport buildGridReport() const;
    void populateGridScaling(SimResults& results) const;
    double unsteadyFrictionScale(const PipeState& ps, double B) const;
    static double velocityGradientAt(const PipeState& ps, int grid_index, double dx);
    static double darcyFFromHazenWilliamsAtVelocity(
        const PipeState& ps,
        const PipeInput& p,
        double velocity_fps,
        double fallback_f = 0.02);
    double steadyFrictionResistance(
        const PipeState& ps,
        const PipeInput& p,
        double dx,
        double velocity_fps) const;
    double unsteadyFrictionHeadTerm(
        const PipeState& ps,
        double k_u,
        int grid_index,
        double V_foot,
        double dx) const;
    static double interpolateElevationAtChainageFt(
        const std::vector<std::pair<double, double>>& profile,
        double chainage_ft);
};

} // namespace rthym
