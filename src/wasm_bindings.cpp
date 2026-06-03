// wasm_bindings.cpp
// Copyright (c) 2026 Jason Lillywhite <jason@lillywhitewater.com>
// SPDX-License-Identifier: MIT
// Author: Jason Lillywhite <jason@lillywhitewater.com>
// Emscripten bindings for the rthym MOC solver.
//

#include <emscripten/bind.h>
#include <emscripten/val.h>
#include "moc_solver.hpp"
#include <cmath>
#include <string>
#include <vector>

using namespace emscripten;
using namespace rthym;

emscripten::val MOCSolver::get_step_results() const {
    emscripten::val nodes_obj = emscripten::val::object();
    emscripten::val links_obj = emscripten::val::object();

    for (const auto& ns : nodes_) {
        const auto& n = ns.input;
        emscripten::val node_res = emscripten::val::object();

        auto in_it = node_inflow_pipes_.find(n.id);
        auto out_it = node_outflow_pipes_.find(n.id);
        const auto& in_pipes = (in_it != node_inflow_pipes_.end()) ? in_it->second : std::vector<int>{};
        const auto& out_pipes = (out_it != node_outflow_pipes_.end()) ? out_it->second : std::vector<int>{};

        double upH = getInitialHead(ns);
        double downH = getInitialHead(ns);
        double h = upH;
        if (!in_pipes.empty()) {
            int pi = in_pipes[0];
            upH = pipes_[pi].H.back();
            h = upH;
        }
        if (!out_pipes.empty()) {
            int pi = out_pipes[0];
            downH = pipes_[pi].H.front();
            if (in_pipes.empty()) {
                h = downH;
            }
        }

        double upPressurePsi = (upH - n.elevation) / 2.31;
        double downPressurePsi = (downH - n.elevation) / 2.31;
        double pressure = (h - n.elevation) / 2.31;

        double nodeFlowGPM = 0.0;
        if (!out_pipes.empty()) {
            int pi = out_pipes[0];
            nodeFlowGPM = pipes_[pi].V.front() * pipes_[pi].area / GPM_TO_CFS;
        } else if (!in_pipes.empty()) {
            int pi = in_pipes[0];
            nodeFlowGPM = pipes_[pi].V.back() * pipes_[pi].area / GPM_TO_CFS;
        }

        if (n.type == NodeType::CheckValve && n.flipped) {
            nodeFlowGPM = -nodeFlowGPM;
        }

        double actualDemand = 0.0;
        if (n.type == NodeType::InflowNode || n.type == NodeType::OutflowNode) {
            actualDemand = ns.actual_demand;
        }

        const bool reverseFlowBlocked =
            n.type == NodeType::CheckValve &&
            (n.flipped ? (upH > downH + 1e-9) : (downH > upH + 1e-9)) &&
            std::abs(nodeFlowGPM) <= 1e-6;

        node_res.set("type", nodeTypeToStr(n.type));
        node_res.set("pressure", pressure);
        node_res.set("upstreamPressure", upPressurePsi);
        node_res.set("downstreamPressure", downPressurePsi);
        node_res.set("upstreamHead", upH);
        node_res.set("downstreamHead", downH);
        node_res.set("flowGPM", nodeFlowGPM);
        node_res.set("actualDemandGPM", actualDemand);
        node_res.set("reverseFlowBlocked", reverseFlowBlocked);
        node_res.set("cavitation", upH <= n.elevation + p_vapor_ || downH <= n.elevation + p_vapor_);
        node_res.set("cavityActive", ns.cavity_active);
        node_res.set("cavityVolume", ns.cavity_volume_ft3);
        node_res.set("cavityCollapseFlag", ns.cavity_collapsed_this_step);
        node_res.set("cavityCollapseCount", ns.cavity_collapse_count);
        node_res.set("currentSpeed", ns.input.current_speed);
        node_res.set("currentSetting", ns.input.current_setting);
        if (n.type == NodeType::Pump || n.type == NodeType::Turbine) {
            node_res.set("hasPower", ns.input.has_power);
        } else {
            node_res.set("hasPower", emscripten::val::undefined());
        }

        if (n.type == NodeType::Standpipe) {
            node_res.set("surgeLevel", ns.surge_level_ft);
        } else {
            node_res.set("surgeLevel", emscripten::val::undefined());
        }

        if (n.type == NodeType::HydropneumaticTank || n.type == NodeType::AirValve) {
            node_res.set("liveGasVol", ns.gas_volume_ft3);
            node_res.set("gasPressure", ns.gas_pressure_psi);
        } else {
            node_res.set("liveGasVol", emscripten::val::undefined());
            node_res.set("gasPressure", emscripten::val::undefined());
        }

        if (n.type == NodeType::AirValve) {
            node_res.set("lossRate", ns.air_loss_rate_gpm);
            node_res.set("cumulativeLoss", ns.air_cumulative_loss_gal);
        } else {
            node_res.set("lossRate", emscripten::val::undefined());
            node_res.set("cumulativeLoss", emscripten::val::undefined());
        }

        if (n.type == NodeType::HydropneumaticTank) {
            node_res.set("tankFlowGPM", ns.tank_flow_gpm);
        } else {
            node_res.set("tankFlowGPM", emscripten::val::undefined());
        }

        if (n.type == NodeType::CheckValve) {
            node_res.set("valvePosition", ns.valve_position);
        } else {
            node_res.set("valvePosition", emscripten::val::undefined());
        }

        nodes_obj.set(n.id, node_res);
    }

    for (size_t i = 0; i < pipe_inputs_.size(); ++i) {
        const auto& p = pipe_inputs_[i];
        const auto& ps = pipes_[i];

        double avgV = 0.0;
        for (double val : ps.V) {
            avgV += val;
        }
        if (!ps.V.empty()) {
            avgV /= ps.V.size();
        }

        double flowGPM = avgV * ps.area / GPM_TO_CFS;
        double headloss = std::abs(ps.H.front() - ps.H.back());

        emscripten::val pipe_res = emscripten::val::object();
        pipe_res.set("flowGPM", flowGPM);
        pipe_res.set("headloss", headloss);

        links_obj.set(p.id, pipe_res);
    }

    emscripten::val res = emscripten::val::object();
    res.set("nodes", nodes_obj);
    res.set("links", links_obj);
    return res;
}

