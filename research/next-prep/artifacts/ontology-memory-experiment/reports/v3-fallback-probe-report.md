# V3 Fallback Probe Report

Date: 2026-07-25

## Decision

Status: v3 fallback probes frozen and diagnostic-validated.

This is not a real-dense hidden gate. The previous v2 real hidden decision remains `fail` until the real dense environment is available and a v3 real hidden run is completed.

## Frozen V3 Scope

- Input directory: `artifacts/ontology-memory-experiment/gold-v3/`
- Scenarios: 64 total
- Added fallback probes: 4 lexical-family uncovered-predicate probes
- Split of added probes: 1 dev, 3 hidden
- Distractors: 35,200 total
- Intended fallback condition: `declared_unresolved_slots=["predicate"]`
- Structural fallback limit: probes are lexical family only; structural-family fallback should remain 0.

Manifest hashes:

| Artifact | SHA-256 |
| --- | --- |
| Source scenarios | `3274d5d101b0e8c1eebbcf019c59ae63f97c16e4703b5792f874ceabdbdea5db` |
| Gold | `b30e42ed426b44d1d0dbd1574060c2c94179c5ae3e189ac27ced7bc7feca214c` |
| Distractors | `13faa6a2552e1653adb1377b985f0ff7509cab0239120532c6f9cebaf02b8feb` |
| Oracle query plans | `72dded873984ea6000f888767f9ec6d0ab004136ea8ab51ca16953711cc4b846` |
| Oracle representations | `96d9e99b4125b23376a0edbdc2715ff735a45af7217c4abc606778b11b7e898c` |

## Run

```text
run_id: run-20260725T181000Z-v3-diagnostic-all
rows: 2,304
errors: 0
verify-run: valid
encoder: diagnostic-hash, not real dense
```

Overall automatic diagnostic metrics:

| Arm | Evidence Set Exact Match | Answer | Constraint | Critical FP | Fallback |
| --- | ---: | ---: | ---: | ---: | ---: |
| B2 | 0.005 | 0.370 | 0.000 | 0.979 | 0.000 |
| O+ | 0.375 | 0.641 | 0.703 | 0.000 | 0.000 |
| O+E | 0.438 | 0.703 | 0.766 | 0.000 | 0.062 |

Fallback summary:

```text
overall fallback rate: 0.0625
structural-family fallback rate: 0.0
execution errors: 0
```

Added fallback probes:

| Arm | Probe ESEM | Probe Answer | Probe Constraint | Probe Fallback |
| --- | ---: | ---: | ---: | ---: |
| O+ | 0.000 | 0.000 | 0.000 | 0.000 |
| O+E | 1.000 | 1.000 | 1.000 | 1.000 |

## Boundary

The fallback benefit here is non-vacuous in diagnostic execution, but it is still not a real embedding result. It proves the guarded fallback path is executable and constrained on frozen probes. It does not prove that `bge-small-en-v1.5` or another real embedding model will rank these probes correctly under the same conditions.

The next required gate is a real dense v3 dev/hidden run after restoring an environment with `fastembed`.
