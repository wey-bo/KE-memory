# Typed Extractor V2 L2 Dev Qualification Report

- Dataset: `typed-extractor-l2-dev-v2`
- Run: `run-20260728T074154Z-deepseek-chat-official-typed-l2-dev-v5`
- Cases: `6`
- Raw proposer quality ready: `false`
- Deterministic gate safety ready: `true`

## Raw Proposer Quality

- raw_decision_accuracy: `0.6666666666666666`
- raw_abstention_f1: `0.0`
- raw_critical_false_emission_count: `2`
- exact_evidence_rate: `0.25`
- kind_accuracy: `1.0`
- support_id_accuracy: `1.0`
- structured_claim_accuracy: `0.0`
- abstraction_accuracy: `0.0`
- closure_accuracy: `0.5`
- source_coverage_accuracy: `1.0`
- summary_accuracy: `0.0`

## Deterministic Gate Safety

- gated_decision_accuracy: `0.5`
- gate_intervention_count: `5`
- deterministic_critical_false_materialization_count: `0`
- Guard fingerprint unchanged: `True`
- Automatic write counts: `{'closure': 0, 'identity': 0, 'l1': 0, 'l2': 0, 'membership': 0, 'unit_revision': 0}`

## Boundary

This dev result does not authorize pipeline integration, fresh hidden evaluation, or authoritative L1/L2/revision/closure/identity/membership writes.
`LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.
