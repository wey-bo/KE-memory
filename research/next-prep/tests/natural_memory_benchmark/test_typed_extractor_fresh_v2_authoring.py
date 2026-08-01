from __future__ import annotations

import copy
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from tools.natural_memory_benchmark.io import canonical_json_bytes, load_json
from tools.natural_memory_benchmark.typed_extractor_fresh_v2_authoring import (
    build_fresh_v2_authoring_bundle,
    freeze_fresh_v2_authoring_receipt,
    freeze_fresh_v2_authoring_supersession_receipt,
    validate_fresh_v2_active_authoring_receipt,
    validate_fresh_v2_authoring_bundle,
    validate_fresh_v2_authoring_receipt,
    validate_fresh_v2_authoring_supersession_receipt,
)


WORKSPACE = Path(".")
PREREGISTRATION = Path(
    "artifacts/automatic-extraction-assessment/"
    "typed-extractor-v2-fresh-hidden-prereg-v3/preregistration.json"
)
OFFICIAL_EVALUATION_ROOT = Path(
    "artifacts/automatic-extraction-assessment/"
    "typed-extractor-v2-fresh-hidden-v2"
)
RECEIPT_TIME = "2026-07-28T14:09:00Z"
ORIGINAL_RECEIPT = PREREGISTRATION.parent / "authoring-implementation-receipt.json"
ORIGINAL_RECEIPT_SHA256 = (
    "4bb2575d985126dfbd91d01a3111d3f4acb2ebe57c3bfd62b1d60ee847d7314d"
)

L1_FAMILIES = (
    "explicit_event_roles",
    "condition_scope",
    "modality_time",
    "lifecycle_revision",
    "derivation_epistemic",
    "abstention_no_memory_controls",
)
L2_FAMILIES = (
    "coreference_task_composition",
    "preference_state_aggregation",
    "lifecycle_supersession",
    "multi_evidence_closure",
    "abstraction_structured_claim_boundary",
    "abstention_unresolved_controls",
)


def _build() -> Any:
    return build_fresh_v2_authoring_bundle(PREREGISTRATION)


def _copy_read_only_preregistration(tmp_path: Path) -> Path:
    copied = tmp_path / "preregistration.json"
    shutil.copyfile(PREREGISTRATION, copied)
    copied.chmod(0o444)
    return copied


def _receipt_paths(tmp_path: Path) -> tuple[Path, Path]:
    return _copy_read_only_preregistration(tmp_path), tmp_path / "fresh-hidden-v2"


def _supersession_paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    preregistration_path, evaluation_root = _receipt_paths(tmp_path)
    predecessor = preregistration_path.parent / ORIGINAL_RECEIPT.name
    shutil.copyfile(ORIGINAL_RECEIPT, predecessor)
    predecessor.chmod(0o444)
    return preregistration_path, evaluation_root, predecessor


def _canonical(value: Any) -> bytes:
    return canonical_json_bytes(value.model_dump(mode="json"))


def _layer_payloads(bundle: Any, layer: str) -> tuple[Any, Any, Any, Any, Any]:
    rendered = getattr(bundle, layer)
    return (
        rendered.source,
        rendered.public,
        rendered.authority,
        rendered.gold,
        rendered.manifest,
    )


def _cases(payload: Any) -> list[Any]:
    return list(getattr(payload, "cases", getattr(payload, "items", [])))


def _strict_model_validation(bundle: Any) -> None:
    from tools.natural_memory_benchmark.typed_extractor_l1 import (
        L1AuthorityPayload,
        L1GoldPayload,
        L1Manifest,
        L1PublicPayload,
        L1SourceConfig,
    )
    from tools.natural_memory_benchmark.typed_extractor_l2 import (
        L2AuthorityPayload,
        L2GoldPayload,
        L2Manifest,
        L2PublicPayload,
        L2SourceConfig,
    )

    l1_source, l1_public, l1_authority, l1_gold, l1_manifest = _layer_payloads(
        bundle, "l1"
    )
    l2_source, l2_public, l2_authority, l2_gold, l2_manifest = _layer_payloads(
        bundle, "l2"
    )
    for model, payload in (
        (L1SourceConfig, l1_source),
        (L1PublicPayload, l1_public),
        (L1AuthorityPayload, l1_authority),
        (L1GoldPayload, l1_gold),
        (L1Manifest, l1_manifest),
        (L2SourceConfig, l2_source),
        (L2PublicPayload, l2_public),
        (L2AuthorityPayload, l2_authority),
        (L2GoldPayload, l2_gold),
        (L2Manifest, l2_manifest),
    ):
        assert model.model_validate(payload.model_dump(mode="json")) == payload


