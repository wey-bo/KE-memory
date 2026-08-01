from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import hashlib
from pathlib import Path
import re
import shutil
from typing import Annotated, Literal, TypeVar, cast

from pydantic import BaseModel, ConfigDict, Field

from ke_memory_demo.aggregation import (
    SemanticDAG,
    SemanticDAGBuilder,
    SessionAggregator,
    SessionMemory,
    validate_evidence_closure,
    validate_session_memory,
)
from ke_memory_demo.core.json import JsonObject, JsonValue, canonical_json
from ke_memory_demo.domain import (
    AggregateNode,
    Conversation,
    CoverageEntry,
    Exchange,
    KnowledgeEquation,
    KnowledgeLevel,
    Lifecycle,
    Message,
    MessageSpan,
    Session,
)
from ke_memory_demo.extraction import (
    LifecycleMaintainer,
    TurnExtractionResult,
    TurnKEExtractor,
)
from ke_memory_demo.infra.llm import StructuredModelClient
from ke_memory_demo.infra.telemetry import (
    ModelTrace,
    TraceContext,
    usage_context_only_trace,
    validate_usage_context_only_trace,
)
from ke_memory_demo.ingestion import load_beam_subset
from ke_memory_demo.ontology import (
    ElasticsearchVocabulary,
    IndexIdentity,
    OntologyRelation,
    OntologyTerm,
)
from ke_memory_demo.settings import AppSettings
from ke_memory_demo.snapshots import GitSnapshotStore
from ke_memory_demo.storage import ArtifactStore, MemoryIndex

from ke_memory_demo.storage.checkpoints import CheckpointStore
from ke_memory_demo.core.concurrency import bounded_ordered_map
from ke_memory_demo.contracts import (
    OntologyRunIdentity,
    PipelineRunManifest,
    PipelineStage,
    PipelineStageResult,
    STAGE_PREDECESSOR,
)


NORMALIZATION_MODE = "bounded-best-effort"
_FULL_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_TRACE_RECORDS_ATTRIBUTE = "trace_records"
ModelT = TypeVar("ModelT", bound=BaseModel)
NonNegativeInt = Annotated[int, Field(ge=0)]


class PipelineInvariantError(RuntimeError):
    """The pipeline was invoked out of order or crossed a trust boundary."""


class PipelinePreflightResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ready: Literal[True]


class PipelinePreflightResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    session_count: NonNegativeInt
    exchange_count: NonNegativeInt
    question_count: NonNegativeInt
    ontology_identity: IndexIdentity
    normalization_mode: Literal["bounded-best-effort"]


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

    def resolve_raw_spans(self, ke_id: str) -> tuple[tuple[MessageSpan, str], ...]:
        equation = next(
            (item for item in self.current_knowledge_equations if item.id == ke_id),
            None,
        )
        if equation is None:
            raise PipelineInvariantError(f"current KE does not exist: {ke_id}")
        messages = {
            message.id: message
            for conversation in self.conversations
            for session in conversation.sessions
            for exchange in session.exchanges
            for message in (exchange.user, exchange.assistant)
        }
        resolved: list[tuple[MessageSpan, str]] = []
        for span in equation.evidence_refs:
            message = messages.get(span.message_id)
            if message is None:
                raise PipelineInvariantError(
                    f"current KE span references an unknown canonical message: {span.message_id}"
                )
            try:
                message.validate_span(span)
            except ValueError as error:
                raise PipelineInvariantError(str(error)) from error
            resolved.append((span, message.content[span.start_char : span.end_char]))
        return tuple(resolved)


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
        if _FULL_GIT_SHA.fullmatch(code_commit) is None:
            raise PipelineInvariantError("code_commit must be a full Git SHA")
        if settings.embedding.enabled:
            raise PipelineInvariantError("the primary pipeline requires embedding.enabled=false")
        if settings.aggregation.max_semantic_depth != 2:
            raise PipelineInvariantError("the primary pipeline requires maximum semantic depth 2")
        self._settings = settings
        self._artifacts = artifacts
        self._snapshots = snapshots
        self._checkpoints = checkpoints
        self._ontology = ontology
        self._work_model = work_model
        self._code_commit = code_commit
        self._run_id = checkpoints.run_id
        self._ontology_identity: IndexIdentity | None = None
        self._preflight_result: PipelinePreflightResult | None = None
        self._conversations: tuple[Conversation, ...] = ()
        self._turn_history: tuple[KnowledgeEquation, ...] = ()
        self._current_turn_kes: tuple[KnowledgeEquation, ...] = ()
        self._coverage: tuple[CoverageEntry, ...] = ()
        self._session_memories: tuple[SessionMemory, ...] = ()
        self._semantic_dag = SemanticDAG(nodes=())

    @property
    def run_id(self) -> str:
        return self._run_id

    async def preflight(self) -> PipelinePreflightResult:
        if self._preflight_result is not None:
            return self._preflight_result

        await self._ontology.health()
        identity = await self._ontology.index_identity()
        self._ontology_identity = identity
        actual_mode = getattr(self._ontology, "normalization_mode", None)
        if actual_mode != NORMALIZATION_MODE:
            raise PipelineInvariantError(
                f"ontology normalization mode must be {NORMALIZATION_MODE}"
            )

        archive_path = self._archive_path()
        actual_archive_sha = _sha256_file(archive_path)
        if actual_archive_sha != self._settings.dataset.archive_sha256:
            raise PipelineInvariantError(
                "BEAM archive SHA-256 does not match the configured dataset identity"
            )
        conversations = tuple(load_beam_subset(archive_path))
        _validate_selected_directories(conversations, self._settings.dataset.selected_directories)
        sessions = tuple(
            session for conversation in conversations for session in conversation.sessions
        )
        exchanges = tuple(exchange for session in sessions for exchange in session.exchanges)
        question_count = sum(len(item.probing_questions) for item in conversations)
        expected = self._settings.dataset
        actual_counts = (len(sessions), len(exchanges), question_count)
        expected_counts = (
            expected.expected_sessions,
            expected.expected_exchanges,
            expected.expected_questions,
        )
        if actual_counts != expected_counts:
            raise PipelineInvariantError(
                "BEAM subset counts do not match configured sessions, exchanges, and questions"
            )

        response = await self._work_model.complete(
            PipelinePreflightResponse,
            (
                {
                    "role": "system",
                    "content": "Return the required structured readiness record.",
                },
                {
                    "role": "user",
                    "content": canonical_json(
                        cast(JsonValue, {"task": "pipeline_preflight", "ready": True})
                    ).decode("utf-8"),
                },
            ),
            TraceContext(operation="pipeline-preflight", metadata={"run_id": self._run_id}),
        )
        if PipelinePreflightResponse.model_validate(response).ready is not True:
            raise PipelineInvariantError("work model structured preflight did not succeed")

        self._snapshots.head()
        if shutil.disk_usage(self._artifacts.root).free <= 0:
            raise PipelineInvariantError("state repository has no available disk space")

        self._conversations = conversations
        self._preflight_result = PipelinePreflightResult(
            run_id=self._run_id,
            session_count=len(sessions),
            exchange_count=len(exchanges),
            question_count=question_count,
            ontology_identity=identity,
            normalization_mode=NORMALIZATION_MODE,
        )
        return self._preflight_result

    async def ingest(self) -> PipelineStageResult:
        self._require_preflight()
        records: dict[str, tuple[BaseModel, ...]] = {
            "conversations": tuple(self._conversations),
            "sessions": tuple(_sessions(self._conversations)),
            "exchanges": tuple(_exchanges(self._conversations)),
            "messages": tuple(_messages(self._conversations)),
            "tool_events": tuple(
                event for exchange in _exchanges(self._conversations) for event in exchange.events
            ),
        }
        return await self._write_stage(PipelineStage.INGESTED, records)

    async def extract_turn_ke(self) -> PipelineStageResult:
        self._require_preflight()
        self._require_predecessor(PipelineStage.TURN_KE_EXTRACTED)
        conversations = self._load_conversations(PipelineStage.INGESTED)
        ordered_exchanges = tuple(_exchanges(conversations))
        extractor = TurnKEExtractor(self._work_model, self._ontology, run_id=self._run_id)

        async def extract_or_load_checkpoint(exchange: Exchange) -> TurnExtractionResult:
            input_sha256 = hashlib.sha256(canonical_json(exchange)).hexdigest()
            cached = self._checkpoints.load(
                PipelineStage.TURN_KE_EXTRACTED.value,
                exchange.id,
                input_sha256,
                TurnExtractionResult,
            )
            if cached is not None:
                if cached.exchange_id != exchange.id:
                    raise PipelineInvariantError(
                        "Turn checkpoint payload does not match its Exchange envelope"
                    )
                return cached
            result = await extractor.extract(exchange)
            if result.exchange_id != exchange.id:
                raise PipelineInvariantError(
                    "Turn extractor result does not match the requested Exchange"
                )
            self._checkpoints.save(
                PipelineStage.TURN_KE_EXTRACTED.value,
                exchange.id,
                input_sha256,
                TurnExtractionResult,
                result,
            )
            return result

        turn_results = await bounded_ordered_map(
            ordered_exchanges,
            extract_or_load_checkpoint,
            limit=self._settings.evaluation.concurrency.turn_workers,
        )
        by_exchange = {item.exchange_id: item for item in turn_results}
        if len(by_exchange) != len(ordered_exchanges):
            raise PipelineInvariantError("Turn extraction did not return one result per Exchange")

        async def reconcile_conversation(
            conversation: Conversation,
        ) -> tuple[tuple[KnowledgeEquation, ...], tuple[KnowledgeEquation, ...]]:
            maintainer = LifecycleMaintainer(self._work_model, run_id=self._run_id)
            current: tuple[KnowledgeEquation, ...] = ()
            all_revisions: list[KnowledgeEquation] = []
            for exchange in _exchanges((conversation,)):
                result = by_exchange[exchange.id]
                lifecycle = await maintainer.apply(current, result.knowledge_equations)
                all_revisions.extend(result.knowledge_equations)
                all_revisions.extend(lifecycle.appended_revisions)
                current = lifecycle.current_records
            return _dedupe_revisions(all_revisions), current

        reconciled = await bounded_ordered_map(
            conversations,
            reconcile_conversation,
            limit=min(3, self._settings.evaluation.concurrency.session_workers),
        )
        history = _dedupe_revisions(
            equation
            for conversation_history, _current in reconciled
            for equation in conversation_history
        )
        current = _unique_current(
            equation
            for _history, conversation_current in reconciled
            for equation in conversation_current
        )
        coverage = tuple(entry for result in turn_results for entry in result.coverage)
        ontology_terms, ontology_relations = await self._fetch_bound_ontology(history)

        records = self._cumulative_records(PipelineStage.INGESTED)
        records.update(
            {
                "knowledge_equations": tuple(history),
                "current_knowledge_equations": tuple(current),
                "coverage": coverage,
                "ontology_terms": tuple(ontology_terms),
                "ontology_relations": tuple(ontology_relations),
            }
        )
        result = await self._write_stage(PipelineStage.TURN_KE_EXTRACTED, records)
        self._conversations = conversations
        self._turn_history = history
        self._current_turn_kes = current
        self._coverage = coverage
        return result

    async def aggregate_sessions(self) -> PipelineStageResult:
        self._require_preflight()
        self._require_predecessor(PipelineStage.SESSION_AGGREGATED)
        conversations = self._load_conversations(PipelineStage.TURN_KE_EXTRACTED)
        current_turn = tuple(
            item
            for item in self._read_records(
                PipelineStage.TURN_KE_EXTRACTED,
                "current_knowledge_equations",
                KnowledgeEquation,
            )
            if item.level is KnowledgeLevel.TURN
        )
        coverage = self._read_records(
            PipelineStage.TURN_KE_EXTRACTED,
            "coverage",
            CoverageEntry,
        )
        sessions = tuple(_sessions(conversations))

        async def aggregate_or_load(session: Session) -> SessionMemory:
            input_sha256 = _input_hash(
                {
                    "session": cast(JsonValue, session.model_dump(mode="json")),
                    "turn_kes": [
                        cast(JsonValue, item.model_dump(mode="json")) for item in current_turn
                    ],
                    "coverage": [
                        cast(JsonValue, item.model_dump(mode="json")) for item in coverage
                    ],
                }
            )
            cached = self._checkpoints.load(
                PipelineStage.SESSION_AGGREGATED.value,
                session.id,
                input_sha256,
                SessionMemory,
            )
            if cached is not None:
                if cached.session_id != session.id:
                    raise PipelineInvariantError(
                        "Session checkpoint payload does not match its Session envelope"
                    )
                selected = _session_turn_kes(session, current_turn)
                validate_session_memory(cached, selected)
                return cached
            memory = await SessionAggregator(
                self._work_model,
                current_turn,
                coverage,
                run_id=self._run_id,
            ).aggregate(session)
            self._checkpoints.save(
                PipelineStage.SESSION_AGGREGATED.value,
                session.id,
                input_sha256,
                SessionMemory,
                memory,
            )
            return memory

        memories = await bounded_ordered_map(
            sessions,
            aggregate_or_load,
            limit=self._settings.evaluation.concurrency.session_workers,
        )
        history = self._read_records(
            PipelineStage.TURN_KE_EXTRACTED,
            "knowledge_equations",
            KnowledgeEquation,
        )
        history = _dedupe_revisions(
            (
                *history,
                *(equation for memory in memories for equation in memory.knowledge_equations),
            )
        )
        current = _unique_current(
            (
                *current_turn,
                *(equation for memory in memories for equation in memory.knowledge_equations),
            )
        )
        records = self._cumulative_records(PipelineStage.TURN_KE_EXTRACTED)
        records.update(
            {
                "knowledge_equations": tuple(history),
                "current_knowledge_equations": tuple(current),
                "session_memories": tuple(memories),
            }
        )
        result = await self._write_stage(PipelineStage.SESSION_AGGREGATED, records)
        self._conversations = conversations
        self._turn_history = tuple(item for item in history if item.level is KnowledgeLevel.TURN)
        self._current_turn_kes = current_turn
        self._coverage = coverage
        self._session_memories = memories
        return result

    async def build_semantic_dag(self) -> PipelineStageResult:
        self._require_preflight()
        self._require_predecessor(PipelineStage.SEMANTIC_DAG_BUILT)
        conversations = self._load_conversations(PipelineStage.SESSION_AGGREGATED)
        current = self._read_records(
            PipelineStage.SESSION_AGGREGATED,
            "current_knowledge_equations",
            KnowledgeEquation,
        )
        current_turn = {item.id: item for item in current if item.level is KnowledgeLevel.TURN}
        memories = self._read_records(
            PipelineStage.SESSION_AGGREGATED,
            "session_memories",
            SessionMemory,
        )
        memory_by_session = {item.session_id: item for item in memories}

        async def build_or_load(conversation: Conversation) -> SemanticDAG:
            selected_memories = tuple(
                memory_by_session[session.id] for session in conversation.sessions
            )
            source_ids = {
                source_id for memory in selected_memories for source_id in memory.source_turn_ke_ids
            }
            selected_turn = {source_id: current_turn[source_id] for source_id in source_ids}
            input_sha256 = _input_hash(
                {
                    "session_memories": [
                        cast(JsonValue, item.model_dump(mode="json")) for item in selected_memories
                    ],
                    "turn_kes": [
                        cast(JsonValue, selected_turn[key].model_dump(mode="json"))
                        for key in sorted(selected_turn)
                    ],
                }
            )
            cached = self._checkpoints.load(
                PipelineStage.SEMANTIC_DAG_BUILT.value,
                conversation.id,
                input_sha256,
                SemanticDAG,
            )
            if cached is not None:
                validate_evidence_closure(cached.nodes, _session_kes(selected_memories))
                return cached
            dag = await SemanticDAGBuilder(
                self._work_model,
                selected_turn,
                run_id=self._run_id,
            ).build(selected_memories)
            self._checkpoints.save(
                PipelineStage.SEMANTIC_DAG_BUILT.value,
                conversation.id,
                input_sha256,
                SemanticDAG,
                dag,
            )
            return dag

        dags = await bounded_ordered_map(
            conversations,
            build_or_load,
            limit=min(3, self._settings.evaluation.concurrency.session_workers),
        )
        by_conversation = {
            conversation.id: dag for conversation, dag in zip(conversations, dags, strict=True)
        }
        nodes = tuple(
            node
            for conversation_id in sorted(by_conversation)
            for node in by_conversation[conversation_id].nodes
        )
        semantic_dag = SemanticDAG(nodes=nodes)
        history = self._read_records(
            PipelineStage.SESSION_AGGREGATED,
            "knowledge_equations",
            KnowledgeEquation,
        )
        history = _dedupe_revisions(
            (*history, *(assertion for node in nodes for assertion in node.assertions))
        )
        current = _unique_current(
            (
                *current,
                *(assertion for node in nodes for assertion in node.assertions),
            )
        )
        records = self._cumulative_records(PipelineStage.SESSION_AGGREGATED)
        records.update(
            {
                "knowledge_equations": tuple(history),
                "current_knowledge_equations": tuple(current),
                "aggregates": nodes,
            }
        )
        result = await self._write_stage(PipelineStage.SEMANTIC_DAG_BUILT, records)
        self._conversations = conversations
        self._session_memories = memories
        self._semantic_dag = semantic_dag
        return result

    async def prepare_ke(self) -> PipelineStageResult:
        self._require_preflight()
        self._require_predecessor(PipelineStage.KE_READY)
        conversations = self._load_conversations(PipelineStage.SEMANTIC_DAG_BUILT)
        history = self._read_records(
            PipelineStage.SEMANTIC_DAG_BUILT,
            "knowledge_equations",
            KnowledgeEquation,
        )
        current = self._read_records(
            PipelineStage.SEMANTIC_DAG_BUILT,
            "current_knowledge_equations",
            KnowledgeEquation,
        )
        aggregates = self._read_records(
            PipelineStage.SEMANTIC_DAG_BUILT,
            "aggregates",
            AggregateNode,
        )
        memories = self._read_records(
            PipelineStage.SEMANTIC_DAG_BUILT,
            "session_memories",
            SessionMemory,
        )
        _validate_current_history(history, current)
        _validate_raw_evidence(conversations, (*history, *current, *aggregates))
        _validate_dags_by_conversation(conversations, memories, aggregates)
        ontology_terms, ontology_relations = await self._fetch_bound_ontology(history)

        exchanges = tuple(_exchanges(conversations))
        index_stats = MemoryIndex(self._artifacts.cache_path(self._run_id)).rebuild(
            exchanges,
            current,
            aggregates,
        )
        records = self._cumulative_records(PipelineStage.SEMANTIC_DAG_BUILT)
        records.update(
            {
                "knowledge_equations": tuple(history),
                "current_knowledge_equations": tuple(current),
                "aggregates": tuple(aggregates),
                "ontology_terms": tuple(ontology_terms),
                "ontology_relations": tuple(ontology_relations),
                "index_stats": (index_stats,),
            }
        )
        result = await self._write_stage(PipelineStage.KE_READY, records)
        self._conversations = conversations
        self._session_memories = memories
        self._semantic_dag = SemanticDAG(nodes=aggregates)
        return result

    async def run_all(self) -> PipelineRunResult:
        await self.preflight()
        await self.ingest()
        await self.extract_turn_ke()
        await self.aggregate_sessions()
        await self.build_semantic_dag()
        ready = await self.prepare_ke()
        current = self._read_records(
            PipelineStage.KE_READY,
            "current_knowledge_equations",
            KnowledgeEquation,
        )
        memories = self._read_records(
            PipelineStage.KE_READY,
            "session_memories",
            SessionMemory,
        )
        aggregates = self._read_records(
            PipelineStage.KE_READY,
            "aggregates",
            AggregateNode,
        )
        return PipelineRunResult(
            run_id=self._run_id,
            stage=PipelineStage.KE_READY,
            snapshot_id=ready.snapshot_id,
            conversations=self._load_conversations(PipelineStage.KE_READY),
            current_knowledge_equations=current,
            session_memories=memories,
            semantic_dag=SemanticDAG(nodes=aggregates),
        )

    def _archive_path(self) -> Path:
        path = self._settings.dataset.archive_path.expanduser()
        if not path.is_absolute():
            path = self._settings.project_root / path
        return path.resolve()

    def _require_preflight(self) -> None:
        if self._preflight_result is None or self._ontology_identity is None:
            raise PipelineInvariantError("pipeline preflight must complete before any stage")

    def _require_predecessor(self, stage: PipelineStage) -> None:
        predecessor = STAGE_PREDECESSOR[stage]
        if predecessor is None:
            return
        try:
            self._artifacts.validate_stage(
                self._run_id,
                predecessor.value,
                canonical=True,
            )
        except Exception as error:
            raise PipelineInvariantError(
                f"stage {stage.value} requires completed prerequisite {predecessor.value}"
            ) from error

    def _load_conversations(self, stage: PipelineStage) -> tuple[Conversation, ...]:
        conversations = self._read_records(stage, "conversations", Conversation)
        if not conversations:
            raise PipelineInvariantError(f"stage {stage.value} contains no conversations")
        return conversations

    def _read_records(
        self,
        stage: PipelineStage,
        name: str,
        model: type[ModelT],
    ) -> tuple[ModelT, ...]:
        try:
            return tuple(
                self._artifacts.read_jsonl(
                    self._run_id,
                    stage.value,
                    name,
                    model,
                    canonical=True,
                )
            )
        except Exception as error:
            raise PipelineInvariantError(
                f"stage {stage.value} has no valid {name} artifact"
            ) from error

    def _cumulative_records(self, predecessor: PipelineStage) -> dict[str, tuple[BaseModel, ...]]:
        manifest = self._artifacts.validate_stage(
            self._run_id,
            predecessor.value,
            canonical=True,
        )
        records: dict[str, tuple[BaseModel, ...]] = {}
        for artifact in manifest.artifacts:
            if artifact.name == "pipeline_manifests":
                continue
            model = self._artifacts.registry[artifact.name]
            records[artifact.name] = tuple(
                self._artifacts.read_jsonl(
                    self._run_id,
                    predecessor.value,
                    artifact.name,
                    model,
                    canonical=True,
                )
            )
        return records

    async def _fetch_bound_ontology(
        self,
        equations: Sequence[KnowledgeEquation],
    ) -> tuple[tuple[OntologyTerm, ...], tuple[OntologyRelation, ...]]:
        document_ids = tuple(
            sorted(
                {
                    binding.document_id
                    for equation in equations
                    for binding in equation.ontology_bindings
                    if binding.document_id is not None
                }
            )
        )
        terms = tuple(await self._ontology.fetch_terms(document_ids)) if document_ids else ()
        relations = (
            tuple(await self._ontology.fetch_relations(document_ids)) if document_ids else ()
        )
        term_ids = tuple(item.document_id for item in terms)
        if len(term_ids) != len(set(term_ids)):
            raise PipelineInvariantError("ontology fetched duplicate bound terms")
        if term_ids != document_ids:
            raise PipelineInvariantError(
                "ontology fetched terms do not exactly match bound document IDs"
            )
        _validate_ontology_bindings(equations, terms)
        unexpected_relation = next(
            (item for item in relations if item.source_document_id not in set(document_ids)),
            None,
        )
        if unexpected_relation is not None:
            raise PipelineInvariantError(
                "ontology fetched a relation outside actually bound document IDs"
            )
        term_relation_keys = sorted(
            (
                relation.source_document_id,
                relation.relation_type,
                relation.target_id,
            )
            for term in terms
            for relation in term.relations
        )
        fetched_relation_keys = sorted(
            (item.source_document_id, item.relation_type, item.target_id) for item in relations
        )
        if fetched_relation_keys != term_relation_keys:
            raise PipelineInvariantError(
                "ontology fetched relations contradict fetched bound terms"
            )
        return terms, tuple(
            sorted(
                relations,
                key=lambda item: (item.source_document_id, item.relation_type, item.target_id),
            )
        )

    async def _write_stage(
        self,
        stage: PipelineStage,
        records: Mapping[str, Sequence[BaseModel]],
    ) -> PipelineStageResult:
        identity = await self._recheck_ontology_identity()
        parent_snapshot_id = self._snapshots.head()
        materialized = {name: tuple(values) for name, values in records.items()}
        try:
            predecessor_traces = tuple(
                validate_usage_context_only_trace(cast(ModelTrace, item))
                for item in materialized.get("model_traces", ())
            )
        except (TypeError, ValueError) as error:
            raise PipelineInvariantError(
                "predecessor model traces are not usage/context-only"
            ) from error
        materialized["model_traces"] = _merge_models(
            predecessor_traces,
            tuple(
                usage_context_only_trace(trace) for trace in _model_trace_records(self._work_model)
            ),
        )
        knowledge_equations = tuple(
            cast(KnowledgeEquation, item) for item in materialized.get("knowledge_equations", ())
        )
        matched_document_ids = tuple(
            sorted(
                {
                    binding.document_id
                    for equation in knowledge_equations
                    for binding in equation.ontology_bindings
                    if binding.document_id is not None
                }
            )
        )
        record_counts = {name: len(values) for name, values in materialized.items()}
        record_counts["pipeline_manifests"] = 1
        pipeline_manifest = PipelineRunManifest(
            run_id=self._run_id,
            stage=stage,
            parent_snapshot_id=parent_snapshot_id,
            code_commit=self._code_commit,
            dataset_sha256=self._settings.dataset.archive_sha256,
            selected_directories=self._settings.dataset.selected_directories,
            ontology=OntologyRunIdentity(
                index=identity,
                normalization_mode=NORMALIZATION_MODE,
                matched_document_ids=matched_document_ids,
            ),
            embedding_enabled=False,
            concurrency=self._settings.evaluation.concurrency,
            record_counts=record_counts,
        )
        with self._artifacts.stage_writer(self._run_id, stage.value) as writer:
            for name in sorted(materialized):
                writer.write(name, materialized[name])
            writer.write("pipeline_manifests", (pipeline_manifest,))
        validated = self._artifacts.validate_stage(
            self._run_id,
            stage.value,
            canonical=True,
        )
        actual_counts = {item.name: item.record_count for item in validated.artifacts}
        if actual_counts != record_counts:
            raise PipelineInvariantError("stage artifact counts changed before snapshot commit")
        snapshot = self._snapshots.commit_stage(self._run_id, stage)
        return PipelineStageResult(
            run_id=self._run_id,
            stage=stage,
            snapshot_id=snapshot.snapshot_id,
            record_counts=record_counts,
        )

    async def _recheck_ontology_identity(self) -> IndexIdentity:
        if self._ontology_identity is None:
            raise PipelineInvariantError("ontology identity was not pinned by preflight")
        identity = await self._ontology.index_identity()
        if identity != self._ontology_identity:
            raise PipelineInvariantError("ontology index identity changed after preflight")
        return identity


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise PipelineInvariantError(f"unable to read configured BEAM archive: {path}") from error
    return digest.hexdigest()


