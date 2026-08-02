"""Three comparable evaluation arms sharing one result contract.

Arms differ in exactly one respect: what evidence reaches the answer model.

- ``full_history`` sees the whole conversation, so it measures answer capability when no
  memory compression or ontology mapping is required. It is a capability upper bound and is
  budgeted separately for that reason.
- ``raw_dense_retrieval`` sees raw evidence units selected without ontology authority.
- ``ontology_memory`` sees what a frozen memory build plus symbolic execution selected.

The formal identities above are reserved for real backends. A lexical stand-in reports under
a ``fixture_*`` identity, because a review found stand-ins publishing as formal baselines,
which overstated what had run.

Selection and delivery are recorded separately. An arm that chose exactly the right evidence
and then lost half of it to the delivery budget is a different failure from one that chose
wrongly, and a single post-budget list cannot tell them apart.

Arms receive :class:`BenchmarkQuestion` and nothing else. The type carries three fields, and
:func:`assert_is_question_only` rejects even a subclass, so scoring material cannot arrive
through an arm's own interface.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from enum import StrEnum
from typing import Annotated, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ke_memory_demo.core.ids import content_id
from ke_memory_demo.core.json import JsonObject

from .channels import (
    BenchmarkQuestion,
    MemoryBuildInput,
    PublicTurn,
    assert_is_question_only,
)

NonEmptyString = Annotated[str, Field(min_length=1)]


class ArmError(ValueError):
    """An arm was configured or compared incorrectly."""


class ArmId(StrEnum):
    """Arm identities. Formal names are reserved for real backends."""

    FULL_HISTORY = "full_history"
    RAW_DENSE_RETRIEVAL = "raw_dense_retrieval"
    ONTOLOGY_MEMORY = "ontology_memory"
    FIXTURE_LEXICAL_RETRIEVAL = "fixture_lexical_retrieval"
    FIXTURE_LEXICAL_MEMORY = "fixture_lexical_memory"


FIXTURE_ARM_IDS: frozenset[ArmId] = frozenset(
    {ArmId.FIXTURE_LEXICAL_RETRIEVAL, ArmId.FIXTURE_LEXICAL_MEMORY}
)
FORMAL_ARM_IDS: frozenset[ArmId] = frozenset(
    {ArmId.FULL_HISTORY, ArmId.RAW_DENSE_RETRIEVAL, ArmId.ONTOLOGY_MEMORY}
)


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ArmBudget(_Record):
    """Delivery limits. Every comparable arm receives the same instance."""

    evidence_budget_tokens: int = Field(gt=0)
    answer_max_output_tokens: int = Field(gt=0)
    max_evidence_units: int = Field(gt=0)


class TokenizerContract(_Record):
    """How tokens are counted, and whether that count is authoritative.

    A budget only means something alongside the tokenizer that measures it. This one is a
    deterministic character-based approximation, declared as such: instrumentation must not
    depend on a provider tokenizer whose version can shift a budget between runs. Because it
    is approximate, it must not be used to claim a prompt fits a model's context window.
    """

    tokenizer_id: NonEmptyString
    is_provider_authoritative: bool
    chars_per_token: int = Field(gt=0)


APPROXIMATE_TOKENIZER = TokenizerContract(
    tokenizer_id="approx-chars-4",
    is_provider_authoritative=False,
    chars_per_token=4,
)


class ArmContract(_Record):
    """Everything that must match across arms for a comparison to mean anything.

    Comparing question-id sets is not sufficient: two arms can answer the same questions
    under different models, prompts, decoding settings or tokenizers and still be reported
    side by side. The hash makes divergence detectable rather than invisible.
    """

    model_id: NonEmptyString
    prompt_version: NonEmptyString
    temperature: float
    tokenizer: TokenizerContract
    budget: ArmBudget

    def contract_hash(self) -> str:
        return content_id(
            "arm-contract",
            {
                "model_id": self.model_id,
                "prompt_version": self.prompt_version,
                "temperature": self.temperature,
                "tokenizer": self.tokenizer.model_dump(),
                "budget": self.budget.model_dump(),
            },
        )


class ArmResult(_Record):
    """The shared result contract. Every arm returns exactly this shape."""

    arm: ArmId
    question_id: NonEmptyString
    conversation_handle: NonEmptyString
    selected_evidence_ids: tuple[str, ...]
    delivered_evidence_ids: tuple[str, ...]
    selected_evidence_tokens: int
    delivered_evidence_tokens: int
    answer_text: str
    abstained: bool
    oracle_layers: tuple[str, ...] = ()
    budget_limited: bool = False
    diagnostics: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_evidence_accounting(self) -> ArmResult:
        for name, ids, tokens in (
            ("selected", self.selected_evidence_ids, self.selected_evidence_tokens),
            ("delivered", self.delivered_evidence_ids, self.delivered_evidence_tokens),
        ):
            if tokens < 0:
                raise ArmError(f"{name}_evidence_tokens cannot be negative")
            if not ids and tokens:
                raise ArmError(
                    f"{name}_evidence_tokens must be zero when no evidence was {name}"
                )
            if len(set(ids)) != len(ids):
                raise ArmError(f"{name} evidence ids must be unique")
        if not set(self.delivered_evidence_ids) <= set(self.selected_evidence_ids):
            raise ArmError("delivered evidence must be a subset of selected evidence")
        if self.delivered_evidence_tokens > self.selected_evidence_tokens:
            raise ArmError("delivered tokens cannot exceed selected tokens")
        expected = len(self.delivered_evidence_ids) < len(self.selected_evidence_ids)
        if self.budget_limited != expected:
            raise ArmError(
                "budget_limited must be true exactly when delivery dropped evidence"
            )
        return self


class AnswerModel(Protocol):
    """Answer generation, injected so arms stay testable without a provider."""

    def answer(
        self,
        question: str,
        evidence: Sequence[PublicTurn],
        max_output_tokens: int,
    ) -> tuple[str, bool]: ...


class TurnSelector(Protocol):
    """Evidence selection, injected to keep gold out of production paths."""

    def select(
        self,
        question: BenchmarkQuestion,
        available: Sequence[PublicTurn],
    ) -> tuple[PublicTurn, ...]: ...


def turns_by_conversation(build_input: MemoryBuildInput) -> dict[str, tuple[PublicTurn, ...]]:
    """Flatten the build input into addressable turns per conversation."""
    return {
        c.conversation_handle: tuple(t for s in c.sessions for t in s.turns)
        for c in build_input.conversations
    }


class Arm:
    """Base arm. Subclasses differ only in which evidence they select."""

    arm_id: ArmId

    def __init__(self, model: AnswerModel, budget: ArmBudget) -> None:
        self._model = model
        self._budget = budget

    @property
    def budget(self) -> ArmBudget:
        return self._budget

    def select(
        self,
        question: BenchmarkQuestion,
        available: Sequence[PublicTurn],
    ) -> tuple[PublicTurn, ...]:
        raise NotImplementedError

    def run(
        self,
        question: BenchmarkQuestion,
        available: Sequence[PublicTurn],
    ) -> ArmResult:
        # The channel types make gold unrepresentable; this rejects a subclass smuggling
        # extra fields through at runtime.
        checked = assert_is_question_only(question)
        chosen = self.select(checked, available)
        delivered = _apply_budget(chosen, self._budget)
        answer_text, abstained = self._model.answer(
            checked.question,
            delivered,
            self._budget.answer_max_output_tokens,
        )
        return ArmResult(
            arm=self.arm_id,
            question_id=checked.question_id,
            conversation_handle=checked.conversation_handle,
            selected_evidence_ids=tuple(t.evidence_handle for t in chosen),
            delivered_evidence_ids=tuple(t.evidence_handle for t in delivered),
            selected_evidence_tokens=sum(t.approximate_tokens for t in chosen),
            delivered_evidence_tokens=sum(t.approximate_tokens for t in delivered),
            answer_text=answer_text,
            abstained=abstained,
            budget_limited=len(delivered) < len(chosen),
            diagnostics={
                "available_units": len(available),
                "selected_units": len(chosen),
                "delivered_units": len(delivered),
                "dropped_by_budget": len(chosen) - len(delivered),
            },
        )


class FullHistoryArm(Arm):
    """Sees everything, in order. No selection, only budget truncation."""

    arm_id = ArmId.FULL_HISTORY

    def select(
        self,
        question: BenchmarkQuestion,
        available: Sequence[PublicTurn],
    ) -> tuple[PublicTurn, ...]:
        return tuple(available)


class FixtureLexicalRetrievalArm(Arm):
    """Lexical-overlap retrieval fixture. Instrumentation, not the dense baseline."""

    arm_id = ArmId.FIXTURE_LEXICAL_RETRIEVAL

    def select(
        self,
        question: BenchmarkQuestion,
        available: Sequence[PublicTurn],
    ) -> tuple[PublicTurn, ...]:
        wanted = _terms(question.question)
        if not wanted:
            return tuple(available[: self._budget.max_evidence_units])
        scored = [
            (len(wanted & _terms(turn.text)), -index, turn)
            for index, turn in enumerate(available)
        ]
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return tuple(turn for score, _order, turn in scored if score > 0)


class MemoryArm(Arm):
    """Evidence chosen by a frozen memory build plus symbolic execution.

    The selector is injected, which is what lets an oracle substitute a layer without the
    production pipeline gaining any gold-reading code path. ``arm_id`` is supplied by the
    caller so a lexical stand-in reports as a fixture while a real backend reports as
    ``ontology_memory``.
    """

    def __init__(
        self,
        model: AnswerModel,
        budget: ArmBudget,
        selector: TurnSelector,
        arm_id: ArmId = ArmId.FIXTURE_LEXICAL_MEMORY,
    ) -> None:
        super().__init__(model, budget)
        self._selector = selector
        self.arm_id = arm_id

    def select(
        self,
        question: BenchmarkQuestion,
        available: Sequence[PublicTurn],
    ) -> tuple[PublicTurn, ...]:
        return self._selector.select(question, available)


def assert_arms_are_comparable(
    results: Sequence[ArmResult],
    budget: ArmBudget,
    *,
    contracts: Mapping[ArmId, ArmContract] | None = None,
    expected_arms: Collection[ArmId] | None = None,
) -> None:
    """Fail unless the arms form a genuinely comparable set.

    Checks no duplicate results, a complete arm set, identical question sets, identical
    contract hashes, and that nothing exceeded the shared delivery budget. An earlier
    version checked only question sets and the budget, leaving contract drift and missing
    arms undetected while still reporting the comparison as valid.
    """
    seen: set[tuple[ArmId, str]] = set()
    duplicates: list[str] = []
    by_arm: dict[ArmId, set[str]] = {}
    for result in results:
        key = (result.arm, result.question_id)
        if key in seen:
            duplicates.append(f"{result.arm}:{result.question_id}")
        seen.add(key)
        by_arm.setdefault(result.arm, set()).add(result.question_id)
    if duplicates:
        raise ArmError(f"duplicate arm results: {duplicates[:5]}")

    if expected_arms is not None:
        missing = sorted(str(a) for a in set(expected_arms) - set(by_arm))
        unexpected = sorted(str(a) for a in set(by_arm) - set(expected_arms))
        if missing or unexpected:
            raise ArmError(f"arm set is incomplete: missing={missing} unexpected={unexpected}")

    if contracts is not None:
        hashes = {arm: contract.contract_hash() for arm, contract in contracts.items()}
        undeclared = sorted(str(a) for a in set(by_arm) - set(hashes))
        if undeclared:
            raise ArmError(f"arms ran without a declared contract: {undeclared}")
        if len({h for arm, h in hashes.items() if arm in by_arm}) > 1:
            raise ArmError(
                "arm contracts diverge, so results are not comparable: "
                + ", ".join(f"{arm}={h[:16]}" for arm, h in sorted(hashes.items()))
            )

    if len(by_arm) >= 2:
        reference_arm, reference = next(iter(by_arm.items()))
        for arm, questions in by_arm.items():
            if questions != reference:
                raise ArmError(
                    f"arm {arm} is not comparable with {reference_arm}: "
                    f"missing={sorted(reference - questions)[:5]} "
                    f"extra={sorted(questions - reference)[:5]}"
                )

    over = [
        r.question_id
        for r in results
        if r.delivered_evidence_tokens > budget.evidence_budget_tokens
    ]
    if over:
        raise ArmError(f"arms exceeded the shared delivery budget: {over[:5]}")


def _apply_budget(
    turns: Sequence[PublicTurn],
    budget: ArmBudget,
) -> tuple[PublicTurn, ...]:
    kept: list[PublicTurn] = []
    tokens = 0
    for turn in turns[: budget.max_evidence_units]:
        if tokens + turn.approximate_tokens > budget.evidence_budget_tokens:
            break
        kept.append(turn)
        tokens += turn.approximate_tokens
    return tuple(kept)


_WORD = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    {
        "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "did", "do",
        "does", "is", "are", "was", "were", "what", "when", "where", "which", "who", "how",
        "why", "my", "i", "me", "you", "it", "that", "this", "about", "any", "have", "has",
    }
)


def _terms(text: str) -> set[str]:
    return {t for t in _WORD.findall(text.lower()) if t not in _STOPWORDS and len(t) > 2}
