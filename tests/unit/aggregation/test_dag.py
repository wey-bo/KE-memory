from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
import hashlib
import inspect
from typing import Any, Literal, TypeVar, cast

import pytest
from pydantic import BaseModel

from ke_memory_demo.aggregation import (
    AggregationInvariantError,
    AggregateAssertionProposal,
    AggregateCandidate,
    AggregateNodeProposal,
    AggregateSelectionOutput,
    SemanticDAG,
    SemanticDAGBuilder,
    SessionMemory,
    create_aggregate_node,
    generate_depth1_candidates,
    generate_depth2_candidates,
    validate_evidence_closure,
    validate_semantic_dag,
)
from ke_memory_demo.core.json import JsonValue, canonical_json
from ke_memory_demo.domain import (
    AggregateNode,
    AggregateNodeKind,
    AssertionRef,
    ConceptRef,
    Expression,
    IndividualRef,
    KnowledgeEquation,
    MessageSpan,
    Modality,
    OntologyBinding,
    OntologyBindingStatus,
    OntologyRole,
    OperatorApplication,
    OperatorRef,
    Polarity,
    TemporalMetadata,
    content_id,
)
from ke_memory_demo.infra.telemetry import TraceContext


ModelT = TypeVar("ModelT", bound=BaseModel)
_SOURCE_TURN_KES: dict[str, KnowledgeEquation] = {}


class FakeDAGModel:
    def __init__(self, outputs: Sequence[object]) -> None:
        self.outputs = list(outputs)
        self.calls: list[tuple[type[BaseModel], Sequence[Mapping[str, object]], TraceContext]] = []
        self.embedding_calls = 0

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
        return cast(ModelT, self.outputs.pop(0))

    async def embed(self, _texts: Sequence[str]) -> Sequence[Sequence[float]]:
        self.embedding_calls += 1
        raise AssertionError("embedding must never be called")


def _span(name: str) -> MessageSpan:
    text = f"evidence-{name}"
    return MessageSpan(
        message_id=f"message-{name}",
        start_char=0,
        end_char=len(text),
        text_hash=hashlib.sha256(text.encode()).hexdigest(),
    )


def _session_ke(
    name: str,
    *,
    subject: str = "person:alice",
    operator: str | None = "operator:works-on",
    value: str | None = None,
    derived_from: Sequence[str] | None = None,
    temporal: TemporalMetadata | None = None,
    bindings: Sequence[OntologyBinding] = (),
    lhs: Expression | None = None,
    rhs: Expression | None = None,
) -> KnowledgeEquation:
    target = value or f"project:{name}"
    evidence = (_span(name),)
    default_rhs = (
        OperatorApplication(
            operator=OperatorRef(term_id=operator, label=operator),
            arguments=(ConceptRef(term_id=target, label=target),),
        )
        if operator is not None
        else ConceptRef(term_id=target, label=target)
    )
    lhs_expression = lhs or IndividualRef(term_id=subject, label=subject)
    rhs_expression = rhs or default_rhs
    source = KnowledgeEquation.create(
        level="turn",
        lhs=lhs_expression,
        rhs=rhs_expression,
        gloss=f"{subject} {operator or 'equals'} {target}",
        modality="fact",
        polarity="positive",
        lifecycle="active",
        speaker="user",
        temporal=temporal,
        ontology_bindings=tuple(bindings),
        evidence_refs=evidence,
        confidence=0.9,
        produced_in_run_id="turn-run",
        produced_in_stage="turn-ke-extracted",
    )
    _SOURCE_TURN_KES[source.id] = source
    session_temporal = TemporalMetadata()
    if temporal is not None:
        if temporal.valid_from is not None or temporal.valid_to is not None:
            session_temporal = TemporalMetadata(
                valid_from=temporal.valid_from,
                valid_to=temporal.valid_to,
            )
        elif (point := temporal.event_time or temporal.mentioned_at) is not None:
            session_temporal = TemporalMetadata(valid_from=point, valid_to=point)
    return KnowledgeEquation.create(
        level="session",
        lhs=lhs_expression,
        rhs=rhs_expression,
        gloss=f"{subject} {operator or 'equals'} {target}",
        modality="fact",
        polarity="positive",
        lifecycle="active",
        speaker="derived",
        temporal=session_temporal,
        ontology_bindings=tuple(sorted(bindings, key=canonical_json)),
        evidence_refs=evidence,
        derived_from=tuple(derived_from) if derived_from is not None else (source.id,),
        confidence=0.9,
        produced_in_run_id="session-run",
        produced_in_stage="session-aggregated",
    )


def _memory(session_id: str, equations: Sequence[KnowledgeEquation]) -> SessionMemory:
    equations = tuple(sorted(equations, key=lambda item: item.id))
    source_ids = tuple(sorted({ref for item in equations for ref in item.derived_from}))
    evidence = _unique_spans(span for item in equations for span in item.evidence_refs)
    return SessionMemory(
        session_id=session_id,
        summary=f"Memory for {session_id}",
        knowledge_equations=equations,
        unresolved_conflicts=(),
        constraints=(),
        open_questions=(),
        source_turn_ke_ids=source_ids,
        evidence_closure=evidence,
    )


def _assertion_proposal(
    lower: Sequence[KnowledgeEquation],
    *,
    key: str = "assertion-1",
    derived_from: Sequence[str] | None = None,
    lhs: Expression | None = None,
    rhs: Expression | None = None,
) -> AggregateAssertionProposal:
    source = lower[0]
    return AggregateAssertionProposal(
        key=key,
        lhs=lhs or source.lhs,
        rhs=rhs or source.rhs,
        gloss="Cross-session aggregate.",
        modality=Modality.FACT,
        polarity=Polarity.POSITIVE,
        lifecycle="active",
        confidence=0.86,
        derived_from=(
            tuple(derived_from) if derived_from is not None else tuple(item.id for item in lower)
        ),
    )


def _node_proposal(
    candidate_id: str,
    members: Sequence[str],
    lower: Sequence[KnowledgeEquation],
    *,
    depth: Literal[1, 2] = 1,
    kind: AggregateNodeKind = AggregateNodeKind.PROJECT,
) -> AggregateNodeProposal:
    return AggregateNodeProposal(
        candidate_id=candidate_id,
        depth=depth,
        member_refs=tuple(members),
        node_kind=kind,
        title="Shared project",
        summary="The sessions concern the same project.",
        confidence=0.84,
        assertions=(_assertion_proposal(lower),),
    )


def _aggregate_assertion(
    lower: Sequence[KnowledgeEquation],
    *,
    derived_from: Sequence[str] | None = None,
    run_id: str = "dag-run",
    lhs: Expression | None = None,
    rhs: Expression | None = None,
    ontology_bindings: Sequence[OntologyBinding] = (),
) -> KnowledgeEquation:
    refs = tuple(derived_from) if derived_from is not None else tuple(item.id for item in lower)
    evidence = _unique_spans(
        span for item in lower if item.id in refs for span in item.evidence_refs
    )
    cited = tuple(item for item in lower if item.id in refs)
    intervals: list[tuple[datetime | None, datetime | None]] = []
    for item in cited:
        if item.temporal.valid_from is not None or item.temporal.valid_to is not None:
            intervals.append((item.temporal.valid_from, item.temporal.valid_to))
        elif (point := item.temporal.event_time or item.temporal.mentioned_at) is not None:
            intervals.append((point, point))
    temporal = TemporalMetadata()
    if intervals:
        temporal = TemporalMetadata(
            valid_from=(
                None
                if any(lower_bound is None for lower_bound, _ in intervals)
                else min(cast(datetime, lower_bound) for lower_bound, _ in intervals)
            ),
            valid_to=(
                None
                if any(upper_bound is None for _, upper_bound in intervals)
                else max(cast(datetime, upper_bound) for _, upper_bound in intervals)
            ),
        )
    return KnowledgeEquation.create(
        level="aggregate",
        lhs=lhs or lower[0].lhs,
        rhs=rhs or lower[0].rhs,
        gloss="Aggregate assertion",
        modality="fact",
        polarity="positive",
        lifecycle="active",
        speaker="derived",
        temporal=temporal,
        ontology_bindings=ontology_bindings,
        evidence_refs=evidence,
        derived_from=tuple(sorted(refs)),
        confidence=0.8,
        produced_in_run_id=run_id,
        produced_in_stage="semantic-dag-built",
    )


