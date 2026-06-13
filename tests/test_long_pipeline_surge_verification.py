"""Notebook parity for ``examples/long_pipeline_surge_verification.ipynb``."""

from __future__ import annotations

import numpy as np

from long_pipeline_surge_verification_utils import (
    evaluate_collapse_spike,
    evaluate_grid_cap,
    evaluate_summit_cavity,
    evaluate_summit_static,
    run_downsurge_case,
    run_refill_collapse_case,
    run_static_preview,
    summit_index,
)


def test_long_pipeline_surge_verification_lp02_static() -> None:
    results = run_static_preview()
    assert evaluate_summit_static(results).passed


def test_long_pipeline_surge_verification_lp03_cavity() -> None:
    results = run_downsurge_case()
    assert evaluate_summit_cavity(results).passed


def test_long_pipeline_surge_verification_lp04_collapse() -> None:
    results = run_refill_collapse_case()
    assert evaluate_collapse_spike(results).passed


def test_long_pipeline_surge_verification_grid_metadata() -> None:
    results = run_static_preview()
    assert evaluate_grid_cap(results).passed


def test_evaluate_collapse_spike_fails_when_cavity_never_collapses() -> None:
    results = run_downsurge_case()
    volume = np.asarray(results["pipe_profile_cavity_volume"]["Pmain"], dtype=float)
    chainage = np.asarray(results["pipe_profile_chainage_ft"]["Pmain"])
    idx = summit_index(chainage)
    volume[:, idx] = np.maximum.accumulate(volume[:, idx])
    results["pipe_profile_cavity_volume"]["Pmain"] = volume

    metrics = evaluate_collapse_spike(results)
    assert not metrics.passed
    assert metrics.collapse_step == -1
    assert metrics.rise_ft == 0.0
