from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest

from ke_memory_demo.core.json import canonical_json
from ke_memory_demo.domain import Exchange, Message, MessageRole
from ke_memory_demo.evaluation import EvaluationFailure
from ke_memory_demo.infra.telemetry import ModelTrace, TraceContext, UsageRecord
from ke_memory_demo.ontology import IndexIdentity, OntologyRelation, OntologyTerm
from ke_memory_demo.pipeline import (
    EVALUATION_ARTIFACT_REGISTRY,
    PIPELINE_ARTIFACT_REGISTRY,
    OntologyRunIdentity,
    PipelineRunManifest,
    PipelineStage,
)
from ke_memory_demo.settings import EvaluationConcurrencySettings
from ke_memory_demo.snapshots import GitSnapshotStore, SnapshotError
from ke_memory_demo.storage import ArtifactStore


def test_snapshots_package_imports_in_a_fresh_interpreter() -> None:
    completed = subprocess.run(
        (
            sys.executable,
            "-c",
            "from ke_memory_demo.snapshots import GitSnapshotStore; "
            "print(GitSnapshotStore.__name__)",
        ),
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "GitSnapshotStore"


def initialized_state(tmp_path: Path) -> tuple[ArtifactStore, GitSnapshotStore]:
    artifacts = ArtifactStore(tmp_path / "state", registry=PIPELINE_ARTIFACT_REGISTRY)
    snapshots = GitSnapshotStore.init(artifacts.root, artifacts)
    return artifacts, snapshots


def write_ingested_stage(
    artifacts: ArtifactStore,
    parent_snapshot_id: str | None,
    *,
    matched_document_ids: tuple[str, ...] = (),
    ontology_terms: tuple[OntologyTerm, ...] = (),
    ontology_relations: tuple[OntologyRelation, ...] = (),
    evaluation_failures: tuple[EvaluationFailure, ...] = (),
    model_traces: tuple[ModelTrace, ...] = (),
) -> None:
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
            matched_document_ids=matched_document_ids,
        ),
        embedding_enabled=False,
        concurrency=EvaluationConcurrencySettings(
            turn_workers=1,
            session_workers=1,
            question_workers=1,
            judge_workers=1,
        ),
        record_counts={
            "exchanges": 1,
            **({"evaluation_failures": len(evaluation_failures)} if evaluation_failures else {}),
            **({"model_traces": len(model_traces)} if model_traces else {}),
            **({"ontology_relations": len(ontology_relations)} if ontology_relations else {}),
            **({"ontology_terms": len(ontology_terms)} if ontology_terms else {}),
            "pipeline_manifests": 1,
        },
    )
    with artifacts.stage_writer("run-1", PipelineStage.INGESTED.value) as writer:
        writer.write("exchanges", [exchange])
        if evaluation_failures:
            writer.write("evaluation_failures", evaluation_failures)
        if model_traces:
            writer.write("model_traces", model_traces)
        if ontology_relations:
            writer.write("ontology_relations", ontology_relations)
        if ontology_terms:
            writer.write("ontology_terms", ontology_terms)
        writer.write("pipeline_manifests", [manifest])


