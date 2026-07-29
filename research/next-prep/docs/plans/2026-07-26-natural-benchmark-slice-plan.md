# Natural Benchmark Small-Slice Implementation Plan

**Goal:** Freeze and validate a small natural benchmark slice for BEAM, LoCoMo, and LongMemEval, with source/gold separation and external author results kept contextual only.

**Architecture:** Add a separate `tools/natural_memory_benchmark/` package so natural benchmark slicing does not pollute the controlled ontology-memory experiment runner. The package reads official raw source snapshots, emits a leakage-safe `slice.json`, keeps answers/evidence in `gold.json`, and validates an external-results ledger without rerunning named memory systems.

**Tech Stack:** Python 3.13, pytest, DuckDB for BEAM parquet, built-in JSON/hashlib/pathlib, immutable UTF-8 JSON artifacts.

---

## Non-negotiable boundaries

- Do not copy code, tests, or evaluation logic from the old Fusion Memory project.
- Do not rerun Mem0, Graphiti, Hindsight, MemPalace, Zep, or other external memory systems.
- Keep `slice.json` free of answers, evidence references, rubrics, adversarial answers, and score labels.
- Keep `gold.json` separate and bind it to the same source manifest.
- Treat LoCoMo category 5 as `manual_required` for answer scoring because the source provides `adversarial_answer` but no explicit gold answer.
- Do not claim full benchmark performance from slice v1.
- Current `.git` is not a real repository, so no worktree or commit steps are available.

## Test list

1. Source manifest records exact path, size, SHA-256, official URL, frozen identity, and reader requirements for all three raw sources.
2. BEAM loader reads the official parquet through DuckDB and extracts 400 probing questions with stable categories.
3. LoCoMo loader extracts 1,986 QA candidates and marks category 5 candidates as `manual_required`.
4. LongMemEval loader extracts 500 oracle candidates with question type, answer, answer session IDs, and haystack session IDs.
5. Slice selector returns 10 BEAM, 10 LoCoMo, and 12 LongMemEval items under the v1 policy.
6. `slice.json` excludes all gold-only fields; `gold.json` contains only known answers/evidence or explicit `manual_required`.
7. External results ledger validates comparability status and forbids local scores for unrun systems.
8. CLI commands `freeze-slice`, `validate-slice`, and `validate-ledger` are deterministic and refuse incompatible overwrites.

### Task 1: Contracts and source manifest

**Files:**
- Create: `tools/natural_memory_benchmark/__init__.py`
- Create: `tools/natural_memory_benchmark/models.py`
- Create: `tools/natural_memory_benchmark/io.py`
- Create: `tests/natural_memory_benchmark/test_contracts.py`

**Step 1: Write failing tests**

Tests assert source hash binding, source/answer separation, `manual_required` semantics, immutable JSON writes, and rejection of gold fields inside slice items.

**Step 2: Verify RED**

Run:

```powershell
D:\Anaconda\python.exe -m pytest tests\natural_memory_benchmark\test_contracts.py -q --import-mode=importlib -p no:cacheprovider --basetemp .t\nbm-contracts-red
```

Expected: import failure for `tools.natural_memory_benchmark`.

**Step 3: Implement minimal contracts**

Use small dataclasses or Pydantic models with explicit `to_public_slice_item()` and `to_gold_item()` boundaries. `write_json_immutable()` allows byte-identical replay and refuses different content.

**Step 4: Verify GREEN**

Run the same command with `.t\nbm-contracts-green`; expect pass.

### Task 2: Benchmark source loaders

**Files:**
- Create: `tools/natural_memory_benchmark/loaders.py`
- Create: `tests/natural_memory_benchmark/test_loaders.py`

**Step 1: Write failing loader tests**

Tests use the real frozen raw files:

- BEAM: 20 conversations and 400 questions; required categories include the five slice categories.
- LoCoMo: 10 samples and 1,986 questions; category 5 has `manual_required`.
- LongMemEval: 500 questions and the six known question types.

**Step 2: Verify RED**

Run:

```powershell
D:\Anaconda\python.exe -m pytest tests\natural_memory_benchmark\test_loaders.py -q --import-mode=importlib -p no:cacheprovider --basetemp .t\nbm-loaders-red
```

**Step 3: Implement loaders**

Read BEAM with DuckDB and `ast.literal_eval()` for `probing_questions`; read LoCoMo and LongMemEval with JSON. Normalize evidence references into benchmark-local strings without resolving them to text yet.

