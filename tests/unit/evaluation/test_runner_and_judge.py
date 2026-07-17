from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import TypeVar, cast

import pytest
from pydantic import BaseModel, ValidationError

from ke_memory_demo.answering import AnswerModelOutput, AnswerService
from ke_memory_demo.core.json import JsonObject, canonical_json
from ke_memory_demo.domain import ConceptRef, Evidence, OntologyRole
from ke_memory_demo.evaluation import (
    EvaluationRunner,
    EvaluationStatus,
    ExperimentManifest,
    JudgeInvariantError,
    JudgeModelOutput,
    JudgeResult,
    JudgeService,
    ProbeQuestion,
    QuestionAnswer,
    QuestionCategory,
    RubricJudgement,
)
from ke_memory_demo.infra.llm import StructuredCompletion
from ke_memory_demo.infra.telemetry import TraceContext, UsageRecord
from ke_memory_demo.ontology import IndexIdentity
from ke_memory_demo.pipeline import CheckpointStore, OntologyRunIdentity
from ke_memory_demo.retrieval import (
    KEMatchDecision,
    MatchRelation,
    QueryGroundingSpan,
    QueryKE,
    QuerySurfaceGrounding,
    RetrievalTrace,
    TracedRetrieval,
)
from ke_memory_demo.settings import EvaluationConcurrencySettings
from ke_memory_demo.systems import KEMemorySystem


ModelT = TypeVar("ModelT", bound=BaseModel)


class _ZeroTokenCounter:
    def count(self, text: str) -> int:
        del text
        return 0


class _ConcurrencyProbe:
    def __init__(self) -> None:
        self.work_current = 0
        self.work_peak = 0
        self.judge_current = 0
        self.judge_peak = 0
        self.phases_overlapped = False

    async def work(self, question: str) -> None:
        self.work_current += 1
        self.work_peak = max(self.work_peak, self.work_current)
        self.phases_overlapped |= self.judge_current > 0
        try:
            await asyncio.sleep(0 if question.endswith("q-1") else 0.01)
        finally:
            self.work_current -= 1

    async def judge(self) -> None:
        self.judge_current += 1
        self.judge_peak = max(self.judge_peak, self.judge_current)
        self.phases_overlapped |= self.work_current > 0
        try:
            await asyncio.sleep(0.01)
        finally:
            self.judge_current -= 1


class _AnswerClient:
    model_name = "gpt-5.4"
    max_output_tokens = 1024

    def __init__(self, probe: _ConcurrencyProbe) -> None:
        self._probe = probe
        self.calls = 0

    async def complete_with_usage(
        self,
        model_type: type[ModelT],
        messages: Sequence[Mapping[str, object]],
        trace_context: TraceContext | Mapping[str, object],
    ) -> StructuredCompletion[ModelT]:
        assert isinstance(trace_context, TraceContext)
        payload = cast(JsonObject, json.loads(str(messages[-1]["content"])))
        question = cast(str, payload["question"])
        evidence = cast(list[JsonObject], payload["evidence"])
        self.calls += 1
        await self._probe.work(question)
        return StructuredCompletion(
            value=model_type.model_validate(
                AnswerModelOutput(
                    answer=f"Candidate answer for {question.removeprefix('Question ')}",
                    citations=(cast(str, evidence[0]["evidence_id"]),),
                )
            ),
            usage=_usage(self.model_name, f"answer-{self.calls}"),
        )


class _JudgeClient:
    model_name = "deepseek-v4-pro"
    max_output_tokens = 2048

    def __init__(self, probe: _ConcurrencyProbe | None = None) -> None:
        self._probe = probe or _ConcurrencyProbe()
        self._failed_questions: set[str] = set()
        self.calls = 0
        self.last_user_payload: JsonObject = {}
        self.reverse_rubric = False

    def fail_question(self, question_id: str) -> None:
        self._failed_questions.add(question_id)

    async def complete_with_usage(
        self,
        model_type: type[ModelT],
        messages: Sequence[Mapping[str, object]],
        trace_context: TraceContext | Mapping[str, object],
    ) -> StructuredCompletion[ModelT]:
        assert isinstance(trace_context, TraceContext)
        self.last_user_payload = cast(JsonObject, json.loads(str(messages[-1]["content"])))
        candidate = cast(str, self.last_user_payload["candidate_answer"])
        question_id = candidate.removeprefix("Candidate answer for ")
        self.calls += 1
        await self._probe.judge()
        if question_id in self._failed_questions:
            raise RuntimeError("internal judge detail")
        rubric = tuple(cast(list[str], self.last_user_payload["rubric"]))
        if self.reverse_rubric:
            rubric = tuple(reversed(rubric))
        output = JudgeModelOutput(
            rubric_items=tuple(
                RubricJudgement(
                    rubric=item,
                    satisfied=index != 1,
                    reason="concise reason",
                )
                for index, item in enumerate(rubric)
            ),
            factual_error=False,
            unsupported_claim=False,
            abstention_correct=None,
            short_rationale="Two rubric items are satisfied.",
        )
        return StructuredCompletion(
            value=model_type.model_validate(output),
            usage=_usage(self.model_name, f"judge-{self.calls}"),
        )


