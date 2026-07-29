# Knowledge-First Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run an evidence-preserving, two-pass knowledge extraction pipeline over all 43 turns in `data/gold-candidates/KE-test.json`, then extract typed keywords and align them to verified schema.org and WordNet candidates.

**Architecture:** Deterministic Python code prepares isolated model payloads, validates immutable first-pass records, applies append-only dialogue reconciliation operations, projects the active knowledge ledger, queries pinned vocabularies, and exports review artifacts. All semantic extraction and semantic candidate ranking are performed by fresh subagents from versioned prompts; the root agent never writes semantic answers itself.

**Tech Stack:** Python 3.13, Pydantic 2.10, pytest 8.3, standard-library JSON/hashlib/urllib, NLTK WordNet, Codex collaboration subagents.

---

## Preconditions And File Map

The workspace currently contains an empty `.git` directory and is not a valid Git repository. Do not initialize Git automatically. Commit steps below are conditional: run them only after the user creates or repairs the repository; otherwise record the completed task in `knowledge-extraction/run.json` and continue without pretending a commit exists.

The old KEOL and custom KE files are comparison artifacts only. No prompt builder or subagent may read `artifacts/keol-baseline/`, `archive/legacy-ke-v0.2/`, or any file within those directories.

Create these focused modules:

- `knowledge_pipeline/models.py`: Pydantic contracts and enums only.
- `knowledge_pipeline/source.py`: lossless `data/gold-candidates/KE-test.json` loading and isolated payload preparation.
- `knowledge_pipeline/evidence.py`: quote occurrence resolution and character-coordinate validation.
- `knowledge_pipeline/turn_pass.py`: first-pass output validation and immutable aggregation.
- `knowledge_pipeline/dialogue_pass.py`: reconciliation output validation and reference closure.
- `knowledge_pipeline/projector.py`: deterministic active-ledger projection.
- `knowledge_pipeline/keywords.py`: keyword output validation and per-knowledge coverage.
- `knowledge_pipeline/vocabulary.py`: pinned schema.org/WordNet bootstrap, lookup, and ID validation.
- `knowledge_pipeline/ranking.py`: candidate whitelist validation.
- `knowledge_pipeline/export.py`: `Knowledge.txt` and experiment report rendering.
- `knowledge_pipeline/verify.py`: end-to-end acceptance checks.
- `knowledge_pipeline/cli.py`: prepare/validate/project/query/export command entry points.
- `knowledge-extraction/prompts/*.md`: four versioned model prompts.
- `tests/knowledge_pipeline/*.py`: focused tests for every boundary.

### Task 1: Define The Knowledge Ledger Contracts

**Files:**
- Create: `knowledge_pipeline/__init__.py`
- Create: `knowledge_pipeline/models.py`
- Create: `tests/knowledge_pipeline/test_models.py`

- [ ] **Step 1: Write failing model-contract tests**

```python
from pydantic import ValidationError

from knowledge_pipeline.models import EvidenceDraft, KnowledgeDraft


def test_inferred_knowledge_requires_inference_basis() -> None:
    payload = {
        "knowledge_id": "K_CAND_001_001",
        "candidate_id": "CAND",
        "turn_index": 1,
        "statement": "用户担心计划发生冲突。",
        "subject": "用户",
        "predicate": "担心",
        "object": "计划发生冲突",
        "qualifiers": {"modality": "possible", "polarity": "positive"},
        "source_status": "user_reported",
        "derivation": "inferred",
        "evidence": [{"message": "user", "quote": "会不会冲突", "occurrence_index": 0, "evidence_role": "inference_support"}],
        "confidence": 0.9,
    }
    try:
        KnowledgeDraft.model_validate(payload)
    except ValidationError:
        return
    raise AssertionError("inferred knowledge without inference_basis must fail")


def test_evidence_occurrence_index_cannot_be_negative() -> None:
    try:
        EvidenceDraft(message="user", quote="文本", occurrence_index=-1, evidence_role="explicit_support")
    except ValidationError:
        return
    raise AssertionError("negative occurrence index must fail")
```

- [ ] **Step 2: Run the tests and verify the import failure**

Run: `python -m pytest tests/knowledge_pipeline/test_models.py -q`

Expected: FAIL because `knowledge_pipeline.models` does not exist.

- [ ] **Step 3: Implement the complete Pydantic contract**

Implement string enums for:

