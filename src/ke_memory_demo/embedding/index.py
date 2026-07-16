from __future__ import annotations

from collections.abc import Generator, Iterable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import io
import os
from pathlib import Path
import stat
from typing import Annotated, Literal, Protocol, TypeVar, cast
from uuid import uuid4

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ke_memory_demo.aggregation import SessionMemory
from ke_memory_demo.core.ids import content_id
from ke_memory_demo.core.json import JsonObject, JsonValue, canonical_json
from ke_memory_demo.domain import (
    AggregateNode,
    Exchange,
    KnowledgeEquation,
    KnowledgeLevel,
    Message,
    MessageSpan,
    ToolEvent,
)
from ke_memory_demo.storage import ArtifactStore, StorageError, validate_storage_name

from .chunking import Tokenizer, chunk_text


NonEmptyString = Annotated[str, Field(min_length=1)]
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
ModelT = TypeVar("ModelT", bound=BaseModel)

INDEX_FORMAT_VERSION = "ke-memory-exact-vector-index/v1"
_INDEX_FILENAMES = frozenset({"documents.jsonl", "vectors.npy", "manifest.json"})


class EmbeddingError(RuntimeError):
    """Base class for deterministic embedding failures."""


class EmbeddingInvariantError(EmbeddingError, ValueError):
    """Embedding input, output, or persisted state violates its contract."""


class EmbeddingBackend(Protocol):
    @property
    def dimension(self) -> int: ...

    @property
    def tokenizer(self) -> Tokenizer: ...

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray: ...

    def embed_query(self, question: str) -> np.ndarray: ...


