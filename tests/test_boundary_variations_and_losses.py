"""Boundary-condition, unsteady-friction, and local-loss regressions.

These tests cover a set of basic but important transient controls:

- sudden junction-demand changes within a single run
- sudden fixed-head boundary changes representing reservoir / pressure-boundary steps
- the effect of enabling an unsteady-friction correction versus steady friction only
- the effect of stronger local loss at a throttled valve
"""

import numpy as np

import rthym_moc as m

DT_S = 0.01
DEMAND_TOTAL_TIME_S = 10.0
HEAD_TOTAL_TIME_S = 10.0
LOSS_TOTAL_TIME_S = 2.0
USF_TOTAL_TIME_S = 8.0
TURBINE_TOTAL_TIME_S = 8.0


def _make_node(node_id, node_type, **kwargs):
    node = m.NodeInput()
    node.id = node_id
    node.type = node_type
    for key, value in kwargs.items():
        setattr(node, key, value)
    return node


def _make_pipe(pipe_id, from_node, to_node, length_ft, flow_gpm, diameter_in=12.0):
    pipe = m.PipeInput()
    pipe.id = pipe_id
    pipe.from_node = from_node
    pipe.to_node = to_node
    pipe.length = length_ft
    pipe.flow_gpm = flow_gpm
    pipe.diameter = diameter_in
    pipe.roughness = 130.0
    return pipe


def _mean_over_window(time_s, values, start_s, end_s):
    mask = (time_s >= start_s) & (time_s <= end_s)
    assert np.any(mask), f"No samples found in window [{start_s}, {end_s}] s"
    return float(np.asarray(values)[mask].mean())


def _run_demand_step_case():
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=150.0))
    solver.add_node(_make_node("J1", "Junction", head=145.0, demand=500.0))
    solver.add_pipe(_make_pipe("P1", "R1", "J1", 3000.0, 500.0))
    solver.set_demand_schedule(
        "J1",
        [
            (0.0, 500.0),
            (4.99, 500.0),
            (5.0, 700.0),
            (DEMAND_TOTAL_TIME_S, 700.0),
        ],
    )
    return solver.run(total_time=DEMAND_TOTAL_TIME_S, dt=DT_S)


def _run_boundary_head_step_case():
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=150.0))
    solver.add_node(_make_node("R2", "PressureBoundary", head=145.0))
    solver.add_pipe(_make_pipe("P1", "R1", "R2", 3000.0, 500.0))
    solver.set_head_schedule(
        "R2",
        [
            (0.0, 145.0),
            (4.99, 145.0),
            (5.0, 130.0),
            (HEAD_TOTAL_TIME_S, 130.0),
        ],
    )
    return solver.run(total_time=HEAD_TOTAL_TIME_S, dt=DT_S)


def _run_usf_case(k_bru, usf_tau):
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=150.0))
    solver.add_node(_make_node("V1", "Valve", diameter=12.0, current_setting=100.0, head=148.0))
    solver.add_node(_make_node("R2", "PressureBoundary", head=147.9))
    solver.add_pipe(_make_pipe("P1", "R1", "V1", 3000.0, 500.0))
    solver.add_pipe(_make_pipe("P2", "V1", "R2", 40.0, 500.0))
    solver.set_valve_schedule(
        "V1",
        [
            (0.0, 100.0),
            (0.09, 100.0),
            (0.1, 0.0),
            (USF_TOTAL_TIME_S, 0.0),
        ],
    )
    return solver.run(total_time=USF_TOTAL_TIME_S, dt=DT_S, p_vapor_psi=-14.0, usf_tau=usf_tau, k_bru=k_bru)


def _run_valve_loss_case(setting_pct):
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=150.0))
    solver.add_node(_make_node("V1", "Valve", diameter=12.0, current_setting=setting_pct, head=148.0))
    solver.add_node(_make_node("R2", "PressureBoundary", head=120.0))
    solver.add_pipe(_make_pipe("P1", "R1", "V1", 1000.0, 800.0))
    solver.add_pipe(_make_pipe("P2", "V1", "R2", 100.0, 800.0))
    return solver.run(total_time=LOSS_TOTAL_TIME_S, dt=DT_S)


def _run_persisted_demand_case():
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=150.0))
    solver.add_node(_make_node("J1", "Junction", head=145.0, demand=500.0))
    solver.add_pipe(_make_pipe("P1", "R1", "J1", 3000.0, 500.0))

    baseline = solver.run(total_time=LOSS_TOTAL_TIME_S, dt=DT_S)
    solver.set_node_demand("J1", 700.0)
    updated = solver.run(total_time=LOSS_TOTAL_TIME_S, dt=DT_S)
    return baseline, updated


