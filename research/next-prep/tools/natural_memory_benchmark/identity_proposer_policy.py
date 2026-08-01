from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .frozen_input_guard import require_frozen_input
from .identity_proposal import (
    PublicIdentityPayload,
    SourceConfig,
    freeze_natural_identity_slice,
    validate_natural_identity_slice,
)
from .identity_proposal_opaque import validate_opaque_identity_slice
from .io import (
    canonical_json_bytes,
    load_json,
    sha256_file,
    write_json_immutable,
    write_text_immutable,
)


DEV_DATASET_ID = "natural-identity-membership-dev-repair-v3"
V2_DATASET_ID = "natural-identity-membership-opaque-v2"
FORMAL_V1_SOURCE_PATH = Path(
    "artifacts/identity-memory-experiment/natural-v1/source-cases.json"
)
FORMAL_V2_SOURCE_PATH = Path(
    "artifacts/identity-memory-experiment/natural-v2/source-cases.json"
)
DEV_CASE_COUNT = 6
FINAL_CASE_COUNT = 12
SLICE_FILES = (
    "source-cases.json",
    "public.json",
    "authority.json",
    "gold.json",
    "manifest.json",
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class IdentityProposerPolicyFreeze(StrictModel):
    schema_version: Literal["natural-identity-proposer-policy-freeze-v1"] = (
        "natural-identity-proposer-policy-freeze-v1"
    )
    status: Literal["frozen"] = "frozen"
    policy_path: str = Field(min_length=1)
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dev_public_path: str = Field(min_length=1)
    dev_public_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    final_public_path: str = Field(min_length=1)
    dev_prompt_path: str = Field(min_length=1)
    dev_prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    final_prompt_path: str = Field(min_length=1)
    final_prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dev_run_id: str = Field(min_length=1)
    final_run_id: str = Field(min_length=1)
    proposer_id: str = Field(min_length=1)
    proposer_version: str = Field(min_length=1)
    dev_dataset_id: str = Field(default=DEV_DATASET_ID, min_length=1)
    dev_case_count: int = Field(default=DEV_CASE_COUNT, ge=1)
    final_case_count: int = Field(default=FINAL_CASE_COUNT, ge=1)
    fresh_hidden_authored_before_policy_freeze: Literal[False] = False


def _require_read_only(path: Path, label: str) -> None:
    """Verify a committed input portably.

    Content-based rather than mode-based: git records only the executable bit, so
    a 0444 input arrives as 0644 and a mode precondition rejects correct files on
    every fresh clone. Mode is retained only for freshly written output -- see
    ``frozen_input_guard``.
    """
    require_frozen_input(path, label)


def _resolve(path: Path, workspace_root: Path) -> Path:
    return path.resolve() if path.is_absolute() else (workspace_root / path).resolve()


def _validate_frozen_v2_source(
    v2_source_path: Path,
    *,
    workspace_root: Path,
) -> None:
    _require_read_only(v2_source_path, "dev repair v2 source")
    formal_v1_source = _resolve(FORMAL_V1_SOURCE_PATH, workspace_root)
    formal_v2_source = _resolve(FORMAL_V2_SOURCE_PATH, workspace_root)
    validate_opaque_identity_slice(
        formal_v1_source,
        formal_v2_source.parent,
        workspace_root=workspace_root,
    )
    if sha256_file(v2_source_path) != sha256_file(formal_v2_source):
        raise ValueError("dev repair source must match frozen opaque v2 source")


def prepare_identity_dev_slice(
    v2_source_path: Path,
    output_root: Path,
    *,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    workspace_root = (workspace_root or Path.cwd()).resolve()
    v2_source_path = (
        v2_source_path.resolve()
        if v2_source_path.is_absolute()
        else (workspace_root / v2_source_path).resolve()
    )
    output_root = output_root.resolve()
    _validate_frozen_v2_source(v2_source_path, workspace_root=workspace_root)
    source = SourceConfig.model_validate(load_json(v2_source_path))
    if source.dataset_id != V2_DATASET_ID:
        raise ValueError("dev repair source must be opaque v2")
    dev_cases = [case for case in source.cases if case.split == "dev"]
    if len(dev_cases) != DEV_CASE_COUNT:
        raise ValueError("dev repair source must contain exactly six dev cases")
    payload = source.model_dump(mode="json", exclude_unset=True)
    payload["dataset_id"] = DEV_DATASET_ID
    payload["cases"] = [case.model_dump(mode="json", exclude_unset=True) for case in dev_cases]

    write_json_immutable(output_root / "source-cases.json", payload)
    freeze_natural_identity_slice(
        output_root / "source-cases.json",
        output_root,
        workspace_root=workspace_root,
    )
    result = validate_natural_identity_slice(output_root, workspace_root=workspace_root)
    manifest = load_json(output_root / "manifest.json")
    if manifest.get("source_config_sha256") != sha256_file(
        output_root / "source-cases.json"
    ):
        raise ValueError("dev repair source config hash mismatch")
    if result["case_count"] != DEV_CASE_COUNT or result["hidden_count"] != 0:
        raise ValueError("dev repair slice composition mismatch")
    for name in SLICE_FILES:
        (output_root / name).chmod(0o444)
    return validate_natural_identity_slice(output_root, workspace_root=workspace_root)


def _render_prompt(
    policy_text: str,
    *,
    policy_sha256: str,
    public_path: Path,
    run_id: str,
    proposer_id: str,
    proposer_version: str,
    case_count: int,
) -> str:
    staged_path = (
        Path.cwd()
        / ".tmp"
        / "identity-proposer-stage"
        / run_id
        / "proposals.json"
    ).resolve()
    return f"""# Natural Identity Proposal-Only Contract

You are a fresh proposer with no inherited conversation history.

## Allowed input

Read exactly this dataset file and no other workspace file:

`{public_path}`

Do not read or inspect directories, source cases, mappings, preregistration, authority, gold, prior model runs, scorer code, scorer outputs, reports, plans, or documentation. The restriction is part of the experiment.

## Frozen decision policy

Policy SHA-256: `{policy_sha256}`

{policy_text.rstrip()}

## Output

Write proposal JSON to:

`{staged_path}`

Use this exact run metadata:

- `schema_version`: `natural-identity-proposals-v1`
- `run_id`: `{run_id}`
- `proposer_id`: `{proposer_id}`
- `proposer_version`: `{proposer_version}`
- `dataset_id`: copy exactly from public input
- `case_count`: `{case_count}`

The top-level object contains `schema_version`, `dataset_id`, `run_id`, `proposer_id`, `proposer_version`, `case_count`, and `proposals`.

Each proposal contains exactly `case_id`, `relation_kind`, `action`, `confidence`, `evidence_mention_ids`, `reason_code`, `proposer_id`, `proposer_version`, and `run_id`. For identity, action is `merge`, `keep_distinct`, or `abstain`. For membership, action is `include`, `exclude`, or `abstain`. Evidence IDs must belong to the same public case. Produce exactly one proposal per public case with no duplicates or omissions.

Use only public semantic evidence. Do not infer meaning from opaque IDs or the dev/hidden split. Before finishing, parse the output and verify schema, metadata, coverage, action families, confidence bounds, and evidence IDs. Do not include commentary or Markdown in the JSON file.
"""


def freeze_identity_proposer_policy(
    policy_path: Path,
    dev_prompt_path: Path,
    final_prompt_path: Path,
    output_path: Path,
    *,
    dev_public_path: Path,
    final_public_path: Path,
    dev_run_id: str,
    final_run_id: str,
    proposer_id: str,
    proposer_version: str,
    dev_dataset_id: str = DEV_DATASET_ID,
    dev_case_count: int = DEV_CASE_COUNT,
    final_case_count: int = FINAL_CASE_COUNT,
) -> dict[str, Any]:
    policy_path = policy_path.resolve()
    dev_prompt_path = dev_prompt_path.resolve()
    final_prompt_path = final_prompt_path.resolve()
    output_path = output_path.resolve()
    dev_public_path = dev_public_path.resolve()
    final_public_path = final_public_path.resolve()
    _require_read_only(policy_path, "policy")
    _require_read_only(dev_public_path, "dev public input")
    dev_public = PublicIdentityPayload.model_validate(load_json(dev_public_path))
    if (
        dev_public.dataset_id != dev_dataset_id
        or dev_public.case_count != dev_case_count
    ):
        raise ValueError("dev public input composition mismatch")
    if any(case.split != "dev" for case in dev_public.cases):
        raise ValueError("dev public input contains non-dev case")

    policy_text = policy_path.read_text(encoding="utf-8")
    if not policy_text.strip():
        raise ValueError("policy must not be empty")
    policy_hash = sha256_file(policy_path)
    dev_prompt = _render_prompt(
        policy_text,
        policy_sha256=policy_hash,
        public_path=dev_public_path,
        run_id=dev_run_id,
        proposer_id=proposer_id,
        proposer_version=proposer_version,
        case_count=dev_case_count,
    )
    final_prompt = _render_prompt(
        policy_text,
        policy_sha256=policy_hash,
        public_path=final_public_path,
        run_id=final_run_id,
        proposer_id=proposer_id,
        proposer_version=proposer_version,
        case_count=final_case_count,
    )
    write_text_immutable(dev_prompt_path, dev_prompt)
    write_text_immutable(final_prompt_path, final_prompt)
    dev_prompt_path.chmod(0o444)
    final_prompt_path.chmod(0o444)

    frozen = IdentityProposerPolicyFreeze(
        policy_path=str(policy_path),
        policy_sha256=policy_hash,
        dev_public_path=str(dev_public_path),
        dev_public_sha256=sha256_file(dev_public_path),
        final_public_path=str(final_public_path),
        dev_prompt_path=str(dev_prompt_path),
        dev_prompt_sha256=sha256_file(dev_prompt_path),
        final_prompt_path=str(final_prompt_path),
        final_prompt_sha256=sha256_file(final_prompt_path),
        dev_run_id=dev_run_id,
        final_run_id=final_run_id,
        proposer_id=proposer_id,
        proposer_version=proposer_version,
        dev_dataset_id=dev_dataset_id,
        dev_case_count=dev_case_count,
        final_case_count=final_case_count,
    )
    write_json_immutable(output_path, frozen)
    output_path.chmod(0o444)
    return frozen.model_dump(mode="json")
