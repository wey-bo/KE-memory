# Typed Extractor Fresh-Hidden V2 Authoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the deterministic 36-case authoring mechanism and freeze its implementation receipt before any formal hidden artifact or model request exists.

**Architecture:** A new standalone module contains strict declarative L1/L2 blueprints, deterministic in-memory renderers, contamination checks, and immutable receipt freeze/validation. The shared CLI and preregistration code remain unchanged so their frozen hashes do not drift.

**Tech Stack:** Python 3.13, Pydantic v2, pytest, canonical JSON and SHA-256 helpers, existing `.venv-h100`.

## Global Constraints

- Work only in `/public/home/wwb/KE-mem/KE-memory-next-prep-20260727`; this is not a Git repository, so do not initialize Git, create a worktree, or commit.
- Keep prereg-v2/v3 and all existing frozen artifacts byte-identical.
- Require formal evaluation root `artifacts/automatic-extraction-assessment/typed-extractor-v2-fresh-hidden-v2` to remain absent.
- Do not create formal hidden source/public/authority/gold/manifest/chronology artifacts and do not run a model.
- Use all L1 24 and L2 12 blueprints in exact preregistered family counts; prohibit filtering, replacement, and resampling.
- Reject prior ID, evidence, source-text, and normalized-semantic-signature contamination against prereg-v3 bound inputs.
- Do not modify the shared CLI or any query compiler file.
- Do not authorize pipeline integration or any L1/L2/revision/source-revision/closure/identity/membership/snapshot/aggregate write.
- Do not access old Fusion Memory or rerun external memory systems.

---

### Task 1: Close Preregistration Documentation And Define The Authoring Contract

**Files:**
- Modify: `安排.md`
- Modify: `docs/designs/2026-07-28-typed-extractor-fresh-hidden-v2-preregistration-design.md`
- Modify: `docs/plans/2026-07-28-typed-extractor-fresh-hidden-v2-preregistration-plan.md`
- Create: `docs/designs/2026-07-28-typed-extractor-fresh-hidden-v2-authoring-implementation-design.md`
- Create: `docs/plans/2026-07-28-typed-extractor-fresh-hidden-v2-authoring-implementation-plan.md`

**Interfaces:**
- Consumes the immutable prereg-v3 identity and review findings.
- Produces the binding authoring and receipt requirements for Tasks 2-4.

- [x] Replace stale prereg-v2 current-state claims with the prereg-v3 schema, path, timestamp, SHA-256, size, mode, and `17/127/197/498` test counts.
- [x] Record prereg-v2 as immutable but superseded.
- [x] Record the pure in-memory authoring, contamination, receipt, and zero-write design.

### Task 2: Write And Observe The Failing Authoring Tests

**Files:**
- Create: `tests/natural_memory_benchmark/test_typed_extractor_fresh_v2_authoring.py`
- Test target: `tools/natural_memory_benchmark/typed_extractor_fresh_v2_authoring.py`

**Interfaces:**
- Expects `build_fresh_v2_authoring_bundle(preregistration_path: Path) -> FreshV2AuthoringBundle`.
- Expects `validate_fresh_v2_authoring_bundle(bundle: FreshV2AuthoringBundle, preregistration_path: Path) -> dict[str, Any]`.
- Expects `freeze_fresh_v2_authoring_receipt(preregistration_path: Path, evaluation_root: Path, workspace_root: Path, receipt_time: str) -> dict[str, Any]`.
- Expects `validate_fresh_v2_authoring_receipt(preregistration_path: Path, evaluation_root: Path, workspace_root: Path) -> dict[str, Any]`.

- [x] Write tests for exact stable family order/counts, strict existing L1/L2 payload validation, public/private separation, deterministic bytes, evidence/reference closure, and prior-data disjointness.
- [x] Write rejection tests for duplicate/changed blueprint IDs, text/signature contamination, invalid offsets, incomplete L2 closure, coercive receipt types, impossible UTC, code/test/prereg drift, existing evaluation root, and existing model-run paths.
- [x] Run `.venv-h100/bin/pytest -q tests/natural_memory_benchmark/test_typed_extractor_fresh_v2_authoring.py` and confirm collection fails with `ModuleNotFoundError` for the absent module.

### Task 3: Implement The Pure Authoring Module

**Files:**
- Create: `tools/natural_memory_benchmark/typed_extractor_fresh_v2_authoring.py`
- Test: `tests/natural_memory_benchmark/test_typed_extractor_fresh_v2_authoring.py`

**Interfaces:**
- Implements the three Task 2 public functions without changing shared CLI or prereg code.
- Returns strict in-memory source/public/authority/gold/manifest payloads for each layer; writes only the receipt when explicitly asked.

- [x] Add strict Pydantic blueprint/bundle/receipt models and exact frozen constants.
- [x] Add deterministic opaque reference, source/evidence offset, semantic-signature, prior-inventory, and closure validation helpers.
- [x] Add all 24 L1 and 12 L2 declarative blueprints and render them in stable family/ordinal order.
- [x] Make focused tests pass with the minimal implementation and confirm the formal evaluation root remains absent.

### Task 4: Freeze And Audit The Implementation Receipt

**Files:**
- Preserve: `artifacts/automatic-extraction-assessment/typed-extractor-v2-fresh-hidden-prereg-v3/authoring-implementation-receipt.json`
- Generate: `artifacts/automatic-extraction-assessment/typed-extractor-v2-fresh-hidden-prereg-v3/authoring-implementation-receipt-v2.json`
- Modify after verification: `README.md`, `AGENTS.md`, `安排.md`, and this plan.

**Interfaces:**
- Consumes the exact read-only prereg-v3 plus authoring module/test/dependencies.
- Produces one active `0444` append-only supersession receipt; no formal evaluation artifact.

- [x] Confirm the original receipt and formal evaluation root states, run focused tests, and preserve the prematurely frozen original receipt after review found code drift.
- [x] Validate the append-only v2 receipt SHA/mode, predecessor hash, blueprint manifest hashes, code/test/dependency hashes, active selection, and all formal hidden/model paths absent.
- [x] Run all typed-extractor tests, the complete natural-memory suite, knowledge-pipeline tests, and `compileall`.
- [x] Recheck protected prereg, candidate queue, guard hashes, zero automatic writes, credential-pattern count, and no active test/API sessions.
- [x] Obtain an independent read-only review; repair every Critical/Important issue with a failing regression test before re-review.
- [x] Update workspace fact sources with the superseded v1 and active v2 identities, verification counts, next one-time hidden-materialization step, and unchanged claim boundaries.

Execution record: v1 receipt SHA-256 `4bb2575d985126dfbd91d01a3111d3f4acb2ebe57c3bfd62b1d60ee847d7314d` remains immutable and superseded. Active v2 receipt SHA-256 is `4ce77c20c2941a66c3e74c1bd561e9d5ceee360a3723b75eed694fc47267c94b`, frozen at `2026-07-29T00:30:16Z`, mode `0444`. Final verification before documentation updates was focused `49 passed`, typed extractor `177 passed`, knowledge pipeline `197 passed`, natural memory `580 passed`, and `compileall` success.

## Self-Review

- Spec coverage: the plan covers exact composition, pure rendering, public/private separation, contamination, receipt chronology, immutable output, test-first implementation, audit, and claim boundaries.
- Placeholder scan: every deferred action is an explicit later-stage boundary, not an unspecified implementation detail.
- Type consistency: all three public function signatures are identical across the design and Tasks 2-4.
