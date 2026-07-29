from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationError,
    model_validator,
)

from .io import (
    canonical_json_bytes,
    load_json,
)
from .query_compiler_v2 import QueryDraftV1
from .query_compiler_v2_assessment import (
    QueryCompilerAuthorityDocumentV1,
    QueryCompilerGateScoreV1,
    QueryCompilerGoldDocumentV1,
    QueryCompilerProposalDocumentV1,
    QueryCompilerProposalV1,
    QueryCompilerPublicDocumentV1,
    QueryCompilerVerificationV1,
    compile_query_proposals,
    score_query_compiler_batch,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


class QueryDraftRawProposalV1(StrictModel):
    schema_version: Literal["query-draft-raw-proposal-v1"] = (
        "query-draft-raw-proposal-v1"
    )
    case_id: str = Field(pattern=r"^qc-[0-9a-f]{16}$")
    parse_status: Literal["json", "missing", "invalid_json", "transport_error"]
    raw_payload: JsonValue | None = None
    raw_response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    errors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_status(self) -> "QueryDraftRawProposalV1":
        if self.errors != sorted(set(self.errors)):
            raise ValueError("proposal envelope errors must be sorted and unique")
        if self.parse_status == "json" and self.errors:
            raise ValueError("parsed JSON proposal cannot carry envelope errors")
        if self.parse_status != "json" and self.raw_payload is not None:
            raise ValueError("non-JSON proposal cannot carry a parsed payload")
        if self.parse_status != "json" and not self.errors:
            raise ValueError("non-JSON proposal requires an envelope error")
        return self


class QueryDraftProposalDocumentV1(StrictModel):
    schema_version: Literal["query-draft-proposals-v1"] = (
        "query-draft-proposals-v1"
    )
    dataset_id: str = Field(min_length=1)
    proposals: list[QueryDraftRawProposalV1] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_case_ids(self) -> "QueryDraftProposalDocumentV1":
        case_ids = [item.case_id for item in self.proposals]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("duplicate proposal case id")
        return self


class QueryDraftProposalProvenanceV1(StrictModel):
    schema_version: Literal["query-draft-proposal-provenance-v1"] = (
        "query-draft-proposal-provenance-v1"
    )
    dataset_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    requested_model: str = Field(min_length=1)
    response_model: str = Field(min_length=1)
    public_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dispatch_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposals_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    semantic_run_count: Literal[1] = 1
    history_context_inherited: Literal[False] = False
    authority_or_gold_read_before_freeze: Literal[False] = False
    proposals_frozen_before_scoring: Literal[True] = True
    isolation_enforcement: Literal["declarative_file_access_contract"] = (
        "declarative_file_access_contract"
    )


_RUN_ARTIFACT_NAMES = (
    "public.json",
    "proposer-prompt.md",
    "dispatch.json",
    "raw-response.json",
    "proposals.json",
    "provenance.json",
    "validation-receipt.json",
    "typed-proposals.json",
)
_FORBIDDEN_CREDENTIAL_KEY_SUFFIXES = (
    "apikey",
    "authorization",
    "password",
    "passwd",
    "clientsecret",
    "accesstoken",
    "refreshtoken",
    "sessiontoken",
    "idtoken",
    "authtoken",
    "secretaccesskey",
    "privatekey",
    "cookie",
    "credential",
    "credentials",
)
_SCOPED_CREDENTIAL_KEYS = {
    "apitoken",
    "githubtoken",
    "gitlabtoken",
    "openaitoken",
    "anthropictoken",
    "huggingfacetoken",
    "hftoken",
    "oauthtoken",
    "bearertoken",
    "authheader",
    "clientsecretvalue",
}
_FORBIDDEN_CREDENTIAL_PATTERNS = (
    re.compile(r"(?i)\bbearer\s+(?P<secret>[a-z0-9._~+/=${}<>*-]{12,})"),
    re.compile(r"\bsk-(?P<secret>[A-Za-z0-9_-]{16,})"),
    re.compile(
        r"\b(?:hf_|ghp_|github_pat_)(?P<secret>[A-Za-z0-9_-]{16,})"
    ),
)
_CREDENTIAL_PLACEHOLDER = re.compile(
    r"(?i)^(?:"
    r"YOUR_[A-Z0-9_]+|"
    r"REDACTED|"
    r"PLACEHOLDER(?:_[A-Z0-9_]+)?|"
    r"EXAMPLE(?:_[A-Z0-9_]+)?|"
    r"DUMMY(?:_[A-Z0-9_]+)?|"
    r"<TOKEN>|"
    r"\$\{[A-Z0-9_]+\}"
    r")$"
)


class QueryDraftProposalArtifactManifestV1(StrictModel):
    schema_version: Literal["query-draft-proposal-artifact-manifest-v1"] = (
        "query-draft-proposal-artifact-manifest-v1"
    )
    dataset_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    requested_model: str = Field(min_length=1)
    response_model: str = Field(min_length=1)
    isolation_enforcement: Literal["declarative_file_access_contract"] = (
        "declarative_file_access_contract"
    )
    artifact_sha256: dict[str, str]

    @model_validator(mode="after")
    def validate_artifacts(self) -> "QueryDraftProposalArtifactManifestV1":
        if set(self.artifact_sha256) != set(_RUN_ARTIFACT_NAMES):
            raise ValueError("artifact manifest file set mismatch")
        if any(
            re.fullmatch(r"[0-9a-f]{64}", value) is None
            for value in self.artifact_sha256.values()
        ):
            raise ValueError("artifact manifest contains invalid sha256")
        return self


def _validate_relative_path(value: str, field_name: str) -> None:
    normalized = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or normalized.is_absolute()
        or ".." in normalized.parts
        or str(normalized) != value
    ):
        raise ValueError(f"{field_name} must be a normalized relative path")
    if value.startswith(":") or any(char in value for char in "*?["):
        raise ValueError(f"{field_name} cannot contain Git pathspec magic")


class QueryDraftProposalPreregistrationV1(StrictModel):
    schema_version: Literal["query-draft-proposal-preregistration-v1"] = (
        "query-draft-proposal-preregistration-v1"
    )
    dataset_id: str = Field(min_length=1)
    prompt_path: str = Field(min_length=1)
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    compiler_path: str = Field(min_length=1)
    compiler_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    assessment_path: str = Field(min_length=1)
    assessment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposer_eval_path: str = Field(min_length=1)
    proposer_eval_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_paths(self) -> "QueryDraftProposalPreregistrationV1":
        paths = [
            self.prompt_path,
            self.compiler_path,
            self.assessment_path,
            self.proposer_eval_path,
        ]
        if len(paths) != len(set(paths)):
            raise ValueError("preregistration paths must be unique")
        for path in paths:
            _validate_relative_path(path, "preregistration path")
        return self