def test_builds_all_preregistered_blueprints_in_stable_family_ordinal_order() -> None:
    bundle = _build()

    assert [(item.family, item.ordinal) for item in bundle.l1.blueprints] == [
        (family, ordinal)
        for family in L1_FAMILIES
        for ordinal in range(1, 5)
    ]
    assert [(item.family, item.ordinal) for item in bundle.l2.blueprints] == [
        (family, ordinal)
        for family in L2_FAMILIES
        for ordinal in range(1, 3)
    ]
    assert len(bundle.l1.blueprints) == 24
    assert len(bundle.l2.blueprints) == 12
    assert bundle.preregistration_sha256 == (
        "1455bb7d5bb35b61809c78180ebf766573c1561e39bbeddda4a80f939a893760"
    )
    assert bundle.namespace == "typed-extractor-fresh-hidden-v2-authored:2026-07-28"
    validate_fresh_v2_authoring_bundle(bundle, PREREGISTRATION)


@pytest.mark.parametrize("mutation", ["duplicate", "changed"])
def test_validation_rejects_duplicate_or_changed_blueprint_ids(
    mutation: str,
) -> None:
    bundle = _build()
    blueprints = list(bundle.l1.blueprints)
    replacement_id = (
        blueprints[0].blueprint_id
        if mutation == "duplicate"
        else "fresh-v2-l1-explicit_event_roles-99"
    )
    blueprints[1] = blueprints[1].model_copy(
        update={"blueprint_id": replacement_id}
    )
    changed = bundle.model_copy(
        update={
            "l1": bundle.l1.model_copy(
                update={"blueprints": tuple(blueprints)}
            )
        }
    )

    with pytest.raises(ValueError, match="blueprint ID.*drift|duplicate.*blueprint ID"):
        validate_fresh_v2_authoring_bundle(changed, PREREGISTRATION)


def test_bundle_renders_existing_strict_l1_and_l2_payload_models() -> None:
    bundle = _build()

    _strict_model_validation(bundle)
    for layer, expected_count in (("l1", 24), ("l2", 12)):
        source, public, authority, gold, manifest = _layer_payloads(bundle, layer)
        assert len(source.cases) == expected_count
        assert public.case_count == expected_count
        assert authority.case_count == expected_count
        assert gold.case_count == expected_count
        assert manifest.case_count == expected_count


def test_bundle_is_deterministic_and_does_not_mutate_formal_artifacts() -> None:
    """Building the bundle twice is deterministic and writes nothing.

    The absence assertions were dropped: the official evaluation root was committed
    as evidence after this test was written, and it has existed since before the
    reorganization baseline. What the test actually protects is that building does
    not *change* anything, so the root's contents and the receipt are captured before
    and compared after -- a stronger check than absence, since it would also catch a
    build that quietly rewrote an existing artifact.
    """
    receipt_path = PREREGISTRATION.parent / "authoring-implementation-receipt.json"
    receipt_before = receipt_path.read_bytes() if receipt_path.exists() else None
    root_before = (
        {
            path.relative_to(OFFICIAL_EVALUATION_ROOT).as_posix(): path.read_bytes()
            for path in sorted(OFFICIAL_EVALUATION_ROOT.rglob("*"))
            if path.is_file()
        }
        if OFFICIAL_EVALUATION_ROOT.exists()
        else None
    )

    first = _build()
    second = _build()

    assert _canonical(first) == _canonical(second)
    receipt_after = receipt_path.read_bytes() if receipt_path.exists() else None
    assert receipt_after == receipt_before
    root_after = (
        {
            path.relative_to(OFFICIAL_EVALUATION_ROOT).as_posix(): path.read_bytes()
            for path in sorted(OFFICIAL_EVALUATION_ROOT.rglob("*"))
            if path.is_file()
        }
        if OFFICIAL_EVALUATION_ROOT.exists()
        else None
    )
    assert root_after == root_before


def test_public_payloads_exclude_private_family_authority_and_gold_material() -> None:
    bundle = _build()

    l1_payload = bundle.l1.public.model_dump(mode="json")
    l2_payload = bundle.l2.public.model_dump(mode="json")
    assert set(l1_payload) == {
        "schema_version", "dataset_id", "case_count", "allowed_vocabulary", "cases"
    }
    assert set(l2_payload) == set(l1_payload)
    assert all(
        set(case) == {"case_id", "candidate_ref", "source_turn", "untyped_candidate"}
        for case in l1_payload["cases"]
    )
    assert all(
        set(case) == {
            "case_id",
            "candidate_ref",
            "source_session_ref",
            "source_turns",
            "untyped_candidate",
            "typed_l1_support_pack",
        }
        for case in l2_payload["cases"]
    )
    serialized = json.dumps({"l1": l1_payload, "l2": l2_payload}, sort_keys=True)
    for layer in (bundle.l1, bundle.l2):
        for blueprint in layer.blueprints:
            assert blueprint.private_case_id not in serialized
            assert blueprint.blueprint_id not in serialized


def test_l1_public_catalog_membership_does_not_reveal_hidden_decisions() -> None:
    bundle = _build()
    operators = set(bundle.l1.public.allowed_vocabulary["canonical_operators"])
    membership_by_decision: dict[str, set[bool]] = {}
    for blueprint in bundle.l1.blueprints:
        operator = blueprint.untyped_candidate.predicate.replace(" ", "_")
        membership_by_decision.setdefault(
            blueprint.expected_decision, set()
        ).add(operator in operators)

    assert membership_by_decision == {
        "abstain": {True},
        "emit_l1": {True},
        "no_memory": {True},
    }


