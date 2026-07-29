from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .io import canonical_json_bytes
from .representation_contract import (
    MemoryRepresentationBundle,
    RepresentationProfile,
    assess_bundle_integrity,
)
from .semantic_ir import (
    ClosureRecord,
    EpistemicBinding,
    L1MemoryUnit,
    L2MemoryUnit,
    Lifecycle,
    LinkBinding,
    Modality,
    Polarity,
    QuerySlotPlan,
    SourceBinding,
    TimeBinding,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PredicateNode(StrictModel):
    node_id: str = Field(min_length=1)
    ordinal: int = Field(ge=0)
    node_type: Literal["predicate"] = "predicate"
    surface: str = Field(min_length=1)
    sense: str = Field(min_length=1)
    canonical_operator: str = Field(min_length=1)


class EntityNode(StrictModel):
    node_id: str = Field(min_length=1)
    ordinal: int = Field(ge=0)
    node_type: Literal["entity"] = "entity"
    entity_id: str = Field(min_length=1)


class AbstractionNode(StrictModel):
    node_id: str = Field(min_length=1)
    ordinal: int = Field(ge=0)
    node_type: Literal["abstraction"] = "abstraction"
    summary: str = Field(min_length=1)
    assertions: list[str] = Field(min_length=1)


class ReferenceNode(StrictModel):
    node_id: str = Field(min_length=1)
    ordinal: int = Field(ge=0)
    node_type: Literal["reference"] = "reference"
    reference_type: Literal["memory_unit", "turn", "session", "closure"]
    reference_id: str = Field(min_length=1)


GraphNode = Annotated[
    PredicateNode | EntityNode | AbstractionNode | ReferenceNode,
    Field(discriminator="node_type"),
]


class GraphEdge(StrictModel):
    edge_id: str = Field(min_length=1)
    ordinal: int = Field(ge=0)
    source_node_id: str = Field(min_length=1)
    target_node_id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    role_name: str = Field(min_length=1)


class L1GraphAnnotations(StrictModel):
    modality: Modality
    polarity: Polarity
    time: TimeBinding
    source: SourceBinding
    epistemic: EpistemicBinding
    links: LinkBinding
    lifecycle: Lifecycle


class L2GraphAnnotations(StrictModel):
    lifecycle: Lifecycle
    valid_time: str | None
    abstraction_method: dict[str, str | None]


def _validate_ordered_ids(items: list[Any], *, item_name: str) -> None:
    identifiers = [item.node_id if hasattr(item, "node_id") else item.edge_id for item in items]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f"duplicate {item_name} ids")
    ordinals = [item.ordinal for item in items]
    if ordinals != list(range(len(items))):
        raise ValueError(f"{item_name} ordinals must be contiguous and ordered")


def _validate_edges(
    nodes: list[GraphNode],
    edges: list[GraphEdge],
    *,
    root_node_id: str,
) -> dict[str, GraphNode]:
    _validate_ordered_ids(nodes, item_name="node")
    _validate_ordered_ids(edges, item_name="edge")
    node_by_id = {node.node_id: node for node in nodes}
    duplicate_keys: set[tuple[str, str, str, str]] = set()
    for edge in edges:
        if edge.source_node_id not in node_by_id:
            raise ValueError(f"edge {edge.edge_id} references missing source node")
        if edge.target_node_id not in node_by_id:
            raise ValueError(f"edge {edge.edge_id} references missing target node")
        if edge.source_node_id != root_node_id:
            raise ValueError(f"edge {edge.edge_id} must start at the graph root")
        key = (edge.source_node_id, edge.target_node_id, edge.role, edge.role_name)
        if key in duplicate_keys:
            raise ValueError(f"duplicate role edge: {edge.role}")
        duplicate_keys.add(key)
    return node_by_id


