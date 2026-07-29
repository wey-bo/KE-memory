# Typed Extractor Fresh-Hidden V2 Preregistration Design

## Status

Approved by the user's standing direction on 2026-07-28 to execute the next
stage without intermediate confirmation. This design is written before the v2
preregistration, authoring implementation, authoring receipt, hidden source,
public input, authority, gold, proposal, or score artifacts exist.

## Goal

Freeze a contamination-resistant contract for the second fresh-hidden typed
extractor evaluation. This stage freezes only the preregistration. It does not
author hidden cases, run a proposer, score proposals, integrate candidates, or
authorize any memory write.

## Alternatives Considered

1. Reuse the bridge-v3 remainder with a new namespace. Rejected: fresh-hidden
   v1 consumed all eight unused cross-turn L2 records, so this would not be a
   fresh evaluation.
2. Select a new natural-benchmark source immediately. Rejected for this stage:
   source choice, licensing, and benchmark-specific annotation would add new
   variables before the extraction contract itself is requalified.
3. Freeze a deterministic authored-hidden protocol, then implement and freeze
   the authoring mechanism before creating any hidden data. Selected: it binds
   composition, chronology, exclusions, and failure behavior before any case
   content exists, while remaining independent of the exhausted bridge pool.

## Architecture

The v2 preregistration is a new strict Pydantic contract and CLI pair. It does
not modify or import v1 preregistration behavior. The contract binds the final
passing L1 V10 and L2 v9 prompt/model/scoring chains, exact qualification
thresholds, fixed authored-case families, prior-data exclusion hashes, future
artifact paths, model isolation, and zero-write boundaries.

Hidden creation is a later three-step chronology:

1. Freeze and validate this preregistration while the evaluation root, future
   authoring module/test, and authoring receipt are all absent.
2. Implement and test the deterministic authoring module, then freeze an
   implementation receipt containing its code/test/contract hashes while the
   evaluation root remains absent.
3. Generate all preregistered cases exactly once, freeze source/public/
   authority/gold, and only then dispatch one public-only proposer run per
   layer. Proposals and provenance freeze before independent scoring reads
   authority or gold.

The preregistration validator is deliberately a pre-authoring gate. Later
chronology verification must bind its immutable SHA-256 and mode instead of
rerunning a validator whose required future paths are no longer absent.

## Frozen Passing Chains

L1 is bound to:

- prompt `typed-extractor-v2-l1-dev-repair-v2/proposer-prompt-l1-v10.md`,
  SHA-256 `b868bb2baaf1dfb3c27f99e2fe29888e2af0c57e56be3d2ecf70bfb6d2bcdfcf`;
- run `run-20260728T130544Z-deepseek-chat-official-typed-l1-dev-repair-v10`;
- proposals/provenance/score/qualification SHA-256 values
  `7cca8c171d784fbee1ea4849c52403fa6446f3d78fe746cec4134a3effb95c39`,
  `8a2ef39bf2da9a059a24537505b05f5391a1806f5012642fa173864746dbf483`,
  `993200f235b075b4f7e5e72bf37d19cc8427d360ce75ab5375f91f3e7923ba43`,
  and `377d91553db76fa1e3d48602e739aed255b107fca3856a35908234c769cb93a0`.

L2 is bound to:

- prompt `typed-extractor-v2-l2-dev-repair-v3/proposer-prompt-l2.md`,
  SHA-256 `d547a7d8b61eea33735bce4b3c96bb34466bb0fa6eb95d4e1b9070d64f211c6a`;
- run `run-20260728T123925Z-deepseek-chat-official-typed-l2-dev-repair-v9`;
- proposals/provenance/score/qualification SHA-256 values
  `d27e614b8bef0dfbc2dedf53eb7a320b5c1f1fcdc87021bd951bc5d02082d77a`,
  `2f6d87a6a71c3dd471606cdcf76d2e59b31879a6ba47a0171c1acbab4b069049`,
  `ea1c87d15f775b6d1e93dc1b80ce63125dfdd33e2b73713d4312c6b41cfa8e7c`,
  and `4abdc7c1f256178c13d5b47cc0455c5ce183ee3ab40c0fbc9f723967d9885a46`.

The contract also binds the final diagnostic source/public/authority/gold/
manifest files, fresh-hidden v1 preregistration and evaluation inputs, and the
relevant L1/L2 contract, scorer, model-freeze, qualification, and IO code.
Every bound non-source artifact must already be read-only.

## Authorship And Composition

