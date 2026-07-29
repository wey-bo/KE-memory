# Typed Extractor V2 Dev Qualification Design

## Status

L1 and L2 dev qualification passed on 2026-07-28. This remains a
dev/diagnostic-only result: it permits preregistration of a fresh hidden
evaluation, but does not itself authorize hidden claims, pipeline integration,
or authoritative writes.

## Goal

Qualify a real model as a producer of typed, non-authoritative L1 and L2
candidates before any fresh hidden evaluation or pipeline integration. The wave
must address the exact gaps emitted by `bridge-v3` while preserving the current
two-pass extraction skeleton and every authoritative write boundary.

## Approaches Considered

### Deterministic heuristic conversion

Map free-text subject, predicate, object, qualifiers, and lifecycle fields into
the authoritative schema with rules. This is rejected because it would invent
memory kind, predicate sense, canonical operator, typed roles, local entity
identity, typed time, L2 support, and closure.

### Immediate end-to-end typed re-extraction

Replace the current turn/dialogue prompts and rerun all 43 turns. This is
deferred because extraction recall, record segmentation, typing, and closure
errors would be mixed in one score, making dev repair ambiguous.

### Sequential typed enrichment over frozen candidates

Use the frozen extraction records and their exact source evidence as public
candidate inputs. First qualify L1 typing; after L1 passes, qualify L2
abstraction against frozen typed L1 support packs. This is the selected
approach. It isolates the bridge gaps without claiming the current record set is
semantically complete or correct.

## Scope

The dev qualification has two dependent stages:

1. **L1 dev gate:** 12 diagnostic cases selected from frozen single-turn
   candidates. The slice covers all five L1 kinds, user/agent/tool source
   statuses, exact and unresolved time, active/corrected/superseded lifecycle,
   supported modality mappings, unsupported modality abstention, and explicit
   no-memory behavior.
2. **L2 dev gate:** 6 diagnostic cases selected from frozen cross-turn
   candidates. Four require typed L2 output and two require abstention because
   support, modality, identity, or closure is insufficient. L2 inputs include a
   frozen typed L1 support pack and cannot run until the L1 dev gate passes.

The exact case list, authority, and gold are frozen before model dispatch. The
same dev cases may be rerun during repair, but no fresh hidden slice is authored
until both dev gates pass.

## Input Separation

Formal dev artifacts live under:

`artifacts/automatic-extraction-assessment/typed-extractor-v2-dev/`

Each stage has strict layers:

- `source-cases-<level>.json`: source selection, expected evidence, and private
  authoring metadata;
- `public-<level>.json`: only opaque case IDs, frozen source text, the untyped
  candidate, exact evidence references, allowed contract vocabulary, and, for
  L2, typed L1 support candidates;
- `authority-<level>.json`: admissible evidence, lifecycle references, source
  turn/session coverage, and safety restrictions;
- `gold-<level>.json`: expected decision and typed semantic fields;
- `manifest-<level>.json`: hashes, case counts, distribution, thresholds, and
  claim boundaries;
- `proposer-prompt-<level>.md`: model instructions frozen before dispatch.

The proposer may read only the public file and matching prompt. It must not read
authority, gold, bridge assessment metrics, prior proposals, scorer outputs, or
historical error analysis. Isolation is a declarative fresh-agent file-access
contract and must be reported as such, not as OS-enforced isolation.

## Proposal Contract

Every case returns exactly one decision:

- `emit_l1`;
- `emit_l2`;
- `abstain`;
- `no_memory`.

An emitted L1 candidate contains:

- typed `kind`;
- predicate `surface`, `sense`, and `canonical_operator`;
- candidate-scoped local entities with contiguous opaque local IDs;
- typed role bindings referencing only those local IDs;
- typed modality and polarity;
- `event_time` and `valid_time`, with unresolved values left null;
- exact evidence IDs;
- exact evidence speaker bindings;
- typed condition and scope bindings;
- typed derivation/inference provenance;
- explicit lifecycle plus correction, supersession, or conflict references when
  the public input supplies them.
