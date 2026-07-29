# Natural Identity Proposer Dev Repair and Fresh-v3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. This workspace is not a Git repository, so commit/worktree steps do not apply.

**Goal:** Freeze a dev-only conservative proposer policy, require it to pass all six dev cases, then evaluate it once on a new opaque-ID slice with six fresh hidden cases.

**Architecture:** Add one benchmark-only module for policy/prompt freezing and dev-slice preparation, plus one module for fresh-v3 source combination, opaque remapping, no-overlap validation, and preregistration. Reuse the existing proposal freezer, authority gate, scorer, and report renderer unchanged.

**Tech Stack:** Python 3.13, Pydantic 2.10.3, pytest 8.3.4, canonical JSON/SHA-256, existing natural identity contracts and immutable writers.

## Global Constraints

- Work only in `/public/home/wwb/KE-mem/KE-memory-next-prep-20260727` on H100.
- Policy changes may use only v2 dev and separately created diagnostic evidence.
- Freeze the passing policy and final prompt before authoring or inspecting fresh hidden cases.
- Do not reuse any v2 hidden case or hidden evidence-unit combination in fresh-v3 hidden.
- Keep the existing authority gate and scorer behavior unchanged.
- Model proposals cannot write merge, membership, or L2 state.
- Embedding cannot authorize identity, membership, or facts.
- `LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.
- Do not run external memory systems or access prior Fusion Memory material.

---

### Task 1: Dev-only Slice and Policy Freeze

**Files:**
- Create: `tools/natural_memory_benchmark/identity_proposer_policy.py`
- Create: `tests/natural_memory_benchmark/test_identity_proposer_policy.py`
- Modify: `tools/natural_memory_benchmark/cli.py`
- Create: `artifacts/identity-memory-experiment/dev-repair-v3/source-cases.json`
- Create: `artifacts/identity-memory-experiment/dev-repair-v3/public.json`
- Create: `artifacts/identity-memory-experiment/dev-repair-v3/authority.json`
- Create: `artifacts/identity-memory-experiment/dev-repair-v3/gold.json`
- Create: `artifacts/identity-memory-experiment/dev-repair-v3/manifest.json`
- Create: `artifacts/identity-memory-experiment/dev-repair-v3/policy-v1.md`
- Create: `artifacts/identity-memory-experiment/dev-repair-v3/dev-proposer-prompt-v1.md`
- Create: `artifacts/identity-memory-experiment/dev-repair-v3/final-proposer-prompt-v1.md`
- Create: `artifacts/identity-memory-experiment/dev-repair-v3/policy-freeze-v1.json`

**Interfaces:**
- Produces: `prepare_identity_dev_slice(v2_source_path: Path, output_root: Path, *, workspace_root: Path | None = None) -> dict[str, Any]`.
- Produces: `freeze_identity_proposer_policy(policy_path: Path, dev_prompt_path: Path, final_prompt_path: Path, output_path: Path, *, dev_public_path: Path, final_public_path: Path, dev_run_id: str, final_run_id: str, proposer_id: str, proposer_version: str) -> dict[str, Any]`.

- [x] **Step 1: Write RED tests for exact dev filtering and immutable replay**

```python
def test_prepare_identity_dev_slice_keeps_only_v2_dev_cases(tmp_path):
    root = tmp_path / "dev-repair-v3"
    result = prepare_identity_dev_slice(V2_SOURCE, root, workspace_root=Path("."))
    public = load_json(root / "public.json")
    assert result["case_count"] == 6
    assert {case["split"] for case in public["cases"]} == {"dev"}
    assert [case["case_id"] for case in public["cases"]] == V2_DEV_CASE_IDS
    assert all((root / name).stat().st_mode & 0o777 == 0o444 for name in SLICE_FILES)
```

- [x] **Step 2: Write RED tests for policy hash binding and prompt invariants**

```python
def test_freeze_policy_binds_same_policy_into_dev_and_final_prompts(tmp_path):
    dev_root = tmp_path / "dev-repair-v3"
    prepare_identity_dev_slice(V2_SOURCE, dev_root, workspace_root=Path("."))
    policy_path = tmp_path / "policy.md"
    policy_path.write_text("Merge only with explicit same-entity evidence.\n", encoding="utf-8")
    policy_path.chmod(0o444)
    result = freeze_identity_proposer_policy(
        policy_path,
        tmp_path / "dev-prompt.md",
        tmp_path / "final-prompt.md",
        tmp_path / "policy-freeze.json",
        dev_public_path=dev_root / "public.json",
        final_public_path=Path("artifacts/identity-memory-experiment/natural-v3-fresh/public.json"),
        dev_run_id="run-dev-v1",
        final_run_id="run-fresh-v3",
        proposer_id="codex-gpt-5.6-sol",
        proposer_version="2026-07-27-policy-v1",
    )
    assert result["policy_sha256"] == sha256_file(policy_path)
    assert result["fresh_hidden_authored_before_policy_freeze"] is False
    assert (tmp_path / "policy-freeze.json").stat().st_mode & 0o777 == 0o444