class L1Graph(StrictModel):
    graph_id: str = Field(min_length=1)
    unit_id: str = Field(min_length=1)
    unit_schema_version: Literal["semantic-ir-l1-v1"]
    bundle_ordinal: int = Field(ge=0)
    level: Literal["L1"] = "L1"
    kind: Literal["event", "state", "preference", "task", "attribute"]
    nodes: list[GraphNode] = Field(min_length=2)
    edges: list[GraphEdge] = Field(min_length=1)
    annotations: L1GraphAnnotations

    @model_validator(mode="after")
    def validate_graph(self) -> "L1Graph":
        predicates = [node for node in self.nodes if isinstance(node, PredicateNode)]
        entities = [node for node in self.nodes if isinstance(node, EntityNode)]
        if len(predicates) != 1:
            raise ValueError("L1 graph must contain exactly one predicate node")
        if len(entities) != len(self.nodes) - 1:
            raise ValueError("L1 graph may contain only predicate and entity nodes")
        node_by_id = _validate_edges(
            self.nodes,
            self.edges,
            root_node_id=predicates[0].node_id,
        )
        referenced_entities: set[str] = set()
        for edge in self.edges:
            target = node_by_id[edge.target_node_id]
            if not isinstance(target, EntityNode):
                raise ValueError(f"L1 role edge {edge.edge_id} must target an entity node")
            referenced_entities.add(target.node_id)
        if referenced_entities != {node.node_id for node in entities}:
            raise ValueError("L1 graph contains an unreferenced entity node")
        return self


_L2_ROLE_REFERENCE_TYPES = {
    "abstracts": "memory_unit",
    "source_l1_unit": "memory_unit",
    "source_turn": "turn",
    "source_session": "session",
    "supported_by_closure": "closure",
}


class L2Graph(StrictModel):
    graph_id: str = Field(min_length=1)
    unit_id: str = Field(min_length=1)
    unit_schema_version: Literal["semantic-ir-l2-v1"]
    bundle_ordinal: int = Field(ge=0)
    level: Literal["L2"] = "L2"
    kind: Literal["task", "preference_profile", "project", "habit", "long_running_state", "summary_event"]
    nodes: list[GraphNode] = Field(min_length=2)
    edges: list[GraphEdge] = Field(min_length=5)
    annotations: L2GraphAnnotations

    @model_validator(mode="after")
    def validate_graph(self) -> "L2Graph":
        abstractions = [node for node in self.nodes if isinstance(node, AbstractionNode)]
        references = [node for node in self.nodes if isinstance(node, ReferenceNode)]
        if len(abstractions) != 1:
            raise ValueError("L2 graph must contain exactly one abstraction node")
        if len(references) != len(self.nodes) - 1:
            raise ValueError("L2 graph may contain only abstraction and reference nodes")
        node_by_id = _validate_edges(
            self.nodes,
            self.edges,
            root_node_id=abstractions[0].node_id,
        )
        role_counts = {role: 0 for role in _L2_ROLE_REFERENCE_TYPES}
        referenced_nodes: set[str] = set()
        for edge in self.edges:
            expected_type = _L2_ROLE_REFERENCE_TYPES.get(edge.role)
            if expected_type is None:
                raise ValueError(f"unsupported L2 derivation edge role: {edge.role}")
            target = node_by_id[edge.target_node_id]
            if not isinstance(target, ReferenceNode) or target.reference_type != expected_type:
                raise ValueError(f"L2 edge {edge.edge_id} has incompatible reference target")
            role_counts[edge.role] += 1
            referenced_nodes.add(target.node_id)
        if role_counts["supported_by_closure"] != 1:
            raise ValueError("L2 graph must contain exactly one closure reference")
        for role in ("abstracts", "source_l1_unit", "source_turn", "source_session"):
            if role_counts[role] == 0:
                raise ValueError(f"L2 graph is missing required derivation role: {role}")
        if referenced_nodes != {node.node_id for node in references}:
            raise ValueError("L2 graph contains an unreferenced reference node")
        return self


GraphRecord = Annotated[L1Graph | L2Graph, Field(discriminator="level")]


class ExtendedAmrPayload(StrictModel):
    schema_version: Literal["extended-amr-memory-graph-v1"] = "extended-amr-memory-graph-v1"
    logical_bundle_schema_version: Literal["memory-representation-bundle-v2"]
    bundle_id: str = Field(min_length=1)
    logical_profile: RepresentationProfile
    physical_profile: RepresentationProfile
    graphs: list[GraphRecord]
    closures: list[ClosureRecord]
    queries: list[QuerySlotPlan]
    query_unit_scopes: dict[str, list[str]]
    logical_metadata: dict[str, Any]

    @model_validator(mode="after")
    def validate_graph_identity(self) -> "ExtendedAmrPayload":
        graph_ids = [graph.graph_id for graph in self.graphs]
        if len(graph_ids) != len(set(graph_ids)):
            raise ValueError("duplicate graph ids")
        unit_ids = [graph.unit_id for graph in self.graphs]
        if len(unit_ids) != len(set(unit_ids)):
            raise ValueError("duplicate graph unit ids")
        ordinals = [graph.bundle_ordinal for graph in self.graphs]
        if ordinals != list(range(len(self.graphs))):
            raise ValueError("graph bundle ordinals must be contiguous and ordered")
        if self.physical_profile.family != "extended_amr":
            raise ValueError("physical profile must use the extended_amr family")
        return self


