"""Simple pump and valve transient regression for an uphill pumping main.

This fixture models a low reservoir, a pump, a long main, and a throttled valve
feeding a higher reservoir. The tests focus on transient behavior that should be
stable across solver changes:

- pump trip should collapse discharge head and reverse the suction-side pipe
- pump restart should rebuild forward pumping conditions
- fast valve closure should create a larger surge than slow closure
- reopening a nearly closed valve should restore flow and relieve deadhead head
"""

from pathlib import Path

import numpy as np
import pytest
import rthym_moc

pytest.importorskip("wntr", reason="wntr is required for INP benchmark tests")

NETWORK_PATH = Path(__file__).resolve().parent / "networks" / "pump_valve_benchmark.inp"

DT_S = 0.01
PUMP_TOTAL_TIME_S = 15.0
VALVE_TOTAL_TIME_S = 12.0

PRE_EVENT_START_S = 1.0
PRE_EVENT_END_S = 4.0
PUMP_TRIP_START_S = 5.2
PUMP_TRIP_END_S = 6.0
PUMP_RESTART_START_S = 10.2
PUMP_RESTART_END_S = 11.0
VALVE_OPEN_PRE_START_S = 5.0
VALVE_OPEN_PRE_END_S = 7.0
VALVE_OPEN_LATE_START_S = 10.2
VALVE_OPEN_LATE_END_S = 11.5


def _mean_over_window(time_s, values, start_s, end_s):
    mask = (time_s >= start_s) & (time_s <= end_s)
    assert np.any(mask), f"No samples found in window [{start_s}, {end_s}] s"
    return float(np.asarray(values)[mask].mean())


def _run_solver(*, total_time_s, pump_schedule=None, valve_schedule=None):
    solver = rthym_moc.load_inp(str(NETWORK_PATH), use_wntr=True)
    if pump_schedule is not None:
        solver.set_pump_schedule("_PUMP_Pump_A", pump_schedule)
    if valve_schedule is not None:
        solver.set_valve_schedule("_VALVE_Valve_A", valve_schedule)
    results = solver.run(total_time=total_time_s, dt=DT_S)
    results["time_s"] = np.asarray(results["time"])
    return results


@pytest.fixture(scope="module")
def pump_cycle_data():
    return _run_solver(
        total_time_s=PUMP_TOTAL_TIME_S,
        pump_schedule=[
            (0.0, 100.0),
            (4.99, 100.0),
            (5.0, 0.0),
            (9.99, 0.0),
            (10.0, 100.0),
            (PUMP_TOTAL_TIME_S, 100.0),
        ],
    )


@pytest.fixture(scope="module")
def fast_closure_data():
    return _run_solver(
        total_time_s=VALVE_TOTAL_TIME_S,
        valve_schedule=[
            (0.0, 10.0),
            (4.99, 10.0),
            (5.0, 0.0),
            (VALVE_TOTAL_TIME_S, 0.0),
        ],
    )


@pytest.fixture(scope="module")
def slow_closure_data():
    return _run_solver(
        total_time_s=VALVE_TOTAL_TIME_S,
        valve_schedule=[
            (0.0, 10.0),
            (4.99, 10.0),
            (9.0, 0.0),
            (VALVE_TOTAL_TIME_S, 0.0),
        ],
    )


@pytest.fixture(scope="module")
def reopening_data():
    return _run_solver(
        total_time_s=VALVE_TOTAL_TIME_S,
        valve_schedule=[
            (0.0, 1.0),
            (7.99, 1.0),
            (10.0, 100.0),
            (VALVE_TOTAL_TIME_S, 100.0),
        ],
    )


