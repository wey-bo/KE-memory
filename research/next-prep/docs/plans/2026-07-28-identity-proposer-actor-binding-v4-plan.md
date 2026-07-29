# Identity Proposer Actor-Binding v4 Implementation Plan

> **For agentic workers:** Execute task-by-task with TDD and a read-only review after each formal freeze boundary.

**Goal:** Add independent actor-binding dev coverage, qualify policy-v4, and only after a passing dev run evaluate it on a newly frozen fresh-v4 hidden slice.

**Architecture:** Add a benchmark-only v4 dev builder and validator while reusing the current proposal schema, model-run freezer, deterministic authority gate, scorer, and report renderer. Generalize policy-freeze case counts without changing existing v3 artifacts or their validation.

**Tech Stack:** Python 3.13, Pydantic 2.10.3, pytest 8.3.4, canonical JSON/SHA-256, immutable file writers, existing natural identity scorer/gate.

## Global Constraints

- H100 workspace only; no old Fusion Memory access and no external-system reruns.
- No fresh-v3 hidden evidence or surface form may enter v4 dev data or policy examples.
- No automatic merge, membership, or L2 writes.
- Embedding is non-authoritative.
- `LONGMEMEVAL-6d550036` remains unresolved.
- Fresh-v4 hidden authoring starts only after the formal v4 dev score passes.

---

### Task 1: Freeze Independent Actor-Binding Diagnostic Data

**Files:**
- Create: `artifacts/identity-memory-experiment/dev-repair-v4/diagnostic-gold-evidence.json`
- Create: `artifacts/identity-memory-experiment/dev-repair-v4/diagnostic-source-cases.json`
- Create: `artifacts/identity-memory-experiment/dev-repair-v4/combined-gold-evidence.json`
- Create: `artifacts/identity-memory-experiment/dev-repair-v4/preregistration.json`
- Create: `tools/natural_memory_benchmark/identity_proposer_policy_v4.py`
- Create: `tests/natural_memory_benchmark/test_identity_proposer_policy_v4.py`

**Interfaces:**
- Produces: `prepare_identity_dev_v4(...) -> dict[str, Any]`
- Produces: `validate_identity_dev_v4(...) -> dict[str, Any]`

- [x] Write failing tests for exact action balance, raw-source actor replay, prior-hidden evidence overlap rejection, deterministic replay, protected hashes, and read-only formal artifacts.
- [x] Run the focused tests and confirm the missing v4 builder failures.
- [x] Implement strict diagnostic models and the combined evidence/source builder.
- [x] Freeze the formal 12-case dev slice and preregistration.
- [x] Run focused tests and the v4/base validators (`5 passed`; all identity tests `59 passed`).

### Task 2: Generalize and Freeze Policy v4

**Files:**
- Modify: `tools/natural_memory_benchmark/identity_proposer_policy.py`
- Modify: `tools/natural_memory_benchmark/cli.py`
- Modify: `tests/natural_memory_benchmark/test_identity_proposer_policy.py`
- Create: `artifacts/identity-memory-experiment/dev-repair-v4/policy-v4.md`
- Create: `artifacts/identity-memory-experiment/dev-repair-v4/dev-proposer-prompt-v4.md`
- Create: `artifacts/identity-memory-experiment/dev-repair-v4/final-proposer-prompt-v4.md`
- Create: `artifacts/identity-memory-experiment/dev-repair-v4/policy-freeze-v4.json`

**Interfaces:**
- `freeze_identity_proposer_policy(..., dev_dataset_id: str, dev_case_count: int, final_case_count: int)`

- [x] Write failing backward-compatibility and variable-case-count tests.
- [x] Run the tests and confirm current literal-count validation fails.
- [x] Generalize only policy-freeze metadata and prompt counts; preserve current defaults.
- [x] Freeze policy-v4 and both prompts after the diagnostic slice is read-only.
- [x] Verify policy/prompt hashes and chronology (`62 passed` across identity tests).

Execution preflight found that the H100 API does not expose `codex-gpt-5.6-sol`.
The immutable Codex-named freeze was not dispatched. The actual run is bound to
`policy-freeze-v4-claude.json` and the same policy bytes using the available
`claude-sonnet-4-6` model; chronology must bind only this executed freeze.

