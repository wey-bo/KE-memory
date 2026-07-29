from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tools.natural_memory_benchmark.io import load_json, sha256_file
from tools.natural_memory_benchmark.typed_extractor_l1_dev_repair import (
    EXPECTED_L1_PRIMARY_COUNTS,
    L1DiagnosticSource,
    prepare_l1_dev_repair_slice,
    validate_l1_dev_repair_slice,
)


ROOT = Path(
    "artifacts/automatic-extraction-assessment/"
    "typed-extractor-v2-l1-dev-repair-v1"
)
SOURCE = ROOT / "diagnostic-source-l1.json"
V2_ROOT = Path(
    "artifacts/automatic-extraction-assessment/"
    "typed-extractor-v2-l1-dev-repair-v2"
)
V2_SOURCE = V2_ROOT / "diagnostic-source-l1.json"
V7_PROMPT = V2_ROOT / "proposer-prompt-l1-v7.md"
V8_PROMPT = V2_ROOT / "proposer-prompt-l1-v8.md"
V9_PROMPT = V2_ROOT / "proposer-prompt-l1-v9.md"
V10_PROMPT = V2_ROOT / "proposer-prompt-l1-v10.md"
PRIOR_ROOTS = (
    Path(
        "artifacts/automatic-extraction-assessment/"
        "typed-extractor-v2-dev-v3"
    ),
    Path(
        "artifacts/automatic-extraction-assessment/"
        "typed-extractor-v2-fresh-hidden-v1/l1"
    ),
)


