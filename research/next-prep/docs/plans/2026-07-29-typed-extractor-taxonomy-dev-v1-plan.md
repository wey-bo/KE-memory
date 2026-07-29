# Typed Extractor Taxonomy Dev V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and qualify fresh taxonomy-driven L1/L2 diagnostic slices without reading or reusing fresh-v2 hidden case content.

**Architecture:** A focused authoring module projects new private diagnostic source JSON into the existing typed extractor public/authority/gold/manifest contracts with a new opaque namespace. Existing shared scorer, proposer runner, fresh-v2 artifacts, query modules, and authoritative memory remain unchanged. The model baseline and any prompt repair are separate immutable stages.

**Tech Stack:** Python 3.13, Pydantic v2, pytest, canonical JSON/SHA-256 helpers, existing typed extractor contracts and official OpenAI-compatible proposer runners, H100 `.venv-h100`.

## Global Constraints

- Work only in `/public/home/wwb/KE-mem/KE-memory-next-prep-20260727`; do not initialize Git or create a worktree.
- Do not read, copy, or reuse fresh-v2 hidden `source-cases`, `authority`, `gold`, raw proposals, error-analysis case text, or scoring case details during source authoring.
- Do not modify fresh-v2, its preregistration/receipts/manifests/proposals/scores, candidate v3 queue, shared scorer/model-run modules, query files, or authoritative memory code.
- Diagnostic source provenance is `diagnostic_authored`; it is not natural benchmark evidence.
- Proposals/provenance freeze before authority/gold scoring. API credentials are process-only.
- No automatic writes or pipeline integration; preserve unresolved LongMemEval identity and non-authoritative embedding boundary.

---

### Task 1: Implement Strict Taxonomy Source Contracts

**Files:**
- Create: `tools/natural_memory_benchmark/typed_extractor_taxonomy_dev.py`
- Create: `tests/natural_memory_benchmark/test_typed_extractor_taxonomy_dev.py`

**Interfaces:**
- `prepare_taxonomy_dev_slice(source_path: Path, layer: Literal["l1", "l2"], output_root: Path, prior_roots: Sequence[Path]) -> dict[str, Any]`
- `validate_taxonomy_dev_slice(source_path: Path, layer: Literal["l1", "l2"], root: Path, prior_roots: Sequence[Path]) -> dict[str, Any]`

- [x] Write failing tests for strict extras, version/dataset mismatch, duplicate IDs, invalid spans, public leakage, overlap, distribution, closure, and mutable outputs.
- [x] Implement strict private L1/L2 case/source models and a new namespace `typed-extractor-taxonomy-{layer}-dev-v1:2026-07-29`.
- [x] Implement deterministic opaque projection into existing public/authority/gold models and exact evidence/support/lifecycle remapping.
- [x] Implement new-source-only authoring validation and prior-root overlap rejection without reading fresh-v2 hidden content.
- [x] Implement canonical prepare/validate, `0444` source/output modes, exact manifest hashes, diagnostic-only claim boundary, and byte replay.
- [x] Run the focused test file and resolve all contract failures before authoring formal roots.

### Task 2: Author And Freeze New L1/L2 Diagnostic Roots

**Files:**
- Create: `artifacts/automatic-extraction-assessment/typed-extractor-taxonomy-l1-dev-v1/diagnostic-source-l1.json`
- Create: `artifacts/automatic-extraction-assessment/typed-extractor-taxonomy-l2-dev-v1/diagnostic-source-l2.json`
- Generate: matching public/authority/gold/manifest files under both roots.

**Interfaces:**
- L1 source has exactly 20 cases with distribution `false_emission=3`, `false_abstention=3`, `role_or_local_entity=4`, `time=3`, `condition_or_scope=3`, `evidence=2`, `derivation_or_speaker=1`, `lifecycle=1`.
- L2 source has exactly 12 cases with four abstentions and eight emissions, including one state-summary and one preference-aggregation case.

- [x] Author all new source text, private IDs, candidate IDs, evidence spans, and typed gold in the new source files; do not derive strings from fresh-v2 hidden files.
- [x] Run source validators and focused replay tests in temporary roots.
- [x] Prepare the two formal diagnostic roots once, set all source/output/manifest files to `0444`, and validate them.
- [x] Record source/output/manifest hashes, distribution, zero-write boundary, prior-overlap count, and diagnostic-only status.

### Task 3: Freeze Unchanged-Prompt Baseline

**Files:**
- Generate immutable baseline roots under the two taxonomy dev roots.
- Copy current passing diagnostic prompts byte-for-byte into the corresponding run directories.
- Use existing `typed_extractor_l1_api_run.py` and `typed_extractor_l2_api_run.py` only.

**Interfaces:**
- One no-history, public-only proposer request per layer; requested model `deepseek-chat` and process-only API credential.
- Dispatch -> raw response -> proposals -> provenance freeze order.
- Independent scorer consumes frozen authority/gold only after proposals/provenance freeze.

- [x] Freeze dispatches and verify public/prompt/input hashes before any request.
- [x] Run one official proposer per layer with no semantic retry and archive raw response without credentials.
- [x] Freeze proposals/provenance and verify raw-response-to-proposal equality before scoring.
- [x] Run existing scorers through read-only compatibility views only if required; never alter formal manifests.
- [x] Run strict qualification and classify raw/gate failures separately; preserve `not_qualified` and all zero-write boundaries.

### Task 4: Diagnostic-Only Prompt Repair

**Files:**
- Create new immutable prompt revisions under each taxonomy dev root.
- Generate new model-run/scoring/qualification artifacts under those roots.
- Modify only the taxonomy diagnostic prompt, not shared scorer or fresh-v2 prompt.

