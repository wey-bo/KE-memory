from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Literal, TypeVar, cast

import pytest
from pydantic import BaseModel, ValidationError

from ke_memory_demo.domain import (
    ConceptRef,
    IndividualRef,
    KnowledgeEquation,
    MessageSpan,
    OperatorApplication,
    OperatorRef,
    TemporalMetadata,
)
from ke_memory_demo.extraction import (
    LifecycleInvariantError,
    LifecycleMaintainer,
    LifecycleMatchDecision,
    LifecycleMatchOutput,
)
from ke_memory_demo.infra.telemetry import TraceContext


ModelT = TypeVar("ModelT", bound=BaseModel)


class FakeMatcher:
    def __init__(self, output: LifecycleMatchOutput) -> None:
        self.output = output
        self.calls: list[tuple[type[BaseModel], Sequence[Mapping[str, object]], TraceContext]] = []

    async def complete(
        self,
        model_type: type[ModelT],
        messages: Sequence[Mapping[str, object]],
        trace_context: TraceContext | Mapping[str, object],
    ) -> ModelT:
        context = (
            trace_context
            if isinstance(trace_context, TraceContext)
            else TraceContext.model_validate(trace_context)
        )
        self.calls.append((cast(type[BaseModel], model_type), messages, context))
        assert model_type is LifecycleMatchOutput
        return cast(ModelT, self.output)


def _ke(
    value: str,
    *,
    subject: str = "alice",
    operator: str = "likes",
    modality: str = "preference",
    polarity: str = "positive",
    lifecycle: str = "active",
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
    run_id: str = "source-run",
) -> KnowledgeEquation:
    return KnowledgeEquation.create(
        level="turn",
        lhs=IndividualRef(term_id=subject, label=subject.title()),
        rhs=OperatorApplication(
            operator=OperatorRef(term_id=operator, label=operator),
            arguments=(ConceptRef(term_id=value, label=value),),
        ),
        gloss=f"{subject} {operator} {value}",
        modality=modality,
        polarity=polarity,
        lifecycle=lifecycle,
        speaker="user",
        temporal=TemporalMetadata(valid_from=valid_from, valid_to=valid_to),
        evidence_refs=(
            MessageSpan(
                message_id=f"message-{value}",
                start_char=0,
                end_char=1,
                text_hash="0" * 64,
            ),
        ),
        confidence=0.9,
        produced_in_run_id=run_id,
        produced_in_stage="turn-ke-extracted",
    )


def _decision(
    old: KnowledgeEquation,
    new: KnowledgeEquation,
    decision: Literal["contradicts", "updates", "no_match"],
    *,
    explicit_retraction: bool = False,
) -> LifecycleMatchDecision:
    return LifecycleMatchDecision(
        old_ke_id=old.id,
        new_ke_id=new.id,
        decision=decision,
        confidence=0.91,
        reason=f"test {decision}",
        explicit_retraction=explicit_retraction,
    )


@pytest.mark.asyncio
async def test_no_match_appends_new_unchanged() -> None:
    old = _ke("red")
    new = _ke("blue")
    matcher = FakeMatcher(LifecycleMatchOutput(matches=(_decision(old, new, "no_match"),)))

    result = await LifecycleMaintainer(matcher, run_id="lifecycle-run").apply(
        (old,),
        (new,),
    )

    assert result.appended_revisions == (new,)
    assert result.current_records == tuple(sorted((old, new), key=lambda ke: ke.id))
    assert result.decisions == matcher.output.matches
    assert matcher.calls[0][2] == TraceContext(
        operation="turn-ke-lifecycle-match",
        metadata={"run_id": "lifecycle-run"},
    )


