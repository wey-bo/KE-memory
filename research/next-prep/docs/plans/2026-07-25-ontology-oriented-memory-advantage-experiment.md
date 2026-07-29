# Ontology-Oriented Memory Advantage Experiment Implementation Plan

**Goal:** Build and run the approved 60-scenario controlled experiment that separates representation from execution, measures an ontology-oriented memory ceiling and automatic extraction tax, and treats embedding only as a conditional evidence-recovery fallback.

**Architecture:** The implementation has four independently testable boundaries: immutable source/gold contracts, representation adapters, query executors, and paired scoring/reporting. Source scenarios and questions are visible to all arms, while answers, required evidence, required primitives, split labels, and architecture attribution remain in a separately loaded gold file used only by scoring. Oracle and automatic representations share executors; each adapter exposes only the semantic fields it actually produced, and every result retains a trace back to source turn IDs.

**Tech Stack:** Python 3.13, Pydantic 2, pytest, NumPy/scikit-learn for diagnostics and bootstrap, FastEmbed with a frozen BGE small English model for the actual dense arm, JSON/JSONL/Markdown artifacts.

---

## Non-Negotiable Boundaries

- Do not read, copy, or adapt code, tests, evaluation logic, or conclusions from any previous Fusion Memory project.
- Do not install or rerun Mem0, Graphiti, Hindsight, or MemPalace. Record only official repository/paper evidence at the frozen commits.
- Do not label TF-IDF, BM25, hashing, or hand-authored similarity as the strong dense baseline. The main `B0/B1/B2/O+E` run requires the configured real embedding backend and records model ID, revision, dimensions, and cache state.
- Arms may receive `scenario_id` only for result joins. They may not branch on it or receive family, split, attribution, answer, required evidence, required primitives, remedy, or falsifier.
- `O-` removes the scenario's pre-registered required primitive from an otherwise identical oracle representation. It may not reconstruct that primitive from raw text.
- Embedding candidates may fill only declared unresolved slots or an empty symbolic result. They are rejected when they conflict with explicit polarity, temporal validity, modality, provenance, conflict, supersession, role, or quantity constraints.
- The three distractor scales are repeated observations of the same 60 base scenarios. Bootstrap resampling and all denominators use base scenarios, not 180 rows.
- Generated artifacts are immutable by default: identical replay is allowed; different content at an existing path fails.
- This is a controlled capability experiment. It can establish class-level evidence, not scores for unrun named systems.
- Because `.git` is an empty directory, worktree and commit steps are unavailable. Agents use exclusive file ownership and root performs integration verification.

## Frozen Interfaces

### Source document

`artifacts/ontology-memory-experiment/gold/source-scenarios.json` contains only:

```json
{
  "schema_version": "ontology-memory-source-v1",
  "scenarios": [
    {
      "scenario_id": "OME-S001",
      "language": "en",
      "turns": [
        {"turn_id": "OME-S001-T01", "speaker": "user", "text": "..."}
      ],
      "question": "...",
      "candidate_answer_budget": 32
    }
  ]
}
```

### Gold document

`artifacts/ontology-memory-experiment/gold/gold.json` contains:

```json
{
  "schema_version": "ontology-memory-gold-v1",
  "status": "frozen",
  "scenarios": [
    {
      "scenario_id": "OME-S001",
      "family": "roles_polarity_modality_quantity",
      "origin": "architecture_directed",
      "primary_system": "mem0",
      "split": "dev",
      "answer": {"kind": "value", "values": ["Avery"]},
      "required_evidence_turn_ids": ["OME-S001-T03"],
      "hard_negative_turn_ids": ["OME-S001-T02"],
      "required_primitives": ["role"],
      "critical_constraints": ["agent_role"],
      "architecture_claim_ids": ["CLAIM-MEM0-001"],
      "proposed_ontology_remedy": "typed participant roles",
      "falsifier": "O- matches O+ on role-swapped negatives"
    }
  ]
}
```

### Representation and query plan

