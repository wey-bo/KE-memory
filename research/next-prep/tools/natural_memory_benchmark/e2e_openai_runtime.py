from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
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
    ExtractionProfileIdentityV1,
    ModelCallHashV1,
    OpenAICompatibleL1BatchProducer,
    OpenAICompatibleL2Producer,
    build_diagnostic_production_policy,
    build_extraction_profile_identity,
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
from .identity_resolution import IdentityAwareMemoryBundleV4
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

    def receipt(
        self,
        requested_model: str,
        *,
        require_matching_response_model: bool = True,
    ) -> ModelCallHashV1:
        if (
            self.request_sha256 is None
            or self.response_sha256 is None
            or self.response_model is None
        ):
            raise ValueError("query model call receipt is unavailable")
        if (
            require_matching_response_model
            and self.response_model != requested_model
        ):
            raise ValueError(
                "query response model does not match the requested model"
            )
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
    """Historical query-only receipt. Retained so frozen artifacts still load.

    The four counters are schema literals here, so a receipt in this shape
    asserts its guarantees rather than reporting measurements. Superseded by
    ``OpenAIQueryOnlyReceiptV2``; do not emit this shape for new attempts.
    """

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


class OpenAIQueryOnlyReceiptV1Transitional(StrictModel):
    """A receipt written while ``v1`` was being changed in place.

    Attempts 4 and 5 were emitted mid-change: they carry the ``v1`` label but
    the measured ``v2`` shape, so neither the ``v1`` nor the ``v2`` model can
    load them. The bytes are frozen evidence and must not be edited, so this
    model exists to keep them machine-readable. Do not emit this shape.
    """

    schema_version: Literal["openai-query-only-receipt-v1"] = (
        "openai-query-only-receipt-v1"
    )
    workflow_run_id: str = Field(min_length=1)
    requested_model: str = Field(min_length=1)
    closure_kind: Literal["controlled_query_only_closure"] = (
        "controlled_query_only_closure"
    )
    model_call: ModelCallHashV1
    query_call_count: int = Field(ge=0)
    l1_producer_call_count: int = Field(ge=0)
    l2_producer_call_count: int = Field(ge=0)
    automatic_memory_write_count: int = Field(ge=0)
    observed_write_phases: tuple[str, ...] = Field(min_length=1)
    deterministic_replay_verified: bool
    snapshot: QueryOnlySnapshotReceiptV1
    answer: EvidenceBackedAnswerV1


class OpenAIQueryOnlyReceiptV2(StrictModel):
    """Query-only closure receipt with measured, not asserted, guarantees.

    ``v1`` declared the four guarantee counters as schema literals, so a
    violated guarantee was unrepresentable. Measuring them changed the meaning
    of the same field names, which is a contract change rather than an
    extension, so this is a new schema version and the frozen ``v1`` receipts
    keep validating against their own model.
    """

    schema_version: Literal["openai-query-only-receipt-v2"] = (
        "openai-query-only-receipt-v2"
    )
    workflow_run_id: str = Field(min_length=1)
    requested_model: str = Field(min_length=1)
    closure_kind: Literal["controlled_query_only_closure"] = (
        "controlled_query_only_closure"
    )
    model_call: ModelCallHashV1
    query_call_count: int = Field(ge=0)
    l1_producer_call_count: int = Field(ge=0)
    l2_producer_call_count: int = Field(ge=0)
    automatic_memory_write_count: int = Field(ge=0)
    observed_write_phases: tuple[str, ...] = Field(min_length=1)
    deterministic_replay_verified: bool
    #: 这次运行用的是哪个 extraction profile。可选而非必填：已冻结的 v2 收据没有
    #: 这个字段，设为必填会让那些不可变记录变成不可读。未设置时从序列化结果中
    #: 省略，这样一份冻结收据仍然逐字节往返，而不是被补上一个 null。
    extraction_profile: ExtractionProfileIdentityV1 | None = Field(
        default=None, exclude=False
    )
    snapshot: QueryOnlySnapshotReceiptV1
    answer: EvidenceBackedAnswerV1

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        payload = super().model_dump(**kwargs)
        if payload.get("extraction_profile") is None:
            payload.pop("extraction_profile", None)
        return payload


class QueryOnlyPipelineResultV1(StrictModel):
    bundle: MemoryRepresentationBundleV3
    turn_bundles: tuple[TurnBundleRevision, ...]
    compilation: QueryCompilationResultV1
    execution: QueryExecutionResultV3
    deterministic_replay: QueryExecutionResultV3
    answer: EvidenceBackedAnswerV1


