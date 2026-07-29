# Automatic L1/L2 Extraction Bridge Assessment Design

## Status

Approved for autonomous execution under the user's standing instruction to
continue without per-step confirmation.

## Goal

Measure how much of the existing validated two-pass model extraction can be
mapped losslessly into the representation-neutral authoritative L1/L2 contract,
without rerunning a model, changing the extraction skeleton, or publishing any
authoritative memory writes.

This wave answers one narrow question: what is already structurally usable,
what is missing, and what exact typed fields the next dev-only extractor must
produce?

## Inputs

The assessment consumes only current-workspace artifacts:

- `data/gold-candidates/KE-test.json`
- `knowledge-extraction/turn-pass/validated/manifest.json`
- `knowledge-extraction/dialogue-pass/validated/manifest.json`
- `knowledge-extraction/final-knowledge.json`
- `knowledge-extraction/run.json`
- `knowledge-extraction/source-segments.json`

The validated manifests are replayed through
`knowledge_pipeline.projector.project_validated_manifests`. The recomputed
canonical semantic payload (`schema_version`, `active_ids`, `counts`, and
`records`) must match `final-knowledge.json` exactly before any compatibility
measurement is allowed. Provenance manifest/source-segment hashes must also
match. Absolute provenance path strings are excluded from equality because the
frozen file records the pre-migration Windows paths while replay runs on H100.

No KEOL output, old Fusion Memory artifact, external memory-system result,
identity authority/gold file, or embedding result is an input.

## Approaches Considered

### Direct heuristic materialization

Convert all 390 active knowledge records into authoritative L1/L2 units using
rules inferred from free-text subject, predicate, object, and qualifiers. This
would maximize apparent coverage but silently invent memory kinds, predicate
senses, canonical operators, typed roles, entity identities, and typed time.
It is rejected.

### Loss-aware read-only bridge assessment

Replay the frozen model extraction, verify evidence and provenance, classify
each record by candidate level, and report exact, normalized, unsupported, and
missing mappings. Incomplete records remain non-authoritative candidates. This
is the selected approach.

### Immediate typed-extractor rerun

Change the prompt and rerun all turns against the authoritative schema. This is
the next dev-only wave after the present assessment produces an evidence-based
gap taxonomy. Doing it first would mix prompt, semantic, and adapter failures.

## Architecture

Add an isolated benchmark module:

`tools/natural_memory_benchmark/extraction_bridge_assessment.py`

It has four responsibilities:

1. Replay and bind the existing extraction ledger.
2. Build one immutable compatibility envelope per projected knowledge record.
3. Measure raw extraction structure separately from deterministic bridge safety.
4. Write an immutable ledger, assessment JSON, and Markdown report.

It does not modify `knowledge_pipeline`, `semantic_ir.py`,
`authoritative_memory.py`, `turn_bundle.py`, identity resolution, question
processing, symbolic retrieval, or guarded embedding fallback.

## Candidate Classification

Every projected record is classified from evidence and projection provenance,
not from a semantic guess:

- `l1_single_turn_candidate`: all evidence belongs to exactly one source turn.
- `l2_cross_turn_candidate`: evidence spans multiple turns or the record was
  introduced by a dialogue-level `add` operation.
- `blocked_candidate`: provenance cannot support either classification.

Classification is not materialization authorization. A record can be an L1 or
L2 candidate while still having blocking semantic gaps.

Corrected and superseded records remain in the ledger. Projection lifecycle is
mapped without deleting history:

- `active` -> `active`
- `active_conflict` -> `conflicted`
- `corrected` -> `superseded`
- `superseded` -> `superseded`

The adapter must not collapse equivalence groups or infer identity from matching
surface strings.

## Mapping Contract

The bridge records mapping status for each required capability.

### Exact mappings

- evidence quote, occurrence, Unicode offsets, turn, and message side;
- `source_status`;
- polarity;
- extraction confidence;
- source candidate and turn provenance;
- projection lifecycle and replacement/conflict links where explicitly present.

### Normalized but non-authoritative mappings

The following modality translations may be reported as normalized, but they do
not make a record authoritative:

- `asserted` or `observed` -> `actual`
- `planned` -> `planned`
- `requested` -> `requested`
- `hypothetical` -> `hypothetical`
- `advised` -> `recommended`

`possible`, `preferred`, `questioned`, `committed`, and `claimed_completed`
remain unsupported until the typed extractor or contract explicitly represents
their semantics. Source status must never be used to erase this gap.

### Blocking gaps for L1

- missing typed memory `kind`;
- missing predicate sense;
- missing canonical operator;
- free-text subject/object without typed role bindings and local entity IDs;
- free-text temporal qualifiers without typed time bindings;
- evidence or declared source outside the single-turn boundary;
- unresolved lifecycle or replacement reference.

### Additional blocking gaps for L2

- missing explicit supporting L1 unit IDs;
- missing structured claim;
- missing abstraction method;
- missing closure pattern/specification;
- missing source-turn and source-session closure;
- unresolved identity required by an aggregate claim.

The bridge does not use keywords, WordNet, schema.org, or embeddings to fill any
blocking semantic field. Those resources may later propose vocabulary
candidates, but they are not factual or identity authority.