def _node(
    members: Sequence[KnowledgeEquation],
    *,
    title: str = "Node",
    assertion: KnowledgeEquation | None = None,
) -> AggregateNode:
    assertion = assertion or _aggregate_assertion(members)
    evidence = _unique_spans(span for item in members for span in item.evidence_refs)
    return create_aggregate_node(
        node_kind=AggregateNodeKind.PROJECT,
        title=title,
        summary="Summary",
        assertions=(assertion,),
        member_refs=tuple(item.id for item in members),
        derived_from=assertion.derived_from,
        evidence_closure=evidence,
        temporal_extent=TemporalMetadata(),
        confidence=0.8,
        depth=1,
    )


def test_depth1_candidates_are_symbolic_cross_session_overlapping_and_deterministic() -> None:
    one = _session_ke("one", subject="person:alice", operator="operator:works-on")
    two = _session_ke("two", subject="person:alice", operator="operator:likes")
    three = _session_ke("three", subject="person:bob", operator="operator:works-on")
    memories = (_memory("s2", (two,)), _memory("s1", (one,)), _memory("s3", (three,)))

    first = _depth1_candidates(memories)
    second = _depth1_candidates(tuple(reversed(memories)))

    assert first == second
    member_sets = {candidate.member_refs for candidate in first}
    assert tuple(sorted((one.id, two.id))) in member_sets
    assert tuple(sorted((one.id, three.id))) in member_sets
    assert any(one.id in item.member_refs and two.id in item.member_refs for item in first)
    assert any(one.id in item.member_refs and three.id in item.member_refs for item in first)
    assert tuple(item.id for item in first) == tuple(sorted(item.id for item in first))
    assert all(item.id.startswith("candidate:") for item in first)
    assert all(item.depth == 1 for item in first)


def test_depth1_candidates_require_at_least_two_sessions() -> None:
    first = _session_ke("one")
    second = _session_ke("two")

    assert _depth1_candidates((_memory("same-session", (first, second)),)) == ()


def test_operator_free_equations_share_equation_symbol_and_temporal_adjacent_pairs_overlap() -> (
    None
):
    base = datetime(2026, 1, 1, tzinfo=UTC)
    equations = tuple(
        _session_ke(
            str(index),
            operator=None,
            temporal=TemporalMetadata(event_time=base + timedelta(days=index)),
        )
        for index in range(3)
    )
    memories = tuple(_memory(f"s{index}", (equation,)) for index, equation in enumerate(equations))

    candidates = _depth1_candidates(memories)

    all_members = tuple(sorted(item.id for item in equations))
    assert any(
        item.member_refs == all_members and "shared_operator" in item.reasons for item in candidates
    )
    adjacent = {
        item.member_refs
        for item in candidates
        if "temporal_adjacency" in item.reasons and len(item.member_refs) == 2
    }
    assert adjacent == {
        tuple(sorted((equations[0].id, equations[1].id))),
        tuple(sorted((equations[1].id, equations[2].id))),
    }


def test_temporal_adjacency_is_global_before_symbolic_filtering() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    first = _session_ke(
        "first",
        subject="person:alice",
        operator="operator:works-on",
        temporal=TemporalMetadata(event_time=base),
    )
    unrelated_middle = _session_ke(
        "middle",
        subject="person:bob",
        operator="operator:likes",
        temporal=TemporalMetadata(event_time=base + timedelta(days=1)),
    )
    last = _session_ke(
        "last",
        subject="person:alice",
        operator="operator:works-on",
        temporal=TemporalMetadata(event_time=base + timedelta(days=2)),
    )

    memories = (
        _memory("s1", (first,)),
        _memory("s2", (unrelated_middle,)),
        _memory("s3", (last,)),
    )
    candidates = _depth1_candidates(memories)

    shared_pair = tuple(sorted((first.id, last.id)))
    matching = [item for item in candidates if item.member_refs == shared_pair]
    assert matching
    assert "temporal_adjacency" not in matching[0].reasons


def test_depth1_candidates_share_nested_operators_only_when_the_inner_id_matches() -> None:
    one = _session_ke(
        "nested-one",
        lhs=IndividualRef(term_id="person:one", label="One"),
        rhs=_nested_operator_expression("operator:outer-one", "operator:shared-inner"),
    )
    two = _session_ke(
        "nested-two",
        lhs=IndividualRef(term_id="person:two", label="Two"),
        rhs=_nested_operator_expression("operator:outer-two", "operator:shared-inner"),
    )
    nonmatching = _session_ke(
        "nested-three",
        lhs=IndividualRef(term_id="person:three", label="Three"),
        rhs=_nested_operator_expression("operator:outer-three", "operator:other-inner"),
    )
    memories = (
        _memory("nested-s1", (one,)),
        _memory("nested-s2", (two,)),
        _memory("nested-s3", (nonmatching,)),
    )

    candidates = _depth1_candidates(memories)

    matching_members = tuple(sorted((one.id, two.id)))
    assert any(
        candidate.member_refs == matching_members and "shared_operator" in candidate.reasons
        for candidate in candidates
    )
    assert not any(
        "shared_operator" in candidate.reasons
        and one.id in candidate.member_refs
        and nonmatching.id in candidate.member_refs
        for candidate in candidates
    )


def test_depth2_candidates_share_nested_assertion_operators_without_member_overlap() -> None:
    members = tuple(_session_ke(f"nested-depth2-{index}") for index in range(6))
    first_assertion = _aggregate_assertion(
        members[:2],
        lhs=IndividualRef(term_id="aggregate-subject:one", label="One"),
        rhs=_nested_operator_expression("operator:outer-one", "operator:shared-inner"),
    )
    second_assertion = _aggregate_assertion(
        members[2:4],
        lhs=IndividualRef(term_id="aggregate-subject:two", label="Two"),
        rhs=_nested_operator_expression("operator:outer-two", "operator:shared-inner"),
    )
    other_assertion = _aggregate_assertion(
        members[4:],
        lhs=IndividualRef(term_id="aggregate-subject:three", label="Three"),
        rhs=_nested_operator_expression("operator:outer-three", "operator:other-inner"),
    )
    first = _node(members[:2], title="Nested first", assertion=first_assertion)
    second = _node(members[2:4], title="Nested second", assertion=second_assertion)
    nonmatching = _node(members[4:], title="Nested other", assertion=other_assertion)

    candidates = generate_depth2_candidates((first, second, nonmatching))

    matching_members = tuple(sorted((first.id, second.id)))
    assert any(
        candidate.member_refs == matching_members and "shared_operator" in candidate.reasons
        for candidate in candidates
    )
    assert not any(
        "shared_operator" in candidate.reasons
        and first.id in candidate.member_refs
        and nonmatching.id in candidate.member_refs
        for candidate in candidates
    )


@pytest.mark.asyncio
async def test_empty_memory_and_no_cross_session_candidates_skip_model() -> None:
    empty = _memory("empty", ())
    isolated = _memory("one", (_session_ke("only"),))
    model = FakeDAGModel(())

    memories = (empty, isolated)
    assert await _builder(model, memories).build(memories) == SemanticDAG(nodes=())
    assert model.calls == []
    assert model.embedding_calls == 0


