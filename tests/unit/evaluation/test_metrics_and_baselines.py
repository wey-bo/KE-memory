from __future__ import annotations

from datetime import date
import hashlib
from pathlib import Path
from typing import Literal

import pytest

from ke_memory_demo.domain import (
    AggregateNode,
    AggregateNodeKind,
    ConceptRef,
    Conversation,
    CoverageEntry,
    CoverageStatus,
    Evidence,
    Exchange,
    KnowledgeEquation,
    KnowledgeLevel,
    Lifecycle,
    Message,
    MessageRole,
    MessageSpan,
    Modality,
    OntologyBinding,
    OntologyBindingStatus,
    OntologyRole,
    Polarity,
    Session,
    Speaker,
    TemporalMetadata,
    ToolEvent,
    ToolEventKind,
)
from ke_memory_demo.evaluation import (
    EvaluationFailure,
    EvaluationRun,
    EvaluationStatus,
    GoldSourceMapping,
    GoldSourceStatus,
    JudgeResult,
    ProbeQuestion,
    QuestionAnswer,
    QuestionCategory,
    ReportDocument,
    RubricJudgement,
)
from ke_memory_demo.evaluation.baseline_results import load_public_baseline_results
from ke_memory_demo.evaluation.metrics import (
    QuestionMetricInput,
    aggregate_operation_usage,
    compute_metrics,
    compute_question_metrics,
    select_turn_ke_audits,
)
from ke_memory_demo.evaluation.report import ReportInvariantError
from ke_memory_demo.infra.telemetry import ModelTrace, TraceContext, UsageRecord
from ke_memory_demo.evaluation.runtime import (
    evaluation_can_promote,
    finalize_evaluation_outputs,
)
from ke_memory_demo.retrieval import (
    QueryGroundingSpan,
    QueryKE,
    QuerySurfaceGrounding,
    RetrievalTrace,
)


def test_source_metrics_exclude_only_unmappable_gold() -> None:
    fixture = _memory_fixture()
    mapped = compute_question_metrics(_question_metric_input(fixture, mapped=True))
    unmapped = compute_question_metrics(_question_metric_input(fixture, mapped=False))

    assert mapped.source_recall == 0.5
    assert mapped.complete_evidence is False
    assert mapped.citation_valid is True
    assert mapped.citation_traceable is True
    assert unmapped.answer_score == 1.0
    assert unmapped.source_recall is None
    assert unmapped.complete_evidence is None


def test_citation_traceability_requires_a_canonical_raw_span_closure() -> None:
    fixture = _memory_fixture()
    metric_input = _question_metric_input(fixture, mapped=True)
    evidence = metric_input.answer.evidence[0].model_copy(
        update={"system_record_ids": ("missing-record",)}
    )
    answer = metric_input.answer.model_copy(
        update={"evidence": (evidence,), "citations": (evidence.evidence_id,)}
    )

    metrics = compute_question_metrics(metric_input.model_copy(update={"answer": answer}))

    assert metrics.citation_valid is True
    assert metrics.citation_traceable is False


