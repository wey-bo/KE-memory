from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tools.natural_memory_benchmark.typed_extractor_l1 import (
    L1ProposalPayload,
    L1ProposalRecord,
    TypedConditionBinding,
    TypedDerivationProvenance,
    TypedEvidenceBinding,
    TypedL1Candidate,
    TypedLifecycleBinding,
    TypedLocalEntity,
    TypedOperationProvenance,
    TypedPredicate,
    TypedRoleBinding,
    TypedScopeBinding,
    TypedTimeBinding,
    prepare_l1_dev_slice,
    run_l1_scoring_file,
    score_l1_proposals,
    validate_l1_dev_slice,
)
from tools.natural_memory_benchmark.io import load_json, sha256_file
from tools.natural_memory_benchmark.authoritative_conformance_runner import (
    build_authoritative_conformance_bundle,
)
from tools.natural_memory_benchmark.typed_extractor_model_run import (
    freeze_l1_model_proposals,
    write_l1_model_dispatch,
)


SOURCE_CONFIG = Path(
    "artifacts/automatic-extraction-assessment/typed-extractor-v2-dev/"
    "source-cases-l1.json"
)
PROMPT = Path(
    "artifacts/automatic-extraction-assessment/typed-extractor-v2-dev/"
    "proposer-prompt-l1.md"
)
BRIDGE_LEDGER = Path(
    "artifacts/automatic-extraction-assessment/bridge-v3/compatibility-ledger.json"
)
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
ISOLATION_CONTEXT = "fresh-agent-no-history-declarative"
V3_L1_OUTPUTS = (
    "authority-l1.json",
    "gold-l1.json",
    "public-l1.json",
    "source-cases-l1.json",
)


def _candidate() -> TypedL1Candidate:
    return TypedL1Candidate(
        kind="task",
        predicate=TypedPredicate(
            surface="请求退回",
            sense="request.return_item",
            canonical_operator="request_return",
        ),
        local_entities=[
            TypedLocalEntity(local_entity_id="entity-01", surface="用户"),
            TypedLocalEntity(local_entity_id="entity-02", surface="平板"),
        ],
        roles=[
            TypedRoleBinding(
                role="requester",
                role_name="请求者",
                local_entity_id="entity-01",
            ),
            TypedRoleBinding(
                role="theme",
                role_name="对象",
                local_entity_id="entity-02",
            ),
        ],
        modality="requested",
        polarity="positive",
        time=TypedTimeBinding(event_time=None, valid_time=None),
        condition_bindings=[
            TypedConditionBinding(
                operator="when",
                value="用户确认执行",
                local_entity_ids=["entity-01"],
            )
        ],
        scope_bindings=[
            TypedScopeBinding(
                operator="applies_to",
                value="订单中的平板",
                local_entity_ids=["entity-02"],
            )
        ],
        derivation=TypedDerivationProvenance(
            method="explicit",
            basis=None,
            evidence_ids=["evidence-01"],
        ),
        evidence_bindings=[
            TypedEvidenceBinding(evidence_id="evidence-01", speaker="user")
        ],
        lifecycle=TypedLifecycleBinding(
            lifecycle="active",
            replacement_candidate_ref=None,
            replaces_candidate_refs=[],
            supersedes_candidate_refs=[],
            conflicts_with_candidate_refs=[],
        ),
        operation_provenance=TypedOperationProvenance(
            confirmed_by_operation_refs=[],
            added_by_operation_refs=[],
        ),
    )


def test_typed_l1_candidate_requires_contiguous_local_ids_and_closed_refs() -> None:
    candidate = _candidate()

    assert [item.local_entity_id for item in candidate.local_entities] == [
        "entity-01",
        "entity-02",
    ]

    payload = candidate.model_dump(mode="json")
    payload["local_entities"][1]["local_entity_id"] = "entity-03"
    with pytest.raises(ValidationError, match="contiguous"):
        TypedL1Candidate.model_validate(payload)

    payload = candidate.model_dump(mode="json")
    payload["roles"][0]["local_entity_id"] = "entity-99"
    with pytest.raises(ValidationError, match="unknown local entity"):
        TypedL1Candidate.model_validate(payload)

    payload = candidate.model_dump(mode="json")
    payload["condition_bindings"][0]["local_entity_ids"] = ["entity-99"]
    with pytest.raises(ValidationError, match="unknown local entity"):
        TypedL1Candidate.model_validate(payload)


