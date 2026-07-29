from __future__ import annotations

import json
from typing import Any

from .authoritative_memory import MemoryRepresentationBundleV3
from .extended_amr_v2_adapter import ExtendedAmrV2JsonAdapter
from .identity_resolution import (
    CanonicalIdentityGroup,
    ConceptRegistryEntry,
    EntityRecord,
    ExternalOntologyMapping,
    IdentityAggregateClaim,
    IdentityAwareMemoryBundleV4,
    IdentityDecision,
    IdentityDependency,
    IdentityEvidenceClosure,
    IdentitySnapshot,
    TypedIdentifier,
    assess_identity_bundle_integrity,
)
from .io import canonical_json_bytes
from .representation_contract import RepresentationProfile


_IDENTITY_FIELDS = {
    "concept_registry",
    "entity_records",
    "identity_decisions",
    "identity_closures",
    "identity_snapshots",
    "aggregate_claims",
}


def _edge(source: str, target: str, edge_type: str, **annotations: Any) -> dict[str, Any]:
    return {
        "edge_id": f"edge:{edge_type}:{source}:{target}:{len(annotations)}",
        "source": source,
        "target": target,
        "edge_type": edge_type,
        "annotations": annotations,
    }


def _ref(node_id: str, node_type: str, reference_id: str) -> dict[str, Any]:
    return {
        "node_id": node_id,
        "node_type": node_type,
        "reference_id": reference_id,
    }


def _base_bundle(bundle: IdentityAwareMemoryBundleV4) -> MemoryRepresentationBundleV3:
    data = bundle.model_dump(mode="json", exclude=_IDENTITY_FIELDS)
    data["schema_version"] = "memory-representation-bundle-v3"
    return MemoryRepresentationBundleV3.model_validate(data)


def _concept_graph(item: ConceptRegistryEntry) -> dict[str, Any]:
    root = f"concept:{item.concept_id}"
    nodes = [_ref(root, "concept", item.concept_id)]
    edges: list[dict[str, Any]] = []
    for index, mapping in enumerate(item.external_mappings):
        node_id = f"external-mapping:{item.concept_id}:{index}"
        nodes.append(_ref(node_id, "external_concept_or_property", mapping.external_id))
        edges.append(_edge(root, node_id, "maps_to", relation=mapping.relation))
    for parent_id in item.parent_concept_ids:
        node_id = f"parent-concept:{parent_id}"
        nodes.append(_ref(node_id, "concept", parent_id))
        edges.append(_edge(root, node_id, "subconcept_of"))
    return {
        "schema_version": "extended-amr-concept-graph-v1",
        "graph_id": f"concept-graph:{item.concept_id}",
        "root_node_id": root,
        "nodes": nodes,
        "edges": edges,
        "annotations": item.model_dump(mode="json"),
    }


def _entity_graph(item: EntityRecord) -> dict[str, Any]:
    root = f"entity:{item.entity_id}"
    nodes = [_ref(root, "entity", item.entity_id)]
    edges: list[dict[str, Any]] = []
    for concept_id in item.concept_ids:
        node_id = f"concept-ref:{concept_id}"
        nodes.append(_ref(node_id, "concept", concept_id))
        edges.append(_edge(root, node_id, "instance_of"))
    for index, identifier in enumerate(item.identifiers):
        node_id = f"identifier:{item.entity_id}:{index}"
        nodes.append(_ref(node_id, "typed_identifier", f"{identifier.namespace}:{identifier.value}"))
        edges.append(
            _edge(root, node_id, "has_identifier", namespace=identifier.namespace, value=identifier.value)
        )
    for unit_id in item.source_l1_unit_ids:
        node_id = f"l1-ref:{unit_id}"
        nodes.append(_ref(node_id, "l1_unit", unit_id))
        edges.append(_edge(root, node_id, "supported_by_l1"))
    for source_id in item.source_revision_ids:
        node_id = f"source-ref:{source_id}"
        nodes.append(_ref(node_id, "source_revision", source_id))
        edges.append(_edge(root, node_id, "supported_by_source"))
    return {
        "schema_version": "extended-amr-entity-graph-v1",
        "graph_id": f"entity-graph:{item.entity_id}",
        "root_node_id": root,
        "nodes": nodes,
        "edges": edges,
        "annotations": item.model_dump(mode="json"),
    }