@pytest.mark.asyncio
async def test_builder_runs_one_or_two_structured_passes_and_never_embeddings() -> None:
    one = _session_ke("one")
    two = _session_ke("two")
    memories = (_memory("s1", (one,)), _memory("s2", (two,)))
    candidate = _depth1_candidates(memories)[0]
    accepted = _node_proposal(candidate.id, candidate.member_refs, (one, two))
    model = FakeDAGModel(
        (
            AggregateSelectionOutput(accepted=(accepted,)),
            AggregateSelectionOutput(accepted=()),
        )
    )

    dag = await _builder(model, memories).build(memories)

    assert len(model.calls) in (1, 2)
    assert len(model.calls) == 1 or model.calls[1][2].operation == "semantic-dag-depth-2"
    assert model.calls[0][2].operation == "semantic-dag-depth-1"
    assert all(call[0] is AggregateSelectionOutput for call in model.calls)
    assert model.embedding_calls == 0
    assert dag.max_depth == 1
    assert dag.nodes[0].member_refs == candidate.member_refs
    assert dag.nodes[0].depth == 1
    assert all(item.level.value == "aggregate" for item in dag.nodes[0].assertions)
    assert all(item.speaker.value == "derived" for item in dag.nodes[0].assertions)
    assert all(item.produced_in_stage == "semantic-dag-built" for item in dag.nodes[0].assertions)


@pytest.mark.asyncio
async def test_builder_executes_depth2_pass_with_node_members_only() -> None:
    shared = _session_ke("shared", subject="person:alice", operator="operator:works-on")
    subject_peer = _session_ke("subject-peer", subject="person:alice", operator="operator:likes")
    operator_peer = _session_ke("operator-peer", subject="person:bob", operator="operator:works-on")
    memories = (
        _memory("s1", (shared,)),
        _memory("s2", (subject_peer,)),
        _memory("s3", (operator_peer,)),
    )
    candidates = _depth1_candidates(memories)
    subject_candidate = next(
        item
        for item in candidates
        if item.member_refs == tuple(sorted((shared.id, subject_peer.id)))
    )
    operator_candidate = next(
        item
        for item in candidates
        if item.member_refs == tuple(sorted((shared.id, operator_peer.id)))
    )
    first_output = AggregateSelectionOutput(
        accepted=(
            _node_proposal(
                subject_candidate.id,
                subject_candidate.member_refs,
                (shared, subject_peer),
            ),
            _node_proposal(
                operator_candidate.id,
                operator_candidate.member_refs,
                (shared, operator_peer),
            ),
        )
    )
    first_model = FakeDAGModel((first_output, AggregateSelectionOutput(accepted=())))
    depth1_only = await _builder(first_model, memories).build(memories)
    depth1_nodes = tuple(item for item in depth1_only.nodes if item.depth == 1)
    depth2_candidate = generate_depth2_candidates(depth1_nodes)[0]
    lower_assertions = tuple(node.assertions[0] for node in depth1_nodes)
    depth2_proposal = AggregateNodeProposal(
        candidate_id=depth2_candidate.id,
        depth=2,
        member_refs=depth2_candidate.member_refs,
        node_kind=AggregateNodeKind.TOPIC,
        title="Related work",
        summary="Two overlapping project aggregates.",
        confidence=0.8,
        assertions=(
            _assertion_proposal(
                lower_assertions,
                derived_from=tuple(node.id for node in depth1_nodes),
            ),
        ),
    )
    model = FakeDAGModel(
        (
            first_output,
            AggregateSelectionOutput(accepted=(depth2_proposal,)),
        )
    )

    dag = await _builder(model, memories).build(memories)

    assert len(model.calls) == 2
    assert dag.max_depth == 2
    higher = dag.nodes[-1]
    assert higher.depth == 2
    assert set(higher.member_refs) == {node.id for node in dag.nodes if node.depth == 1}
    assert all(reference.startswith("aggregate:") for reference in higher.member_refs)
    assert higher.assertions[0].derived_from == tuple(sorted(higher.member_refs))


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper", ("invent", "members", "order", "duplicate"))
async def test_model_can_only_accept_exact_offered_candidate_membership_once(tamper: str) -> None:
    one = _session_ke("one")
    two = _session_ke("two")
    memories = (_memory("s1", (one,)), _memory("s2", (two,)))
    candidate = _depth1_candidates(memories)[0]
    proposal = _node_proposal(candidate.id, candidate.member_refs, (one, two))
    accepted: tuple[AggregateNodeProposal, ...]
    if tamper == "invent":
        accepted = (proposal.model_copy(update={"candidate_id": "candidate:invented"}),)
    elif tamper == "members":
        accepted = (proposal.model_copy(update={"member_refs": (one.id, "ke:invented")}),)
    elif tamper == "order":
        accepted = (
            proposal.model_copy(update={"member_refs": tuple(reversed(proposal.member_refs))}),
        )
    else:
        accepted = (proposal, proposal)
    forged = AggregateSelectionOutput.model_construct(accepted=accepted)
    model = FakeDAGModel((forged,))

    with pytest.raises(AggregationInvariantError, match="(candidate|member|validated)"):
        await _builder(model, memories).build(memories)


@pytest.mark.asyncio
async def test_aggregate_assertion_cannot_invent_terms_or_lower_references() -> None:
    one = _session_ke("one")
    two = _session_ke("two")
    memories = (_memory("s1", (one,)), _memory("s2", (two,)))
    candidate = _depth1_candidates(memories)[0]
    bad_assertion = _assertion_proposal(
        (one, two), lhs=IndividualRef(term_id="person:invented", label="Invented")
    )
    proposal = _node_proposal(candidate.id, candidate.member_refs, (one, two)).model_copy(
        update={"assertions": (bad_assertion,)}
    )
    model = FakeDAGModel((AggregateSelectionOutput(accepted=(proposal,)),))

    with pytest.raises(AggregationInvariantError, match="term"):
        await _builder(model, memories).build(memories)

    dangling = _assertion_proposal((one, two), derived_from=("ke:missing",))
    proposal = _node_proposal(candidate.id, candidate.member_refs, (one, two)).model_copy(
        update={"assertions": (dangling,)}
    )
    model = FakeDAGModel((AggregateSelectionOutput(accepted=(proposal,)),))
    with pytest.raises(AggregationInvariantError, match="lower"):
        await _builder(model, memories).build(memories)

    retyped = _assertion_proposal(
        (one, two),
        lhs=OperatorRef(term_id="person:alice", label="Alice as operator"),
    )
    proposal = _node_proposal(candidate.id, candidate.member_refs, (one, two)).model_copy(
        update={"assertions": (retyped,)}
    )
    model = FakeDAGModel((AggregateSelectionOutput(accepted=(proposal,)),))
    with pytest.raises(AggregationInvariantError, match="term or operator role"):
        await _builder(model, memories).build(memories)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    (
        "same_label_different_resolved_id",
        "same_document_different_role",
        "unresolved_same_surface_different_role",
        "unresolved_role",
        "nested_expression",
    ),
)
async def test_aggregate_binding_union_is_exact_for_used_atoms(case: str) -> None:
    source_lhs, source_rhs, bindings, lhs, rhs, expected = _ontology_binding_case(case)
    one = _session_ke(
        "one",
        lhs=source_lhs,
        rhs=source_rhs,
        bindings=bindings,
    )
    two = _session_ke(
        "two",
        lhs=source_lhs,
        rhs=source_rhs,
        bindings=bindings,
    )
    memories = (_memory("s1", (one,)), _memory("s2", (two,)))
    candidate = _depth1_candidates(memories)[0]
    assertion = _assertion_proposal((one, two), lhs=lhs, rhs=rhs)
    proposal = _node_proposal(candidate.id, candidate.member_refs, (one, two)).model_copy(
        update={"assertions": (assertion,)}
    )

    dag = await _builder(
        FakeDAGModel((AggregateSelectionOutput(accepted=(proposal,)),)),
        memories,
    ).build(memories)

    assert dag.nodes[0].assertions[0].ontology_bindings == expected
    validate_semantic_dag(dag.nodes, {one.id: one, two.id: two})


