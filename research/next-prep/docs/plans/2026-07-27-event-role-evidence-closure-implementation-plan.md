# Event-Role-Evidence Closure Minimal Implementation Plan

**Goal:** Build a minimal, testable AMR-style event-role-evidence closure IR that supports L1 atomic memory units, L2 derived abstractions, closure validation, and query execution over small diagnostic fixtures.

**Architecture:** Add an isolated `semantic_ir.py` module under `tools/natural_memory_benchmark/` as an experimental logical representation carrier without selecting a persistence backend. The module defines strict Pydantic contracts plus deterministic in-memory execution over hand-authored IR records. The first implementation proves structure, closure, and answerability behavior before any model-based extraction or representation selection.

**Tech Stack:** Python 3.13, Pydantic v2, pytest, immutable JSON-compatible dict models.

---

## Task 1: IR data contracts

**Files:**
- Create: `tools/natural_memory_benchmark/semantic_ir.py`
- Create: `tests/natural_memory_benchmark/test_semantic_ir.py`

**Step 1: Write failing tests**

Add tests that import:

```python
from tools.natural_memory_benchmark.semantic_ir import (
    ClosureRecord,
    EvidenceSpan,
    L1MemoryUnit,
    L2MemoryUnit,
    Predicate,
    QuerySlotPlan,
    RoleBinding,
    SourceBinding,
)
```

Tests must assert:

- L1 records require at least one evidence span;
- L2 records require `abstracts`, `closure_id`, and provenance source L1 units;
- predicate `surface`, `sense`, and `canonical_operator` are preserved;
- extra fields are rejected.

**Step 2: Verify RED**

Run:

```powershell
D:\Anaconda\python.exe -m pytest tests\natural_memory_benchmark\test_semantic_ir.py -q --import-mode=importlib -p no:cacheprovider --basetemp .t\bm-semantic-ir-red
```

Expected: import error for `tools.natural_memory_benchmark.semantic_ir`.

**Step 3: Implement minimal contracts**

Create strict Pydantic models:

- `Predicate(surface, sense, canonical_operator)`
- `RoleBinding(role, entity_id, role_name)`
- `EvidenceSpan(evidence_id, turn_id, session_id, char_start, char_end, text)`
- `SourceBinding(speaker, source_status, evidence_spans)`
- `TimeBinding(event_time, valid_time, transaction_time)`
- `EpistemicBinding(extraction_confidence, epistemic_trust, memory_utility)`
- `LinkBinding(same_as, supersedes, conflicts_with, derived_from)`
- `L1MemoryUnit`
- `L2MemoryUnit`
- `ClosureRequirement(unit_id, role)`
- `ClosureRecord`
- `QuerySlotPlan`

Use `extra="forbid"` and frozen models. Validate required closure/provenance relationships at model level.

**Step 4: Verify GREEN**

Run the same focused test command; expect pass.

## Task 2: Closure execution

**Files:**
- Modify: `tools/natural_memory_benchmark/semantic_ir.py`
- Modify: `tests/natural_memory_benchmark/test_semantic_ir.py`

**Step 1: Write failing tests**

Add tests for:

- `single_fact` closure is complete when all required L1 IDs exist;
- `multi_evidence_set` is incomplete when any required evidence unit is missing;
- `causal_answerability` requires cause, effect, and causal link roles;
- structural missing slots block fallback;
- lexical/evidence candidate missing slots allow guarded fallback.

**Step 2: Verify RED**

Run focused tests and confirm missing function failures.

**Step 3: Implement minimal execution**

Add:

```python
def evaluate_closure(closure: ClosureRecord, available_unit_ids: set[str]) -> ClosureRecord
```

and:

```python
def fallback_allowed_for_closure(closure: ClosureRecord) -> bool
```

`evaluate_closure` returns a new `ClosureRecord` with `complete` and `missing_slots` set deterministically. `fallback_allowed_for_closure` returns true only for missing slots with roles in `{"unresolved_entity", "lexical_predicate_missing_link", "incomplete_evidence_slot"}`.

**Step 4: Verify GREEN**

Run focused tests; expect pass.

## Task 3: Query execution over hand-authored IR

**Files:**
- Modify: `tools/natural_memory_benchmark/semantic_ir.py`
- Modify: `tests/natural_memory_benchmark/test_semantic_ir.py`

**Step 1: Write failing tests**

Add tests for five diagnostic scenarios:

1. `led/manage` matches project leadership but not causal `led-to`.
2. `led-to/cause` matches causal query.
3. feedback causal answerability abstains when no causal link unit exists.
4. multi-session closure requires all project evidence units.
5. preference supersession returns only active current preference.

**Step 2: Verify RED**

Run focused tests and confirm failures from missing executor.

**Step 3: Implement minimal executor**

Add:

```python
def execute_query(plan: QuerySlotPlan, l1_units: list[L1MemoryUnit], l2_units: list[L2MemoryUnit], closures: list[ClosureRecord]) -> QueryResult
```

`QueryResult` returns:

- `matched_unit_ids`
- `required_evidence_ids`
- `closure_complete`
- `abstained`
- `missing_slots`
- `fallback_allowed`
- `reason`

The executor should match by canonical operator, predicate sense, role constraints, lifecycle, and closure ID. It should not do fuzzy lexical matching.

**Step 4: Verify GREEN**

Run focused tests; expect pass.

## Task 4: Status documentation and verification

**Files:**
- Modify: `AGENTS.md`
- Modify: `安排.md`
- Modify: `README.md`

**Step 1: Update status**

Record:

- new module path;
- test path;
- diagnostic scenarios covered;
- verification command and result;
- explicit limitation: hand-authored IR only, no model extraction and no benchmark expansion.

**Step 2: Verify**

Run:

```powershell
D:\Anaconda\python.exe -m pytest tests\natural_memory_benchmark\test_semantic_ir.py -q --import-mode=importlib -p no:cacheprovider --basetemp .t\bm-semantic-ir-focused
D:\Anaconda\python.exe -m pytest tests\natural_memory_benchmark -q --import-mode=importlib -p no:cacheprovider --basetemp .t\bm-semantic-ir-all
D:\Anaconda\python.exe -m tools.natural_memory_benchmark.cli validate-slice --root artifacts\natural-benchmark-slices --slice-id slice-v1
D:\Anaconda\python.exe -m tools.natural_memory_benchmark.cli validate-ledger --path artifacts\natural-benchmark-slices\external-results-ledger.json
```

Expected:

- focused semantic IR tests pass;
- all natural benchmark tests pass;
- slice and ledger remain valid.

## Acceptance criteria

- The IR enforces evidence-backed L1 and derived-from L2 records.
- Closure completeness is deterministic and test-covered.
- Structural missing slots cannot be repaired by embedding fallback.
- Lexical/evidence missing slots can be flagged as fallback-eligible.
- The five diagnostic scenarios are represented without dense retrieval.
- No existing benchmark slice/gold contract is changed.
