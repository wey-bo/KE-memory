from __future__ import annotations

import os
from pathlib import Path
import socket
from typing import cast

import numpy as np
import pytest

from ke_memory_demo.embedding import QwenEmbeddingBackend
from ke_memory_demo.settings import load_settings


pytestmark = pytest.mark.live_embedding


def test_local_qwen_embedding_is_finite_and_fingerprint_is_stable(
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not os.environ.get("KE_MEMORY_EMBEDDING_PATH", "").strip():
        pytest.skip("KE_MEMORY_EMBEDDING_PATH is not set")

    def deny_network(_socket: socket.socket, address: object) -> None:
        raise AssertionError(f"embedding test attempted network access: {address!r}")

    monkeypatch.setattr(socket.socket, "connect", deny_network)
    settings = load_settings(project_root)
    backend = QwenEmbeddingBackend(settings)
    fingerprint = backend.fingerprint

    vector = backend.embed_documents(["A local embedding smoke test."])[0]

    assert vector.shape == (1024,)
    assert vector.dtype == np.float32
    assert np.isfinite(vector).all()
    np.testing.assert_allclose(cast(float, np.linalg.norm(vector)), 1.0, atol=1e-5)
    backend.verify_model_fingerprint()
    assert backend.fingerprint == fingerprint
