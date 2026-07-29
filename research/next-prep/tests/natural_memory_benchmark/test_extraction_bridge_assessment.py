from __future__ import annotations

from collections import Counter
import copy
from dataclasses import replace
import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from tools.natural_memory_benchmark import extraction_bridge_assessment as bridge_module
from tools.natural_memory_benchmark.cli import main as cli_main
from tools.natural_memory_benchmark.extraction_bridge_assessment import (
    AutomaticWriteClaims,
    TYPED_EXTRACTOR_V2_REQUIREMENTS,
    assess_extraction_bridge,
    build_compatibility_envelopes,
    map_modality,
    replay_extraction_inputs,
    run_extraction_bridge_assessment,
)
from tools.natural_memory_benchmark.authoritative_conformance_runner import (
    build_authoritative_conformance_bundle,
)
from tools.natural_memory_benchmark.authoritative_memory import canonical_sha256
from tools.natural_memory_benchmark.io import canonical_json_bytes, sha256_file


SOURCE = Path("data/gold-candidates/KE-test.json")
TURN_MANIFEST = Path("knowledge-extraction/turn-pass/validated/manifest.json")
DIALOGUE_MANIFEST = Path("knowledge-extraction/dialogue-pass/validated/manifest.json")
FINAL_KNOWLEDGE = Path("knowledge-extraction/final-knowledge.json")
RUN = Path("knowledge-extraction/run.json")
SOURCE_SEGMENTS = Path("knowledge-extraction/source-segments.json")
GUARD_ROOT = Path("artifacts/natural-benchmark-slices")
GUARD_RESULTS = Path(
    "artifacts/natural-benchmark-slices/slice-v1/"
    "symbolic-fallback-answerability-v2-fastembed-results.json"
)


def _replay(**overrides):
    inputs = {
        "source_path": SOURCE,
        "turn_manifest_path": TURN_MANIFEST,
        "dialogue_manifest_path": DIALOGUE_MANIFEST,
        "final_knowledge_path": FINAL_KNOWLEDGE,
        "run_path": RUN,
        "source_segments_path": SOURCE_SEGMENTS,
    }
    inputs.update(overrides)
    return replay_extraction_inputs(**inputs)


def _write_json(path: Path, value: object) -> None:
    path.write_bytes(canonical_json_bytes(value))


def _guard_bundle():
    return build_authoritative_conformance_bundle(GUARD_ROOT, "slice-v1", GUARD_RESULTS)


def _run_outputs(root: Path):
    return run_extraction_bridge_assessment(
        source_path=SOURCE,
        turn_manifest_path=TURN_MANIFEST,
        dialogue_manifest_path=DIALOGUE_MANIFEST,
        final_knowledge_path=FINAL_KNOWLEDGE,
        run_path=RUN,
        source_segments_path=SOURCE_SEGMENTS,
        guard_root=GUARD_ROOT,
        guard_slice_id="slice-v1",
        guard_results_path=GUARD_RESULTS,
        ledger_path=root / "compatibility-ledger.json",
        assessment_path=root / "assessment.json",
        report_path=root / "report.md",
    )


def test_replay_binds_the_formal_extraction_ledger() -> None:
    replay = _replay()

    assert replay.record_count == 416
    assert replay.active_record_count == 390
    assert len(replay.source_turns) == 43
    assert len({candidate_id for candidate_id, _ in replay.source_turns}) == 10
    assert replay.input_sha256 == {
        "dialogue_manifest": sha256_file(DIALOGUE_MANIFEST),
        "final_knowledge": sha256_file(FINAL_KNOWLEDGE),
        "run": sha256_file(RUN),
        "source": sha256_file(SOURCE),
        "source_segments": sha256_file(SOURCE_SEGMENTS),
        "turn_manifest": sha256_file(TURN_MANIFEST),
    }
    assert replay.view.provenance is not None
    assert replay.view.provenance["turn_manifest_sha256"] == sha256_file(TURN_MANIFEST)
    assert replay.view.provenance["dialogue_manifest_sha256"] == sha256_file(
        DIALOGUE_MANIFEST
    )
    assert replay.view.provenance["source_segments_sha256"] == sha256_file(
        SOURCE_SEGMENTS
    )


