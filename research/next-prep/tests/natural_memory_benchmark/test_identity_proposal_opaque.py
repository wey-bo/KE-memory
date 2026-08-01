from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.natural_memory_benchmark.identity_proposal_opaque import (
    CASE_ID_RE,
    MENTION_ID_RE,
    derive_opaque_id,
    prepare_opaque_identity_slice,
    validate_opaque_identity_slice,
)
from tools.natural_memory_benchmark.io import (
    canonical_json_bytes,
    load_json,
    sha256_file,
)


V1_SOURCE = Path(
    "artifacts/identity-memory-experiment/natural-v1/source-cases.json"
)
WORKSPACE_ROOT = Path(".")
SLICE_FILES = (
    "source-cases.json",
    "opaque-id-map.json",
    "preregistration.json",
    "public.json",
    "authority.json",
    "gold.json",
    "manifest.json",
)


def _replace_json(path: Path, payload: object) -> None:
    path.chmod(0o644)
    path.write_bytes(canonical_json_bytes(payload))


def _refresh_manifest_and_preregistration(root: Path) -> None:
    manifest_path = root / "manifest.json"
    manifest = load_json(manifest_path)
    manifest["source_config_sha256"] = sha256_file(root / "source-cases.json")
    manifest["output_sha256"] = {
        name: sha256_file(root / name)
        for name in ("public.json", "authority.json", "gold.json")
    }
    _replace_json(manifest_path, manifest)

    preregistration_path = root / "preregistration.json"
    preregistration = load_json(preregistration_path)
    preregistration["files_sha256"] = {
        name: sha256_file(root / name)
        for name in (
            "source-cases.json",
            "opaque-id-map.json",
            "public.json",
            "authority.json",
            "gold.json",
            "manifest.json",
        )
    }
    _replace_json(preregistration_path, preregistration)


def test_derive_opaque_id_is_stable_typed_and_source_sensitive():
    first = derive_opaque_id("namespace", "case", 1, "source-a")
    assert first == derive_opaque_id("namespace", "case", 1, "source-a")
    assert CASE_ID_RE.fullmatch(first)
    assert first != derive_opaque_id("namespace", "case", 2, "source-a")
    assert first != derive_opaque_id("namespace", "case", 1, "source-b")
    assert MENTION_ID_RE.fullmatch(
        derive_opaque_id("namespace", "mention", 1, "source-a")
    )


def test_prepare_is_deterministic_opaque_and_semantically_equivalent(tmp_path):
    root = tmp_path / "natural-v2"
    first = prepare_opaque_identity_slice(
        V1_SOURCE,
        root,
        workspace_root=WORKSPACE_ROOT,
    )
    first_bytes = {name: (root / name).read_bytes() for name in SLICE_FILES}
    second = prepare_opaque_identity_slice(
        V1_SOURCE,
        root,
        workspace_root=WORKSPACE_ROOT,
    )

    assert first == second
    assert first_bytes == {name: (root / name).read_bytes() for name in SLICE_FILES}
    assert first["case_count"] == 12
    assert first["dev_count"] == 6
    assert first["hidden_count"] == 6
    assert first["identifier_policy_valid"] is True
    assert first["semantic_equivalence_valid"] is True

    public = load_json(root / "public.json")
    assert public["dataset_id"] == "natural-identity-membership-opaque-v2"
    assert all(CASE_ID_RE.fullmatch(case["case_id"]) for case in public["cases"])
    assert all(
        MENTION_ID_RE.fullmatch(mention["mention_id"])
        for case in public["cases"]
        for mention in case["mentions"]
    )

    mapping = load_json(root / "opaque-id-map.json")
    assert len(mapping["case_ids"]) == 12
    assert len(mapping["mention_ids"]) == 18
    assert len({item["v2"] for item in mapping["case_ids"]}) == 12
    assert len({item["v2"] for item in mapping["mention_ids"]}) == 18

    public_text = (root / "public.json").read_text(encoding="utf-8")
    assert all(item["v1"] not in public_text for item in mapping["case_ids"])
    assert all(item["v1"] not in public_text for item in mapping["mention_ids"])
    assert all((root / name).stat().st_mode & 0o777 == 0o444 for name in SLICE_FILES)

    validation = validate_opaque_identity_slice(
        V1_SOURCE,
        root,
        workspace_root=WORKSPACE_ROOT,
    )
    assert validation["status"] == "valid"
    assert validation["identifier_policy_valid"] is True
    assert validation["semantic_equivalence_valid"] is True


