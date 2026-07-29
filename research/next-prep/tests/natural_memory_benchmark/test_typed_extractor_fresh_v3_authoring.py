from __future__ import annotations

import fcntl
import json
import os
import shutil
import stat
from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from tools.natural_memory_benchmark import typed_extractor_fresh_v3_authoring as authoring
from tools.natural_memory_benchmark.authoritative_conformance_runner import (
    build_authoritative_conformance_bundle,
)
from tools.natural_memory_benchmark.io import (
    canonical_json_bytes,
    load_json,
    sha256_file,
)
from tools.natural_memory_benchmark.typed_extractor_fresh_v3_authoring import (
    FreshV3AuthoringReceipt,
    build_fresh_v3_authoring_bundle,
    freeze_fresh_v3_authoring_receipt,
    validate_fresh_v3_authoring_bundle,
    validate_fresh_v3_authoring_receipt,
)
from tools.natural_memory_benchmark.typed_extractor_fresh_v3_prereg import (
    L1_FAMILIES,
    L2_FAMILIES,
)


WORKSPACE = Path(__file__).resolve().parents[2]
ASSESSMENT = WORKSPACE / "artifacts/automatic-extraction-assessment"
FORMAL_PREREG = (
    ASSESSMENT
    / "typed-extractor-v3-fresh-hidden-prereg-v1"
    / "preregistration.json"
)
FORMAL_EVALUATION = ASSESSMENT / "typed-extractor-v3-fresh-hidden-v1"
RECEIPT_TIME = "2026-07-29T06:30:00Z"
GUARD_ROOT = WORKSPACE / "artifacts/natural-benchmark-slices"
GUARD_RESULTS = (
    GUARD_ROOT
    / "slice-v1/symbolic-fallback-answerability-v2-fastembed-results.json"
)
GUARD_COUNTS = {
    "closure_evaluation_count": 6,
    "closure_spec_count": 6,
    "l1_unit_count": 13,
    "l2_unit_count": 1,
    "query_plan_count": 5,
    "raw_artifact_revision_count": 2,
    "source_record_revision_count": 13,
    "unit_revision_count": 14,
}


def _copy_preregistration(tmp_path: Path) -> Path:
    prereg = tmp_path / "prereg" / "preregistration.json"
    prereg.parent.mkdir()
    shutil.copy2(FORMAL_PREREG, prereg)
    prereg.chmod(0o444)
    return prereg


def _rewrite_json(path: Path, payload: dict[str, object]) -> None:
    path.chmod(0o644)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )
    path.chmod(0o444)


def _allow_temp_receipt_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        authoring,
        "_validate_chronology_paths",
        lambda **_: None,
    )


def _rerender_and_validate_l1(
    bundle: authoring.FreshV3AuthoringBundle,
    blueprints: tuple[authoring.L1Blueprint, ...],
) -> None:
    layer = authoring._render_l1(
        blueprints,
        authoring._load_preregistration(FORMAL_PREREG),
    )
    validate_fresh_v3_authoring_bundle(
        bundle.model_copy(update={"l1": layer}),
        FORMAL_PREREG,
    )


def _rerender_and_validate_l2(
    bundle: authoring.FreshV3AuthoringBundle,
    blueprints: tuple[authoring.L2Blueprint, ...],
) -> None:
    layer = authoring._render_l2(
        blueprints,
        authoring._load_preregistration(FORMAL_PREREG),
    )
    validate_fresh_v3_authoring_bundle(
        bundle.model_copy(update={"l2": layer}),
        FORMAL_PREREG,
    )


def test_bundle_uses_every_preregistered_blueprint_in_stable_order() -> None:
    bundle = build_fresh_v3_authoring_bundle(FORMAL_PREREG)

    assert len(bundle.l1.blueprints) == 24
    assert len(bundle.l2.blueprints) == 18
    assert Counter(item.family for item in bundle.l1.blueprints) == L1_FAMILIES
    assert Counter(item.family for item in bundle.l2.blueprints) == L2_FAMILIES
    assert [(item.family, item.ordinal) for item in bundle.l1.blueprints] == [
        (family, ordinal)
        for family, count in L1_FAMILIES.items()
        for ordinal in range(1, count + 1)
    ]
    assert [(item.family, item.ordinal) for item in bundle.l2.blueprints] == [
        (family, ordinal)
        for family, count in L2_FAMILIES.items()
        for ordinal in range(1, count + 1)
    ]
    assert bundle.l1.public.case_count == 24
    assert bundle.l2.public.case_count == 18
    assert bundle.l1.public.dataset_id == "typed-extractor-v3-fresh-hidden-v1-l1"
    assert bundle.l2.public.dataset_id == "typed-extractor-v3-fresh-hidden-v1-l2"


def test_bundle_is_deterministic_and_creates_no_formal_artifact() -> None:
    assert not FORMAL_EVALUATION.exists()

    first = build_fresh_v3_authoring_bundle(FORMAL_PREREG)
    second = build_fresh_v3_authoring_bundle(FORMAL_PREREG)

    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert not FORMAL_EVALUATION.exists()


def test_public_payload_contains_no_private_identifiers() -> None:
    bundle = build_fresh_v3_authoring_bundle(FORMAL_PREREG)
    public_text = (
        canonical_json_bytes(bundle.l1.public)
        + canonical_json_bytes(bundle.l2.public)
    ).decode()
    private_values = {
        value
        for blueprint in (*bundle.l1.blueprints, *bundle.l2.blueprints)
        for value in (
            blueprint.blueprint_id,
            blueprint.private_case_id,
            blueprint.knowledge_id,
            blueprint.candidate_id,
        )
    }

    assert not {value for value in private_values if value in public_text}
    assert "expected_typed_candidate" not in public_text
    assert "primary_family" not in public_text


def test_l2_public_payload_excludes_authoring_tokens_and_lifecycle_answers() -> None:
    bundle = build_fresh_v3_authoring_bundle(FORMAL_PREREG)
    public_text = canonical_json_bytes(bundle.l2.public).decode()

    assert "support_lifecycle_bindings" not in public_text
    assert "fresh-v3 case" not in public_text
    for token in (
        "topaz_old_recipient",
        "topaz_new_recipient",
        "onyx_old_date",
        "onyx_new_date",
    ):
        assert token not in public_text


def test_public_vocabulary_is_label_independent_for_every_blueprint() -> None:
    bundle = build_fresh_v3_authoring_bundle(FORMAL_PREREG)

    assert set(bundle.l1.public.allowed_vocabulary["canonical_operators"]) == {
        item.vocabulary_operator for item in bundle.l1.blueprints
    }
    assert set(bundle.l1.public.allowed_vocabulary["predicate_senses"]) == {
        item.vocabulary_sense for item in bundle.l1.blueprints
    }
    assert set(bundle.l2.public.allowed_vocabulary["canonical_operators"]) == {
        item.vocabulary_operator for item in bundle.l2.blueprints
    }
    assert set(bundle.l2.public.allowed_vocabulary["predicate_senses"]) == {
        item.vocabulary_sense for item in bundle.l2.blueprints
    }
    assert set(bundle.l2.public.allowed_vocabulary["operator_sense_bindings"]) == {
        f"{item.vocabulary_operator}|{item.vocabulary_sense}"
        for item in bundle.l2.blueprints
    }


def test_public_vocabulary_has_no_outcome_bearing_control_labels() -> None:
    bundle = build_fresh_v3_authoring_bundle(FORMAL_PREREG)
    labels = [
        value
        for layer in (bundle.l1.public, bundle.l2.public)
        for values in layer.allowed_vocabulary.values()
        for value in values
    ]
    forbidden = ("control", "unsupported", "unresolved", "incompatible", "incomplete")
    assert not [label for label in labels if any(token in label for token in forbidden)]


