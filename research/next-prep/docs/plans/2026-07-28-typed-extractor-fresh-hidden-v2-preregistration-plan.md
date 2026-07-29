# Typed Extractor Fresh-Hidden V2 Preregistration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement, validate, and freeze the fresh-hidden v2 preregistration before any authoring implementation, hidden data, or model run exists.

**Architecture:** Add an independent strict v2 preregistration module that binds the final L1 V10/L2 v9 passing chains, prior-data exclusions, deterministic authored-hidden protocol, exact qualification gates, future chronology, and zero-write boundary. Wire only freeze/validate CLI commands, then create one immutable preregistration artifact while every future authoring/evaluation path is absent.

**Tech Stack:** Python 3.13, Pydantic v2, pytest, canonical JSON/SHA-256 helpers, existing H100 `.venv-h100`.

## Global Constraints

- Work only in `/public/home/wwb/KE-mem/KE-memory-next-prep-20260727`; do not initialize Git or create a worktree.
- Keep v1 preregistration code and artifacts byte-identical.
- Do not create `typed_extractor_fresh_v2_authoring.py`, its test, an authoring receipt, or any hidden source/public/authority/gold file in this stage.
- Require the future evaluation root to be absent at freeze and validation.
- Bind L1 V10 and L2 v9 final prompts and passing-chain artifacts exactly.
- Require every strict quality metric to equal `1.0` and all three safety counts to equal `0`.
- Preserve public-only/no-history proposer isolation, one semantic run per layer, proposal freeze before scoring, and separate raw/gated reporting.
- Do not authorize pipeline integration or any L1/L2/revision/closure/identity/membership/snapshot/aggregate/source-revision write.
- Do not access old Fusion Memory or rerun external memory systems.

---

### Task 1: Write The V2 Preregistration Contract Tests

**Files:**
- Create: `tests/natural_memory_benchmark/test_typed_extractor_fresh_v2_prereg.py`
- Test target: `tools/natural_memory_benchmark/typed_extractor_fresh_v2_prereg.py`
- CLI target: `tools/natural_memory_benchmark/cli.py`

**Interfaces:**
- Consumes the exact workspace paths and hashes frozen in the design.
- Expects `freeze_typed_extractor_fresh_v2_preregistration(...) -> dict[str, Any]`.
- Expects `validate_typed_extractor_fresh_v2_preregistration(...) -> dict[str, Any]`.

- [x] Write tests for exact schema/evaluation IDs, L1/L2 family counts, exact metric thresholds, zero safety counts, requested model/isolation, prior-artifact hashes, future-path absence, and mode `0444`.
- [x] Write tests that reject an existing evaluation root, future authoring module/test, authoring receipt, unknown fields, and changed bound inputs.
- [x] Write CLI parity tests for `freeze-typed-extractor-fresh-v2-preregistration` and `validate-typed-extractor-fresh-v2-preregistration`.
- [x] Run `.venv-h100/bin/pytest -q tests/natural_memory_benchmark/test_typed_extractor_fresh_v2_prereg.py` and confirm collection fails because the v2 module is absent.

### Task 2: Implement The Independent Contract And CLI

**Files:**
- Create: `tools/natural_memory_benchmark/typed_extractor_fresh_v2_prereg.py`
- Modify: `tools/natural_memory_benchmark/cli.py`

**Interfaces:**
- `freeze_typed_extractor_fresh_v2_preregistration(output_root: Path, evaluation_root: Path, workspace_root: Path, freeze_time: str) -> dict[str, Any]` writes only `preregistration.json`.
- `validate_typed_extractor_fresh_v2_preregistration(root: Path, evaluation_root: Path, workspace_root: Path, freeze_time: str) -> dict[str, Any]` rehashes and rebuilds the exact contract.

- [x] Implement frozen constants, strict Pydantic models, exact input/code registries, passing-chain verification, future-path absence checks, and immutable writer.
- [x] Add the two CLI parsers and dispatch branches without changing v1 commands.
- [x] Run the focused tests and make the minimal implementation pass.
- [x] Run the existing v1 prereg tests to prove compatibility.

### Task 3: Freeze The Formal Preregistration

**Files:**
- Generate: `artifacts/automatic-extraction-assessment/typed-extractor-v2-fresh-hidden-prereg-v3/preregistration.json`

**Interfaces:**
- Consumes only the contract implementation and already frozen passing/exclusion inputs.
- Produces no hidden data and no authoring implementation.

- [x] Confirm preregistration root, future evaluation root, future authoring module/test, and authoring receipt are absent.
- [x] Freeze with the current UTC timestamp through the v2 CLI.
- [x] Validate immediately with the same timestamp and record SHA-256, size, and mode.
- [x] Confirm the evaluation root and every expected hidden path remain absent.

### Task 4: Audit And Update Workspace Facts

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `安排.md`
- Modify: `docs/plans/2026-07-28-typed-extractor-fresh-hidden-v2-preregistration-plan.md`

**Interfaces:**
- Records the immutable preregistration identity and the exact next chronology.

- [x] Run focused v2/v1 tests, all typed-extractor tests, all natural-memory tests, knowledge-pipeline tests, and `compileall`.
- [x] Revalidate the formal v2 preregistration, verify mode/hash and all future-path absence, scan for credential patterns, and confirm protected guard/candidate hashes.
- [x] Update the three workspace fact sources with the preregistration hash, validation result, zero-write status, and next authoring-implementation receipt step.
- [x] Re-run focused tests and contract validation after documentation updates.

## Execution Record

- The first prereg-v2 artifact at freeze time `2026-07-28T13:40:13Z`, SHA-256
  `0ac045b0cbed26a2fb624bc1f70d8275ae94edb41a57e868bae78c6effadc243`,
  is superseded after review found coercive Pydantic types and an inaccurate
  filesystem-mtime chronology claim. It remains immutable for audit.
- Review hardening added strict Pydantic validation, real UTC parsing, code-hash
  drift coverage, and accurate `filesystem-presence-plus-sha256` chronology
  with a caller-supplied untrusted UTC label.
- Current formal freeze time: `2026-07-28T14:08:22Z`.
- Current formal preregistration SHA-256: `1455bb7d5bb35b61809c78180ebf766573c1561e39bbeddda4a80f939a893760`.
- Current formal schema/mode/size: `typed-extractor-fresh-v2-preregistration-v2`,
  `0444`, `11016` bytes.
- Final validator: `valid`, L1 `24`, L2 `12`, future artifacts absent, hidden artifacts not created.
- Final tests: prereg focused `17 passed`, typed extractor `127 passed`, natural memory benchmark `498 passed`, knowledge pipeline `197 passed`, `compileall` success.
- Final audit: guard and candidate-v3 protected hashes unchanged; credential token pattern count `0`; no authoring module/test/receipt or evaluation root exists.

## Self-Review

- Spec coverage: passing chains, authorship, composition, strict thresholds, chronology, isolation, reporting separation, failure behavior, and claim boundaries each map to an implementation or audit step.
- Placeholder scan: no `TBD`, `TODO`, deferred implementation, or unspecified test remains.
- Type consistency: both public functions take only root/workspace/time inputs; future authoring paths are contract data, not current implementation inputs.
