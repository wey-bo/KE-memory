# Typed Extractor V2 L1 Dev Qualification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Qualify a real zero-history proposer on a frozen 12-case L1 dev slice while keeping every proposal non-authoritative and every automatic memory write disabled.

**Architecture:** Reuse the frozen bridge-v3 replay as the only source of existing extraction candidates. A dev-slice builder separates private source selection, public proposer input, authority, gold, manifest, and prompt; a typed-specific model-run module freezes public-only proposals before an independent scorer reads authority/gold. The scorer reports raw semantic quality separately from a deterministic fail-closed gate that can only preserve an emitted candidate or reduce it to abstention.

**Tech Stack:** Python 3.13, Pydantic v2, pytest, existing `tools.natural_memory_benchmark` canonical JSON/hash/immutable-output helpers, H100 `.venv-h100`.

## Global Constraints

- Work only in `/public/home/wwb/KE-mem/KE-memory-next-prep-20260727` on H100.
- This workspace is not a Git repository; do not initialize Git, create a worktree, or add commit steps.
- Do not rerun the existing turn/dialogue extraction models or any external memory system.
- Do not access or reuse old Fusion Memory code, tests, architecture, or experiment conclusions.
- The proposer may read only frozen `public-l1.json` and `proposer-prompt-l1.md`; authority/gold become readable only after proposal freeze.
- Raw proposer quality and deterministic gate safety remain separate top-level results.
- The deterministic gate may only preserve a proposal or reduce it to abstention; it cannot repair kind, predicate, role, time, lifecycle, condition, scope, derivation, or evidence semantics.
- Embeddings, WordNet, schema.org, surface equality, Extended-AMR, and KEOL cannot authorize facts, identity, membership, roles, time, lifecycle, or closure.
- Do not create fresh hidden evaluation data until both L1 and later L2 dev gates pass.
- Do not create authoritative L1/L2 units, unit revisions, closure records/evaluations, identity decisions, or membership writes.
- `LONGMEMEVAL-6d550036` remains `structured_l2_identity_unresolved`.
- Formal artifacts are immutable mode `0444`; replay must be byte-identical.

---

## File Structure

- Create `tools/natural_memory_benchmark/typed_extractor_l1.py`: strict L1 source/public/authority/gold/manifest/proposal/score models, bridge-v3-backed slice preparation and validation, deterministic gate, scoring, error taxonomy, and report rendering.
- Create `tools/natural_memory_benchmark/typed_extractor_model_run.py`: typed-extractor dispatch receipt and public-only proposal/provenance freeze.
- Create `tests/natural_memory_benchmark/test_typed_extractor_l1.py`: slice, separation, opaqueness, scoring, gate, replay, and mutation-guard tests.
- Create `tests/natural_memory_benchmark/test_typed_extractor_model_run.py`: dispatch/freeze chronology, coverage, hash, read-only, and CLI tests.
- Modify `tools/natural_memory_benchmark/cli.py`: add L1 dev preparation, validation, dispatch, freeze, and scoring commands.
- Create `artifacts/automatic-extraction-assessment/typed-extractor-v2-dev/source-cases-l1.json`: the 12-case private semantic authoring source.
- Create `artifacts/automatic-extraction-assessment/typed-extractor-v2-dev/proposer-prompt-l1.md`: frozen public-only proposer instructions.
- Generate `public-l1.json`, `authority-l1.json`, `gold-l1.json`, `manifest-l1.json`, and formal model-run outputs through the tested CLI.
- Modify `README.md`, `AGENTS.md`, `安排.md`, and the typed-extractor design after formal scoring.

### Task 1: Freeze The L1 Dev Contract

**Files:**
- Create: `tests/natural_memory_benchmark/test_typed_extractor_l1.py`
- Create: `tools/natural_memory_benchmark/typed_extractor_l1.py`

**Interfaces:**
- Consumes: `ExtractionReplay` from `replay_extraction_inputs(...)` and canonical helpers from `io.py`.
- Produces: `L1SourceConfig`, `L1PublicPayload`, `L1AuthorityPayload`, `L1GoldPayload`, `L1Manifest`, `L1ProposalPayload`, and `L1ScorePayload` Pydantic models.

