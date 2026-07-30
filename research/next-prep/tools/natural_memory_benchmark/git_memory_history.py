from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from .authoritative_memory import (
    MemoryUnitRevision,
    SourceRecordRevision,
    StrictModel,
    canonical_sha256,
)
from .io import canonical_json_bytes
from .turn_bundle import TurnBundleRevision, validate_turn_bundle_closure


ArtifactKind = Literal[
    "turn_bundle",
    "l2_bundle",
    "tombstone",
    "blob_ref",
    "purge_manifest",
]
ReferenceRelation = Literal[
    "source",
    "derived_from",
    "supersedes",
    "conflicts_with",
    "tombstones",
    "blob",
]
SAFE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$"
ARTIFACT_KIND_ORDER = {
    "turn_bundle": 0,
    "l2_bundle": 1,
    "tombstone": 2,
    "blob_ref": 3,
    "purge_manifest": 4,
}


def _reference_key(reference: "HistoryArtifactReference") -> tuple[object, ...]:
    return (
        reference.relation,
        ARTIFACT_KIND_ORDER[reference.artifact_kind],
        reference.logical_id,
        reference.revision_id or "",
    )


def _artifact_key(artifact: "HistoryArtifact") -> tuple[object, ...]:
    return (
        ARTIFACT_KIND_ORDER[artifact.artifact_kind],
        artifact.logical_id,
        artifact.revision_id,
    )


def _artifact_path(
    artifact_kind: ArtifactKind,
    logical_id: str,
    revision_id: str,
) -> str:
    return f"records/{artifact_kind}/{logical_id}/{revision_id}.json"


class HistoryArtifactReference(StrictModel):
    relation: ReferenceRelation
    artifact_kind: ArtifactKind
    logical_id: str = Field(min_length=1, pattern=SAFE_ID_PATTERN)
    revision_id: str | None = Field(default=None, min_length=1, pattern=SAFE_ID_PATTERN)


class HistoryArtifact(StrictModel):
    schema_version: Literal["git-memory-artifact-v1"] = "git-memory-artifact-v1"
    artifact_kind: ArtifactKind
    logical_id: str = Field(min_length=1, pattern=SAFE_ID_PATTERN)
    revision_id: str = Field(min_length=1, pattern=SAFE_ID_PATTERN)
    transaction_time: str = Field(min_length=1)
    payload: dict[str, Any]
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    references: list[HistoryArtifactReference] = Field(default_factory=list)
    path: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_contract(self) -> "HistoryArtifact":
        expected_path = _artifact_path(
            self.artifact_kind,
            self.logical_id,
            self.revision_id,
        )
        if self.path != expected_path:
            raise ValueError("artifact path does not match the generated canonical path")
        if self.payload_sha256 != canonical_sha256(self.payload):
            raise ValueError("payload_sha256 does not match the canonical payload")
        ordered = sorted(self.references, key=_reference_key)
        if self.references != ordered:
            raise ValueError("artifact references must be in canonical order")
        reference_keys = [_reference_key(item) for item in self.references]
        if len(reference_keys) != len(set(reference_keys)):
            raise ValueError("artifact references must be unique")
        relations = {item.relation for item in self.references}
        if self.artifact_kind == "l2_bundle":
            derived_from = [
                item for item in self.references if item.relation == "derived_from"
            ]
            if not derived_from:
                raise ValueError(
                    "l2_bundle requires at least one derived_from reference"
                )
            if any(
                item.artifact_kind not in {"turn_bundle", "l2_bundle"}
                for item in derived_from
            ):
                raise ValueError(
                    "l2_bundle derived_from references must target turn_bundle "
                    "or l2_bundle artifacts"
                )
            if not any(
                item.artifact_kind == "turn_bundle" for item in derived_from
            ):
                raise ValueError(
                    "l2_bundle requires a direct derived_from turn_bundle reference"
                )
        if self.artifact_kind == "tombstone" and (
            not self.references or relations != {"tombstones"}
        ):
            raise ValueError(
                "tombstone requires one or more tombstones references"
            )
        if self.artifact_kind == "purge_manifest" and self.references:
            raise ValueError("purge_manifest cannot contain artifact references")
        return self


class CheckpointArtifactDescriptor(StrictModel):
    artifact_kind: ArtifactKind
    logical_id: str = Field(min_length=1, pattern=SAFE_ID_PATTERN)
    revision_id: str = Field(min_length=1, pattern=SAFE_ID_PATTERN)
    transaction_time: str = Field(min_length=1)
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    references: list[HistoryArtifactReference] = Field(default_factory=list)
    path: str = Field(min_length=1)

    @classmethod
    def from_artifact(cls, artifact: HistoryArtifact) -> "CheckpointArtifactDescriptor":
        return cls(
            artifact_kind=artifact.artifact_kind,
            logical_id=artifact.logical_id,
            revision_id=artifact.revision_id,
            transaction_time=artifact.transaction_time,
            payload_sha256=artifact.payload_sha256,
            references=artifact.references,
            path=artifact.path,
        )


