# KE Memory Core Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete, locally testable KE memory pipeline from BEAM exchange ingestion through KE extraction, hierarchical aggregation, orthogonal embedding retrieval, common answering, and Git snapshots.

**Architecture:** The implementation is a Python 3.12 CLI application with immutable Pydantic domain objects, JSONL canonical artifacts, and a rebuildable SQLite index. External systems are injected through small protocols: a read-only Elasticsearch vocabulary, an OpenAI-compatible structured-output client, a local Qwen embedding backend, and a Git snapshot store. The core KE system implements the same `MemorySystem` protocol later used by baseline adapters.

**Tech Stack:** Python 3.12, uv, Pydantic 2, Typer, HTTPX, OpenAI Python SDK, orjson, SQLite, NumPy, sentence-transformers, PyTorch, tiktoken, pytest, pytest-asyncio, respx.

**Design Spec:** `docs/superpowers/specs/2026-07-15-ke-memory-demo-design.md` at approved commit `90a9575f71740b399405e8c568090c282c5290b7`. This is plan 1 of 3 and must complete before the baseline plan.

## Global Constraints

- Work only in `/public/home/wwb/KE_mem/ke-memory-demo`; do not read or import `/public/home/wwb/memory` or any fusion-memory project.
- Treat `/public/home/wwb/KE_mem/KEOL@2970fb331178391fb7db5ccfd090938cdb1dc1be` and `/public/home/wwb/KE_mem/Ontology-Specification@7e17e52d41963676da6658b4131482b26c153e72` as specifications, not runtime dependencies.
- One exchange is one user message plus its following assistant message; intervening tool call/result records are optional attached events.
- Preserve raw message text byte-for-byte after JSON decoding and verify source hashes; KE is never the lossless replacement for raw text.
- Elasticsearch is read-only. A normal miss becomes `unresolved`; outage, authentication failure, schema mismatch, or index drift fails the stage.
- Do not snapshot the Elasticsearch vocabulary. Record only index identity and documents actually bound to KEs.
- Work model: `gpt-5.4` at `https://api.penguinsaichat.dpdns.org/v1`, secret env `KE_MEMORY_WORK_API_KEY`.
- Judge is outside this plan; its fixed model remains `deepseek-v4-pro` at `https://api.deepseek.com/v1`.
- Embedding model: local `Qwen/Qwen3-Embedding-0.6B`, revision `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`, 1024 dimensions, `local_files_only=True`.
- Embedding query template: `Instruct: Given an agent-memory question, retrieve conversation evidence needed to answer it.\nQuery: {question}`.
- KE and embedding candidate generation remain independent until evidence fusion; no internal ablation experiment is added.
- BEAM archive: `/public/home/wwb/datasets/BEAM.zip`, SHA-256 `690106a93ab88dac46e8fef1e84884acc889518424240f57a47428d3efbe6346`; selected directories are exactly `4`, `15`, `17`.
- Evidence input budget is 8192 work-model tokens; answer `max_output_tokens` is 1024.
- Canonical state is JSONL in the separate state Git repository. SQLite is ignored and rebuildable.
- Use TDD for every behavior. Never make a live model, ES, or BEAM call in unit tests.
- Never write API keys to source, tests, command history, traces, reports, Git objects, or plan documents.

---

### Task 1: Package, Configuration, and Secret Hygiene

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.local.example`
- Create: `config/models.toml`
- Create: `config/experiment.toml`
- Create: `config/es_vocab.toml`
- Create: `src/ke_memory_demo/__init__.py`
- Create: `src/ke_memory_demo/settings.py`
- Create: `src/ke_memory_demo/infra/secrets.py`
- Create: `scripts/init_local_secrets.py`
- Create: `tests/conftest.py`
- Create: `tests/unit/test_settings.py`
- Create: `tests/unit/test_secret_hygiene.py`

**Interfaces:**
- Consumes: the exact model, dataset, token-budget, and secret rules in Global Constraints.
- Produces: `AppSettings`, `load_settings(root: Path) -> AppSettings`, and `write_env_local(path: Path, work_key: str, judge_key: str) -> None`.

- [ ] **Step 1: Write failing configuration and permission tests**

```python
from pathlib import Path
import stat

from ke_memory_demo.infra.secrets import write_env_local
from ke_memory_demo.settings import load_settings


def test_settings_keep_secret_values_out_of_toml(project_root: Path):
    settings = load_settings(project_root)
    assert settings.work.model == "gpt-5.4"
    assert settings.work.api_key_env == "KE_MEMORY_WORK_API_KEY"
    assert settings.embedding.dimension == 1024
    assert "sk-" not in (project_root / "config/models.toml").read_text()


def test_write_env_local_is_private_and_complete(tmp_path: Path):
    target = tmp_path / ".env.local"
    write_env_local(target, "work-test-value", "judge-test-value")
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert target.read_text().splitlines() == [
        "KE_MEMORY_WORK_API_KEY=work-test-value",
        "KE_MEMORY_JUDGE_API_KEY=judge-test-value",
    ]
```

- [ ] **Step 2: Run the tests and confirm the package is absent**

Run: `uv run pytest tests/unit/test_settings.py tests/unit/test_secret_hygiene.py -v`

Expected: collection fails with `ModuleNotFoundError: No module named 'ke_memory_demo'`.

- [ ] **Step 3: Add the package metadata and exact non-secret configuration**

```toml
# pyproject.toml
[project]
name = "ke-memory-demo"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = [
  "httpx>=0.28,<1", "numpy>=2.2,<3", "openai>=1.93,<2",
  "orjson>=3.10,<4", "pydantic>=2.11,<3", "python-dotenv>=1.1,<2",
  "sentence-transformers>=5,<6", "tiktoken>=0.9,<1", "torch>=2.7,<3",
  "typer>=0.16,<1",
]

[project.scripts]
ke-memory = "ke_memory_demo.cli:app"

[dependency-groups]
dev = ["pyright>=1.1.403,<2", "pytest>=8.4,<9", "pytest-asyncio>=1,<2", "respx>=0.22,<1", "ruff>=0.12,<1"]

