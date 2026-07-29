from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .identity_proposal import (
    SourceConfig,
    _gold_evidence_index,
    _locomo_dialogue_index,
    _validate_source_cases,
    freeze_natural_identity_slice,
    validate_natural_identity_slice,
)
from .identity_proposal_fresh import _derive_expected_artifacts
from .identity_proposal_opaque import PROPOSAL_THRESHOLDS
from .identity_proposer_policy import IdentityProposerPolicyFreeze
from .identity_proposer_policy_v4 import PROTECTED_PATHS as PRIOR_PROTECTED_PATHS
from .io import canonical_json_bytes, load_json, sha256_file, write_json_immutable


DATASET_ID = "natural-identity-membership-fresh-v4"
HIDDEN_DATASET_ID = "natural-identity-membership-fresh-v4-hidden-source"
FRESH_NAMESPACE = "natural-identity-membership-fresh-v4:2026-07-28"
CASE_ID_RE = re.compile(r"case-[0-9a-f]{16}")
MENTION_ID_RE = re.compile(r"mention-[0-9a-f]{16}")
FORMAL_ROOT = Path("artifacts/identity-memory-experiment/natural-v4-fresh")
FORMAL_V2_SOURCE = Path(
    "artifacts/identity-memory-experiment/natural-v2/source-cases.json"
)
FORMAL_V3_HIDDEN_SOURCE = Path(
    "artifacts/identity-memory-experiment/natural-v3-fresh/hidden-source-cases.json"
)
FORMAL_V4_HIDDEN_SOURCE = FORMAL_ROOT / "hidden-source-cases.json"
FORMAL_POLICY_FREEZE = Path(
    "artifacts/identity-memory-experiment/dev-repair-v4/"
    "policy-freeze-v4.1-claude.json"
)
FORMAL_V4_DEV_SOURCE = Path(
    "artifacts/identity-memory-experiment/dev-repair-v4/source-cases.json"
)
BASE_EVIDENCE = Path(
    "artifacts/natural-benchmark-slices/slice-v1/gold-evidence.json"
)
LOCOMO_RAW = Path(
    "artifacts/natural-benchmark-slices/raw/locomo/locomo10.json"
)
EXPECTED_ACTION_DISTRIBUTION = {
    "merge": 1,
    "keep_distinct": 1,
    "abstain_identity": 1,
    "include": 1,
    "exclude": 1,
    "abstain_membership": 1,
}
DEV_RUN_FILES = (
    "dispatch.json",
    "api-transport.json",
    "proposals.json",
    "provenance.json",
    "score.json",
    "report.md",
    "error-analysis.md",
)
GENERATED_FILES = (
    "hidden-gold-evidence.json",
    "source-cases.json",
    "opaque-id-map.json",
    "chronology-receipt-v4.json",
    "preregistration.json",
    "public.json",
    "authority.json",
    "gold.json",
    "manifest.json",
)

V4_PROTECTED_PATHS = (
    "artifacts/identity-memory-experiment/dev-repair-v4/diagnostic-gold-evidence.json",
    "artifacts/identity-memory-experiment/dev-repair-v4/diagnostic-source-cases.json",
    "artifacts/identity-memory-experiment/dev-repair-v4/combined-gold-evidence.json",
    "artifacts/identity-memory-experiment/dev-repair-v4/source-cases.json",
    "artifacts/identity-memory-experiment/dev-repair-v4/public.json",
    "artifacts/identity-memory-experiment/dev-repair-v4/authority.json",
    "artifacts/identity-memory-experiment/dev-repair-v4/gold.json",
    "artifacts/identity-memory-experiment/dev-repair-v4/manifest.json",
    "artifacts/identity-memory-experiment/dev-repair-v4/preregistration.json",
    "artifacts/identity-memory-experiment/dev-repair-v4/policy-v4.md",
    "artifacts/identity-memory-experiment/dev-repair-v4/policy-v4.1.md",
    "artifacts/identity-memory-experiment/dev-repair-v4/dev-proposer-prompt-v4.md",
    "artifacts/identity-memory-experiment/dev-repair-v4/final-proposer-prompt-v4.md",
    "artifacts/identity-memory-experiment/dev-repair-v4/policy-freeze-v4.json",
    "artifacts/identity-memory-experiment/dev-repair-v4/dev-proposer-prompt-v4-claude.md",
    "artifacts/identity-memory-experiment/dev-repair-v4/final-proposer-prompt-v4-claude.md",
    "artifacts/identity-memory-experiment/dev-repair-v4/policy-freeze-v4-claude.json",
    "artifacts/identity-memory-experiment/dev-repair-v4/dev-proposer-prompt-v4.1-claude.md",
    "artifacts/identity-memory-experiment/dev-repair-v4/final-proposer-prompt-v4.1-claude.md",
    "artifacts/identity-memory-experiment/dev-repair-v4/policy-freeze-v4.1-claude.json",
    *tuple(
        "artifacts/identity-memory-experiment/dev-repair-v4/model-runs/"
        "run-20260728T012500Z-claude-sonnet-4-6-dev-policy-v4/" + name
        for name in DEV_RUN_FILES
    ),
    *tuple(
        "artifacts/identity-memory-experiment/dev-repair-v4/model-runs/"
        "run-20260728T013000Z-claude-sonnet-4-6-dev-policy-v4-1/" + name
        for name in DEV_RUN_FILES
    ),
)
PROTECTED_PATHS = (*PRIOR_PROTECTED_PATHS, *V4_PROTECTED_PATHS)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FreshV4IdPair(StrictModel):
    ordinal: int = Field(ge=1)
    source: str = Field(min_length=1)
    v4: str = Field(min_length=1)


