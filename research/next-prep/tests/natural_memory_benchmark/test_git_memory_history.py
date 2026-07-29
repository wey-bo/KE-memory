from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from tools.natural_memory_benchmark.authoritative_memory import (
    L1MemoryUnitV2,
    ProducerIdentity,
    SourceBindingV2,
    canonical_sha256,
    make_evidence_span,
    make_memory_unit_revision,
    make_source_record_revision,
)
from tools.natural_memory_benchmark.git_memory_history import (
    GitMemoryHistoryError,
    GitMemoryHistoryRepository,
    HistoryArtifactReference,
    make_hard_purge_request,
    RepositoryState,
    make_checkpoint_manifest,
    make_history_artifact,
    make_turn_bundle_history_artifact,
)
from tools.natural_memory_benchmark.semantic_ir import Predicate, RoleBinding
from tools.natural_memory_benchmark.turn_bundle import (
    TurnSourceRevisionRef,
    make_turn_bundle_revision,
)
from tools.natural_memory_benchmark.io import canonical_json_bytes
from tools.natural_memory_benchmark.git_memory_history_cli import build_parser


def test_history_artifact_commits_canonical_payload_and_generated_path() -> None:
    payload = {
        "schema_version": "fixture-v1",
        "raw_text": "I prefer tea.",
        "valid_time": "2026-07-28",
    }

    artifact = make_history_artifact(
        artifact_kind="turn_bundle",
        logical_id="turn-bundle-1",
        revision_id="turn-bundle-revision-1",
        transaction_time="2026-07-28T00:00:02Z",
        payload=payload,
    )

    assert artifact.payload_sha256 == canonical_sha256(payload)
    assert artifact.path == (
        "records/turn_bundle/turn-bundle-1/turn-bundle-revision-1.json"
    )


def test_history_artifact_rejects_unsafe_path_identifiers() -> None:
    with pytest.raises(ValidationError, match="logical_id"):
        make_history_artifact(
            artifact_kind="turn_bundle",
            logical_id="../escape",
            revision_id="revision-1",
            transaction_time="2026-07-28T00:00:02Z",
            payload={"value": 1},
        )


def test_checkpoint_identity_is_order_independent_and_reference_explicit() -> None:
    first = make_history_artifact(
        artifact_kind="turn_bundle",
        logical_id="turn-bundle-1",
        revision_id="revision-1",
        transaction_time="2026-07-28T00:00:02Z",
        payload={"value": 1},
    )
    second = make_history_artifact(
        artifact_kind="l2_bundle",
        logical_id="task-1",
        revision_id="revision-1",
        transaction_time="2026-07-28T00:00:03Z",
        payload={"value": 2},
        references=[
            HistoryArtifactReference(
                relation="derived_from",
                artifact_kind="turn_bundle",
                logical_id="turn-bundle-1",
                revision_id="revision-1",
            )
        ],
    )

    forward = make_checkpoint_manifest(
        workspace_id="workspace-1",
        repository_epoch_id="epoch-1",
        sequence=1,
        previous_checkpoint_id=None,
        transaction_time="2026-07-28T00:00:04Z",
        artifacts=[first, second],
    )
    reverse = make_checkpoint_manifest(
        workspace_id="workspace-1",
        repository_epoch_id="epoch-1",
        sequence=1,
        previous_checkpoint_id=None,
        transaction_time="2026-07-28T00:00:04Z",
        artifacts=[second, first],
    )

    assert forward == reverse
    assert forward.checkpoint_id.startswith("checkpoint-")
    assert forward.artifact_paths == [first.path, second.path]
    assert forward.manifest_sha256 == canonical_sha256(
        forward.model_dump(mode="json", exclude={"manifest_sha256"})
    )


def test_bare_repository_initialization_creates_genesis_state(tmp_path) -> None:
    repo_path = tmp_path / "memory-history.git"

    repository = GitMemoryHistoryRepository.initialize(
        repo_path,
        workspace_id="workspace-1",
        created_at="2026-07-28T00:00:00Z",
    )

    assert (repo_path / "HEAD").is_file()
    assert not (repo_path / ".git").exists()
    metadata = repository.read_repository_metadata()
    state = repository.read_state()
    assert metadata.workspace_id == "workspace-1"
    assert metadata.repository_epoch_id.startswith("epoch-")
    assert state.sequence == 0
    assert state.checkpoint_id is None
    assert state.git_commit == repository.head_commit()
    assert repository.verify().status == "valid"


def test_checkpoint_commit_is_git_readable_and_retry_is_idempotent(tmp_path) -> None:
    repository = GitMemoryHistoryRepository.initialize(
        tmp_path / "memory-history.git",
        workspace_id="workspace-1",
        created_at="2026-07-28T00:00:00Z",
    )
    artifact = make_history_artifact(
        artifact_kind="turn_bundle",
        logical_id="turn-bundle-1",
        revision_id="revision-1",
        transaction_time="2026-07-28T00:00:02Z",
        payload={"raw_text": "Remember tea.", "l1": [{"predicate": "prefer"}]},
    )
    manifest = repository.make_checkpoint(
        artifacts=[artifact],
        transaction_time="2026-07-28T00:00:03Z",
    )
    genesis = repository.head_commit()

    receipt = repository.commit_checkpoint(
        manifest=manifest,
        artifacts=[artifact],
        expected_head=genesis,
    )
    retry = repository.commit_checkpoint(
        manifest=manifest,
        artifacts=[artifact],
        expected_head=genesis,
    )

    assert retry == receipt
    assert receipt.git_commit == repository.head_commit()
    assert repository.read_artifact(
        artifact_kind="turn_bundle",
        logical_id="turn-bundle-1",
        revision_id="revision-1",
    ) == artifact
    assert repository.read_state().checkpoint_id == manifest.checkpoint_id
    assert repository.verify().status == "valid"


