"""Surge design-rule parameter sweeps (tests + notebook)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import rthym_moc as m

DT_S = 0.01
TOTAL_TIME_S = 12.0
TRIP_START_S = 5.2
TRIP_END_S = 6.0
HEAD_BOUND_TOL_FT = 1.0
PLACEMENT_TRIP_FLOORS_FT = {40.0: 180.0, 120.0: 100.0, 300.0: -5.0, 600.0: -20.0}

STANDPIPE_AREA_CASES: tuple[tuple[float, float], ...] = (
    (1.0, 160.0),
    (2.0, 154.0),
    (5.0, 150.0),
    (10.0, 148.0),
    (20.0, 147.0),
)

PLACEMENT_DISTANCES_FT = (40.0, 120.0, 300.0, 600.0)


def _make_node(node_id, node_type, **kwargs):
    node = m.NodeInput()
    node.id, node.type = node_id, node_type
    for key, value in kwargs.items():
        setattr(node, key, value)
    return node


def _make_pipe(pipe_id, from_node, to_node, length_ft, flow_gpm=500.0):
    pipe = m.PipeInput()
    pipe.id, pipe.from_node, pipe.to_node = pipe_id, from_node, to_node
    pipe.length, pipe.diameter, pipe.roughness, pipe.flow_gpm = length_ft, 12.0, 130.0, flow_gpm
    return pipe


def run_standpipe_area_case(tank_area_ft2: float) -> dict:
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=150.0))
    solver.add_node(_make_node("SP1", "Standpipe", head=145.8, tank_area=tank_area_ft2))
    solver.add_node(_make_node("Valve_A", "Valve", diameter=12.0, current_setting=100.0, head=145.8))
    solver.add_node(_make_node("R2", "PressureBoundary", head=145.8))
    solver.add_pipe(_make_pipe("P1", "R1", "SP1", 3000.0))
    solver.add_pipe(_make_pipe("P2", "SP1", "Valve_A", 40.0))
    solver.add_pipe(_make_pipe("P3", "Valve_A", "R2", 40.0, flow_gpm=0.0))
    solver.set_valve_schedule("Valve_A", [(0.0, 100.0), (DT_S, 0.0), (TOTAL_TIME_S, 0.0)])
    return solver.run(total_time=TOTAL_TIME_S, dt=DT_S)


@dataclass(frozen=True)
class StandpipeSweepPoint:
    area_ft2: float
    peak_limit_ft: float
    peak_head_ft: float
    cavitation_steps: int
    passed: bool


def evaluate_standpipe_sweep() -> list[StandpipeSweepPoint]:
    points = []
    for area, limit in STANDPIPE_AREA_CASES:
        data = run_standpipe_area_case(area)
        peak = float(np.max(np.asarray(data["node_head"]["SP1"])))
        cav = int(np.asarray(data["node_cavity_active"]["SP1"]).sum())
        points.append(
            StandpipeSweepPoint(
                area_ft2=area,
                peak_limit_ft=limit,
                peak_head_ft=peak,
                cavitation_steps=cav,
                passed=peak <= limit and cav == 0,
            )
        )
    return points


def standpipe_sweep_monotonic(points: list[StandpipeSweepPoint]) -> bool:
    peaks = [p.peak_head_ft for p in sorted(points, key=lambda x: x.area_ft2)]
    return all(peaks[i] >= peaks[i + 1] for i in range(len(peaks) - 1))


def run_hpt_placement_case(distance_ft: float, vessel_ft3: float = 10.0) -> dict:
    """Pump-trip geometry with hydropneumatic vessel at ``distance_ft`` from pump."""
    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", head=200.0))
    solver.add_node(_make_node("Pump_A", "Pump", head=220.0))
    solver.add_node(_make_node("J1", "Junction", head=220.0))
    solver.add_node(
        _make_node(
            "HPT1",
            "HydropneumaticTank",
            head=215.0,
            tank_volume=vessel_ft3,
            gas_volume=0.4 * vessel_ft3,
            diameter=4.0,
            polytropic_n=1.2,
            loss_coeff_in=0.7,
            loss_coeff_out=0.7,
        )
    )
    solver.add_node(_make_node("R2", "PressureBoundary", head=180.0))
    solver.add_pipe(_make_pipe("P1", "R1", "Pump_A", distance_ft))
    solver.add_pipe(_make_pipe("P2", "Pump_A", "J1", 40.0))
    solver.add_pipe(_make_pipe("P3", "J1", "HPT1", 40.0))
    solver.add_pipe(_make_pipe("P4", "HPT1", "R2", 500.0, flow_gpm=0.0))
    solver.set_pump_schedule(
        "Pump_A",
        [(0.0, 100.0), (4.99, 100.0), (5.0, 0.0), (TOTAL_TIME_S, 0.0)],
    )
    return solver.run(total_time=TOTAL_TIME_S, dt=DT_S)


@dataclass(frozen=True)
class PlacementSweepPoint:
    distance_ft: float
    trip_mean_head_ft: float
    trip_head_floor_ft: float
    passed: bool


def evaluate_placement_sweep() -> list[PlacementSweepPoint]:
    out = []
    for dist in PLACEMENT_DISTANCES_FT:
        data = run_hpt_placement_case(dist)
        t = np.asarray(data["time"], dtype=float)
        heads = np.asarray(data["node_head"]["J1"], dtype=float)
        trip_mask = (t >= TRIP_START_S) & (t <= TRIP_END_S)
        trip_mean = float(np.mean(heads[trip_mask]))
        floor = PLACEMENT_TRIP_FLOORS_FT[dist]
        out.append(
            PlacementSweepPoint(
                distance_ft=dist,
                trip_mean_head_ft=trip_mean,
                trip_head_floor_ft=floor,
                passed=trip_mean >= floor - HEAD_BOUND_TOL_FT,
            )
        )
    return out
