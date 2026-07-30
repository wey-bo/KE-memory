from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tools.natural_memory_benchmark.typed_extractor_l1 import (
    TypedEvidenceBinding,
    TypedLocalEntity,
    TypedPredicate,
    TypedRoleBinding,
    TypedTimeBinding,
)
from tools.natural_memory_benchmark.typed_extractor_l2 import (
    L2ProposalRecord,
    TypedL1SupportCandidate,
    TypedL2Abstraction,
    TypedL2Candidate,
    TypedL2Closure,
    TypedL2StructuredClaim,
    prepare_l2_dev_slice,
    run_l2_scoring_file,
    score_l2_proposals,
    validate_l2_dev_slice,
)
from tools.natural_memory_benchmark.io import load_json, sha256_file
from tools.natural_memory_benchmark.authoritative_conformance_runner import (
    build_authoritative_conformance_bundle,
)
from tools.natural_memory_benchmark.typed_extractor_l2_model_run import (
    freeze_l2_model_proposals,
    write_l2_model_dispatch,
)


ROOT = Path(
    "artifacts/automatic-extraction-assessment/typed-extractor-v2-l2-dev"
)
SOURCE_CONFIG = ROOT / "source-cases-l2.json"
PROMPT = ROOT / "proposer-prompt-l2.md"
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
ISOLATION = "fresh-agent-no-history-declarative"
V3_L2_OUTPUTS = (
    "authority-l2.json",
    "gold-l2.json",
    "public-l2.json",
    "source-cases-l2.json",
)
V3_L2_THRESHOLDS = {
    "proposal_coverage": 1.0,
    "schema_valid_rate": 1.0,
    "raw_decision_accuracy": 1.0,
    "raw_abstention_f1": 1.0,
    "exact_evidence_rate": 1.0,
    "support_id_accuracy": 1.0,
    "kind_accuracy": 1.0,
    "structured_claim_accuracy": 1.0,
    "abstraction_accuracy": 1.0,
    "closure_accuracy": 1.0,
    "source_coverage_accuracy": 1.0,
    "summary_accuracy": 1.0,
}


def _support(ref: str, turn_ref: str, evidence_id: str) -> TypedL1SupportCandidate:
    return TypedL1SupportCandidate(
        support_ref=ref,
        source_turn_ref=turn_ref,
        source_session_ref="session-0123456789abcdef",
        kind="task",
        predicate=TypedPredicate(
            surface="请求",
            sense="request.example",
            canonical_operator="request_example",
        ),
        local_entities=[
            TypedLocalEntity(local_entity_id="entity-01", surface="用户"),
            TypedLocalEntity(local_entity_id="entity-02", surface="例子"),
        ],
        roles=[
            TypedRoleBinding(
                role="requester", role_name="请求者", local_entity_id="entity-01"
            ),
            TypedRoleBinding(
                role="theme", role_name="请求内容", local_entity_id="entity-02"
            ),
        ],
        modality="requested",
        polarity="positive",
        time=TypedTimeBinding(event_time=None, valid_time=None),
        evidence_bindings=[TypedEvidenceBinding(evidence_id=evidence_id, speaker="user")],
    )


def _claim(*support_refs: str) -> TypedL2StructuredClaim:
    return TypedL2StructuredClaim(
        claim_ref="claim-01",
        predicate=TypedPredicate(
            surface="请求函数使用例子",
            sense="software.request_function_example",
            canonical_operator="request_function_example",
        ),
        local_entities=[
            TypedLocalEntity(local_entity_id="entity-01", surface="用户"),
            TypedLocalEntity(
                local_entity_id="entity-02", surface="make_hyperlink 函数的使用例子"
            ),
        ],
        roles=[
            TypedRoleBinding(
                role="requester", role_name="请求者", local_entity_id="entity-01"
            ),
            TypedRoleBinding(
                role="theme", role_name="请求内容", local_entity_id="entity-02"
            ),
        ],
        modality="requested",
        polarity="positive",
        time=TypedTimeBinding(event_time=None, valid_time=None),
        supporting_l1_refs=list(support_refs),
    )


