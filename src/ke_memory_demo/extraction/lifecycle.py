from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ValidationError

from ke_memory_demo.core.json import JsonObject, JsonValue, canonical_json
from ke_memory_demo.domain import (
    AssertionRef,
    Expression,
    KnowledgeEquation,
    Lifecycle,
    OperatorApplication,
    OperatorRef,
    TemporalMetadata,
)
from ke_memory_demo.infra.telemetry import TraceContext

from .schemas import (
    LifecycleMatchCandidate,
    LifecycleMatchDecision,
    LifecycleMatchOutput,
    LifecycleResult,
)
from .turn_ke import StructuredCompletionClient, normalize_surface


LIFECYCLE_STAGE = "lifecycle-maintained"
_PROMPT_ROOT = Path(__file__).resolve().parents[3] / "prompts"


class LifecycleInvariantError(ValueError):
    """Raised when lifecycle candidates or matcher output violate the contract."""


class LifecycleMaintainer:
    def __init__(self, model: StructuredCompletionClient, *, run_id: str) -> None:
        if not run_id:
            raise ValueError("run_id must not be empty")
        self._model = model
        self._run_id = run_id

    async def apply(
        self,
        existing: Sequence[KnowledgeEquation],
        new: Sequence[KnowledgeEquation],
    ) -> LifecycleResult:
        existing = tuple(existing)
        new = tuple(new)
        _reject_duplicate_new_records(new)

        current_existing: dict[str, KnowledgeEquation] = {}
        for equation in existing:
            current_existing[equation.id] = equation
        new_by_id = {equation.id: equation for equation in new}

        candidates = _generate_candidates(current_existing, new_by_id)
        decisions: tuple[LifecycleMatchDecision, ...] = ()
        if candidates:
            response = await self._model.complete(
                LifecycleMatchOutput,
                self._match_messages(candidates),
                TraceContext(
                    operation="turn-ke-lifecycle-match",
                    metadata={"run_id": self._run_id},
                ),
            )
            output = _validated_match_output(response)
            decisions = _validate_decisions(candidates, output)

        old_contradictions: dict[str, set[str]] = defaultdict(set)
        new_contradictions: dict[str, set[str]] = defaultdict(set)
        new_supersedes: dict[str, set[str]] = defaultdict(set)
        old_lifecycle: dict[str, Lifecycle] = {}
        for decision in decisions:
            if decision.decision == "contradicts":
                old_contradictions[decision.old_ke_id].add(decision.new_ke_id)
                new_contradictions[decision.new_ke_id].add(decision.old_ke_id)
            elif decision.decision == "updates":
                transition = (
                    Lifecycle.RETRACTED if decision.explicit_retraction else Lifecycle.SUPERSEDED
                )
                if old_lifecycle.get(decision.old_ke_id) is Lifecycle.RETRACTED:
                    transition = Lifecycle.RETRACTED
                old_lifecycle[decision.old_ke_id] = transition
                new_supersedes[decision.new_ke_id].add(decision.old_ke_id)

        appended_old: list[KnowledgeEquation] = []
        for old_id in sorted(set(old_contradictions).union(old_lifecycle)):
            old = current_existing[old_id]
            appended_old.append(
                _recreate(
                    old,
                    run_id=self._run_id,
                    lifecycle=old_lifecycle.get(old_id, old.lifecycle),
                    contradicts=tuple(
                        sorted(set(old.contradicts).union(old_contradictions[old_id]))
                    ),
                )
            )

        appended_new: list[KnowledgeEquation] = []
        for new_id in sorted(new_by_id):
            equation = new_by_id[new_id]
            contradictions = tuple(
                sorted(set(equation.contradicts).union(new_contradictions[new_id]))
            )
            supersedes = tuple(sorted(set(equation.supersedes).union(new_supersedes[new_id])))
            if contradictions != equation.contradicts or supersedes != equation.supersedes:
                equation = _recreate(
                    equation,
                    run_id=self._run_id,
                    lifecycle=equation.lifecycle,
                    contradicts=contradictions,
                    supersedes=supersedes,
                )
            appended_new.append(equation)

        appended = (*appended_old, *appended_new)
        current = dict(current_existing)
        current.update({equation.id: equation for equation in appended})
        return LifecycleResult(
            decisions=decisions,
            appended_revisions=appended,
            current_records=tuple(current[key] for key in sorted(current)),
        )

    def _match_messages(
        self,
        candidates: Mapping[tuple[str, str], LifecycleMatchCandidate],
    ) -> list[dict[str, object]]:
        payload: JsonObject = {
            "task": "match_knowledge_equation_lifecycle",
            "offered_pairs": [
                cast(JsonValue, candidates[key].model_dump(mode="json"))
                for key in sorted(candidates)
            ],
        }
        try:
            system_prompt = (_PROMPT_ROOT / "lifecycle_match/system.md").read_text(encoding="utf-8")
        except OSError as error:
            raise LifecycleInvariantError(
                "required lifecycle matcher prompt is unavailable"
            ) from error
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": canonical_json(payload).decode("utf-8")},
        ]


