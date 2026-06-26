"""EPANET steady-state + pump-trip checks for complex_topology.inp (tests + notebook)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rthym_moc

try:
    import wntr
except ImportError:
    wntr = None  # type: ignore[assignment]

NETWORK_PATH = Path(__file__).resolve().parent / "networks" / "complex_topology.inp"

DT_S = 0.01
TOTAL_TIME_S = 12.0
PUMP_TRIP_TIME_S = 10.0
PRETRIP_START_S = 0.1
PRETRIP_END_S = 0.5
POSTTRIP_START_S = 10.2
POSTTRIP_END_S = 10.8

TOL_HEAD_FT = 20.0
TOL_FLOW_GPM = 70.0

HEAD_NODES = [
    "Junction_A", "Junction_B", "Junction_C", "Junction_D", "Junction_E", "Junction_F",
    "Valve_A_in", "Valve_A_out", "Valve_B_in", "Valve_B_out",
    "OutflowNode_A", "OutflowNode_B", "OutflowNode_C",
]

FLOW_PIPES = [f"Pipe_{i}" for i in range(1, 18)]


def mean_over_window(time_s, values, start_s: float, end_s: float) -> float:
    mask = (np.asarray(time_s) >= start_s) & (np.asarray(time_s) <= end_s)
    if not np.any(mask):
        raise ValueError(f"No samples in [{start_s}, {end_s}] s")
    return float(np.asarray(values)[mask].mean())


def load_epanet_steady_state():
    if wntr is None:
        raise ImportError("wntr is required; install with: pip install wntr")
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
    return heads_ref_ft, flows_ref_gpm


def run_pump_trip_transient() -> dict:
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
    return solver.run(total_time=TOTAL_TIME_S, dt=DT_S)


@dataclass(frozen=True)
class PretripMetric:
    id: str
    kind: str
    sim_mean: float
    ref_mean: float
    error: float
    passed: bool


@dataclass(frozen=True)
class TripCheck:
    name: str
    value: float
    passed: bool
    detail: str


@dataclass(frozen=True)
class ComplexTopologyBundle:
    heads_ref_ft: dict[str, float]
    flows_ref_gpm: dict[str, float]
    time_s: np.ndarray
    node_head: dict
    pipe_flow_gpm: dict
    pretrip_head_metrics: list[PretripMetric]
    pretrip_flow_metrics: list[PretripMetric]
    trip_checks: list[TripCheck]


def evaluate_complex_topology() -> ComplexTopologyBundle:
    heads_ref_ft, flows_ref_gpm = load_epanet_steady_state()
    results = run_pump_trip_transient()
    time_s = np.asarray(results["time"], dtype=float)

    pretrip_heads = []
    for node in HEAD_NODES:
        sim = mean_over_window(time_s, results["node_head"][node], PRETRIP_START_S, PRETRIP_END_S)
        ref = heads_ref_ft[node]
        err = abs(sim - ref)
        pretrip_heads.append(PretripMetric(node, "head", sim, ref, err, err <= TOL_HEAD_FT))

    pretrip_flows = []
    for pipe in FLOW_PIPES:
        sim = mean_over_window(time_s, results["pipe_flow_gpm"][pipe], PRETRIP_START_S, PRETRIP_END_S)
        ref = flows_ref_gpm[pipe]
        err = abs(sim - ref)
        pretrip_flows.append(PretripMetric(pipe, "flow", sim, ref, err, err <= TOL_FLOW_GPM))

    pretrip_e = mean_over_window(time_s, results["node_head"]["Junction_E"], PRETRIP_START_S, PRETRIP_END_S)
    posttrip_e = mean_over_window(time_s, results["node_head"]["Junction_E"], POSTTRIP_START_S, POSTTRIP_END_S)
    drop_e = pretrip_e - posttrip_e

    pretrip_p8 = mean_over_window(time_s, results["pipe_flow_gpm"]["Pipe_8"], PRETRIP_START_S, PRETRIP_END_S)
    posttrip_p8 = mean_over_window(time_s, results["pipe_flow_gpm"]["Pipe_8"], POSTTRIP_START_S, POSTTRIP_END_S)

    trip_checks = [
        TripCheck("Junction_E head drop", drop_e, drop_e >= 50.0, f"pre={pretrip_e:.1f} ft post={posttrip_e:.1f} ft"),
        TripCheck("Pipe_8 flow decay", pretrip_p8 - posttrip_p8, pretrip_p8 > 0.0 and posttrip_p8 < pretrip_p8 - 50.0, f"pre={pretrip_p8:.1f} post={posttrip_p8:.1f} GPM"),
    ]

    return ComplexTopologyBundle(
        heads_ref_ft=heads_ref_ft,
        flows_ref_gpm=flows_ref_gpm,
        time_s=time_s,
        node_head=results["node_head"],
        pipe_flow_gpm=results["pipe_flow_gpm"],
        pretrip_head_metrics=pretrip_heads,
        pretrip_flow_metrics=pretrip_flows,
        trip_checks=trip_checks,
    )
