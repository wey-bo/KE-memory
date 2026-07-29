# Typed Extractor V2 Dev Repair For Fresh V2 Design

## Status

Approved under the user's standing direction to execute the established design
without intermediate confirmation. This design is limited to dev/diagnostic
repair. It does not create, select, or inspect fresh-hidden v2 cases.

## Goal

Repair the raw L1 and L2 proposer failure classes observed in fresh-hidden v1
using only new diagnostic-authored dev data. Require both raw proposer quality
and deterministic gate safety to pass a stricter repair gate before separately
preregistering fresh-hidden v2.

## Frozen Failure Input

Only the aggregate v1 error taxonomy and metrics may guide diagnostic coverage.
Fresh-v1 public, authority, gold, proposals, and case-level semantics are not
inputs to the diagnostic builders or proposer prompts. They remain immutable
audit artifacts.

The repair targets are:

- L1: false emission, false abstention, evidence, condition/scope, time,
  role/local entity, lifecycle, predicate/operator, modality/polarity,
  derivation/speaker, and operation provenance.
- L2: false emission on required abstentions, abstraction method, structured
  claim, and kind. Evidence, support, source coverage, closure, and summary
  remain regression requirements even though they passed v1.

## Alternatives

### Prompt-only repair on the old dev slices

This is rejected. The prior dev slices already passed and do not expose the
missing behaviors. Editing prompts without independent coverage would be an
unverified hidden-driven change.

### Deterministic-gate expansion

This is rejected as the primary repair. It could demote more unsafe proposals,
but it cannot improve raw proposer quality and would risk presenting safety as
semantic competence.

### New diagnostic-authored dev packs

This is selected. It gives each failed family explicit non-hidden coverage,
keeps the cases clearly separate from natural benchmark evidence, and permits
versioned prompt repair with immutable dev runs. The trade-off is that passing
diagnostics is not natural-data evidence; fresh-hidden v2 remains mandatory.

## Diagnostic Data

L1 uses 16 cases under namespace
`typed-extractor-l1-dev-repair-v1:2026-07-28`:

- four non-emission controls split between `no_memory` and `abstain`, including
  questions/instructions with no durable fact and unsupported modality;
- three valid emissions designed to detect false abstention across distinct
  memory kinds;
- two exact-evidence cases containing plausible distractor spans;
- two condition/scope cases with explicit participant binding;
- two time cases, one resolved and one unresolved;
- two role/local-entity cases with competing participants;
- one lifecycle plus operation-provenance case.

Cases may cover more than one family, but the manifest records one primary
diagnostic family and all secondary coverage. Every target family must have at
least two scored opportunities across the pack after overlap is counted.

L2 uses 12 cases under namespace
`typed-extractor-l2-dev-repair-v1:2026-07-28`:

- four required abstentions covering unsupported modality, unresolved deictic
  selection, incompatible supports, and incomplete support/evidence closure;
- two coreference-resolution emissions;
- two task-composition emissions;
- two lifecycle-resolution/update emissions;
- two state/preference aggregation emissions that force non-task kind and
  structured-claim selection.

Every L2 case includes two or more closed typed L1 supports. Diagnostic source
text, support IDs, turn/session refs, and evidence IDs are newly authored and
must not overlap L1/L2 dev or fresh-v1 identifiers. The source metadata says
`diagnostic_authored`; these results cannot be reported as natural benchmark
quality.

## Artifacts And Separation

The roots are:

- `artifacts/automatic-extraction-assessment/typed-extractor-v2-l1-dev-repair-v1/`
- `artifacts/automatic-extraction-assessment/typed-extractor-v2-l2-dev-repair-v1/`

Each root contains an immutable diagnostic source, public, authority, gold,
manifest, prompt versions, and model-run directories. Public files contain only
opaque IDs, diagnostic source text, untyped candidates, allowed vocabularies,
and L2 typed support packs. Authority/gold and prior scorer output are excluded
from proposer access.

New builders are separate adapters around the existing strict L1/L2 public,
authority, gold, and proposal models. They do not modify the bridge-v3 ledger,
existing dev roots, fresh-v1 roots, shared scorer thresholds, query modules, or
authoritative memory code.

## Qualification

Every model run is an immutable no-history official API request. The dispatch
requests `deepseek-chat`; the raw response model is recorded independently. Raw
response, proposals, and provenance freeze before scoring reads authority/gold.
Semantic dev failures are retained. Prompt repairs create a new prompt version
and a new run; no failed run is overwritten.

Existing L1/L2 scorers produce the normal raw and deterministic metrics. A
separate dev-repair qualification report applies stricter exit criteria without
changing those scorers:

- proposal coverage and schema validity: `1.0`;
- raw decision accuracy and abstention F1: `1.0`;
- exact evidence, support ID, and source coverage where applicable: `1.0`;
- every L1 field-family accuracy: `1.0`;
- L2 kind, structured claim, abstraction, closure, and summary accuracy: `1.0`;
- raw critical false emission count: `0`;
- gate intervention count: `0`;
- deterministic critical false materialization count: `0`;
- automatic authoritative writes: `0` and guard fingerprint unchanged.

Raw and gated results remain separate. A scorer-level pass under the older
thresholds does not satisfy dev-repair readiness unless the stricter report also
passes.

## Transition To Fresh V2

Both L1 and L2 dev-repair reports must pass before any fresh-v2 source/public/
authority/gold path exists. Passing prompts, thresholds, diagnostic exclusions,
code hashes, namespaces, model policy, and zero-write boundaries are then bound
by a new preregistration. Fresh-v2 selection and authoring require a separate
design/plan and must use evidence and identifiers absent from all dev and v1
hidden sets.

## Boundaries

- No L1, L2, revision, closure, identity, membership, snapshot, aggregate, or
  source-revision write is authorized.
- The four user-confirmed identity adjudications remain unmaterialized and the
  candidate-generation v3 queue remains unchanged.
- Embeddings cannot authorize facts, roles, identity, membership, or closure.
- External memory systems are not rerun and old Fusion Memory is not accessed.
- Query compiler/executor work remains independent and cannot consume these
  diagnostic candidates as authoritative memory.
- `LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.

## Verification

Tests require strict schema rejection, deterministic opaque IDs, public/private
separation, diagnostic-family counts, no prior ID/evidence overlap, immutable
artifacts, raw/provenance freeze order, scorer replay, stricter qualification
recomputation, unchanged guards, and zero writes. The final dev-repair report
must name its diagnostic-only limitation and the mandatory fresh-v2 step.
