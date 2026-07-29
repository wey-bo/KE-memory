from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from tools.natural_memory_benchmark.git_memory_history import (
    GitMemoryHistoryRepository,
    make_history_artifact,
)
from tools.natural_memory_benchmark.io import canonical_json_bytes, load_json
from tools.natural_memory_benchmark.query_compiler_v2 import (
    AnswerDraftV1,
    CompilerRegistryV1,
    GitMemoryViewRefV1,
    PredicateRegistryEntryV1,
    QueryAtomDraftV1,
    QueryContextV1,
    QueryDraftV1,
    QueryPatternGroupDraftV1,
    QueryRoleDraftV1,
    QueryTermDraftV1,
    QueryCompilationResultV1,
)
from tools.natural_memory_benchmark.query_compiler_v2_assessment import (
    QueryCompilerAuthorityCaseV1,
    QueryCompilerAuthorityDocumentV1,
    QueryCompilerBatchEntryV1,
    QueryCompilerBatchResultV1,
    QueryCompilerGateScoreV1,
    QueryCompilerFormalFreezeV1,
    QueryCompilerGoldCaseV1,
    QueryCompilerGoldDocumentV1,
    QueryCompilerPreregistrationV1,
    QueryCompilerProposalV1,
    QueryCompilerProposalDocumentV1,
    QueryCompilerPublicCaseV1,
    QueryCompilerPublicDocumentV1,
    QueryFamily,
    compile_query_proposals,
    memory_view_handle,
    run_query_compiler_batch_file,
    score_query_compiler_batch,
    verify_authoritative_memory_view,
    verify_formal_preregistration_history,
)


def _context() -> QueryContextV1:
    return QueryContextV1(
        query_id="qq-0123456789abcdef",
        raw_query="Which project do I lead?",
        query_time="2026-07-28T10:00:00Z",
        current_user_entity_id="entity-user",
        memory_view=GitMemoryViewRefV1(
            workspace_id="workspace-main",
            repository_epoch_id="epoch-001",
            checkpoint_id="checkpoint-0007",
            git_commit="a" * 40,
            authoritative_ref="refs/heads/authoritative",
        ),
        ontology_revision="ontology-v7",
        identity_revision="identity-v4",
        compiler_policy_revision="query-policy-v1",
    )


def _registry() -> CompilerRegistryV1:
    return CompilerRegistryV1(
        ontology_revision="ontology-v7",
        identity_revision="identity-v4",
        registry_revision="registry-v1",
        entity_aliases={"i": ["entity-user"]},
        entity_types={"entity-user": ["Person"]},
        identity_status={"entity-user": "resolved"},
        predicate_aliases={
            "lead": [
                PredicateRegistryEntryV1(
                    sense="lead/manage",
                    canonical_operator="manage",
                    role_types={"agent": "Person", "theme": "Project"},
                )
            ]
        },
    )


def _draft(*, predicate_surface: str = "lead") -> QueryDraftV1:
    return QueryDraftV1(
        query_id="qq-0123456789abcdef",
        intent="fact_lookup",
        target_level="both",
        answer=AnswerDraftV1(kind="fact", variable="?project"),
        pattern_groups=[
            QueryPatternGroupDraftV1(
                group_id="group-1",
                atoms=[
                    QueryAtomDraftV1(
                        atom_id="atom-1",
                        predicate_surface=predicate_surface,
                        roles=[
                            QueryRoleDraftV1(
                                role="agent",
                                role_name="ARG0",
                                term=QueryTermDraftV1(
                                    kind="entity_surface",
                                    value="i",
                                    expected_type="Person",
                                ),
                            ),
                            QueryRoleDraftV1(
                                role="theme",
                                role_name="ARG1",
                                term=QueryTermDraftV1(
                                    kind="variable",
                                    value="?project",
                                    expected_type="Project",
                                ),
                            ),
                        ],
                    )
                ],
            )
        ],
        conflict_policy="require_resolved",
        supersession_policy="current_only",
        evidence_policy="provenance_closure",
        producer_id="model-proposer",
        producer_version="1",
    )