@pytest.mark.parametrize("tamper", ("over_broad", "under_broad"))
def test_validate_semantic_dag_rejects_inexact_role_aware_binding_sets(tamper: str) -> None:
    source_lhs, source_rhs, bindings, lhs, rhs, expected = _ontology_binding_case(
        "same_label_different_resolved_id"
    )
    one = _session_ke(
        "one",
        lhs=source_lhs,
        rhs=source_rhs,
        bindings=bindings,
    )
    two = _session_ke(
        "two",
        lhs=source_lhs,
        rhs=source_rhs,
        bindings=bindings,
    )
    tampered_bindings = (
        tuple(sorted(bindings, key=canonical_json)) if tamper == "over_broad" else ()
    )
    assertion = _aggregate_assertion(
        (one, two),
        lhs=lhs,
        rhs=rhs,
        ontology_bindings=tampered_bindings,
    )
    node = _node((one, two), assertion=assertion)
    assert expected

    with pytest.raises(AggregationInvariantError, match="ontology bindings are not exact"):
        validate_semantic_dag((node,), {one.id: one, two.id: two})


@pytest.mark.parametrize("field", ("contradicts", "supersedes"))
def test_validate_semantic_dag_rejects_dangling_aggregate_ke_relations(field: str) -> None:
    one = _session_ke("relation-one")
    two = _session_ke("relation-two")
    assertion = _aggregate_assertion((one, two))
    assertion = _recreate_equation(assertion, **{field: ("ke:missing",)})
    node = _node((one, two), assertion=assertion)

    with pytest.raises(AggregationInvariantError, match="contradicts|supersedes"):
        validate_semantic_dag((node,), {one.id: one, two.id: two})


def test_validate_semantic_dag_rejects_node_id_as_aggregate_ke_relation_target() -> None:
    one = _session_ke("relation-one")
    two = _session_ke("relation-two")
    three = _session_ke("relation-three")
    first = _node((one, two), title="Relation first")
    second = _node((one, three), title="Relation second")
    higher_assertion = KnowledgeEquation.create(
        level="aggregate",
        lhs=first.assertions[0].lhs,
        rhs=first.assertions[0].rhs,
        gloss="Wrong-type relation target",
        modality="fact",
        polarity="positive",
        lifecycle="active",
        speaker="derived",
        evidence_refs=_unique_spans((*first.evidence_closure, *second.evidence_closure)),
        derived_from=tuple(sorted((first.id, second.id))),
        contradicts=(first.id,),
        confidence=0.8,
        produced_in_run_id="dag-run",
        produced_in_stage="semantic-dag-built",
    )
    higher = create_aggregate_node(
        node_kind=AggregateNodeKind.TOPIC,
        title="Higher relation",
        summary="Higher relation summary",
        assertions=(higher_assertion,),
        member_refs=(first.id, second.id),
        derived_from=higher_assertion.derived_from,
        evidence_closure=_unique_spans((*first.evidence_closure, *second.evidence_closure)),
        temporal_extent=TemporalMetadata(),
        confidence=0.8,
        depth=2,
    )

    with pytest.raises(AggregationInvariantError, match="KnowledgeEquation|node ID"):
        validate_semantic_dag(
            (first, second, higher),
            {item.id: item for item in (one, two, three)},
        )


def test_aggregate_factory_rejects_depth1_node_id_as_assertion_ref_target() -> None:
    one = _session_ke("assertion-ref-one")
    two = _session_ke("assertion-ref-two")
    three = _session_ke("assertion-ref-three")
    first = _node((one, two), title="AssertionRef first")
    second = _node((one, three), title="AssertionRef second")
    invalid_assertion = _depth2_assertion_with_ref(first, second, first.id)

    with pytest.raises(AggregationInvariantError, match="AssertionRef.*KnowledgeEquation"):
        create_aggregate_node(
            node_kind=AggregateNodeKind.TOPIC,
            title="Invalid AssertionRef",
            summary="Node IDs are not assertion IDs.",
            assertions=(invalid_assertion,),
            member_refs=(first.id, second.id),
            derived_from=invalid_assertion.derived_from,
            evidence_closure=_unique_spans((*first.evidence_closure, *second.evidence_closure)),
            temporal_extent=TemporalMetadata(),
            confidence=0.8,
            depth=2,
        )


@pytest.mark.parametrize(
    "validator",
    (validate_evidence_closure, validate_semantic_dag),
    ids=("evidence_closure", "semantic_dag"),
)
def test_public_dag_validators_reject_nested_assertion_ref_to_depth1_node(
    validator: object,
) -> None:
    one = _session_ke("assertion-ref-one")
    two = _session_ke("assertion-ref-two")
    three = _session_ke("assertion-ref-three")
    first = _node((one, two), title="AssertionRef first")
    second = _node((one, three), title="AssertionRef second")
    valid_assertion = _depth2_assertion_with_ref(
        first,
        second,
        first.assertions[0].id,
    )
    valid = create_aggregate_node(
        node_kind=AggregateNodeKind.TOPIC,
        title="Valid AssertionRef",
        summary="The expression names a lower assertion.",
        assertions=(valid_assertion,),
        member_refs=(first.id, second.id),
        derived_from=valid_assertion.derived_from,
        evidence_closure=_unique_spans((*first.evidence_closure, *second.evidence_closure)),
        temporal_extent=TemporalMetadata(),
        confidence=0.8,
        depth=2,
    )
    invalid_assertion = _depth2_assertion_with_ref(first, second, first.id)
    invalid = _rehash_node(valid, assertions=(invalid_assertion,))
    known = {item.id: item for item in (one, two, three)}

    with pytest.raises(AggregationInvariantError, match="AssertionRef.*KnowledgeEquation"):
        cast(Any, validator)((first, second, invalid), known)


def test_validate_semantic_dag_rejects_dangling_known_session_ke_relations() -> None:
    one = _session_ke("known-relation-one")
    two = _session_ke("known-relation-two")
    forged = _recreate_equation(one, supersedes=("ke:missing",))
    node = _node((one, two))

    with pytest.raises(AggregationInvariantError, match="known Session KE.*supersedes"):
        validate_semantic_dag((node,), {forged.id: forged, two.id: two})


def test_aggregate_factory_uses_exact_logical_payload_and_revision_surface() -> None:
    one = _session_ke("one")
    two = _session_ke("two")
    assertion = _aggregate_assertion((one, two))
    node = _node((one, two), assertion=assertion)
    expected_payload = cast(
        JsonValue,
        {
            "schema_version": "ke-memory/v1",
            "node_kind": "Project",
            "member_refs": sorted((one.id, two.id)),
            "derived_from": sorted(assertion.derived_from),
            "assertion_ids": [assertion.id],
            "depth": 1,
        },
    )

    assert node.id == content_id("aggregate", expected_payload)
    changed = create_aggregate_node(
        node_kind=node.node_kind,
        title="Changed title",
        summary=node.summary,
        assertions=node.assertions,
        member_refs=node.member_refs,
        derived_from=node.derived_from,
        evidence_closure=node.evidence_closure,
        temporal_extent=node.temporal_extent,
        confidence=node.confidence,
        depth=node.depth,
    )
    assert changed.id == node.id
    assert changed.revision != node.revision
    assert canonical_json(node.model_dump(mode="json", exclude={"revision"}))


def test_validate_evidence_closure_rejects_missing_and_inexact_member_closure() -> None:
    one = _session_ke("one")
    two = _session_ke("two")
    node = _node((one, two))

    with pytest.raises(AggregationInvariantError, match="missing member"):
        validate_evidence_closure((node,), {one.id: one})

    bad = create_aggregate_node(
        node_kind=node.node_kind,
        title=node.title,
        summary=node.summary,
        assertions=node.assertions,
        member_refs=node.member_refs,
        derived_from=node.derived_from,
        evidence_closure=one.evidence_refs,
        temporal_extent=node.temporal_extent,
        confidence=node.confidence,
        depth=node.depth,
    )
    with pytest.raises(AggregationInvariantError, match="evidence closure"):
        validate_evidence_closure((bad,), {one.id: one, two.id: two})


