"""The evaluation stage: orchestration for measuring a ke-ready run.

Split out of ``RuntimeFactory``, where the evaluation cluster was six of twelve
methods but about seventy percent of the code. Keeping them together made the
pipeline layer import the evaluation layer, so the layer that runs the system could
not be loaded without the layer that scores it.

The stage takes its collaborators explicitly and **does not hold the runtime
factory**. That restraint is the point: a stored factory would turn the removed
import cycle into a service locator, where the real coupling is invisible in every
signature and the dependency gate has nothing left to check. Instead:

- ``RuntimeContext`` carries the immutable run identity (state root, code commit).
- ``EvaluationPort`` is the narrow pipeline behaviour the stage calls.
- The shared infrastructure it needs -- settings, artifacts, snapshots, ontology and
  the work model -- arrives as named constructor arguments, built once by the
  composition root and passed to both objects.

Evaluation-run state lives here rather than in the factory: the judge and answer
clients, the token counter and the promoted snapshot id are properties of a
measurement run, and leaving them on the production runtime meant a pipeline-only
process carried evaluation state it never used.

Nothing about model dispatch, scoring, receipts, checkpoints or snapshots changes.
The method bodies moved verbatim; only where they get their collaborators changed.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from pydantic import BaseModel

from ke_memory_demo.answering import AnswerService
from ke_memory_demo.contracts import PipelineRunManifest, PipelineStage
from ke_memory_demo.core.json import JsonValue, canonical_json
from ke_memory_demo.domain.conversation import Conversation
from ke_memory_demo.domain.memory import AggregateNode, CoverageEntry, KnowledgeEquation
from ke_memory_demo.infra.telemetry import (
    InMemoryTraceRecorder,
    ModelTrace,
    usage_context_only_trace,
    validate_usage_context_only_trace,
)
from ke_memory_demo.retrieval.tokens import O200KTokenCounter
from ke_memory_demo.pipeline.ports import EvaluationPort, RuntimeContext, SnapshotModelT
from ke_memory_demo.evaluation.baseline_results import load_public_baseline_results
from ke_memory_demo.evaluation.gold_sources import (
    SourceCatalog,
    build_gold_source_mapping,
)
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
from ke_memory_demo.evaluation.questions import (
    normalize_questions,
    question_manifest_sha256,
)
from ke_memory_demo.evaluation.report import ReportInput, ReportWriter
from ke_memory_demo.evaluation.runner import EvaluationRunner
from ke_memory_demo.evaluation.runtime import (
    APPROVED_PLAN_SHA256,
    APPROVED_SPEC_SHA256,
    FIXED_QUESTIONS,
    evaluation_can_promote,
    finalize_evaluation_outputs,
)
from ke_memory_demo.pipeline.runtime import (
    RuntimeInvariantError,
    RuntimeStructuredModelClient,
    runtime_trace_records,
    snapshot_records_from_git,
    snapshot_stage_manifest_from_git,
    sorted_model_traces,
)
from ke_memory_demo.storage.checkpoints import CheckpointStore
from ke_memory_demo.storage.layout import validate_storage_name

if TYPE_CHECKING:  # pragma: no cover - imported for annotations only
    from collections.abc import Mapping
    from pathlib import Path

    from ke_memory_demo.infra.llm import StructuredModelClient
    from ke_memory_demo.ontology.elasticsearch import ElasticsearchVocabulary
    from ke_memory_demo.settings import AppSettings
    from ke_memory_demo.storage import ArtifactStore
    from ke_memory_demo.snapshots import GitSnapshotStore
    from ke_memory_demo.systems import KEMemorySystem


class EvaluationStage:
    """Runs the frozen evaluation against a verified ke-ready snapshot."""

    def __init__(
        self,
        *,
        context: RuntimeContext,
        port: EvaluationPort,
        settings: AppSettings,
        artifacts: ArtifactStore,
        snapshots: GitSnapshotStore,
        ontology: ElasticsearchVocabulary,
        work_model: StructuredModelClient,
    ) -> None:
        self._context = context
        self._port = port
        self.settings = settings
        self.artifacts = artifacts
        self.snapshots = snapshots
        self.ontology = ontology
        self.work_model = work_model
        # Evaluation-run state. Owned here so a pipeline-only runtime never holds it.
        self._token_counter = O200KTokenCounter()
        self._evaluation_clients: (
            tuple[RuntimeStructuredModelClient, RuntimeStructuredModelClient] | None
        ) = None
        self._evaluation_snapshot_id: str | None = None

    @property
    def _state_root(self) -> Path:
        return self._context.state_root

    @property
    def _code_commit(self) -> str:
        return self._context.code_commit

    async def build_ke_systems(
        self,
        run_id: str,
        snapshot_id: str,
        *,
        conversation_ids: frozenset[str] | None = None,
    ) -> Mapping[str, KEMemorySystem]:
        """Delegate to the pipeline port.

        Present so the moved bodies keep calling ``self.build_ke_systems`` unchanged;
        it forwards rather than reimplementing, so there is one definition of how
        systems are built. The signature mirrors ``EvaluationPort`` exactly: forwarding
        through ``*args: object`` would erase these types at every call site, which is
        how the split first lost them.
        """
        return await self._port.build_ke_systems(
            run_id, snapshot_id, conversation_ids=conversation_ids
        )

    def _snapshot_records(
        self,
        snapshot_id: str,
        run_id: str,
        artifact_name: str,
        model: type[SnapshotModelT],
    ) -> tuple[SnapshotModelT, ...]:
        """Delegate to the pipeline port, for the same reason as above.

        Generic in the record type so callers keep the concrete model they asked for
        rather than an unknown tuple.
        """
        return self._port.snapshot_records(snapshot_id, run_id, artifact_name, model)

    async def aclose(self) -> None:
        """Close the clients this stage created.

        The factory's ``aclose`` no longer knows about evaluation clients, so the
        stage that opened them closes them. Errors are collected rather than
        short-circuited, so one failing client cannot leave the others open.
        """
        terminal_error: Exception | None = None
        for client in self._evaluation_clients or ():
            try:
                await client.aclose()
            except Exception as error:  # noqa: BLE001 - re-raised below
                terminal_error = terminal_error or error
        if terminal_error is not None:
            raise RuntimeInvariantError(
                "evaluation resources did not close cleanly"
            ) from terminal_error

    def build_evaluation_clients(
        self,
    ) -> tuple[RuntimeStructuredModelClient, RuntimeStructuredModelClient]:
        if self._evaluation_clients is not None:
            return self._evaluation_clients
        answer_settings = self.settings.work.model_copy(
            update={"max_output_tokens": self.settings.retrieval.answer_max_output_tokens}
        )
        answer_recorder = InMemoryTraceRecorder()
        judge_recorder = InMemoryTraceRecorder()
        answer = cast(
            RuntimeStructuredModelClient,
            RuntimeStructuredModelClient.from_model_settings(
                answer_settings,
                api_key=self.settings.require_work_api_key(),
                supports_json_schema=True,
                trace_recorder=answer_recorder,
            ),
        )
        judge = cast(
            RuntimeStructuredModelClient,
            RuntimeStructuredModelClient.from_model_settings(
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
        evaluation_traces = sorted_model_traces(
            (
                *runtime_trace_records(self.work_model),
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
            or report_input.manifest.expected_questions != FIXED_QUESTIONS
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
            "model_traces": sorted_model_traces(
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
        manifest = snapshot_stage_manifest_from_git(
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
            records[artifact.name] = snapshot_records_from_git(
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
            spec_sha256=APPROVED_SPEC_SHA256,
            plan_sha256=APPROVED_PLAN_SHA256,
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
