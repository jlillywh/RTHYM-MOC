// test_waterhammer.cpp
// Standalone C++ validation test.  Compile with:
//   g++ -std=c++17 -O2 -I../src test_waterhammer.cpp ../src/moc_solver.cpp -o moc_test && ./moc_test
//
// Validates the classic Joukowsky waterhammer formula using a dead-end
// boundary (Junction with demand=0, no outflow pipe), which represents
// an instantaneously-closed valve at the pipe terminus:
//
//   ΔH = a · V₀ / g
//
// The dead-end Junction forces Q=0 exactly on the first time step, giving
// H_node = C+ = H[N-2] + B·V[N-2] (penultimate-node wave characteristic).
// This is the purest test of the MOC interior + boundary formulation.

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include "moc_solver.hpp"

static const double PASS_THRESHOLD = 0.02; // 2 % relative error

int main() {
    using namespace rthym;

    // ── Network: Reservoir ──── P1 ──── DeadEnd (closed) ─────────────────
    // The dead-end Junction has no outflow pipe.  On the first MOC step the
    // boundary condition forces V=0, creating an exact Joukowsky pressure rise.
    MOCSolver solver;

    NodeInput R1;
    R1.id        = "R1";
    R1.type      = NodeType::PressureBoundary;
    R1.elevation = 0.0;
    R1.head      = 150.0;   // ft  HGL
    solver.add_node(R1);

    NodeInput dead_end;
    dead_end.id        = "DE";
    dead_end.type      = NodeType::Junction;
    dead_end.elevation = 0.0;
    dead_end.demand    = 0.0;   // no demand → dead-end (Q=0 enforced by BC)
    solver.add_node(dead_end);

    PipeInput P1;
    P1.id        = "P1";
    P1.from_node = "R1";
    P1.to_node   = "DE";
    P1.length    = 3000.0;  // ft
    P1.diameter  = 12.0;    // inches
    P1.roughness = 130.0;   // Hazen-Williams C
    P1.flow_gpm  = 500.0;   // initial steady-state flow (GPM)
    solver.add_pipe(P1);

    // ── Run 3 s of transient ──────────────────────────────────────────────
    // Wave travel time R1→DE = 3000/4000 = 0.75 s.
    // First peak at t=dt, steady Joukowsky plateau until reflected wave at 1.5 s.
    const double dt          = 0.01;
    const double total_time  = 3.0;
    auto results = solver.run(total_time, dt, -14.0, 0.5);

    // ── Joukowsky analytical prediction ──────────────────────────────────
    // ΔH = a · V₀ / g  where a is the pipe's Courant-adjusted wave speed.
    // The actual simulated wave speed a_sim = (L/numSegs)/dt.
    // For L=3000, dt=0.01, rigid-pipe default 4000 ft/s: numSegs=75, a_sim=4000.
    const double D_ft   = 12.0 / 12.0;
    const double A_pipe = M_PI_ * (D_ft / 2.0) * (D_ft / 2.0);
    const double Q0_cfs = 500.0 * GPM_TO_CFS;
    const double V0     = Q0_cfs / A_pipe;       // ft/s  initial velocity
    const double a_sim  = 4000.0;                // ft/s  (rigid pipe default)
    const double dH_j   = a_sim * V0 / G_FT_S2; // Joukowsky rise (ft)

    // Baseline head at DE from initial conditions (linear HGL interpolation):
    //   H_DE_initial = H_R1 - Hf_friction ≈ 150 - 2.3 = 147.7 ft
    // But the dead-end BC uses H[N-2] (penultimate) which is one node inward:
    //   Expected peak = H[N-2]_initial + B·V₀ − R·V₀²
    //                ≈ (H_R1 − Hf × (N-2)/(N-1)) + a/g · V₀
    // For approximate comparison we use the reservoir head + ΔH:
    const double H_exp  = 150.0 + dH_j;  // conservative upper bound

    // ── Simulated dead-end head at t=dt (first Joukowsky peak) ───────────
    const auto& H_de  = results.node_head.at("DE");
    const double H_t1 = H_de.at(0);  // first time step

    // ── Report ────────────────────────────────────────────────────────────
    std::printf("==================================================\n");
    std::printf("  Joukowsky Waterhammer Benchmark\n");
    std::printf("==================================================\n");
    std::printf("  Initial velocity V0     : %.4f ft/s\n", V0);
    std::printf("  Simulated wave speed    : %.0f ft/s\n",   a_sim);
    std::printf("  Joukowsky ΔH            : %.2f ft\n",   dH_j);
    std::printf("  Analytical upper bound  : %.2f ft\n",   H_exp);
    std::printf("  Simulated H at t=dt     : %.2f ft\n",   H_t1);
    const double rel_err = std::abs(H_t1 - H_exp) / H_exp;
    std::printf("  Relative error          : %.2f %%\n",  rel_err * 100.0);
    std::printf("==================================================\n");

    if (rel_err > PASS_THRESHOLD) {
        std::fprintf(stderr, "FAIL: relative error %.2f %% exceeds threshold %.0f %%\n",
                     rel_err * 100.0, PASS_THRESHOLD * 100.0);
        return EXIT_FAILURE;
    }

    std::printf("PASS\n");
    return EXIT_SUCCESS;
}
