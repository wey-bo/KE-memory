from __future__ import annotations

from pathlib import Path

from ke_memory_demo.core.json import canonical_json
from ke_memory_demo.domain import Exchange, Message, MessageRole
from ke_memory_demo.ontology import IndexIdentity
from ke_memory_demo.pipeline import (
    PIPELINE_ARTIFACT_REGISTRY,
    OntologyRunIdentity,
    PipelineRunManifest,
    PipelineStage,
)
from ke_memory_demo.settings import EvaluationConcurrencySettings
from ke_memory_demo.snapshots import GitSnapshotStore
from ke_memory_demo.storage import ArtifactStore


def initialized_state(tmp_path: Path) -> tuple[ArtifactStore, GitSnapshotStore]:
    artifacts = ArtifactStore(tmp_path / "state", registry=PIPELINE_ARTIFACT_REGISTRY)
    snapshots = GitSnapshotStore.init(artifacts.root, artifacts)
    return artifacts, snapshots


def write_ingested_stage(artifacts: ArtifactStore, parent_snapshot_id: str | None) -> None:
    exchange = Exchange(
        id="exchange-1",
        session_id="session-1",
        user=Message(
            id="message-user-1",
            role=MessageRole.USER,
            content="Remember tea.",
            source_order=0,
        ),
        assistant=Message(
            id="message-assistant-1",
            role=MessageRole.ASSISTANT,
            content="Noted.",
            source_order=1,
        ),
        global_ordinal=0,
    )
    manifest = PipelineRunManifest(
        run_id="run-1",
        stage=PipelineStage.INGESTED,
        parent_snapshot_id=parent_snapshot_id,
        code_commit="a" * 40,
        dataset_sha256="b" * 64,
        selected_directories=(1, 2, 3),
        ontology=OntologyRunIdentity(
            index=IndexIdentity(
                index_name="test-ontology",
                index_uuid="test-index-uuid",
                mapping_sha256="c" * 64,
            ),
            normalization_mode="bounded-best-effort",
        ),
        embedding_enabled=False,
        concurrency=EvaluationConcurrencySettings(
            turn_workers=1,
            session_workers=1,
            question_workers=1,
            judge_workers=1,
        ),
        record_counts={"exchanges": 1, "pipeline_manifests": 1},
    )
    with artifacts.stage_writer("run-1", PipelineStage.INGESTED.value) as writer:
        writer.write("exchanges", [exchange])
        writer.write("pipeline_manifests", [manifest])


def only_pipeline_manifest(
    artifacts: ArtifactStore,
    run_id: str,
    stage: str,
) -> PipelineRunManifest:
    records = tuple(
        artifacts.read_jsonl(run_id, stage, "pipeline_manifests", PipelineRunManifest)
    )
    assert len(records) == 1
    return records[0]


def test_snapshot_is_commit_sha_without_self_reference(tmp_path: Path) -> None:
    artifacts, snapshots = initialized_state(tmp_path)
    write_ingested_stage(artifacts, parent_snapshot_id=None)

    result = snapshots.commit_stage("run-1", PipelineStage.INGESTED)

    assert result.snapshot_id == snapshots.head()
    assert len(result.snapshot_id) == 40
    manifest = only_pipeline_manifest(artifacts, "run-1", "ingested")
    assert result.snapshot_id not in canonical_json(manifest).decode()


def test_snapshot_excludes_cache_secrets_and_complete_vocabulary(tmp_path: Path) -> None:
    artifacts, snapshots = initialized_state(tmp_path)
    write_ingested_stage(artifacts, parent_snapshot_id=None)
    artifacts.cache_path("run-1").parent.mkdir(parents=True, exist_ok=True)
    artifacts.cache_path("run-1").write_bytes(b"sqlite")
    (artifacts.root / ".env.local").write_text("SECRET=value")

    result = snapshots.commit_stage("run-1", PipelineStage.INGESTED)
    names = snapshots.tracked_files(result.snapshot_id)

    assert not any("cache/" in name or name.endswith(".sqlite3") for name in names)
    assert ".env.local" not in names
    assert not any("complete-es-vocabulary" in name for name in names)


def test_verify_checks_out_and_revalidates_stage_bytes(tmp_path: Path) -> None:
    artifacts, snapshots = initialized_state(tmp_path)
    write_ingested_stage(artifacts, parent_snapshot_id=None)
    result = snapshots.commit_stage("run-1", PipelineStage.INGESTED)

    assert snapshots.verify(result.snapshot_id, "run-1", PipelineStage.INGESTED).verified
