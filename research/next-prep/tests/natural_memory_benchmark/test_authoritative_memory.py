from __future__ import annotations

from tools.natural_memory_benchmark.authoritative_memory import (
    AuthoritativeQueryPlan,
    ClaimClosureContext,
    ClosureEvaluationInputs,
    ClosureSlotSpec,
    ExactTimeConstraint,
    L1MemoryUnitV2,
    L2MemoryUnitV2,
    L2StructuredClaim,
    MemoryRepresentationBundleV3,
    ProducerIdentity,
    QueryClosureContext,
    SourceBindingV2,
    assess_authoritative_bundle_integrity,
    evaluate_closure_spec,
    execute_authoritative_query,
    is_closure_evaluation_fresh,
    make_closure_spec,
    make_evidence_span,
    make_memory_unit_revision,
    make_raw_artifact_revision,
    make_source_record_revision,
)
from tools.natural_memory_benchmark.representation_contract import (
    REQUIRED_MEMORY_CAPABILITIES,
    CapabilityDeclaration,
    RepresentationProfile,
)
from tools.natural_memory_benchmark.semantic_ir import LinkBinding, Predicate, RoleBinding, TimeBinding


def _profile() -> RepresentationProfile:
    return RepresentationProfile(
        representation_id="authoritative-test",
        family="semantic_ir",
        format_version="memory-representation-bundle-v3",
        role="authoritative_candidate",
        capabilities=[
            CapabilityDeclaration(capability=name, support_mode="native", location="test")
            for name in REQUIRED_MEMORY_CAPABILITIES
        ],
    )


def _artifact():
    return make_raw_artifact_revision(
        source_id="source-a",
        frozen_identity="commit|hash",
        official_url="https://example.test/source-a.json",
        local_path="artifacts/raw/source-a.json",
        reader="json",
        size_bytes=12,
        content_sha256="a" * 64,
    )


def _source_record(text: str = "User led Project Alpha.", *, revision_number: int = 1, previous=None):
    return make_source_record_revision(
        source_record_id="source-record-a",
        revision_number=revision_number,
        previous_revision_id=previous,
        artifact_revision_id=_artifact().artifact_revision_id,
        source_ref="question_id=q1;session_id=s1",
        turn_id="question_id=q1;session_id=s1",
        session_id="s1",
        record_kind="normalized_session",
        text=text,
        resolver_id="test-resolver",
        resolver_version="1",
        transaction_time="2026-07-27T00:00:00Z",
        metadata={"source_id": "source-a"},
    )


def _l1(
    unit_id: str = "l1-led-alpha",
    *,
    entity_id: str = "project_alpha",
    modality: str = "actual",
    polarity: str = "positive",
    lifecycle: str = "active",
    links: LinkBinding | None = None,
    source_record=None,
) -> L1MemoryUnitV2:
    source_record = source_record or _source_record()
    span = make_evidence_span(
        evidence_id=f"E-{unit_id}",
        source_revision=source_record,
        turn_id=source_record.turn_id,
        session_id=source_record.session_id,
        char_start=0,
        char_end=len(source_record.text),
        text=source_record.text,
    )
    return L1MemoryUnitV2(
        unit_id=unit_id,
        kind="event",
        predicate=Predicate(surface="led", sense="lead/manage", canonical_operator="led_by"),
        roles=[
            RoleBinding(role="ARG0", entity_id="user", role_name="leader"),
            RoleBinding(role="ARG1", entity_id=entity_id, role_name="project"),
        ],
        modality=modality,
        polarity=polarity,
        time=TimeBinding(
            event_time="2025-01-01",
            valid_time="2025",
            transaction_time="2026-07-27T00:00:00Z",
        ),
        source=SourceBindingV2(
            speaker="user",
            source_status="user_reported",
            evidence_spans=[span],
        ),
        lifecycle=lifecycle,
        links=links or LinkBinding(),
    )


def _producer() -> ProducerIdentity:
    return ProducerIdentity(
        workflow_run_id="run-test",
        producer_id="authoritative-test-builder",
        producer_version="1",
    )


