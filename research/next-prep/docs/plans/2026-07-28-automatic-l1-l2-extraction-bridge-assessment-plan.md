# Automatic L1/L2 Extraction Bridge Assessment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` and implement this plan task-by-task with TDD.
> This H100 workspace is not a Git repository, so commit/worktree steps do not
> apply.

**Goal:** Replay the existing validated two-pass model extraction and produce a
strict, immutable, non-authoritative assessment of its compatibility with the
authoritative L1/L2 contract.

**Architecture:** Add one isolated assessment module and CLI under
`tools/natural_memory_benchmark`. It reuses the existing extraction projector,
source loader, authoritative guard bundle, canonical writers, and frozen input
artifacts. It emits per-record compatibility envelopes and aggregate metrics;
it never creates authoritative memory-unit revisions or changes the extraction
skeleton.

**Tech Stack:** Python 3.13, Pydantic v2, pytest 8, canonical JSON, SHA-256,
existing immutable writers.

## Global Constraints

- H100 workspace only.
- Do not rerun a model, external memory system, or old Fusion Memory code.
- Do not modify `knowledge_pipeline`, `semantic_ir.py`,
  `authoritative_memory.py`, `turn_bundle.py`, identity resolution, question
  processing, symbolic retrieval, or guarded embedding fallback.
- Do not publish authoritative L1/L2/revision/closure/identity/membership writes.
- Do not use WordNet, schema.org, keywords, or embeddings to fill missing
  semantic fields.
- Report raw extraction structure separately from deterministic bridge safety.
- Keep `LONGMEMEVAL-6d550036` as `structured_l2_identity_unresolved`.
- Formal output files must be canonical, replay-identical, and mode `0444`.

---

### Task 1: Replay and Bind the Existing Extraction Ledger

**Files:**

- Create: `tests/natural_memory_benchmark/test_extraction_bridge_assessment.py`
- Create: `tools/natural_memory_benchmark/extraction_bridge_assessment.py`

**Interfaces:**

- Produces:

  ```python
  @dataclass(frozen=True)
  class ExtractionReplay:
      view: FinalKnowledgeView
      source_turns: dict[tuple[str, int], TurnUnit]
      input_sha256: dict[str, str]
      record_count: int
      active_record_count: int

  def replay_extraction_inputs(
      *,
      source_path: Path,
      turn_manifest_path: Path,
      dialogue_manifest_path: Path,
      final_knowledge_path: Path,
      run_path: Path,
      source_segments_path: Path,
  ) -> ExtractionReplay:
      ...
  ```

- Consumes `knowledge_pipeline.projector.project_validated_manifests`,
  `knowledge_pipeline.projector.render_final_knowledge`, and
  `knowledge_pipeline.source.load_turn_units`.

- [x] **Step 1: Write failing replay tests**

  Add tests that require:

  - exact record/active/count equivalence with frozen `final-knowledge.json`;
  - exact turn/dialogue/source-segment hashes from the replayed manifests;
  - source data coverage for all 10 candidates and 43 turns;
  - final file path strings to be ignored while provenance hashes remain exact;
  - tampered final records, manifest hashes, or run bindings to fail closed.

- [x] **Step 2: Run RED**

  Run:

  ```bash
  PYTHONDONTWRITEBYTECODE=1 .venv-h100/bin/python -m pytest \
    -p no:cacheprovider \
    tests/natural_memory_benchmark/test_extraction_bridge_assessment.py \
    -q --basetemp=/tmp/ke-memory-extraction-bridge-red
  ```

  Expected: collection fails because
  `tools.natural_memory_benchmark.extraction_bridge_assessment` does not exist.

- [x] **Step 3: Implement minimal replay and validation**

  Implement helpers that:

  - hash all six declared inputs;
  - reproject the validated manifests;
  - compare `schema_version`, `active_ids`, derived counts, and `records` to the
    frozen final file;
  - compare manifest/source-segment hashes to final provenance and `run.json`;
  - require unique knowledge IDs;
  - require each evidence ID reuse to resolve to one identical definition;
  - bind each evidence item to the exact candidate/turn/message text and verify
    `text[start:end] == quote` plus the declared occurrence index.

- [x] **Step 4: Run GREEN**

  Run the focused test file and require all Task 1 tests to pass.