class CheckpointManifest(StrictModel):
    schema_version: Literal["git-memory-checkpoint-v1"] = "git-memory-checkpoint-v1"
    workspace_id: str = Field(min_length=1, pattern=SAFE_ID_PATTERN)
    repository_epoch_id: str = Field(min_length=1, pattern=SAFE_ID_PATTERN)
    sequence: int = Field(ge=1)
    previous_checkpoint_id: str | None = Field(
        default=None,
        min_length=1,
        pattern=SAFE_ID_PATTERN,
    )
    transaction_time: str = Field(min_length=1)
    artifacts: list[CheckpointArtifactDescriptor] = Field(min_length=1)
    artifact_paths: list[str] = Field(min_length=1)
    checkpoint_id: str = Field(min_length=1, pattern=SAFE_ID_PATTERN)
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_contract(self) -> "CheckpointManifest":
        if self.sequence == 1 and self.previous_checkpoint_id is not None:
            raise ValueError("checkpoint sequence 1 cannot have a previous checkpoint")
        if self.sequence > 1 and self.previous_checkpoint_id is None:
            raise ValueError("later checkpoints require a previous checkpoint")
        descriptor_keys = [
            (
                ARTIFACT_KIND_ORDER[item.artifact_kind],
                item.logical_id,
                item.revision_id,
            )
            for item in self.artifacts
        ]
        if descriptor_keys != sorted(descriptor_keys):
            raise ValueError("checkpoint artifacts must be in canonical order")
        if len(descriptor_keys) != len(set(descriptor_keys)):
            raise ValueError("checkpoint artifacts must be unique")
        if self.artifact_paths != [item.path for item in self.artifacts]:
            raise ValueError("artifact_paths must match the canonical descriptors")

        identity = self.model_dump(
            mode="json",
            exclude={"checkpoint_id", "manifest_sha256"},
        )
        expected_checkpoint_id = f"checkpoint-{canonical_sha256(identity)[:24]}"
        if self.checkpoint_id != expected_checkpoint_id:
            raise ValueError("checkpoint_id does not match the canonical manifest identity")
        manifest = self.model_dump(mode="json", exclude={"manifest_sha256"})
        if self.manifest_sha256 != canonical_sha256(manifest):
            raise ValueError("manifest_sha256 does not match the canonical manifest")
        return self


class RepositoryMetadata(StrictModel):
    schema_version: Literal["git-memory-repository-v1"] = (
        "git-memory-repository-v1"
    )
    workspace_id: str = Field(min_length=1, pattern=SAFE_ID_PATTERN)
    repository_epoch_id: str = Field(min_length=1, pattern=SAFE_ID_PATTERN)
    created_at: str = Field(min_length=1)
    authoritative_ref: Literal["refs/heads/authoritative"] = (
        "refs/heads/authoritative"
    )
    parent_repository_epoch_id: str | None = Field(
        default=None,
        min_length=1,
        pattern=SAFE_ID_PATTERN,
    )
    purge_request_id: str | None = Field(
        default=None,
        min_length=1,
        pattern=SAFE_ID_PATTERN,
    )


class RepositoryState(StrictModel):
    schema_version: Literal["git-memory-state-v1"] = "git-memory-state-v1"
    workspace_id: str = Field(min_length=1, pattern=SAFE_ID_PATTERN)
    repository_epoch_id: str = Field(min_length=1, pattern=SAFE_ID_PATTERN)
    sequence: int = Field(ge=0)
    checkpoint_id: str | None = Field(
        default=None,
        min_length=1,
        pattern=SAFE_ID_PATTERN,
    )
    transaction_time: str = Field(min_length=1)
    git_commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{40,64}$")

    @model_validator(mode="after")
    def validate_contract(self) -> "RepositoryState":
        if self.sequence == 0 and self.checkpoint_id is not None:
            raise ValueError("genesis state cannot name a checkpoint")
        if self.sequence > 0 and self.checkpoint_id is None:
            raise ValueError("checkpoint state requires a checkpoint_id")
        return self


class CheckpointReceipt(StrictModel):
    schema_version: Literal["git-memory-checkpoint-receipt-v1"] = (
        "git-memory-checkpoint-receipt-v1"
    )
    checkpoint_id: str = Field(min_length=1, pattern=SAFE_ID_PATTERN)
    sequence: int = Field(ge=1)
    git_commit: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    previous_git_commit: str = Field(pattern=r"^[0-9a-f]{40,64}$")


class VerificationReport(StrictModel):
    schema_version: Literal["git-memory-verification-v1"] = (
        "git-memory-verification-v1"
    )
    status: Literal["valid", "invalid"]
    head_commit: str | None = None
    sequence: int | None = Field(default=None, ge=0)
    checked_artifacts: int = Field(default=0, ge=0)
    errors: list[str] = Field(default_factory=list)


class GitMemoryHistoryError(RuntimeError):
    pass



class HardPurgeRequest(StrictModel):
    schema_version: Literal["git-memory-hard-purge-request-v1"] = (
        "git-memory-hard-purge-request-v1"
    )
    request_id: str = Field(min_length=1, pattern=SAFE_ID_PATTERN)
    source_repository_epoch_id: str = Field(
        min_length=1,
        pattern=SAFE_ID_PATTERN,
    )
    source_head: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    target_logical_ids: list[str] = Field(min_length=1)
    authorizer: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    authorized_at: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_contract(self) -> "HardPurgeRequest":
        if any(
            not item or not re.fullmatch(SAFE_ID_PATTERN, item)
            for item in self.target_logical_ids
        ):
            raise ValueError("target logical IDs must be path-safe")
        if self.target_logical_ids != sorted(set(self.target_logical_ids)):
            raise ValueError("target logical IDs must be sorted and unique")
        identity = self.model_dump(mode="json", exclude={"request_id"})
        expected = f"purge-request-{canonical_sha256(identity)[:24]}"
        if self.request_id != expected:
            raise ValueError("request_id does not match hard-purge request identity")
        return self


class HardPurgeResult(StrictModel):
    schema_version: Literal["git-memory-hard-purge-result-v1"] = (
        "git-memory-hard-purge-result-v1"
    )
    request_id: str = Field(min_length=1, pattern=SAFE_ID_PATTERN)
    source_repository_epoch_id: str = Field(
        min_length=1,
        pattern=SAFE_ID_PATTERN,
    )
    source_head: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    destination_repository_epoch_id: str = Field(
        min_length=1,
        pattern=SAFE_ID_PATTERN,
    )
    destination_head: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    destination_repo_path: str = Field(min_length=1)
    removed_artifact_count: int = Field(ge=1)
    retained_artifact_count: int = Field(ge=0)
    purge_manifest_logical_id: str = Field(
        min_length=1,
        pattern=SAFE_ID_PATTERN,
    )
    purge_manifest_revision_id: str = Field(
        min_length=1,
        pattern=SAFE_ID_PATTERN,
    )


