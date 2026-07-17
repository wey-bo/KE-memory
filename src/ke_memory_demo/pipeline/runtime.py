from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
import os
from pathlib import Path
import subprocess
import time
from typing import TypeVar, cast

from pydantic import BaseModel, ValidationError

from ke_memory_demo.core.json import canonical_json
from ke_memory_demo.domain import (
    AggregateNode,
    Conversation,
    Evidence,
    Exchange,
    KnowledgeEquation,
    RunScope,
)
from ke_memory_demo.infra.llm import StructuredModelClient
from ke_memory_demo.infra.telemetry import (
    InMemoryTraceRecorder,
    ModelTrace,
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


class RuntimeInvariantError(RuntimeError):
    """Real runtime composition or exact-snapshot hydration failed."""


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
        validate_storage_name(artifact_name, label="artifact name")
        path = f"runs/{run_id}/{PipelineStage.KE_READY.value}/{artifact_name}.jsonl"
        completed = subprocess.run(
            ("git", "-C", str(self._state_root), "show", f"{snapshot_id}:{path}"),
            check=False,
            capture_output=True,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
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
