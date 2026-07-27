from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import tomllib

import pytest

from ke_memory_demo.online.api import create_app as legacy_create_app
from ke_memory_demo.online.factory import build_online_runtime as legacy_build_runtime
from ke_memory_service.api import create_app
from ke_memory_service.identity import (
    InMemoryPrincipalRegistry,
    PrincipalConflict,
    PrincipalKind,
    PrincipalRegistration,
)
from ke_memory_service.runtime import build_online_runtime


ROOT = Path(__file__).resolve().parents[2]


def test_service_package_owns_runtime_and_api() -> None:
    assert create_app is legacy_create_app
    assert build_online_runtime is legacy_build_runtime


def test_service_entry_point_uses_new_package() -> None:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        config = tomllib.load(stream)
    assert config["project"]["scripts"]["ke-memory-serve"] == "ke_memory_service.api:main"


def test_principal_registration_is_stable_and_idempotent() -> None:
    registry = InMemoryPrincipalRegistry()
    request = PrincipalRegistration(
        tenant_id="tenant-a",
        external_id="user-1",
        kind=PrincipalKind.USER,
        display_name="User One",
    )
    first = registry.register(request, recorded_at=datetime(2026, 7, 27, tzinfo=UTC))
    replay = registry.register(request, recorded_at=datetime(2026, 7, 28, tzinfo=UTC))

    assert replay == first
    assert registry.get(first.principal_id) == first

    with pytest.raises(PrincipalConflict):
        registry.register(
            request.model_copy(update={"display_name": "Different Name"}),
            recorded_at=datetime(2026, 7, 28, tzinfo=UTC),
        )

