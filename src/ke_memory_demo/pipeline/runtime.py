from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
import errno
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time
from typing import Literal, TypeVar, cast
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, ValidationError

from ke_memory_demo.core.json import canonical_json
from ke_memory_demo.domain import (
    AggregateNode,
    Conversation,
    Evidence,
    Exchange,
    KnowledgeEquation,
    RunScope,
)
from ke_memory_demo.evaluation.preflight import EvaluationPreflight, PreflightCheckFailure
from ke_memory_demo.evaluation.questions import normalize_questions
from ke_memory_demo.infra.llm import StructuredModelClient
from ke_memory_demo.infra.telemetry import (
    InMemoryTraceRecorder,
    ModelTrace,
    TraceContext,
    TraceRecorder,
    UsageRecord,
)
from ke_memory_demo.ontology import ElasticsearchVocabulary
from ke_memory_demo.retrieval import (
    CanonicalSymbolicRecordSource,
    DisabledEmbeddingRetriever,
    EvidenceFusion,
    LLMMatcher,
    O200KTokenCounter,
    QueryKEExtractor,
    RetrievalCoordinator,
    SymbolicRetriever,
    TokenCounter,
)
from ke_memory_demo.settings import AppSettings, ModelSettings, load_settings
from ke_memory_demo.snapshots import GitSnapshotStore
from ke_memory_demo.storage import ArtifactStore, MemoryIndex, validate_storage_name
from ke_memory_demo.systems import (
    KE_MEMORY_SYSTEM_ID,
    KE_READY_STAGE,
    KEMemorySystem,
    PreparedRunState,
    StageReadiness,
    StoredExchange,
)

from .checkpoints import CheckpointStore
from .models import PIPELINE_ARTIFACT_REGISTRY, PipelineRunManifest, PipelineStage
from .runner import MemoryPipeline, PipelineInvariantError


Sleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]
SnapshotModelT = TypeVar("SnapshotModelT", bound=BaseModel)
_GIT_SHA = re.compile(r"[0-9a-f]{40}", flags=re.ASCII)
_SK_CREDENTIAL = re.compile(rb"sk-[A-Za-z0-9_-]{12,}", flags=re.ASCII)
_APPROVED_SPEC_PATH = Path("docs/superpowers/specs/2026-07-17-ke-only-evaluation-design.md")
_APPROVED_SPEC_SHA256 = "192bf8384185eaa014634ea61fee18c2ab35220bd23037c78da959aca8ca73cb"
_APPROVED_PLAN_PATH = Path("docs/superpowers/plans/2026-07-17-ke-only-completion-implementation.md")
_APPROVED_PLAN_SHA256 = "47fcf0e87ee7738a190c8cb3a9d3b253e35f01a446c465d2f47d024c216e680b"
_FIXED_DATASET_SHA256 = "690106a93ab88dac46e8fef1e84884acc889518424240f57a47428d3efbe6346"
_FIXED_DIRECTORIES = (4, 15, 17)
_FIXED_SESSIONS = 13
_FIXED_EXCHANGES = 385
_FIXED_QUESTIONS = 60


class RuntimeInvariantError(RuntimeError):
    """Real runtime composition or exact-snapshot hydration failed."""


class _EvaluationProbeResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ready: Literal[True]


class _RuntimeStructuredModelClient(StructuredModelClient):
    def __init__(
        self,
        settings: ModelSettings,
        *,
        client: object,
        supports_json_schema: bool,
        trace_recorder: TraceRecorder,
        known_secrets: Iterable[str] = (),
        sleep: Sleep = asyncio.sleep,
        clock: Clock = time.time,
        _owns_client: bool = False,
    ) -> None:
        self._runtime_trace_recorder = trace_recorder
        super().__init__(
            settings,
            client=client,
            supports_json_schema=supports_json_schema,
            trace_recorder=trace_recorder,
            known_secrets=known_secrets,
            sleep=sleep,
            clock=clock,
            _owns_client=_owns_client,
        )

    @property
    def trace_records(self) -> tuple[ModelTrace, ...]:
        raw = getattr(self._runtime_trace_recorder, "records", ())
        if not isinstance(raw, Sequence):
            raise RuntimeInvariantError("runtime trace recorder exposed invalid records")
        return tuple(ModelTrace.model_validate(item) for item in cast(Sequence[object], raw))


