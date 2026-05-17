# Copyright (c) 2026 Jason Lillywhite <jason@lillywhitewater.com>
# SPDX-License-Identifier: MIT
# Author: Jason Lillywhite <jason@lillywhitewater.com>
"""
rthym_moc – 1-D Method of Characteristics transient hydraulic solver.

Quick-start
-----------
>>> import rthym_moc
>>> solver = rthym_moc.MOCSolver()
>>>
>>> # Reservoir → pipe → junction → pipe → valve → reservoir
>>> solver.add_node(rthym_moc.NodeInput(id="R1", type="Tank",
...                                      elevation=0.0, head=150.0))
>>> solver.add_node(rthym_moc.NodeInput(id="J1", type="Junction",
...                                      elevation=0.0, demand=0.0))
>>> solver.add_node(rthym_moc.NodeInput(id="V1", type="Valve",
...                                      elevation=0.0, diameter=12.0,
...                                      current_setting=100.0))
>>> solver.add_node(rthym_moc.NodeInput(id="R2", type="Tank",
...                                      elevation=0.0, head=0.0))
>>>
>>> solver.add_pipe(rthym_moc.PipeInput(id="P1", from_node="R1", to_node="J1",
...                                      length=3000.0, diameter=12.0,
...                                      roughness=130.0, flow_gpm=500.0))
>>> solver.add_pipe(rthym_moc.PipeInput(id="P2", from_node="J1", to_node="V1",
...                                      length=500.0, diameter=12.0,
...                                      roughness=130.0, flow_gpm=500.0))
>>> solver.add_pipe(rthym_moc.PipeInput(id="P3", from_node="V1", to_node="R2",
...                                      length=100.0, diameter=12.0,
...                                      roughness=130.0, flow_gpm=500.0))
>>>
>>> results = solver.run(total_time=5.0, dt=0.01)
>>> import numpy as np
>>> time = results["time"]
>>> head_J1 = results["node_head"]["J1"]   # head time series at junction (ft)
"""

from ._rthym_moc import (
    MOCSolver,
    NodeInput,
    PipeInput,
    G_FT_S2,
    GPM_TO_CFS,
    PSI_TO_FT,
)
from .epanet import load_inp

__all__ = [
    "MOCSolver",
    "NodeInput",
    "PipeInput",
    "G_FT_S2",
    "GPM_TO_CFS",
    "PSI_TO_FT",
    "load_inp",
]

__version__ = "0.1.0"
