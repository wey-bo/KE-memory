from __future__ import annotations

from collections.abc import Sequence
import hashlib
import json
import os
from pathlib import Path
from typing import cast

import numpy as np
import pytest

from ke_memory_demo.aggregation import (
    SEMANTIC_DAG_STAGE,
    SessionMemory,
    create_aggregate_node,
)
from ke_memory_demo.domain import (
    AggregateNode,
    AggregateNodeKind,
    ConceptRef,
    Exchange,
    IndividualRef,
    KnowledgeEquation,
    KnowledgeLevel,
    Lifecycle,
    Message,
    MessageRole,
    MessageSpan,
    Modality,
    Polarity,
    Speaker,
)
from ke_memory_demo.embedding import (
    QUERY_INSTRUCTION,
    EmbeddingDocument,
    EmbeddingInvariantError,
    ExactVectorIndex,
    QwenEmbeddingBackend,
    fingerprint_model_directory,
    generate_embedding_documents,
)
from ke_memory_demo.settings import EmbeddingSettings
from ke_memory_demo.storage import ArtifactStore


def test_exact_index_returns_source_provenance() -> None:
    index = ExactVectorIndex(dimension=2)
    index.add(
        EmbeddingDocument(
            id="d1",
            text="alpha",
            vector=[1.0, 0.0],  # pyright: ignore[reportArgumentType]
            source_exchange_ids=["e1"],  # pyright: ignore[reportArgumentType]
        )
    )

    [hit] = index.search([1.0, 0.0], limit=1)

    assert hit.document_id == "d1"
    assert hit.source_exchange_ids == ["e1"]


@pytest.fixture
def local_model_dir(tmp_path: Path) -> Path:
    root = tmp_path / "qwen"
    (root / "nested").mkdir(parents=True)
    (root / "nested/config.json").write_text('{"hidden_size":1024}')
    (root / "tokenizer.json").write_text('{"version":"1.0"}')
    (root / "model.safetensors").write_bytes(b"weights")
    (root / "README.md").write_text("not fingerprinted")
    return root


def test_model_fingerprint_is_sorted_selective_and_content_sensitive(
    local_model_dir: Path,
) -> None:
    first = fingerprint_model_directory(local_model_dir)

    assert [item.path for item in first.files] == [
        "model.safetensors",
        "nested/config.json",
        "tokenizer.json",
    ]
    assert first == fingerprint_model_directory(local_model_dir)

    (local_model_dir / "README.md").write_text("ignored change")
    assert fingerprint_model_directory(local_model_dir) == first
    (local_model_dir / "model.safetensors").write_bytes(b"changed weights")
    assert fingerprint_model_directory(local_model_dir).sha256 != first.sha256