```python
SourceStatus = Literal["user_reported", "agent_generated", "tool_observed"]
Derivation = Literal["explicit", "context_completed", "inferred"]
Modality = Literal[
    "asserted", "questioned", "requested", "preferred", "planned",
    "hypothetical", "possible", "advised", "committed",
    "claimed_completed", "observed",
]
Polarity = Literal["positive", "negative"]
CompletionKind = Literal[
    "coreference", "ellipsis", "role_resolution", "temporal_resolution",
    "pragmatic_inference", "unresolved",
]
OperationKind = Literal["confirm", "correct", "supersede", "conflict", "add"]
KeywordType = Literal[
    "entity", "concept", "action", "event", "property", "relation",
    "time", "quantity", "condition", "modality",
]
MappingKind = Literal["exact", "narrow", "broad", "related"]
```

Define `EvidenceDraft`, `Evidence`, `Qualifiers`, `ContextCompletion`, `KnowledgeDraft`, `Knowledge`, `TurnPassOutput`, `ReconciliationOperation`, `DialoguePassOutput`, `KeywordDraft`, `KeywordPassOutput`, `VocabularyCandidate`, and `CandidateRanking`.

Required validators:

```python
@model_validator(mode="after")
def require_inference_basis(self):
    if self.derivation in {"context_completed", "inferred"} and not self.inference_basis.strip():
        raise ValueError("context-completed and inferred knowledge require inference_basis")
    if self.derivation == "explicit" and self.inference_basis:
        raise ValueError("explicit knowledge must not carry inference_basis")
    return self
```

Use `ConfigDict(extra="forbid")` on every model. Constrain confidence and scores to `[0, 1]`, make statement/subject/predicate non-empty, allow `object` to be `None`, and keep all qualifier arrays as empty lists by default.

- [ ] **Step 4: Run the model tests**

Run: `python -m pytest tests/knowledge_pipeline/test_models.py -q`

Expected: PASS.

- [ ] **Step 5: Commit if Git is valid**

```powershell
git add knowledge_pipeline/__init__.py knowledge_pipeline/models.py tests/knowledge_pipeline/test_models.py
git commit -m "feat: define knowledge extraction contracts"
```

### Task 2: Preserve Source Turns And Materialize Evidence Coordinates

**Files:**
- Create: `knowledge_pipeline/source.py`
- Create: `knowledge_pipeline/evidence.py`
- Create: `knowledge_pipeline/cli.py`
- Create: `tests/knowledge_pipeline/test_source_and_evidence.py`

- [ ] **Step 1: Write failing losslessness and quote-resolution tests**

```python
from knowledge_pipeline.evidence import resolve_evidence
from knowledge_pipeline.source import load_turn_units


def test_ke_test_has_ten_candidates_and_43_turns() -> None:
units = load_turn_units("data/gold-candidates/KE-test.json")
    assert len({item.candidate_id for item in units}) == 10
    assert len(units) == 43
    assert sum(bool(item.user) + bool(item.agent) for item in units) == 86


def test_resolve_second_occurrence_uses_unicode_offsets() -> None:
    result = resolve_evidence("休假，然后休假。", message="user", quote="休假", occurrence_index=1, evidence_role="explicit_support")
    assert result.start == 5
    assert result.end == 7
    assert "休假，然后休假。"[result.start:result.end] == result.quote
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/knowledge_pipeline/test_source_and_evidence.py -q`

Expected: FAIL because source/evidence functions do not exist.

- [ ] **Step 3: Implement immutable source units and payload writers**

`load_turn_units()` must parse only the canonical `data/gold-candidates/KE-test.json`, reject unknown candidate/turn fields, and return frozen records containing `candidate_id`, `candidate_index`, `turn_index`, `source`, `user`, `agent`, and JSON Pointers for both messages.

`write_turn_inputs()` writes one file per turn under `knowledge-extraction/inputs/turns/` and a manifest containing SHA-256 hashes of the exact User and Agent strings. It must never read any prior extraction artifact.

Create an `argparse` CLI skeleton with a required subcommand and a `prepare-turns` handler that calls `write_turn_inputs()`. Later tasks extend this same parser; no task may replace earlier subcommands.

- [ ] **Step 4: Implement deterministic evidence materialization**

```python
def resolve_evidence(text: str, **draft: object) -> Evidence:
    quote = str(draft["quote"])
    occurrence_index = int(draft["occurrence_index"])
    starts = []
    cursor = 0
    while True:
        found = text.find(quote, cursor)
        if found < 0:
            break
        starts.append(found)
        cursor = found + 1
    if occurrence_index >= len(starts):
        raise ValueError("evidence quote occurrence does not exist")
    start = starts[occurrence_index]
    return Evidence(**draft, start=start, end=start + len(quote))
```

