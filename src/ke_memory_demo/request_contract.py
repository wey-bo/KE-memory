"""The one request builder the answer path and the contract freeze both use.

Four rounds of contract work froze a synthetic ``{evidence_handle, speaker, text}`` triple
while :class:`AnswerService` sent ``model_evidence_payload(Evidence)`` — full Evidence records
with rank, score, channel, source ids and metadata. The hashes recomputed correctly and still
constrained nothing, because they described a shape the runtime never sends.

There were also three unreconciled budgets: 8192 inside ``AnswerService``, 24576 for the
delivery arm, and 124285 from the freeze. A contract that names one of three numbers is not a
contract.

So this module owns request construction and budget enforcement, and both callers consume it:

- :func:`build_answer_request` produces the exact payload that goes on the wire.
- :func:`serialized_request_bytes` produces the exact bytes, once, for counting.
- :class:`RequestBudget` names the arm it belongs to, so different arms may hold different
  numbers while no number is left unbound.
- :func:`enforce_budget` is the only place the over-limit policy is applied, and production
  calls it. A helper that only tests call enforces nothing.

Counting happens on the whole serialized request rather than per component. Summing
per-component rounded estimates drifts from the real total by tens of tokens, which the review
measured at -42 to +15, and an eligibility claim built on that is approximate in a way its name
did not admit.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field

from ke_memory_demo.core.json import JsonObject, canonical_json
from ke_memory_demo.domain import Evidence
from ke_memory_demo.retrieval.evidence_payload import model_evidence_payload

NonEmptyString = Annotated[str, Field(min_length=1)]

# The task discriminator the answer path sends. Kept here so the freeze hashes the same string
# the runtime emits rather than a copy that can drift.
ANSWER_TASK: Final[str] = "answer_from_evidence"

# The answer arm's budget, declared here so the value is discoverable from the contract rather
# than hidden in a service module. deepseek-v4-flash advertises a 128000-token context; the
# system reserve is measured from the real prompt and the output reserve matches
# ANSWER_MAX_OUTPUT_TOKENS.
ANSWER_ARM_BUDGET_TERMS: Final[dict[str, int]] = {
    "context_window_tokens": 128_000,
    "system_reserve_tokens": 116,
    "output_reserve_tokens": 1024,
    "safety_margin_tokens": 2560,
}


def answer_arm_budget() -> "RequestBudget":
    """The answer arm's budget, built from the declared terms."""
    return RequestBudget(
        arm_identity="answer_arm",
        context_window_tokens=ANSWER_ARM_BUDGET_TERMS["context_window_tokens"],
        system_reserve_tokens=ANSWER_ARM_BUDGET_TERMS["system_reserve_tokens"],
        output_reserve_tokens=ANSWER_ARM_BUDGET_TERMS["output_reserve_tokens"],
        safety_margin_tokens=ANSWER_ARM_BUDGET_TERMS["safety_margin_tokens"],
    )


class RequestBuildError(ValueError):
    """A request could not be built, or violates the frozen budget."""


class OverLimitPolicy(StrEnum):
    """What to do when a request cannot fit.

    Only one value exists on purpose. Truncating and continuing was available in earlier
    versions and produced a truncated-history condition reported as full history.
    """

    NOT_EXECUTED_CONTEXT_LIMIT = "not_executed_context_limit"


class RequestBudget(BaseModel):
    """A budget, carrying the arm it belongs to.

    Different arms may legitimately hold different numbers, so the type is not a singleton. What
    it removes is an *unbound* number: every budget names its arm, and a service receives one
    explicitly instead of closing over a module constant that no contract can see.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    arm_identity: NonEmptyString
    context_window_tokens: int = Field(gt=0)
    system_reserve_tokens: int = Field(ge=0)
    output_reserve_tokens: int = Field(gt=0)
    safety_margin_tokens: int = Field(ge=0)
    over_limit_policy: OverLimitPolicy = OverLimitPolicy.NOT_EXECUTED_CONTEXT_LIMIT

    @property
    def request_budget_tokens(self) -> int:
        """Tokens available for the serialized user request."""
        available = (
            self.context_window_tokens
            - self.system_reserve_tokens
            - self.output_reserve_tokens
            - self.safety_margin_tokens
        )
        if available <= 0:
            raise RequestBuildError(
                "the reserves exhaust the context window, leaving no room for a request"
            )
        return available

    def arithmetic(self) -> str:
        return (
            f"[{self.arm_identity}] {self.context_window_tokens} context"
            f" - {self.system_reserve_tokens} system"
            f" - {self.output_reserve_tokens} output"
            f" - {self.safety_margin_tokens} margin"
            f" = {self.request_budget_tokens} request"
        )


class RequestMeasurement(BaseModel):
    """One count over one serialized request."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    serialized_bytes: int
    request_tokens: int
    budget_tokens: int
    evidence_count: int

    @property
    def fits(self) -> bool:
        return self.request_tokens <= self.budget_tokens

    @property
    def headroom_tokens(self) -> int:
        return self.budget_tokens - self.request_tokens


def build_answer_request(
    question: str,
    evidence: Sequence[Evidence],
) -> JsonObject:
    """Build the exact payload the answer model receives.

    ``AnswerService.request_payload`` delegates here, so the freeze and the runtime cannot
    describe different requests.
    """
    if not question.strip():
        raise RequestBuildError("a request requires a non-empty question")
    return {
        "task": ANSWER_TASK,
        "question": question,
        "evidence": list(model_evidence_payload(evidence)),
    }


def serialized_request_bytes(question: str, evidence: Sequence[Evidence]) -> bytes:
    """The exact bytes sent as the user message."""
    return canonical_json(build_answer_request(question, evidence))


def approximate_tokens(payload: bytes) -> int:
    """Token estimate over a whole serialized payload.

    Deliberately takes bytes rather than a sequence of parts. Rounding each part separately and
    summing drifts from the true total, and a budget decision made on the drifted figure is
    wrong in a way the name "exact" would conceal.
    """
    return max(1, (len(payload) + 3) // 4)


def measure_request(
    question: str,
    evidence: Sequence[Evidence],
    budget: RequestBudget,
) -> RequestMeasurement:
    """Count the complete serialized request once, against the single budget."""
    payload = serialized_request_bytes(question, evidence)
    return RequestMeasurement(
        serialized_bytes=len(payload),
        request_tokens=approximate_tokens(payload),
        budget_tokens=budget.request_budget_tokens,
        evidence_count=len(evidence),
    )


def enforce_budget(
    question: str,
    evidence: Sequence[Evidence],
    budget: RequestBudget,
) -> RequestMeasurement:
    """Apply the over-limit policy. The only place that decision is made.

    Raises rather than trimming: the policy is ``not_executed_context_limit``, so a request that
    does not fit is not executed, and the caller records it as such.
    """
    measurement = measure_request(question, evidence, budget)
    if not measurement.fits:
        raise RequestBuildError(
            f"{budget.over_limit_policy}: the serialized request needs "
            f"{measurement.request_tokens} tokens against a budget of "
            f"{measurement.budget_tokens}, so it is not executed rather than truncated"
        )
    return measurement
