"""Parameterized hydropneumatic-vessel sizing benchmark.

This benchmark sweeps hydropneumatic vessel size on the pump-trip protection
geometry while keeping the precharge ratio fixed:

    gas_volume / tank_volume = 0.4

That lets the benchmark isolate the effect of overall vessel size, rather than
mixing size changes with a changing precharge state.

Network:
  Rlow -> Pump_A -> Jd -> HPT(size sweep) -> Rhigh

Expected outcome:
- larger vessels should recover more trip-window head at the pump discharge
- larger vessels should reduce or eliminate negative-head exposure during the
  trip window
- the whole sweep should remain free of actual vapor-pressure cavitation at Jd
"""

import numpy as np
import pytest

import rthym_moc as m


DT_S = 0.01
TOTAL_TIME_S = 12.0
TRIP_START_S = 5.2
TRIP_END_S = 6.0
PRECHARGE_RATIO = 0.4

SIZE_CASES = [
    pytest.param(2.0, 0.0, 60, id="2ft3"),
    pytest.param(4.0, 30.0, 20, id="4ft3"),
    pytest.param(6.0, 60.0, 0, id="6ft3"),
    pytest.param(10.0, 100.0, 0, id="10ft3"),
    pytest.param(20.0, 150.0, 0, id="20ft3"),
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


def _run_hydropneumatic_size_case(tank_volume_ft3):
    gas_volume_ft3 = PRECHARGE_RATIO * tank_volume_ft3

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
            gas_volume=gas_volume_ft3,
            tank_volume=tank_volume_ft3,
            polytropic_n=1.2,
            loss_coeff_in=0.7,
            loss_coeff_out=0.7,
        )
    )
    solver.add_node(_make_node("Rhigh", "PressureBoundary", head=160.0))

    solver.add_pipe(_make_pipe("Ps", "Rlow", "PumpIn", 500.0, 800.0))
    solver.add_pipe(_make_pipe("Ppump", "Pump_A", "Jd", 40.0, 800.0))
    solver.add_pipe(_make_pipe("Pstub", "Jd", "HPT1", 40.0, 800.0))
    solver.add_pipe(_make_pipe("Pmain", "HPT1", "Rhigh", 4000.0, 800.0))

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
def hydropneumatic_size_data():
    return {tank_volume: _run_hydropneumatic_size_case(tank_volume) for tank_volume in [2.0, 4.0, 6.0, 10.0, 20.0]}


@pytest.mark.parametrize(("tank_volume_ft3", "trip_head_floor_ft", "negative_head_max_steps"), SIZE_CASES)
def test_hydropneumatic_size_sweep_recovers_trip_head_and_limits_negative_exposure(
    hydropneumatic_size_data,
    tank_volume_ft3,
    trip_head_floor_ft,
    negative_head_max_steps,
):
    """Each vessel size should meet an explicit trip-head floor and negative-head exposure limit."""
    data = hydropneumatic_size_data[tank_volume_ft3]
    time_s = np.asarray(data["time"])
    discharge_head_ft = np.asarray(data["node_head"]["Jd"])
    discharge_cavitation = np.asarray(data["node_cavitation"]["Jd"])

    trip_window = (time_s >= TRIP_START_S) & (time_s <= TRIP_END_S)
    trip_head_ft = _mean_over_window(time_s, discharge_head_ft, TRIP_START_S, TRIP_END_S)
    negative_head_steps = int((discharge_head_ft[trip_window] < 0.0).sum())
    trip_cavitation_steps = int(discharge_cavitation[trip_window].sum())

    assert trip_head_ft >= trip_head_floor_ft, (
        f"Expected hydropneumatic tank volume {tank_volume_ft3:.1f} ft^3 to keep trip-window mean head above {trip_head_floor_ft:.1f} ft, got {trip_head_ft:.2f} ft"
    )
    assert negative_head_steps <= negative_head_max_steps, (
        f"Expected hydropneumatic tank volume {tank_volume_ft3:.1f} ft^3 to limit negative-head exposure to at most {negative_head_max_steps} steps, got {negative_head_steps}"
    )
    assert trip_cavitation_steps == 0, (
        f"Expected hydropneumatic tank volume {tank_volume_ft3:.1f} ft^3 to avoid actual trip-window cavitation at Jd, got {trip_cavitation_steps} cavitating steps"
    )


def test_hydropneumatic_size_sweep_is_monotonic(hydropneumatic_size_data):
    """Larger vessels at fixed precharge ratio should improve trip-window head recovery monotonically."""
    ordered_tank_volumes = [2.0, 4.0, 6.0, 10.0, 20.0]
    ordered_trip_heads = []
    ordered_negative_steps = []

    for tank_volume_ft3 in ordered_tank_volumes:
        data = hydropneumatic_size_data[tank_volume_ft3]
        time_s = np.asarray(data["time"])
        discharge_head_ft = np.asarray(data["node_head"]["Jd"])
        trip_window = (time_s >= TRIP_START_S) & (time_s <= TRIP_END_S)
        ordered_trip_heads.append(_mean_over_window(time_s, discharge_head_ft, TRIP_START_S, TRIP_END_S))
        ordered_negative_steps.append(int((discharge_head_ft[trip_window] < 0.0).sum()))

    assert all(lhs < rhs for lhs, rhs in zip(ordered_trip_heads, ordered_trip_heads[1:])), (
        f"Expected larger hydropneumatic vessels to improve trip-window mean head monotonically, got heads {ordered_trip_heads} for volumes {ordered_tank_volumes}"
    )
    assert all(lhs >= rhs for lhs, rhs in zip(ordered_negative_steps, ordered_negative_steps[1:])), (
        f"Expected larger hydropneumatic vessels to reduce negative-head exposure monotonically, got exposure counts {ordered_negative_steps} for volumes {ordered_tank_volumes}"
    )
    assert ordered_trip_heads[-1] - ordered_trip_heads[0] >= 150.0, (
        f"Expected the largest hydropneumatic vessel to recover at least 150 ft more trip head than the smallest, got {ordered_trip_heads[-1] - ordered_trip_heads[0]:.2f} ft"
    )
