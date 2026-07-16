from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
import hashlib
import inspect
from typing import Literal, TypeVar, cast

import pytest
from pydantic import BaseModel

from ke_memory_demo.aggregation import (
    AggregationInvariantError,
    AggregateAssertionProposal,
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
    ConceptRef,
    Expression,
    IndividualRef,
    KnowledgeEquation,
    MessageSpan,
    Modality,
    OperatorApplication,
    OperatorRef,
    Polarity,
    TemporalMetadata,
    content_id,
)
from ke_memory_demo.infra.telemetry import TraceContext


ModelT = TypeVar("ModelT", bound=BaseModel)


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
) -> KnowledgeEquation:
    target = value or f"project:{name}"
    rhs = (
        OperatorApplication(
            operator=OperatorRef(term_id=operator, label=operator),
            arguments=(ConceptRef(term_id=target, label=target),),
        )
        if operator is not None
        else ConceptRef(term_id=target, label=target)
    )
    return KnowledgeEquation.create(
        level="session",
        lhs=IndividualRef(term_id=subject, label=subject),
        rhs=rhs,
        gloss=f"{subject} {operator or 'equals'} {target}",
        modality="fact",
        polarity="positive",
        lifecycle="active",
        speaker="derived",
        temporal=temporal,
        evidence_refs=(_span(name),),
        derived_from=tuple(derived_from) if derived_from is not None else (f"turn:{name}",),
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
) -> AggregateAssertionProposal:
    source = lower[0]
    return AggregateAssertionProposal(
        key=key,
        lhs=lhs or source.lhs,
        rhs=source.rhs,
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
        lhs=lower[0].lhs,
        rhs=lower[0].rhs,
        gloss="Aggregate assertion",
        modality="fact",
        polarity="positive",
        lifecycle="active",
        speaker="derived",
        temporal=temporal,
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

    first = generate_depth1_candidates(memories)
    second = generate_depth1_candidates(tuple(reversed(memories)))

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

    assert generate_depth1_candidates((_memory("same-session", (first, second)),)) == ()


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

    candidates = generate_depth1_candidates(memories)

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

    candidates = generate_depth1_candidates(
        (
            _memory("s1", (first,)),
            _memory("s2", (unrelated_middle,)),
            _memory("s3", (last,)),
        )
    )

    shared_pair = tuple(sorted((first.id, last.id)))
    matching = [item for item in candidates if item.member_refs == shared_pair]
    assert matching
    assert "temporal_adjacency" not in matching[0].reasons


@pytest.mark.asyncio
async def test_empty_memory_and_no_cross_session_candidates_skip_model() -> None:
    empty = _memory("empty", ())
    isolated = _memory("one", (_session_ke("only"),))
    model = FakeDAGModel(())

    assert await SemanticDAGBuilder(model, run_id="dag-run").build(
        (empty, isolated)
    ) == SemanticDAG(nodes=())
    assert model.calls == []
    assert model.embedding_calls == 0


@pytest.mark.asyncio
async def test_builder_runs_one_or_two_structured_passes_and_never_embeddings() -> None:
    one = _session_ke("one")
    two = _session_ke("two")
    memories = (_memory("s1", (one,)), _memory("s2", (two,)))
    candidate = generate_depth1_candidates(memories)[0]
    accepted = _node_proposal(candidate.id, candidate.member_refs, (one, two))
    model = FakeDAGModel(
        (
            AggregateSelectionOutput(accepted=(accepted,)),
            AggregateSelectionOutput(accepted=()),
        )
    )

    dag = await SemanticDAGBuilder(model, run_id="dag-run").build(memories)

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
    candidates = generate_depth1_candidates(memories)
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
    depth1_only = await SemanticDAGBuilder(first_model, run_id="dag-run").build(memories)
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

    dag = await SemanticDAGBuilder(model, run_id="dag-run").build(memories)

    assert len(model.calls) == 2
    assert dag.max_depth == 2
    higher = dag.nodes[-1]
    assert higher.depth == 2
    assert set(higher.member_refs) == {node.id for node in dag.nodes if node.depth == 1}
    assert all(reference.startswith("aggregate:") for reference in higher.member_refs)
    assert higher.assertions[0].derived_from == tuple(sorted(higher.member_refs))


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper", ["invent", "members", "duplicate"])
async def test_model_can_only_accept_exact_offered_candidate_membership_once(tamper: str) -> None:
    one = _session_ke("one")
    two = _session_ke("two")
    memories = (_memory("s1", (one,)), _memory("s2", (two,)))
    candidate = generate_depth1_candidates(memories)[0]
    proposal = _node_proposal(candidate.id, candidate.member_refs, (one, two))
    accepted: tuple[AggregateNodeProposal, ...]
    if tamper == "invent":
        accepted = (proposal.model_copy(update={"candidate_id": "candidate:invented"}),)
    elif tamper == "members":
        accepted = (proposal.model_copy(update={"member_refs": (one.id, "ke:invented")}),)
    else:
        accepted = (proposal, proposal)
    forged = AggregateSelectionOutput.model_construct(accepted=accepted)
    model = FakeDAGModel((forged,))

    with pytest.raises(AggregationInvariantError, match="(candidate|member|validated)"):
        await SemanticDAGBuilder(model, run_id="dag-run").build(memories)


@pytest.mark.asyncio
async def test_aggregate_assertion_cannot_invent_terms_or_lower_references() -> None:
    one = _session_ke("one")
    two = _session_ke("two")
    memories = (_memory("s1", (one,)), _memory("s2", (two,)))
    candidate = generate_depth1_candidates(memories)[0]
    bad_assertion = _assertion_proposal(
        (one, two), lhs=IndividualRef(term_id="person:invented", label="Invented")
    )
    proposal = _node_proposal(candidate.id, candidate.member_refs, (one, two)).model_copy(
        update={"assertions": (bad_assertion,)}
    )
    model = FakeDAGModel((AggregateSelectionOutput(accepted=(proposal,)),))

    with pytest.raises(AggregationInvariantError, match="term"):
        await SemanticDAGBuilder(model, run_id="dag-run").build(memories)

    dangling = _assertion_proposal((one, two), derived_from=("ke:missing",))
    proposal = _node_proposal(candidate.id, candidate.member_refs, (one, two)).model_copy(
        update={"assertions": (dangling,)}
    )
    model = FakeDAGModel((AggregateSelectionOutput(accepted=(proposal,)),))
    with pytest.raises(AggregationInvariantError, match="lower"):
        await SemanticDAGBuilder(model, run_id="dag-run").build(memories)

    retyped = _assertion_proposal(
        (one, two),
        lhs=OperatorRef(term_id="person:alice", label="Alice as operator"),
    )
    proposal = _node_proposal(candidate.id, candidate.member_refs, (one, two)).model_copy(
        update={"assertions": (retyped,)}
    )
    model = FakeDAGModel((AggregateSelectionOutput(accepted=(proposal,)),))
    with pytest.raises(AggregationInvariantError, match="term or operator role"):
        await SemanticDAGBuilder(model, run_id="dag-run").build(memories)


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
            "revision",
        ),
    )
    for forged, expected_error in forged_nodes:
        with pytest.raises(AggregationInvariantError, match=expected_error):
            validate_evidence_closure((forged,), known)


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
        generate_depth1_candidates((memory, _memory("s2", (second,))))


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
