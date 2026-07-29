from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.natural_memory_benchmark.authoritative_memory import (
    EvidenceSpanV2,
    canonical_sha256,
    make_raw_artifact_revision,
    make_source_record_revision,
)
from tools.natural_memory_benchmark.l1_admission import (
    AdmissionContext,
    AdmissionPolicy,
    CanonicalIdentityMembership,
    CanonicalEntityBinding,
    IdentitySnapshotAuthority,
    SourceEpistemicBinding,
    admit_linked_l1,
    make_identity_snapshot_authority,
    run_dev_ontology_linking_assessment,
)
from tools.natural_memory_benchmark.l1_ontology_linking import (
    LinkedL1Candidate,
    build_diagnostic_ontology_registry,
    link_l1_candidate,
)
from tools.natural_memory_benchmark.typed_extractor_l1 import (
    TypedDerivationProvenance,
    TypedEvidenceBinding,
    TypedL1Candidate,
    TypedLifecycleBinding,
    TypedLocalEntity,
    TypedOperationProvenance,
    TypedPolarity,
    TypedPredicate,
    TypedRoleBinding,
    TypedTimeBinding,
)


def _source_fixture(tmp_path: Path, text: str) -> tuple[object, object, EvidenceSpanV2]:
    raw_path = tmp_path / "source.json"
    raw_path.write_text(text, encoding="utf-8")
    raw = make_raw_artifact_revision(
        source_id="l1-admission-test",
        frozen_identity="l1-admission-test-v1",
        official_url="https://example.invalid/l1-admission-test",
        local_path=str(raw_path),
        reader="json",
        size_bytes=raw_path.stat().st_size,
        content_sha256=__import__("hashlib").sha256(raw_path.read_bytes()).hexdigest(),
    )
    source = make_source_record_revision(
        source_record_id="record:l1-admission-test",
        revision_number=1,
        previous_revision_id=None,
        artifact_revision_id=raw.artifact_revision_id,
        source_ref="record:l1-admission-test",
        turn_id="turn:l1-admission-test",
        session_id="session:l1-admission-test",
        record_kind="message",
        text=text,
        resolver_id="test-resolver",
        resolver_version="1",
        transaction_time="2026-07-29T00:00:00Z",
    )
    evidence = EvidenceSpanV2(
        evidence_id="evidence:l1-admission-test",
        source_revision_id=source.source_revision_id,
        turn_id=source.turn_id,
        session_id=source.session_id,
        char_start=0,
        char_end=len(text),
        text=text,
        quote_sha256=__import__("hashlib").sha256(text.encode("utf-8")).hexdigest(),
    )
    return raw, source, evidence


def _candidate(
    *,
    text: str,
    predicate_surface: str,
    predicate_sense: str,
    canonical_operator: str,
    entity_surface: str,
    modality: str = "actual",
    evidence_id: str = "evidence:l1-admission-test",
    speaker: str = "user",
    lifecycle: TypedLifecycleBinding | None = None,
) -> TypedL1Candidate:
    return TypedL1Candidate(
        kind="preference" if predicate_surface == "prefer" else "event",
        predicate=TypedPredicate(
            surface=predicate_surface,
            sense=predicate_sense,
            canonical_operator=canonical_operator,
        ),
        local_entities=[
            TypedLocalEntity(local_entity_id="entity-01", surface=entity_surface)
        ],
        roles=[
            TypedRoleBinding(
                role="ARG1",
                role_name="theme",
                local_entity_id="entity-01",
            )
        ],
        modality=modality,
        polarity="positive",
        time=TypedTimeBinding(),
        derivation=TypedDerivationProvenance(
            method="explicit",
            evidence_ids=[evidence_id],
        ),
        evidence_bindings=[
            TypedEvidenceBinding(evidence_id=evidence_id, speaker=speaker)
        ],
        lifecycle=lifecycle or TypedLifecycleBinding(lifecycle="active"),
        operation_provenance=TypedOperationProvenance(),
    )


def _link(
    tmp_path: Path,
    *,
    text: str,
    predicate_surface: str = "prefer",
    predicate_sense: str = "preference_theme",
    canonical_operator: str = "prefer",
    entity_surface: str = "coffee",
    modality: str = "actual",
    identity_binding: CanonicalEntityBinding | None = None,
    speaker: str = "user",
    lifecycle: TypedLifecycleBinding | None = None,
):
    raw, source, evidence = _source_fixture(tmp_path, text)
    candidate = _candidate(
        text=text,
        predicate_surface=predicate_surface,
        predicate_sense=predicate_sense,
        canonical_operator=canonical_operator,
        entity_surface=entity_surface,
        modality=modality,
        speaker=speaker,
        lifecycle=lifecycle,
    )
    registry = build_diagnostic_ontology_registry()
    linked = link_l1_candidate(
        candidate,
        registry=registry,
        evidence_spans=[evidence],
        canonical_entity_bindings=([] if identity_binding is None else [identity_binding]),
    )
    return linked, registry, raw, source, evidence