def test_sequential_writes_reuse_the_verified_authoritative_head(
    tmp_path,
    monkeypatch,
) -> None:
    repository = GitMemoryHistoryRepository.initialize(
        tmp_path / "memory-history.git",
        workspace_id="workspace-1",
        created_at="2026-07-28T00:00:00Z",
    )
    original_verify = repository.verify
    verify_calls = 0

    def counting_verify():
        nonlocal verify_calls
        verify_calls += 1
        return original_verify()

    monkeypatch.setattr(repository, "verify", counting_verify)
    for index in range(2):
        artifact = _generic_artifact(
            logical_id=f"turn-bundle-{index}",
            revision_id="revision-1",
            value=index,
        )
        manifest = repository.make_checkpoint(
            artifacts=[artifact],
            transaction_time=f"2026-07-28T00:00:0{index + 3}Z",
        )
        repository.commit_checkpoint(
            manifest=manifest,
            artifacts=[artifact],
            expected_head=repository.head_commit(),
        )

    assert verify_calls == 0


def _closed_turn_bundle_fixture():
    user_source = make_source_record_revision(
        source_record_id="source-user",
        revision_number=1,
        previous_revision_id=None,
        artifact_revision_id="artifact-revision-test",
        source_ref="fixture=user",
        turn_id="turn-1",
        session_id="session-1",
        record_kind="message",
        text="I prefer tea.",
        resolver_id="git-history-test",
        resolver_version="1",
        transaction_time="2026-07-28T00:00:00Z",
        metadata={"speaker": "user"},
    )
    assistant_source = make_source_record_revision(
        source_record_id="source-assistant",
        revision_number=1,
        previous_revision_id=None,
        artifact_revision_id="artifact-revision-test",
        source_ref="fixture=assistant",
        turn_id="turn-1",
        session_id="session-1",
        record_kind="message",
        text="Noted.",
        resolver_id="git-history-test",
        resolver_version="1",
        transaction_time="2026-07-28T00:00:00Z",
        metadata={"speaker": "assistant"},
    )
    span = make_evidence_span(
        evidence_id="evidence-preference",
        source_revision=user_source,
        turn_id="turn-1",
        session_id="session-1",
        char_start=0,
        char_end=len(user_source.text),
        text=user_source.text,
    )
    unit = L1MemoryUnitV2(
        unit_id="l1-preference",
        kind="preference",
        predicate=Predicate(
            surface="prefer",
            sense="prefer-01",
            canonical_operator="prefers",
        ),
        roles=[
            RoleBinding(
                role="ARG0",
                entity_id="user",
                role_name="experiencer",
            )
        ],
        source=SourceBindingV2(
            speaker="user",
            source_status="user_reported",
            evidence_spans=[span],
        ),
    )
    unit_revision = make_memory_unit_revision(
        payload=unit,
        revision_number=1,
        previous_revision_id=None,
        revision_kind="create",
        transaction_time="2026-07-28T00:00:01Z",
        source_revision_ids=[user_source.source_revision_id],
        derived_from_revision_ids=[],
        producer=ProducerIdentity(
            workflow_run_id="git-history-test",
            producer_id="test-extractor",
            producer_version="1",
        ),
    )
    bundle = make_turn_bundle_revision(
        turn_bundle_id="turn-bundle-closed",
        revision_number=1,
        previous_revision_id=None,
        session_id="session-1",
        turn_id="turn-1",
        turn_index=0,
        source_records=[
            TurnSourceRevisionRef(
                ordinal=0,
                source_revision_id=user_source.source_revision_id,
                speaker="user",
            ),
            TurnSourceRevisionRef(
                ordinal=1,
                source_revision_id=assistant_source.source_revision_id,
                speaker="assistant",
            ),
        ],
        extraction_state="complete",
        l1_unit_revision_ids=[unit_revision.revision_id],
        no_memory_reason=None,
        failure_reason=None,
        extractor_id="test-extractor",
        extractor_version="1",
        transaction_time="2026-07-28T00:00:02Z",
    )
    return bundle, user_source, assistant_source, unit_revision


def test_closed_turn_bundle_artifact_recovers_exact_raw_and_l1_payload(tmp_path) -> None:
    bundle, user_source, assistant_source, unit_revision = (
        _closed_turn_bundle_fixture()
    )
    artifact = make_turn_bundle_history_artifact(
        bundle=bundle,
        source_revisions=[user_source, assistant_source],
        unit_revisions=[unit_revision],
    )
    repository = GitMemoryHistoryRepository.initialize(
        tmp_path / "memory-history.git",
        workspace_id="workspace-1",
        created_at="2026-07-28T00:00:00Z",
    )
    manifest = repository.make_checkpoint(
        artifacts=[artifact],
        transaction_time="2026-07-28T00:00:03Z",
    )
    repository.commit_checkpoint(
        manifest=manifest,
        artifacts=[artifact],
        expected_head=repository.head_commit(),
    )

    recovered = repository.read_artifact(
        artifact_kind="turn_bundle",
        logical_id=bundle.turn_bundle_id,
        revision_id=bundle.bundle_revision_id,
    )
    assert recovered.payload["source_record_revisions"][0]["text"] == "I prefer tea."
    assert recovered.payload["l1_unit_revisions"][0] == unit_revision.model_dump(
        mode="json"
    )


def test_turn_bundle_history_artifact_rejects_incomplete_revision_set() -> None:
    bundle, user_source, _, unit_revision = _closed_turn_bundle_fixture()

    with pytest.raises(ValueError, match="source revision set must exactly match"):
        make_turn_bundle_history_artifact(
            bundle=bundle,
            source_revisions=[user_source],
            unit_revisions=[unit_revision],
        )


def _generic_artifact(*, logical_id: str, revision_id: str, value: int):
    return make_history_artifact(
        artifact_kind="turn_bundle",
        logical_id=logical_id,
        revision_id=revision_id,
        transaction_time="2026-07-28T00:00:02Z",
        payload={"value": value},
    )


