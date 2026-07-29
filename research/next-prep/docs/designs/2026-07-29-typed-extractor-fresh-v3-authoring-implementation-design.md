# Typed Extractor Fresh-Hidden V3 Authoring Implementation Design

## Status

Approved under the user's standing instruction to continue the established
design without intermediate confirmation. The user also reported a remote
Codex working concurrently. A pre-edit audit found no v3 authoring,
materialization, receipt, evaluation, pytest, or proposer artifact in this
workspace; this stage therefore owns only the new v3 authoring files named
below and must preserve any later concurrent change it did not create.

## Goal

Implement and freeze the deterministic 42-case authoring mechanism required by
the immutable fresh-v3 preregistration while the formal evaluation root remains
absent. This stage proves the exact mechanism and freezes one implementation
receipt. It does not materialize hidden data, call a proposer, score proposals,
integrate the pipeline, or write memory state.

## Alternatives

1. Reuse fresh-v2 blueprints under new IDs. Rejected because semantic content
   already exposed to evaluation is not fresh.
2. Extract and modify a shared authoring framework. Rejected because changing
   fresh-v2 code would invalidate its immutable receipt hashes.
3. Create an independent v3 module using only stable L1/L2 schema and IO types.
   Selected because it preserves all prior frozen chains while providing new
   content and an explicit contamination boundary.

## Ownership And Files

This stage creates only:

- `tools/natural_memory_benchmark/typed_extractor_fresh_v3_authoring.py`;
- `tests/natural_memory_benchmark/test_typed_extractor_fresh_v3_authoring.py`;
- `artifacts/automatic-extraction-assessment/typed-extractor-v3-fresh-hidden-prereg-v1/authoring-implementation-receipt.json`;
- this design, its implementation plan, and completion updates to the three
  workspace fact sources.

It does not modify the frozen v3 preregistration module/test/JSON, v1/v2
authoring code, shared CLI, scorer/model runner, query, identity, authority, or
benchmark modules.

## Authoring Bundle

`typed_extractor_fresh_v3_authoring.py` owns strict blueprint models, stable
family/ordinal ordering, deterministic opaque references, in-memory rendering,
contamination validation, and receipt freeze/validation. Its public seam is:

```python
build_fresh_v3_authoring_bundle(
    preregistration_path: Path,
) -> FreshV3AuthoringBundle

validate_fresh_v3_authoring_bundle(
    bundle: FreshV3AuthoringBundle,
    preregistration_path: Path,
) -> dict[str, Any]

freeze_fresh_v3_authoring_receipt(
    preregistration_path: Path,
    evaluation_root: Path,
    workspace_root: Path,
    receipt_time: str,
) -> dict[str, Any]

validate_fresh_v3_authoring_receipt(
    preregistration_path: Path,
    evaluation_root: Path,
    workspace_root: Path,
) -> dict[str, Any]
```

The bundle contains strict existing L1/L2 source, public, authority, gold, and
manifest models. Building or validating it performs no filesystem writes.
Only the explicit receipt freezer writes a file.

## Composition

L1 uses 24 new blueprints, exactly three per preregistered family and in the
preregistration's family order:

- `false_emission`;
- `false_abstention`;
- `role_or_local_entity`;
- `time`;
- `condition_or_scope`;
- `evidence`;
- `derivation_or_speaker`;
- `lifecycle`.

The cases cover question/instruction/hypothetical controls, explicit user and
tool facts, compound/prepositional participants, event/valid/unresolved time,
condition/scope binding, distractor-safe exact evidence, user/tool/assistant
epistemic separation, and correction/supersession/conflict provenance.

L2 uses 18 new blueprints, exactly two per preregistered family and in the
preregistration's family order:

- `unsupported_modality_control`;
- `unresolved_selection_control`;
- `incompatible_support_control`;
- `incomplete_closure_control`;
- `coreference_case`;
- `task_composition_case`;
- `lifecycle_case`;
- `state_summary_case`;
- `preference_aggregation_case`.

