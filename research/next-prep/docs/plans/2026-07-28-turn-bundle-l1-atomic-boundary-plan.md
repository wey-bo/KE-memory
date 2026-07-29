# TurnBundle and L1 Atomic Boundary Implementation Plan

**Goal:** Add a representation-neutral contract that makes one user/assistant turn the transaction and evidence-package boundary while allowing that turn to publish zero or more atomic L1 event/state units.

**Architecture:** Introduce a standalone `TurnBundleRevision` beside the frozen authoritative v3/v5 models. The bundle references immutable source revisions and L1 unit revisions, validates all evidence stays inside the turn, and prevents failed extraction from publishing partial L1 membership. No existing schema, CLI, identity path, frozen artifact, or shared fact-source document is modified.

**Tech Stack:** Python 3.13, Pydantic v2, canonical JSON/SHA-256, pytest 8.

---

### Task 1: Specify the boundary with RED tests

**Files:**

- Create: `tests/natural_memory_benchmark/test_turn_bundle.py`

**Steps:**

1. Test that one ordered user/assistant source package can own multiple atomic L1 revisions.
2. Test that a complete zero-memory extraction requires an explicit reason.
3. Test that failed extraction cannot expose partial L1 membership.
4. Test ordered source records, required user/assistant roles, evidence containment, and payload-hash integrity.
5. Run:

   ```bash
   PYTHONDONTWRITEBYTECODE=1 .venv-h100/bin/python -m pytest \
     -p no:cacheprovider tests/natural_memory_benchmark/test_turn_bundle.py \
     -q --basetemp=/tmp/ke-memory-turn-bundle-red
   ```

   Expected: collection fails because `tools.natural_memory_benchmark.turn_bundle` does not exist.

### Task 2: Implement the isolated contract

**Files:**

- Create: `tools/natural_memory_benchmark/turn_bundle.py`

**Steps:**

1. Add immutable `TurnSourceRevisionRef` and `TurnBundleRevision` models.
2. Add `make_turn_bundle_revision` with deterministic payload/revision hashes.
3. Enforce state invariants for `raw_only`, `complete`, and `failed` extraction.
4. Add `validate_turn_bundle_closure` against existing source and memory-unit revisions.
5. Require all L1 evidence and declared source revisions to remain inside the same turn/session package.
6. Run the focused test and require all cases to pass.

### Task 3: Verify non-interference

**Steps:**

1. Run the new focused test with workspace bytecode/cache disabled.
2. Run existing authoritative and representation-contract tests with the same isolation flags.
3. Verify no existing frozen artifact was modified and no new writable file appeared under identity experiment paths.
4. Hand the standalone contract to the H100 plugin for later adapter/transaction-store integration; do not register a CLI or alter the identity shadow queue in this wave.

No Git/worktree step applies because the H100 preparation workspace is not a valid Git repository.