## Output Contract

Formal outputs live under:

`artifacts/automatic-extraction-assessment/bridge-v3/`

- `compatibility-ledger.json`: one envelope per projected record, including
  input hashes, classification, exact mappings, normalized mappings, gaps, and
  all automatic-write claims set to `false`.
- `assessment.json`: aggregate metrics, guard fingerprints, readiness, and the
  next typed-extractor requirements.
- `report.md`: human-readable raw quality, bridge safety, limitations, and gap
  distribution.

All outputs are canonical, deterministically replayable, frozen immediately as
mode `0444`, and rejected if a destination already exists.

## Metrics

Raw automatic-extraction structure and deterministic bridge safety are reported
separately.

### Raw extraction structure

- projected record count and active record count;
- turn-stage and dialogue-stage counts;
- exact evidence binding rate;
- source-status admissibility rate;
- statement/SPO/qualifier completeness rate;
- single-turn versus cross-turn evidence distribution;
- modality distribution and unsupported-modality count;
- correction, supersession, conflict, and dialogue-add counts.
- exact confirm/add operation provenance and same-candidate ownership.

These are structural metrics over existing model output. They are not gold
semantic accuracy and must not be described as such.

### Deterministic bridge safety

- L1 candidate count and L2 candidate count;
- lossless authoritative-ready L1/L2 counts;
- blocked candidate count and gap distribution;
- automatic L1/L2/revision/closure/identity/membership write counts;
- before/after authoritative guard fingerprint and protected counts;
- replay and read-only status.

`automatic_extraction_integration_ready` is true only if at least one candidate
is losslessly materializable and every safety invariant passes. The expected
initial result may legitimately be false.

## Typed Extractor V2 Requirements

The assessment emits a machine-readable requirement list for the next dev-only
extractor:

- explicit `level` and typed memory `kind`;
- predicate `surface`, `sense`, and `canonical_operator`;
- typed role bindings with candidate-scoped local entity IDs;
- typed modality, polarity, and time bindings;
- exact evidence references only;
- explicit lifecycle and correction/supersession/conflict links;
- exact confirm/add operation provenance with same-candidate ownership;
- for L2, supporting L1 candidate IDs, structured claims, abstraction method,
  closure pattern, and source turn/session coverage;
- explicit abstention or no-memory result when required fields are unresolved.

The model still produces candidates. Deterministic code owns stable IDs,
revision construction, evidence closure validation, and all authoritative write
authorization.

## Failure Handling

The assessment fails closed on:

- manifest or validated-file hash drift;
- final projection mismatch;
- duplicate knowledge/evidence IDs;
- evidence quote or offset mismatch;
- cross-candidate references;
- unknown projection lifecycle or operation reference;
- writable or overwritten formal output;
- mutation of the authoritative guard bundle.

Partial outputs are frozen immediately before the error is propagated.

## Review Closure

`bridge-v1` is retained as the initial read-only diagnostic but omitted typed
condition/scope, non-explicit derivation provenance, evidence speaker binding,
and several strict replay checks. `bridge-v2` added those requirements and
checks, but independent review found that `confirmed_by` and `added_by`
operation IDs were neither ownership-validated nor preserved in envelopes.
Because `added_by` affects L1/L2 classification, this was an Important
fail-closed gap.

`bridge-v3` is the formal closure. It reconstructs operation ID -> candidate
ownership from hash-bound frozen dialogue validated files, rejects unknown or
cross-candidate confirm/add references, and preserves both operation lists in
each envelope. It also directly tests evidence quote, occurrence, and offset
mismatch paths. v1/v2 remain immutable audit artifacts and are not the complete
typed-extractor input contract.

## Tests

Focused tests cover:

- exact replay of the validated extraction manifests;
- final-view semantic equivalence plus exact provenance-hash binding;
- L1/L2 candidate classification;
- exact versus normalized versus unsupported modality mapping;
- blocking gap derivation;
- correction/supersession/conflict preservation;
- tamper, duplicate, cross-turn, and cross-candidate rejection;
- zero authoritative mutation and false write claims;
- deterministic immutable output and CLI behavior.

Regression verification includes all `knowledge_pipeline` tests, all
`tests/natural_memory_benchmark`, `compileall`, extraction manifest replay,
natural slice/ledger validators, and protected identity/authoritative hashes.

## Boundaries

- This wave does not rerun a model and does not claim new model quality.
- It does not publish authoritative L1 or L2 units.
- It does not compile questions or execute new benchmark queries.
- It does not implement cross-session aggregation or select a storage profile.
- It does not change the existing two-pass extraction skeleton.
- `LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.
- Embeddings cannot supply facts, identity, membership, typed roles, or closure.
- External memory systems and old Fusion Memory remain out of scope.

## Acceptance Criteria

1. The existing extraction ledger replays exactly and binds all input hashes.
2. Every projected record receives one deterministic compatibility envelope.
3. Raw extraction structure and bridge safety remain separately visible.
4. Missing typed semantics are blocked rather than heuristically invented.
5. Automatic authoritative writes remain zero and the guard is unchanged.
6. The output provides an exact typed-extractor v2 requirement list.
7. Formal outputs replay byte-identically and remain mode `0444`.
