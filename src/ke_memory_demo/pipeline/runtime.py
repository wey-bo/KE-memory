from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime
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

from ke_memory_demo.answering import AnswerService
from ke_memory_demo.core.json import JsonValue, canonical_json
from ke_memory_demo.domain import (
    AggregateNode,
    Conversation,
    CoverageEntry,
    Evidence,
    Exchange,
    KnowledgeEquation,
    RunScope,
)
from ke_memory_demo.evaluation.baseline_results import load_public_baseline_results
from ke_memory_demo.evaluation.gold_sources import SourceCatalog, build_gold_source_mapping
from ke_memory_demo.evaluation.judge import JudgeService
from ke_memory_demo.evaluation.manifest import ExperimentManifest
from ke_memory_demo.evaluation.metrics import (
    aggregate_operation_usage,
    compute_metrics,
    select_turn_ke_audits,
)
from ke_memory_demo.evaluation.models import (
    EvaluationRun,
    GoldSourceStatus,
    ProbeQuestion,
    ReportDocument,
)
from ke_memory_demo.evaluation.preflight import EvaluationPreflight, PreflightCheckFailure
from ke_memory_demo.evaluation.questions import normalize_questions, question_manifest_sha256
from ke_memory_demo.evaluation.report import (
    ReportInput,
    ReportWriter,
    materialize_report_documents,
)
from ke_memory_demo.evaluation.runner import EvaluationRunner
from ke_memory_demo.infra.llm import StructuredModelClient
from ke_memory_demo.infra.telemetry import (
    InMemoryTraceRecorder,
    ModelTrace,
    TraceContext,
    TraceRecorder,
    UsageRecord,
    usage_context_only_trace,
    validate_usage_context_only_trace,
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
    resolve_config_layout,
)
from ke_memory_demo.snapshots import GitSnapshotStore
from ke_memory_demo.storage import (
    ArtifactStore,
    MemoryIndex,
    StateLayout,
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

from .checkpoints import CheckpointStore
from .models import (
    EVALUATION_ARTIFACT_REGISTRY,
    PIPELINE_ARTIFACT_REGISTRY,
    PipelineRunManifest,
    PipelineStage,
)
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


def evaluation_can_promote(run: EvaluationRun, *, smoke: bool) -> bool:
    expected_ids = run.expected_question_ids
    return (
        not smoke
        and run.status.value == "complete"
        and len(expected_ids) == _FIXED_QUESTIONS
        and tuple(item.question_id for item in run.answers) == expected_ids
        and tuple(item.question_id for item in run.judgements) == expected_ids
        and not run.failures
    )


def materialize_evaluation_report(
    state_root: Path,
    run_id: str,
    snapshot_id: str,
) -> tuple[Path, ...]:
    validate_storage_name(run_id, label="run ID")
    artifacts = ArtifactStore(
        state_root,
        registry={
            **PIPELINE_ARTIFACT_REGISTRY,
            **dict(EVALUATION_ARTIFACT_REGISTRY),
        },
    )
    snapshots = GitSnapshotStore.init(artifacts.root, artifacts)
    verified = snapshots.verify(snapshot_id, run_id, PipelineStage.EVALUATION_COMPLETE)
    documents = _snapshot_records_from_git(
        artifacts.root,
        verified.snapshot_id,
        run_id,
        "report_documents",
        ReportDocument,
        stage=PipelineStage.EVALUATION_COMPLETE,
    )
    return materialize_report_documents(
        documents,
        artifacts.root / "exports" / run_id,
        layout=artifacts.layout,
    )


def finalize_evaluation_outputs(
    *,
    run: EvaluationRun,
    smoke: bool,
    state_root: Path,
    run_id: str,
    documents: Sequence[ReportDocument],
    promote_complete: Callable[[], str],
) -> str | None:
    validate_storage_name(run_id, label="run ID")
    validated_run = EvaluationRun.model_validate(run)
    validated_documents = tuple(ReportDocument.model_validate(item) for item in documents)
    if smoke:
        return None
    if not evaluation_can_promote(validated_run, smoke=False):
        layout = StateLayout(state_root)
        materialize_report_documents(
            validated_documents,
            layout.root / "exports" / run_id / "incomplete",
            layout=layout,
        )
        return None
    snapshot_id = promote_complete()
    if _GIT_SHA.fullmatch(snapshot_id) is None:
        raise RuntimeInvariantError("evaluation promotion returned an invalid snapshot ID")
    return snapshot_id


def _read_only_git_env() -> dict[str, str]:
    return {
        **os.environ,
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
    }


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
        self._evaluation_clients: (
            tuple[_RuntimeStructuredModelClient, _RuntimeStructuredModelClient] | None
        ) = None
        self._evaluation_snapshot_id: str | None = None

    @classmethod
    def from_paths(
        cls,
        config_root: Path | ConfigLayout,
        state_root: Path,
    ) -> RuntimeFactory:
        settings = load_settings(config_root)
        artifacts = ArtifactStore(
            state_root,
            registry={
                **PIPELINE_ARTIFACT_REGISTRY,
                **dict(EVALUATION_ARTIFACT_REGISTRY),
            },
        )
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
    ) -> tuple[_RuntimeStructuredModelClient, _RuntimeStructuredModelClient]:
        if self._evaluation_clients is not None:
            return self._evaluation_clients
        answer_settings = self.settings.work.model_copy(
            update={"max_output_tokens": self.settings.retrieval.answer_max_output_tokens}
        )
        answer_recorder = InMemoryTraceRecorder()
        judge_recorder = InMemoryTraceRecorder()
        answer = cast(
            _RuntimeStructuredModelClient,
            _RuntimeStructuredModelClient.from_model_settings(
                answer_settings,
                api_key=self.settings.require_work_api_key(),
                supports_json_schema=True,
                trace_recorder=answer_recorder,
            ),
        )
        judge = cast(
            _RuntimeStructuredModelClient,
            _RuntimeStructuredModelClient.from_model_settings(
                self.settings.judge,
                api_key=self.settings.require_judge_api_key(),
                supports_json_schema=True,
                trace_recorder=judge_recorder,
            ),
        )
        clients = (answer, judge)
        self._evaluation_clients = clients
        return clients

    @property
    def evaluation_snapshot_id(self) -> str | None:
        return self._evaluation_snapshot_id

    async def build_ke_systems(
        self,
        run_id: str,
        snapshot_id: str,
        *,
        conversation_ids: frozenset[str] | None = None,
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
        available_conversation_ids = {item.id for item in conversations}
        if conversation_ids is not None:
            missing = sorted(conversation_ids.difference(available_conversation_ids))
            if missing:
                raise RuntimeInvariantError(
                    f"requested Conversation is absent from the snapshot: {missing[0]}"
                )
            conversations = tuple(item for item in conversations if item.id in conversation_ids)
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

    async def run_evaluation(
        self,
        run_id: str,
        snapshot_id: str | None,
        *,
        smoke: bool,
    ) -> EvaluationRun:
        validate_storage_name(run_id, label="run ID")
        selected_snapshot = snapshot_id or self.snapshots.head()
        if selected_snapshot is None:
            raise RuntimeInvariantError("evaluation requires an existing ke-ready snapshot")
        verification = self.snapshots.verify(
            selected_snapshot,
            run_id,
            PipelineStage.KE_READY,
        )
        selected_snapshot = verification.snapshot_id
        manifests = self._snapshot_records(
            selected_snapshot,
            run_id,
            "pipeline_manifests",
            PipelineRunManifest,
        )
        conversations = self._snapshot_records(
            selected_snapshot,
            run_id,
            "conversations",
            Conversation,
        )
        if len(manifests) != 1:
            raise RuntimeInvariantError(
                "verified ke-ready snapshot must contain exactly one pipeline manifest"
            )
        questions = tuple(sorted(normalize_questions(conversations), key=lambda item: item.id))
        if len(questions) != self.settings.dataset.expected_questions:
            raise RuntimeInvariantError("verified snapshot question count does not match settings")
        selected_questions = questions[:1] if smoke else questions
        if not selected_questions:
            raise RuntimeInvariantError("evaluation snapshot contains no questions")
        selected_conversation_ids = frozenset(item.conversation_id for item in selected_questions)
        systems = await self.build_ke_systems(
            run_id,
            selected_snapshot,
            conversation_ids=selected_conversation_ids,
        )

        conversation_by_id = {item.id: item for item in conversations}
        gold_mappings = tuple(
            build_gold_source_mapping(
                question.raw_metadata,
                SourceCatalog.from_conversation(conversation_by_id[question.conversation_id]),
                question_id=question.id,
            )
            for question in selected_questions
        )
        answer_client, judge_client = self.build_evaluation_clients()
        answer_services = {
            conversation_id: AnswerService(answer_client, token_counter=self._token_counter)
            for conversation_id in systems
        }
        judge = JudgeService(judge_client)
        manifest = self._evaluation_manifest(
            pipeline_manifest=manifests[0],
            snapshot_id=selected_snapshot,
            questions=selected_questions,
            gold_mappings=gold_mappings,
            answer_service=next(iter(answer_services.values())),
            judge=judge,
        )
        runner = EvaluationRunner(
            systems=systems,
            answer_services=answer_services,
            judge=judge,
            checkpoints=CheckpointStore(self._state_root, run_id),
            manifest=manifest,
        )
        run = await runner.run(selected_questions)
        self._evaluation_snapshot_id = None
        if smoke:
            return run

        knowledge_equations = self._snapshot_records(
            selected_snapshot,
            run_id,
            "knowledge_equations",
            KnowledgeEquation,
        )
        current_knowledge_equations = self._snapshot_records(
            selected_snapshot,
            run_id,
            "current_knowledge_equations",
            KnowledgeEquation,
        )
        coverage = self._snapshot_records(
            selected_snapshot,
            run_id,
            "coverage",
            CoverageEntry,
        )
        aggregates = self._snapshot_records(
            selected_snapshot,
            run_id,
            "aggregates",
            AggregateNode,
        )
        predecessor_traces = self._snapshot_records(
            selected_snapshot,
            run_id,
            "model_traces",
            ModelTrace,
        )
        evaluation_traces = _sorted_model_traces(
            (
                *_runtime_trace_records(self.work_model),
                *answer_client.trace_records,
                *judge_client.trace_records,
            )
        )
        computed = compute_metrics(
            run=run,
            questions=selected_questions,
            gold_mappings=gold_mappings,
            conversations=conversations,
            current_knowledge_equations=current_knowledge_equations,
            aggregates=aggregates,
        )
        baseline_results = load_public_baseline_results(
            self.settings.project_root / "data" / "baselines" / "public_results.toml"
        )
        audits = select_turn_ke_audits(
            conversations,
            coverage,
            knowledge_equations,
            aggregates,
        )
        report_input = ReportInput(
            manifest=manifest,
            run=run,
            questions=selected_questions,
            gold_mappings=gold_mappings,
            question_metrics=computed.question_metrics,
            aggregate_metrics=computed.aggregate_metrics,
            operation_usage_metrics=aggregate_operation_usage(
                (*predecessor_traces, *evaluation_traces),
                authoritative_usage={
                    "common-answer": tuple(item.usage for item in run.answers),
                    "independent-judge": tuple(item.usage for item in run.judgements),
                },
            ),
            baseline_public_results=baseline_results,
            turn_ke_audits=audits,
        )
        documents = ReportWriter.build(report_input)
        if evaluation_can_promote(run, smoke=False):
            current_identity = await self.ontology.index_identity()
            if current_identity != manifests[0].ontology.index:
                raise RuntimeInvariantError(
                    "ontology index identity changed before evaluation promotion"
                )
        self._evaluation_snapshot_id = finalize_evaluation_outputs(
            run=run,
            smoke=False,
            state_root=self._state_root,
            run_id=run_id,
            documents=documents,
            promote_complete=lambda: self._promote_evaluation_complete(
                pipeline_manifest=manifests[0],
                report_input=report_input,
                report_documents=documents,
                evaluation_traces=evaluation_traces,
            ),
        )
        return run

    def _promote_evaluation_complete(
        self,
        *,
        pipeline_manifest: PipelineRunManifest,
        report_input: ReportInput,
        report_documents: Sequence[ReportDocument],
        evaluation_traces: Sequence[ModelTrace],
    ) -> str:
        run = report_input.run
        if (
            pipeline_manifest.stage is not PipelineStage.KE_READY
            or pipeline_manifest.run_id != report_input.manifest.run_id
            or report_input.manifest.expected_questions != _FIXED_QUESTIONS
        ):
            raise RuntimeInvariantError(
                "evaluation-complete inputs do not match the verified ke-ready run"
            )
        if not evaluation_can_promote(run, smoke=False):
            raise RuntimeInvariantError(
                "evaluation-complete promotion requires exact complete 60/60 results"
            )
        if self.snapshots.head() != run.ke_ready_snapshot_id:
            raise RuntimeInvariantError(
                "evaluation-complete promotion requires the verified ke-ready snapshot at HEAD"
            )
        mapped_count = sum(
            item.status is GoldSourceStatus.MAPPED for item in report_input.gold_mappings
        )
        unmappable_count = sum(
            item.status is GoldSourceStatus.UNMAPPABLE for item in report_input.gold_mappings
        )
        if (mapped_count, unmappable_count) != (54, 6):
            raise RuntimeInvariantError(
                "evaluation-complete promotion requires 54 mapped and 6 unmappable gold records"
            )

        records = self._cumulative_evaluation_records(
            pipeline_manifest.run_id,
            run.ke_ready_snapshot_id,
        )
        try:
            existing_traces = tuple(
                validate_usage_context_only_trace(cast(ModelTrace, item))
                for item in records.get("model_traces", ())
            )
        except (TypeError, ValueError) as error:
            raise RuntimeInvariantError(
                "ke-ready predecessor model traces are not usage/context-only"
            ) from error
        answers = tuple(sorted(run.answers, key=lambda item: item.question_id))
        judgements = tuple(sorted(run.judgements, key=lambda item: item.question_id))
        failures = tuple(
            sorted(
                run.failures,
                key=lambda item: (item.question_id, item.stage, item.error_type),
            )
        )
        question_metrics = tuple(
            sorted(report_input.question_metrics, key=lambda item: item.question_id)
        )
        operation_usage = tuple(
            sorted(report_input.operation_usage_metrics, key=lambda item: item.operation)
        )
        documents = tuple(sorted(report_documents, key=lambda item: item.name))
        new_records: dict[str, tuple[BaseModel, ...]] = {
            "probe_questions": tuple(report_input.questions),
            "gold_source_mappings": tuple(report_input.gold_mappings),
            "experiment_manifests": (report_input.manifest,),
            "retrieval_traces": tuple(item.retrieval_trace for item in answers),
            "question_answers": answers,
            "judge_results": judgements,
            "evaluation_failures": failures,
            "evaluation_runs": (run,),
            "question_metrics": question_metrics,
            "aggregate_metrics": tuple(report_input.aggregate_metrics),
            "operation_usage_metrics": operation_usage,
            "baseline_public_results": tuple(report_input.baseline_public_results),
            "turn_ke_audits": tuple(report_input.turn_ke_audits),
            "report_documents": documents,
            "model_traces": _sorted_model_traces(
                (
                    *existing_traces,
                    *(usage_context_only_trace(trace) for trace in evaluation_traces),
                )
            ),
        }
        records.update(new_records)
        record_counts = {name: len(values) for name, values in records.items()}
        record_counts["pipeline_manifests"] = 1
        manifest = PipelineRunManifest(
            run_id=pipeline_manifest.run_id,
            stage=PipelineStage.EVALUATION_COMPLETE,
            parent_snapshot_id=run.ke_ready_snapshot_id,
            code_commit=self._code_commit,
            dataset_sha256=pipeline_manifest.dataset_sha256,
            selected_directories=pipeline_manifest.selected_directories,
            ontology=pipeline_manifest.ontology,
            embedding_enabled=False,
            concurrency=pipeline_manifest.concurrency,
            record_counts=record_counts,
        )
        with self.artifacts.stage_writer(
            pipeline_manifest.run_id,
            PipelineStage.EVALUATION_COMPLETE.value,
        ) as writer:
            for name in sorted(records):
                writer.write(name, records[name])
            writer.write("pipeline_manifests", (manifest,))
        validated = self.artifacts.validate_stage(
            pipeline_manifest.run_id,
            PipelineStage.EVALUATION_COMPLETE.value,
            canonical=True,
        )
        actual_counts = {item.name: item.record_count for item in validated.artifacts}
        if actual_counts != record_counts:
            raise RuntimeInvariantError(
                "evaluation-complete artifact counts changed before snapshot commit"
            )
        committed = self.snapshots.commit_stage(
            pipeline_manifest.run_id,
            PipelineStage.EVALUATION_COMPLETE,
        )
        verified = self.snapshots.verify(
            committed.snapshot_id,
            pipeline_manifest.run_id,
            PipelineStage.EVALUATION_COMPLETE,
        )
        return verified.snapshot_id

    def _cumulative_evaluation_records(
        self,
        run_id: str,
        snapshot_id: str,
    ) -> dict[str, tuple[BaseModel, ...]]:
        manifest = _snapshot_stage_manifest_from_git(
            self._state_root,
            snapshot_id,
            run_id,
            PipelineStage.KE_READY,
        )
        records: dict[str, tuple[BaseModel, ...]] = {}
        for artifact in manifest.artifacts:
            if artifact.name == "pipeline_manifests":
                continue
            try:
                model = self.artifacts.registry[artifact.name]
            except KeyError as error:
                raise RuntimeInvariantError(
                    f"verified snapshot contains an unknown artifact: {artifact.name}"
                ) from error
            records[artifact.name] = _snapshot_records_from_git(
                self._state_root,
                snapshot_id,
                run_id,
                artifact.name,
                model,
                stage=PipelineStage.KE_READY,
            )
        try:
            for trace in records.get("model_traces", ()):
                validate_usage_context_only_trace(cast(ModelTrace, trace))
        except (TypeError, ValueError) as error:
            raise RuntimeInvariantError(
                "ke-ready predecessor model traces are not usage/context-only"
            ) from error
        return records

    def _evaluation_manifest(
        self,
        *,
        pipeline_manifest: PipelineRunManifest,
        snapshot_id: str,
        questions: Sequence[ProbeQuestion],
        gold_mappings: Sequence[BaseModel],
        answer_service: AnswerService,
        judge: JudgeService,
    ) -> ExperimentManifest:
        gold_payload = cast(
            JsonValue,
            [item.model_dump(mode="json") for item in gold_mappings],
        )
        return ExperimentManifest(
            run_id=pipeline_manifest.run_id,
            code_commit=self._code_commit,
            spec_sha256=_APPROVED_SPEC_SHA256,
            plan_sha256=_APPROVED_PLAN_SHA256,
            ke_ready_snapshot_id=snapshot_id,
            dataset_sha256=pipeline_manifest.dataset_sha256,
            selected_directories=pipeline_manifest.selected_directories,
            expected_sessions=self.settings.dataset.expected_sessions,
            expected_exchanges=self.settings.dataset.expected_exchanges,
            expected_questions=len(questions),
            question_manifest_sha256=question_manifest_sha256(questions),
            gold_mapping_sha256=hashlib.sha256(canonical_json(gold_payload)).hexdigest(),
            ontology=pipeline_manifest.ontology,
            work_model=answer_service.model_name,
            work_base_url=self.settings.work.base_url,
            judge_model=judge.model_name,
            judge_base_url=self.settings.judge.base_url,
            answer_prompt_sha256=answer_service.prompt_sha256,
            judge_prompt_sha256=judge.prompt_sha256,
            embedding_enabled=False,
            concurrency=pipeline_manifest.concurrency,
            created_at=datetime.now(UTC),
        )

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
        config_root: Path | ConfigLayout,
        state_root: Path,
        run_id: str,
        snapshot_id: str,
    ) -> None:
        self._config_root = (
            config_root.project_root
            if isinstance(config_root, ConfigLayout)
            else config_root.expanduser()
        )
        self._state_root = state_root.expanduser().resolve()
        self._run_id = run_id
        self._snapshot_id = snapshot_id
        self._dotenv_path = self._config_root / ".env.local"
        self._dotenv_failure: str | None = None
        self._settings: AppSettings | None = None
        self._settings_error = "SettingsUnavailable"
        try:
            layout = (
                config_root
                if isinstance(config_root, ConfigLayout)
                else resolve_config_layout(config_root)
            )
        except Exception as error:
            self._settings_error = type(error).__name__
        else:
            self._config_root = layout.project_root
            self._dotenv_path = layout.project_root / ".env.local"
            self._dotenv_failure = self._dotenv_permission_failure()
            if self._dotenv_failure is None:
                try:
                    self._settings = load_settings(layout)
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
            env=_read_only_git_env(),
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
    config_root: Path | ConfigLayout,
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


