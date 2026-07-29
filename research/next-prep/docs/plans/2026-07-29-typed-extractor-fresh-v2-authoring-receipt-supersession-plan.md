# Typed Extractor Fresh-V2 Authoring Receipt Supersession Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the prematurely frozen receipt and create a strictly validated append-only v2 receipt that binds the repaired authoring implementation.

**Architecture:** The existing authoring module gains a strict v2 receipt model, a v2 freeze/validator pair, and one active-receipt resolver. The original receipt remains immutable and becomes an explicitly superseded predecessor rather than being deleted or overwritten.

**Tech Stack:** Python 3.13, Pydantic v2, pytest, canonical JSON, SHA-256, existing `.venv-h100`.

## Global Constraints

- Work only in `/public/home/wwb/KE-mem/KE-memory-next-prep-20260727`; do not initialize Git.
- Keep prereg-v3 and `authoring-implementation-receipt.json` byte-identical.
- Keep `artifacts/automatic-extraction-assessment/typed-extractor-v2-fresh-hidden-v2` absent.
- Do not create formal hidden artifacts, run a model, or execute authoritative writes.
- Do not modify the shared CLI, query compiler, or frozen preregistration code.
- `LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.

---

### Task 1: Close The L2 Literal-Binding Finding

**Files:**
- Modify: `tools/natural_memory_benchmark/typed_extractor_fresh_v2_authoring.py`
- Modify: `tests/natural_memory_benchmark/test_typed_extractor_fresh_v2_authoring.py`

**Interfaces:**
- Consumes the frozen L2 prompt literal-binding contract.
- Produces a bundle validator that rejects any emitted primary claim whose predicate, subject, object/theme, or support set drifts from the public candidate.

- [x] Add a regression test across every emitted L2 blueprint and observe the travel case fail on predicate/object binding.
- [x] Add a validator-mutation test and observe the old validator fail to report the literal-binding error.
- [x] Replace the travel two-claim special case with one aggregate primary claim while preserving separate per-turn L1 supports.
- [x] Enforce the invariant before inventory validation and remove the unused two-claim authoring path.
- [x] Run the focused tests; result after the semantic repair is `34 passed`.

### Task 2: Implement Append-Only Receipt Supersession

**Files:**
- Modify: `tools/natural_memory_benchmark/typed_extractor_fresh_v2_authoring.py`
- Modify: `tests/natural_memory_benchmark/test_typed_extractor_fresh_v2_authoring.py`

**Interfaces:**
- Produces `freeze_fresh_v2_authoring_supersession_receipt(preregistration_path: Path, evaluation_root: Path, workspace_root: Path, receipt_time: str) -> dict[str, Any]`.
- Produces `validate_fresh_v2_authoring_supersession_receipt(preregistration_path: Path, evaluation_root: Path, workspace_root: Path) -> dict[str, Any]`.
- Produces `validate_fresh_v2_active_authoring_receipt(preregistration_path: Path, evaluation_root: Path, workspace_root: Path) -> dict[str, Any]`.

- [x] Add failing tests that copy the exact predecessor receipt and verify v2 schema, predecessor hash, current hashes, immutable mode, idempotence, and active selection.
- [x] Add rejection tests for missing/writable/modified predecessor, current code/test/blueprint drift, existing different v2 receipt, and premature evaluation/model-run paths.
- [x] Implement a strict `AuthoringSupersessionReceipt` model with exact false/zero boundaries and fixed reason `post_freeze_review_primary_literal_binding_repair`.
- [x] Implement v2 payload construction, immutable write, recomputation validator, and active resolver without changing the v1 receipt bytes.
- [x] Run focused tests and confirm both original-receipt and v2-receipt paths are covered; current result is `49 passed`.

### Task 3: Review, Freeze, And Audit

**Files:**
- Generate: `artifacts/automatic-extraction-assessment/typed-extractor-v2-fresh-hidden-prereg-v3/authoring-implementation-receipt-v2.json`
- Modify after verification: `README.md`, `AGENTS.md`, `安排.md`, `docs/plans/2026-07-28-typed-extractor-fresh-hidden-v2-authoring-implementation-plan.md`, and this plan.

**Interfaces:**
- Consumes the exact predecessor receipt SHA-256 `4bb2575d985126dfbd91d01a3111d3f4acb2ebe57c3bfd62b1d60ee847d7314d`.
- Produces the only active implementation binding accepted by the next materialization stage.

- [x] Obtain an independent read-only re-review with no open Critical/Important finding.
- [x] Run focused authoring, all typed-extractor, complete natural-memory, knowledge-pipeline, and `compileall` verification.
- [x] Recheck prereg/queue/guard hashes, credential-pattern count, formal-root absence, zero automatic writes, and no active workspace test/API/model session.
- [x] Freeze v2 using a current UTC label; validate mode `0444`, SHA-256, predecessor hash, current code/test/dependency/blueprint hashes, and active-receipt selection.
- [x] Update workspace fact sources with both the superseded v1 identity and active v2 identity; keep raw proposer/gate and write-authorization boundaries unchanged.

Execution record: independent re-review found no Critical/Important and one Minor direct active-selector corruption coverage suggestion. The active receipt was frozen at `2026-07-29T00:30:16Z`, mode `0444`, size `7364`, SHA-256 `4ce77c20c2941a66c3e74c1bd561e9d5ceee360a3723b75eed694fc47267c94b`. The predecessor remains mode `0444`, SHA-256 `4bb2575d985126dfbd91d01a3111d3f4acb2ebe57c3bfd62b1d60ee847d7314d`. Verification was focused `49 passed`, typed extractor `177 passed`, knowledge pipeline `197 passed`, natural memory `580 passed`, and `compileall` success.

## Self-Review

- Spec coverage: immutable predecessor preservation, fail-closed active selection, TDD, review, freeze, and audit are all assigned.
- Placeholder scan: no deferred implementation detail is left unspecified.
- Type consistency: all three v2 public signatures use the same `Path, Path, Path` inputs as the existing receipt validator, with `receipt_time` added only to the writer.