def _documents(
    *,
    draft: QueryDraftV1 | None = None,
    context: QueryContextV1 | None = None,
):
    active_context = context or _context()
    public = QueryCompilerPublicDocumentV1(
        dataset_id="query-dev-v1",
        cases=[
            QueryCompilerPublicCaseV1(
                case_id="qc-0123456789abcdef",
                query_id=active_context.query_id,
                raw_query=active_context.raw_query,
                query_time=active_context.query_time,
                current_user_surface="I",
                memory_view_handle=memory_view_handle(active_context.memory_view),
                compiler_policy_revision=active_context.compiler_policy_revision,
            )
        ],
    )
    authority = QueryCompilerAuthorityDocumentV1(
        dataset_id="query-dev-v1",
        cases=[
            QueryCompilerAuthorityCaseV1(
                case_id="qc-0123456789abcdef",
                context=active_context,
                registry=_registry(),
            )
        ],
    )
    proposals = QueryCompilerProposalDocumentV1(
        dataset_id="query-dev-v1",
        proposals=[
            QueryCompilerProposalV1(
                case_id="qc-0123456789abcdef",
                draft=draft or _draft(),
            )
        ],
    )
    return public, authority, proposals


def test_batch_compilation_uses_public_authority_and_frozen_drafts_without_gold() -> None:
    public, authority, proposals = _documents()

    result = compile_query_proposals(public, authority, proposals)

    assert result.dataset_id == "query-dev-v1"
    assert len(result.entries) == 1
    assert result.entries[0].case_id == "qc-0123456789abcdef"
    assert result.entries[0].result.status == "executable"
    assert result.entries[0].result.plan is not None
    assert result.claim_boundary.gold_read_during_compilation is False
    assert result.claim_boundary.automatic_memory_write_count == 0
    assert result.claim_boundary.embedding_authority is False


def test_batch_compilation_rejects_missing_or_extra_proposals() -> None:
    public, authority, proposals = _documents()
    missing = proposals.model_copy(update={"proposals": []})
    extra = proposals.model_copy(
        update={
            "proposals": [
                *proposals.proposals,
                QueryCompilerProposalV1(
                    case_id="qc-fedcba9876543210",
                    draft=_draft(),
                ),
            ]
        }
    )

    with pytest.raises(ValueError, match="proposal case coverage mismatch"):
        compile_query_proposals(public, authority, missing)
    with pytest.raises(ValueError, match="proposal case coverage mismatch"):
        compile_query_proposals(public, authority, extra)


def test_batch_compilation_rejects_public_authority_context_mismatch() -> None:
    public, authority, proposals = _documents()
    mismatched_case = authority.cases[0].model_copy(
        update={
            "context": authority.cases[0].context.model_copy(
                update={"query_time": "2026-07-29T10:00:00Z"}
            )
        }
    )
    mismatched = authority.model_copy(update={"cases": [mismatched_case]})

    with pytest.raises(ValueError, match="public/authority query_time mismatch"):
        compile_query_proposals(public, mismatched, proposals)


def test_batch_file_is_immutable_and_deterministic(tmp_path: Path) -> None:
    public, authority, proposals = _documents()
    public_path = tmp_path / "public.json"
    authority_path = tmp_path / "authority.json"
    proposals_path = tmp_path / "proposals.json"
    output_path = tmp_path / "results.json"
    replay_path = tmp_path / "replay-results.json"
    public_path.write_text(public.model_dump_json(indent=2), encoding="utf-8")
    authority_path.write_text(authority.model_dump_json(indent=2), encoding="utf-8")
    proposals_path.write_text(proposals.model_dump_json(indent=2), encoding="utf-8")

    first = run_query_compiler_batch_file(
        public_path=public_path,
        authority_path=authority_path,
        proposals_path=proposals_path,
        output_path=output_path,
        run_id="run-query-dev-v1",
    )
    payload = load_json(output_path)

    assert first == payload
    assert output_path.stat().st_mode & 0o777 == 0o444
    run_query_compiler_batch_file(
        public_path=public_path,
        authority_path=authority_path,
        proposals_path=proposals_path,
        output_path=replay_path,
        run_id="run-query-dev-v1",
    )
    assert replay_path.stat().st_mode & 0o777 == 0o444
    assert output_path.read_bytes() == replay_path.read_bytes()

    run_query_compiler_batch_file(
        public_path=public_path,
        authority_path=authority_path,
        proposals_path=proposals_path,
        output_path=output_path,
        run_id="run-query-dev-v1",
    )
    changed = proposals.model_copy(
        update={
            "proposals": [
                proposals.proposals[0].model_copy(
                    update={
                        "draft": proposals.proposals[0].draft.model_copy(
                            update={"producer_version": "2"}
                        )
                    }
                )
            ]
        }
    )
    proposals_path.write_text(changed.model_dump_json(indent=2), encoding="utf-8")
    with pytest.raises(FileExistsError, match="immutable artifact differs"):
        run_query_compiler_batch_file(
            public_path=public_path,
            authority_path=authority_path,
            proposals_path=proposals_path,
            output_path=output_path,
            run_id="run-query-dev-v1",
        )