[build-system]
requires = ["hatchling>=1.27,<2"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/ke_memory_demo"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = ["live_embedding", "live_es", "live_model", "live_baseline", "live_evaluation"]

[tool.pyright]
include = ["src", "tests"]
pythonVersion = "3.12"
typeCheckingMode = "strict"

[tool.ruff]
line-length = 100
target-version = "py312"
```

```toml
# config/models.toml
[work]
model = "gpt-5.4"
base_url = "https://api.penguinsaichat.dpdns.org/v1"
api_key_env = "KE_MEMORY_WORK_API_KEY"
temperature = 0.0
max_output_tokens = 4096

[judge]
model = "deepseek-v4-pro"
base_url = "https://api.deepseek.com/v1"
api_key_env = "KE_MEMORY_JUDGE_API_KEY"
temperature = 0.0
max_output_tokens = 2048

[embedding]
model = "Qwen/Qwen3-Embedding-0.6B"
revision = "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
local_path_env = "KE_MEMORY_EMBEDDING_PATH"
dimension = 1024
chunk_tokens = 1024
overlap_tokens = 128
local_files_only = true
```

```toml
# config/es_vocab.toml
endpoint_env = "KE_MEMORY_ES_URL"
index_env = "KE_MEMORY_ES_INDEX"
api_key_env = "KE_MEMORY_ES_API_KEY"
request_timeout_seconds = 30.0

[fields]
canonical = "term"
type = "type"
aliases = "aliases"
relations = "relations"
relation_type = "type"
relation_target_id = "target_id"

[roles]
concept = ["concept", "class", "entity_type"]
individual = ["individual", "instance", "entity"]
operator = ["operator", "relation", "predicate", "action"]
```

```dotenv
# .env.local.example
KE_MEMORY_WORK_API_KEY=
KE_MEMORY_JUDGE_API_KEY=
KE_MEMORY_ES_URL=
KE_MEMORY_ES_INDEX=
KE_MEMORY_ES_API_KEY=
KE_MEMORY_EMBEDDING_PATH=
```

```python
# src/ke_memory_demo/infra/secrets.py
from pathlib import Path
import os


def write_env_local(path: Path, work_key: str, judge_key: str) -> None:
    if not work_key or not judge_key or "\n" in work_key or "\n" in judge_key:
        raise ValueError("Both API keys must be non-empty single-line values")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        payload = (
            f"KE_MEMORY_WORK_API_KEY={work_key}\n"
            f"KE_MEMORY_JUDGE_API_KEY={judge_key}\n"
        ).encode()
        os.write(fd, payload)
    finally:
        os.close(fd)
    os.chmod(path, 0o600)
```

```python
# scripts/init_local_secrets.py
from getpass import getpass
from pathlib import Path
from ke_memory_demo.infra.secrets import write_env_local


write_env_local(
    Path(".env.local"),
    work_key=getpass("Work-model API key: "),
    judge_key=getpass("Judge API key: "),
)
```

Implement `load_settings()` with `tomllib`, immutable Pydantic models, `.env.local` loading through `python-dotenv`, path resolution relative to project root, and explicit errors for missing model path or secret env vars only when the relevant live client is requested. Add `.env.local`, `.venv`, `.baseline-envs`, `var`, `*.sqlite3`, model artifacts, and the sibling state-repo working path to `.gitignore`.

```python
# tests/conftest.py
from pathlib import Path
import pytest


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]
```

- [ ] **Step 4: Lock dependencies and run the tests**

Run: `uv lock && uv run pytest tests/unit/test_settings.py tests/unit/test_secret_hygiene.py -v`

Expected: all tests pass and `uv.lock` is created.

- [ ] **Step 5: Verify the repository cannot stage local secrets**

Run: `git check-ignore .env.local && ! git grep -nE 'sk-[A-Za-z0-9]' -- . ':!docs/superpowers/specs/*' ':!docs/superpowers/plans/*'`

Expected: `.env.local` is reported as ignored; the secret-pattern search returns no matches.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock .gitignore .env.local.example config scripts/init_local_secrets.py src/ke_memory_demo tests/conftest.py tests/unit
git commit -m "build: initialize KE memory project"
```

### Task 2: Immutable Domain Models and Deterministic IDs

**Files:**
- Create: `src/ke_memory_demo/domain/__init__.py`
- Create: `src/ke_memory_demo/domain/conversation.py`
- Create: `src/ke_memory_demo/domain/expressions.py`
- Create: `src/ke_memory_demo/domain/memory.py`
- Create: `src/ke_memory_demo/domain/systems.py`
- Create: `src/ke_memory_demo/core/ids.py`
- Create: `src/ke_memory_demo/core/json.py`
- Create: `tests/unit/domain/test_conversation.py`
- Create: `tests/unit/domain/test_knowledge_equation.py`
- Create: `tests/unit/domain/test_system_protocol.py`

**Interfaces:**
- Consumes: `AppSettings` from Task 1.
- Produces: `Message`, `MessageSpan`, `ToolEvent`, `Exchange`, `Session`, `Conversation`, expression union `Expression`, `KnowledgeEquation`, `CoverageEntry`, `AggregateNode`, `Evidence`, `RunScope`, receipts, `MemorySystem`, `JsonValue`, `canonical_json()`, and `content_id()`.

- [ ] **Step 1: Write failing model-invariant tests**

```python
import pytest

from ke_memory_demo.domain.conversation import Message, MessageSpan
from ke_memory_demo.domain.expressions import IndividualRef, OperatorApplication, OperatorRef
from ke_memory_demo.domain.memory import KnowledgeEquation, Lifecycle, Modality, Polarity


def test_ke_id_is_stable_but_revision_changes_with_lifecycle():
    span = MessageSpan(message_id="m1", start_char=0, end_char=5, text_hash="a" * 64)
    lhs = OperatorApplication(
        operator=OperatorRef(term_id="op:likes", label="likes"),
        arguments=[IndividualRef(term_id="person:u", label="user")],
    )
    ke = KnowledgeEquation.create(
        level="turn", lhs=lhs, rhs=IndividualRef(term_id="x:tea", label="tea"),
        gloss="The user likes tea.", modality=Modality.PREFERENCE,
        polarity=Polarity.POSITIVE, lifecycle=Lifecycle.ACTIVE,
        speaker="user", evidence_refs=[span], produced_in_run_id="run-1",
        produced_in_stage="turn-ke-extracted",
    )
    revised = ke.transition(Lifecycle.SUPERSEDED)
    assert revised.id == ke.id
    assert revised.revision != ke.revision


def test_span_rejects_out_of_range_offsets():
    message = Message(id="m1", role="user", content="abc", source_order=0)
    with pytest.raises(ValueError, match="outside message"):
        message.validate_span(MessageSpan(message_id="m1", start_char=0, end_char=4, text_hash="b" * 64))
```

