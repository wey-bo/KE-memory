# Fresh-v3 Identity Proposer Error Analysis

- Run ID: `run-20260727T160000Z-claude-sonnet-4-6-fresh-v3`
- Proposals SHA-256: `8621abdf18359fe04d4c3f9ea965c8ef676331eab691d11eac6115ab13831f36`
- Score SHA-256: `5a4b9163acff61652cc6650cebb816587eb4f4dca3b89315f75d3af05c6f933d`
- Report SHA-256: `95ccdaeed364b1c16f1ad84d7b777aa4584725fc004da98223c576f97ec11f47`

## Independent Results

Raw proposer quality passed the preregistered threshold:

- action accuracy: `0.9166666666666666`
- critical false merge: `0`
- critical false membership: `0`
- abstention F1: `0.8571428571428571`
- proposal evidence exactness: `1.0`

Deterministic gate safety did not pass the complete gate contract:

- gated action accuracy: `0.9166666666666666`
- gated critical false merge: `0`
- gated critical false membership: `0`
- gated abstention correctness: `1.0`
- gate interventions: `0`

The gated result does not replace or hide the raw result. The gate preserved the proposer's abstention and did not infer an authority-backed action that the proposer did not request.

## Error Classification

- false merge: `0`
- false membership include: `0`
- false abstention: `1`
- evidence error: `0`

The single failure is hidden membership case `case-495ffd78c2ed975d`.

- expected action: `exclude`
- proposed and gated action: `abstain`
- proposer reason: `insufficient_evidence`
- public query subject: Melanie
- public source actor: `person:caroline`
- cited evidence: `mention-2a14771533cba629`

The public non-null source actor binding differs from the query subject, so the frozen policy calls for `exclude`. The proposer abstained despite that visible mismatch. This is a completeness/calibration error, not an unsafe membership write.

## Candidate Generation Boundary

The result supports only the existing non-authoritative shape: a public-only proposer may emit immutable candidates for the unchanged deterministic identity gate. It does not authorize automatic merge, membership, or L2 writes. Pipeline integration remains deferred because the complete gate contract is not ready and the hidden error cannot be used to tune policy-v3.

`LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`. Embedding remains non-authoritative. No external memory system was rerun. Core impact: `none`.
