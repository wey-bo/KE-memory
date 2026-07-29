# Opaque-ID v2 Raw Proposer Error Analysis

This analysis was written after proposals were frozen and after the independent scorer read authority/gold. It was not visible to the proposer.

## Independent decisions

- Raw proposal quality: `fail`
- Deterministic gate safety: `pass`
- Raw action accuracy: `0.8333333333333334` (`10/12`)
- Raw critical false merges: `1`
- Raw critical false memberships: `0`
- Raw abstention F1: `0.0`
- Proposal evidence exact rate: `1.0`
- Gated action accuracy: `1.0`
- Gated critical false merges/memberships: `0/0`
- Gate interventions: `2`

## Error categories

### False merge

- Count: `1`
- Dev case `case-1ed6f84bc0c6914f`: proposed `merge` at confidence `0.78`; gold action was `abstain`. Same-thread repository/application context did not establish authoritative identity. The deterministic gate rejected the merge and returned `abstain`.

### False membership

- Count: `0`

### Abstention

- Expected abstentions: `2`
- Correct raw abstentions: `0`
- Dev case `case-1ed6f84bc0c6914f`: `merge` instead of `abstain`.
- Hidden case `case-c987f1ddab9a5c64`: `keep_distinct` at confidence `0.99` instead of `abstain`. The class/project surface differences did not authorize a definitive identity decision. The deterministic gate returned `abstain`.

### Evidence

- Evidence errors: `0`
- All 12 proposals used the exact required mention set.

## Repair boundary

Only the dev false-merge/abstention error and separately created diagnostic data may be used to change the proposer prompt or candidate-generation policy. The hidden error is recorded for evaluation completeness but must not be used for iterative repair. A subsequent formal evaluation requires a newly frozen version with fresh hidden cases.

Model proposals remain non-authoritative. This result does not authorize automatic merge, membership, or L2 writes. `LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.

The existing report renderer contains fixed reference-proposer wording. The actual proposer identity for this run is the frozen `codex-gpt-5.6-sol@2026-07-27` proposal/score/provenance metadata.