---

### Task 2: Build Loss-Aware Compatibility Envelopes

**Files:**

- Modify: `tests/natural_memory_benchmark/test_extraction_bridge_assessment.py`
- Modify: `tools/natural_memory_benchmark/extraction_bridge_assessment.py`

**Interfaces:**

- Produces strict frozen models:

  ```python
  CandidateLevel = Literal[
      "l1_single_turn_candidate",
      "l2_cross_turn_candidate",
      "blocked_candidate",
  ]
  MappingStatus = Literal["exact", "normalized", "unsupported", "missing"]

  class FieldMapping(StrictModel):
      field: str
      status: MappingStatus
      source_value: Any | None = None
      target_value: Any | None = None
      reason: str

  class AutomaticWriteClaims(StrictModel):
      l1: Literal[False] = False
      l2: Literal[False] = False
      unit_revision: Literal[False] = False
      closure: Literal[False] = False
      identity: Literal[False] = False
      membership: Literal[False] = False

  class ExtractionCompatibilityEnvelope(StrictModel):
      envelope_id: str
      knowledge_id: str
      candidate_id: str
      source_stage: Literal["turn", "dialogue"]
      projection_status: str
      candidate_level: CandidateLevel
      evidence_ids: list[str]
      evidence_turns: list[int]
      mappings: list[FieldMapping]
      blocking_gaps: list[str]
      authoritative_materialization_allowed: Literal[False] = False
      automatic_write_claims: AutomaticWriteClaims
  ```

- Produces:

  ```python
  def build_compatibility_envelopes(
      replay: ExtractionReplay,
  ) -> list[ExtractionCompatibilityEnvelope]:
      ...
  ```

- [x] **Step 1: Write failing classification and mapping tests**

  Cover:

  - single-turn evidence -> `l1_single_turn_candidate`;
  - multi-turn evidence or dialogue `added_by` -> `l2_cross_turn_candidate`;
  - active/conflicted/corrected/superseded lifecycle preservation;
  - exact mappings for evidence/source status/polarity/confidence;
  - normalized modality mappings for asserted, observed, planned, requested,
    hypothetical, and advised;
  - unsupported modality mappings for possible, preferred, questioned,
    committed, and claimed_completed;
  - required L1 gaps and additional L2 gaps;
  - all authoritative write claims are false;
  - envelope IDs are content-derived and deterministic.

- [x] **Step 2: Run RED**

  Run the focused tests and confirm failures reference missing envelope models or
  `build_compatibility_envelopes`.

- [x] **Step 3: Implement minimal envelope construction**

  Use only explicit record/evidence/projection fields. Do not infer kind,
  predicate sense, canonical operator, role names, entity identity, typed time,
  L2 supports, structured claims, or closure.

  Candidate-level precedence is:

  ```python
  if not evidence_turns:
      level = "blocked_candidate"
  elif len(evidence_turns) > 1 or projection.added_by:
      level = "l2_cross_turn_candidate"
  else:
      level = "l1_single_turn_candidate"
  ```

  Sort mappings, gaps, evidence IDs, and evidence turns deterministically.

- [x] **Step 4: Run GREEN**

  Run the focused test file and require all Task 1-2 tests to pass.

---

### Task 3: Separate Raw Structure Metrics from Bridge Safety

**Files:**

- Modify: `tests/natural_memory_benchmark/test_extraction_bridge_assessment.py`
- Modify: `tools/natural_memory_benchmark/extraction_bridge_assessment.py`

**Interfaces:**

- Produces:

  ```python
  class ExtractionCompatibilityLedger(StrictModel):
      schema_version: Literal["automatic-extraction-compatibility-ledger-v1"]
      input_sha256: dict[str, str]
      record_count: int
      envelopes: list[ExtractionCompatibilityEnvelope]

  class ExtractionBridgeAssessment(StrictModel):
      schema_version: Literal["automatic-extraction-bridge-assessment-v1"]
      status: Literal["pass"]
      raw_extraction_structure: dict[str, Any]
      deterministic_bridge_safety: dict[str, Any]
      guard_state: dict[str, Any]
      typed_extractor_v2_requirements: list[str]
      automatic_extraction_integration_ready: bool
      claim_boundary: dict[str, bool | str]
  ```

