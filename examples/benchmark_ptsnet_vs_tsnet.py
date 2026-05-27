# Copyright (c) 2026 Jason Lillywhite <jason@lillywhitewater.com>
# SPDX-License-Identifier: MIT
"""
Three-way surge benchmark: **rthym_moc**, **TSNet**, and **PTSNet**.

Runs selected cases on all selected engines and prints one table: **median
wall-clock time to complete one full simulation** for each tool (load/configure
the model, then integrate through the last time step). Each timed sample starts
from a fresh model build so the numbers reflect end-to-end completion cost, not
only the inner integration loop.

Models
------
0. **tnet3-valve** — PTSNet's TNET3 example network with a 1 s TCV closure. This
   is the default case because it is large enough for reliable 4-rank PTSNet.
1. **joukowsky** — instant valve closure on a single 3000 ft pipe (3 s, dt=0.01).
2. **standpipe** — open surge tank at the junction upstream of an instant closure
   (25 s, dt=0.001; appendix §B.8). Stub pipes use L = 2.1·a·dt so all three
   engines satisfy TSNet's dt < L/(2a) Courant check (see ``stub_length_m``).

Usage (from repository root):

    pip install -e ".[benchmark]"
    mpiexec -n 4 python examples/benchmark_ptsnet_vs_tsnet.py --warmup 0 --repeat 1

PTSNet requires ``mpi4py`` and should be launched with ``mpiexec``. The default
``tnet3-valve`` case is the MPI-safe desktop comparison target. The smaller
Joukowsky and standpipe cases remain useful microbenchmarks, but PTSNet 0.1.10
can hang on those tiny topologies with more than one MPI rank, so this script
skips their PTSNet rows under ``mpiexec -n N`` when ``N > 1``.

Optional flags:

    --warmup 1       discard this many runs before timing (default 1)
    --repeat 3       median over this many timed runs (default 3)
    --models all     run every built-in model (default: 0 = TNET3)
    --rthym-concurrency 4
                     run 4 independent rthym_moc simulations concurrently
    --skip-rthym     TSNet + PTSNet only
    --skip-tsnet     rthym_moc + PTSNet only
    --skip-ptsnet    rthym_moc + TSNet only
"""

from __future__ import annotations

import argparse
import math
import multiprocessing as mp
import os
import platform
import shutil
import statistics
import sys
import tempfile
import time
import uuid
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass

import numpy as np

# PTSNet 0.1.10 still references removed NumPy scalar aliases (1.24+).
for _np_alias, _builtin in (
    ("int", int),
    ("float", float),
    ("bool", bool),
    ("complex", complex),
):
    if not hasattr(np, _np_alias):
        setattr(np, _np_alias, _builtin)  # type: ignore[attr-defined]

FT_TO_M = 0.3048
IN_TO_MM = 25.4
GPM_TO_M3S = 6.309e-5

H_RES_FT = 150.0
L_FT = 3000.0
D_IN = 12.0
HW_C = 130.0
Q0_GPM = 500.0
A_WAVE_FT = 4000.0
A_S_FT2 = 1.0

# TSNet requires user dt < L/(2a) on every pipe. With L = k·a·dt, need k > 2.
TSNET_STUB_COURANT_FACTOR = 2.1

D_FT = D_IN / 12.0

H_RES_M = H_RES_FT * FT_TO_M
L_M = L_FT * FT_TO_M
D_MM = D_IN * IN_TO_MM
A_WAVE_M = A_WAVE_FT * FT_TO_M
Q0_M3S = Q0_GPM * GPM_TO_M3S
D_M = D_FT * FT_TO_M
A_S_M2 = A_S_FT2 * FT_TO_M**2

Hf_M = 10.67 * L_M * Q0_M3S**1.852 / (HW_C**1.852 * D_M**4.87)
H_MID_M = H_RES_M - Hf_M
H_MID_FT = H_MID_M / FT_TO_M


@dataclass(frozen=True)
class SurgeModelCase:
    """One surge-analysis scenario for cross-engine timing."""

    label: str
    description: str
    dt_s: float
    total_s: float
    monitor_node: str
    with_standpipe: bool
    source: str = "synthetic"
    example_name: str | None = None
    valve_id: str = "V1"
    rthym_valve_id: str | None = None
    wave_speed_m_s: float = A_WAVE_M
    closure_start_s: float = 0.0
    closure_end_s: float = 0.0
    ptsnet_parallel_safe: bool = False

    @property
    def n_steps(self) -> int:
        return int(round(self.total_s / self.dt_s))

    @property
    def stub_length_m(self) -> float:
        """Stub length (m) shared by rthym, TSNet INP, and PTSNet."""
        return TSNET_STUB_COURANT_FACTOR * A_WAVE_FT * self.dt_s * FT_TO_M