def _validate_selected_directories(
    conversations: Sequence[Conversation],
    expected: tuple[int, int, int],
) -> None:
    values = tuple(
        conversation.source_metadata.get("beam_directory_id") for conversation in conversations
    )
    if not any(value is not None for value in values):
        return
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise PipelineInvariantError("BEAM conversations have invalid directory provenance")
    if cast(tuple[int, ...], values) != expected:
        raise PipelineInvariantError(
            "BEAM conversation directories do not match the configured selected subset"
        )


def _sessions(conversations: Sequence[Conversation]) -> Iterable[Session]:
    return (session for conversation in conversations for session in conversation.sessions)


def _exchanges(conversations: Sequence[Conversation]) -> Iterable[Exchange]:
    return (
        exchange
        for conversation in conversations
        for session in conversation.sessions
        for exchange in session.exchanges
    )


def _messages(conversations: Sequence[Conversation]) -> Iterable[Message]:
    return (
        message
        for exchange in _exchanges(conversations)
        for message in (exchange.user, exchange.assistant)
    )


def _input_hash(value: JsonObject) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _dedupe_revisions(
    equations: Iterable[KnowledgeEquation],
) -> tuple[KnowledgeEquation, ...]:
    records: dict[tuple[str, str], KnowledgeEquation] = {}
    for equation in equations:
        records.setdefault((equation.id, equation.revision), equation)
    return tuple(records.values())