def test_public_ids_are_opaque_and_reject_outcome_leakage() -> None:
    context = _context()

    with pytest.raises(ValueError, match="case_id"):
        QueryCompilerPublicCaseV1(
            case_id="case-critical-abstain-identity",
            query_id=context.query_id,
            raw_query=context.raw_query,
            query_time=context.query_time,
            current_user_surface="I",
            memory_view_handle=memory_view_handle(context.memory_view),
            compiler_policy_revision=context.compiler_policy_revision,
        )
    with pytest.raises(ValueError, match="query_id"):
        QueryCompilerPublicCaseV1(
            case_id="qc-fedcba9876543210",
            query_id="query-membership-unresolved",
            raw_query=context.raw_query,
            query_time=context.query_time,
            current_user_surface="I",
            memory_view_handle=memory_view_handle(context.memory_view),
            compiler_policy_revision=context.compiler_policy_revision,
        )


def test_gate_scorer_reports_safety_separately_from_raw_quality() -> None:
    public, authority, proposals = _documents()
    batch = compile_query_proposals(public, authority, proposals)
    assert batch.entries[0].result.plan is not None
    frozen_plan_sha256 = batch.entries[0].result.plan.plan_sha256
    gold = QueryCompilerGoldDocumentV1(
        dataset_id="query-dev-v1",
        cases=[
            QueryCompilerGoldCaseV1(
                case_id="qc-0123456789abcdef",
                family="atomic_fact_role",
                expected_status="executable",
                expected_plan_sha256=frozen_plan_sha256,
                expected_fallback_allowed=False,
                expected_fallback_reason=None,
                expected_unresolved_slots=[],
                expected_blocked_reasons=[],
                critical=False,
            )
        ],
    )

    score = score_query_compiler_batch(batch, gold)

    assert score.metrics.case_coverage == 1.0
    assert score.metrics.gate_status_accuracy == 1.0
    assert score.metrics.accepted_plan_exact == 1.0
    assert score.metrics.fallback_decision_exact == 1.0
    assert score.metrics.fallback_reason_exact == 1.0
    assert score.metrics.critical_false_executable_count == 0
    assert score.gate_safety_ready is True
    assert score.compilation_utility_ready is True
    assert score.formal_gate_ready is False
    assert score.raw_proposer_quality_evaluated is False
    assert score.proposal_quality_ready is False


def test_gate_scorer_counts_critical_false_executable_plan() -> None:
    public, authority, proposals = _documents()
    batch = compile_query_proposals(public, authority, proposals)
    gold = QueryCompilerGoldDocumentV1(
        dataset_id="query-dev-v1",
        cases=[
            QueryCompilerGoldCaseV1(
                case_id="qc-0123456789abcdef",
                family="identity_aggregate",
                expected_status="abstain",
                expected_plan_sha256=None,
                expected_fallback_allowed=False,
                expected_fallback_reason=None,
                expected_unresolved_slots=[],
                expected_blocked_reasons=[],
                critical=True,
            )
        ],
    )

    score = score_query_compiler_batch(batch, gold)

    assert score.metrics.critical_false_executable_count == 1
    assert score.gate_safety_ready is False
    assert score.raw_proposer_quality_evaluated is False


