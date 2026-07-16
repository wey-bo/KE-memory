from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import hashlib
import json
from typing import Any, TypeVar, cast

import pytest
from pydantic import BaseModel, ValidationError

from ke_memory_demo.aggregation import (
    EMPTY_SESSION_SUMMARY,
    AggregationInvariantError,
    SessionAggregationOutput,
    SessionAggregator,
    SessionItemKind,
    SessionItemProposal,
    SessionKEProposal,
    SessionMemory,
    validate_session_memory,
)
from ke_memory_demo.domain import (
    AssertionRef,
    ConceptRef,
    CoverageEntry,
    CoverageStatus,
    Exchange,
    Expression,
    IndividualRef,
    KnowledgeEquation,
    Message,
    MessageRole,
    MessageSpan,
    Modality,
    OntologyBinding,
    OntologyBindingStatus,
    OntologyRole,
    OperatorApplication,
    OperatorRef,
    Polarity,
    Session,
    TemporalMetadata,
    ToolEvent,
    ToolEventKind,
)
from ke_memory_demo.infra.telemetry import TraceContext


ModelT = TypeVar("ModelT", bound=BaseModel)


class FakeSessionModel:
    def __init__(self, output: object) -> None:
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
        return cast(ModelT, self.output)


def _message(
    message_id: str,
    role: MessageRole,
    content: str,
    source_order: int,
) -> Message:
    return Message(id=message_id, role=role, content=content, source_order=source_order)


def _session(
    session_id: str = "session-a",
    *,
    user_text: str = "Alice prefers tea. PRIVATE CONTEXT",
    assistant_text: str = "Preference recorded. UNRELATED RESPONSE",
) -> Session:
    return Session(
        id=session_id,
        conversation_id="conversation-1",
        exchanges=(
            Exchange(
                id=f"exchange-{session_id}",
                session_id=session_id,
                user=_message(f"user-{session_id}", MessageRole.USER, user_text, 0),
                events=(
                    ToolEvent(
                        id=f"tool-{session_id}",
                        kind=ToolEventKind.TOOL_RESULT,
                        content="TOOL EVENT MUST NEVER LEAK",
                        source_order=1,
                    ),
                ),
                assistant=_message(
                    f"assistant-{session_id}", MessageRole.ASSISTANT, assistant_text, 2
                ),
                global_ordinal=0,
            ),
        ),
    )


def _span(message: Message, start: int, end: int) -> MessageSpan:
    return MessageSpan(
        message_id=message.id,
        start_char=start,
        end_char=end,
        text_hash=hashlib.sha256(message.content[start:end].encode()).hexdigest(),
    )


def _binding(term_id: str = "concept:tea", surface: str = "tea") -> OntologyBinding:
    return OntologyBinding(
        surface_form=surface,
        normalized_surface=surface.casefold(),
        status=OntologyBindingStatus.RESOLVED,
        document_id=term_id,
        canonical_term=surface.title(),
        role=OntologyRole.CONCEPT,
        source_type="concept",
    )


def _turn_ke(
    session: Session,
    *,
    evidence: Sequence[MessageSpan] | None = None,
    subject: str = "person:alice",
    value: str = "concept:tea",
    operator: str = "operator:prefers",
    temporal: TemporalMetadata | None = None,
    binding: OntologyBinding | None = None,
    run_id: str = "turn-run",
) -> KnowledgeEquation:
    user = session.exchanges[0].user
    spans = tuple(evidence) if evidence is not None else (_span(user, 0, 17),)
    return KnowledgeEquation.create(
        level="turn",
        lhs=IndividualRef(term_id=subject, label="Alice"),
        rhs=OperatorApplication(
            operator=OperatorRef(term_id=operator, label="prefers"),
            arguments=(ConceptRef(term_id=value, label="tea"),),
        ),
        gloss="Alice prefers tea.",
        modality="preference",
        polarity="positive",
        lifecycle="active",
        speaker="user",
        temporal=temporal,
        ontology_bindings=((binding or _binding(value)),),
        evidence_refs=spans,
        confidence=0.91,
        produced_in_run_id=run_id,
        produced_in_stage="turn-ke-extracted",
    )


