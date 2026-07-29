# Natural Identity and Membership Opaque-ID v2 Implementation Plan

Status: complete. Formal evaluation, review hardening, and verification finished on 2026-07-27.

> **For agentic workers:** Execute task-by-task with fresh verification at every checkpoint. The workspace is not a Git repository, so commit/worktree steps do not apply.

**Goal:** Prepare a semantically identical opaque-ID v2 slice, run a no-history isolated model proposer, freeze its proposals before scoring, and report raw proposal quality separately from deterministic gate safety.

**Architecture:** Add one benchmark-only module for deterministic v1-to-v2 source remapping and one for public-only proposal validation/provenance freezing. Reuse the existing v1 freeze contracts, authority gate, scorer, and report renderer unchanged. Formal artifacts are phase-frozen under a new `natural-v2` root.

**Tech Stack:** Python 3.13, Pydantic 2.10.3, pytest 8.3.4, canonical JSON/SHA-256, existing immutable artifact helpers and natural identity scorer.

## Global Constraints

- Work only in `/public/home/wwb/KE-mem/KE-memory-next-prep-20260727` on H100.
- Do not modify or overwrite any v1 input, run, or protected experiment artifact.
- Do not modify the core ontology, dynamic extension, L1/L2 extraction, question handling, symbolic retrieval, guarded embedding fallback, identity authority gate, or scorer behavior.
- Model proposals are non-authoritative and cannot write merge, membership, or L2 state.
- Embedding cannot authorize facts, identity, or membership.
- `LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.
- Do not run external memory systems or access prior Fusion Memory material.
- The model proposer receives no conversation history and may read only v2 `public.json` plus its frozen output contract.

---

### Task 1: Deterministic Opaque Slice Preparation

**Files:**
- Create: `tools/natural_memory_benchmark/identity_proposal_opaque.py`
- Create: `tests/natural_memory_benchmark/test_identity_proposal_opaque.py`

**Interfaces:**
- Consumes: v1 `SourceConfig`, `freeze_natural_identity_slice()`, `validate_natural_identity_slice()`, `canonical_json_bytes()`, `sha256_file()`, and immutable JSON writers.
- Produces: `derive_opaque_id()`, `prepare_opaque_identity_slice()`, and `validate_opaque_identity_slice()`.

- [x] **Step 1: Write RED tests for deterministic opaque IDs and controlled equivalence**

```python
def test_prepare_is_deterministic_opaque_and_semantically_equivalent(tmp_path):
    root = tmp_path / "natural-v2"
    first = prepare_opaque_identity_slice(V1_SOURCE, root, workspace_root=Path("."))
    second = prepare_opaque_identity_slice(V1_SOURCE, root, workspace_root=Path("."))
    assert first == second
    public = load_json(root / "public.json")
    assert all(CASE_ID_RE.fullmatch(case["case_id"]) for case in public["cases"])
    assert all(
        MENTION_ID_RE.fullmatch(mention["mention_id"])
        for case in public["cases"]
        for mention in case["mentions"]
    )
    assert validate_opaque_identity_slice(V1_SOURCE, root, workspace_root=Path("."))["semantic_equivalence_valid"] is True
```

- [x] **Step 2: Write RED tests for malformed IDs, old-ID residue, and conflicting replay**

```python
def test_validate_rejects_non_opaque_ids_and_semantic_drift(tmp_path):
    root = tmp_path / "natural-v2"
    prepare_opaque_identity_slice(V1_SOURCE, root, workspace_root=Path("."))
    public = load_json(root / "public.json")
    public["cases"][0]["case_id"] = "case-distinct"
    public_path = root / "public.json"
    public_path.chmod(0o644)
    public_path.write_bytes(canonical_json_bytes(public))
    with pytest.raises(ValueError, match="opaque case id"):
        validate_opaque_identity_slice(V1_SOURCE, root, workspace_root=Path("."))

