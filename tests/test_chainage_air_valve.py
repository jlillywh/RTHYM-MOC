"""Phase 5: chainage air-valve attachment API."""

from __future__ import annotations

import pytest

import rthym_moc as m
from rthym_moc.chainage_air_valve import (
    PipeNetwork,
    attach_air_valve_at_chainage,
    attach_air_valve_at_survey_high_point,
    elevation_at_chainage_ft,
    head_at_chainage_ft,
    split_pipe_at_chainage,
    survey_high_point_chainage_ft,
)


def _make_node(node_id: str, node_type: str, **kwargs) -> m.NodeInput:
    node = m.NodeInput()
    node.id = node_id
    node.type = node_type
    for key, value in kwargs.items():
        setattr(node, key, value)
    return node


def _make_pipe(pipe_id: str, from_node: str, to_node: str, **kwargs) -> m.PipeInput:
    pipe = m.PipeInput()
    pipe.id = pipe_id
    pipe.from_node = from_node
    pipe.to_node = to_node
    for key, value in kwargs.items():
        setattr(pipe, key, value)
    return pipe


def _sloping_network() -> PipeNetwork:
    length_ft = 2000.0
    survey = [(0.0, 100.0), (1000.0, 280.0), (length_ft, 120.0)]
    net = PipeNetwork()
    net.add_node(_make_node("R1", "PressureBoundary", elevation=100.0, head=320.0))
    net.add_node(_make_node("R2", "PressureBoundary", elevation=120.0, head=320.0))
    pipe = _make_pipe(
        "P1",
        "R1",
        "R2",
        length=length_ft,
        diameter=12.0,
        roughness=130.0,
        flow_gpm=0.0,
    )
    pipe.elevation_profile = survey
    pipe.interior_dvcm_chainages_ft = [500.0, 1500.0]
    net.add_pipe(pipe)
    return net


def test_survey_high_point_chainage_finds_summit() -> None:
    net = _sloping_network()
    assert survey_high_point_chainage_ft(net.pipes["P1"], net.nodes) == pytest.approx(1000.0)


def test_elevation_and_head_at_chainage_use_survey() -> None:
    net = _sloping_network()
    pipe = net.pipes["P1"]
    assert elevation_at_chainage_ft(pipe, net.nodes, 1000.0) == pytest.approx(280.0)
    assert head_at_chainage_ft(pipe, net.nodes, 1000.0) == pytest.approx(320.0)


def test_split_pipe_at_chainage_preserves_reach_lengths() -> None:
    net = _sloping_network()
    split = split_pipe_at_chainage(
        net.pipes["P1"],
        net.nodes,
        800.0,
        valve_node_id="AV1",
    )
    assert split.upstream_pipe.length == pytest.approx(800.0)
    assert split.downstream_pipe.length == pytest.approx(1200.0)
    assert split.upstream_pipe.to_node == "AV1"
    assert split.downstream_pipe.from_node == "AV1"
    assert split.valve_node.type == "AirValve"
    assert split.valve_node.elevation == pytest.approx(
        elevation_at_chainage_ft(net.pipes["P1"], net.nodes, 800.0)
    )


def test_split_pipe_rebases_elevation_profile_and_dvcm_chainages() -> None:
    net = _sloping_network()
    split = split_pipe_at_chainage(
        net.pipes["P1"],
        net.nodes,
        1000.0,
        valve_node_id="AV1",
    )
    assert split.upstream_pipe.elevation_profile[-1][0] == pytest.approx(1000.0)
    assert split.downstream_pipe.elevation_profile[0][0] == pytest.approx(0.0)
    assert split.upstream_pipe.interior_dvcm_chainages_ft == [500.0]
    assert split.downstream_pipe.interior_dvcm_chainages_ft == [500.0]


def test_attach_air_valve_at_chainage_updates_network() -> None:
    net = _sloping_network()
    valve_id = attach_air_valve_at_chainage(net, "P1", 1000.0, valve_node_id="AV_summit")
    assert valve_id == "AV_summit"
    assert "P1" not in net.pipes
    assert net.nodes["AV_summit"].type == "AirValve"
    assert set(net.pipes) == {"P1_up", "P1_dn"}
    assert net.pipes["P1_up"].length == pytest.approx(1000.0)
    assert net.pipes["P1_dn"].length == pytest.approx(1000.0)


