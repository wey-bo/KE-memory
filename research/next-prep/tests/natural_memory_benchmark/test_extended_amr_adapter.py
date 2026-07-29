from __future__ import annotations

import json

import pytest

from tools.natural_memory_benchmark.extended_amr_adapter import ExtendedAmrJsonAdapter
from tools.natural_memory_benchmark.representation_contract import (
    REQUIRED_MEMORY_CAPABILITIES,
    CapabilityDeclaration,
    MemoryRepresentationBundle,
    RepresentationProfile,
    evaluate_adapter_conformance,
)
from tools.natural_memory_benchmark.semantic_ir import (
    EvidenceSpan,
    L1MemoryUnit,
    Predicate,
    RoleBinding,
    SourceBinding,
)


def _profile(family: str, representation_id: str) -> RepresentationProfile:
    return RepresentationProfile(
        representation_id=representation_id,
        family=family,  # type: ignore[arg-type]
        format_version="test-v1",
        role="exchange",
        capabilities=[
            CapabilityDeclaration(capability=capability, support_mode="native", location="test")
            for capability in REQUIRED_MEMORY_CAPABILITIES
        ],
    )


def _bundle() -> MemoryRepresentationBundle:
    text = "Even if the timeline is tight, I would launch if the budget is approved."
    unit = L1MemoryUnit(
        unit_id="l1-concession-condition",
        kind="event",
        predicate=Predicate(surface="launch", sense="launch-01", canonical_operator="launch"),
        roles=[
            RoleBinding(role="ARG0", entity_id="user", role_name="agent"),
            RoleBinding(role="ARG1", entity_id="product", role_name="theme"),
            RoleBinding(role="condition", entity_id="budget_approved", role_name="condition"),
            RoleBinding(role="concession", entity_id="timeline_tight", role_name="concession"),
        ],
        modality="hypothetical",
        polarity="negative",
        time={"event_time": "future", "valid_time": "conditional", "transaction_time": "2026-07-27T12:00:00Z"},
        source=SourceBinding(
            speaker="user",
            source_status="user_reported",
            evidence_spans=[
                EvidenceSpan(
                    evidence_id="E-concession",
                    turn_id="turn-concession",
                    session_id="session-concession",
                    char_start=0,
                    char_end=len(text),
                    text=text,
                )
            ],
        ),
        lifecycle="candidate",
    )
    return MemoryRepresentationBundle(
        bundle_id="bundle-extended-amr-test",
        profile=_profile("semantic_ir", "logical-test-carrier"),
        l1_units=[unit],
        l2_units=[],
        closures=[],
        query_plans=[],
        metadata={"scope": "extended amr adapter test"},
    )


def test_extended_amr_payload_uses_explicit_nodes_edges_and_memory_annotations():
    bundle = _bundle()
    adapter = ExtendedAmrJsonAdapter(profile=_profile("extended_amr", "extended-amr-test"))

    payload = json.loads(adapter.encode(bundle))

    assert payload["schema_version"] == "extended-amr-memory-graph-v1"
    assert "l1_units" not in payload
    assert "l2_units" not in payload
    graph = payload["graphs"][0]
    assert graph["level"] == "L1"
    assert {node["node_type"] for node in graph["nodes"]} == {"predicate", "entity"}
    assert [edge["role"] for edge in graph["edges"]] == [
        "ARG0",
        "ARG1",
        "condition",
        "concession",
    ]
    assert graph["annotations"]["modality"] == "hypothetical"
    assert graph["annotations"]["polarity"] == "negative"
    assert graph["annotations"]["source"]["evidence_spans"][0]["evidence_id"] == "E-concession"


def test_extended_amr_adapter_round_trips_condition_concession_and_memory_semantics():
    bundle = _bundle()
    adapter = ExtendedAmrJsonAdapter(profile=_profile("extended_amr", "extended-amr-test"))

    decoded = adapter.decode(adapter.encode(bundle))
    report = evaluate_adapter_conformance(adapter, bundle)

    assert decoded == bundle
    assert decoded.l1_units[0].roles[2].role == "condition"
    assert decoded.l1_units[0].roles[3].role == "concession"
    assert decoded.l1_units[0].modality == "hypothetical"
    assert decoded.l1_units[0].polarity == "negative"
    assert report.round_trip_exact is True
    assert report.status == "pass"


def test_extended_amr_adapter_rejects_missing_predicate_node():
    adapter = ExtendedAmrJsonAdapter(profile=_profile("extended_amr", "extended-amr-test"))
    payload = json.loads(adapter.encode(_bundle()))
    payload["graphs"][0]["nodes"] = [
        node for node in payload["graphs"][0]["nodes"] if node["node_type"] != "predicate"
    ]

    with pytest.raises(ValueError, match="predicate"):
        adapter.decode(payload)


def test_extended_amr_adapter_rejects_duplicate_role_edge():
    adapter = ExtendedAmrJsonAdapter(profile=_profile("extended_amr", "extended-amr-test"))
    payload = json.loads(adapter.encode(_bundle()))
    duplicate = dict(payload["graphs"][0]["edges"][0])
    duplicate["edge_id"] = "duplicate-edge"
    duplicate["ordinal"] = len(payload["graphs"][0]["edges"])
    payload["graphs"][0]["edges"].append(duplicate)

    with pytest.raises(ValueError, match="duplicate role edge"):
        adapter.decode(payload)


def test_extended_amr_adapter_rejects_missing_required_memory_annotation():
    adapter = ExtendedAmrJsonAdapter(profile=_profile("extended_amr", "extended-amr-test"))
    payload = json.loads(adapter.encode(_bundle()))
    del payload["graphs"][0]["annotations"]["source"]

    with pytest.raises(ValueError, match="source"):
        adapter.decode(payload)