def test_validator_rejects_coherent_blueprint_replacement() -> None:
    bundle = build_fresh_v3_authoring_bundle(FORMAL_PREREG)
    blueprint = bundle.l1.blueprints[0]
    changed = blueprint.model_copy(
        update={
            "source_turn": {
                **blueprint.source_turn,
                "agent": blueprint.source_turn["agent"] + " Extra neutral context.",
            }
        }
    )
    with pytest.raises(ValueError, match="authored L1 blueprint manifest drift"):
        _rerender_and_validate_l1(
            bundle,
            (changed, *bundle.l1.blueprints[1:]),
        )


def test_public_private_family_field_leak_is_rejected() -> None:
    bundle = build_fresh_v3_authoring_bundle(FORMAL_PREREG)
    blueprint = bundle.l1.blueprints[0]
    qualifiers = dict(blueprint.untyped_candidate.qualifiers)
    qualifiers["primary_family"] = "false_emission"
    changed = blueprint.model_copy(
        update={
            "untyped_candidate": blueprint.untyped_candidate.model_copy(
                update={"qualifiers": qualifiers}
            )
        }
    )

    with pytest.raises(ValueError, match="private family field leaked"):
        _rerender_and_validate_l1(
            bundle,
            (changed, *bundle.l1.blueprints[1:]),
        )


def test_evidence_and_l2_literal_closure_are_exact() -> None:
    bundle = build_fresh_v3_authoring_bundle(FORMAL_PREREG)

    for case in bundle.l1.public.cases:
        for evidence in case.untyped_candidate.evidence:
            message = case.source_turn[evidence.message]
            assert message[evidence.start : evidence.end] == evidence.quote
    for public_case, gold_item in zip(
        bundle.l2.public.cases,
        bundle.l2.gold.items,
        strict=True,
    ):
        for evidence in public_case.untyped_candidate.evidence:
            support = next(
                item
                for item in public_case.typed_l1_support_pack
                if evidence.evidence_id
                in {binding.evidence_id for binding in item.evidence_bindings}
            )
            turn = next(
                item
                for item in public_case.source_turns
                if item.source_turn_ref == support.source_turn_ref
            )
            message = turn.user if evidence.speaker == "user" else turn.agent
            assert message[evidence.start : evidence.end] == evidence.quote
        expected = gold_item.expected_typed_candidate
        if expected is None:
            continue
        assert set(expected.supporting_l1_refs) == set(
            expected.closure.required_support_refs
        )
        assert {
            ref
            for claim in expected.structured_claims
            for ref in claim.supporting_l1_refs
        } == set(expected.supporting_l1_refs)
        primary = expected.structured_claims[0]
        assert primary.predicate.surface == public_case.untyped_candidate.predicate
        assert primary.local_entities[0].surface == public_case.untyped_candidate.subject
        assert primary.local_entities[1].surface == public_case.untyped_candidate.object


def test_formal_bundle_validates_with_zero_overlap() -> None:
    result = validate_fresh_v3_authoring_bundle(
        build_fresh_v3_authoring_bundle(FORMAL_PREREG),
        FORMAL_PREREG,
    )

    assert result == {
        "status": "valid",
        "l1_case_count": 24,
        "l2_case_count": 18,
        "l1_family_counts": L1_FAMILIES,
        "l2_family_counts": L2_FAMILIES,
        "prior_identifier_overlap_count": 0,
        "prior_evidence_overlap_count": 0,
        "prior_source_text_overlap_count": 0,
        "prior_semantic_signature_overlap_count": 0,
        "formal_artifacts_created": False,
        "model_request_count": 0,
    }


def test_inventory_contains_public_refs_lifecycle_operations_and_supports() -> None:
    bundle = build_fresh_v3_authoring_bundle(FORMAL_PREREG)
    inventory = authoring._new_inventory(bundle)

    public_l1 = bundle.l1.public.cases[0]
    assert public_l1.case_id in inventory.identifiers
    assert public_l1.candidate_ref in inventory.identifiers
    lifecycle_blueprint = next(
        item
        for item in bundle.l1.blueprints
        if item.untyped_candidate.lifecycle_links.replaces_candidate_refs
    )
    lifecycle_ref = lifecycle_blueprint.untyped_candidate.lifecycle_links.replaces_candidate_refs[0]
    assert lifecycle_ref in inventory.identifiers
    operation_blueprint = next(
        item
        for item in bundle.l1.blueprints
        if item.untyped_candidate.operation_provenance.added_by_operation_refs
    )
    operation_ref = operation_blueprint.untyped_candidate.operation_provenance.added_by_operation_refs[0]
    assert operation_ref in inventory.identifiers
    support = bundle.l2.blueprints[0].typed_l1_support_pack[0]
    support_signature = authoring._semantic_signature(
        support.model_dump(mode="json")
    )
    assert support_signature in inventory.semantic_signatures


def test_l1_reference_registry_resolves_owners_and_no_memory_has_no_operation() -> None:
    bundle = build_fresh_v3_authoring_bundle(FORMAL_PREREG)
    for blueprint in bundle.l1.blueprints:
        registry = blueprint.untyped_candidate.qualifiers["reference_registry"]
        candidate_refs = set(registry["candidate_refs"])
        operation_refs = set(registry["operation_refs"])
        candidate_records = registry["candidate_records"]
        operation_records = registry["operation_records"]
        assert candidate_refs == {
            record["candidate_ref"] for record in candidate_records
        }
        assert operation_refs == {
            record["operation_ref"] for record in operation_records
        }
        assert all(
            record["owner_candidate_ref"]
            == authoring._opaque("candidate", blueprint.candidate_id)
            for record in operation_records
        )
        if blueprint.expected_decision != "emit_l1":
            assert not operation_refs


def test_l1_current_lifecycle_candidates_use_forward_active_links() -> None:
    bundle = build_fresh_v3_authoring_bundle(FORMAL_PREREG)
    lifecycle_blueprints = [
        item for item in bundle.l1.blueprints if item.family == "lifecycle"
    ]

    for blueprint in lifecycle_blueprints[:2]:
        lifecycle = blueprint.untyped_candidate.lifecycle_links
        assert lifecycle.lifecycle == "active"
        assert lifecycle.replacement_candidate_ref is None
        assert blueprint.untyped_candidate.projection_status == "active"
    assert lifecycle_blueprints[0].untyped_candidate.lifecycle_links.replaces_candidate_refs
    assert lifecycle_blueprints[1].untyped_candidate.lifecycle_links.supersedes_candidate_refs


def test_l1_operation_registry_uses_canonical_kinds_and_shapes() -> None:
    bundle = build_fresh_v3_authoring_bundle(FORMAL_PREREG)
    allowed_kinds = {"confirm", "correct", "supersede", "conflict", "add"}
    for blueprint in bundle.l1.blueprints:
        if blueprint.expected_decision != "emit_l1":
            continue
        candidate_ref = authoring._opaque("candidate", blueprint.candidate_id)
        lifecycle = blueprint.untyped_candidate.lifecycle_links
        records = blueprint.untyped_candidate.qualifiers["reference_registry"][
            "operation_records"
        ]
        assert len(records) == 1
        record = records[0]
        assert record["operation_kind"] in allowed_kinds
        assert set(record) == {
            "operation_ref",
            "owner_candidate_ref",
            "operation_kind",
            "targets",
            "replacement_candidate_ref",
        }
        if lifecycle.replaces_candidate_refs:
            assert record["operation_kind"] == "correct"
            assert record["targets"] == lifecycle.replaces_candidate_refs
            assert record["replacement_candidate_ref"] == candidate_ref
        elif lifecycle.supersedes_candidate_refs:
            assert record["operation_kind"] == "supersede"
            assert record["targets"] == lifecycle.supersedes_candidate_refs
            assert record["replacement_candidate_ref"] is None
        elif lifecycle.conflicts_with_candidate_refs:
            assert record["operation_kind"] == "conflict"
            assert record["targets"] == sorted(
                [candidate_ref, *lifecycle.conflicts_with_candidate_refs]
            )
            assert record["replacement_candidate_ref"] is None
        else:
            assert record["operation_kind"] == "confirm"
            assert record["targets"] == [candidate_ref]
            assert record["replacement_candidate_ref"] is None