def test_replay_ignores_migrated_absolute_provenance_paths(tmp_path: Path) -> None:
    final = json.loads(FINAL_KNOWLEDGE.read_text(encoding="utf-8"))
    final["provenance"]["turn_manifest"] = "/different-host/turn-manifest.json"
    final["provenance"]["dialogue_manifest"] = "/different-host/dialogue-manifest.json"
    migrated = tmp_path / "final-knowledge.json"
    _write_json(migrated, final)
    run = json.loads(RUN.read_text(encoding="utf-8"))
    run["projection"]["output_sha256"] = sha256_file(migrated)
    migrated_run = tmp_path / "run.json"
    _write_json(migrated_run, run)

    replay = _replay(final_knowledge_path=migrated, run_path=migrated_run)

    assert replay.record_count == 416
    assert replay.active_record_count == 390


def test_replay_rejects_final_semantic_drift(tmp_path: Path) -> None:
    final = json.loads(FINAL_KNOWLEDGE.read_text(encoding="utf-8"))
    final["records"][0]["knowledge"]["statement"] = "tampered statement"
    tampered = tmp_path / "final-knowledge.json"
    _write_json(tampered, final)

    with pytest.raises(ValueError, match="final knowledge semantic payload mismatch"):
        _replay(final_knowledge_path=tampered)


def test_replay_rejects_final_provenance_hash_drift(tmp_path: Path) -> None:
    final = json.loads(FINAL_KNOWLEDGE.read_text(encoding="utf-8"))
    final["provenance"]["turn_manifest_sha256"] = "0" * 64
    tampered = tmp_path / "final-knowledge.json"
    _write_json(tampered, final)

    with pytest.raises(ValueError, match="final knowledge provenance hashes mismatch"):
        _replay(final_knowledge_path=tampered)


def test_replay_rejects_run_binding_drift(tmp_path: Path) -> None:
    run = json.loads(RUN.read_text(encoding="utf-8"))
    run["turn_pass"]["validated_manifest"]["sha256"] = "0" * 64
    tampered = tmp_path / "run.json"
    _write_json(tampered, run)

    with pytest.raises(ValueError, match="run metadata does not bind extraction inputs"):
        _replay(run_path=tampered)


