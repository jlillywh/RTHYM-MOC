"""Shared builders for Phase 7 long-pipeline surge validation (LP-02–LP-04)."""

from __future__ import annotations

import rthym_moc as m

FT_PER_MILE = 5280.0
DEFAULT_LENGTH_MI = 5.0
DEFAULT_LENGTH_FT = DEFAULT_LENGTH_MI * FT_PER_MILE
SUMMIT_CHAINAGE_FT = DEFAULT_LENGTH_FT / 2.0
SUMMIT_ELEVATION_FT = 450.0
DEFAULT_GRID_CAP = 2000
DEFAULT_DT_S = 0.001
DEFAULT_MAX_DISTORTION = 0.15
DEFAULT_TOTAL_TIME_S = 8.0
P_VAPOR_PSI = -14.0
CASE_ID = "LP-SURGE-01"


def default_survey(
    length_ft: float = DEFAULT_LENGTH_FT,
    summit_chainage_ft: float = SUMMIT_CHAINAGE_FT,
    summit_elevation_ft: float = SUMMIT_ELEVATION_FT,
) -> list[tuple[float, float]]:
    """Piecewise-linear survey with a single interior high point at mid-chainage."""
    return [
        (0.0, 200.0),
        (summit_chainage_ft, summit_elevation_ft),
        (length_ft, 150.0),
    ]


def survey_z_ft(
    chainage_ft: float,
    survey: list[tuple[float, float]],
) -> float:
    ordered = sorted(survey, key=lambda pair: pair[0])
    if chainage_ft <= ordered[0][0]:
        return ordered[0][1]
    if chainage_ft >= ordered[-1][0]:
        return ordered[-1][1]
    for (x0, z0), (x1, z1) in zip(ordered, ordered[1:]):
        if chainage_ft <= x1:
            frac = (chainage_ft - x0) / (x1 - x0)
            return z0 + frac * (z1 - z0)
    return ordered[-1][1]


def _make_node(node_id: str, node_type: str, **kwargs) -> m.NodeInput:
    node = m.NodeInput()
    node.id = node_id
    node.type = node_type
    for key, value in kwargs.items():
        setattr(node, key, value)
    return node


def _make_pipe(pipe_id: str, from_node: str, to_node: str, **kwargs) -> m.PipeInput:
    pipe = m.PipeInput()
    pipe.id = pipe_id
    pipe.from_node = from_node
    pipe.to_node = to_node
    for key, value in kwargs.items():
        setattr(pipe, key, value)
    return pipe


def expected_grid_distortion_pct(
    *,
    length_ft: float = DEFAULT_LENGTH_FT,
    dt_s: float = DEFAULT_DT_S,
    max_segments_per_pipe: int = DEFAULT_GRID_CAP,
    design_a_fps: float = 4000.0,
) -> tuple[int, float]:
    """Return (num_segments, distortion_pct) mirroring initGrid() with segment cap."""
    n = max(1, round(length_ft / (design_a_fps * dt_s)))
    if max_segments_per_pipe > 0:
        n = min(n, max_segments_per_pipe)
        n = max(n, 2)
    a_adj = length_ft / (n * dt_s)
    distortion_pct = abs(a_adj - design_a_fps) / design_a_fps * 100.0
    return n, distortion_pct


def build_long_pipeline_solver(
    *,
    length_ft: float = DEFAULT_LENGTH_FT,
    survey: list[tuple[float, float]] | None = None,
    sparse_dvcm_at_summit: bool = False,
    max_segments_per_pipe: int = DEFAULT_GRID_CAP,
    with_refill: bool = False,
) -> m.MOCSolver:
    """Multi-mile sloping transmission main with optional summit DVCM watchpoint."""
    survey = survey or default_survey(length_ft=length_ft)

    solver = m.MOCSolver()
    solver.add_node(_make_node("R1", "PressureBoundary", elevation=200.0, head=520.0))
    solver.add_node(_make_node("R2", "PressureBoundary", elevation=150.0, head=520.0))
    pipe = _make_pipe(
        "Pmain",
        "R1",
        "R2",
        length=length_ft,
        diameter=24.0,
        roughness=130.0,
        flow_gpm=2500.0,
    )
    pipe.elevation_profile = survey
    if sparse_dvcm_at_summit:
        pipe.interior_dvcm_chainages_ft = [length_ft / 2.0]
    solver.add_pipe(pipe)
    if with_refill:
        # Downsurge opens a summit cavity; downstream refill drives collapse spikes.
        solver.set_head_schedule(
            "R2",
            [(0.0, 520.0), (0.05, 120.0), (2.0, 520.0)],
        )
    else:
        solver.set_head_schedule("R2", [(0.0, 520.0), (0.05, 120.0)])
    solver.set_grid_policy(
        max_segments_per_pipe=max_segments_per_pipe,
        max_wave_speed_distortion=DEFAULT_MAX_DISTORTION,
        distortion_action="warn",
    )
    return solver


def run_long_pipeline_case(
    solver: m.MOCSolver,
    *,
    total_time_s: float = DEFAULT_TOTAL_TIME_S,
    dt_s: float = DEFAULT_DT_S,
    enable_interior_dvcm: bool = True,
) -> dict[str, object]:
    return solver.run(
        total_time=total_time_s,
        dt=dt_s,
        p_vapor_psi=P_VAPOR_PSI,
        cavitation_model=m.CavitationModel.DVCM,
        record_pipe_profiles=True,
        enable_interior_dvcm=enable_interior_dvcm,
    )