@pytest.mark.asyncio
async def test_contradiction_appends_bidirectional_links_without_hiding_either_ke() -> None:
    old = _ke("remote", polarity="positive")
    new = _ke("office", polarity="negative")
    old_before = old.model_dump_json()
    new_before = new.model_dump_json()
    matcher = FakeMatcher(LifecycleMatchOutput(matches=(_decision(old, new, "contradicts"),)))

    result = await LifecycleMaintainer(matcher, run_id="lifecycle-run").apply(
        (old,),
        (new,),
    )

    revised = {ke.id: ke for ke in result.appended_revisions}
    assert revised[old.id].contradicts == (new.id,)
    assert revised[new.id].contradicts == (old.id,)
    assert revised[old.id].lifecycle == old.lifecycle
    assert revised[new.id].lifecycle == new.lifecycle
    assert revised[old.id].revision != old.revision
    assert old.model_dump_json() == old_before
    assert new.model_dump_json() == new_before
    assert KnowledgeEquation.model_validate_json(old_before) == old


@pytest.mark.asyncio
async def test_update_supersedes_old_and_links_new_revision() -> None:
    old = _ke("red")
    new = _ke("blue")
    matcher = FakeMatcher(LifecycleMatchOutput(matches=(_decision(old, new, "updates"),)))

    result = await LifecycleMaintainer(matcher, run_id="lifecycle-run").apply(
        (old,),
        (new,),
    )

    revised = {ke.id: ke for ke in result.appended_revisions}
    assert revised[old.id].lifecycle.value == "superseded"
    assert revised[new.id].supersedes == (old.id,)
    assert revised[new.id].lifecycle.value == "active"
    assert all(ke.produced_in_run_id == "lifecycle-run" for ke in revised.values())
    assert all(ke.produced_in_stage == "lifecycle-maintained" for ke in revised.values())


@pytest.mark.asyncio
async def test_explicit_retraction_retracts_old_and_keeps_new_statement_visible() -> None:
    old = _ke("red")
    retraction = _ke("withdraw-red", polarity="negative", lifecycle="uncertain")
    matcher = FakeMatcher(
        LifecycleMatchOutput(
            matches=(_decision(old, retraction, "updates", explicit_retraction=True),)
        )
    )

    result = await LifecycleMaintainer(matcher, run_id="lifecycle-run").apply(
        (old,),
        (retraction,),
    )

    revised = {ke.id: ke for ke in result.appended_revisions}
    assert revised[old.id].lifecycle.value == "retracted"
    assert revised[retraction.id].lifecycle.value == "uncertain"
    assert revised[retraction.id].supersedes == (old.id,)


@pytest.mark.asyncio
async def test_explicit_retraction_takes_precedence_over_another_update() -> None:
    old = _ke("red")
    first, second = sorted((_ke("blue"), _ke("green")), key=lambda equation: equation.id)
    matcher = FakeMatcher(
        LifecycleMatchOutput(
            matches=(
                _decision(old, first, "updates", explicit_retraction=True),
                _decision(old, second, "updates"),
            )
        )
    )

    result = await LifecycleMaintainer(matcher, run_id="lifecycle-run").apply(
        (old,),
        (first, second),
    )

    revised_old = next(ke for ke in result.appended_revisions if ke.id == old.id)
    assert revised_old.lifecycle.value == "retracted"


@pytest.mark.asyncio
async def test_new_records_must_enter_lifecycle_maintenance_visible() -> None:
    old = _ke("red", subject="other")
    invalid_new = _ke("blue", lifecycle="superseded")

    with pytest.raises(LifecycleInvariantError, match="active or uncertain"):
        await LifecycleMaintainer(
            FakeMatcher(LifecycleMatchOutput(matches=())),
            run_id="lifecycle-run",
        ).apply((old,), (invalid_new,))