Select the User or Agent source text from `message`; `tool_observed` evidence still points to the exact tool-result span inside the Agent message.
`start/end` are Unicode character offsets with a left-closed, right-open interval; they are always computed from `quote + occurrence_index`, never trusted from model output.

- [ ] **Step 5: Run source/evidence tests**

Run: `python -m pytest tests/knowledge_pipeline/test_source_and_evidence.py -q`

Expected: PASS with 10 candidates, 43 turns, and 86 speaker slots.

- [ ] **Step 6: Commit if Git is valid**

```powershell
git add knowledge_pipeline/source.py knowledge_pipeline/evidence.py knowledge_pipeline/cli.py tests/knowledge_pipeline/test_source_and_evidence.py
git commit -m "feat: preserve turns and resolve evidence spans"
```

### Task 3: Build Versioned Prompts And First-Pass Validation

**Files:**
- Create: `knowledge-extraction/prompts/turn_knowledge_extraction.md`
- Create: `knowledge-extraction/prompts/dialogue_reconciliation.md`
- Create: `knowledge-extraction/prompts/knowledge_keyword_extraction.md`
- Create: `knowledge-extraction/prompts/vocabulary_candidate_ranking.md`
- Create: `knowledge_pipeline/turn_pass.py`
- Modify: `knowledge_pipeline/cli.py`
- Create: `tests/knowledge_pipeline/test_turn_pass.py`

- [ ] **Step 1: Write failing tests for first-pass isolation and validation**

```python
def test_turn_payload_contains_only_one_turn(tmp_path):
paths = prepare_turn_payloads("data/gold-candidates/KE-test.json", tmp_path)
    payload = json.loads(paths[0].read_text(encoding="utf-8"))
    assert set(payload) == {"prompt_version", "candidate_id", "turn_index", "source", "user", "agent", "output_contract"}
    assert "previous_turn" not in payload
    assert "KE.txt" not in json.dumps(payload, ensure_ascii=False)


def test_turn_output_rejects_cross_candidate_id(sample_turn_output):
    sample_turn_output["knowledge"][0]["candidate_id"] = "OTHER"
    with pytest.raises(ValueError, match="candidate mismatch"):
        validate_turn_output(sample_turn_output, expected_candidate="CAND", expected_turn=1, user="用户文本", agent="Agent 文本")
```

- [ ] **Step 2: Run the tests and verify failure**

Run: `python -m pytest tests/knowledge_pipeline/test_turn_pass.py -q`

Expected: FAIL because prompt/payload and validation functions do not exist.

- [ ] **Step 3: Write all four complete prompts**

Each prompt must contain these exact sections: `Input Boundary`, `Output Contract`, `Completeness Checklist`, `Evidence Rules`, `Epistemic Rules`, `Forbidden Behavior`, and `Final Self-Check`.

The turn prompt must state:

```text
You see exactly one User message and its corresponding Agent output. Do not infer facts from earlier or later turns. First list explicit context completions; preserve unresolved references. Then emit atomic knowledge. Agent advice is agent_generated, not a real-world fact. A tool call is not a successful result; only an explicit tool result can be tool_observed. Return JSON only and use exact source quotations with occurrence_index.
```

The dialogue prompt must state that A-stage records are immutable and only `confirm/correct/supersede/conflict/add` operations are allowed. The keyword prompt must forbid vocabulary IDs. The ranking prompt must forbid IDs outside the supplied candidate whitelist.

- [ ] **Step 4: Implement first-pass payload and output validation**

`prepare_turn_payloads()` writes 43 isolated payloads and embeds the JSON Schema generated by `TurnPassOutput.model_json_schema()`.

`validate_turn_output()` must:

- enforce candidate/turn identity;
- enforce the `K_<candidate-slug>_<turn:03d>_<index:03d>` ID format and uniqueness;
- materialize every Evidence coordinate;
- verify `source_status=tool_observed` only when evidence quotes a `[工具结果]` span;
- reject any reference to other candidate IDs;
- verify every context completion and knowledge record has evidence;
- write validated output without modifying the raw subagent file.

Add `validate-turns` to `cli.py`; it loads the manifest, requires exactly one raw result per expected unit, validates all results, writes validated files, and exits nonzero without partial aggregation when any unit fails.

