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
from typing import TYPE_CHECKING, TypeVar, cast
from urllib.parse import urlsplit

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
from ke_memory_demo.core.errors import PreflightCheckFailure

if TYPE_CHECKING:  # pragma: no cover - imported for annotations only
    # Evaluation types appear in three method signatures. Under TYPE_CHECKING they
    # cost no runtime import, so orchestration still does not depend on measurement
    # when loaded; type checkers and the dependency gate both see the truth.
    pass

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
    TracedRetrieval,
    SymbolicRetriever,
    TokenCounter,
)
from ke_memory_demo.settings import (
    AppSettings,
    ConfigLayout,
    ModelSettings,
    load_settings,
)
from ke_memory_demo.snapshots import GitSnapshotStore
from ke_memory_demo.storage import (
    ArtifactStore,
    MemoryIndex,
    StageManifest,
    validate_storage_name,
)
from ke_memory_demo.systems import (
    KE_MEMORY_SYSTEM_ID,
    KE_READY_STAGE,
    KEMemorySystem,
    PreparedRunState,
    StageReadiness,
    StoredExchange,
)

from ke_memory_demo.storage.checkpoints import CheckpointStore
from ke_memory_demo.contracts import (
    PIPELINE_ARTIFACT_REGISTRY,
    PipelineRunManifest,
    PipelineStage,
)
from .runner import MemoryPipeline, PipelineInvariantError


Sleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]
SnapshotModelT = TypeVar("SnapshotModelT", bound=BaseModel)
GIT_SHA = re.compile(r"[0-9a-f]{40}", flags=re.ASCII)








def read_only_git_env() -> dict[str, str]:
    return {
        **os.environ,
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
    }


class RuntimeInvariantError(RuntimeError):
    """Real runtime composition or exact-snapshot hydration failed."""




