# KE-only Demo Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the ontology-first, KE-only memory demo from Git-backed pipeline snapshots through a bounded-concurrent BEAM 100K evaluation with common answers, independent DeepSeek Judge results, traceable metrics, and a sourced public-baseline appendix.

**Architecture:** Keep the completed domain, ingestion, ontology, extraction, aggregation, symbolic retrieval, fusion, and answering modules as the stable core. Add a resumable orchestration layer that freezes the ES ontology identity before KE extraction, writes cumulative canonical artifacts, commits successful stages to a separate Git state repository, and exposes `ke-ready` independently of embedding. Add a KE-only evaluation layer that normalizes 60 BEAM questions, runs answer and Judge work with separate bounded concurrency, and writes deterministic reports; no baseline adapter or baseline runtime is built.

**Tech Stack:** Python 3.12, asyncio, Pydantic 2, Typer, HTTPX, OpenAI-compatible SDK, SQLite, Git subprocesses, TOML/JSONL/CSV/Markdown, pytest, pytest-asyncio, Ruff, Pyright.

**Approved Specs:**

- `docs/superpowers/specs/2026-07-15-ke-memory-demo-design.md`
- `docs/superpowers/specs/2026-07-17-ke-only-evaluation-design.md` at commit `2842443`

**Supersedes:**

- Core Tasks 11-12 in `2026-07-15-ke-memory-core-implementation.md`.
- All tasks in `2026-07-15-ke-memory-baselines-implementation.md`; they are cancelled.
- All tasks in `2026-07-15-ke-memory-evaluation-implementation.md`.

## Global Constraints

- Work only in `/public/home/wwb/KE_mem/ke-memory-demo/.worktrees/ke-memory-demo-implementation` on `feature/ke-memory-demo-implementation`.
- Never read from, import, or reference fusion-memory or `/public/home/wwb/memory`.
- Baseline research may read only `/public/home/wwb/memory-sota-study`, frozen official repositories, papers, and official public pages; no baseline is installed or run.
- `Turn` and `Exchange` denote the same basic unit: exactly one User input followed by exactly one
  Agent reply. Tool call/result records are optional attached events inside that Turn; they do not
  form independent Turns, and multiple User/Agent pairs are never merged into one Turn.
- Preserve raw decoded message text exactly. KE is not a lossless replacement for raw text.
- The real Elasticsearch vocabulary is strictly read-only. Ontology identity must be established before Turn KE extraction and rechecked before stage promotion.
- Ontology normalization mode is exactly `bounded-best-effort`; reports must never claim exhaustive normalized recall.
- Do not snapshot the complete ES vocabulary. Persist only identity metadata and documents actually bound to KEs.
- Turn KE dual-track information-loss scoring is deferred. Retain exact spans, hashes, coverage, rejection, and representative raw-to-KE audits.
- Higher-level memory is an overlapping semantic DAG; Task is only one possible node kind and maximum semantic depth remains 2.
- The primary path is KE-only. Existing Qwen embedding code remains optional and default-disabled; formal evaluation must not require `KE_MEMORY_EMBEDDING_PATH` or `embedding-ready`.
- Work model is `gpt-5.4` at `https://api.penguinsaichat.dpdns.org/v1`; answer output maximum is 1024 tokens.
- Judge is official `deepseek-v4-pro` at `https://api.deepseek.com/v1`, one anonymous answer per call.
- BEAM archive is `/public/home/wwb/datasets/BEAM.zip`, SHA-256 `690106a93ab88dac46e8fef1e84884acc889518424240f57a47428d3efbe6346`; selected directories are exactly `4`, `15`, `17` with 13 sessions, 385 exchanges, and 60 questions.
- Evaluation concurrency is bounded and recorded. Source-order lifecycle reconciliation, semantic depth, artifact promotion, and Git commits remain ordered.
- A missing answer or Judge result is not a zero. The run becomes `incomplete` and cannot produce a complete-result claim.
- Do not commit or print credentials. `.env.local` stays ignored and mode `0600`; state snapshots exclude secrets, SQLite, complete ES vocabulary, and unredacted headers.
- Use lean, risk-focused tests. Prefer parameterization and shared fixtures; do not add a separate test for every data combination.
- Unit and golden tests make no live model, ES, embedding, baseline, or network calls.
- Current verified baseline before this plan is `641 passed, 1 skipped`, Ruff clean, Pyright clean.

## File Responsibility Map

- `settings.py` and `config/*.toml`: default-disabled embedding and bounded-concurrency configuration.
- `infra/llm.py`: concurrency-safe per-call structured output plus usage ownership.
- `systems/ke_memory.py`: `ke-ready` protocol boundary.
- `retrieval/disabled_embedding.py`: no-op candidate path used by formal KE-only retrieval.
- `retrieval/records.py`: Conversation-scoped canonical KE/Aggregate/span source for symbolic retrieval.
- `pipeline/models.py`: pipeline stages, ontology receipt, cumulative run manifest, and stage results.
- `pipeline/concurrency.py`: stable ordered bounded execution and failure collection.
- `pipeline/checkpoints.py`: ignored, atomic, content-authenticated item checkpoints.
- `pipeline/runner.py`: ontology-first ingestion, Turn KE, lifecycle, Session, DAG, index, and stage promotion.
- `pipeline/runtime.py`: real settings/client/store wiring used by CLI only.
- `snapshots/git_store.py`: separate state-repository init, commit, checkout, and verification.
- `evaluation/models.py`: normalized questions, answers, Judge outputs, failures, and metrics records.
- `evaluation/questions.py` and `evaluation/gold_sources.py`: deterministic BEAM evaluation inputs.
- `evaluation/manifest.py` and `evaluation/preflight.py`: frozen KE-only run identity and live gates.
- `retrieval/coordinator.py`: structured per-question retrieval trace while preserving Task 10 behavior.
- `evaluation/judge.py` and `evaluation/runner.py`: blinded Judge and bounded-concurrent question execution.
- `evaluation/metrics.py`, `evaluation/baseline_results.py`, and `evaluation/report.py`: deterministic results and sourced non-ranking baseline appendix.
- `cli.py`: stage, smoke, evaluation, report, and snapshot commands.

---

### Task 1: KE-ready Boundary, Optional Embedding, and Concurrent Usage Ownership

**Files:**

- Modify: `config/models.toml`
- Modify: `config/experiment.toml`
- Modify: `src/ke_memory_demo/settings.py`
- Modify: `src/ke_memory_demo/infra/llm.py`
- Modify: `src/ke_memory_demo/infra/secrets.py`
- Modify: `src/ke_memory_demo/answering.py`
- Modify: `src/ke_memory_demo/systems/ke_memory.py`
- Modify: `src/ke_memory_demo/systems/__init__.py`
- Create: `src/ke_memory_demo/retrieval/disabled_embedding.py`
- Modify: `src/ke_memory_demo/retrieval/__init__.py`
- Modify: `tests/unit/test_settings.py`
- Modify: `tests/unit/infra/test_llm.py`
- Modify: `tests/unit/test_secret_hygiene.py`
- Modify: `scripts/init_local_secrets.py`
- Modify: `tests/unit/test_answering.py`
- Modify: `tests/unit/test_ke_memory_system.py`
- Modify: `tests/unit/retrieval/test_orthogonality.py`

**Interfaces:**

- Produces: `EmbeddingSettings.enabled`, `EvaluationConcurrencySettings`, `StructuredCompletion[T]`, `StructuredModelClient.from_model_settings()`, `StructuredModelClient.complete_with_usage()`, `write_runtime_env_local()`, `KE_READY_STAGE`, and `DisabledEmbeddingRetriever.retrieve()`.
- Preserves: every existing `StructuredModelClient.complete()` caller and Task 10 retrieval/fusion behavior.

- [ ] **Step 1: Write the focused failing tests**

Add one settings assertion, one concurrent usage test, update the existing KE system readiness tests, and add one no-op embedding assertion:

```python
def test_primary_demo_disables_embedding_and_bounds_concurrency(project_root: Path) -> None:
    settings = load_settings(project_root)
    assert settings.embedding.enabled is False
    assert settings.evaluation.concurrency.turn_workers == 8
    assert settings.evaluation.concurrency.session_workers == 4
    assert settings.evaluation.concurrency.question_workers == 8
    assert settings.evaluation.concurrency.judge_workers == 8


@pytest.mark.asyncio
async def test_complete_with_usage_keeps_concurrent_calls_separate(concurrent_client) -> None:
    left, right = await asyncio.gather(
        concurrent_client.complete_with_usage(OutputRecord, messages("left"), trace("left")),
        concurrent_client.complete_with_usage(OutputRecord, messages("right"), trace("right")),
    )
    assert left.value.value == "left"
    assert left.usage.request_id == "request-left"
    assert right.value.value == "right"
    assert right.usage.request_id == "request-right"


@pytest.mark.asyncio
async def test_ke_memory_system_requires_successful_ke_ready(tmp_path: Path) -> None:
    stages = _Stages(StageReadiness(stage=KE_READY_STAGE, successful=True, pending_count=0))
    system = make_system(tmp_path, stages)
    await system.prepare(_scope())
    receipt = await system.await_ready()
    assert receipt.ready
    assert stages.ready_calls == [(_scope(), KE_READY_STAGE)]


@pytest.mark.asyncio
async def test_disabled_embedding_returns_no_candidates_without_a_backend() -> None:
    assert await DisabledEmbeddingRetriever().retrieve(question="status?") == ()


def test_runtime_env_file_is_atomic_private_and_complete(tmp_path: Path) -> None:
    target = tmp_path / ".env.local"
    values = {
        "KE_MEMORY_WORK_API_KEY": "work-value",
        "KE_MEMORY_JUDGE_API_KEY": "judge-value",
        "KE_MEMORY_ES_URL": "https://es.example.test",
        "KE_MEMORY_ES_INDEX": "domain-terms",
        "KE_MEMORY_ES_API_KEY": "es-value",
    }
    write_runtime_env_local(target, values)
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert target.read_text().splitlines() == [
        f"{name}={values[name]}" for name in sorted(values)
    ]
```

- [ ] **Step 2: Run the focused tests and confirm the old assumptions fail**

Run:

```bash
uv run pytest tests/unit/test_settings.py tests/unit/infra/test_llm.py \
  tests/unit/test_answering.py tests/unit/test_ke_memory_system.py \
  tests/unit/retrieval/test_orthogonality.py tests/unit/test_secret_hygiene.py -q
```

