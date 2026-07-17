from __future__ import annotations

from collections.abc import Sequence
import hashlib
from pathlib import Path
import shutil
from typing import Annotated, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ke_memory_demo.core.json import JsonObject, canonical_json
from ke_memory_demo.domain import (
    AdapterIdentity,
    Evidence,
    Exchange,
    IngestReceipt,
    ReadinessReceipt,
    ResetReceipt,
    RunScope,
    UsageAndLatency,
)
from ke_memory_demo.infra.telemetry import UsageRecord
from ke_memory_demo.retrieval.evidence_payload import serialize_evidence_payload
from ke_memory_demo.retrieval.tokens import TokenCounter
from ke_memory_demo.storage import ArtifactStore


KE_MEMORY_SYSTEM_ID = "ke-memory"
KE_READY_STAGE = "ke-ready"
EMBEDDING_READY_STAGE = "embedding-ready"
MAX_EVIDENCE_TOKENS = 8192

NonEmptyString = Annotated[str, Field(min_length=1)]
NonNegativeInt = Annotated[int, Field(ge=0)]


class KEMemorySystemError(RuntimeError):
    """The KE adapter was used out of order or a staged port broke its contract."""


class _StageRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PreparedRunState(_StageRecord):
    metadata: JsonObject = Field(default_factory=dict)


class StoredExchange(_StageRecord):
    record_ids: tuple[NonEmptyString, ...]
    metadata: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_ids(self) -> StoredExchange:
        if len(self.record_ids) != len(set(self.record_ids)):
            raise ValueError("stored exchange record IDs must be duplicate-free")
        return self


class StageReadiness(_StageRecord):
    stage: NonEmptyString
    successful: bool
    pending_count: NonNegativeInt
    metadata: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_success(self) -> StageReadiness:
        if self.successful and self.pending_count:
            raise ValueError("successful stage readiness requires zero pending records")
        return self


class StagedKEOperations(Protocol):
    async def prepare(self, scope: RunScope, runtime_cache: Path) -> PreparedRunState: ...

    async def ingest(self, scope: RunScope, exchange: Exchange) -> StoredExchange: ...

    async def await_ready(
        self,
        scope: RunScope,
        required_stage: str,
    ) -> StageReadiness: ...


class RetrievalPort(Protocol):
    async def retrieve(
        self,
        scope: RunScope,
        question: str,
        evidence_budget_tokens: int,
    ) -> Sequence[Evidence]: ...


class UsageSource(Protocol):
    def usage_records(self, scope: RunScope) -> tuple[UsageRecord, ...]: ...