def test_aggregates_cover_all_categories_and_incomplete_runs_withhold_means() -> None:
    fixture = _memory_fixture()
    questions = tuple(
        _question(f"q-{index:02d}", category) for index, category in enumerate(QuestionCategory)
    )
    answers = tuple(
        _answer(question, fixture.first_ke, fixture.first_exchange) for question in questions
    )
    judgements = tuple(_judgement(question.id) for question in questions)
    mappings = tuple(
        GoldSourceMapping(
            question_id=question.id,
            status=GoldSourceStatus.MAPPED,
            source_numbers=(1,),
            source_exchange_ids=(fixture.first_exchange.id,),
            matched_paths=("$.source_chat_id",),
        )
        for question in questions
    )
    complete = _run(questions, answers, judgements)

    computed = compute_metrics(
        run=complete,
        questions=questions,
        gold_mappings=mappings,
        conversations=(fixture.conversation,),
        current_knowledge_equations=fixture.knowledge_equations,
        aggregates=(fixture.aggregate,),
    )

    assert len(computed.question_metrics) == 10
    assert [item.scope for item in computed.aggregate_metrics] == [
        "overall",
        "conversation:conversation-1",
        *(f"category:{category.value}" for category in QuestionCategory),
    ]
    assert all(item.question_count > 0 for item in computed.aggregate_metrics)

    incomplete = EvaluationRun(
        manifest_hash="a" * 64,
        expected_question_ids=tuple(question.id for question in questions),
        question_manifest_sha256="b" * 64,
        ke_ready_snapshot_id="c" * 40,
        status=EvaluationStatus.INCOMPLETE,
        answers=answers,
        judgements=judgements[:-1],
        failures=(
            EvaluationFailure(
                question_id=questions[-1].id,
                stage="judge",
                error_type="TimeoutError",
                message="judge failed",
            ),
        ),
    )
    diagnostics = compute_metrics(
        run=incomplete,
        questions=questions,
        gold_mappings=mappings,
        conversations=(fixture.conversation,),
        current_knowledge_equations=fixture.knowledge_equations,
        aggregates=(fixture.aggregate,),
    )

    assert len(diagnostics.question_metrics) == 9
    assert [item.scope for item in diagnostics.aggregate_metrics] == [
        "overall",
        "conversation:conversation-1",
        *(f"category:{category.value}" for category in QuestionCategory),
    ]
    overall = diagnostics.aggregate_metrics[0]
    assert overall.question_count == 10
    assert overall.completed_question_count == 10
    assert overall.scored_question_count == 9
    assert overall.answer_score_sum == 9.0
    assert overall.answer_score_mean is None
    missing_category = diagnostics.aggregate_metrics[-1]
    assert missing_category.question_count == 1
    assert missing_category.completed_question_count == 1
    assert missing_category.scored_question_count == 0
    assert missing_category.answer_score_mean is None


def test_operation_usage_groups_exact_operations_and_never_partially_sums_cost() -> None:
    records = (
        _trace("ke-match", "match-2", cost=None, input_tokens=7),
        _trace("common-answer", "answer-1", cost=0.2, input_tokens=11),
        _trace("ke-match", "match-1", cost=0.1, input_tokens=5),
    )

    metrics = aggregate_operation_usage(records)

    assert [item.operation for item in metrics] == ["common-answer", "ke-match"]
    assert metrics[0].provider_cost == 0.2
    assert metrics[1].call_count == 2
    assert metrics[1].input_tokens == 12
    assert metrics[1].provider_cost is None


def test_checkpointed_answer_usage_replaces_missing_or_live_operation_traces() -> None:
    checkpointed = UsageRecord(
        request_id="cached-answer",
        model="gpt-5.4",
        latency_seconds=0.75,
        input_tokens=30,
        output_tokens=4,
        total_tokens=34,
        provider_cost=0.3,
    )

    [metrics] = aggregate_operation_usage(
        (_trace("common-answer", "live-answer", cost=0.2, input_tokens=11),),
        authoritative_usage={"common-answer": (checkpointed,)},
    )

    assert metrics.call_count == 1
    assert metrics.input_tokens == 30
    assert metrics.provider_cost == 0.3


def test_turn_ke_audits_use_the_first_deterministic_examples() -> None:
    fixture = _memory_fixture()

    audits = select_turn_ke_audits(
        (fixture.conversation,),
        fixture.coverage,
        fixture.knowledge_equations,
        (fixture.aggregate,),
    )

    assert [item.audit_kind for item in audits] == [
        "conversation_first",
        "tool_event",
        "unresolved",
        "lifecycle",
        "cross_session",
    ]
    assert audits[0].exchange_ids == (fixture.first_exchange.id,)
    assert audits[1].exchange_ids == (fixture.tool_exchange.id,)
    assert audits[2].exchange_ids == (fixture.tool_exchange.id,)
    assert audits[3].exchange_ids == (
        fixture.first_exchange.id,
        fixture.update_exchange.id,
    )
    assert audits[4].aggregate_ids == (fixture.aggregate.id,)


