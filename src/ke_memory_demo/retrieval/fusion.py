from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
import hashlib
from typing import Annotated, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ke_memory_demo.core.ids import content_id
from ke_memory_demo.core.json import JsonObject, JsonValue, canonical_json
from ke_memory_demo.domain import Evidence, MessageSpan, TemporalMetadata

from .matcher import KEMatchDecision, MatchRelation
from .evidence_payload import serialize_evidence_payload
from .symbolic import SourceFragment, SymbolicCandidate
from .tokens import TokenCounter


MAX_EVIDENCE_TOKENS = 8192
MAX_MANDATORY_SEARCH_STATES = 100_000
NonEmptyString = Annotated[str, Field(min_length=1)]
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


class FusionInvariantError(ValueError):
    """Evidence candidates cannot be normalized deterministically."""


class EvidenceBudgetError(FusionInvariantError):
    """Required evidence cannot fit within the configured hard budget."""


class EvidenceCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: NonEmptyString
    text: str
    score: FiniteFloat
    channel: NonEmptyString
    source_exchange_ids: tuple[NonEmptyString, ...] = ()
    source_message_ids: tuple[NonEmptyString, ...] = ()
    source_session_ids: tuple[NonEmptyString, ...] = ()
    system_record_ids: tuple[NonEmptyString, ...] = ()
    message_span: MessageSpan | None = None
    derived: bool = False
    raw_closure: tuple[SourceFragment, ...] = ()
    metadata: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_provenance(self) -> EvidenceCandidate:
        for label, values in (
            ("source exchange IDs", self.source_exchange_ids),
            ("source message IDs", self.source_message_ids),
            ("source session IDs", self.source_session_ids),
            ("system record IDs", self.system_record_ids),
        ):
            if values != tuple(sorted(set(values))):
                raise ValueError(f"{label} must be sorted and duplicate-free")
        if self.message_span is not None:
            if (
                self.source_message_ids
                and self.message_span.message_id not in self.source_message_ids
            ):
                raise ValueError("message span must agree with source message IDs")
            if len(self.text) != self.message_span.end_char - self.message_span.start_char:
                raise ValueError("evidence text length does not match its message span")
            expected = hashlib.sha256(self.text.encode("utf-8")).hexdigest()
            if expected != self.message_span.text_hash:
                raise ValueError("evidence text hash does not match its message span")
        if self.derived and not self.raw_closure:
            raise ValueError("derived evidence requires a non-empty raw closure")
        if not self.derived and self.raw_closure:
            raise ValueError("raw closure is allowed only for derived evidence")
        return self


@dataclass(frozen=True)
class _MergedCandidate:
    key: tuple[str, ...]
    candidate_id: str
    text: str
    score: float
    channels: tuple[str, ...]
    channel_scores: tuple[tuple[str, float], ...]
    source_exchange_ids: tuple[str, ...]
    source_message_ids: tuple[str, ...]
    source_session_ids: tuple[str, ...]
    system_record_ids: tuple[str, ...]
    message_span: MessageSpan | None
    metadata: JsonObject
    token_count: int
    derived_record_id: str | None
    closure_for: tuple[str, ...]
    pure_closure: bool


class EvidenceFusion:
    def __init__(self, token_counter: TokenCounter, *, budget: int = MAX_EVIDENCE_TOKENS) -> None:
        self._token_counter = token_counter
        self._budget = _validated_budget(budget)

    def fuse(
        self,
        *,
        symbolic_candidates: Sequence[SymbolicCandidate],
        matches: Sequence[KEMatchDecision],
        embedding_candidates: Sequence[EvidenceCandidate],
        budget: int | None = None,
    ) -> tuple[Evidence, ...]:
        symbolic = tuple(
            SymbolicCandidate.model_validate(item.model_dump(mode="python"))
            for item in symbolic_candidates
        )
        decisions = tuple(
            KEMatchDecision.model_validate(item.model_dump(mode="python")) for item in matches
        )
        offered_ids = {item.candidate_id for item in symbolic}
        returned_ids = {item.candidate_id for item in decisions}
        if len(returned_ids) != len(decisions):
            raise FusionInvariantError("fusion received duplicate matcher candidate IDs")
        if returned_ids != offered_ids:
            raise FusionInvariantError("fusion matcher decisions do not match symbolic candidates")
        by_id = {item.candidate_id: item for item in decisions}
        fused_candidates = [
            EvidenceCandidate.model_validate(item.model_dump(mode="python"))
            for item in embedding_candidates
        ]
        for candidate in symbolic:
            decision = by_id[candidate.candidate_id]
            if decision.match_type is MatchRelation.NO_MATCH:
                continue
            fused_candidates.append(_symbolic_evidence(candidate, decision))
        return self.pack(fused_candidates, budget=budget)

    def pack(
        self,
        candidates: Sequence[EvidenceCandidate],
        *,
        budget: int | None = None,
    ) -> tuple[Evidence, ...]:
        actual_budget = self._budget if budget is None else _validated_budget(budget)
        expanded = tuple(
            item
            for candidate in candidates
            for item in _expand_candidate(
                EvidenceCandidate.model_validate(candidate.model_dump(mode="python"))
            )
        )
        merged = _merge_candidates(expanded, self._validated_token_count)
        selected = _select_candidates(merged, actual_budget, self._serialized_token_count)
        evidence = _ranked_evidence(selected)
        if self._serialized_token_count(selected) > actual_budget:
            raise EvidenceBudgetError("serialized evidence collection exceeds the budget")
        return evidence

    def _validated_token_count(self, text: str) -> int:
        count = self._token_counter.count(text)
        if isinstance(count, bool) or count < 0:
            raise FusionInvariantError("token counter returned an invalid count")
        return count

    def _serialized_token_count(self, candidates: Sequence[_MergedCandidate]) -> int:
        return self._validated_token_count(serialize_evidence_payload(_ranked_evidence(candidates)))


