"""Parameterized multi-device placement benchmark for split hydropneumatic protection.

This benchmark splits a fixed total hydropneumatic capacity across two vessels
and varies their placement along the pump-discharge main.

Network:
  Rlow -> Pump_A -> Jd -> HPT1 -> HPT2 -> Rhigh

Expected outcome in this geometry:
- layouts that keep at least one vessel near pump discharge should maintain
  strong trip-window recovery and avoid negative-head exposure at Jd
- layouts that move both vessels away from the disturbance source should lose
  most of that benefit and can allow cavitation to reappear
"""

import numpy as np
import pytest

import rthym_moc as m


DT_S = 0.01
TOTAL_TIME_S = 12.0
TRIP_START_S = 5.2
TRIP_END_S = 6.0
TOTAL_DISCHARGE_LENGTH_FT = 4040.0

PLACEMENT_CASES = [
    pytest.param((40.0, 300.0), 165.0, 0, 0, id="40ft_300ft"),
    pytest.param((40.0, 1200.0), 165.0, 0, 0, id="40ft_1200ft"),
    pytest.param((300.0, 1200.0), 0.0, 60, 0, id="300ft_1200ft"),
    pytest.param((600.0, 1200.0), -16.0, 80, 5, id="600ft_1200ft"),
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


def _add_split_vessel(solver, node_id):
    solver.add_node(
        _make_node(
            node_id,
            "HydropneumaticTank",
            head=160.0,
            diameter=4.0,
            gas_volume=6.0,
            tank_volume=15.0,
            polytropic_n=1.2,
            loss_coeff_in=0.7,
            loss_coeff_out=0.7,
        )
    )


def _run_multi_device_placement_case(positions_ft):
    first_position_ft, second_position_ft = sorted(positions_ft)

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
    _add_split_vessel(solver, "HPT1")
    _add_split_vessel(solver, "HPT2")
    solver.add_node(_make_node("Rhigh", "PressureBoundary", head=160.0))

    solver.add_pipe(_make_pipe("Ps", "Rlow", "PumpIn", 500.0, 800.0))
    solver.add_pipe(_make_pipe("Ppump", "Pump_A", "Jd", 40.0, 800.0))
    solver.add_pipe(_make_pipe("P1", "Jd", "HPT1", first_position_ft, 800.0))
    solver.add_pipe(_make_pipe("P2", "HPT1", "HPT2", second_position_ft - first_position_ft, 800.0))
    solver.add_pipe(
        _make_pipe(
            "Pmain",
            "HPT2",
            "Rhigh",
            max(40.0, TOTAL_DISCHARGE_LENGTH_FT - second_position_ft),
            800.0,
        )
    )

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
def multi_device_placement_data():
    return {
        positions_ft: _run_multi_device_placement_case(positions_ft)
        for positions_ft in [(40.0, 300.0), (40.0, 1200.0), (300.0, 1200.0), (600.0, 1200.0)]
    }


@pytest.mark.parametrize(("positions_ft", "trip_head_floor_ft", "negative_head_max_steps", "cavitation_max_steps"), PLACEMENT_CASES)
def test_multi_device_placement_cases_meet_expected_trip_window_bounds(
    multi_device_placement_data,
    positions_ft,
    trip_head_floor_ft,
    negative_head_max_steps,
    cavitation_max_steps,
):
    """Each two-vessel layout should satisfy an explicit trip-head and exposure bound."""
    data = multi_device_placement_data[positions_ft]
    time_s = np.asarray(data["time"])
    discharge_head_ft = np.asarray(data["node_head"]["Jd"])
    discharge_cavitation = np.asarray(data["node_cavitation"]["Jd"])

    trip_window = (time_s >= TRIP_START_S) & (time_s <= TRIP_END_S)
    trip_head_ft = _mean_over_window(time_s, discharge_head_ft, TRIP_START_S, TRIP_END_S)
    negative_head_steps = int((discharge_head_ft[trip_window] < 0.0).sum())
    cavitation_steps = int(discharge_cavitation[trip_window].sum())

    assert trip_head_ft >= trip_head_floor_ft, (
        f"Expected split-vessel placement {positions_ft} ft to keep trip-window mean head above {trip_head_floor_ft:.1f} ft, got {trip_head_ft:.2f} ft"
    )
    assert negative_head_steps <= negative_head_max_steps, (
        f"Expected split-vessel placement {positions_ft} ft to limit negative-head exposure to at most {negative_head_max_steps} steps, got {negative_head_steps}"
    )
    assert cavitation_steps <= cavitation_max_steps, (
        f"Expected split-vessel placement {positions_ft} ft to limit cavitation to at most {cavitation_max_steps} trip-window steps, got {cavitation_steps}"
    )


def test_multi_device_placement_requires_a_near_pump_vessel(multi_device_placement_data):
    """Keeping one of two smaller vessels near pump discharge should dominate all-remote layouts."""
    near_layouts = [(40.0, 300.0), (40.0, 1200.0)]
    remote_layouts = [(300.0, 1200.0), (600.0, 1200.0)]

    near_trip_heads = []
    near_negative_steps = []
    remote_trip_heads = []
    remote_negative_steps = []

    for positions_ft in near_layouts:
        data = multi_device_placement_data[positions_ft]
        time_s = np.asarray(data["time"])
        discharge_head_ft = np.asarray(data["node_head"]["Jd"])
        trip_window = (time_s >= TRIP_START_S) & (time_s <= TRIP_END_S)
        near_trip_heads.append(_mean_over_window(time_s, discharge_head_ft, TRIP_START_S, TRIP_END_S))
        near_negative_steps.append(int((discharge_head_ft[trip_window] < 0.0).sum()))

    for positions_ft in remote_layouts:
        data = multi_device_placement_data[positions_ft]
        time_s = np.asarray(data["time"])
        discharge_head_ft = np.asarray(data["node_head"]["Jd"])
        trip_window = (time_s >= TRIP_START_S) & (time_s <= TRIP_END_S)
        remote_trip_heads.append(_mean_over_window(time_s, discharge_head_ft, TRIP_START_S, TRIP_END_S))
        remote_negative_steps.append(int((discharge_head_ft[trip_window] < 0.0).sum()))

    assert min(near_trip_heads) >= 150.0, (
        f"Expected any split-vessel layout with one near-pump vessel to keep trip-window mean head above 150 ft, got {near_trip_heads}"
    )
    assert max(near_negative_steps) == 0, (
        f"Expected any split-vessel layout with one near-pump vessel to avoid negative-head exposure, got counts {near_negative_steps}"
    )
    assert max(remote_trip_heads) <= 10.0, (
        f"Expected all-remote split-vessel layouts to provide only weak trip-window recovery, got heads {remote_trip_heads}"
    )
    assert min(remote_negative_steps) >= 50, (
        f"Expected all-remote split-vessel layouts to retain substantial negative-head exposure, got counts {remote_negative_steps}"
    )
    assert min(near_trip_heads) - max(remote_trip_heads) >= 140.0, (
        f"Expected keeping one vessel near pump discharge to improve trip-window mean head by at least 140 ft versus all-remote layouts, got near {near_trip_heads} and remote {remote_trip_heads}"
    )
