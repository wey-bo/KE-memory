from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
import os
from pathlib import Path
import tomllib
from typing import Annotated, Literal, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ke_memory_demo.domain import Exchange
from ke_memory_demo.embedding import QwenEmbeddingBackend
from ke_memory_demo.extraction import LifecycleMaintainer, TurnExtractionResult, TurnKEExtractor
from ke_memory_demo.infra.llm import StructuredModelClient
from ke_memory_demo.infra.telemetry import InMemoryTraceRecorder
from ke_memory_ontology import ElasticsearchVocabulary
from ke_memory_demo.settings import SettingsError, load_settings

from ke_memory_demo.online.extractor import LifecycleMaintainerAdapter, TurnKEExtractorAdapter
from ke_memory_demo.online.repository import SQLiteOnlineMemoryRepository
from ke_memory_demo.online.retrieval import DenseCandidateFallback, OntologyMemoryRetriever
from ke_memory_demo.online.service import OntologyMemoryService


NonEmptyString = Annotated[str, Field(min_length=1)]
Port = Annotated[int, Field(ge=1, le=65535)]


class _OnlineConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Literal["offline", "production"]
    database_path: Path
    host: NonEmptyString
    port: Port
    keol_commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]


class _OnlineConfigFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    online: _OnlineConfig


class _AsyncCloser(Protocol):
    async def aclose(self) -> None: ...


class EmptyOnlineExtractor:
    async def extract(self, exchange: Exchange) -> TurnExtractionResult:
        return TurnExtractionResult(exchange_id=exchange.id)


class OnlineRuntime:
    def __init__(
        self,
        *,
        mode: str,
        repository: SQLiteOnlineMemoryRepository,
        service: OntologyMemoryService,
        retriever: OntologyMemoryRetriever,
        extraction_ready: bool,
        host: str = "127.0.0.1",
        port: int = 8787,
        keol_commit: str = "44631e64fd07c9b85f22e36035bf49c882dba592",
        closers: Sequence[_AsyncCloser] = (),
    ) -> None:
        self.mode = mode
        self.repository = repository
        self.service = service
        self.retriever = retriever
        self.extraction_ready = extraction_ready
        self.host = host
        self.port = port
        self.keol_commit = keol_commit
        self._closers = tuple(closers)

    async def aclose(self) -> None:
        errors: list[Exception] = []
        for closer in reversed(self._closers):
            try:
                await closer.aclose()
            except Exception as error:
                errors.append(error)
        if errors:
            raise RuntimeError("online runtime resource cleanup failed") from errors[0]


def build_online_runtime(root: str | Path) -> OnlineRuntime:
    project_root = _project_root(Path(root))
    config = _load_online_config(project_root)
    config = _apply_environment_overrides(config)
    database_path = config.database_path
    if not database_path.is_absolute():
        database_path = project_root / database_path
    repository = SQLiteOnlineMemoryRepository(database_path.resolve())

    if config.mode == "offline":
        service = OntologyMemoryService(
            repository=repository,
            extractor=EmptyOnlineExtractor(),
        )
        return OnlineRuntime(
            mode=config.mode,
            repository=repository,
            service=service,
            retriever=OntologyMemoryRetriever(repository=repository),
            extraction_ready=False,
            host=config.host,
            port=config.port,
            keol_commit=config.keol_commit,
        )

    settings = load_settings(project_root)
    settings.require_work_api_key()
    settings.require_es_connection()
    recorder = InMemoryTraceRecorder()
    model = StructuredModelClient.from_app_settings(
        settings,
        supports_json_schema=True,
        trace_recorder=recorder,
    )
    ontology = ElasticsearchVocabulary.from_app_settings(settings)
    run_id = f"online-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    extractor = TurnKEExtractorAdapter(
        TurnKEExtractor(model, ontology, run_id=run_id)
    )
    lifecycle = LifecycleMaintainerAdapter(
        LifecycleMaintainer(model, run_id=run_id)
    )
    service = OntologyMemoryService(
        repository=repository,
        extractor=extractor,
        lifecycle=lifecycle,
    )
    fallback = (
        DenseCandidateFallback(QwenEmbeddingBackend(settings))
        if settings.embedding.enabled
        else None
    )
    return OnlineRuntime(
        mode=config.mode,
        repository=repository,
        service=service,
        retriever=OntologyMemoryRetriever(repository=repository, fallback=fallback),
        extraction_ready=True,
        host=config.host,
        port=config.port,
        keol_commit=config.keol_commit,
        closers=(model, ontology),
    )


def _project_root(root: Path) -> Path:
    resolved = root.expanduser().resolve()
    return resolved.parent if resolved.name == "config" else resolved


def _load_online_config(project_root: Path) -> _OnlineConfig:
    path = project_root / "config" / "online.toml"
    try:
        with path.open("rb") as stream:
            payload = cast(dict[str, object], tomllib.load(stream))
        return _OnlineConfigFile.model_validate(payload).online
    except (OSError, tomllib.TOMLDecodeError, ValidationError) as error:
        raise SettingsError(f"Invalid online configuration {path}: {error}") from error


def _apply_environment_overrides(config: _OnlineConfig) -> _OnlineConfig:
    updates: dict[str, object] = {}
    environment_fields = {
        "KE_MEMORY_ONLINE_MODE": "mode",
        "KE_MEMORY_DATABASE_PATH": "database_path",
        "KE_MEMORY_HOST": "host",
        "KE_MEMORY_PORT": "port",
    }
    for environment_name, field_name in environment_fields.items():
        value = os.environ.get(environment_name, "").strip()
        if value:
            updates[field_name] = value
    if not updates:
        return config
    try:
        return _OnlineConfig.model_validate({**config.model_dump(), **updates})
    except ValidationError as error:
        raise SettingsError(f"Invalid online environment override: {error}") from error
