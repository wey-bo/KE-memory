from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tools.natural_memory_benchmark.io import load_json
from tools.natural_memory_benchmark.typed_extractor_taxonomy_dev import (
    author_taxonomy_dev_sources,
    prepare_taxonomy_dev_slice,
    validate_taxonomy_dev_slice,
)


WORKSPACE = Path(__file__).resolve().parents[2]
ASSESSMENT = WORKSPACE / "artifacts/automatic-extraction-assessment"
L1_ROOT = ASSESSMENT / "typed-extractor-taxonomy-l1-dev-v1"
L2_ROOT = ASSESSMENT / "typed-extractor-taxonomy-l2-dev-v1"
L1_PRIORS = (
    ASSESSMENT / "typed-extractor-v2-l1-dev-repair-v1",
    ASSESSMENT / "typed-extractor-v2-l1-dev-repair-v2",
)
L2_PRIORS = (
    L1_ROOT,
    ASSESSMENT / "typed-extractor-v2-l2-dev-repair-v1",
    ASSESSMENT / "typed-extractor-v2-l2-dev-repair-v2",
    ASSESSMENT / "typed-extractor-v2-l2-dev-repair-v3",
)
L1_TEMPLATE = L1_PRIORS[-1] / "diagnostic-source-l1.json"
L2_TEMPLATE = L2_PRIORS[-1] / "diagnostic-source-l2.json"


def _write_source(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(0o444)


def _assert_public_has_no_private_labels(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for forbidden in (
        "private_case_id",
        "primary_family",
        "secondary_families",
        "expected_decision",
        "expected_typed_candidate",
        "authority",
    ):
        assert forbidden not in text


def test_l1_preparation_accepts_multiple_prior_l1_roots(tmp_path: Path) -> None:
    l1_root = tmp_path / "l1"
    l2_root = tmp_path / "l2"
    author_taxonomy_dev_sources(
        L1_TEMPLATE,
        L2_TEMPLATE,
        l1_root / "diagnostic-source-l1.json",
        l2_root / "diagnostic-source-l2.json",
    )

    result = prepare_taxonomy_dev_slice(
        l1_root / "diagnostic-source-l1.json", "l1", l1_root, L1_PRIORS
    )

    assert result["status"] == "valid"
    assert result["case_count"] == 20


@pytest.mark.parametrize(
    ("layer", "root", "source_name", "priors"),
    [
        ("l1", L1_ROOT, "diagnostic-source-l1.json", L1_PRIORS),
        ("l2", L2_ROOT, "diagnostic-source-l2.json", L2_PRIORS),
    ],
)
def test_source_rejects_duplicate_authority_ids(
    tmp_path: Path,
    layer: str,
    root: Path,
    source_name: str,
    priors: tuple[Path, ...],
) -> None:
    payload = load_json(root / source_name)
    payload["cases"][1]["authority"]["knowledge_id"] = payload["cases"][0][
        "authority"
    ]["knowledge_id"]
    payload["cases"][1]["authority"]["candidate_id"] = payload["cases"][0][
        "authority"
    ]["candidate_id"]
    source = tmp_path / source_name
    _write_source(source, payload)
    output = tmp_path / "out"
    output.mkdir()

    with pytest.raises(ValueError, match="duplicate .* authority (knowledge|candidate) ID"):
        prepare_taxonomy_dev_slice(source, layer, output, priors)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("schema_version", "typed-extractor-taxonomy-l1-source-v0"),
        ("dataset_id", "typed-extractor-taxonomy-l1-dev-other"),
    ],
)
def test_source_rejects_version_or_dataset_mismatch(
    tmp_path: Path, key: str, value: str
) -> None:
    payload = load_json(L1_ROOT / "diagnostic-source-l1.json")
    payload[key] = value
    source = tmp_path / "diagnostic-source-l1.json"
    _write_source(source, payload)
    output = tmp_path / "out"
    output.mkdir()

    with pytest.raises(ValueError, match=key):
        prepare_taxonomy_dev_slice(source, "l1", output, L1_PRIORS)