def load_query_only_receipt(
    payload: dict[str, Any],
) -> (
    OpenAIQueryOnlyReceiptV1
    | OpenAIQueryOnlyReceiptV1Transitional
    | OpenAIQueryOnlyReceiptV2
):
    """Load any frozen query-only receipt, whatever shape it was written in.

    The label alone does not identify the contract, because attempts 4 and 5
    were written while ``v1`` was being changed in place. Dispatch on label and
    shape so every append-only artifact stays readable without editing it.
    """
    version = payload.get("schema_version")
    if version == "openai-query-only-receipt-v2":
        return OpenAIQueryOnlyReceiptV2.model_validate(payload)
    if version == "openai-query-only-receipt-v1":
        if "observed_write_phases" in payload:
            return OpenAIQueryOnlyReceiptV1Transitional.model_validate(payload)
        return OpenAIQueryOnlyReceiptV1.model_validate(payload)
    raise ValueError(f"unknown query-only receipt schema: {version!r}")


@dataclass(frozen=True)
class OpenAIQueryOnlyOutcome:
    pipeline: QueryOnlyPipelineResultV1
    receipt: OpenAIQueryOnlyReceiptV2


#: Windows a query-only attempt must observe for authoritative writes. Recorded
#: in the receipt so the zero write count states what it actually covered.
OBSERVED_WRITE_PHASES = ("recovery", "snapshot", "compilation", "execution")


class ExtractionCallObserver:
    """Counts L1/L2 producer construction and use during a query-only attempt.

    Query-only closure asserts an extraction call count of zero. That claim must
    be measured on the path that emits the receipt, not merely proven by tests
    patching the producers.
    """

    def __init__(self) -> None:
        self.l1_calls: list[str] = []
        self.l2_calls: list[str] = []
        self._restore: list[tuple[str, Any]] = []

    #: Guards against a second observer patching over an active one, which on a
    #: non-LIFO exit would leave a wrapper installed for the process.
    _active: "ExtractionCallObserver | None" = None

    def __enter__(self) -> "ExtractionCallObserver":
        if self._restore or type(self)._active is not None:
            raise RuntimeError("extraction observation windows must not nest")
        type(self)._active = self
        module = sys.modules[__name__]
        for name, sink in (
            ("OpenAICompatibleL1BatchProducer", self.l1_calls),
            ("OpenAICompatibleL2Producer", self.l2_calls),
        ):
            original = getattr(module, name)
            self._restore.append((name, original))
            setattr(module, name, self._wrap(name, original, sink))
        return self

    def __exit__(self, *_args: object) -> None:
        module = sys.modules[__name__]
        while self._restore:
            name, original = self._restore.pop()
            setattr(module, name, original)
        if type(self)._active is self:
            type(self)._active = None

    @property
    def active(self) -> bool:
        return bool(self._restore)

    @staticmethod
    def _wrap(name: str, original: Any, sink: list[str]) -> Any:
        def wrapper(*args: object, **kwargs: object) -> object:
            sink.append(name)
            return original(*args, **kwargs)

        return wrapper

    @property
    def l1_count(self) -> int:
        return len(self.l1_calls)

    @property
    def l2_count(self) -> int:
        return len(self.l2_calls)


