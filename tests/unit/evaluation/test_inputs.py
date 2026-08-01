from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
from typing import Any, cast

import pytest
from pydantic import ValidationError

from ke_memory_demo.core.json import JsonObject
from ke_memory_demo.domain import Conversation, Exchange, Message, MessageRole, Session
from ke_memory_demo.evaluation import (
    EvaluationPreflight,
    ExperimentManifest,
    GoldSourceStatus,
    PreflightCheckFailure,
    SourceCatalog,
    SourceMappingError,
    build_gold_source_mapping,
    normalize_question,
)
from ke_memory_demo.ontology import IndexIdentity
from ke_memory_demo.pipeline import (
    OntologyRunIdentity,
    PipelineRunManifest,
    PipelineStage,
)
from ke_memory_demo.evaluation.runtime import validate_evaluation_snapshot_contract
from ke_memory_demo.evaluation.runtime import build_evaluation_preflight
from ke_memory_demo.settings import EvaluationConcurrencySettings, load_settings


@pytest.mark.parametrize(
    ("raw", "field", "answer"),
    [
        (
            {
                "ideal_answer": "a",
                "ideal_response": "b",
                "answer": "c",
                "ideal_summary": "d",
                "expected_compliance": "e",
            },
            "ideal_answer",
            "a",
        ),
        ({"ideal_response": "b", "answer": "c"}, "ideal_response", "b"),
        ({"answer": "c"}, "answer", "c"),
        ({"ideal_summary": "d"}, "ideal_summary", "d"),
        ({"expected_compliance": "e"}, "expected_compliance", "e"),
    ],
)
def test_answer_priority(raw: JsonObject, field: str, answer: str) -> None:
    value: JsonObject = {"question": "q", "rubric": ["r"], **raw}
    normalized = normalize_question(
        value,
        conversation_id="conversation-1",
        category="knowledge_update",
        ordinal=0,
    )
    assert normalized.ideal_answer == answer
    assert normalized.original_answer_field == field


def test_gold_mapping_uses_only_unique_explicit_source_numbers() -> None:
    catalog = SourceCatalog.from_conversation(_conversation((8, 10, 12, 14)))
    mapping = build_gold_source_mapping(
        {
            "source_chat_ids": [8, [10, 12]],
            "conversation_references": ["Session 14"],
            "unapproved_numbers": [16, 18],
        },
        catalog,
        question_id="q-1",
    )
    assert mapping.status is GoldSourceStatus.MAPPED
    assert mapping.source_numbers == (8, 10, 12, 14)
    assert mapping.source_exchange_ids == catalog.resolve((8, 10, 12, 14))
    assert all("unapproved_numbers" not in path for path in mapping.matched_paths)


@pytest.mark.parametrize(
    ("raw", "raw_message_ids"),
    [
        ({"description": "No explicit source number here"}, (8,)),
        ({"conversation_references": ["chat_id: 8"]}, (8, 8)),
    ],
)
def test_gold_mapping_keeps_zero_or_ambiguous_sources_unmappable(
    raw: JsonObject,
    raw_message_ids: tuple[int, ...],
) -> None:
    catalog = SourceCatalog.from_conversation(_conversation(raw_message_ids))
    mapping = build_gold_source_mapping(raw, catalog, question_id="q-1")
    assert mapping.status is GoldSourceStatus.UNMAPPABLE
    assert mapping.source_exchange_ids == ()
    assert mapping.exclusion_reason is not None

    if mapping.source_numbers:
        with pytest.raises(SourceMappingError):
            catalog.resolve(mapping.source_numbers)


def test_manifest_hash_excludes_only_creation_time_and_hash() -> None:
    created_at = datetime(2026, 7, 17, 10, 0, tzinfo=UTC)
    first = _manifest(created_at)
    later = _manifest(created_at + timedelta(hours=1))

    assert first.content_hash == later.content_hash
    assert len(first.content_hash) == 64
    assert "api_key" not in ExperimentManifest.model_fields
    assert "headers" not in ExperimentManifest.model_fields
    assert "baseline" not in ExperimentManifest.model_fields
    assert "embedding_fingerprint" not in ExperimentManifest.model_fields
    with pytest.raises(ValidationError):
        first.run_id = "mutated"


def test_snapshot_contract_pins_the_fixed_dataset_hash(project_root: Path) -> None:
    settings = load_settings(project_root)
    manifest = PipelineRunManifest(
        run_id="run-1",
        stage=PipelineStage.KE_READY,
        parent_snapshot_id=None,
        code_commit="a" * 40,
        dataset_sha256="0" * 64,
        selected_directories=(4, 15, 17),
        ontology=OntologyRunIdentity(
            index=IndexIdentity(
                index_name="ontology",
                index_uuid="uuid-1",
                mapping_sha256="1" * 64,
            ),
            normalization_mode="bounded-best-effort",
        ),
        embedding_enabled=False,
        concurrency=settings.evaluation.concurrency,
        record_counts={},
    )

    with pytest.raises(PreflightCheckFailure, match="SnapshotContractMismatch"):
        validate_evaluation_snapshot_contract(manifest, (), settings)