def _coverage(session: Session, ke: KnowledgeEquation | None) -> tuple[CoverageEntry, ...]:
    user = session.exchanges[0].user
    assistant = session.exchanges[0].assistant
    user_end = len(user.content)
    entries: list[CoverageEntry] = []
    if ke is None:
        entries.append(
            CoverageEntry(
                message_id=user.id,
                start_char=0,
                end_char=user_end,
                status=CoverageStatus.NON_MEMORY,
            )
        )
    else:
        evidence_end = ke.evidence_refs[0].end_char
        entries.append(
            CoverageEntry(
                message_id=user.id,
                start_char=0,
                end_char=evidence_end,
                status=CoverageStatus.REPRESENTED,
                ke_ids=(ke.id,),
            )
        )
        if evidence_end < user_end:
            entries.append(
                CoverageEntry(
                    message_id=user.id,
                    start_char=evidence_end,
                    end_char=user_end,
                    status=CoverageStatus.CONTEXT_ONLY,
                )
            )
    if assistant.content:
        entries.append(
            CoverageEntry(
                message_id=assistant.id,
                start_char=0,
                end_char=len(assistant.content),
                status=CoverageStatus.CONTEXT_ONLY,
            )
        )
    return tuple(entries)


def _proposal(
    ke: KnowledgeEquation,
    *,
    key: str = "session-ke-1",
    lhs: Expression | None = None,
    rhs: Expression | None = None,
    derived_from: Sequence[str] | None = None,
) -> SessionKEProposal:
    return SessionKEProposal(
        key=key,
        lhs=lhs or ke.lhs,
        rhs=rhs or ke.rhs,
        gloss="Alice has a stable preference for tea.",
        modality=Modality.PREFERENCE,
        polarity=Polarity.POSITIVE,
        lifecycle="active",
        confidence=0.88,
        derived_from=tuple(derived_from) if derived_from is not None else (ke.id,),
    )


def _output(
    ke: KnowledgeEquation,
    *,
    proposals: Sequence[SessionKEProposal] | None = None,
    conflicts: Sequence[SessionItemProposal] = (),
    constraints: Sequence[SessionItemProposal] = (),
    questions: Sequence[SessionItemProposal] = (),
) -> SessionAggregationOutput:
    return SessionAggregationOutput(
        summary="Alice prefers tea.",
        proposals=tuple(proposals) if proposals is not None else (_proposal(ke),),
        unresolved_conflicts=tuple(conflicts),
        constraints=tuple(constraints),
        open_questions=tuple(questions),
    )


def _payload(model: FakeSessionModel) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(str(model.calls[0][1][1]["content"])))


@pytest.mark.asyncio
async def test_session_model_receives_only_exact_validated_evidence_snippets() -> None:
    session = _session()
    turn_ke = _turn_ke(session)
    model = FakeSessionModel(_output(turn_ke))

    result = await SessionAggregator(
        model, (turn_ke,), _coverage(session, turn_ke), run_id="session-run"
    ).aggregate(session)

    payload = _payload(model)
    assert payload["session_id"] == session.id
    assert payload["evidence_snippets"] == [
        {
            "message_id": turn_ke.evidence_refs[0].message_id,
            "start_char": 0,
            "end_char": 17,
            "text_hash": turn_ke.evidence_refs[0].text_hash,
            "text": "Alice prefers tea",
        }
    ]
    serialized = str(model.calls[0][1])
    assert "PRIVATE CONTEXT" not in serialized
    assert "UNRELATED RESPONSE" not in serialized
    assert "TOOL EVENT MUST NEVER LEAK" not in serialized
    assert "source_metadata" not in serialized
    assert model.calls[0][0] is SessionAggregationOutput
    assert model.calls[0][2] == TraceContext(
        operation="session-memory-aggregate",
        metadata={"run_id": "session-run", "session_id": session.id},
    )
    assert result.session_id == session.id
    assert result.source_turn_ke_ids == (turn_ke.id,)


@pytest.mark.asyncio
async def test_session_aggregation_rejects_cross_session_evidence_mixing_before_model_call() -> (
    None
):
    first = _session("session-a")
    second = _session("session-b")
    mixed = _turn_ke(
        first,
        evidence=(
            _span(first.exchanges[0].user, 0, 5),
            _span(second.exchanges[0].user, 0, 5),
        ),
    )
    model = FakeSessionModel(_output(mixed))

    with pytest.raises(AggregationInvariantError, match="mixes session"):
        await SessionAggregator(
            model, (mixed,), _coverage(first, mixed), run_id="session-run"
        ).aggregate(first)

    assert model.calls == []