def test_replay_rejects_run_projection_binding_drift(tmp_path: Path) -> None:
    run = json.loads(RUN.read_text(encoding="utf-8"))
    run["projection"]["output_sha256"] = "0" * 64
    tampered = tmp_path / "run.json"
    _write_json(tampered, run)

    with pytest.raises(ValueError, match="run projection does not bind final knowledge"):
        _replay(run_path=tampered)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("active_count", 0),
        ("counts", {"active": 416}),
        ("deterministic_replay", False),
        ("status", "failed"),
        ("turn_manifest_sha256", "0" * 64),
        ("dialogue_manifest_sha256", "0" * 64),
        ("source_segments_sha256", "0" * 64),
    ],
)
def test_replay_rejects_each_run_projection_binding_field_drift(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    run = json.loads(RUN.read_text(encoding="utf-8"))
    run["projection"][field] = value
    tampered = tmp_path / "run.json"
    _write_json(tampered, run)

    with pytest.raises(ValueError, match="run projection does not bind final knowledge"):
        _replay(run_path=tampered)


def test_replay_rejects_conflicting_evidence_id_reuse(tmp_path: Path) -> None:
    final = json.loads(FINAL_KNOWLEDGE.read_text(encoding="utf-8"))
    records = copy.deepcopy(final["records"])
    first_evidence = records[0]["knowledge"]["evidence"][0]
    conflicting = copy.deepcopy(first_evidence)
    conflicting["quote"] = "different quote"
    conflicting["end"] = conflicting["start"] + len(conflicting["quote"])
    records[1]["knowledge"]["evidence"][0] = conflicting
    final["records"] = records
    tampered = tmp_path / "final-knowledge.json"
    _write_json(tampered, final)

    with pytest.raises(ValueError, match="final knowledge semantic payload mismatch"):
        _replay(final_knowledge_path=tampered)


def test_evidence_definition_validation_rejects_conflicting_id_reuse() -> None:
    replay = _replay()
    records = list(replay.view.records)
    first = copy.deepcopy(records[0].knowledge["evidence"][0])
    second_index = next(
        index
        for index, record in enumerate(records[1:], start=1)
        if canonical_json_bytes(record.knowledge["evidence"][0])
        != canonical_json_bytes(first)
    )
    second_knowledge = copy.deepcopy(records[second_index].knowledge)
    second_knowledge["evidence"][0]["evidence_id"] = first["evidence_id"]
    records[second_index] = replace(records[second_index], knowledge=second_knowledge)
    tampered_view = replace(replay.view, records=tuple(records))

    with pytest.raises(ValueError, match="conflicting evidence ID reuse"):
        bridge_module._validate_evidence_definitions(tampered_view)


def _mapping(envelope, field: str):
    return next(item for item in envelope.mappings if item.field == field)


def test_envelopes_classify_single_turn_and_cross_turn_candidates() -> None:
    replay = _replay()
    envelopes = build_compatibility_envelopes(replay)
    by_id = {item.knowledge_id: item for item in envelopes}

    assert len(envelopes) == replay.record_count
    assert len(by_id) == replay.record_count

    single_record = next(
        record
        for record in replay.view.records
        if len({item["turn_index"] for item in record.knowledge["evidence"]}) == 1
        and not record.added_by
    )
    single = by_id[single_record.knowledge_id]
    assert single.candidate_level == "l1_single_turn_candidate"
    assert len(single.evidence_turns) == 1

    cross_record = next(
        record
        for record in replay.view.records
        if len({item["turn_index"] for item in record.knowledge["evidence"]}) > 1
        or record.added_by
    )
    cross = by_id[cross_record.knowledge_id]
    assert cross.candidate_level == "l2_cross_turn_candidate"
    assert {
        "missing_supporting_l1_unit_ids",
        "missing_structured_claim",
        "missing_abstraction_method",
        "missing_closure_specification",
        "missing_source_turn_session_closure",
    }.issubset(cross.blocking_gaps)


def test_envelopes_preserve_lifecycle_and_explicit_links() -> None:
    replay = _replay()
    envelopes = {item.knowledge_id: item for item in build_compatibility_envelopes(replay)}

    corrected = next(record for record in replay.view.records if record.status == "corrected")
    corrected_envelope = envelopes[corrected.knowledge_id]
    assert _mapping(corrected_envelope, "lifecycle").target_value == "superseded"
    assert _mapping(corrected_envelope, "replacement_links").status == "exact"
    assert _mapping(corrected_envelope, "replacement_links").target_value == {
        "conflicts_with": list(corrected.conflicts_with),
        "replacement_id": corrected.replacement_id,
        "replaces": list(corrected.replaces),
        "supersedes": list(corrected.supersedes),
    }

    superseded = next(record for record in replay.view.records if record.status == "superseded")
    assert _mapping(envelopes[superseded.knowledge_id], "lifecycle").target_value == (
        "superseded"
    )

    confirmed = next(record for record in replay.view.records if record.confirmed_by)
    assert _mapping(envelopes[confirmed.knowledge_id], "operation_links").target_value == {
        "added_by": list(confirmed.added_by),
        "confirmed_by": list(confirmed.confirmed_by),
    }


def test_bridge_rejects_cross_candidate_lifecycle_links() -> None:
    replay = _replay()
    records = list(replay.view.records)
    source_index = next(
        index
        for index, record in enumerate(records)
        if record.candidate_id != records[0].candidate_id
    )
    records[0] = replace(records[0], replacement_id=records[source_index].knowledge_id)
    tampered_view = replace(replay.view, records=tuple(records))

    with pytest.raises(ValueError, match="cross-candidate projection reference"):
        bridge_module._validate_projection_candidate_boundaries(
            tampered_view,
            replay.operation_candidates,
        )


@pytest.mark.parametrize("field", ["confirmed_by", "added_by"])
def test_bridge_rejects_cross_candidate_operation_links(field: str) -> None:
    replay = _replay()
    records = list(replay.view.records)
    source_index = next(
        index
        for index, record in enumerate(records)
        if record.candidate_id != records[0].candidate_id
    )
    foreign_candidate = records[source_index].candidate_id
    foreign_operation = next(
        operation_id
        for operation_id, candidate_id in replay.operation_candidates.items()
        if candidate_id == foreign_candidate
    )
    records[0] = replace(records[0], **{field: (foreign_operation,)})
    tampered_view = replace(replay.view, records=tuple(records))

    with pytest.raises(ValueError, match="cross-candidate projection operation"):
        bridge_module._validate_projection_candidate_boundaries(
            tampered_view,
            replay.operation_candidates,
        )


def test_bridge_rejects_unknown_projection_operation_link() -> None:
    replay = _replay()
    records = list(replay.view.records)
    records[0] = replace(records[0], confirmed_by=("R_unknown",))
    tampered_view = replace(replay.view, records=tuple(records))

    with pytest.raises(ValueError, match="unknown projection operation reference"):
        bridge_module._validate_projection_candidate_boundaries(
            tampered_view,
            replay.operation_candidates,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("quote", "quote occurrence is missing or out of range"),
        ("occurrence_index", "quote occurrence is missing or out of range"),
        ("offset", "evidence binding mismatch"),
    ],
)
def test_evidence_validation_directly_rejects_binding_mismatch(
    mutation: str,
    message: str,
) -> None:
    replay = _replay()
    records = list(replay.view.records)
    evidence_counts = Counter(
        str(evidence["evidence_id"])
        for record in records
        for evidence in record.knowledge["evidence"]
    )
    record_index = next(
        index
        for index, record in enumerate(records)
        if all(
            evidence_counts[str(evidence["evidence_id"])] == 1
            for evidence in record.knowledge["evidence"]
        )
    )
    knowledge = copy.deepcopy(records[record_index].knowledge)
    evidence = knowledge["evidence"][0]
    if mutation == "quote":
        evidence["quote"] = "definitely absent from the source turn"
    elif mutation == "occurrence_index":
        evidence["occurrence_index"] = evidence["occurrence_index"] + 1
    else:
        evidence["start"] = evidence["start"] + 1
    records[record_index] = replace(records[record_index], knowledge=knowledge)
    tampered_view = replace(replay.view, records=tuple(records))

    with pytest.raises(ValueError, match=message):
        bridge_module._validate_evidence(tampered_view, replay.source_turns)


