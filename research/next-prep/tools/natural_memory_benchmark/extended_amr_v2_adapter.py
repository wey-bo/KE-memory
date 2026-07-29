from __future__ import annotations

import json
from typing import Any

from .authoritative_memory import (
    AggregateClaim,
    AuthoritativeQueryPlan,
    ClaimClosureContext,
    ClosureEvaluation,
    ClosureSpec,
    EvidenceSpanV2,
    L1MemoryUnitV2,
    L2MemoryUnitV2,
    L2StructuredClaim,
    MemoryRepresentationBundleV3,
    MemoryUnitRevision,
    ProducerIdentity,
    QueryClosureContext,
    RawArtifactRevision,
    SourceBindingV2,
    SourceRecordRevision,
    assess_authoritative_bundle_integrity,
    canonical_sha256,
)
from .io import canonical_json_bytes
from .representation_contract import RepresentationProfile
from .semantic_ir import EpistemicBinding, LinkBinding, Predicate, RoleBinding, TimeBinding


def _graph_id(revision: MemoryUnitRevision) -> str:
    return f"amr-graph-{revision.revision_id}"


def _edge(
    graph_id: str,
    index: int,
    *,
    edge_type: str,
    source: str,
    target: str,
    ordinal: int,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "edge_id": f"{graph_id}:edge:{index}",
        "edge_type": edge_type,
        "source": source,
        "target": target,
        "ordinal": ordinal,
        **extra,
    }


def _reference_node(
    graph_id: str,
    index: int,
    *,
    reference_type: str,
    reference_id: str,
) -> dict[str, Any]:
    return {
        "node_id": f"{graph_id}:reference:{index}",
        "node_type": "reference",
        "reference_type": reference_type,
        "reference_id": reference_id,
    }


def _encode_l1_graph(revision: MemoryUnitRevision, payload: L1MemoryUnitV2) -> dict[str, Any]:
    graph_id = _graph_id(revision)
    predicate_id = f"{graph_id}:predicate"
    nodes: list[dict[str, Any]] = [
        {
            "node_id": predicate_id,
            "node_type": "predicate",
            "predicate": payload.predicate.model_dump(mode="json"),
        }
    ]
    edges: list[dict[str, Any]] = []
    for index, role in enumerate(payload.roles):
        entity_id = f"{graph_id}:entity:{index}"
        nodes.append(
            {
                "node_id": entity_id,
                "node_type": "entity",
                "entity_id": role.entity_id,
            }
        )
        edges.append(
            _edge(
                graph_id,
                index,
                edge_type="role",
                source=predicate_id,
                target=entity_id,
                ordinal=index,
                role=role.role,
                role_name=role.role_name,
            )
        )
    return {
        "schema_version": "extended-amr-unit-graph-v2",
        "graph_id": graph_id,
        "unit_revision_id": revision.revision_id,
        "memory_unit_id": payload.unit_id,
        "level": "L1",
        "nodes": nodes,
        "edges": edges,
        "annotations": {
            "kind": payload.kind,
            "modality": payload.modality,
            "polarity": payload.polarity,
            "time": payload.time.model_dump(mode="json"),
            "source": payload.source.model_dump(mode="json"),
            "epistemic": payload.epistemic.model_dump(mode="json"),
            "links": payload.links.model_dump(mode="json"),
            "lifecycle": payload.lifecycle,
        },
    }


