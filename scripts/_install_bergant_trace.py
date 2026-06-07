#!/usr/bin/env python3
"""One-shot: install WebPlotDigitizer export into tests/."""
from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_SRC = Path("/mnt/c/Users/jason/Downloads/Default Dataset.csv")
DST = REPO / "validation" / "datasets" / "bergant_adelaide" / "severe_valve_trace_reference.csv"

HEADER = [
    "# source: He et al. (2025) Processes 13:3510 Fig. 4 — experimental valve pressure (severe, V0=1.4 m/s)",
    "# method: WebPlotDigitizer pen extraction, N=16 panel",
    "# pressure_unit: gauge",
    "# time_unit: s",
    "# case_id: severe_cavitation",
]


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SRC
    if not src.is_file():
        print(f"Not found: {src}")
        return 1

    rows: list[tuple[float, float]] = []
    with src.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append((float(row["t_s"].strip()), float(row["p_gauge_kPa"].strip())))
    rows.sort(key=lambda x: x[0])

    with DST.open("w", newline="", encoding="utf-8") as fh:
        for line in HEADER:
            fh.write(line + "\n")
        writer = csv.writer(fh)
        writer.writerow(["t_s", "p_gauge_kPa"])
        for t, p in rows:
            writer.writerow([f"{t:.6f}", f"{p:.4f}"])

    print(f"Wrote {len(rows)} points to {DST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
