# Copyright (c) 2026 Jason Lillywhite <jason@lillywhitewater.com>
# SPDX-License-Identifier: MIT
# Author: Jason Lillywhite <jason@lillywhitewater.com>
"""
rthym_moc – 1-D Method of Characteristics transient hydraulic solver.

Quick-start
-----------
>>> import rthym_moc
>>> solver = rthym_moc.MOCSolver()
>>>
>>> # Reservoir → pipe → junction → pipe → valve → reservoir
>>> solver.add_node(rthym_moc.NodeInput(id="R1", type="Tank",
...                                      elevation=0.0, head=150.0))
>>> solver.add_node(rthym_moc.NodeInput(id="J1", type="Junction",
...                                      elevation=0.0, demand=0.0))
>>> solver.add_node(rthym_moc.NodeInput(id="V1", type="Valve",
...                                      elevation=0.0, diameter=12.0,
...                                      current_setting=100.0))
>>> solver.add_node(rthym_moc.NodeInput(id="R2", type="Tank",
...                                      elevation=0.0, head=0.0))
>>>
>>> solver.add_pipe(rthym_moc.PipeInput(id="P1", from_node="R1", to_node="J1",
...                                      length=3000.0, diameter=12.0,
...                                      roughness=130.0, flow_gpm=500.0))
>>> solver.add_pipe(rthym_moc.PipeInput(id="P2", from_node="J1", to_node="V1",
...                                      length=500.0, diameter=12.0,
...                                      roughness=130.0, flow_gpm=500.0))
>>> solver.add_pipe(rthym_moc.PipeInput(id="P3", from_node="V1", to_node="R2",
...                                      length=100.0, diameter=12.0,
...                                      roughness=130.0, flow_gpm=500.0))
>>>
>>> results = solver.run(total_time=5.0, dt=0.01)
>>> import numpy as np
>>> time = results["time"]
>>> head_J1 = results["node_head"]["J1"]   # head time series at junction (ft)
"""

from __future__ import annotations

import warnings
from ._rthym_moc import (
    CavitationModel,
    MOCSolver as _RawMOCSolver,
    NodeInput,
    PipeInput,
    ControlType,
    ControlRuleInput,
    TransientFrictionModel,
    G_FT_S2,
    GPM_TO_CFS,
    PSI_TO_FT,
)
from .epanet import load_inp, load_inp_si
from .report import (
    cavitation_summary,
    export_study_csv,
    export_study_csv_si,
    export_study_json,
    format_grid_report,
    format_study_table,
    format_study_table_si,
    head_to_pressure_kpa,
    head_to_pressure_psi,
    series_extrema,
    study_summary_to_si,
    summarize_study,
    summarize_study_si,
    summarize_grid_report,
)
from .acceptance import (
    run_acceptance_checks,
    format_acceptance_report,
)
from .chainage_air_valve import (
    PipeNetwork,
    SplitPipeAtChainageResult,
    attach_air_valve_at_chainage,
    attach_air_valve_at_survey_high_point,
    elevation_at_chainage_ft,
    head_at_chainage_ft,
    split_pipe_at_chainage,
    survey_high_point_chainage_ft,
)
from .units import (
    DEFAULT_P_VAPOR_KPA,
    FT_TO_M,
    FTS_TO_MS,
    GPM_TO_M3S,
    IN_TO_MM,
    KPA_TO_PSI,
    M3S_TO_GPM,
    M_TO_FT,
    MM_TO_IN,
    MS_TO_FTS,
    PA_TO_PSI,
    PSI_TO_KPA,
    FT2_TO_M2,
    M2_TO_FT2,
    FT3_TO_M3,
    M3_TO_FT3,
    area_ft2_to_m2,
    area_m2_to_ft2,
    control_rule_si,
    convert_demand_schedule_si,
    convert_head_schedule_si,
    diameter_in_to_mm,
    diameter_mm_to_in,
    flow_gpm_to_m3s,
    flow_m3s_to_gpm,
    length_ft_to_m,
    get_node_head_si,
    get_node_pressure_si,
    length_m_to_ft,
    node_si,
    pipe_si,
    pressure_kpa_to_psi,
    pressure_psi_to_kpa,
    results_to_si,
    run_si,
    set_demand_schedule_si,
    set_head_schedule_si,
    set_node_demand_si,
    set_node_head_si,
    velocity_fts_to_ms,
    velocity_ms_to_fts,
    volume_ft3_to_m3,
    volume_m3_to_ft3,
)
from ._version import __version__

