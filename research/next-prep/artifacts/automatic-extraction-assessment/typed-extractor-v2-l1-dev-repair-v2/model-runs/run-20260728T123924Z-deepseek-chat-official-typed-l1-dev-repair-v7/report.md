# Typed Extractor V2 L1 Dev Qualification

- Run ID: `run-20260728T123924Z-deepseek-chat-official-typed-l1-dev-repair-v7`
- Cases: `16`

## Raw proposer quality

- Ready: `true`
- Decision accuracy: `1.0`
- Abstention F1: `1.0`
- Critical false emissions: `0`
- Exact evidence rate: `1.0`
- Error taxonomy: `{'modality_or_polarity_error': 1, 'role_or_local_entity_error': 1}`

## Deterministic gate safety

- Ready: `true`
- Gated decision accuracy: `0.9375`
- Critical false materializations: `0`
- Gate interventions: `1`
- Gate reasons: `{'modality_not_authorized': 1}`
- Guard unchanged: `true`

## Boundaries

The deterministic gate only preserves a proposal or reduces it to abstention. It does not correct semantic fields, and its safety result does not replace raw proposer quality.

No authoritative L1, L2, unit revision, closure, identity, or membership write is authorized. Embeddings are not authority. `LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.
