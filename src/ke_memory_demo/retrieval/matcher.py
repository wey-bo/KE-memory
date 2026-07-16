from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import Enum
import hashlib
from pathlib import Path
from typing import Annotated, Protocol, TypeVar, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ke_memory_demo.core.json import JsonObject, JsonValue, canonical_json
from ke_memory_demo.infra.telemetry import TraceContext

from .query import QueryKE, RetrievalInvariantError
from .symbolic import SymbolicCandidate


_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts/ke_match/system.md"
NonEmptyString = Annotated[str, Field(min_length=1)]
Confidence = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
ModelT = TypeVar("ModelT", bound=BaseModel)


class MatcherInvariantError(RetrievalInvariantError):
    """The KE matcher returned incomplete or unoffered decisions."""


class MatchRelation(str, Enum):
    EXACT = "exact"
    EQUIVALENT = "equivalent"
    SUBSUMES = "subsumes"
    RELATED = "related"
    CONTRADICTS = "contradicts"
    UPDATES = "updates"
    TEMPORAL_PRECEDES = "temporal_precedes"
    TEMPORAL_FOLLOWS = "temporal_follows"
    NO_MATCH = "no_match"


class _MatcherRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class KEMatchDecision(_MatcherRecord):
    candidate_id: NonEmptyString
    match_type: MatchRelation
    confidence: Confidence
    reason: NonEmptyString


class KEMatchOutput(_MatcherRecord):
    matches: tuple[KEMatchDecision, ...] = ()

    @model_validator(mode="after")
    def _validate_candidates(self) -> KEMatchOutput:
        candidate_ids = tuple(item.candidate_id for item in self.matches)
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("duplicate KE matcher candidate IDs are not allowed")
        return self


class StructuredMatcherClient(Protocol):
    async def complete(
        self,
        model_type: type[ModelT],
        messages: Sequence[Mapping[str, object]],
        trace_context: TraceContext | Mapping[str, object],
    ) -> ModelT: ...


class LLMMatcher:
    def __init__(self, model: StructuredMatcherClient, *, run_id: str) -> None:
        if not run_id:
            raise MatcherInvariantError("run_id must not be empty")
        self._model = model
        self._run_id = run_id
        self._prompt = _read_prompt()
        self.prompt_sha256 = hashlib.sha256(self._prompt.encode("utf-8")).hexdigest()

    async def match(
        self,
        *,
        query_ke: QueryKE,
        symbolic_candidates: Sequence[SymbolicCandidate],
    ) -> tuple[KEMatchDecision, ...]:
        query = QueryKE.model_validate(query_ke.model_dump(mode="python"))
        candidates = tuple(
            SymbolicCandidate.model_validate(item.model_dump(mode="python"))
            for item in symbolic_candidates
        )
        offered_ids = tuple(item.candidate_id for item in candidates)
        if len(offered_ids) != len(set(offered_ids)):
            raise MatcherInvariantError("duplicate offered symbolic candidate IDs")
        if not candidates:
            return ()
        payload: JsonObject = {
            "task": "match_query_ke_candidates",
            "query_ke": cast(JsonValue, query.model_dump(mode="json")),
            "symbolic_candidates": [
                cast(JsonValue, item.model_dump(mode="json")) for item in candidates
            ],
        }
        response = await self._model.complete(
            KEMatchOutput,
            (
                {"role": "system", "content": self._prompt},
                {"role": "user", "content": canonical_json(payload).decode("utf-8")},
            ),
            TraceContext(
                operation="ke-match",
                metadata={
                    "run_id": self._run_id,
                    "candidate_count": len(candidates),
                    "prompt_sha256": self.prompt_sha256,
                },
            ),
        )
        output = _revalidate_output(response)
        returned = {item.candidate_id for item in output.matches}
        offered = set(offered_ids)
        unoffered = sorted(returned.difference(offered))
        if unoffered:
            raise MatcherInvariantError(
                f"KE matcher returned unoffered candidate: {unoffered[0]}"
            )
        missing = sorted(offered.difference(returned))
        if missing:
            raise MatcherInvariantError(f"KE matcher is missing candidate: {missing[0]}")
        by_id = {item.candidate_id: item for item in output.matches}
        return tuple(by_id[candidate_id] for candidate_id in sorted(offered))


def _read_prompt() -> str:
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8")
    except OSError as error:
        raise MatcherInvariantError("required KE matcher prompt is unavailable") from error


def _revalidate_output(value: object) -> KEMatchOutput:
    if not isinstance(value, BaseModel):
        raise MatcherInvariantError("KE matcher did not return a validated record")
    try:
        return KEMatchOutput.model_validate(value.model_dump(mode="python"))
    except ValidationError as error:
        raise MatcherInvariantError("KE matcher output failed local schema validation") from error
