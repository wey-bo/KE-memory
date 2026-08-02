from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from typing import TypeVar

import pytest
from pydantic import BaseModel

from ke_memory_demo.request_contract import RequestBudget
from ke_memory_demo.answering import (
    ANSWER_MAX_OUTPUT_TOKENS,
    ANSWER_MODEL,
    AnswerInvariantError,
    AnswerModelOutput,
    AnswerService,
)
from ke_memory_demo.domain import Evidence
from ke_memory_demo.infra.llm import StructuredCompletion
from ke_memory_demo.infra.telemetry import TraceContext, UsageRecord


ModelT = TypeVar("ModelT", bound=BaseModel)


class _CharacterTokenCounter:
    def count(self, text: str) -> int:
        return len(text)


class _AnswerClient:
    def __init__(
        self,
        output: AnswerModelOutput,
        *,
        model_name: str = "deepseek-v4-flash",
        max_output_tokens: int = 1024,
    ) -> None:
        self.model_name = model_name
        self.max_output_tokens = max_output_tokens
        self.output = output
        self.usage = UsageRecord(
            request_id="request-answer-1",
            model=self.model_name,
            latency_seconds=0.25,
            input_tokens=40,
            output_tokens=12,
            total_tokens=52,
        )
        self.calls: list[tuple[type[BaseModel], Sequence[Mapping[str, object]], TraceContext]] = []

    async def complete_with_usage(
        self,
        model_type: type[ModelT],
        messages: Sequence[Mapping[str, object]],
        trace_context: TraceContext | Mapping[str, object],
    ) -> StructuredCompletion[ModelT]:
        assert isinstance(trace_context, TraceContext)
        self.calls.append((model_type, messages, trace_context))
        return StructuredCompletion(
            value=model_type.model_validate(self.output.model_dump(mode="python")),
            usage=self.usage,
        )


def _evidence() -> Evidence:
    return Evidence(
        evidence_id="evidence-1",
        text="The project is active.",
        source_exchange_ids=("exchange-1",),
        source_message_ids=("message-1",),
        system_record_ids=("ke-1",),
        score=0.9,
        rank=1,
        channel="symbolic",
        metadata={"match_type": "equivalent"},
        token_count=5,
    )


async def test_answer_service_uses_fixed_prompt_configuration_citations_and_usage() -> None:
    client = _AnswerClient(
        AnswerModelOutput(answer="The project is active.", citations=("evidence-1",))
    )
    service = AnswerService(client, token_counter=_CharacterTokenCounter())

    result = await service.answer("What is the project status?", (_evidence(),))

    assert ANSWER_MODEL == "deepseek-v4-flash"
    assert ANSWER_MAX_OUTPUT_TOKENS == 1024
    assert result.answer == "The project is active."
    assert result.citations == ("evidence-1",)
    assert result.usage == client.usage
    model_type, messages, trace = client.calls[0]
    assert model_type is AnswerModelOutput
    assert messages[0]["role"] == "system"
    payload = json.loads(str(messages[1]["content"]))
    assert set(payload) == {"task", "question", "evidence"}
    assert payload["question"] == "What is the project status?"
    assert payload["evidence"][0]["evidence_id"] == "evidence-1"
    assert "token_count" not in payload["evidence"][0]
    assert trace.operation == "common-answer"
    assert trace.metadata["model"] == "deepseek-v4-flash"
    assert trace.metadata["max_output_tokens"] == 1024
    assert len(str(trace.metadata["prompt_sha256"])) == 64


@pytest.mark.parametrize(
    ("model_name", "max_output_tokens"),
    [
        pytest.param("other-model", 1024, id="model"),
        pytest.param("deepseek-v4-flash", 2048, id="output-limit"),
    ],
)
def test_answer_service_rejects_nonfixed_client_configuration(
    model_name: str,
    max_output_tokens: int,
) -> None:
    client = _AnswerClient(
        AnswerModelOutput(answer="answer", citations=()),
        model_name=model_name,
        max_output_tokens=max_output_tokens,
    )

    with pytest.raises(AnswerInvariantError, match="deepseek-v4-flash|1024"):
        AnswerService(client, token_counter=_CharacterTokenCounter())


async def test_answer_service_rejects_a_citation_not_in_packed_evidence() -> None:
    client = _AnswerClient(AnswerModelOutput(answer="unsupported", citations=("invented",)))

    with pytest.raises(AnswerInvariantError, match="unoffered citation"):
        await AnswerService(client, token_counter=_CharacterTokenCounter()).answer(
            "question", (_evidence(),)
        )


async def test_answer_service_refuses_a_request_over_its_injected_budget() -> None:
    """Enforcement must run in production, through the shared contract.

    The former check compared an evidence-only count against a module constant of 8192 that no
    contract could see. The budget is now injected, names its arm, and is applied to the whole
    serialized request, so this test pins the real refusal path rather than a private threshold.
    """
    client = _AnswerClient(AnswerModelOutput(answer="unused"))
    # A budget small enough that the serialized request cannot fit.
    tight = RequestBudget(
        arm_identity="test_arm",
        context_window_tokens=400,
        system_reserve_tokens=10,
        output_reserve_tokens=20,
        safety_margin_tokens=5,
    )
    oversized = _evidence().model_copy(
        update={"metadata": {"provenance": "p" * 8192}, "token_count": 1}
    )

    with pytest.raises(AnswerInvariantError, match="not_executed_context_limit"):
        await AnswerService(
            client, token_counter=_CharacterTokenCounter(), budget=tight
        ).answer("question", (oversized,))

    assert client.calls == []


@pytest.mark.asyncio
async def test_the_answer_arm_budget_is_declared_by_the_contract() -> None:
    """A service must not hold an unbound number, even a correct one."""
    service = AnswerService(
        _AnswerClient(AnswerModelOutput(answer="ok")),
        token_counter=_CharacterTokenCounter(),
    )
    assert service.budget.arm_identity == "answer_arm"
    assert service.budget is not None
    # The arithmetic is derivable, so an audit can recompute it rather than trust it.
    assert str(service.budget.request_budget_tokens) in service.budget.arithmetic()
