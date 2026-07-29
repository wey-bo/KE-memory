from __future__ import annotations

import json
import hashlib
import re
from collections import Counter
from pathlib import Path

import pytest

import tools.natural_memory_benchmark.query_compiler_v2_dev_qualification as qualification
import tools.natural_memory_benchmark.query_compiler_v2_proposal_eval as proposal_eval
from tools.natural_memory_benchmark.query_compiler_v2_assessment import (
    QueryCompilerAuthorityDocumentV1,
    QueryCompilerGoldDocumentV1,
    QueryCompilerPublicDocumentV1,
)
from tools.natural_memory_benchmark.query_compiler_v2 import compile_query_draft
from tools.natural_memory_benchmark.query_compiler_v2_dev_qualification import (
    EXPECTED_FAMILY_COUNTS,
    build_query_proposer_dev_v1,
    validate_query_proposer_dev_v1,
)
from tools.natural_memory_benchmark.query_compiler_v2_proposal_eval import (
    QueryDraftGoldDocumentV1,
    QueryDraftProposalEvaluationV1,
    validate_frozen_query_draft_proposal_run,
)


def _json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _leaf_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_task6_dev_qualification_module_exposes_author_and_validator() -> None:
    assert callable(build_query_proposer_dev_v1)
    assert callable(validate_query_proposer_dev_v1)


def test_builds_twenty_case_eight_family_dev_matrix(tmp_path: Path) -> None:
    root = tmp_path / "dev-v1"

    manifest = build_query_proposer_dev_v1(root)

    public = QueryCompilerPublicDocumentV1.model_validate(_json(root / "public.json"))
    compiler_gold = QueryCompilerGoldDocumentV1.model_validate(
        _json(root / "compiler-gold.json")
    )
    assert manifest.case_count == 20
    assert len(public.cases) == 20
    assert Counter(item.family for item in compiler_gold.cases) == Counter(
        EXPECTED_FAMILY_COUNTS
    )
    assert all(count >= 2 for count in EXPECTED_FAMILY_COUNTS.values())
    assert sum(item.expected_status == "executable" for item in compiler_gold.cases) == 11
    assert sum(item.expected_status == "abstain" for item in compiler_gold.cases) == 9
    assert sum(item.critical for item in compiler_gold.cases) == 8
    assert sum(item.expected_fallback_allowed for item in compiler_gold.cases) == 2


def test_documents_have_exact_case_and_dataset_coverage(tmp_path: Path) -> None:
    root = tmp_path / "dev-v1"
    build_query_proposer_dev_v1(root)

    public = QueryCompilerPublicDocumentV1.model_validate(_json(root / "public.json"))
    authority = QueryCompilerAuthorityDocumentV1.model_validate(
        _json(root / "authority.json")
    )
    draft_gold = QueryDraftGoldDocumentV1.model_validate(
        _json(root / "draft-gold.json")
    )
    compiler_gold = QueryCompilerGoldDocumentV1.model_validate(
        _json(root / "compiler-gold.json")
    )
    documents = [public, authority, draft_gold, compiler_gold]
    assert {item.dataset_id for item in documents} == {"query-proposer-dev-v1"}
    public_ids = [item.case_id for item in public.cases]
    assert len(public_ids) == len(set(public_ids)) == 20
    assert all(re.fullmatch(r"qc-[0-9a-f]{16}", value) for value in public_ids)
    assert all(
        re.fullmatch(r"qq-[0-9a-f]{16}", item.query_id)
        for item in public.cases
    )
    for document in documents[1:]:
        assert [item.case_id for item in document.cases] == public_ids


def test_public_document_does_not_leak_authority_or_gold_fields(tmp_path: Path) -> None:
    root = tmp_path / "dev-v1"
    build_query_proposer_dev_v1(root)
    public_payload = _json(root / "public.json")

    forbidden_keys = {
        "family",
        "status",
        "expected_status",
        "critical",
        "fallback",
        "fallback_allowed",
        "entity_id",
        "registry",
        "gold",
    }

    def visit(value: object) -> None:
        if isinstance(value, dict):
            assert forbidden_keys.isdisjoint(value)
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(public_payload)
    public_text = (root / "public.json").read_text(encoding="utf-8").casefold()
    assert "typed-extractor" not in public_text
    assert "fresh-v3" not in public_text