def test_bridge_rejects_unknown_projection_lifecycle() -> None:
    replay = _replay()
    records = list(replay.view.records)
    records[0] = replace(records[0], status="unknown")
    tampered_replay = replace(replay, view=replace(replay.view, records=tuple(records)))

    with pytest.raises(ValueError, match="unsupported projection lifecycle"):
        build_compatibility_envelopes(tampered_replay)


@pytest.mark.parametrize(
    ("source_modality", "target_modality"),
    list(
        {
        "asserted": "actual",
        "observed": "actual",
        "planned": "planned",
        "requested": "requested",
        "hypothetical": "hypothetical",
        "advised": "recommended",
        }.items()
    ),
)
def test_normalized_modality_mapping(source_modality: str, target_modality: str) -> None:
    mapping = map_modality(source_modality)

    assert mapping.status == "normalized"
    assert mapping.target_value == target_modality


@pytest.mark.parametrize(
    "source_modality",
    [
        "possible",
        "preferred",
        "questioned",
        "committed",
        "claimed_completed",
    ],
)
def test_unsupported_modality_mapping(source_modality: str) -> None:
    mapping = map_modality(source_modality)

    assert mapping.status == "unsupported"
    assert mapping.target_value is None


def test_envelopes_report_exact_and_unsupported_record_mappings() -> None:
    replay = _replay()
    envelopes = {item.knowledge_id: item for item in build_compatibility_envelopes(replay)}

    sample = envelopes[replay.view.records[0].knowledge_id]
    assert _mapping(sample, "evidence").status == "exact"
    assert _mapping(sample, "source_status").status == "exact"
    assert _mapping(sample, "polarity").status == "exact"
    assert _mapping(sample, "confidence").status == "exact"
    assert _mapping(sample, "evidence_speaker_bindings").status == "exact"

    unsupported_record = next(
        item
        for item in replay.view.records
        if item.knowledge["qualifiers"]["modality"] == "claimed_completed"
    )
    unsupported = envelopes[unsupported_record.knowledge_id]
    assert _mapping(unsupported, "modality").status == "unsupported"
    assert "unsupported_modality" in unsupported.blocking_gaps


