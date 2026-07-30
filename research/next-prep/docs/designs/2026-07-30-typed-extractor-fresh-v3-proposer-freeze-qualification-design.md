# Typed Extractor Fresh-V3 Proposer Freeze And Qualification Design

## Status

Approved by the user on 2026-07-30. This document is written after commit
`703b990a883a0c1e28c2688949beb3b22c97ae65` published and recorded the exact
pre-model fresh-v3 materialization. Approval authorizes only the two one-shot
proposer freezes and independent qualification defined here; it does not
authorize pipeline integration or any authoritative memory write.

## Goal

Run exactly one no-history, public-only semantic proposer request for each of
the frozen L1 and L2 layers, freeze each dispatch/raw response/proposal/
provenance chain before any scorer reads authority or gold, then produce an
independent preregistered qualification decision. Stop after the qualification
is frozen, whether the result passes, fails, or is incomplete because a layer
could not produce a valid proposal freeze.

## Alternatives

1. Reuse the fresh-v2 procedure and its temporary compatibility manifests.
   This is the smallest immediate change, but fresh-v2 required post-freeze
   compatibility and supersession receipts for an exact-output-hash mismatch,
   a hard-coded L2 dev threshold shape, and an absolute guard path. Repeating
   that procedure would knowingly carry avoidable ambiguity into fresh-v3.
2. Add a fresh-v3 phase controller and narrowly parameterize the existing
   scorer entry points while retaining their current defaults. Selected. The
   controller binds materialization, prompts, public inputs, run paths, request
   count, proposal chronology, and qualification thresholds. The scorer keeps
   exact manifest validation but accepts an explicit exact filename set and an
   explicit threshold contract for v3; all historical callers preserve their
   existing behavior.
3. Copy the L1 and L2 scorers into new v3-only modules. This maximizes isolation
   but duplicates large scoring and gate logic, making parity drift more likely
   and review substantially harder.

## Architecture

Add two independent modules and focused tests:

- `typed_extractor_fresh_v3_proposer_freeze.py` owns the pre-request gate,
  exact run layout, dispatch creation, one-shot transport orchestration,
  proposal/provenance freeze, failure receipts, and read-only proposal-freeze
  validation. It may call the existing L1/L2 dispatch, API runner, parser, and
  proposal-freeze functions, but it never reads authority or gold.
- `typed_extractor_fresh_v3_qualification.py` owns the phase transition from
  two complete proposal freezes to scoring, exact preregistered threshold
  checks, per-layer qualification, overall decision, and final audit. It has no
  model transport interface and cannot begin unless both layer freeze receipts
  are complete and immutable.

The existing `typed_extractor_l1.py` and `typed_extractor_l2.py` scorer entry
points receive only backward-compatible parameters for exact manifest output
filenames and, for L2, the required threshold mapping. Their legacy defaults
remain unchanged. Fresh-v3 passes all four official output filenames per layer
and the exact preregistration thresholds, so no rewritten manifest, temporary
scoring view, or compatibility receipt is needed.

All implementation code, tests, and scorer parameterization must be committed
and independently reviewed before either model request. The model runs then
bind those committed blobs and the materialization fact commit.

## Fixed Inputs And Bindings

The controller requires all of the following before creating a run directory:

- repository/workspace and linked-worktree identity fixed to the active
  extraction worktree;
- materialization fact commit
  `703b990a883a0c1e28c2688949beb3b22c97ae65` in current HEAD ancestry;
- official evaluation ID/root
  `typed-extractor-v3-fresh-hidden-v1` and exact materialization chronology SHA
  `fe3cfbd739de477d99089c4ed6f85322236e00deb9b405596f038366bee16cca`;
- valid canonical replay of the ten official payloads, file modes `0444`, and
  root/layer modes `0775`;
- active authoring receipt SHA
  `c810f421d5a3b0726b862ec2f12c89e0d638e0747892637e2a32977587b7ef8c`;
