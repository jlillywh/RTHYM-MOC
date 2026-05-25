# Copyright (c) 2026 Jason Lillywhite <jason@lillywhitewater.com>
# SPDX-License-Identifier: MIT
"""Engineering summaries and export helpers for MOCSolver results."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Mapping, TypedDict

import numpy as np

from . import PSI_TO_FT


class Extrema(TypedDict):
    min: float
    min_time_s: float
    max: float
    max_time_s: float


class CavitationSummary(TypedDict):
    occurred: bool
    first_time_s: float | None
    steps: int
    duration_s: float


class NodeStudySummary(TypedDict, total=False):
    head_ft: Extrema
    pressure_psi: Extrema
    cavitation: CavitationSummary


class PipeStudySummary(TypedDict):
    flow_gpm: Extrema


class StudySummary(TypedDict):
    meta: dict[str, float | int]
    nodes: dict[str, NodeStudySummary]
    pipes: dict[str, PipeStudySummary]


def _as_time(results: Mapping[str, Any]) -> np.ndarray:
    return np.asarray(results["time"], dtype=float)


def _infer_dt(time_s: np.ndarray) -> float:
    if time_s.size < 2:
        return 0.0
    diffs = np.diff(time_s)
    positive = diffs[diffs > 0.0]
    if positive.size == 0:
        return 0.0
    return float(np.median(positive))


def series_extrema(time_s: np.ndarray, values: np.ndarray) -> Extrema:
    """Return min/max values and the times at which they occur."""
    y = np.asarray(values, dtype=float)
    t = np.asarray(time_s, dtype=float)
    if y.size == 0:
        return Extrema(min=float("nan"), min_time_s=float("nan"), max=float("nan"), max_time_s=float("nan"))
    i_min = int(np.argmin(y))
    i_max = int(np.argmax(y))
    return Extrema(
        min=float(y[i_min]),
        min_time_s=float(t[i_min]),
        max=float(y[i_max]),
        max_time_s=float(t[i_max]),
    )


def cavitation_summary(
    time_s: np.ndarray,
    flags: np.ndarray,
    *,
    dt_s: float | None = None,
) -> CavitationSummary:
    """Summarize cavitation flags (1 = at or below vapor pressure)."""
    t = np.asarray(time_s, dtype=float)
    f = np.asarray(flags, dtype=int)
    active = f > 0
    steps = int(active.sum())
    if steps == 0:
        return CavitationSummary(occurred=False, first_time_s=None, steps=0, duration_s=0.0)
    dt = _infer_dt(t) if dt_s is None else float(dt_s)
    first_idx = int(np.argmax(active))
    return CavitationSummary(
        occurred=True,
        first_time_s=float(t[first_idx]),
        steps=steps,
        duration_s=float(steps * dt),
    )


def summarize_study(results: Mapping[str, Any], *, dt_s: float | None = None) -> StudySummary:
    """Build node/pipe envelopes and cavitation summaries from a ``run()`` result dict."""
    time_s = _as_time(results)
    dt = _infer_dt(time_s) if dt_s is None else float(dt_s)

    nodes_out: dict[str, NodeStudySummary] = {}
    for node_id, head_series in results.get("node_head", {}).items():
        entry: NodeStudySummary = {
            "head_ft": series_extrema(time_s, head_series),
        }
        if node_id in results.get("node_pressure", {}):
            entry["pressure_psi"] = series_extrema(time_s, results["node_pressure"][node_id])
        if node_id in results.get("node_cavitation", {}):
            entry["cavitation"] = cavitation_summary(
                time_s,
                results["node_cavitation"][node_id],
                dt_s=dt,
            )
        nodes_out[str(node_id)] = entry

    pipes_out: dict[str, PipeStudySummary] = {}
    for pipe_id, flow_series in results.get("pipe_flow_gpm", {}).items():
        pipes_out[str(pipe_id)] = {
            "flow_gpm": series_extrema(time_s, flow_series),
        }

    return StudySummary(
        meta={
            "duration_s": float(time_s[-1]) if time_s.size else 0.0,
            "num_steps": int(time_s.size),
            "dt_s": dt,
        },
        nodes=nodes_out,
        pipes=pipes_out,
    )


def format_study_table(summary: StudySummary) -> str:
    """Return a plain-text table suitable for logs or reports."""
    lines = [
        "Transient study summary",
        f"  steps={summary['meta']['num_steps']}  "
        f"dt={summary['meta']['dt_s']:.4g} s  "
        f"duration={summary['meta']['duration_s']:.4g} s",
        "",
        "Node envelopes:",
        f"  {'ID':<20} {'H_min':>8} {'@t':>7} {'H_max':>8} {'@t':>7} "
        f"{'P_min':>8} {'P_max':>8} {'Cav_s':>7}",
    ]
    for node_id, node_row in sorted(summary["nodes"].items()):
        h = node_row["head_ft"]
        p = node_row.get("pressure_psi")
        cav = node_row.get("cavitation")
        p_min = p["min"] if p else float("nan")
        p_max = p["max"] if p else float("nan")
        cav_d = cav["duration_s"] if cav and cav["occurred"] else 0.0
        lines.append(
            f"  {node_id:<20} {h['min']:8.2f} {h['min_time_s']:7.2f} "
            f"{h['max']:8.2f} {h['max_time_s']:7.2f} "
            f"{p_min:8.2f} {p_max:8.2f} {cav_d:7.2f}"
        )

    lines.extend(["", "Pipe flow peaks:", f"  {'ID':<20} {'Q_min':>10} {'@t':>7} {'Q_max':>10} {'@t':>7}"])
    for pipe_id, pipe_row in sorted(summary["pipes"].items()):
        q = pipe_row["flow_gpm"]
        lines.append(
            f"  {pipe_id:<20} {q['min']:10.1f} {q['min_time_s']:7.2f} "
            f"{q['max']:10.1f} {q['max_time_s']:7.2f}"
        )
    return "\n".join(lines)


def export_study_json(path: str | Path, summary: StudySummary) -> Path:
    """Write a study summary dict to JSON."""
    out = Path(path)
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


def export_study_csv(directory: str | Path, summary: StudySummary) -> dict[str, Path]:
    """Write node, pipe, and cavitation summary CSV files."""
    out_dir = Path(directory)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    nodes_path = out_dir / "node_envelopes.csv"
    with nodes_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "node_id",
                "head_min_ft",
                "head_min_time_s",
                "head_max_ft",
                "head_max_time_s",
                "pressure_min_psi",
                "pressure_max_psi",
                "cavitation_duration_s",
                "cavitation_first_time_s",
            ]
        )
        for node_id, node_row in sorted(summary["nodes"].items()):
            h = node_row["head_ft"]
            p = node_row.get("pressure_psi")
            cav = node_row.get("cavitation")
            writer.writerow(
                [
                    node_id,
                    h["min"],
                    h["min_time_s"],
                    h["max"],
                    h["max_time_s"],
                    p["min"] if p else "",
                    p["max"] if p else "",
                    cav["duration_s"] if cav else 0.0,
                    cav["first_time_s"] if cav and cav["first_time_s"] is not None else "",
                ]
            )
    written["nodes"] = nodes_path

    pipes_path = out_dir / "pipe_flow_envelopes.csv"
    with pipes_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "pipe_id",
                "flow_min_gpm",
                "flow_min_time_s",
                "flow_max_gpm",
                "flow_max_time_s",
            ]
        )
        for pipe_id, pipe_row in sorted(summary["pipes"].items()):
            q = pipe_row["flow_gpm"]
            writer.writerow(
                [pipe_id, q["min"], q["min_time_s"], q["max"], q["max_time_s"]]
            )
    written["pipes"] = pipes_path

    meta_path = out_dir / "study_meta.json"
    export_study_json(meta_path, summary)
    written["meta"] = meta_path
    return written


def head_to_pressure_psi(head_ft: float, elevation_ft: float) -> float:
    """Convert piezometric head (ft) to gauge pressure (psi) at *elevation_ft*."""
    return (head_ft - elevation_ft) / PSI_TO_FT
