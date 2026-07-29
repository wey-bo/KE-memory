import sys
from types import SimpleNamespace

import tools.ontology_memory_experiment.dense as dense_module
from tools.ontology_memory_experiment.dense import CachingEncoder, rank_dense
from tools.ontology_memory_experiment.dense import FastEmbedEncoder


class DeterministicEncoder:
    model_metadata = {"provider": "test", "model_id": "deterministic", "dimension": 2}

    def encode(self, texts):
        return [[1.0, 0.0] if "correct" in text else [0.0, 1.0] for text in texts]


def test_rank_dense_uses_injected_encoder_and_returns_normalized_descending_scores():
    ranked = rank_dense("correct query", [{"record_id": "wrong", "surface_text": "wrong"}, {"record_id": "right", "surface_text": "correct"}], DeterministicEncoder())

    assert [item["record_id"] for item in ranked] == ["right", "wrong"]
    assert ranked[0]["score"] == 1.0


def test_fastembed_encoder_declares_upstream_and_executed_backend_without_loading_in_unit_tests():
    assert FastEmbedEncoder.default_metadata() == {
        "provider": "fastembed",
        "model_id": "qdrant/bge-small-en-v1.5-onnx-q",
        "revision": "52398278842ec682c6f32300af41344b1c0b0bb2",
        "upstream_model_id": "BAAI/bge-small-en-v1.5",
        "upstream_revision": "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a",
        "dimensions": 384,
    }


def test_rank_dense_uses_query_and_document_paths_and_caches_repeated_texts():
    class SplitEncoder:
        model_metadata = {"model_id": "split"}
        def __init__(self): self.calls = []
        def encode(self, texts): raise AssertionError("generic path must not be used")
        def encode_query(self, texts): self.calls.append(("query", list(texts))); return [[1., 0.]]
        def encode_documents(self, texts): self.calls.append(("document", list(texts))); return [[1., 0.] for _ in texts]
    inner = SplitEncoder(); encoder = CachingEncoder(inner)
    rank_dense("q", [{"record_id": "r", "surface_text": "same"}], encoder)
    rank_dense("q", [{"record_id": "r", "surface_text": "same"}], encoder)
    assert inner.calls == [("query", ["q"]), ("document", ["same"])]
    assert encoder.model_metadata["cache_hits"] == 2


def test_rank_dense_normalizes_numpy_scores_for_json_artifacts():
    import numpy as np

    class NumpyEncoder:
        model_metadata = {"model_id": "numpy"}

        def encode_query(self, texts):
            return [np.asarray([1.0, 0.0], dtype=np.float32)]

        def encode_documents(self, texts):
            return [np.asarray([1.0, 0.0], dtype=np.float32) for _ in texts]

        def encode(self, texts):
            raise AssertionError("split paths should be used")

    ranked = rank_dense("q", [{"record_id": "r", "surface_text": "same"}], NumpyEncoder())

    assert isinstance(ranked[0]["score"], float)


def test_fastembed_records_load_latency_rss_and_existing_cache(monkeypatch, tmp_path):
    class FakeTextEmbedding:
        def __init__(self, *, model_name, cache_dir):
            self.model_name = model_name
            self.cache_dir = cache_dir

        def passage_embed(self, texts):
            return [[1.0] * 384 for _ in texts]

    (tmp_path / "cached-model").mkdir()
    monkeypatch.setitem(sys.modules, "fastembed", SimpleNamespace(TextEmbedding=FakeTextEmbedding))
    ticks = iter([10.0, 10.25])
    rss_values = iter([100.0, 128.5])
    monkeypatch.setattr(dense_module, "perf_counter", lambda: next(ticks))
    monkeypatch.setattr(dense_module, "_process_rss_mib", lambda: next(rss_values))

    encoder = FastEmbedEncoder(cache_dir=str(tmp_path))

    assert encoder.model_metadata["model_load_latency_ms"] == 250.0
    assert encoder.model_metadata["rss_before_load_mib"] == 100.0
    assert encoder.model_metadata["rss_after_load_mib"] == 128.5
    assert encoder.model_metadata["rss_load_delta_mib"] == 28.5
    assert encoder.model_metadata["cache_state_before_load"] == "warm"