def _candidate() -> TypedL2Candidate:
    support_1 = _support(
        "support-0123456789abcdef",
        "turn-0123456789abcdef",
        "evidence-one",
    )
    support_2 = _support(
        "support-fedcba9876543210",
        "turn-fedcba9876543210",
        "evidence-two",
    )
    return TypedL2Candidate(
        kind="task",
        summary="用户请求 make_hyperlink 函数的使用例子。",
        supporting_l1_refs=[support_1.support_ref, support_2.support_ref],
        structured_claims=[_claim(support_1.support_ref, support_2.support_ref)],
        abstraction=TypedL2Abstraction(
            method="coreference_resolution",
            basis="后续的例子请求回指前一轮的函数。",
        ),
        closure=TypedL2Closure(
            pattern="multi_evidence_set",
            required_support_refs=[support_1.support_ref, support_2.support_ref],
            optional_support_refs=[],
        ),
        source_turn_refs=[support_1.source_turn_ref, support_2.source_turn_ref],
        source_session_refs=[support_1.source_session_ref],
        evidence_bindings=[
            *support_1.evidence_bindings,
            *support_2.evidence_bindings,
        ],
        lifecycle="candidate",
    )


def test_l2_emit_requires_complete_closed_candidate() -> None:
    candidate = _candidate()
    proposal = L2ProposalRecord(
        case_id="case-0123456789abcdef",
        candidate_ref="candidate-0123456789abcdef",
        decision="emit_l2",
        confidence=1.0,
        typed_candidate=candidate,
        reason_code="complete_cross_turn_task",
    )
    assert proposal.typed_candidate == candidate


def test_l2_abstain_forbids_typed_candidate() -> None:
    with pytest.raises(ValidationError, match="non-emission"):
        L2ProposalRecord(
            case_id="case-0123456789abcdef",
            candidate_ref="candidate-0123456789abcdef",
            decision="abstain",
            confidence=0.5,
            typed_candidate=_candidate(),
            reason_code="incomplete_support",
        )


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("supporting_l1_refs", [], "at least 1"),
        (
            "structured_claims",
            [
                _claim(
                    "support-0123456789abcdef",
                    "support-aaaaaaaaaaaaaaaa",
                )
            ],
            "unknown support",
        ),
        (
            "closure",
            TypedL2Closure(
                pattern="multi_evidence_set",
                required_support_refs=["support-aaaaaaaaaaaaaaaa"],
                optional_support_refs=[],
            ),
            "unknown support",
        ),
        (
            "closure",
            TypedL2Closure(
                pattern="multi_evidence_set",
                required_support_refs=["support-0123456789abcdef"],
                optional_support_refs=[],
            ),
            "claim support",
        ),
        ("source_session_refs", [], "at least 1"),
    ],
)
def test_l2_candidate_rejects_incomplete_closure(
    field: str, value: object, match: str
) -> None:
    payload = _candidate().model_dump(mode="json")
    payload[field] = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    with pytest.raises(ValidationError, match=match):
        TypedL2Candidate.model_validate(payload)


def test_l2_candidate_does_not_echo_public_support_pack() -> None:
    assert "supporting_l1_candidates" not in _candidate().model_dump(mode="json")


def test_l2_claim_requires_contiguous_local_entity_ids() -> None:
    payload = _claim("support-0123456789abcdef").model_dump(mode="json")
    payload["local_entities"][0]["local_entity_id"] = "entity-02"
    with pytest.raises(ValidationError, match="contiguous"):
        TypedL2StructuredClaim.model_validate(payload)


