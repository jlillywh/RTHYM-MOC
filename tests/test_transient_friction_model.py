"""Phase 6: transient friction model enum and solver plumbing."""

from __future__ import annotations

import numpy as np
import pytest

import rthym_moc as m

FT_PER_MILE = 5280.0
_LONG_PIPE_MI = 5.0
_LONG_PIPE_FT = _LONG_PIPE_MI * FT_PER_MILE
_LONG_PIPE_GRID_CAP = 2000
_LONG_PIPE_DT_S = 0.001
_LONG_PIPE_PERIOD_S = 2 * _LONG_PIPE_GRID_CAP * _LONG_PIPE_DT_S


def _build_valve_closure_solver() -> m.MOCSolver:
    solver = m.MOCSolver()

    r1 = m.NodeInput()
    r1.id = "R1"
    r1.type = "PressureBoundary"
    r1.head = 200.0

    v1 = m.NodeInput()
    v1.id = "V1"
    v1.type = "Valve"
    v1.diameter = 12.0
    v1.current_setting = 100.0

    r2 = m.NodeInput()
    r2.id = "R2"
    r2.type = "PressureBoundary"
    r2.head = 50.0

    p1 = m.PipeInput()
    p1.id = "P1"
    p1.from_node = "R1"
    p1.to_node = "V1"
    p1.length = 3000.0
    p1.diameter = 12.0
    p1.roughness = 130.0
    p1.flow_gpm = 500.0

    p2 = m.PipeInput()
    p2.id = "P2"
    p2.from_node = "V1"
    p2.to_node = "R2"
    p2.length = 100.0
    p2.diameter = 12.0
    p2.roughness = 130.0
    p2.flow_gpm = 500.0

    solver.add_node(r1)
    solver.add_node(v1)
    solver.add_node(r2)
    solver.add_pipe(p1)
    solver.add_pipe(p2)
    solver.set_valve_schedule("V1", [(0.0, 100.0), (0.01, 0.0)])
    return solver


def test_transient_friction_model_default_is_brunone_iir() -> None:
    solver = m.MOCSolver()
    assert solver.get_friction_model() == m.TransientFrictionModel.BrunoneIIR


def test_transient_friction_model_set_get() -> None:
    solver = m.MOCSolver()
    solver.set_friction_model(m.TransientFrictionModel.Steady)
    assert solver.get_friction_model() == m.TransientFrictionModel.Steady


def test_default_run_matches_explicit_brunone_iir() -> None:
    baseline = _build_valve_closure_solver()
    explicit = _build_valve_closure_solver()

    res_default = baseline.run(total_time=0.5, dt=0.01)
    res_brunone = explicit.run(
        total_time=0.5,
        dt=0.01,
        friction_model=m.TransientFrictionModel.BrunoneIIR,
    )

    np.testing.assert_allclose(
        res_default["node_head"]["V1"],
        res_brunone["node_head"]["V1"],
        rtol=0.0,
        atol=0.0,
    )


def test_steady_friction_model_matches_k_bru_zero() -> None:
    solver_steady = _build_valve_closure_solver()
    solver_k0 = _build_valve_closure_solver()

    res_steady = solver_steady.run(
        total_time=0.5,
        dt=0.01,
        friction_model=m.TransientFrictionModel.Steady,
    )
    res_k0 = solver_k0.run(total_time=0.5, dt=0.01, k_bru=0.0)

    np.testing.assert_allclose(
        res_steady["node_head"]["V1"],
        res_k0["node_head"]["V1"],
        rtol=0.0,
        atol=0.0,
    )


def test_steady_friction_differs_from_default_brunone_when_usf_active() -> None:
    solver_steady = _build_valve_closure_solver()
    solver_brunone = _build_valve_closure_solver()

    res_steady = solver_steady.run(
        total_time=0.5,
        dt=0.01,
        friction_model=m.TransientFrictionModel.Steady,
    )
    res_brunone = solver_brunone.run(total_time=0.5, dt=0.01)

    assert not np.allclose(
        res_steady["node_head"]["V1"],
        res_brunone["node_head"]["V1"],
        rtol=0.0,
        atol=1e-9,
    )


