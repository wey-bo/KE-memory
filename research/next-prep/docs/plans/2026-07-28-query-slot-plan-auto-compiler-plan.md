# QuerySlotPlan Automatic Compiler Implementation Plan

**Goal:** Build a versioned, representation-neutral compiler core that turns a structured
natural-query draft into a gated executable retrieval plan or explicit abstention, without
changing the existing memory, query, recall, or representation core.

**Architecture:** Add a separate V2 compiler module with strict Pydantic contracts, deterministic
linking and gate rules, canonical hashing, and conservative lowering to the existing
`AuthoritativeQueryPlan`. Add an independent evaluation module after the compiler core is stable.

**Tech Stack:** Python 3.13, Pydantic v2, pytest, existing canonical JSON and authoritative query
contracts.

---

## Workspace and concurrency constraints

- H100 root: `/public/home/wwb/KE-mem/KE-memory-next-prep-20260727`.
- The workspace `.git` directory is intentionally empty. Do not initialize Git, create a
  worktree, or claim commit/SHA review.
- Server Codex currently owns `typed_extractor_fresh_*`, its tests, and fresh-hidden artifacts.
- This plan owns only the new query compiler files listed below until server work becomes idle.
- Existing `semantic_ir.py`, `authoritative_memory.py`, `cli.py`, README, and AGENTS remain
  unchanged during the isolated compiler-core wave.

### Task 1: Freeze the compiler contract with failing tests

**Files:**

- Create: `tests/natural_memory_benchmark/test_query_compiler_v2.py`
- Create: `tools/natural_memory_benchmark/query_compiler_v2.py`

**Steps:**

1. Write tests for strict round-trip validation, memory/ontology/identity revision binding,
   deterministic plan hashing, answer-variable validation, and OR-of-AND pattern groups.
2. Run:

   ```bash
   .venv-h100/bin/python -m pytest \
     tests/natural_memory_benchmark/test_query_compiler_v2.py -q \
     --basetemp=/tmp/ke-memory-query-compiler-v2-red
   ```

   Expected: import failure because `query_compiler_v2.py` does not exist.
3. Implement the minimal strict models and canonical hash helper.
4. Re-run the focused test and require pass.

### Task 2: Implement deterministic linking and gate safety

**Files:**

- Modify: `tools/natural_memory_benchmark/query_compiler_v2.py`
- Modify: `tests/natural_memory_benchmark/test_query_compiler_v2.py`

**Steps:**

1. Add failing tests for:
   - unresolved structural predicate blocks execution;
   - lexical predicate/entity gap may allow guarded fallback;
   - count requires canonical-identity distinctness and resolved identities;
   - latest/current requires valid-time ordering and active lifecycle;
   - explicit absence requires an explicit-absence evidence policy;
   - disconnected multi-hop variables are rejected;
   - modality, conflict, and answerability failures block embedding fallback.
2. Run the focused test and confirm the new assertions fail for missing behavior.
3. Implement `compile_query_draft()` and deterministic gate helpers with no network access.
4. Re-run focused tests and require pass.

### Task 3: Add conservative V1 lowering

**Files:**

- Modify: `tools/natural_memory_benchmark/query_compiler_v2.py`
- Modify: `tests/natural_memory_benchmark/test_query_compiler_v2.py`

**Steps:**

1. Add failing tests proving a simple single-atom plan lowers without semantic loss.
2. Add failing tests proving OR, multi-hop, unsupported aggregation, and explicit-absence plans
   refuse V1 lowering.
3. Implement `lower_to_authoritative_query_plan()` using the existing immutable models.
4. Verify lowered plan fields and fallback restrictions exactly match the accepted V2 plan.

### Task 4: Add producer boundary and natural-query entry point

**Files:**

- Modify: `tools/natural_memory_benchmark/query_compiler_v2.py`
- Modify: `tests/natural_memory_benchmark/test_query_compiler_v2.py`

**Steps:**

1. Add a `QueryDraftProducer` protocol and `compile_natural_query()` orchestration function.
2. Test with an isolated fake producer that only receives raw question, public query context, and
   compiler policy revision.
3. Prove producer output cannot mark itself executable or inject stable linked IDs outside the
   deterministic registry input.
4. Do not add an API/model runner in this task; the compiler contract must qualify first.

### Task 5: Adjacent regression verification

Run:

```bash
.venv-h100/bin/python -m pytest \
  tests/natural_memory_benchmark/test_query_compiler_v2.py \
  tests/natural_memory_benchmark/test_authoritative_memory.py \
  tests/natural_memory_benchmark/test_representation_contract.py \
  tests/natural_memory_benchmark/test_identity_resolution.py \
  -q --basetemp=/tmp/ke-memory-query-compiler-v2-adjacent
```

Then run `compileall` and `tabnanny` on the new module. Do not start the full suite while server
Codex is running a fresh-hidden full regression. After its wave is idle, run the complete
`tests/natural_memory_benchmark` suite once with a unique `/tmp` basetemp.

### Task 6: Follow-on evaluation wave

After the compiler core passes and server fresh-hidden work is complete, create separate files:

- `tools/natural_memory_benchmark/query_compiler_v2_eval.py`
- `tests/natural_memory_benchmark/test_query_compiler_v2_eval.py`
- a frozen dev query slice and independent gold plans;
- a preregistration contract before any compiler fresh-hidden queries are authored.

Raw producer quality and deterministic gate safety must remain separate. This follow-on wave may
add a model runner, immutable proposals/provenance, scorer, CLI, and reports, but it still cannot
authorize memory writes or natural-language answer generation.