def test_l2_support_time_and_claim_modality_are_closed() -> None:
    bundle = build_fresh_v3_authoring_bundle(FORMAL_PREREG)
    for blueprint in bundle.l2.blueprints:
        expected = blueprint.expected_typed_candidate
        if expected is None:
            continue
        modalities = {support.modality for support in blueprint.typed_l1_support_pack}
        assert len(modalities) == 1
        assert expected.structured_claims[0].modality == next(iter(modalities))
        if blueprint.family == "state_summary_case":
            assert all(
                support.time.event_time or support.time.valid_time
                for support in blueprint.typed_l1_support_pack
            )
        if blueprint.family == "lifecycle_case":
            assert len(blueprint.support_lifecycle_bindings) == 2


def test_l2_persistent_summary_does_not_narrow_claim_time() -> None:
    bundle = build_fresh_v3_authoring_bundle(FORMAL_PREREG)
    summaries = [
        item for item in bundle.l2.blueprints if item.family == "state_summary_case"
    ]

    assert summaries
    assert all(
        item.expected_typed_candidate is not None
        and item.expected_typed_candidate.structured_claims[0].time
        == authoring.TypedTimeBinding()
        for item in summaries
    )


def test_l2_claim_time_is_bound_to_support_time() -> None:
    bundle = build_fresh_v3_authoring_bundle(FORMAL_PREREG)
    index = next(
        index
        for index, item in enumerate(bundle.l2.blueprints)
        if item.family == "lifecycle_case" and item.ordinal == 2
    )
    blueprint = bundle.l2.blueprints[index]
    expected = blueprint.expected_typed_candidate
    assert expected is not None
    claim = expected.structured_claims[0].model_copy(
        update={"time": authoring.TypedTimeBinding(event_time="2099-01-01")}
    )
    changed = blueprint.model_copy(
        update={
            "expected_typed_candidate": expected.model_copy(
                update={"structured_claims": [claim]}
            )
        }
    )
    with pytest.raises(ValueError, match="L2 claim time closure mismatch"):
        _rerender_and_validate_l2(
            bundle,
            tuple(changed if i == index else item for i, item in enumerate(bundle.l2.blueprints)),
        )


def test_l2_lifecycle_relation_direction_is_closed() -> None:
    bundle = build_fresh_v3_authoring_bundle(FORMAL_PREREG)
    index = next(
        index for index, item in enumerate(bundle.l2.blueprints) if item.family == "lifecycle_case"
    )
    blueprint = bundle.l2.blueprints[index]
    first, second = blueprint.support_lifecycle_bindings
    changed_first = first.model_copy(update={"relation": "supersedes"})
    changed = blueprint.model_copy(
        update={"support_lifecycle_bindings": (changed_first, second)}
    )
    with pytest.raises(ValueError, match="relation mismatch"):
        _rerender_and_validate_l2(
            bundle,
            tuple(changed if i == index else item for i, item in enumerate(bundle.l2.blueprints)),
        )


def test_l1_registry_rejects_duplicate_or_mismatched_operation_records() -> None:
    bundle = build_fresh_v3_authoring_bundle(FORMAL_PREREG)
    blueprint = next(
        item
        for item in bundle.l1.blueprints
        if item.untyped_candidate.operation_provenance.confirmed_by_operation_refs
    )
    registry = dict(blueprint.untyped_candidate.qualifiers["reference_registry"])
    records = list(registry["operation_records"])
    records.append(dict(records[0]))
    registry["operation_records"] = records
    qualifiers = dict(blueprint.untyped_candidate.qualifiers)
    qualifiers["reference_registry"] = registry
    changed = blueprint.model_copy(
        update={
            "untyped_candidate": blueprint.untyped_candidate.model_copy(
                update={"qualifiers": qualifiers}
            )
        }
    )
    with pytest.raises(ValueError, match="operation reference record closure"):
        _rerender_and_validate_l1(
            bundle,
            tuple(changed if item is blueprint else item for item in bundle.l1.blueprints),
        )


def test_duplicate_blueprint_id_is_rejected() -> None:
    bundle = build_fresh_v3_authoring_bundle(FORMAL_PREREG)
    duplicate = bundle.l1.blueprints[1].model_copy(
        update={"blueprint_id": bundle.l1.blueprints[0].blueprint_id}
    )
    changed_l1 = bundle.l1.model_copy(
        update={"blueprints": (bundle.l1.blueprints[0], duplicate, *bundle.l1.blueprints[2:])}
    )

    with pytest.raises(ValueError, match="duplicate L1 blueprint ID"):
        validate_fresh_v3_authoring_bundle(
            bundle.model_copy(update={"l1": changed_l1}), FORMAL_PREREG
        )


def test_invalid_l1_evidence_offset_is_rejected() -> None:
    bundle = build_fresh_v3_authoring_bundle(FORMAL_PREREG)
    blueprint = bundle.l1.blueprints[0]
    evidence = blueprint.untyped_candidate.evidence[0].model_copy(
        update={"start": blueprint.untyped_candidate.evidence[0].start + 1}
    )
    candidate = blueprint.untyped_candidate.model_copy(update={"evidence": [evidence]})
    changed = blueprint.model_copy(update={"untyped_candidate": candidate})
    changed_l1 = bundle.l1.model_copy(
        update={"blueprints": (changed, *bundle.l1.blueprints[1:])}
    )

    with pytest.raises(ValueError, match="L1 evidence offset mismatch"):
        validate_fresh_v3_authoring_bundle(
            bundle.model_copy(update={"l1": changed_l1}), FORMAL_PREREG
        )


def test_bundle_rejects_nested_coercive_existing_payload_value() -> None:
    bundle = build_fresh_v3_authoring_bundle(FORMAL_PREREG)
    blueprint = bundle.l1.blueprints[0]
    evidence = blueprint.untyped_candidate.evidence[0].model_copy(
        update={"start": 0.0}
    )
    candidate = blueprint.untyped_candidate.model_copy(
        update={"evidence": [evidence]}
    )
    changed = blueprint.model_copy(update={"untyped_candidate": candidate})
    changed_l1 = bundle.l1.model_copy(
        update={"blueprints": (changed, *bundle.l1.blueprints[1:])}
    )

    with pytest.raises(ValidationError, match="int_type"):
        validate_fresh_v3_authoring_bundle(
            bundle.model_copy(update={"l1": changed_l1}),
            FORMAL_PREREG,
        )


def test_l1_lifecycle_reference_registry_drift_is_rejected() -> None:
    bundle = build_fresh_v3_authoring_bundle(FORMAL_PREREG)
    index = next(
        index
        for index, item in enumerate(bundle.l1.blueprints)
        if item.untyped_candidate.lifecycle_links.supersedes_candidate_refs
    )
    blueprint = bundle.l1.blueprints[index]
    qualifiers = dict(blueprint.untyped_candidate.qualifiers)
    registry = dict(qualifiers["reference_registry"])
    registry["candidate_refs"] = ["candidate-deadbeefdeadbeef"]
    qualifiers["reference_registry"] = registry
    candidate = blueprint.untyped_candidate.model_copy(
        update={"qualifiers": qualifiers}
    )
    changed = blueprint.model_copy(update={"untyped_candidate": candidate})
    blueprints = list(bundle.l1.blueprints)
    blueprints[index] = changed
    changed_l1 = bundle.l1.model_copy(update={"blueprints": tuple(blueprints)})

    with pytest.raises(ValueError, match="L1 lifecycle reference registry mismatch"):
        validate_fresh_v3_authoring_bundle(
            bundle.model_copy(update={"l1": changed_l1}), FORMAL_PREREG
        )