def _decision_graph(item: IdentityDecision) -> dict[str, Any]:
    root = f"identity-decision:{item.decision_id}"
    nodes = [_ref(root, "identity_decision", item.decision_id)]
    edges: list[dict[str, Any]] = []
    for entity_id in item.subject_entity_ids:
        node_id = f"entity-ref:{item.decision_id}:{entity_id}"
        nodes.append(_ref(node_id, "entity", entity_id))
        edges.append(_edge(root, node_id, "identity_subject"))
    if item.canonical_entity_id:
        node_id = f"canonical-ref:{item.decision_id}:{item.canonical_entity_id}"
        nodes.append(_ref(node_id, "canonical_entity", item.canonical_entity_id))
        edges.append(_edge(root, node_id, "resolves_to"))
    for unit_id in item.evidence_l1_unit_ids:
        node_id = f"l1-ref:{item.decision_id}:{unit_id}"
        nodes.append(_ref(node_id, "l1_unit", unit_id))
        edges.append(_edge(root, node_id, "supported_by_l1"))
    for source_id in item.evidence_source_revision_ids:
        node_id = f"source-ref:{item.decision_id}:{source_id}"
        nodes.append(_ref(node_id, "source_revision", source_id))
        edges.append(_edge(root, node_id, "supported_by_source"))
    closure_node = f"identity-closure-ref:{item.closure_id}"
    nodes.append(_ref(closure_node, "identity_closure", item.closure_id))
    edges.append(_edge(root, closure_node, "uses_identity_closure"))
    if item.supersedes_decision_id:
        node_id = f"decision-ref:{item.decision_id}:{item.supersedes_decision_id}"
        nodes.append(_ref(node_id, "identity_decision", item.supersedes_decision_id))
        edges.append(_edge(root, node_id, "supersedes_decision"))
    return {
        "schema_version": "extended-amr-identity-decision-graph-v1",
        "graph_id": f"identity-decision-graph:{item.decision_id}",
        "root_node_id": root,
        "nodes": nodes,
        "edges": edges,
        "annotations": item.model_dump(mode="json"),
    }


def _closure_graph(item: IdentityEvidenceClosure) -> dict[str, Any]:
    root = f"identity-closure:{item.closure_id}"
    nodes = [_ref(root, "identity_closure", item.closure_id)]
    edges: list[dict[str, Any]] = []
    decision_node = f"decision-ref:{item.decision_id}"
    nodes.append(_ref(decision_node, "identity_decision", item.decision_id))
    edges.append(_edge(root, decision_node, "evaluates_decision"))
    for index, dependency in enumerate(item.dependencies):
        node_id = f"dependency:{item.closure_id}:{index}"
        nodes.append(_ref(node_id, dependency.reference_kind, dependency.reference_id))
        edges.append(
            _edge(
                root,
                node_id,
                "depends_on",
                reference_kind=dependency.reference_kind,
                content_sha256=dependency.content_sha256,
            )
        )
    return {
        "schema_version": "extended-amr-identity-closure-graph-v1",
        "graph_id": f"identity-closure-graph:{item.closure_id}",
        "root_node_id": root,
        "nodes": nodes,
        "edges": edges,
        "annotations": item.model_dump(mode="json"),
    }


def _snapshot_graph(item: IdentitySnapshot) -> dict[str, Any]:
    root = f"identity-snapshot:{item.snapshot_id}"
    nodes = [_ref(root, "identity_snapshot", item.snapshot_id)]
    edges: list[dict[str, Any]] = []
    for group in item.groups:
        canonical_node = f"canonical-ref:{item.snapshot_id}:{group.canonical_entity_id}"
        nodes.append(_ref(canonical_node, "canonical_entity", group.canonical_entity_id))
        for member_id in group.member_entity_ids:
            member_node = f"entity-ref:{item.snapshot_id}:{member_id}"
            nodes.append(_ref(member_node, "entity", member_id))
            edges.append(_edge(member_node, canonical_node, "canonicalizes"))
    for left, right in item.distinct_pairs:
        left_node = f"distinct-ref:{item.snapshot_id}:{left}"
        right_node = f"distinct-ref:{item.snapshot_id}:{right}"
        nodes.extend([_ref(left_node, "canonical_entity", left), _ref(right_node, "canonical_entity", right)])
        edges.append(_edge(left_node, right_node, "distinct_from"))
    for index, group in enumerate(item.unresolved_groups):
        for entity_id in group:
            node_id = f"unresolved-ref:{item.snapshot_id}:{index}:{entity_id}"
            nodes.append(_ref(node_id, "entity", entity_id))
            edges.append(_edge(root, node_id, "identity_unresolved", group_index=index))
    for decision_id in item.active_decision_ids:
        node_id = f"active-decision-ref:{item.snapshot_id}:{decision_id}"
        nodes.append(_ref(node_id, "identity_decision", decision_id))
        edges.append(_edge(root, node_id, "uses_active_decision"))
    for decision_id in item.superseded_decision_ids:
        node_id = f"superseded-decision-ref:{item.snapshot_id}:{decision_id}"
        nodes.append(_ref(node_id, "identity_decision", decision_id))
        edges.append(_edge(root, node_id, "records_superseded_decision"))
    return {
        "schema_version": "extended-amr-identity-snapshot-graph-v1",
        "graph_id": f"identity-snapshot-graph:{item.snapshot_id}",
        "root_node_id": root,
        "nodes": nodes,
        "edges": edges,
        "annotations": {
            "schema_version": item.schema_version,
            "snapshot_id": item.snapshot_id,
            "policy_version": item.policy_version,
            "scoped_entity_ids": item.scoped_entity_ids,
            "decision_closure_hashes": item.decision_closure_hashes,
            "input_fingerprint": item.input_fingerprint,
        },
    }


