# Query Execution Authority Result Boundary V1

## Scope

This change separates deterministic evaluation of a caller-provided query
snapshot from an authoritative execution result. It does not change query
matching, abstention, closure, latest-time, role, or evidence semantics.

## Problem

The low-level `_execute_compiled_query_snapshot` helper accepts an ordinary
`QueryExecutionSnapshotV1` but returns `QueryExecutionResultV2`, including a
Git memory view and `closure_complete=True`. A diagnostic call can therefore
be mistaken for a result produced after repository and artifact verification.
A leading underscore is not a semantic authority boundary.

## Design

1. `_evaluate_compiled_query_snapshot` returns
   `QuerySnapshotEvaluationV1`. This model contains only query denotation,
   evidence, closure, and abstention fields. It has no memory view or authority
   claim.
2. `QueryExecutionAuthorityV1` is a frozen content binding created by the
   verified snapshot adapter. It binds the Git memory view, bundle ID, full
   bundle-history artifact hash, registry hash, optional identity snapshot
   pair, snapshot hash, plan hash, complete evaluation hash, and its own
   recomputed authority hash.
3. `QueryExecutionResultV3` nests the evaluation and authority binding. It
   exposes read-only compatibility properties for existing callers while its
   serialized schema makes the authority boundary explicit.
4. The adapter first revalidates the compiled plan, verifies repository HEAD,
   bundle history, TurnBundles, registry, identity scope, and snapshot, then
   evaluates and constructs the authority binding.
5. Evaluation collections are tuples in memory and remain JSON arrays on the
   wire. Authority and V3 `model_copy(update=...)` calls round-trip through
   model validation so Pydantic's unchecked copy path cannot preserve stale
   hashes after an update.

## Invariants

- A low-level evaluation cannot serialize a Git memory view or authority hash.
- `evaluation_sha256` is the canonical SHA-256 of the complete evaluation,
  including query ID, plan hash, answers, matched facts, evidence, closure,
  abstention, count, and reason.
- An authority hash is the canonical SHA-256 of every authority field except
  `authority_sha256` itself, including `evaluation_sha256`.
- Identity snapshot ID and fingerprint are either both present or both absent.
- Result evaluation plan hash and authority plan hash must match.
- Tuple-valued semantic outputs remain sorted for deterministic replay and
  serialize as JSON arrays.
- Direct collection mutation is unavailable, and Authority/V3 copy updates
  must pass the same canonical validators as deserialized input.
- No hidden data, model request, authoritative write, or shared fact-source
  update is part of this change.

## Trust Boundary

The authority and evaluation hashes are deterministic integrity and audit
bindings. They are not digital signatures, unforgeable capabilities, or a
Python sandbox. A process that can fabricate every field can recompute both
hashes. Untrusted cross-process consumers must reopen the Git repository and
verify the bound commit and artifacts, or require a separately signed or
Git-published execution receipt. V3 only prevents a diagnostic snapshot
evaluation from being confused with the adapter's verified result inside the
current execution boundary.

## Alternatives Rejected

Keeping V2 and adding an `authoritative` boolean remains forgeable and mixes
diagnostic and authority semantics. Returning a flat V3 duplicates every
evaluation field and keeps content and authority claims visually mixed.
Freezing only the outer Pydantic model is insufficient because nested lists
remain mutable and `model_copy(update=...)` skips validation. A cryptographic
signature or independently verifiable execution receipt is a later
persistence/distribution concern, not part of this in-process boundary split.