def test_reference_run_and_evaluation_pass_both_dev_gates(tmp_path: Path) -> None:
    root = tmp_path / "dev-v1"
    build_query_proposer_dev_v1(root)

    receipt = validate_frozen_query_draft_proposal_run(root / "reference-run")
    evaluation = QueryDraftProposalEvaluationV1.model_validate(
        _json(root / "evaluation.json")
    )

    assert receipt.dataset_id == "query-proposer-dev-v1"
    assert evaluation.validation_receipt.all_drafts_valid is True
    assert all(
        entry.validation_status == "valid"
        for entry in evaluation.validation_receipt.entries
    )
    raw = evaluation.raw_score.metrics
    assert raw.case_count == 20
    assert raw.case_coverage == 1.0
    assert raw.schema_valid_rate == 1.0
    assert raw.query_id_accuracy == 1.0
    assert raw.intent_accuracy == 1.0
    assert raw.target_level_accuracy == 1.0
    assert raw.answer_accuracy == 1.0
    assert raw.pattern_accuracy == 1.0
    assert raw.time_accuracy == 1.0
    assert raw.lifecycle_accuracy == 1.0
    assert raw.source_accuracy == 1.0
    assert raw.conflict_supersession_accuracy == 1.0
    assert raw.evidence_policy_accuracy == 1.0
    assert raw.explicit_absence_accuracy == 1.0
    assert raw.draft_template_exact == 1.0
    assert raw.draft_semantic_exact == 1.0
    assert raw.missing_output_count == 0
    assert raw.invalid_json_count == 0
    assert raw.transport_error_count == 0
    assert raw.schema_invalid_output_count == 0
    assert raw.critical_invalid_output_count == 0
    assert evaluation.raw_score.raw_proposer_quality_ready is True
    assert evaluation.gate_evaluated is True
    assert evaluation.gate_score is not None
    gate = evaluation.gate_score
    assert gate.metrics.case_count == 20
    assert gate.metrics.family_coverage_count == 8
    assert gate.metrics.gate_status_accuracy == 1.0
    assert gate.metrics.accepted_plan_exact == 1.0
    assert gate.metrics.fallback_decision_exact == 1.0
    assert gate.metrics.fallback_reason_exact == 1.0
    assert gate.metrics.unresolved_slots_exact == 1.0
    assert gate.metrics.blocked_reasons_exact == 1.0
    assert gate.metrics.false_abstention_count == 0
    assert gate.metrics.false_executable_count == 0
    assert gate.metrics.unsafe_executable_plan_count == 0
    assert gate.metrics.critical_false_executable_count == 0
    assert gate.metrics.structural_fallback_count == 0
    assert gate.gate_safety_ready is True
    assert gate.compilation_utility_ready is True
    assert evaluation.combined_dev_ready is True