def _run_persisted_valve_case():
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=150.0))
    solver.add_node(_make_node("V1", "Valve", diameter=12.0, current_setting=100.0, head=148.0))
    solver.add_node(_make_node("R2", "PressureBoundary", head=120.0))
    solver.add_pipe(_make_pipe("P1", "R1", "V1", 1000.0, 800.0))
    solver.add_pipe(_make_pipe("P2", "V1", "R2", 100.0, 800.0))

    baseline = solver.run(total_time=LOSS_TOTAL_TIME_S, dt=DT_S)
    solver.set_valve_setting("V1", 5.0)
    updated = solver.run(total_time=LOSS_TOTAL_TIME_S, dt=DT_S)
    return baseline, updated


def _run_persisted_pump_case():
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=120.0))
    solver.add_node(_make_node("Pump1", "Pump", head=140.0, design_head=60.0, design_flow=800.0, current_speed=100.0))
    solver.add_node(_make_node("R2", "PressureBoundary", head=150.0))
    solver.add_pipe(_make_pipe("P1", "R1", "Pump1", 1000.0, 800.0))
    solver.add_pipe(_make_pipe("P2", "Pump1", "R2", 1000.0, 800.0))

    baseline = solver.run(total_time=LOSS_TOTAL_TIME_S, dt=DT_S)
    solver.set_pump_speed("Pump1", 0.0)
    updated = solver.run(total_time=LOSS_TOTAL_TIME_S, dt=DT_S)
    return baseline, updated


def _run_inflow_node_case():
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=120.0))
    solver.add_node(_make_node("I1", "InflowNode", head=110.0, demand=0.0))
    solver.add_node(_make_node("R2", "PressureBoundary", head=100.0))
    solver.add_pipe(_make_pipe("P1", "R1", "I1", 1200.0, 200.0))
    solver.add_pipe(_make_pipe("P2", "I1", "R2", 1200.0, 200.0))

    baseline = solver.run(total_time=LOSS_TOTAL_TIME_S, dt=DT_S)
    solver.set_node_demand("I1", 400.0)
    updated = solver.run(total_time=LOSS_TOTAL_TIME_S, dt=DT_S)
    return baseline, updated


def _run_outflow_node_case():
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=120.0))
    solver.add_node(_make_node("O1", "OutflowNode", head=110.0, demand=0.0))
    solver.add_node(_make_node("R2", "PressureBoundary", head=100.0))
    solver.add_pipe(_make_pipe("P1", "R1", "O1", 1200.0, 200.0))
    solver.add_pipe(_make_pipe("P2", "O1", "R2", 1200.0, 200.0))

    baseline = solver.run(total_time=LOSS_TOTAL_TIME_S, dt=DT_S)
    solver.set_node_demand("O1", 400.0)
    updated = solver.run(total_time=LOSS_TOTAL_TIME_S, dt=DT_S)
    return baseline, updated


def _run_tank_head_step_case():
    solver = m.MOCSolver()
    solver.add_node(_make_node("T1", "Tank", head=160.0))
    solver.add_node(_make_node("J1", "Junction", head=150.0, demand=500.0))
    solver.add_pipe(_make_pipe("P1", "T1", "J1", 3000.0, 500.0))
    solver.set_head_schedule(
        "T1",
        [
            (0.0, 160.0),
            (1.99, 160.0),
            (2.0, 140.0),
            (HEAD_TOTAL_TIME_S, 140.0),
        ],
    )
    return solver.run(total_time=HEAD_TOTAL_TIME_S, dt=DT_S)


def _run_persisted_head_case():
    solver = m.MOCSolver()
    solver.add_node(_make_node("T1", "Tank", head=160.0))
    solver.add_node(_make_node("J1", "Junction", head=150.0, demand=500.0))
    solver.add_pipe(_make_pipe("P1", "T1", "J1", 3000.0, 500.0))

    baseline = solver.run(total_time=HEAD_TOTAL_TIME_S, dt=DT_S)
    solver.set_node_head("T1", 140.0)
    updated = solver.run(total_time=HEAD_TOTAL_TIME_S, dt=DT_S)
    return baseline, updated


