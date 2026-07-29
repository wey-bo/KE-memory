# Natural Identity and Membership Proposal v1 Design

Status: frozen for implementation on 2026-07-27.

## Core impact

`none`

This wave adds benchmark-side data, proposal contracts, a programmatic acceptance gate, and scoring. It does not modify the base ontology kernel, dynamic ontology extension interface, L1/L2 extraction stages, authoritative memory bundle, question compiler, symbolic retrieval, or guarded embedding fallback.

## Goal

Move from the eight hand-authored identity-contract cases to a larger natural-text diagnostic that separates candidate generation from authoritative acceptance. A proposer may suggest identity or membership actions, but only a deterministic gate using frozen source-side evidence may accept them.

The result must distinguish two questions:

1. Is the acceptance gate safe enough to prevent unsupported merges and subject-membership errors?
2. Is the proposer itself accurate enough to be considered for automatic candidate generation?

Passing the first question never implies passing the second.

## Chosen approach

The frozen slice contains 12 pairwise cases, split into 6 dev and 6 hidden cases. It reuses only already-authorized BEAM, LoCoMo, and LongMemEval source snapshots. Cases cover:

- same-speaker identity across LoCoMo turns;
- different-speaker separation;
- subject-bound membership and adversarial subject mismatch;
- explicit table-column membership;
- the same vehicle across LongMemEval sessions;
- distinct named events;
- ambiguous repository aliases;
- the frozen LongMemEval project-identity ambiguity.

The source configuration is resolved against `gold-evidence.json`; exact quotes and evidence unit IDs must match. LoCoMo speaker IDs are additionally checked against the frozen raw `locomo10.json` snapshot.

## Artifact separation

`artifacts/identity-memory-experiment/natural-v1/` contains:

- `source-cases.json`: gold-side authoring source with exact source coordinates;
- `public.json`: proposer-visible case text, mention IDs, source references, concepts, and non-label metadata;
- `authority.json`: gate-only trusted identifiers, actor bindings, explicit relation evidence, and required evidence IDs;
- `gold.json`: scorer-only expected actions and critical-error labels;
- `manifest.json`: hashes and case counts;
- `reference-proposals.json`: deterministic candidate-only baseline output;
- `reference-score.json` and `reference-report.md`: formal evaluation.

Public input must not contain expected actions, critical labels, gate authorization facts, or scorer thresholds. The proposer implementation must read only `public.json`.

## Contracts

Relation kinds:

- `identity`: actions are `merge`, `keep_distinct`, or `abstain`;
- `membership`: actions are `include`, `exclude`, or `abstain`.

Each proposal records case ID, action, confidence, evidence mention IDs, reason code, proposer identity/version, and run ID. The programmatic gate returns the original proposal plus accepted action and gate reason.

For identity cases, `merge` requires a shared trusted identifier or explicit same-entity evidence. `keep_distinct` requires conflicting trusted identifiers or explicit distinctness evidence. Unsupported actions become `abstain`.

For membership cases, `include` requires an exact trusted subject/actor binding or explicit relation evidence. `exclude` requires a trusted actor mismatch or explicit non-membership evidence. Missing required evidence always becomes `abstain`.

Embedding, lexical similarity, schema.org mappings, and AMR edges cannot authorize an action.

## Reference proposer

The reference proposer is deliberately simple and reads public data only:

- equal public actor IDs propose `merge`; different actor IDs propose `keep_distinct`;
- overlapping normalized identity surfaces propose `merge`; disjoint named surfaces propose `keep_distinct`;
- membership proposes `include` or `exclude` from public actor/query-subject equality;
- explicit group/member phrases propose `include`;
- otherwise it abstains.

This baseline is a gate stress test, not a model result. It is expected to make at least one unsafe lexical identity proposal that the authority gate must block.

## Metrics and decisions

Safety metrics:

- gated critical false merge count;
- gated critical false membership count;
- gated action accuracy;
- gated abstention correctness;
- required evidence exactness;
- source validation and manifest integrity;
- frozen v5 hash and LongMemEval abstention regression;
- structural fallback count, fixed at zero because this path cannot call embedding.

Proposal-quality metrics:

- raw action accuracy;
- raw critical false merge/membership count;
- raw abstention precision/recall;
- proposal evidence exactness;
- gate intervention rate;
- accepted non-abstain coverage.

`gate_safety_ready=true` requires zero gated critical errors, 1.0 gated accuracy/abstention/evidence/source integrity, preserved v5 regression, and zero fallback.

`proposal_quality_ready=true` is separately pre-registered as raw action accuracy at least 0.85, zero raw critical false merges and false memberships, abstention F1 at least 0.80, and proposal evidence exactness at least 0.95. A reference baseline may therefore produce `gate_safety_ready=true` and `proposal_quality_ready=false`.

## Claim boundary

This wave validates proposal isolation and authority-gate behavior on a small frozen natural diagnostic. It does not run an external model, modify the production extraction path, resolve the real LongMemEval project count, select final storage, or establish product/external-system superiority. The real `LONGMEMEVAL-6d550036` v5 result remains `structured_l2_identity_unresolved`.