def test_gate_scorer_scores_exact_fallback_and_diagnostic_taxonomy() -> None:
    public, authority, proposals = _documents(draft=_draft(predicate_surface="guide"))
    batch = compile_query_proposals(public, authority, proposals)
    gold = QueryCompilerGoldDocumentV1(
        dataset_id="query-dev-v1",
        cases=[
            QueryCompilerGoldCaseV1(
                case_id="qc-0123456789abcdef",
                family="entity_predicate_linking",
                expected_status="abstain",
                expected_plan_sha256=None,
                expected_fallback_allowed=True,
                expected_fallback_reason="lexical_predicate_missing_link",
                expected_unresolved_slots=["predicate:atom-1"],
                expected_blocked_reasons=[],
                critical=False,
            )
        ],
    )

    score = score_query_compiler_batch(batch, gold)

    assert score.metrics.fallback_decision_exact == 1.0
    assert score.metrics.fallback_reason_exact == 1.0
    assert score.metrics.unresolved_slots_exact == 1.0
    assert score.metrics.blocked_reasons_exact == 1.0
    assert score.metrics.structural_fallback_count == 0
    assert score.gate_safety_ready is True
    assert score.compilation_utility_ready is False


def test_all_abstain_dataset_cannot_vacuously_pass_utility_or_formal_gate() -> None:
    public, authority, proposals = _documents(draft=_draft(predicate_surface="guide"))
    batch = compile_query_proposals(public, authority, proposals)
    gold = QueryCompilerGoldDocumentV1(
        dataset_id="query-dev-v1",
        cases=[
            QueryCompilerGoldCaseV1(
                case_id="qc-0123456789abcdef",
                family="entity_predicate_linking",
                expected_status="abstain",
                expected_plan_sha256=None,
                expected_fallback_allowed=True,
                expected_fallback_reason="lexical_predicate_missing_link",
                expected_unresolved_slots=["predicate:atom-1"],
                expected_blocked_reasons=[],
                critical=True,
            )
        ],
    )

    score = score_query_compiler_batch(batch, gold, assessment_mode="formal_gate")

    assert score.metrics.executable_gold_count == 0
    assert score.metrics.accepted_plan_exact == 0.0
    assert score.compilation_utility_ready is False
    assert score.formal_gate_ready is False
    assert "non_vacuous_executable_cases_missing" in score.formal_gate_blocked_reasons
    assert "taxonomy_coverage_incomplete" in score.formal_gate_blocked_reasons


def test_structural_fallback_is_counted_as_unsafe() -> None:
    public, authority, proposals = _documents()
    original = compile_query_proposals(public, authority, proposals)
    unsafe_result = QueryCompilationResultV1(
        query_id=_context().query_id,
        status="abstain",
        unresolved_slots=["entity:atom-1:agent"],
        blocked_reasons=["identity_unresolved:atom-1:agent"],
        fallback_allowed=True,
        fallback_reason="unresolved_entity",
    )
    batch = original.model_copy(
        update={
            "entries": [
                QueryCompilerBatchEntryV1(
                    case_id="qc-0123456789abcdef",
                    result=unsafe_result,
                )
            ]
        }
    )
    gold = QueryCompilerGoldDocumentV1(
        dataset_id="query-dev-v1",
        cases=[
            QueryCompilerGoldCaseV1(
                case_id="qc-0123456789abcdef",
                family="identity_aggregate",
                expected_status="abstain",
                expected_plan_sha256=None,
                expected_fallback_allowed=False,
                expected_fallback_reason=None,
                expected_unresolved_slots=["entity:atom-1:agent"],
                expected_blocked_reasons=["identity_unresolved:atom-1:agent"],
                critical=True,
            )
        ],
    )

    score = score_query_compiler_batch(batch, gold)

    assert score.metrics.structural_fallback_count == 1
    assert score.gate_safety_ready is False