- [ ] **Step 5: Run prompt/turn validation tests**

Run: `python -m pytest tests/knowledge_pipeline/test_turn_pass.py -q`

Expected: PASS.

- [ ] **Step 6: Commit if Git is valid**

```powershell
git add knowledge-extraction/prompts knowledge_pipeline/turn_pass.py tests/knowledge_pipeline/test_turn_pass.py
git commit -m "feat: add model prompts and turn-pass validation"
```

### Task 4: Run First-Pass Extraction With Subagents

**Files:**
- Generate: `knowledge-extraction/inputs/turns/*.json`
- Generate: `knowledge-extraction/turn-pass/raw/*.json`
- Generate: `knowledge-extraction/turn-pass/validated/*.json`
- Generate: `knowledge-extraction/turn-pass/manifest.json`
- Modify: `knowledge-extraction/run.json`

- [ ] **Step 1: Prepare and verify the 43 isolated inputs**

Run: `python -m knowledge_pipeline.cli prepare-turns --input data/gold-candidates/KE-test.json --output-dir .`

Expected: `10 candidates, 43 turn payloads, 86 source messages` and no access to old extraction files.

- [ ] **Step 2: Dispatch exactly three extraction subagents**

The root agent prepares the prompt and dispatches fresh subagents over disjoint candidate sets:

```text
Agent A (15 turns): WILDCHAT-MGMT-CAND-001, WILDCHAT-MGMT-CAND-002,
                    WILDCHAT-LEARN-CAND-002, WILDCHAT-MGMT-CAND-003
Agent B (14 turns): WILDCHAT-LEARN-CAND-004, TASKMASTER2-CAND-001,
                    TAU-BENCH-CAND-001
Agent C (14 turns): BEAM-CAND-004, WILDCHAT-LEARN-CAND-001,
                    WILDCHAT-LEARN-CAND-003
```

Each subagent instruction names only its input payload files, `turn_knowledge_extraction.md`, `models.py`, and its output paths. It explicitly forbids reading any KEOL/custom KE output. The root agent must not fill missing semantic records itself; an invalid or missing file is returned to the responsible subagent.

- [ ] **Step 3: Validate every raw subagent output**

Run: `python -m knowledge_pipeline.cli validate-turns`

Expected: `43/43 outputs valid`, exact candidate/turn coverage, zero bad Evidence spans, zero cross-candidate IDs.

- [ ] **Step 4: Record provenance and immutable hashes**

Write each subagent task name, assigned candidates, prompt SHA-256, raw output SHA-256, validation result, and completion time to `knowledge-extraction/run.json`. Mark `turn-pass/validated` immutable by policy; later stages may read but never rewrite it.

- [ ] **Step 5: Commit generated first-pass artifacts if Git is valid**

```powershell
git add knowledge-extraction/inputs knowledge-extraction/turn-pass knowledge-extraction/run.json
git commit -m "data: add isolated first-pass knowledge extraction"
```

### Task 5: Validate And Run Dialogue Reconciliation

**Files:**
- Create: `knowledge_pipeline/dialogue_pass.py`
- Modify: `knowledge_pipeline/cli.py`
- Create: `tests/knowledge_pipeline/test_dialogue_pass.py`
- Generate: `knowledge-extraction/inputs/dialogues/*.json`
- Generate: `knowledge-extraction/dialogue-pass/raw/*.json`
- Generate: `knowledge-extraction/dialogue-pass/validated/*.json`

- [ ] **Step 1: Write failing reconciliation tests**

```python
def test_correct_requires_existing_target_and_replacement(valid_ledger):
    operation = {"operation_id": "R_CAND_001", "operation": "correct", "targets": ["K_missing"], "replacement": "D_CAND_001", "reason": "关系方向错误", "evidence": [], "confidence": 0.9}
    with pytest.raises(ValueError, match="unknown target"):
        validate_dialogue_output(valid_ledger, {"new_knowledge": [], "operations": [operation]})


def test_dialogue_input_contains_original_turn_pass_hashes(dialogue_payload):
    assert dialogue_payload["turn_pass_hashes"]
    assert len(dialogue_payload["turns"]) >= 3
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/knowledge_pipeline/test_dialogue_pass.py -q`

Expected: FAIL because dialogue validation does not exist.

- [ ] **Step 3: Implement dialogue payload preparation and append-only validation**

Prepare one payload per candidate containing the exact complete conversation, validated A-stage records, and their hashes.

