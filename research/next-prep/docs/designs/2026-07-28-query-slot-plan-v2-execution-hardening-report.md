# QuerySlotPlan V2 Execution Hardening Report

Date: 2026-07-28
Updated: 2026-07-29
Workspace: `/public/home/wwb/KE-mem/KE-memory-next-prep-20260727`

## Scope

This wave hardens the representation-neutral QuerySlotPlan V2 compiler and
execution boundary. It does not change the memory write path, the L1/L2
extractor, the authoritative memory core, or any fresh-hidden artifact.

## Implemented Contract

- `CompilerRegistryV1` binds ontology and identity revisions, a deterministic
  content hash, and optional identity snapshot ID/fingerprint.
- `CompiledQueryPlanV2` carries the registry content hash and identity snapshot
  binding in its own plan hash.
- `QueryExecutionSnapshotV1` carries all registry bindings and is built only by
  the Git/bundle/TurnBundle adapter.
- `execute_authoritative_query()` rebuilds and verifies the snapshot internally;
  the executor module no longer exposes a public `execute_compiled_query` entry.
- The public entry revalidates the compiled plan hash before execution.
- Execution abstains on any memory, ontology, identity, registry label/hash, or
  identity snapshot mismatch.
- Canonical roles are matched independently of carrier-specific role labels.
- Conjunctive patterns may reuse one fact when the query semantics permit it;
  output fact and evidence IDs are sorted for deterministic replay.
- Compiler and executor both fail closed for literal terms, explicit absence,
  unsupported time operators, multiple latest constraints, multi-atom temporal
  scope, and unsupported answer kinds.
- V1 lowering rejects literal terms instead of silently dropping constraints.
- Low-level snapshot evaluation now returns `QuerySnapshotEvaluationV1`, which
  cannot serialize a Git memory view or an authority claim.
- `QueryExecutionResultV3` nests the evaluation under
  `QueryExecutionAuthorityV1`. The authority binds the Git view, bundle ID,
  full bundle-history artifact hash, registry hash, optional identity snapshot,
  snapshot hash, plan hash, and complete evaluation hash.
- Evaluation collections are immutable tuples in Python and JSON arrays on the
  wire. Authority/V3 `model_copy(update=...)` calls revalidate canonical hashes
  so unchecked Pydantic copies cannot preserve stale bindings.
- Only `execute_authoritative_query()` constructs V3 after adapter
  verification. The checksum is an integrity/audit binding, not a digital
  signature or an unforgeable execution capability.

## Verification

The final review-driven RED cycle produced three expected `DID NOT RAISE`
failures for direct collection mutation and unchecked Authority/V3 copies.
After the minimal fix:

- Owned executor/adapter tests: `47 passed`.
- Complete QuerySlotPlan test set: `95 passed`.
- Complete natural-memory suite before formal hidden publication:
  `603 passed`.
- Post-publication natural-memory suite: `602 passed, 1 deselected`. The sole
  deselected node is the active-receipt-bound pre-materialization test that
  intentionally asserts the formal root is absent; changing it would invalidate
  the frozen authoring receipt.
- Independent knowledge-pipeline suite: `197 passed`.
- `compileall` across natural-memory and knowledge-pipeline code/tests: clean.
- `tabnanny` for the changed Query modules: clean.
- Independent read-only re-review: no Critical, High, or Important finding.

The final bound hashes are:

```text
executor  acd03c1314b7a2bdd40db1a2bcfe3f6ecc496f2cfaee636193291d1645ed2b57
adapter   ace97d3375526c62a9473a92c50c2717216135ea9a7a610ad4b67bcd266b9dfc
exec test 6916884d973df03e1471dbf70d7231de4187b1c8cc68503effb658448da45dde
adapt test cf153bce414dc8ada9a5407b8e40fdc553a2f137f33cad678d2dec800e2df4aa
design    7d8049540291f207ebf9e04907f8739a53bd9002ad779d07bf48c97146a06e52
```

The server-owned fresh-v2 hidden materialization implementation remained a
separate track. This Query wave created no hidden artifact, model request,
automatic memory write, or shared fact-source edit.

## Remaining Boundary

The low-level snapshot evaluator is intentionally non-authoritative and may be
used for deterministic diagnostics. Python module privacy and Pydantic frozen
models are not a security sandbox. A process that can fabricate all V3 fields
can recompute the checksums; untrusted cross-process consumers must reopen and
verify the bound Git state or require a signed/Git-published execution receipt.
Registry ontology and identity content is hash-bound in this wave, while
publication of registry artifacts as first-class Git history objects remains a
later persistence task.