- L1 prompt SHA
  `a5250a453863f3cfd388613d6633d8a529485a11c5226d2965c8235a9c1dc342`;
- L2 prompt SHA
  `d547a7d8b61eea33735bce4b3c96bb34466bb0fa6eb95d4e1b9070d64f211c6a`;
- L1 public SHA
  `d3cf87588f4c2d70a2420ffc5a961c4e1a3cc3beeb9d5222af7b5d6c256a9159`;
- L2 public SHA
  `9f0fe37d410c9f121d9064f49caaa6dda2dd365fb6acae29214ca484c221e160`;
- requested alias `deepseek-chat`, response model recorded from the raw API
  response, and isolation context `fresh-agent-no-history-declarative`;
- unchanged candidate queue SHA, live guard fingerprint/counts, materializer
  hashes, parallel-session hashes, manual-adjudication false, unresolved
  LongMemEval, and all nine automatic write counts equal to zero.

The controller binds the committed SHA-256 of itself, its tests, the
qualification module/tests, and the narrowly changed shared scorer files/tests.
Any drift before either request or before scoring fails closed.

## Formal Run Layout

Each layer receives exactly one formal run directory:

```text
l1/model-runs/<l1-run-id>/
l2/model-runs/<l2-run-id>/
```

Before scoring, a successful run directory contains exactly:

```text
dispatch.json
raw-response.json
proposals.json
provenance.json
proposal-freeze-receipt.json
```

All files are mode `0444`; directories are `0775`. Parsing may use a unique
temporary file outside the official evaluation root, but a successful freeze
must leave no temporary or staging path under the official root. The receipt
binds all four files, their sizes/modes, the exact request ordinal `1`, the
materialization chronology, prompt/public hashes, requested/response models,
code/test hashes, and the sequence
`dispatch -> raw_response -> proposals -> provenance`.

After scoring, the same directory adds exactly:

```text
score.json
error-analysis.json
report.md
qualification.json
```

The evaluation root then adds `overall-score.json`, `overall-report.md`, and
`qualification-chronology.json`. These files bind both proposal-freeze
receipts, both scores and qualifications, the preregistration/materialization
chain, scorer code, protected state, and the final authorization boundary.

## Proposer Phase

1. Validate the full pre-request gate before creating either dispatch.
2. Freeze both L1 and L2 dispatch files. Each dispatch allowlist contains only
   its exact frozen prompt and public payload; authority/gold are false and
   absent from the request body.
3. Run L1 and L2 as independent one-shot operations. Each layer makes at most
   one HTTP request. No transport retry, invalid-JSON retry, semantic retry,
   fallback model, or replacement run is allowed in this qualification, even
   though the older preregistration schema described how a transport retry
   would have to be recorded.
4. Persist the raw response bytes immediately as `0444`, parse only that frozen
   response, validate full public case coverage and references, then freeze
   proposals and provenance.
5. Reopen every file and freeze the proposal receipt. No scorer entry point is
   callable until both layer receipts validate.

The API key and base URL are runtime-only inputs and are never serialized,
logged, hashed into artifacts, or included in reports. A request failure
preserves all already-created evidence and closes that layer without another
request. The other layer may still execute once if the global materialization,
Git, and protected-state bindings remain valid; this produces a complete audit
of both independent opportunities without retrying the failed layer.

## Scoring And Qualification Phase

Scoring starts in a separate process after model transport has ended. Its
public entry point accepts no base URL, credential, model alias, prompt path,
or opener. It first validates both proposal-freeze receipts and proves the
official authority/gold files were not among proposer allowed files.

The existing deterministic scorers then read public, authority, gold, the
frozen proposals/provenance, and the unchanged guard bundle. Exact official
manifest bindings include source/public/authority/gold, not a three-file
compatibility subset. L2 qualification uses the preregistered fresh-v3
thresholds rather than the legacy `L2_DEV_THRESHOLDS` default.