def _unique_current(equations: Iterable[KnowledgeEquation]) -> tuple[KnowledgeEquation, ...]:
    by_id: dict[str, KnowledgeEquation] = {}
    for equation in equations:
        if equation.id in by_id:
            raise PipelineInvariantError(
                f"current KE records contain duplicate logical ID: {equation.id}"
            )
        by_id[equation.id] = equation
    return tuple(by_id[key] for key in sorted(by_id))


def _session_turn_kes(
    session: Session,
    turn_kes: Sequence[KnowledgeEquation],
) -> tuple[KnowledgeEquation, ...]:
    message_ids = {
        message.id
        for exchange in session.exchanges
        for message in (exchange.user, exchange.assistant)
    }
    return tuple(
        item
        for item in turn_kes
        if {span.message_id for span in item.evidence_refs}.intersection(message_ids)
    )


def _session_kes(memories: Sequence[SessionMemory]) -> tuple[KnowledgeEquation, ...]:
    return tuple(equation for memory in memories for equation in memory.knowledge_equations)


def _validate_current_history(
    history: Sequence[KnowledgeEquation],
    current: Sequence[KnowledgeEquation],
) -> None:
    current_by_id = {item.id: item for item in current}
    if len(current_by_id) != len(current):
        raise PipelineInvariantError("current KE records contain duplicate logical IDs")
    history_pairs = {(item.id, item.revision) for item in history}
    missing = next(
        (item for item in current if (item.id, item.revision) not in history_pairs),
        None,
    )
    if missing is not None:
        raise PipelineInvariantError("current KE revision is absent from audit history")
    latest: dict[str, KnowledgeEquation] = {}
    for item in history:
        latest[item.id] = item
    if latest != current_by_id:
        raise PipelineInvariantError("current KE records are not the latest audit revisions")


