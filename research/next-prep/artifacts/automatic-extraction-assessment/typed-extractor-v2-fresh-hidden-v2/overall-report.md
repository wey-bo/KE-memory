# Typed Extractor Fresh-V2 Hidden Evaluation

- Overall: `not_qualified`
- Requested model: `deepseek-chat`
- Response model: `deepseek-v4-flash` for both layers
- Semantic runs: `1` per layer; no semantic retry
- Guard fingerprint: `e184b6caf2998acf1c8700bc84d24bbafd49ab9c8f15738d1af8cc484ee5ebcc`

## L1

- Cases: `24`
- Raw proposer quality ready: `false`
- Deterministic gate safety ready: `false`
- Layer ready: `false`
- Metrics: `{'condition_or_scope_accuracy': 0.9444444444444444, 'derivation_or_speaker_accuracy': 1.0, 'deterministic_critical_false_materialization_count': 0, 'exact_evidence_rate': 1.0, 'gate_intervention_count': 4, 'gated_decision_accuracy': 0.875, 'kind_accuracy': 1.0, 'lifecycle_accuracy': 1.0, 'modality_or_polarity_accuracy': 1.0, 'operation_provenance_accuracy': 1.0, 'predicate_or_operator_accuracy': 1.0, 'proposal_coverage': 1.0, 'raw_abstention_f1': 0.8571428571428571, 'raw_abstention_precision': 1.0, 'raw_abstention_recall': 0.75, 'raw_critical_false_emission_count': 1, 'raw_decision_accuracy': 0.9583333333333334, 'role_or_local_entity_accuracy': 0.5555555555555556, 'schema_valid_rate': 1.0, 'time_accuracy': 0.8888888888888888}`
- Raw error taxonomy: `{'condition_or_scope_error': 1, 'false_emission': 1, 'role_or_local_entity_error': 8, 'time_error': 2}`
- Gate reasons: `{'condition_not_authorized': 1, 'emission_not_authorized': 1, 'event_time_required': 2, 'modality_not_authorized': 1, 'valid_time_not_authorized': 2}`

## L2

- Cases: `12`
- Raw proposer quality ready: `false`
- Deterministic gate safety ready: `false`
- Layer ready: `false`
- Metrics: `{'abstraction_accuracy': 0.7777777777777778, 'closure_accuracy': 0.5555555555555556, 'deterministic_critical_false_materialization_count': 0, 'exact_evidence_rate': 1.0, 'gate_intervention_count': 4, 'gated_decision_accuracy': 0.6666666666666666, 'kind_accuracy': 1.0, 'proposal_coverage': 1.0, 'raw_abstention_f1': 1.0, 'raw_abstention_precision': 1.0, 'raw_abstention_recall': 1.0, 'raw_critical_false_emission_count': 0, 'raw_decision_accuracy': 1.0, 'schema_valid_rate': 1.0, 'source_coverage_accuracy': 1.0, 'structured_claim_accuracy': 0.0, 'summary_accuracy': 1.0, 'support_id_accuracy': 1.0}`
- Raw error taxonomy: `{'abstraction_error': 2, 'closure_error': 4, 'decision_error': 0, 'evidence_error': 0, 'false_abstention': 0, 'false_emission': 0, 'kind_error': 0, 'source_coverage_error': 0, 'structured_claim_error': 9, 'summary_error': 0, 'support_id_error': 0}`
- Gate reasons: `{'abstraction_method_not_authorized': 2, 'closure_pattern_not_authorized': 4}`

## Boundary

Raw proposer quality and deterministic gate safety are reported separately. The final qualification uses the frozen fresh-v2 preregistration exact thresholds; legacy scorer readiness fields are not used to qualify the run.

No L1, L2, identity, membership, closure, revision, source-revision, snapshot, aggregate, or pipeline write is authorized. `LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.