class _RecorderUsageSource:
    def __init__(self, recorder: InMemoryTraceRecorder) -> None:
        self._recorder = recorder

    def usage_records(self, scope: RunScope) -> tuple[UsageRecord, ...]:
        del scope
        return self._recorder.usage_records


class _ConversationRuntimePort:
    def __init__(
        self,
        *,
        conversation: Conversation,
        current_knowledge_equations: Sequence[KnowledgeEquation],
        aggregates: Sequence[AggregateNode],
        settings: AppSettings,
        ontology: ElasticsearchVocabulary,
        work_model: StructuredModelClient,
        token_counter: TokenCounter,
        run_id: str,
    ) -> None:
        self._conversation = conversation
        self._exchanges = tuple(
            exchange for session in conversation.sessions for exchange in session.exchanges
        )
        self._exchange_by_id = {item.id: item for item in self._exchanges}
        self._current_kes = tuple(current_knowledge_equations)
        self._aggregates = tuple(aggregates)
        self._settings = settings
        self._ontology = ontology
        self._work_model = work_model
        self._token_counter = token_counter
        self._run_id = run_id
        self._ingested: set[str] = set()
        self._coordinator: RetrievalCoordinator | None = None

    async def prepare(self, scope: RunScope, runtime_cache: Path) -> PreparedRunState:
        self._validate_scope(scope)
        index = MemoryIndex(runtime_cache / "memory.sqlite3")
        stats = index.rebuild(self._exchanges, self._current_kes, self._aggregates)
        records = CanonicalSymbolicRecordSource(
            self._exchanges,
            self._current_kes,
            self._aggregates,
        )
        query_extractor = QueryKEExtractor(
            self._work_model,
            self._ontology,
            run_id=self._run_id,
        )
        symbolic = SymbolicRetriever(
            index,
            records,
            query_extractor=query_extractor,
        )
        matcher = LLMMatcher(self._work_model, run_id=self._run_id)
        fusion = EvidenceFusion(
            self._token_counter,
            budget=self._settings.retrieval.evidence_budget_tokens,
        )
        self._coordinator = RetrievalCoordinator(
            symbolic,
            DisabledEmbeddingRetriever(),
            matcher,
            fusion,
        )
        return PreparedRunState(
            metadata={
                "conversation_id": self._conversation.id,
                "embedding_enabled": False,
                "index_stats": stats.model_dump(mode="json"),
            }
        )

    async def ingest(self, scope: RunScope, exchange: Exchange) -> StoredExchange:
        self._validate_scope(scope)
        canonical = self._exchange_by_id.get(exchange.id)
        if canonical is None or canonical != exchange:
            raise RuntimeInvariantError(
                f"runtime Exchange is outside Conversation scope: {exchange.id}"
            )
        self._ingested.add(exchange.id)
        return StoredExchange(
            record_ids=(
                exchange.id,
                exchange.user.id,
                *(event.id for event in exchange.events),
                exchange.assistant.id,
            ),
            metadata={"conversation_id": self._conversation.id},
        )

    async def await_ready(
        self,
        scope: RunScope,
        required_stage: str,
    ) -> StageReadiness:
        self._validate_scope(scope)
        if required_stage != KE_READY_STAGE:
            raise RuntimeInvariantError("Conversation runtime only supports ke-ready")
        pending = len(set(self._exchange_by_id).difference(self._ingested))
        return StageReadiness(
            stage=KE_READY_STAGE,
            successful=pending == 0,
            pending_count=pending,
            metadata={
                "conversation_id": self._conversation.id,
                "embedding_enabled": False,
            },
        )

    async def retrieve(
        self,
        scope: RunScope,
        question: str,
        evidence_budget_tokens: int,
    ) -> Sequence[Evidence]:
        self._validate_scope(scope)
        if self._coordinator is None:
            raise RuntimeInvariantError("Conversation retrieval runtime is not prepared")
        return await self._coordinator.retrieve(question, evidence_budget_tokens)

    def _validate_scope(self, scope: RunScope) -> None:
        if (
            scope.run_id != self._run_id
            or scope.conversation_id != self._conversation.id
            or scope.system_id != KE_MEMORY_SYSTEM_ID
        ):
            raise RuntimeInvariantError("runtime scope does not match its Conversation")