def test_validate_evidence_closure_reauthenticates_node_identity_and_revision() -> None:
    one = _session_ke("one")
    two = _session_ke("two")
    node = _node((one, two))
    known = {one.id: one, two.id: two}

    forged_nodes = (
        (node.model_copy(update={"id": "aggregate:tampered"}), "logical ID"),
        (node.model_copy(update={"title": "Tampered title"}), "revision"),
        (
            node.model_copy(update={"member_refs": tuple(reversed(node.member_refs))}),
            "canonical",
        ),
    )
    for forged, expected_error in forged_nodes:
        with pytest.raises(AggregationInvariantError, match=expected_error):
            validate_evidence_closure((forged,), known)


@pytest.mark.parametrize(
    "case",
    (
        "single_member",
        "duplicate_members",
        "unsorted_members",
        "unsorted_derived_from",
        "unsorted_assertions",
        "duplicate_assertions",
        "unsorted_evidence",
        "invalid_nested_assertion",
        "coercible_depth",
        "coercible_nested_mapping",
    ),
)
@pytest.mark.parametrize(
    "validator",
    (validate_evidence_closure, validate_semantic_dag),
    ids=("evidence_closure", "semantic_dag"),
)
def test_public_aggregate_validators_reject_rehashed_noncanonical_node_shapes(
    case: str,
    validator: object,
) -> None:
    one = _session_ke("one")
    two = _session_ke("two")
    known = {one.id: one, two.id: two}
    assertion = _aggregate_assertion((one, two))
    node = _node((one, two), assertion=assertion)

    if case in {"single_member", "duplicate_members"}:
        assertion = _aggregate_assertion((one,))
        node = _rehash_node(
            node,
            assertions=(assertion,),
            member_refs=((one.id,) if case == "single_member" else (one.id, one.id)),
            derived_from=assertion.derived_from,
            evidence_closure=one.evidence_refs,
        )
    elif case == "unsorted_members":
        node = _rehash_node(node, member_refs=tuple(reversed(node.member_refs)))
    elif case == "unsorted_derived_from":
        node = _rehash_node(node, derived_from=tuple(reversed(node.derived_from)))
    elif case in {"unsorted_assertions", "duplicate_assertions"}:
        second = _aggregate_assertion((two, one))
        node = create_aggregate_node(
            node_kind=node.node_kind,
            title=node.title,
            summary=node.summary,
            assertions=(assertion, second),
            member_refs=node.member_refs,
            derived_from=node.derived_from,
            evidence_closure=node.evidence_closure,
            temporal_extent=node.temporal_extent,
            confidence=node.confidence,
            depth=node.depth,
        )
        assertions = (
            tuple(reversed(node.assertions))
            if case == "unsorted_assertions"
            else (node.assertions[0], node.assertions[0])
        )
        node = _rehash_node(node, assertions=assertions)
    elif case == "unsorted_evidence":
        node = _rehash_node(node, evidence_closure=tuple(reversed(node.evidence_closure)))
    elif case == "invalid_nested_assertion":
        invalid_assertion = KnowledgeEquation.model_construct(
            **cast(
                Any,
                {
                    **{
                        field: getattr(assertion, field) for field in KnowledgeEquation.model_fields
                    },
                    "gloss": "",
                },
            )
        )
        node = _rehash_node(node, assertions=(invalid_assertion,))
    elif case == "coercible_depth":
        node = _rehash_node(node, depth=1.0)
    else:
        node = _rehash_node(node, assertions=(assertion.model_dump(mode="python"),))

    with pytest.raises(AggregationInvariantError, match="shape|canonical"):
        cast(Any, validator)((node,), known)


def test_public_aggregate_validators_accept_factory_canonical_node() -> None:
    one = _session_ke("one")
    two = _session_ke("two")
    node = _node((one, two))
    known = {one.id: one, two.id: two}

    validate_evidence_closure((node,), known)
    assert validate_semantic_dag((node,), known).nodes == (node,)


def test_validate_semantic_dag_requires_authentic_session_level_known_kes() -> None:
    one = _session_ke("one")
    two = _session_ke("two")
    node = _node((one, two))

    forged = one.model_copy(update={"revision": "0" * 64})
    with pytest.raises(AggregationInvariantError, match="known Session KE.*revision"):
        validate_semantic_dag((node,), {forged.id: forged, two.id: two})

    turn = KnowledgeEquation.create(
        level="turn",
        lhs=one.lhs,
        rhs=one.rhs,
        gloss=one.gloss,
        modality=one.modality,
        polarity=one.polarity,
        lifecycle=one.lifecycle,
        speaker="user",
        evidence_refs=one.evidence_refs,
        confidence=one.confidence,
        produced_in_run_id="turn-run",
        produced_in_stage="turn-ke-extracted",
    )
    wrong_level_node = _node((turn, two))
    with pytest.raises(AggregationInvariantError, match="not Session-level"):
        validate_semantic_dag((wrong_level_node,), {turn.id: turn, two.id: two})


def test_aggregate_factory_rejects_invalid_depth_and_empty_assertions() -> None:
    one = _session_ke("one")
    two = _session_ke("two")
    evidence = _unique_spans((*one.evidence_refs, *two.evidence_refs))
    with pytest.raises(AggregationInvariantError, match="depth"):
        create_aggregate_node(
            node_kind=AggregateNodeKind.OTHER,
            title="Invalid",
            summary="Invalid depth",
            assertions=(_aggregate_assertion((one, two)),),
            member_refs=(one.id, two.id),
            derived_from=(one.id, two.id),
            evidence_closure=evidence,
            temporal_extent=TemporalMetadata(),
            confidence=0.5,
            depth=3,
        )
    with pytest.raises(AggregationInvariantError, match="assertion"):
        create_aggregate_node(
            node_kind=AggregateNodeKind.OTHER,
            title="Invalid",
            summary="No assertions",
            assertions=(),
            member_refs=(one.id, two.id),
            derived_from=(one.id, two.id),
            evidence_closure=evidence,
            temporal_extent=TemporalMetadata(),
            confidence=0.5,
            depth=1,
        )

    source_assertion = _aggregate_assertion((one, two))
    tampered_assertion = source_assertion.model_copy(update={"revision": "0" * 64})
    with pytest.raises(AggregationInvariantError, match="assertion.*revision"):
        create_aggregate_node(
            node_kind=AggregateNodeKind.OTHER,
            title="Invalid",
            summary="Tampered assertion",
            assertions=(tampered_assertion,),
            member_refs=(one.id, two.id),
            derived_from=source_assertion.derived_from,
            evidence_closure=evidence,
            temporal_extent=TemporalMetadata(),
            confidence=0.5,
            depth=1,
        )

    with pytest.raises(AggregationInvariantError, match="exact aggregate assertion"):
        create_aggregate_node(
            node_kind=AggregateNodeKind.OTHER,
            title="Invalid",
            summary="Mismatched node refs",
            assertions=(source_assertion,),
            member_refs=(one.id, two.id),
            derived_from=(one.id,),
            evidence_closure=evidence,
            temporal_extent=TemporalMetadata(),
            confidence=0.5,
            depth=1,
        )


def test_depth1_candidates_reject_tampered_session_memory_before_any_model_pass() -> None:
    first = _session_ke("first")
    second = _session_ke("second")
    forged = first.model_copy(update={"revision": "0" * 64})
    memory = _memory("s1", (first,)).model_copy(update={"knowledge_equations": (forged,)})

    with pytest.raises(AggregationInvariantError, match="SessionMemory"):
        _depth1_candidates((memory, _memory("s2", (second,))))