def _run_clear_case():
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=150.0))
    solver.add_node(_make_node("J1", "Junction", head=145.0, demand=500.0))
    solver.add_pipe(_make_pipe("P1", "R1", "J1", 3000.0, 500.0))
    solver.set_demand_schedule(
        "J1",
        [
            (0.0, 500.0),
            (1.0, 700.0),
            (LOSS_TOTAL_TIME_S, 700.0),
        ],
    )

    solver.clear()
    return solver.run(total_time=LOSS_TOTAL_TIME_S, dt=DT_S)


def _run_turbine_case(setting_pct):
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=220.0))
    solver.add_node(
        _make_node(
            "T1",
            "Turbine",
            diameter=24.0,
            current_setting=setting_pct,
            design_head=120.0,
            design_flow=4000.0,
            head=180.0,
        )
    )
    solver.add_node(_make_node("R2", "PressureBoundary", head=120.0))
    solver.add_pipe(_make_pipe("P1", "R1", "T1", 4000.0, 4000.0, diameter_in=24.0))
    solver.add_pipe(_make_pipe("P2", "T1", "R2", 500.0, 4000.0, diameter_in=24.0))
    return solver.run(total_time=LOSS_TOTAL_TIME_S, dt=DT_S)


def _run_turbine_shutdown_case(schedule):
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=220.0))
    solver.add_node(
        _make_node(
            "T1",
            "Turbine",
            diameter=24.0,
            current_setting=100.0,
            design_head=120.0,
            design_flow=4000.0,
            head=180.0,
        )
    )
    solver.add_node(_make_node("R2", "PressureBoundary", head=120.0))
    solver.add_pipe(_make_pipe("P1", "R1", "T1", 4000.0, 4000.0, diameter_in=24.0))
    solver.add_pipe(_make_pipe("P2", "T1", "R2", 500.0, 4000.0, diameter_in=24.0))
    solver.set_valve_schedule("T1", schedule)
    return solver.run(total_time=TURBINE_TOTAL_TIME_S, dt=DT_S)


def _run_turbine_startup_case(schedule):
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=220.0))
    solver.add_node(
        _make_node(
            "T1",
            "Turbine",
            diameter=24.0,
            current_setting=10.0,
            design_head=120.0,
            design_flow=4000.0,
            head=180.0,
        )
    )
    solver.add_node(_make_node("R2", "PressureBoundary", head=120.0))
    solver.add_pipe(_make_pipe("P1", "R1", "T1", 4000.0, 4000.0, diameter_in=24.0))
    solver.add_pipe(_make_pipe("P2", "T1", "R2", 500.0, 4000.0, diameter_in=24.0))
    solver.set_valve_schedule("T1", schedule)
    return solver.run(total_time=TURBINE_TOTAL_TIME_S, dt=DT_S)


def test_demand_step_increases_flow_and_drops_junction_head():
    """A sudden demand increase should pull down the junction head and increase inflow."""
    data = _run_demand_step_case()
    time_s = np.asarray(data["time"])
    pre_head_ft = _mean_over_window(time_s, data["node_head"]["J1"], 1.0, 4.0)
    post_head_ft = _mean_over_window(time_s, data["node_head"]["J1"], 5.2, 6.0)
    pre_flow_gpm = _mean_over_window(time_s, data["pipe_flow_gpm"]["P1"], 1.0, 4.0)
    post_flow_gpm = _mean_over_window(time_s, data["pipe_flow_gpm"]["P1"], 5.2, 6.0)

    assert pre_head_ft - post_head_ft >= 100.0, (
        f"Expected the demand step to drop J1 head by at least 100 ft, got {pre_head_ft - post_head_ft:.2f} ft"
    )
    assert post_flow_gpm - pre_flow_gpm >= 80.0, (
        f"Expected the demand step to increase inflow by at least 80 GPM, got {post_flow_gpm - pre_flow_gpm:.2f} GPM"
    )


def test_fixed_head_step_updates_boundary_head_and_increases_pipe_flow():
    """A sudden fixed-head change should be honored directly and alter the through-flow."""
    data = _run_boundary_head_step_case()
    time_s = np.asarray(data["time"])
    pre_downstream_head_ft = _mean_over_window(time_s, data["node_head"]["R2"], 1.0, 4.0)
    post_downstream_head_ft = _mean_over_window(time_s, data["node_head"]["R2"], 5.2, 6.0)
    pre_flow_gpm = _mean_over_window(time_s, data["pipe_flow_gpm"]["P1"], 1.0, 4.0)
    post_flow_gpm = _mean_over_window(time_s, data["pipe_flow_gpm"]["P1"], 5.2, 6.0)

    assert abs(pre_downstream_head_ft - 145.0) <= 0.5, (
        f"Expected the scheduled pre-step boundary head to stay near 145 ft, got {pre_downstream_head_ft:.2f} ft"
    )
    assert abs(post_downstream_head_ft - 130.0) <= 0.5, (
        f"Expected the scheduled post-step boundary head to stay near 130 ft, got {post_downstream_head_ft:.2f} ft"
    )
    assert post_flow_gpm - pre_flow_gpm >= 15.0, (
        f"Expected the downstream head drop to increase pipe flow by at least 15 GPM, got {post_flow_gpm - pre_flow_gpm:.2f} GPM"
    )


