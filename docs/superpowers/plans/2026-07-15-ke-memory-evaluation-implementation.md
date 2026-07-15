# BEAM Evaluation and Reporting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the frozen five-system BEAM experiment, judge all 300 answers independently, compute evidence/answer/cost/latency metrics, and publish a traceable report without silently dropping failures.

**Architecture:** Evaluation is a strict consumer of the core `MemorySystem` protocol. A dataset normalizer freezes 60 questions and machine-resolvable gold sources before any system runs; the experiment runner writes identical exchanges, retrieves normalized evidence, applies one common token packer and answer model, then sends anonymous answers to an independent Judge. Immutable artifacts feed deterministic metrics and Markdown/JSON/CSV reports before the final Git snapshot.

**Tech Stack:** Core and baseline plan stack, Pydantic, Python stdlib csv, Jinja2, NumPy, pytest, pytest-asyncio.

**Design Spec:** `docs/superpowers/specs/2026-07-15-ke-memory-demo-design.md` at approved commit `90a9575f71740b399405e8c568090c282c5290b7`. This is plan 3 of 3 and starts only after both prior verification gates.

## Global Constraints

- Complete `2026-07-15-ke-memory-core-implementation.md` and `2026-07-15-ke-memory-baselines-implementation.md` first.
- Systems are exactly `ke-memory`, `mem0`, `graphiti`, `hindsight`, and `mempalace`; do not add internal ablation systems.
- Dataset is exactly BEAM 100K directories `4`, `15`, and `17`: 13 sessions, 385 exchanges, 60 questions, 10 categories, 2 questions/category/conversation.
- Never ingest probing questions, ideal answers, rubrics, source labels, or Judge output into any memory system.
- Every system receives the same source-ordered exchanges and a fresh isolated conversation namespace.
- Every answer uses the same `gpt-5.4` endpoint, answer prompt, 8192-token evidence budget, and 1024-token output maximum.
- Judge uses only `deepseek-v4-pro` at the official endpoint, one anonymous answer per call, with the BEAM question, normalized ideal answer, and rubric.
- All BEAM rubric items are mandatory. Judge output is Pydantic-validated; a missing/invalid result makes the experiment incomplete.
- Evidence source IDs come only from public adapter output/receipts and pre-registered gold mapping. Never infer attribution from answer similarity.
- Questions without uniquely resolvable gold sources remain in answer scoring but are excluded from source-recall denominators and unique-success classification.
- A failed baseline or missing answer/Judge result is not zero. It blocks comparative ranking until rerun.
- Report all ten categories and emphasize contradiction resolution, event ordering, knowledge update, multi-session reasoning, summarization, and temporal reasoning.
- Use 10,000 paired question-level bootstrap samples with a seed derived from the experiment manifest hash.
- Record tokens and latency separately for ingest, internal processing, retrieval, common answer, and Judge. Cost requires provider-reported cost or an untracked, preflight-validated pricing file.
- Final state snapshot stage is `evaluation-complete`; SQLite and complete ES vocabulary remain excluded.
- Do not reference `/public/home/wwb/memory` or any fusion-memory project.

---

### Task 1: Probe Question and Gold-Source Normalization

**Files:**
- Create: `src/ke_memory_demo/evaluation/__init__.py`
- Create: `src/ke_memory_demo/evaluation/models.py`
- Create: `src/ke_memory_demo/evaluation/questions.py`
- Create: `src/ke_memory_demo/evaluation/gold_sources.py`
- Create: `tests/unit/evaluation/test_questions.py`
- Create: `tests/unit/evaluation/test_gold_sources.py`
- Create: `tests/integration/test_beam_questions.py`

**Interfaces:**
- Consumes: normalized BEAM conversations and source catalogs from the core plan.
- Produces: `ProbeQuestion`, `GoldSourceMapping`, `load_probe_questions()`, and `build_gold_source_mapping()`.

- [ ] **Step 1: Write failing answer-priority and source-resolution tests**