def test_envelopes_report_condition_scope_and_derivation_gaps() -> None:
    replay = _replay()
    envelopes = {item.knowledge_id: item for item in build_compatibility_envelopes(replay)}

    condition_record = next(
        item for item in replay.view.records if item.knowledge["qualifiers"]["conditions"]
    )
    condition = envelopes[condition_record.knowledge_id]
    assert _mapping(condition, "typed_condition_bindings").status == "missing"
    assert "missing_typed_condition_bindings" in condition.blocking_gaps

    scope_record = next(
        item for item in replay.view.records if item.knowledge["qualifiers"]["scope"]
    )
    scope = envelopes[scope_record.knowledge_id]
    assert _mapping(scope, "typed_scope_bindings").status == "missing"
    assert "missing_typed_scope_bindings" in scope.blocking_gaps

    derived_record = next(
        item for item in replay.view.records if item.knowledge["derivation"] != "explicit"
    )
    derived = envelopes[derived_record.knowledge_id]
    assert _mapping(derived, "typed_derivation_provenance").status == "missing"
    assert "missing_typed_derivation_provenance" in derived.blocking_gaps

    exact_record = next(
        item
        for item in replay.view.records
        if not item.knowledge["qualifiers"]["conditions"]
        and not item.knowledge["qualifiers"]["scope"]
        and item.knowledge["derivation"] == "explicit"
    )
    exact = envelopes[exact_record.knowledge_id]
    assert _mapping(exact, "typed_condition_bindings").status == "exact"
    assert _mapping(exact, "typed_scope_bindings").status == "exact"
    assert _mapping(exact, "typed_derivation_provenance").status == "exact"


def test_evidence_speaker_bindings_distinguish_user_assistant_and_tool() -> None:
    replay = _replay()
    envelopes = {item.knowledge_id: item for item in build_compatibility_envelopes(replay)}

    expected = {
        "user_reported": "user",
        "agent_generated": "assistant",
        "tool_observed": "tool",
    }
    for source_status, speaker in expected.items():
        record = next(
            item
            for item in replay.view.records
            if item.knowledge["source_status"] == source_status
        )
        mapping = _mapping(envelopes[record.knowledge_id], "evidence_speaker_bindings")
        assert {item["speaker"] for item in mapping.target_value} == {speaker}


def test_envelopes_block_missing_authoritative_semantics_and_all_writes() -> None:
    replay = _replay()
    first = build_compatibility_envelopes(replay)[0]

    assert {
        "missing_memory_kind",
        "missing_predicate_sense",
        "missing_canonical_operator",
        "missing_typed_role_bindings",
        "missing_local_entity_ids",
    }.issubset(first.blocking_gaps)
    assert first.authoritative_materialization_allowed is False
    assert set(first.automatic_write_claims.model_dump().values()) == {False}


def test_envelope_ids_and_order_are_deterministic() -> None:
    replay = _replay()
    first = build_compatibility_envelopes(replay)
    second = build_compatibility_envelopes(replay)

    assert canonical_json_bytes([item.model_dump(mode="json") for item in first]) == (
        canonical_json_bytes([item.model_dump(mode="json") for item in second])
    )
    assert [item.knowledge_id for item in first] == sorted(
        item.knowledge_id for item in first
    )
    assert len({item.envelope_id for item in first}) == len(first)


def test_automatic_write_claims_cannot_be_true() -> None:
    with pytest.raises(ValidationError):
        AutomaticWriteClaims(l1=True)


