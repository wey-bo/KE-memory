from __future__ import annotations

import json
import math
from typing import cast

from pydantic import BaseModel


type JsonScalar = None | bool | int | float | str
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]


def canonical_json(value: BaseModel | JsonValue) -> bytes:
    """Serialize a model or JSON value to deterministic UTF-8 JSON bytes."""
    normalized = _normalize_json(value)
    return json.dumps(
        normalized,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _normalize_json(value: object) -> JsonValue:
    if isinstance(value, BaseModel):
        return _normalize_json(value.model_dump(mode="json"))
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical JSON does not support NaN or infinity")
        return value
    if isinstance(value, list | tuple):
        sequence = cast(list[object] | tuple[object, ...], value)
        return [_normalize_json(item) for item in sequence]
    if isinstance(value, dict):
        mapping = cast(dict[object, object], value)
        normalized: JsonObject = {}
        for key, item in mapping.items():
            if not isinstance(key, str):
                raise TypeError("canonical JSON object keys must be strings")
            normalized[key] = _normalize_json(item)
        return normalized
    raise TypeError(f"unsupported canonical JSON value: {type(value).__name__}")
