"""Exact source-span resolution for extraction evidence."""

from __future__ import annotations

import hashlib
import json

from knowledge_pipeline.models import Evidence, SourceStatus


def resolve_evidence(
    candidate_id: str,
    turn_index: int,
    text: str,
    message: str,
    quote: str,
    occurrence_index: int,
    evidence_role: SourceStatus,
) -> Evidence:
    """Resolve a 0-based exact quote occurrence to Unicode code-point offsets."""
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        raise ValueError("candidate_id must be non-empty")
    if not isinstance(turn_index, int) or isinstance(turn_index, bool) or turn_index < 0:
        raise ValueError("turn_index must be a non-negative integer")
    if message not in {"user", "agent"}:
        raise ValueError("message must be user or agent")
    if evidence_role not in {"user_reported", "agent_generated", "tool_observed"}:
        raise ValueError("evidence_role is invalid")
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    if not isinstance(quote, str) or not quote:
        raise ValueError("quote must be non-empty")
    if not isinstance(occurrence_index, int) or isinstance(occurrence_index, bool) or occurrence_index < 0:
        raise ValueError("occurrence_index must be a non-negative integer")

    starts: list[int] = []
    start = text.find(quote)
    while start != -1:
        starts.append(start)
        start = text.find(quote, start + 1)
    if occurrence_index >= len(starts):
        raise ValueError("quote occurrence is missing or out of range")
    start = starts[occurrence_index]
    scope = json.dumps(
        {
            "candidate_id": candidate_id,
            "turn_index": turn_index,
            "message": message,
            "quote": quote,
            "occurrence_index": occurrence_index,
            "evidence_role": evidence_role,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(scope.encode("utf-8")).hexdigest()
    return Evidence(
        evidence_id=f"evidence-{digest}",
        candidate_id=candidate_id,
        turn_index=turn_index,
        message=message,
        occurrence_index=occurrence_index,
        quote=quote,
        evidence_role=evidence_role,
        start=start,
        end=start + len(quote),
    )