def make_hard_purge_request(
    *,
    source_repository_epoch_id: str,
    source_head: str,
    target_logical_ids: list[str],
    authorizer: str,
    reason: str,
    authorized_at: str,
) -> HardPurgeRequest:
    identity = {
        "schema_version": "git-memory-hard-purge-request-v1",
        "source_repository_epoch_id": source_repository_epoch_id,
        "source_head": source_head,
        "target_logical_ids": sorted(set(target_logical_ids)),
        "authorizer": authorizer,
        "reason": reason,
        "authorized_at": authorized_at,
    }
    return HardPurgeRequest(
        request_id=f"purge-request-{canonical_sha256(identity)[:24]}",
        **identity,
    )

def make_history_artifact(
    *,
    artifact_kind: ArtifactKind,
    logical_id: str,
    revision_id: str,
    transaction_time: str,
    payload: dict[str, Any],
    references: list[HistoryArtifactReference] | None = None,
) -> HistoryArtifact:
    ordered_references = sorted(references or [], key=_reference_key)
    return HistoryArtifact(
        artifact_kind=artifact_kind,
        logical_id=logical_id,
        revision_id=revision_id,
        transaction_time=transaction_time,
        payload=payload,
        payload_sha256=canonical_sha256(payload),
        references=ordered_references,
        path=_artifact_path(artifact_kind, logical_id, revision_id),
    )


def make_checkpoint_manifest(
    *,
    workspace_id: str,
    repository_epoch_id: str,
    sequence: int,
    previous_checkpoint_id: str | None,
    transaction_time: str,
    artifacts: list[HistoryArtifact],
) -> CheckpointManifest:
    ordered_artifacts = sorted(artifacts, key=_artifact_key)
    descriptors = [
        CheckpointArtifactDescriptor.from_artifact(item)
        for item in ordered_artifacts
    ]
    identity = {
        "schema_version": "git-memory-checkpoint-v1",
        "workspace_id": workspace_id,
        "repository_epoch_id": repository_epoch_id,
        "sequence": sequence,
        "previous_checkpoint_id": previous_checkpoint_id,
        "transaction_time": transaction_time,
        "artifacts": [item.model_dump(mode="json") for item in descriptors],
        "artifact_paths": [item.path for item in descriptors],
    }
    checkpoint_id = f"checkpoint-{canonical_sha256(identity)[:24]}"
    manifest = {**identity, "checkpoint_id": checkpoint_id}
    return CheckpointManifest(
        **manifest,
        manifest_sha256=canonical_sha256(manifest),
    )


def make_turn_bundle_history_artifact(
    *,
    bundle: TurnBundleRevision,
    source_revisions: list[SourceRecordRevision],
    unit_revisions: list[MemoryUnitRevision],
) -> HistoryArtifact:
    source_ids = [item.source_revision_id for item in source_revisions]
    unit_ids = [item.revision_id for item in unit_revisions]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("source revisions must have unique identities")
    if len(unit_ids) != len(set(unit_ids)):
        raise ValueError("unit revisions must have unique identities")

    expected_source_ids = [
        item.source_revision_id for item in bundle.source_records
    ]
    if set(source_ids) != set(expected_source_ids):
        raise ValueError(
            "source revision set must exactly match the turn bundle references"
        )
    if set(unit_ids) != set(bundle.l1_unit_revision_ids):
        raise ValueError(
            "L1 unit revision set must exactly match the turn bundle membership"
        )

    source_by_id = {
        item.source_revision_id: item for item in source_revisions
    }
    unit_by_id = {item.revision_id: item for item in unit_revisions}
    validate_turn_bundle_closure(
        bundle,
        source_revisions=source_by_id,
        unit_revisions=unit_by_id,
    )
    payload = {
        "schema_version": "git-memory-turn-bundle-payload-v1",
        "turn_bundle_revision": bundle.model_dump(mode="json"),
        "source_record_revisions": [
            source_by_id[item.source_revision_id].model_dump(mode="json")
            for item in bundle.source_records
        ],
        "l1_unit_revisions": [
            unit_by_id[revision_id].model_dump(mode="json")
            for revision_id in bundle.l1_unit_revision_ids
        ],
    }
    return make_history_artifact(
        artifact_kind="turn_bundle",
        logical_id=bundle.turn_bundle_id,
        revision_id=bundle.bundle_revision_id,
        transaction_time=bundle.transaction_time,
        payload=payload,
    )