SURGE_MODELS: list[SurgeModelCase] = [
    SurgeModelCase(
        "tnet3-valve",
        "PTSNet TNET3 network with VALVE-179 closure (MPI-safe)",
        dt_s=0.005,
        total_s=3.0,
        monitor_node="JUNCTION-73",
        with_standpipe=False,
        source="ptsnet-example",
        example_name="TNET3",
        valve_id="VALVE-179",
        rthym_valve_id="_VALVE_VALVE-179",
        wave_speed_m_s=1200.0,
        closure_start_s=1.0,
        closure_end_s=2.0,
        ptsnet_parallel_safe=True,
    ),
    SurgeModelCase(
        "joukowsky",
        "Instant valve closure (Joukowsky slam)",
        dt_s=0.01,
        total_s=3.0,
        monitor_node="J1",
        with_standpipe=False,
    ),
    SurgeModelCase(
        "standpipe",
        "Open standpipe surge protection (A_s = 1 ft²)",
        dt_s=0.001,
        total_s=25.0,
        monitor_node="J1",
        with_standpipe=True,
    ),
]


def _timing_stats(samples: list[float]) -> tuple[float, float | None]:
    median = statistics.median(samples)
    if len(samples) < 2:
        return median, None
    mean = statistics.mean(samples)
    if mean <= 0.0:
        return median, None
    return median, statistics.stdev(samples) / mean * 100.0


def _sample_seconds(run_fn, warmup: int, repeat: int) -> tuple[float, float | None]:
    for _ in range(warmup):
        run_fn()
    samples = [run_fn() for _ in range(repeat)]
    return _timing_stats(samples)


def _joukowsky_inp() -> str:
    return f"""[TITLE]
Joukowsky Benchmark (TSNet vs PTSNet)

[OPTIONS]
 Units                LPS
 Headloss             H-W
 Trials               40
 Accuracy             0.001
 Unbalanced           Continue 10
 Quality              None

[JUNCTIONS]
 J1   0.000   0.000   ;

[RESERVOIRS]
 R1   {H_RES_M:.5f}   ;
 R2   {H_MID_M:.5f}   ;

[PIPES]
 P1  R1     J1     {L_M:.3f}  {D_MM:.3f}  {HW_C:.0f}    0      Open

[VALVES]
 V1  J1     R2     {D_MM:.3f}  TCV   0.001    0

[REPORT]
 Status  No
 Summary No

[END]
"""


def _standpipe_inp(stub_length_m: float) -> str:
    return f"""[TITLE]
Standpipe Surge Protection (TSNet vs PTSNet)

[OPTIONS]
 Units                LPS
 Headloss             H-W
 Trials               40
 Accuracy             0.001
 Unbalanced           Continue 10
 Quality              None

[JUNCTIONS]
 J1   0.000   0.000   ;
 J2   0.000   0.000   ;
 J3   0.000   0.000   ;

[RESERVOIRS]
 R1   {H_RES_M:.5f}   ;
 R2   {H_MID_M:.5f}   ;

[PIPES]
 P1  R1     J1     {L_M:.3f}  {D_MM:.3f}  {HW_C:.0f}    0      Open
 P2  J1     J2     {stub_length_m:.3f}  {D_MM:.3f}  {HW_C:.0f}    0      Open
 P3  J3     R2     {stub_length_m:.3f}  {D_MM:.3f}  {HW_C:.0f}    0      Open

[VALVES]
 V1  J2     J3     {D_MM:.3f}  TCV   0.001    0

[REPORT]
 Status  No
 Summary No

[END]
"""


def _ptsnet_example_inp_content(example_name: str) -> str:
    from ptsnet.utils.io import get_example_path

    with open(get_example_path(example_name), encoding="utf-8", errors="replace") as handle:
        return handle.read()


def _inp_content_for_case(case: SurgeModelCase) -> str:
    if case.source == "ptsnet-example":
        if not case.example_name:
            raise ValueError(f"{case.label} is missing example_name")
        return _ptsnet_example_inp_content(case.example_name)
    return _standpipe_inp(case.stub_length_m) if case.with_standpipe else _joukowsky_inp()


def _write_temp_inp(content: str) -> str:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".inp", delete=False) as handle:
        handle.write(content)
        return handle.name


def _mpi_context():
    try:
        from mpi4py import MPI

        comm = MPI.COMM_WORLD
        return MPI, comm, comm.Get_rank(), comm.Get_size()
    except Exception:
        return None, None, 0, 1


def _is_root_rank() -> bool:
    _mpi, _comm, rank, _size = _mpi_context()
    return rank == 0


@contextmanager
def _ptsnet_workdir():
    """Run PTSNet in an isolated directory so workspace folders stay out of the repo."""
    with tempfile.TemporaryDirectory(prefix="ptsnet_bench_") as tmp:
        previous = os.getcwd()
        os.chdir(tmp)
        try:
            yield tmp
        finally:
            os.chdir(previous)