def test_public_baselines_are_sourced_separate_records_and_never_ranked(
    project_root: Path,
) -> None:
    records = load_public_baseline_results(project_root / "data/baselines/public_results.toml")

    assert {item.system for item in records} == {"mem0", "graphiti", "hindsight", "mempalace"}
    assert len(records) == 9
    assert all(item.retrieved_on == date(2026, 7, 17) for item in records)
    assert all(item.source_url.startswith("https://") for item in records)
    assert all(
        "not_reproduced" in item.statuses or "not_found" in item.statuses for item in records
    )
    assert not any(hasattr(item, "rank") for item in records)
    assert {
        (item.system, item.dataset, item.score) for item in records if item.score is not None
    } == {
        ("mem0", "BEAM", 64.1),
        ("mem0", "BEAM", 48.6),
        ("mem0", "LoCoMo", 91.6),
        ("mem0", "LongMemEval", 94.8),
        ("hindsight", "LongMemEval", 94.6),
        ("mempalace", "LongMemEval", 96.6),
        ("mempalace", "LongMemEval", 98.4),
        ("mempalace", "LoCoMo", 88.9),
    }


def test_only_exact_formal_sixty_question_run_can_promote() -> None:
    fixture = _memory_fixture()
    questions = tuple(
        _question(f"q-{index:02d}", tuple(QuestionCategory)[index % 10]) for index in range(60)
    )
    answers = tuple(
        _answer(question, fixture.first_ke, fixture.first_exchange) for question in questions
    )
    judgements = tuple(_judgement(question.id) for question in questions)
    complete = _run(questions, answers, judgements)
    incomplete = complete.model_copy(
        update={
            "status": EvaluationStatus.INCOMPLETE,
            "judgements": judgements[:-1],
            "failures": (
                EvaluationFailure(
                    question_id=questions[-1].id,
                    stage="judge",
                    error_type="TimeoutError",
                    message="judge failed",
                ),
            ),
        }
    )

    assert evaluation_can_promote(complete, smoke=False) is True
    assert evaluation_can_promote(complete, smoke=True) is False
    assert evaluation_can_promote(incomplete, smoke=False) is False


def test_evaluation_artifact_registry_uses_the_exact_result_models() -> None:
    from ke_memory_demo.evaluation import (
        AggregateMetrics,
        BaselinePublicResult,
        OperationUsageMetrics,
        QuestionMetrics,
        ReportDocument,
        TurnKEAuditCase,
    )
    from ke_memory_demo.pipeline import EVALUATION_ARTIFACT_REGISTRY

    assert {
        name: EVALUATION_ARTIFACT_REGISTRY[name]
        for name in (
            "question_metrics",
            "aggregate_metrics",
            "operation_usage_metrics",
            "baseline_public_results",
            "turn_ke_audits",
            "report_documents",
        )
    } == {
        "question_metrics": QuestionMetrics,
        "aggregate_metrics": AggregateMetrics,
        "operation_usage_metrics": OperationUsageMetrics,
        "baseline_public_results": BaselinePublicResult,
        "turn_ke_audits": TurnKEAuditCase,
        "report_documents": ReportDocument,
    }


def test_incomplete_finalization_exports_diagnostics_without_promoting(tmp_path: Path) -> None:
    fixture = _memory_fixture()
    questions = tuple(
        _question(f"q-{index:02d}", tuple(QuestionCategory)[index % 10]) for index in range(60)
    )
    answers = tuple(
        _answer(question, fixture.first_ke, fixture.first_exchange) for question in questions
    )
    judgements = tuple(_judgement(question.id) for question in questions)
    incomplete = EvaluationRun(
        manifest_hash="a" * 64,
        expected_question_ids=tuple(question.id for question in questions),
        question_manifest_sha256="b" * 64,
        ke_ready_snapshot_id="c" * 40,
        status=EvaluationStatus.INCOMPLETE,
        answers=answers,
        judgements=judgements[:-1],
        failures=(
            EvaluationFailure(
                question_id=questions[-1].id,
                stage="judge",
                error_type="TimeoutError",
                message="judge failed",
            ),
        ),
    )
    promoted: list[bool] = []

    snapshot_id = finalize_evaluation_outputs(
        run=incomplete,
        smoke=False,
        state_root=tmp_path,
        run_id="run-1",
        documents=_report_documents(),
        promote_complete=lambda: promoted.append(True) or "d" * 40,
    )

    assert snapshot_id is None
    assert promoted == []
    assert sorted(path.name for path in (tmp_path / "exports/run-1/incomplete").iterdir()) == [
        "metrics.json",
        "question_results.csv",
        "report.md",
    ]


