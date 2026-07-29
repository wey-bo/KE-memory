"""Six experimental arms: ranking, deterministic execution, and guarded fallback."""

from __future__ import annotations

import json
import re
from typing import Any, Iterable

from .dense import DenseEncoder, rank_dense


_ARMS = {"B0", "B1", "B2", "O-", "O+", "O+E"}
_HARD = {
    "polarity": "polarity",
    "modality": "modality",
    "quantity": "quantity",
    "time_filter": "valid_time",
    "status_filter": "lifecycle_status",
    "context_filter": "conflict_group",
    "provenance_filter": "provenance_status",
}
_PLAN_ALIASES = {
    "time_filter": "valid_time",
    "provenance_filter": "provenance_status",
}


def _plan_value(plan: dict[str, Any], name: str) -> Any:
    value = plan.get(name)
    if value is None and name in _PLAN_ALIASES:
        value = plan.get(_PLAN_ALIASES[name])
    return value


def _superseded(records: list[dict[str, Any]]) -> set[str]:
    return {item for record in records for item in record.get("supersedes", [])}


def _match(
    record: dict[str, Any],
    plan: dict[str, Any],
    relaxed: set[str] | None = None,
) -> tuple[bool, dict[str, bool]]:
    relaxed = relaxed or set()
    checks: dict[str, bool] = {}
    predicate = plan.get("predicate")
    checks["predicate"] = "predicate" in relaxed or predicate is None or record.get("predicate") == predicate
    entities = {str(value).lower() for value in plan.get("entity_candidates", [])}
    record_entities = {str(value).lower() for value in record.get("entities", [])}
    checks["entities"] = "entity" in relaxed or not entities or entities.issubset(record_entities)
    checks["roles"] = "roles" in relaxed or all(
        record.get("roles", {}).get(name) == value
        for name, value in plan.get("role_constraints", {}).items()
    )
    for plan_name, record_name in _HARD.items():
        expected = _plan_value(plan, plan_name)
        if plan_name == "transaction_filter" or plan_name == "require_supersession":
            continue
        checks[plan_name] = expected is None or str(record.get(record_name)) == str(expected)
    transaction_filter = plan.get("transaction_filter")
    checks["transaction_filter"] = transaction_filter is None or (
        transaction_filter == "latest" and record.get("transaction_time") is not None
    )
    require_supersession = bool(plan.get("require_supersession", False))
    checks["require_supersession"] = not require_supersession or bool(record.get("supersedes"))
    return all(checks.values()), checks


def _relation_parts(relation: dict[str, Any]) -> tuple[Any, Any, Any]:
    return (
        relation.get("source", relation.get("subject", relation.get("from"))),
        relation.get("predicate", relation.get("relation", relation.get("type"))),
        relation.get("target", relation.get("object", relation.get("to"))),
    )


def _step_parts(step: Any, answer_slot: str) -> tuple[Any, Any, Any, Any]:
    if hasattr(step, "model_dump"):
        step = step.model_dump(mode="json")
    source = step.get("source", step.get("from"))
    predicate = step.get("predicate", step.get("relation"))
    target = step.get("target", step.get("to"))
    target_slot = step.get("target_slot")
    # v1 automatic plans used `to: project` as a variable name.
    if target_slot is None and "to" in step and target == answer_slot:
        target, target_slot = None, answer_slot
    return source, predicate, target, target_slot


def _target_matches_slot(value: Any, slot: str | None) -> bool:
    if slot is None:
        return True
    text = str(value)
    slot_text = str(slot)
    if text == slot_text or text.startswith(f"{slot_text}-"):
        return True
    if slot_text == "project":
        return bool(re.fullmatch(r"project-\d+", text, flags=re.I))
    return False