@pytest.mark.parametrize(
    "case",
    ("speaker", "lifecycle", "stage", "lower_order"),
)
def test_depth1_candidates_require_fully_validated_session_memories(case: str) -> None:
    memories, source_turn_kes = _invalid_session_source_fixture(case)

    with pytest.raises(
        AggregationInvariantError,
        match="speaker|lifecycle|stage|lower refs",
    ):
        generate_depth1_candidates(memories, source_turn_kes)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    ("speaker", "lifecycle", "stage", "lower_order"),
)
async def test_builder_rejects_invalid_session_sources_before_model_call(case: str) -> None:
    memories, source_turn_kes = _invalid_session_source_fixture(case)
    model = FakeDAGModel(())

    with pytest.raises(
        AggregationInvariantError,
        match="speaker|lifecycle|stage|lower refs",
    ):
        await SemanticDAGBuilder(
            model,
            source_turn_kes,
            run_id="dag-run",
        ).build(memories)

    assert model.calls == []


@pytest.mark.parametrize("case", ("nested_mapping", "list_source_ids"))
def test_depth1_candidates_reject_noncanonical_session_memory_runtime_shape(
    case: str,
) -> None:
    memories, source_turn_kes = _noncanonical_memory_fixture(case)

    with pytest.raises(AggregationInvariantError, match="SessionMemory.*shape"):
        generate_depth1_candidates(memories, source_turn_kes)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ("nested_mapping", "list_source_ids"))
async def test_builder_rejects_noncanonical_session_memory_before_any_read_or_model_call(
    case: str,
) -> None:
    memories, source_turn_kes = _noncanonical_memory_fixture(case)
    model = FakeDAGModel(())

    with pytest.raises(AggregationInvariantError, match="SessionMemory.*shape"):
        await SemanticDAGBuilder(model, source_turn_kes, run_id="dag-run").build(memories)

    assert model.calls == []


@pytest.mark.parametrize("case", ("missing", "extra", "duplicate_claim"))
def test_depth1_candidates_require_exact_unshared_turn_ke_sources(case: str) -> None:
    memories, source_turn_kes = _source_mapping_fixture(case)

    with pytest.raises(AggregationInvariantError, match="missing|extra|more than one"):
        generate_depth1_candidates(memories, source_turn_kes)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ("missing", "extra", "duplicate_claim"))
async def test_builder_rejects_inexact_turn_ke_sources_before_model_call(case: str) -> None:
    memories, source_turn_kes = _source_mapping_fixture(case)
    model = FakeDAGModel(())

    with pytest.raises(AggregationInvariantError, match="missing|extra|more than one"):
        await SemanticDAGBuilder(
            model,
            source_turn_kes,
            run_id="dag-run",
        ).build(memories)

    assert model.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("public_path", ("candidate_generator", "builder"))
@pytest.mark.parametrize("field", ("derived_from", "contradicts", "supersedes"))
async def test_depth1_boundaries_reject_dangling_global_turn_ke_relations_before_model_call(
    field: str,
    public_path: str,
) -> None:
    memories, source_turn_kes = _global_turn_relation_fixture((field,), dangling=True)
    model = FakeDAGModel(())

    with pytest.raises(AggregationInvariantError, match=rf"source Turn KE.*{field}"):
        if public_path == "candidate_generator":
            generate_depth1_candidates(memories, source_turn_kes)
        else:
            await SemanticDAGBuilder(model, source_turn_kes, run_id="dag-run").build(memories)

    assert model.calls == []


@pytest.mark.asyncio
async def test_global_turn_ke_relations_may_target_a_different_cross_session_turn_ke() -> None:
    memories, source_turn_kes = _global_turn_relation_fixture(
        ("derived_from", "contradicts", "supersedes"),
        dangling=False,
    )

    candidates = generate_depth1_candidates(memories, source_turn_kes)
    model = FakeDAGModel((AggregateSelectionOutput(),))

    assert candidates
    assert await SemanticDAGBuilder(model, source_turn_kes, run_id="dag-run").build(memories) == (
        SemanticDAG()
    )
    assert len(model.calls) == 1


def test_validate_semantic_dag_rejects_self_dangling_cycle_and_depth_type_errors() -> None:
    one = _session_ke("one")
    two = _session_ke("two")
    valid = _node((one, two))

    self_edge = valid.model_copy(update={"member_refs": (valid.id,)})
    with pytest.raises(AggregationInvariantError, match="self"):
        validate_semantic_dag((self_edge,), {one.id: one, two.id: two})

    dangling = valid.model_copy(update={"member_refs": ("aggregate:missing",)})
    with pytest.raises(AggregationInvariantError, match="dangling|missing member"):
        validate_semantic_dag((dangling,), {one.id: one, two.id: two})

    a = valid.model_copy(update={"id": "aggregate:a", "depth": 2})
    b = valid.model_copy(update={"id": "aggregate:b", "revision": "1" * 64, "depth": 2})
    a = a.model_copy(update={"member_refs": (b.id,)})
    b = b.model_copy(update={"member_refs": (a.id,)})
    with pytest.raises(AggregationInvariantError, match="cycle"):
        validate_semantic_dag((a, b), {one.id: one, two.id: two})

    depth_one_with_node = valid.model_copy(update={"member_refs": ("aggregate:other",)})
    other = valid.model_copy(update={"id": "aggregate:other", "revision": "2" * 64})
    with pytest.raises(AggregationInvariantError, match="depth-1"):
        validate_semantic_dag((depth_one_with_node, other), {one.id: one, two.id: two})


def test_validate_semantic_dag_rejects_tampered_node_id_revision_and_assertion_revision() -> None:
    one = _session_ke("one")
    two = _session_ke("two")
    node = _node((one, two))
    known = {one.id: one, two.id: two}

    with pytest.raises(AggregationInvariantError, match="logical ID"):
        validate_semantic_dag((node.model_copy(update={"id": "aggregate:tampered"}),), known)
    with pytest.raises(AggregationInvariantError, match="revision"):
        validate_semantic_dag((node.model_copy(update={"revision": "0" * 64}),), known)
    bad_assertion = node.assertions[0].model_copy(update={"revision": "0" * 64})
    bad_node = node.model_copy(update={"assertions": (bad_assertion,)})
    with pytest.raises(AggregationInvariantError, match="assertion.*revision"):
        validate_semantic_dag((bad_node,), known)

    with pytest.raises(AggregationInvariantError, match="exact aggregate assertion"):
        create_aggregate_node(
            node_kind=node.node_kind,
            title=node.title,
            summary=node.summary,
            assertions=node.assertions,
            member_refs=node.member_refs,
            derived_from=(one.id,),
            evidence_closure=node.evidence_closure,
            temporal_extent=node.temporal_extent,
            confidence=node.confidence,
            depth=node.depth,
        )


def test_validate_semantic_dag_rejects_authentic_unsorted_assertion_lower_refs() -> None:
    one = _session_ke("one")
    two = _session_ke("two")
    source = _aggregate_assertion((one, two))
    reversed_refs = tuple(reversed(source.derived_from))
    assert reversed_refs != source.derived_from
    reordered = KnowledgeEquation.create(
        level=source.level,
        lhs=source.lhs,
        rhs=source.rhs,
        gloss=source.gloss,
        modality=source.modality,
        polarity=source.polarity,
        lifecycle=source.lifecycle,
        speaker=source.speaker,
        temporal=source.temporal,
        ontology_bindings=source.ontology_bindings,
        evidence_refs=source.evidence_refs,
        derived_from=reversed_refs,
        confidence=source.confidence,
        produced_in_run_id=source.produced_in_run_id,
        produced_in_stage=source.produced_in_stage,
    )
    node = _node((one, two), assertion=reordered)

    with pytest.raises(AggregationInvariantError, match="lower refs must be sorted"):
        validate_semantic_dag((node,), {one.id: one, two.id: two})


