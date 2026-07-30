from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal, Sequence
from urllib.request import Request, urlopen

from pydantic import Field, TypeAdapter

from .authoritative_memory import (
    MemoryRepresentationBundleV3,
    ProducerIdentity,
    StrictModel,
    canonical_sha256,
)
from .e2e_openai_producers import (
    ModelCallHashV1,
    OpenAICompatibleL1BatchProducer,
    OpenAICompatibleL2Producer,
    build_diagnostic_production_policy,
)
from .e2e_pipeline import (
    EndToEndResultV1,
    EvidenceBackedAnswerV1,
    RawTurnV1,
    build_compiler_registry,
    build_evidence_backed_answer,
    run_e2e_pipeline,
)
from .git_memory_history import (
    GitMemoryHistoryRepository,
    HistoryArtifact,
)
from .l1_ontology_linking import build_diagnostic_ontology_registry
from .query_compiler_v2 import (
    QueryCompilationResultV1,
    QueryContextV1,
    compile_natural_query,
)
from .query_compiler_v2_openai_producer import (
    OpenAICompatibleQueryDraftProducer,
    QueryDraftProductionError,
)
from .query_execution_snapshot_adapter import (
    GitMemoryViewRefV1,
    QueryExecutionResultV3,
    build_query_execution_snapshot,
    execute_authoritative_query,
)
from .turn_bundle import TurnBundleRevision


class _BufferedResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> "_BufferedResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


class _QueryRecordingOpener:
    def __init__(self, opener: Callable[..., Any]) -> None:
        self._opener = opener
        self.attempts = 0
        self.request_sha256: str | None = None
        self.response_sha256: str | None = None
        self.response_model: str | None = None

    def __call__(self, request: Request, *, timeout: int) -> _BufferedResponse:
        self.attempts += 1
        request_bytes = request.data
        if not isinstance(request_bytes, bytes):
            raise TypeError("query request body must be bytes")
        with self._opener(request, timeout=timeout) as response:
            raw = response.read()
        self.request_sha256 = hashlib.sha256(request_bytes).hexdigest()
        self.response_sha256 = hashlib.sha256(raw).hexdigest()
        try:
            response_model = json.loads(raw)["model"]
            if not isinstance(response_model, str) or not response_model.strip():
                raise TypeError("query response model is absent")
        except Exception:
            raise QueryDraftProductionError(
                "query draft response did not identify its model"
            ) from None
        self.response_model = response_model
        return _BufferedResponse(raw)

    def receipt(self, requested_model: str) -> ModelCallHashV1:
        if (
            self.request_sha256 is None
            or self.response_sha256 is None
            or self.response_model is None
        ):
            raise ValueError("query model call receipt is unavailable")
        return ModelCallHashV1(
            stage="query",
            requested_model=requested_model,
            response_model=self.response_model,
            request_sha256=self.request_sha256,
            response_sha256=self.response_sha256,
            attempts=self.attempts,
        )


class SnapshotRunReceiptV1(StrictModel):
    repository_path: str = Field(min_length=1)
    checkpoint_id: str = Field(min_length=1)
    git_commit: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    previous_git_commit: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    verification_status: Literal["valid"] = "valid"


class OpenAIE2ERunReceiptV1(StrictModel):
    schema_version: Literal["openai-e2e-run-receipt-v1"] = (
        "openai-e2e-run-receipt-v1"
    )
    workflow_run_id: str = Field(min_length=1)
    requested_model: str = Field(min_length=1)
    model_calls: tuple[ModelCallHashV1, ModelCallHashV1, ModelCallHashV1]
    snapshot: SnapshotRunReceiptV1
    answer: EvidenceBackedAnswerV1


@dataclass(frozen=True)
class OpenAIE2EOutcome:
    pipeline: EndToEndResultV1
    receipt: OpenAIE2ERunReceiptV1


class QueryOnlySnapshotReceiptV1(StrictModel):
    repository_path: str = Field(min_length=1)
    checkpoint_id: str = Field(min_length=1)
    git_commit: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    previous_git_commit: str = Field(pattern=r"^[0-9a-f]{40,64}$")
    bundle_id: str = Field(min_length=1)
    registry_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    verification_status: Literal["valid"] = "valid"