def test_incomplete_finalization_rejects_an_exports_symlink(tmp_path: Path) -> None:
    fixture = _memory_fixture()
    question = _question("q-00", QuestionCategory.ABSTENTION)
    incomplete = EvaluationRun(
        manifest_hash="a" * 64,
        expected_question_ids=(question.id,),
        question_manifest_sha256="b" * 64,
        ke_ready_snapshot_id="c" * 40,
        status=EvaluationStatus.INCOMPLETE,
        answers=(_answer(question, fixture.first_ke, fixture.first_exchange),),
        judgements=(),
        failures=(
            EvaluationFailure(
                question_id=question.id,
                stage="judge",
                error_type="TimeoutError",
                message="judge failed",
            ),
        ),
    )
    state_root = tmp_path / "state"
    state_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (state_root / "exports").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ReportInvariantError, match="symlink"):
        finalize_evaluation_outputs(
            run=incomplete,
            smoke=False,
            state_root=state_root,
            run_id="run-1",
            documents=_report_documents(),
            promote_complete=lambda: "d" * 40,
        )

    assert list(outside.iterdir()) == []


def _report_documents() -> tuple[ReportDocument, ...]:
    return (
        _report_document("metrics.json", "application/json"),
        _report_document("question_results.csv", "text/csv; charset=utf-8"),
        _report_document("report.md", "text/markdown; charset=utf-8"),
    )


def _report_document(
    name: Literal["metrics.json", "question_results.csv", "report.md"],
    media_type: str,
) -> ReportDocument:
    content = f"{name}\n"
    return ReportDocument(
        name=name,
        media_type=media_type,
        sha256=hashlib.sha256(content.encode()).hexdigest(),
        content=content,
    )


class _MemoryFixture:
    def __init__(
        self,
        *,
        conversation: Conversation,
        first_exchange: Exchange,
        tool_exchange: Exchange,
        update_exchange: Exchange,
        first_ke: KnowledgeEquation,
        knowledge_equations: tuple[KnowledgeEquation, ...],
        aggregate: AggregateNode,
        coverage: tuple[CoverageEntry, ...],
    ) -> None:
        self.conversation = conversation
        self.first_exchange = first_exchange
        self.tool_exchange = tool_exchange
        self.update_exchange = update_exchange
        self.first_ke = first_ke
        self.knowledge_equations = knowledge_equations
        self.aggregate = aggregate
        self.coverage = coverage


def _memory_fixture() -> _MemoryFixture:
    first = _exchange("exchange-1", "session-1", 0, "Alpha started", "Acknowledged")
    tool = _exchange(
        "exchange-2",
        "session-1",
        1,
        "Check beta",
        "Beta is pending",
        tool_text="lookup beta",
    )
    update = _exchange("exchange-3", "session-2", 2, "Alpha stopped", "Updated")
    conversation = Conversation(
        id="conversation-1",
        sessions=(
            Session(id="session-1", conversation_id="conversation-1", exchanges=(first, tool)),
            Session(id="session-2", conversation_id="conversation-1", exchanges=(update,)),
        ),
    )
    first_span = _span(first.user)
    tool_span = _span(tool.user)
    update_span = _span(update.user)
    first_ke = _ke("alpha started", first_span)
    unresolved = _ke(
        "beta pending",
        tool_span,
        bindings=(
            OntologyBinding(
                surface_form="beta",
                normalized_surface="beta",
                status=OntologyBindingStatus.UNRESOLVED,
            ),
        ),
    )
    updated = _ke("alpha stopped", update_span, supersedes=(first_ke.id,))
    aggregate = AggregateNode(
        id="aggregate-cross-session",
        node_kind=AggregateNodeKind.PROJECT,
        title="Alpha lifecycle",
        summary="Alpha changed across sessions.",
        member_refs=(first_ke.id, updated.id),
        derived_from=(first_ke.id, updated.id),
        evidence_closure=(first_span, update_span),
        temporal_extent=TemporalMetadata(),
        confidence=1.0,
        revision="d" * 64,
        depth=1,
    )
    equations = (first_ke, unresolved, updated)
    coverage = tuple(
        CoverageEntry(
            message_id=message.id,
            start_char=0,
            end_char=len(message.content),
            status=CoverageStatus.REPRESENTED,
            ke_ids=tuple(
                equation.id
                for equation in equations
                if any(span.message_id == message.id for span in equation.evidence_refs)
            ),
        )
        for exchange in (first, tool, update)
        for message in (exchange.user, exchange.assistant)
    )
    return _MemoryFixture(
        conversation=conversation,
        first_exchange=first,
        tool_exchange=tool,
        update_exchange=update,
        first_ke=first_ke,
        knowledge_equations=equations,
        aggregate=aggregate,
        coverage=coverage,
    )