def test_gate_score_rederives_readiness_and_rejects_tampering() -> None:
    public, authority, proposals = _documents()
    batch = compile_query_proposals(public, authority, proposals)
    assert batch.entries[0].result.plan is not None
    gold = QueryCompilerGoldDocumentV1(
        dataset_id="query-dev-v1",
        cases=[
            QueryCompilerGoldCaseV1(
                case_id="qc-0123456789abcdef",
                family="atomic_fact_role",
                expected_status="executable",
                expected_plan_sha256=batch.entries[0].result.plan.plan_sha256,
                expected_fallback_allowed=False,
                expected_fallback_reason=None,
                expected_unresolved_slots=[],
                expected_blocked_reasons=[],
                critical=False,
            )
        ],
    )
    score = score_query_compiler_batch(batch, gold)
    payload = score.model_dump(mode="json")
    payload["gate_safety_ready"] = False

    with pytest.raises(ValueError, match="gate_safety_ready"):
        QueryCompilerGateScoreV1.model_validate(payload)


def test_batch_input_hashes_require_lowercase_hex() -> None:
    public, authority, proposals = _documents()
    batch = compile_query_proposals(public, authority, proposals)
    payload = batch.model_dump(mode="json")
    payload["input_sha256"]["public"] = "z" * 64

    with pytest.raises(ValueError, match="input hash"):
        QueryCompilerBatchResultV1.model_validate(payload)