```python
def test_reference_answer_priority_is_stable():
    raw = {"question": "q", "ideal_answer": "a1", "ideal_response": "a2", "answer": "a3", "rubric": ["r"]}
    normalized = normalize_question(raw, conversation_id="c", category="knowledge_update", ordinal=0)
    assert normalized.ideal_answer == "a1"
    assert normalized.original_answer_field == "ideal_answer"


def test_only_unique_structured_or_regex_source_is_accepted(source_catalog):
    raw = {"source_chat_ids": [4, 8], "conversation_references": ["Session 12"]}
    mapping = build_gold_source_mapping(raw, source_catalog)
    assert mapping.status == "mapped"
    assert mapping.source_exchange_ids == source_catalog.exchange_ids_for_source_numbers({4, 8, 12})


def test_ambiguous_reference_is_excluded_not_guessed(ambiguous_catalog):
    mapping = build_gold_source_mapping({"conversation_references": ["Session 4"]}, ambiguous_catalog)
    assert mapping.status == "unmappable"
    assert mapping.source_exchange_ids == []
```

- [ ] **Step 2: Run tests and verify missing evaluation models**

Run: `uv run pytest tests/unit/evaluation/test_questions.py tests/unit/evaluation/test_gold_sources.py tests/integration/test_beam_questions.py -v`

Expected: FAIL during import.

- [ ] **Step 3: Implement normalized question models and parser**

```python
from enum import StrEnum


class QuestionCategory(StrEnum):
    ABSTENTION = "abstention"
    CONTRADICTION_RESOLUTION = "contradiction_resolution"
    EVENT_ORDERING = "event_ordering"
    INFORMATION_EXTRACTION = "information_extraction"
    INSTRUCTION_FOLLOWING = "instruction_following"
    KNOWLEDGE_UPDATE = "knowledge_update"
    MULTI_SESSION_REASONING = "multi_session_reasoning"
    PREFERENCE_FOLLOWING = "preference_following"
    SUMMARIZATION = "summarization"
    TEMPORAL_REASONING = "temporal_reasoning"


class ProbeQuestion(BaseModel, frozen=True):
    id: str
    conversation_id: str
    category: QuestionCategory
    ordinal: int
    question: str
    ideal_answer: str
    original_answer_field: Literal["ideal_answer", "ideal_response", "answer"]
    rubric: tuple[str, ...]
    raw_metadata: dict[str, JsonValue]
```

Select the first nonempty answer in the exact priority `ideal_answer`, `ideal_response`, `answer`. Reject missing question, empty rubric, unknown category, duplicate deterministic ID, or more/less than two questions per category per conversation.

- [ ] **Step 4: Implement source parsing without heuristics**

Recursively collect integer values from explicit source fields such as `source_chat_ids`. Parse free-text references only with case-insensitive `\b(?:chat_id|Session)\s*:?\s*(\d+)\b`. Resolve each number through the frozen source catalog; require exactly one Exchange per number. Save mapping status, source field paths, matched tokens, exchange IDs, and an exclusion reason. Do not use LLMs for gold mapping.

- [ ] **Step 5: Run real-archive integration checks**

Run: `uv run pytest tests/unit/evaluation/test_questions.py tests/unit/evaluation/test_gold_sources.py tests/integration/test_beam_questions.py -v`

Expected: all tests pass; output confirms 60 questions, ten categories, six questions/category overall, and reports the exact mapped/unmappable source coverage count.

- [ ] **Step 6: Commit**

```bash
git add src/ke_memory_demo/evaluation tests/unit/evaluation/test_questions.py tests/unit/evaluation/test_gold_sources.py tests/integration/test_beam_questions.py
git commit -m "feat: freeze BEAM questions and gold sources"
```

### Task 2: Experiment Manifest, Pricing, and Preflight