def test_two_checkpoints_form_a_contiguous_first_parent_chain(tmp_path) -> None:
    repository = GitMemoryHistoryRepository.initialize(
        tmp_path / "memory-history.git",
        workspace_id="workspace-1",
        created_at="2026-07-28T00:00:00Z",
    )
    first = _generic_artifact(
        logical_id="turn-bundle-1",
        revision_id="revision-1",
        value=1,
    )
    first_manifest = repository.make_checkpoint(
        artifacts=[first],
        transaction_time="2026-07-28T00:00:03Z",
    )
    repository.commit_checkpoint(
        manifest=first_manifest,
        artifacts=[first],
        expected_head=repository.head_commit(),
    )
    first_head = repository.head_commit()
    second = _generic_artifact(
        logical_id="turn-bundle-2",
        revision_id="revision-1",
        value=2,
    )
    second_manifest = repository.make_checkpoint(
        artifacts=[second],
        transaction_time="2026-07-28T00:00:04Z",
    )

    second_receipt = repository.commit_checkpoint(
        manifest=second_manifest,
        artifacts=[second],
        expected_head=first_head,
    )

    assert second_manifest.sequence == 2
    assert second_manifest.previous_checkpoint_id == first_manifest.checkpoint_id
    assert second_receipt.previous_git_commit == first_head
    assert repository.read_state().sequence == 2
    assert repository.verify().status == "valid"


def test_stale_writer_cannot_advance_authoritative_ref(tmp_path) -> None:
    repository = GitMemoryHistoryRepository.initialize(
        tmp_path / "memory-history.git",
        workspace_id="workspace-1",
        created_at="2026-07-28T00:00:00Z",
    )
    genesis = repository.head_commit()
    winner = _generic_artifact(
        logical_id="turn-bundle-winner",
        revision_id="revision-1",
        value=1,
    )
    stale = _generic_artifact(
        logical_id="turn-bundle-stale",
        revision_id="revision-1",
        value=2,
    )
    winner_manifest = repository.make_checkpoint(
        artifacts=[winner],
        transaction_time="2026-07-28T00:00:03Z",
    )
    stale_manifest = make_checkpoint_manifest(
        workspace_id="workspace-1",
        repository_epoch_id=repository.read_repository_metadata().repository_epoch_id,
        sequence=1,
        previous_checkpoint_id=None,
        transaction_time="2026-07-28T00:00:03Z",
        artifacts=[stale],
    )
    repository.commit_checkpoint(
        manifest=winner_manifest,
        artifacts=[winner],
        expected_head=genesis,
    )
    winner_head = repository.head_commit()

    with pytest.raises(GitMemoryHistoryError, match="stale expected head"):
        repository.commit_checkpoint(
            manifest=stale_manifest,
            artifacts=[stale],
            expected_head=genesis,
        )

    assert repository.head_commit() == winner_head


def test_checkpoint_rejects_immutable_artifact_collision(tmp_path) -> None:
    repository = GitMemoryHistoryRepository.initialize(
        tmp_path / "memory-history.git",
        workspace_id="workspace-1",
        created_at="2026-07-28T00:00:00Z",
    )
    original = _generic_artifact(
        logical_id="turn-bundle-1",
        revision_id="revision-1",
        value=1,
    )
    manifest = repository.make_checkpoint(
        artifacts=[original],
        transaction_time="2026-07-28T00:00:03Z",
    )
    repository.commit_checkpoint(
        manifest=manifest,
        artifacts=[original],
        expected_head=repository.head_commit(),
    )
    head = repository.head_commit()
    collision = _generic_artifact(
        logical_id="turn-bundle-1",
        revision_id="revision-1",
        value=999,
    )
    collision_manifest = repository.make_checkpoint(
        artifacts=[collision],
        transaction_time="2026-07-28T00:00:04Z",
    )

    with pytest.raises(GitMemoryHistoryError, match="immutable artifact collision"):
        repository.commit_checkpoint(
            manifest=collision_manifest,
            artifacts=[collision],
            expected_head=head,
        )

    assert repository.head_commit() == head


def test_verifier_detects_artifact_tampering_in_authoritative_tree(tmp_path) -> None:
    repository = GitMemoryHistoryRepository.initialize(
        tmp_path / "memory-history.git",
        workspace_id="workspace-1",
        created_at="2026-07-28T00:00:00Z",
    )
    artifact = _generic_artifact(
        logical_id="turn-bundle-1",
        revision_id="revision-1",
        value=1,
    )
    manifest = repository.make_checkpoint(
        artifacts=[artifact],
        transaction_time="2026-07-28T00:00:03Z",
    )
    repository.commit_checkpoint(
        manifest=manifest,
        artifacts=[artifact],
        expected_head=repository.head_commit(),
    )
    clean_head = repository.head_commit()
    tampered = artifact.model_dump(mode="json")
    tampered["payload"] = {"value": 999}
    tampered_commit = repository._create_commit(
        parent=clean_head,
        files={artifact.path: canonical_json_bytes(tampered)},
        transaction_time="2026-07-28T00:00:04Z",
        message="Tampered tree",
    )
    repository._update_ref(tampered_commit, expected_old=clean_head)

    report = repository.verify()

    assert report.status == "invalid"
    assert any("payload_sha256" in error for error in report.errors)


