# AMR Single-Sentence Pilot Implementation Plan

**Goal:** Build and run the approved 12-sentence A/B/C pilot that compares direct standard AMR, knowledge-first AMR, and atomic knowledge while preserving source provenance and measuring semantic quality and efficiency.

**Architecture:** Keep experiment code in `tools/amr_pilot/` and immutable inputs, prompts, raw attempts, sidecars, gold, and reports in `artifacts/amr-pilot/`. Python prepares isolated payloads and deterministically validates, blinds, scores, and reports; the user-authorized balanced `gpt-5.6-terra` subagent performs semantic generation only after the user approves gold and the runtime records the exact model and usage telemetry status.

**Tech Stack:** Python 3.13, Pydantic 2, pytest 8, `penman` pinned after package-index verification, JSON/Markdown artifacts, Codex subagents for model generation.

---

The pre-change baseline is:

```powershell
D:\Anaconda\python.exe -m pytest tests -q -p no:cacheprovider --basetemp .pytest-tmp-amr-baseline-20260724
# 241 passed
```

The workspace has an empty `.git` directory rather than a usable repository. Worktree and commit steps are intentionally omitted; no Git initialization is authorized.

### Task 1: Define the Strict Experiment Contracts

**Files:**
- Create: `tools/amr_pilot/__init__.py`
- Create: `tools/amr_pilot/models.py`
- Create: `tests/amr_pilot/test_models.py`

**Step 1: Write failing model tests**

Cover these behaviors independently:

- sample IDs use `AMR-S001` format;
- route is exactly `A`, `B`, or `C`;
- source text is non-blank English and has a matching SHA-256;
- phenomenon is one of the four approved strata;
- gold items have an explicit positive weight and `critical`/`ordinary` importance;
- sidecars distinguish measured usage from explicitly unavailable usage;
- attempt number is 1 or 2 and attempt 2 references attempt 1;
- extra fields are rejected.

**Step 2: Verify RED**

```powershell
D:\Anaconda\python.exe -m pytest tests/amr_pilot/test_models.py -q -p no:cacheprovider --basetemp .t\amr-models-red
```

Expected: collection fails because `tools.amr_pilot.models` does not exist.

**Step 3: Implement the minimal Pydantic models**

Use `ConfigDict(extra="forbid")`, strict enums/literals, and model validators for hash and attempt invariants. Do not add query, retrieval, embedding, summary, KEOL, or benchmark fields.

**Step 4: Verify GREEN**

Run the same test command and expect all tests in the file to pass.

### Task 2: Recover and Validate the 12 English Inputs

**Files:**
- Create: `tools/amr_pilot/inputs.py`
- Create: `tests/amr_pilot/test_inputs.py`
- Create after source recovery: `artifacts/amr-pilot/inputs/sentences.json`
- Create after source recovery: `artifacts/amr-pilot/inputs/manifest.json`
- Create after source recovery: `artifacts/amr-pilot/inputs/source-records.json`

**Step 1: Write failing input-set tests**

Test that the loader:

- requires exactly 12 unique English sentences;
- requires exactly 3 samples in each approved phenomenon stratum;
- rejects duplicate text hashes and corrected/paraphrased source text;
- requires a KE-test candidate ID and an exact public-source coordinate;
- writes a deterministic manifest with source-record, sentence, and complete-set hashes;
- refuses stale managed files rather than deleting or overwriting them.

Use synthetic English fixtures only; do not use selected experiment sentences in unit tests.

**Step 2: Verify RED, implement minimally, and verify GREEN**

```powershell
D:\Anaconda\python.exe -m pytest tests/amr_pilot/test_inputs.py -q -p no:cacheprovider --basetemp .t\amr-inputs
```

**Step 3: Recover source records from authorized public sources**

Use the coordinates in `data/gold-candidates/KE-test-config.md`. Prefer the smallest official files that contain Taskmaster-2, tau-bench, or BEAM candidates; download the WildChat shard only if needed for the approved semantic strata. Preserve downloaded-record hashes and exact message/utterance indices. Do not reconstruct English by translating the Chinese display text.

**Step 4: Select 12 candidate sentences**

