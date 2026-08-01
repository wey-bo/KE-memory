from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
import hashlib
from typing import cast

from ke_memory_demo.answering import AnswerService
from ke_memory_demo.core.json import JsonObject, JsonValue, canonical_json
from ke_memory_demo.storage.checkpoints import CheckpointStore
from ke_memory_demo.core.concurrency import BatchOutcome, bounded_collect
from ke_memory_demo.systems import KEMemorySystem

from .judge import JudgeService
from .manifest import ExperimentManifest
from .models import (
    EvaluationFailure,
    EvaluationRun,
    EvaluationStatus,
    JudgeResult,
    ProbeQuestion,
    QuestionAnswer,
    QuestionExecution,
)
from .questions import question_manifest_sha256


EVIDENCE_BUDGET_TOKENS = 8192
ANSWER_CHECKPOINT_STAGE = "question-answers"
JUDGE_CHECKPOINT_STAGE = "judge-results"


class EvaluationInvariantError(RuntimeError):
    """Prepared evaluation inputs or outputs violate the frozen run contract."""


class EvaluationRunner:
    def __init__(
        self,
        systems: Mapping[str, KEMemorySystem],
        answer_services: Mapping[str, AnswerService],
        judge: JudgeService,
        checkpoints: CheckpointStore,
        manifest: ExperimentManifest,
    ) -> None:
        if set(systems) != set(answer_services):
            raise EvaluationInvariantError(
                "systems and answer services must cover the same Conversations"
            )
        if not systems:
            raise EvaluationInvariantError("evaluation requires at least one Conversation")
        if checkpoints.run_id != manifest.run_id:
            raise EvaluationInvariantError("checkpoint namespace does not match the manifest run")
        for service in answer_services.values():
            if service.model_name != manifest.work_model:
                raise EvaluationInvariantError("answer service model does not match the manifest")
            if service.prompt_sha256 != manifest.answer_prompt_sha256:
                raise EvaluationInvariantError("answer prompt does not match the manifest")
        if judge.model_name != manifest.judge_model:
            raise EvaluationInvariantError("Judge service model does not match the manifest")
        if judge.prompt_sha256 != manifest.judge_prompt_sha256:
            raise EvaluationInvariantError("Judge prompt does not match the manifest")
        self._systems = dict(systems)
        self._answer_services = dict(answer_services)
        self._judge = judge
        self._checkpoints = checkpoints
        self._manifest = manifest
        self._work_semaphore = asyncio.Semaphore(manifest.concurrency.question_workers)
        self._judge_semaphore = asyncio.Semaphore(manifest.concurrency.judge_workers)

    async def run(self, questions: Sequence[ProbeQuestion]) -> EvaluationRun:
        try:
            ordered = tuple(
                sorted(
                    (ProbeQuestion.model_validate(item) for item in questions),
                    key=lambda item: item.id,
                )
            )
        except (TypeError, ValueError) as error:
            raise EvaluationInvariantError("evaluation questions failed validation") from error
        if not ordered:
            raise EvaluationInvariantError("evaluation question set must not be empty")
        question_ids = tuple(item.id for item in ordered)
        if len(question_ids) != len(set(question_ids)):
            raise EvaluationInvariantError("evaluation questions contain duplicate IDs")
        if len(ordered) != self._manifest.expected_questions:
            raise EvaluationInvariantError("evaluation question count does not match the manifest")
        if question_manifest_sha256(ordered) != self._manifest.question_manifest_sha256:
            raise EvaluationInvariantError("evaluation question manifest hash does not match")
        outcome = await bounded_collect(
            ordered,
            key=lambda item: item.id,
            worker=self._run_question,
            limit=self._manifest.concurrency.question_workers,
        )
        return self._build_run(ordered, outcome)

    async def _run_question(self, question: ProbeQuestion) -> QuestionExecution:
        system = self._systems.get(question.conversation_id)
        answer_service = self._answer_services.get(question.conversation_id)
        if system is None or answer_service is None:
            raise EvaluationInvariantError(
                f"prepared Conversation is unavailable for question {question.id}"
            )

        async with self._work_semaphore:
            traced = await system.retrieve_with_trace(
                question.question,
                EVIDENCE_BUDGET_TOKENS,
            )
            answer_payload = answer_service.request_payload(question.question, traced.evidence)
            answer_input_sha256 = self._checkpoint_input_sha256(
                question,
                prompt_sha256=answer_service.prompt_sha256,
                model=answer_service.model_name,
                payload=answer_payload,
            )
            answer = self._checkpoints.load(
                ANSWER_CHECKPOINT_STAGE,
                question.id,
                answer_input_sha256,
                QuestionAnswer,
            )
            if answer is None:
                result = await answer_service.answer(question.question, traced.evidence)
                answer = QuestionAnswer(
                    question_id=question.id,
                    conversation_id=question.conversation_id,
                    evidence=traced.evidence,
                    answer=result.answer,
                    citations=result.citations,
                    retrieval_trace=traced.trace,
                    usage=result.usage,
                )
                self._checkpoints.save(
                    ANSWER_CHECKPOINT_STAGE,
                    question.id,
                    answer_input_sha256,
                    QuestionAnswer,
                    answer,
                )
            else:
                self._validate_cached_answer(question, traced.trace.question_sha256, answer)

        try:
            async with self._judge_semaphore:
                judge_payload = self._judge.request_payload(question, answer)
                judge_input_sha256 = self._checkpoint_input_sha256(
                    question,
                    prompt_sha256=self._judge.prompt_sha256,
                    model=self._judge.model_name,
                    payload=judge_payload,
                )
                judgement = self._checkpoints.load(
                    JUDGE_CHECKPOINT_STAGE,
                    question.id,
                    judge_input_sha256,
                    JudgeResult,
                )
                if judgement is None:
                    judgement = await self._judge.judge(question, answer)
                    self._checkpoints.save(
                        JUDGE_CHECKPOINT_STAGE,
                        question.id,
                        judge_input_sha256,
                        JudgeResult,
                        judgement,
                    )
                elif judgement.question_id != question.id:
                    raise EvaluationInvariantError(
                        "cached Judge result does not match its question"
                    )
            return QuestionExecution(answer=answer, judgement=judgement, failure=None)
        except Exception as error:
            return QuestionExecution(
                answer=answer,
                judgement=None,
                failure=EvaluationFailure(
                    question_id=question.id,
                    stage="judge",
                    error_type=type(error).__name__,
                    message="judge failed",
                ),
            )

    def _build_run(
        self,
        expected: Sequence[ProbeQuestion],
        outcome: BatchOutcome[QuestionExecution],
    ) -> EvaluationRun:
        expected_ids = tuple(item.id for item in expected)
        answers = tuple(sorted((item.answer for item in outcome.values), key=_answer_key))
        judgements = tuple(
            sorted(
                (item.judgement for item in outcome.values if item.judgement is not None),
                key=_judgement_key,
            )
        )
        failures = [item.failure for item in outcome.values if item.failure is not None]
        failures.extend(
            EvaluationFailure(
                question_id=item.item_id,
                stage="retrieve_answer",
                error_type=item.error_type,
                message="retrieve and answer failed",
            )
            for item in outcome.failures
        )
        answer_ids = tuple(item.question_id for item in answers)
        judgement_ids = tuple(item.question_id for item in judgements)
        complete = answer_ids == expected_ids and judgement_ids == expected_ids and not failures
        return EvaluationRun(
            manifest_hash=self._manifest.content_hash,
            expected_question_ids=expected_ids,
            question_manifest_sha256=self._manifest.question_manifest_sha256,
            ke_ready_snapshot_id=self._manifest.ke_ready_snapshot_id,
            status=EvaluationStatus.COMPLETE if complete else EvaluationStatus.INCOMPLETE,
            answers=answers,
            judgements=judgements,
            failures=tuple(sorted(failures, key=_failure_key)),
        )

    def _checkpoint_input_sha256(
        self,
        question: ProbeQuestion,
        *,
        prompt_sha256: str,
        model: str,
        payload: JsonObject,
    ) -> str:
        payload_sha256 = hashlib.sha256(canonical_json(payload)).hexdigest()
        identity: JsonObject = {
            "manifest_hash": self._manifest.content_hash,
            "question": cast(JsonValue, question.model_dump(mode="json")),
            "ke_ready_snapshot_id": self._manifest.ke_ready_snapshot_id,
            "prompt_sha256": prompt_sha256,
            "model": model,
            "payload_sha256": payload_sha256,
        }
        return hashlib.sha256(canonical_json(identity)).hexdigest()

    @staticmethod
    def _validate_cached_answer(
        question: ProbeQuestion,
        question_sha256: str,
        answer: QuestionAnswer,
    ) -> None:
        if (
            answer.question_id != question.id
            or answer.conversation_id != question.conversation_id
            or answer.retrieval_trace.question_sha256 != question_sha256
        ):
            raise EvaluationInvariantError("cached answer does not match its question")


def _answer_key(item: QuestionAnswer) -> str:
    return item.question_id


def _judgement_key(item: JudgeResult) -> str:
    return item.question_id


def _failure_key(item: EvaluationFailure) -> tuple[str, str, str]:
    return item.question_id, item.stage, item.error_type
