from __future__ import annotations

import csv
from datetime import UTC, datetime
import hashlib
import io
import json
from pathlib import Path

from ke_memory_demo.domain import (
    ConceptRef,
    KnowledgeEquation,
    KnowledgeLevel,
    Lifecycle,
    MessageSpan,
    Modality,
    OntologyRole,
    Polarity,
    Speaker,
)
from ke_memory_demo.evaluation import (
    AggregateMetrics,
    EvaluationRun,
    EvaluationStatus,
    ExperimentManifest,
    GoldSourceMapping,
    GoldSourceStatus,
    JudgeResult,
    OperationUsageMetrics,
    ProbeQuestion,
    QuestionAnswer,
    QuestionCategory,
    QuestionMetrics,
    ReportDocument,
    RubricJudgement,
    TurnKEAuditCase,
)
from ke_memory_demo.evaluation.baseline_results import load_public_baseline_results
from ke_memory_demo.evaluation.report import ReportInput, ReportWriter
from ke_memory_demo.infra.telemetry import UsageRecord
from ke_memory_demo.ontology import IndexIdentity
from ke_memory_demo.pipeline import OntologyRunIdentity
from ke_memory_demo.retrieval import (
    QueryGroundingSpan,
    QueryKE,
    QuerySurfaceGrounding,
    RetrievalTrace,
)
from ke_memory_demo.settings import EvaluationConcurrencySettings


def test_report_contains_ke_metrics_audits_and_comparison_warning(
    project_root: Path,
) -> None:
    report_input = _report_input(project_root)

    first = ReportWriter.build(report_input)
    second = ReportWriter.build(report_input)

    assert first == second
    assert [item.name for item in first] == [
        "metrics.json",
        "question_results.csv",
        "report.md",
    ]
    assert all(
        item.sha256 == hashlib.sha256(item.content.encode("utf-8")).hexdigest() for item in first
    )
    markdown = _document(first, "report.md").content
    for section in _required_sections():
        assert section in markdown
    assert "60/60 answers" in markdown
    assert "60/60 Judge results" in markdown
    assert "不可直接比较" in markdown
    assert "baseline ranking" not in markdown.lower()
    assert "Turn KE 双轨" not in markdown
    assert "embedding metric" not in markdown.lower()
    assert "alpha is active" in markdown
    assert "Evidence spans:" in markdown
    assert "Abstention correctness:" in markdown

    metrics = json.loads(_document(first, "metrics.json").content)
    assert metrics["completeness"] == {
        "answers": 60,
        "expected": 60,
        "failures": 0,
        "judge_results": 60,
        "status": "complete",
    }
    rows = list(csv.DictReader(io.StringIO(_document(first, "question_results.csv").content)))
    assert [row["question_id"] for row in rows] == sorted(row["question_id"] for row in rows)
    assert len(rows) == 60


