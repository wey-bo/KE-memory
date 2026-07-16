from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import json
from typing import Literal, TypeVar, cast

import pytest
from pydantic import BaseModel, ValidationError

from ke_memory_demo.domain import (
    AssertionRef,
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
    event_time: datetime | None = None,
    mentioned_at: datetime | None = None,
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
        temporal=TemporalMetadata(
            valid_from=valid_from,
            valid_to=valid_to,
            event_time=event_time,
            mentioned_at=mentioned_at,
        ),
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


def _revision(
    equation: KnowledgeEquation,
    *,
    lifecycle: str | None = None,
    gloss: str | None = None,
    run_id: str = "revision-run",
) -> KnowledgeEquation:
    return KnowledgeEquation.create(
        level=equation.level,
        lhs=equation.lhs,
        rhs=equation.rhs,
        gloss=gloss or equation.gloss,
        modality=equation.modality,
        polarity=equation.polarity,
        lifecycle=lifecycle or equation.lifecycle,
        speaker=equation.speaker,
        temporal=equation.temporal,
        ontology_bindings=equation.ontology_bindings,
        evidence_refs=equation.evidence_refs,
        derived_from=equation.derived_from,
        contradicts=equation.contradicts,
        supersedes=equation.supersedes,
        confidence=equation.confidence,
        produced_in_run_id=run_id,
        produced_in_stage="lifecycle-maintained",
    )


def _operator_free_ke(
    kind: Literal["concept", "individual", "assertion"],
    value: str,
    *,
    subject: str = "shared-subject",
) -> KnowledgeEquation:
    if kind == "concept":
        lhs = ConceptRef(term_id=subject, label=subject)
        rhs = ConceptRef(term_id=value, label=value)
    elif kind == "individual":
        lhs = IndividualRef(term_id=subject, label=subject)
        rhs = IndividualRef(term_id=value, label=value)
    else:
        lhs = AssertionRef(assertion_id=subject)
        rhs = AssertionRef(assertion_id=value)
    return KnowledgeEquation.create(
        level="turn",
        lhs=lhs,
        rhs=rhs,
        gloss=f"{subject} equals {value}",
        modality="fact",
        polarity="positive",
        lifecycle="active",
        speaker="user",
        evidence_refs=(
            MessageSpan(
                message_id=f"operator-free-{kind}-{value}",
                start_char=0,
                end_char=1,
                text_hash="1" * 64,
            ),
        ),
        confidence=0.8,
        produced_in_run_id="source-run",
        produced_in_stage="turn-ke-extracted",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["concept", "individual", "assertion"])
async def test_operator_free_atomic_equations_use_total_symbolic_identity(
    kind: Literal["concept", "individual", "assertion"],
) -> None:
    old = _operator_free_ke(kind, "old-value")
    new = _operator_free_ke(kind, "new-value")
    matcher = FakeMatcher(LifecycleMatchOutput(matches=(_decision(old, new, "no_match"),)))

    result = await LifecycleMaintainer(matcher, run_id="lifecycle-run").apply(
        (old,),
        (new,),
    )

    payload = json.loads(str(matcher.calls[0][1][1]["content"]))
    assert payload["offered_pairs"][0]["operator_identity"] == "__equation__"
    assert result.appended_revisions == (new,)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["concept", "individual", "assertion"])
async def test_operator_free_equations_with_different_subjects_do_not_match(
    kind: Literal["concept", "individual", "assertion"],
) -> None:
    old = _operator_free_ke(kind, "old-value", subject="first-subject")
    new = _operator_free_ke(kind, "new-value", subject="second-subject")
    matcher = FakeMatcher(LifecycleMatchOutput(matches=()))

    result = await LifecycleMaintainer(matcher, run_id="lifecycle-run").apply(
        (old,),
        (new,),
    )

    assert matcher.calls == []
    assert result.appended_revisions == (new,)


@pytest.mark.asyncio
async def test_explicit_operator_identity_remains_its_normalized_term_id() -> None:
    old = _ke("red", operator="  LIKES  ")
    new = _ke("blue", operator="  likes  ")
    matcher = FakeMatcher(LifecycleMatchOutput(matches=(_decision(old, new, "no_match"),)))

    await LifecycleMaintainer(matcher, run_id="lifecycle-run").apply(
        (old,),
        (new,),
    )

    payload = json.loads(str(matcher.calls[0][1][1]["content"]))
    assert payload["offered_pairs"][0]["operator_identity"] == "likes"


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["superseded", "retracted", "contradicted"])
async def test_terminal_current_records_are_never_offered_or_regressed(terminal: str) -> None:
    old = _ke("red", lifecycle=terminal)
    new = _ke("blue")
    matcher = FakeMatcher(LifecycleMatchOutput(matches=(_decision(old, new, "updates"),)))

    result = await LifecycleMaintainer(matcher, run_id="lifecycle-run").apply(
        (old,),
        (new,),
    )

    assert matcher.calls == []
    assert result.appended_revisions == (new,)
    current_by_id = {equation.id: equation for equation in result.current_records}
    assert current_by_id[old.id] == old
    assert current_by_id[old.id].lifecycle.value == terminal


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "offered"),
    [
        ("open_future", True),
        ("open_past", True),
        ("same_point", True),
        ("inclusive_boundary", True),
        ("different_points", False),
        ("disjoint_ranges", False),
    ],
)
async def test_temporal_candidate_boundaries(case: str, offered: bool) -> None:
    boundary = datetime(2025, 1, 2, tzinfo=UTC)
    if case == "open_future":
        old = _ke("red", valid_from=datetime(2025, 1, 1, tzinfo=UTC))
        new = _ke("blue", valid_from=datetime(2030, 1, 1, tzinfo=UTC))
    elif case == "open_past":
        old = _ke("red", valid_to=boundary)
        new = _ke("blue", valid_to=datetime(2024, 1, 1, tzinfo=UTC))
    elif case == "same_point":
        old = _ke("red", event_time=boundary)
        new = _ke("blue", mentioned_at=boundary)
    elif case == "inclusive_boundary":
        old = _ke("red", valid_to=boundary)
        new = _ke("blue", valid_from=boundary)
    elif case == "different_points":
        old = _ke("red", event_time=datetime(2025, 1, 1, tzinfo=UTC))
        new = _ke("blue", event_time=boundary)
    else:
        old = _ke(
            "red",
            valid_from=datetime(2024, 1, 1, tzinfo=UTC),
            valid_to=datetime(2024, 1, 2, tzinfo=UTC),
        )
        new = _ke(
            "blue",
            valid_from=datetime(2025, 1, 1, tzinfo=UTC),
            valid_to=boundary,
        )
    output = (
        LifecycleMatchOutput(matches=(_decision(old, new, "no_match"),))
        if offered
        else LifecycleMatchOutput(matches=())
    )
    matcher = FakeMatcher(output)

    result = await LifecycleMaintainer(matcher, run_id="lifecycle-run").apply(
        (old,),
        (new,),
    )

    assert bool(matcher.calls) is offered
    assert result.appended_revisions == (new,)