def _generate_candidates(
    existing: Mapping[str, KnowledgeEquation],
    new: Mapping[str, KnowledgeEquation],
) -> dict[tuple[str, str], LifecycleMatchCandidate]:
    candidates: dict[tuple[str, str], LifecycleMatchCandidate] = {}
    for old_id in sorted(existing):
        old = existing[old_id]
        old_subject = _subject_identity(old.lhs)
        old_operator = _operator_identity(old)
        if old_subject is None or old_operator is None:
            continue
        for new_id in sorted(new):
            current = new[new_id]
            if old_id == new_id:
                continue
            new_subject = _subject_identity(current.lhs)
            new_operator = _operator_identity(current)
            if (
                new_subject != old_subject
                or new_operator != old_operator
                or current.modality is not old.modality
                or not _temporally_overlaps(old.temporal, current.temporal)
            ):
                continue
            pair = (old_id, new_id)
            candidates[pair] = LifecycleMatchCandidate(
                old_ke_id=old_id,
                new_ke_id=new_id,
                old_revision=old.revision,
                new_revision=current.revision,
                subject_identity=old_subject,
                operator_identity=old_operator,
                modality=old.modality,
                old_polarity=old.polarity,
                new_polarity=current.polarity,
                old_lifecycle=old.lifecycle.value,
                new_lifecycle=current.lifecycle.value,
                old_temporal=old.temporal,
                new_temporal=current.temporal,
                old_gloss=old.gloss,
                new_gloss=current.gloss,
                old_produced_in_run_id=old.produced_in_run_id,
                new_produced_in_run_id=current.produced_in_run_id,
            )
    return candidates


def _validated_match_output(value: object) -> LifecycleMatchOutput:
    if not isinstance(value, BaseModel):
        raise LifecycleInvariantError("lifecycle matcher did not return a validated record")
    raw_matches = getattr(value, "matches", ())
    raw_pairs = tuple((item.old_ke_id, item.new_ke_id) for item in raw_matches)
    if len(raw_pairs) != len(set(raw_pairs)):
        raise LifecycleInvariantError("duplicate lifecycle matcher pair")
    try:
        return LifecycleMatchOutput.model_validate(value.model_dump(mode="python"))
    except ValidationError as error:
        raise LifecycleInvariantError("lifecycle matcher output failed local validation") from error


def _validate_decisions(
    candidates: Mapping[tuple[str, str], LifecycleMatchCandidate],
    output: LifecycleMatchOutput,
) -> tuple[LifecycleMatchDecision, ...]:
    offered = set(candidates)
    returned = {(item.old_ke_id, item.new_ke_id) for item in output.matches}
    unoffered = sorted(returned.difference(offered))
    if unoffered:
        raise LifecycleInvariantError(f"lifecycle matcher returned unoffered pair {unoffered[0]}")
    missing = sorted(offered.difference(returned))
    if missing:
        raise LifecycleInvariantError(f"lifecycle matcher is missing required pair {missing[0]}")
    by_pair = {(item.old_ke_id, item.new_ke_id): item for item in output.matches}
    decisions = tuple(by_pair[pair] for pair in sorted(offered))
    update_targets: dict[str, set[str]] = defaultdict(set)
    for decision in decisions:
        if decision.decision == "updates":
            update_targets[decision.new_ke_id].add(decision.old_ke_id)
    offenders = sorted(new_id for new_id, old_ids in update_targets.items() if len(old_ids) > 1)
    if offenders:
        raise LifecycleInvariantError(
            f"new KE {offenders[0]} has more than one update or retraction target"
        )
    return decisions