def test_l1_operation_reference_registry_drift_is_rejected() -> None:
    bundle = build_fresh_v3_authoring_bundle(FORMAL_PREREG)
    blueprint = bundle.l1.blueprints[0]
    qualifiers = dict(blueprint.untyped_candidate.qualifiers)
    registry = dict(qualifiers["reference_registry"])
    registry["operation_refs"] = ["operation-deadbeefdeadbeef"]
    qualifiers["reference_registry"] = registry
    candidate = blueprint.untyped_candidate.model_copy(
        update={"qualifiers": qualifiers}
    )
    changed = blueprint.model_copy(update={"untyped_candidate": candidate})
    changed_l1 = bundle.l1.model_copy(
        update={"blueprints": (changed, *bundle.l1.blueprints[1:])}
    )

    with pytest.raises(ValueError, match="L1 operation reference registry mismatch"):
        validate_fresh_v3_authoring_bundle(
            bundle.model_copy(update={"l1": changed_l1}), FORMAL_PREREG
        )


def test_l1_condition_and_scope_bind_explicit_local_entities() -> None:
    bundle = build_fresh_v3_authoring_bundle(FORMAL_PREREG)
    blueprints = [
        item for item in bundle.l1.blueprints if item.family == "condition_or_scope"
    ]

    for blueprint in blueprints:
        expected = blueprint.expected_typed_candidate
        assert expected is not None
        bindings = [*expected.condition_bindings, *expected.scope_bindings]
        assert bindings
        entity_by_id = {
            item.local_entity_id: item.surface for item in expected.local_entities
        }
        for binding in bindings:
            assert binding.local_entity_ids
            assert all(
                entity_by_id[entity_id].casefold() in binding.value.casefold()
                for entity_id in binding.local_entity_ids
            )


def test_l1_evidence_speaker_drift_is_rejected() -> None:
    bundle = build_fresh_v3_authoring_bundle(FORMAL_PREREG)
    index = next(
        index
        for index, item in enumerate(bundle.l1.blueprints)
        if item.expected_typed_candidate is not None
    )
    blueprint = bundle.l1.blueprints[index]
    expected = blueprint.expected_typed_candidate
    assert expected is not None
    binding = expected.evidence_bindings[0].model_copy(
        update={"speaker": "assistant"}
    )
    changed = blueprint.model_copy(
        update={
            "expected_typed_candidate": expected.model_copy(
                update={"evidence_bindings": [binding]}
            )
        }
    )
    blueprints = list(bundle.l1.blueprints)
    blueprints[index] = changed

    with pytest.raises(ValueError, match="L1 evidence binding mismatch"):
        _rerender_and_validate_l1(bundle, tuple(blueprints))


def test_incomplete_l2_support_closure_is_rejected() -> None:
    bundle = build_fresh_v3_authoring_bundle(FORMAL_PREREG)
    index = next(
        index
        for index, item in enumerate(bundle.l2.blueprints)
        if item.expected_typed_candidate is not None
    )
    blueprint = bundle.l2.blueprints[index]
    expected = blueprint.expected_typed_candidate
    assert expected is not None
    closure = expected.closure.model_copy(
        update={"required_support_refs": expected.closure.required_support_refs[:1]}
    )
    changed = blueprint.model_copy(
        update={"expected_typed_candidate": expected.model_copy(update={"closure": closure})}
    )
    blueprints = list(bundle.l2.blueprints)
    blueprints[index] = changed
    changed_l2 = bundle.l2.model_copy(update={"blueprints": tuple(blueprints)})

    with pytest.raises(ValueError, match="L2 support closure mismatch"):
        validate_fresh_v3_authoring_bundle(
            bundle.model_copy(update={"l2": changed_l2}), FORMAL_PREREG
        )


def test_l2_support_session_drift_is_rejected() -> None:
    bundle = build_fresh_v3_authoring_bundle(FORMAL_PREREG)
    blueprint = bundle.l2.blueprints[0]
    support = blueprint.typed_l1_support_pack[0].model_copy(
        update={"source_session_ref": "session-deadbeefdeadbeef"}
    )
    changed = blueprint.model_copy(
        update={
            "typed_l1_support_pack": (
                support,
                *blueprint.typed_l1_support_pack[1:],
            )
        }
    )
    with pytest.raises(ValueError, match="L2 support session mismatch"):
        _rerender_and_validate_l2(
            bundle,
            (changed, *bundle.l2.blueprints[1:]),
        )


def test_l2_expected_evidence_omission_is_rejected() -> None:
    bundle = build_fresh_v3_authoring_bundle(FORMAL_PREREG)
    index = next(
        index
        for index, item in enumerate(bundle.l2.blueprints)
        if item.expected_typed_candidate is not None
    )
    blueprint = bundle.l2.blueprints[index]
    expected = blueprint.expected_typed_candidate
    assert expected is not None
    changed = blueprint.model_copy(
        update={
            "expected_typed_candidate": expected.model_copy(
                update={"evidence_bindings": []}
            )
        }
    )
    blueprints = list(bundle.l2.blueprints)
    blueprints[index] = changed

    with pytest.raises(ValueError, match="L2 evidence closure mismatch"):
        _rerender_and_validate_l2(bundle, tuple(blueprints))


def test_l2_public_evidence_speaker_drift_is_rejected() -> None:
    bundle = build_fresh_v3_authoring_bundle(FORMAL_PREREG)
    blueprint = bundle.l2.blueprints[0]
    evidence = blueprint.untyped_candidate.evidence[0].model_copy(
        update={"speaker": "assistant"}
    )
    candidate = blueprint.untyped_candidate.model_copy(
        update={"evidence": [evidence, *blueprint.untyped_candidate.evidence[1:]]}
    )
    changed = blueprint.model_copy(update={"untyped_candidate": candidate})

    with pytest.raises(ValueError, match="L2 evidence speaker mismatch"):
        _rerender_and_validate_l2(
            bundle,
            (changed, *bundle.l2.blueprints[1:]),
        )


def test_prior_source_text_overlap_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = build_fresh_v3_authoring_bundle(FORMAL_PREREG)
    text = bundle.l1.blueprints[0].source_turn["user"]
    original = authoring._build_prior_inventory

    def contaminated(preregistration_path: Path) -> authoring.PriorInventory:
        inventory = original(preregistration_path)
        return inventory.model_copy(
            update={
                "source_texts": sorted(
                    {*inventory.source_texts, authoring._normalize_text(text)}
                )
            }
        )

    monkeypatch.setattr(authoring, "_build_prior_inventory", contaminated)
    with pytest.raises(ValueError, match="prior source text overlap"):
        validate_fresh_v3_authoring_bundle(bundle, FORMAL_PREREG)


def test_prior_evidence_text_overlap_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = build_fresh_v3_authoring_bundle(FORMAL_PREREG)
    text = bundle.l1.blueprints[0].untyped_candidate.evidence[0].quote
    original = authoring._build_prior_inventory

    def contaminated(preregistration_path: Path) -> authoring.PriorInventory:
        inventory = original(preregistration_path)
        return inventory.model_copy(
            update={
                "evidence_texts": sorted(
                    {*inventory.evidence_texts, authoring._normalize_text(text)}
                )
            }
        )

    monkeypatch.setattr(authoring, "_build_prior_inventory", contaminated)
    with pytest.raises(ValueError, match="prior evidence text overlap"):
        validate_fresh_v3_authoring_bundle(bundle, FORMAL_PREREG)


