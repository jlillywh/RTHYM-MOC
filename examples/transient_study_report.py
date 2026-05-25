#!/usr/bin/env python3
"""Example: run a transient and export engineering study summaries.

Roadmap item 5 — post-processing workflow without bespoke analysis code.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import rthym_moc as m


def build_demo_solver() -> m.MOCSolver:
    solver = m.MOCSolver()

    def node(node_id, node_type, **kwargs):
        n = m.NodeInput()
        n.id = node_id
        n.type = node_type
        for k, v in kwargs.items():
            setattr(n, k, v)
        return n

    def pipe(pipe_id, frm, to, **kwargs):
        p = m.PipeInput()
        p.id = pipe_id
        p.from_node = frm
        p.to_node = to
        for k, v in kwargs.items():
            setattr(p, k, v)
        return p

    solver.add_node(node("R1", "PressureBoundary", head=160.0))
    solver.add_node(node("J1", "Junction", elevation=0.0, head=140.0))
    solver.add_node(node("V1", "Valve", diameter=12.0, current_setting=100.0))
    solver.add_node(node("R2", "PressureBoundary", head=100.0))

    for pid, frm, to, q in (
        ("P1", "R1", "J1", 300.0),
        ("P2", "J1", "V1", 300.0),
        ("P3", "V1", "R2", 300.0),
    ):
        solver.add_pipe(
            pipe(pid, frm, to, length=500.0, diameter=12.0, roughness=130.0, flow_gpm=q)
        )

    # Fast valve closure to generate a surge worth summarizing.
    solver.set_valve_schedule(
        "V1",
        [
            (0.0, 100.0),
            (0.09, 100.0),
            (0.1, 0.0),
            (1.0, 0.0),
        ],
    )
    return solver


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("study_output"),
        help="Directory for CSV/JSON exports (default: study_output)",
    )
    parser.add_argument("--total-time", type=float, default=1.0)
    parser.add_argument("--dt", type=float, default=0.01)
    args = parser.parse_args()

    results = build_demo_solver().run(total_time=args.total_time, dt=args.dt)
    summary = m.summarize_study(results)

    print(m.format_study_table(summary))
    print()

    args.out.mkdir(parents=True, exist_ok=True)
    json_path = m.export_study_json(args.out / "study_summary.json", summary)
    csv_paths = m.export_study_csv(args.out, summary)
    print(f"Wrote {json_path}")
    for label, path in csv_paths.items():
        print(f"Wrote {label}: {path}")


if __name__ == "__main__":
    main()
