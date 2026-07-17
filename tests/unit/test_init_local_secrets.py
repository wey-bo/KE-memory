from collections.abc import Callable, Mapping
import builtins
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
    writes: list[tuple[Path, Mapping[str, str]]] = []

    def fake_getpass(prompt: str) -> str:
        prompts.append(prompt)
        return "import-test-value"

    def fake_runtime_write(path: Path, values: Mapping[str, str]) -> None:
        writes.append((path, values))

    def fake_legacy_write(path: Path, work_key: str, judge_key: str) -> None:
        del path, work_key, judge_key

    monkeypatch.setattr(getpass_module, "getpass", fake_getpass)
    monkeypatch.setattr(secrets, "write_runtime_env_local", fake_runtime_write, raising=False)
    monkeypatch.setattr(secrets, "write_env_local", fake_legacy_write)

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

    def discard_runtime_write(path: Path, values: Mapping[str, str]) -> None:
        del path, values

    def discard_legacy_write(path: Path, work_key: str, judge_key: str) -> None:
        del path, work_key, judge_key

    monkeypatch.setattr(getpass_module, "getpass", import_getpass)
    monkeypatch.setattr(
        secrets,
        "write_runtime_env_local",
        discard_runtime_write,
        raising=False,
    )
    monkeypatch.setattr(secrets, "write_env_local", discard_legacy_write)
    module = _load_initializer(project_root / "scripts/init_local_secrets.py")
    secret_responses = iter(("work-test-value", "judge-test-value", "es-api-test-value"))
    visible_responses = iter(("https://es.example.test", "domain-terms"))
    secret_prompts: list[str] = []
    visible_prompts: list[str] = []
    writes: list[tuple[Path, Mapping[str, str]]] = []
    legacy_writes: list[tuple[Path, str, str]] = []

    def fake_getpass(prompt: str) -> str:
        secret_prompts.append(prompt)
        return next(secret_responses)

    def fake_input(prompt: str) -> str:
        visible_prompts.append(prompt)
        return next(visible_responses)

    def fake_runtime_write(path: Path, values: Mapping[str, str]) -> None:
        writes.append((path, dict(values)))

    def fake_legacy_write(path: Path, work_key: str, judge_key: str) -> None:
        legacy_writes.append((path, work_key, judge_key))

    monkeypatch.setattr(module, "getpass", fake_getpass)
    monkeypatch.setattr(builtins, "input", fake_input)
    monkeypatch.setattr(module, "write_runtime_env_local", fake_runtime_write, raising=False)
    monkeypatch.setattr(module, "write_env_local", fake_legacy_write, raising=False)

    main = cast(Callable[[], None], getattr(module, "main"))
    main()

    assert secret_prompts == [
        "Work-model API key: ",
        "Judge API key: ",
        "Elasticsearch API key: ",
    ]
    assert visible_prompts == ["Elasticsearch URL: ", "Elasticsearch index: "]
    assert writes == [
        (
            project_root / ".env.local",
            {
                "KE_MEMORY_WORK_API_KEY": "work-test-value",
                "KE_MEMORY_JUDGE_API_KEY": "judge-test-value",
                "KE_MEMORY_ES_URL": "https://es.example.test",
                "KE_MEMORY_ES_INDEX": "domain-terms",
                "KE_MEMORY_ES_API_KEY": "es-api-test-value",
            },
        )
    ]
    assert legacy_writes == []