def test_manifest_records_harness_only_zero_write_boundary(tmp_path: Path) -> None:
    root = tmp_path / "dev-v1"
    manifest = build_query_proposer_dev_v1(root)

    assert manifest.source_allowlist == ["newly_authored_diagnostic_text"]
    assert len(manifest.case_source_mapping) == 20
    assert set(manifest.case_source_mapping.values()) == {
        "newly_authored_diagnostic_text"
    }
    assert manifest.typed_extractor_hidden_read is False
    assert manifest.semantic_model_call_count == 0
    assert manifest.deterministic_producer_emission_count == 1
    assert manifest.gold_semantic_outcome_compiler_call_count == 0
    assert manifest.gold_plan_hash_binding_compiler_batch_count == 1
    assert manifest.artifact_build_gate_scoring_compiler_batch_count == 1
    assert manifest.semantic_run_count == 1
    assert manifest.semantic_run_count_interpretation == (
        "single_deterministic_reference_emission_not_model_call"
    )
    assert manifest.natural_language_answer_generated is False
    assert manifest.automatic_memory_write_count == 0
    assert manifest.automatic_identity_write_count == 0
    assert manifest.automatic_membership_write_count == 0
    assert manifest.automatic_closure_write_count == 0
    assert manifest.automatic_revision_write_count == 0
    assert manifest.automatic_snapshot_write_count == 0
    assert manifest.automatic_aggregate_write_count == 0
    assert manifest.reference_is_harness_qualification_only is True
    assert manifest.compiler_gold_binding_method == (
        "independent_frozen_outcomes_with_prebound_plan_hashes"
    )
    assert manifest.gold_oracle_source == "query_compiler_v2_dev_oracle_v2.json"
    assert re.fullmatch(r"[0-9a-f]{64}", manifest.gold_oracle_sha256)
    assert manifest.reference_fixture_source == (
        "query_compiler_v2_dev_reference_v3.json"
    )
    assert re.fullmatch(r"[0-9a-f]{64}", manifest.reference_fixture_sha256)
    assert manifest.reference_fixture_authored_after_oracle_freeze is True
    assert manifest.future_semantic_run_requirement == (
        "freeze_canonical_ids_or_add_alpha_normalized_compiler_gate"
    )


def test_canonical_local_ids_are_stable_for_non_alpha_plan_hashes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "dev-v1"
    build_query_proposer_dev_v1(root)
    draft_gold = QueryDraftGoldDocumentV1.model_validate(
        _json(root / "draft-gold.json")
    )

    for case in draft_gold.cases:
        draft = case.expected_draft
        assert [group.group_id for group in draft.pattern_groups] == [
            f"group-{index}" for index in range(len(draft.pattern_groups))
        ]
        atom_ids = [
            atom.atom_id
            for group in draft.pattern_groups
            for atom in group.atoms
        ]
        assert atom_ids == [f"atom-{index}" for index in range(len(atom_ids))]


def test_identity_count_plan_is_bound_to_an_identity_snapshot(tmp_path: Path) -> None:
    root = tmp_path / "dev-v1"
    build_query_proposer_dev_v1(root)
    authority = QueryCompilerAuthorityDocumentV1.model_validate(
        _json(root / "authority.json")
    )
    draft_gold = QueryDraftGoldDocumentV1.model_validate(
        _json(root / "draft-gold.json")
    )
    compiler_gold = QueryCompilerGoldDocumentV1.model_validate(
        _json(root / "compiler-gold.json")
    )
    authority_by_id = {item.case_id: item for item in authority.cases}
    draft_by_id = {item.case_id: item for item in draft_gold.cases}
    executable_identity = [
        item
        for item in compiler_gold.cases
        if item.family == "identity_aggregate"
        and item.expected_status == "executable"
    ]
    assert len(executable_identity) == 1
    case = executable_identity[0]
    authority_case = authority_by_id[case.case_id]
    result = compile_query_draft(
        draft_by_id[case.case_id].expected_draft,
        authority_case.context,
        authority_case.registry,
    )
    assert result.plan is not None
    assert result.plan.identity_snapshot_id == "identity-snapshot-dev-v1"
    assert result.plan.identity_input_fingerprint == "1" * 64


def test_replay_is_byte_deterministic_and_existing_root_is_rejected(
    tmp_path: Path,
) -> None:
    first = tmp_path / "dev-v1-a"
    second = tmp_path / "dev-v1-b"
    build_query_proposer_dev_v1(first)
    build_query_proposer_dev_v1(second)

    assert _leaf_bytes(first) == _leaf_bytes(second)
    with pytest.raises(FileExistsError, match="already exists"):
        build_query_proposer_dev_v1(first)


