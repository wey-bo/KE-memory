from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import cast
import unicodedata

from pydantic import ValidationError

from ke_memory_demo.domain import (
    AssertionRef,
    ConceptRef,
    Expression,
    IndividualRef,
    KnowledgeEquation,
    MessageSpan,
    OntologyBinding,
    OntologyRole,
    OperatorApplication,
    OperatorRef,
    TemporalMetadata,
    canonical_json,
)


class AggregationInvariantError(ValueError):
    """Raised when aggregation input or model output crosses a trust boundary."""


type SpanKey = tuple[str, int, int, str]
type AtomicTerm = tuple[str, str, OntologyRole]


def span_key(span: MessageSpan) -> SpanKey:
    return (span.message_id, span.start_char, span.end_char, span.text_hash)


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
) -> tuple[str, ...]:
    used_atoms = {
        (term_id, role)
        for expression in (lhs, rhs)
        for term_id, _, role in expression_terms(expression)
    }
    offered_atoms = {
        (term_id, role)
        for record in cited_records
        for expression in (record.lhs, record.rhs)
        for term_id, _, role in expression_terms(expression)
    }
    invented = sorted(
        used_atoms.difference(offered_atoms), key=lambda item: (item[0], item[1].value)
    )
    if invented:
        raise AggregationInvariantError(
            f"{label} uses invented term or operator role {invented[0][0]} "
            f"as {invented[0][1].value}"
        )

    assertion_refs = {
        reference
        for expression in (lhs, rhs)
        for reference in expression_assertion_refs(expression)
    }
    dangling = sorted(assertion_refs.difference(cited_ids))
    if dangling:
        raise AggregationInvariantError(
            f"{label} AssertionRef does not name a cited lower record: {dangling[0]}"
        )
    return tuple(sorted(term_id for term_id, _ in used_atoms))


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
    used_term_ids: Iterable[str],
    records: Iterable[KnowledgeEquation],
) -> tuple[OntologyBinding, ...]:
    used = set(used_term_ids)
    unique: dict[bytes, OntologyBinding] = {}
    for record in records:
        atoms = tuple(
            term for expression in (record.lhs, record.rhs) for term in expression_terms(expression)
        )
        for binding in record.ontology_bindings:
            applicable = {
                term_id
                for term_id, label, _ in atoms
                if binding.document_id == term_id
                or normalize_identity(binding.normalized_surface) == normalize_identity(label)
            }
            if not applicable.intersection(used):
                continue
            key = canonical_json(binding)
            unique[key] = binding
    offered_by_term = {
        term_id
        for record in records
        for expression in (record.lhs, record.rhs)
        for term_id, _, _ in expression_terms(expression)
    }
    unbound = sorted(used.difference(offered_by_term))
    if unbound:
        raise AggregationInvariantError(
            f"ontology binding union requested unknown term ID {unbound[0]}"
        )
    return tuple(unique[key] for key in sorted(unique))


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
