from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from tools.natural_memory_benchmark.io import canonical_json_bytes
from tools.natural_memory_benchmark.query_compiler_v2 import (
    AnswerDraftV1,
    CompilerRegistryV1,
    GitMemoryViewRefV1,
    PredicateRegistryEntryV1,
    QueryAtomDraftV1,
    QueryContextV1,
    QueryDraftV1,
    QueryPatternGroupDraftV1,
    QueryRoleDraftV1,
    QueryTermDraftV1,
    compile_query_draft,
)
from tools.natural_memory_benchmark.query_compiler_v2_assessment import (
    QueryCompilerAuthorityCaseV1,
    QueryCompilerAuthorityDocumentV1,
    QueryCompilerGoldCaseV1,
    QueryCompilerGoldDocumentV1,
    QueryCompilerPublicCaseV1,
    QueryCompilerPublicDocumentV1,
    memory_view_handle,
)
from tools.natural_memory_benchmark.query_compiler_v2_proposal_eval import (
    QueryDraftGoldCaseV1,
    QueryDraftGoldDocumentV1,
    QueryDraftProposalDocumentV1,
    QueryDraftProposalFormalFreezeV1,
    QueryDraftProposalPreregistrationV1,
    QueryDraftProposalProvenanceV1,
    QueryDraftProposalScoreV1,
    QueryDraftRawProposalV1,
    QueryDraftValidationDocumentV1,
    evaluate_query_draft_proposals,
    freeze_query_draft_proposal_run,
    materialize_typed_query_proposals,
    score_query_draft_proposals,
    validate_frozen_query_draft_proposal_run,
    validate_public_proposal_boundary,
    validate_proposal_provenance,
    validate_typed_proposal_materialization,
    verify_query_draft_proposal_history,
)
from tools.natural_memory_benchmark import query_compiler_v2_proposal_eval


