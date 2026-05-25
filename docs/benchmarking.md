# Performance Benchmarking Guide

This document describes how RTHYM-MOC reports **runtime performance** alongside
[TSNet](https://github.com/glorialulu/TSNet), a widely used open-source MOC
library in Python. The same benchmark networks are run on both solvers so you
can compare wall-clock time on equivalent physics. Solver **correctness** is
documented separately in [docs/validation.md](validation.md).

## Purpose

RTHYM-MOC was developed for interactive transient simulation—including the
R-THYM web application—where responsiveness in the browser matters. The
time-stepping loop is implemented in C++17 behind a thin Python API. TSNet is a
natural comparison point because it solves the same 1-D MOC problem class. A
representative timing result on developer hardware is:

> On an equivalent Joukowsky instant-closure case, RTHYM-MOC completes the same
> time history in roughly **200–400× less wall-clock time** than TSNet on typical
> developer hardware.

Exact ratios depend on CPU, Python version, and whether the extension is built
with optimizations. Treat published numbers as **reproducible studies**, not CI
gates.

## Standard Benchmark Case

Both engines use the classical single-pipe Joukowsky slam (see appendix §B.6):

| Parameter | Value |
|---|---|
| Upstream reservoir head | 150 ft |
| Pipe length | 3000 ft |
| Pipe diameter | 12 in |
| Hazen-Williams C | 130 |
| Initial flow | 500 GPM |
| Wave speed | 4000 ft/s |
| Time step | 0.01 s |
| Duration | 3.0 s (~300 steps) |
| Transient event | Instant valve closure at t = 0 |

**Fair-comparison settings** (enforced in `examples/benchmark_vs_tsnet.py`):

- unsteady-friction correction disabled in RTHYM-MOC (`usf_tau = dt`)
- identical wave speed and time step passed to TSNet
- comparable network topology (reservoir → pipe → closed valve → short stub → reservoir)

## How To Run

Install the optional TSNet dependency, then run from the repository root.

**Single case** (physics + timing summary):

```bash
pip install tsnet==0.3.1
python examples/benchmark_vs_tsnet.py
```

**Performance matrix** (multiple grid sizes, tabulated speedups):

```bash
python examples/benchmark_matrix.py
```

The matrix sweeps time step and duration on the same Joukowsky network. Each row
reports step count, approximate segment count, median wall time (warm-up +
repeats), speedup, and first-cycle RMS head difference. Use `--skip-tsnet` for
RTHYM-MOC-only timings, or `--cases 0,1,2` to run a subset.

`benchmark_vs_tsnet.py` prints, for each engine:

- first-step Joukowsky head and error vs the analytical formula
- transient maximum head and error vs the theoretical envelope
- wall-clock execution time for the full transient
- speed ratio (TSNet time ÷ RTHYM-MOC time)
- RMS head difference over 0–1.5 s (physics agreement check)

Example output shape:

```
  Execution time     : 0.85 ms  (300 time steps)    # rthym_moc
  Execution time     : 65.2 ms  (300 time steps)    # TSNet
  Speed ratio        : 370x  (rthym_moc vs TSNet)
```

## Documented Results

Long-form methodology and tabulated physics results are in
[docs/appendix_b_verification.md](appendix_b_verification.md) §B.6.

Representative results from that study (single machine, pure steady-friction MOC):

| Engine | First-step error vs analytical | Wall time (300 steps) |
|---|---:|---:|
| RTHYM-MOC | 0.02 % | **< 1 ms** |
| TSNet | 0.04 % | **~65 ms** |
| Speed ratio | — | **~200–400×** |

Before citing a speedup in papers or README material, re-run
`examples/benchmark_matrix.py` (or `benchmark_vs_tsnet.py` for one row) on your
target hardware and record the printed ratio.

## Relationship To Validation

| Question | Where to look |
|---|---|
| Is the MOC implementation correct? | `pytest -q`, [docs/validation.md](validation.md), R-THYM / analytical regressions |
| Does RTHYM-MOC agree with TSNet physics? | `benchmark_vs_tsnet.py`, appendix §B.6 (~0.175 ft RMS on first cycle) |
| Is RTHYM-MOC faster than TSNet? | This guide and `benchmark_vs_tsnet.py` |

TSNet is intentionally **not** installed in default CI. Physics agreement is
documented; wall-clock time is left to local reproduction because it is
environment-sensitive.

## Extending Performance Benchmarks

When adding new performance studies:

- keep the case definition in `examples/` or a dedicated script, not in default
  `pytest` unless the test only asserts physics with a generous time ceiling
- document network parameters, grid size, and any solver options that affect
  fairness (USF, Courant adjustment, segment count)
- record hardware and `rthym_moc.__version__` in the appendix or commit message
- do not check in machine-specific millisecond thresholds as hard CI assertions