class OpenAIQueryOnlyReceiptV1(StrictModel):
    schema_version: Literal["openai-query-only-receipt-v1"] = (
        "openai-query-only-receipt-v1"
    )
    workflow_run_id: str = Field(min_length=1)
    requested_model: str = Field(min_length=1)
    closure_kind: Literal["controlled_query_only_closure"] = (
        "controlled_query_only_closure"
    )
    model_call: ModelCallHashV1
    query_call_count: Literal[1] = 1
    l1_producer_call_count: Literal[0] = 0
    l2_producer_call_count: Literal[0] = 0
    automatic_memory_write_count: Literal[0] = 0
    deterministic_replay_verified: bool
    snapshot: QueryOnlySnapshotReceiptV1
    answer: EvidenceBackedAnswerV1


class QueryOnlyPipelineResultV1(StrictModel):
    bundle: MemoryRepresentationBundleV3
    turn_bundles: tuple[TurnBundleRevision, ...]
    compilation: QueryCompilationResultV1
    execution: QueryExecutionResultV3
    deterministic_replay: QueryExecutionResultV3
    answer: EvidenceBackedAnswerV1


@dataclass(frozen=True)
class OpenAIQueryOnlyOutcome:
    pipeline: QueryOnlyPipelineResultV1
    receipt: OpenAIQueryOnlyReceiptV1


@dataclass(frozen=True)
class RecoveredCheckpoint:
    repository: GitMemoryHistoryRepository
    git_commit: str
    previous_git_commit: str
    checkpoint_id: str
    bundle: MemoryRepresentationBundleV3
    turn_bundles: tuple[TurnBundleRevision, ...]
    bundle_history_artifact: HistoryArtifact
    memory_view: GitMemoryViewRefV1


def recover_authoritative_checkpoint(
    *,
    repository_path: Path,
    expected_git_commit: str,
    expected_checkpoint_id: str,
) -> RecoveredCheckpoint:
    """Re-open and re-verify an existing authoritative checkpoint read-only."""
    repository_path = Path(repository_path).resolve()
    if not repository_path.exists():
        raise FileNotFoundError(
            "query-only execution requires an existing memory history repository"
        )
    repository = GitMemoryHistoryRepository(repository_path)
    verification = repository.verify()
    if verification.status != "valid":
        raise ValueError(
            "recovered Git history verification failed: "
            + "; ".join(verification.errors)
        )
    head_commit = repository.head_commit()
    if head_commit != expected_git_commit:
        raise ValueError(
            "recovered authoritative head does not match the expected commit"
        )
    state = repository.read_state(commit=head_commit)
    if state.checkpoint_id != expected_checkpoint_id:
        raise ValueError(
            "recovered checkpoint state does not match the expected checkpoint"
        )
    metadata = repository.read_repository_metadata(commit=head_commit)
    manifest = repository.read_checkpoint_manifest(commit=head_commit)
    if manifest.checkpoint_id != expected_checkpoint_id:
        raise ValueError(
            "recovered checkpoint manifest does not match the expected checkpoint"
        )
    parents = repository.commit_parents(head_commit)
    if len(parents) != 1:
        raise ValueError("authoritative checkpoint commit must have one parent")

    bundle_descriptors = [
        item for item in manifest.artifacts if item.artifact_kind == "l2_bundle"
    ]
    if len(bundle_descriptors) != 1:
        raise ValueError("recovered checkpoint must contain exactly one L2 bundle")
    bundle_artifact = repository.read_artifact(
        artifact_kind="l2_bundle",
        logical_id=bundle_descriptors[0].logical_id,
        revision_id=bundle_descriptors[0].revision_id,
        commit=head_commit,
    )
    bundle = MemoryRepresentationBundleV3.model_validate(
        bundle_artifact.payload["memory_representation_bundle"]
    )
    turn_bundles: list[TurnBundleRevision] = []
    for descriptor in manifest.artifacts:
        if descriptor.artifact_kind != "turn_bundle":
            continue
        artifact = repository.read_artifact(
            artifact_kind="turn_bundle",
            logical_id=descriptor.logical_id,
            revision_id=descriptor.revision_id,
            commit=head_commit,
        )
        turn_bundles.append(
            TurnBundleRevision.model_validate(
                artifact.payload["turn_bundle_revision"]
            )
        )
    if not turn_bundles:
        raise ValueError("recovered checkpoint must contain at least one turn bundle")
    turn_bundles.sort(key=lambda item: item.turn_index)
    return RecoveredCheckpoint(
        repository=repository,
        git_commit=head_commit,
        previous_git_commit=parents[0],
        checkpoint_id=expected_checkpoint_id,
        bundle=bundle,
        turn_bundles=tuple(turn_bundles),
        bundle_history_artifact=bundle_artifact,
        memory_view=GitMemoryViewRefV1(
            workspace_id=metadata.workspace_id,
            repository_epoch_id=metadata.repository_epoch_id,
            checkpoint_id=expected_checkpoint_id,
            git_commit=head_commit,
        ),
    )