- [ ] **Step 2: Run the focused tests and confirm missing models**

Run: `uv run pytest tests/unit/domain -v`

Expected: FAIL during import because the domain modules do not exist.

- [ ] **Step 3: Implement discriminated expression and memory models**

```python
# src/ke_memory_demo/domain/expressions.py
from typing import Annotated, Literal
from pydantic import BaseModel, Field


class ConceptRef(BaseModel, frozen=True):
    kind: Literal["concept"] = "concept"
    term_id: str
    label: str


class IndividualRef(BaseModel, frozen=True):
    kind: Literal["individual"] = "individual"
    term_id: str
    label: str


class OperatorRef(BaseModel, frozen=True):
    kind: Literal["operator"] = "operator"
    term_id: str
    label: str


class AssertionRef(BaseModel, frozen=True):
    kind: Literal["assertion"] = "assertion"
    assertion_id: str


AtomicExpression = Annotated[
    ConceptRef | IndividualRef | OperatorRef | AssertionRef,
    Field(discriminator="kind"),
]


class OperatorApplication(BaseModel, frozen=True):
    kind: Literal["application"] = "application"
    operator: OperatorRef
    arguments: list["Expression"]


Expression = Annotated[
    ConceptRef | IndividualRef | OperatorRef | AssertionRef | OperatorApplication,
    Field(discriminator="kind"),
]

OperatorApplication.model_rebuild()
```

Implement enums exactly as specified, forbid extra fields, make all canonical records immutable, and compute logical IDs from schema version + level + canonical expression + evidence/derived references while excluding lifecycle and run-local metadata. Compute `revision` from the complete canonical payload excluding `revision` itself.

- [ ] **Step 4: Define the cross-plan memory-system protocol**

```python
# src/ke_memory_demo/domain/systems.py
from collections.abc import Sequence
from typing import Protocol

from .conversation import Exchange
from .memory import Evidence


class MemorySystem(Protocol):
    system_id: str

    async def prepare(self, scope: "RunScope") -> "AdapterIdentity":
        raise NotImplementedError

    async def ingest(self, exchange: Exchange) -> "IngestReceipt":
        raise NotImplementedError

    async def await_ready(self) -> "ReadinessReceipt":
        raise NotImplementedError

    async def retrieve(self, question: str, evidence_budget_tokens: int) -> Sequence[Evidence]:
        raise NotImplementedError

    async def stats(self) -> "UsageAndLatency":
        raise NotImplementedError

    async def reset(self) -> "ResetReceipt":
        raise NotImplementedError
```

Define the referenced receipt models in the same file as immutable Pydantic objects. `Evidence` must carry `evidence_id`, `text`, source exchange/message IDs, system record IDs, score, rank, channel, metadata, and token count.

- [ ] **Step 5: Run domain tests and static checks**

Run: `uv run pytest tests/unit/domain -v && uv run pyright src/ke_memory_demo/domain src/ke_memory_demo/core`

Expected: all tests pass and pyright reports zero errors.

- [ ] **Step 6: Commit**

```bash
git add src/ke_memory_demo/domain src/ke_memory_demo/core tests/unit/domain
git commit -m "feat: define immutable memory domain models"
```

### Task 3: Deterministic BEAM Selection and Exchange Normalization

**Files:**
- Create: `src/ke_memory_demo/ingestion/__init__.py`
- Create: `src/ke_memory_demo/ingestion/beam.py`
- Create: `src/ke_memory_demo/ingestion/exchange_builder.py`
- Create: `tests/unit/ingestion/test_exchange_builder.py`
- Create: `tests/integration/test_beam_subset.py`

**Interfaces:**
- Consumes: conversation models and `content_id()` from Task 2.
- Produces: ingestion-only `SourceMessage`, `select_beam_directories(archive_sha: str) -> tuple[int, int, int]`, `load_beam_subset(zip_path: Path) -> list[Conversation]`, and `build_exchanges(messages: Iterable[SourceMessage]) -> list[Exchange]`.

- [ ] **Step 1: Write state-machine and real-archive tests**

```python
def test_two_pairs_inside_one_beam_turn_become_two_exchanges():
    source = [
        SourceMessage(id=0, role="user", content="u1"),
        SourceMessage(id=1, role="assistant", content="a1"),
        SourceMessage(id=2, role="user", content="u2"),
        SourceMessage(id=3, role="assistant", content="a2"),
    ]
    exchanges = build_exchanges(source)
    assert [(x.user.content, x.assistant.content) for x in exchanges] == [("u1", "a1"), ("u2", "a2")]


def test_tool_events_attach_without_closing_exchange():
    source = [
        SourceMessage(id=0, role="user", content="run it"),
        SourceMessage(id=1, role="tool_call", content='{"name":"run"}'),
        SourceMessage(id=2, role="tool_result", content='{"ok":true}'),
        SourceMessage(id=3, role="assistant", content="done"),
    ]
    [exchange] = build_exchanges(source)
    assert [event.kind for event in exchange.events] == ["tool_call", "tool_result"]
```

The integration test must assert archive hash, selected directories `(4, 15, 17)`, session counts `(3, 5, 5)`, exchange counts `(106, 136, 143)`, total 385, and 20 questions per conversation without writing the probing questions into exchanges.

- [ ] **Step 2: Run tests and verify the loader is missing**

Run: `uv run pytest tests/unit/ingestion tests/integration/test_beam_subset.py -v`

Expected: FAIL with missing ingestion modules.

- [ ] **Step 3: Implement zip-stream loading and strict pairing**