def test_attach_air_valve_at_survey_high_point() -> None:
    net = _sloping_network()
    valve_id, chainage = attach_air_valve_at_survey_high_point(
        net,
        "P1",
        valve_node_id="AV_summit",
    )
    assert valve_id == "AV_summit"
    assert chainage == pytest.approx(1000.0)
    assert net.pipes["P1_up"].to_node == "AV_summit"


def test_network_apply_to_solver_runs() -> None:
    net = _sloping_network()
    attach_air_valve_at_survey_high_point(net, "P1", valve_node_id="AV_summit")
    solver = m.MOCSolver()
    net.apply_to(solver)
    results = solver.run(total_time=0.05, dt=0.01)
    assert "AV_summit" in results["node_head"]
    assert set(results["pipe_flow_gpm"]) == {"P1_up", "P1_dn"}


def test_split_rejects_endpoint_chainage() -> None:
    net = _sloping_network()
    with pytest.raises(ValueError, match="strictly inside"):
        split_pipe_at_chainage(net.pipes["P1"], net.nodes, 0.0, valve_node_id="AV1")


def test_elevation_and_head_without_survey_interpolate_endpoints() -> None:
    nodes = {
        "R1": _make_node("R1", "PressureBoundary", elevation=100.0, head=300.0),
        "R2": _make_node("R2", "PressureBoundary", elevation=200.0, head=400.0),
    }
    pipe = _make_pipe("P1", "R1", "R2", length=1000.0)
    assert elevation_at_chainage_ft(pipe, nodes, 500.0) == pytest.approx(150.0)
    assert head_at_chainage_ft(pipe, nodes, 500.0) == pytest.approx(350.0)


def test_elevation_and_head_zero_length_pipe_use_upstream() -> None:
    nodes = {
        "R1": _make_node("R1", "PressureBoundary", elevation=100.0, head=300.0),
        "R2": _make_node("R2", "PressureBoundary", elevation=200.0, head=400.0),
    }
    pipe = _make_pipe("P1", "R1", "R2", length=0.0)
    assert elevation_at_chainage_ft(pipe, nodes, 0.0) == pytest.approx(100.0)
    assert head_at_chainage_ft(pipe, nodes, 0.0) == pytest.approx(300.0)


def test_survey_high_point_without_profile_uses_endpoint_slopes() -> None:
    nodes_up = {
        "R1": _make_node("R1", "PressureBoundary", elevation=100.0),
        "R2": _make_node("R2", "PressureBoundary", elevation=200.0),
    }
    pipe_up = _make_pipe("P1", "R1", "R2", length=500.0)
    assert survey_high_point_chainage_ft(pipe_up, nodes_up) == pytest.approx(500.0)

    nodes_dn = {
        "R1": _make_node("R1", "PressureBoundary", elevation=200.0),
        "R2": _make_node("R2", "PressureBoundary", elevation=100.0),
    }
    pipe_dn = _make_pipe("P2", "R1", "R2", length=500.0)
    assert survey_high_point_chainage_ft(pipe_dn, nodes_dn) == pytest.approx(0.0)

    nodes_flat = {
        "R1": _make_node("R1", "PressureBoundary", elevation=150.0),
        "R2": _make_node("R2", "PressureBoundary", elevation=150.0),
    }
    pipe_flat = _make_pipe("P3", "R1", "R2", length=500.0)
    assert survey_high_point_chainage_ft(pipe_flat, nodes_flat) == pytest.approx(0.0)


def test_survey_z_clamps_and_handles_degenerate_segments() -> None:
    from rthym_moc.chainage_air_valve import _survey_z_ft

    profile = [(100.0, 50.0), (200.0, 80.0)]
    assert _survey_z_ft(50.0, profile) == pytest.approx(50.0)
    assert _survey_z_ft(250.0, profile) == pytest.approx(80.0)
    assert _survey_z_ft(150.0, profile) == pytest.approx(65.0)
    assert _survey_z_ft(0.0, [(0.0, 10.0), (0.0, 20.0), (100.0, 30.0)]) == pytest.approx(10.0)