def run_openai_e2e(
    *,
    turns: Sequence[RawTurnV1],
    question: str,
    repository_path: Path,
    result_path: Path,
    base_url: str,
    api_key: str,
    model: str,
    timeout_seconds: int = 600,
    max_attempts: int = 2,
    opener: Callable[..., Any] = urlopen,
) -> OpenAIE2EOutcome:
    repository_path = repository_path.resolve()
    result_path = result_path.resolve()
    raw_path = repository_path.with_name(f"{repository_path.name}.raw.json")
    if repository_path.exists() or raw_path.exists() or result_path.exists():
        raise FileExistsError(
            "model E2E repository, raw artifact, and result must be fresh"
        )
    if timeout_seconds <= 0:
        raise ValueError("model timeout must be positive")
    if max_attempts not in {1, 2}:
        raise ValueError("model attempts must be one or two")
    ordered_turns = [
        RawTurnV1.model_validate(item.model_dump(mode="json")) for item in turns
    ]
    if not ordered_turns:
        raise ValueError("model E2E requires raw turns")
    registry = build_diagnostic_ontology_registry()
    policy = build_diagnostic_production_policy(registry)

    l1_batch = OpenAICompatibleL1BatchProducer(
        registry=registry,
        policy=policy,
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        opener=opener,
    )
    bound_l1 = l1_batch.produce(ordered_turns)

    l2_producer = OpenAICompatibleL2Producer(
        registry=registry,
        policy=policy,
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        opener=opener,
    )
    query_recording_opener = _QueryRecordingOpener(opener)
    query_producer = OpenAICompatibleQueryDraftProducer(
        registry=build_compiler_registry(registry),
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        opener=query_recording_opener,
    )
    workflow_run_id = "run-openai-e2e-" + canonical_sha256(
        {
            "turns": [item.model_dump(mode="json") for item in ordered_turns],
            "question": question,
            "model": model,
        }
    )[:16]
    pipeline = run_e2e_pipeline(
        turns=ordered_turns,
        l1_producer=bound_l1,
        l2_producer=l2_producer,
        query_producer=query_producer,
        repository_path=repository_path,
        question=question,
        ontology_registry=registry,
        memory_producer=ProducerIdentity(
            workflow_run_id=workflow_run_id,
            producer_id="openai-compatible-model",
            producer_version=model,
        ),
    )
    if l1_batch.last_call is None or l2_producer.last_call is None:
        raise ValueError("model extraction call receipt is unavailable")
    receipt = OpenAIE2ERunReceiptV1(
        workflow_run_id=workflow_run_id,
        requested_model=model,
        model_calls=(
            l1_batch.last_call,
            l2_producer.last_call,
            query_recording_opener.receipt(model),
        ),
        snapshot=SnapshotRunReceiptV1(
            repository_path=pipeline.snapshot.repository_path,
            checkpoint_id=pipeline.snapshot.checkpoint_id,
            git_commit=pipeline.snapshot.git_commit,
            previous_git_commit=pipeline.snapshot.previous_git_commit,
            verification_status="valid",
        ),
        answer=pipeline.answer,
    )
    _write_receipt_exclusive(result_path, receipt)
    return OpenAIE2EOutcome(pipeline=pipeline, receipt=receipt)


