from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .identity_proposal import (
    AuthorityIdentityCase,
    AuthorityIdentityPayload,
    GoldIdentityItem,
    GoldIdentityPayload,
    PublicIdentityPayload,
    SourceConfig,
    _gold_evidence_index,
    _locomo_dialogue_index,
    _validate_source_cases,
    freeze_natural_identity_slice,
    validate_natural_identity_slice,
)
from .identity_proposal_opaque import (
    PROPOSAL_THRESHOLDS,
    PROTECTED_PATHS as V1_PROTECTED_PATHS,
)
from .identity_proposer_policy import IdentityProposerPolicyFreeze
from .io import canonical_json_bytes, load_json, sha256_file, write_json_immutable


FRESH_DATASET_ID = "natural-identity-membership-fresh-v3"
FRESH_HIDDEN_DATASET_ID = "natural-identity-membership-fresh-v3-hidden-source"
FRESH_NAMESPACE = "natural-identity-membership-fresh-v3:2026-07-27"
V2_DATASET_ID = "natural-identity-membership-opaque-v2"
FORMAL_PUBLIC_PATH = Path(
    "artifacts/identity-memory-experiment/natural-v3-fresh/public.json"
)
FORMAL_FRESH_ROOT = Path(
    "artifacts/identity-memory-experiment/natural-v3-fresh"
)
FORMAL_V2_SOURCE_PATH = Path(
    "artifacts/identity-memory-experiment/natural-v2/source-cases.json"
)
FORMAL_POLICY_FREEZE_PATH = Path(
    "artifacts/identity-memory-experiment/dev-repair-v3/policy-freeze-v3.json"
)
FORMAL_HIDDEN_SOURCE_PATH = Path(
    "artifacts/identity-memory-experiment/natural-v3-fresh/hidden-source-cases.json"
)
FORMAL_CHRONOLOGY_RECEIPT_PATH = Path(
    "artifacts/identity-memory-experiment/dev-repair-v3/chronology-receipt-v3.json"
)
FORMAL_CHRONOLOGY_RECEIPT_SHA256 = (
    "ad7e5e9fd8865be16afbb4e73416600455bdf7b909db60df31fe7fea77b04240"
)
CASE_ID_RE = re.compile(r"case-[0-9a-f]{16}")
MENTION_ID_RE = re.compile(r"mention-[0-9a-f]{16}")
DEV_CASE_COUNT = 6
HIDDEN_CASE_COUNT = 6
CASE_COUNT = DEV_CASE_COUNT + HIDDEN_CASE_COUNT

EXPECTED_HIDDEN_ACTION_DISTRIBUTION = {
    "merge": 1,
    "keep_distinct": 1,
    "abstain_identity": 1,
    "include": 1,
    "exclude": 1,
    "abstain_membership": 1,
}

GENERATED_FILES = (
    "source-cases.json",
    "opaque-id-map.json",
    "preregistration.json",
    "public.json",
    "authority.json",
    "gold.json",
    "manifest.json",
)

V2_PROTECTED_PATHS = (
    "artifacts/identity-memory-experiment/natural-v2/source-cases.json",
    "artifacts/identity-memory-experiment/natural-v2/opaque-id-map.json",
    "artifacts/identity-memory-experiment/natural-v2/preregistration.json",
    "artifacts/identity-memory-experiment/natural-v2/public.json",
    "artifacts/identity-memory-experiment/natural-v2/authority.json",
    "artifacts/identity-memory-experiment/natural-v2/gold.json",
    "artifacts/identity-memory-experiment/natural-v2/manifest.json",
    "artifacts/identity-memory-experiment/natural-v2/model-runs/run-20260727T124023Z-codex-gpt-5-6-sol-opaque-v2/dispatch.json",
    "artifacts/identity-memory-experiment/natural-v2/model-runs/run-20260727T124023Z-codex-gpt-5-6-sol-opaque-v2/proposals.json",
    "artifacts/identity-memory-experiment/natural-v2/model-runs/run-20260727T124023Z-codex-gpt-5-6-sol-opaque-v2/provenance.json",
    "artifacts/identity-memory-experiment/natural-v2/model-runs/run-20260727T124023Z-codex-gpt-5-6-sol-opaque-v2/score.json",
    "artifacts/identity-memory-experiment/natural-v2/model-runs/run-20260727T124023Z-codex-gpt-5-6-sol-opaque-v2/report.md",
)
PROTECTED_PATHS = (*V1_PROTECTED_PATHS, *V2_PROTECTED_PATHS)

