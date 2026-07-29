# Typed Extractor Fresh-Hidden V3 Preregistration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement, freeze, and validate the fresh-hidden v3 preregistration before authoring code, hidden data, or model requests exist.

**Architecture:** Add one independent strict preregistration module and two CLI commands. Bind the final taxonomy L1 repair-v1/L2 baseline-v1 chains, deterministic all-blueprint composition, prior exclusions, exact quality/safety gates, future chronology, and zero-write boundary without changing v1/v2 preregistration or shared execution code.

**Tech Stack:** Python 3.13, Pydantic v2, pytest, canonical JSON/SHA-256 helpers, H100 `.venv-h100`.

## Global Constraints

- Work only in `/public/home/wwb/KE-mem/KE-memory-next-prep-20260727`; do not initialize Git or create a worktree.
- Keep v1/v2 preregistration modules and all existing formal artifacts unchanged.
- Do not create v3 authoring/materialization modules or tests, an authoring receipt, the evaluation root, hidden data, or model runs in this stage.
- Require L1 24 cases across eight families and L2 18 cases across nine families; use every blueprint without semantic filtering, replacement, or resampling.
- Require every strict quality metric to equal `1.0` and all three safety counts to equal `0`.
- Preserve public-only/no-history isolation, one semantic run per layer, proposal freeze before scoring, and separate raw/gated reporting.
- Do not authorize pipeline integration or any authoritative memory write.
- Do not access old Fusion Memory, rerun external memory systems, resolve the protected LongMemEval identity, or materialize manual identity adjudications.

---

### Task 1: Write The Independent Contract Tests

**Files:**
- Create: `tests/natural_memory_benchmark/test_typed_extractor_fresh_v3_prereg.py`
- Test target: `tools/natural_memory_benchmark/typed_extractor_fresh_v3_prereg.py`
- CLI target: `tools/natural_memory_benchmark/cli.py`

**Interfaces:**
- `freeze_typed_extractor_fresh_v3_preregistration(output_root: Path, evaluation_root: Path, workspace_root: Path, freeze_time: str) -> dict[str, Any]`
- `validate_typed_extractor_fresh_v3_preregistration(root: Path, evaluation_root: Path, workspace_root: Path, freeze_time: str) -> dict[str, Any]`

- [x] Write tests for exact IDs, passing hashes, family/count contracts, exact metrics, zero safety counts, isolation, exclusions, future absence, and mode `0444`.
- [x] Write rejection tests for unknown/coercive fields, an existing evaluation root, future authoring/materialization files or receipt, mutable/drifted inputs, and a second freeze into an existing root.
- [x] Write CLI parity tests for freeze and validate.
- [x] Run the focused file and confirm collection fails only because the v3 module is absent.

### Task 2: Implement The Contract And CLI

**Files:**
- Create: `tools/natural_memory_benchmark/typed_extractor_fresh_v3_prereg.py`
- Modify: `tools/natural_memory_benchmark/cli.py`

**Interfaces:**
- The freezer writes only `<output_root>/preregistration.json`.
- The validator rebuilds the contract from current read-only bound inputs and rejects drift.

- [x] Implement strict frozen models, family/threshold constants, exact passing chains, input/code registries, qualified-chain checks, and future absence checks.
- [x] Implement immutable freeze and pre-authoring validation with resolved paths and real UTC timestamp validation.
- [x] Add the two v3 CLI parsers and dispatch branches without changing v1/v2 behavior.
- [x] Run the focused tests to green, then run v1/v2 preregistration tests.

### Task 3: Freeze The Formal Preregistration

**Files:**
- Generate: `artifacts/automatic-extraction-assessment/typed-extractor-v3-fresh-hidden-prereg-v1/preregistration.json`

**Interfaces:**
- Consumes only frozen taxonomy passing chains, prior exclusions, and contract code.
- Produces no authoring implementation, receipt, evaluation root, hidden file, proposal, or score.

- [x] Confirm prereg/evaluation roots and every future implementation/test/receipt path are absent.
- [x] Freeze once through the CLI with the current caller-supplied UTC label.
- [x] Validate immediately; record schema, evaluation ID, SHA-256, size, mode, case counts, and future-path absence.
- [x] Confirm the formal root contains exactly `preregistration.json`.

### Task 4: Audit And Update Workspace Facts

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `安排.md`
- Modify: this plan

- [x] Run focused prereg tests, all typed extractor tests with the documented single deselection, knowledge-pipeline tests, full natural-memory tests with the same deselection, `compileall`, and `tabnanny`.
- [x] Revalidate the formal preregistration, scan for credential patterns, verify guard/candidate hashes, and confirm every automatic write count remains zero.
- [x] Record the immutable prereg identity and the next authoring-implementation receipt chronology in all three fact sources.
- [x] Re-run focused validation after documentation changes and record the completion evidence.

## Self-Review

- The plan covers composition, passing-chain binding, chronology, isolation, reporting separation, failure behavior, and zero-write boundaries.
- No task authors hidden content or invokes a model.
- The v3 names do not collide with `typed-extractor-v2-fresh-hidden-prereg-v3`.
- There are no placeholders or deferred contract decisions.

## Completion Record

- TDD RED failed only because `typed_extractor_fresh_v3_prereg` was absent;
  GREEN is `16 passed`. Adjacent v1/v2/v3 prereg tests are `34 passed`.
- The formal freeze label is `2026-07-29T04:51:35Z`. The only formal file is
  `artifacts/automatic-extraction-assessment/typed-extractor-v3-fresh-hidden-prereg-v1/preregistration.json`.
- Formal schema/evaluation ID are `typed-extractor-fresh-v3-preregistration-v1`
  and `typed-extractor-v3-fresh-hidden-v1`. SHA-256 is
  `183cf6fc2991361e5da57b17e06a5970f651000986d50b87e8af2e6796440204`;
  size/mode are `10998` bytes / `0444`.
- Validator reports `valid`, L1 `24`, L2 `18`, future absent, hidden not
  created, and model request count `0`. It binds 39 immutable inputs, 11 code/
  test files, 14/12 exact-1.0 quality metrics, and three zero safety counts.
- Module/test/CLI SHA-256 are
  `8b5ad64e99cabe2feeb63e79ac3046c64f5e871a6fafcc3ddad4606b628eeb4f`,
  `dd2001111d042abd4f3b2d9b84d645348cc373c3832bf00956fd638dfd0426bb`,
  and `817fc5105c42e0a7095b457ea2a6ea2b793ced31c0021eef1c097a458b418bc2`.
- Final regression is typed extractor `226 passed, 1 deselected`, knowledge
  pipeline `197 passed`, natural memory `653 passed, 1 deselected`, with
  `compileall` and `tabnanny` passing. The sole deselection remains the bound
  pre-materialization root-absence test.
- Candidate queue SHA-256 remains
  `518ead9de8627a9a4384df8cdd9b8728a21fcf797f6b0f3d208dfcb28ac41c0f`;
  guard fingerprint remains
  `e184b6caf2998acf1c8700bc84d24bbafd49ab9c8f15738d1af8cc484ee5ebcc`.
  Credential pattern and every automatic write count are `0`.
- The next stage may implement deterministic v3 authoring and freeze its
  implementation receipt. Hidden materialization, proposer calls, scoring,
  pipeline integration, and authoritative writes remain unauthorized.