- exact confirm/add operation provenance when the public input supplies it.

An emitted L2 candidate contains:

- typed L2 `kind` and summary;
- exact supporting L1 candidate IDs;
- one or more structured claims using the same predicate/role contract;
- abstraction method;
- closure pattern and required support IDs;
- complete source turn and source session coverage;
- exact evidence IDs and lifecycle.

The model does not create final unit IDs, source revision IDs, global entity
IDs, identity decisions, closure IDs, closure evaluation IDs, revision numbers,
or transaction time. Deterministic code owns those fields and all write
authorization.

## Freeze and Scoring Order

For each stage:

1. Freeze source, public, authority, gold, manifest, prompt, and dispatch
   receipt.
2. Start a zero-history isolated proposer with only the frozen public file and
   prompt.
3. Validate proposal coverage and structure, then freeze proposals and
   provenance as mode `0444`.
4. Only after proposal freeze may the independent scorer read authority and
   gold.
5. Freeze score, report, and error taxonomy as mode `0444`.

Scoring never repairs a proposal. The deterministic gate may only preserve an
accepted candidate or reduce it to abstention.

## Metrics

Raw proposer quality and deterministic gate safety remain separate top-level
results.

### Raw proposer quality

- proposal coverage and schema-valid rate;
- decision accuracy and abstention precision/recall/F1;
- critical false emission count for gold `abstain` or `no_memory` cases;
- exact evidence rate;
- kind accuracy;
- predicate sense and canonical-operator accuracy;
- role-name, local-entity partition, and role-binding accuracy;
- modality, polarity, and typed-time accuracy;
- lifecycle-link accuracy;
- for L2, support-ID, structured-claim, abstraction-method, closure-pattern,
  and source-coverage accuracy.

### Deterministic gate safety

- unknown or cross-case evidence rejection;
- invalid local-entity or role reference rejection;
- unsupported modality/time rejection;
- incomplete lifecycle, support, claim, or closure rejection;
- unresolved identity-dependent aggregate rejection;
- gate intervention count and reason distribution;
- critical false L1/L2 materialization count;
- authoritative guard fingerprint and protected counts before/after;
- automatic write counts for L1, L2, revision, closure, identity, and
  membership.

The gate does not convert an incorrect kind, predicate, role, time, or closure
into a correct one. Gated safety cannot be used to hide raw proposer errors.

## Dev Gates

Both stages require:

- proposal coverage `1.0`;
- schema-valid rate `1.0`;
- exact evidence rate `1.0`;
- raw critical false emission count `0`;
- raw decision accuracy at least `0.90`;
- raw abstention F1 at least `0.80`;
- each safety-critical field family accuracy at least `0.85`;
- deterministic critical false materialization count `0`;
- every automatic authoritative write count `0`;
- unchanged authoritative guard fingerprint and counts.

L2 additionally requires exact support-ID and source-turn/session coverage rate
`1.0`, because incomplete provenance cannot be recovered downstream.

## Failure Taxonomy and Repair

Failures are classified before prompt or policy changes:

- `false_emission`;
- `false_abstention`;
- `evidence_error`;
- `kind_error`;
- `predicate_or_operator_error`;
- `role_or_local_entity_error`;
- `modality_or_polarity_error`;
- `time_error`;
- `lifecycle_error`;
- `l2_support_error`;
- `l2_claim_or_abstraction_error`;
- `l2_closure_or_source_coverage_error`.

Repairs may use only the frozen dev/diagnostic cases. Each policy or prompt
version is frozen with its run. A passing dev result does not authorize hidden
reuse, automatic writes, or pipeline integration.

## Deterministic Candidate Compiler