Choose one complete source sentence per sample, with three samples per stratum. Exclude text that requires previous-turn context or combines tool calls/results. Generate `sentences.json` and a provenance manifest, then run the input validator.

### Task 3: Prepare the Independent Gold Candidate

**Files:**
- Create: `tools/amr_pilot/gold.py`
- Create: `tests/amr_pilot/test_gold.py`
- Create: `artifacts/amr-pilot/gold/semantic-checklists.draft.json`
- Create only after user approval: `artifacts/amr-pilot/gold/approval.json`

**Step 1: Write failing gold tests**

Test exact sample coverage, unique item IDs, positive explicit weights, evidence substrings, critical error categories, forbidden-inference entries, and refusal to mark gold approved without a separate approval record matching the draft hash.

**Step 2: Verify RED, implement, and verify GREEN**

```powershell
D:\Anaconda\python.exe -m pytest tests/amr_pilot/test_gold.py -q -p no:cacheprovider --basetemp .t\amr-gold
```

**Step 3: Generate and review the draft**

Create a human-readable draft directly from the 12 original English sentences. Do not read route output, current `final-knowledge.json`, or KEOL output. Present the full draft to the user. Write `approval.json` only after explicit confirmation; its SHA-256 must bind the exact draft.

### Task 4: Version the Three Prompts and Isolated Payloads

**Files:**
- Create: `artifacts/amr-pilot/prompts/direct-amr-v1.md`
- Create: `artifacts/amr-pilot/prompts/atomic-knowledge-v1.md`
- Create: `artifacts/amr-pilot/prompts/knowledge-to-amr-v1.md`
- Create: `tools/amr_pilot/payloads.py`
- Create: `tests/amr_pilot/test_payloads.py`

**Step 1: Write failing payload tests**

Assert that A sees only the sentence and AMR contract, C sees only the sentence and atomic-knowledge contract, and B sees only the validated C output plus the AMR contract. Assert that no route sees gold, other sentences, Chinese display text, current extraction results, KEOL artifacts, query rules, or benchmark fields. Assert prompt and payload hashes in the manifest.

**Step 2: Verify RED, implement, and verify GREEN**

```powershell
D:\Anaconda\python.exe -m pytest tests/amr_pilot/test_payloads.py -q -p no:cacheprovider --basetemp .t\amr-payloads
```

### Task 5: Add Standard PENMAN Validation and Immutable Attempts

**Files:**
- Create: `tools/amr_pilot/penman_validation.py`
- Create: `tools/amr_pilot/run_ledger.py`
- Create: `tests/amr_pilot/test_penman_validation.py`
- Create: `tests/amr_pilot/test_run_ledger.py`
- Create after dependency verification: `tools/amr_pilot/requirements.txt`

**Step 1: Verify and pin `penman`**

Query the package index, pin the exact selected version in `requirements.txt`, and install it into the experiment environment. Do not hand-roll a PENMAN parser.

**Step 2: Write failing validator tests**

Use synthetic graphs to test valid decoding, malformed graphs, fenced Markdown rejection, missing instance triples, unbound references, multiple top graphs, and unknown PropBank frames against a tiny test inventory. Unknown frame and representation gaps remain explicit validation results rather than silent repair.

**Step 3: Write failing ledger tests**

Test immutable attempt files, refusal to overwrite, attempt-2 eligibility only after an attempt-1 parse failure, sidecar hashes, timing fields, and explicit `usage_status="unavailable"` when telemetry is absent.

**Step 4: Verify RED, implement, and verify GREEN**

```powershell
D:\Anaconda\python.exe -m pytest tests/amr_pilot/test_penman_validation.py tests/amr_pilot/test_run_ledger.py -q -p no:cacheprovider --basetemp .t\amr-validation
```

### Task 6: Add Blinding and Deterministic Scoring

**Files:**
- Create: `tools/amr_pilot/scoring.py`
- Create: `tests/amr_pilot/test_scoring.py`
- Create after model runs: `artifacts/amr-pilot/reports/blinded-review-payloads.json`
- Create after review: `artifacts/amr-pilot/reports/review-results.json`
- Create after adjudication: `artifacts/amr-pilot/reports/adjudication.json`

