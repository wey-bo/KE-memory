from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
import hashlib
from pathlib import Path
from typing import Annotated, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ke_memory_demo.core.json import JsonObject, JsonValue, canonical_json
from ke_memory_demo.domain import (
    SCHEMA_VERSION,
    AggregateNode,
    AggregateNodeKind,
    Expression,
    KnowledgeEquation,
    KnowledgeLevel,
    Lifecycle,
    MessageSpan,
    Modality,
    Polarity,
    Speaker,
    TemporalMetadata,
    content_id,
)
from ke_memory_demo.infra.telemetry import TraceContext

from .candidates import (
    AggregateCandidate,
    generate_depth1_candidates,
    generate_depth2_candidates,
)
from .session import (
    SessionMemory,
    StructuredCompletionClient,
    validate_session_memory_shape,
)
from .validation import (
    AggregationInvariantError,
    authenticate_knowledge_equation,
    evidence_union,
    expression_assertion_refs,
    ontology_binding_union,
    records_by_id,
    same_runtime_shape,
    sorted_unique_spans,
    temporal_envelope,
    validate_expression_authority,
    validate_knowledge_equation_relations,
)


SEMANTIC_DAG_STAGE = "semantic-dag-built"
_PROMPT_ROOT = Path(__file__).resolve().parents[3] / "prompts"

NonEmptyString = Annotated[str, Field(min_length=1)]
Confidence = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
NodeDepth = Literal[1, 2]


