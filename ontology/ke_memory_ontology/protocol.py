from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from ke_memory_demo.domain import OntologyBinding

from .models import IndexIdentity, OntologyHealth, OntologyRelation, OntologyTerm


@runtime_checkable
class OntologyVocabulary(Protocol):
    async def health(self) -> OntologyHealth: ...

    async def index_identity(self) -> IndexIdentity: ...

    async def resolve_terms(self, surface_terms: Sequence[str]) -> list[OntologyBinding]: ...

    async def fetch_terms(self, document_ids: Sequence[str]) -> list[OntologyTerm]: ...

    async def fetch_relations(self, document_ids: Sequence[str]) -> list[OntologyRelation]: ...