class FreshV4IdMap(StrictModel):
    schema_version: Literal["natural-identity-fresh-v4-id-map-v1"] = (
        "natural-identity-fresh-v4-id-map-v1"
    )
    source_dataset_id: Literal[
        "natural-identity-membership-fresh-v4-hidden-source"
    ] = HIDDEN_DATASET_ID
    dataset_id: Literal["natural-identity-membership-fresh-v4"] = DATASET_ID
    namespace: Literal[
        "natural-identity-membership-fresh-v4:2026-07-28"
    ] = FRESH_NAMESPACE
    derivation: Literal["sha256-namespace-kind-ordinal-source-prefix16"] = (
        "sha256-namespace-kind-ordinal-source-prefix16"
    )
    case_ids: list[FreshV4IdPair] = Field(min_length=1)
    mention_ids: list[FreshV4IdPair] = Field(min_length=1)


class FrozenObservation(StrictModel):
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mtime_ns: int = Field(ge=1)


class FreshV4ChronologyReceipt(StrictModel):
    schema_version: Literal["natural-identity-chronology-receipt-v4"] = (
        "natural-identity-chronology-receipt-v4"
    )
    status: Literal["frozen-posthoc-audit"] = "frozen-posthoc-audit"
    evidence_kind: Literal["filesystem-mtime-plus-sha256"] = (
        "filesystem-mtime-plus-sha256"
    )
    trusted_timestamp_authority: Literal[False] = False
    policy_freeze: FrozenObservation
    dev_run_files: dict[str, FrozenObservation]
    hidden_source: FrozenObservation
    policy_freeze_precedes_dev_run: Literal[True] = True
    dev_run_complete_precedes_hidden_source: Literal[True] = True


class FreshV4IdentifierPolicy(StrictModel):
    case_pattern: Literal["case-[0-9a-f]{16}"] = CASE_ID_RE.pattern
    mention_pattern: Literal["mention-[0-9a-f]{16}"] = MENTION_ID_RE.pattern
    source_id_residue_allowed: Literal[False] = False
    prior_id_overlap_allowed: Literal[False] = False
    mapping_must_be_bijective: Literal[True] = True


class FreshV4Thresholds(StrictModel):
    raw_action_accuracy_min: float
    raw_critical_false_merge_count_max: int
    raw_critical_false_membership_count_max: int
    raw_abstention_f1_min: float
    proposal_evidence_exactness_min: float


class FreshV4ActionDistribution(StrictModel):
    merge: Literal[1] = 1
    keep_distinct: Literal[1] = 1
    abstain_identity: Literal[1] = 1
    include: Literal[1] = 1
    exclude: Literal[1] = 1
    abstain_membership: Literal[1] = 1


class FreshV4PolicyBinding(StrictModel):
    policy_freeze_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dev_public_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dev_prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    final_prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dev_run_id: str = Field(min_length=1)
    final_run_id: str = Field(min_length=1)
    proposer_id: str = Field(min_length=1)
    proposer_version: str = Field(min_length=1)
    dev_run_sha256: dict[str, str]