@contextmanager
def _shared_ptsnet_case_dir(inp_content: str):
    """Shared temporary workspace for all MPI ranks in one PTSNet sample."""
    _mpi, comm, rank, size = _mpi_context()
    if size == 1 or comm is None:
        with _ptsnet_workdir():
            inp_path = _write_temp_inp(inp_content)
            try:
                yield inp_path, f"bench_{uuid.uuid4().hex[:8]}"
            finally:
                os.unlink(inp_path)
        return

    tmp_dir = None
    inp_path = None
    workspace = None
    if rank == 0:
        tmp_dir = tempfile.mkdtemp(prefix="ptsnet_bench_")
        inp_path = os.path.join(tmp_dir, "network.inp")
        with open(inp_path, "w", encoding="utf-8") as handle:
            handle.write(inp_content)
        workspace = f"bench_{uuid.uuid4().hex[:8]}"

    tmp_dir = comm.bcast(tmp_dir, root=0)
    inp_path = comm.bcast(inp_path, root=0)
    workspace = comm.bcast(workspace, root=0)
    comm.Barrier()

    previous = os.getcwd()
    os.chdir(tmp_dir)
    try:
        yield inp_path, workspace
    finally:
        os.chdir(previous)
        comm.Barrier()
        if rank == 0:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        comm.Barrier()


def _instant_valve_tsnet(model, dt_s: float) -> None:
    dtc = model.time_step
    model.valve_closure("V1", [dtc, 0.0, 0.0, 1])


def _configure_tsnet_transient(model, case: SurgeModelCase) -> None:
    if case.source == "ptsnet-example":
        closure_time = max(case.dt_s, case.closure_end_s - case.closure_start_s)
        model.valve_closure(case.valve_id, [closure_time, case.closure_start_s, 0.0, 1])
    else:
        _instant_valve_tsnet(model, case.dt_s)


def _configure_ptsnet_transient(sim, case: SurgeModelCase) -> None:
    if case.source == "ptsnet-example":
        sim.define_valve_operation(
            case.valve_id,
            initial_setting=1.0,
            final_setting=0.0,
            start_time=case.closure_start_s,
            end_time=case.closure_end_s,
        )
    else:
        sim.define_valve_settings(case.valve_id, np.array([0.0, case.dt_s]), np.array([1.0, 0.0]))


def _build_rthym_joukowsky_solver(dt_s: float):
    """Same topology as ``benchmark_matrix.py`` (V1 monitored; matches TSNet J1)."""
    import rthym_moc as m

    solver = m.MOCSolver()

    r1 = m.NodeInput()
    r1.id = "R1"
    r1.type = "PressureBoundary"
    r1.head = H_RES_FT

    v1 = m.NodeInput()
    v1.id = "V1"
    v1.type = "Valve"
    v1.diameter = D_IN
    v1.current_setting = 0.0
    v1.head = H_MID_FT

    r2 = m.NodeInput()
    r2.id = "R2"
    r2.type = "PressureBoundary"
    r2.head = H_MID_FT

    p1 = m.PipeInput()
    p1.id = "P1"
    p1.from_node = "R1"
    p1.to_node = "V1"
    p1.length = L_FT
    p1.diameter = D_IN
    p1.roughness = HW_C
    p1.flow_gpm = Q0_GPM

    p2 = m.PipeInput()
    p2.id = "P2"
    p2.from_node = "V1"
    p2.to_node = "R2"
    p2.length = A_WAVE_FT * dt_s
    p2.diameter = D_IN
    p2.roughness = HW_C
    p2.flow_gpm = 0.0

    solver.add_node(r1)
    solver.add_node(v1)
    solver.add_node(r2)
    solver.add_pipe(p1)
    solver.add_pipe(p2)
    return solver