def test_l2_public_catalog_membership_does_not_reveal_hidden_decisions() -> None:
    bundle = _build()
    operators = set(bundle.l2.public.allowed_vocabulary["canonical_operators"])
    operator_by_id = {
        "fresh-v2-l2-coreference_task_composition-01": "compose_dossier_workflow",
        "fresh-v2-l2-coreference_task_composition-02": "compose_imaging_workflow",
        "fresh-v2-l2-preference_state_aggregation-01": "aggregate_desk_preferences",
        "fresh-v2-l2-preference_state_aggregation-02": "summarize_ankle_state",
        "fresh-v2-l2-lifecycle_supersession-01": "resolve_invoice_recipient",
        "fresh-v2-l2-lifecycle_supersession-02": "resolve_demo_schedule",
        "fresh-v2-l2-multi_evidence_closure-01": "summarize_pump_incident",
        "fresh-v2-l2-multi_evidence_closure-02": "compose_project_progression",
        "fresh-v2-l2-abstraction_structured_claim_boundary-01": "aggregate_travel_profile",
        "fresh-v2-l2-abstraction_structured_claim_boundary-02": "compose_unrelated_project",
        "fresh-v2-l2-abstention_unresolved_controls-01": "resolve_option_selection",
        "fresh-v2-l2-abstention_unresolved_controls-02": "resolve_audit_leader",
    }
    membership_by_decision: dict[str, set[bool]] = {}
    for blueprint in bundle.l2.blueprints:
        membership_by_decision.setdefault(
            blueprint.expected_decision, set()
        ).add(operator_by_id[blueprint.blueprint_id] in operators)

    assert membership_by_decision == {
        "abstain": {True},
        "emit_l2": {True},
    }


def test_l1_gold_preserves_named_entities_and_exercises_operations() -> None:
    bundle = _build()
    expected_surfaces = {
        "fresh-v2-l1-condition_scope-02": {"the coral dashboard", "workspace Juniper"},
        "fresh-v2-l1-condition_scope-04": {"the bronze deployment", "checkpoint Kappa"},
        "fresh-v2-l1-modality_time-01": {"the user", "vault Sigma"},
        "fresh-v2-l1-modality_time-02": {"the user", "lab Cinder"},
        "fresh-v2-l1-modality_time-03": {"the user", "permit P9"},
        "fresh-v2-l1-lifecycle_revision-01": {"the launch review", "Thursday", "Friday"},
        "fresh-v2-l1-lifecycle_revision-02": {"locker Jade", "access code 4821"},
        "fresh-v2-l1-lifecycle_revision-03": {"folder", "Quartz", "Saffron"},
        "fresh-v2-l1-lifecycle_revision-04": {"batch 14", "passed", "failed"},
        "fresh-v2-l1-derivation_epistemic-01": {"gauge L6", "72 kPa"},
        "fresh-v2-l1-derivation_epistemic-02": {"the assistant", "the orchid report"},
        "fresh-v2-l1-derivation_epistemic-03": {"the user", "the cedar draft", "the signed appendix"},
    }
    by_id = {item.blueprint_id: item for item in bundle.l1.blueprints}
    for blueprint_id, surfaces in expected_surfaces.items():
        typed = by_id[blueprint_id].expected_typed_candidate
        assert typed is not None
        assert surfaces.issubset(
            {item.surface for item in typed.local_entities}
        )

    emitted = [
        item.expected_typed_candidate
        for item in bundle.l1.blueprints
        if item.expected_typed_candidate is not None
    ]
    assert any(
        item.operation_provenance.confirmed_by_operation_refs
        or item.operation_provenance.added_by_operation_refs
        for item in emitted
    )


def test_l2_supports_preserve_per_turn_semantics() -> None:
    bundle = _build()
    by_id = {item.blueprint_id: item for item in bundle.l2.blueprints}

    invoice = by_id["fresh-v2-l2-lifecycle_supersession-01"]
    invoice_surfaces = [
        {entity.surface for entity in support.local_entities}
        for support in invoice.typed_l1_support_pack
    ]
    assert "Malik" in invoice_surfaces[0] and "Priya" not in invoice_surfaces[0]
    assert "Priya" in invoice_surfaces[1]

    schedule = by_id["fresh-v2-l2-lifecycle_supersession-02"]
    schedule_surfaces = [
        {entity.surface for entity in support.local_entities}
        for support in schedule.typed_l1_support_pack
    ]
    assert "Monday" in schedule_surfaces[0] and "Wednesday" not in schedule_surfaces[0]
    assert "Wednesday" in schedule_surfaces[1]

    unrelated = by_id["fresh-v2-l2-abstraction_structured_claim_boundary-02"]
    unrelated_surfaces = [
        {entity.surface for entity in support.local_entities}
        for support in unrelated.typed_l1_support_pack
    ]
    assert "bicycle Kestrel" in unrelated_surfaces[0]
    assert "marine biology" not in unrelated_surfaces[0]
    assert "marine biology" in unrelated_surfaces[1]

    travel = by_id["fresh-v2-l2-abstraction_structured_claim_boundary-01"]
    expected = travel.expected_typed_candidate
    assert expected is not None
    assert len(expected.structured_claims) == 1
    assert expected.structured_claims[0].predicate.canonical_operator == (
        "aggregate_travel_profile"
    )
    assert expected.structured_claims[0].predicate.sense == (
        "preference.travel_profile"
    )
    assert expected.structured_claims[0].supporting_l1_refs == (
        expected.supporting_l1_refs
    )
    assert expected.abstraction.method == "preference_aggregation"
    assert expected.closure.pattern == "multi_evidence_set"



