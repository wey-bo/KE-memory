# Identity Proposer v4.1 Fresh-v4 Error Analysis

Run: `run-20260728T031000Z-claude-sonnet-4-6-fresh-policy-v4-1`

## Raw Proposer Quality

- Status: pass
- Action accuracy: `1.0`
- Critical false merges: `0`
- Critical false memberships: `0`
- Abstention precision / recall / F1: `1.0 / 1.0 / 1.0`
- Proposal evidence exactness: `1.0`

All six hidden actions were correct: identity `merge`, `keep_distinct`, and
`abstain`, plus membership `include`, `exclude`, and `abstain`.

## Deterministic Gate Safety

- Status: pass
- Gated action accuracy: `1.0`
- Gated critical false merges: `0`
- Gated critical false memberships: `0`
- Gate interventions: `0`
- Required evidence exactness: `1.0`
- Structural fallbacks: `0`

Raw quality and gated safety are reported independently. The deterministic gate
did not mask or repair any raw error.

## Isolation and Boundary

The proposer received one user message containing only the frozen final prompt
and fresh-v4 public JSON. Proposals and provenance were frozen before scoring read
authority or gold.

This result does not authorize automatic merge, membership writes, L2 writes, or
candidate integration into the identity pipeline. Embeddings remain
non-authoritative, and `LONGMEMEVAL-6d550036` remains
`structured_l2_identity_unresolved`.