def _aggregate_graph(item: IdentityAggregateClaim) -> dict[str, Any]:
    root = f"identity-aggregate:{item.aggregate_claim_id}"
    nodes = [_ref(root, "identity_aggregate", item.aggregate_claim_id)]
    edges: list[dict[str, Any]] = []
    snapshot_node = f"snapshot-ref:{item.identity_snapshot_id}"
    query_node = f"query-ref:{item.query_id}"
    claim_node = f"claim-ref:{item.supporting_l2_claim_id}"
    nodes.extend(
        [
            _ref(snapshot_node, "identity_snapshot", item.identity_snapshot_id),
            _ref(query_node, "query", item.query_id),
            _ref(claim_node, "l2_claim", item.supporting_l2_claim_id),
        ]
    )
    edges.extend(
        [
            _edge(root, snapshot_node, "uses_identity_snapshot"),
            _edge(root, query_node, "supports_query"),
            _edge(root, claim_node, "supports_l2_claim"),
        ]
    )
    for index, (unit_id, entity_id) in enumerate(
        zip(item.member_l1_unit_ids, item.member_entity_ids, strict=True)
    ):
        unit_node = f"member-ref:{item.aggregate_claim_id}:{index}:{unit_id}"
        entity_node = f"member-entity-ref:{item.aggregate_claim_id}:{index}:{entity_id}"
        nodes.extend([_ref(unit_node, "l1_unit", unit_id), _ref(entity_node, "entity", entity_id)])
        edges.append(
            _edge(
                root,
                unit_node,
                "aggregate_member",
                order=index,
                source_role=item.source_role,
                entity_id=entity_id,
            )
        )
        edges.append(_edge(unit_node, entity_node, "counts_entity"))
    for decision_id in item.identity_decision_ids:
        node_id = f"decision-ref:{item.aggregate_claim_id}:{decision_id}"
        nodes.append(_ref(node_id, "identity_decision", decision_id))
        edges.append(_edge(root, node_id, "authorized_by_decision"))
    for evidence_id in item.required_evidence_ids:
        node_id = f"evidence-ref:{item.aggregate_claim_id}:{evidence_id}"
        nodes.append(_ref(node_id, "evidence", evidence_id))
        edges.append(_edge(root, node_id, "supported_by_evidence"))
    for canonical_id in item.resolved_canonical_entity_ids:
        node_id = f"canonical-ref:{item.aggregate_claim_id}:{canonical_id}"
        nodes.append(_ref(node_id, "canonical_entity", canonical_id))
        edges.append(_edge(root, node_id, "resolves_to_canonical"))
    return {
        "schema_version": "extended-amr-identity-aggregate-graph-v1",
        "graph_id": f"identity-aggregate-graph:{item.aggregate_claim_id}",
        "root_node_id": root,
        "nodes": nodes,
        "edges": edges,
        "annotations": item.model_dump(mode="json"),
    }


