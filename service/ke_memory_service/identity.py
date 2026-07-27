from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ke_memory_demo.core.ids import content_id


NonEmptyString = Annotated[str, Field(min_length=1)]


class PrincipalKind(str, Enum):
    USER = "user"
    AGENT = "agent"
    SERVICE = "service"


class PrincipalStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


class _IdentityRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PrincipalRegistration(_IdentityRecord):
    tenant_id: NonEmptyString
    external_id: NonEmptyString
    kind: PrincipalKind
    display_name: NonEmptyString

    @field_validator("tenant_id", "external_id", "display_name", mode="before")
    @classmethod
    def _strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class RegisteredPrincipal(_IdentityRecord):
    principal_id: NonEmptyString
    tenant_id: NonEmptyString
    external_id: NonEmptyString
    kind: PrincipalKind
    display_name: NonEmptyString
    status: PrincipalStatus
    created_at: datetime


class PrincipalConflict(RuntimeError):
    """The same external identity was registered with different immutable attributes."""


@runtime_checkable
class PrincipalRegistry(Protocol):
    def register(
        self,
        registration: PrincipalRegistration,
        *,
        recorded_at: datetime,
    ) -> RegisteredPrincipal: ...

    def get(self, principal_id: str) -> RegisteredPrincipal | None: ...


class InMemoryPrincipalRegistry:
    """Deterministic reference registry; persistent adapters implement the same protocol."""

    def __init__(self) -> None:
        self._by_id: dict[str, RegisteredPrincipal] = {}
        self._by_external: dict[tuple[str, PrincipalKind, str], str] = {}

    def register(
        self,
        registration: PrincipalRegistration,
        *,
        recorded_at: datetime,
    ) -> RegisteredPrincipal:
        if recorded_at.tzinfo is None or recorded_at.utcoffset() is None:
            raise ValueError("recorded_at must be timezone-aware")
        external_key = (
            registration.tenant_id,
            registration.kind,
            registration.external_id,
        )
        existing_id = self._by_external.get(external_key)
        if existing_id is not None:
            existing = self._by_id[existing_id]
            if existing.display_name != registration.display_name:
                raise PrincipalConflict("principal identity is already registered")
            return existing

        principal_id = content_id(
            "principal",
            {
                "tenant_id": registration.tenant_id,
                "kind": registration.kind.value,
                "external_id": registration.external_id,
            },
        )
        principal = RegisteredPrincipal(
            principal_id=principal_id,
            tenant_id=registration.tenant_id,
            external_id=registration.external_id,
            kind=registration.kind,
            display_name=registration.display_name,
            status=PrincipalStatus.ACTIVE,
            created_at=recorded_at,
        )
        self._by_id[principal_id] = principal
        self._by_external[external_key] = principal_id
        return principal

    def get(self, principal_id: str) -> RegisteredPrincipal | None:
        return self._by_id.get(principal_id)