def _build_rthym_standpipe_solver(dt_s: float, stub_length_m: float):
    """Open standpipe upstream of valve; monitor SP1 (matches appendix §B.8 layout)."""
    import rthym_moc as m

    L_short_ft = stub_length_m / FT_TO_M
    solver = m.MOCSolver()

    r1 = m.NodeInput()
    r1.id = "R1"
    r1.type = "PressureBoundary"
    r1.head = H_RES_FT

    sp1 = m.NodeInput()
    sp1.id = "SP1"
    sp1.type = "Standpipe"
    sp1.head = H_MID_FT
    sp1.tank_area = A_S_FT2

    v1 = m.NodeInput()
    v1.id = "V1"
    v1.type = "Valve"
    v1.diameter = D_IN
    v1.current_setting = 0.0
    v1.head = H_MID_FT

    r2 = m.NodeInput()
    r2.id = "R2"
    r2.type = "PressureBoundary"
    r2.head = H_MID_FT

    p1 = m.PipeInput()
    p1.id = "P1"
    p1.from_node = "R1"
    p1.to_node = "SP1"
    p1.length = L_FT
    p1.diameter = D_IN
    p1.roughness = HW_C
    p1.flow_gpm = Q0_GPM

    p2 = m.PipeInput()
    p2.id = "P2"
    p2.from_node = "SP1"
    p2.to_node = "V1"
    p2.length = L_short_ft
    p2.diameter = D_IN
    p2.roughness = HW_C
    p2.flow_gpm = Q0_GPM

    p3 = m.PipeInput()
    p3.id = "P3"
    p3.from_node = "V1"
    p3.to_node = "R2"
    p3.length = L_short_ft
    p3.diameter = D_IN
    p3.roughness = HW_C
    p3.flow_gpm = 0.0

    solver.add_node(r1)
    solver.add_node(sp1)
    solver.add_node(v1)
    solver.add_node(r2)
    solver.add_pipe(p1)
    solver.add_pipe(p2)
    solver.add_pipe(p3)
    return solver


def _run_rthym_once(case: SurgeModelCase) -> tuple[float, np.ndarray]:
    node_id = case.monitor_node if case.source == "ptsnet-example" else ("SP1" if case.with_standpipe else "V1")
    t0 = time.perf_counter()
    if case.source == "ptsnet-example":
        import rthym_moc as m

        inp_content = _inp_content_for_case(case)
        inp_path = _write_temp_inp(inp_content)
        try:
            solver = m.load_inp(inp_path)
        finally:
            os.unlink(inp_path)
        if case.rthym_valve_id:
            solver.set_valve_schedule(
                case.rthym_valve_id,
                [
                    (case.closure_start_s, 100.0),
                    (case.closure_end_s, 0.0),
                ],
            )
    elif case.with_standpipe:
        solver = _build_rthym_standpipe_solver(case.dt_s, case.stub_length_m)
    else:
        solver = _build_rthym_joukowsky_solver(case.dt_s)
    results = solver.run(case.total_s, case.dt_s, -14.0, case.dt_s)
    elapsed = time.perf_counter() - t0
    h_ft = np.array(results["node_head"][node_id], dtype=float).reshape(-1)
    return elapsed, h_ft


def _run_rthym_transient(
    case: SurgeModelCase,
    warmup: int,
    repeat: int,
) -> tuple[float, float | None, np.ndarray]:
    last_heads: np.ndarray | None = None

    def _timed_run() -> float:
        nonlocal last_heads
        elapsed, last_heads = _run_rthym_once(case)
        return elapsed

    elapsed, cv_pct = _sample_seconds(_timed_run, warmup=warmup, repeat=repeat)
    assert last_heads is not None
    return elapsed, cv_pct, last_heads


def _run_rthym_once_for_pool(case: SurgeModelCase) -> float:
    elapsed, _heads = _run_rthym_once(case)
    return elapsed


def _run_rthym_concurrent(
    case: SurgeModelCase,
    *,
    workers: int,
    warmup: int,
    repeat: int,
) -> tuple[float, float | None, float]:
    """Run independent rthym_moc simulations in separate processes.

    Returns (batch wall seconds, average single-run seconds inside the workers).
    The batch wall time includes process-pool setup for an honest throughput smoke
    test of the simple setup a user would run from Python.
    """

    def _batch() -> tuple[float, float]:
        t0 = time.perf_counter()
        with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn")) as pool:
            worker_elapsed = list(pool.map(_run_rthym_once_for_pool, [case] * workers))
        batch_elapsed = time.perf_counter() - t0
        return batch_elapsed, statistics.mean(worker_elapsed)

    for _ in range(warmup):
        _batch()

    samples = [_batch() for _ in range(repeat)]
    batch_seconds, batch_cv_pct = _timing_stats([sample[0] for sample in samples])
    worker_seconds = statistics.median(sample[1] for sample in samples)
    return batch_seconds, batch_cv_pct, worker_seconds


def _run_tsnet_transient(
    case: SurgeModelCase,
    warmup: int,
    repeat: int,
) -> tuple[float, float | None, np.ndarray, np.ndarray]:
    import tsnet

    inp_content = _inp_content_for_case(case)

    def _prepare() -> object:
        inp_path = _write_temp_inp(inp_content)
        try:
            model = tsnet.network.TransientModel(inp_path)
        finally:
            os.unlink(inp_path)
        model.set_wavespeed(case.wave_speed_m_s)
        model.set_time(case.total_s, case.dt_s)
        _configure_tsnet_transient(model, case)
        if case.with_standpipe:
            model.add_surge_tank(case.monitor_node, [A_S_M2], tank_type="open")
        return tsnet.simulation.Initializer(model, 0.0, "DD")

    def _timed_run() -> float:
        t0 = time.perf_counter()
        prepared = _prepare()
        tsnet.simulation.MOCSimulator(prepared)
        return time.perf_counter() - t0

    elapsed, cv_pct = _sample_seconds(_timed_run, warmup=warmup, repeat=repeat)

    prepared = _prepare()
    finished = tsnet.simulation.MOCSimulator(prepared)
    heads = np.array(finished.get_node(case.monitor_node)._head, dtype=float).reshape(-1)
    times = np.array(finished.simulation_timestamps, dtype=float).reshape(-1)
    return elapsed, cv_pct, heads, times