def test_source_rejects_invalid_evidence_span(tmp_path: Path) -> None:
    payload = load_json(L1_ROOT / "diagnostic-source-l1.json")
    payload["cases"][0]["untyped_candidate"]["evidence"][0]["start"] += 1
    source = tmp_path / "diagnostic-source-l1.json"
    _write_source(source, payload)
    output = tmp_path / "out"
    output.mkdir()

    with pytest.raises(ValueError, match="evidence offset mismatch"):
        prepare_taxonomy_dev_slice(source, "l1", output, L1_PRIORS)


@pytest.mark.parametrize("identifier_key", ["knowledge_id", "candidate_id"])
def test_authority_id_overlap_with_prior_fails_closed(
    tmp_path: Path, identifier_key: str
) -> None:
    payload = load_json(L1_ROOT / "diagnostic-source-l1.json")
    prior = tmp_path / "prior"
    prior.mkdir()
    prior_payload = {identifier_key: payload["cases"][0]["authority"][identifier_key]}
    _write_source(prior / "identity.json", prior_payload)
    output = tmp_path / "out"
    output.mkdir()

    with pytest.raises(ValueError, match="prior identifier overlap"):
        prepare_taxonomy_dev_slice(
            L1_ROOT / "diagnostic-source-l1.json",
            "l1",
            output,
            (*L1_PRIORS, prior),
        )


@pytest.mark.parametrize("tamper", ["authority_support", "gold_closure"])
def test_l2_support_or_closure_tamper_fails_closed(
    tmp_path: Path, tamper: str
) -> None:
    payload = load_json(L2_ROOT / "diagnostic-source-l2.json")
    case = next(item for item in payload["cases"] if item["expected_typed_candidate"])
    if tamper == "authority_support":
        case["authority"]["required_support_refs"] = list(
            reversed(case["authority"]["required_support_refs"])
        )
    else:
        case["expected_typed_candidate"]["closure"]["required_support_refs"] = [
            case["expected_typed_candidate"]["closure"]["required_support_refs"][0]
        ]
    source = tmp_path / "diagnostic-source-l2.json"
    _write_source(source, payload)
    output = tmp_path / "out"
    output.mkdir()

    with pytest.raises(ValueError, match="support closure"):
        prepare_taxonomy_dev_slice(source, "l2", output, L2_PRIORS)


@pytest.mark.parametrize(
    ("root", "source_name", "public_name"),
    [
        (L1_ROOT, "diagnostic-source-l1.json", "public-l1.json"),
        (L2_ROOT, "diagnostic-source-l2.json", "public-l2.json"),
    ],
)
def test_public_projection_contains_no_private_identity_values(
    root: Path, source_name: str, public_name: str
) -> None:
    source = load_json(root / source_name)
    private_values: set[str] = set()
    private_reference_keys = {
        "evidence_id",
        "evidence_ids",
        "replacement_candidate_ref",
        "replaces_candidate_refs",
        "supersedes_candidate_refs",
        "conflicts_with_candidate_refs",
        "confirmed_by_operation_refs",
        "added_by_operation_refs",
    }

    def collect_private_references(value: object, key: str | None = None) -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                collect_private_references(child, child_key)
        elif isinstance(value, list):
            for child in value:
                collect_private_references(child, key)
        elif isinstance(value, str) and key in private_reference_keys:
            private_values.add(value)

    collect_private_references(source)
    for case in source["cases"]:
        private_values.add(case["private_case_id"])
        private_values.update(case["authority"][key] for key in ("knowledge_id", "candidate_id"))
        for key in ("private_session_id",):
            if key in case:
                private_values.add(case[key])
        private_values.update(
            turn["private_turn_id"] for turn in case.get("source_turns", [])
        )
        private_values.update(
            support["private_support_id"]
            for support in case.get("typed_l1_support_pack", [])
        )
    public_text = (root / public_name).read_text(encoding="utf-8")

    assert not {value for value in private_values if value in public_text}


