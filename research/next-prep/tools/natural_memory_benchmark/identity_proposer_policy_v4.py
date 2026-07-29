from __future__ import annotations

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
from .identity_proposal_fresh import (
    PROTECTED_PATHS as BASE_PROTECTED_PATHS,
    _derive_expected_artifacts,
)
from .identity_proposal_opaque import derive_opaque_id, validate_opaque_identity_slice
from .io import canonical_json_bytes, load_json, sha256_file, write_json_immutable


DATASET_ID = "natural-identity-membership-dev-repair-v4"
DIAGNOSTIC_DATASET_ID = "natural-identity-membership-actor-binding-diagnostic-v4"
DIAGNOSTIC_NAMESPACE = "natural-identity-membership-dev-repair-v4:2026-07-28"
FORMAL_ROOT = Path("artifacts/identity-memory-experiment/dev-repair-v4")
FORMAL_V1_SOURCE = Path(
    "artifacts/identity-memory-experiment/natural-v1/source-cases.json"
)
FORMAL_V2_SOURCE = Path(
    "artifacts/identity-memory-experiment/natural-v2/source-cases.json"
)
FORMAL_DIAGNOSTIC_SOURCE = FORMAL_ROOT / "diagnostic-source-cases.json"
FORMAL_DIAGNOSTIC_EVIDENCE = FORMAL_ROOT / "diagnostic-gold-evidence.json"
BASE_EVIDENCE = Path(
    "artifacts/natural-benchmark-slices/slice-v1/gold-evidence.json"
)
LOCOMO_RAW = Path(
    "artifacts/natural-benchmark-slices/raw/locomo/locomo10.json"
)
FRESH_V3_HIDDEN_SOURCE = Path(
    "artifacts/identity-memory-experiment/natural-v3-fresh/hidden-source-cases.json"
)
EXPECTED_ACTION_DISTRIBUTION = {"include": 2, "exclude": 2, "abstain": 2}
GENERATED_FILES = (
    "combined-gold-evidence.json",
    "source-cases.json",
    "public.json",
    "authority.json",
    "gold.json",
    "manifest.json",
    "preregistration.json",
)

V3_PROTECTED_PATHS = (
    "artifacts/identity-memory-experiment/natural-v3-fresh/hidden-source-cases.json",
    "artifacts/identity-memory-experiment/natural-v3-fresh/source-cases.json",
    "artifacts/identity-memory-experiment/natural-v3-fresh/opaque-id-map.json",
    "artifacts/identity-memory-experiment/natural-v3-fresh/preregistration.json",
    "artifacts/identity-memory-experiment/natural-v3-fresh/public.json",
    "artifacts/identity-memory-experiment/natural-v3-fresh/authority.json",
    "artifacts/identity-memory-experiment/natural-v3-fresh/gold.json",
    "artifacts/identity-memory-experiment/natural-v3-fresh/manifest.json",
    "artifacts/identity-memory-experiment/natural-v3-fresh/model-runs/run-20260727T160000Z-claude-sonnet-4-6-fresh-v3/dispatch.json",
    "artifacts/identity-memory-experiment/natural-v3-fresh/model-runs/run-20260727T160000Z-claude-sonnet-4-6-fresh-v3/api-transport.json",
    "artifacts/identity-memory-experiment/natural-v3-fresh/model-runs/run-20260727T160000Z-claude-sonnet-4-6-fresh-v3/proposals.json",
    "artifacts/identity-memory-experiment/natural-v3-fresh/model-runs/run-20260727T160000Z-claude-sonnet-4-6-fresh-v3/provenance.json",
    "artifacts/identity-memory-experiment/natural-v3-fresh/model-runs/run-20260727T160000Z-claude-sonnet-4-6-fresh-v3/score.json",
    "artifacts/identity-memory-experiment/natural-v3-fresh/model-runs/run-20260727T160000Z-claude-sonnet-4-6-fresh-v3/report.md",
    "artifacts/identity-memory-experiment/natural-v3-fresh/model-runs/run-20260727T160000Z-claude-sonnet-4-6-fresh-v3/error-analysis.md",
    "artifacts/identity-memory-experiment/dev-repair-v3/policy-v3.md",
    "artifacts/identity-memory-experiment/dev-repair-v3/dev-proposer-prompt-v3.md",
    "artifacts/identity-memory-experiment/dev-repair-v3/final-proposer-prompt-v3.md",
    "artifacts/identity-memory-experiment/dev-repair-v3/policy-freeze-v3.json",
    "artifacts/identity-memory-experiment/dev-repair-v3/chronology-receipt-v3.json",
)
PROTECTED_PATHS = (*BASE_PROTECTED_PATHS, *V3_PROTECTED_PATHS)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DiagnosticActionDistribution(StrictModel):
    include: Literal[2] = 2
    exclude: Literal[2] = 2
    abstain: Literal[2] = 2