def _l2(source_unit: L1MemoryUnitV2, *, structured: bool = True) -> L2MemoryUnitV2:
    claims = []
    if structured:
        claims = [
            L2StructuredClaim(
                claim_id="claim-led-projects",
                predicate=Predicate(surface="led projects", sense="lead/manage", canonical_operator="led_by"),
                roles=[RoleBinding(role="ARG0", entity_id="user", role_name="leader")],
                modality="actual",
                polarity="positive",
                time=TimeBinding(event_time="2025-01-01", valid_time="2025"),
                supporting_l1_units=[source_unit.unit_id],
            )
        ]
    span = source_unit.source.evidence_spans[0]
    return L2MemoryUnitV2(
        unit_id="l2-led-projects",
        kind="project",
        abstracts=[source_unit.unit_id],
        summary="The user led projects.",
        display_assertions=["count(led_projects_by_user)=2"],
        structured_claims=claims,
        closure_id="closure-led-projects-claim",
        closure_spec_revision=1,
        closure_evaluation_id="pending",
        lifecycle="candidate",
        source_l1_units=[source_unit.unit_id],
        source_turns=[span.turn_id],
        source_sessions=[span.session_id],
    )


def _query(**updates) -> AuthoritativeQueryPlan:
    values = {
        "query_id": "query-led-projects",
        "intent": "multi_evidence",
        "target_level": "both",
        "predicate_sense": "lead/manage",
        "canonical_operator": "led_by",
        "role_constraints": [RoleBinding(role="ARG0", entity_id="user", role_name="leader")],
        "answer_kind": "count",
        "closure_id": "closure-led-projects-query",
        "closure_spec_revision": 1,
    }
    values.update(updates)
    return AuthoritativeQueryPlan(**values)


def _bundle(*, structured_l2: bool = True) -> MemoryRepresentationBundleV3:
    artifact = _artifact()
    source_record = _source_record()
    l1 = _l1(source_record=source_record)
    l2 = _l2(l1, structured=structured_l2)
    l1_revision = make_memory_unit_revision(
        payload=l1,
        revision_number=1,
        previous_revision_id=None,
        revision_kind="create",
        transaction_time="2026-07-27T00:00:00Z",
        source_revision_ids=[source_record.source_revision_id],
        derived_from_revision_ids=[],
        producer=_producer(),
    )
    claim_spec = make_closure_spec(
        closure_id="closure-led-projects-claim",
        revision=1,
        target_id="claim-led-projects",
        pattern="multi_evidence_set",
        slots=[
            ClosureSlotSpec(
                slot_id="slot-led-project",
                role="evidence",
                required=True,
                bound_unit_id=l1.unit_id,
                fallback_class="blocked",
            )
        ],
    )
    claim_inputs = ClosureEvaluationInputs(
        evaluated_bundle_id="bundle-v3-test",
        context=ClaimClosureContext(
            l2_unit_id=l2.unit_id,
            claim_id=l2.structured_claims[0].claim_id if l2.structured_claims else "display-only",
            claim_hash=l2.structured_claims[0].semantic_hash if l2.structured_claims else "0" * 64,
            support_unit_ids=[l1.unit_id] if l2.structured_claims else [],
            support_scope=[l1.unit_id],
        ),
        current_revision_ids={l1.unit_id: l1_revision.revision_id},
        unit_revisions=[l1_revision],
        source_revisions=[source_record],
        evaluator_id="closure-evaluator",
        evaluator_version="1",
        policy_version="1",
    )
    claim_evaluation = evaluate_closure_spec(claim_spec, claim_inputs)
    l2 = l2.model_copy(
        update={
            "closure_evaluation_id": claim_evaluation.evaluation_id,
            "lifecycle": "active" if structured_l2 else "candidate",
        }
    )
    l2_revision = make_memory_unit_revision(
        payload=l2,
        revision_number=1,
        previous_revision_id=None,
        revision_kind="create",
        transaction_time="2026-07-27T00:00:00Z",
        source_revision_ids=[source_record.source_revision_id],
        derived_from_revision_ids=[l1_revision.revision_id],
        producer=_producer(),
    )
    plan = _query()
    query_spec = make_closure_spec(
        closure_id="closure-led-projects-query",
        revision=1,
        target_id=plan.query_id,
        pattern="multi_evidence_set",
        slots=[
            ClosureSlotSpec(
                slot_id="slot-led-project-query",
                role="evidence",
                required=True,
                bound_unit_id=l1.unit_id,
                fallback_class="blocked",
            )
        ],
    )
    query_inputs = ClosureEvaluationInputs(
        evaluated_bundle_id="bundle-v3-test",
        context=QueryClosureContext(
            query_plan=plan,
            query_scope=[l1.unit_id, l2.unit_id],
            available_unit_ids=[l1.unit_id, l2.unit_id],
        ),
        current_revision_ids={l1.unit_id: l1_revision.revision_id, l2.unit_id: l2_revision.revision_id},
        unit_revisions=[l1_revision, l2_revision],
        source_revisions=[source_record],
        evaluator_id="closure-evaluator",
        evaluator_version="1",
        policy_version="1",
    )
    query_evaluation = evaluate_closure_spec(query_spec, query_inputs)
    return MemoryRepresentationBundleV3(
        bundle_id="bundle-v3-test",
        profile=_profile(),
        raw_artifact_revisions=[artifact],
        source_record_revisions=[source_record],
        unit_revisions=[l1_revision, l2_revision],
        current_revision_ids={l1.unit_id: l1_revision.revision_id, l2.unit_id: l2_revision.revision_id},
        l1_units=[l1],
        l2_units=[l2],
        closure_specs=[claim_spec, query_spec],
        closure_evaluations=[claim_evaluation, query_evaluation],
        query_plans=[plan],
        query_unit_scopes={plan.query_id: [l1.unit_id, l2.unit_id]},
        metadata={
            "scope": "test",
            "closure_evaluator_id": "closure-evaluator",
            "closure_evaluator_version": "1",
            "closure_policy_version": "1",
        },
    )