class MemoryWriteObserver:
    """Counts authoritative write entry points reached during a query.

    The receipt must be able to represent a violated guarantee, so the write
    count is observed rather than asserted.
    """

    WRITE_METHODS = (
        "initialize",
        "make_checkpoint",
        "commit_checkpoint",
        "prepare_hard_purge",
        "_create_commit",
        "_update_ref",
        # `_command` is the generic git primitive every writer funnels through.
        # Observing it closes the bypass of calling it directly, and the verb
        # filter below keeps read-only plumbing uncounted.
        "_command",
    )

    #: git verbs known to only read. Anything else reaching the generic
    #: primitive is counted as a write, so an unlisted or newly introduced
    #: mutating verb fails closed instead of going unobserved.
    READ_ONLY_GIT_VERBS = frozenset(
        {
            # Plumbing reads only. `status` and `diff` are deliberately absent:
            # both can write (index refresh, `--output=`), so they count as
            # writes rather than widening the read-only set.
            "cat-file",
            "ls-tree",
            "rev-list",
            "rev-parse",
            "show",
            "merge-base",
            "for-each-ref",
            "diff-tree",
            "verify-pack",
        }
    )

    #: Guards against a second observer patching over an active one, which on a
    #: non-LIFO exit would leave a wrapper installed for the process.
    _active: "MemoryWriteObserver | None" = None

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.phases: list[str] = []
        self._phase: str | None = None
        self._restore: list[tuple[str, Any]] = []

    def observing(self, phase: str) -> "MemoryWriteObserver":
        """Label the next observation window so coverage is auditable."""
        self._phase = phase
        return self

    def __enter__(self) -> "MemoryWriteObserver":
        if self._restore or type(self)._active is not None:
            raise RuntimeError("write observation windows must not nest")
        type(self)._active = self
        if self._phase is not None:
            self.phases.append(self._phase)
            self._phase = None
        for name in self.WRITE_METHODS:
            # Read the raw descriptor rather than the bound attribute so a
            # classmethod is restored as a classmethod.
            descriptor = GitMemoryHistoryRepository.__dict__.get(name)
            if descriptor is None:
                continue
            self._restore.append((name, descriptor))
            setattr(
                GitMemoryHistoryRepository,
                name,
                self._wrap(name, descriptor),
            )
        return self

    def __exit__(self, *_args: object) -> None:
        while self._restore:
            name, descriptor = self._restore.pop()
            setattr(GitMemoryHistoryRepository, name, descriptor)
        if type(self)._active is self:
            type(self)._active = None

    def _wrap(self, name: str, descriptor: Any) -> Any:
        observer = self
        is_classmethod = isinstance(descriptor, classmethod)
        function = descriptor.__func__ if is_classmethod else descriptor

        def wrapper(*args: object, **kwargs: object) -> object:
            if name != "_command" or observer._mutates(args):
                observer.calls.append(name)
            return function(*args, **kwargs)

        return classmethod(wrapper) if is_classmethod else wrapper

    def _mutates(self, args: tuple[object, ...]) -> bool:
        # args[0] is the bound instance; the git verb is the first argv entry.
        verbs = [item for item in args[1:] if isinstance(item, str)]
        if not verbs:
            return True
        return verbs[0] not in self.READ_ONLY_GIT_VERBS

    @property
    def count(self) -> int:
        return len(self.calls)