def _snapshot_stage_manifest_from_git(
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
    if _GIT_SHA.fullmatch(snapshot_id) is None:
        raise RuntimeInvariantError("snapshot ID must be a full Git SHA")
    completed = subprocess.run(
        ("git", "-C", str(state_root), "show", f"{snapshot_id}:{path}"),
        check=False,
        capture_output=True,
        env=_read_only_git_env(),
    )
    if completed.returncode != 0:
        raise RuntimeInvariantError(f"verified snapshot is missing {description}")
    return completed.stdout


def _snapshot_records_from_git(
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


def _runtime_trace_records(model: object) -> tuple[ModelTrace, ...]:
    raw = getattr(model, "trace_records", ())
    if not isinstance(raw, Sequence):
        raise RuntimeInvariantError("evaluation model exposed invalid trace records")
    try:
        return tuple(ModelTrace.model_validate(item) for item in cast(Sequence[object], raw))
    except (TypeError, ValueError) as error:
        raise RuntimeInvariantError("evaluation model exposed an invalid trace") from error


def _sorted_model_traces(traces: Iterable[ModelTrace]) -> tuple[ModelTrace, ...]:
    validated = tuple(ModelTrace.model_validate(item) for item in traces)
    return tuple(sorted(validated, key=canonical_json))


def _git_text(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(root), *arguments),
        check=False,
        capture_output=True,
        text=True,
        env=_read_only_git_env(),
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
        env=_read_only_git_env(),
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
        env=_read_only_git_env(),
    )
    commit = completed.stdout.strip()
    if completed.returncode != 0 or len(commit) != 40:
        raise PipelineInvariantError("unable to resolve the full code Git SHA")
    return commit
