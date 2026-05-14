#pragma once

#include <string>
#include <vector>
#include <unordered_map>
#include <cmath>
#include <stdexcept>

namespace rthym {

// ── Physical constants (US customary units) ──────────────────────────────────
constexpr double G_FT_S2    = 32.2;     // ft/s²
constexpr double GPM_TO_CFS = 0.002228; // GPM → ft³/s
constexpr double PSI_TO_FT  = 2.31;     // psi → ft of water
constexpr double M_PI_      = 3.14159265358979323846;

// ── Node type enumeration ────────────────────────────────────────────────────
enum class NodeType {
    Junction,         // Interior demand node (Kirchhoff balance)
    Tank,             // Fixed-level reservoir
    PressureBoundary, // Fixed-head pressure source
    FuelTank,         // Fixed H=0 boundary
    Valve,            // Inline throttling device  (K quadratic)
    Turbine,          // Inline turbine            (K quadratic, design-curve K)
    Pump,             // Inline centrifugal pump   (3-coeff affinity curve)
    SurgeTank,        // Standpipe with free surface (level updated each step)
    InflowNode,       // Demand node that injects flow (demand sign is negative)
    OutflowNode,      // Standard demand node
};

// Convert string → NodeType (unknown strings become Junction)
NodeType parseNodeType(const std::string& s);
std::string nodeTypeToStr(NodeType t);

// ── User-facing input structs ────────────────────────────────────────────────

struct NodeInput {
    std::string id;
    NodeType    type            = NodeType::Junction;

    // Geometry / steady-state
    double  elevation           = 0.0;   // ft above datum
    double  head                = 100.0; // ft HGL  (Tank, PressureBoundary)
    double  level               = 100.0; // % full   (Tank)
    double  max_level           = 20.0;  // ft depth at 100% full (Tank)

    // Demand
    double  demand              = 0.0;   // GPM (Junction / OutflowNode / InflowNode)

    // Pump fields
    double  current_speed       = 100.0; // % rated speed
    double  design_head         = 50.0;  // ft shut-off/design head
    double  design_flow         = 100.0; // GPM at BEP

    // Valve / Turbine fields
    double  current_setting     = 100.0; // % open (100 = fully open)
    double  diameter            = 8.0;   // inches (valve orifice / turbine runner)
    double  design_velocity     = 0.0;   // ft/s  (Turbine; computed from design_flow if 0)

    // Surge tank
    double  tank_area           = 10.0;  // ft² cross-section of standpipe
};

struct PipeInput {
    std::string id;
    std::string from_node;   // upstream node id
    std::string to_node;     // downstream node id

    double  length           = 100.0;  // ft
    double  diameter         = 8.0;    // inches
    double  roughness        = 120.0;  // Hazen-Williams C
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

    std::vector<double> H;          // head (ft)          [num_nodes]
    std::vector<double> V;          // velocity (ft/s)    [num_nodes]
    std::vector<double> V_filtered; // IIR-filtered V for unsteady friction
};

// ── Internal node runtime state ──────────────────────────────────────────────

struct NodeState {
    NodeInput input;
    double surge_level_ft   = 0.0;  // SurgeTank current water surface (ft)
    double actual_demand    = 0.0;  // GPM  (updated by solver, Junction/OutflowNode)
};

// ── Main MOC solver class ────────────────────────────────────────────────────

class MOCSolver {
public:
    void add_node(const NodeInput& n);
    void add_pipe(const PipeInput& p);
    void clear();

    // Adjust boundary conditions between calls to run() for scripted transients
    void set_valve_setting(const std::string& id, double pct_open);
    void set_pump_speed   (const std::string& id, double pct_speed);
    void set_node_demand  (const std::string& id, double demand_gpm);

    // Time-varying valve schedule: list of (time_s, pct_open) pairs.
    // During run() the setting is linearly interpolated at each time step.
    // Replaces any constant setting on the named valve for the duration of run().
    void set_valve_schedule(const std::string& id,
                            const std::vector<std::pair<double,double>>& schedule);

    // Execute the full transient simulation
    SimResults run(double total_time_s,
                   double dt            = 0.01,
                   double p_vapor_psi   = -14.0,
                   double usf_tau       = 0.5,
                   double k_bru         = 0.0);

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

    // Simulation parameters
    double dt_      = 0.01;
    double p_vapor_ = -14.0 * PSI_TO_FT; // ft (converted from psi at init)
    double usf_tau_ = 0.5;               // s  boundary-layer relaxation time constant
    // Brunone (1991) dimensionless USF coefficient.  0 = steady friction only.
    // Typical calibrated value: 0.02–0.15 (Vardy-Brown 1996 gives ~0.04–0.10
    // for turbulent pipe flow).  Default 0 keeps the solver conservative until
    // the user supplies a calibrated value.
    double k_Bru_   = 0.0;

    void   initGrid();
    void   stepMOC();
    double getInitialHead(const NodeState& ns) const;
    void   recordStep(SimResults& results) const;
};

} // namespace rthym
