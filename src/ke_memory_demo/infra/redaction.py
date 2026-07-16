from __future__ import annotations

from collections.abc import Iterable, Mapping
import json
import re
from typing import TypeVar, cast


REDACTED = "[REDACTED]"

_T = TypeVar("_T")
_SEPARATOR = re.compile(r"[^a-zA-Z0-9]+")
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
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
    variants = {
        variant
        for secret in secrets
        for variant in (
            secret,
            json.dumps(secret, ensure_ascii=False)[1:-1],
            json.dumps(secret, ensure_ascii=True)[1:-1],
        )
        if variant
    }
    redacted = value
    for variant in sorted(variants, key=len, reverse=True):
        redacted = redacted.replace(variant, REDACTED)
    return redacted


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
