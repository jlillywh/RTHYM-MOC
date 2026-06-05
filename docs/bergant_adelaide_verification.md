# Bergant–Simpson Adelaide rig verification

The University of Adelaide tank–pipeline–valve apparatus (37.2 m copper pipe,
22.1 mm bore, fast ball-valve closure, column separation) is the usual benchmark
for vaporous cavitation and discrete cavity models. RTHYM-MOC treats it as
**independent verification**: published laboratory values, not checked-in golden
traces from an earlier solver run.

| Layer | Test module | Needs |
|-------|-------------|--------|
| Scalar peaks (CI today) | `test_dvcm_bergant_adelaide_experiment.py` | Literature peaks in `bergant_adelaide_*_reference.json` |
| Full valve trace (optional) | `test_dvcm_bergant_adelaide_trace.py` | You add `bergant_adelaide_severe_valve_trace_reference.csv` |

Helpers: `tests/bergant_adelaide_verification_utils.py`.

## Complete the trace task (checklist)

You are **one CSV away** from enabling `test_dvcm_bergant_adelaide_trace.py`.

| Step | Action |
|------|--------|
| 1 | WebPlotDigitizer → load your **Fig. 4 (N=16)** PNG (orange **Experiment** only) |
| 2 | Calibrate X: **0.0–0.8 s**, Y: **−400–2400 kPa** (values as on the axis) |
| 3 | Export CSV → columns **`t_s`**, **`p_gauge_kPa`** (cavity flat ≈ 0 is gauge — see below) |
| 4 | `cp tests/bergant_adelaide_severe_valve_trace_reference.csv.example tests/bergant_adelaide_severe_valve_trace_reference.csv` and paste data |
| 5 | `python scripts/validate_bergant_trace_csv.py` |
| 6 | `python scripts/plot_bergant_trace_overlay.py` — visual check + RMS preview |
| 7 | `pytest tests/test_dvcm_bergant_adelaide_trace.py -v` |
| 8 | If FAIL: inspect overlay PNG, loosen `rms_kpa_max` in `bergant_adelaide_severe_reference.json`, commit CSV + tuned limits |

**Pressure convention:** digitize the Y-axis **as printed**. The flat cavity at 0 kPa is
**gauge** (vapor reference), matching how rthym-moc compares in the trace test. Peak
scalars in the other test still use **absolute kPa** from the paper (2057 kPa).

## Scalar checks (already in CI)

| Case | V₀ | Metric | Experimental anchor |
|------|-----|--------|---------------------|
| Moderate | 0.3 m/s | Maximum absolute pressure at valve | 1015 kPa (He et al. 2025, Fig. 3) |
| Severe | 1.4 m/s | Second peak after cavity minimum | 2057 kPa (Fig. 4) |

15% relative tolerance on peaks. No email or raw R128 files required.

## Trace check (DIY, no email)

This is the **no-outreach** path to a stronger source of truth: digitize the
**experimental** curve from an open paper, commit the CSV, and pytest compares
RMS error on a time window.

### 1. Get the figure

1. Open **He, Li & Guo (2025)**, *Processes* 13:3510 — [DOI 10.3390/pr13113510](https://doi.org/10.3390/pr13113510) (open access).
2. Use **Figure 4** (valve pressure, **V₀ = 1.4 m/s**, severe cavitation).
3. Digitize the **experimental** / measured series (not the model line). If the
   legend is unclear, use the noisier trace or the one labeled “experimental” /
   “measured” in the caption.

### 2. WebPlotDigitizer (recommended)

1. Go to [automeris.io/WebPlotDigitizer](https://automeris.io/WebPlotDigitizer/).
2. **Load** a screenshot or cropped image of Fig. 4 (PDF screenshot is fine).
3. Choose plot type **2D (X-Y)**.
4. Align axes:
   - **X**: **0.0** and **0.8** s
   - **Y**: **−400** and **2400** kPa (read values directly off the figure)
5. Trace the **orange Experiment** line only (not blue).
6. Export CSV; use columns **`t_s`**, **`p_gauge_kPa`** (recommended for Fig. 4).
   Alternatively `p_abs_kPa` if you convert peaks yourself — set `# pressure_unit: absolute` in the header.
7. Aim for **≥ 80 points** along the orange curve (more on peaks is better).

### 3. Install into the repo

```bash
cp tests/bergant_adelaide_severe_valve_trace_reference.csv.example \
   tests/bergant_adelaide_severe_valve_trace_reference.csv
```

Paste exported points under the header. Keep the `# source:` comment lines (edit
`method:` to note WebPlotDigitizer and figure).

Validate and preview:

```bash
python scripts/validate_bergant_trace_csv.py
python scripts/plot_bergant_trace_overlay.py
```

Run the trace test:

```bash
pytest tests/test_dvcm_bergant_adelaide_trace.py -v
```

While the CSV is missing, that test is **skipped**; CI stays green on scalar peaks only.

### 4. Tune tolerances (after first import)

Defaults in `bergant_adelaide_severe_reference.json` → `trace_comparison`:

| Field | Default | Meaning |
|-------|---------|---------|
| `pressure_compare` | `gauge` | Same unit as Fig. 4 axis |
| `trace_windows` | 0.33–0.47 s and 0.64–0.80 s | RMS only on rebound pulses (skips cavity at 0) |
| `exclude_below_gauge_kpa` | 400 | Drop low-pressure points inside windows |
| `rms_kpa_max` / `max_abs_kpa` | 250 / 450 kPa | Loose until overlay looks reasonable |

Digitization noise, valve-law mismatch, and DVCM grid spikes mean the first import
may fail—**loosen limits, then tighten** once the overlay looks reasonable in a notebook.

Provenance to record in CSV comments:

```text
# source: He et al. (2025) Processes 13:3510 Fig. 4 experimental
# method: WebPlotDigitizer 4.x, axis calibrated to ...
```

### 5. Optional: vector PDF path

If the PDF line art is vector-based, Inkscape → copy path → parse SVG coordinates
can be cleaner than raster digitization. Same output file format.

### 6. Direct request (optional)

Not required. Bergant / Simpson sometimes share R128 data; see community notes in
older versions of this doc if you change your mind later.

## DVCM comparison notes

RTHYM-MOC uses **DVCM** (discrete vapor cavities at MOC nodes). Collapse peaks are
**grid-dependent**; do not expect pointwise match to DGCM-smoothed literature curves.

For fair comparison:

1. Match effective `dt` / reach count to the paper you digitized from (Fu/He cite
   ~64 segments for mesh independence in FD codes).
2. Compare shape and peak timing in the trace window, not every high-frequency spike.
3. Scalar peak tests and trace RMS are complementary—peaks guard gross error; trace
   guards phase and cavity duration.

## References

- Bergant, A. & Simpson, A.R. (1999). Pipeline column separation flow regimes. *J. Hydraul. Eng.* 125(8):835–848.
- He, J., Li, C. & Guo, Y. (2025). Modeling transient vaporous cavitating flow. *Processes* 13:3510.
- Karadžić, U. et al. (2014). Valve-induced water hammer. *Stroj. vestn.* 60(11):742–754.