- [x] **Step 1: Write failing contract tests**

  Add tests that require strict tagged decisions `emit_l1 | abstain | no_memory`, candidate-scoped contiguous local IDs (`entity-01`, `entity-02`, ...), closed role/entity references, exact evidence speaker bindings, structured condition/scope bindings, typed derivation provenance, typed time, lifecycle links, and null typed content for non-emission decisions.

- [x] **Step 2: Verify RED**

  Run:

  ```bash
  .venv-h100/bin/python -m pytest -p no:cacheprovider \
    tests/natural_memory_benchmark/test_typed_extractor_l1.py -q \
    --basetemp=/tmp/ke-memory-typed-l1-contract-red
  ```

  Expected: collection/import failure because `typed_extractor_l1.py` does not exist.

- [x] **Step 3: Implement strict models**

  Define these exact proposal-side types:

  ```python
  L1Decision = Literal["emit_l1", "abstain", "no_memory"]
  L1Kind = Literal["event", "state", "preference", "task", "attribute"]

  class LocalEntity(StrictModel):
      local_entity_id: str = Field(pattern=r"^entity-[0-9]{2}$")
      surface: str = Field(min_length=1)

  class TypedRoleBinding(StrictModel):
      role: str = Field(min_length=1)
      role_name: str = Field(min_length=1)
      local_entity_id: str = Field(pattern=r"^entity-[0-9]{2}$")

  class TypedQualifierBinding(StrictModel):
      operator: str = Field(min_length=1)
      value: str = Field(min_length=1)
      local_entity_ids: list[str] = Field(default_factory=list)

  class TypedEvidenceBinding(StrictModel):
      evidence_id: str = Field(min_length=1)
      speaker: Literal["user", "assistant", "tool"]

  class TypedDerivationProvenance(StrictModel):
      method: Literal["explicit", "context_completed", "inferred"]
      basis: str | None = None
      evidence_ids: list[str] = Field(min_length=1)

  class TypedTimeBinding(StrictModel):
      event_time: str | None = None
      valid_time: str | None = None

  class TypedLifecycleBinding(StrictModel):
      lifecycle: Literal["active", "superseded", "conflicted"]
      replacement_candidate_ref: str | None = None
      replaces_candidate_refs: list[str] = Field(default_factory=list)
      supersedes_candidate_refs: list[str] = Field(default_factory=list)
      conflicts_with_candidate_refs: list[str] = Field(default_factory=list)

  class TypedOperationProvenance(StrictModel):
      confirmed_by_operation_refs: list[str] = Field(default_factory=list)
      added_by_operation_refs: list[str] = Field(default_factory=list)
  ```

  Add model validators that require all typed fields for `emit_l1`, forbid them for `abstain/no_memory`, require contiguous local IDs, and reject dangling qualifier/role references.

- [x] **Step 4: Verify GREEN**

  Run the Task 1 test file and expect all contract tests to pass.

### Task 2: Build And Validate The Frozen 12-Case Slice

**Files:**
- Modify: `tests/natural_memory_benchmark/test_typed_extractor_l1.py`
- Modify: `tools/natural_memory_benchmark/typed_extractor_l1.py`
- Create: `artifacts/automatic-extraction-assessment/typed-extractor-v2-dev/source-cases-l1.json`
- Create: `artifacts/automatic-extraction-assessment/typed-extractor-v2-dev/proposer-prompt-l1.md`

**Interfaces:**
- Produces: `prepare_l1_dev_slice(source_config_path, output_root, ..., prompt_path) -> dict[str, Any]` and `validate_l1_dev_slice(...) -> dict[str, Any]`.
- Public payload contains opaque `case_id` and `candidate_ref`, source turn text, untyped candidate fields, evidence spans/speakers, allowed vocabularies, and opaque lifecycle references.
- Authority contains original knowledge IDs, admissible evidence/speaker/time/lifecycle values, and all automatic-write permissions fixed to false.