class RuntimeFactory:
    def __init__(
        self,
        *,
        settings: AppSettings,
        artifacts: ArtifactStore,
        snapshots: GitSnapshotStore,
        ontology: ElasticsearchVocabulary,
        work_model: StructuredModelClient,
        work_recorder: InMemoryTraceRecorder,
        code_commit: str,
    ) -> None:
        self.settings = settings
        self.artifacts = artifacts
        self.snapshots = snapshots
        self.ontology = ontology
        self.work_model = work_model
        self._work_recorder = work_recorder
        self._code_commit = code_commit
        self._state_root = artifacts.root
        self._token_counter = O200KTokenCounter()
        self._evaluation_clients: tuple[StructuredModelClient, StructuredModelClient] | None = None

    @classmethod
    def from_paths(cls, config_root: Path, state_root: Path) -> RuntimeFactory:
        settings = load_settings(config_root)
        artifacts = ArtifactStore(state_root, registry=PIPELINE_ARTIFACT_REGISTRY)
        snapshots = GitSnapshotStore.init(artifacts.root, artifacts)
        ontology = ElasticsearchVocabulary.from_app_settings(settings)
        work_secret = settings.require_work_api_key()
        work_recorder = InMemoryTraceRecorder()
        work_model = cast(
            _RuntimeStructuredModelClient,
            _RuntimeStructuredModelClient.from_model_settings(
                settings.work,
                api_key=work_secret,
                supports_json_schema=True,
                trace_recorder=work_recorder,
            ),
        )
        return cls(
            settings=settings,
            artifacts=artifacts,
            snapshots=snapshots,
            ontology=ontology,
            work_model=work_model,
            work_recorder=work_recorder,
            code_commit=_code_commit(settings.project_root),
        )

    def build_pipeline(self, run_id: str) -> MemoryPipeline:
        return MemoryPipeline(
            self.settings,
            self.artifacts,
            self.snapshots,
            CheckpointStore(self._state_root, run_id),
            self.ontology,
            self.work_model,
            code_commit=self._code_commit,
        )

    def build_evaluation_clients(
        self,
    ) -> tuple[StructuredModelClient, StructuredModelClient]:
        if self._evaluation_clients is not None:
            return self._evaluation_clients
        answer_settings = self.settings.work.model_copy(
            update={"max_output_tokens": self.settings.retrieval.answer_max_output_tokens}
        )
        answer_recorder = InMemoryTraceRecorder()
        judge_recorder = InMemoryTraceRecorder()
        answer = StructuredModelClient.from_model_settings(
            answer_settings,
            api_key=self.settings.require_work_api_key(),
            supports_json_schema=True,
            trace_recorder=answer_recorder,
        )
        judge = StructuredModelClient.from_model_settings(
            self.settings.judge,
            api_key=self.settings.require_judge_api_key(),
            supports_json_schema=True,
            trace_recorder=judge_recorder,
        )
        self._evaluation_clients = (answer, judge)
        return self._evaluation_clients

    async def build_ke_systems(
        self,
        run_id: str,
        snapshot_id: str,
    ) -> Mapping[str, KEMemorySystem]:
        validate_storage_name(run_id, label="run ID")
        self.snapshots.verify(snapshot_id, run_id, PipelineStage.KE_READY)
        manifests = self._snapshot_records(
            snapshot_id,
            run_id,
            "pipeline_manifests",
            PipelineRunManifest,
        )
        if len(manifests) != 1:
            raise RuntimeInvariantError(
                "verified ke-ready snapshot must contain exactly one pipeline manifest"
            )
        manifest = manifests[0]
        current_identity = await self.ontology.index_identity()
        if current_identity != manifest.ontology.index:
            raise RuntimeInvariantError(
                "live ontology identity differs from the verified ke-ready snapshot"
            )
        conversations = self._snapshot_records(
            snapshot_id,
            run_id,
            "conversations",
            Conversation,
        )
        current = self._snapshot_records(
            snapshot_id,
            run_id,
            "current_knowledge_equations",
            KnowledgeEquation,
        )
        aggregates = self._snapshot_records(
            snapshot_id,
            run_id,
            "aggregates",
            AggregateNode,
        )
        usage_source = _RecorderUsageSource(self._work_recorder)
        systems: dict[str, KEMemorySystem] = {}
        for conversation in sorted(conversations, key=lambda item: item.id):
            scoped_kes, scoped_aggregates = _conversation_records(
                conversation,
                current,
                aggregates,
            )
            port = _ConversationRuntimePort(
                conversation=conversation,
                current_knowledge_equations=scoped_kes,
                aggregates=scoped_aggregates,
                settings=self.settings,
                ontology=self.ontology,
                work_model=self.work_model,
                token_counter=self._token_counter,
                run_id=run_id,
            )
            system = KEMemorySystem(
                self.artifacts,
                port,
                port,
                usage_source,
                token_counter=self._token_counter,
            )
            scope = RunScope(
                run_id=run_id,
                conversation_id=conversation.id,
                system_id=KE_MEMORY_SYSTEM_ID,
            )
            await system.prepare(scope)
            for exchange in (
                exchange for session in conversation.sessions for exchange in session.exchanges
            ):
                await system.ingest(exchange)
            readiness = await system.await_ready()
            if not readiness.ready:
                raise RuntimeInvariantError(
                    f"Conversation KE runtime did not reach ke-ready: {conversation.id}"
                )
            systems[conversation.id] = system
        return systems

    async def aclose(self) -> None:
        evaluation_clients = self._evaluation_clients or ()
        terminal_error: Exception | None = None
        for client in (*evaluation_clients, self.work_model):
            try:
                await client.aclose()
            except Exception as error:
                terminal_error = terminal_error or error
        try:
            await self.ontology.aclose()
        except Exception as error:
            terminal_error = terminal_error or error
        if terminal_error is not None:
            raise RuntimeInvariantError(
                "runtime resources did not close cleanly"
            ) from terminal_error

    def _snapshot_records(
        self,
        snapshot_id: str,
        run_id: str,
        artifact_name: str,
        model: type[SnapshotModelT],
    ) -> tuple[SnapshotModelT, ...]:
        return _snapshot_records_from_git(
            self._state_root,
            snapshot_id,
            run_id,
            artifact_name,
            model,
        )


