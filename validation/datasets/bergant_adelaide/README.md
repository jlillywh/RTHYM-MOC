# Bergant–Simpson Adelaide column-separation rig

University of Adelaide tank–pipeline–valve apparatus used for independent DVCM verification.

## Files

| File | Description |
|------|-------------|
| `moderate_reference.json` | Scalar peak anchor — moderate cavitation (V₀ = 0.3 m/s) |
| `severe_reference.json` | Scalar peak anchor — severe cavitation (V₀ = 1.4 m/s) |
| `severe_valve_trace_reference.csv` | Optional digitized experimental valve pressure trace |
| `severe_valve_trace_reference.csv.example` | Template for trace digitization |

## Provenance

- Bergant & Simpson (1999), *J. Hydraul. Eng.* 125(8):835–848
- He, Li & Guo (2025), *Processes* 13:3510 — open-access figures for digitization

Full acquisition notes: [`docs/bergant_adelaide_verification.md`](../../../docs/bergant_adelaide_verification.md).

## Usage

```python
from bergant_adelaide_verification_utils import load_reference, reference_path

ref = load_reference("severe_cavitation")
print(reference_path("moderate_cavitation"))
```