def _validate_raw_evidence(
    conversations: Sequence[Conversation],
    records: Sequence[KnowledgeEquation | AggregateNode],
) -> None:
    messages = {item.id: item for item in _messages(conversations)}
    for record in records:
        spans = (
            record.evidence_refs
            if isinstance(record, KnowledgeEquation)
            else record.evidence_closure
        )
        if not spans:
            raise PipelineInvariantError(f"record has no raw evidence closure: {record.id}")
        for span in spans:
            message = messages.get(span.message_id)
            if message is None:
                raise PipelineInvariantError(
                    f"evidence span references unknown canonical message: {span.message_id}"
                )
            try:
                message.validate_span(span)
            except ValueError as error:
                raise PipelineInvariantError(str(error)) from error


def _validate_ontology_bindings(
    equations: Sequence[KnowledgeEquation],
    terms: Sequence[OntologyTerm],
) -> None:
    terms_by_id = {item.document_id: item for item in terms}
    for term in terms:
        if any(relation.source_document_id != term.document_id for relation in term.relations):
            raise PipelineInvariantError(
                f"ontology term relations contradict their source document: {term.document_id}"
            )
    for equation in equations:
        for binding in equation.ontology_bindings:
            if binding.document_id is None:
                continue
            term = terms_by_id.get(binding.document_id)
            if term is None:
                raise PipelineInvariantError(
                    f"ontology binding has no fetched term: {binding.document_id}"
                )
            binding_relations = tuple(
                (item.relation_type, item.target_id) for item in binding.relations
            )
            term_relations = tuple((item.relation_type, item.target_id) for item in term.relations)
            if (
                binding.canonical_term != term.canonical_term
                or binding.source_type != term.source_type
                or binding.role != term.role
                or binding.aliases != term.aliases
                or binding_relations != term_relations
            ):
                raise PipelineInvariantError(
                    f"ontology binding contradicts fetched term: {binding.document_id}"
                )


