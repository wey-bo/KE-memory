# V3 Parser Repair Post-hoc Report

Date: 2026-07-25

## Decision

Status: post-hoc repair validated, but not a clean hidden gate.

The repair improves automatic structural and lexical generalization enough for the already-exposed v3 hidden split to pass. Because v3 hidden had already been inspected at aggregate and sample level during failure analysis, this result must be treated as a regression check and not as the final decision to enter large benchmarks. A clean go/no-go still requires a newly frozen v4 hidden split.

## Repair Scope

The code change is limited to the automatic source-blind representation adapter:

- parse `connected ... to both ...` as `linked_to`;
- parse `exact set contains ...` as exact-set support;
- parse `Before ... log recorded ... as active` as historical temporal provenance;
- parse `used ledger for ...` as ledger alias context;
- parse `ledger denotes an account record rather than a travel schedule` without flipping the sense to `travel schedule`;
- propagate explicit owner/external-relation absence into later accounting-sense summary evidence.

No scorer, oracle fixture, gold answer, or benchmark rule was changed.

## New Regression Tests

Added source-blind automatic tests:

```text
test_automatic_multihop_accepts_connected_and_exact_set_contains_wording
test_automatic_temporal_closure_keeps_before_update_provenance_turn
test_automatic_sense_query_handles_used_ledger_and_denotes_wording
test_automatic_owner_query_uses_explicit_absence_over_later_owner_claim
```

Red/green summary:

```text
initial targeted run: 4 failures across the new tests
final targeted and focused suite: passing
```

## Diagnostic All

```text
run_id: run-20260725T202000Z-v3-parser2-diagnostic-all
rows: 2,304
errors: 0
verify-run: valid
encoder: diagnostic-hash, not real dense
```

Automatic diagnostic metrics:

| Arm | Evidence Set Exact Match | Answer | Constraint | Critical FP | Fallback |
| --- | ---: | ---: | ---: | ---: | ---: |
| B2 | 0.016 | 0.375 | 0.000 | 0.974 | 0.000 |
| O+ | 0.938 | 0.938 | 0.938 | 0.000 | 0.000 |
| O+E | 1.000 | 1.000 | 1.000 | 0.000 | 0.062 |

Automatic diagnostic family metrics:

| Family | O+ ESEM | O+E ESEM |
| --- | ---: | ---: |
| roles_polarity_modality_quantity | 1.000 | 1.000 |
| temporal_updates_conflicts_provenance | 1.000 | 1.000 |
| conjunction_exact_set_multihop | 1.000 | 1.000 |
| synonymy_sense_external_unanswerable | 0.789 | 1.000 |

## Real Dev

```text
run_id: run-20260725T203000Z-v3-parser2-real-dev
rows: 468
errors: 0
verify-run: valid
model: qdrant/bge-small-en-v1.5-onnx-q@52398278842ec682c6f32300af41344b1c0b0bb2
```

Automatic real dev metrics:

| Arm | Evidence Set Exact Match | Answer | Constraint | Critical FP | Fallback |
| --- | ---: | ---: | ---: | ---: | ---: |
| B2 | 0.000 | 0.538 | 0.000 | 1.000 | 0.000 |
| O+ | 0.923 | 0.923 | 0.923 | 0.000 | 0.000 |
| O+E | 1.000 | 1.000 | 1.000 | 0.000 | 0.077 |

## Post-hoc Real Hidden

```text
run_id: run-20260725T204000Z-v3-parser2-real-hidden
rows: 1,836
errors: 0
verify-run: valid
model: qdrant/bge-small-en-v1.5-onnx-q@52398278842ec682c6f32300af41344b1c0b0bb2
```

Generated post-hoc gate report:

```text
artifacts/ontology-memory-experiment/reports/v3-parser2-posthoc-hidden-gate-report.md
decision: pass
automatic_retained_gain: 0.8431372549019608
```

Automatic post-hoc hidden metrics:

| Arm | Evidence Set Exact Match | Answer | Constraint | Critical FP | Fallback |
| --- | ---: | ---: | ---: | ---: | ---: |
| B2 | 0.098 | 0.562 | 0.000 | 0.882 | 0.000 |
| O+ | 0.941 | 0.941 | 0.941 | 0.000 | 0.000 |
| O+E | 1.000 | 1.000 | 1.000 | 0.000 | 0.059 |

Fallback summary:

```text
overall fallback rate: 0.058823529411764705
structural-family fallback rate: 0.0
execution errors: 0
```

Automatic post-hoc hidden family metrics:

| Family | O+ ESEM | O+E ESEM |
| --- | ---: | ---: |
| roles_polarity_modality_quantity | 1.000 | 1.000 |
| temporal_updates_conflicts_provenance | 1.000 | 1.000 |
| conjunction_exact_set_multihop | 1.000 | 1.000 |
| synonymy_sense_external_unanswerable | 0.800 | 1.000 |

## Interpretation

The automatic pipeline can now express the controlled structural primitives under the v3 surface variations, and real embedding fallback is properly limited to the lexical family. This is the first result where automatic `O+E` reaches 1.0 on the already-exposed hidden split with real dense retrieval.

The remaining methodological blocker is experimental cleanliness, not the current v3 post-hoc score. The next valid go/no-go is to freeze v4 with fresh hidden variants and run the same gate without using v4 hidden for development.