def test_unsteady_friction_changes_late_time_oscillation_damping():
    """Turning on a static Brunone term should materially change the late oscillation envelope."""
    steady = _run_usf_case(k_bru=0.0, usf_tau=DT_S)
    unsteady = _run_usf_case(k_bru=0.02, usf_tau=0.5)
    time_s = np.asarray(steady["time"])
    steady_head_ft = np.asarray(steady["node_head"]["V1"])
    unsteady_head_ft = np.asarray(unsteady["node_head"]["V1"])

    steady_late_abs_ft = float(np.mean(np.abs(steady_head_ft[(time_s >= 4.0) & (time_s <= 6.0)] - 150.0)))
    unsteady_late_abs_ft = float(np.mean(np.abs(unsteady_head_ft[(time_s >= 4.0) & (time_s <= 6.0)] - 150.0)))

    assert steady_late_abs_ft - unsteady_late_abs_ft >= 80.0, (
        f"Expected the unsteady-friction model to change the late oscillation envelope by at least 80 ft, got {steady_late_abs_ft - unsteady_late_abs_ft:.2f} ft"
    )


def test_stronger_valve_local_loss_reduces_flow_and_raises_upstream_head():
    """A more throttled valve should impose a stronger local loss at the same boundaries."""
    open_case = _run_valve_loss_case(setting_pct=100.0)
    throttled_case = _run_valve_loss_case(setting_pct=5.0)
    time_s = np.asarray(open_case["time"])
    open_flow_gpm = _mean_over_window(time_s, open_case["pipe_flow_gpm"]["P1"], 0.5, 1.5)
    throttled_flow_gpm = _mean_over_window(time_s, throttled_case["pipe_flow_gpm"]["P1"], 0.5, 1.5)
    open_valve_head_ft = _mean_over_window(time_s, open_case["node_head"]["V1"], 0.5, 1.5)
    throttled_valve_head_ft = _mean_over_window(time_s, throttled_case["node_head"]["V1"], 0.5, 1.5)

    assert open_flow_gpm - throttled_flow_gpm >= 100.0, (
        f"Expected the stronger valve loss to reduce steady flow by at least 100 GPM, got {open_flow_gpm - throttled_flow_gpm:.2f} GPM"
    )
    assert throttled_valve_head_ft - open_valve_head_ft >= 20.0, (
        f"Expected the stronger valve loss to raise upstream valve-node head by at least 20 ft, got {throttled_valve_head_ft - open_valve_head_ft:.2f} ft"
    )


def test_set_node_demand_persists_across_separate_run_calls():
    """set_node_demand() should update the stored initial condition used by the next run()."""
    baseline, updated = _run_persisted_demand_case()
    time_s = np.asarray(baseline["time"])

    baseline_flow_gpm = _mean_over_window(time_s, baseline["pipe_flow_gpm"]["P1"], 0.5, 1.5)
    updated_flow_gpm = _mean_over_window(time_s, updated["pipe_flow_gpm"]["P1"], 0.5, 1.5)
    baseline_head_ft = _mean_over_window(time_s, baseline["node_head"]["J1"], 0.5, 1.5)
    updated_head_ft = _mean_over_window(time_s, updated["node_head"]["J1"], 0.5, 1.5)

    assert updated_flow_gpm - baseline_flow_gpm >= 120.0, (
        f"Expected set_node_demand() to increase the next run's inflow by at least 120 GPM, got {updated_flow_gpm - baseline_flow_gpm:.2f} GPM"
    )
    assert baseline_head_ft - updated_head_ft >= 100.0, (
        f"Expected set_node_demand() to lower the next run's junction head by at least 100 ft, got {baseline_head_ft - updated_head_ft:.2f} ft"
    )


