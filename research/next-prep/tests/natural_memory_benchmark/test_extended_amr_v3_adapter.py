from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from tools.natural_memory_benchmark.extended_amr_v3_adapter import ExtendedAmrV3JsonAdapter
from tools.natural_memory_benchmark.identity_resolution import (
    build_identity_scenario_bundle,
    execute_identity_aware_query,
    identity_extended_amr_profile,
)


EXPERIMENT_ROOT = Path("artifacts/identity-memory-experiment")


def _adapter() -> ExtendedAmrV3JsonAdapter:
    return ExtendedAmrV3JsonAdapter(profile=identity_extended_amr_profile())


def test_v3_payload_is_explicit_and_contains_no_opaque_native_bundle_copy():
    bundle = build_identity_scenario_bundle(
        EXPERIMENT_ROOT, "ID-HIDDEN-003-four-mentions-two-entities"
    )
    data = json.loads(_adapter().encode(bundle))

    assert data["schema_version"] == "extended-amr-memory-graph-v3"
    assert "native_bundle" not in data
    assert "identity_aware_bundle" not in data
    assert len(data["concept_graphs"]) >= 8
    assert len(data["entity_graphs"]) == 4
    assert len(data["identity_decision_graphs"]) == 3
    assert len(data["identity_snapshot_graphs"]) == 1
    assert len(data["aggregate_graphs"]) == 1

    aggregate = data["aggregate_graphs"][0]
    edge_types = {edge["edge_type"] for edge in aggregate["edges"]}
    assert {
        "aggregate_member",
        "uses_identity_snapshot",
        "authorized_by_decision",
        "supports_query",
        "supports_l2_claim",
    }.issubset(edge_types)


def test_extended_amr_v3_exactly_round_trips_all_frozen_scenarios_with_query_parity():
    source = json.loads(
        (EXPERIMENT_ROOT / "gold-v1" / "source-scenarios.json").read_text(encoding="utf-8")
    )
    adapter = _adapter()
    for scenario in source["scenarios"]:
        bundle = build_identity_scenario_bundle(EXPERIMENT_ROOT, scenario["scenario_id"])
        decoded = adapter.decode(adapter.encode(bundle))
        assert decoded == bundle
        assert execute_identity_aware_query(decoded.query_plans[0], decoded) == execute_identity_aware_query(
            bundle.query_plans[0], bundle
        )


def test_decode_rejects_missing_identity_evidence_canonicalization_and_aggregate_edges():
    bundle = build_identity_scenario_bundle(EXPERIMENT_ROOT, "ID-DEV-001-alias-shared-identifier")
    adapter = _adapter()
    data = json.loads(adapter.encode(bundle))

    missing_evidence = deepcopy(data)
    decision_graph = missing_evidence["identity_decision_graphs"][0]
    decision_graph["edges"] = [
        edge for edge in decision_graph["edges"] if edge["edge_type"] != "supported_by_l1"
    ]
    with pytest.raises(ValueError, match="identity decision evidence"):
        adapter.decode(missing_evidence)

    missing_canonical = deepcopy(data)
    snapshot_graph = missing_canonical["identity_snapshot_graphs"][0]
    snapshot_graph["edges"] = [
        edge for edge in snapshot_graph["edges"] if edge["edge_type"] != "canonicalizes"
    ]
    with pytest.raises(ValueError, match="identity snapshot canonical"):
        adapter.decode(missing_canonical)

    missing_member = deepcopy(data)
    aggregate_graph = missing_member["aggregate_graphs"][0]
    aggregate_graph["edges"] = [
        edge for edge in aggregate_graph["edges"] if edge["edge_type"] != "aggregate_member"
    ]
    with pytest.raises(ValueError, match="aggregate member"):
        adapter.decode(missing_member)


def test_decode_rejects_tampered_decision_status_snapshot_hash_and_schema_mapping():
    bundle = build_identity_scenario_bundle(EXPERIMENT_ROOT, "ID-DEV-003-rename-stable-identity")
    adapter = _adapter()
    data = json.loads(adapter.encode(bundle))

    bad_status = deepcopy(data)
    bad_status["identity_decision_graphs"][0]["annotations"]["status"] = "candidate"
    with pytest.raises(ValueError, match="identity|snapshot|aggregate"):
        adapter.decode(bad_status)

    bad_snapshot = deepcopy(data)
    bad_snapshot["identity_snapshot_graphs"][0]["annotations"]["input_fingerprint"] = "0" * 64
    with pytest.raises(ValueError, match="snapshot"):
        adapter.decode(bad_snapshot)

    bad_mapping = deepcopy(data)
    bad_mapping["concept_graphs"][0]["annotations"]["external_mappings"][0]["relation"] = "invented"
    with pytest.raises(ValueError, match="mapping|relation"):
        adapter.decode(bad_mapping)