@pytest.mark.parametrize(
    ("git_target", "failure_detail"),
    [
        ("objects", "state_repo:GitObjectStorageNotWritable"),
        ("active_ref", "state_repo:GitRefMetadataNotWritable"),
    ],
)
@pytest.mark.asyncio
async def test_state_repo_requires_writable_git_storage(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    git_target: str,
    failure_detail: str,
) -> None:
    config_root = tmp_path / "config-root"
    shutil.copytree(project_root / "config", config_root / "config")
    for name in (
        "KE_MEMORY_ES_API_KEY",
        "KE_MEMORY_ES_INDEX",
        "KE_MEMORY_ES_URL",
        "KE_MEMORY_JUDGE_API_KEY",
        "KE_MEMORY_WORK_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("GIT_OPTIONAL_LOCKS", raising=False)

    state_root = tmp_path / "state"
    state_root.mkdir()
    _git(state_root, "init", "--quiet", "--object-format=sha1")
    _git(state_root, "config", "user.name", "Preflight Test")
    _git(state_root, "config", "user.email", "preflight@example.invalid")
    _git(state_root, "config", "commit.gpgsign", "false")
    (state_root / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    _git(state_root, "add", "tracked.txt")
    _git(state_root, "commit", "--quiet", "-m", "initial")
    head = _git(state_root, "rev-parse", "HEAD")

    tracked_path = state_root / "tracked.txt"
    tracked_stat = tracked_path.stat()
    os.utime(
        tracked_path,
        ns=(tracked_stat.st_atime_ns, tracked_stat.st_mtime_ns + 5_000_000_000),
    )
    assert tracked_path.read_text(encoding="utf-8") == "tracked\n"

    active_ref = _git(state_root, "symbolic-ref", "-q", "HEAD")
    index_path = _resolved_git_path(state_root, "index")
    head_path = _resolved_git_path(state_root, "HEAD")
    ref_path = _resolved_git_path(state_root, active_ref)
    objects_directory = _resolved_git_path(state_root, "objects")
    ref_directory = ref_path.parent
    relevant_directories = tuple(
        dict.fromkeys((state_root, head_path.parent, objects_directory, ref_directory))
    )
    index_before = index_path.read_bytes()
    index_sha256_before = hashlib.sha256(index_before).hexdigest()
    ls_files_debug_before = _git(state_root, "ls-files", "--debug")
    head_file_before = head_path.read_bytes()
    ref_file_before = ref_path.read_bytes()
    directory_entries_before = {
        directory: tuple(sorted(item.name for item in directory.iterdir()))
        for directory in relevant_directories
    }

    if git_target == "objects":
        target_directory = objects_directory
    else:
        target_directory = ref_directory
    original_mode = stat.S_IMODE(target_directory.stat().st_mode)
    target_directory.chmod(original_mode & ~0o222)
    credential_git_environments: list[Mapping[str, str]] = []
    credential_command = (
        "git",
        "-C",
        str(config_root),
        "ls-files",
        "-z",
        "--",
        "src",
        "config",
        "tests",
    )
    real_subprocess_run = subprocess.run

    def recording_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        if args and args[0] == credential_command:
            credential_git_environments.append(dict(cast(Mapping[str, str], kwargs["env"])))
        return cast(subprocess.CompletedProcess[Any], real_subprocess_run(*args, **kwargs))

    try:
        assert os.access(state_root, os.W_OK)
        assert not os.access(target_directory, os.W_OK)
        with monkeypatch.context() as subprocess_patch:
            subprocess_patch.setattr(subprocess, "run", recording_run)
            report = await build_evaluation_preflight(
                config_root,
                state_root,
                "run-1",
                head,
            ).run()
    finally:
        target_directory.chmod(original_mode)

    [credential_git_environment] = credential_git_environments
    assert credential_git_environment.get("GIT_OPTIONAL_LOCKS") == "0"
    assert credential_git_environment.get("GIT_TERMINAL_PROMPT") == "0"
    state_check = next(item for item in report.checks if item.name == "state_repo")
    assert state_check.passed is False
    assert state_check.detail == failure_detail
    assert stat.S_IMODE(target_directory.stat().st_mode) == original_mode
    index_after = index_path.read_bytes()
    assert index_after == index_before
    assert hashlib.sha256(index_after).hexdigest() == index_sha256_before
    assert _git(state_root, "ls-files", "--debug") == ls_files_debug_before
    assert _git(state_root, "rev-parse", "HEAD") == head
    assert _git(state_root, "symbolic-ref", "-q", "HEAD") == active_ref
    assert head_path.read_bytes() == head_file_before
    assert ref_path.read_bytes() == ref_file_before
    assert {
        directory: tuple(sorted(item.name for item in directory.iterdir()))
        for directory in relevant_directories
    } == directory_entries_before


@pytest.mark.asyncio
async def test_preflight_reports_all_failures_without_ingestion_or_secret_details() -> None:
    ports = _FakePreflightPorts()
    ports.fail("judge_model", "state_repo", "ontology_identity")

    report = await EvaluationPreflight(ports).run()

    assert report.ready is False
    assert [item.name for item in report.failed] == [
        "judge_model",
        "ontology_identity",
        "state_repo",
    ]
    assert ports.ingest_calls == 0
    rendered = report.model_dump_json()
    assert "Authorization" not in rendered
    assert "provider-secret-body" not in rendered


@pytest.mark.asyncio
async def test_preflight_reports_missing_environment_names_without_values() -> None:
    class MissingEnvironmentPorts:
        async def check(self, name: str) -> str:
            if name == "environment":
                raise PreflightCheckFailure(
                    "environment:missing=KE_MEMORY_ES_API_KEY,KE_MEMORY_WORK_API_KEY"
                )
            return f"{name}:ok"

    report = await EvaluationPreflight(MissingEnvironmentPorts()).run()

    [failure] = report.failed
    assert failure.detail == ("environment:missing=KE_MEMORY_ES_API_KEY,KE_MEMORY_WORK_API_KEY")


def _conversation(raw_message_ids: Sequence[int]) -> Conversation:
    conversation_id = "conversation-1"
    session_id = "session-1"
    exchanges = tuple(
        Exchange(
            id=f"exchange-{ordinal}",
            session_id=session_id,
            user=Message(
                id=f"user-{ordinal}",
                role=MessageRole.USER,
                content=f"user {ordinal}",
                source_order=ordinal * 2,
                source_metadata={"raw_message_id": raw_message_id},
            ),
            assistant=Message(
                id=f"assistant-{ordinal}",
                role=MessageRole.ASSISTANT,
                content=f"assistant {ordinal}",
                source_order=ordinal * 2 + 1,
                source_metadata={"raw_message_id": 1_000 + ordinal},
            ),
            global_ordinal=ordinal * 2,
        )
        for ordinal, raw_message_id in enumerate(raw_message_ids)
    )
    return Conversation(
        id=conversation_id,
        sessions=(
            Session(
                id=session_id,
                conversation_id=conversation_id,
                exchanges=exchanges,
            ),
        ),
    )


def _manifest(created_at: datetime) -> ExperimentManifest:
    return ExperimentManifest(
        run_id="run-1",
        code_commit="a" * 40,
        spec_sha256="b" * 64,
        plan_sha256="c" * 64,
        ke_ready_snapshot_id="d" * 40,
        dataset_sha256="e" * 64,
        selected_directories=(4, 15, 17),
        expected_sessions=13,
        expected_exchanges=385,
        expected_questions=60,
        question_manifest_sha256="f" * 64,
        gold_mapping_sha256="0" * 64,
        ontology=OntologyRunIdentity(
            index=IndexIdentity(
                index_name="ontology",
                index_uuid="uuid-1",
                mapping_sha256="1" * 64,
            ),
            normalization_mode="bounded-best-effort",
        ),
        work_model="gpt-5.4",
        work_base_url="https://work.invalid/v1",
        judge_model="deepseek-v4-pro",
        judge_base_url="https://judge.invalid/v1",
        answer_prompt_sha256="2" * 64,
        judge_prompt_sha256="3" * 64,
        embedding_enabled=False,
        concurrency=EvaluationConcurrencySettings(
            turn_workers=8,
            session_workers=4,
            question_workers=8,
            judge_workers=8,
        ),
        created_at=created_at,
    )


class _FakePreflightPorts:
    def __init__(self) -> None:
        self._failures: set[str] = set()
        self.ingest_calls = 0

    def fail(self, *names: str) -> None:
        self._failures.update(names)

    async def check(self, name: str) -> str:
        if name in self._failures:
            if name == "state_repo":
                raise PreflightCheckFailure("state_repo:PermissionError")
            raise RuntimeError("Authorization provider-secret-body")
        return f"{name}:ok"


def _git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(root), *arguments),
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _resolved_git_path(root: Path, git_path: str) -> Path:
    path = Path(_git(root, "rev-parse", "--git-path", git_path))
    if not path.is_absolute():
        path = root / path
    return path.resolve(strict=True)
