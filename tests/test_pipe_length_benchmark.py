"""Parameterized pipe-length benchmark for hydropneumatic pump-trip protection.

This benchmark varies the protected discharge-main length while holding the
hydropneumatic vessel size and placement fixed near pump discharge.

Network:
  Rlow -> Pump_A -> Jd -> HPT1 -> Rhigh

Expected outcome in this geometry:
- very short discharge mains allow deeper low-pressure collapse after pump trip
- longer discharge mains improve trip-window recovery at the pump discharge
- negative-head exposure should disappear once the protected main is long enough
"""

import numpy as np
import pytest

import rthym_moc as m


DT_S = 0.01
TOTAL_TIME_S = 12.0
TRIP_START_S = 5.2
TRIP_END_S = 6.0

LENGTH_CASES = [
    pytest.param(500.0, -10.0, 70, id="500ft"),
    pytest.param(1000.0, -10.0, 65, id="1000ft"),
    pytest.param(2000.0, 60.0, 0, id="2000ft"),
    pytest.param(4000.0, 180.0, 0, id="4000ft"),
    pytest.param(8000.0, 250.0, 0, id="8000ft"),
]


def _make_node(node_id, node_type, **kwargs):
    node = m.NodeInput()
    node.id = node_id
    node.type = node_type
    for key, value in kwargs.items():
        setattr(node, key, value)
    return node


def _make_pipe(pipe_id, from_node, to_node, length_ft, flow_gpm):
    pipe = m.PipeInput()
    pipe.id = pipe_id
    pipe.from_node = from_node
    pipe.to_node = to_node
    pipe.length = length_ft
    pipe.diameter = 12.0
    pipe.roughness = 130.0
    pipe.flow_gpm = flow_gpm
    return pipe


def _mean_over_window(time_s, values, start_s, end_s):
    mask = (time_s >= start_s) & (time_s <= end_s)
    assert np.any(mask), f"No samples found in window [{start_s}, {end_s}] s"
    return float(np.asarray(values)[mask].mean())


def _run_pipe_length_case(discharge_main_length_ft):
    solver = m.MOCSolver()
    solver.add_node(_make_node("Rlow", "PressureBoundary", head=100.0))
    solver.add_node(_make_node("PumpIn", "Junction", head=100.0))
    solver.add_node(
        _make_node(
            "Pump_A",
            "Pump",
            design_head=120.0,
            design_flow=500.0,
            current_speed=100.0,
            head=220.0,
        )
    )
    solver.add_node(_make_node("Jd", "Junction", head=220.0))
    solver.add_node(
        _make_node(
            "HPT1",
            "HydropneumaticTank",
            head=160.0,
            diameter=4.0,
            gas_volume=12.0,
            tank_volume=30.0,
            polytropic_n=1.2,
            loss_coeff_in=0.7,
            loss_coeff_out=0.7,
        )
    )
    solver.add_node(_make_node("Rhigh", "PressureBoundary", head=160.0))

    solver.add_pipe(_make_pipe("Ps", "Rlow", "PumpIn", 500.0, 800.0))
    solver.add_pipe(_make_pipe("Ppump", "Pump_A", "Jd", 40.0, 800.0))
    solver.add_pipe(_make_pipe("Pstub", "Jd", "HPT1", 40.0, 800.0))
    solver.add_pipe(_make_pipe("Pmain", "HPT1", "Rhigh", discharge_main_length_ft, 800.0))

    solver.set_pump_schedule(
        "Pump_A",
        [
            (0.0, 100.0),
            (4.99, 100.0),
            (5.0, 0.0),
            (TOTAL_TIME_S, 0.0),
        ],
    )
    return solver.run(total_time=TOTAL_TIME_S, dt=DT_S)


@pytest.fixture(scope="module")
def hydropneumatic_pipe_length_data():
    return {
        discharge_main_length_ft: _run_pipe_length_case(discharge_main_length_ft)
        for discharge_main_length_ft in [500.0, 1000.0, 2000.0, 4000.0, 8000.0]
    }