class EmbeddingDocument(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: NonEmptyString
    text: NonEmptyString
    vector: tuple[FiniteFloat, ...]
    source_exchange_ids: tuple[NonEmptyString, ...] = ()
    source_message_ids: tuple[NonEmptyString, ...] = ()
    source_ke_ids: tuple[NonEmptyString, ...] = ()
    source_session_ids: tuple[NonEmptyString, ...] = ()
    source_aggregate_ids: tuple[NonEmptyString, ...] = ()
    metadata: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_provenance(self) -> EmbeddingDocument:
        for label, values in (
            ("source exchange IDs", self.source_exchange_ids),
            ("source message IDs", self.source_message_ids),
            ("source KE IDs", self.source_ke_ids),
            ("source session IDs", self.source_session_ids),
            ("source aggregate IDs", self.source_aggregate_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate {label} are not allowed")
            if values != tuple(sorted(values)):
                raise ValueError(f"{label} must be sorted")
        return self


class SearchHit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: NonEmptyString
    text: NonEmptyString
    score: FiniteFloat
    source_exchange_ids: list[NonEmptyString] = Field(default_factory=list)
    source_message_ids: list[NonEmptyString] = Field(default_factory=list)
    source_ke_ids: list[NonEmptyString] = Field(default_factory=list)
    source_session_ids: list[NonEmptyString] = Field(default_factory=list)
    source_aggregate_ids: list[NonEmptyString] = Field(default_factory=list)
    metadata: JsonObject = Field(default_factory=dict)


class VectorIndexManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    format_version: Literal["ke-memory-exact-vector-index/v1"] = INDEX_FORMAT_VERSION
    dimension: PositiveInt
    record_count: NonNegativeInt
    model_fingerprint: NonEmptyString | None = None
    documents_sha256: Sha256Hex
    vectors_sha256: Sha256Hex


class _EmbeddingDocumentMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: NonEmptyString
    text: NonEmptyString
    source_exchange_ids: tuple[NonEmptyString, ...] = ()
    source_message_ids: tuple[NonEmptyString, ...] = ()
    source_ke_ids: tuple[NonEmptyString, ...] = ()
    source_session_ids: tuple[NonEmptyString, ...] = ()
    source_aggregate_ids: tuple[NonEmptyString, ...] = ()
    metadata: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_provenance(self) -> _EmbeddingDocumentMetadata:
        _validate_provenance_tuples(self)
        return self


class ExactVectorIndex:
    def __init__(self, *, dimension: int, model_fingerprint: str | None = None) -> None:
        if isinstance(dimension, bool) or dimension <= 0:
            raise EmbeddingInvariantError("index dimension must be a positive integer")
        if model_fingerprint is not None and not model_fingerprint:
            raise EmbeddingInvariantError("model fingerprint must not be empty")
        self.dimension = dimension
        self.model_fingerprint = model_fingerprint
        self._documents: dict[str, EmbeddingDocument] = {}

    @property
    def documents(self) -> tuple[EmbeddingDocument, ...]:
        return tuple(self._documents[key] for key in sorted(self._documents))

    def add(self, document: EmbeddingDocument) -> None:
        try:
            validated = EmbeddingDocument.model_validate(document.model_dump(mode="python"))
        except (AttributeError, TypeError, ValueError) as error:
            raise EmbeddingInvariantError(f"invalid embedding document: {error}") from error
        if validated.id in self._documents:
            raise EmbeddingInvariantError(f"duplicate embedding document ID: {validated.id}")
        vector = _normalized_vector(
            validated.vector,
            dimension=self.dimension,
            label=f"document {validated.id} vector",
        )
        self._documents[validated.id] = validated.model_copy(
            update={"vector": tuple(float(value) for value in vector)}
        )

    def add_all(self, documents: Iterable[EmbeddingDocument]) -> None:
        for document in documents:
            self.add(document)

    def search(self, query: Sequence[float], *, limit: int) -> list[SearchHit]:
        if isinstance(limit, bool) or limit <= 0:
            raise EmbeddingInvariantError("search limit must be a positive integer")
        query_vector = _normalized_vector(
            query,
            dimension=self.dimension,
            label="query vector",
        )
        documents = self.documents
        if not documents:
            return []
        matrix = np.asarray([document.vector for document in documents], dtype=np.float32)
        scores = matrix @ query_vector
        ranked = sorted(
            zip(documents, scores, strict=True),
            key=lambda item: (-float(item[1]), item[0].id),
        )
        return [_search_hit(document, float(score)) for document, score in ranked[:limit]]

    def save(self, directory: Path) -> VectorIndexManifest:
        documents = self.documents
        metadata_bytes = b"".join(
            canonical_json(_metadata_from_document(document)) + b"\n" for document in documents
        )
        vectors = _document_matrix(documents, self.dimension)
        vectors_bytes = _npy_bytes(vectors)
        manifest = VectorIndexManifest(
            dimension=self.dimension,
            record_count=len(documents),
            model_fingerprint=self.model_fingerprint,
            documents_sha256=hashlib.sha256(metadata_bytes).hexdigest(),
            vectors_sha256=hashlib.sha256(vectors_bytes).hexdigest(),
        )
        try:
            with _open_index_directory(directory, create=True) as directory_fd:
                entries = set(os.listdir(directory_fd))
                unexpected = sorted(entries.difference(_INDEX_FILENAMES))
                if unexpected:
                    raise EmbeddingInvariantError(
                        f"vector index directory contains unexpected entry: {unexpected[0]}"
                    )
                _write_regular_atomic_at(directory_fd, "documents.jsonl", metadata_bytes)
                _write_regular_atomic_at(directory_fd, "vectors.npy", vectors_bytes)
                _write_regular_atomic_at(
                    directory_fd,
                    "manifest.json",
                    canonical_json(manifest),
                )
        except EmbeddingInvariantError:
            raise
        except OSError as error:
            raise EmbeddingInvariantError(f"unable to save vector index: {error}") from error
        return manifest

    def save_to_artifact_store(
        self,
        store: ArtifactStore,
        run_id: str,
    ) -> VectorIndexManifest:
        return self.save(_artifact_store_directory(store, run_id))

    @classmethod
    def load(
        cls,
        directory: Path,
        *,
        expected_model_fingerprint: str | None = None,
    ) -> ExactVectorIndex:
        try:
            with _open_index_directory(directory, create=False) as directory_fd:
                entries = set(os.listdir(directory_fd))
                if frozenset(entries) != _INDEX_FILENAMES:
                    raise EmbeddingInvariantError(
                        "vector index files disagree with the required canonical layout"
                    )
                manifest_bytes = _read_regular_at(directory_fd, "manifest.json")
                documents_bytes = _read_regular_at(directory_fd, "documents.jsonl")
                vectors_bytes = _read_regular_at(directory_fd, "vectors.npy")
        except EmbeddingInvariantError:
            raise
        except OSError as error:
            raise EmbeddingInvariantError(f"unable to load vector index: {error}") from error

        manifest = _parse_manifest(manifest_bytes)
        if hashlib.sha256(documents_bytes).hexdigest() != manifest.documents_sha256:
            raise EmbeddingInvariantError("vector index document digest does not match manifest")
        if hashlib.sha256(vectors_bytes).hexdigest() != manifest.vectors_sha256:
            raise EmbeddingInvariantError("vector index vector digest does not match manifest")
        if (
            expected_model_fingerprint is not None
            and manifest.model_fingerprint != expected_model_fingerprint
        ):
            raise EmbeddingInvariantError("vector index model fingerprint does not match")

        metadata = _parse_document_metadata(documents_bytes)
        if len(metadata) != manifest.record_count:
            raise EmbeddingInvariantError("vector index record count does not match manifest")
        vectors = _parse_vectors(
            vectors_bytes,
            rows=manifest.record_count,
            dimension=manifest.dimension,
        )
        index = cls(
            dimension=manifest.dimension,
            model_fingerprint=manifest.model_fingerprint,
        )
        for position, item in enumerate(metadata):
            index.add(
                EmbeddingDocument(
                    **item.model_dump(mode="python"),
                    vector=tuple(float(value) for value in vectors[position]),
                )
            )
        return index

    @classmethod
    def load_from_artifact_store(
        cls,
        store: ArtifactStore,
        run_id: str,
        *,
        expected_model_fingerprint: str | None = None,
    ) -> ExactVectorIndex:
        return cls.load(
            _artifact_store_directory(store, run_id),
            expected_model_fingerprint=expected_model_fingerprint,
        )


@dataclass(frozen=True)
class _SourceText:
    kind: str
    source_id: str
    text: str
    source_revision: str | None = None
    source_exchange_ids: tuple[str, ...] = ()
    source_message_ids: tuple[str, ...] = ()
    source_ke_ids: tuple[str, ...] = ()
    source_session_ids: tuple[str, ...] = ()
    source_aggregate_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class _RecordOwner:
    record: Message | ToolEvent
    exchange_id: str
    session_id: str


@dataclass(frozen=True)
class _SpanProvenance:
    source_exchange_ids: tuple[str, ...]
    source_message_ids: tuple[str, ...]
    source_session_ids: tuple[str, ...]


def generate_embedding_documents(
    exchanges: Sequence[Exchange],
    turn_kes: Sequence[KnowledgeEquation],
    sessions: Sequence[SessionMemory],
    aggregates: Sequence[AggregateNode],
    *,
    backend: EmbeddingBackend,
    tokenizer: Tokenizer | None = None,
    chunk_tokens: int = 1024,
    overlap_tokens: int = 128,
) -> tuple[EmbeddingDocument, ...]:
    validated_exchanges = _validated_records(exchanges, Exchange, label="exchange")
    validated_turn_kes = _validated_records(turn_kes, KnowledgeEquation, label="Turn KE")
    validated_sessions = _validated_records(sessions, SessionMemory, label="session memory")
    validated_aggregates = _validated_records(aggregates, AggregateNode, label="aggregate")
    _reject_duplicate_keys(
        tuple(exchange.id for exchange in validated_exchanges),
        "exchange IDs",
    )
    _reject_duplicate_keys(
        tuple((item.id, item.revision) for item in validated_turn_kes),
        "Turn KE revisions",
    )
    _reject_duplicate_keys(
        tuple(item.session_id for item in validated_sessions),
        "session memory IDs",
    )
    _reject_duplicate_keys(
        tuple((item.id, item.revision) for item in validated_aggregates),
        "aggregate revisions",
    )
    if any(item.level is not KnowledgeLevel.TURN for item in validated_turn_kes):
        raise EmbeddingInvariantError("turn_kes may contain only Turn-level KEs")
    if any(
        item.level is not KnowledgeLevel.SESSION
        for session in validated_sessions
        for item in session.knowledge_equations
    ):
        raise EmbeddingInvariantError("session memories may contain only Session-level KEs")
    if any(
        item.level is not KnowledgeLevel.AGGREGATE
        for aggregate in validated_aggregates
        for item in aggregate.assertions
    ):
        raise EmbeddingInvariantError("aggregates may contain only Aggregate-level KEs")

    owners = _record_owners(validated_exchanges)
    source_texts: list[_SourceText] = []
    for exchange in sorted(validated_exchanges, key=lambda item: (item.global_ordinal, item.id)):
        records = (exchange.user, *exchange.events, exchange.assistant)
        source_texts.append(
            _SourceText(
                kind="exchange",
                source_id=exchange.id,
                text=_render_exchange(exchange),
                source_exchange_ids=(exchange.id,),
                source_message_ids=tuple(sorted(record.id for record in records)),
                source_session_ids=(exchange.session_id,),
            )
        )
    for equation in sorted(validated_turn_kes, key=lambda item: (item.id, item.revision)):
        provenance = _span_provenance(equation.evidence_refs, owners)
        source_texts.append(
            _SourceText(
                kind="turn_ke",
                source_id=equation.id,
                source_revision=equation.revision,
                text=equation.gloss,
                source_ke_ids=(equation.id,),
                source_exchange_ids=provenance.source_exchange_ids,
                source_message_ids=provenance.source_message_ids,
                source_session_ids=provenance.source_session_ids,
            )
        )
    for session in sorted(validated_sessions, key=lambda item: item.session_id):
        summary_provenance = _span_provenance(session.evidence_closure, owners)
        _validate_session_provenance(session.session_id, summary_provenance)
        source_texts.append(
            _SourceText(
                kind="session_summary",
                source_id=session.session_id,
                text=session.summary,
                source_ke_ids=session.source_turn_ke_ids,
                source_session_ids=(session.session_id,),
                source_exchange_ids=summary_provenance.source_exchange_ids,
                source_message_ids=summary_provenance.source_message_ids,
            )
        )
        for equation in session.knowledge_equations:
            provenance = _span_provenance(equation.evidence_refs, owners)
            _validate_session_provenance(session.session_id, provenance)
            source_texts.append(
                _SourceText(
                    kind="session_ke",
                    source_id=equation.id,
                    source_revision=equation.revision,
                    text=equation.gloss,
                    source_ke_ids=(equation.id,),
                    source_session_ids=(session.session_id,),
                    source_exchange_ids=provenance.source_exchange_ids,
                    source_message_ids=provenance.source_message_ids,
                )
            )
    for aggregate in sorted(validated_aggregates, key=lambda item: (item.depth, item.id)):
        summary_provenance = _span_provenance(aggregate.evidence_closure, owners)
        source_texts.append(
            _SourceText(
                kind="aggregate_summary",
                source_id=aggregate.id,
                source_revision=aggregate.revision,
                text=aggregate.summary,
                source_ke_ids=aggregate.derived_from,
                source_aggregate_ids=(aggregate.id,),
                source_exchange_ids=summary_provenance.source_exchange_ids,
                source_message_ids=summary_provenance.source_message_ids,
                source_session_ids=summary_provenance.source_session_ids,
            )
        )
        for equation in aggregate.assertions:
            provenance = _span_provenance(equation.evidence_refs, owners)
            source_texts.append(
                _SourceText(
                    kind="aggregate_ke",
                    source_id=equation.id,
                    source_revision=equation.revision,
                    text=equation.gloss,
                    source_ke_ids=(equation.id,),
                    source_aggregate_ids=(aggregate.id,),
                    source_exchange_ids=provenance.source_exchange_ids,
                    source_message_ids=provenance.source_message_ids,
                    source_session_ids=provenance.source_session_ids,
                )
            )

    actual_tokenizer = tokenizer or backend.tokenizer
    metadata_records: list[_EmbeddingDocumentMetadata] = []
    for source in source_texts:
        chunks = chunk_text(
            source.text,
            actual_tokenizer,
            chunk_tokens=chunk_tokens,
            overlap_tokens=overlap_tokens,
        )
        if not chunks:
            raise EmbeddingInvariantError(
                f"embedding source tokenized to an empty sequence: {source.kind}/{source.source_id}"
            )
        for chunk in chunks:
            metadata: JsonObject = {
                "kind": source.kind,
                "source_id": source.source_id,
                "token_start": chunk.token_start,
                "token_end": chunk.token_end,
            }
            if source.source_revision is not None:
                metadata["source_revision"] = source.source_revision
            payload = cast(
                JsonValue,
                {
                    "text": chunk.text,
                    "source_exchange_ids": list(source.source_exchange_ids),
                    "source_message_ids": list(source.source_message_ids),
                    "source_ke_ids": list(source.source_ke_ids),
                    "source_session_ids": list(source.source_session_ids),
                    "source_aggregate_ids": list(source.source_aggregate_ids),
                    "metadata": metadata,
                },
            )
            metadata_records.append(
                _EmbeddingDocumentMetadata(
                    id=content_id("embedding-document", payload),
                    text=chunk.text,
                    source_exchange_ids=source.source_exchange_ids,
                    source_message_ids=source.source_message_ids,
                    source_ke_ids=source.source_ke_ids,
                    source_session_ids=source.source_session_ids,
                    source_aggregate_ids=source.source_aggregate_ids,
                    metadata=metadata,
                )
            )
    metadata_records.sort(key=lambda item: item.id)
    _reject_duplicate_keys(tuple(item.id for item in metadata_records), "embedding document IDs")
    if not metadata_records:
        return ()
    if isinstance(backend.dimension, bool) or backend.dimension <= 0:
        raise EmbeddingInvariantError("embedding backend dimension must be a positive integer")
    raw_vectors = backend.embed_documents(tuple(item.text for item in metadata_records))
    vectors = _normalized_output_matrix(
        raw_vectors,
        rows=len(metadata_records),
        dimension=backend.dimension,
    )
    return tuple(
        EmbeddingDocument(
            **item.model_dump(mode="python"),
            vector=tuple(float(value) for value in vectors[position]),
        )
        for position, item in enumerate(metadata_records)
    )


def _validated_records(
    records: Sequence[ModelT],
    model: type[ModelT],
    *,
    label: str,
) -> tuple[ModelT, ...]:
    validated: list[ModelT] = []
    try:
        for record in records:
            validated.append(model.model_validate(record.model_dump(mode="python")))
    except (AttributeError, TypeError, ValueError, ValidationError) as error:
        raise EmbeddingInvariantError(f"invalid {label} input: {error}") from error
    return tuple(validated)


def _record_owners(exchanges: Sequence[Exchange]) -> dict[str, _RecordOwner]:
    owners: dict[str, _RecordOwner] = {}
    for exchange in exchanges:
        for record in (exchange.user, *exchange.events, exchange.assistant):
            if record.id in owners:
                raise EmbeddingInvariantError(f"duplicate source record ID: {record.id}")
            owners[record.id] = _RecordOwner(
                record=record,
                exchange_id=exchange.id,
                session_id=exchange.session_id,
            )
    return owners


def _span_provenance(
    spans: Sequence[MessageSpan],
    owners: Mapping[str, _RecordOwner],
) -> _SpanProvenance:
    exchange_ids: set[str] = set()
    message_ids: set[str] = set()
    session_ids: set[str] = set()
    for span in spans:
        owner = owners.get(span.message_id)
        if owner is None:
            raise EmbeddingInvariantError(
                f"embedding source span references missing record {span.message_id}"
            )
        content = owner.record.content
        if span.end_char > len(content):
            raise EmbeddingInvariantError(
                f"embedding source span is outside record {span.message_id}"
            )
        expected_hash = hashlib.sha256(
            content[span.start_char : span.end_char].encode("utf-8")
        ).hexdigest()
        if span.text_hash != expected_hash:
            raise EmbeddingInvariantError(
                f"embedding source span hash does not match record {span.message_id}"
            )
        exchange_ids.add(owner.exchange_id)
        message_ids.add(span.message_id)
        session_ids.add(owner.session_id)
    return _SpanProvenance(
        source_exchange_ids=tuple(sorted(exchange_ids)),
        source_message_ids=tuple(sorted(message_ids)),
        source_session_ids=tuple(sorted(session_ids)),
    )


def _render_exchange(exchange: Exchange) -> str:
    rendered: list[str] = [f"User:\n{exchange.user.content}"]
    for event in exchange.events:
        label = "Tool call" if event.kind.value == "tool_call" else "Tool result"
        rendered.append(f"{label}:\n{event.content}")
    rendered.append(f"Assistant:\n{exchange.assistant.content}")
    return "\n\n".join(rendered)


def _validate_session_provenance(
    session_id: str,
    provenance: _SpanProvenance,
) -> None:
    foreign = tuple(
        source_session_id
        for source_session_id in provenance.source_session_ids
        if source_session_id != session_id
    )
    if foreign:
        raise EmbeddingInvariantError(
            f"session memory {session_id} cites evidence from session {foreign[0]}"
        )


def _normalized_output_matrix(raw: object, *, rows: int, dimension: int) -> np.ndarray:
    try:
        matrix = np.asarray(raw, dtype=np.float32)
    except (TypeError, ValueError, OverflowError) as error:
        raise EmbeddingInvariantError("embedding backend output must be numeric") from error
    if matrix.ndim == 1 and rows == 1:
        matrix = matrix.reshape(1, -1)
    if matrix.ndim != 2 or matrix.shape != (rows, dimension):
        raise EmbeddingInvariantError(
            f"embedding backend output must have shape ({rows}, {dimension})"
        )
    return np.stack(
        [
            _normalized_vector(row, dimension=dimension, label="embedding backend vector")
            for row in matrix
        ],
        axis=0,
    ).astype(np.float32, copy=False)


def _validate_provenance_tuples(record: EmbeddingDocument | _EmbeddingDocumentMetadata) -> None:
    for label, values in (
        ("source exchange IDs", record.source_exchange_ids),
        ("source message IDs", record.source_message_ids),
        ("source KE IDs", record.source_ke_ids),
        ("source session IDs", record.source_session_ids),
        ("source aggregate IDs", record.source_aggregate_ids),
    ):
        if len(values) != len(set(values)):
            raise ValueError(f"duplicate {label} are not allowed")
        if values != tuple(sorted(values)):
            raise ValueError(f"{label} must be sorted")


def _reject_duplicate_keys(values: Sequence[object], label: str) -> None:
    if len(values) != len(set(values)):
        raise EmbeddingInvariantError(f"duplicate {label} are not allowed")


def _metadata_from_document(document: EmbeddingDocument) -> _EmbeddingDocumentMetadata:
    return _EmbeddingDocumentMetadata.model_validate(
        document.model_dump(mode="python", exclude={"vector"})
    )


def _document_matrix(
    documents: Sequence[EmbeddingDocument],
    dimension: int,
) -> np.ndarray:
    if not documents:
        return np.empty((0, dimension), dtype=np.float32)
    matrix = np.asarray([document.vector for document in documents], dtype=np.float32)
    if matrix.shape != (len(documents), dimension) or not np.isfinite(matrix).all():
        raise EmbeddingInvariantError("embedding documents cannot form a valid vector matrix")
    return matrix


def _npy_bytes(matrix: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    np.save(buffer, np.asarray(matrix, dtype=np.float32), allow_pickle=False)
    return buffer.getvalue()


def _parse_manifest(data: bytes) -> VectorIndexManifest:
    try:
        manifest = VectorIndexManifest.model_validate_json(data)
    except (ValueError, ValidationError) as error:
        raise EmbeddingInvariantError(f"invalid vector index manifest: {error}") from error
    if canonical_json(manifest) != data:
        raise EmbeddingInvariantError("vector index manifest is not canonical JSON")
    return manifest


def _parse_document_metadata(data: bytes) -> tuple[_EmbeddingDocumentMetadata, ...]:
    if not data:
        return ()
    if not data.endswith(b"\n") or b"\n\n" in data:
        raise EmbeddingInvariantError("vector index document JSONL framing is invalid")
    records: list[_EmbeddingDocumentMetadata] = []
    for line in data[:-1].split(b"\n"):
        try:
            record = _EmbeddingDocumentMetadata.model_validate_json(line)
        except (ValueError, ValidationError) as error:
            raise EmbeddingInvariantError(
                f"invalid vector index document metadata: {error}"
            ) from error
        if canonical_json(record) != line:
            raise EmbeddingInvariantError("vector index document metadata is not canonical JSON")
        records.append(record)
    ids = tuple(record.id for record in records)
    if ids != tuple(sorted(ids)) or len(ids) != len(set(ids)):
        raise EmbeddingInvariantError("vector index document metadata must have unique sorted IDs")
    return tuple(records)


def _parse_vectors(data: bytes, *, rows: int, dimension: int) -> np.ndarray:
    try:
        loaded = np.load(io.BytesIO(data), allow_pickle=False)
        vectors = np.asarray(loaded)
    except (OSError, TypeError, ValueError) as error:
        raise EmbeddingInvariantError(f"invalid vector index array: {error}") from error
    if vectors.dtype != np.dtype(np.float32):
        raise EmbeddingInvariantError("vector index array must use float32")
    if vectors.shape != (rows, dimension):
        raise EmbeddingInvariantError(f"vector index array must have shape ({rows}, {dimension})")
    if not np.isfinite(vectors).all():
        raise EmbeddingInvariantError("vector index array contains NaN or infinity")
    if rows:
        norms = np.linalg.norm(vectors.astype(np.float64), axis=1)
        if not np.allclose(norms, 1.0, rtol=1e-5, atol=1e-6):
            raise EmbeddingInvariantError("vector index array contains non-normalized vectors")
    if _npy_bytes(vectors) != data:
        raise EmbeddingInvariantError("vector index array is not in canonical NPY form")
    return vectors


def _artifact_store_directory(store: ArtifactStore, run_id: str) -> Path:
    try:
        validate_storage_name(run_id, label="run ID")
        directory = store.layout.cache_root / run_id / "embedding"
        store.layout.assert_safe(directory)
    except (AttributeError, StorageError, ValueError) as error:
        raise EmbeddingInvariantError(
            f"invalid artifact-store vector index path: {error}"
        ) from error
    return directory


@contextmanager
def _open_index_directory(path: Path, *, create: bool) -> Generator[int, None, None]:
    expanded = path.expanduser()
    if ".." in expanded.parts:
        raise EmbeddingInvariantError("vector index path must not contain '..'")
    absolute = Path(os.path.abspath(expanded))
    descriptor = _open_directory_tree(absolute, create=create)
    try:
        yield descriptor
    finally:
        os.close(descriptor)


def _open_directory_tree(path: Path, *, create: bool) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    completed = False
    try:
        descriptor = os.open(path.anchor, flags)
        for part in path.parts[1:]:
            if create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
                else:
                    os.fsync(descriptor)
            child = os.open(part, flags, dir_fd=descriptor)
            metadata = os.fstat(child)
            if not stat.S_ISDIR(metadata.st_mode):
                os.close(child)
                raise EmbeddingInvariantError(
                    f"vector index path component is not a directory: {part}"
                )
            os.close(descriptor)
            descriptor = child
        completed = True
        return descriptor
    except FileNotFoundError as error:
        raise EmbeddingInvariantError(f"vector index directory does not exist: {path}") from error
    except EmbeddingInvariantError:
        raise
    except OSError as error:
        raise EmbeddingInvariantError(
            f"vector index directory is unsafe or unreadable: {path}"
        ) from error
    finally:
        if not completed and descriptor >= 0:
            os.close(descriptor)


def _write_regular_atomic_at(directory_fd: int, name: str, data: bytes) -> None:
    existing = _stat_at(directory_fd, name)
    if existing is not None:
        if stat.S_ISLNK(existing.st_mode):
            raise EmbeddingInvariantError(f"vector index file is a symlink: {name}")
        if not stat.S_ISREG(existing.st_mode):
            raise EmbeddingInvariantError(f"vector index path is not a regular file: {name}")
    temporary = f".{name}.tmp-{uuid4().hex}"
    descriptor = -1
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=directory_fd,
        )
        remaining = memoryview(data)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("short write made no progress")
            remaining = remaining[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(
            temporary,
            name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        os.fsync(directory_fd)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary, dir_fd=directory_fd)
        except FileNotFoundError:
            pass


def _read_regular_at(directory_fd: int, name: str) -> bytes:
    metadata = _stat_at(directory_fd, name)
    if metadata is None:
        raise EmbeddingInvariantError(f"vector index file is missing: {name}")
    if stat.S_ISLNK(metadata.st_mode):
        raise EmbeddingInvariantError(f"vector index file is a symlink: {name}")
    if not stat.S_ISREG(metadata.st_mode):
        raise EmbeddingInvariantError(f"vector index path is not a regular file: {name}")
    descriptor = os.open(
        name,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=directory_fd,
    )
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise EmbeddingInvariantError(f"vector index path is not a regular file: {name}")
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 1024 * 1024):
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _stat_at(directory_fd: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _normalized_vector(
    values: object,
    *,
    dimension: int,
    label: str,
) -> np.ndarray:
    try:
        vector = np.asarray(values, dtype=np.float32)
    except (TypeError, ValueError, OverflowError) as error:
        raise EmbeddingInvariantError(f"{label} must contain numeric values") from error
    if vector.ndim != 1 or vector.shape[0] != dimension:
        raise EmbeddingInvariantError(f"{label} must have dimension {dimension}")
    if not np.isfinite(vector).all():
        raise EmbeddingInvariantError(f"{label} contains NaN or infinity")
    norm = float(np.linalg.norm(vector.astype(np.float64)))
    if not np.isfinite(norm) or norm == 0.0:
        raise EmbeddingInvariantError(f"{label} must have a finite non-zero norm")
    normalized = np.asarray(vector / norm, dtype=np.float32)
    if not np.isfinite(normalized).all():
        raise EmbeddingInvariantError(f"{label} normalization produced NaN or infinity")
    return normalized


def _search_hit(document: EmbeddingDocument, score: float) -> SearchHit:
    return SearchHit(
        document_id=document.id,
        text=document.text,
        score=score,
        source_exchange_ids=list(document.source_exchange_ids),
        source_message_ids=list(document.source_message_ids),
        source_ke_ids=list(document.source_ke_ids),
        source_session_ids=list(document.source_session_ids),
        source_aggregate_ids=list(document.source_aggregate_ids),
        metadata=dict(document.metadata),
    )
