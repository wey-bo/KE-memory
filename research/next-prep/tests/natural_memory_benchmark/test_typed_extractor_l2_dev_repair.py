from __future__ import annotations

import copy
import json
import shutil
from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from tools.natural_memory_benchmark.io import load_json, sha256_file
from tools.natural_memory_benchmark.typed_extractor_l2_dev_repair import (
    EXPECTED_L2_CASE_IDS,
    L2DiagnosticSource,
    prepare_l2_dev_repair_slice,
    validate_l2_dev_repair_slice,
)


ROOT = Path(
    "artifacts/automatic-extraction-assessment/"
    "typed-extractor-v2-l2-dev-repair-v1"
)
SOURCE = ROOT / "diagnostic-source-l2.json"
V2_ROOT = Path(
    "artifacts/automatic-extraction-assessment/"
    "typed-extractor-v2-l2-dev-repair-v2"
)
V2_SOURCE = V2_ROOT / "diagnostic-source-l2.json"
V3_ROOT = Path(
    "artifacts/automatic-extraction-assessment/"
    "typed-extractor-v2-l2-dev-repair-v3"
)
V3_SOURCE = V3_ROOT / "diagnostic-source-l2.json"
V9_PROMPT = V3_ROOT / "proposer-prompt-l2.md"
L1_DIAGNOSTIC_ROOT = Path(
    "artifacts/automatic-extraction-assessment/"
    "typed-extractor-v2-l1-dev-repair-v1"
)
PRIOR_ROOTS = (
    Path(
        "artifacts/automatic-extraction-assessment/"
        "typed-extractor-v2-l2-dev-v9"
    ),
    Path(
        "artifacts/automatic-extraction-assessment/"
        "typed-extractor-v2-fresh-hidden-v1/l2"
    ),
    L1_DIAGNOSTIC_ROOT,
)


