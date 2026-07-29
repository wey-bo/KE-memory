# Typed Extractor Dev-Repair Qualification

- Layer: `l2`
- Dataset: `typed-extractor-taxonomy-l2-dev-v1`
- Run: `run-20260729T041501Z-deepseek-chat-official-typed-l2-taxonomy-baseline-v1`
- Raw proposer quality: `pass`
- Deterministic gate safety: `pass`
- Dev repair ready: `pass`

This result is diagnostic-only and is not natural benchmark evidence. Even on pass, fresh-v2 remains unauthorized until both layers pass and a separate preregistration is frozen.

## Exact metrics

- `abstraction_accuracy`: pass
- `closure_accuracy`: pass
- `exact_evidence_rate`: pass
- `kind_accuracy`: pass
- `proposal_coverage`: pass
- `raw_abstention_f1`: pass
- `raw_decision_accuracy`: pass
- `schema_valid_rate`: pass
- `source_coverage_accuracy`: pass
- `structured_claim_accuracy`: pass
- `summary_accuracy`: pass
- `support_id_accuracy`: pass

## Zero-count safety checks

- `raw_critical_false_emission_count`: pass
- `gate_intervention_count`: pass
- `deterministic_critical_false_materialization_count`: pass

Raw proposer quality and deterministic gate safety are reported separately. No pipeline integration or authoritative write is authorized.
