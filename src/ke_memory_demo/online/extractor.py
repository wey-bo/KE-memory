from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from ke_memory_demo.domain import Exchange, KnowledgeEquation
from ke_memory_demo.extraction import (
    LifecycleMaintainer,
    LifecycleResult,
    TurnExtractionResult,
    TurnKEExtractor,
)


@runtime_checkable
class OnlineTurnExtractor(Protocol):
    async def extract(self, exchange: Exchange) -> TurnExtractionResult: ...


@runtime_checkable
class OnlineLifecycle(Protocol):
    async def apply(
        self,
        existing: Sequence[KnowledgeEquation],
        new: Sequence[KnowledgeEquation],
    ) -> LifecycleResult: ...


class TurnKEExtractorAdapter:
    def __init__(self, extractor: TurnKEExtractor) -> None:
        self._extractor = extractor

    async def extract(self, exchange: Exchange) -> TurnExtractionResult:
        return await self._extractor.extract(exchange)


class LifecycleMaintainerAdapter:
    def __init__(self, maintainer: LifecycleMaintainer) -> None:
        self._maintainer = maintainer

    async def apply(
        self,
        existing: Sequence[KnowledgeEquation],
        new: Sequence[KnowledgeEquation],
    ) -> LifecycleResult:
        return await self._maintainer.apply(existing, new)


class NoOpLifecycle:
    async def apply(
        self,
        existing: Sequence[KnowledgeEquation],
        new: Sequence[KnowledgeEquation],
    ) -> LifecycleResult:
        current = {equation.id: equation for equation in existing}
        current.update({equation.id: equation for equation in new})
        return LifecycleResult(
            appended_revisions=tuple(new),
            current_records=tuple(current[key] for key in sorted(current)),
        )
