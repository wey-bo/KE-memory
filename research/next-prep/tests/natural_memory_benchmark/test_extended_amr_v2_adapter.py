from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.natural_memory_benchmark.authoritative_memory import (
    L1MemoryUnitV2,
    ProducerIdentity,
    build_real_slice_authoritative_bundle,
    make_memory_unit_revision,
)
from tools.natural_memory_benchmark.extended_amr_v2_adapter import ExtendedAmrV2JsonAdapter
from tools.natural_memory_benchmark.representation_contract import (
    REQUIRED_MEMORY_CAPABILITIES,
    CapabilityDeclaration,
    RepresentationProfile,
)


ROOT = Path("artifacts/natural-benchmark-slices")
SLICE_ID = "slice-v1"
RESULTS = ROOT / SLICE_ID / "symbolic-fallback-answerability-v2-fastembed-results.json"


def _producer() -> ProducerIdentity:
    return ProducerIdentity(
        workflow_run_id="run-amr-v2-test",
        producer_id="extended-amr-v2-test",
        producer_version="1",
    )


def _bundle():
    return build_real_slice_authoritative_bundle(
        ROOT,
        SLICE_ID,
        RESULTS,
        transaction_time="2026-07-27T12:00:00Z",
        producer=_producer(),
        query_answer_kinds={"LONGMEMEVAL-6d550036": "count"},
    )


def _profile() -> RepresentationProfile:
    return RepresentationProfile(
        representation_id="extended-amr-memory-graph-candidate-v2",
        family="extended_amr",
        format_version="extended-amr-memory-graph-v2",
        role="authoritative_candidate",
        capabilities=[
            CapabilityDeclaration(capability=name, support_mode="extension", location="v2 graph")
            for name in REQUIRED_MEMORY_CAPABILITIES
        ],
    )


def test_v2_payload_has_typed_ledgers_and_no_opaque_unit_payload_copies():
    payload = json.loads(ExtendedAmrV2JsonAdapter(profile=_profile()).encode(_bundle()))

    assert payload["schema_version"] == "extended-amr-memory-graph-v2"
    assert "l1_units" not in payload
    assert "l2_units" not in payload
    assert "unit_revisions" not in payload
    assert len(payload["raw_artifact_revisions"]) == 2
    assert len(payload["source_record_revisions"]) == 13
    assert len(payload["unit_revision_headers"]) == 14
    assert all("payload" not in item for item in payload["unit_revision_headers"])
    assert payload["current_revision_ids"] == _bundle().current_revision_ids
    assert len(payload["closure_specs"]) == 6
    assert len(payload["closure_evaluations"]) == 6


def test_l1_and_l2_graphs_use_explicit_predicates_roles_claim_support_and_closure_refs():
    bundle = _bundle()
    payload = json.loads(ExtendedAmrV2JsonAdapter(profile=_profile()).encode(bundle))

    l1_graph = next(graph for graph in payload["graphs"] if graph["level"] == "L1")
    assert {node["node_type"] for node in l1_graph["nodes"]} == {"predicate", "entity"}
    assert any(edge["edge_type"] == "role" for edge in l1_graph["edges"])
    assert l1_graph["annotations"]["source"]["evidence_spans"][0]["source_revision_id"]

    l2_graph = next(graph for graph in payload["graphs"] if graph["level"] == "L2")
    node_types = {node["node_type"] for node in l2_graph["nodes"]}
    assert {"abstraction", "claim_predicate", "entity", "reference"}.issubset(node_types)
    edge_types = {edge["edge_type"] for edge in l2_graph["edges"]}
    assert {
        "contains_claim",
        "claim_role",
        "claim_support",
        "abstracts_l1",
        "source_l1",
        "source_turn",
        "source_session",
        "closure_spec_reference",
        "closure_evaluation_reference",
    }.issubset(edge_types)
    abstraction = next(node for node in l2_graph["nodes"] if node["node_type"] == "abstraction")
    assert abstraction["display_assertions"] == ["count(led_projects_by_user)=2"]
    claim = next(node for node in l2_graph["nodes"] if node["node_type"] == "claim_predicate")
    assert claim["predicate"]["sense"] == "lead/manage"
    assert claim["aggregate"] is None


