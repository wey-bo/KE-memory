# Typed Extractor V2 L1 Dev Qualification

- Run ID: `run-20260728T052550Z-codex-gpt-5-6-sol-typed-l1-dev-v2`
- Cases: `12`

## Raw proposer quality

- Ready: `false`
- Decision accuracy: `0.9166666666666666`
- Abstention F1: `0.6666666666666666`
- Critical false emissions: `1`
- Exact evidence rate: `1.0`
- Error taxonomy: `{'condition_or_scope_error': 1, 'false_emission': 1, 'predicate_or_operator_error': 9, 'role_or_local_entity_error': 9, 'time_error': 2}`

## Deterministic gate safety

- Ready: `true`
- Gated decision accuracy: `0.8333333333333334`
- Critical false materializations: `0`
- Gate interventions: `3`
- Gate reasons: `{'emission_not_authorized': 1, 'event_time_not_authorized': 1, 'modality_not_authorized': 1, 'valid_time_not_authorized': 1}`
- Guard unchanged: `true`

## Boundaries

The deterministic gate only preserves a proposal or reduces it to abstention. It does not correct semantic fields, and its safety result does not replace raw proposer quality.

No authoritative L1, L2, unit revision, closure, identity, or membership write is authorized. Embeddings are not authority. `LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.