def _l1_only_bundle(
    source_bundle: MemoryRepresentationBundleV3,
    *,
    revisions,
    current_revision_id: str,
    current_view: L1MemoryUnitV2,
) -> MemoryRepresentationBundleV3:
    return MemoryRepresentationBundleV3(
        bundle_id="bundle-v3-ledger-only",
        profile=source_bundle.profile,
        raw_artifact_revisions=source_bundle.raw_artifact_revisions,
        source_record_revisions=source_bundle.source_record_revisions,
        unit_revisions=revisions,
        current_revision_ids={current_view.unit_id: current_revision_id},
        l1_units=[current_view],
        l2_units=[],
        closure_specs=[],
        closure_evaluations=[],
        query_plans=[],
        query_unit_scopes={},
        metadata={"scope": "ledger test"},
    )


def test_factories_are_deterministic_and_evidence_is_exactly_bound():
    artifact = _artifact()
    source_a = _source_record()
    source_b = _source_record()
    span = _l1(source_record=source_a).source.evidence_spans[0]

    assert artifact == _artifact()
    assert source_a == source_b
    assert source_a.content_sha256 != ""
    assert span.source_revision_id == source_a.source_revision_id
    assert source_a.text[span.char_start : span.char_end] == span.text
    assert len(span.quote_sha256) == 64
    assert span.offset_unit == "unicode_codepoint"