- Produces:

  ```python
  def assess_extraction_bridge(
      replay: ExtractionReplay,
      envelopes: list[ExtractionCompatibilityEnvelope],
      *,
      guard_bundle: MemoryRepresentationBundleV3,
  ) -> tuple[ExtractionCompatibilityLedger, ExtractionBridgeAssessment]:
      ...
  ```

- [x] **Step 1: Write failing metric and guard tests**

  Assert:

  - raw metrics count all projected, active, stage, modality, evidence, and
    projection-operation categories;
  - raw metrics never contain a gold semantic-accuracy claim;
  - safety metrics count L1/L2/blocked/ready candidates and gap frequencies;
  - ready L1/L2 counts are zero while mandatory typed fields are absent;
  - every automatic write count is zero;
  - guard fingerprint and protected counts are unchanged;
  - integration readiness is false;
  - `LONGMEMEVAL-6d550036` remains unresolved in the claim boundary;
  - the typed-extractor requirement list is exact and stable.

- [x] **Step 2: Run RED**

  Run the focused tests and confirm missing assessment behavior.

- [x] **Step 3: Implement pure assessment logic**

  Fingerprint the guard with `authoritative_memory.canonical_sha256` before and
  after envelope/metric construction. Count raw structure and safety in separate
  top-level objects. Reject any true write claim or guard drift.

- [x] **Step 4: Run GREEN**

  Run the focused tests and require all Task 1-3 tests to pass.

---

### Task 4: Add Immutable Runner, Report, and CLI

**Files:**

- Modify: `tests/natural_memory_benchmark/test_extraction_bridge_assessment.py`
- Modify: `tools/natural_memory_benchmark/extraction_bridge_assessment.py`
- Modify: `tools/natural_memory_benchmark/cli.py`

**Interfaces:**

- Produces:

  ```python
  def run_extraction_bridge_assessment(
      *,
      source_path: Path,
      turn_manifest_path: Path,
      dialogue_manifest_path: Path,
      final_knowledge_path: Path,
      run_path: Path,
      source_segments_path: Path,
      guard_root: Path,
      guard_slice_id: str,
      guard_results_path: Path,
      ledger_path: Path,
      assessment_path: Path,
      report_path: Path,
  ) -> dict[str, Any]:
      ...
  ```

- Adds CLI command `assess-automatic-l1-l2-extraction` with explicit arguments
  for every input, guard input, and output path.

- [x] **Step 1: Write failing runner and CLI tests**

  Require:

  - deterministic byte-identical output in two isolated temporary roots;
  - destination-exists rejection;
  - immediate `0444` freezing for each successfully written file and any partial
    output left by a later failure;
  - report sections named `Raw extraction structure`,
    `Deterministic bridge safety`, `Typed extractor v2 requirements`, and
    `Limitations`;
  - report wording states no model rerun, no gold semantic accuracy, and zero
    authoritative writes;
  - CLI prints output hashes and readiness.

- [x] **Step 2: Run RED**

  Run the focused tests and confirm the runner/CLI are absent.

- [x] **Step 3: Implement immutable output flow**

  Use existing canonical JSON/text writers. Freeze each path immediately after
  writing. On failure, chmod every existing managed output to `0444` before
  propagating the exception. Never overwrite an existing destination.

- [x] **Step 4: Run GREEN**

  Run the focused tests and CLI tests to green.

---

### Task 5: Freeze Formal Bridge-v1 and Close the Wave

**Files:**

- Create: `artifacts/automatic-extraction-assessment/bridge-v1/compatibility-ledger.json`
- Create: `artifacts/automatic-extraction-assessment/bridge-v1/assessment.json`
- Create: `artifacts/automatic-extraction-assessment/bridge-v1/report.md`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `安排.md`
- Modify: this plan

- [x] **Step 1: Run focused RED/GREEN history and formal command**

  Run the CLI only against the frozen inputs listed in the design and write to
  the exact bridge-v1 paths.

- [x] **Step 2: Replay in an isolated temporary output root**

  Require all three output files to be byte-identical to the formal files.