Expected: failures mention missing `enabled`, missing evaluation concurrency, missing
`complete_with_usage`, missing `write_runtime_env_local`, and the old `embedding-ready`
requirement.

- [ ] **Step 3: Add exact configuration models and defaults**

Add to `config/models.toml`:

```toml
[embedding]
enabled = false
```

Add to `config/experiment.toml`:

```toml
[evaluation.concurrency]
turn_workers = 8
session_workers = 4
question_workers = 8
judge_workers = 8
```

Extend settings with frozen positive values:

```python
class EmbeddingSettings(_FrozenModel):
    enabled: bool
    model: NonEmptyString
    revision: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    local_path_env: NonEmptyString
    dimension: PositiveInt
    chunk_tokens: PositiveInt
    overlap_tokens: Annotated[int, Field(ge=0)]
    local_files_only: bool


class EvaluationConcurrencySettings(_FrozenModel):
    turn_workers: PositiveInt
    session_workers: PositiveInt
    question_workers: PositiveInt
    judge_workers: PositiveInt


class EvaluationSettings(_FrozenModel):
    concurrency: EvaluationConcurrencySettings
```

Add `evaluation: EvaluationSettings` to `_ExperimentFile` and `AppSettings`. Keep `require_embedding_path()` lazy so a disabled formal run never reads `KE_MEMORY_EMBEDDING_PATH`.

Add an allowlisted secret writer while retaining the existing two-key wrapper:

```python
RUNTIME_ENV_NAMES = frozenset(
    {
        "KE_MEMORY_WORK_API_KEY",
        "KE_MEMORY_JUDGE_API_KEY",
        "KE_MEMORY_ES_URL",
        "KE_MEMORY_ES_INDEX",
        "KE_MEMORY_ES_API_KEY",
    }
)


def write_runtime_env_local(path: Path, values: Mapping[str, str]) -> None:
    if set(values) != RUNTIME_ENV_NAMES:
        raise ValueError("runtime environment values must match the exact allowlist")
    if any(not value or "\r" in value or "\n" in value for value in values.values()):
        raise ValueError("runtime environment values must be non-empty single-line strings")
    payload = "".join(f"{name}={values[name]}\n" for name in sorted(values)).encode()
    _atomic_private_write(path, payload)
```

Factor the existing `mkstemp`/`fchmod(0o600)`/`fsync`/`os.replace` implementation into
`_atomic_private_write`. Keep `write_env_local(path, work_key, judge_key)` for existing callers.
Update `scripts/init_local_secrets.py` to prompt for the five allowlisted values without echoing
API keys; it writes no embedding path because embedding is disabled.

- [ ] **Step 4: Make structured usage call-local**

Add this public result type and method without changing existing extraction callers:

```python
from dataclasses import dataclass
from typing import Generic


@dataclass(frozen=True)
class StructuredCompletion(Generic[ModelT]):
    value: ModelT
    usage: UsageRecord


async def complete_with_usage(
    self,
    model_type: type[ModelT],
    messages: Sequence[Mapping[str, object]],
    trace_context: TraceContext | Mapping[str, object],
) -> StructuredCompletion[ModelT]:
    return await self._complete_with_usage(model_type, messages, trace_context)


async def complete(
    self,
    model_type: type[ModelT],
    messages: Sequence[Mapping[str, object]],
    trace_context: TraceContext | Mapping[str, object],
) -> ModelT:
    completion = await self.complete_with_usage(model_type, messages, trace_context)
    return completion.value
```

Inside `_complete_with_usage`, keep a local `list[UsageRecord]`, append every provider response usage including schema-repair responses, and return one aggregate:

```python
def _aggregate_call_usage(records: Sequence[UsageRecord]) -> UsageRecord:
    return UsageRecord(
        request_id=records[-1].request_id,
        model=records[-1].model,
        latency_seconds=sum(item.latency_seconds for item in records),
        input_tokens=sum(item.input_tokens for item in records),
        output_tokens=sum(item.output_tokens for item in records),
        total_tokens=sum(item.total_tokens for item in records),
        provider_cost=(
            sum(cast(float, item.provider_cost) for item in records)
            if all(item.provider_cost is not None for item in records)
            else None
        ),
    )
```

Do not derive usage by slicing a shared recorder; that is unsafe when question calls overlap.

Add a generic client factory used by both configured endpoints:

```python
@classmethod
def from_model_settings(
    cls,
    model_settings: ModelSettings,
    *,
    api_key: str,
    supports_json_schema: bool,
    trace_recorder: TraceRecorder,
) -> StructuredModelClient:
    client = AsyncOpenAI(
        base_url=model_settings.base_url,
        api_key=api_key,
        max_retries=0,
    )
    return cls(
        model_settings,
        client=client,
        supports_json_schema=supports_json_schema,
        trace_recorder=trace_recorder,
        known_secrets=(api_key,),
        _owns_client=True,
    )
```

Keep `from_app_settings()` as the work-model convenience wrapper. The evaluation runtime calls
`StructuredModelClient.from_model_settings(settings.judge,
api_key=settings.require_judge_api_key(), supports_json_schema=False,
trace_recorder=judge_trace_recorder)`; neither factory stores or logs the key.

- [ ] **Step 5: Update AnswerService and KE-only retrieval wiring**

Change `ConfiguredAnswerClient` to require `complete_with_usage`, remove `AnswerUsageSource` from `AnswerService.__init__`, and use the returned call-local usage:

```python
messages = (
    {"role": "system", "content": self._prompt},
    {"role": "user", "content": canonical_json(payload).decode("utf-8")},
)
completion = await self._model.complete_with_usage(
    AnswerModelOutput,
    messages,
    TraceContext(
        operation="common-answer",
        metadata={
            "model": ANSWER_MODEL,
            "max_output_tokens": ANSWER_MAX_OUTPUT_TOKENS,
            "prompt_sha256": self.prompt_sha256,
            "question_sha256": hashlib.sha256(question.encode("utf-8")).hexdigest(),
            "evidence_count": len(ordered),
            "evidence_tokens": evidence_tokens,
        },
    ),
)
output = _validated_output(completion.value)
return AnswerResult(answer=output.answer, citations=output.citations, usage=completion.usage)
```

Add the no-op candidate path:

```python
class DisabledEmbeddingRetriever:
    async def retrieve(self, *, question: str) -> tuple[EvidenceCandidate, ...]:
        if not question.strip():
            raise RetrievalInvariantError("question must not be empty")
        return ()
```

Replace the readiness constant and messages:

```python
KE_READY_STAGE = "ke-ready"

# KEMemorySystem.await_ready()
raw_status = await self._stages.await_ready(scope, KE_READY_STAGE)
if status.stage != KE_READY_STAGE:
    raise KEMemorySystemError(f"readiness must report the {KE_READY_STAGE} stage")
```

Keep `EMBEDDING_READY_STAGE = "embedding-ready"` exported only for the optional embedding path. `stats().metadata` must say `ke_ready`, not `embedding_ready`.

- [ ] **Step 6: Run the focused suite and commit**

Run:

```bash
uv run pytest tests/unit/test_settings.py tests/unit/infra/test_llm.py \
  tests/unit/test_answering.py tests/unit/test_ke_memory_system.py \
  tests/unit/retrieval/test_orthogonality.py tests/unit/test_secret_hygiene.py -q
uv run ruff check src/ke_memory_demo/settings.py src/ke_memory_demo/infra/llm.py \
  src/ke_memory_demo/answering.py src/ke_memory_demo/systems \
  src/ke_memory_demo/retrieval/disabled_embedding.py
```

Expected: focused tests pass and Ruff exits 0.

```bash
git add config/models.toml config/experiment.toml src/ke_memory_demo/settings.py \
  src/ke_memory_demo/infra/llm.py src/ke_memory_demo/infra/secrets.py \
  src/ke_memory_demo/answering.py scripts/init_local_secrets.py \
  src/ke_memory_demo/systems src/ke_memory_demo/retrieval \
  tests/unit/test_settings.py tests/unit/infra/test_llm.py tests/unit/test_answering.py \
  tests/unit/test_ke_memory_system.py tests/unit/retrieval/test_orthogonality.py \
  tests/unit/test_secret_hygiene.py
git commit -m "feat: make KE readiness independent of embedding"
```

### Task 2: Cumulative Stage Manifests and Git Snapshot Store

**Files:**

- Create: `src/ke_memory_demo/pipeline/__init__.py`
- Create: `src/ke_memory_demo/pipeline/models.py`
- Create: `src/ke_memory_demo/snapshots/__init__.py`
- Create: `src/ke_memory_demo/snapshots/git_store.py`
- Modify: `src/ke_memory_demo/storage/__init__.py`
- Create: `tests/unit/snapshots/test_git_store.py`

**Interfaces:**

- Produces: `PipelineStage`, `OntologyRunIdentity`, `PipelineRunManifest`, `PipelineStageResult`, `PIPELINE_ARTIFACT_REGISTRY`, `SnapshotRef`, and `GitSnapshotStore`.
- Consumes: existing `ArtifactStore`, `StageManifest`, `IndexIdentity`, `OntologyTerm`, `OntologyRelation`, `SessionMemory`, and `IndexStats`.

- [ ] **Step 1: Write the failing Git snapshot contract test**

Keep this file to three high-value tests: commit identity, forbidden content, and checkout verification.

```python
def test_snapshot_is_commit_sha_without_self_reference(tmp_path: Path) -> None:
    artifacts, snapshots = initialized_state(tmp_path)
    write_ingested_stage(artifacts, parent_snapshot_id=None)

    result = snapshots.commit_stage("run-1", PipelineStage.INGESTED)

    assert result.snapshot_id == snapshots.head()
    assert len(result.snapshot_id) == 40
    manifest = only_pipeline_manifest(artifacts, "run-1", "ingested")
    assert result.snapshot_id not in canonical_json(manifest).decode()


def test_snapshot_excludes_cache_secrets_and_complete_vocabulary(tmp_path: Path) -> None:
    artifacts, snapshots = initialized_state(tmp_path)
    write_ingested_stage(artifacts, parent_snapshot_id=None)
    artifacts.cache_path("run-1").parent.mkdir(parents=True, exist_ok=True)
    artifacts.cache_path("run-1").write_bytes(b"sqlite")
    (artifacts.root / ".env.local").write_text("SECRET=value")

    result = snapshots.commit_stage("run-1", PipelineStage.INGESTED)
    names = snapshots.tracked_files(result.snapshot_id)

    assert not any("cache/" in name or name.endswith(".sqlite3") for name in names)
    assert ".env.local" not in names
    assert not any("complete-es-vocabulary" in name for name in names)


def test_verify_checks_out_and_revalidates_stage_bytes(tmp_path: Path) -> None:
    artifacts, snapshots = initialized_state(tmp_path)
    write_ingested_stage(artifacts, parent_snapshot_id=None)
    result = snapshots.commit_stage("run-1", PipelineStage.INGESTED)
    assert snapshots.verify(result.snapshot_id, "run-1", PipelineStage.INGESTED).verified
```