L1 raw quality requires all 14 metrics to equal `1.0`:

- proposal coverage, schema validity, raw decision accuracy, raw abstention
  F1, and exact evidence;
- kind, predicate/operator, modality/polarity, role/local entity, time,
  condition/scope, derivation/speaker, lifecycle, and operation provenance.

L2 raw quality requires all 12 metrics to equal `1.0`:

- proposal coverage, schema validity, raw decision accuracy, raw abstention
  F1, exact evidence, support ID, kind, structured claim, abstraction,
  closure, source coverage, and summary.

For each layer, raw critical false emission, gate intervention, and
deterministic critical false materialization must each equal `0`.
`raw_proposer_quality_ready` and `deterministic_gate_safety_ready` are recorded
separately; `layer_ready` is true only when both are true. The overall result is
`qualified` only when both layers are ready. Any proposer-phase failure,
invalid freeze, scorer failure, or threshold failure yields `not_qualified` or
`incomplete_not_qualified` with the failure class preserved. No gate demotion
may conceal a raw error.

## Failure And Recovery Policy

- Pre-request drift or unexpected existing run/result paths: make no request
  and stop.
- Transport failure before raw bytes exist: preserve dispatch and a frozen
  failure receipt; do not retry.
- Invalid or semantically invalid raw response: preserve raw bytes and failure
  receipt; do not retry or edit the response/proposal.
- Interruption after raw response: deterministic recovery may inspect and
  finish freezing from the same immutable raw bytes only under an explicit
  recovery audit that proves model request count remains one. It may never
  issue another request.
- Scorer implementation or compatibility failure: preserve all proposer
  evidence and stop. Do not change scorer behavior after inspecting hidden
  results without a separate user-approved supersession design based on
  non-hidden tests.
- Raw or deterministic qualification failure: freeze the failure and stop.
  Repair is allowed only on a new dev/diagnostic set followed by a separately
  preregistered fresh hidden version.

## Verification

Before either request, run focused controller/qualification/scorer tests,
phase-aware v3 tests, tracked typed/runtime/natural/knowledge gates, Ruff,
compileall, tabnanny, diff, credential, Git/index, official-root replay,
candidate queue/live guard, parallel hash, path absence, and zero-write checks.
An independent review must report zero Critical and zero Important findings.

After each proposal freeze, reopen and replay every proposer artifact before
allowing the next phase. After qualification, validate exact file sets,
canonical bytes, hashes, modes, request counts, raw/proposal replay,
score/qualification replay, thresholds, guard/protected state, credential zero,
and authorization boundaries. Run the same focused/static/protected checks
again and update only extraction fact sources plus this plan's execution record.

## Authorization Boundary

Approval of this design and its implementation plan authorizes only the two
one-shot proposer requests, immutable proposal freeze, deterministic scoring,
and final fresh-v3 qualification described here. It does not authorize retries,
hidden-driven tuning, manual proposal edits, identity adjudication
materialization, pipeline integration, automatic L1/L2/revision/source-
revision/closure/identity/membership/snapshot/aggregate writes, cross-session
aggregation, benchmark expansion, storage selection, or external-system reruns.

The task stops immediately after the qualification conclusion is frozen and
reported, regardless of pass or fail. `LONGMEMEVAL-6d550036` remains
`structured_l2_identity_unresolved`, and embedding remains non-authoritative.

## Self-Review

- Placeholder scan: no deferred file, count, metric, retry policy, phase gate,
  or authorization decision remains.
- Consistency: exact IDs, hashes, counts, prompt/public bindings, thresholds,
  modes, run order, and stop conditions match the frozen preregistration and
  materialization facts.
- Scope: the selected approach adds only a v3 controller/qualifier and narrow
  backward-compatible scorer parameters; it does not touch query, ontology,
  L1 admission/linking, runtime packages, or authoritative write paths.