def test_verifier_rejects_checkpoint_sequence_gap(tmp_path) -> None:
    repository = GitMemoryHistoryRepository.initialize(
        tmp_path / "memory-history.git",
        workspace_id="workspace-1",
        created_at="2026-07-28T00:00:00Z",
    )
    genesis = repository.head_commit()
    metadata = repository.read_repository_metadata()
    artifact = _generic_artifact(
        logical_id="turn-bundle-gap",
        revision_id="revision-1",
        value=2,
    )
    manifest = make_checkpoint_manifest(
        workspace_id=metadata.workspace_id,
        repository_epoch_id=metadata.repository_epoch_id,
        sequence=2,
        previous_checkpoint_id="checkpoint-missing",
        transaction_time="2026-07-28T00:00:04Z",
        artifacts=[artifact],
    )
    state = RepositoryState(
        workspace_id=metadata.workspace_id,
        repository_epoch_id=metadata.repository_epoch_id,
        sequence=2,
        checkpoint_id=manifest.checkpoint_id,
        transaction_time=manifest.transaction_time,
        git_commit=None,
    )
    gap_commit = repository._create_commit(
        parent=genesis,
        files={
            artifact.path: canonical_json_bytes(artifact),
            repository._checkpoint_path(manifest): canonical_json_bytes(
                manifest
            ),
            "state/current.json": canonical_json_bytes(state),
        },
        transaction_time=manifest.transaction_time,
        message="Skipped checkpoint sequence",
    )
    repository._update_ref(gap_commit, expected_old=genesis)

    report = repository.verify()

    assert report.status == "invalid"

    next_artifact = _generic_artifact(
        logical_id="turn-bundle-after-gap",
        revision_id="revision-1",
        value=3,
    )
    next_manifest = repository.make_checkpoint(
        artifacts=[next_artifact],
        transaction_time="2026-07-28T00:00:05Z",
    )

    with pytest.raises(GitMemoryHistoryError, match="authoritative history"):
        repository.commit_checkpoint(
            manifest=next_manifest,
            artifacts=[next_artifact],
            expected_head=gap_commit,
        )

    assert repository.head_commit() == gap_commit


def test_tombstone_checkpoint_preserves_target_history_bytes(tmp_path) -> None:
    repository = GitMemoryHistoryRepository.initialize(
        tmp_path / "memory-history.git",
        workspace_id="workspace-1",
        created_at="2026-07-28T00:00:00Z",
    )
    target = _generic_artifact(
        logical_id="turn-bundle-forgotten",
        revision_id="revision-1",
        value=1,
    )
    first_manifest = repository.make_checkpoint(
        artifacts=[target],
        transaction_time="2026-07-28T00:00:03Z",
    )
    repository.commit_checkpoint(
        manifest=first_manifest,
        artifacts=[target],
        expected_head=repository.head_commit(),
    )
    target_bytes = repository._read_bytes_at(
        repository.head_commit(),
        target.path,
    )
    tombstone = make_history_artifact(
        artifact_kind="tombstone",
        logical_id="tombstone-turn-bundle-forgotten",
        revision_id="revision-1",
        transaction_time="2026-07-28T00:00:04Z",
        payload={
            "reason": "user_requested_forgetting",
            "authorized_by": "user-1",
        },
        references=[
            HistoryArtifactReference(
                relation="tombstones",
                artifact_kind="turn_bundle",
                logical_id=target.logical_id,
                revision_id=target.revision_id,
            )
        ],
    )
    second_manifest = repository.make_checkpoint(
        artifacts=[tombstone],
        transaction_time="2026-07-28T00:00:05Z",
    )
    repository.commit_checkpoint(
        manifest=second_manifest,
        artifacts=[tombstone],
        expected_head=repository.head_commit(),
    )

    assert repository._read_bytes_at(
        repository.head_commit(),
        target.path,
    ) == target_bytes
    assert repository.read_artifact(
        artifact_kind="tombstone",
        logical_id=tombstone.logical_id,
        revision_id=tombstone.revision_id,
    ) == tombstone
    assert repository.verify().status == "valid"


def _purge_source_repository(tmp_path):
    repository = GitMemoryHistoryRepository.initialize(
        tmp_path / "source-history.git",
        workspace_id="workspace-1",
        created_at="2026-07-28T00:00:00Z",
    )
    secret = _generic_artifact(
        logical_id="turn-bundle-secret",
        revision_id="revision-1",
        value=1,
    )
    dependent = make_history_artifact(
        artifact_kind="l2_bundle",
        logical_id="task-dependent",
        revision_id="revision-1",
        transaction_time="2026-07-28T00:00:02Z",
        payload={"summary": "derived task"},
        references=[
            HistoryArtifactReference(
                relation="derived_from",
                artifact_kind="turn_bundle",
                logical_id=secret.logical_id,
                revision_id=secret.revision_id,
            )
        ],
    )
    retained = _generic_artifact(
        logical_id="turn-bundle-retained",
        revision_id="revision-1",
        value=3,
    )
    manifest = repository.make_checkpoint(
        artifacts=[secret, dependent, retained],
        transaction_time="2026-07-28T00:00:03Z",
    )
    repository.commit_checkpoint(
        manifest=manifest,
        artifacts=[secret, dependent, retained],
        expected_head=repository.head_commit(),
    )
    return repository, secret, dependent, retained


def test_hard_purge_prepares_new_epoch_with_transitive_dependents_removed(
    tmp_path,
) -> None:
    source, secret, dependent, retained = _purge_source_repository(tmp_path)
    source_head = source.head_commit()
    source_epoch = source.read_repository_metadata().repository_epoch_id
    retained_bytes = source._read_bytes_at(source_head, retained.path)
    request = make_hard_purge_request(
        source_repository_epoch_id=source_epoch,
        source_head=source_head,
        target_logical_ids=[secret.logical_id],
        authorizer="user-1",
        reason="permanent deletion request",
        authorized_at="2026-07-28T00:00:04Z",
    )
    destination = tmp_path / "purged-history.git"

    result = source.prepare_hard_purge(destination, request=request)

    assert source.head_commit() == source_head
    purged = GitMemoryHistoryRepository(destination)
    assert purged.verify().status == "valid"
    assert purged.read_repository_metadata().repository_epoch_id != source_epoch
    assert purged._read_bytes_at(
        purged.head_commit(),
        retained.path,
    ) == retained_bytes
    assert purged.read_artifact(
        artifact_kind="turn_bundle",
        logical_id=retained.logical_id,
        revision_id=retained.revision_id,
    ) == retained
    with pytest.raises(GitMemoryHistoryError, match="missing canonical path"):
        purged.read_artifact(
            artifact_kind="turn_bundle",
            logical_id=secret.logical_id,
            revision_id=secret.revision_id,
        )
    with pytest.raises(GitMemoryHistoryError, match="missing canonical path"):
        purged.read_artifact(
            artifact_kind="l2_bundle",
            logical_id=dependent.logical_id,
            revision_id=dependent.revision_id,
        )
    purge_manifest = purged.read_artifact(
        artifact_kind="purge_manifest",
        logical_id=result.purge_manifest_logical_id,
        revision_id=result.purge_manifest_revision_id,
    )
    manifest_bytes = canonical_json_bytes(purge_manifest.payload)
    assert secret.logical_id.encode("utf-8") not in manifest_bytes
    assert dependent.logical_id.encode("utf-8") not in manifest_bytes
    assert result.removed_artifact_count == 2
    assert result.retained_artifact_count == 1