def test_initial_operating_point_pumps_uphill(pump_cycle_data):
    """The baseline state should move water uphill from the low reservoir."""
    pre_suction_flow_gpm = _mean_over_window(
        pump_cycle_data["time_s"],
        pump_cycle_data["pipe_flow_gpm"]["Pipe_Suction"],
        PRE_EVENT_START_S,
        PRE_EVENT_END_S,
    )
    pre_main_flow_gpm = _mean_over_window(
        pump_cycle_data["time_s"],
        pump_cycle_data["pipe_flow_gpm"]["Pipe_Main"],
        PRE_EVENT_START_S,
        PRE_EVENT_END_S,
    )
    high_side_head_ft = _mean_over_window(
        pump_cycle_data["time_s"],
        pump_cycle_data["node_head"]["Valve_A_in"],
        PRE_EVENT_START_S,
        PRE_EVENT_END_S,
    )

    assert pre_suction_flow_gpm >= 700.0, f"Expected strong suction-side forward flow, got {pre_suction_flow_gpm:.2f} GPM"
    assert pre_main_flow_gpm >= 700.0, f"Expected strong mainline forward flow, got {pre_main_flow_gpm:.2f} GPM"
    assert high_side_head_ft >= 162.0, f"Expected the pump to lift the main above the high reservoir, got {high_side_head_ft:.2f} ft"


def test_pump_trip_collapses_discharge_head_and_reverses_suction_flow(pump_cycle_data):
    """A pump trip should dump discharge head and reverse the suction-side pipe."""
    pre_discharge_head_ft = _mean_over_window(
        pump_cycle_data["time_s"],
        pump_cycle_data["node_head"]["Pump_A_out"],
        PRE_EVENT_START_S,
        PRE_EVENT_END_S,
    )
    tripped_discharge_head_ft = _mean_over_window(
        pump_cycle_data["time_s"],
        pump_cycle_data["node_head"]["Pump_A_out"],
        PUMP_TRIP_START_S,
        PUMP_TRIP_END_S,
    )
    pre_suction_flow_gpm = _mean_over_window(
        pump_cycle_data["time_s"],
        pump_cycle_data["pipe_flow_gpm"]["Pipe_Suction"],
        PRE_EVENT_START_S,
        PRE_EVENT_END_S,
    )
    tripped_suction_flow_gpm = _mean_over_window(
        pump_cycle_data["time_s"],
        pump_cycle_data["pipe_flow_gpm"]["Pipe_Suction"],
        PUMP_TRIP_START_S,
        PUMP_TRIP_END_S,
    )

    assert pre_discharge_head_ft - tripped_discharge_head_ft >= 150.0, (
        f"Expected pump trip to drop discharge head by at least 150 ft, got {pre_discharge_head_ft - tripped_discharge_head_ft:.2f} ft"
    )
    assert pre_suction_flow_gpm > 0.0, f"Expected pre-trip suction flow to be positive, got {pre_suction_flow_gpm:.2f} GPM"
    assert tripped_suction_flow_gpm < 0.0, f"Expected suction flow reversal after trip, got {tripped_suction_flow_gpm:.2f} GPM"


def test_pump_restart_recovers_forward_flow_and_discharge_head(pump_cycle_data):
    """Restarting the pump should rebuild positive flow and discharge head."""
    tripped_discharge_head_ft = _mean_over_window(
        pump_cycle_data["time_s"],
        pump_cycle_data["node_head"]["Pump_A_out"],
        PUMP_TRIP_START_S,
        PUMP_TRIP_END_S,
    )
    restarted_discharge_head_ft = _mean_over_window(
        pump_cycle_data["time_s"],
        pump_cycle_data["node_head"]["Pump_A_out"],
        PUMP_RESTART_START_S,
        PUMP_RESTART_END_S,
    )
    restarted_suction_flow_gpm = _mean_over_window(
        pump_cycle_data["time_s"],
        pump_cycle_data["pipe_flow_gpm"]["Pipe_Suction"],
        PUMP_RESTART_START_S,
        PUMP_RESTART_END_S,
    )

    assert restarted_discharge_head_ft - tripped_discharge_head_ft >= 150.0, (
        f"Expected restart to recover at least 150 ft of discharge head, got {restarted_discharge_head_ft - tripped_discharge_head_ft:.2f} ft"
    )
    assert restarted_discharge_head_ft >= 140.0, (
        f"Expected recovered discharge head near the pumped operating range, got {restarted_discharge_head_ft:.2f} ft"
    )
    assert restarted_suction_flow_gpm >= 300.0, f"Expected restart to restore strong forward suction flow, got {restarted_suction_flow_gpm:.2f} GPM"


