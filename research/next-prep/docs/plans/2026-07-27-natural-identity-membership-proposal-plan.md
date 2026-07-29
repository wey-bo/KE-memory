# Natural Identity and Membership Proposal v1 Implementation Plan

**Goal:** Freeze a 12-case natural identity/membership proposal slice and implement a proposal-only reference baseline, deterministic authority gate, scorer, report, and CLI without changing the core memory skeleton.

**Architecture:** Add benchmark-side modules parallel to the existing identity conformance runner. Public proposal input, gate authority, and gold labels remain separate. Candidate generation reads public data only; acceptance and scoring happen afterward.

**Tech Stack:** Python 3.13, Pydantic v2, pytest, canonical JSON/SHA-256, existing immutable artifact helpers.

---

## TODO 1: Freeze design and source cases

**Files:**

- Create: `docs/designs/2026-07-27-natural-identity-membership-proposal-design.md`
- Create: `artifacts/identity-memory-experiment/natural-v1/source-cases.json`
- Create: `docs/plans/2026-07-27-natural-identity-membership-proposal-plan.md`

Steps:

1. Freeze 6 dev and 6 hidden cases from authorized source snapshots.
2. Record exact evidence unit IDs, source refs, quotes, actor locators, authority facts, and gold labels.
3. Pre-register separate safety and proposal-quality decisions.
4. Mark `核心影响：无`.

## TODO 2: Write RED tests

**Files:**

- Create: `tests/natural_memory_benchmark/test_identity_proposal.py`
- Create: `tests/natural_memory_benchmark/test_identity_proposal_runner.py`

Test list:

1. Freeze produces public/authority/gold separation and deterministic hashes.
2. Quote/source and LoCoMo actor replay reject tampering.
3. Proposal contracts reject invalid action/relation combinations and missing evidence.
4. Unsafe lexical merge and subject-mismatch membership cannot pass the gate.
5. Reference proposer reads public input only and is deterministic.
6. Scorer reports raw and gated metrics separately.
7. Safety readiness can pass while proposal-quality readiness fails.
8. Frozen v5 hash and `structured_l2_identity_unresolved` remain preserved.
9. File writers are immutable and deterministic.
10. CLI freeze, validate, propose, and score commands work.

Run RED:

```powershell
& 'D:\Anaconda\python.exe' -m pytest `
  tests\natural_memory_benchmark\test_identity_proposal.py `
  tests\natural_memory_benchmark\test_identity_proposal_runner.py `
  -q --basetemp=.tmp\identity-proposal-red
```

Expected: import/command failures because the new modules and CLI commands do not exist.

## TODO 3: Implement contracts, freeze, gate, and scorer

**Files:**

- Create: `tools/natural_memory_benchmark/identity_proposal.py`
- Create: `tools/natural_memory_benchmark/identity_proposal_runner.py`
- Modify: `tools/natural_memory_benchmark/cli.py`

Steps:

1. Add strict public, authority, gold, proposal, gated-decision, and score models.
2. Resolve evidence units and exact quotes from `gold-evidence.json`.
3. Validate LoCoMo actor IDs against the frozen raw snapshot.
4. Write immutable public/authority/gold/manifest files.
5. Implement the public-only reference proposer.
6. Implement evidence-complete identity/membership acceptance rules.
7. Compute raw/gated safety and proposal-quality metrics plus v5 regression.
8. Add Markdown report rendering and immutable file helpers.
9. Register CLI commands:
   - `freeze-natural-identity-slice`
   - `validate-natural-identity-slice`
   - `run-identity-proposal-reference`
   - `score-identity-proposals`

Run GREEN with the same focused command and require all tests to pass.

## TODO 4: Generate formal artifacts

Steps:

1. Freeze `public.json`, `authority.json`, `gold.json`, and `manifest.json`.
2. Run the reference proposer with a fixed run ID.
3. Score proposals and write formal JSON/report artifacts.
4. Replay all generated files into an isolated `.tmp` directory.
5. Compare canonical bytes and SHA-256 values.

## TODO 5: Full verification and documentation

Steps:

1. Run focused proposal tests.
2. Run all `tests/natural_memory_benchmark` tests.
3. Validate natural slice-v1 and the external-results ledger.
4. Verify the frozen identity v1 and authoritative v5 hashes remain unchanged.
5. Update `README.md`, `AGENTS.md`, and `安排.md` with implemented capability and claim boundaries.
6. Record next TODO as a real proposal-only model run using the frozen public file; no automatic merge path is authorized.

No Git commit/worktree steps apply because this workspace is not a usable Git repository.

## Completion evidence

Status: completed on 2026-07-27. Core impact: `none`.

- RED: focused tests failed only because `identity_proposal` did not yet exist.
- GREEN: `test_identity_proposal.py` and `test_identity_proposal_runner.py` are 10 passed.
- Full regression: `tests/natural_memory_benchmark` is 143 passed.
- Source and integrity checks: natural slice-v1 and external-results ledger are valid; natural identity source replay and manifest integrity are valid.
- Formal run: `run-20260727T090000Z-natural-identity-reference-v1`.
- Decisions: `gate_safety_ready=true`; `proposal_quality_ready=false`.
- Metrics: raw action accuracy 0.8333333333333334; gated action accuracy 1.0; raw/gated critical false merge 1/0; raw/gated critical false membership 0/0; gate interventions 2; proposal evidence exact rate 1.0; structural fallback count 0.
- Regressions: frozen v5 SHA-256 remains `3ec6656c037200f8591fac44cd7e1e4bf2caa3aa9447f3fa5ba9854324d4cc33`; identity v1 result/report hashes remain `e7cc632ae20f6436156fcd9c777352eac0f8286e63cb24f42ddee05875ae633c` and `bc032cf6a5590a8d1f12adf5d523af9da65d599b66ceddac52667d213b920ae8`; `structured_l2_identity_unresolved` is preserved.
- Replay: all seven generated files are byte-identical in an isolated replay.
- Formal score/report SHA-256: `d346eb0f0d277be39fad363da8f4f89f98b0fc4a49be2a95c0970f62abf562b2` and `45d0dd7452873e0df8545b9930b19aad6938b2ea764cc2177a16de3e05ba380a`.

Next TODO: run a real proposal-only model against frozen `public.json`. Candidate output remains non-authoritative; no automatic merge or membership write path is authorized.