def test_l2_transformation_claim_requires_distinct_theme_and_target() -> None:
    payload = _claim("support-0123456789abcdef").model_dump(mode="json")
    payload["predicate"] = {
        "surface": "请求改成",
        "sense": "performance.transform_goals_smart",
        "canonical_operator": "transform_performance_goals_smart",
    }
    payload["roles"].append(
        {
            "role": "target_format",
            "role_name": "目标格式",
            "local_entity_id": "entity-02",
        }
    )
    with pytest.raises(ValidationError, match="distinct local entities"):
        TypedL2StructuredClaim.model_validate(payload)


def test_l2_candidate_rejects_unused_top_level_support() -> None:
    payload = _candidate().model_dump(mode="json")
    payload["supporting_l1_refs"].append("support-1111111111111111")
    with pytest.raises(ValidationError, match="every L1 support"):
        TypedL2Candidate.model_validate(payload)


@pytest.mark.parametrize(
    "claim_refs",
    [
        ["claim-01", "claim-01"],
        ["claim-02"],
    ],
)
def test_l2_candidate_requires_unique_contiguous_claim_refs(
    claim_refs: list[str],
) -> None:
    payload = _candidate().model_dump(mode="json")
    base_claim = payload["structured_claims"][0]
    payload["structured_claims"] = [
        {**copy.deepcopy(base_claim), "claim_ref": claim_ref}
        for claim_ref in claim_refs
    ]
    with pytest.raises(ValidationError, match="claim refs must be contiguous"):
        TypedL2Candidate.model_validate(payload)


def _prepare(root: Path) -> dict[str, object]:
    return prepare_l2_dev_slice(
        source_config_path=SOURCE_CONFIG,
        prompt_path=PROMPT,
        bridge_ledger_path=BRIDGE_LEDGER,
        source_path=SOURCE,
        turn_manifest_path=TURN_MANIFEST,
        dialogue_manifest_path=DIALOGUE_MANIFEST,
        final_knowledge_path=FINAL_KNOWLEDGE,
        run_path=RUN,
        source_segments_path=SOURCE_SEGMENTS,
        l1_qualification_root=Path(
            "artifacts/automatic-extraction-assessment/typed-extractor-v2-dev-v3"
        ),
        output_root=root,
    )


def test_prepare_l2_slice_has_required_distribution_and_separation(
    tmp_path: Path,
) -> None:
    output = tmp_path / "slice"
    result = _prepare(output)
    assert result == {
        "status": "valid",
        "case_count": 6,
        "emit_count": 4,
        "abstain_count": 2,
        "closure_patterns": ["multi_evidence_set", "update_supersession"],
        "abstraction_methods": [
            "coreference_resolution",
            "lifecycle_resolution",
            "task_composition",
        ],
    }
    public = load_json(output / "public-l2.json")
    authority = load_json(output / "authority-l2.json")
    gold = load_json(output / "gold-l2.json")
    assert public["case_count"] == authority["case_count"] == gold["case_count"] == 6
    assert sum(item["expected_decision"] == "emit_l2" for item in gold["items"]) == 4
    assert sum(item["expected_decision"] == "abstain" for item in gold["items"]) == 2
    public_text = (output / "public-l2.json").read_text(encoding="utf-8")
    for private_field in (
        "private_case_id",
        "knowledge_id",
        "expected_decision",
        "expected_typed_candidate",
        "emission_allowed",
    ):
        assert private_field not in public_text
    for case in public["cases"]:
        assert len(case["typed_l1_support_pack"]) >= 2
        assert len(case["source_turns"]) >= 2
        assert all(item["support_ref"].startswith("support-") for item in case["typed_l1_support_pack"])


def test_l2_public_ids_are_opaque_and_outcome_neutral(tmp_path: Path) -> None:
    output = tmp_path / "slice"
    _prepare(output)
    public = load_json(output / "public-l2.json")
    forbidden = {
        "emit",
        "abstain",
        "gold",
        "unsupported",
        "incomplete",
        "correct",
        "false",
    }
    identifiers = [
        value
        for case in public["cases"]
        for value in [
            case["case_id"],
            case["candidate_ref"],
            case["source_session_ref"],
            *(turn["source_turn_ref"] for turn in case["source_turns"]),
            *(support["support_ref"] for support in case["typed_l1_support_pack"]),
        ]
    ]
    assert not any(token in value.lower() for token in forbidden for value in identifiers)


