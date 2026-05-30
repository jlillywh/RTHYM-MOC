"""Air-valve-dominant mixed-device benchmark for pump-trip protection.

This benchmark flips the previous mixed-device hierarchy:

- the air valve sits near pump discharge and provides the primary vacuum relief
- a very small downstream hydropneumatic vessel provides only secondary damping

The shared acceptance metric is the average trip-window head across the three
protected-region nodes influenced by this layout:

- `Jd`, the pump-discharge junction
- `Vent`, the air-valve location
- `HPT1`, the small downstream damping vessel location

Expected outcome in this geometry:
- the air-only layout should outperform the vessel-only layout on protected-
  region mean head and on low-pressure/cavitation control
- the combined layout should improve the same protected-region mean head beyond
  the air-only case without sacrificing the air valve's vacuum protection
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
VESSEL_GAS_VOLUME_FT3 = 0.1
VESSEL_TANK_VOLUME_FT3 = 0.3

CASE_BOUNDS = [
    pytest.param("none", 0.0, 190, 90, id="none"),
    pytest.param("air", 20.0, 170, 4, id="air_only"),
    pytest.param("vessel", 17.0, 160, 50, id="vessel_only"),
    pytest.param("both", 30.0, 155, 4, id="both"),
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


def _run_case(kind):
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

    if kind in {"air", "both"}:
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
    else:
        solver.add_node(_make_node("Vent", "Junction", elevation=0.0, head=160.0))

    if kind in {"vessel", "both"}:
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
    else:
        solver.add_node(_make_node("HPT1", "Junction", head=160.0))

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
def air_valve_dominant_layout_data():
    return {kind: _run_case(kind) for kind in ["none", "air", "vessel", "both"]}


@pytest.mark.parametrize(("kind", "region_mean_floor_ft", "total_negative_max_steps", "total_cavitation_max_steps"), CASE_BOUNDS)
def test_air_valve_dominant_layout_meets_expected_bounds(
    air_valve_dominant_layout_data,
    kind,
    region_mean_floor_ft,
    total_negative_max_steps,
    total_cavitation_max_steps,
):
    """Each layout should satisfy explicit protected-region head and exposure bounds."""
    data = air_valve_dominant_layout_data[kind]
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
        f"Expected air-valve-dominant layout {kind} to keep protected-region mean trip head above {region_mean_floor_ft:.1f} ft, got {region_mean_head_ft:.2f} ft"
    )
    assert total_negative_steps <= total_negative_max_steps, (
        f"Expected air-valve-dominant layout {kind} to limit protected-region negative-head exposure to at most {total_negative_max_steps} samples, got {total_negative_steps}"
    )
    assert total_cavitation_steps <= total_cavitation_max_steps, (
        f"Expected air-valve-dominant layout {kind} to limit protected-region cavitation to at most {total_cavitation_max_steps} samples, got {total_cavitation_steps}"
    )


def test_air_valve_dominates_and_small_vessel_adds_secondary_damping(air_valve_dominant_layout_data):
    """Air-only should beat vessel-only, while the combination should beat air-only on the same regional metric."""
    region_mean_by_kind = {}
    total_negative_by_kind = {}
    total_cavitation_by_kind = {}

    for kind, data in air_valve_dominant_layout_data.items():
        time_s = np.asarray(data["time"])
        trip_window = (time_s >= TRIP_START_S) & (time_s <= TRIP_END_S)
        jd_head_ft = np.asarray(data["node_head"]["Jd"])
        vent_head_ft = np.asarray(data["node_head"]["Vent"])
        vessel_head_ft = np.asarray(data["node_head"]["HPT1"])
        jd_cavitation = np.asarray(data["node_cavitation"]["Jd"])
        vent_cavitation = np.asarray(data["node_cavitation"]["Vent"])
        vessel_cavitation = np.asarray(data["node_cavitation"]["HPT1"])

        region_mean_by_kind[kind] = (
            _mean_over_window(time_s, jd_head_ft, TRIP_START_S, TRIP_END_S)
            + _mean_over_window(time_s, vent_head_ft, TRIP_START_S, TRIP_END_S)
            + _mean_over_window(time_s, vessel_head_ft, TRIP_START_S, TRIP_END_S)
        ) / 3.0
        total_negative_by_kind[kind] = int(
            (jd_head_ft[trip_window] < 0.0).sum()
            + (vent_head_ft[trip_window] < 0.0).sum()
            + (vessel_head_ft[trip_window] < 0.0).sum()
        )
        total_cavitation_by_kind[kind] = int(
            jd_cavitation[trip_window].sum()
            + vent_cavitation[trip_window].sum()
            + vessel_cavitation[trip_window].sum()
        )

    assert region_mean_by_kind["none"] < region_mean_by_kind["vessel"] < region_mean_by_kind["air"] < region_mean_by_kind["both"], (
        f"Expected protected-region mean trip head ordering none < vessel < air < both, got {region_mean_by_kind}"
    )
    assert total_cavitation_by_kind["air"] <= 3 and total_cavitation_by_kind["both"] <= 3, (
        f"Expected air-valve-containing layouts to have very low protected-region cavitation in this geometry, got {total_cavitation_by_kind}"
    )
    assert total_cavitation_by_kind["vessel"] >= 40, (
        f"Expected the tiny downstream vessel alone to remain a weak cavitation control device here, got {total_cavitation_by_kind}"
    )
    assert total_negative_by_kind["both"] <= total_negative_by_kind["air"] - 3, (
        f"Expected the downstream vessel to cut at least 3 more negative-head samples beyond the air-only layout, got {total_negative_by_kind}"
    )
    assert region_mean_by_kind["both"] >= region_mean_by_kind["air"] + 8.0, (
        f"Expected the downstream vessel to add at least 8 ft of secondary damping beyond the air-only layout on protected-region mean head, got {region_mean_by_kind}"
    )
