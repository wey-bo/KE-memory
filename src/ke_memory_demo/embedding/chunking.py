from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


NonNegativeInt = Annotated[int, Field(ge=0)]


class Tokenizer(Protocol):
    def encode(self, text: str, *, add_special_tokens: bool) -> Sequence[int]: ...

    def decode(
        self,
        token_ids: Sequence[int],
        *,
        skip_special_tokens: bool,
        clean_up_tokenization_spaces: bool,
    ) -> str: ...


class TextChunk(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    token_start: NonNegativeInt
    token_end: NonNegativeInt

    @model_validator(mode="after")
    def _validate_range(self) -> TextChunk:
        if self.token_end <= self.token_start:
            raise ValueError("chunk token range must be non-empty")
        return self


def chunk_text(
    text: str,
    tokenizer: Tokenizer,
    *,
    chunk_tokens: int,
    overlap_tokens: int,
) -> tuple[TextChunk, ...]:
    if isinstance(chunk_tokens, bool) or chunk_tokens <= 0:
        raise ValueError("chunk_tokens must be a positive integer")
    if isinstance(overlap_tokens, bool) or overlap_tokens < 0:
        raise ValueError("overlap_tokens must be a non-negative integer")
    if overlap_tokens >= chunk_tokens:
        raise ValueError("overlap_tokens must be smaller than chunk_tokens")

    token_ids = tuple(tokenizer.encode(text, add_special_tokens=False))
    if not token_ids:
        return ()

    step = chunk_tokens - overlap_tokens
    chunks: list[TextChunk] = []
    for start in range(0, len(token_ids), step):
        end = min(start + chunk_tokens, len(token_ids))
        window = token_ids[start:end]
        chunks.append(
            TextChunk(
                text=tokenizer.decode(
                    window,
                    skip_special_tokens=False,
                    clean_up_tokenization_spaces=False,
                ),
                token_start=start,
                token_end=end,
            )
        )
        if end == len(token_ids):
            break
    return tuple(chunks)