Add `prepare-dialogues` and `validate-dialogues` CLI subcommands. `prepare-dialogues` refuses to run until all 43 turn outputs validate; `validate-dialogues` refuses partial success if any of the ten candidate files is missing or invalid.

Validation rules:

- operation IDs and `D_<candidate-slug>_<index:03d>` new knowledge IDs are unique;
- all targets resolve inside the same candidate;
- `correct` has exactly one replacement and it resolves to new knowledge;
- `supersede` has targets and no required replacement;
- `conflict` has at least two targets;
- `add` references one new knowledge record and no old target is silently removed;
- every new knowledge Evidence resolves against an exact conversation turn/message;
- hashes prove A-stage files were not altered.

- [ ] **Step 4: Run dialogue validation tests**

Run: `python -m pytest tests/knowledge_pipeline/test_dialogue_pass.py -q`

Expected: PASS.

- [ ] **Step 5: Prepare the ten complete-dialogue payloads**

Run: `python -m knowledge_pipeline.cli prepare-dialogues`

Expected: `10 dialogue payloads prepared`, each containing the full original candidate conversation, all validated first-pass records for that candidate, and immutable first-pass hashes.

- [ ] **Step 6: Dispatch three fresh reconciliation subagents**

Use the same balanced candidate partitions as Task 4, but do not reuse the first-pass subagent tasks. Each agent reads only its dialogue payloads and `dialogue_reconciliation.md` and writes one raw JSON file per candidate.

- [ ] **Step 7: Validate all ten dialogue outputs**

Run: `python -m knowledge_pipeline.cli validate-dialogues`

Expected: `10/10 dialogue outputs valid`, zero unknown references, and all 43 first-pass file hashes unchanged.

- [ ] **Step 8: Commit if Git is valid**

```powershell
git add knowledge_pipeline/dialogue_pass.py tests/knowledge_pipeline/test_dialogue_pass.py knowledge-extraction/inputs/dialogues knowledge-extraction/dialogue-pass
git commit -m "feat: add append-only dialogue reconciliation"
```

### Task 6: Project The Deterministic Active Knowledge Ledger

**Files:**
- Create: `knowledge_pipeline/projector.py`
- Modify: `knowledge_pipeline/cli.py`
- Create: `tests/knowledge_pipeline/test_projector.py`
- Generate: `knowledge-extraction/final-knowledge.json`

- [ ] **Step 1: Write failing projection tests**

```python
def test_corrected_record_is_retained_but_not_active(sample_ledger):
    view = project_final_knowledge(sample_ledger)
    assert view.by_id["K_old"].status == "corrected"
    assert view.by_id["D_new"].status == "active"
    assert "K_old" not in view.active_ids


def test_conflicting_records_both_remain_active(conflict_ledger):
    view = project_final_knowledge(conflict_ledger)
    assert {"K_a", "K_b"} <= set(view.active_ids)
    assert view.by_id["K_a"].conflicts_with == ["K_b"]
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/knowledge_pipeline/test_projector.py -q`

Expected: FAIL because the projector does not exist.

- [ ] **Step 3: Implement pure ledger projection**

`project_final_knowledge()` takes validated A-stage records and B-stage operations and returns a stable sort by candidate, source turn, and ID. It never calls a model and never mutates input files. Replaying it twice over identical hashes must produce byte-identical canonical JSON.

Add the `project` CLI subcommand; serialize with sorted keys, UTF-8, stable list ordering, and a trailing newline before hashing.

Statuses are `active`, `corrected`, `superseded`, or `active_conflict`. Confirmed records remain active and collect confirming operation IDs. Equivalent records retain all Evidence and are linked by an `equivalence_group` without destructive deduplication.

- [ ] **Step 4: Run projection tests and generate the final view**

Run: `python -m pytest tests/knowledge_pipeline/test_projector.py -q`

Expected: PASS.

Run: `python -m knowledge_pipeline.cli project`

Expected: writes `final-knowledge.json` and reports active/corrected/superseded/conflict counts.

- [ ] **Step 5: Verify deterministic replay**

Run the project command twice and compare SHA-256 values in `run.json`.

Expected: identical hash both times.

- [ ] **Step 6: Commit if Git is valid**

```powershell
git add knowledge_pipeline/projector.py tests/knowledge_pipeline/test_projector.py knowledge-extraction/final-knowledge.json
git commit -m "feat: project active knowledge ledger"
```