- [x] **Step 1: Write failing replay/separation tests**

  Require exact bridge-v3 input hashes, exactly 12 unique single-turn records, no original knowledge/candidate IDs in public JSON, exact public/authority/gold case coverage, no gold action or expected semantic field names in public metadata, and distribution:

  ```text
  kind coverage: event, state, preference, task, attribute
  source status coverage: user_reported, agent_generated, tool_observed
  projection status coverage: active, corrected, superseded
  non-explicit derivation >= 2
  condition-bearing emit >= 1
  scope-bearing emit >= 1
  confirm/add operation-bearing emit >= 1
  resolved-time emit >= 1
  unresolved-time emit >= 1
  abstain >= 2
  no_memory >= 1
  ```

- [x] **Step 2: Verify RED**

  Run the focused tests; expect missing preparation functions.

- [x] **Step 3: Implement deterministic opaque remapping and slice preparation**

  Derive case/candidate refs with fixed namespace UUID5 or canonical SHA-256 prefixes. Reuse `replay_extraction_inputs(...)`; reject records that are absent, cross-turn, duplicated, or hash-drifted. Write public, authority, gold, and manifest with `write_json_immutable`, then chmod all formal inputs and prompt `0444`.

- [x] **Step 4: Author the 12 private cases and prompt**

  Use only frozen dev/diagnostic records. The source config must explicitly cover:

  ```text
  K_beam-cand-004-4d648a026dc4_003_003       state emit
  K_taskmaster2-cand-001-5f5e1081bd0b_001_003 preference emit
  K_tau-bench-cand-001-650fada2c0dc_000_001  task emit
  K_tau-bench-cand-001-650fada2c0dc_003_005  attribute emit
  K_tau-bench-cand-001-650fada2c0dc_001_005  event emit
  K_tau-bench-cand-001-650fada2c0dc_000_004  superseded task emit
  K_beam-cand-004-4d648a026dc4_003_002       resolved-time attribute emit
  K_taskmaster2-cand-001-5f5e1081bd0b_001_001 unresolved-time event emit
  K_taskmaster2-cand-001-5f5e1081bd0b_004_001 corrected unresolved-reference abstain
  K_beam-cand-004-4d648a026dc4_000_005       unsupported-modality abstain
  K_taskmaster2-cand-001-5f5e1081bd0b_000_003 question-only no_memory
  K_wildchat-learn-cand-001-8def27ce661d_002_005 confirmed hypothetical state emit
  ```

  The prompt must define output JSON exactly, forbid global IDs and authoritative writes, require null unresolved time, distinguish `abstain` from `no_memory`, and prohibit reading any file other than the named public input.

- [x] **Step 5: Verify GREEN and deterministic replay**

  Prepare the slice twice into distinct temporary roots and assert byte-identical public/authority/gold/manifest outputs.

### Task 3: Freeze Public-Only Model Proposals Before Scoring

**Files:**
- Create: `tests/natural_memory_benchmark/test_typed_extractor_model_run.py`
- Create: `tools/natural_memory_benchmark/typed_extractor_model_run.py`

**Interfaces:**
- Produces: `write_l1_model_dispatch(...) -> dict[str, Any]` and `freeze_l1_model_proposals(...) -> dict[str, Any]`.
- Allowed input set is exactly `{"public-l1.json", "proposer-prompt-l1.md"}`.

- [x] **Step 1: Write failing dispatch/freeze tests**

  Require read-only inputs, exact allowed-file/hash set, `history_context_inherited=false`, `authority_or_gold_allowed=false`, complete case coverage, proposal metadata matching dispatch, no unknown evidence/candidate refs, proposal freeze before provenance, and `0444` outputs.

- [x] **Step 2: Verify RED**

  Run the model-run test file; expect missing module/functions.

- [x] **Step 3: Implement dispatch and freeze**

  Follow the existing `identity_model_run.py` pattern but validate `L1PublicPayload`/`L1ProposalPayload`. Provenance must bind dispatch SHA, proposal SHA, allowed input hashes, proposer ID/version, run ID, and declarative zero-history isolation.