def test_topological_order_is_lower_before_higher_with_id_ties_and_overlap_allowed() -> None:
    one = _session_ke("one")
    two = _session_ke("two")
    three = _session_ke("three")
    first = _node((one, two), title="First")
    second = _node((one, three), title="Second")
    # The shared Session KE is intentionally owned by both depth-1 nodes.
    depth_two_assertion = KnowledgeEquation.create(
        level="aggregate",
        lhs=first.assertions[0].lhs,
        rhs=first.assertions[0].rhs,
        gloss="Higher assertion",
        modality="fact",
        polarity="positive",
        lifecycle="active",
        speaker="derived",
        evidence_refs=_unique_spans((*first.evidence_closure, *second.evidence_closure)),
        derived_from=tuple(
            sorted(
                {
                    reference
                    for node in (first, second)
                    for assertion in node.assertions
                    for reference in assertion.derived_from
                }
            )
        ),
        confidence=0.8,
        produced_in_run_id="dag-run",
        produced_in_stage="semantic-dag-built",
    )
    higher = create_aggregate_node(
        node_kind=AggregateNodeKind.TOPIC,
        title="Higher",
        summary="Higher summary",
        assertions=(depth_two_assertion,),
        member_refs=(second.id, first.id),
        derived_from=depth_two_assertion.derived_from,
        evidence_closure=_unique_spans((*first.evidence_closure, *second.evidence_closure)),
        temporal_extent=TemporalMetadata(),
        confidence=0.8,
        depth=2,
    )
    known = {item.id: item for item in (one, two, three)}

    dag = validate_semantic_dag((higher, second, first), known)

    expected_lower = tuple(sorted((first.id, second.id)))
    assert tuple(item.id for item in dag.nodes[:2]) == expected_lower
    assert dag.nodes[2].id == higher.id
    assert dag.max_depth == 2


def test_node_temporal_extent_must_equal_exact_open_member_envelope() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    one = _session_ke("one", temporal=TemporalMetadata(valid_from=start))
    two = _session_ke("two", temporal=TemporalMetadata(event_time=start + timedelta(days=2)))
    assertion = _aggregate_assertion((one, two))
    evidence = tuple(sorted((*one.evidence_refs, *two.evidence_refs), key=_span_key))
    correct = create_aggregate_node(
        node_kind=AggregateNodeKind.EVENT_CHAIN,
        title="Timeline",
        summary="Timeline summary",
        assertions=(assertion,),
        member_refs=(one.id, two.id),
        derived_from=assertion.derived_from,
        evidence_closure=evidence,
        temporal_extent=TemporalMetadata(valid_from=start),
        confidence=0.8,
        depth=1,
    )
    validate_semantic_dag((correct,), {one.id: one, two.id: two})

    bad = create_aggregate_node(
        node_kind=correct.node_kind,
        title=correct.title,
        summary=correct.summary,
        assertions=correct.assertions,
        member_refs=correct.member_refs,
        derived_from=correct.derived_from,
        evidence_closure=correct.evidence_closure,
        temporal_extent=TemporalMetadata(valid_from=start, valid_to=start + timedelta(days=2)),
        confidence=correct.confidence,
        depth=1,
    )
    with pytest.raises(AggregationInvariantError, match="temporal extent"):
        validate_semantic_dag((bad,), {one.id: one, two.id: two})


def test_depth2_candidates_use_only_depth1_nodes_and_overlap_symbolically() -> None:
    one = _session_ke("one")
    two = _session_ke("two")
    three = _session_ke("three")
    first = _node((one, two), title="First")
    second = _node((one, three), title="Second")

    candidates = generate_depth2_candidates((second, first))

    assert candidates
    assert any("overlapping_members" in item.reasons for item in candidates)
    assert all(item.depth == 2 for item in candidates)
    assert all(set(item.member_refs).issubset({first.id, second.id}) for item in candidates)


def test_builder_has_no_embedding_dependency_surface() -> None:
    parameters = inspect.signature(SemanticDAGBuilder).parameters
    assert "embedding" not in parameters
    assert "embedder" not in parameters


def _span_key(span: MessageSpan) -> tuple[str, int, int, str]:
    return (span.message_id, span.start_char, span.end_char, span.text_hash)


def _unique_spans(spans: Iterable[MessageSpan]) -> tuple[MessageSpan, ...]:
    unique = {_span_key(span): span for span in spans}
    return tuple(unique[key] for key in sorted(unique))


def _rehash_node(node: AggregateNode, **updates: object) -> AggregateNode:
    data = {field: getattr(node, field) for field in AggregateNode.model_fields}
    data.update(updates)
    forged = AggregateNode.model_construct(**data)
    raw_assertions = cast(tuple[object, ...], forged.assertions)
    logical_payload = cast(
        JsonValue,
        {
            "schema_version": "ke-memory/v1",
            "node_kind": forged.node_kind.value,
            "member_refs": list(sorted(forged.member_refs)),
            "derived_from": list(sorted(forged.derived_from)),
            "assertion_ids": sorted(_raw_assertion_id(assertion) for assertion in raw_assertions),
            "depth": forged.depth,
        },
    )
    forged = forged.model_copy(update={"id": content_id("aggregate", logical_payload)})
    revision_payload = cast(
        JsonValue,
        forged.model_dump(mode="json", exclude={"revision"}, warnings=False),
    )
    return forged.model_copy(
        update={"revision": hashlib.sha256(canonical_json(revision_payload)).hexdigest()}
    )


def _raw_assertion_id(assertion: object) -> str:
    if isinstance(assertion, KnowledgeEquation):
        return assertion.id
    return cast(str, cast(Mapping[str, object], assertion)["id"])


def _ontology_binding_case(
    case: str,
) -> tuple[
    Expression,
    Expression,
    tuple[OntologyBinding, ...],
    Expression,
    Expression,
    tuple[OntologyBinding, ...],
]:
    if case == "same_label_different_resolved_id":
        wanted = ConceptRef(term_id="concept:wanted", label="shared")
        other = ConceptRef(term_id="concept:other", label="shared")
        bindings = (
            _resolved_binding("concept:wanted", "shared", OntologyRole.CONCEPT),
            _resolved_binding("concept:other", "shared", OntologyRole.CONCEPT),
        )
        return wanted, other, bindings, wanted, wanted, (bindings[0],)
    if case == "same_document_different_role":
        wanted = ConceptRef(term_id="entity:shared", label="shared")
        other = OperatorRef(term_id="entity:shared", label="shared")
        bindings = (
            _resolved_binding("entity:shared", "shared", OntologyRole.CONCEPT),
            _resolved_binding("entity:shared", "shared", OntologyRole.OPERATOR),
        )
        return wanted, other, bindings, wanted, wanted, (bindings[0],)
    if case == "unresolved_same_surface_different_role":
        normalized = "mystery"
        wanted = ConceptRef(
            term_id=content_id("unresolved-concept", normalized),
            label="Mystery",
        )
        other = OperatorRef(
            term_id=content_id("unresolved-operator", normalized),
            label="Mystery",
        )
        binding = OntologyBinding(
            surface_form="Mystery",
            normalized_surface=normalized,
            status=OntologyBindingStatus.UNRESOLVED,
        )
        return wanted, other, (binding,), wanted, wanted, (binding,)
    if case == "unresolved_role":
        normalized = "ambiguous"
        wanted = ConceptRef(
            term_id=content_id("unresolved-concept", normalized),
            label="Ambiguous",
        )
        binding = OntologyBinding(
            surface_form="Ambiguous",
            normalized_surface=normalized,
            status=OntologyBindingStatus.UNRESOLVED_ROLE,
            document_id="roleless-document",
            canonical_term="Ambiguous",
            source_type="ambiguous",
        )
        return wanted, wanted, (binding,), wanted, wanted, (binding,)

    subject = IndividualRef(term_id="person:alice", label="Alice")
    value = ConceptRef(term_id="concept:nested", label="Nested")
    inner = OperatorApplication(
        operator=OperatorRef(term_id="operator:inner", label="inner"),
        arguments=(value,),
    )
    outer = OperatorApplication(
        operator=OperatorRef(term_id="operator:outer", label="outer"),
        arguments=(inner,),
    )
    bindings = (
        _resolved_binding("concept:nested", "Nested", OntologyRole.CONCEPT),
        _resolved_binding("operator:inner", "inner", OntologyRole.OPERATOR),
        _resolved_binding("operator:outer", "outer", OntologyRole.OPERATOR),
    )
    expected = tuple(sorted(bindings[:2], key=canonical_json))
    return subject, outer, bindings, subject, inner, expected


