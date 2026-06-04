#!/usr/bin/env python3
"""Smoke + pytest for DVCM canonical JSON regression (~5 s)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TESTS = REPO / "tests"


def main() -> None:
    sys.path.insert(0, str(TESTS))
    from dvcm_canonical_verification_utils import CASES, run_and_evaluate

    for case_id in CASES:
        _, _, m = run_and_evaluate(case_id)
        print(f"  {case_id}: PASS={m.passed}")
        if not m.passed:
            raise SystemExit(1)

    subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_dvcm_canonical_scenarios.py", "-q"],
        cwd=REPO,
        check=True,
    )
    print("DVCM canonical checks passed.")


if __name__ == "__main__":
    main()