class QueryDraftProposalFormalFreezeV1(StrictModel):
    schema_version: Literal["query-draft-proposal-formal-freeze-v1"] = (
        "query-draft-proposal-formal-freeze-v1"
    )
    dataset_id: str = Field(min_length=1)
    preregistration_commit: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    public_commit: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    raw_commit: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    typed_commit: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    authority_gold_commit: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    preregistration_path: str = Field(min_length=1)
    public_path: str = Field(min_length=1)
    dispatch_path: str = Field(min_length=1)
    raw_response_path: str = Field(min_length=1)
    proposals_path: str = Field(min_length=1)
    provenance_path: str = Field(min_length=1)
    validation_receipt_path: str = Field(min_length=1)
    typed_proposals_path: str = Field(min_length=1)
    authority_path: str = Field(min_length=1)
    draft_gold_path: str = Field(min_length=1)
    compiler_gold_path: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_contract(self) -> "QueryDraftProposalFormalFreezeV1":
        commits = [
            self.preregistration_commit,
            self.public_commit,
            self.raw_commit,
            self.typed_commit,
            self.authority_gold_commit,
        ]
        if len(commits) != len(set(commits)):
            raise ValueError("formal freeze commits must be unique")
        paths = [
            self.preregistration_path,
            self.public_path,
            self.dispatch_path,
            self.raw_response_path,
            self.proposals_path,
            self.provenance_path,
            self.validation_receipt_path,
            self.typed_proposals_path,
            self.authority_path,
            self.draft_gold_path,
            self.compiler_gold_path,
        ]
        if len(paths) != len(set(paths)):
            raise ValueError("formal freeze paths must be unique")
        for path in paths:
            _validate_relative_path(path, "formal freeze path")
        return self

    def model_copy(
        self,
        *,
        update: dict[str, object] | None = None,
        deep: bool = False,
    ) -> "QueryDraftProposalFormalFreezeV1":
        payload = self.model_dump(mode="python")
        if update:
            payload.update(update)
        return type(self).model_validate(payload)


class QueryDraftGoldCaseV1(StrictModel):
    schema_version: Literal["query-draft-gold-case-v1"] = (
        "query-draft-gold-case-v1"
    )
    case_id: str = Field(pattern=r"^qc-[0-9a-f]{16}$")
    expected_draft: QueryDraftV1
    critical: bool = False


class QueryDraftGoldDocumentV1(StrictModel):
    schema_version: Literal["query-draft-gold-v1"] = "query-draft-gold-v1"
    dataset_id: str = Field(min_length=1)
    cases: list[QueryDraftGoldCaseV1] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_case_ids(self) -> "QueryDraftGoldDocumentV1":
        case_ids = [item.case_id for item in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("duplicate draft gold case id")
        return self


class QueryDraftProposalMetricsV1(StrictModel):
    case_count: int = Field(ge=1)
    case_coverage: float = Field(ge=0.0, le=1.0)
    schema_valid_rate: float = Field(ge=0.0, le=1.0)
    query_id_accuracy: float = Field(ge=0.0, le=1.0)
    intent_accuracy: float = Field(ge=0.0, le=1.0)
    target_level_accuracy: float = Field(ge=0.0, le=1.0)
    answer_accuracy: float = Field(ge=0.0, le=1.0)
    pattern_accuracy: float = Field(ge=0.0, le=1.0)
    time_accuracy: float = Field(ge=0.0, le=1.0)
    lifecycle_accuracy: float = Field(ge=0.0, le=1.0)
    source_accuracy: float = Field(ge=0.0, le=1.0)
    conflict_supersession_accuracy: float = Field(ge=0.0, le=1.0)
    evidence_policy_accuracy: float = Field(ge=0.0, le=1.0)
    explicit_absence_accuracy: float = Field(ge=0.0, le=1.0)
    draft_template_exact: float = Field(ge=0.0, le=1.0)
    draft_semantic_exact: float = Field(ge=0.0, le=1.0)
    missing_output_count: int = Field(ge=0)
    invalid_json_count: int = Field(ge=0)
    transport_error_count: int = Field(ge=0)
    schema_invalid_output_count: int = Field(ge=0)
    critical_invalid_output_count: int = Field(ge=0)


def _derive_raw_proposer_quality(metrics: QueryDraftProposalMetricsV1) -> bool:
    exact_rates = [
        metrics.case_coverage,
        metrics.schema_valid_rate,
        metrics.query_id_accuracy,
        metrics.intent_accuracy,
        metrics.target_level_accuracy,
        metrics.answer_accuracy,
        metrics.pattern_accuracy,
        metrics.time_accuracy,
        metrics.lifecycle_accuracy,
        metrics.source_accuracy,
        metrics.conflict_supersession_accuracy,
        metrics.evidence_policy_accuracy,
        metrics.explicit_absence_accuracy,
        metrics.draft_semantic_exact,
    ]
    return (
        all(value == 1.0 for value in exact_rates)
        and metrics.missing_output_count == 0
        and metrics.invalid_json_count == 0
        and metrics.transport_error_count == 0
        and metrics.schema_invalid_output_count == 0
        and metrics.critical_invalid_output_count == 0
    )


class QueryDraftProposalScoreV1(StrictModel):
    schema_version: Literal["query-draft-proposal-score-v1"] = (
        "query-draft-proposal-score-v1"
    )
    dataset_id: str = Field(min_length=1)
    metrics: QueryDraftProposalMetricsV1
    validation_errors: dict[str, list[str]] = Field(default_factory=dict)
    raw_proposer_quality_ready: bool

    @model_validator(mode="after")
    def validate_readiness(self) -> "QueryDraftProposalScoreV1":
        expected = _derive_raw_proposer_quality(self.metrics)
        if self.raw_proposer_quality_ready != expected:
            raise ValueError(
                "raw_proposer_quality_ready does not match typed metrics"
            )
        invalid_output_count = (
            self.metrics.missing_output_count
            + self.metrics.invalid_json_count
            + self.metrics.transport_error_count
            + self.metrics.schema_invalid_output_count
        )
        if len(self.validation_errors) != invalid_output_count:
            raise ValueError("validation error count mismatch")
        for errors in self.validation_errors.values():
            if errors != sorted(set(errors)):
                raise ValueError("validation errors must be sorted and unique")
        return self

    def model_copy(
        self,
        *,
        update: dict[str, object] | None = None,
        deep: bool = False,
    ) -> "QueryDraftProposalScoreV1":
        payload = self.model_dump(mode="python")
        if update:
            payload.update(update)
        return type(self).model_validate(payload)


class QueryDraftValidationEntryV1(StrictModel):
    schema_version: Literal["query-draft-validation-entry-v1"] = (
        "query-draft-validation-entry-v1"
    )
    case_id: str = Field(pattern=r"^qc-[0-9a-f]{16}$")
    raw_envelope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation_status: Literal[
        "valid",
        "missing",
        "invalid_json",
        "transport_error",
        "schema_invalid",
    ]
    validation_errors: list[str] = Field(default_factory=list)
    typed_draft_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )

    @model_validator(mode="after")
    def validate_binding(self) -> "QueryDraftValidationEntryV1":
        if self.validation_errors != sorted(set(self.validation_errors)):
            raise ValueError("validation errors must be sorted and unique")
        if self.validation_status == "valid":
            if self.validation_errors:
                raise ValueError("valid draft cannot carry validation errors")
            if self.typed_draft_sha256 is None:
                raise ValueError("valid draft requires typed_draft_sha256")
        elif self.typed_draft_sha256 is not None:
            raise ValueError("invalid draft cannot carry typed_draft_sha256")
        elif not self.validation_errors:
            raise ValueError("invalid draft requires validation errors")
        return self


