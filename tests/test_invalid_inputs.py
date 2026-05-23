"""Focused invalid-input and edge-case regressions for the Python API surface."""

import pytest

import rthym_moc as m


def _make_node(node_id, node_type, **kwargs):
    node = m.NodeInput()
    node.id = node_id
    node.type = node_type
    for key, value in kwargs.items():
        setattr(node, key, value)
    return node


def test_unknown_node_type_string_raises_value_error():
    """Setting an unsupported public node type should fail instead of silently becoming a Junction."""
    node = m.NodeInput()

    with pytest.raises(ValueError, match="Unknown node type"):
        node.type = "DefinitelyNotAType"


def test_set_node_demand_rejects_unknown_node_id():
    """Demand updates should fail loudly when the target node does not exist."""
    solver = m.MOCSolver()

    with pytest.raises(ValueError, match="existing node id"):
        solver.set_node_demand("missing", 123.0)


def test_set_valve_schedule_rejects_wrong_node_type():
    """Valve schedules should only bind to Valve or Turbine nodes."""
    solver = m.MOCSolver()
    solver.add_node(_make_node("J1", "Junction", head=120.0, demand=50.0))

    with pytest.raises(ValueError, match="Valve or Turbine"):
        solver.set_valve_schedule("J1", [(0.0, 100.0), (1.0, 0.0)])


def test_set_valve_schedule_rejects_unsorted_times():
    """Schedules should require strictly increasing timestamps."""
    solver = m.MOCSolver()
    solver.add_node(_make_node("V1", "Valve", diameter=12.0, current_setting=100.0, head=148.0))

    with pytest.raises(ValueError, match="strictly increasing schedule times"):
        solver.set_valve_schedule("V1", [(1.0, 0.0), (0.0, 100.0)])


def test_set_head_schedule_rejects_empty_schedule():
    """Fixed-head schedules should reject empty input instead of silently applying defaults."""
    solver = m.MOCSolver()
    solver.add_node(_make_node("T1", "Tank", head=160.0))

    with pytest.raises(ValueError, match="at least one schedule point"):
        solver.set_head_schedule("T1", [])