class _System:
    def __init__(self) -> None:
        self.failed_questions: set[str] = set()
        self.calls = 0

    async def retrieve_with_trace(
        self,
        question: str,
        evidence_budget_tokens: int,
    ) -> TracedRetrieval:
        assert evidence_budget_tokens == 8192
        self.calls += 1
        question_id = question.removeprefix("Question ")
        if question_id in self.failed_questions:
            raise RuntimeError("internal retrieval detail")
        evidence = _evidence(question_id)
        return TracedRetrieval(
            evidence=(evidence,),
            trace=_retrieval_trace(question, evidence.evidence_id),
        )


def _usage(model: str, request_id: str) -> UsageRecord:
    return UsageRecord(
        request_id=request_id,
        model=model,
        latency_seconds=0.01,
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
    )


def _query_ke(gloss: str) -> QueryKE:
    lhs = ConceptRef(term_id="term-project", label="project")
    rhs = ConceptRef(term_id="term-status", label="status")
    return QueryKE(
        lhs=lhs,
        rhs=rhs,
        gloss=gloss,
        surface_groundings=(
            QuerySurfaceGrounding(
                surface_form=lhs.label,
                role=OntologyRole.CONCEPT,
                grounding_span=QueryGroundingSpan(start_char=0, end_char=1),
            ),
            QuerySurfaceGrounding(
                surface_form=rhs.label,
                role=OntologyRole.CONCEPT,
                grounding_span=QueryGroundingSpan(start_char=1, end_char=2),
            ),
        ),
    )


def _evidence(question_id: str) -> Evidence:
    return Evidence(
        evidence_id=f"evidence-{question_id}",
        text=f"Evidence for {question_id}",
        source_exchange_ids=(f"exchange-{question_id}",),
        source_message_ids=(f"message-{question_id}",),
        system_record_ids=(f"record-{question_id}",),
        score=1.0,
        rank=1,
        channel="symbolic",
        metadata={"internal_system": "ke-memory"},
        token_count=1,
    )


def _retrieval_trace(question: str, evidence_id: str) -> RetrievalTrace:
    candidate_id = f"candidate-{question.removeprefix('Question ')}"
    return RetrievalTrace(
        question_sha256=hashlib.sha256(question.encode()).hexdigest(),
        query_ke=_query_ke(question),
        symbolic_candidate_ids=(candidate_id,),
        matches=(
            KEMatchDecision(
                candidate_id=candidate_id,
                match_type=MatchRelation.EXACT,
                confidence=1.0,
                reason="exact",
            ),
        ),
        embedding_candidate_count=0,
        evidence_ids=(evidence_id,),
    )


def _question(question_id: str, conversation_id: str = "conversation-1") -> ProbeQuestion:
    return ProbeQuestion(
        id=question_id,
        conversation_id=conversation_id,
        category=QuestionCategory.KNOWLEDGE_UPDATE,
        ordinal=0,
        question=f"Question {question_id}",
        ideal_answer=f"Ideal {question_id}",
        original_answer_field="ideal_answer",
        rubric=("accurate", "complete", "concise"),
        raw_metadata={"internal_system": "ke-memory"},
    )


def _answer(question: ProbeQuestion) -> QuestionAnswer:
    evidence = _evidence(question.id)
    return QuestionAnswer(
        question_id=question.id,
        conversation_id=question.conversation_id,
        evidence=(evidence,),
        answer=f"Candidate answer for {question.id}",
        citations=(evidence.evidence_id,),
        retrieval_trace=_retrieval_trace(question.question, evidence.evidence_id),
        usage=_usage("gpt-5.4", "answer-1"),
    )


def _manifest(
    *,
    answer_prompt_sha256: str,
    judge_prompt_sha256: str,
    expected_questions: int = 3,
) -> ExperimentManifest:
    return ExperimentManifest(
        run_id="run-1",
        code_commit="a" * 40,
        spec_sha256="b" * 64,
        plan_sha256="c" * 64,
        ke_ready_snapshot_id="d" * 40,
        dataset_sha256="e" * 64,
        selected_directories=(4, 15, 17),
        expected_sessions=13,
        expected_exchanges=385,
        expected_questions=expected_questions,
        question_manifest_sha256="f" * 64,
        gold_mapping_sha256="0" * 64,
        ontology=OntologyRunIdentity(
            index=IndexIdentity(
                index_name="ontology",
                index_uuid="uuid-1",
                mapping_sha256="1" * 64,
            ),
            normalization_mode="bounded-best-effort",
        ),
        work_model="gpt-5.4",
        work_base_url="https://work.invalid/v1",
        judge_model="deepseek-v4-pro",
        judge_base_url="https://judge.invalid/v1",
        answer_prompt_sha256=answer_prompt_sha256,
        judge_prompt_sha256=judge_prompt_sha256,
        embedding_enabled=False,
        concurrency=EvaluationConcurrencySettings(
            turn_workers=8,
            session_workers=4,
            question_workers=3,
            judge_workers=2,
        ),
        created_at=datetime(2026, 7, 17, tzinfo=UTC),
    )


