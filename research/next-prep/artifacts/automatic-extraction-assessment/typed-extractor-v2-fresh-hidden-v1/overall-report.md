# Typed Extractor V2 Fresh Hidden Evaluation Summary

## Decision

The fresh-hidden v1 evaluation is closed. Both layers failed raw proposer
qualification and passed deterministic gate safety. The gate result does not
override the raw failures, so neither layer is qualified for pipeline
integration or authoritative materialization.

| Layer | Cases | Raw quality | Gate safety | Raw decision accuracy | Raw abstention F1 | Raw critical false emissions | Gate interventions | Critical materializations |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: |
| L1 | 24 | fail | pass | 0.7916666666666666 | 0.5714285714285715 | 3 | 4 | 0 |
| L2 | 8 | fail | pass | 0.625 | 0.0 | 3 | 6 | 0 |

## Protocol

- Preregistration SHA-256: `9ec35f71c86c0e2c0257438d01445d9f0a490eee57a0d582ccb01024ffc0921c`.
- Chronology receipt SHA-256: `2f2c38e475a8b25a3a553333ea4733f6428f505a5adb8e6c95bdfd0964fbc699`.
- Requested model: `deepseek-chat`; both API responses reported `deepseek-v4-flash`.
- Each proposer was a one-shot, no-history, public-only request. Raw response,
  proposals, and provenance froze before authority/gold scoring.
- L1 selected 24 cases by preregistered public-structure strata. L2 used all
  eight unused bridge-v3 cross-turn records. No hidden case was replaced.

## Raw Failure Classification

L1 produced three false emissions, including both control questions and one
unauthorized semantic case, and two false abstentions on valid emissions. It
also had condition/scope, time, role/local-entity, evidence, lifecycle,
predicate/operator, modality/polarity, derivation/speaker, and operation
provenance errors.

L2 emitted all three cases that required abstention. Among valid emissions,
three used the wrong abstraction method, two had structured-claim errors, and
one had a kind error. Evidence, support IDs, source coverage, closure, and
summary accuracy remained `1.0`; these correct fields do not offset the failed
decision and abstraction gates.

## Artifact Integrity

| Layer | Raw response | Proposals | Provenance | Score | Report | Error analysis |
| --- | --- | --- | --- | --- | --- | --- |
| L1 | `c63e633109c9ffd334b7300ed8892c2b2a9122dc8417d87d57b90366937a1632` | `ef00272deea2b2380940a69669d6a77c69bcfd5a93011025dc688371feea967e` | `d3699342b725beff86a2d45c5ef2c064afe7d202246192a03d35d830173324b9` | `84940b212079127f6b16f90b93a317fda86e19822d173624266f40254611ec16` | `9cd92d83b0629159eb71ac394534a726f6fe52cce5980c3d23ebca687fa42e41` | `040b1c88209f71169553fedd3bd26e09ab604b4fdb7022de7417023ec643cfc6` |
| L2 | `a32f5ff3f64a6caa14ca13f00eaf884e16abf4cab068457896d442784df7510e` | `1dea9db3a7489ba6d27247da1c8dfe87376890985345aafb7987af47535991d7` | `a007cf7b8d2409653517bfe6bddfa3e098a7486bbe83ae22883989243a606cc8` | `12fc340bafc7e9645b835289237ef709384eedefa5a7818fb5c7132e744de5d8` | `a924a8f4579f04d5f5d4d7cf4181736f71ae96ac93885f6b0240454424d6f779` | `35f8467792dfef038bb8875cf4ae23c5a51234efd7bb0167abf1a9ae35cd178f` |

Bridge-v3 and both score/report/error-analysis triples replay byte-identically.
All formal evaluation artifacts are read-only.

The per-layer reports retain generic `Dev Qualification` headings because the
preregistered scorer/renderers were reused byte-for-byte. Their score status
means that scoring completed, not that raw hidden qualification passed. Their
scorer-local `fresh_hidden_created=false` claim means the scoring call did not
create a hidden slice; the frozen manifests and chronology receipt are the
authority that this run evaluated fresh hidden data.

## Boundaries And Next Step

All L1, L2, revision, closure, identity, membership, snapshot, and aggregate
automatic write counts remain zero. The candidate-generation v3 queue remains
non-authoritative at SHA-256
`518ead9de8627a9a4384df8cdd9b8728a21fcf797f6b0f3d208dfcb28ac41c0f`;
the four user-confirmed manual identity adjudications remain unmaterialized.
`LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`. The API
credential was process-only and the repository secret-token scan found no
matching path.

Repairs may use only a new dev/diagnostic set. L1 repair must target false
emission, false abstention, evidence, condition/scope, time, role, and lifecycle
errors. L2 repair must target abstention, abstraction method, structured claim,
and kind errors. A passing dev gate must be followed by a separately frozen and
preregistered fresh-hidden v2 evaluation; v1 is not retried or modified.