def test_prepare_rejects_conflicting_existing_artifact(tmp_path):
    root = tmp_path / "natural-v2"
    prepare_opaque_identity_slice(V1_SOURCE, root, workspace_root=Path("."))
    mapping_path = root / "opaque-id-map.json"
    mapping_path.chmod(0o644)
    mapping_path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(FileExistsError, match="immutable artifact differs"):
        prepare_opaque_identity_slice(V1_SOURCE, root, workspace_root=Path("."))
```

- [x] **Step 3: Run RED and confirm the module import fails**

Run:

```bash
.venv-h100/bin/python -m pytest tests/natural_memory_benchmark/test_identity_proposal_opaque.py -q --import-mode=importlib -p no:cacheprovider --basetemp .tmp/opaque-v2-red
```

Expected: collection fails because `identity_proposal_opaque` does not exist.

- [x] **Step 4: Implement deterministic remapping and validation**

Use these exact public definitions:

```python
OPAQUE_DATASET_ID = "natural-identity-membership-opaque-v2"
OPAQUE_NAMESPACE = "natural-identity-membership-opaque-v2:2026-07-27"
CASE_ID_RE = re.compile(r"case-[0-9a-f]{16}")
MENTION_ID_RE = re.compile(r"mention-[0-9a-f]{16}")

def derive_opaque_id(namespace: str, kind: Literal["case", "mention"], ordinal: int, source_id: str) -> str:
    material = f"{namespace}\0{kind}\0{ordinal}\0{source_id}".encode("utf-8")
    prefix = "case" if kind == "case" else "mention"
    return f"{prefix}-{hashlib.sha256(material).hexdigest()[:16]}"
```

Implement `prepare_opaque_identity_slice(v1_source_path: Path, output_root: Path, *, workspace_root: Path | None = None, namespace: str = OPAQUE_NAMESPACE) -> dict[str, Any]` and `validate_opaque_identity_slice(v1_source_path: Path, v2_root: Path, *, workspace_root: Path | None = None) -> dict[str, Any]`. The preparer must remap source `case_id`, mention `mention_id`, and authority `required_mention_ids`; write `source-cases.json` and `opaque-id-map.json`; call the existing freeze function; verify reverse-mapped source equality; scan public for v1 ID residue; write a preregistration containing thresholds, claim boundaries, protected/v1/v2 hashes, and validation flags; and set the seven slice artifacts to mode `0444`. The proposer prompt is frozen separately before model dispatch.

- [x] **Step 5: Run GREEN and full existing proposal tests**

```bash
.venv-h100/bin/python -m pytest tests/natural_memory_benchmark/test_identity_proposal_opaque.py tests/natural_memory_benchmark/test_identity_proposal.py tests/natural_memory_benchmark/test_identity_proposal_runner.py -q --import-mode=importlib -p no:cacheprovider --basetemp .tmp/opaque-v2-green
```

Expected: all new tests and the existing 10 proposal tests pass.

### Task 2: Public-Only Model Proposal Freezing and Provenance

**Files:**
- Create: `tools/natural_memory_benchmark/identity_model_run.py`
- Create: `tests/natural_memory_benchmark/test_identity_model_run.py`
- Modify: `tools/natural_memory_benchmark/cli.py`

**Interfaces:**
- Consumes: `PublicIdentityPayload`, `IdentityProposalPayload`, canonical JSON, immutable writers, and SHA-256 helpers.
- Produces: `write_identity_model_dispatch()`, `freeze_identity_model_proposals()`, and four preparation/validation/freeze CLI commands.

- [x] **Step 1: Write RED tests for proposal coverage, evidence IDs, provenance, and permissions**

```python
def _write_valid_staged_proposals(tmp_path: Path, public_path: Path) -> Path:
    public = load_json(public_path)
    proposals = {
        "schema_version": "natural-identity-proposals-v1",
        "dataset_id": public["dataset_id"],
        "run_id": "run-test-opaque-v2",
        "proposer_id": "test-model",
        "proposer_version": "1",
        "case_count": public["case_count"],
        "proposals": [
            {
                "case_id": case["case_id"],
                "relation_kind": case["relation_kind"],
                "action": "abstain",
                "confidence": 0.5,
                "evidence_mention_ids": [item["mention_id"] for item in case["mentions"]],
                "reason_code": "insufficient_public_evidence",
                "proposer_id": "test-model",
                "proposer_version": "1",
                "run_id": "run-test-opaque-v2",
            }
            for case in public["cases"]
        ],
    }
    staged = tmp_path / "staged-proposals.json"
    staged.write_text(json.dumps(proposals), encoding="utf-8")
    return staged