def test_set_node_head_persists_across_separate_run_calls():
    """set_node_head() should update the stored initial condition used by the next run()."""
    baseline, updated = _run_persisted_head_case()
    time_s = np.asarray(baseline["time"])

    baseline_head_ft = _mean_over_window(time_s, baseline["node_head"]["J1"], 0.5, 1.5)
    updated_head_ft = _mean_over_window(time_s, updated["node_head"]["J1"], 0.5, 1.5)
    baseline_tank_head_ft = _mean_over_window(time_s, baseline["node_head"]["T1"], 0.5, 1.5)
    updated_tank_head_ft = _mean_over_window(time_s, updated["node_head"]["T1"], 0.5, 1.5)

    assert baseline_tank_head_ft - updated_tank_head_ft >= 19.0, (
        f"Expected set_node_head() to lower the next run's tank head by about 20 ft, got {baseline_tank_head_ft - updated_tank_head_ft:.2f} ft"
    )
    assert baseline_head_ft - updated_head_ft >= 15.0, (
        f"Expected set_node_head() to lower the next run's junction head by at least 15 ft, got {baseline_head_ft - updated_head_ft:.2f} ft"
    )


def test_set_valve_setting_persists_across_separate_run_calls():
    """set_valve_setting() should update the stored initial condition used by the next run()."""
    baseline, updated = _run_persisted_valve_case()
    time_s = np.asarray(baseline["time"])

    baseline_flow_gpm = _mean_over_window(time_s, baseline["pipe_flow_gpm"]["P1"], 0.5, 1.5)
    updated_flow_gpm = _mean_over_window(time_s, updated["pipe_flow_gpm"]["P1"], 0.5, 1.5)
    baseline_head_ft = _mean_over_window(time_s, baseline["node_head"]["V1"], 0.5, 1.5)
    updated_head_ft = _mean_over_window(time_s, updated["node_head"]["V1"], 0.5, 1.5)

    assert baseline_flow_gpm - updated_flow_gpm >= 100.0, (
        f"Expected set_valve_setting() to reduce the next run's through-flow by at least 100 GPM, got {baseline_flow_gpm - updated_flow_gpm:.2f} GPM"
    )
    assert updated_head_ft - baseline_head_ft >= 20.0, (
        f"Expected set_valve_setting() to raise the next run's upstream valve head by at least 20 ft, got {updated_head_ft - baseline_head_ft:.2f} ft"
    )


def test_set_pump_speed_persists_across_separate_run_calls():
    """set_pump_speed() should update the stored initial condition used by the next run()."""
    baseline, updated = _run_persisted_pump_case()
    time_s = np.asarray(baseline["time"])

    baseline_flow_gpm = _mean_over_window(time_s, baseline["pipe_flow_gpm"]["P2"], 0.5, 1.5)
    updated_flow_gpm = _mean_over_window(time_s, updated["pipe_flow_gpm"]["P2"], 0.5, 1.5)
    baseline_head_ft = _mean_over_window(time_s, baseline["node_head"]["Pump1"], 0.5, 1.5)
    updated_head_ft = _mean_over_window(time_s, updated["node_head"]["Pump1"], 0.5, 1.5)

    assert baseline_flow_gpm - updated_flow_gpm >= 100.0, (
        f"Expected set_pump_speed() to cut the next run's discharge flow by at least 100 GPM, got {baseline_flow_gpm - updated_flow_gpm:.2f} GPM"
    )
    assert updated_head_ft - baseline_head_ft >= 30.0, (
        f"Expected setting pump speed to 0 % to materially change the next run's pump-node head, got {updated_head_ft - baseline_head_ft:.2f} ft"
    )


def test_inflow_node_injects_flow_with_reversed_demand_sign():
    """Increasing InflowNode demand should inject water into the network rather than withdraw it."""
    baseline, updated = _run_inflow_node_case()
    time_s = np.asarray(baseline["time"])

    baseline_head_ft = _mean_over_window(time_s, baseline["node_head"]["I1"], 0.5, 1.5)
    updated_head_ft = _mean_over_window(time_s, updated["node_head"]["I1"], 0.5, 1.5)
    baseline_upstream_flow_gpm = _mean_over_window(time_s, baseline["pipe_flow_gpm"]["P1"], 0.5, 1.5)
    updated_upstream_flow_gpm = _mean_over_window(time_s, updated["pipe_flow_gpm"]["P1"], 0.5, 1.5)
    baseline_downstream_flow_gpm = _mean_over_window(time_s, baseline["pipe_flow_gpm"]["P2"], 0.5, 1.5)
    updated_downstream_flow_gpm = _mean_over_window(time_s, updated["pipe_flow_gpm"]["P2"], 0.5, 1.5)

    assert updated_head_ft - baseline_head_ft >= 70.0, (
        f"Expected increasing InflowNode demand to raise the injection-node head by at least 70 ft, got {updated_head_ft - baseline_head_ft:.2f} ft"
    )
    assert baseline_upstream_flow_gpm - updated_upstream_flow_gpm >= 100.0, (
        f"Expected the inflow node injection to reduce upstream supply flow by at least 100 GPM, got {baseline_upstream_flow_gpm - updated_upstream_flow_gpm:.2f} GPM"
    )
    assert updated_downstream_flow_gpm - baseline_downstream_flow_gpm >= 250.0, (
        f"Expected the inflow node injection to increase downstream discharge by at least 250 GPM, got {updated_downstream_flow_gpm - baseline_downstream_flow_gpm:.2f} GPM"
    )