class _LiveEvaluationPreflightPorts:
    def __init__(
        self,
        config_root: Path,
        state_root: Path,
        run_id: str,
        snapshot_id: str,
    ) -> None:
        self._config_root = config_root.expanduser().resolve()
        self._state_root = state_root.expanduser().resolve()
        self._run_id = run_id
        self._snapshot_id = snapshot_id
        self._dotenv_path = self._config_root / ".env.local"
        self._dotenv_failure = self._dotenv_permission_failure()
        self._settings: AppSettings | None = None
        self._settings_error = "SettingsUnavailable"
        if self._dotenv_failure is None:
            try:
                self._settings = load_settings(self._config_root)
            except Exception as error:
                self._settings_error = type(error).__name__
        self._snapshot_cache: tuple[PipelineRunManifest, tuple[Conversation, ...]] | None = None

    async def check(self, name: str) -> str:
        if name == "code_identity":
            return self._check_code_identity()
        if name == "concurrency":
            return self._check_concurrency()
        if name == "credential_scan":
            return self._check_credentials()
        if name == "embedding":
            return self._check_embedding()
        if name == "environment":
            return self._check_environment()
        if name == "judge_model":
            return await self._check_model("judge_model")
        if name == "ke_ready_snapshot":
            return self._check_ke_ready_snapshot()
        if name == "ontology_identity":
            return await self._check_ontology_identity()
        if name == "state_repo":
            return self._check_state_repo()
        if name == "work_model":
            return await self._check_model("work_model")
        raise PreflightCheckFailure(f"{name}:UnknownCheck")

    def _check_code_identity(self) -> str:
        commit = _git_text(self._config_root, "rev-parse", "--verify", "HEAD^{commit}")
        if _GIT_SHA.fullmatch(commit) is None:
            raise PreflightCheckFailure("code_identity:InvalidGitHead")
        if _git_text(
            self._config_root,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ):
            raise PreflightCheckFailure("code_identity:DirtyWorktree")
        spec_sha = _sha256_file(self._config_root / _APPROVED_SPEC_PATH)
        plan_sha = _sha256_file(self._config_root / _APPROVED_PLAN_PATH)
        if spec_sha != _APPROVED_SPEC_SHA256:
            raise PreflightCheckFailure("code_identity:SpecHashMismatch")
        if plan_sha != _APPROVED_PLAN_SHA256:
            raise PreflightCheckFailure("code_identity:PlanHashMismatch")
        return f"code_identity:commit={commit}:spec={spec_sha}:plan={plan_sha}"

    def _check_concurrency(self) -> str:
        settings = self._require_settings("concurrency")
        concurrency = settings.evaluation.concurrency
        values = (
            concurrency.turn_workers,
            concurrency.session_workers,
            concurrency.question_workers,
            concurrency.judge_workers,
        )
        if any(value <= 0 for value in values):
            raise PreflightCheckFailure("concurrency:NonPositiveLimit")
        return (
            "concurrency:"
            f"turn={values[0]}:session={values[1]}:question={values[2]}:judge={values[3]}"
        )

    def _check_credentials(self) -> str:
        completed = subprocess.run(
            (
                "git",
                "-C",
                str(self._config_root),
                "ls-files",
                "-z",
                "--",
                "src",
                "config",
                "tests",
            ),
            check=False,
            capture_output=True,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        if completed.returncode != 0:
            raise RuntimeInvariantError("unable to enumerate tracked preflight files")
        paths = tuple(path for path in completed.stdout.split(b"\0") if path)
        matched = 0
        for raw_path in paths:
            try:
                relative = Path(os.fsdecode(raw_path))
                content = (self._config_root / relative).read_bytes()
            except OSError as error:
                raise RuntimeInvariantError("unable to scan tracked preflight files") from error
            if _SK_CREDENTIAL.search(content) is not None:
                matched += 1
        if matched:
            raise PreflightCheckFailure(f"credential_scan:CredentialPattern:files={matched}")
        return f"credential_scan:files={len(paths)}:matches=0"

    def _check_embedding(self) -> str:
        settings = self._require_settings("embedding")
        if settings.embedding.enabled:
            raise PreflightCheckFailure("embedding:Enabled")
        return "embedding:enabled=false:path_required=false"

    def _check_environment(self) -> str:
        if self._dotenv_failure is not None:
            raise PreflightCheckFailure(self._dotenv_failure)
        settings = self._require_settings("environment")
        names = tuple(
            sorted(
                {
                    settings.work.api_key_env,
                    settings.judge.api_key_env,
                    settings.es.endpoint_env,
                    settings.es.index_env,
                    settings.es.api_key_env,
                }
            )
        )
        missing = tuple(
            name for name in names if not (value := os.environ.get(name)) or not value.strip()
        )
        if missing:
            raise PreflightCheckFailure(f"environment:missing={','.join(missing)}")
        dotenv_identity = "mode=0600" if self._dotenv_path.exists() else "absent"
        return f"environment:variables={len(names)}:dotenv={dotenv_identity}"

    async def _check_model(self, name: Literal["work_model", "judge_model"]) -> str:
        settings = self._require_settings(name)
        if name == "work_model":
            model_settings = settings.work.model_copy(
                update={"max_output_tokens": settings.retrieval.answer_max_output_tokens}
            )
            api_key = settings.require_work_api_key()
        else:
            model_settings = settings.judge
            api_key = settings.require_judge_api_key()
        endpoint = _nonsecret_model_endpoint(model_settings.base_url, check_name=name)
        client = StructuredModelClient.from_model_settings(
            model_settings,
            api_key=api_key,
            supports_json_schema=True,
            trace_recorder=InMemoryTraceRecorder(),
        )
        try:
            response = await client.complete(
                _EvaluationProbeResponse,
                [{"role": "user", "content": 'Return exactly {"ready":true}.'}],
                TraceContext(operation="evaluation_preflight", metadata={"check": name}),
            )
            if response.ready is not True:
                raise PreflightCheckFailure(f"{name}:StructuredProbeRejected")
        finally:
            await client.aclose()
        return f"{name}:model={model_settings.model}:base_url={endpoint}"

    def _check_ke_ready_snapshot(self) -> str:
        _manifest, conversations = self._load_snapshot()
        sessions = sum(len(conversation.sessions) for conversation in conversations)
        exchanges = sum(
            len(session.exchanges)
            for conversation in conversations
            for session in conversation.sessions
        )
        questions = len(normalize_questions(conversations))
        return (
            "ke_ready_snapshot:"
            f"directories=4,15,17:sessions={sessions}:exchanges={exchanges}:questions={questions}"
        )

    async def _check_ontology_identity(self) -> str:
        settings = self._require_settings("ontology_identity")
        manifest, _conversations = self._load_snapshot()
        if manifest.ontology.normalization_mode != "bounded-best-effort":
            raise PreflightCheckFailure("ontology_identity:NormalizationModeMismatch")
        ontology = ElasticsearchVocabulary.from_app_settings(settings)
        try:
            await ontology.health()
            current = await ontology.index_identity()
        finally:
            await ontology.aclose()
        if ontology.normalization_mode != "bounded-best-effort":
            raise PreflightCheckFailure("ontology_identity:NormalizationModeMismatch")
        if current != manifest.ontology.index:
            raise PreflightCheckFailure("ontology_identity:OntologyDriftError")
        return (
            "ontology_identity:"
            f"index={current.index_name}:uuid={current.index_uuid}:"
            f"mapping={current.mapping_sha256}:mode=bounded-best-effort"
        )

    def _check_state_repo(self) -> str:
        return probe_state_repository_writable(self._state_root, self._snapshot_id)

    def _load_snapshot(self) -> tuple[PipelineRunManifest, tuple[Conversation, ...]]:
        if self._snapshot_cache is not None:
            return self._snapshot_cache
        if not self._state_root.is_dir():
            raise RuntimeInvariantError("state repository is unavailable")
        artifacts = ArtifactStore(self._state_root, registry=PIPELINE_ARTIFACT_REGISTRY)
        snapshots = GitSnapshotStore(artifacts.root, artifacts)
        snapshots.verify(self._snapshot_id, self._run_id, PipelineStage.KE_READY)
        manifests = _snapshot_records_from_git(
            self._state_root,
            self._snapshot_id,
            self._run_id,
            "pipeline_manifests",
            PipelineRunManifest,
        )
        conversations = _snapshot_records_from_git(
            self._state_root,
            self._snapshot_id,
            self._run_id,
            "conversations",
            Conversation,
        )
        if len(manifests) != 1:
            raise RuntimeInvariantError(
                "verified ke-ready snapshot must contain exactly one pipeline manifest"
            )
        manifest = manifests[0]
        settings = self._require_settings("ke_ready_snapshot")
        validate_evaluation_snapshot_contract(manifest, conversations, settings)
        self._snapshot_cache = manifest, conversations
        return self._snapshot_cache

    def _require_settings(self, check_name: str) -> AppSettings:
        if self._settings is None:
            raise PreflightCheckFailure(f"{check_name}:{self._settings_error}")
        return self._settings

    def _dotenv_permission_failure(self) -> str | None:
        try:
            metadata = self._dotenv_path.lstat()
        except FileNotFoundError:
            return None
        except OSError as error:
            return f"environment:{type(error).__name__}"
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            return "environment:DotenvFileTypeError"
        mode = stat.S_IMODE(metadata.st_mode)
        if mode != 0o600:
            return f"environment:dotenv_mode={mode:04o}"
        return None


def build_evaluation_preflight(
    config_root: Path,
    state_root: Path,
    run_id: str,
    snapshot_id: str,
) -> EvaluationPreflight:
    """Compose the read-only live preflight without hydrating an answer runtime."""
    return EvaluationPreflight(
        _LiveEvaluationPreflightPorts(config_root, state_root, run_id, snapshot_id)
    )


def validate_evaluation_snapshot_contract(
    manifest: PipelineRunManifest,
    conversations: Sequence[Conversation],
    settings: AppSettings,
) -> None:
    directory_ids: list[int] = []
    archive_hashes: list[str] = []
    for conversation in conversations:
        directory_id = conversation.source_metadata.get("beam_directory_id")
        archive_hash = conversation.source_metadata.get("archive_sha256")
        if isinstance(directory_id, bool) or not isinstance(directory_id, int):
            raise PreflightCheckFailure("ke_ready_snapshot:SnapshotContractMismatch")
        if not isinstance(archive_hash, str):
            raise PreflightCheckFailure("ke_ready_snapshot:SnapshotContractMismatch")
        directory_ids.append(directory_id)
        archive_hashes.append(archive_hash)
    session_count = sum(len(conversation.sessions) for conversation in conversations)
    exchange_count = sum(
        len(session.exchanges)
        for conversation in conversations
        for session in conversation.sessions
    )
    question_count = len(normalize_questions(conversations))
    actual = (
        settings.dataset.archive_sha256,
        manifest.dataset_sha256,
        tuple(sorted(set(archive_hashes))),
        settings.dataset.selected_directories,
        manifest.selected_directories,
        tuple(sorted(directory_ids)),
        settings.dataset.expected_sessions,
        session_count,
        settings.dataset.expected_exchanges,
        exchange_count,
        settings.dataset.expected_questions,
        question_count,
        settings.embedding.enabled,
        manifest.embedding_enabled,
        manifest.ontology.normalization_mode,
        manifest.concurrency,
    )
    expected = (
        _FIXED_DATASET_SHA256,
        _FIXED_DATASET_SHA256,
        (_FIXED_DATASET_SHA256,),
        _FIXED_DIRECTORIES,
        _FIXED_DIRECTORIES,
        _FIXED_DIRECTORIES,
        _FIXED_SESSIONS,
        _FIXED_SESSIONS,
        _FIXED_EXCHANGES,
        _FIXED_EXCHANGES,
        _FIXED_QUESTIONS,
        _FIXED_QUESTIONS,
        False,
        False,
        "bounded-best-effort",
        settings.evaluation.concurrency,
    )
    if actual != expected:
        raise PreflightCheckFailure("ke_ready_snapshot:SnapshotContractMismatch")


def probe_state_repository_writable(state_root: Path, expected_head: str) -> str:
    if not state_root.is_dir():
        raise PreflightCheckFailure("state_repo:MissingDirectory")
    head = _git_text(state_root, "rev-parse", "--verify", "HEAD^{commit}")
    if head != expected_head:
        raise PreflightCheckFailure("state_repo:HeadMismatch")
    if _git_text(
        state_root,
        "status",
        "--porcelain=v1",
        "--untracked-files=no",
    ):
        raise PreflightCheckFailure("state_repo:DirtyTrackedState")

    _probe_writable_directory(
        state_root,
        failure_detail="state_repo:WorktreeRootNotWritable",
    )
    objects_directory = _resolved_git_directory(
        state_root,
        "objects",
        failure_detail="state_repo:GitObjectStorageNotWritable",
    )
    _probe_writable_directory(
        objects_directory,
        failure_detail="state_repo:GitObjectStorageNotWritable",
    )
    ref_directory = _active_ref_lock_directory(state_root)
    _probe_writable_directory(
        ref_directory,
        failure_detail="state_repo:GitRefMetadataNotWritable",
    )
    return f"state_repo:head={head}:writable=true"


def _snapshot_records_from_git(
    state_root: Path,
    snapshot_id: str,
    run_id: str,
    artifact_name: str,
    model: type[SnapshotModelT],
) -> tuple[SnapshotModelT, ...]:
    validate_storage_name(run_id, label="run ID")
    validate_storage_name(artifact_name, label="artifact name")
    path = f"runs/{run_id}/{PipelineStage.KE_READY.value}/{artifact_name}.jsonl"
    completed = subprocess.run(
        ("git", "-C", str(state_root), "show", f"{snapshot_id}:{path}"),
        check=False,
        capture_output=True,
        env={
            **os.environ,
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
        },
    )
    if completed.returncode != 0:
        raise RuntimeInvariantError(f"verified snapshot is missing artifact {artifact_name}")
    data = completed.stdout
    if data and not data.endswith(b"\n"):
        raise RuntimeInvariantError(f"snapshot artifact lacks final newline: {artifact_name}")
    lines = () if not data else tuple(data[:-1].split(b"\n"))
    try:
        records = tuple(model.model_validate_json(line) for line in lines)
    except ValidationError as error:
        raise RuntimeInvariantError(
            f"snapshot artifact failed model validation: {artifact_name}"
        ) from error
    if any(canonical_json(item) != line for item, line in zip(records, lines, strict=True)):
        raise RuntimeInvariantError(f"snapshot artifact is not canonical JSON: {artifact_name}")
    return records


def _git_text(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(root), *arguments),
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
        },
    )
    if completed.returncode != 0:
        raise RuntimeInvariantError("Git preflight command failed")
    return completed.stdout.strip()


