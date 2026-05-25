# EPANET import fidelity (`load_inp`)

Roadmap item **4 — Industry-ready import fidelity**: what `rthym_moc.load_inp()` imports today, what is still manual, and how control times are interpreted.

## Supported on import

| EPANET input | R-THYM behavior |
|--------------|-----------------|
| `[JUNCTIONS]` base demand + optional pattern ID | Base demand stored; multiplier at pattern index 0 applied to initial `Junction.demand` |
| `[DEMANDS]` | Added to junction base demand; optional pattern ID |
| `[PATTERNS]` | Index 0 sets initial demand; 2+ points → `set_demand_schedule()` on the junction |
| `[TIMES]` `Pattern Timestep` | Step size for pattern schedules (EPANET **hours**, converted to **seconds** ×3600) |
| `[CONTROLS]` `LINK … STATUS OPEN\|CLOSED AT TIME …` | → `set_pump_schedule("_PUMP_<id>")` or `set_valve_schedule("_VALVE_<id>")` |
| `[STATUS]` | Pipe/pump/valve open, closed, CV |
| wntr steady solve (`use_wntr=True`) | Initial link flows and node heads |
| Inline pump/valve heads | Prefer wntr head on generated node, else upstream, else downstream junction |

## Not imported (use explicit API or `[RTHYM]`)

| EPANET input | Workaround |
|--------------|------------|
| `[RULES]` | `MOCSolver.add_control_rule()` (Threshold, Deadband, PID, PCV) |
| `[CONTROLS]` NODE / valve SETTINGS / timing other than `AT TIME` | Build schedules in Python or JS |
| `[PATTERNS]` on reservoirs/tanks | Not mapped |
| FCV / GPV valves | Treated as open TCV with warning |
| Full EPANET rule priority / composite controls | Document and replicate manually |

## Control time units

EPANET stores `AT TIME` in **decimal hours**. Import converts to **seconds** for `run(total_time=…, dt=…)`:

```
t_seconds = time_hours * 3600
```

Example: `AT TIME 0.02` → 72 s.

## Acceptance benchmarks

| Test module | What it checks |
|-------------|----------------|
| `tests/test_inp_import_fidelity.py` | Patterns, demands, simple LINK controls |
| `tests/test_complex_topology_from_inp.py` | Pre-trip heads/flows vs wntr (±0.5 ft / ±0.5 GPM) |

## Fewer manual fixes checklist

After import, you should still verify:

1. **Transient duration** covers last control / pattern step.
2. **Stub length** (`stub_length_ft`) for fast valve closures (see README).
3. **PRV/PSV/PBV** setpoints are control heads, not user IC overrides.
4. **Pump trip** events not in INP → add `set_pump_schedule` or rules.