def direct_commit(artifacts: ArtifactStore, message: str) -> str:
    subprocess.run(
        (
            "git",
            "-C",
            str(artifacts.root),
            "add",
            "--",
            ".gitignore",
            "runs/run-1/ingested",
        ),
        check=True,
    )
    subprocess.run(
        ("git", "-C", str(artifacts.root), "commit", "--quiet", "-m", message),
        check=True,
    )
    completed = subprocess.run(
        ("git", "-C", str(artifacts.root), "rev-parse", "HEAD"),
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def unsafe_model_trace() -> ModelTrace:
    return ModelTrace(
        context=TraceContext(operation="pipeline-preflight", metadata={"run_id": "run-1"}),
        transport_attempt=1,
        structured_request=1,
        latency_seconds=0.25,
        request={"messages": [{"content": "private prompt"}]},
        response={"choices": [{"content": "private response"}]},
        error=None,
        usage=UsageRecord(
            request_id="request-1",
            model="test-model",
            latency_seconds=0.25,
            input_tokens=4,
            output_tokens=2,
            total_tokens=6,
        ),
    )


def only_pipeline_manifest(
    artifacts: ArtifactStore,
    run_id: str,
    stage: str,
) -> PipelineRunManifest:
    records = tuple(artifacts.read_jsonl(run_id, stage, "pipeline_manifests", PipelineRunManifest))
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


def test_stage_artifact_allowlist_rejects_evaluation_records_before_and_after_commit(
    tmp_path: Path,
) -> None:
    registry = {
        **PIPELINE_ARTIFACT_REGISTRY,
        **dict(EVALUATION_ARTIFACT_REGISTRY),
    }
    failure = EvaluationFailure(
        question_id="question-1",
        stage="judge",
        error_type="TimeoutError",
        message="judge timed out",
    )
    artifacts = ArtifactStore(tmp_path / "commit" / "state", registry=registry)
    snapshots = GitSnapshotStore.init(artifacts.root, artifacts)
    write_ingested_stage(
        artifacts,
        parent_snapshot_id=None,
        evaluation_failures=(failure,),
    )

    with pytest.raises(SnapshotError, match="evaluation_failures.*ingested"):
        snapshots.commit_stage("run-1", PipelineStage.INGESTED)

    bypass_artifacts = ArtifactStore(tmp_path / "verify" / "state", registry=registry)
    bypass_snapshots = GitSnapshotStore.init(bypass_artifacts.root, bypass_artifacts)
    write_ingested_stage(
        bypass_artifacts,
        parent_snapshot_id=None,
        evaluation_failures=(failure,),
    )
    snapshot_id = direct_commit(bypass_artifacts, "legacy invalid stage")

    with pytest.raises(SnapshotError, match="evaluation_failures.*ingested"):
        bypass_snapshots.verify(snapshot_id, "run-1", PipelineStage.INGESTED)


def test_model_trace_bodies_are_rejected_before_and_after_commit(tmp_path: Path) -> None:
    artifacts, snapshots = initialized_state(tmp_path / "commit")
    write_ingested_stage(
        artifacts,
        parent_snapshot_id=None,
        model_traces=(unsafe_model_trace(),),
    )

    with pytest.raises(SnapshotError, match="model trace.*usage/context"):
        snapshots.commit_stage("run-1", PipelineStage.INGESTED)

    bypass_artifacts, bypass_snapshots = initialized_state(tmp_path / "verify")
    write_ingested_stage(
        bypass_artifacts,
        parent_snapshot_id=None,
        model_traces=(unsafe_model_trace(),),
    )
    snapshot_id = direct_commit(bypass_artifacts, "legacy unsafe trace")

    with pytest.raises(SnapshotError, match="model trace.*usage/context"):
        bypass_snapshots.verify(snapshot_id, "run-1", PipelineStage.INGESTED)


def test_snapshot_excludes_cache_secrets_and_complete_vocabulary(tmp_path: Path) -> None:
    artifacts, snapshots = initialized_state(tmp_path / "empty-ontology")
    write_ingested_stage(artifacts, parent_snapshot_id=None)
    artifacts.cache_path("run-1").parent.mkdir(parents=True, exist_ok=True)
    artifacts.cache_path("run-1").write_bytes(b"sqlite")
    (artifacts.root / ".env.local").write_text("SECRET=value")

    result = snapshots.commit_stage("run-1", PipelineStage.INGESTED)
    names = snapshots.tracked_files(result.snapshot_id)

    assert not any("cache/" in name or name.endswith(".sqlite3") for name in names)
    assert ".env.local" not in names
    assert not any("complete-es-vocabulary" in name for name in names)

    nested_relation = OntologyRelation(
        source_document_id="term-1",
        relation_type="related-to",
        target_id="shape",
    )
    standalone_relation = OntologyRelation(
        source_document_id="term-1",
        relation_type="rooted-at",
        target_id="root",
    )
    matched_term = OntologyTerm(
        document_id="term-1",
        canonical_term="Tea",
        source_type="concept",
        role=None,
        relations=(nested_relation,),
    )
    matched_artifacts, matched_snapshots = initialized_state(tmp_path / "matched-ontology")
    write_ingested_stage(
        matched_artifacts,
        parent_snapshot_id=None,
        matched_document_ids=("term-1",),
        ontology_terms=(matched_term,),
        ontology_relations=(standalone_relation,),
    )
    matched_result = matched_snapshots.commit_stage("run-1", PipelineStage.INGESTED)
    assert matched_snapshots.verify(
        matched_result.snapshot_id,
        "run-1",
        PipelineStage.INGESTED,
    ).verified

    unbound_term_artifacts, unbound_term_snapshots = initialized_state(tmp_path / "unbound-term")
    write_ingested_stage(
        unbound_term_artifacts,
        parent_snapshot_id=None,
        ontology_terms=(matched_term,),
    )
    with pytest.raises(SnapshotError, match="matched document"):
        unbound_term_snapshots.commit_stage("run-1", PipelineStage.INGESTED)

    invalid_artifacts, invalid_snapshots = initialized_state(tmp_path / "unbound-relation-source")
    write_ingested_stage(
        invalid_artifacts,
        parent_snapshot_id=None,
        matched_document_ids=("term-1",),
        ontology_relations=(
            OntologyRelation(
                source_document_id="term-2",
                relation_type="related-to",
                target_id="root",
            ),
        ),
    )
    with pytest.raises(SnapshotError, match="matched document"):
        invalid_snapshots.commit_stage("run-1", PipelineStage.INGESTED)


def test_verify_checks_out_and_revalidates_stage_bytes(tmp_path: Path) -> None:
    artifacts, snapshots = initialized_state(tmp_path)
    write_ingested_stage(artifacts, parent_snapshot_id=None)
    ingested = snapshots.commit_stage("run-1", PipelineStage.INGESTED)
    predecessor_manifest = only_pipeline_manifest(artifacts, "run-1", "ingested")
    predecessor_exchange = tuple(artifacts.read_jsonl("run-1", "ingested", "exchanges", Exchange))[
        0
    ]
    successor_base = {
        **predecessor_manifest.model_dump(mode="python"),
        "stage": PipelineStage.TURN_KE_EXTRACTED,
        "parent_snapshot_id": ingested.snapshot_id,
    }

    missing_manifest = PipelineRunManifest.model_validate(
        {**successor_base, "record_counts": {"pipeline_manifests": 1}}
    )
    with artifacts.stage_writer("run-1", PipelineStage.TURN_KE_EXTRACTED.value) as writer:
        writer.write("pipeline_manifests", [missing_manifest])
    with pytest.raises(SnapshotError, match="cumulative stage"):
        snapshots.commit_stage("run-1", PipelineStage.TURN_KE_EXTRACTED)

    appended_exchange = Exchange(
        id="exchange-2",
        session_id="session-1",
        user=Message(
            id="message-user-2",
            role=MessageRole.USER,
            content="Remember coffee.",
            source_order=2,
        ),
        assistant=Message(
            id="message-assistant-2",
            role=MessageRole.ASSISTANT,
            content="Noted.",
            source_order=3,
        ),
        global_ordinal=1,
    )
    replacement_manifest = PipelineRunManifest.model_validate(
        {
            **successor_base,
            "record_counts": {"exchanges": 1, "pipeline_manifests": 1},
        }
    )
    with artifacts.stage_writer("run-1", PipelineStage.TURN_KE_EXTRACTED.value) as writer:
        writer.write("exchanges", [appended_exchange])
        writer.write("pipeline_manifests", [replacement_manifest])
    with pytest.raises(SnapshotError, match="cumulative stage"):
        snapshots.commit_stage("run-1", PipelineStage.TURN_KE_EXTRACTED)

    cumulative_manifest = PipelineRunManifest.model_validate(
        {
            **successor_base,
            "record_counts": {"exchanges": 2, "pipeline_manifests": 1},
        }
    )
    with artifacts.stage_writer("run-1", PipelineStage.TURN_KE_EXTRACTED.value) as writer:
        writer.write("exchanges", [predecessor_exchange, appended_exchange])
        writer.write("pipeline_manifests", [cumulative_manifest])
    result = snapshots.commit_stage("run-1", PipelineStage.TURN_KE_EXTRACTED)

    assert snapshots.verify(
        result.snapshot_id,
        "run-1",
        PipelineStage.TURN_KE_EXTRACTED,
    ).verified