class IdentityDevV4ClaimBoundary(StrictModel):
    automatic_merge_authorized: Literal[False] = False
    automatic_membership_write_authorized: Literal[False] = False
    automatic_l2_write_authorized: Literal[False] = False
    embedding_is_authority: Literal[False] = False
    external_memory_systems_rerun: Literal[False] = False
    longmemeval_status: Literal["structured_l2_identity_unresolved"] = (
        "structured_l2_identity_unresolved"
    )
    fresh_v3_hidden_used_for_development: Literal[False] = False
    core_impact: Literal["none"] = "none"


class IdentityDevV4Preregistration(StrictModel):
    schema_version: Literal["natural-identity-dev-v4-preregistration-v1"] = (
        "natural-identity-dev-v4-preregistration-v1"
    )
    dataset_id: Literal["natural-identity-membership-dev-repair-v4"] = DATASET_ID
    status: Literal["frozen"] = "frozen"
    v2_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagnostic_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagnostic_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    files_sha256: dict[str, str]
    protected_sha256: dict[str, str]
    diagnostic_action_distribution: DiagnosticActionDistribution
    prior_hidden_evidence_overlap_count: Literal[0] = 0
    prior_id_overlap_count: Literal[0] = 0
    claim_boundary: IdentityDevV4ClaimBoundary


def _resolve(path: Path, workspace_root: Path) -> Path:
    return path.resolve() if path.is_absolute() else (workspace_root / path).resolve()


def _require_read_only(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} missing: {path}")
    if path.stat().st_mode & 0o222:
        raise ValueError(f"{label} must be read-only")


def _path_for_source(path: Path, workspace_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(workspace_root))
    except ValueError:
        return str(path.resolve())