The common representation is a list of typed `MemoryRecord` values with `record_id`, `source_turn_ids`, `surface_text`, canonical `entities`, `predicate`, typed `roles`, `polarity`, `modality`, `quantity`, `valid_time`, `transaction_time`, `provenance_status`, `conflict_group`, `supersedes`, and `relations`. Missing fields remain null/empty and are never synthesized by an executor.

`QueryPlan` contains canonical entity/sense candidates, predicate, role constraints, polarity, modality, quantity, time/status/provenance filters, conjunction groups, bounded traversal steps, required answer slot, and declared unresolved slots. Automatic query compilation receives only question text.

### Arm result

Every result records `run_id`, `track`, `arm`, `scenario_id`, `distractor_scale`, ranked evidence turn IDs with scores, selected evidence turn IDs, predicted answer or abstention, constraint checks, symbolic trace, fallback trigger/reason, rejected fallback candidates, latency, model metadata, and error status.

## Test List

1. Contracts forbid hidden gold fields in source and arm inputs.
2. The generator creates exactly 60 unique English scenarios, 15 per family, 40 directed and 20 neutral, with a 12/48 split and preserved system proportions.
3. Every scenario has 4-8 turns, one answer or unanswerable, exact evidence, 2-4 hard negatives, and valid source spans.
4. Distractor scales contain exactly 0/50/500 new memories, preserve the base answer, reuse hard lexical material, and have stable hashes.
5. The audit accepts only official URLs, frozen commits, evidence grades, verbatim excerpts, and explicit comparability labels.
6. `B0/B1/B2` rank without executing hidden structural filters.
7. `O-` deletes exactly one required primitive and cannot recover it.
8. `O+` executes roles, polarity, modality, quantity, time, provenance, conflict/supersession, conjunction, exact set, traversal, and abstention.
9. `O+E` triggers only for declared symbolic misses and cannot override explicit constraints.
10. Oracle and automatic tracks use the same executor and differ only in representation/query compilation.
11. Evidence Set Exact Match, critical false positives, constraint satisfaction, answers, abstention, recall/precision, fallback, and efficiency are computed at base-scenario level.
12. Gate logic implements all six approved thresholds and returns `pass`, `fail`, or `undecidable` with reasons.
13. Run output is immutable, hash-bound, source-traceable, and replayable from the CLI.

### Task 1: Strict Contracts and Immutable I/O

**Files:**
- Create: `tools/ontology_memory_experiment/__init__.py`
- Create: `tools/ontology_memory_experiment/models.py`
- Create: `tools/ontology_memory_experiment/io.py`
- Create: `tests/ontology_memory_experiment/test_contracts.py`

**Step 1: Write the failing contract tests**

Test exact schema versions, stable IDs, 4-8 turn bounds, evidence references, answer/unanswerable exclusivity, representation field typing, fallback reason enums, `extra="forbid"`, SHA-256 validation, and refusal to overwrite different output.

**Step 2: Verify RED**

Run:

```powershell
D:\Anaconda\python.exe -m pytest tests\ontology_memory_experiment\test_contracts.py -q -p no:cacheprovider --basetemp .t\ome-contracts-red
```

Expected: import failure for `tools.ontology_memory_experiment.models`.

**Step 3: Implement minimal contracts**

Use `Literal`, constrained Pydantic fields, and after validators. `write_json_immutable(path, value)` serializes sorted UTF-8 JSON plus one newline, allows byte-identical replay, and raises on a different existing file. `sha256_file` and `write_manifest` bind all frozen inputs.

**Step 4: Verify GREEN**

Run the same test with basetemp `.t\ome-contracts-green`; expect all tests to pass.

### Task 2: Official Architecture Audit

**Files:**
- Create: `tools/ontology_memory_experiment/audit.py`
- Create: `tests/ontology_memory_experiment/test_audit.py`
- Create: `artifacts/ontology-memory-experiment/architecture-audit/source-manifest.json`
- Create: `artifacts/ontology-memory-experiment/architecture-audit/capability-matrix.json`
- Create: `artifacts/ontology-memory-experiment/architecture-audit/gap-hypothesis-ledger.json`
- Create: `artifacts/ontology-memory-experiment/architecture-audit/official-results-ledger.json`
- Create: `artifacts/ontology-memory-experiment/architecture-audit/README.md`