def test_hard_purge_rejects_stale_source_head_without_creating_destination(
    tmp_path,
) -> None:
    source, secret, _, _ = _purge_source_repository(tmp_path)
    request = make_hard_purge_request(
        source_repository_epoch_id=(
            source.read_repository_metadata().repository_epoch_id
        ),
        source_head="0" * 40,
        target_logical_ids=[secret.logical_id],
        authorizer="user-1",
        reason="permanent deletion request",
        authorized_at="2026-07-28T00:00:04Z",
    )
    destination = tmp_path / "purged-history.git"

    with pytest.raises(GitMemoryHistoryError, match="source head"):
        source.prepare_hard_purge(destination, request=request)

    assert not destination.exists()


def test_hard_purge_rejects_existing_destination(tmp_path) -> None:
    source, secret, _, _ = _purge_source_repository(tmp_path)
    request = make_hard_purge_request(
        source_repository_epoch_id=(
            source.read_repository_metadata().repository_epoch_id
        ),
        source_head=source.head_commit(),
        target_logical_ids=[secret.logical_id],
        authorizer="user-1",
        reason="permanent deletion request",
        authorized_at="2026-07-28T00:00:04Z",
    )
    destination = tmp_path / "purged-history.git"
    destination.mkdir()

    with pytest.raises(GitMemoryHistoryError, match="destination already exists"):
        source.prepare_hard_purge(destination, request=request)


def test_manual_cli_parser_exposes_only_isolated_history_commands() -> None:
    parser = build_parser()
    command_action = next(
        action for action in parser._actions if action.dest == "command"
    )

    assert set(command_action.choices) == {
        "init",
        "commit",
        "verify",
        "show-state",
        "prepare-hard-purge",
    }


def _run_history_cli(*args: str) -> dict[str, object]:
    workspace_root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.natural_memory_benchmark.git_memory_history_cli",
            *args,
        ],
        cwd=workspace_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_manual_cli_init_commit_verify_and_show_state(tmp_path) -> None:
    repo_path = tmp_path / "memory-history.git"
    init_result = _run_history_cli(
        "init",
        "--repo",
        str(repo_path),
        "--workspace-id",
        "workspace-1",
        "--created-at",
        "2026-07-28T00:00:00Z",
    )
    assert init_result["status"] == "initialized"

    artifact = _generic_artifact(
        logical_id="turn-bundle-cli",
        revision_id="revision-1",
        value=1,
    )
    artifact_file = tmp_path / "artifacts.json"
    artifact_file.write_bytes(
        canonical_json_bytes([artifact.model_dump(mode="json")])
    )
    commit_result = _run_history_cli(
        "commit",
        "--repo",
        str(repo_path),
        "--transaction-time",
        "2026-07-28T00:00:03Z",
        "--artifacts",
        str(artifact_file),
        "--expected-head",
        str(init_result["head_commit"]),
    )
    assert commit_result["sequence"] == 1

    verify_result = _run_history_cli(
        "verify",
        "--repo",
        str(repo_path),
    )
    state_result = _run_history_cli(
        "show-state",
        "--repo",
        str(repo_path),
    )
    assert verify_result["status"] == "valid"
    assert state_result["sequence"] == 1
    assert state_result["git_commit"] == commit_result["git_commit"]


def test_manual_cli_prepares_hard_purge_repository(tmp_path) -> None:
    source, secret, _, retained = _purge_source_repository(tmp_path)
    request = make_hard_purge_request(
        source_repository_epoch_id=(
            source.read_repository_metadata().repository_epoch_id
        ),
        source_head=source.head_commit(),
        target_logical_ids=[secret.logical_id],
        authorizer="user-1",
        reason="permanent deletion request",
        authorized_at="2026-07-28T00:00:04Z",
    )
    request_file = tmp_path / "purge-request.json"
    request_file.write_bytes(canonical_json_bytes(request))
    destination = tmp_path / "purged-history.git"

    result = _run_history_cli(
        "prepare-hard-purge",
        "--repo",
        str(source.repo_path),
        "--destination",
        str(destination),
        "--request",
        str(request_file),
    )

    purged = GitMemoryHistoryRepository(destination)
    assert result["removed_artifact_count"] == 2
    assert purged.verify().status == "valid"
    assert purged.read_artifact(
        artifact_kind="turn_bundle",
        logical_id=retained.logical_id,
        revision_id=retained.revision_id,
    ) == retained


def test_checkpoint_rejects_dangling_artifact_reference(tmp_path) -> None:
    repository = GitMemoryHistoryRepository.initialize(
        tmp_path / "memory-history.git",
        workspace_id="workspace-1",
        created_at="2026-07-28T00:00:00Z",
    )
    genesis = repository.head_commit()
    dangling = make_history_artifact(
        artifact_kind="l2_bundle",
        logical_id="task-dangling",
        revision_id="revision-1",
        transaction_time="2026-07-28T00:00:02Z",
        payload={"summary": "missing source"},
        references=[
            HistoryArtifactReference(
                relation="derived_from",
                artifact_kind="turn_bundle",
                logical_id="turn-bundle-missing",
                revision_id="revision-1",
            )
        ],
    )
    manifest = repository.make_checkpoint(
        artifacts=[dangling],
        transaction_time="2026-07-28T00:00:03Z",
    )

    with pytest.raises(GitMemoryHistoryError, match="dangling reference"):
        repository.commit_checkpoint(
            manifest=manifest,
            artifacts=[dangling],
            expected_head=genesis,
        )

    assert repository.head_commit() == genesis