def test_integrity_rejects_independent_evidence_quote_hash_and_offset_tampering():
    bundle = _bundle()
    l1 = bundle.l1_units[0]
    span = l1.source.evidence_spans[0]

    bad_hash = span.model_copy(update={"quote_sha256": "0" * 64})
    bad_l1 = l1.model_copy(
        update={"source": l1.source.model_copy(update={"evidence_spans": [bad_hash]})}
    )
    bad_revision = make_memory_unit_revision(
        payload=bad_l1,
        revision_number=1,
        previous_revision_id=None,
        revision_kind="create",
        transaction_time="2026-07-27T00:00:00Z",
        source_revision_ids=[bundle.source_record_revisions[0].source_revision_id],
        derived_from_revision_ids=[],
        producer=_producer(),
    )
    tampered = bundle.model_copy(
        update={
            "l1_units": [bad_l1],
            "unit_revisions": [bad_revision, bundle.unit_revisions[1]],
            "current_revision_ids": {
                bad_l1.unit_id: bad_revision.revision_id,
                bundle.l2_units[0].unit_id: bundle.unit_revisions[1].revision_id,
            },
        }
    )

    report = assess_authoritative_bundle_integrity(tampered)
    assert report.valid is False
    assert any("quote hash" in error for error in report.errors)

    bad_offset = span.model_copy(update={"char_start": 1})
    bad_l1_offset = l1.model_copy(
        update={"source": l1.source.model_copy(update={"evidence_spans": [bad_offset]})}
    )
    bad_offset_revision = make_memory_unit_revision(
        payload=bad_l1_offset,
        revision_number=1,
        previous_revision_id=None,
        revision_kind="create",
        transaction_time="2026-07-27T00:00:00Z",
        source_revision_ids=[bundle.source_record_revisions[0].source_revision_id],
        derived_from_revision_ids=[],
        producer=_producer(),
    )
    tampered_offset = bundle.model_copy(
        update={
            "l1_units": [bad_l1_offset],
            "unit_revisions": [bad_offset_revision, bundle.unit_revisions[1]],
            "current_revision_ids": {
                bad_l1_offset.unit_id: bad_offset_revision.revision_id,
                bundle.l2_units[0].unit_id: bundle.unit_revisions[1].revision_id,
            },
        }
    )
    offset_report = assess_authoritative_bundle_integrity(tampered_offset)
    assert offset_report.valid is False
    assert any("quote slice" in error for error in offset_report.errors)


def test_revision_chain_accepts_linear_history_and_rejects_branch_gap_and_non_leaf_pointer():
    bundle = _bundle()
    original = bundle.unit_revisions[0]
    updated_payload = bundle.l1_units[0].model_copy(update={"lifecycle": "superseded"})
    revision_two = make_memory_unit_revision(
        payload=updated_payload,
        revision_number=2,
        previous_revision_id=original.revision_id,
        revision_kind="lifecycle_update",
        transaction_time="2026-07-27T01:00:00Z",
        source_revision_ids=original.source_revision_ids,
        derived_from_revision_ids=[],
        producer=_producer(),
    )
    linear = _l1_only_bundle(
        bundle,
        revisions=[original, revision_two],
        current_revision_id=revision_two.revision_id,
        current_view=updated_payload,
    )
    assert assess_authoritative_bundle_integrity(linear).valid is True

    non_leaf = _l1_only_bundle(
        bundle,
        revisions=[original, revision_two],
        current_revision_id=original.revision_id,
        current_view=bundle.l1_units[0],
    )
    assert any(
        "non-leaf" in error for error in assess_authoritative_bundle_integrity(non_leaf).errors
    )

    branch = revision_two.model_copy(
        update={"revision_id": "branch-revision", "transaction_time": "2026-07-27T02:00:00Z"}
    )
    branched = _l1_only_bundle(
        bundle,
        revisions=[original, revision_two, branch],
        current_revision_id=revision_two.revision_id,
        current_view=updated_payload,
    )
    assert any("branch" in error for error in assess_authoritative_bundle_integrity(branched).errors)

    gap = revision_two.model_copy(update={"revision_number": 3, "revision_id": "gap-revision"})
    gapped = _l1_only_bundle(
        bundle,
        revisions=[original, gap],
        current_revision_id=gap.revision_id,
        current_view=updated_payload,
    )
    assert any("gap" in error for error in assess_authoritative_bundle_integrity(gapped).errors)


def test_structured_l2_matches_all_semantic_constraints_and_returns_claim_support_evidence():
    bundle = _bundle()
    plan = bundle.query_plans[0].model_copy(
        update={
            "target_level": "L2",
            "answer_kind": "evidence_set",
            "closure_id": None,
            "closure_spec_revision": None,
            "entity_ids": ["user"],
            "modality": "actual",
            "polarity": "positive",
            "time_constraint": ExactTimeConstraint(event_time="2025-01-01", valid_time="2025"),
        }
    )

    result = execute_authoritative_query(plan, bundle)

    assert result.abstained is False
    assert result.matched_unit_ids == ["l2-led-projects"]
    assert result.required_evidence_ids == ["E-l1-led-alpha"]

    for update in (
        {"canonical_operator": "caused_by"},
        {"predicate_sense": "lead-to/cause"},
        {"entity_ids": ["other-user"]},
        {"modality": "planned"},
        {"polarity": "negative"},
        {"time_constraint": ExactTimeConstraint(event_time="2024-01-01")},
    ):
        mismatch = execute_authoritative_query(plan.model_copy(update=update), bundle)
        assert mismatch.abstained is True
        assert mismatch.matched_unit_ids == []