def test_l2_primary_claims_copy_public_candidate_literal_bindings() -> None:
    bundle = _build()

    for blueprint in bundle.l2.blueprints:
        expected = blueprint.expected_typed_candidate
        if expected is None:
            continue
        primary = expected.structured_claims[0]
        entities = {
            entity.local_entity_id: entity.surface
            for entity in primary.local_entities
        }
        theme_surfaces = {
            entities[role.local_entity_id]
            for role in primary.roles
            if role.role == "theme"
        }

        assert primary.predicate.surface == blueprint.untyped_candidate.predicate
        assert primary.local_entities[0].surface == blueprint.untyped_candidate.subject
        assert theme_surfaces == {blueprint.untyped_candidate.object}
        assert primary.supporting_l1_refs == expected.supporting_l1_refs


def test_validation_rejects_l2_primary_claim_literal_binding_drift() -> None:
    bundle = _build()
    blueprints = list(bundle.l2.blueprints)
    emitted_index = next(
        index
        for index, blueprint in enumerate(blueprints)
        if blueprint.expected_typed_candidate is not None
    )
    blueprint = blueprints[emitted_index]
    expected = blueprint.expected_typed_candidate
    assert expected is not None
    claims = list(expected.structured_claims)
    claims[0] = claims[0].model_copy(
        update={
            "predicate": claims[0].predicate.model_copy(
                update={"surface": "drifted predicate"}
            )
        }
    )
    blueprints[emitted_index] = blueprint.model_copy(
        update={
            "expected_typed_candidate": expected.model_copy(
                update={"structured_claims": claims}
            )
        }
    )
    changed = bundle.model_copy(
        update={
            "l2": bundle.l2.model_copy(
                update={"blueprints": tuple(blueprints)}
            )
        }
    )

    with pytest.raises(ValueError, match="L2 primary claim literal binding drift"):
        validate_fresh_v2_authoring_bundle(changed, PREREGISTRATION)


def test_rendered_payloads_have_opaque_id_parity_and_closed_evidence_references() -> None:
    bundle = _build()

    for layer in ("l1", "l2"):
        source, public, authority, gold, _ = _layer_payloads(bundle, layer)
        source_cases = _cases(source)
        public_cases = _cases(public)
        authority_cases = _cases(authority)
        gold_cases = _cases(gold)
        assert [case.case_id for case in public_cases] == [
            case.case_id for case in authority_cases
        ] == [case.case_id for case in gold_cases]
        assert [case.candidate_ref for case in public_cases] == [
            case.candidate_ref for case in authority_cases
        ] == [case.candidate_ref for case in gold_cases]
        assert len({case.case_id for case in public_cases}) == len(public_cases)
        assert len({case.candidate_ref for case in public_cases}) == len(public_cases)
        assert len(source_cases) == len(public_cases)

        for source_case, public_case, authority_case in zip(
            source_cases, public_cases, authority_cases, strict=True
        ):
            evidence = public_case.untyped_candidate.evidence
            evidence_ids = [item.evidence_id for item in evidence]
            assert evidence_ids == [
                item.evidence_id for item in authority_case.required_evidence_bindings
            ]
            evidence_messages: dict[str, str] = {}
            if layer == "l1":
                evidence_messages = {
                    item.evidence_id: public_case.source_turn[item.message]
                    for item in evidence
                }
            else:
                turns = {item.source_turn_ref: item for item in public_case.source_turns}
                for support in public_case.typed_l1_support_pack:
                    turn = turns[support.source_turn_ref]
                    for binding in support.evidence_bindings:
                        evidence_messages[binding.evidence_id] = getattr(
                            turn, "agent" if binding.speaker != "user" else "user"
                        )
            for item in evidence:
                message = evidence_messages[item.evidence_id]
                assert message[item.start : item.end] == item.quote
                assert item.end > item.start
            assert source_case.private_case_id not in {
                public_case.case_id,
                public_case.candidate_ref,
            }


