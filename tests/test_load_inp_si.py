"""Tests for SI overrides on EPANET import."""

from __future__ import annotations

from unittest import mock

import pytest

import rthym_moc as m


def test_load_inp_si_converts_override_kwargs():
    sentinel = object()
    with mock.patch("rthym_moc.epanet.load_inp", return_value=sentinel) as load_inp:
        result = m.load_inp_si(
            "network.inp",
            use_wntr=False,
            initial_flows_m3s={"P1": m.flow_gpm_to_m3s(100.0), "V1": m.flow_gpm_to_m3s(250.0)},
            initial_heads_m={"J1": 30.48, "_VALVE_V1": 45.72},
            stub_length_m=12.192,
        )

    assert result is sentinel
    load_inp.assert_called_once()
    _, kwargs = load_inp.call_args
    assert kwargs["use_wntr"] is False
    assert kwargs["initial_flows"]["P1"] == pytest.approx(100.0)
    assert kwargs["initial_flows"]["V1"] == pytest.approx(250.0)
    assert kwargs["initial_heads"]["J1"] == pytest.approx(100.0)
    assert kwargs["initial_heads"]["_VALVE_V1"] == pytest.approx(150.0)
    assert kwargs["stub_length_ft"] == pytest.approx(40.0)


def test_load_inp_si_passes_through_when_overrides_omitted():
    with mock.patch("rthym_moc.epanet.load_inp") as load_inp:
        m.load_inp_si("network.inp", use_wntr=True)

    load_inp.assert_called_once_with(
        "network.inp",
        use_wntr=True,
        initial_flows=None,
        initial_heads=None,
        stub_length_ft=None,
    )