def _git_optional_text(root: Path, *arguments: str) -> str | None:
    completed = subprocess.run(
        ("git", "-C", str(root), *arguments),
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
        },
    )
    if completed.returncode == 0:
        return completed.stdout.strip()
    if completed.returncode == 1:
        return None
    raise RuntimeInvariantError("Git preflight command failed")


def _resolved_git_directory(
    root: Path,
    git_path: str,
    *,
    failure_detail: str,
) -> Path:
    raw_path = _git_text(root, "rev-parse", "--git-path", git_path)
    path = Path(raw_path)
    if not path.is_absolute():
        path = root / path
    return _require_probe_directory(path, failure_detail=failure_detail)


def _active_ref_lock_directory(root: Path) -> Path:
    active_ref = _git_optional_text(root, "symbolic-ref", "-q", "HEAD")
    if active_ref is None:
        raw_path = _git_text(root, "rev-parse", "--git-dir")
        path = Path(raw_path)
        if not path.is_absolute():
            path = root / path
        return _require_probe_directory(
            path,
            failure_detail="state_repo:GitRefMetadataNotWritable",
        )

    raw_path = _git_text(root, "rev-parse", "--git-path", active_ref)
    ref_path = Path(raw_path)
    if not ref_path.is_absolute():
        ref_path = root / ref_path
    return _require_probe_directory(
        ref_path.parent,
        failure_detail="state_repo:GitRefMetadataNotWritable",
    )