def _symbolic_evidence(
    candidate: SymbolicCandidate,
    decision: KEMatchDecision,
) -> EvidenceCandidate:
    fragments = candidate.source_fragments
    if not fragments:
        raise FusionInvariantError(
            f"matched derived record has no raw evidence closure: {candidate.candidate_id}"
        )
    source_exchange_ids = tuple(sorted({item.source_exchange_id for item in fragments}))
    source_message_ids = tuple(sorted({item.span.message_id for item in fragments}))
    source_session_ids = tuple(sorted({item.source_session_id for item in fragments}))
    metadata: JsonObject = {
        "record_kind": candidate.record_kind,
        "match_type": decision.match_type.value,
        "match_reason": decision.reason,
        "matched_fields": list(candidate.matched_fields),
    }
    if candidate.knowledge_equation is not None:
        text = candidate.knowledge_equation.gloss
        metadata["lifecycle"] = candidate.knowledge_equation.lifecycle.value
        metadata["knowledge_level"] = candidate.knowledge_equation.level.value
        _add_temporal_metadata(metadata, candidate.knowledge_equation.temporal)
    elif candidate.aggregate is not None:
        text = candidate.aggregate.summary
        metadata["aggregate_depth"] = candidate.aggregate.depth
        metadata["aggregate_kind"] = candidate.aggregate.node_kind.value
        _add_temporal_metadata(metadata, candidate.aggregate.temporal_extent)
    else:
        raise FusionInvariantError("symbolic candidate has no record")
    if decision.match_type is MatchRelation.CONTRADICTS:
        metadata["conflict_side"] = candidate.candidate_id
    return EvidenceCandidate(
        candidate_id=candidate.candidate_id,
        text=text,
        score=decision.confidence,
        channel="symbolic",
        source_exchange_ids=source_exchange_ids,
        source_message_ids=source_message_ids,
        source_session_ids=source_session_ids,
        system_record_ids=(candidate.candidate_id,),
        derived=True,
        raw_closure=fragments,
        metadata=metadata,
    )


def _expand_candidate(candidate: EvidenceCandidate) -> tuple[EvidenceCandidate, ...]:
    if not candidate.derived:
        return (candidate,)
    summary_metadata = dict(candidate.metadata)
    summary_metadata["derived_record_id"] = candidate.candidate_id
    summary = candidate.model_copy(update={"metadata": summary_metadata})
    closure: list[EvidenceCandidate] = []
    for fragment in candidate.raw_closure:
        metadata: JsonObject = {
            "closure_for": candidate.candidate_id,
            "raw_source": True,
        }
        embedding_document_id = candidate.metadata.get("embedding_document_id")
        if isinstance(embedding_document_id, str) and embedding_document_id:
            metadata["embedding_document_id"] = embedding_document_id
        closure.append(
            EvidenceCandidate(
                candidate_id=f"{candidate.candidate_id}:raw:{fragment.fragment_id}",
                text=fragment.text,
                score=candidate.score,
                channel=candidate.channel,
                source_exchange_ids=(fragment.source_exchange_id,),
                source_message_ids=(fragment.span.message_id,),
                source_session_ids=(fragment.source_session_id,),
                system_record_ids=candidate.system_record_ids,
                message_span=fragment.span,
                metadata=metadata,
            )
        )
    return (summary, *closure)


def _add_temporal_metadata(
    metadata: JsonObject,
    temporal: TemporalMetadata,
) -> None:
    values = temporal.model_dump(mode="json", exclude_none=True)
    if not values:
        return
    metadata["temporal"] = cast(JsonObject, values)
    for field in ("event_time", "valid_from", "mentioned_at", "valid_to"):
        value = values.get(field)
        if isinstance(value, str):
            metadata["time_point"] = value
            return


