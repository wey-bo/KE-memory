from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tools.natural_memory_benchmark.io import (
    canonical_json_bytes,
    load_json,
)
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
    compile_query_draft,
)
from tools.natural_memory_benchmark.query_compiler_v2_assessment import (
    QueryCompilerAuthorityCaseV1,
    QueryCompilerAuthorityDocumentV1,
    QueryCompilerGoldCaseV1,
    QueryCompilerGoldDocumentV1,
    QueryCompilerPublicCaseV1,
    QueryCompilerPublicDocumentV1,
    memory_view_handle,
)
from tools.natural_memory_benchmark.query_compiler_v2_proposal_eval import (
    QueryDraftGoldCaseV1,
    QueryDraftGoldDocumentV1,
    QueryDraftProposalDocumentV1,
    QueryDraftProposalEvaluationV1,
    QueryDraftProposalProvenanceV1,
    QueryDraftRawProposalV1,
    freeze_query_draft_proposal_run,
    materialize_typed_query_proposals,
)


ROOT = Path(__file__).resolve().parents[2]
CLI_MODULE = (
    "tools.natural_memory_benchmark.query_compiler_v2_proposal_eval_cli"
)
DATASET_ID = "query-proposer-cli-dev-v1"
CASE_ID = "qc-0123456789abcdef"
QUERY_ID = "qq-fedcba9876543210"


def _context() -> QueryContextV1:
    return QueryContextV1(
        query_id=QUERY_ID,
        raw_query="Which project do I lead?",
        query_time="2026-07-29T00:00:00Z",
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
        compiler_policy_revision="query-policy-v2",
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
        query_id=QUERY_ID,
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
        lifecycle="active",
        conflict_policy="require_resolved",
        supersession_policy="current_only",
        evidence_policy="provenance_closure",
        producer_id="reference-proposer",
        producer_version="1",
    )


def _documents() -> tuple[
    QueryCompilerPublicDocumentV1,
    QueryCompilerAuthorityDocumentV1,
    QueryDraftProposalDocumentV1,
    QueryDraftGoldDocumentV1,
    QueryCompilerGoldDocumentV1,
]:
    context = _context()
    registry = _registry()
    draft = _draft()
    public = QueryCompilerPublicDocumentV1(
        dataset_id=DATASET_ID,
        cases=[
            QueryCompilerPublicCaseV1(
                case_id=CASE_ID,
                query_id=QUERY_ID,
                raw_query=context.raw_query,
                query_time=context.query_time,
                current_user_surface="I",
                memory_view_handle=memory_view_handle(context.memory_view),
                compiler_policy_revision=context.compiler_policy_revision,
            )
        ],
    )
    authority = QueryCompilerAuthorityDocumentV1(
        dataset_id=DATASET_ID,
        cases=[
            QueryCompilerAuthorityCaseV1(
                case_id=CASE_ID,
                context=context,
                registry=registry,
            )
        ],
    )
    raw_response = {"response_id": "response-1", "model": "model-returned"}
    raw_response_sha256 = hashlib.sha256(
        canonical_json_bytes(raw_response)
    ).hexdigest()
    proposals = QueryDraftProposalDocumentV1(
        dataset_id=DATASET_ID,
        proposals=[
            QueryDraftRawProposalV1(
                case_id=CASE_ID,
                parse_status="json",
                raw_payload=draft.model_dump(mode="json"),
                raw_response_sha256=raw_response_sha256,
            )
        ],
    )
    draft_gold = QueryDraftGoldDocumentV1(
        dataset_id=DATASET_ID,
        cases=[
            QueryDraftGoldCaseV1(
                case_id=CASE_ID,
                expected_draft=draft.model_copy(
                    update={
                        "producer_id": "gold-author",
                        "producer_version": "gold-v1",
                    }
                ),
                critical=True,
            )
        ],
    )
    compiled = compile_query_draft(draft, context, registry)
    assert compiled.status == "executable"
    assert compiled.plan is not None
    compiler_gold = QueryCompilerGoldDocumentV1(
        dataset_id=DATASET_ID,
        cases=[
            QueryCompilerGoldCaseV1(
                case_id=CASE_ID,
                family="atomic_fact_role",
                expected_status="executable",
                expected_plan_sha256=compiled.plan.plan_sha256,
                expected_fallback_allowed=False,
                expected_unresolved_slots=[],
                expected_blocked_reasons=[],
            )
        ],
    )
    return public, authority, proposals, draft_gold, compiler_gold