Dataset ID is `typed-extractor-v2-fresh-hidden-v2`. The authoring namespace is
`typed-extractor-fresh-hidden-v2-authored:2026-07-28`, and the policy is
`deterministic_blueprints_use_all_no_replacement_v1`.

L1 contains exactly 24 cases, four from each family:

- `explicit_event_roles`;
- `condition_scope`;
- `modality_time`;
- `lifecycle_revision`;
- `derivation_epistemic`;
- `abstention_no_memory_controls`.

L2 contains exactly 12 cases, two from each family:

- `coreference_task_composition`;
- `preference_state_aggregation`;
- `lifecycle_supersession`;
- `multi_evidence_closure`;
- `abstraction_structured_claim_boundary`;
- `abstention_unresolved_controls`.

Every authored blueprint is used. Semantic filtering, hand-picking, case
replacement, and post-generation resampling are forbidden. Invalid generation
aborts the evaluation; it does not permit substituting an easier case. Future
validation must reject reused private/public IDs, evidence IDs, source text,
or normalized semantic signatures from bound dev, diagnostic, or fresh-v1
exclusion artifacts.

Public proposer input contains only opaque case/candidate/support/turn/session
references, raw case text/evidence, and the explicitly versioned public
vocabularies. Private family labels, source authority, expected decisions,
typed gold, and exclusion mappings are not proposer-visible.

## Qualification And Reporting

Every scorer metric used by the final strict diagnostic qualification is fixed
at exact `1.0` for v2. This includes proposal coverage, schema validity,
decision and abstention, evidence, and every L1/L2 semantic field family.
Raw critical false emission, deterministic critical false materialization, and
gate intervention counts must each be `0`.

Raw proposer quality and deterministic gate safety are reported as separate
decisions. A deterministic demotion cannot convert a raw error into a proposer
pass. Each layer receives one semantic proposer run. Transport or invalid-JSON
retries require a new immutable run with the same frozen prompt and public
input; semantic failures are never retried on v2.

The requested model alias is `deepseek-chat`. The response model identifier is
recorded separately. The proposer inherits no conversation history and may
read only its frozen layer prompt and public payload. Authority and gold are
unavailable until proposals and provenance are immutable.

## Failure Handling

Any preregistration drift, missing/read-write passing artifact, premature
future artifact, invalid authoring family count, contamination overlap,
post-generation replacement, or chronology mismatch aborts the stage.

A later raw proposer failure closes fresh-hidden v2. Errors are classified as
false emission, false abstention, evidence, role/entity, qualifier/time/
lifecycle, kind/claim/abstraction/closure, or source coverage failures. Repair
may occur only on a new dev/diagnostic set followed by another separately
preregistered fresh-hidden evaluation.

## Boundaries

- No hidden artifact or model request is created in this preregistration stage.
- No L1, L2, revision, closure, identity, membership, snapshot, aggregate, or
  source-revision write is authorized.
- Embedding is not an authority for facts, identity, roles, membership, or
  closure.
- The frozen candidate-generation v3 queue and separate manual adjudications
  are neither read for materialization nor modified.
- `LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.
- External memory systems are not rerun, old Fusion Memory is not accessed,
  and concurrent query work is not modified.
- A v2 pass would authorize only candidate-generation integration assessment,
  not automatic authoritative memory writes or a final storage format.

## Verification

Focused tests must first fail because the independent v2 module and CLI do not
exist. After implementation they verify strict schema rejection, exact frozen
chains, exact family/count/threshold contracts, absence chronology, immutable
write behavior, hash drift detection, and CLI parity. The formal freeze may
occur only after confirming both the preregistration root and evaluation root
are absent. The resulting file is mode `0444` and is validated before any next
stage begins.

## Review Hardening And Formal Artifact

The first prereg-v2 artifact remains immutable but is superseded. Read-only
review found that its Pydantic models accepted coercive scalar types and that
its chronology claimed filesystem mtime evidence without recording mtimes.
The hardened contract uses strict models, parses a real UTC timestamp, and
accurately describes its evidence as `filesystem-presence-plus-sha256` with a
`caller_supplied_untrusted_utc_label`.

The current formal artifact is
`artifacts/automatic-extraction-assessment/typed-extractor-v2-fresh-hidden-prereg-v3/preregistration.json`,
schema `typed-extractor-fresh-v2-preregistration-v2`, frozen at
`2026-07-28T14:08:22Z`. Its SHA-256 is
`1455bb7d5bb35b61809c78180ebf766573c1561e39bbeddda4a80f939a893760`,
size `11016` bytes, and mode `0444`.
