from __future__ import annotations

from typing import Protocol

import tiktoken


O200K_BASE = "o200k_base"


class TokenCounter(Protocol):
    def count(self, text: str) -> int: ...


class O200KTokenCounter:
    def __init__(self) -> None:
        self._encoding = tiktoken.get_encoding(O200K_BASE)

    @property
    def encoding_name(self) -> str:
        return self._encoding.name

    def count(self, text: str) -> int:
        return len(self._encoding.encode(text, disallowed_special=()))