def _sha(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _context() -> QueryContextV1:
    return QueryContextV1(
        query_id="qq-fedcba9876543210",
        raw_query="Which project do I lead?",
        query_time="2026-07-29T00:00:00Z",
        current_user_entity_id="entity-user",
        memory_view=GitMemoryViewRefV1(
            workspace_id="workspace-main",
            repository_epoch_id="epoch-001",
            checkpoint_id="checkpoint-0007",
            git_commit="a" * 40,
            authoritative_ref="refs/heads/authoritative",
        ),
        ontology_revision="ontology-v7",
        identity_revision="identity-v4",
        compiler_policy_revision="query-policy-v2",
    )


def _registry() -> CompilerRegistryV1:
    return CompilerRegistryV1(
        ontology_revision="ontology-v7",
        identity_revision="identity-v4",
        registry_revision="registry-v1",
        entity_aliases={"i": ["entity-user"]},
        entity_types={"entity-user": ["Person"]},
        identity_status={"entity-user": "resolved"},
        predicate_aliases={
            "lead": [
                PredicateRegistryEntryV1(
                    sense="lead/manage",
                    canonical_operator="manage",
                    role_types={"agent": "Person", "theme": "Project"},
                )
            ]
        },
    )


def _public() -> QueryCompilerPublicDocumentV1:
    context = _context()
    return QueryCompilerPublicDocumentV1(
        dataset_id="query-proposer-dev-v1",
        cases=[
            QueryCompilerPublicCaseV1(
                case_id="qc-0123456789abcdef",
                query_id="qq-fedcba9876543210",
                raw_query=context.raw_query,
                query_time=context.query_time,
                current_user_surface="I",
                memory_view_handle=memory_view_handle(context.memory_view),
                compiler_policy_revision=context.compiler_policy_revision,
            )
        ],
    )


def _proposals(
    *,
    raw_payload: object | None = None,
    parse_status: str = "json",
    errors: list[str] | None = None,
    raw_response_sha256: str = "a" * 64,
) -> QueryDraftProposalDocumentV1:
    if raw_payload is None and parse_status == "json":
        raw_payload = {"not": "a valid QueryDraftV1"}
    return QueryDraftProposalDocumentV1(
        dataset_id="query-proposer-dev-v1",
        proposals=[
            QueryDraftRawProposalV1(
                case_id="qc-0123456789abcdef",
                parse_status=parse_status,
                raw_payload=raw_payload,
                raw_response_sha256=raw_response_sha256,
                errors=errors or [],
            )
        ],
    )


def _draft(
    *,
    predicate_surface: str = "lead",
    producer_id: str = "model-proposer",
    producer_version: str = "1",
    group_id: str = "group-1",
    atom_id: str = "atom-1",
    answer_variable: str = "?project",
) -> QueryDraftV1:
    return QueryDraftV1(
        query_id="qq-fedcba9876543210",
        intent="fact_lookup",
        target_level="both",
        answer=AnswerDraftV1(kind="fact", variable=answer_variable),
        pattern_groups=[
            QueryPatternGroupDraftV1(
                group_id=group_id,
                atoms=[
                    QueryAtomDraftV1(
                        atom_id=atom_id,
                        predicate_surface=predicate_surface,
                        roles=[
                            QueryRoleDraftV1(
                                role="agent",
                                role_name="ARG0",
                                term=QueryTermDraftV1(
                                    kind="entity_surface",
                                    value="i",
                                    expected_type="Person",
                                ),
                            ),
                            QueryRoleDraftV1(
                                role="theme",
                                role_name="ARG1",
                                term=QueryTermDraftV1(
                                    kind="variable",
                                    value=answer_variable,
                                    expected_type="Project",
                                ),
                            ),
                        ],
                    )
                ],
            )
        ],
        lifecycle="active",
        conflict_policy="require_resolved",
        supersession_policy="current_only",
        evidence_policy="provenance_closure",
        producer_id=producer_id,
        producer_version=producer_version,
    )


def _draft_gold(*, critical: bool = True) -> QueryDraftGoldDocumentV1:
    return QueryDraftGoldDocumentV1(
        dataset_id="query-proposer-dev-v1",
        cases=[
            QueryDraftGoldCaseV1(
                case_id="qc-0123456789abcdef",
                expected_draft=_draft(
                    producer_id="gold-author",
                    producer_version="gold-v1",
                ),
                critical=critical,
            )
        ],
    )


def _authority() -> QueryCompilerAuthorityDocumentV1:
    return QueryCompilerAuthorityDocumentV1(
        dataset_id="query-proposer-dev-v1",
        cases=[
            QueryCompilerAuthorityCaseV1(
                case_id="qc-0123456789abcdef",
                context=_context(),
                registry=_registry(),
            )
        ],
    )


def _compiler_gold() -> QueryCompilerGoldDocumentV1:
    result = compile_query_draft(_draft(), _context(), _registry())
    assert result.status == "executable"
    assert result.plan is not None
    return QueryCompilerGoldDocumentV1(
        dataset_id="query-proposer-dev-v1",
        cases=[
            QueryCompilerGoldCaseV1(
                case_id="qc-0123456789abcdef",
                family="atomic_fact_role",
                expected_status="executable",
                expected_plan_sha256=result.plan.plan_sha256,
                expected_fallback_allowed=False,
                expected_unresolved_slots=[],
                expected_blocked_reasons=[],
            )
        ],
    )


def _valid_run_artifacts() -> tuple[
    QueryCompilerPublicDocumentV1,
    bytes,
    dict[str, object],
    dict[str, object],
    QueryDraftProposalDocumentV1,
    QueryDraftProposalProvenanceV1,
    QueryDraftValidationDocumentV1,
    object,
]:
    public = _public()
    prompt = b"Return one QueryDraftV1 for each opaque case.\n"
    dispatch = {
        "request_id": "request-1",
        "case_count": 1,
        "model": "model-alias",
    }
    raw_response = {"response_id": "response-1", "model": "model-returned"}
    proposals = _proposals(
        raw_payload=_draft().model_dump(mode="json"),
        raw_response_sha256=_sha(raw_response),
    )
    provenance = QueryDraftProposalProvenanceV1(
        dataset_id=public.dataset_id,
        run_id="run-query-proposer-dev-v1",
        requested_model="model-alias",
        response_model="model-returned",
        public_sha256=_sha(public),
        prompt_sha256=hashlib.sha256(prompt).hexdigest(),
        dispatch_sha256=_sha(dispatch),
        raw_response_sha256=_sha(raw_response),
        proposals_sha256=_sha(proposals),
    )
    receipt, typed = materialize_typed_query_proposals(public, proposals)
    assert typed is not None
    return (
        public,
        prompt,
        dispatch,
        raw_response,
        proposals,
        provenance,
        receipt,
        typed,
    )


def test_raw_draft_payload_remains_scoreable_before_schema_validation() -> None:
    public = _public()
    proposals = _proposals()

    validate_public_proposal_boundary(public, proposals)

    assert proposals.proposals[0].raw_payload == {"not": "a valid QueryDraftV1"}


def test_public_proposal_boundary_requires_exact_unique_opaque_coverage() -> None:
    public = _public()
    proposals = _proposals()

    duplicate = proposals.model_copy(
        update={"proposals": [proposals.proposals[0], proposals.proposals[0]]}
    )
    with pytest.raises(ValueError, match="duplicate proposal case id"):
        QueryDraftProposalDocumentV1.model_validate(duplicate.model_dump())

    missing = proposals.model_copy(update={"proposals": []})
    with pytest.raises(ValidationError):
        QueryDraftProposalDocumentV1.model_validate(missing.model_dump())

    extra = proposals.model_copy(
        update={
            "proposals": [
                proposals.proposals[0],
                QueryDraftRawProposalV1(
                    case_id="qc-1111111111111111",
                    parse_status="json",
                    raw_payload=["extra", True],
                    raw_response_sha256="b" * 64,
                ),
            ]
        }
    )
    with pytest.raises(ValueError, match="public/proposal case coverage mismatch"):
        validate_public_proposal_boundary(public, extra)

    with pytest.raises(ValidationError):
        QueryDraftRawProposalV1(
            case_id="qc-latest-answer",
            parse_status="json",
            raw_payload={"leaks": "outcome"},
            raw_response_sha256="c" * 64,
        )


def test_provenance_binds_public_prompt_transport_and_frozen_proposals() -> None:
    public = _public()
    prompt = b"Return one QueryDraftV1 for each opaque case.\n"
    dispatch = {
        "request_id": "request-1",
        "case_count": 1,
        "model": "model-alias",
    }
    raw_response = {"response_id": "response-1", "model": "model-returned"}
    proposals = _proposals(raw_response_sha256=_sha(raw_response))
    provenance = QueryDraftProposalProvenanceV1(
        dataset_id=public.dataset_id,
        run_id="run-query-proposer-dev-v1",
        requested_model="model-alias",
        response_model="model-returned",
        public_sha256=_sha(public),
        prompt_sha256=hashlib.sha256(prompt).hexdigest(),
        dispatch_sha256=_sha(dispatch),
        raw_response_sha256=_sha(raw_response),
        proposals_sha256=_sha(proposals),
    )

    validate_proposal_provenance(
        public=public,
        proposals=proposals,
        provenance=provenance,
        prompt_bytes=prompt,
        dispatch=dispatch,
        raw_response=raw_response,
    )

    tampered = provenance.model_copy(update={"proposals_sha256": "0" * 64})
    with pytest.raises(ValueError, match="proposal provenance hash mismatch"):
        validate_proposal_provenance(
            public=public,
            proposals=proposals,
            provenance=tampered,
            prompt_bytes=prompt,
            dispatch=dispatch,
            raw_response=raw_response,
        )


def test_provenance_rejects_envelope_not_bound_to_raw_response() -> None:
    public = _public()
    prompt = b"Return one QueryDraftV1 for each opaque case.\n"
    dispatch = {
        "request_id": "request-1",
        "case_count": 1,
        "model": "model-alias",
    }
    raw_response = {"response_id": "response-1", "model": "model-returned"}
    proposals = _proposals(raw_response_sha256="0" * 64)
    provenance = QueryDraftProposalProvenanceV1(
        dataset_id=public.dataset_id,
        run_id="run-query-proposer-dev-v1",
        requested_model="model-alias",
        response_model="model-returned",
        public_sha256=_sha(public),
        prompt_sha256=hashlib.sha256(prompt).hexdigest(),
        dispatch_sha256=_sha(dispatch),
        raw_response_sha256=_sha(raw_response),
        proposals_sha256=_sha(proposals),
    )

    with pytest.raises(ValueError, match="envelope raw-response hash mismatch"):
        validate_proposal_provenance(
            public=public,
            proposals=proposals,
            provenance=provenance,
            prompt_bytes=prompt,
            dispatch=dispatch,
            raw_response=raw_response,
        )


def test_provenance_enforces_one_run_public_only_zero_history_boundary() -> None:
    public = _public()
    proposals = _proposals()
    payload = {
        "schema_version": "query-draft-proposal-provenance-v1",
        "dataset_id": public.dataset_id,
        "run_id": "run-query-proposer-dev-v1",
        "requested_model": "model-alias",
        "response_model": "model-returned",
        "public_sha256": _sha(public),
        "prompt_sha256": "1" * 64,
        "dispatch_sha256": "2" * 64,
        "raw_response_sha256": "3" * 64,
        "proposals_sha256": _sha(proposals),
        "semantic_run_count": 2,
        "history_context_inherited": False,
        "authority_or_gold_read_before_freeze": False,
        "proposals_frozen_before_scoring": True,
        "isolation_enforcement": "declarative_file_access_contract",
    }

    with pytest.raises(ValidationError):
        QueryDraftProposalProvenanceV1.model_validate(payload)

    payload["semantic_run_count"] = 1
    payload["history_context_inherited"] = True
    with pytest.raises(ValidationError):
        QueryDraftProposalProvenanceV1.model_validate(payload)

    payload["history_context_inherited"] = False
    payload["authority_or_gold_read_before_freeze"] = True
    with pytest.raises(ValidationError):
        QueryDraftProposalProvenanceV1.model_validate(payload)


def test_raw_draft_score_is_semantic_and_excludes_producer_identity() -> None:
    public = _public()
    proposals = _proposals(
        raw_payload=_draft(
            producer_id="different-provider",
            producer_version="response-model-v7",
        ).model_dump(mode="json")
    )

    score = score_query_draft_proposals(public, proposals, _draft_gold())

    assert score.metrics.case_coverage == 1.0
    assert score.metrics.schema_valid_rate == 1.0
    assert score.metrics.query_id_accuracy == 1.0
    assert score.metrics.intent_accuracy == 1.0
    assert score.metrics.target_level_accuracy == 1.0
    assert score.metrics.answer_accuracy == 1.0
    assert score.metrics.pattern_accuracy == 1.0
    assert score.metrics.time_accuracy == 1.0
    assert score.metrics.lifecycle_accuracy == 1.0
    assert score.metrics.source_accuracy == 1.0
    assert score.metrics.conflict_supersession_accuracy == 1.0
    assert score.metrics.evidence_policy_accuracy == 1.0
    assert score.metrics.explicit_absence_accuracy == 1.0
    assert score.metrics.draft_template_exact == 1.0
    assert score.metrics.draft_semantic_exact == 1.0
    assert score.metrics.missing_output_count == 0
    assert score.metrics.invalid_json_count == 0
    assert score.metrics.transport_error_count == 0
    assert score.metrics.schema_invalid_output_count == 0
    assert score.metrics.critical_invalid_output_count == 0
    assert score.raw_proposer_quality_ready is True


def test_schema_invalid_raw_draft_stays_in_denominator_and_fails_ready() -> None:
    score = score_query_draft_proposals(_public(), _proposals(), _draft_gold())

    assert score.metrics.case_count == 1
    assert score.metrics.schema_valid_rate == 0.0
    assert score.metrics.draft_semantic_exact == 0.0
    assert score.metrics.schema_invalid_output_count == 1
    assert score.metrics.critical_invalid_output_count == 1
    assert score.raw_proposer_quality_ready is False
    assert score.validation_errors["qc-0123456789abcdef"]


@pytest.mark.parametrize(
    ("parse_status", "metric_name"),
    [
        ("missing", "missing_output_count"),
        ("invalid_json", "invalid_json_count"),
        ("transport_error", "transport_error_count"),
    ],
)
def test_non_json_output_statuses_remain_in_denominator(
    parse_status: str,
    metric_name: str,
) -> None:
    proposals = _proposals(
        parse_status=parse_status,
        raw_payload=None,
        errors=[f"{parse_status} output"],
    )

    score = score_query_draft_proposals(_public(), proposals, _draft_gold())

    assert score.metrics.schema_valid_rate == 0.0
    assert getattr(score.metrics, metric_name) == 1
    assert score.metrics.critical_invalid_output_count == 1
    assert score.raw_proposer_quality_ready is False


def test_pattern_error_is_localized_without_hiding_other_exact_fields() -> None:
    proposals = _proposals(
        raw_payload=_draft(predicate_surface="guide").model_dump()
    )

    score = score_query_draft_proposals(_public(), proposals, _draft_gold())

    assert score.metrics.pattern_accuracy == 0.0
    assert score.metrics.draft_semantic_exact == 0.0
    assert score.metrics.answer_accuracy == 1.0
    assert score.metrics.conflict_supersession_accuracy == 1.0
    assert score.raw_proposer_quality_ready is False


def test_semantic_exact_alpha_normalizes_local_ids_and_variables() -> None:
    proposals = _proposals(
        raw_payload=_draft(
            group_id="local-or-7",
            atom_id="local-atom-9",
            answer_variable="?work",
        ).model_dump()
    )

    score = score_query_draft_proposals(_public(), proposals, _draft_gold())

    assert score.metrics.draft_template_exact == 0.0
    assert score.metrics.draft_semantic_exact == 1.0
    assert score.raw_proposer_quality_ready is True


def test_raw_score_rederives_readiness_on_validate_and_model_copy() -> None:
    score = score_query_draft_proposals(
        _public(),
        _proposals(raw_payload=_draft().model_dump()),
        _draft_gold(),
    )
    payload = score.model_dump(mode="json")
    payload["raw_proposer_quality_ready"] = False

    with pytest.raises(ValueError, match="raw_proposer_quality_ready"):
        QueryDraftProposalScoreV1.model_validate(payload)
    with pytest.raises(ValueError, match="raw_proposer_quality_ready"):
        score.model_copy(update={"raw_proposer_quality_ready": False})


def test_raw_score_rejects_validation_errors_inconsistent_with_counts() -> None:
    ready = score_query_draft_proposals(
        _public(),
        _proposals(raw_payload=_draft().model_dump()),
        _draft_gold(),
    )
    ready_payload = ready.model_dump(mode="json")
    ready_payload["validation_errors"] = {
        "qc-0123456789abcdef": ["unexpected validation error"]
    }
    with pytest.raises(ValueError, match="validation error count mismatch"):
        QueryDraftProposalScoreV1.model_validate(ready_payload)

    invalid = score_query_draft_proposals(_public(), _proposals(), _draft_gold())
    invalid_payload = invalid.model_dump(mode="json")
    invalid_payload["validation_errors"] = {}
    with pytest.raises(ValueError, match="validation error count mismatch"):
        QueryDraftProposalScoreV1.model_validate(invalid_payload)


def test_validation_receipt_binds_raw_envelope_to_exact_typed_proposal() -> None:
    proposals = _proposals(raw_payload=_draft().model_dump(mode="json"))

    receipt, typed = materialize_typed_query_proposals(_public(), proposals)

    assert receipt.all_drafts_valid is True
    assert typed is not None
    assert receipt.typed_proposals_sha256 == _sha(typed)
    entry = receipt.entries[0]
    assert entry.validation_status == "valid"
    assert entry.raw_envelope_sha256 == _sha(proposals.proposals[0])
    assert entry.typed_draft_sha256 == _sha(typed.proposals[0].draft)
    validate_typed_proposal_materialization(proposals, receipt, typed)

    repaired = typed.model_copy(
        update={
            "proposals": [
                typed.proposals[0].model_copy(
                    update={"draft": _draft(predicate_surface="guide")}
                )
            ]
        }
    )
    with pytest.raises(ValueError, match="typed proposal materialization mismatch"):
        validate_typed_proposal_materialization(proposals, receipt, repaired)


def test_invalid_raw_case_prevents_formal_gate_evaluation() -> None:
    evaluation = evaluate_query_draft_proposals(
        public=_public(),
        authority=_authority(),
        proposals=_proposals(),
        draft_gold=_draft_gold(),
        compiler_gold=_compiler_gold(),
    )

    assert evaluation.raw_score.raw_proposer_quality_ready is False
    assert evaluation.validation_receipt.all_drafts_valid is False
    assert evaluation.gate_evaluated is False
    assert evaluation.gate_score is None
    assert evaluation.combined_dev_ready is False


def test_valid_raw_cases_use_unchanged_compiler_gate_and_keep_readiness_separate() -> None:
    evaluation = evaluate_query_draft_proposals(
        public=_public(),
        authority=_authority(),
        proposals=_proposals(raw_payload=_draft().model_dump(mode="json")),
        draft_gold=_draft_gold(),
        compiler_gold=_compiler_gold(),
    )

    assert evaluation.raw_score.raw_proposer_quality_ready is True
    assert evaluation.gate_evaluated is True
    assert evaluation.gate_score is not None
    assert evaluation.gate_score.gate_safety_ready is True
    assert evaluation.gate_score.compilation_utility_ready is True
    assert evaluation.gate_score.raw_proposer_quality_evaluated is False
    assert evaluation.combined_dev_ready is True


def test_validation_receipt_and_combined_result_rederive_claims_on_copy() -> None:
    proposals = _proposals(raw_payload=_draft().model_dump())
    receipt, _ = materialize_typed_query_proposals(_public(), proposals)
    with pytest.raises(ValueError, match="all_drafts_valid"):
        receipt.model_copy(update={"all_drafts_valid": False})

    evaluation = evaluate_query_draft_proposals(
        public=_public(),
        authority=_authority(),
        proposals=proposals,
        draft_gold=_draft_gold(),
        compiler_gold=_compiler_gold(),
    )
    with pytest.raises(ValueError, match="combined_dev_ready"):
        evaluation.model_copy(update={"combined_dev_ready": False})

    payload = receipt.model_dump(mode="json")
    payload["typed_proposals_sha256"] = None
    with pytest.raises(ValueError, match="typed_proposals_sha256"):
        QueryDraftValidationDocumentV1.model_validate(payload)


def test_combined_evaluation_rejects_mixed_dataset_documents() -> None:
    evaluation = evaluate_query_draft_proposals(
        public=_public(),
        authority=_authority(),
        proposals=_proposals(raw_payload=_draft().model_dump()),
        draft_gold=_draft_gold(),
        compiler_gold=_compiler_gold(),
    )
    payload = evaluation.model_dump(mode="json")
    payload["raw_score"]["dataset_id"] = "different-dataset"

    with pytest.raises(ValueError, match="evaluation dataset_id mismatch"):
        type(evaluation).model_validate(payload)


def test_frozen_run_is_read_only_replayable_and_binds_model_ids(tmp_path) -> None:
    (
        public,
        prompt,
        dispatch,
        raw_response,
        proposals,
        provenance,
        receipt,
        typed,
    ) = _valid_run_artifacts()
    run_root = tmp_path / "query-proposer-run"

    manifest = freeze_query_draft_proposal_run(
        root=run_root,
        public=public,
        prompt_bytes=prompt,
        dispatch=dispatch,
        raw_response=raw_response,
        proposals=proposals,
        provenance=provenance,
        validation_receipt=receipt,
        typed_proposals=typed,
    )

    assert manifest.requested_model == "model-alias"
    assert manifest.response_model == "model-returned"
    assert set(manifest.artifact_sha256) == {
        "public.json",
        "proposer-prompt.md",
        "dispatch.json",
        "raw-response.json",
        "proposals.json",
        "provenance.json",
        "validation-receipt.json",
        "typed-proposals.json",
    }
    for name in [*manifest.artifact_sha256, "artifact-manifest.json"]:
        assert (run_root / name).stat().st_mode & 0o222 == 0
    assert validate_frozen_query_draft_proposal_run(run_root) == manifest
    assert (
        freeze_query_draft_proposal_run(
            root=run_root,
            public=public,
            prompt_bytes=prompt,
            dispatch=dispatch,
            raw_response=raw_response,
            proposals=proposals,
            provenance=provenance,
            validation_receipt=receipt,
            typed_proposals=typed,
        )
        == manifest
    )

    changed_provenance = provenance.model_copy(update={"run_id": "different-run"})
    with pytest.raises(FileExistsError, match="immutable artifact differs"):
        freeze_query_draft_proposal_run(
            root=run_root,
            public=public,
            prompt_bytes=prompt,
            dispatch=dispatch,
            raw_response=raw_response,
            proposals=proposals,
            provenance=changed_provenance,
            validation_receipt=receipt,
            typed_proposals=typed,
        )


def test_freeze_rejects_credentials_before_writing_any_artifact(tmp_path) -> None:
    (
        public,
        prompt,
        dispatch,
        raw_response,
        proposals,
        provenance,
        receipt,
        typed,
    ) = _valid_run_artifacts()
    raw_response["authorization"] = "Bearer secret-value-1234567890"
    run_root = tmp_path / "query-proposer-run"

    with pytest.raises(ValueError, match="forbidden credential material"):
        freeze_query_draft_proposal_run(
            root=run_root,
            public=public,
            prompt_bytes=prompt,
            dispatch=dispatch,
            raw_response=raw_response,
            proposals=proposals,
            provenance=provenance,
            validation_receipt=receipt,
            typed_proposals=typed,
        )

    assert not run_root.exists()


@pytest.mark.parametrize(
    ("field", "unsafe_value"),
    [
        ("semantic_run_count", 2),
        ("history_context_inherited", True),
        ("authority_or_gold_read_before_freeze", True),
        ("proposals_frozen_before_scoring", False),
    ],
)
def test_freeze_revalidates_model_copy_safety_claims_before_writing(
    tmp_path,
    field,
    unsafe_value,
) -> None:
    (
        public,
        prompt,
        dispatch,
        raw_response,
        proposals,
        provenance,
        receipt,
        typed,
    ) = _valid_run_artifacts()
    forged = provenance.model_copy(update={field: unsafe_value})
    run_root = tmp_path / field

    with pytest.raises(ValidationError):
        freeze_query_draft_proposal_run(
            root=run_root,
            public=public,
            prompt_bytes=prompt,
            dispatch=dispatch,
            raw_response=raw_response,
            proposals=proposals,
            provenance=forged,
            validation_receipt=receipt,
            typed_proposals=typed,
        )

    assert not run_root.exists()


def test_freeze_revalidates_external_models_before_writing(tmp_path) -> None:
    (
        public,
        prompt,
        dispatch,
        raw_response,
        proposals,
        provenance,
        receipt,
        typed,
    ) = _valid_run_artifacts()
    forged_public = public.model_copy(update={"cases": []})
    run_root = tmp_path / "forged-public"

    with pytest.raises(ValidationError):
        freeze_query_draft_proposal_run(
            root=run_root,
            public=forged_public,
            prompt_bytes=prompt,
            dispatch=dispatch,
            raw_response=raw_response,
            proposals=proposals,
            provenance=provenance,
            validation_receipt=receipt,
            typed_proposals=typed,
        )

    assert not run_root.exists()


@pytest.mark.parametrize(
    ("location", "claimed_model"),
    [("requested", "wrong-requested-model"), ("response", "wrong-response-model")],
)
def test_freeze_binds_declared_models_to_transport_objects(
    tmp_path,
    location,
    claimed_model,
) -> None:
    (
        public,
        prompt,
        dispatch,
        raw_response,
        proposals,
        provenance,
        receipt,
        typed,
    ) = _valid_run_artifacts()
    field = "requested_model" if location == "requested" else "response_model"
    forged = provenance.model_copy(update={field: claimed_model})
    run_root = tmp_path / location

    with pytest.raises(ValueError, match=f"{field} does not match"):
        freeze_query_draft_proposal_run(
            root=run_root,
            public=public,
            prompt_bytes=prompt,
            dispatch=dispatch,
            raw_response=raw_response,
            proposals=proposals,
            provenance=forged,
            validation_receipt=receipt,
            typed_proposals=typed,
        )

    assert not run_root.exists()


@pytest.mark.parametrize(
    "forbidden_key",
    [
        "openai_api_key",
        "x-api-key",
        "aws_secret_access_key",
        "private_key",
        "session_token",
        "cookie",
        "api_token",
        "github_token",
        "auth_header",
        "client_secret_value",
        "credential",
        "credentials",
    ],
)
def test_freeze_rejects_common_nested_credential_keys(
    tmp_path,
    forbidden_key,
) -> None:
    (
        public,
        prompt,
        dispatch,
        raw_response,
        proposals,
        provenance,
        receipt,
        typed,
    ) = _valid_run_artifacts()
    dispatch["transport"] = {forbidden_key: "live-secret-value"}
    run_root = tmp_path / forbidden_key

    with pytest.raises(ValueError, match="forbidden credential material"):
        freeze_query_draft_proposal_run(
            root=run_root,
            public=public,
            prompt_bytes=prompt,
            dispatch=dispatch,
            raw_response=raw_response,
            proposals=proposals,
            provenance=provenance,
            validation_receipt=receipt,
            typed_proposals=typed,
        )

    assert not run_root.exists()


def test_freeze_allows_hash_metadata_and_explicit_secret_placeholders(
    tmp_path,
) -> None:
    (
        public,
        prompt,
        dispatch,
        raw_response,
        proposals,
        provenance,
        receipt,
        typed,
    ) = _valid_run_artifacts()
    dispatch.update(
        {
            "api_key_sha256": "0" * 64,
            "token_count": 12,
            "password_policy": "never persist passwords",
            "documentation": "Authorization: Bearer YOUR_API_TOKEN",
            "stop_token": "<END_OF_TURN>",
            "auth_header": "Bearer YOUR_API_TOKEN",
        }
    )
    provenance = provenance.model_copy(
        update={"dispatch_sha256": _sha(dispatch)}
    )

    manifest = freeze_query_draft_proposal_run(
        root=tmp_path / "placeholder-run",
        public=public,
        prompt_bytes=prompt,
        dispatch=dispatch,
        raw_response=raw_response,
        proposals=proposals,
        provenance=provenance,
        validation_receipt=receipt,
        typed_proposals=typed,
    )

    assert manifest.dataset_id == public.dataset_id


@pytest.mark.parametrize(
    "documentation",
    [
        (
            "Bearer YOUR_API_TOKEN followed by "
            "Bearer live-secret-value-1234567890"
        ),
        "Bearer live-EXAMPLE-secret-1234567890",
        "token=hf_abcdefghijklmnopqrstuvwxyz123456",
        "token=ghp_abcdefghijklmnopqrstuvwxyz123456",
    ],
)
def test_freeze_rejects_live_secret_after_placeholder_or_provider_prefix(
    tmp_path,
    documentation,
) -> None:
    (
        public,
        prompt,
        dispatch,
        raw_response,
        proposals,
        provenance,
        receipt,
        typed,
    ) = _valid_run_artifacts()
    dispatch["documentation"] = documentation
    provenance = provenance.model_copy(
        update={"dispatch_sha256": _sha(dispatch)}
    )
    run_root = tmp_path / hashlib.sha256(
        documentation.encode("utf-8")
    ).hexdigest()[:12]

    with pytest.raises(ValueError, match="forbidden credential material"):
        freeze_query_draft_proposal_run(
            root=run_root,
            public=public,
            prompt_bytes=prompt,
            dispatch=dispatch,
            raw_response=raw_response,
            proposals=proposals,
            provenance=provenance,
            validation_receipt=receipt,
            typed_proposals=typed,
        )

    assert not run_root.exists()


def test_freeze_rejects_conflicting_nested_transport_model(tmp_path) -> None:
    (
        public,
        prompt,
        dispatch,
        raw_response,
        proposals,
        provenance,
        receipt,
        typed,
    ) = _valid_run_artifacts()
    dispatch["provider_request"] = {"model": "different-model"}
    provenance = provenance.model_copy(
        update={"dispatch_sha256": _sha(dispatch)}
    )
    run_root = tmp_path / "nested-model"

    with pytest.raises(ValueError, match="conflicting nested model"):
        freeze_query_draft_proposal_run(
            root=run_root,
            public=public,
            prompt_bytes=prompt,
            dispatch=dispatch,
            raw_response=raw_response,
            proposals=proposals,
            provenance=provenance,
            validation_receipt=receipt,
            typed_proposals=typed,
        )

    assert not run_root.exists()


@pytest.mark.parametrize(
    "unsafe_path",
    [
        ":(literal)gate/prompt.md",
        "gate/*.json",
        "gate/[raw].json",
        "gate/file?.json",
    ],
)
def test_git_contract_paths_reject_pathspec_magic(unsafe_path) -> None:
    with pytest.raises(ValidationError, match="pathspec"):
        QueryDraftProposalPreregistrationV1(
            dataset_id="query-proposer-dev-v1",
            prompt_path=unsafe_path,
            prompt_sha256="a" * 64,
            compiler_path="frozen/compiler.py",
            compiler_sha256="b" * 64,
            assessment_path="frozen/assessment.py",
            assessment_sha256="c" * 64,
            proposer_eval_path="frozen/proposer.py",
            proposer_eval_sha256="d" * 64,
        )


def test_invalid_utf8_prompt_fails_before_any_artifact_is_written(tmp_path) -> None:
    (
        public,
        _,
        dispatch,
        raw_response,
        proposals,
        provenance,
        receipt,
        typed,
    ) = _valid_run_artifacts()
    prompt = b"\xff\xfe"
    provenance = provenance.model_copy(
        update={"prompt_sha256": hashlib.sha256(prompt).hexdigest()}
    )
    run_root = tmp_path / "invalid-prompt"

    with pytest.raises(UnicodeDecodeError):
        freeze_query_draft_proposal_run(
            root=run_root,
            public=public,
            prompt_bytes=prompt,
            dispatch=dispatch,
            raw_response=raw_response,
            proposals=proposals,
            provenance=provenance,
            validation_receipt=receipt,
            typed_proposals=typed,
        )

    assert not run_root.exists()


@pytest.mark.parametrize(
    "extra_name",
    ["authority.json", "draft-gold.json", "secret.txt"],
)
def test_frozen_run_rejects_unmanifested_files(tmp_path, extra_name) -> None:
    (
        public,
        prompt,
        dispatch,
        raw_response,
        proposals,
        provenance,
        receipt,
        typed,
    ) = _valid_run_artifacts()
    run_root = tmp_path / extra_name.replace(".", "-")
    freeze_query_draft_proposal_run(
        root=run_root,
        public=public,
        prompt_bytes=prompt,
        dispatch=dispatch,
        raw_response=raw_response,
        proposals=proposals,
        provenance=provenance,
        validation_receipt=receipt,
        typed_proposals=typed,
    )
    (run_root / extra_name).write_text("unmanifested\n", encoding="utf-8")

    with pytest.raises(ValueError, match="run artifact set mismatch"):
        validate_frozen_query_draft_proposal_run(run_root)


def test_frozen_run_rejects_unmanifested_directory_and_symlink(tmp_path) -> None:
    (
        public,
        prompt,
        dispatch,
        raw_response,
        proposals,
        provenance,
        receipt,
        typed,
    ) = _valid_run_artifacts()
    run_root = tmp_path / "extra-entries"
    freeze_query_draft_proposal_run(
        root=run_root,
        public=public,
        prompt_bytes=prompt,
        dispatch=dispatch,
        raw_response=raw_response,
        proposals=proposals,
        provenance=provenance,
        validation_receipt=receipt,
        typed_proposals=typed,
    )
    (run_root / "extra-dir").mkdir()

    with pytest.raises(ValueError, match="run artifact set mismatch"):
        validate_frozen_query_draft_proposal_run(run_root)

    (run_root / "extra-dir").rmdir()
    try:
        (run_root / "extra-link").symlink_to(run_root / "public.json")
    except OSError:
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(ValueError, match="run artifact set mismatch"):
        validate_frozen_query_draft_proposal_run(run_root)


def test_atomic_freeze_cleans_staging_directory_when_publish_fails(
    tmp_path,
    monkeypatch,
) -> None:
    (
        public,
        prompt,
        dispatch,
        raw_response,
        proposals,
        provenance,
        receipt,
        typed,
    ) = _valid_run_artifacts()
    run_root = tmp_path / "publish-failure"
    original_rename = Path.rename

    def fail_publish(path, target):
        if ".publish-failure.freeze-" in path.name:
            raise OSError("injected publish failure")
        return original_rename(path, target)

    monkeypatch.setattr(Path, "rename", fail_publish)
    with pytest.raises(OSError, match="injected publish failure"):
        freeze_query_draft_proposal_run(
            root=run_root,
            public=public,
            prompt_bytes=prompt,
            dispatch=dispatch,
            raw_response=raw_response,
            proposals=proposals,
            provenance=provenance,
            validation_receipt=receipt,
            typed_proposals=typed,
        )

    assert not run_root.exists()
    assert list(tmp_path.glob(".publish-failure.freeze-*")) == []


def _git(repo_path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", os.fspath(repo_path), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.decode("utf-8").strip()


def _commit(repo_path: Path, message: str) -> str:
    _git(repo_path, "add", ".")
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "Query Proposer Test",
            "GIT_AUTHOR_EMAIL": "query-proposer@example.invalid",
            "GIT_COMMITTER_NAME": "Query Proposer Test",
            "GIT_COMMITTER_EMAIL": "query-proposer@example.invalid",
        }
    )
    subprocess.run(
        ["git", "-C", os.fspath(repo_path), "commit", "-q", "-m", message],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    return _git(repo_path, "rev-parse", "HEAD")


def test_git_history_change_scan_covers_merged_tamper_restore(tmp_path) -> None:
    repo_path = tmp_path / "merge-history"
    subprocess.run(
        ["git", "init", "-q", "-b", "main", os.fspath(repo_path)],
        check=True,
    )
    protected = repo_path / "gate" / "raw.json"
    protected.parent.mkdir(parents=True)
    protected.write_text("frozen\n", encoding="utf-8")
    frozen_commit = _commit(repo_path, "freeze protected path")
    _git(repo_path, "checkout", "-q", "-b", "tamper")
    protected.write_text("tampered\n", encoding="utf-8")
    _commit(repo_path, "tamper protected path")
    protected.write_text("frozen\n", encoding="utf-8")
    _commit(repo_path, "restore protected path")
    _git(repo_path, "checkout", "-q", "main")
    marker = repo_path / "merge-marker.txt"
    marker.write_text("main\n", encoding="utf-8")
    _commit(repo_path, "advance main")
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "Query Proposer Test",
            "GIT_AUTHOR_EMAIL": "query-proposer@example.invalid",
            "GIT_COMMITTER_NAME": "Query Proposer Test",
            "GIT_COMMITTER_EMAIL": "query-proposer@example.invalid",
        }
    )
    subprocess.run(
        [
            "git",
            "-C",
            os.fspath(repo_path),
            "merge",
            "-q",
            "--no-ff",
            "tamper",
            "-m",
            "merge restored branch",
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    final_commit = _git(repo_path, "rev-parse", "HEAD")

    assert query_compiler_v2_proposal_eval._git_path_changed_after(
        repo_path,
        frozen_commit,
        final_commit,
        "gate/raw.json",
    )


def test_extended_history_binds_all_freeze_stages_and_rejects_tampering(
    tmp_path,
) -> None:
    (
        public,
        prompt,
        dispatch,
        raw_response,
        proposals,
        provenance,
        receipt,
        typed,
    ) = _valid_run_artifacts()
    repo_path = tmp_path / "query-proposer-history"
    subprocess.run(
        ["git", "init", "-q", "-b", "main", os.fspath(repo_path)],
        check=True,
    )

    frozen_root = repo_path / "frozen"
    frozen_root.mkdir(parents=True)
    code_files = {
        "query_compiler_v2.py": b"# frozen compiler\n",
        "query_compiler_v2_assessment.py": b"# frozen assessment\n",
        "query_compiler_v2_proposal_eval.py": b"# frozen proposer scorer\n",
    }
    for name, content in code_files.items():
        (frozen_root / name).write_bytes(content)
    gate_root = repo_path / "gate"
    gate_root.mkdir()
    prompt_path = gate_root / "prompt.md"
    prompt_path.write_bytes(prompt)
    preregistration = QueryDraftProposalPreregistrationV1(
        dataset_id=public.dataset_id,
        prompt_path="gate/prompt.md",
        prompt_sha256=hashlib.sha256(prompt).hexdigest(),
        compiler_path="frozen/query_compiler_v2.py",
        compiler_sha256=hashlib.sha256(
            code_files["query_compiler_v2.py"]
        ).hexdigest(),
        assessment_path="frozen/query_compiler_v2_assessment.py",
        assessment_sha256=hashlib.sha256(
            code_files["query_compiler_v2_assessment.py"]
        ).hexdigest(),
        proposer_eval_path="frozen/query_compiler_v2_proposal_eval.py",
        proposer_eval_sha256=hashlib.sha256(
            code_files["query_compiler_v2_proposal_eval.py"]
        ).hexdigest(),
    )
    prereg_path = gate_root / "preregistration.json"
    prereg_path.write_bytes(canonical_json_bytes(preregistration))
    prereg_commit = _commit(repo_path, "freeze preregistration")

    public_path = gate_root / "public.json"
    public_path.write_bytes(canonical_json_bytes(public))
    public_commit = _commit(repo_path, "freeze public")

    raw_paths = {
        "dispatch.json": dispatch,
        "raw-response.json": raw_response,
        "proposals.json": proposals,
        "provenance.json": provenance,
        "validation-receipt.json": receipt,
    }
    for name, value in raw_paths.items():
        (gate_root / name).write_bytes(canonical_json_bytes(value))
    raw_commit = _commit(repo_path, "freeze raw proposal boundary")

    typed_path = gate_root / "typed-proposals.json"
    typed_path.write_bytes(canonical_json_bytes(typed))
    typed_commit = _commit(repo_path, "freeze typed proposals")

    authority_path = gate_root / "authority.json"
    draft_gold_path = gate_root / "draft-gold.json"
    compiler_gold_path = gate_root / "compiler-gold.json"
    authority_path.write_bytes(canonical_json_bytes(_authority()))
    draft_gold_path.write_bytes(canonical_json_bytes(_draft_gold()))
    compiler_gold_path.write_bytes(canonical_json_bytes(_compiler_gold()))
    authority_gold_commit = _commit(repo_path, "freeze authority and gold")

    freeze = QueryDraftProposalFormalFreezeV1(
        dataset_id=public.dataset_id,
        preregistration_commit=prereg_commit,
        public_commit=public_commit,
        raw_commit=raw_commit,
        typed_commit=typed_commit,
        authority_gold_commit=authority_gold_commit,
        preregistration_path="gate/preregistration.json",
        public_path="gate/public.json",
        dispatch_path="gate/dispatch.json",
        raw_response_path="gate/raw-response.json",
        proposals_path="gate/proposals.json",
        provenance_path="gate/provenance.json",
        validation_receipt_path="gate/validation-receipt.json",
        typed_proposals_path="gate/typed-proposals.json",
        authority_path="gate/authority.json",
        draft_gold_path="gate/draft-gold.json",
        compiler_gold_path="gate/compiler-gold.json",
    )

    verified = verify_query_draft_proposal_history(repo_path=repo_path, freeze=freeze)
    assert verified.verified is True
    assert verified.errors == []

    (gate_root / "raw-response.json").write_text("{}\n", encoding="utf-8")
    tampered_commit = _commit(repo_path, "tamper raw response")
    rejected = verify_query_draft_proposal_history(
        repo_path=repo_path,
        freeze=freeze.model_copy(update={"authority_gold_commit": tampered_commit}),
    )
    assert rejected.verified is False
    assert "raw response bytes changed after raw freeze" in rejected.errors

    (gate_root / "raw-response.json").write_bytes(
        canonical_json_bytes(raw_response)
    )
    _commit(repo_path, "restore raw response")
    prompt_path.write_text("tampered prompt\n", encoding="utf-8")
    _commit(repo_path, "tamper prompt")
    prompt_path.write_bytes(prompt)
    _commit(repo_path, "restore prompt")
    proposer_eval_path = frozen_root / "query_compiler_v2_proposal_eval.py"
    proposer_eval_path.write_text("# tampered scorer\n", encoding="utf-8")
    _commit(repo_path, "tamper proposer scorer")
    proposer_eval_path.write_bytes(code_files[proposer_eval_path.name])
    _commit(repo_path, "restore proposer scorer")
    typed_path.write_text("{}\n", encoding="utf-8")
    _commit(repo_path, "tamper typed proposals")
    typed_path.write_bytes(canonical_json_bytes(typed))
    restored_commit = _commit(repo_path, "restore typed proposals")

    restored_rejected = verify_query_draft_proposal_history(
        repo_path=repo_path,
        freeze=freeze.model_copy(
            update={"authority_gold_commit": restored_commit}
        ),
    )
    assert restored_rejected.verified is False
    assert "raw response bytes changed after raw freeze" in restored_rejected.errors
    assert "prompt bytes changed after preregistration" in restored_rejected.errors
    assert (
        "proposer evaluator bytes changed after preregistration"
        in restored_rejected.errors
    )
    assert (
        "typed proposal bytes changed after typed freeze"
        in restored_rejected.errors
    )
