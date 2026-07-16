from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypeVar

import pytest
from pydantic import BaseModel, ValidationError

from ke_memory_demo.domain import (
    ConceptRef,
    KnowledgeEquation,
    Lifecycle,
    Modality,
    Polarity,
    Speaker,
)
from ke_memory_demo.infra.telemetry import TraceContext
from ke_memory_demo.retrieval import (
    KEMatchDecision,
    KEMatchOutput,
    LLMMatcher,
    MatchRelation,
    MatcherInvariantError,
    QueryKE,
    SymbolicCandidate,
)


ModelT = TypeVar("ModelT", bound=BaseModel)


def _ke() -> KnowledgeEquation:
    return KnowledgeEquation.create(
        level="turn",
        lhs=ConceptRef(term_id="term-project", label="project"),
        rhs=ConceptRef(term_id="term-active", label="active"),
        gloss="the project is active",
        modality=Modality.FACT,
        polarity=Polarity.POSITIVE,
        lifecycle=Lifecycle.ACTIVE,
        speaker=Speaker.USER,
        produced_in_run_id="run-memory",
        produced_in_stage="turn-ke-extracted",
    )


def _query() -> QueryKE:
    return QueryKE(
        lhs=ConceptRef(term_id="term-project", label="project"),
        rhs=ConceptRef(term_id="term-status", label="status"),
        gloss="project status",
    )


class _MatchModel:
    def __init__(self, output: KEMatchOutput) -> None:
        self.output = output
        self.calls: list[tuple[Sequence[Mapping[str, object]], TraceContext]] = []

    async def complete(
        self,
        model_type: type[ModelT],
        messages: Sequence[Mapping[str, object]],
        trace_context: TraceContext | Mapping[str, object],
    ) -> ModelT:
        assert model_type is KEMatchOutput
        assert isinstance(trace_context, TraceContext)
        self.calls.append((messages, trace_context))
        return model_type.model_validate(self.output.model_dump(mode="python"))


@pytest.mark.parametrize("relation", tuple(MatchRelation))
def test_match_relations_are_exactly_the_contract_values(relation: MatchRelation) -> None:
    decision = KEMatchDecision(
        candidate_id="candidate-1",
        match_type=relation,
        confidence=0.8,
        reason="bounded semantic comparison",
    )

    assert decision.match_type is relation


def test_match_relation_rejects_values_outside_the_contract() -> None:
    with pytest.raises(ValidationError):
        KEMatchDecision.model_validate(
            {
                "candidate_id": "candidate-1",
                "match_type": "similar",
                "confidence": 0.8,
                "reason": "not an allowed relation",
            }
        )


async def test_matcher_receives_only_query_and_offered_symbolic_candidates() -> None:
    equation = _ke()
    candidate = SymbolicCandidate(
        candidate_id=equation.id,
        record_kind="knowledge_equation",
        knowledge_equation=equation,
        matched_fields=("term:term-project",),
    )
    output = KEMatchOutput(
        matches=(
            KEMatchDecision(
                candidate_id=equation.id,
                    match_type=MatchRelation.EQUIVALENT,
                confidence=0.9,
                reason="same project status assertion",
            ),
        )
    )
    model = _MatchModel(output)

    matches = await LLMMatcher(model, run_id="run-1").match(
        query_ke=_query(), symbolic_candidates=(candidate,)
    )

    assert matches == output.matches
    messages, trace = model.calls[0]
    assert "embedding" not in str(messages).casefold()
    assert trace.operation == "ke-match"
    assert len(str(trace.metadata["prompt_sha256"])) == 64


@pytest.mark.parametrize(
    "returned_id",
    [pytest.param("unoffered", id="unoffered"), pytest.param(None, id="missing")],
)
async def test_matcher_rejects_unoffered_or_missing_decisions(returned_id: str | None) -> None:
    equation = _ke()
    candidate = SymbolicCandidate(
        candidate_id=equation.id,
        record_kind="knowledge_equation",
        knowledge_equation=equation,
        matched_fields=("term:term-project",),
    )
    output = KEMatchOutput(
        matches=(
            (
                KEMatchDecision(
                    candidate_id=returned_id,
                    match_type=MatchRelation.RELATED,
                    confidence=0.5,
                    reason="returned by fake",
                ),
            )
            if returned_id is not None
            else ()
        )
    )

    with pytest.raises(MatcherInvariantError, match="missing|unoffered"):
        await LLMMatcher(_MatchModel(output), run_id="run-1").match(
            query_ke=_query(), symbolic_candidates=(candidate,)
        )
