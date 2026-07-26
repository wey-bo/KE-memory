# Ontology Agent Memory A+B Implementation Plan

**Goal:** Add a complete online A+B memory vertical slice with atomic KEOL-backed writes,
symbolic-first retrieval, user correction/forgetting, warmup context, and an HTTP API.

**Architecture:** Preserve the existing research pipeline and add an independent `online` package.
The online package uses a repository protocol with a SQLite WAL implementation, wraps the existing
Turn KE and lifecycle components, compiles admitted records into KEOL-compatible bundles, and
exposes FastAPI endpoints. Embedding remains an injected guarded fallback port.

**Tech Stack:** Python 3.12, Pydantic 2, SQLite/WAL, existing KE extraction/retrieval components,
FastAPI, HTTPX, pytest, Ruff, Pyright.

---

### Task 1: Online domain and admission contract

**Files:**
- Create: `src/ke_memory_demo/online/models.py`
- Create: `src/ke_memory_demo/online/admission.py`
- Create: `src/ke_memory_demo/online/__init__.py`
- Test: `tests/unit/online/test_admission.py`

1. Write failing tests for namespace validation, user/tool/agent source status, preference and task
   admission, and the separation of extraction confidence, epistemic trust, and memory utility.
2. Run `pytest tests/unit/online/test_admission.py -q` and verify RED.
3. Implement frozen Pydantic records and an explicit rule table. Agent-generated facts remain
   candidates; user preferences/tasks and tool-observed states are admitted.
4. Run the focused tests and then the existing domain tests.
5. Commit `feat: add online memory admission contract`.

### Task 2: KEOL bundle compiler

**Files:**
- Create: `src/ke_memory_demo/online/keol_bridge.py`
- Test: `tests/contract/test_online_keol_bridge.py`

1. Write failing contract tests that load KEOL `onto.models` from the fixed `44631e6` source and
   validate emitted Concept, Individual, Operator, Assertion, Evidence, and WorkflowRun objects.
2. Run the contract test with `PYTHONPATH=/public/home/wwb/KE_mem/KEOL/src` and verify RED.
3. Implement deterministic expression-to-Term conversion, stable hashes/slugs, exact evidence
   conversion, and a closed bundle validator.
4. Verify malformed or dangling references fail locally.
5. Commit `feat: compile online memories into KEOL bundles`.

### Task 3: Atomic SQLite repository

**Files:**
- Create: `src/ke_memory_demo/online/repository.py`
- Test: `tests/unit/online/test_repository.py`

1. Write failing tests for schema creation, WAL/foreign keys, idempotent turn writes, mismatched
   idempotency rejection, transaction rollback, current revision selection, links, correction,
   tombstones, namespace isolation, and evidence retrieval.
2. Verify RED.
3. Implement the repository protocol and `SQLiteOnlineMemoryRepository` using explicit
   transactions and canonical JSON payloads.
4. Verify focused tests and SQLite integrity checks.
5. Commit `feat: add atomic online memory repository`.

### Task 4: Online extraction and lifecycle service

**Files:**
- Create: `src/ke_memory_demo/online/extractor.py`
- Create: `src/ke_memory_demo/online/service.py`
- Test: `tests/unit/online/test_service.py`

1. Write failing tests using injected extractor/lifecycle fakes for raw-turn preservation,
   admission, KEOL compilation, task state supersession, preference persistence, tool provenance,
   agent-generated fact protection, and atomic failure behavior.
2. Verify RED.
3. Implement `OnlineTurnExtractor` protocol, adapter for `TurnKEExtractor`, optional lifecycle
   adapter, and `OntologyMemoryService` orchestration.
4. Verify focused tests.
5. Commit `feat: orchestrate online ontology memory writes`.

### Task 5: Symbolic-first search and warmup context

**Files:**
- Create: `src/ke_memory_demo/online/retrieval.py`
- Test: `tests/unit/online/test_retrieval.py`

1. Write failing tests for current task/preference retrieval, lifecycle and time filtering,
   conflict visibility, evidence closure, slot completeness, no fallback on exact structural
   matches, and fallback only for unresolved entity/predicate slots.
2. Verify RED.
3. Implement deterministic symbolic scoring and an injected `EmbeddingFallback` protocol.
4. Implement context selection for active tasks, constraints, preferences, changes, and conflicts.
5. Commit `feat: add symbolic-first online retrieval`.

### Task 6: HTTP API and runtime factory

**Files:**
- Create: `src/ke_memory_demo/online/api.py`
- Create: `src/ke_memory_demo/online/factory.py`
- Create: `config/online.toml`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Test: `tests/integration/test_online_memory_api.py`

1. Add FastAPI and Uvicorn dependencies and sync the isolated environment.
2. Write failing HTTP tests for health, add, search, context, correction, get, delete, validation,
   and namespace isolation.
3. Implement an app factory and dependency-injected service. Do not perform model/network calls at
   import time.
4. Add `ke-memory-serve` entry point and verify API tests.
5. Commit `feat: expose ontology memory HTTP API`.

### Task 7: Documentation and full verification

**Files:**
- Modify: `README.md`
- Create: `docs/online-memory-api.md`

1. Document local configuration, KEOL source pin, service startup, API examples, state layout,
   trust/admission rules, and the guarded fallback boundary.
2. Run `ruff check src tests` and `pyright`.
3. Run the full pytest suite.
4. Start the server on an unused localhost port and run a health/add/search/context smoke sequence.
5. Verify `git diff --check`, secret hygiene, and remote worktree status.
6. Commit `docs: document ontology memory service`.