def test_model_fingerprint_rejects_a_symlink_escaping_model_root(
    local_model_dir: Path,
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside.safetensors"
    outside.write_bytes(b"outside")
    (local_model_dir / "escape.safetensors").symlink_to(outside)

    with pytest.raises(EmbeddingInvariantError, match="symlink.*escapes"):
        fingerprint_model_directory(local_model_dir)


@pytest.mark.parametrize(
    "missing_name", ["nested/config.json", "tokenizer.json", "model.safetensors"]
)
def test_model_fingerprint_requires_config_tokenizer_and_weight_files(
    local_model_dir: Path,
    missing_name: str,
) -> None:
    (local_model_dir / missing_name).unlink()

    with pytest.raises(EmbeddingInvariantError, match="config|tokenizer|weight"):
        fingerprint_model_directory(local_model_dir)


class _FakeQwenModel:
    def __init__(self, *, dimension: int = 1024, output: np.ndarray | None = None) -> None:
        self.dimension = dimension
        self.output = output
        self.calls: list[tuple[list[str], dict[str, object]]] = []
        self.tokenizer = _CodePointTokenizer()

    def get_sentence_embedding_dimension(self) -> int:
        return self.dimension

    def encode(self, sentences: list[str], **kwargs: object) -> np.ndarray:
        self.calls.append((sentences, kwargs))
        if self.output is not None:
            return self.output
        result = np.zeros((len(sentences), self.dimension), dtype=np.float64)
        result[:, 0] = 3.0
        result[:, 1] = 4.0
        return result


class _FakeModelFactory:
    def __init__(self, model: _FakeQwenModel) -> None:
        self.model = model
        self.calls: list[tuple[str, dict[str, object]]] = []

    def __call__(self, path: str, **kwargs: object) -> _FakeQwenModel:
        self.calls.append((path, kwargs))
        return self.model


def _embedding_settings() -> EmbeddingSettings:
    return EmbeddingSettings(
        enabled=True,
        model="Qwen/Qwen3-Embedding-0.6B",
        revision="97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3",
        local_path_env="KE_MEMORY_EMBEDDING_PATH",
        dimension=1024,
        chunk_tokens=1024,
        overlap_tokens=128,
        local_files_only=True,
    )


def test_qwen_backend_is_local_only_and_uses_query_instruction(
    local_model_dir: Path,
) -> None:
    model = _FakeQwenModel()
    factory = _FakeModelFactory(model)
    backend = QwenEmbeddingBackend(
        _embedding_settings(),
        local_model_dir,
        model_factory=factory,
    )

    [document] = backend.embed_documents(["document text"])
    query = backend.embed_query("where is the tea?")

    assert factory.calls == [
        (
            str(local_model_dir.resolve()),
            {"local_files_only": True, "trust_remote_code": True},
        )
    ]
    assert model.calls[0][0] == ["document text"]
    assert model.calls[1][0] == [f"{QUERY_INSTRUCTION}\nQuery: where is the tea?"]
    assert all(
        call[1]
        == {
            "batch_size": 32,
            "convert_to_numpy": True,
            "normalize_embeddings": False,
            "precision": "float32",
            "show_progress_bar": False,
        }
        for call in model.calls
    )
    assert document.dtype == np.float32
    assert query.dtype == np.float32
    np.testing.assert_allclose(cast(float, np.linalg.norm(document)), 1.0)
    np.testing.assert_allclose(cast(float, np.linalg.norm(query)), 1.0)
    assert backend.fingerprint == fingerprint_model_directory(local_model_dir)
    assert len(backend.configuration_hash) == 64


def test_qwen_backend_rejects_changed_model_fingerprint(local_model_dir: Path) -> None:
    backend = QwenEmbeddingBackend(
        _embedding_settings(),
        local_model_dir,
        model_factory=_FakeModelFactory(_FakeQwenModel()),
    )
    (local_model_dir / "model.safetensors").write_bytes(b"drift")

    with pytest.raises(EmbeddingInvariantError, match="fingerprint changed"):
        backend.embed_query("question")


@pytest.mark.parametrize(
    "output",
    [
        pytest.param(np.zeros((1, 1024)), id="zero-norm"),
        pytest.param(np.full((1, 1024), np.nan), id="nan"),
        pytest.param(np.full((1, 1024), np.inf), id="infinity"),
        pytest.param(np.ones((1, 1023)), id="wrong-dimension"),
    ],
)
def test_qwen_backend_rejects_invalid_model_vectors(
    local_model_dir: Path,
    output: np.ndarray,
) -> None:
    backend = QwenEmbeddingBackend(
        _embedding_settings(),
        local_model_dir,
        model_factory=_FakeModelFactory(_FakeQwenModel(output=output)),
    )

    with pytest.raises(EmbeddingInvariantError, match="dimension|NaN|infinity|non-zero"):
        backend.embed_documents(["document"])


def test_qwen_backend_requires_the_fixed_1024_dimension(local_model_dir: Path) -> None:
    with pytest.raises(
        EmbeddingInvariantError,
        match="Qwen3 embedding dimension must be 1024",
    ):
        QwenEmbeddingBackend(
            _embedding_settings(),
            local_model_dir,
            model_factory=_FakeModelFactory(_FakeQwenModel(dimension=768)),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("chunk_tokens", 512, id="chunk-tokens"),
        pytest.param("overlap_tokens", 64, id="overlap-tokens"),
    ],
)
def test_qwen_backend_requires_fixed_chunk_configuration(
    local_model_dir: Path,
    field: str,
    value: int,
) -> None:
    settings = _embedding_settings().model_copy(update={field: value})

    with pytest.raises(EmbeddingInvariantError, match="1024.*128"):
        QwenEmbeddingBackend(
            settings,
            local_model_dir,
            model_factory=_FakeModelFactory(_FakeQwenModel()),
        )


