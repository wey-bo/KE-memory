# Typed Extractor Dev-Repair Qualification

- Layer: `l1`
- Dataset: `typed-extractor-l1-dev-repair-v2`
- Run: `run-20260728T125941Z-deepseek-chat-official-typed-l1-dev-repair-v9`
- Raw proposer quality: `fail`
- Deterministic gate safety: `pass`
- Dev repair ready: `fail`

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
- `raw_abstention_f1`: fail
- `raw_decision_accuracy`: fail
- `role_or_local_entity_accuracy`: fail
- `schema_valid_rate`: pass
- `time_accuracy`: pass

## Zero-count safety checks

- `raw_critical_false_emission_count`: pass
- `gate_intervention_count`: pass
- `deterministic_critical_false_materialization_count`: pass

Raw proposer quality and deterministic gate safety are reported separately. No pipeline integration or authoritative write is authorized.