Define the three test helpers in the same file: `initialized_state()` creates an `ArtifactStore`
with `PIPELINE_ARTIFACT_REGISTRY` and calls `GitSnapshotStore.init()`;
`write_ingested_stage()` writes one Exchange plus exactly one matching `PipelineRunManifest` with
`stage_writer`; `only_pipeline_manifest()` reads `pipeline_manifests` and requires exactly one
record. The helper manifest uses a fixed fake `IndexIdentity`, code SHA, dataset SHA, and disabled
embedding, so tests never need ES or a model.

- [ ] **Step 2: Run the snapshot tests and confirm imports fail**

Run: `uv run pytest tests/unit/snapshots/test_git_store.py -q`

Expected: collection fails because the pipeline/snapshot models do not exist.

- [ ] **Step 3: Define exact cumulative run records**

Use `StrEnum` and frozen Pydantic models:

```python
class PipelineStage(StrEnum):
    INGESTED = "ingested"
    TURN_KE_EXTRACTED = "turn-ke-extracted"
    SESSION_AGGREGATED = "session-aggregated"
    SEMANTIC_DAG_BUILT = "semantic-dag-built"
    KE_READY = "ke-ready"
    EVALUATION_COMPLETE = "evaluation-complete"


STAGE_PREDECESSOR: dict[PipelineStage, PipelineStage | None] = {
    PipelineStage.INGESTED: None,
    PipelineStage.TURN_KE_EXTRACTED: PipelineStage.INGESTED,
    PipelineStage.SESSION_AGGREGATED: PipelineStage.TURN_KE_EXTRACTED,
    PipelineStage.SEMANTIC_DAG_BUILT: PipelineStage.SESSION_AGGREGATED,
    PipelineStage.KE_READY: PipelineStage.SEMANTIC_DAG_BUILT,
    PipelineStage.EVALUATION_COMPLETE: PipelineStage.KE_READY,
}


class OntologyRunIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    index: IndexIdentity
    normalization_mode: Literal["bounded-best-effort"]
    matched_document_ids: tuple[str, ...] = ()


class PipelineRunManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    run_id: str
    stage: PipelineStage
    parent_snapshot_id: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")] | None
    code_commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    dataset_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    selected_directories: tuple[int, int, int]
    ontology: OntologyRunIdentity
    embedding_enabled: bool
    concurrency: EvaluationConcurrencySettings
    record_counts: dict[str, int]

    @model_validator(mode="after")
    def _ke_only(self) -> PipelineRunManifest:
        if self.embedding_enabled:
            raise ValueError("formal KE-only manifests must keep embedding disabled")
        return self


class PipelineStageResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    run_id: str
    stage: PipelineStage
    snapshot_id: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    record_counts: dict[str, int]


class SnapshotRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    snapshot_id: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    run_id: str
    stage: PipelineStage
    stage_manifest_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class SnapshotVerification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    snapshot_id: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    run_id: str
    stage: PipelineStage
    verified: Literal[True]
    stage_manifest_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
```

Set the custom artifact registry exactly once:

```python
PIPELINE_ARTIFACT_REGISTRY = {
    "pipeline_manifests": PipelineRunManifest,
    "ontology_terms": OntologyTerm,
    "ontology_relations": OntologyRelation,
    "session_memories": SessionMemory,
    "index_stats": IndexStats,
    "current_knowledge_equations": KnowledgeEquation,
    "model_traces": ModelTrace,
}
```

Use `InMemoryTraceRecorder` while concurrent calls are active, then write its validated records
once through the stage's single writer. Do not let concurrent model callbacks call
`ArtifactStore.write_jsonl()` independently.

Every promoted stage is cumulative: it contains the canonical lower-stage records needed to rebuild that stage without reading a later snapshot.

- [ ] **Step 4: Implement the separate Git state repository**

`GitSnapshotStore` exposes the exact public methods `init(root: Path,
artifacts: ArtifactStore) -> GitSnapshotStore`, `head() -> str | None`,
`commit_stage(run_id: str, stage: PipelineStage) -> SnapshotRef`,
`verify(snapshot_id: str, run_id: str, stage: PipelineStage) -> SnapshotVerification`, and
`tracked_files(snapshot_id: str) -> tuple[str, ...]`.

All Git calls go through this checked helper:

```python
def _git(self, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(self._root), *arguments),
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    if completed.returncode != 0:
        raise SnapshotError(
            f"git {' '.join(arguments)} failed: {completed.stderr.strip()}"
        )
    return completed.stdout.strip()
```

Initialization uses non-secret local identity and writes this state-repo `.gitignore`:

```text
.staging/
cache/
checkpoints/
.env.local
*.sqlite3
```

Before commit:

1. Validate the canonical stage through
   `self._artifacts.validate_stage(run_id, stage.value, canonical=True)`.
2. Read exactly one `PipelineRunManifest`.
3. Require `manifest.stage == stage` and `manifest.parent_snapshot_id == head()`; a fresh state
   repo may have `None`, while a new run in an existing state repo points at the current HEAD.
4. For every stage except `ingested`, require the predecessor stage from `STAGE_PREDECESSOR` to
   exist for the same run in the parent tree. This prevents skipped stages even when the state repo
   contains snapshots from other runs.
5. Add only `.gitignore` and `runs/<run_id>/<stage>`.
6. Reject any staged path outside those locations.
7. Commit `stage: <run_id> <stage>` and return `git rev-parse HEAD`.

Verification creates a temporary detached Git worktree, reconstructs an `ArtifactStore` with `PIPELINE_ARTIFACT_REGISTRY`, validates the target stage, compares its manifest hash, removes the worktree, and never changes the caller's checkout.

- [ ] **Step 5: Run snapshot tests, secret scan, and commit**

Run:

```bash
uv run pytest tests/unit/snapshots/test_git_store.py -q
uv run ruff check src/ke_memory_demo/pipeline src/ke_memory_demo/snapshots
! git grep -nE 'sk-[A-Za-z0-9]+' -- src tests config
```

Expected: three snapshot tests pass, Ruff exits 0, and the secret scan has no matches.

```bash
git add src/ke_memory_demo/pipeline src/ke_memory_demo/snapshots \
  src/ke_memory_demo/storage/__init__.py tests/unit/snapshots/test_git_store.py
git commit -m "feat: add Git-backed KE stage snapshots"
```

### Task 3: Bounded Execution and Resumable Item Checkpoints

**Files:**

- Create: `src/ke_memory_demo/pipeline/concurrency.py`
- Create: `src/ke_memory_demo/pipeline/checkpoints.py`
- Modify: `src/ke_memory_demo/pipeline/__init__.py`
- Create: `tests/unit/pipeline/test_execution.py`

**Interfaces:**

- Produces: `bounded_ordered_map()`, `bounded_collect()`, `BatchFailure`, `BatchOutcome[T]`, and `CheckpointStore`.
- Guarantees: bounded active workers, stable input ordering, serializable failures, atomic checkpoint writes, and input-hash/model validation on resume.

- [ ] **Step 1: Write three parameterized execution tests**

```python
@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [1, 2, 4])
async def test_bounded_map_preserves_input_order_and_limit(limit: int) -> None:
    active = 0
    peak = 0

    async def worker(value: int) -> int:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep((5 - value) / 1000)
        active -= 1
        return value * 10

    assert await bounded_ordered_map(range(5), worker, limit=limit) == (0, 10, 20, 30, 40)
    assert peak <= limit


@pytest.mark.asyncio
async def test_collect_keeps_successes_and_typed_failures() -> None:
    async def worker(value: int) -> int:
        if value == 2:
            raise ValueError("bad item")
        return value

    outcome = await bounded_collect(range(4), key=str, worker=worker, limit=2)
    assert outcome.values == (0, 1, 3)
    assert [(item.item_id, item.error_type) for item in outcome.failures] == [("2", "ValueError")]


def test_checkpoint_rejects_changed_input_and_model(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "state", run_id="run-1")
    store.save("turn-ke-extracted", "exchange-1", "a" * 64, TurnExtractionResult, result())
    assert store.load("turn-ke-extracted", "exchange-1", "a" * 64, TurnExtractionResult) == result()
    assert store.load("turn-ke-extracted", "exchange-1", "b" * 64, TurnExtractionResult) is None
    assert store.load("turn-ke-extracted", "exchange-1", "a" * 64, SessionMemory) is None
```

Define `result()` in this test file as
`TurnExtractionResult(exchange_id="exchange-1", knowledge_equations=(), coverage=())`; no model
or ontology fixture is needed for checkpoint framing.

- [ ] **Step 2: Run tests and confirm the utilities are absent**

Run: `uv run pytest tests/unit/pipeline/test_execution.py -q`

Expected: collection fails on missing imports.

- [ ] **Step 3: Implement stable bounded execution**

Use one semaphore and indexed result slots; do not let completion order reorder results:

```python
@dataclass(frozen=True)
class BatchFailure:
    item_id: str
    input_ordinal: int
    error_type: str
    message: str


@dataclass(frozen=True)
class BatchOutcome(Generic[ResultT]):
    values: tuple[ResultT, ...]
    failures: tuple[BatchFailure, ...]


async def bounded_ordered_map(
    items: Iterable[ItemT],
    worker: Callable[[ItemT], Awaitable[ResultT]],
    *,
    limit: int,
) -> tuple[ResultT, ...]:
    values = tuple(items)
    semaphore = asyncio.Semaphore(_positive_limit(limit))
    results: list[ResultT | None] = [None] * len(values)

    async def run(index: int, item: ItemT) -> None:
        async with semaphore:
            results[index] = await worker(item)

    async with asyncio.TaskGroup() as group:
        for index, item in enumerate(values):
            group.create_task(run(index, item))
    return tuple(cast(ResultT, value) for value in results)
```