def _encode_l2_graph(revision: MemoryUnitRevision, payload: L2MemoryUnitV2) -> dict[str, Any]:
    graph_id = _graph_id(revision)
    abstraction_id = f"{graph_id}:abstraction"
    nodes: list[dict[str, Any]] = [
        {
            "node_id": abstraction_id,
            "node_type": "abstraction",
            "summary": payload.summary,
            "display_assertions": list(payload.display_assertions),
        }
    ]
    edges: list[dict[str, Any]] = []
    edge_index = 0
    reference_index = 0

    def add_reference(
        *,
        reference_type: str,
        reference_id: str,
        edge_type: str,
        ordinal: int,
        source: str = abstraction_id,
        **extra: Any,
    ) -> None:
        nonlocal edge_index, reference_index
        node = _reference_node(
            graph_id,
            reference_index,
            reference_type=reference_type,
            reference_id=reference_id,
        )
        reference_index += 1
        nodes.append(node)
        edges.append(
            _edge(
                graph_id,
                edge_index,
                edge_type=edge_type,
                source=source,
                target=node["node_id"],
                ordinal=ordinal,
                **extra,
            )
        )
        edge_index += 1

    for claim_ordinal, claim in enumerate(payload.structured_claims):
        claim_node_id = f"{graph_id}:claim:{claim_ordinal}"
        nodes.append(
            {
                "node_id": claim_node_id,
                "node_type": "claim_predicate",
                "claim_id": claim.claim_id,
                "predicate": claim.predicate.model_dump(mode="json"),
                "modality": claim.modality,
                "polarity": claim.polarity,
                "time": claim.time.model_dump(mode="json"),
                "aggregate": claim.aggregate.model_dump(mode="json") if claim.aggregate else None,
            }
        )
        edges.append(
            _edge(
                graph_id,
                edge_index,
                edge_type="contains_claim",
                source=abstraction_id,
                target=claim_node_id,
                ordinal=claim_ordinal,
            )
        )
        edge_index += 1
        for role_ordinal, role in enumerate(claim.roles):
            entity_node_id = f"{claim_node_id}:entity:{role_ordinal}"
            nodes.append(
                {
                    "node_id": entity_node_id,
                    "node_type": "entity",
                    "entity_id": role.entity_id,
                }
            )
            edges.append(
                _edge(
                    graph_id,
                    edge_index,
                    edge_type="claim_role",
                    source=claim_node_id,
                    target=entity_node_id,
                    ordinal=role_ordinal,
                    role=role.role,
                    role_name=role.role_name,
                )
            )
            edge_index += 1
        for support_ordinal, support_id in enumerate(claim.supporting_l1_units):
            add_reference(
                reference_type="l1_unit",
                reference_id=support_id,
                edge_type="claim_support",
                ordinal=support_ordinal,
                source=claim_node_id,
            )

    for ordinal, unit_id in enumerate(payload.abstracts):
        add_reference(
            reference_type="l1_unit",
            reference_id=unit_id,
            edge_type="abstracts_l1",
            ordinal=ordinal,
        )
    for ordinal, unit_id in enumerate(payload.source_l1_units):
        add_reference(
            reference_type="l1_unit",
            reference_id=unit_id,
            edge_type="source_l1",
            ordinal=ordinal,
        )
    for ordinal, turn_id in enumerate(payload.source_turns):
        add_reference(
            reference_type="source_turn",
            reference_id=turn_id,
            edge_type="source_turn",
            ordinal=ordinal,
        )
    for ordinal, session_id in enumerate(payload.source_sessions):
        add_reference(
            reference_type="source_session",
            reference_id=session_id,
            edge_type="source_session",
            ordinal=ordinal,
        )
    add_reference(
        reference_type="closure_spec",
        reference_id=payload.closure_id,
        edge_type="closure_spec_reference",
        ordinal=0,
        spec_revision=payload.closure_spec_revision,
    )
    add_reference(
        reference_type="closure_evaluation",
        reference_id=payload.closure_evaluation_id,
        edge_type="closure_evaluation_reference",
        ordinal=0,
    )
    return {
        "schema_version": "extended-amr-unit-graph-v2",
        "graph_id": graph_id,
        "unit_revision_id": revision.revision_id,
        "memory_unit_id": payload.unit_id,
        "level": "L2",
        "nodes": nodes,
        "edges": edges,
        "annotations": {
            "kind": payload.kind,
            "lifecycle": payload.lifecycle,
            "valid_time": payload.valid_time,
            "abstraction_method": payload.abstraction_method,
        },
    }


def _encode_graph(revision: MemoryUnitRevision) -> dict[str, Any]:
    if isinstance(revision.payload, L1MemoryUnitV2):
        return _encode_l1_graph(revision, revision.payload)
    return _encode_l2_graph(revision, revision.payload)


def _revision_header(revision: MemoryUnitRevision) -> dict[str, Any]:
    return {
        "schema_version": "extended-amr-unit-revision-header-v1",
        "memory_unit_id": revision.memory_unit_id,
        "revision_id": revision.revision_id,
        "revision_number": revision.revision_number,
        "previous_revision_id": revision.previous_revision_id,
        "revision_kind": revision.revision_kind,
        "transaction_time": revision.transaction_time,
        "payload_sha256": revision.payload_sha256,
        "source_revision_ids": list(revision.source_revision_ids),
        "derived_from_revision_ids": list(revision.derived_from_revision_ids),
        "producer": revision.producer.model_dump(mode="json"),
        "graph_id": _graph_id(revision),
    }