def _write_json(path: Path, value: object) -> None:
    path.write_bytes(canonical_json_bytes(value))


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", CLI_MODULE, *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _score_args(root: Path, output: Path) -> tuple[str, ...]:
    return (
        "score-proposals",
        "--public",
        os.fspath(root / "public.json"),
        "--authority",
        os.fspath(root / "authority.json"),
        "--proposals",
        os.fspath(root / "proposals.json"),
        "--draft-gold",
        os.fspath(root / "draft-gold.json"),
        "--compiler-gold",
        os.fspath(root / "compiler-gold.json"),
        "--output",
        os.fspath(output),
    )


def _write_score_inputs(
    root: Path,
    *,
    draft_gold: QueryDraftGoldDocumentV1 | None = None,
) -> None:
    public, authority, proposals, default_gold, compiler_gold = _documents()
    inputs = {
        "public.json": public,
        "authority.json": authority,
        "proposals.json": proposals,
        "draft-gold.json": draft_gold or default_gold,
        "compiler-gold.json": compiler_gold,
    }
    root.mkdir(parents=True, exist_ok=True)
    for name, value in inputs.items():
        _write_json(root / name, value)


def test_parser_exposes_only_standalone_proposal_commands() -> None:
    from tools.natural_memory_benchmark.query_compiler_v2_proposal_eval_cli import (
        build_parser,
    )

    parser = build_parser()

    score = parser.parse_args(
        [
            "score-proposals",
            "--public",
            "public.json",
            "--authority",
            "authority.json",
            "--proposals",
            "proposals.json",
            "--draft-gold",
            "draft-gold.json",
            "--compiler-gold",
            "compiler-gold.json",
            "--output",
            "evaluation.json",
        ]
    )
    validate = parser.parse_args(["validate-run", "--root", "run"])

    assert score.command == "score-proposals"
    assert validate.command == "validate-run"


def test_score_proposals_writes_one_immutable_combined_evaluation(
    tmp_path: Path,
) -> None:
    public, authority, proposals, draft_gold, compiler_gold = _documents()
    inputs = {
        "public.json": public,
        "authority.json": authority,
        "proposals.json": proposals,
        "draft-gold.json": draft_gold,
        "compiler-gold.json": compiler_gold,
    }
    for name, value in inputs.items():
        _write_json(tmp_path / name, value)
    output = tmp_path / "evaluation.json"
    args = (
        "score-proposals",
        "--public",
        os.fspath(tmp_path / "public.json"),
        "--authority",
        os.fspath(tmp_path / "authority.json"),
        "--proposals",
        os.fspath(tmp_path / "proposals.json"),
        "--draft-gold",
        os.fspath(tmp_path / "draft-gold.json"),
        "--compiler-gold",
        os.fspath(tmp_path / "compiler-gold.json"),
        "--output",
        os.fspath(output),
    )

    completed = _run_cli(*args)

    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout)
    assert summary == {
        "combined_dev_ready": True,
        "dataset_id": DATASET_ID,
        "gate_evaluated": True,
        "status": "scored",
    }
    evaluation = QueryDraftProposalEvaluationV1.model_validate(load_json(output))
    assert evaluation.raw_score.raw_proposer_quality_ready is True
    assert evaluation.gate_score is not None
    assert evaluation.gate_score.gate_safety_ready is True
    original_bytes = output.read_bytes()

    replay = _run_cli(*args)

    assert replay.returncode == 0, replay.stderr
    assert output.read_bytes() == original_bytes

    changed_gold = draft_gold.model_copy(
        update={
            "cases": [
                draft_gold.cases[0].model_copy(
                    update={"expected_draft": _draft(predicate_surface="own")}
                )
            ]
        }
    )
    _write_json(tmp_path / "draft-gold.json", changed_gold)
    rejected = _run_cli(*args)

    assert rejected.returncode != 0
    assert "immutable artifact differs" in rejected.stderr
    assert output.read_bytes() == original_bytes


def test_score_rejects_dangling_output_symlink_without_creating_target(
    tmp_path: Path,
) -> None:
    _write_score_inputs(tmp_path)
    target = tmp_path / "redirected.json"
    output = tmp_path / "evaluation.json"
    try:
        output.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    completed = _run_cli(*_score_args(tmp_path, output))

    assert completed.returncode != 0
    assert "symlink" in completed.stderr
    assert not target.exists()