def _run_ptsnet_transient(
    case: SurgeModelCase,
    warmup: int,
    repeat: int,
) -> tuple[float, float | None, np.ndarray, np.ndarray]:
    from ptsnet.simulation.sim import PTSNETSimulation

    inp_content = _inp_content_for_case(case)
    settings = {
        "time_step": case.dt_s,
        "duration": case.total_s,
        "default_wave_speed": case.wave_speed_m_s,
        "show_progress": False,
        # Avoid PTSNet's parallel HDF5/workspace result save during MPI benchmarks.
        # The in-memory worker results are enough for timing and peak extraction.
        "save_results": False,
        "warnings_on": False,
        "skip_compatibility_check": True,
    }

    def _one_transient() -> tuple[float, np.ndarray | None, np.ndarray | None]:
        mpi, comm, rank, size = _mpi_context()
        with _shared_ptsnet_case_dir(inp_content) as (inp_path, workspace):
            if comm is not None:
                comm.Barrier()
            t0 = time.perf_counter()
            sim = PTSNETSimulation(
                workspace_name=workspace,
                inpfile=inp_path,
                settings=settings,
            )
            _configure_ptsnet_transient(sim, case)
            if case.with_standpipe:
                sim.add_surge_protection(case.monitor_node, "open", A_S_M2)
            sim.run()
            elapsed_local = time.perf_counter() - t0
            elapsed = (
                comm.allreduce(elapsed_local, op=mpi.MAX)
                if comm is not None and mpi is not None
                else elapsed_local
            )

            local_peak = -np.inf
            try:
                local_heads = np.array(sim["node"].head[case.monitor_node], dtype=float).reshape(-1)
                finite_heads = local_heads[np.isfinite(local_heads)]
                if finite_heads.size:
                    local_peak = float(np.max(finite_heads))
            except Exception:
                pass

            if comm is not None and mpi is not None:
                global_peak = comm.allreduce(local_peak, op=mpi.MAX)
            else:
                global_peak = local_peak
            peak_heads = (
                np.array([global_peak], dtype=float)
                if np.isfinite(global_peak)
                else np.array([np.nan], dtype=float)
            )

            if rank == 0:
                times = np.array(sim["time"], dtype=float).reshape(-1)
                return elapsed, peak_heads, times
            return elapsed, np.array([], dtype=float), np.array([], dtype=float)

    elapsed, cv_pct = _sample_seconds(lambda: _one_transient()[0], warmup=warmup, repeat=repeat)
    _last_elapsed, heads, times = _one_transient()
    assert heads is not None and times is not None
    return elapsed, cv_pct, heads, times


@dataclass
class EngineTiming:
    label: str
    elapsed_ms: float | None
    peak_head_ft: float | None
    cv_pct: float | None = None
    error: str | None = None


@dataclass
class ConcurrentRthymTiming:
    workers: int
    batch_wall_ms: float | None = None
    batch_cv_pct: float | None = None
    worker_mean_ms: float | None = None
    error: str | None = None

    @property
    def throughput_ms_per_run(self) -> float | None:
        if self.batch_wall_ms is not None and self.workers > 0:
            return self.batch_wall_ms / self.workers
        return None


@dataclass
class ModelTimingRow:
    case: SurgeModelCase
    rthym: EngineTiming
    tsnet: EngineTiming
    ptsnet: EngineTiming
    rthym_concurrent: ConcurrentRthymTiming | None = None

    @property
    def ptsnet_speedup(self) -> float | None:
        if self.tsnet.elapsed_ms and self.ptsnet.elapsed_ms:
            return self.tsnet.elapsed_ms / self.ptsnet.elapsed_ms
        return None