class QueryDraftValidationDocumentV1(StrictModel):
    schema_version: Literal["query-draft-validation-v1"] = (
        "query-draft-validation-v1"
    )
    dataset_id: str = Field(min_length=1)
    raw_proposals_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    entries: list[QueryDraftValidationEntryV1] = Field(min_length=1)
    all_drafts_valid: bool
    typed_proposals_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )

    @model_validator(mode="after")
    def validate_binding(self) -> "QueryDraftValidationDocumentV1":
        case_ids = [item.case_id for item in self.entries]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("duplicate validation case id")
        expected_all_valid = all(
            item.validation_status == "valid" for item in self.entries
        )
        if self.all_drafts_valid != expected_all_valid:
            raise ValueError("all_drafts_valid does not match validation entries")
        if self.all_drafts_valid != (self.typed_proposals_sha256 is not None):
            raise ValueError("typed_proposals_sha256 does not match validation status")
        return self

    def model_copy(
        self,
        *,
        update: dict[str, object] | None = None,
        deep: bool = False,
    ) -> "QueryDraftValidationDocumentV1":
        payload = self.model_dump(mode="python")
        if update:
            payload.update(update)
        return type(self).model_validate(payload)


class QueryDraftProposalEvaluationV1(StrictModel):
    schema_version: Literal["query-draft-proposal-evaluation-v1"] = (
        "query-draft-proposal-evaluation-v1"
    )
    dataset_id: str = Field(min_length=1)
    raw_score: QueryDraftProposalScoreV1
    validation_receipt: QueryDraftValidationDocumentV1
    gate_evaluated: bool
    gate_score: QueryCompilerGateScoreV1 | None = None
    combined_dev_ready: bool

    @model_validator(mode="after")
    def validate_readiness(self) -> "QueryDraftProposalEvaluationV1":
        nested_dataset_ids = [
            self.raw_score.dataset_id,
            self.validation_receipt.dataset_id,
        ]
        if self.gate_score is not None:
            nested_dataset_ids.append(self.gate_score.dataset_id)
        if any(value != self.dataset_id for value in nested_dataset_ids):
            raise ValueError("evaluation dataset_id mismatch")
        if self.gate_evaluated != self.validation_receipt.all_drafts_valid:
            raise ValueError("gate_evaluated does not match validation receipt")
        if self.gate_evaluated != (self.gate_score is not None):
            raise ValueError("gate_score does not match gate_evaluated")
        expected = (
            self.raw_score.raw_proposer_quality_ready
            and self.gate_evaluated
            and self.gate_score is not None
            and self.gate_score.gate_safety_ready
            and self.gate_score.compilation_utility_ready
        )
        if self.combined_dev_ready != expected:
            raise ValueError("combined_dev_ready does not match nested readiness")
        return self

    def model_copy(
        self,
        *,
        update: dict[str, object] | None = None,
        deep: bool = False,
    ) -> "QueryDraftProposalEvaluationV1":
        payload = self.model_dump(mode="python")
        if update:
            payload.update(update)
        return type(self).model_validate(payload)


def validate_public_proposal_boundary(
    public: QueryCompilerPublicDocumentV1,
    proposals: QueryDraftProposalDocumentV1,
) -> None:
    if public.dataset_id != proposals.dataset_id:
        raise ValueError("public/proposal dataset_id mismatch")
    public_ids = {item.case_id for item in public.cases}
    proposal_ids = {item.case_id for item in proposals.proposals}
    if public_ids != proposal_ids:
        raise ValueError("public/proposal case coverage mismatch")


def validate_proposal_provenance(
    *,
    public: QueryCompilerPublicDocumentV1,
    proposals: QueryDraftProposalDocumentV1,
    provenance: QueryDraftProposalProvenanceV1,
    prompt_bytes: bytes,
    dispatch: object,
    raw_response: object,
) -> None:
    validate_public_proposal_boundary(public, proposals)
    if provenance.dataset_id != public.dataset_id:
        raise ValueError("proposal provenance dataset_id mismatch")
    expected = {
        "public_sha256": _sha256(public),
        "prompt_sha256": hashlib.sha256(prompt_bytes).hexdigest(),
        "dispatch_sha256": _sha256(dispatch),
        "raw_response_sha256": _sha256(raw_response),
        "proposals_sha256": _sha256(proposals),
    }
    actual = {key: getattr(provenance, key) for key in expected}
    if actual != expected:
        raise ValueError("proposal provenance hash mismatch")
    requested_model = _transport_model_id(dispatch, "dispatch")
    response_model = _transport_model_id(raw_response, "raw response")
    if provenance.requested_model != requested_model:
        raise ValueError("requested_model does not match dispatch model")
    if provenance.response_model != response_model:
        raise ValueError("response_model does not match raw response model")
    if any(
        proposal.raw_response_sha256 != provenance.raw_response_sha256
        for proposal in proposals.proposals
    ):
        raise ValueError("envelope raw-response hash mismatch")