`bounded_collect` catches `Exception` per item, never `BaseException`, sorts failures by input ordinal, and returns successful values in original order. It is used for evaluation, where one failed question must not erase other diagnostic results. Pipeline promotion uses `bounded_ordered_map` and remains fail-fast.

- [ ] **Step 4: Implement authenticated ignored checkpoints**

Checkpoint envelope:

```python
class CheckpointEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    stage: str
    item_id: str
    input_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    model: str
    payload_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    payload: JsonObject
```

`CheckpointStore.__init__(state_root: Path, run_id: str)` validates and owns one run namespace.
Because domain IDs contain `:`, derive the filename as
`sha256(item_id.encode("utf-8")).hexdigest() + ".json"`; keep the exact item ID only inside the
authenticated envelope. Write to `state_root/checkpoints/<run_id>/<stage>/<filename>` with a
same-directory temporary file, `os.replace`, file `fsync`, and directory `fsync`. `load()`
validates stage/item/input hash,
fully qualified model name, payload hash, and `model_type.model_validate(payload)`; any mismatch
returns `None` and never trusts stale data. Validate all path components with
`validate_storage_name`; require the envelope item ID to be nonempty but never use it as a path.

- [ ] **Step 5: Run focused tests and commit**

Run:

```bash
uv run pytest tests/unit/pipeline/test_execution.py -q
uv run ruff check src/ke_memory_demo/pipeline tests/unit/pipeline/test_execution.py
```

Expected: tests pass and Ruff exits 0.

```bash
git add src/ke_memory_demo/pipeline tests/unit/pipeline/test_execution.py
git commit -m "feat: add resumable bounded pipeline execution"
```

### Task 4: Ontology-first KE Pipeline, CLI, and Golden Workflow

**Files:**

- Create: `src/ke_memory_demo/pipeline/runner.py`
- Create: `src/ke_memory_demo/pipeline/runtime.py`
- Modify: `src/ke_memory_demo/pipeline/__init__.py`
- Create: `src/ke_memory_demo/retrieval/records.py`
- Modify: `src/ke_memory_demo/retrieval/__init__.py`
- Modify: `src/ke_memory_demo/cli.py`
- Create: `tests/golden/data/multi_session_conversation.json`
- Create: `tests/golden/test_memory_pipeline.py`
- Modify: `tests/unit/test_cli.py`
- Create: `README.md`

**Interfaces:**

- Produces: `MemoryPipeline.preflight()`, `ingest()`, `extract_turn_ke()`, `aggregate_sessions()`, `build_semantic_dag()`, `prepare_ke()`, `run_all()`, `RuntimeFactory`, and stage CLI commands.
- Consumes: Tasks 1-3 plus existing `load_beam_subset`, `TurnKEExtractor`, `LifecycleMaintainer`, `SessionAggregator`, `SemanticDAGBuilder`, `MemoryIndex`, and read-only `ElasticsearchVocabulary`.

- [ ] **Step 1: Write one golden workflow test and extend CLI help assertions**

The single golden fixture must cover user preference, cross-session project/task fragments, contradiction, explicit update, ordered events, unresolved ontology term, and tool call/result.
It must also assert that every Turn contains exactly one User message and one Agent reply, while
tool events remain attached to that pair.

```python
@pytest.mark.asyncio
async def test_golden_pipeline_is_ontology_first_ke_only_and_traceable(golden_runtime) -> None:
    result = await golden_runtime.pipeline.run_all()

    assert golden_runtime.ontology.calls[0] == "health"
    assert golden_runtime.ontology.calls[1] == "index_identity"
    assert golden_runtime.first_extract_call > golden_runtime.last_preflight_call
    assert golden_runtime.embedding_calls == 0
    assert result.stage is PipelineStage.KE_READY
    assert result.exchange_count == 4
    assert result.semantic_dag.max_depth <= 2
    assert any(node.depth == 1 and len(node.evidence_closure) >= 2 for node in result.semantic_dag.nodes)
    current = result.find_current_ke("project status")
    assert current.supersedes
    assert result.resolve_raw_spans(current.id)
    assert golden_runtime.snapshots.verify(
        result.snapshot_id, result.run_id, PipelineStage.KE_READY
    ).verified


def test_cli_lists_ke_only_stages() -> None:
    result = runner.invoke(app, ["--help"])
    for command in (
        "preflight", "ingest", "extract-turn-ke", "aggregate-session",
        "build-semantic-dag", "prepare-ke", "run-pipeline", "retrieve",
        "verify-snapshot",
    ):
        assert command in result.stdout
    assert "run-baselines" not in result.stdout
```

- [ ] **Step 2: Run the golden and CLI tests and confirm pipeline commands are missing**

Run: `uv run pytest tests/golden/test_memory_pipeline.py tests/unit/test_cli.py -q`

Expected: failures mention missing `MemoryPipeline` and missing commands.

- [ ] **Step 3: Implement preflight and cumulative stage writing**

`MemoryPipeline` constructor:

```python
class MemoryPipeline:
    def __init__(
        self,
        settings: AppSettings,
        artifacts: ArtifactStore,
        snapshots: GitSnapshotStore,
        checkpoints: CheckpointStore,
        ontology: ElasticsearchVocabulary,
        work_model: StructuredModelClient,
        *,
        code_commit: str,
    ) -> None:
        if len(code_commit) != 40:
            raise PipelineInvariantError("code_commit must be a full Git SHA")
        if settings.embedding.enabled:
            raise PipelineInvariantError("the primary pipeline requires embedding.enabled=false")
        self._settings = settings
        self._artifacts = artifacts
        self._snapshots = snapshots
        self._checkpoints = checkpoints
        self._ontology = ontology
        self._work_model = work_model
        self._code_commit = code_commit
        self._ontology_identity: IndexIdentity | None = None
```

`preflight()` performs, in order:

1. `ontology.health()`.
2. `ontology.index_identity()` and pin exact identity.
3. Verify normalization mode equals `bounded-best-effort`.
4. Verify BEAM archive hash and exact counts without writing memory artifacts.
5. Execute one minimal structured work-model request.
6. Initialize/verify the Git state repository and available disk.
7. Do not call `require_embedding_path()`.

Each stage writes cumulative canonical records with `ArtifactStore.stage_writer`, adds exactly one `pipeline_manifests` record whose parent is the current state HEAD, validates record counts, then calls `GitSnapshotStore.commit_stage`. No partial stage creates a commit.

- [ ] **Step 4: Implement bounded Turn KE and ordered lifecycle reconciliation**

For all 385 Exchanges, compute `input_sha256 = sha256(canonical_json(exchange))`. Reuse a
valid `TurnExtractionResult` checkpoint or execute this exact bounded call:

```python
turn_results = await bounded_ordered_map(
    ordered_exchanges,
    extract_or_load_checkpoint,
    limit=self._settings.evaluation.concurrency.turn_workers,
)
```

Then process each conversation independently in source ordinal order:

```python
current: tuple[KnowledgeEquation, ...] = ()
all_revisions: list[KnowledgeEquation] = []
for result in ordered_conversation_results:
    lifecycle = await maintainer.apply(current, result.knowledge_equations)
    all_revisions.extend(result.knowledge_equations)
    all_revisions.extend(lifecycle.appended_revisions)
    current = lifecycle.current_records
```

The three Conversation reconciliation chains may run concurrently with a limit of
`min(3, session_workers)`, but the loop inside each chain is strictly serial.

Deduplicate revisions by `(id, revision)`, keep every historical revision, and preserve coverage from extraction. Re-read ES identity after all workers and before promotion. Collect resolved document IDs from actual KE bindings, call only `fetch_terms(ids)` and `fetch_relations(ids)`, and save those matched records; never enumerate the index.

- [ ] **Step 5: Implement Session, DAG, and KE-ready stages**

Run Session aggregation with `session_workers`, one Session per item after all its Turn KEs and coverage validate. Build one semantic DAG per Conversation; conversations may run concurrently, but each builder completes depth 1 before depth 2. Merge DAGs in conversation-ID order.

At `ke-ready`:

1. Include every Turn, Session, and aggregate assertion revision in `knowledge_equations` for
   audit history, and exactly one latest revision per logical ID in
   `current_knowledge_equations` for indexing/retrieval.
2. Include AggregateNodes in `aggregates`.
3. Revalidate every evidence closure and ontology binding.
4. Rebuild `MemoryIndex` from Exchanges, `current_knowledge_equations`, and AggregateNodes so an
   earlier revision of the same logical ID cannot create an unauthenticated lifecycle hit.
5. Save one `IndexStats` record.
6. Require successful `ke-ready`; do not create or require `embedding-ready`.

Return this non-artifact convenience record from `run_all()`:

```python
class PipelineRunResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)
    run_id: str
    stage: Literal[PipelineStage.KE_READY]
    snapshot_id: str
    conversations: tuple[Conversation, ...]
    current_knowledge_equations: tuple[KnowledgeEquation, ...]
    session_memories: tuple[SessionMemory, ...]
    semantic_dag: SemanticDAG

    @property
    def exchange_count(self) -> int:
        return sum(
            len(session.exchanges)
            for conversation in self.conversations
            for session in conversation.sessions
        )

    def find_current_ke(self, gloss_fragment: str) -> KnowledgeEquation:
        matches = tuple(
            item
            for item in self.current_knowledge_equations
            if gloss_fragment.casefold() in item.gloss.casefold()
            and item.lifecycle in (Lifecycle.ACTIVE, Lifecycle.UNCERTAIN)
        )
        if len(matches) != 1:
            raise PipelineInvariantError("current KE lookup must resolve exactly one record")
        return matches[0]
```

`resolve_raw_spans(ke_id: str) -> tuple[tuple[MessageSpan, str], ...]` finds the current KE,
resolves each span against canonical user/assistant messages, calls `Message.validate_span`, and
returns the span plus exact substring. It must not read cached evidence text.

- [ ] **Step 6: Wire real runtime and Typer commands**

`RuntimeFactory.from_paths(config_root, state_root)` constructs settings, `ArtifactStore` with
`PIPELINE_ARTIFACT_REGISTRY`, `GitSnapshotStore`, `CheckpointStore`, redacting trace recorders,
one extraction/query/match `StructuredModelClient` using `settings.work`, and
`ElasticsearchVocabulary`. For evaluation it creates a separate answer client from
`settings.work.model_copy(update={"max_output_tokens":
settings.retrieval.answer_max_output_tokens})` and a separate Judge client from
`settings.judge`. Clients may share the same secret value in memory but never a mutable usage
slice or trace recorder. It never logs secret values.

