from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import math
import re
from typing import Any, cast

import pytest
from pydantic import TypeAdapter, ValidationError

from ke_memory_demo.core.ids import content_id
from ke_memory_demo.core.json import JsonValue, canonical_json
from ke_memory_demo.domain.conversation import MessageSpan
from ke_memory_demo.domain.expressions import (
    ConceptRef,
    Expression,
    IndividualRef,
    OperatorApplication,
    OperatorRef,
)
from ke_memory_demo.domain.memory import (
    SCHEMA_VERSION,
    AggregateNode,
    AggregateNodeKind,
    CoverageEntry,
    CoverageStatus,
    KnowledgeEquation,
    KnowledgeLevel,
    Lifecycle,
    Modality,
    OntologyBinding,
    OntologyBindingStatus,
    OntologyRelationRef,
    OntologyRole,
    Polarity,
    Speaker,
    TemporalMetadata,
)


def _span(message_id: str = "message-1", text_hash: str = "a" * 64) -> MessageSpan:
    return MessageSpan(message_id=message_id, start_char=0, end_char=3, text_hash=text_hash)


def _lhs() -> OperatorApplication:
    return OperatorApplication(
        operator=OperatorRef(term_id="operator:likes", label="likes"),
        arguments=(IndividualRef(term_id="person:user", label="user"),),
    )


def _ke(**changes: object) -> KnowledgeEquation:
    values: dict[str, Any] = {
        "level": KnowledgeLevel.TURN,
        "lhs": _lhs(),
        "rhs": IndividualRef(term_id="drink:tea", label="tea"),
        "gloss": "The user likes tea.",
        "modality": Modality.PREFERENCE,
        "polarity": Polarity.POSITIVE,
        "lifecycle": Lifecycle.ACTIVE,
        "speaker": Speaker.USER,
        "evidence_refs": (_span(),),
        "derived_from": (),
        "confidence": 0.9,
        "produced_in_run_id": "run-1",
        "produced_in_stage": "turn-ke-extracted",
    }
    values.update(changes)
    return KnowledgeEquation.create(**values)


def test_all_memory_enums_have_exact_values() -> None:
    assert [item.value for item in KnowledgeLevel] == ["turn", "session", "aggregate"]
    assert [item.value for item in Modality] == [
        "fact",
        "belief",
        "preference",
        "goal",
        "plan",
        "instruction",
        "hypothesis",
        "question",
    ]
    assert [item.value for item in Polarity] == ["positive", "negative", "unknown"]
    assert [item.value for item in Lifecycle] == [
        "active",
        "superseded",
        "contradicted",
        "retracted",
        "uncertain",
    ]
    assert [item.value for item in Speaker] == ["user", "assistant", "tool", "derived"]
    assert [item.value for item in CoverageStatus] == [
        "represented",
        "context_only",
        "non_memory",
        "extraction_failed",
    ]
    assert [item.value for item in AggregateNodeKind] == [
        "Task",
        "Project",
        "Topic",
        "Goal",
        "EventChain",
        "EntityTimeline",
        "Decision",
        "State",
        "Constraint",
        "Preference",
        "Procedure",
        "Pattern",
        "Issue",
        "Other",
    ]


def test_recursive_expression_union_round_trips_and_uses_tuples() -> None:
    adapter: TypeAdapter[Expression] = TypeAdapter(Expression)
    raw = {
        "kind": "application",
        "operator": {"kind": "operator", "term_id": "op:believes", "label": "believes"},
        "arguments": [
            {"kind": "individual", "term_id": "person:user", "label": "user"},
            {
                "kind": "application",
                "operator": {"kind": "operator", "term_id": "op:likes", "label": "likes"},
                "arguments": [{"kind": "individual", "term_id": "drink:tea", "label": "tea"}],
            },
        ],
    }

    expression = adapter.validate_python(raw)
    round_tripped = adapter.validate_json(adapter.dump_json(expression))

    assert isinstance(expression, OperatorApplication)
    assert isinstance(expression.arguments, tuple)
    assert isinstance(expression.arguments[1], OperatorApplication)
    assert isinstance(expression.arguments[1].arguments, tuple)
    assert round_tripped == expression


def test_expression_models_are_frozen_and_reject_extra_or_empty_labels() -> None:
    expression = ConceptRef(term_id="concept:drink", label="drink")

    with pytest.raises(ValidationError):
        expression.label = "changed"
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ConceptRef.model_validate(
            {"kind": "concept", "term_id": "concept:drink", "label": "drink", "extra": 1}
        )
    with pytest.raises(ValidationError):
        OperatorRef(term_id="operator:likes", label="")


def test_canonical_json_is_utf8_sorted_and_has_no_insignificant_whitespace() -> None:
    first: JsonValue = {"z": [2, 3], "a": "\u8336"}
    second: JsonValue = {"a": "\u8336", "z": [2, 3]}

    first_bytes = canonical_json(first)

    assert first_bytes == canonical_json(second)
    assert first_bytes == b'{"a":"\xe8\x8c\xb6","z":[2,3]}'


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_canonical_json_rejects_non_finite_numbers(value: float) -> None:
    with pytest.raises(ValueError):
        canonical_json(value)