def test_publish_refuses_to_replace_a_preexisting_empty_root(
    tmp_path: Path,
) -> None:
    staging = tmp_path / ".dev-v1.author"
    root = tmp_path / "dev-v1"
    staging.mkdir()
    (staging / "marker.txt").write_text("staged", encoding="utf-8")
    root.mkdir()

    with pytest.raises(FileExistsError, match="already exists"):
        qualification._publish_directory_noreplace(staging, root)

    assert (staging / "marker.txt").read_text(encoding="utf-8") == "staged"
    assert list(root.iterdir()) == []


def test_gold_loading_and_artifact_build_report_real_compiler_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compiler_calls: list[tuple[object, ...]] = []
    real_compile = proposal_eval.compile_query_proposals

    def trace_compile(*args: object, **kwargs: object) -> object:
        compiler_calls.append(args)
        return real_compile(*args, **kwargs)

    monkeypatch.setattr(proposal_eval, "compile_query_proposals", trace_compile)

    oracle = qualification._load_independent_gold_oracle()

    assert oracle.isolation.reference_artifacts_read_before_freeze is False
    assert oracle.isolation.compiler_used_to_author_semantic_outcomes is False
    assert oracle.isolation.compiler_plan_hash_binding_after_outcome_freeze is True
    assert compiler_calls == []
    assert len(oracle.draft_gold.cases) == 20
    assert len(oracle.compiler_gold.cases) == 20

    payload = qualification._dev_payload()

    assert len(compiler_calls) == 1
    assert (
        payload.dataset_manifest.artifact_build_gate_scoring_compiler_batch_count
        == 1
    )


def test_known_good_reference_fixture_loads_without_reading_gold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called() -> object:
        raise AssertionError("reference fixture loader read the gold oracle")

    monkeypatch.setattr(
        qualification,
        "_load_independent_gold_oracle",
        fail_if_called,
    )

    reference = qualification._load_reference_fixture()

    assert reference.authored_after_oracle_freeze is True
    assert reference.semantic_model_call_count == 0
    assert len(reference.drafts) == 20
    assert re.fullmatch(r"[0-9a-f]{64}", reference.source_oracle_sha256)


def test_manifest_outcome_counts_are_cross_checked_against_compiler_gold(
    tmp_path: Path,
) -> None:
    root = tmp_path / "dev-v1"
    manifest = build_query_proposer_dev_v1(root)
    compiler_gold = QueryCompilerGoldDocumentV1.model_validate(
        _json(root / "compiler-gold.json")
    )
    inconsistent = manifest.model_copy(
        update={
            "expected_executable_count": 12,
            "expected_abstain_count": 8,
        }
    )

    with pytest.raises(ValueError, match="manifest outcome counts"):
        qualification._assert_manifest_matches_compiler_gold(
            inconsistent,
            compiler_gold,
        )


def test_validator_requires_exact_read_only_tree_and_no_hidden_markers(
    tmp_path: Path,
) -> None:
    root = tmp_path / "dev-v1"
    expected = build_query_proposer_dev_v1(root)

    validated = validate_query_proposer_dev_v1(root)

    assert validated == expected
    assert set(path.name for path in root.iterdir()) == {
        "authority.json",
        "compiler-gold.json",
        "dev-dataset-manifest.json",
        "draft-gold.json",
        "evaluation.json",
        "manifest.json",
        "proposer-prompt-and-policy.md",
        "public.json",
        "reference-run",
    }
    assert all(not (path.stat().st_mode & 0o222) for path in root.rglob("*"))
    joined = b"\n".join(_leaf_bytes(root).values()).lower()
    assert b"typed-extractor-fresh" not in joined
    assert b"fresh-v3" not in joined
    assert b"longmemeval-6d550036" not in joined

    root_manifest = _json(root / "manifest.json")
    assert isinstance(root_manifest, dict)
    hashes = root_manifest["artifact_sha256"]
    assert set(hashes) == set(_leaf_bytes(root)) - {"manifest.json"}
    for relative_path, expected_sha256 in hashes.items():
        actual = hashlib.sha256((root / relative_path).read_bytes()).hexdigest()
        assert actual == expected_sha256