class _DAGRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AggregateAssertionProposal(_DAGRecord):
    key: NonEmptyString
    lhs: Expression
    rhs: Expression
    gloss: NonEmptyString
    modality: Modality
    polarity: Polarity
    lifecycle: Literal["active", "uncertain"]
    confidence: Confidence
    derived_from: tuple[NonEmptyString, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_proposal(self) -> AggregateAssertionProposal:
        _reject_duplicates(self.derived_from, "aggregate assertion lower refs")
        return self


class AggregateNodeProposal(_DAGRecord):
    candidate_id: NonEmptyString
    depth: NodeDepth
    member_refs: tuple[NonEmptyString, ...] = Field(min_length=2)
    node_kind: AggregateNodeKind
    title: NonEmptyString
    summary: NonEmptyString
    confidence: Confidence
    assertions: tuple[AggregateAssertionProposal, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_proposal(self) -> AggregateNodeProposal:
        _reject_duplicates(self.member_refs, "aggregate proposal member refs")
        _reject_duplicates(
            tuple(item.key for item in self.assertions),
            "aggregate assertion proposal keys",
        )
        return self


class AggregateSelectionOutput(_DAGRecord):
    accepted: tuple[AggregateNodeProposal, ...] = ()

    @model_validator(mode="after")
    def _validate_output(self) -> AggregateSelectionOutput:
        _reject_duplicates(
            tuple(item.candidate_id for item in self.accepted),
            "accepted candidate IDs",
        )
        return self


class SemanticDAG(_DAGRecord):
    nodes: tuple[AggregateNode, ...] = ()

    @property
    def max_depth(self) -> int:
        return max((node.depth for node in self.nodes), default=0)


def create_aggregate_node(
    *,
    node_kind: AggregateNodeKind | str,
    title: str,
    summary: str,
    assertions: Sequence[KnowledgeEquation],
    member_refs: Sequence[str],
    derived_from: Sequence[str],
    evidence_closure: Sequence[MessageSpan],
    temporal_extent: TemporalMetadata | None,
    confidence: float,
    depth: int,
) -> AggregateNode:
    if depth not in (1, 2):
        raise AggregationInvariantError("aggregate node depth must be 1 or 2")
    if not assertions:
        raise AggregationInvariantError("aggregate node requires at least one assertion")
    if len(set(member_refs)) < 2:
        raise AggregationInvariantError("aggregate node requires at least two unique members")
    kind = AggregateNodeKind(node_kind)
    members = tuple(sorted(member_refs))
    lower_refs = tuple(sorted(derived_from))
    assertion_records = tuple(sorted(assertions, key=lambda item: item.id))
    assertion_ids = tuple(item.id for item in assertion_records)
    assertion_revisions = tuple(item.revision for item in assertion_records)
    if len(assertion_ids) != len(set(assertion_ids)):
        raise AggregationInvariantError("duplicate aggregate assertion logical ID")
    if len(assertion_revisions) != len(set(assertion_revisions)):
        raise AggregationInvariantError("duplicate aggregate assertion revision")
    for assertion in assertion_records:
        authenticate_knowledge_equation(
            assertion,
            label=f"aggregate assertion {assertion.id}",
        )
        if assertion.level is not KnowledgeLevel.AGGREGATE:
            raise AggregationInvariantError("aggregate node assertion has the wrong level")
        if assertion.speaker is not Speaker.DERIVED:
            raise AggregationInvariantError("aggregate node assertion must have derived speaker")
        if assertion.lifecycle not in (Lifecycle.ACTIVE, Lifecycle.UNCERTAIN):
            raise AggregationInvariantError("aggregate node assertion has an invalid lifecycle")
        if assertion.produced_in_stage != SEMANTIC_DAG_STAGE:
            raise AggregationInvariantError("aggregate node assertion has the wrong stage")
        invalid_assertion_refs = sorted(
            reference
            for expression in (assertion.lhs, assertion.rhs)
            for reference in expression_assertion_refs(expression)
            if not reference.startswith("ke:")
        )
        if invalid_assertion_refs:
            raise AggregationInvariantError(
                "aggregate assertion AssertionRef must name a KnowledgeEquation"
            )
    assertion_lower_refs = {
        reference for assertion in assertion_records for reference in assertion.derived_from
    }
    if set(lower_refs) != assertion_lower_refs:
        raise AggregationInvariantError(
            "node derived_from is not the exact aggregate assertion reference union"
        )
    evidence = sorted_unique_spans(evidence_closure)
    logical_payload = cast(
        JsonValue,
        {
            "schema_version": SCHEMA_VERSION,
            "node_kind": kind.value,
            "member_refs": list(members),
            "derived_from": list(lower_refs),
            "assertion_ids": list(assertion_ids),
            "depth": depth,
        },
    )
    draft = AggregateNode(
        id=content_id("aggregate", logical_payload),
        node_kind=kind,
        title=title,
        summary=summary,
        assertions=assertion_records,
        member_refs=members,
        derived_from=lower_refs,
        evidence_closure=evidence,
        temporal_extent=temporal_extent or TemporalMetadata(),
        confidence=confidence,
        revision="0" * 64,
        depth=depth,
    )
    revision_payload = cast(JsonValue, draft.model_dump(mode="json", exclude={"revision"}))
    return draft.model_copy(
        update={"revision": hashlib.sha256(canonical_json(revision_payload)).hexdigest()}
    )


class SemanticDAGBuilder:
    def __init__(
        self,
        model: StructuredCompletionClient,
        turn_kes: Mapping[str, KnowledgeEquation],
        *,
        run_id: str,
    ) -> None:
        if not run_id:
            raise ValueError("run_id must not be empty")
        self._model = model
        self._turn_kes = dict(turn_kes)
        self._run_id = run_id

    async def build(self, session_memories: Sequence[SessionMemory]) -> SemanticDAG:
        memories = tuple(validate_session_memory_shape(memory) for memory in session_memories)
        depth1_candidates = generate_depth1_candidates(memories, self._turn_kes)
        known_kes = {
            equation.id: equation for memory in memories for equation in memory.knowledge_equations
        }
        if not depth1_candidates:
            return SemanticDAG(nodes=())

        depth1_output = await self._complete(depth1_candidates, known_kes, 1)
        depth1 = self._accept_depth1(depth1_candidates, depth1_output, known_kes)
        if not depth1:
            return SemanticDAG(nodes=())

        depth2_candidates = generate_depth2_candidates(depth1)
        depth2: tuple[AggregateNode, ...] = ()
        if depth2_candidates:
            depth2_output = await self._complete_depth2(depth2_candidates, depth1, known_kes)
            depth2 = self._accept_depth2(
                depth2_candidates,
                depth2_output,
                depth1,
                known_kes,
            )
        return validate_semantic_dag((*depth1, *depth2), known_kes)

    async def _complete(
        self,
        candidates: Sequence[AggregateCandidate],
        known_kes: Mapping[str, KnowledgeEquation],
        depth: Literal[1],
    ) -> AggregateSelectionOutput:
        payload: JsonObject = {
            "task": "select_semantic_dag_candidates",
            "depth": depth,
            "candidates": [
                {
                    **cast(dict[str, JsonValue], candidate.model_dump(mode="json")),
                    "lower_records": [
                        cast(JsonValue, known_kes[reference].model_dump(mode="json"))
                        for reference in candidate.member_refs
                    ],
                }
                for candidate in candidates
            ],
        }
        response = await self._model.complete(
            AggregateSelectionOutput,
            _model_messages(payload),
            TraceContext(
                operation="semantic-dag-depth-1",
                metadata={"run_id": self._run_id, "depth": 1},
            ),
        )
        return _validated_selection(response)

    async def _complete_depth2(
        self,
        candidates: Sequence[AggregateCandidate],
        depth1_nodes: Sequence[AggregateNode],
        known_kes: Mapping[str, KnowledgeEquation],
    ) -> AggregateSelectionOutput:
        nodes = {node.id: node for node in depth1_nodes}
        payload: JsonObject = {
            "task": "select_semantic_dag_candidates",
            "depth": 2,
            "candidates": [
                {
                    **cast(dict[str, JsonValue], candidate.model_dump(mode="json")),
                    "lower_records": [
                        _depth2_node_payload(nodes[reference], known_kes)
                        for reference in candidate.member_refs
                    ],
                }
                for candidate in candidates
            ],
        }
        response = await self._model.complete(
            AggregateSelectionOutput,
            _model_messages(payload),
            TraceContext(
                operation="semantic-dag-depth-2",
                metadata={"run_id": self._run_id, "depth": 2},
            ),
        )
        return _validated_selection(response)

    def _accept_depth1(
        self,
        candidates: Sequence[AggregateCandidate],
        output: AggregateSelectionOutput,
        known_kes: Mapping[str, KnowledgeEquation],
    ) -> tuple[AggregateNode, ...]:
        offered = {candidate.id: candidate for candidate in candidates}
        nodes = tuple(
            self._build_node(proposal, offered, known_kes, {}, depth=1)
            for proposal in output.accepted
        )
        validate_semantic_dag(nodes, known_kes)
        return tuple(sorted(nodes, key=lambda item: item.id))

    def _accept_depth2(
        self,
        candidates: Sequence[AggregateCandidate],
        output: AggregateSelectionOutput,
        depth1_nodes: Sequence[AggregateNode],
        known_kes: Mapping[str, KnowledgeEquation],
    ) -> tuple[AggregateNode, ...]:
        offered = {candidate.id: candidate for candidate in candidates}
        nodes_by_id = {node.id: node for node in depth1_nodes}
        nodes = tuple(
            self._build_node(proposal, offered, known_kes, nodes_by_id, depth=2)
            for proposal in output.accepted
        )
        validate_semantic_dag((*depth1_nodes, *nodes), known_kes)
        return tuple(sorted(nodes, key=lambda item: item.id))

    def _build_node(
        self,
        proposal: AggregateNodeProposal,
        offered: Mapping[str, AggregateCandidate],
        known_kes: Mapping[str, KnowledgeEquation],
        known_nodes: Mapping[str, AggregateNode],
        *,
        depth: NodeDepth,
    ) -> AggregateNode:
        candidate = offered.get(proposal.candidate_id)
        if candidate is None:
            raise AggregationInvariantError(
                f"model accepted an unoffered candidate {proposal.candidate_id}"
            )
        if proposal.depth != depth or candidate.depth != depth:
            raise AggregationInvariantError("model accepted a candidate at the wrong depth")
        if tuple(sorted(proposal.member_refs)) != candidate.member_refs:
            raise AggregationInvariantError("model changed offered candidate member refs")

        closure = _candidate_closure(candidate, known_kes, known_nodes)
        assertions = tuple(
            sorted(
                (self._build_assertion(assertion, closure) for assertion in proposal.assertions),
                key=lambda item: item.id,
            )
        )
        if not assertions:
            raise AggregationInvariantError("accepted aggregate node has no valid assertion")
        ids = tuple(item.id for item in assertions)
        revisions = tuple(item.revision for item in assertions)
        if len(ids) != len(set(ids)):
            raise AggregationInvariantError("duplicate aggregate assertion logical ID")
        if len(revisions) != len(set(revisions)):
            raise AggregationInvariantError("duplicate aggregate assertion revision")
        return create_aggregate_node(
            node_kind=proposal.node_kind,
            title=proposal.title,
            summary=proposal.summary,
            assertions=assertions,
            member_refs=candidate.member_refs,
            derived_from=tuple(
                sorted(
                    {reference for assertion in assertions for reference in assertion.derived_from}
                )
            ),
            evidence_closure=closure.member_evidence,
            temporal_extent=closure.member_temporal,
            confidence=proposal.confidence,
            depth=depth,
        )

    def _build_assertion(
        self,
        proposal: AggregateAssertionProposal,
        closure: _CandidateClosure,
    ) -> KnowledgeEquation:
        cited_ids = tuple(sorted(proposal.derived_from))
        missing = sorted(set(cited_ids).difference(closure.refs))
        if missing:
            raise AggregationInvariantError(
                f"aggregate assertion {proposal.key} cites unknown lower record {missing[0]}"
            )
        cited_records = tuple(
            record for reference in cited_ids for record in closure.symbol_records[reference]
        )
        used_terms = validate_expression_authority(
            proposal.lhs,
            proposal.rhs,
            cited_records,
            cited_ids,
            label=f"aggregate assertion {proposal.key}",
            allowed_assertion_ids={record.id for record in cited_records},
        )
        return KnowledgeEquation.create(
            level=KnowledgeLevel.AGGREGATE,
            lhs=proposal.lhs,
            rhs=proposal.rhs,
            gloss=proposal.gloss,
            modality=proposal.modality,
            polarity=proposal.polarity,
            lifecycle=proposal.lifecycle,
            speaker=Speaker.DERIVED,
            temporal=temporal_envelope(
                closure.temporal_by_ref[reference] for reference in cited_ids
            ),
            ontology_bindings=ontology_binding_union(used_terms, cited_records),
            evidence_refs=sorted_unique_spans(
                span for reference in cited_ids for span in closure.evidence_by_ref[reference]
            ),
            derived_from=cited_ids,
            confidence=proposal.confidence,
            produced_in_run_id=self._run_id,
            produced_in_stage=SEMANTIC_DAG_STAGE,
        )


class _CandidateClosure:
    def __init__(
        self,
        symbol_records: Mapping[str, tuple[KnowledgeEquation, ...]],
        evidence_by_ref: Mapping[str, tuple[MessageSpan, ...]],
        temporal_by_ref: Mapping[str, TemporalMetadata],
        member_evidence: tuple[MessageSpan, ...],
        member_temporal: TemporalMetadata,
    ) -> None:
        self.symbol_records = symbol_records
        self.evidence_by_ref = evidence_by_ref
        self.temporal_by_ref = temporal_by_ref
        self.member_evidence = member_evidence
        self.member_temporal = member_temporal

    @property
    def refs(self) -> frozenset[str]:
        return frozenset(self.symbol_records)


def validate_evidence_closure(
    nodes: Sequence[AggregateNode],
    known_kes: Mapping[str, KnowledgeEquation] | Sequence[KnowledgeEquation],
) -> None:
    lower_kes = records_by_id(known_kes, label="known Session KE")
    for equation in lower_kes.values():
        authenticate_knowledge_equation(equation, label=f"known Session KE {equation.id}")
        if equation.level is not KnowledgeLevel.SESSION:
            raise AggregationInvariantError(f"known KE {equation.id} is not Session-level")
    lower_ids = set(lower_kes)
    for equation in lower_kes.values():
        validate_knowledge_equation_relations(
            equation,
            lower_ids,
            label=f"known Session KE {equation.id}",
        )
    nodes_by_id = _nodes_by_id(nodes)
    for node in nodes:
        if node.depth not in (1, 2):
            raise AggregationInvariantError("aggregate node depth exceeds the maximum of 2")
        if node.id in node.member_refs:
            raise AggregationInvariantError(f"aggregate node {node.id} has a self edge")
        closure = _node_closure(node, lower_kes, nodes_by_id)
        if len(node.member_refs) < 2:
            raise AggregationInvariantError(
                "aggregate node canonical shape requires at least two unique members"
            )
        if not node.assertions:
            raise AggregationInvariantError(
                "aggregate node canonical shape requires at least one assertion"
            )
        transitive_ids = set(closure.refs)
        if not set(node.derived_from).issubset(transitive_ids):
            raise AggregationInvariantError("node derived_from escapes transitive member closure")
        assertion_derived = {
            reference for assertion in node.assertions for reference in assertion.derived_from
        }
        if set(node.derived_from) != assertion_derived:
            raise AggregationInvariantError(
                "node derived_from is not the exact aggregate assertion reference union"
            )
        for assertion in node.assertions:
            authenticate_knowledge_equation(
                assertion,
                label=f"aggregate assertion {assertion.id}",
            )
            if assertion.level is not KnowledgeLevel.AGGREGATE:
                raise AggregationInvariantError("aggregate assertion has the wrong level")
            if assertion.speaker is not Speaker.DERIVED:
                raise AggregationInvariantError("aggregate assertion must have derived speaker")
            if assertion.lifecycle not in (Lifecycle.ACTIVE, Lifecycle.UNCERTAIN):
                raise AggregationInvariantError("aggregate assertion has an invalid lifecycle")
            if assertion.produced_in_stage != SEMANTIC_DAG_STAGE:
                raise AggregationInvariantError("aggregate assertion has the wrong stage")
            allowed_relation_ids = {
                record.id for records in closure.symbol_records.values() for record in records
            }
            validate_knowledge_equation_relations(
                assertion,
                allowed_relation_ids,
                label=f"aggregate assertion {assertion.id}",
            )
            if assertion.derived_from != tuple(sorted(assertion.derived_from)):
                raise AggregationInvariantError("aggregate assertion lower refs must be sorted")
            if not set(assertion.derived_from).issubset(transitive_ids):
                raise AggregationInvariantError(
                    "aggregate assertion derived_from escapes transitive member closure"
                )
            cited_records = tuple(
                record
                for reference in assertion.derived_from
                for record in closure.symbol_records[reference]
            )
            used_terms = validate_expression_authority(
                assertion.lhs,
                assertion.rhs,
                cited_records,
                assertion.derived_from,
                label=f"aggregate assertion {assertion.id}",
                allowed_assertion_ids={record.id for record in cited_records},
            )
            expected_evidence = sorted_unique_spans(
                span
                for reference in assertion.derived_from
                for span in closure.evidence_by_ref[reference]
            )
            if assertion.evidence_refs != expected_evidence:
                raise AggregationInvariantError("aggregate assertion evidence closure is not exact")
            if assertion.ontology_bindings != ontology_binding_union(used_terms, cited_records):
                raise AggregationInvariantError(
                    "aggregate assertion ontology bindings are not exact"
                )
            expected_temporal = temporal_envelope(
                closure.temporal_by_ref[reference] for reference in assertion.derived_from
            )
            if assertion.temporal != expected_temporal:
                raise AggregationInvariantError(
                    "aggregate assertion temporal envelope is not exact"
                )
        _authenticate_aggregate_node(node)
        if not node.assertions:
            raise AggregationInvariantError("accepted aggregate node has no valid assertion")
        if node.evidence_closure != closure.member_evidence:
            raise AggregationInvariantError("aggregate node evidence closure is not exact")
        if node.temporal_extent != closure.member_temporal:
            raise AggregationInvariantError("aggregate node temporal extent is not exact")


def validate_semantic_dag(
    nodes: Sequence[AggregateNode],
    known_kes: Mapping[str, KnowledgeEquation] | Sequence[KnowledgeEquation],
) -> SemanticDAG:
    node_records = tuple(nodes)
    lower_kes = records_by_id(known_kes, label="known Session KE")
    nodes_by_id = _nodes_by_id(node_records)
    _reject_cycles(nodes_by_id)
    validate_evidence_closure(node_records, lower_kes)

    return SemanticDAG(nodes=_topological_order(nodes_by_id))


def _authenticate_aggregate_node(node: AggregateNode) -> None:
    logical_payload = cast(
        JsonValue,
        {
            "schema_version": SCHEMA_VERSION,
            "node_kind": node.node_kind.value,
            "member_refs": list(node.member_refs),
            "derived_from": list(node.derived_from),
            "assertion_ids": [assertion.id for assertion in node.assertions],
            "depth": node.depth,
        },
    )
    expected_id = content_id("aggregate", logical_payload)
    if node.id != expected_id:
        raise AggregationInvariantError(
            f"aggregate node logical ID is invalid: expected {expected_id}"
        )
    revision_payload = cast(JsonValue, node.model_dump(mode="json", exclude={"revision"}))
    expected_revision = hashlib.sha256(canonical_json(revision_payload)).hexdigest()
    if node.revision != expected_revision:
        raise AggregationInvariantError("aggregate node revision is invalid")


def _candidate_closure(
    candidate: AggregateCandidate,
    known_kes: Mapping[str, KnowledgeEquation],
    known_nodes: Mapping[str, AggregateNode],
) -> _CandidateClosure:
    placeholder = AggregateNode(
        id="candidate-placeholder",
        node_kind=AggregateNodeKind.OTHER,
        title="candidate",
        summary="candidate",
        assertions=(),
        member_refs=candidate.member_refs,
        derived_from=(),
        evidence_closure=(),
        temporal_extent=TemporalMetadata(),
        confidence=0,
        revision="0" * 64,
        depth=candidate.depth,
    )
    return _node_closure(placeholder, known_kes, known_nodes)


def _node_closure(
    node: AggregateNode,
    known_kes: Mapping[str, KnowledgeEquation],
    known_nodes: Mapping[str, AggregateNode],
) -> _CandidateClosure:
    return _node_closure_inner(node, known_kes, known_nodes, visiting=set())


def _node_closure_inner(
    node: AggregateNode,
    known_kes: Mapping[str, KnowledgeEquation],
    known_nodes: Mapping[str, AggregateNode],
    *,
    visiting: set[str],
) -> _CandidateClosure:
    if node.id in visiting:
        raise AggregationInvariantError(f"aggregate DAG contains a cycle involving {node.id}")
    next_visiting = {*visiting, node.id}
    if node.depth == 1:
        missing = sorted(set(node.member_refs).difference(known_kes))
        if missing:
            if missing[0] in known_nodes:
                raise AggregationInvariantError("depth-1 member must be a known Session KE")
            raise AggregationInvariantError(f"missing member {missing[0]} for depth-1 aggregate")
        members = tuple(known_kes[ref] for ref in node.member_refs)
        return _CandidateClosure(
            symbol_records={item.id: (item,) for item in members},
            evidence_by_ref={item.id: item.evidence_refs for item in members},
            temporal_by_ref={item.id: item.temporal for item in members},
            member_evidence=evidence_union(members),
            member_temporal=temporal_envelope(item.temporal for item in members),
        )
    if node.depth == 2:
        missing = sorted(set(node.member_refs).difference(known_nodes))
        if missing:
            if missing[0] in known_kes:
                raise AggregationInvariantError("depth-2 member must be a depth-1 node")
            raise AggregationInvariantError(f"dangling member {missing[0]} for depth-2 aggregate")
        members = tuple(known_nodes[ref] for ref in node.member_refs)
        wrong_depth = sorted(member.id for member in members if member.depth != 1)
        if wrong_depth:
            raise AggregationInvariantError("depth-2 member must be a depth-1 node")
        symbol_records: dict[str, tuple[KnowledgeEquation, ...]] = {}
        evidence_by_ref: dict[str, tuple[MessageSpan, ...]] = {}
        temporal_by_ref: dict[str, TemporalMetadata] = {}
        for member in members:
            lower = _node_closure_inner(
                member,
                known_kes,
                known_nodes,
                visiting=next_visiting,
            )
            symbol_records.update(lower.symbol_records)
            evidence_by_ref.update(lower.evidence_by_ref)
            temporal_by_ref.update(lower.temporal_by_ref)
            for assertion in member.assertions:
                symbol_records[assertion.id] = (assertion,)
                evidence_by_ref[assertion.id] = assertion.evidence_refs
                temporal_by_ref[assertion.id] = assertion.temporal
            if member.id in symbol_records:
                raise AggregationInvariantError(
                    f"aggregate node ID collides with assertion ID {member.id}"
                )
            symbol_records[member.id] = member.assertions
            evidence_by_ref[member.id] = member.evidence_closure
            temporal_by_ref[member.id] = member.temporal_extent
        return _CandidateClosure(
            symbol_records=symbol_records,
            evidence_by_ref=evidence_by_ref,
            temporal_by_ref=temporal_by_ref,
            member_evidence=sorted_unique_spans(
                span for member in members for span in member.evidence_closure
            ),
            member_temporal=temporal_envelope(member.temporal_extent for member in members),
        )
    raise AggregationInvariantError("aggregate node depth exceeds the maximum of 2")


def _nodes_by_id(nodes: Sequence[AggregateNode]) -> dict[str, AggregateNode]:
    result: dict[str, AggregateNode] = {}
    for node in nodes:
        _validate_aggregate_node_shape(node)
        if node.id in result:
            raise AggregationInvariantError(f"duplicate aggregate node {node.id}")
        result[node.id] = node
    revisions = tuple(node.revision for node in result.values())
    if len(revisions) != len(set(revisions)):
        raise AggregationInvariantError("duplicate aggregate node revision")
    return result


def _validate_aggregate_node_shape(node: AggregateNode) -> None:
    try:
        validated = AggregateNode.model_validate(node.model_dump(mode="python", warnings=False))
    except (AttributeError, TypeError, ValidationError, ValueError) as error:
        if not isinstance(error, ValidationError):
            raise AggregationInvariantError("aggregate node has an invalid shape") from error
        nested_revision = any(
            details["loc"]
            and details["loc"][0] == "assertions"
            and "revision" in details["msg"].casefold()
            for details in error.errors()
        )
        if nested_revision:
            raise AggregationInvariantError(
                "aggregate assertion has an invalid revision"
            ) from error
        raise AggregationInvariantError("aggregate node has an invalid shape") from error
    if not same_runtime_shape(node, validated):
        raise AggregationInvariantError("aggregate node has a noncanonical runtime shape")

    if node.member_refs != tuple(sorted(node.member_refs)):
        raise AggregationInvariantError("aggregate node member refs are not canonical")
    if node.derived_from != tuple(sorted(node.derived_from)):
        raise AggregationInvariantError("aggregate node derived refs are not canonical")
    if node.assertions != tuple(sorted(node.assertions, key=lambda item: item.id)):
        raise AggregationInvariantError("aggregate node assertions are not canonical")
    assertion_revisions = tuple(assertion.revision for assertion in node.assertions)
    if len(assertion_revisions) != len(set(assertion_revisions)):
        raise AggregationInvariantError(
            "aggregate node assertion revisions are not a canonical unique tuple"
        )
    if node.evidence_closure != sorted_unique_spans(node.evidence_closure):
        raise AggregationInvariantError("aggregate node evidence closure is not canonical")


def _reject_cycles(nodes: Mapping[str, AggregateNode]) -> None:
    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()

    def strong_connect(node_id: str) -> None:
        nonlocal index
        indices[node_id] = index
        lowlinks[node_id] = index
        index += 1
        stack.append(node_id)
        on_stack.add(node_id)
        for member in sorted(nodes[node_id].member_refs):
            if member not in nodes:
                continue
            if member == node_id:
                raise AggregationInvariantError(f"aggregate node {node_id} has a self edge")
            if member not in indices:
                strong_connect(member)
                lowlinks[node_id] = min(lowlinks[node_id], lowlinks[member])
            elif member in on_stack:
                lowlinks[node_id] = min(lowlinks[node_id], indices[member])
        if lowlinks[node_id] != indices[node_id]:
            return
        component: list[str] = []
        while True:
            member = stack.pop()
            on_stack.remove(member)
            component.append(member)
            if member == node_id:
                break
        if len(component) > 1:
            raise AggregationInvariantError(
                f"aggregate DAG contains a cycle involving {min(component)}"
            )

    for node_id in sorted(nodes):
        if node_id not in indices:
            strong_connect(node_id)


def _topological_order(nodes: Mapping[str, AggregateNode]) -> tuple[AggregateNode, ...]:
    dependency_count = {
        node_id: sum(member in nodes for member in node.member_refs)
        for node_id, node in nodes.items()
    }
    dependents: dict[str, set[str]] = defaultdict(set)
    for node_id, node in nodes.items():
        for member in node.member_refs:
            if member in nodes:
                dependents[member].add(node_id)
    ready = sorted(node_id for node_id, count in dependency_count.items() if count == 0)
    ordered: list[AggregateNode] = []
    while ready:
        node_id = ready.pop(0)
        ordered.append(nodes[node_id])
        for dependent in sorted(dependents[node_id]):
            dependency_count[dependent] -= 1
            if dependency_count[dependent] == 0:
                ready.append(dependent)
                ready.sort()
    if len(ordered) != len(nodes):
        raise AggregationInvariantError("aggregate DAG contains a cycle")
    return tuple(ordered)


def _validated_selection(value: object) -> AggregateSelectionOutput:
    if not isinstance(value, BaseModel):
        raise AggregationInvariantError("DAG model did not return a validated record")
    try:
        return AggregateSelectionOutput.model_validate(value.model_dump(mode="python"))
    except (TypeError, ValidationError, ValueError) as error:
        raise AggregationInvariantError("DAG model output is not a validated record") from error


def _model_messages(payload: JsonObject) -> list[dict[str, object]]:
    try:
        prompt = (_PROMPT_ROOT / "semantic_dag/system.md").read_text(encoding="utf-8")
    except OSError as error:
        raise AggregationInvariantError("required semantic DAG prompt is unavailable") from error
    return [
        {"role": "system", "content": prompt},
        {"role": "user", "content": canonical_json(payload).decode("utf-8")},
    ]


def _depth2_node_payload(
    node: AggregateNode,
    known_kes: Mapping[str, KnowledgeEquation],
) -> JsonValue:
    closure = _node_closure(node, known_kes, {node.id: node})
    return {
        "node": cast(JsonValue, node.model_dump(mode="json")),
        "transitive_records": [
            cast(JsonValue, record.model_dump(mode="json"))
            for key in sorted(closure.symbol_records)
            for record in closure.symbol_records[key]
        ],
    }


def _reject_duplicates(values: tuple[object, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label} are not allowed")
