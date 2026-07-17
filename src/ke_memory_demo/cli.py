from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Annotated, cast

import typer

from ke_memory_demo.core.json import JsonObject, JsonValue, canonical_json
from ke_memory_demo.infra.redaction import redact_text
from ke_memory_demo.pipeline import (
    PIPELINE_ARTIFACT_REGISTRY,
    MemoryPipeline,
    PipelineInvariantError,
    PipelineStage,
    PipelineStageResult,
    RuntimeFactory,
)
from ke_memory_demo.snapshots import GitSnapshotStore
from ke_memory_demo.storage import ArtifactStore


app = typer.Typer(
    add_completion=False,
    help="KE memory research demo.",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"ke-memory {package_version('ke-memory-demo')}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            help="Show the version and exit.",
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Run the KE memory research demo."""


ConfigRoot = Annotated[
    Path,
    typer.Option("--config-root", help="Project root containing config/ and .env.local."),
]
StateRoot = Annotated[
    Path,
    typer.Option("--state-root", help="Git-backed pipeline state root."),
]
RunId = Annotated[str, typer.Option("--run-id", help="Portable pipeline run identifier.")]


@app.command("preflight")
def preflight_command(
    run_id: RunId,
    config_root: ConfigRoot = Path("."),
    state_root: StateRoot = Path("state"),
) -> None:
    """Verify ontology, input, model, Git state, and disk prerequisites."""

    async def operation(factory: RuntimeFactory) -> JsonObject:
        result = await factory.build_pipeline(run_id).preflight()
        return {
            "run_id": result.run_id,
            "stage": "preflight",
            "snapshot_id": None,
            "counts": {
                "sessions": result.session_count,
                "exchanges": result.exchange_count,
                "questions": result.question_count,
            },
            "normalization_mode": result.normalization_mode,
            "ontology_identity": cast_json(result.ontology_identity.model_dump(mode="json")),
        }

    _execute_factory(config_root, state_root, operation)


@app.command("ingest")
def ingest_command(
    run_id: RunId,
    config_root: ConfigRoot = Path("."),
    state_root: StateRoot = Path("state"),
) -> None:
    """Write the canonical ingested stage after a successful preflight."""

    _execute_stage(config_root, state_root, run_id, lambda pipeline: pipeline.ingest())


@app.command("extract-turn-ke")
def extract_turn_ke_command(
    run_id: RunId,
    config_root: ConfigRoot = Path("."),
    state_root: StateRoot = Path("state"),
) -> None:
    """Extract bounded Turn KEs and reconcile lifecycle in source order."""

    _execute_stage(
        config_root,
        state_root,
        run_id,
        lambda pipeline: pipeline.extract_turn_ke(),
    )


@app.command("aggregate-session")
def aggregate_session_command(
    run_id: RunId,
    config_root: ConfigRoot = Path("."),
    state_root: StateRoot = Path("state"),
) -> None:
    """Aggregate one SessionMemory per canonical Session."""

    _execute_stage(
        config_root,
        state_root,
        run_id,
        lambda pipeline: pipeline.aggregate_sessions(),
    )


@app.command("build-semantic-dag")
def build_semantic_dag_command(
    run_id: RunId,
    config_root: ConfigRoot = Path("."),
    state_root: StateRoot = Path("state"),
) -> None:
    """Build Conversation-local semantic DAGs through depth two."""

    _execute_stage(
        config_root,
        state_root,
        run_id,
        lambda pipeline: pipeline.build_semantic_dag(),
    )


@app.command("prepare-ke")
def prepare_ke_command(
    run_id: RunId,
    config_root: ConfigRoot = Path("."),
    state_root: StateRoot = Path("state"),
) -> None:
    """Validate canonical closures and commit the ke-ready stage."""

    _execute_stage(
        config_root,
        state_root,
        run_id,
        lambda pipeline: pipeline.prepare_ke(),
    )


@app.command("run-pipeline")
def run_pipeline_command(
    run_id: RunId,
    config_root: ConfigRoot = Path("."),
    state_root: StateRoot = Path("state"),
) -> None:
    """Run the ontology-first pipeline through ke-ready."""

    async def operation(factory: RuntimeFactory) -> JsonObject:
        result = await factory.build_pipeline(run_id).run_all()
        return {
            "run_id": result.run_id,
            "stage": result.stage.value,
            "snapshot_id": result.snapshot_id,
            "counts": {
                "conversations": len(result.conversations),
                "exchanges": result.exchange_count,
                "current_knowledge_equations": len(result.current_knowledge_equations),
                "session_memories": len(result.session_memories),
                "aggregates": len(result.semantic_dag.nodes),
            },
        }

    _execute_factory(config_root, state_root, operation)


@app.command("retrieve")
def retrieve_command(
    run_id: RunId,
    snapshot_id: Annotated[
        str,
        typer.Option("--snapshot-id", help="Verified full ke-ready snapshot SHA."),
    ],
    question: Annotated[str, typer.Option("--question", help="Raw retrieval question.")],
    conversation_id: Annotated[
        str | None,
        typer.Option(
            "--conversation-id", help="Conversation scope; required for multi-scope runs."
        ),
    ] = None,
    config_root: ConfigRoot = Path("."),
    state_root: StateRoot = Path("state"),
) -> None:
    """Retrieve KE-only evidence from one verified Conversation scope."""

    async def operation(factory: RuntimeFactory) -> JsonObject:
        systems = await factory.build_ke_systems(run_id, snapshot_id)
        selected_id = conversation_id
        if selected_id is None:
            if len(systems) != 1:
                raise PipelineInvariantError(
                    "--conversation-id is required when a snapshot has multiple Conversations"
                )
            selected_id = next(iter(systems))
        system = systems.get(selected_id)
        if system is None:
            raise PipelineInvariantError(
                f"Conversation is absent from the verified snapshot: {selected_id}"
            )
        evidence = await system.retrieve(
            question,
            factory.settings.retrieval.evidence_budget_tokens,
        )
        return {
            "run_id": run_id,
            "stage": PipelineStage.KE_READY.value,
            "snapshot_id": snapshot_id,
            "conversation_id": selected_id,
            "counts": {"evidence": len(evidence)},
            "evidence": [cast_json(item.model_dump(mode="json")) for item in evidence],
            "embedding_enabled": False,
        }

    _execute_factory(config_root, state_root, operation)


@app.command("verify-snapshot")
def verify_snapshot_command(
    run_id: RunId,
    snapshot_id: Annotated[
        str,
        typer.Option("--snapshot-id", help="Full snapshot SHA to check out and validate."),
    ],
    config_root: ConfigRoot = Path("."),
    state_root: StateRoot = Path("state"),
) -> None:
    """Check out and validate a supplied ke-ready snapshot SHA."""

    del config_root

    def operation() -> JsonObject:
        artifacts = ArtifactStore(state_root, registry=PIPELINE_ARTIFACT_REGISTRY)
        snapshots = GitSnapshotStore.init(artifacts.root, artifacts)
        result = snapshots.verify(snapshot_id, run_id, PipelineStage.KE_READY)
        return {
            "run_id": result.run_id,
            "stage": result.stage.value,
            "snapshot_id": result.snapshot_id,
            "counts": {},
            "verified": result.verified,
            "stage_manifest_sha256": result.stage_manifest_sha256,
        }

    _execute(operation)


def _execute_stage(
    config_root: Path,
    state_root: Path,
    run_id: str,
    stage_call: Callable[[MemoryPipeline], Awaitable[PipelineStageResult]],
) -> None:
    async def operation(factory: RuntimeFactory) -> JsonObject:
        pipeline = factory.build_pipeline(run_id)
        await pipeline.preflight()
        result = await stage_call(pipeline)
        return {
            "run_id": result.run_id,
            "stage": result.stage.value,
            "snapshot_id": result.snapshot_id,
            "counts": cast_json(result.record_counts),
        }

    _execute_factory(config_root, state_root, operation)


def _execute_factory(
    config_root: Path,
    state_root: Path,
    operation: Callable[[RuntimeFactory], Awaitable[JsonObject]],
) -> None:
    async def invoke() -> JsonObject:
        factory = RuntimeFactory.from_paths(config_root, state_root)
        try:
            return await operation(factory)
        finally:
            await factory.aclose()

    _execute(lambda: asyncio.run(invoke()))


def _execute(operation: Callable[[], JsonObject]) -> None:
    try:
        payload = operation()
    except Exception as error:
        failure: JsonObject = {
            "error": {
                "type": type(error).__name__,
                "message": redact_text(str(error)),
            }
        }
        typer.echo(canonical_json(failure).decode("utf-8"), err=True)
        raise typer.Exit(code=1) from None
    typer.echo(canonical_json(payload).decode("utf-8"))


def cast_json(value: object) -> JsonValue:
    return cast(JsonValue, value)
