from __future__ import annotations

from collections.abc import Sequence
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ke_memory_demo.core.json import JsonObject, JsonValue, canonical_json


ArtifactKind = Literal["turn_bundle", "l2_bundle", "tombstone", "blob_ref", "purge_manifest"]
ReferenceRelation = Literal[
    "source",
    "derived_from",
    "supersedes",
    "conflicts_with",
    "tombstones",
    "blob",
]
SAFE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$"
_GIT_COMMIT_PATTERN = r"^[0-9a-f]{40,64}$"
_ZERO_COMMIT = "0" * 40
ARTIFACT_KIND_ORDER: dict[ArtifactKind, int] = {
    "turn_bundle": 0,
    "l2_bundle": 1,
    "tombstone": 2,
    "blob_ref": 3,
    "purge_manifest": 4,
}


class _HistoryModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def _canonical_sha256(value: BaseModel | JsonObject) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _reference_key(reference: HistoryArtifactReference) -> tuple[object, ...]:
    return (
        reference.relation,
        ARTIFACT_KIND_ORDER[reference.artifact_kind],
        reference.logical_id,
        reference.revision_id or "",
    )


def _artifact_key(artifact: HistoryArtifact) -> tuple[object, ...]:
    return (
        ARTIFACT_KIND_ORDER[artifact.artifact_kind],
        artifact.logical_id,
        artifact.revision_id,
    )


def _artifact_path(artifact_kind: ArtifactKind, logical_id: str, revision_id: str) -> str:
    return f"records/{artifact_kind}/{logical_id}/{revision_id}.json"


class HistoryArtifactReference(_HistoryModel):
    relation: ReferenceRelation
    artifact_kind: ArtifactKind
    logical_id: str = Field(min_length=1, pattern=SAFE_ID_PATTERN)
    revision_id: str | None = Field(default=None, min_length=1, pattern=SAFE_ID_PATTERN)


class HistoryArtifact(_HistoryModel):
    schema_version: Literal["git-memory-artifact-v1"] = "git-memory-artifact-v1"
    artifact_kind: ArtifactKind
    logical_id: str = Field(min_length=1, pattern=SAFE_ID_PATTERN)
    revision_id: str = Field(min_length=1, pattern=SAFE_ID_PATTERN)
    transaction_time: str = Field(min_length=1)
    payload: JsonObject
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    references: tuple[HistoryArtifactReference, ...] = ()
    path: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_contract(self) -> HistoryArtifact:
        if self.path != _artifact_path(self.artifact_kind, self.logical_id, self.revision_id):
            raise ValueError("artifact path does not match the generated canonical path")
        if self.payload_sha256 != _canonical_sha256(self.payload):
            raise ValueError("payload_sha256 does not match the canonical payload")
        ordered = tuple(sorted(self.references, key=_reference_key))
        if self.references != ordered:
            raise ValueError("artifact references must be in canonical order")
        reference_keys = tuple(_reference_key(item) for item in self.references)
        if len(reference_keys) != len(set(reference_keys)):
            raise ValueError("artifact references must be unique")
        relations = {item.relation for item in self.references}
        if self.artifact_kind == "l2_bundle":
            derived_from = tuple(item for item in self.references if item.relation == "derived_from")
            if not derived_from:
                raise ValueError("l2_bundle requires at least one derived_from reference")
            if any(item.artifact_kind not in {"turn_bundle", "l2_bundle"} for item in derived_from):
                raise ValueError(
                    "l2_bundle derived_from references must target turn_bundle or l2_bundle artifacts"
                )
            if not any(item.artifact_kind == "turn_bundle" for item in derived_from):
                raise ValueError("l2_bundle requires a direct derived_from turn_bundle reference")
        if self.artifact_kind == "tombstone" and (not self.references or relations != {"tombstones"}):
            raise ValueError("tombstone requires one or more tombstones references")
        if self.artifact_kind == "purge_manifest" and self.references:
            raise ValueError("purge_manifest cannot contain artifact references")
        return self


