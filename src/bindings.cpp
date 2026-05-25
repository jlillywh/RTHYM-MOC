// bindings.cpp
// Copyright (c) 2026 Jason Lillywhite <jason@lillywhitewater.com>
// SPDX-License-Identifier: MIT
// Author: Jason Lillywhite <jason@lillywhitewater.com>
// PyBind11 Python bindings for the rthym MOC solver.
//
// Python API example:
//
//   import rthym_moc
//
//   solver = rthym_moc.MOCSolver()
//   solver.add_node(rthym_moc.NodeInput(id="R1", type="Tank",
//                                        elevation=0.0, head=100.0))
//   solver.add_node(rthym_moc.NodeInput(id="J1", type="Junction",
//                                        elevation=50.0, demand=100.0))
//   solver.add_pipe(rthym_moc.PipeInput(id="P1", from_node="R1", to_node="J1",
//                                        length=2000.0, diameter=12.0,
//                                        roughness=130.0, flow_gpm=200.0))
//   results = solver.run(total_time=10.0, dt=0.01)
//
//   import numpy as np
//   time     = np.array(results["time"])
//   head_J1  = np.array(results["node_head"]["J1"])
//   flow_P1  = np.array(results["pipe_flow_gpm"]["P1"])

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/numpy.h>

#include "moc_solver.hpp"

namespace py = pybind11;
using namespace rthym;

// Helper: convert std::vector<double> → 1-D numpy array (zero-copy via capsule)
static py::array_t<double> to_numpy(std::vector<double>&& v) {
    auto* ptr = new std::vector<double>(std::move(v));
    auto capsule = py::capsule(ptr, [](void* p) {
        delete reinterpret_cast<std::vector<double>*>(p);
    });
    return py::array_t<double>(
        {static_cast<py::ssize_t>(ptr->size())},
        {sizeof(double)},
        ptr->data(),
        capsule
    );
}

static py::array_t<int> to_numpy_int(std::vector<int>&& v) {
    auto* ptr = new std::vector<int>(std::move(v));
    auto capsule = py::capsule(ptr, [](void* p) {
        delete reinterpret_cast<std::vector<int>*>(p);
    });
    return py::array_t<int>(
        {static_cast<py::ssize_t>(ptr->size())},
        {sizeof(int)},
        ptr->data(),
        capsule
    );
}

// Convert SimResults → Python dict of numpy arrays
static py::dict results_to_dict(SimResults&& r) {
    py::dict out;

    // time vector
    out["time"] = to_numpy(std::move(r.time));

    // node_head dict
    py::dict nh;
    for (auto& [k, v] : r.node_head) nh[k.c_str()] = to_numpy(std::move(v));
    out["node_head"] = nh;

    // node_pressure dict
    py::dict np_;
    for (auto& [k, v] : r.node_pressure) np_[k.c_str()] = to_numpy(std::move(v));
    out["node_pressure"] = np_;

    // node_cavitation dict
    py::dict nc;
    for (auto& [k, v] : r.node_cavitation) nc[k.c_str()] = to_numpy_int(std::move(v));
    out["node_cavitation"] = nc;

    // pipe_flow_gpm dict
    py::dict pf;
    for (auto& [k, v] : r.pipe_flow_gpm) pf[k.c_str()] = to_numpy(std::move(v));
    out["pipe_flow_gpm"] = pf;

    // valve_position dict
    py::dict vp;
    for (auto& [k, v] : r.valve_position) vp[k.c_str()] = to_numpy(std::move(v));
    out["valve_position"] = vp;

    // valve_velocity dict
    py::dict vv;
    for (auto& [k, v] : r.valve_velocity) vv[k.c_str()] = to_numpy(std::move(v));
    out["valve_velocity"] = vv;

    return out;
}