def run_openai_query_only(
    *,
    question: str,
    query_time: str,
    repository_path: Path,
    expected_git_commit: str,
    expected_checkpoint_id: str,
    result_path: Path,
    query_id: str = "query-e2e-1",
    base_url: str,
    api_key: str,
    model: str,
    timeout_seconds: int = 600,
    max_attempts: int = 1,
    opener: Callable[..., Any] = urlopen,
) -> OpenAIQueryOnlyOutcome:
    """Recover an existing checkpoint and answer one query without any write."""
    repository_path = Path(repository_path).resolve()
    result_path = Path(result_path).resolve()
    if result_path.exists():
        raise FileExistsError("query-only result artifact must be fresh")
    if timeout_seconds <= 0:
        raise ValueError("model timeout must be positive")
    if max_attempts != 1:
        raise ValueError("query-only execution fixes a single model attempt")

    recovered = recover_authoritative_checkpoint(
        repository_path=repository_path,
        expected_git_commit=expected_git_commit,
        expected_checkpoint_id=expected_checkpoint_id,
    )
    registry = build_diagnostic_ontology_registry()
    compiler_registry = build_compiler_registry(registry)
    snapshot = build_query_execution_snapshot(
        repository_path=repository_path,
        bundle=recovered.bundle,
        bundle_history_artifact=recovered.bundle_history_artifact,
        turn_bundles=list(recovered.turn_bundles),
        registry=compiler_registry,
    )
    if snapshot.memory_view != recovered.memory_view:
        raise ValueError("verified snapshot memory view does not match the checkpoint")

    query_recording_opener = _QueryRecordingOpener(opener)
    query_producer = OpenAICompatibleQueryDraftProducer(
        registry=compiler_registry,
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        opener=query_recording_opener,
    )
    workflow_run_id = "run-openai-query-only-" + canonical_sha256(
        {
            "question": question,
            "query_time": query_time,
            "git_commit": recovered.git_commit,
            "checkpoint_id": recovered.checkpoint_id,
            "model": model,
        }
    )[:16]
    query_context = QueryContextV1(
        query_id=query_id,
        raw_query=question,
        query_time=query_time,
        current_user_entity_id=None,
        memory_view=recovered.memory_view,
        ontology_revision=compiler_registry.ontology_revision,
        identity_revision=compiler_registry.identity_revision,
        compiler_policy_revision="e2e-query-policy-v1",
    )
    compilation = compile_natural_query(
        question=question,
        context=query_context,
        registry=compiler_registry,
        producer=query_producer,
    )
    if compilation.status != "executable" or compilation.plan is None:
        raise ValueError(
            "query compilation abstained: "
            + ",".join([*compilation.blocked_reasons, *compilation.unresolved_slots])
        )
    if query_recording_opener.attempts != 1:
        raise ValueError("query-only execution must issue exactly one model request")

    execution = execute_authoritative_query(
        repository_path=repository_path,
        bundle=recovered.bundle,
        bundle_history_artifact=recovered.bundle_history_artifact,
        turn_bundles=list(recovered.turn_bundles),
        registry=compiler_registry,
        plan=compilation.plan,
    )
    deterministic_replay = execute_authoritative_query(
        repository_path=repository_path,
        bundle=recovered.bundle,
        bundle_history_artifact=recovered.bundle_history_artifact,
        turn_bundles=list(recovered.turn_bundles),
        registry=compiler_registry,
        plan=compilation.plan,
    )
    if execution != deterministic_replay:
        raise ValueError("deterministic query replay diverged from the execution")
    answer = build_evidence_backed_answer(
        execution=execution,
        bundle=recovered.bundle,
    )
    post_commit = recovered.repository.head_commit()
    post_state = recovered.repository.read_state(commit=post_commit)
    if (
        post_commit != recovered.git_commit
        or post_state.checkpoint_id != recovered.checkpoint_id
    ):
        raise ValueError("query-only execution must not advance authoritative history")

    receipt = OpenAIQueryOnlyReceiptV1(
        workflow_run_id=workflow_run_id,
        requested_model=model,
        model_call=query_recording_opener.receipt(model),
        deterministic_replay_verified=True,
        snapshot=QueryOnlySnapshotReceiptV1(
            repository_path=str(recovered.repository.repo_path),
            checkpoint_id=recovered.checkpoint_id,
            git_commit=recovered.git_commit,
            previous_git_commit=recovered.previous_git_commit,
            bundle_id=recovered.bundle.bundle_id,
            registry_sha256=snapshot.registry_sha256,
            snapshot_sha256=canonical_sha256(snapshot),
            authority_sha256=execution.authority.authority_sha256,
        ),
        answer=answer,
    )
    _write_query_only_receipt_exclusive(result_path, receipt)
    return OpenAIQueryOnlyOutcome(
        pipeline=QueryOnlyPipelineResultV1(
            bundle=recovered.bundle,
            turn_bundles=recovered.turn_bundles,
            compilation=compilation,
            execution=execution,
            deterministic_replay=deterministic_replay,
            answer=answer,
        ),
        receipt=receipt,
    )