@pytest.mark.asyncio
async def test_session_aggregation_revalidates_span_hash_before_model_call() -> None:
    session = _session()
    turn_ke = _turn_ke(session)
    forged_span = turn_ke.evidence_refs[0].model_copy(update={"text_hash": "f" * 64})
    forged = turn_ke.model_copy(update={"evidence_refs": (forged_span,)})
    model = FakeSessionModel(_output(turn_ke))

    with pytest.raises(AggregationInvariantError, match="text_hash"):
        await SessionAggregator(
            model, (forged,), _coverage(session, turn_ke), run_id="session-run"
        ).aggregate(session)

    assert model.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["gap", "unknown_reference", "extraction_failed"])
async def test_session_aggregation_revalidates_exact_final_coverage(case: str) -> None:
    session = _session()
    turn_ke = _turn_ke(session)
    coverage = list(_coverage(session, turn_ke))
    if case == "gap":
        coverage[0] = coverage[0].model_copy(update={"end_char": 16})
    elif case == "unknown_reference":
        coverage[0] = coverage[0].model_copy(update={"ke_ids": ("ke:missing",)})
    else:
        coverage[0] = coverage[0].model_copy(
            update={"status": CoverageStatus.EXTRACTION_FAILED, "ke_ids": ()}
        )
    model = FakeSessionModel(_output(turn_ke))

    with pytest.raises(AggregationInvariantError):
        await SessionAggregator(model, (turn_ke,), tuple(coverage), run_id="session-run").aggregate(
            session
        )

    assert model.calls == []


@pytest.mark.asyncio
async def test_session_aggregation_filters_unrelated_coverage_and_rejects_unrepresented_ke() -> (
    None
):
    session = _session()
    other_session = _session("session-other")
    turn_ke = _turn_ke(session)
    other_ke = _turn_ke(other_session)
    model = FakeSessionModel(_output(turn_ke))
    unrelated = (*_coverage(session, turn_ke), *_coverage(other_session, other_ke))

    await SessionAggregator(model, (turn_ke,), unrelated, run_id="session-run").aggregate(session)

    payload = _payload(model)
    assert {entry["message_id"] for entry in payload["coverage_summaries"]} == {
        session.exchanges[0].user.id,
        session.exchanges[0].assistant.id,
    }
    assert other_session.exchanges[0].user.id not in str(model.calls[0][1])
    model.calls.clear()

    coverage = tuple(
        entry.model_copy(update={"status": CoverageStatus.CONTEXT_ONLY, "ke_ids": ()})
        if entry.status is CoverageStatus.REPRESENTED
        else entry
        for entry in _coverage(session, turn_ke)
    )
    with pytest.raises(AggregationInvariantError, match="not represented by final coverage"):
        await SessionAggregator(model, (turn_ke,), coverage, run_id="session-run").aggregate(
            session
        )
    assert model.calls == []


@pytest.mark.asyncio
async def test_empty_session_memory_is_deterministic_and_skips_model() -> None:
    session = _session(user_text="nothing", assistant_text="")
    model = FakeSessionModel(object())

    result = await SessionAggregator(
        model, (), _coverage(session, None), run_id="session-run"
    ).aggregate(session)

    assert result == SessionMemory(
        session_id=session.id,
        summary=EMPTY_SESSION_SUMMARY,
        knowledge_equations=(),
        unresolved_conflicts=(),
        constraints=(),
        open_questions=(),
        source_turn_ke_ids=(),
        evidence_closure=(),
    )
    assert result.summary == "No memory-bearing information."
    assert model.calls == []


@pytest.mark.asyncio
async def test_empty_session_rejects_represented_coverage_and_unselected_foreign_references() -> (
    None
):
    session = _session(user_text="nothing", assistant_text="")
    model = FakeSessionModel(object())
    coverage = (
        CoverageEntry(
            message_id=session.exchanges[0].user.id,
            start_char=0,
            end_char=len(session.exchanges[0].user.content),
            status=CoverageStatus.REPRESENTED,
            ke_ids=("ke:missing",),
        ),
    )
    with pytest.raises(AggregationInvariantError, match="unknown reference"):
        await SessionAggregator(model, (), coverage, run_id="session-run").aggregate(session)
    assert model.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("invented", ["term", "assertion", "lower_ref"])