def test_typed_l1_candidate_closes_derivation_and_evidence_bindings() -> None:
    payload = _candidate().model_dump(mode="json")
    payload["derivation"]["evidence_ids"] = ["evidence-unknown"]

    with pytest.raises(ValidationError, match="derivation evidence"):
        TypedL1Candidate.model_validate(payload)

    payload = _candidate().model_dump(mode="json")
    payload["evidence_bindings"].append(
        {"evidence_id": "evidence-01", "speaker": "assistant"}
    )
    with pytest.raises(ValidationError, match="duplicate evidence"):
        TypedL1Candidate.model_validate(payload)


def test_proposal_decision_union_requires_and_forbids_typed_candidate() -> None:
    emitted = L1ProposalRecord(
        case_id="case-0123456789abcdef",
        candidate_ref="candidate-0123456789abcdef",
        decision="emit_l1",
        confidence=0.9,
        typed_candidate=_candidate(),
        reason_code="typed_from_exact_evidence",
    )
    assert emitted.typed_candidate is not None

    non_emission = emitted.model_dump(mode="json")
    non_emission["decision"] = "abstain"
    with pytest.raises(ValidationError, match="must not include typed_candidate"):
        L1ProposalRecord.model_validate(non_emission)

    missing_candidate = emitted.model_dump(mode="json")
    missing_candidate["typed_candidate"] = None
    with pytest.raises(ValidationError, match="requires typed_candidate"):
        L1ProposalRecord.model_validate(missing_candidate)


def test_proposal_payload_requires_unique_cases_and_consistent_count() -> None:
    record = L1ProposalRecord(
        case_id="case-0123456789abcdef",
        candidate_ref="candidate-0123456789abcdef",
        decision="emit_l1",
        confidence=0.9,
        typed_candidate=_candidate(),
        reason_code="typed_from_exact_evidence",
    )
    payload = {
        "schema_version": "typed-extractor-l1-proposals-v1",
        "dataset_id": "typed-extractor-l1-dev-v1",
        "run_id": "run-test",
        "proposer_id": "test-proposer",
        "proposer_version": "1",
        "case_count": 1,
        "proposals": [record.model_dump(mode="json")],
    }
    assert L1ProposalPayload.model_validate(payload).case_count == 1

    duplicate = copy.deepcopy(payload)
    duplicate["case_count"] = 2
    duplicate["proposals"].append(copy.deepcopy(duplicate["proposals"][0]))
    with pytest.raises(ValidationError, match="duplicate proposal case"):
        L1ProposalPayload.model_validate(duplicate)

    wrong_count = copy.deepcopy(payload)
    wrong_count["case_count"] = 2
    with pytest.raises(ValidationError, match="case count mismatch"):
        L1ProposalPayload.model_validate(wrong_count)


def _prepare_slice(root: Path) -> dict:
    return prepare_l1_dev_slice(
        source_config_path=SOURCE_CONFIG,
        prompt_path=PROMPT,
        bridge_ledger_path=BRIDGE_LEDGER,
        source_path=SOURCE,
        turn_manifest_path=TURN_MANIFEST,
        dialogue_manifest_path=DIALOGUE_MANIFEST,
        final_knowledge_path=FINAL_KNOWLEDGE,
        run_path=RUN,
        source_segments_path=SOURCE_SEGMENTS,
        output_root=root,
    )