def test_validate_rejects_non_opaque_case_and_mention_ids(tmp_path):
    root = tmp_path / "natural-v2"
    prepare_opaque_identity_slice(V1_SOURCE, root, workspace_root=WORKSPACE_ROOT)
    public_path = root / "public.json"
    public = load_json(public_path)
    public["cases"][0]["case_id"] = "case-distinct"
    _replace_json(public_path, public)
    with pytest.raises(ValueError, match="opaque case id"):
        validate_opaque_identity_slice(V1_SOURCE, root, workspace_root=WORKSPACE_ROOT)

    root = tmp_path / "natural-v2-mention"
    prepare_opaque_identity_slice(V1_SOURCE, root, workspace_root=WORKSPACE_ROOT)
    public_path = root / "public.json"
    public = load_json(public_path)
    public["cases"][0]["mentions"][0]["mention_id"] = "mention-unresolved"
    _replace_json(public_path, public)
    with pytest.raises(ValueError, match="opaque mention id"):
        validate_opaque_identity_slice(V1_SOURCE, root, workspace_root=WORKSPACE_ROOT)


def test_validate_rejects_v1_id_residue_and_semantic_drift(tmp_path):
    root = tmp_path / "natural-v2"
    prepare_opaque_identity_slice(V1_SOURCE, root, workspace_root=WORKSPACE_ROOT)
    mapping = load_json(root / "opaque-id-map.json")
    public_path = root / "public.json"
    public = load_json(public_path)
    public["cases"][0]["question"] += f" [{mapping['case_ids'][0]['v1']}]"
    _replace_json(public_path, public)
    with pytest.raises(ValueError, match="v1 identifier residue"):
        validate_opaque_identity_slice(V1_SOURCE, root, workspace_root=WORKSPACE_ROOT)

    root = tmp_path / "natural-v2-drift"
    prepare_opaque_identity_slice(V1_SOURCE, root, workspace_root=WORKSPACE_ROOT)
    source_path = root / "source-cases.json"
    source = load_json(source_path)
    source["cases"][0]["question"] = "A semantically different question"
    _replace_json(source_path, source)
    with pytest.raises(ValueError, match="semantic equivalence"):
        validate_opaque_identity_slice(V1_SOURCE, root, workspace_root=WORKSPACE_ROOT)


def test_validate_rejects_coordinated_gold_semantic_drift(tmp_path):
    root = tmp_path / "natural-v2"
    prepare_opaque_identity_slice(V1_SOURCE, root, workspace_root=WORKSPACE_ROOT)
    gold_path = root / "gold.json"
    gold = load_json(gold_path)
    gold["items"][0]["expected_action"] = "abstain"
    _replace_json(gold_path, gold)
    _refresh_manifest_and_preregistration(root)

    with pytest.raises(ValueError, match="derived artifact semantic equivalence"):
        validate_opaque_identity_slice(V1_SOURCE, root, workspace_root=WORKSPACE_ROOT)


def test_validate_rejects_wrong_mapping_namespace(tmp_path):
    root = tmp_path / "natural-v2"
    prepare_opaque_identity_slice(V1_SOURCE, root, workspace_root=WORKSPACE_ROOT)
    mapping_path = root / "opaque-id-map.json"
    mapping = load_json(mapping_path)
    mapping["namespace"] = "natural-identity-membership-opaque-v2:wrong"
    _replace_json(mapping_path, mapping)
    _refresh_manifest_and_preregistration(root)

    with pytest.raises(ValueError, match="namespace"):
        validate_opaque_identity_slice(V1_SOURCE, root, workspace_root=WORKSPACE_ROOT)