def _context(
    *,
    raw: object,
    source: object,
    policy: AdmissionPolicy | None = None,
    identity_bindings: list[CanonicalEntityBinding] | None = None,
    identity_snapshot_authorities: list[IdentitySnapshotAuthority] | None = None,
    current_identity_snapshot_ids: list[str] | None = None,
    source_status: str = "user_reported",
    source_speaker: str = "user",
    transaction_time: str | None = "2026-07-29T00:00:00Z",
    known_lifecycle_candidate_refs: list[str] | None = None,
) -> AdmissionContext:
    return AdmissionContext(
        raw_artifacts=[raw],
        source_revisions=[source],
        identity_bindings=identity_bindings or [],
        identity_snapshot_authorities=identity_snapshot_authorities or [],
        current_identity_snapshot_ids=current_identity_snapshot_ids or [],
        identity_registry_revision="identity-r1",
        identity_registry_hash="2" * 64,
        transaction_time=transaction_time,
        source_epistemics=[
            SourceEpistemicBinding(
                source_revision_id=source.source_revision_id,
                source_status=source_status,
                speaker=source_speaker,
            )
        ],
        known_lifecycle_candidate_refs=known_lifecycle_candidate_refs or [],
        policy=policy
        or AdmissionPolicy(
            policy_id="policy-dev-v1",
            policy_version="1",
            allow_modalities=["actual"],
            allow_source_statuses=["user_reported"],
            require_transaction_time=True,
        ),
    )


def _identity_authority() -> IdentitySnapshotAuthority:
    return make_identity_snapshot_authority(
        snapshot_id="identity-snapshot:test",
        snapshot_revision="identity-snapshot-r1",
        identity_registry_revision="identity-r1",
        identity_registry_hash="2" * 64,
        memberships=[
            CanonicalIdentityMembership(
                canonical_entity_id="entity:cup-1",
                member_entity_ids=["entity:cup-1"],
                concept_type_ids=["memory:CoffeeBeverage"],
            )
        ],
        unresolved_entity_ids=[],
    )


def _rehashed_linked(
    linked: LinkedL1Candidate, *, entity_links: list[object]
) -> LinkedL1Candidate:
    payload = linked.model_dump(mode="json")
    payload["entity_links"] = [
        item.model_dump(mode="json") for item in entity_links
    ]
    payload.pop("linked_candidate_hash")
    payload["linked_candidate_hash"] = canonical_sha256(payload)
    return LinkedL1Candidate.model_validate(payload)


def test_admission_accepts_complete_evidence_closure_for_category_preference(tmp_path):
    linked, registry, raw, source, evidence = _link(
        tmp_path,
        text="I prefer coffee.",
    )
    decision = admit_linked_l1(
        linked,
        registry,
        _context(raw=raw, source=source),
    )

    assert decision.status == "accept"
    assert decision.reason_codes == []
    assert decision.evidence_bindings == [evidence.evidence_id]
    assert decision.proposed_action.action == "create"
    assert decision.proposed_action.automatic_write is False


def test_admission_rejects_tampered_quote_hash_and_source_slice(tmp_path):
    linked, registry, raw, source, evidence = _link(
        tmp_path,
        text="I prefer coffee.",
    )
    tampered = evidence.model_copy(update={"text": "I prefer tea."})
    tampered_linked = linked.model_copy(update={"evidence_spans": [tampered]})

    decision = admit_linked_l1(
        tampered_linked,
        registry,
        _context(raw=raw, source=source),
    )

    assert decision.status == "reject"
    assert "evidence_quote_hash_mismatch" in decision.reason_codes
    assert decision.proposed_action.action == "none"
    assert decision.proposed_action.automatic_write is False


