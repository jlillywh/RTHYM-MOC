"""Tests for [RTHYM] section unit handling tied to EPANET [OPTIONS] Units."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

import rthym_moc as m
from rthym_moc.epanet import _convert_rthym_params_to_us, _parse_rthym_overrides


def test_convert_rthym_params_to_us_from_si():
    gas_volume_m3 = m.volume_ft3_to_m3(0.1)
    tank_volume_m3 = m.volume_ft3_to_m3(1.0)
    params = {
        "node_type": "AirValve",
        "air_release_head": 3.048,
        "diameter": 50.8,
        "air_release_diameter": 12.7,
        "gas_volume": gas_volume_m3,
        "tank_volume": tank_volume_m3,
        "tank_area": m.area_ft2_to_m2(1.5),
        "polytropic_n": 1.2,
        "loss_coeff_in": 0.7,
    }

    out = _convert_rthym_params_to_us(params, si_units=True)

    assert out["air_release_head"] == pytest.approx(10.0)
    assert out["diameter"] == pytest.approx(2.0)
    assert out["air_release_diameter"] == pytest.approx(0.5)
    assert out["gas_volume"] == pytest.approx(0.1)
    assert out["tank_volume"] == pytest.approx(1.0)
    assert out["tank_area"] == pytest.approx(1.5)
    assert out["polytropic_n"] == pytest.approx(1.2)
    assert out["loss_coeff_in"] == pytest.approx(0.7)


def test_convert_rthym_params_to_us_leaves_us_values_unchanged():
    params = {
        "node_type": "Standpipe",
        "tank_area": 1.5,
        "closure_time": 2.5,
    }

    out = _convert_rthym_params_to_us(params, si_units=False)

    assert out == params


def test_parse_rthym_overrides_uses_epanet_units_keyword():
    sec = {
        "RTHYM": [
            ["J1", "Standpipe", "tank_area=0.13935456"],
        ]
    }

    us = _parse_rthym_overrides(sec, "GPM")
    si = _parse_rthym_overrides(sec, "LPS")

    assert us["J1"]["tank_area"] == pytest.approx(0.13935456)
    assert si["J1"]["tank_area"] == pytest.approx(1.5)


def _capture_nodes_from_inp(path: str) -> dict[str, m.NodeInput]:
    added_nodes: dict[str, m.NodeInput] = {}
    original_add_node = m.MOCSolver.add_node

    def mock_add_node(self, node: m.NodeInput):
        added_nodes[node.id] = node
        return original_add_node(self, node)

    with mock.patch.object(m.MOCSolver, "add_node", mock_add_node):
        m.load_inp(path, use_wntr=False, initial_flows={"P2": 500.0}, initial_heads={"J1": 150.0})

    return added_nodes


def _minimal_rthym_inp(*, units: str, rthym_row: str) -> str:
    return f"""[TITLE]
RTHYM units test

[JUNCTIONS]
J1   0          0
J2   0          0

[RESERVOIRS]
R1   160
R2   140

[CURVES]
C1   0   100
C1   200   200

[PUMPS]
PU1  R1  J1  HEAD C1

[VALVES]
VA1  J1  J2  12  TCV  10

[PIPES]
P2   J2  R2  40      12        130        0          CV

[RTHYM]
{rthym_row}

[OPTIONS]
UNITS {units}
HEADLOSS H-W

[END]
"""


def test_load_inp_rthym_si_units_match_us_equivalent(tmp_path: Path):
    us_path = tmp_path / "us.inp"
    si_path = tmp_path / "si.inp"
    us_path.write_text(
        _minimal_rthym_inp(
            units="GPM",
            rthym_row=(
                "_PUMP_PU1 AirValve diameter=2.0 air_release_head=10.0 "
                "air_release_diameter=0.5 gas_volume=0.1 tank_volume=1.0 "
                "loss_coeff_in=0.6 loss_coeff_out=0.8"
            ),
        ),
        encoding="utf-8",
    )
    si_path.write_text(
        _minimal_rthym_inp(
            units="LPS",
            rthym_row=(
                "_PUMP_PU1 AirValve diameter=50.8 air_release_head=3.048 "
                f"air_release_diameter=12.7 gas_volume={m.volume_ft3_to_m3(0.1)} "
                f"tank_volume={m.volume_ft3_to_m3(1.0)} "
                "loss_coeff_in=0.6 loss_coeff_out=0.8"
            ),
        ),
        encoding="utf-8",
    )

    us_pump = _capture_nodes_from_inp(str(us_path))["_PUMP_PU1"]
    si_pump = _capture_nodes_from_inp(str(si_path))["_PUMP_PU1"]

    assert si_pump.type == us_pump.type == "AirValve"
    assert si_pump.diameter == pytest.approx(us_pump.diameter)
    assert si_pump.air_release_head == pytest.approx(us_pump.air_release_head)
    assert si_pump.air_release_diameter == pytest.approx(us_pump.air_release_diameter)
    assert si_pump.gas_volume == pytest.approx(us_pump.gas_volume)
    assert si_pump.tank_volume == pytest.approx(us_pump.tank_volume)
    assert si_pump.loss_coeff_in == pytest.approx(us_pump.loss_coeff_in)
    assert si_pump.loss_coeff_out == pytest.approx(us_pump.loss_coeff_out)
