# Typed Extractor Fresh-V2 Hidden Materialization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Atomically publish the exact preregistered L1 24/L2 12 authored hidden dataset and its hash-based pre-model chronology without running a model.

**Architecture:** A standalone materializer validates the active authoring receipt, stages ten canonical JSON payloads plus one chronology receipt, validates the staged tree, and atomically renames it to the absent formal root. The receipt-bound authoring module and test remain byte-identical.

**Tech Stack:** Python 3.13, Pydantic v2, pytest, canonical JSON, SHA-256, `tempfile`, Linux `renameat2(RENAME_NOREPLACE)`, existing `.venv-h100`.

## Global Constraints

- Work only in `/public/home/wwb/KE-mem/KE-memory-next-prep-20260727`; do not initialize Git.
- Do not modify `typed_extractor_fresh_v2_authoring.py`, its test, prereg-v3, v1/v2 authoring receipts, candidate v3 queue, query files, or frozen prior artifacts.
- Call `validate_fresh_v2_active_authoring_receipt` before any staging write.
- Materialize exactly L1 24 and L2 12 cases; do not filter, replace, resample, or add adjudications.
- Create no model-run/proposal/provenance/score/report path and make no model request.
- Execute no authoritative L1/L2/revision/source-revision/closure/identity/membership/snapshot/aggregate write.
- Preserve `LONGMEMEVAL-6d550036` as `structured_l2_identity_unresolved`.

---

### Task 1: Write Materialization Tests And Observe RED

**Files:**
- Create: `tests/natural_memory_benchmark/test_typed_extractor_fresh_v2_materialization.py`
- Test target: `tools/natural_memory_benchmark/typed_extractor_fresh_v2_materialization.py`

**Interfaces:**
- Expects `materialize_fresh_v2_hidden(Path, Path, Path, str) -> dict[str, Any]`.
- Expects `validate_fresh_v2_hidden_materialization(Path, Path, Path) -> dict[str, Any]`.

- [x] Add a test that copies prereg-v3 plus both receipts to a temporary tree, calls the writer, and asserts exact L1/L2 names, `24/12` counts, canonical equality with `build_fresh_v2_authoring_bundle`, file mode `0444`, absent `model-runs`, and chronology schema/status.
- [x] Add fail-closed tests for existing final root, missing/writable/tampered v2 receipt, predecessor drift, invalid UTC, output/manifest/materializer drift, added model-run paths, and second materialization.
- [x] Add atomicity/no-clobber tests for injected publication failure and a concurrently created empty target; assert exact staging cleanup without target removal.
- [x] Run `PYTHONDONTWRITEBYTECODE=1 .venv-h100/bin/python -m pytest -q -p no:cacheprovider tests/natural_memory_benchmark/test_typed_extractor_fresh_v2_materialization.py` and confirm the initial module-missing RED.

### Task 2: Implement The Standalone Atomic Materializer

**Files:**
- Create: `tools/natural_memory_benchmark/typed_extractor_fresh_v2_materialization.py`
- Test: `tests/natural_memory_benchmark/test_typed_extractor_fresh_v2_materialization.py`

**Interfaces:**
- Consumes the active v2 receipt and pure `FreshV2AuthoringBundle`.
- Produces the two public functions from Task 1 and the immutable formal layout.

- [x] Define strict `MaterializedArtifact` and `FreshV2MaterializationReceipt` Pydantic models with exact schema/status, `24/12` counts, exact output-name sets, zero write counts, false authorization fields, and unresolved LongMemEval status.
- [x] Implement canonical layer mapping:

```python
LAYER_VALUES = {
    "l1": {
        "source-cases-l1.json": "source",
        "public-l1.json": "public",
        "authority-l1.json": "authority",
        "gold-l1.json": "gold",
        "manifest-l1.json": "manifest",
    },
    "l2": {
        "source-cases-l2.json": "source",
        "public-l2.json": "public",
        "authority-l2.json": "authority",
        "gold-l2.json": "gold",
        "manifest-l2.json": "manifest",
    },
}
```

- [x] Implement preflight: final root absent, valid UTC label, active receipt validation before staging, exact approved receipt SHA/mode, valid authoring bundle, and parent directory available.
- [x] Implement unique sibling staging, canonical writes, exact `0444` modes, chronology construction, staging validation, directory mode `0775`, and no-clobber `renameat2(RENAME_NOREPLACE)` publication.
- [x] Implement exception cleanup with `shutil.rmtree(staging)` only when the exact staging directory exists and the final root remains untouched.
- [x] Implement post-publication validation that binds current code/dependency hashes to the active receipt, rebuilds the authoring bundle, checks canonical bytes/modes and chronology hashes, and rejects model-run paths.
- [x] Run the focused test file and make all tests pass while the official evaluation root remains absent.

### Task 3: Review, Verify, And Perform The One-Time Materialization

