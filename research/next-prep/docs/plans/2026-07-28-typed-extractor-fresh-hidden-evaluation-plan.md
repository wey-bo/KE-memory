# Typed Extractor Fresh Hidden Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze a contamination-resistant typed-extractor preregistration, build deterministic hidden-only L1/L2 slices after that freeze, and run one immutable public-only model evaluation per layer.

**Architecture:** A preregistration module binds prompts, dev exclusions, source/code hashes, namespaces, selection rules, thresholds, expected hidden paths, and zero-write boundaries before hidden authoring. Separate L1/L2 hidden builders then select cases deterministically, freeze public/authority/gold artifacts, and reuse the provenance-v2 dispatch/freeze/scoring flow without hidden-driven repair.

**Tech Stack:** Python 3.13, Pydantic v2, pytest, canonical JSON/SHA-256 helpers, existing typed L1/L2 contracts and H100 `.venv-h100`.

## Global Constraints

- Work only in the current H100 workspace; do not initialize Git.
- Do not create hidden cases until the preregistration validator passes and the preregistration is mode `0444`.
- Use L1 prompt V6 and the final L2 prompt byte-for-byte; no hidden-driven prompt or threshold changes.
- Freeze proposals/provenance before scoring reads authority/gold.
- Report raw proposer quality separately from deterministic gate safety.
- Keep all authoritative writes at zero and `LONGMEMEVAL-6d550036` unresolved.
- Do not rerun external memory systems or access old Fusion Memory.

---

### Task 1: Freeze And Validate The Preregistration

**Files:**
- Create: `tools/natural_memory_benchmark/typed_extractor_fresh_prereg.py`
- Create: `tests/natural_memory_benchmark/test_typed_extractor_fresh_prereg.py`
- Modify: `tools/natural_memory_benchmark/cli.py`
- Generate: `artifacts/automatic-extraction-assessment/typed-extractor-v2-fresh-hidden-prereg-v1/preregistration.json`

**Interfaces:**
- Produces `freeze_typed_extractor_fresh_preregistration(...) -> dict[str, Any]` and `validate_typed_extractor_fresh_preregistration(...) -> dict[str, Any]`.
- Adds CLI commands `freeze-typed-extractor-fresh-preregistration` and `validate-typed-extractor-fresh-preregistration`.

- [x] Write strict-model tests for exact namespaces, counts, strata, thresholds, prompt/source/dev/code hashes, expected hidden paths, and zero-write claim boundary.
- [x] Run the focused test and confirm missing-module failure.
- [x] Implement the strict model, exact hash gathering, hidden-path absence gate, immutable writer, validator, and CLI wiring.
- [x] Run focused tests and confirm pass.
- [x] Freeze the formal preregistration while the evaluation root is absent; validate it and record its SHA-256/mode.

### Task 2: Build The Hidden L1 Slice

**Files:**
- Create: `tools/natural_memory_benchmark/typed_extractor_fresh_l1.py`
- Create: `tests/natural_memory_benchmark/test_typed_extractor_fresh_l1.py`
- Generate L1 source/public/authority/gold/manifest files under `typed-extractor-v2-fresh-hidden-v1/l1/`.

**Interfaces:**
- Produces `prepare_fresh_l1_slice(...)` and `validate_fresh_l1_slice(...)`.

- [x] Write failing tests for deterministic 24-case stratum selection, dev ID/evidence non-overlap, opaque public IDs, public/gold separation, exact source replay, and prereg chronology.
- [x] Implement selection from bridge-v3 and raw turns without semantic filtering.
- [x] Author gold only for the selected records; do not modify selection, prompt, thresholds, or namespace.
- [x] Freeze and validate the L1 hidden artifacts as `0444`; replay byte-identically.

### Task 3: Build The Hidden L2 Slice

**Files:**
- Create: `tools/natural_memory_benchmark/typed_extractor_fresh_l2.py`
- Create: `tests/natural_memory_benchmark/test_typed_extractor_fresh_l2.py`
- Generate L2 source/public/authority/gold/manifest files under `typed-extractor-v2-fresh-hidden-v1/l2/`.

**Interfaces:**
- Produces `prepare_fresh_l2_slice(...)` and `validate_fresh_l2_slice(...)`.

- [x] Write failing tests requiring all eight unused bridge-v3 cross-turn records, no semantic filtering, dev non-overlap, exact support/evidence closure, opaque IDs, and prereg chronology.
- [x] Implement all-unused deterministic selection and strict public/authority/gold builders.
- [x] Author gold after selection is fixed; abort rather than replace an inconvenient case.
- [x] Freeze, validate, and byte-replay the L2 hidden artifacts.

### Task 4: Run The One-Shot L1 Evaluation

- [x] Freeze provenance-v2 dispatch using requested model `deepseek-chat`, L1 prompt V6, and only hidden L1 public input.
- [x] Send a fresh no-history official API request, archive raw response, and freeze proposals/provenance.
- [x] Confirm proposal/provenance mode and hashes before scoring.
- [x] Score once against hidden L1 authority/gold, freeze score/report/error analysis, and do not repair from hidden results.

### Task 5: Run The One-Shot L2 Evaluation

- [x] Freeze provenance-v2 dispatch using requested model `deepseek-chat`, final L2 prompt, and only hidden L2 public input.
- [x] Send a fresh no-history official API request, archive raw response, and freeze proposals/provenance.
- [x] Confirm proposal/provenance mode and hashes before scoring.
- [x] Score once against hidden L2 authority/gold, freeze score/report/error analysis, and do not repair from hidden results.

### Task 6: Verify And Report

- [x] Run focused fresh-hidden tests, all typed tests, knowledge tests, full natural benchmark tests, and compileall.
- [x] Validate identity v1-v4, benchmark slice/ledger, bridge-v3, L1/L2 dev, fresh prereg chronology, and fresh hidden artifacts.
- [x] Verify protected hashes, candidate v3 queue, four unmaterialized manual adjudications, all `0444` modes, zero writes, unchanged guard fingerprints, and no key material.
- [x] Update `README.md`, `AGENTS.md`, `安排.md`, and the typed-extractor design with raw and gated results separately.

Task 6 note: the preregistration CLI validator is intentionally a pre-authoring
gate and rejects a now-existing evaluation root. It passed before hidden
authoring. Post-authoring verification uses the frozen preregistration SHA/mode,
the chronology receipt binding, and the fresh L1/L2 validators without changing
the preregistration-bound code. The existing natural-memory suite is `403
passed`; the unconditional collection command is currently blocked by a
concurrently added `test_query_compiler_v2_assessment.py` whose corresponding
module has not yet been added. That parallel file is outside this plan and was
neither modified nor silently excluded from the reported blocker.

## Self-Review

- Spec coverage: prompt/threshold freeze, deterministic selection, chronology, model provenance, raw/gated separation, failure policy, and zero-write boundaries each have an explicit task.
- Placeholder scan: no task defers an unspecified implementation or test.
- Type consistency: the prereg validator is the sole pre-authoring gate; L1/L2 builders and model runs consume its exact immutable contract.