class CheckpointArtifactDescriptor(_HistoryModel):
    artifact_kind: ArtifactKind
    logical_id: str = Field(min_length=1, pattern=SAFE_ID_PATTERN)
    revision_id: str = Field(min_length=1, pattern=SAFE_ID_PATTERN)
    transaction_time: str = Field(min_length=1)
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    references: tuple[HistoryArtifactReference, ...] = ()
    path: str = Field(min_length=1)

    @classmethod
    def from_artifact(cls, artifact: HistoryArtifact) -> CheckpointArtifactDescriptor:
        return cls(
            artifact_kind=artifact.artifact_kind,
            logical_id=artifact.logical_id,
            revision_id=artifact.revision_id,
            transaction_time=artifact.transaction_time,
            payload_sha256=artifact.payload_sha256,
            references=artifact.references,
            path=artifact.path,
        )


class CheckpointManifest(_HistoryModel):
    schema_version: Literal["git-memory-checkpoint-v1"] = "git-memory-checkpoint-v1"
    workspace_id: str = Field(min_length=1, pattern=SAFE_ID_PATTERN)
    repository_epoch_id: str = Field(min_length=1, pattern=SAFE_ID_PATTERN)
    sequence: int = Field(ge=1)
    previous_checkpoint_id: str | None = Field(default=None, min_length=1, pattern=SAFE_ID_PATTERN)
    transaction_time: str = Field(min_length=1)
    artifacts: tuple[CheckpointArtifactDescriptor, ...] = Field(min_length=1)
    artifact_paths: tuple[str, ...] = Field(min_length=1)
    checkpoint_id: str = Field(min_length=1, pattern=SAFE_ID_PATTERN)
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _validate_contract(self) -> CheckpointManifest:
        if self.sequence == 1 and self.previous_checkpoint_id is not None:
            raise ValueError("checkpoint sequence 1 cannot have a previous checkpoint")
        if self.sequence > 1 and self.previous_checkpoint_id is None:
            raise ValueError("later checkpoints require a previous checkpoint")
        descriptor_keys = tuple(
            (ARTIFACT_KIND_ORDER[item.artifact_kind], item.logical_id, item.revision_id)
            for item in self.artifacts
        )
        if descriptor_keys != tuple(sorted(descriptor_keys)):
            raise ValueError("checkpoint artifacts must be in canonical order")
        if len(descriptor_keys) != len(set(descriptor_keys)):
            raise ValueError("checkpoint artifacts must be unique")
        if self.artifact_paths != tuple(item.path for item in self.artifacts):
            raise ValueError("artifact_paths must match the canonical descriptors")
        identity = self.model_dump(mode="json", exclude={"checkpoint_id", "manifest_sha256"})
        expected_checkpoint_id = f"checkpoint-{_canonical_sha256(cast(JsonObject, identity))[:24]}"
        if self.checkpoint_id != expected_checkpoint_id:
            raise ValueError("checkpoint_id does not match the canonical manifest identity")
        manifest = self.model_dump(mode="json", exclude={"manifest_sha256"})
        if self.manifest_sha256 != _canonical_sha256(cast(JsonObject, manifest)):
            raise ValueError("manifest_sha256 does not match the canonical manifest")
        return self


class RepositoryMetadata(_HistoryModel):
    schema_version: Literal["git-memory-repository-v1"] = "git-memory-repository-v1"
    workspace_id: str = Field(min_length=1, pattern=SAFE_ID_PATTERN)
    repository_epoch_id: str = Field(min_length=1, pattern=SAFE_ID_PATTERN)
    created_at: str = Field(min_length=1)
    authoritative_ref: Literal["refs/heads/authoritative"] = "refs/heads/authoritative"
    parent_repository_epoch_id: str | None = Field(default=None, min_length=1, pattern=SAFE_ID_PATTERN)
    purge_request_id: str | None = Field(default=None, min_length=1, pattern=SAFE_ID_PATTERN)