def _write_query_only_receipt_exclusive(
    path: Path,
    receipt: OpenAIQueryOnlyReceiptV1,
) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        receipt.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    with path.open("xb") as stream:
        stream.write(payload)
    path.chmod(0o444)


def _write_receipt_exclusive(path: Path, receipt: OpenAIE2ERunReceiptV1) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        receipt.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    with path.open("xb") as stream:
        stream.write(payload)
    path.chmod(0o444)


def query_only_main() -> int:
    parser = argparse.ArgumentParser(
        description="Answer one query from an existing authoritative checkpoint."
    )
    parser.add_argument("--question", required=True)
    parser.add_argument("--query-time", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--expected-git-commit", required=True)
    parser.add_argument("--expected-checkpoint-id", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--query-id", default="query-e2e-1")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args()

    base_url = os.environ.get("OPENAI_BASE_URL")
    api_key = os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("OPENAI_MODEL")
    if not base_url or not api_key or not model:
        raise RuntimeError(
            "OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL are required"
        )
    outcome = run_openai_query_only(
        question=args.question,
        query_time=args.query_time,
        repository_path=Path(args.repository),
        expected_git_commit=args.expected_git_commit,
        expected_checkpoint_id=args.expected_checkpoint_id,
        result_path=Path(args.result),
        query_id=args.query_id,
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout_seconds=args.timeout_seconds,
        max_attempts=1,
    )
    print(
        json.dumps(
            {
                "status": "complete",
                "closure_kind": outcome.receipt.closure_kind,
                "git_commit": outcome.receipt.snapshot.git_commit,
                "checkpoint_id": outcome.receipt.snapshot.checkpoint_id,
                "requested_model": outcome.receipt.requested_model,
                "response_model": outcome.receipt.model_call.response_model,
                "query_call_count": outcome.receipt.query_call_count,
                "l1_producer_call_count": outcome.receipt.l1_producer_call_count,
                "l2_producer_call_count": outcome.receipt.l2_producer_call_count,
                "automatic_memory_write_count": (
                    outcome.receipt.automatic_memory_write_count
                ),
                "answer_values": outcome.receipt.answer.answer_values,
                "abstained": outcome.receipt.answer.abstained,
                "evidence_ids": [
                    span.evidence_id for span in outcome.receipt.answer.evidence_spans
                ],
                "authority_sha256": outcome.receipt.snapshot.authority_sha256,
                "result": str(Path(args.result).resolve()),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the diagnostic-ontology production model E2E smoke."
    )
    parser.add_argument("--turns", required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--max-attempts", type=int, choices=(1, 2), default=2)
    args = parser.parse_args()

    base_url = os.environ.get("OPENAI_BASE_URL")
    api_key = os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("OPENAI_MODEL")
    if not base_url or not api_key or not model:
        raise RuntimeError(
            "OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL are required"
        )
    turns_payload = json.loads(Path(args.turns).read_text(encoding="utf-8"))
    turns = TypeAdapter(list[RawTurnV1]).validate_python(turns_payload)
    outcome = run_openai_e2e(
        turns=turns,
        question=args.question,
        repository_path=Path(args.repository),
        result_path=Path(args.result),
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout_seconds=args.timeout_seconds,
        max_attempts=args.max_attempts,
    )
    print(
        json.dumps(
            {
                "status": "complete",
                "git_commit": outcome.receipt.snapshot.git_commit,
                "answer_values": outcome.receipt.answer.answer_values,
                "result": str(Path(args.result).resolve()),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