def test_prior_l2_claim_signature_overlap_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = build_fresh_v3_authoring_bundle(FORMAL_PREREG)
    expected = next(
        item.expected_typed_candidate
        for item in bundle.l2.blueprints
        if item.expected_typed_candidate is not None
    )
    assert expected is not None
    signature = authoring._semantic_signature(
        expected.structured_claims[0].model_dump(mode="json")
    )
    original = authoring._build_prior_inventory

    def contaminated(preregistration_path: Path) -> authoring.PriorInventory:
        inventory = original(preregistration_path)
        return inventory.model_copy(
            update={
                "semantic_signatures": sorted(
                    {*inventory.semantic_signatures, signature}
                )
            }
        )

    monkeypatch.setattr(authoring, "_build_prior_inventory", contaminated)
    with pytest.raises(ValueError, match="prior semantic signature overlap"):
        validate_fresh_v3_authoring_bundle(bundle, FORMAL_PREREG)


def test_semantic_signature_normalizes_unicode_case_and_whitespace() -> None:
    first = {"surface": "Ａlpha   BETA", "kind": "State"}
    second = {"surface": "alpha beta", "kind": "state"}

    assert authoring._semantic_signature(first) == authoring._semantic_signature(
        second
    )


def test_receipt_freezes_exact_implementation_and_no_hidden(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)
    evaluation = tmp_path / "evaluation"

    payload = freeze_fresh_v3_authoring_receipt(
        prereg,
        evaluation,
        WORKSPACE,
        RECEIPT_TIME,
    )
    receipt = prereg.parent / "authoring-implementation-receipt.json"

    assert payload["schema_version"] == "typed-extractor-fresh-v3-authoring-receipt-v1"
    assert payload["evaluation_id"] == "typed-extractor-v3-fresh-hidden-v1"
    assert payload["preregistration_sha256"] == sha256_file(FORMAL_PREREG)
    assert payload["l1_case_count"] == 24
    assert payload["l2_case_count"] == 18
    assert payload["hidden_artifact_write_count"] == 0
    assert payload["model_request_count"] == 0
    assert payload["pipeline_integration_authorized"] is False
    assert payload["longmemeval_status"] == "structured_l2_identity_unresolved"
    assert payload["guard_results_sha256"] == sha256_file(GUARD_RESULTS)
    assert payload["guard_counts"] == GUARD_COUNTS
    assert receipt.stat().st_mode & 0o777 == 0o444
    assert not evaluation.exists()


def test_receipt_freeze_rebuilds_live_guard_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)
    guard_bundle = build_authoritative_conformance_bundle(
        GUARD_ROOT,
        "slice-v1",
        GUARD_RESULTS,
    )
    drifted_bundle = guard_bundle.model_copy(
        update={"l1_units": [*guard_bundle.l1_units, guard_bundle.l1_units[0]]}
    )
    monkeypatch.setattr(
        authoring,
        "build_authoritative_conformance_bundle",
        lambda *_args, **_kwargs: drifted_bundle,
        raising=False,
    )

    with pytest.raises(ValueError, match="live guard (fingerprint|count) drift"):
        freeze_fresh_v3_authoring_receipt(
            prereg,
            tmp_path / "evaluation",
            WORKSPACE,
            RECEIPT_TIME,
        )


def test_receipt_validator_rebuilds_live_guard_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)
    evaluation = tmp_path / "evaluation"
    freeze_fresh_v3_authoring_receipt(
        prereg,
        evaluation,
        WORKSPACE,
        RECEIPT_TIME,
    )
    guard_bundle = build_authoritative_conformance_bundle(
        GUARD_ROOT,
        "slice-v1",
        GUARD_RESULTS,
    )
    drifted_bundle = guard_bundle.model_copy(
        update={"l1_units": [*guard_bundle.l1_units, guard_bundle.l1_units[0]]}
    )
    monkeypatch.setattr(
        authoring,
        "build_authoritative_conformance_bundle",
        lambda *_args, **_kwargs: drifted_bundle,
        raising=False,
    )

    with pytest.raises(ValueError, match="live guard (fingerprint|count) drift"):
        validate_fresh_v3_authoring_receipt(
            prereg,
            evaluation,
            WORKSPACE,
        )


def test_receipt_publish_holds_preregistration_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)
    original = authoring._write_receipt_no_clobber
    lock_observed = False

    def observe_lock(
        receipt_path: Path,
        receipt: authoring.FreshV3AuthoringReceipt,
        *,
        before_publish: object = None,
    ) -> None:
        nonlocal lock_observed
        contender = os.open(prereg, os.O_RDONLY)
        try:
            try:
                fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                lock_observed = True
            else:
                fcntl.flock(contender, fcntl.LOCK_UN)
        finally:
            os.close(contender)
        original(receipt_path, receipt, before_publish=before_publish)

    monkeypatch.setattr(authoring, "_write_receipt_no_clobber", observe_lock)
    freeze_fresh_v3_authoring_receipt(
        prereg,
        tmp_path / "evaluation",
        WORKSPACE,
        RECEIPT_TIME,
    )

    assert lock_observed


def test_receipt_publish_uses_anonymous_inode_without_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)
    original_publish = getattr(authoring, "_publish_fd_noreplace", None)
    observations: list[tuple[int, int, str]] = []

    def observe_publish(
        descriptor: int,
        directory_descriptor: int,
        target_name: str,
    ) -> None:
        observations.append((descriptor, directory_descriptor, target_name))
        opened = os.fstat(descriptor)
        assert stat.S_ISREG(opened.st_mode)
        assert opened.st_nlink == 0
        assert stat.S_IMODE(opened.st_mode) == 0o444
        assert stat.S_ISDIR(os.fstat(directory_descriptor).st_mode)
        assert target_name == authoring.RECEIPT_NAME
        assert {path.name for path in prereg.parent.iterdir()} == {
            "preregistration.json"
        }
        assert original_publish is not None
        original_publish(descriptor, directory_descriptor, target_name)

    monkeypatch.setattr(
        authoring,
        "_publish_fd_noreplace",
        observe_publish,
        raising=False,
    )
    freeze_fresh_v3_authoring_receipt(
        prereg,
        tmp_path / "evaluation",
        WORKSPACE,
        RECEIPT_TIME,
    )

    assert len(observations) == 1
    assert {path.name for path in prereg.parent.iterdir()} == {
        "preregistration.json",
        authoring.RECEIPT_NAME,
    }


def test_receipt_publish_fails_closed_when_anonymous_inode_is_unsupported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)

    def unsupported(_directory: Path) -> int:
        raise RuntimeError("O_TMPFILE is unsupported")

    monkeypatch.setattr(
        authoring,
        "_open_anonymous_receipt",
        unsupported,
        raising=False,
    )
    with pytest.raises(RuntimeError, match="O_TMPFILE is unsupported"):
        freeze_fresh_v3_authoring_receipt(
            prereg,
            tmp_path / "evaluation",
            WORKSPACE,
            RECEIPT_TIME,
        )

    assert not (prereg.parent / authoring.RECEIPT_NAME).exists()


def test_receipt_publish_rejects_disappeared_concurrent_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)

    def report_missing_collision(
        _descriptor: int,
        _directory_descriptor: int,
        target_name: str,
    ) -> None:
        raise FileExistsError(f"injected missing target collision: {target_name}")

    monkeypatch.setattr(
        authoring,
        "_publish_fd_noreplace",
        report_missing_collision,
        raising=False,
    )
    with pytest.raises(ValueError, match="disappeared during publication"):
        freeze_fresh_v3_authoring_receipt(
            prereg,
            tmp_path / "evaluation",
            WORKSPACE,
            RECEIPT_TIME,
        )

    assert not list(
        prereg.parent.glob(f".{authoring.RECEIPT_NAME}.staging-*")
    )


