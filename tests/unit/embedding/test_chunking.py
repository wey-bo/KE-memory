from __future__ import annotations

from collections.abc import Sequence

import pytest

from ke_memory_demo.embedding import chunk_text


class _CharacterTokenizer:
    def encode(self, text: str, *, add_special_tokens: bool) -> list[int]:
        assert add_special_tokens is False
        return list(range(len(text)))

    def decode(
        self,
        token_ids: Sequence[int],
        *,
        skip_special_tokens: bool,
        clean_up_tokenization_spaces: bool,
    ) -> str:
        assert skip_special_tokens is False
        assert clean_up_tokenization_spaces is False
        return "x" * len(token_ids)


@pytest.fixture
def fake_tokenizer() -> _CharacterTokenizer:
    return _CharacterTokenizer()


def test_chunks_use_1024_tokens_and_128_overlap(
    fake_tokenizer: _CharacterTokenizer,
) -> None:
    chunks = chunk_text(
        "x" * 2300,
        fake_tokenizer,
        chunk_tokens=1024,
        overlap_tokens=128,
    )

    assert [chunk.token_start for chunk in chunks] == [0, 896, 1792]
    assert all(chunk.token_end - chunk.token_start <= 1024 for chunk in chunks)
