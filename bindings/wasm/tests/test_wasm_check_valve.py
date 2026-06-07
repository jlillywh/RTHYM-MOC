"""Regression coverage for maintainer/internal Emscripten bindings."""

from __future__ import annotations

from pathlib import Path
import json
import shutil
import subprocess

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
CORE_CPP = REPO_ROOT / "src" / "solver" / "moc_solver.cpp"
WASM_BINDINGS_CPP = REPO_ROOT / "bindings" / "wasm" / "wasm_bindings.cpp"
WASM_OUT_DIR = REPO_ROOT / "build" / "wasm"
WASM_JS = WASM_OUT_DIR / "rthym_moc.js"
WASM_BIN = WASM_OUT_DIR / "rthym_moc.wasm"


def test_wasm_bindings_expose_check_valve_runtime_contract():
    """The WASM bindings should explicitly expose CheckValve runtime state."""
    core_source = CORE_CPP.read_text(encoding="utf-8")
    wasm_source = WASM_BINDINGS_CPP.read_text(encoding="utf-8")

    assert "NodeType::CheckValve" in core_source
    assert "reverse_flow_blocked" in core_source
    assert "convert_snapshot_to_val" in wasm_source
    assert 'node_res.set("type", node.type);' in wasm_source
    assert 'node_res.set("reverseFlowBlocked", node.reverse_flow_blocked);' in wasm_source


