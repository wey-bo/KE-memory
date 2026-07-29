"""Deterministic projection of validated knowledge and reconciliation operations."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ACTIVE_STATUSES = frozenset({"active", "active_conflict"})


def _tuple_add(values: tuple[str, ...], additions: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(set(values).union(additions)))


def _source_turn(knowledge: Mapping[str, Any]) -> int:
    direct = knowledge.get("turn_index")
    if isinstance(direct, int) and direct >= 0:
        return direct
    turns = [
        item.get("turn_index")
        for item in knowledge.get("evidence", [])
        if isinstance(item, Mapping) and isinstance(item.get("turn_index"), int)
    ]
    return min(turns, default=-1)


def _equivalence_signature(knowledge: Mapping[str, Any]) -> str:
    semantic = {
        "candidate_id": knowledge.get("candidate_id"),
        "subject": knowledge.get("subject"),
        "predicate": knowledge.get("predicate"),
        "object": knowledge.get("object"),
        "qualifiers": knowledge.get("qualifiers"),
    }
    return json.dumps(semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class ProjectedKnowledge:
    knowledge: dict[str, Any]
    stage: str
    source_turn: int
    status: str = "active"
    confirmed_by: tuple[str, ...] = ()
    conflicts_with: tuple[str, ...] = ()
    replacement_id: str | None = None
    replaces: tuple[str, ...] = ()
    supersedes: tuple[str, ...] = ()
    added_by: tuple[str, ...] = ()
    equivalence_group: str | None = None

    @property
    def knowledge_id(self) -> str:
        return str(self.knowledge["knowledge_id"])

    @property
    def candidate_id(self) -> str:
        return str(self.knowledge["candidate_id"])

    @property
    def evidence(self) -> tuple[Any, ...]:
        return tuple(self.knowledge.get("evidence", []))

    def to_dict(self) -> dict[str, Any]:
        return {
            "knowledge": copy.deepcopy(self.knowledge),
            "projection": {
                "stage": self.stage,
                "source_turn": self.source_turn,
                "status": self.status,
                "confirmed_by": list(self.confirmed_by),
                "conflicts_with": list(self.conflicts_with),
                "replacement_id": self.replacement_id,
                "replaces": list(self.replaces),
                "supersedes": list(self.supersedes),
                "added_by": list(self.added_by),
                "equivalence_group": self.equivalence_group,
            },
        }


@dataclass(frozen=True)
class FinalKnowledgeView:
    records: tuple[ProjectedKnowledge, ...]
    active_ids: tuple[str, ...]
    provenance: Mapping[str, Any] | None = None

    @property
    def by_id(self) -> dict[str, ProjectedKnowledge]:
        return {item.knowledge_id: item for item in self.records}

    def to_dict(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for item in self.records:
            counts[item.status] = counts.get(item.status, 0) + 1
        value = {
            "schema_version": "final-knowledge-v1",
            "active_ids": list(self.active_ids),
            "counts": {key: counts[key] for key in sorted(counts)},
            "records": [item.to_dict() for item in self.records],
        }
        if self.provenance is not None:
            value["provenance"] = copy.deepcopy(dict(self.provenance))
        return value


@dataclass(frozen=True)
class ProjectionArtifact:
    path: Path
    sha256: str
    active_count: int
    counts: Mapping[str, int]
    view: FinalKnowledgeView
    deterministic_replay: bool


def _record(knowledge: Mapping[str, Any], stage: str) -> ProjectedKnowledge:
    value = copy.deepcopy(dict(knowledge))
    knowledge_id = value.get("knowledge_id")
    candidate_id = value.get("candidate_id")
    if not isinstance(knowledge_id, str) or not knowledge_id.strip():
        raise ValueError("knowledge record has no valid knowledge_id")
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        raise ValueError(f"knowledge {knowledge_id} has no valid candidate_id")
    return ProjectedKnowledge(knowledge=value, stage=stage, source_turn=_source_turn(value))


def project_final_knowledge(
    first_pass_knowledge: Sequence[Mapping[str, Any]],
    dialogue_outputs: Sequence[Mapping[str, Any]],
) -> FinalKnowledgeView:
    """Apply append-only dialogue operations without mutating the inputs."""
    records: dict[str, ProjectedKnowledge] = {}
    for item in first_pass_knowledge:
        record = _record(item, "turn")
        if record.knowledge_id in records:
            raise ValueError(f"duplicate knowledge ID: {record.knowledge_id}")
        records[record.knowledge_id] = record

    operations: list[Mapping[str, Any]] = []
    for output in dialogue_outputs:
        for item in output.get("new_knowledge", []):
            record = _record(item, "dialogue")
            if record.knowledge_id in records:
                raise ValueError(f"duplicate knowledge ID: {record.knowledge_id}")
            records[record.knowledge_id] = record
        operations.extend(output.get("operations", []))

    operation_ids: set[str] = set()
    for operation in operations:
        operation_id = operation.get("operation_id")
        kind = operation.get("operation")
        targets = operation.get("targets", [])
        replacement_id = operation.get("replacement")
        if not isinstance(operation_id, str) or not operation_id:
            raise ValueError("operation has no valid operation_id")
        if operation_id in operation_ids:
            raise ValueError(f"duplicate operation ID: {operation_id}")
        operation_ids.add(operation_id)
        if not isinstance(targets, list) or any(target not in records for target in targets):
            raise ValueError(f"operation {operation_id} has unknown target")
        if replacement_id is not None and replacement_id not in records:
            raise ValueError(f"operation {operation_id} has unknown replacement")

        if kind == "confirm":
            for target in targets:
                records[target] = replace(
                    records[target], confirmed_by=_tuple_add(records[target].confirmed_by, [operation_id])
                )
        elif kind == "correct":
            if replacement_id is None:
                raise ValueError(f"correct operation {operation_id} has no replacement")
            for target in targets:
                if records[target].status != "active":
                    raise ValueError(f"correct operation {operation_id} targets non-active knowledge")
                records[target] = replace(records[target], status="corrected", replacement_id=replacement_id)
            replacement = records[replacement_id]
            records[replacement_id] = replace(
                replacement, replaces=_tuple_add(replacement.replaces, targets)
            )
        elif kind == "supersede":
            for target in targets:
                if records[target].status != "active":
                    raise ValueError(f"supersede operation {operation_id} targets non-active knowledge")
                records[target] = replace(records[target], status="superseded", replacement_id=replacement_id)
            if replacement_id is not None:
                replacement = records[replacement_id]
                records[replacement_id] = replace(
                    replacement, supersedes=_tuple_add(replacement.supersedes, targets)
                )
        elif kind == "conflict":
            for target in targets:
                if records[target].status not in ACTIVE_STATUSES:
                    raise ValueError(f"conflict operation {operation_id} targets inactive knowledge")
                peers = [item for item in targets if item != target]
                records[target] = replace(
                    records[target],
                    status="active_conflict",
                    conflicts_with=_tuple_add(records[target].conflicts_with, peers),
                )
        elif kind == "add":
            if replacement_id is None:
                raise ValueError(f"add operation {operation_id} has no replacement")
            replacement = records[replacement_id]
            records[replacement_id] = replace(
                replacement, added_by=_tuple_add(replacement.added_by, [operation_id])
            )
        else:
            raise ValueError(f"unknown operation kind: {kind}")

    groups: dict[str, list[str]] = {}
    for knowledge_id, record in records.items():
        groups.setdefault(_equivalence_signature(record.knowledge), []).append(knowledge_id)
    for signature, identifiers in groups.items():
        if len(identifiers) < 2:
            continue
        group_id = "EQ_" + hashlib.sha256(signature.encode("utf-8")).hexdigest()[:16]
        for knowledge_id in identifiers:
            records[knowledge_id] = replace(records[knowledge_id], equivalence_group=group_id)

    ordered = tuple(sorted(
        records.values(), key=lambda item: (item.candidate_id, item.source_turn, item.knowledge_id)
    ))
    active_ids = tuple(item.knowledge_id for item in ordered if item.status in ACTIVE_STATUSES)
    return FinalKnowledgeView(records=ordered, active_ids=active_ids)


def render_final_knowledge(view: FinalKnowledgeView) -> bytes:
    """Render canonical UTF-8 JSON with a trailing newline."""
    text = json.dumps(view.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return (text + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_json(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    try:
        data = path.read_bytes()
        value = json.loads(data.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"could not parse {label}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return data, value


def _manifest_files(directory: Path, entries: Sequence[Mapping[str, Any]], label: str) -> dict[str, Path]:
    expected: dict[str, Path] = {}
    for entry in entries:
        filename = entry.get("validated_file")
        if not isinstance(filename, str) or not filename.endswith(".json") or filename == "manifest.json":
            raise ValueError(f"{label} manifest has an invalid validated_file")
        if filename in expected:
            raise ValueError(f"{label} manifest repeats {filename}")
        expected[filename] = directory / filename
    actual = {path.name for path in directory.glob("*.json") if path.name != "manifest.json"}
    if actual != set(expected):
        raise ValueError(f"{label} validated file set does not match its manifest")
    return expected


def project_validated_manifests(
    turn_manifest_path: str | Path,
    dialogue_manifest_path: str | Path,
) -> FinalKnowledgeView:
    """Load validated artifacts, verify their hash closure, and project them."""
    turn_manifest_file = Path(turn_manifest_path).resolve()
    dialogue_manifest_file = Path(dialogue_manifest_path).resolve()
    turn_bytes, turn_manifest = _read_json(turn_manifest_file, "turn validated manifest")
    dialogue_bytes, dialogue_manifest = _read_json(dialogue_manifest_file, "dialogue validated manifest")
    turn_manifest_hash = _sha256(turn_bytes)
    dialogue_manifest_hash = _sha256(dialogue_bytes)
    if dialogue_manifest.get("first_pass_manifest_sha256") != turn_manifest_hash:
        raise ValueError("dialogue manifest does not reference the exact turn validated manifest")
    if dialogue_manifest.get("source_segments_sha256") != turn_manifest.get("source_segments_sha256"):
        raise ValueError("turn and dialogue manifests disagree on source-segments hash")

    turn_entries = turn_manifest.get("turns")
    dialogue_entries = dialogue_manifest.get("candidates")
    if not isinstance(turn_entries, list) or not isinstance(dialogue_entries, list):
        raise ValueError("validated manifests have invalid entry collections")
    turn_files = _manifest_files(turn_manifest_file.parent, turn_entries, "turn")
    dialogue_files = _manifest_files(dialogue_manifest_file.parent, dialogue_entries, "dialogue")

    bound_first_pass: dict[str, str] = {}
    for entry in dialogue_entries:
        if entry.get("raw_sha256_before") != entry.get("raw_sha256_after"):
            raise ValueError("dialogue manifest records an unstable raw hash")
        first_pass_files = entry.get("first_pass_files")
        if not isinstance(first_pass_files, list):
            raise ValueError("dialogue manifest has invalid first_pass_files")
        for item in first_pass_files:
            if not isinstance(item, dict):
                raise ValueError("dialogue manifest has invalid first-pass file binding")
            filename, digest = item.get("canonical_filename"), item.get("sha256")
            if not isinstance(filename, str) or not isinstance(digest, str):
                raise ValueError("dialogue manifest has invalid first-pass file binding")
            if filename in bound_first_pass:
                raise ValueError(f"dialogue manifest repeats first-pass file {filename}")
            bound_first_pass[filename] = digest
    if set(bound_first_pass) != set(turn_files):
        raise ValueError("dialogue manifest does not bind every first-pass file exactly once")

    first_pass_knowledge: list[dict[str, Any]] = []
    for entry in turn_entries:
        filename = str(entry["validated_file"])
        if entry.get("raw_sha256_before") != entry.get("raw_sha256_after"):
            raise ValueError("turn manifest records an unstable raw hash")
        data, output = _read_json(turn_files[filename], f"turn validated output {filename}")
        if _sha256(data) != bound_first_pass[filename]:
            raise ValueError(f"first-pass file hash mismatch: {filename}")
        if output.get("candidate_id") != entry.get("candidate_id") or output.get("turn_index") != entry.get("turn_index"):
            raise ValueError(f"turn validated identity mismatch: {filename}")
        knowledge = output.get("knowledge")
        if not isinstance(knowledge, list):
            raise ValueError(f"turn validated knowledge is invalid: {filename}")
        first_pass_knowledge.extend(knowledge)

    dialogue_outputs: list[dict[str, Any]] = []
    for entry in dialogue_entries:
        filename = str(entry["validated_file"])
        data, output = _read_json(dialogue_files[filename], f"dialogue validated output {filename}")
        expected_hash = entry.get("validated_sha256")
        if not isinstance(expected_hash, str) or _sha256(data) != expected_hash:
            raise ValueError(f"dialogue validated file hash mismatch: {filename}")
        if output.get("candidate_id") != entry.get("candidate_id"):
            raise ValueError(f"dialogue validated identity mismatch: {filename}")
        dialogue_outputs.append(output)

    view = project_final_knowledge(first_pass_knowledge, dialogue_outputs)
    return replace(view, provenance={
        "turn_manifest": str(turn_manifest_file),
        "turn_manifest_sha256": turn_manifest_hash,
        "dialogue_manifest": str(dialogue_manifest_file),
        "dialogue_manifest_sha256": dialogue_manifest_hash,
        "source_segments_sha256": turn_manifest.get("source_segments_sha256"),
    })


def write_projected_knowledge(
    turn_manifest_path: str | Path,
    dialogue_manifest_path: str | Path,
    output_path: str | Path,
) -> ProjectionArtifact:
    """Project validated artifacts and atomically publish canonical JSON."""
    artifact, content = _build_projection_artifact(turn_manifest_path, dialogue_manifest_path, output_path)
    destination = Path(output_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name(destination.name + ".new")
    try:
        staging.write_bytes(content)
        os.replace(staging, destination)
    except Exception:
        staging.unlink(missing_ok=True)
        raise
    return artifact


def _build_projection_artifact(
    turn_manifest_path: str | Path,
    dialogue_manifest_path: str | Path,
    output_path: str | Path,
) -> tuple[ProjectionArtifact, bytes]:
    first_view = project_validated_manifests(turn_manifest_path, dialogue_manifest_path)
    second_view = project_validated_manifests(turn_manifest_path, dialogue_manifest_path)
    content = render_final_knowledge(first_view)
    if content != render_final_knowledge(second_view):
        raise ValueError("projection replay is not deterministic")
    counts: dict[str, int] = {}
    for record in first_view.records:
        counts[record.status] = counts.get(record.status, 0) + 1
    return ProjectionArtifact(
        path=Path(output_path).resolve(),
        sha256=_sha256(content),
        active_count=len(first_view.active_ids),
        counts={key: counts[key] for key in sorted(counts)},
        view=first_view,
        deterministic_replay=True,
    ), content


def _projection_run_bytes(run_path: Path, artifact: ProjectionArtifact) -> bytes:
    _, run = _read_json(run_path, "knowledge extraction run")
    provenance = artifact.view.provenance
    if provenance is None:
        raise ValueError("projection artifact has no input provenance")
    expected = {
        "turn": provenance["turn_manifest_sha256"],
        "dialogue": provenance["dialogue_manifest_sha256"],
        "segments": provenance["source_segments_sha256"],
    }
    actual = {
        "turn": run.get("turn_pass", {}).get("validated_manifest", {}).get("sha256"),
        "dialogue": run.get("dialogue_pass", {}).get("validated_manifest", {}).get("sha256"),
        "segments": run.get("source_segments", {}).get("sha256"),
    }
    if actual != expected:
        raise ValueError("run metadata does not match projection input manifests")
    run["projection"] = {
        "status": "projected",
        "turn_manifest_sha256": expected["turn"],
        "dialogue_manifest_sha256": expected["dialogue"],
        "source_segments_sha256": expected["segments"],
        "output_path": str(artifact.path),
        "output_sha256": artifact.sha256,
        "active_count": artifact.active_count,
        "counts": dict(artifact.counts),
        "deterministic_replay": artifact.deterministic_replay,
    }
    return (json.dumps(run, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def record_projection_run(run_path: str | Path, artifact: ProjectionArtifact) -> None:
    """Atomically record projection provenance without changing earlier run sections."""
    destination = Path(run_path).resolve()
    content = _projection_run_bytes(destination, artifact)
    staging = destination.with_name(destination.name + ".new")
    try:
        staging.write_bytes(content)
        os.replace(staging, destination)
    except Exception:
        staging.unlink(missing_ok=True)
        raise


def project_and_record(
    turn_manifest_path: str | Path,
    dialogue_manifest_path: str | Path,
    output_path: str | Path,
    run_path: str | Path,
) -> ProjectionArtifact:
    """Publish final knowledge and matching run metadata as one recoverable transaction."""
    output = Path(output_path).resolve()
    run = Path(run_path).resolve()
    artifact, output_content = _build_projection_artifact(turn_manifest_path, dialogue_manifest_path, output)
    run_content = _projection_run_bytes(run, artifact)
    output.parent.mkdir(parents=True, exist_ok=True)
    output_staging = output.with_name(output.name + ".new")
    run_staging = run.with_name(run.name + ".new")
    output_backup = output.with_name(output.name + ".backup")
    if output_backup.exists():
        raise ValueError(f"projection backup already exists: {output_backup}")
    had_output = output.exists()
    try:
        output_staging.write_bytes(output_content)
        run_staging.write_bytes(run_content)
        if had_output:
            os.replace(output, output_backup)
        os.replace(output_staging, output)
        try:
            os.replace(run_staging, run)
        except Exception:
            output.unlink(missing_ok=True)
            if had_output and output_backup.exists():
                os.replace(output_backup, output)
            raise
        output_backup.unlink(missing_ok=True)
    except Exception:
        output_staging.unlink(missing_ok=True)
        run_staging.unlink(missing_ok=True)
        if had_output and not output.exists() and output_backup.exists():
            os.replace(output_backup, output)
        raise
    return artifact
