from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypeVar

from pydantic import BaseModel

from ke_memory_demo.domain import (
    ConceptRef,
    IndividualRef,
    OntologyBinding,
    OntologyBindingStatus,
    OntologyRole,
    OperatorApplication,
)
from ke_memory_demo.infra.telemetry import TraceContext
from ke_memory_demo.retrieval import (
    InMemoryQueryTraceRecorder,
    QueryKEExtractor,
)


ModelT = TypeVar("ModelT", bound=BaseModel)


class _DraftModel:
    def __init__(self) -> None:
        self.calls: list[tuple[type[BaseModel], Sequence[Mapping[str, object]], TraceContext]] = []

    async def complete(
        self,
        model_type: type[ModelT],
        messages: Sequence[Mapping[str, object]],
        trace_context: TraceContext | Mapping[str, object],
    ) -> ModelT:
        assert isinstance(trace_context, TraceContext)
        self.calls.append((model_type, messages, trace_context))
        return model_type.model_validate(
            {
                "lhs": {
                    "kind": "application",
                    "operator": {"kind": "operator", "surface_form": "Before"},
                    "arguments": (
                        {"kind": "individual", "surface_form": "Alex"},
                        {"kind": "concept", "surface_form": "Launch"},
                    ),
                },
                "rhs": {"kind": "concept", "surface_form": "Action"},
                "gloss": "Alex's action before launch",
                "lifecycle": ("active", "uncertain"),
                "temporal": {},
            }
        )


class _Vocabulary:
    def __init__(self) -> None:
        self.queries: list[tuple[str, ...]] = []

    async def resolve_terms(self, surface_terms: Sequence[str]) -> list[OntologyBinding]:
        self.queries.append(tuple(surface_terms))
        bindings = {
            "Action": OntologyBinding(
                surface_form="Action",
                normalized_surface="action",
                status=OntologyBindingStatus.RESOLVED,
                document_id="term-action",
                canonical_term="Action",
                role=OntologyRole.CONCEPT,
            ),
            "Alex": OntologyBinding(
                surface_form="Alex",
                normalized_surface="alex",
                status=OntologyBindingStatus.RESOLVED,
                document_id="term-alex",
                canonical_term="Alex",
                role=OntologyRole.INDIVIDUAL,
            ),
            "Before": OntologyBinding(
                surface_form="Before",
                normalized_surface="before",
                status=OntologyBindingStatus.RESOLVED,
                document_id="op-before",
                canonical_term="before",
                role=OntologyRole.OPERATOR,
            ),
            "Launch": OntologyBinding(
                surface_form="Launch",
                normalized_surface="launch",
                status=OntologyBindingStatus.UNRESOLVED,
            ),
        }
        return [bindings[item] for item in surface_terms]


async def test_query_ke_uses_domain_expressions_ontology_resolution_and_ephemeral_trace() -> None:
    model = _DraftModel()
    vocabulary = _Vocabulary()
    trace = InMemoryQueryTraceRecorder()
    extractor = QueryKEExtractor(model, vocabulary, run_id="run-1", trace_recorder=trace)

    query_ke = await extractor.extract("What did Alex do before launch?")

    assert vocabulary.queries == [("Action", "Alex", "Before", "Launch")]
    assert isinstance(query_ke.lhs, OperatorApplication)
    assert query_ke.lhs.operator.term_id == "op-before"
    assert isinstance(query_ke.lhs.arguments[0], IndividualRef)
    assert query_ke.lhs.arguments[0].term_id == "term-alex"
    assert isinstance(query_ke.lhs.arguments[1], ConceptRef)
    assert query_ke.lhs.arguments[1].term_id.startswith("unresolved-concept:")
    assert isinstance(query_ke.rhs, ConceptRef)
    assert query_ke.rhs.term_id == "term-action"
    assert [item.normalized_surface for item in query_ke.ontology_bindings] == [
        "action",
        "alex",
        "before",
        "launch",
    ]
    assert len(trace.records) == 1
    assert trace.records[0].query_ke == query_ke
    assert len(trace.records[0].question_sha256) == 64
    assert len(trace.records[0].prompt_sha256) == 64
    assert model.calls[0][2].metadata["prompt_sha256"] == trace.records[0].prompt_sha256
