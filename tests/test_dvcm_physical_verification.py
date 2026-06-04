"""Independent physical and analytical validation of the Discrete Vapor Cavity Model (DVCM).

These checks use invariants that are separate from stored regression traces:

1. Mass conservation: cavity volume increments match the Wylie continuity rate
   ``(Q_out - Q_in)`` integrated over ``dt``, including the DVCM per-step volume cap.
2. Collapse spike: the post-collapse head rise at the junction is consistent with the
   discrete water-column collision estimate used in ``docs/dvcm_timestep_guidance.md``.
"""

import pytest
import numpy as np

from dvcm_physical_verification_utils import (
    DEFAULT_DT_S,
    evaluate_collapse_spike,
    evaluate_mass_conservation,
    run_physical_verification_case,
    vapor_head_ft,
)

pytestmark = pytest.mark.dvcm

MASS_RTOL = 0.02
MASS_ATOL_FT3 = 1e-5
COLLAPSE_SPIKE_RTOL = 0.15


def test_dvcm_mass_conservation_invariant() -> None:
    """Cavity volume step changes track bounded (Q_out - Q_in) integration."""
    results = run_physical_verification_case(dt=DEFAULT_DT_S)
    metrics = evaluate_mass_conservation(
        results,
        dt=DEFAULT_DT_S,
        rtol=MASS_RTOL,
        atol_ft3=MASS_ATOL_FT3,
    )

    assert metrics.n_steps_checked > 0, "Expected cavity volume changes during the transient."
    assert metrics.passed, (
        "Mass-conservation step mismatch: "
        f"max_abs={metrics.max_abs_step_error_ft3:.3e} ft³, "
        f"max_rel={metrics.max_rel_step_error:.3e} "
        f"({metrics.n_steps_checked} steps checked)"
    )

    volume = np.asarray(results["node_cavity_volume"]["J1"], dtype=float)
    active = np.asarray(results["node_cavity_active"]["J1"], dtype=int)
    assert np.all(volume >= -1e-12)
    assert np.any(volume > 0.0)
    assert np.any(active == 1)
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
