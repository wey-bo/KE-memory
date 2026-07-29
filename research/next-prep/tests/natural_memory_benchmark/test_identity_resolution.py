from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from tools.natural_memory_benchmark.identity_resolution import (
    IdentityAwareMemoryBundleV4,
    assess_identity_bundle_integrity,
    build_identity_scenario_bundle,
    build_schemaorg_concept_registry,
    execute_identity_aware_query,
    identity_groups_for_scope,
    is_identity_closure_fresh,
    rebuild_identity_snapshot,
    validate_identity_sources,
)


EXPERIMENT_ROOT = Path("artifacts/identity-memory-experiment")
GOLD_ROOT = EXPERIMENT_ROOT / "gold-v1"


def _source() -> dict:
    return json.loads((GOLD_ROOT / "source-scenarios.json").read_text(encoding="utf-8"))


def _gold() -> dict[str, dict]:
    payload = json.loads((GOLD_ROOT / "gold.json").read_text(encoding="utf-8"))
    return {item["scenario_id"]: item for item in payload["items"]}


def test_schemaorg_registry_is_advisory_and_project_mapping_is_not_exact():
    entries = build_schemaorg_concept_registry(EXPERIMENT_ROOT / "schemaorg-selected-v30.json")
    by_id = {item.concept_id: item for item in entries}

    assert by_id["memory:Person"].external_mappings[0].relation == "exact"
    assert by_id["memory:Organization"].external_mappings[0].relation == "exact"
    project = by_id["memory:Project"]
    assert project.external_mappings[0].external_id == "https://schema.org/Project"
    assert project.external_mappings[0].relation == "related"
    assert "personal and class projects" in project.constraints[0]

    same_as = by_id["memory:IdentityReference"]
    assert same_as.external_mappings[0].external_id == "https://schema.org/sameAs"
    assert same_as.external_mappings[0].relation == "narrower"
    assert same_as.identity_authority is False


def test_all_frozen_scenarios_execute_exact_count_evidence_and_abstention_contract():
    gold = _gold()
    for scenario in _source()["scenarios"]:
        scenario_id = scenario["scenario_id"]
        bundle = build_identity_scenario_bundle(EXPERIMENT_ROOT, scenario_id)
        assert isinstance(bundle, IdentityAwareMemoryBundleV4)
        assert assess_identity_bundle_integrity(bundle).valid is True
        assert validate_identity_sources(bundle, Path.cwd()).valid is True

        plan = bundle.query_plans[0]
        result = execute_identity_aware_query(plan, bundle)
        expected = gold[scenario_id]

        assert result.aggregate_value == expected["expected_count"]
        assert result.abstained is expected["expected_abstained"]
        assert result.required_evidence_ids == expected["expected_evidence_ids"]
        assert result.fallback_allowed is False
        if expected.get("expected_reason"):
            assert result.reason == expected["expected_reason"]
        else:
            assert result.reason == "identity_aggregate_complete"

        scope = bundle.aggregate_claims[0].member_entity_ids
        assert identity_groups_for_scope(bundle.identity_snapshots[0], scope) == expected[
            "expected_canonical_groups"
        ]


def test_same_name_distinct_and_rejected_merge_never_form_a_false_union():
    for scenario_id in (
        "ID-DEV-002-same-name-distinct",
        "ID-HIDDEN-001-reject-erroneous-merge",
    ):
        bundle = build_identity_scenario_bundle(EXPERIMENT_ROOT, scenario_id)
        snapshot = bundle.identity_snapshots[0]
        assert len(identity_groups_for_scope(snapshot, bundle.aggregate_claims[0].member_entity_ids)) == 2
        assert len(snapshot.distinct_pairs) == 1


def test_split_supersedes_old_merge_and_old_policy_cannot_authorize_count():
    bundle = build_identity_scenario_bundle(EXPERIMENT_ROOT, "ID-HIDDEN-002-split-correction")
    snapshot = bundle.identity_snapshots[0]

    assert snapshot.active_decision_ids == ["decision:harbor-split-v2"]
    assert snapshot.superseded_decision_ids == ["decision:harbor-merge-v1"]
    assert identity_groups_for_scope(snapshot, bundle.aggregate_claims[0].member_entity_ids) == [
        ["entity:harbor-east"],
        ["entity:harbor-west"],
    ]

    decisions = [
        decision.model_copy(update={"status": "accepted"})
        if decision.decision_id == "decision:harbor-merge-v1"
        else decision
        for decision in bundle.identity_decisions
    ]
    conflicting = bundle.model_copy(update={"identity_decisions": decisions})
    report = assess_identity_bundle_integrity(conflicting)
    assert report.valid is False
    assert any("merged and distinct" in error or "superseded" in error for error in report.errors)