def test_receipt_publish_converges_with_identical_concurrent_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)
    receipt = prereg.parent / authoring.RECEIPT_NAME
    original_publish = getattr(authoring, "_publish_fd_noreplace", None)

    def publish_identical_then_collide(
        descriptor: int,
        directory_descriptor: int,
        target_name: str,
    ) -> None:
        receipt.write_bytes(os.pread(descriptor, os.fstat(descriptor).st_size, 0))
        receipt.chmod(0o444)
        assert original_publish is not None
        original_publish(descriptor, directory_descriptor, target_name)

    monkeypatch.setattr(
        authoring,
        "_publish_fd_noreplace",
        publish_identical_then_collide,
        raising=False,
    )
    payload = freeze_fresh_v3_authoring_receipt(
        prereg,
        tmp_path / "evaluation",
        WORKSPACE,
        RECEIPT_TIME,
    )

    assert receipt.read_bytes() == canonical_json_bytes(payload)
    assert receipt.stat().st_mode & 0o777 == 0o444
    assert not list(
        prereg.parent.glob(f".{authoring.RECEIPT_NAME}.staging-*")
    )


def test_receipt_publish_rejects_different_concurrent_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)
    receipt = prereg.parent / authoring.RECEIPT_NAME
    foreign_content = b'{"foreign":true}\n'
    original_publish = getattr(authoring, "_publish_fd_noreplace", None)

    def publish_different_then_collide(
        descriptor: int,
        directory_descriptor: int,
        target_name: str,
    ) -> None:
        receipt.write_bytes(foreign_content)
        receipt.chmod(0o444)
        assert original_publish is not None
        original_publish(descriptor, directory_descriptor, target_name)

    monkeypatch.setattr(
        authoring,
        "_publish_fd_noreplace",
        publish_different_then_collide,
        raising=False,
    )
    with pytest.raises(ValueError, match="already differs"):
        freeze_fresh_v3_authoring_receipt(
            prereg,
            tmp_path / "evaluation",
            WORKSPACE,
            RECEIPT_TIME,
        )

    assert receipt.read_bytes() == foreign_content
    assert not list(
        prereg.parent.glob(f".{authoring.RECEIPT_NAME}.staging-*")
    )


def test_receipt_write_failure_leaves_no_target_or_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)
    receipt = prereg.parent / authoring.RECEIPT_NAME

    def fail_write(_descriptor: int, _content: bytes) -> int:
        raise OSError("injected receipt write failure")

    monkeypatch.setattr(authoring.os, "write", fail_write)
    with pytest.raises(OSError, match="injected receipt write failure"):
        freeze_fresh_v3_authoring_receipt(
            prereg,
            tmp_path / "evaluation",
            WORKSPACE,
            RECEIPT_TIME,
        )

    assert not receipt.exists()
    assert not list(
        prereg.parent.glob(f".{authoring.RECEIPT_NAME}.staging-*")
    )


def test_receipt_file_fsync_failure_leaves_no_target_or_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)
    receipt = prereg.parent / authoring.RECEIPT_NAME
    original_fsync = authoring.os.fsync

    def fail_file_fsync(descriptor: int) -> None:
        if stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OSError("injected receipt fsync failure")
        original_fsync(descriptor)

    monkeypatch.setattr(authoring.os, "fsync", fail_file_fsync)
    with pytest.raises(OSError, match="injected receipt fsync failure"):
        freeze_fresh_v3_authoring_receipt(
            prereg,
            tmp_path / "evaluation",
            WORKSPACE,
            RECEIPT_TIME,
        )

    assert not receipt.exists()
    assert not list(
        prereg.parent.glob(f".{authoring.RECEIPT_NAME}.staging-*")
    )


def test_receipt_parent_fsync_failure_leaves_complete_published_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)
    evaluation = tmp_path / "evaluation"
    expected = authoring._build_receipt(
        preregistration_path=prereg.resolve(),
        evaluation_root=evaluation.resolve(),
        workspace_root=WORKSPACE.resolve(),
        receipt_time=RECEIPT_TIME,
    )
    receipt = prereg.parent / authoring.RECEIPT_NAME
    original_fsync = authoring.os.fsync

    def fail_directory_fsync(descriptor: int) -> None:
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError("injected receipt directory fsync failure")
        original_fsync(descriptor)

    monkeypatch.setattr(authoring.os, "fsync", fail_directory_fsync)
    with pytest.raises(OSError, match="injected receipt directory fsync failure"):
        freeze_fresh_v3_authoring_receipt(
            prereg,
            evaluation,
            WORKSPACE,
            RECEIPT_TIME,
        )

    assert receipt.read_bytes() == canonical_json_bytes(expected)
    assert receipt.stat().st_mode & 0o777 == 0o444
    assert not list(
        prereg.parent.glob(f".{authoring.RECEIPT_NAME}.staging-*")
    )


def test_receipt_retry_fsyncs_existing_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)
    evaluation = tmp_path / "evaluation"
    freeze_fresh_v3_authoring_receipt(
        prereg,
        evaluation,
        WORKSPACE,
        RECEIPT_TIME,
    )
    original_fsync = authoring.os.fsync
    directory_fsync_count = 0

    def observe_directory_fsync(descriptor: int) -> None:
        nonlocal directory_fsync_count
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            directory_fsync_count += 1
        original_fsync(descriptor)

    monkeypatch.setattr(authoring.os, "fsync", observe_directory_fsync)
    freeze_fresh_v3_authoring_receipt(
        prereg,
        evaluation,
        WORKSPACE,
        RECEIPT_TIME,
    )

    assert directory_fsync_count == 1


def test_receipt_retry_rejects_target_replacement_after_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)
    evaluation = tmp_path / "evaluation"
    freeze_fresh_v3_authoring_receipt(
        prereg,
        evaluation,
        WORKSPACE,
        RECEIPT_TIME,
    )
    receipt = prereg.parent / authoring.RECEIPT_NAME
    replacement = prereg.parent / "foreign-receipt.json"
    foreign_content = b'{"foreign":true}\n'
    replacement.write_bytes(foreign_content)
    replacement.chmod(0o444)
    original_fsync_directory = authoring._fsync_directory

    def replace_after_fsync(path: Path) -> None:
        original_fsync_directory(path)
        os.replace(replacement, receipt)

    monkeypatch.setattr(authoring, "_fsync_directory", replace_after_fsync)
    with pytest.raises(ValueError, match="receipt path changed"):
        freeze_fresh_v3_authoring_receipt(
            prereg,
            evaluation,
            WORKSPACE,
            RECEIPT_TIME,
        )

    assert receipt.read_bytes() == foreign_content


def test_receipt_publish_rejects_target_replacement_after_directory_fsync(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)
    receipt = prereg.parent / authoring.RECEIPT_NAME
    replacement = prereg.parent / "foreign-receipt.json"
    foreign_content = b'{"foreign":true}\n'
    replacement.write_bytes(foreign_content)
    replacement.chmod(0o444)
    original_fsync = authoring.os.fsync
    replaced = False

    def replace_published_target(descriptor: int) -> None:
        nonlocal replaced
        original_fsync(descriptor)
        if stat.S_ISDIR(os.fstat(descriptor).st_mode) and not replaced:
            os.replace(replacement, receipt)
            replaced = True

    monkeypatch.setattr(authoring.os, "fsync", replace_published_target)
    with pytest.raises(ValueError, match="receipt path changed"):
        freeze_fresh_v3_authoring_receipt(
            prereg,
            tmp_path / "evaluation",
            WORKSPACE,
            RECEIPT_TIME,
        )

    assert replaced
    assert receipt.read_bytes() == foreign_content


