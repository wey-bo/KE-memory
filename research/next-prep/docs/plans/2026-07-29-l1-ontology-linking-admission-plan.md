# L1 Ontology Linking and Admission Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use test-driven development for every
> behavior. This H100 workspace has no usable Git repository; do not initialize Git,
> create a worktree, or add commit steps.

**Goal:** Build a replayable, representation-independent Local L1 ontology linking and
deterministic admission layer that performs no authoritative writes.

**Architecture:** `l1_ontology_linking.py` owns the local ontology registry, subtype
closure, proposal records, candidate generation, and linked envelope. `l1_admission.py`
owns source/identity/lifecycle context and the fail-closed admission decision. A small
assessment runner in the admission module materializes only independent dev-v1
diagnostic outputs.

**Tech Stack:** Python 3.13, Pydantic 2, pytest, canonical JSON/SHA-256 helpers already in
`tools.natural_memory_benchmark`.

## Global Constraints

- Use `.venv-h100/bin/python` for every Python command.
- Do not modify `typed_extractor_l1.py`, `typed_extractor_l2.py`,
  `identity_resolution.py`, `authoritative_memory.py`, any Query module, shared
  `cli.py`, frozen artifacts, `README.md`, `AGENTS.md`, or `安排.md`.
- Do not read or reuse fresh-v2/v3 hidden cases, identifiers, model outputs, or errors.
- Do not create linking fresh-hidden data or connect the pipeline before both parallel
  sessions finish.
- WordNet 3.0 and schema.org 30.0 mappings are versioned advisory inputs only.
- Unknown concepts remain unresolved or produce extension proposals without canonical
  concept IDs.
- Embedding cannot authorize links, identity, facts, admission, or writes.
- Automatic L1/L2/identity/membership/closure/revision/snapshot/aggregate writes are
  exactly zero.

---

### Task 1: Registry and linking contract

**Files:**

- Create: `tools/natural_memory_benchmark/l1_ontology_linking.py`
- Create: `tests/natural_memory_benchmark/test_l1_ontology_linking.py`

**Interfaces:**

- Produces: `OntologyRegistry`, `OntologyConcept`, `PredicateRoleConstraint`,
  `ConceptLinkProposal`, `EntityLinkProposal`, `PredicateLinkProposal`,
  `ProvisionalConceptExtensionProposal`, `LinkedL1Candidate`,
  `build_diagnostic_ontology_registry`, `is_subtype`, and `link_l1_candidate`.
- Consumes: frozen `TypedL1Candidate`, `EvidenceSpanV2`, canonical JSON, and SHA-256
  helpers.

- [ ] Write failing model tests for duplicate/missing/cyclic registry concepts,
  canonical registry hash drift, external advisory authority flags, and unknown
  extension proposals that cannot hold a canonical concept ID.
- [ ] Run
  `.venv-h100/bin/python -m pytest tests/natural_memory_benchmark/test_l1_ontology_linking.py -q --import-mode=importlib -p no:cacheprovider --basetemp .tmp/l1-linking-red`
  and confirm collection fails because `l1_ontology_linking` does not exist.
- [ ] Implement the strict Pydantic models and registry hash validation, including local
  parent closure and cycle detection.
- [ ] Run the focused tests and confirm the registry/model cases pass.
- [ ] Add failing subtype and contextual linking tests for coffee preference, specific
  coffee cup, milk drink, milk ingredient, unknown drink, and same-surface different
  senses.
- [ ] Implement deterministic candidate generation that uses local alias candidates
  followed by predicate/operator/role/subtype constraints. Canonical individual IDs may
  only come from explicit caller bindings.
- [ ] Add failing hash/evidence tests for source candidate hash, registry binding,
  evidence-span completeness, unresolved candidate preservation, and deterministic
  replay.
- [ ] Implement the linked envelope and canonical hash validation, then run the full
  linking test file green.

### Task 2: Deterministic admission

**Files:**

- Create: `tools/natural_memory_benchmark/l1_admission.py`
- Create: `tests/natural_memory_benchmark/test_l1_admission.py`

**Interfaces:**

