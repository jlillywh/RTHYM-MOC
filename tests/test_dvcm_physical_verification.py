"""Independent physical and analytical validation of the Discrete Vapor Cavity Model (DVCM).

These checks use invariants that are separate from stored regression traces:

1. Mass conservation: during cavity growth, each volume increment matches the
   Wylie continuity rate ``(Q_out - Q_in) * dt``, capped per DVCM junction rules.
2. Collapse spike: the post-collapse head rise matches the discrete water-column
   collision estimate for the primary collapse event on the canonical rapid-recovery
   transient (see ``tests/dvcm_rapid_closure_reference.json``).
"""

import pytest
import numpy as np

from dvcm_physical_verification_utils import (
    COLLAPSE_SPIKE_RTOL,
    DEFAULT_DT_S,
    MASS_STEP_ATOL_FT3,
    evaluate_collapse_spike,
    evaluate_mass_conservation,
    junction_cavity_capacity_ft3,
    run_physical_verification_case,
    vapor_head_ft,
)

pytestmark = pytest.mark.dvcm


def test_dvcm_mass_conservation_invariant() -> None:
    """Cavity growth steps track bounded (Q_out - Q_in) integration."""
    results = run_physical_verification_case(dt=DEFAULT_DT_S)
    metrics = evaluate_mass_conservation(results, dt=DEFAULT_DT_S, atol_ft3=MASS_STEP_ATOL_FT3)

    assert metrics.n_steps_checked > 0, "Expected cavity growth steps during the transient."
    assert metrics.passed, (
        "Mass-conservation growth-step mismatch: "
        f"max_abs={metrics.max_abs_step_error_ft3:.3e} ft^3 "
        f"(limit {MASS_STEP_ATOL_FT3:g} ft^3), "
        f"{metrics.n_steps_checked} growth steps checked"
    )

    volume = np.asarray(results["node_cavity_volume"]["J1"], dtype=float)
    active = np.asarray(results["node_cavity_active"]["J1"], dtype=int)
    assert np.all(volume >= -1e-12)
    assert np.any(volume > 0.0)
    assert np.any(active == 1)
    assert float(volume.max()) <= junction_cavity_capacity_ft3() + 1e-9
    assert float(volume[-1]) == 0.0


def test_dvcm_analytical_collapse_spike_verification() -> None:
    """Post-collapse junction head rise matches the discrete collision estimate."""
    results = run_physical_verification_case(dt=DEFAULT_DT_S)
    metrics = evaluate_collapse_spike(results, dt=DEFAULT_DT_S, rtol=COLLAPSE_SPIKE_RTOL)

    assert metrics.v_before_ft3 > 0.0
    assert metrics.observed_dh_ft > 0.0
    assert metrics.expected_dh_ft > 0.0
    assert metrics.passed, (
        "Collapse spike mismatch: "
        f"observed_dH={metrics.observed_dh_ft:.3f} ft, "
        f"expected_dH={metrics.expected_dh_ft:.3f} ft, "
        f"rel_err={metrics.relative_error:.3f} at step {metrics.collapse_step}"
    )

    head = np.asarray(results["node_head"]["J1"], dtype=float)
    h_vapor = vapor_head_ft()
    assert float(head[metrics.collapse_step : metrics.collapse_step + 3].max()) > h_vapor
