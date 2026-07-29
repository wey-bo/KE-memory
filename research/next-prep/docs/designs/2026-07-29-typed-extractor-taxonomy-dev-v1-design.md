# Typed Extractor Taxonomy-Driven Diagnostic V1 Design

## Status

Design approved by the standing workspace instruction to continue according to
the established plan. This is a diagnostic-only wave after the closed
`typed-extractor-v2-fresh-hidden-v2` evaluation. It is not a hidden evaluation,
not a natural benchmark slice, and not an authorization to write memory state.

## Goal

Create fresh, independently authored L1/L2 dev cases that cover the error
taxonomy observed in fresh-v2 without reading, copying, or reverse-engineering
fresh-v2 hidden case text. Establish an unchanged-prompt baseline, then allow
prompt repair only from the new diagnostic results.

## Non-Negotiable Boundaries

- Read only aggregate fresh-v2 error categories and metric failures; do not read
  fresh-v2 `source-cases`, `gold`, `authority`, raw proposals, or error-analysis
  case text while authoring the new source.
- Keep fresh-v2, its preregistration, receipts, manifests, proposals, scores,
  qualification files, and candidate queue immutable.
- Use new source text, new private IDs, new opaque namespace, and new evidence
  quotes. Prior-root overlap validation must reject repeated private IDs,
  public IDs, evidence IDs, or exact evidence text.
- Proposer input is frozen prompt plus public JSON only. Proposals and
  provenance freeze before any authority/gold read. Scoring is a separate
  process boundary.
- Keep raw proposer quality and deterministic gate safety separate. The strict
  qualification requires every configured metric to equal `1.0`, raw critical
  false emissions to equal `0`, gate interventions to equal `0`, deterministic
  critical materialization to equal `0`, unchanged guard state, and zero writes.
- No L1/L2/revision/source-revision/closure/identity/membership/snapshot/
  aggregate write, pipeline integration, external memory rerun, or embedding
  authority is permitted. `LONGMEMEVAL-6d550036` remains
  `structured_l2_identity_unresolved`.

## Dataset Composition

The two layers have independent roots and manifests. Both sources carry
`provenance="diagnostic_authored"` and a schema version ending in `v1`.

### L1: 20 cases

The new source contains the following primary families; each targeted fresh-v2
failure family has at least four scored opportunities.

| Primary family | Count | Purpose |
| --- | ---: | --- |
| `false_emission` | 3 | question-only, instruction-only, unsupported hypothetical must not emit |
| `false_abstention` | 3 | explicit user state, requested task, and tool-observed event must emit |
| `role_or_local_entity` | 4 | participant, beneficiary, recipient, and agent-vs-user role bindings |
| `time` | 3 | explicit event date, explicit validity interval, unresolved deictic time |
| `condition_or_scope` | 3 | approver condition, project scope, and conditional preference |
| `evidence` | 2 | exact span and distractor exclusion |
| `derivation_or_speaker` | 1 | user report versus assistant suggestion |
| `lifecycle` | 1 | correction/supersession with operation provenance |
| **Total** | **20** | |

Each case has a fresh two-message turn, a public untyped candidate, private
authority/gold expectations, and closed exact evidence spans. Secondary labels
provide at least two opportunities for predicate/operator, kind, modality,
operation provenance, and lifecycle fields even when they are not primary.

### L2: 12 cases

The source has four abstention controls and eight emissions. The eight emissions
cover each abstraction/closure contract at least twice, with dedicated new
cases for the two fresh-v2 failure families.

| Primary family | Count | Expected behavior |
| --- | ---: | --- |
| `unsupported_modality_control` | 1 | abstain |
| `unresolved_selection_control` | 1 | abstain |
| `incompatible_support_control` | 1 | abstain |
| `incomplete_closure_control` | 1 | abstain |
| `coreference_case` | 2 | document/device reference with exact claim sense |
| `task_composition_case` | 2 | task composition with complete support union |
| `lifecycle_case` | 2 | commitment and supersession |
| `state_summary_case` | 1 | persistent state must use `state_summary` |
| `preference_aggregation_case` | 1 | compatible preference supports must aggregate |
| **Total** | **12** | |

Every emitted candidate has at least two typed L1 supports, exact structured
claim literals, complete source/session/evidence closure, and a catalog-bound
operator/sense pair. Abstention cases have explicit unresolved fields and no
typed candidate.

## Architecture

Add one focused module,
`tools/natural_memory_benchmark/typed_extractor_taxonomy_dev.py`, containing
strict private source models, deterministic opaque-ID projection, source
validation, prior-overlap checks, and immutable prepare/validate functions. It
reuses the existing L1/L2 public, authority, gold, manifest, candidate, and
evidence models; it does not modify shared scorer/model-run modules.

The module accepts explicit `layer` and source paths and emits the existing
file names (`diagnostic-source-*.json`, `public-*.json`, `authority-*.json`,
`gold-*.json`, `manifest-*.json`) below new roots:

- `artifacts/automatic-extraction-assessment/typed-extractor-taxonomy-l1-dev-v1/`
- `artifacts/automatic-extraction-assessment/typed-extractor-taxonomy-l2-dev-v1/`

The source authoring data itself is kept in the root under a new file name and
is immutable after preparation. Public projection removes private IDs,
families, expected decisions, and authority labels. Manifest claim boundaries
declare diagnostic-only status, all automatic writes zero, no fresh hidden
created, and unresolved LongMemEval identity.

## Evaluation Flow

1. Validate source schema, distribution, exact spans, public/private separation,
   and overlap against all prior diagnostic/fresh roots.
2. Prepare and freeze the two diagnostic roots; validate deterministic replay
   before any model request.
3. Copy the selected current L1/L2 prompts into the diagnostic roots and run
   one unchanged-prompt, no-history, public-only proposer per layer.
4. Freeze dispatch, raw response, proposals, and provenance; only then run the
   existing scorer against authority/gold via read-only compatibility views if
   the legacy scorer requires one.
5. Run strict diagnostic qualification. Report raw metrics, gate metrics,
   intervention taxonomy, and all zero-write boundaries separately.
6. If either layer fails, author a prompt-repair revision using only this new
   diagnostic source and baseline result. Never use fresh-v2 hidden case text.
7. Repeat only on this diagnostic source until both strict qualifications pass;
   then freeze a separate fresh-hidden preregistration before any hidden data or
   model request.

## Failure Handling

Any malformed source, overlap, mutable artifact, proposal/provenance mismatch,
authority read before freeze, score/manifest mismatch, non-zero write, guard
drift, or unexpected metric key fails closed. A proposer failure leaves its
immutable raw/provenance record and is classified; it is not repaired in place.

## Verification

The focused tests must cover strict model rejection, exact distributions,
opaque-ID stability, evidence offsets, support/closure, prior overlap,
public/private leakage, byte-identical replay, read-only modes, and zero-write
boundaries. Before any fresh preregistration, run typed extractor tests,
knowledge pipeline tests, the complete natural-memory suite (excluding only
the documented pre-materialization root-absence test), `compileall`,
`tabnanny`, credential scanning, and a frozen-artifact hash audit.