### Task 7: Extract Typed Keywords With Fresh Subagents

**Files:**
- Create: `knowledge_pipeline/keywords.py`
- Modify: `knowledge_pipeline/cli.py`
- Create: `tests/knowledge_pipeline/test_keywords.py`
- Generate: `knowledge-extraction/inputs/keywords/*.json`
- Generate: `knowledge-extraction/keyword-pass/raw/*.json`
- Generate: `knowledge-extraction/keyword-pass.json`

- [ ] **Step 1: Write failing keyword validation tests**

```python
def test_each_active_knowledge_has_keywords_or_reason(active_knowledge, keyword_output):
    validate_keyword_coverage(active_knowledge, keyword_output)
    covered = {item.knowledge_id for item in keyword_output.items}
    assert covered == set(active_knowledge.active_ids)


def test_keyword_stage_rejects_vocabulary_ids(keyword_output):
    keyword_output.items[0].keywords[0]["id"] = "schema:Event"
    with pytest.raises(ValidationError):
        KeywordPassOutput.model_validate(keyword_output)
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/knowledge_pipeline/test_keywords.py -q`

Expected: FAIL because keyword validation does not exist.

- [ ] **Step 3: Implement keyword payload and coverage validation**

Create one payload per candidate containing only active/final knowledge and its evidence. Output for each knowledge has either a non-empty `keywords` array or a non-empty `no_keyword_reason`. A keyword includes `surface`, `normalized_zh`, `query_lemma`, `keyword_type`, `semantic_role`, `source_field`, and `translation_confidence`; it contains no vocabulary ID.

Add `prepare-keywords` and `validate-keywords` CLI subcommands. Preparation requires a valid final ledger hash; validation requires exact active-knowledge coverage.

- [ ] **Step 4: Run keyword unit tests**

Run: `python -m pytest tests/knowledge_pipeline/test_keywords.py -q`

Expected: PASS.

- [ ] **Step 5: Prepare keyword payloads**

Run: `python -m knowledge_pipeline.cli prepare-keywords`

Expected: one payload per candidate with active knowledge only; the union of payload knowledge IDs equals the final active set.

- [ ] **Step 6: Dispatch three fresh keyword subagents**

Use the same candidate partitions. Each subagent reads only final active-knowledge payloads and `knowledge_keyword_extraction.md`. The root agent does not add missing keywords; failures go back to the responsible subagent.

- [ ] **Step 7: Validate and aggregate keyword outputs**

Run: `python -m knowledge_pipeline.cli validate-keywords`

Expected: every active knowledge ID covered exactly once, zero vocabulary IDs, all Chinese surfaces traceable to the statement or structured fields, and all English query lemmas non-empty.

- [ ] **Step 8: Commit if Git is valid**

```powershell
git add knowledge_pipeline/keywords.py knowledge_pipeline/cli.py tests/knowledge_pipeline/test_keywords.py knowledge-extraction/inputs/keywords knowledge-extraction/keyword-pass knowledge-extraction/keyword-pass.json
git commit -m "data: add typed knowledge keywords"
```

### Task 8: Pin And Query schema.org And WordNet

**Files:**
- Create: `knowledge_pipeline/vocabulary.py`
- Modify: `knowledge_pipeline/cli.py`
- Create: `tests/knowledge_pipeline/test_vocabulary.py`
- Generate: `knowledge-extraction/vocabularies/schemaorg-current-https.jsonld`
- Generate: `knowledge-extraction/vocabularies/nltk_data/corpora/wordnet*`
- Generate: `knowledge-extraction/vocabularies/manifest.json`
- Generate: `knowledge-extraction/vocabulary-candidates.json`

- [ ] **Step 1: Write failing fixture-based vocabulary tests**

```python
def test_schema_candidates_are_real_graph_ids(schema_fixture):
    index = SchemaOrgIndex.from_jsonld(schema_fixture)
    candidates = index.search("event", limit=5)
    assert candidates[0].id == "https://schema.org/Event"
    assert all(index.contains(item.id) for item in candidates)


def test_wordnet_candidates_round_trip(wordnet_index):
    candidates = wordnet_index.search("vacation", limit=5)
    assert candidates
    assert all(wordnet_index.contains(item.id) for item in candidates)
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/knowledge_pipeline/test_vocabulary.py -q`

Expected: FAIL because vocabulary indexes do not exist.

- [ ] **Step 3: Implement schema.org JSON-LD indexing**