- [x] **Step 4: Verify GREEN**

  Run both typed-extractor focused test files.

### Task 4: Implement Independent Raw Scoring And Fail-Closed Gate

**Files:**
- Modify: `tests/natural_memory_benchmark/test_typed_extractor_l1.py`
- Modify: `tools/natural_memory_benchmark/typed_extractor_l1.py`

**Interfaces:**
- Produces: `score_l1_proposals(root, proposals_path, guard_bundle, ...) -> L1ScorePayload` and `run_l1_scoring_file(...) -> dict[str, Any]`.
- Error taxonomy values are exactly `false_emission`, `false_abstention`, `evidence_error`, `kind_error`, `predicate_or_operator_error`, `role_or_local_entity_error`, `modality_or_polarity_error`, `time_error`, `lifecycle_error`, `condition_or_scope_error`, and `derivation_or_speaker_error`.

- [x] **Step 1: Write failing raw/gate separation tests**

  Construct a semantically wrong but structurally valid proposal and assert raw field accuracy fails while the gate does not silently correct it. Construct unknown evidence, dangling role refs, unsupported time, and cross-case lifecycle refs and assert the gated decision becomes abstain with explicit reasons.

- [x] **Step 2: Write failing guard tests**

  Assert before/after authoritative bundle fingerprint and counts are equal, all automatic write counts are zero, and `LONGMEMEVAL-6d550036` remains unresolved.

- [x] **Step 3: Verify RED**

  Run focused tests and confirm expected missing scorer/gate failures.

- [x] **Step 4: Implement minimal gate and scorer**

  The gate reads public+authority, never gold, and only validates evidence/speaker exactness, local reference closure, admitted modality/time, lifecycle-reference scope, condition/scope reference closure, and derivation evidence closure. The scorer then reads gold and reports raw and gated decisions separately.

- [x] **Step 5: Implement metrics and readiness**

  Require:

  ```text
  proposal_coverage = 1.0
  schema_valid_rate = 1.0
  exact_evidence_rate = 1.0
  raw_critical_false_emission_count = 0
  raw_decision_accuracy >= 0.90
  raw_abstention_f1 >= 0.80
  every safety-critical emitted field-family accuracy >= 0.85
  deterministic_critical_false_materialization_count = 0
  all automatic authoritative write counts = 0
  unchanged guard fingerprint/counts
  ```

- [x] **Step 6: Verify GREEN**

  Run the focused tests and inspect the complete score structure, not only readiness booleans.

### Task 5: Add CLI And Formal Dev Inputs

**Files:**
- Modify: `tools/natural_memory_benchmark/cli.py`
- Modify: `tests/natural_memory_benchmark/test_typed_extractor_l1.py`
- Modify: `tests/natural_memory_benchmark/test_typed_extractor_model_run.py`

**Interfaces:**
- Add commands `prepare-typed-extractor-l1-dev`, `validate-typed-extractor-l1-dev`, `prepare-typed-extractor-l1-dispatch`, `freeze-typed-extractor-l1-proposals`, and `score-typed-extractor-l1-proposals`.

- [x] **Step 1: Write failing CLI tests**

  Exercise each command through `python -m tools.natural_memory_benchmark.cli`, including a negative attempt to score writable or unfrozen proposals.

- [x] **Step 2: Verify RED**

  Run CLI-focused tests; expect argparse command rejection.

- [x] **Step 3: Wire the CLI**

  Keep output summaries narrow: status, dataset/run IDs, case count, raw proposer readiness, gate safety readiness, and zero-write count.

- [x] **Step 4: Generate and freeze formal source/public/authority/gold/manifest/prompt**

  Use the fixed bridge-v3 inputs and authoritative-v5 guard bundle. Verify all files are mode `0444` and validation returns `valid`.

- [x] **Step 5: Verify GREEN**

  Run both focused files and deterministic prepare/validate replay.

### Task 6: Run The Real Isolated Proposer And Score Only After Freeze