def test_fast_valve_closure_creates_larger_upstream_surge_than_slow_closure(
    fast_closure_data,
    slow_closure_data,
):
    """Closing the valve quickly should produce the larger upstream pressure spike."""
    fast_peak_head_ft = float(np.max(np.asarray(fast_closure_data["node_head"]["Valve_A_in"])))
    slow_peak_head_ft = float(np.max(np.asarray(slow_closure_data["node_head"]["Valve_A_in"])))

    assert fast_peak_head_ft >= slow_peak_head_ft + 20.0, (
        f"Expected fast closure peak head to exceed slow closure by at least 20 ft, got {fast_peak_head_ft - slow_peak_head_ft:.2f} ft"
    )
    assert fast_peak_head_ft >= 780.0, f"Expected a pronounced fast-closure surge, got {fast_peak_head_ft:.2f} ft"


def test_fast_valve_closure_drives_stronger_flow_reversal_than_slow_closure(
    fast_closure_data,
    slow_closure_data,
):
    """The fast closure should force a deeper mainline flow reversal."""
    fast_min_flow_gpm = float(np.min(np.asarray(fast_closure_data["pipe_flow_gpm"]["Pipe_Main"])))
    slow_min_flow_gpm = float(np.min(np.asarray(slow_closure_data["pipe_flow_gpm"]["Pipe_Main"])))
    slow_late_flow_gpm = _mean_over_window(
        slow_closure_data["time_s"],
        slow_closure_data["pipe_flow_gpm"]["Pipe_Main"],
        9.5,
        11.0,
    )

    assert fast_min_flow_gpm <= -50.0, f"Expected fast closure to reverse Pipe_Main strongly, got {fast_min_flow_gpm:.2f} GPM"
    assert slow_min_flow_gpm >= 0.0, f"Expected slow closure to avoid full reversal during closure, got {slow_min_flow_gpm:.2f} GPM"
    assert slow_late_flow_gpm >= 100.0, f"Expected slow closure to retain forward flow late in the ramp, got {slow_late_flow_gpm:.2f} GPM"


def test_valve_reopening_restores_flow_and_relieves_deadhead_pressure(reopening_data):
    """Opening a nearly closed valve should recover flow and lower pump discharge head."""
    preopen_flow_gpm = _mean_over_window(
        reopening_data["time_s"],
        reopening_data["pipe_flow_gpm"]["Pipe_Main"],
        VALVE_OPEN_PRE_START_S,
        VALVE_OPEN_PRE_END_S,
    )
    late_flow_gpm = _mean_over_window(
        reopening_data["time_s"],
        reopening_data["pipe_flow_gpm"]["Pipe_Main"],
        VALVE_OPEN_LATE_START_S,
        VALVE_OPEN_LATE_END_S,
    )
    preopen_head_ft = _mean_over_window(
        reopening_data["time_s"],
        reopening_data["node_head"]["Pump_A_out"],
        VALVE_OPEN_PRE_START_S,
        VALVE_OPEN_PRE_END_S,
    )
    late_head_ft = _mean_over_window(
        reopening_data["time_s"],
        reopening_data["node_head"]["Pump_A_out"],
        VALVE_OPEN_LATE_START_S,
        VALVE_OPEN_LATE_END_S,
    )

    assert late_flow_gpm - preopen_flow_gpm >= 60.0, (
        f"Expected valve reopening to increase mainline flow by at least 60 GPM, got {late_flow_gpm - preopen_flow_gpm:.2f} GPM"
    )
    assert preopen_head_ft - late_head_ft >= 15.0, (
        f"Expected valve reopening to relieve at least 15 ft of discharge head, got {preopen_head_ft - late_head_ft:.2f} ft"
    )