**Files:**
- Create: `src/ke_memory_demo/evaluation/manifest.py`
- Create: `src/ke_memory_demo/evaluation/pricing.py`
- Create: `src/ke_memory_demo/evaluation/preflight.py`
- Create: `config/pricing.local.toml.example`
- Create: `tests/unit/evaluation/test_manifest.py`
- Create: `tests/unit/evaluation/test_pricing.py`
- Create: `tests/unit/evaluation/test_preflight.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: dataset manifest, system identities, model/ES/embedding settings, prompt/schema hashes, and baseline environment manifests.
- Produces: immutable `ExperimentManifest`, `PricingResolver`, and `EvaluationPreflight.run() -> PreflightReport`.

- [ ] **Step 1: Write failing manifest and pricing tests**

```python
def test_manifest_hash_is_order_independent_for_system_map():
    left = experiment_manifest(systems={"mem0": identity("mem0"), "graphiti": identity("graphiti")})
    right = experiment_manifest(systems={"graphiti": identity("graphiti"), "mem0": identity("mem0")})
    assert left.content_hash == right.content_hash


def test_pricing_requires_provider_cost_or_private_rates():
    resolver = PricingResolver(private_rates=None)
    with pytest.raises(PricingUnavailableError):
        resolver.cost(UsageRecord(model="gpt-5.4", input_tokens=10, output_tokens=5, provider_cost=None))
```

- [ ] **Step 2: Run tests and verify missing preflight code**

Run: `uv run pytest tests/unit/evaluation/test_manifest.py tests/unit/evaluation/test_pricing.py tests/unit/evaluation/test_preflight.py -v`

Expected: FAIL during import.

- [ ] **Step 3: Implement immutable experiment manifest**

Include code commit, design/spec hash, all three plan hashes, BEAM hash/IDs/counts, question/gold mapping hash, prompt/schema/config hashes, work/Judge model IDs and endpoints, embedding revision/fingerprint, ES identity, all five system identities, baseline tree/environment fingerprints, evidence/output budgets, retry rules, bootstrap count, and run creation time. Derive manifest content hash from canonical JSON excluding creation time and content hash itself.

- [ ] **Step 4: Implement private pricing resolution**

The resolver first uses provider-returned cost. Otherwise load ignored `config/pricing.local.toml`, keyed by endpoint + model with nonnegative input/output price per million tokens and currency. Formal preflight fails if any model used by any system lacks provider cost support and lacks a private rate. Save rate hashes and currency, never provider billing credentials.

```toml
# config/pricing.local.toml.example
formal_run_enabled = false
currency = "USD"

[models."https://api.penguinsaichat.dpdns.org/v1|gpt-5.4"]
input_per_million = 0.0
output_per_million = 0.0

[models."https://api.deepseek.com/v1|deepseek-v4-pro"]
input_per_million = 0.0
output_per_million = 0.0
```

The example is structurally valid but cannot authorize a formal run because `formal_run_enabled` is false. The ignored local file must set it true and contain the current account rates, unless every relevant provider response supplies cost directly.

- [ ] **Step 5: Implement preflight gates**

Require clean code commit, exact dataset counts, complete question/gold manifest, local embedding fingerprint, unchanged ES identity, both model structured-output probes, five healthy/fresh memory systems, baseline source/env identities, writable state repo, sufficient disk, pricing availability, and absence of secrets in tracked files. Return all failures together; perform no memory ingestion.

- [ ] **Step 6: Run tests and commit**

Run: `uv run pytest tests/unit/evaluation/test_manifest.py tests/unit/evaluation/test_pricing.py tests/unit/evaluation/test_preflight.py -v`

Expected: all tests pass, including a report with multiple simultaneous failures.

```bash
git add src/ke_memory_demo/evaluation/manifest.py src/ke_memory_demo/evaluation/pricing.py src/ke_memory_demo/evaluation/preflight.py config/pricing.local.toml.example tests/unit/evaluation/test_manifest.py tests/unit/evaluation/test_pricing.py tests/unit/evaluation/test_preflight.py .gitignore
git commit -m "feat: preflight reproducible memory experiments"
```

### Task 3: Five-System Experiment Runner and Common Answer Generation

**Files:**
- Create: `src/ke_memory_demo/evaluation/runner.py`
- Create: `src/ke_memory_demo/evaluation/checkpoints.py`
- Create: `tests/unit/evaluation/test_runner.py`
- Create: `tests/integration/test_experiment_runner.py`
- Modify: `src/ke_memory_demo/cli.py`

**Interfaces:**
- Consumes: five `MemorySystem` instances, questions, common `EvidenceFusion`, `AnswerService`, artifacts, snapshots, and preflight.
- Produces: `ExperimentRunner.ingest_all()`, `ExperimentRunner.answer_all()`, `SystemAnswer`, and resumable question-level checkpoints.

- [ ] **Step 1: Write failing fairness and completeness tests**

```python
@pytest.mark.asyncio
async def test_all_systems_receive_identical_exchange_hashes(fake_systems):
    runner = ExperimentRunner(fake_systems, fake_services())
    await runner.ingest_all(conversations_fixture())
    expected = [exchange.content_hash for exchange in conversations_fixture()[0].exchanges]
    assert all(system.ingested_hashes == expected for system in fake_systems)


