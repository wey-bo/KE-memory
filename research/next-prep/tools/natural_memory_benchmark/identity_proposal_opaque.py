from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .identity_proposal import (
    SourceConfig,
    freeze_natural_identity_slice,
    validate_natural_identity_slice,
)
from .io import canonical_json_bytes, load_json, sha256_file, write_json_immutable


OPAQUE_DATASET_ID = "natural-identity-membership-opaque-v2"
OPAQUE_NAMESPACE = "natural-identity-membership-opaque-v2:2026-07-27"
CASE_ID_RE = re.compile(r"case-[0-9a-f]{16}")
MENTION_ID_RE = re.compile(r"mention-[0-9a-f]{16}")

PROPOSAL_THRESHOLDS = {
    "raw_action_accuracy_min": 0.85,
    "raw_critical_false_merge_count_max": 0,
    "raw_critical_false_membership_count_max": 0,
    "raw_abstention_f1_min": 0.80,
    "proposal_evidence_exactness_min": 0.95,
}

PROTECTED_PATHS = (
    "artifacts/identity-memory-experiment/natural-v1/public.json",
    "artifacts/identity-memory-experiment/natural-v1/authority.json",
    "artifacts/identity-memory-experiment/natural-v1/gold.json",
    "artifacts/identity-memory-experiment/natural-v1/manifest.json",
    "artifacts/identity-memory-experiment/natural-v1/reference-score.json",
    "artifacts/identity-memory-experiment/natural-v1/reference-report.md",
    "artifacts/identity-memory-experiment/natural-v1/model-runs/run-20260727T104020Z-codex-gpt-5-6-sol-proposal-only-v1/proposals.json",
    "artifacts/identity-memory-experiment/natural-v1/model-runs/run-20260727T104020Z-codex-gpt-5-6-sol-proposal-only-v1/score.json",
    "artifacts/identity-memory-experiment/natural-v1/model-runs/run-20260727T104020Z-codex-gpt-5-6-sol-proposal-only-v1/report.md",
    "artifacts/identity-memory-experiment/reports/identity-conformance-report-v1.md",
    "artifacts/identity-memory-experiment/runs/run-20260727T080000Z-identity-v1/identity-conformance-results-v1.json",
    "artifacts/natural-benchmark-slices/slice-v1/representation-conformance-report-v5.md",
    "artifacts/natural-benchmark-slices/slice-v1/representation-conformance-results-v5.json",
)