def _report_input(project_root: Path) -> ReportInput:
    questions = tuple(
        _question(index, tuple(QuestionCategory)[index % len(QuestionCategory)])
        for index in range(60)
    )
    answers = tuple(_answer(question) for question in questions)
    judgements = tuple(_judgement(question.id) for question in questions)
    manifest = _manifest(questions)
    run = EvaluationRun(
        manifest_hash=manifest.content_hash,
        expected_question_ids=tuple(question.id for question in questions),
        question_manifest_sha256="b" * 64,
        ke_ready_snapshot_id="c" * 40,
        status=EvaluationStatus.COMPLETE,
        answers=answers,
        judgements=judgements,
        failures=(),
    )
    question_metrics = tuple(
        QuestionMetrics(
            question_id=question.id,
            conversation_id=question.conversation_id,
            category=question.category,
            answer_score=1.0,
            satisfied_rubrics=1,
            rubric_count=1,
            factual_error=False,
            unsupported_claim=False,
            abstention_correct=True if question.category is QuestionCategory.ABSTENTION else None,
            source_recall=None if index >= 54 else 1.0,
            complete_evidence=None if index >= 54 else True,
            citation_valid=True,
            citation_traceable=True,
            source_session_count=2,
            used_aggregate=index % 2 == 0,
            evidence_tokens=7,
            work_usage=_usage("gpt-5.4", f"work-{index:02d}"),
            judge_usage=_usage("deepseek-v4-pro", f"judge-{index:02d}"),
        )
        for index, question in enumerate(questions)
    )
    aggregate_metrics = (
        _aggregate("overall", 60, mapped=54),
        _aggregate("conversation:conversation-1", 60, mapped=54),
        *(_aggregate(f"category:{category.value}", 6, mapped=6) for category in QuestionCategory),
    )
    mappings = tuple(
        GoldSourceMapping(
            question_id=question.id,
            status=GoldSourceStatus.MAPPED if index < 54 else GoldSourceStatus.UNMAPPABLE,
            source_numbers=(index + 1,) if index < 54 else (),
            source_exchange_ids=(f"exchange-{index:02d}",) if index < 54 else (),
            matched_paths=("$.source_chat_id",) if index < 54 else (),
            exclusion_reason=None if index < 54 else "no_explicit_source_reference",
        )
        for index, question in enumerate(questions)
    )
    return ReportInput(
        manifest=manifest,
        run=run,
        questions=questions,
        gold_mappings=mappings,
        question_metrics=question_metrics,
        aggregate_metrics=aggregate_metrics,
        operation_usage_metrics=(
            OperationUsageMetrics(
                operation="common-answer",
                call_count=60,
                input_tokens=600,
                output_tokens=120,
                latency_seconds=15.0,
                provider_cost=None,
            ),
            OperationUsageMetrics(
                operation="independent-judge",
                call_count=60,
                input_tokens=600,
                output_tokens=120,
                latency_seconds=15.0,
                provider_cost=1.2,
            ),
        ),
        baseline_public_results=load_public_baseline_results(
            project_root / "data/baselines/public_results.toml"
        ),
        turn_ke_audits=(
            TurnKEAuditCase(
                audit_kind="conversation_first",
                conversation_id="conversation-1",
                exchange_ids=("exchange-00",),
                raw_records=({"user": "raw user", "assistant": "raw assistant"},),
                coverage=(),
                knowledge_equations=(_audit_ke(),),
            ),
            TurnKEAuditCase(
                audit_kind="cross_session",
                conversation_id="conversation-1",
                exchange_ids=("exchange-00", "exchange-30"),
                raw_records=({"closure": "two sessions"},),
                coverage=(),
                knowledge_equations=(),
                aggregate_ids=("aggregate-1",),
            ),
        ),
    )


def _question(index: int, category: QuestionCategory) -> ProbeQuestion:
    return ProbeQuestion(
        id=f"q-{index:02d}",
        conversation_id="conversation-1",
        category=category,
        ordinal=index // len(QuestionCategory),
        question=f"Question {index}",
        ideal_answer="Ideal answer",
        original_answer_field="ideal_answer",
        rubric=("correct",),
        raw_metadata={},
    )


def _audit_ke() -> KnowledgeEquation:
    return KnowledgeEquation.create(
        level=KnowledgeLevel.TURN,
        lhs=ConceptRef(term_id="alpha", label="alpha"),
        rhs=ConceptRef(term_id="active", label="active"),
        gloss="alpha is active",
        modality=Modality.FACT,
        polarity=Polarity.POSITIVE,
        lifecycle=Lifecycle.ACTIVE,
        speaker=Speaker.USER,
        evidence_refs=(
            MessageSpan(
                message_id="exchange-00-user",
                start_char=0,
                end_char=5,
                text_hash="9" * 64,
            ),
        ),
        confidence=1.0,
        produced_in_run_id="run-1",
        produced_in_stage="turn-ke-extracted",
    )


