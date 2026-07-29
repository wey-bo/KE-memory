# Identity Proposer v4.1 Dev Error Analysis

Run: `run-20260728T013000Z-claude-sonnet-4-6-dev-policy-v4-1`

## Raw Proposer Quality

- Status: pass
- Action accuracy: `1.0`
- Critical false merges: `0`
- Critical false memberships: `0`
- Abstention precision / recall / F1: `1.0 / 1.0 / 1.0`
- Proposal evidence exactness: `1.0`

No raw proposer errors were observed on the 12-case frozen dev slice.

## Deterministic Gate Safety

- Status: pass
- Gated action accuracy: `1.0`
- Critical false merges: `0`
- Critical false memberships: `0`
- Gate interventions: `0`
- Required evidence exactness: `1.0`
- Structural fallbacks: `0`

The raw and gated results are reported separately. The gate did not mask any raw
error in this run.

## Boundary

This pass authorizes fresh-v4 hidden authoring and evaluation only. It does not
authorize automatic merge, membership writes, L2 writes, or identity-pipeline
integration. Embeddings remain non-authoritative, and the frozen LongMemEval case
remains `structured_l2_identity_unresolved`.