@pytest.mark.asyncio
async def test_only_last_historical_revision_is_offered_as_current_candidate() -> None:
    old_active = _ke("red")
    old_uncertain = KnowledgeEquation.create(
        level=old_active.level,
        lhs=old_active.lhs,
        rhs=old_active.rhs,
        gloss=old_active.gloss,
        modality=old_active.modality,
        polarity=old_active.polarity,
        lifecycle="uncertain",
        speaker=old_active.speaker,
        temporal=old_active.temporal,
        ontology_bindings=old_active.ontology_bindings,
        evidence_refs=old_active.evidence_refs,
        derived_from=old_active.derived_from,
        contradicts=old_active.contradicts,
        supersedes=old_active.supersedes,
        confidence=old_active.confidence,
        produced_in_run_id="later-run",
        produced_in_stage="lifecycle-maintained",
    )
    new = _ke("blue")
    matcher = FakeMatcher(
        LifecycleMatchOutput(matches=(_decision(old_uncertain, new, "no_match"),))
    )

    result = await LifecycleMaintainer(matcher, run_id="lifecycle-run").apply(
        (old_active, old_uncertain),
        (new,),
    )

    assert old_active.id == old_uncertain.id
    assert result.appended_revisions == (new,)
    assert {ke.id: ke for ke in result.current_records}[old_active.id] == old_uncertain
    assert old_active.revision != old_uncertain.revision
    assert "later-run" in str(matcher.calls[0][1])


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["missing", "duplicate", "unoffered"])
async def test_matcher_output_must_exactly_cover_offered_pairs(case: str) -> None:
    old = _ke("red")
    new = _ke("blue")
    valid = _decision(old, new, "no_match")
    if case == "missing":
        output = LifecycleMatchOutput(matches=())
    elif case == "duplicate":
        output = LifecycleMatchOutput.model_construct(matches=(valid, valid))
    else:
        output = LifecycleMatchOutput(
            matches=(
                LifecycleMatchDecision(
                    old_ke_id="unoffered-old",
                    new_ke_id=new.id,
                    decision="no_match",
                    confidence=0.5,
                    reason="fabricated pair",
                ),
            )
        )

    with pytest.raises(LifecycleInvariantError, match="missing|duplicate|unoffered"):
        await LifecycleMaintainer(FakeMatcher(output), run_id="lifecycle-run").apply(
            (old,),
            (new,),
        )


@pytest.mark.asyncio
async def test_one_new_ke_cannot_update_more_than_one_old_target() -> None:
    old_red = _ke("red")
    old_green = _ke("green")
    new = _ke("blue")
    matcher = FakeMatcher(
        LifecycleMatchOutput(
            matches=(
                _decision(old_red, new, "updates"),
                _decision(old_green, new, "updates"),
            )
        )
    )

    with pytest.raises(LifecycleInvariantError, match="more than one update"):
        await LifecycleMaintainer(matcher, run_id="lifecycle-run").apply(
            (old_red, old_green),
            (new,),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "new",
    [
        _ke("blue", subject="bob"),
        _ke("blue", operator="avoids"),
        _ke("blue", modality="goal"),
        _ke(
            "blue",
            valid_from=datetime(2025, 1, 1, tzinfo=UTC),
            valid_to=datetime(2025, 1, 2, tzinfo=UTC),
        ),
    ],
)
async def test_symbolic_candidate_generation_filters_nonmatching_pairs(
    new: KnowledgeEquation,
) -> None:
    old = _ke(
        "red",
        valid_from=(datetime(2024, 1, 1, tzinfo=UTC) if new.temporal.valid_from else None),
        valid_to=(datetime(2024, 1, 2, tzinfo=UTC) if new.temporal.valid_to else None),
    )
    matcher = FakeMatcher(LifecycleMatchOutput(matches=()))

    result = await LifecycleMaintainer(matcher, run_id="lifecycle-run").apply(
        (old,),
        (new,),
    )

    assert matcher.calls == []
    assert result.decisions == ()
    assert result.appended_revisions == (new,)


def test_explicit_retraction_is_allowed_only_for_updates() -> None:
    with pytest.raises(ValidationError, match="explicit_retraction"):
        LifecycleMatchDecision(
            old_ke_id="old",
            new_ke_id="new",
            decision="contradicts",
            confidence=0.5,
            reason="invalid",
            explicit_retraction=True,
        )
