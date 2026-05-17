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

namespace rthym {

// ── String ↔ NodeType helpers ─────────────────────────────────────────────────

NodeType parseNodeType(const std::string& s) {
    if (s == "Tank")                return NodeType::Tank;
    if (s == "PressureBoundary")    return NodeType::PressureBoundary;
    if (s == "FuelTank")            return NodeType::FuelTank;
    if (s == "Valve")               return NodeType::Valve;
    if (s == "Turbine")             return NodeType::Turbine;
    if (s == "Pump")                return NodeType::Pump;
    if (s == "SurgeTank")           return NodeType::SurgeTank;
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
        case NodeType::FuelTank:            return "FuelTank";
        case NodeType::Valve:               return "Valve";
        case NodeType::Turbine:             return "Turbine";
        case NodeType::Pump:                return "Pump";
        case NodeType::SurgeTank:           return "SurgeTank";
        case NodeType::Standpipe:           return "Standpipe";
        case NodeType::HydropneumaticTank:  return "HydropneumaticTank";
        case NodeType::InflowNode:          return "InflowNode";
        case NodeType::OutflowNode:         return "OutflowNode";
        default:                            return "Junction";
    }
}

// ── Public input API ──────────────────────────────────────────────────────────

void MOCSolver::add_node(const NodeInput& n)  { node_inputs_.push_back(n); }
void MOCSolver::add_pipe(const PipeInput& p)  { pipe_inputs_.push_back(p); }

void MOCSolver::clear() {
    node_inputs_.clear();
    pipe_inputs_.clear();
    valve_schedules_.clear();
}

void MOCSolver::set_valve_setting(const std::string& id, double pct) {
    auto it = node_idx_map_.find(id);
    if (it != node_idx_map_.end())
        nodes_[it->second].input.current_setting = pct;
}

void MOCSolver::set_pump_speed(const std::string& id, double pct) {
    auto it = node_idx_map_.find(id);
    if (it != node_idx_map_.end())
        nodes_[it->second].input.current_speed = pct;
}

void MOCSolver::set_node_demand(const std::string& id, double demand_gpm) {
    auto it = node_idx_map_.find(id);
    if (it != node_idx_map_.end())
        nodes_[it->second].input.demand = demand_gpm;
}