async def test_session_proposals_cannot_invent_terms_assertions_or_lower_refs(
    invented: str,
) -> None:
    session = _session()
    turn_ke = _turn_ke(session)
    lhs: object = turn_ke.lhs
    rhs: object = turn_ke.rhs
    derived_from: Sequence[str] = (turn_ke.id,)
    if invented == "term":
        lhs = IndividualRef(term_id="person:mallory", label="Mallory")
    elif invented == "assertion":
        rhs = AssertionRef(assertion_id="ke:not-cited")
    else:
        derived_from = ("ke:missing",)
    proposal = _proposal(turn_ke, lhs=lhs, rhs=rhs, derived_from=derived_from)
    model = FakeSessionModel(_output(turn_ke, proposals=(proposal,)))

    with pytest.raises(AggregationInvariantError, match="(term|AssertionRef|lower)"):
        await SessionAggregator(
            model, (turn_ke,), _coverage(session, turn_ke), run_id="session-run"
        ).aggregate(session)


@pytest.mark.asyncio
async def test_session_proposal_cannot_retype_a_cited_term_id_as_an_operator() -> None:
    session = _session()
    turn_ke = _turn_ke(session)
    proposal = _proposal(
        turn_ke,
        rhs=OperatorRef(term_id="concept:tea", label="tea-as-operator"),
    )
    model = FakeSessionModel(_output(turn_ke, proposals=(proposal,)))

    with pytest.raises(AggregationInvariantError, match="term or operator role"):
        await SessionAggregator(
            model, (turn_ke,), _coverage(session, turn_ke), run_id="session-run"
        ).aggregate(session)


@pytest.mark.asyncio
async def test_session_assertion_gets_exact_evidence_binding_and_open_temporal_envelope() -> None:
    session = _session()
    start = datetime(2026, 1, 3, tzinfo=UTC)
    point = datetime(2026, 1, 5, tzinfo=UTC)
    first = _turn_ke(
        session,
        temporal=TemporalMetadata(valid_from=start),
        run_id="turn-run-1",
    )
    second_span = _span(session.exchanges[0].assistant, 0, 10)
    second = _turn_ke(
        session,
        evidence=(second_span,),
        temporal=TemporalMetadata(event_time=point),
        run_id="turn-run-2",
    )
    proposal = _proposal(first, derived_from=(second.id, first.id))
    model = FakeSessionModel(_output(first, proposals=(proposal,)))
    coverage = (
        CoverageEntry(
            message_id=session.exchanges[0].user.id,
            start_char=0,
            end_char=len(session.exchanges[0].user.content),
            status=CoverageStatus.REPRESENTED,
            ke_ids=(first.id,),
        ),
        CoverageEntry(
            message_id=session.exchanges[0].assistant.id,
            start_char=0,
            end_char=10,
            status=CoverageStatus.REPRESENTED,
            ke_ids=(second.id,),
        ),
        CoverageEntry(
            message_id=session.exchanges[0].assistant.id,
            start_char=10,
            end_char=len(session.exchanges[0].assistant.content),
            status=CoverageStatus.CONTEXT_ONLY,
        ),
    )

    result = await SessionAggregator(
        model, (second, first), coverage, run_id="session-run"
    ).aggregate(session)

    equation = result.knowledge_equations[0]
    assert equation.level.value == "session"
    assert equation.speaker.value == "derived"
    assert equation.lifecycle.value == "active"
    assert equation.produced_in_stage == "session-aggregated"
    assert equation.derived_from == tuple(sorted((first.id, second.id)))
    assert equation.evidence_refs == tuple(
        sorted((first.evidence_refs[0], second_span), key=_span_key)
    )
    assert equation.ontology_bindings == first.ontology_bindings
    assert equation.temporal == TemporalMetadata(valid_from=start, valid_to=None)
    validate_session_memory(result, {first.id: first, second.id: second})