def test_assessment_separates_raw_structure_from_bridge_safety() -> None:
    replay = _replay()
    envelopes = build_compatibility_envelopes(replay)
    ledger, assessment = assess_extraction_bridge(
        replay,
        envelopes,
        guard_bundle=_guard_bundle(),
    )

    assert ledger.record_count == 416
    assert len(ledger.envelopes) == 416
    raw = assessment.raw_extraction_structure
    safety = assessment.deterministic_bridge_safety
    assert raw["projected_record_count"] == 416
    assert raw["active_record_count"] == 390
    assert raw["stage_counts"] == {"dialogue": 17, "turn": 399}
    assert raw["exact_evidence_binding_rate"] == 1.0
    assert raw["source_status_admissibility_rate"] == 1.0
    assert raw["required_surface_field_completeness_rate"] == 1.0
    assert raw["object_present_rate"] == pytest.approx(397 / 416)
    assert raw["condition_qualifier_record_count"] == 51
    assert raw["scope_qualifier_record_count"] == 79
    assert raw["non_explicit_derivation_record_count"] == 68
    assert not any("accuracy" in key for key in raw)

    assert (
        safety["l1_candidate_count"]
        + safety["l2_candidate_count"]
        + safety["blocked_candidate_count"]
        == 416
    )
    assert safety["authoritative_ready_l1_count"] == 0
    assert safety["authoritative_ready_l2_count"] == 0
    assert safety["gap_counts"]["missing_memory_kind"] == 416
    assert safety["gap_counts"]["missing_typed_condition_bindings"] == 51
    assert safety["gap_counts"]["missing_typed_scope_bindings"] == 79
    assert safety["gap_counts"]["missing_typed_derivation_provenance"] == 68
    assert safety["automatic_l1_write_count"] == 0
    assert safety["automatic_l2_write_count"] == 0
    assert safety["automatic_unit_revision_write_count"] == 0
    assert safety["automatic_closure_write_count"] == 0
    assert safety["automatic_identity_write_count"] == 0
    assert safety["automatic_membership_write_count"] == 0


def test_assessment_preserves_guard_and_claim_boundaries() -> None:
    replay = _replay()
    envelopes = build_compatibility_envelopes(replay)
    guard = _guard_bundle()
    before = canonical_sha256(guard)

    _, assessment = assess_extraction_bridge(replay, envelopes, guard_bundle=guard)

    assert canonical_sha256(guard) == before
    assert assessment.guard_state["before_fingerprint"] == before
    assert assessment.guard_state["after_fingerprint"] == before
    assert assessment.guard_state["unchanged"] is True
    assert assessment.guard_state["before_counts"] == assessment.guard_state["after_counts"]
    assert assessment.automatic_extraction_integration_ready is False
    assert assessment.claim_boundary == {
        "automatic_closure_write_authorized": False,
        "automatic_identity_write_authorized": False,
        "automatic_l1_write_authorized": False,
        "automatic_l2_write_authorized": False,
        "automatic_membership_write_authorized": False,
        "automatic_unit_revision_write_authorized": False,
        "embedding_authority": False,
        "longmemeval_status": "structured_l2_identity_unresolved",
    }


def test_assessment_requires_exact_envelope_record_and_candidate_coverage() -> None:
    replay = _replay()
    envelopes = build_compatibility_envelopes(replay)
    wrong_id = list(envelopes)
    wrong_id[0] = wrong_id[0].model_copy(update={"knowledge_id": "unknown-knowledge"})

    with pytest.raises(ValueError, match="compatibility envelope record coverage mismatch"):
        assess_extraction_bridge(replay, wrong_id, guard_bundle=_guard_bundle())

    wrong_candidate = list(envelopes)
    wrong_candidate[0] = wrong_candidate[0].model_copy(
        update={"candidate_id": "wrong-candidate"}
    )
    with pytest.raises(ValueError, match="compatibility envelope candidate mismatch"):
        assess_extraction_bridge(replay, wrong_candidate, guard_bundle=_guard_bundle())


