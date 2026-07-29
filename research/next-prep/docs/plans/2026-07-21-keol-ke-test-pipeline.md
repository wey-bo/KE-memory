# KEOL KE-test Pipeline Implementation Plan

**Goal:** Use the latest visible KEOL code (`44631e64fd07c9b85f22e36035bf49c882dba592`) to extract a baseline ontology and assertions from all 43 turns in `data/gold-candidates/KE-test.json`, with model judgments delegated to Codex subagents.

**Architecture:** A deterministic adapter derives one lossless text unit per `user -> agent` turn and keeps a JSON Pointer back to `data/gold-candidates/KE-test.json`. Subagents return the exact KEOL `KnowledgeGraph` node/edge contract. The adapter validates and materializes those graphs as KEOL rawdata output, after which the unmodified KEOL reader, ontology builder, projection, store, and validator produce the native ontology.

**Tech Stack:** Python 3.13 standard library, pytest, Pydantic 2, KEOL `44631e6`.

---

### Task 1: Turn Adapter And Graph Contract

**Files:**
- Create: `tools/keol_baseline/keol_ke_test_adapter.py`
- Create: `tests/test_keol_ke_test_adapter.py`

1. Write tests for 43 turn units, stable IDs, exact `user`/`agent` text, JSON Pointers, complete model-unit coverage, unique node IDs, and valid edge references.
2. Run `python -m pytest tests/test_keol_ke_test_adapter.py -q` and confirm import/behavior failure.
3. Implement only the tested adapter and graph validation functions.
4. Re-run the same test and confirm all tests pass.

### Task 2: KEOL Rawdata Materialization

**Files:**
- Modify: `tools/keol_baseline/keol_ke_test_adapter.py`
- Modify: `tests/test_keol_ke_test_adapter.py`
- Generate: `artifacts/keol-baseline/input/manifest.json`
- Generate: `artifacts/keol-baseline/input/turns/*.txt`
- Generate: `artifacts/keol-baseline/model-extraction/*.json`
- Generate: `artifacts/keol-baseline/native-output/KE-test/_metadata.json`
- Generate: `artifacts/keol-baseline/native-output/KE-test/text/*/chunk_000.json`

1. Add a failing test proving raw turn text and turn metadata survive into each KEOL chunk.
2. Implement materialization using the current KEOL rawdata JSON schema.
3. Generate 43 turn documents from `data/gold-candidates/KE-test.json`.
4. Dispatch subagents over disjoint candidate batches. Each subagent must read only `data/gold-candidates/KE-test.json`, the generated manifest/turn documents, and KEOL's graph schema/prompt; it must not read v0.2 extraction artifacts.
5. Merge and validate every model graph before materialization.

### Task 3: Native KEOL Build And Validation

**Files:**
- Generate: `artifacts/keol-baseline/native-output/KE-test/onto/**`
- Generate: `artifacts/keol-baseline/run/KEOL-run.json`

1. Run `build_ontology(..., use_llm=False, validate=True, strict_validation=True)` from `C:\Users\86137\Desktop\Haitun-agent\KEOL\src` against the materialized dataset.
2. Run `validate_ontology_output(..., write=True, strict=True)` independently.
3. Record the exact KEOL commit, model/subagent provenance, input counts, model graph counts, ontology counts, and validation status in `artifacts/keol-baseline/run/KEOL-run.json`.
4. Treat this as a KEOL baseline, not a final gold annotation; do not import conclusions from v0.2.

### Task 4: Human-Readable Export And Workspace State

**Files:**
- Replace: `artifacts/keol-baseline/views/KE-ontology.json`
- Replace: `artifacts/keol-baseline/views/KE-extraction.json`
- Replace: `artifacts/keol-baseline/views/KE.txt`
- Update: `artifacts/keol-baseline/config/KE-experiment-config.md`
- Update: `artifacts/keol-baseline/reports/KE-experiment-report.md`
- Update: `AGENTS.md`
- Update: `安排.md`

1. Export aggregate views under `artifacts/keol-baseline/views/` from the native KEOL files without changing their semantics.
2. Render assertions grouped by `candidate_id` and `turn_index`; keep evidence/source coordinates.
3. Mark v0.2 as superseded and document known KEOL baseline limitations: no conversation-aware reader, no literal term in the ontology model, no automatic nested KE generation, and chunk-level rather than span-level Evidence.
4. Run adapter tests, KEOL builder/validator tests, native output validation, reference closure checks, and source-unit coverage checks.