def test_freeze_model_proposals_validates_public_only_contract(tmp_path):
    root = tmp_path / "natural-v2"
    prepare_opaque_identity_slice(V1_SOURCE, root, workspace_root=Path("."))
    public_path = root / "public.json"
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("Read public.json and emit proposal JSON.\n", encoding="utf-8")
    prompt_path.chmod(0o444)
    dispatch_path = tmp_path / "dispatch.json"
    write_identity_model_dispatch(
        public_path,
        prompt_path,
        dispatch_path,
        run_id="run-test-opaque-v2",
        proposer_id="test-model",
        proposer_version="1",
        isolation_context="fresh-agent-no-history-declarative",
    )
    staged = _write_valid_staged_proposals(tmp_path, public_path)
    result = freeze_identity_model_proposals(
        public_path,
        staged,
        tmp_path / "proposals.json",
        tmp_path / "provenance.json",
        prompt_path=prompt_path,
        isolation_context="fresh-agent-no-history-declarative",
        dispatch_path=dispatch_path,
    )
    assert result["case_count"] == 12
    assert result["allowed_input_sha256"]["public.json"] == sha256_file(public_path)
    assert (tmp_path / "proposals.json").stat().st_mode & 0o777 == 0o444
    assert (tmp_path / "provenance.json").stat().st_mode & 0o777 == 0o444

def test_freeze_model_proposals_rejects_unknown_evidence_id(tmp_path):
    root = tmp_path / "natural-v2"
    prepare_opaque_identity_slice(V1_SOURCE, root, workspace_root=Path("."))
    public_path = root / "public.json"
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("Read public.json and emit proposal JSON.\n", encoding="utf-8")
    prompt_path.chmod(0o444)
    dispatch_path = tmp_path / "dispatch.json"
    write_identity_model_dispatch(
        public_path,
        prompt_path,
        dispatch_path,
        run_id="run-test-opaque-v2",
        proposer_id="test-model",
        proposer_version="1",
        isolation_context="fresh-agent-no-history-declarative",
    )
    staged = _write_valid_staged_proposals(tmp_path, public_path)
    payload = load_json(staged)
    payload["proposals"][0]["evidence_mention_ids"] = ["mention-deadbeefdeadbeef"]
    staged.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown evidence mention id"):
        freeze_identity_model_proposals(public_path, staged, tmp_path / "out.json", tmp_path / "provenance.json", prompt_path=prompt_path, isolation_context="fresh-agent-no-history-declarative", dispatch_path=dispatch_path)