def _nodes(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    values = graph.get("nodes", [])
    index = {str(item.get("node_id", "")): item for item in values}
    if len(index) != len(values) or "" in index:
        raise ValueError("graph nodes must have unique non-empty ids")
    return index


def _refs(graph: dict[str, Any], edge_type: str, *, target_type: str | None = None) -> list[str]:
    nodes = _nodes(graph)
    result = []
    for edge in graph.get("edges", []):
        if edge.get("edge_type") != edge_type:
            continue
        target = nodes.get(str(edge.get("target", "")))
        if target is None:
            raise ValueError(f"edge references missing target for {edge_type}")
        if target_type and target.get("node_type") != target_type:
            raise ValueError(f"edge {edge_type} references wrong node type")
        result.append(str(target.get("reference_id", "")))
    return result


def _decode_concept(graph: dict[str, Any]) -> ConceptRegistryEntry:
    item = ConceptRegistryEntry.model_validate(graph["annotations"])
    mapping_refs = _refs(graph, "maps_to", target_type="external_concept_or_property")
    if mapping_refs != [mapping.external_id for mapping in item.external_mappings]:
        raise ValueError("concept mapping edges do not match annotations")
    return item


def _decode_entity(graph: dict[str, Any]) -> EntityRecord:
    item = EntityRecord.model_validate(graph["annotations"])
    if _refs(graph, "instance_of", target_type="concept") != item.concept_ids:
        raise ValueError("entity concept edges do not match annotations")
    if _refs(graph, "supported_by_l1", target_type="l1_unit") != item.source_l1_unit_ids:
        raise ValueError("entity L1 evidence edges do not match annotations")
    if _refs(graph, "supported_by_source", target_type="source_revision") != item.source_revision_ids:
        raise ValueError("entity source evidence edges do not match annotations")
    return item


def _decode_decision(graph: dict[str, Any]) -> IdentityDecision:
    item = IdentityDecision.model_validate(graph["annotations"])
    if _refs(graph, "identity_subject", target_type="entity") != item.subject_entity_ids:
        raise ValueError("identity decision subjects do not match annotations")
    if _refs(graph, "supported_by_l1", target_type="l1_unit") != item.evidence_l1_unit_ids:
        raise ValueError("identity decision evidence edges do not match annotations")
    if _refs(graph, "supported_by_source", target_type="source_revision") != item.evidence_source_revision_ids:
        raise ValueError("identity decision source evidence edges do not match annotations")
    canonical = _refs(graph, "resolves_to", target_type="canonical_entity")
    if canonical != ([item.canonical_entity_id] if item.canonical_entity_id else []):
        raise ValueError("identity decision canonical target does not match annotations")
    return item


def _decode_closure(graph: dict[str, Any]) -> IdentityEvidenceClosure:
    item = IdentityEvidenceClosure.model_validate(graph["annotations"])
    dependencies = []
    nodes = _nodes(graph)
    for edge in graph.get("edges", []):
        if edge.get("edge_type") != "depends_on":
            continue
        target = nodes[str(edge["target"])]
        annotations = edge.get("annotations", {})
        dependencies.append(
            IdentityDependency(
                reference_id=str(target["reference_id"]),
                reference_kind=annotations["reference_kind"],
                content_sha256=annotations["content_sha256"],
            )
        )
    if dependencies != item.dependencies:
        raise ValueError("identity closure dependency edges do not match annotations")
    return item


def _decode_snapshot(graph: dict[str, Any]) -> IdentitySnapshot:
    annotations = graph["annotations"]
    nodes = _nodes(graph)
    groups: dict[str, list[str]] = {}
    distinct_pairs: list[list[str]] = []
    unresolved: dict[int, list[str]] = {}
    active: list[str] = []
    superseded: list[str] = []
    for edge in graph.get("edges", []):
        edge_type = edge.get("edge_type")
        source = nodes.get(str(edge.get("source", "")))
        target = nodes.get(str(edge.get("target", "")))
        if source is None or target is None:
            raise ValueError("identity snapshot edge references missing node")
        if edge_type == "canonicalizes":
            groups.setdefault(str(target["reference_id"]), []).append(str(source["reference_id"]))
        elif edge_type == "distinct_from":
            distinct_pairs.append(sorted([str(source["reference_id"]), str(target["reference_id"])]))
        elif edge_type == "identity_unresolved":
            index = int(edge.get("annotations", {}).get("group_index", 0))
            unresolved.setdefault(index, []).append(str(target["reference_id"]))
        elif edge_type == "uses_active_decision":
            active.append(str(target["reference_id"]))
        elif edge_type == "records_superseded_decision":
            superseded.append(str(target["reference_id"]))
    if not groups:
        raise ValueError("identity snapshot canonical edges are missing")
    return IdentitySnapshot(
        snapshot_id=annotations["snapshot_id"],
        policy_version=annotations["policy_version"],
        scoped_entity_ids=annotations["scoped_entity_ids"],
        groups=[
            CanonicalIdentityGroup(
                canonical_entity_id=canonical_id,
                member_entity_ids=sorted(members),
            )
            for canonical_id, members in sorted(groups.items())
        ],
        distinct_pairs=sorted(distinct_pairs),
        unresolved_groups=[sorted(unresolved[index]) for index in sorted(unresolved)],
        active_decision_ids=active,
        superseded_decision_ids=superseded,
        decision_closure_hashes=annotations["decision_closure_hashes"],
        input_fingerprint=annotations["input_fingerprint"],
    )


def _decode_aggregate(graph: dict[str, Any]) -> IdentityAggregateClaim:
    item = IdentityAggregateClaim.model_validate(graph["annotations"])
    member_edges = [
        edge for edge in graph.get("edges", []) if edge.get("edge_type") == "aggregate_member"
    ]
    member_edges.sort(key=lambda edge: int(edge.get("annotations", {}).get("order", 0)))
    nodes = _nodes(graph)
    unit_ids = [str(nodes[str(edge["target"])]["reference_id"]) for edge in member_edges]
    entity_ids = [str(edge.get("annotations", {}).get("entity_id", "")) for edge in member_edges]
    if unit_ids != item.member_l1_unit_ids or entity_ids != item.member_entity_ids:
        raise ValueError("aggregate member edges do not match annotations")
    if _refs(graph, "uses_identity_snapshot", target_type="identity_snapshot") != [
        item.identity_snapshot_id
    ]:
        raise ValueError("aggregate identity snapshot edge does not match annotations")
    if _refs(graph, "authorized_by_decision", target_type="identity_decision") != item.identity_decision_ids:
        raise ValueError("aggregate decision edges do not match annotations")
    if _refs(graph, "supports_query", target_type="query") != [item.query_id]:
        raise ValueError("aggregate query edge does not match annotations")
    if _refs(graph, "supports_l2_claim", target_type="l2_claim") != [item.supporting_l2_claim_id]:
        raise ValueError("aggregate L2 claim edge does not match annotations")
    return item


class ExtendedAmrV3JsonAdapter:
    def __init__(self, *, profile: RepresentationProfile) -> None:
        self.profile = profile

    def encode(self, bundle: IdentityAwareMemoryBundleV4) -> bytes:
        base = json.loads(ExtendedAmrV2JsonAdapter(profile=self.profile).encode(_base_bundle(bundle)))
        base.update(
            {
                "schema_version": "extended-amr-memory-graph-v3",
                "logical_schema_version": bundle.schema_version,
                "concept_graphs": [_concept_graph(item) for item in bundle.concept_registry],
                "entity_graphs": [_entity_graph(item) for item in bundle.entity_records],
                "identity_decision_graphs": [
                    _decision_graph(item) for item in bundle.identity_decisions
                ],
                "identity_closure_graphs": [
                    _closure_graph(item) for item in bundle.identity_closures
                ],
                "identity_snapshot_graphs": [
                    _snapshot_graph(item) for item in bundle.identity_snapshots
                ],
                "aggregate_graphs": [_aggregate_graph(item) for item in bundle.aggregate_claims],
            }
        )
        return canonical_json_bytes(base)

    def decode(self, payload: Any) -> IdentityAwareMemoryBundleV4:
        if isinstance(payload, bytes):
            data = json.loads(payload)
        elif isinstance(payload, str):
            data = json.loads(payload)
        elif isinstance(payload, dict):
            data = payload
        else:
            raise TypeError(f"unsupported payload type: {type(payload).__name__}")
        if data.get("schema_version") != "extended-amr-memory-graph-v3":
            raise ValueError("unsupported Extended-AMR memory graph version")
        base_data = {
            key: value
            for key, value in data.items()
            if key
            not in {
                "logical_schema_version",
                "concept_graphs",
                "entity_graphs",
                "identity_decision_graphs",
                "identity_closure_graphs",
                "identity_snapshot_graphs",
                "aggregate_graphs",
            }
        }
        base_data["schema_version"] = "extended-amr-memory-graph-v2"
        base = ExtendedAmrV2JsonAdapter(profile=self.profile).decode(base_data)
        bundle = IdentityAwareMemoryBundleV4(
            **base.model_dump(mode="json", exclude={"schema_version"}),
            concept_registry=[_decode_concept(item) for item in data.get("concept_graphs", [])],
            entity_records=[_decode_entity(item) for item in data.get("entity_graphs", [])],
            identity_decisions=[
                _decode_decision(item) for item in data.get("identity_decision_graphs", [])
            ],
            identity_closures=[
                _decode_closure(item) for item in data.get("identity_closure_graphs", [])
            ],
            identity_snapshots=[
                _decode_snapshot(item) for item in data.get("identity_snapshot_graphs", [])
            ],
            aggregate_claims=[
                _decode_aggregate(item) for item in data.get("aggregate_graphs", [])
            ],
        )
        report = assess_identity_bundle_integrity(bundle)
        if not report.valid:
            raise ValueError("identity bundle integrity invalid: " + "; ".join(report.errors))
        return bundle