@pytest.mark.wasm_runtime
def test_wasm_runtime_reports_check_valve_type_and_reverse_flow_blocked():
    """The generated WASM module should report explicit CheckValve runtime state."""
    if shutil.which("node") is None:
        pytest.fail("node is required for WASM runtime tests")
    if not WASM_JS.exists() or not WASM_BIN.exists():
        pytest.fail(
            "WASM artifacts not found. Run bash build_wasm.sh, then "
            "pytest -m wasm_runtime --override-ini=\"addopts=\" bindings/wasm/tests"
        )

    node_program = f"""
const createRthymMOC = require({json.dumps(str(WASM_JS))});

function makeNode(Module, id, type, fields = {{}}) {{
  const node = new Module.NodeInput();
  node.id = id;
  node.type = type;
  for (const [key, value] of Object.entries(fields)) {{
    node[key] = value;
  }}
  return node;
}}

function makePipe(Module, id, fromNode, toNode, flowGPM) {{
  const pipe = new Module.PipeInput();
  pipe.id = id;
  pipe.from_node = fromNode;
  pipe.to_node = toNode;
  pipe.length = 40.0;
  pipe.diameter = 12.0;
  pipe.roughness = 130.0;
  pipe.flow_gpm = flowGPM;
  return pipe;
}}

(async () => {{
  const Module = await createRthymMOC();
  const solver = new Module.MOCSolver();

  solver.add_node(makeNode(Module, "R1", "PressureBoundary", {{ head: 160.0 }}));
  solver.add_node(makeNode(Module, "CV1", "CheckValve", {{ head: 150.0, diameter: 12.0 }}));
  solver.add_node(makeNode(Module, "R2", "PressureBoundary", {{ head: 260.0 }}));

  solver.add_pipe(makePipe(Module, "P1", "R1", "CV1", 500.0));
  solver.add_pipe(makePipe(Module, "P2", "CV1", "R2", 500.0));

  solver.set_dt(0.01);
  solver.initGrid();
  for (let i = 0; i < 50; i++) {{
    solver.stepMOC();
  }}

  const results = solver.get_step_results();
  const cv = results.nodes.CV1;
  process.stdout.write(JSON.stringify({{
    type: cv.type,
    reverseFlowBlocked: cv.reverseFlowBlocked,
    flowGPM: cv.flowGPM,
    upstreamHead: cv.upstreamHead,
    downstreamHead: cv.downstreamHead
  }}));
}})().catch((error) => {{
  console.error(error);
  process.exit(1);
}});
"""

    completed = subprocess.run(
        ["node", "-e", node_program],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(completed.stdout)
    assert payload["type"] == "CheckValve"
    assert payload["reverseFlowBlocked"] is True
    assert abs(payload["flowGPM"]) <= 1.0
    assert payload["downstreamHead"] > payload["upstreamHead"]


@pytest.mark.wasm_runtime
def test_wasm_runtime_step_results_include_link_telemetry() -> None:
    """Link snapshots from capture_step_snapshot() should serialize under results.links."""
    if shutil.which("node") is None:
        pytest.fail("node is required for WASM runtime tests")
    if not WASM_JS.exists() or not WASM_BIN.exists():
        pytest.fail("WASM artifacts not found. Run bash build_wasm.sh first.")

    node_program = f"""
const createRthymMOC = require({json.dumps(str(WASM_JS))});

(async () => {{
  const Module = await createRthymMOC();
  const solver = new Module.MOCSolver();

  const r1 = new Module.NodeInput();
  r1.id = "R1";
  r1.type = "PressureBoundary";
  r1.head = 200.0;

  const r2 = new Module.NodeInput();
  r2.id = "R2";
  r2.type = "PressureBoundary";
  r2.head = 150.0;

  const pipe = new Module.PipeInput();
  pipe.id = "P1";
  pipe.from_node = "R1";
  pipe.to_node = "R2";
  pipe.length = 1000.0;
  pipe.diameter = 12.0;
  pipe.roughness = 130.0;
  pipe.flow_gpm = 500.0;

  solver.add_node(r1);
  solver.add_node(r2);
  solver.add_pipe(pipe);
  solver.set_dt(0.01);
  solver.initGrid();
  solver.stepMOC();

  const results = solver.get_step_results();
  const link = results.links.P1;
  process.stdout.write(JSON.stringify({{
    flowGPM: link.flowGPM,
    headloss: link.headloss
  }}));
}})().catch((error) => {{
  console.error(error);
  process.exit(1);
}});
"""

    completed = subprocess.run(
        ["node", "-e", node_program],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(completed.stdout)
    assert payload["flowGPM"] > 0.0
    assert payload["headloss"] >= 0.0


@pytest.mark.wasm_runtime
def test_wasm_runtime_handles_isolated_nodes():
    """The WASM runtime should handle isolated nodes without crashes during initGrid/stepMOC/get_step_results."""
    if shutil.which("node") is None:
        pytest.fail("node is required for WASM runtime tests")
    if not WASM_JS.exists() or not WASM_BIN.exists():
        pytest.fail("WASM artifacts not found.")

    node_program = f"""
const createRthymMOC = require({json.dumps(str(WASM_JS))});

function makeNode(Module, id, type, fields = {{}}) {{
  const node = new Module.NodeInput();
  node.id = id;
  node.type = type;
  for (const [key, value] of Object.entries(fields)) {{
    node[key] = value;
  }}
  return node;
}}

function makePipe(Module, id, fromNode, toNode, flowGPM) {{
  const pipe = new Module.PipeInput();
  pipe.id = id;
  pipe.from_node = fromNode;
  pipe.to_node = toNode;
  pipe.length = 40.0;
  pipe.diameter = 12.0;
  pipe.roughness = 130.0;
  pipe.flow_gpm = flowGPM;
  return pipe;
}}

(async () => {{
  const Module = await createRthymMOC();
  const solver = new Module.MOCSolver();

  solver.add_node(makeNode(Module, "R1", "PressureBoundary", {{ head: 100.0 }}));
  solver.add_node(makeNode(Module, "R2", "PressureBoundary", {{ head: 90.0 }}));
  // Isolated node
  solver.add_node(makeNode(Module, "ISO1", "Junction", {{ head: 95.0, demand: 0.0 }}));

  solver.add_pipe(makePipe(Module, "P1", "R1", "R2", 10.0));

  solver.set_dt(0.01);
  solver.initGrid();
  solver.stepMOC();

  const results = solver.get_step_results();
  const iso = results.nodes.ISO1;
  process.stdout.write(JSON.stringify({{
    id: "ISO1",
    head: iso.upstreamHead
  }}));
}})().catch((error) => {{
  console.error(error);
  process.exit(1);
}});
"""

    completed = subprocess.run(
        ["node", "-e", node_program],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(completed.stdout)

    assert payload["id"] == "ISO1"
    assert abs(payload["head"] - 95.0) < 1e-6