@pytest.mark.parametrize(
    "query",
    [
        pytest.param([0.0, 0.0], id="zero-norm"),
        pytest.param([float("nan"), 0.0], id="nan"),
        pytest.param([float("inf"), 0.0], id="infinity"),
        pytest.param([1.0], id="wrong-dimension"),
    ],
)
def test_exact_index_rejects_invalid_query_vectors(query: list[float]) -> None:
    with pytest.raises(EmbeddingInvariantError, match="dimension|NaN|infinity|non-zero"):
        ExactVectorIndex(dimension=2).search(query, limit=1)


def test_exact_index_normalizes_and_breaks_score_ties_by_document_id() -> None:
    index = ExactVectorIndex(dimension=2)
    index.add(EmbeddingDocument(id="d2", text="second", vector=(2.0, 0.0)))
    index.add(EmbeddingDocument(id="d1", text="first", vector=(1.0, 0.0)))

    hits = index.search([3.0, 0.0], limit=2)

    assert [hit.document_id for hit in hits] == ["d1", "d2"]
    assert all(np.isclose(np.linalg.norm(document.vector), 1.0) for document in index.documents)


def test_exact_index_persistence_is_deterministic_and_authenticated(tmp_path: Path) -> None:
    fingerprint = "f" * 64
    index = ExactVectorIndex(dimension=2, model_fingerprint=fingerprint)
    index.add(EmbeddingDocument(id="d2", text="second", vector=(0.0, 5.0)))
    index.add(EmbeddingDocument(id="d1", text="first", vector=(2.0, 0.0)))
    directory = tmp_path / "index"

    manifest = index.save(directory)
    first_bytes = {path.name: path.read_bytes() for path in directory.iterdir()}
    index.save(directory)

    assert {path.name: path.read_bytes() for path in directory.iterdir()} == first_bytes
    metadata = [
        json.loads(line) for line in (directory / "documents.jsonl").read_text().splitlines()
    ]
    assert [item["id"] for item in metadata] == ["d1", "d2"]
    assert all("vector" not in item for item in metadata)
    vectors = np.load(directory / "vectors.npy", allow_pickle=False)
    assert vectors.dtype == np.float32
    assert vectors.tolist() == [[1.0, 0.0], [0.0, 1.0]]
    assert manifest.record_count == 2
    assert (
        ExactVectorIndex.load(
            directory,
            expected_model_fingerprint=fingerprint,
        ).documents
        == index.documents
    )

    with pytest.raises(EmbeddingInvariantError, match="fingerprint"):
        ExactVectorIndex.load(directory, expected_model_fingerprint="changed")
    (directory / "vectors.npy").write_bytes(b"tampered")
    with pytest.raises(EmbeddingInvariantError, match="digest"):
        ExactVectorIndex.load(directory, expected_model_fingerprint=fingerprint)


def test_exact_index_uses_artifact_store_derived_cache_layout(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "state")
    index = ExactVectorIndex(dimension=2, model_fingerprint="f" * 64)
    index.add(EmbeddingDocument(id="d1", text="first", vector=(1.0, 0.0)))

    index.save_to_artifact_store(store, "run-1")
    loaded = ExactVectorIndex.load_from_artifact_store(
        store,
        "run-1",
        expected_model_fingerprint="f" * 64,
    )

    assert loaded.documents == index.documents
    assert set((store.root / "cache/run-1/embedding").iterdir()) == {
        store.root / "cache/run-1/embedding/documents.jsonl",
        store.root / "cache/run-1/embedding/vectors.npy",
        store.root / "cache/run-1/embedding/manifest.json",
    }