def _require_probe_directory(path: Path, *, failure_detail: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
        is_directory = resolved.is_dir()
    except OSError:
        raise PreflightCheckFailure(failure_detail) from None
    if not is_directory:
        raise PreflightCheckFailure(failure_detail)
    return resolved


def _probe_writable_directory(directory: Path, *, failure_detail: str) -> None:
    descriptor: int | None = None
    temporary_path: Path | None = None
    failed = False
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".ke-memory-preflight-",
            suffix=".tmp",
            dir=directory,
        )
        temporary_path = Path(temporary_name)
        os.fchmod(descriptor, 0o600)
        if stat.S_IMODE(os.fstat(descriptor).st_mode) != 0o600:
            raise OSError("preflight probe mode mismatch")
        _write_probe_payload(descriptor)
        os.fsync(descriptor)
    except OSError:
        failed = True
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                failed = True
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except OSError:
                failed = True
            try:
                _fsync_directory_if_supported(directory)
            except OSError:
                failed = True
    if failed:
        raise PreflightCheckFailure(failure_detail)


def _write_probe_payload(descriptor: int) -> None:
    payload = memoryview(b"ke-memory-preflight\n")
    written = 0
    while written < len(payload):
        count = os.write(descriptor, payload[written:])
        if count <= 0:
            raise OSError("preflight probe write failed")
        written += count