def test_admission_rejects_predicate_role_type_incompatibility(tmp_path):
    linked, registry, raw, source, _ = _link(
        tmp_path,
        text="I prefer coffee.",
        predicate_surface="prefer",
        predicate_sense="preference_theme",
        canonical_operator="prefer",
        entity_surface="coffee",
    )
    entity_link = linked.entity_links[0]
    incompatible_concept = entity_link.concept.model_copy(
        update={
            "candidate_concept_ids": ["memory:DairyIngredient"],
            "selected_concept_ids": ["memory:DairyIngredient"],
        }
    )
    linked = linked.model_copy(
        update={
            "entity_links": [
                entity_link.model_copy(
                    update={
                        "concept": incompatible_concept,
                        "selected_concept_ids": ["memory:DairyIngredient"],
                    }
                )
            ]
        }
    )
    decision = admit_linked_l1(
        linked,
        registry,
        _context(raw=raw, source=source),
    )

    assert decision.status == "reject"
    assert "predicate_role_type_incompatible" in decision.reason_codes
    assert decision.proposed_action.automatic_write is False


@pytest.mark.parametrize(
    ("entity_surface", "modality", "expected_reason"),
    [
        ("coffee", "hypothetical", "hypothetical_modality"),
        ("unknown beverage", "actual", "ontology_extension_required"),
        ("this cup of coffee", "actual", "identity_unresolved"),
    ],
)
def test_admission_abstains_for_incomplete_or_unresolved_inputs(
    tmp_path,
    entity_surface,
    modality,
    expected_reason,
):
    linked, registry, raw, source, _ = _link(
        tmp_path,
        text="I prefer coffee.",
        entity_surface=entity_surface,
        modality=modality,
    )
    decision = admit_linked_l1(
        linked,
        registry,
        _context(raw=raw, source=source),
    )

    assert decision.status == "abstain"
    assert expected_reason in decision.reason_codes
    assert decision.proposed_action.action == "none"
    assert decision.proposed_action.automatic_write is False


def test_admission_accepts_resolved_individual_with_fresh_identity_binding(tmp_path):
    authority = _identity_authority()
    identity_binding = CanonicalEntityBinding(
        local_entity_id="entity-01",
        canonical_entity_id="entity:cup-1",
        identity_snapshot_id=authority.snapshot_id,
        identity_snapshot_hash=authority.snapshot_hash,
        identity_registry_revision="identity-r1",
        identity_status="resolved",
        concept_type_ids=["memory:CoffeeBeverage", "memory:Beverage"],
    )
    linked, registry, raw, source, _ = _link(
        tmp_path,
        text="I drank this cup of coffee.",
        predicate_surface="drink",
        predicate_sense="consume_beverage",
        canonical_operator="drink",
        entity_surface="this cup of coffee",
        identity_binding=identity_binding,
    )
    binding = linked.entity_links[0].canonical_entity_binding
    decision = admit_linked_l1(
        linked,
        registry,
        _context(
            raw=raw,
            source=source,
            identity_bindings=[binding],
            identity_snapshot_authorities=[authority],
            current_identity_snapshot_ids=[authority.snapshot_id],
        ),
    )

    assert decision.status == "accept"
    assert decision.reason_codes == []
    assert decision.proposed_action.action == "create"
    assert decision.proposed_action.automatic_write is False


def test_admission_rejects_agent_generated_fact_even_with_valid_evidence(tmp_path):
    linked, registry, raw, source, _ = _link(
        tmp_path,
        text="I prefer coffee.",
    )
    decision = admit_linked_l1(
        linked,
        registry,
        _context(raw=raw, source=source, source_status="agent_generated"),
    )

    assert decision.status == "reject"
    assert "source_status_not_authorized" in decision.reason_codes
    assert decision.proposed_action.automatic_write is False


def test_admission_replay_is_deterministic_and_never_writes(tmp_path):
    linked, registry, raw, source, _ = _link(
        tmp_path,
        text="I prefer coffee.",
    )
    context = _context(raw=raw, source=source)
    first = admit_linked_l1(linked, registry, context)
    second = admit_linked_l1(linked, registry, context)

    assert first == second
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.proposed_action.automatic_write is False
    assert first.proposed_action.action in {"create", "none"}
    assert first.automatic_write_counts == {
        "l1": 0,
        "l2": 0,
        "identity": 0,
        "membership": 0,
        "closure": 0,
        "revision": 0,
        "snapshot": 0,
        "aggregate": 0,
    }