- Consumes: `LinkedL1Candidate`, `OntologyRegistry`, `RawArtifactRevision`,
  `SourceRecordRevision`, explicit canonical entity bindings with identity snapshot
  revision/hash, known lifecycle targets, source epistemics, and transaction time.
- Produces: `AdmissionPolicy`, `AdmissionContext`, `ProposedRevisionAction`,
  `AdmissionDecision`, and `admit_linked_l1`.

- [ ] Write failing evidence-closure tests for raw artifact binding, source quote hashes,
  exact source slices, evidence speaker binding, missing source revisions, and link
  evidence references.
- [ ] Run the admission test file and confirm failure is caused by the missing module.
- [ ] Implement hash, registry, source, and evidence checks. Tampered inputs return
  `reject` with deterministic reason codes.
- [ ] Add failing compatibility tests for category versus instance shape,
  predicate-role-subtype constraints, external-only concepts, resolved instance type,
  and unresolved identity.
- [ ] Implement compatibility and identity gates. Ambiguous, extension-required, and
  identity-unresolved inputs return `abstain`.
- [ ] Add failing modality, source-epistemic, transaction-time, lifecycle, conflict, and
  supersession tests, including hypothetical preference abstention.
- [ ] Implement the remaining gates and proposed actions. No path imports or calls
  `make_memory_unit_revision` or a persistence helper.
- [ ] Add deterministic replay and explicit eight-category zero-write assertions, then
  run both new focused test files green.

### Task 3: Dev-v1 diagnostic assessment

**Files:**

- Modify: `tools/natural_memory_benchmark/l1_admission.py`
- Modify: `tests/natural_memory_benchmark/test_l1_admission.py`
- Create: `artifacts/ontology-linking-assessment/dev-v1/assessment.json`
- Create: `artifacts/ontology-linking-assessment/dev-v1/assessment-report.md`
- Create: `artifacts/ontology-linking-assessment/dev-v1/manifest.json`

**Interfaces:**

- Produces: `run_dev_ontology_linking_assessment(output_root: Path)` with deterministic,
  immutable diagnostic files and no shared CLI registration.

- [ ] Write a failing assessment test that requires all eight authored cases, exact
  metric names, critical false admission `0`, and eight automatic write counts `0`.
- [ ] Implement the authored diagnostic builder and scorer using only public synthetic
  text from the design.
- [ ] Run the assessment twice in separate temporary directories and assert canonical
  bytes match.
- [ ] Materialize the official dev-v1 root with
  `.venv-h100/bin/python -m tools.natural_memory_benchmark.l1_admission --output-root artifacts/ontology-linking-assessment/dev-v1`.
- [ ] Re-run in place and confirm immutable replay succeeds without changing bytes.

### Task 4: Verification and independent review

**Files:**

- Verify only all new files and the recorded protected-file hash set.

- [ ] Run focused tests for both new modules.
- [ ] Run adjacent tests:
  `test_typed_extractor_l1.py`, `test_typed_extractor_l2.py`,
  `test_identity_resolution.py`, and `test_authoritative_memory.py`.
- [ ] Run
  `.venv-h100/bin/python -m compileall -q tools/natural_memory_benchmark/l1_ontology_linking.py tools/natural_memory_benchmark/l1_admission.py tests/natural_memory_benchmark/test_l1_ontology_linking.py tests/natural_memory_benchmark/test_l1_admission.py`.
- [ ] Run
  `.venv-h100/bin/python -m tabnanny tools/natural_memory_benchmark/l1_ontology_linking.py tools/natural_memory_benchmark/l1_admission.py tests/natural_memory_benchmark/test_l1_ontology_linking.py tests/natural_memory_benchmark/test_l1_admission.py`.
- [ ] Request an independent read-only code review, fix every Critical/Important finding
  under TDD, and re-run the affected checks.
- [ ] Confirm all protected hashes except concurrently active parallel-track files match
  the preflight baseline; report observed parallel-track drift without modifying it.
- [ ] Confirm no fresh linking hidden root, pipeline integration, or authoritative write
  artifact was created. Defer the full suite until the two parallel files are stable.