The compiler validates proposal structure and emits a read-only typed candidate
envelope. It may derive stable candidate/proposal IDs, bind exact EvidenceSpan
and source revisions, and calculate fingerprints. It must not construct an
authoritative `L1MemoryUnitV2`, `L2MemoryUnitV2`, revision, closure evaluation,
identity decision, or membership write in this wave.

## Tests

Tests cover:

- exact dev source replay and public/authority/gold separation;
- opaque IDs and no answer-bearing public metadata;
- complete requirement coverage and distribution checks;
- strict proposal unions and local-reference closure;
- evidence, source, lifecycle, support, claim, and closure validation;
- proposal freeze before scoring;
- raw/gated metric separation and score recomputation;
- all failure taxonomy categories;
- immutable partial-output handling and deterministic replay;
- zero authoritative writes and unchanged guard state;
- protected identity, authoritative-v5, fresh-v4,
  candidate-assessment-v3, and bridge-v1/v2/v3 hashes.

## Boundaries

- No external memory system is rerun.
- No old Fusion Memory code, tests, architecture, or results are accessed.
- The existing extraction skeleton and core ontology/query/retrieval/fallback
  surfaces are unchanged.
- Embeddings, WordNet, schema.org, KEOL, and surface-string equality cannot
  supply facts, identity, membership, typed roles, or closure.
- `LONGMEMEVAL-6d550036` remains
  `structured_l2_identity_unresolved`.
- No fresh hidden data is created until both dev gates pass.
- No automatic L1/L2/revision/closure/identity/membership write is authorized.
- This wave does not select Extended-AMR, KEOL, or another storage profile.

## L1 Measured Result

The final L1 dev slice is
`artifacts/automatic-extraction-assessment/typed-extractor-v2-dev-v3/`.
Earlier dev-v1 and dev-v2 slices/runs remain immutable failure evidence. The
first proposer output was rejected before freeze because the prompt described
semantic requirements without exposing the exact nested JSON field contract.
The next valid run showed that exact canonical predicate and role scoring was
underdetermined without a public canonical catalog. Repairs therefore exposed
global operator/sense/role/kind/qualifier/time policies, never case-to-gold
mappings, and were developed only on the same 12 dev cases.

The passing run is
`run-20260728T060140Z-deepseek-v4-pro-typed-l1-dev-v6`, produced by a fresh
no-history OpenAI-compatible request using actual model `deepseek-v4-pro`.
Proposals and provenance were frozen before scoring. Raw proposer quality and
deterministic gate safety both passed. Decision accuracy, abstention F1, exact
evidence, kind, predicate/operator, modality/polarity, time, lifecycle,
derivation/speaker, and operation provenance were `1.0`; role/local-entity and
condition/scope accuracy were `8/9`. One condition participant/local-entity
error remains visible in raw error analysis. Critical false emission, gate
intervention, and deterministic critical false materialization were all zero.

All automatic authoritative write counts remained zero and guard fingerprint
`e184b6caf2998acf1c8700bc84d24bbafd49ab9c8f15738d1af8cc484ee5ebcc`
was unchanged. The score/report/error analysis replay was byte-identical.
Fresh verification was 22 focused typed L1 tests, 197 knowledge-pipeline tests,
292 natural-memory tests, successful compileall, and all formal validators
valid. At that point this result unlocked only the L2 dev stage; the L2 result
below completes the two-stage dev acceptance criteria.

### L1 provenance-v2 follow-up

Before fresh-hidden preregistration, L1 was upgraded to the same provenance-v2
chain as L2. Dispatch now binds the requested model, raw response is archived
read-only, freeze proves that staged proposals equal the raw response payload,
and scoring revalidates dispatch, raw response, proposals, public input, and
requested/response model metadata. Dev v7 and v8 remain immutable raw failures.
Prompt V6 was repaired only against those dev failures and v9
`run-20260728T091848Z-deepseek-chat-official-typed-l1-dev-v9` passed both
readiness gates. The requested alias was `deepseek-chat`; the response model
was `deepseek-v4-flash`; isolation remained declarative.

