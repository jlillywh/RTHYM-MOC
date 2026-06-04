#!/usr/bin/env python3
"""Export Appendix B.8.5 TSNet standpipe reference artifacts (maintainer tool).

Writes:
  tests/TSNet_Standpipe_B8_Verification.json
  tests/TSNet_Standpipe_B8_Traces.csv

Requires: ``pip install tsnet`` (not a default pytest dependency).

Uses the same TSNet driver as ``examples/benchmark_ptsnet_vs_tsnet.py`` (standpipe case).
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
TESTS = REPO / "tests"
EXAMPLES = REPO / "examples"
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(EXAMPLES))

from benchmark_ptsnet_vs_tsnet import (  # noqa: E402
    FT_TO_M,
    SURGE_MODELS,
    _run_tsnet_transient,
)
from cross_engine_verification_utils import TSNET_COMPARE_WINDOW_S  # noqa: E402
from surge_device_verification_utils import H_SP1_SS_FT, run_b8_with_standpipe  # noqa: E402


def main() -> None:
    case = next(c for c in SURGE_MODELS if c.label == "standpipe")
    try:
        _, _, heads_m, times_s = _run_tsnet_transient(case, warmup=0, repeat=1)
    except Exception as exc:
        raise SystemExit(f"TSNet run failed: {exc}") from exc

    heads_ft = np.asarray(heads_m, dtype=float).reshape(-1) / FT_TO_M
    times_s = np.asarray(times_s, dtype=float).reshape(-1)

    res = run_b8_with_standpipe()
    rthym_t = np.asarray(res["time"], dtype=float).reshape(-1)
    rthym_h = np.asarray(res["node_head"]["SP1"], dtype=float).reshape(-1)

    rmask = (rthym_t <= TSNET_COMPARE_WINDOW_S) & (rthym_t >= 0.0)
    rthym_w = rthym_h[rmask]
    tw = rthym_t[rmask]
    ts_interp = np.interp(tw, times_s, heads_ft)
    rms = float(np.sqrt(np.mean((rthym_w - ts_interp) ** 2)))

    mask = times_s <= TSNET_COMPARE_WINDOW_S
    h_w = heads_ft[mask]

    verification = {
        "source": "TSNet MOCSimulator via examples/benchmark_ptsnet_vs_tsnet.py (standpipe case)",
        "compare_window_s": [0.0, TSNET_COMPARE_WINDOW_S],
        "node_id": "J1",
        "rthym_node_id": "SP1",
        "steady_state_head_ft": float(h_w[0]) if h_w.size else None,
        "peak_head_ft": float(np.max(h_w)),
        "rthym_peak_head_ft": float(np.max(rthym_w)) if rthym_w.size else None,
        "peak_diff_ft": abs(float(np.max(rthym_w)) - float(np.max(h_w))) if rthym_w.size and h_w.size else None,
        "rms_head_ft": rms,
        "reference_ss_head_ft": H_SP1_SS_FT,
    }

    json_path = TESTS / "TSNet_Standpipe_B8_Verification.json"
    csv_path = TESTS / "TSNet_Standpipe_B8_Traces.csv"
    json_path.write_text(json.dumps(verification, indent=2) + "\n")

    with csv_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["time_s", "J1_head_ft"])
        for ti, hi in zip(times_s, heads_ft):
            writer.writerow([f"{float(ti):.6f}", f"{float(hi):.6f}"])

    print(f"Wrote {json_path}")
    print(f"Wrote {csv_path} ({len(times_s)} rows)")
    print(json.dumps(verification, indent=2))


if __name__ == "__main__":
    main()
