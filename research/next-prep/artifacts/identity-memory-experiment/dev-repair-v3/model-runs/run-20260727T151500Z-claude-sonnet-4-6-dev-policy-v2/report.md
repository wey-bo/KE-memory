# Natural Identity and Membership Proposal v1 Report

- Run ID: `run-20260727T151500Z-claude-sonnet-4-6-dev-policy-v2`
- Cases: `6`
- Gate safety: `pass`
- Proposal quality: `fail`
- Raw action accuracy: `0.8333333333333334`
- Gated action accuracy: `1.0`
- Raw critical false merges: `1`
- Gated critical false merges: `0`
- Raw critical false memberships: `0`
- Gated critical false memberships: `0`
- Gate interventions: `1`
- Proposal evidence exact rate: `1.0`
- Structural fallback count: `0`

## Interpretation

The reference proposer is not a model run. It is a deterministic, public-only gate stress test. Gate safety and proposal quality are independent decisions: a safe gate may pass while the proposer fails its quality threshold.

This diagnostic does not modify the core memory skeleton. It adds no automatic merge path, does not change L1/L2 extraction, question processing, symbolic retrieval, or guarded embedding fallback, and does not establish product or external-system superiority.

The frozen real LongMemEval result remains `structured_l2_identity_unresolved`; neither lexical overlap nor Extended-AMR edges are factual authority for resolving it.
