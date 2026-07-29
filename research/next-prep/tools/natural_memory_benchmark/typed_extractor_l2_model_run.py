from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .io import load_json, sha256_file, write_json_immutable
from .typed_extractor_l2 import L2ProposalPayload, L2PublicPayload


IsolationContext = Literal["fresh-agent-no-history-declarative"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class L2ModelDispatch(StrictModel):
    schema_version: Literal["typed-extractor-l2-model-dispatch-v2"] = (
        "typed-extractor-l2-model-dispatch-v2"
    )
    status: Literal["frozen"] = "frozen"
    dataset_id: str = Field(min_length=1)
    case_count: int = Field(ge=1)
    run_id: str = Field(min_length=1)
    proposer_id: str = Field(min_length=1)
    proposer_version: str = Field(min_length=1)
    requested_model: str = Field(min_length=1)
    isolation_context: IsolationContext
    isolation_enforcement: Literal["declarative-agent-file-access-contract"] = (
        "declarative-agent-file-access-contract"
    )
    history_context_inherited: Literal[False] = False
    authority_or_gold_allowed: Literal[False] = False
    allowed_files: dict[str, str]
    allowed_input_sha256: dict[str, str]


class L2ModelProvenance(StrictModel):
    schema_version: Literal["typed-extractor-l2-model-provenance-v2"] = (
        "typed-extractor-l2-model-provenance-v2"
    )
    status: Literal["frozen"] = "frozen"
    dataset_id: str = Field(min_length=1)
    case_count: int = Field(ge=1)
    run_id: str = Field(min_length=1)
    proposer_id: str = Field(min_length=1)
    proposer_version: str = Field(min_length=1)
    requested_model: str = Field(min_length=1)
    response_model: str = Field(min_length=1)
    isolation_context: IsolationContext
    isolation_enforcement: Literal["declarative-agent-file-access-contract"] = (
        "declarative-agent-file-access-contract"
    )
    history_context_inherited: Literal[False] = False
    authority_or_gold_read_before_freeze: Literal[False] = False
    allowed_files: dict[str, str]
    allowed_input_sha256: dict[str, str]
    dispatch_filename: str = Field(pattern=r"^[^/\\]+$")
    dispatch_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_response_filename: str = Field(pattern=r"^[^/\\]+$")
    raw_response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposals_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_source_verified: Literal[True] = True
    freeze_sequence: tuple[
        Literal["dispatch"],
        Literal["raw_response"],
        Literal["proposals"],
        Literal["provenance"],
    ] = ("dispatch", "raw_response", "proposals", "provenance")


def _require_read_only(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{label} missing: {path}")
    if path.stat().st_mode & 0o222:
        raise ValueError(f"{label} must be read-only")


def write_l2_model_dispatch(
    public_path: Path,
    prompt_path: Path,
    dispatch_path: Path,
    *,
    run_id: str,
    proposer_id: str,
    proposer_version: str,
    requested_model: str,
    isolation_context: IsolationContext,
) -> dict[str, Any]:
    public_path = public_path.resolve()
    prompt_path = prompt_path.resolve()
    dispatch_path = dispatch_path.resolve()
    _require_read_only(public_path, "public input")
    _require_read_only(prompt_path, "prompt")
    public = L2PublicPayload.model_validate(load_json(public_path))
    dispatch = L2ModelDispatch(
        dataset_id=public.dataset_id,
        case_count=public.case_count,
        run_id=run_id,
        proposer_id=proposer_id,
        proposer_version=proposer_version,
        requested_model=requested_model,
        isolation_context=isolation_context,
        allowed_files={
            "proposer-prompt-l2.md": str(prompt_path),
            "public-l2.json": str(public_path),
        },
        allowed_input_sha256={
            "proposer-prompt-l2.md": sha256_file(prompt_path),
            "public-l2.json": sha256_file(public_path),
        },
    )
    write_json_immutable(dispatch_path, dispatch)
    dispatch_path.chmod(0o444)
    return dispatch.model_dump(mode="json")


def _validate_dispatch(
    dispatch: L2ModelDispatch,
    *,
    public_path: Path,
    prompt_path: Path,
    isolation_context: IsolationContext,
) -> None:
    if dispatch.isolation_context != isolation_context:
        raise ValueError("isolation context mismatch")
    expected_files = {
        "proposer-prompt-l2.md": str(prompt_path),
        "public-l2.json": str(public_path),
    }
    if dispatch.allowed_files != expected_files:
        raise ValueError("dispatch allowed files mismatch")
    expected_hashes = {
        "proposer-prompt-l2.md": sha256_file(prompt_path),
        "public-l2.json": sha256_file(public_path),
    }
    if dispatch.allowed_input_sha256 != expected_hashes:
        raise ValueError("dispatch allowed input hash mismatch")


def extract_l2_proposal_payload(
    response_payload: dict[str, Any],
) -> L2ProposalPayload:
    choices = response_payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("API response has no choices")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ValueError("API response has no assistant message")
    value = message.get("content")
    if not isinstance(value, str) or not value.strip():
        value = message.get("reasoning_content")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("assistant message has no JSON content")
    value = value.strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        value = "\n".join(lines).strip()
    return L2ProposalPayload.model_validate_json(value)


def _validate_proposals(
    public: L2PublicPayload,
    proposals: L2ProposalPayload,
    dispatch: L2ModelDispatch,
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
    public_by_id = {item.case_id: item for item in public.cases}
    proposal_by_id = {item.case_id: item for item in proposals.proposals}
    if set(public_by_id) != set(proposal_by_id):
        raise ValueError("proposal case coverage mismatch")
    for case_id, proposal in proposal_by_id.items():
        case = public_by_id[case_id]
        if proposal.candidate_ref != case.candidate_ref:
            raise ValueError(f"proposal candidate ref mismatch: {case_id}")
        typed = proposal.typed_candidate
        if typed is None:
            continue
        operator_sense_bindings = public.allowed_vocabulary.get(
            "operator_sense_bindings"
        )
        if operator_sense_bindings is not None:
            allowed_pairs = set(operator_sense_bindings)
            for claim in typed.structured_claims:
                pair = (
                    f"{claim.predicate.canonical_operator}|"
                    f"{claim.predicate.sense}"
                )
                if pair not in allowed_pairs:
                    raise ValueError(
                        f"proposal operator/sense pair is not public: {case_id}"
                    )
        if (
            typed.structured_claims[0].predicate.surface
            != case.untyped_candidate.predicate
        ):
            raise ValueError(f"proposal does not copy public predicate surface: {case_id}")
        support_refs = [item.support_ref for item in case.typed_l1_support_pack]
        if typed.supporting_l1_refs != support_refs:
            raise ValueError(f"proposal support refs mismatch: {case_id}")
        turn_refs = [item.source_turn_ref for item in case.source_turns]
        if typed.source_turn_refs != turn_refs:
            raise ValueError(f"proposal source turn refs mismatch: {case_id}")
        if typed.source_session_refs != [case.source_session_ref]:
            raise ValueError(f"proposal source session refs mismatch: {case_id}")
        public_evidence = sorted(
            (
                binding.evidence_id,
                binding.speaker,
            )
            for support in case.typed_l1_support_pack
            for binding in support.evidence_bindings
        )
        proposal_evidence = sorted(
            (binding.evidence_id, binding.speaker)
            for binding in typed.evidence_bindings
        )
        if proposal_evidence != public_evidence:
            raise ValueError(f"proposal evidence coverage mismatch: {case_id}")


def freeze_l2_model_proposals(
    public_path: Path,
    staged_proposals_path: Path,
    output_path: Path,
    provenance_path: Path,
    *,
    prompt_path: Path,
    dispatch_path: Path,
    raw_response_path: Path,
    isolation_context: IsolationContext,
) -> dict[str, Any]:
    public_path = public_path.resolve()
    staged_proposals_path = staged_proposals_path.resolve()
    output_path = output_path.resolve()
    provenance_path = provenance_path.resolve()
    prompt_path = prompt_path.resolve()
    dispatch_path = dispatch_path.resolve()
    raw_response_path = raw_response_path.resolve()
    _require_read_only(public_path, "public input")
    _require_read_only(prompt_path, "prompt")
    _require_read_only(dispatch_path, "dispatch")
    _require_read_only(raw_response_path, "raw response")
    artifact_root = provenance_path.parent
    if any(
        path.parent != artifact_root
        for path in (dispatch_path, raw_response_path, output_path)
    ):
        raise ValueError("dispatch, raw response, proposals, and provenance must be siblings")
    public = L2PublicPayload.model_validate(load_json(public_path))
    dispatch = L2ModelDispatch.model_validate(load_json(dispatch_path))
    _validate_dispatch(
        dispatch,
        public_path=public_path,
        prompt_path=prompt_path,
        isolation_context=isolation_context,
    )
    proposals = L2ProposalPayload.model_validate(load_json(staged_proposals_path))
    response_payload = load_json(raw_response_path)
    response_model = response_payload.get("model")
    if not isinstance(response_model, str) or not response_model.strip():
        raise ValueError("raw response does not identify the response model")
    raw_proposals = extract_l2_proposal_payload(response_payload)
    if raw_proposals != proposals:
        raise ValueError("staged proposals do not match raw response")
    _validate_proposals(public, proposals, dispatch)
    write_json_immutable(output_path, proposals)
    provenance = L2ModelProvenance(
        dataset_id=public.dataset_id,
        case_count=public.case_count,
        run_id=proposals.run_id,
        proposer_id=proposals.proposer_id,
        proposer_version=proposals.proposer_version,
        requested_model=dispatch.requested_model,
        response_model=response_model,
        isolation_context=isolation_context,
        allowed_files=dispatch.allowed_files,
        allowed_input_sha256=dispatch.allowed_input_sha256,
        dispatch_filename=dispatch_path.name,
        dispatch_sha256=sha256_file(dispatch_path),
        raw_response_filename=raw_response_path.name,
        raw_response_sha256=sha256_file(raw_response_path),
        proposals_sha256=sha256_file(output_path),
        proposal_source_verified=True,
    )
    write_json_immutable(provenance_path, provenance)
    output_path.chmod(0o444)
    provenance_path.chmod(0o444)
    return provenance.model_dump(mode="json")