def test_semantically_constrained_query_rejects_display_only_l2_count_claim():
    bundle = _bundle(structured_l2=False)
    plan = bundle.query_plans[0].model_copy(
        update={
            "target_level": "L2",
            "answer_kind": "evidence_set",
            "closure_id": None,
            "closure_spec_revision": None,
        }
    )

    result = execute_authoritative_query(plan, bundle)

    assert result.abstained is True
    assert result.matched_unit_ids == []
    assert bundle.l2_units[0].display_assertions == ["count(led_projects_by_user)=2"]
    assert bundle.l2_units[0].structured_claims == []


def test_count_query_abstains_when_project_identity_is_not_structurally_resolved():
    bundle = _bundle()
    plan = bundle.query_plans[0].model_copy(update={"target_level": "both"})

    result = execute_authoritative_query(plan, bundle)

    assert result.abstained is True
    assert result.reason == "structured_l2_identity_unresolved"
    assert result.required_evidence_ids == ["E-l1-led-alpha"]
    assert result.fallback_allowed is False


def test_integrity_rejects_duplicate_claim_ids_and_support_outside_l2_sources():
    bundle = _bundle()
    l2 = bundle.l2_units[0]
    claim = l2.structured_claims[0]
    duplicated = l2.model_copy(update={"structured_claims": [claim, claim]})
    duplicated_bundle = bundle.model_copy(update={"l2_units": [duplicated]})
    duplicate_report = assess_authoritative_bundle_integrity(duplicated_bundle)
    assert any("duplicate structured claim" in error for error in duplicate_report.errors)

    outside = claim.model_copy(update={"supporting_l1_units": ["l1-outside"]})
    outside_l2 = l2.model_copy(update={"structured_claims": [outside]})
    outside_bundle = bundle.model_copy(update={"l2_units": [outside_l2]})
    outside_report = assess_authoritative_bundle_integrity(outside_bundle)
    assert any("claim support" in error for error in outside_report.errors)


def test_closure_evaluation_id_is_deterministic_and_scope_external_changes_do_not_make_it_stale():
    bundle = _bundle()
    spec = bundle.closure_specs[1]
    evaluation = bundle.closure_evaluations[1]
    inputs = ClosureEvaluationInputs.for_query(bundle, bundle.query_plans[0])

    assert evaluate_closure_spec(spec, inputs) == evaluation
    assert is_closure_evaluation_fresh(evaluation, spec, inputs) is True

    external = _l1("l1-outside-scope", entity_id="outside")
    external_revision = make_memory_unit_revision(
        payload=external,
        revision_number=1,
        previous_revision_id=None,
        revision_kind="create",
        transaction_time="2026-07-27T03:00:00Z",
        source_revision_ids=[external.source.evidence_spans[0].source_revision_id],
        derived_from_revision_ids=[],
        producer=_producer(),
    )
    with_external = inputs.model_copy(
        update={
            "unit_revisions": [*inputs.unit_revisions, external_revision],
            "current_revision_ids": {
                **inputs.current_revision_ids,
                external.unit_id: external_revision.revision_id,
            },
        }
    )
    assert is_closure_evaluation_fresh(evaluation, spec, with_external) is True