class RuntimeStructuredModelClient(StructuredModelClient):
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

    async def retrieve_with_trace(
        self,
        scope: RunScope,
        question: str,
        evidence_budget_tokens: int,
    ) -> TracedRetrieval:
        self._validate_scope(scope)
        if self._coordinator is None:
            raise RuntimeInvariantError("Conversation retrieval runtime is not prepared")
        return await self._coordinator.retrieve_with_trace(question, evidence_budget_tokens)

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

    @classmethod
    def from_paths(
        cls,
        config_root: Path | ConfigLayout,
        state_root: Path,
        *,
        extra_artifact_registry: Mapping[str, type[BaseModel]] | None = None,
    ) -> RuntimeFactory:
        """Build a pipeline-only runtime.

        ``extra_artifact_registry`` is how a composition root adds artifact types the
        pipeline itself does not produce -- the evaluation set, in practice. Naming
        the evaluation registry here directly would put an evaluation import back in
        the pipeline layer, and a pipeline-only process would carry artifact types it
        can never write.
        """
        settings = load_settings(config_root)
        artifacts = ArtifactStore(
            state_root,
            registry={
                **PIPELINE_ARTIFACT_REGISTRY,
                **dict(extra_artifact_registry or {}),
            },
        )
        snapshots = GitSnapshotStore.init(artifacts.root, artifacts)
        ontology = ElasticsearchVocabulary.from_app_settings(settings)
        work_secret = settings.require_work_api_key()
        work_recorder = InMemoryTraceRecorder()
        work_model = cast(
            RuntimeStructuredModelClient,
            RuntimeStructuredModelClient.from_model_settings(
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

    @property
    def code_commit(self) -> str:
        """The commit this runtime was built from.

        Exposed so a composition root can pass it into ``RuntimeContext`` without
        reaching for a private attribute -- the context is meant to be constructed
        from published values, not scraped off the factory.
        """
        return self._code_commit

    async def build_ke_systems(
        self,
        run_id: str,
        snapshot_id: str,
        *,
        conversation_ids: frozenset[str] | None = None,
    ) -> Mapping[str, KEMemorySystem]:
        validate_storage_name(run_id, label="run ID")
        self.snapshots.verify(snapshot_id, run_id, PipelineStage.KE_READY)
        manifests = self.snapshot_records(
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
        conversations = self.snapshot_records(
            snapshot_id,
            run_id,
            "conversations",
            Conversation,
        )
        available_conversation_ids = {item.id for item in conversations}
        if conversation_ids is not None:
            missing = sorted(conversation_ids.difference(available_conversation_ids))
            if missing:
                raise RuntimeInvariantError(
                    f"requested Conversation is absent from the snapshot: {missing[0]}"
                )
            conversations = tuple(item for item in conversations if item.id in conversation_ids)
        current = self.snapshot_records(
            snapshot_id,
            run_id,
            "current_knowledge_equations",
            KnowledgeEquation,
        )
        aggregates = self.snapshot_records(
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
        terminal_error: Exception | None = None
        for client in (self.work_model,):
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

    def snapshot_records(
        self,
        snapshot_id: str,
        run_id: str,
        artifact_name: str,
        model: type[SnapshotModelT],
    ) -> tuple[SnapshotModelT, ...]:
        return snapshot_records_from_git(
            self._state_root,
            snapshot_id,
            run_id,
            artifact_name,
            model,
        )








def probe_state_repository_writable(state_root: Path, expected_head: str) -> str:
    if not state_root.is_dir():
        raise PreflightCheckFailure("state_repo:MissingDirectory")
    head = git_text(state_root, "rev-parse", "--verify", "HEAD^{commit}")
    if head != expected_head:
        raise PreflightCheckFailure("state_repo:HeadMismatch")
    if git_text(
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


def snapshot_stage_manifest_from_git(
    state_root: Path,
    snapshot_id: str,
    run_id: str,
    stage: PipelineStage,
) -> StageManifest:
    validate_storage_name(run_id, label="run ID")
    path = f"runs/{run_id}/{stage.value}/manifest.json"
    data = _snapshot_file_from_git(
        state_root,
        snapshot_id,
        path,
        description=f"{stage.value} manifest",
    )
    try:
        manifest = StageManifest.model_validate_json(data)
    except ValidationError as error:
        raise RuntimeInvariantError("snapshot stage manifest failed validation") from error
    if manifest.run_id != run_id or manifest.stage != stage.value:
        raise RuntimeInvariantError("snapshot stage manifest identity does not match")
    if canonical_json(manifest) != data:
        raise RuntimeInvariantError("snapshot stage manifest is not canonical JSON")
    return manifest


def _snapshot_file_from_git(
    state_root: Path,
    snapshot_id: str,
    path: str,
    *,
    description: str,
) -> bytes:
    if GIT_SHA.fullmatch(snapshot_id) is None:
        raise RuntimeInvariantError("snapshot ID must be a full Git SHA")
    completed = subprocess.run(
        ("git", "-C", str(state_root), "show", f"{snapshot_id}:{path}"),
        check=False,
        capture_output=True,
        env=read_only_git_env(),
    )
    if completed.returncode != 0:
        raise RuntimeInvariantError(f"verified snapshot is missing {description}")
    return completed.stdout


def snapshot_records_from_git(
    state_root: Path,
    snapshot_id: str,
    run_id: str,
    artifact_name: str,
    model: type[SnapshotModelT],
    *,
    stage: PipelineStage = PipelineStage.KE_READY,
) -> tuple[SnapshotModelT, ...]:
    validate_storage_name(run_id, label="run ID")
    validate_storage_name(artifact_name, label="artifact name")
    path = f"runs/{run_id}/{stage.value}/{artifact_name}.jsonl"
    data = _snapshot_file_from_git(
        state_root,
        snapshot_id,
        path,
        description=f"artifact {artifact_name}",
    )
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


def runtime_trace_records(model: object) -> tuple[ModelTrace, ...]:
    raw = getattr(model, "trace_records", ())
    if not isinstance(raw, Sequence):
        raise RuntimeInvariantError("evaluation model exposed invalid trace records")
    try:
        return tuple(ModelTrace.model_validate(item) for item in cast(Sequence[object], raw))
    except (TypeError, ValueError) as error:
        raise RuntimeInvariantError("evaluation model exposed an invalid trace") from error


def sorted_model_traces(traces: Iterable[ModelTrace]) -> tuple[ModelTrace, ...]:
    validated = tuple(ModelTrace.model_validate(item) for item in traces)
    return tuple(sorted(validated, key=canonical_json))


def git_text(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(root), *arguments),
        check=False,
        capture_output=True,
        text=True,
        env=read_only_git_env(),
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
        env=read_only_git_env(),
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
    raw_path = git_text(root, "rev-parse", "--git-path", git_path)
    path = Path(raw_path)
    if not path.is_absolute():
        path = root / path
    return _require_probe_directory(path, failure_detail=failure_detail)


def _active_ref_lock_directory(root: Path) -> Path:
    active_ref = _git_optional_text(root, "symbolic-ref", "-q", "HEAD")
    if active_ref is None:
        raw_path = git_text(root, "rev-parse", "--git-dir")
        path = Path(raw_path)
        if not path.is_absolute():
            path = root / path
        return _require_probe_directory(
            path,
            failure_detail="state_repo:GitRefMetadataNotWritable",
        )

    raw_path = git_text(root, "rev-parse", "--git-path", active_ref)
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


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
    except OSError as error:
        raise RuntimeInvariantError("approved identity file is unavailable") from error
    return hasher.hexdigest()


def nonsecret_model_endpoint(value: str, *, check_name: str) -> str:
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
        env=read_only_git_env(),
    )
    commit = completed.stdout.strip()
    if completed.returncode != 0 or len(commit) != 40:
        raise PipelineInvariantError("unable to resolve the full code Git SHA")
    return commit
