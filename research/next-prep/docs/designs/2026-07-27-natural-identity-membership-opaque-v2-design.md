# Natural Identity and Membership Opaque-ID v2 Design

Status: approved for implementation on 2026-07-27.

## Core impact

`none`

This wave decontaminates proposer-visible identifiers and repeats the existing proposal-only experiment. It does not modify the base ontology, dynamic ontology extension, L1/L2 extraction, question handling, symbolic retrieval, guarded embedding fallback, authoritative identity policy, or deterministic scorer.

## Goal

Produce a controlled v2 copy of the frozen 12-case natural identity/membership slice in which every proposer-visible case and mention identifier is opaque. All semantic content, source coordinates, split assignments, authority facts, gold labels, and scoring thresholds remain unchanged so that identifier decontamination is the only experimental variable.

The v2 experiment must answer two questions separately:

1. Does an isolated model proposer pass the pre-registered raw proposal-quality gate without outcome-bearing identifiers?
2. Does the existing deterministic authority gate continue to prevent unsupported identity and membership actions?

Passing gate safety cannot substitute for passing raw proposal quality.

## Chosen approach

Add a benchmark-only opaque-ID preparation layer alongside the existing v1 contracts. The preparation layer reads the frozen v1 `source-cases.json`, creates a deterministic bijection for dataset, case, and mention identifiers, writes a separate `natural-v2` source configuration plus a private mapping sidecar, and then delegates public/authority/gold/manifest generation to the existing freeze implementation.

The current v1 files, Pydantic contracts, authority gate, scorer, and report renderer remain unchanged. The v2 payloads continue to use the existing structural schema versions because only identifiers and dataset identity change.

## Identifier policy

V2 identifiers use these exact formats:

- case: `case-` followed by 16 lowercase hexadecimal characters;
- mention: `mention-` followed by 16 lowercase hexadecimal characters;
- dataset: `natural-identity-membership-opaque-v2`.

Identifiers are derived deterministically with SHA-256 from a frozen namespace, identifier kind, ordinal, and v1 identifier. The digest is an audit-stable pseudonym, not a security boundary. The proposer never receives the namespace inputs or mapping sidecar.

The case identifier cannot encode split, relation kind, entity surface, expected action, or ambiguity. The mention identifier cannot encode actor, surface, relation, action, membership, distinctness, mismatch, or abstention. IDs must be unique, the v1-to-v2 mapping must be bijective, and no v1 case or mention ID may remain in v2 `public.json`.

## Controlled equivalence

The preparer verifies v1/v2 equality after normalizing only these permitted differences:

- top-level `dataset_id`;
- every `case_id` and its cross-file references;
- every `mention_id` and its authority/proposal evidence references.

Case order, split, relation kind, question, mention order, source item ID, evidence unit ID, quote, surface, concept, source actor, actor locator, query subject, group/member surface, authority values, required evidence, gold action, and critical-error labels must be byte-equivalent after ID normalization. Any other difference aborts preparation before a model is called.

## Artifacts

`artifacts/identity-memory-experiment/natural-v2/` contains:

- `source-cases.json`: v2 gold-side source configuration;
- `opaque-id-map.json`: private bijective v1/v2 mapping and derivation metadata;
- `preregistration.json`: frozen experiment protocol, thresholds, hashes, and claim boundaries;
- `public.json`: the only dataset file visible to the proposer;
- `authority.json`: deterministic gate-only facts;
- `gold.json`: scorer-only expected actions and critical labels;
- `manifest.json`: existing source/input/output integrity manifest;
- `model-runs/<run-id>/proposals.json`: frozen model proposals;
- `model-runs/<run-id>/dispatch.json`: pre-dispatch public/prompt hashes, model metadata, and declarative isolation contract; this file is not proposer-visible;
- `model-runs/<run-id>/provenance.json`: model, prompt, allowed-input, isolation, and proposal hashes;
- `model-runs/<run-id>/score.json`: deterministic scorer output;
- `model-runs/<run-id>/report.md`: rendered raw/gated report.