def _merge_candidates(
    candidates: Sequence[EvidenceCandidate],
    count_tokens: Callable[[str], int],
) -> tuple[_MergedCandidate, ...]:
    groups: dict[tuple[str, ...], list[EvidenceCandidate]] = defaultdict(list)
    for candidate in candidates:
        groups[_dedup_key(candidate)].append(candidate)
    merged: list[_MergedCandidate] = []
    for key in sorted(groups):
        group = groups[key]
        texts = {item.text for item in group}
        if len(texts) != 1:
            raise FusionInvariantError("deduplicated evidence candidates disagree on source text")
        representative = min(
            group,
            key=lambda item: (-item.score, item.candidate_id, item.channel),
        )
        channels = tuple(sorted({item.channel for item in group}))
        channel_scores = tuple(
            (channel, max(item.score for item in group if item.channel == channel))
            for channel in channels
        )
        metadata = _merged_metadata(group)
        metadata["channels"] = list(channels)
        metadata["channel_scores"] = dict(channel_scores)
        source_session_ids = _union(item.source_session_ids for item in group)
        if source_session_ids:
            metadata["source_session_ids"] = list(source_session_ids)
        token_count = count_tokens(representative.text)
        closure_for = _metadata_strings(group, "closure_for")
        derived_ids = _metadata_strings(group, "derived_record_id")
        merged.append(
            _MergedCandidate(
                key=key,
                candidate_id=min(item.candidate_id for item in group),
                text=representative.text,
                score=max(item.score for item in group),
                channels=channels,
                channel_scores=channel_scores,
                source_exchange_ids=_union(item.source_exchange_ids for item in group),
                source_message_ids=_union(item.source_message_ids for item in group),
                source_session_ids=source_session_ids,
                system_record_ids=_union(item.system_record_ids for item in group),
                message_span=representative.message_span,
                metadata=metadata,
                token_count=token_count,
                derived_record_id=derived_ids[0] if derived_ids else None,
                closure_for=closure_for,
                pure_closure=all("closure_for" in item.metadata for item in group),
            )
        )
    return tuple(merged)


def _select_candidates(
    candidates: Sequence[_MergedCandidate],
    budget: int,
    selection_token_count: Callable[[Sequence[_MergedCandidate]], int],
) -> tuple[_MergedCandidate, ...]:
    by_derived: dict[str, tuple[_MergedCandidate, ...]] = {}
    for item in candidates:
        if item.derived_record_id is not None:
            by_derived[item.derived_record_id] = tuple(
                closure for closure in candidates if item.derived_record_id in closure.closure_for
            )

    def bundle(item: _MergedCandidate) -> tuple[_MergedCandidate, ...]:
        dependencies = (
            by_derived.get(item.derived_record_id, ()) if item.derived_record_id is not None else ()
        )
        values = {candidate.key: candidate for candidate in (item, *dependencies)}
        return tuple(values[key] for key in sorted(values))

    selectable = tuple(item for item in candidates if not item.pure_closure)
    required: set[str] = set()
    for item in selectable:
        required.update(_requirements(item))
    selected = _mandatory_selection(
        selectable,
        required,
        bundle=bundle,
        budget=budget,
        selection_token_count=selection_token_count,
    )

    def add(item: _MergedCandidate) -> bool:
        additions = tuple(value for value in bundle(item) if value.key not in selected)
        proposed = (*selected.values(), *additions)
        if selection_token_count(proposed) > budget:
            return False
        for value in additions:
            selected[value.key] = value
        return True

    for item in sorted(selectable, key=lambda value: (-value.score, value.candidate_id, value.key)):
        if item.key in selected:
            continue
        add(item)
    return tuple(selected[key] for key in sorted(selected))