DEV_RUN_FILES = (
    "dispatch.json",
    "api-transport.json",
    "proposals.json",
    "provenance.json",
    "score.json",
    "report.md",
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FreshIdPair(StrictModel):
    ordinal: int = Field(ge=1)
    source: str = Field(min_length=1)
    v3: str = Field(min_length=1)


class FreshIdMap(StrictModel):
    schema_version: Literal["natural-identity-fresh-id-map-v1"] = (
        "natural-identity-fresh-id-map-v1"
    )
    dev_source_dataset_id: Literal["natural-identity-membership-opaque-v2"] = (
        V2_DATASET_ID
    )
    hidden_source_dataset_id: Literal[
        "natural-identity-membership-fresh-v3-hidden-source"
    ] = FRESH_HIDDEN_DATASET_ID
    dataset_id: Literal["natural-identity-membership-fresh-v3"] = FRESH_DATASET_ID
    namespace: Literal["natural-identity-membership-fresh-v3:2026-07-27"] = (
        FRESH_NAMESPACE
    )
    derivation: Literal["sha256-namespace-kind-ordinal-source-prefix16"] = (
        "sha256-namespace-kind-ordinal-source-prefix16"
    )
    case_ids: list[FreshIdPair] = Field(min_length=1)
    mention_ids: list[FreshIdPair] = Field(min_length=1)


class FreshIdentifierPolicy(StrictModel):
    case_pattern: Literal["case-[0-9a-f]{16}"] = CASE_ID_RE.pattern
    mention_pattern: Literal["mention-[0-9a-f]{16}"] = MENTION_ID_RE.pattern
    source_id_residue_allowed: Literal[False] = False
    v2_id_overlap_allowed: Literal[False] = False
    mapping_must_be_bijective: Literal[True] = True


class FreshProposalQualityThresholds(StrictModel):
    raw_action_accuracy_min: float
    raw_critical_false_merge_count_max: int
    raw_critical_false_membership_count_max: int
    raw_abstention_f1_min: float
    proposal_evidence_exactness_min: float


class FreshActionDistribution(StrictModel):
    merge: Literal[1] = 1
    keep_distinct: Literal[1] = 1
    abstain_identity: Literal[1] = 1
    include: Literal[1] = 1
    exclude: Literal[1] = 1
    abstain_membership: Literal[1] = 1


class FreshPolicyBinding(StrictModel):
    policy_freeze_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dev_prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    final_prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dev_run_id: str = Field(min_length=1)
    final_run_id: str = Field(min_length=1)
    proposer_id: str = Field(min_length=1)
    proposer_version: str = Field(min_length=1)
    policy_freeze_mtime_ns: int = Field(ge=1)
    hidden_source_mtime_ns: int = Field(ge=1)
    dev_run_sha256: dict[str, str]


class FrozenFileObservation(StrictModel):
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mtime_ns: int = Field(ge=1)


class FreshChronologyReceipt(StrictModel):
    schema_version: Literal["natural-identity-chronology-receipt-v1"] = (
        "natural-identity-chronology-receipt-v1"
    )
    status: Literal["frozen-posthoc-audit"] = "frozen-posthoc-audit"
    evidence_kind: Literal["filesystem-mtime-plus-sha256"] = (
        "filesystem-mtime-plus-sha256"
    )
    trusted_timestamp_authority: Literal[False] = False
    dev_run_id: str = Field(min_length=1)
    policy_freeze: FrozenFileObservation
    dev_run_files: dict[str, FrozenFileObservation]
    hidden_source: FrozenFileObservation
    policy_freeze_precedes_dev_run: Literal[True] = True
    dev_run_complete_precedes_hidden_source: Literal[True] = True


class FreshValidationFlags(StrictModel):
    identifier_policy_valid: Literal[True] = True
    derived_artifact_equivalence_valid: Literal[True] = True
    source_validation_valid: Literal[True] = True
    manifest_integrity_valid: Literal[True] = True
    policy_chronology_valid: Literal[True] = True
    hidden_freshness_valid: Literal[True] = True


class FreshClaimBoundary(StrictModel):
    automatic_merge_authorized: Literal[False] = False
    automatic_membership_write_authorized: Literal[False] = False
    automatic_l2_write_authorized: Literal[False] = False
    embedding_is_authority: Literal[False] = False
    longmemeval_status: Literal["structured_l2_identity_unresolved"] = (
        "structured_l2_identity_unresolved"
    )
    external_memory_systems_rerun: Literal[False] = False
    core_impact: Literal["none"] = "none"


class FreshPreregistration(StrictModel):
    schema_version: Literal["natural-identity-fresh-preregistration-v1"] = (
        "natural-identity-fresh-preregistration-v1"
    )
    dataset_id: Literal["natural-identity-membership-fresh-v3"] = FRESH_DATASET_ID
    status: Literal["frozen"] = "frozen"
    v2_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    hidden_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    files_sha256: dict[str, str]
    protected_sha256: dict[str, str]
    identifier_policy: FreshIdentifierPolicy
    proposal_quality_thresholds: FreshProposalQualityThresholds
    hidden_action_distribution: FreshActionDistribution
    cross_session_hidden_count: int = Field(ge=2)
    v2_id_overlap_count: Literal[0] = 0
    v2_hidden_source_id_overlap_count: Literal[0] = 0
    v2_hidden_evidence_overlap_count: Literal[0] = 0
    policy_binding: FreshPolicyBinding
    validation: FreshValidationFlags
    claim_boundary: FreshClaimBoundary


def derive_fresh_id(
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


def _require_read_only(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} missing: {path}")
    if path.stat().st_mode & 0o222:
        raise ValueError(f"{label} must be read-only")


def _protected_hashes(workspace_root: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for relative in PROTECTED_PATHS:
        path = _resolve(Path(relative), workspace_root)
        if not path.is_file():
            raise FileNotFoundError(f"protected artifact missing: {relative}")
        values[relative] = sha256_file(path)
    return values


def _require_formal_fresh_inputs(
    root: Path,
    *,
    v2_source_path: Path,
    hidden_source_path: Path,
    policy_freeze_path: Path,
    workspace_root: Path,
) -> None:
    if root != _resolve(FORMAL_FRESH_ROOT, workspace_root):
        return
    expected = (
        _resolve(FORMAL_V2_SOURCE_PATH, workspace_root),
        _resolve(FORMAL_HIDDEN_SOURCE_PATH, workspace_root),
        _resolve(FORMAL_POLICY_FREEZE_PATH, workspace_root),
    )
    actual = (v2_source_path, hidden_source_path, policy_freeze_path)
    if actual != expected:
        raise ValueError(
            "formal fresh validation requires exact formal input paths"
        )


def _validate_chronology_receipt(
    receipt_path: Path,
    *,
    policy_freeze_path: Path,
    hidden_source_path: Path,
    dev_run_root: Path,
    workspace_root: Path,
    expected_sha256: str,
) -> dict[str, Any]:
    _require_read_only(receipt_path, "chronology receipt")
    if sha256_file(receipt_path) != expected_sha256:
        raise ValueError("chronology receipt hash mismatch")
    receipt = FreshChronologyReceipt.model_validate(load_json(receipt_path))
    if set(receipt.dev_run_files) != set(DEV_RUN_FILES):
        raise ValueError("chronology receipt dev run file set mismatch")

    def validate_observation(
        observation: FrozenFileObservation,
        expected_path: Path,
        label: str,
    ) -> int:
        observed_path = _resolve(Path(observation.path), workspace_root)
        if observed_path != expected_path.resolve():
            raise ValueError(f"chronology receipt path mismatch: {label}")
        _require_read_only(expected_path, label)
        if sha256_file(expected_path) != observation.sha256:
            raise ValueError(f"chronology receipt hash mismatch: {label}")
        actual_mtime = expected_path.stat().st_mtime_ns
        if actual_mtime != observation.mtime_ns:
            raise ValueError(f"chronology receipt mtime mismatch: {label}")
        return actual_mtime

    policy_mtime = validate_observation(
        receipt.policy_freeze,
        policy_freeze_path,
        "policy freeze",
    )
    dev_mtimes = [
        validate_observation(
            receipt.dev_run_files[name],
            dev_run_root / name,
            f"passing dev run {name}",
        )
        for name in DEV_RUN_FILES
    ]
    hidden_mtime = validate_observation(
        receipt.hidden_source,
        hidden_source_path,
        "fresh hidden source",
    )
    if not policy_mtime < min(dev_mtimes):
        raise ValueError("policy freeze must predate passing dev run")
    if not max(dev_mtimes) < hidden_mtime:
        raise ValueError("passing dev run must predate hidden source")
    return {
        "policy_freeze_precedes_dev_run": True,
        "dev_run_complete_precedes_hidden_source": True,
        "trusted_timestamp_authority": False,
    }


def _build_fresh_source(
    v2_source: SourceConfig,
    hidden_source: SourceConfig,
) -> tuple[dict[str, Any], FreshIdMap]:
    if v2_source.dataset_id != V2_DATASET_ID:
        raise ValueError("fresh dev source must be opaque v2")
    if hidden_source.dataset_id != FRESH_HIDDEN_DATASET_ID:
        raise ValueError("fresh hidden source dataset mismatch")
    if v2_source.source_inputs != hidden_source.source_inputs:
        raise ValueError("fresh source inputs mismatch")
    dev_cases = [case for case in v2_source.cases if case.split == "dev"]
    hidden_cases = list(hidden_source.cases)
    if len(dev_cases) != DEV_CASE_COUNT:
        raise ValueError("fresh slice requires exactly six v2 dev cases")
    if len(hidden_cases) != HIDDEN_CASE_COUNT or any(
        case.split != "hidden" for case in hidden_cases
    ):
        raise ValueError("fresh hidden source requires exactly six hidden cases")

    payload = {
        "schema_version": "natural-identity-source-config-v1",
        "dataset_id": FRESH_DATASET_ID,
        "source_inputs": v2_source.source_inputs,
        "cases": [
            case.model_dump(mode="json", exclude_unset=True)
            for case in [*dev_cases, *hidden_cases]
        ],
    }
    case_pairs: list[FreshIdPair] = []
    mention_pairs: list[FreshIdPair] = []
    mention_ordinal = 0
    for case_ordinal, case in enumerate(payload["cases"], start=1):
        source_case_id = case["case_id"]
        v3_case_id = derive_fresh_id(
            FRESH_NAMESPACE, "case", case_ordinal, source_case_id
        )
        case_pairs.append(
            FreshIdPair(ordinal=case_ordinal, source=source_case_id, v3=v3_case_id)
        )
        case["case_id"] = v3_case_id
        mention_mapping: dict[str, str] = {}
        for mention in case["mentions"]:
            mention_ordinal += 1
            source_mention_id = mention["mention_id"]
            v3_mention_id = derive_fresh_id(
                FRESH_NAMESPACE, "mention", mention_ordinal, source_mention_id
            )
            mention_pairs.append(
                FreshIdPair(
                    ordinal=mention_ordinal,
                    source=source_mention_id,
                    v3=v3_mention_id,
                )
            )
            mention_mapping[source_mention_id] = v3_mention_id
            mention["mention_id"] = v3_mention_id
        case["authority"]["required_mention_ids"] = [
            mention_mapping[item]
            for item in case["authority"]["required_mention_ids"]
        ]

    mapping = FreshIdMap(case_ids=case_pairs, mention_ids=mention_pairs)
    _validate_mapping(mapping)
    SourceConfig.model_validate(payload)
    return payload, mapping


def _validate_mapping(mapping: FreshIdMap) -> None:
    case_sources = [item.source for item in mapping.case_ids]
    case_values = [item.v3 for item in mapping.case_ids]
    mention_sources = [item.source for item in mapping.mention_ids]
    mention_values = [item.v3 for item in mapping.mention_ids]
    if len(case_sources) != len(set(case_sources)) or len(case_values) != len(
        set(case_values)
    ):
        raise ValueError("fresh case id mapping must be bijective")
    if len(mention_sources) != len(set(mention_sources)) or len(
        mention_values
    ) != len(set(mention_values)):
        raise ValueError("fresh mention id mapping must be bijective")
    if [item.ordinal for item in mapping.case_ids] != list(
        range(1, len(mapping.case_ids) + 1)
    ):
        raise ValueError("fresh case id ordinals must be contiguous")
    if [item.ordinal for item in mapping.mention_ids] != list(
        range(1, len(mapping.mention_ids) + 1)
    ):
        raise ValueError("fresh mention id ordinals must be contiguous")
    for item in mapping.case_ids:
        if not CASE_ID_RE.fullmatch(item.v3):
            raise ValueError(f"invalid fresh case id: {item.v3}")
        if item.v3 != derive_fresh_id(
            FRESH_NAMESPACE, "case", item.ordinal, item.source
        ):
            raise ValueError(f"invalid derived fresh case id: {item.v3}")
    for item in mapping.mention_ids:
        if not MENTION_ID_RE.fullmatch(item.v3):
            raise ValueError(f"invalid fresh mention id: {item.v3}")
        if item.v3 != derive_fresh_id(
            FRESH_NAMESPACE, "mention", item.ordinal, item.source
        ):
            raise ValueError(f"invalid derived fresh mention id: {item.v3}")


def _derive_expected_artifacts(
    source: SourceConfig,
    *,
    workspace_root: Path,
) -> dict[str, dict[str, Any]]:
    input_paths = {
        key: _resolve(Path(value), workspace_root)
        for key, value in source.source_inputs.items()
    }
    evidence_index = _gold_evidence_index(input_paths["gold_evidence"])
    locomo_index = _locomo_dialogue_index(input_paths["locomo_raw"])
    resolved = _validate_source_cases(source.cases, evidence_index, locomo_index)
    public_cases: list[dict[str, Any]] = []
    authority_cases: list[dict[str, Any]] = []
    gold_items: list[dict[str, Any]] = []
    for item in resolved:
        case = item["case"]
        mentions = item["mentions"]
        public_cases.append(
            {
                "case_id": case.case_id,
                "split": case.split,
                "relation_kind": case.relation_kind,
                "question": case.question,
                "mentions": mentions,
                "query_subject_id": case.query_subject_id,
                "group_surface": case.group_surface,
                "member_surface": case.member_surface,
            }
        )
        authority = case.authority
        authority_cases.append(
            AuthorityIdentityCase(
                case_id=case.case_id,
                relation_kind=case.relation_kind,
                **authority.model_dump(
                    mode="json", exclude={"required_mention_ids"}
                ),
                trusted_actor_bindings={
                    mention.mention_id: mention.source_actor_id
                    for mention in case.mentions
                },
                required_mention_ids=authority.required_mention_ids,
                required_evidence_unit_ids=[
                    mention.evidence_unit_id for mention in case.mentions
                ],
            ).model_dump(mode="json")
        )
        gold_items.append(
            GoldIdentityItem(
                case_id=case.case_id,
                split=case.split,
                relation_kind=case.relation_kind,
                **case.gold.model_dump(mode="json"),
            ).model_dump(mode="json")
        )
    return {
        "public.json": PublicIdentityPayload(
            dataset_id=source.dataset_id,
            case_count=len(public_cases),
            cases=public_cases,
        ).model_dump(mode="json"),
        "authority.json": AuthorityIdentityPayload(
            dataset_id=source.dataset_id,
            case_count=len(authority_cases),
            cases=authority_cases,
        ).model_dump(mode="json"),
        "gold.json": GoldIdentityPayload(
            dataset_id=source.dataset_id,
            case_count=len(gold_items),
            items=gold_items,
        ).model_dump(mode="json"),
    }


def _check_derived_artifacts(
    source: SourceConfig,
    root: Path,
    *,
    workspace_root: Path,
) -> None:
    expected = _derive_expected_artifacts(source, workspace_root=workspace_root)
    for name, payload in expected.items():
        if canonical_json_bytes(load_json(root / name)) != canonical_json_bytes(payload):
            raise ValueError(f"derived artifact semantic equivalence mismatch: {name}")


def _check_public_identifier_policy(
    public: dict[str, Any], mapping: FreshIdMap
) -> None:
    case_ids: list[str] = []
    mention_ids: list[str] = []
    for case in public.get("cases", []):
        case_id = str(case.get("case_id", ""))
        if not CASE_ID_RE.fullmatch(case_id):
            raise ValueError(f"invalid fresh case id: {case_id}")
        case_ids.append(case_id)
        for mention in case.get("mentions", []):
            mention_id = str(mention.get("mention_id", ""))
            if not MENTION_ID_RE.fullmatch(mention_id):
                raise ValueError(f"invalid fresh mention id: {mention_id}")
            mention_ids.append(mention_id)
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("duplicate fresh case id")
    if len(mention_ids) != len(set(mention_ids)):
        raise ValueError("duplicate fresh mention id")
    public_text = json.dumps(public, ensure_ascii=False, sort_keys=True)
    for pair in [*mapping.case_ids, *mapping.mention_ids]:
        if pair.source in public_text:
            raise ValueError(f"source identifier residue in public input: {pair.source}")


def _evidence_signature(case: Any) -> tuple[str, ...]:
    return tuple(
        sorted(
            f"{mention.source_item_id}:{mention.evidence_unit_id}"
            for mention in case.mentions
        )
    )


def _hidden_action_distribution(source: SourceConfig) -> dict[str, int]:
    distribution = {key: 0 for key in EXPECTED_HIDDEN_ACTION_DISTRIBUTION}
    for case in source.cases:
        action = case.gold.expected_action
        key = f"abstain_{case.relation_kind}" if action == "abstain" else action
        if key not in distribution:
            raise ValueError(f"unexpected hidden action: {key}")
        distribution[key] += 1
    return distribution


def _session_token(source_ref: str) -> str | None:
    for field in ("session_index", "session", "session_id"):
        match = re.search(rf"(?:^|;){field}=([^;]+)", source_ref)
        if match:
            return f"{field}:{match.group(1)}"
    return None


def _cross_session_hidden_count(public: dict[str, Any]) -> int:
    count = 0
    for case in public.get("cases", []):
        if case.get("split") != "hidden":
            continue
        sessions = {
            token
            for mention in case.get("mentions", [])
            if (token := _session_token(str(mention.get("source_ref", ""))))
        }
        if len(sessions) >= 2:
            count += 1
    return count


def _validate_policy_binding(
    policy_freeze_path: Path,
    hidden_source_path: Path,
    *,
    workspace_root: Path,
) -> dict[str, Any]:
    _require_read_only(policy_freeze_path, "policy freeze")
    frozen = IdentityProposerPolicyFreeze.model_validate(load_json(policy_freeze_path))
    policy_path = Path(frozen.policy_path).resolve()
    dev_public_path = Path(frozen.dev_public_path).resolve()
    dev_prompt_path = Path(frozen.dev_prompt_path).resolve()
    final_prompt_path = Path(frozen.final_prompt_path).resolve()
    for path, label in (
        (policy_path, "policy"),
        (dev_public_path, "dev public input"),
        (dev_prompt_path, "dev prompt"),
        (final_prompt_path, "final prompt"),
    ):
        _require_read_only(path, label)
    if sha256_file(policy_path) != frozen.policy_sha256:
        raise ValueError("policy hash mismatch")
    if sha256_file(dev_public_path) != frozen.dev_public_sha256:
        raise ValueError("dev public hash mismatch")
    if sha256_file(dev_prompt_path) != frozen.dev_prompt_sha256:
        raise ValueError("dev prompt hash mismatch")
    if sha256_file(final_prompt_path) != frozen.final_prompt_sha256:
        raise ValueError("final prompt hash mismatch")
    expected_public = _resolve(FORMAL_PUBLIC_PATH, workspace_root)
    if Path(frozen.final_public_path).resolve() != expected_public:
        raise ValueError("final public path mismatch")
    if frozen.fresh_hidden_authored_before_policy_freeze is not False:
        raise ValueError("policy chronology flag mismatch")

    policy_mtime = policy_freeze_path.stat().st_mtime_ns
    hidden_mtime = hidden_source_path.stat().st_mtime_ns
    if hidden_mtime < policy_mtime:
        raise ValueError("hidden source predates policy freeze")

    dev_run_root = policy_freeze_path.parent / "model-runs" / frozen.dev_run_id
    dev_run_sha256: dict[str, str] = {}
    dev_run_mtime_ns: list[int] = []
    for name in DEV_RUN_FILES:
        path = dev_run_root / name
        _require_read_only(path, f"passing dev run {name}")
        dev_run_sha256[name] = sha256_file(path)
        dev_run_mtime_ns.append(path.stat().st_mtime_ns)
    if not policy_mtime < min(dev_run_mtime_ns):
        raise ValueError("policy freeze must predate passing dev run")
    if not max(dev_run_mtime_ns) < hidden_mtime:
        raise ValueError("passing dev run must predate hidden source")
    if (
        policy_freeze_path == _resolve(FORMAL_POLICY_FREEZE_PATH, workspace_root)
        and hidden_source_path == _resolve(FORMAL_HIDDEN_SOURCE_PATH, workspace_root)
    ):
        _validate_chronology_receipt(
            _resolve(FORMAL_CHRONOLOGY_RECEIPT_PATH, workspace_root),
            policy_freeze_path=policy_freeze_path,
            hidden_source_path=hidden_source_path,
            dev_run_root=dev_run_root,
            workspace_root=workspace_root,
            expected_sha256=FORMAL_CHRONOLOGY_RECEIPT_SHA256,
        )
    score = load_json(dev_run_root / "score.json")
    metrics = score.get("metrics", {})
    if not score.get("proposal_quality_ready") or not score.get("gate_safety_ready"):
        raise ValueError("policy dev gate did not pass")
    if not (
        metrics.get("raw_action_accuracy") == 1.0
        and metrics.get("raw_critical_false_merge_count") == 0
        and metrics.get("raw_critical_false_membership_count") == 0
        and metrics.get("raw_abstention_f1") == 1.0
        and metrics.get("proposal_evidence_exact_rate") == 1.0
    ):
        raise ValueError("policy dev metrics did not pass")
    provenance = load_json(dev_run_root / "provenance.json")
    if provenance.get("authority_or_gold_read_before_freeze") is not False:
        raise ValueError("passing dev provenance phase order mismatch")
    if provenance.get("history_context_inherited") is not False:
        raise ValueError("passing dev provenance history mismatch")
    transport = load_json(dev_run_root / "api-transport.json")
    if not (
        transport.get("history_message_count") == 0
        and transport.get("request_message_count") == 1
        and transport.get("authority_or_gold_included") is False
        and transport.get("dispatch_sha256") == dev_run_sha256["dispatch.json"]
        and transport.get("prompt_sha256") == frozen.dev_prompt_sha256
        and transport.get("public_sha256") == frozen.dev_public_sha256
    ):
        raise ValueError("passing dev API transport mismatch")
    return {
        "policy_freeze_sha256": sha256_file(policy_freeze_path),
        "policy_sha256": frozen.policy_sha256,
        "dev_prompt_sha256": frozen.dev_prompt_sha256,
        "final_prompt_sha256": frozen.final_prompt_sha256,
        "dev_run_id": frozen.dev_run_id,
        "final_run_id": frozen.final_run_id,
        "proposer_id": frozen.proposer_id,
        "proposer_version": frozen.proposer_version,
        "policy_freeze_mtime_ns": policy_mtime,
        "hidden_source_mtime_ns": hidden_mtime,
        "dev_run_sha256": dev_run_sha256,
    }


def _core_validation(
    v2_source_path: Path,
    hidden_source_path: Path,
    root: Path,
    *,
    policy_freeze_path: Path,
    workspace_root: Path,
) -> dict[str, Any]:
    _require_read_only(v2_source_path, "v2 source")
    _require_read_only(hidden_source_path, "fresh hidden source")
    policy = _validate_policy_binding(
        policy_freeze_path,
        hidden_source_path,
        workspace_root=workspace_root,
    )
    v2 = SourceConfig.model_validate(load_json(v2_source_path))
    hidden = SourceConfig.model_validate(load_json(hidden_source_path))
    expected_source, expected_mapping = _build_fresh_source(v2, hidden)
    actual_source_raw = load_json(root / "source-cases.json")
    actual_source = SourceConfig.model_validate(actual_source_raw)
    actual_mapping = FreshIdMap.model_validate(load_json(root / "opaque-id-map.json"))
    _validate_mapping(actual_mapping)
    if canonical_json_bytes(actual_mapping) != canonical_json_bytes(expected_mapping):
        raise ValueError("fresh mapping does not match frozen derivation")
    if canonical_json_bytes(actual_source_raw) != canonical_json_bytes(expected_source):
        raise ValueError("fresh source semantic equivalence mismatch")
    _check_public_identifier_policy(load_json(root / "public.json"), actual_mapping)
    _check_derived_artifacts(actual_source, root, workspace_root=workspace_root)
    base = validate_natural_identity_slice(root, workspace_root=workspace_root)

    v2_ids = {
        value
        for case in v2.cases
        for value in [case.case_id, *[mention.mention_id for mention in case.mentions]]
    }
    v3_ids = {
        value
        for case in actual_source.cases
        for value in [case.case_id, *[mention.mention_id for mention in case.mentions]]
    }
    v2_id_overlap_count = len(v2_ids & v3_ids)
    v2_hidden = [case for case in v2.cases if case.split == "hidden"]
    v2_hidden_ids = {case.case_id for case in v2_hidden}
    hidden_source_ids = {case.case_id for case in hidden.cases}
    v2_hidden_source_id_overlap_count = len(v2_hidden_ids & hidden_source_ids)
    v2_hidden_signatures = {_evidence_signature(case) for case in v2_hidden}
    hidden_signatures = {_evidence_signature(case) for case in hidden.cases}
    v2_hidden_evidence_overlap_count = len(v2_hidden_signatures & hidden_signatures)
    if v2_id_overlap_count:
        raise ValueError("v2 ID overlap")
    if v2_hidden_source_id_overlap_count:
        raise ValueError("v2 hidden case overlap")
    if v2_hidden_evidence_overlap_count:
        raise ValueError("v2 hidden evidence overlap")

    action_distribution = _hidden_action_distribution(hidden)
    if action_distribution != EXPECTED_HIDDEN_ACTION_DISTRIBUTION:
        raise ValueError("fresh hidden action distribution mismatch")
    cross_session_hidden_count = _cross_session_hidden_count(load_json(root / "public.json"))
    if cross_session_hidden_count < 2:
        raise ValueError("fresh hidden requires at least two cross-session cases")
    if not (
        base["case_count"] == CASE_COUNT
        and base["dev_count"] == DEV_CASE_COUNT
        and base["hidden_count"] == HIDDEN_CASE_COUNT
    ):
        raise ValueError("fresh slice composition mismatch")
    return {
        **base,
        "identifier_policy_valid": True,
        "derived_artifact_equivalence_valid": True,
        "policy_chronology_valid": True,
        "hidden_freshness_valid": True,
        "hidden_action_distribution": action_distribution,
        "cross_session_hidden_count": cross_session_hidden_count,
        "v2_id_overlap_count": v2_id_overlap_count,
        "v2_hidden_source_id_overlap_count": v2_hidden_source_id_overlap_count,
        "v2_hidden_evidence_overlap_count": v2_hidden_evidence_overlap_count,
        "v2_source_sha256": sha256_file(v2_source_path),
        "hidden_source_sha256": sha256_file(hidden_source_path),
        "policy_binding": policy,
    }


def _slice_hashes(root: Path) -> dict[str, str]:
    return {
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


def _build_preregistration(
    core: dict[str, Any], root: Path, *, workspace_root: Path
) -> FreshPreregistration:
    return FreshPreregistration(
        v2_source_sha256=core["v2_source_sha256"],
        hidden_source_sha256=core["hidden_source_sha256"],
        files_sha256=_slice_hashes(root),
        protected_sha256=_protected_hashes(workspace_root),
        identifier_policy=FreshIdentifierPolicy(),
        proposal_quality_thresholds=FreshProposalQualityThresholds(
            **PROPOSAL_THRESHOLDS
        ),
        hidden_action_distribution=FreshActionDistribution(
            **core["hidden_action_distribution"]
        ),
        cross_session_hidden_count=core["cross_session_hidden_count"],
        v2_id_overlap_count=core["v2_id_overlap_count"],
        v2_hidden_source_id_overlap_count=core[
            "v2_hidden_source_id_overlap_count"
        ],
        v2_hidden_evidence_overlap_count=core[
            "v2_hidden_evidence_overlap_count"
        ],
        policy_binding=FreshPolicyBinding(**core["policy_binding"]),
        validation=FreshValidationFlags(),
        claim_boundary=FreshClaimBoundary(),
    )


def prepare_fresh_identity_slice(
    v2_source_path: Path,
    hidden_source_path: Path,
    output_root: Path,
    *,
    policy_freeze_path: Path,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    workspace_root = (workspace_root or Path.cwd()).resolve()
    v2_source_path = _resolve(v2_source_path, workspace_root)
    hidden_source_path = _resolve(hidden_source_path, workspace_root)
    policy_freeze_path = _resolve(policy_freeze_path, workspace_root)
    output_root = output_root.resolve()
    _require_formal_fresh_inputs(
        output_root,
        v2_source_path=v2_source_path,
        hidden_source_path=hidden_source_path,
        policy_freeze_path=policy_freeze_path,
        workspace_root=workspace_root,
    )
    _require_read_only(v2_source_path, "v2 source")
    _require_read_only(hidden_source_path, "fresh hidden source")
    _validate_policy_binding(
        policy_freeze_path,
        hidden_source_path,
        workspace_root=workspace_root,
    )
    v2 = SourceConfig.model_validate(load_json(v2_source_path))
    hidden = SourceConfig.model_validate(load_json(hidden_source_path))
    source, mapping = _build_fresh_source(v2, hidden)
    write_json_immutable(output_root / "source-cases.json", source)
    write_json_immutable(output_root / "opaque-id-map.json", mapping)
    freeze_natural_identity_slice(
        output_root / "source-cases.json",
        output_root,
        workspace_root=workspace_root,
    )
    core = _core_validation(
        v2_source_path,
        hidden_source_path,
        output_root,
        policy_freeze_path=policy_freeze_path,
        workspace_root=workspace_root,
    )
    preregistration = _build_preregistration(
        core, output_root, workspace_root=workspace_root
    )
    write_json_immutable(output_root / "preregistration.json", preregistration)
    for name in GENERATED_FILES:
        (output_root / name).chmod(0o444)
    return validate_fresh_identity_slice(
        v2_source_path,
        hidden_source_path,
        output_root,
        policy_freeze_path=policy_freeze_path,
        workspace_root=workspace_root,
    )


def validate_fresh_identity_slice(
    v2_source_path: Path,
    hidden_source_path: Path,
    root: Path,
    *,
    policy_freeze_path: Path,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    workspace_root = (workspace_root or Path.cwd()).resolve()
    v2_source_path = _resolve(v2_source_path, workspace_root)
    hidden_source_path = _resolve(hidden_source_path, workspace_root)
    policy_freeze_path = _resolve(policy_freeze_path, workspace_root)
    root = root.resolve()
    _require_formal_fresh_inputs(
        root,
        v2_source_path=v2_source_path,
        hidden_source_path=hidden_source_path,
        policy_freeze_path=policy_freeze_path,
        workspace_root=workspace_root,
    )
    core = _core_validation(
        v2_source_path,
        hidden_source_path,
        root,
        policy_freeze_path=policy_freeze_path,
        workspace_root=workspace_root,
    )
    preregistration = FreshPreregistration.model_validate(
        load_json(root / "preregistration.json")
    )
    expected = _build_preregistration(core, root, workspace_root=workspace_root)
    if canonical_json_bytes(preregistration) != canonical_json_bytes(expected):
        raise ValueError("fresh preregistration mismatch")
    for name in GENERATED_FILES:
        path = root / name
        if path.stat().st_mode & 0o222:
            raise ValueError(f"formal slice artifact must be read-only: {name}")
    return {key: value for key, value in core.items() if key != "policy_binding"}