@pytest.mark.asyncio
async def test_answer_failure_marks_incomplete_without_synthetic_zero(fake_systems):
    fake_systems[2].fail_retrieve(question_id="q2")
    result = await ExperimentRunner(fake_systems, fake_services()).answer_all(questions_fixture())
    assert result.status == "incomplete"
    assert "q2" not in result.answers_by_system[fake_systems[2].system_id]
    assert result.synthetic_scores_created == 0
```

- [ ] **Step 2: Run tests and verify missing runner**

Run: `uv run pytest tests/unit/evaluation/test_runner.py tests/integration/test_experiment_runner.py -v`

Expected: FAIL during import.

- [ ] **Step 3: Implement strict ingestion orchestration**

For each conversation create five fresh scopes, then give every system the exact same immutable Exchange sequence. Systems may run one after another to avoid resource contention, but no system sees another system's output. Persist ingest receipt after every exchange, require public readiness, compare per-system source hash sequences, and abort questions for a conversation when any system is not ready.

- [ ] **Step 4: Implement common retrieval and answer path**

For each of 60 questions and five systems: call `retrieve(question, 8192)`, pass normalized evidence through the same token counter/packer, record the exact evidence artifact, call the common `AnswerService` once, and save answer, citations, usage, latency, request ID, system ID, question ID, manifest hash, and evidence hash. Do not include ideal answer, rubric, category, gold sources, or system comparison in retrieval/answer prompts.

- [ ] **Step 5: Implement safe resume**

Skip an answer only when a checkpoint has matching manifest hash, system identity, question ID, evidence artifact hash, answer prompt hash, actual model ID, and a valid `SystemAnswer`. Any mismatch invalidates that checkpoint and recomputes the answer. Never merge checkpoints from two manifests.

- [ ] **Step 6: Run tests and commit**

Run: `uv run pytest tests/unit/evaluation/test_runner.py tests/integration/test_experiment_runner.py -v`

Expected: all tests pass; a complete fixture yields exactly `systems × questions` answers.

```bash
git add src/ke_memory_demo/evaluation/runner.py src/ke_memory_demo/evaluation/checkpoints.py src/ke_memory_demo/cli.py tests/unit/evaluation/test_runner.py tests/integration/test_experiment_runner.py
git commit -m "feat: run fair five-system memory experiments"
```

### Task 4: Independent DeepSeek Judge

**Files:**
- Create: `prompts/judge/system.md`
- Create: `src/ke_memory_demo/evaluation/judge.py`
- Create: `tests/unit/evaluation/test_judge.py`
- Create: `tests/integration/test_judge_batch.py`

**Interfaces:**
- Consumes: `ProbeQuestion`, `SystemAnswer`, Judge model settings, structured client, redacted traces, and checkpoints.
- Produces: `JudgeResult`, `JudgeService.judge()`, and `JudgeBatch.run()`.

- [ ] **Step 1: Write failing blinded-prompt and schema tests**

```python
@pytest.mark.asyncio
async def test_judge_prompt_contains_no_system_identity(fake_judge_model):
    service = JudgeService(fake_judge_model.client)
    await service.judge(probe_question(), system_answer(system_id="graphiti"))
    payload = fake_judge_model.last_user_payload()
    assert "graphiti" not in payload.lower()
    assert set(payload) == {"question", "ideal_answer", "rubric", "candidate_answer"}