SLICE_FILES = (
    "source-cases.json",
    "opaque-id-map.json",
    "preregistration.json",
    "public.json",
    "authority.json",
    "gold.json",
    "manifest.json",
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class OpaqueIdPair(StrictModel):
    ordinal: int = Field(ge=1)
    v1: str = Field(min_length=1)
    v2: str = Field(min_length=1)


class OpaqueIdMap(StrictModel):
    schema_version: Literal["natural-identity-opaque-id-map-v1"] = (
        "natural-identity-opaque-id-map-v1"
    )
    source_dataset_id: str = Field(min_length=1)
    dataset_id: Literal["natural-identity-membership-opaque-v2"] = OPAQUE_DATASET_ID
    namespace: Literal["natural-identity-membership-opaque-v2:2026-07-27"] = (
        OPAQUE_NAMESPACE
    )
    derivation: Literal["sha256-namespace-kind-ordinal-source-prefix16"] = (
        "sha256-namespace-kind-ordinal-source-prefix16"
    )
    case_ids: list[OpaqueIdPair] = Field(min_length=1)
    mention_ids: list[OpaqueIdPair] = Field(min_length=1)


class OpaqueIdentifierPolicy(StrictModel):
    case_pattern: Literal["case-[0-9a-f]{16}"] = CASE_ID_RE.pattern
    mention_pattern: Literal["mention-[0-9a-f]{16}"] = MENTION_ID_RE.pattern
    old_id_residue_allowed: Literal[False] = False
    mapping_must_be_bijective: Literal[True] = True


class OpaqueProposalQualityThresholds(StrictModel):
    raw_action_accuracy_min: float
    raw_critical_false_merge_count_max: int
    raw_critical_false_membership_count_max: int
    raw_abstention_f1_min: float
    proposal_evidence_exactness_min: float


class OpaqueValidationFlags(StrictModel):
    identifier_policy_valid: Literal[True] = True
    semantic_equivalence_valid: Literal[True] = True
    source_validation_valid: Literal[True] = True
    manifest_integrity_valid: Literal[True] = True


class OpaqueClaimBoundary(StrictModel):
    automatic_merge_authorized: Literal[False] = False
    automatic_membership_write_authorized: Literal[False] = False
    automatic_l2_write_authorized: Literal[False] = False
    embedding_is_authority: Literal[False] = False
    longmemeval_status: Literal["structured_l2_identity_unresolved"] = (
        "structured_l2_identity_unresolved"
    )
    external_memory_systems_rerun: Literal[False] = False
    isolation_enforcement: Literal["declarative-agent-file-access-contract"] = (
        "declarative-agent-file-access-contract"
    )


class OpaquePreregistration(StrictModel):
    schema_version: Literal["natural-identity-opaque-preregistration-v1"] = (
        "natural-identity-opaque-preregistration-v1"
    )
    dataset_id: Literal["natural-identity-membership-opaque-v2"] = OPAQUE_DATASET_ID
    status: Literal["frozen"] = "frozen"
    core_impact: Literal["none"] = "none"
    v1_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    files_sha256: dict[str, str]
    protected_sha256: dict[str, str]
    identifier_policy: OpaqueIdentifierPolicy
    proposal_quality_thresholds: OpaqueProposalQualityThresholds
    validation: OpaqueValidationFlags
    claim_boundary: OpaqueClaimBoundary


def derive_opaque_id(
    namespace: str,
    kind: Literal["case", "mention"],
    ordinal: int,
    source_id: str,
) -> str:
    material = f"{namespace}\0{kind}\0{ordinal}\0{source_id}".encode("utf-8")
    prefix = "case" if kind == "case" else "mention"
    return f"{prefix}-{hashlib.sha256(material).hexdigest()[:16]}"


def _resolve(path: Path, workspace_root: Path) -> Path:
    return path.resolve() if path.is_absolute() else (workspace_root / path).resolve()


def _build_v2_source(
    source: SourceConfig,
    *,
    namespace: str,
) -> tuple[dict[str, Any], OpaqueIdMap]:
    payload = source.model_dump(mode="json", exclude_unset=True)
    payload["dataset_id"] = OPAQUE_DATASET_ID
    case_pairs: list[OpaqueIdPair] = []
    mention_pairs: list[OpaqueIdPair] = []
    mention_ordinal = 0

    for case_ordinal, case in enumerate(payload["cases"], start=1):
        v1_case_id = case["case_id"]
        v2_case_id = derive_opaque_id(namespace, "case", case_ordinal, v1_case_id)
        case_pairs.append(OpaqueIdPair(ordinal=case_ordinal, v1=v1_case_id, v2=v2_case_id))
        case["case_id"] = v2_case_id

        mention_mapping: dict[str, str] = {}
        for mention in case["mentions"]:
            mention_ordinal += 1
            v1_mention_id = mention["mention_id"]
            v2_mention_id = derive_opaque_id(
                namespace,
                "mention",
                mention_ordinal,
                v1_mention_id,
            )
            mention_pairs.append(
                OpaqueIdPair(
                    ordinal=mention_ordinal,
                    v1=v1_mention_id,
                    v2=v2_mention_id,
                )
            )
            mention_mapping[v1_mention_id] = v2_mention_id
            mention["mention_id"] = v2_mention_id
        case["authority"]["required_mention_ids"] = [
            mention_mapping[item]
            for item in case["authority"]["required_mention_ids"]
        ]

    mapping = OpaqueIdMap(
        source_dataset_id=source.dataset_id,
        namespace=namespace,
        case_ids=case_pairs,
        mention_ids=mention_pairs,
    )
    _validate_mapping(mapping)
    SourceConfig.model_validate(payload)
    return payload, mapping


def _validate_mapping(mapping: OpaqueIdMap) -> None:
    if mapping.namespace != OPAQUE_NAMESPACE:
        raise ValueError("opaque mapping namespace mismatch")
    v1_cases = [item.v1 for item in mapping.case_ids]
    v2_cases = [item.v2 for item in mapping.case_ids]
    v1_mentions = [item.v1 for item in mapping.mention_ids]
    v2_mentions = [item.v2 for item in mapping.mention_ids]
    if len(v1_cases) != len(set(v1_cases)) or len(v2_cases) != len(set(v2_cases)):
        raise ValueError("opaque case id mapping must be bijective")
    if len(v1_mentions) != len(set(v1_mentions)) or len(v2_mentions) != len(set(v2_mentions)):
        raise ValueError("opaque mention id mapping must be bijective")
    if [item.ordinal for item in mapping.case_ids] != list(
        range(1, len(mapping.case_ids) + 1)
    ):
        raise ValueError("opaque case id ordinals must be contiguous")
    if [item.ordinal for item in mapping.mention_ids] != list(
        range(1, len(mapping.mention_ids) + 1)
    ):
        raise ValueError("opaque mention id ordinals must be contiguous")
    for item in mapping.case_ids:
        if not CASE_ID_RE.fullmatch(item.v2):
            raise ValueError(f"invalid opaque case id: {item.v2}")
        if item.v2 != derive_opaque_id(
            OPAQUE_NAMESPACE,
            "case",
            item.ordinal,
            item.v1,
        ):
            raise ValueError(f"invalid derived opaque case id: {item.v2}")
    for item in mapping.mention_ids:
        if not MENTION_ID_RE.fullmatch(item.v2):
            raise ValueError(f"invalid opaque mention id: {item.v2}")
        if item.v2 != derive_opaque_id(
            OPAQUE_NAMESPACE,
            "mention",
            item.ordinal,
            item.v1,
        ):
            raise ValueError(f"invalid derived opaque mention id: {item.v2}")


def _reverse_v2_source(
    source: dict[str, Any],
    mapping: OpaqueIdMap,
) -> dict[str, Any]:
    payload = deepcopy(source)
    payload["dataset_id"] = mapping.source_dataset_id
    case_reverse = {item.v2: item.v1 for item in mapping.case_ids}
    mention_reverse = {item.v2: item.v1 for item in mapping.mention_ids}
    for case in payload["cases"]:
        try:
            case["case_id"] = case_reverse[case["case_id"]]
            for mention in case["mentions"]:
                mention["mention_id"] = mention_reverse[mention["mention_id"]]
            case["authority"]["required_mention_ids"] = [
                mention_reverse[item]
                for item in case["authority"]["required_mention_ids"]
            ]
        except KeyError as exc:
            raise ValueError(f"opaque mapping does not cover source id: {exc.args[0]}") from exc
    return payload


def _check_source_equivalence(
    v1_source: dict[str, Any],
    v2_source: dict[str, Any],
    mapping: OpaqueIdMap,
) -> None:
    reversed_v2 = _reverse_v2_source(v2_source, mapping)
    if canonical_json_bytes(reversed_v2) != canonical_json_bytes(v1_source):
        raise ValueError("v1/v2 semantic equivalence mismatch")


def _remap_v1_derived_artifact(
    payload: dict[str, Any],
    mapping: OpaqueIdMap,
    *,
    name: Literal["public.json", "authority.json", "gold.json"],
) -> dict[str, Any]:
    remapped = deepcopy(payload)
    remapped["dataset_id"] = OPAQUE_DATASET_ID
    case_forward = {item.v1: item.v2 for item in mapping.case_ids}
    mention_forward = {item.v1: item.v2 for item in mapping.mention_ids}
    collection = "items" if name == "gold.json" else "cases"
    try:
        for item in remapped[collection]:
            item["case_id"] = case_forward[item["case_id"]]
            if name == "public.json":
                for mention in item["mentions"]:
                    mention["mention_id"] = mention_forward[mention["mention_id"]]
            elif name == "authority.json":
                item["trusted_actor_bindings"] = {
                    mention_forward[mention_id]: actor_id
                    for mention_id, actor_id in item["trusted_actor_bindings"].items()
                }
                item["required_mention_ids"] = [
                    mention_forward[mention_id]
                    for mention_id in item["required_mention_ids"]
                ]
    except KeyError as exc:
        raise ValueError(
            f"opaque mapping does not cover v1 derived artifact id: {exc.args[0]}"
        ) from exc
    return remapped


def _check_derived_artifact_equivalence(
    v1_root: Path,
    v2_root: Path,
    mapping: OpaqueIdMap,
) -> None:
    for name in ("public.json", "authority.json", "gold.json"):
        v1_path = v1_root / name
        if not v1_path.is_file():
            raise FileNotFoundError(f"v1 derived artifact missing: {v1_path}")
        expected = _remap_v1_derived_artifact(
            load_json(v1_path),
            mapping,
            name=name,
        )
        actual = load_json(v2_root / name)
        if canonical_json_bytes(actual) != canonical_json_bytes(expected):
            raise ValueError(
                f"derived artifact semantic equivalence mismatch: {name}"
            )


def _check_public_identifier_policy(
    public: dict[str, Any],
    mapping: OpaqueIdMap,
) -> None:
    case_ids: list[str] = []
    mention_ids: list[str] = []
    for case in public.get("cases", []):
        case_id = str(case.get("case_id", ""))
        if not CASE_ID_RE.fullmatch(case_id):
            raise ValueError(f"invalid opaque case id: {case_id}")
        case_ids.append(case_id)
        for mention in case.get("mentions", []):
            mention_id = str(mention.get("mention_id", ""))
            if not MENTION_ID_RE.fullmatch(mention_id):
                raise ValueError(f"invalid opaque mention id: {mention_id}")
            mention_ids.append(mention_id)
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("duplicate opaque case id")
    if len(mention_ids) != len(set(mention_ids)):
        raise ValueError("duplicate opaque mention id")

    public_text = json.dumps(public, ensure_ascii=False, sort_keys=True)
    for pair in [*mapping.case_ids, *mapping.mention_ids]:
        if pair.v1 in public_text:
            raise ValueError(f"v1 identifier residue in public input: {pair.v1}")


def _protected_hashes(workspace_root: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for relative in PROTECTED_PATHS:
        path = _resolve(Path(relative), workspace_root)
        if not path.is_file():
            raise FileNotFoundError(f"protected artifact missing: {relative}")
        values[relative] = sha256_file(path)
    return values


def _core_validation(
    v1_source_path: Path,
    v2_root: Path,
    *,
    workspace_root: Path,
) -> dict[str, Any]:
    v1_raw = load_json(v1_source_path)
    v1_source = SourceConfig.model_validate(v1_raw)
    v2_source_path = v2_root / "source-cases.json"
    v2_raw = load_json(v2_source_path)
    v2_source = SourceConfig.model_validate(v2_raw)
    mapping = OpaqueIdMap.model_validate(load_json(v2_root / "opaque-id-map.json"))

    if mapping.source_dataset_id != v1_source.dataset_id:
        raise ValueError("opaque mapping source dataset mismatch")
    if v2_source.dataset_id != OPAQUE_DATASET_ID:
        raise ValueError("opaque v2 dataset id mismatch")
    _validate_mapping(mapping)
    expected_v2_raw, expected_mapping = _build_v2_source(
        v1_source,
        namespace=OPAQUE_NAMESPACE,
    )
    if canonical_json_bytes(mapping) != canonical_json_bytes(expected_mapping):
        raise ValueError("opaque mapping does not match frozen derivation")
    if canonical_json_bytes(v2_raw) != canonical_json_bytes(expected_v2_raw):
        raise ValueError("v1/v2 semantic equivalence mismatch")
    _check_source_equivalence(v1_raw, v2_raw, mapping)
    _check_public_identifier_policy(load_json(v2_root / "public.json"), mapping)
    _check_derived_artifact_equivalence(v1_source_path.parent, v2_root, mapping)

    manifest = load_json(v2_root / "manifest.json")
    if manifest.get("source_config_sha256") != sha256_file(v2_source_path):
        raise ValueError("v2 source config hash mismatch")
    base = validate_natural_identity_slice(v2_root, workspace_root=workspace_root)
    return {
        **base,
        "identifier_policy_valid": True,
        "semantic_equivalence_valid": True,
        "v1_source_sha256": sha256_file(v1_source_path),
    }


def _slice_hashes(v2_root: Path) -> dict[str, str]:
    return {
        name: sha256_file(v2_root / name)
        for name in (
            "source-cases.json",
            "opaque-id-map.json",
            "public.json",
            "authority.json",
            "gold.json",
            "manifest.json",
        )
    }


def _build_preregistration(
    v1_source_path: Path,
    v2_root: Path,
    *,
    workspace_root: Path,
) -> OpaquePreregistration:
    return OpaquePreregistration(
        v1_source_sha256=sha256_file(v1_source_path),
        files_sha256=_slice_hashes(v2_root),
        protected_sha256=_protected_hashes(workspace_root),
        identifier_policy=OpaqueIdentifierPolicy(),
        proposal_quality_thresholds=OpaqueProposalQualityThresholds(
            **PROPOSAL_THRESHOLDS
        ),
        validation=OpaqueValidationFlags(),
        claim_boundary=OpaqueClaimBoundary(),
    )


def prepare_opaque_identity_slice(
    v1_source_path: Path,
    output_root: Path,
    *,
    workspace_root: Path | None = None,
    namespace: str = OPAQUE_NAMESPACE,
) -> dict[str, Any]:
    workspace_root = (workspace_root or Path.cwd()).resolve()
    v1_source_path = _resolve(v1_source_path, workspace_root)
    output_root = output_root.resolve()
    if namespace != OPAQUE_NAMESPACE:
        raise ValueError("opaque mapping namespace mismatch")
    source = SourceConfig.model_validate(load_json(v1_source_path))
    v2_source, mapping = _build_v2_source(source, namespace=namespace)

    write_json_immutable(output_root / "source-cases.json", v2_source)
    write_json_immutable(output_root / "opaque-id-map.json", mapping)
    freeze_natural_identity_slice(
        output_root / "source-cases.json",
        output_root,
        workspace_root=workspace_root,
    )
    _core_validation(
        v1_source_path,
        output_root,
        workspace_root=workspace_root,
    )
    preregistration = _build_preregistration(
        v1_source_path,
        output_root,
        workspace_root=workspace_root,
    )
    write_json_immutable(output_root / "preregistration.json", preregistration)
    for name in SLICE_FILES:
        (output_root / name).chmod(0o444)
    return validate_opaque_identity_slice(
        v1_source_path,
        output_root,
        workspace_root=workspace_root,
    )


def validate_opaque_identity_slice(
    v1_source_path: Path,
    v2_root: Path,
    *,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    workspace_root = (workspace_root or Path.cwd()).resolve()
    v1_source_path = _resolve(v1_source_path, workspace_root)
    v2_root = v2_root.resolve()
    core = _core_validation(
        v1_source_path,
        v2_root,
        workspace_root=workspace_root,
    )
    preregistration = OpaquePreregistration.model_validate(
        load_json(v2_root / "preregistration.json")
    )
    if preregistration.v1_source_sha256 != sha256_file(v1_source_path):
        raise ValueError("preregistration v1 source hash mismatch")
    if preregistration.files_sha256 != _slice_hashes(v2_root):
        raise ValueError("preregistration v2 file hash mismatch")
    if preregistration.protected_sha256 != _protected_hashes(workspace_root):
        raise ValueError("protected artifact hash mismatch")
    if (
        preregistration.proposal_quality_thresholds.model_dump(mode="json")
        != PROPOSAL_THRESHOLDS
    ):
        raise ValueError("proposal quality thresholds mismatch")
    if preregistration.identifier_policy != OpaqueIdentifierPolicy():
        raise ValueError("identifier policy mismatch")
    for name in SLICE_FILES:
        path = v2_root / name
        if path.stat().st_mode & 0o222:
            raise ValueError(f"formal slice artifact must be read-only: {name}")
    return core