@pytest.mark.parametrize(("discharge_main_length_ft", "trip_head_floor_ft", "negative_head_max_steps"), LENGTH_CASES)
def test_pipe_length_sweep_meets_expected_trip_window_bounds(
    hydropneumatic_pipe_length_data,
    discharge_main_length_ft,
    trip_head_floor_ft,
    negative_head_max_steps,
):
    """Each discharge-main length should satisfy an explicit trip-head and low-pressure bound."""
    data = hydropneumatic_pipe_length_data[discharge_main_length_ft]
    time_s = np.asarray(data["time"])
    discharge_head_ft = np.asarray(data["node_head"]["Jd"])
    discharge_cavitation = np.asarray(data["node_cavitation"]["Jd"])

    trip_window = (time_s >= TRIP_START_S) & (time_s <= TRIP_END_S)
    trip_head_ft = _mean_over_window(time_s, discharge_head_ft, TRIP_START_S, TRIP_END_S)
    negative_head_steps = int((discharge_head_ft[trip_window] < 0.0).sum())
    trip_cavitation_steps = int(discharge_cavitation[trip_window].sum())

    assert trip_head_ft >= trip_head_floor_ft, (
        f"Expected discharge-main length {discharge_main_length_ft:.0f} ft to keep trip-window mean head above {trip_head_floor_ft:.1f} ft, got {trip_head_ft:.2f} ft"
    )
    assert negative_head_steps <= negative_head_max_steps, (
        f"Expected discharge-main length {discharge_main_length_ft:.0f} ft to limit negative-head exposure to at most {negative_head_max_steps} steps, got {negative_head_steps}"
    )
    assert trip_cavitation_steps == 0, (
        f"Expected discharge-main length {discharge_main_length_ft:.0f} ft to avoid actual trip-window cavitation at Jd, got {trip_cavitation_steps} cavitating steps"
    )


def test_pipe_length_sweep_is_monotonic(hydropneumatic_pipe_length_data):
    """Longer protected discharge mains should improve recovery in this pump-trip geometry."""
    ordered_lengths = [500.0, 1000.0, 2000.0, 4000.0, 8000.0]
    ordered_trip_heads = []
    ordered_negative_steps = []
    ordered_min_heads = []

    for discharge_main_length_ft in ordered_lengths:
        data = hydropneumatic_pipe_length_data[discharge_main_length_ft]
        time_s = np.asarray(data["time"])
        discharge_head_ft = np.asarray(data["node_head"]["Jd"])
        trip_window = (time_s >= TRIP_START_S) & (time_s <= TRIP_END_S)

        ordered_trip_heads.append(_mean_over_window(time_s, discharge_head_ft, TRIP_START_S, TRIP_END_S))
        ordered_negative_steps.append(int((discharge_head_ft[trip_window] < 0.0).sum()))
        ordered_min_heads.append(float(discharge_head_ft[trip_window].min()))

    assert all(lhs < rhs for lhs, rhs in zip(ordered_trip_heads, ordered_trip_heads[1:])), (
        f"Expected longer discharge mains to improve trip-window mean head monotonically, got heads {ordered_trip_heads} for lengths {ordered_lengths}"
    )
    assert all(lhs >= rhs for lhs, rhs in zip(ordered_negative_steps, ordered_negative_steps[1:])), (
        f"Expected longer discharge mains to reduce negative-head exposure monotonically, got exposure counts {ordered_negative_steps} for lengths {ordered_lengths}"
    )
    assert ordered_min_heads[0] < 0.0 and ordered_min_heads[1] < 0.0, (
        f"Expected the two shortest discharge mains to dip below zero during the trip window, got minima {ordered_min_heads[:2]}"
    )
    assert all(min_head > 0.0 for min_head in ordered_min_heads[2:]), (
        f"Expected discharge mains of 2000 ft and longer to stay above zero during the trip window, got minima {ordered_min_heads[2:]}"
    )
    assert all(lhs < rhs for lhs, rhs in zip(ordered_min_heads[2:], ordered_min_heads[3:])), (
        f"Expected longer discharge mains beyond 2000 ft to raise the trip-window minimum head monotonically, got minima {ordered_min_heads} for lengths {ordered_lengths}"
    )
    assert ordered_trip_heads[-1] - ordered_trip_heads[0] >= 250.0, (
        f"Expected the longest discharge main to recover at least 250 ft more trip head than the shortest, got {ordered_trip_heads[-1] - ordered_trip_heads[0]:.2f} ft"
    )