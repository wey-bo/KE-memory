# Identity Resolution and Extended-AMR v3 Implementation Plan

**Goal:** Implement a schema.org-informed local concept registry, representation-neutral identity decisions, correction-safe snapshots, safe `count_distinct`, and Extended-AMR v3 parity without changing frozen v3/v5 behavior.

**Architecture:** Add a parallel identity-aware v4 logical bundle over the existing authoritative v3 bundle. Build identity snapshots only from accepted decisions with fresh evidence closure. Authorize aggregates only from exact member units and a fresh snapshot. Encode the same logical records explicitly in Extended-AMR v3.

**Tech stack:** Python 3.13, Pydantic v2, pytest, canonical JSON/SHA-256, existing authoritative v3 and Extended-AMR v2 modules.

## TODO 1: Freeze sources, concepts, scenarios, and gates

- [x] Read `AGENTS.md`, `安排.md`, the scheme PDF, and v3/v5 design/code.
- [x] Verify the 117-test v3/v5 baseline.
- [x] Freeze schema.org 30.0 selected definitions and official repository commit.
- [x] Freeze four dev and four hidden identity scenarios.
- [x] Pre-register correctness and regression gates before implementation.

## TODO 2: Write failing contract tests

- [x] Add tests for concept mapping constraints and schema.org advisory boundaries.
- [x] Add tests for merge, keep-distinct, reject-merge, split, and abstain decisions.
- [x] Add tests for decision evidence closure and scoped freshness.
- [x] Add tests for deterministic snapshots and contradiction rejection.
- [x] Add tests for safe `count_distinct`, exact evidence, and unresolved abstention.
- [x] Run RED and confirm failures are missing identity APIs.

## TODO 3: Implement native identity-aware v4

- [x] Add `identity_resolution.py` with strict logical models and deterministic IDs.
- [x] Build concept registry and scenario-to-v4 bundle loader.
- [x] Implement identity closure evaluation and freshness checks.
- [x] Implement active-decision resolution, union/distinct policy, and snapshots.
- [x] Implement aggregate construction, validation, and identity-aware query execution.
- [x] Keep existing `authoritative_memory.py` v3 behavior and artifacts unchanged.
- [x] Run focused GREEN tests.

## TODO 4: Implement Extended-AMR v3

- [x] Add explicit concept, entity, decision, snapshot, and aggregate graph records.
- [x] Reuse explicit v2 event-role/revision graphs without opaque v4 copies.
- [x] Decode to native v4 and run all identity integrity/freshness checks.
- [x] Test exact multi-revision round-trip and malformed graph rejection.
- [x] Test native/Extended-AMR query parity.

## TODO 5: Build the immutable identity conformance run

- [x] Add a runner and CLI command for the frozen dev/hidden diagnostic.
- [x] Score false merges, count/evidence exactness, abstention, revision stability, closure freshness, fallback, and carrier parity.
- [x] Preserve the existing LongMemEval v5 abstention as a hard regression.
- [x] Write new immutable JSON and Markdown artifacts under `artifacts/identity-memory-experiment/runs/` and `reports/`.
- [x] Replay to an isolated path and compare canonical bytes.

## TODO 6: Full verification and documentation

- [x] Run focused identity tests.
- [x] Run all `tests/natural_memory_benchmark` tests.
- [x] Validate slice and external ledger.
- [x] Verify frozen v5 artifact hashes are unchanged.
- [x] Update `README.md`, `AGENTS.md`, `安排.md`, and related design status.
- [x] Report implemented capability separately from product/storage conclusions.

## Completion evidence

- Focused identity tests: `16 passed`.
- Full `tests/natural_memory_benchmark`: `133 passed`.
- Slice validation: `32` public / `32` gold, valid.
- External ledger: `13` entries, valid.
- Formal run: `run-20260727T080000Z-identity-v1`, status `pass`.
- Results SHA-256: `e7cc632ae20f6436156fcd9c777352eac0f8286e63cb24f42ddee05875ae633c`.
- Report SHA-256: `bc032cf6a5590a8d1f12adf5d523af9da65d599b66ceddac52667d213b920ae8`.
- Isolated replay: JSON and report byte-identical.
- Frozen v5 results SHA-256 remains `3ec6656c037200f8591fac44cd7e1e4bf2caa3aa9447f3fa5ba9854324d4cc33`.

## Final documentation reconciliation

- [x] Add the identity design, modules, artifacts, metrics, hashes, and claim boundary to `README.md`.
- [x] Add the identity/schema.org/Extended-AMR v3 follow-up to both representation design documents.
- [x] Replace the stale Extended-AMR v4 blocker in `AGENTS.md` with the current natural identity-candidate and storage-selection TODO.
- [x] Confirm `安排.md` already records the same identity status and next TODO.
- [x] Re-run the 16 focused tests and the full 133-test natural-memory suite after documentation reconciliation.
- [x] Re-validate slice-v1 and the external-results ledger.
- [x] Re-check identity results/report and frozen v5 SHA-256 values.
- [x] Re-run the formal identity CLI in an isolated directory and confirm JSON/report byte identity.

## Commands

```powershell
New-Item -ItemType Directory -Force '.tmp' | Out-Null

& 'D:\Anaconda\python.exe' -m pytest `
  tests\natural_memory_benchmark\test_identity_resolution.py `
  tests\natural_memory_benchmark\test_extended_amr_v3_adapter.py `
  tests\natural_memory_benchmark\test_identity_conformance_runner.py `
  -q --basetemp=.tmp\identity-focused

& 'D:\Anaconda\python.exe' -m pytest `
  tests\natural_memory_benchmark `
  -q --basetemp=.tmp\identity-full
```
