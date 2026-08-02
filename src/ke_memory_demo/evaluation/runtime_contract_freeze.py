"""Freeze the contract the runtime actually uses.

Stage 1A's first freeze hashed a three-field ``PublicTurn`` triple and summed per-turn rounded
estimates. Both were rejected: the answer path sends nine-field ``Evidence`` records and counts
the whole serialized request once. The earlier hashes recompute correctly and describe a shape
nothing sends, so they are superseded here rather than amended — a hash that no longer
represents the path it names should not keep its authority.

This module freezes what :mod:`ke_memory_demo.request_contract` produces, by calling it. If the
runtime request shape changes, these hashes move, because the same function builds both.
"""

from __future__ import annotations

import hashlib
import inspect
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from ke_memory_demo.core.json import JsonObject, JsonValue, canonical_json
from ke_memory_demo.domain import Evidence
from ke_memory_demo.request_contract import (
    ANSWER_ARM_BUDGET_TERMS,
    ANSWER_TASK,
    OverLimitPolicy,
    RequestBudget,
    answer_arm_budget,
    approximate_tokens,
    build_answer_request,
    measure_request,
    serialized_request_bytes,
)

NonEmptyString = Annotated[str, Field(min_length=1)]

_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts/answer/system.md"


class RuntimeFreezeError(ValueError):
    """The runtime contract could not be frozen."""


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def _sha256_of(payload: JsonValue) -> str:
    return hashlib.sha256(canonical_json(payload)).hexdigest()


class RuntimeRequestFreeze(_Frozen):
    """The request shape, taken from the builder the runtime calls."""

    task: NonEmptyString
    builder_reference: NonEmptyString
    builder_source_sha256: NonEmptyString
    evidence_fields: tuple[str, ...]
    excluded_evidence_fields: tuple[str, ...]
    example_serialized_bytes: int
    counting_method: NonEmptyString

    def freeze_hash(self) -> str:
        return _sha256_of(self.model_dump(mode="json"))


class RuntimeBudgetFreeze(_Frozen):
    """The budget the runtime enforces, with its arithmetic and its enforcement point."""

    arm_identity: NonEmptyString
    terms: JsonObject
    request_budget_tokens: int
    arithmetic: NonEmptyString
    over_limit_policy: NonEmptyString
    enforcement_reference: NonEmptyString
    enforced_in_production: bool

    def freeze_hash(self) -> str:
        return _sha256_of(self.model_dump(mode="json"))


class RuntimeContractFreeze(_Frozen):
    """Both sections plus the statement of what they supersede."""

    request: RuntimeRequestFreeze
    budget: RuntimeBudgetFreeze
    supersedes: JsonObject

    def as_json(self) -> JsonObject:
        return {
            "request": self.request.model_dump(mode="json"),
            "request_sha256": self.request.freeze_hash(),
            "budget": self.budget.model_dump(mode="json"),
            "budget_sha256": self.budget.freeze_hash(),
            "supersedes": self.supersedes,
            "hash_scope": (
                "each digest covers its own section only, so a change to the request shape and a "
                "change to the budget move different hashes"
            ),
        }


def _example_evidence() -> tuple[Evidence, ...]:
    """A minimal record used only to capture the field set the runtime sends."""
    return (
        Evidence(
            evidence_id="e1",
            rank=1,
            score=1.0,
            channel="symbolic",
            text="frozen example",
            source_exchange_ids=("x1",),
            source_message_ids=("m1",),
            system_record_ids=(),
            metadata={},
            token_count=3,
        ),
    )


def freeze_runtime_request() -> RuntimeRequestFreeze:
    """Capture the request shape by building one."""
    evidence = _example_evidence()
    request = build_answer_request("frozen example question", evidence)
    records = request["evidence"]
    if not isinstance(records, list) or not records:
        raise RuntimeFreezeError("the builder produced no evidence records to freeze")
    first = records[0]
    if not isinstance(first, dict):
        raise RuntimeFreezeError("an evidence record was not an object")

    source = inspect.getsource(build_answer_request) + inspect.getsource(
        serialized_request_bytes
    )
    return RuntimeRequestFreeze(
        task=str(request["task"]),
        builder_reference=(
            f"{build_answer_request.__module__}.{build_answer_request.__qualname__}"
        ),
        builder_source_sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
        evidence_fields=tuple(sorted(first)),
        # token_count is excluded by model_evidence_payload, so the model never sees it.
        excluded_evidence_fields=("token_count",),
        example_serialized_bytes=len(
            serialized_request_bytes("frozen example question", evidence)
        ),
        counting_method=(
            "approximate_tokens over the whole serialized request once; per-component rounded "
            "sums drift from this total and may not be substituted"
        ),
    )