void MOCSolver::set_valve_schedule(const std::string& id,
                                   const std::vector<std::pair<double,double>>& schedule) {
    valve_schedules_[id] = schedule;
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
            return n.elevation + (n.level / 100.0) * n.max_level;
        case NodeType::PressureBoundary:
            return n.head;
        case NodeType::FuelTank:
            return 0.0;
        case NodeType::SurgeTank:
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

    // Build node state vector and lookup map
    nodes_.reserve(node_inputs_.size());
    for (int i = 0; i < static_cast<int>(node_inputs_.size()); ++i) {
        NodeState ns;
        ns.input = node_inputs_[i];
        if (ns.input.type == NodeType::SurgeTank ||
            ns.input.type == NodeType::Standpipe)
            ns.surge_level_ft = ns.input.head; // initial water-surface elevation (ft HGL)
        if (ns.input.type == NodeType::HydropneumaticTank) {
            // Compute and store the polytropic gas constant:
            //   C = H_g_abs * V_g^n
            // At steady state there is no orifice flow, so H_P = H_tank:
            //   H_g_abs = (H_P_0 - elevation) + H_atm
            constexpr double H_ATM_FT = 33.9;  // ft  (1 atm = 14.696 psi)
            ns.gas_volume_ft3 = ns.input.gas_volume;
            const double H_g_abs0 = (ns.input.head - ns.input.elevation) + H_ATM_FT;
            ns.gas_constant = H_g_abs0 *
                std::pow(std::max(ns.gas_volume_ft3, 1e-6), ns.input.polytropic_n);
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

        const double diam_ft = p.diameter / 12.0;
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
            wave_speed = a0 / std::sqrt(
                1.0 + (K / p.youngs_modulus) * (p.diameter / p.wall_thickness) * c);
        }

        // ── Courant condition: Cr = a·dt/dx = 1 ───────────────────────────
        // Round number of segments to nearest integer, then back-compute
        // the exact wave speed that gives Cr = 1.0 for that integer count.
        const double dx_target = wave_speed * dt_;
        const int    num_segs  = std::max(1, static_cast<int>(std::round(p.length / dx_target)));
        ps.a_wave    = (p.length / num_segs) / dt_; // adjusted wave speed
        ps.num_nodes = num_segs + 1;

        // ── Darcy-Weisbach friction factor from Hazen-Williams ─────────────
        // Hf = 10.44 · L · Q^1.852 / (C^1.852 · D_in^4.871)  [all US units]
        const double Q_cfs     = p.flow_gpm * GPM_TO_CFS;
        const double vel_init  = (ps.area > 1e-9) ? Q_cfs / ps.area : 0.0;
        double Hf_pipe = 0.0;
        if (std::abs(p.flow_gpm) > 1e-4) {
            Hf_pipe = (10.44 * p.length * std::pow(std::abs(p.flow_gpm), 1.852))
                    / (std::pow(p.roughness, 1.852) * std::pow(p.diameter, 4.871));
        }
        double f_calc = 0.02;
        if (std::abs(vel_init) > 1e-4) {
            f_calc = (Hf_pipe * ps.D * 2.0 * G_FT_S2)
                   / (p.length * vel_init * vel_init);
        }
        ps.f = std::max(0.001, std::min(f_calc, 0.5));

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
        // "Fixed-head" sources: Tank, PressureBoundary, FuelTank, SurgeTank.
        // Everything else (Junction, Valve, Pump, Turbine, In/OutflowNode)
        // is treated as an inferred endpoint.
        auto is_fixed_head = [](NodeType t) {
            return t == NodeType::Tank || t == NodeType::PressureBoundary ||
                   t == NodeType::FuelTank || t == NodeType::SurgeTank ||
                   t == NodeType::Standpipe || t == NodeType::HydropneumaticTank;
        };
        bool from_fixed = false, to_fixed = false;
        {
            auto fit = node_idx_map_.find(p.from_node);
            auto tit = node_idx_map_.find(p.to_node);
            if (fit != node_idx_map_.end()) from_fixed = is_fixed_head(nodes_[fit->second].input.type);
            if (tit != node_idx_map_.end()) to_fixed   = is_fixed_head(nodes_[tit->second].input.type);
        }

        const double sgn = (p.flow_gpm >= 0.0) ? 1.0 : -1.0;
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
                    return t == NodeType::Valve || t == NodeType::Pump;
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
}

// ── Single MOC time step ──────────────────────────────────────────────────────
// Mirrors transientWorker.js :: stepMOC()

void MOCSolver::stepMOC() {
    const double g          = G_FT_S2;
    const double alpha_filt = dt_ / usf_tau_; // IIR coefficient: dt / τ_BL

    const int num_pipes = static_cast<int>(pipes_.size());
    const int num_nodes = static_cast<int>(nodes_.size());

    // Allocate output arrays (avoids aliasing during computation)
    std::vector<std::vector<double>> newH(num_pipes), newV(num_pipes);
    for (int i = 0; i < num_pipes; ++i) {
        newH[i].resize(pipes_[i].num_nodes);
        newV[i].resize(pipes_[i].num_nodes);
    }

    // ── Per-pipe: IIR filter + interior C± equations + boundary chars ────────

    // Boundary characteristics arriving at each pipe end
    struct PipeBndry {
        double area;   // ft²
        double B;      // a/g  (pipe impedance)
        double C_P;    // C+ at downstream end  (→ to_node)
        double C_M;    // C- at upstream end    (→ from_node)
    };
    std::vector<PipeBndry> bndry(num_pipes);

    for (int i = 0; i < num_pipes; ++i) {
        auto& ps  = pipes_[i];
        const int  N    = ps.num_nodes;
        const double dx = ps.a_wave * dt_;
        const double B  = ps.a_wave / g;               // ft·s/ft² = s/ft
        const double R  = ps.f * dx / (2.0 * g * ps.D); // steady-friction resistance
        // Brunone (1991) unsteady-friction scale:  k_u = k_Bru * B  [units: s]
        // k_Bru is the dimensionless Brunone coefficient; Vardy-Brown (1996) gives
        //   k_Bru = C*/sqrt(π),  C* = 7.41/Re^0.352   (turbulent, smooth pipe)
        // Typical range: 0.02–0.15.  The USF term is zero when k_Bru = 0.
        //
        // BUG HISTORY: was  k_u = dt_ * B  (timestep-dependent, 10–50× too large).
        //   That coefficient has units s² not s and amplified the first Joukowsky
        //   peak ~22 % rather than providing mild physical damping.  Fixed here by
        //   decoupling k_u from the timestep and using the correct Brunone formula.
        const double k_u = k_Bru_ * B;                // unsteady-friction scale  [s]

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

            newH[i][j] = (C_P + C_M) / 2.0;
            newV[i][j] = (C_P - C_M) / (2.0 * B);
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

        const auto& in_pipes  = node_inflow_pipes_ [n.id]; // pipes arriving
        const auto& out_pipes = node_outflow_pipes_[n.id]; // pipes leaving

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

        switch (n.type) {

        // ── Fixed-head boundaries ──────────────────────────────────────────
        case NodeType::Tank:
        case NodeType::PressureBoundary:
        case NodeType::FuelTank: {
            const double H_f = getInitialHead(ns);
            for (int pi : in_pipes)  set_downstream(pi, H_f);
            for (int pi : out_pipes) set_upstream(pi, H_f);
            break;
        }

        // ── Open surge tank / standpipe (free surface) ───────────────────
        // H = current water-surface elevation (= HGL for open-to-atm tank).
        // dH/dt = Q_net / A_s   (continuity, Wylie & Streeter §7.3)
        case NodeType::SurgeTank:   // backward-compat alias
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

            // Solve:  Keq·Q² + Q − C_eq = 0
            double Q_net;
            if (Keq < 1e-12) {
                Q_net = C_eq;  // zero orifice resistance → H_P = H_tank
            } else if (C_eq >= 0.0) {
                Q_net = (-1.0 + std::sqrt(1.0 + 4.0 * Keq * C_eq)) / (2.0 * Keq);
            } else {
                Q_net = ( 1.0 - std::sqrt(1.0 - 4.0 * Keq * C_eq)) / (2.0 * Keq);
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
            ns.gas_volume_ft3 = std::max(1e-9,
                std::min(ns.gas_volume_ft3 - Q_net * dt_, n.tank_volume));
            break;
        }

        // ── Valve / Turbine ────────────────────────────────────────────────
        // Head loss: ΔH = K_eq · Q²   (K_eq = K / (2g·A_v²))
        // Combined with C± gives a quadratic in Q.
        case NodeType::Valve:
        case NodeType::Turbine: {
            const double setting = std::max(1e-6, n.current_setting);

            double K; // dimensionless loss coefficient
            if (n.type == NodeType::Valve) {
                // K = (100/setting)² − 1   (K→∞ when fully closed)
                K = std::pow(100.0 / setting, 2.0) - 1.0;
            } else {
                // Turbine modelled as variable-K orifice
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

            // Quadratic solve helper: K_eq·Q² + B_eq·Q − C_eq = 0
            auto quadratic_Q = [&](double Keq, double Beq, double Ceq) -> double {
                if (Keq < 1e-4) return Ceq / Beq;
                if (Ceq >= 0.0)
                    return (-Beq + std::sqrt(std::max(0.0, Beq*Beq + 4.0*Keq*Ceq))) / (2.0*Keq);
                else
                    return ( Beq - std::sqrt(std::max(0.0, Beq*Beq - 4.0*Keq*Ceq))) / (2.0*Keq);
            };

            if (in_pipes.size() == 1 && out_pipes.size() == 1) {
                const int bIn  = in_pipes[0];
                const int bOut = out_pipes[0];
                const double B_eq = (bndry[bIn].B  / bndry[bIn].area)
                                  + (bndry[bOut].B / bndry[bOut].area);
                const double C_eq = bndry[bIn].C_P - bndry[bOut].C_M;
                double Q = quadratic_Q(K_eq, B_eq, C_eq);

                double H_up = bndry[bIn].C_P  - (bndry[bIn].B  / bndry[bIn].area)  * Q;
                double H_dn = bndry[bOut].C_M + (bndry[bOut].B / bndry[bOut].area) * Q;

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
            if (spd <= 0.0) {
                // Pump off: dead-end (zero-velocity) boundary
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
                break;
            }

            const double H_D   = n.design_head;
            const double Q_D   = n.design_flow;
            const double alpha  = (4.0 / 3.0) * H_D;            // ft
            const double beta   = (1.0 / 3.0) * H_D / (Q_D * Q_D);
            const double beta_cfs = beta * 201449.26;            // 448.831² ≈ 201449
            const double s  = spd / 100.0;
            const double s2 = s * s;

            if (in_pipes.size() == 1 && out_pipes.size() == 1) {
                const int bIn  = in_pipes[0];
                const int bOut = out_pipes[0];
                const double B_eq = (bndry[bIn].B  / bndry[bIn].area)
                                  + (bndry[bOut].B / bndry[bOut].area);
                const double C_eq = bndry[bIn].C_P - bndry[bOut].C_M;

                // Equation: beta_cfs·s²·Q² + B_eq·Q − (C_eq + alpha·s²) = 0
                const double a_q = beta_cfs * s2;
                const double b_q = B_eq;
                const double c_q = -(C_eq + alpha * s2);

                double Q = 0.0;
                if (a_q < 1e-10) {
                    Q = -c_q / b_q;
                } else {
                    const double disc = b_q * b_q - 4.0 * a_q * c_q;
                    if (disc >= 0.0)
                        Q = (-b_q + std::sqrt(disc)) / (2.0 * a_q);
                }
                Q = std::max(0.0, Q); // pumps do not reverse (simplification)

                double H_up = bndry[bIn].C_P  - (bndry[bIn].B  / bndry[bIn].area)  * Q;
                double H_dn = bndry[bOut].C_M + (bndry[bOut].B / bndry[bOut].area) * Q;

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

                set_downstream(bIn,  H_up);
                set_upstream  (bOut, H_dn);
            } else {
                // Multi-pipe pump: approximate with static head rise
                const double H_base = getInitialHead(ns);
                for (int pi : in_pipes)  set_downstream(pi, std::max(H_vap, H_base - alpha * s2));
                for (int pi : out_pipes) set_upstream  (pi, std::max(H_vap, H_base + alpha * s2));
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

            double H_P = (sum_AB > 1e-12)
                ? (sum_AB_C - Q_dem) / sum_AB
                : getInitialHead(ns);
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
        pipes_[i].H = std::move(newH[i]);
        pipes_[i].V = std::move(newV[i]);
    }
}

// ── Record current state into results vectors ─────────────────────────────────

void MOCSolver::recordStep(SimResults& results) const {
    for (int ni = 0; ni < static_cast<int>(nodes_.size()); ++ni) {
        const auto& ns = nodes_[ni];
        const auto& n  = ns.input;

        // Head: prefer downstream end of inflow pipe, else upstream end of outflow pipe
        double H = getInitialHead(ns);
        const auto& in_p  = node_inflow_pipes_ .at(n.id);   // guaranteed to exist after init
        const auto& out_p = node_outflow_pipes_.at(n.id);

        if (!in_p.empty())
            H = pipes_[in_p[0]].H.back();
        else if (!out_p.empty())
            H = pipes_[out_p[0]].H.front();

        const double P_psi   = (H - n.elevation) / PSI_TO_FT;
        const double P_vapor = p_vapor_ / PSI_TO_FT;

        results.node_head    [n.id].push_back(H);
        results.node_pressure[n.id].push_back(P_psi);
        results.node_cavitation[n.id].push_back(P_psi <= P_vapor ? 1 : 0);
    }

    for (int i = 0; i < static_cast<int>(pipes_.size()); ++i) {
        const auto& ps = pipes_[i];
        double avg_V = 0.0;
        for (double v : ps.V) avg_V += v;
        avg_V /= ps.num_nodes;
        results.pipe_flow_gpm[pipe_inputs_[i].id].push_back(avg_V * ps.area / GPM_TO_CFS);
    }
}

// ── Main run loop ─────────────────────────────────────────────────────────────

SimResults MOCSolver::run(double total_time_s, double dt,
                          double p_vapor_psi, double usf_tau,
                          double k_bru) {
    dt_      = dt;
    p_vapor_ = p_vapor_psi * PSI_TO_FT; // convert psi → ft
    usf_tau_ = usf_tau;
    k_Bru_   = k_bru;

    initGrid();

    const int num_steps = static_cast<int>(std::ceil(total_time_s / dt));

    // Pre-allocate result containers
    SimResults results;
    results.time.reserve(num_steps);
    for (const auto& ni : node_inputs_) {
        results.node_head      [ni.id].reserve(num_steps);
        results.node_pressure  [ni.id].reserve(num_steps);
        results.node_cavitation[ni.id].reserve(num_steps);
    }
    for (const auto& pi : pipe_inputs_) {
        results.pipe_flow_gpm[pi.id].reserve(num_steps);
    }

    // Make sure every node id has an entry in adjacency maps
    // (isolated nodes will have empty vectors, which is fine)
    for (const auto& ni : node_inputs_) {
        node_inflow_pipes_ .emplace(ni.id, std::vector<int>{});
        node_outflow_pipes_.emplace(ni.id, std::vector<int>{});
    }

    for (int step = 0; step < num_steps; ++step) {
        // Apply scheduled valve settings at the START of this step
        // (setting in effect during step N corresponds to t = N*dt)
        if (!valve_schedules_.empty()) {
            const double t_now = static_cast<double>(step) * dt;
            for (auto& [vid, sched] : valve_schedules_) {
                auto nit = node_idx_map_.find(vid);
                if (nit != node_idx_map_.end())
                    nodes_[nit->second].input.current_setting =
                        interpSchedule(sched, t_now);
            }
        }
        stepMOC();
        results.time.push_back(static_cast<double>(step + 1) * dt);
        recordStep(results);
    }

    return results;
}

} // namespace rthym
