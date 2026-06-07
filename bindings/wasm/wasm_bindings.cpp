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
#include <utility>

using namespace emscripten;
using namespace rthym;

namespace {

void set_optional_bool(emscripten::val& obj, const char* key, const std::optional<bool>& value) {
    if (value.has_value()) {
        obj.set(key, *value);
    } else {
        obj.set(key, emscripten::val::undefined());
    }
}

void set_optional_double(emscripten::val& obj, const char* key, const std::optional<double>& value) {
    if (value.has_value()) {
        obj.set(key, *value);
    } else {
        obj.set(key, emscripten::val::undefined());
    }
}

} // namespace

emscripten::val convert_snapshot_to_val(const StepSnapshot& snapshot) {
    emscripten::val nodes_obj = emscripten::val::object();
    emscripten::val links_obj = emscripten::val::object();

    for (const auto& node : snapshot.nodes) {
        emscripten::val node_res = emscripten::val::object();
        node_res.set("type", node.type);
        node_res.set("pressure", node.pressure_psi);
        node_res.set("upstreamPressure", node.upstream_pressure_psi);
        node_res.set("downstreamPressure", node.downstream_pressure_psi);
        node_res.set("upstreamHead", node.upstream_head_ft);
        node_res.set("downstreamHead", node.downstream_head_ft);
        node_res.set("flowGPM", node.flow_gpm);
        node_res.set("actualDemandGPM", node.actual_demand_gpm);
        node_res.set("reverseFlowBlocked", node.reverse_flow_blocked);
        node_res.set("cavitation", node.cavitation);
        node_res.set("cavityActive", node.cavity_active);
        node_res.set("cavityVolume", node.cavity_volume_ft3);
        node_res.set("cavityCollapseFlag", node.cavity_collapse_flag);
        node_res.set("cavityCollapseCount", node.cavity_collapse_count);
        node_res.set("currentSpeed", node.current_speed);
        node_res.set("currentSetting", node.current_setting);
        set_optional_bool(node_res, "hasPower", node.has_power);
        set_optional_double(node_res, "surgeLevel", node.surge_level_ft);
        set_optional_double(node_res, "liveGasVol", node.gas_volume_ft3);
        set_optional_double(node_res, "gasPressure", node.gas_pressure_psi);
        set_optional_double(node_res, "lossRate", node.air_loss_rate_gpm);
        set_optional_double(node_res, "cumulativeLoss", node.air_cumulative_loss_gal);
        set_optional_double(node_res, "tankFlowGPM", node.tank_flow_gpm);
        set_optional_double(node_res, "valvePosition", node.valve_position);
        nodes_obj.set(node.id, node_res);
    }

    for (const auto& link : snapshot.links) {
        emscripten::val pipe_res = emscripten::val::object();
        pipe_res.set("flowGPM", link.flow_gpm);
        pipe_res.set("headloss", link.headloss_ft);
        links_obj.set(link.id, pipe_res);
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

    enum_<TransientFrictionModel>("TransientFrictionModel")
        .value("Steady", TransientFrictionModel::Steady)
        .value("QuasiSteady", TransientFrictionModel::QuasiSteady)
        .value("BrunoneIIR", TransientFrictionModel::BrunoneIIR)
        .value("Vitkovsky", TransientFrictionModel::Vitkovsky);

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
        .function("set_friction_model", &MOCSolver::set_friction_model)
        .function("get_friction_model", &MOCSolver::get_friction_model)
        .function("set_cavitation_model", &MOCSolver::set_cavitation_model)
        .function("get_cavitation_model", &MOCSolver::get_cavitation_model)
        .function("get_step_results", +[](const MOCSolver& solver) {
            return convert_snapshot_to_val(solver.capture_step_snapshot());
        });
}