def _protected_hashes(workspace_root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in PROTECTED_PATHS:
        path = _resolve(Path(relative), workspace_root)
        if not path.is_file():
            raise FileNotFoundError(f"protected artifact missing: {relative}")
        hashes[relative] = sha256_file(path)
    return hashes


def _evidence_signature(case: Any) -> tuple[str, ...]:
    return tuple(
        sorted(
            f"{mention.source_item_id}:{mention.evidence_unit_id}"
            for mention in case.mentions
        )
    )


def _action_distribution(source: SourceConfig) -> dict[str, int]:
    distribution = {key: 0 for key in EXPECTED_ACTION_DISTRIBUTION}
    for case in source.cases:
        action = case.gold.expected_action
        if action not in distribution:
            raise ValueError("diagnostic cases must use membership actions")
        distribution[action] += 1
    return distribution


def _merge_evidence(
    base_payload: dict[str, Any], diagnostic_payload: dict[str, Any]
) -> dict[str, Any]:
    merged = deepcopy(base_payload)
    merged["slice_id"] = "identity-dev-v4-combined"
    items = merged["items"]
    for item_id, units in diagnostic_payload["items"].items():
        existing = items.setdefault(item_id, [])
        by_unit = {str(item["unit_id"]): item for item in existing}
        for unit in units:
            unit_id = str(unit["unit_id"])
            if unit_id in by_unit:
                if canonical_json_bytes(by_unit[unit_id]) != canonical_json_bytes(unit):
                    raise ValueError(
                        f"diagnostic evidence conflicts with frozen base: {item_id}/{unit_id}"
                    )
                continue
            existing.append(unit)
            by_unit[unit_id] = unit
    merged["item_count"] = len(items)
    return merged


def _remap_diagnostic_cases(source: SourceConfig) -> list[dict[str, Any]]:
    remapped: list[dict[str, Any]] = []
    mention_ordinal = 0
    for case_ordinal, case_model in enumerate(source.cases, start=1):
        case = case_model.model_dump(mode="json", exclude_unset=True)
        case["case_id"] = derive_opaque_id(
            DIAGNOSTIC_NAMESPACE,
            "case",
            case_ordinal,
            case_model.case_id,
        )
        mention_mapping: dict[str, str] = {}
        for mention in case["mentions"]:
            mention_ordinal += 1
            source_mention_id = mention["mention_id"]
            remapped_id = derive_opaque_id(
                DIAGNOSTIC_NAMESPACE,
                "mention",
                mention_ordinal,
                source_mention_id,
            )
            mention_mapping[source_mention_id] = remapped_id
            mention["mention_id"] = remapped_id
        case["authority"]["required_mention_ids"] = [
            mention_mapping[item]
            for item in case["authority"]["required_mention_ids"]
        ]
        remapped.append(case)
    return remapped


def _validate_diagnostic_evidence(
    source: SourceConfig,
    diagnostic_evidence_path: Path,
    *,
    workspace_root: Path,
) -> None:
    evidence_index = _gold_evidence_index(diagnostic_evidence_path)
    locomo_index = _locomo_dialogue_index(_resolve(LOCOMO_RAW, workspace_root))
    _validate_source_cases(source.cases, evidence_index, locomo_index)
    base_index = _gold_evidence_index(_resolve(BASE_EVIDENCE, workspace_root))
    for case in source.cases:
        for mention in case.mentions:
            unit = next(
                item
                for item in evidence_index[mention.source_item_id]
                if str(item["unit_id"]) == str(mention.evidence_unit_id)
            )
            if mention.actor_locator is not None:
                locator = mention.actor_locator
                session = locator.dia_id.split(":", 1)[0].removeprefix("D")
                expected_ref = (
                    f"sample_id={locator.sample_id};session={session};"
                    f"dia_id={locator.dia_id}"
                )
                if unit.get("source_ref") != expected_ref:
                    raise ValueError(
                        f"diagnostic LoCoMo source ref mismatch: {mention.mention_id}"
                    )
            else:
                base_unit = next(
                    (
                        item
                        for item in base_index.get(mention.source_item_id, [])
                        if str(item["unit_id"]) == str(mention.evidence_unit_id)
                    ),
                    None,
                )
                if base_unit is None or canonical_json_bytes(base_unit) != canonical_json_bytes(
                    unit
                ):
                    raise ValueError(
                        f"diagnostic non-actor evidence mismatch: {mention.mention_id}"
                    )


def _build_expected(
    v2_source: SourceConfig,
    diagnostic_source: SourceConfig,
    diagnostic_evidence: dict[str, Any],
    output_root: Path,
    *,
    workspace_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    base_evidence = load_json(_resolve(BASE_EVIDENCE, workspace_root))
    combined_evidence = _merge_evidence(base_evidence, diagnostic_evidence)
    dev_cases = [
        case.model_dump(mode="json", exclude_unset=True)
        for case in v2_source.cases
        if case.split == "dev"
    ]
    if len(dev_cases) != 6:
        raise ValueError("frozen opaque v2 must contain six dev cases")
    combined_path = output_root / "combined-gold-evidence.json"
    source = {
        "schema_version": "natural-identity-source-config-v1",
        "dataset_id": DATASET_ID,
        "source_inputs": {
            "gold_evidence": _path_for_source(combined_path, workspace_root),
            "locomo_raw": _path_for_source(
                _resolve(LOCOMO_RAW, workspace_root), workspace_root
            ),
        },
        "cases": [*dev_cases, *_remap_diagnostic_cases(diagnostic_source)],
    }
    SourceConfig.model_validate(source)
    return combined_evidence, source


def _overlap_counts(
    v2_source: SourceConfig,
    diagnostic_source: SourceConfig,
    combined_source: SourceConfig,
    *,
    workspace_root: Path,
) -> tuple[int, int]:
    fresh_v3_hidden = SourceConfig.model_validate(
        load_json(_resolve(FRESH_V3_HIDDEN_SOURCE, workspace_root))
    )
    prior_hidden = [
        *[case for case in v2_source.cases if case.split == "hidden"],
        *fresh_v3_hidden.cases,
    ]
    prior_signatures = {_evidence_signature(case) for case in prior_hidden}
    diagnostic_signatures = {
        _evidence_signature(case) for case in diagnostic_source.cases
    }
    evidence_overlap = len(prior_signatures & diagnostic_signatures)

    prior_ids = {
        value
        for case in [*v2_source.cases, *fresh_v3_hidden.cases]
        for value in [case.case_id, *[mention.mention_id for mention in case.mentions]]
    }
    combined_ids = {
        value
        for case in combined_source.cases[6:]
        for value in [case.case_id, *[mention.mention_id for mention in case.mentions]]
    }
    return evidence_overlap, len(prior_ids & combined_ids)


def _files_sha256(
    root: Path,
    diagnostic_source_path: Path,
    diagnostic_evidence_path: Path,
) -> dict[str, str]:
    return {
        "diagnostic-source-cases.json": sha256_file(diagnostic_source_path),
        "diagnostic-gold-evidence.json": sha256_file(diagnostic_evidence_path),
        **{
            name: sha256_file(root / name)
            for name in GENERATED_FILES
            if name != "preregistration.json"
        },
    }


def _build_preregistration(
    v2_source_path: Path,
    diagnostic_source_path: Path,
    diagnostic_evidence_path: Path,
    root: Path,
    *,
    workspace_root: Path,
) -> IdentityDevV4Preregistration:
    return IdentityDevV4Preregistration(
        v2_source_sha256=sha256_file(v2_source_path),
        diagnostic_source_sha256=sha256_file(diagnostic_source_path),
        diagnostic_evidence_sha256=sha256_file(diagnostic_evidence_path),
        files_sha256=_files_sha256(
            root, diagnostic_source_path, diagnostic_evidence_path
        ),
        protected_sha256=_protected_hashes(workspace_root),
        diagnostic_action_distribution=DiagnosticActionDistribution(),
        prior_hidden_evidence_overlap_count=0,
        prior_id_overlap_count=0,
        claim_boundary=IdentityDevV4ClaimBoundary(),
    )


def _require_formal_inputs(
    root: Path,
    v2_source_path: Path,
    diagnostic_source_path: Path,
    diagnostic_evidence_path: Path,
    *,
    workspace_root: Path,
) -> None:
    if root != _resolve(FORMAL_ROOT, workspace_root):
        return
    expected = (
        _resolve(FORMAL_V2_SOURCE, workspace_root),
        _resolve(FORMAL_DIAGNOSTIC_SOURCE, workspace_root),
        _resolve(FORMAL_DIAGNOSTIC_EVIDENCE, workspace_root),
    )
    if (v2_source_path, diagnostic_source_path, diagnostic_evidence_path) != expected:
        raise ValueError("formal dev v4 validation requires exact formal input paths")


def _core_validation(
    v2_source_path: Path,
    diagnostic_source_path: Path,
    diagnostic_evidence_path: Path,
    root: Path,
    *,
    workspace_root: Path,
) -> dict[str, Any]:
    for path, label in (
        (v2_source_path, "v2 source"),
        (diagnostic_source_path, "diagnostic source"),
        (diagnostic_evidence_path, "diagnostic evidence"),
    ):
        _require_read_only(path, label)
    validate_opaque_identity_slice(
        _resolve(FORMAL_V1_SOURCE, workspace_root),
        _resolve(FORMAL_V2_SOURCE, workspace_root).parent,
        workspace_root=workspace_root,
    )
    if sha256_file(v2_source_path) != sha256_file(
        _resolve(FORMAL_V2_SOURCE, workspace_root)
    ):
        raise ValueError("dev v4 source must match frozen opaque v2 source")

    v2_source = SourceConfig.model_validate(load_json(v2_source_path))
    diagnostic_source = SourceConfig.model_validate(load_json(diagnostic_source_path))
    if diagnostic_source.dataset_id != DIAGNOSTIC_DATASET_ID:
        raise ValueError("diagnostic dataset id mismatch")
    if len(diagnostic_source.cases) != 6 or any(
        case.split != "dev" or case.relation_kind != "membership"
        for case in diagnostic_source.cases
    ):
        raise ValueError("diagnostic source must contain six dev membership cases")
    _validate_diagnostic_evidence(
        diagnostic_source,
        diagnostic_evidence_path,
        workspace_root=workspace_root,
    )
    distribution = _action_distribution(diagnostic_source)
    if distribution != EXPECTED_ACTION_DISTRIBUTION:
        raise ValueError("diagnostic action distribution mismatch")

    diagnostic_evidence = load_json(diagnostic_evidence_path)
    expected_evidence, expected_source = _build_expected(
        v2_source,
        diagnostic_source,
        diagnostic_evidence,
        root,
        workspace_root=workspace_root,
    )
    if canonical_json_bytes(load_json(root / "combined-gold-evidence.json")) != canonical_json_bytes(
        expected_evidence
    ):
        raise ValueError("combined diagnostic evidence mismatch")
    actual_source_raw = load_json(root / "source-cases.json")
    if canonical_json_bytes(actual_source_raw) != canonical_json_bytes(expected_source):
        raise ValueError("combined dev source semantic equivalence mismatch")
    combined_source = SourceConfig.model_validate(actual_source_raw)
    evidence_overlap, id_overlap = _overlap_counts(
        v2_source,
        diagnostic_source,
        combined_source,
        workspace_root=workspace_root,
    )
    if evidence_overlap:
        raise ValueError("prior hidden evidence overlap")
    if id_overlap:
        raise ValueError("prior identity id overlap")

    expected_artifacts = _derive_expected_artifacts(
        combined_source, workspace_root=workspace_root
    )
    for name, expected in expected_artifacts.items():
        if canonical_json_bytes(load_json(root / name)) != canonical_json_bytes(expected):
            raise ValueError(f"derived artifact semantic equivalence mismatch: {name}")
    base = validate_natural_identity_slice(root, workspace_root=workspace_root)
    if not (
        base["case_count"] == 12
        and base["dev_count"] == 12
        and base["hidden_count"] == 0
    ):
        raise ValueError("dev v4 slice composition mismatch")
    return {
        **base,
        "diagnostic_action_distribution": distribution,
        "prior_hidden_evidence_overlap_count": evidence_overlap,
        "prior_id_overlap_count": id_overlap,
        "diagnostic_source_sha256": sha256_file(diagnostic_source_path),
        "diagnostic_evidence_sha256": sha256_file(diagnostic_evidence_path),
    }


def prepare_identity_dev_v4(
    v2_source_path: Path,
    diagnostic_source_path: Path,
    diagnostic_evidence_path: Path,
    output_root: Path,
    *,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    workspace_root = (workspace_root or Path.cwd()).resolve()
    v2_source_path = _resolve(v2_source_path, workspace_root)
    diagnostic_source_path = _resolve(diagnostic_source_path, workspace_root)
    diagnostic_evidence_path = _resolve(diagnostic_evidence_path, workspace_root)
    output_root = output_root.resolve()
    _require_formal_inputs(
        output_root,
        v2_source_path,
        diagnostic_source_path,
        diagnostic_evidence_path,
        workspace_root=workspace_root,
    )
    for path, label in (
        (v2_source_path, "v2 source"),
        (diagnostic_source_path, "diagnostic source"),
        (diagnostic_evidence_path, "diagnostic evidence"),
    ):
        _require_read_only(path, label)

    v2_source = SourceConfig.model_validate(load_json(v2_source_path))
    diagnostic_source = SourceConfig.model_validate(load_json(diagnostic_source_path))
    _validate_diagnostic_evidence(
        diagnostic_source,
        diagnostic_evidence_path,
        workspace_root=workspace_root,
    )
    distribution = _action_distribution(diagnostic_source)
    if distribution != EXPECTED_ACTION_DISTRIBUTION:
        raise ValueError("diagnostic action distribution mismatch")
    combined_evidence, combined_source = _build_expected(
        v2_source,
        diagnostic_source,
        load_json(diagnostic_evidence_path),
        output_root,
        workspace_root=workspace_root,
    )
    write_json_immutable(output_root / "combined-gold-evidence.json", combined_evidence)
    write_json_immutable(output_root / "source-cases.json", combined_source)
    freeze_natural_identity_slice(
        output_root / "source-cases.json",
        output_root,
        workspace_root=workspace_root,
    )
    core = _core_validation(
        v2_source_path,
        diagnostic_source_path,
        diagnostic_evidence_path,
        output_root,
        workspace_root=workspace_root,
    )
    preregistration = _build_preregistration(
        v2_source_path,
        diagnostic_source_path,
        diagnostic_evidence_path,
        output_root,
        workspace_root=workspace_root,
    )
    write_json_immutable(output_root / "preregistration.json", preregistration)
    for name in GENERATED_FILES:
        (output_root / name).chmod(0o444)
    return validate_identity_dev_v4(
        v2_source_path,
        diagnostic_source_path,
        diagnostic_evidence_path,
        output_root,
        workspace_root=workspace_root,
    )


def validate_identity_dev_v4(
    v2_source_path: Path,
    diagnostic_source_path: Path,
    diagnostic_evidence_path: Path,
    root: Path,
    *,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    workspace_root = (workspace_root or Path.cwd()).resolve()
    v2_source_path = _resolve(v2_source_path, workspace_root)
    diagnostic_source_path = _resolve(diagnostic_source_path, workspace_root)
    diagnostic_evidence_path = _resolve(diagnostic_evidence_path, workspace_root)
    root = root.resolve()
    _require_formal_inputs(
        root,
        v2_source_path,
        diagnostic_source_path,
        diagnostic_evidence_path,
        workspace_root=workspace_root,
    )
    core = _core_validation(
        v2_source_path,
        diagnostic_source_path,
        diagnostic_evidence_path,
        root,
        workspace_root=workspace_root,
    )
    actual = IdentityDevV4Preregistration.model_validate(
        load_json(root / "preregistration.json")
    )
    expected = _build_preregistration(
        v2_source_path,
        diagnostic_source_path,
        diagnostic_evidence_path,
        root,
        workspace_root=workspace_root,
    )
    if canonical_json_bytes(actual) != canonical_json_bytes(expected):
        raise ValueError("dev v4 preregistration mismatch")
    for name in GENERATED_FILES:
        _require_read_only(root / name, f"formal dev v4 artifact {name}")
    return core
