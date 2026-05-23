"""Layout-sensitivity benchmark within the air-valve-dominant protection regime.

This benchmark fixes a near-pump air valve as the dominant protection element
and sweeps the location of a tiny downstream hydropneumatic vessel.

Network:
  Rlow -> Pump_A -> Jd -> Vent(air valve fixed near pump) -> HPT1(distance sweep) -> Rhigh

Expected outcome in this geometry:
- the air valve should continue to suppress protected-region cavitation across
  the sweep
- moving the tiny secondary vessel farther downstream should increase the
  protected-region mean trip head
- the sweep should remain bounded in negative-head exposure even though the air
  valve remains the primary protection element
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
VESSEL_GAS_VOLUME_FT3 = 0.1
VESSEL_TANK_VOLUME_FT3 = 0.3

DISTANCE_CASES = [
    pytest.param(300.0, 2.0, 135, 5, id="300ft"),
    pytest.param(600.0, 7.0, 145, 0, id="600ft"),
    pytest.param(1200.0, 30.0, 155, 0, id="1200ft"),
    pytest.param(2000.0, 50.0, 155, 0, id="2000ft"),
    pytest.param(3000.0, 57.0, 155, 0, id="3000ft"),
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


def _run_case(vessel_distance_ft):
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
            gas_volume=VESSEL_GAS_VOLUME_FT3,
            tank_volume=VESSEL_TANK_VOLUME_FT3,
            polytropic_n=1.2,
            loss_coeff_in=0.7,
            loss_coeff_out=0.7,
        )
    )
    solver.add_node(_make_node("Rhigh", "PressureBoundary", head=160.0))

    solver.add_pipe(_make_pipe("Ps", "Rlow", "PumpIn", 500.0, 800.0))
    solver.add_pipe(_make_pipe("Ppump", "Pump_A", "Jd", 40.0, 800.0))
    solver.add_pipe(_make_pipe("P1", "Jd", "Vent", VENT_DISTANCE_FT, 800.0))
    solver.add_pipe(_make_pipe("P2", "Vent", "HPT1", max(40.0, vessel_distance_ft - VENT_DISTANCE_FT), 800.0))
    solver.add_pipe(
        _make_pipe(
            "Pmain",
            "HPT1",
            "Rhigh",
            max(40.0, TOTAL_DISCHARGE_LENGTH_FT - vessel_distance_ft),
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
def air_valve_dominant_layout_sensitivity_data():
    return {
        vessel_distance_ft: _run_case(vessel_distance_ft)
        for vessel_distance_ft in [300.0, 600.0, 1200.0, 2000.0, 3000.0]
    }


@pytest.mark.parametrize(("vessel_distance_ft", "region_mean_floor_ft", "total_negative_max_steps", "total_cavitation_max_steps"), DISTANCE_CASES)
def test_air_valve_dominant_vessel_distance_cases_meet_expected_bounds(
    air_valve_dominant_layout_sensitivity_data,
    vessel_distance_ft,
    region_mean_floor_ft,
    total_negative_max_steps,
    total_cavitation_max_steps,
):
    """Each downstream-vessel distance should satisfy explicit protected-region bounds."""
    data = air_valve_dominant_layout_sensitivity_data[vessel_distance_ft]
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
        f"Expected downstream-vessel distance {vessel_distance_ft:.0f} ft to keep protected-region mean trip head above {region_mean_floor_ft:.1f} ft, got {region_mean_head_ft:.2f} ft"
    )
    assert total_negative_steps <= total_negative_max_steps, (
        f"Expected downstream-vessel distance {vessel_distance_ft:.0f} ft to limit protected-region negative-head exposure to at most {total_negative_max_steps} samples, got {total_negative_steps}"
    )
    assert total_cavitation_steps <= total_cavitation_max_steps, (
        f"Expected downstream-vessel distance {vessel_distance_ft:.0f} ft to limit protected-region cavitation to at most {total_cavitation_max_steps} samples, got {total_cavitation_steps}"
    )


def test_air_valve_dominant_vessel_distance_sweep_improves_regional_damping(
    air_valve_dominant_layout_sensitivity_data,
):
    """Moving the tiny secondary vessel farther downstream should increase protected-region mean trip head."""
    ordered_distances = [300.0, 600.0, 1200.0, 2000.0, 3000.0]
    ordered_region_means = []
    ordered_total_negative = []
    ordered_total_cavitation = []

    for vessel_distance_ft in ordered_distances:
        data = air_valve_dominant_layout_sensitivity_data[vessel_distance_ft]
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
        f"Expected farther downstream placement of the tiny secondary vessel to improve protected-region mean trip head monotonically, got means {ordered_region_means} for distances {ordered_distances}"
    )
    assert ordered_total_cavitation[0] >= 1 and all(value == 0 for value in ordered_total_cavitation[1:]), (
        f"Expected the shortest-distance case to be the only one with residual protected-region cavitation, got cavitation counts {ordered_total_cavitation}"
    )
    assert max(ordered_total_negative[1:]) - min(ordered_total_negative[1:]) <= 8, (
        f"Expected protected-region negative-head exposure to remain broadly bounded once the downstream vessel is 600 ft or farther away, got counts {ordered_total_negative}"
    )
    assert ordered_region_means[-1] - ordered_region_means[0] >= 50.0, (
        f"Expected moving the tiny secondary vessel from 300 ft to 3000 ft to improve protected-region mean trip head by at least 50 ft, got {ordered_region_means[-1] - ordered_region_means[0]:.2f} ft"
    )