"""Mixed-device interaction benchmark for pump-trip low-pressure protection.

This benchmark combines a small near-pump hydropneumatic vessel with a nearby
air valve on the same discharge main and compares four layouts:

- no protection
- air valve only
- surge vessel only
- surge vessel plus air valve

The shared acceptance metric is the aggregate trip-window negative-head
exposure across the two critical nodes that each device influences:

- `Jd`, the pump-discharge junction
- `Vent`, the downstream vent location

Expected outcome in this geometry:
- the air valve should reduce downstream vacuum exposure substantially
- the small surge vessel should reduce discharge-side collapse substantially
- the combined layout should outperform either single-device layout on total
  negative-head exposure across the two-node protected region
"""

import numpy as np
import pytest

import rthym_moc as m


DT_S = 0.01
TOTAL_TIME_S = 12.0
TRIP_START_S = 5.2
TRIP_END_S = 6.0
TOTAL_DISCHARGE_LENGTH_FT = 4040.0
VESSEL_DISTANCE_FT = 80.0
VENT_DISTANCE_FT = 120.0

CASE_BOUNDS = [
    pytest.param("none", 170, 90, 81, 90, id="none"),
    pytest.param("air", 145, 5, 81, 70, id="air_only"),
    pytest.param("vessel", 110, 0, 80, 35, id="vessel_only"),
    pytest.param("both", 90, 0, 80, 10, id="both"),
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

    if kind in {"vessel", "both"}:
        solver.add_node(
            _make_node(
                "HPT1",
                "HydropneumaticTank",
                head=160.0,
                diameter=4.0,
                gas_volume=0.5,
                tank_volume=1.5,
                polytropic_n=1.2,
                loss_coeff_in=0.7,
                loss_coeff_out=0.7,
            )
        )
    else:
        solver.add_node(_make_node("HPT1", "Junction", head=160.0))

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

    solver.add_node(_make_node("Rhigh", "PressureBoundary", head=160.0))

    solver.add_pipe(_make_pipe("Ps", "Rlow", "PumpIn", 500.0, 800.0))
    solver.add_pipe(_make_pipe("Ppump", "Pump_A", "Jd", 40.0, 800.0))
    solver.add_pipe(_make_pipe("P1", "Jd", "HPT1", VESSEL_DISTANCE_FT, 800.0))
    solver.add_pipe(_make_pipe("P2", "HPT1", "Vent", max(40.0, VENT_DISTANCE_FT - VESSEL_DISTANCE_FT), 800.0))
    solver.add_pipe(
        _make_pipe(
            "Pmain",
            "Vent",
            "Rhigh",
            max(40.0, TOTAL_DISCHARGE_LENGTH_FT - VENT_DISTANCE_FT),
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
def mixed_device_interaction_data():
    return {kind: _run_case(kind) for kind in ["none", "air", "vessel", "both"]}


@pytest.mark.parametrize(("kind", "total_negative_max_steps", "total_cavitation_max_steps", "jd_negative_max_steps", "vent_negative_max_steps"), CASE_BOUNDS)
def test_mixed_device_cases_meet_expected_trip_window_bounds(
    mixed_device_interaction_data,
    kind,
    total_negative_max_steps,
    total_cavitation_max_steps,
    jd_negative_max_steps,
    vent_negative_max_steps,
):
    """Each protection layout should satisfy explicit aggregate and local exposure bounds."""
    data = mixed_device_interaction_data[kind]
    time_s = np.asarray(data["time"])
    trip_window = (time_s >= TRIP_START_S) & (time_s <= TRIP_END_S)

    jd_head_ft = np.asarray(data["node_head"]["Jd"])
    vent_head_ft = np.asarray(data["node_head"]["Vent"])
    jd_cavitation = np.asarray(data["node_cavitation"]["Jd"])
    vent_cavitation = np.asarray(data["node_cavitation"]["Vent"])

    jd_negative_steps = int((jd_head_ft[trip_window] < 0.0).sum())
    vent_negative_steps = int((vent_head_ft[trip_window] < 0.0).sum())
    total_negative_steps = jd_negative_steps + vent_negative_steps
    total_cavitation_steps = int(jd_cavitation[trip_window].sum() + vent_cavitation[trip_window].sum())

    assert total_negative_steps <= total_negative_max_steps, (
        f"Expected mixed-device layout {kind} to limit total trip-window negative-head exposure to at most {total_negative_max_steps} samples, got {total_negative_steps}"
    )
    assert total_cavitation_steps <= total_cavitation_max_steps, (
        f"Expected mixed-device layout {kind} to limit total trip-window cavitation to at most {total_cavitation_max_steps} samples, got {total_cavitation_steps}"
    )
    assert jd_negative_steps <= jd_negative_max_steps, (
        f"Expected mixed-device layout {kind} to limit discharge-node negative-head exposure to at most {jd_negative_max_steps} samples, got {jd_negative_steps}"
    )
    assert vent_negative_steps <= vent_negative_max_steps, (
        f"Expected mixed-device layout {kind} to limit vent-node negative-head exposure to at most {vent_negative_max_steps} samples, got {vent_negative_steps}"
    )


def test_mixed_devices_reduce_total_low_pressure_exposure_best(mixed_device_interaction_data):
    """The combined layout should beat either single-device layout on aggregate low-pressure exposure."""
    exposure_by_kind = {}
    mean_head_by_kind = {}

    for kind, data in mixed_device_interaction_data.items():
        time_s = np.asarray(data["time"])
        trip_window = (time_s >= TRIP_START_S) & (time_s <= TRIP_END_S)
        jd_head_ft = np.asarray(data["node_head"]["Jd"])
        vent_head_ft = np.asarray(data["node_head"]["Vent"])

        exposure_by_kind[kind] = int((jd_head_ft[trip_window] < 0.0).sum() + (vent_head_ft[trip_window] < 0.0).sum())
        mean_head_by_kind[kind] = 0.5 * (
            _mean_over_window(time_s, jd_head_ft, TRIP_START_S, TRIP_END_S)
            + _mean_over_window(time_s, vent_head_ft, TRIP_START_S, TRIP_END_S)
        )

    assert exposure_by_kind["none"] > exposure_by_kind["air"] > exposure_by_kind["vessel"] > exposure_by_kind["both"], (
        f"Expected aggregate low-pressure exposure ordering none > air > vessel > both, got {exposure_by_kind}"
    )
    assert exposure_by_kind["both"] <= exposure_by_kind["vessel"] - 20, (
        f"Expected combined protection to cut at least 20 more negative-head samples than the vessel-only case, got vessel={exposure_by_kind['vessel']} and both={exposure_by_kind['both']}"
    )
    assert exposure_by_kind["both"] <= exposure_by_kind["air"] - 50, (
        f"Expected combined protection to cut at least 50 more negative-head samples than the air-only case, got air={exposure_by_kind['air']} and both={exposure_by_kind['both']}"
    )
    assert mean_head_by_kind["both"] >= mean_head_by_kind["air"] + 14.0, (
        f"Expected combined protection to raise the average protected-region trip head at least 14 ft above the air-only case, got {mean_head_by_kind}"
    )