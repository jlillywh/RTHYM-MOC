"""EPANET steady-state vs MOC pre-trip (complex_topology.inp)."""

import pytest

wntr = pytest.importorskip("wntr")

from cross_engine_verification_utils import evaluate_epanet_complex_topology_pretrip


def test_epanet_pretrip_heads_and_flows_match_moc() -> None:
    _, summary = evaluate_epanet_complex_topology_pretrip()
    assert summary.passed, (
        f"EPANET pre-trip: heads {summary.head_passed}/{summary.head_total}, "
        f"flows {summary.flow_passed}/{summary.flow_total}"
    )
