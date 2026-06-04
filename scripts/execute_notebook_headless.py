#!/usr/bin/env python3
"""Execute a notebook in-place without the Jupyter CLI (matplotlib Agg backend)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_WNTR_NOTEBOOKS = frozenset(
    {
        "cross_engine_surge_verification.ipynb",
        "epanet_import_verification.ipynb",
        "quickstart_notebook.ipynb",
    }
)


def _configure_stdio_utf8() -> None:
    """Windows cp1252 consoles cannot encode notebook Unicode; prefer UTF-8."""
    os.environ.setdefault("PYTHONUTF8", "1")
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def run_notebook(path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: F401

    nb = json.loads(path.read_text(encoding="utf-8"))
    g: dict = {"__name__": "__main__", "plt": plt}
    cwd = path.parent.resolve()
    os.chdir(cwd)
    examples_dir = str(cwd)
    if examples_dir not in sys.path:
        sys.path.insert(0, examples_dir)
    from _verification_notebook_setup import bootstrap_verification_notebook

    bootstrap_verification_notebook(require_wntr=path.name in _WNTR_NOTEBOOKS)

    for i, cell in enumerate(nb.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue
        src = "".join(cell.get("source", []))
        if not src.strip():
            continue
        print(f"  cell {i} ...", flush=True)
        exec(compile(src, f"{path.name}:cell_{i}", "exec"), g, g)
        plt.close("all")

    path.write_text(json.dumps(nb, indent=1) + "\n", encoding="utf-8")
    print(f"Executed {path}")


def main() -> None:
    _configure_stdio_utf8()
    p = argparse.ArgumentParser()
    p.add_argument("notebook", type=Path)
    args = p.parse_args()
    run_notebook(args.notebook.resolve())


if __name__ == "__main__":
    main()
