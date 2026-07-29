# Typed Extractor Fresh Hidden Evaluation Design

## Status

Approved by standing user direction on 2026-07-28: execute the established
design without intermediate confirmation. This document freezes the design
before any fresh-hidden source, authority, gold, or public case is authored.

## Goal

Evaluate the frozen L1 prompt V6 and final L2 prompt once on new hidden-only
cases that were not used for dev repair. Preserve the existing public-only
proposer, immutable proposal freeze, independent scoring, raw/gated separation,
and zero-authoritative-write boundaries.

## Alternatives Considered

1. Hand-pick a small hidden set after inspecting all remaining candidates.
   This gives balanced examples but creates selection bias and weakens the
   meaning of fresh hidden.
2. Select every remaining candidate. This is clean for L2, whose pool is only
   eight unused cross-turn candidates, but unnecessarily large and highly
   redundant for the 390 unused L1 candidates.
3. Use deterministic predeclared selection. This is selected. L2 consumes all
   unused cross-turn candidates; L1 selects fixed public-structure strata with
   a namespace-bound hash order. Semantic labels are authored only after the
   preregistration is frozen.

## Frozen Inputs

- L1 source carrier: bridge-v3 compatibility ledger SHA-256
  `2ed9e6fdeaca81964fff542287adfc2980145b978b7ef9ed6dfc5f914ebca7c0`.
- L1 prompt V6 SHA-256
  `a4d03b0e3717be47a3cd32358f6ca881d4be55bac804bc343999b6b22b835586`.
- L2 prompt SHA-256
  `55fddf350d4a2c821000436aa4ce4c614da589ffe053ea5ab4c1bb7e774e60c7`.
- L1 dev public/source and L2 dev public/source hashes are frozen as exclusion
  sets. No hidden source knowledge ID, evidence combination, case ID, or public
  candidate ref may overlap them.
- The proposer request model is `deepseek-chat`. The API response model is
  recorded separately and is not assumed in advance.

## Selection

### L1

Select 24 single-turn records not present in the L1 dev source. Selection uses
namespace `typed-extractor-l1-fresh-hidden-v1:2026-07-28` and ascending SHA-256
of `namespace || knowledge_id`. Fill these public-structure strata without
semantic gold inspection:

- 8 ordinary explicit records, covering all available source statuses;
- 4 non-explicit derivation records;
- 3 condition-bearing records;
- 3 scope-bearing records;
- 2 non-active lifecycle records;
- 2 time-bearing records;
- 2 negative/control turns selected by deterministic question/control syntax.

A record may satisfy multiple coverage properties but occupies only one stratum
in the priority order above. If a stratum cannot be filled, preparation aborts;
the implementation may not substitute a manually preferred case.

### L2

Use every bridge-v3 cross-turn record not present in the six-case L2 dev source.
The expected count is eight. Namespace is
`typed-extractor-l2-fresh-hidden-v1:2026-07-28`. Ordering is the ascending
SHA-256 of `namespace || knowledge_id`; no semantic filtering is allowed.

## Separation And Chronology

The preregistration root is
`artifacts/automatic-extraction-assessment/typed-extractor-v2-fresh-hidden-prereg-v1/`.
The later evaluation root is
`artifacts/automatic-extraction-assessment/typed-extractor-v2-fresh-hidden-v1/`.

At preregistration freeze, the evaluation root and all hidden source/public/
authority/gold files must be absent. The preregistration records their expected
paths and exact frozen input/code hashes. Files are mode `0444`. This is a
filesystem hash/mtime audit, not a trusted timestamp authority.

After authoring, public contains only opaque case/candidate/support/turn/session
references and proposer-visible vocabularies. Authority and gold are separate
read-only files. Proposer dispatch sees only the matching frozen prompt and
public file. Proposals and provenance freeze before scoring reads authority or
gold.

## Metrics And Decisions

L1 uses the already implemented dev thresholds:

- proposal coverage and schema-valid rate `1.0`;
- raw decision accuracy at least `0.90`;
- raw abstention F1 at least `0.80`;
- exact evidence rate `1.0`;
- every safety field-family accuracy at least `0.85`;
- raw critical false emission count `0`;
- deterministic critical false materialization count `0`.

L2 uses the frozen `L2_DEV_THRESHOLDS` values, including exact evidence,
support ID, and source coverage `1.0`, raw decision accuracy at least `0.90`,
raw abstention F1 at least `0.80`, safety field accuracy at least `0.85`, and
zero raw critical false emission or deterministic critical materialization.

Raw proposer quality and deterministic gate safety remain separate. A layer
passes only when both are ready. Gate demotions and raw semantic errors are
reported separately. No combined score may conceal a raw failure.

## Failure Policy

There is one formal proposer run per layer. Transport or invalid-JSON failures
may be retried only as a new immutable run with the unchanged prompt and public
input; semantic failure is not retried. Any semantic failure is classified on
the hidden result, the evaluation is closed, and repairs move to a new dev or
diagnostic set followed by a separately preregistered fresh-v2 evaluation.

## Boundaries

- No L1, L2, identity, membership, closure, revision, snapshot, aggregate, or
  source-revision write is authorized.
- The user-confirmed identity adjudications remain a separate unmaterialized
  manual-review fact; this evaluation neither reads nor writes them.
- Embeddings cannot authorize facts, identity, roles, membership, or closure.
- External memory systems are not rerun, and old Fusion Memory is not accessed.
- `LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.
- This evaluation does not authorize pipeline integration or choose a storage
  profile.

## Verification

The preregistration validator rehashes all inputs and code, validates fixed
namespaces/counts/thresholds, checks read-only mode, confirms hidden artifacts
are absent at freeze, and rejects unknown fields. Later preparation tests require
deterministic replay, dev/hidden non-overlap, public/gold separation, exact
chronology receipt binding, and byte-identical output.

## Final Result

The formal evaluation is closed. Both public-only one-shot requests used the
requested `deepseek-chat` alias and received model identifier
`deepseek-v4-flash`. L1 evaluated 24 cases and L2 evaluated eight cases.

L1 raw proposer quality failed while deterministic gate safety passed. Raw
decision accuracy was `0.7916666666666666`, abstention F1 was
`0.5714285714285715`, exact evidence was `0.8947368421052632`, and there were
three critical false emissions. The gate made four interventions and produced
zero critical materializations.

L2 raw proposer quality also failed while deterministic gate safety passed.
Raw decision accuracy was `0.625`, abstention F1 was `0.0`, and there were three
critical false emissions. Exact evidence, support ID, closure, source coverage,
and summary accuracy were `1.0`, but abstraction and structured-claim accuracy
were only `0.4` and `0.6`. The gate made six interventions and produced zero
critical materializations.

The overall decision is therefore fail for both layers; no gated safety result
may be presented as proposer qualification. The immutable summary is
`artifacts/automatic-extraction-assessment/typed-extractor-v2-fresh-hidden-v1/overall-report.md`.
Any repair must use new dev/diagnostic cases and then a separately preregistered
fresh-hidden v2 evaluation.

The reused per-layer renderers retain generic `Dev Qualification` headings and
scorer-local `fresh_hidden_created=false` claims. These indicate the bound
renderer/scorer behavior, not the dataset split; the frozen manifests and
chronology receipt establish that this was the fresh-hidden v1 evaluation.
