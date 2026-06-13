// types.hpp
// Copyright (c) 2026 Jason Lillywhite <jason@lillywhitewater.com>
// SPDX-License-Identifier: MIT
// Plain C++ step telemetry snapshots (no binding-layer types).
#pragma once

#include <optional>
#include <string>
#include <vector>

namespace rthym {

struct NodeStepSnapshot {
    std::string id;
    std::string type;
    double pressure_psi = 0.0;
    double upstream_pressure_psi = 0.0;
    double downstream_pressure_psi = 0.0;
    double upstream_head_ft = 0.0;
    double downstream_head_ft = 0.0;
    double flow_gpm = 0.0;
    double actual_demand_gpm = 0.0;
    bool reverse_flow_blocked = false;
    bool cavitation = false;
    bool cavity_active = false;
    bool cavity_collapse_flag = false;
    int cavity_collapse_count = 0;
    double cavity_volume_ft3 = 0.0;
    double current_speed = 0.0;
    double current_setting = 0.0;
    std::optional<bool> has_power;
    std::optional<double> surge_level_ft;
    std::optional<double> gas_volume_ft3;
    std::optional<double> gas_pressure_psi;
    std::optional<double> air_loss_rate_gpm;
    std::optional<double> air_cumulative_loss_gal;
    std::optional<double> tank_flow_gpm;
    std::optional<double> valve_position;
};

struct LinkStepSnapshot {
    std::string id;
    double flow_gpm = 0.0;
    double headloss_ft = 0.0;
};

struct StepSnapshot {
    double time_s = 0.0;
    std::vector<NodeStepSnapshot> nodes;
    std::vector<LinkStepSnapshot> links;
};

} // namespace rthym