V9 raw decision accuracy, abstention F1, evidence, kind, predicate, modality,
time, derivation, and operation accuracy were `1.0`. Role/local-entity,
condition/scope, and lifecycle accuracy were `8/9`; one lifecycle error caused
one fail-closed gate demotion, so gated decision accuracy was `11/12`. This
residual raw error remains explicit. The final prompt/proposals/provenance/score
hashes are `a4d03b0e...b835586`, `dd284824...dfeac2`,
`400217f3...52cc`, and `e2bd3a3c...443612`.

Because the L1 root now contains two passing runs, L2 source replay selects its
original v6 dependency through immutable
`l2-source-qualification-receipt.json` rather than directory cardinality. The
receipt hash is `27e5f46e...70544`, and the existing L2 manifest remains
byte-identical.

## L2 Measured Result

The final L2 dev slice is
`artifacts/automatic-extraction-assessment/typed-extractor-v2-l2-dev-v9/`.
It contains six frozen cases: four emissions and two abstentions. v7/v10 is
retained as audit history because review found standalone-threshold and
raw/model provenance gaps. After provenance v2 fixed those gaps, v8/v11
correctly failed raw quality on one structured-claim predicate-surface error
while deterministic gate safety passed. The error was repaired only in the dev
public exact-copy contract; no fresh hidden data was created or inspected.

The passing run is
`run-20260728T084011Z-deepseek-chat-official-typed-l2-dev-v12`. The frozen
requested alias is `deepseek-chat`; the archived API response identifies the
resolved model as `deepseek-v4-flash`. Provenance records these separately and
binds dispatch, raw response, proposals, and freeze sequence. This remains a
declarative fresh-agent file-access contract, not OS-enforced isolation.
Proposals and provenance were frozen before scoring read authority or gold.

Raw decision accuracy, abstention F1, evidence, support, kind, structured
claim, abstraction, closure, source coverage, and summary accuracy were all
`1.0`. Raw critical false emission, gate intervention, and deterministic
critical false materialization were zero. Both readiness gates passed. All
automatic authoritative writes remained zero and guard fingerprint
`e184b6caf2998acf1c8700bc84d24bbafd49ab9c8f15738d1af8cc484ee5ebcc`
was unchanged.

Final proposals, provenance, score, and report SHA-256 are
`655c696154d7e623ae417d3c5978a23ac7f7fb611e1b9f27ef21f7e25344e2c9`,
`df905c9ed119eff40b39239243b53ef1ccfc6aced39b5b377854233fcc421d26`,
`e27be9f426a78bf67fb03938ce97aeccc697e071bf866494d9a1d319fed4db57`,
and `c7cdd49adb166112c5a6ba6a64ef3c398f01c979bd4591c3135d911eafe8d600`.
All formal v7-v9 files are read-only, and score/report/error analysis replayed
byte-identically. Verification completed with 31 focused L2 tests, 197
knowledge-pipeline tests, 352 natural-memory tests, compileall, formal
validators, protected hashes, and bridge-v3 replay.

This pass satisfies the two-stage dev acceptance criteria. The next authorized
step is preregistration of a fresh hidden typed-extraction evaluation. It does
not authorize pipeline integration, automatic L1/L2/revision/closure/identity/
membership writes, embedding authority, or resolution of
`LONGMEMEVAL-6d550036`.

## Acceptance Criteria

1. L1 and L2 dev slices are frozen with public/authority/gold separation.
2. Real proposals are produced by a zero-history isolated proposer and frozen
   before scoring.
3. Raw proposer quality and deterministic gate safety are independently
   reproducible.
4. Failures are classified and repaired only on dev/diagnostic data.
5. Every accepted typed candidate has exact evidence and complete local
   reference closure; every unresolved case abstains.
6. Automatic authoritative writes remain zero and protected state is unchanged.
7. A fresh hidden evaluation is considered only after both dev gates pass.
