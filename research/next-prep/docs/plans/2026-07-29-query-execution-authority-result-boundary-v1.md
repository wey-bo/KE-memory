# Query Execution Authority Result Boundary Implementation Plan

**Goal:** Prevent caller-constructed snapshots from producing results that can
be mistaken for Git-verified authoritative query execution.

**Architecture:** Split deterministic snapshot evaluation from the verified
adapter boundary. The evaluator returns a non-authoritative model; the adapter
adds an immutable canonical authority binding and returns versioned V3 output.

**Tech Stack:** Python 3, Pydantic v2, pytest, existing canonical SHA-256 and
Git memory-history utilities.

---

### Task 1: Freeze Current Behavior

**Files:**
- Test: `tests/natural_memory_benchmark/test_query_plan_v2_executor.py`

- [x] Keep the existing abstention, matching, closure, latest-time, role, and
   deterministic-order assertions as characterization coverage.
- [x] Run both owned test files and record the baseline count: 44 passed before
  the final deep-immutability review additions.

### Task 2: Add RED Boundary Tests

**Files:**
- Modify: `tests/natural_memory_benchmark/test_query_plan_v2_executor.py`
- Modify: `tests/natural_memory_benchmark/test_query_execution_snapshot_adapter.py`

- [x] Require `_evaluate_compiled_query_snapshot` and
   `QuerySnapshotEvaluationV1` with no `memory_view` or authority fields.
- [x] Require `execute_authoritative_query` to return V3 with a valid binding.
- [x] Require authority, evaluation, identity-pair, direct collection, and
  unchecked copy tampering to fail.
- [x] Require deterministic replay to yield identical serialized bytes.
- [x] Observe RED: evaluation binding first failed with `DID NOT RAISE`; the
  deep-immutability review then produced three expected `DID NOT RAISE`
  failures before the production fix.

### Task 3: Implement the Minimal Split

**Files:**
- Modify: `tools/natural_memory_benchmark/query_plan_v2_executor.py`
- Modify: `tools/natural_memory_benchmark/query_execution_snapshot_adapter.py`

- [x] Replace low-level V2 construction with `QuerySnapshotEvaluationV1`.
- [x] Rename the evaluator and remove the old helper.
- [x] Add authority and V3 result models with canonical validators.
- [x] Bind the complete evaluation hash into the authority hash.
- [x] Make evaluation collections deeply immutable and revalidate Authority/V3
  `model_copy(update=...)` calls.
- [x] Build the authority only after adapter verification and plan
  revalidation.
- [x] Preserve existing semantic result values, ordering, JSON arrays, and
  reasons.

### Task 4: Verify and Audit

- [x] Run the two owned test files with isolated pytest temp state: 47 passed.
- [x] Run the broader QuerySlotPlan contract tests: 95 passed.
- [x] Run the complete natural-memory suite from the remote repository root
  before formal hidden publication: 603 passed. After publication, preserve
  the receipt-bound pre-materialization test unchanged and verify the current
  state as 602 passed, 1 deselected. Run the independent knowledge-pipeline
  suite: 197 passed.
- [x] Run `compileall` across the natural-memory and knowledge-pipeline code
  and tests, plus `tabnanny` on the changed Query modules: clean.
- [x] Complete independent read-only re-review: no Critical, High, or
  Important finding remains.
- [x] Record final code/test/design hashes and confirm no hidden artifact,
  model request, automatic write, or server-owned materialization file was
  changed by this wave.

## Final Bound Hashes

```text
query_plan_v2_executor.py
acd03c1314b7a2bdd40db1a2bcfe3f6ecc496f2cfaee636193291d1645ed2b57

query_execution_snapshot_adapter.py
ace97d3375526c62a9473a92c50c2717216135ea9a7a610ad4b67bcd266b9dfc

test_query_plan_v2_executor.py
6916884d973df03e1471dbf70d7231de4187b1c8cc68503effb658448da45dde

test_query_execution_snapshot_adapter.py
cf153bce414dc8ada9a5407b8e40fdc553a2f137f33cad678d2dec800e2df4aa

2026-07-29-query-execution-authority-result-boundary-v1.md
7d8049540291f207ebf9e04907f8739a53bd9002ad779d07bf48c97146a06e52
```
