# Copyright (c) 2026 Jason Lillywhite <jason@lillywhitewater.com>
# SPDX-License-Identifier: MIT
"""Attach AirValve nodes at a chainage along an uninterrupted pipe reach (Phase 5).

Implements roadmap Option A: split the pipe topologically at the chainage and
insert an ``AirValve`` junction node reusing the existing compressible air model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ._rthym_moc import MOCSolver, NodeInput, PipeInput


def _survey_z_ft(
    chainage_ft: float,
    profile: list[tuple[float, float]],
) -> float:
    ordered = sorted(profile, key=lambda pair: pair[0])
    if chainage_ft <= ordered[0][0]:
        return ordered[0][1]
    if chainage_ft >= ordered[-1][0]:
        return ordered[-1][1]
    for (x0, z0), (x1, z1) in zip(ordered, ordered[1:]):
        if chainage_ft <= x1:
            if abs(x1 - x0) < 1e-12:
                return z0
            frac = (chainage_ft - x0) / (x1 - x0)
            return z0 + frac * (z1 - z0)
    return ordered[-1][1]


def elevation_at_chainage_ft(
    pipe: PipeInput,
    nodes: Mapping[str, NodeInput],
    chainage_ft: float,
) -> float:
    """Ground elevation at ``chainage_ft`` from survey table or endpoint interpolation."""
    if pipe.elevation_profile:
        return _survey_z_ft(chainage_ft, list(pipe.elevation_profile))
    z_from = float(nodes[pipe.from_node].elevation)
    z_to = float(nodes[pipe.to_node].elevation)
    if pipe.length <= 0.0:
        return z_from
    frac = chainage_ft / pipe.length
    return z_from + frac * (z_to - z_from)


def head_at_chainage_ft(
    pipe: PipeInput,
    nodes: Mapping[str, NodeInput],
    chainage_ft: float,
) -> float:
    """Initial piezometric head at ``chainage_ft`` (linear between endpoint node heads)."""
    h_from = float(nodes[pipe.from_node].head)
    h_to = float(nodes[pipe.to_node].head)
    if pipe.length <= 0.0:
        return h_from
    frac = chainage_ft / pipe.length
    return h_from + frac * (h_to - h_from)


def survey_high_point_chainage_ft(
    pipe: PipeInput,
    nodes: Mapping[str, NodeInput],
) -> float:
    """Return chainage (ft from ``from_node``) of the survey or endpoint high point."""
    if pipe.elevation_profile:
        summit = max(pipe.elevation_profile, key=lambda pair: pair[1])
        return float(summit[0])
    z_from = float(nodes[pipe.from_node].elevation)
    z_to = float(nodes[pipe.to_node].elevation)
    return 0.0 if z_from >= z_to else float(pipe.length)


def _split_elevation_profile(
    profile: list[tuple[float, float]],
    chainage_ft: float,
    z_at: float,
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    if not profile:
        return [], []

    ordered = sorted(profile, key=lambda pair: pair[0])
    upstream: list[tuple[float, float]] = [
        (chainage, elevation) for chainage, elevation in ordered if chainage <= chainage_ft
    ]
    if not upstream or upstream[-1][0] < chainage_ft - 1e-9:
        upstream.append((chainage_ft, z_at))

    downstream: list[tuple[float, float]] = [
        (chainage - chainage_ft, elevation)
        for chainage, elevation in ordered
        if chainage >= chainage_ft
    ]
    if not downstream or downstream[0][0] > 1e-9:
        downstream.insert(0, (0.0, z_at))
    return upstream, downstream


def _copy_pipe(pipe: PipeInput) -> PipeInput:
    out = PipeInput()
    out.id = pipe.id
    out.from_node = pipe.from_node
    out.to_node = pipe.to_node
    out.length = pipe.length
    out.diameter = pipe.diameter
    out.roughness = pipe.roughness
    out.minor_loss = pipe.minor_loss
    out.flow_gpm = pipe.flow_gpm
    out.wall_thickness = pipe.wall_thickness
    out.youngs_modulus = pipe.youngs_modulus
    out.poissons_ratio = pipe.poissons_ratio
    out.elevation_profile = list(pipe.elevation_profile)
    out.interior_dvcm_chainages_ft = list(pipe.interior_dvcm_chainages_ft)
    return out


def _make_air_valve_node(
    node_id: str,
    *,
    elevation_ft: float,
    head_ft: float,
    air_valve_kwargs: Mapping[str, Any],
) -> NodeInput:
    node = NodeInput()
    node.id = node_id
    node.type = "AirValve"
    node.elevation = float(elevation_ft)
    node.head = float(head_ft)
    node.diameter = float(air_valve_kwargs.get("diameter", 6.0))
    node.air_release_diameter = float(air_valve_kwargs.get("air_release_diameter", 0.25))
    node.air_release_head = float(air_valve_kwargs.get("air_release_head", 0.0))
    node.gas_volume = float(air_valve_kwargs.get("gas_volume", 0.05))
    node.tank_volume = float(air_valve_kwargs.get("tank_volume", 2.0))
    node.loss_coeff_in = float(air_valve_kwargs.get("loss_coeff_in", 0.8))
    node.loss_coeff_out = float(air_valve_kwargs.get("loss_coeff_out", 0.7))
    return node


@dataclass
class SplitPipeAtChainageResult:
    upstream_pipe: PipeInput
    downstream_pipe: PipeInput
    valve_node: NodeInput
    chainage_ft: float


def split_pipe_at_chainage(
    pipe: PipeInput,
    nodes: Mapping[str, NodeInput],
    chainage_ft: float,
    *,
    valve_node_id: str,
    upstream_pipe_id: str | None = None,
    downstream_pipe_id: str | None = None,
    air_valve_kwargs: Mapping[str, Any] | None = None,
) -> SplitPipeAtChainageResult:
    """Split one pipe into upstream/downstream reaches with an AirValve junction."""
    if pipe.from_node not in nodes:
        raise ValueError(f"Unknown from_node '{pipe.from_node}' for pipe '{pipe.id}'")
    if pipe.to_node not in nodes:
        raise ValueError(f"Unknown to_node '{pipe.to_node}' for pipe '{pipe.id}'")
    if chainage_ft <= 0.0 or chainage_ft >= pipe.length:
        raise ValueError(
            f"chainage_ft must lie strictly inside (0, {pipe.length}) for pipe '{pipe.id}'"
        )
    if valve_node_id in {pipe.from_node, pipe.to_node}:
        raise ValueError(
            f"valve_node_id '{valve_node_id}' must differ from pipe endpoints"
        )
    if valve_node_id in nodes:
        raise ValueError(f"Node id '{valve_node_id}' already exists")

    length_upstream = chainage_ft
    length_downstream = pipe.length - chainage_ft
    z_at = elevation_at_chainage_ft(pipe, nodes, chainage_ft)
    h_at = head_at_chainage_ft(pipe, nodes, chainage_ft)

    upstream = _copy_pipe(pipe)
    upstream.id = upstream_pipe_id or f"{pipe.id}_up"
    upstream.from_node = pipe.from_node
    upstream.to_node = valve_node_id
    upstream.length = length_upstream
    up_profile, dn_profile = _split_elevation_profile(
        list(pipe.elevation_profile),
        chainage_ft,
        z_at,
    )
    upstream.elevation_profile = up_profile
    upstream.interior_dvcm_chainages_ft = [
        chainage for chainage in pipe.interior_dvcm_chainages_ft if chainage < chainage_ft
    ]

    downstream = _copy_pipe(pipe)
    downstream.id = downstream_pipe_id or f"{pipe.id}_dn"
    downstream.from_node = valve_node_id
    downstream.to_node = pipe.to_node
    downstream.length = length_downstream
    downstream.elevation_profile = dn_profile
    downstream.interior_dvcm_chainages_ft = [
        chainage - chainage_ft
        for chainage in pipe.interior_dvcm_chainages_ft
        if chainage > chainage_ft
    ]

    valve = _make_air_valve_node(
        valve_node_id,
        elevation_ft=z_at,
        head_ft=h_at,
        air_valve_kwargs=air_valve_kwargs or {},
    )
    return SplitPipeAtChainageResult(
        upstream_pipe=upstream,
        downstream_pipe=downstream,
        valve_node=valve,
        chainage_ft=chainage_ft,
    )


@dataclass
class PipeNetwork:
    """Mutable node/pipe registry for topology helpers before ``MOCSolver.run()``."""

    nodes: dict[str, NodeInput] = field(default_factory=dict)
    pipes: dict[str, PipeInput] = field(default_factory=dict)

    def add_node(self, node: NodeInput) -> None:
        if node.id in self.nodes:
            raise ValueError(f"Duplicate node id '{node.id}'")
        self.nodes[node.id] = node

    def add_pipe(self, pipe: PipeInput) -> None:
        if pipe.id in self.pipes:
            raise ValueError(f"Duplicate pipe id '{pipe.id}'")
        if pipe.from_node not in self.nodes:
            raise ValueError(f"Unknown from_node '{pipe.from_node}' for pipe '{pipe.id}'")
        if pipe.to_node not in self.nodes:
            raise ValueError(f"Unknown to_node '{pipe.to_node}' for pipe '{pipe.id}'")
        self.pipes[pipe.id] = pipe

    def apply_to(self, solver: MOCSolver) -> None:
        solver.clear()
        for node in self.nodes.values():
            solver.add_node(node)
        for pipe in self.pipes.values():
            solver.add_pipe(pipe)


def attach_air_valve_at_chainage(
    network: PipeNetwork,
    pipe_id: str,
    chainage_ft: float,
    *,
    valve_node_id: str | None = None,
    upstream_pipe_id: str | None = None,
    downstream_pipe_id: str | None = None,
    **air_valve_kwargs: Any,
) -> str:
    """Split ``pipe_id`` at ``chainage_ft`` and insert an ``AirValve`` node.

    Returns the air-valve node id.
    """
    if pipe_id not in network.pipes:
        raise ValueError(f"Unknown pipe id '{pipe_id}'")
    pipe = network.pipes[pipe_id]
    valve_id = valve_node_id or f"{pipe_id}_av_{int(round(chainage_ft))}"
    split = split_pipe_at_chainage(
        pipe,
        network.nodes,
        chainage_ft,
        valve_node_id=valve_id,
        upstream_pipe_id=upstream_pipe_id,
        downstream_pipe_id=downstream_pipe_id,
        air_valve_kwargs=air_valve_kwargs,
    )
    del network.pipes[pipe_id]
    network.nodes[split.valve_node.id] = split.valve_node
    network.pipes[split.upstream_pipe.id] = split.upstream_pipe
    network.pipes[split.downstream_pipe.id] = split.downstream_pipe
    return valve_id


def attach_air_valve_at_survey_high_point(
    network: PipeNetwork,
    pipe_id: str,
    *,
    valve_node_id: str | None = None,
    upstream_pipe_id: str | None = None,
    downstream_pipe_id: str | None = None,
    **air_valve_kwargs: Any,
) -> tuple[str, float]:
    """Attach an air valve at the survey or endpoint high point on ``pipe_id``.

    Returns ``(valve_node_id, chainage_ft)``.
    """
    if pipe_id not in network.pipes:
        raise ValueError(f"Unknown pipe id '{pipe_id}'")
    chainage_ft = survey_high_point_chainage_ft(network.pipes[pipe_id], network.nodes)
    if chainage_ft <= 0.0 or chainage_ft >= network.pipes[pipe_id].length:
        raise ValueError(
            f"High point on pipe '{pipe_id}' lies at an endpoint (chainage={chainage_ft} ft); "
            "attach the air valve to the endpoint node instead."
        )
    valve_id = attach_air_valve_at_chainage(
        network,
        pipe_id,
        chainage_ft,
        valve_node_id=valve_node_id,
        upstream_pipe_id=upstream_pipe_id,
        downstream_pipe_id=downstream_pipe_id,
        **air_valve_kwargs,
    )
    return valve_id, chainage_ft