def test_exact_index_save_refuses_symlink_targets(tmp_path: Path) -> None:
    index = ExactVectorIndex(dimension=2)
    index.add(EmbeddingDocument(id="d1", text="first", vector=(1.0, 0.0)))
    directory = tmp_path / "index"
    directory.mkdir()
    outside = tmp_path / "outside"
    outside.write_bytes(b"unchanged")
    (directory / "documents.jsonl").symlink_to(outside)

    with pytest.raises(EmbeddingInvariantError, match="symlink"):
        index.save(directory)

    assert outside.read_bytes() == b"unchanged"


def test_exact_index_rejects_an_intermediate_symlink_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ke_memory_demo.embedding import index as index_module

    index = ExactVectorIndex(dimension=2)
    index.add(EmbeddingDocument(id="d1", text="first", vector=(1.0, 0.0)))
    managed = tmp_path / "managed"
    nested = managed / "nested"
    directory = nested / "index"
    directory.mkdir(parents=True)
    outside = tmp_path / "outside"
    (outside / "index").mkdir(parents=True)
    real_open = os.open
    swapped = False

    def swap_before_open(
        path: str | bytes | os.PathLike[str],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        path_text = os.fsdecode(path)
        if not swapped and (Path(path_text) == directory or path_text == "nested"):
            nested.rename(managed / "parked")
            nested.symlink_to(outside, target_is_directory=True)
            swapped = True
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(index_module.os, "open", swap_before_open)

    with pytest.raises(EmbeddingInvariantError, match="symlink|unsafe"):
        index.save(directory)

    assert swapped
    assert list((outside / "index").iterdir()) == []


class _CodePointTokenizer:
    def encode(self, text: str, *, add_special_tokens: bool) -> list[int]:
        assert add_special_tokens is False
        return [ord(character) for character in text]

    def decode(
        self,
        token_ids: Sequence[int],
        *,
        skip_special_tokens: bool,
        clean_up_tokenization_spaces: bool,
    ) -> str:
        assert skip_special_tokens is False
        assert clean_up_tokenization_spaces is False
        return "".join(chr(token_id) for token_id in token_ids)


class _FakeEmbeddingBackend:
    dimension = 2
    tokenizer = _CodePointTokenizer()

    def __init__(self) -> None:
        self.seen_texts: tuple[str, ...] = ()

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        self.seen_texts = tuple(texts)
        result = np.zeros((len(texts), 2), dtype=np.float32)
        result[:, 0] = 1.0
        return result

    def embed_query(self, question: str) -> np.ndarray:
        raise AssertionError(f"unexpected query: {question}")


def test_document_generation_chunk_configuration_cannot_be_overridden() -> None:
    with pytest.raises(TypeError, match="unexpected keyword argument 'chunk_tokens'"):
        generate_embedding_documents(
            (),
            (),
            (),
            (),
            backend=_FakeEmbeddingBackend(),
            chunk_tokens=1,  # pyright: ignore[reportCallIssue]
        )


def _knowledge_equation(
    *,
    level: KnowledgeLevel,
    gloss: str,
    speaker: Speaker,
    derived_from: Sequence[str],
    produced_in_stage: str,
    span: MessageSpan,
) -> KnowledgeEquation:
    return KnowledgeEquation.create(
        level=level,
        lhs=IndividualRef(term_id="person", label="Person"),
        rhs=ConceptRef(term_id="tea", label="Tea"),
        gloss=gloss,
        modality=Modality.PREFERENCE,
        polarity=Polarity.POSITIVE,
        lifecycle=Lifecycle.ACTIVE,
        speaker=speaker,
        evidence_refs=(span,),
        derived_from=derived_from,
        confidence=1.0,
        produced_in_run_id="run-1",
        produced_in_stage=produced_in_stage,
    )


@pytest.fixture
def layered_memory() -> tuple[
    Exchange,
    KnowledgeEquation,
    SessionMemory,
    AggregateNode,
]:
    exchange = Exchange(
        id="exchange-1",
        session_id="session-1",
        user=Message(id="user-1", role=MessageRole.USER, content="tea", source_order=0),
        assistant=Message(
            id="assistant-1",
            role=MessageRole.ASSISTANT,
            content="noted",
            source_order=1,
        ),
        global_ordinal=0,
    )
    span = MessageSpan(
        message_id="user-1",
        start_char=0,
        end_char=3,
        text_hash=hashlib.sha256(b"tea").hexdigest(),
    )
    turn_ke = _knowledge_equation(
        level=KnowledgeLevel.TURN,
        gloss="Person prefers tea.",
        speaker=Speaker.USER,
        derived_from=(),
        produced_in_stage="turn-extracted",
        span=span,
    )
    session_ke = _knowledge_equation(
        level=KnowledgeLevel.SESSION,
        gloss="Tea remains preferred.",
        speaker=Speaker.DERIVED,
        derived_from=(turn_ke.id,),
        produced_in_stage="session-aggregated",
        span=span,
    )
    session = SessionMemory(
        session_id="session-1",
        summary="The session records a tea preference.",
        knowledge_equations=(session_ke,),
        source_turn_ke_ids=(turn_ke.id,),
        evidence_closure=(span,),
    )
    aggregate_ke = _knowledge_equation(
        level=KnowledgeLevel.AGGREGATE,
        gloss="Tea is a stable preference.",
        speaker=Speaker.DERIVED,
        derived_from=(session_ke.id,),
        produced_in_stage=SEMANTIC_DAG_STAGE,
        span=span,
    )
    aggregate = create_aggregate_node(
        node_kind=AggregateNodeKind.PREFERENCE,
        title="Tea preference",
        summary="Across sessions, tea is preferred.",
        assertions=(aggregate_ke,),
        member_refs=(turn_ke.id, session_ke.id),
        derived_from=(session_ke.id,),
        evidence_closure=(span,),
        temporal_extent=None,
        confidence=1.0,
        depth=1,
    )
    return exchange, turn_ke, session, aggregate


def test_document_generation_covers_each_layer_with_deterministic_provenance(
    layered_memory: tuple[Exchange, KnowledgeEquation, SessionMemory, AggregateNode],
) -> None:
    exchange, turn_ke, session, aggregate = layered_memory
    backend = _FakeEmbeddingBackend()

    documents = generate_embedding_documents(
        (exchange,),
        (turn_ke,),
        (session,),
        (aggregate,),
        backend=backend,
        tokenizer=backend.tokenizer,
    )

    assert [document.id for document in documents] == sorted(document.id for document in documents)
    assert {cast(str, document.metadata["kind"]) for document in documents} == {
        "exchange",
        "turn_ke",
        "session_summary",
        "session_ke",
        "aggregate_summary",
        "aggregate_ke",
    }
    assert len(documents) == 6
    assert all(document.vector == (1.0, 0.0) for document in documents)
    assert all(document.source_exchange_ids == ("exchange-1",) for document in documents)
    assert next(
        item for item in documents if item.metadata["kind"] == "session_summary"
    ).source_session_ids == ("session-1",)
    assert next(
        item for item in documents if item.metadata["kind"] == "aggregate_summary"
    ).source_aggregate_ids == (aggregate.id,)
    assert "Person prefers tea." in backend.seen_texts


def test_document_generation_rejects_cross_session_evidence(
    layered_memory: tuple[Exchange, KnowledgeEquation, SessionMemory, AggregateNode],
) -> None:
    exchange, turn_ke, session, aggregate = layered_memory
    foreign_session = session.model_copy(update={"session_id": "session-2"})

    with pytest.raises(EmbeddingInvariantError, match="session-2.*session-1"):
        generate_embedding_documents(
            (exchange,),
            (turn_ke,),
            (foreign_session,),
            (aggregate,),
            backend=_FakeEmbeddingBackend(),
        )