- [x] **Step 3: Run regression verification**

  Run:

  ```bash
  PYTHONDONTWRITEBYTECODE=1 .venv-h100/bin/python -m pytest \
    -p no:cacheprovider tests/knowledge_pipeline -q \
    --basetemp=/tmp/ke-memory-extraction-bridge-kp

  PYTHONDONTWRITEBYTECODE=1 .venv-h100/bin/python -m pytest \
    -p no:cacheprovider tests/natural_memory_benchmark -q \
    --basetemp=/tmp/ke-memory-extraction-bridge-natural

  .venv-h100/bin/python -m compileall -q \
    knowledge_pipeline tools/natural_memory_benchmark \
    tests/knowledge_pipeline tests/natural_memory_benchmark

  .venv-h100/bin/python -m tools.natural_memory_benchmark.cli \
    validate-slice --root artifacts/natural-benchmark-slices --slice-id slice-v1

  .venv-h100/bin/python -m tools.natural_memory_benchmark.cli \
    validate-ledger \
    --path artifacts/natural-benchmark-slices/external-results-ledger.json
  ```

  Also rerun extraction-manifest replay and verify protected identity,
  authoritative-v5, fresh-v4, and candidate-assessment-v3 hashes.

- [x] **Step 4: Record exact results and boundaries**

  Update status documents with exact counts, gap distribution, file hashes,
  permissions, test counts, validators, and the next dev-only typed-extractor
  action. Do not describe bridge safety as model semantic quality.

Formal `bridge-v3` closed with 416 projected records, 390 active records, 402
single-turn L1 candidates, and 14 cross-turn L2 candidates. Exact evidence
binding and source-status admissibility were both `1.0`, but these are raw
structure checks rather than gold semantic accuracy. All 416 candidates remain
blocked from authoritative materialization: the common missing fields are
memory kind, predicate sense, canonical operator, typed roles, and local entity
IDs; 64 records also lack typed time, 52 have unsupported modality, and all 14
L2 candidates lack explicit support IDs, structured claims, abstraction method,
closure specification, and source turn/session coverage. Authoritative-ready
L1/L2 counts and every automatic write count are zero. The guard fingerprint
remained
`e184b6caf2998acf1c8700bc84d24bbafd49ab9c8f15738d1af8cc484ee5ebcc`.

The formal ledger/assessment/report SHA-256 values are
`2ed9e6fdeaca81964fff542287adfc2980145b978b7ef9ed6dfc5f914ebca7c0`,
`d5d00b2edebdaf7b2409f09a647c0bce41d1ce29e5c2e1d3c67e646fb5f5e92e`,
and `b7e29b605ac46b0ff85c1be963f9d3fca7693f3c445a64188f67b8eecc3d9bf9`.
All three files are mode `0444` and an isolated replay was byte-identical.
Extraction-manifest replay was semantically identical after normalizing only
the migrated `provenance.turn_manifest` and `provenance.dialogue_manifest`
absolute paths; the frozen historical `final-knowledge.json` was not rewritten.

Independent review after v1 added condition/scope, derivation/inference,
speaker-binding, lifecycle, envelope-coverage, optional-object, and failure-path
repairs in v2. A second review found that v2 still did not validate or preserve
`confirmed_by`/`added_by` operation ownership; foreign `added_by` could change
candidate classification. v3 reconstructs the hash-bound operation ownership
map, rejects unknown/cross-candidate operation references, and preserves exact
operation provenance. v1/v2 remain immutable audit artifacts.

Fresh verification was focused bridge `51 passed`, knowledge pipeline `197
passed`, full natural benchmark `270 passed`, and `compileall` exit `0`.
Bridge-v1/v2 hashes remained unchanged.
The H100 virtual environment required `nltk 3.10.0` to collect the existing
knowledge-pipeline tests. The next action is a dev-only typed extractor v2; no
fresh hidden evaluation is created until its dev gates pass.

## Acceptance Criteria

- The frozen extraction ledger replays with exact semantic and hash binding.
- Every projected record has one deterministic compatibility envelope.
- Raw extraction structure and deterministic bridge safety are separate.
- Missing typed semantics are visible and block materialization.
- No authoritative memory surface changes.
- Formal outputs are immutable and replay-identical.
- The next typed-extractor v2 input contract is explicit and machine-readable.
- Confirm/add operation provenance is exact and candidate-scoped.