def test_receipt_collision_rejects_target_replacement_after_directory_fsync(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)
    receipt = prereg.parent / authoring.RECEIPT_NAME
    replacement = prereg.parent / "foreign-receipt.json"
    foreign_content = b'{"foreign":true}\n'
    replacement.write_bytes(foreign_content)
    replacement.chmod(0o444)
    original_publish = authoring._publish_fd_noreplace
    original_fsync = authoring.os.fsync
    collision_created = False
    replaced = False

    def publish_identical_then_collide(
        descriptor: int,
        directory_descriptor: int,
        target_name: str,
    ) -> None:
        nonlocal collision_created
        receipt.write_bytes(os.pread(descriptor, os.fstat(descriptor).st_size, 0))
        receipt.chmod(0o444)
        collision_created = True
        original_publish(descriptor, directory_descriptor, target_name)

    def replace_collision_target(descriptor: int) -> None:
        nonlocal replaced
        original_fsync(descriptor)
        if (
            stat.S_ISDIR(os.fstat(descriptor).st_mode)
            and collision_created
            and not replaced
        ):
            os.replace(replacement, receipt)
            replaced = True

    monkeypatch.setattr(
        authoring,
        "_publish_fd_noreplace",
        publish_identical_then_collide,
    )
    monkeypatch.setattr(authoring.os, "fsync", replace_collision_target)
    with pytest.raises(ValueError, match="receipt path changed"):
        freeze_fresh_v3_authoring_receipt(
            prereg,
            tmp_path / "evaluation",
            WORKSPACE,
            RECEIPT_TIME,
        )

    assert collision_created
    assert replaced
    assert receipt.read_bytes() == foreign_content


def test_receipt_rejects_symlink_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)
    evaluation = tmp_path / "evaluation"
    expected = authoring._build_receipt(
        preregistration_path=prereg.resolve(),
        evaluation_root=evaluation.resolve(),
        workspace_root=WORKSPACE.resolve(),
        receipt_time=RECEIPT_TIME,
    )
    backing = tmp_path / "receipt-backing.json"
    backing.write_bytes(canonical_json_bytes(expected))
    backing.chmod(0o444)
    receipt = prereg.parent / authoring.RECEIPT_NAME
    receipt.symlink_to(backing)

    with pytest.raises(ValueError, match="regular non-symlink"):
        freeze_fresh_v3_authoring_receipt(
            prereg,
            evaluation,
            WORKSPACE,
            RECEIPT_TIME,
        )


def test_receipt_validator_rejects_symlink_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)
    evaluation = tmp_path / "evaluation"
    freeze_fresh_v3_authoring_receipt(
        prereg,
        evaluation,
        WORKSPACE,
        RECEIPT_TIME,
    )
    receipt = prereg.parent / authoring.RECEIPT_NAME
    backing = tmp_path / "receipt-backing.json"
    receipt.rename(backing)
    receipt.symlink_to(backing)

    with pytest.raises(ValueError, match="regular non-symlink"):
        validate_fresh_v3_authoring_receipt(
            prereg,
            evaluation,
            WORKSPACE,
        )


def test_receipt_freeze_rejects_preregistration_final_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)
    symlink = prereg.with_name("preregistration-symlink.json")
    symlink.symlink_to(prereg)

    with pytest.raises(ValueError, match="regular non-symlink"):
        freeze_fresh_v3_authoring_receipt(
            symlink,
            tmp_path / "evaluation",
            WORKSPACE,
            RECEIPT_TIME,
        )


def test_receipt_freeze_rejects_dangling_evaluation_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)
    evaluation = tmp_path / "evaluation"
    evaluation.symlink_to(tmp_path / "missing-evaluation-target")

    with pytest.raises(ValueError, match="evaluation root must be absent"):
        freeze_fresh_v3_authoring_receipt(
            prereg,
            evaluation,
            WORKSPACE,
            RECEIPT_TIME,
        )


def test_receipt_freeze_rejects_dangling_materialization_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)
    materialization = tmp_path / "typed_extractor_fresh_v3_materialization.py"
    materialization.symlink_to(tmp_path / "missing-materialization-target.py")
    monkeypatch.setattr(
        authoring,
        "MATERIALIZATION_WORKSPACE_PATHS",
        (str(materialization),),
    )

    with pytest.raises(ValueError, match="materialization artifact must be absent"):
        freeze_fresh_v3_authoring_receipt(
            prereg,
            tmp_path / "evaluation",
            WORKSPACE,
            RECEIPT_TIME,
        )


def test_receipt_freeze_rejects_preregistration_inode_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)
    original_build = authoring._build_receipt
    replaced = False

    def replace_after_build(**kwargs: object) -> authoring.FreshV3AuthoringReceipt:
        nonlocal replaced
        receipt = original_build(**kwargs)
        if not replaced:
            replacement = prereg.with_name("replacement.json")
            shutil.copy2(prereg, replacement)
            replacement.chmod(0o444)
            os.replace(replacement, prereg)
            replaced = True
        return receipt

    monkeypatch.setattr(authoring, "_build_receipt", replace_after_build)
    with pytest.raises(ValueError, match="preregistration path changed while locked"):
        freeze_fresh_v3_authoring_receipt(
            prereg,
            tmp_path / "evaluation",
            WORKSPACE,
            RECEIPT_TIME,
        )

    assert not (prereg.parent / authoring.RECEIPT_NAME).exists()


def test_receipt_validator_rejects_noncanonical_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)
    evaluation = tmp_path / "evaluation"
    freeze_fresh_v3_authoring_receipt(
        prereg,
        evaluation,
        WORKSPACE,
        RECEIPT_TIME,
    )
    receipt = prereg.parent / authoring.RECEIPT_NAME
    payload = load_json(receipt)
    receipt.chmod(0o644)
    receipt.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    receipt.chmod(0o444)

    with pytest.raises(ValueError, match="canonical JSON bytes"):
        validate_fresh_v3_authoring_receipt(prereg, evaluation, WORKSPACE)


def test_receipt_validator_reports_actual_receipt_sha256(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)
    evaluation = tmp_path / "evaluation"
    freeze_fresh_v3_authoring_receipt(
        prereg,
        evaluation,
        WORKSPACE,
        RECEIPT_TIME,
    )
    receipt = prereg.parent / authoring.RECEIPT_NAME

    result = validate_fresh_v3_authoring_receipt(
        prereg,
        evaluation,
        WORKSPACE,
    )

    assert result["receipt_sha256"] == sha256_file(receipt)


def test_receipt_validator_rejects_target_replacement_during_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)
    evaluation = tmp_path / "evaluation"
    freeze_fresh_v3_authoring_receipt(
        prereg,
        evaluation,
        WORKSPACE,
        RECEIPT_TIME,
    )
    receipt = prereg.parent / authoring.RECEIPT_NAME
    replacement = prereg.parent / "foreign-receipt.json"
    foreign_content = b'{"foreign":true}\n'
    replacement.write_bytes(foreign_content)
    replacement.chmod(0o444)
    original_build = authoring._build_receipt

    def replace_after_build(**kwargs: object) -> authoring.FreshV3AuthoringReceipt:
        expected = original_build(**kwargs)
        os.replace(replacement, receipt)
        return expected

    monkeypatch.setattr(authoring, "_build_receipt", replace_after_build)
    with pytest.raises(ValueError, match="receipt path changed"):
        validate_fresh_v3_authoring_receipt(
            prereg,
            evaluation,
            WORKSPACE,
        )

    assert receipt.read_bytes() == foreign_content


def test_receipt_validates_and_reports_future_absence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)
    evaluation = tmp_path / "evaluation"
    freeze_fresh_v3_authoring_receipt(prereg, evaluation, WORKSPACE, RECEIPT_TIME)

    result = validate_fresh_v3_authoring_receipt(
        prereg,
        evaluation,
        WORKSPACE,
    )
    receipt = prereg.parent / authoring.RECEIPT_NAME

    assert result == {
        "status": "valid",
        "active_receipt": "authoring-implementation-receipt.json",
        "l1_case_count": 24,
        "l2_case_count": 18,
        "evaluation_root_absent": True,
        "materialization_implementation_absent": True,
        "hidden_artifacts_created": False,
        "model_request_count": 0,
        "receipt_sha256": sha256_file(receipt),
    }