```

- [x] **Step 3: Run RED**

Run:

```bash
.venv-h100/bin/python -m pytest tests/natural_memory_benchmark/test_identity_proposer_policy.py -q --import-mode=importlib -p no:cacheprovider --basetemp .tmp/identity-policy-red
```

Expected: collection fails because `identity_proposer_policy` does not exist.

- [x] **Step 4: Implement the dev preparer and policy freezer**

The dev preparer loads the frozen v2 source, preserves only `split=dev`, changes only `dataset_id` to `natural-identity-membership-dev-repair-v3`, calls `freeze_natural_identity_slice()`, validates the slice, and freezes its five files. The policy freezer requires the policy and dev public input to be read-only, renders both prompts from one policy byte sequence, records all four hashes and fixed metadata in `natural-identity-proposer-policy-freeze-v1`, and freezes all outputs.

- [x] **Step 5: Register CLI commands and run GREEN**

Add:

```text
prepare-identity-dev-slice --v2-source --output-root --workspace-root
freeze-identity-proposer-policy --policy --dev-prompt --final-prompt --output --dev-public --final-public --dev-run-id --final-run-id --proposer-id --proposer-version
```

Run the Task 1 test command again. Expected: all tests pass.

- [x] **Step 6: Freeze policy v1 before fresh hidden authoring**

Policy v1 must encode the exact conservative identity/membership rules in the design. Use fixed run IDs:

```text
run-20260727T151000Z-codex-gpt-5-6-sol-dev-policy-v1
run-20260727T153000Z-codex-gpt-5-6-sol-fresh-v3
```

Freeze `policy-v1.md`, both prompts, and `policy-freeze-v1.json`; record their SHA-256 values before opening unused source evidence for hidden authoring.

### Task 2: Isolated Dev Proposer and Gate

**Files:**
- Create: `artifacts/identity-memory-experiment/dev-repair-v3/model-runs/run-20260727T151000Z-codex-gpt-5-6-sol-dev-policy-v1/dispatch.json`
- Create: `artifacts/identity-memory-experiment/dev-repair-v3/model-runs/run-20260727T151000Z-codex-gpt-5-6-sol-dev-policy-v1/proposals.json`
- Create: `artifacts/identity-memory-experiment/dev-repair-v3/model-runs/run-20260727T151000Z-codex-gpt-5-6-sol-dev-policy-v1/provenance.json`
- Create: `artifacts/identity-memory-experiment/dev-repair-v3/model-runs/run-20260727T151000Z-codex-gpt-5-6-sol-dev-policy-v1/score.json`
- Create: `artifacts/identity-memory-experiment/dev-repair-v3/model-runs/run-20260727T151000Z-codex-gpt-5-6-sol-dev-policy-v1/report.md`

**Interfaces:**
- Consumes: existing `prepare-identity-model-dispatch`, `freeze-identity-model-proposals`, and `score-identity-proposals` commands.
- Produces: a frozen dev decision that either advances policy v1 or creates a new policy version.

- [x] **Step 1: Freeze the dev dispatch**

Run `prepare-identity-model-dispatch` with the frozen dev public/prompt paths and `fresh-agent-no-history-declarative`.

- [x] **Step 2: Dispatch a `fork_turns="none"` proposer**

The proposer reads only the frozen dev prompt and dev public file and writes exactly six staged proposals. It cannot read authority, gold, source, v2 hidden, prior scores, reports, or plans.

- [x] **Step 3: Freeze dev proposals before scoring**

Run the existing proposal freezer and verify proposals/provenance are `0444`.

- [x] **Step 4: Score and enforce the dev gate**

Run the existing scorer. Advance only if raw accuracy, abstention F1, and evidence exactness are all `1.0`, with zero raw critical false merge/membership. If any condition fails, classify only dev errors, create `policy-v2.md`, and repeat Tasks 1.6 through 2 without inspecting fresh hidden.

- [x] **Step 5: Replay and freeze dev score/report**

Score to isolated temporary paths, require `cmp` equality, then set formal score/report to `0444`.

### Task 3: Fresh Hidden Source and Opaque-v3 Preparation

**Files:**
- Create: `tools/natural_memory_benchmark/identity_proposal_fresh.py`
- Create: `tests/natural_memory_benchmark/test_identity_proposal_fresh.py`
- Modify: `tools/natural_memory_benchmark/cli.py`
- Create: `artifacts/identity-memory-experiment/natural-v3-fresh/hidden-source-cases.json`
- Create: `artifacts/identity-memory-experiment/natural-v3-fresh/source-cases.json`
- Create: `artifacts/identity-memory-experiment/natural-v3-fresh/opaque-id-map.json`
- Create: `artifacts/identity-memory-experiment/natural-v3-fresh/preregistration.json`
- Create: `artifacts/identity-memory-experiment/natural-v3-fresh/public.json`
- Create: `artifacts/identity-memory-experiment/natural-v3-fresh/authority.json`
- Create: `artifacts/identity-memory-experiment/natural-v3-fresh/gold.json`
- Create: `artifacts/identity-memory-experiment/natural-v3-fresh/manifest.json`

**Interfaces:**
- Produces: `prepare_fresh_identity_slice(v2_source_path: Path, hidden_source_path: Path, output_root: Path, *, policy_freeze_path: Path, workspace_root: Path | None = None) -> dict[str, Any]`.
- Produces: `validate_fresh_identity_slice(v2_source_path: Path, hidden_source_path: Path, root: Path, *, policy_freeze_path: Path, workspace_root: Path | None = None) -> dict[str, Any]`.

- [x] **Step 1: Write RED tests for composition, action balance, and no overlap**

```python
def test_prepare_fresh_slice_has_balanced_new_hidden_and_no_v2_overlap(tmp_path):
    root = tmp_path / "natural-v3-fresh"
    result = prepare_fresh_identity_slice(
        V2_SOURCE,
        FRESH_HIDDEN_SOURCE,
        root,
        policy_freeze_path=POLICY_FREEZE,
        workspace_root=Path("."),
    )
    assert result["dev_count"] == 6
    assert result["hidden_count"] == 6
    assert result["hidden_action_distribution"] == {
        "merge": 1,
        "keep_distinct": 1,
        "abstain_identity": 1,
        "include": 1,
        "exclude": 1,
        "abstain_membership": 1,
    }
    assert result["v2_id_overlap_count"] == 0
    assert result["v2_hidden_evidence_overlap_count"] == 0