def test_answer_score_is_derived_not_trusted_from_model():
    raw = judge_output([True, False, True], model_claimed_score=1.0)
    result = JudgeResult.from_model_output(raw)
    assert result.answer_score == pytest.approx(2 / 3)
```

- [ ] **Step 2: Run tests and verify missing Judge service**

Run: `uv run pytest tests/unit/evaluation/test_judge.py tests/integration/test_judge_batch.py -v`

Expected: FAIL during import.

- [ ] **Step 3: Implement exact Judge schema and prompt**

```python
class RubricJudgement(BaseModel, frozen=True):
    rubric: str
    satisfied: bool
    reason: str


class JudgeModelOutput(BaseModel, frozen=True):
    rubric_items: tuple[RubricJudgement, ...]
    factual_error: bool
    unsupported_claim: bool
    abstention_correct: bool | None
    short_rationale: str
```

Require one output item per rubric in the same order and exact rubric text. Compute `answer_score = satisfied_count / rubric_count` in code. Send no memory-system ID, evidence, retrieval score, KE, category, or competing answer. Use one answer per request. Apply the structured retry policy from core; no alternative Judge model is allowed.

- [ ] **Step 4: Implement batch completeness and resume**

Judge all 300 answers. A checkpoint is reusable only when Judge model/endpoint, prompt hash, question hash, answer hash, and manifest hash match. Missing/invalid Judge output sets experiment status incomplete and never creates a score.

- [ ] **Step 5: Run tests and commit**

Run: `uv run pytest tests/unit/evaluation/test_judge.py tests/integration/test_judge_batch.py -v`

Expected: all tests pass; fixture count equals answer count and labels remain blinded.

```bash
git add prompts/judge src/ke_memory_demo/evaluation/judge.py tests/unit/evaluation/test_judge.py tests/integration/test_judge_batch.py
git commit -m "feat: add independent blinded answer judge"
```

### Task 5: Metrics, Evidence Recall, Unique Cases, and Bootstrap

**Files:**
- Create: `src/ke_memory_demo/evaluation/metrics.py`
- Create: `src/ke_memory_demo/evaluation/bootstrap.py`
- Create: `src/ke_memory_demo/evaluation/cases.py`
- Create: `tests/unit/evaluation/test_metrics.py`
- Create: `tests/unit/evaluation/test_bootstrap.py`
- Create: `tests/unit/evaluation/test_cases.py`

**Interfaces:**
- Consumes: questions, gold mappings, evidence artifacts, answers, Judge results, usage, latency, and pricing.
- Produces: `QuestionMetrics`, `AggregateMetrics`, `BootstrapInterval`, `UniqueSuccessCase`, and `compute_experiment_metrics()`.

- [ ] **Step 1: Write failing denominator, unique-case, and deterministic-bootstrap tests**

```python
def test_unmappable_gold_is_excluded_only_from_source_metrics():
    metrics = compute_question_metrics(unmappable_question_fixture())
    assert metrics.answer_score == 1.0
    assert metrics.source_evidence_recall is None
    assert metrics.complete_evidence is None


def test_unique_success_requires_all_rubrics_and_all_gold_sources():
    case = classify_case(unique_case_fixture())
    assert case.kind == "ke_unique_success"
    broken = unique_case_fixture(ke_source_recall=0.5)
    assert classify_case(broken).kind != "ke_unique_success"


def test_bootstrap_is_reproducible_from_manifest_hash():
    left = paired_bootstrap(differences_fixture(), samples=10_000, seed_material="a" * 64)
    right = paired_bootstrap(differences_fixture(), samples=10_000, seed_material="a" * 64)
    assert left == right
