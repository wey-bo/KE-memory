from __future__ import annotations

from pathlib import Path
import tomllib
from typing import cast

from pydantic import TypeAdapter, ValidationError

from ke_memory_demo.core.json import JsonObject

from .models import BaselinePublicResult


class BaselineResultError(ValueError):
    """The frozen public-result appendix is missing or violates its strict schema."""


_RESULTS = TypeAdapter(tuple[BaselinePublicResult, ...])


def load_public_baseline_results(path: Path) -> tuple[BaselinePublicResult, ...]:
    try:
        with path.open("rb") as stream:
            payload = cast(JsonObject, tomllib.load(stream))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise BaselineResultError(f"unable to load public baseline appendix: {path}") from error
    raw_results = payload.get("results")
    try:
        records = _RESULTS.validate_python(raw_results)
    except ValidationError as error:
        raise BaselineResultError("public baseline appendix failed schema validation") from error
    if not records:
        raise BaselineResultError("public baseline appendix must not be empty")
    return tuple(sorted(records, key=_sort_key))


def _sort_key(item: BaselinePublicResult) -> tuple[str, str, str, str, float]:
    score = item.score if item.score is not None else float("-inf")
    return item.system, item.dataset, item.split, item.metric, score