@pytest.mark.parametrize(
    ("layer", "root", "source_name", "priors", "case_count"),
    [
        ("l1", L1_ROOT, "diagnostic-source-l1.json", L1_PRIORS, 20),
        ("l2", L2_ROOT, "diagnostic-source-l2.json", L2_PRIORS, 12),
    ],
)
def test_formal_taxonomy_slice_validates_and_replays(
    tmp_path: Path,
    layer: str,
    root: Path,
    source_name: str,
    priors: tuple[Path, ...],
    case_count: int,
) -> None:
    source = root / source_name
    result = validate_taxonomy_dev_slice(source, layer, root, priors)
    assert result["status"] == "valid"
    assert result["case_count"] == case_count
    assert result["diagnostic_only"] is True
    assert result["prior_identifier_overlap_count"] == 0
    assert result["prior_evidence_overlap_count"] == 0

    replay = tmp_path / layer
    replay.mkdir()
    prepare_taxonomy_dev_slice(source, layer, replay, priors)
    expected_names = {
        source_name,
        f"public-{layer}.json",
        f"authority-{layer}.json",
        f"gold-{layer}.json",
        f"manifest-{layer}.json",
    }
    for name in expected_names - {source_name}:
        assert (replay / name).read_bytes() == (root / name).read_bytes()
    for name in expected_names:
        formal = root / name
        assert formal.stat().st_mode & 0o777 == 0o444
    _assert_public_has_no_private_labels(root / f"public-{layer}.json")


def test_l1_distribution_is_exact() -> None:
    result = validate_taxonomy_dev_slice(
        L1_ROOT / "diagnostic-source-l1.json", "l1", L1_ROOT, L1_PRIORS
    )
    assert result["primary_family_counts"] == {
        "condition_or_scope": 3,
        "derivation_or_speaker": 1,
        "evidence": 2,
        "false_abstention": 3,
        "false_emission": 3,
        "lifecycle": 1,
        "role_or_local_entity": 4,
        "time": 3,
    }
    assert result["non_emission_count"] == 4


def test_l2_distribution_and_closure_are_exact() -> None:
    result = validate_taxonomy_dev_slice(
        L2_ROOT / "diagnostic-source-l2.json", "l2", L2_ROOT, L2_PRIORS
    )
    assert result["emit_count"] == 8
    assert result["abstain_count"] == 4
    assert result["abstraction_method_counts"] == {
        "coreference_resolution": 2,
        "lifecycle_resolution": 2,
        "preference_aggregation": 1,
        "state_summary": 1,
        "task_composition": 2,
    }


def test_source_models_reject_extra_fields(tmp_path: Path) -> None:
    copied = tmp_path / "diagnostic-source-l1.json"
    payload = load_json(L1_ROOT / "diagnostic-source-l1.json")
    payload["unexpected"] = True
    copied.write_text(json.dumps(payload), encoding="utf-8")
    copied.chmod(0o444)
    output = tmp_path / "out"
    output.mkdir()
    with pytest.raises(ValueError, match="extra"):
        prepare_taxonomy_dev_slice(copied, "l1", output, L1_PRIORS)


def test_prior_overlap_fails_closed(tmp_path: Path) -> None:
    copied_root = tmp_path / "prior"
    copied_root.mkdir()
    shutil.copy2(L1_ROOT / "diagnostic-source-l1.json", copied_root / "copy.json")
    output = tmp_path / "output"
    output.mkdir()
    with pytest.raises(ValueError, match="prior (identifier|evidence) overlap"):
        prepare_taxonomy_dev_slice(
            L1_ROOT / "diagnostic-source-l1.json",
            "l1",
            output,
            (*L1_PRIORS, copied_root),
        )


def test_mutable_formal_output_is_rejected(tmp_path: Path) -> None:
    copied = tmp_path / "root"
    shutil.copytree(L1_ROOT, copied)
    (copied / "public-l1.json").chmod(0o644)
    with pytest.raises(ValueError, match="read-only"):
        validate_taxonomy_dev_slice(
            copied / "diagnostic-source-l1.json", "l1", copied, L1_PRIORS
        )