Add `CanonicalSymbolicRecordSource` in `retrieval/records.py`:

```python
class CanonicalSymbolicRecordSource:
    def __init__(
        self,
        exchanges: Sequence[Exchange],
        current_knowledge_equations: Sequence[KnowledgeEquation],
        aggregates: Sequence[AggregateNode],
    ) -> None:
        self._messages = {
            record.id: (exchange, record)
            for exchange in exchanges
            for record in (exchange.user, exchange.assistant)
        }
        self._kes = {item.id: item for item in current_knowledge_equations}
        if len(self._kes) != len(current_knowledge_equations):
            raise SymbolicInvariantError("current KE records contain duplicate logical IDs")
        self._aggregates = {item.id: item for item in aggregates}

    def get_knowledge_equation(self, record_id: str) -> KnowledgeEquation | None:
        return self._kes.get(record_id)

    def get_aggregate(self, record_id: str) -> AggregateNode | None:
        return self._aggregates.get(record_id)

    def resolve_span(self, span: MessageSpan) -> SourceFragment:
        exchange, message = self._messages[span.message_id]
        message.validate_span(span)
        return SourceFragment(
            fragment_id=content_id("source_fragment", span.model_dump(mode="json")),
            text=message.content[span.start_char : span.end_char],
            span=span,
            source_exchange_id=exchange.id,
            source_session_id=exchange.session_id,
        )
```

When hydrating retrieval, `RuntimeFactory.build_ke_systems(run_id, snapshot_id)` filters the
cumulative `ke-ready` records by Conversation, rebuilds one scope-local SQLite index under the
owned runtime cache, constructs `CanonicalSymbolicRecordSource`, `QueryKEExtractor`,
`SymbolicRetriever`, `LLMMatcher`, `DisabledEmbeddingRetriever`, `EvidenceFusion`, and
`RetrievalCoordinator`, then prepares one `KEMemorySystem` per Conversation. A query must never
see records from another Conversation.

Every stage command accepts `--run-id`, `--config-root`, and `--state-root`, refuses skipped prerequisites, prints JSON containing stage, counts, and snapshot SHA, and exits nonzero on failure. `run-pipeline` executes through `ke-ready`; `retrieve` requires a verified `ke-ready` snapshot and uses `DisabledEmbeddingRetriever`; `verify-snapshot` checks out and validates a supplied SHA.

README must document the ontology-first order, `.env.local` variable names only, KE-only commands, snapshot locations, and that embedding/baselines are not part of the primary run.

- [ ] **Step 7: Run the golden/core-focused tests and commit**

Run:

```bash
uv run pytest tests/golden/test_memory_pipeline.py tests/unit/test_cli.py \
  tests/unit/pipeline tests/unit/snapshots -q
uv run ke-memory --help
```

Expected: tests pass; help lists KE-only commands and no baseline command.

```bash
git add src/ke_memory_demo/pipeline src/ke_memory_demo/retrieval/records.py \
  src/ke_memory_demo/retrieval/__init__.py src/ke_memory_demo/cli.py \
  tests/golden tests/unit/test_cli.py README.md
git commit -m "feat: complete ontology-first KE pipeline"
```

### Task 5: Core Verification Gate

**Files:**

- Modify only files required by failures from the commands below.
- Update after review: `.git/worktrees/ke-memory-demo-implementation/sdd/progress.md`.

**Interfaces:**

- Consumes: Tasks 1-4 and all completed Core Tasks 1-10.
- Produces: a reviewed `ke-ready` core that no longer depends on baseline or embedding execution.

- [ ] **Step 1: Run format, lint, types, and the complete offline suite**

Run:

```bash
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest -m 'not live_embedding and not live_es and not live_model and not live_baseline and not live_evaluation' -q
```

Expected: all commands exit 0; pytest has zero failures. Do not loosen type checking or delete a meaningful test to pass this gate.

- [ ] **Step 2: Reconfirm fixed BEAM normalization and KE-only readiness**

Run:

```bash
uv run pytest tests/integration/test_beam_subset.py \
  tests/integration/test_sqlite_rebuild.py \
  tests/golden/test_memory_pipeline.py -q
```

Expected: exact directories `4,15,17`, 13 sessions, 385 Exchanges, 60 excluded probing questions, reproducible SQLite rebuild, and a verified `ke-ready` snapshot.

- [ ] **Step 3: Run scope and secret scans**

Run:

```bash
! git grep -nE 'sk-[A-Za-z0-9]+' -- src tests config scripts README.md
! git grep -nE 'fusion-memory|/public/home/wwb/memory(/|$)' -- src tests config scripts README.md
! git grep -nE 'run-baselines|live_baseline' -- src config README.md
git diff --check
```

Expected: no credential, forbidden source, or baseline runtime remains; `git diff --check` exits 0. Existing pytest marker metadata may retain `live_baseline` until a later cleanup only if no runtime code uses it.

- [ ] **Step 4: Record review outcome and commit fixes if needed**

Task status is complete only after spec-compliance and code-quality review both pass. Record the new verified test count and the fact that embedding is optional/default-disabled. If verification required code changes:

```bash
git add -A
git commit -m "test: verify KE-only core pipeline"
```

Do not create an empty commit.

### Task 6: BEAM Questions, Gold Sources, Experiment Manifest, and Live Preflight

**Files:**

- Create: `src/ke_memory_demo/evaluation/__init__.py`
- Create: `src/ke_memory_demo/evaluation/models.py`
- Create: `src/ke_memory_demo/evaluation/questions.py`
- Create: `src/ke_memory_demo/evaluation/gold_sources.py`
- Create: `src/ke_memory_demo/evaluation/manifest.py`
- Create: `src/ke_memory_demo/evaluation/preflight.py`
- Create: `tests/unit/evaluation/test_inputs.py`
- Create: `tests/integration/test_beam_evaluation_inputs.py`
- Modify: `src/ke_memory_demo/pipeline/runtime.py`
- Modify: `src/ke_memory_demo/cli.py`

**Interfaces:**

- Produces: `QuestionCategory`, `ProbeQuestion`, `SourceCatalog`, `GoldSourceMapping`, `ExperimentManifest`, `PreflightCheck`, `PreflightReport`, `normalize_questions()`, `build_gold_source_mapping()`, and `EvaluationPreflight.run()`.
- Consumes: a verified `ke-ready` snapshot, fixed BEAM Conversations, work/Judge settings, ontology identity, prompt hashes, concurrency settings, and code/spec/plan identities.

- [ ] **Step 1: Write compact input and preflight tests**

Use one parameterized unit file and one real-archive integration file:

```python
@pytest.mark.parametrize(
    ("raw", "field", "answer"),
    [
        ({"ideal_answer": "a", "ideal_response": "b", "answer": "c"}, "ideal_answer", "a"),
        ({"ideal_response": "b", "answer": "c"}, "ideal_response", "b"),
        ({"answer": "c"}, "answer", "c"),
    ],
)
def test_answer_priority(raw: JsonObject, field: str, answer: str) -> None:
    value = {"question": "q", "rubric": ["r"], **raw}
    normalized = normalize_question(
        value, conversation_id="conversation-1", category="knowledge_update", ordinal=0
    )
    assert normalized.ideal_answer == answer
    assert normalized.original_answer_field == field


def test_gold_mapping_uses_only_unique_explicit_source_numbers(conversation_fixture) -> None:
    catalog = SourceCatalog.from_conversation(conversation_fixture)
    mapping = build_gold_source_mapping(
        {"source_chat_ids": [8, [10, 12]], "conversation_references": ["Session 14"]},
        catalog,
        question_id="q-1",
    )
    assert mapping.status is GoldSourceStatus.MAPPED
    assert mapping.source_numbers == (8, 10, 12, 14)
    assert mapping.source_exchange_ids == catalog.resolve((8, 10, 12, 14))


@pytest.mark.asyncio
async def test_preflight_reports_all_failures_without_ingestion(fake_preflight_ports) -> None:
    fake_preflight_ports.fail("judge_model", "state_repo", "ontology_identity")
    report = await EvaluationPreflight(fake_preflight_ports).run()
    assert report.ready is False
    assert [item.name for item in report.failed] == [
        "judge_model", "ontology_identity", "state_repo"
    ]
    assert fake_preflight_ports.ingest_calls == 0
```

The integration test loads the real archive and asserts 60 normalized questions, ten categories, two questions/category/conversation, stable IDs, and no question/rubric/ideal answer in any ingested Exchange.

- [ ] **Step 2: Run input tests and confirm evaluation modules are absent**

Run:

```bash
uv run pytest tests/unit/evaluation/test_inputs.py \
  tests/integration/test_beam_evaluation_inputs.py -q
```

Expected: collection fails on missing evaluation modules.

- [ ] **Step 3: Implement normalized question and exact source models**

```python
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


class ProbeQuestion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str
    conversation_id: str
    category: QuestionCategory
    ordinal: int
    question: str
    ideal_answer: str
    original_answer_field: Literal["ideal_answer", "ideal_response", "answer"]
    rubric: tuple[str, ...]
    raw_metadata: JsonObject


class GoldSourceStatus(StrEnum):
    MAPPED = "mapped"
    UNMAPPABLE = "unmappable"


class GoldSourceMapping(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    question_id: str
    status: GoldSourceStatus
    source_numbers: tuple[int, ...] = ()
    source_exchange_ids: tuple[str, ...] = ()
    matched_paths: tuple[str, ...] = ()
    exclusion_reason: str | None = None
```

`SourceCatalog.from_conversation()` maps each integer `raw_message_id` in message/tool metadata to exactly one Exchange. Recursively collect integers only under explicit source fields such as `source_chat_ids`; parse free text only with case-insensitive `\b(?:chat_id|Session)\s*:?\s*(\d+)\b`. Zero or multiple Exchange matches make the question unmappable. Never use an LLM or answer similarity for gold mapping.

The exact function signature is
`build_gold_source_mapping(raw: JsonObject, catalog: SourceCatalog, *, question_id: str) ->
GoldSourceMapping`. `SourceCatalog.resolve(numbers: Sequence[int]) -> tuple[str, ...]` raises a
typed mapping error unless every number maps to exactly one Exchange.

- [ ] **Step 4: Implement the immutable KE-only experiment manifest**

