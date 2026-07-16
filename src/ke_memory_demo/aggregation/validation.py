from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import cast
import unicodedata

from pydantic import BaseModel, ValidationError

from ke_memory_demo.domain import (
    AssertionRef,
    ConceptRef,
    Expression,
    IndividualRef,
    KnowledgeEquation,
    KnowledgeLevel,
    MessageSpan,
    OntologyBinding,
    OntologyBindingStatus,
    OntologyRole,
    OperatorApplication,
    OperatorRef,
    TemporalMetadata,
    canonical_json,
    content_id,
)


class AggregationInvariantError(ValueError):
    """Raised when aggregation input or model output crosses a trust boundary."""


type SpanKey = tuple[str, int, int, str]
type AtomicTerm = tuple[str, str, OntologyRole]


def span_key(span: MessageSpan) -> SpanKey:
    return (span.message_id, span.start_char, span.end_char, span.text_hash)


def same_runtime_shape(value: object, validated: object) -> bool:
    if type(value) is not type(validated):
        return False
    if isinstance(validated, BaseModel):
        return all(
            same_runtime_shape(getattr(value, field), getattr(validated, field))
            for field in type(validated).model_fields
        )
    if isinstance(validated, tuple):
        raw_tuple = cast(tuple[object, ...], value)
        validated_tuple = cast(tuple[object, ...], validated)
        return len(raw_tuple) == len(validated_tuple) and all(
            same_runtime_shape(raw_item, validated_item)
            for raw_item, validated_item in zip(
                raw_tuple,
                validated_tuple,
                strict=True,
            )
        )
    return True


def sorted_unique_spans(spans: Iterable[MessageSpan]) -> tuple[MessageSpan, ...]:
    unique = {span_key(span): span for span in spans}
    return tuple(unique[key] for key in sorted(unique))


def expression_terms(expression: Expression) -> tuple[AtomicTerm, ...]:
    if isinstance(expression, ConceptRef):
        return ((expression.term_id, expression.label, OntologyRole.CONCEPT),)
    if isinstance(expression, IndividualRef):
        return ((expression.term_id, expression.label, OntologyRole.INDIVIDUAL),)
    if isinstance(expression, OperatorRef):
        return ((expression.term_id, expression.label, OntologyRole.OPERATOR),)
    if isinstance(expression, AssertionRef):
        return ()
    return (
        (expression.operator.term_id, expression.operator.label, OntologyRole.OPERATOR),
        *(term for argument in expression.arguments for term in expression_terms(argument)),
    )


def expression_assertion_refs(expression: Expression) -> tuple[str, ...]:
    if isinstance(expression, AssertionRef):
        return (expression.assertion_id,)
    if isinstance(expression, OperatorApplication):
        return tuple(
            reference
            for argument in expression.arguments
            for reference in expression_assertion_refs(argument)
        )
    return ()


def validate_expression_authority(
    lhs: Expression,
    rhs: Expression,
    cited_records: Sequence[KnowledgeEquation],
    cited_ids: Sequence[str],
    *,
    label: str,
    allowed_assertion_ids: Iterable[str] | None = None,
) -> tuple[AtomicTerm, ...]:
    used_atoms = {atom for expression in (lhs, rhs) for atom in expression_terms(expression)}
    offered_atoms = {
        atom
        for record in cited_records
        for expression in (record.lhs, record.rhs)
        for atom in expression_terms(expression)
    }
    invented = sorted(
        used_atoms.difference(offered_atoms),
        key=lambda item: (item[0], normalize_identity(item[1]), item[2].value),
    )
    if invented:
        raise AggregationInvariantError(
            f"{label} uses invented term or operator role {invented[0][0]} "
            f"as {invented[0][2].value}"
        )

    assertion_refs = {
        reference
        for expression in (lhs, rhs)
        for reference in expression_assertion_refs(expression)
    }
    allowed_refs = set(cited_ids if allowed_assertion_ids is None else allowed_assertion_ids)
    dangling = sorted(assertion_refs.difference(allowed_refs))
    if dangling:
        raise AggregationInvariantError(
            f"{label} AssertionRef does not name a cited lower KnowledgeEquation: {dangling[0]}"
        )
    return tuple(
        sorted(
            used_atoms,
            key=lambda item: (item[0], normalize_identity(item[1]), item[2].value),
        )
    )


def evidence_union(records: Iterable[KnowledgeEquation]) -> tuple[MessageSpan, ...]:
    return sorted_unique_spans(span for record in records for span in record.evidence_refs)


