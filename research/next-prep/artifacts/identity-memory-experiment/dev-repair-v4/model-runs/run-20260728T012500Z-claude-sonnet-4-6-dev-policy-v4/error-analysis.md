# Identity Proposer v4 Dev Error Analysis

Run: `run-20260728T012500Z-claude-sonnet-4-6-dev-policy-v4`

## Outcome

- Raw proposer quality: pass
- Deterministic gate safety: fail
- Raw action accuracy: `0.9166666666666666`
- Raw critical false merges: `0`
- Raw critical false memberships: `0`
- Raw abstention F1: `0.8571428571428571`
- Proposal evidence exactness: `1.0`
- Gated action accuracy: `0.9166666666666666`

The raw and gated results are reported separately. The raw-quality threshold pass
does not override the deterministic gate-safety failure.

## Classification

Exactly one case failed: `case-105e39b70808e864`.

- Relation: membership
- Expected action: `include`
- Proposed action: `abstain`
- Gated action: `abstain`
- Error category: false abstention
- Evidence category: exact; the required case-local mention was cited
- False merge category: none
- False membership category: none

The public quote is an imperative requested-member statement for the member named
by the public case. The proposer reason code,
`null_actor_binding_no_explicit_membership`, shows that policy-v4 did not make
this observable imperative pattern operational enough under the null-actor
fallback.

All six independent actor-binding diagnostic cases were correct, including both
non-null matches, both non-null mismatches, and both null-actor abstentions.

## Authorized Repair

Remain on the frozen dev slice. Clarify that an imperative/request verb such as
`include`, `add`, or `create`, applied to the same public member surface in a
requested-membership question, is explicit membership evidence even when the
quoted fragment omits the group name. Re-freeze the policy and prompts, then run
a new zero-history proposer. Do not author fresh-v4 hidden data until both gates
pass.

No fresh-v3 hidden evidence or surface form was used for this repair. No automatic
merge, membership write, or L2 write is authorized.
