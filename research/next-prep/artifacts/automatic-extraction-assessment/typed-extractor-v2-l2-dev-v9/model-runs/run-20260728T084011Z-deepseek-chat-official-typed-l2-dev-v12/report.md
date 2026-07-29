# Typed Extractor V2 L2 Dev Qualification Report

- Score schema: `typed-extractor-l2-score-v2`
- Scoring policy: `evidence-set-abstraction-method-v2`
- Dataset: `typed-extractor-l2-dev-v7`
- Run: `run-20260728T084011Z-deepseek-chat-official-typed-l2-dev-v12`
- Cases: `6`
- Raw proposer quality ready: `true`
- Deterministic gate safety ready: `true`

## Raw Proposer Quality

- raw_decision_accuracy: `1.0`
- raw_abstention_f1: `1.0`
- raw_critical_false_emission_count: `0`
- exact_evidence_rate: `1.0`
- kind_accuracy: `1.0`
- support_id_accuracy: `1.0`
- structured_claim_accuracy: `1.0`
- abstraction_accuracy: `1.0`
- closure_accuracy: `1.0`
- source_coverage_accuracy: `1.0`
- summary_accuracy: `1.0`

## Deterministic Gate Safety

- gated_decision_accuracy: `1.0`
- gate_intervention_count: `0`
- deterministic_critical_false_materialization_count: `0`
- Guard fingerprint unchanged: `True`
- Automatic write counts: `{'closure': 0, 'identity': 0, 'l1': 0, 'l2': 0, 'membership': 0, 'unit_revision': 0}`

## Boundary

This dev result does not authorize pipeline integration, fresh hidden evaluation, or authoritative L1/L2/revision/closure/identity/membership writes.
`LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.