**Step 1: Write failing audit tests**

Require the four frozen commits, official URLs, retrieval timestamps, document hashes or immutable commit URLs, claim-level excerpts, one allowed evidence grade, no unsupported `confirmed_gap`, and no direct numeric table entry unless benchmark/split/model/metric/protocol are compatible.

**Step 2: Verify RED**

```powershell
D:\Anaconda\python.exe -m pytest tests\ontology_memory_experiment\test_audit.py -q -p no:cacheprovider --basetemp .t\ome-audit-red
```

**Step 3: Retrieve and record official evidence**

Read only the official repositories or papers at the frozen commits. Record excerpts for both confirmed capabilities and the exact architecture risks being tested. Leave unavailable author results as `not_found`, not zero. Validate artifacts through `audit.py`.

**Step 4: Verify GREEN**

Run the audit tests and `python -m tools.ontology_memory_experiment.cli validate-audit ...`; expect success and four systems.

### Task 3: Controlled Scenario, Gold, and Distractor Generation

**Files:**
- Create: `tools/ontology_memory_experiment/scenarios.py`
- Create: `tests/ontology_memory_experiment/test_scenarios.py`
- Create: `artifacts/ontology-memory-experiment/gold/source-scenarios.json`
- Create: `artifacts/ontology-memory-experiment/gold/gold.json`
- Create: `artifacts/ontology-memory-experiment/gold/distractors.json`
- Create: `artifacts/ontology-memory-experiment/gold/manifest.json`

**Step 1: Write failing generator tests**

Assert all distribution, turn, evidence, hard-negative, answer, primitive, attribution, split, scale, leakage, deterministic replay, and hash requirements from the frozen design.

**Step 2: Verify RED**

```powershell
D:\Anaconda\python.exe -m pytest tests\ontology_memory_experiment\test_scenarios.py -q -p no:cacheprovider --basetemp .t\ome-scenarios-red
```

**Step 3: Implement deterministic English scenarios**

Use 15 competency templates per family, but vary people, objects, locations, dates, aliases, predicates, and question wording from seeded pools. Ten directed cases per audited system are distributed across families; five neutral cases per family complete the 20 neutral cases. Exactly three scenarios per family are dev. Generate distractors from source-only lexical elements while flipping at least one role, polarity, quantity, validity, provenance, or sense primitive. Do not include `family`, `split`, `primary_system`, `answer`, or gold labels in source/distractor records.

**Step 4: Freeze artifacts and verify GREEN**

Generate once through the CLI, validate, then rerun to a temp directory and compare hashes. Expect 60 base scenarios and 33,000 distractors total across the 50 and 500 scales.

### Task 4: Representation Adapters and Query Compilation

**Files:**
- Create: `tools/ontology_memory_experiment/representations.py`
- Create: `tools/ontology_memory_experiment/query.py`
- Create: `tests/ontology_memory_experiment/test_representations.py`
- Create: `tests/ontology_memory_experiment/test_query.py`

**Step 1: Write failing adapter tests**

Cover `L0`, `L1`, `L2`, `L3`, oracle/automatic tracks, exact provenance, evidence links, field absence rather than invention, primitive ablation, and no access to gold-only fields. Query tests cover generic English constraints without scenario-ID branching.

**Step 2: Verify RED**

```powershell
D:\Anaconda\python.exe -m pytest tests\ontology_memory_experiment\test_representations.py tests\ontology_memory_experiment\test_query.py -q -p no:cacheprovider --basetemp .t\ome-representation-red
```

**Step 3: Implement adapters**

Oracle data is a separately generated representation fixture bound to source hashes, not a runtime read of answers. Automatic extraction uses frozen, generic regex/lexicon rules for the controlled English grammar and records per-primitive success/failure. It must parse participant roles, explicit negation/modality/quantity, ISO-like dates, correction markers, source speaker/tool status, conjunctions, and explicit relation chains. Unparsed concepts become unresolved slots.

**Step 4: Verify GREEN**

Run focused tests; additionally scan production modules for `OME-S`, `primary_system`, and gold answer access, allowing those strings only in validators/result joins.