```

- [ ] **Step 2: Run tests and verify missing metrics**

Run: `uv run pytest tests/unit/evaluation/test_metrics.py tests/unit/evaluation/test_bootstrap.py tests/unit/evaluation/test_cases.py -v`

Expected: FAIL during import.

- [ ] **Step 3: Implement question and aggregate metrics**

Compute rubric score, factual/unsupported flags, abstention correctness, source evidence recall, complete evidence, retrieved token count, and stage-specific tokens/latency/cost. Aggregate overall, by system, conversation, all ten categories, and the six emphasized categories. Always emit denominator counts and mapped-gold coverage. Refuse aggregation if any expected answer/Judge is missing.

- [ ] **Step 4: Implement paired comparisons and case rules**

For every baseline compute per-question KE-minus-baseline score and evidence difference, then 10,000 paired bootstrap resamples. `ke_unique_success` requires all KE rubric items satisfied, source recall 1.0, and every baseline missing at least one rubric or gold source. `ke_comparative_advantage` requires KE score strictly above every baseline and source recall at least the best baseline. Unmappable-source questions cannot be unique successes.

- [ ] **Step 5: Run tests and commit**

Run: `uv run pytest tests/unit/evaluation/test_metrics.py tests/unit/evaluation/test_bootstrap.py tests/unit/evaluation/test_cases.py -v`

Expected: all tests pass with deterministic intervals and denominators.

```bash
git add src/ke_memory_demo/evaluation/metrics.py src/ke_memory_demo/evaluation/bootstrap.py src/ke_memory_demo/evaluation/cases.py tests/unit/evaluation/test_metrics.py tests/unit/evaluation/test_bootstrap.py tests/unit/evaluation/test_cases.py
git commit -m "feat: compute paired memory evaluation metrics"
```

### Task 6: Reproducible JSON, CSV, and Markdown Reports

**Files:**
- Create: `src/ke_memory_demo/evaluation/report.py`
- Create: `templates/report.md.j2`
- Create: `tests/golden/report/expected_sections.txt`
- Create: `tests/golden/test_report.py`
- Modify: `pyproject.toml`
- Modify: `src/ke_memory_demo/cli.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: manifest, complete metrics, unique/comparative cases, answers, evidence, Judge, usage, and failure records.
- Produces: `report.json`, `question-results.csv`, `category-results.csv`, `cases.jsonl`, and `report.md` plus `ke-memory report` CLI.

- [ ] **Step 1: Write failing golden report test**

```python
def test_report_contains_protocol_denominators_and_all_categories(tmp_path: Path):
    paths = ReportWriter(tmp_path).write(complete_report_fixture())
    markdown = paths.markdown.read_text()
    for section in expected_sections():
        assert section in markdown
    assert "60/60 questions" in markdown
    assert "300/300 answers" in markdown
    assert "300/300 judge results" in markdown
    assert "Internal ablation" not in markdown
```

- [ ] **Step 2: Run test and verify missing writer**

Run: `uv run pytest tests/golden/test_report.py -v`

Expected: FAIL during import.

- [ ] **Step 3: Implement deterministic reports**

Sort systems in the fixed order `ke-memory`, `mem0`, `graphiti`, `hindsight`, `mempalace`; sort questions by conversation/category/ordinal; emit stable float precision and no current-time field in content-hashed report bodies. Include protocol/version table, completeness, gold mapping coverage, overall scores, ten categories, emphasized categories, paired CIs, source metrics, unsupported/abstention, tokens, stage latency, cost/currency, failures, baseline configuration differences, and limitations.

Run: `uv add 'jinja2>=3.1,<4'`

Expected: `pyproject.toml` and `uv.lock` add Jinja2 without changing unrelated dependency constraints.

- [ ] **Step 4: Implement evidence-backed case studies**

For each unique/comparative case include question, anonymous system answers, rubric decisions, source IDs, normalized evidence text, KE query/matches, aggregate evidence chain for KE memory, and explicit reason each baseline missed. Redact trace secrets and never include model chain-of-thought.

