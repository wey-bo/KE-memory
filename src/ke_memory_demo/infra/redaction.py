from __future__ import annotations

from collections.abc import Iterable, Mapping
import json
import re
from typing import TypeVar, cast


REDACTED = "[REDACTED]"

_T = TypeVar("_T")
_SEPARATOR = re.compile(r"[^a-zA-Z0-9]+")
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")
_SIMPLE_JSON_ESCAPES = {
    '"': '"',
    "\\": "\\",
    "/": "/",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
}
_USAGE_TOKEN_KEYS = {
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "completion_tokens",
    "prompt_tokens",
    "cached_tokens",
    "reasoning_tokens",
    "max_tokens",
    "max_output_tokens",
    "max_completion_tokens",
}


def redact_tree(value: _T, *, known_secrets: Iterable[str] = ()) -> _T:
    """Return a recursively redacted copy of a JSON-like value."""
    secrets = _normalized_secrets(known_secrets)
    return cast(_T, _redact_value(value, secrets))


def redact_text(value: str, *, known_secrets: Iterable[str] = ()) -> str:
    """Replace every known secret occurrence without changing the input string."""
    return _redact_string(value, _normalized_secrets(known_secrets))


def _redact_value(value: object, secrets: tuple[str, ...]) -> object:
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        result: dict[object, object] = {}
        for key, item in mapping.items():
            redacted_key = _redact_string(key, secrets) if isinstance(key, str) else key
            result[redacted_key] = (
                REDACTED
                if isinstance(key, str) and _is_sensitive_key(key)
                else _redact_value(item, secrets)
            )
        return result
    if isinstance(value, list):
        items = cast(list[object], value)
        return [_redact_value(item, secrets) for item in items]
    if isinstance(value, tuple):
        items = cast(tuple[object, ...], value)
        return tuple(_redact_value(item, secrets) for item in items)
    if isinstance(value, str):
        return _redact_string(value, secrets)
    return value


def _normalized_secrets(known_secrets: Iterable[str]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {secret for secret in known_secrets if secret and secret.strip()},
            key=len,
            reverse=True,
        )
    )


def _redact_string(value: str, secrets: tuple[str, ...]) -> str:
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return _replace_secret_variants(value, secrets)

    redacted_decoded = _redact_value(decoded, secrets)
    if redacted_decoded == decoded:
        return _replace_secret_variants(value, secrets)
    return json.dumps(
        redacted_decoded,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _replace_secret_variants(value: str, secrets: tuple[str, ...]) -> str:
    logical, spans = _decode_json_escapes(value)
    candidates: list[tuple[int, int, int]] = []
    for index in range(len(logical)):
        for secret in secrets:
            if logical.startswith(secret, index):
                candidates.append((spans[index][0], spans[index + len(secret) - 1][1], len(secret)))
    for secret in secrets:
        search_from = 0
        while (start := value.find(secret, search_from)) >= 0:
            candidates.append((start, start + len(secret), len(secret)))
            search_from = start + 1

    replacements: list[tuple[int, int]] = []
    cursor = 0
    for start, end, _secret_length in sorted(
        candidates,
        key=lambda candidate: (candidate[0], -candidate[2], -(candidate[1] - candidate[0])),
    ):
        if start < cursor:
            continue
        replacements.append((start, end))
        cursor = end

    if not replacements:
        return value
    parts: list[str] = []
    cursor = 0
    for start, end in replacements:
        parts.extend((value[cursor:start], REDACTED))
        cursor = end
    parts.append(value[cursor:])
    return "".join(parts)


def _decode_json_escapes(value: str) -> tuple[str, tuple[tuple[int, int], ...]]:
    characters: list[str] = []
    spans: list[tuple[int, int]] = []
    index = 0
    while index < len(value):
        escape = _json_escape_at(value, index)
        if escape is None:
            characters.append(value[index])
            spans.append((index, index + 1))
            index += 1
            continue
        character, end = escape
        characters.append(character)
        spans.append((index, end))
        index = end
    return "".join(characters), tuple(spans)


def _json_escape_at(value: str, start: int) -> tuple[str, int] | None:
    if value[start] != "\\" or start + 1 >= len(value):
        return None
    marker = value[start + 1]
    simple = _SIMPLE_JSON_ESCAPES.get(marker)
    if simple is not None:
        return simple, start + 2
    if marker != "u":
        return None

    first = _unicode_code_unit(value, start)
    if first is None:
        return None
    first_value, first_end = first
    if 0xD800 <= first_value <= 0xDBFF:
        second = _unicode_code_unit(value, first_end)
        if second is None or not 0xDC00 <= second[0] <= 0xDFFF:
            return None
        codepoint = 0x10000 + ((first_value - 0xD800) << 10) + (second[0] - 0xDC00)
        return chr(codepoint), second[1]
    if 0xDC00 <= first_value <= 0xDFFF:
        return None
    return chr(first_value), first_end


def _unicode_code_unit(value: str, start: int) -> tuple[int, int] | None:
    end = start + 6
    if end > len(value) or value[start : start + 2] != "\\u":
        return None
    digits = value[start + 2 : end]
    if len(digits) != 4 or any(digit not in _HEX_DIGITS for digit in digits):
        return None
    return int(digits, 16), end


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    if lowered in _USAGE_TOKEN_KEYS:
        return False

    normalized = _SEPARATOR.sub("", lowered)
    if "authorization" in normalized or "apikey" in normalized or "cookie" in normalized:
        return True

    words = tuple(
        word.lower()
        for part in _SEPARATOR.split(key)
        for word in _CAMEL_BOUNDARY.sub(" ", part).split()
        if word
    )
    return "token" in words or "tokens" in words
