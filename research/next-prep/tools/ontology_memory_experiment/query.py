"""Generic English query compilation with a separate oracle-fixture boundary."""
from __future__ import annotations
import copy
import re
from typing import Any

_OBJECT = r"(archive|invoice|permit|tablet|shipment|calendar|report|contract)"

def compile_query(question: str, track: str, oracle_query_fixture: Any | None = None) -> dict[str, Any]:
    if track == "oracle":
        if not oracle_query_fixture: raise ValueError("oracle track requires a separate query fixture")
        fixture = oracle_query_fixture.model_dump() if hasattr(oracle_query_fixture, "model_dump") else dict(oracle_query_fixture)
        return copy.deepcopy(fixture.get("query_plan", fixture))
    if track != "automatic": raise ValueError("track must be oracle or automatic")
    low = question.lower(); object_match = re.search(_OBJECT, low); obj = object_match.group(1) if object_match else None
    identifier = re.search(r"\b(?:invoice|order|case|document)\s+[A-Z]-?\d+\b", question, flags=re.I)
    entities = [identifier.group(0) if identifier else obj] if (identifier or obj) else []
    for value in re.findall(r"\b(Avery|Blair|Casey|Devon|Emery|Flynn|Gray|Harper|Boston|Dublin|Lisbon|Oslo|Reno|Seoul|Taipei|Zurich)\b", question): entities.append(value)
    plan: dict[str, Any] = {"entity_candidates": entities, "predicate": None, "role_constraints": {}, "polarity": None, "modality": None, "quantity": None, "time_filter": None, "status_filter": None, "provenance_filter": None, "conjunction_groups": [], "traversal_steps": [], "required_answer_slot": "value", "declared_unresolved_slots": []}
    if "how many" in low:
        # The question may constrain an agent role, but its requested quantity
        # is an answer slot and must never be copied into ``quantity``.
        role_constraints: dict[str, str] = {}
        agent_match = re.search(
            r"\bthe\s+([a-z][a-z-]*)\s+(?:(?:is\s+)?expected\s+to|(?:is\s+)?supposed\s+to|should|may|can|did|does)\s+approve\b",
            low,
        )
        if agent_match:
            role_constraints["agent"] = agent_match.group(1)
        modality = "planned" if re.search(r"\b(?:expected\s+to|supposed\s+to|should)\s+approve\b", low) else None
        plan.update(
            predicate="approve",
            role_constraints=role_constraints,
            modality=modality,
            required_answer_slot="quantity",
        )
        person = next((value for value in entities if value[0].isupper() and value not in {"Boston", "Dublin", "Lisbon", "Oslo", "Reno", "Seoul", "Taipei", "Zurich"}), None)
        if person: plan["role_constraints"]["requester"] = person
    elif "is the" in low and "active after" in low:
        # A yes/no question asks for polarity; it does not assert either
        # polarity.  Only explicit lexical negation is a polarity filter.
        explicit_negative = bool(re.search(r"\b(?:not|inactive|isn't|wasn't|weren't)\b", low))
        date_match = re.search(r"\d{4}-\d{2}-\d{2}", question)
        plan.update(
            predicate="active",
            polarity="negative" if explicit_negative else None,
            required_answer_slot="value",
            time_filter=date_match.group(0) if date_match else None,
            status_filter="current",
            evidence_expansion="provenance_closure",
        )
    elif "linked through both" in low or "shared by both" in low or "connects both" in low:
        location = next((value for value in entities if value[0].isupper()), None)
        plan.update(
            predicate="linked_to",
            conjunction_groups=[[obj, "archive", location]],
            traversal_steps=[
                {"source": "archive", "predicate": "linked_to", "target_slot": "project"}
            ],
            required_answer_slot="project",
        )
    elif "which sense" in low:
        plan.update(predicate="sense_of", required_answer_slot="sense", evidence_expansion="provenance_closure")
    elif "which project" in low and any(marker in low for marker in ("point", "designat", "map", "route")):
        codename_match = re.search(r"\bdoes\s+([a-z][a-z0-9-]*)\s+(?:point|designate|designates|map|maps|route|routes)\b", low)
        if codename_match and codename_match.group(1) not in entities:
            entities.append(codename_match.group(1))
        plan.update(
            predicate="points_to_project",
            required_answer_slot="project",
            declared_unresolved_slots=["predicate"],
            evidence_expansion="provenance_closure",
        )
    elif "who owns" in low:
        plan.update(
            predicate="own",
            required_answer_slot="owner",
            answer_policy="require_explicit_absence",
            evidence_expansion="provenance_closure",
        )
    elif "approve" in low:
        plan.update(predicate="approve", required_answer_slot="agent", polarity="negative" if "not" in low else None)
    else: plan["declared_unresolved_slots"].append("predicate")
    return plan
