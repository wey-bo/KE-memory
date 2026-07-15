from pathlib import Path
import shutil

import pytest
from pydantic import ValidationError

from ke_memory_demo.settings import SettingsError, load_settings


LIVE_ENV_VARS = (
    "KE_MEMORY_WORK_API_KEY",
    "KE_MEMORY_JUDGE_API_KEY",
    "KE_MEMORY_ES_URL",
    "KE_MEMORY_ES_INDEX",
    "KE_MEMORY_ES_API_KEY",
    "KE_MEMORY_EMBEDDING_PATH",
)


@pytest.fixture(autouse=True)
def unset_live_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in LIVE_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_settings_keep_secret_values_out_of_toml(project_root: Path):
    settings = load_settings(project_root)
    assert settings.work.model == "gpt-5.4"
    assert settings.work.api_key_env == "KE_MEMORY_WORK_API_KEY"
    assert settings.embedding.dimension == 1024
    assert "sk-" not in (project_root / "config/models.toml").read_text()


def test_settings_load_all_exact_experiment_and_es_values(project_root: Path):
    settings = load_settings(project_root)

    assert settings.dataset.archive_path == Path("/public/home/wwb/datasets/BEAM.zip")
    assert settings.dataset.selected_directories == (4, 15, 17)
    assert settings.dataset.expected_sessions == 13
    assert settings.dataset.expected_exchanges == 385
    assert settings.dataset.expected_questions == 60
    assert settings.retrieval.evidence_budget_tokens == 8192
    assert settings.retrieval.answer_max_output_tokens == 1024
    assert settings.aggregation.max_semantic_depth == 2
    assert settings.es.fields.canonical == "term"
    assert settings.es.roles.operator == ("operator", "relation", "predicate", "action")


def test_load_settings_does_not_require_live_environment(project_root: Path):
    load_settings(project_root)


def test_settings_are_immutable(project_root: Path):
    settings = load_settings(project_root)

    with pytest.raises(ValidationError):
        settings.work.model = "different-model"


@pytest.mark.parametrize(
    ("method_name", "environment_name"),
    [
        ("require_work_api_key", "KE_MEMORY_WORK_API_KEY"),
        ("require_judge_api_key", "KE_MEMORY_JUDGE_API_KEY"),
        ("require_embedding_path", "KE_MEMORY_EMBEDDING_PATH"),
        ("require_es_connection", "KE_MEMORY_ES_URL"),
    ],
)
def test_live_requirements_raise_clear_errors_for_missing_values(
    project_root: Path,
    method_name: str,
    environment_name: str,
):
    settings = load_settings(project_root)

    with pytest.raises(SettingsError, match=environment_name):
        getattr(settings, method_name)()


def test_live_requirements_read_environment_at_call_time(
    project_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    settings = load_settings(project_root)
    model_path = tmp_path / "embedding-model"
    model_path.mkdir()
    monkeypatch.setenv("KE_MEMORY_WORK_API_KEY", "work-test-value")
    monkeypatch.setenv("KE_MEMORY_JUDGE_API_KEY", "judge-test-value")
    monkeypatch.setenv("KE_MEMORY_EMBEDDING_PATH", str(model_path))
    monkeypatch.setenv("KE_MEMORY_ES_URL", "https://es.test.invalid")
    monkeypatch.setenv("KE_MEMORY_ES_INDEX", "test-index")
    monkeypatch.setenv("KE_MEMORY_ES_API_KEY", "es-test-value")

    assert settings.require_work_api_key() == "work-test-value"
    assert settings.require_judge_api_key() == "judge-test-value"
    assert settings.require_embedding_path() == model_path
    assert settings.require_es_connection() == (
        "https://es.test.invalid",
        "test-index",
        "es-test-value",
    )


@pytest.mark.parametrize(
    "missing_name",
    ["KE_MEMORY_ES_URL", "KE_MEMORY_ES_INDEX", "KE_MEMORY_ES_API_KEY"],
)
def test_es_connection_names_each_missing_environment_value(
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    missing_name: str,
):
    values = {
        "KE_MEMORY_ES_URL": "https://es.test.invalid",
        "KE_MEMORY_ES_INDEX": "test-index",
        "KE_MEMORY_ES_API_KEY": "es-test-value",
    }
    for name, value in values.items():
        if name != missing_name:
            monkeypatch.setenv(name, value)
    settings = load_settings(project_root)

    with pytest.raises(SettingsError, match=missing_name):
        settings.require_es_connection()


def test_embedding_path_is_resolved_from_project_root(
    project_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    config_root = tmp_path / "project"
    shutil.copytree(project_root / "config", config_root / "config")
    model_path = config_root / "models" / "embedding"
    model_path.mkdir(parents=True)
    monkeypatch.setenv("KE_MEMORY_EMBEDDING_PATH", "models/embedding")

    settings = load_settings(config_root)

    assert settings.require_embedding_path() == model_path


@pytest.mark.parametrize("kind", ["missing", "file"])
def test_embedding_path_must_be_an_existing_directory(
    project_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
):
    candidate = tmp_path / "embedding-model"
    if kind == "file":
        candidate.write_text("not a model directory")
    monkeypatch.setenv("KE_MEMORY_EMBEDDING_PATH", str(candidate))
    settings = load_settings(project_root)

    with pytest.raises(SettingsError, match="existing directory"):
        settings.require_embedding_path()


def test_dotenv_values_are_loaded_without_overriding_process_environment(
    project_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    config_root = tmp_path / "project"
    shutil.copytree(project_root / "config", config_root / "config")
    (config_root / ".env.local").write_text(
        "KE_MEMORY_WORK_API_KEY=dotenv-test-value\n"
        "KE_MEMORY_JUDGE_API_KEY=dotenv-judge-test-value\n"
    )
    monkeypatch.setenv("KE_MEMORY_WORK_API_KEY", "process-test-value")

    settings = load_settings(config_root)

    assert settings.require_work_api_key() == "process-test-value"
    assert settings.require_judge_api_key() == "dotenv-judge-test-value"