def _exchange(
    exchange_id: str,
    session_id: str,
    ordinal: int,
    user_text: str,
    assistant_text: str,
    *,
    tool_text: str | None = None,
) -> Exchange:
    user = Message(
        id=f"{exchange_id}-user",
        role=MessageRole.USER,
        content=user_text,
        source_order=ordinal * 10,
    )
    events = (
        (
            ToolEvent(
                id=f"{exchange_id}-tool",
                kind=ToolEventKind.TOOL_RESULT,
                content=tool_text,
                source_order=ordinal * 10 + 1,
            ),
        )
        if tool_text is not None
        else ()
    )
    return Exchange(
        id=exchange_id,
        session_id=session_id,
        user=user,
        events=events,
        assistant=Message(
            id=f"{exchange_id}-assistant",
            role=MessageRole.ASSISTANT,
            content=assistant_text,
            source_order=ordinal * 10 + 2,
        ),
        global_ordinal=ordinal,
    )


def _span(message: Message) -> MessageSpan:
    return MessageSpan(
        message_id=message.id,
        start_char=0,
        end_char=len(message.content),
        text_hash=hashlib.sha256(message.content.encode()).hexdigest(),
    )


def _ke(
    gloss: str,
    span: MessageSpan,
    *,
    bindings: tuple[OntologyBinding, ...] = (),
    supersedes: tuple[str, ...] = (),
) -> KnowledgeEquation:
    return KnowledgeEquation.create(
        level=KnowledgeLevel.TURN,
        lhs=ConceptRef(term_id="alpha", label="alpha"),
        rhs=ConceptRef(term_id=gloss.replace(" ", "-"), label=gloss),
        gloss=gloss,
        modality=Modality.FACT,
        polarity=Polarity.POSITIVE,
        lifecycle=Lifecycle.ACTIVE,
        speaker=Speaker.USER,
        ontology_bindings=bindings,
        evidence_refs=(span,),
        supersedes=supersedes,
        confidence=1.0,
        produced_in_run_id="run-1",
        produced_in_stage="turn-ke-extracted",
    )


def _question(question_id: str, category: QuestionCategory) -> ProbeQuestion:
    return ProbeQuestion(
        id=question_id,
        conversation_id="conversation-1",
        category=category,
        ordinal=0,
        question=f"Question {question_id}",
        ideal_answer="Ideal answer",
        original_answer_field="ideal_answer",
        rubric=("correct",),
        raw_metadata={},
    )


def _answer(
    question: ProbeQuestion,
    equation: KnowledgeEquation,
    exchange: Exchange,
) -> QuestionAnswer:
    evidence_id = f"evidence-{question.id}"
    evidence = Evidence(
        evidence_id=evidence_id,
        text=equation.gloss,
        source_exchange_ids=(exchange.id,),
        source_message_ids=(exchange.user.id,),
        system_record_ids=(equation.id,),
        score=1.0,
        rank=1,
        channel="symbolic",
        metadata={},
        token_count=3,
    )
    return QuestionAnswer(
        question_id=question.id,
        conversation_id=question.conversation_id,
        evidence=(evidence,),
        answer="Answer",
        citations=(evidence_id,),
        retrieval_trace=RetrievalTrace(
            question_sha256=hashlib.sha256(question.question.encode()).hexdigest(),
            query_ke=_query_ke(question.question, "alpha", "status"),
            symbolic_candidate_ids=(equation.id,),
            matches=(),
            embedding_candidate_count=0,
            evidence_ids=(evidence_id,),
        ),
        usage=_usage("gpt-5.4", f"work-{question.id}"),
    )