### Task 5: Dense Ranking, Symbolic Execution, and Conditional Fallback

**Files:**
- Create: `tools/ontology_memory_experiment/dense.py`
- Create: `tools/ontology_memory_experiment/executors.py`
- Create: `tests/ontology_memory_experiment/test_dense.py`
- Create: `tests/ontology_memory_experiment/test_executors.py`
- Create: `tools/ontology_memory_experiment/requirements-dense.txt`

**Step 1: Write failing executor tests**

Use an injected deterministic encoder in unit tests. Prove ranking-only arms can surface structurally wrong candidates, `O+` filters them, `O-` fails when its deleted primitive is necessary, conjunction/path execution returns complete evidence sets, and fallback is blocked from overriding structural constraints.

**Step 2: Verify RED**

```powershell
D:\Anaconda\python.exe -m pytest tests\ontology_memory_experiment\test_dense.py tests\ontology_memory_experiment\test_executors.py -q -p no:cacheprovider --basetemp .t\ome-executors-red
```

**Step 3: Implement the six arms**

`DenseEncoder` is injected. The real provider wraps FastEmbed, normalizes vectors, batches documents, and records the actual model revision/dimension. `B0` ranks raw turns, `B1` ranks atomic text, and `B2` ranks serialized full records without structural filters. `O-` and `O+` use the same deterministic executor. `O+E` executes symbols first and only then requests a dense candidate for an enumerated unresolved slot or empty result; it re-runs all expressible constraints before admitting the candidate.

**Step 4: Verify GREEN**

Run focused tests. Install dense dependencies into an isolated local environment only after unit behavior is green, then run a two-scenario smoke test and record model metadata.

### Task 6: Scoring, Bootstrap, and Gate Report

**Files:**
- Create: `tools/ontology_memory_experiment/scoring.py`
- Create: `tools/ontology_memory_experiment/report.py`
- Create: `tests/ontology_memory_experiment/test_scoring.py`
- Create: `tests/ontology_memory_experiment/test_report.py`

**Step 1: Write failing metric tests**

Use hand-computed fixtures for Evidence Set Exact Match, critical false-positive rate, constraint satisfaction, answer correctness, abstention, P/R@K, fallback rates, extraction accuracy, P50/P95, storage, and base-scenario bootstrap intervals. Test every gate boundary, `undecidable` handling, and the 70-percent retained-gain formula:

```text
retained_gain = (automatic_O+ - automatic_baseline) / (oracle_O+ - oracle_baseline)
```

**Step 2: Verify RED**

```powershell
D:\Anaconda\python.exe -m pytest tests\ontology_memory_experiment\test_scoring.py tests\ontology_memory_experiment\test_report.py -q -p no:cacheprovider --basetemp .t\ome-score-red
```

**Step 3: Implement paired scoring and report rendering**

Aggregate scales within base scenario before bootstrap. Emit overall and family/scale/track/arm slices, absolute paired differences, deterministic 95-percent bootstrap intervals with a recorded seed, error categories, gate checks, caveats, and class-level audit linkage. Never render an unrun named system as an arm.

**Step 4: Verify GREEN**

Run focused tests and JSON-schema/Pydantic validation of a fixture report.

### Task 7: Runner, CLI, and Immutable Ledger

**Files:**
- Create: `tools/ontology_memory_experiment/runner.py`
- Create: `tools/ontology_memory_experiment/cli.py`
- Create: `tests/ontology_memory_experiment/test_runner.py`
- Create: `tests/ontology_memory_experiment/test_cli.py`
- Modify: `tests/test_project_layout.py`

**Step 1: Write failing integration tests**

Test commands `generate`, `validate-audit`, `validate-gold`, `smoke`, `run`, `score`, and `report`; stable run IDs supplied by caller; source/gold hash binding; six arms; two tracks; three scales; no overwrite; raw rankings/traces/errors; and exact source evidence recovery.

**Step 2: Verify RED**

```powershell
D:\Anaconda\python.exe -m pytest tests\ontology_memory_experiment\test_runner.py tests\ontology_memory_experiment\test_cli.py tests\test_project_layout.py -q -p no:cacheprovider --basetemp .t\ome-runner-red
```