def test_closure_evaluation_becomes_stale_for_spec_policy_scope_and_dependency_changes():
    bundle = _bundle()
    spec = bundle.closure_specs[1]
    evaluation = bundle.closure_evaluations[1]
    inputs = ClosureEvaluationInputs.for_query(bundle, bundle.query_plans[0])

    revised_spec = make_closure_spec(
        closure_id=spec.closure_id,
        revision=2,
        target_id=spec.target_id,
        pattern=spec.pattern,
        slots=spec.slots,
    )
    assert is_closure_evaluation_fresh(evaluation, revised_spec, inputs) is False
    assert is_closure_evaluation_fresh(
        evaluation, spec, inputs.model_copy(update={"policy_version": "2"})
    ) is False
    assert is_closure_evaluation_fresh(
        evaluation,
        spec,
        inputs.model_copy(
            update={
                "context": inputs.context.model_copy(
                    update={"query_scope": [bundle.l1_units[0].unit_id]}
                )
            }
        ),
    ) is False
    assert is_closure_evaluation_fresh(
        evaluation,
        spec,
        inputs.model_copy(
            update={"context": inputs.context.model_copy(update={"available_unit_ids": []})}
        ),
    ) is False

    changed_payload = bundle.l1_units[0].model_copy(update={"polarity": "negative"})
    changed_revision = make_memory_unit_revision(
        payload=changed_payload,
        revision_number=2,
        previous_revision_id=bundle.unit_revisions[0].revision_id,
        revision_kind="correction",
        transaction_time="2026-07-27T04:00:00Z",
        source_revision_ids=bundle.unit_revisions[0].source_revision_ids,
        derived_from_revision_ids=[],
        producer=_producer(),
    )
    changed_inputs = inputs.model_copy(
        update={
            "unit_revisions": [bundle.unit_revisions[0], changed_revision, bundle.unit_revisions[1]],
            "current_revision_ids": {
                **inputs.current_revision_ids,
                changed_payload.unit_id: changed_revision.revision_id,
            },
        }
    )
    assert is_closure_evaluation_fresh(evaluation, spec, changed_inputs) is False


def test_incomplete_or_stale_closure_cannot_support_answer_active_l2_or_fallback():
    bundle = _bundle()
    spec = make_closure_spec(
        closure_id="closure-led-projects-query",
        revision=1,
        target_id="query-led-projects",
        pattern="multi_evidence_set",
        slots=[
            ClosureSlotSpec(
                slot_id="slot-unbound",
                role="causal_link",
                required=True,
                bound_unit_id=None,
                fallback_class="blocked",
            )
        ],
    )
    inputs = ClosureEvaluationInputs.for_query(bundle, bundle.query_plans[0])
    incomplete = evaluate_closure_spec(spec, inputs)
    assert incomplete.complete is False
    assert incomplete.fallback_allowed is False

    broken = bundle.model_copy(
        update={
            "closure_specs": [bundle.closure_specs[0], spec],
            "closure_evaluations": [bundle.closure_evaluations[0], incomplete],
        }
    )
    result = execute_authoritative_query(bundle.query_plans[0], broken)
    assert result.abstained is True
    assert result.fallback_allowed is False
    report = assess_authoritative_bundle_integrity(broken)
    assert report.valid is True

    stale_inputs = inputs.model_copy(update={"policy_version": "changed"})
    stale_bundle = bundle.model_copy(
        update={"metadata": {**bundle.metadata, "closure_policy_version": "changed"}}
    )
    assert is_closure_evaluation_fresh(
        bundle.closure_evaluations[1], bundle.closure_specs[1], stale_inputs
    ) is False
    stale_result = execute_authoritative_query(bundle.query_plans[0], stale_bundle)
    assert stale_result.abstained is True
    assert stale_result.fallback_allowed is False


def test_active_l2_rejects_query_context_evaluation_even_when_query_evaluation_is_complete():
    bundle = _bundle()
    l2 = bundle.l2_units[0].model_copy(
        update={"closure_evaluation_id": bundle.closure_evaluations[1].evaluation_id}
    )
    revision = make_memory_unit_revision(
        payload=l2,
        revision_number=1,
        previous_revision_id=None,
        revision_kind="create",
        transaction_time="2026-07-27T00:00:00Z",
        source_revision_ids=bundle.unit_revisions[1].source_revision_ids,
        derived_from_revision_ids=bundle.unit_revisions[1].derived_from_revision_ids,
        producer=_producer(),
    )
    candidate = bundle.model_copy(
        update={
            "l2_units": [l2],
            "unit_revisions": [bundle.unit_revisions[0], revision],
            "current_revision_ids": {
                bundle.l1_units[0].unit_id: bundle.unit_revisions[0].revision_id,
                l2.unit_id: revision.revision_id,
            },
        }
    )

    report = assess_authoritative_bundle_integrity(candidate)

    assert any("active l2" in error and "claim-context" in error for error in report.errors)