def test_outflow_node_withdraws_flow_with_standard_demand_sign():
    """Increasing OutflowNode demand should withdraw water from the network like a junction sink."""
    baseline, updated = _run_outflow_node_case()
    time_s = np.asarray(baseline["time"])

    baseline_head_ft = _mean_over_window(time_s, baseline["node_head"]["O1"], 0.5, 1.5)
    updated_head_ft = _mean_over_window(time_s, updated["node_head"]["O1"], 0.5, 1.5)
    baseline_upstream_flow_gpm = _mean_over_window(time_s, baseline["pipe_flow_gpm"]["P1"], 0.5, 1.5)
    updated_upstream_flow_gpm = _mean_over_window(time_s, updated["pipe_flow_gpm"]["P1"], 0.5, 1.5)
    baseline_downstream_flow_gpm = _mean_over_window(time_s, baseline["pipe_flow_gpm"]["P2"], 0.5, 1.5)
    updated_downstream_flow_gpm = _mean_over_window(time_s, updated["pipe_flow_gpm"]["P2"], 0.5, 1.5)

    assert baseline_head_ft - updated_head_ft >= 70.0, (
        f"Expected increasing OutflowNode demand to lower the withdrawal-node head by at least 70 ft, got {baseline_head_ft - updated_head_ft:.2f} ft"
    )
    assert updated_upstream_flow_gpm - baseline_upstream_flow_gpm >= 250.0, (
        f"Expected the OutflowNode withdrawal to increase upstream supply flow by at least 250 GPM, got {updated_upstream_flow_gpm - baseline_upstream_flow_gpm:.2f} GPM"
    )
    assert baseline_downstream_flow_gpm - updated_downstream_flow_gpm >= 120.0, (
        f"Expected the OutflowNode withdrawal to reduce downstream export flow by at least 120 GPM, got {baseline_downstream_flow_gpm - updated_downstream_flow_gpm:.2f} GPM"
    )


def test_tank_head_schedule_behaves_like_a_fixed_head_boundary():
    """A Tank head schedule should directly control the fixed head seen by the connected pipe."""
    data = _run_tank_head_step_case()
    time_s = np.asarray(data["time"])
    pre_tank_head_ft = _mean_over_window(time_s, data["node_head"]["T1"], 0.5, 1.5)
    post_tank_head_ft = _mean_over_window(time_s, data["node_head"]["T1"], 2.2, 3.5)
    pre_junction_head_ft = _mean_over_window(time_s, data["node_head"]["J1"], 0.5, 1.5)
    post_junction_head_ft = _mean_over_window(time_s, data["node_head"]["J1"], 2.2, 3.5)
    pre_flow_gpm = _mean_over_window(time_s, data["pipe_flow_gpm"]["P1"], 0.5, 1.5)
    post_flow_gpm = _mean_over_window(time_s, data["pipe_flow_gpm"]["P1"], 2.2, 3.5)

    assert abs(pre_tank_head_ft - 160.0) <= 0.5, (
        f"Expected the scheduled pre-step tank head to stay near 160 ft, got {pre_tank_head_ft:.2f} ft"
    )
    assert abs(post_tank_head_ft - 140.0) <= 0.5, (
        f"Expected the scheduled post-step tank head to stay near 140 ft, got {post_tank_head_ft:.2f} ft"
    )
    assert pre_junction_head_ft - post_junction_head_ft >= 5.0, (
        f"Expected lowering the tank head to reduce the connected junction head by at least 5 ft, got {pre_junction_head_ft - post_junction_head_ft:.2f} ft"
    )
    assert pre_flow_gpm - post_flow_gpm >= 10.0, (
        f"Expected lowering the tank head to reduce supplied flow by at least 10 GPM, got {pre_flow_gpm - post_flow_gpm:.2f} GPM"
    )