def test_extended_amr_v2_exactly_round_trips_the_authoritative_bundle():
    bundle = _bundle()
    adapter = ExtendedAmrV2JsonAdapter(profile=_profile())

    decoded = adapter.decode(adapter.encode(bundle))

    assert decoded == bundle


def test_extended_amr_v2_round_trips_an_unrelated_two_revision_history():
    bundle = _bundle()
    seed = bundle.l1_units[0]
    extra_v1 = seed.model_copy(
        update={"unit_id": "l1-unrelated-history", "lifecycle": "active"}
    )
    revision_one = make_memory_unit_revision(
        payload=extra_v1,
        revision_number=1,
        previous_revision_id=None,
        revision_kind="create",
        transaction_time="2026-07-27T13:00:00Z",
        source_revision_ids=bundle.unit_revisions[0].source_revision_ids,
        derived_from_revision_ids=[],
        producer=_producer(),
    )
    extra_v2 = extra_v1.model_copy(update={"lifecycle": "superseded"})
    revision_two = make_memory_unit_revision(
        payload=extra_v2,
        revision_number=2,
        previous_revision_id=revision_one.revision_id,
        revision_kind="lifecycle_update",
        transaction_time="2026-07-27T14:00:00Z",
        source_revision_ids=revision_one.source_revision_ids,
        derived_from_revision_ids=[],
        producer=_producer(),
    )
    expanded = bundle.model_copy(
        update={
            "l1_units": [*bundle.l1_units, extra_v2],
            "unit_revisions": [*bundle.unit_revisions, revision_one, revision_two],
            "current_revision_ids": {
                **bundle.current_revision_ids,
                extra_v2.unit_id: revision_two.revision_id,
            },
        }
    )
    adapter = ExtendedAmrV2JsonAdapter(profile=_profile())

    decoded = adapter.decode(adapter.encode(expanded))

    assert decoded == expanded
    assert [
        item.revision_number
        for item in decoded.unit_revisions
        if item.memory_unit_id == extra_v2.unit_id
    ] == [1, 2]


def test_decode_rejects_missing_claim_support_and_role_edges():
    adapter = ExtendedAmrV2JsonAdapter(profile=_profile())
    payload = json.loads(adapter.encode(_bundle()))
    l2_graph = next(graph for graph in payload["graphs"] if graph["level"] == "L2")
    l2_graph["edges"] = [
        edge for edge in l2_graph["edges"] if edge["edge_type"] != "claim_support"
    ]
    with pytest.raises(ValueError, match="claim support"):
        adapter.decode(payload)

    payload = json.loads(adapter.encode(_bundle()))
    l2_graph = next(graph for graph in payload["graphs"] if graph["level"] == "L2")
    l2_graph["edges"] = [
        edge for edge in l2_graph["edges"] if edge["edge_type"] != "claim_role"
    ]
    with pytest.raises(ValueError, match="claim role"):
        adapter.decode(payload)


def test_decode_rejects_tampered_closure_policy_spec_and_current_pointer():
    adapter = ExtendedAmrV2JsonAdapter(profile=_profile())
    payload = json.loads(adapter.encode(_bundle()))
    payload["closure_evaluations"][0]["policy_version"] = "tampered"
    with pytest.raises(ValueError, match="closure|integrity|fresh"):
        adapter.decode(payload)

    payload = json.loads(adapter.encode(_bundle()))
    payload["closure_specs"][0]["revision"] = 99
    with pytest.raises(ValueError, match="closure|integrity|spec"):
        adapter.decode(payload)

    payload = json.loads(adapter.encode(_bundle()))
    payload["current_revision_ids"].pop(next(iter(payload["current_revision_ids"])))
    with pytest.raises(ValueError, match="current revision|current pointer|integrity"):
        adapter.decode(payload)

