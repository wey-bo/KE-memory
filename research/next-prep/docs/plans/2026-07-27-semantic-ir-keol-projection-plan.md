# Semantic IR to KEOL Projection Implementation Plan

**Goal:** Add an optional deterministic KEOL compatibility projection from event-role-evidence semantic IR units while preserving evidence, lifecycle, closure, and source-status metadata without selecting KEOL as the persistence backend.

**Architecture:** Create a local projection module under `tools/natural_memory_benchmark/` that converts `L1MemoryUnit`, `L2MemoryUnit`, and `ClosureRecord` into JSON-compatible KEOL-shaped dictionaries for `evidence`, `operators`, `individuals`, `assertions`, and `workflow_runs`. This is an optional adapter contract, not a KEOL runtime replacement, not a writer into the existing KEOL baseline artifacts, and not a storage-selection decision.

**Tech Stack:** Python 3.13, existing semantic IR Pydantic models, pytest, deterministic stable IDs via SHA-256.

---

## Task 1: RED tests for L1 projection

**Files:**
- Create: `tests/natural_memory_benchmark/test_semantic_ir_keol_projection.py`
- Create: `tools/natural_memory_benchmark/semantic_ir_keol_projection.py`

**Steps:**
1. Write a test that builds an `L1MemoryUnit` with one evidence span and calls `project_semantic_ir_to_keol`.
2. Assert output contains one `Evidence`, one `Operator`, role/value `Individual`s, and one `Assertion`.
3. Assert assertion uses an `operator_application` lhs and `individual` rhs.
4. Assert assertion metadata preserves semantic IR unit ID, level, predicate sense, source status, lifecycle, and role bindings.

## Task 2: RED tests for L2 and closure projection

**Files:**
- Modify: `tests/natural_memory_benchmark/test_semantic_ir_keol_projection.py`
- Modify: `tools/natural_memory_benchmark/semantic_ir_keol_projection.py`

**Steps:**
1. Add a test that projects two L1 units, one L2 abstraction, and one closure record.
2. Assert L2 assertion is derived from L1 assertion IDs.
3. Assert closure projection creates a closure assertion with metadata listing required units and closure completeness.
4. Assert evidence IDs remain traceable to raw evidence spans.

## Task 3: CLI artifact generation

**Files:**
- Modify: `tools/natural_memory_benchmark/cli.py`
- Modify: `tests/natural_memory_benchmark/test_semantic_ir_keol_projection.py`

**Steps:**
1. Add `project-semantic-ir-slice-to-keol` CLI using the existing real-slice diagnostic suite.
2. Write immutable JSON artifact to `artifacts/natural-benchmark-slices/slice-v1/semantic-ir-keol-projection.json`.
3. The artifact must state scope: adapter contract only, no KEOL baseline mutation, no model extraction.

## Acceptance criteria

- Projection is deterministic and JSON-compatible with KEOL core object names.
- Every assertion has evidence or derived assertion provenance.
- Source status/lifecycle/closure metadata is preserved.
- Existing semantic IR tests and natural benchmark validation remain green.
