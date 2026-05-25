"""Parameterized device-placement benchmark for hydropneumatic protection.

This benchmark varies hydropneumatic vessel placement along the pump-discharge
main while holding vessel size fixed. It checks the engineering expectation that
protection is strongest when the vessel is placed closer to the pump discharge,
where the low-pressure transient originates.

Network:
  Rlow -> Pump_A -> Jd -> HPT1(distance sweep) -> Rhigh

The total discharge-main length is held constant while the short connection to
the hydropneumatic vessel is moved farther from Jd.

Expected outcome:
- trip-window discharge head should fall monotonically as the vessel is moved
  farther from pump discharge
- negative-head exposure should increase as the vessel is moved farther away
- close placement should keep the trip response well above zero head, while far
  placement should allow deep low-pressure collapse and possible cavitation
"""

import numpy as np
import pytest

import rthym_moc as m


DT_S = 0.01
TOTAL_TIME_S = 12.0
TRIP_START_S = 5.2
TRIP_END_S = 6.0
TOTAL_DISCHARGE_LENGTH_FT = 4040.0
HEAD_BOUND_TOL_FT = 1.0

PLACEMENT_CASES = [
    pytest.param(40.0, 180.0, 0, id="40ft"),
    pytest.param(120.0, 100.0, 0, id="120ft"),
    pytest.param(300.0, -5.0, 70, id="300ft"),
    pytest.param(600.0, -20.0, 90, id="600ft"),
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


def _run_hydropneumatic_placement_case(distance_from_pump_ft):
    downstream_main_ft = max(40.0, TOTAL_DISCHARGE_LENGTH_FT - distance_from_pump_ft)

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
    solver.add_pipe(_make_pipe("Pstub", "Jd", "HPT1", distance_from_pump_ft, 800.0))
    solver.add_pipe(_make_pipe("Pmain", "HPT1", "Rhigh", downstream_main_ft, 800.0))

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
def hydropneumatic_placement_data():
    return {
        distance: _run_hydropneumatic_placement_case(distance)
        for distance in [40.0, 120.0, 300.0, 600.0]
    }


@pytest.mark.parametrize(("distance_from_pump_ft", "trip_head_floor_ft", "negative_head_max_steps"), PLACEMENT_CASES)
def test_hydropneumatic_placement_sweep_meets_expected_trip_window_bounds(
    hydropneumatic_placement_data,
    distance_from_pump_ft,
    trip_head_floor_ft,
    negative_head_max_steps,
):
    """Each placement should satisfy an explicit trip-head and negative-exposure bound."""
    data = hydropneumatic_placement_data[distance_from_pump_ft]
    time_s = np.asarray(data["time"])
    discharge_head_ft = np.asarray(data["node_head"]["Jd"])

    trip_window = (time_s >= TRIP_START_S) & (time_s <= TRIP_END_S)
    trip_head_ft = _mean_over_window(time_s, discharge_head_ft, TRIP_START_S, TRIP_END_S)
    negative_head_steps = int((discharge_head_ft[trip_window] < 0.0).sum())

    assert trip_head_ft >= trip_head_floor_ft - HEAD_BOUND_TOL_FT, (
        f"Expected hydropneumatic placement {distance_from_pump_ft:.0f} ft from pump discharge to keep trip head above {trip_head_floor_ft:.1f} ft within a {HEAD_BOUND_TOL_FT:.1f} ft numeric tolerance, got {trip_head_ft:.2f} ft"
    )
    assert negative_head_steps <= negative_head_max_steps, (
        f"Expected hydropneumatic placement {distance_from_pump_ft:.0f} ft from pump discharge to limit negative-head exposure to at most {negative_head_max_steps} steps, got {negative_head_steps}"
    )


def test_hydropneumatic_placement_sweep_is_monotonic(hydropneumatic_placement_data):
    """Moving the vessel farther from pump discharge should monotonically weaken protection."""
    ordered_distances = [40.0, 120.0, 300.0, 600.0]
    ordered_trip_heads = []
    ordered_negative_steps = []
    ordered_cavitation_steps = []

    for distance_from_pump_ft in ordered_distances:
        data = hydropneumatic_placement_data[distance_from_pump_ft]
        time_s = np.asarray(data["time"])
        discharge_head_ft = np.asarray(data["node_head"]["Jd"])
        discharge_cavitation = np.asarray(data["node_cavitation"]["Jd"])
        trip_window = (time_s >= TRIP_START_S) & (time_s <= TRIP_END_S)

        ordered_trip_heads.append(_mean_over_window(time_s, discharge_head_ft, TRIP_START_S, TRIP_END_S))
        ordered_negative_steps.append(int((discharge_head_ft[trip_window] < 0.0).sum()))
        ordered_cavitation_steps.append(int(discharge_cavitation[trip_window].sum()))

    assert all(lhs > rhs for lhs, rhs in zip(ordered_trip_heads, ordered_trip_heads[1:])), (
        f"Expected farther hydropneumatic placement to reduce trip-window head monotonically, got heads {ordered_trip_heads} for distances {ordered_distances}"
    )
    assert all(lhs <= rhs for lhs, rhs in zip(ordered_negative_steps, ordered_negative_steps[1:])), (
        f"Expected farther hydropneumatic placement to increase negative-head exposure monotonically, got exposure counts {ordered_negative_steps} for distances {ordered_distances}"
    )
    assert ordered_trip_heads[0] - ordered_trip_heads[-1] >= 200.0, (
        f"Expected near-vs-far placement to shift trip-window mean head by at least 200 ft, got {ordered_trip_heads[0] - ordered_trip_heads[-1]:.2f} ft"
    )
    assert ordered_cavitation_steps[-1] >= 1, (
        f"Expected the farthest placement case to allow at least some actual trip-window cavitation, got cavitation counts {ordered_cavitation_steps}"
    )
