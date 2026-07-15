from __future__ import annotations

import hashlib

from pydantic import BaseModel

from .json import JsonValue, canonical_json


def content_id(prefix: str, value: BaseModel | JsonValue) -> str:
    """Return a namespaced SHA-256 content identifier."""
    if not prefix:
        raise ValueError("content ID prefix must not be empty")
    digest = hashlib.sha256(canonical_json(value)).hexdigest()
    return f"{prefix}:{digest}"
