# Typed Extractor V2 L1 Dev Qualification

- Run ID: `run-20260728T102319Z-deepseek-chat-official-typed-l1-fresh-hidden-v1`
- Cases: `24`

## Raw proposer quality

- Ready: `false`
- Decision accuracy: `0.7916666666666666`
- Abstention F1: `0.5714285714285715`
- Critical false emissions: `3`
- Exact evidence rate: `0.8947368421052632`
- Error taxonomy: `{'condition_or_scope_error': 4, 'derivation_or_speaker_error': 2, 'evidence_error': 2, 'false_abstention': 2, 'false_emission': 3, 'kind_error': 2, 'lifecycle_error': 2, 'modality_or_polarity_error': 2, 'operation_provenance_error': 2, 'predicate_or_operator_error': 2, 'role_or_local_entity_error': 3, 'time_error': 3}`

## Deterministic gate safety

- Ready: `true`
- Gated decision accuracy: `0.7916666666666666`
- Critical false materializations: `0`
- Gate interventions: `4`
- Gate reasons: `{'emission_not_authorized': 3, 'modality_not_authorized': 3, 'valid_time_required': 1}`
- Guard unchanged: `true`

## Boundaries

The deterministic gate only preserves a proposal or reduces it to abstention. It does not correct semantic fields, and its safety result does not replace raw proposer quality.

No authoritative L1, L2, unit revision, closure, identity, or membership write is authorized. Embeddings are not authority. `LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.