**Step 4: Verify GREEN**

Run the focused loader tests.

### Task 3: Slice selection and freeze

**Files:**
- Create: `tools/natural_memory_benchmark/slices.py`
- Create: `tests/natural_memory_benchmark/test_slices.py`
- Create by CLI: `artifacts/natural-benchmark-slices/source-manifest.json`
- Create by CLI: `artifacts/natural-benchmark-slices/slice-v1/slice.json`
- Create by CLI: `artifacts/natural-benchmark-slices/slice-v1/gold.json`

**Step 1: Write failing selector tests**

Tests assert exact item counts, quotas, deterministic item IDs, no leakage fields in `slice.json`, gold coverage for every item, and `manual_required` only where source gold is absent.

**Step 2: Verify RED**

Run:

```powershell
D:\Anaconda\python.exe -m pytest tests\natural_memory_benchmark\test_slices.py -q --import-mode=importlib -p no:cacheprovider --basetemp .t\nbm-slices-red
```

**Step 3: Implement selector and freeze writer**

Apply the v1 policy from `docs/designs/2026-07-26-natural-benchmark-slice-design.md`. Write artifacts immutably and bind them to the source manifest hash.

**Step 4: Verify GREEN**

Run focused tests, then freeze:

```powershell
D:\Anaconda\python.exe -m tools.natural_memory_benchmark.cli freeze-slice --root artifacts\natural-benchmark-slices --slice-id slice-v1
```

### Task 4: External results ledger

**Files:**
- Create: `tools/natural_memory_benchmark/ledger.py`
- Create: `tests/natural_memory_benchmark/test_ledger.py`
- Create by CLI: `artifacts/natural-benchmark-slices/external-results-ledger.json`

**Step 1: Write failing ledger tests**

Tests require official source URLs, benchmark/version fields, metric definitions, `external_context_only` comparability, and `local_rerun=false` for all named systems.

**Step 2: Verify RED**

Run:

```powershell
D:\Anaconda\python.exe -m pytest tests\natural_memory_benchmark\test_ledger.py -q --import-mode=importlib -p no:cacheprovider --basetemp .t\nbm-ledger-red
```

**Step 3: Implement ledger validator and static v1 writer**

Reuse the facts already frozen in `artifacts/ontology-memory-experiment/reports/external-context.md` only as source context; the new JSON ledger remains machine-readable and explicitly non-comparable to the local slice unless protocol identity is proven.

**Step 4: Verify GREEN**

Run focused ledger tests.

### Task 5: CLI and integration verification

**Files:**
- Create: `tools/natural_memory_benchmark/cli.py`
- Create: `tests/natural_memory_benchmark/test_cli.py`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `安排.md`

**Step 1: Write failing CLI tests**

Tests cover `freeze-slice`, `validate-slice`, `validate-ledger`, source hash mismatch detection, deterministic replay, and immutable overwrite refusal.

**Step 2: Verify RED**

Run:

```powershell
D:\Anaconda\python.exe -m pytest tests\natural_memory_benchmark\test_cli.py -q --import-mode=importlib -p no:cacheprovider --basetemp .t\nbm-cli-red
```

**Step 3: Implement CLI**

Expose commands:

```powershell
D:\Anaconda\python.exe -m tools.natural_memory_benchmark.cli freeze-slice --root artifacts\natural-benchmark-slices --slice-id slice-v1
D:\Anaconda\python.exe -m tools.natural_memory_benchmark.cli validate-slice --root artifacts\natural-benchmark-slices --slice-id slice-v1
D:\Anaconda\python.exe -m tools.natural_memory_benchmark.cli validate-ledger --path artifacts\natural-benchmark-slices\external-results-ledger.json
```

**Step 4: Verify final state**

Run:

```powershell
D:\Anaconda\python.exe -m pytest tests\natural_memory_benchmark -q --import-mode=importlib -p no:cacheprovider --basetemp .t\nbm-focused-final
D:\Anaconda\python.exe -m tools.natural_memory_benchmark.cli validate-slice --root artifacts\natural-benchmark-slices --slice-id slice-v1
D:\Anaconda\python.exe -m tools.natural_memory_benchmark.cli validate-ledger --path artifacts\natural-benchmark-slices\external-results-ledger.json
```

Expected: tests pass; source manifest validates; slice has 32 items; gold has matching 32 items; no named external system has a local score.