def test_validate_rejects_coordinated_non_derived_case_id(tmp_path):
    root = tmp_path / "natural-v2"
    prepare_opaque_identity_slice(V1_SOURCE, root, workspace_root=WORKSPACE_ROOT)
    old_case_id = load_json(root / "opaque-id-map.json")["case_ids"][0]["v2"]
    replacement = "case-0000000000000000"

    mapping_path = root / "opaque-id-map.json"
    mapping = load_json(mapping_path)
    mapping["case_ids"][0]["v2"] = replacement
    _replace_json(mapping_path, mapping)

    source_path = root / "source-cases.json"
    source = load_json(source_path)
    source["cases"][0]["case_id"] = replacement
    _replace_json(source_path, source)

    for name, collection in (
        ("public.json", "cases"),
        ("authority.json", "cases"),
        ("gold.json", "items"),
    ):
        path = root / name
        payload = load_json(path)
        item = next(entry for entry in payload[collection] if entry["case_id"] == old_case_id)
        item["case_id"] = replacement
        _replace_json(path, payload)
    _refresh_manifest_and_preregistration(root)

    with pytest.raises(ValueError, match="derived opaque case id"):
        validate_opaque_identity_slice(V1_SOURCE, root, workspace_root=WORKSPACE_ROOT)


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("claim_boundary", "automatic_merge_authorized", True),
        ("validation", "semantic_equivalence_valid", False),
    ],
)
def test_validate_rejects_preregistration_policy_drift(
    tmp_path,
    section,
    field,
    value,
):
    root = tmp_path / f"natural-v2-{section}"
    prepare_opaque_identity_slice(V1_SOURCE, root, workspace_root=WORKSPACE_ROOT)
    preregistration_path = root / "preregistration.json"
    preregistration = load_json(preregistration_path)
    preregistration[section][field] = value
    _replace_json(preregistration_path, preregistration)

    with pytest.raises(ValueError, match=field):
        validate_opaque_identity_slice(V1_SOURCE, root, workspace_root=WORKSPACE_ROOT)


def test_validate_rejects_mutated_formal_slice_file(tmp_path):
    """A tampered slice artifact must be refused by content.

    Was: chmod to 0644 and expect "must be read-only". That could not hold on a
    fresh clone, where every file is writable. The property that matters is that
    changed bytes are rejected, which files_sha256 in the preregistration covers.
    """
    root = tmp_path / "natural-v2"
    prepare_opaque_identity_slice(V1_SOURCE, root, workspace_root=WORKSPACE_ROOT)
    target = root / "public.json"
    target.chmod(0o644)
    original = target.read_bytes()
    mutated = original.replace(b'"concept_id":"memory:Person"', b'"concept_id":"memory:Poster"', 1)
    assert len(mutated) == len(original) and mutated != original, (
        "the mutation must actually change a byte, or this test proves nothing"
    )
    target.write_bytes(mutated)

    with pytest.raises(ValueError):
        validate_opaque_identity_slice(V1_SOURCE, root, workspace_root=WORKSPACE_ROOT)


def test_validate_accepts_writable_formal_slice_after_a_clone(tmp_path):
    """The inverse: unchanged bytes at clone mode must validate."""
    root = tmp_path / "natural-v2"
    prepare_opaque_identity_slice(V1_SOURCE, root, workspace_root=WORKSPACE_ROOT)
    for path in root.rglob("*"):
        if path.is_file():
            path.chmod(0o644)

    validate_opaque_identity_slice(V1_SOURCE, root, workspace_root=WORKSPACE_ROOT)


def test_prepare_rejects_conflicting_existing_mapping(tmp_path):
    root = tmp_path / "natural-v2"
    prepare_opaque_identity_slice(V1_SOURCE, root, workspace_root=WORKSPACE_ROOT)
    mapping_path = root / "opaque-id-map.json"
    mapping_path.chmod(0o644)
    mapping_path.write_text(json.dumps({"tampered": True}) + "\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="immutable artifact differs"):
        prepare_opaque_identity_slice(V1_SOURCE, root, workspace_root=WORKSPACE_ROOT)
