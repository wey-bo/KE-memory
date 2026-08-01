from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .frozen_input_guard import require_frozen_input
from .identity_proposal import IdentityProposalPayload, PublicIdentityPayload
from .io import load_json, sha256_file, write_json_immutable


IsolationContext = Literal["fresh-agent-no-history-declarative"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class IdentityModelDispatch(StrictModel):
    schema_version: Literal["natural-identity-model-dispatch-v1"] = (
        "natural-identity-model-dispatch-v1"
    )
    status: Literal["frozen"] = "frozen"
    dataset_id: str = Field(min_length=1)
    case_count: int = Field(ge=1)
    run_id: str = Field(min_length=1)
    proposer_id: str = Field(min_length=1)
    proposer_version: str = Field(min_length=1)
    isolation_context: IsolationContext
    isolation_enforcement: Literal["declarative-agent-file-access-contract"] = (
        "declarative-agent-file-access-contract"
    )
    history_context_inherited: Literal[False] = False
    authority_or_gold_allowed: Literal[False] = False
    allowed_files: dict[str, str]
    allowed_input_sha256: dict[str, str]


class IdentityModelProvenance(StrictModel):
    schema_version: Literal["natural-identity-model-provenance-v1"] = (
        "natural-identity-model-provenance-v1"
    )
    status: Literal["frozen"] = "frozen"
    dataset_id: str = Field(min_length=1)
    case_count: int = Field(ge=1)
    run_id: str = Field(min_length=1)
    proposer_id: str = Field(min_length=1)
    proposer_version: str = Field(min_length=1)
    isolation_context: IsolationContext
    isolation_enforcement: Literal["declarative-agent-file-access-contract"] = (
        "declarative-agent-file-access-contract"
    )
    history_context_inherited: Literal[False] = False
    authority_or_gold_read_before_freeze: Literal[False] = False
    allowed_files: dict[str, str]
    allowed_input_sha256: dict[str, str]
    dispatch_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposals_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def _require_read_only(path: Path, label: str) -> None:
    """Verify a committed input portably.

    Content-based rather than mode-based: git records only the executable bit, so
    a 0444 input arrives as 0644 and a mode precondition rejects correct files on
    every fresh clone. Mode is retained only for freshly written output -- see
    ``frozen_input_guard``.
    """
    require_frozen_input(path, label)


def write_identity_model_dispatch(
    public_path: Path,
    prompt_path: Path,
    dispatch_path: Path,
    *,
    run_id: str,
    proposer_id: str,
    proposer_version: str,
    isolation_context: IsolationContext,
) -> dict[str, Any]:
    public_path = public_path.resolve()
    prompt_path = prompt_path.resolve()
    dispatch_path = dispatch_path.resolve()
    _require_read_only(public_path, "public input")
    _require_read_only(prompt_path, "prompt")
    public = PublicIdentityPayload.model_validate(load_json(public_path))
    dispatch = IdentityModelDispatch(
        dataset_id=public.dataset_id,
        case_count=public.case_count,
        run_id=run_id,
        proposer_id=proposer_id,
        proposer_version=proposer_version,
        isolation_context=isolation_context,
        allowed_files={
            "proposer-prompt.md": str(prompt_path),
            "public.json": str(public_path),
        },
        allowed_input_sha256={
            "proposer-prompt.md": sha256_file(prompt_path),
            "public.json": sha256_file(public_path),
        },
    )
    write_json_immutable(dispatch_path, dispatch)
    dispatch_path.chmod(0o444)
    return dispatch.model_dump(mode="json")


def _validate_dispatch_inputs(
    dispatch: IdentityModelDispatch,
    *,
    public_path: Path,
    prompt_path: Path,
    isolation_context: IsolationContext,
) -> None:
    if dispatch.isolation_context != isolation_context:
        raise ValueError("isolation context mismatch")
    expected_files = {
        "proposer-prompt.md": str(prompt_path),
        "public.json": str(public_path),
    }
    if dispatch.allowed_files != expected_files:
        raise ValueError("dispatch allowed files mismatch")
    public_hash = sha256_file(public_path)
    prompt_hash = sha256_file(prompt_path)
    if dispatch.allowed_input_sha256.get("public.json") != public_hash:
        raise ValueError("public input hash mismatch")
    if dispatch.allowed_input_sha256.get("proposer-prompt.md") != prompt_hash:
        raise ValueError("prompt hash mismatch")
    if set(dispatch.allowed_input_sha256) != {"public.json", "proposer-prompt.md"}:
        raise ValueError("dispatch allowed input hashes mismatch")


def _validate_proposals_against_public(
    public: PublicIdentityPayload,
    proposals: IdentityProposalPayload,
    dispatch: IdentityModelDispatch,
) -> None:
    if proposals.dataset_id != public.dataset_id or dispatch.dataset_id != public.dataset_id:
        raise ValueError("proposal dataset mismatch")
    if proposals.case_count != public.case_count or dispatch.case_count != public.case_count:
        raise ValueError("proposal case count mismatch")
    if (
        proposals.run_id != dispatch.run_id
        or proposals.proposer_id != dispatch.proposer_id
        or proposals.proposer_version != dispatch.proposer_version
    ):
        raise ValueError("proposal metadata does not match dispatch")

    public_by_id = {case.case_id: case for case in public.cases}
    proposal_by_id = {proposal.case_id: proposal for proposal in proposals.proposals}
    if set(proposal_by_id) != set(public_by_id):
        raise ValueError("proposal case coverage mismatch")
    for case_id, proposal in proposal_by_id.items():
        case = public_by_id[case_id]
        if proposal.relation_kind != case.relation_kind:
            raise ValueError(f"proposal relation kind mismatch: {case_id}")
        allowed_evidence = {mention.mention_id for mention in case.mentions}
        unknown = set(proposal.evidence_mention_ids) - allowed_evidence
        if unknown:
            raise ValueError(
                f"unknown evidence mention id for {case_id}: {sorted(unknown)[0]}"
            )


def freeze_identity_model_proposals(
    public_path: Path,
    staged_proposals_path: Path,
    output_path: Path,
    provenance_path: Path,
    *,
    prompt_path: Path,
    dispatch_path: Path,
    isolation_context: IsolationContext,
) -> dict[str, Any]:
    public_path = public_path.resolve()
    staged_proposals_path = staged_proposals_path.resolve()
    output_path = output_path.resolve()
    provenance_path = provenance_path.resolve()
    prompt_path = prompt_path.resolve()
    dispatch_path = dispatch_path.resolve()
    _require_read_only(public_path, "public input")
    _require_read_only(prompt_path, "prompt")
    _require_read_only(dispatch_path, "dispatch")

    public = PublicIdentityPayload.model_validate(load_json(public_path))
    dispatch = IdentityModelDispatch.model_validate(load_json(dispatch_path))
    _validate_dispatch_inputs(
        dispatch,
        public_path=public_path,
        prompt_path=prompt_path,
        isolation_context=isolation_context,
    )
    proposals = IdentityProposalPayload.model_validate(load_json(staged_proposals_path))
    _validate_proposals_against_public(public, proposals, dispatch)

    write_json_immutable(output_path, proposals)
    provenance = IdentityModelProvenance(
        dataset_id=public.dataset_id,
        case_count=public.case_count,
        run_id=proposals.run_id,
        proposer_id=proposals.proposer_id,
        proposer_version=proposals.proposer_version,
        isolation_context=isolation_context,
        allowed_files=dispatch.allowed_files,
        allowed_input_sha256=dispatch.allowed_input_sha256,
        dispatch_sha256=sha256_file(dispatch_path),
        proposals_sha256=sha256_file(output_path),
    )
    write_json_immutable(provenance_path, provenance)
    output_path.chmod(0o444)
    provenance_path.chmod(0o444)
    return provenance.model_dump(mode="json")