def _transport_model_id(value: object, label: str) -> str:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object with a model field")
    model = value.get("model")
    if not isinstance(model, str) or not model.strip():
        raise ValueError(f"{label} must contain a non-empty model field")
    nested_models = _nested_model_ids(
        {key: item for key, item in value.items() if key != "model"},
        label=label,
    )
    if any(nested_model != model for nested_model in nested_models):
        raise ValueError(f"{label} contains a conflicting nested model field")
    return model


def _nested_model_ids(value: object, *, label: str) -> list[str]:
    models: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
            if normalized == "model":
                if not isinstance(item, str) or not item.strip():
                    raise ValueError(
                        f"{label} contains an invalid nested model field"
                    )
                models.append(item)
            models.extend(_nested_model_ids(item, label=label))
    elif isinstance(value, (list, tuple)):
        for item in value:
            models.extend(_nested_model_ids(item, label=label))
    return models


def _is_forbidden_credential_key(normalized: str, value: object) -> bool:
    if any(
        normalized.endswith(suffix)
        for suffix in _FORBIDDEN_CREDENTIAL_KEY_SUFFIXES
    ):
        return True
    if normalized not in _SCOPED_CREDENTIAL_KEYS:
        return False
    if not isinstance(value, (str, bytes)):
        return False
    text = (
        value.decode("utf-8", errors="replace")
        if isinstance(value, bytes)
        else value
    )
    stripped = text.strip()
    return len(stripped) >= 8 and not _is_credential_placeholder(stripped)


def _is_credential_placeholder(value: str) -> bool:
    stripped = value.strip()
    if _CREDENTIAL_PLACEHOLDER.fullmatch(stripped) is not None:
        return True
    scheme_and_value = stripped.split(maxsplit=1)
    if len(scheme_and_value) != 2:
        return False
    scheme, candidate = scheme_and_value
    return (
        scheme.casefold() in {"bearer", "basic"}
        and _CREDENTIAL_PLACEHOLDER.fullmatch(candidate) is not None
    )


def _credential_hits(value: object, *, path: str) -> list[str]:
    hits: list[str] = []
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
            item_path = f"{path}.{key}"
            if _is_forbidden_credential_key(normalized, item):
                hits.append(item_path)
            hits.extend(_credential_hits(item, path=item_path))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            hits.extend(_credential_hits(item, path=f"{path}[{index}]"))
    elif isinstance(value, (str, bytes)):
        text = value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value
        for pattern in _FORBIDDEN_CREDENTIAL_PATTERNS:
            for match in pattern.finditer(text):
                if not _is_credential_placeholder(match.group("secret")):
                    hits.append(path)
                    return hits
    return hits


def _require_no_credentials(values: dict[str, object]) -> None:
    hits: list[str] = []
    for label, value in values.items():
        hits.extend(_credential_hits(value, path=label))
    if hits:
        raise ValueError(
            "forbidden credential material: " + ", ".join(sorted(set(hits)))
        )


def _run_artifact_values(
    *,
    public: QueryCompilerPublicDocumentV1,
    prompt_bytes: bytes,
    dispatch: object,
    raw_response: object,
    proposals: QueryDraftProposalDocumentV1,
    provenance: QueryDraftProposalProvenanceV1,
    validation_receipt: QueryDraftValidationDocumentV1,
    typed_proposals: QueryCompilerProposalDocumentV1,
) -> dict[str, object]:
    return {
        "public.json": public,
        "proposer-prompt.md": prompt_bytes,
        "dispatch.json": dispatch,
        "raw-response.json": raw_response,
        "proposals.json": proposals,
        "provenance.json": provenance,
        "validation-receipt.json": validation_receipt,
        "typed-proposals.json": typed_proposals,
    }


def _artifact_bytes(name: str, value: object) -> bytes:
    if name == "proposer-prompt.md":
        if not isinstance(value, bytes):
            raise TypeError("prompt artifact must be bytes")
        return value
    return canonical_json_bytes(value)


def _revalidate_model(value: BaseModel) -> BaseModel:
    payload = value.model_dump(mode="python", round_trip=True)
    return type(value).model_validate(payload)


def _write_run_bundle_immutable(
    root: Path,
    bundle_bytes: dict[str, bytes],
) -> None:
    expected_names = set(bundle_bytes)
    if root.exists():
        if not root.is_dir() or root.is_symlink():
            raise FileExistsError(f"immutable artifact root differs: {root}")
        actual_names = {entry.name for entry in root.iterdir()}
        if actual_names != expected_names:
            raise FileExistsError(f"immutable artifact set differs: {root}")
        for name, expected in bundle_bytes.items():
            path = root / name
            if path.is_symlink() or not path.is_file():
                raise FileExistsError(f"immutable artifact type differs: {path}")
            if path.read_bytes() != expected:
                raise FileExistsError(f"immutable artifact differs: {path}")
            os.chmod(path, 0o444)
        return

    root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{root.name}.freeze-", dir=root.parent)
    )
    try:
        for name, content in bundle_bytes.items():
            path = staging / name
            path.write_bytes(content)
            os.chmod(path, 0o444)
        staging.rename(root)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def freeze_query_draft_proposal_run(
    *,
    root: Path,
    public: QueryCompilerPublicDocumentV1,
    prompt_bytes: bytes,
    dispatch: object,
    raw_response: object,
    proposals: QueryDraftProposalDocumentV1,
    provenance: QueryDraftProposalProvenanceV1,
    validation_receipt: QueryDraftValidationDocumentV1,
    typed_proposals: QueryCompilerProposalDocumentV1,
) -> QueryDraftProposalArtifactManifestV1:
    public = QueryCompilerPublicDocumentV1.model_validate(
        _revalidate_model(public).model_dump(mode="python")
    )
    proposals = QueryDraftProposalDocumentV1.model_validate(
        _revalidate_model(proposals).model_dump(mode="python")
    )
    provenance = QueryDraftProposalProvenanceV1.model_validate(
        _revalidate_model(provenance).model_dump(mode="python")
    )
    validation_receipt = QueryDraftValidationDocumentV1.model_validate(
        _revalidate_model(validation_receipt).model_dump(mode="python")
    )
    typed_proposals = QueryCompilerProposalDocumentV1.model_validate(
        _revalidate_model(typed_proposals).model_dump(mode="python")
    )
    prompt_bytes.decode("utf-8")
    values = _run_artifact_values(
        public=public,
        prompt_bytes=prompt_bytes,
        dispatch=dispatch,
        raw_response=raw_response,
        proposals=proposals,
        provenance=provenance,
        validation_receipt=validation_receipt,
        typed_proposals=typed_proposals,
    )
    _require_no_credentials(values)
    validate_proposal_provenance(
        public=public,
        proposals=proposals,
        provenance=provenance,
        prompt_bytes=prompt_bytes,
        dispatch=dispatch,
        raw_response=raw_response,
    )
    validate_typed_proposal_materialization(
        proposals,
        validation_receipt,
        typed_proposals,
    )
    artifact_sha256 = {
        name: hashlib.sha256(_artifact_bytes(name, value)).hexdigest()
        for name, value in values.items()
    }
    manifest = QueryDraftProposalArtifactManifestV1(
        dataset_id=public.dataset_id,
        run_id=provenance.run_id,
        requested_model=provenance.requested_model,
        response_model=provenance.response_model,
        isolation_enforcement=provenance.isolation_enforcement,
        artifact_sha256=artifact_sha256,
    )
    bundle_bytes = {
        name: _artifact_bytes(name, value)
        for name, value in values.items()
    }
    bundle_bytes["artifact-manifest.json"] = canonical_json_bytes(manifest)
    _write_run_bundle_immutable(root, bundle_bytes)
    return manifest