def temporal_envelope(temporals: Iterable[TemporalMetadata]) -> TemporalMetadata:
    intervals: list[tuple[datetime | None, datetime | None]] = []
    for temporal in temporals:
        if temporal.valid_from is not None or temporal.valid_to is not None:
            intervals.append((temporal.valid_from, temporal.valid_to))
            continue
        point = temporal.event_time or temporal.mentioned_at
        if point is not None:
            intervals.append((point, point))

    if not intervals:
        return TemporalMetadata()
    lower = (
        None
        if any(start is None for start, _ in intervals)
        else min(cast(datetime, start) for start, _ in intervals)
    )
    upper = (
        None
        if any(end is None for _, end in intervals)
        else max(cast(datetime, end) for _, end in intervals)
    )
    return TemporalMetadata(valid_from=lower, valid_to=upper)


def ontology_binding_union(
    used_atoms: Iterable[AtomicTerm],
    records: Iterable[KnowledgeEquation],
) -> tuple[OntologyBinding, ...]:
    used = set(used_atoms)
    unique: dict[bytes, OntologyBinding] = {}
    for record in records:
        record_atoms = {
            term for expression in (record.lhs, record.rhs) for term in expression_terms(expression)
        }
        applicable_atoms = used.intersection(record_atoms)
        for binding in record.ontology_bindings:
            if not any(_binding_applies_to_atom(binding, atom) for atom in applicable_atoms):
                continue
            key = canonical_json(binding)
            unique[key] = binding
    return tuple(unique[key] for key in sorted(unique))


def _binding_applies_to_atom(binding: OntologyBinding, atom: AtomicTerm) -> bool:
    term_id, label, role = atom
    if binding.status is OntologyBindingStatus.RESOLVED:
        return binding.document_id == term_id and binding.role is role

    normalized_surface = normalize_identity(binding.normalized_surface)
    if normalize_identity(binding.surface_form) != normalized_surface:
        return False
    return normalize_identity(label) == normalized_surface and term_id == content_id(
        f"unresolved-{role.value}", normalized_surface
    )


def authenticate_knowledge_equation(
    equation: KnowledgeEquation,
    *,
    label: str,
) -> None:
    try:
        KnowledgeEquation.model_validate(equation.model_dump(mode="python"))
    except ValidationError as error:
        detail = "revision" if "revision" in str(error) else "identity"
        raise AggregationInvariantError(f"{label} has an invalid {detail}") from error


def validate_global_turn_kes(
    turn_kes: Mapping[str, KnowledgeEquation] | Sequence[KnowledgeEquation],
) -> dict[str, KnowledgeEquation]:
    records = records_by_id(turn_kes, label="source Turn KE")
    for equation in records.values():
        authenticate_knowledge_equation(equation, label=f"source Turn KE {equation.id}")
        if equation.level is not KnowledgeLevel.TURN:
            raise AggregationInvariantError(f"source Turn KE {equation.id} is not a Turn-level KE")

    record_ids = set(records)
    for equation in records.values():
        for field, references in (
            ("derived_from", equation.derived_from),
            ("contradicts", equation.contradicts),
            ("supersedes", equation.supersedes),
        ):
            if equation.id in references:
                raise AggregationInvariantError(
                    f"source Turn KE {equation.id} {field} must not reference itself"
                )
            missing = sorted(set(references).difference(record_ids))
            if missing:
                raise AggregationInvariantError(
                    f"source Turn KE {equation.id} {field} does not name a global "
                    f"Turn-level KE: {missing[0]}"
                )
    return records


def validate_knowledge_equation_relations(
    equation: KnowledgeEquation,
    allowed_ids: set[str] | frozenset[str],
    *,
    label: str,
) -> None:
    for field, references in (
        ("contradicts", equation.contradicts),
        ("supersedes", equation.supersedes),
    ):
        invalid = sorted(set(references).difference(allowed_ids))
        if invalid:
            raise AggregationInvariantError(
                f"{label} {field} does not name a lower KnowledgeEquation: {invalid[0]}"
            )


def normalize_identity(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.split()).casefold()


def records_by_id(
    records: Mapping[str, KnowledgeEquation] | Sequence[KnowledgeEquation],
    *,
    label: str,
) -> dict[str, KnowledgeEquation]:
    if isinstance(records, Mapping):
        result = dict(records)
        mismatched = sorted(key for key, value in result.items() if key != value.id)
        if mismatched:
            raise AggregationInvariantError(f"{label} mapping key does not match record ID")
    else:
        result = {record.id: record for record in records}
        if len(result) != len(records):
            raise AggregationInvariantError(f"duplicate {label} logical ID")
    revisions = tuple(record.revision for record in result.values())
    if len(revisions) != len(set(revisions)):
        raise AggregationInvariantError(f"duplicate {label} revision")
    return result