```python
class ExperimentManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    run_id: str
    code_commit: str
    spec_sha256: str
    plan_sha256: str
    ke_ready_snapshot_id: str
    dataset_sha256: str
    selected_directories: tuple[int, int, int]
    expected_sessions: int
    expected_exchanges: int
    expected_questions: int
    question_manifest_sha256: str
    gold_mapping_sha256: str
    ontology: OntologyRunIdentity
    work_model: str
    work_base_url: str
    judge_model: str
    judge_base_url: str
    answer_prompt_sha256: str
    judge_prompt_sha256: str
    embedding_enabled: Literal[False]
    concurrency: EvaluationConcurrencySettings
    created_at: AwareDatetime
    content_hash: str
```

Compute `content_hash` from canonical JSON excluding `content_hash` and `created_at`. Endpoints are allowed; keys and headers are not. Do not include baseline runtime identities, embedding fingerprints, pricing gates, or paired-bootstrap settings.

- [ ] **Step 5: Implement all-at-once live preflight**

`EvaluationPreflight.run()` returns every failed check sorted by name and performs no ingestion. Checks are:

```python
class PreflightCheck(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str
    passed: bool
    detail: str


class PreflightReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    checks: tuple[PreflightCheck, ...]

    @property
    def ready(self) -> bool:
        return all(item.passed for item in self.checks)

    @property
    def failed(self) -> tuple[PreflightCheck, ...]:
        return tuple(item for item in self.checks if not item.passed)
```

`detail` contains check names, non-secret identities, counts, or sanitized error classes only. It
must never contain an environment value, Authorization header, cookie, or provider response body.

1. Clean code commit and approved spec/plan hashes.
2. Verified `ke-ready` snapshot with exact 4/15/17, 13/385/60 counts.
3. Current ES identity equals the `ke-ready` ontology identity and mode is `bounded-best-effort`.
4. One minimal structured work-model request and one minimal structured Judge request.
5. Work/Judge/ES environment variables exist and `.env.local`, when used, has mode `0600`;
   failures report variable names only.
6. State Git repository is writable and has the expected HEAD.
7. `embedding.enabled` is false and no embedding path is required.
8. Concurrency limits are positive.
9. Tracked source/config/tests contain no `sk-` credential.

Add `ke-memory evaluate preflight`; it prints canonical JSON and exits 2 when `ready` is false.

- [ ] **Step 6: Run input/preflight tests and commit**

Run:

```bash
uv run pytest tests/unit/evaluation/test_inputs.py \
  tests/integration/test_beam_evaluation_inputs.py tests/unit/test_cli.py -q
uv run ruff check src/ke_memory_demo/evaluation tests/unit/evaluation \
  tests/integration/test_beam_evaluation_inputs.py
```

Expected: tests pass and Ruff exits 0.

```bash
git add src/ke_memory_demo/evaluation src/ke_memory_demo/pipeline/runtime.py \
  src/ke_memory_demo/cli.py tests/unit/evaluation tests/integration/test_beam_evaluation_inputs.py \
  tests/unit/test_cli.py
git commit -m "feat: freeze KE-only BEAM evaluation inputs"
```

### Task 7: Structured Retrieval Trace, Concurrent Answers, and Independent Judge

**Files:**

- Create: `src/ke_memory_demo/retrieval/coordinator.py`
- Modify: `src/ke_memory_demo/retrieval/query.py`
- Modify: `src/ke_memory_demo/retrieval/__init__.py`
- Create: `prompts/judge/system.md`
- Create: `src/ke_memory_demo/evaluation/judge.py`
- Create: `src/ke_memory_demo/evaluation/runner.py`
- Modify: `src/ke_memory_demo/evaluation/models.py`
- Modify: `src/ke_memory_demo/evaluation/__init__.py`
- Modify: `src/ke_memory_demo/pipeline/models.py`
- Modify: `src/ke_memory_demo/pipeline/runtime.py`
- Modify: `src/ke_memory_demo/cli.py`
- Modify: `tests/unit/retrieval/test_orthogonality.py`
- Create: `tests/unit/evaluation/test_runner_and_judge.py`

**Interfaces:**

- Produces: `RetrievalTrace`, `RetrievalTraceRecorder`, `QuestionAnswer`, `RubricJudgement`, `JudgeResult`, `EvaluationFailure`, `EvaluationRun`, `JudgeService.judge()`, and `EvaluationRunner.run()`.
- Preserves: public import `ke_memory_demo.retrieval.RetrievalCoordinator` and the symbolic/embedding orthogonality contract.

- [ ] **Step 1: Write compact trace, blindness, and concurrency tests**

```python
@pytest.mark.asyncio
async def test_ke_only_coordinator_records_structured_trace() -> None:
    recorder = InMemoryRetrievalTraceRecorder()
    coordinator = RetrievalCoordinator(
        symbolic_spy(), DisabledEmbeddingRetriever(), matcher_spy(), fusion_spy(),
        trace_recorder=recorder,
    )
    evidence = await coordinator.retrieve("current project status?")
    [trace] = recorder.records
    assert trace.query_ke.gloss
    assert trace.symbolic_candidate_ids
    assert trace.matches
    assert trace.evidence_ids == tuple(item.evidence_id for item in evidence)
    assert trace.embedding_candidate_count == 0


@pytest.mark.asyncio
async def test_judge_payload_is_blind_and_score_is_derived(fake_judge_client) -> None:
    result = await JudgeService(fake_judge_client).judge(question(), answer())
    payload = fake_judge_client.last_user_payload
    assert set(payload) == {"question", "ideal_answer", "rubric", "candidate_answer"}
    assert "ke-memory" not in canonical_json(payload).decode().lower()
    assert result.answer_score == pytest.approx(2 / 3)


@pytest.mark.asyncio
async def test_runner_bounds_work_and_judge_and_keeps_stable_order(fake_evaluation) -> None:
    run = await fake_evaluation.runner.run(fake_evaluation.questions)
    assert [item.question_id for item in run.answers] == sorted(
        item.question_id for item in run.answers
    )
    assert fake_evaluation.work_peak <= 3
    assert fake_evaluation.judge_peak <= 2
    assert run.status is EvaluationStatus.COMPLETE


@pytest.mark.asyncio
async def test_missing_judge_marks_incomplete_without_zero(fake_evaluation) -> None:
    fake_evaluation.judge.fail_question("q-2")
    run = await fake_evaluation.runner.run(fake_evaluation.questions)
    assert run.status is EvaluationStatus.INCOMPLETE
    assert [item.question_id for item in run.judgements] == ["q-1", "q-3"]
    assert all(failure.question_id == "q-2" for failure in run.failures)
```

- [ ] **Step 2: Run tests and confirm missing trace/Judge/runner code**

Run:

```bash
uv run pytest tests/unit/retrieval/test_orthogonality.py \
  tests/unit/evaluation/test_runner_and_judge.py -q
```

Expected: missing imports fail before implementation.

- [ ] **Step 3: Move only coordinator responsibility and record typed traces**

Move `_SymbolicPath`, `_EmbeddingPath`, `_Matcher`, `_Fusion`, and `RetrievalCoordinator` from `query.py` to `coordinator.py`; leave Query KE extraction and `EmbeddingRetriever` in `query.py`. Keep re-exports stable.

```python
class RetrievalTrace(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    question_sha256: str
    query_ke: QueryKE
    symbolic_candidate_ids: tuple[str, ...]
    matches: tuple[KEMatchDecision, ...]
    embedding_candidate_count: int
    evidence_ids: tuple[str, ...]


class RetrievalCoordinator:
    def __init__(
        self,
        symbolic: object,
        embedding: object,
        matcher: object,
        fusion: object,
        *,
        trace_recorder: RetrievalTraceRecorder | None = None,
    ) -> None:
        self._symbolic = cast(_SymbolicPath, symbolic)
        self._embedding = cast(_EmbeddingPath, embedding)
        self._matcher = cast(_Matcher, matcher)
        self._fusion = cast(_Fusion, fusion)
        self._trace_recorder = trace_recorder or InMemoryRetrievalTraceRecorder()

    async def retrieve(self, question: str, evidence_budget_tokens: int = 8192) -> Sequence[Evidence]:
        query_ke = await self._symbolic.extract_query(question)
        symbolic = tuple(await self._symbolic.retrieve(query_ke=query_ke))
        matches = tuple(await self._matcher.match(query_ke=query_ke, symbolic_candidates=symbolic))
        embedding = tuple(await self._embedding.retrieve(question=question))
        evidence = tuple(self._fusion.fuse(
            symbolic_candidates=symbolic,
            matches=matches,
            embedding_candidates=embedding,
            budget=evidence_budget_tokens,
        ))
        self._trace_recorder.record(
            RetrievalTrace(
                question_sha256=hashlib.sha256(question.encode("utf-8")).hexdigest(),
                query_ke=query_ke,
                symbolic_candidate_ids=tuple(item.candidate_id for item in symbolic),
                matches=matches,
                embedding_candidate_count=len(embedding),
                evidence_ids=tuple(item.evidence_id for item in evidence),
            )
        )
        return evidence
```

Do not add embedding scores to the symbolic path. Formal runtime injects `DisabledEmbeddingRetriever`.

- [ ] **Step 4: Implement exact blinded Judge schema**

Judge prompt instructs evaluation against every rubric item, forbids hidden chain-of-thought, and requests concise reasons only.

```python
class RubricJudgement(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    rubric: str
    satisfied: bool
    reason: str


class JudgeModelOutput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    rubric_items: tuple[RubricJudgement, ...]
    factual_error: bool
    unsupported_claim: bool
    abstention_correct: bool | None
    short_rationale: str


class JudgeResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    question_id: str
    rubric_items: tuple[RubricJudgement, ...]
    answer_score: float
    factual_error: bool
    unsupported_claim: bool
    abstention_correct: bool | None
    short_rationale: str
    usage: UsageRecord


class EvaluationStatus(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


class QuestionAnswer(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    question_id: str
    conversation_id: str
    evidence: tuple[Evidence, ...]
    answer: str
    citations: tuple[str, ...]
    retrieval_trace: RetrievalTrace
    usage: UsageRecord


class EvaluationFailure(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    question_id: str
    stage: Literal["retrieve_answer", "judge"]
    error_type: str
    message: str


class QuestionExecution(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    answer: QuestionAnswer
    judgement: JudgeResult | None
    failure: EvaluationFailure | None

    @model_validator(mode="after")
    def _judge_outcome(self) -> QuestionExecution:
        if (self.judgement is None) == (self.failure is None):
            raise ValueError("question execution requires exactly one Judge outcome")
        return self


class EvaluationRun(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    manifest_hash: str
    status: EvaluationStatus
    answers: tuple[QuestionAnswer, ...]
    judgements: tuple[JudgeResult, ...]
    failures: tuple[EvaluationFailure, ...]
```