def _run_model_row(
    case: SurgeModelCase,
    *,
    warmup: int,
    repeat: int,
    run_rthym: bool,
    run_tsnet: bool,
    run_ptsnet: bool,
    rthym_concurrency: int,
) -> ModelTimingRow:
    rthym_timing = EngineTiming("rthym_moc", None, None)
    tsnet_timing = EngineTiming("TSNet", None, None)
    ptsnet_timing = EngineTiming("PTSNet", None, None)
    rthym_concurrent: ConcurrentRthymTiming | None = None

    if run_rthym and _is_root_rank():
        try:
            elapsed, cv_pct, heads = _run_rthym_transient(case, warmup=warmup, repeat=repeat)
            rthym_timing = EngineTiming("rthym_moc", elapsed * 1000.0, float(np.max(heads)), cv_pct)
        except Exception as exc:
            rthym_timing = EngineTiming("rthym_moc", None, None, error=str(exc))

        if rthym_concurrency > 1:
            try:
                batch_s, batch_cv_pct, worker_s = _run_rthym_concurrent(
                    case,
                    workers=rthym_concurrency,
                    warmup=warmup,
                    repeat=repeat,
                )
                rthym_concurrent = ConcurrentRthymTiming(
                    workers=rthym_concurrency,
                    batch_wall_ms=batch_s * 1000.0,
                    batch_cv_pct=batch_cv_pct,
                    worker_mean_ms=worker_s * 1000.0,
                )
            except Exception as exc:
                rthym_concurrent = ConcurrentRthymTiming(rthym_concurrency, error=str(exc))

    if run_tsnet and _is_root_rank():
        try:
            elapsed, cv_pct, heads, _times = _run_tsnet_transient(case, warmup=warmup, repeat=repeat)
            tsnet_timing = EngineTiming("TSNet", elapsed * 1000.0, float(np.max(heads)) / FT_TO_M, cv_pct)
        except Exception as exc:
            tsnet_timing = EngineTiming("TSNet", None, None, error=str(exc))

    if run_ptsnet:
        _mpi, _comm, _rank, mpi_size = _mpi_context()
        if mpi_size > 1 and not case.ptsnet_parallel_safe:
            if _is_root_rank():
                ptsnet_timing = EngineTiming(
                    "PTSNet",
                    None,
                    None,
                    error=(
                        "skipped: PTSNet 0.1.10 can hang on this tiny synthetic "
                        "topology with MPI size > 1; run it with mpiexec -n 1 "
                        "or use the tnet3-valve case for 4-rank comparison"
                    ),
                )
            return ModelTimingRow(
                case=case,
                rthym=rthym_timing,
                tsnet=tsnet_timing,
                ptsnet=ptsnet_timing,
                rthym_concurrent=rthym_concurrent,
            )
        try:
            elapsed, cv_pct, heads, _times = _run_ptsnet_transient(case, warmup=warmup, repeat=repeat)
            if _is_root_rank():
                ptsnet_timing = EngineTiming("PTSNet", elapsed * 1000.0, float(np.max(heads)) / FT_TO_M, cv_pct)
        except Exception as exc:
            if _is_root_rank():
                ptsnet_timing = EngineTiming("PTSNet", None, None, error=str(exc))

    return ModelTimingRow(
        case=case,
        rthym=rthym_timing,
        tsnet=tsnet_timing,
        ptsnet=ptsnet_timing,
        rthym_concurrent=rthym_concurrent,
    )


def _print_header() -> None:
    _mpi, _comm, _rank, mpi_size = _mpi_context()

    print("=" * 120)
    print("  rthym_moc vs TSNet vs PTSNet — surge-model speed comparison")
    print("=" * 120)
    print(f"  Platform  {platform.platform()}")
    print(f"  Python    {sys.version.split()[0]}")
    if mpi_size is not None:
        print(f"  MPI size  {mpi_size} process(es)")
    else:
        print("  MPI       not available (install mpi4py; run with mpiexec -n 1)")
    print("  Physics   default case is PTSNet TNET3 with VALVE-179 closure")
    print(
        "  Timing: each column = median wall-clock to **complete** one full run "
        "(build/load + configure + integrate through the final step). "
        "Every timed sample uses a freshly built model."
    )
    print()


def _fmt_ratio_over(numer: float | None, denom: float | None) -> str:
    """Wall-time ratio numer÷denom (e.g. TSNet ms ÷ rthym ms = how many × slower TSNet)."""
    if numer is not None and denom is not None and denom > 0:
        return f"{numer / denom:.1f}x"
    return "n/a"


def _fmt_cv(value: float | None) -> str:
    return f"{value:.1f}" if value is not None else "·"