```

- [x] **Step 2: Run RED and confirm missing module/CLI failures**

```bash
.venv-h100/bin/python -m pytest tests/natural_memory_benchmark/test_identity_model_run.py -q --import-mode=importlib -p no:cacheprovider --basetemp .tmp/model-freeze-red
```

Expected: collection fails because `identity_model_run` does not exist.

- [x] **Step 3: Implement proposal validation and provenance freezing**

Implement `write_identity_model_dispatch(public_path: Path, prompt_path: Path, dispatch_path: Path, *, run_id: str, proposer_id: str, proposer_version: str, isolation_context: Literal["fresh-agent-no-history-declarative"]) -> dict[str, Any]` and `freeze_identity_model_proposals(public_path: Path, staged_proposals_path: Path, output_path: Path, provenance_path: Path, *, prompt_path: Path, isolation_context: Literal["fresh-agent-no-history-declarative"], dispatch_path: Path) -> dict[str, Any]`. The dispatch writer requires public and prompt to be read-only, records their hashes and model/run metadata, and freezes `dispatch.json`. The proposal freezer validates the dispatch hashes before processing proposals, then validates dataset, case count, exact case coverage, relation kind, proposal/run metadata, and that every proposed evidence mention ID belongs to its public case. Do not require evidence exactness here; omissions must remain visible to the scorer. Write canonical proposals and a `natural-identity-model-provenance-v1` sidecar containing public/prompt/dispatch/proposal hashes, model metadata, allowed inputs, declarative-isolation limitation, and `authority_or_gold_read_before_freeze=false`. Set both files to `0444`.

- [x] **Step 4: Register the three CLI commands and test the real subprocess path**

CLI arguments:

```text
prepare-natural-identity-opaque-slice --v1-source --output-root --workspace-root
validate-natural-identity-opaque-slice --v1-source --root --workspace-root
prepare-identity-model-dispatch --public --prompt --output --run-id --proposer-id --proposer-version --isolation-context
freeze-identity-model-proposals --public --staged-proposals --output --provenance --prompt --dispatch --isolation-context
```

Run:

```bash
.venv-h100/bin/python -m pytest tests/natural_memory_benchmark/test_identity_model_run.py tests/natural_memory_benchmark/test_identity_proposal_opaque.py -q --import-mode=importlib -p no:cacheprovider --basetemp .tmp/opaque-v2-cli-green
```

Expected: all model-freeze, opaque preparation, and CLI tests pass.

### Task 3: Freeze the Pre-Registered V2 Slice

**Files:**
- Create: `artifacts/identity-memory-experiment/natural-v2/source-cases.json`
- Create: `artifacts/identity-memory-experiment/natural-v2/opaque-id-map.json`
- Create: `artifacts/identity-memory-experiment/natural-v2/preregistration.json`
- Create: `artifacts/identity-memory-experiment/natural-v2/public.json`
- Create: `artifacts/identity-memory-experiment/natural-v2/authority.json`
- Create: `artifacts/identity-memory-experiment/natural-v2/gold.json`
- Create: `artifacts/identity-memory-experiment/natural-v2/manifest.json`

- [x] **Step 1: Run the new preparation CLI exactly once against the frozen v1 source**

```bash
.venv-h100/bin/python -m tools.natural_memory_benchmark.cli prepare-natural-identity-opaque-slice --v1-source artifacts/identity-memory-experiment/natural-v1/source-cases.json --output-root artifacts/identity-memory-experiment/natural-v2 --workspace-root .
```

Expected: `status=valid`, 12 cases, 6 dev, 6 hidden, identifier policy valid, semantic equivalence valid.

- [x] **Step 2: Run v2 opaque and existing natural identity validators**

```bash
.venv-h100/bin/python -m tools.natural_memory_benchmark.cli validate-natural-identity-opaque-slice --v1-source artifacts/identity-memory-experiment/natural-v1/source-cases.json --root artifacts/identity-memory-experiment/natural-v2 --workspace-root .
.venv-h100/bin/python -m tools.natural_memory_benchmark.cli validate-natural-identity-slice --root artifacts/identity-memory-experiment/natural-v2 --workspace-root .
```

Expected: both return `status=valid`.

- [x] **Step 3: Freeze the exact proposer prompt**

Create `model-runs/run-20260727T124023Z-codex-gpt-5-6-sol-opaque-v2/proposer-prompt.md` containing only the allowed public path, exact proposal schema/coverage rules, model/run metadata, destination staging path, and explicit prohibitions. Set it to `0444`, then run `prepare-identity-model-dispatch` to freeze `dispatch.json` with the exact public/prompt hashes before dispatch.

### Task 4: Run the Isolated Proposer, Freeze, Then Score

**Files:**
- Create: `artifacts/identity-memory-experiment/natural-v2/model-runs/run-20260727T124023Z-codex-gpt-5-6-sol-opaque-v2/proposer-prompt.md`
- Create: `artifacts/identity-memory-experiment/natural-v2/model-runs/run-20260727T124023Z-codex-gpt-5-6-sol-opaque-v2/dispatch.json`
- Create: `artifacts/identity-memory-experiment/natural-v2/model-runs/run-20260727T124023Z-codex-gpt-5-6-sol-opaque-v2/proposals.json`
- Create: `artifacts/identity-memory-experiment/natural-v2/model-runs/run-20260727T124023Z-codex-gpt-5-6-sol-opaque-v2/provenance.json`
- Create: `artifacts/identity-memory-experiment/natural-v2/model-runs/run-20260727T124023Z-codex-gpt-5-6-sol-opaque-v2/score.json`
- Create: `artifacts/identity-memory-experiment/natural-v2/model-runs/run-20260727T124023Z-codex-gpt-5-6-sol-opaque-v2/report.md`

- [x] **Step 1: Dispatch a `fork_turns="none"` proposer**

The proposer may read only the frozen prompt and v2 public file. It writes a staged proposal file under `.tmp/opaque-v2-model-stage/`. It must output exactly 12 `natural-identity-proposals-v1` records with `proposer_id=codex-gpt-5.6-sol`, `proposer_version=2026-07-27`, and the fixed run ID.

- [x] **Step 2: Freeze proposals and provenance before scoring**

```bash
.venv-h100/bin/python -m tools.natural_memory_benchmark.cli freeze-identity-model-proposals --public artifacts/identity-memory-experiment/natural-v2/public.json --staged-proposals .tmp/opaque-v2-model-stage/proposals.json --output artifacts/identity-memory-experiment/natural-v2/model-runs/run-20260727T124023Z-codex-gpt-5-6-sol-opaque-v2/proposals.json --provenance artifacts/identity-memory-experiment/natural-v2/model-runs/run-20260727T124023Z-codex-gpt-5-6-sol-opaque-v2/provenance.json --prompt artifacts/identity-memory-experiment/natural-v2/model-runs/run-20260727T124023Z-codex-gpt-5-6-sol-opaque-v2/proposer-prompt.md --dispatch artifacts/identity-memory-experiment/natural-v2/model-runs/run-20260727T124023Z-codex-gpt-5-6-sol-opaque-v2/dispatch.json --isolation-context fresh-agent-no-history-declarative
```

Expected: exact coverage and evidence-ID validation pass; proposals/provenance become `0444`.

- [x] **Step 3: Only now run the existing scorer**

```bash
.venv-h100/bin/python -m tools.natural_memory_benchmark.cli score-identity-proposals --root artifacts/identity-memory-experiment/natural-v2 --proposals artifacts/identity-memory-experiment/natural-v2/model-runs/run-20260727T124023Z-codex-gpt-5-6-sol-opaque-v2/proposals.json --output artifacts/identity-memory-experiment/natural-v2/model-runs/run-20260727T124023Z-codex-gpt-5-6-sol-opaque-v2/score.json --report artifacts/identity-memory-experiment/natural-v2/model-runs/run-20260727T124023Z-codex-gpt-5-6-sol-opaque-v2/report.md --workspace-root .
```

Expected: scorer reports `gate_safety_ready` and `proposal_quality_ready` separately. No result is interpreted before raw error categories are inspected.

- [x] **Step 4: Replay score/report to `.tmp` and compare bytes**

Run the same scorer with new temporary output/report paths, then require `cmp` exit code 0 for both files. Set formal score/report to `0444` only after byte equality is proven.

### Task 5: Full Verification, Review, and Documentation

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `安排.md`
- Modify: this plan with completion evidence

- [x] **Step 1: Run focused and full tests**

```bash
.venv-h100/bin/python -m pytest tests/natural_memory_benchmark/test_identity_proposal_opaque.py tests/natural_memory_benchmark/test_identity_model_run.py tests/natural_memory_benchmark/test_identity_proposal.py tests/natural_memory_benchmark/test_identity_proposal_runner.py -q --import-mode=importlib -p no:cacheprovider --basetemp .tmp/opaque-v2-focused
.venv-h100/bin/python -m pytest tests/natural_memory_benchmark -q --import-mode=importlib -p no:cacheprovider --basetemp .tmp/opaque-v2-full
```

Expected: focused tests and the complete natural-memory suite pass with zero failures.

- [x] **Step 2: Validate identity v2, natural slice, and ledger**

```bash
.venv-h100/bin/python -m tools.natural_memory_benchmark.cli validate-natural-identity-opaque-slice --v1-source artifacts/identity-memory-experiment/natural-v1/source-cases.json --root artifacts/identity-memory-experiment/natural-v2 --workspace-root .
.venv-h100/bin/python -m tools.natural_memory_benchmark.cli validate-natural-identity-slice --root artifacts/identity-memory-experiment/natural-v2 --workspace-root .
.venv-h100/bin/python -m tools.natural_memory_benchmark.cli validate-slice --root artifacts/natural-benchmark-slices --slice-id slice-v1
.venv-h100/bin/python -m tools.natural_memory_benchmark.cli validate-ledger --path artifacts/natural-benchmark-slices/external-results-ledger.json
```

Expected: all validators return `status=valid`.

- [x] **Step 3: Verify immutability and protected hashes**

Compare current v1 public/authority/gold/manifest, v1 model run, identity-v1, authoritative-v5, and reference hashes with their recorded values. Require all formal v2 pre-model and run artifacts to be `0444`.

- [x] **Step 4: Update state documents with measured results and exact claim boundaries**

Record raw metrics, gated metrics, hashes, isolation limitations, pass/fail branch, `核心影响：无`, non-authoritative status, and the next authorized action. Do not infer storage, product, UX, or external-system superiority.

- [x] **Step 5: Request final read-only review and address all Critical/Important findings**

The reviewer checks isolation evidence, ID opacity, semantic equivalence, phase order, scorer reproducibility, permissions, protected hashes, raw/gated interpretation, and documentation consistency.

## Completion Evidence

- Frozen slice: 12 cases, 6 dev + 6 hidden; identifier policy, controlled semantic equivalence, source replay, and manifest integrity valid.
- Frozen public SHA-256: `66e52df63f55c087e63de3f667e926c362252d5076834bb092719184cc86bbcf`.
- Frozen run: `run-20260727T124023Z-codex-gpt-5-6-sol-opaque-v2`; proposals SHA-256 `55034bc117c589baf434c6181439eaa57e3158b9a404f9ffa102769a1c5d7f8d`.
- Phase order: prompt/dispatch/proposals/provenance frozen before authority/gold scoring; provenance records `authority_or_gold_read_before_freeze=false` and declarative isolation limitations.
- Raw proposer quality: fail; accuracy `0.8333333333333334`, critical false merge `1`, critical false membership `0`, abstention F1 `0.0`, evidence exact `1.0`.
- Deterministic gate safety: pass; gated accuracy `1.0`, gated critical false merge/membership `0/0`, intervention count `2`.
- Score/report SHA-256: `3124ade877c4aaf8d81518f75587ac219acc1ff8060b80acfadff06650d8875e` / `76ae0df98040eb269467ca4a4454955434e7bc8f899455d0abd7d76466560037`; replay byte-identical.
- Review hardening: fixed namespace and derived-ID recomputation, canonical v1-to-v2 public/authority/gold comparison, strict preregistration policy models, and read-only slice validation; coordinated-drift negative tests pass.
- Verification: focused `27 passed`; full `tests/natural_memory_benchmark` `160 passed`; four validators valid; 13 protected hashes preserved; all formal v2 slice/run artifacts `0444`.
- Final read-only review: the frozen run remained credible; one Critical and two Important validator findings were reproduced, fixed with RED/GREEN tests, and closed by the fresh verification above. The known fixed renderer wording remains disclosed as a Minor limitation.
- Branch decision: only dev/diagnostic false-merge and abstention repair is authorized; hidden results cannot be used for tuning, and a later formal evaluation must use a newly frozen version with fresh hidden cases.