def test_validate_l2_slice_replays_byte_identically(tmp_path: Path) -> None:
    output = tmp_path / "slice"
    expected = _prepare(output)
    actual = validate_l2_dev_slice(
        source_config_path=SOURCE_CONFIG,
        prompt_path=PROMPT,
        bridge_ledger_path=BRIDGE_LEDGER,
        source_path=SOURCE,
        turn_manifest_path=TURN_MANIFEST,
        dialogue_manifest_path=DIALOGUE_MANIFEST,
        final_knowledge_path=FINAL_KNOWLEDGE,
        run_path=RUN,
        source_segments_path=SOURCE_SEGMENTS,
        l1_qualification_root=Path(
            "artifacts/automatic-extraction-assessment/typed-extractor-v2-dev-v3"
        ),
        root=output,
    )
    assert actual == expected


def test_validate_l2_slice_rejects_manifest_threshold_drift(tmp_path: Path) -> None:
    output = tmp_path / "slice"
    _prepare(output)
    manifest_path = output / "manifest-l2.json"
    manifest_path.chmod(0o644)
    manifest = load_json(manifest_path)
    manifest["thresholds"]["raw_decision_accuracy"] = 0.0
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    manifest_path.chmod(0o444)

    with pytest.raises(ValueError, match="typed L2 manifest drift"):
        validate_l2_dev_slice(
            source_config_path=SOURCE_CONFIG,
            prompt_path=PROMPT,
            bridge_ledger_path=BRIDGE_LEDGER,
            source_path=SOURCE,
            turn_manifest_path=TURN_MANIFEST,
            dialogue_manifest_path=DIALOGUE_MANIFEST,
            final_knowledge_path=FINAL_KNOWLEDGE,
            run_path=RUN,
            source_segments_path=SOURCE_SEGMENTS,
            l1_qualification_root=Path(
                "artifacts/automatic-extraction-assessment/typed-extractor-v2-dev-v3"
            ),
            root=output,
        )