@pytest.mark.asyncio
async def test_combined_update_and_contradiction_preserve_links_order_and_inputs() -> None:
    updated_old = _ke("red")
    contradicted_old = _ke("green")
    new = _ke("blue", polarity="negative")
    before = tuple(item.model_dump_json() for item in (updated_old, contradicted_old, new))
    matcher = FakeMatcher(
        LifecycleMatchOutput(
            matches=(
                _decision(updated_old, new, "updates"),
                _decision(contradicted_old, new, "contradicts"),
            )
        )
    )

    result = await LifecycleMaintainer(matcher, run_id="lifecycle-run").apply(
        (updated_old, contradicted_old),
        (new,),
    )

    revised = {item.id: item for item in result.appended_revisions}
    assert revised[updated_old.id].lifecycle.value == "superseded"
    assert revised[contradicted_old.id].lifecycle == contradicted_old.lifecycle
    assert revised[contradicted_old.id].contradicts == (new.id,)
    assert revised[new.id].supersedes == (updated_old.id,)
    assert revised[new.id].contradicts == (contradicted_old.id,)
    assert tuple(item.id for item in result.appended_revisions) == (
        *sorted((updated_old.id, contradicted_old.id)),
        new.id,
    )
    assert tuple(item.id for item in result.current_records) == tuple(
        sorted((updated_old.id, contradicted_old.id, new.id))
    )
    assert all(
        item.produced_in_run_id == "lifecycle-run"
        and item.produced_in_stage == "lifecycle-maintained"
        for item in result.appended_revisions
    )
    assert tuple(item.model_dump_json() for item in (updated_old, contradicted_old, new)) == before
    assert tuple(KnowledgeEquation.model_validate_json(item) for item in before) == (
        updated_old,
        contradicted_old,
        new,
    )


@pytest.mark.asyncio
async def test_identical_logical_id_replay_is_a_complete_no_op() -> None:
    current = _ke("red")
    replay = KnowledgeEquation.model_validate_json(current.model_dump_json())
    assert replay == current
    assert replay is not current
    matcher = FakeMatcher(LifecycleMatchOutput(matches=()))

    result = await LifecycleMaintainer(matcher, run_id="lifecycle-run").apply(
        (current,),
        (replay,),
    )

    assert matcher.calls == []
    assert result.decisions == ()
    assert result.appended_revisions == ()
    assert result.current_records == (current,)


@pytest.mark.asyncio
async def test_conflicting_logical_id_revision_fails_before_matcher_call() -> None:
    current = _ke("red")
    collision = _revision(current, lifecycle="uncertain", gloss="conflicting replay")
    matcher = FakeMatcher(LifecycleMatchOutput(matches=()))

    with pytest.raises(LifecycleInvariantError, match="logical ID collision"):
        await LifecycleMaintainer(matcher, run_id="lifecycle-run").apply(
            (current,),
            (collision,),
        )

    assert matcher.calls == []
    assert current.lifecycle.value == "active"
    assert collision.lifecycle.value == "uncertain"


@pytest.mark.asyncio
async def test_replay_of_historical_but_not_current_revision_is_a_collision() -> None:
    historical = _ke("red")
    current = _revision(historical, lifecycle="uncertain")
    matcher = FakeMatcher(LifecycleMatchOutput(matches=()))

    with pytest.raises(LifecycleInvariantError, match="logical ID collision"):
        await LifecycleMaintainer(matcher, run_id="lifecycle-run").apply(
            (historical, current),
            (historical,),
        )

    assert matcher.calls == []
    assert historical.revision != current.revision


@pytest.mark.asyncio
async def test_replayed_old_record_can_be_transitioned_once_by_another_new_ke() -> None:
    old = _ke("red")
    replacement = _ke("blue")
    matcher = FakeMatcher(LifecycleMatchOutput(matches=(_decision(old, replacement, "updates"),)))

    result = await LifecycleMaintainer(matcher, run_id="lifecycle-run").apply(
        (old,),
        (old, replacement),
    )

    appended_by_id = {equation.id: equation for equation in result.appended_revisions}
    assert len(appended_by_id) == len(result.appended_revisions) == 2
    assert appended_by_id[old.id].lifecycle.value == "superseded"
    assert appended_by_id[replacement.id].supersedes == (old.id,)
    assert {equation.id for equation in result.current_records} == {
        old.id,
        replacement.id,
    }


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
