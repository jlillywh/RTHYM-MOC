from __future__ import annotations

from typing import TypedDict

import numpy as np
from numpy.typing import NDArray


class SimResultsDict(TypedDict):
    time: NDArray[np.float64]
    node_head: dict[str, NDArray[np.float64]]
    node_pressure: dict[str, NDArray[np.float64]]
    node_cavitation: dict[str, NDArray[np.int_]]
    pipe_flow_gpm: dict[str, NDArray[np.float64]]
    valve_position: dict[str, NDArray[np.float64]]
    valve_velocity: dict[str, NDArray[np.float64]]
    pump_speed: dict[str, NDArray[np.float64]]


class NodeInput:
    id: str
    type: str
    elevation: float
    head: float
    level: float
    max_level: float
    demand: float
    current_speed: float
    has_power: bool
    current_setting: float
    design_head: float
    design_flow: float
    diameter: float
    air_release_head: float
    air_release_diameter: float
    design_velocity: float
    tank_area: float
    gas_volume: float
    tank_volume: float
    polytropic_n: float
    loss_coeff_in: float
    loss_coeff_out: float
    closure_time: float
    closure_damping: float
    flipped: bool
    inertia_wr2: float
    speed_rpm: float
    efficiency: float
    ramp_time: float

    def __init__(self) -> None: ...


class PipeInput:
    id: str
    from_node: str
    to_node: str
    length: float
    diameter: float
    roughness: float
    minor_loss: float
    flow_gpm: float
    wall_thickness: float
    youngs_modulus: float
    poissons_ratio: float

    def __init__(self) -> None: ...


class ControlType:
    Threshold: ControlType
    Deadband: ControlType
    PID: ControlType
    PCV: ControlType


class ControlRuleInput:
    id: str
    type: ControlType
    monitored_node: str
    controlled_node: str
    monitored_quantity: str
    monitored_pipe: str
    condition: str
    threshold: float
    target: float
    deadband: float
    action: str
    kp: float
    ki: float
    kd: float

    def __init__(self) -> None: ...


class MOCSolver:
    def __init__(self) -> None: ...
    def add_node(self, node: NodeInput) -> None: ...
    def add_pipe(self, pipe: PipeInput) -> None: ...
    def clear(self) -> None: ...
    def add_control_rule(self, rule: ControlRuleInput) -> None: ...
    def clear_control_rules(self) -> None: ...
    def get_node_head(self, id: str) -> float: ...
    def get_node_pressure(self, id: str) -> float: ...
    def set_valve_setting(self, id: str, pct_open: float) -> None: ...
    def set_pump_speed(self, id: str, pct_speed: float) -> None: ...
    def set_pump_power(self, id: str, has_power: bool) -> None: ...
    def set_node_demand(self, id: str, demand_gpm: float) -> None: ...
    def set_node_head(self, id: str, head_ft: float) -> None: ...
    def set_valve_schedule(self, id: str, schedule: list[tuple[float, float]]) -> None: ...
    def set_pump_schedule(self, id: str, schedule: list[tuple[float, float]]) -> None: ...
    def set_demand_schedule(self, id: str, schedule: list[tuple[float, float]]) -> None: ...
    def set_head_schedule(self, id: str, schedule: list[tuple[float, float]]) -> None: ...
    def run(
        self,
        total_time: float,
        dt: float = 0.01,
        p_vapor_psi: float = -14.0,
        usf_tau: float = 0.5,
        k_bru: float = -1.0,
    ) -> SimResultsDict: ...


G_FT_S2: float
GPM_TO_CFS: float
PSI_TO_FT: float