def test_identity_closure_detects_scoped_tampering_but_ignores_outside_scope_changes():
    bundle = build_identity_scenario_bundle(EXPERIMENT_ROOT, "ID-HIDDEN-004-outside-scope-stability")
    closure = next(
        item for item in bundle.identity_closures if item.decision_id == "decision:lumen-merge"
    )
    assert is_identity_closure_fresh(bundle, closure) is True

    scoped_unit = next(item for item in bundle.l1_units if item.unit_id == "l1-lumen-1")
    changed_scoped = scoped_unit.model_copy(
        update={"predicate": scoped_unit.predicate.model_copy(update={"surface": "managed"})}
    )
    stale_bundle = bundle.model_copy(
        update={
            "l1_units": [changed_scoped if item.unit_id == changed_scoped.unit_id else item for item in bundle.l1_units]
        }
    )
    assert is_identity_closure_fresh(stale_bundle, closure) is False

    unrelated = next(item for item in bundle.entity_records if item.entity_id == "entity:unrelated")
    changed_unrelated = unrelated.model_copy(update={"names": [*unrelated.names, "Quartz alias"]})
    outside_bundle = bundle.model_copy(
        update={
            "entity_records": [
                changed_unrelated if item.entity_id == changed_unrelated.entity_id else item
                for item in bundle.entity_records
            ]
        }
    )
    rebuilt = rebuild_identity_snapshot(outside_bundle, bundle.aggregate_claims[0])
    assert rebuilt == bundle.identity_snapshots[0]


def test_aggregate_rejects_tampered_value_membership_snapshot_and_unresolved_identity():
    bundle = build_identity_scenario_bundle(
        EXPERIMENT_ROOT, "ID-HIDDEN-003-four-mentions-two-entities"
    )
    aggregate = bundle.aggregate_claims[0]

    for update, expected_error in (
        ({"value": 3}, "aggregate value mismatch"),
        ({"member_l1_unit_ids": aggregate.member_l1_unit_ids[:-1]}, "aggregate member"),
        ({"identity_snapshot_id": "snapshot:missing"}, "missing identity snapshot"),
    ):
        tampered = aggregate.model_copy(update=update)
        changed = bundle.model_copy(update={"aggregate_claims": [tampered]})
        report = assess_identity_bundle_integrity(changed)
        assert report.valid is False
        assert any(expected_error in error for error in report.errors)

    unresolved = build_identity_scenario_bundle(EXPERIMENT_ROOT, "ID-DEV-004-unresolved-alias")
    result = execute_identity_aware_query(unresolved.query_plans[0], unresolved)
    assert result.abstained is True
    assert result.aggregate_value is None
    assert result.reason == "identity_unresolved"


def test_source_replay_rejects_text_and_artifact_hash_tampering():
    bundle = build_identity_scenario_bundle(EXPERIMENT_ROOT, "ID-DEV-001-alias-shared-identifier")
    source = bundle.source_record_revisions[0]
    changed_source = source.model_copy(update={"text": source.text + " altered"})
    source_tampered = bundle.model_copy(
        update={
            "source_record_revisions": [
                changed_source if item.source_revision_id == source.source_revision_id else item
                for item in bundle.source_record_revisions
            ]
        }
    )
    assert validate_identity_sources(source_tampered, Path.cwd()).valid is False

    artifact = bundle.raw_artifact_revisions[0]
    changed_artifact = artifact.model_copy(update={"content_sha256": "0" * 64})
    artifact_tampered = bundle.model_copy(update={"raw_artifact_revisions": [changed_artifact]})
    assert validate_identity_sources(artifact_tampered, Path.cwd()).valid is False


def test_native_v4_dump_is_deterministic_and_does_not_mutate_frozen_v3_fixture():
    first = build_identity_scenario_bundle(EXPERIMENT_ROOT, "ID-DEV-003-rename-stable-identity")
    second = build_identity_scenario_bundle(EXPERIMENT_ROOT, "ID-DEV-003-rename-stable-identity")
    assert first == second
    assert first.schema_version == "identity-aware-memory-bundle-v4"

    v5_path = Path(
        "artifacts/natural-benchmark-slices/slice-v1/representation-conformance-results-v5.json"
    )
    before = v5_path.read_bytes()
    deepcopy(first.model_dump(mode="json"))
    assert v5_path.read_bytes() == before
