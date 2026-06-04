"""Interactive surge-device notebook mirrors (standpipe, HPT, air valve).

See ``examples/surge_device_verification.ipynb`` and
``tests/surge_device_verification_utils.py``.
"""

import pytest

from surge_device_verification_utils import (
    evaluate_air_valve_restart,
    evaluate_air_valve_vs_unprotected,
    evaluate_hydropneumatic_precharge,
    evaluate_standpipe,
    evaluate_valve_closure_mitigation,
)


def test_surge_standpipe_b8_joukowsky_and_mass_oscillation() -> None:
    _, _, metrics = evaluate_standpipe()
    assert metrics.passed, metrics


def test_surge_valve_side_standpipe_and_hpt_limit_closure_peak() -> None:
    _, _, device_metrics = evaluate_valve_closure_mitigation()
    assert all(m.passed for m in device_metrics), device_metrics


def test_surge_hydropneumatic_pump_trip_protection() -> None:
    _, _, trip, pre = evaluate_hydropneumatic_precharge()
    assert trip.passed and pre.passed, (trip, pre)


def test_surge_air_valve_pump_trip_floor() -> None:
    _, _, metrics = evaluate_air_valve_vs_unprotected()
    assert metrics.passed, metrics


def test_surge_air_valve_trapped_air_restart() -> None:
    _, metrics = evaluate_air_valve_restart()
    assert metrics.passed, metrics
