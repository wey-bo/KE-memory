from __future__ import annotations

from datetime import UTC, datetime
import hashlib

from ke_memory_demo.domain import (
    AggregateNode,
    AggregateNodeKind,
    ConceptRef,
    IndividualRef,
    KnowledgeEquation,
    Lifecycle,
    MessageSpan,
    Modality,
    OntologyBinding,
    OntologyBindingStatus,
    OperatorApplication,
    OperatorRef,
    Polarity,
    Speaker,
    TemporalMetadata,
)
from ke_memory_demo.retrieval import QueryKE, SourceFragment, SymbolicRetriever


def _ke(label: str, term_id: str) -> KnowledgeEquation:
    text = f"raw source for {label}"
    span = MessageSpan(
        message_id=f"message-{term_id}",
        start_char=0,
        end_char=len(text),
        text_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )
    return KnowledgeEquation.create(
        level="turn",
        lhs=ConceptRef(term_id=term_id, label=label),
        rhs=ConceptRef(term_id=f"value-{term_id}", label=f"value {label}"),
        gloss=f"memory about {label}",
        modality=Modality.FACT,
        polarity=Polarity.POSITIVE,
        lifecycle=Lifecycle.ACTIVE,
        speaker=Speaker.USER,
        evidence_refs=(span,),
        produced_in_run_id="run-memory",
        produced_in_stage="turn-ke-extracted",
    )


def _aggregate(aggregate_id: str, member_ref: str, depth: int) -> AggregateNode:
    return AggregateNode(
        id=aggregate_id,
        node_kind=AggregateNodeKind.EVENT_CHAIN,
        title=aggregate_id,
        summary=f"aggregate {aggregate_id}",
        member_refs=(member_ref,),
        derived_from=(member_ref,),
        confidence=0.9,
        revision="a" * 64,
        depth=depth,
    )


class _Index:
    def __init__(
        self,
        term_ke: KnowledgeEquation,
        unresolved_ke: KnowledgeEquation,
        aggregate_1: AggregateNode,
        aggregate_2: AggregateNode,
    ) -> None:
        self.term_ke = term_ke
        self.unresolved_ke = unresolved_ke
        self.aggregate_1 = aggregate_1
        self.aggregate_2 = aggregate_2
        self.calls: list[tuple[str, object]] = []

    def lookup_term_id(self, term_id: str) -> tuple[str, ...]:
        self.calls.append(("term", term_id))
        return (self.term_ke.id,) if term_id in {"term-alex", "op-before"} else ()

    def lookup_operator_id(self, operator_id: str) -> tuple[str, ...]:
        self.calls.append(("operator", operator_id))
        return (self.term_ke.id,) if operator_id == "op-before" else ()

    def lookup_unresolved_label(self, normalized_surface: str) -> tuple[str, ...]:
        self.calls.append(("unresolved", normalized_surface))
        return (self.unresolved_ke.id,) if normalized_surface == "launch" else ()

    def lookup_lifecycle(self, lifecycle: Lifecycle | str) -> tuple[str, ...]:
        value = lifecycle.value if isinstance(lifecycle, Lifecycle) else lifecycle
        self.calls.append(("lifecycle", value))
        return (self.unresolved_ke.id,) if value == "active" else ()

    def lookup_temporal(
        self,
        start: datetime | None,
        end: datetime | None,
    ) -> tuple[str, ...]:
        self.calls.append(("temporal", (start, end)))
        return (self.term_ke.id,)

    def lookup_aggregate_membership(self, member_ref: str) -> tuple[str, ...]:
        self.calls.append(("aggregate", member_ref))
        if member_ref == self.term_ke.id:
            return (self.aggregate_1.id,)
        if member_ref == self.aggregate_1.id:
            return (self.aggregate_2.id,)
        return ()


class _Records:
    def __init__(
        self,
        equations: tuple[KnowledgeEquation, ...],
        aggregates: tuple[AggregateNode, ...],
    ) -> None:
        self.equations = {item.id: item for item in equations}
        self.aggregates = {item.id: item for item in aggregates}
        self.text_by_message = {
            item.evidence_refs[0].message_id: f"raw source for {item.lhs.label}"
            for item in equations
            if isinstance(item.lhs, ConceptRef)
        }

    def get_knowledge_equation(self, record_id: str) -> KnowledgeEquation | None:
        return self.equations.get(record_id)

    def get_aggregate(self, record_id: str) -> AggregateNode | None:
        return self.aggregates.get(record_id)

    def resolve_span(self, span: MessageSpan) -> SourceFragment:
        text = self.text_by_message[span.message_id]
        return SourceFragment(
            fragment_id=f"fragment-{span.message_id}",
            text=text,
            span=span,
            source_exchange_id=f"exchange-{span.message_id}",
            source_session_id="session-1",
        )


async def test_symbolic_retrieval_uses_every_index_family_and_recursive_membership() -> None:
    term_ke = _ke("Alex", "term-alex")
    unresolved_ke = _ke("Launch", "unresolved-concept:launch")
    aggregate_1 = _aggregate("aggregate-1", term_ke.id, 1)
    aggregate_2 = _aggregate("aggregate-2", aggregate_1.id, 2)
    index = _Index(term_ke, unresolved_ke, aggregate_1, aggregate_2)
    records = _Records((term_ke, unresolved_ke), (aggregate_1, aggregate_2))
    start = datetime(2025, 1, 1, tzinfo=UTC)
    end = datetime(2025, 2, 1, tzinfo=UTC)
    query_ke = QueryKE(
        lhs=OperatorApplication(
            operator=OperatorRef(term_id="op-before", label="before"),
            arguments=(IndividualRef(term_id="term-alex", label="Alex"),),
        ),
        rhs=ConceptRef(term_id="unresolved-concept:launch", label="Launch"),
        gloss="Alex before launch",
        lifecycle=(Lifecycle.ACTIVE,),
        temporal=TemporalMetadata(valid_from=start, valid_to=end),
        ontology_bindings=(
            OntologyBinding(
                surface_form="Launch",
                normalized_surface="launch",
                status=OntologyBindingStatus.UNRESOLVED,
            ),
        ),
    )

    candidates = await SymbolicRetriever(index, records).retrieve(query_ke=query_ke)

    assert {item.candidate_id for item in candidates} == {
        term_ke.id,
        unresolved_ke.id,
        "aggregate-1",
        "aggregate-2",
    }
    assert ("term", "op-before") in index.calls
    assert ("term", "term-alex") in index.calls
    assert ("term", "unresolved-concept:launch") in index.calls
    assert ("operator", "op-before") in index.calls
    assert ("unresolved", "launch") in index.calls
    assert ("lifecycle", "active") in index.calls
    assert ("temporal", (start, end)) in index.calls
    assert ("aggregate", term_ke.id) in index.calls
    assert ("aggregate", "aggregate-1") in index.calls
    assert all("score" not in item.model_dump() for item in candidates)
    assert next(item for item in candidates if item.candidate_id == term_ke.id).source_fragments