def load_recovered_bundle(
    payload: dict[str, Any],
) -> MemoryRepresentationBundleV3:
    """Read a committed bundle in whichever shape was committed.

    The pipeline commits an identity-aware V4 bundle so a count can be answered,
    but earlier checkpoints hold plain V3. Dispatch on the recorded schema
    version rather than guessing, and fail closed on an unknown one: silently
    dropping identity would make a recovered count abstain for a reason that has
    nothing to do with the memory it recovered.
    """
    schema_version = payload.get("schema_version")
    if schema_version == "identity-aware-memory-bundle-v4":
        return IdentityAwareMemoryBundleV4.model_validate(payload)
    if schema_version == "memory-representation-bundle-v3":
        return MemoryRepresentationBundleV3.model_validate(payload)
    raise ValueError(
        "recovered bundle carries an unsupported schema version"
    )


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
    if manifest.sequence != 1:
        # Each manifest lists only the artifacts published by its own
        # checkpoint, so recovering from the head manifest alone would silently
        # drop turn bundles published earlier. Refuse instead of answering from
        # a partial artifact set.
        raise ValueError(
            "checkpoint recovery supports a single-checkpoint history; "
            f"head checkpoint sequence is {manifest.sequence}"
        )

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
    bundle = load_recovered_bundle(
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
    with ExtractionCallObserver() as extraction_observer:
        return _run_openai_query_only(
            question=question,
            query_time=query_time,
            repository_path=repository_path,
            expected_git_commit=expected_git_commit,
            expected_checkpoint_id=expected_checkpoint_id,
            result_path=result_path,
            query_id=query_id,
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
            max_attempts=max_attempts,
            opener=opener,
            extraction_observer=extraction_observer,
        )


def _run_openai_query_only(
    *,
    question: str,
    query_time: str,
    repository_path: Path,
    expected_git_commit: str,
    expected_checkpoint_id: str,
    result_path: Path,
    query_id: str,
    base_url: str,
    api_key: str,
    model: str,
    timeout_seconds: int,
    max_attempts: int,
    opener: Callable[..., Any],
    extraction_observer: ExtractionCallObserver,
) -> OpenAIQueryOnlyOutcome:
    if not extraction_observer.active:
        raise ValueError(
            "query-only execution requires an active extraction observer"
        )
    repository_path = Path(repository_path).resolve()
    result_path = Path(result_path).resolve()
    if result_path.exists():
        raise FileExistsError("query-only result artifact must be fresh")
    # Resolve the raw artifact too: if it is itself a symlink, a name-derived
    # comparison would miss a result path pointing at the same file.
    raw_path = repository_path.with_name(
        f"{repository_path.name}.raw.json"
    ).resolve()
    if repository_path in result_path.parents or result_path in (
        repository_path,
        raw_path,
    ):
        raise ValueError(
            "query-only result must not be written inside the memory repository"
        )
    if timeout_seconds <= 0:
        raise ValueError("model timeout must be positive")
    if max_attempts != 1:
        raise ValueError("query-only execution fixes a single model attempt")

    write_observer = MemoryWriteObserver()
    with write_observer.observing("recovery"):
        recovered = recover_authoritative_checkpoint(
            repository_path=repository_path,
            expected_git_commit=expected_git_commit,
            expected_checkpoint_id=expected_checkpoint_id,
        )
    registry = build_diagnostic_ontology_registry()
    # 绑定恢复出来的那份 snapshot：不绑定的话恢复出的实体会被报告为 unresolved，
    # 一个 count 只能弃权，而这与被恢复的记忆无关。
    recovered_snapshot = (
        recovered.bundle.identity_snapshots[0]
        if isinstance(recovered.bundle, IdentityAwareMemoryBundleV4)
        and recovered.bundle.identity_snapshots
        else None
    )
    compiler_registry = build_compiler_registry(
        registry, identity_snapshot=recovered_snapshot
    )
    recovered_snapshot_id = (
        recovered_snapshot.snapshot_id if recovered_snapshot is not None else None
    )
    with write_observer.observing("snapshot"):
        snapshot = build_query_execution_snapshot(
            repository_path=repository_path,
            bundle=recovered.bundle,
            bundle_history_artifact=recovered.bundle_history_artifact,
            turn_bundles=list(recovered.turn_bundles),
            registry=compiler_registry,
            identity_snapshot_id=recovered_snapshot_id,
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
    # The model request runs inside this window: it is the one stage where
    # untrusted output drives code, so it must not be the stage left unobserved.
    with write_observer.observing("compilation"):
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

    with write_observer.observing("execution"):
        execution = execute_authoritative_query(
            repository_path=repository_path,
            bundle=recovered.bundle,
            bundle_history_artifact=recovered.bundle_history_artifact,
            turn_bundles=list(recovered.turn_bundles),
            registry=compiler_registry,
            plan=compilation.plan,
            identity_snapshot_id=recovered_snapshot_id,
        )
        deterministic_replay = execute_authoritative_query(
            repository_path=repository_path,
            bundle=recovered.bundle,
            bundle_history_artifact=recovered.bundle_history_artifact,
            turn_bundles=list(recovered.turn_bundles),
            registry=compiler_registry,
            plan=compilation.plan,
            identity_snapshot_id=recovered_snapshot_id,
        )
    if execution != deterministic_replay:
        raise ValueError("deterministic query replay diverged from the execution")
    if execution.abstained or not execution.closure_complete:
        raise ValueError(
            "query-only execution abstained instead of closing: "
            f"{execution.evaluation.reason}"
        )
    if (
        canonical_sha256(snapshot) != execution.authority.snapshot_sha256
        or snapshot.registry_sha256 != execution.authority.registry_sha256
    ):
        raise ValueError(
            "verified snapshot does not match the executed query authority"
        )
    answer = build_evidence_backed_answer(
        execution=execution,
        bundle=recovered.bundle,
    )
    if not answer.answer_values or not answer.evidence_spans:
        raise ValueError("query-only closure requires an evidence-backed answer")
    post_commit = recovered.repository.head_commit()
    post_state = recovered.repository.read_state(commit=post_commit)
    if (
        post_commit != recovered.git_commit
        or post_state.checkpoint_id != recovered.checkpoint_id
    ):
        raise ValueError("query-only execution must not advance authoritative history")

    receipt = OpenAIQueryOnlyReceiptV2(
        workflow_run_id=workflow_run_id,
        requested_model=model,
        model_call=query_recording_opener.receipt(
            model,
            require_matching_response_model=True,
        ),
        query_call_count=query_recording_opener.attempts,
        l1_producer_call_count=extraction_observer.l1_count,
        l2_producer_call_count=extraction_observer.l2_count,
        automatic_memory_write_count=write_observer.count,
        observed_write_phases=tuple(write_observer.phases),
        deterministic_replay_verified=execution == deterministic_replay,
        # 收据自述它用的是哪个 profile：一份不说明 profile 的收据无法判断某个
        # 资格结论是否适用于它。
        extraction_profile=build_extraction_profile_identity(
            registry=registry,
            policy=build_diagnostic_production_policy(registry),
        ),
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
    if (
        receipt.query_call_count != 1
        or receipt.l1_producer_call_count != 0
        or receipt.l2_producer_call_count != 0
        or receipt.automatic_memory_write_count != 0
    ):
        raise ValueError(
            "query-only closure requires exactly one model call, no extraction "
            "calls, and no writes"
        )
    if receipt.observed_write_phases != OBSERVED_WRITE_PHASES:
        raise ValueError(
            "query-only closure must observe writes across "
            f"{OBSERVED_WRITE_PHASES}"
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
    receipt: OpenAIQueryOnlyReceiptV2,
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