def _subject_identity(expression: Expression) -> str | None:
    if isinstance(expression, OperatorApplication):
        if expression.arguments:
            return _expression_identity(expression.arguments[0])
        return _identity(expression.operator.term_id)
    return _expression_identity(expression)


def _expression_identity(expression: Expression) -> str:
    if isinstance(expression, AssertionRef):
        return _identity(expression.assertion_id)
    if isinstance(expression, OperatorApplication):
        if expression.arguments:
            return _expression_identity(expression.arguments[0])
        return _identity(expression.operator.term_id)
    return _identity(expression.term_id)


def _operator_identity(equation: KnowledgeEquation) -> str | None:
    return _operator_in_expression(equation.rhs) or _operator_in_expression(equation.lhs)


def _operator_in_expression(expression: Expression) -> str | None:
    if isinstance(expression, OperatorApplication):
        return _identity(expression.operator.term_id)
    if isinstance(expression, OperatorRef):
        return _identity(expression.term_id)
    return None


def _identity(value: str) -> str:
    return normalize_surface(value)


def _temporally_overlaps(left: TemporalMetadata, right: TemporalMetadata) -> bool:
    left_start, left_end = _temporal_interval(left)
    right_start, right_end = _temporal_interval(right)
    if left_end is not None and right_start is not None and left_end < right_start:
        return False
    if right_end is not None and left_start is not None and right_end < left_start:
        return False
    return True


def _temporal_interval(
    temporal: TemporalMetadata,
) -> tuple[datetime | None, datetime | None]:
    if temporal.valid_from is not None or temporal.valid_to is not None:
        return temporal.valid_from, temporal.valid_to
    point = temporal.event_time or temporal.mentioned_at
    return point, point


def _recreate(
    equation: KnowledgeEquation,
    *,
    run_id: str,
    lifecycle: Lifecycle,
    contradicts: tuple[str, ...] | None = None,
    supersedes: tuple[str, ...] | None = None,
) -> KnowledgeEquation:
    recreated = KnowledgeEquation.create(
        level=equation.level,
        lhs=equation.lhs,
        rhs=equation.rhs,
        gloss=equation.gloss,
        modality=equation.modality,
        polarity=equation.polarity,
        lifecycle=lifecycle,
        speaker=equation.speaker,
        temporal=equation.temporal,
        ontology_bindings=equation.ontology_bindings,
        evidence_refs=equation.evidence_refs,
        derived_from=equation.derived_from,
        contradicts=contradicts if contradicts is not None else equation.contradicts,
        supersedes=supersedes if supersedes is not None else equation.supersedes,
        confidence=equation.confidence,
        produced_in_run_id=run_id,
        produced_in_stage=LIFECYCLE_STAGE,
    )
    if recreated.id != equation.id:
        raise LifecycleInvariantError("lifecycle revision changed the logical KE ID")
    return recreated


def _reject_duplicate_new_records(new: Sequence[KnowledgeEquation]) -> None:
    invalid_lifecycle = next(
        (item for item in new if item.lifecycle not in {Lifecycle.ACTIVE, Lifecycle.UNCERTAIN}),
        None,
    )
    if invalid_lifecycle is not None:
        raise LifecycleInvariantError(f"new KE {invalid_lifecycle.id} must be active or uncertain")
    ids = tuple(item.id for item in new)
    if len(ids) != len(set(ids)):
        raise LifecycleInvariantError("duplicate new knowledge-equation IDs are not allowed")
    revisions = tuple(item.revision for item in new)
    if len(revisions) != len(set(revisions)):
        raise LifecycleInvariantError("duplicate new knowledge-equation revisions are not allowed")