@pytest.mark.asyncio
async def test_session_notes_require_lower_refs_and_contribute_exact_evidence_closure() -> None:
    session = _session()
    turn_ke = _turn_ke(session)
    conflict = SessionItemProposal(
        key="conflict-1",
        kind=SessionItemKind.UNRESOLVED_CONFLICT,
        text="The preference may conflict with a prior choice.",
        derived_from=(turn_ke.id,),
    )
    constraint = SessionItemProposal(
        key="constraint-1",
        kind=SessionItemKind.CONSTRAINT,
        text="Use tea.",
        derived_from=(turn_ke.id,),
    )
    question = SessionItemProposal(
        key="question-1",
        kind=SessionItemKind.OPEN_QUESTION,
        text="Which tea?",
        derived_from=(turn_ke.id,),
    )
    model = FakeSessionModel(
        _output(
            turn_ke,
            conflicts=(conflict,),
            constraints=(constraint,),
            questions=(question,),
        )
    )

    result = await SessionAggregator(
        model, (turn_ke,), _coverage(session, turn_ke), run_id="session-run"
    ).aggregate(session)

    assert result.unresolved_conflicts[0].evidence_refs == turn_ke.evidence_refs
    assert result.constraints[0].evidence_refs == turn_ke.evidence_refs
    assert result.open_questions[0].evidence_refs == turn_ke.evidence_refs
    assert result.evidence_closure == turn_ke.evidence_refs
    assert result.source_turn_ke_ids == (turn_ke.id,)

    bad_item = conflict.model_copy(update={"derived_from": ()})
    bad_output = SessionAggregationOutput.model_construct(
        summary="bad",
        proposals=(_proposal(turn_ke),),
        unresolved_conflicts=(bad_item,),
        constraints=(),
        open_questions=(),
    )
    bad_model = FakeSessionModel(bad_output)
    with pytest.raises(AggregationInvariantError, match="validated"):
        await SessionAggregator(
            bad_model, (turn_ke,), _coverage(session, turn_ke), run_id="session-run"
        ).aggregate(session)


@pytest.mark.asyncio
async def test_duplicate_session_logical_ids_or_revisions_are_rejected() -> None:
    session = _session()
    turn_ke = _turn_ke(session)
    first = _proposal(turn_ke, key="one")
    second = _proposal(turn_ke, key="two")
    model = FakeSessionModel(_output(turn_ke, proposals=(first, second)))

    with pytest.raises(AggregationInvariantError, match="duplicate.*(ID|revision)"):
        await SessionAggregator(
            model, (turn_ke,), _coverage(session, turn_ke), run_id="session-run"
        ).aggregate(session)


@pytest.mark.asyncio
async def test_session_inputs_are_not_mutated_and_output_order_is_deterministic() -> None:
    session = _session()
    first = _turn_ke(session, value="concept:tea", run_id="one")
    second = _turn_ke(
        session,
        subject="person:alice",
        value="concept:coffee",
        binding=_binding("concept:coffee", "coffee"),
        run_id="two",
    )
    before = (first.model_dump(), second.model_dump())
    output = _output(
        first,
        proposals=(
            _proposal(second, key="z", derived_from=(second.id,)),
            _proposal(first, key="a", derived_from=(first.id,)),
        ),
    )
    model = FakeSessionModel(output)
    coverage = list(_coverage(session, first))
    coverage[0] = coverage[0].model_copy(update={"ke_ids": (first.id, second.id)})

    result = await SessionAggregator(
        model, (second, first), tuple(coverage), run_id="session-run"
    ).aggregate(session)

    assert tuple(item.id for item in result.knowledge_equations) == tuple(
        sorted(item.id for item in result.knowledge_equations)
    )
    assert result.source_turn_ke_ids == tuple(sorted((first.id, second.id)))
    assert (first.model_dump(), second.model_dump()) == before


def test_session_records_are_frozen_tuple_backed_and_reject_extra_or_temporal_proposals() -> None:
    session = _session()
    turn_ke = _turn_ke(session)
    proposal = _proposal(turn_ke)
    assert isinstance(proposal.derived_from, tuple)

    with pytest.raises(ValidationError, match="extra_forbidden"):
        SessionKEProposal.model_validate(
            {
                **proposal.model_dump(mode="python"),
                "temporal": {"event_time": "2026-01-01T00:00:00Z"},
            }
        )
    with pytest.raises(ValidationError):
        proposal.gloss = "changed"