```python
def select_beam_directories(archive_sha: str) -> tuple[int, int, int]:
    strata = {
        "formal": (1, 2, 3, 4, 5),
        "artifact": (6, 7, 8, 9, 10, 13, 14, 15),
        "human": (11, 12, 16, 17, 18, 19, 20),
    }
    selected: list[int] = []
    for name, ids in strata.items():
        ranked = sorted(
            ids,
            key=lambda directory_id: hashlib.sha256(
                f"ke-memory-demo:BEAM-100K:{archive_sha}:{name}:{directory_id}".encode()
            ).hexdigest(),
        )
        selected.append(ranked[0])
    return tuple(selected)
```

Read JSON directly with `zipfile.ZipFile.open()`. Preserve BEAM directory ID, topic ID, batch number, turn-group index, message ID, original index, role, content, and global ordinal. Reject orphan assistant, repeated source ID, unsupported role, consecutive user, and unclosed exchange with typed `IngestionInvariantError`.

- [ ] **Step 4: Run tests and write a normalized-count manifest**

Run: `uv run pytest tests/unit/ingestion tests/integration/test_beam_subset.py -v`

Expected: all tests pass; the integration test reports 385 exchanges and performs no network access.

- [ ] **Step 5: Commit**

```bash
git add src/ke_memory_demo/ingestion tests/unit/ingestion tests/integration/test_beam_subset.py
git commit -m "feat: normalize the fixed BEAM subset"
```

### Task 4: Canonical Artifact Store and Rebuildable SQLite Index

**Files:**
- Create: `src/ke_memory_demo/storage/__init__.py`
- Create: `src/ke_memory_demo/storage/artifacts.py`
- Create: `src/ke_memory_demo/storage/sqlite_index.py`
- Create: `src/ke_memory_demo/storage/layout.py`
- Create: `tests/unit/storage/test_artifacts.py`
- Create: `tests/integration/test_sqlite_rebuild.py`

**Interfaces:**
- Consumes: immutable domain objects from Task 2 and conversations from Task 3.
- Produces: `ArtifactStore.write_jsonl()`, `ArtifactStore.read_jsonl()`, `ArtifactStore.promote_stage()`, `MemoryIndex.rebuild()`, and symbolic lookup methods used by retrieval.

- [ ] **Step 1: Write atomic-write and rebuild tests**

```python
def test_failed_stage_never_replaces_canonical_artifact(tmp_path: Path):
    store = ArtifactStore(tmp_path)
    store.write_jsonl("run-1", "ingested", "exchanges", [sample_exchange()])
    store.promote_stage("run-1", "ingested")
    original = store.canonical_path("run-1", "ingested", "exchanges").read_bytes()
    with pytest.raises(RuntimeError):
        with store.stage_writer("run-1", "ingested") as writer:
            writer.write("exchanges", [sample_exchange(content="changed")])
            raise RuntimeError("stop")
    assert store.canonical_path("run-1", "ingested", "exchanges").read_bytes() == original
```

The rebuild test writes exchanges, KEs, and aggregates to JSONL, creates SQLite, deletes SQLite, rebuilds, and compares object counts plus ordered IDs.

- [ ] **Step 2: Run tests and observe missing storage classes**

Run: `uv run pytest tests/unit/storage tests/integration/test_sqlite_rebuild.py -v`

Expected: FAIL during import.

- [ ] **Step 3: Implement canonical JSONL and stage promotion**

Use `orjson.OPT_SORT_KEYS`, one object per line, trailing newline, fsync before `os.replace`, and a manifest containing relative path, record count, and SHA-256. Promotion validates every JSON line against its Pydantic type before moving the temporary stage directory into `runs/{run_id}/{stage}/`.

```text
ArtifactStore.write_jsonl(run_id, stage, name, records) -> ArtifactDigest
ArtifactStore.read_jsonl(run_id, stage, name, model) -> Iterator[T]
ArtifactStore.validate_stage(run_id, stage) -> StageManifest
ArtifactStore.promote_stage(run_id, stage) -> StageManifest
```

- [ ] **Step 4: Implement SQLite rebuild and symbolic indexes**

Create tables for messages, exchanges, KEs, ontology bindings, KE relations, aggregate membership, and source spans. Rebuild in a transaction into a temporary database, run `PRAGMA integrity_check`, then atomically replace the cache. Provide exact lookup methods for term ID, normalized unresolved label, operator ID, lifecycle, temporal bounds, and aggregate membership.

- [ ] **Step 5: Run storage tests**

Run: `uv run pytest tests/unit/storage tests/integration/test_sqlite_rebuild.py -v`

Expected: all tests pass; `PRAGMA integrity_check` returns `ok`.

- [ ] **Step 6: Commit**

```bash
git add src/ke_memory_demo/storage tests/unit/storage tests/integration/test_sqlite_rebuild.py
git commit -m "feat: add canonical artifacts and rebuildable index"
```

### Task 5: Real Read-Only Elasticsearch Vocabulary Adapter

**Files:**
- Create: `src/ke_memory_demo/ontology/__init__.py`
- Create: `src/ke_memory_demo/ontology/models.py`
- Create: `src/ke_memory_demo/ontology/protocol.py`
- Create: `src/ke_memory_demo/ontology/elasticsearch.py`
- Create: `tests/unit/ontology/test_elasticsearch_adapter.py`
- Create: `tests/contract/test_ontology_contract.py`

**Interfaces:**
- Consumes: ES settings from Task 1.
- Produces: `OntologyVocabulary` protocol and `ElasticsearchVocabulary` implementing `health`, `resolve_terms`, `fetch_terms`, `fetch_relations`, and `index_identity`.

- [ ] **Step 1: Write request-shape, alias, miss, and outage tests**

```python
@pytest.mark.asyncio
async def test_resolve_term_returns_binding_and_unresolved(mock_es):
    mock_es.search_result([
        {"_id": "c1", "_source": {"term": "triangle", "type": "concept", "aliases": ["triangular shape"], "relations": []}}
    ])
    adapter = ElasticsearchVocabulary(mock_es.settings)
    resolved = await adapter.resolve_terms(["triangle", "unknown phrase"])
    assert resolved[0].document_id == "c1"
    assert resolved[1].status == "unresolved"


@pytest.mark.asyncio
async def test_transport_failure_is_not_an_unresolved_term(mock_es):
    mock_es.raise_timeout()
    with pytest.raises(OntologyUnavailableError):
        await ElasticsearchVocabulary(mock_es.settings).resolve_terms(["triangle"])
```