def _print_table(rows: list[ModelTimingRow]) -> None:
    print(
        "  Median ms = wall-clock to finish one full simulation (fresh model each "
        "sample: build/load + configure + every time step to completion)."
    )
    print()
    concurrent_workers = next(
        (row.rthym_concurrent.workers for row in rows if row.rthym_concurrent is not None),
        None,
    )
    concurrent_header = (
        f"{f'rthym×{concurrent_workers}(ms)':>14} {f'×{concurrent_workers}/run':>10} "
        if concurrent_workers is not None
        else ""
    )
    header = (
        f"{'Model':<12} {'T(s)':>6} {'Steps':>6} "
        f"{'rthym(ms)':>10} {concurrent_header}{'TSNet(ms)':>10} {'PTSNet(ms)':>11} "
        f"{'TS/rth':>8} {'PT/rth':>8} {'PT/TS':>8} "
        f"{'CV%(r|T|P)':>12} {'Peak·r|T|P':>16}"
    )
    print(header)
    print("-" * len(header))

    ptsnet_vs_tsnet: list[float] = []
    for row in rows:
        case = row.case
        rh = f"{row.rthym.elapsed_ms:.2f}" if row.rthym.elapsed_ms is not None else "n/a"
        rh_conc = ""
        if concurrent_workers is not None:
            if row.rthym_concurrent and row.rthym_concurrent.batch_wall_ms is not None:
                rh_batch = f"{row.rthym_concurrent.batch_wall_ms:.2f}"
                rh_per_run_value = row.rthym_concurrent.throughput_ms_per_run
                rh_per_run = f"{rh_per_run_value:.2f}" if rh_per_run_value is not None else "n/a"
            else:
                rh_batch = "n/a"
                rh_per_run = "n/a"
            rh_conc = f"{rh_batch:>14} {rh_per_run:>10} "
        ts_ms = row.tsnet.elapsed_ms
        pt_ms = row.ptsnet.elapsed_ms
        ts_s = f"{ts_ms:.2f}" if ts_ms is not None else "n/a"
        pt_s = f"{pt_ms:.2f}" if pt_ms is not None else "n/a"
        ts_over_rth = _fmt_ratio_over(ts_ms, row.rthym.elapsed_ms)
        pt_over_rth = _fmt_ratio_over(pt_ms, row.rthym.elapsed_ms)
        pt_ts = (
            f"{row.ptsnet_speedup:.1f}x"
            if row.ptsnet_speedup is not None and row.ptsnet_speedup >= 1.0
            else (
                f"TS {1.0 / row.ptsnet_speedup:.1f}x"
                if row.ptsnet_speedup is not None and row.ptsnet_speedup > 0
                else "n/a"
            )
        )

        pk_r = f"{row.rthym.peak_head_ft:.1f}" if row.rthym.peak_head_ft is not None else "·"
        pk_t = f"{row.tsnet.peak_head_ft:.1f}" if row.tsnet.peak_head_ft is not None else "·"
        pk_p = f"{row.ptsnet.peak_head_ft:.1f}" if row.ptsnet.peak_head_ft is not None else "·"
        peak3 = f"{pk_r}|{pk_t}|{pk_p}"
        cv3 = f"{_fmt_cv(row.rthym.cv_pct)}|{_fmt_cv(row.tsnet.cv_pct)}|{_fmt_cv(row.ptsnet.cv_pct)}"

        print(
            f"{case.label:<12} {case.total_s:6.1f} {case.n_steps:6d} "
            f"{rh:>10} {rh_conc}{ts_s:>10} {pt_s:>11} "
            f"{ts_over_rth:>8} {pt_over_rth:>8} {pt_ts:>8} "
            f"{cv3:>12} {peak3:>16}"
        )

        if row.rthym.error:
            print(f"  rthym_moc error ({case.label}): {row.rthym.error}", file=sys.stderr)
        if row.rthym_concurrent and row.rthym_concurrent.error:
            print(
                f"  rthym_moc concurrent error ({case.label}): {row.rthym_concurrent.error}",
                file=sys.stderr,
            )
        if row.tsnet.error:
            print(f"  TSNet error ({case.label}): {row.tsnet.error}", file=sys.stderr)
        if row.ptsnet.error:
            print(f"  PTSNet error ({case.label}): {row.ptsnet.error}", file=sys.stderr)
        if row.ptsnet_speedup is not None:
            ptsnet_vs_tsnet.append(row.ptsnet_speedup)

    print()
    print(
        "  TS/rth, PT/rth = how many × slower TSNet or PTSNet is vs rthym_moc "
        "(same complete-run definition for all three)."
    )
    if concurrent_workers is not None:
        print(
            f"  rthym×{concurrent_workers}(ms) = wall time for {concurrent_workers} "
            "simultaneous, independent rthym_moc model instances in separate Python processes; "
            f"×{concurrent_workers}/run = batch throughput as estimated per-instance latency "
            f"(wall ÷ {concurrent_workers}), not parallel speedup of one simulation."
        )
    print(
        "  Peak·r|T|P = peak head (ft) rthym | TSNet | PTSNet "
        "(monitored node depends on the model row)."
    )
    print(
        "  CV%(r|T|P) = coefficient of variation of timed samples (%) for "
        "rthym_moc | TSNet | PTSNet; · means repeat=1 or unavailable."
    )

    if ptsnet_vs_tsnet:
        faster = [s for s in ptsnet_vs_tsnet if s >= 1.0]
        if faster:
            print(
                f"  PTSNet vs TSNet faster on {len(faster)}/{len(ptsnet_vs_tsnet)} model(s); "
                f"median {statistics.median(faster):.1f}x."
            )
        slower = [s for s in ptsnet_vs_tsnet if s < 1.0]
        if slower:
            print(
                f"  TSNet vs PTSNet faster on {len(slower)}/{len(ptsnet_vs_tsnet)} model(s); "
                f"median {statistics.median(1.0 / s for s in slower):.1f}x."
            )
    print()