def _l1_graph(unit: L1MemoryUnit, bundle_ordinal: int) -> L1Graph:
    graph_id = f"graph:{unit.unit_id}"
    predicate_id = f"{graph_id}:predicate"
    nodes: list[GraphNode] = [
        PredicateNode(
            node_id=predicate_id,
            ordinal=0,
            surface=unit.predicate.surface,
            sense=unit.predicate.sense,
            canonical_operator=unit.predicate.canonical_operator,
        )
    ]
    entity_node_ids: dict[str, str] = {}
    edges: list[GraphEdge] = []
    for role in unit.roles:
        target_id = entity_node_ids.get(role.entity_id)
        if target_id is None:
            target_id = f"{graph_id}:entity:{len(entity_node_ids)}"
            entity_node_ids[role.entity_id] = target_id
            nodes.append(
                EntityNode(
                    node_id=target_id,
                    ordinal=len(nodes),
                    entity_id=role.entity_id,
                )
            )
        edges.append(
            GraphEdge(
                edge_id=f"{graph_id}:edge:{len(edges)}",
                ordinal=len(edges),
                source_node_id=predicate_id,
                target_node_id=target_id,
                role=role.role,
                role_name=role.role_name,
            )
        )
    return L1Graph(
        graph_id=graph_id,
        unit_id=unit.unit_id,
        unit_schema_version=unit.schema_version,
        bundle_ordinal=bundle_ordinal,
        kind=unit.kind,
        nodes=nodes,
        edges=edges,
        annotations=L1GraphAnnotations(
            modality=unit.modality,
            polarity=unit.polarity,
            time=unit.time,
            source=unit.source,
            epistemic=unit.epistemic,
            links=unit.links,
            lifecycle=unit.lifecycle,
        ),
    )


def _l2_graph(unit: L2MemoryUnit, bundle_ordinal: int) -> L2Graph:
    graph_id = f"graph:{unit.unit_id}"
    root_id = f"{graph_id}:abstraction"
    nodes: list[GraphNode] = [
        AbstractionNode(
            node_id=root_id,
            ordinal=0,
            summary=unit.summary,
            assertions=unit.assertions,
        )
    ]
    edges: list[GraphEdge] = []

    def add_references(role: str, role_name: str, reference_type: str, values: list[str]) -> None:
        for value in values:
            target_id = f"{graph_id}:reference:{len(nodes) - 1}"
            nodes.append(
                ReferenceNode(
                    node_id=target_id,
                    ordinal=len(nodes),
                    reference_type=reference_type,  # type: ignore[arg-type]
                    reference_id=value,
                )
            )
            edges.append(
                GraphEdge(
                    edge_id=f"{graph_id}:edge:{len(edges)}",
                    ordinal=len(edges),
                    source_node_id=root_id,
                    target_node_id=target_id,
                    role=role,
                    role_name=role_name,
                )
            )

    add_references("abstracts", "abstracted_unit", "memory_unit", unit.abstracts)
    add_references("source_l1_unit", "source_l1_unit", "memory_unit", unit.source_l1_units)
    add_references("source_turn", "source_turn", "turn", unit.source_turns)
    add_references("source_session", "source_session", "session", unit.source_sessions)
    add_references("supported_by_closure", "closure", "closure", [unit.closure_id])
    return L2Graph(
        graph_id=graph_id,
        unit_id=unit.unit_id,
        unit_schema_version=unit.schema_version,
        bundle_ordinal=bundle_ordinal,
        kind=unit.kind,
        nodes=nodes,
        edges=edges,
        annotations=L2GraphAnnotations(
            lifecycle=unit.lifecycle,
            valid_time=unit.valid_time,
            abstraction_method=unit.abstraction_method,
        ),
    )


def _reference_values(graph: L2Graph, role: str) -> list[str]:
    nodes = {node.node_id: node for node in graph.nodes}
    values: list[str] = []
    for edge in graph.edges:
        if edge.role != role:
            continue
        target = nodes[edge.target_node_id]
        if not isinstance(target, ReferenceNode):
            raise ValueError(f"L2 role {role} does not target a reference node")
        values.append(target.reference_id)
    return values


