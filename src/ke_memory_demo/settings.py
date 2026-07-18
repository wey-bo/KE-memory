from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tomllib
from typing import Annotated, cast

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError


PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeFloat = Annotated[float, Field(ge=0)]
NonEmptyString = Annotated[str, Field(min_length=1)]
_CONFIG_FILENAMES = ("models.toml", "experiment.toml", "es_vocab.toml")


class SettingsError(RuntimeError):
    """Raised when configuration cannot support a requested operation."""


@dataclass(frozen=True)
class ConfigLayout:
    project_root: Path
    config_dir: Path


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ModelSettings(_FrozenModel):
    model: NonEmptyString
    base_url: NonEmptyString
    api_key_env: NonEmptyString
    temperature: NonNegativeFloat
    max_output_tokens: PositiveInt


class EmbeddingSettings(_FrozenModel):
    enabled: bool
    model: NonEmptyString
    revision: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    local_path_env: NonEmptyString
    dimension: PositiveInt
    chunk_tokens: PositiveInt
    overlap_tokens: Annotated[int, Field(ge=0)]
    local_files_only: bool


class DatasetSettings(_FrozenModel):
    archive_path: Path
    archive_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    selected_directories: tuple[int, int, int]
    expected_sessions: PositiveInt
    expected_exchanges: PositiveInt
    expected_questions: PositiveInt


class RetrievalSettings(_FrozenModel):
    evidence_budget_tokens: PositiveInt
    answer_max_output_tokens: PositiveInt


class AggregationSettings(_FrozenModel):
    max_semantic_depth: PositiveInt


class EvaluationConcurrencySettings(_FrozenModel):
    turn_workers: PositiveInt
    session_workers: PositiveInt
    question_workers: PositiveInt
    judge_workers: PositiveInt


class EvaluationSettings(_FrozenModel):
    concurrency: EvaluationConcurrencySettings


class ElasticsearchFields(_FrozenModel):
    canonical: NonEmptyString
    type: NonEmptyString
    aliases: NonEmptyString
    relations: NonEmptyString
    relation_type: NonEmptyString
    relation_target_id: NonEmptyString


class ElasticsearchRoles(_FrozenModel):
    concept: tuple[NonEmptyString, ...]
    individual: tuple[NonEmptyString, ...]
    operator: tuple[NonEmptyString, ...]


class ElasticsearchSettings(_FrozenModel):
    endpoint_env: NonEmptyString
    index_env: NonEmptyString
    api_key_env: NonEmptyString
    request_timeout_seconds: Annotated[float, Field(gt=0)]
    fields: ElasticsearchFields
    roles: ElasticsearchRoles


class _ModelsFile(_FrozenModel):
    work: ModelSettings
    judge: ModelSettings
    embedding: EmbeddingSettings


class _ExperimentFile(_FrozenModel):
    dataset: DatasetSettings
    retrieval: RetrievalSettings
    aggregation: AggregationSettings
    evaluation: EvaluationSettings


class AppSettings(_FrozenModel):
    project_root: Path = Field(repr=False, exclude=True)
    work: ModelSettings
    judge: ModelSettings
    embedding: EmbeddingSettings
    dataset: DatasetSettings
    retrieval: RetrievalSettings
    aggregation: AggregationSettings
    evaluation: EvaluationSettings
    es: ElasticsearchSettings

    def require_work_api_key(self) -> str:
        return _require_environment(self.work.api_key_env, "work model client")

    def require_judge_api_key(self) -> str:
        return _require_environment(self.judge.api_key_env, "judge model client")

    def require_embedding_path(self) -> Path:
        raw_path = _require_environment(self.embedding.local_path_env, "embedding client")
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = self.project_root / path
        path = path.resolve()
        if not path.is_dir():
            raise SettingsError(
                f"Environment variable {self.embedding.local_path_env} must name an "
                "existing directory for the embedding client"
            )
        return path

    def require_es_connection(self) -> tuple[str, str, str]:
        endpoint = _require_environment(self.es.endpoint_env, "Elasticsearch client")
        index = _require_environment(self.es.index_env, "Elasticsearch client")
        api_key = _require_environment(self.es.api_key_env, "Elasticsearch client")
        return endpoint, index, api_key


def resolve_config_layout(root: Path) -> ConfigLayout:
    candidate = root.expanduser().resolve()
    if candidate.name == "config":
        layout = ConfigLayout(project_root=candidate.parent, config_dir=candidate)
    else:
        layout = ConfigLayout(project_root=candidate, config_dir=candidate / "config")
    project_config = _contains_config_files(layout.project_root)
    config_dir = _contains_config_files(layout.config_dir)
    if project_config and config_dir:
        raise SettingsError("Configuration layout is ambiguous")
    if not config_dir:
        raise SettingsError("Configuration layout is missing or nested incorrectly")
    return layout


def load_settings(root: Path | ConfigLayout) -> AppSettings:
    layout = root if isinstance(root, ConfigLayout) else resolve_config_layout(root)
    load_dotenv(layout.project_root / ".env.local", override=False)

    try:
        models = _ModelsFile.model_validate(_read_toml(layout.config_dir / "models.toml"))
        experiment = _ExperimentFile.model_validate(
            _read_toml(layout.config_dir / "experiment.toml")
        )
        es = ElasticsearchSettings.model_validate(_read_toml(layout.config_dir / "es_vocab.toml"))
    except ValidationError as exc:
        raise SettingsError(f"Invalid configuration under {layout.config_dir}: {exc}") from exc

    return AppSettings(
        project_root=layout.project_root,
        work=models.work,
        judge=models.judge,
        embedding=models.embedding,
        dataset=experiment.dataset,
        retrieval=experiment.retrieval,
        aggregation=experiment.aggregation,
        evaluation=experiment.evaluation,
        es=es,
    )


def _contains_config_files(root: Path) -> bool:
    return all((root / name).is_file() for name in _CONFIG_FILENAMES)


def _read_toml(path: Path) -> dict[str, object]:
    try:
        with path.open("rb") as stream:
            return cast(dict[str, object], tomllib.load(stream))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise SettingsError(f"Unable to load configuration file {path}: {exc}") from exc


def _require_environment(name: str, purpose: str) -> str:
    value = os.environ.get(name)
    if value is None or not value.strip():
        raise SettingsError(f"Environment variable {name} is required for the {purpose}")
    return value
