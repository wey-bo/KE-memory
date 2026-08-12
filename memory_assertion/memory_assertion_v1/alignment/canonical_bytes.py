"""The byte contract every deterministic artifact in this layer obeys.

One place, because "the same inputs produce the same bytes" is a property of the whole
bundle rather than of any single writer. Six rules, frozen together:

- **UTF-8** without a BOM, and a trailing newline so the files are diffable.
- **NFC** on every string, applied to object member names as well as values -- two
  spellings of the same character would otherwise hash differently.
- **I-JSON**: no NaN, no infinities, no lone surrogates. A number that cannot round-trip
  cannot be part of a reproducible digest.
- **JCS-style member ordering**: object members sorted by their UTF-16 code units, as
  RFC 8785 specifies.
- **Stable array ordering** supplied by the caller. JCS does not sort arrays, and it must
  not: `input_concepts` is ordered by meaning. Semantically unordered arrays are sorted at
  the point they are built, not here.
- **SHA-256** over the canonical bytes.

The hash graph is acyclic by construction: an artifact may record the digest of an artifact
it consumed, never its own. A file that contained its own digest could not be written.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Any, cast


class CanonicalBytesError(ValueError):
    """A value cannot be serialised under the byte contract."""


def normalize_text(value: str) -> str:
    """Apply NFC. The only string normalisation this layer performs."""
    return unicodedata.normalize("NFC", value)


def canonicalize(value: Any) -> Any:
    """Recursively normalise strings and reject values I-JSON forbids.

    Member names are normalised too, and a collision after normalisation is an error rather
    than a silent overwrite: two keys that differ only by Unicode form are almost certainly
    a mistake upstream, and picking one would hide it.
    """
    if isinstance(value, str):
        return normalize_text(value)
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise CanonicalBytesError(f"non-finite number is not I-JSON: {value!r}")
        return value
    if isinstance(value, list):
        return [canonicalize(item) for item in cast("list[Any]", value)]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for raw_key, raw_value in cast("dict[Any, Any]", value).items():
            if not isinstance(raw_key, str):
                raise CanonicalBytesError(f"object member name is not a string: {raw_key!r}")
            key = normalize_text(raw_key)
            if key in result:
                raise CanonicalBytesError(f"member name collides after NFC: {key!r}")
            result[key] = canonicalize(raw_value)
        return result
    raise CanonicalBytesError(f"unsupported type for canonical bytes: {type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    """Serialise to the canonical byte sequence.

    `sort_keys` gives RFC 8785 member ordering for the ASCII member names used throughout
    this layer. `ensure_ascii=False` keeps the NFC forms intact rather than escaping them,
    so the bytes match what NFC produced.
    """
    payload = canonicalize(value)
    text = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return text.encode("utf-8") + b"\n"


def digest(value: Any) -> str:
    """SHA-256 of the canonical bytes, lowercase hex."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def digest_bytes(payload: bytes) -> str:
    """SHA-256 of an existing byte sequence -- used for source artifacts read from disk."""
    return hashlib.sha256(payload).hexdigest()