def test_verifier_rejects_record_not_declared_by_checkpoint_manifest(
    tmp_path,
) -> None:
    repository = GitMemoryHistoryRepository.initialize(
        tmp_path / "memory-history.git",
        workspace_id="workspace-1",
        created_at="2026-07-28T00:00:00Z",
    )
    genesis = repository.head_commit()
    metadata = repository.read_repository_metadata()
    declared = _generic_artifact(
        logical_id="turn-bundle-declared",
        revision_id="revision-1",
        value=1,
    )
    extra = _generic_artifact(
        logical_id="turn-bundle-unmanifested",
        revision_id="revision-1",
        value=2,
    )
    manifest = make_checkpoint_manifest(
        workspace_id=metadata.workspace_id,
        repository_epoch_id=metadata.repository_epoch_id,
        sequence=1,
        previous_checkpoint_id=None,
        transaction_time="2026-07-28T00:00:03Z",
        artifacts=[declared],
    )
    state = RepositoryState(
        workspace_id=metadata.workspace_id,
        repository_epoch_id=metadata.repository_epoch_id,
        sequence=1,
        checkpoint_id=manifest.checkpoint_id,
        transaction_time=manifest.transaction_time,
        git_commit=None,
    )
    tampered_commit = repository._create_commit(
        parent=genesis,
        files={
            declared.path: canonical_json_bytes(declared),
            extra.path: canonical_json_bytes(extra),
            repository._checkpoint_path(manifest): canonical_json_bytes(
                manifest
            ),
            "state/current.json": canonical_json_bytes(state),
        },
        transaction_time=manifest.transaction_time,
        message="Unmanifested record",
    )
    repository._update_ref(tampered_commit, expected_old=genesis)

    report = repository.verify()

    assert report.status == "invalid"
    assert any("unmanifested" in error for error in report.errors)


def test_artifact_kind_contract_requires_authoritative_references() -> None:
    with pytest.raises(ValidationError, match="l2_bundle requires"):
        make_history_artifact(
            artifact_kind="l2_bundle",
            logical_id="task-without-provenance",
            revision_id="revision-1",
            transaction_time="2026-07-28T00:00:02Z",
            payload={"summary": "missing provenance"},
        )

    with pytest.raises(ValidationError, match="tombstone requires"):
        make_history_artifact(
            artifact_kind="tombstone",
            logical_id="tombstone-without-target",
            revision_id="revision-1",
            transaction_time="2026-07-28T00:00:02Z",
            payload={"reason": "missing target"},
        )

    with pytest.raises(ValidationError, match="derived_from references must target"):
        make_history_artifact(
            artifact_kind="l2_bundle",
            logical_id="task-derived-from-blob",
            revision_id="revision-1",
            transaction_time="2026-07-28T00:00:02Z",
            payload={"summary": "invalid authority chain"},
            references=[
                HistoryArtifactReference(
                    relation="derived_from",
                    artifact_kind="blob_ref",
                    logical_id="blob-1",
                    revision_id="revision-1",
                )
            ],
        )


def test_repository_rejects_logical_id_reuse_across_artifact_kinds(
    tmp_path,
) -> None:
    repository = GitMemoryHistoryRepository.initialize(
        tmp_path / "memory-history.git",
        workspace_id="workspace-1",
        created_at="2026-07-28T00:00:00Z",
    )
    turn_bundle = _generic_artifact(
        logical_id="shared-logical-id",
        revision_id="turn-revision-1",
        value=1,
    )
    l2_bundle = make_history_artifact(
        artifact_kind="l2_bundle",
        logical_id="shared-logical-id",
        revision_id="l2-revision-1",
        transaction_time="2026-07-28T00:00:03Z",
        payload={"summary": "ambiguous purge target"},
        references=[
            HistoryArtifactReference(
                relation="derived_from",
                artifact_kind="turn_bundle",
                logical_id=turn_bundle.logical_id,
                revision_id=turn_bundle.revision_id,
            )
        ],
    )
    manifest = repository.make_checkpoint(
        artifacts=[turn_bundle, l2_bundle],
        transaction_time="2026-07-28T00:00:04Z",
    )

    with pytest.raises(GitMemoryHistoryError, match="logical ID.*artifact kinds"):
        repository.commit_checkpoint(
            manifest=manifest,
            artifacts=[turn_bundle, l2_bundle],
            expected_head=repository.head_commit(),
        )


def _publish_manual_checkpoint_tree(
    repository,
    *,
    declared,
    extra_files,
):
    genesis = repository.head_commit()
    metadata = repository.read_repository_metadata()
    manifest = make_checkpoint_manifest(
        workspace_id=metadata.workspace_id,
        repository_epoch_id=metadata.repository_epoch_id,
        sequence=1,
        previous_checkpoint_id=None,
        transaction_time="2026-07-28T00:00:03Z",
        artifacts=[declared],
    )
    state = RepositoryState(
        workspace_id=metadata.workspace_id,
        repository_epoch_id=metadata.repository_epoch_id,
        sequence=1,
        checkpoint_id=manifest.checkpoint_id,
        transaction_time=manifest.transaction_time,
        git_commit=None,
    )
    commit = repository._create_commit(
        parent=genesis,
        files={
            declared.path: canonical_json_bytes(declared),
            repository._checkpoint_path(manifest): canonical_json_bytes(
                manifest
            ),
            "state/current.json": canonical_json_bytes(state),
            **extra_files,
        },
        transaction_time=manifest.transaction_time,
        message="Invalid record tree",
    )
    repository._update_ref(commit, expected_old=genesis)