def _git(repo_path: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", os.fspath(repo_path), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def _commit(repo_path: Path, message: str) -> str:
    _git(repo_path, "add", ".")
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "Query Gate Test",
            "GIT_AUTHOR_EMAIL": "query-gate@example.invalid",
            "GIT_COMMITTER_NAME": "Query Gate Test",
            "GIT_COMMITTER_EMAIL": "query-gate@example.invalid",
        }
    )
    subprocess.run(
        ["git", "-C", os.fspath(repo_path), "commit", "-q", "-m", message],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    return _git(repo_path, "rev-parse", "HEAD")


def _verified_memory_context(
    repo_path: Path,
) -> tuple[QueryContextV1, GitMemoryHistoryRepository]:
    repository = GitMemoryHistoryRepository.initialize(
        repo_path,
        workspace_id="workspace-main",
        created_at="2026-07-28T00:00:00Z",
    )
    artifact = make_history_artifact(
        artifact_kind="turn_bundle",
        logical_id="turn-bundle-1",
        revision_id="revision-1",
        transaction_time="2026-07-28T00:00:01Z",
        payload={"raw_text": "Remember tea."},
    )
    manifest = repository.make_checkpoint(
        artifacts=[artifact],
        transaction_time="2026-07-28T00:00:02Z",
    )
    repository.commit_checkpoint(
        manifest=manifest,
        artifacts=[artifact],
        expected_head=repository.head_commit(),
    )
    metadata = repository.read_repository_metadata()
    state = repository.read_state()
    context = _context().model_copy(
        update={
            "memory_view": GitMemoryViewRefV1(
                workspace_id=metadata.workspace_id,
                repository_epoch_id=metadata.repository_epoch_id,
                checkpoint_id=state.checkpoint_id,
                git_commit=repository.head_commit(),
                authoritative_ref="refs/heads/authoritative",
            )
        }
    )
    return context, repository


def test_memory_view_verification_uses_real_authoritative_history(
    tmp_path: Path,
) -> None:
    context, repository = _verified_memory_context(tmp_path / "memory-history.git")
    _, authority, _ = _documents(context=context)

    verified = verify_authoritative_memory_view(authority, repository.repo_path)
    tampered_case = authority.cases[0].model_copy(
        update={
            "context": context.model_copy(
                update={
                    "memory_view": context.memory_view.model_copy(
                        update={"git_commit": "b" * 40}
                    )
                }
            )
        }
    )
    tampered = authority.model_copy(update={"cases": [tampered_case]})
    rejected = verify_authoritative_memory_view(tampered, repository.repo_path)

    assert verified.verified is True
    assert verified.errors == []
    assert rejected.verified is False
    assert "git_commit mismatch" in rejected.errors


def test_formal_preregistration_history_verifies_order_and_immutability(
    tmp_path: Path,
) -> None:
    context, memory_repository = _verified_memory_context(
        tmp_path / "memory-history.git"
    )
    public, authority, proposals = _documents(context=context)
    batch = compile_query_proposals(public, authority, proposals)
    assert batch.entries[0].result.plan is not None
    gold = QueryCompilerGoldDocumentV1(
        dataset_id="query-dev-v1",
        cases=[
            QueryCompilerGoldCaseV1(
                case_id="qc-0123456789abcdef",
                family="atomic_fact_role",
                expected_status="executable",
                expected_plan_sha256=batch.entries[0].result.plan.plan_sha256,
                expected_fallback_allowed=False,
                expected_fallback_reason=None,
                expected_unresolved_slots=[],
                expected_blocked_reasons=[],
                critical=True,
            )
        ],
    )
    repo_path = tmp_path / "formal-gate"
    subprocess.run(
        ["git", "init", "-q", "-b", "main", os.fspath(repo_path)],
        check=True,
    )
    compiler_path = repo_path / "frozen" / "query_compiler_v2.py"
    assessment_path = repo_path / "frozen" / "query_compiler_v2_assessment.py"
    compiler_path.parent.mkdir(parents=True)
    compiler_path.write_text("# frozen compiler\n", encoding="utf-8")
    assessment_path.write_text("# frozen assessor\n", encoding="utf-8")
    preregistration = QueryCompilerPreregistrationV1(
        dataset_id="query-dev-v1",
        required_families=list(QueryFamily.__args__),
        minimum_executable_cases=1,
        minimum_critical_cases=1,
        compiler_path="frozen/query_compiler_v2.py",
        compiler_sha256=hashlib.sha256(compiler_path.read_bytes()).hexdigest(),
        assessment_path="frozen/query_compiler_v2_assessment.py",
        assessment_sha256=hashlib.sha256(assessment_path.read_bytes()).hexdigest(),
    )
    prereg_path = repo_path / "gate" / "preregistration.json"
    prereg_path.parent.mkdir(parents=True)
    prereg_path.write_bytes(canonical_json_bytes(preregistration))
    prereg_commit = _commit(repo_path, "freeze preregistration")

    public_path = repo_path / "gate" / "public.json"
    public_path.write_bytes(canonical_json_bytes(public))
    public_commit = _commit(repo_path, "freeze public queries")

    proposals_path = repo_path / "gate" / "proposals.json"
    proposals_path.write_bytes(canonical_json_bytes(proposals))
    proposals_commit = _commit(repo_path, "freeze proposals")

    authority_path = repo_path / "gate" / "authority.json"
    gold_path = repo_path / "gate" / "gold.json"
    authority_path.write_bytes(canonical_json_bytes(authority))
    gold_path.write_bytes(canonical_json_bytes(gold))
    authority_gold_commit = _commit(repo_path, "freeze authority and gold")
    freeze = QueryCompilerFormalFreezeV1(
        dataset_id="query-dev-v1",
        preregistration_commit=prereg_commit,
        public_commit=public_commit,
        proposals_commit=proposals_commit,
        authority_gold_commit=authority_gold_commit,
        preregistration_path="gate/preregistration.json",
        public_path="gate/public.json",
        proposals_path="gate/proposals.json",
        authority_path="gate/authority.json",
        gold_path="gate/gold.json",
    )

    verified = verify_formal_preregistration_history(
        repo_path=repo_path,
        freeze=freeze,
        batch=batch,
        gold=gold,
    )
    score = score_query_compiler_batch(
        batch,
        gold,
        assessment_mode="formal_gate",
        formal_repo_path=repo_path,
        formal_freeze=freeze,
        authority=authority,
        memory_repo_path=memory_repository.repo_path,
    )
    public_path.write_text("{}\n", encoding="utf-8")
    tampered_commit = _commit(repo_path, "tamper public after gold")
    tampered_freeze = freeze.model_copy(
        update={"authority_gold_commit": tampered_commit}
    )
    rejected = verify_formal_preregistration_history(
        repo_path=repo_path,
        freeze=tampered_freeze,
        batch=batch,
        gold=gold,
    )

    assert verified.verified is True
    assert verified.errors == []
    assert "preregistration_unverified" not in score.formal_gate_blocked_reasons
    assert (
        "authoritative_memory_view_unverified"
        not in score.formal_gate_blocked_reasons
    )
    assert "taxonomy_coverage_incomplete" in score.formal_gate_blocked_reasons
    assert score.formal_gate_ready is False
    assert rejected.verified is False
    assert "public bytes changed after proposal freeze" in rejected.errors
