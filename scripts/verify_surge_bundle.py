#!/usr/bin/env python3
"""Fast local check: surge utils smoke + pytest (no TSNet, no long-pipe).

Typical runtime ~60–90 s on a built .venv.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TESTS = REPO / "tests"


def smoke() -> None:
    sys.path.insert(0, str(TESTS))
    from surge_device_verification_utils import (
        evaluate_air_valve_restart,
        evaluate_air_valve_vs_unprotected,
        evaluate_hydropneumatic_precharge,
        evaluate_standpipe,
        evaluate_valve_closure_mitigation,
    )

    _, _, sp = evaluate_standpipe()
    _, _, valve = evaluate_valve_closure_mitigation()
    _, _, trip, pre = evaluate_hydropneumatic_precharge()
    _, _, av = evaluate_air_valve_vs_unprotected()
    _, restart = evaluate_air_valve_restart()

    checks = [
        ("standpipe B.8", sp.passed),
        ("valve-side SP/HPT", all(m.passed for m in valve)),
        ("HPT trip", trip.passed),
        ("HPT precharge", pre.passed),
        ("air valve trip", av.passed),
        ("air valve restart", restart.passed),
    ]
    for name, ok in checks:
        print(f"  smoke {name}: {'PASS' if ok else 'FAIL'}")
    if not all(ok for _, ok in checks):
        raise SystemExit(1)


def pytest_surge() -> None:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_surge_device_verification.py",
        "-q",
        "--tb=line",
    ]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, cwd=REPO, check=True)


def execute_surge_notebook() -> None:
    nb = REPO / "examples" / "surge_device_verification.ipynb"
    cmd = [
        sys.executable,
        "-m",
        "jupyter",
        "nbconvert",
        "--execute",
        "--to",
        "notebook",
        "--inplace",
        str(nb),
        "--ExecutePreprocessor.timeout=300",
    ]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, cwd=REPO, check=True)


def main() -> None:
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--smoke-only", action="store_true")
    p.add_argument("--skip-notebook", action="store_true")
    args = p.parse_args()

    print("=== surge utils smoke ===")
    smoke()
    if args.smoke_only:
        return
    print("=== pytest test_surge_device_verification ===")
    pytest_surge()
    if not args.skip_notebook:
        print("=== execute surge_device_verification.ipynb ===")
        execute_surge_notebook()
    print("All surge bundle checks passed.")


if __name__ == "__main__":
    main()
