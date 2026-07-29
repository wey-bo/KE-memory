from __future__ import annotations

from pathlib import Path

import pytest

from tools.natural_memory_benchmark.io import load_json
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
)
from tools.natural_memory_benchmark.query_compiler_v2_assessment import (
    QueryCompilerAuthorityCaseV1,
    QueryCompilerAuthorityDocumentV1,
    QueryCompilerGoldCaseV1,
    QueryCompilerGoldDocumentV1,
    QueryCompilerProposalDocumentV1,
    QueryCompilerProposalV1,
    QueryCompilerPublicCaseV1,
    QueryCompilerPublicDocumentV1,
    compile_query_proposals,
    memory_view_handle,
)
from tools.natural_memory_benchmark.query_compiler_v2_cli import main


def _documents():
    context = QueryContextV1(
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
    registry = CompilerRegistryV1(
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
    draft = QueryDraftV1(
        query_id=context.query_id,
        intent="fact_lookup",
        target_level="both",
        answer=AnswerDraftV1(kind="fact", variable="?project"),
        pattern_groups=[
            QueryPatternGroupDraftV1(
                group_id="group-1",
                atoms=[
                    QueryAtomDraftV1(
                        atom_id="atom-1",
                        predicate_surface="lead",
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
    public = QueryCompilerPublicDocumentV1(
        dataset_id="query-cli-dev-v1",
        cases=[
            QueryCompilerPublicCaseV1(
                case_id="qc-0123456789abcdef",
                query_id=context.query_id,
                raw_query=context.raw_query,
                query_time=context.query_time,
                current_user_surface="I",
                memory_view_handle=memory_view_handle(context.memory_view),
                compiler_policy_revision=context.compiler_policy_revision,
            )
        ],
    )
    authority = QueryCompilerAuthorityDocumentV1(
        dataset_id=public.dataset_id,
        cases=[
            QueryCompilerAuthorityCaseV1(
                case_id=public.cases[0].case_id,
                context=context,
                registry=registry,
            )
        ],
    )
    proposals = QueryCompilerProposalDocumentV1(
        dataset_id=public.dataset_id,
        proposals=[
            QueryCompilerProposalV1(
                case_id=public.cases[0].case_id,
                draft=draft,
            )
        ],
    )
    return public, authority, proposals


def _write(path: Path, model: object) -> None:
    path.write_text(model.model_dump_json(indent=2), encoding="utf-8")


def test_compile_batch_cli_writes_immutable_result(tmp_path: Path) -> None:
    public, authority, proposals = _documents()
    public_path = tmp_path / "public.json"
    authority_path = tmp_path / "authority.json"
    proposals_path = tmp_path / "proposals.json"
    output_path = tmp_path / "batch.json"
    _write(public_path, public)
    _write(authority_path, authority)
    _write(proposals_path, proposals)

    exit_code = main(
        [
            "compile-batch",
            "--public",
            str(public_path),
            "--authority",
            str(authority_path),
            "--proposals",
            str(proposals_path),
            "--output",
            str(output_path),
            "--run-id",
            "run-query-cli-dev-v1",
        ]
    )

    assert exit_code == 0
    assert load_json(output_path)["schema_version"] == "query-compiler-batch-result-v1"
    assert output_path.stat().st_mode & 0o777 == 0o444


def test_score_batch_cli_writes_typed_dev_smoke_and_rejects_change(
    tmp_path: Path,
) -> None:
    public, authority, proposals = _documents()
    batch = compile_query_proposals(public, authority, proposals)
    assert batch.entries[0].result.plan is not None
    gold = QueryCompilerGoldDocumentV1(
        dataset_id=public.dataset_id,
        cases=[
            QueryCompilerGoldCaseV1(
                case_id=public.cases[0].case_id,
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
    batch_path = tmp_path / "batch.json"
    gold_path = tmp_path / "gold.json"
    output_path = tmp_path / "score.json"
    _write(batch_path, batch)
    _write(gold_path, gold)

    assert main(
        [
            "score-batch",
            "--batch",
            str(batch_path),
            "--gold",
            str(gold_path),
            "--output",
            str(output_path),
        ]
    ) == 0
    payload = load_json(output_path)

    assert payload["assessment_mode"] == "dev_smoke"
    assert payload["gate_safety_ready"] is True
    assert payload["compilation_utility_ready"] is True
    assert payload["formal_gate_ready"] is False
    assert output_path.stat().st_mode & 0o777 == 0o444

    changed_gold = gold.model_copy(
        update={
            "cases": [
                gold.cases[0].model_copy(update={"expected_fallback_allowed": True})
            ]
        }
    )
    _write(gold_path, changed_gold)
    with pytest.raises((FileExistsError, ValueError)):
        main(
            [
                "score-batch",
                "--batch",
                str(batch_path),
                "--gold",
                str(gold_path),
                "--output",
                str(output_path),
            ]
        )