def _validate_dags_by_conversation(
    conversations: Sequence[Conversation],
    memories: Sequence[SessionMemory],
    aggregates: Sequence[AggregateNode],
) -> None:
    memories_by_session = {item.session_id: item for item in memories}
    unclaimed = {item.id: item for item in aggregates}
    for conversation in sorted(conversations, key=lambda item: item.id):
        selected_memories = tuple(
            memories_by_session[session.id] for session in conversation.sessions
        )
        lower = _session_kes(selected_memories)
        allowed = {item.id for item in lower}
        selected_nodes: list[AggregateNode] = []
        for node in sorted(aggregates, key=lambda item: (item.depth, item.id)):
            if node.id not in unclaimed:
                continue
            if set(node.member_refs).issubset(allowed):
                selected_nodes.append(node)
                allowed.add(node.id)
                unclaimed.pop(node.id)
        validate_evidence_closure(selected_nodes, lower)
    if unclaimed:
        raise PipelineInvariantError(
            f"aggregate cannot be assigned to one Conversation: {min(unclaimed)}"
        )


def _merge_models(
    existing: Sequence[BaseModel],
    appended: Sequence[BaseModel],
) -> tuple[BaseModel, ...]:
    by_payload: dict[bytes, BaseModel] = {}
    for item in (*existing, *appended):
        by_payload.setdefault(canonical_json(item), item)
    return tuple(by_payload.values())


def _model_trace_records(model: object) -> tuple[ModelTrace, ...]:
    raw = getattr(model, _TRACE_RECORDS_ATTRIBUTE, ())
    if not isinstance(raw, Sequence):
        raise PipelineInvariantError("model trace recorder exposed an invalid record collection")
    records = cast(Sequence[object], raw)
    try:
        return tuple(ModelTrace.model_validate(item) for item in records)
    except (TypeError, ValueError) as error:
        raise PipelineInvariantError("model trace recorder exposed an invalid trace") from error