def test_clear_removes_network_topology_and_schedules():
    """clear() should remove nodes, pipes, and schedules before the next run()."""
    results = _run_clear_case()

    assert len(results["time"]) == int(LOSS_TOTAL_TIME_S / DT_S), (
        f"Expected an empty solver run after clear() to still emit the requested time vector length, got {len(results['time'])} samples"
    )
    assert results["node_head"] == {}, f"Expected clear() to remove all node series, got keys {list(results['node_head'])}"
    assert results["node_pressure"] == {}, f"Expected clear() to remove all node pressure series, got keys {list(results['node_pressure'])}"
    assert results["node_cavitation"] == {}, f"Expected clear() to remove all node cavitation series, got keys {list(results['node_cavitation'])}"
    assert results["pipe_flow_gpm"] == {}, f"Expected clear() to remove all pipe flow series, got keys {list(results['pipe_flow_gpm'])}"


def test_smaller_turbine_opening_reduces_flow_and_raises_upstream_head():
    """A more closed turbine should behave like a stronger hydraulic resistance."""
    open_case = _run_turbine_case(setting_pct=100.0)
    mid_case = _run_turbine_case(setting_pct=60.0)
    tight_case = _run_turbine_case(setting_pct=30.0)

    time_s = np.asarray(open_case["time"])
    open_flow_gpm = _mean_over_window(time_s, open_case["pipe_flow_gpm"]["P1"], 0.5, 1.5)
    mid_flow_gpm = _mean_over_window(time_s, mid_case["pipe_flow_gpm"]["P1"], 0.5, 1.5)
    tight_flow_gpm = _mean_over_window(time_s, tight_case["pipe_flow_gpm"]["P1"], 0.5, 1.5)
    open_head_ft = _mean_over_window(time_s, open_case["node_head"]["T1"], 0.5, 1.5)
    mid_head_ft = _mean_over_window(time_s, mid_case["node_head"]["T1"], 0.5, 1.5)
    tight_head_ft = _mean_over_window(time_s, tight_case["node_head"]["T1"], 0.5, 1.5)

    assert open_flow_gpm > mid_flow_gpm > tight_flow_gpm, (
        f"Expected smaller turbine openings to monotonically reduce flow, got open/mid/tight flows {open_flow_gpm:.2f}, {mid_flow_gpm:.2f}, {tight_flow_gpm:.2f} GPM"
    )
    assert open_head_ft < mid_head_ft < tight_head_ft, (
        f"Expected smaller turbine openings to monotonically raise upstream turbine head, got open/mid/tight heads {open_head_ft:.2f}, {mid_head_ft:.2f}, {tight_head_ft:.2f} ft"
    )
    assert open_flow_gpm - tight_flow_gpm >= 900.0, (
        f"Expected closing the turbine from 100 % to 30 % to cut through-flow by at least 900 GPM, got {open_flow_gpm - tight_flow_gpm:.2f} GPM"
    )
    assert tight_head_ft - open_head_ft >= 200.0, (
        f"Expected closing the turbine from 100 % to 30 % to raise upstream head by at least 200 ft, got {tight_head_ft - open_head_ft:.2f} ft"
    )


def test_fast_turbine_shutdown_creates_stronger_surge_than_slow_shutdown():
    """A faster turbine load rejection should create a larger pressure rise and sharper flow collapse."""
    fast_case = _run_turbine_shutdown_case(
        [(0.0, 100.0), (1.99, 100.0), (2.0, 10.0), (TURBINE_TOTAL_TIME_S, 10.0)]
    )
    slow_case = _run_turbine_shutdown_case(
        [(0.0, 100.0), (1.99, 100.0), (5.0, 10.0), (TURBINE_TOTAL_TIME_S, 10.0)]
    )

    time_fast = np.asarray(fast_case["time"])
    time_slow = np.asarray(slow_case["time"])
    fast_head_ft = np.asarray(fast_case["node_head"]["T1"])
    slow_head_ft = np.asarray(slow_case["node_head"]["T1"])
    fast_peak_head_ft = float(np.max(fast_head_ft))
    slow_peak_head_ft = float(np.max(slow_head_ft))
    fast_min_flow_gpm = float(np.min(np.asarray(fast_case["pipe_flow_gpm"]["P1"])))
    slow_min_flow_gpm = float(np.min(np.asarray(slow_case["pipe_flow_gpm"]["P1"])))

    assert fast_peak_head_ft >= slow_peak_head_ft + 70.0, (
        f"Expected a faster turbine shutdown to produce at least 70 ft more peak head than a slow shutdown, got fast {fast_peak_head_ft:.2f} ft and slow {slow_peak_head_ft:.2f} ft"
    )
    assert fast_min_flow_gpm <= -100.0 and slow_min_flow_gpm >= 0.0, (
        f"Expected a fast shutdown to drive reverse penstock flow while a slow shutdown remains forward-flowing, got min flows fast {fast_min_flow_gpm:.2f} GPM and slow {slow_min_flow_gpm:.2f} GPM"
    )