Also assert recorded requests never target `_bulk`, `_doc`, `_update`, or `_delete_by_query` and that index UUID/mapping hash drift raises `OntologyDriftError`.

- [ ] **Step 2: Run tests and confirm the adapter is absent**

Run: `uv run pytest tests/unit/ontology tests/contract/test_ontology_contract.py -v`

Expected: FAIL during import.

- [ ] **Step 3: Implement the protocol and HTTPX adapter**

```text
OntologyVocabulary.health() -> OntologyHealth
OntologyVocabulary.index_identity() -> IndexIdentity
OntologyVocabulary.resolve_terms(surface_terms) -> list[OntologyBinding]
OntologyVocabulary.fetch_terms(document_ids) -> list[OntologyTerm]
OntologyVocabulary.fetch_relations(document_ids) -> list[OntologyRelation]
```

Use only `GET /_cluster/health`, `GET /{index}/_mapping`, `GET /_cat/indices/{index}?format=json`, `POST /{index}/_search`, and `POST /{index}/_mget`. Search canonical and aliases fields with exact normalized clauses first and a bounded lexical fallback second. Validate source types through the configured mapping; unknown source type becomes an unresolved-role binding, never an invented Concept or Operator.

- [ ] **Step 4: Run contract tests**

Run: `uv run pytest tests/unit/ontology tests/contract/test_ontology_contract.py -v`

Expected: all tests pass with zero write endpoints observed.

- [ ] **Step 5: Commit**

```bash
git add src/ke_memory_demo/ontology tests/unit/ontology tests/contract/test_ontology_contract.py
git commit -m "feat: add read-only Elasticsearch vocabulary"
```

### Task 6: Structured LLM Client, Retry Policy, Usage, and Redacted Traces

**Files:**
- Create: `src/ke_memory_demo/infra/llm.py`
- Create: `src/ke_memory_demo/infra/retry.py`
- Create: `src/ke_memory_demo/infra/redaction.py`
- Create: `src/ke_memory_demo/infra/telemetry.py`
- Create: `tests/unit/infra/test_llm.py`
- Create: `tests/unit/infra/test_redaction.py`

**Interfaces:**
- Consumes: work model settings and secret lookup from Task 1, artifact store from Task 4.
- Produces: `StructuredModelClient.complete(model_type, messages, trace_context) -> T`, `UsageRecord`, `redact_tree()`, and typed transient/permanent errors.

- [ ] **Step 1: Write retry, repair, and redaction tests**

```python
class ExampleOutput(BaseModel):
    value: int


@pytest.mark.asyncio
async def test_schema_error_gets_two_repairs_then_succeeds(fake_chat):
    fake_chat.queue('{"wrong":1}', '{"value":"bad"}', '{"value":3}')
    result = await fake_chat.client.complete(ExampleOutput, [{"role": "user", "content": "return value"}], trace_context("x"))
    assert result.value == 3
    assert fake_chat.call_count == 3


def test_redaction_removes_headers_and_known_secret_values():
    value = {"Authorization": "Bearer secret-value", "nested": {"api_key": "secret-value"}}
    assert redact_tree(value, known_secrets={"secret-value"}) == {
        "Authorization": "[REDACTED]", "nested": {"api_key": "[REDACTED]"}
    }
```

- [ ] **Step 2: Run tests and verify failure**

Run: `uv run pytest tests/unit/infra/test_llm.py tests/unit/infra/test_redaction.py -v`

Expected: FAIL during import.

- [ ] **Step 3: Implement the exact retry state machine**

Use one initial structured request plus at most two repair requests for schema errors. For 429, timeout, and recoverable 5xx, use at most four total transport attempts, honor `Retry-After`, otherwise delay 1, 2, and 4 seconds. Authentication, missing model, content policy, and invariant errors are permanent. Inject sleep and clock functions so tests do not wait.

Use `AsyncOpenAI(base_url=settings.base_url, api_key=settings.api_key)`; omit `temperature` for `gpt-5*`, `o1*`, and `o3*` models. Request JSON schema when accepted by preflight and JSON object mode otherwise, then always validate with Pydantic. Save redacted request/response, request ID, actual model, latency, and usage in the temporary stage trace area before promotion.

- [ ] **Step 4: Run tests and type checking**

Run: `uv run pytest tests/unit/infra -v && uv run pyright src/ke_memory_demo/infra`

Expected: all tests pass and pyright reports zero errors.

- [ ] **Step 5: Commit**

```bash
git add src/ke_memory_demo/infra tests/unit/infra
git commit -m "feat: add structured model client and safe traces"
```

### Task 7: Turn KE Extraction, Coverage, and Lifecycle Maintenance

**Files:**
- Create: `prompts/turn_ke/system.md`
- Create: `prompts/turn_ke/repair.md`
- Create: `prompts/lifecycle_match/system.md`
- Create: `src/ke_memory_demo/extraction/__init__.py`
- Create: `src/ke_memory_demo/extraction/schemas.py`
- Create: `src/ke_memory_demo/extraction/coverage.py`
- Create: `src/ke_memory_demo/extraction/turn_ke.py`
- Create: `src/ke_memory_demo/extraction/lifecycle.py`
- Create: `tests/unit/extraction/test_coverage.py`
- Create: `tests/unit/extraction/test_turn_ke.py`
- Create: `tests/unit/extraction/test_lifecycle.py`

**Interfaces:**
- Consumes: `Exchange`, KE models, `OntologyVocabulary`, `StructuredModelClient`, and artifact store.
- Produces: `TurnExtractionResult`, `TurnKEExtractor.extract(exchange)`, `CoverageValidator.validate()`, and `LifecycleMaintainer.apply(existing, new)`.

- [ ] **Step 1: Write failing extraction and complete-coverage tests**

```python
@pytest.mark.asyncio
async def test_extractor_accepts_only_es_candidates_and_preserves_unresolved(fake_llm, fake_vocab):
    fake_vocab.bind("triangle", document_id="c7", role="concept")
    fake_llm.return_turn_ke(preference_for="triangle", unresolved_term="special theorem")
    result = await TurnKEExtractor(fake_llm, fake_vocab).extract(sample_exchange())
    ids = {binding.document_id for ke in result.knowledge_equations for binding in ke.ontology_bindings if binding.document_id}
    assert ids == {"c7"}
    assert any(binding.status == "unresolved" for ke in result.knowledge_equations for binding in ke.ontology_bindings)


def test_coverage_requires_every_codepoint_exactly_classified():
    message = Message(id="m", role="user", content="abc", source_order=0)
    with pytest.raises(CoverageInvariantError, match="gap"):
        CoverageValidator.validate(message, [CoverageEntry(message_id="m", start_char=0, end_char=2, status="represented")])
```