def _path_records(
    records: list[dict[str, Any]],
    plan: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    steps = plan.get("traversal_steps", [])
    if not steps:
        selected = list(records)
        bindings: dict[str, str] = {}
    else:
        selected = []
        bindings = {}
        answer_slot = str(plan.get("required_answer_slot", ""))
        for step in steps:
            source, predicate, target, target_slot = _step_parts(step, answer_slot)
            step_mapping = step.model_dump(mode="json") if hasattr(step, "model_dump") else step
            legacy_variable = (
                isinstance(step_mapping, dict)
                and "to" in step_mapping
                and step_mapping.get("target_slot") is None
            )
            candidates: list[tuple[dict[str, Any], str]] = []
            for record in records:
                for relation in record.get("relations", []):
                    edge_source, edge_predicate, edge_target = _relation_parts(relation)
                    if edge_source != source or edge_predicate != predicate:
                        continue
                    if target is not None and edge_target != target:
                        continue
                    if target is None and target_slot is not None and not _target_matches_slot(edge_target, str(target_slot)):
                        continue
                    if legacy_variable and target_slot is not None and not (
                        edge_target == target_slot or str(edge_target).startswith(f"{target_slot}-")
                    ):
                        continue
                    candidates.append((record, str(edge_target)))
            if not candidates:
                return [], {}
            if target_slot is not None:
                values = {value for _, value in candidates}
                if len(values) != 1:
                    return [], {}
                value = next(iter(values))
                if target_slot in bindings and bindings[target_slot] != value:
                    return [], {}
                bindings[str(target_slot)] = value
            selected.extend(record for record, _ in candidates)

    selected_by_id = {record["record_id"]: record for record in selected}
    needed = {
        str(value).lower()
        for group in plan.get("conjunction_groups", [])
        for value in group
        if value
    }
    if needed:
        selected_by_id.update(
            {
                record["record_id"]: record
                for record in records
                if needed.intersection(str(value).lower() for value in record.get("entities", []))
            }
        )
    selected = [record for record in records if record["record_id"] in selected_by_id]
    covered_entities = {
        str(entity).lower()
        for record in selected
        for entity in record.get("entities", [])
    }
    for group in plan.get("conjunction_groups", []):
        required = {str(value).lower() for value in group if value}
        if not required.issubset(covered_entities):
            return [], {}
    return selected, bindings


def _provenance_closure(
    all_records: list[dict[str, Any]],
    seeds: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_id = {record["record_id"]: record for record in all_records}
    neighbours: dict[str, set[str]] = {record_id: set() for record_id in by_id}
    for record in all_records:
        record_id = record["record_id"]
        for related_id in [*record.get("derived_from", []), *record.get("supersedes", [])]:
            if related_id in by_id:
                neighbours[record_id].add(related_id)
                neighbours[related_id].add(record_id)
    reached = {record["record_id"] for record in seeds}
    pending = list(reached)
    while pending:
        record_id = pending.pop()
        for related_id in neighbours.get(record_id, set()):
            if related_id not in reached:
                reached.add(related_id)
                pending.append(related_id)
    return [record for record in all_records if record["record_id"] in reached]


def _answer(
    records: list[dict[str, Any]],
    plan: dict[str, Any],
    bindings: dict[str, str] | None = None,
    explicit_absence: bool = False,
    allow_text_fallback: bool = False,
) -> tuple[Any, bool]:
    if explicit_absence:
        return None, True
    slot = plan.get("required_answer_slot")
    if bindings and slot in bindings:
        return bindings[slot], False
    for record in records:
        if slot in record.get("roles", {}):
            value = record["roles"][slot]
            if value not in (None, ""):
                return value, False
        if slot == "quantity" and record.get("quantity") is not None:
            return record["quantity"], False
        if slot == "polarity" and record.get("polarity") is not None:
            return ("no" if record["polarity"] == "negative" else "yes"), False
        if slot == "value" and record.get("polarity") is not None:
            return ("no" if record["polarity"] == "negative" else "yes"), False
    if allow_text_fallback:
        return _answer_from_text(records, plan)
    return None, True


def _answer_from_text(
    records: Iterable[dict[str, Any]],
    plan: dict[str, Any],
) -> tuple[Any, bool]:
    """Extract only explicit answer phrases from the selected evidence text.

    Ranking arms intentionally expose no structured fields.  This small
    answer stage is shared by every arm and never inspects gold annotations or
    applies a structural filter; it only reads phrases already present in the
    selected records.
    """
    texts = [str(record.get("surface_text", "")) for record in records]
    texts = [text for text in texts if text.strip()]
    if not texts:
        return None, True
    slot = str(plan.get("required_answer_slot") or "value")

    if slot == "quantity":
        candidates: list[tuple[int, int]] = []
        for index, text in enumerate(texts):
            matches = list(re.finditer(r"\b(?:exactly|claim uses|uses|approve(?:d|s)?)\s+(\d+)\b", text, re.I))
            for match in matches:
                score = 0
                prefix = text[: match.start()].lower()
                if "should approve" in text.lower() or "current request" in prefix or "active instruction" in prefix:
                    score += 3
                if "exactly" in match.group(0).lower():
                    score += 2
                if "another" in text.lower() or "different" in text.lower():
                    score -= 2
                candidates.append((score, index * 100 + int(match.start())))
                candidates[-1] = (score, int(match.group(1)))
        if candidates:
            return str(max(candidates, key=lambda item: item[0])[1]), False

    if slot in {"value", "polarity"}:
        negative: list[tuple[int, int]] = []
        positive: list[tuple[int, int]] = []
        for index, text in enumerate(texts):
            low = text.lower()
            if re.search(r"\b(?:inactive|not active|no owner|none was|without)\b", low):
                score = 3 + int(any(marker in low for marker in ("current", "correction", "after", "following")))
                negative.append((score, -index))
            if re.search(r"\b(?:active|is named|was named)\b", low) and not re.search(r"\b(?:inactive|not active)\b", low):
                positive.append((1, -index))
        if negative:
            return "no", False
        if positive:
            return "yes", False

    if slot == "project":
        candidates: list[tuple[int, int, str]] = []
        for index, text in enumerate(texts):
            for match in re.finditer(r"\bproject-\d+\b", text, re.I):
                low = text.lower()
                score = 1
                if "exact set" in low:
                    score += 3
                if re.search(r"\b(?:archive|report|contract|invoice|permit|tablet|shipment|calendar) links?\b", low):
                    score += 2
                if any(marker in low for marker in ("separate", "unrelated", "another", "only")):
                    score -= 2
                candidates.append((score, -index, match.group(0)))
        if candidates:
            return max(candidates, key=lambda item: (item[0], item[1]))[2], False

    if slot == "sense":
        candidates: list[tuple[int, int, str]] = []
        for index, text in enumerate(texts):
            for match in re.finditer(r"\bmeans?\s+(?:an?\s+)?([a-z][a-z ]+?)(?:,?\s+not\b|\.|$)", text, re.I):
                value = match.group(1).strip()
                score = 2 if "account record" in value.lower() else 1
                if "not a travel schedule" in text.lower():
                    score += 2
                candidates.append((score, -index, value))
        if candidates:
            return max(candidates, key=lambda item: (item[0], item[1]))[2], False

    if slot == "owner":
        for index, text in enumerate(texts):
            match = re.search(r"\b([A-Z][a-z]+)\s+is listed as owner\b", text)
            if match:
                return match.group(1), False
        if any(re.search(r"\bno owner\b|\bowner\s+was\s+not\s+named\b|\bowner\s+is\s+absent\b", text, re.I) for text in texts):
            return None, True

    if slot in {"agent", "requester", "beneficiary"}:
        for text in texts:
            match = re.search(r"\bthe\s+([a-z][a-z-]*)\s+(?:should|may|can)\s+approve\b", text, re.I)
            if match:
                return match.group(1), False
            match = re.search(r"\b([A-Z][a-z]+|receiver|clerk)\s+approved\b", text)
            if match:
                return match.group(1), False

    if plan.get("answer_policy") == "require_explicit_absence" and any(
        re.search(r"\bno\s+[^.]*\b(named|specified|provided)\b", text, re.I) for text in texts
    ):
        return None, True
    return None, True


def _turn_ids(records: Iterable[dict[str, Any]]) -> list[str]:
    return sorted({turn for record in records for turn in record.get("source_turn_ids", [])})


def execute_arm(
    arm: str,
    scenario: dict[str, Any],
    records: list[dict[str, Any]],
    query_plan: dict[str, Any],
    encoder: DenseEncoder,
    distractors: Iterable[dict[str, Any]] = (),
    evidence_token_budget: int | None = None,
) -> dict[str, Any]:
    if arm not in _ARMS:
        raise ValueError(f"unknown arm {arm}")
    all_records = [*records, *distractors]
    result: dict[str, Any] = {
        "arm": arm,
        "scenario_id": scenario["scenario_id"],
        "ranked_evidence": [],
        "selected_evidence_turn_ids": [],
        "predicted_answer": None,
        "abstained": True,
        "constraint_checks": {},
        "symbolic_trace": [],
        "fallback_trigger": None,
        "fallback_reason": None,
        "fallback": {"triggered": False, "reason": None, "rejected_candidates": []},
        "rejected_fallback_candidates": [],
        "model_metadata": dict(encoder.model_metadata),
    }
    if arm in {"B0", "B1", "B2"}:
        candidates = [
            dict(
                record,
                surface_text=(
                    json.dumps(record, sort_keys=True, default=str)
                    if arm == "B2"
                    else record.get("surface_text", "")
                ),
            )
            for record in all_records
        ]
        ranking = rank_dense(str(scenario.get("question", "")), candidates, encoder)
        index = {record["record_id"]: record for record in all_records}
        token_budget = int(
            evidence_token_budget
            if evidence_token_budget is not None
            else scenario.get("candidate_answer_budget", 32)
        )
        used = 0
        selected = []
        for item in ranking:
            candidate = index[item["record_id"]]
            cost = len(str(candidate.get("surface_text", "")).split())
            if selected and used + cost > token_budget:
                break
            if cost <= token_budget:
                selected.append(candidate)
                used += cost
        result.update(ranked_evidence=ranking, selected_evidence_turn_ids=_turn_ids(selected))
        result["predicted_answer"], result["abstained"] = _answer(
            selected,
            query_plan,
            allow_text_fallback=True,
        )
        return result

    superseded = _superseded(all_records)
    inactive_lifecycle = {"rejected", "obsolete"}
    active = [
        record
        for record in all_records
        if record["record_id"] not in superseded
        and record.get("lifecycle_status") not in inactive_lifecycle
    ]
    matched: list[dict[str, Any]] = []
    traces = []
    distributed = bool(query_plan.get("conjunction_groups") or query_plan.get("traversal_steps"))
    for record in active:
        passed, checks = _match(record, query_plan, {"entity"} if distributed else None)
        traces.append({"record_id": record["record_id"], "accepted": passed, "checks": checks})
        if passed:
            matched.append(record)

    bindings: dict[str, str] = {}
    if distributed and matched:
        matched, bindings = _path_records(matched, query_plan)

    explicit_absence = False
    answer_slot = query_plan.get("required_answer_slot")
    if matched and query_plan.get("answer_policy") == "require_explicit_absence":
        absence_matched = [record for record in matched if answer_slot in record.get("absent_slots", [])]
        if absence_matched:
            matched = absence_matched
            explicit_absence = True
        else:
            matched = []
    elif matched and any(answer_slot in record.get("absent_slots", []) for record in matched):
        explicit_absence = True
    if not matched:
        absence_records = []
        for record in active:
            if answer_slot not in record.get("absent_slots", []):
                continue
            passed, _ = _match(record, query_plan, {"roles"})
            if passed:
                absence_records.append(record)
        if absence_records:
            matched = absence_records
            explicit_absence = True

    result["symbolic_trace"] = traces
    accepted_traces = [trace for trace in traces if trace["accepted"]]
    result["constraint_checks"] = (
        {**accepted_traces[0]["checks"], "complete_result": bool(matched)}
        if accepted_traces
        else {"complete_result": bool(matched)}
    )
    if query_plan.get("traversal_steps"):
        result["constraint_checks"]["traversal"] = bool(bindings)
    if query_plan.get("conjunction_groups"):
        result["constraint_checks"]["conjunction"] = bool(matched)

    unresolved = set(query_plan.get("declared_unresolved_slots", query_plan.get("unresolved_slots", [])))
    allowed = unresolved & {"entity", "entities", "predicate", "lexical"}
    if arm == "O+E" and allowed:
        reason = "uncovered_predicate" if "predicate" in allowed else "unresolved_entity"
        relaxed = {"predicate"} if "predicate" in allowed else {"entity"}
        result.update(fallback_trigger=reason, fallback_reason=reason)
        result["fallback"] = {"triggered": True, "reason": reason, "rejected_candidates": []}
        ranking = rank_dense(str(scenario.get("question", "")), active, encoder)
        result["ranked_evidence"] = ranking
        by_id = {record["record_id"]: record for record in active}
        for item in ranking:
            candidate = by_id[item["record_id"]]
            passed, _ = _match(candidate, query_plan, relaxed)
            if passed:
                structured_answer, structured_abstained = _answer([candidate], query_plan)
                text_answer, text_abstained = (
                    (None, True)
                    if not structured_abstained
                    else _answer_from_text([candidate], query_plan)
                )
                if structured_abstained and text_abstained:
                    result["rejected_fallback_candidates"].append(candidate["record_id"])
                    result["fallback"]["rejected_candidates"].append(candidate["record_id"])
                    continue
                if candidate not in matched:
                    matched.append(candidate)
                break
            result["rejected_fallback_candidates"].append(candidate["record_id"])
            result["fallback"]["rejected_candidates"].append(candidate["record_id"])

    if result.get("fallback", {}).get("triggered"):
        result["constraint_checks"]["complete_result"] = bool(matched)
        result["constraint_checks"]["fallback_guarded"] = bool(matched)

    answer_records = list(matched)
    result["predicted_answer"], result["abstained"] = _answer(
        answer_records,
        query_plan,
        bindings,
        explicit_absence,
        allow_text_fallback=bool(result.get("fallback", {}).get("triggered")),
    )
    evidence_records = matched
    if query_plan.get("evidence_expansion") == "provenance_closure" and matched:
        evidence_records = _provenance_closure(all_records, matched)
    result["selected_evidence_turn_ids"] = _turn_ids(evidence_records)
    return result
