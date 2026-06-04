"""Smoke-test verification notebooks headless (same executor as scripts/verify_verification_notebooks.py)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = REPO / "examples"
EXECUTOR = REPO / "scripts" / "execute_notebook_headless.py"

# Keep in sync with scripts/verify_verification_notebooks.py FAST_NOTEBOOKS
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


@pytest.mark.parametrize("notebook", FAST_NOTEBOOKS)
def test_verification_notebook_runs_headless(notebook: str) -> None:
    """Each fast verification notebook should execute without error (Agg backend)."""
    path = EXAMPLES / notebook
    assert path.is_file(), f"Missing {path}"
    subprocess.run(
        [sys.executable, str(EXECUTOR), str(path)],
        cwd=REPO,
        check=True,
        timeout=600,
    )
