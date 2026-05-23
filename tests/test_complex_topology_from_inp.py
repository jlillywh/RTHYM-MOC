"""Complex topology regression using an INP-defined network and pump-trip event.

The first 30 tests in this module compare the solver's pre-trip operating point
against an EPANET steady-state reference for the recovered complex-topology INP.
That restores the previously skipped 13 node-head and 17 pipe-flow checks
without depending on pre-generated CSV artifacts.

The final two tests assert the transient response of the Pump_A trip itself.
"""

from pathlib import Path

import numpy as np
import pytest
import rthym_moc

wntr = pytest.importorskip("wntr", reason="wntr is required for INP benchmark tests")

NETWORK_PATH = Path(__file__).resolve().parent / "networks" / "complex_topology.inp"

DT_S = 0.01
TOTAL_TIME_S = 12.0
PUMP_TRIP_TIME_S = 10.0
PRETRIP_START_S = 0.1
PRETRIP_END_S = 0.5
POSTTRIP_START_S = 10.2
POSTTRIP_END_S = 10.8

# This network includes tanks, a pump, and inline valve expansion stubs.
# After seeding tanks from the imported steady-state head, the pre-trip slice
# tracks EPANET within about 0.21 ft and 0.24 GPM on this fixture.
TOL_HEAD_FT = 0.5
TOL_FLOW_GPM = 0.5

HEAD_NODES = [
    "Junction_A",
    "Junction_B",
    "Junction_C",
    "Junction_D",
    "Junction_E",
    "Junction_F",
    "Valve_A_in",
    "Valve_A_out",
    "Valve_B_in",
    "Valve_B_out",
    "OutflowNode_A",
    "OutflowNode_B",
    "OutflowNode_C",
]

FLOW_PIPES = [
    "Pipe_1",
    "Pipe_2",
    "Pipe_3",
    "Pipe_4",
    "Pipe_5",
    "Pipe_6",
    "Pipe_7",
    "Pipe_8",
    "Pipe_9",
    "Pipe_10",
    "Pipe_11",
    "Pipe_12",
    "Pipe_13",
    "Pipe_14",
    "Pipe_15",
    "Pipe_16",
    "Pipe_17",
]


def _mean_over_window(time_s, values, start_s, end_s):
    mask = (time_s >= start_s) & (time_s <= end_s)
    assert np.any(mask), f"No samples found in window [{start_s}, {end_s}] s"
    return float(np.asarray(values)[mask].mean())


@pytest.fixture(scope="module")
def data():
    wn = wntr.network.WaterNetworkModel(str(NETWORK_PATH))
    ref_results = wntr.sim.EpanetSimulator(wn).run_sim()
    heads_ref_ft = {
        str(node_id): float(head_m) / 0.3048
        for node_id, head_m in ref_results.node["head"].iloc[0].items()
    }
    flows_ref_gpm = {
        str(link_id): float(flow_m3s) * 15850.3
        for link_id, flow_m3s in ref_results.link["flowrate"].iloc[0].items()
    }

    solver = rthym_moc.load_inp(str(NETWORK_PATH), use_wntr=True)
    solver.set_pump_schedule(
        "_PUMP_Pump_A",
        [
            (0.0, 100.0),
            (PUMP_TRIP_TIME_S - DT_S, 100.0),
            (PUMP_TRIP_TIME_S, 0.0),
            (TOTAL_TIME_S, 0.0),
        ],
    )
    results = solver.run(total_time=TOTAL_TIME_S, dt=DT_S)

    return {
        "time_s": np.asarray(results["time"]),
        "heads_ref_ft": heads_ref_ft,
        "flows_ref_gpm": flows_ref_gpm,
        "node_head": results["node_head"],
        "pipe_flow_gpm": results["pipe_flow_gpm"],
    }


@pytest.mark.parametrize("node", HEAD_NODES)
def test_junction_head_pretrip(data, node):
    """Pre-trip complex-topology heads stay near the EPANET operating point."""
    sim_head_ft = _mean_over_window(
        data["time_s"],
        data["node_head"][node],
        PRETRIP_START_S,
        PRETRIP_END_S,
    )
    ref_head_ft = data["heads_ref_ft"][node]
    diff_ft = abs(sim_head_ft - ref_head_ft)
    assert diff_ft <= TOL_HEAD_FT, (
        f"{node}: pre-trip head diff {diff_ft:.2f} ft exceeds {TOL_HEAD_FT:.1f} ft "
        f"(sim={sim_head_ft:.2f} ft, ref={ref_head_ft:.2f} ft)"
    )


@pytest.mark.parametrize("pipe", FLOW_PIPES)
def test_pipe_flow_pretrip(data, pipe):
    """Pre-trip complex-topology flows stay near the EPANET operating point."""
    sim_flow_gpm = _mean_over_window(
        data["time_s"],
        data["pipe_flow_gpm"][pipe],
        PRETRIP_START_S,
        PRETRIP_END_S,
    )
    ref_flow_gpm = data["flows_ref_gpm"][pipe]
    diff_gpm = abs(sim_flow_gpm - ref_flow_gpm)
    assert diff_gpm <= TOL_FLOW_GPM, (
        f"{pipe}: pre-trip flow diff {diff_gpm:.2f} GPM exceeds {TOL_FLOW_GPM:.1f} GPM "
        f"(sim={sim_flow_gpm:.2f} GPM, ref={ref_flow_gpm:.2f} GPM)"
    )


def test_pump_trip_drops_junction_e_head(data):
    """Turning Pump_A off should substantially reduce head at Junction_E."""
    pretrip_head_ft = _mean_over_window(
        data["time_s"],
        data["node_head"]["Junction_E"],
        PRETRIP_START_S,
        PRETRIP_END_S,
    )
    posttrip_head_ft = _mean_over_window(
        data["time_s"],
        data["node_head"]["Junction_E"],
        POSTTRIP_START_S,
        POSTTRIP_END_S,
    )
    drop_ft = pretrip_head_ft - posttrip_head_ft
    assert drop_ft >= 50.0, (
        f"Pump trip should drop Junction_E head by at least 50 ft, got {drop_ft:.2f} ft "
        f"(pre={pretrip_head_ft:.2f} ft, post={posttrip_head_ft:.2f} ft)"
    )


def test_pump_trip_reverses_suction_pipe_flow(data):
    """After Pump_A trips, the suction-side pipe should reverse direction."""
    pretrip_flow_gpm = _mean_over_window(
        data["time_s"],
        data["pipe_flow_gpm"]["Pipe_8"],
        PRETRIP_START_S,
        PRETRIP_END_S,
    )
    posttrip_flow_gpm = _mean_over_window(
        data["time_s"],
        data["pipe_flow_gpm"]["Pipe_8"],
        POSTTRIP_START_S,
        POSTTRIP_END_S,
    )
    assert pretrip_flow_gpm > 0.0, f"Expected pre-trip Pipe_8 flow to be positive, got {pretrip_flow_gpm:.2f} GPM"
    assert posttrip_flow_gpm < 0.0, f"Expected post-trip Pipe_8 flow to reverse, got {posttrip_flow_gpm:.2f} GPM"