- [ ] **Step 2: Run tests and verify missing extractor**

Run: `uv run pytest tests/unit/extraction -v`

Expected: FAIL during import.

- [ ] **Step 3: Implement the two-pass extraction contract**

Pass 1 asks the LLM for information units, surface terms, expression roles, modality, polarity, temporal fields, exact spans, and full coverage labels. Query ES for all unique surface terms. Pass 2 gives the LLM only returned candidate IDs plus unresolved markers and asks for final KEs. Program validation rejects nonexistent ES IDs, mismatched span text hashes, expression-role mismatches, gaps/conflicting coverage, dangling assertion refs, and unsupported lifecycle values.

```python
class TurnKEExtractor:
    async def extract(self, exchange: Exchange) -> TurnExtractionResult:
        draft = await self._model.complete(TurnKEDraft, self._draft_messages(exchange), self._trace(exchange, "draft"))
        bindings = await self._vocabulary.resolve_terms(sorted(set(draft.surface_terms)))
        final = await self._model.complete(TurnKEOutput, self._binding_messages(exchange, draft, bindings), self._trace(exchange, "bind"))
        return self._validator.build_result(exchange, final, bindings)
```

- [ ] **Step 4: Implement lifecycle rules**

Candidate selection uses normalized subject, operator, temporal overlap, modality, and polarity. The matcher may emit `contradicts`, `updates`, or `no_match`. Contradiction creates bidirectional links and leaves both visible; update appends a superseded revision for the old KE; explicit retraction appends a retracted revision. Every transition preserves the prior revision in canonical JSONL.

- [ ] **Step 5: Run extraction tests**

Run: `uv run pytest tests/unit/extraction -v`

Expected: all tests pass, including full Unicode span coverage and contradiction/update cases.

- [ ] **Step 6: Commit**

```bash
git add prompts/turn_ke prompts/lifecycle_match src/ke_memory_demo/extraction tests/unit/extraction
git commit -m "feat: extract traceable turn knowledge equations"
```

### Task 8: Session Induction and Cross-Session Semantic DAG

**Files:**
- Create: `prompts/session_aggregation/system.md`
- Create: `prompts/semantic_dag/system.md`
- Create: `src/ke_memory_demo/aggregation/__init__.py`
- Create: `src/ke_memory_demo/aggregation/session.py`
- Create: `src/ke_memory_demo/aggregation/candidates.py`
- Create: `src/ke_memory_demo/aggregation/dag.py`
- Create: `src/ke_memory_demo/aggregation/validation.py`
- Create: `tests/unit/aggregation/test_session.py`
- Create: `tests/unit/aggregation/test_dag.py`

**Interfaces:**
- Consumes: Turn KEs, coverage, exchanges, model client, and artifact store.
- Produces: `SessionAggregator.aggregate(session) -> SessionMemory`, `SemanticDAGBuilder.build(session_memories) -> SemanticDAG`, and `validate_evidence_closure()`.

- [ ] **Step 1: Write failing evidence-closure and cycle tests**

```python
def test_aggregate_requires_raw_evidence_closure():
    node = aggregate_node(member_refs=["ke:missing"], derived_from=["ke:missing"])
    with pytest.raises(AggregationInvariantError, match="missing member"):
        validate_semantic_dag([node], known_kes={})


def test_cycle_is_rejected_even_when_all_nodes_exist():
    a = aggregate_node(id="a", member_refs=["b"])
    b = aggregate_node(id="b", member_refs=["a"])
    with pytest.raises(AggregationInvariantError, match="cycle"):
        validate_semantic_dag([a, b], known_kes={})
```

- [ ] **Step 2: Run tests and verify failure**

Run: `uv run pytest tests/unit/aggregation -v`

Expected: FAIL during import.

- [ ] **Step 3: Implement session aggregation**

Give the model Turn KEs, coverage summaries, and only the source text required by those spans. Require a session summary, session KEs, unresolved conflicts, constraints, and open questions. Reject every derived assertion without lower-level references or complete message-span closure.

- [ ] **Step 4: Implement depth-bounded overlapping DAG construction**

Generate first-level candidates using shared normalized subject, operator, explicit references, and temporal adjacency only; do not call embeddings. Allow node kinds `Task`, `Project`, `Topic`, `Goal`, `EventChain`, `EntityTimeline`, `Decision`, `State`, `Constraint`, `Preference`, `Procedure`, `Pattern`, `Issue`, and `Other`. Run one optional second-level pass and reject depth greater than 2. Use deterministic topological sort and Tarjan/DFS cycle detection.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/unit/aggregation -v`

Expected: all tests pass and a fixture KE can belong to multiple aggregate nodes.

- [ ] **Step 6: Commit**

```bash
git add prompts/session_aggregation prompts/semantic_dag src/ke_memory_demo/aggregation tests/unit/aggregation
git commit -m "feat: build traceable semantic memory DAG"
```

### Task 9: Local Qwen Embedding and Exact Vector Index

**Files:**
- Create: `src/ke_memory_demo/embedding/__init__.py`
- Create: `src/ke_memory_demo/embedding/fingerprint.py`
- Create: `src/ke_memory_demo/embedding/chunking.py`
- Create: `src/ke_memory_demo/embedding/qwen.py`
- Create: `src/ke_memory_demo/embedding/index.py`
- Create: `tests/unit/embedding/test_chunking.py`
- Create: `tests/unit/embedding/test_index.py`
- Create: `tests/integration/test_local_embedding.py`

**Interfaces:**
- Consumes: embedding settings, exchanges, KEs, sessions, aggregates, and artifact store.
- Produces: `EmbeddingBackend`, `QwenEmbeddingBackend`, `EmbeddingDocument`, `ExactVectorIndex`, and deterministic model fingerprint.

- [ ] **Step 1: Write failing deterministic chunk and cosine tests**

```python
def test_chunks_use_1024_tokens_and_128_overlap(fake_tokenizer):
    chunks = chunk_text("x" * 2300, fake_tokenizer, chunk_tokens=1024, overlap_tokens=128)
    assert [chunk.token_start for chunk in chunks] == [0, 896, 1792]
    assert all(chunk.token_end - chunk.token_start <= 1024 for chunk in chunks)