class FreshV4ValidationFlags(StrictModel):
    identifier_policy_valid: Literal[True] = True
    derived_artifact_equivalence_valid: Literal[True] = True
    source_validation_valid: Literal[True] = True
    manifest_integrity_valid: Literal[True] = True
    policy_chronology_valid: Literal[True] = True
    hidden_freshness_valid: Literal[True] = True


class FreshV4ClaimBoundary(StrictModel):
    automatic_merge_authorized: Literal[False] = False
    automatic_membership_write_authorized: Literal[False] = False
    automatic_l2_write_authorized: Literal[False] = False
    embedding_is_authority: Literal[False] = False
    external_memory_systems_rerun: Literal[False] = False
    longmemeval_status: Literal["structured_l2_identity_unresolved"] = (
        "structured_l2_identity_unresolved"
    )
    core_impact: Literal["none"] = "none"


class FreshV4Preregistration(StrictModel):
    schema_version: Literal["natural-identity-fresh-v4-preregistration-v1"] = (
        "natural-identity-fresh-v4-preregistration-v1"
    )
    dataset_id: Literal["natural-identity-membership-fresh-v4"] = DATASET_ID
    status: Literal["frozen"] = "frozen"
    v2_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    v3_hidden_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    hidden_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    files_sha256: dict[str, str]
    protected_sha256: dict[str, str]
    identifier_policy: FreshV4IdentifierPolicy
    proposal_quality_thresholds: FreshV4Thresholds
    hidden_action_distribution: FreshV4ActionDistribution
    cross_session_hidden_count: int = Field(ge=2)
    prior_evidence_overlap_count: Literal[0] = 0
    prior_id_overlap_count: Literal[0] = 0
    policy_binding: FreshV4PolicyBinding
    validation: FreshV4ValidationFlags
    claim_boundary: FreshV4ClaimBoundary


