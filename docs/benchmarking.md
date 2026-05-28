# Performance Benchmarking Guide

This guide compares **wall-clock time to complete a transient simulation** across
three open-source 1-D MOC engines:

| Engine | Implementation | Typical parallelism |
|--------|----------------|-------------------|
| **[rthym_moc](..)** (RTHYM-MOC) | C++17 core, thin Python API | Single process (multi-threaded BLAS only if linked) |
| **[TSNet](https://github.com/glorialulu/TSNet)** | Pure Python MOC | **Single process** |
| **[PTSNet](https://github.com/gandresr/PTSNET)** | Vectorized / distributed MOC | **MPI** (`mpiexec -n N`; 4 ranks is verified on the default TNET3 case) |

The **primary** comparison script is `examples/benchmark_ptsnet_vs_tsnet.py`. Its
default case runs PTSNet's TNET3 transient network on all three tools and prints
one table with median completion times and speed ratios.

Solver **correctness** is documented separately in
[docs/validation.md](validation.md). Long-form physics checks are in
[docs/appendix_b_verification.md](appendix_b_verification.md) §B.6–B.8.

---

## What we measure

For each tool we record **median wall-clock time to finish one full run**:

1. Build or load the model (INP / native network).
2. Configure wave speed, time step, valve closure, and surge devices.
3. Integrate through the **last** time step.

Each timed sample uses a **fresh** model so the number includes setup cost, not
only the inner loop. That matches the question: *how long until this simulation
is done?*

We intentionally include model build and configuration time to reflect the total
latency of the workflow. Users rarely run the solver in isolation; they run it as
part of an iterative design cycle. Therefore, the total time to "results ready" is
the primary metric of interest.

The timing starts inside an already-running Python process, so Python interpreter
startup is **not** included in the single-run `rthym(ms)`, `TSNet(ms)`, or
`PTSNet(ms)` columns. The optional `rthym×N(ms)` throughput column does include the
simple process-pool launch overhead for the independent worker processes.

The script can also report optional **rthym_moc process throughput** with
`--rthym-concurrency N`. That launches `N` simultaneous, independent fresh
rthym_moc model instances in separate Python processes and reports both the batch
wall time and wall time divided by `N`. This is a throughput check, not the same
thing as PTSNet's MPI ranks cooperating on one simulation.

The current primary table combines setup and solve time. That is deliberate for
workflow latency, but it does not yet separate INP parsing/model construction from
the MOC integration loop. Use the numbers as end-to-end timing unless a future
instrumented table explicitly reports setup and solve phases separately.

**Default comparison model** (same INP loaded by all three engines):

| Model | Duration | Time step | Steps (requested) | Why it is the default |
|-------|----------|-----------|-------------------|-----------------------|
| **TNET3 valve closure** | 3 s | 0.005 s | 600 | Large enough for reliable `mpiexec -n 4` PTSNet partitioning |

The default row uses PTSNet's bundled `TNET3.inp` network and closes `VALVE-179`
from 100% open to closed between 1 and 2 s. TSNet needs `dt < 0.00762 s` for this
network, so the benchmark requests `dt = 0.005 s`.

**Supplementary small surge models** (same script, useful for rthym_moc/TSNet and
single-rank PTSNet checks):

| Model | Duration | Time step | Steps (requested) | Appendix |
|-------|----------|-----------|-------------------|----------|
| **Joukowsky** | 3 s | 0.01 s | 300 | §B.6 — instant valve closure |
| **Standpipe** | 25 s | 0.001 s | 25 000 | §B.8 — open surge tank (A_s = 1 ft²) |

Shared physics (Joukowsky row): 150 ft reservoir, 3000 ft × 12 in pipe, HW C = 130,
500 GPM, a = 4000 ft/s. Standpipe adds an open tank at the junction upstream of the
valve. Stub pipes use **L = 2.1·a·dt** so TSNet’s Courant rule **dt &lt; L/(2a)**
passes on the short links (see [Standpipe stub length](#standpipe-stub-length)).

**rthym_moc** uses `usf_tau = dt` (unsteady friction off) on the Joukowsky-style
network so comparisons stay on pure steady-friction MOC where possible.

---

## Parallelism: how many processes for PTSNet?

PTSNet is designed for **MPI**. Launch it with `mpiexec` (even for one rank). The
desktop comparison is **4 MPI ranks** on the default TNET3 case.

| Setting | Command | When to use |
|---------|---------|-------------|
| Desktop target | `mpiexec -n 4` | Default TNET3 comparison; verified in WSL2/Python 3.12 |
| Single-rank fallback | `mpiexec -n 1` | Useful when MPI launch is unavailable or for PTSNet microbenchmark smoke checks |

**TSNet** and **rthym_moc** in these benchmarks are **single-process**. Comparing
`mpiexec -n 4` PTSNet to single-process TSNet is the intended desktop story.

PTSNet 0.1.10 can hang when its MPI partitioner is given the tiny synthetic
Joukowsky/standpipe topologies. The script skips PTSNet for those rows when
`MPI size > 1`; run them with `mpiexec -n 1` or skip PTSNet when using
`--models all`.

The script header prints `MPI size N process(es)` so you can confirm `-n` was
honored. Document the rank count next to every timing table.

---

## Run the three-way benchmark

From the repository root:

```bash
pip install -e ".[benchmark]"
mpiexec -n 4 python examples/benchmark_ptsnet_vs_tsnet.py --warmup 0 --repeat 1
```

For publication-quality repeatability, prefer at least 30 timed samples:

```bash
mpiexec -n 4 python examples/benchmark_ptsnet_vs_tsnet.py --warmup 3 --repeat 30
```

The script reports the median wall-clock time and a `CV%(r|T|P)` column when
multiple repeats are used. CV is the coefficient of variation
(`standard deviation / mean × 100`) and is a compact indicator of timing stability.

Optional flags:

- `--warmup 1 --repeat 3` — fuller median timing run
- `--models 0` — default TNET3 valve-closure comparison
- `--models 1`, `--models 2`, or `--models all` — supplementary small cases
- `--rthym-concurrency 4` — add rthym_moc 4-process throughput columns
- `--skip-rthym`, `--skip-tsnet`, `--skip-ptsnet` — subset of engines

**Dependencies:** `numpy<2`, `setuptools<81`, `numba`, `mpi4py`, `h5py`, `tqdm`
(see `[project.optional-dependencies] benchmark` in `pyproject.toml`). The script
patches legacy `np.int` / `np.float` aliases required by PTSNet 0.1.10.

If PTSNet cannot find EPANET, add a WNTR symlink:

`…/site-packages/wntr/epanet/Linux/libepanet.so` → `../libepanet/linux-x64/libepanet2.so`

---

## Measured results (WSL2, MPI size 4)

Environment: Linux 6.6.87 (WSL2), Python 3.12, `mpiexec -n 4`, TNET3 default case,
`--warmup 0 --repeat 1`. Re-run on your hardware before citing exact milliseconds.

Hardware for this representative run:

| Component | Specification |
|-----------|---------------|
| CPU | AMD Ryzen 7 7735HS with Radeon Graphics; 8 cores / 16 threads exposed to WSL |
| Memory | 6.6 GiB available to WSL |
| Workspace storage | `/dev/sdd`, 1007G filesystem, 929G available, mounted at `/` |
| Virtualization | WSL2 |

Limitations: MPI performance reported on WSL2 may be subject to hypervisor and
virtual network latency. Bare-metal Linux can exhibit different PTSNet scaling
characteristics, especially for short transients where communication overhead is a
large part of total runtime.

```
Model          T(s)  Steps  rthym(ms)  TSNet(ms)  PTSNet(ms)   TS/rth   PT/rth    PT/TS  CV%(r|T|P)       Peak·r|T|P
---------------------------------------------------------------------------------------------------------------------
tnet3-valve     3.0    600     107.36   20640.33     1428.45   192.3x    13.3x    14.4x        ·|·|· 871.5|867.2|866.3
```

The `·|·|·` CV entry means this documented row was a smoke run with `--repeat 1`.
Use `--repeat 30` before citing stable ratios in academic work.

A single-rank TNET3 smoke run on the same session completed as:

```
tnet3-valve     3.0    600      68.73   17249.51      620.47   251.0x     9.0x    27.8x 871.5|867.2|866.3
```

The 4-rank PTSNet result is slower than the 1-rank result on this short 3 s
transient because MPI setup/communication dominates the tiny runtime. The
important result is that the 4-rank comparison now completes on a PTSNet-supported
network, instead of hanging on under-sized synthetic topologies.

### How to read the table

Representative clock times for the TNET3 valve-closure case in the same WSL2
environment:

| Column | Representative value | Clock-time meaning |
|--------|---------------------:|--------------------|
| **rthym(ms)** | 107.36 ms | One rthym_moc run from INP load/build through `solver.run()` completion |
| **rthym×4(ms)** | 1817.20 ms | Wall time for four simultaneous, independent rthym_moc model instances in separate Python processes |
| **×4/run** | 454.30 ms | Batch throughput expressed as estimated per-instance latency (`1817.20 / 4`), not parallel speedup of one simulation |
| **TSNet(ms)** | 20640.33 ms | One TSNet run from INP load through `MOCSimulator` completion |
| **PTSNet(ms)** | 1428.45 ms | One PTSNet run using four MPI ranks through all time steps |
| **TS/rth** | 192.3x | TSNet clock time divided by single-run rthym_moc clock time |
| **PT/rth** | 13.3x | PTSNet clock time divided by single-run rthym_moc clock time |
| **PT/TS** | 14.4x | TSNet clock time divided by PTSNet clock time, so PTSNet is 14.4x faster than TSNet here |
| **CV%(r\|T\|P)** | ·\|·\|· | Repeatability metric; unavailable in the smoke row because `--repeat 1` |
| **Peak·r\|T\|P** | 871.5\|867.2\|866.3 ft | Peak head check, not a timing value |

| Column | Meaning |
|--------|---------|
| **rthym(ms)** | rthym_moc load/build + configure + full `solver.run()` |
| **rthym×N(ms)** | Optional wall time for `N` simultaneous, independent rthym_moc model instances in separate Python processes |
| **×N/run** | Optional batch throughput expressed as estimated per-instance latency, computed as `rthym×N(ms) / N`; not parallel speedup of one simulation |
| **TSNet(ms)** | TSNet load + `Initializer` + `MOCSimulator` |
| **PTSNet(ms)** | PTSNet setup + `initialize` + all `run_step`s (MPI rank count from script header) |
| **TS/rth** | TSNet time ÷ rthym time |
| **PT/rth** | PTSNet time ÷ rthym time |
| **PT/TS** | PTSNet time ÷ TSNet time (&gt; 1 ⇒ PTSNet faster) |
| **CV%(r\|T\|P)** | Coefficient of variation (%) for rthym_moc \| TSNet \| PTSNet timing samples; `·` means unavailable |
| **Peak·r\|T\|P** | Peak head (ft): rthym \| TSNet \| PTSNet |

### Summary (representative run, MPI size 4)

| Scenario | rthym_moc | TSNet | PTSNet | PTSNet vs TSNet |
|----------|-----------|-------|--------|-----------------|
| TNET3 valve closure (3 s) | **~0.1 s** | **~20.6 s** | **~1.4 s** | PTSNet **~14×** faster |

**Takeaways**

- **rthym_moc** is fastest on the shared TNET3 case despite including INP load/setup.
- **PTSNet** with 4 ranks completes reliably on TNET3 and is much faster than TSNet.
- **PTSNet** is still not a good multi-rank target for the tiny synthetic cases; use
  TNET3 for MPI speed comparisons and the synthetic cases for physics-focused checks.

---

## Standpipe stub length

TSNet enforces `dt_max = min(L/(2a))` over **every** pipe. With short stubs
**L = a·dt**, that limit is **dt/2**, so the requested `dt` is always rejected.

The benchmark uses **L = 2.1·a·dt** on the standpipe stub pipes (P2/P3), shared by
rthym_moc, TSNet INP, and PTSNet. That is slightly longer than the classic single-segment
**L = a·dt** stub used in some rthym-only tests but is required for a fair
three-way grid.

---

## Other benchmark scripts (legacy / supplementary)

These predate the three-way script and are still useful for specific questions:

| Script | Compares | Use when |
|--------|----------|----------|
| `examples/benchmark_vs_tsnet.py` | rthym_moc vs **TSNet** only | Physics detail + RMS on one Joukowsky case |
| `examples/benchmark_matrix.py` | rthym_moc vs **TSNet** | Grid-size sweep; TSNet times **MOCSimulator only** (not full setup) |

Example (`benchmark_vs_tsnet.py`):

```
  Execution time     : 0.85 ms  (300 time steps)    # rthym_moc
  Execution time     : 65.2 ms  (300 time steps)    # TSNet
  Speed ratio        : 370x  (rthym_moc vs TSNet)
```

For **all three tools in one table**, use `benchmark_ptsnet_vs_tsnet.py` only.

---

## Relationship to validation

| Question | Where to look |
|----------|----------------|
| Is the MOC implementation correct? | `pytest -q`, [validation.md](validation.md) |
| Does rthym_moc agree with TSNet physics? | `benchmark_vs_tsnet.py`, appendix §B.6 |
| How fast are all three on the same cases? | **This guide** + `benchmark_ptsnet_vs_tsnet.py` |
| Is PTSNet faster than TSNet? | **PT/TS** column (with documented `mpiexec -n`) |

None of these timing dependencies are installed in default CI. Reproduce locally
and record platform, `mpiexec -n`, and `rthym_moc.__version__`.

---

## Extending benchmarks

- Keep new cases in `examples/` (not default `pytest` unless only checking physics).
- Document grid size, USF, Courant choices, and **MPI rank count** for PTSNet.
- Do not commit machine-specific millisecond thresholds as CI gates.