def test_score_rejects_output_aliasing_any_input(tmp_path: Path) -> None:
    _write_score_inputs(tmp_path)
    public_path = tmp_path / "public.json"
    original = public_path.read_bytes()

    completed = _run_cli(*_score_args(tmp_path, public_path))

    assert completed.returncode != 0
    assert "output aliases input" in completed.stderr
    assert public_path.read_bytes() == original


def test_score_publication_is_atomic_first_writer_wins(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    _write_score_inputs(first_root)
    _, _, _, changed_gold, _ = _documents()
    changed_gold = changed_gold.model_copy(
        update={
            "cases": [
                changed_gold.cases[0].model_copy(
                    update={"expected_draft": _draft(predicate_surface="own")}
                )
            ]
        }
    )
    _write_score_inputs(second_root, draft_gold=changed_gold)
    output = tmp_path / "evaluation.json"
    command_prefix = [sys.executable, "-m", CLI_MODULE]
    first = subprocess.Popen(
        [*command_prefix, *_score_args(first_root, output)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    second = subprocess.Popen(
        [*command_prefix, *_score_args(second_root, output)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    first_output = first.communicate()
    second_output = second.communicate()

    assert sorted([first.returncode, second.returncode]) == [0, 1]
    errors = [first_output[1], second_output[1]]
    assert any("immutable artifact differs" in value for value in errors)
    evaluation = QueryDraftProposalEvaluationV1.model_validate(load_json(output))
    assert evaluation.dataset_id == DATASET_ID


def test_atomic_writer_cleans_temp_file_when_publication_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from tools.natural_memory_benchmark import (
        query_compiler_v2_proposal_eval_cli,
    )

    output = tmp_path / "evaluation.json"

    def fail_link(source, destination):
        raise OSError("injected link failure")

    monkeypatch.setattr(os, "link", fail_link)
    with pytest.raises(OSError, match="injected link failure"):
        query_compiler_v2_proposal_eval_cli._write_json_atomic_immutable(
            output,
            {"status": "test"},
        )

    assert not output.exists()
    assert list(tmp_path.glob(".evaluation.json.*.tmp")) == []


def test_validate_run_replays_fixed_artifacts_and_rejects_tampering(
    tmp_path: Path,
) -> None:
    public, _, proposals, _, _ = _documents()
    prompt = b"Return one QueryDraftV1 for each opaque case.\n"
    dispatch = {
        "case_count": 1,
        "model": "model-alias",
        "request_id": "request-1",
    }
    raw_response = {"response_id": "response-1", "model": "model-returned"}
    raw_hash = hashlib.sha256(
        canonical_json_bytes(raw_response)
    ).hexdigest()
    proposals = proposals.model_copy(
        update={
            "proposals": [
                proposals.proposals[0].model_copy(
                    update={"raw_response_sha256": raw_hash}
                )
            ]
        }
    )
    provenance = QueryDraftProposalProvenanceV1(
        dataset_id=DATASET_ID,
        run_id="run-query-proposer-cli-dev-v1",
        requested_model="model-alias",
        response_model="model-returned",
        public_sha256=hashlib.sha256(
            canonical_json_bytes(public)
        ).hexdigest(),
        prompt_sha256=hashlib.sha256(prompt).hexdigest(),
        dispatch_sha256=hashlib.sha256(
            canonical_json_bytes(dispatch)
        ).hexdigest(),
        raw_response_sha256=raw_hash,
        proposals_sha256=hashlib.sha256(
            canonical_json_bytes(proposals)
        ).hexdigest(),
    )
    receipt, typed = materialize_typed_query_proposals(public, proposals)
    assert typed is not None
    run_root = tmp_path / "run"
    manifest = freeze_query_draft_proposal_run(
        root=run_root,
        public=public,
        prompt_bytes=prompt,
        dispatch=dispatch,
        raw_response=raw_response,
        proposals=proposals,
        provenance=provenance,
        validation_receipt=receipt,
        typed_proposals=typed,
    )

    completed = _run_cli("validate-run", "--root", os.fspath(run_root))

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "dataset_id": DATASET_ID,
        "requested_model": "model-alias",
        "response_model": "model-returned",
        "run_id": manifest.run_id,
        "status": "valid",
    }

    raw_path = run_root / "raw-response.json"
    os.chmod(raw_path, 0o644)
    raw_path.write_text("{}\n", encoding="utf-8")
    rejected = _run_cli("validate-run", "--root", os.fspath(run_root))

    assert rejected.returncode != 0
    assert "artifact hash mismatch" in rejected.stderr