def _decode_l1(graph: L1Graph) -> L1MemoryUnit:
    predicate = next(node for node in graph.nodes if isinstance(node, PredicateNode))
    nodes = {node.node_id: node for node in graph.nodes}
    roles = []
    for edge in graph.edges:
        target = nodes[edge.target_node_id]
        if not isinstance(target, EntityNode):
            raise ValueError(f"L1 role {edge.role} does not target an entity node")
        roles.append(
            {
                "role": edge.role,
                "entity_id": target.entity_id,
                "role_name": edge.role_name,
            }
        )
    return L1MemoryUnit(
        schema_version=graph.unit_schema_version,
        unit_id=graph.unit_id,
        kind=graph.kind,
        predicate={
            "surface": predicate.surface,
            "sense": predicate.sense,
            "canonical_operator": predicate.canonical_operator,
        },
        roles=roles,
        modality=graph.annotations.modality,
        polarity=graph.annotations.polarity,
        time=graph.annotations.time,
        source=graph.annotations.source,
        epistemic=graph.annotations.epistemic,
        links=graph.annotations.links,
        lifecycle=graph.annotations.lifecycle,
    )


def _decode_l2(graph: L2Graph) -> L2MemoryUnit:
    abstraction = next(node for node in graph.nodes if isinstance(node, AbstractionNode))
    closure_ids = _reference_values(graph, "supported_by_closure")
    return L2MemoryUnit(
        schema_version=graph.unit_schema_version,
        unit_id=graph.unit_id,
        kind=graph.kind,
        abstracts=_reference_values(graph, "abstracts"),
        summary=abstraction.summary,
        assertions=abstraction.assertions,
        closure_id=closure_ids[0],
        lifecycle=graph.annotations.lifecycle,
        valid_time=graph.annotations.valid_time,
        abstraction_method=graph.annotations.abstraction_method,
        source_l1_units=_reference_values(graph, "source_l1_unit"),
        source_turns=_reference_values(graph, "source_turn"),
        source_sessions=_reference_values(graph, "source_session"),
    )


class ExtendedAmrJsonAdapter:
    def __init__(self, *, profile: RepresentationProfile) -> None:
        if profile.family != "extended_amr":
            raise ValueError("ExtendedAmrJsonAdapter requires an extended_amr profile")
        self.profile = profile

    def encode(self, bundle: MemoryRepresentationBundle) -> bytes:
        graphs: list[GraphRecord] = []
        for unit in bundle.l1_units:
            graphs.append(_l1_graph(unit, len(graphs)))
        for unit in bundle.l2_units:
            graphs.append(_l2_graph(unit, len(graphs)))
        payload = ExtendedAmrPayload(
            logical_bundle_schema_version=bundle.schema_version,
            bundle_id=bundle.bundle_id,
            logical_profile=bundle.profile,
            physical_profile=self.profile,
            graphs=graphs,
            closures=bundle.closures,
            queries=bundle.query_plans,
            query_unit_scopes=bundle.query_unit_scopes,
            logical_metadata=bundle.metadata,
        )
        return canonical_json_bytes(payload)

    def decode(self, payload: Any) -> MemoryRepresentationBundle:
        if isinstance(payload, ExtendedAmrPayload):
            parsed = payload
        elif isinstance(payload, dict):
            parsed = ExtendedAmrPayload.model_validate(payload)
        elif isinstance(payload, bytes):
            parsed = ExtendedAmrPayload.model_validate_json(payload)
        elif isinstance(payload, str):
            parsed = ExtendedAmrPayload.model_validate_json(payload)
        else:
            raise TypeError(f"unsupported payload type: {type(payload).__name__}")
        if parsed.physical_profile != self.profile:
            raise ValueError("payload physical profile does not match adapter profile")

        l1_units = [
            _decode_l1(graph)
            for graph in parsed.graphs
            if isinstance(graph, L1Graph)
        ]
        l2_units = [
            _decode_l2(graph)
            for graph in parsed.graphs
            if isinstance(graph, L2Graph)
        ]
        bundle = MemoryRepresentationBundle(
            schema_version=parsed.logical_bundle_schema_version,
            bundle_id=parsed.bundle_id,
            profile=parsed.logical_profile,
            l1_units=l1_units,
            l2_units=l2_units,
            closures=parsed.closures,
            query_plans=parsed.queries,
            query_unit_scopes=parsed.query_unit_scopes,
            metadata=parsed.logical_metadata,
        )
        integrity = assess_bundle_integrity(bundle)
        if not integrity.valid:
            raise ValueError("decoded bundle integrity invalid: " + "; ".join(integrity.errors))
        return bundle