class GitMemoryHistoryRepository:
    AUTHORITATIVE_REF = "refs/heads/authoritative"

    def __init__(self, repo_path: Path | str) -> None:
        self.repo_path = Path(repo_path)
        self._verified_head: str | None = None

    @classmethod
    def initialize(
        cls,
        repo_path: Path | str,
        *,
        workspace_id: str,
        created_at: str,
        parent_repository_epoch_id: str | None = None,
        purge_request_id: str | None = None,
    ) -> "GitMemoryHistoryRepository":
        path = Path(repo_path)
        if path.exists() and any(path.iterdir()):
            raise GitMemoryHistoryError(
                f"repository destination already exists and is not empty: {path}"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            [
                "git",
                "init",
                "--bare",
                "--quiet",
                "--initial-branch=authoritative",
                os.fspath(path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode != 0:
            raise GitMemoryHistoryError(
                completed.stderr.decode("utf-8", errors="replace").strip()
                or "git init --bare failed"
            )

        repository = cls(path)
        epoch_identity = {
            "workspace_id": workspace_id,
            "created_at": created_at,
            "parent_repository_epoch_id": parent_repository_epoch_id,
            "purge_request_id": purge_request_id,
        }
        epoch_id = f"epoch-{canonical_sha256(epoch_identity)[:24]}"
        metadata = RepositoryMetadata(
            workspace_id=workspace_id,
            repository_epoch_id=epoch_id,
            created_at=created_at,
            parent_repository_epoch_id=parent_repository_epoch_id,
            purge_request_id=purge_request_id,
        )
        state = RepositoryState(
            workspace_id=workspace_id,
            repository_epoch_id=epoch_id,
            sequence=0,
            checkpoint_id=None,
            transaction_time=created_at,
            git_commit=None,
        )
        files = {
            "repository.json": canonical_json_bytes(metadata),
            f"epochs/{epoch_id}.json": canonical_json_bytes(metadata),
            "state/current.json": canonical_json_bytes(state),
        }
        genesis = repository._create_commit(
            parent=None,
            files=files,
            transaction_time=created_at,
            message=f"Initialize memory history {epoch_id}",
        )
        repository._update_ref(genesis, expected_old=None)
        repository._git("symbolic-ref", "HEAD", cls.AUTHORITATIVE_REF)
        report = repository.verify()
        if report.status != "valid":
            raise GitMemoryHistoryError(
                "initialized repository failed verification: "
                + "; ".join(report.errors)
            )
        return repository

    def _command(
        self,
        *args: str,
        input_bytes: bytes | None = None,
        env: dict[str, str] | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[bytes]:
        completed = subprocess.run(
            ["git", f"--git-dir={self.repo_path}", *args],
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            check=False,
        )
        if check and completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", errors="replace").strip()
            raise GitMemoryHistoryError(
                f"git {' '.join(args)} failed: {detail or completed.returncode}"
            )
        return completed

    def _git(
        self,
        *args: str,
        input_bytes: bytes | None = None,
        env: dict[str, str] | None = None,
    ) -> str:
        return self._command(
            *args,
            input_bytes=input_bytes,
            env=env,
        ).stdout.decode("utf-8").strip()

    def _create_commit(
        self,
        *,
        parent: str | None,
        files: dict[str, bytes],
        transaction_time: str,
        message: str,
    ) -> str:
        with tempfile.TemporaryDirectory(prefix="git-memory-index-") as temp_dir:
            index_path = Path(temp_dir) / "index"
            git_env = os.environ.copy()
            git_env["GIT_INDEX_FILE"] = os.fspath(index_path)
            if parent is None:
                self._git("read-tree", "--empty", env=git_env)
            else:
                self._git("read-tree", parent, env=git_env)
            for path, content in sorted(files.items()):
                blob = self._git("hash-object", "-w", "--stdin", input_bytes=content)
                self._git(
                    "update-index",
                    "--add",
                    "--cacheinfo",
                    "100644",
                    blob,
                    path,
                    env=git_env,
                )
            tree = self._git("write-tree", env=git_env)

        commit_env = os.environ.copy()
        commit_env.update(
            {
                "GIT_AUTHOR_NAME": "KE Memory History",
                "GIT_AUTHOR_EMAIL": "memory-history@local.invalid",
                "GIT_COMMITTER_NAME": "KE Memory History",
                "GIT_COMMITTER_EMAIL": "memory-history@local.invalid",
                "GIT_AUTHOR_DATE": transaction_time,
                "GIT_COMMITTER_DATE": transaction_time,
            }
        )
        args = ["commit-tree", tree]
        if parent is not None:
            args.extend(["-p", parent])
        return self._git(
            *args,
            input_bytes=f"{message}\n".encode("utf-8"),
            env=commit_env,
        )

    def _update_ref(self, new_commit: str, *, expected_old: str | None) -> None:
        old_value = expected_old or ("0" * 40)
        completed = self._command(
            "update-ref",
            self.AUTHORITATIVE_REF,
            new_commit,
            old_value,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", errors="replace").strip()
            raise GitMemoryHistoryError(
                f"authoritative ref compare-and-swap failed: {detail}"
            )
        self._verified_head = None

    def head_commit(self) -> str:
        completed = self._command(
            "rev-parse",
            "--verify",
            self.AUTHORITATIVE_REF,
            check=False,
        )
        if completed.returncode != 0:
            raise GitMemoryHistoryError("authoritative ref does not exist")
        return completed.stdout.decode("utf-8").strip()

    def _read_bytes_at(self, commit: str, path: str) -> bytes:
        completed = self._command("show", f"{commit}:{path}", check=False)
        if completed.returncode != 0:
            raise GitMemoryHistoryError(
                f"missing canonical path at {commit}: {path}"
            )
        return completed.stdout

    def _read_json_at(self, commit: str, path: str) -> Any:
        try:
            return json.loads(self._read_bytes_at(commit, path))
        except json.JSONDecodeError as exc:
            raise GitMemoryHistoryError(
                f"invalid JSON at {commit}:{path}: {exc}"
            ) from exc

    def _path_exists_at(self, commit: str, path: str) -> bool:
        return (
            self._command("cat-file", "-e", f"{commit}:{path}", check=False).returncode
            == 0
        )

    def read_repository_metadata(
        self,
        *,
        commit: str | None = None,
    ) -> RepositoryMetadata:
        target = commit or self.head_commit()
        return RepositoryMetadata.model_validate(
            self._read_json_at(target, "repository.json")
        )

    def read_state(self, *, commit: str | None = None) -> RepositoryState:
        target = commit or self.head_commit()
        state = RepositoryState.model_validate(
            self._read_json_at(target, "state/current.json")
        )
        if state.git_commit is not None:
            raise GitMemoryHistoryError(
                "state/current.json must not persist a self-referential git_commit"
            )
        return state.model_copy(update={"git_commit": target})

    def commit_parents(self, commit: str) -> list[str]:
        return self._git("show", "-s", "--format=%P", commit).split()

    def read_checkpoint_manifest(
        self,
        *,
        commit: str | None = None,
    ) -> CheckpointManifest:
        target = commit or self.head_commit()
        state = self.read_state(commit=target)
        if state.checkpoint_id is None:
            raise GitMemoryHistoryError(
                "genesis state does not publish a checkpoint manifest"
            )
        path = (
            f"checkpoints/{state.sequence:020d}-{state.checkpoint_id}.json"
        )
        return CheckpointManifest.model_validate(
            self._read_json_at(target, path)
        )

    def make_checkpoint(
        self,
        *,
        artifacts: list[HistoryArtifact],
        transaction_time: str,
    ) -> CheckpointManifest:
        metadata = self.read_repository_metadata()
        state = self.read_state()
        return make_checkpoint_manifest(
            workspace_id=metadata.workspace_id,
            repository_epoch_id=metadata.repository_epoch_id,
            sequence=state.sequence + 1,
            previous_checkpoint_id=state.checkpoint_id,
            transaction_time=transaction_time,
            artifacts=artifacts,
        )

    @staticmethod
    def _checkpoint_path(manifest: CheckpointManifest) -> str:
        return (
            f"checkpoints/{manifest.sequence:020d}-{manifest.checkpoint_id}.json"
        )

    def _receipt_for_current(
        self,
        manifest: CheckpointManifest,
        current: str,
    ) -> CheckpointReceipt:
        parents = self._git("show", "-s", "--format=%P", current).split()
        if len(parents) != 1:
            raise GitMemoryHistoryError("checkpoint commit must have exactly one parent")
        return CheckpointReceipt(
            checkpoint_id=manifest.checkpoint_id,
            sequence=manifest.sequence,
            git_commit=current,
            previous_git_commit=parents[0],
        )

    def _find_idempotent_retry_commit(
        self,
        *,
        current: str,
        expected_head: str,
        manifest: CheckpointManifest,
        artifacts: list[HistoryArtifact],
    ) -> str | None:
        if current == expected_head:
            return None
        if self._command(
            "merge-base",
            "--is-ancestor",
            expected_head,
            current,
            check=False,
        ).returncode != 0:
            return None
        candidates = self._git(
            "rev-list",
            "--first-parent",
            "--reverse",
            f"{expected_head}..{current}",
        ).splitlines()
        for commit in candidates:
            try:
                state = self.read_state(commit=commit)
            except (GitMemoryHistoryError, ValueError):
                continue
            if state.checkpoint_id != manifest.checkpoint_id:
                continue
            checkpoint_path = self._checkpoint_path(manifest)
            if self._read_bytes_at(commit, checkpoint_path) != canonical_json_bytes(
                manifest
            ):
                raise GitMemoryHistoryError(
                    "published checkpoint ID collides with different manifest bytes"
                )
            for artifact in artifacts:
                if self._read_bytes_at(commit, artifact.path) != canonical_json_bytes(
                    artifact
                ):
                    raise GitMemoryHistoryError(
                        f"published artifact differs during retry: {artifact.path}"
                    )
            return commit
        return None

    def _validated_authoritative_head(self) -> str:
        current = self.head_commit()
        if self._verified_head == current:
            return current
        history_report = self.verify()
        if history_report.status != "valid":
            raise GitMemoryHistoryError(
                "authoritative history is invalid: "
                + "; ".join(history_report.errors)
            )
        if history_report.head_commit is None:
            raise GitMemoryHistoryError("authoritative history has no head commit")
        return history_report.head_commit

    def commit_checkpoint(
        self,
        *,
        manifest: CheckpointManifest,
        artifacts: list[HistoryArtifact],
        expected_head: str,
    ) -> CheckpointReceipt:
        expected_descriptors = [
            CheckpointArtifactDescriptor.from_artifact(item)
            for item in sorted(artifacts, key=_artifact_key)
        ]
        if manifest.artifacts != expected_descriptors:
            raise GitMemoryHistoryError(
                "checkpoint artifact set does not match the manifest"
            )

        current = self._validated_authoritative_head()
        published_commit = self._find_idempotent_retry_commit(
            current=current,
            expected_head=expected_head,
            manifest=manifest,
            artifacts=artifacts,
        )
        if published_commit is not None:
            return self._receipt_for_current(manifest, published_commit)
        if current != expected_head:
            raise GitMemoryHistoryError(
                f"stale expected head: expected {expected_head}, current {current}"
            )

        metadata = self.read_repository_metadata(commit=expected_head)
        previous_state = self.read_state(commit=expected_head)
        expected_manifest = make_checkpoint_manifest(
            workspace_id=metadata.workspace_id,
            repository_epoch_id=metadata.repository_epoch_id,
            sequence=previous_state.sequence + 1,
            previous_checkpoint_id=previous_state.checkpoint_id,
            transaction_time=manifest.transaction_time,
            artifacts=artifacts,
        )
        if manifest != expected_manifest:
            raise GitMemoryHistoryError(
                "checkpoint manifest does not match the expected repository state"
            )

        files: dict[str, bytes] = {}
        for artifact in artifacts:
            content = canonical_json_bytes(artifact)
            if self._path_exists_at(expected_head, artifact.path):
                if self._read_bytes_at(expected_head, artifact.path) != content:
                    raise GitMemoryHistoryError(
                        f"immutable artifact collision: {artifact.path}"
                    )
            files[artifact.path] = content
        candidate_by_identity = {
            self._artifact_identity(item): item
            for item in self._all_history_artifacts(expected_head)
        }
        candidate_by_identity.update(
            {self._artifact_identity(item): item for item in artifacts}
        )
        self._validate_reference_closure(list(candidate_by_identity.values()))
        files[self._checkpoint_path(manifest)] = canonical_json_bytes(manifest)
        next_state = RepositoryState(
            workspace_id=metadata.workspace_id,
            repository_epoch_id=metadata.repository_epoch_id,
            sequence=manifest.sequence,
            checkpoint_id=manifest.checkpoint_id,
            transaction_time=manifest.transaction_time,
            git_commit=None,
        )
        files["state/current.json"] = canonical_json_bytes(next_state)
        commit = self._create_commit(
            parent=expected_head,
            files=files,
            transaction_time=manifest.transaction_time,
            message=f"Checkpoint {manifest.sequence}: {manifest.checkpoint_id}",
        )
        try:
            self._update_ref(commit, expected_old=expected_head)
        except GitMemoryHistoryError:
            current = self._validated_authoritative_head()
            published_commit = self._find_idempotent_retry_commit(
                current=current,
                expected_head=expected_head,
                manifest=manifest,
                artifacts=artifacts,
            )
            if published_commit is not None:
                return self._receipt_for_current(manifest, published_commit)
            raise
        self._verified_head = commit
        return CheckpointReceipt(
            checkpoint_id=manifest.checkpoint_id,
            sequence=manifest.sequence,
            git_commit=commit,
            previous_git_commit=expected_head,
        )

    def read_artifact(
        self,
        *,
        artifact_kind: ArtifactKind,
        logical_id: str,
        revision_id: str,
        commit: str | None = None,
    ) -> HistoryArtifact:
        target = commit or self.head_commit()
        path = _artifact_path(artifact_kind, logical_id, revision_id)
        return HistoryArtifact.model_validate(self._read_json_at(target, path))

    def _all_history_artifacts(self, commit: str) -> list[HistoryArtifact]:
        paths = self._git(
            "ls-tree",
            "-r",
            "--name-only",
            commit,
            "--",
            "records",
        ).splitlines()
        artifacts: list[HistoryArtifact] = []
        for path in paths:
            if not path.endswith(".json"):
                raise GitMemoryHistoryError(
                    f"non-JSON record path in authoritative tree: {path}"
                )
            artifact = HistoryArtifact.model_validate(
                self._read_json_at(commit, path)
            )
            if artifact.path != path:
                raise GitMemoryHistoryError(
                    f"artifact physical path mismatch: {path} != {artifact.path}"
                )
            artifacts.append(artifact)
        return artifacts

    def _validate_canonical_tree_paths(
        self,
        commit: str,
        metadata: RepositoryMetadata,
    ) -> list[str]:
        paths = self._git(
            "ls-tree",
            "-r",
            "--name-only",
            commit,
        ).splitlines()
        exact_paths = {
            "repository.json",
            f"epochs/{metadata.repository_epoch_id}.json",
            "state/current.json",
        }
        checkpoint_pattern = re.compile(
            r"checkpoints/[0-9]{20}-"
            r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\.json"
        )
        for path in paths:
            if path in exact_paths or path.startswith("records/"):
                continue
            if checkpoint_pattern.fullmatch(path):
                continue
            raise GitMemoryHistoryError(
                f"non-canonical tree path in authoritative commit: {path}"
            )
        return paths

    @staticmethod
    def _artifact_identity(
        artifact: HistoryArtifact,
    ) -> tuple[ArtifactKind, str, str]:
        return (
            artifact.artifact_kind,
            artifact.logical_id,
            artifact.revision_id,
        )

    @staticmethod
    def _reference_resolves(
        reference: HistoryArtifactReference,
        artifacts: dict[tuple[ArtifactKind, str, str], HistoryArtifact],
    ) -> bool:
        if reference.revision_id is not None:
            return (
                reference.artifact_kind,
                reference.logical_id,
                reference.revision_id,
            ) in artifacts
        return any(
            artifact_kind == reference.artifact_kind
            and logical_id == reference.logical_id
            for artifact_kind, logical_id, _ in artifacts
        )

    @classmethod
    def _validate_reference_closure(
        cls,
        artifacts: list[HistoryArtifact],
    ) -> None:
        kinds_by_logical_id: dict[str, set[ArtifactKind]] = {}
        for artifact in artifacts:
            kinds_by_logical_id.setdefault(artifact.logical_id, set()).add(
                artifact.artifact_kind
            )
        ambiguous_logical_ids = sorted(
            logical_id
            for logical_id, artifact_kinds in kinds_by_logical_id.items()
            if len(artifact_kinds) > 1
        )
        if ambiguous_logical_ids:
            raise GitMemoryHistoryError(
                "logical IDs must be unique across artifact kinds: "
                f"{ambiguous_logical_ids}"
            )
        by_identity = {
            cls._artifact_identity(artifact): artifact
            for artifact in artifacts
        }
        for artifact in artifacts:
            for reference in artifact.references:
                if not cls._reference_resolves(reference, by_identity):
                    target = (
                        f"{reference.artifact_kind}/{reference.logical_id}/"
                        f"{reference.revision_id or '*'}"
                    )
                    raise GitMemoryHistoryError(
                        f"dangling reference from {artifact.path}: {target}"
                    )

    @staticmethod
    def _reference_targets_removed_artifact(
        reference: HistoryArtifactReference,
        removed: set[tuple[ArtifactKind, str, str]],
    ) -> bool:
        return any(
            reference.artifact_kind == artifact_kind
            and reference.logical_id == logical_id
            and (
                reference.revision_id is None
                or reference.revision_id == revision_id
            )
            for artifact_kind, logical_id, revision_id in removed
        )

    def prepare_hard_purge(
        self,
        destination_repo_path: Path | str,
        *,
        request: HardPurgeRequest,
    ) -> HardPurgeResult:
        source_report = self.verify()
        if source_report.status != "valid":
            raise GitMemoryHistoryError(
                "source repository failed verification: "
                + "; ".join(source_report.errors)
            )
        source_head = self.head_commit()
        metadata = self.read_repository_metadata(commit=source_head)
        if request.source_repository_epoch_id != metadata.repository_epoch_id:
            raise GitMemoryHistoryError(
                "hard-purge source repository epoch does not match"
            )
        if request.source_head != source_head:
            raise GitMemoryHistoryError("hard-purge source head does not match")
        source_path = self.repo_path.resolve()
        destination = Path(destination_repo_path).resolve(strict=False)
        if destination == source_path or destination.is_relative_to(source_path):
            raise GitMemoryHistoryError(
                "hard-purge destination cannot be inside source repository"
            )
        if destination.exists():
            raise GitMemoryHistoryError(
                f"hard-purge destination already exists: {destination}"
            )
        destination.parent.mkdir(parents=True, exist_ok=True)

        artifacts = self._all_history_artifacts(source_head)
        target_ids = set(request.target_logical_ids)
        found_ids = {
            artifact.logical_id
            for artifact in artifacts
            if artifact.logical_id in target_ids
        }
        missing_ids = sorted(target_ids - found_ids)
        if missing_ids:
            raise GitMemoryHistoryError(
                f"hard-purge targets do not exist: {missing_ids}"
            )

        removed = {
            self._artifact_identity(artifact)
            for artifact in artifacts
            if artifact.logical_id in target_ids
        }
        changed = True
        while changed:
            changed = False
            for artifact in artifacts:
                identity = self._artifact_identity(artifact)
                if identity in removed:
                    continue
                if any(
                    self._reference_targets_removed_artifact(reference, removed)
                    for reference in artifact.references
                ):
                    removed.add(identity)
                    changed = True

        removed_artifacts = sorted(
            (
                artifact
                for artifact in artifacts
                if self._artifact_identity(artifact) in removed
            ),
            key=_artifact_key,
        )
        retained_artifacts = sorted(
            (
                artifact
                for artifact in artifacts
                if self._artifact_identity(artifact) not in removed
            ),
            key=_artifact_key,
        )
        removed_fingerprints = [
            {
                "artifact_kind": artifact.artifact_kind,
                "logical_id_sha256": canonical_sha256(artifact.logical_id),
                "revision_id_sha256": canonical_sha256(artifact.revision_id),
                "path_sha256": canonical_sha256(artifact.path),
                "payload_sha256": artifact.payload_sha256,
            }
            for artifact in removed_artifacts
        ]
        purge_payload = {
            "schema_version": "git-memory-purge-manifest-payload-v1",
            "request_id": request.request_id,
            "source_repository_epoch_id": metadata.repository_epoch_id,
            "source_head": source_head,
            "authorized_at": request.authorized_at,
            "authorizer_sha256": canonical_sha256(request.authorizer),
            "reason_sha256": canonical_sha256(request.reason),
            "target_logical_id_sha256": [
                canonical_sha256(item) for item in request.target_logical_ids
            ],
            "removed_artifacts": removed_fingerprints,
            "removed_artifact_count": len(removed_artifacts),
            "retained_artifact_count": len(retained_artifacts),
        }
        purge_manifest_revision_id = (
            f"purge-manifest-revision-{canonical_sha256(purge_payload)[:24]}"
        )
        purge_manifest = make_history_artifact(
            artifact_kind="purge_manifest",
            logical_id=request.request_id,
            revision_id=purge_manifest_revision_id,
            transaction_time=request.authorized_at,
            payload=purge_payload,
        )

        with tempfile.TemporaryDirectory(
            prefix=f".{destination.name}.staging-",
            dir=destination.parent,
        ) as staging_directory:
            staging_repo = Path(staging_directory) / "repository.git"
            staging_repository = self.initialize(
                staging_repo,
                workspace_id=metadata.workspace_id,
                created_at=request.authorized_at,
                parent_repository_epoch_id=metadata.repository_epoch_id,
                purge_request_id=request.request_id,
            )
            checkpoint_artifacts = [*retained_artifacts, purge_manifest]
            checkpoint = staging_repository.make_checkpoint(
                artifacts=checkpoint_artifacts,
                transaction_time=request.authorized_at,
            )
            staging_repository.commit_checkpoint(
                manifest=checkpoint,
                artifacts=checkpoint_artifacts,
                expected_head=staging_repository.head_commit(),
            )
            destination_report = staging_repository.verify()
            if destination_report.status != "valid":
                raise GitMemoryHistoryError(
                    "purged repository failed verification: "
                    + "; ".join(destination_report.errors)
                )
            if self.head_commit() != source_head:
                raise GitMemoryHistoryError(
                    "source repository changed while preparing hard purge"
                )
            if destination.exists():
                raise GitMemoryHistoryError(
                    f"hard-purge destination already exists: {destination}"
                )
            os.rename(staging_repo, destination)

        destination_repository = GitMemoryHistoryRepository(destination)
        try:
            destination_report = destination_repository.verify()
            if destination_report.status != "valid":
                raise GitMemoryHistoryError(
                    "moved purged repository failed verification: "
                    + "; ".join(destination_report.errors)
                )
            destination_metadata = destination_repository.read_repository_metadata()
        except Exception:
            if destination.is_symlink():
                destination.unlink()
            elif destination.exists():
                shutil.rmtree(destination)
            raise
        return HardPurgeResult(
            request_id=request.request_id,
            source_repository_epoch_id=metadata.repository_epoch_id,
            source_head=source_head,
            destination_repository_epoch_id=(
                destination_metadata.repository_epoch_id
            ),
            destination_head=destination_repository.head_commit(),
            destination_repo_path=os.fspath(destination),
            removed_artifact_count=len(removed_artifacts),
            retained_artifact_count=len(retained_artifacts),
            purge_manifest_logical_id=purge_manifest.logical_id,
            purge_manifest_revision_id=purge_manifest.revision_id,
        )

    def verify(self) -> VerificationReport:
        head: str | None = None
        sequence: int | None = None
        checked_artifacts = 0
        errors: list[str] = []
        try:
            head = self.head_commit()
            metadata = self.read_repository_metadata(commit=head)
            epoch_metadata = RepositoryMetadata.model_validate(
                self._read_json_at(
                    head,
                    f"epochs/{metadata.repository_epoch_id}.json",
                )
            )
            if metadata != epoch_metadata:
                raise GitMemoryHistoryError(
                    "repository metadata differs from the current epoch record"
                )

            commits = self._git(
                "rev-list",
                "--first-parent",
                "--reverse",
                head,
            ).splitlines()
            if not commits:
                raise GitMemoryHistoryError("authoritative history is empty")
            previous_checkpoint_id: str | None = None
            previous_checkpoint_paths: set[str] = set()
            previous_record_paths: set[str] = set()
            previous_commit: str | None = None
            for expected_sequence, commit in enumerate(commits):
                parents = self._git("show", "-s", "--format=%P", commit).split()
                expected_parents = [] if expected_sequence == 0 else [
                    commits[expected_sequence - 1]
                ]
                if parents != expected_parents:
                    raise GitMemoryHistoryError(
                        "authoritative history is not a linear first-parent chain"
                    )
                commit_metadata = self.read_repository_metadata(commit=commit)
                if commit_metadata != metadata:
                    raise GitMemoryHistoryError(
                        "repository metadata changed within the current epoch"
                    )
                tree_paths = self._validate_canonical_tree_paths(commit, metadata)
                state = self.read_state(commit=commit)
                sequence = state.sequence
                if state.workspace_id != metadata.workspace_id:
                    raise GitMemoryHistoryError("state workspace_id mismatch")
                if state.repository_epoch_id != metadata.repository_epoch_id:
                    raise GitMemoryHistoryError("state repository_epoch_id mismatch")

                manifest: CheckpointManifest | None = None
                current_checkpoint_path: str | None = None
                manifest_artifact_paths: set[str] = set()
                if state.sequence == 0:
                    if state.checkpoint_id is not None:
                        raise GitMemoryHistoryError(
                            "genesis state cannot name a checkpoint"
                        )
                else:
                    checkpoint_prefix = f"checkpoints/{state.sequence:020d}-"
                    matches = [
                        path
                        for path in tree_paths
                        if path.startswith(checkpoint_prefix)
                    ]
                    if len(matches) != 1:
                        raise GitMemoryHistoryError(
                            "state does not resolve to exactly one checkpoint manifest"
                        )
                    current_checkpoint_path = matches[0]
                    manifest = CheckpointManifest.model_validate(
                        self._read_json_at(commit, current_checkpoint_path)
                    )
                    expected_checkpoint_path = self._checkpoint_path(manifest)
                    if current_checkpoint_path != expected_checkpoint_path:
                        raise GitMemoryHistoryError(
                            "checkpoint physical path mismatch: "
                            f"{current_checkpoint_path} != "
                            f"{expected_checkpoint_path}"
                        )
                    if manifest.checkpoint_id != state.checkpoint_id:
                        raise GitMemoryHistoryError("state checkpoint_id mismatch")
                    if manifest.transaction_time != state.transaction_time:
                        raise GitMemoryHistoryError(
                            "state transaction_time does not match checkpoint"
                        )
                    manifest_artifact_paths = set(manifest.artifact_paths)

                checkpoint_paths = {
                    path for path in tree_paths if path.startswith("checkpoints/")
                }
                expected_checkpoint_paths = set(previous_checkpoint_paths)
                if current_checkpoint_path is not None:
                    expected_checkpoint_paths.add(current_checkpoint_path)
                extra_checkpoint_paths = sorted(
                    checkpoint_paths - expected_checkpoint_paths
                )
                if extra_checkpoint_paths:
                    raise GitMemoryHistoryError(
                        "unexpected checkpoint manifest paths: "
                        f"{extra_checkpoint_paths}"
                    )
                missing_checkpoint_paths = sorted(
                    expected_checkpoint_paths - checkpoint_paths
                )
                if missing_checkpoint_paths:
                    raise GitMemoryHistoryError(
                        "checkpoint manifest paths disappeared within repository "
                        f"epoch: {missing_checkpoint_paths}"
                    )
                if previous_commit is not None:
                    for path in sorted(previous_checkpoint_paths):
                        if self._read_bytes_at(
                            previous_commit,
                            path,
                        ) != self._read_bytes_at(commit, path):
                            raise GitMemoryHistoryError(
                                "checkpoint manifest changed within repository "
                                f"epoch: {path}"
                            )

                all_artifacts = self._all_history_artifacts(commit)
                artifacts_by_path = {
                    artifact.path: artifact for artifact in all_artifacts
                }
                actual_record_paths = set(artifacts_by_path)
                expected_record_paths = (
                    previous_record_paths | manifest_artifact_paths
                )
                extra_paths = sorted(actual_record_paths - expected_record_paths)
                if extra_paths:
                    raise GitMemoryHistoryError(
                        f"unmanifested record paths: {extra_paths}"
                    )
                missing_paths = sorted(expected_record_paths - actual_record_paths)
                if missing_paths:
                    raise GitMemoryHistoryError(
                        f"record paths disappeared within repository epoch: {missing_paths}"
                    )
                if previous_commit is not None:
                    for path in sorted(previous_record_paths):
                        if self._read_bytes_at(previous_commit, path) != self._read_bytes_at(
                            commit,
                            path,
                        ):
                            raise GitMemoryHistoryError(
                                f"immutable record changed within repository epoch: {path}"
                            )
                self._validate_reference_closure(all_artifacts)
                if manifest is not None:
                    for descriptor in manifest.artifacts:
                        artifact = artifacts_by_path[descriptor.path]
                        if (
                            CheckpointArtifactDescriptor.from_artifact(artifact)
                            != descriptor
                        ):
                            raise GitMemoryHistoryError(
                                f"artifact descriptor mismatch: {descriptor.path}"
                            )
                checked_artifacts += len(all_artifacts)

                if state.sequence != expected_sequence:
                    raise GitMemoryHistoryError(
                        "checkpoint sequence is not contiguous with first-parent history"
                    )
                if manifest is not None:
                    if manifest.sequence != expected_sequence:
                        raise GitMemoryHistoryError(
                            "checkpoint manifest sequence is not contiguous"
                        )
                    if manifest.previous_checkpoint_id != previous_checkpoint_id:
                        raise GitMemoryHistoryError(
                            "checkpoint previous ID is not contiguous"
                        )
                    if manifest.workspace_id != metadata.workspace_id:
                        raise GitMemoryHistoryError("checkpoint workspace_id mismatch")
                    if manifest.repository_epoch_id != metadata.repository_epoch_id:
                        raise GitMemoryHistoryError(
                            "checkpoint repository_epoch_id mismatch"
                        )
                    previous_checkpoint_id = manifest.checkpoint_id
                previous_checkpoint_paths = checkpoint_paths
                previous_record_paths = actual_record_paths
                previous_commit = commit
        except Exception as exc:
            errors.append(str(exc))
        report = VerificationReport(
            status="invalid" if errors else "valid",
            head_commit=head,
            sequence=sequence,
            checked_artifacts=checked_artifacts,
            errors=errors,
        )
        self._verified_head = head if report.status == "valid" else None
        return report
