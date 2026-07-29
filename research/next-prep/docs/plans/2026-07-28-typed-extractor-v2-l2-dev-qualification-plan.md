# Typed Extractor V2 L2 Dev Qualification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Qualify a real zero-history proposer on a frozen six-case L2 dev slice after the L1 dev gate passed, while preserving complete L1 support/evidence provenance and keeping all authoritative writes disabled.

**Architecture:** Add an L2-specific contract beside the existing L1 modules. The slice builder replays only frozen bridge-v3 cross-turn candidates, binds each case to a private typed L1 support pack, and produces separated public/authority/gold artifacts. A model-run module freezes public-only proposals and provenance before the scorer can read authority/gold; the scorer reports raw L2 semantic quality separately from a fail-closed deterministic gate.

**Tech Stack:** Python 3.13, Pydantic v2, pytest, existing canonical JSON/hash/immutable-output helpers, H100 `.venv-h100`, OpenAI-compatible API.

## Global Constraints

- Work only in `/public/home/wwb/KE-mem/KE-memory-next-prep-20260727` on H100.
- This workspace is not a Git repository; do not initialize Git or create a worktree.
- Do not rerun the existing turn/dialogue extraction models or any external memory system.
- Do not access or reuse old Fusion Memory code, tests, architecture, or conclusions.
- The L2 proposer may read only frozen `public-l2.json` and `proposer-prompt-l2.md`.
- Freeze proposals/provenance before the scorer reads `authority-l2.json` or `gold-l2.json`.
- Raw proposer quality and deterministic gate safety remain separate top-level results.
- The gate may only preserve `emit_l2` or reduce it to `abstain`; it cannot repair claims, supports, abstraction, closure, or coverage.
- L2 public input contains frozen typed L1 support candidates, not authoritative L1 units or global identities.
- Do not create fresh hidden data until this L2 dev gate passes.
- Do not create authoritative L1/L2, revision, closure, identity, membership, snapshot, or aggregate writes.
- `LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.
- Formal artifacts are mode `0444`; deterministic replay must be byte-identical.

---

## File Structure

- Create `tools/natural_memory_benchmark/typed_extractor_l2.py`: strict L2 source/public/authority/gold/proposal/score models, six-case builder, validator, gate, scorer, taxonomy, and report.
- Create `tools/natural_memory_benchmark/typed_extractor_l2_model_run.py`: public-only dispatch and proposal/provenance freezing.
- Create `tests/natural_memory_benchmark/test_typed_extractor_l2.py`: L2 contract, separation, source replay, gate/scorer, mutation guard, and replay tests.
- Create `tests/natural_memory_benchmark/test_typed_extractor_l2_model_run.py`: dispatch/freeze chronology and public-reference validation tests.
- Modify `tools/natural_memory_benchmark/cli.py`: add L2 prepare, validate, dispatch, freeze, and score commands.
- Create `artifacts/automatic-extraction-assessment/typed-extractor-v2-l2-dev/source-cases-l2.json`: six private dev cases with frozen typed L1 support packs and expected decisions.
- Create `artifacts/automatic-extraction-assessment/typed-extractor-v2-l2-dev/proposer-prompt-l2.md`: exact public-only L2 proposal contract.
- Generate immutable public/authority/gold/manifest and formal model-run outputs through tested CLIs.
- Update `README.md`, `AGENTS.md`, `安排.md`, and the existing typed-extractor design only after formal scoring.

### Task 1: Implement The Strict L2 Contract

**Interfaces:**

- Consumes: shared typed predicate/entity/role/time/evidence classes from `typed_extractor_l1.py`.
- Produces: `TypedL1SupportCandidate`, `TypedL2StructuredClaim`, `TypedL2Closure`, `TypedL2Candidate`, `L2ProposalRecord`, and `L2ProposalPayload`.

- [x] Write failing tests requiring `emit_l2 | abstain`, exact tagged unions, contiguous claim-local entity IDs, closed role references, unique support refs, complete claim/support closure, complete source turn/session coverage, and null typed content for abstentions.
- [x] Run `.venv-h100/bin/python -m pytest -p no:cacheprovider tests/natural_memory_benchmark/test_typed_extractor_l2.py -q --basetemp=/tmp/ke-memory-typed-l2-contract-red`; expect import failure because the L2 module is absent.
- [x] Implement the strict Pydantic models with L2 kinds `task | preference_profile | project | habit | long_running_state | summary_event`, existing closure-pattern vocabulary, and candidate-only lifecycle.
- [x] Re-run the focused contract tests; expect pass.

### Task 2: Build And Validate The Six-Case Dev Slice

**Interfaces:**

- Consumes: frozen bridge-v3 ledger, exact extraction replay, private source config, and prompt.
- Produces: `prepare_l2_dev_slice(...)` and `validate_l2_dev_slice(...)`.

- [x] Add failing tests for exactly six cross-turn cases, four emits, two abstentions, at least two closure patterns, complete typed L1 support/evidence replay, opaque public IDs, public/authority/gold separation, and no answer-bearing metadata.
- [x] Run the focused tests and confirm the expected missing-builder failures.
- [x] Implement deterministic opaque IDs, source-turn/session binding, bridge-v3 cross-turn enforcement, exact evidence replay, public support-pack construction, authority restrictions, gold construction, manifest hashes, and read-only output handling.
- [x] Author the six-case dev source and exact prompt using only frozen dev/diagnostic records.
- [x] Run `prepare-typed-extractor-l2-dev`, freeze generated artifacts, and run `validate-typed-extractor-l2-dev`; expect `status=valid`, `case_count=6`, `emit_count=4`, and `abstain_count=2`.

### Task 3: Implement Public-Only Dispatch And Freeze

**Interfaces:**

- Consumes: immutable public/prompt, staged proposal JSON, and dispatch receipt.
- Produces: immutable dispatch, proposals, and provenance with exact hashes.

- [x] Add failing tests for the exact two-file allowlist, no inherited history, no authority/gold access, proposal coverage, support/turn/session/evidence reference closure, immutable outputs, and provenance hash binding.
- [x] Run the model-run tests and confirm missing implementation failures.
- [x] Implement `write_l2_model_dispatch(...)` and `freeze_l2_model_proposals(...)`.
- [x] Re-run both L2 focused test files and expect pass.

### Task 4: Implement Independent L2 Scoring And Safety Gate

**Interfaces:**

- Consumes: immutable public/authority/gold/manifest/proposals/provenance plus the existing authoritative guard bundle.
- Produces: immutable score, report, and error analysis.

- [x] Add failing tests for raw decision/abstention/evidence/kind/claim/support/abstraction/closure/source-coverage metrics, failure taxonomy, gate-only abstention, critical false materialization zero, unchanged guard fingerprint/counts, and all automatic writes zero.
- [x] Run the focused scorer tests and confirm missing scorer failures.
- [x] Implement `score_l2_proposals(...)`, `render_l2_score_report(...)`, and `run_l2_scoring_file(...)` without constructing authoritative objects.
- [x] Re-run focused tests and require pass.

### Task 5: Add CLI Integration

**Interfaces:**

- Produces commands `prepare-typed-extractor-l2-dev`, `validate-typed-extractor-l2-dev`, `prepare-typed-extractor-l2-dispatch`, `freeze-typed-extractor-l2-proposals`, and `score-typed-extractor-l2-proposals`.

- [x] Add failing CLI parser/round-trip tests.
- [x] Run the specific CLI tests and confirm unknown-command failures.
- [x] Add parser arguments and handlers mirroring the isolated L1 flow with L2-specific files/functions.
- [x] Re-run focused L2 tests and expect pass.

### Task 6: Execute The Real Dev Qualification

- [x] Freeze source/public/authority/gold/manifest/prompt and a dispatch receipt.
- [x] Send one fresh no-history OpenAI-compatible request containing only prompt and public payload; archive the raw response unchanged.
- [x] Extract only the response JSON to a temporary staged file, validate it, then freeze proposals/provenance before scoring.
- [x] Run independent scoring and freeze score/report/error analysis.
- [x] If raw quality fails, classify only against the L2 dev taxonomy, revise only public policy/prompt or deterministic schema validation, freeze a new versioned dev root/run, and repeat without hidden data.
- [x] Stop only on a passing L2 dev result or a concrete unrecoverable external blocker.

### Task 7: Final Verification And Status Update

- [x] Re-run focused L2 tests, all typed extractor tests, `tests/knowledge_pipeline`, all `tests/natural_memory_benchmark`, and `compileall`.
- [x] Validate L1/L2 slices, natural identity variants, benchmark slice/ledger, bridge-v3 replay, formal proposal/score/report replay, file modes, and all protected hashes.
- [x] Confirm the manual-review v3 queue remains byte-identical and no manual adjudication was materialized.
- [x] Record measured L2 raw/gated results, hashes, residual failures, guard state, and next authorized step in the four fact-source documents.

