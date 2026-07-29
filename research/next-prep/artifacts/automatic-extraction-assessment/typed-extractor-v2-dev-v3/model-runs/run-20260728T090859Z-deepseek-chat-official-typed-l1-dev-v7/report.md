# Typed Extractor V2 L1 Dev Qualification

- Run ID: `run-20260728T090859Z-deepseek-chat-official-typed-l1-dev-v7`
- Cases: `12`

## Raw proposer quality

- Ready: `false`
- Decision accuracy: `0.8333333333333334`
- Abstention F1: `0.6666666666666666`
- Critical false emissions: `0`
- Exact evidence rate: `0.7777777777777778`
- Error taxonomy: `{'condition_or_scope_error': 4, 'derivation_or_speaker_error': 2, 'evidence_error': 2, 'false_abstention': 2, 'kind_error': 2, 'lifecycle_error': 2, 'modality_or_polarity_error': 2, 'operation_provenance_error': 2, 'predicate_or_operator_error': 2, 'role_or_local_entity_error': 3, 'time_error': 2}`

## Deterministic gate safety

- Ready: `true`
- Gated decision accuracy: `0.8333333333333334`
- Critical false materializations: `0`
- Gate interventions: `0`
- Gate reasons: `{}`
- Guard unchanged: `true`

## Boundaries

The deterministic gate only preserves a proposal or reduces it to abstention. It does not correct semantic fields, and its safety result does not replace raw proposer quality.

No authoritative L1, L2, unit revision, closure, identity, or membership write is authorized. Embeddings are not authority. `LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.
