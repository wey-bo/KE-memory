from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from pathlib import PurePosixPath
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .git_memory_history import GitMemoryHistoryRepository
from .io import canonical_json_bytes, load_json, write_json_immutable
from .query_compiler_v2 import (
    CompilerRegistryV1,
    GitMemoryViewRefV1,
    QueryCompilationResultV1,
    QueryContextV1,
    QueryDraftV1,
    compile_query_draft,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


QueryFamily = Literal[
    "atomic_fact_role",
    "entity_predicate_linking",
    "temporal_lifecycle",
    "epistemic_constraint",
    "boolean_and_or",
    "multihop",
    "l2_evidence_closure",
    "identity_aggregate",
]
AssessmentMode = Literal["dev_smoke", "formal_gate"]
FallbackReason = Literal[
    "unresolved_entity",
    "lexical_predicate_missing_link",
]
OPAQUE_CASE_ID_PATTERN = r"^qc-[0-9a-f]{16}$"
OPAQUE_QUERY_ID_PATTERN = r"^qq-[0-9a-f]{16}$"
GIT_OBJECT_ID_PATTERN = r"^[0-9a-f]{40,64}$"


def _sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def memory_view_handle(memory_view: GitMemoryViewRefV1) -> str:
    return f"memory-view-{_sha256(memory_view)[:24]}"


def _unique(values: list[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label}")


def _validate_relative_path(value: str, label: str) -> None:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or value != path.as_posix():
        raise ValueError(f"{label} must be a normalized relative path")


class QueryCompilerPublicCaseV1(StrictModel):
    schema_version: Literal["query-compiler-public-case-v1"] = (
        "query-compiler-public-case-v1"
    )
    case_id: str = Field(pattern=OPAQUE_CASE_ID_PATTERN)
    query_id: str = Field(pattern=OPAQUE_QUERY_ID_PATTERN)
    raw_query: str = Field(min_length=1)
    query_time: str = Field(min_length=1)
    current_user_surface: str | None = None
    memory_view_handle: str = Field(pattern=r"^memory-view-[0-9a-f]{24}$")
    compiler_policy_revision: str = Field(min_length=1)


class QueryCompilerPublicDocumentV1(StrictModel):
    schema_version: Literal["query-compiler-public-v1"] = (
        "query-compiler-public-v1"
    )
    dataset_id: str = Field(min_length=1)
    cases: list[QueryCompilerPublicCaseV1] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_case_ids(self) -> "QueryCompilerPublicDocumentV1":
        _unique([item.case_id for item in self.cases], "public case id")
        _unique([item.query_id for item in self.cases], "public query id")
        return self


class QueryCompilerAuthorityCaseV1(StrictModel):
    schema_version: Literal["query-compiler-authority-case-v1"] = (
        "query-compiler-authority-case-v1"
    )
    case_id: str = Field(min_length=1)
    context: QueryContextV1
    registry: CompilerRegistryV1


class QueryCompilerAuthorityDocumentV1(StrictModel):
    schema_version: Literal["query-compiler-authority-v1"] = (
        "query-compiler-authority-v1"
    )
    dataset_id: str = Field(min_length=1)
    cases: list[QueryCompilerAuthorityCaseV1] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_case_ids(self) -> "QueryCompilerAuthorityDocumentV1":
        _unique([item.case_id for item in self.cases], "authority case id")
        return self


class QueryCompilerProposalV1(StrictModel):
    schema_version: Literal["query-compiler-proposal-v1"] = (
        "query-compiler-proposal-v1"
    )
    case_id: str = Field(min_length=1)
    draft: QueryDraftV1


class QueryCompilerProposalDocumentV1(StrictModel):
    schema_version: Literal["query-compiler-proposals-v1"] = (
        "query-compiler-proposals-v1"
    )
    dataset_id: str = Field(min_length=1)
    proposals: list[QueryCompilerProposalV1] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_case_ids(self) -> "QueryCompilerProposalDocumentV1":
        _unique([item.case_id for item in self.proposals], "proposal case id")
        return self


class QueryCompilerClaimBoundaryV1(StrictModel):
    schema_version: Literal["query-compiler-claim-boundary-v1"] = (
        "query-compiler-claim-boundary-v1"
    )
    gold_read_during_compilation: Literal[False] = False
    raw_proposer_quality_evaluated: Literal[False] = False
    automatic_memory_write_count: Literal[0] = 0
    automatic_identity_write_count: Literal[0] = 0
    automatic_membership_write_count: Literal[0] = 0
    embedding_authority: Literal[False] = False
    natural_language_answer_generated: Literal[False] = False


class QueryCompilerBatchEntryV1(StrictModel):
    schema_version: Literal["query-compiler-batch-entry-v1"] = (
        "query-compiler-batch-entry-v1"
    )
    case_id: str = Field(min_length=1)
    result: QueryCompilationResultV1


class QueryCompilerBatchResultV1(StrictModel):
    schema_version: Literal["query-compiler-batch-result-v1"] = (
        "query-compiler-batch-result-v1"
    )
    dataset_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    input_sha256: dict[str, str]
    entries: list[QueryCompilerBatchEntryV1] = Field(min_length=1)
    claim_boundary: QueryCompilerClaimBoundaryV1 = Field(
        default_factory=QueryCompilerClaimBoundaryV1
    )

    @model_validator(mode="after")
    def validate_entries(self) -> "QueryCompilerBatchResultV1":
        _unique([item.case_id for item in self.entries], "batch result case id")
        if set(self.input_sha256) != {"public", "authority", "proposals"}:
            raise ValueError("batch result input hash keys mismatch")
        if any(
            re.fullmatch(r"[0-9a-f]{64}", value) is None
            for value in self.input_sha256.values()
        ):
            raise ValueError("batch result input hash invalid")
        return self


def _validate_case_boundary(
    public: QueryCompilerPublicCaseV1,
    authority: QueryCompilerAuthorityCaseV1,
    proposal: QueryCompilerProposalV1,
) -> None:
    context = authority.context
    if public.query_id != context.query_id:
        raise ValueError("public/authority query_id mismatch")
    if public.raw_query != context.raw_query:
        raise ValueError("public/authority raw_query mismatch")
    if public.query_time != context.query_time:
        raise ValueError("public/authority query_time mismatch")
    if public.compiler_policy_revision != context.compiler_policy_revision:
        raise ValueError("public/authority compiler policy mismatch")
    if public.memory_view_handle != memory_view_handle(context.memory_view):
        raise ValueError("public/authority memory view mismatch")
    if proposal.draft.query_id != public.query_id:
        raise ValueError("proposal/public query_id mismatch")


def compile_query_proposals(
    public: QueryCompilerPublicDocumentV1,
    authority: QueryCompilerAuthorityDocumentV1,
    proposals: QueryCompilerProposalDocumentV1,
    *,
    run_id: str = "in-memory-query-compiler-run",
) -> QueryCompilerBatchResultV1:
    if len({public.dataset_id, authority.dataset_id, proposals.dataset_id}) != 1:
        raise ValueError("query compiler dataset_id mismatch")
    public_ids = {item.case_id for item in public.cases}
    authority_ids = {item.case_id for item in authority.cases}
    proposal_ids = {item.case_id for item in proposals.proposals}
    if public_ids != authority_ids:
        raise ValueError("public/authority case coverage mismatch")
    if public_ids != proposal_ids:
        raise ValueError("proposal case coverage mismatch")

    authority_by_id = {item.case_id: item for item in authority.cases}
    proposal_by_id = {item.case_id: item for item in proposals.proposals}
    entries: list[QueryCompilerBatchEntryV1] = []
    for public_case in public.cases:
        authority_case = authority_by_id[public_case.case_id]
        proposal = proposal_by_id[public_case.case_id]
        _validate_case_boundary(public_case, authority_case, proposal)
        result = compile_query_draft(
            proposal.draft,
            authority_case.context,
            authority_case.registry,
        )
        entries.append(
            QueryCompilerBatchEntryV1(
                case_id=public_case.case_id,
                result=result,
            )
        )

    return QueryCompilerBatchResultV1(
        dataset_id=public.dataset_id,
        run_id=run_id,
        input_sha256={
            "public": _sha256(public),
            "authority": _sha256(authority),
            "proposals": _sha256(proposals),
        },
        entries=entries,
    )


def run_query_compiler_batch_file(
    *,
    public_path: Path,
    authority_path: Path,
    proposals_path: Path,
    output_path: Path,
    run_id: str,
) -> dict[str, object]:
    public = QueryCompilerPublicDocumentV1.model_validate(load_json(public_path))
    authority = QueryCompilerAuthorityDocumentV1.model_validate(
        load_json(authority_path)
    )
    proposals = QueryCompilerProposalDocumentV1.model_validate(
        load_json(proposals_path)
    )
    result = compile_query_proposals(
        public,
        authority,
        proposals,
        run_id=run_id,
    )
    payload = result.model_dump(mode="json")
    write_json_immutable(output_path, payload)
    output_path.chmod(0o444)
    return payload


class QueryCompilerGoldCaseV1(StrictModel):
    schema_version: Literal["query-compiler-gold-case-v1"] = (
        "query-compiler-gold-case-v1"
    )
    case_id: str = Field(min_length=1)
    family: QueryFamily
    expected_status: Literal["executable", "abstain"]
    expected_plan_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    expected_fallback_allowed: bool
    expected_fallback_reason: FallbackReason | None = None
    expected_unresolved_slots: list[str] = Field(default_factory=list)
    expected_blocked_reasons: list[str] = Field(default_factory=list)
    critical: bool = False

    @model_validator(mode="after")
    def validate_expected_plan(self) -> "QueryCompilerGoldCaseV1":
        if self.expected_status == "executable" and self.expected_plan_sha256 is None:
            raise ValueError("executable gold case requires plan hash")
        if self.expected_status == "abstain" and self.expected_plan_sha256 is not None:
            raise ValueError("abstain gold case cannot require plan hash")
        if self.expected_fallback_allowed and self.expected_fallback_reason is None:
            raise ValueError("allowed fallback gold requires an exact reason")
        if not self.expected_fallback_allowed and self.expected_fallback_reason is not None:
            raise ValueError("blocked fallback gold cannot name an allowed reason")
        for values, label in (
            (self.expected_unresolved_slots, "expected unresolved slots"),
            (self.expected_blocked_reasons, "expected blocked reasons"),
        ):
            if values != sorted(set(values)):
                raise ValueError(f"{label} must be sorted and unique")
        return self


class QueryCompilerGoldDocumentV1(StrictModel):
    schema_version: Literal["query-compiler-gold-v1"] = "query-compiler-gold-v1"
    dataset_id: str = Field(min_length=1)
    cases: list[QueryCompilerGoldCaseV1] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_case_ids(self) -> "QueryCompilerGoldDocumentV1":
        _unique([item.case_id for item in self.cases], "gold case id")
        return self


class QueryCompilerPreregistrationV1(StrictModel):
    schema_version: Literal["query-compiler-preregistration-v1"] = (
        "query-compiler-preregistration-v1"
    )
    dataset_id: str = Field(min_length=1)
    required_families: list[QueryFamily]
    minimum_executable_cases: int = Field(ge=1)
    minimum_critical_cases: int = Field(ge=1)
    compiler_path: str = Field(min_length=1)
    compiler_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    assessment_path: str = Field(min_length=1)
    assessment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_contract(self) -> "QueryCompilerPreregistrationV1":
        if self.required_families != list(get_args(QueryFamily)):
            raise ValueError("required query families must cover the frozen taxonomy")
        _validate_relative_path(self.compiler_path, "compiler_path")
        _validate_relative_path(self.assessment_path, "assessment_path")
        if self.compiler_path == self.assessment_path:
            raise ValueError("compiler and assessment paths must be distinct")
        return self


class QueryCompilerFormalFreezeV1(StrictModel):
    schema_version: Literal["query-compiler-formal-freeze-v1"] = (
        "query-compiler-formal-freeze-v1"
    )
    dataset_id: str = Field(min_length=1)
    preregistration_commit: str = Field(pattern=GIT_OBJECT_ID_PATTERN)
    public_commit: str = Field(pattern=GIT_OBJECT_ID_PATTERN)
    proposals_commit: str = Field(pattern=GIT_OBJECT_ID_PATTERN)
    authority_gold_commit: str = Field(pattern=GIT_OBJECT_ID_PATTERN)
    preregistration_path: str = Field(min_length=1)
    public_path: str = Field(min_length=1)
    proposals_path: str = Field(min_length=1)
    authority_path: str = Field(min_length=1)
    gold_path: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_contract(self) -> "QueryCompilerFormalFreezeV1":
        commits = [
            self.preregistration_commit,
            self.public_commit,
            self.proposals_commit,
            self.authority_gold_commit,
        ]
        _unique(commits, "formal freeze commit")
        paths = [
            self.preregistration_path,
            self.public_path,
            self.proposals_path,
            self.authority_path,
            self.gold_path,
        ]
        _unique(paths, "formal freeze path")
        for path in paths:
            _validate_relative_path(path, "formal freeze path")
        return self


class QueryCompilerVerificationV1(StrictModel):
    schema_version: Literal["query-compiler-verification-v1"] = (
        "query-compiler-verification-v1"
    )
    verified: bool
    errors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_status(self) -> "QueryCompilerVerificationV1":
        if self.verified != (not self.errors):
            raise ValueError("verification status must match errors")
        return self


def _run_git(
    repo_path: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    completed = subprocess.run(
        ["git", "-C", os.fspath(repo_path), *args],
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


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def verify_authoritative_memory_view(
    authority: QueryCompilerAuthorityDocumentV1,
    repo_path: Path,
) -> QueryCompilerVerificationV1:
    errors: list[str] = []
    try:
        repository = GitMemoryHistoryRepository(repo_path)
        report = repository.verify()
        if report.status != "valid":
            errors.extend(f"memory history: {item}" for item in report.errors)
        metadata = repository.read_repository_metadata()
        state = repository.read_state()
        head = repository.head_commit()
        for case in authority.cases:
            view = case.context.memory_view
            if view.workspace_id != metadata.workspace_id:
                errors.append("workspace_id mismatch")
            if view.repository_epoch_id != metadata.repository_epoch_id:
                errors.append("repository_epoch_id mismatch")
            if view.checkpoint_id != state.checkpoint_id:
                errors.append("checkpoint_id mismatch")
            if view.git_commit != head:
                errors.append("git_commit mismatch")
            if view.authoritative_ref != repository.AUTHORITATIVE_REF:
                errors.append("authoritative_ref mismatch")
    except Exception as exc:
        errors.append(f"memory view verification failed: {exc}")
    errors = list(dict.fromkeys(errors))
    return QueryCompilerVerificationV1(verified=not errors, errors=errors)


def verify_formal_preregistration_history(
    *,
    repo_path: Path,
    freeze: QueryCompilerFormalFreezeV1,
    batch: QueryCompilerBatchResultV1,
    gold: QueryCompilerGoldDocumentV1,
) -> QueryCompilerVerificationV1:
    errors: list[str] = []
    commits = [
        freeze.preregistration_commit,
        freeze.public_commit,
        freeze.proposals_commit,
        freeze.authority_gold_commit,
    ]
    try:
        for commit in commits:
            _run_git(repo_path, "cat-file", "-e", f"{commit}^{{commit}}")
        for earlier, later in zip(commits, commits[1:]):
            if not _git_is_ancestor(repo_path, earlier, later):
                errors.append("formal freeze commits are not in chronological order")

        prereg_bytes = _git_bytes(
            repo_path,
            freeze.preregistration_commit,
            freeze.preregistration_path,
        )
        preregistration = QueryCompilerPreregistrationV1.model_validate(
            json.loads(prereg_bytes.decode("utf-8"))
        )
        if preregistration.dataset_id != freeze.dataset_id:
            errors.append("preregistration dataset_id mismatch")
        if batch.dataset_id != freeze.dataset_id or gold.dataset_id != freeze.dataset_id:
            errors.append("formal freeze dataset_id mismatch")

        hidden_paths = [
            freeze.public_path,
            freeze.proposals_path,
            freeze.authority_path,
            freeze.gold_path,
        ]
        for path in hidden_paths:
            if _git_has_path(repo_path, freeze.preregistration_commit, path):
                errors.append(f"hidden artifact existed at preregistration: {path}")
        for path in [
            freeze.proposals_path,
            freeze.authority_path,
            freeze.gold_path,
        ]:
            if _git_has_path(repo_path, freeze.public_commit, path):
                errors.append(f"post-public artifact existed too early: {path}")
        for path in [freeze.authority_path, freeze.gold_path]:
            if _git_has_path(repo_path, freeze.proposals_commit, path):
                errors.append(f"authority or gold existed before proposals froze: {path}")

        compiler_prereg = _git_bytes(
            repo_path,
            freeze.preregistration_commit,
            preregistration.compiler_path,
        )
        assessment_prereg = _git_bytes(
            repo_path,
            freeze.preregistration_commit,
            preregistration.assessment_path,
        )
        if _sha256_bytes(compiler_prereg) != preregistration.compiler_sha256:
            errors.append("frozen compiler hash mismatch")
        if _sha256_bytes(assessment_prereg) != preregistration.assessment_sha256:
            errors.append("frozen assessment hash mismatch")
        if compiler_prereg != _git_bytes(
            repo_path,
            freeze.authority_gold_commit,
            preregistration.compiler_path,
        ):
            errors.append("compiler bytes changed after preregistration")
        if assessment_prereg != _git_bytes(
            repo_path,
            freeze.authority_gold_commit,
            preregistration.assessment_path,
        ):
            errors.append("assessment bytes changed after preregistration")

        public_frozen = _git_bytes(repo_path, freeze.public_commit, freeze.public_path)
        public_final = _git_bytes(
            repo_path,
            freeze.authority_gold_commit,
            freeze.public_path,
        )
        if public_frozen != public_final:
            errors.append("public bytes changed after proposal freeze")
        proposals_frozen = _git_bytes(
            repo_path,
            freeze.proposals_commit,
            freeze.proposals_path,
        )
        proposals_final = _git_bytes(
            repo_path,
            freeze.authority_gold_commit,
            freeze.proposals_path,
        )
        if proposals_frozen != proposals_final:
            errors.append("proposal bytes changed after proposal freeze")

        public = QueryCompilerPublicDocumentV1.model_validate(
            json.loads(public_frozen.decode("utf-8"))
        )
        proposals = QueryCompilerProposalDocumentV1.model_validate(
            json.loads(proposals_frozen.decode("utf-8"))
        )
        authority = QueryCompilerAuthorityDocumentV1.model_validate(
            json.loads(
                _git_bytes(
                    repo_path,
                    freeze.authority_gold_commit,
                    freeze.authority_path,
                ).decode("utf-8")
            )
        )
        frozen_gold = QueryCompilerGoldDocumentV1.model_validate(
            json.loads(
                _git_bytes(
                    repo_path,
                    freeze.authority_gold_commit,
                    freeze.gold_path,
                ).decode("utf-8")
            )
        )
        expected_hashes = {
            "public": _sha256(public),
            "authority": _sha256(authority),
            "proposals": _sha256(proposals),
        }
        if batch.input_sha256 != expected_hashes:
            errors.append("batch input hashes do not match frozen history")
        if frozen_gold != gold:
            errors.append("scored gold does not match frozen history")
    except Exception as exc:
        errors.append(f"formal history verification failed: {exc}")
    errors = list(dict.fromkeys(errors))
    return QueryCompilerVerificationV1(verified=not errors, errors=errors)


class QueryCompilerGateMetricsV1(StrictModel):
    case_count: int = Field(ge=1)
    family_coverage_count: int = Field(ge=0)
    executable_gold_count: int = Field(ge=0)
    critical_gold_count: int = Field(ge=0)
    case_coverage: float = Field(ge=0.0, le=1.0)
    gate_status_accuracy: float = Field(ge=0.0, le=1.0)
    accepted_plan_exact: float = Field(ge=0.0, le=1.0)
    fallback_decision_exact: float = Field(ge=0.0, le=1.0)
    fallback_reason_exact: float = Field(ge=0.0, le=1.0)
    unresolved_slots_exact: float = Field(ge=0.0, le=1.0)
    blocked_reasons_exact: float = Field(ge=0.0, le=1.0)
    false_abstention_count: int = Field(ge=0)
    false_executable_count: int = Field(ge=0)
    unsafe_executable_plan_count: int = Field(ge=0)
    critical_false_executable_count: int = Field(ge=0)
    structural_fallback_count: int = Field(ge=0)


def _derive_gate_safety(metrics: QueryCompilerGateMetricsV1) -> bool:
    return (
        metrics.false_executable_count == 0
        and metrics.unsafe_executable_plan_count == 0
        and metrics.critical_false_executable_count == 0
        and metrics.structural_fallback_count == 0
    )


def _derive_compilation_utility(
    metrics: QueryCompilerGateMetricsV1,
    gate_safety_ready: bool,
) -> bool:
    return (
        gate_safety_ready
        and metrics.executable_gold_count > 0
        and metrics.false_abstention_count == 0
        and metrics.case_coverage == 1.0
        and metrics.gate_status_accuracy == 1.0
        and metrics.accepted_plan_exact == 1.0
        and metrics.fallback_decision_exact == 1.0
        and metrics.fallback_reason_exact == 1.0
        and metrics.unresolved_slots_exact == 1.0
        and metrics.blocked_reasons_exact == 1.0
    )


class QueryCompilerGateScoreV1(StrictModel):
    schema_version: Literal["query-compiler-gate-score-v1"] = (
        "query-compiler-gate-score-v1"
    )
    dataset_id: str = Field(min_length=1)
    assessment_mode: AssessmentMode = "dev_smoke"
    metrics: QueryCompilerGateMetricsV1
    gate_safety_ready: bool
    compilation_utility_ready: bool
    formal_gate_ready: bool
    formal_gate_blocked_reasons: list[str]
    raw_proposer_quality_evaluated: Literal[False] = False
    proposal_quality_ready: Literal[False] = False

    @model_validator(mode="after")
    def validate_readiness(self) -> "QueryCompilerGateScoreV1":
        safety = _derive_gate_safety(self.metrics)
        if self.gate_safety_ready != safety:
            raise ValueError("gate_safety_ready does not match typed metrics")
        utility = _derive_compilation_utility(self.metrics, safety)
        if self.compilation_utility_ready != utility:
            raise ValueError("compilation_utility_ready does not match typed metrics")
        formal = (
            self.assessment_mode == "formal_gate"
            and utility
            and not self.formal_gate_blocked_reasons
        )
        if self.formal_gate_ready != formal:
            raise ValueError("formal_gate_ready does not match verified prerequisites")
        return self


def _rate(numerator: int, denominator: int) -> float:
    return 0.0 if denominator == 0 else numerator / denominator


def score_query_compiler_batch(
    batch: QueryCompilerBatchResultV1,
    gold: QueryCompilerGoldDocumentV1,
    *,
    assessment_mode: AssessmentMode = "dev_smoke",
    formal_repo_path: Path | None = None,
    formal_freeze: QueryCompilerFormalFreezeV1 | None = None,
    authority: QueryCompilerAuthorityDocumentV1 | None = None,
    memory_repo_path: Path | None = None,
) -> QueryCompilerGateScoreV1:
    if batch.dataset_id != gold.dataset_id:
        raise ValueError("batch/gold dataset_id mismatch")
    batch_ids = {item.case_id for item in batch.entries}
    gold_ids = {item.case_id for item in gold.cases}
    if batch_ids != gold_ids:
        raise ValueError("batch/gold case coverage mismatch")

    entries = {item.case_id: item for item in batch.entries}
    status_correct = 0
    fallback_decision_correct = 0
    fallback_reason_correct = 0
    unresolved_slots_correct = 0
    blocked_reasons_correct = 0
    executable_gold = 0
    exact_plans = 0
    false_abstentions = 0
    false_executables = 0
    unsafe_executable_plans = 0
    critical_false = 0
    structural_fallback = 0
    for gold_case in gold.cases:
        result = entries[gold_case.case_id].result
        if result.status == gold_case.expected_status:
            status_correct += 1
        if result.fallback_allowed == gold_case.expected_fallback_allowed:
            fallback_decision_correct += 1
        if result.fallback_reason == gold_case.expected_fallback_reason:
            fallback_reason_correct += 1
        if result.unresolved_slots == gold_case.expected_unresolved_slots:
            unresolved_slots_correct += 1
        if result.blocked_reasons == gold_case.expected_blocked_reasons:
            blocked_reasons_correct += 1
        if gold_case.expected_status == "executable":
            executable_gold += 1
            if result.status == "abstain":
                false_abstentions += 1
            if (
                result.plan is not None
                and result.plan.plan_sha256 == gold_case.expected_plan_sha256
            ):
                exact_plans += 1
            elif result.status == "executable":
                unsafe_executable_plans += 1
        elif result.status == "executable":
            false_executables += 1
        if gold_case.critical and gold_case.expected_status == "abstain":
            if result.status == "executable":
                critical_false += 1
        if result.fallback_allowed and (
            result.blocked_reasons
            or result.fallback_reason not in get_args(FallbackReason)
        ):
            structural_fallback += 1

    case_count = len(gold.cases)
    metrics = QueryCompilerGateMetricsV1(
        case_count=case_count,
        family_coverage_count=len({item.family for item in gold.cases}),
        executable_gold_count=executable_gold,
        critical_gold_count=sum(item.critical for item in gold.cases),
        case_coverage=_rate(len(batch.entries), case_count),
        gate_status_accuracy=_rate(status_correct, case_count),
        accepted_plan_exact=_rate(exact_plans, executable_gold),
        fallback_decision_exact=_rate(fallback_decision_correct, case_count),
        fallback_reason_exact=_rate(fallback_reason_correct, case_count),
        unresolved_slots_exact=_rate(unresolved_slots_correct, case_count),
        blocked_reasons_exact=_rate(blocked_reasons_correct, case_count),
        false_abstention_count=false_abstentions,
        false_executable_count=false_executables,
        unsafe_executable_plan_count=unsafe_executable_plans,
        critical_false_executable_count=critical_false,
        structural_fallback_count=structural_fallback,
    )
    gate_safety_ready = _derive_gate_safety(metrics)
    compilation_utility_ready = _derive_compilation_utility(
        metrics,
        gate_safety_ready,
    )
    formal_blocked: list[str] = []
    if assessment_mode != "formal_gate":
        formal_blocked.append("assessment_mode_not_formal")
    else:
        if executable_gold == 0:
            formal_blocked.append("non_vacuous_executable_cases_missing")
        if metrics.critical_gold_count == 0:
            formal_blocked.append("critical_cases_missing")
        if metrics.family_coverage_count != len(get_args(QueryFamily)):
            formal_blocked.append("taxonomy_coverage_incomplete")
        if formal_repo_path is None or formal_freeze is None:
            formal_blocked.append("preregistration_unverified")
        else:
            preregistration_report = verify_formal_preregistration_history(
                repo_path=formal_repo_path,
                freeze=formal_freeze,
                batch=batch,
                gold=gold,
            )
            if not preregistration_report.verified:
                formal_blocked.append("preregistration_unverified")
                formal_blocked.extend(
                    f"preregistration: {item}"
                    for item in preregistration_report.errors
                )
        if authority is None or memory_repo_path is None:
            formal_blocked.append("authoritative_memory_view_unverified")
        else:
            memory_view_report = verify_authoritative_memory_view(
                authority,
                memory_repo_path,
            )
            if not memory_view_report.verified:
                formal_blocked.append("authoritative_memory_view_unverified")
                formal_blocked.extend(
                    f"memory_view: {item}" for item in memory_view_report.errors
                )
    formal_gate_ready = (
        assessment_mode == "formal_gate"
        and compilation_utility_ready
        and not formal_blocked
    )
    return QueryCompilerGateScoreV1(
        dataset_id=batch.dataset_id,
        assessment_mode=assessment_mode,
        metrics=metrics,
        gate_safety_ready=gate_safety_ready,
        compilation_utility_ready=compilation_utility_ready,
        formal_gate_ready=formal_gate_ready,
        formal_gate_blocked_reasons=formal_blocked,
    )
