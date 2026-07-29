# Real Slice Semantic IR Mapping Implementation Plan

**Goal:** Map a small fixed set of real `slice-v1` benchmark items into the event-role-evidence semantic IR and compare the deterministic IR result with the current `symbolic_fallback_answerability_v2` behavior.

**Architecture:** Add an isolated real-slice diagnostic runner under `tools/natural_memory_benchmark/`. It remains hand-authored and deterministic: no model extraction, no new benchmark scoring contract, no external memory-system reruns. The runner consumes frozen `slice.json`, `gold.json`, `evidence-corpus.json`, and current results, builds semantic IR fixtures for selected item IDs, executes `execute_query`, and writes a machine JSON plus Markdown report.

**Tech Stack:** Python 3.13, Pydantic v2 semantic IR models, pytest, immutable JSON artifacts.

---

## Task 1: RED tests for real-slice semantic IR diagnostics

**Files:**
- Create: `tests/natural_memory_benchmark/test_semantic_ir_slice_runner.py`

**Steps:**
1. Add tests that import `build_real_slice_diagnostic_suite`, `run_real_slice_semantic_ir_diagnostics`, and `render_real_slice_semantic_ir_report`.
2. Assert the suite contains five fixed real slice item IDs:
   - `BEAM-100K-C001-abstention-001`
   - `LONGMEMEVAL-6d550036`
   - `BEAM-100K-C001-contradiction_resolution-001`
   - `BEAM-100K-C001-knowledge_update-002`
   - `LONGMEMEVAL-gpt4_2655b836`
3. Assert run metrics: 5 cases, 5 pass, 5 IR evidence-exact, 3 existing evidence-exact, 2 IR evidence-exact improvements, 1 existing fallback, 0 IR fallback allowed, 1 IR abstention.
4. Add a CLI test for `run-semantic-ir-slice-diagnostics`.

## Task 2: GREEN real-slice diagnostic runner

**Files:**
- Create: `tools/natural_memory_benchmark/semantic_ir_slice_runner.py`
- Modify: `tools/natural_memory_benchmark/cli.py`

**Steps:**
1. Implement helpers that find public/gold/result/corpus units by item ID.
2. Build L1/L2/Closure/QuerySlotPlan records for the five selected cases.
3. Execute `execute_query` and compare IR evidence refs against gold refs.
4. Render Markdown with per-case existing behavior vs IR behavior.
5. Register CLI:
   `run-semantic-ir-slice-diagnostics --root <root> --slice-id slice-v1 --results <path> --output <json> --report <md> --run-id <id>`.

## Task 3: Generate formal artifacts and verify

**Files:**
- Create: `artifacts/natural-benchmark-slices/slice-v1/semantic-ir-slice-diagnostic-results.json`
- Create: `artifacts/natural-benchmark-slices/slice-v1/semantic-ir-slice-diagnostic-report.md`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `安排.md`

**Verification:**

```powershell
D:\Anaconda\python.exe -m pytest tests\natural_memory_benchmark\test_semantic_ir_slice_runner.py -q --import-mode=importlib -p no:cacheprovider --basetemp .t\bm-semantic-ir-slice-runner
D:\Anaconda\python.exe -m pytest tests\natural_memory_benchmark -q --import-mode=importlib -p no:cacheprovider --basetemp .t\bm-semantic-ir-slice-all
D:\Anaconda\python.exe -m tools.natural_memory_benchmark.cli validate-slice --root artifacts\natural-benchmark-slices --slice-id slice-v1
D:\Anaconda\python.exe -m tools.natural_memory_benchmark.cli validate-ledger --path artifacts\natural-benchmark-slices\external-results-ledger.json
```

## Acceptance criteria

- The runner maps real frozen slice items, not synthetic examples.
- The mapping remains hand-authored and diagnostic-only.
- The IR blocks the known causal unanswerable case without fallback.
- The IR recovers exact evidence for the existing lexical fallback item without needing fallback.
- The IR exposes two evidence-boundary improvements over the current shallow symbolic arm.
- No slice/gold contract is modified.
