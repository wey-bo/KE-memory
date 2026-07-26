from __future__ import annotations

from pathlib import Path

import pytest

from ke_memory_demo.online.factory import build_online_runtime


@pytest.mark.asyncio
async def test_offline_factory_needs_only_online_config_and_resolves_database_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "online.toml").write_text(
        """
[online]
mode = "production"
database_path = "state/test-memory.sqlite3"
host = "127.0.0.1"
port = 8899
keol_commit = "44631e64fd07c9b85f22e36035bf49c882dba592"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("KE_MEMORY_ONLINE_MODE", "offline")

    runtime = build_online_runtime(tmp_path)

    assert runtime.mode == "offline"
    assert runtime.extraction_ready is False
    assert runtime.host == "127.0.0.1"
    assert runtime.port == 8899
    assert runtime.keol_commit == "44631e64fd07c9b85f22e36035bf49c882dba592"
    assert runtime.repository.database_path == (
        tmp_path / "state" / "test-memory.sqlite3"
    ).resolve()
    assert runtime.repository.integrity_check() == ("ok",)

    await runtime.aclose()