def _mandatory_selection(
    selectable: Sequence[_MergedCandidate],
    required: set[str],
    *,
    bundle: Callable[[_MergedCandidate], tuple[_MergedCandidate, ...]],
    budget: int,
    selection_token_count: Callable[[Sequence[_MergedCandidate]], int],
) -> dict[tuple[str, ...], _MergedCandidate]:
    options = tuple(
        sorted(
            selectable,
            key=lambda item: (-item.score, item.candidate_id, item.key),
        )
    )
    requirements_by_option = {item.key: _bundle_requirements(bundle(item)) for item in options}
    states = 0

    def search(
        selected: dict[tuple[str, ...], _MergedCandidate],
        remaining: frozenset[str],
    ) -> dict[tuple[str, ...], _MergedCandidate] | None:
        nonlocal states
        states += 1
        if states > MAX_MANDATORY_SEARCH_STATES:
            raise FusionInvariantError(
                "mandatory evidence search limit exhausted before feasibility was decided"
            )
        if not remaining:
            return selected

        covering = {
            requirement: tuple(
                item
                for item in options
                if item.key not in selected and requirement in requirements_by_option[item.key]
            )
            for requirement in remaining
        }
        if any(not candidates for candidates in covering.values()):
            return None
        requirement = min(
            remaining,
            key=lambda value: (len(covering[value]), value),
        )
        branches: list[
            tuple[
                int,
                int,
                float,
                str,
                _MergedCandidate,
                dict[tuple[str, ...], _MergedCandidate],
                frozenset[str],
            ]
        ] = []
        for item in covering[requirement]:
            proposed = dict(selected)
            for value in bundle(item):
                proposed[value.key] = value
            cost = selection_token_count(tuple(proposed.values()))
            if cost > budget:
                continue
            covered = requirements_by_option[item.key].intersection(remaining)
            branches.append(
                (
                    -len(covered),
                    cost,
                    -item.score,
                    item.candidate_id,
                    item,
                    proposed,
                    remaining.difference(covered),
                )
            )
        for *_priority, proposed, next_remaining in sorted(
            branches,
            key=lambda branch: branch[:4],
        ):
            result = search(proposed, next_remaining)
            if result is not None:
                return result
        return None

    result = search({}, frozenset(required))
    if result is None:
        raise EvidenceBudgetError(
            "required conflict, temporal, or session evidence does not fit within the budget"
        )
    return result


def _ranked_evidence(candidates: Sequence[_MergedCandidate]) -> tuple[Evidence, ...]:
    ranked = sorted(candidates, key=lambda item: (-item.score, item.candidate_id, item.key))
    return tuple(_to_evidence(item, rank) for rank, item in enumerate(ranked, start=1))


def _requirements(item: _MergedCandidate) -> set[str]:
    requirements = {f"session:{value}" for value in item.source_session_ids}
    for field in ("conflict_side", "time_point"):
        value = item.metadata.get(field)
        if isinstance(value, str) and value:
            requirements.add(f"{field}:{value}")
        variants = item.metadata.get(f"{field}_values")
        if isinstance(variants, list):
            requirements.update(
                f"{field}:{variant}" for variant in variants if isinstance(variant, str)
            )
    return requirements


def _bundle_requirements(bundle: Sequence[_MergedCandidate]) -> set[str]:
    result: set[str] = set()
    for item in bundle:
        result.update(_requirements(item))
    return result


def _dedup_key(candidate: EvidenceCandidate) -> tuple[str, ...]:
    span = candidate.message_span
    if span is not None:
        return (
            "span",
            span.message_id,
            str(span.start_char),
            str(span.end_char),
            span.text_hash,
        )
    return ("candidate", candidate.candidate_id)


def _merged_metadata(group: Sequence[EvidenceCandidate]) -> JsonObject:
    result: JsonObject = {}
    keys = sorted({key for item in group for key in item.metadata})
    for key in keys:
        by_json: dict[bytes, JsonValue] = {}
        for item in group:
            if key not in item.metadata:
                continue
            value = item.metadata[key]
            by_json[canonical_json(value)] = value
        ordered = [by_json[item] for item in sorted(by_json)]
        if len(ordered) == 1:
            result[key] = ordered[0]
        elif ordered:
            result[key] = ordered[0]
            result[f"{key}_values"] = ordered
    return result


def _metadata_strings(
    group: Sequence[EvidenceCandidate],
    key: str,
) -> tuple[str, ...]:
    values: set[str] = set()
    for item in group:
        value = item.metadata.get(key)
        if isinstance(value, str):
            values.add(value)
    return tuple(sorted(values))


def _union(groups: Iterable[Sequence[str]]) -> tuple[str, ...]:
    return tuple(sorted({value for group in groups for value in group}))


def _to_evidence(item: _MergedCandidate, rank: int) -> Evidence:
    payload: JsonObject = {
        "dedup_key": list(item.key),
        "text": item.text,
        "source_exchange_ids": list(item.source_exchange_ids),
        "source_message_ids": list(item.source_message_ids),
        "system_record_ids": list(item.system_record_ids),
        "channels": list(item.channels),
    }
    return Evidence(
        evidence_id=content_id("evidence", cast(JsonValue, payload)),
        text=item.text,
        source_exchange_ids=item.source_exchange_ids,
        source_message_ids=item.source_message_ids,
        system_record_ids=item.system_record_ids,
        score=item.score,
        rank=rank,
        channel="|".join(item.channels),
        metadata=item.metadata,
        token_count=item.token_count,
    )


def _validated_budget(budget: int) -> int:
    if isinstance(budget, bool) or budget <= 0 or budget > MAX_EVIDENCE_TOKENS:
        raise FusionInvariantError(
            f"evidence budget must be between 1 and {MAX_EVIDENCE_TOKENS} tokens"
        )
    return budget