def test_survey_z_degenerate_segment(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    from rthym_moc.chainage_air_valve import _survey_z_ft

    profile = [(0.0, 10.0), (50.0, 20.0), (50.0, 30.0), (100.0, 40.0)]
    monkeypatch.setattr(
        builtins,
        "zip",
        lambda _ordered, _rest: iter([((50.0, 20.0), (50.0, 30.0))]),
    )
    assert _survey_z_ft(50.0, profile) == pytest.approx(20.0)


def test_survey_z_fallback_when_no_segment_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    from rthym_moc.chainage_air_valve import _survey_z_ft

    monkeypatch.setattr(builtins, "zip", lambda *_args, **_kwargs: iter([]))
    assert _survey_z_ft(50.0, [(0.0, 10.0), (100.0, 20.0)]) == pytest.approx(20.0)


def test_split_without_elevation_profile_leaves_empty_profiles() -> None:
    net = PipeNetwork()
    net.add_node(_make_node("R1", "PressureBoundary", elevation=100.0, head=320.0))
    net.add_node(_make_node("R2", "PressureBoundary", elevation=120.0, head=320.0))
    pipe = _make_pipe("P1", "R1", "R2", length=1000.0)
    net.add_pipe(pipe)

    split = split_pipe_at_chainage(pipe, net.nodes, 400.0, valve_node_id="AV1")
    assert split.upstream_pipe.elevation_profile == []
    assert split.downstream_pipe.elevation_profile == []


def test_split_rejects_unknown_nodes_and_valve_conflicts() -> None:
    net = _sloping_network()
    pipe = net.pipes["P1"]
    pipe.from_node = "missing"
    with pytest.raises(ValueError, match="Unknown from_node"):
        split_pipe_at_chainage(pipe, net.nodes, 500.0, valve_node_id="AV1")

    pipe.from_node = "R1"
    pipe.to_node = "missing"
    with pytest.raises(ValueError, match="Unknown to_node"):
        split_pipe_at_chainage(pipe, net.nodes, 500.0, valve_node_id="AV1")

    pipe.to_node = "R2"
    with pytest.raises(ValueError, match="must differ from pipe endpoints"):
        split_pipe_at_chainage(pipe, net.nodes, 500.0, valve_node_id="R2")

    net.add_node(_make_node("AV_dup", "AirValve", elevation=200.0, head=320.0))
    with pytest.raises(ValueError, match="already exists"):
        split_pipe_at_chainage(pipe, net.nodes, 500.0, valve_node_id="AV_dup")


def test_pipe_network_rejects_duplicate_and_unknown_ids() -> None:
    net = PipeNetwork()
    node = _make_node("R1", "PressureBoundary", elevation=100.0)
    net.add_node(node)
    with pytest.raises(ValueError, match="Duplicate node"):
        net.add_node(node)

    pipe = _make_pipe("P1", "R1", "missing", length=100.0)
    with pytest.raises(ValueError, match="Unknown to_node"):
        net.add_pipe(pipe)

    pipe.to_node = "R1"
    pipe.from_node = "missing"
    with pytest.raises(ValueError, match="Unknown from_node"):
        net.add_pipe(pipe)

    pipe.from_node = "R1"
    net.add_pipe(pipe)
    with pytest.raises(ValueError, match="Duplicate pipe"):
        net.add_pipe(pipe)


def test_attach_helpers_reject_unknown_pipe() -> None:
    net = _sloping_network()
    with pytest.raises(ValueError, match="Unknown pipe id"):
        attach_air_valve_at_chainage(net, "missing", 500.0)
    with pytest.raises(ValueError, match="Unknown pipe id"):
        attach_air_valve_at_survey_high_point(net, "missing")


def test_attach_air_valve_default_valve_node_id() -> None:
    net = _sloping_network()
    valve_id = attach_air_valve_at_chainage(net, "P1", 1000.0)
    assert valve_id == "P1_av_1000"
    assert net.nodes[valve_id].type == "AirValve"


def test_attach_survey_high_point_rejects_endpoint_summit() -> None:
    net = PipeNetwork()
    net.add_node(_make_node("R1", "PressureBoundary", elevation=320.0, head=400.0))
    net.add_node(_make_node("R2", "PressureBoundary", elevation=100.0, head=400.0))
    pipe = _make_pipe("P1", "R1", "R2", length=2000.0)
    pipe.elevation_profile = [(0.0, 320.0), (2000.0, 100.0)]
    net.add_pipe(pipe)

    with pytest.raises(ValueError, match="lies at an endpoint"):
        attach_air_valve_at_survey_high_point(net, "P1")