@pytest.mark.asyncio
async def test_validate_session_memory_reauthenticates_top_level_and_source_turn_kes() -> None:
    session = _session()
    first = _turn_ke(session, value="concept:tea", run_id="one")
    second = _turn_ke(
        session,
        value="concept:coffee",
        binding=_binding("concept:coffee", "coffee"),
        run_id="two",
    )
    output = _output(
        first,
        proposals=(
            _proposal(first, key="one"),
            _proposal(second, key="two", derived_from=(second.id,)),
        ),
    )
    coverage = list(_coverage(session, first))
    coverage[0] = coverage[0].model_copy(update={"ke_ids": (first.id, second.id)})
    memory = await SessionAggregator(
        FakeSessionModel(output),
        (first, second),
        coverage,
        run_id="session-run",
    ).aggregate(session)

    unsorted = memory.model_copy(
        update={"source_turn_ke_ids": tuple(reversed(memory.source_turn_ke_ids))}
    )
    with pytest.raises(AggregationInvariantError, match="validated SessionMemory"):
        validate_session_memory(unsorted, {first.id: first, second.id: second})

    forged = first.model_copy(update={"revision": "0" * 64})
    with pytest.raises(AggregationInvariantError, match="source Turn KE.*revision"):
        validate_session_memory(memory, {forged.id: forged, second.id: second})


@pytest.mark.asyncio
async def test_validate_session_memory_requires_exact_selected_source_ids() -> None:
    session = _session()
    first = _turn_ke(session, value="concept:tea", run_id="one")
    second = _turn_ke(
        session,
        value="concept:coffee",
        binding=_binding("concept:coffee", "coffee"),
        run_id="two",
    )
    coverage = list(_coverage(session, first))
    coverage[0] = coverage[0].model_copy(update={"ke_ids": (first.id, second.id)})
    memory = await SessionAggregator(
        FakeSessionModel(_output(first, proposals=(_proposal(first),))),
        (first, second),
        coverage,
        run_id="session-run",
    ).aggregate(session)
    omitted = memory.model_copy(update={"source_turn_ke_ids": (first.id,)})

    with pytest.raises(AggregationInvariantError, match="source Turn-KE IDs.*exact"):
        validate_session_memory(omitted, {first.id: first, second.id: second})


@pytest.mark.asyncio
async def test_validate_session_memory_rejects_authentic_unsorted_assertion_lower_refs() -> None:
    session = _session()
    first = _turn_ke(session, value="concept:tea", run_id="one")
    second = _turn_ke(
        session,
        value="concept:coffee",
        binding=_binding("concept:coffee", "coffee"),
        run_id="two",
    )
    coverage = list(_coverage(session, first))
    coverage[0] = coverage[0].model_copy(update={"ke_ids": (first.id, second.id)})
    memory = await SessionAggregator(
        FakeSessionModel(
            _output(first, proposals=(_proposal(first, derived_from=(first.id, second.id)),))
        ),
        (first, second),
        coverage,
        run_id="session-run",
    ).aggregate(session)
    assertion = memory.knowledge_equations[0]
    reversed_refs = tuple(reversed(assertion.derived_from))
    assert reversed_refs != assertion.derived_from
    reordered = KnowledgeEquation.create(
        level=assertion.level,
        lhs=assertion.lhs,
        rhs=assertion.rhs,
        gloss=assertion.gloss,
        modality=assertion.modality,
        polarity=assertion.polarity,
        lifecycle=assertion.lifecycle,
        speaker=assertion.speaker,
        temporal=assertion.temporal,
        ontology_bindings=assertion.ontology_bindings,
        evidence_refs=assertion.evidence_refs,
        derived_from=reversed_refs,
        confidence=assertion.confidence,
        produced_in_run_id=assertion.produced_in_run_id,
        produced_in_stage=assertion.produced_in_stage,
    )
    tampered = memory.model_copy(update={"knowledge_equations": (reordered,)})

    with pytest.raises(AggregationInvariantError, match="lower refs must be sorted"):
        validate_session_memory(tampered, {first.id: first, second.id: second})


def _span_key(span: MessageSpan) -> tuple[str, int, int, str]:
    return (span.message_id, span.start_char, span.end_char, span.text_hash)
