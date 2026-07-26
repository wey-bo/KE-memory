from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from ke_memory_demo.domain import Exchange, KnowledgeEquation, Lifecycle

from .admission import AdmissionPolicy
from .extractor import NoOpLifecycle, OnlineLifecycle, OnlineTurnExtractor
from .keol_bridge import KEOLBundleCompiler
from .models import AdmissionStatus, MemoryNamespace
from .repository import (
    AssessedEquation,
    ExistingMemoryRevision,
    MemoryLinkWrite,
    MemoryWrite,
    SQLiteOnlineMemoryRepository,
)


NonEmptyString = Annotated[str, Field(min_length=1)]


class OnlineIngestResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    transaction_id: NonEmptyString
    replayed: bool
    admitted_memory_ids: tuple[NonEmptyString, ...] = ()
    candidate_equation_ids: tuple[NonEmptyString, ...] = ()
    rejected_equation_ids: tuple[NonEmptyString, ...] = ()


class OntologyMemoryService:
    def __init__(
        self,
        *,
        repository: SQLiteOnlineMemoryRepository,
        extractor: OnlineTurnExtractor,
        lifecycle: OnlineLifecycle | None = None,
        admission_policy: AdmissionPolicy | None = None,
        compiler: KEOLBundleCompiler | None = None,
    ) -> None:
        self._repository = repository
        self._extractor = extractor
        self._lifecycle = lifecycle or NoOpLifecycle()
        self._admission = admission_policy or AdmissionPolicy()
        self._compiler = compiler or KEOLBundleCompiler()

    async def ingest_turn(
        self,
        *,
        namespace: MemoryNamespace,
        conversation_id: str,
        idempotency_key: str,
        exchange: Exchange,
        recorded_at: datetime,
    ) -> OnlineIngestResult:
        replay = self._repository.get_turn_receipt(namespace, idempotency_key)
        if replay is not None and self._raw_matches(namespace, exchange):
            extractions = self._repository.get_extractions(namespace, exchange.id)
            return _ingest_result(replay, extractions)

        extraction = await self._extractor.extract(exchange)
        if extraction.exchange_id != exchange.id:
            raise ValueError("extractor result references a different exchange")

        assessed = tuple(
            AssessedEquation(equation=equation, assessment=self._admission.assess(equation))
            for equation in extraction.knowledge_equations
        )
        admitted = tuple(
            item.equation
            for item in assessed
            if item.assessment.status is AdmissionStatus.ADMITTED
        )
        existing = self._repository.list_current(namespace)
        lifecycle_result = await self._lifecycle.apply(
            tuple(item.equation for item in existing),
            admitted,
        )
        appended = {equation.id: equation for equation in lifecycle_result.appended_revisions}
        if len(appended) != len(lifecycle_result.appended_revisions):
            raise ValueError("lifecycle returned duplicate logical equation IDs")

        source_messages = {
            record.id: record.content
            for record in (exchange.user, *exchange.events, exchange.assistant)
        }
        assessment_by_id = {
            item.equation.id: item.assessment
            for item in assessed
            if item.assessment.status is AdmissionStatus.ADMITTED
        }
        adjusted_new = tuple(appended.get(equation.id, equation) for equation in admitted)
        memories = tuple(
            MemoryWrite(
                equation=equation,
                assessment=assessment_by_id[equation.id],
                bundle=self._compiler.compile(
                    namespace=namespace,
                    equation=equation,
                    assessment=assessment_by_id[equation.id],
                    source_messages=source_messages,
                    recorded_at=recorded_at,
                ),
            )
            for equation in adjusted_new
        )

        existing_by_equation_id = {item.equation.id: item for item in existing}
        transitions = tuple(
            ExistingMemoryRevision(
                memory_id=existing_by_equation_id[equation.id].memory_id,
                equation=equation,
            )
            for equation in lifecycle_result.appended_revisions
            if equation.id in existing_by_equation_id
            and equation.revision != existing_by_equation_id[equation.id].equation.revision
        )
        links = self._lifecycle_links(
            namespace=namespace,
            adjusted_new=adjusted_new,
            transitions=transitions,
            existing_by_equation_id=existing_by_equation_id,
        )
        receipt = self._repository.write_turn(
            namespace=namespace,
            conversation_id=conversation_id,
            idempotency_key=idempotency_key,
            exchange=exchange,
            memories=memories,
            extractions=assessed,
            transitions=transitions,
            links=links,
            recorded_at=recorded_at,
        )
        return _ingest_result(receipt, assessed)

    def _raw_matches(self, namespace: MemoryNamespace, exchange: Exchange) -> bool:
        stored = self._repository.get_raw_turn(namespace, exchange.id)
        incoming = (exchange.user, *exchange.events, exchange.assistant)
        if len(stored) != len(incoming):
            return False
        return all(
            item.get("record_id") == record.id
            and item.get("content_hash") == record.content_hash
            and item.get("source_order") == record.source_order
            for item, record in zip(stored, incoming, strict=True)
        )

    def _lifecycle_links(
        self,
        *,
        namespace: MemoryNamespace,
        adjusted_new: tuple[KnowledgeEquation, ...],
        transitions: tuple[ExistingMemoryRevision, ...],
        existing_by_equation_id: dict[str, object],
    ) -> tuple[MemoryLinkWrite, ...]:
        existing_ids = set(existing_by_equation_id)
        new_ids = {equation.id for equation in adjusted_new}
        links: dict[tuple[str, str, str], MemoryLinkWrite] = {}

        def add(source_equation_id: str, target_equation_id: str, relation: str) -> None:
            if target_equation_id not in existing_ids and target_equation_id not in new_ids:
                raise ValueError(
                    f"lifecycle link references unknown equation: {target_equation_id}"
                )
            source_id = self._repository.memory_id_for(namespace, source_equation_id)
            target_id = self._repository.memory_id_for(namespace, target_equation_id)
            link = MemoryLinkWrite(
                source_memory_id=source_id,
                target_memory_id=target_id,
                relation=relation,
            )
            links[(source_id, target_id, relation)] = link

        for equation in adjusted_new:
            for target in equation.supersedes:
                add(equation.id, target, "supersedes")
            for target in equation.contradicts:
                add(equation.id, target, "conflicts_with")
        for transition in transitions:
            for target in transition.equation.contradicts:
                add(transition.equation.id, target, "conflicts_with")
        return tuple(links[key] for key in sorted(links))


def _ingest_result(receipt: object, extractions: tuple[AssessedEquation, ...]) -> OnlineIngestResult:
    from .repository import TurnWriteReceipt

    if not isinstance(receipt, TurnWriteReceipt):
        raise TypeError("repository returned an invalid turn receipt")
    return OnlineIngestResult(
        transaction_id=receipt.transaction_id,
        replayed=receipt.replayed,
        admitted_memory_ids=receipt.memory_ids,
        candidate_equation_ids=tuple(
            item.equation.id
            for item in extractions
            if item.assessment.status is AdmissionStatus.CANDIDATE
        ),
        rejected_equation_ids=tuple(
            item.equation.id
            for item in extractions
            if item.assessment.status is AdmissionStatus.REJECTED
        ),
    )