def validate_frozen_query_draft_proposal_run(
    root: Path,
) -> QueryDraftProposalArtifactManifestV1:
    expected_names = {*_RUN_ARTIFACT_NAMES, "artifact-manifest.json"}
    if not root.is_dir() or root.is_symlink():
        raise ValueError("run artifact root must be a real directory")
    entries = list(root.iterdir())
    if {entry.name for entry in entries} != expected_names:
        raise ValueError("run artifact set mismatch")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise ValueError("run artifact type mismatch")
    manifest_path = root / "artifact-manifest.json"
    manifest_payload = load_json(manifest_path)
    manifest = QueryDraftProposalArtifactManifestV1.model_validate(manifest_payload)
    if manifest_path.read_bytes() != canonical_json_bytes(manifest):
        raise ValueError("artifact manifest is not canonical JSON")

    prompt_bytes = (root / "proposer-prompt.md").read_bytes()
    values: dict[str, object] = {
        "public.json": QueryCompilerPublicDocumentV1.model_validate(
            load_json(root / "public.json")
        ),
        "proposer-prompt.md": prompt_bytes,
        "dispatch.json": load_json(root / "dispatch.json"),
        "raw-response.json": load_json(root / "raw-response.json"),
        "proposals.json": QueryDraftProposalDocumentV1.model_validate(
            load_json(root / "proposals.json")
        ),
        "provenance.json": QueryDraftProposalProvenanceV1.model_validate(
            load_json(root / "provenance.json")
        ),
        "validation-receipt.json": QueryDraftValidationDocumentV1.model_validate(
            load_json(root / "validation-receipt.json")
        ),
        "typed-proposals.json": QueryCompilerProposalDocumentV1.model_validate(
            load_json(root / "typed-proposals.json")
        ),
    }
    _require_no_credentials(values)
    for name, value in values.items():
        path = root / name
        expected_bytes = _artifact_bytes(name, value)
        if path.read_bytes() != expected_bytes:
            raise ValueError(f"non-canonical or changed artifact bytes: {name}")
        if hashlib.sha256(expected_bytes).hexdigest() != manifest.artifact_sha256[name]:
            raise ValueError(f"artifact hash mismatch: {name}")
        if path.stat().st_mode & 0o222:
            raise ValueError(f"artifact is writable: {name}")
    if manifest_path.stat().st_mode & 0o222:
        raise ValueError("artifact manifest is writable")

    public = values["public.json"]
    proposals = values["proposals.json"]
    provenance = values["provenance.json"]
    receipt = values["validation-receipt.json"]
    typed = values["typed-proposals.json"]
    assert isinstance(public, QueryCompilerPublicDocumentV1)
    assert isinstance(proposals, QueryDraftProposalDocumentV1)
    assert isinstance(provenance, QueryDraftProposalProvenanceV1)
    assert isinstance(receipt, QueryDraftValidationDocumentV1)
    assert isinstance(typed, QueryCompilerProposalDocumentV1)
    validate_proposal_provenance(
        public=public,
        proposals=proposals,
        provenance=provenance,
        prompt_bytes=prompt_bytes,
        dispatch=values["dispatch.json"],
        raw_response=values["raw-response.json"],
    )
    validate_typed_proposal_materialization(proposals, receipt, typed)
    if (
        manifest.dataset_id != public.dataset_id
        or manifest.run_id != provenance.run_id
        or manifest.requested_model != provenance.requested_model
        or manifest.response_model != provenance.response_model
        or manifest.isolation_enforcement != provenance.isolation_enforcement
    ):
        raise ValueError("artifact manifest provenance mismatch")
    return manifest