def test_canonical_json_rejects_unsupported_values_and_non_string_keys() -> None:
    with pytest.raises(TypeError):
        canonical_json(cast(JsonValue, {1, 2}))
    with pytest.raises(TypeError, match="keys"):
        canonical_json(cast(JsonValue, {1: "not-json"}))


def test_content_id_is_stable_and_rejects_an_empty_prefix() -> None:
    first = content_id("test", {"right": 2, "left": 1})
    second = content_id("test", {"left": 1, "right": 2})

    assert first == second
    assert re.fullmatch(r"test:[0-9a-f]{64}", first)
    with pytest.raises(ValueError, match="prefix"):
        content_id("", {"value": 1})


def test_temporal_metadata_requires_aware_datetimes_and_ordered_validity() -> None:
    start = datetime(2026, 7, 15, 8, 0, tzinfo=UTC)
    temporal = TemporalMetadata(
        mentioned_at=start,
        event_time=start + timedelta(hours=1),
        valid_from=start,
        valid_to=start + timedelta(days=1),
    )

    assert temporal.valid_to is not None and temporal.valid_to > start
    with pytest.raises(ValidationError, match="timezone"):
        TemporalMetadata(event_time=datetime(2026, 7, 15, 8, 0))
    with pytest.raises(ValidationError, match="valid_to"):
        TemporalMetadata(valid_from=start, valid_to=start - timedelta(seconds=1))


def test_ontology_binding_enforces_resolution_states_and_immutable_relations() -> None:
    binding = OntologyBinding.model_validate(
        {
            "surface_form": "likes",
            "normalized_surface": "likes",
            "status": "resolved",
            "document_id": "es-doc-1",
            "canonical_term": "likes",
            "role": "operator",
            "source_type": "relation",
            "matched_alias": "likes",
            "aliases": ["prefers"],
            "relations": [{"relation_type": "inverse", "target_id": "operator:liked-by"}],
        }
    )

    assert binding.status is OntologyBindingStatus.RESOLVED
    assert binding.role is OntologyRole.OPERATOR
    assert binding.aliases == ("prefers",)
    assert binding.relations == (
        OntologyRelationRef(relation_type="inverse", target_id="operator:liked-by"),
    )

    with pytest.raises(ValidationError, match="resolved"):
        OntologyBinding(
            surface_form="likes",
            normalized_surface="likes",
            status=OntologyBindingStatus.RESOLVED,
        )
    with pytest.raises(ValidationError, match="unresolved"):
        OntologyBinding(
            surface_form="unknown",
            normalized_surface="unknown",
            status=OntologyBindingStatus.UNRESOLVED,
            document_id="unexpected",
        )
    with pytest.raises(ValidationError, match="unresolved_role"):
        OntologyBinding(
            surface_form="item",
            normalized_surface="item",
            status=OntologyBindingStatus.UNRESOLVED_ROLE,
            document_id="es-doc-2",
            canonical_term="item",
            role=OntologyRole.CONCEPT,
        )


def test_ontology_binding_rejects_duplicate_relation_refs() -> None:
    relation = OntologyRelationRef(relation_type="parent", target_id="concept:drink")

    with pytest.raises(ValidationError, match="duplicate"):
        OntologyBinding(
            surface_form="tea",
            normalized_surface="tea",
            status=OntologyBindingStatus.UNRESOLVED,
            relations=(relation, relation),
        )


def test_ke_id_is_stable_but_revision_changes_with_lifecycle() -> None:
    ke = _ke()

    revised = ke.transition(Lifecycle.SUPERSEDED)

    assert revised.id == ke.id
    assert revised.lifecycle is Lifecycle.SUPERSEDED
    assert revised.revision != ke.revision
    assert ke.lifecycle is Lifecycle.ACTIVE


def test_ke_logical_id_includes_only_the_exact_logical_payload() -> None:
    original = _ke()
    changed_non_logical_fields = _ke(
        gloss="A different gloss.",
        lifecycle=Lifecycle.UNCERTAIN,
        temporal=TemporalMetadata(event_time=datetime(2026, 7, 15, tzinfo=UTC)),
        ontology_bindings=(
            OntologyBinding(
                surface_form="tea",
                normalized_surface="tea",
                status=OntologyBindingStatus.UNRESOLVED,
            ),
        ),
        contradicts=("ke:conflict",),
        supersedes=("ke:prior",),
        confidence=0.1,
        produced_in_run_id="run-2",
        produced_in_stage="session-induced",
    )

    assert changed_non_logical_fields.id == original.id
    assert changed_non_logical_fields.revision != original.revision
    assert _ke(evidence_refs=(_span("message-2"),)).id != original.id
    assert _ke(derived_from=("ke:source",)).id != original.id