def _write_source(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    path.chmod(0o444)


def _string_values(value: object) -> set[str]:
    if isinstance(value, dict):
        return set().union(*(_string_values(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_string_values(item) for item in value))
    return {value} if isinstance(value, str) else set()


def test_diagnostic_source_is_strict_and_has_exact_distribution() -> None:
    source = L1DiagnosticSource.model_validate(load_json(SOURCE))

    assert source.provenance == "diagnostic_authored"
    assert len(source.cases) == 16
    assert len({case.private_case_id for case in source.cases}) == 16
    primary_counts = {
        family: sum(case.primary_family == family for case in source.cases)
        for family in EXPECTED_L1_PRIMARY_COUNTS
    }
    assert primary_counts == EXPECTED_L1_PRIMARY_COUNTS

    malformed = load_json(SOURCE)
    malformed["unexpected"] = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        L1DiagnosticSource.model_validate(malformed)


def test_prepare_is_deterministic_opaque_and_private_separated(
    tmp_path: Path,
) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"

    first = prepare_l1_dev_repair_slice(SOURCE, first_root, PRIOR_ROOTS)
    second = prepare_l1_dev_repair_slice(SOURCE, second_root, PRIOR_ROOTS)

    assert first == second
    assert first["status"] == "valid"
    assert first["case_count"] == 16
    assert first["provenance"] == "diagnostic_authored"
    assert first["prior_identifier_overlap_count"] == 0
    assert first["prior_evidence_overlap_count"] == 0
    assert all(count >= 2 for count in first["family_opportunity_counts"].values())

    formal_names = (
        "public-l1.json",
        "authority-l1.json",
        "gold-l1.json",
        "manifest-l1.json",
    )
    for name in formal_names:
        assert first_root.joinpath(name).read_bytes() == second_root.joinpath(
            name
        ).read_bytes()
        assert first_root.joinpath(name).stat().st_mode & 0o777 == 0o444

    source_payload = load_json(SOURCE)
    public_bytes = (first_root / "public-l1.json").read_bytes()
    public_values = _string_values(load_json(first_root / "public-l1.json"))
    for case in source_payload["cases"]:
        assert case["private_case_id"].encode() not in public_bytes
        assert case["primary_family"] not in public_values
        for family in case["secondary_families"]:
            assert family not in public_values
        assert case["authority"]["knowledge_id"].encode() not in public_bytes
        assert case["authority"]["candidate_id"].encode() not in public_bytes
    for private_field in (
        b"private_case_id",
        b"primary_family",
        b"secondary_families",
        b"expected_decision",
        b"expected_typed_candidate",
        b"authority",
    ):
        assert private_field not in public_bytes

    public = load_json(first_root / "public-l1.json")
    authority = load_json(first_root / "authority-l1.json")
    gold = load_json(first_root / "gold-l1.json")
    public_case_ids = {case["case_id"] for case in public["cases"]}
    assert public_case_ids == {case["case_id"] for case in authority["cases"]}
    assert public_case_ids == {item["case_id"] for item in gold["items"]}
    assert all(case_id.startswith("case-") for case_id in public_case_ids)
    assert all(
        case["candidate_ref"].startswith("candidate-")
        for case in public["cases"]
    )


def test_prepare_rejects_prior_identifier_and_evidence_overlap(
    tmp_path: Path,
) -> None:
    prior_authority = load_json(PRIOR_ROOTS[0] / "authority-l1.json")
    source = load_json(SOURCE)
    source["cases"][0]["authority"]["knowledge_id"] = prior_authority["cases"][0][
        "knowledge_id"
    ]
    overlapping_id = tmp_path / "overlapping-id.json"
    _write_source(overlapping_id, source)

    with pytest.raises(ValueError, match="prior identifier overlap"):
        prepare_l1_dev_repair_slice(
            overlapping_id,
            tmp_path / "id-output",
            PRIOR_ROOTS,
        )

    source = load_json(SOURCE)
    prior_evidence = prior_authority["cases"][0]["required_evidence_bindings"][0]
    source["cases"][0]["untyped_candidate"]["evidence"][0]["evidence_id"] = (
        prior_evidence["evidence_id"]
    )
    source["cases"][0]["authority"]["required_evidence_bindings"][0][
        "evidence_id"
    ] = prior_evidence["evidence_id"]
    overlapping_evidence = tmp_path / "overlapping-evidence.json"
    _write_source(overlapping_evidence, source)

    with pytest.raises(ValueError, match="prior evidence overlap"):
        prepare_l1_dev_repair_slice(
            overlapping_evidence,
            tmp_path / "evidence-output",
            PRIOR_ROOTS,
        )


def test_evidence_offsets_must_resolve_exactly(tmp_path: Path) -> None:
    source = load_json(SOURCE)
    source["cases"][0]["untyped_candidate"]["evidence"][0]["start"] += 1
    invalid = tmp_path / "invalid-offset.json"
    _write_source(invalid, source)

    with pytest.raises(ValueError, match="evidence offset"):
        prepare_l1_dev_repair_slice(invalid, tmp_path / "output", PRIOR_ROOTS)


def test_validate_rebuilds_bytes_and_binds_claim_boundaries(tmp_path: Path) -> None:
    root = tmp_path / "slice"
    prepare_l1_dev_repair_slice(SOURCE, root, PRIOR_ROOTS)

    result = validate_l1_dev_repair_slice(SOURCE, root, PRIOR_ROOTS)

    assert result["status"] == "valid"
    manifest = load_json(root / "manifest-l1.json")
    assert manifest["input_sha256"]["diagnostic_source"] == sha256_file(SOURCE)
    assert manifest["claim_boundary"] == {
        "automatic_authoritative_writes": False,
        "diagnostic_only": True,
        "embedding_authority": False,
        "fresh_hidden_v2_created": False,
        "longmemeval_status": "structured_l2_identity_unresolved",
    }

    public = load_json(root / "public-l1.json")
    public["cases"][0]["source_turn"]["user"] += " drift"
    path = root / "public-l1.json"
    path.chmod(0o644)
    path.write_text(json.dumps(public, ensure_ascii=False), encoding="utf-8")
    path.chmod(0o444)
    with pytest.raises(ValueError, match="artifact drift"):
        validate_l1_dev_repair_slice(SOURCE, root, PRIOR_ROOTS)


def test_source_rejects_duplicate_private_id_and_extra_case_field() -> None:
    duplicate = load_json(SOURCE)
    duplicate["cases"][1]["private_case_id"] = duplicate["cases"][0][
        "private_case_id"
    ]
    with pytest.raises(ValidationError, match="duplicate private case ID"):
        L1DiagnosticSource.model_validate(duplicate)

    extra = copy.deepcopy(load_json(SOURCE))
    extra["cases"][0]["unexpected"] = "not allowed"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        L1DiagnosticSource.model_validate(extra)


def test_l1_v2_rejects_prompt_incomplete_public_catalog() -> None:
    source = load_json(SOURCE)
    source["schema_version"] = "typed-extractor-l1-diagnostic-source-v2"
    source["dataset_id"] = "typed-extractor-l1-dev-repair-v2"

    with pytest.raises(ValidationError, match="missing L1 V6 public catalogs"):
        L1DiagnosticSource.model_validate(source)


def test_l1_v2_formal_contract_is_complete_and_uses_new_opaque_ids(
    tmp_path: Path,
) -> None:
    output = tmp_path / "v2"
    result = prepare_l1_dev_repair_slice(V2_SOURCE, output, PRIOR_ROOTS)

    assert result["status"] == "valid"
    public = load_json(output / "public-l1.json")
    assert {
        "condition_operators",
        "modality_policy",
        "operator_kind_bindings",
        "operator_role_bindings",
        "operator_time_bindings",
        "scope_operators",
    }.issubset(public["allowed_vocabulary"])

    v1_public = load_json(ROOT / "public-l1.json")
    assert {case["case_id"] for case in public["cases"]}.isdisjoint(
        case["case_id"] for case in v1_public["cases"]
    )
    assert {
        evidence["evidence_id"]
        for case in public["cases"]
        for evidence in case["untyped_candidate"]["evidence"]
    }.isdisjoint(
        evidence["evidence_id"]
        for case in v1_public["cases"]
        for evidence in case["untyped_candidate"]["evidence"]
    )


def test_l1_v2_rejects_catalog_that_does_not_cover_emitted_gold() -> None:
    source = load_json(V2_SOURCE)
    source["public_vocabulary"]["operator_kind_bindings"].remove(
        "approve_artifact|event"
    )

    with pytest.raises(ValidationError, match="L1 V6 operator-kind catalog"):
        L1DiagnosticSource.model_validate(source)


def test_l1_v2_rejects_catalog_that_does_not_cover_emission_gold() -> None:
    source = load_json(V2_SOURCE)
    source["public_vocabulary"]["operator_kind_bindings"].remove(
        "approve_artifact|event"
    )

    with pytest.raises(
        ValidationError,
        match="L1 V6 public catalog does not cover emitted candidate",
    ):
        L1DiagnosticSource.model_validate(source)


def test_l1_v7_prompt_requires_explicit_prepositional_participant_decomposition(
) -> None:
    prompt = V7_PROMPT.read_text(encoding="utf-8")

    assert prompt.startswith("# Typed Extractor V2 L1 Dev Proposer Contract V7")
    assert "`with X`" in prompt
    assert "`for X`" in prompt
    assert "`to X`" in prompt
    assert "distinct exact-source local entity" in prompt
    assert "selected operator exposes" in prompt
    assert "Do not infer an unstated participant" in prompt
    assert "case-c4c2917f23b9a1e7" not in prompt


def test_l1_v8_prompt_requires_disjoint_head_and_requested_task_modality(
) -> None:
    prompt = V8_PROMPT.read_text(encoding="utf-8")

    assert prompt.startswith("# Typed Extractor V2 L1 Dev Proposer Contract V8")
    assert "exact head substring before the participant phrase" in prompt
    assert "must not retain the participant phrase" in prompt
    assert "explicitly asks or requests an actor to perform a task" in prompt
    assert "`requested`, not `actual`" in prompt
    assert "case-c4c2917f23b9a1e7" not in prompt
    assert "case-db65090bd80cbf35" not in prompt


def test_l1_v9_prompt_prioritizes_public_candidate_surfaces_and_audits_split_heads(
) -> None:
    prompt = V9_PROMPT.read_text(encoding="utf-8")

    assert prompt.startswith("# Typed Extractor V2 L1 Dev Proposer Contract V9")
    assert "untyped_candidate.subject" in prompt
    assert "untyped_candidate.object" in prompt
    assert "take precedence over source_turn wording" in prompt
    assert "do not replace `the user` with `I`" in prompt
    assert "must not contain ` with X`, ` for X`, or ` to X`" in prompt
    assert "case-48e6274908cd3ea8" not in prompt
    assert "case-7efb4b0a2932abff" not in prompt
    assert "case-c4c2917f23b9a1e7" not in prompt
    assert "case-f7c05b73908c12fb" not in prompt


def test_l1_v10_prompt_has_decision_precedence_and_mechanical_participant_split(
) -> None:
    prompt = V10_PROMPT.read_text(encoding="utf-8")

    assert prompt.startswith("# Typed Extractor V2 L1 Dev Proposer Contract V10")
    assert "Apply decision precedence before typed field selection" in prompt
    assert "question-only content is `no_memory`" in prompt
    assert "must not be changed to `abstain`" in prompt
    assert "split the surface once at the ASCII delimiter" in prompt
    assert "left substring" in prompt
    assert "right substring X" in prompt
    assert "must not appear anywhere in `local_entities`" in prompt
    assert "case-736a5166c9e2a446" not in prompt
    assert "case-c4c2917f23b9a1e7" not in prompt