- [ ] **Step 5: Run golden test and commit**

Run: `uv run pytest tests/golden/test_report.py -v`

Expected: report matches expected structure and all output files parse successfully.

```bash
git add pyproject.toml uv.lock src/ke_memory_demo/evaluation/report.py templates/report.md.j2 tests/golden/report tests/golden/test_report.py src/ke_memory_demo/cli.py README.md
git commit -m "feat: report BEAM memory comparison results"
```

### Task 7: Smoke Run, Full BEAM Run, Final Snapshot, and Verification

**Files:**
- Create: `tests/live/test_evaluation_smoke.py`
- Create: `scripts/verify_experiment.py`
- Modify only implementation files required by failures found below.

**Interfaces:**
- Consumes: all prior tasks and real external configuration.
- Produces: one successful smoke run, one complete 3-conversation/60-question run, and an `evaluation-complete` Git snapshot.

- [ ] **Step 1: Run the full offline verification gate**

Run: `uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run pytest -m 'not live_baseline and not live_embedding and not live_es and not live_model and not live_evaluation' -v`

Expected: all commands exit 0 and pytest reports zero failures.

- [ ] **Step 2: Run secret, forbidden-reference, and scope scans**

Run: `! git grep -nE 'sk-[A-Za-z0-9]|/public/home/wwb/memory(/|$)|fusion-memory' -- ':!docs/superpowers/specs/*' ':!docs/superpowers/plans/*' && ! git grep -nE 'embedding-only|turn-KE|hierarchical-KE|KE\+embedding' -- src tests config`

Expected: no tracked secret, forbidden runtime path, or internal-ablation implementation exists.

- [ ] **Step 3: Run live preflight**

Run: `uv run ke-memory evaluate preflight --config-root config --state-root ../ke-memory-demo-state`

Expected: exact BEAM/model/embedding/ES/system identities, five healthy systems, pricing availability, clean Git commit, and zero failed checks. If this fails, stop without ingesting BEAM and report every failed check.

- [ ] **Step 4: Run one-conversation/one-question smoke experiment**

Run: `uv run pytest tests/live/test_evaluation_smoke.py -v -m live_evaluation`

Expected: five systems ingest the same smoke exchanges, produce five answers, and receive five valid blinded Judge results; no comparative report is labeled formal.

- [ ] **Step 5: Run the frozen full experiment**

Run: `uv run ke-memory evaluate run --config-root config --state-root ../ke-memory-demo-state --run-id beam-100k-ke-memory-v1`

Expected: 385 source exchanges per system, 60 questions per system, 300 answers, 300 valid Judge results, zero missing records, and status `complete`.

- [ ] **Step 6: Generate and verify reports**

Run: `uv run ke-memory report --state-root ../ke-memory-demo-state --run-id beam-100k-ke-memory-v1 && uv run python scripts/verify_experiment.py --state-root ../ke-memory-demo-state --run-id beam-100k-ke-memory-v1`

Expected: JSON/CSV/JSONL/Markdown outputs parse, denominators match 385/60/300/300, all ten categories appear, paired bootstrap has 10,000 samples, and no result is synthetic zero.

- [ ] **Step 7: Commit the final state snapshot**

Run: `uv run ke-memory snapshot commit --state-root ../ke-memory-demo-state --run-id beam-100k-ke-memory-v1 --stage evaluation-complete`

Expected: command returns a 40-character commit SHA; `verify-snapshot` rebuilds SQLite and matches every canonical artifact hash. The state commit contains no SQLite, `.env.local`, full ES vocabulary, or unredacted trace.

- [ ] **Step 8: Commit code fixes and the report pointer**

Add only implementation/test/documentation changes in the code repository. Add a small report pointer containing state snapshot SHA and run ID, not duplicate state artifacts.

```bash
git add src tests scripts README.md docs/results
git commit -m "test: verify the full BEAM memory experiment"
```

Do not create an empty code commit when the full run requires no code or documentation changes.
