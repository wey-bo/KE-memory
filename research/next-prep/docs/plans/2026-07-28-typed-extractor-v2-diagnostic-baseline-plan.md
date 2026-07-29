# Typed Extractor V2 Diagnostic Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build independent L1/L2 diagnostic dev packs and a strict repair-readiness layer, then run the unchanged passing dev prompts once to establish a non-hidden repair baseline.

**Architecture:** Separate L1 and L2 diagnostic adapters consume immutable diagnostic-authored source files and emit the existing strict public/authority/gold contracts with deterministic opaque IDs. Existing proposer dispatch/freeze/scorers remain unchanged. A small qualification module recomputes stricter all-exact repair readiness from frozen score files.

**Tech Stack:** Python 3.13, Pydantic v2, pytest, canonical JSON/SHA-256 helpers, existing typed extractor proposal/scorer/model-run modules, H100 `.venv-h100`.

## Global Constraints

- Work only in `/public/home/wwb/KE-mem/KE-memory-next-prep-20260727`; this directory is not a Git repository.
- Do not read old Fusion Memory or rerun external memory systems.
- Do not modify fresh-hidden v1, bridge-v3, shared typed scorers, query compiler/executor files, or authoritative memory code.
- Do not create any fresh-hidden v2 path during this plan.
- Diagnostic source must be marked `diagnostic_authored` and must not be reported as natural benchmark evidence.
- Proposer input is frozen prompt plus public JSON only; proposals/provenance freeze before scoring reads authority/gold.
- Keep all L1/L2/revision/closure/identity/membership/snapshot/aggregate writes at zero and keep `LONGMEMEVAL-6d550036` unresolved.
- API credentials are process-only and must not be written to files, command arguments, logs, or reports.

---

### Task 1: L1 Diagnostic Slice Adapter

**Files:**
- Create: `tools/natural_memory_benchmark/typed_extractor_l1_dev_repair.py`
- Create: `tests/natural_memory_benchmark/test_typed_extractor_l1_dev_repair.py`
- Create: `artifacts/automatic-extraction-assessment/typed-extractor-v2-l1-dev-repair-v1/diagnostic-source-l1.json`

**Interfaces:**
- Produces `prepare_l1_dev_repair_slice(source_path: Path, output_root: Path, prior_roots: Sequence[Path]) -> dict[str, Any]`.
- Produces `validate_l1_dev_repair_slice(source_path: Path, root: Path, prior_roots: Sequence[Path]) -> dict[str, Any]`.
- Reuses `L1PublicPayload`, `L1AuthorityPayload`, `L1GoldPayload`, `L1Manifest`, and typed candidate models from `typed_extractor_l1.py`.

- [ ] **Step 1: Write strict schema and distribution tests**

Test a 16-case source with exact primary-family counts: four non-emissions, three false-abstention controls, two evidence cases, two condition/scope cases, two time cases, two role cases, and one lifecycle/operation case. Require `diagnostic_authored`, unique private IDs, at least two scored opportunities for every target field family, and strict rejection of extra fields.

Run:

```bash
.venv-h100/bin/python -m pytest -q tests/natural_memory_benchmark/test_typed_extractor_l1_dev_repair.py
```

Expected: FAIL because `typed_extractor_l1_dev_repair` does not exist.

- [ ] **Step 2: Implement diagnostic source models and opaque mapping**

Add frozen Pydantic models equivalent to:

```python
class L1DiagnosticCase(StrictModel):
    private_case_id: str
    primary_family: L1RepairFamily
    secondary_families: list[L1RepairFamily]
    source_turn: dict[Literal["user", "agent"], str]
    untyped_candidate: PublicUntypedCandidate
    expected_decision: L1Decision
    expected_typed_candidate: TypedL1Candidate | None
    authority: L1DiagnosticAuthority

class L1DiagnosticSource(StrictModel):
    schema_version: Literal["typed-extractor-l1-diagnostic-source-v1"]
    dataset_id: Literal["typed-extractor-l1-dev-repair-v1"]
    provenance: Literal["diagnostic_authored"]
    public_vocabulary: dict[str, list[str]]
    cases: list[L1DiagnosticCase]
```

Derive `case-*` and `candidate-*` with SHA-256 namespace
`typed-extractor-l1-dev-repair-v1:2026-07-28`; never expose private IDs or family labels in public output.

- [ ] **Step 3: Author the 16 source cases**

Use these private IDs and primary families exactly:

```text
control-question-no-durable-fact         false_emission
control-instruction-no-state             false_emission
unsupported-modal-rumor                  modality_or_polarity
insufficient-evidence-attribution        evidence
valid-user-state                         false_abstention
valid-requested-task                     false_abstention
valid-tool-event                         false_abstention
evidence-same-speaker-distractor          evidence
evidence-cross-speaker-distractor         derivation_or_speaker
condition-explicit-approver               condition_or_scope
scope-explicit-project                    condition_or_scope
resolved-calendar-valid-time              time
unresolved-deictic-time                   time
role-two-people-transfer                  role_or_local_entity
role-agent-versus-beneficiary             role_or_local_entity
lifecycle-correction-confirmation         lifecycle
```

Give every source and candidate newly authored text. Add secondary coverage so
predicate/operator, kind, operation provenance, and all remaining L1 families
each have at least two opportunities. Evidence offsets must resolve exactly to
the source turn and distractor spans must not be included in gold bindings.

- [ ] **Step 4: Implement immutable prepare/validate**

Write `public-l1.json`, `authority-l1.json`, `gold-l1.json`, and
`manifest-l1.json` with the existing canonical writer, then chmod all five
source/output files to `0444`. Validation rebuilds byte-for-byte, rejects any
prior dev/fresh-v1 ID or evidence overlap, confirms public/private separation,
and checks zero-write claim boundaries.

- [ ] **Step 5: Run focused tests and freeze the formal L1 diagnostic slice**

Run the focused test until it passes, prepare the formal root once, validate it,
and replay preparation into a temporary directory for byte comparison.

### Task 2: L2 Diagnostic Slice Adapter

**Files:**
- Create: `tools/natural_memory_benchmark/typed_extractor_l2_dev_repair.py`
- Create: `tests/natural_memory_benchmark/test_typed_extractor_l2_dev_repair.py`
- Create: `artifacts/automatic-extraction-assessment/typed-extractor-v2-l2-dev-repair-v1/diagnostic-source-l2.json`

**Interfaces:**
- Produces `prepare_l2_dev_repair_slice(source_path: Path, output_root: Path, prior_roots: Sequence[Path]) -> dict[str, Any]`.
- Produces `validate_l2_dev_repair_slice(source_path: Path, root: Path, prior_roots: Sequence[Path]) -> dict[str, Any]`.
- Reuses existing `L2PublicPayload`, `L2AuthorityPayload`, `L2GoldPayload`, `L2Manifest`, and typed L1/L2 candidate models.

- [ ] **Step 1: Write strict schema, closure, and distribution tests**

Require exactly 12 cases, four abstentions, eight emissions, at least two cases
per selected abstraction family, at least one non-task kind, closed support/
turn/session/evidence references, strict extra-field rejection, and no overlap
with L2 dev/fresh-v1 or L1 diagnostic IDs/evidence.

Expected initial focused result: module import failure.

- [ ] **Step 2: Implement diagnostic source models and opaque mapping**

Use namespace `typed-extractor-l2-dev-repair-v1:2026-07-28`. Each diagnostic
case stores source turns, untyped candidate, at least two typed L1 supports,
private expectation/authority, primary family, and secondary families. Emit the
existing L2 public/authority/gold contracts without private labels.

- [ ] **Step 3: Author the 12 source cases**

Use these private IDs exactly:

```text
abstain-unsupported-modality
abstain-unresolved-selected-option
abstain-incompatible-supports
abstain-incomplete-evidence-closure
emit-coreference-device-request
emit-coreference-document-reference
emit-task-composition-release
emit-task-composition-travel
emit-lifecycle-commitment
emit-lifecycle-supersession
emit-state-summary
emit-preference-aggregation
```

Use newly authored source text and IDs. The last two cases must require
`long_running_state/state_summary` and
`preference_profile/preference_aggregation` respectively. Emission gold must
use exact untyped statement/predicate/subject/object surfaces, complete support
sets, and closed source/evidence coverage.

- [ ] **Step 4: Implement immutable prepare/validate and freeze**

Write and chmod source/public/authority/gold/manifest to `0444`. Validate
byte-replay, distribution, reference closure, public/private separation,
diagnostic provenance, prior-overlap count zero, and zero writes.

### Task 3: Strict Dev-Repair Qualification

**Files:**
- Create: `tools/natural_memory_benchmark/typed_extractor_dev_repair_qualification.py`
- Create: `tests/natural_memory_benchmark/test_typed_extractor_dev_repair_qualification.py`