`JudgeService` sends only `question`, `ideal_answer`, `rubric`, and `candidate_answer`; requires exact rubric text and order; computes `answer_score` in code; and uses `complete_with_usage()`. It never accepts a system ID, evidence, KE, category, competing answer, or baseline data.

Add these registry entries when constructing evaluation state:

```python
EVALUATION_ARTIFACT_REGISTRY = {
    "probe_questions": ProbeQuestion,
    "gold_source_mappings": GoldSourceMapping,
    "experiment_manifests": ExperimentManifest,
    "query_traces": QueryExtractionTrace,
    "retrieval_traces": RetrievalTrace,
    "question_answers": QuestionAnswer,
    "judge_results": JudgeResult,
    "evaluation_failures": EvaluationFailure,
    "evaluation_runs": EvaluationRun,
}
```

- [ ] **Step 5: Implement per-question answer/Judge execution with separate limits**

```python
class EvaluationRunner:
    def __init__(
        self,
        systems: Mapping[str, KEMemorySystem],
        answer_services: Mapping[str, AnswerService],
        judge: JudgeService,
        checkpoints: CheckpointStore,
        manifest: ExperimentManifest,
    ) -> None:
        if set(systems) != set(answer_services):
            raise EvaluationInvariantError(
                "systems and answer services must cover the same Conversations"
            )
        self._systems = dict(systems)
        self._answer_services = dict(answer_services)
        self._judge = judge
        self._checkpoints = checkpoints
        self._manifest = manifest
        self._work_semaphore = asyncio.Semaphore(
            manifest.concurrency.question_workers
        )
        self._judge_semaphore = asyncio.Semaphore(
            manifest.concurrency.judge_workers
        )

    async def run(self, questions: Sequence[ProbeQuestion]) -> EvaluationRun:
        ordered = tuple(sorted(questions, key=lambda item: item.id))
        outcome = await bounded_collect(
            ordered,
            key=lambda item: item.id,
            worker=self._run_question,
            limit=self._manifest.concurrency.question_workers,
        )
        return self._build_run(ordered, outcome)
```

The private signatures are
`_run_question(question: ProbeQuestion) -> QuestionExecution` and
`_build_run(expected: Sequence[ProbeQuestion], outcome: BatchOutcome[QuestionExecution]) ->
EvaluationRun`. `_build_run` converts `BatchFailure` records into sanitized
`retrieve_answer` failures. `_run_question` checkpoints and retains a valid answer even if Judge
fails, returning a `QuestionExecution` with `judgement=None` and a sanitized `judge` failure.
`_build_run` sets `complete` only when all expected IDs occur once in both answers and Judgements.

One question task performs:

1. Select the prepared/`ke-ready` system by `conversation_id`.
2. Acquire the work semaphore, retrieve KE-only evidence, generate the answer, attach the structured retrieval trace, and atomically checkpoint `QuestionAnswer`.
3. Release work semaphore.
4. Acquire the independent Judge semaphore, Judge the saved answer, and checkpoint `JudgeResult`.
5. Release Judge semaphore.

Across questions, these phases overlap. Use `bounded_collect` with `question_workers`; the work semaphore capacity is `question_workers` and the Judge semaphore capacity is `judge_workers`. Checkpoints are reusable only when manifest hash, question hash, `ke-ready` snapshot, prompt hash, actual model ID, and payload hash match. Return answers/Judgements sorted by question ID, plus sorted typed failures. Exactly 60 valid answers and 60 valid Judgements are required for `complete`.

Add `ke-memory evaluate smoke` for one fixed conversation/question and `ke-memory evaluate run` for the exact full set. Only the latter can be formal.

- [ ] **Step 6: Run focused tests and commit**

Run:

```bash
uv run pytest tests/unit/retrieval/test_orthogonality.py \
  tests/unit/evaluation/test_runner_and_judge.py tests/unit/test_cli.py -q
uv run ruff check src/ke_memory_demo/retrieval src/ke_memory_demo/evaluation \
  tests/unit/evaluation/test_runner_and_judge.py
```

Expected: tests pass; concurrency peaks stay within configured limits and Judge payload remains blind.

```bash
git add prompts/judge src/ke_memory_demo/retrieval src/ke_memory_demo/evaluation \
  src/ke_memory_demo/pipeline src/ke_memory_demo/cli.py \
  tests/unit/retrieval/test_orthogonality.py tests/unit/evaluation/test_runner_and_judge.py \
  tests/unit/test_cli.py
git commit -m "feat: run concurrent KE answers with independent judge"
```

### Task 8: Metrics, Turn KE Audit, Public Baseline Appendix, and Deterministic Report

**Files:**

- Create: `data/baselines/public_results.toml`
- Create: `src/ke_memory_demo/evaluation/baseline_results.py`
- Create: `src/ke_memory_demo/evaluation/metrics.py`
- Create: `src/ke_memory_demo/evaluation/report.py`
- Modify: `src/ke_memory_demo/evaluation/models.py`
- Modify: `src/ke_memory_demo/evaluation/__init__.py`
- Modify: `src/ke_memory_demo/pipeline/models.py`
- Modify: `src/ke_memory_demo/pipeline/runtime.py`
- Modify: `src/ke_memory_demo/cli.py`
- Create: `tests/unit/evaluation/test_metrics_and_baselines.py`
- Create: `tests/golden/report/required_sections.txt`
- Create: `tests/golden/test_evaluation_report.py`
- Modify: `README.md`

**Interfaces:**

- Produces: `BaselinePublicResult`, `QuestionMetrics`, `AggregateMetrics`, `TurnKEAuditCase`, `ReportDocument`, `compute_metrics()`, `select_turn_ke_audits()`, `load_public_baseline_results()`, and `ReportWriter.build()`.
- Consumes: complete or incomplete KE-only `EvaluationRun`, questions, gold mappings, canonical KE artifacts, retrieval traces, ontology identity, and fixed public baseline records.

- [ ] **Step 1: Write metric, baseline, and report golden tests**

```python
def test_source_metrics_exclude_only_unmappable_gold() -> None:
    mapped = compute_question_metrics(mapped_fixture())
    unmapped = compute_question_metrics(unmapped_fixture())
    assert mapped.source_recall == pytest.approx(0.5)
    assert mapped.complete_evidence is False
    assert unmapped.answer_score == 1.0
    assert unmapped.source_recall is None
    assert unmapped.complete_evidence is None


def test_public_baselines_are_sourced_and_never_ranked(project_root: Path) -> None:
    records = load_public_baseline_results(project_root / "data/baselines/public_results.toml")
    assert {item.system for item in records} == {"mem0", "graphiti", "hindsight", "mempalace"}
    assert all(item.retrieved_on == date(2026, 7, 17) for item in records)
    assert all(item.source_url.startswith("https://") for item in records)
    assert all("not_reproduced" in item.statuses or "not_found" in item.statuses for item in records)
    assert not any(hasattr(item, "rank") for item in records)


def test_report_contains_ke_metrics_audits_and_comparison_warning(report_fixture) -> None:
    documents = ReportWriter.build(report_fixture)
    markdown = document(documents, "report.md").content
    for section in required_sections():
        assert section in markdown
    assert "60/60 answers" in markdown
    assert "60/60 Judge results" in markdown
    assert "不可直接比较" in markdown
    assert "baseline ranking" not in markdown.lower()
    assert "Turn KE 双轨" not in markdown
```

- [ ] **Step 2: Run tests and confirm report modules/data are absent**

Run:

```bash
uv run pytest tests/unit/evaluation/test_metrics_and_baselines.py \
  tests/golden/test_evaluation_report.py -q
```

Expected: missing modules and data fail collection/tests.

- [ ] **Step 3: Freeze the sourced baseline appendix**

Each TOML record includes `system`, `source_url`, `source_commit`, `retrieved_on`, `dataset`, `split`, `metric`, optional `score`, `statuses`, `vendor_self_report`, `reproduction_artifacts`, and `notes`. Include these claims without converting metrics:

```python
BaselineStatus = Literal[
    "public_result", "not_reproduced", "not_found", "not_directly_comparable"
]


class BaselinePublicResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    system: Literal["mem0", "graphiti", "hindsight", "mempalace"]
    source_url: str
    source_commit: str
    retrieved_on: date
    dataset: str
    split: str
    metric: str
    score: float | None = None
    statuses: tuple[BaselineStatus, ...]
    vendor_self_report: bool
    reproduction_artifacts: str
    notes: str
```

```toml
[[results]]
system = "mem0"
source_url = "https://github.com/mem0ai/mem0"
source_commit = "87276ef96879ee406690e640d34060de546560a5"
retrieved_on = "2026-07-17"
dataset = "BEAM"
split = "1M"
metric = "official README score; protocol differs from this demo"
score = 64.1
statuses = ["public_result", "not_reproduced", "not_directly_comparable"]
vendor_self_report = true
reproduction_artifacts = "official README links an open evaluation framework"
notes = "This demo uses a fixed BEAM 100K subset and an independent DeepSeek Judge."

[[results]]
system = "graphiti"
source_url = "https://github.com/getzep/graphiti"
source_commit = "62ff03ac5662d288ebd9f6aafb70d6ae4070c632"
retrieved_on = "2026-07-17"
dataset = "LongMemEval"
split = "repository eval script"
metric = "no complete official result table found in the frozen repository"
statuses = ["not_found"]
vendor_self_report = false
reproduction_artifacts = "tests/evals/eval_e2e_graph_building.py"
notes = "A third-party chart is not treated as an official Graphiti result."
```

Also include Mem0 LoCoMo 91.6, LongMemEval 94.8, BEAM 10M 48.6; Hindsight LongMemEval 94.6; MemPalace LongMemEval R@5 96.6, held-out R@5 98.4, and LoCoMo R@10 88.9 as separate records. Never average, normalize, or order them against KE results.

- [ ] **Step 4: Implement KE-only metrics and traceability checks**

Use these stable output records:

