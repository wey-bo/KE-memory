from __future__ import annotations

from pathlib import Path

import pytest

from ke_memory_demo.core.json import JsonObject, canonical_json
from ke_memory_demo.history import (
    GitMemoryHistoryError,
    GitMemoryHistoryRepository,
    HistoryArtifactReference,
    make_checkpoint_manifest,
    make_history_artifact,
)


def test_history_repository_initializes_genesis_authoritative_ref(tmp_path: Path) -> None:
    repository = GitMemoryHistoryRepository.initialize(
        tmp_path / "memory-history.git",
        workspace_id="workspace-1",
        created_at="2026-07-29T00:00:00Z",
    )

    metadata = repository.read_repository_metadata()
    state = repository.read_state()

    assert metadata.workspace_id == "workspace-1"
    assert metadata.repository_epoch_id.startswith("epoch-")
    assert state.sequence == 0
    assert state.checkpoint_id is None
    assert state.git_commit == repository.head_commit()
    assert repository.verify().status == "valid"


def test_history_artifact_uses_canonical_path_and_payload_hash() -> None:
    payload: JsonObject = {"raw_text": "I prefer tea.", "valid_time": "2026-07-29"}

    artifact = make_history_artifact(
        artifact_kind="turn_bundle",
        logical_id="turn-bundle-1",
        revision_id="revision-1",
        transaction_time="2026-07-29T00:00:01Z",
        payload=payload,
    )

    assert artifact.path == "records/turn_bundle/turn-bundle-1/revision-1.json"
    assert artifact.payload_sha256 == repository_sha256(payload)


def test_checkpoint_commit_is_git_readable_and_idempotent(tmp_path: Path) -> None:
    repository = GitMemoryHistoryRepository.initialize(
        tmp_path / "memory-history.git",
        workspace_id="workspace-1",
        created_at="2026-07-29T00:00:00Z",
    )
    artifact = make_history_artifact(
        artifact_kind="turn_bundle",
        logical_id="turn-bundle-1",
        revision_id="revision-1",
        transaction_time="2026-07-29T00:00:01Z",
        payload={"raw_text": "Remember tea.", "l1": [{"predicate": "prefer"}]},
    )
    manifest = repository.make_checkpoint(
        artifacts=[artifact],
        transaction_time="2026-07-29T00:00:02Z",
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


def test_checkpoint_requires_authoritative_head_match(tmp_path: Path) -> None:
    repository = GitMemoryHistoryRepository.initialize(
        tmp_path / "memory-history.git",
        workspace_id="workspace-1",
        created_at="2026-07-29T00:00:00Z",
    )
    genesis = repository.head_commit()
    first = make_history_artifact(
        artifact_kind="turn_bundle",
        logical_id="turn-bundle-winner",
        revision_id="revision-1",
        transaction_time="2026-07-29T00:00:01Z",
        payload={"value": 1},
    )
    stale = make_history_artifact(
        artifact_kind="turn_bundle",
        logical_id="turn-bundle-stale",
        revision_id="revision-1",
        transaction_time="2026-07-29T00:00:01Z",
        payload={"value": 2},
    )

    repository.commit_checkpoint(
        manifest=repository.make_checkpoint(
            artifacts=[first],
            transaction_time="2026-07-29T00:00:02Z",
        ),
        artifacts=[first],
        expected_head=genesis,
    )
    winning_head = repository.head_commit()
    stale_manifest = make_checkpoint_manifest(
        workspace_id="workspace-1",
        repository_epoch_id=repository.read_repository_metadata().repository_epoch_id,
        sequence=1,
        previous_checkpoint_id=None,
        transaction_time="2026-07-29T00:00:02Z",
        artifacts=[stale],
    )

    with pytest.raises(GitMemoryHistoryError, match="stale expected head"):
        repository.commit_checkpoint(
            manifest=stale_manifest,
            artifacts=[stale],
            expected_head=genesis,
        )

    assert repository.head_commit() == winning_head


def test_checkpoint_rejects_immutable_artifact_collision(tmp_path: Path) -> None:
    repository = GitMemoryHistoryRepository.initialize(
        tmp_path / "memory-history.git",
        workspace_id="workspace-1",
        created_at="2026-07-29T00:00:00Z",
    )
    original = make_history_artifact(
        artifact_kind="turn_bundle",
        logical_id="turn-bundle-1",
        revision_id="revision-1",
        transaction_time="2026-07-29T00:00:01Z",
        payload={"value": 1},
    )
    repository.commit_checkpoint(
        manifest=repository.make_checkpoint(
            artifacts=[original],
            transaction_time="2026-07-29T00:00:02Z",
        ),
        artifacts=[original],
        expected_head=repository.head_commit(),
    )
    original_head = repository.head_commit()
    collision = make_history_artifact(
        artifact_kind="turn_bundle",
        logical_id="turn-bundle-1",
        revision_id="revision-1",
        transaction_time="2026-07-29T00:00:03Z",
        payload={"value": 999},
    )

    with pytest.raises(GitMemoryHistoryError, match="immutable artifact collision"):
        repository.commit_checkpoint(
            manifest=repository.make_checkpoint(
                artifacts=[collision],
                transaction_time="2026-07-29T00:00:04Z",
            ),
            artifacts=[collision],
            expected_head=original_head,
        )

    assert repository.head_commit() == original_head


def test_l2_artifacts_must_reference_a_direct_turn_bundle() -> None:
    with pytest.raises(ValueError, match="direct derived_from turn_bundle"):
        make_history_artifact(
            artifact_kind="l2_bundle",
            logical_id="session-summary-1",
            revision_id="revision-1",
            transaction_time="2026-07-29T00:00:01Z",
            payload={"summary": "The user prefers tea."},
            references=[
                HistoryArtifactReference(
                    relation="derived_from",
                    artifact_kind="l2_bundle",
                    logical_id="higher-summary-1",
                    revision_id="revision-1",
                )
            ],
        )


def repository_sha256(value: JsonObject) -> str:
    import hashlib

    return hashlib.sha256(canonical_json(value)).hexdigest()