def test_prepare_l1_dev_slice_is_opaque_separated_and_deterministic(
    tmp_path: Path,
) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"

    first = _prepare_slice(first_root)
    second = _prepare_slice(second_root)

    assert first == second
    assert first["status"] == "valid"
    assert first["case_count"] == 12
    assert first["kind_coverage"] == [
        "attribute",
        "event",
        "preference",
        "state",
        "task",
    ]
    assert first["source_status_coverage"] == [
        "agent_generated",
        "tool_observed",
        "user_reported",
    ]
    assert first["projection_status_coverage"] == [
        "active",
        "corrected",
        "superseded",
    ]
    assert first["non_explicit_derivation_count"] >= 2
    assert first["condition_emit_count"] >= 1
    assert first["scope_emit_count"] >= 1
    assert first["operation_emit_count"] >= 1
    assert first["resolved_time_emit_count"] >= 1
    assert first["unresolved_time_emit_count"] >= 1
    assert first["abstain_count"] >= 2
    assert first["no_memory_count"] >= 1

    formal_names = (
        "public-l1.json",
        "authority-l1.json",
        "gold-l1.json",
        "manifest-l1.json",
    )
    for name in formal_names:
        assert (first_root / name).read_bytes() == (second_root / name).read_bytes()
        assert first_root.joinpath(name).stat().st_mode & 0o777 == 0o444

    public_bytes = (first_root / "public-l1.json").read_bytes()
    source_config = load_json(SOURCE_CONFIG)
    for case in source_config["cases"]:
        assert case["knowledge_id"].encode() not in public_bytes
    assert b"expected_decision" not in public_bytes
    assert b"expected_typed_candidate" not in public_bytes

    public = load_json(first_root / "public-l1.json")
    authority = load_json(first_root / "authority-l1.json")
    gold = load_json(first_root / "gold-l1.json")
    public_ids = {item["case_id"] for item in public["cases"]}
    assert public_ids == {item["case_id"] for item in authority["cases"]}
    assert public_ids == {item["case_id"] for item in gold["items"]}
    assert all(item["case_id"].startswith("case-") for item in public["cases"])
    assert all(
        item["candidate_ref"].startswith("candidate-") for item in public["cases"]
    )


def test_source_config_can_publish_global_canonical_policy_without_case_mapping(
    tmp_path: Path,
) -> None:
    source = load_json(SOURCE_CONFIG)
    source["dataset_id"] = "typed-extractor-l1-dev-policy-test"
    source["public_vocabulary"] = {
        "canonical_operators": ["request_return"],
        "predicate_senses": ["commerce.return_request"],
        "role_bindings": ["requester|请求者", "theme|退回对象"],
        "time_policy": [
            "absolute_calendar_date_to_iso_8601",
            "unresolved_deictic_time_to_null",
        ],
    }
    source_path = tmp_path / "source-with-policy.json"
    source_path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
    source_path.chmod(0o444)
    root = tmp_path / "slice"

    prepare_l1_dev_slice(
        source_config_path=source_path,
        prompt_path=PROMPT,
        bridge_ledger_path=BRIDGE_LEDGER,
        source_path=SOURCE,
        turn_manifest_path=TURN_MANIFEST,
        dialogue_manifest_path=DIALOGUE_MANIFEST,
        final_knowledge_path=FINAL_KNOWLEDGE,
        run_path=RUN,
        source_segments_path=SOURCE_SEGMENTS,
        output_root=root,
    )

    public = load_json(root / "public-l1.json")
    assert public["allowed_vocabulary"]["canonical_operators"] == [
        "request_return"
    ]
    assert public["allowed_vocabulary"]["predicate_senses"] == [
        "commerce.return_request"
    ]
    assert public["allowed_vocabulary"]["role_bindings"] == [
        "requester|请求者",
        "theme|退回对象",
    ]
    assert "expected_typed_candidate" not in (root / "public-l1.json").read_text(
        encoding="utf-8"
    )


def test_validate_l1_dev_slice_binds_bridge_v3_and_read_only_inputs(
    tmp_path: Path,
) -> None:
    root = tmp_path / "slice"
    _prepare_slice(root)

    result = validate_l1_dev_slice(
        source_config_path=SOURCE_CONFIG,
        prompt_path=PROMPT,
        bridge_ledger_path=BRIDGE_LEDGER,
        source_path=SOURCE,
        turn_manifest_path=TURN_MANIFEST,
        dialogue_manifest_path=DIALOGUE_MANIFEST,
        final_knowledge_path=FINAL_KNOWLEDGE,
        run_path=RUN,
        source_segments_path=SOURCE_SEGMENTS,
        root=root,
    )

    assert result["status"] == "valid"
    manifest = load_json(root / "manifest-l1.json")
    assert manifest["input_sha256"]["bridge_ledger"] == sha256_file(BRIDGE_LEDGER)
    assert manifest["input_sha256"]["source_config"] == sha256_file(SOURCE_CONFIG)
    assert manifest["input_sha256"]["prompt"] == sha256_file(PROMPT)
    assert manifest["output_sha256"] == {
        name: sha256_file(root / name)
        for name in ("authority-l1.json", "gold-l1.json", "public-l1.json")
    }


