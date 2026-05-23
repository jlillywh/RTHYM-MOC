"""Size-sweep benchmark within the air-valve-dominant protection regime.

This benchmark fixes a near-pump air valve and a downstream vessel location,
then sweeps the size of the tiny secondary hydropneumatic vessel.

Network:
  Rlow -> Pump_A -> Jd -> Vent(air valve fixed near pump) -> HPT1(size sweep) -> Rhigh

Expected outcome in this geometry:
- the air valve should continue to eliminate protected-region cavitation across
  the whole sweep
- increasing the tiny secondary vessel size should monotonically improve the
  protected-region mean trip head
- protected-region negative-head exposure should remain broadly bounded because
  the air valve is still the dominant protection element
"""

import numpy as np
import pytest

import rthym_moc as m


DT_S = 0.01
TOTAL_TIME_S = 12.0
TRIP_START_S = 5.2
TRIP_END_S = 6.0
TOTAL_DISCHARGE_LENGTH_FT = 4040.0
VENT_DISTANCE_FT = 80.0
VESSEL_DISTANCE_FT = 1200.0
PRECHARGE_RATIO = 1.0 / 3.0

SIZE_CASES = [
    pytest.param(0.3, 30.0, 155, 0, id="0.3ft3"),
    pytest.param(0.6, 36.0, 155, 0, id="0.6ft3"),
    pytest.param(1.2, 44.0, 155, 0, id="1.2ft3"),
    pytest.param(2.4, 53.0, 155, 0, id="2.4ft3"),
    pytest.param(4.8, 58.0, 155, 0, id="4.8ft3"),
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


def _run_case(vessel_tank_volume_ft3):
    vessel_gas_volume_ft3 = PRECHARGE_RATIO * vessel_tank_volume_ft3

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
            "Vent",
            "AirValve",
            elevation=0.0,
            head=160.0,
            diameter=6.0,
            air_release_diameter=0.25,
            gas_volume=0.05,
            tank_volume=2.0,
            loss_coeff_in=0.8,
            loss_coeff_out=0.7,
        )
    )
    solver.add_node(
        _make_node(
            "HPT1",
            "HydropneumaticTank",
            head=160.0,
            diameter=4.0,
            gas_volume=vessel_gas_volume_ft3,
            tank_volume=vessel_tank_volume_ft3,
            polytropic_n=1.2,
            loss_coeff_in=0.7,
            loss_coeff_out=0.7,
        )
    )
    solver.add_node(_make_node("Rhigh", "PressureBoundary", head=160.0))

    solver.add_pipe(_make_pipe("Ps", "Rlow", "PumpIn", 500.0, 800.0))
    solver.add_pipe(_make_pipe("Ppump", "Pump_A", "Jd", 40.0, 800.0))
    solver.add_pipe(_make_pipe("P1", "Jd", "Vent", VENT_DISTANCE_FT, 800.0))
    solver.add_pipe(_make_pipe("P2", "Vent", "HPT1", max(40.0, VESSEL_DISTANCE_FT - VENT_DISTANCE_FT), 800.0))
    solver.add_pipe(
        _make_pipe(
            "Pmain",
            "HPT1",
            "Rhigh",
            max(40.0, TOTAL_DISCHARGE_LENGTH_FT - VESSEL_DISTANCE_FT),
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
def air_valve_dominant_size_sweep_data():
    return {
        vessel_tank_volume_ft3: _run_case(vessel_tank_volume_ft3)
        for vessel_tank_volume_ft3 in [0.3, 0.6, 1.2, 2.4, 4.8]
    }


@pytest.mark.parametrize(("vessel_tank_volume_ft3", "region_mean_floor_ft", "total_negative_max_steps", "total_cavitation_max_steps"), SIZE_CASES)
def test_air_valve_dominant_vessel_size_cases_meet_expected_bounds(
    air_valve_dominant_size_sweep_data,
    vessel_tank_volume_ft3,
    region_mean_floor_ft,
    total_negative_max_steps,
    total_cavitation_max_steps,
):
    """Each vessel size should satisfy explicit protected-region bounds."""
    data = air_valve_dominant_size_sweep_data[vessel_tank_volume_ft3]
    time_s = np.asarray(data["time"])
    trip_window = (time_s >= TRIP_START_S) & (time_s <= TRIP_END_S)

    jd_head_ft = np.asarray(data["node_head"]["Jd"])
    vent_head_ft = np.asarray(data["node_head"]["Vent"])
    vessel_head_ft = np.asarray(data["node_head"]["HPT1"])
    jd_cavitation = np.asarray(data["node_cavitation"]["Jd"])
    vent_cavitation = np.asarray(data["node_cavitation"]["Vent"])
    vessel_cavitation = np.asarray(data["node_cavitation"]["HPT1"])

    region_mean_head_ft = (
        _mean_over_window(time_s, jd_head_ft, TRIP_START_S, TRIP_END_S)
        + _mean_over_window(time_s, vent_head_ft, TRIP_START_S, TRIP_END_S)
        + _mean_over_window(time_s, vessel_head_ft, TRIP_START_S, TRIP_END_S)
    ) / 3.0
    total_negative_steps = int(
        (jd_head_ft[trip_window] < 0.0).sum()
        + (vent_head_ft[trip_window] < 0.0).sum()
        + (vessel_head_ft[trip_window] < 0.0).sum()
    )
    total_cavitation_steps = int(
        jd_cavitation[trip_window].sum()
        + vent_cavitation[trip_window].sum()
        + vessel_cavitation[trip_window].sum()
    )

    assert region_mean_head_ft >= region_mean_floor_ft, (
        f"Expected downstream vessel size {vessel_tank_volume_ft3:.1f} ft^3 to keep protected-region mean trip head above {region_mean_floor_ft:.1f} ft, got {region_mean_head_ft:.2f} ft"
    )
    assert total_negative_steps <= total_negative_max_steps, (
        f"Expected downstream vessel size {vessel_tank_volume_ft3:.1f} ft^3 to limit protected-region negative-head exposure to at most {total_negative_max_steps} samples, got {total_negative_steps}"
    )
    assert total_cavitation_steps <= total_cavitation_max_steps, (
        f"Expected downstream vessel size {vessel_tank_volume_ft3:.1f} ft^3 to eliminate protected-region cavitation, got {total_cavitation_steps} samples"
    )


def test_air_valve_dominant_vessel_size_sweep_improves_regional_damping(
    air_valve_dominant_size_sweep_data,
):
    """Increasing tiny downstream vessel size should monotonically improve protected-region mean trip head."""
    ordered_sizes = [0.3, 0.6, 1.2, 2.4, 4.8]
    ordered_region_means = []
    ordered_total_negative = []
    ordered_total_cavitation = []

    for vessel_tank_volume_ft3 in ordered_sizes:
        data = air_valve_dominant_size_sweep_data[vessel_tank_volume_ft3]
        time_s = np.asarray(data["time"])
        trip_window = (time_s >= TRIP_START_S) & (time_s <= TRIP_END_S)
        jd_head_ft = np.asarray(data["node_head"]["Jd"])
        vent_head_ft = np.asarray(data["node_head"]["Vent"])
        vessel_head_ft = np.asarray(data["node_head"]["HPT1"])
        jd_cavitation = np.asarray(data["node_cavitation"]["Jd"])
        vent_cavitation = np.asarray(data["node_cavitation"]["Vent"])
        vessel_cavitation = np.asarray(data["node_cavitation"]["HPT1"])

        ordered_region_means.append(
            (
                _mean_over_window(time_s, jd_head_ft, TRIP_START_S, TRIP_END_S)
                + _mean_over_window(time_s, vent_head_ft, TRIP_START_S, TRIP_END_S)
                + _mean_over_window(time_s, vessel_head_ft, TRIP_START_S, TRIP_END_S)
            )
            / 3.0
        )
        ordered_total_negative.append(
            int(
                (jd_head_ft[trip_window] < 0.0).sum()
                + (vent_head_ft[trip_window] < 0.0).sum()
                + (vessel_head_ft[trip_window] < 0.0).sum()
            )
        )
        ordered_total_cavitation.append(
            int(
                jd_cavitation[trip_window].sum()
                + vent_cavitation[trip_window].sum()
                + vessel_cavitation[trip_window].sum()
            )
        )

    assert all(lhs < rhs for lhs, rhs in zip(ordered_region_means, ordered_region_means[1:])), (
        f"Expected larger tiny downstream vessels to improve protected-region mean trip head monotonically, got means {ordered_region_means} for sizes {ordered_sizes}"
    )
    assert all(value == 0 for value in ordered_total_cavitation), (
        f"Expected the fixed air-valve-dominant layout to remain cavitation-free across the calibrated size sweep, got cavitation counts {ordered_total_cavitation}"
    )
    assert max(ordered_total_negative) - min(ordered_total_negative) <= 5, (
        f"Expected protected-region negative-head exposure to remain broadly flat across the size sweep, got counts {ordered_total_negative}"
    )
    assert ordered_region_means[-1] - ordered_region_means[0] >= 25.0, (
        f"Expected the largest tiny downstream vessel to improve protected-region mean trip head by at least 25 ft over the smallest stable case, got {ordered_region_means[-1] - ordered_region_means[0]:.2f} ft"
    )