PYBIND11_MODULE(_rthym_moc, m) {
    m.doc() = R"pbdoc(
        rthym_moc – High-performance 1-D Method of Characteristics transient
        hydraulic solver.  C++ core with Python bindings via PyBind11.

        Units on all API boundaries:
          Lengths / heads  : ft
          Pressures        : psi
          Flows            : GPM
          Wave speed       : ft/s
          Time             : s
    )pbdoc";

    // ── NodeInput ──────────────────────────────────────────────────────────
    py::class_<NodeInput>(m, "NodeInput",
        R"pbdoc(
        Describes one node (junction, reservoir, valve, pump, surge tank, etc.).

        Parameters
        ----------
        id : str
        type : str
            One of: "Junction", "Tank", "PressureBoundary",
                "AirValve", "CheckValve",
                    "Valve", "Turbine", "Pump",
                    "Standpipe" (open surge tank — R-THYM SurgeControl),
                    "HydropneumaticTank" (closed pressurized vessel — R-THYM SurgeTank),
                    "InflowNode", "OutflowNode"
        elevation : float, ft
        head : float, ft
            For Tank/PressureBoundary: HGL.
                        For Standpipe: initial water-surface elevation (ft HGL).
            For HydropneumaticTank: steady-state pipeline head at the
              connection point (used to compute the initial gas constant).
        level : float, %
            Tank fill level 0–100. Retained for compatibility; when both are
            present, ``head`` is treated as the authoritative tank HGL.
        max_level : float, ft
            Tank depth at 100% full. Used with ``level`` only to derive a
            display/compatibility value; imported steady-state initialisation
            uses ``head`` directly.
        demand : float, GPM
        current_speed : float, %   (Pump)
        current_setting : float, % open   (Valve / Turbine)
        design_head : float, ft   (Pump BEP head)
        design_flow : float, GPM  (Pump BEP flow)
        diameter : float, inches
            Valve/Turbine: orifice diameter.
            HydropneumaticTank: connection orifice diameter.
            AirValve: large-orifice air-admission diameter.
        air_release_head : float, ft
            AirValve: gauge head offset applied to the vent reference.
            Default 0.0, so the vent references atmosphere at the node elevation.
        air_release_diameter : float, inches
            AirValve: small-orifice air-release diameter used during repressurisation.
        design_velocity : float, ft/s  (Turbine; computed from design_flow if 0)
        tank_area : float, ft²  (Standpipe cross-sectional area)
        gas_volume : float, ft³
            HydropneumaticTank: initial trapped gas volume. Default 10.
            AirValve: initial trapped air-pocket volume inside the valve body.
        tank_volume : float, ft³
            HydropneumaticTank: total vessel volume (gas + water). Default 30.
            AirValve: maximum local air-pocket chamber volume.
        polytropic_n : float
            HydropneumaticTank: polytropic exponent (1.0=isothermal, 1.4=adiabatic).
            Default 1.2 (typical for air-charged vessels).
        loss_coeff_in : float
            HydropneumaticTank: orifice discharge coefficient C_d for inflow
            (water entering the tank, gas compresses). Default 0.7.
            AirValve: large-orifice admission discharge coefficient.
        loss_coeff_out : float
            HydropneumaticTank: orifice discharge coefficient C_d for outflow
            (water leaving the tank, gas expands). Default 0.7.
            AirValve: small-orifice release discharge coefficient.
        )pbdoc")
        .def(py::init<>())
        .def_readwrite("id",               &NodeInput::id)
        // type is exposed as string property (converts to/from NodeType enum)
        .def_property("type",
            [](const NodeInput& self) { return nodeTypeToStr(self.type); },
            [](NodeInput& self, const std::string& s) {
                const auto parsed = parseNodeType(s);
                if (parsed == NodeType::Junction && s != "Junction") {
                    throw py::value_error("Unknown node type: " + s);
                }
                self.type = parsed;
            })
        .def_readwrite("elevation",        &NodeInput::elevation)
        .def_readwrite("head",             &NodeInput::head)
        .def_readwrite("level",            &NodeInput::level)
        .def_readwrite("max_level",        &NodeInput::max_level)
        .def_readwrite("demand",           &NodeInput::demand)
        .def_readwrite("current_speed",    &NodeInput::current_speed)
        .def_readwrite("current_setting",  &NodeInput::current_setting)
        .def_readwrite("design_head",      &NodeInput::design_head)
        .def_readwrite("design_flow",      &NodeInput::design_flow)
        .def_readwrite("diameter",         &NodeInput::diameter)
        .def_readwrite("air_release_head", &NodeInput::air_release_head)
        .def_readwrite("air_release_diameter", &NodeInput::air_release_diameter)
        .def_readwrite("design_velocity",  &NodeInput::design_velocity)
        .def_readwrite("tank_area",        &NodeInput::tank_area)
        // Hydropneumatic tank fields
        .def_readwrite("gas_volume",       &NodeInput::gas_volume)
        .def_readwrite("tank_volume",      &NodeInput::tank_volume)
        .def_readwrite("polytropic_n",     &NodeInput::polytropic_n)
        .def_readwrite("loss_coeff_in",    &NodeInput::loss_coeff_in)
        .def_readwrite("loss_coeff_out",   &NodeInput::loss_coeff_out)
        // CheckValve closure dynamics
        .def_readwrite("closure_time",     &NodeInput::closure_time)
        .def_readwrite("closure_damping",  &NodeInput::closure_damping)
        .def_readwrite("flipped",          &NodeInput::flipped);

    // ── PipeInput ──────────────────────────────────────────────────────────
    py::class_<PipeInput>(m, "PipeInput",
        R"pbdoc(
        Describes one pipe segment.

        Parameters
        ----------
        id : str
        from_node : str   upstream node id
        to_node : str     downstream node id
        length : float, ft
        diameter : float, inches
        roughness : float   Hazen-Williams C (default 120)
        minor_loss : float
            Dimensionless local-loss coefficient K distributed across the pipe.
        flow_gpm : float, GPM   initial steady-state flow (+ = from→to)
        wall_thickness : float, inches   (for elastic wave speed; default 0.25)
        youngs_modulus : float, psi      (0 = rigid pipe → default 4000 ft/s)
        poissons_ratio : float           (default 0.3)
        )pbdoc")
        .def(py::init<>())
        .def_readwrite("id",             &PipeInput::id)
        .def_readwrite("from_node",      &PipeInput::from_node)
        .def_readwrite("to_node",        &PipeInput::to_node)
        .def_readwrite("length",         &PipeInput::length)
        .def_readwrite("diameter",       &PipeInput::diameter)
        .def_readwrite("roughness",      &PipeInput::roughness)
        .def_readwrite("minor_loss",     &PipeInput::minor_loss)
        .def_readwrite("flow_gpm",       &PipeInput::flow_gpm)
        .def_readwrite("wall_thickness", &PipeInput::wall_thickness)
        .def_readwrite("youngs_modulus", &PipeInput::youngs_modulus)
        .def_readwrite("poissons_ratio", &PipeInput::poissons_ratio);

    // ── ControlType Enum ───────────────────────────────────────────────────
    py::enum_<ControlType>(m, "ControlType")
        .value("Threshold", ControlType::Threshold)
        .value("Deadband", ControlType::Deadband)
        .value("PID", ControlType::PID)
        .value("PCV", ControlType::PCV)
        .export_values();

    // ── ControlRuleInput ───────────────────────────────────────────────────
    py::class_<ControlRuleInput>(m, "ControlRuleInput")
        .def(py::init<>())
        .def_readwrite("id", &ControlRuleInput::id)
        .def_readwrite("type", &ControlRuleInput::type)
        .def_readwrite("monitored_node", &ControlRuleInput::monitored_node)
        .def_readwrite("controlled_node", &ControlRuleInput::controlled_node)
        .def_readwrite("monitored_quantity", &ControlRuleInput::monitored_quantity)
        .def_readwrite("monitored_pipe", &ControlRuleInput::monitored_pipe)
        .def_readwrite("condition", &ControlRuleInput::condition)
        .def_readwrite("threshold", &ControlRuleInput::threshold)
        .def_readwrite("target", &ControlRuleInput::target)
        .def_readwrite("deadband", &ControlRuleInput::deadband)
        .def_readwrite("action", &ControlRuleInput::action)
        .def_readwrite("kp", &ControlRuleInput::kp)
        .def_readwrite("ki", &ControlRuleInput::ki)
        .def_readwrite("kd", &ControlRuleInput::kd);

    // ── MOCSolver ──────────────────────────────────────────────────────────
    py::class_<MOCSolver>(m, "MOCSolver",
        R"pbdoc(
        1-D Method of Characteristics (MOC) transient hydraulic solver.

        Workflow
        --------
        1. Build the network topology by calling add_node() and add_pipe().
        2. Call run() to execute the full transient simulation.
        3. Inspect the returned dict of numpy arrays.

        For scripted transients (e.g. valve closure), call run() with a short
        total_time, then update settings via set_valve_setting() / set_pump_speed(),
        then call run() again.  The solver state persists between calls.

        Note: run() calls initGrid() internally each time, which resets the MOC
        grid from the steady-state initial conditions provided in the node/pipe
        inputs.  To continue from a prior transient state, use the step-based API
        (not yet exposed – extend stepMOC() binding as needed).
        )pbdoc")
        .def(py::init<>())
        .def("add_node", &MOCSolver::add_node,
            py::arg("node"),
            "Append a node to the network topology.")
        .def("add_pipe", &MOCSolver::add_pipe,
            py::arg("pipe"),
            "Append a pipe to the network topology.")
        .def("clear", &MOCSolver::clear,
            "Remove all nodes and pipes from the solver.")
        .def("add_control_rule", &MOCSolver::add_control_rule,
            py::arg("rule"),
            "Register an operational control rule.")
        .def("clear_control_rules", &MOCSolver::clear_control_rules,
            "Clear all registered operational control rules.")
        .def("get_node_head", &MOCSolver::get_node_head,
            py::arg("id"),
            "Query the current piezometric HGL head (ft) of a node.")
        .def("get_node_pressure", &MOCSolver::get_node_pressure,
            py::arg("id"),
            "Query the current gauge pressure (psi) of a node.")
        .def("set_valve_setting", &MOCSolver::set_valve_setting,
            py::arg("id"), py::arg("pct_open"),
            "Update a valve's opening (0=closed, 100=fully open) mid-simulation.")
        .def("set_pump_speed", &MOCSolver::set_pump_speed,
            py::arg("id"), py::arg("pct_speed"),
            "Update a pump's speed (0=off, 100=rated speed) mid-simulation.")
        .def("set_node_demand", &MOCSolver::set_node_demand,
            py::arg("id"), py::arg("demand_gpm"),
            "Update a junction demand mid-simulation.")
        .def("set_node_head", &MOCSolver::set_node_head,
            py::arg("id"), py::arg("head_ft"),
            "Update a fixed-head boundary node's stored head between runs.")
        .def("set_valve_schedule",
            [](MOCSolver& self,
               const std::string& id,
               const std::vector<std::pair<double,double>>& schedule) {
                self.set_valve_schedule(id, schedule);
            },
            py::arg("id"), py::arg("schedule"),
            R"pbdoc(
            Register a time-varying opening schedule for a Valve node.

            Parameters
            ----------
            id : str
                Valve node id (must already be added via add_node).
            schedule : list[tuple[float, float]]
                List of (time_s, pct_open) pairs in ascending time order.
                pct_open is 0 (closed) … 100 (fully open).
                Values are linearly interpolated during run().
                Outside the schedule range the nearest endpoint value is held.

            Examples
            --------
            # Linear closure from 100 % to 0 % over 3 seconds
            solver.set_valve_schedule("V1",
                [(t, max(0.0, 100.0 - 100.0/3.0 * t))
                 for t in [i * 0.01 for i in range(301)]])
            )pbdoc")
        .def("set_pump_schedule",
            [](MOCSolver& self,
               const std::string& id,
               const std::vector<std::pair<double,double>>& schedule) {
                self.set_pump_schedule(id, schedule);
            },
            py::arg("id"), py::arg("schedule"),
            R"pbdoc(
            Register a time-varying speed schedule for a Pump node.

            Parameters
            ----------
            id : str
                Pump node id (must already be added via add_node).
            schedule : list[tuple[float, float]]
                List of (time_s, pct_speed) pairs in ascending time order.
                pct_speed is 0 (off) … 100 (rated speed).
                Values are linearly interpolated during run().
                Outside the schedule range the nearest endpoint value is held.
            )pbdoc")
        .def("set_demand_schedule",
            [](MOCSolver& self,
               const std::string& id,
               const std::vector<std::pair<double,double>>& schedule) {
                self.set_demand_schedule(id, schedule);
            },
            py::arg("id"), py::arg("schedule"),
            R"pbdoc(
            Register a time-varying demand schedule for a Junction-like node.

            Parameters
            ----------
            id : str
                Node id (typically Junction, OutflowNode, or InflowNode).
            schedule : list[tuple[float, float]]
                List of (time_s, demand_gpm) pairs in ascending time order.
                Values are linearly interpolated during run().
            )pbdoc")
        .def("set_head_schedule",
            [](MOCSolver& self,
               const std::string& id,
               const std::vector<std::pair<double,double>>& schedule) {
                self.set_head_schedule(id, schedule);
            },
            py::arg("id"), py::arg("schedule"),
            R"pbdoc(
            Register a time-varying head schedule for a fixed-head node.

            Parameters
            ----------
            id : str
                Node id (typically PressureBoundary or Tank).
            schedule : list[tuple[float, float]]
                List of (time_s, head_ft) pairs in ascending time order.
                Values are linearly interpolated during run().
            )pbdoc")
        .def("run",
            [](MOCSolver& self,
               double total_time,
               double dt,
               double p_vapor_psi,
               double usf_tau,
               double k_bru) -> py::dict {
                return results_to_dict(
                    self.run(total_time, dt, p_vapor_psi, usf_tau, k_bru));
            },
            py::arg("total_time"),
            py::arg("dt")          = 0.01,
            py::arg("p_vapor_psi") = -14.0,
            py::arg("usf_tau")     = 0.5,
            py::arg("k_bru")       = -1.0,
            R"pbdoc(
            Run the transient simulation and return results.

            Parameters
            ----------
            total_time : float
                Simulation duration in seconds.
            dt : float
                Time step in seconds (default 0.01 s = 10 ms).
                The Courant condition is enforced automatically by adjusting
                each pipe's wave speed to the nearest integer-segment solution.
            p_vapor_psi : float
                Vapour pressure threshold for cavitation detection (default −14 psi).
            usf_tau : float
                Boundary-layer relaxation time constant τ for the IIR unsteady
                friction filter (default 0.5 s).
            k_bru : float
                Brunone (1991) dimensionless unsteady-friction coefficient.

                **-1 (default)** — Dynamic Vardy-Brown (1996): k_Bru is computed
                automatically each timestep from the instantaneous pipe Reynolds
                number using ``k_Bru = C*/sqrt(π)``, ``C* = 7.41/Re^0.352``.
                This provides physically realistic damping without calibration.

                **0** — Steady friction only (no USF).

                **> 0** — User-supplied static value (calibrated). Typical
                turbulent pipe flow range: 0.02–0.15.

            Returns
            -------
            dict with keys:
              "time"             : numpy.ndarray (num_steps,)  seconds
              "node_head"        : dict[node_id] → numpy.ndarray (num_steps,)  ft
              "node_pressure"    : dict[node_id] → numpy.ndarray (num_steps,)  psi
              "node_cavitation"  : dict[node_id] → numpy.ndarray (num_steps,)  0/1
              "pipe_flow_gpm"    : dict[pipe_id] → numpy.ndarray (num_steps,)  GPM
            )pbdoc");

    // ── Module-level convenience constants ────────────────────────────────
    m.attr("G_FT_S2")    = G_FT_S2;
    m.attr("GPM_TO_CFS") = GPM_TO_CFS;
    m.attr("PSI_TO_FT")  = PSI_TO_FT;
}
