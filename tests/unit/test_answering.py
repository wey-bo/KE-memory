from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from typing import TypeVar

import pytest
from pydantic import BaseModel

from ke_memory_demo.answering import (
    ANSWER_MAX_OUTPUT_TOKENS,
    ANSWER_MODEL,
    AnswerInvariantError,
    AnswerModelOutput,
    AnswerService,
)
from ke_memory_demo.domain import Evidence
from ke_memory_demo.infra.telemetry import TraceContext, UsageRecord


ModelT = TypeVar("ModelT", bound=BaseModel)


class _UsageSource:
    def __init__(self) -> None:
        self.values: tuple[UsageRecord, ...] = ()

    @property
    def usage_records(self) -> tuple[UsageRecord, ...]:
        return self.values


class _CharacterTokenCounter:
    def count(self, text: str) -> int:
        return len(text)


class _AnswerClient:
    def __init__(
        self,
        output: AnswerModelOutput,
        usage_source: _UsageSource,
        *,
        model_name: str = "gpt-5.4",
        max_output_tokens: int = 1024,
    ) -> None:
        self.model_name = model_name
        self.max_output_tokens = max_output_tokens
        self.output = output
        self.usage_source = usage_source
        self.calls: list[tuple[type[BaseModel], Sequence[Mapping[str, object]], TraceContext]] = []

    async def complete(
        self,
        model_type: type[ModelT],
        messages: Sequence[Mapping[str, object]],
        trace_context: TraceContext | Mapping[str, object],
    ) -> ModelT:
        assert isinstance(trace_context, TraceContext)
        self.calls.append((model_type, messages, trace_context))
        self.usage_source.values = (
            *self.usage_source.values,
            UsageRecord(
                request_id="request-answer-1",
                model=self.model_name,
                latency_seconds=0.25,
                input_tokens=40,
                output_tokens=12,
                total_tokens=52,
            ),
        )
        return model_type.model_validate(self.output.model_dump(mode="python"))


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
    usage = _UsageSource()
    client = _AnswerClient(
        AnswerModelOutput(answer="The project is active.", citations=("evidence-1",)),
        usage,
    )
    service = AnswerService(client, usage, token_counter=_CharacterTokenCounter())

    result = await service.answer("What is the project status?", (_evidence(),))

    assert ANSWER_MODEL == "gpt-5.4"
    assert ANSWER_MAX_OUTPUT_TOKENS == 1024
    assert result.answer == "The project is active."
    assert result.citations == ("evidence-1",)
    assert result.usage == usage.usage_records[0]
    model_type, messages, trace = client.calls[0]
    assert model_type is AnswerModelOutput
    assert messages[0]["role"] == "system"
    payload = json.loads(str(messages[1]["content"]))
    assert set(payload) == {"task", "question", "evidence"}
    assert payload["question"] == "What is the project status?"
    assert payload["evidence"][0]["evidence_id"] == "evidence-1"
    assert "token_count" not in payload["evidence"][0]
    assert trace.operation == "common-answer"
    assert trace.metadata["model"] == "gpt-5.4"
    assert trace.metadata["max_output_tokens"] == 1024
    assert len(str(trace.metadata["prompt_sha256"])) == 64


@pytest.mark.parametrize(
    ("model_name", "max_output_tokens"),
    [
        pytest.param("other-model", 1024, id="model"),
        pytest.param("gpt-5.4", 2048, id="output-limit"),
    ],
)
def test_answer_service_rejects_nonfixed_client_configuration(
    model_name: str,
    max_output_tokens: int,
) -> None:
    usage = _UsageSource()
    client = _AnswerClient(
        AnswerModelOutput(answer="answer", citations=()),
        usage,
        model_name=model_name,
        max_output_tokens=max_output_tokens,
    )

    with pytest.raises(AnswerInvariantError, match="gpt-5.4|1024"):
        AnswerService(client, usage, token_counter=_CharacterTokenCounter())


async def test_answer_service_rejects_a_citation_not_in_packed_evidence() -> None:
    usage = _UsageSource()
    client = _AnswerClient(
        AnswerModelOutput(answer="unsupported", citations=("invented",)),
        usage,
    )

    with pytest.raises(AnswerInvariantError, match="unoffered citation"):
        await AnswerService(client, usage, token_counter=_CharacterTokenCounter()).answer(
            "question", (_evidence(),)
        )


async def test_answer_service_rejects_full_serialized_evidence_above_hard_limit() -> None:
    usage = _UsageSource()
    client = _AnswerClient(AnswerModelOutput(answer="unused"), usage)
    oversized = _evidence().model_copy(
        update={"metadata": {"provenance": "p" * 8192}, "token_count": 1}
    )

    with pytest.raises(AnswerInvariantError, match="8192-token hard limit"):
        await AnswerService(client, usage, token_counter=_CharacterTokenCounter()).answer(
            "question", (oversized,)
        )

    assert client.calls == []
