from __future__ import annotations

from pathlib import Path

from tools.natural_memory_benchmark.authoritative_memory import (
    ProducerIdentity,
    assess_authoritative_bundle_integrity,
    build_real_slice_authoritative_bundle,
    execute_authoritative_query,
    migrate_v2_bundle_to_v3,
    validate_authoritative_sources,
)
from tools.natural_memory_benchmark.io import canonical_json_bytes
from tools.natural_memory_benchmark.representation_conformance_runner import (
    build_real_slice_representation_bundle,
)


ROOT = Path("artifacts/natural-benchmark-slices")
SLICE_ID = "slice-v1"
RESULTS = ROOT / SLICE_ID / "symbolic-fallback-answerability-v2-fastembed-results.json"
TRANSACTION_TIME = "2026-07-27T12:00:00Z"


def _producer() -> ProducerIdentity:
    return ProducerIdentity(
        workflow_run_id="run-authoritative-migration-test",
        producer_id="real-slice-v2-to-v3",
        producer_version="1",
    )


def _build():
    return build_real_slice_authoritative_bundle(
        ROOT,
        SLICE_ID,
        RESULTS,
        transaction_time=TRANSACTION_TIME,
        producer=_producer(),
        query_answer_kinds={"LONGMEMEVAL-6d550036": "count"},
    )


def test_real_slice_migration_is_byte_deterministic_and_keeps_v2_immutable():
    v2 = build_real_slice_representation_bundle(ROOT, SLICE_ID, RESULTS)
    before = canonical_json_bytes(v2)

    first = _build()
    second = _build()

    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert canonical_json_bytes(v2) == before
    assert first.schema_version == "memory-representation-bundle-v3"


def test_real_slice_migration_builds_expected_authoritative_ledgers():
    bundle = _build()

    assert len(bundle.raw_artifact_revisions) == 2
    assert {item.source_id for item in bundle.raw_artifact_revisions} == {
        "beam-100K",
        "longmemeval-oracle",
    }
    assert len(bundle.source_record_revisions) == 13
    assert len(bundle.l1_units) == 13
    assert len(bundle.l2_units) == 1
    assert len(bundle.unit_revisions) == 14
    assert all(item.revision_number == 1 for item in bundle.unit_revisions)
    assert len(bundle.closure_specs) == 6
    assert len(bundle.closure_evaluations) == 6
    assert len(bundle.query_plans) == 5
    assert assess_authoritative_bundle_integrity(bundle).valid is True


def test_real_slice_source_records_replay_against_frozen_raw_artifacts():
    report = validate_authoritative_sources(_build(), workspace_root=Path("."))

    assert report.valid is True
    assert report.errors == []
    assert report.metrics["artifact_verified_count"] == 2
    assert report.metrics["source_record_replayed_count"] == 13


def test_migration_recomputes_closure_and_ignores_legacy_materialized_outcome():
    v2 = build_real_slice_representation_bundle(ROOT, SLICE_ID, RESULTS)
    tampered_closures = [
        closure.model_copy(
            update={
                "complete": not closure.complete,
                "missing_slots": [],
                "reason": "tampered legacy materialization",
            }
        )
        for closure in v2.closures
    ]
    tampered = v2.model_copy(update={"closures": tampered_closures})

    baseline = migrate_v2_bundle_to_v3(
        v2,
        root=ROOT,
        slice_id=SLICE_ID,
        transaction_time=TRANSACTION_TIME,
        producer=_producer(),
        query_answer_kinds={"LONGMEMEVAL-6d550036": "count"},
    )
    migrated = migrate_v2_bundle_to_v3(
        tampered,
        root=ROOT,
        slice_id=SLICE_ID,
        transaction_time=TRANSACTION_TIME,
        producer=_producer(),
        query_answer_kinds={"LONGMEMEVAL-6d550036": "count"},
    )

    assert migrated.closure_specs == baseline.closure_specs
    assert migrated.closure_evaluations == baseline.closure_evaluations


def test_five_authoritative_queries_match_frozen_correctness_expectations():
    bundle = _build()
    results = {
        plan.query_id: execute_authoritative_query(plan, bundle)
        for plan in bundle.query_plans
    }

    causal = results["BEAM-100K-C001-abstention-001"]
    assert causal.abstained is True
    assert causal.closure_complete is False
    assert causal.fallback_allowed is False
    assert causal.required_evidence_ids == []
    assert causal.reason == "missing_required_slot"

    count = results["LONGMEMEVAL-6d550036"]
    assert count.matched_unit_ids == [
        "l1-led-project-1",
        "l1-led-project-2",
        "l1-led-project-3",
        "l1-led-project-4",
        "l2-longmemeval-led-project-count",
    ]
    assert count.required_evidence_ids == [
        "answer_ec904b3c_4",
        "answer_ec904b3c_2",
        "answer_ec904b3c_1",
        "answer_ec904b3c_3",
    ]
    assert count.abstained is True
    assert count.closure_complete is True
    assert count.fallback_allowed is False
    assert count.reason == "structured_l2_identity_unresolved"

    for query_id in (
        "BEAM-100K-C001-contradiction_resolution-001",
        "BEAM-100K-C001-knowledge_update-002",
        "LONGMEMEVAL-gpt4_2655b836",
    ):
        result = results[query_id]
        assert result.abstained is False
        assert result.closure_complete is True
        assert result.fallback_allowed is False
        assert result.required_evidence_ids


def test_raw_artifact_path_size_and_hash_tampering_fail_closed():
    bundle = _build()
    artifact = bundle.raw_artifact_revisions[0]

    escaped = artifact.model_copy(update={"local_path": "../outside.json"})
    escaped_report = validate_authoritative_sources(
        bundle.model_copy(update={"raw_artifact_revisions": [escaped, *bundle.raw_artifact_revisions[1:]]}),
        workspace_root=Path("."),
    )
    assert any("escapes workspace root" in error for error in escaped_report.errors)

    wrong_size = artifact.model_copy(update={"size_bytes": artifact.size_bytes + 1})
    size_report = validate_authoritative_sources(
        bundle.model_copy(update={"raw_artifact_revisions": [wrong_size, *bundle.raw_artifact_revisions[1:]]}),
        workspace_root=Path("."),
    )
    assert any("size mismatch" in error for error in size_report.errors)

    wrong_hash = artifact.model_copy(update={"content_sha256": "0" * 64})
    hash_report = validate_authoritative_sources(
        bundle.model_copy(update={"raw_artifact_revisions": [wrong_hash, *bundle.raw_artifact_revisions[1:]]}),
        workspace_root=Path("."),
    )
    assert any("hash mismatch" in error for error in hash_report.errors)