**Interfaces:**
- Produces `qualify_dev_repair(layer: Literal["l1", "l2"], score_path: Path, output_path: Path, report_path: Path) -> dict[str, Any]`.
- Consumes only a frozen existing scorer output and the matching diagnostic manifest.

- [ ] **Step 1: Write failing qualification tests**

Test that scorer-level readiness is insufficient when any target metric is
below `1.0` or gate interventions exceed zero. Reject dataset/run/hash mismatch,
non-zero writes, changed guards, LongMemEval status drift, unknown metrics, and
mutable score input.

- [ ] **Step 2: Implement exact repair thresholds**

Use exact layer metric sets:

```python
L1_EXACT = {
    "proposal_coverage", "schema_valid_rate", "raw_decision_accuracy",
    "raw_abstention_f1", "exact_evidence_rate", "kind_accuracy",
    "predicate_or_operator_accuracy", "role_or_local_entity_accuracy",
    "modality_or_polarity_accuracy", "time_accuracy",
    "condition_or_scope_accuracy", "derivation_or_speaker_accuracy",
    "lifecycle_accuracy", "operation_provenance_accuracy",
}
L2_EXACT = {
    "proposal_coverage", "schema_valid_rate", "raw_decision_accuracy",
    "raw_abstention_f1", "exact_evidence_rate", "support_id_accuracy",
    "source_coverage_accuracy", "kind_accuracy",
    "structured_claim_accuracy", "abstraction_accuracy",
    "closure_accuracy", "summary_accuracy",
}
```

All exact metrics equal `1.0`; critical false emission, gate intervention, and
critical materialization counts equal zero. Preserve raw and gate readiness as
separate fields and set `dev_repair_ready` only when both plus all strict checks
pass.

- [ ] **Step 3: Implement immutable JSON/Markdown outputs and replay tests**

The report must say diagnostic-only, not natural benchmark evidence, and must
state that fresh-v2 remains unauthorized. Require byte-identical replay.

### Task 4: CLI Wiring And Regression Coverage

**Files:**
- Modify: `tools/natural_memory_benchmark/cli.py`
- Modify: `tests/natural_memory_benchmark/test_cli.py`

**Interfaces:**
- Adds `prepare-typed-extractor-l1-dev-repair` and `validate-typed-extractor-l1-dev-repair`.
- Adds `prepare-typed-extractor-l2-dev-repair` and `validate-typed-extractor-l2-dev-repair`.
- Adds `qualify-typed-extractor-dev-repair`.

- [ ] **Step 1: Write CLI parser and dispatch failures first**
- [ ] **Step 2: Wire exact paths and print only status/count/readiness summaries**
- [ ] **Step 3: Run L1/L2 repair tests, all typed tests, knowledge tests, and natural tests excluding only the separately recorded concurrent query-assessment blocker if it still exists**
- [ ] **Step 4: Run `compileall` and verify no query compiler/executor file was modified**

### Task 5: Unchanged-Prompt Diagnostic Baselines

**Files:**
- Generate immutable model runs under both diagnostic roots.
- Generate strict qualification JSON/Markdown beside each scored run.
- Update: `README.md`, `AGENTS.md`, `安排.md`.

**Interfaces:**
- Reuses existing L1/L2 dispatch, official API runner, proposal freeze, and scorer functions without modification.

- [ ] **Step 1: Copy the frozen L1 V6 and L2 V8 prompts byte-for-byte into each diagnostic root and record their source hashes**
- [ ] **Step 2: Freeze dispatches with requested model `deepseek-chat` and diagnostic public-only input**
- [ ] **Step 3: Send one no-history official request per layer with a process-only credential; archive raw responses and freeze proposals/provenance before scoring**
- [ ] **Step 4: Run existing scorers, then strict repair qualification; preserve failures without prompt repair in this plan**
- [ ] **Step 5: Classify baseline errors and write the next prompt-repair plan using only diagnostic results**
- [ ] **Step 6: Verify all formal modes/hashes, zero writes, unchanged guard fingerprints, candidate queue SHA, unmaterialized manual adjudications, unresolved LongMemEval status, and no key material**

## Self-Review

- Spec coverage: independent diagnostic data, public/private separation,
  stricter raw/gate qualification, immutable model protocol, zero writes, and
  fresh-v2 deferral each map to a task.
- Placeholder scan: implementation stops deliberately after the unchanged-
  prompt baseline; prompt edits belong to a result-specific follow-up plan and
  are not represented as unspecified work here.
- Type consistency: adapters emit the existing L1/L2 carrier models;
  qualification consumes the existing score schemas and does not alter shared
  thresholds.
