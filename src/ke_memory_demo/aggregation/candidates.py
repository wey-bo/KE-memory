from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ke_memory_demo.domain import (
    AggregateNode,
    AssertionRef,
    Expression,
    KnowledgeEquation,
    KnowledgeLevel,
    OperatorApplication,
    OperatorRef,
    TemporalMetadata,
    content_id,
)

from .session import SessionMemory
from .validation import (
    AggregationInvariantError,
    authenticate_knowledge_equation,
    expression_assertion_refs,
    normalize_identity,
)


NonEmptyString = Annotated[str, Field(min_length=1)]
CandidateDepth = Literal[1, 2]

SHARED_SUBJECT = "shared_subject"
SHARED_OPERATOR = "shared_operator"
EXPLICIT_REFERENCE = "explicit_reference"
TEMPORAL_ADJACENCY = "temporal_adjacency"
OVERLAPPING_MEMBERS = "overlapping_members"
EQUATION_OPERATOR_IDENTITY = "__equation__"


class _CandidateRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AggregateCandidate(_CandidateRecord):
    id: NonEmptyString
    depth: CandidateDepth
    member_refs: tuple[NonEmptyString, ...] = Field(min_length=2)
    reasons: tuple[NonEmptyString, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_candidate(self) -> AggregateCandidate:
        if self.member_refs != tuple(sorted(self.member_refs)):
            raise ValueError("candidate member refs must be sorted")
        if len(self.member_refs) != len(set(self.member_refs)):
            raise ValueError("duplicate candidate member refs are not allowed")
        if self.reasons != tuple(sorted(self.reasons)):
            raise ValueError("candidate reasons must be sorted")
        if len(self.reasons) != len(set(self.reasons)):
            raise ValueError("duplicate candidate reasons are not allowed")
        expected = _candidate_id(self.depth, self.member_refs, self.reasons)
        if self.id != expected:
            raise ValueError(f"candidate ID does not match symbolic payload: expected {expected}")
        return self


def generate_depth1_candidates(
    session_memories: Sequence[SessionMemory],
) -> tuple[AggregateCandidate, ...]:
    memories = tuple(session_memories)
    for memory in memories:
        try:
            SessionMemory.model_validate(memory.model_dump(mode="python"))
        except ValidationError as error:
            raise AggregationInvariantError(
                f"SessionMemory {memory.session_id} is not an authentic validated record"
            ) from error
    session_ids = tuple(memory.session_id for memory in memories)
    if len(session_ids) != len(set(session_ids)):
        raise AggregationInvariantError("duplicate SessionMemory session ID")

    equations: dict[str, KnowledgeEquation] = {}
    owners: dict[str, str] = {}
    for memory in sorted(memories, key=lambda item: item.session_id):
        for equation in memory.knowledge_equations:
            if equation.level is not KnowledgeLevel.SESSION:
                raise AggregationInvariantError(f"depth-1 source {equation.id} is not a Session KE")
            if equation.id in equations:
                raise AggregationInvariantError(
                    f"Session KE {equation.id} occurs in more than one SessionMemory"
                )
            authenticate_knowledge_equation(
                equation,
                label=f"SessionMemory {memory.session_id} KE {equation.id}",
            )
            equations[equation.id] = equation
            owners[equation.id] = memory.session_id

    groups: dict[tuple[str, ...], set[str]] = defaultdict(set)

    by_subject: dict[str, list[str]] = defaultdict(list)
    by_operator: dict[str, list[str]] = defaultdict(list)
    for equation_id in sorted(equations):
        equation = equations[equation_id]
        by_subject[subject_identity(equation.lhs)].append(equation_id)
        by_operator[operator_identity(equation)].append(equation_id)
    for members in by_subject.values():
        _offer_group(groups, members, SHARED_SUBJECT, owners=owners)
    for members in by_operator.values():
        _offer_group(groups, members, SHARED_OPERATOR, owners=owners)

    explicit = {
        equation_id: _ke_explicit_refs(equation) for equation_id, equation in equations.items()
    }
    for component in _connected_components(tuple(equations), explicit):
        _offer_group(groups, component, EXPLICIT_REFERENCE, owners=owners)

    _offer_temporal_adjacencies(
        groups,
        equations,
        {key: value.temporal for key, value in equations.items()},
        owners=owners,
        subjects={key: subject_identity(value.lhs) for key, value in equations.items()},
        operators={key: operator_identity(value) for key, value in equations.items()},
    )
    return _materialize_candidates(1, groups)


def generate_depth2_candidates(
    depth1_nodes: Sequence[AggregateNode],
) -> tuple[AggregateCandidate, ...]:
    nodes: dict[str, AggregateNode] = {}
    for node in depth1_nodes:
        if node.depth != 1:
            raise AggregationInvariantError("depth-2 candidates require only depth-1 nodes")
        if node.id in nodes:
            raise AggregationInvariantError(f"duplicate depth-1 node {node.id}")
        nodes[node.id] = node

    groups: dict[tuple[str, ...], set[str]] = defaultdict(set)
    by_member: dict[str, list[str]] = defaultdict(list)
    by_subject: dict[str, list[str]] = defaultdict(list)
    by_operator: dict[str, list[str]] = defaultdict(list)
    for node_id in sorted(nodes):
        node = nodes[node_id]
        for member in node.member_refs:
            by_member[member].append(node_id)
        node_subjects = {subject_identity(assertion.lhs) for assertion in node.assertions}
        node_operators = {operator_identity(assertion) for assertion in node.assertions}
        for identity in sorted(node_subjects):
            by_subject[identity].append(node_id)
        for identity in sorted(node_operators):
            by_operator[identity].append(node_id)

    for members in by_member.values():
        _offer_group(groups, members, OVERLAPPING_MEMBERS)
    for members in by_subject.values():
        _offer_group(groups, members, SHARED_SUBJECT)
    for members in by_operator.values():
        _offer_group(groups, members, SHARED_OPERATOR)

    explicit = {node_id: _node_explicit_refs(node) for node_id, node in nodes.items()}
    for component in _connected_components(tuple(nodes), explicit):
        _offer_group(groups, component, EXPLICIT_REFERENCE)

    temporals = {key: value.temporal_extent for key, value in nodes.items()}
    subjects = {
        node_id: frozenset(subject_identity(assertion.lhs) for assertion in node.assertions)
        for node_id, node in nodes.items()
    }
    operators = {
        node_id: frozenset(operator_identity(assertion) for assertion in node.assertions)
        for node_id, node in nodes.items()
    }
    _offer_temporal_adjacencies(
        groups,
        nodes,
        temporals,
        subjects=subjects,
        operators=operators,
    )
    return _materialize_candidates(2, groups)


def subject_identity(expression: Expression) -> str:
    if isinstance(expression, OperatorApplication):
        if expression.arguments:
            return _expression_identity(expression.arguments[0])
        return normalize_identity(expression.operator.term_id)
    return _expression_identity(expression)


def operator_identity(equation: KnowledgeEquation) -> str:
    return (
        _operator_in_expression(equation.rhs)
        or _operator_in_expression(equation.lhs)
        or EQUATION_OPERATOR_IDENTITY
    )


def _expression_identity(expression: Expression) -> str:
    if isinstance(expression, AssertionRef):
        return normalize_identity(expression.assertion_id)
    if isinstance(expression, OperatorApplication):
        if expression.arguments:
            return _expression_identity(expression.arguments[0])
        return normalize_identity(expression.operator.term_id)
    return normalize_identity(expression.term_id)


def _operator_in_expression(expression: Expression) -> str | None:
    if isinstance(expression, OperatorApplication):
        return normalize_identity(expression.operator.term_id)
    if isinstance(expression, OperatorRef):
        return normalize_identity(expression.term_id)
    return None


def _ke_explicit_refs(equation: KnowledgeEquation) -> set[str]:
    return {
        *equation.derived_from,
        *(
            reference
            for expression in (equation.lhs, equation.rhs)
            for reference in expression_assertion_refs(expression)
        ),
    }


def _node_explicit_refs(node: AggregateNode) -> set[str]:
    return {
        *node.derived_from,
        *(
            reference
            for assertion in node.assertions
            for expression in (assertion.lhs, assertion.rhs)
            for reference in expression_assertion_refs(expression)
        ),
    }


def _connected_components(
    record_ids: Sequence[str],
    references: dict[str, set[str]],
) -> tuple[tuple[str, ...], ...]:
    ids = tuple(sorted(record_ids))
    graph: dict[str, set[str]] = {record_id: set() for record_id in ids}
    for index, left in enumerate(ids):
        for right in ids[index + 1 :]:
            if (
                left in references[right]
                or right in references[left]
                or references[left].intersection(references[right])
            ):
                graph[left].add(right)
                graph[right].add(left)
    visited: set[str] = set()
    components: list[tuple[str, ...]] = []
    for start in ids:
        if start in visited or not graph[start]:
            continue
        stack = [start]
        component: list[str] = []
        visited.add(start)
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in sorted(graph[current], reverse=True):
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        components.append(tuple(sorted(component)))
    return tuple(components)


def _offer_group(
    groups: dict[tuple[str, ...], set[str]],
    members: Iterable[str],
    reason: str,
    *,
    owners: dict[str, str] | None = None,
) -> None:
    member_refs = tuple(sorted(set(members)))
    if len(member_refs) < 2:
        return
    if owners is not None and len({owners[member] for member in member_refs}) < 2:
        return
    groups[member_refs].add(reason)


def _offer_temporal_adjacencies(
    groups: dict[tuple[str, ...], set[str]],
    members: Iterable[str],
    temporals: dict[str, TemporalMetadata],
    *,
    owners: dict[str, str] | None = None,
    subjects: Mapping[str, str | frozenset[str]] | None = None,
    operators: Mapping[str, str | frozenset[str]] | None = None,
) -> None:
    bounded = [
        (bounds[0], bounds[1], member)
        for member in sorted(set(members))
        if (bounds := _known_interval(temporals[member])) is not None
    ]
    bounded.sort()
    for left, right in zip(bounded, bounded[1:]):
        left_id = left[2]
        right_id = right[2]
        if subjects is not None and operators is not None:
            left_subjects = _identity_set(subjects[left_id])
            right_subjects = _identity_set(subjects[right_id])
            left_operators = _identity_set(operators[left_id])
            right_operators = _identity_set(operators[right_id])
            if not (
                left_subjects.intersection(right_subjects)
                or left_operators.intersection(right_operators)
            ):
                continue
        _offer_group(groups, (left_id, right_id), TEMPORAL_ADJACENCY, owners=owners)


def _identity_set(value: str | frozenset[str]) -> frozenset[str]:
    return frozenset((value,)) if isinstance(value, str) else value


def _known_interval(temporal: TemporalMetadata) -> tuple[datetime, datetime] | None:
    if temporal.valid_from is not None or temporal.valid_to is not None:
        if temporal.valid_from is None or temporal.valid_to is None:
            return None
        return temporal.valid_from, temporal.valid_to
    point = temporal.event_time or temporal.mentioned_at
    return None if point is None else (point, point)


def _materialize_candidates(
    depth: CandidateDepth,
    groups: dict[tuple[str, ...], set[str]],
) -> tuple[AggregateCandidate, ...]:
    candidates: list[AggregateCandidate] = []
    for members, reason_set in groups.items():
        reasons = tuple(sorted(reason_set))
        candidates.append(
            AggregateCandidate(
                id=_candidate_id(depth, members, reasons),
                depth=depth,
                member_refs=members,
                reasons=reasons,
            )
        )
    return tuple(sorted(candidates, key=lambda item: item.id))


def _candidate_id(
    depth: CandidateDepth,
    member_refs: Sequence[str],
    reasons: Sequence[str],
) -> str:
    return content_id(
        "candidate",
        {
            "depth": depth,
            "member_refs": list(sorted(member_refs)),
            "reasons": list(sorted(reasons)),
        },
    )