Every emitted L2 candidate has at least two typed L1 supports, exact public
predicate/subject/object or theme binding, an allowed operator/sense pair, and
complete source/session/evidence closure. Controls expose the unresolved or
incompatible field and must abstain.

All 42 blueprints are used. There is no seed, sampling, filtering, ranking,
replacement, retry, or resampling path. Invalid generation aborts the stage.

## Public And Private Separation

Opaque case, candidate, evidence, support, session, and turn references derive
from the preregistered namespace plus private keys via SHA-256. Public payloads
contain only the raw messages/evidence, untyped candidate, opaque references,
and versioned public vocabulary. They exclude private case IDs, primary or
secondary families, expected decisions, authority constraints, typed gold,
prior inventories, and receipt data.

The validator recursively checks that no private identifier or private family
label occurs in the canonical public bytes. Evidence quotes must match exact
source offsets and speaker bindings. Every candidate, lifecycle, operation,
support, claim, and closure reference must resolve inside its case.

## Contamination Contract

The module verifies the formal preregistration by exact fixed SHA-256, schema,
evaluation ID, mode `0444`, and the 39 bound input hashes. It obtains prior
paths from the frozen preregistration registry without invoking the
pre-authoring-only absence validator.

The derived prior inventory contains:

- private and opaque identifiers from ID/reference fields;
- evidence IDs and normalized exact evidence/source messages;
- normalized semantic signatures for typed L1 candidates and L2 claims,
  abstraction, and closure.

Normalization is Unicode NFKC, case-folding, and whitespace collapse; semantic
objects are canonical JSON after removing only opaque identity and evidence
reference fields. New blueprints fail closed on any ID, evidence text, source
message, or semantic-signature overlap. The inventory is in memory and is not
written into proposer-visible payloads.

## Implementation Receipt

The only formal artifact in this stage is
`authoring-implementation-receipt.json`, schema
`typed-extractor-fresh-v3-authoring-receipt-v1`, mode `0444`. It binds:

- exact preregistration path, SHA-256, schema, mode, and evaluation ID;
- authoring module and test SHA-256;
- L1/L2 schema, preregistration, and IO dependency SHA-256 values;
- L1/L2 blueprint-manifest SHA-256 values and exact family/count contracts;
- all 39 preregistered prior input hashes;
- formal evaluation root and materialization module/test absence;
- hidden artifact and model request count `0`;
- every automatic memory/identity/membership/closure/revision/snapshot/
  aggregate write count `0`;
- unchanged candidate queue SHA-256 and guard fingerprint;
- unresolved LongMemEval identity and non-authoritative embedding boundary.

Receipt time is a caller-supplied untrusted UTC label. The writer rejects an
existing evaluation root, materialization implementation/test, model-run path,
mutable or drifted preregistration, code/test/input drift, or a different
existing receipt. No file-existence-only fallback is an authority rule; the
future materializer must call the receipt validator and bind its exact SHA.

## Concurrent Writer Handling

Before each edit or freeze, the stage rechecks whether a target path appeared.
If an unknown writer creates a target, work stops for read-only reconciliation;
the file is not overwritten, deleted, chmod-mutated, or treated as valid by
existence alone. Existing unrelated workspace changes are preserved.

## Testing

Tests first fail because the authoring module is absent. Green coverage includes
strict model rejection, exact family/order/counts, deterministic byte rendering,
public/private separation, evidence offsets, L1 lifecycle/operation closure, L2
literal/support/source/evidence closure, all-prior contamination rejection,
zero formal writes, receipt strictness, impossible timestamps, hash drift,
premature future paths, immutable `0444` mode, and validation parity.

## Boundaries

- Formal hidden source/public/authority/gold/manifest/chronology remains absent.
- No proposer/model request runs and no API credential is read or persisted.
- No L1/L2/revision/source-revision/closure/identity/membership/snapshot/
  aggregate write is authorized.
- Candidate-generation v3 and manual adjudications remain immutable and
  unmaterialized.
- Embedding is not an authority.
- `LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.
- External memory systems are not rerun and old Fusion Memory is not accessed.

Passing this receipt gate authorizes only one-time formal hidden
materialization in a later stage.
