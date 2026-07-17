from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from ke_memory_demo.core.json import JsonObject, JsonValue, canonical_json
from ke_memory_demo.domain import Evidence


def model_evidence_payload(evidence: Sequence[Evidence]) -> tuple[JsonObject, ...]:
    """Return the canonical records exposed to the answer model."""
    ordered = sorted(evidence, key=lambda item: (item.rank, item.evidence_id))
    return tuple(
        cast(
            JsonObject,
            item.model_dump(mode="json", exclude={"token_count"}),
        )
        for item in ordered
    )


def serialize_evidence_payload(evidence: Sequence[Evidence]) -> str:
    payload = cast(JsonValue, list(model_evidence_payload(evidence)))
    return canonical_json(payload).decode("utf-8")