### Task 3: Run and Score the v4 Dev Proposer

**Files:**
- Create: `artifacts/identity-memory-experiment/dev-repair-v4/model-runs/run-20260728T012500Z-claude-sonnet-4-6-dev-policy-v4/dispatch.json`
- Create: `artifacts/identity-memory-experiment/dev-repair-v4/model-runs/run-20260728T012500Z-claude-sonnet-4-6-dev-policy-v4/api-transport.json`
- Create: `artifacts/identity-memory-experiment/dev-repair-v4/model-runs/run-20260728T012500Z-claude-sonnet-4-6-dev-policy-v4/proposals.json`
- Create: `artifacts/identity-memory-experiment/dev-repair-v4/model-runs/run-20260728T012500Z-claude-sonnet-4-6-dev-policy-v4/provenance.json`
- Create: `artifacts/identity-memory-experiment/dev-repair-v4/model-runs/run-20260728T012500Z-claude-sonnet-4-6-dev-policy-v4/score.json`
- Create: `artifacts/identity-memory-experiment/dev-repair-v4/model-runs/run-20260728T012500Z-claude-sonnet-4-6-dev-policy-v4/report.md`
- Create: `artifacts/identity-memory-experiment/dev-repair-v4/model-runs/run-20260728T012500Z-claude-sonnet-4-6-dev-policy-v4/error-analysis.md`

- [x] Freeze an allowlisted dispatch using only the dev prompt/public hashes.
- [x] Invoke a fresh proposer with no inherited history and one request message.
- [x] Validate exact 12-case coverage and case-local evidence IDs, then freeze proposals/provenance before scoring.
- [x] Run the unchanged scorer and separately report raw quality and gate safety.
- [x] On the first dev gate failure, stop before hidden authoring, classify the false abstention, repair only on dev, and rerun. Policy-v4.1 passed both gates with all raw and gated metrics at `1.0` and zero critical errors.

### Task 4: Prepare Fresh-v4 Only After Dev Pass

**Files:**
- Create only after Task 3 passes: `artifacts/identity-memory-experiment/natural-v4-fresh/hidden-source-cases.json`
- Create: `tools/natural_memory_benchmark/identity_proposal_fresh_v4.py`
- Create: `tests/natural_memory_benchmark/test_identity_proposal_fresh_v4.py`
- Create: formal fresh-v4 source/mapping/preregistration/public/authority/gold/manifest files

- [x] Write failing tests for policy/dev chronology, hidden freshness, fixed namespace IDs, no overlap with v2/fresh-v3 hidden, balanced hidden actions, and formal path binding.
- [x] Author six new hidden cases with one action from each identity/membership family and at least two cross-session cases.
- [x] Implement and run the fresh-v4 validator.
- [x] Freeze all formal files read-only (`4 passed`; all identity tests `66 passed`).

### Task 5: Run Fresh-v4 and Close the Milestone

- [x] Run a second zero-history proposer using only the frozen final prompt and fresh-v4 public JSON.
- [x] Freeze proposals/provenance before authority/gold scoring.
- [x] Score and classify raw versus gated results.
- [x] Replay score/report byte-identically and verify protected hashes/permissions.
- [x] Run focused and full identity regression tests plus formal validators and a final read-only review.
- [x] Update `README.md`, `AGENTS.md`, `安排.md`, and this plan with exact hashes, metrics, limitations, and the next authorized action.

Final run: `run-20260728T031000Z-claude-sonnet-4-6-fresh-policy-v4-1`.
Raw and gated action accuracy, abstention F1, and evidence exactness were all
`1.0`; critical false merge/membership counts, gate interventions, and structural
fallbacks were all `0`. Proposals/score/report SHA-256 were
`aba38ed3f30fa5faf1208ff6f3ae9847822854a4d5b166679c755e6c33a386d2`,
`6a47808b49302d1c14e34dad4d67c062484909892c7de8137eed795e05259b75`,
and `5851955aebc8dc0726cb7ae617c2b3fdcb3067b5509e947e92cd2a59ad328007`.
This authorizes only a read-only candidate-generation integration assessment;
automatic merge, membership, and L2 writes remain unauthorized.