EMSCRIPTEN_BINDINGS(rthym_moc) {
    class_<NodeInput>("NodeInput")
        .constructor<>()
        .property("id", &NodeInput::id)
        .property("type", 
            std::function<std::string(const NodeInput&)>([](const NodeInput& self) {
                return nodeTypeToStr(self.type);
            }),
            std::function<void(NodeInput&, const std::string&)>([](NodeInput& self, const std::string& s) {
                self.type = parseNodeType(s);
            })
        )
        .property("elevation", &NodeInput::elevation)
        .property("head", &NodeInput::head)
        .property("level", &NodeInput::level)
        .property("max_level", &NodeInput::max_level)
        .property("demand", &NodeInput::demand)
        .property("current_speed", &NodeInput::current_speed)
        .property("has_power", &NodeInput::has_power)
        .property("current_setting", &NodeInput::current_setting)
        .property("design_head", &NodeInput::design_head)
        .property("design_flow", &NodeInput::design_flow)
        .property("diameter", &NodeInput::diameter)
        .property("air_release_head", &NodeInput::air_release_head)
        .property("air_release_diameter", &NodeInput::air_release_diameter)
        .property("design_velocity", &NodeInput::design_velocity)
        .property("tank_area", &NodeInput::tank_area)
        .property("gas_volume", &NodeInput::gas_volume)
        .property("tank_volume", &NodeInput::tank_volume)
        .property("polytropic_n", &NodeInput::polytropic_n)
        .property("loss_coeff_in",    &NodeInput::loss_coeff_in)
        .property("loss_coeff_out",   &NodeInput::loss_coeff_out)
        .property("closure_time",     &NodeInput::closure_time)
        .property("flipped",          &NodeInput::flipped)
        .property("inertia_wr2",      &NodeInput::inertia_wr2)
        .property("speed_rpm",        &NodeInput::speed_rpm)
        .property("efficiency",       &NodeInput::efficiency)
        .property("ramp_time",        &NodeInput::ramp_time);

    class_<PipeInput>("PipeInput")
        .constructor<>()
        .property("id", &PipeInput::id)
        .property("from_node", &PipeInput::from_node)
        .property("to_node", &PipeInput::to_node)
        .property("length", &PipeInput::length)
        .property("diameter", &PipeInput::diameter)
        .property("roughness", &PipeInput::roughness)
        .property("minor_loss", &PipeInput::minor_loss)
        .property("flow_gpm", &PipeInput::flow_gpm)
        .property("wall_thickness", &PipeInput::wall_thickness)
        .property("youngs_modulus", &PipeInput::youngs_modulus)
        .property("poissons_ratio", &PipeInput::poissons_ratio);

    enum_<ControlType>("ControlType")
        .value("Threshold", ControlType::Threshold)
        .value("Deadband", ControlType::Deadband)
        .value("PID", ControlType::PID)
        .value("PCV", ControlType::PCV);

    enum_<CavitationModel>("CavitationModel")
        .value("LegacyClamp", CavitationModel::LegacyClamp)
        .value("DVCM", CavitationModel::DVCM);

    class_<ControlRuleInput>("ControlRuleInput")
        .constructor<>()
        .property("id", &ControlRuleInput::id)
        .property("type", &ControlRuleInput::type)
        .property("monitored_node", &ControlRuleInput::monitored_node)
        .property("controlled_node", &ControlRuleInput::controlled_node)
        .property("monitored_quantity", &ControlRuleInput::monitored_quantity)
        .property("monitored_pipe", &ControlRuleInput::monitored_pipe)
        .property("condition", &ControlRuleInput::condition)
        .property("threshold", &ControlRuleInput::threshold)
        .property("target", &ControlRuleInput::target)
        .property("deadband", &ControlRuleInput::deadband)
        .property("action", &ControlRuleInput::action)
        .property("kp", &ControlRuleInput::kp)
        .property("ki", &ControlRuleInput::ki)
        .property("kd", &ControlRuleInput::kd);

    class_<MOCSolver>("MOCSolver")
        .constructor<>()
        .function("add_node", &MOCSolver::add_node)
        .function("add_pipe", &MOCSolver::add_pipe)
        .function("clear", &MOCSolver::clear)
        .function("add_control_rule", &MOCSolver::add_control_rule)
        .function("clear_control_rules", &MOCSolver::clear_control_rules)
        .function("set_valve_setting", &MOCSolver::set_valve_setting)
        .function("set_pump_speed", &MOCSolver::set_pump_speed)
        .function("set_pump_command_speed", &MOCSolver::set_pump_command_speed)
        .function("set_pump_power", &MOCSolver::set_pump_power)
        .function("set_generator_connected", &MOCSolver::set_pump_power)
        .function("set_node_demand", &MOCSolver::set_node_demand)
        .function("set_node_head", &MOCSolver::set_node_head)
        .function("set_node_type", &MOCSolver::set_node_type)
        .function("initGrid", &MOCSolver::initGrid)
        .function("stepMOC", &MOCSolver::stepMOC)
        .function("set_dt", &MOCSolver::set_dt)
        .function("get_dt", &MOCSolver::get_dt)
        .function("set_p_vapor_psi", &MOCSolver::set_p_vapor_psi)
        .function("set_usf_tau", &MOCSolver::set_usf_tau)
        .function("set_k_bru", &MOCSolver::set_k_bru)
        .function("set_cavitation_model", &MOCSolver::set_cavitation_model)
        .function("get_cavitation_model", &MOCSolver::get_cavitation_model)
        .function("get_step_results", &MOCSolver::get_step_results);
}
