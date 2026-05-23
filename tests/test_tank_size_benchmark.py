"""Parameterized standpipe-size benchmark.

This benchmark starts the surge-device parameter sweeps with standpipe size.
It uses the same rapid valve-closure protection geometry as the existing surge-
mitigation regressions and checks that increasing standpipe cross-sectional area
produces a stronger reduction in the protected-node pressure peak.

Network:
  R1 --[3000 ft]--> SP(area sweep) --[40 ft]--> Valve_A --[40 ft]--> R2

Expected outcome:
- all standpipe sizes suppress cavitation at the protected node
- larger standpipe area monotonically lowers the closure peak
- large standpipes drive the protected-node peak close to the steady head
"""

import numpy as np
import pytest

import rthym_moc as m


DT_S = 0.01
TOTAL_TIME_S = 12.0

AREA_CASES = [
    pytest.param(1.0, 160.0, id="1ft2"),
    pytest.param(2.0, 154.0, id="2ft2"),
    pytest.param(5.0, 150.0, id="5ft2"),
    pytest.param(10.0, 148.0, id="10ft2"),
    pytest.param(20.0, 147.0, id="20ft2"),
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


def _run_standpipe_area_case(tank_area_ft2):
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=150.0))
    solver.add_node(_make_node("SP1", "Standpipe", head=145.8, tank_area=tank_area_ft2))
    solver.add_node(_make_node("Valve_A", "Valve", diameter=12.0, current_setting=100.0, head=145.8))
    solver.add_node(_make_node("R2", "PressureBoundary", head=145.8))

    solver.add_pipe(_make_pipe("P1", "R1", "SP1", 3000.0, 500.0))
    solver.add_pipe(_make_pipe("P2", "SP1", "Valve_A", 40.0, 500.0))
    solver.add_pipe(_make_pipe("P3", "Valve_A", "R2", 40.0, 0.0))

    solver.set_valve_schedule(
        "Valve_A",
        [
            (0.0, 100.0),
            (DT_S, 0.0),
            (TOTAL_TIME_S, 0.0),
        ],
    )
    return solver.run(total_time=TOTAL_TIME_S, dt=DT_S)


@pytest.fixture(scope="module")
def standpipe_area_data():
    return {area: _run_standpipe_area_case(area) for area, _ in [(1.0, 160.0), (2.0, 154.0), (5.0, 150.0), (10.0, 148.0), (20.0, 147.0)]}


@pytest.mark.parametrize(("tank_area_ft2", "peak_limit_ft"), AREA_CASES)
def test_standpipe_tank_size_sweep_keeps_peak_within_expected_band(standpipe_area_data, tank_area_ft2, peak_limit_ft):
    """Each standpipe size should cap the closure peak within a tighter band as area increases."""
    data = standpipe_area_data[tank_area_ft2]
    peak_head_ft = float(np.max(np.asarray(data["node_head"]["SP1"])))
    cav_steps = int(np.asarray(data["node_cavitation"]["SP1"]).sum())

    assert peak_head_ft <= peak_limit_ft, (
        f"Expected standpipe area {tank_area_ft2:.1f} ft^2 to keep the protected-node peak below {peak_limit_ft:.1f} ft, got {peak_head_ft:.2f} ft"
    )
    assert cav_steps == 0, (
        f"Expected standpipe area {tank_area_ft2:.1f} ft^2 to suppress cavitation at the protected node, got {cav_steps} cavitating steps"
    )


def test_standpipe_tank_size_sweep_is_monotonic(standpipe_area_data):
    """Increasing standpipe area should monotonically reduce the protected-node closure peak."""
    ordered_areas = [1.0, 2.0, 5.0, 10.0, 20.0]
    ordered_peaks = [
        float(np.max(np.asarray(standpipe_area_data[area]["node_head"]["SP1"])))
        for area in ordered_areas
    ]

    assert all(lhs > rhs for lhs, rhs in zip(ordered_peaks, ordered_peaks[1:])), (
        f"Expected larger standpipe areas to reduce the closure peak monotonically, got peaks {ordered_peaks} for areas {ordered_areas}"
    )
    assert ordered_peaks[0] - ordered_peaks[-1] >= 10.0, (
        f"Expected the largest standpipe to cut at least 10 ft from the smallest-area case, got {ordered_peaks[0] - ordered_peaks[-1]:.2f} ft"
    )