def test_verifier_binds_artifact_to_actual_git_tree_path(tmp_path) -> None:
    repository = GitMemoryHistoryRepository.initialize(
        tmp_path / "memory-history.git",
        workspace_id="workspace-1",
        created_at="2026-07-28T00:00:00Z",
    )
    declared = _generic_artifact(
        logical_id="turn-bundle-declared",
        revision_id="revision-1",
        value=1,
    )
    _publish_manual_checkpoint_tree(
        repository,
        declared=declared,
        extra_files={
            "records/turn_bundle/alias/revision-copy.json": (
                canonical_json_bytes(declared)
            )
        },
    )

    report = repository.verify()

    assert report.status == "invalid"
    assert any("physical path" in error for error in report.errors)


def test_verifier_rejects_non_json_record_files(tmp_path) -> None:
    repository = GitMemoryHistoryRepository.initialize(
        tmp_path / "memory-history.git",
        workspace_id="workspace-1",
        created_at="2026-07-28T00:00:00Z",
    )
    declared = _generic_artifact(
        logical_id="turn-bundle-declared",
        revision_id="revision-1",
        value=1,
    )
    _publish_manual_checkpoint_tree(
        repository,
        declared=declared,
        extra_files={"records/hidden.bin": b"hidden bytes"},
    )

    report = repository.verify()

    assert report.status == "invalid"
    assert any("non-JSON record" in error for error in report.errors)


def test_verifier_rejects_paths_outside_the_canonical_tree(tmp_path) -> None:
    repository = GitMemoryHistoryRepository.initialize(
        tmp_path / "memory-history.git",
        workspace_id="workspace-1",
        created_at="2026-07-28T00:00:00Z",
    )
    declared = _generic_artifact(
        logical_id="turn-bundle-declared",
        revision_id="revision-1",
        value=1,
    )
    _publish_manual_checkpoint_tree(
        repository,
        declared=declared,
        extra_files={"hidden.bin": b"hidden bytes"},
    )

    report = repository.verify()

    assert report.status == "invalid"
    assert any("non-canonical tree path" in error for error in report.errors)


def test_verifier_rejects_unmanifested_checkpoint_namespace_entries(
    tmp_path,
) -> None:
    repository = GitMemoryHistoryRepository.initialize(
        tmp_path / "memory-history.git",
        workspace_id="workspace-1",
        created_at="2026-07-28T00:00:00Z",
    )
    declared = _generic_artifact(
        logical_id="turn-bundle-declared",
        revision_id="revision-1",
        value=1,
    )
    _publish_manual_checkpoint_tree(
        repository,
        declared=declared,
        extra_files={
            "checkpoints/00000000000000000099-checkpoint-hidden.json": (
                b'{"hidden":true}\n'
            )
        },
    )

    report = repository.verify()

    assert report.status == "invalid"
    assert any("unexpected checkpoint manifest" in error for error in report.errors)


def test_verifier_binds_checkpoint_manifest_to_physical_path(tmp_path) -> None:
    repository = GitMemoryHistoryRepository.initialize(
        tmp_path / "memory-history.git",
        workspace_id="workspace-1",
        created_at="2026-07-28T00:00:00Z",
    )
    genesis = repository.head_commit()
    metadata = repository.read_repository_metadata()
    declared = _generic_artifact(
        logical_id="turn-bundle-declared",
        revision_id="revision-1",
        value=1,
    )
    manifest = make_checkpoint_manifest(
        workspace_id=metadata.workspace_id,
        repository_epoch_id=metadata.repository_epoch_id,
        sequence=1,
        previous_checkpoint_id=None,
        transaction_time="2026-07-28T00:00:03Z",
        artifacts=[declared],
    )
    state = RepositoryState(
        workspace_id=metadata.workspace_id,
        repository_epoch_id=metadata.repository_epoch_id,
        sequence=1,
        checkpoint_id=manifest.checkpoint_id,
        transaction_time=manifest.transaction_time,
        git_commit=None,
    )
    wrong_path = "checkpoints/00000000000000000001-checkpoint-wrong.json"
    commit = repository._create_commit(
        parent=genesis,
        files={
            declared.path: canonical_json_bytes(declared),
            wrong_path: canonical_json_bytes(manifest),
            "state/current.json": canonical_json_bytes(state),
        },
        transaction_time=manifest.transaction_time,
        message="Wrong checkpoint manifest path",
    )
    repository._update_ref(commit, expected_old=genesis)

    report = repository.verify()

    assert report.status == "invalid"
    assert any("checkpoint physical path" in error for error in report.errors)


def test_verifier_rejects_prior_checkpoint_manifest_rewrite(tmp_path) -> None:
    repository = GitMemoryHistoryRepository.initialize(
        tmp_path / "memory-history.git",
        workspace_id="workspace-1",
        created_at="2026-07-28T00:00:00Z",
    )
    first = _generic_artifact(
        logical_id="turn-bundle-first",
        revision_id="revision-1",
        value=1,
    )
    first_manifest = repository.make_checkpoint(
        artifacts=[first],
        transaction_time="2026-07-28T00:00:03Z",
    )
    repository.commit_checkpoint(
        manifest=first_manifest,
        artifacts=[first],
        expected_head=repository.head_commit(),
    )
    first_head = repository.head_commit()
    second = _generic_artifact(
        logical_id="turn-bundle-second",
        revision_id="revision-1",
        value=2,
    )
    second_manifest = repository.make_checkpoint(
        artifacts=[second],
        transaction_time="2026-07-28T00:00:04Z",
    )
    metadata = repository.read_repository_metadata()
    state = RepositoryState(
        workspace_id=metadata.workspace_id,
        repository_epoch_id=metadata.repository_epoch_id,
        sequence=second_manifest.sequence,
        checkpoint_id=second_manifest.checkpoint_id,
        transaction_time=second_manifest.transaction_time,
        git_commit=None,
    )
    tampered_commit = repository._create_commit(
        parent=first_head,
        files={
            second.path: canonical_json_bytes(second),
            repository._checkpoint_path(second_manifest): canonical_json_bytes(
                second_manifest
            ),
            repository._checkpoint_path(first_manifest): b'{"tampered":true}\n',
            "state/current.json": canonical_json_bytes(state),
        },
        transaction_time=second_manifest.transaction_time,
        message="Rewrite prior checkpoint manifest",
    )
    repository._update_ref(tampered_commit, expected_old=first_head)

    report = repository.verify()

    assert report.status == "invalid"
    assert any("checkpoint manifest changed" in error for error in report.errors)