**Step 1: Write failing scoring tests**

Test deterministic blind IDs that reveal no route name, complete gold-item coverage, weighted precision/recall from explicit weights, hallucination counts, critical-error counts, first-pass parse rate, route-level latency/token aggregation, and refusal to decide cost gates when usage is unavailable.

**Step 2: Verify RED, implement, and verify GREEN**

```powershell
D:\Anaconda\python.exe -m pytest tests/amr_pilot/test_scoring.py -q -p no:cacheprovider --basetemp .t\amr-scoring
```

### Task 7: Add the Experiment CLI and Layout Contract

**Files:**
- Create: `tools/amr_pilot/cli.py`
- Create: `tests/amr_pilot/test_cli.py`
- Modify: `tests/test_project_layout.py`

**Step 1: Write failing CLI and layout tests**

Cover `validate-inputs`, `validate-gold`, `prepare-payloads`, `validate-attempt`, `prepare-blind-review`, `score`, and `report`. Assert that the approved `tools/amr_pilot/` and `artifacts/amr-pilot/` responsibilities exist without moving or rewriting current knowledge and KEOL artifacts.

**Step 2: Verify RED, implement, and verify GREEN**

```powershell
D:\Anaconda\python.exe -m pytest tests/amr_pilot tests/test_project_layout.py -q -p no:cacheprovider --basetemp .t\amr-cli
```

### Task 8: Execute the Model Runs Only After Both Gates

**Preconditions:**

1. `gold/approval.json` matches the exact gold draft hash;
2. the active subagent interface can explicitly run `gpt-5.6-terra` and identify that model in the sidecar;
3. usage telemetry is available, or the user explicitly revises the balanced efficiency gate.

The user has explicitly authorized `gpt-5.6-terra` after cancelling the earlier 5.4 restriction. Do not silently change away from that model without renewed authorization.

**Execution:**

- run C once per sentence;
- validate and freeze C;
- run A once per sentence;
- run B once per validated C result;
- allow attempt 2 only for a recorded PENMAN parse failure;
- store every raw response and sidecar before validation or review;
- generate anonymous review payloads for an independent reviewer;
- ask the user to adjudicate disputed items.

### Task 9: Produce the Balanced Gate Report

**Files:**
- Create: `tools/amr_pilot/report.py`
- Create: `tests/amr_pilot/test_report.py`
- Create after adjudication: `artifacts/amr-pilot/reports/final-report.json`
- Create after adjudication: `artifacts/amr-pilot/reports/final-report.md`

**Step 1: Write a failing report test**

Use synthetic scored routes to verify every approved gate: 12 final parses, at least 11 first-pass parses, recall at least 90%, precision at least 95%, zero unresolved critical errors, at least two net AMR fixes in a predefined hard category, B improvement rules, and 1.5x/2.5x efficiency ceilings. Missing telemetry must produce `undecidable`, never pass.

**Step 2: Verify RED, implement, and verify GREEN**

```powershell
D:\Anaconda\python.exe -m pytest tests/amr_pilot/test_report.py -q -p no:cacheprovider --basetemp .t\amr-report
```

**Step 3: Run focused and full verification**

```powershell
D:\Anaconda\python.exe -m pytest tests/amr_pilot tests/test_project_layout.py -q -p no:cacheprovider --basetemp .t\amr-focused
D:\Anaconda\python.exe -m pytest tests -q -p no:cacheprovider --basetemp .t\amr-full
```

Validate all new JSON files with `ConvertFrom-Json` or Python `json`, verify recorded hashes, and confirm the old knowledge export remains byte-identical after its standard replay.

### Task 10: Update Workspace Facts Only After Adjudication

**Files:**
- Modify after a real conclusion: `AGENTS.md`
- Modify after a real conclusion: `安排.md`
- Modify if navigation is useful: `README.md`

Record sample counts, model identity, prompt and input hashes, parse/semantic/efficiency results, failed cases, and the explicit node decision. Until then, describe the AMR pilot as approved/in progress and do not rewrite the current KE-first memory architecture as an AMR architecture.