@pytest.mark.parametrize(
    "selected_concepts",
    [
        ["memory:TeaBeverage"],
        ["memory:CoffeeBeverage", "memory:TeaBeverage"],
    ],
)
def test_admission_rejects_self_consistent_rehashed_link_substitution(
    tmp_path, selected_concepts
):
    linked, registry, raw, source, _ = _link(
        tmp_path,
        text="I prefer coffee.",
    )
    entity_link = linked.entity_links[0]
    altered_concept = entity_link.concept.model_copy(
        update={
            "candidate_concept_ids": selected_concepts,
            "selected_concept_ids": selected_concepts,
            "advisory_mappings": [],
        }
    )
    altered_entity = entity_link.model_copy(
        update={
            "concept": altered_concept,
            "selected_concept_ids": selected_concepts,
        }
    )
    altered = _rehashed_linked(linked, entity_links=[altered_entity])

    decision = admit_linked_l1(
        altered, registry, _context(raw=raw, source=source)
    )

    assert decision.status == "reject"
    assert "deterministic_link_replay_mismatch" in decision.reason_codes


def test_admission_abstains_when_individual_has_no_snapshot_authority(tmp_path):
    binding = CanonicalEntityBinding(
        local_entity_id="entity-01",
        canonical_entity_id="entity:cup-1",
        identity_snapshot_id="identity-snapshot:invented",
        identity_snapshot_hash="0" * 64,
        identity_registry_revision="identity-r1",
        identity_status="resolved",
        concept_type_ids=["memory:CoffeeBeverage"],
    )
    linked, registry, raw, source, _ = _link(
        tmp_path,
        text="I drank this cup of coffee.",
        predicate_surface="drink",
        predicate_sense="consume_beverage",
        canonical_operator="drink",
        entity_surface="this cup of coffee",
        identity_binding=binding,
    )

    decision = admit_linked_l1(
        linked,
        registry,
        _context(raw=raw, source=source, identity_bindings=[binding]),
    )

    assert decision.status == "abstain"
    assert "identity_authority_unavailable" in decision.reason_codes


@pytest.mark.parametrize(
    ("speaker", "source_status"),
    [("assistant", "user_reported"), ("tool", "user_reported")],
)
def test_admission_rejects_speaker_epistemic_relabeling(
    tmp_path, speaker, source_status
):
    linked, registry, raw, source, _ = _link(
        tmp_path,
        text="I prefer coffee.",
        speaker=speaker,
    )
    policy = AdmissionPolicy(
        policy_id="policy-dev-v1",
        policy_version="1",
        allow_modalities=["actual"],
        allow_source_statuses=["user_reported", "agent_generated", "tool_observed"],
        require_transaction_time=True,
    )

    decision = admit_linked_l1(
        linked,
        registry,
        _context(
            raw=raw,
            source=source,
            policy=policy,
            source_status=source_status,
            source_speaker=speaker,
        ),
    )

    assert decision.status == "reject"
    assert "speaker_source_status_incompatible" in decision.reason_codes


def test_admission_rejects_tampered_raw_revision_identity(tmp_path):
    linked, registry, raw, source, _ = _link(
        tmp_path,
        text="I prefer coffee.",
    )
    tampered_raw = raw.model_copy(update={"content_sha256": "f" * 64})

    decision = admit_linked_l1(
        linked, registry, _context(raw=tampered_raw, source=source)
    )

    assert decision.status == "reject"
    assert "raw_artifact_revision_identity_mismatch" in decision.reason_codes


def test_admission_rejects_unreferenced_source_revision(tmp_path):
    linked, registry, raw, source, _ = _link(
        tmp_path,
        text="I prefer coffee.",
    )
    extra = make_source_record_revision(
        source_record_id="record:extra",
        revision_number=1,
        previous_revision_id=None,
        artifact_revision_id=raw.artifact_revision_id,
        source_ref="record:extra",
        turn_id="turn:extra",
        session_id=source.session_id,
        record_kind="message",
        text="extra",
        resolver_id="test-resolver",
        resolver_version="1",
        transaction_time="2026-07-29T00:00:00Z",
    )
    context = _context(raw=raw, source=source).model_copy(
        update={"source_revisions": [source, extra]}
    )

    decision = admit_linked_l1(linked, registry, context)

    assert decision.status == "reject"
    assert "unexpected_source_revision" in decision.reason_codes


def test_decision_hash_binds_full_policy_and_lifecycle_context(tmp_path):
    linked, registry, raw, source, _ = _link(
        tmp_path,
        text="I prefer coffee.",
    )
    narrow = AdmissionPolicy(
        policy_id="same-policy",
        policy_version="1",
        allow_modalities=["actual"],
        allow_source_statuses=["user_reported"],
    )
    broad = narrow.model_copy(
        update={
            "allow_source_statuses": ["user_reported", "tool_observed"]
        }
    )
    first = admit_linked_l1(
        linked, registry, _context(raw=raw, source=source, policy=narrow)
    )
    second = admit_linked_l1(
        linked,
        registry,
        _context(
            raw=raw,
            source=source,
            policy=broad,
            known_lifecycle_candidate_refs=["candidate:other"],
        ),
    )

    assert first.status == second.status == "accept"
    assert first.admission_context_hash != second.admission_context_hash
    assert first.decision_hash != second.decision_hash