def test_late_byte_identical_retry_finds_published_checkpoint_in_history(
    tmp_path,
) -> None:
    repository = GitMemoryHistoryRepository.initialize(
        tmp_path / "memory-history.git",
        workspace_id="workspace-1",
        created_at="2026-07-28T00:00:00Z",
    )
    genesis = repository.head_commit()
    first = _generic_artifact(
        logical_id="turn-bundle-first",
        revision_id="revision-1",
        value=1,
    )
    first_manifest = repository.make_checkpoint(
        artifacts=[first],
        transaction_time="2026-07-28T00:00:03Z",
    )
    first_receipt = repository.commit_checkpoint(
        manifest=first_manifest,
        artifacts=[first],
        expected_head=genesis,
    )
    second = _generic_artifact(
        logical_id="turn-bundle-second",
        revision_id="revision-1",
        value=2,
    )
    second_manifest = repository.make_checkpoint(
        artifacts=[second],
        transaction_time="2026-07-28T00:00:04Z",
    )
    repository.commit_checkpoint(
        manifest=second_manifest,
        artifacts=[second],
        expected_head=repository.head_commit(),
    )
    current_head = repository.head_commit()

    retry = repository.commit_checkpoint(
        manifest=first_manifest,
        artifacts=[first],
        expected_head=genesis,
    )

    assert retry == first_receipt
    assert repository.head_commit() == current_head

    with pytest.raises(GitMemoryHistoryError, match="artifact set"):
        repository.commit_checkpoint(
            manifest=first_manifest,
            artifacts=[],
            expected_head=genesis,
        )


def test_hard_purge_rejects_destination_inside_source_repository(
    tmp_path,
) -> None:
    source, secret, _, _ = _purge_source_repository(tmp_path)
    request = make_hard_purge_request(
        source_repository_epoch_id=(
            source.read_repository_metadata().repository_epoch_id
        ),
        source_head=source.head_commit(),
        target_logical_ids=[secret.logical_id],
        authorizer="user-1",
        reason="permanent deletion request",
        authorized_at="2026-07-28T00:00:04Z",
    )
    destination = source.repo_path / "nested-purged.git"

    with pytest.raises(GitMemoryHistoryError, match="inside source repository"):
        source.prepare_hard_purge(destination, request=request)

    assert not destination.exists()


def test_failed_hard_purge_does_not_claim_final_destination(tmp_path) -> None:
    source, secret, _, _ = _purge_source_repository(tmp_path)
    request = make_hard_purge_request(
        source_repository_epoch_id=(
            source.read_repository_metadata().repository_epoch_id
        ),
        source_head=source.head_commit(),
        target_logical_ids=[secret.logical_id],
        authorizer="user-1",
        reason="permanent deletion request",
        authorized_at="not-a-git-date",
    )
    destination = tmp_path / "purged-history.git"

    with pytest.raises(GitMemoryHistoryError):
        source.prepare_hard_purge(destination, request=request)

    assert not destination.exists()


def test_failed_post_move_purge_verification_releases_destination(
    tmp_path,
    monkeypatch,
) -> None:
    source, secret, _, _ = _purge_source_repository(tmp_path)
    request = make_hard_purge_request(
        source_repository_epoch_id=(
            source.read_repository_metadata().repository_epoch_id
        ),
        source_head=source.head_commit(),
        target_logical_ids=[secret.logical_id],
        authorizer="user-1",
        reason="permanent deletion request",
        authorized_at="2026-07-28T00:00:04Z",
    )
    destination = (tmp_path / "purged-history.git").resolve()
    original_verify = GitMemoryHistoryRepository.verify

    def fail_only_after_move(repository):
        report = original_verify(repository)
        if repository.repo_path.resolve() == destination:
            return report.model_copy(
                update={
                    "status": "invalid",
                    "errors": ["forced post-move verification failure"],
                }
            )
        return report

    monkeypatch.setattr(GitMemoryHistoryRepository, "verify", fail_only_after_move)

    with pytest.raises(GitMemoryHistoryError, match="moved purged repository"):
        source.prepare_hard_purge(destination, request=request)

    assert not destination.exists()


def _history_cli_completed(*args: str):
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.natural_memory_benchmark.git_memory_history_cli",
            *args,
        ],
        cwd=Path(__file__).resolve().parents[2],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )


def test_manual_cli_verify_invalid_uses_exit_one_and_json_stdout(
    tmp_path,
) -> None:
    repository = GitMemoryHistoryRepository.initialize(
        tmp_path / "memory-history.git",
        workspace_id="workspace-1",
        created_at="2026-07-28T00:00:00Z",
    )
    declared = _generic_artifact(
        logical_id="turn-bundle-declared",
        revision_id="revision-1",
        value=1,
    )
    _publish_manual_checkpoint_tree(
        repository,
        declared=declared,
        extra_files={"records/hidden.bin": b"hidden bytes"},
    )

    completed = _history_cli_completed(
        "verify",
        "--repo",
        str(repository.repo_path),
    )

    assert completed.returncode == 1
    assert completed.stderr == ""
    assert json.loads(completed.stdout)["status"] == "invalid"


def test_manual_cli_operational_error_uses_exit_two_and_json_stderr(
    tmp_path,
) -> None:
    completed = _history_cli_completed(
        "show-state",
        "--repo",
        str(tmp_path / "missing.git"),
    )

    assert completed.returncode == 2
    assert completed.stdout == ""
    payload = json.loads(completed.stderr)
    assert payload["status"] == "error"
    assert payload["error_type"] == "GitMemoryHistoryError"