Parse `@graph`, index `rdfs:label`, `rdfs:comment`, local ID, and `@type`, and return at most five deterministic candidates ranked by exact normalized label, token overlap, then ID. Keep actual URI, label, description, and term kind.

- [ ] **Step 4: Implement WordNet lookup and ID validation**

Add `knowledge-extraction/vocabularies/nltk_data` to `nltk.data.path`. Query `wordnet.synsets(query_lemma.replace(" ", "_"))`, return `synset.name()` as the stable ID, lemma names, POS, definition, and examples. Validate by calling `wordnet.synset(candidate_id)`.

Add `bootstrap-vocabularies` and `query-vocabularies` CLI subcommands. The query command requires valid keyword-pass and vocabulary-manifest hashes.

- [ ] **Step 5: Implement the explicit vocabulary bootstrap command**

Run: `python -m knowledge_pipeline.cli bootstrap-vocabularies`

The command downloads schema.org from `https://schema.org/version/latest/schemaorg-current-https.jsonld` and NLTK packages `wordnet` plus `omw-1.4` into the workspace vocabulary directory. It records source URLs, retrieval time, detected version, byte count, and SHA-256 in `manifest.json`. Network failure must stop this stage; it must not fabricate an empty vocabulary.

Expected: both vocabulary snapshots exist and manifest hashes verify.

- [ ] **Step 6: Query candidates for every keyword**

Run: `python -m knowledge_pipeline.cli query-vocabularies`

Expected: each keyword has zero to five candidates per applicable vocabulary; concrete values remain local; every returned ID round-trips through its index.

- [ ] **Step 7: Run vocabulary tests**

Run: `python -m pytest tests/knowledge_pipeline/test_vocabulary.py -q`

Expected: PASS using small committed fixtures and the pinned full snapshots when present.

- [ ] **Step 8: Commit code, fixtures, and manifest if Git is valid**

Do not commit large NLTK/schema snapshots unless the user explicitly wants vendoring. Commit the manifest and code:

```powershell
git add knowledge_pipeline/vocabulary.py tests/knowledge_pipeline/test_vocabulary.py knowledge-extraction/vocabularies/manifest.json knowledge-extraction/vocabulary-candidates.json
git commit -m "feat: query pinned schema and WordNet vocabularies"
```

### Task 9: Rank Only Real Vocabulary Candidates

**Files:**
- Create: `knowledge_pipeline/ranking.py`
- Modify: `knowledge_pipeline/cli.py`
- Create: `tests/knowledge_pipeline/test_ranking.py`
- Generate: `knowledge-extraction/inputs/ranking/*.json`
- Generate: `knowledge-extraction/ranking-pass/raw/*.json`
- Generate: `knowledge-extraction/vocabulary-alignment.json`

- [ ] **Step 1: Write failing whitelist tests**

```python
def test_ranking_rejects_invented_candidate_id(candidate_payload):
    ranking = {"keyword_id": candidate_payload["keyword_id"], "ranked": [{"id": "vacation.n.999", "mapping": "exact", "score": 0.9, "match_basis": "invented"}]}
    with pytest.raises(ValueError, match="outside candidate whitelist"):
        validate_ranking(candidate_payload, ranking)


def test_selected_candidate_remains_null(valid_ranking):
    result = materialize_alignment(valid_ranking)
    assert result.selected_candidate is None
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/knowledge_pipeline/test_ranking.py -q`

Expected: FAIL because ranking validation does not exist.

- [ ] **Step 3: Implement ranking payloads and whitelist validation**

Each payload contains one knowledge statement, one keyword, and the actual candidates returned by Task 8. Ranking output may reject all candidates or assign `exact/narrow/broad/related`, score, and short match basis. It may not add IDs, alter labels, or set `selected_candidate`.

Add `prepare-rankings` and `validate-rankings` CLI subcommands. Validation reloads the pinned vocabulary indexes instead of trusting IDs copied into the payload.

- [ ] **Step 4: Run ranking unit tests**

Run: `python -m pytest tests/knowledge_pipeline/test_ranking.py -q`

Expected: PASS.

- [ ] **Step 5: Prepare ranking payloads**

Run: `python -m knowledge_pipeline.cli prepare-rankings`

Expected: every keyword with at least one retrieved candidate has exactly one whitelist-constrained ranking payload; zero-candidate keywords are recorded without model dispatch.

- [ ] **Step 6: Dispatch three fresh ranking subagents**

