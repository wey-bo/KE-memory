# Typed Extractor V2 L1 Dev Qualification

- Run ID: `run-20260729T024500Z-deepseek-chat-official-typed-l1-fresh-hidden-v2`
- Cases: `24`

## Raw proposer quality

- Ready: `false`
- Decision accuracy: `0.9583333333333334`
- Abstention F1: `0.8571428571428571`
- Critical false emissions: `1`
- Exact evidence rate: `1.0`
- Error taxonomy: `{'condition_or_scope_error': 1, 'false_emission': 1, 'role_or_local_entity_error': 8, 'time_error': 2}`

## Deterministic gate safety

- Ready: `true`
- Gated decision accuracy: `0.875`
- Critical false materializations: `0`
- Gate interventions: `4`
- Gate reasons: `{'condition_not_authorized': 1, 'emission_not_authorized': 1, 'event_time_required': 2, 'modality_not_authorized': 1, 'valid_time_not_authorized': 2}`
- Guard unchanged: `true`

## Boundaries

The deterministic gate only preserves a proposal or reduces it to abstention. It does not correct semantic fields, and its safety result does not replace raw proposer quality.

No authoritative L1, L2, unit revision, closure, identity, or membership write is authorized. Embeddings are not authority. `LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.