**Files:**
- Generate: `artifacts/automatic-extraction-assessment/typed-extractor-v2-dev/model-runs/<run-id>/dispatch.json`
- Stage: `/tmp/<run-id>-staged-proposals.json`
- Generate: formal `proposals.json`, `provenance.json`, `score.json`, `report.md`, and `error-analysis.json` under the run directory.

**Interfaces:**
- Proposer receives only the absolute paths to frozen public and prompt plus a temporary output path.
- Scorer receives authority/gold only after formal proposals/provenance are `0444`.

- [x] **Step 1: Freeze dispatch**

  Create a dispatch receipt whose allowed input set has exactly two files and whose proposer metadata matches the actually available model.

- [x] **Step 2: Start a zero-history isolated proposer**

  Dispatch with no inherited conversation turns. Explicitly forbid reads outside public/prompt and require one complete JSON payload at the temporary staged path.

- [x] **Step 3: Validate and freeze proposals/provenance**

  Do not invoke the scorer until proposal and provenance hashes and mode `0444` are confirmed.

- [x] **Step 4: Score independently**

  Run the scorer using frozen authority/gold. Freeze score/report/error analysis immediately.

- [x] **Step 5: Classify any dev failures before repair**

  If raw quality or gate safety fails, use only the frozen 12 dev cases and the exact taxonomy. Freeze the failed run, revise only the public proposer prompt/policy or deterministic structural gate as justified, assign a new version/run ID, and repeat dispatch -> proposal freeze -> scoring. Do not create hidden cases.

### Task 7: Full Verification And Status Update

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `安排.md`
- Modify: `docs/designs/2026-07-28-typed-extractor-v2-dev-qualification-design.md`

- [x] **Step 1: Run focused and full tests**

  ```bash
  .venv-h100/bin/python -m pytest -p no:cacheprovider \
    tests/natural_memory_benchmark/test_typed_extractor_l1.py \
    tests/natural_memory_benchmark/test_typed_extractor_model_run.py -q \
    --basetemp=/tmp/ke-memory-typed-l1-focused

  .venv-h100/bin/python -m pytest -p no:cacheprovider \
    tests/knowledge_pipeline -q \
    --basetemp=/tmp/ke-memory-typed-l1-knowledge

  .venv-h100/bin/python -m pytest -p no:cacheprovider \
    tests/natural_memory_benchmark -q \
    --basetemp=/tmp/ke-memory-typed-l1-natural

  .venv-h100/bin/python -m compileall -q \
    knowledge_pipeline tools/natural_memory_benchmark \
    tests/knowledge_pipeline tests/natural_memory_benchmark
  ```

- [x] **Step 2: Validate all protected formal slices and ledgers**

  Re-run natural-v1, opaque-v2, fresh-v3, dev-v4, fresh-v4, slice-v1, external ledger, bridge-v3, and typed L1 validators.

- [x] **Step 3: Verify protected hashes and permissions**

  Confirm identity-v1, authoritative-v5, fresh-v4, candidate-assessment-v3, bridge-v1, bridge-v2, bridge-v3, and all new formal L1 inputs/run outputs have expected SHA-256 and mode `0444`.

- [x] **Step 4: Update status documents with measured results**

  Record exact raw metrics, gated metrics, intervention taxonomy, hashes, replay result, tests, validators, guard fingerprint, and all zero-write counts. State clearly whether L1 dev passed; do not infer L2 readiness, hidden readiness, pipeline integration, storage choice, or product superiority.

## Self-Review

- Spec coverage: all bridge-v3 requirements, including condition, scope, derivation/inference provenance, evidence speaker binding, and confirm/add operation provenance, have explicit proposal fields, validation, metrics, and tests.
- Boundary coverage: proposal generation, freeze, scoring, and guard are separate; scorer cannot run against writable proposals; gate cannot repair semantics.
- Identifier coverage: public case/candidate IDs are opaque and no gold action or expected typed fields appear in public metadata.
- Type consistency: the same `L1ProposalPayload` is used by freeze and scorer; authority/gold case IDs match public exactly.
- No placeholder steps remain; L2 qualification is deliberately excluded from this plan and begins only after L1 dev passes.