def _resolved_binding(
    document_id: str,
    surface: str,
    role: OntologyRole,
) -> OntologyBinding:
    return OntologyBinding(
        surface_form=surface,
        normalized_surface=surface.casefold(),
        status=OntologyBindingStatus.RESOLVED,
        document_id=document_id,
        canonical_term=surface.title(),
        role=role,
        source_type="test",
    )


def _source_turn_kes(
    memories: Sequence[SessionMemory],
) -> dict[str, KnowledgeEquation]:
    source_ids = {source_id for memory in memories for source_id in memory.source_turn_ke_ids}
    return {source_id: _SOURCE_TURN_KES[source_id] for source_id in source_ids}


def _depth1_candidates(
    memories: Sequence[SessionMemory],
) -> tuple[AggregateCandidate, ...]:
    return generate_depth1_candidates(memories, _source_turn_kes(memories))


def _builder(
    model: FakeDAGModel,
    memories: Sequence[SessionMemory],
) -> SemanticDAGBuilder:
    return SemanticDAGBuilder(model, _source_turn_kes(memories), run_id="dag-run")


def _invalid_session_source_fixture(
    case: str,
) -> tuple[tuple[SessionMemory, ...], dict[str, KnowledgeEquation]]:
    first = _session_ke("boundary-first")
    if case == "lower_order":
        support = _session_ke("boundary-support")
        source_ids = tuple(sorted((*first.derived_from, *support.derived_from)))
        evidence = _unique_spans((*first.evidence_refs, *support.evidence_refs))
        first = _recreate_equation(
            first,
            derived_from=tuple(reversed(source_ids)),
            evidence_refs=evidence,
        )
    elif case == "speaker":
        first = _recreate_equation(first, speaker="user")
    elif case == "lifecycle":
        first = _recreate_equation(first, lifecycle="retracted")
    else:
        first = _recreate_equation(first, produced_in_stage="wrong-stage")
    peer = _session_ke("boundary-peer")
    memories = (_memory("boundary-s1", (first,)), _memory("boundary-s2", (peer,)))
    return memories, _source_turn_kes(memories)


def _source_mapping_fixture(
    case: str,
) -> tuple[tuple[SessionMemory, ...], dict[str, KnowledgeEquation]]:
    first = _session_ke("mapping-first")
    second = _session_ke("mapping-second")
    memories = (_memory("mapping-s1", (first,)), _memory("mapping-s2", (second,)))
    sources = _source_turn_kes(memories)
    if case == "missing":
        sources.pop(first.derived_from[0])
        return memories, sources
    if case == "extra":
        extra = _session_ke("mapping-extra")
        sources.update(_source_turn_kes((_memory("unused", (extra,)),)))
        return memories, sources

    source = _SOURCE_TURN_KES[first.derived_from[0]]
    lhs_assertion = _session_equation_from_turn(source, source.lhs, source.lhs)
    rhs_assertion = _session_equation_from_turn(source, source.rhs, source.rhs)
    memories = (
        _memory("mapping-s1", (lhs_assertion,)),
        _memory("mapping-s2", (rhs_assertion,)),
    )
    return memories, {source.id: source}


def _global_turn_relation_fixture(
    fields: Sequence[str],
    *,
    dangling: bool,
) -> tuple[tuple[SessionMemory, ...], dict[str, KnowledgeEquation]]:
    first = _session_ke("global-relation-first")
    second = _session_ke("global-relation-second")
    first_source = _SOURCE_TURN_KES[first.derived_from[0]]
    second_source = _SOURCE_TURN_KES[second.derived_from[0]]
    target_id = "ke:missing" if dangling else second_source.id
    linked_source = _recreate_equation(
        first_source,
        **{field: (target_id,) for field in fields},
    )
    linked_session = _session_equation_from_turn(
        linked_source,
        linked_source.lhs,
        linked_source.rhs,
    )
    memories = (
        _memory("global-relation-s1", (linked_session,)),
        _memory("global-relation-s2", (second,)),
    )
    return memories, {linked_source.id: linked_source, second_source.id: second_source}


def _noncanonical_memory_fixture(
    case: str,
) -> tuple[tuple[SessionMemory, ...], dict[str, KnowledgeEquation]]:
    first = _session_ke("runtime-memory-first")
    second = _session_ke("runtime-memory-second")
    valid_memories = (
        _memory("runtime-s1", (first,)),
        _memory("runtime-s2", (second,)),
    )
    source_turn_kes = _source_turn_kes(valid_memories)
    first_data = {field: getattr(valid_memories[0], field) for field in SessionMemory.model_fields}
    if case == "nested_mapping":
        first_data["knowledge_equations"] = (first.model_dump(mode="python"),)
    else:
        first_data["source_turn_ke_ids"] = list(valid_memories[0].source_turn_ke_ids)
    forged = SessionMemory.model_construct(**cast(Any, first_data))
    return (forged, valid_memories[1]), source_turn_kes


def _session_equation_from_turn(
    source: KnowledgeEquation,
    lhs: Expression,
    rhs: Expression,
) -> KnowledgeEquation:
    return KnowledgeEquation.create(
        level="session",
        lhs=lhs,
        rhs=rhs,
        gloss="Validated Session source",
        modality="fact",
        polarity="positive",
        lifecycle="active",
        speaker="derived",
        temporal=source.temporal,
        ontology_bindings=(),
        evidence_refs=source.evidence_refs,
        derived_from=(source.id,),
        confidence=0.9,
        produced_in_run_id="session-run",
        produced_in_stage="session-aggregated",
    )


def _recreate_equation(
    equation: KnowledgeEquation,
    **updates: object,
) -> KnowledgeEquation:
    values: dict[str, object] = {
        "level": equation.level,
        "lhs": equation.lhs,
        "rhs": equation.rhs,
        "gloss": equation.gloss,
        "modality": equation.modality,
        "polarity": equation.polarity,
        "lifecycle": equation.lifecycle,
        "speaker": equation.speaker,
        "temporal": equation.temporal,
        "ontology_bindings": equation.ontology_bindings,
        "evidence_refs": equation.evidence_refs,
        "derived_from": equation.derived_from,
        "contradicts": equation.contradicts,
        "supersedes": equation.supersedes,
        "confidence": equation.confidence,
        "produced_in_run_id": equation.produced_in_run_id,
        "produced_in_stage": equation.produced_in_stage,
    }
    values.update(updates)
    return KnowledgeEquation.create(**cast(Any, values))


def _depth2_assertion_with_ref(
    first: AggregateNode,
    second: AggregateNode,
    assertion_id: str,
) -> KnowledgeEquation:
    source_rhs = cast(OperatorApplication, first.assertions[0].rhs)
    lhs = OperatorApplication(
        operator=source_rhs.operator,
        arguments=(AssertionRef(assertion_id=assertion_id),),
    )
    return KnowledgeEquation.create(
        level="aggregate",
        lhs=lhs,
        rhs=first.assertions[0].rhs,
        gloss="Nested lower assertion reference",
        modality="fact",
        polarity="positive",
        lifecycle="active",
        speaker="derived",
        evidence_refs=_unique_spans((*first.evidence_closure, *second.evidence_closure)),
        derived_from=tuple(sorted((first.id, second.id))),
        confidence=0.8,
        produced_in_run_id="dag-run",
        produced_in_stage="semantic-dag-built",
    )


def _nested_operator_expression(
    outer_id: str,
    inner_id: str,
) -> OperatorApplication:
    return OperatorApplication(
        operator=OperatorRef(term_id=outer_id, label=outer_id),
        arguments=(
            OperatorApplication(
                operator=OperatorRef(term_id=inner_id, label=inner_id),
                arguments=(ConceptRef(term_id="concept:value", label="Value"),),
            ),
        ),
    )