def _node_index(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        raise ValueError("graph nodes must be a list")
    index: dict[str, dict[str, Any]] = {}
    for node in nodes:
        node_id = str(node.get("node_id", ""))
        if not node_id or node_id in index:
            raise ValueError("graph node ids must be non-empty and unique")
        index[node_id] = node
    return index


def _edges_of(graph: dict[str, Any], edge_type: str, *, source: str | None = None) -> list[dict[str, Any]]:
    edges = [edge for edge in graph.get("edges", []) if edge.get("edge_type") == edge_type]
    if source is not None:
        edges = [edge for edge in edges if edge.get("source") == source]
    return sorted(edges, key=lambda item: int(item.get("ordinal", -1)))


def _reference_id(nodes: dict[str, dict[str, Any]], edge: dict[str, Any], expected_type: str) -> str:
    target = nodes.get(str(edge.get("target", "")))
    if target is None or target.get("node_type") != "reference":
        raise ValueError(f"{edge.get('edge_type')} must target a reference node")
    if target.get("reference_type") != expected_type:
        raise ValueError(
            f"{edge.get('edge_type')} reference type must be {expected_type}"
        )
    return str(target.get("reference_id", ""))


def _decode_l1_graph(graph: dict[str, Any]) -> L1MemoryUnitV2:
    nodes = _node_index(graph)
    predicates = [node for node in nodes.values() if node.get("node_type") == "predicate"]
    if len(predicates) != 1:
        raise ValueError("L1 graph requires exactly one predicate node")
    predicate_node = predicates[0]
    roles: list[RoleBinding] = []
    for edge in _edges_of(graph, "role", source=str(predicate_node["node_id"])):
        target = nodes.get(str(edge.get("target", "")))
        if target is None or target.get("node_type") != "entity":
            raise ValueError("L1 role edge must target an entity node")
        roles.append(
            RoleBinding(
                role=str(edge["role"]),
                entity_id=str(target["entity_id"]),
                role_name=str(edge["role_name"]),
            )
        )
    if not roles:
        raise ValueError("L1 graph requires role edges")
    annotations = graph.get("annotations", {})
    return L1MemoryUnitV2(
        unit_id=str(graph["memory_unit_id"]),
        kind=annotations["kind"],
        predicate=Predicate.model_validate(predicate_node["predicate"]),
        roles=roles,
        modality=annotations["modality"],
        polarity=annotations["polarity"],
        time=TimeBinding.model_validate(annotations["time"]),
        source=SourceBindingV2.model_validate(annotations["source"]),
        epistemic=EpistemicBinding.model_validate(annotations["epistemic"]),
        links=LinkBinding.model_validate(annotations["links"]),
        lifecycle=annotations["lifecycle"],
    )


def _decode_l2_graph(graph: dict[str, Any]) -> L2MemoryUnitV2:
    nodes = _node_index(graph)
    abstractions = [node for node in nodes.values() if node.get("node_type") == "abstraction"]
    if len(abstractions) != 1:
        raise ValueError("L2 graph requires exactly one abstraction node")
    abstraction = abstractions[0]
    abstraction_id = str(abstraction["node_id"])
    claims: list[L2StructuredClaim] = []
    for contains_edge in _edges_of(graph, "contains_claim", source=abstraction_id):
        claim_node = nodes.get(str(contains_edge.get("target", "")))
        if claim_node is None or claim_node.get("node_type") != "claim_predicate":
            raise ValueError("contains_claim must target a claim predicate node")
        claim_node_id = str(claim_node["node_id"])
        roles: list[RoleBinding] = []
        for role_edge in _edges_of(graph, "claim_role", source=claim_node_id):
            entity = nodes.get(str(role_edge.get("target", "")))
            if entity is None or entity.get("node_type") != "entity":
                raise ValueError("claim role edge must target an entity node")
            roles.append(
                RoleBinding(
                    role=str(role_edge["role"]),
                    entity_id=str(entity["entity_id"]),
                    role_name=str(role_edge["role_name"]),
                )
            )
        if not roles:
            raise ValueError(f"claim role edges missing for {claim_node.get('claim_id')}")
        supports = [
            _reference_id(nodes, edge, "l1_unit")
            for edge in _edges_of(graph, "claim_support", source=claim_node_id)
        ]
        if not supports:
            raise ValueError(f"claim support edges missing for {claim_node.get('claim_id')}")
        aggregate = claim_node.get("aggregate")
        claims.append(
            L2StructuredClaim(
                claim_id=str(claim_node["claim_id"]),
                predicate=Predicate.model_validate(claim_node["predicate"]),
                roles=roles,
                modality=claim_node["modality"],
                polarity=claim_node["polarity"],
                time=TimeBinding.model_validate(claim_node["time"]),
                supporting_l1_units=supports,
                aggregate=AggregateClaim.model_validate(aggregate) if aggregate else None,
            )
        )

    def refs(edge_type: str, reference_type: str) -> list[str]:
        return [
            _reference_id(nodes, edge, reference_type)
            for edge in _edges_of(graph, edge_type, source=abstraction_id)
        ]

    spec_edges = _edges_of(graph, "closure_spec_reference", source=abstraction_id)
    evaluation_edges = _edges_of(graph, "closure_evaluation_reference", source=abstraction_id)
    if len(spec_edges) != 1 or len(evaluation_edges) != 1:
        raise ValueError("L2 graph requires one closure spec and one closure evaluation reference")
    annotations = graph.get("annotations", {})
    return L2MemoryUnitV2(
        unit_id=str(graph["memory_unit_id"]),
        kind=annotations["kind"],
        abstracts=refs("abstracts_l1", "l1_unit"),
        summary=str(abstraction["summary"]),
        display_assertions=list(abstraction.get("display_assertions", [])),
        structured_claims=claims,
        closure_id=_reference_id(nodes, spec_edges[0], "closure_spec"),
        closure_spec_revision=int(spec_edges[0]["spec_revision"]),
        closure_evaluation_id=_reference_id(
            nodes, evaluation_edges[0], "closure_evaluation"
        ),
        lifecycle=annotations["lifecycle"],
        valid_time=annotations.get("valid_time"),
        abstraction_method=dict(annotations.get("abstraction_method", {})),
        source_l1_units=refs("source_l1", "l1_unit"),
        source_turns=refs("source_turn", "source_turn"),
        source_sessions=refs("source_session", "source_session"),
    )


def _decode_graph(graph: dict[str, Any]) -> L1MemoryUnitV2 | L2MemoryUnitV2:
    if graph.get("schema_version") != "extended-amr-unit-graph-v2":
        raise ValueError("unsupported Extended-AMR unit graph version")
    if graph.get("level") == "L1":
        return _decode_l1_graph(graph)
    if graph.get("level") == "L2":
        return _decode_l2_graph(graph)
    raise ValueError(f"unsupported graph level: {graph.get('level')}")


class ExtendedAmrV2JsonAdapter:
    def __init__(self, *, profile: RepresentationProfile) -> None:
        self.profile = profile

    def encode(self, bundle: MemoryRepresentationBundleV3) -> bytes:
        graphs = [_encode_graph(revision) for revision in bundle.unit_revisions]
        payload = {
            "schema_version": "extended-amr-memory-graph-v2",
            "bundle_id": bundle.bundle_id,
            "representation_profile": self.profile.model_dump(mode="json"),
            "logical_profile": bundle.profile.model_dump(mode="json"),
            "raw_artifact_revisions": [
                item.model_dump(mode="json") for item in bundle.raw_artifact_revisions
            ],
            "source_record_revisions": [
                item.model_dump(mode="json") for item in bundle.source_record_revisions
            ],
            "unit_revision_headers": [
                _revision_header(item) for item in bundle.unit_revisions
            ],
            "current_revision_ids": dict(bundle.current_revision_ids),
            "current_unit_order": [
                item.unit_id for item in [*bundle.l1_units, *bundle.l2_units]
            ],
            "graphs": graphs,
            "closure_specs": [item.model_dump(mode="json") for item in bundle.closure_specs],
            "closure_evaluations": [
                item.model_dump(mode="json") for item in bundle.closure_evaluations
            ],
            "query_plans": [item.model_dump(mode="json") for item in bundle.query_plans],
            "query_unit_scopes": bundle.query_unit_scopes,
            "metadata": bundle.metadata,
        }
        return canonical_json_bytes(payload)

    def decode(self, payload: Any) -> MemoryRepresentationBundleV3:
        if isinstance(payload, bytes):
            data = json.loads(payload)
        elif isinstance(payload, str):
            data = json.loads(payload)
        elif isinstance(payload, dict):
            data = payload
        else:
            raise TypeError(f"unsupported payload type: {type(payload).__name__}")
        if data.get("schema_version") != "extended-amr-memory-graph-v2":
            raise ValueError("unsupported Extended-AMR memory graph version")

        graph_by_id: dict[str, dict[str, Any]] = {}
        for graph in data.get("graphs", []):
            graph_id = str(graph.get("graph_id", ""))
            if not graph_id or graph_id in graph_by_id:
                raise ValueError("graph ids must be non-empty and unique")
            graph_by_id[graph_id] = graph
        unit_revisions: list[MemoryUnitRevision] = []
        for header in data.get("unit_revision_headers", []):
            graph = graph_by_id.get(str(header.get("graph_id", "")))
            if graph is None:
                raise ValueError(f"unit revision has missing graph {header.get('graph_id')}")
            payload_value = _decode_graph(graph)
            revision = MemoryUnitRevision.model_validate(
                {
                    "memory_unit_id": header["memory_unit_id"],
                    "revision_id": header["revision_id"],
                    "revision_number": header["revision_number"],
                    "previous_revision_id": header.get("previous_revision_id"),
                    "revision_kind": header["revision_kind"],
                    "transaction_time": header["transaction_time"],
                    "payload_sha256": header["payload_sha256"],
                    "payload": payload_value.model_dump(mode="json"),
                    "source_revision_ids": header.get("source_revision_ids", []),
                    "derived_from_revision_ids": header.get("derived_from_revision_ids", []),
                    "producer": ProducerIdentity.model_validate(header["producer"]).model_dump(mode="json"),
                }
            )
            if graph.get("unit_revision_id") != revision.revision_id:
                raise ValueError("graph unit revision id does not match revision header")
            if graph.get("memory_unit_id") != revision.memory_unit_id:
                raise ValueError("graph memory unit id does not match revision header")
            if canonical_sha256(revision.payload) != revision.payload_sha256:
                raise ValueError(f"unit revision payload hash mismatch: {revision.revision_id}")
            unit_revisions.append(revision)
        revisions_by_id = {item.revision_id: item for item in unit_revisions}
        current_ids = dict(data.get("current_revision_ids", {}))
        current_order = list(data.get("current_unit_order", []))
        if not current_order:
            current_order = [
                revision.memory_unit_id
                for revision in unit_revisions
                if revision.revision_id in set(current_ids.values())
            ]
        current_payloads = []
        for unit_id in current_order:
            revision_id = current_ids.get(unit_id)
            if revision_id is None or revision_id not in revisions_by_id:
                continue
            current_payloads.append(revisions_by_id[revision_id].payload)
        bundle = MemoryRepresentationBundleV3(
            bundle_id=data["bundle_id"],
            profile=RepresentationProfile.model_validate(data["logical_profile"]),
            raw_artifact_revisions=[
                RawArtifactRevision.model_validate(item)
                for item in data.get("raw_artifact_revisions", [])
            ],
            source_record_revisions=[
                SourceRecordRevision.model_validate(item)
                for item in data.get("source_record_revisions", [])
            ],
            unit_revisions=unit_revisions,
            current_revision_ids=current_ids,
            l1_units=[item for item in current_payloads if isinstance(item, L1MemoryUnitV2)],
            l2_units=[item for item in current_payloads if isinstance(item, L2MemoryUnitV2)],
            closure_specs=[
                ClosureSpec.model_validate(item) for item in data.get("closure_specs", [])
            ],
            closure_evaluations=[
                ClosureEvaluation.model_validate(item)
                for item in data.get("closure_evaluations", [])
            ],
            query_plans=[
                AuthoritativeQueryPlan.model_validate(item)
                for item in data.get("query_plans", [])
            ],
            query_unit_scopes={
                str(key): list(value)
                for key, value in data.get("query_unit_scopes", {}).items()
            },
            metadata=dict(data.get("metadata", {})),
        )
        report = assess_authoritative_bundle_integrity(bundle)
        if not report.valid:
            raise ValueError(
                "authoritative bundle integrity invalid: " + "; ".join(report.errors)
            )
        return bundle