class RepositoryState(_HistoryModel):
    schema_version: Literal["git-memory-state-v1"] = "git-memory-state-v1"
    workspace_id: str = Field(min_length=1, pattern=SAFE_ID_PATTERN)
    repository_epoch_id: str = Field(min_length=1, pattern=SAFE_ID_PATTERN)
    sequence: int = Field(ge=0)
    checkpoint_id: str | None = Field(default=None, min_length=1, pattern=SAFE_ID_PATTERN)
    transaction_time: str = Field(min_length=1)
    git_commit: str | None = Field(default=None, pattern=_GIT_COMMIT_PATTERN)

    @model_validator(mode="after")
    def _validate_contract(self) -> RepositoryState:
        if self.sequence == 0 and self.checkpoint_id is not None:
            raise ValueError("genesis state cannot name a checkpoint")
        if self.sequence > 0 and self.checkpoint_id is None:
            raise ValueError("checkpoint state requires a checkpoint_id")
        return self


class CheckpointReceipt(_HistoryModel):
    schema_version: Literal["git-memory-checkpoint-receipt-v1"] = (
        "git-memory-checkpoint-receipt-v1"
    )
    checkpoint_id: str = Field(min_length=1, pattern=SAFE_ID_PATTERN)
    sequence: int = Field(ge=1)
    git_commit: str = Field(pattern=_GIT_COMMIT_PATTERN)
    previous_git_commit: str = Field(pattern=_GIT_COMMIT_PATTERN)


class VerificationReport(_HistoryModel):
    schema_version: Literal["git-memory-verification-v1"] = "git-memory-verification-v1"
    status: Literal["valid", "invalid"]
    head_commit: str | None = None
    sequence: int | None = Field(default=None, ge=0)
    checked_artifacts: int = Field(default=0, ge=0)
    errors: tuple[str, ...] = ()


class GitMemoryHistoryError(RuntimeError):
    """Git-backed memory history operation failed."""