class KEMemorySystem:
    system_id = KE_MEMORY_SYSTEM_ID

    def __init__(
        self,
        artifacts: ArtifactStore,
        stages: StagedKEOperations,
        retrieval: RetrievalPort,
        usage_source: UsageSource,
        *,
        token_counter: TokenCounter,
    ) -> None:
        self._artifacts = artifacts
        self._stages = stages
        self._retrieval = retrieval
        self._usage_source = usage_source
        self._token_counter = token_counter
        self._scope: RunScope | None = None
        self._identity: AdapterIdentity | None = None
        self._runtime_id: str | None = None
        self._runtime_cache: Path | None = None
        self._ingested_exchange_ids: set[str] = set()
        self._ready = False

    async def prepare(self, scope: RunScope) -> AdapterIdentity:
        validated_scope = RunScope.model_validate(scope.model_dump(mode="python"))
        if validated_scope.system_id != self.system_id:
            raise KEMemorySystemError(
                f"run scope system_id must be {self.system_id}, got {validated_scope.system_id}"
            )
        if self._scope is not None:
            if self._scope == validated_scope and self._identity is not None:
                return self._identity
            raise KEMemorySystemError("KE memory system is already prepared for another scope")

        runtime_id = _runtime_id(validated_scope)
        runtime_cache = self._artifacts.cache_path(runtime_id).parent
        self._artifacts.layout.ensure_directory(runtime_cache)
        try:
            raw_prepared = await self._stages.prepare(validated_scope, runtime_cache)
            prepared = PreparedRunState.model_validate(raw_prepared.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError, ValidationError) as error:
            _remove_runtime_cache(self._artifacts, runtime_cache)
            raise KEMemorySystemError("staged prepare returned an invalid result") from error
        except BaseException:
            _remove_runtime_cache(self._artifacts, runtime_cache)
            raise

        namespace = _namespace(validated_scope)
        identity = AdapterIdentity(
            system_id=self.system_id,
            namespace=namespace,
            implementation="ke_memory_demo.systems.KEMemorySystem",
            version="1",
            metadata={
                "runtime_cache_id": runtime_id,
                "stage": prepared.metadata,
            },
        )
        self._scope = validated_scope
        self._identity = identity
        self._runtime_id = runtime_id
        self._runtime_cache = runtime_cache
        self._ingested_exchange_ids.clear()
        self._ready = False
        return identity

    async def ingest(self, exchange: Exchange) -> IngestReceipt:
        scope, namespace = self._prepared_identity()
        validated_exchange = Exchange.model_validate(exchange.model_dump(mode="python"))
        if validated_exchange.id in self._ingested_exchange_ids:
            raise KEMemorySystemError(
                f"exchange was already ingested in this run: {validated_exchange.id}"
            )
        try:
            raw_stored = await self._stages.ingest(scope, validated_exchange)
            stored = StoredExchange.model_validate(raw_stored.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError, ValidationError) as error:
            raise KEMemorySystemError("staged ingest returned an invalid result") from error
        self._ingested_exchange_ids.add(validated_exchange.id)
        self._ready = False
        return IngestReceipt(
            system_id=self.system_id,
            namespace=namespace,
            source_exchange_id=validated_exchange.id,
            system_record_ids=stored.record_ids,
            source_content_hash=hashlib.sha256(canonical_json(validated_exchange)).hexdigest(),
            metadata=stored.metadata,
        )

    async def await_ready(self) -> ReadinessReceipt:
        scope, namespace = self._prepared_identity()
        try:
            raw_status = await self._stages.await_ready(scope, KE_READY_STAGE)
            status = StageReadiness.model_validate(raw_status.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError, ValidationError) as error:
            raise KEMemorySystemError("staged readiness returned an invalid result") from error
        if status.stage != KE_READY_STAGE:
            raise KEMemorySystemError(f"readiness must report the {KE_READY_STAGE} stage")
        self._ready = status.successful
        metadata = dict(status.metadata)
        metadata["required_stage"] = KE_READY_STAGE
        return ReadinessReceipt(
            system_id=self.system_id,
            namespace=namespace,
            ready=status.successful,
            pending_count=status.pending_count,
            metadata=metadata,
        )

    async def retrieve(
        self,
        question: str,
        evidence_budget_tokens: int,
    ) -> Sequence[Evidence]:
        scope, _namespace = self._prepared_identity()
        if not self._ready:
            raise KEMemorySystemError(
                f"KE memory system is not ready; await successful {KE_READY_STAGE}"
            )
        if not question.strip():
            raise KEMemorySystemError("question must not be empty")
        if (
            isinstance(evidence_budget_tokens, bool)
            or evidence_budget_tokens <= 0
            or evidence_budget_tokens > MAX_EVIDENCE_TOKENS
        ):
            raise KEMemorySystemError(
                f"evidence budget must be between 1 and {MAX_EVIDENCE_TOKENS} tokens"
            )
        raw_evidence = await self._retrieval.retrieve(
            scope,
            question,
            evidence_budget_tokens,
        )
        try:
            evidence = tuple(
                Evidence.model_validate(item.model_dump(mode="python")) for item in raw_evidence
            )
        except (AttributeError, TypeError, ValueError, ValidationError) as error:
            raise KEMemorySystemError("retrieval returned invalid evidence") from error
        serialized_tokens = self._token_counter.count(serialize_evidence_payload(evidence))
        if isinstance(serialized_tokens, bool) or serialized_tokens < 0:
            raise KEMemorySystemError("token counter returned an invalid count")
        if serialized_tokens > evidence_budget_tokens:
            raise KEMemorySystemError("retrieval exceeded the requested evidence budget")
        evidence_ids = tuple(item.evidence_id for item in evidence)
        if len(evidence_ids) != len(set(evidence_ids)):
            raise KEMemorySystemError("retrieval returned duplicate evidence IDs")
        return evidence

    async def stats(self) -> UsageAndLatency:
        scope, namespace = self._prepared_identity()
        usage = self._usage_source.usage_records(scope)
        costs = tuple(item.provider_cost for item in usage if item.provider_cost is not None)
        return UsageAndLatency(
            system_id=self.system_id,
            namespace=namespace,
            call_count=len(usage),
            input_tokens=sum(item.input_tokens for item in usage),
            output_tokens=sum(item.output_tokens for item in usage),
            total_latency_seconds=sum(item.latency_seconds for item in usage),
            provider_cost=sum(costs) if costs else None,
            currency="USD" if costs else None,
            metadata={
                "ingested_exchange_count": len(self._ingested_exchange_ids),
                "ke_ready": self._ready,
            },
        )

    async def reset(self) -> ResetReceipt:
        _scope, namespace = self._prepared_identity()
        if self._runtime_cache is None or self._runtime_id is None:
            raise KEMemorySystemError("prepared runtime cache identity is missing")
        expected = self._artifacts.cache_path(self._runtime_id).parent
        if self._runtime_cache != expected:
            raise KEMemorySystemError("runtime cache path no longer matches its prepared identity")
        deleted = _remove_runtime_cache(self._artifacts, self._runtime_cache)
        runtime_id = self._runtime_id
        self._scope = None
        self._identity = None
        self._runtime_id = None
        self._runtime_cache = None
        self._ingested_exchange_ids.clear()
        self._ready = False
        return ResetReceipt(
            system_id=self.system_id,
            namespace=namespace,
            reset=True,
            deleted_record_count=deleted,
            metadata={"runtime_cache_id": runtime_id},
        )

    def _prepared_identity(self) -> tuple[RunScope, str]:
        if self._scope is None or self._identity is None:
            raise KEMemorySystemError("KE memory system must be prepared first")
        return self._scope, self._identity.namespace


def _namespace(scope: RunScope) -> str:
    return f"{scope.run_id}:{scope.conversation_id}:{scope.system_id}"


def _runtime_id(scope: RunScope) -> str:
    digest = hashlib.sha256(canonical_json(scope)).hexdigest()
    return f"ke-runtime-{digest}"


def _remove_runtime_cache(artifacts: ArtifactStore, runtime_cache: Path) -> int:
    cache_root = artifacts.layout.cache_root
    artifacts.layout.assert_safe(runtime_cache)
    try:
        relative = runtime_cache.relative_to(cache_root)
    except ValueError as error:
        raise KEMemorySystemError("runtime cache path escapes the cache root") from error
    if not relative.parts:
        raise KEMemorySystemError("refusing to remove the shared cache root")
    if not runtime_cache.exists():
        return 0
    entries = tuple(runtime_cache.rglob("*"))
    for entry in entries:
        artifacts.layout.assert_safe(entry)
    deleted = sum(1 for entry in entries if not entry.is_dir())
    try:
        shutil.rmtree(runtime_cache)
    except OSError as error:
        raise KEMemorySystemError("unable to remove the owned runtime cache") from error
    return deleted