def test_l1_and_l2_typed_reference_and_closure_contracts_are_complete() -> None:
    bundle = _build()
    l1_source, _, l1_authority, l1_gold, _ = _layer_payloads(bundle, "l1")
    l2_source, l2_public, l2_authority, l2_gold, _ = _layer_payloads(bundle, "l2")

    for source_case, authority_case, gold_item in zip(
        l1_source.cases, l1_authority.cases, l1_gold.items, strict=True
    ):
        expected = source_case.expected_typed_candidate
        assert source_case.expected_decision == gold_item.expected_decision
        assert authority_case.emission_allowed == source_case.emission_allowed
        if expected is not None:
            evidence_ids = {item.evidence_id for item in expected.evidence_bindings}
            assert set(expected.derivation.evidence_ids).issubset(evidence_ids)
            assert evidence_ids == {
                item.evidence_id for item in authority_case.required_evidence_bindings
            }

    public_by_id = {case.case_id: case for case in l2_public.cases}
    for source_case, authority_case, gold_item in zip(
        l2_source.cases, l2_authority.cases, l2_gold.items, strict=True
    ):
        expected = source_case.expected_typed_candidate
        assert source_case.expected_decision == gold_item.expected_decision
        if expected is None:
            assert source_case.unresolved_required_fields
            continue
        support_refs = set(expected.supporting_l1_refs)
        assert support_refs == set(expected.closure.required_support_refs)
        assert support_refs == set(authority_case.required_support_refs)
        assert set(expected.source_turn_refs) == {
            item.source_turn_ref
            for item in public_by_id[authority_case.case_id].typed_l1_support_pack
        }
        assert set(expected.source_session_refs) == {
            item.source_session_ref
            for item in public_by_id[authority_case.case_id].typed_l1_support_pack
        }
        assert set().union(
            *(set(claim.supporting_l1_refs) for claim in expected.structured_claims)
        ) == support_refs


def test_prior_inventory_is_bound_to_all_preregistered_inputs() -> None:
    bundle = _build()
    preregistration = load_json(PREREGISTRATION)

    assert bundle.prior_inventory.input_sha256 == preregistration["input_sha256"]
    assert bundle.prior_inventory.private_or_public_ids
    assert bundle.prior_inventory.evidence_ids
    assert bundle.prior_inventory.normalized_source_texts
    assert bundle.prior_inventory.semantic_signatures


@pytest.mark.parametrize("group", ["l1-dev", "fresh-v1/l2"])
def test_prior_inventory_derives_cross_file_public_gold_semantics(group: str) -> None:
    from tools.natural_memory_benchmark.typed_extractor_fresh_v2_authoring import (
        _semantic_signature,
    )
    from tools.natural_memory_benchmark.typed_extractor_fresh_v2_prereg import (
        _input_paths,
    )

    bundle = _build()
    paths = _input_paths(WORKSPACE_ROOT)
    layer = "l1" if group == "l1-dev" else "l2"
    public = load_json(paths[f"{group}/public-{layer}.json"])
    gold = load_json(paths[f"{group}/gold-{layer}.json"])
    public_by_id = {item["case_id"]: item for item in public["cases"]}
    gold_item = gold["items"][0]
    public_item = public_by_id[gold_item["case_id"]]
    expected = _semantic_signature(
        gold_item["expected_decision"],
        public_item["untyped_candidate"],
        gold_item.get("expected_typed_candidate"),
    )

    assert expected in bundle.prior_inventory.semantic_signatures


def test_validation_rejects_omitted_derived_prior_inventory_entries() -> None:
    bundle = _build()
    omitted = bundle.prior_inventory.model_copy(
        update={"normalized_source_texts": ()}
    )

    with pytest.raises(ValueError, match="prior inventory.*drift"):
        validate_fresh_v2_authoring_bundle(
            bundle.model_copy(update={"prior_inventory": omitted}),
            PREREGISTRATION,
        )


@pytest.mark.parametrize(
    "inventory_field, match",
    [
        ("private_or_public_ids", "identifier.*contamination"),
        ("evidence_ids", "evidence.*contamination"),
        ("normalized_source_texts", "source.*contamination"),
        ("semantic_signatures", "semantic.*contamination"),
    ],
)
def test_validation_rejects_overlap_with_the_derived_prior_inventory(
    inventory_field: str,
    match: str,
) -> None:
    bundle = _build()
    current = list(getattr(bundle.current_inventory, inventory_field))
    prior = bundle.prior_inventory.model_copy(
        update={
            inventory_field: tuple(
                [*getattr(bundle.prior_inventory, inventory_field), current[0]]
            )
        }
    )
    contaminated = bundle.model_copy(update={"prior_inventory": prior})

    with pytest.raises(ValueError, match=match):
        validate_fresh_v2_authoring_bundle(contaminated, PREREGISTRATION)