class MOCSolver(_RawMOCSolver):
    def set_cavitation_model(self, cavitation_model: CavitationModel) -> None:
        if cavitation_model == CavitationModel.DVCM:
            warnings.warn(
                "Ensure your timestep is sufficiently small (dt <= 0.001 s) to maintain numerical stability when using the DVCM cavitation model.",
                UserWarning,
                stacklevel=2
            )
        super().set_cavitation_model(cavitation_model)

    def set_grid_policy(
        self,
        *,
        max_segments_per_pipe: int | None = None,
        max_wave_speed_distortion: float | None = None,
        distortion_action: str = "warn",
    ) -> None:
        """Configure long-pipe MOC grid scaling and distortion limits."""
        if max_segments_per_pipe is not None:
            self.set_max_segments_per_pipe(max_segments_per_pipe)
        if max_wave_speed_distortion is not None:
            self.set_max_wave_speed_distortion(max_wave_speed_distortion)
            self.set_wave_speed_distortion_action(distortion_action)

    def get_grid_report(self, dt: float, *, warn: bool = True):
        """Preview Courant grid scaling for ``dt`` without running the transient."""
        report = super().get_grid_report(dt)
        if warn and report.get("distortion_warning"):
            warnings.warn(report["distortion_warning"], UserWarning, stacklevel=2)
        return report

    def run(self, *args, **kwargs):
        # Determine the cavitation model being used
        cav_model = kwargs.get("cavitation_model")
        if cav_model is None:
            if len(args) > 5:
                cav_model = args[5]
            else:
                cav_model = self.get_cavitation_model()

        # Determine the timestep
        dt = 0.01
        if len(args) > 1:
            dt = args[1]
        elif "dt" in kwargs:
            dt = kwargs["dt"]

        if cav_model == CavitationModel.DVCM and dt > 0.001:
            warnings.warn(
                "Ensure your timestep is sufficiently small (dt <= 0.001 s) to maintain numerical stability when using the DVCM cavitation model.",
                UserWarning,
                stacklevel=2
            )
        result = super().run(*args, **kwargs)
        grid_msg = self.get_grid_distortion_warning()
        if grid_msg:
            warnings.warn(grid_msg, UserWarning, stacklevel=2)
        return result

__all__ = [
    "CavitationModel",
    "TransientFrictionModel",
    "MOCSolver",
    "NodeInput",
    "PipeInput",
    "ControlType",
    "ControlRuleInput",
    "G_FT_S2",
    "GPM_TO_CFS",
    "PSI_TO_FT",
    "load_inp",
    "load_inp_si",
    "summarize_study",
    "summarize_study_si",
    "summarize_grid_report",
    "format_grid_report",
    "run_acceptance_checks",
    "format_acceptance_report",
    "PipeNetwork",
    "SplitPipeAtChainageResult",
    "attach_air_valve_at_chainage",
    "attach_air_valve_at_survey_high_point",
    "elevation_at_chainage_ft",
    "head_at_chainage_ft",
    "split_pipe_at_chainage",
    "survey_high_point_chainage_ft",
    "study_summary_to_si",
    "series_extrema",
    "cavitation_summary",
    "format_study_table",
    "format_study_table_si",
    "export_study_json",
    "export_study_csv",
    "export_study_csv_si",
    "head_to_pressure_psi",
    "head_to_pressure_kpa",
    "FT_TO_M",
    "M_TO_FT",
    "IN_TO_MM",
    "MM_TO_IN",
    "GPM_TO_M3S",
    "M3S_TO_GPM",
    "PSI_TO_KPA",
    "DEFAULT_P_VAPOR_KPA",
    "KPA_TO_PSI",
    "PA_TO_PSI",
    "FT2_TO_M2",
    "M2_TO_FT2",
    "FT3_TO_M3",
    "M3_TO_FT3",
    "FTS_TO_MS",
    "MS_TO_FTS",
    "length_m_to_ft",
    "length_ft_to_m",
    "diameter_mm_to_in",
    "diameter_in_to_mm",
    "flow_m3s_to_gpm",
    "flow_gpm_to_m3s",
    "pressure_kpa_to_psi",
    "pressure_psi_to_kpa",
    "velocity_ms_to_fts",
    "velocity_fts_to_ms",
    "area_m2_to_ft2",
    "area_ft2_to_m2",
    "volume_m3_to_ft3",
    "volume_ft3_to_m3",
    "node_si",
    "pipe_si",
    "control_rule_si",
    "convert_head_schedule_si",
    "convert_demand_schedule_si",
    "set_head_schedule_si",
    "set_demand_schedule_si",
    "set_node_head_si",
    "set_node_demand_si",
    "get_node_head_si",
    "get_node_pressure_si",
    "run_si",
    "results_to_si",
    "__version__",
]
