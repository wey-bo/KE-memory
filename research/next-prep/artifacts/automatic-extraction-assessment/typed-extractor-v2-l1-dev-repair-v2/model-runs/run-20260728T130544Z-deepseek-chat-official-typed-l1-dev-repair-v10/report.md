# Typed Extractor V2 L1 Dev Qualification

- Run ID: `run-20260728T130544Z-deepseek-chat-official-typed-l1-dev-repair-v10`
- Cases: `16`

## Raw proposer quality

- Ready: `true`
- Decision accuracy: `1.0`
- Abstention F1: `1.0`
- Critical false emissions: `0`
- Exact evidence rate: `1.0`
- Error taxonomy: `{}`

## Deterministic gate safety

- Ready: `true`
- Gated decision accuracy: `1.0`
- Critical false materializations: `0`
- Gate interventions: `0`
- Gate reasons: `{}`
- Guard unchanged: `true`

## Boundaries

The deterministic gate only preserves a proposal or reduces it to abstention. It does not correct semantic fields, and its safety result does not replace raw proposer quality.

No authoritative L1, L2, unit revision, closure, identity, or membership write is authorized. Embeddings are not authority. `LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.
