"""Source-blind representation adapters for the controlled experiment."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from .models import MemoryRecord


_PEOPLE = r"Avery|Blair|Casey|Devon|Emery|Flynn|Gray|Harper"
_LOCATIONS = r"Boston|Dublin|Lisbon|Oslo|Reno|Seoul|Taipei|Zurich"
_OBJECTS = r"archive|invoice|permit|tablet|shipment|calendar|report|contract"


def _as_dict(value: Any) -> dict[str, Any]:
    return value.model_dump() if hasattr(value, "model_dump") else dict(value)


def _hash_source(source: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(source, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _base(turn: dict[str, Any], ordinal: int, **values: Any) -> dict[str, Any]:
    record = {
        "record_id": values.pop("record_id", f"{turn['turn_id']}-R{ordinal}"),
        "source_turn_ids": values.pop("source_turn_ids", [turn["turn_id"]]),
        "surface_text": values.pop("surface_text", turn["text"]),
        "entities": values.pop("entities", []), "predicate": values.pop("predicate", None),
        "roles": values.pop("roles", {}), "polarity": values.pop("polarity", None),
        "modality": values.pop("modality", None), "quantity": values.pop("quantity", None),
        "valid_time": values.pop("valid_time", None), "transaction_time": values.pop("transaction_time", None),
        "provenance_status": values.pop("provenance_status", {"user": "user_reported", "agent": "agent_generated", "tool": "tool_observed"}.get(turn.get("speaker"))),
        "lifecycle_status": values.pop("lifecycle_status", None),
        "conflict_group": values.pop("conflict_group", None), "supersedes": values.pop("supersedes", []),
        "derived_from": values.pop("derived_from", []), "absent_slots": values.pop("absent_slots", []),
        "relations": values.pop("relations", []), "unresolved_slots": values.pop("unresolved_slots", []), **values,
    }
    if record["quantity"] is not None:
        record["quantity"] = str(record["quantity"])
    # Keep this adapter tolerant of additive optional fields in the public
    # record contract while still validating every field it knows about.
    MemoryRecord.model_validate({field: record.get(field) for field in MemoryRecord.model_fields if field in record})
    return record


def _date(text: str) -> str | None:
    match = re.search(r"\b\d{4}-\d{2}-\d{2}\b", text)
    return match.group(0) if match else None


def _merge_unique(values: list[str], *extra: str | None) -> list[str]:
    return list(dict.fromkeys([*values, *[value for value in extra if value]]))


def _active_status_record(
    turn: dict[str, Any],
    *,
    object_name: str | None,
    location_name: str | None = None,
    polarity: str,
    lifecycle_status: str | None,
    valid_time: str | None = None,
    ordinal: int = 1,
) -> dict[str, Any]:
    return _base(
        turn,
        ordinal,
        entities=[value for value in (object_name, location_name) if value],
        predicate="active",
        polarity=polarity,
        valid_time=valid_time,
        lifecycle_status=lifecycle_status,
        conflict_group=f"{object_name}:active" if object_name else None,
        roles={"value": "no" if polarity == "negative" else "yes"},
    )


def _automatic(turn: dict[str, Any]) -> list[dict[str, Any]]:
    text = turn["text"]
    low = text.lower()
    person = re.search(r"\b(Avery|Blair|Casey|Devon|Emery|Flynn|Gray|Harper)\b", text)
    location = re.search(r"\b(Boston|Dublin|Lisbon|Oslo|Reno|Seoul|Taipei|Zurich)\b", text)
    obj = re.search(r"\b(archive|invoice|permit|tablet|shipment|calendar|report|contract)s?\b", low)
    object_name = obj.group(1) if obj else None
    quantity = re.search(r"\bexactly (\d+)\b", low) or re.search(r"\bapprove (\d+)\b", low)
    codename = None
    if "project-" in low or "codename" in low:
        code_match = re.search(r"\bcodename\s+([a-z][a-z0-9-]*)\b", low) or re.search(r"\b([a-z][a-z0-9-]*)\s+note\b", low)
        codename = code_match.group(1) if code_match and code_match.group(1) not in {"another", "the", "a"} else None
    if "approve" in low:
        return [_base(turn, 1, entities=[value for value in (person.group(0) if person else None, object_name) if value], predicate="approve", roles={"agent": "clerk", **({"requester": person.group(0)} if person else {})}, polarity="negative" if "did not" in low else "positive", modality="possible" if " may " in f" {low} " else ("requested" if "asked" in low or "request" in low else "planned" if "should" in low or "supposed to" in low or "expected to" in low else "asserted"), quantity=quantity.group(1) if quantity else None)]
    if "recorded status before" in low and " active" in low:
        return [
            _active_status_record(
                turn,
                object_name=object_name,
                polarity="positive",
                lifecycle_status="historical",
                valid_time=_date(text),
            )
        ]
    if "before" in low and "log recorded" in low and " as active" in low:
        return [
            _active_status_record(
                turn,
                object_name=object_name,
                polarity="positive",
                lifecycle_status="historical",
                valid_time=_date(text),
            )
        ]
    if "superseded" in low and "not active" in low:
        return [
            _active_status_record(
                turn,
                object_name=object_name,
                polarity="negative",
                lifecycle_status="current",
                valid_time=_date(text),
            )
        ]
    if "current status is inactive" in low:
        return [
            _active_status_record(
                turn,
                object_name=object_name,
                polarity="negative",
                lifecycle_status="current",
                valid_time=_date(text),
            )
        ]
    if "obsolete record" in low and ("remains active" in low or "was active" in low or "is active" in low):
        return [
            _active_status_record(
                turn,
                object_name=object_name,
                polarity="positive",
                lifecycle_status="obsolete",
                valid_time=_date(text),
            )
        ]
    if " is active in " in low or " was active in " in low:
        return [
            _active_status_record(
                turn,
                object_name=object_name,
                location_name=location.group(0) if location else None,
                polarity="positive",
                lifecycle_status="historical" if " was active in " in low else "current",
                valid_time=_date(text),
            )
        ]
    if " links " in low:
        project = re.search(r"project-\d+", low)
        subject = "archive" if low.startswith("the archive") else object_name
        objects = [value for value in (location.group(0) if location else None, project.group(0) if project else None) if value]
        rejected = any(marker in low for marker in ("separate", "similar", "different"))
        return [_base(turn, 1, entities=[value for value in (subject, *objects) if value], predicate="linked_to", roles={"project": project.group(0)} if project and not rejected else {}, lifecycle_status="rejected" if rejected else None, relations=[{"source": subject or "", "predicate": "linked_to", "target": value} for value in objects])]
    if " connected " in low and " to both " in low:
        targets = [location.group(0)] if location else []
        if "archive" in low:
            targets.append("archive")
        rejected = any(marker in low for marker in ("similar", "separate", "different", "not part"))
        return [_base(turn, 1, entities=[value for value in (person.group(0) if person else None, object_name, *targets) if value], predicate="linked_to", lifecycle_status="rejected" if rejected else None, relations=[{"source": object_name or "", "predicate": "linked_to", "target": target} for target in targets])]
    if " linked " in low and " to " in low:
        targets = [location.group(0)] if location else []
        if "archive" in low and "not part" not in low:
            targets.append("archive")
        rejected = any(marker in low for marker in ("similar", "separate", "different", "not part"))
        return [_base(turn, 1, entities=[value for value in (person.group(0) if person else None, object_name, *targets) if value], predicate="linked_to", lifecycle_status="rejected" if rejected else None, relations=[{"source": object_name or "", "predicate": "linked_to", "target": target} for target in targets])]
    if "exact set is" in low or "exact set contains" in low or "exact set includes" in low or "exact set comprises" in low:
        project = re.search(r"project-\d+", low)
        entity_values = _merge_unique(
            [],
            object_name,
            location.group(0) if location else None,
            "archive" if "archive" in low else None,
            project.group(0) if project else None,
        )
        return [
            _base(
                turn,
                1,
                entities=entity_values,
                predicate="linked_to",
                lifecycle_status="supported",
                roles={"project": project.group(0)} if project else {},
            )
        ]
    if "listed as owner" in low:
        owner = re.search(r"\b([A-Z][a-z]+)\s+is listed as owner\b", text)
        return [
            _base(
                turn,
                1,
                entities=[value for value in (object_name, location.group(0) if location else None) if value],
                predicate="own",
                roles={"owner": owner.group(1)} if owner else {},
            )
        ]
    used_ledger = re.search(r"\bused\s+ledger\s+for\s+the\s+(archive|invoice|permit|tablet|shipment|calendar|report|contract)\b", low)
    if used_ledger:
        return [
            _base(
                turn,
                1,
                entities=[value for value in (person.group(0) if person else None, used_ledger.group(1), location.group(0) if location else None) if value],
                predicate="sense_of",
                roles={"alias": "ledger"},
                polarity="positive",
            )
        ]
    if "no owner" in low or "owner or external relation was named" in low:
        return [
            _base(
                turn,
                1,
                entities=[value for value in (object_name, location.group(0) if location else None) if value],
                predicate="own",
                polarity="negative",
                absent_slots=["owner", "external_relation"],
            )
        ]
    if "available turns support only the accounting sense" in low or "evidence supports the accounting sense only" in low:
        return [
            _base(
                turn,
                1,
                entities=[value for value in (object_name, location.group(0) if location else None) if value],
                predicate="sense_of",
                roles={"sense": "account record"},
                absent_slots=["owner", "external_relation"],
            )
        ]
    if "account record" in low or "ledger" in low:
        rejected = "another trip record" in low or (
            "travel schedule" in low
            and "not a travel schedule" not in low
            and "rather than a travel schedule" not in low
        )
        alias = re.search(r"\bcalled the (?:archive|invoice|permit|tablet|shipment|calendar|report|contract) a ([a-z]+)\b", low)
        roles = {}
        if "accounting sense" in low or "account record" in low:
            roles["sense"] = "account record"
        if alias:
            roles["alias"] = alias.group(1)
        if (
            "travel schedule" in low
            and "not a travel schedule" not in low
            and "rather than a travel schedule" not in low
        ):
            roles["sense"] = "travel schedule"
        return [_base(turn, 1, entities=[value for value in (object_name, location.group(0) if location else None) if value], predicate="sense_of", roles=roles, polarity="negative" if "not a travel" in low else "positive", lifecycle_status="rejected" if rejected else None)]
    return [
        _base(
            turn,
            1,
            entities=[
                value
                for value in (
                    person.group(0) if person else None,
                    object_name,
                    location.group(0) if location else None,
                    codename,
                )
                if value
            ],
            unresolved_slots=["predicate"],
        )
    ]


def _complete_temporal_links(records: list[dict[str, Any]]) -> None:
    latest_by_group: dict[str, dict[str, Any]] = {}
    latest_correction_by_group: dict[str, dict[str, Any]] = {}
    latest_correction: dict[str, Any] | None = None
    for record in records:
        group = record.get("conflict_group")
        if not group or record.get("predicate") != "active":
            text = str(record.get("surface_text", "")).lower()
            if (
                record.get("predicate") == "active"
                and not group
                and record.get("polarity") == "negative"
                and "current status" in text
                and latest_correction is not None
            ):
                group = latest_correction.get("conflict_group")
                record["conflict_group"] = group
                record["entities"] = _merge_unique(
                    list(record.get("entities", [])),
                    *[value for value in latest_correction.get("entities", []) if str(value).islower()],
                )
            else:
                continue
        text = str(record.get("surface_text", "")).lower()
        if record.get("polarity") == "negative" and "superseded" in text:
            prior = latest_by_group.get(group)
            if prior is not None:
                record["supersedes"] = _merge_unique(record.get("supersedes", []), prior["record_id"])
                record["derived_from"] = _merge_unique(record.get("derived_from", []), prior["record_id"])
            latest_correction_by_group[group] = record
            latest_correction = record
        elif record.get("polarity") == "negative" and "current status" in text:
            correction = latest_correction_by_group.get(group)
            if correction is not None:
                related = [correction["record_id"], *correction.get("supersedes", [])]
                record["derived_from"] = _merge_unique(record.get("derived_from", []), *related)
        latest_by_group[group] = record


def _complete_lexical_context(records: list[dict[str, Any]]) -> None:
    context_entities: list[str] = []
    context_record_ids: list[str] = []
    sense_record_ids: list[str] = []
    absence_record_ids: list[str] = []
    codename_contexts: dict[str, tuple[list[str], str]] = {}
    for record in records:
        text = str(record.get("surface_text", "")).lower()
        codename_match = re.search(r"\bcodename\s+([a-z][a-z0-9-]*)\b", text)
        if codename_match:
            codename_contexts[codename_match.group(1)] = (
                list(record.get("entities", [])),
                record["record_id"],
            )
        for codename, (entities, record_id) in codename_contexts.items():
            if codename in text and record["record_id"] != record_id:
                record_entities = {str(value) for value in record.get("entities", [])}
                context_objects = {value for value in entities if str(value).lower() in _OBJECTS.split("|")}
                context_locations = {value for value in entities if str(value) in _LOCATIONS.split("|")}
                record_objects = {value for value in record_entities if str(value).lower() in _OBJECTS.split("|")}
                record_locations = {value for value in record_entities if str(value) in _LOCATIONS.split("|")}
                if record_objects and context_objects and record_objects.isdisjoint(context_objects):
                    continue
                if record_locations and context_locations and record_locations.isdisjoint(context_locations):
                    continue
                record["entities"] = _merge_unique(list(record.get("entities", [])), codename, *entities)
                record["derived_from"] = _merge_unique(list(record.get("derived_from", [])), record_id)
        if record.get("predicate") == "sense_of" and record.get("roles", {}).get("alias") == "ledger":
            context_entities = list(record.get("entities", []))
            context_record_ids = [record["record_id"]]
            sense_record_ids = []
            absence_record_ids = []
            continue
        if not context_entities or record.get("lifecycle_status") == "rejected":
            continue
        if (
            record.get("predicate") in {"sense_of", "own"}
            and "another" not in text
            and "trip record" not in text
            and "listed as owner" not in text
        ):
            record["entities"] = _merge_unique(list(record.get("entities", [])), *context_entities)
            extra_absence_ids = absence_record_ids if "missing details" in text or "unresolved" in text else []
            record["derived_from"] = _merge_unique(list(record.get("derived_from", [])), *context_record_ids, *sense_record_ids, *extra_absence_ids)
            if record.get("predicate") == "own" and record.get("absent_slots"):
                absence_record_ids = _merge_unique(absence_record_ids, record["record_id"])
            if record.get("predicate") == "sense_of" and record.get("roles", {}).get("sense"):
                sense_record_ids = _merge_unique(sense_record_ids, record["record_id"])


def build_distractor_representations(distractor_records: Any) -> list[dict[str, Any]]:
    """Parse distractor text into typed, source-traceable memory records.

    Distractors intentionally have no scenario context at this boundary.  The
    parser therefore uses only their own ``record_id`` and ``text`` and marks
    unsupported wording unresolved instead of inferring a gold-side answer.
    """
    records: list[dict[str, Any]] = []
    for raw in distractor_records:
        item = _as_dict(raw)
        record_id = item.get("record_id")
        text = item.get("text")
        if not isinstance(record_id, str) or not record_id:
            raise ValueError("distractor requires a non-empty record_id")
        if not isinstance(text, str) or not text:
            raise ValueError(f"distractor {record_id} requires non-empty text")

        low = text.lower()
        people = re.findall(rf"\b({_PEOPLE})\b", text, flags=re.I)
        locations = re.findall(rf"\b({_LOCATIONS})\b", text, flags=re.I)
        objects = re.findall(rf"\b({_OBJECTS})s?\b", text, flags=re.I)
        entities = list(dict.fromkeys([*people, *objects, *locations]))
        values: dict[str, Any] = {"entities": entities}

        if "role reversal" in low:
            # Keep the predicate so role-constrained symbolic queries can
            # reject this hard negative rather than treating it as unrelated.
            values.update(
                predicate="approve",
                roles={"agent": people[0] if people else "reversed agent"},
                polarity="positive",
                modality="asserted",
                lifecycle_status="rejected",
            )
        elif "changed value" in low:
            number = re.search(r"\b(?:uses|claim uses)\s+(\d+)\b", low)
            values.update(
                predicate="approve",
                quantity=number.group(1) if number else None,
                polarity="positive",
                modality="asserted",
                lifecycle_status="rejected",
            )
        elif "stale status" in low:
            date = re.search(r"\b\d{4}-\d{2}-\d{2}\b", text)
            values.update(
                predicate="active",
                polarity="positive",
                valid_time=date.group(0) if date else None,
                lifecycle_status="obsolete",
                conflict_group=f"{objects[0] if objects else 'unknown'}:active",
            )
        elif "missing link" in low:
            target_match = re.search(r"\bfor\s+(?:a\s+)?([a-z][a-z -]+?)\s*\.?(?:$|\s)", low)
            target = target_match.group(1).strip() if target_match else (objects[0] if objects else "unknown")
            values.update(
                predicate="linked_to",
                relations=[
                    {"source": "similar record", "predicate": "linked_to", "target": target}
                ],
                lifecycle_status="rejected",
            )
            entities = list(dict.fromkeys([*entities, "similar record"]))
            values["entities"] = entities
        else:
            values["unresolved_slots"] = ["predicate"]

        pseudo_turn = {"turn_id": record_id, "speaker": "tool", "text": text}
        records.append(
            _base(
                pseudo_turn,
                1,
                record_id=record_id,
                source_turn_ids=[record_id],
                **values,
            )
        )
    return records


def build_representations(source_scenario: Any, track: str, representation_fixture: Any | None = None, ablate_primitive: str | None = None) -> list[dict[str, Any]]:
    """Build records from source or a separately frozen, source-bound oracle fixture."""
    source = _as_dict(source_scenario)
    if track not in {"oracle", "automatic"}:
        raise ValueError("track must be oracle or automatic")
    if track == "oracle":
        if representation_fixture is None:
            raise ValueError("oracle track requires a separate representation fixture")
        fixture = _as_dict(representation_fixture)
        if fixture.get("scenario_id") != source.get("scenario_id"):
            raise ValueError("oracle fixture is not bound to this source scenario")
        if fixture.get("source_sha256") and fixture["source_sha256"] != _hash_source(source):
            raise ValueError("oracle fixture source hash does not match")
        raw_by_turn = fixture.get("records_by_turn")
        if not isinstance(raw_by_turn, Mapping):
            raise ValueError("oracle fixture requires records_by_turn")
        turns = {turn["turn_id"]: turn for turn in source["turns"]}
        records = []
        for turn_id, raw_records in raw_by_turn.items():
            if turn_id not in turns:
                raise ValueError("oracle fixture cites an unknown source turn")
            records.extend(_base(turns[turn_id], ordinal, **_as_dict(raw)) for ordinal, raw in enumerate(raw_records, 1))
    else:
        records = [record for turn in source["turns"] for record in _automatic(_as_dict(turn))]
        _complete_temporal_links(records)
        _complete_lexical_context(records)
    if ablate_primitive:
        # ``role`` is the experiment primitive; ``roles`` is its storage field.
        # Accept both spellings because oracle diffing reports storage fields.
        ablation_field = {"role": "roles", "roles": "roles"}.get(ablate_primitive, ablate_primitive)
        for record in records:
            if ablation_field == "roles":
                record["roles"] = {}
            elif ablate_primitive == "provenance":
                record["provenance_status"] = None
            elif ablation_field in record:
                record[ablation_field] = [] if isinstance(record[ablation_field], list) else None
            else:
                raise ValueError(f"unknown primitive {ablate_primitive}")
            record["unresolved_slots"] = sorted(set(record["unresolved_slots"] + [ablate_primitive]))
    return records