def _proposal_payload(root: Path) -> dict:
    public = load_json(root / "public-l1.json")
    gold = load_json(root / "gold-l1.json")
    gold_by_id = {item["case_id"]: item for item in gold["items"]}
    return {
        "schema_version": "typed-extractor-l1-proposals-v1",
        "dataset_id": public["dataset_id"],
        "run_id": "run-test-typed-l1-score",
        "proposer_id": "test-proposer",
        "proposer_version": "1",
        "case_count": public["case_count"],
        "proposals": [
            {
                "case_id": case["case_id"],
                "candidate_ref": case["candidate_ref"],
                "decision": gold_by_id[case["case_id"]]["expected_decision"],
                "confidence": 0.95,
                "typed_candidate": copy.deepcopy(
                    gold_by_id[case["case_id"]]["expected_typed_candidate"]
                ),
                "reason_code": "dev_semantic_judgment",
            }
            for case in public["cases"]
        ],
    }


def _freeze_proposals(root: Path, payload: dict, run_name: str) -> tuple[Path, Path]:
    run_root = root / run_name
    dispatch_path = run_root / "dispatch.json"
    write_l1_model_dispatch(
        root / "public-l1.json",
        PROMPT,
        dispatch_path,
        run_id=payload["run_id"],
        proposer_id=payload["proposer_id"],
        proposer_version=payload["proposer_version"],
        requested_model="test-model-alias",
        isolation_context=ISOLATION_CONTEXT,
    )
    staged = root / f"{run_name}-staged.json"
    staged.write_text(
        __import__("json").dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    proposals_path = run_root / "proposals.json"
    provenance_path = run_root / "provenance.json"
    raw_response_path = run_root / "raw-response.json"
    raw_response_path.write_text(
        __import__("json").dumps(
            {
                "model": "resolved-test-model",
                "choices": [
                    {
                        "message": {
                            "content": staged.read_text(encoding="utf-8")
                        }
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    raw_response_path.chmod(0o444)
    freeze_l1_model_proposals(
        root / "public-l1.json",
        staged,
        proposals_path,
        provenance_path,
        prompt_path=PROMPT,
        dispatch_path=dispatch_path,
        raw_response_path=raw_response_path,
        isolation_context=ISOLATION_CONTEXT,
    )
    return proposals_path, provenance_path


def _guard_bundle():
    return build_authoritative_conformance_bundle(
        GUARD_ROOT,
        "slice-v1",
        GUARD_RESULTS,
    )


def _bind_v3_outputs(root: Path) -> None:
    source_path = root / "source-cases-l1.json"
    if source_path.exists():
        source_path.chmod(0o644)
    source_path.write_bytes(SOURCE_CONFIG.read_bytes())
    source_path.chmod(0o444)
    manifest_path = root / "manifest-l1.json"
    manifest_path.chmod(0o644)
    manifest = load_json(manifest_path)
    manifest["output_sha256"] = {
        name: sha256_file(root / name) for name in V3_L1_OUTPUTS
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    manifest_path.chmod(0o444)


def test_score_l1_proposals_separates_raw_quality_and_gate_safety(
    tmp_path: Path,
) -> None:
    root = tmp_path / "slice"
    _prepare_slice(root)
    proposals_path, provenance_path = _freeze_proposals(
        root,
        _proposal_payload(root),
        "exact",
    )

    score = score_l1_proposals(
        root,
        proposals_path,
        provenance_path,
        guard_bundle=_guard_bundle(),
    )

    assert score.raw_proposer_quality_ready is True
    assert score.deterministic_gate_safety_ready is True
    assert score.metrics["raw_decision_accuracy"] == 1.0
    assert score.metrics["gated_decision_accuracy"] == 1.0
    assert score.metrics["exact_evidence_rate"] == 1.0
    assert score.metrics["raw_critical_false_emission_count"] == 0
    assert score.metrics["deterministic_critical_false_materialization_count"] == 0
    assert score.metrics["gate_intervention_count"] == 0
    assert score.guard_state["unchanged"] is True
    assert score.guard_state["before_fingerprint"] == score.guard_state[
        "after_fingerprint"
    ]
    assert score.claim_boundary["automatic_l1_write_count"] == 0
    assert score.claim_boundary["automatic_l2_write_count"] == 0
    assert score.claim_boundary["automatic_identity_write_count"] == 0
    assert score.claim_boundary["automatic_membership_write_count"] == 0


def test_l1_scorer_accepts_explicit_v3_manifest_outputs(tmp_path: Path) -> None:
    root = tmp_path / "slice"
    _prepare_slice(root)
    proposals_path, provenance_path = _freeze_proposals(
        root,
        _proposal_payload(root),
        "v3",
    )

    legacy = score_l1_proposals(
        root,
        proposals_path,
        provenance_path,
        guard_bundle=_guard_bundle(),
    )
    _bind_v3_outputs(root)
    v3 = score_l1_proposals(
        root,
        proposals_path,
        provenance_path,
        guard_bundle=_guard_bundle(),
        manifest_output_names=V3_L1_OUTPUTS,
    )
    result = run_l1_scoring_file(
        root,
        proposals_path,
        provenance_path,
        guard_root=GUARD_ROOT,
        guard_slice_id="slice-v1",
        guard_results_path=GUARD_RESULTS,
        score_path=root / "v3-score.json",
        report_path=root / "v3-report.md",
        error_analysis_path=root / "v3-errors.json",
        manifest_output_names=V3_L1_OUTPUTS,
    )

    assert legacy.metrics == v3.metrics
    assert result["metrics"] == v3.metrics


@pytest.mark.parametrize(
    "manifest_output_names",
    [
        (*V3_L1_OUTPUTS, "extra-l1.json"),
        (*V3_L1_OUTPUTS, "source-cases-l1.json"),
        (*V3_L1_OUTPUTS[:-1], "nested/source-cases-l1.json"),
    ],
)
def test_l1_scorer_rejects_invalid_explicit_manifest_output_names(
    tmp_path: Path,
    manifest_output_names: tuple[str, ...],
) -> None:
    root = tmp_path / "slice"
    _prepare_slice(root)
    proposals_path, provenance_path = _freeze_proposals(root, _proposal_payload(root), "v3")
    _bind_v3_outputs(root)

    with pytest.raises(ValueError, match="manifest output names"):
        score_l1_proposals(
            root,
            proposals_path,
            provenance_path,
            guard_bundle=_guard_bundle(),
            manifest_output_names=manifest_output_names,
        )


def test_l1_scorer_rejects_missing_or_drifted_v3_source_hash(tmp_path: Path) -> None:
    root = tmp_path / "slice"
    _prepare_slice(root)
    proposals_path, provenance_path = _freeze_proposals(root, _proposal_payload(root), "v3")
    source_path = root / "source-cases-l1.json"
    source_path.write_bytes(SOURCE_CONFIG.read_bytes())
    source_path.chmod(0o444)

    with pytest.raises(ValueError, match="manifest does not bind scoring inputs"):
        score_l1_proposals(
            root,
            proposals_path,
            provenance_path,
            guard_bundle=_guard_bundle(),
            manifest_output_names=V3_L1_OUTPUTS,
        )

    _bind_v3_outputs(root)
    source_path.chmod(0o644)
    source_path.write_text("source hash drift", encoding="utf-8")
    source_path.chmod(0o444)

    with pytest.raises(ValueError, match="manifest does not bind scoring inputs"):
        score_l1_proposals(
            root,
            proposals_path,
            provenance_path,
            guard_bundle=_guard_bundle(),
            manifest_output_names=V3_L1_OUTPUTS,
        )


def test_gate_does_not_repair_semantically_wrong_predicate(tmp_path: Path) -> None:
    root = tmp_path / "slice"
    _prepare_slice(root)
    payload = _proposal_payload(root)
    emit = next(item for item in payload["proposals"] if item["decision"] == "emit_l1")
    emit["typed_candidate"]["predicate"]["sense"] = "wrong.semantic_sense"
    proposals_path, provenance_path = _freeze_proposals(root, payload, "wrong-predicate")

    score = score_l1_proposals(
        root,
        proposals_path,
        provenance_path,
        guard_bundle=_guard_bundle(),
    )

    case = next(item for item in score.cases if item.case_id == emit["case_id"])
    assert case.raw_decision == "emit_l1"
    assert case.gated_decision == "emit_l1"
    assert case.gate_reasons == []
    assert "predicate_or_operator_error" in case.raw_errors
    assert score.metrics["predicate_or_operator_accuracy"] < 1.0


def test_raw_false_emission_is_visible_even_when_gate_abstains(
    tmp_path: Path,
) -> None:
    root = tmp_path / "slice"
    _prepare_slice(root)
    payload = _proposal_payload(root)
    public = load_json(root / "public-l1.json")
    gold = load_json(root / "gold-l1.json")
    authority = load_json(root / "authority-l1.json")
    gold_by_id = {item["case_id"]: item for item in gold["items"]}
    authority_by_id = {item["case_id"]: item for item in authority["cases"]}
    target = next(
        item
        for item in payload["proposals"]
        if gold_by_id[item["case_id"]]["expected_decision"] == "abstain"
    )
    template = copy.deepcopy(
        next(
            item["typed_candidate"]
            for item in payload["proposals"]
            if item["decision"] == "emit_l1"
        )
    )
    public_case = next(item for item in public["cases"] if item["case_id"] == target["case_id"])
    auth_case = authority_by_id[target["case_id"]]
    template["evidence_bindings"] = copy.deepcopy(auth_case["required_evidence_bindings"])
    template["derivation"] = copy.deepcopy(auth_case["required_derivation"])
    template["lifecycle"] = copy.deepcopy(public_case["untyped_candidate"]["lifecycle_links"])
    template["operation_provenance"] = copy.deepcopy(
        public_case["untyped_candidate"]["operation_provenance"]
    )
    template["condition_bindings"] = []
    template["scope_bindings"] = []
    target["decision"] = "emit_l1"
    target["typed_candidate"] = template
    proposals_path, provenance_path = _freeze_proposals(root, payload, "false-emission")

    score = score_l1_proposals(
        root,
        proposals_path,
        provenance_path,
        guard_bundle=_guard_bundle(),
    )

    case = next(item for item in score.cases if item.case_id == target["case_id"])
    assert case.raw_decision == "emit_l1"
    assert case.gated_decision == "abstain"
    assert "false_emission" in case.raw_errors
    assert "emission_not_authorized" in case.gate_reasons
    assert score.raw_proposer_quality_ready is False
    assert score.deterministic_gate_safety_ready is True
    assert score.metrics["raw_critical_false_emission_count"] == 1
    assert score.metrics["deterministic_critical_false_materialization_count"] == 0


def test_gate_rejects_hallucinated_typed_time_without_repair(tmp_path: Path) -> None:
    root = tmp_path / "slice"
    _prepare_slice(root)
    payload = _proposal_payload(root)
    target = next(
        item
        for item in payload["proposals"]
        if item["typed_candidate"]
        and item["typed_candidate"]["time"]["valid_time"] == "2024-05-02"
    )
    target["typed_candidate"]["time"]["valid_time"] = "2024-05-03"
    proposals_path, provenance_path = _freeze_proposals(root, payload, "wrong-time")

    score = score_l1_proposals(
        root,
        proposals_path,
        provenance_path,
        guard_bundle=_guard_bundle(),
    )

    case = next(item for item in score.cases if item.case_id == target["case_id"])
    assert case.raw_decision == "emit_l1"
    assert case.gated_decision == "abstain"
    assert "time_error" in case.raw_errors
    assert "valid_time_not_authorized" in case.gate_reasons


def test_scoring_runner_writes_immutable_separated_outputs(tmp_path: Path) -> None:
    root = tmp_path / "slice"
    _prepare_slice(root)
    proposals_path, provenance_path = _freeze_proposals(
        root,
        _proposal_payload(root),
        "formal",
    )
    run_root = root / "formal"
    score_path = run_root / "score.json"
    report_path = run_root / "report.md"
    errors_path = run_root / "error-analysis.json"

    first = run_l1_scoring_file(
        root,
        proposals_path,
        provenance_path,
        guard_root=GUARD_ROOT,
        guard_slice_id="slice-v1",
        guard_results_path=GUARD_RESULTS,
        score_path=score_path,
        report_path=report_path,
        error_analysis_path=errors_path,
    )
    second = run_l1_scoring_file(
        root,
        proposals_path,
        provenance_path,
        guard_root=GUARD_ROOT,
        guard_slice_id="slice-v1",
        guard_results_path=GUARD_RESULTS,
        score_path=score_path,
        report_path=report_path,
        error_analysis_path=errors_path,
    )

    assert first == second
    assert first["raw_proposer_quality_ready"] is True
    assert first["deterministic_gate_safety_ready"] is True
    assert "## Raw proposer quality" in report_path.read_text(encoding="utf-8")
    assert "## Deterministic gate safety" in report_path.read_text(encoding="utf-8")
    for path in (score_path, report_path, errors_path):
        assert path.stat().st_mode & 0o777 == 0o444