def freeze_runtime_budget(budget: RequestBudget | None = None) -> RuntimeBudgetFreeze:
    """Capture the budget the runtime enforces."""
    effective = budget if budget is not None else answer_arm_budget()
    from ke_memory_demo import answering

    enforced = "enforce_budget(" in inspect.getsource(answering.AnswerService)
    return RuntimeBudgetFreeze(
        arm_identity=effective.arm_identity,
        terms=dict(ANSWER_ARM_BUDGET_TERMS)
        if budget is None
        else {
            "context_window_tokens": effective.context_window_tokens,
            "system_reserve_tokens": effective.system_reserve_tokens,
            "output_reserve_tokens": effective.output_reserve_tokens,
            "safety_margin_tokens": effective.safety_margin_tokens,
        },
        request_budget_tokens=effective.request_budget_tokens,
        arithmetic=effective.arithmetic(),
        over_limit_policy=str(effective.over_limit_policy),
        enforcement_reference="ke_memory_demo.request_contract.enforce_budget",
        # Measured from the source rather than asserted: a helper only tests call enforces
        # nothing, which is why the previous freeze bound no behaviour.
        enforced_in_production=enforced,
    )


def freeze_runtime_contract(
    superseded_hashes: JsonObject | None = None,
) -> RuntimeContractFreeze:
    """Freeze both sections and record what they replace."""
    request = freeze_runtime_request()
    budget = freeze_runtime_budget()
    if not budget.enforced_in_production:
        raise RuntimeFreezeError(
            "the budget is not enforced in production, so freezing it would record a "
            "constraint that does not bind"
        )
    if len(request.evidence_fields) < 5:
        raise RuntimeFreezeError(
            "the frozen request carries too few evidence fields to be the runtime shape; the "
            "earlier freeze bound a three-field stand-in"
        )
    return RuntimeContractFreeze(
        request=request,
        budget=budget,
        supersedes={
            "superseded_artifact": "artifacts/stage-1a/contract-freeze.json",
            "reason": (
                "that freeze hashed a three-field PublicTurn triple and summed per-turn rounded "
                "estimates, while the runtime sends nine-field Evidence records counted once "
                "over the whole serialized request"
            ),
            "superseded_hashes": superseded_hashes or {},
            "authority": (
                "the superseded hashes recompute correctly but no longer represent the path they "
                "name, so they carry no authority over a run"
            ),
        },
    )


def measure_eligibility(
    questions: Sequence[tuple[str, str]],
    evidence_by_question: dict[str, Sequence[Evidence]],
    budget: RequestBudget | None = None,
) -> JsonObject:
    """Recompute eligibility through the shared contract, one count per request."""
    effective = budget if budget is not None else answer_arm_budget()
    eligible: list[str] = []
    ineligible: list[str] = []
    measurements: dict[str, int] = {}

    for question_id, question_text in questions:
        evidence = evidence_by_question.get(question_id, ())
        measurement = measure_request(question_text, evidence, effective)
        measurements[question_id] = measurement.request_tokens
        (eligible if measurement.fits else ineligible).append(question_id)

    eligible_tokens = [measurements[q] for q in eligible]
    ineligible_tokens = [measurements[q] for q in ineligible]
    result: JsonObject = {
        # str() coerces pydantic's constrained string alias, which the JSON type does not admit.
        "arm_identity": str(effective.arm_identity),
        "request_budget_tokens": effective.request_budget_tokens,
        "coverage": f"{len(eligible)}/{len(questions)}",
        "eligible_count": len(eligible),
        "ineligible_item_ids": [str(item) for item in sorted(ineligible)],
        "largest_eligible_request_tokens": max(eligible_tokens) if eligible_tokens else 0,
        "smallest_ineligible_request_tokens": (
            min(ineligible_tokens) if ineligible_tokens else 0
        ),
        "boundary_gap_tokens": (
            min(ineligible_tokens) - max(eligible_tokens)
            if eligible_tokens and ineligible_tokens
            else 0
        ),
        "counting_basis": (
            "approximate_tokens over the full serialized request, measured once per question "
            "through request_contract.measure_request"
        ),
        "standing": (
            "diagnostic: the tokenizer is a character approximation and is not provider "
            "authoritative, so this bounds instrumentation and cannot prove a request fits"
        ),
    }
    return result


def prompt_sha256() -> str:
    return hashlib.sha256(_PROMPT_PATH.read_bytes()).hexdigest()


def system_reserve_tokens() -> int:
    """The system reserve, measured from the real prompt bytes."""
    return approximate_tokens(_PROMPT_PATH.read_bytes())


__all__ = [
    "ANSWER_TASK",
    "OverLimitPolicy",
    "RuntimeBudgetFreeze",
    "RuntimeContractFreeze",
    "RuntimeFreezeError",
    "RuntimeRequestFreeze",
    "freeze_runtime_budget",
    "freeze_runtime_contract",
    "freeze_runtime_request",
    "measure_eligibility",
    "prompt_sha256",
    "system_reserve_tokens",
]
