import sys
import math
import pytest
import warnings
from pathlib import Path
from unittest.mock import patch, MagicMock

import rthym_moc as m
from rthym_moc.epanet import _get_option, _hw_from_dw
import rthym_moc.epanet as epanet_mod

def test_load_inp_file_not_found():
    with pytest.raises(FileNotFoundError):
        m.load_inp("non_existent_file_xyz_123.inp")

def test_load_inp_invalid_units(tmp_path: Path):
    inp_path = tmp_path / "invalid_units.inp"
    inp_path.write_text(
        """[OPTIONS]
UNITS XYZ
HEADLOSS H-W
""",
        encoding="utf-8"
    )
    with pytest.raises(ValueError, match="Unrecognised EPANET Units value"):
        m.load_inp(str(inp_path))

def test_load_inp_malformed_sections_and_warnings(tmp_path: Path):
    inp_path = tmp_path / "malformed_rows.inp"
    inp_path.write_text(
        """[JUNCTIONS]
;ID  Elevation  Demand
J1   ; malformed (less than 2 tokens)
J2   10   0

[RESERVOIRS]
;ID  Head
R1   ; malformed
R2   150

[TANKS]
;ID  Elevation  InitLevel  MinLevel  MaxLevel  Diameter  MinVol
T1   10   5   0   ; malformed
T2   10   5   0   20   12   0

[PIPES]
;ID  Node1  Node2  Length  Diameter  Roughness  MinorLoss  Status
P1   frm ; malformed
P2   J2     R2     1000    12        130        0.0        CLOSED
P3   J2     T2     1000    12        0.1        0.0        CV  ; status CV

[PUMPS]
;ID  Node1  Node2  Parameters
PU1  ; malformed
PU2  R2     J2     HEAD Curve1
PU3  R2     J2     POWER 10

[VALVES]
;ID  Node1  Node2  Diameter  Type  Setting
V1   ; malformed
V2   J2     T2     8         PRV   50
V3   J2     T2     8         GPV   1.0
V4   J2     T2     8         XYZ   1.0

[CURVES]
C1   ; malformed
C1   1.0   abc  ; value error

[RTHYM]
J2   ; malformed

[OPTIONS]
UNITS GPM
HEADLOSS INVALID_HL
""",
        encoding="utf-8"
    )

    with pytest.warns(UserWarning) as record:
        solver = m.load_inp(
            str(inp_path),
            use_wntr=False,
            initial_flows={"P2": 0.0, "P3": 10.0, "_PUMP_PU2": 0.0, "_PUMP_PU3": 0.0},
            initial_heads={"J2": 150.0}
        )

    # Verify that warnings were issued for closed pipe, invalid headloss, etc.
    warnings_text = [str(w.message).upper() for w in record]
    assert any("CLOSED" in text for text in warnings_text)
    assert any("HEADLOSS" in text for text in warnings_text)
    assert any("CURVE1" in text for text in warnings_text)
    assert any("POWER" in text for text in warnings_text)
    assert any("PRESSURE SETPOINT" in text for text in warnings_text)
    assert any("NOT SUPPORTED" in text for text in warnings_text)
    assert any("UNRECOGNISED TYPE" in text for text in warnings_text)
    assert solver is not None

def test_roughness_conversions(tmp_path: Path):
    # Darcy-Weisbach conversion in US units
    inp_path_dw_us = tmp_path / "dw_us.inp"
    inp_path_dw_us.write_text(
        """[JUNCTIONS]
J1   0   0
J2   0   0

[PIPES]
P1   J1   J2   1000   12   0.02   0.0   OPEN

[OPTIONS]
UNITS GPM
HEADLOSS D-W
""",
        encoding="utf-8"
    )
    solver1 = m.load_inp(str(inp_path_dw_us), use_wntr=False)
    assert solver1 is not None

    # Darcy-Weisbach conversion in SI units
    inp_path_dw_si = tmp_path / "dw_si.inp"
    inp_path_dw_si.write_text(
        """[JUNCTIONS]
J1   0   0
J2   0   0

[PIPES]
P1   J1   J2   1000   300   0.5   0.0   OPEN

[OPTIONS]
UNITS LPS
HEADLOSS D-W
""",
        encoding="utf-8"
    )
    solver2 = m.load_inp(str(inp_path_dw_si), use_wntr=False)
    assert solver2 is not None

    # Manning conversion
    inp_path_cm = tmp_path / "cm.inp"
    inp_path_cm.write_text(
        """[JUNCTIONS]
J1   0   0
J2   0   0

[PIPES]
P1   J1   J2   1000   12   0.013   0.0   OPEN

[OPTIONS]
UNITS GPM
HEADLOSS C-M
""",
        encoding="utf-8"
    )
    solver3 = m.load_inp(str(inp_path_cm), use_wntr=False)
    assert solver3 is not None

    # Manning conversion with invalid/negative n (to trigger line 253 default)
    inp_path_cm_neg = tmp_path / "cm_neg.inp"
    inp_path_cm_neg.write_text(
        """[JUNCTIONS]
J1   0   0
J2   0   0

[PIPES]
P1   J1   J2   1000   12   -0.013   0.0   OPEN

[OPTIONS]
UNITS GPM
HEADLOSS C-M
""",
        encoding="utf-8"
    )
    solver4 = m.load_inp(str(inp_path_cm_neg), use_wntr=False)
    assert solver4 is not None

def test_get_option_default():
    # Trigger line 160 (return default in _get_option)
    assert _get_option({}, "UNITS", "GPM") == "GPM"

def test_wntr_import_error_and_exception_paths(tmp_path: Path):
    inp_path = tmp_path / "simple.inp"
    inp_path.write_text(
        """[JUNCTIONS]
J1   0   0
J2   0   0

[PIPES]
P1   J1   J2   1000   12   130   0.0   OPEN

[OPTIONS]
UNITS GPM
HEADLOSS H-W
""",
        encoding="utf-8"
    )

    # 1. Trigger wntr ImportError (lines 341-348)
    with patch.dict(sys.modules, {"wntr": None}):
        with pytest.warns(UserWarning, match="wntr is not installed"):
            solver = m.load_inp(str(inp_path), use_wntr=True)
            assert solver is not None

    # 2. Trigger wntr solve failure exception (lines 358-363)
    # We mock the wntr module entirely to prevent real wntr import/dependency failures in CI
    mock_wntr = MagicMock()
    mock_wntr.sim.EpanetSimulator.side_effect = Exception("Mock simulator error")
    with patch.dict(sys.modules, {"wntr": mock_wntr}):
        with pytest.warns(UserWarning, match="wntr hydraulic solve failed"):
            solver2 = m.load_inp(str(inp_path), use_wntr=True)
            assert solver2 is not None

def test_hw_from_dw_zero_denom():
    # Swap epanet_mod.math to trigger denom underflow (line 244)
    orig_math = epanet_mod.math
    mock_math = MagicMock()
    mock_math.log10.return_value = float("inf")
    mock_math.pi = orig_math.pi
    mock_math.sqrt = orig_math.sqrt
    try:
        epanet_mod.math = mock_math
        assert _hw_from_dw(0.02, 300) == 130.0
    finally:
        epanet_mod.math = orig_math