def test_source_normalization_is_nfkc_casefolded_and_whitespace_collapsed() -> None:
    bundle = _build()
    current_text = bundle.current_inventory.normalized_source_texts[0]
    variant = f"  {current_text.upper()}\n\t"
    prior = bundle.prior_inventory.model_copy(
        update={
            "normalized_source_texts": tuple(
                [*bundle.prior_inventory.normalized_source_texts, variant]
            )
        }
    )

    with pytest.raises(ValueError, match="source.*contamination"):
        validate_fresh_v2_authoring_bundle(
            bundle.model_copy(update={"prior_inventory": prior}), PREREGISTRATION
        )


def test_semantic_signatures_distinguish_role_and_closure_structure() -> None:
    from tools.natural_memory_benchmark.typed_extractor_fresh_v2_authoring import (
        _semantic_signature,
    )

    bundle = _build()
    l1_blueprint = next(
        item
        for item in bundle.l1.blueprints
        if item.expected_typed_candidate is not None
        and len(item.expected_typed_candidate.roles) >= 2
    )
    l1_typed = l1_blueprint.expected_typed_candidate
    assert l1_typed is not None
    swapped_roles = list(l1_typed.roles)
    first_id = swapped_roles[0].local_entity_id
    second_id = swapped_roles[1].local_entity_id
    swapped_roles[0] = swapped_roles[0].model_copy(
        update={"local_entity_id": second_id}
    )
    swapped_roles[1] = swapped_roles[1].model_copy(
        update={"local_entity_id": first_id}
    )
    role_swapped = l1_typed.model_copy(update={"roles": swapped_roles})
    assert _semantic_signature(
        l1_blueprint.expected_decision,
        l1_blueprint.untyped_candidate,
        l1_typed,
    ) != _semantic_signature(
        l1_blueprint.expected_decision,
        l1_blueprint.untyped_candidate,
        role_swapped,
    )

    l2_blueprint = next(
        item
        for item in bundle.l2.blueprints
        if item.expected_typed_candidate is not None
    )
    l2_typed = l2_blueprint.expected_typed_candidate
    assert l2_typed is not None
    changed_closure = l2_typed.model_copy(
        update={
            "closure": l2_typed.closure.model_copy(
                update={"pattern": "ordered_sequence"}
            )
        }
    )
    assert _semantic_signature(
        l2_blueprint.expected_decision,
        l2_blueprint.untyped_candidate,
        l2_typed,
    ) != _semantic_signature(
        l2_blueprint.expected_decision,
        l2_blueprint.untyped_candidate,
        changed_closure,
    )


def test_build_rejects_invalid_evidence_offsets_and_incomplete_l2_closure(
) -> None:
    bundle = _build()
    l1_blueprints = list(bundle.l1.blueprints)
    untyped = l1_blueprints[0].untyped_candidate.model_copy(
        update={
            "evidence": [
                l1_blueprints[0].untyped_candidate.evidence[0].model_copy(
                    update={"end": 0}
                )
            ]
        }
    )
    l1_blueprints[0] = l1_blueprints[0].model_copy(
        update={"untyped_candidate": untyped}
    )
    invalid_l1 = bundle.model_copy(
        update={"l1": bundle.l1.model_copy(update={"blueprints": tuple(l1_blueprints)})}
    )
    with pytest.raises(ValueError, match="evidence.*offset"):
        validate_fresh_v2_authoring_bundle(invalid_l1, PREREGISTRATION)

    l2_blueprints = list(bundle.l2.blueprints)
    expected = l2_blueprints[0].expected_typed_candidate
    assert expected is not None
    l2_blueprints[0] = l2_blueprints[0].model_copy(
        update={
            "expected_typed_candidate": expected.model_copy(
                update={
                    "closure": expected.closure.model_copy(
                        update={"required_support_refs": []}
                    )
                }
            )
        }
    )
    invalid_l2 = bundle.model_copy(
        update={"l2": bundle.l2.model_copy(update={"blueprints": tuple(l2_blueprints)})}
    )
    with pytest.raises(ValueError, match="closure"):
        validate_fresh_v2_authoring_bundle(invalid_l2, PREREGISTRATION)


def test_freeze_and_validate_receipt_are_strict_and_leave_hidden_root_absent(
    tmp_path: Path,
) -> None:
    preregistration_path, evaluation_root = _receipt_paths(tmp_path)

    receipt = freeze_fresh_v2_authoring_receipt(
        preregistration_path,
        evaluation_root,
        WORKSPACE,
        RECEIPT_TIME,
    )
    receipt_path = preregistration_path.parent / "authoring-implementation-receipt.json"
    assert receipt == load_json(receipt_path)
    assert receipt["schema_version"] == "typed-extractor-fresh-v2-authoring-receipt-v1"
    assert receipt["formal_evaluation_root"] == str(evaluation_root.resolve())
    assert receipt["receipt_time"] == RECEIPT_TIME
    assert receipt["model_request_count"] == 0
    assert receipt["automatic_write_counts"] == {
        "aggregate": 0,
        "closure": 0,
        "identity": 0,
        "l1": 0,
        "l2": 0,
        "membership": 0,
        "revision": 0,
        "snapshot": 0,
        "source_revision": 0,
    }
    assert receipt_path.stat().st_mode & 0o777 == 0o444
    assert not evaluation_root.exists()
    assert validate_fresh_v2_authoring_receipt(
        preregistration_path, evaluation_root, WORKSPACE
    ) == receipt


