from collections.abc import Callable
import getpass as getpass_module
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest

from ke_memory_demo.infra import secrets


def _load_initializer(path: Path) -> ModuleType:
    spec = spec_from_file_location("test_init_local_secrets", path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load initializer at {path}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_importing_initializer_has_no_side_effects(
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    prompts: list[str] = []
    writes: list[tuple[Path, str, str]] = []

    def fake_getpass(prompt: str) -> str:
        prompts.append(prompt)
        return "import-test-value"

    def fake_write(path: Path, work_key: str, judge_key: str) -> None:
        writes.append((path, work_key, judge_key))

    monkeypatch.setattr(getpass_module, "getpass", fake_getpass)
    monkeypatch.setattr(secrets, "write_env_local", fake_write)

    module = _load_initializer(project_root / "scripts/init_local_secrets.py")

    assert prompts == []
    assert writes == []
    assert callable(getattr(module, "main", None))


def test_initializer_main_writes_to_repository_root(
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    def import_getpass(prompt: str) -> str:
        return "unused-import-value"

    def discard_write(path: Path, work_key: str, judge_key: str) -> None:
        return None

    monkeypatch.setattr(getpass_module, "getpass", import_getpass)
    monkeypatch.setattr(secrets, "write_env_local", discard_write)
    module = _load_initializer(project_root / "scripts/init_local_secrets.py")
    responses = iter(("work-test-value", "judge-test-value"))
    writes: list[tuple[Path, str, str]] = []

    def fake_getpass(prompt: str) -> str:
        return next(responses)

    def fake_write(path: Path, work_key: str, judge_key: str) -> None:
        writes.append((path, work_key, judge_key))

    monkeypatch.setattr(module, "getpass", fake_getpass)
    monkeypatch.setattr(module, "write_env_local", fake_write)

    main = cast(Callable[[], None], getattr(module, "main"))
    main()

    assert writes == [(project_root / ".env.local", "work-test-value", "judge-test-value")]
