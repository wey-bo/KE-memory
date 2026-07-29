# Natural Identity Proposer Dev Repair and Fresh-v3 Evaluation Design

Status: approved for autonomous execution by the user's standing instruction on 2026-07-27.

## Core impact

`none`

This wave changes benchmark-only proposer instructions and evaluation artifacts. It does not modify the base ontology, dynamic ontology extension, L1/L2 extraction, question handling, symbolic retrieval, guarded embedding fallback, identity authority gate, or scorer behavior.

## Goal

Repair the opaque-v2 model proposer's false-merge and abstention calibration using only dev/diagnostic evidence, then run a newly frozen evaluation whose hidden identity/membership cases were not used to create or select the repaired policy.

Raw proposal quality and deterministic gate safety remain independent decisions. A safe gated result cannot compensate for a raw proposer failure.

## Approaches considered

### A. Frozen prompt policy plus fresh hidden evaluation

Add an explicit conservative identity-decision policy to the proposer prompt, validate it on the six existing dev cases, freeze the passing policy before fresh hidden case authoring, then evaluate once on a new 6-dev + 6-hidden slice. This is the selected approach because the observed defect is decision calibration, not missing scorer or authority-gate functionality.

### B. Deterministic candidate-feature layer

Add program-generated identity features such as shared actor binding, explicit identifier conflict, source continuity, and membership subject match before model proposal. This could improve consistency but begins integrating candidate generation into the identity pipeline before the raw model policy passes a clean gate. It is deferred.

### C. Multi-proposer consensus

Run multiple isolated proposers and accept only consensus candidates. This increases cost and can hide individual proposer errors behind aggregation. It is deferred until a single proposer passes the raw quality gate.

## Development contamination boundary

Only the six v2 dev cases, their gold/authority records, and separately created diagnostic cases may influence policy revisions. The previously scored v2 hidden outcomes are evaluation history only and cannot be included in repair prompts, examples, rationales, or selection rules.

The passing policy is frozen before fresh hidden cases are authored or inspected. The final prompt may name the future public path and fixed run metadata before that public file exists. This establishes chronological evidence that hidden contents did not influence the policy text.

If a dev policy iteration fails, a new immutable policy version is created. Existing failed policy/prompt/run artifacts are retained. Once a policy passes the dev gate, it cannot be edited for the corresponding fresh evaluation.

## Repaired proposer policy

For identity cases:

- `merge` requires explicit public evidence of sameness, a shared authoritative actor binding visible in the public record, or direct anaphoric/possessive continuity that unambiguously names one object;
- same source item, thread, topic, concept type, lexical similarity, or repository/application context alone is insufficient for `merge`;
- `keep_distinct` requires explicit incompatible actor bindings, identifiers, or statements of distinctness;
- surface, role, class, title, format, or time differences alone are insufficient for `keep_distinct` when both mentions could still denote one entity;
- otherwise the proposer must `abstain`.

For membership cases:

- `include` or `exclude` requires an explicit subject/actor binding or explicit membership/non-membership statement visible in public evidence;
- topic relevance or embedding-like similarity is insufficient;
- otherwise the proposer must `abstain`.

Evidence mention IDs must remain case-local. Non-abstain decisions must cite all public mentions used by the decision. The policy does not authorize writes.

## Dev-only gate

The dev repair root contains exactly the six v2 dev cases with their existing opaque IDs and unchanged semantics. A fresh no-history proposer reads only the dev prompt and dev public file. Proposals are frozen before dev authority/gold scoring.

The policy can advance to fresh evaluation only if all dev conditions pass:

- raw action accuracy `1.0`;
- raw critical false merge count `0`;
- raw critical false membership count `0`;
- raw abstention F1 `1.0`;
- proposal evidence exactness `1.0`.

Gate safety is still reported separately but cannot qualify a failing policy.

## Fresh-v3 slice

The formal evaluation contains 12 cases: the unchanged six dev semantics plus six newly authored hidden cases. Hidden cases use frozen BEAM, LoCoMo, or LongMemEval source snapshots already authorized in this workspace, but cannot reuse a v2 hidden case or the same hidden evidence-unit combination.

Fresh hidden composition is fixed at three identity and three membership cases:

- identity: one `merge`, one `keep_distinct`, one `abstain`;
- membership: one `include`, one `exclude`, one `abstain`.

At least two hidden cases must cross sessions, and all quotes/source coordinates must replay through the existing source validator. Authority and gold remain private. Case and mention IDs are derived under `natural-identity-membership-fresh-v3:2026-07-27` and cannot overlap natural-v2 IDs.

The fresh preparer records the selected policy/prompt hashes, v2 protected hashes, source hashes, no-overlap checks, action distribution, semantic replay, and claim boundaries. All formal slice files become `0444`.

## Data flow

1. Create a dev-only slice by filtering the frozen v2 source to the six dev cases.
2. Freeze policy version 1 and render/freeze both dev and future final prompts.
3. Dispatch a no-history dev proposer, freeze its proposals/provenance, then score.
4. If dev fails, classify only dev errors and create a new policy version. Do not inspect fresh hidden.
5. After dev passes, author and source-validate six fresh hidden cases under the pre-frozen selection contract.
6. Prepare and freeze the fresh-v3 opaque slice, including no-overlap and policy-hash evidence.
7. Dispatch a new no-history final proposer that reads only the already frozen final prompt and fresh public file.
8. Freeze proposals/provenance before authority/gold scoring.
9. Score and replay score/report byte-for-byte before freezing outputs.

## Formal gates

The fresh evaluation keeps the existing preregistered thresholds:

- raw action accuracy at least `0.85`;
- raw critical false merge count `0`;
- raw critical false membership count `0`;
- raw abstention F1 at least `0.80`;
- proposal evidence exactness at least `0.95`.

`gate_safety_ready` and `proposal_quality_ready` are reported independently. If fresh-v3 fails, its hidden outcomes are not used to revise the same evaluation version; another attempt requires a new policy decision based on dev/diagnostic evidence and another fresh hidden version.

## Unchanged boundaries

- Model proposals remain non-authoritative candidates.
- No automatic merge, membership, or L2 write path is added.
- Embedding cannot authorize identity, membership, or facts.
- `LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.
- External memory systems are not rerun.
- Prior Fusion Memory material remains prohibited.
- Work remains in `/public/home/wwb/KE-mem/KE-memory-next-prep-20260727` on H100.
- Storage-profile comparison remains downstream of stable identity, extraction, query compilation, evidence closure, cross-session aggregation, and real benchmark expansion.

## Verification

Tests must prove dev-only filtering, policy/prompt immutability, policy hash binding, fresh ID derivation, v2 ID/evidence non-overlap, hidden action distribution, source replay, exact proposal coverage, phase order, deterministic score replay, formal permissions, and protected hashes. The full `tests/natural_memory_benchmark` suite and all identity/slice/ledger validators must pass before reporting completion.
