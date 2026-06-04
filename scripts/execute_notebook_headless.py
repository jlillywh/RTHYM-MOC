#!/usr/bin/env python3
"""Execute a notebook in-place without the Jupyter CLI (matplotlib Agg backend)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def run_notebook(path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: F401

    nb = json.loads(path.read_text())
    g: dict = {"__name__": "__main__", "plt": plt}
    cwd = path.parent.resolve()
    import os

    os.chdir(cwd)
    examples_dir = str(cwd)
    if examples_dir not in sys.path:
        sys.path.insert(0, examples_dir)
    from _verification_notebook_setup import bootstrap_verification_notebook

    require_wntr = path.name == "epanet_import_verification.ipynb"
    bootstrap_verification_notebook(require_wntr=require_wntr)

    for i, cell in enumerate(nb.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue
        src = "".join(cell.get("source", []))
        if not src.strip():
            continue
        print(f"  cell {i} ...", flush=True)
        exec(compile(src, f"{path.name}:cell_{i}", "exec"), g, g)
        plt.close("all")

    path.write_text(json.dumps(nb, indent=1) + "\n")
    print(f"Executed {path}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("notebook", type=Path)
    args = p.parse_args()
    run_notebook(args.notebook.resolve())


if __name__ == "__main__":
    main()