def test_assessment_emits_stable_typed_extractor_requirements() -> None:
    replay = _replay()
    ledger, assessment = assess_extraction_bridge(
        replay,
        build_compatibility_envelopes(replay),
        guard_bundle=_guard_bundle(),
    )

    assert assessment.status == "pass"
    assert assessment.typed_extractor_v2_requirements == [
        "explicit_level_and_typed_memory_kind",
        "typed_predicate_surface_sense_and_canonical_operator",
        "typed_role_bindings_and_candidate_scoped_local_entity_ids",
        "typed_modality_polarity_and_time_bindings",
        "typed_condition_and_scope_bindings",
        "typed_derivation_and_inference_provenance",
        "typed_evidence_speaker_bindings",
        "exact_evidence_references",
        "explicit_lifecycle_correction_supersession_and_conflict_links",
        "l2_supporting_l1_candidate_ids",
        "l2_structured_claims_and_abstraction_method",
        "l2_closure_pattern_and_source_turn_session_coverage",
        "explicit_abstention_or_no_memory_for_unresolved_required_fields",
    ]
    assert tuple(assessment.typed_extractor_v2_requirements) == (
        TYPED_EXTRACTOR_V2_REQUIREMENTS
    )
    assert ledger.input_sha256 == replay.input_sha256
    assert ledger.schema_version == "automatic-extraction-compatibility-ledger-v3"


def test_runner_writes_deterministic_read_only_outputs(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"

    first = _run_outputs(first_root)
    second = _run_outputs(second_root)

    for name in ("compatibility-ledger.json", "assessment.json", "report.md"):
        first_path = first_root / name
        second_path = second_root / name
        assert first_path.read_bytes() == second_path.read_bytes()
        assert os.stat(first_path).st_mode & 0o777 == 0o444
        assert os.stat(second_path).st_mode & 0o777 == 0o444
    assert first == second
    assert first["automatic_extraction_integration_ready"] is False
    assert first["record_count"] == 416
    assert set(first["output_sha256"]) == {"assessment", "ledger", "report"}


def test_runner_rejects_any_existing_destination(tmp_path: Path) -> None:
    root = tmp_path / "existing"
    root.mkdir()
    (root / "compatibility-ledger.json").write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError, match="assessment output already exists"):
        _run_outputs(root)

    assert not (root / "assessment.json").exists()
    assert not (root / "report.md").exists()


def test_runner_freezes_partial_outputs_on_late_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "partial"

    def fail_report(path: Path, content: str) -> None:
        raise RuntimeError("report failure")

    monkeypatch.setattr(bridge_module, "write_text_immutable", fail_report)
    with pytest.raises(RuntimeError, match="report failure"):
        _run_outputs(root)

    assert os.stat(root / "compatibility-ledger.json").st_mode & 0o777 == 0o444
    assert os.stat(root / "assessment.json").st_mode & 0o777 == 0o444
    assert not (root / "report.md").exists()


def test_report_keeps_quality_and_safety_separate(tmp_path: Path) -> None:
    root = tmp_path / "report"
    _run_outputs(root)
    report = (root / "report.md").read_text(encoding="utf-8")

    assert "## Raw extraction structure" in report
    assert "## Deterministic bridge safety" in report
    assert "## Typed extractor v2 requirements" in report
    assert "## Limitations" in report
    assert "No model was rerun" in report
    assert "not gold semantic accuracy" in report
    assert "Automatic authoritative writes: 0" in report


def test_cli_runs_bridge_assessment(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "cli"
    result = cli_main(
        [
            "assess-automatic-l1-l2-extraction",
            "--source",
            str(SOURCE),
            "--turn-manifest",
            str(TURN_MANIFEST),
            "--dialogue-manifest",
            str(DIALOGUE_MANIFEST),
            "--final-knowledge",
            str(FINAL_KNOWLEDGE),
            "--run",
            str(RUN),
            "--source-segments",
            str(SOURCE_SEGMENTS),
            "--guard-root",
            str(GUARD_ROOT),
            "--guard-slice-id",
            "slice-v1",
            "--guard-results",
            str(GUARD_RESULTS),
            "--ledger",
            str(root / "compatibility-ledger.json"),
            "--output",
            str(root / "assessment.json"),
            "--report",
            str(root / "report.md"),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert payload["status"] == "pass"
    assert payload["record_count"] == 416
    assert payload["automatic_extraction_integration_ready"] is False
    assert set(payload["output_sha256"]) == {"assessment", "ledger", "report"}