def test_exact_index_returns_source_provenance():
    index = ExactVectorIndex(dimension=2)
    index.add(EmbeddingDocument(id="d1", text="alpha", vector=[1.0, 0.0], source_exchange_ids=["e1"]))
    [hit] = index.search([1.0, 0.0], limit=1)
    assert hit.document_id == "d1"
    assert hit.source_exchange_ids == ["e1"]
```

- [ ] **Step 2: Run unit tests and verify missing implementation**

Run: `uv run pytest tests/unit/embedding -v`

Expected: FAIL during import.

- [ ] **Step 3: Implement local-only model load and fingerprint**

```python
model = SentenceTransformer(
    str(settings.local_path),
    local_files_only=True,
    trust_remote_code=True,
)
if model.get_sentence_embedding_dimension() != 1024:
    raise EmbeddingInvariantError("Qwen3 embedding dimension must be 1024")
```

Fingerprint sorted relative paths and SHA-256 values for config, tokenizer, and weight files. Refuse symlinks escaping the configured model root. Encode query text with the fixed instruction template, documents without instruction, use float32, and L2-normalize every vector. Reject NaN, infinity, zero norm, dimension mismatch, or a changed fingerprint.

- [ ] **Step 4: Implement document generation and exact cosine search**

Generate documents for raw exchange chunks, Turn KE glosses, Session summaries/KEs, and aggregate summaries/KEs. Save document metadata JSONL and vectors as deterministic `.npy` arrays ordered by document ID. Search by matrix multiplication of normalized vectors and break score ties by document ID.

- [ ] **Step 5: Run unit and opt-in local integration tests**

Run: `uv run pytest tests/unit/embedding -v`

Expected: all unit tests pass.

Run after `KE_MEMORY_EMBEDDING_PATH` is set: `uv run pytest tests/integration/test_local_embedding.py -v -m live_embedding`

Expected: one 1024-dimensional finite vector and a stable model fingerprint. This command performs no network request.

- [ ] **Step 6: Commit**

```bash
git add src/ke_memory_demo/embedding tests/unit/embedding tests/integration/test_local_embedding.py
git commit -m "feat: add orthogonal local Qwen retrieval"
```

### Task 10: Query KE, LLM Match, Evidence Fusion, and Common Answering

**Files:**
- Create: `prompts/query_ke/system.md`
- Create: `prompts/ke_match/system.md`
- Create: `prompts/answer/system.md`
- Create: `src/ke_memory_demo/retrieval/__init__.py`
- Create: `src/ke_memory_demo/retrieval/query.py`
- Create: `src/ke_memory_demo/retrieval/symbolic.py`
- Create: `src/ke_memory_demo/retrieval/matcher.py`
- Create: `src/ke_memory_demo/retrieval/fusion.py`
- Create: `src/ke_memory_demo/retrieval/tokens.py`
- Create: `src/ke_memory_demo/answering.py`
- Create: `src/ke_memory_demo/systems/ke_memory.py`
- Create: `tests/unit/retrieval/test_orthogonality.py`
- Create: `tests/unit/retrieval/test_fusion.py`
- Create: `tests/unit/test_ke_memory_system.py`

**Interfaces:**
- Consumes: SQLite symbolic index, ontology, model client, vector index, artifacts, and domain protocol.
- Produces: `QueryKEExtractor`, `SymbolicRetriever`, `LLMMatcher`, `EvidenceFusion`, `AnswerService`, and `KEMemorySystem` implementing `MemorySystem`.

- [ ] **Step 1: Write failing orthogonality and evidence-budget tests**

```python
@pytest.mark.asyncio
async def test_symbolic_path_never_receives_embedding_scores(spies):
    await RetrievalCoordinator(spies.symbolic, spies.embedding, spies.matcher, spies.fusion).retrieve("question")
    assert spies.symbolic.received_fields == {"query_ke"}
    assert spies.matcher.received_fields == {"query_ke", "symbolic_candidates"}
    assert spies.embedding.received_fields == {"question"}


def test_fusion_keeps_conflict_sides_under_budget(token_counter):
    evidence = EvidenceFusion(token_counter, budget=20).pack(conflict_fixture())
    assert {item.metadata["conflict_side"] for item in evidence} == {"first", "second"}
    assert sum(item.token_count for item in evidence) <= 20
