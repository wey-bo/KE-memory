# Typed Extractor V2 L1 Dev Qualification

- Run ID: `run-20260730T143749Z-deepseek-v4-pro-official-v2-typed-l1-fresh-hidden-v3`
- Cases: `24`

## Raw proposer quality

- Ready: `false`
- Decision accuracy: `0.9583333333333334`
- Abstention F1: `0.6666666666666666`
- Critical false emissions: `1`
- Exact evidence rate: `1.0`
- Error taxonomy: `{'false_emission': 1, 'kind_error': 5, 'role_or_local_entity_error': 20}`

## Deterministic gate safety

- Ready: `true`
- Gated decision accuracy: `1.0`
- Critical false materializations: `0`
- Gate interventions: `1`
- Gate reasons: `{'emission_not_authorized': 1, 'modality_not_authorized': 1}`
- Guard unchanged: `true`

## Boundaries

The deterministic gate only preserves a proposal or reduces it to abstention. It does not correct semantic fields, and its safety result does not replace raw proposer quality.

No authoritative L1, L2, unit revision, closure, identity, or membership write is authorized. Embeddings are not authority. `LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.
