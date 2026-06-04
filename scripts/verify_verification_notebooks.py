#!/usr/bin/env python3
"""Headless smoke execution of verification notebooks (catches notebook vs utils drift).

Default: fast notebooks only (~2 min total). Use --include-slow for long_pipe and dvcm_showcase.

CI runs the same list via ``tests/test_verification_notebooks_smoke.py``.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = REPO / "examples"
EXECUTOR = REPO / "scripts" / "execute_notebook_headless.py"

FAST_NOTEBOOKS = [
    "validation_notebooks_index.ipynb",
    "cross_engine_surge_verification.ipynb",
    "dvcm_canonical_verification.ipynb",
    "dvcm_physical_verification.ipynb",
    "gradual_closure_verification.ipynb",
    "surge_device_verification.ipynb",
    "surge_design_rules_verification.ipynb",
    "epanet_import_verification.ipynb",
    "quickstart_notebook.ipynb",
]

SLOW_NOTEBOOKS = [
    "long_pipe_valve_verification.ipynb",
    "dvcm_showcase.ipynb",
]


def run_one(nb: Path) -> None:
    subprocess.run(
        [sys.executable, str(EXECUTOR), str(nb)],
        cwd=REPO,
        check=True,
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--include-slow", action="store_true", help="Also run long_pipe and dvcm_showcase")
    p.add_argument("--notebook", type=str, help="Run a single notebook under examples/")
    args = p.parse_args()

    if args.notebook:
        run_one(EXAMPLES / args.notebook)
        return

    notebooks = list(FAST_NOTEBOOKS)
    if args.include_slow:
        notebooks.extend(SLOW_NOTEBOOKS)

    for name in notebooks:
        path = EXAMPLES / name
        if not path.exists():
            raise FileNotFoundError(path)
        print(f"=== {name} ===", flush=True)
        run_one(path)
    print(f"Executed {len(notebooks)} notebook(s) successfully.")


if __name__ == "__main__":
    main()