**Step 3: Implement orchestration**

Load source separately from gold, build representations before loading scorer gold, precompute dense embeddings per scale, use bounded thread pools for scenario-level execution, record per-arm timing, and sort all outputs before immutable writes. The CLI refuses a main run when the real dense backend is unavailable; only `smoke --allow-diagnostic-encoder` may use the deterministic test encoder.

**Step 4: Verify GREEN**

Run the focused integration tests and a diagnostic smoke run. Confirm the layout test requires code plus the minimum audit/gold artifacts without treating generated run IDs as fixed project structure.

### Task 8: Execute, Interpret, and Synchronize Workspace Status

**Files:**
- Create: `artifacts/ontology-memory-experiment/runs/<run_id>/manifest.json`
- Create: `artifacts/ontology-memory-experiment/runs/<run_id>/results.jsonl`
- Create: `artifacts/ontology-memory-experiment/runs/<run_id>/metrics.json`
- Create: `artifacts/ontology-memory-experiment/runs/<run_id>/errors.jsonl`
- Create: `artifacts/ontology-memory-experiment/reports/gate-report.json`
- Create: `artifacts/ontology-memory-experiment/reports/gate-report.md`
- Create: `artifacts/ontology-memory-experiment/reports/external-context.md`
- Modify: `AGENTS.md`
- Modify: `安排.md`
- Modify: `README.md` only if a new reproducible command needs discovery.

**Step 1: Run a two-scenario real-model smoke test**

Record peak process memory before/after model load, model metadata, warm/cold latency, and artifact hashes. A failed model load blocks the main dense comparison and must be reported as `undecidable`, not replaced silently.

**Step 2: Run the frozen development slice**

Use all arms/tracks/scales to catch implementation errors. Changes after this point may fix code defects only; any schema, rule, primitive, or prompt change requires regenerating and re-freezing the experiment under a new version.

**Step 3: Run the hidden slice once**

Run scenarios concurrently with a bounded worker count, while keeping dense model inference within its provider's safe batching policy. Preserve raw result order through deterministic sorting.

**Step 4: Generate and inspect the gate report**

Report the six primary gates, family-level outcomes, 500-distractor robustness, automatic retained gain, fallback behavior, latency/memory, and representative failures. Keep official external results in contextual tables unless all comparability fields match.

**Step 5: Run fresh verification**

```powershell
D:\Anaconda\python.exe -m pytest tests\ontology_memory_experiment -q -p no:cacheprovider --basetemp .t\ome-focused-final
D:\Anaconda\python.exe -m pytest tests -q -p no:cacheprovider --basetemp .t\ome-full-final
D:\Anaconda\python.exe -m tools.ontology_memory_experiment.cli validate-gold --source artifacts\ontology-memory-experiment\gold\source-scenarios.json --gold artifacts\ontology-memory-experiment\gold\gold.json --distractors artifacts\ontology-memory-experiment\gold\distractors.json --manifest artifacts\ontology-memory-experiment\gold\manifest.json
D:\Anaconda\python.exe -m tools.ontology_memory_experiment.cli verify-run --run-dir artifacts\ontology-memory-experiment\runs\<run_id>
```

Expected: all tests pass; 60 valid scenarios; all frozen hashes match; 2 tracks x 6 arms x 3 scales x 60 scenarios are accounted for or have explicit error rows; evidence links recover exact source turns.

**Step 6: Update workspace facts**

Only after the fresh commands pass, update `AGENTS.md` and `安排.md` with actual artifact paths, run ID, model revision, scenario/result counts, metric values, gate decision, limitations, and the next human decision. Do not convert directional pilot findings into universal architecture claims.

## Parallel Ownership

- Architecture audit agent: Task 2 files only.
- Contracts/data agent: Tasks 1 and 3 files only.
- Representation/execution agent: Tasks 4-6 files only.
- Root agent: Task 7, dependency/model smoke, integration, Task 8, and all shared documentation.

An agent must run and report its RED test before adding production code, then run its focused GREEN tests. Root reviews file overlap, reads every agent summary, runs all focused tests, and runs the complete suite before making any completion claim.
