// moc_solver.cpp
// Copyright (c) 2026 Jason Lillywhite <jason@lillywhitewater.com>
// SPDX-License-Identifier: MIT
// Author: Jason Lillywhite <jason@lillywhitewater.com>
// Pure C++ implementation of a 1-D Method of Characteristics (MOC) transient
// hydraulic solver, ported from the R-THYM transientWorker.js engine.
//
// Unit system  (internal, all quantities in US customary):
//   Length  : ft
//   Head    : ft  (piezometric)
//   Velocity: ft/s
//   Flow    : ft³/s  (CFS) internally; GPM on API boundary
//   Pressure: ft HGL internally; psi on API boundary
//   g       : 32.2 ft/s²
//
// Key references:
//   Wylie & Streeter, "Fluid Transients in Systems" (1993)
//   Trikha (1975) – O(N) unsteady-friction approximation

#include "moc_solver.hpp"

#include <algorithm>
#include <cassert>
#include <cmath>
#include <numeric>
#include <stdexcept>
#include <sstream>

namespace rthym {

// ── String ↔ NodeType helpers ─────────────────────────────────────────────────

NodeType parseNodeType(const std::string& s) {
    if (s == "Tank")                return NodeType::Tank;
    if (s == "PressureBoundary")    return NodeType::PressureBoundary;
    if (s == "AirValve")            return NodeType::AirValve;
    if (s == "CheckValve")          return NodeType::CheckValve;
    if (s == "PRV")                 return NodeType::PRV;
    if (s == "PSV")                 return NodeType::PSV;
    if (s == "PBV")                 return NodeType::PBV;
    if (s == "Valve")               return NodeType::Valve;
    if (s == "Turbine")             return NodeType::Turbine;
    if (s == "Pump")                return NodeType::Pump;
    if (s == "Standpipe")           return NodeType::Standpipe;
    if (s == "HydropneumaticTank")  return NodeType::HydropneumaticTank;
    if (s == "InflowNode")          return NodeType::InflowNode;
    if (s == "OutflowNode")         return NodeType::OutflowNode;
    return NodeType::Junction;
}

std::string nodeTypeToStr(NodeType t) {
    switch (t) {
        case NodeType::Tank:                return "Tank";
        case NodeType::PressureBoundary:    return "PressureBoundary";
        case NodeType::AirValve:            return "AirValve";
        case NodeType::CheckValve:          return "CheckValve";
        case NodeType::PRV:                 return "PRV";
        case NodeType::PSV:                 return "PSV";
        case NodeType::PBV:                 return "PBV";
        case NodeType::Valve:               return "Valve";
        case NodeType::Turbine:             return "Turbine";
        case NodeType::Pump:                return "Pump";
        case NodeType::Standpipe:           return "Standpipe";
        case NodeType::HydropneumaticTank:  return "HydropneumaticTank";
        case NodeType::InflowNode:          return "InflowNode";
        case NodeType::OutflowNode:         return "OutflowNode";
        default:                            return "Junction";
    }
}

namespace {

NodeInput* findNodeInput(std::vector<NodeInput>& node_inputs, const std::string& id) {
    for (auto& node_input : node_inputs) {
        if (node_input.id == id)
            return &node_input;
    }
    return nullptr;
}

const NodeInput& requireNodeInput(std::vector<NodeInput>& node_inputs,
                                  const std::string& id,
                                  const char* operation) {
    auto* node_input = findNodeInput(node_inputs, id);
    if (node_input == nullptr) {
        throw std::invalid_argument(std::string(operation) + " requires an existing node id, got '" + id + "'");
    }
    return *node_input;
}

NodeInput& requireNodeInputMutable(std::vector<NodeInput>& node_inputs,
                                   const std::string& id,
                                   const char* operation) {
    return const_cast<NodeInput&>(requireNodeInput(node_inputs, id, operation));
}

bool nodeTypeMatchesAny(NodeType type, std::initializer_list<NodeType> allowed_types) {
    return std::find(allowed_types.begin(), allowed_types.end(), type) != allowed_types.end();
}

void requireNodeType(const NodeInput& node_input,
                     const std::string& id,
                     const char* operation,
                     std::initializer_list<NodeType> allowed_types,
                     const char* expected_types) {
    if (!nodeTypeMatchesAny(node_input.type, allowed_types)) {
        throw std::invalid_argument(
            std::string(operation) + " requires a " + expected_types + " node, got '" + id + "' of type '" +
            nodeTypeToStr(node_input.type) + "'");
    }
}

void validateSchedule(const std::vector<std::pair<double,double>>& schedule,
                      const char* operation) {
    if (schedule.empty()) {
        throw std::invalid_argument(std::string(operation) + " requires at least one schedule point");
    }

    for (std::size_t index = 1; index < schedule.size(); ++index) {
        if (!(schedule[index - 1].first < schedule[index].first)) {
            std::ostringstream message;
            message << operation << " requires strictly increasing schedule times, but entries "
                    << (index - 1) << " and " << index << " are "
                    << schedule[index - 1].first << " and " << schedule[index].first;
            throw std::invalid_argument(message.str());
        }
    }
}

constexpr double R_AIR = 1716.0; // ft-lb/(slug-R)
constexpr double T_ATM_R = 529.67; // Rankine (~70 F)
constexpr double RHO_WATER_G = 62.4; // lb/ft^3

double computeCompressibleAirFlow(double Cd, double Area, double p1, double pr, double T1) {
    if (Cd <= 0.0 || Area <= 0.0 || p1 <= 0.0) return 0.0;
    
    constexpr double k = 1.4;
    constexpr double R = 1716.0;
    constexpr double pr_crit = 0.52828;
    
    double m_dot = 0.0;
    if (pr <= pr_crit) {
        // Sonic / Choked flow
        double factor = std::sqrt((k / R) * std::pow(2.0 / (k + 1.0), (k + 1.0) / (k - 1.0)));
        m_dot = Cd * Area * (p1 / std::sqrt(T1)) * factor;
    } else {
        // Subsonic flow
        double term = std::max(0.0, std::pow(pr, 2.0 / k) - std::pow(pr, (k + 1.0) / k));
        double factor = std::sqrt((2.0 * k) / (R * (k - 1.0))) * std::sqrt(term);
        m_dot = Cd * Area * (p1 / std::sqrt(T1)) * factor;
    }
    return m_dot;
}

} // namespace

// ── Public input API ──────────────────────────────────────────────────────────

void MOCSolver::add_node(const NodeInput& n)  { node_inputs_.push_back(n); }
void MOCSolver::add_pipe(const PipeInput& p)  { pipe_inputs_.push_back(p); }

void MOCSolver::clear() {
    node_inputs_.clear();
    pipe_inputs_.clear();
    valve_schedules_.clear();
    pump_schedules_.clear();
    demand_schedules_.clear();
    head_schedules_.clear();
    control_rules_.clear();
    control_rule_states_.clear();
}

void MOCSolver::add_control_rule(const ControlRuleInput& rule) {
    control_rules_.push_back(rule);
}

void MOCSolver::clear_control_rules() {
    control_rules_.clear();
    control_rule_states_.clear();
}

double MOCSolver::get_node_head(const std::string& id) const {
    auto it = node_idx_map_.find(id);
    if (it == node_idx_map_.end()) {
        throw std::invalid_argument("Node not found: " + id);
    }
    const auto& ns = nodes_[it->second];
    const auto& n = ns.input;

    const auto& in_p_it = node_inflow_pipes_.find(n.id);
    const auto& out_p_it = node_outflow_pipes_.find(n.id);
    const auto& in_p = (in_p_it != node_inflow_pipes_.end()) ? in_p_it->second : std::vector<int>{};
    const auto& out_p = (out_p_it != node_outflow_pipes_.end()) ? out_p_it->second : std::vector<int>{};

    if (!in_p.empty()) {
        return pipes_[in_p[0]].H.back();
    } else if (!out_p.empty()) {
        return pipes_[out_p[0]].H.front();
    }
    return getInitialHead(ns);
}

double MOCSolver::get_node_pressure(const std::string& id) const {
    auto it = node_idx_map_.find(id);
    if (it == node_idx_map_.end()) {
        throw std::invalid_argument("Node not found: " + id);
    }
    const auto& ns = nodes_[it->second];
    return (get_node_head(id) - ns.input.elevation) / PSI_TO_FT;
}

double MOCSolver::get_node_head_by_idx(int idx) const {
    const auto& ns = nodes_[idx];
    if (!ns.inflow_pipes.empty()) {
        return pipes_[ns.inflow_pipes[0]].H.back();
    } else if (!ns.outflow_pipes.empty()) {
        return pipes_[ns.outflow_pipes[0]].H.front();
    }
    return getInitialHead(ns);
}

double MOCSolver::get_node_pressure_by_idx(int idx) const {
    const auto& ns = nodes_[idx];
    return (get_node_head_by_idx(idx) - ns.input.elevation) / PSI_TO_FT;
}

double MOCSolver::get_node_gas_volume(const std::string& id) const {
    auto it = node_idx_map_.find(id);
    if (it == node_idx_map_.end()) {
        throw std::invalid_argument("Node not found: " + id);
    }
    return nodes_[it->second].gas_volume_ft3;
}

double MOCSolver::get_node_tank_flow_gpm(const std::string& id) const {
    auto it = node_idx_map_.find(id);
    if (it == node_idx_map_.end()) {
        throw std::invalid_argument("Node not found: " + id);
    }
    return nodes_[it->second].tank_flow_gpm;
}

void MOCSolver::set_valve_setting(const std::string& id, double pct) {
    auto& node_input = requireNodeInputMutable(node_inputs_, id, "set_valve_setting()");
    requireNodeType(node_input, id, "set_valve_setting()", {NodeType::Valve, NodeType::Turbine, NodeType::PRV, NodeType::PSV, NodeType::PBV}, "Valve, Turbine, PRV, PSV, or PBV");
    node_input.current_setting = pct;
    auto it = node_idx_map_.find(id);
    if (it != node_idx_map_.end())
        nodes_[it->second].input.current_setting = pct;
}

void MOCSolver::set_node_type(const std::string& id, const std::string& type_str) {
    auto& node_input = requireNodeInputMutable(node_inputs_, id, "set_node_type()");
    NodeType new_type = parseNodeType(type_str);
    node_input.type = new_type;
    auto it = node_idx_map_.find(id);
    if (it != node_idx_map_.end()) {
        nodes_[it->second].input.type = new_type;
    }
}

void MOCSolver::set_pump_speed(const std::string& id, double pct) {
    auto& node_input = requireNodeInputMutable(node_inputs_, id, "set_pump_speed()");
    requireNodeType(node_input, id, "set_pump_speed()", {NodeType::Pump}, "Pump");
    node_input.current_speed = pct;
    auto it = node_idx_map_.find(id);
    if (it != node_idx_map_.end()) {
        nodes_[it->second].input.current_speed = pct;
        nodes_[it->second].command_speed = pct;
    }
}

void MOCSolver::set_pump_command_speed(const std::string& id, double pct) {
    auto& node_input = requireNodeInputMutable(node_inputs_, id, "set_pump_command_speed()");
    requireNodeType(node_input, id, "set_pump_command_speed()", {NodeType::Pump}, "Pump");
    node_input.current_speed = pct;
    auto it = node_idx_map_.find(id);
    if (it != node_idx_map_.end()) {
        nodes_[it->second].command_speed = pct;
    }
}

void MOCSolver::set_pump_power(const std::string& id, bool has_power) {
    auto& node_input = requireNodeInputMutable(node_inputs_, id, "set_pump_power()");
    requireNodeType(node_input, id, "set_pump_power()", {NodeType::Pump, NodeType::Turbine}, "Pump or Turbine");
    node_input.has_power = has_power;
    auto it = node_idx_map_.find(id);
    if (it != node_idx_map_.end())
        nodes_[it->second].input.has_power = has_power;
}

void MOCSolver::set_node_demand(const std::string& id, double demand_gpm) {
    auto& node_input = requireNodeInputMutable(node_inputs_, id, "set_node_demand()");
    requireNodeType(
        node_input,
        id,
        "set_node_demand()",
        {NodeType::Junction, NodeType::InflowNode, NodeType::OutflowNode},
        "Junction, InflowNode, or OutflowNode");
    node_input.demand = demand_gpm;
    auto it = node_idx_map_.find(id);
    if (it != node_idx_map_.end())
        nodes_[it->second].input.demand = demand_gpm;
}

void MOCSolver::set_node_head(const std::string& id, double head_ft) {
    auto& node_input = requireNodeInputMutable(node_inputs_, id, "set_node_head()");
    requireNodeType(node_input, id, "set_node_head()", {NodeType::Tank, NodeType::PressureBoundary}, "Tank or PressureBoundary");
    node_input.head = head_ft;
    auto it = node_idx_map_.find(id);
    if (it != node_idx_map_.end())
        nodes_[it->second].input.head = head_ft;
}

void MOCSolver::set_valve_schedule(const std::string& id,
                                   const std::vector<std::pair<double,double>>& schedule) {
    const auto& node_input = requireNodeInput(node_inputs_, id, "set_valve_schedule()");
    requireNodeType(node_input, id, "set_valve_schedule()", {NodeType::Valve, NodeType::Turbine}, "Valve or Turbine");
    validateSchedule(schedule, "set_valve_schedule()");
    valve_schedules_[id] = schedule;
}

void MOCSolver::set_pump_schedule(const std::string& id,
                                  const std::vector<std::pair<double,double>>& schedule) {
    const auto& node_input = requireNodeInput(node_inputs_, id, "set_pump_schedule()");
    requireNodeType(node_input, id, "set_pump_schedule()", {NodeType::Pump}, "Pump");
    validateSchedule(schedule, "set_pump_schedule()");
    pump_schedules_[id] = schedule;
}

void MOCSolver::set_demand_schedule(const std::string& id,
                                    const std::vector<std::pair<double,double>>& schedule) {
    const auto& node_input = requireNodeInput(node_inputs_, id, "set_demand_schedule()");
    requireNodeType(
        node_input,
        id,
        "set_demand_schedule()",
        {NodeType::Junction, NodeType::InflowNode, NodeType::OutflowNode},
        "Junction, InflowNode, or OutflowNode");
    validateSchedule(schedule, "set_demand_schedule()");
    demand_schedules_[id] = schedule;
}

void MOCSolver::set_head_schedule(const std::string& id,
                                  const std::vector<std::pair<double,double>>& schedule) {
    const auto& node_input = requireNodeInput(node_inputs_, id, "set_head_schedule()");
    requireNodeType(node_input, id, "set_head_schedule()", {NodeType::Tank, NodeType::PressureBoundary}, "Tank or PressureBoundary");
    validateSchedule(schedule, "set_head_schedule()");
    head_schedules_[id] = schedule;
}

// Linear interpolation helper for a (time, pct_open) schedule.
static double interpSchedule(
        const std::vector<std::pair<double,double>>& sched, double t) {
    if (sched.empty())              return 100.0;
    if (t <= sched.front().first)   return sched.front().second;
    if (t >= sched.back().first)    return sched.back().second;
    // Binary search for the bracketing interval.
    auto it = std::lower_bound(sched.begin(), sched.end(), t,
        [](const std::pair<double,double>& p, double v) { return p.first < v; });
    auto prev = std::prev(it);
    const double t0 = prev->first, t1 = it->first;
    const double frac = (t1 > t0) ? (t - t0) / (t1 - t0) : 1.0;
    return prev->second + (it->second - prev->second) * frac;
}

// ── Initial head for fixed-head / free-surface nodes ─────────────────────────

double MOCSolver::getInitialHead(const NodeState& ns) const {
    const auto& n = ns.input;
    switch (n.type) {
        case NodeType::Tank:
            // Use the imported piezometric head directly. EPANET loaders seed
            // Tank::head to elevation + initial level, while NodeInput::level
            // remains a legacy percentage field that may not reflect the
            // actual operating point.
            return n.head;
        case NodeType::PressureBoundary:
            return n.head;
        case NodeType::AirValve:
            // Closed at steady state; use the imported/assigned pipeline head.
            return n.head;
        case NodeType::Standpipe:
            return ns.surge_level_ft;
        case NodeType::HydropneumaticTank:
            // During initGrid the pipeline head at the connection == n.head
            // (steady state: no orifice pressure drop).
            return n.head;
        default:
            // For Junction / InflowNode / OutflowNode the user supplies the
            // initial piezometric head via NodeInput::head (ft HGL, not psi).
            // Default is 100 ft; for accurate ICs supply the EPANET value.
            return n.head;
    }
}

// ── Grid initialization ───────────────────────────────────────────────────────
// Mirrors transientWorker.js :: initGrid()

void MOCSolver::initGrid() {
    pipes_.clear();
    nodes_.clear();
    node_idx_map_.clear();
    pipe_idx_map_.clear();
    node_inflow_pipes_.clear();
    node_outflow_pipes_.clear();

    for (const auto& ni : node_inputs_) {
        node_inflow_pipes_ .emplace(ni.id, std::vector<int>{});
        node_outflow_pipes_.emplace(ni.id, std::vector<int>{});
    }

    // Build node state vector and lookup map
    nodes_.reserve(node_inputs_.size());
    for (int i = 0; i < static_cast<int>(node_inputs_.size()); ++i) {
        NodeState ns;
        ns.input = node_inputs_[i];
        if (ns.input.diameter <= 0.0) {
            ns.input.diameter = 1e-2;
        }
        if (ns.input.air_release_diameter <= 0.0) {
            ns.input.air_release_diameter = 1e-2;
        }
        if (ns.input.type == NodeType::Pump || ns.input.type == NodeType::Turbine) {
            if (ns.input.design_head <= 0.0) ns.input.design_head = 50.0;
            if (ns.input.design_flow <= 0.0) ns.input.design_flow = 100.0;
        }
        ns.air_loss_rate_gpm = 0.0;
        ns.air_cumulative_loss_gal = 0.0;
        ns.gas_pressure_psi = 0.0;
        ns.tank_flow_gpm = 0.0;
        if (ns.input.type == NodeType::Pump || ns.input.type == NodeType::Turbine)
            ns.command_speed = ns.input.current_speed;
        if (ns.input.type == NodeType::Standpipe) {
            ns.surge_level_ft = ns.input.head; // initial water-surface elevation (ft HGL)
            if (ns.input.tank_area <= 0.0) {
                ns.input.tank_area = 1e-4;
            }
        }
        if (ns.input.type == NodeType::HydropneumaticTank) {
            // Compute and store the polytropic gas constant:
            //   C = H_g_abs * V_g^n
            // At steady state there is no orifice flow, so H_P = H_tank:
            //   H_g_abs = (H_P_0 - elevation) + H_atm
            constexpr double H_ATM_FT = 33.9;  // ft  (1 atm = 14.696 psi)
            ns.gas_volume_ft3 = ns.input.gas_volume;
            const double H_g_abs0 = (ns.input.head - ns.input.elevation) + H_ATM_FT;
            ns.gas_constant = H_g_abs0 *
                std::pow(std::max(ns.gas_volume_ft3, 1e-9), ns.input.polytropic_n);
        }
        if (ns.input.type == NodeType::AirValve) {
            // Air valves start closed in the loaded steady-state operating
            // point. A trapped pocket is created only when the local junction
            // would otherwise go subatmospheric.
            ns.gas_volume_ft3 = std::max(0.0,
                std::min(ns.input.gas_volume, std::max(ns.input.tank_volume, 1e-6)));
            if (ns.gas_volume_ft3 > 1e-6) {
                constexpr double H_ATM_FT = 33.9;
                const double H_ref_abs = H_ATM_FT + ns.input.air_release_head;
                double p0 = RHO_WATER_G * H_ref_abs;
                ns.gas_constant = (p0 * ns.gas_volume_ft3) / (R_AIR * T_ATM_R);
            } else {
                ns.gas_constant = 0.0;
            }
        }
        if (ns.input.type == NodeType::Pump) {
            double q_d = ns.input.design_flow;
            double h_d = ns.input.design_head;
            double eff = std::max(0.01, ns.input.efficiency);
            double rpm = std::max(1.0, ns.input.speed_rpm);
            double bhp_d = (q_d * h_d) / (3960.0 * eff);
            ns.rated_torque_ftlb = (5252.0 * bhp_d) / rpm;
        }
        if (ns.input.type == NodeType::Turbine) {
            double q_d = ns.input.design_flow;
            double h_d = ns.input.design_head;
            double eff = std::max(0.01, ns.input.efficiency);
            double rpm = std::max(1.0, ns.input.speed_rpm);
            double bhp_d = (q_d * h_d * eff) / 3960.0;
            ns.rated_torque_ftlb = (5252.0 * bhp_d) / rpm;
        }
        nodes_.push_back(std::move(ns));
        node_idx_map_[node_inputs_[i].id] = i;
    }

    // Build pipe state vector
    pipes_.reserve(pipe_inputs_.size());
    for (int i = 0; i < static_cast<int>(pipe_inputs_.size()); ++i) {
        const auto& p = pipe_inputs_[i];
        PipeState ps;
        ps.from_id = p.from_node;
        ps.to_id   = p.to_node;
        ps.L       = p.length;

        const double d_in = std::max(p.diameter, 1e-2);
        const double flow_gpm_sanitized = (p.diameter <= 0.0) ? 0.0 : p.flow_gpm;
        const double diam_ft = d_in / 12.0;
        ps.D    = diam_ft;
        ps.area = M_PI_ * (diam_ft / 2.0) * (diam_ft / 2.0);

        // ── Wave speed (Joukowsky / Korteweg formula) ──────────────────────
        // a = a₀ / sqrt(1 + (K/E)·(D/e)·c)
        //   a₀ = 4860 ft/s (rigid-water acoustic speed)
        //   K  = 319 000 psi (bulk modulus of water)
        //   c  = 1 − ν²  (anchored pipe restraint factor)
        double wave_speed = 4000.0; // ft/s  default (rigid pipe approximation)
        if (p.youngs_modulus > 0.0) {
            const double K  = 319000.0;          // psi
            const double c  = 1.0 - p.poissons_ratio * p.poissons_ratio;
            const double a0 = 4860.0;            // ft/s
            const double t_in = std::max(p.wall_thickness, 1e-2);
            wave_speed = a0 / std::sqrt(
                1.0 + (K / p.youngs_modulus) * (d_in / t_in) * c);
        }

        // ── Courant condition: Cr = a·dt/dx = 1 ───────────────────────────
        // Round number of segments to nearest integer, then back-compute
        // the exact wave speed that gives Cr = 1.0 for that integer count.
        const double dx_target = wave_speed * dt_;
        const int    num_segs  = std::max(1, static_cast<int>(std::round(p.length / dx_target)));
        ps.a_wave    = (p.length / num_segs) / dt_; // adjusted wave speed
        ps.num_nodes = num_segs + 1;
        ps.k_minor   = std::max(0.0, p.minor_loss) / num_segs;

        // ── Darcy-Weisbach friction factor from Hazen-Williams ─────────────
        // Hf = 10.44 · L · Q^1.852 / (C^1.852 · D_in^4.871)  [all US units]
        const double Q_cfs     = flow_gpm_sanitized * GPM_TO_CFS;
        const double vel_init  = (ps.area > 1e-9) ? Q_cfs / ps.area : 0.0;
        double Hf_pipe_hw = 0.0;
        if (std::abs(flow_gpm_sanitized) > 1e-4) {
            Hf_pipe_hw = (10.44 * p.length * std::pow(std::abs(flow_gpm_sanitized), 1.852))
                       / (std::pow(p.roughness, 1.852) * std::pow(d_in, 4.871));
        }
        double f_calc = 0.02;
        if (std::abs(vel_init) > 1e-4) {
            f_calc = (Hf_pipe_hw * ps.D * 2.0 * G_FT_S2)
                   / (p.length * vel_init * vel_init);
        }
        ps.f = std::max(0.001, std::min(f_calc, 0.5));
        const double Hf_minor = std::max(0.0, p.minor_loss) * vel_init * vel_init / (2.0 * G_FT_S2);
        const double Hf_pipe = Hf_pipe_hw + Hf_minor;

        // ── Initial heads at pipe endpoints ───────────────────────────────
        double H_from = 100.0, H_to = 100.0;
        {
            auto fit = node_idx_map_.find(p.from_node);
            auto tit = node_idx_map_.find(p.to_node);
            if (fit != node_idx_map_.end()) H_from = getInitialHead(nodes_[fit->second]);
            if (tit != node_idx_map_.end()) H_to   = getInitialHead(nodes_[tit->second]);
        }

        // Determine which endpoints have a user-specified (fixed) piezometric
        // head vs. which are junction / inline-device nodes whose head must be
        // inferred from friction head loss.
        //
        // "Fixed-head" sources: Tank, PressureBoundary, Standpipe.
        // Everything else (Junction, Valve, Pump, Turbine, In/OutflowNode)
        // is treated as an inferred endpoint.
        auto is_fixed_head = [](NodeType t) {
            return t == NodeType::Tank || t == NodeType::PressureBoundary ||
                   t == NodeType::Standpipe || t == NodeType::HydropneumaticTank;
        };
        bool from_fixed = false, to_fixed = false;
        {
            auto fit = node_idx_map_.find(p.from_node);
            auto tit = node_idx_map_.find(p.to_node);
            if (fit != node_idx_map_.end()) from_fixed = is_fixed_head(nodes_[fit->second].input.type);
            if (tit != node_idx_map_.end()) to_fixed   = is_fixed_head(nodes_[tit->second].input.type);
        }

        const double sgn = (flow_gpm_sanitized >= 0.0) ? 1.0 : -1.0;
        double H_start = H_from, H_end = H_to;
        if (from_fixed && !to_fixed) {
            // Upstream reservoir drives; downstream head is friction-derived.
            H_start = H_from;
            H_end   = H_from - Hf_pipe * sgn;
        } else if (!from_fixed && to_fixed) {
            // Downstream reservoir drives; upstream head is friction-derived.
            H_end   = H_to;
            H_start = H_to + Hf_pipe * sgn;
        } else {
            // Both fixed (use exact endpoint heads) or both inferred (use
            // user-supplied heads from NodeInput::head with friction split).
            H_start = H_from;
            H_end   = H_to;

            // Special case: if one endpoint is a Valve or Pump, the stored
            // node head equals the upstream-face pressure (same as the
            // upstream junction head), NOT the downstream-face pressure.
            // Initialise the stub flat at the NON-device endpoint head so
            // that no spurious Joukowsky wave is generated at t = 0.
            //   Downstream stub (device is FROM-node): flat at H_to.
            //   Upstream   stub (device is TO-node  ): flat at H_from.
            {
                auto fit2 = node_idx_map_.find(p.from_node);
                auto tit2 = node_idx_map_.find(p.to_node);
                auto is_device = [](NodeType t) {
                    return t == NodeType::Valve || t == NodeType::CheckValve ||
                           t == NodeType::Pump || t == NodeType::PRV ||
                           t == NodeType::PSV || t == NodeType::PBV;
                };
                bool from_is_device = (fit2 != node_idx_map_.end()) &&
                                       is_device(nodes_[fit2->second].input.type);
                bool to_is_device   = (tit2 != node_idx_map_.end()) &&
                                       is_device(nodes_[tit2->second].input.type);

                if (from_is_device && !to_fixed) {
                    H_start = H_to;   // downstream stub → flat at downstream head
                } else if (to_is_device && !from_fixed) {
                    H_end = H_from;   // upstream stub   → flat at upstream head
                }
            }
        }

        buildPipeGridElevations(ps, p);
        initializePipeSegmentStates(ps);

        // ── Linear HGL + uniform velocity initial condition ───────────────
        ps.H.resize(ps.num_nodes);
        ps.V.resize(ps.num_nodes, vel_init);
        ps.V_filtered.resize(ps.num_nodes, vel_init); // filter starts at steady state
        for (int j = 0; j < ps.num_nodes; ++j) {
            const double t_frac = (ps.num_nodes > 1)
                ? static_cast<double>(j) / (ps.num_nodes - 1) : 0.0;
            ps.H[j] = H_start + (H_end - H_start) * t_frac;
        }

        pipe_idx_map_[p.id] = i;
        pipes_.push_back(std::move(ps));
    }

    // Build O(1) adjacency maps (used every time step)
    for (int i = 0; i < static_cast<int>(pipes_.size()); ++i) {
        node_outflow_pipes_[pipes_[i].from_id].push_back(i); // pipe leaves from_node
        node_inflow_pipes_ [pipes_[i].to_id  ].push_back(i); // pipe arrives at to_node
    }

    // Initialize control rule states
    control_rule_states_.clear();
    control_rule_states_.reserve(control_rules_.size());
    t_now_ = 0.0;

    for (const auto& rule : control_rules_) {
        ControlRuleState state;
        state.input = rule;
        state.integral_error = 0.0;
        state.previous_error = 0.0;
        state.has_prev_error = false;

        auto p_it = node_idx_map_.find(rule.monitored_node);
        auto v_it = node_idx_map_.find(rule.controlled_node);

        // Resolve and cache indices for speed
        auto mon_pipe_it = pipe_idx_map_.find(rule.monitored_pipe);
        state.monitored_pipe_idx = (mon_pipe_it != pipe_idx_map_.end()) ? mon_pipe_it->second : -1;
        state.monitored_node_idx = (p_it != node_idx_map_.end()) ? p_it->second : -1;
        state.action_node_idx = (v_it != node_idx_map_.end()) ? v_it->second : -1;

        if (rule.type == ControlType::PCV) {
            bool pump_on = false;
            if (p_it != node_idx_map_.end() && nodes_[p_it->second].input.type == NodeType::Pump) {
                pump_on = nodes_[p_it->second].command_speed > 0.0;
            }
            bool valve_open = false;
            if (v_it != node_idx_map_.end()) {
                valve_open = nodes_[v_it->second].input.current_setting > 0.0;
            }
            if (pump_on && valve_open) {
                state.pcv_phase = "running";
            } else if (!pump_on && !valve_open) {
                state.pcv_phase = "idle";
            } else if (pump_on && !valve_open) {
                state.pcv_phase = "opening";
                state.pcv_timer = 0.0;
            } else {
                state.pcv_phase = "closing";
                state.pcv_timer = 0.0;
            }
        }

        if (rule.type == ControlType::PID && rule.ki != 0.0) {
            double initial_val = 0.0;
            if (v_it != node_idx_map_.end()) {
                if (nodes_[v_it->second].input.type == NodeType::Pump) {
                    initial_val = nodes_[v_it->second].input.current_speed;
                } else {
                    initial_val = nodes_[v_it->second].input.current_setting;
                }
            }
            state.integral_error = initial_val / rule.ki;
        }

        state.last_active = false;
        if (rule.type == ControlType::Deadband || rule.type == ControlType::Threshold) {
            if (v_it != node_idx_map_.end()) {
                const auto& ctrl_node = nodes_[v_it->second];
                if (ctrl_node.input.type == NodeType::Pump) {
                    state.last_active = (ctrl_node.command_speed > 0.0);
                } else if (ctrl_node.input.type == NodeType::Valve || ctrl_node.input.type == NodeType::Turbine) {
                    state.last_active = (ctrl_node.input.current_setting > 0.0);
                }
            }
        }

        control_rule_states_.push_back(state);
    }

    // Populate O(1) indices directly in NodeState
    for (int i = 0; i < static_cast<int>(nodes_.size()); ++i) {
        auto& ns = nodes_[i];
        ns.inflow_pipes = node_inflow_pipes_[ns.input.id];
        ns.outflow_pipes = node_outflow_pipes_[ns.input.id];
    }

    // Resolve schedule maps to index-based ResolvedSchedule lists
    resolved_valve_schedules_.clear();
    for (const auto& [vid, sched] : valve_schedules_) {
        auto it = node_idx_map_.find(vid);
        if (it != node_idx_map_.end()) resolved_valve_schedules_.push_back({it->second, sched});
    }
    resolved_pump_schedules_.clear();
    for (const auto& [pid, sched] : pump_schedules_) {
        auto it = node_idx_map_.find(pid);
        if (it != node_idx_map_.end()) resolved_pump_schedules_.push_back({it->second, sched});
    }
    resolved_demand_schedules_.clear();
    for (const auto& [nid, sched] : demand_schedules_) {
        auto it = node_idx_map_.find(nid);
        if (it != node_idx_map_.end()) resolved_demand_schedules_.push_back({it->second, sched});
    }
    resolved_head_schedules_.clear();
    for (const auto& [nid, sched] : head_schedules_) {
        auto it = node_idx_map_.find(nid);
        if (it != node_idx_map_.end()) resolved_head_schedules_.push_back({it->second, sched});
    }

    // Pre-allocate newH_, newV_, and bndry_ to avoid per-timestep allocation overhead
    const int num_pipes = static_cast<int>(pipes_.size());
    newH_.resize(num_pipes);
    newV_.resize(num_pipes);
    for (int i = 0; i < num_pipes; ++i) {
        newH_[i].resize(pipes_[i].num_nodes);
        newV_[i].resize(pipes_[i].num_nodes);
    }
    bndry_.resize(num_pipes);
}

namespace {

constexpr double H_CAVITY_ENTER_TOL_FT = 0.10 * PSI_TO_FT;
constexpr double H_CAVITY_LEAVE_TOL_FT = 0.50 * PSI_TO_FT;

void stepInteriorSegmentDvcm(
    PipeSegmentState& seg,
    double H_candidate,
    double H_vap_j,
    double cavity_capacity_ft3,
    double dt_s,
    double segment_conductance_cfs_per_ft) {
    const bool enter_cavity = H_candidate <= (H_vap_j - H_CAVITY_ENTER_TOL_FT);
    const bool leave_cavity = H_candidate >= (H_vap_j + H_CAVITY_LEAVE_TOL_FT);
    const double imbalance_cfs =
        std::abs(segment_conductance_cfs_per_ft * (H_candidate - H_vap_j));
    const double max_step_delta_ft3 = 0.25 * cavity_capacity_ft3;
    const double bounded_step_delta_ft3 = std::min(imbalance_cfs * dt_s, max_step_delta_ft3);

    switch (seg.cavity_regime) {
        case CavityRegime::LiquidFull:
            if (enter_cavity) {
                seg.cavity_regime = CavityRegime::CavityActive;
                seg.cavity_active = true;
                seg.cavity_volume_ft3 = std::min(
                    cavity_capacity_ft3,
                    std::max(0.0, seg.cavity_volume_ft3 + bounded_step_delta_ft3));
            } else {
                seg.cavity_active = false;
                seg.cavity_volume_ft3 = 0.0;
                seg.cavity_consecutive_collapses = 0;
            }
            break;
        case CavityRegime::CavityActive:
            if (leave_cavity) {
                seg.cavity_regime = CavityRegime::CollapseTransition;
                seg.cavity_active = false;
                seg.cavity_volume_ft3 =
                    std::max(0.0, seg.cavity_volume_ft3 - bounded_step_delta_ft3);
                seg.cavity_collapsed_this_step = true;
                seg.cavity_collapse_count += 1;
                seg.cavity_consecutive_collapses += 1;
            } else {
                seg.cavity_active = true;
                seg.cavity_volume_ft3 = std::min(
                    cavity_capacity_ft3,
                    std::max(0.0, seg.cavity_volume_ft3 + bounded_step_delta_ft3));
            }
            break;
        case CavityRegime::CollapseTransition:
            if (seg.cavity_volume_ft3 <= bounded_step_delta_ft3 &&
                H_candidate >= (H_vap_j - H_CAVITY_ENTER_TOL_FT)) {
                seg.cavity_regime = CavityRegime::LiquidFull;
                seg.cavity_active = false;
                seg.cavity_volume_ft3 = 0.0;
                seg.cavity_consecutive_collapses = 0;
            } else {
                seg.cavity_active = false;
                seg.cavity_volume_ft3 =
                    std::max(0.0, seg.cavity_volume_ft3 - bounded_step_delta_ft3);
            }
            break;
    }
}

[[noreturn]] void throwInteriorDvcmInstability(
    const std::string& pipe_id,
    int grid_index,
    const std::string& quantity) {
    throw std::runtime_error(
        "Numerical instability: NaN/Inf detected in interior " + quantity
        + " for pipe '" + pipe_id + "' at grid index " + std::to_string(grid_index));
}

void throwIfInvalidInteriorSegmentState(
    const std::string& pipe_id,
    int grid_index,
    double Hj,
    double Vj,
    const PipeSegmentState& seg,
    double cavity_capacity_ft3) {
    if (std::isnan(Hj) || std::isinf(Hj)) {
        throwInteriorDvcmInstability(pipe_id, grid_index, "head");
    }
    if (std::isnan(Vj) || std::isinf(Vj)) {
        throwInteriorDvcmInstability(pipe_id, grid_index, "velocity");
    }
    if (std::isnan(seg.cavity_volume_ft3) || std::isinf(seg.cavity_volume_ft3)) {
        throwInteriorDvcmInstability(pipe_id, grid_index, "cavity volume");
    }
    if (seg.cavity_volume_ft3 < -1e-9) {
        throw std::runtime_error(
            "Non-physical state: Negative interior cavity volume for pipe '"
            + pipe_id + "' at grid index " + std::to_string(grid_index));
    }
    if (seg.cavity_volume_ft3 > cavity_capacity_ft3 + 1e-9) {
        throw std::runtime_error(
            "Non-physical state: Interior cavity volume exceeds segment capacity for pipe '"
            + pipe_id + "' at grid index " + std::to_string(grid_index));
    }
}

} // namespace

// ── Single MOC time step ──────────────────────────────────────────────────────
// Mirrors transientWorker.js :: stepMOC()

void MOCSolver::stepMOC() {
    evaluateControlRules(t_now_);

    // Enforce VFD Pump Speed acceleration/deceleration limits
    for (int ni = 0; ni < static_cast<int>(nodes_.size()); ++ni) {
        auto& ns = nodes_[ni];
        if (ns.input.type == NodeType::Pump) {
            bool under_pcv_close = false;
            for (const auto& state : control_rule_states_) {
                if (state.input.type == ControlType::PCV &&
                    state.monitored_node_idx == ni &&
                    state.pcv_phase == "closing") {
                    under_pcv_close = true;
                    break;
                }
            }
            if (under_pcv_close) {
                continue;
            }
            if (ns.input.has_power) {
                double s_current = ns.input.current_speed;
                double s_cmd = ns.command_speed;
                if (s_current != s_cmd) {
                    if (ns.input.ramp_time <= 0.0) {
                        ns.input.current_speed = s_cmd;
                    } else {
                        double delta_s_max = (100.0 / ns.input.ramp_time) * dt_;
                        if (s_current < s_cmd) {
                            ns.input.current_speed = std::min(s_cmd, s_current + delta_s_max);
                        } else {
                            ns.input.current_speed = std::max(s_cmd, s_current - delta_s_max);
                        }
                    }
                }
            }
        }
    }

    const double g          = G_FT_S2;
    const double alpha_filt = dt_ / usf_tau_; // IIR coefficient: dt / τ_BL

    const int num_pipes = static_cast<int>(pipes_.size());
    const int num_nodes = static_cast<int>(nodes_.size());

    // Use class-level pre-allocated vectors to avoid per-timestep allocation overhead
    auto& newH = newH_;
    auto& newV = newV_;
    auto& bndry = bndry_;

    // ── Per-pipe: IIR filter + interior C± equations + boundary chars ────────

    for (int i = 0; i < num_pipes; ++i) {
        auto& ps  = pipes_[i];
        if (enable_interior_dvcm_) {
            for (auto& seg : ps.segments) {
                seg.cavity_collapsed_this_step = false;
            }
        }
        const int  N    = ps.num_nodes;
        const double dx = ps.a_wave * dt_;
        const double B  = ps.a_wave / g;               // ft·s/ft² = s/ft
        const double R  = (ps.f * dx / ps.D + ps.k_minor) / (2.0 * g); // distributed steady + minor-loss resistance
        // Brunone (1991) unsteady-friction scale:  k_u = k_Bru_eff * B  [units: s]
        // Vardy-Brown (1996):  k_Bru = C*/sqrt(π),  C* = 7.41/Re^0.352  (turbulent)
        // Typical range: 0.02–0.15.
        //
        // k_Bru_ < 0  → compute dynamically from instantaneous Reynolds number (default)
        // k_Bru_ = 0  → steady friction only
        // k_Bru_ > 0  → user-supplied static value
        //
        // BUG HISTORY: was  k_u = dt_ * B  (timestep-dependent, 10–50× too large).
        //   That coefficient has units s² not s and amplified the first Joukowsky
        //   peak ~22 % rather than providing mild physical damping.  Fixed here by
        //   decoupling k_u from the timestep and using the correct Brunone formula.
        double k_Bru_eff;
        if (k_Bru_ < 0.0) {
            // Dynamic Vardy-Brown: sample velocity at pipe midpoint
            const int    mid   = ps.num_nodes / 2;
            const double Re    = std::abs(ps.V[mid]) * ps.D / NU_FT2_S;
            const double C_star = Re > 100.0 ? 7.41 / std::pow(Re, 0.352) : 0.0;
            k_Bru_eff = C_star / std::sqrt(M_PI_);
        } else {
            k_Bru_eff = k_Bru_;          // static (0 = no USF, >0 = calibrated)
        }
        const double k_u = k_Bru_eff * B * (dt_ / 0.01);             // unsteady-friction scale  [s]

        // ── IIR low-pass filter ───────────────────────────────────────────
        // V̄_j ← V̄_j + (V_j − V̄_j) · α
        // The residual (V − V̄) is the high-frequency (transient) acceleration
        // component, used to approximate the Zielke boundary-layer shear.
        for (int j = 0; j < N; ++j)
            ps.V_filtered[j] += (ps.V[j] - ps.V_filtered[j]) * alpha_filt;

        // ── Interior nodes  j = 1 … N-2  (C+ from left, C- from right) ───
        for (int j = 1; j < N - 1; ++j) {
            const double H_A = ps.H[j-1], V_A = ps.V[j-1];
            const double H_B = ps.H[j+1], V_B = ps.V[j+1];
            const double vt_A = V_A - ps.V_filtered[j-1];
            const double vt_B = V_B - ps.V_filtered[j+1];

            const double C_P = H_A + B*V_A  - (R*V_A*std::abs(V_A) + k_u*vt_A);
            const double C_M = H_B - B*V_B  + (R*V_B*std::abs(V_B) + k_u*vt_B);

            double Hj = (C_P + C_M) / 2.0;
            double Vj = (C_P - C_M) / (2.0 * B);

            if (enable_interior_dvcm_ && cavitation_model_ == CavitationModel::DVCM) {
                auto& seg = ps.segments[static_cast<std::size_t>(j)];
                const double H_vap_j = pipeGridVaporHeadFt(ps, j);
                const double cavity_capacity_ft3 = dx * ps.area;
                const double segment_conductance = 2.0 * ps.area / B;
                stepInteriorSegmentDvcm(
                    seg,
                    Hj,
                    H_vap_j,
                    cavity_capacity_ft3,
                    dt_,
                    segment_conductance);

                if (seg.cavity_regime != CavityRegime::LiquidFull && Hj < H_vap_j) {
                    Hj = H_vap_j;
                    Vj = (C_P - H_vap_j) / B;
                }

                throwIfInvalidInteriorSegmentState(
                    pipe_inputs_[i].id,
                    j,
                    Hj,
                    Vj,
                    seg,
                    cavity_capacity_ft3);
            } else if (cavitation_model_ == CavitationModel::LegacyClamp && ps.has_terrain_elevation) {
                // LegacyClamp on terrain reaches: vapor floor uses local z[j], not node z.
                const double H_vap_j = pipeGridVaporHeadFt(ps, j);
                if (Hj < H_vap_j) {
                    Hj = H_vap_j;
                    Vj = (C_P - H_vap_j) / B;
                }
            }

            newH[i][j] = Hj;
            newV[i][j] = Vj;
        }

        // ── Pipe-end boundary characteristics ────────────────────────────
        // C_P arrives at the downstream end  (from node N-2)
        // C_M arrives at the upstream end    (from node 1)
        const double V_up = ps.V[N-2]; // penultimate node → downstream BC
        const double V_dn = ps.V[1];   // second node      → upstream BC
        const double damp_up = k_u * (V_up - ps.V_filtered[N-2]);
        const double damp_dn = k_u * (V_dn - ps.V_filtered[1]);

        bndry[i].area = ps.area;
        bndry[i].B    = B;
        bndry[i].C_P  = ps.H[N-2] + B*V_up - (R*V_up*std::abs(V_up) + damp_up);
        bndry[i].C_M  = ps.H[1]   - B*V_dn + (R*V_dn*std::abs(V_dn) + damp_dn);
    }

    // ── Node boundary conditions ──────────────────────────────────────────────

    for (int ni = 0; ni < num_nodes; ++ni) {
        auto& ns = nodes_[ni];
        auto& n  = ns.input;

        const auto& in_pipes  = ns.inflow_pipes; // pipes arriving
        const auto& out_pipes = ns.outflow_pipes; // pipes leaving

        if (in_pipes.empty() && out_pipes.empty()) continue;

        const double H_vap = n.elevation + p_vapor_; // cavitation head (ft)

        // Convenience lambdas for setting a pipe's boundary node values
        auto set_downstream = [&](int pi, double H_P) {
            const int last = pipes_[pi].num_nodes - 1;
            newH[pi][last] = H_P;
            newV[pi][last] = (bndry[pi].C_P - H_P) / bndry[pi].B;
        };
        auto set_upstream = [&](int pi, double H_P) {
            newH[pi][0] = H_P;
            newV[pi][0] = (H_P - bndry[pi].C_M) / bndry[pi].B;
        };

        // Quadratic solve helper: K_eq·Q² + B_eq·Q − C_eq = 0
        auto quadratic_Q = [&](double Keq, double Beq, double Ceq) -> double {
            if (Keq < 1e-4) return Ceq / Beq;
            if (Ceq >= 0.0)
                return (-Beq + std::sqrt(std::max(0.0, Beq*Beq + 4.0*Keq*Ceq))) / (2.0*Keq);
            else
                return ( Beq - std::sqrt(std::max(0.0, Beq*Beq - 4.0*Keq*Ceq))) / (2.0*Keq);
        };

        ns.cavity_collapsed_this_step = false;

        switch (n.type) {

        // ── Fixed-head boundaries ──────────────────────────────────────────
        case NodeType::Tank:
        case NodeType::PressureBoundary: {
            const double H_f = getInitialHead(ns);
            for (int pi : in_pipes)  set_downstream(pi, H_f);
            for (int pi : out_pipes) set_upstream(pi, H_f);
            break;
        }

        // ── Open surge tank / standpipe (free surface) ───────────────────
        // H = current water-surface elevation (= HGL for open-to-atm tank).
        // dH/dt = Q_net / A_s   (continuity, Wylie & Streeter §7.3)
        case NodeType::Standpipe: {
            const double H_t = ns.surge_level_ft;
            double net_Q = 0.0; // CFS flowing into the tank (positive = rising)
            for (int pi : in_pipes) {
                const int last = pipes_[pi].num_nodes - 1;
                newH[pi][last] = H_t;
                const double V_new = (bndry[pi].C_P - H_t) / bndry[pi].B;
                newV[pi][last] = V_new;
                net_Q += V_new * pipes_[pi].area;
            }
            for (int pi : out_pipes) {
                newH[pi][0] = H_t;
                const double V_new = (H_t - bndry[pi].C_M) / bndry[pi].B;
                newV[pi][0] = V_new;
                net_Q -= V_new * pipes_[pi].area;
            }
            // dL/dt = Q_net / A_tank
            ns.surge_level_ft += (net_Q / n.tank_area) * dt_;
            break;
        }

        // ── Hydropneumatic surge tank (closed, pressurized vessel) ────────
        // Physics (Wylie & Streeter §7.5):
        //   Polytropic gas law:  C = H_g_abs · V_g^n   (constant, set at init)
        //   Orifice headloss:    H_P − H_tank = K·Q·|Q|
        //     K_in  = 1/(2g·(C_in ·A_ori)²)   (water entering, gas compresses)
        //     K_out = 1/(2g·(C_out·A_ori)²)   (water leaving,  gas expands)
        //   Quadratic in Q_net:  sum_AB·K·Q² + Q − C_eq = 0
        //     where  C_eq = sum_AB_C − sum_AB·H_tank
        case NodeType::HydropneumaticTank: {
            constexpr double H_ATM_FT = 33.9;  // ft  (1 atm = 14.696 psi)

            // Orifice area — uses NodeInput::diameter (inches)
            const double d_ft  = n.diameter / 12.0;
            const double A_ori = M_PI_ * (d_ft / 2.0) * (d_ft / 2.0);

            // Aggregate MOC characteristics from all connecting pipes
            double sum_AB   = 0.0;
            double sum_AB_C = 0.0;
            for (int pi : in_pipes) {
                const double AB = bndry[pi].area / bndry[pi].B;
                sum_AB_C += AB * bndry[pi].C_P;
                sum_AB   += AB;
            }
            for (int pi : out_pipes) {
                const double AB = bndry[pi].area / bndry[pi].B;
                sum_AB_C += AB * bndry[pi].C_M;
                sum_AB   += AB;
            }
            if (sum_AB < 1e-12) break;  // isolated node — skip

            // Current tank piezometric head from polytropic gas law (explicit):
            //   H_g_abs = C / V_g^n
            //   H_tank  = H_g_abs − H_atm + elevation   (gauge piezometric, ft)
            const double H_g_abs = ns.gas_constant /
                std::pow(std::max(ns.gas_volume_ft3, 1e-9), n.polytropic_n);
            const double H_tank  = H_g_abs - H_ATM_FT + n.elevation;

            // Orifice loss coefficients  K = 1 / (2g·(Cd·A)²)
            const double K_in  = 1.0 / (2.0 * g *
                std::pow(std::max(n.loss_coeff_in,  1e-9) * A_ori, 2.0));
            const double K_out = 1.0 / (2.0 * g *
                std::pow(std::max(n.loss_coeff_out, 1e-9) * A_ori, 2.0));

            // C_eq = sum_AB_C − sum_AB·H_tank  (positive = pipeline > tank → inflow)
            const double C_eq = sum_AB_C - sum_AB * H_tank;
            const double K    = (C_eq >= 0.0) ? K_in : K_out;  // asymmetric
            const double Keq  = K * sum_AB;

            // Check if already at limits and flow direction is trying to violate the bounds:
            const bool is_empty = (ns.gas_volume_ft3 >= n.tank_volume - 1e-5);
            const bool is_full  = (ns.gas_volume_ft3 <= 1e-5);

            double Q_net = 0.0;
            if (is_empty && C_eq < 0.0) {
                // Tank is empty, trying to draw water out -> clamp to 0
                Q_net = 0.0;
            } else if (is_full && C_eq > 0.0) {
                // Tank is full, trying to push water in -> clamp to 0
                Q_net = 0.0;
            } else {
                // Solve standard quadratic: Keq·Q² + Q − C_eq = 0
                if (Keq < 1e-12) {
                    Q_net = C_eq;  // zero orifice resistance → H_P = H_tank
                } else if (C_eq >= 0.0) {
                    Q_net = (-1.0 + std::sqrt(1.0 + 4.0 * Keq * C_eq)) / (2.0 * Keq);
                } else {
                    Q_net = ( 1.0 - std::sqrt(1.0 - 4.0 * Keq * C_eq)) / (2.0 * Keq);
                }

                // Limit Q_net if it would cross the empty/full boundary within this time step
                if (Q_net > 0.0) {
                    // Inflow (water enters, gas volume V_g decreases)
                    const double max_inflow = (ns.gas_volume_ft3 - 1e-5) / dt_;
                    if (max_inflow < 0.0) {
                        Q_net = 0.0;
                    } else if (Q_net > max_inflow) {
                        Q_net = max_inflow;
                    }
                } else if (Q_net < 0.0) {
                    // Outflow (water leaves, gas volume V_g increases)
                    const double max_outflow = (ns.gas_volume_ft3 - (n.tank_volume - 1e-5)) / dt_;
                    if (max_outflow > 0.0) {
                        Q_net = 0.0;
                    } else if (Q_net < max_outflow) {
                        Q_net = max_outflow;
                    }
                }
            }

            // Pipeline head at the connection node
            double H_P = (sum_AB_C - Q_net) / sum_AB;
            if (H_P < H_vap) {
                H_P   = H_vap;
                Q_net = sum_AB_C - sum_AB * H_vap;
            }

            for (int pi : in_pipes)  set_downstream(pi, H_P);
            for (int pi : out_pipes) set_upstream  (pi, H_P);

            // Update gas volume:  Q_net > 0 ⟹ water enters ⟹ V_g decreases
            ns.gas_volume_ft3 = std::max(0.0,
                std::min(ns.gas_volume_ft3 - Q_net * dt_, n.tank_volume));

            // Store transient metrics
            const double H_g_abs_new = ns.gas_constant /
                std::pow(std::max(ns.gas_volume_ft3, 1e-9), n.polytropic_n);
            ns.gas_pressure_psi = (H_g_abs_new - 33.9) * 0.433;
            ns.tank_flow_gpm = Q_net / GPM_TO_CFS;
            break;
        }

        // ── Air valve with finite admission / release and trapped air ─────
        // The node contains a trapped air pocket. Water exchange with the pipe
        // changes pocket volume, while the air valve exchanges mass with the
        // atmosphere through asymmetric orifices:
        //   - large admission port: NodeInput::diameter
        //   - small release port  : NodeInput::air_release_diameter
        //
        // Current implementation uses an isothermal ideal-gas surrogate
        // M = H_abs * V, which is sufficient to capture finite inflow/outflow
        // and delayed repressurisation from a trapped pocket.
        case NodeType::AirValve: {
            constexpr double H_ATM_FT = 33.9;
            const double H_ref = n.elevation + n.air_release_head;
            const double H_ref_abs = H_ATM_FT + n.air_release_head;

            double sum_AB_C = 0.0, sum_AB = 0.0;
            for (int pi : in_pipes) {
                const double AB = bndry[pi].area / bndry[pi].B;
                sum_AB_C += AB * bndry[pi].C_P;
                sum_AB   += AB;
            }
            for (int pi : out_pipes) {
                const double AB = bndry[pi].area / bndry[pi].B;
                sum_AB_C += AB * bndry[pi].C_M;
                sum_AB   += AB;
            }
            const double Q_dem = n.demand * GPM_TO_CFS;
            const double H_junc = (sum_AB > 1e-12)
                ? (sum_AB_C - Q_dem) / sum_AB
                : getInitialHead(ns);

            const bool pocket_active = ns.gas_volume_ft3 > 1e-6;
            if (!pocket_active && H_junc >= H_ref) {
                const double H_closed = std::max(H_vap, H_junc);
                for (int pi : in_pipes)  set_downstream(pi, H_closed);
                for (int pi : out_pipes) set_upstream  (pi, H_closed);
                ns.actual_demand = n.demand;
                ns.gas_volume_ft3 = 0.0;
                ns.gas_constant = 0.0;
                break;
            }

            if (!pocket_active) {
                ns.gas_volume_ft3 = std::max(1e-4, n.gas_volume);
                const double p0 = RHO_WATER_G * H_ref_abs;
                ns.gas_constant = (p0 * ns.gas_volume_ft3) / (R_AIR * T_ATM_R);
            }

            const double p_pocket = (std::max(1e-12, ns.gas_constant) * R_AIR * T_ATM_R) / std::max(ns.gas_volume_ft3, 1e-6);
            const double H_abs = std::max(1e-6, p_pocket / RHO_WATER_G);
            double H_P = n.elevation + H_abs - H_ATM_FT;
            const bool clamp_to_vapor =
                (cavitation_model_ == CavitationModel::LegacyClamp) ||
                (cavitation_model_ == CavitationModel::DVCM);
            if (clamp_to_vapor && H_P < H_vap) H_P = H_vap;

            double net_Q = 0.0; // CFS into the air chamber (positive compresses air)
            for (int pi : in_pipes) {
                const int last = pipes_[pi].num_nodes - 1;
                newH[pi][last] = H_P;
                const double V_new = (bndry[pi].C_P - H_P) / bndry[pi].B;
                newV[pi][last] = V_new;
                net_Q += V_new * pipes_[pi].area;
            }
            for (int pi : out_pipes) {
                newH[pi][0] = H_P;
                const double V_new = (H_P - bndry[pi].C_M) / bndry[pi].B;
                newV[pi][0] = V_new;
                net_Q -= V_new * pipes_[pi].area;
            }

            const double chamber_vol = std::max(n.tank_volume, 1e-6);
            const double V_after_water = std::max(1e-6,
                std::min(ns.gas_volume_ft3 - net_Q * dt_, chamber_vol));

            const double admit_d_ft = n.diameter / 12.0;
            const double release_d_ft = n.air_release_diameter / 12.0;
            const double A_admit = M_PI_ * std::pow(admit_d_ft / 2.0, 2.0);
            const double A_release = M_PI_ * std::pow(release_d_ft / 2.0, 2.0);

            double M_after_air = ns.gas_constant;
            double Q_air_cfs = 0.0;
            const double rho_atm = (RHO_WATER_G * H_ATM_FT) / (R_AIR * T_ATM_R);

            if (H_abs < H_ref_abs - 1e-9) {
                const double p_atm_abs = RHO_WATER_G * H_ref_abs;
                const double pr = p_pocket / p_atm_abs;
                const double m_dot_in = computeCompressibleAirFlow(std::max(n.loss_coeff_in, 1e-9), A_admit, p_atm_abs, pr, T_ATM_R);
                M_after_air += m_dot_in * dt_;
            } else if (H_abs > H_ref_abs + 1e-9 && V_after_water > 1e-6) {
                const double p_atm_abs = RHO_WATER_G * H_ref_abs;
                const double pr = p_atm_abs / p_pocket;
                const double m_dot_out = computeCompressibleAirFlow(std::max(n.loss_coeff_out, 1e-9), A_release, p_pocket, pr, T_ATM_R);
                M_after_air = std::max(1e-12, M_after_air - m_dot_out * dt_);
                Q_air_cfs = m_dot_out / rho_atm;
            }

            if (V_after_water <= 5e-4) {
                ns.gas_volume_ft3 = 0.0;
                ns.gas_constant = 0.0;
                ns.air_loss_rate_gpm = 0.0;
            } else {
                ns.gas_volume_ft3 = V_after_water;
                ns.gas_constant = M_after_air;
                ns.air_loss_rate_gpm = Q_air_cfs * 448.831;
                ns.air_cumulative_loss_gal += Q_air_cfs * dt_ * 7.48052;
            }
            ns.gas_pressure_psi = (H_abs - 33.9) * 0.433;
            ns.actual_demand = n.demand;
            break;
        }

        // ── Check valve ────────────────────────────────────────────────────
        // Ideal one-way inline device: forward flow only, zero loss when open.
        // Reverse-flow tendency closes the device and enforces Q = 0 while
        // allowing a head discontinuity across the valve.
        case NodeType::CheckValve: {
            // Closure dynamics implementation
            if (in_pipes.size() == 1 && out_pipes.size() == 1) {
                const int bIn  = in_pipes[0];
                const int bOut = out_pipes[0];
                const double B_eq = (bndry[bIn].B  / bndry[bIn].area)
                                  + (bndry[bOut].B / bndry[bOut].area);

                // Compute flow tendency (positive = forward, negative = reverse)
                double C_eq = n.flipped ? (bndry[bOut].C_M - bndry[bIn].C_P)
                                       : (bndry[bIn].C_P - bndry[bOut].C_M);
                double Q_tendency = (B_eq > 1e-12) ? (C_eq / B_eq) : 0.0;

                // Closure dynamics integration (simple first-order, can extend to 2nd order)
                double closure_time = std::max(1e-6, n.closure_time);
                double pos = ns.valve_position;
                double vel = ns.valve_velocity;
                bool closing = ns.is_closing;

                // Detect closure/opening trigger
                if (Q_tendency < -1e-8) {
                    closing = true;
                } else if (Q_tendency > 1e-8) {
                    closing = false;
                }

                // Integrate position (exact exponential update)
                if (closing) {
                    // Exponential decay toward 0
                    pos = pos * std::exp(-dt_ / closure_time);
                    vel = (pos - ns.valve_position) / dt_;
                } else {
                    // Exponential rise toward 1
                    pos = 1.0 - (1.0 - pos) * std::exp(-dt_ / closure_time);
                    vel = (pos - ns.valve_position) / dt_;
                }
                pos = std::clamp(pos, 0.0, 1.0);

                ns.valve_position = pos;
                ns.valve_velocity = vel;
                ns.is_closing = closing;

                // Effective loss coefficient (quadratic)
                // K_eff = (1/pos)^2 - 1. When pos = 1, K = 0. When pos -> 0, K -> 1e12
                double K = (pos > 1e-3) ? (1.0 / (pos * pos) - 1.0) : 1e12;
                const double diam_ft = n.diameter / 12.0;
                const double A_v     = M_PI_ * (diam_ft / 2.0) * (diam_ft / 2.0);
                const double K_eq    = K / (2.0 * g * A_v * A_v);

                // Solve for Q using the quadratic solver
                // Since pipe flows are solved in the physical direction (A to B),
                // we use the physical C_eq = bIn.C_P - bOut.C_M
                double C_eq_phys = bndry[bIn].C_P - bndry[bOut].C_M;
                double Q = quadratic_Q(K_eq, B_eq, C_eq_phys);

                // Enforce one-way check valve blocking
                if (n.flipped) {
                    Q = std::min(0.0, Q); // Only allow flow from B to A (negative flow)
                } else {
                    Q = std::max(0.0, Q); // Only allow flow from A to B (positive flow)
                }

                double H_up = bndry[bIn].C_P  - (bndry[bIn].B  / bndry[bIn].area)  * Q;
                double H_dn = bndry[bOut].C_M + (bndry[bOut].B / bndry[bOut].area) * Q;

                double H_up_candidate = H_up;
                double H_dn_candidate = H_dn;
                double Q_candidate = Q;

                if (cavitation_model_ == CavitationModel::DVCM) {
                    constexpr double H_CAVITY_ENTER_TOL = 0.10 * PSI_TO_FT;
                    constexpr double H_CAVITY_LEAVE_TOL = 0.50 * PSI_TO_FT;
                    const bool enter_cavity = (H_up_candidate <= (H_vap - H_CAVITY_ENTER_TOL)) || (H_dn_candidate <= (H_vap - H_CAVITY_ENTER_TOL));
                    const bool leave_cavity = (H_up_candidate >= (H_vap + H_CAVITY_LEAVE_TOL)) && (H_dn_candidate >= (H_vap + H_CAVITY_LEAVE_TOL));

                    double H_up_clamped = H_up_candidate;
                    double H_dn_clamped = H_dn_candidate;
                    double Q_clamped = Q_candidate;

                    if (H_dn_clamped < H_vap) {
                        H_dn_clamped = H_vap;
                        const double Bc  = bndry[bIn].B / bndry[bIn].area;
                        Q_clamped    = quadratic_Q(K_eq, Bc, bndry[bIn].C_P - H_vap);
                        if (n.flipped) Q_clamped = std::min(0.0, Q_clamped);
                        else           Q_clamped = std::max(0.0, Q_clamped);
                        H_up_clamped = bndry[bIn].C_P - Bc * Q_clamped;
                    }
                    if (H_up_clamped < H_vap) {
                        H_up_clamped = H_vap;
                        const double Bc  = bndry[bOut].B / bndry[bOut].area;
                        Q_clamped    = quadratic_Q(K_eq, Bc, H_vap - bndry[bOut].C_M);
                        if (n.flipped) Q_clamped = std::min(0.0, Q_clamped);
                        else           Q_clamped = std::max(0.0, Q_clamped);
                        H_dn_clamped = bndry[bOut].C_M + Bc * Q_clamped;
                    }
                    const double flow_in_vap = (bndry[bIn].C_P - H_vap) / (bndry[bIn].B / bndry[bIn].area);
                    const double flow_out_vap = (H_vap - bndry[bOut].C_M) / (bndry[bOut].B / bndry[bOut].area);
                    const double imbalance_cfs = std::abs(flow_in_vap - flow_out_vap);

                    const double cavity_capacity_ft3 = 0.5 * pipes_[bIn].area * pipes_[bIn].L + 0.5 * pipes_[bOut].area * pipes_[bOut].L;
                    const double max_step_delta_ft3 = 0.25 * cavity_capacity_ft3;
                    const double bounded_step_delta_ft3 = std::min(imbalance_cfs * dt_, max_step_delta_ft3);

                    ns.cavity_collapsed_this_step = false;

                    switch (ns.cavity_regime) {
                        case CavityRegime::LiquidFull:
                            if (enter_cavity) {
                                ns.cavity_regime = CavityRegime::CavityActive;
                                ns.cavity_active = true;
                                ns.cavity_volume_ft3 = std::min(
                                    cavity_capacity_ft3,
                                    std::max(0.0, ns.cavity_volume_ft3 + bounded_step_delta_ft3));
                            } else {
                                ns.cavity_active = false;
                                ns.cavity_volume_ft3 = 0.0;
                                ns.cavity_consecutive_collapses = 0;
                            }
                            break;
                        case CavityRegime::CavityActive:
                            if (leave_cavity) {
                                ns.cavity_regime = CavityRegime::CollapseTransition;
                                ns.cavity_active = false;
                                ns.cavity_volume_ft3 = std::max(0.0, ns.cavity_volume_ft3 - bounded_step_delta_ft3);
                                ns.cavity_collapsed_this_step = true;
                                ns.cavity_collapse_count += 1;
                                ns.cavity_consecutive_collapses += 1;
                            } else {
                                ns.cavity_active = true;
                                ns.cavity_volume_ft3 = std::min(
                                    cavity_capacity_ft3,
                                    std::max(0.0, ns.cavity_volume_ft3 + bounded_step_delta_ft3));
                            }
                            break;
                        case CavityRegime::CollapseTransition:
                            if (ns.cavity_volume_ft3 <= bounded_step_delta_ft3 &&
                                H_up_candidate >= (H_vap - H_CAVITY_ENTER_TOL) &&
                                H_dn_candidate >= (H_vap - H_CAVITY_ENTER_TOL)) {
                                ns.cavity_regime = CavityRegime::LiquidFull;
                                ns.cavity_active = false;
                                ns.cavity_volume_ft3 = 0.0;
                                ns.cavity_consecutive_collapses = 0;
                            } else {
                                ns.cavity_active = false;
                                ns.cavity_volume_ft3 = std::max(0.0, ns.cavity_volume_ft3 - bounded_step_delta_ft3);
                            }
                            break;
                    }
                }

                if (cavitation_model_ == CavitationModel::LegacyClamp ||
                    (cavitation_model_ == CavitationModel::DVCM && ns.cavity_regime != CavityRegime::LiquidFull)) {
                    // Cavitation checks...
                    if (H_dn < H_vap) {
                        H_dn = H_vap;
                        const double Bc  = bndry[bIn].B / bndry[bIn].area;
                        Q    = quadratic_Q(K_eq, Bc, bndry[bIn].C_P - H_vap);
                        if (n.flipped) Q = std::min(0.0, Q);
                        else           Q = std::max(0.0, Q);
                        H_up = bndry[bIn].C_P - Bc * Q;
                    }
                    if (H_up < H_vap) {
                        H_up = H_vap;
                        const double Bc  = bndry[bOut].B / bndry[bOut].area;
                        Q    = quadratic_Q(K_eq, Bc, H_vap - bndry[bOut].C_M);
                        if (n.flipped) Q = std::min(0.0, Q);
                        else           Q = std::max(0.0, Q);
                        H_dn = bndry[bOut].C_M + Bc * Q;
                    }
                }

                set_downstream(bIn,  H_up);
                set_upstream  (bOut, H_dn);
            } else {
                const double H_f = std::max(H_vap, getInitialHead(ns));
                for (int pi : in_pipes)  set_downstream(pi, H_f);
                for (int pi : out_pipes) set_upstream  (pi, H_f);
            }
            break;
        }

        // ── Pressure-control valves (PRV / PSV / PBV) ─────────────────────
        // NodeInput::head stores the control target in ft HGL:
        //   PRV → downstream piezometric head setpoint
        //   PSV → upstream piezometric head setpoint
        //   PBV → required head drop across the valve (ft)
        case NodeType::PRV:
        case NodeType::PSV:
        case NodeType::PBV: {
            if (in_pipes.size() == 1 && out_pipes.size() == 1) {
                if (n.current_setting < 99.9) {
                    const double setting = std::max(1e-6, n.current_setting);
                    const double K = std::pow(100.0 / setting, 2.0) - 1.0;
                    const double diam_ft = n.diameter / 12.0;
                    const double A_v     = M_PI_ * (diam_ft / 2.0) * (diam_ft / 2.0);
                    const double K_eq    = K / (2.0 * g * A_v * A_v);

                    const int bIn  = in_pipes[0];
                    const int bOut = out_pipes[0];
                    const double B_eq = (bndry[bIn].B  / bndry[bIn].area)
                                      + (bndry[bOut].B / bndry[bOut].area);
                    const double C_eq = bndry[bIn].C_P - bndry[bOut].C_M;
                    double Q = quadratic_Q(K_eq, B_eq, C_eq);

                    double H_up = bndry[bIn].C_P  - (bndry[bIn].B  / bndry[bIn].area)  * Q;
                    double H_dn = bndry[bOut].C_M + (bndry[bOut].B / bndry[bOut].area) * Q;

                    double H_up_candidate = H_up;
                    double H_dn_candidate = H_dn;
                    double Q_candidate = Q;

                    if (cavitation_model_ == CavitationModel::DVCM) {
                        constexpr double H_CAVITY_ENTER_TOL = 0.10 * PSI_TO_FT;
                        constexpr double H_CAVITY_LEAVE_TOL = 0.50 * PSI_TO_FT;
                        const bool enter_cavity = (H_up_candidate <= (H_vap - H_CAVITY_ENTER_TOL)) || (H_dn_candidate <= (H_vap - H_CAVITY_ENTER_TOL));
                        const bool leave_cavity = (H_up_candidate >= (H_vap + H_CAVITY_LEAVE_TOL)) && (H_dn_candidate >= (H_vap + H_CAVITY_LEAVE_TOL));

                        double H_up_clamped = H_up_candidate;
                        double H_dn_clamped = H_dn_candidate;
                        double Q_clamped = Q_candidate;

                        if (H_dn_clamped < H_vap) {
                            H_dn_clamped = H_vap;
                            const double Bc  = bndry[bIn].B / bndry[bIn].area;
                            Q_clamped    = quadratic_Q(K_eq, Bc, bndry[bIn].C_P - H_vap);
                            H_up_clamped = bndry[bIn].C_P - Bc * Q_clamped;
                        }
                        if (H_up_clamped < H_vap) {
                            H_up_clamped = H_vap;
                            const double Bc  = bndry[bOut].B / bndry[bOut].area;
                            Q_clamped    = quadratic_Q(K_eq, Bc, H_vap - bndry[bOut].C_M);
                            H_dn_clamped = bndry[bOut].C_M + Bc * Q_clamped;
                        }
                        const double flow_in_vap = (bndry[bIn].C_P - H_vap) / (bndry[bIn].B / bndry[bIn].area);
                        const double flow_out_vap = (H_vap - bndry[bOut].C_M) / (bndry[bOut].B / bndry[bOut].area);
                        const double imbalance_cfs = std::abs(flow_in_vap - flow_out_vap);

                        const double cavity_capacity_ft3 = 0.5 * pipes_[bIn].area * pipes_[bIn].L + 0.5 * pipes_[bOut].area * pipes_[bOut].L;
                        const double max_step_delta_ft3 = 0.25 * cavity_capacity_ft3;
                        const double bounded_step_delta_ft3 = std::min(imbalance_cfs * dt_, max_step_delta_ft3);

                        ns.cavity_collapsed_this_step = false;

                        switch (ns.cavity_regime) {
                            case CavityRegime::LiquidFull:
                                if (enter_cavity) {
                                    ns.cavity_regime = CavityRegime::CavityActive;
                                    ns.cavity_active = true;
                                    ns.cavity_volume_ft3 = std::min(
                                        cavity_capacity_ft3,
                                        std::max(0.0, ns.cavity_volume_ft3 + bounded_step_delta_ft3));
                                } else {
                                    ns.cavity_active = false;
                                    ns.cavity_volume_ft3 = 0.0;
                                    ns.cavity_consecutive_collapses = 0;
                                }
                                break;
                            case CavityRegime::CavityActive:
                                if (leave_cavity) {
                                    ns.cavity_regime = CavityRegime::CollapseTransition;
                                    ns.cavity_active = false;
                                    ns.cavity_volume_ft3 = std::max(0.0, ns.cavity_volume_ft3 - bounded_step_delta_ft3);
                                    ns.cavity_collapsed_this_step = true;
                                    ns.cavity_collapse_count += 1;
                                    ns.cavity_consecutive_collapses += 1;
                                } else {
                                    ns.cavity_active = true;
                                    ns.cavity_volume_ft3 = std::min(
                                        cavity_capacity_ft3,
                                        std::max(0.0, ns.cavity_volume_ft3 + bounded_step_delta_ft3));
                                }
                                break;
                            case CavityRegime::CollapseTransition:
                                if (ns.cavity_volume_ft3 <= bounded_step_delta_ft3 &&
                                    H_up_candidate >= (H_vap - H_CAVITY_ENTER_TOL) &&
                                    H_dn_candidate >= (H_vap - H_CAVITY_ENTER_TOL)) {
                                    ns.cavity_regime = CavityRegime::LiquidFull;
                                    ns.cavity_active = false;
                                    ns.cavity_volume_ft3 = 0.0;
                                    ns.cavity_consecutive_collapses = 0;
                                } else {
                                    ns.cavity_active = false;
                                    ns.cavity_volume_ft3 = std::max(0.0, ns.cavity_volume_ft3 - bounded_step_delta_ft3);
                                }
                                break;
                        }
                    }

                    if (cavitation_model_ == CavitationModel::LegacyClamp ||
                        (cavitation_model_ == CavitationModel::DVCM && ns.cavity_regime != CavityRegime::LiquidFull)) {
                        // Cavitation: downstream
                        if (H_dn < H_vap) {
                            H_dn = H_vap;
                            const double Bc  = bndry[bIn].B / bndry[bIn].area;
                            Q    = quadratic_Q(K_eq, Bc, bndry[bIn].C_P - H_vap);
                            H_up = bndry[bIn].C_P - Bc * Q;
                        }
                        // Cavitation: upstream
                        if (H_up < H_vap) {
                            H_up = H_vap;
                            const double Bc  = bndry[bOut].B / bndry[bOut].area;
                            Q    = quadratic_Q(K_eq, Bc, H_vap - bndry[bOut].C_M);
                            H_dn = bndry[bOut].C_M + Bc * Q;
                        }
                    }

                    set_downstream(bIn,  H_up);
                    set_upstream  (bOut, H_dn);
                } else {
                    const int bIn  = in_pipes[0];
                    const int bOut = out_pipes[0];
                    const double Bi  = bndry[bIn].B  / bndry[bIn].area;
                    const double Bo  = bndry[bOut].B / bndry[bOut].area;
                    const double B_eq = Bi + Bo;
                    const double C_eq = bndry[bIn].C_P - bndry[bOut].C_M;

                    double Q_open = (B_eq > 1e-12) ? (C_eq / B_eq) : 0.0;
                    double H_up_open = bndry[bIn].C_P - Bi * Q_open;
                    double H_dn_open = bndry[bOut].C_M + Bo * Q_open;

                    double Q    = Q_open;
                    double H_up = H_up_open;
                    double H_dn = H_dn_open;
                    const double H_set = n.head;
                    constexpr double reg_tol = 1e-4;

                    if (n.type == NodeType::PRV) {
                        if (H_dn_open > H_set + reg_tol) {
                            const double Q_reg = (H_set - bndry[bOut].C_M) / std::max(Bo, 1e-12);
                            if (Q_reg < 0.0) {
                                // Closed
                                Q    = 0.0;
                                H_up = bndry[bIn].C_P;
                                H_dn = bndry[bOut].C_M;
                            } else {
                                // Regulating
                                Q    = Q_reg;
                                H_dn = H_set;
                                H_up = bndry[bIn].C_P - Bi * Q;
                            }
                        } else {
                            if (Q_open < 0.0) {
                                // Closed
                                Q    = 0.0;
                                H_up = bndry[bIn].C_P;
                                H_dn = bndry[bOut].C_M;
                            } else {
                                // Open
                                Q    = Q_open;
                                H_up = H_up_open;
                                H_dn = H_dn_open;
                            }
                        }
                    } else if (n.type == NodeType::PSV) {
                        if (H_up_open < H_set - reg_tol) {
                            const double Q_reg = (bndry[bIn].C_P - H_set) / std::max(Bi, 1e-12);
                            if (Q_reg < 0.0) {
                                // Closed
                                Q    = 0.0;
                                H_up = bndry[bIn].C_P;
                                H_dn = bndry[bOut].C_M;
                            } else {
                                // Regulating
                                Q    = Q_reg;
                                H_up = H_set;
                                H_dn = bndry[bOut].C_M + Bo * Q;
                            }
                        } else {
                            if (Q_open < 0.0) {
                                // Closed
                                Q    = 0.0;
                                H_up = bndry[bIn].C_P;
                                H_dn = bndry[bOut].C_M;
                            } else {
                                // Open
                                Q    = Q_open;
                                H_up = H_up_open;
                                H_dn = H_dn_open;
                            }
                        }
                    } else {
                        const double delta = H_set;
                        Q = (C_eq - delta) / std::max(B_eq, 1e-12);
                        if (Q < 0.0) {
                            // Closed
                            Q    = 0.0;
                            H_up = bndry[bIn].C_P;
                            H_dn = bndry[bOut].C_M;
                        } else {
                            H_up = bndry[bIn].C_P - Bi * Q;
                            H_dn = H_up - delta;
                        }
                    }

                    if (H_dn < H_vap) {
                        H_dn = H_vap;
                        Q    = (bndry[bIn].C_P - H_dn) / std::max(Bi, 1e-12);
                        H_up = bndry[bIn].C_P - Bi * Q;
                    }
                    if (H_up < H_vap) {
                        H_up = H_vap;
                        Q    = (bndry[bIn].C_P - H_up) / std::max(Bi, 1e-12);
                        H_dn = bndry[bOut].C_M + Bo * Q;
                    }

                    set_downstream(bIn,  H_up);
                    set_upstream  (bOut, H_dn);
                }
            } else {
                if (n.current_setting < 99.9) {
                    const double setting = std::max(1e-6, n.current_setting);
                    const double K = std::pow(100.0 / setting, 2.0) - 1.0;
                    const double diam_ft = n.diameter / 12.0;
                    const double A_v     = M_PI_ * (diam_ft / 2.0) * (diam_ft / 2.0);
                    const double K_eq    = K / (2.0 * g * A_v * A_v);
                    
                    const double H_f = getInitialHead(ns);
                    for (int pi : in_pipes) {
                        const double Bc   = bndry[pi].B / bndry[pi].area;
                        double Q = quadratic_Q(K_eq, Bc, bndry[pi].C_P - H_f);
                        double H_up = std::max(H_vap, bndry[pi].C_P - Bc * Q);
                        set_downstream(pi, H_up);
                    }
                    for (int pi : out_pipes) {
                        const double Bc   = bndry[pi].B / bndry[pi].area;
                        double Q = quadratic_Q(K_eq, Bc, H_f - bndry[pi].C_M);
                        double H_dn = std::max(H_vap, bndry[pi].C_M + Bc * Q);
                        set_upstream(pi, H_dn);
                    }
                } else {
                    const double H_f = std::max(H_vap, getInitialHead(ns));
                    for (int pi : in_pipes)  set_downstream(pi, H_f);
                    for (int pi : out_pipes) set_upstream  (pi, H_f);
                }
            }
            break;
        }

        // ── Valve / Turbine ────────────────────────────────────────────────
        // Head loss: ΔH = K_eq · Q²   (K_eq = K / (2g·A_v²))
        // Combined with C± gives a quadratic in Q.
        case NodeType::Valve:
        case NodeType::Turbine: {
            const double setting = std::max(1e-6, n.current_setting);

            double K; // dimensionless loss coefficient
            if (n.type == NodeType::Valve && !(n.design_head > 0.0 && n.design_flow > 0.0)) {
                // K = (100/setting)² − 1   (K→∞ when fully closed)
                K = std::pow(100.0 / setting, 2.0) - 1.0;
            } else {
                // Turbine or Valve with design curve modeled as variable-K orifice from design point.
                const double A_t  = M_PI_ * std::pow(n.diameter / 24.0, 2.0); // ft²
                const double V_d  = (n.design_velocity > 1e-6)
                    ? n.design_velocity
                    : (n.design_flow * GPM_TO_CFS / std::max(A_t, 1e-9));
                const double K_base = (n.design_head * 2.0 * g)
                                    / std::pow(std::max(V_d, 0.001), 2.0);
                K = K_base / std::pow(setting / 100.0, 2.0);
            }

            const double diam_ft = n.diameter / 12.0;
            const double A_v     = M_PI_ * (diam_ft / 2.0) * (diam_ft / 2.0);
            const double K_eq    = K / (2.0 * g * A_v * A_v);

            if (in_pipes.size() == 1 && out_pipes.size() == 1) {
                const int bIn  = in_pipes[0];
                const int bOut = out_pipes[0];
                const double B_eq = (bndry[bIn].B  / bndry[bIn].area)
                                  + (bndry[bOut].B / bndry[bOut].area);
                const double C_eq = bndry[bIn].C_P - bndry[bOut].C_M;
                double Q = quadratic_Q(K_eq, B_eq, C_eq);

                double H_up = bndry[bIn].C_P  - (bndry[bIn].B  / bndry[bIn].area)  * Q;
                double H_dn = bndry[bOut].C_M + (bndry[bOut].B / bndry[bOut].area) * Q;

                double H_up_candidate = H_up;
                double H_dn_candidate = H_dn;
                double Q_candidate = Q;

                if (cavitation_model_ == CavitationModel::DVCM) {
                    constexpr double H_CAVITY_ENTER_TOL = 0.10 * PSI_TO_FT;
                    constexpr double H_CAVITY_LEAVE_TOL = 0.50 * PSI_TO_FT;
                    const bool enter_cavity = (H_up_candidate <= (H_vap - H_CAVITY_ENTER_TOL)) || (H_dn_candidate <= (H_vap - H_CAVITY_ENTER_TOL));
                    const bool leave_cavity = (H_up_candidate >= (H_vap + H_CAVITY_LEAVE_TOL)) && (H_dn_candidate >= (H_vap + H_CAVITY_LEAVE_TOL));

                    double H_up_clamped = H_up_candidate;
                    double H_dn_clamped = H_dn_candidate;
                    double Q_clamped = Q_candidate;

                    if (H_dn_clamped < H_vap) {
                        H_dn_clamped = H_vap;
                        const double Bc  = bndry[bIn].B / bndry[bIn].area;
                        Q_clamped    = quadratic_Q(K_eq, Bc, bndry[bIn].C_P - H_vap);
                        H_up_clamped = bndry[bIn].C_P - Bc * Q_clamped;
                    }
                    if (H_up_clamped < H_vap) {
                        H_up_clamped = H_vap;
                        const double Bc  = bndry[bOut].B / bndry[bOut].area;
                        Q_clamped    = quadratic_Q(K_eq, Bc, H_vap - bndry[bOut].C_M);
                        H_dn_clamped = bndry[bOut].C_M + Bc * Q_clamped;
                    }
                    const double flow_in_vap = (bndry[bIn].C_P - H_vap) / (bndry[bIn].B / bndry[bIn].area);
                    const double flow_out_vap = (H_vap - bndry[bOut].C_M) / (bndry[bOut].B / bndry[bOut].area);
                    const double imbalance_cfs = std::abs(flow_in_vap - flow_out_vap);

                    const double cavity_capacity_ft3 = 0.5 * pipes_[bIn].area * pipes_[bIn].L + 0.5 * pipes_[bOut].area * pipes_[bOut].L;
                    const double max_step_delta_ft3 = 0.25 * cavity_capacity_ft3;
                    const double bounded_step_delta_ft3 = std::min(imbalance_cfs * dt_, max_step_delta_ft3);

                    ns.cavity_collapsed_this_step = false;

                    switch (ns.cavity_regime) {
                        case CavityRegime::LiquidFull:
                            if (enter_cavity) {
                                ns.cavity_regime = CavityRegime::CavityActive;
                                ns.cavity_active = true;
                                ns.cavity_volume_ft3 = std::min(
                                    cavity_capacity_ft3,
                                    std::max(0.0, ns.cavity_volume_ft3 + bounded_step_delta_ft3));
                            } else {
                                ns.cavity_active = false;
                                ns.cavity_volume_ft3 = 0.0;
                                ns.cavity_consecutive_collapses = 0;
                            }
                            break;
                        case CavityRegime::CavityActive:
                            if (leave_cavity) {
                                ns.cavity_regime = CavityRegime::CollapseTransition;
                                ns.cavity_active = false;
                                ns.cavity_volume_ft3 = std::max(0.0, ns.cavity_volume_ft3 - bounded_step_delta_ft3);
                                ns.cavity_collapsed_this_step = true;
                                ns.cavity_collapse_count += 1;
                                ns.cavity_consecutive_collapses += 1;
                            } else {
                                ns.cavity_active = true;
                                ns.cavity_volume_ft3 = std::min(
                                    cavity_capacity_ft3,
                                    std::max(0.0, ns.cavity_volume_ft3 + bounded_step_delta_ft3));
                            }
                            break;
                        case CavityRegime::CollapseTransition:
                            if (ns.cavity_volume_ft3 <= bounded_step_delta_ft3 &&
                                H_up_candidate >= (H_vap - H_CAVITY_ENTER_TOL) &&
                                H_dn_candidate >= (H_vap - H_CAVITY_ENTER_TOL)) {
                                ns.cavity_regime = CavityRegime::LiquidFull;
                                ns.cavity_active = false;
                                ns.cavity_volume_ft3 = 0.0;
                                ns.cavity_consecutive_collapses = 0;
                            } else {
                                ns.cavity_active = false;
                                ns.cavity_volume_ft3 = std::max(0.0, ns.cavity_volume_ft3 - bounded_step_delta_ft3);
                            }
                            break;
                    }
                }

                if (cavitation_model_ == CavitationModel::LegacyClamp ||
                    (cavitation_model_ == CavitationModel::DVCM && ns.cavity_regime != CavityRegime::LiquidFull)) {
                    // Cavitation: downstream
                    if (H_dn < H_vap) {
                        H_dn = H_vap;
                        const double Bc  = bndry[bIn].B / bndry[bIn].area;
                        Q    = quadratic_Q(K_eq, Bc, bndry[bIn].C_P - H_vap);
                        H_up = bndry[bIn].C_P - Bc * Q;
                    }
                    // Cavitation: upstream
                    if (H_up < H_vap) {
                        H_up = H_vap;
                        const double Bc  = bndry[bOut].B / bndry[bOut].area;
                        Q    = quadratic_Q(K_eq, Bc, H_vap - bndry[bOut].C_M);
                        H_dn = bndry[bOut].C_M + Bc * Q;
                    }
                }

                set_downstream(bIn,  H_up);
                set_upstream  (bOut, H_dn);
            } else {
                // Multi-pipe valve node: fall back to fixed-head approximation
                const double H_f = getInitialHead(ns);
                for (int pi : in_pipes) {
                    const double Bc   = bndry[pi].B / bndry[pi].area;
                    double Q = quadratic_Q(K_eq, Bc, bndry[pi].C_P - H_f);
                    double H_up = std::max(H_vap, bndry[pi].C_P - Bc * Q);
                    set_downstream(pi, H_up);
                }
                for (int pi : out_pipes) {
                    const double Bc   = bndry[pi].B / bndry[pi].area;
                    double Q = quadratic_Q(K_eq, Bc, H_f - bndry[pi].C_M);
                    double H_dn = std::max(H_vap, bndry[pi].C_M + Bc * Q);
                    set_upstream(pi, H_dn);
                }
            }

            if (n.type == NodeType::Turbine) {
                const double G = n.current_setting / 100.0;
                double H_up = n.elevation;
                double H_dn = n.elevation;
                if (!in_pipes.empty()) {
                    const int bIn = in_pipes[0];
                    const int last = pipes_[bIn].num_nodes - 1;
                    H_up = newH[bIn][last];
                }
                if (!out_pipes.empty()) {
                    const int bOut = out_pipes[0];
                    H_dn = newH[bOut][0];
                }

                const double dH = std::max(0.0, H_up - H_dn);
                const double N_rated = std::max(1.0, n.speed_rpm);
                const double H_design = std::max(1e-6, n.design_head);
                const double dH_ratio = dH / H_design;

                const double T_stall = 1.5 * ns.rated_torque_ftlb * G * dH_ratio;
                const double N_runaway = 1.8 * N_rated * std::sqrt(dH_ratio);
                const double N_current = (n.current_speed / 100.0) * N_rated;

                double T_hydraulic = 0.0;
                if (N_runaway > 1e-6) {
                    T_hydraulic = T_stall * (1.0 - N_current / N_runaway);
                }

                if (n.has_power) {
                    n.current_speed = 100.0;
                } else {
                    if (n.inertia_wr2 <= 1e-6) {
                        n.current_speed = (N_runaway / N_rated) * 100.0;
                    } else {
                        const double dN_rpm = (307.486 * T_hydraulic / n.inertia_wr2) * dt_;
                        const double N_new = std::max(0.0, N_current + dN_rpm);
                        n.current_speed = (N_new / N_rated) * 100.0;
                    }
                }
            }
            break;
        }

        // ── Centrifugal pump ───────────────────────────────────────────────
        // 3-coefficient affinity-law curve:
        //   ΔH = α·s² − β_cfs·Q²
        //   α = 4/3·H_D   (shutoff head at rated speed)
        //   β = 1/3·H_D / Q_D²  (in GPM units)
        //   β_cfs = β · 448.831²  (convert to CFS units)
        case NodeType::Pump: {
            const double spd = n.current_speed;
            const double H_D   = n.design_head;
            const double Q_D   = n.design_flow;
            const double alpha  = (4.0 / 3.0) * H_D;            // ft
            const double beta   = (1.0 / 3.0) * H_D / (Q_D * Q_D);
            const double beta_cfs = beta * 201449.26;            // 448.831² ≈ 201449
            const double s  = spd / 100.0;
            const double s2 = s * s;
            double Q = 0.0;

            if (in_pipes.size() == 1 && out_pipes.size() == 1) {
                const int bIn  = in_pipes[0];
                const int bOut = out_pipes[0];
                const double a_q = beta_cfs * s2;

                double H_up = 0.0;
                double H_dn = 0.0;

                if (spd <= 0.0) {
                    H_up = bndry[bIn].C_P;
                    H_dn = bndry[bOut].C_M;
                    Q = 0.0;
                } else {
                    const double B_eq = (bndry[bIn].B  / bndry[bIn].area)
                                      + (bndry[bOut].B / bndry[bOut].area);
                    const double C_eq = bndry[bIn].C_P - bndry[bOut].C_M;
                    const double c_q = -(C_eq + alpha * s2);

                    if (a_q < 1e-10) {
                        Q = -c_q / B_eq;
                    } else {
                        const double disc = B_eq * B_eq - 4.0 * a_q * c_q;
                        if (disc >= 0.0)
                            Q = (-B_eq + std::sqrt(disc)) / (2.0 * a_q);
                    }
                    Q = std::max(0.0, Q);

                    H_up = bndry[bIn].C_P  - (bndry[bIn].B  / bndry[bIn].area)  * Q;
                    H_dn = bndry[bOut].C_M + (bndry[bOut].B / bndry[bOut].area) * Q;
                }

                double H_up_candidate = H_up;
                double H_dn_candidate = H_dn;
                double Q_candidate = Q;

                if (cavitation_model_ == CavitationModel::DVCM) {
                    constexpr double H_CAVITY_ENTER_TOL = 0.10 * PSI_TO_FT;
                    constexpr double H_CAVITY_LEAVE_TOL = 0.50 * PSI_TO_FT;
                    const bool enter_cavity = (H_up_candidate <= (H_vap - H_CAVITY_ENTER_TOL)) || (H_dn_candidate <= (H_vap - H_CAVITY_ENTER_TOL));
                    const bool leave_cavity = (H_up_candidate >= (H_vap + H_CAVITY_LEAVE_TOL)) && (H_dn_candidate >= (H_vap + H_CAVITY_LEAVE_TOL));

                    const double flow_in_vap = (bndry[bIn].C_P - H_vap) / (bndry[bIn].B / bndry[bIn].area);
                    const double flow_out_vap = (H_vap - bndry[bOut].C_M) / (bndry[bOut].B / bndry[bOut].area);
                    const double imbalance_cfs = std::abs(flow_in_vap - flow_out_vap);

                    const double cavity_capacity_ft3 = 0.5 * pipes_[bIn].area * pipes_[bIn].L + 0.5 * pipes_[bOut].area * pipes_[bOut].L;
                    const double max_step_delta_ft3 = 0.25 * cavity_capacity_ft3;
                    const double bounded_step_delta_ft3 = std::min(imbalance_cfs * dt_, max_step_delta_ft3);

                    ns.cavity_collapsed_this_step = false;

                    switch (ns.cavity_regime) {
                        case CavityRegime::LiquidFull:
                            if (enter_cavity) {
                                ns.cavity_regime = CavityRegime::CavityActive;
                                ns.cavity_active = true;
                                ns.cavity_volume_ft3 = std::min(
                                    cavity_capacity_ft3,
                                    std::max(0.0, ns.cavity_volume_ft3 + bounded_step_delta_ft3));
                            } else {
                                ns.cavity_active = false;
                                ns.cavity_volume_ft3 = 0.0;
                                ns.cavity_consecutive_collapses = 0;
                            }
                            break;
                        case CavityRegime::CavityActive:
                            if (leave_cavity) {
                                ns.cavity_regime = CavityRegime::CollapseTransition;
                                ns.cavity_active = false;
                                ns.cavity_volume_ft3 = std::max(0.0, ns.cavity_volume_ft3 - bounded_step_delta_ft3);
                                ns.cavity_collapsed_this_step = true;
                                ns.cavity_collapse_count += 1;
                                ns.cavity_consecutive_collapses += 1;
                            } else {
                                ns.cavity_active = true;
                                ns.cavity_volume_ft3 = std::min(
                                    cavity_capacity_ft3,
                                    std::max(0.0, ns.cavity_volume_ft3 + bounded_step_delta_ft3));
                            }
                            break;
                        case CavityRegime::CollapseTransition:
                            if (ns.cavity_volume_ft3 <= bounded_step_delta_ft3 &&
                                H_up_candidate >= (H_vap - H_CAVITY_ENTER_TOL) &&
                                H_dn_candidate >= (H_vap - H_CAVITY_ENTER_TOL)) {
                                ns.cavity_regime = CavityRegime::LiquidFull;
                                ns.cavity_active = false;
                                ns.cavity_volume_ft3 = 0.0;
                                ns.cavity_consecutive_collapses = 0;
                            } else {
                                ns.cavity_active = false;
                                ns.cavity_volume_ft3 = std::max(0.0, ns.cavity_volume_ft3 - bounded_step_delta_ft3);
                            }
                            break;
                    }
                }

                if (cavitation_model_ == CavitationModel::LegacyClamp ||
                    (cavitation_model_ == CavitationModel::DVCM && ns.cavity_regime != CavityRegime::LiquidFull)) {
                    if (spd <= 0.0) {
                        if (H_up < H_vap) H_up = H_vap;
                        if (H_dn < H_vap) H_dn = H_vap;
                    } else {
                        // Cavitation downstream
                        if (H_dn < H_vap) {
                            H_dn = H_vap;
                            const double bc  = bndry[bIn].B / bndry[bIn].area;
                            const double cc  = -(bndry[bIn].C_P + alpha * s2 - H_vap);
                            if (a_q < 1e-10) { Q = -cc / bc; }
                            else {
                                const double dc = bc * bc - 4.0 * a_q * cc;
                                if (dc >= 0.0) Q = (-bc + std::sqrt(dc)) / (2.0 * a_q);
                            }
                            Q    = std::max(0.0, Q);
                            H_up = bndry[bIn].C_P - (bndry[bIn].B / bndry[bIn].area) * Q;
                        }
                        // Cavitation upstream
                        if (H_up < H_vap) {
                            H_up = H_vap;
                            const double bc  = bndry[bOut].B / bndry[bOut].area;
                            const double cc  = -(H_vap + alpha * s2 - bndry[bOut].C_M);
                            if (a_q < 1e-10) { Q = -cc / bc; }
                            else {
                                const double dc = bc * bc - 4.0 * a_q * cc;
                                if (dc >= 0.0) Q = (-bc + std::sqrt(dc)) / (2.0 * a_q);
                            }
                            Q    = std::max(0.0, Q);
                            H_dn = bndry[bOut].C_M + (bndry[bOut].B / bndry[bOut].area) * Q;
                        }
                    }
                }

                if (spd <= 0.0) {
                    double V_up = 0.0;
                    double V_dn = 0.0;
                    if (H_up < H_vap + 1e-9) { H_up = H_vap; V_up = (bndry[bIn].C_P - H_vap) / bndry[bIn].B; }
                    if (H_dn < H_vap + 1e-9) { H_dn = H_vap; V_dn = (H_vap - bndry[bOut].C_M) / bndry[bOut].B; }
                    set_downstream(bIn, H_up);
                    newV[bIn][pipes_[bIn].num_nodes - 1] = V_up;
                    set_upstream(bOut, H_dn);
                    newV[bOut][0] = V_dn;
                } else {
                    set_downstream(bIn,  H_up);
                    set_upstream  (bOut, H_dn);
                }

            } else {
                // Multi-pipe pump:
                if (spd <= 0.0) {
                    for (int pi : in_pipes) {
                        double H_P = bndry[pi].C_P;
                        double V_P = 0.0;
                        if (H_P < H_vap) { H_P = H_vap; V_P = (bndry[pi].C_P - H_vap) / bndry[pi].B; }
                        set_downstream(pi, H_P);
                        newV[pi][pipes_[pi].num_nodes - 1] = V_P;
                    }
                    for (int pi : out_pipes) {
                        double H_P = bndry[pi].C_M;
                        double V_P = 0.0;
                        if (H_P < H_vap) { H_P = H_vap; V_P = (H_vap - bndry[pi].C_M) / bndry[pi].B; }
                        set_upstream(pi, H_P);
                        newV[pi][0] = V_P;
                    }
                } else {
                    // Multi-pipe pump: approximate with static head rise
                    const double H_base = getInitialHead(ns);
                    for (int pi : in_pipes)  set_downstream(pi, std::max(H_vap, H_base - alpha * s2));
                    for (int pi : out_pipes) set_upstream  (pi, std::max(H_vap, H_base + alpha * s2));

                    // Estimate Q for speed decay
                    double Q_sum = 0.0;
                    for (int pi : in_pipes) {
                        int last = pipes_[pi].num_nodes - 1;
                        Q_sum += newV[pi][last] * pipes_[pi].area;
                    }
                    Q = std::max(0.0, Q_sum);
                }
            }

            // Integrate pump deceleration speed decay if power is lost and pump has inertia
            if (!n.has_power && n.inertia_wr2 > 0.0) {
                double Q_gpm = Q / GPM_TO_CFS;
                double q_ratio = (n.design_flow > 1e-6) ? Q_gpm / n.design_flow : 0.0;
                double torque_h = ns.rated_torque_ftlb * (0.5 * s2 + 0.5 * s * q_ratio);
                double I = n.inertia_wr2 / g;
                double omega_0 = 2.0 * M_PI_ * std::max(1.0, n.speed_rpm) / 60.0;
                double denom = I * omega_0;
                double ds = 0.0;
                if (denom > 1e-9) {
                    ds = (-torque_h / denom) * dt_;
                }
                double s_new = std::clamp(s + ds, 0.0, 1.0);
                ns.input.current_speed = s_new * 100.0;
            } else if (!n.has_power) {
                // Tripped and no inertia: instant stop
                ns.input.current_speed = 0.0;
            }

            break;
        }

        // ── Interior junction / demand node ────────────────────────────────
        // Kirchhoff continuity: ΣQ_in − ΣQ_out = Q_demand
        // Each pipe contributes:  Q_i = (A_i / B_i) · (C_P_i − H_P)  (inflow)
        //                         Q_i = (A_i / B_i) · (H_P − C_M_i)  (outflow)
        // Summing and solving for H_P gives a linear equation.
        case NodeType::Junction:
        case NodeType::InflowNode:
        case NodeType::OutflowNode:
        default: {
            const double sign  = (n.type == NodeType::InflowNode) ? -1.0 : 1.0;
            const double Q_dem = sign * n.demand * GPM_TO_CFS; // CFS (positive = outflow)

            double sum_AB_C = 0.0, sum_AB = 0.0;
            for (int pi : in_pipes) {
                const double AB = bndry[pi].area / bndry[pi].B;
                sum_AB_C += AB * bndry[pi].C_P;
                sum_AB   += AB;
            }
            for (int pi : out_pipes) {
                const double AB = bndry[pi].area / bndry[pi].B;
                sum_AB_C += AB * bndry[pi].C_M;
                sum_AB   += AB;
            }
            const double H_candidate = (sum_AB > 1e-12)
                ? (sum_AB_C - Q_dem) / sum_AB
                : getInitialHead(ns);
            double H_P = H_candidate;

            if (cavitation_model_ == CavitationModel::DVCM) {
                constexpr double H_CAVITY_ENTER_TOL = 0.10 * PSI_TO_FT;
                constexpr double H_CAVITY_LEAVE_TOL = 0.50 * PSI_TO_FT;
                const bool enter_cavity = H_candidate <= (H_vap - H_CAVITY_ENTER_TOL);
                const bool leave_cavity = H_candidate >= (H_vap + H_CAVITY_LEAVE_TOL);
                double cavity_capacity_ft3 = 0.0;
                for (int pi : in_pipes) {
                    cavity_capacity_ft3 += 0.5 * pipes_[pi].area * pipes_[pi].L;
                }
                for (int pi : out_pipes) {
                    cavity_capacity_ft3 += 0.5 * pipes_[pi].area * pipes_[pi].L;
                }
                const double imbalance_cfs = std::abs(sum_AB * (H_candidate - H_vap));
                const double max_step_delta_ft3 = 0.25 * cavity_capacity_ft3;
                const double bounded_step_delta_ft3 = std::min(imbalance_cfs * dt_, max_step_delta_ft3);

                switch (ns.cavity_regime) {
                    case CavityRegime::LiquidFull:
                        if (enter_cavity) {
                            ns.cavity_regime = CavityRegime::CavityActive;
                            ns.cavity_active = true;
                            ns.cavity_volume_ft3 = std::min(
                                cavity_capacity_ft3,
                                std::max(0.0, ns.cavity_volume_ft3 + bounded_step_delta_ft3));
                        } else {
                            ns.cavity_active = false;
                            ns.cavity_volume_ft3 = 0.0;
                            ns.cavity_consecutive_collapses = 0;
                        }
                        break;
                    case CavityRegime::CavityActive:
                        if (leave_cavity) {
                            ns.cavity_regime = CavityRegime::CollapseTransition;
                            ns.cavity_active = false;
                            ns.cavity_volume_ft3 = std::max(0.0, ns.cavity_volume_ft3 - bounded_step_delta_ft3);
                            ns.cavity_collapsed_this_step = true;
                            ns.cavity_collapse_count += 1;
                            ns.cavity_consecutive_collapses += 1;
                        } else {
                            ns.cavity_active = true;
                            ns.cavity_volume_ft3 = std::min(
                                cavity_capacity_ft3,
                                std::max(0.0, ns.cavity_volume_ft3 + bounded_step_delta_ft3));
                        }
                        break;
                    case CavityRegime::CollapseTransition:
                        if (ns.cavity_volume_ft3 <= bounded_step_delta_ft3 &&
                            H_candidate >= (H_vap - H_CAVITY_ENTER_TOL)) {
                            ns.cavity_regime = CavityRegime::LiquidFull;
                            ns.cavity_active = false;
                            ns.cavity_volume_ft3 = 0.0;
                            ns.cavity_consecutive_collapses = 0;
                        } else {
                            ns.cavity_active = false;
                            ns.cavity_volume_ft3 = std::max(0.0, ns.cavity_volume_ft3 - bounded_step_delta_ft3);
                        }
                        break;
                }
            }
            // Cavitation limit: clamp HGL to vapor pressure.
            // NOTE: This is a simplified, first-order cavitation model. It detects
            // when the local pressure reaches vapor pressure, but it does not
            // integrate or track vapor cavity volume over time. Severe column
            // separation events resulting in high-pressure spikes upon cavity
            // collapse (water column collision) are not modeled. For such scenarios,
            // a full Discrete Vapor Cavity Model (DVCM) is recommended.
            if (H_P < H_vap) H_P = H_vap;

            for (int pi : in_pipes)  set_downstream(pi, H_P);
            for (int pi : out_pipes) set_upstream  (pi, H_P);
            ns.actual_demand = n.demand;
            break;
        }

        } // end switch
    } // end node loop

    // Commit new state
    for (int i = 0; i < num_pipes; ++i) {
        pipes_[i].H.swap(newH[i]);
        pipes_[i].V.swap(newV[i]);
    }

    // Update cavity-state scaffolding from the committed hydraulic state.
    // This tracks transitions only; cavity volume remains a placeholder until
    // DVCM integration is implemented in a later phase.
    const double P_vapor = p_vapor_ / PSI_TO_FT;
    for (int ni = 0; ni < static_cast<int>(nodes_.size()); ++ni) {
        auto& ns = nodes_[ni];
        const auto& n = ns.input;

        const bool is_dvcm_supported =
            n.type == NodeType::Junction ||
            n.type == NodeType::InflowNode ||
            n.type == NodeType::OutflowNode ||
            ((n.type == NodeType::Valve || n.type == NodeType::Turbine || n.type == NodeType::CheckValve || n.type == NodeType::Pump) &&
             ns.inflow_pipes.size() == 1 && ns.outflow_pipes.size() == 1);
        if (cavitation_model_ == CavitationModel::DVCM && is_dvcm_supported) {
            if (!ns.cavity_active) {
                ns.cavity_volume_ft3 = std::max(ns.cavity_volume_ft3, 0.0);
            } else {
                ns.cavity_volume_ft3 = std::max(ns.cavity_volume_ft3, 0.0);
            }
            continue;
        }

        double H = getInitialHead(ns);
        const auto& in_p = ns.inflow_pipes;
        const auto& out_p = ns.outflow_pipes;

        if (n.type == NodeType::PRV || n.type == NodeType::PBV) {
            if (!out_p.empty()) {
                H = pipes_[out_p[0]].H.front();
            } else if (!in_p.empty()) {
                H = pipes_[in_p[0]].H.back();
            }
        } else if (n.type == NodeType::PSV) {
            if (!in_p.empty()) {
                H = pipes_[in_p[0]].H.back();
            } else if (!out_p.empty()) {
                H = pipes_[out_p[0]].H.front();
            }
        } else if (!in_p.empty()) {
            H = pipes_[in_p[0]].H.back();
        } else if (!out_p.empty()) {
            H = pipes_[out_p[0]].H.front();
        }

        const double P_psi = (H - n.elevation) / PSI_TO_FT;
        const bool is_cavity_active = (P_psi <= P_vapor);
        const bool collapsed_this_step = ns.cavity_active && !is_cavity_active;
        ns.cavity_collapsed_this_step = collapsed_this_step;

        if (collapsed_this_step) {
            ns.cavity_collapse_count += 1;
            ns.cavity_consecutive_collapses += 1;
        } else if (!is_cavity_active) {
            ns.cavity_consecutive_collapses = 0;
        }

        ns.cavity_active = is_cavity_active;
        ns.cavity_regime = is_cavity_active ? CavityRegime::CavityActive : CavityRegime::LiquidFull;
        if (!is_cavity_active) {
            ns.cavity_volume_ft3 = 0.0;
        } else {
            ns.cavity_volume_ft3 = std::max(ns.cavity_volume_ft3, 0.0);
        }
    }

    t_now_ += dt_;
}

// ── Pipe elevation profile helpers ────────────────────────────────────────────

double MOCSolver::interpolateElevationAtChainageFt(
    const std::vector<std::pair<double, double>>& profile,
    double chainage_ft) {
    if (profile.empty()) {
        return 0.0;
    }
    if (chainage_ft <= profile.front().first) {
        return profile.front().second;
    }
    if (chainage_ft >= profile.back().first) {
        return profile.back().second;
    }
    for (std::size_t k = 1; k < profile.size(); ++k) {
        const double x0 = profile[k - 1].first;
        const double x1 = profile[k].first;
        if (chainage_ft <= x1) {
            const double z0 = profile[k - 1].second;
            const double z1 = profile[k].second;
            const double denom = x1 - x0;
            if (std::abs(denom) < 1e-12) {
                return z1;
            }
            const double frac = (chainage_ft - x0) / denom;
            return z0 + frac * (z1 - z0);
        }
    }
    return profile.back().second;
}

void MOCSolver::buildPipeGridElevations(PipeState& ps, const PipeInput& p) const {
    ps.z.resize(ps.num_nodes);

    double z_from = 0.0;
    double z_to   = 0.0;
    const auto fit = node_idx_map_.find(p.from_node);
    const auto tit = node_idx_map_.find(p.to_node);
    if (fit != node_idx_map_.end()) {
        z_from = nodes_[fit->second].input.elevation;
    }
    if (tit != node_idx_map_.end()) {
        z_to = nodes_[tit->second].input.elevation;
    }

    const double dx = (ps.num_nodes > 1)
        ? (ps.L / static_cast<double>(ps.num_nodes - 1))
        : 0.0;

    if (p.elevation_profile.empty()) {
        for (int j = 0; j < ps.num_nodes; ++j) {
            const double frac = (ps.num_nodes > 1)
                ? static_cast<double>(j) / static_cast<double>(ps.num_nodes - 1)
                : 0.0;
            ps.z[j] = z_from + frac * (z_to - z_from);
        }
        ps.has_terrain_elevation = std::abs(z_from - z_to) > 1e-3;
        return;
    }

    if (p.elevation_profile.size() < 2) {
        throw std::invalid_argument(
            "Pipe '" + p.id + "': elevation_profile requires at least 2 "
            "(chainage_ft, elevation_ft) points");
    }

    std::vector<std::pair<double, double>> profile = p.elevation_profile;
    std::sort(profile.begin(), profile.end(),
              [](const std::pair<double, double>& a, const std::pair<double, double>& b) {
                  return a.first < b.first;
              });

    for (int j = 0; j < ps.num_nodes; ++j) {
        const double chainage_ft = static_cast<double>(j) * dx;
        ps.z[j] = interpolateElevationAtChainageFt(profile, chainage_ft);
    }
    ps.has_terrain_elevation = true;
}

// ── Pipe profile capture helpers ──────────────────────────────────────────────

std::vector<int> MOCSolver::buildProfilePointIndices(int num_nodes, int stride) {
    const int step = std::max(1, stride);
    std::vector<int> indices;
    if (num_nodes <= 0) {
        return indices;
    }
    for (int j = 0; j < num_nodes; j += step) {
        indices.push_back(j);
    }
    const int last = num_nodes - 1;
    if (indices.empty() || indices.back() != last) {
        indices.push_back(last);
    }
    return indices;
}

double MOCSolver::pipeGridElevationFt(const PipeState& ps, int grid_index) const {
    if (grid_index >= 0 && grid_index < static_cast<int>(ps.z.size())) {
        return ps.z[static_cast<std::size_t>(grid_index)];
    }
    return 0.0;
}

double MOCSolver::pipeGridVaporHeadFt(const PipeState& ps, int grid_index) const {
    return pipeGridElevationFt(ps, grid_index) + p_vapor_;
}

void MOCSolver::initializePipeSegmentStates(PipeState& ps) {
    ps.segments.assign(static_cast<std::size_t>(ps.num_nodes), PipeSegmentState{});
}

void MOCSolver::initializePipeProfileCapture(SimResults& results) {
    profile_point_indices_.clear();
    profile_chainage_ft_.clear();
    results.pipe_profile_chainage_ft.clear();
    results.pipe_profile_head_ft.clear();
    results.pipe_profile_pressure_psi.clear();
    results.pipe_profile_velocity_fps.clear();
    results.pipe_profile_cavitation.clear();
    results.pipe_profile_cavity_volume.clear();
    results.pipe_profile_cavity_active.clear();

    for (int i = 0; i < static_cast<int>(pipes_.size()); ++i) {
        const auto& ps = pipes_[i];
        const auto& pipe_id = pipe_inputs_[i].id;
        const auto indices = buildProfilePointIndices(ps.num_nodes, profile_stride_);
        profile_point_indices_[pipe_id] = indices;

        std::vector<double> chainage;
        chainage.reserve(indices.size());
        const double dx = (ps.num_nodes > 1) ? (ps.L / static_cast<double>(ps.num_nodes - 1)) : 0.0;
        for (int j : indices) {
            chainage.push_back(static_cast<double>(j) * dx);
        }
        profile_chainage_ft_[pipe_id] = chainage;
        results.pipe_profile_chainage_ft[pipe_id] = chainage;
    }
}

// ── Record current state into results vectors ─────────────────────────────────

void MOCSolver::recordStep(SimResults& results) const {
    for (int ni = 0; ni < static_cast<int>(nodes_.size()); ++ni) {
        const auto& ns = nodes_[ni];
        const auto& n  = ns.input;

        // Head telemetry: default to downstream inflow end, else outflow upstream end.
        // Pressure-control valves report the regulated face (PRV/PSV/PBV).
        double H = getInitialHead(ns);
        const auto& in_p  = ns.inflow_pipes;
        const auto& out_p = ns.outflow_pipes;

        if (n.type == NodeType::PRV || n.type == NodeType::PBV) {
            if (!out_p.empty())
                H = pipes_[out_p[0]].H.front();
            else if (!in_p.empty())
                H = pipes_[in_p[0]].H.back();
        } else if (n.type == NodeType::PSV) {
            if (!in_p.empty())
                H = pipes_[in_p[0]].H.back();
            else if (!out_p.empty())
                H = pipes_[out_p[0]].H.front();
        } else if (!in_p.empty()) {
            H = pipes_[in_p[0]].H.back();
        } else if (!out_p.empty()) {
            H = pipes_[out_p[0]].H.front();
        }

        const double P_psi   = (H - n.elevation) / PSI_TO_FT;
        const double P_vapor = p_vapor_ / PSI_TO_FT;

        if (std::isnan(H) || std::isinf(H)) {
            throw std::runtime_error("Numerical instability: NaN/Inf detected in head for node '" + n.id + "'");
        }
        if (std::isnan(ns.cavity_volume_ft3) || std::isinf(ns.cavity_volume_ft3)) {
            throw std::runtime_error("Numerical instability: NaN/Inf detected in cavity volume for node '" + n.id + "'");
        }
        if (ns.cavity_volume_ft3 < -1e-9) {
            throw std::runtime_error("Non-physical state: Negative cavity volume detected for node '" + n.id + "'");
        }
        if (std::isnan(ns.valve_position) || std::isinf(ns.valve_position)) {
            throw std::runtime_error("Numerical instability: NaN/Inf detected in valve position for node '" + n.id + "'");
        }
        if (ns.valve_position < -1e-9 || ns.valve_position > 1.0 + 1e-9) {
            throw std::runtime_error("Non-physical state: Valve position out of bounds for node '" + n.id + "'");
        }

        results.node_head    [n.id].push_back(H);
        results.node_pressure[n.id].push_back(P_psi);
        results.node_cavitation[n.id].push_back(P_psi <= P_vapor ? 1 : 0);
        results.node_cavity_volume[n.id].push_back(ns.cavity_volume_ft3);
        results.node_cavity_active[n.id].push_back(ns.cavity_active ? 1 : 0);
        results.node_cavity_collapse_flag[n.id].push_back(ns.cavity_collapsed_this_step ? 1 : 0);
        results.node_cavity_collapse_count[n.id].push_back(ns.cavity_collapse_count);

        // CheckValve closure dynamics telemetry
        results.valve_position[n.id].push_back(ns.valve_position);
        results.valve_velocity[n.id].push_back(ns.valve_velocity);
        if (n.type == NodeType::Valve || n.type == NodeType::Turbine)
            results.valve_setting[n.id].push_back(n.current_setting);
        if (n.type == NodeType::Pump)
            results.pump_speed[n.id].push_back(n.current_speed);
        if (n.type == NodeType::Turbine)
            results.turbine_speed[n.id].push_back(n.current_speed);
    }

    for (int i = 0; i < static_cast<int>(pipes_.size()); ++i) {
        const auto& ps = pipes_[i];
        const auto& pipe_id = pipe_inputs_[i].id;
        const double dx = (ps.num_nodes > 1)
            ? (ps.L / static_cast<double>(ps.num_nodes - 1))
            : ps.L;
        const double segment_capacity_ft3 = dx * ps.area;

        double avg_V = 0.0;
        for (int j = 0; j < ps.num_nodes; ++j) {
            const double v = ps.V[static_cast<std::size_t>(j)];
            if (std::isnan(v) || std::isinf(v)) {
                throw std::runtime_error(
                    "Numerical instability: NaN/Inf detected in flow velocity for pipe '"
                    + pipe_id + "'");
            }
            avg_V += v;

            if (enable_interior_dvcm_
                && cavitation_model_ == CavitationModel::DVCM
                && j > 0
                && j < ps.num_nodes - 1) {
                const double Hj = ps.H[static_cast<std::size_t>(j)];
                const auto& seg = ps.segments[static_cast<std::size_t>(j)];
                throwIfInvalidInteriorSegmentState(
                    pipe_id,
                    j,
                    Hj,
                    v,
                    seg,
                    segment_capacity_ft3);
            }
        }
        avg_V /= ps.num_nodes;
        results.pipe_flow_gpm[pipe_id].push_back(avg_V * ps.area / GPM_TO_CFS);
    }

    if (record_pipe_profiles_) {
        for (int i = 0; i < static_cast<int>(pipes_.size()); ++i) {
            const auto& ps = pipes_[i];
            const auto& pipe_id = pipe_inputs_[i].id;
            const auto idx_it = profile_point_indices_.find(pipe_id);
            if (idx_it == profile_point_indices_.end()) {
                continue;
            }

            std::vector<double> head_row;
            std::vector<double> pressure_row;
            std::vector<double> velocity_row;
            std::vector<int> cavitation_row;
            std::vector<double> cavity_volume_row;
            std::vector<int> cavity_active_row;
            head_row.reserve(idx_it->second.size());
            pressure_row.reserve(idx_it->second.size());
            velocity_row.reserve(idx_it->second.size());
            cavitation_row.reserve(idx_it->second.size());
            if (enable_interior_dvcm_) {
                cavity_volume_row.reserve(idx_it->second.size());
                cavity_active_row.reserve(idx_it->second.size());
            }

            const double P_vapor_psi = p_vapor_ / PSI_TO_FT;

            for (int j : idx_it->second) {
                const double Hj = ps.H[j];
                const double zj = pipeGridElevationFt(ps, j);
                if (std::isnan(Hj) || std::isinf(Hj)) {
                    throw std::runtime_error(
                        "Numerical instability: NaN/Inf detected in profile head for pipe '" + pipe_id + "'");
                }
                if (std::isnan(ps.V[j]) || std::isinf(ps.V[j])) {
                    throw std::runtime_error(
                        "Numerical instability: NaN/Inf detected in profile velocity for pipe '" + pipe_id + "'");
                }
                const double P_psi = (Hj - zj) / PSI_TO_FT;
                head_row.push_back(Hj);
                pressure_row.push_back(P_psi);
                velocity_row.push_back(ps.V[j]);
                cavitation_row.push_back(P_psi <= P_vapor_psi ? 1 : 0);
                if (enable_interior_dvcm_) {
                    const auto& seg = ps.segments[static_cast<std::size_t>(j)];
                    const double dx = (ps.num_nodes > 1)
                        ? (ps.L / static_cast<double>(ps.num_nodes - 1))
                        : ps.L;
                    throwIfInvalidInteriorSegmentState(
                        pipe_id,
                        j,
                        Hj,
                        ps.V[static_cast<std::size_t>(j)],
                        seg,
                        dx * ps.area);
                    cavity_volume_row.push_back(seg.cavity_volume_ft3);
                    cavity_active_row.push_back(seg.cavity_active ? 1 : 0);
                }
            }

            results.pipe_profile_head_ft[pipe_id].push_back(std::move(head_row));
            results.pipe_profile_pressure_psi[pipe_id].push_back(std::move(pressure_row));
            results.pipe_profile_velocity_fps[pipe_id].push_back(std::move(velocity_row));
            results.pipe_profile_cavitation[pipe_id].push_back(std::move(cavitation_row));
            if (enable_interior_dvcm_) {
                results.pipe_profile_cavity_volume[pipe_id].push_back(std::move(cavity_volume_row));
                results.pipe_profile_cavity_active[pipe_id].push_back(std::move(cavity_active_row));
            }
        }
    }
}

// ── Main run loop ─────────────────────────────────────────────────────────────

SimResults MOCSolver::run(double total_time_s, double dt,
                          double p_vapor_psi, double usf_tau,
                          double k_bru, std::optional<CavitationModel> cavitation_model,
                          bool record_pipe_profiles, int profile_stride,
                          bool enable_interior_dvcm) {
    if (dt <= 0.0) {
        throw std::invalid_argument("Timestep dt must be strictly positive");
    }
    if (total_time_s < 0.0) {
        throw std::invalid_argument("Total simulation time must be non-negative");
    }
    if (usf_tau <= 0.0) {
        throw std::invalid_argument("Filter time constant usf_tau must be strictly positive");
    }
    if (profile_stride < 1) {
        throw std::invalid_argument("profile_stride must be >= 1");
    }

    dt_      = dt;
    p_vapor_ = p_vapor_psi * PSI_TO_FT; // convert psi → ft
    if (cavitation_model.has_value()) {
        cavitation_model_ = *cavitation_model;
    }
    usf_tau_ = usf_tau;
    k_Bru_   = k_bru;
    record_pipe_profiles_ = record_pipe_profiles;
    profile_stride_       = profile_stride;
    enable_interior_dvcm_ = enable_interior_dvcm;

    initGrid();

    const int num_steps = static_cast<int>(std::ceil(total_time_s / dt));

    // Pre-allocate result containers
    SimResults results;
    results.time.reserve(num_steps);
    for (const auto& ni : node_inputs_) {
        results.node_head      [ni.id].reserve(num_steps);
        results.node_pressure  [ni.id].reserve(num_steps);
        results.node_cavitation[ni.id].reserve(num_steps);
        results.node_cavity_volume[ni.id].reserve(num_steps);
        results.node_cavity_active[ni.id].reserve(num_steps);
        results.node_cavity_collapse_flag[ni.id].reserve(num_steps);
        results.node_cavity_collapse_count[ni.id].reserve(num_steps);
        if (ni.type == NodeType::Pump) {
            results.pump_speed[ni.id].reserve(num_steps);
        }
        if (ni.type == NodeType::Turbine) {
            results.turbine_speed[ni.id].reserve(num_steps);
        }
    }
    for (const auto& pi : pipe_inputs_) {
        results.pipe_flow_gpm[pi.id].reserve(num_steps);
    }

    if (record_pipe_profiles_) {
        initializePipeProfileCapture(results);
        for (const auto& pi : pipe_inputs_) {
            results.pipe_profile_head_ft[pi.id].reserve(num_steps);
            results.pipe_profile_pressure_psi[pi.id].reserve(num_steps);
            results.pipe_profile_velocity_fps[pi.id].reserve(num_steps);
            results.pipe_profile_cavitation[pi.id].reserve(num_steps);
            if (enable_interior_dvcm_) {
                results.pipe_profile_cavity_volume[pi.id].reserve(num_steps);
                results.pipe_profile_cavity_active[pi.id].reserve(num_steps);
            }
        }
    }

    for (int step = 0; step < num_steps; ++step) {
        // Apply scheduled valve settings at the START of this step
        // (setting in effect during step N corresponds to t = N*dt)
        if (!resolved_valve_schedules_.empty()) {
            const double t_now = static_cast<double>(step) * dt;
            for (auto& rs : resolved_valve_schedules_) {
                nodes_[rs.node_idx].input.current_setting = interpSchedule(rs.schedule, t_now);
            }
        }
        if (!resolved_pump_schedules_.empty()) {
            const double t_now = static_cast<double>(step) * dt;
            for (auto& rs : resolved_pump_schedules_) {
                nodes_[rs.node_idx].command_speed = interpSchedule(rs.schedule, t_now);
            }
        }
        if (!resolved_demand_schedules_.empty()) {
            const double t_now = static_cast<double>(step) * dt;
            for (auto& rs : resolved_demand_schedules_) {
                nodes_[rs.node_idx].input.demand = interpSchedule(rs.schedule, t_now);
            }
        }
        if (!resolved_head_schedules_.empty()) {
            const double t_now = static_cast<double>(step) * dt;
            for (auto& rs : resolved_head_schedules_) {
                nodes_[rs.node_idx].input.head = interpSchedule(rs.schedule, t_now);
            }
        }
        stepMOC();
        results.time.push_back(static_cast<double>(step + 1) * dt);
        recordStep(results);
    }

    return results;
}

void MOCSolver::evaluateControlRules(double t_now) {
    if (control_rule_states_.empty()) return;

    for (auto& state : control_rule_states_) {
        const auto& rule = state.input;
        
        // 1. Get the monitored value
        double monitored_val = 0.0;
        if (rule.monitored_quantity == "flow") {
            if (state.monitored_pipe_idx != -1) {
                const auto& ps = pipes_[state.monitored_pipe_idx];
                double avg_V = 0.0;
                for (double v : ps.V) avg_V += v;
                avg_V /= ps.num_nodes;
                monitored_val = avg_V * ps.area / GPM_TO_CFS; // GPM (signed)
            }
        } else {
            if (state.monitored_node_idx != -1) {
                const auto& ns = nodes_[state.monitored_node_idx];
                const auto& n = ns.input;
                if (rule.monitored_quantity == "pressure") {
                    monitored_val = get_node_pressure_by_idx(state.monitored_node_idx);
                } else if (rule.monitored_quantity == "head") {
                    monitored_val = get_node_head_by_idx(state.monitored_node_idx);
                } else if (rule.monitored_quantity == "level") {
                    double H = get_node_head_by_idx(state.monitored_node_idx);
                    monitored_val = (n.max_level > 1e-6) 
                        ? 100.0 * (H - n.elevation) / n.max_level 
                        : 0.0;
                }
            }
        }
        
        // 2. Evaluate control type logic
        if (rule.type == ControlType::Threshold) {
            bool condition_met = false;
            if (rule.condition == "lt") {
                condition_met = (monitored_val < rule.threshold);
            } else if (rule.condition == "gt") {
                condition_met = (monitored_val > rule.threshold);
            }
            
            if (condition_met) {
                if (state.action_node_idx != -1) {
                    auto& ns = nodes_[state.action_node_idx];
                    if (ns.input.type == NodeType::Pump) {
                        const double spd = std::clamp(rule.target, 0.0, 100.0);
                        ns.command_speed = spd;
                    } else if (ns.input.type == NodeType::Valve || ns.input.type == NodeType::Turbine) {
                        ns.input.current_setting = std::clamp(rule.target, 0.0, 100.0);
                    }
                }
                state.last_active = true;
            } else {
                if (state.action_node_idx != -1) {
                    auto& ns = nodes_[state.action_node_idx];
                    if (ns.input.type == NodeType::Pump) {
                        ns.command_speed = 0.0;
                    } else if (ns.input.type == NodeType::Valve || ns.input.type == NodeType::Turbine) {
                        ns.input.current_setting = 0.0;
                    }
                }
                state.last_active = false;
            }
        } 
        else if (rule.type == ControlType::Deadband) {
            double low_limit = rule.threshold;
            double high_limit = rule.threshold + rule.deadband;
            
            bool turn_on = false;
            bool turn_off = false;
            
            if (rule.action == "fill") {
                if (monitored_val < low_limit) {
                    turn_on = true;
                } else if (monitored_val > high_limit) {
                    turn_off = true;
                }
            } else if (rule.action == "drain") {
                if (monitored_val > high_limit) {
                    turn_on = true;
                } else if (monitored_val < low_limit) {
                    turn_off = true;
                }
            }
            
            bool active = state.last_active;
            if (turn_on) active = true;
            if (turn_off) active = false;
            state.last_active = active;
            
            if (state.action_node_idx != -1) {
                auto& ns = nodes_[state.action_node_idx];
                double target_val = active ? 100.0 : 0.0;
                if (ns.input.type == NodeType::Pump) {
                    ns.command_speed = target_val;
                } else if (ns.input.type == NodeType::Valve || ns.input.type == NodeType::Turbine) {
                    ns.input.current_setting = target_val;
                }
            }
        } 
        else if (rule.type == ControlType::PID) {
            double error = rule.target - monitored_val;
            double P = rule.kp * error;
            state.integral_error += error * dt_;
            
            double D = 0.0;
            if (state.has_prev_error) {
                D = rule.kd * (error - state.previous_error) / dt_;
            }
            state.previous_error = error;
            state.has_prev_error = true;
            
            double I = rule.ki * state.integral_error;
            double output = P + I + D;
            double clamped_output = std::clamp(output, 0.0, 100.0);
            
            if (rule.ki != 0.0) {
                double min_i = 0.0;
                double max_i = 100.0;
                if (rule.ki > 0.0) {
                    state.integral_error = std::clamp(state.integral_error, min_i / rule.ki, max_i / rule.ki);
                } else {
                    state.integral_error = std::clamp(state.integral_error, max_i / rule.ki, min_i / rule.ki);
                }
            }
            
            if (state.action_node_idx != -1) {
                auto& ns = nodes_[state.action_node_idx];
                if (ns.input.type == NodeType::Pump) {
                    ns.command_speed = clamped_output;
                } else if (ns.input.type == NodeType::Valve || ns.input.type == NodeType::Turbine) {
                    ns.input.current_setting = clamped_output;
                }
            }
        } 
        else if (rule.type == ControlType::PCV) {
            if (state.monitored_node_idx != -1 && state.action_node_idx != -1) {
                auto& pump = nodes_[state.monitored_node_idx];
                auto& valve = nodes_[state.action_node_idx];
                
                double cmd_speed = pump.command_speed;
                double ramp_open = std::max(1e-6, rule.threshold);
                double ramp_close = std::max(1e-6, rule.deadband);
                
                if (cmd_speed > 0.0 && pump.input.has_power) {
                    if (state.pcv_phase == "idle" || state.pcv_phase == "closing" || state.pcv_phase == "off") {
                        state.pcv_phase = "opening";
                        state.pcv_timer = 0.0;
                    }
                    
                    if (state.pcv_phase == "opening") {
                        state.pcv_timer += dt_;
                        double frac = state.pcv_timer / ramp_open;
                        valve.input.current_setting = std::clamp(frac * 100.0, 0.0, 100.0);
                        if (state.pcv_timer >= ramp_open) {
                            valve.input.current_setting = 100.0;
                            state.pcv_phase = "running";
                        }
                    } else if (state.pcv_phase == "running") {
                        valve.input.current_setting = 100.0;
                    }
                    pump.input.current_speed = cmd_speed;
                    pump.command_speed = cmd_speed;
                } else {
                    if (state.pcv_phase == "running" || state.pcv_phase == "opening") {
                        state.pcv_phase = "closing";
                        state.pcv_timer = 0.0;
                    }
                    
                    if (state.pcv_phase == "closing") {
                        state.pcv_timer += dt_;
                        double frac = 1.0 - (state.pcv_timer / ramp_close);
                        valve.input.current_setting = std::clamp(frac * 100.0, 0.0, 100.0);
                        if (state.pcv_timer >= ramp_close || valve.input.current_setting <= 0.0) {
                            valve.input.current_setting = 0.0;
                            state.pcv_phase = "idle";
                            if (pump.input.inertia_wr2 <= 0.0) {
                                pump.input.current_speed = 0.0;
                                pump.command_speed = 0.0;
                            }
                        } else if (pump.input.has_power) {
                            pump.input.current_speed = 100.0;
                            // Keep pump.command_speed at 0.0 (user's target) to allow PCV to closing state
                        } else if (pump.input.inertia_wr2 <= 0.0) {
                            pump.input.current_speed = 0.0;
                            pump.command_speed = 0.0;
                        }
                    } else if (state.pcv_phase == "idle" || state.pcv_phase == "off") {
                        valve.input.current_setting = 0.0;
                        if (pump.input.inertia_wr2 <= 0.0) {
                            pump.input.current_speed = 0.0;
                            pump.command_speed = 0.0;
                        }
                    }
                }
            }
        }
    }
}

} // namespace rthym