Partition payloads by candidate so knowledge context stays local. Each agent reads only its ranking payloads and `vocabulary_candidate_ranking.md`. The root agent never supplies semantic rankings.

- [ ] **Step 7: Validate and aggregate alignments**

Run: `python -m knowledge_pipeline.cli validate-rankings`

Expected: zero IDs outside retrieval whitelists, all scores in range, all mapped IDs still valid in pinned vocabularies, and `selected_candidate=null` throughout.

- [ ] **Step 8: Commit if Git is valid**

```powershell
git add knowledge_pipeline/ranking.py tests/knowledge_pipeline/test_ranking.py knowledge-extraction/inputs/ranking knowledge-extraction/ranking-pass knowledge-extraction/vocabulary-alignment.json
git commit -m "data: rank verified vocabulary candidates"
```

### Task 10: Export Review Views And Verify End To End

**Files:**
- Create: `knowledge_pipeline/export.py`
- Create: `knowledge_pipeline/verify.py`
- Modify: `knowledge_pipeline/cli.py`
- Create: `tests/knowledge_pipeline/test_export_and_verify.py`
- Generate: `Knowledge.txt`
- Generate: `knowledge-extraction-report.md`
- Update: `knowledge-extraction/run.json`
- Update: `安排.md`

- [ ] **Step 1: Write failing end-to-end tests**

```python
def test_review_text_contains_every_candidate(final_artifacts):
    text = render_knowledge_text(final_artifacts)
    assert text.count("对话id:") == 10
    assert "来源状态:" in text
    assert "证据:" in text
    assert "校正链:" in text


def test_verify_rejects_changed_first_pass_hash(run_fixture):
    run_fixture["turn_pass"][0]["validated_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="immutable first-pass hash"):
        verify_run(run_fixture)
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/knowledge_pipeline/test_export_and_verify.py -q`

Expected: FAIL because export/verification functions do not exist.

- [ ] **Step 3: Implement review exports**

`Knowledge.txt` is grouped by candidate then turn. For each active knowledge, print statement, source status, derivation, modality, Evidence quotes, keywords, candidate mappings, and reconciliation chain. Corrected/superseded knowledge appears in a separate history block, not mixed with active facts.

`knowledge-extraction-report.md` includes counts for turn knowledge, dialogue additions, confirm/correct/supersede/conflict operations, `source_status`, `derivation`, `modality`, unresolved references, Evidence failures, keyword coverage, schema.org hit rate, WordNet hit rate, rejected candidates, and subagent provenance.

- [ ] **Step 4: Implement full acceptance verification**

Verify all twelve checks from the design document, plus prompt hashes, vocabulary snapshot hashes, raw/validated output separation, and byte-identical final projection replay. Return nonzero on any failure and print each failed invariant with its file and ID.

- [ ] **Step 5: Run the complete test suite**

Run: `python -m pytest tests/knowledge_pipeline -q`

Expected: all tests pass with zero failures.

- [ ] **Step 6: Generate final views and run verification**

Run: `python -m knowledge_pipeline.cli export`

Run: `python -m knowledge_pipeline.cli verify`

Expected summary:

```text
candidates=10
turns=43
speaker_slots=86
missing_turn_outputs=0
bad_evidence_spans=0
cross_candidate_refs=0
broken_reconciliation_refs=0
missing_keyword_records=0
invented_vocabulary_ids=0
immutable_first_pass=true
deterministic_projection=true
```

- [ ] **Step 7: Update workspace status without reviving KEOL**

Append a dated status paragraph to `安排.md` stating that KEOL extraction is paused, this knowledge-first experiment is the active Wave 0 extraction method, semantic stages were performed by subagents, and outputs remain gold candidates pending human review. Do not edit the invalidated `AGENTS.md` instructions.

- [ ] **Step 8: Commit if Git is valid**

```powershell
git add knowledge_pipeline knowledge-extraction Knowledge.txt knowledge-extraction-report.md tests/knowledge_pipeline 安排.md
git commit -m "feat: complete knowledge-first extraction experiment"
```

## Final Execution Gate

Before claiming completion, independently check:

1. the remote/source vocabulary IDs round-trip through the pinned snapshots;
2. the root agent did not author any semantic extraction or ranking record;
3. all subagent assignments and prompt hashes are recorded;
4. old KEOL/custom KE outputs were never used as model inputs;
5. all tests and `knowledge_pipeline.cli verify` pass from a fresh process;
6. known quality limitations and unresolved knowledge remain visible in the report.
