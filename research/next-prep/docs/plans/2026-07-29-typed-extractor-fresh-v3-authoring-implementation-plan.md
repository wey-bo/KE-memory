# Typed Extractor Fresh-Hidden V3 Authoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the deterministic 42-case fresh-v3 authoring mechanism and freeze its implementation receipt before any formal hidden artifact or model request exists.

**Architecture:** A new standalone module owns strict blueprints, deterministic in-memory L1/L2 rendering, contamination checks, and one immutable receipt. It imports only stable schema/IO types and the frozen preregistration registry; it does not modify v1/v2 authoring, the shared CLI, scorer, query, identity, or authority code.

**Tech Stack:** Python 3.13, Pydantic v2, pytest, canonical JSON/SHA-256 helpers, H100 `.venv-h100`.

## Global Constraints

- Work only in `/public/home/wwb/KE-mem/KE-memory-next-prep-20260727`; do not initialize Git or create a worktree.
- Treat the reported remote Codex as a concurrent writer; never overwrite a target that appears after the pre-edit audit.
- Keep the formal v3 preregistration and every prior artifact byte-identical.
- Keep `typed-extractor-v3-fresh-hidden-v1` and v3 materialization module/test absent throughout this stage.
- Use all L1 24 and L2 18 blueprints in exact family order/counts; prohibit selection, filtering, replacement, retry, and resampling.
- Produce no hidden data and make no model/API request.
- Do not modify shared CLI/scorer/model-run/query/identity/authority code.
- Do not authorize pipeline integration or any automatic memory write.

---

### Task 1: Write And Observe Failing Authoring Tests

**Files:**
- Create: `tests/natural_memory_benchmark/test_typed_extractor_fresh_v3_authoring.py`
- Test target: `tools/natural_memory_benchmark/typed_extractor_fresh_v3_authoring.py`

**Interfaces:**
- `build_fresh_v3_authoring_bundle(preregistration_path: Path) -> FreshV3AuthoringBundle`
- `validate_fresh_v3_authoring_bundle(bundle: FreshV3AuthoringBundle, preregistration_path: Path) -> dict[str, Any]`
- `freeze_fresh_v3_authoring_receipt(preregistration_path: Path, evaluation_root: Path, workspace_root: Path, receipt_time: str) -> dict[str, Any]`
- `validate_fresh_v3_authoring_receipt(preregistration_path: Path, evaluation_root: Path, workspace_root: Path) -> dict[str, Any]`

- [ ] Write tests for exact L1/L2 family order/counts, strict existing payload models, deterministic bytes, public/private separation, evidence/reference closure, and prior disjointness.
- [ ] Write mutation tests for duplicate blueprint IDs, invalid offsets, leaked private values, L1 lifecycle/operation drift, L2 literal/support/closure/source drift, and contamination overlap.
- [ ] Write receipt tests for strict fields, exact hashes, mode `0444`, impossible UTC, prereg/code/test drift, idempotence, and premature evaluation/materialization/model paths.
- [ ] Run `.venv-h100/bin/python -m pytest -q tests/natural_memory_benchmark/test_typed_extractor_fresh_v3_authoring.py` and confirm collection fails only because the authoring module is absent.

### Task 2: Implement The Pure Authoring Bundle

**Files:**
- Create: `tools/natural_memory_benchmark/typed_extractor_fresh_v3_authoring.py`
- Test: `tests/natural_memory_benchmark/test_typed_extractor_fresh_v3_authoring.py`

**Interfaces:**
- The builder returns strict in-memory source/public/authority/gold/manifest layers and writes nothing.
- The validator returns exact counts, family distributions, contamination counts, and `formal_artifacts_created=False`.

- [ ] Add frozen dataset/prereg/namespace constants and strict blueprint, layer, bundle, inventory, and receipt models.
- [ ] Add deterministic opaque-ID, normalization, evidence-offset, canonical-semantic-signature, prior-inventory, and private-leak helpers.
- [ ] Add 24 new L1 blueprints, three in each preregistered family, with full typed candidate and provenance closure.
- [ ] Add 18 new L2 blueprints, two in each preregistered family, with at least two L1 supports and exact claim/abstraction/closure/source binding for emissions.
- [ ] Render existing strict L1/L2 payload models, validate all invariants, and make the focused tests pass without creating the evaluation root.

### Task 3: Freeze The Authoring Implementation Receipt

**Files:**
- Generate: `artifacts/automatic-extraction-assessment/typed-extractor-v3-fresh-hidden-prereg-v1/authoring-implementation-receipt.json`

**Interfaces:**
- Consumes the exact preregistration, authoring module/test, stable dependencies, blueprint manifests, prior hashes, candidate queue, and guard fingerprint.
- Writes only the receipt and returns its strict payload.

- [ ] Recheck concurrent target paths, formal root, materialization module/test, model paths, and receipt absence immediately before freeze.
- [ ] Run focused and adjacent authoring/prereg tests before freeze.
- [ ] Freeze once with a caller-supplied UTC label; set mode `0444` and validate exact code/test/dependency/prereg/blueprint/prior hashes.
- [ ] Confirm the preregistration root contains only the original preregistration and the receipt, while the evaluation root remains absent.

### Task 4: Audit And Record The Stage

**Files:**
- Modify after receipt validation: `README.md`
- Modify after receipt validation: `AGENTS.md`
- Modify after receipt validation: `安排.md`
- Modify after receipt validation: this plan

- [ ] Run all typed-extractor tests with the documented pre-materialization deselection, knowledge-pipeline tests, full natural-memory tests with the same deselection, `compileall`, and `tabnanny`.
- [ ] Revalidate the receipt, byte/hash/mode/future absence, candidate queue, guard fingerprint, credential pattern, and every zero-write boundary.
- [ ] Recheck target timestamps before fact-source edits and preserve any concurrent unknown change.
- [ ] Record exact receipt identity, verification evidence, no-hidden/no-model status, and the next one-time materialization boundary.

## Self-Review

- The plan covers every preregistered family and chronology requirement.
- The module has one responsibility: pure authoring plus its implementation receipt.
- No task creates hidden data, invokes a model, or changes a frozen/shared module.
- There are no placeholders or implicit authorization decisions.