```

- [ ] **Step 2: Run tests and verify failure**

Run: `uv run pytest tests/unit/retrieval tests/unit/test_ke_memory_system.py -v`

Expected: FAIL during import.

- [ ] **Step 3: Implement query and symbolic retrieval**

Extract Query KE with the same expression schema and ES resolver as Turn KE, but store it only in the request trace. Search term IDs, unresolved normalized labels, operators, lifecycle, temporal bounds, and aggregate membership. Pass only symbolic candidates to the matcher, which returns `exact`, `equivalent`, `subsumes`, `related`, `contradicts`, `updates`, `temporal_precedes`, `temporal_follows`, or `no_match` with candidate ID, confidence, and reason.

- [ ] **Step 4: Implement deterministic fusion and answer service**

Union symbolic/matched and embedding candidates at fusion, deduplicate by message span, retain channel provenance, add minimal raw closure for derived nodes, prioritize required conflict sides/time points/session diversity, then pack to exactly at most 8192 `o200k_base` tokens. The answer service sends the fixed prompt, question, and packed evidence to `gpt-5.4` with max output 1024 and returns answer plus citations and usage.

- [ ] **Step 5: Implement `KEMemorySystem`**

Map protocol methods to staged core operations: `prepare` creates isolated run state; `ingest` stores one Exchange; `await_ready` requires successful `embedding-ready`; `retrieve` calls the coordinator; `stats` aggregates usage/latency; `reset` removes only the current ignored runtime cache, never canonical Git snapshots.

- [ ] **Step 6: Run retrieval and protocol tests**

Run: `uv run pytest tests/unit/retrieval tests/unit/test_ke_memory_system.py -v`

Expected: all tests pass; spies prove the two candidate paths meet only in fusion.

- [ ] **Step 7: Commit**

```bash
git add prompts/query_ke prompts/ke_match prompts/answer src/ke_memory_demo/retrieval src/ke_memory_demo/answering.py src/ke_memory_demo/systems tests/unit/retrieval tests/unit/test_ke_memory_system.py
git commit -m "feat: add KE retrieval fusion and answering"
```

### Task 11: Git Snapshots, Stage CLI, and Golden End-to-End Pipeline

**Files:**
- Create: `src/ke_memory_demo/snapshots/__init__.py`
- Create: `src/ke_memory_demo/snapshots/git_store.py`
- Create: `src/ke_memory_demo/pipeline.py`
- Create: `src/ke_memory_demo/cli.py`
- Create: `tests/unit/snapshots/test_git_store.py`
- Create: `tests/golden/data/multi_session_conversation.json`
- Create: `tests/golden/test_memory_pipeline.py`
- Modify: `pyproject.toml`
- Create: `README.md`

**Interfaces:**
- Consumes: every core service from Tasks 1-10.
- Produces: `GitSnapshotStore`, resumable `MemoryPipeline`, and commands `preflight`, `ingest`, `extract-turn-ke`, `aggregate-session`, `build-semantic-dag`, `embed`, `retrieve`, and `verify-snapshot`.

- [ ] **Step 1: Write failing snapshot and golden workflow tests**

```python
def test_snapshot_id_is_commit_sha_and_not_embedded_in_manifest(tmp_path: Path):
    store = GitSnapshotStore.init(tmp_path / "state")
    snapshot = store.commit_stage(sample_manifest(stage="ingested"))
    assert len(snapshot.snapshot_id) == 40
    assert snapshot.snapshot_id == store.head()
    assert snapshot.snapshot_id not in (tmp_path / "state/runs/run-1/ingested/manifest.json").read_text()


@pytest.mark.asyncio
async def test_golden_pipeline_traces_cross_session_update_to_raw_spans(golden_pipeline):
    result = await golden_pipeline.run_all()
    assert result.exchange_count > 1
    assert result.dag.max_depth <= 2
    current = result.find_ke("current project status")
    assert current.supersedes
    assert result.resolve_raw_spans(current.id)
```

- [ ] **Step 2: Run tests and verify missing snapshot/pipeline code**

Run: `uv run pytest tests/unit/snapshots tests/golden/test_memory_pipeline.py -v`

Expected: FAIL during import.

- [ ] **Step 3: Implement Git snapshot semantics**

Initialize the sibling state repository with branch `main`, local non-secret commit identity, and normalized Git config. Validate and commit only a completed stage. Derive `snapshot_id` from `git rev-parse HEAD`; manifests record parent SHA and logical stage ID but never their own commit SHA. Support checkout verification in a temporary worktree and compare manifest hashes. Never commit SQLite, `.env.local`, complete ES vocabulary, or unredacted traces.

Allow only the exact successful stage names `ingested`, `turn-ke-extracted`, `session-aggregated`, `semantic-dag-built`, `embedding-ready`, and `evaluation-complete`; core commands create the first five and the evaluation plan creates the last. Re-read Elasticsearch index identity immediately before and after every stage that resolves ontology terms and fail promotion on drift.

- [ ] **Step 4: Implement resumable pipeline and Typer commands**

Each command accepts `--run-id`, `--config-root`, and `--state-root`; refuses to skip prerequisites; validates artifacts before snapshot; exits nonzero on partial completion. `preflight` verifies BEAM hash, local model fingerprint, required secrets, ES identity, model structured output, state repo, and disk space without writing memory artifacts.

- [ ] **Step 5: Build the golden fixture and run the full local suite**

The fixture must contain preference, a project spread across sessions, contradiction, explicit update, ordered events, unresolved term, and tool call/result. Use fake model/ES/embedding clients with deterministic outputs.

Run: `uv run pytest tests/unit tests/contract tests/integration/test_beam_subset.py tests/integration/test_sqlite_rebuild.py tests/golden -v`

Expected: all non-live tests pass with no network access.

- [ ] **Step 6: Verify CLI help and snapshot rebuild**

Run: `state_root=var/golden-state; snapshot=$(git -C "$state_root" rev-parse HEAD); uv run ke-memory --help && uv run ke-memory verify-snapshot --state-root "$state_root" --snapshot "$snapshot"`

Expected: all stage commands appear; verification reports matching artifact counts and hashes after rebuilding SQLite.

- [ ] **Step 7: Commit**

```bash
git add src/ke_memory_demo/snapshots src/ke_memory_demo/pipeline.py src/ke_memory_demo/cli.py tests/unit/snapshots tests/golden pyproject.toml README.md
git commit -m "feat: complete snapshot-backed KE memory pipeline"
```

### Task 12: Core Plan Verification Gate

**Files:**
- Modify only files required to fix findings from the commands below.

**Interfaces:**
- Consumes: Tasks 1-11.
- Produces: a reviewed core contract ready for baseline-plan consumers.

- [ ] **Step 1: Run formatting, lint, types, and all non-live tests**

Run: `uv run ruff format --check . && uv run ruff check . && uv run pyright && uv run pytest -m 'not live_embedding and not live_es and not live_model' -v`

Expected: every command exits 0 and pytest reports zero failures.

- [ ] **Step 2: Run secret and forbidden-reference scans**

Run: `! git grep -nE 'sk-[A-Za-z0-9]|/public/home/wwb/memory(/|$)|fusion-memory' -- ':!docs/superpowers/specs/*' ':!docs/superpowers/plans/*'`

Expected: no matches.

- [ ] **Step 3: Verify core acceptance counts without external services**

Run: `uv run ke-memory ingest --run-id beam-count-check --config-root config --state-root var/count-state`

Expected: output reports directories `4,15,17`, 13 sessions, 385 exchanges, 60 probing questions excluded from ingestion, and matching archive hash.

- [ ] **Step 4: Commit verification fixes, if any**

```bash
git add -A
git commit -m "test: verify KE memory core pipeline"
```

Do not create an empty commit when no files changed. Record the successful command output in the implementation handoff.
