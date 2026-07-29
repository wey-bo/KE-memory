# Typed Extractor Fresh-Hidden V3 Preregistration Design

## Status

Approved by the user's standing instruction to continue the established design
without intermediate confirmation. This design is written while the v3
preregistration root, authoring implementation/test/receipt, evaluation root,
hidden data, and model runs are absent.

## Goal

Freeze a new contamination-resistant preregistration after the taxonomy-only
dev wave passed strict raw proposer quality and deterministic gate safety. This
stage creates only `preregistration.json`; it does not author hidden cases, call
a proposer, score proposals, integrate the pipeline, or write memory state.

## Alternatives Considered

1. Reuse fresh-v2 authored cases under new opaque IDs. Rejected because the
   semantic distribution and case content have already been evaluated.
2. Select a natural benchmark slice immediately. Rejected because source and
   annotation changes would confound typed-extraction requalification.
3. Freeze a new deterministic authored-hidden protocol before its authoring
   implementation exists. Selected because it binds composition, exclusions,
   chronology, failure behavior, and scoring before any hidden content exists.

## Architecture

Add an independent strict contract in
`tools/natural_memory_benchmark/typed_extractor_fresh_v3_prereg.py`. It binds
the final taxonomy L1 repair-v1 and L2 unchanged-prompt baseline chains, exact
strict gates, prior exclusion artifacts, a fixed future blueprint composition,
model isolation, proposal-before-scoring chronology, and zero-write boundaries.
The v1 and v2 preregistration modules, shared scorers, query modules, authority
modules, and existing immutable artifacts remain unchanged.

The required chronology is:

1. Freeze and validate this preregistration while the evaluation root, future
   authoring module/test, authoring receipt, and materialization module/test are
   absent.
2. Implement deterministic authoring and freeze an implementation receipt that
   binds the preregistration, module, test, blueprint manifests, and exclusions.
3. Materialize every blueprint exactly once and freeze source/public/authority/
   gold/manifest/chronology artifacts.
4. Run one no-history, public-only proposer request per layer. Freeze proposals
   and provenance before an independent scoring stage reads authority or gold.

The preregistration validator is a pre-authoring validator. Later phases bind
its immutable SHA-256 and do not reinterpret the original absence check.

## Passing Chains

L1 binds taxonomy repair-v1:

- run `run-20260729T042500Z-deepseek-chat-official-typed-l1-taxonomy-repair-v1`;
- prompt SHA-256
  `a5250a453863f3cfd388613d6633d8a529485a11c5226d2965c8235a9c1dc342`;
- proposals/provenance/score/qualification SHA-256 values
  `db468cc0251abe48bfb1c98dead13471b16e32556df3a61da528e3e29de95750`,
  `d6d699b30d806ebdc938ea9d1d2c5a8271c3b0de4cc9f97765e9f49f2433b452`,
  `dfbb8a415e6654b89f4ac09e0ae72bc45d1687cec13e69cbd2211f6ef295bb92`,
  and `92e627fb72ba18ef1458aa9ef810bf8bf9b5efad3a12cc0f7559231e07a3c3de`.

L2 binds taxonomy unchanged-prompt baseline-v1:

- run `run-20260729T041501Z-deepseek-chat-official-typed-l2-taxonomy-baseline-v1`;
- prompt SHA-256
  `d547a7d8b61eea33735bce4b3c96bb34466bb0fa6eb95d4e1b9070d64f211c6a`;
- proposals/provenance/score/qualification SHA-256 values
  `c735225a119c546fcba44372b5c56f32a2d1bd7caba3997ab51af4dc3ee25084`,
  `c178ac3adcb5ed6c0d7ea70238e414b5a33c20112ee8edeb335b5d711fb2e947`,
  `1c04a09d29f7d23abba85df249fb4194fd99bea2faca1ef7a288aa23444ee796`,
  and `643944140f7348347448de3728b891d9e1209f05ba96384d3885b998e6f00ea4`.

Both chains must report every strict quality metric as exactly `1.0`, and raw
critical false emission, gate intervention, and deterministic critical false
materialization as exactly `0`. The contract also binds the taxonomy source,
public, authority, gold, and manifest files and prior fresh-v2 artifacts used by
later contamination checks. Every bound artifact is already read-only.

## Authorship And Composition

Dataset ID is `typed-extractor-v3-fresh-hidden-v1`. The namespace is
`typed-extractor-fresh-hidden-v3-authored:2026-07-29`; authoring policy is
`deterministic_blueprints_use_all_no_replacement_v2`.

L1 contains exactly 24 cases, three per taxonomy family:

- `false_emission`;
- `false_abstention`;
- `role_or_local_entity`;
- `time`;
- `condition_or_scope`;
- `evidence`;
- `derivation_or_speaker`;
- `lifecycle`.

Secondary labels must cover kind, predicate/operator, modality/polarity, and
operation provenance without changing primary-family counts.

L2 contains exactly 18 cases, two per taxonomy family:

- `unsupported_modality_control`;
- `unresolved_selection_control`;
- `incompatible_support_control`;
- `incomplete_closure_control`;
- `coreference_case`;
- `task_composition_case`;
- `lifecycle_case`;
- `state_summary_case`;
- `preference_aggregation_case`.

Secondary labels must provide scored opportunities for false emission, false
abstention, evidence, support ID, kind, structured claim, abstraction, closure,
source coverage, and summary fields without changing primary-family counts.

Every blueprint must be used. Semantic filtering, hand-picking, replacement,
and post-generation resampling are forbidden. Invalid generation aborts the
evaluation. Future validation rejects reused private/public identifiers,
evidence identifiers, exact evidence text, or normalized semantic signatures
from every bound dev, diagnostic, and fresh-hidden exclusion artifact.

## Model And Scoring Policy

The requested alias is `deepseek-chat`; the response model is recorded
separately. Each layer gets one semantic request, no inherited conversation
history, and access only to its frozen prompt and public payload. A transport or
invalid-JSON retry requires a new immutable run with identical frozen inputs; a
semantic failure is never retried within v3.

Authority and gold are unavailable until proposals and provenance are frozen.
Raw proposer quality and deterministic gate safety receive separate decisions.
A deterministic demotion cannot convert a raw proposer error into a pass.

## Failure Handling

Unknown fields, coercive scalar types, missing or mutable bound artifacts, hash
drift, a non-qualified passing chain, premature future artifacts, family/count
drift, contamination overlap, replacement, or chronology drift fail closed. A
later raw failure closes v3; repair is permitted only on a new dev/diagnostic
set followed by another separately frozen fresh-hidden preregistration.

## Boundaries

- This stage writes only the immutable preregistration file and makes zero model
  requests and zero hidden writes.
- No L1, L2, revision, source-revision, closure, identity, membership, snapshot,
  or aggregate write is authorized.
- Pipeline integration remains unauthorized even if v3 later passes.
- Embedding is not an authority for facts, identity, membership, roles, or
  closure.
- Candidate-generation v3 and its separate manual adjudications remain
  immutable and are not materialized.
- `LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.
- External memory systems are not rerun and old Fusion Memory is not accessed.

## Verification

Focused tests first fail because the independent v3 module does not exist. They
then verify strict schema rejection, exact passing hashes and metrics, exact
family/count contracts, future-path absence, immutable one-file output, input
and code drift detection, and CLI parity. Formal freeze requires both the
preregistration and evaluation roots to be absent; the resulting JSON is mode
`0444` and is immediately validated.