def _answer(question: ProbeQuestion) -> QuestionAnswer:
    return QuestionAnswer(
        question_id=question.id,
        conversation_id=question.conversation_id,
        evidence=(),
        answer="Answer",
        citations=(),
        retrieval_trace=RetrievalTrace(
            question_sha256=hashlib.sha256(question.question.encode()).hexdigest(),
            query_ke=_query_ke(question.question),
            symbolic_candidate_ids=(),
            matches=(),
            embedding_candidate_count=0,
            evidence_ids=(),
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
        abstention_correct=None,
        short_rationale="correct",
        usage=_usage("deepseek-v4-pro", f"judge-{question_id}"),
    )


def _query_ke(gloss: str) -> QueryKE:
    return QueryKE(
        lhs=ConceptRef(term_id="subject", label="subject"),
        rhs=ConceptRef(term_id="state", label="state"),
        gloss=gloss,
        surface_groundings=(
            QuerySurfaceGrounding(
                surface_form="subject",
                role=OntologyRole.CONCEPT,
                grounding_span=QueryGroundingSpan(start_char=0, end_char=1),
            ),
            QuerySurfaceGrounding(
                surface_form="state",
                role=OntologyRole.CONCEPT,
                grounding_span=QueryGroundingSpan(start_char=1, end_char=2),
            ),
        ),
    )


def _aggregate(scope: str, count: int, *, mapped: int) -> AggregateMetrics:
    return AggregateMetrics(
        scope=scope,
        question_count=count,
        answer_score_sum=float(count),
        answer_score_mean=1.0,
        mapped_source_count=mapped,
        source_recall_sum=float(mapped),
        source_recall_mean=1.0 if mapped else None,
        complete_evidence_count=mapped,
        citation_valid_count=count,
        citation_traceable_count=count,
        factual_error_count=0,
        unsupported_claim_count=0,
    )


def _manifest(questions: tuple[ProbeQuestion, ...]) -> ExperimentManifest:
    return ExperimentManifest(
        run_id="run-1",
        code_commit="1" * 40,
        spec_sha256="2" * 64,
        plan_sha256="3" * 64,
        ke_ready_snapshot_id="c" * 40,
        dataset_sha256="4" * 64,
        selected_directories=(4, 15, 17),
        expected_sessions=13,
        expected_exchanges=385,
        expected_questions=len(questions),
        question_manifest_sha256="b" * 64,
        gold_mapping_sha256="5" * 64,
        ontology=OntologyRunIdentity(
            index=IndexIdentity(
                index_name="ontology",
                index_uuid="uuid-1",
                mapping_sha256="6" * 64,
            ),
            normalization_mode="bounded-best-effort",
            matched_document_ids=("term-1",),
        ),
        work_model="gpt-5.4",
        work_base_url="https://work.invalid/v1",
        judge_model="deepseek-v4-pro",
        judge_base_url="https://judge.invalid/v1",
        answer_prompt_sha256="7" * 64,
        judge_prompt_sha256="8" * 64,
        embedding_enabled=False,
        concurrency=EvaluationConcurrencySettings(
            turn_workers=8,
            session_workers=4,
            question_workers=8,
            judge_workers=8,
        ),
        created_at=datetime(2026, 7, 17, tzinfo=UTC),
    )


def _usage(model: str, request_id: str) -> UsageRecord:
    return UsageRecord(
        request_id=request_id,
        model=model,
        latency_seconds=0.25,
        input_tokens=10,
        output_tokens=2,
        total_tokens=12,
        provider_cost=None,
    )


def _document(documents: tuple[ReportDocument, ...], name: str) -> ReportDocument:
    return next(item for item in documents if getattr(item, "name") == name)


def _required_sections() -> tuple[str, ...]:
    path = Path(__file__).parent / "report/required_sections.txt"
    return tuple(line for line in path.read_text(encoding="utf-8").splitlines() if line)
