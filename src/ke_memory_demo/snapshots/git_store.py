from __future__ import annotations

from collections import Counter
from collections.abc import Generator, Mapping
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from pydantic import BaseModel

from ke_memory_demo.core.json import canonical_json
from ke_memory_demo.infra.telemetry import ModelTrace, validate_usage_context_only_trace
from ke_memory_demo.contracts import (
    STAGE_ARTIFACT_ALLOWLIST,
    STAGE_PREDECESSOR,
    PipelineRunManifest,
    PipelineStage,
    SnapshotRef,
    SnapshotVerification,
)
from ke_memory_demo.ontology import OntologyRelation, OntologyTerm
from ke_memory_demo.storage import ArtifactStore, StageManifest


_GITIGNORE = """.staging/
cache/
checkpoints/
exports/
.env.local
*.sqlite3
"""
_SHA1 = re.compile(r"[0-9a-f]{40}", flags=re.ASCII)


class SnapshotError(RuntimeError):
    """A state snapshot could not be created or verified deterministically."""


class GitSnapshotStore:
    def __init__(self, root: Path, artifacts: ArtifactStore) -> None:
        self._root = root
        self._artifacts = artifacts

    @classmethod
    def init(cls, root: Path, artifacts: ArtifactStore) -> GitSnapshotStore:
        root.mkdir(parents=True, exist_ok=True)
        resolved_root = root.resolve(strict=True)
        if resolved_root != artifacts.root:
            raise SnapshotError("snapshot repository root must match the artifact state root")

        store = cls(resolved_root, artifacts)
        store._git("init", "--quiet", "--object-format=sha1")
        store._git("config", "--local", "user.name", "KE Memory Snapshot Store")
        store._git("config", "--local", "user.email", "ke-memory-snapshots@local")
        store._git("config", "--local", "commit.gpgsign", "false")

        ignore_path = resolved_root / ".gitignore"
        artifacts.layout.assert_safe(ignore_path)
        ignore_path.write_text(_GITIGNORE, encoding="utf-8")
        return store

    def head(self) -> str | None:
        try:
            value = self._git("rev-parse", "--verify", "HEAD^{commit}")
        except SnapshotError:
            if self._git("rev-parse", "--is-inside-work-tree") != "true":
                raise
            return None
        return self._validated_snapshot_id(value)

    def commit_stage(self, run_id: str, stage: PipelineStage) -> SnapshotRef:
        stage_manifest = self._artifacts.validate_stage(
            run_id,
            stage.value,
            canonical=True,
        )
        self._validate_stage_artifact_allowlist(stage_manifest, stage)
        self._validate_model_traces(self._artifacts, stage_manifest, run_id, stage)
        manifest = self._validated_pipeline_manifest(
            self._artifacts,
            stage_manifest,
            run_id,
            stage,
        )
        parent_snapshot_id = self.head()
        if manifest.parent_snapshot_id != parent_snapshot_id:
            raise SnapshotError(
                "pipeline manifest parent snapshot does not match the state repository HEAD"
            )
        self._require_predecessor(run_id, stage, parent_snapshot_id)
        self._validate_cumulative_stage(
            self._artifacts,
            stage_manifest,
            run_id,
            stage,
            parent_snapshot_id,
        )

        stage_manifest_bytes = self._canonical_stage_manifest_bytes(
            self._artifacts,
            stage_manifest,
            run_id,
            stage,
        )
        stage_manifest_sha256 = hashlib.sha256(stage_manifest_bytes).hexdigest()
        self._reject_staged_paths_outside(run_id, stage)
        stage_path = f"runs/{run_id}/{stage.value}"
        self._git("add", "--", ".gitignore", stage_path)
        self._reject_staged_paths_outside(run_id, stage)
        self._git("commit", "--no-verify", "-m", f"stage: {run_id} {stage.value}")

        snapshot_id = self.head()
        if snapshot_id is None:
            raise SnapshotError("Git commit completed without creating a repository HEAD")
        committed_manifest = self._manifest_bytes_from_commit(snapshot_id, run_id, stage)
        if hashlib.sha256(committed_manifest).hexdigest() != stage_manifest_sha256:
            raise SnapshotError("committed stage manifest differs from the validated stage")
        return SnapshotRef(
            snapshot_id=snapshot_id,
            run_id=run_id,
            stage=stage,
            stage_manifest_sha256=stage_manifest_sha256,
        )

    def verify(
        self,
        snapshot_id: str,
        run_id: str,
        stage: PipelineStage,
    ) -> SnapshotVerification:
        snapshot_id = self._resolve_commit(snapshot_id)
        expected_manifest = self._manifest_bytes_from_commit(snapshot_id, run_id, stage)
        expected_sha256 = hashlib.sha256(expected_manifest).hexdigest()
        parent_snapshot_id = self._validate_committed_stage(
            snapshot_id,
            run_id,
            stage,
            expected_manifest_sha256=expected_sha256,
        )
        self._validate_predecessor_chain(
            parent_snapshot_id,
            run_id,
            STAGE_PREDECESSOR[stage],
            seen={snapshot_id},
        )

        return SnapshotVerification(
            snapshot_id=snapshot_id,
            run_id=run_id,
            stage=stage,
            verified=True,
            stage_manifest_sha256=expected_sha256,
        )

    def _validate_committed_stage(
        self,
        snapshot_id: str,
        run_id: str,
        stage: PipelineStage,
        *,
        expected_manifest_sha256: str | None = None,
    ) -> str | None:
        parent_snapshot_id = self._commit_parent(snapshot_id)

        with self._detached_worktree(snapshot_id) as checkout:
            checked_artifacts = ArtifactStore(
                checkout,
                registry=_artifact_registry(self._artifacts),
            )
            stage_manifest = checked_artifacts.validate_stage(
                run_id,
                stage.value,
                canonical=True,
            )
            self._validate_stage_artifact_allowlist(stage_manifest, stage)
            self._validate_model_traces(
                checked_artifacts,
                stage_manifest,
                run_id,
                stage,
            )
            manifest = self._validated_pipeline_manifest(
                checked_artifacts,
                stage_manifest,
                run_id,
                stage,
            )
            if manifest.parent_snapshot_id != parent_snapshot_id:
                raise SnapshotError(
                    "pipeline manifest parent snapshot does not match the snapshot commit parent"
                )
            self._require_predecessor(run_id, stage, parent_snapshot_id)
            self._validate_cumulative_stage(
                checked_artifacts,
                stage_manifest,
                run_id,
                stage,
                parent_snapshot_id,
            )
            checked_manifest = self._canonical_stage_manifest_bytes(
                checked_artifacts,
                stage_manifest,
                run_id,
                stage,
            )
            checked_sha256 = hashlib.sha256(checked_manifest).hexdigest()
            if expected_manifest_sha256 is not None and checked_sha256 != expected_manifest_sha256:
                raise SnapshotError("checked-out stage manifest differs from the Git snapshot")
        return parent_snapshot_id

    def _validate_predecessor_chain(
        self,
        snapshot_id: str | None,
        run_id: str,
        stage: PipelineStage | None,
        *,
        seen: set[str],
    ) -> None:
        while stage is not None:
            if snapshot_id is None:
                raise SnapshotError(f"snapshot ancestry ended before required stage {stage.value}")
            if snapshot_id in seen:
                raise SnapshotError("snapshot ancestry contains a cycle")
            seen.add(snapshot_id)
            snapshot_id = self._validate_committed_stage(snapshot_id, run_id, stage)
            stage = STAGE_PREDECESSOR[stage]

    def tracked_files(self, snapshot_id: str) -> tuple[str, ...]:
        snapshot_id = self._resolve_commit(snapshot_id)
        output = self._git("ls-tree", "-r", "-z", snapshot_id, "--")
        names: list[str] = []
        for record in (item for item in output.split("\0") if item):
            _metadata, separator, path = record.partition("\t")
            if not separator or not path:
                raise SnapshotError("Git returned an invalid tracked-file record")
            names.append(path)
        return tuple(names)

    def _git(self, *arguments: str) -> str:
        completed = subprocess.run(
            ("git", "-C", str(self._root), *arguments),
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        if completed.returncode != 0:
            raise SnapshotError(f"git {' '.join(arguments)} failed: {completed.stderr.strip()}")
        return completed.stdout.strip()

    def _resolve_commit(self, snapshot_id: str) -> str:
        snapshot_id = self._validated_snapshot_id(snapshot_id)
        resolved = self._git("rev-parse", "--verify", f"{snapshot_id}^{{commit}}")
        if resolved != snapshot_id:
            raise SnapshotError("snapshot ID did not resolve to the requested commit")
        return snapshot_id

    @staticmethod
    def _validated_snapshot_id(value: str) -> str:
        if _SHA1.fullmatch(value) is None:
            raise SnapshotError("snapshot ID must be a full 40-character lowercase Git SHA")
        return value

    @staticmethod
    def _validate_stage_artifact_allowlist(
        stage_manifest: StageManifest,
        stage: PipelineStage,
    ) -> None:
        allowed = STAGE_ARTIFACT_ALLOWLIST[stage]
        forbidden = sorted(
            artifact.name for artifact in stage_manifest.artifacts if artifact.name not in allowed
        )
        if forbidden:
            raise SnapshotError(f"artifact {forbidden[0]} is not allowed in stage {stage.value}")

    @staticmethod
    def _validate_model_traces(
        artifacts: ArtifactStore,
        stage_manifest: StageManifest,
        run_id: str,
        stage: PipelineStage,
    ) -> None:
        if not any(artifact.name == "model_traces" for artifact in stage_manifest.artifacts):
            return
        try:
            traces = artifacts.read_jsonl(
                run_id,
                stage.value,
                "model_traces",
                ModelTrace,
            )
            for trace in traces:
                validate_usage_context_only_trace(trace)
        except (TypeError, ValueError) as error:
            raise SnapshotError(
                "model trace artifact must contain usage/context-only records"
            ) from error

    @staticmethod
    def _validated_pipeline_manifest(
        artifacts: ArtifactStore,
        stage_manifest: StageManifest,
        run_id: str,
        stage: PipelineStage,
    ) -> PipelineRunManifest:
        records = tuple(
            artifacts.read_jsonl(
                run_id,
                stage.value,
                "pipeline_manifests",
                PipelineRunManifest,
            )
        )
        if len(records) != 1:
            raise SnapshotError("snapshot stage must contain exactly one pipeline manifest")
        manifest = records[0]
        if manifest.run_id != run_id or manifest.stage != stage:
            raise SnapshotError("pipeline manifest identity does not match the committed stage")
        actual_counts = {
            artifact.name: artifact.record_count for artifact in stage_manifest.artifacts
        }
        if manifest.record_counts != actual_counts:
            raise SnapshotError("pipeline manifest record counts do not match the stage manifest")
        GitSnapshotStore._validate_ontology_scope(
            artifacts,
            stage_manifest,
            manifest,
            run_id,
            stage,
        )
        return manifest

    @staticmethod
    def _validate_ontology_scope(
        artifacts: ArtifactStore,
        stage_manifest: StageManifest,
        manifest: PipelineRunManifest,
        run_id: str,
        stage: PipelineStage,
    ) -> None:
        matched_document_ids = set(manifest.ontology.matched_document_ids)
        artifact_names = {artifact.name for artifact in stage_manifest.artifacts}
        if "ontology_terms" in artifact_names:
            terms = artifacts.read_jsonl(
                run_id,
                stage.value,
                "ontology_terms",
                OntologyTerm,
            )
            for term in terms:
                if term.document_id not in matched_document_ids:
                    raise SnapshotError(
                        f"ontology term is outside matched document IDs: {term.document_id}"
                    )
                for relation in term.relations:
                    GitSnapshotStore._validate_ontology_relation(
                        relation,
                        matched_document_ids,
                    )
        if "ontology_relations" in artifact_names:
            relations = artifacts.read_jsonl(
                run_id,
                stage.value,
                "ontology_relations",
                OntologyRelation,
            )
            for relation in relations:
                GitSnapshotStore._validate_ontology_relation(
                    relation,
                    matched_document_ids,
                )

    @staticmethod
    def _validate_ontology_relation(
        relation: OntologyRelation,
        matched_document_ids: set[str],
    ) -> None:
        if relation.source_document_id not in matched_document_ids:
            raise SnapshotError(
                "ontology relation source is outside matched document IDs: "
                f"{relation.source_document_id}"
            )

    @staticmethod
    def _canonical_stage_manifest_bytes(
        artifacts: ArtifactStore,
        stage_manifest: StageManifest,
        run_id: str,
        stage: PipelineStage,
    ) -> bytes:
        manifest_path = artifacts.layout.canonical_stage(run_id, stage.value) / "manifest.json"
        data = manifest_path.read_bytes()
        if data != canonical_json(stage_manifest):
            raise SnapshotError("stage manifest must use canonical JSON bytes")
        return data

    def _manifest_bytes_from_commit(
        self,
        snapshot_id: str,
        run_id: str,
        stage: PipelineStage,
    ) -> bytes:
        path = f"runs/{run_id}/{stage.value}/manifest.json"
        return self._git("show", f"{snapshot_id}:{path}").encode("utf-8")

    def _commit_parent(self, snapshot_id: str) -> str | None:
        fields = self._git("rev-list", "--parents", "-n", "1", snapshot_id).split()
        if not fields or fields[0] != snapshot_id:
            raise SnapshotError("Git returned an invalid snapshot ancestry record")
        if len(fields) > 2:
            raise SnapshotError("snapshot commits must not be merge commits")
        return fields[1] if len(fields) == 2 else None

    def _require_predecessor(
        self,
        run_id: str,
        stage: PipelineStage,
        parent_snapshot_id: str | None,
    ) -> None:
        predecessor = STAGE_PREDECESSOR[stage]
        if predecessor is None:
            return
        if parent_snapshot_id is None:
            raise SnapshotError(
                f"stage {stage.value} requires predecessor {predecessor.value} in its parent"
            )
        predecessor_manifest = (
            f"{parent_snapshot_id}:runs/{run_id}/{predecessor.value}/manifest.json"
        )
        try:
            self._git("cat-file", "-e", predecessor_manifest)
        except SnapshotError as error:
            raise SnapshotError(
                f"stage {stage.value} requires predecessor {predecessor.value} "
                f"for run {run_id} in its parent snapshot"
            ) from error

    def _validate_cumulative_stage(
        self,
        artifacts: ArtifactStore,
        stage_manifest: StageManifest,
        run_id: str,
        stage: PipelineStage,
        parent_snapshot_id: str | None,
    ) -> None:
        predecessor = STAGE_PREDECESSOR[stage]
        if predecessor is None:
            return
        if parent_snapshot_id is None:
            raise SnapshotError(f"cumulative stage {stage.value} has no parent snapshot")

        with self._detached_worktree(parent_snapshot_id) as checkout:
            predecessor_artifacts = ArtifactStore(
                checkout,
                registry=_artifact_registry(self._artifacts),
            )
            predecessor_manifest = predecessor_artifacts.validate_stage(
                run_id,
                predecessor.value,
                canonical=True,
            )
            self._validate_stage_artifact_allowlist(predecessor_manifest, predecessor)
            self._validate_model_traces(
                predecessor_artifacts,
                predecessor_manifest,
                run_id,
                predecessor,
            )
            successor_by_name = {artifact.name: artifact for artifact in stage_manifest.artifacts}
            for predecessor_artifact in predecessor_manifest.artifacts:
                if predecessor_artifact.name == "pipeline_manifests":
                    continue
                successor_artifact = successor_by_name.get(predecessor_artifact.name)
                if successor_artifact is None:
                    raise SnapshotError(
                        "cumulative stage is missing predecessor artifact: "
                        f"{predecessor_artifact.name}"
                    )
                predecessor_records = self._canonical_artifact_records(
                    predecessor_artifacts,
                    run_id,
                    predecessor,
                    predecessor_artifact.path,
                )
                successor_records = self._canonical_artifact_records(
                    artifacts,
                    run_id,
                    stage,
                    successor_artifact.path,
                )
                if predecessor_records - successor_records:
                    raise SnapshotError(
                        "cumulative stage dropped predecessor records from artifact: "
                        f"{predecessor_artifact.name}"
                    )

    @staticmethod
    def _canonical_artifact_records(
        artifacts: ArtifactStore,
        run_id: str,
        stage: PipelineStage,
        artifact_path: str,
    ) -> Counter[bytes]:
        data = (artifacts.layout.canonical_stage(run_id, stage.value) / artifact_path).read_bytes()
        if not data:
            return Counter()
        return Counter(data[:-1].split(b"\n"))

    def _reject_staged_paths_outside(self, run_id: str, stage: PipelineStage) -> None:
        output = self._git(
            "diff",
            "--cached",
            "--name-status",
            "--diff-filter=ACDMRTUXB",
            "-z",
            "--",
        )
        prefix = f"runs/{run_id}/{stage.value}/"
        forbidden = tuple(
            path
            for path in self._staged_paths(output)
            if path != ".gitignore" and not path.startswith(prefix)
        )
        if forbidden:
            raise SnapshotError(f"staged path is outside the snapshot allowlist: {forbidden[0]}")

    @staticmethod
    def _staged_paths(output: str) -> tuple[str, ...]:
        fields = tuple(field for field in output.split("\0") if field)
        paths: list[str] = []
        index = 0
        while index < len(fields):
            status = fields[index]
            index += 1
            path_count = 2 if status.startswith(("R", "C")) else 1
            if index + path_count > len(fields):
                raise SnapshotError("Git returned an invalid staged-path record")
            paths.extend(fields[index : index + path_count])
            index += path_count
        return tuple(paths)

    @contextmanager
    def _detached_worktree(self, snapshot_id: str) -> Generator[Path, None, None]:
        checkout = Path(tempfile.mkdtemp(prefix="ke-memory-snapshot-verify-"))
        added = False
        try:
            self._git("worktree", "add", "--detach", "--quiet", str(checkout), snapshot_id)
            added = True
            yield checkout
        finally:
            active_error = sys.exc_info()[0] is not None
            cleanup_error: SnapshotError | None = None
            if added:
                try:
                    self._git("worktree", "remove", "--force", str(checkout))
                except SnapshotError as error:
                    cleanup_error = error
            shutil.rmtree(checkout, ignore_errors=True)
            try:
                self._git("worktree", "prune")
            except SnapshotError as error:
                cleanup_error = cleanup_error or error
            if cleanup_error is not None and not active_error:
                raise cleanup_error


def _artifact_registry(artifacts: ArtifactStore) -> Mapping[str, type[BaseModel]]:
    """The registry to validate against: the one this store was built with.

    Previously this merged the module-level pipeline and evaluation registries, which
    made a pipeline-only process fail -- the evaluation registry is populated by
    importing evaluation, and a pipeline run has no reason to. The artifact store
    already carries whatever the composition root registered, so reading it there is
    both correct and narrower: a store built without evaluation types validates
    without them.
    """
    return artifacts.registry