```python
class QuestionMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    question_id: str
    conversation_id: str
    category: QuestionCategory
    answer_score: float
    satisfied_rubrics: int
    rubric_count: int
    factual_error: bool
    unsupported_claim: bool
    abstention_correct: bool | None
    source_recall: float | None
    complete_evidence: bool | None
    citation_valid: bool
    citation_traceable: bool
    source_session_count: int
    used_aggregate: bool
    evidence_tokens: int
    work_usage: UsageRecord
    judge_usage: UsageRecord


class AggregateMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    scope: str
    question_count: int
    answer_score_sum: float
    answer_score_mean: float
    mapped_source_count: int
    source_recall_sum: float
    source_recall_mean: float | None
    complete_evidence_count: int
    citation_valid_count: int
    citation_traceable_count: int
    factual_error_count: int
    unsupported_claim_count: int


class OperationUsageMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    operation: str
    call_count: int
    input_tokens: int
    output_tokens: int
    latency_seconds: float
    provider_cost: float | None


class TurnKEAuditCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    audit_kind: Literal[
        "conversation_first", "tool_event", "unresolved", "lifecycle", "cross_session"
    ]
    conversation_id: str
    exchange_ids: tuple[str, ...]
    raw_records: tuple[JsonObject, ...]
    coverage: tuple[CoverageEntry, ...]
    knowledge_equations: tuple[KnowledgeEquation, ...]
    aggregate_ids: tuple[str, ...] = ()
```

For each question compute:

- Judge answer score and rubric counts.
- factual error, unsupported claim, and abstention correctness.
- source recall and complete evidence only when gold is mapped.
- citation validity: every answer citation is an offered evidence ID.
- citation traceability: every cited Evidence resolves through `system_record_ids` to a KE/AggregateNode and ultimately to valid raw message spans.
- evidence tokens, work/Judge tokens, latency, and provider cost when present.
- number of source Sessions represented and whether an AggregateNode contributed.

Separately aggregate canonical `ModelTrace.usage` by `TraceContext.operation` for Turn draft/bind,
lifecycle, Session aggregation, DAG depth 1/2, Query KE, KE match, common answer, and Judge. Emit
`OperationUsageMetrics`; if any contributing call lacks provider cost, that operation's cost is
`None` rather than a partial sum.

Aggregate overall, by Conversation, and by all ten categories, always emitting numerator and denominator. Incomplete runs retain diagnostics but the report heading/status must say incomplete.

Select deterministic Turn KE audits without a loss score: first Exchange in each Conversation, first tool-event Exchange, first unresolved binding, first contradiction/update pair, and first cross-Session aggregate case. Each `TurnKEAuditCase` contains raw user/assistant/tool text, coverage counts, KE gloss/expression/lifecycle, exact spans, and aggregate closure when applicable.

- [ ] **Step 5: Build canonical report documents and complete snapshot**

```python
class ReportDocument(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: Literal["report.md", "question_results.csv", "metrics.json"]
    media_type: str
    sha256: str
    content: str
```

Extend the evaluation registry with `question_metrics`, `aggregate_metrics`,
`operation_usage_metrics`, `baseline_public_results`, `turn_ke_audits`, and `report_documents`,
each mapped to its exact Pydantic model.

`ReportWriter.build()` returns three sorted, hash-validated records using only stdlib CSV/JSON/Markdown generation. Required Markdown sections are protocol, completeness, ontology identity/mode, concurrency, answer metrics, evidence/citation metrics, six focus categories, cross-Session induction cases, Turn KE raw-to-form audit, failures, public baseline appendix, non-comparability warning, and limitations.

Write a cumulative `evaluation-complete` stage containing inputs, one `evaluation_runs` record,
answers, retrieval traces, Judge results, failures, question metrics, aggregate metrics, baseline
public records, Turn KE audits, and `report_documents`. Commit it only when all 60 answers and
Judges are valid; for an incomplete run, write ignored checkpoints/exports but do not create an
`evaluation-complete` snapshot.

`ke-memory evaluate report` materializes `report.md`, `question_results.csv`, and `metrics.json` under ignored `state_root/exports/<run_id>/` from canonical `ReportDocument` records and verifies hashes.

- [ ] **Step 6: Run report tests and commit**

Run:

```bash
uv run pytest tests/unit/evaluation/test_metrics_and_baselines.py \
  tests/golden/test_evaluation_report.py tests/unit/test_cli.py -q
uv run ruff check src/ke_memory_demo/evaluation tests/unit/evaluation \
  tests/golden/test_evaluation_report.py
```

Expected: deterministic reports parse, required sections appear, and no numerical baseline ranking is emitted.

```bash
git add data/baselines src/ke_memory_demo/evaluation src/ke_memory_demo/pipeline \
  src/ke_memory_demo/cli.py tests/unit/evaluation tests/golden README.md
git commit -m "feat: report traceable KE-only evaluation results"
```

### Task 9: Offline Gate, Live Smoke, Full BEAM Run, and Final Verification

**Files:**

- Create: `scripts/verify_ke_run.py`
- Create after a successful formal run: `docs/results/beam-100k-ke-only-v1.md`
- Modify only implementation files required by verified failures.
- Update after review: `.git/worktrees/ke-memory-demo-implementation/sdd/progress.md`.

**Interfaces:**

- Consumes: Tasks 1-8 plus real work-model, Judge, and ES configuration.
- Produces: a successful live smoke, a complete 385-Exchange/60-question KE-only evaluation, a verified `evaluation-complete` state snapshot, materialized reports, and a small code-repo result pointer.

- [ ] **Step 1: Run the complete offline verification gate**

Run:

```bash
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest -m 'not live_embedding and not live_es and not live_model and not live_baseline and not live_evaluation' -q
git diff --check
```

Expected: every command exits 0 and pytest has zero failures.

- [ ] **Step 2: Run final scope and credential scans**

Run:

```bash
! git grep -nE 'sk-[A-Za-z0-9]+' -- src tests config scripts data README.md
! git grep -nE 'fusion-memory|/public/home/wwb/memory(/|$)' -- src tests config scripts data README.md
! git grep -nE 'run-baselines|baseline adapter|five-system' -- src tests config scripts README.md
```

Expected: no tracked credential, forbidden project reference, or baseline execution path.

- [ ] **Step 3: Run core live preflight before formal ingestion**

Run:

```bash
uv run ke-memory preflight \
  --run-id beam-100k-ke-only-v1 \
  --config-root config \
  --state-root ../ke-memory-demo-state
```

Expected: BEAM counts, clean code commit, current ES identity, work model, state repo, disk, and
concurrency checks pass; embedding is reported disabled. If an environment variable or ES
endpoint/index is absent, stop here and report only the missing variable/check names. Do not
ingest, substitute services, or expose values.

- [ ] **Step 4: Run one-conversation/one-question live smoke**

Run:

```bash
uv run ke-memory evaluate smoke \
  --run-id beam-100k-ke-only-smoke \
  --config-root config \
  --state-root ../ke-memory-demo-state
```

Expected: ontology preflight precedes extraction; one fixed Conversation reaches `ke-ready`; one fixed question produces KE-only evidence, one cited answer, and one valid blinded Judge result. The smoke output is explicitly non-formal and cannot create an `evaluation-complete` snapshot.

- [ ] **Step 5: Build the full ontology-bound `ke-ready` snapshot**

Run:

```bash
uv run ke-memory run-pipeline \
  --run-id beam-100k-ke-only-v1 \
  --config-root config \
  --state-root ../ke-memory-demo-state
```

Expected: directories `4,15,17`, 13 sessions, and 385 Exchanges pass through Turn KE, ordered
lifecycle reconciliation, Session aggregation, per-Conversation semantic DAGs, SQLite rebuild,
and Git `ke-ready`; ontology identity is unchanged and embedding calls equal 0.

- [ ] **Step 6: Run evaluation preflight against the frozen KE snapshot**

Run:

```bash
uv run ke-memory evaluate preflight \
  --run-id beam-100k-ke-only-v1 \
  --config-root config \
  --state-root ../ke-memory-demo-state
```

Expected: the verified `ke-ready` SHA, 60 normalized questions/gold mappings, current ES identity,
work answer client, official Judge client, state HEAD, concurrency values, and secret hygiene all
pass without ingesting or mutating memory.

- [ ] **Step 7: Run the full bounded-concurrent BEAM evaluation**

Run:

```bash
uv run ke-memory evaluate run \
  --run-id beam-100k-ke-only-v1 \
  --config-root config \
  --state-root ../ke-memory-demo-state
```

Expected:

- the frozen `ke-ready` snapshot is used without re-ingestion;
- ontology identity unchanged from preflight through stage promotion;
- embedding calls exactly 0;
- 60 questions, 60 answers, and 60 valid Judge results;
- configured worker limits recorded and never exceeded;
- no baseline process or adapter call;
- status `complete` and an `evaluation-complete` Git snapshot SHA.

Do not lower denominators or publish a complete result if any item is missing. Resume from authenticated checkpoints after transient interruption.

- [ ] **Step 8: Materialize and independently verify reports/snapshot**

Run:

```bash
uv run ke-memory evaluate report \
  --run-id beam-100k-ke-only-v1 \
  --state-root ../ke-memory-demo-state
uv run python scripts/verify_ke_run.py \
  --run-id beam-100k-ke-only-v1 \
  --state-root ../ke-memory-demo-state
```

`verify_ke_run.py` must check snapshot checkout, all stage/artifact hashes, SQLite rebuild counts, ontology mode/identity, 385/60/60/60 denominators, citation resolution to raw spans, ten categories, report-document hashes, baseline source/status fields, zero embedding calls, and absence of secrets/complete ES vocabulary.

- [ ] **Step 9: Write the result pointer and run final review**

Create `docs/results/beam-100k-ke-only-v1.md` containing only run ID, code commit, state snapshot SHA, BEAM SHA/subset, work/Judge model IDs, ontology index identity, concurrency values, completeness counts, links/paths to materialized reports, and a clear exploratory/non-SOTA limitation. Do not duplicate private state artifacts or credentials.

Run the full verification commands from Step 1 again, then request spec-compliance and code-quality review. Record actual commands, counts, snapshot SHA, any missing public baseline result, and live service limitations in the progress ledger.

- [ ] **Step 10: Commit verified code/report pointer changes**

```bash
git add scripts/verify_ke_run.py docs/results README.md src tests config data
git commit -m "test: verify the KE-only BEAM demo"
```

Do not create an empty commit. The separate state repository retains the evaluation artifacts; the code repository keeps only the small result pointer.