def test_ke_id_is_independent_of_expression_mapping_insertion_order() -> None:
    adapter: TypeAdapter[Expression] = TypeAdapter(Expression)
    first = adapter.validate_python({"kind": "individual", "term_id": "drink:tea", "label": "tea"})
    second = adapter.validate_python({"label": "tea", "term_id": "drink:tea", "kind": "individual"})

    assert _ke(rhs=first).id == _ke(rhs=second).id


def test_ke_revision_is_sha256_of_complete_canonical_record_except_revision() -> None:
    ke = _ke()
    revision_payload = ke.model_dump(mode="json", exclude={"revision"})

    expected = hashlib.sha256(canonical_json(revision_payload)).hexdigest()

    assert ke.schema_version == SCHEMA_VERSION == "ke-memory/v1"
    assert ke.revision == expected
    assert re.fullmatch(r"[0-9a-f]{64}", ke.revision)


def test_ke_rejects_tampered_logical_id_or_revision_on_deserialization() -> None:
    dumped = _ke().model_dump(mode="json")

    with pytest.raises(ValidationError, match="logical ID"):
        KnowledgeEquation.model_validate({**dumped, "id": f"ke:{'f' * 64}"})
    with pytest.raises(ValidationError, match="revision"):
        KnowledgeEquation.model_validate({**dumped, "revision": "f" * 64})


def test_ke_references_are_tuples_and_reject_duplicates() -> None:
    ke = _ke(derived_from=("ke:a", "ke:b"), contradicts=("ke:c",), supersedes=("ke:d",))

    assert isinstance(ke.evidence_refs, tuple)
    assert isinstance(ke.derived_from, tuple)
    assert isinstance(ke.contradicts, tuple)
    assert isinstance(ke.supersedes, tuple)
    with pytest.raises(ValidationError, match="duplicate"):
        _ke(derived_from=("ke:a", "ke:a"))
    with pytest.raises(ValidationError, match="duplicate"):
        _ke(evidence_refs=(_span(), _span()))


@pytest.mark.parametrize("confidence", [-0.01, 1.01, math.nan])
def test_ke_confidence_must_be_finite_and_in_range(confidence: float) -> None:
    with pytest.raises(ValidationError):
        _ke(confidence=confidence)


def test_ke_rejects_extra_fields_and_wrong_schema_versions() -> None:
    dumped = _ke().model_dump(mode="json")

    with pytest.raises(ValidationError, match="extra_forbidden"):
        KnowledgeEquation.model_validate({**dumped, "unexpected": True})
    with pytest.raises(ValidationError):
        KnowledgeEquation.model_validate({**dumped, "schema_version": "ke-memory/v2"})


def test_coverage_entry_validates_offsets_ids_and_tuple_conversion() -> None:
    entry = CoverageEntry.model_validate(
        {
            "message_id": "message-1",
            "start_char": 0,
            "end_char": 3,
            "status": "represented",
            "ke_ids": ["ke:one", "ke:two"],
        }
    )

    assert entry.ke_ids == ("ke:one", "ke:two")
    with pytest.raises(ValidationError):
        CoverageEntry(
            message_id="message-1",
            start_char=1,
            end_char=1,
            status=CoverageStatus.CONTEXT_ONLY,
        )
    with pytest.raises(ValidationError, match="duplicate"):
        CoverageEntry(
            message_id="message-1",
            start_char=0,
            end_char=1,
            status=CoverageStatus.REPRESENTED,
            ke_ids=("ke:one", "ke:one"),
        )


def test_aggregate_node_exposes_typed_depth_and_immutable_evidence_closure() -> None:
    assertion = _ke(level=KnowledgeLevel.AGGREGATE, evidence_refs=(), derived_from=("ke:turn",))
    node = AggregateNode.model_validate(
        {
            "id": "aggregate:tea-preferences",
            "node_kind": "Preference",
            "title": "Tea preferences",
            "summary": "The user's tea preferences.",
            "assertions": [assertion],
            "member_refs": ["ke:turn"],
            "derived_from": ["session:one"],
            "evidence_closure": [_span()],
            "temporal_extent": {},
            "confidence": 0.8,
            "revision": "b" * 64,
            "depth": 2,
        }
    )

    assert node.node_kind is AggregateNodeKind.PREFERENCE
    assert node.depth == 2
    assert isinstance(node.assertions, tuple)
    assert isinstance(node.member_refs, tuple)
    assert isinstance(node.derived_from, tuple)
    assert isinstance(node.evidence_closure, tuple)
    with pytest.raises(ValidationError):
        AggregateNode.model_validate({**node.model_dump(), "confidence": 1.1})
    with pytest.raises(ValidationError, match="duplicate"):
        AggregateNode.model_validate({**node.model_dump(), "member_refs": ["ke:turn", "ke:turn"]})