def test_fast_turbine_startup_creates_deeper_low_pressure_excursion_than_slow_startup():
    """A faster turbine startup should create the deeper low-pressure excursion."""
    fast_case = _run_turbine_startup_case(
        [(0.0, 10.0), (1.99, 10.0), (2.0, 100.0), (TURBINE_TOTAL_TIME_S, 100.0)]
    )
    slow_case = _run_turbine_startup_case(
        [(0.0, 10.0), (1.99, 10.0), (5.0, 100.0), (TURBINE_TOTAL_TIME_S, 100.0)]
    )

    time_fast = np.asarray(fast_case["time"])
    time_slow = np.asarray(slow_case["time"])
    fast_pre_head_ft = _mean_over_window(time_fast, fast_case["node_head"]["T1"], 0.5, 1.5)
    slow_pre_head_ft = _mean_over_window(time_slow, slow_case["node_head"]["T1"], 0.5, 1.5)
    fast_startup_min_head_ft = float(
        np.min(np.asarray(fast_case["node_head"]["T1"])[(time_fast >= 2.0) & (time_fast <= 4.0)])
    )
    slow_startup_min_head_ft = float(
        np.min(np.asarray(slow_case["node_head"]["T1"])[(time_slow >= 2.0) & (time_slow <= 4.0)])
    )
    fast_pre_discharge_gpm = _mean_over_window(time_fast, fast_case["pipe_flow_gpm"]["P2"], 0.5, 1.5)
    slow_pre_discharge_gpm = _mean_over_window(time_slow, slow_case["pipe_flow_gpm"]["P2"], 0.5, 1.5)
    fast_startup_discharge_gpm = _mean_over_window(time_fast, fast_case["pipe_flow_gpm"]["P2"], 2.0, 4.0)
    slow_startup_discharge_gpm = _mean_over_window(time_slow, slow_case["pipe_flow_gpm"]["P2"], 2.0, 4.0)

    assert abs(fast_pre_head_ft - slow_pre_head_ft) <= 1.0, (
        f"Expected fast and slow startup cases to share the same throttled initial head, got fast {fast_pre_head_ft:.2f} ft and slow {slow_pre_head_ft:.2f} ft"
    )
    assert slow_startup_min_head_ft - fast_startup_min_head_ft >= 60.0, (
        f"Expected a fast turbine startup to create at least 60 ft deeper low-pressure excursion than a slow startup, got fast min {fast_startup_min_head_ft:.2f} ft and slow min {slow_startup_min_head_ft:.2f} ft"
    )
    assert fast_pre_head_ft - fast_startup_min_head_ft >= 100.0, (
        f"Expected the fast startup to pull the turbine-node head materially below the throttled initial condition, got pre {fast_pre_head_ft:.2f} ft and startup minimum {fast_startup_min_head_ft:.2f} ft"
    )
    assert slow_pre_head_ft - slow_startup_min_head_ft >= 100.0, (
        f"Expected the slow startup to pull the turbine-node head materially below the throttled initial condition, got pre {slow_pre_head_ft:.2f} ft and startup minimum {slow_startup_min_head_ft:.2f} ft"
    )
    assert fast_startup_discharge_gpm - fast_pre_discharge_gpm >= 800.0, (
        f"Expected the fast startup to increase downstream turbine discharge by at least 800 GPM, got pre {fast_pre_discharge_gpm:.2f} GPM and startup mean {fast_startup_discharge_gpm:.2f} GPM"
    )
    assert slow_startup_discharge_gpm - slow_pre_discharge_gpm >= 800.0, (
        f"Expected the slow startup to increase downstream turbine discharge by at least 800 GPM, got pre {slow_pre_discharge_gpm:.2f} GPM and startup mean {slow_startup_discharge_gpm:.2f} GPM"
    )
