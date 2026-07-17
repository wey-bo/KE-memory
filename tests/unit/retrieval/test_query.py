from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import TypeGuard, TypeVar, cast

import pytest
from pydantic import BaseModel, ConfigDict

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
    QueryInvariantError,
    QueryKEExtractor,
)


ModelT = TypeVar("ModelT", bound=BaseModel)
_QUESTION = "Did Alex plan before launch while active on 2025-01-02?"


def _span(surface: str) -> dict[str, int]:
    start = _QUESTION.index(surface)
    return {"start_char": start, "end_char": start + len(surface)}


def _valid_draft() -> dict[str, object]:
    return {
        "lhs": {
            "kind": "application",
            "operator": {
                "kind": "operator",
                "surface_form": "before",
                "grounding_span": _span("before"),
            },
            "arguments": (
                {
                    "kind": "individual",
                    "surface_form": "Alex",
                    "grounding_span": _span("Alex"),
                },
                {
                    "kind": "application",
                    "operator": {
                        "kind": "operator",
                        "surface_form": "plan",
                        "grounding_span": _span("plan"),
                    },
                    "arguments": (
                        {
                            "kind": "concept",
                            "surface_form": "launch",
                            "grounding_span": _span("launch"),
                        },
                    ),
                },
            ),
        },
        "rhs": {
            "kind": "concept",
            "surface_form": "active",
            "grounding_span": _span("active"),
        },
        "gloss": "Alex plans a launch before the active date",
        "lifecycle": ("active",),
        "lifecycle_groundings": ({"value": "active", "grounding_span": _span("active")},),
        "temporal": {"event_time": "2025-01-02T00:00:00Z"},
        "temporal_groundings": ({"field": "event_time", "grounding_span": _span("2025-01-02")},),
    }


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
        return model_type.model_validate(_valid_draft())


class _UntrustedOutput(BaseModel):
    model_config = ConfigDict(extra="allow")


def _is_object_tuple(value: object) -> TypeGuard[tuple[object, ...]]:
    return isinstance(value, tuple)


def _is_string_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict)


class _InvalidDraftModel:
    def __init__(self, path: tuple[str | int, ...], value: object) -> None:
        self._path = path
        self._value = value

    async def complete(
        self,
        model_type: type[ModelT],
        messages: Sequence[Mapping[str, object]],
        trace_context: TraceContext | Mapping[str, object],
    ) -> ModelT:
        del model_type, messages, trace_context
        payload = deepcopy(_valid_draft())
        target: object = payload
        for key in self._path[:-1]:
            if isinstance(key, int):
                if not _is_object_tuple(target):
                    raise AssertionError("integer mutation path requires a tuple")
                target = target[key]
            else:
                if not _is_string_object_dict(target):
                    raise AssertionError("string mutation path requires a mapping")
                target = target[key]
        final_key = self._path[-1]
        if not isinstance(final_key, str):
            raise AssertionError("test mutation must end at a mapping field")
        if not _is_string_object_dict(target):
            raise AssertionError("test mutation target must be a mapping")
        target[final_key] = self._value
        return cast(ModelT, _UntrustedOutput.model_validate(payload))


class _Vocabulary:
    def __init__(self) -> None:
        self.queries: list[tuple[str, ...]] = []

    async def resolve_terms(self, surface_terms: Sequence[str]) -> list[OntologyBinding]:
        self.queries.append(tuple(surface_terms))
        bindings = {
            "active": OntologyBinding(
                surface_form="active",
                normalized_surface="active",
                status=OntologyBindingStatus.RESOLVED,
                document_id="term-active",
                canonical_term="active",
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
            "before": OntologyBinding(
                surface_form="before",
                normalized_surface="before",
                status=OntologyBindingStatus.RESOLVED,
                document_id="op-before",
                canonical_term="before",
                role=OntologyRole.OPERATOR,
            ),
            "launch": OntologyBinding(
                surface_form="launch",
                normalized_surface="launch",
                status=OntologyBindingStatus.UNRESOLVED,
            ),
            "plan": OntologyBinding(
                surface_form="plan",
                normalized_surface="plan",
                status=OntologyBindingStatus.RESOLVED,
                document_id="op-plan",
                canonical_term="plan",
                role=OntologyRole.OPERATOR,
            ),
        }
        return [bindings[item] for item in surface_terms]


async def test_query_ke_uses_domain_expressions_ontology_resolution_and_ephemeral_trace() -> None:
    model = _DraftModel()
    vocabulary = _Vocabulary()
    trace = InMemoryQueryTraceRecorder()
    extractor = QueryKEExtractor(model, vocabulary, run_id="run-1", trace_recorder=trace)

    query_ke = await extractor.extract(_QUESTION)

    assert vocabulary.queries == [("active", "Alex", "before", "launch", "plan")]
    assert isinstance(query_ke.lhs, OperatorApplication)
    assert query_ke.lhs.operator.term_id == "op-before"
    assert isinstance(query_ke.lhs.arguments[0], IndividualRef)
    assert query_ke.lhs.arguments[0].term_id == "term-alex"
    assert isinstance(query_ke.lhs.arguments[1], OperatorApplication)
    assert query_ke.lhs.arguments[1].operator.term_id == "op-plan"
    assert isinstance(query_ke.lhs.arguments[1].arguments[0], ConceptRef)
    assert query_ke.lhs.arguments[1].arguments[0].term_id.startswith("unresolved-concept:")
    assert isinstance(query_ke.rhs, ConceptRef)
    assert query_ke.rhs.term_id == "term-active"
    assert [item.normalized_surface for item in query_ke.ontology_bindings] == [
        "alex",
        "active",
        "before",
        "plan",
        "launch",
    ]
    assert [item.surface_form for item in query_ke.surface_groundings] == [
        "before",
        "Alex",
        "plan",
        "launch",
        "active",
    ]
    assert query_ke.lifecycle_groundings[0].value is query_ke.lifecycle[0]
    assert query_ke.temporal_groundings[0].field == "event_time"
    assert len(trace.records) == 1
    assert trace.records[0].query_ke == query_ke
    assert len(trace.records[0].question_sha256) == 64
    assert len(trace.records[0].prompt_sha256) == 64
    assert model.calls[0][2].metadata["prompt_sha256"] == trace.records[0].prompt_sha256


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        pytest.param(
            ("lhs", "arguments", 0, "grounding_span"),
            {"start_char": 4, "end_char": 999},
            "outside question",
            id="out-of-bounds-atom",
        ),
        pytest.param(
            ("lhs", "arguments", 0, "surface_form"),
            "ALEX",
            "exact question substring",
            id="case-changed-surface",
        ),
        pytest.param(
            ("lhs", "arguments", 0, "surface_form"),
            "Jordan",
            "exact question substring",
            id="invented-surface",
        ),
        pytest.param(
            ("lifecycle_groundings",),
            (),
            "lifecycle.*grounding",
            id="ungrounded-lifecycle",
        ),
        pytest.param(
            ("temporal_groundings",),
            (),
            "temporal.*grounding",
            id="ungrounded-temporal",
        ),
    ],
)
async def test_query_ke_rejects_invalid_or_missing_question_grounding(
    path: tuple[str | int, ...],
    value: object,
    message: str,
) -> None:
    with pytest.raises(QueryInvariantError, match=message):
        await QueryKEExtractor(
            _InvalidDraftModel(path, value), _Vocabulary(), run_id="run-1"
        ).extract(_QUESTION)