@pytest.mark.parametrize(
    ("receipt_time", "match"),
    [
        ("2026-07-28T24:00:00Z", "valid UTC timestamp"),
        ("2026-07-28T14:09:00+08:00", "valid UTC timestamp"),
    ],
)
def test_freeze_rejects_impossible_or_non_utc_receipt_label(
    tmp_path: Path,
    receipt_time: str,
    match: str,
) -> None:
    preregistration_path, evaluation_root = _receipt_paths(tmp_path)

    with pytest.raises(ValidationError, match=match):
        freeze_fresh_v2_authoring_receipt(
            preregistration_path, evaluation_root, WORKSPACE, receipt_time
        )
    assert not evaluation_root.exists()


@pytest.mark.parametrize(
    "drift_target",
    ["preregistration", "module", "test"],
)
def test_receipt_validation_rejects_preregistration_and_code_hash_drift(
    tmp_path: Path,
    drift_target: str,
) -> None:
    preregistration_path, evaluation_root = _receipt_paths(tmp_path)
    freeze_fresh_v2_authoring_receipt(
        preregistration_path, evaluation_root, WORKSPACE, RECEIPT_TIME
    )
    receipt_path = preregistration_path.parent / "authoring-implementation-receipt.json"
    receipt = load_json(receipt_path)
    receipt_path.chmod(0o644)
    if drift_target == "preregistration":
        receipt["preregistration_sha256"] = "0" * 64
    else:
        receipt["code_sha256"][drift_target] = "f" * 64
    receipt_path.write_text(
        json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    receipt_path.chmod(0o444)

    with pytest.raises(ValueError, match="drift"):
        validate_fresh_v2_authoring_receipt(
            preregistration_path, evaluation_root, WORKSPACE
        )


@pytest.mark.parametrize("path_kind", ["evaluation", "model_run"])
def test_receipt_freeze_rejects_premature_evaluation_or_model_run_paths(
    tmp_path: Path,
    path_kind: str,
) -> None:
    preregistration_path, evaluation_root = _receipt_paths(tmp_path)
    if path_kind == "evaluation":
        evaluation_root.mkdir()
    else:
        (evaluation_root / "l1" / "model-runs").mkdir(parents=True)

    with pytest.raises(ValueError, match="must be absent"):
        freeze_fresh_v2_authoring_receipt(
            preregistration_path, evaluation_root, WORKSPACE, RECEIPT_TIME
        )


def test_receipt_rejects_coercive_types_and_existing_different_receipt(
    tmp_path: Path,
) -> None:
    preregistration_path, evaluation_root = _receipt_paths(tmp_path)
    freeze_fresh_v2_authoring_receipt(
        preregistration_path, evaluation_root, WORKSPACE, RECEIPT_TIME
    )
    receipt_path = preregistration_path.parent / "authoring-implementation-receipt.json"
    receipt = load_json(receipt_path)
    receipt_path.chmod(0o644)
    receipt["model_request_count"] = "0"
    receipt_path.write_text(
        json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    receipt_path.chmod(0o444)

    with pytest.raises(ValidationError):
        validate_fresh_v2_authoring_receipt(
            preregistration_path, evaluation_root, WORKSPACE
        )
    with pytest.raises(ValueError, match="receipt.*differs"):
        freeze_fresh_v2_authoring_receipt(
            preregistration_path, evaluation_root, WORKSPACE, RECEIPT_TIME
        )


def test_freeze_validate_and_select_supersession_receipt(
    tmp_path: Path,
) -> None:
    preregistration_path, evaluation_root, predecessor = _supersession_paths(
        tmp_path
    )
    predecessor_before = predecessor.read_bytes()

    receipt = freeze_fresh_v2_authoring_supersession_receipt(
        preregistration_path,
        evaluation_root,
        WORKSPACE,
        RECEIPT_TIME,
    )
    receipt_path = preregistration_path.parent / (
        "authoring-implementation-receipt-v2.json"
    )

    assert receipt["schema_version"] == (
        "typed-extractor-fresh-v2-authoring-receipt-v2"
    )
    assert receipt["supersedes_receipt_sha256"] == ORIGINAL_RECEIPT_SHA256
    assert receipt["supersession_reason"] == (
        "post_freeze_review_primary_literal_binding_repair"
    )
    assert receipt_path.stat().st_mode & 0o777 == 0o444
    assert predecessor.read_bytes() == predecessor_before
    assert not evaluation_root.exists()
    assert validate_fresh_v2_authoring_supersession_receipt(
        preregistration_path, evaluation_root, WORKSPACE
    ) == receipt
    assert validate_fresh_v2_active_authoring_receipt(
        preregistration_path, evaluation_root, WORKSPACE
    ) == receipt
    assert freeze_fresh_v2_authoring_supersession_receipt(
        preregistration_path,
        evaluation_root,
        WORKSPACE,
        RECEIPT_TIME,
    ) == receipt


@pytest.mark.parametrize(
    "predecessor_state", ["missing", "writable", "wrong_mode", "modified"]
)
def test_supersession_rejects_invalid_predecessor(
    tmp_path: Path,
    predecessor_state: str,
) -> None:
    preregistration_path, evaluation_root, predecessor = _supersession_paths(
        tmp_path
    )
    if predecessor_state == "missing":
        predecessor.unlink()
    elif predecessor_state == "writable":
        predecessor.chmod(0o644)
    elif predecessor_state == "wrong_mode":
        predecessor.chmod(0o400)
    else:
        predecessor.chmod(0o644)
        predecessor.write_bytes(predecessor.read_bytes() + b"\n")
        predecessor.chmod(0o444)

    with pytest.raises(ValueError, match="superseded authoring receipt"):
        freeze_fresh_v2_authoring_supersession_receipt(
            preregistration_path,
            evaluation_root,
            WORKSPACE,
            RECEIPT_TIME,
        )


@pytest.mark.parametrize(
    ("section", "field"),
    [
        ("code_sha256", "module"),
        ("code_sha256", "test"),
        ("blueprint_manifest_sha256", "l2"),
    ],
)
def test_supersession_validation_rejects_current_binding_drift(
    tmp_path: Path,
    section: str,
    field: str,
) -> None:
    preregistration_path, evaluation_root, _ = _supersession_paths(tmp_path)
    freeze_fresh_v2_authoring_supersession_receipt(
        preregistration_path,
        evaluation_root,
        WORKSPACE,
        RECEIPT_TIME,
    )
    receipt_path = preregistration_path.parent / (
        "authoring-implementation-receipt-v2.json"
    )
    receipt = load_json(receipt_path)
    receipt_path.chmod(0o644)
    receipt[section][field] = "f" * 64
    receipt_path.write_text(
        json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    receipt_path.chmod(0o444)

    with pytest.raises(ValueError, match="supersession receipt drift"):
        validate_fresh_v2_authoring_supersession_receipt(
            preregistration_path, evaluation_root, WORKSPACE
        )


@pytest.mark.parametrize("path_kind", ["evaluation", "model_run"])
def test_supersession_rejects_premature_formal_paths(
    tmp_path: Path,
    path_kind: str,
) -> None:
    preregistration_path, evaluation_root, _ = _supersession_paths(tmp_path)
    if path_kind == "evaluation":
        evaluation_root.mkdir()
    else:
        (evaluation_root / "l2" / "model-runs").mkdir(parents=True)

    with pytest.raises(ValueError, match="must be absent"):
        freeze_fresh_v2_authoring_supersession_receipt(
            preregistration_path,
            evaluation_root,
            WORKSPACE,
            RECEIPT_TIME,
        )


def test_active_receipt_fails_closed_when_only_drifted_v1_exists(
    tmp_path: Path,
) -> None:
    preregistration_path, evaluation_root, _ = _supersession_paths(tmp_path)

    with pytest.raises(ValueError, match="authoring receipt drift"):
        validate_fresh_v2_active_authoring_receipt(
            preregistration_path, evaluation_root, WORKSPACE
        )


@pytest.mark.parametrize(
    "drift", ["writable", "wrong_mode", "coercive", "different"]
)
def test_supersession_receipt_rejects_invalid_existing_artifact(
    tmp_path: Path,
    drift: str,
) -> None:
    preregistration_path, evaluation_root, _ = _supersession_paths(tmp_path)
    freeze_fresh_v2_authoring_supersession_receipt(
        preregistration_path,
        evaluation_root,
        WORKSPACE,
        RECEIPT_TIME,
    )
    receipt_path = preregistration_path.parent / (
        "authoring-implementation-receipt-v2.json"
    )
    if drift in {"writable", "wrong_mode"}:
        receipt_path.chmod(0o644 if drift == "writable" else 0o400)
        with pytest.raises(ValueError, match="must have mode 0444"):
            validate_fresh_v2_authoring_supersession_receipt(
                preregistration_path, evaluation_root, WORKSPACE
            )
        return

    receipt = load_json(receipt_path)
    receipt_path.chmod(0o644)
    if drift == "coercive":
        receipt["model_request_count"] = "0"
    else:
        receipt["receipt_time"] = "2026-07-28T14:09:01Z"
    receipt_path.write_text(
        json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    receipt_path.chmod(0o444)

    if drift == "coercive":
        with pytest.raises(ValidationError):
            validate_fresh_v2_authoring_supersession_receipt(
                preregistration_path, evaluation_root, WORKSPACE
            )
    else:
        with pytest.raises(ValueError, match="already exists and differs"):
            freeze_fresh_v2_authoring_supersession_receipt(
                preregistration_path,
                evaluation_root,
                WORKSPACE,
                RECEIPT_TIME,
            )