def _print_model_descriptions(cases: list[SurgeModelCase]) -> None:
    print("Models:")
    for index, case in enumerate(cases):
        print(f"  [{index}] {case.label:<12} {case.description}")
    print()


def _check_mpi_warning() -> None:
    _mpi, _comm, _rank, mpi_size = _mpi_context()
    if _comm is None:
        print(
            "  Warning: mpi4py is not installed. PTSNet requires mpi4py.\n"
            "  Install with: pip install mpi4py ptsnet\n",
            file=sys.stderr,
        )
        return

    if mpi_size == 1:
        print(
            "  Note: PTSNet is running with MPI size 1. Use mpiexec -n 4 for the\n"
            "        default TNET3 desktop parallel comparison.\n",
            file=sys.stderr,
        )
    elif mpi_size != 4:
        print(
            f"  Note: MPI size is {mpi_size} (docs recommend -n 4 for typical desktops).\n",
            file=sys.stderr,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warmup", type=int, default=1, help="warm-up runs per model")
    parser.add_argument("--repeat", type=int, default=3, help="timed runs per model (median)")
    parser.add_argument(
        "--rthym-concurrency",
        type=int,
        default=1,
        help="run this many independent rthym_moc simulations concurrently (1 disables)",
    )
    parser.add_argument(
        "--models",
        type=str,
        default="0",
        help="comma-separated model indices, or 'all' (default: 0 = MPI-safe TNET3)",
    )
    parser.add_argument("--skip-rthym", action="store_true", help="TSNet + PTSNet only")
    parser.add_argument("--skip-tsnet", action="store_true", help="rthym_moc + PTSNet only")
    parser.add_argument("--skip-ptsnet", action="store_true", help="rthym_moc + TSNet only")
    args = parser.parse_args()

    if args.models.strip().lower() == "all":
        cases = list(SURGE_MODELS)
    elif args.models.strip():
        indices = [int(item.strip()) for item in args.models.split(",")]
        cases = [SURGE_MODELS[index] for index in indices]
    else:
        cases = [SURGE_MODELS[0]]

    if _is_root_rank():
        _print_header()
        _check_mpi_warning()
        _print_model_descriptions(cases)

    run_tsnet = not args.skip_tsnet
    run_ptsnet = not args.skip_ptsnet
    run_rthym = not args.skip_rthym
    rthym_concurrency = max(1, args.rthym_concurrency)

    if run_rthym and _is_root_rank():
        try:
            import rthym_moc  # noqa: F401
        except ImportError:
            print("  rthym_moc not importable; skipping. Use --skip-rthym to silence.", file=sys.stderr)
            run_rthym = False

    if run_tsnet and _is_root_rank():
        try:
            import tsnet  # noqa: F401
            if int(np.__version__.split(".", maxsplit=1)[0]) >= 2:
                print(
                    "  TSNet disabled: detected NumPy>=2, which breaks TSNet discretization "
                    "(TypeError at set_time). Install benchmark deps with: "
                    'pip install "numpy<2" tsnet==0.3.1',
                    file=sys.stderr,
                )
                run_tsnet = False
        except ImportError:
            print("  TSNet not installed; use: pip install tsnet==0.3.1", file=sys.stderr)
            run_tsnet = False

    if run_ptsnet:
        try:
            import ptsnet  # noqa: F401
            import h5py  # noqa: F401
            import tqdm  # noqa: F401
            from mpi4py import MPI  # noqa: F401
        except ImportError:
            print(
                "  PTSNet stack not installed; use: pip install ptsnet==0.1.10 mpi4py h5py tqdm",
                file=sys.stderr,
            )
            run_ptsnet = False

    rows: list[ModelTimingRow] = []
    for case in cases:
        if _is_root_rank():
            print(f"  Running {case.label} ({case.n_steps} steps) …")
        rows.append(
            _run_model_row(
                case,
                warmup=args.warmup,
                repeat=args.repeat,
                run_rthym=run_rthym,
                run_tsnet=run_tsnet,
                run_ptsnet=run_ptsnet,
                rthym_concurrency=rthym_concurrency,
            )
        )

    if _is_root_rank():
        print()
        _print_table(rows)


if __name__ == "__main__":
    main()