def test_quasi_steady_friction_differs_from_fixed_f_steady_on_transient() -> None:
    """Variable f from instantaneous velocity should diverge from fixed-f Steady."""
    steady = _build_valve_closure_solver()
    quasi = _build_valve_closure_solver()

    res_steady = steady.run(
        total_time=0.5,
        dt=0.01,
        friction_model=m.TransientFrictionModel.Steady,
    )
    res_quasi = quasi.run(
        total_time=0.5,
        dt=0.01,
        friction_model=m.TransientFrictionModel.QuasiSteady,
    )

    assert not np.allclose(
        res_steady["node_head"]["V1"],
        res_quasi["node_head"]["V1"],
        rtol=0.0,
        atol=1e-9,
    )


def test_quasi_steady_has_no_unsteady_term_like_steady_at_uniform_flow() -> None:
    """With constant flow, quasi-steady f matches design f and tracks steady friction."""
    solver = m.MOCSolver()

    r1 = m.NodeInput()
    r1.id = "R1"
    r1.type = "PressureBoundary"
    r1.head = 200.0

    r2 = m.NodeInput()
    r2.id = "R2"
    r2.type = "PressureBoundary"
    r2.head = 150.0

    pipe = m.PipeInput()
    pipe.id = "P1"
    pipe.from_node = "R1"
    pipe.to_node = "R2"
    pipe.length = 3000.0
    pipe.diameter = 12.0
    pipe.roughness = 130.0
    pipe.flow_gpm = 500.0

    solver.add_node(r1)
    solver.add_node(r2)
    solver.add_pipe(pipe)

    res_steady = solver.run(
        total_time=0.10,
        dt=0.01,
        friction_model=m.TransientFrictionModel.Steady,
    )
    solver.clear()
    solver.add_node(r1)
    solver.add_node(r2)
    solver.add_pipe(pipe)
    res_quasi = solver.run(
        total_time=0.10,
        dt=0.01,
        friction_model=m.TransientFrictionModel.QuasiSteady,
    )

    np.testing.assert_allclose(
        res_steady["node_head"]["R1"],
        res_quasi["node_head"]["R1"],
        rtol=0.0,
        atol=1e-6,
    )


def test_vitkovsky_friction_differs_from_brunone_iir() -> None:
    brunone = _build_valve_closure_solver()
    vitkovsky = _build_valve_closure_solver()

    res_brunone = brunone.run(total_time=0.5, dt=0.01)
    res_vitkovsky = vitkovsky.run(
        total_time=0.5,
        dt=0.01,
        friction_model=m.TransientFrictionModel.Vitkovsky,
    )

    assert not np.allclose(
        res_brunone["node_head"]["V1"],
        res_vitkovsky["node_head"]["V1"],
        rtol=0.0,
        atol=1e-9,
    )


def test_vitkovsky_friction_damps_more_than_brunone_iir_late() -> None:
    """Vitkovsky should dissipate late oscillations more than BrunoneIIR on this case."""
    brunone = _build_valve_closure_solver()
    vitkovsky = _build_valve_closure_solver()

    res_brunone = brunone.run(total_time=2.0, dt=0.01)
    res_vitkovsky = vitkovsky.run(
        total_time=2.0,
        dt=0.01,
        friction_model=m.TransientFrictionModel.Vitkovsky,
    )

    time_s = np.asarray(res_brunone["time"])
    mask = (time_s >= 1.0) & (time_s <= 2.0)
    brunone_late = float(
        np.mean(np.abs(np.asarray(res_brunone["node_head"]["V1"])[mask] - 150.0))
    )
    vit_late = float(
        np.mean(np.abs(np.asarray(res_vitkovsky["node_head"]["V1"])[mask] - 150.0))
    )
    assert brunone_late > vit_late


def _period_peak_envelope(
    time_s: np.ndarray | list[float],
    head_ft: np.ndarray | list[float],
    period_s: float,
    *,
    skip_periods: int = 2,
) -> tuple[float, list[float]]:
    """Max |H - H_eq| in each wave period after skip_periods (multi-period envelope)."""
    t = np.asarray(time_s, dtype=float)
    h = np.asarray(head_ft, dtype=float)
    eq = float(np.mean(h[t >= t[-1] * 0.85]))
    dev = np.abs(h - eq)
    amps: list[float] = []
    for k in range(skip_periods, int(t[-1] / period_s)):
        mask = (t >= k * period_s) & (t < (k + 1) * period_s)
        if np.any(mask):
            amps.append(float(np.max(dev[mask])))
    return eq, amps