def test_receipt_freeze_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)
    evaluation = tmp_path / "evaluation"

    first = freeze_fresh_v3_authoring_receipt(
        prereg,
        evaluation,
        WORKSPACE,
        RECEIPT_TIME,
    )
    second = freeze_fresh_v3_authoring_receipt(
        prereg,
        evaluation,
        WORKSPACE,
        RECEIPT_TIME,
    )

    assert second == first


def test_receipt_build_rejects_non_preregistered_paths(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="chronology path mismatch"):
        authoring._build_receipt(
            preregistration_path=FORMAL_PREREG,
            evaluation_root=tmp_path / "evaluation",
            workspace_root=WORKSPACE,
            receipt_time=RECEIPT_TIME,
        )


def test_receipt_rejects_existing_evaluation_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)
    evaluation = tmp_path / "evaluation"
    evaluation.mkdir()

    with pytest.raises(ValueError, match="evaluation root must be absent"):
        freeze_fresh_v3_authoring_receipt(
            prereg,
            evaluation,
            WORKSPACE,
            RECEIPT_TIME,
        )


def test_receipt_rejects_premature_materialization_implementation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)
    premature = tmp_path / "typed_extractor_fresh_v3_materialization.py"
    premature.write_text("premature = True\n", encoding="utf-8")
    monkeypatch.setattr(
        authoring,
        "MATERIALIZATION_WORKSPACE_PATHS",
        (str(premature),),
    )

    with pytest.raises(ValueError, match="materialization artifact must be absent"):
        freeze_fresh_v3_authoring_receipt(
            prereg,
            tmp_path / "evaluation",
            WORKSPACE,
            RECEIPT_TIME,
        )


def test_receipt_rejects_impossible_utc_time(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)

    with pytest.raises(ValidationError, match="valid UTC timestamp"):
        freeze_fresh_v3_authoring_receipt(
            prereg,
            tmp_path / "evaluation",
            WORKSPACE,
            "2026-07-29T24:00:00Z",
        )


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("unexpected", True),
        ("l1_case_count", 24.0),
        ("l2_case_count", 18.0),
        ("hidden_artifact_write_count", False),
        ("model_request_count", False),
    ],
)
def test_receipt_rejects_unknown_or_coercive_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    key: str,
    value: object,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)
    evaluation = tmp_path / "evaluation"
    freeze_fresh_v3_authoring_receipt(prereg, evaluation, WORKSPACE, RECEIPT_TIME)
    receipt = prereg.parent / "authoring-implementation-receipt.json"
    payload = load_json(receipt)
    payload[key] = value
    _rewrite_json(receipt, payload)

    with pytest.raises(ValidationError):
        validate_fresh_v3_authoring_receipt(prereg, evaluation, WORKSPACE)


def test_receipt_rejects_code_hash_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)
    evaluation = tmp_path / "evaluation"
    freeze_fresh_v3_authoring_receipt(prereg, evaluation, WORKSPACE, RECEIPT_TIME)
    original = authoring.sha256_file

    def drift(path: Path) -> str:
        if path.name == "typed_extractor_fresh_v3_authoring.py":
            return "f" * 64
        return original(path)

    monkeypatch.setattr(authoring, "sha256_file", drift)
    with pytest.raises(ValueError, match="authoring receipt drift"):
        validate_fresh_v3_authoring_receipt(prereg, evaluation, WORKSPACE)


def test_receipt_rejects_shared_prereg_code_hash_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)
    monkeypatch.setattr(authoring, "PREREGISTRATION_SHA256", sha256_file(prereg))
    payload = load_json(prereg)
    code_hashes = dict(payload["code_sha256"])
    code_hashes["typed_extractor_l1.py"] = "f" * 64
    payload["code_sha256"] = code_hashes
    _rewrite_json(prereg, payload)
    monkeypatch.setattr(authoring, "PREREGISTRATION_SHA256", sha256_file(prereg))

    with pytest.raises(ValueError, match="preregistration code hash drift"):
        freeze_fresh_v3_authoring_receipt(
            prereg,
            tmp_path / "evaluation",
            WORKSPACE,
            RECEIPT_TIME,
        )


def test_receipt_rechecks_future_absence_after_bundle_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)
    evaluation = tmp_path / "evaluation"
    original = authoring._build_receipt
    calls = 0

    def racing_build(**kwargs: object) -> authoring.FreshV3AuthoringReceipt:
        nonlocal calls
        receipt = original(**kwargs)
        calls += 1
        if calls == 1:
            evaluation.mkdir()
        return receipt

    monkeypatch.setattr(authoring, "_build_receipt", racing_build)
    with pytest.raises(ValueError, match="evaluation root must be absent"):
        freeze_fresh_v3_authoring_receipt(
            prereg,
            evaluation,
            WORKSPACE,
            RECEIPT_TIME,
        )


def test_receipt_rebuilds_all_bindings_immediately_before_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)
    original = authoring._build_receipt
    calls = 0

    def drifting_build(**kwargs: object) -> authoring.FreshV3AuthoringReceipt:
        nonlocal calls
        calls += 1
        receipt = original(**kwargs)
        if calls == 2:
            hashes = dict(receipt.code_sha256)
            hashes["typed_extractor_fresh_v3_authoring.py"] = "f" * 64
            return receipt.model_copy(update={"code_sha256": hashes})
        return receipt

    monkeypatch.setattr(authoring, "_build_receipt", drifting_build)
    with pytest.raises(ValueError, match="inputs changed during receipt freeze"):
        freeze_fresh_v3_authoring_receipt(
            prereg,
            tmp_path / "evaluation",
            WORKSPACE,
            RECEIPT_TIME,
        )

    assert calls == 2
    assert not (prereg.parent / authoring.RECEIPT_NAME).exists()


def test_receipt_rechecks_bindings_after_anonymous_inode_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)
    original_build = authoring._build_receipt
    original_write = authoring._write_all
    staged = False
    calls = 0

    def observe_staging(descriptor: int, content: bytes) -> None:
        nonlocal staged
        original_write(descriptor, content)
        staged = True

    def drift_after_staging(**kwargs: object) -> authoring.FreshV3AuthoringReceipt:
        nonlocal calls
        calls += 1
        receipt = original_build(**kwargs)
        if staged:
            hashes = dict(receipt.code_sha256)
            hashes["typed_extractor_fresh_v3_authoring.py"] = "f" * 64
            return receipt.model_copy(update={"code_sha256": hashes})
        return receipt

    monkeypatch.setattr(authoring, "_write_all", observe_staging)
    monkeypatch.setattr(authoring, "_build_receipt", drift_after_staging)

    with pytest.raises(ValueError, match="inputs changed during receipt freeze"):
        freeze_fresh_v3_authoring_receipt(
            prereg,
            tmp_path / "evaluation",
            WORKSPACE,
            RECEIPT_TIME,
        )

    assert calls >= 2
    assert not (prereg.parent / authoring.RECEIPT_NAME).exists()


def test_preregistration_and_receipt_require_exact_0444_and_filename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _allow_temp_receipt_paths(monkeypatch)
    prereg = _copy_preregistration(tmp_path)
    monkeypatch.setattr(authoring, "PREREGISTRATION_SHA256", sha256_file(prereg))
    prereg.chmod(0o400)
    with pytest.raises(ValueError, match="mode 0444"):
        build_fresh_v3_authoring_bundle(prereg)

    prereg.chmod(0o444)
    renamed = prereg.with_name("renamed.json")
    prereg.rename(renamed)
    with pytest.raises(ValueError, match="filename"):
        authoring._build_receipt(
            preregistration_path=renamed,
            evaluation_root=tmp_path / "evaluation",
            workspace_root=WORKSPACE,
            receipt_time=RECEIPT_TIME,
        )


def test_receipt_model_is_strict() -> None:
    schema = FreshV3AuthoringReceipt.model_json_schema()
    assert schema["additionalProperties"] is False