def derive_fresh_v4_id(
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


def _relative_path(path: Path, workspace_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(workspace_root))
    except ValueError:
        return str(path.resolve())


def _protected_hashes(workspace_root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in PROTECTED_PATHS:
        path = _resolve(Path(relative), workspace_root)
        if not path.is_file():
            raise FileNotFoundError(f"protected artifact missing: {relative}")
        result[relative] = sha256_file(path)
    return result


def _require_formal_inputs(
    root: Path,
    v2_source_path: Path,
    v3_hidden_source_path: Path,
    hidden_source_path: Path,
    policy_freeze_path: Path,
    *,
    workspace_root: Path,
) -> None:
    if root != _resolve(FORMAL_ROOT, workspace_root):
        return
    expected = (
        _resolve(FORMAL_V2_SOURCE, workspace_root),
        _resolve(FORMAL_V3_HIDDEN_SOURCE, workspace_root),
        _resolve(FORMAL_V4_HIDDEN_SOURCE, workspace_root),
        _resolve(FORMAL_POLICY_FREEZE, workspace_root),
    )
    actual = (
        v2_source_path,
        v3_hidden_source_path,
        hidden_source_path,
        policy_freeze_path,
    )
    if actual != expected:
        raise ValueError("formal fresh v4 validation requires exact formal input paths")


def _observation(path: Path, workspace_root: Path) -> FrozenObservation:
    return FrozenObservation(
        path=_relative_path(path, workspace_root),
        sha256=sha256_file(path),
        mtime_ns=path.stat().st_mtime_ns,
    )


def _validate_policy_chronology(
    policy_freeze_path: Path,
    hidden_source_path: Path,
    *,
    workspace_root: Path,
) -> tuple[FreshV4PolicyBinding, FreshV4ChronologyReceipt]:
    _require_read_only(policy_freeze_path, "policy freeze")
    frozen = IdentityProposerPolicyFreeze.model_validate(load_json(policy_freeze_path))
    if not (
        frozen.dev_dataset_id == "natural-identity-membership-dev-repair-v4"
        and frozen.dev_case_count == 12
        and frozen.final_case_count == 6
    ):
        raise ValueError("fresh v4 policy composition mismatch")
    if Path(frozen.final_public_path).resolve() != _resolve(
        FORMAL_ROOT / "public.json", workspace_root
    ):
        raise ValueError("fresh v4 final public path mismatch")

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
    for path, expected, label in (
        (policy_path, frozen.policy_sha256, "policy"),
        (dev_public_path, frozen.dev_public_sha256, "dev public"),
        (dev_prompt_path, frozen.dev_prompt_sha256, "dev prompt"),
        (final_prompt_path, frozen.final_prompt_sha256, "final prompt"),
    ):
        if sha256_file(path) != expected:
            raise ValueError(f"{label} hash mismatch")

    dev_run_root = policy_freeze_path.parent / "model-runs" / frozen.dev_run_id
    run_paths = {name: dev_run_root / name for name in DEV_RUN_FILES}
    for name, path in run_paths.items():
        _require_read_only(path, f"passing dev run {name}")
    policy_mtime = policy_freeze_path.stat().st_mtime_ns
    dev_mtimes = [path.stat().st_mtime_ns for path in run_paths.values()]
    hidden_mtime = hidden_source_path.stat().st_mtime_ns
    if not policy_mtime < min(dev_mtimes):
        raise ValueError("policy freeze must predate passing dev run")
    if not max(dev_mtimes) < hidden_mtime:
        raise ValueError("passing dev run must predate hidden source")

    score = load_json(run_paths["score.json"])
    if not score.get("proposal_quality_ready") or not score.get("gate_safety_ready"):
        raise ValueError("fresh v4 policy dev gate did not pass")
    provenance = load_json(run_paths["provenance.json"])
    if provenance.get("history_context_inherited") is not False or provenance.get(
        "authority_or_gold_read_before_freeze"
    ) is not False:
        raise ValueError("fresh v4 dev provenance phase order mismatch")
    transport = load_json(run_paths["api-transport.json"])
    run_hashes = {name: sha256_file(path) for name, path in run_paths.items()}
    if not (
        transport.get("history_message_count") == 0
        and transport.get("request_message_count") == 1
        and transport.get("authority_or_gold_included") is False
        and transport.get("model_requested") == frozen.proposer_id
        and transport.get("dispatch_sha256") == run_hashes["dispatch.json"]
        and transport.get("prompt_sha256") == frozen.dev_prompt_sha256
        and transport.get("public_sha256") == frozen.dev_public_sha256
    ):
        raise ValueError("fresh v4 dev API transport mismatch")

    binding = FreshV4PolicyBinding(
        policy_freeze_sha256=sha256_file(policy_freeze_path),
        policy_sha256=frozen.policy_sha256,
        dev_public_sha256=frozen.dev_public_sha256,
        dev_prompt_sha256=frozen.dev_prompt_sha256,
        final_prompt_sha256=frozen.final_prompt_sha256,
        dev_run_id=frozen.dev_run_id,
        final_run_id=frozen.final_run_id,
        proposer_id=frozen.proposer_id,
        proposer_version=frozen.proposer_version,
        dev_run_sha256=run_hashes,
    )
    receipt = FreshV4ChronologyReceipt(
        policy_freeze=_observation(policy_freeze_path, workspace_root),
        dev_run_files={
            name: _observation(path, workspace_root)
            for name, path in run_paths.items()
        },
        hidden_source=_observation(hidden_source_path, workspace_root),
    )
    return binding, receipt


def _build_hidden_evidence(
    hidden: SourceConfig,
    *,
    workspace_root: Path,
) -> dict[str, Any]:
    base_payload = load_json(_resolve(BASE_EVIDENCE, workspace_root))
    base_index = _gold_evidence_index(_resolve(BASE_EVIDENCE, workspace_root))
    locomo_index = _locomo_dialogue_index(_resolve(LOCOMO_RAW, workspace_root))
    items: dict[str, list[dict[str, Any]]] = {}
    for case in hidden.cases:
        for mention in case.mentions:
            if mention.actor_locator is None:
                unit = next(
                    (
                        item
                        for item in base_index.get(mention.source_item_id, [])
                        if str(item.get("unit_id")) == str(mention.evidence_unit_id)
                    ),
                    None,
                )
                if unit is None:
                    raise ValueError(
                        f"fresh v4 base evidence missing: {mention.mention_id}"
                    )
                candidate = deepcopy(unit)
            else:
                locator = mention.actor_locator
                turn = locomo_index.get((locator.sample_id, locator.dia_id))
                if turn is None:
                    raise ValueError(
                        f"fresh v4 LoCoMo turn missing: {mention.mention_id}"
                    )
                session = locator.dia_id.split(":", 1)[0].removeprefix("D")
                candidate = {
                    "benchmark": "locomo",
                    "metadata": {"speaker": str(turn.get("speaker", ""))},
                    "source_id": "locomo10",
                    "source_ref": (
                        f"sample_id={locator.sample_id};session={session};"
                        f"dia_id={locator.dia_id}"
                    ),
                    "text": str(turn.get("text", "")),
                    "unit_id": str(mention.evidence_unit_id),
                }
            existing = items.setdefault(mention.source_item_id, [])
            prior = next(
                (
                    item
                    for item in existing
                    if str(item.get("unit_id")) == str(mention.evidence_unit_id)
                ),
                None,
            )
            if prior is not None and canonical_json_bytes(prior) != canonical_json_bytes(
                candidate
            ):
                raise ValueError("fresh v4 evidence unit conflict")
            if prior is None:
                existing.append(candidate)
    return {
        "schema_version": base_payload["schema_version"],
        "slice_id": "natural-identity-fresh-v4-hidden-evidence",
        "item_count": len(items),
        "items": items,
    }


def _build_source_and_mapping(
    hidden: SourceConfig,
    evidence_path: Path,
    *,
    workspace_root: Path,
) -> tuple[dict[str, Any], FreshV4IdMap]:
    cases: list[dict[str, Any]] = []
    case_pairs: list[FreshV4IdPair] = []
    mention_pairs: list[FreshV4IdPair] = []
    mention_ordinal = 0
    for case_ordinal, case_model in enumerate(hidden.cases, start=1):
        case = case_model.model_dump(mode="json", exclude_unset=True)
        source_case_id = case_model.case_id
        case_id = derive_fresh_v4_id(
            FRESH_NAMESPACE, "case", case_ordinal, source_case_id
        )
        case["case_id"] = case_id
        case_pairs.append(
            FreshV4IdPair(ordinal=case_ordinal, source=source_case_id, v4=case_id)
        )
        mention_mapping: dict[str, str] = {}
        for mention in case["mentions"]:
            mention_ordinal += 1
            source_mention_id = mention["mention_id"]
            mention_id = derive_fresh_v4_id(
                FRESH_NAMESPACE, "mention", mention_ordinal, source_mention_id
            )
            mention["mention_id"] = mention_id
            mention_mapping[source_mention_id] = mention_id
            mention_pairs.append(
                FreshV4IdPair(
                    ordinal=mention_ordinal,
                    source=source_mention_id,
                    v4=mention_id,
                )
            )
        case["authority"]["required_mention_ids"] = [
            mention_mapping[item]
            for item in case["authority"]["required_mention_ids"]
        ]
        cases.append(case)
    payload = {
        "schema_version": "natural-identity-source-config-v1",
        "dataset_id": DATASET_ID,
        "source_inputs": {
            "gold_evidence": _relative_path(evidence_path, workspace_root),
            "locomo_raw": _relative_path(
                _resolve(LOCOMO_RAW, workspace_root), workspace_root
            ),
        },
        "cases": cases,
    }
    mapping = FreshV4IdMap(case_ids=case_pairs, mention_ids=mention_pairs)
    _validate_mapping(mapping)
    SourceConfig.model_validate(payload)
    return payload, mapping


def _validate_mapping(mapping: FreshV4IdMap) -> None:
    case_sources = [item.source for item in mapping.case_ids]
    case_values = [item.v4 for item in mapping.case_ids]
    mention_sources = [item.source for item in mapping.mention_ids]
    mention_values = [item.v4 for item in mapping.mention_ids]
    if len(case_sources) != len(set(case_sources)) or len(case_values) != len(
        set(case_values)
    ):
        raise ValueError("fresh v4 case id mapping must be bijective")
    if len(mention_sources) != len(set(mention_sources)) or len(
        mention_values
    ) != len(set(mention_values)):
        raise ValueError("fresh v4 mention id mapping must be bijective")
    for kind, values in (("case", mapping.case_ids), ("mention", mapping.mention_ids)):
        for expected_ordinal, item in enumerate(values, start=1):
            if item.ordinal != expected_ordinal:
                raise ValueError(f"fresh v4 {kind} ordinals must be contiguous")
            expected = derive_fresh_v4_id(
                FRESH_NAMESPACE, kind, item.ordinal, item.source
            )
            actual = item.v4
            pattern = CASE_ID_RE if kind == "case" else MENTION_ID_RE
            if not pattern.fullmatch(actual) or actual != expected:
                raise ValueError(f"invalid derived fresh v4 {kind} id: {actual}")


def _action_distribution(source: SourceConfig) -> dict[str, int]:
    distribution = {key: 0 for key in EXPECTED_ACTION_DISTRIBUTION}
    for case in source.cases:
        action = case.gold.expected_action
        key = f"abstain_{case.relation_kind}" if action == "abstain" else action
        if key not in distribution:
            raise ValueError(f"unexpected fresh v4 hidden action: {key}")
        distribution[key] += 1
    return distribution


def _evidence_refs(source: SourceConfig) -> set[tuple[str, str]]:
    return {
        (mention.source_item_id, str(mention.evidence_unit_id))
        for case in source.cases
        for mention in case.mentions
    }


def _all_ids(source: SourceConfig) -> set[str]:
    return {
        value
        for case in source.cases
        for value in [case.case_id, *[mention.mention_id for mention in case.mentions]]
    }


def _overlap_counts(
    v2: SourceConfig,
    v3_hidden: SourceConfig,
    v4_dev: SourceConfig,
    hidden: SourceConfig,
    combined: SourceConfig,
) -> tuple[int, int]:
    prior_sources = (v2, v3_hidden, v4_dev)
    prior_refs = set().union(*(_evidence_refs(source) for source in prior_sources))
    evidence_overlap = len(prior_refs & _evidence_refs(hidden))
    prior_ids = set().union(*(_all_ids(source) for source in prior_sources))
    id_overlap = len(prior_ids & (_all_ids(hidden) | _all_ids(combined)))
    return evidence_overlap, id_overlap


def _session_token(source_ref: str) -> str | None:
    for field in ("session_index", "session", "session_id"):
        match = re.search(rf"(?:^|;){field}=([^;]+)", source_ref)
        if match:
            return f"{field}:{match.group(1)}"
    return None


def _cross_session_count(public: dict[str, Any]) -> int:
    count = 0
    for case in public.get("cases", []):
        sessions = {
            token
            for mention in case.get("mentions", [])
            if (token := _session_token(str(mention.get("source_ref", ""))))
        }
        if len(sessions) >= 2:
            count += 1
    return count


def _core_validation(
    v2_source_path: Path,
    v3_hidden_source_path: Path,
    hidden_source_path: Path,
    root: Path,
    *,
    policy_freeze_path: Path,
    workspace_root: Path,
) -> dict[str, Any]:
    for path, label in (
        (v2_source_path, "v2 source"),
        (v3_hidden_source_path, "v3 hidden source"),
        (hidden_source_path, "fresh v4 hidden source"),
    ):
        _require_read_only(path, label)
    for name in GENERATED_FILES:
        if name != "preregistration.json":
            _require_read_only(root / name, f"fresh v4 artifact {name}")

    binding, receipt = _validate_policy_chronology(
        policy_freeze_path, hidden_source_path, workspace_root=workspace_root
    )
    actual_receipt = FreshV4ChronologyReceipt.model_validate(
        load_json(root / "chronology-receipt-v4.json")
    )
    if canonical_json_bytes(actual_receipt) != canonical_json_bytes(receipt):
        raise ValueError("fresh v4 chronology receipt mismatch")

    v2 = SourceConfig.model_validate(load_json(v2_source_path))
    v3_hidden = SourceConfig.model_validate(load_json(v3_hidden_source_path))
    v4_dev = SourceConfig.model_validate(
        load_json(_resolve(FORMAL_V4_DEV_SOURCE, workspace_root))
    )
    hidden = SourceConfig.model_validate(load_json(hidden_source_path))
    if hidden.dataset_id != HIDDEN_DATASET_ID:
        raise ValueError("fresh v4 hidden dataset id mismatch")
    if len(hidden.cases) != 6 or any(case.split != "hidden" for case in hidden.cases):
        raise ValueError("fresh v4 hidden source must contain six hidden cases")
    distribution = _action_distribution(hidden)
    if distribution != EXPECTED_ACTION_DISTRIBUTION:
        raise ValueError("fresh v4 hidden action distribution mismatch")

    expected_evidence = _build_hidden_evidence(hidden, workspace_root=workspace_root)
    if canonical_json_bytes(load_json(root / "hidden-gold-evidence.json")) != canonical_json_bytes(
        expected_evidence
    ):
        raise ValueError("fresh v4 hidden evidence replay mismatch")
    expected_source, expected_mapping = _build_source_and_mapping(
        hidden,
        root / "hidden-gold-evidence.json",
        workspace_root=workspace_root,
    )
    actual_source_raw = load_json(root / "source-cases.json")
    if canonical_json_bytes(actual_source_raw) != canonical_json_bytes(expected_source):
        raise ValueError("fresh v4 source semantic equivalence mismatch")
    actual_mapping = FreshV4IdMap.model_validate(load_json(root / "opaque-id-map.json"))
    if canonical_json_bytes(actual_mapping) != canonical_json_bytes(expected_mapping):
        raise ValueError("fresh v4 id mapping mismatch")
    combined = SourceConfig.model_validate(actual_source_raw)
    _validate_source_cases(
        combined.cases,
        _gold_evidence_index(root / "hidden-gold-evidence.json"),
        _locomo_dialogue_index(_resolve(LOCOMO_RAW, workspace_root)),
    )
    evidence_overlap, id_overlap = _overlap_counts(
        v2, v3_hidden, v4_dev, hidden, combined
    )
    if evidence_overlap:
        raise ValueError("prior hidden evidence overlap")
    if id_overlap:
        raise ValueError("prior identity id overlap")

    expected_artifacts = _derive_expected_artifacts(
        combined, workspace_root=workspace_root
    )
    for name, expected in expected_artifacts.items():
        if canonical_json_bytes(load_json(root / name)) != canonical_json_bytes(expected):
            raise ValueError(f"derived artifact semantic equivalence mismatch: {name}")
    base = validate_natural_identity_slice(root, workspace_root=workspace_root)
    if not (
        base["case_count"] == 6
        and base["dev_count"] == 0
        and base["hidden_count"] == 6
    ):
        raise ValueError("fresh v4 slice composition mismatch")
    public = load_json(root / "public.json")
    cross_session = _cross_session_count(public)
    if cross_session < 2:
        raise ValueError("fresh v4 requires at least two cross-session cases")
    public_bytes = canonical_json_bytes(public)
    for item in [*expected_mapping.case_ids, *expected_mapping.mention_ids]:
        if item.source.encode("utf-8") in public_bytes:
            raise ValueError("fresh v4 public contains source id residue")
    return {
        **base,
        "hidden_action_distribution": distribution,
        "cross_session_hidden_count": cross_session,
        "prior_evidence_overlap_count": evidence_overlap,
        "prior_id_overlap_count": id_overlap,
        "policy_chronology_valid": True,
        "policy_binding": binding.model_dump(mode="json"),
    }


def _file_hashes(root: Path, hidden_source_path: Path) -> dict[str, str]:
    return {
        "hidden-source-cases.json": sha256_file(hidden_source_path),
        **{
            name: sha256_file(root / name)
            for name in GENERATED_FILES
            if name != "preregistration.json"
        },
    }


def _build_preregistration(
    core: dict[str, Any],
    v2_source_path: Path,
    v3_hidden_source_path: Path,
    hidden_source_path: Path,
    root: Path,
    *,
    workspace_root: Path,
) -> FreshV4Preregistration:
    return FreshV4Preregistration(
        v2_source_sha256=sha256_file(v2_source_path),
        v3_hidden_source_sha256=sha256_file(v3_hidden_source_path),
        hidden_source_sha256=sha256_file(hidden_source_path),
        files_sha256=_file_hashes(root, hidden_source_path),
        protected_sha256=_protected_hashes(workspace_root),
        identifier_policy=FreshV4IdentifierPolicy(),
        proposal_quality_thresholds=FreshV4Thresholds(**PROPOSAL_THRESHOLDS),
        hidden_action_distribution=FreshV4ActionDistribution(),
        cross_session_hidden_count=core["cross_session_hidden_count"],
        prior_evidence_overlap_count=0,
        prior_id_overlap_count=0,
        policy_binding=FreshV4PolicyBinding.model_validate(core["policy_binding"]),
        validation=FreshV4ValidationFlags(),
        claim_boundary=FreshV4ClaimBoundary(),
    )


def prepare_fresh_identity_v4(
    v2_source_path: Path,
    v3_hidden_source_path: Path,
    hidden_source_path: Path,
    output_root: Path,
    *,
    policy_freeze_path: Path,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    workspace_root = (workspace_root or Path.cwd()).resolve()
    v2_source_path = _resolve(v2_source_path, workspace_root)
    v3_hidden_source_path = _resolve(v3_hidden_source_path, workspace_root)
    hidden_source_path = _resolve(hidden_source_path, workspace_root)
    policy_freeze_path = _resolve(policy_freeze_path, workspace_root)
    output_root = output_root.resolve()
    _require_formal_inputs(
        output_root,
        v2_source_path,
        v3_hidden_source_path,
        hidden_source_path,
        policy_freeze_path,
        workspace_root=workspace_root,
    )
    for path, label in (
        (v2_source_path, "v2 source"),
        (v3_hidden_source_path, "v3 hidden source"),
        (hidden_source_path, "fresh v4 hidden source"),
    ):
        _require_read_only(path, label)
    binding, receipt = _validate_policy_chronology(
        policy_freeze_path, hidden_source_path, workspace_root=workspace_root
    )
    del binding
    hidden = SourceConfig.model_validate(load_json(hidden_source_path))
    evidence = _build_hidden_evidence(hidden, workspace_root=workspace_root)
    source, mapping = _build_source_and_mapping(
        hidden,
        output_root / "hidden-gold-evidence.json",
        workspace_root=workspace_root,
    )
    write_json_immutable(output_root / "hidden-gold-evidence.json", evidence)
    write_json_immutable(output_root / "source-cases.json", source)
    write_json_immutable(output_root / "opaque-id-map.json", mapping)
    write_json_immutable(output_root / "chronology-receipt-v4.json", receipt)
    for name in (
        "hidden-gold-evidence.json",
        "source-cases.json",
        "opaque-id-map.json",
        "chronology-receipt-v4.json",
    ):
        (output_root / name).chmod(0o444)
    freeze_natural_identity_slice(
        output_root / "source-cases.json",
        output_root,
        workspace_root=workspace_root,
    )
    for name in ("public.json", "authority.json", "gold.json", "manifest.json"):
        (output_root / name).chmod(0o444)
    core = _core_validation(
        v2_source_path,
        v3_hidden_source_path,
        hidden_source_path,
        output_root,
        policy_freeze_path=policy_freeze_path,
        workspace_root=workspace_root,
    )
    preregistration = _build_preregistration(
        core,
        v2_source_path,
        v3_hidden_source_path,
        hidden_source_path,
        output_root,
        workspace_root=workspace_root,
    )
    write_json_immutable(output_root / "preregistration.json", preregistration)
    (output_root / "preregistration.json").chmod(0o444)
    return validate_fresh_identity_v4(
        v2_source_path,
        v3_hidden_source_path,
        hidden_source_path,
        output_root,
        policy_freeze_path=policy_freeze_path,
        workspace_root=workspace_root,
    )


def validate_fresh_identity_v4(
    v2_source_path: Path,
    v3_hidden_source_path: Path,
    hidden_source_path: Path,
    root: Path,
    *,
    policy_freeze_path: Path,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    workspace_root = (workspace_root or Path.cwd()).resolve()
    v2_source_path = _resolve(v2_source_path, workspace_root)
    v3_hidden_source_path = _resolve(v3_hidden_source_path, workspace_root)
    hidden_source_path = _resolve(hidden_source_path, workspace_root)
    policy_freeze_path = _resolve(policy_freeze_path, workspace_root)
    root = root.resolve()
    _require_formal_inputs(
        root,
        v2_source_path,
        v3_hidden_source_path,
        hidden_source_path,
        policy_freeze_path,
        workspace_root=workspace_root,
    )
    core = _core_validation(
        v2_source_path,
        v3_hidden_source_path,
        hidden_source_path,
        root,
        policy_freeze_path=policy_freeze_path,
        workspace_root=workspace_root,
    )
    actual = FreshV4Preregistration.model_validate(
        load_json(root / "preregistration.json")
    )
    expected = _build_preregistration(
        core,
        v2_source_path,
        v3_hidden_source_path,
        hidden_source_path,
        root,
        workspace_root=workspace_root,
    )
    if canonical_json_bytes(actual) != canonical_json_bytes(expected):
        raise ValueError("fresh v4 preregistration mismatch")
    for name in GENERATED_FILES:
        _require_read_only(root / name, f"fresh v4 artifact {name}")
    return core