def _run_git(
    repo_path: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    completed = subprocess.run(
        [
            "git",
            "-C",
            os.fspath(repo_path),
            "--literal-pathspecs",
            *args,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(detail or f"git {' '.join(args)} failed")
    return completed


def _git_bytes(repo_path: Path, commit: str, path: str) -> bytes:
    return _run_git(repo_path, "show", f"{commit}:{path}").stdout


def _git_has_path(repo_path: Path, commit: str, path: str) -> bool:
    return (
        _run_git(
            repo_path,
            "cat-file",
            "-e",
            f"{commit}:{path}",
            check=False,
        ).returncode
        == 0
    )


def _git_is_ancestor(repo_path: Path, ancestor: str, descendant: str) -> bool:
    return (
        _run_git(
            repo_path,
            "merge-base",
            "--is-ancestor",
            ancestor,
            descendant,
            check=False,
        ).returncode
        == 0
    )


def _git_path_changed_after(
    repo_path: Path,
    frozen_commit: str,
    final_commit: str,
    path: str,
) -> bool:
    commits = _run_git(
        repo_path,
        "rev-list",
        "--full-history",
        "--ancestry-path",
        f"{frozen_commit}..{final_commit}",
        "--",
        path,
    ).stdout
    return bool(commits.strip())


def _git_json(repo_path: Path, commit: str, path: str) -> tuple[bytes, object]:
    value = _git_bytes(repo_path, commit, path)
    payload = json.loads(value.decode("utf-8"))
    if value != canonical_json_bytes(payload):
        raise ValueError(f"frozen artifact is not canonical JSON: {path}")
    return value, payload


def verify_query_draft_proposal_history(
    *,
    repo_path: Path,
    freeze: QueryDraftProposalFormalFreezeV1,
) -> QueryCompilerVerificationV1:
    errors: list[str] = []
    commits = [
        freeze.preregistration_commit,
        freeze.public_commit,
        freeze.raw_commit,
        freeze.typed_commit,
        freeze.authority_gold_commit,
    ]
    try:
        for commit in commits:
            _run_git(repo_path, "cat-file", "-e", f"{commit}^{{commit}}")
        for earlier, later in zip(commits, commits[1:]):
            if not _git_is_ancestor(repo_path, earlier, later):
                errors.append("formal freeze commits are not in chronological order")

        prereg_bytes, prereg_payload = _git_json(
            repo_path,
            freeze.preregistration_commit,
            freeze.preregistration_path,
        )
        del prereg_bytes
        preregistration = QueryDraftProposalPreregistrationV1.model_validate(
            prereg_payload
        )
        if preregistration.dataset_id != freeze.dataset_id:
            errors.append("preregistration dataset_id mismatch")

        future_paths = [
            freeze.public_path,
            freeze.dispatch_path,
            freeze.raw_response_path,
            freeze.proposals_path,
            freeze.provenance_path,
            freeze.validation_receipt_path,
            freeze.typed_proposals_path,
            freeze.authority_path,
            freeze.draft_gold_path,
            freeze.compiler_gold_path,
        ]
        for path in future_paths:
            if _git_has_path(repo_path, freeze.preregistration_commit, path):
                errors.append(f"future artifact existed at preregistration: {path}")
        for path in future_paths[1:]:
            if _git_has_path(repo_path, freeze.public_commit, path):
                errors.append(f"post-public artifact existed too early: {path}")
        for path in [
            freeze.typed_proposals_path,
            freeze.authority_path,
            freeze.draft_gold_path,
            freeze.compiler_gold_path,
        ]:
            if _git_has_path(repo_path, freeze.raw_commit, path):
                errors.append(f"post-raw artifact existed too early: {path}")
        for path in [
            freeze.authority_path,
            freeze.draft_gold_path,
            freeze.compiler_gold_path,
        ]:
            if _git_has_path(repo_path, freeze.typed_commit, path):
                errors.append(f"authority or gold existed before typed freeze: {path}")

        frozen_code = [
            (
                preregistration.compiler_path,
                preregistration.compiler_sha256,
                "compiler",
            ),
            (
                preregistration.assessment_path,
                preregistration.assessment_sha256,
                "assessment",
            ),
            (
                preregistration.proposer_eval_path,
                preregistration.proposer_eval_sha256,
                "proposer evaluator",
            ),
        ]
        for path, expected_hash, label in frozen_code:
            prereg_content = _git_bytes(
                repo_path,
                freeze.preregistration_commit,
                path,
            )
            if hashlib.sha256(prereg_content).hexdigest() != expected_hash:
                errors.append(f"frozen {label} hash mismatch")
            if (
                prereg_content
                != _git_bytes(repo_path, freeze.authority_gold_commit, path)
                or _git_path_changed_after(
                    repo_path,
                    freeze.preregistration_commit,
                    freeze.authority_gold_commit,
                    path,
                )
            ):
                errors.append(f"{label} bytes changed after preregistration")
        prompt_bytes = _git_bytes(
            repo_path,
            freeze.preregistration_commit,
            preregistration.prompt_path,
        )
        if hashlib.sha256(prompt_bytes).hexdigest() != preregistration.prompt_sha256:
            errors.append("frozen prompt hash mismatch")
        if (
            prompt_bytes
            != _git_bytes(
                repo_path,
                freeze.authority_gold_commit,
                preregistration.prompt_path,
            )
            or _git_path_changed_after(
                repo_path,
                freeze.preregistration_commit,
                freeze.authority_gold_commit,
                preregistration.prompt_path,
            )
        ):
            errors.append("prompt bytes changed after preregistration")

        frozen_stages = [
            (
                freeze.public_commit,
                freeze.public_path,
                "public bytes changed after public freeze",
            ),
            (
                freeze.raw_commit,
                freeze.dispatch_path,
                "dispatch bytes changed after raw freeze",
            ),
            (
                freeze.raw_commit,
                freeze.raw_response_path,
                "raw response bytes changed after raw freeze",
            ),
            (
                freeze.raw_commit,
                freeze.proposals_path,
                "proposal bytes changed after raw freeze",
            ),
            (
                freeze.raw_commit,
                freeze.provenance_path,
                "provenance bytes changed after raw freeze",
            ),
            (
                freeze.raw_commit,
                freeze.validation_receipt_path,
                "validation receipt bytes changed after raw freeze",
            ),
            (
                freeze.typed_commit,
                freeze.typed_proposals_path,
                "typed proposal bytes changed after typed freeze",
            ),
        ]
        for commit, path, message in frozen_stages:
            if (
                _git_bytes(repo_path, commit, path)
                != _git_bytes(repo_path, freeze.authority_gold_commit, path)
                or _git_path_changed_after(
                    repo_path,
                    commit,
                    freeze.authority_gold_commit,
                    path,
                )
            ):
                errors.append(message)

        _, public_payload = _git_json(
            repo_path,
            freeze.public_commit,
            freeze.public_path,
        )
        _, dispatch = _git_json(
            repo_path,
            freeze.raw_commit,
            freeze.dispatch_path,
        )
        _, raw_response = _git_json(
            repo_path,
            freeze.raw_commit,
            freeze.raw_response_path,
        )
        _, proposals_payload = _git_json(
            repo_path,
            freeze.raw_commit,
            freeze.proposals_path,
        )
        _, provenance_payload = _git_json(
            repo_path,
            freeze.raw_commit,
            freeze.provenance_path,
        )
        _, receipt_payload = _git_json(
            repo_path,
            freeze.raw_commit,
            freeze.validation_receipt_path,
        )
        _, typed_payload = _git_json(
            repo_path,
            freeze.typed_commit,
            freeze.typed_proposals_path,
        )
        _, authority_payload = _git_json(
            repo_path,
            freeze.authority_gold_commit,
            freeze.authority_path,
        )
        _, draft_gold_payload = _git_json(
            repo_path,
            freeze.authority_gold_commit,
            freeze.draft_gold_path,
        )
        _, compiler_gold_payload = _git_json(
            repo_path,
            freeze.authority_gold_commit,
            freeze.compiler_gold_path,
        )
        public = QueryCompilerPublicDocumentV1.model_validate(public_payload)
        proposals = QueryDraftProposalDocumentV1.model_validate(proposals_payload)
        provenance = QueryDraftProposalProvenanceV1.model_validate(provenance_payload)
        receipt = QueryDraftValidationDocumentV1.model_validate(receipt_payload)
        typed = QueryCompilerProposalDocumentV1.model_validate(typed_payload)
        authority = QueryCompilerAuthorityDocumentV1.model_validate(authority_payload)
        draft_gold = QueryDraftGoldDocumentV1.model_validate(draft_gold_payload)
        compiler_gold = QueryCompilerGoldDocumentV1.model_validate(
            compiler_gold_payload
        )
        documents = [
            public,
            proposals,
            provenance,
            receipt,
            typed,
            authority,
            draft_gold,
            compiler_gold,
        ]
        if any(document.dataset_id != freeze.dataset_id for document in documents):
            errors.append("frozen proposal document dataset_id mismatch")
        _require_no_credentials(
            {
                "prompt": prompt_bytes,
                "public": public,
                "dispatch": dispatch,
                "raw_response": raw_response,
                "proposals": proposals,
                "provenance": provenance,
                "validation_receipt": receipt,
                "typed_proposals": typed,
            }
        )
        validate_proposal_provenance(
            public=public,
            proposals=proposals,
            provenance=provenance,
            prompt_bytes=prompt_bytes,
            dispatch=dispatch,
            raw_response=raw_response,
        )
        validate_typed_proposal_materialization(proposals, receipt, typed)
    except Exception as exc:
        errors.append(f"proposal history verification failed: {exc}")
    errors = list(dict.fromkeys(errors))
    return QueryCompilerVerificationV1(verified=not errors, errors=errors)


def materialize_typed_query_proposals(
    public: QueryCompilerPublicDocumentV1,
    proposals: QueryDraftProposalDocumentV1,
) -> tuple[QueryDraftValidationDocumentV1, QueryCompilerProposalDocumentV1 | None]:
    validate_public_proposal_boundary(public, proposals)
    return _materialize_typed_query_proposals(proposals)


def _materialize_typed_query_proposals(
    proposals: QueryDraftProposalDocumentV1,
) -> tuple[QueryDraftValidationDocumentV1, QueryCompilerProposalDocumentV1 | None]:
    entries: list[QueryDraftValidationEntryV1] = []
    typed_proposals: list[QueryCompilerProposalV1] = []
    for raw in proposals.proposals:
        raw_hash = _sha256(raw)
        if raw.parse_status != "json":
            entries.append(
                QueryDraftValidationEntryV1(
                    case_id=raw.case_id,
                    raw_envelope_sha256=raw_hash,
                    validation_status=raw.parse_status,
                    validation_errors=list(raw.errors),
                )
            )
            continue
        try:
            draft = QueryDraftV1.model_validate(raw.raw_payload)
        except ValidationError as exc:
            entries.append(
                QueryDraftValidationEntryV1(
                    case_id=raw.case_id,
                    raw_envelope_sha256=raw_hash,
                    validation_status="schema_invalid",
                    validation_errors=_validation_errors(exc),
                )
            )
            continue
        entries.append(
            QueryDraftValidationEntryV1(
                case_id=raw.case_id,
                raw_envelope_sha256=raw_hash,
                validation_status="valid",
                typed_draft_sha256=_sha256(draft),
            )
        )
        typed_proposals.append(
            QueryCompilerProposalV1(case_id=raw.case_id, draft=draft)
        )

    all_valid = len(typed_proposals) == len(proposals.proposals)
    typed = None
    if all_valid:
        typed = QueryCompilerProposalDocumentV1(
            dataset_id=proposals.dataset_id,
            proposals=typed_proposals,
        )
    receipt = QueryDraftValidationDocumentV1(
        dataset_id=proposals.dataset_id,
        raw_proposals_sha256=_sha256(proposals),
        entries=entries,
        all_drafts_valid=all_valid,
        typed_proposals_sha256=None if typed is None else _sha256(typed),
    )
    return receipt, typed


def validate_typed_proposal_materialization(
    proposals: QueryDraftProposalDocumentV1,
    receipt: QueryDraftValidationDocumentV1,
    typed: QueryCompilerProposalDocumentV1 | None,
) -> None:
    rebuilt_receipt, rebuilt_typed = _materialize_typed_query_proposals(proposals)
    if receipt != rebuilt_receipt or typed != rebuilt_typed:
        raise ValueError("typed proposal materialization mismatch")


def evaluate_query_draft_proposals(
    *,
    public: QueryCompilerPublicDocumentV1,
    authority: QueryCompilerAuthorityDocumentV1,
    proposals: QueryDraftProposalDocumentV1,
    draft_gold: QueryDraftGoldDocumentV1,
    compiler_gold: QueryCompilerGoldDocumentV1,
) -> QueryDraftProposalEvaluationV1:
    raw_score = score_query_draft_proposals(public, proposals, draft_gold)
    receipt, typed = materialize_typed_query_proposals(public, proposals)
    if typed is None:
        return QueryDraftProposalEvaluationV1(
            dataset_id=public.dataset_id,
            raw_score=raw_score,
            validation_receipt=receipt,
            gate_evaluated=False,
            combined_dev_ready=False,
        )
    batch = compile_query_proposals(public, authority, typed)
    gate_score = score_query_compiler_batch(batch, compiler_gold)
    return QueryDraftProposalEvaluationV1(
        dataset_id=public.dataset_id,
        raw_score=raw_score,
        validation_receipt=receipt,
        gate_evaluated=True,
        gate_score=gate_score,
        combined_dev_ready=(
            raw_score.raw_proposer_quality_ready
            and gate_score.gate_safety_ready
            and gate_score.compilation_utility_ready
        ),
    )


def _rate(numerator: int, denominator: int) -> float:
    return 0.0 if denominator == 0 else numerator / denominator


def _template_projection(draft: QueryDraftV1) -> dict[str, object]:
    return draft.model_dump(
        mode="json",
        exclude={"producer_id", "producer_version"},
    )


def _semantic_projection(draft: QueryDraftV1) -> dict[str, object]:
    payload = _template_projection(draft)
    variable_map: dict[str, str] = {}

    def variable(value: str) -> str:
        if value not in variable_map:
            variable_map[value] = f"?v{len(variable_map)}"
        return variable_map[value]

    answer = payload["answer"]
    if isinstance(answer, dict):
        answer_variable = answer.get("variable")
        if isinstance(answer_variable, str):
            answer["variable"] = variable(answer_variable)
    groups = payload["pattern_groups"]
    if isinstance(groups, list):
        atom_index = 0
        for group_index, group in enumerate(groups):
            if not isinstance(group, dict):
                continue
            group["group_id"] = f"group-{group_index}"
            atoms = group.get("atoms")
            if not isinstance(atoms, list):
                continue
            for atom in atoms:
                if not isinstance(atom, dict):
                    continue
                atom["atom_id"] = f"atom-{atom_index}"
                atom_index += 1
                roles = atom.get("roles")
                if not isinstance(roles, list):
                    continue
                for role in roles:
                    if not isinstance(role, dict):
                        continue
                    term = role.get("term")
                    if not isinstance(term, dict) or term.get("kind") != "variable":
                        continue
                    value = term.get("value")
                    if isinstance(value, str):
                        term["value"] = variable(value)
    return payload


def _validation_errors(error: ValidationError) -> list[str]:
    values = {
        f"{'.'.join(str(part) for part in item['loc'])}:{item['type']}"
        for item in error.errors()
    }
    return sorted(values)


def score_query_draft_proposals(
    public: QueryCompilerPublicDocumentV1,
    proposals: QueryDraftProposalDocumentV1,
    gold: QueryDraftGoldDocumentV1,
) -> QueryDraftProposalScoreV1:
    validate_public_proposal_boundary(public, proposals)
    if public.dataset_id != gold.dataset_id:
        raise ValueError("public/draft gold dataset_id mismatch")
    public_ids = {item.case_id for item in public.cases}
    gold_ids = {item.case_id for item in gold.cases}
    if public_ids != gold_ids:
        raise ValueError("public/draft gold case coverage mismatch")

    public_by_id = {item.case_id: item for item in public.cases}
    proposals_by_id = {item.case_id: item for item in proposals.proposals}
    counters = {
        "schema_valid": 0,
        "query_id": 0,
        "intent": 0,
        "target_level": 0,
        "answer": 0,
        "pattern": 0,
        "time": 0,
        "lifecycle": 0,
        "source": 0,
        "conflict_supersession": 0,
        "evidence_policy": 0,
        "explicit_absence": 0,
        "template": 0,
        "semantic": 0,
    }
    invalid_counts = {
        "missing": 0,
        "invalid_json": 0,
        "transport_error": 0,
        "schema_invalid": 0,
        "critical": 0,
    }
    validation_errors: dict[str, list[str]] = {}

    for gold_case in gold.cases:
        public_case = public_by_id[gold_case.case_id]
        expected = gold_case.expected_draft
        if expected.query_id != public_case.query_id:
            raise ValueError("public/draft gold query_id mismatch")
        raw = proposals_by_id[gold_case.case_id]
        if raw.parse_status != "json":
            invalid_counts[raw.parse_status] += 1
            if gold_case.critical:
                invalid_counts["critical"] += 1
            validation_errors[gold_case.case_id] = list(raw.errors)
            continue
        try:
            actual = QueryDraftV1.model_validate(raw.raw_payload)
        except ValidationError as exc:
            invalid_counts["schema_invalid"] += 1
            if gold_case.critical:
                invalid_counts["critical"] += 1
            validation_errors[gold_case.case_id] = _validation_errors(exc)
            continue

        counters["schema_valid"] += 1
        actual_semantic = _semantic_projection(actual)
        expected_semantic = _semantic_projection(expected)
        counters["query_id"] += actual.query_id == expected.query_id
        counters["intent"] += actual.intent == expected.intent
        counters["target_level"] += actual.target_level == expected.target_level
        counters["answer"] += (
            actual_semantic["answer"] == expected_semantic["answer"]
        )
        counters["pattern"] += (
            actual_semantic["pattern_groups"]
            == expected_semantic["pattern_groups"]
        )
        counters["time"] += actual.time_constraints == expected.time_constraints
        counters["lifecycle"] += actual.lifecycle == expected.lifecycle
        counters["source"] += (
            actual.source_status_constraints == expected.source_status_constraints
        )
        counters["conflict_supersession"] += (
            actual.conflict_policy == expected.conflict_policy
            and actual.supersession_policy == expected.supersession_policy
        )
        counters["evidence_policy"] += (
            actual.evidence_policy == expected.evidence_policy
        )
        counters["explicit_absence"] += (
            actual.explicit_absence_requested == expected.explicit_absence_requested
        )
        counters["template"] += (
            _template_projection(actual) == _template_projection(expected)
        )
        counters["semantic"] += (
            actual_semantic == expected_semantic
        )

    case_count = len(gold.cases)
    metrics = QueryDraftProposalMetricsV1(
        case_count=case_count,
        case_coverage=_rate(len(proposals.proposals), case_count),
        schema_valid_rate=_rate(counters["schema_valid"], case_count),
        query_id_accuracy=_rate(counters["query_id"], case_count),
        intent_accuracy=_rate(counters["intent"], case_count),
        target_level_accuracy=_rate(counters["target_level"], case_count),
        answer_accuracy=_rate(counters["answer"], case_count),
        pattern_accuracy=_rate(counters["pattern"], case_count),
        time_accuracy=_rate(counters["time"], case_count),
        lifecycle_accuracy=_rate(counters["lifecycle"], case_count),
        source_accuracy=_rate(counters["source"], case_count),
        conflict_supersession_accuracy=_rate(
            counters["conflict_supersession"],
            case_count,
        ),
        evidence_policy_accuracy=_rate(counters["evidence_policy"], case_count),
        explicit_absence_accuracy=_rate(
            counters["explicit_absence"],
            case_count,
        ),
        draft_template_exact=_rate(counters["template"], case_count),
        draft_semantic_exact=_rate(counters["semantic"], case_count),
        missing_output_count=invalid_counts["missing"],
        invalid_json_count=invalid_counts["invalid_json"],
        transport_error_count=invalid_counts["transport_error"],
        schema_invalid_output_count=invalid_counts["schema_invalid"],
        critical_invalid_output_count=invalid_counts["critical"],
    )
    return QueryDraftProposalScoreV1(
        dataset_id=public.dataset_id,
        metrics=metrics,
        validation_errors=validation_errors,
        raw_proposer_quality_ready=_derive_raw_proposer_quality(metrics),
    )