def _build_long_pipe_partial_valve_solver() -> m.MOCSolver:
    """Five-mile transmission main with gradual partial valve throttling."""
    solver = m.MOCSolver()
    r1 = m.NodeInput()
    r1.id = "R1"
    r1.type = "PressureBoundary"
    r1.head = 600.0
    v1 = m.NodeInput()
    v1.id = "V1"
    v1.type = "Valve"
    v1.diameter = 24.0
    v1.current_setting = 100.0
    r2 = m.NodeInput()
    r2.id = "R2"
    r2.type = "PressureBoundary"
    r2.head = 150.0
    p1 = m.PipeInput()
    p1.id = "P1"
    p1.from_node = "R1"
    p1.to_node = "V1"
    p1.length = _LONG_PIPE_FT
    p1.diameter = 24.0
    p1.roughness = 130.0
    p1.flow_gpm = 2000.0
    p2 = m.PipeInput()
    p2.id = "P2"
    p2.from_node = "V1"
    p2.to_node = "R2"
    p2.length = 500.0
    p2.diameter = 24.0
    p2.roughness = 130.0
    p2.flow_gpm = 2000.0
    solver.add_node(r1)
    solver.add_node(v1)
    solver.add_node(r2)
    solver.add_pipe(p1)
    solver.add_pipe(p2)
    solver.set_valve_schedule("V1", [(0.0, 100.0), (1.0, 50.0)])
    solver.set_grid_policy(
        max_segments_per_pipe=_LONG_PIPE_GRID_CAP,
        max_wave_speed_distortion=0.15,
        distortion_action="warn",
    )
    return solver


def _run_long_pipe_friction_case(model: m.TransientFrictionModel) -> dict[str, object]:
    solver = _build_long_pipe_partial_valve_solver()
    return solver.run(
        total_time=80.0,
        dt=_LONG_PIPE_DT_S,
        friction_model=model,
        p_vapor_psi=50.0,
        record_pipe_profiles=True,
        profile_stride=40,
    )


@pytest.mark.slow
def test_long_pipe_peak_envelope_decay_differs_quasi_steady_vs_vitkovsky() -> None:
    """On a 5+ mile line, multi-period peak envelopes differ and Vitkovsky damps more."""
    res_quasi = _run_long_pipe_friction_case(m.TransientFrictionModel.QuasiSteady)
    res_vit = _run_long_pipe_friction_case(m.TransientFrictionModel.Vitkovsky)

    max_chainage_ft = float(max(res_quasi["pipe_profile_chainage_ft"]["P1"]))
    assert max_chainage_ft >= _LONG_PIPE_FT * 0.95
    assert int(res_quasi["pipe_num_segments"]["P1"]) == _LONG_PIPE_GRID_CAP

    mid_idx = len(res_quasi["pipe_profile_chainage_ft"]["P1"]) // 2
    mid_chainage_ft = float(res_quasi["pipe_profile_chainage_ft"]["P1"][mid_idx])
    assert mid_chainage_ft >= _LONG_PIPE_FT * 0.45

    mid_head_quasi = np.asarray(res_quasi["pipe_profile_head"]["P1"][:, mid_idx], dtype=float)
    mid_head_vit = np.asarray(res_vit["pipe_profile_head"]["P1"][:, mid_idx], dtype=float)

    _, env_quasi = _period_peak_envelope(
        res_quasi["time"],
        mid_head_quasi,
        _LONG_PIPE_PERIOD_S,
    )
    _, env_vit = _period_peak_envelope(
        res_vit["time"],
        mid_head_vit,
        _LONG_PIPE_PERIOD_S,
    )

    assert len(env_quasi) >= 6, f"Expected multi-period envelope on long pipe, got {len(env_quasi)} buckets"
    assert len(env_vit) >= 6

    assert not np.allclose(env_quasi, env_vit, rtol=0.0, atol=1.0), (
        "Quasi-steady and Vitkovsky peak envelopes should differ on the long-pipe case"
    )

    quasi_late = float(np.mean(env_quasi[-3:]))
    vit_late = float(np.mean(env_vit[-3:]))
    assert vit_late < quasi_late, (
        f"Expected Vitkovsky late peak envelope ({vit_late:.1f} ft) "
        f"below quasi-steady ({quasi_late:.1f} ft) on reference long-pipe case"
    )

    quasi_decay = env_quasi[-1] / env_quasi[0]
    vit_decay = env_vit[-1] / env_vit[0]
    assert vit_decay < quasi_decay, (
        f"Expected faster Vitkovsky envelope decay ratio ({vit_decay:.3f} vs {quasi_decay:.3f})"
    )