def _fake_evaluation(tmp_path: Path) -> SimpleNamespace:
    probe = _ConcurrencyProbe()
    questions = (
        _question("q-3", "conversation-3"),
        _question("q-1", "conversation-1"),
        _question("q-2", "conversation-2"),
    )
    systems = {question.conversation_id: _System() for question in questions}
    clients = {question.conversation_id: _AnswerClient(probe) for question in questions}
    answer_services = {
        conversation_id: AnswerService(client, token_counter=_ZeroTokenCounter())
        for conversation_id, client in clients.items()
    }
    judge_client = _JudgeClient(probe)
    judge = JudgeService(judge_client)
    manifest = _manifest(
        answer_prompt_sha256=next(iter(answer_services.values())).prompt_sha256,
        judge_prompt_sha256=judge.prompt_sha256,
    )
    runner = EvaluationRunner(
        systems=cast(Mapping[str, KEMemorySystem], systems),
        answer_services=answer_services,
        judge=judge,
        checkpoints=CheckpointStore(tmp_path / "state", manifest.run_id),
        manifest=manifest,
    )
    return SimpleNamespace(
        answer_clients=clients,
        judge=judge_client,
        probe=probe,
        questions=questions,
        runner=runner,
        systems=systems,
    )


@pytest.mark.asyncio
async def test_judge_payload_is_blind_and_score_is_derived() -> None:
    client = _JudgeClient()
    question = _question("q-1")

    result = await JudgeService(client).judge(question, _answer(question))

    payload = client.last_user_payload
    assert set(payload) == {"question", "ideal_answer", "rubric", "candidate_answer"}
    assert "ke-memory" not in canonical_json(payload).decode().lower()
    assert result.answer_score == 2 / 3
    assert "answer_score" not in JudgeModelOutput.model_fields


@pytest.mark.asyncio
async def test_judge_rejects_changed_rubric_order() -> None:
    client = _JudgeClient()
    client.reverse_rubric = True
    question = _question("q-1")

    with pytest.raises(JudgeInvariantError, match="rubric"):
        await JudgeService(client).judge(question, _answer(question))


def test_judge_result_rejects_a_forged_authoritative_score() -> None:
    rubric_items = (
        RubricJudgement(rubric="accurate", satisfied=True, reason="yes"),
        RubricJudgement(rubric="complete", satisfied=False, reason="no"),
    )

    with pytest.raises(ValidationError, match="derived"):
        JudgeResult(
            question_id="q-1",
            rubric_items=rubric_items,
            answer_score=1.0,
            factual_error=False,
            unsupported_claim=False,
            abstention_correct=None,
            short_rationale="One item is satisfied.",
            usage=_usage("deepseek-v4-pro", "judge-1"),
        )


@pytest.mark.asyncio
async def test_runner_bounds_work_and_judge_and_keeps_stable_order(tmp_path: Path) -> None:
    fake = _fake_evaluation(tmp_path)

    run = await fake.runner.run(fake.questions)

    assert [item.question_id for item in run.answers] == ["q-1", "q-2", "q-3"]
    assert [item.question_id for item in run.judgements] == ["q-1", "q-2", "q-3"]
    assert fake.probe.work_peak <= 3
    assert fake.probe.judge_peak <= 2
    assert fake.probe.phases_overlapped
    assert run.status is EvaluationStatus.COMPLETE
    assert all(
        item.retrieval_trace.evidence_ids
        == tuple(evidence.evidence_id for evidence in item.evidence)
        for item in run.answers
    )


@pytest.mark.asyncio
async def test_missing_judge_marks_incomplete_without_zero_and_retains_answer(
    tmp_path: Path,
) -> None:
    fake = _fake_evaluation(tmp_path)
    fake.judge.fail_question("q-2")

    run = await fake.runner.run(fake.questions)

    assert run.status is EvaluationStatus.INCOMPLETE
    assert [item.question_id for item in run.answers] == ["q-1", "q-2", "q-3"]
    assert [item.question_id for item in run.judgements] == ["q-1", "q-3"]
    assert [failure.question_id for failure in run.failures] == ["q-2"]
    [failure] = run.failures
    assert failure.stage == "judge"
    assert "internal judge detail" not in failure.message
    assert all(item.answer_score > 0 for item in run.judgements)


@pytest.mark.asyncio
async def test_retrieval_failure_becomes_typed_incomplete_failure(tmp_path: Path) -> None:
    fake = _fake_evaluation(tmp_path)
    fake.systems["conversation-2"].failed_questions.add("q-2")

    run = await fake.runner.run(fake.questions)

    assert run.status is EvaluationStatus.INCOMPLETE
    assert [item.question_id for item in run.answers] == ["q-1", "q-3"]
    assert [item.question_id for item in run.judgements] == ["q-1", "q-3"]
    [failure] = run.failures
    assert failure.question_id == "q-2"
    assert failure.stage == "retrieve_answer"
    assert failure.error_type == "RuntimeError"
    assert "internal retrieval detail" not in failure.message