def _fsync_directory_if_supported(directory: Path) -> None:
    unsupported = {
        errno.EINVAL,
        getattr(errno, "ENOTSUP", errno.EINVAL),
        getattr(errno, "EOPNOTSUPP", errno.EINVAL),
    }
    try:
        descriptor = os.open(
            directory,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
    except OSError as error:
        if error.errno in unsupported:
            return
        raise
    try:
        try:
            os.fsync(descriptor)
        except OSError as error:
            if error.errno not in unsupported:
                raise
    finally:
        os.close(descriptor)


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
    except OSError as error:
        raise RuntimeInvariantError("approved identity file is unavailable") from error
    return hasher.hexdigest()


def _nonsecret_model_endpoint(value: str, *, check_name: str) -> str:
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        _port = parsed.port
    except ValueError:
        raise PreflightCheckFailure(f"{check_name}:EndpointIdentityError") from None
    if (
        parsed.scheme not in {"http", "https"}
        or hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise PreflightCheckFailure(f"{check_name}:EndpointIdentityError")
    return value.rstrip("/")


def _conversation_records(
    conversation: Conversation,
    current: Sequence[KnowledgeEquation],
    aggregates: Sequence[AggregateNode],
) -> tuple[tuple[KnowledgeEquation, ...], tuple[AggregateNode, ...]]:
    message_ids = {
        message.id
        for session in conversation.sessions
        for exchange in session.exchanges
        for message in (exchange.user, exchange.assistant)
    }

    def belongs(spans: Iterable[object], *, record_id: str) -> bool:
        span_message_ids = {cast(str, getattr(span, "message_id")) for span in spans}
        if not span_message_ids:
            raise RuntimeInvariantError(f"record has no raw evidence closure: {record_id}")
        if span_message_ids.intersection(message_ids) and not span_message_ids.issubset(
            message_ids
        ):
            raise RuntimeInvariantError(f"record evidence crosses Conversation scopes: {record_id}")
        return bool(span_message_ids) and span_message_ids.issubset(message_ids)

    scoped_kes = tuple(item for item in current if belongs(item.evidence_refs, record_id=item.id))
    scoped_aggregates = tuple(
        item for item in aggregates if belongs(item.evidence_closure, record_id=item.id)
    )
    return scoped_kes, scoped_aggregates


def _code_commit(project_root: Path) -> str:
    completed = subprocess.run(
        ("git", "-C", str(project_root), "rev-parse", "HEAD"),
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    commit = completed.stdout.strip()
    if completed.returncode != 0 or len(commit) != 40:
        raise PipelineInvariantError("unable to resolve the full code Git SHA")
    return commit
