"""Shared bootstrap for verification notebooks under ``examples/``.

Usage in the first code cell::

    from _verification_notebook_setup import bootstrap_verification_notebook

    REPO_ROOT, TESTS_DIR = bootstrap_verification_notebook()  # require_wntr=True for INP notebooks

Keeps ``tests/`` on ``sys.path`` so ``*_verification_utils`` imports work when the notebook
is run from ``examples/`` or the repo root (Binder, local Jupyter).
"""

from __future__ import annotations

import sys
from pathlib import Path


def find_repo_root(start: Path | None = None) -> Path:
    """Return directory containing ``tests/`` and ``examples/``."""
    cwd = (start or Path.cwd()).resolve()
    for candidate in (cwd, cwd.parent):
        if (candidate / "tests").is_dir() and (candidate / "examples").is_dir():
            return candidate
    raise RuntimeError(
        "Could not find repository root (expected tests/ and examples/). "
        "Open the notebook from the cloned repo or run Jupyter with cwd=examples/."
    )


def bootstrap_verification_notebook(*, require_wntr: bool = False) -> tuple[Path, Path]:
    """Add ``tests/`` to ``sys.path`` and optionally require ``wntr`` for INP notebooks."""
    root = find_repo_root()
    tests = root / "tests"
    examples = root / "examples"
    for path in (tests, examples):
        s = str(path)
        if s not in sys.path:
            sys.path.insert(0, s)
    if require_wntr:
        try:
            import wntr  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "This notebook needs EPANET/wntr. Install with: pip install 'rthym-moc[inp]' or pip install wntr"
            ) from exc
    return root, tests