```

- [x] **Step 2: Write RED tests for policy chronology and coordinated drift**

Tests must reject a writable/changed policy freeze, a policy hash mismatch, a reused v2 hidden evidence combination, malformed or non-derived v3 IDs, coordinated public/authority/gold drift with refreshed local hashes, and any formal writable artifact.

- [x] **Step 3: Run RED**

Run:

```bash
.venv-h100/bin/python -m pytest tests/natural_memory_benchmark/test_identity_proposal_fresh.py -q --import-mode=importlib -p no:cacheprovider --basetemp .tmp/identity-fresh-red
```

Expected: collection fails because `identity_proposal_fresh` does not exist.

- [x] **Step 4: Author six hidden cases after policy freeze**

Use only unused frozen source evidence. Create exactly three identity and three membership cases with the action distribution fixed in the design. Every quote, source coordinate, and LoCoMo actor binding must pass the existing source replay. Do not reuse `LONGMEMEVAL-6d550036` or any v2 hidden case/evidence combination.

- [x] **Step 5: Implement fresh preparation and validation**

Use dataset ID `natural-identity-membership-fresh-v3` and namespace `natural-identity-membership-fresh-v3:2026-07-27`. Combine unchanged v2 dev semantics with six fresh hidden cases, derive all new case/mention IDs, freeze through the existing base slice builder, compare canonical derived artifacts, validate action balance/no-overlap/policy hashes/protected hashes, and set the eight formal files to `0444`.

- [x] **Step 6: Register CLI commands and run GREEN**

Add:

```text
prepare-natural-identity-fresh-slice --v2-source --hidden-source --output-root --policy-freeze --workspace-root
validate-natural-identity-fresh-slice --v2-source --hidden-source --root --policy-freeze --workspace-root
```

Run the Task 3 test command again. Expected: all tests pass.

- [x] **Step 7: Prepare and freeze the formal fresh-v3 slice**

Run the new preparation CLI exactly once, then both fresh and base validators. Require 12 cases, 6 dev, 6 hidden, correct action distribution, zero v2 ID overlap, zero v2 hidden evidence overlap, source replay valid, and policy chronology valid.

### Task 4: Final Isolated Proposer, Freeze, and Score

**Files:**
- Create: `artifacts/identity-memory-experiment/natural-v3-fresh/model-runs/run-20260727T153000Z-codex-gpt-5-6-sol-fresh-v3/dispatch.json`
- Create: `artifacts/identity-memory-experiment/natural-v3-fresh/model-runs/run-20260727T153000Z-codex-gpt-5-6-sol-fresh-v3/proposals.json`
- Create: `artifacts/identity-memory-experiment/natural-v3-fresh/model-runs/run-20260727T153000Z-codex-gpt-5-6-sol-fresh-v3/provenance.json`
- Create: `artifacts/identity-memory-experiment/natural-v3-fresh/model-runs/run-20260727T153000Z-codex-gpt-5-6-sol-fresh-v3/score.json`
- Create: `artifacts/identity-memory-experiment/natural-v3-fresh/model-runs/run-20260727T153000Z-codex-gpt-5-6-sol-fresh-v3/report.md`
- Create: `artifacts/identity-memory-experiment/natural-v3-fresh/model-runs/run-20260727T153000Z-codex-gpt-5-6-sol-fresh-v3/error-analysis.md`

- [x] **Step 1: Freeze final dispatch against the pre-frozen prompt and fresh public**

Require the final prompt hash to equal the value already recorded before hidden authoring.

- [x] **Step 2: Dispatch a new `fork_turns="none"` proposer**

The proposer reads only the final prompt and fresh public file and writes exactly 12 staged proposals.

- [x] **Step 3: Freeze proposals/provenance before scoring**

Run the existing freezer, validate exact coverage and case-local evidence IDs, and require `0444`.

- [x] **Step 4: Run the unchanged scorer**

Read authority/gold only after proposal freeze. Report raw proposer quality and deterministic gate safety separately. Do not authorize writes even if both pass.

- [x] **Step 5: Classify errors and replay outputs**

Classify false merge, false membership, abstention, and evidence errors. Replay score/report to temporary paths, require byte equality, freeze formal outputs, and write a read-only error analysis.

### Task 5: Full Verification, Documentation, and Review

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `安排.md`
- Modify: this plan with completion evidence

- [x] **Step 1: Run focused and full tests**

Run the new policy/fresh tests, existing proposal tests, and complete `tests/natural_memory_benchmark` with isolated `--basetemp` paths.

- [x] **Step 2: Run validators and protected-hash checks**

Run dev, fresh, base identity, slice, and ledger validators. Recheck all v1/v2/identity-v1/authoritative-v5 protected hashes and formal permissions.

- [x] **Step 3: Update state documents**

Record policy hashes, chronology, fresh source/no-overlap evidence, raw metrics, gated metrics, error branch, isolation limitation, `核心影响：无`, and the next authorized action.

- [x] **Step 4: Request final read-only review**

The reviewer checks dev-only contamination control, policy chronology, hidden freshness, ID opacity, source replay, phase order, scorer reproducibility, permissions, protected hashes, and raw/gated interpretation. Fix all Critical/Important findings and rerun full verification.

Review evidence: the first read-only review found no actual contamination or protected-artifact drift, but identified two Important enforcement gaps: a schema-valid substituted v2 source could feed dev preparation, and chronology covered only policy/hidden mtimes rather than the complete passing dev run. Both were repaired with TDD. Dev preparation now requires a read-only byte match to the independently validated frozen opaque-v2 source. Fresh validation now requires `policy freeze < every passing dev-run artifact < hidden source`; the formal run is additionally bound by read-only `chronology-receipt-v3.json` with fixed SHA-256 `ad7e5e9fd8865be16afbb4e73416600455bdf7b909db60df31fe7fea77b04240`. The receipt explicitly records `trusted_timestamp_authority=false`, so it is tamper detection for the observed filesystem chronology, not an external trusted timestamp or independent proof of declarative model isolation. A remediation review then found that byte-identical temporary input paths could bypass receipt selection for the formal root; a fourth red/green regression test now requires exact formal v2, policy-freeze, and hidden-source paths whenever the formal fresh root is prepared or validated. The second review reported no remaining Critical/Important findings. Final verification: focused `42 passed`, full `tests/natural_memory_benchmark` `175 passed`; fresh, opaque, base identity, slice, and ledger validators valid; score/report replay byte-identical; 25 protected hashes unchanged; 26 formal/audit files non-writable; `LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.
