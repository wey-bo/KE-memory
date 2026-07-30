# Typed Extractor V2 L2 Dev Qualification Report

- Score schema: `typed-extractor-l2-score-v2`
- Scoring policy: `evidence-set-abstraction-method-v2`
- Dataset: `typed-extractor-v3-fresh-hidden-v1-l2`
- Run: `run-20260730T143749Z-deepseek-v4-pro-official-v2-typed-l2-fresh-hidden-v3`
- Cases: `18`
- Raw proposer quality ready: `false`
- Deterministic gate safety ready: `true`

## Raw Proposer Quality

- raw_decision_accuracy: `0.8888888888888888`
- raw_abstention_f1: `0.8571428571428571`
- raw_critical_false_emission_count: `2`
- exact_evidence_rate: `1.0`
- kind_accuracy: `0.6`
- support_id_accuracy: `1.0`
- structured_claim_accuracy: `0.0`
- abstraction_accuracy: `1.0`
- closure_accuracy: `0.8`
- source_coverage_accuracy: `1.0`
- summary_accuracy: `0.0`

## Deterministic Gate Safety

- gated_decision_accuracy: `0.8888888888888888`
- gate_intervention_count: `4`
- deterministic_critical_false_materialization_count: `0`
- Guard fingerprint unchanged: `True`
- Automatic write counts: `{'closure': 0, 'identity': 0, 'l1': 0, 'l2': 0, 'membership': 0, 'unit_revision': 0}`

## Boundary

This dev result does not authorize pipeline integration, fresh hidden evaluation, or authoritative L1/L2/revision/closure/identity/membership writes.
`LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.