The seven v2 slice files (source, mapping, preregistration, public, authority, gold, and manifest), proposer prompt, and private dispatch record are frozen before the model run. Proposal and provenance files are frozen before scoring. Score and report are frozen after deterministic replay. Existing v1 artifacts are never overwritten or rewritten.

## Isolation and data flow

1. Prepare and validate the complete v2 slice without invoking a model.
2. Record v1 protected hashes, v2 hashes, semantic-equivalence result, identifier-policy result, and pre-registered thresholds. Freeze a private dispatch record containing the exact public/prompt hashes and proposer/run metadata.
3. Start a proposer with `fork_turns="none"` so it receives no conversation history.
4. Allow the proposer to read only v2 `public.json` plus the proposal output contract and destination path. Explicitly prohibit reads of v1, mapping, preregistration, source cases, authority, gold, reference artifacts, previous model runs, and scorer outputs.
5. Validate proposal schema, exact case coverage, evidence mention IDs, run metadata, and the public/prompt hashes in the private dispatch record. Freeze proposals and provenance before any scoring access.
6. In a separate deterministic scoring stage, read v2 public/authority/gold/manifest plus the frozen proposals and run the existing `score-identity-proposals` command.
7. Replay score/report into an isolated temporary path and require byte equality before freezing the formal outputs.

Agent-level filesystem restrictions are declarative rather than OS-enforced. The provenance record must state this accurately and must not claim a hardware or container isolation guarantee.

## Gates and decisions

The existing thresholds remain pre-registered:

- raw action accuracy at least 0.85;
- raw critical false merge count equal to 0;
- raw critical false membership count equal to 0;
- raw abstention F1 at least 0.80;
- proposal evidence exactness at least 0.95.

`gate_safety_ready` and `proposal_quality_ready` are reported independently. Raw failures remain visible even when deterministic gating produces a safe result.

If proposal quality fails, classify errors into false merge, false membership, abstention, and evidence categories. Prompt or candidate-generation changes may use only dev/diagnostic data. Hidden results cannot be used for iterative repair; a subsequent evaluation requires a newly frozen evaluation version.

If proposal quality passes, the next activity is a design evaluation for connecting candidate generation to the current identity pipeline. Passing does not authorize automatic merge, membership, L2 aggregation, or authoritative writes.

## Error handling and immutability

Preparation fails before model invocation on malformed opaque IDs, collisions, non-bijective mapping, old-ID residue, semantic drift, source replay failure, manifest mismatch, or conflicting destination files. Byte-identical preparation replay is allowed. Proposal freezing reads the private dispatch record written before proposer dispatch and fails on any public/prompt hash mismatch, missing/duplicate cases, invalid action families, unknown evidence IDs, or inconsistent model/run metadata. Scoring never repairs proposals and only writes to a new run directory.

All formal v2 artifacts use immutable writers where available and are made read-only after their phase completes. Temporary replay files are outside the frozen run directory and are removed after verification.

## Verification

TDD coverage must demonstrate:

- deterministic opaque mapping and exact formats;
- rejection of outcome-bearing or malformed IDs;
- mapping bijection and collision rejection;
- no v1 identifier residue in v2 public input;
- controlled semantic equivalence across source/public/authority/gold;
- immutable preparation and CLI behavior;
- proposal coverage and allowed-input provenance checks;
- v1 public/run and six protected experiment hashes remain unchanged;
- focused tests, full `tests/natural_memory_benchmark`, identity/slice/ledger validators, and deterministic score/report replay pass.

## Unchanged boundaries

- Model proposals remain non-authoritative candidates.
- The core memory skeleton is unchanged unless separately authorized.
- Embedding cannot authorize facts, identity, or membership.
- `LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`; it cannot be forced to count 2.
- Mem0, Graphiti, Hindsight, MemPalace, Zep, and other external memory systems are not rerun.
- Previous Fusion Memory code, tests, architecture, and experimental results remain prohibited.
- All subsequent work runs only in `/public/home/wwb/KE-mem/KE-memory-next-prep-20260727` on H100.
- After identity candidate generation stabilizes, work proceeds in order through L1/L2 automatic extraction, question compilation, evidence closure, cross-session aggregation, real benchmark expansion, and only then storage-profile efficiency/execution/operations comparison.