**Interfaces:**
- Repair decisions may use only Task 3 taxonomy metrics and this new diagnostic source; fresh-v2 hidden case text is prohibited.
- A repaired layer remains non-authoritative and diagnostic-only.

- [x] For L1, address false emission, explicit participant/local-entity decomposition, event/valid time distinction, and condition/scope binding.
- [x] For L2, address structured claim literal binding, state-summary/preference abstraction choice, and multi-support closure.
- [x] Run one new no-history public-only request per repaired prompt revision; freeze before scoring.
- [x] Require exact `1.0` strict metrics, raw critical false emissions `0`, gate interventions `0`, deterministic critical materialization `0`, guard unchanged, and zero writes before marking a layer repaired.
- [x] Stop the wave if a layer still fails; author the next repair only from the new diagnostic result.

### Task 5: Audit And Record The Gate

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `安排.md`
- Modify: this plan

- [x] Recompute all formal hashes, modes, model/proposal/provenance freeze order, manifest bindings, guard fingerprint, candidate queue hash, credential scan, and zero writes.
- [x] Run typed extractor tests, `tests/knowledge_pipeline`, complete natural-memory tests excluding only the documented root-absence test, `compileall`, and `tabnanny`.
- [x] Record raw quality and deterministic gate safety separately and state whether a new fresh-hidden preregistration is authorized.
- [x] Keep pipeline integration, authoritative writes, external system reruns, and LongMemEval identity resolution unauthorized.

## Self-Review

- Every taxonomy category from fresh-v2 has a new diagnostic authoring target; no hidden case content is needed.
- The source module is isolated from shared scorers and query/authority modules.
- Baseline, repair, scoring, qualification, and final audit are distinct immutable stages.
- No task creates a fresh-hidden evaluation or authorizes a write.

## Completion Record

- Formal L1/L2 source SHA-256 are `d830246820c1df017baaace328111105f04858ce30f86d624b4a890be49d37b5` and `693cea99322c9589864749213ad1705ba6eabf3323bd3a19d6e5ec85d9a98418`; manifest SHA-256 are `10292706e91d1eca7a0285fc83fd57cf0912ad51faff519fe54000864683029d` and `bed50074ee41a3119a6e5803a0a24d403aa7557f75ceb8491c54ba132b31cdf8`. Both validators report zero prior identifier/evidence overlap and diagnostic-only status.
- Unchanged-prompt L1 baseline `run-20260729T041500Z-deepseek-chat-official-typed-l1-taxonomy-baseline-v1` is strictly `not_qualified`: every strict metric is `1.0` except role/local-entity `0.9375`. Raw quality fails while deterministic gate safety passes with intervention and critical counts `0`; the shared qualifier's `status=qualified` means the check ran, while `dev_repair_ready=false` is the gate result. Proposal/score SHA-256 are `69f3563fe6a35e473ac39f574be1a7e6a2467bab3483ff721313541dc97bf6d7` / `13ce447bd49f204318158a50a97ffd6cc120512db66aa2e85848f43fa1576ad3`.
- Unchanged-prompt L2 baseline `run-20260729T041501Z-deepseek-chat-official-typed-l2-taxonomy-baseline-v1` passes strict raw and gate qualification without repair. Proposal/score/qualification SHA-256 are `c735225a119c546fcba44372b5c56f32a2d1bd7caba3997ab51af4dc3ee25084` / `1c04a09d29f7d23abba85df249fb4194fd99bea2faca1ef7a288aa23444ee796` / `643944140f7348347448de3728b891d9e1209f05ba96384d3885b998e6f00ea4`.
- L1 repair-v1 used only the new diagnostic role error and added a general prepositional-participant construction order; no diagnostic full message or private case ID appears in the prompt. Prompt/proposal/score/qualification SHA-256 are `a5250a453863f3cfd388613d6633d8a529485a11c5226d2965c8235a9c1dc342` / `db468cc0251abe48bfb1c98dead13471b16e32556df3a61da528e3e29de95750` / `dfbb8a415e6654b89f4ac09e0ae72bc45d1687cec13e69cbd2211f6ef295bb92` / `92e627fb72ba18ef1458aa9ef810bf8bf9b5efad3a12cc0f7559231e07a3c3de`. All strict metrics are `1.0`; all three safety counts are `0`.
- All three runs used one official `deepseek-chat` request per revision with no retry and response model `deepseek-v4-flash`. Dispatch/raw/proposals/provenance froze before independent authority/gold scoring; all formal files are `0444`. The final read-only audit passed `67/67`; candidate queue SHA remains `518ead9de8627a9a4384df8cdd9b8728a21fcf797f6b0f3d208dfcb28ac41c0f`, guard fingerprint remains `e184b6caf2998acf1c8700bc84d24bbafd49ab9c8f15738d1af8cc484ee5ebcc`, and credential pattern count is `0`.
- Fresh verification: taxonomy focused `19 passed`; typed extractor `210 passed, 1 deselected`; knowledge pipeline `197 passed`; natural memory `637 passed, 1 deselected`; `compileall` and `tabnanny` pass. The sole deselection remains the pre-materialization root-absence test and was not modified.
- A separately frozen typed-extractor fresh-hidden-v3 preregistration is now authorized. No fresh hidden was created in this wave. Pipeline integration, automatic L1/L2/revision/closure/identity/membership writes, external system reruns, and identity resolution remain unauthorized; `LONGMEMEVAL-6d550036` stays `structured_l2_identity_unresolved`.