def _judgement(question_id: str) -> JudgeResult:
    return JudgeResult(
        question_id=question_id,
        rubric_items=(RubricJudgement(rubric="correct", satisfied=True, reason="yes"),),
        answer_score=1.0,
        factual_error=False,
        unsupported_claim=False,
        abstention_correct=True,
        short_rationale="correct",
        usage=_usage("deepseek-v4-pro", f"judge-{question_id}"),
    )


def _query_ke(gloss: str, lhs_label: str, rhs_label: str) -> QueryKE:
    return QueryKE(
        lhs=ConceptRef(term_id=lhs_label, label=lhs_label),
        rhs=ConceptRef(term_id=rhs_label, label=rhs_label),
        gloss=gloss,
        surface_groundings=(
            QuerySurfaceGrounding(
                surface_form=lhs_label,
                role=OntologyRole.CONCEPT,
                grounding_span=QueryGroundingSpan(start_char=0, end_char=1),
            ),
            QuerySurfaceGrounding(
                surface_form=rhs_label,
                role=OntologyRole.CONCEPT,
                grounding_span=QueryGroundingSpan(start_char=1, end_char=2),
            ),
        ),
    )


def _question_metric_input(fixture: _MemoryFixture, *, mapped: bool) -> QuestionMetricInput:
    category = QuestionCategory.INFORMATION_EXTRACTION if mapped else QuestionCategory.ABSTENTION
    question = _question("q-mapped" if mapped else "q-unmapped", category)
    answer = _answer(question, fixture.first_ke, fixture.first_exchange)
    mapping = GoldSourceMapping(
        question_id=question.id,
        status=GoldSourceStatus.MAPPED if mapped else GoldSourceStatus.UNMAPPABLE,
        source_numbers=(1, 2) if mapped else (),
        source_exchange_ids=(fixture.first_exchange.id, fixture.update_exchange.id)
        if mapped
        else (),
        matched_paths=("$.source_chat_ids",) if mapped else (),
        exclusion_reason=None if mapped else "no_explicit_source_reference",
    )
    return QuestionMetricInput(
        question=question,
        gold_mapping=mapping,
        answer=answer,
        judgement=_judgement(question.id),
        conversations=(fixture.conversation,),
        current_knowledge_equations=fixture.knowledge_equations,
        aggregates=(fixture.aggregate,),
    )


def _usage(model: str, request_id: str) -> UsageRecord:
    return UsageRecord(
        request_id=request_id,
        model=model,
        latency_seconds=0.25,
        input_tokens=10,
        output_tokens=2,
        total_tokens=12,
        provider_cost=0.01,
    )


def _trace(
    operation: str,
    request_id: str,
    *,
    cost: float | None,
    input_tokens: int,
) -> ModelTrace:
    usage = UsageRecord(
        request_id=request_id,
        model="model",
        latency_seconds=0.5,
        input_tokens=input_tokens,
        output_tokens=2,
        total_tokens=input_tokens + 2,
        provider_cost=cost,
    )
    return ModelTrace(
        context=TraceContext(operation=operation),
        transport_attempt=1,
        structured_request=1,
        latency_seconds=usage.latency_seconds,
        request={"model": "model"},
        response={"request_id": request_id},
        error=None,
        usage=usage,
    )


def _run(
    questions: tuple[ProbeQuestion, ...],
    answers: tuple[QuestionAnswer, ...],
    judgements: tuple[JudgeResult, ...],
) -> EvaluationRun:
    return EvaluationRun(
        manifest_hash="a" * 64,
        expected_question_ids=tuple(question.id for question in questions),
        question_manifest_sha256="b" * 64,
        ke_ready_snapshot_id="c" * 40,
        status=EvaluationStatus.COMPLETE,
        answers=answers,
        judgements=judgements,
        failures=(),
    )
