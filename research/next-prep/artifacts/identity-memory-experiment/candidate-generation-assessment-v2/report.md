# Identity Candidate Generation Integration Assessment v2

- Run ID: `run-20260728T031000Z-claude-sonnet-4-6-fresh-policy-v4-1`
- Cases: `6`
- Raw proposer quality: `pass`
- Deterministic gate safety: `pass`
- Candidate-generation integration ready: `false`
- Manual-review eligible candidates: `4`
- Gate abstentions: `2`
- Existing entity binding rate: `0.0`
- L1 evidence binding rate: `0.0`
- Source revision binding rate: `0.0`
- Blocked authoritative writes: `4`
- Automatic authoritative writes: `0`
- Mutation guard: `unchanged`

## Interpretation

The queue is non-authoritative. Eligibility for manual review does not authorize an identity decision, merge, membership, snapshot, aggregate, or L2 write.

Raw proposer quality and deterministic gate safety are independent upstream results. The gate result is not used to conceal or replace raw proposer quality.

Gold-dependent action accuracy remains upstream scorer evidence. This stage verifies frozen input hashes, readiness thresholds, and decision-derived structural metrics without reading authority or gold directly.

The current candidates do not have the existing entity, L1 evidence, source revision, and closure bindings required for authoritative materialization. This assessment records those gaps instead of synthesizing authority.

Embedding remains non-authoritative, and `LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.