@pytest.mark.parametrize(
    ("transaction_time", "expected_reason"),
    [
        ("not-a-time", "transaction_time_invalid"),
        ("2026-07-28T23:59:59Z", "transaction_time_precedes_source"),
    ],
)
def test_admission_rejects_invalid_transaction_time(
    tmp_path, transaction_time, expected_reason
):
    linked, registry, raw, source, _ = _link(
        tmp_path,
        text="I prefer coffee.",
    )

    decision = admit_linked_l1(
        linked,
        registry,
        _context(
            raw=raw, source=source, transaction_time=transaction_time
        ),
    )

    assert decision.status == "reject"
    assert expected_reason in decision.reason_codes


@pytest.mark.parametrize(
    "lifecycle",
    [
        TypedLifecycleBinding(lifecycle="superseded"),
        TypedLifecycleBinding(
            lifecycle="conflicted",
            conflicts_with_candidate_refs=[],
        ),
    ],
)
def test_admission_abstains_when_lifecycle_target_is_missing(tmp_path, lifecycle):
    linked, registry, raw, source, _ = _link(
        tmp_path,
        text="I prefer coffee.",
        lifecycle=lifecycle,
    )

    decision = admit_linked_l1(
        linked, registry, _context(raw=raw, source=source)
    )

    assert decision.status == "abstain"
    assert "lifecycle_target_missing" in decision.reason_codes


@pytest.mark.parametrize(
    "lifecycle",
    [
        TypedLifecycleBinding(
            lifecycle="superseded",
            replacement_candidate_ref="candidate:replacement",
        ),
        TypedLifecycleBinding(
            lifecycle="conflicted",
            conflicts_with_candidate_refs=["candidate:conflict"],
        ),
    ],
)
def test_admission_proposes_lifecycle_update_for_known_targets(tmp_path, lifecycle):
    linked, registry, raw, source, _ = _link(
        tmp_path,
        text="I prefer coffee.",
        lifecycle=lifecycle,
    )
    known = [
        reference
        for reference in [
            lifecycle.replacement_candidate_ref,
            *lifecycle.conflicts_with_candidate_refs,
        ]
        if reference is not None
    ]

    decision = admit_linked_l1(
        linked,
        registry,
        _context(
            raw=raw,
            source=source,
            known_lifecycle_candidate_refs=known,
        ),
    )

    assert decision.status == "accept"
    assert decision.proposed_action.action == "lifecycle_update"
    assert decision.proposed_action.target_candidate_refs == known
    assert decision.proposed_action.automatic_write is False


def test_dev_assessment_is_complete_immutable_and_replayable(tmp_path):
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first = run_dev_ontology_linking_assessment(first_root)
    second = run_dev_ontology_linking_assessment(second_root)

    expected_cases = {
        "prefer-coffee",
        "drink-coffee-cup",
        "drink-milk",
        "add-milk-to-coffee",
        "hypothetical-preference",
        "unknown-beverage",
        "same-surface-sense",
        "identity-unresolved",
    }
    assert set(first["cases"]) == expected_cases
    assert first["metrics"]["linking_exact_rate"] == 1.0
    assert first["metrics"]["hierarchy_consistency_rate"] == 1.0
    assert first["metrics"]["sense_accuracy"] == 1.0
    assert first["metrics"]["decision_exact_rate"] == 1.0
    assert first["metrics"]["abstention_precision"] == 1.0
    assert first["metrics"]["abstention_recall"] == 1.0
    assert first["metrics"]["abstention_f1"] == 1.0
    assert first["metrics"]["critical_false_admission_count"] == 0
    assert first["metrics"]["evidence_exact_rate"] == 1.0
    assert first["automatic_write_counts"] == {
        "l1": 0,
        "l2": 0,
        "identity": 0,
        "membership": 0,
        "closure": 0,
        "revision": 0,
        "snapshot": 0,
        "aggregate": 0,
    }

    for name in ("assessment.json", "assessment-report.md", "manifest.json"):
        assert (first_root / name).read_bytes() == (second_root / name).read_bytes()
    assert json.loads((first_root / "assessment.json").read_text()) == first