def make_history_artifact(
    *,
    artifact_kind: ArtifactKind,
    logical_id: str,
    revision_id: str,
    transaction_time: str,
    payload: JsonObject,
    references: Sequence[HistoryArtifactReference] | None = None,
) -> HistoryArtifact:
    ordered_references = tuple(sorted(tuple(references or ()), key=_reference_key))
    return HistoryArtifact(
        artifact_kind=artifact_kind,
        logical_id=logical_id,
        revision_id=revision_id,
        transaction_time=transaction_time,
        payload=payload,
        payload_sha256=_canonical_sha256(payload),
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
    artifacts: Sequence[HistoryArtifact],
) -> CheckpointManifest:
    ordered_artifacts = tuple(sorted(tuple(artifacts), key=_artifact_key))
    descriptors = tuple(CheckpointArtifactDescriptor.from_artifact(item) for item in ordered_artifacts)
    artifact_paths = tuple(item.path for item in descriptors)
    descriptor_payloads: list[JsonValue] = [
        cast(JsonValue, item.model_dump(mode="json")) for item in descriptors
    ]
    artifact_path_values: list[JsonValue] = [path for path in artifact_paths]
    identity: JsonObject = {
        "schema_version": "git-memory-checkpoint-v1",
        "workspace_id": workspace_id,
        "repository_epoch_id": repository_epoch_id,
        "sequence": sequence,
        "previous_checkpoint_id": previous_checkpoint_id,
        "transaction_time": transaction_time,
        "artifacts": descriptor_payloads,
        "artifact_paths": artifact_path_values,
    }
    checkpoint_id = f"checkpoint-{_canonical_sha256(identity)[:24]}"
    manifest_payload: JsonObject = {**identity, "checkpoint_id": checkpoint_id}
    return CheckpointManifest(
        schema_version="git-memory-checkpoint-v1",
        workspace_id=workspace_id,
        repository_epoch_id=repository_epoch_id,
        sequence=sequence,
        previous_checkpoint_id=previous_checkpoint_id,
        transaction_time=transaction_time,
        artifacts=descriptors,
        artifact_paths=artifact_paths,
        checkpoint_id=checkpoint_id,
        manifest_sha256=_canonical_sha256(manifest_payload),
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
    ) -> GitMemoryHistoryRepository:
        path = Path(repo_path)
        if path.exists() and any(path.iterdir()):
            raise GitMemoryHistoryError(
                f"repository destination already exists and is not empty: {path}"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            ["git", "init", "--bare", "--quiet", "--initial-branch=authoritative", os.fspath(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", errors="replace").strip()
            raise GitMemoryHistoryError(detail or "git init --bare failed")

        repository = cls(path)
        epoch_identity: JsonObject = {
            "workspace_id": workspace_id,
            "created_at": created_at,
            "parent_repository_epoch_id": parent_repository_epoch_id,
            "purge_request_id": purge_request_id,
        }
        epoch_id = f"epoch-{_canonical_sha256(epoch_identity)[:24]}"
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
        genesis = repository._create_commit(
            parent=None,
            files={
                "repository.json": canonical_json(metadata),
                f"epochs/{epoch_id}.json": canonical_json(metadata),
                "state/current.json": canonical_json(state),
            },
            transaction_time=created_at,
            message=f"Initialize memory history {epoch_id}",
        )
        repository._update_ref(genesis, expected_old=None)
        repository._git("symbolic-ref", "HEAD", cls.AUTHORITATIVE_REF)
        report = repository.verify()
        if report.status != "valid":
            raise GitMemoryHistoryError(
                "initialized repository failed verification: " + "; ".join(report.errors)
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
            raise GitMemoryHistoryError(f"git {' '.join(args)} failed: {detail or completed.returncode}")
        return completed

    def _git(
        self,
        *args: str,
        input_bytes: bytes | None = None,
        env: dict[str, str] | None = None,
    ) -> str:
        return self._command(*args, input_bytes=input_bytes, env=env).stdout.decode(
            "utf-8",
            errors="replace",
        ).strip()

    def _create_commit(
        self,
        *,
        parent: str | None,
        files: dict[str, bytes],
        transaction_time: str,
        message: str,
    ) -> str:
        with tempfile.TemporaryDirectory(prefix="ke-memory-history-index-") as temp_dir:
            index_path = Path(temp_dir) / "index"
            git_env = os.environ.copy()
            git_env["GIT_INDEX_FILE"] = os.fspath(index_path)
            if parent is None:
                self._git("read-tree", "--empty", env=git_env)
            else:
                self._git("read-tree", parent, env=git_env)
            for path, content in sorted(files.items()):
                blob = self._git("hash-object", "-w", "--stdin", input_bytes=content)
                self._git("update-index", "--add", "--cacheinfo", "100644", blob, path, env=git_env)
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
        commit_args = ["commit-tree", tree]
        if parent is not None:
            commit_args.extend(["-p", parent])
        return self._git(*commit_args, input_bytes=f"{message}\n".encode("utf-8"), env=commit_env)

    def _update_ref(self, new_commit: str, *, expected_old: str | None) -> None:
        completed = self._command(
            "update-ref",
            self.AUTHORITATIVE_REF,
            new_commit,
            expected_old or _ZERO_COMMIT,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", errors="replace").strip()
            raise GitMemoryHistoryError(
                f"authoritative ref compare-and-swap failed: {detail or completed.returncode}"
            )
        self._verified_head = None

    def head_commit(self) -> str:
        completed = self._command("rev-parse", "--verify", self.AUTHORITATIVE_REF, check=False)
        if completed.returncode != 0:
            raise GitMemoryHistoryError("authoritative ref does not exist")
        return completed.stdout.decode("utf-8", errors="replace").strip()

    def _read_bytes_at(self, commit: str, path: str) -> bytes:
        completed = self._command("show", f"{commit}:{path}", check=False)
        if completed.returncode != 0:
            raise GitMemoryHistoryError(f"missing canonical path at {commit}: {path}")
        return completed.stdout

    def _read_json_at(self, commit: str, path: str) -> Any:
        try:
            return json.loads(self._read_bytes_at(commit, path))
        except json.JSONDecodeError as error:
            raise GitMemoryHistoryError(f"invalid JSON at {commit}:{path}: {error}") from error

    def _path_exists_at(self, commit: str, path: str) -> bool:
        return self._command("cat-file", "-e", f"{commit}:{path}", check=False).returncode == 0

    def read_repository_metadata(self, *, commit: str | None = None) -> RepositoryMetadata:
        target = commit or self.head_commit()
        return RepositoryMetadata.model_validate(self._read_json_at(target, "repository.json"))

    def read_state(self, *, commit: str | None = None) -> RepositoryState:
        target = commit or self.head_commit()
        state = RepositoryState.model_validate(self._read_json_at(target, "state/current.json"))
        if state.git_commit is not None:
            raise GitMemoryHistoryError("state/current.json must not persist a self-referential git_commit")
        return state.model_copy(update={"git_commit": target})

    def make_checkpoint(
        self,
        *,
        artifacts: Sequence[HistoryArtifact],
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
        return f"checkpoints/{manifest.sequence:020d}-{manifest.checkpoint_id}.json"

    def commit_checkpoint(
        self,
        *,
        manifest: CheckpointManifest,
        artifacts: Sequence[HistoryArtifact],
        expected_head: str,
    ) -> CheckpointReceipt:
        artifact_tuple = tuple(artifacts)
        expected_descriptors = tuple(
            CheckpointArtifactDescriptor.from_artifact(item)
            for item in sorted(artifact_tuple, key=_artifact_key)
        )
        if manifest.artifacts != expected_descriptors:
            raise GitMemoryHistoryError("checkpoint artifact set does not match the manifest")

        current = self._validated_authoritative_head()
        published_commit = self._find_idempotent_retry_commit(
            current=current,
            expected_head=expected_head,
            manifest=manifest,
            artifacts=artifact_tuple,
        )
        if published_commit is not None:
            return self._receipt_for_current(manifest, published_commit)
        if current != expected_head:
            raise GitMemoryHistoryError(f"stale expected head: expected {expected_head}, current {current}")

        metadata = self.read_repository_metadata(commit=expected_head)
        previous_state = self.read_state(commit=expected_head)
        expected_manifest = make_checkpoint_manifest(
            workspace_id=metadata.workspace_id,
            repository_epoch_id=metadata.repository_epoch_id,
            sequence=previous_state.sequence + 1,
            previous_checkpoint_id=previous_state.checkpoint_id,
            transaction_time=manifest.transaction_time,
            artifacts=artifact_tuple,
        )
        if manifest != expected_manifest:
            raise GitMemoryHistoryError("checkpoint manifest does not match the expected repository state")

        files: dict[str, bytes] = {}
        for artifact in artifact_tuple:
            content = canonical_json(artifact)
            if self._path_exists_at(expected_head, artifact.path):
                if self._read_bytes_at(expected_head, artifact.path) != content:
                    raise GitMemoryHistoryError(f"immutable artifact collision: {artifact.path}")
            files[artifact.path] = content
        existing_artifacts = self._all_history_artifacts(expected_head)
        candidate_by_identity = {self._artifact_identity(item): item for item in existing_artifacts}
        candidate_by_identity.update({self._artifact_identity(item): item for item in artifact_tuple})
        self._validate_reference_closure(tuple(candidate_by_identity.values()))

        files[self._checkpoint_path(manifest)] = canonical_json(manifest)
        next_state = RepositoryState(
            workspace_id=metadata.workspace_id,
            repository_epoch_id=metadata.repository_epoch_id,
            sequence=manifest.sequence,
            checkpoint_id=manifest.checkpoint_id,
            transaction_time=manifest.transaction_time,
            git_commit=None,
        )
        files["state/current.json"] = canonical_json(next_state)
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
            retry_commit = self._find_idempotent_retry_commit(
                current=current,
                expected_head=expected_head,
                manifest=manifest,
                artifacts=artifact_tuple,
            )
            if retry_commit is not None:
                return self._receipt_for_current(manifest, retry_commit)
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

    def verify(self) -> VerificationReport:
        errors: list[str] = []
        head: str | None = None
        sequence: int | None = None
        checked_artifacts = 0
        try:
            head = self.head_commit()
            metadata = self.read_repository_metadata(commit=head)
            self._validate_canonical_tree_paths(head, metadata)
            state = self.read_state(commit=head)
            if state.workspace_id != metadata.workspace_id:
                raise GitMemoryHistoryError("state workspace_id does not match repository metadata")
            if state.repository_epoch_id != metadata.repository_epoch_id:
                raise GitMemoryHistoryError("state repository_epoch_id does not match repository metadata")
            artifacts = self._all_history_artifacts(head)
            checked_artifacts = len(artifacts)
            self._validate_reference_closure(tuple(artifacts))
            self._validate_checkpoints(head, metadata, state)
            sequence = state.sequence
        except Exception as error:  # noqa: BLE001 - verifier returns structured diagnostics.
            errors.append(str(error))
        status: Literal["valid", "invalid"] = "invalid" if errors else "valid"
        if status == "valid":
            self._verified_head = head
        return VerificationReport(
            status=status,
            head_commit=head,
            sequence=sequence,
            checked_artifacts=checked_artifacts,
            errors=tuple(errors),
        )

    def _validated_authoritative_head(self) -> str:
        current = self.head_commit()
        if self._verified_head == current:
            return current
        report = self.verify()
        if report.status != "valid" or report.head_commit is None:
            raise GitMemoryHistoryError("authoritative history is invalid: " + "; ".join(report.errors))
        self._verified_head = report.head_commit
        return report.head_commit

    def _receipt_for_current(self, manifest: CheckpointManifest, current: str) -> CheckpointReceipt:
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
        artifacts: Sequence[HistoryArtifact],
    ) -> str | None:
        if current == expected_head:
            return None
        if self._command("merge-base", "--is-ancestor", expected_head, current, check=False).returncode != 0:
            return None
        candidates = self._git("rev-list", "--first-parent", "--reverse", f"{expected_head}..{current}").splitlines()
        for commit in candidates:
            try:
                state = self.read_state(commit=commit)
            except (GitMemoryHistoryError, ValueError):
                continue
            if state.checkpoint_id != manifest.checkpoint_id:
                continue
            checkpoint_path = self._checkpoint_path(manifest)
            if self._read_bytes_at(commit, checkpoint_path) != canonical_json(manifest):
                raise GitMemoryHistoryError("published checkpoint ID collides with different manifest bytes")
            for artifact in artifacts:
                if self._read_bytes_at(commit, artifact.path) != canonical_json(artifact):
                    raise GitMemoryHistoryError(f"published artifact differs during retry: {artifact.path}")
            return commit
        return None

    def _all_history_artifacts(self, commit: str) -> tuple[HistoryArtifact, ...]:
        completed = self._command("ls-tree", "-r", "--name-only", commit, "--", "records", check=False)
        if completed.returncode != 0:
            return ()
        paths = completed.stdout.decode("utf-8", errors="replace").splitlines()
        artifacts: list[HistoryArtifact] = []
        for path in paths:
            if not path.endswith(".json"):
                raise GitMemoryHistoryError(f"non-JSON record path in authoritative tree: {path}")
            artifact = HistoryArtifact.model_validate(self._read_json_at(commit, path))
            if artifact.path != path:
                raise GitMemoryHistoryError(f"artifact physical path mismatch: {path} != {artifact.path}")
            artifacts.append(artifact)
        return tuple(artifacts)

    @staticmethod
    def _artifact_identity(artifact: HistoryArtifact) -> tuple[ArtifactKind, str, str]:
        return (artifact.artifact_kind, artifact.logical_id, artifact.revision_id)

    @staticmethod
    def _reference_resolves(
        reference: HistoryArtifactReference,
        artifacts: dict[tuple[ArtifactKind, str, str], HistoryArtifact],
    ) -> bool:
        if reference.revision_id is not None:
            return (reference.artifact_kind, reference.logical_id, reference.revision_id) in artifacts
        return any(
            artifact_kind == reference.artifact_kind and logical_id == reference.logical_id
            for artifact_kind, logical_id, _revision_id in artifacts
        )

    @classmethod
    def _validate_reference_closure(cls, artifacts: Sequence[HistoryArtifact]) -> None:
        kinds_by_logical_id: dict[str, set[ArtifactKind]] = {}
        for artifact in artifacts:
            kinds_by_logical_id.setdefault(artifact.logical_id, set()).add(artifact.artifact_kind)
        ambiguous = sorted(
            logical_id for logical_id, artifact_kinds in kinds_by_logical_id.items() if len(artifact_kinds) > 1
        )
        if ambiguous:
            raise GitMemoryHistoryError(f"logical IDs must be unique across artifact kinds: {ambiguous}")
        by_identity = {cls._artifact_identity(artifact): artifact for artifact in artifacts}
        for artifact in artifacts:
            for reference in artifact.references:
                if not cls._reference_resolves(reference, by_identity):
                    target = f"{reference.artifact_kind}/{reference.logical_id}/{reference.revision_id or '*'}"
                    raise GitMemoryHistoryError(f"dangling reference from {artifact.path}: {target}")

    def _validate_canonical_tree_paths(self, commit: str, metadata: RepositoryMetadata) -> None:
        paths = self._git("ls-tree", "-r", "--name-only", commit).splitlines()
        exact_paths = {
            "repository.json",
            f"epochs/{metadata.repository_epoch_id}.json",
            "state/current.json",
        }
        checkpoint_pattern = re.compile(
            r"checkpoints/[0-9]{20}-[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\.json"
        )
        for path in paths:
            if path in exact_paths or path.startswith("records/") or checkpoint_pattern.fullmatch(path):
                continue
            raise GitMemoryHistoryError(f"non-canonical tree path in authoritative commit: {path}")

    def _validate_checkpoints(
        self,
        commit: str,
        metadata: RepositoryMetadata,
        state: RepositoryState,
    ) -> None:
        completed = self._command("ls-tree", "-r", "--name-only", commit, "--", "checkpoints", check=False)
        paths = completed.stdout.decode("utf-8", errors="replace").splitlines() if completed.returncode == 0 else []
        checkpoints = tuple(
            CheckpointManifest.model_validate(self._read_json_at(commit, path)) for path in paths
        )
        ordered = tuple(sorted(checkpoints, key=lambda item: item.sequence))
        if len(ordered) != state.sequence:
            raise GitMemoryHistoryError("checkpoint count does not match repository state sequence")
        previous_checkpoint_id: str | None = None
        for expected_sequence, manifest in enumerate(ordered, start=1):
            if manifest.sequence != expected_sequence:
                raise GitMemoryHistoryError("checkpoint sequence is not contiguous")
            if manifest.workspace_id != metadata.workspace_id:
                raise GitMemoryHistoryError("checkpoint workspace_id does not match repository metadata")
            if manifest.repository_epoch_id != metadata.repository_epoch_id:
                raise GitMemoryHistoryError("checkpoint repository_epoch_id does not match repository metadata")
            if manifest.previous_checkpoint_id != previous_checkpoint_id:
                raise GitMemoryHistoryError("checkpoint previous_checkpoint_id chain is not contiguous")
            if self._checkpoint_path(manifest) not in paths:
                raise GitMemoryHistoryError("checkpoint path does not match canonical name")
            previous_checkpoint_id = manifest.checkpoint_id
        if state.sequence == 0:
            if state.checkpoint_id is not None:
                raise GitMemoryHistoryError("genesis state unexpectedly names a checkpoint")
            return
        if not ordered or ordered[-1].checkpoint_id != state.checkpoint_id:
            raise GitMemoryHistoryError("state checkpoint_id does not match latest checkpoint")

