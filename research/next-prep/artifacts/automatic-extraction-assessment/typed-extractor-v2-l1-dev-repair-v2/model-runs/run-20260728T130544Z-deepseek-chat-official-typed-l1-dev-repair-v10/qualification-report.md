# Typed Extractor Dev-Repair Qualification

- Layer: `l1`
- Dataset: `typed-extractor-l1-dev-repair-v2`
- Run: `run-20260728T130544Z-deepseek-chat-official-typed-l1-dev-repair-v10`
- Raw proposer quality: `pass`
- Deterministic gate safety: `pass`
- Dev repair ready: `pass`

This result is diagnostic-only and is not natural benchmark evidence. Even on pass, fresh-v2 remains unauthorized until both layers pass and a separate preregistration is frozen.

## Exact metrics

- `condition_or_scope_accuracy`: pass
- `derivation_or_speaker_accuracy`: pass
- `exact_evidence_rate`: pass
- `kind_accuracy`: pass
- `lifecycle_accuracy`: pass
- `modality_or_polarity_accuracy`: pass
- `operation_provenance_accuracy`: pass
- `predicate_or_operator_accuracy`: pass
- `proposal_coverage`: pass
- `raw_abstention_f1`: pass
- `raw_decision_accuracy`: pass
- `role_or_local_entity_accuracy`: pass
- `schema_valid_rate`: pass
- `time_accuracy`: pass

## Zero-count safety checks

- `raw_critical_false_emission_count`: pass
- `gate_intervention_count`: pass
- `deterministic_critical_false_materialization_count`: pass

Raw proposer quality and deterministic gate safety are reported separately. No pipeline integration or authoritative write is authorized.
