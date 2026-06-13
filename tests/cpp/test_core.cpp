// Native C++ tests for the pure solver core (no Python, no Emscripten).

#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include "moc_solver.hpp"

using namespace rthym;

namespace {

NodeInput make_pressure_boundary(const char* id, double head_ft) {
    NodeInput node;
    node.id = id;
    node.type = NodeType::PressureBoundary;
    node.head = head_ft;
    return node;
}

PipeInput make_pipe(const char* id,
                    const char* from_node,
                    const char* to_node,
                    double length_ft,
                    double flow_gpm) {
    PipeInput pipe;
    pipe.id = id;
    pipe.from_node = from_node;
    pipe.to_node = to_node;
    pipe.length = length_ft;
    pipe.diameter = 12.0;
    pipe.roughness = 130.0;
    pipe.flow_gpm = flow_gpm;
    return pipe;
}

MOCSolver make_two_tank_line() {
    MOCSolver solver;
    solver.add_node(make_pressure_boundary("R1", 500.0));
    solver.add_node(make_pressure_boundary("R2", 100.0));
    solver.add_pipe(make_pipe("P1", "R1", "R2", 1000.0, 200.0));
    solver.set_dt(0.01);
    return solver;
}

} // namespace

TEST_CASE("initGrid and stepMOC advance simulation time") {
    MOCSolver solver = make_two_tank_line();
    solver.initGrid();
    solver.stepMOC();
    const StepSnapshot snapshot = solver.capture_step_snapshot();
    CHECK(snapshot.time_s == doctest::Approx(0.01).epsilon(1e-9));
}

TEST_CASE("capture_step_snapshot returns node and link telemetry") {
    MOCSolver solver = make_two_tank_line();
    solver.initGrid();
    solver.stepMOC();
    const StepSnapshot snapshot = solver.capture_step_snapshot();

    REQUIRE(snapshot.nodes.size() == 2);
    REQUIRE(snapshot.links.size() == 1);
    CHECK(snapshot.links[0].id == "P1");
    CHECK(snapshot.links[0].flow_gpm > 0.0);
    CHECK(snapshot.links[0].headloss_ft >= 0.0);

    bool saw_r1 = false;
    for (const auto& node : snapshot.nodes) {
        if (node.id == "R1") {
            saw_r1 = true;
            CHECK(node.type == "PressureBoundary");
            CHECK(node.pressure_psi > 0.0);
        }
    }
    CHECK(saw_r1);
}

TEST_CASE("capture_step_snapshot reports check valve reverse-flow block") {
    MOCSolver solver;
    solver.add_node(make_pressure_boundary("R1", 160.0));
    NodeInput cv = make_pressure_boundary("CV1", 150.0);
    cv.type = NodeType::CheckValve;
    cv.diameter = 12.0;
    solver.add_node(cv);
    solver.add_node(make_pressure_boundary("R2", 260.0));
    solver.add_pipe(make_pipe("P1", "R1", "CV1", 40.0, 500.0));
    solver.add_pipe(make_pipe("P2", "CV1", "R2", 40.0, 500.0));
    solver.set_dt(0.01);
    solver.initGrid();
    for (int i = 0; i < 50; ++i) {
        solver.stepMOC();
    }

    const StepSnapshot snapshot = solver.capture_step_snapshot();
    const NodeStepSnapshot* cv_snap = nullptr;
    for (const auto& node : snapshot.nodes) {
        if (node.id == "CV1") {
            cv_snap = &node;
            break;
        }
    }
    REQUIRE(cv_snap != nullptr);
    CHECK(cv_snap->type == "CheckValve");
    CHECK(cv_snap->reverse_flow_blocked);
    CHECK(cv_snap->downstream_head_ft > cv_snap->upstream_head_ft);
}

TEST_CASE("get_grid_report previews Courant adjustment without time integration") {
    MOCSolver solver = make_two_tank_line();
    const GridReport report = solver.get_grid_report(0.01);

    REQUIRE(report.pipe_num_segments.count("P1") == 1);
    CHECK(report.dt_s == doctest::Approx(0.01).epsilon(1e-9));
    CHECK(report.pipe_num_segments.at("P1") >= 1);
    CHECK(report.pipe_courant_number.at("P1") == doctest::Approx(1.0).epsilon(1e-6));
    CHECK(report.pipe_wave_speed_design_fps.at("P1") > 0.0);
    CHECK(report.pipe_wave_speed_adjusted_fps.at("P1") > 0.0);
    CHECK(report.distortion_limit_exceeded == false);
}