**Files:**
- Generate: `artifacts/automatic-extraction-assessment/typed-extractor-v2-fresh-hidden-v2/`
- Modify after freeze: `README.md`, `AGENTS.md`, `安排.md`, and this plan.

**Interfaces:**
- Consumes active receipt SHA-256 `4ce77c20c2941a66c3e74c1bd561e9d5ceee360a3723b75eed694fc47267c94b`.
- Produces the only formal fresh-v2 hidden source/public/authority/gold/manifest/chronology bundle.

- [x] Obtain an independent read-only review with no open Critical/Important finding; repair findings through a failing regression test and re-review.
- [x] Run focused materialization/authoring, all typed-extractor, complete natural-memory, knowledge-pipeline, and `compileall` verification with the official root still absent.
- [x] Recheck active receipt, prereg, v1 receipt, candidate queue, guard hashes, credential pattern, zero automatic writes, and no active workspace test/API/model session.
- [x] Call the materializer once with a current UTC label; do not create any proposer/model run.
- [x] Validate all eleven files, exact modes/hashes/counts, chronology binding, byte-identical deterministic replay, absent model-run paths, unchanged protected hashes, and unresolved LongMemEval status.
- [x] Update workspace fact sources and record that the next stage is isolated public-only proposer freeze, not scoring or pipeline integration.

## Completion Record

- Published at caller-supplied label `2026-07-29T02:10:29Z`.
- Chronology SHA-256: `278d9ba8f4d466984b11644de920b815de11cbdb56b49dff0dd797543b12b05e`.
- Materializer module/test SHA-256: `57a8e6df5c6fc4739b50cf842f53063610f2c5bfc0ada21b84de0d87ab65a606` / `84f88ce70ca818a27b520b21d5a43a7f46a3bba8d2393bf0ee5417afc24191ac`.
- Pre-freeze verification: focused `64 passed`, typed `192 passed`, knowledge `197 passed`, natural `603 passed`.
- Post-freeze verification: focused `63 passed, 1 deselected`, typed `191 passed, 1 deselected`, knowledge `197 passed`, natural `602 passed, 1 deselected`.
- The deselected receipt-bound authoring test asserts the formal root is absent and is intentionally preserved byte-identical as pre-materialization evidence.

## Post-Materialization Evaluation Record

- Isolated public-only proposer runs completed once per layer with no semantic retry: L1 `run-20260729T024500Z-deepseek-chat-official-typed-l1-fresh-hidden-v2`, L2 `run-20260729T024501Z-deepseek-chat-official-typed-l2-fresh-hidden-v2`. Both requested official `deepseek-chat`; both raw responses identified `deepseek-v4-flash`.
- Proposals/provenance froze before authority/gold scoring. L1/L2 proposal SHA-256: `5e0ac9cf0ed5dd50cf2bffa78add1e988d599856ba94820639e5f763527c4a05` / `59e1f052c2157782c1f8266d91a9ae319a2ba87cb7b065d58bf8a6adbd8a9da6`.
- Final status is `not_qualified`. L1 raw quality failed on one false emission plus role/local-entity, time, and condition/scope fields. L2 raw quality failed on structured claims, abstraction, and closure. Both layers had four deterministic gate interventions; the preregistered zero-intervention safety threshold therefore failed even though deterministic critical materialization stayed zero.
- Compatibility scoring used ephemeral read-only views because the legacy scorer rejects the additional source-case manifest binding and the fresh L2 threshold shape. Official manifests and proposals were not modified. L1's first absolute-path guard score is superseded by canonical `score-v2.json` without a model rerun. Final L1/L2 score SHA-256: `f09d754e6848ade7fbbc0fc723899c63a7e24947c3c2cb6a13401ae1bbd0dbc8` / `6d656d9883803f1b8ca5a200babfa285547f98e99e048fc3908517dc31e8c092`.
- Final read-only audit passed `117/117` checks. The two byte-identical staging proposal copies were removed. Fresh verification: typed `191 passed, 1 deselected`, knowledge `197 passed`, natural `602 passed, 1 deselected`, plus successful `compileall` and `tabnanny`. The sole deselection is `test_bundle_is_deterministic_and_does_not_mutate_formal_artifacts`, which intentionally binds pre-materialization root absence.
- No pipeline integration or authoritative write is authorized. The next work must use new dev/diagnostic data for the recorded L1/L2 error taxonomies; a new fresh-hidden preregistration is forbidden until strict raw metrics pass and gate interventions reach zero.

## Self-Review

- Spec coverage: atomic publish, active-receipt preflight, exact composition, chronology, post-validation, failure cleanup, review, and unchanged authority boundaries are assigned.
- Placeholder scan: no `TBD`, `TODO`, deferred error handling, or unspecified artifact is present.
- Type consistency: both public signatures use `Path` arguments; only the writer accepts the UTC label.