def _freeze_from_gold(
    root: Path,
    run_root: Path,
    *,
    false_emit: bool = False,
    reverse_evidence: bool = False,
    rewrite_abstraction_basis: bool = False,
) -> None:
    run_id = "run-test-l2-score"
    proposer_id = "test-proposer"
    proposer_version = "test-v1"
    dispatch = run_root / "dispatch.json"
    write_l2_model_dispatch(
        root / "public-l2.json",
        PROMPT,
        dispatch,
        run_id=run_id,
        proposer_id=proposer_id,
        proposer_version=proposer_version,
        requested_model="test-model-alias",
        isolation_context=ISOLATION,
    )
    gold = load_json(root / "gold-l2.json")
    public = load_json(root / "public-l2.json")
    proposals = []
    for item in gold["items"]:
        typed = copy.deepcopy(item["expected_typed_candidate"])
        decision = item["expected_decision"]
        if typed is not None and reverse_evidence:
            typed["evidence_bindings"] = list(reversed(typed["evidence_bindings"]))
        if typed is not None and rewrite_abstraction_basis:
            typed["abstraction"]["basis"] = (
                "Equivalent public-only explanation of the selected abstraction."
            )
        if false_emit and decision == "abstain":
            case = next(case for case in public["cases"] if case["case_id"] == item["case_id"])
            supports = case["typed_l1_support_pack"]
            first = supports[0]
            typed = {
                "kind": "task",
                "summary": case["untyped_candidate"]["statement"],
                "supporting_l1_refs": [support["support_ref"] for support in supports],
                "structured_claims": [{
                    "claim_ref": "claim-01",
                    "predicate": {
                        **first["predicate"],
                        "surface": case["untyped_candidate"]["predicate"],
                    },
                    "local_entities": first["local_entities"],
                    "roles": first["roles"],
                    "modality": first["modality"],
                    "polarity": first["polarity"],
                    "time": first["time"],
                    "supporting_l1_refs": [support["support_ref"] for support in supports],
                }],
                "abstraction": {
                    "method": "task_composition",
                    "basis": "public supports were combined despite an unresolved requirement",
                },
                "closure": {
                    "pattern": "multi_evidence_set",
                    "required_support_refs": [support["support_ref"] for support in supports],
                    "optional_support_refs": [],
                },
                "source_turn_refs": [turn["source_turn_ref"] for turn in case["source_turns"]],
                "source_session_refs": [case["source_session_ref"]],
                "evidence_bindings": sorted(
                    [
                        binding
                        for support in supports
                        for binding in support["evidence_bindings"]
                    ],
                    key=lambda binding: binding["evidence_id"],
                ),
                "lifecycle": "candidate",
            }
            decision = "emit_l2"
        proposals.append(
            {
                "case_id": item["case_id"],
                "candidate_ref": item["candidate_ref"],
                "decision": decision,
                "confidence": 1.0,
                "typed_candidate": typed,
                "reason_code": "test_fixture",
            }
        )
    staged = run_root.parent / "staged.json"
    staged_payload = {
        "schema_version": "typed-extractor-l2-proposals-v1",
        "dataset_id": gold["dataset_id"],
        "run_id": run_id,
        "proposer_id": proposer_id,
        "proposer_version": proposer_version,
        "case_count": gold["case_count"],
        "proposals": proposals,
    }
    staged.write_text(
        json.dumps(staged_payload, ensure_ascii=False),
        encoding="utf-8",
    )
    raw_response = run_root / "raw-response.json"
    raw_response.parent.mkdir(parents=True, exist_ok=True)
    raw_response.write_text(
        json.dumps(
            {
                "model": "resolved-test-model",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                staged_payload,
                                ensure_ascii=False,
                            )
                        }
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    raw_response.chmod(0o444)
    freeze_l2_model_proposals(
        root / "public-l2.json",
        staged,
        run_root / "proposals.json",
        run_root / "provenance.json",
        prompt_path=PROMPT,
        dispatch_path=dispatch,
        raw_response_path=raw_response,
        isolation_context=ISOLATION,
    )


def _guard_bundle():
    return build_authoritative_conformance_bundle(
        GUARD_ROOT,
        "slice-v1",
        results_path=GUARD_RESULTS,
    )


def _bind_v3_outputs(root: Path) -> None:
    source_path = root / "source-cases-l2.json"
    if source_path.exists():
        source_path.chmod(0o644)
    source_path.write_bytes(SOURCE_CONFIG.read_bytes())
    source_path.chmod(0o444)
    manifest_path = root / "manifest-l2.json"
    manifest_path.chmod(0o644)
    manifest = load_json(manifest_path)
    manifest["output_sha256"] = {
        name: sha256_file(root / name) for name in V3_L2_OUTPUTS
    }
    manifest["thresholds"] = dict(V3_L2_THRESHOLDS)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    manifest_path.chmod(0o444)


def test_l2_perfect_proposals_pass_raw_and_gate_independently(tmp_path: Path) -> None:
    root = tmp_path / "slice"
    _prepare(root)
    run_root = tmp_path / "run"
    _freeze_from_gold(root, run_root)
    score = score_l2_proposals(
        root,
        run_root / "proposals.json",
        run_root / "provenance.json",
        guard_bundle=_guard_bundle(),
    )
    assert score.schema_version == "typed-extractor-l2-score-v2"
    assert score.status == "scored"
    assert score.scoring_policy_version == "evidence-set-abstraction-method-v2"
    assert score.raw_proposer_quality_ready is True
    assert score.deterministic_gate_safety_ready is True
    assert score.metrics["raw_decision_accuracy"] == 1.0
    assert score.metrics["raw_abstention_f1"] == 1.0
    assert score.metrics["support_id_accuracy"] == 1.0
    assert score.metrics["source_coverage_accuracy"] == 1.0
    assert score.metrics["gate_intervention_count"] == 0
    assert score.metrics["deterministic_critical_false_materialization_count"] == 0
    assert all(value == 0 for value in score.claim_boundary["automatic_write_counts"].values())
    assert score.guard_state["before_fingerprint"] == score.guard_state["after_fingerprint"]


def test_l2_scorer_accepts_explicit_v3_contract_and_threads_it_to_runner(
    tmp_path: Path,
) -> None:
    root = tmp_path / "slice"
    _prepare(root)
    run_root = tmp_path / "run"
    _freeze_from_gold(root, run_root)
    _bind_v3_outputs(root)

    score = score_l2_proposals(
        root,
        run_root / "proposals.json",
        run_root / "provenance.json",
        guard_bundle=_guard_bundle(),
        manifest_output_names=V3_L2_OUTPUTS,
        required_thresholds=V3_L2_THRESHOLDS,
    )
    result = run_l2_scoring_file(
        root,
        run_root / "proposals.json",
        run_root / "provenance.json",
        guard_root=GUARD_ROOT,
        guard_slice_id="slice-v1",
        guard_results_path=GUARD_RESULTS,
        score_path=run_root / "score.json",
        report_path=run_root / "report.md",
        error_analysis_path=run_root / "error-analysis.json",
        manifest_output_names=V3_L2_OUTPUTS,
        required_thresholds=V3_L2_THRESHOLDS,
    )

    assert score.raw_proposer_quality_ready is True
    assert result["metrics"] == score.metrics


@pytest.mark.parametrize(
    "manifest_output_names",
    [
        (*V3_L2_OUTPUTS, "extra-l2.json"),
        (*V3_L2_OUTPUTS, "source-cases-l2.json"),
        (*V3_L2_OUTPUTS[:-1], "nested/source-cases-l2.json"),
    ],
)
def test_l2_scorer_rejects_invalid_explicit_manifest_output_names(
    tmp_path: Path,
    manifest_output_names: tuple[str, ...],
) -> None:
    root = tmp_path / "slice"
    _prepare(root)
    run_root = tmp_path / "run"
    _freeze_from_gold(root, run_root)
    _bind_v3_outputs(root)

    with pytest.raises(ValueError, match="manifest output names"):
        score_l2_proposals(
            root,
            run_root / "proposals.json",
            run_root / "provenance.json",
            guard_bundle=_guard_bundle(),
            manifest_output_names=manifest_output_names,
            required_thresholds=V3_L2_THRESHOLDS,
        )


def test_l2_scorer_rejects_missing_or_drifted_v3_contract(tmp_path: Path) -> None:
    root = tmp_path / "slice"
    _prepare(root)
    run_root = tmp_path / "run"
    _freeze_from_gold(root, run_root)
    source_path = root / "source-cases-l2.json"
    source_path.write_bytes(SOURCE_CONFIG.read_bytes())
    source_path.chmod(0o444)

    with pytest.raises(ValueError, match="manifest does not bind scoring inputs"):
        score_l2_proposals(
            root,
            run_root / "proposals.json",
            run_root / "provenance.json",
            guard_bundle=_guard_bundle(),
            manifest_output_names=V3_L2_OUTPUTS,
            required_thresholds=V3_L2_THRESHOLDS,
        )

    _bind_v3_outputs(root)
    source_path.chmod(0o644)
    source_path.write_text("source hash drift", encoding="utf-8")
    source_path.chmod(0o444)

    with pytest.raises(ValueError, match="manifest does not bind scoring inputs"):
        score_l2_proposals(
            root,
            run_root / "proposals.json",
            run_root / "provenance.json",
            guard_bundle=_guard_bundle(),
            manifest_output_names=V3_L2_OUTPUTS,
            required_thresholds=V3_L2_THRESHOLDS,
        )


def test_l2_scorer_rejects_changed_explicit_threshold(tmp_path: Path) -> None:
    root = tmp_path / "slice"
    _prepare(root)
    run_root = tmp_path / "run"
    _freeze_from_gold(root, run_root)
    _bind_v3_outputs(root)
    changed_thresholds = dict(V3_L2_THRESHOLDS)
    changed_thresholds["raw_decision_accuracy"] = 0.9

    with pytest.raises(ValueError, match="fixed qualification thresholds"):
        score_l2_proposals(
            root,
            run_root / "proposals.json",
            run_root / "provenance.json",
            guard_bundle=_guard_bundle(),
            manifest_output_names=V3_L2_OUTPUTS,
            required_thresholds=changed_thresholds,
        )


def test_l2_scoring_uses_evidence_sets_and_abstraction_methods(tmp_path: Path) -> None:
    root = tmp_path / "slice"
    _prepare(root)
    run_root = tmp_path / "run"
    _freeze_from_gold(
        root,
        run_root,
        reverse_evidence=True,
        rewrite_abstraction_basis=True,
    )
    score = score_l2_proposals(
        root,
        run_root / "proposals.json",
        run_root / "provenance.json",
        guard_bundle=_guard_bundle(),
    )
    assert score.raw_proposer_quality_ready is True
    assert score.deterministic_gate_safety_ready is True
    assert score.metrics["exact_evidence_rate"] == 1.0
    assert score.metrics["abstraction_accuracy"] == 1.0
    assert score.metrics["gate_intervention_count"] == 0


def test_l2_standalone_scorer_rejects_lowered_manifest_thresholds(
    tmp_path: Path,
) -> None:
    root = tmp_path / "slice"
    _prepare(root)
    run_root = tmp_path / "run"
    _freeze_from_gold(root, run_root)
    manifest_path = root / "manifest-l2.json"
    manifest_path.chmod(0o644)
    manifest = load_json(manifest_path)
    manifest["thresholds"]["raw_decision_accuracy"] = 0.0
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    manifest_path.chmod(0o444)

    with pytest.raises(ValueError, match="fixed qualification thresholds"):
        score_l2_proposals(
            root,
            run_root / "proposals.json",
            run_root / "provenance.json",
            guard_bundle=_guard_bundle(),
        )


def test_l2_scorer_rejects_raw_response_hash_drift(tmp_path: Path) -> None:
    root = tmp_path / "slice"
    _prepare(root)
    run_root = tmp_path / "run"
    _freeze_from_gold(root, run_root)
    raw_response = run_root / "raw-response.json"
    raw_response.chmod(0o644)
    payload = load_json(raw_response)
    payload["model"] = "different-resolved-model"
    raw_response.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    raw_response.chmod(0o444)

    with pytest.raises(ValueError, match="raw response"):
        score_l2_proposals(
            root,
            run_root / "proposals.json",
            run_root / "provenance.json",
            guard_bundle=_guard_bundle(),
        )


def test_l2_false_emission_fails_raw_but_gate_stays_safe(tmp_path: Path) -> None:
    root = tmp_path / "slice"
    _prepare(root)
    run_root = tmp_path / "run"
    _freeze_from_gold(root, run_root, false_emit=True)
    score = score_l2_proposals(
        root,
        run_root / "proposals.json",
        run_root / "provenance.json",
        guard_bundle=_guard_bundle(),
    )
    assert score.raw_proposer_quality_ready is False
    assert score.deterministic_gate_safety_ready is True
    assert score.metrics["raw_critical_false_emission_count"] == 2
    assert score.metrics["gate_intervention_count"] == 2
    assert score.metrics["deterministic_critical_false_materialization_count"] == 0
    assert score.error_taxonomy["false_emission"] == 2