def _write_source(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    path.chmod(0o444)


def test_l2_diagnostic_source_is_strict_and_has_required_distribution() -> None:
    source = L2DiagnosticSource.model_validate(load_json(SOURCE))

    assert source.provenance == "diagnostic_authored"
    assert tuple(case.private_case_id for case in source.cases) == EXPECTED_L2_CASE_IDS
    decisions = Counter(case.expected_decision for case in source.cases)
    assert decisions == {"abstain": 4, "emit_l2": 8}
    methods = Counter(
        case.expected_typed_candidate.abstraction.method
        for case in source.cases
        if case.expected_typed_candidate is not None
    )
    assert methods == {
        "coreference_resolution": 2,
        "task_composition": 2,
        "lifecycle_resolution": 2,
        "state_summary": 1,
        "preference_aggregation": 1,
    }
    assert all(len(case.typed_l1_support_pack) >= 2 for case in source.cases)

    malformed = load_json(SOURCE)
    malformed["unexpected"] = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        L2DiagnosticSource.model_validate(malformed)


def test_prepare_l2_is_deterministic_separated_and_reference_closed(
    tmp_path: Path,
) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"

    first = prepare_l2_dev_repair_slice(SOURCE, first_root, PRIOR_ROOTS)
    second = prepare_l2_dev_repair_slice(SOURCE, second_root, PRIOR_ROOTS)

    assert first == second
    assert first["status"] == "valid"
    assert first["case_count"] == 12
    assert first["abstain_count"] == 4
    assert first["emit_count"] == 8
    assert first["non_task_kind_count"] >= 2
    assert first["prior_identifier_overlap_count"] == 0
    assert first["prior_evidence_overlap_count"] == 0
    assert first["abstraction_method_counts"]["coreference_resolution"] == 2
    assert first["abstraction_method_counts"]["task_composition"] == 2
    assert first["abstraction_method_counts"]["lifecycle_resolution"] == 2

    for name in (
        "public-l2.json",
        "authority-l2.json",
        "gold-l2.json",
        "manifest-l2.json",
    ):
        assert first_root.joinpath(name).read_bytes() == second_root.joinpath(
            name
        ).read_bytes()
        assert first_root.joinpath(name).stat().st_mode & 0o777 == 0o444

    source_payload = load_json(SOURCE)
    public_bytes = (first_root / "public-l2.json").read_bytes()
    for case in source_payload["cases"]:
        assert case["private_case_id"].encode() not in public_bytes
        assert case["primary_family"].encode() not in public_bytes
        assert case["authority"]["knowledge_id"].encode() not in public_bytes
        assert case["authority"]["candidate_id"].encode() not in public_bytes
    for field in (
        b"private_case_id",
        b"primary_family",
        b"secondary_families",
        b"expected_decision",
        b"expected_typed_candidate",
        b"authority",
    ):
        assert field not in public_bytes

    public = load_json(first_root / "public-l2.json")
    authority = load_json(first_root / "authority-l2.json")
    gold = load_json(first_root / "gold-l2.json")
    authority_by_id = {case["case_id"]: case for case in authority["cases"]}
    gold_by_id = {item["case_id"]: item for item in gold["items"]}
    assert {case["case_id"] for case in public["cases"]} == set(authority_by_id)
    assert set(authority_by_id) == set(gold_by_id)

    for case in public["cases"]:
        auth = authority_by_id[case["case_id"]]
        supports = case["typed_l1_support_pack"]
        support_refs = {support["support_ref"] for support in supports}
        turn_refs = {turn["source_turn_ref"] for turn in case["source_turns"]}
        support_turn_refs = {support["source_turn_ref"] for support in supports}
        support_session_refs = {support["source_session_ref"] for support in supports}
        support_evidence = {
            binding["evidence_id"]
            for support in supports
            for binding in support["evidence_bindings"]
        }
        public_evidence = {
            binding["evidence_id"]
            for binding in case["untyped_candidate"]["evidence"]
        }
        assert support_refs == set(auth["required_support_refs"])
        assert support_turn_refs.issubset(turn_refs)
        assert support_session_refs == {case["source_session_ref"]}
        assert support_evidence == set(
            binding["evidence_id"]
            for binding in auth["required_evidence_bindings"]
        )
        assert support_evidence.issubset(public_evidence)


def test_prepare_l2_rejects_prior_overlap(tmp_path: Path) -> None:
    prior_authority = load_json(PRIOR_ROOTS[0] / "authority-l2.json")
    source = load_json(SOURCE)
    source["cases"][0]["authority"]["knowledge_id"] = prior_authority["cases"][0][
        "knowledge_id"
    ]
    overlapping_id = tmp_path / "overlap-id.json"
    _write_source(overlapping_id, source)
    with pytest.raises(ValueError, match="prior identifier overlap"):
        prepare_l2_dev_repair_slice(
            overlapping_id,
            tmp_path / "id-output",
            PRIOR_ROOTS,
        )

    source = load_json(SOURCE)
    prior_evidence = prior_authority["cases"][0]["required_evidence_bindings"][0][
        "evidence_id"
    ]
    source["cases"][0]["untyped_candidate"]["evidence"][0][
        "evidence_id"
    ] = prior_evidence
    source["cases"][0]["typed_l1_support_pack"][0]["evidence_bindings"][0][
        "evidence_id"
    ] = prior_evidence
    source["cases"][0]["authority"]["required_evidence_bindings"][0][
        "evidence_id"
    ] = prior_evidence
    overlapping_evidence = tmp_path / "overlap-evidence.json"
    _write_source(overlapping_evidence, source)
    with pytest.raises(ValueError, match="prior evidence overlap"):
        prepare_l2_dev_repair_slice(
            overlapping_evidence,
            tmp_path / "evidence-output",
            PRIOR_ROOTS,
        )


def test_l2_source_rejects_unclosed_expected_support(tmp_path: Path) -> None:
    source = load_json(SOURCE)
    emit = next(
        case for case in source["cases"] if case["expected_decision"] == "emit_l2"
    )
    emit["expected_typed_candidate"]["supporting_l1_refs"][0] = (
        "diag-l2-support-missing"
    )
    invalid = tmp_path / "unclosed.json"
    _write_source(invalid, source)
    with pytest.raises(ValueError, match="support closure"):
        prepare_l2_dev_repair_slice(invalid, tmp_path / "output", PRIOR_ROOTS)


def test_validate_l2_rebuilds_bytes_and_claim_boundaries(tmp_path: Path) -> None:
    root = tmp_path / "slice"
    prepare_l2_dev_repair_slice(SOURCE, root, PRIOR_ROOTS)

    result = validate_l2_dev_repair_slice(SOURCE, root, PRIOR_ROOTS)

    assert result["status"] == "valid"
    manifest = load_json(root / "manifest-l2.json")
    assert manifest["input_sha256"]["diagnostic_source"] == sha256_file(SOURCE)
    assert manifest["claim_boundary"] == {
        "automatic_authoritative_writes": False,
        "diagnostic_only": True,
        "embedding_authority": False,
        "fresh_hidden_v2_created": False,
        "longmemeval_status": "structured_l2_identity_unresolved",
    }

    public = load_json(root / "public-l2.json")
    public["cases"][0]["source_turns"][0]["user"] += " drift"
    path = root / "public-l2.json"
    path.chmod(0o644)
    path.write_text(json.dumps(public, ensure_ascii=False), encoding="utf-8")
    path.chmod(0o444)
    with pytest.raises(ValueError, match="artifact drift"):
        validate_l2_dev_repair_slice(SOURCE, root, PRIOR_ROOTS)


def test_l2_source_rejects_duplicate_private_id_and_extra_case_field() -> None:
    duplicate = load_json(SOURCE)
    duplicate["cases"][1]["private_case_id"] = duplicate["cases"][0][
        "private_case_id"
    ]
    with pytest.raises(ValidationError, match="duplicate private case ID"):
        L2DiagnosticSource.model_validate(duplicate)

    extra = copy.deepcopy(load_json(SOURCE))
    extra["cases"][0]["unexpected"] = "not allowed"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        L2DiagnosticSource.model_validate(extra)


def test_l2_v2_rejects_prompt_incomplete_public_catalog() -> None:
    source = load_json(SOURCE)
    source["schema_version"] = "typed-extractor-l2-diagnostic-source-v2"
    source["dataset_id"] = "typed-extractor-l2-dev-repair-v2"

    with pytest.raises(ValidationError, match="missing L2 V8 public catalogs"):
        L2DiagnosticSource.model_validate(source)


def test_l2_v2_formal_contract_is_complete_and_uses_new_opaque_ids(
    tmp_path: Path,
) -> None:
    output = tmp_path / "v2"
    result = prepare_l2_dev_repair_slice(V2_SOURCE, output, PRIOR_ROOTS)

    assert result["status"] == "valid"
    public = load_json(output / "public-l2.json")
    assert {"operator_kind_bindings", "operator_role_bindings"}.issubset(
        public["allowed_vocabulary"]
    )

    v1_public = load_json(ROOT / "public-l2.json")
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


def test_l2_v2_rejects_catalog_that_does_not_cover_emitted_gold() -> None:
    source = load_json(V2_SOURCE)
    source["public_vocabulary"]["operator_role_bindings"].remove(
        "persist_state|state|persistent condition"
    )

    with pytest.raises(ValidationError, match="L2 V8 operator-role catalog"):
        L2DiagnosticSource.model_validate(source)


def test_l2_v2_rejects_catalog_that_does_not_cover_emission_gold() -> None:
    source = load_json(V2_SOURCE)
    source["public_vocabulary"]["operator_role_bindings"].remove(
        "archive_document|requester|request origin"
    )

    with pytest.raises(
        ValidationError,
        match="L2 V8 public catalog does not cover emitted candidate",
    ):
        L2DiagnosticSource.model_validate(source)


def test_l2_v2_rejects_prompt_incompatible_closure_mapping() -> None:
    source = load_json(V2_SOURCE)
    case = next(
        item for item in source["cases"] if item["private_case_id"] == "emit-state-summary"
    )
    case["expected_typed_candidate"]["closure"]["pattern"] = "temporal_chain"
    case["authority"]["allowed_closure_patterns"] = ["temporal_chain"]

    with pytest.raises(
        ValidationError,
        match="L2 V8 abstraction-to-closure mapping differs",
    ):
        L2DiagnosticSource.model_validate(source)


def test_l2_l1_dependency_ignores_nested_model_run_outputs(
    tmp_path: Path,
) -> None:
    copied_l1 = tmp_path / "l1"
    copied_l1.mkdir()
    for name in (
        "diagnostic-source-l1.json",
        "public-l1.json",
        "authority-l1.json",
        "gold-l1.json",
        "manifest-l1.json",
    ):
        shutil.copy2(V2_ROOT.parent / "typed-extractor-v2-l1-dev-repair-v2" / name, copied_l1 / name)
    nested = copied_l1 / "model-runs" / "run-test"
    nested.mkdir(parents=True)
    (nested / "score.json").write_text('{"status":"audit-only"}', encoding="utf-8")
    (nested / "score.json").chmod(0o444)

    clean_root = tmp_path / "clean"
    nested_root = tmp_path / "nested"
    base_priors = PRIOR_ROOTS[:2]
    prepare_l2_dev_repair_slice(
        V2_SOURCE,
        clean_root,
        (*base_priors, V2_ROOT.parent / "typed-extractor-v2-l1-dev-repair-v2"),
    )
    prepare_l2_dev_repair_slice(
        V2_SOURCE,
        nested_root,
        (*base_priors, copied_l1),
    )

    assert (clean_root / "manifest-l2.json").read_bytes() == (
        nested_root / "manifest-l2.json"
    ).read_bytes()


def test_l2_v3_requires_operator_sense_bindings() -> None:
    source = load_json(V2_SOURCE)
    source["schema_version"] = "typed-extractor-l2-diagnostic-source-v3"
    source["dataset_id"] = "typed-extractor-l2-dev-repair-v3"

    with pytest.raises(ValidationError, match="operator_sense_bindings"):
        L2DiagnosticSource.model_validate(source)


def test_l2_v3_rejects_operator_sense_pair_outside_catalog() -> None:
    source = load_json(V3_SOURCE)
    case = next(
        item
        for item in source["cases"]
        if item["private_case_id"] == "emit-coreference-document-reference"
    )
    case["expected_typed_candidate"]["structured_claims"][0]["predicate"][
        "sense"
    ] = "request.device_service_coreference"

    with pytest.raises(ValidationError, match="operator-sense catalog mismatch"):
        L2DiagnosticSource.model_validate(source)


def test_l2_v3_formal_contract_has_closed_pairs_and_new_opaque_ids(
    tmp_path: Path,
) -> None:
    output = tmp_path / "v3"
    result = prepare_l2_dev_repair_slice(V3_SOURCE, output, PRIOR_ROOTS)

    assert result["status"] == "valid"
    public = load_json(output / "public-l2.json")
    pairs = set(public["allowed_vocabulary"]["operator_sense_bindings"])
    gold = load_json(output / "gold-l2.json")
    gold_pairs = {
        "|".join(
            (
                claim["predicate"]["canonical_operator"],
                claim["predicate"]["sense"],
            )
        )
        for item in gold["items"]
        if item["expected_typed_candidate"] is not None
        for claim in item["expected_typed_candidate"]["structured_claims"]
    }
    assert gold_pairs.issubset(pairs)

    v2_public = load_json(V2_ROOT / "public-l2.json")
    assert {case["case_id"] for case in public["cases"]}.isdisjoint(
        case["case_id"] for case in v2_public["cases"]
    )


def test_l2_v9_prompt_defines_abstraction_dominance_and_pair_closure() -> None:
    prompt = V9_PROMPT.read_text(encoding="utf-8")

    assert prompt.startswith("# Typed Extractor V2 L2 Dev Proposer Contract V9")
    assert "`long_running_state`" in prompt
    assert "`state_summary`" in prompt
    assert "`preference_profile`" in prompt
    assert "`preference_aggregation`" in prompt
    assert "`operator_sense_bindings`" in prompt
    assert "`archive_document|document.archive_coreference`" in prompt
    assert "case-708f1fbac44a3041" not in prompt
    assert "case-f53b582ca339e502" not in prompt
