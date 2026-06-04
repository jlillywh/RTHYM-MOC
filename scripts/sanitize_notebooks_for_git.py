#!/usr/bin/env python3
"""Strip notebook outputs so checked-in .ipynb files pass GitHub's nbformat validator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from execute_notebook_headless import sanitize_notebook_for_git  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DEFAULT_NOTEBOOKS = [
    REPO / "examples" / "quickstart_notebook.ipynb",
]


def sanitize_file(path: Path) -> None:
    nb = json.loads(path.read_text(encoding="utf-8"))
    sanitize_notebook_for_git(nb)
    path.write_text(json.dumps(nb, indent=1) + "\n", encoding="utf-8")
    print(f"Sanitized {path}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "notebooks",
        nargs="*",
        type=Path,
        help="Notebook paths (default: examples/quickstart_notebook.ipynb)",
    )
    args = p.parse_args()
    paths = args.notebooks or DEFAULT_NOTEBOOKS
    for path in paths:
        sanitize_file(path.resolve())


if __name__ == "__main__":
    main()
