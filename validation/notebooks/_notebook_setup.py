"""Bootstrap for notebooks under ``validation/notebooks/``."""

from __future__ import annotations

import sys
from pathlib import Path


def find_repo_root(start: Path | None = None) -> Path:
    cwd = (start or Path.cwd()).resolve()
    for candidate in (cwd, *cwd.parents):
        if (candidate / "tests").is_dir() and (candidate / "validation").is_dir():
            return candidate
    raise RuntimeError(
        "Could not find repository root (expected tests/ and validation/). "
        "Open the notebook from the cloned repo."
    )


def bootstrap_validation_notebook(*, require_wntr: bool = False) -> tuple[Path, Path, Path]:
    """Add ``tests/`` and ``examples/`` to ``sys.path`` for helper imports."""
    root = find_repo_root()
    tests = root / "tests"
    examples = root / "examples"
    validation = root / "validation"
    for path in (tests, examples, validation / "notebooks"):
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)
    if require_wntr:
        try:
            import wntr  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "This notebook needs EPANET/wntr. Install with: pip install 'rthym-moc[inp]'"
            ) from exc
    return root, tests, validation
