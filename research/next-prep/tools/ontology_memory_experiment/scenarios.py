from __future__ import annotations

from pathlib import Path
from typing import Any

from .io import canonical_json_bytes, write_json_immutable, write_manifest
from .models import (
    DistractorDocument,
    GoldDocument,
    OracleQueryPlanDocument,
    OracleRepresentationDocument,
    SourceDocument,
)
import hashlib


FAMILIES = (
    "roles_polarity_modality_quantity",
    "temporal_updates_conflicts_provenance",
    "conjunction_exact_set_multihop",
    "synonymy_sense_external_unanswerable",
)
SYSTEMS = ("mem0", "graphiti", "hindsight", "mempalace")
PEOPLE = ("Avery", "Blair", "Casey", "Devon", "Emery", "Flynn", "Gray", "Harper")
OBJECTS = ("archive", "invoice", "permit", "tablet", "shipment", "calendar", "report", "contract")
LOCATIONS = ("Boston", "Dublin", "Lisbon", "Oslo", "Reno", "Seoul", "Taipei", "Zurich")
COMPETENCIES = {
    FAMILIES[0]: (
        "agent_role", "patient_role", "source_role", "destination_role", "negation_scope",
        "explicit_negation", "requested_modality", "possible_modality", "conditional_modality",
        "exact_quantity", "threshold_quantity", "comparative_quantity", "count_identity",
        "role_quantity_binding", "role_abstention",
    ),
    FAMILIES[1]: (
        "valid_time_start", "valid_time_end", "transaction_time", "correction", "conflict",
        "supersession", "user_provenance", "tool_provenance", "agent_provenance", "current_state",
        "historical_state", "future_plan", "cancelled_state", "temporal_order", "temporal_abstention",
    ),
    FAMILIES[2]: (
        "two_way_conjunction", "three_way_conjunction", "exact_set", "set_exclusion", "two_hop_path",
        "three_hop_path", "shared_node", "relation_direction", "and_not_or", "joined_evidence",
        "bounded_path", "distinct_entities", "closed_set", "conjunction_abstention", "path_abstention",
    ),
    FAMILIES[3]: (
        "synonym_normalization", "sense_disambiguation", "ontology_external_term", "unanswerable_owner",
        "unanswerable_date", "alias_resolution", "polysemy", "subsumption", "lexical_paraphrase",
        "unresolved_entity", "uncovered_predicate", "abstention_with_evidence", "sense_with_provenance",
        "out_of_domain_wording", "unanswerable_relation",
    ),
}


def _assignment(family_index: int, local_index: int) -> tuple[str, str | None, str]:
    """Preserve 40/20 origin, 12/48 split, and directed-system coverage."""
    if local_index == 3:
        return "neutral", None, "dev"
    if local_index in (1, 2):
        return "architecture_directed", SYSTEMS[(family_index * 2 + local_index - 1) % 4], "dev"
    if local_index <= 11:
        return "architecture_directed", SYSTEMS[(local_index - 4) // 2], "hidden"
    return "neutral", None, "hidden"


def _scenario_text(
    family: str,
    competency: str,
    person: str,
    object_name: str,
    location: str,
    index: int,
    *,
    heldout: bool = False,
    hidden_variant: str = "v3",
) -> tuple[list[dict[str, str]], str, str, list[str], str, set[int], set[int]]:
    date = f"2026-0{(index % 8) + 1}-1{index % 9}"
    if family == FAMILIES[0]:
        primitive = ("role", "polarity", "modality", "quantity")[index % 4]
        if heldout and hidden_variant == "v5":
            turns = [
                {"speaker": "user", "text": f"{person} asked the clerk to approve exactly {index + 1} {object_name}s."},
                {"speaker": "agent", "text": f"The receiver approved {index + 2} {object_name}s, and the clerk was not that approver."},
                {"speaker": "user", "text": f"For {person}, the clerk may inspect exactly {index + 1} {object_name}s."},
                {"speaker": "agent", "text": f"The standing plan says the clerk is supposed to approve exactly {index + 1} {object_name}s for {person}."},
                {"speaker": "tool", "text": f"Another clerk approved {index + 2} {object_name}s for another person."},
            ]
            question = f"How many {object_name}s is the clerk supposed to approve for {person}?"
        elif heldout and hidden_variant == "v4":
            turns = [
                {"speaker": "user", "text": f"{person} requested that the clerk approve exactly {index + 1} {object_name}s."},
                {"speaker": "agent", "text": f"The receiver approved {index + 2} {object_name}s, and the clerk was not that approver."},
                {"speaker": "user", "text": f"For {person}, the clerk may review exactly {index + 1} {object_name}s."},
                {"speaker": "agent", "text": f"The standing instruction says the clerk should approve exactly {index + 1} {object_name}s for {person}."},
                {"speaker": "tool", "text": f"Another clerk approved {index + 2} {object_name}s for another person."},
            ]
            question = f"How many {object_name}s is the clerk expected to approve for {person}?"
        elif heldout:
            turns = [
                {"speaker": "user", "text": f"A {competency.replace('_', ' ')} request about {object_name}s was opened by {person}."},
                {"speaker": "agent", "text": f"The receiving party approved {index + 2} {object_name}s; the clerk was not the approving party."},
                {"speaker": "user", "text": f"For {person}, the clerk may review exactly {index + 1} {object_name}s."},
                {"speaker": "agent", "text": f"The active instruction says the clerk should approve exactly {index + 1} {object_name}s for {person}."},
                {"speaker": "tool", "text": f"A separate clerk is recorded approving {index + 2} {object_name}s for another person."},
            ]
            question = f"How many {object_name}s should the clerk approve for {person} in this request?"
        else:
            turns = [
                {"speaker": "user", "text": f"{person} opened a {competency.replace('_', ' ')} request about {object_name}s."},
                {"speaker": "agent", "text": f"The receiver approved {index + 2} {object_name}s; the clerk was not the approving party."},
                {"speaker": "user", "text": f"The clerk may review exactly {index + 1} {object_name}s for {person}."},
                {"speaker": "agent", "text": f"Current request: the clerk should approve exactly {index + 1} {object_name}s for {person}."},
                {"speaker": "tool", "text": f"A different clerk should approve {index + 2} {object_name}s for another person."},
            ]
            question = f"For the {competency.replace('_', ' ')} request, how many {object_name}s should the clerk approve for {person}?"
        return turns, question, str(index + 1), ["role", "modality", "quantity", primitive], primitive, {4}, {2, 5}
    if family == FAMILIES[1]:
        primitive = ("valid_time", "transaction_time", "provenance", "conflict", "supersession")[index % 5]
        if heldout and hidden_variant == "v5":
            turns = [
                {"speaker": "user", "text": f"On {date}, {person} said the {object_name} was active in {location}."},
                {"speaker": "tool", "text": f"Before the correction, the audit log recorded the {object_name} as active."},
                {"speaker": "user", "text": f"A correction superseded that note: the {object_name} is not active after {date}."},
                {"speaker": "agent", "text": f"Following the correction, current status is inactive after {date}; the earlier log remains provenance."},
                {"speaker": "tool", "text": f"An archived record says the {object_name} is active after {date}."},
                {"speaker": "agent", "text": "The update log records an active state after the correction."},
            ]
            question = f"Following the correction, is the {object_name} active after {date}?"
        elif heldout and hidden_variant == "v4":
            turns = [
                {"speaker": "user", "text": f"On {date}, {person} said the {object_name} was active in {location}."},
                {"speaker": "tool", "text": f"Before the correction, the audit log recorded the {object_name} as active."},
                {"speaker": "user", "text": f"A correction superseded that note: the {object_name} is not active after {date}."},
                {"speaker": "agent", "text": f"Current status is inactive after {date}; the earlier log remains provenance."},
                {"speaker": "tool", "text": f"An archived record says the {object_name} is active after {date}."},
                {"speaker": "agent", "text": "The update log records an active state after the correction."},
            ]
            question = f"Following the correction, is the {object_name} active after {date}?"
        elif heldout:
            turns = [
                {"speaker": "user", "text": f"A report dated {date} says that the {object_name} was active in {location}, according to {person}."},
                {"speaker": "tool", "text": f"Before the {competency.replace('_', ' ')} update, the log recorded the {object_name} as active."},
                {"speaker": "user", "text": f"A correction superseded that entry: the {object_name} is not active after {date}."},
                {"speaker": "agent", "text": f"Following the correction, the current status is inactive after {date}; the earlier tool entry remains provenance."},
                {"speaker": "tool", "text": f"An archived record lists the {object_name} as active after {date}."},
                {"speaker": "agent", "text": "The update log records an active state after the correction and labels it a new state."},
            ]
            question = f"Following the {competency.replace('_', ' ')} change, is the {object_name} active after {date}?"
        else:
            turns = [
                {"speaker": "user", "text": f"On {date}, {person} reported that the {object_name} was active in {location}."},
                {"speaker": "tool", "text": f"Recorded status before the {competency.replace('_', ' ')} update: the {object_name} was active."},
                {"speaker": "user", "text": f"Correction: the prior status is superseded and the {object_name} is not active after {date}."},
                {"speaker": "agent", "text": f"Current status is inactive after {date}; retain the prior tool record only as provenance."},
                {"speaker": "tool", "text": f"An obsolete record says the {object_name} remains active after {date}."},
                {"speaker": "agent", "text": "The correction is recorded as a new active state rather than a supersession."},
            ]
            question = f"After the {competency.replace('_', ' ')} update, is the {object_name} active after {date}?"
        return turns, question, "no", ["valid_time", "transaction_time", "provenance", "supersession", primitive], primitive, {2, 3, 4}, {5, 6}
    if family == FAMILIES[2]:
        primitive = ("conjunction", "exact_set", "traversal")[index % 3]
        if heldout and hidden_variant == "v5":
            turns = [
                {"speaker": "user", "text": f"For {competency.replace('_', ' ')}, {person} linked the {object_name} to {location} and archive."},
                {"speaker": "agent", "text": f"A similar {object_name} is linked only to {location}; the archive is not part of this record."},
                {"speaker": "tool", "text": f"The archive links {location} to project-{index:02d}."},
                {"speaker": "agent", "text": f"The exact set comprises {object_name}, {location}, archive, and project-{index:02d}."},
                {"speaker": "tool", "text": f"A separate archive links {location} to project-{index + 30:02d}."},
            ]
            question = f"Which project connects both the {object_name} and archive at {location}?"
        elif heldout and hidden_variant == "v4":
            turns = [
                {"speaker": "user", "text": f"For {competency.replace('_', ' ')}, {person} linked the {object_name} to {location} and the archive."},
                {"speaker": "agent", "text": f"A similar {object_name} is linked only to {location}; the archive is not part of this record."},
                {"speaker": "tool", "text": f"The archive links {location} to project-{index:02d}."},
                {"speaker": "agent", "text": f"The exact set includes {object_name}, {location}, archive, and project-{index:02d}."},
                {"speaker": "tool", "text": f"A separate archive links {location} to project-{index + 30:02d}."},
            ]
            question = f"Which project is shared by both the {object_name} and archive at {location}?"
        elif heldout:
            turns = [
                {"speaker": "user", "text": f"For {competency.replace('_', ' ')}, {person} connected the {object_name} to both {location} and the archive."},
                {"speaker": "agent", "text": f"A similar {object_name} links only to {location}; the archive is not part of that record."},
                {"speaker": "tool", "text": f"The archive links {location} to project-{index:02d}."},
                {"speaker": "agent", "text": f"Taken together, the exact set contains {object_name}, {location}, archive, and project-{index:02d}."},
                {"speaker": "tool", "text": f"A separate archive links {location} to project-{index + 30:02d}."},
            ]
            question = f"Which project is linked through both the {object_name} and archive at {location}?"
        else:
            turns = [
                {"speaker": "user", "text": f"{person} linked the {object_name} to both {location} and the archive for {competency.replace('_', ' ')}."},
                {"speaker": "agent", "text": f"A similar {object_name} is linked only to {location}; the archive is not part of that record."},
                {"speaker": "tool", "text": f"The archive links {location} to project-{index:02d}."},
                {"speaker": "agent", "text": f"The exact set is {object_name}, {location}, archive, and project-{index:02d}."},
                {"speaker": "tool", "text": f"A separate archive links {location} to project-{index + 30:02d}."},
            ]
            question = f"For {competency.replace('_', ' ')}, which project is linked through both the {object_name} and archive at {location}?"
        return turns, question, f"project-{index:02d}", ["conjunction", "exact_set", "traversal", primitive], primitive, {1, 3, 4}, {2, 5}
    unanswerable = index % 3 == 0
    primitive = "unanswerable" if unanswerable else ("sense" if index % 3 == 1 else "synonym")
    if heldout and hidden_variant == "v5":
        turns = [
            {"speaker": "user", "text": f"While in {location}, {person} used ledger for the {object_name} account."},
            {"speaker": "agent", "text": f"In this context, ledger means an account record rather than a travel schedule."},
            {"speaker": "user", "text": f"The account record was reviewed, but no owner or external relation was named."},
            {"speaker": "agent", "text": "The available evidence supports the accounting sense only; missing details remain unresolved."},
            {"speaker": "tool", "text": f"In a separate travel note, ledger means a travel schedule in {location}."},
            {"speaker": "agent", "text": f"{person} is listed as owner of the {object_name} account in {location}."},
        ]
    elif heldout and hidden_variant == "v4":
        turns = [
            {"speaker": "user", "text": f"While in {location}, {person} used ledger for the {object_name} account."},
            {"speaker": "agent", "text": f"In this context, ledger means an account record rather than a travel schedule."},
            {"speaker": "user", "text": f"The account record was reviewed, but no owner or external relation was named."},
            {"speaker": "agent", "text": "The available evidence supports the accounting sense only; missing details remain unresolved."},
            {"speaker": "tool", "text": f"In a separate travel note, ledger means a travel schedule in {location}."},
            {"speaker": "agent", "text": f"{person} is listed as owner of the {object_name} account in {location}."},
        ]
    elif heldout:
        turns = [
            {"speaker": "user", "text": f"While in {location}, {person} used ledger for the {object_name}."},
            {"speaker": "agent", "text": f"In this context, ledger denotes an account record rather than a travel schedule."},
            {"speaker": "user", "text": f"The account record was reviewed, but no owner or external relation was named."},
            {"speaker": "agent", "text": "The evidence supports the accounting sense only; the missing details remain unresolved."},
            {"speaker": "tool", "text": f"In another trip record, ledger denotes a travel schedule in {location}."},
            {"speaker": "agent", "text": f"{person} is listed as owner of the {object_name} account in {location}."},
        ]
    else:
        turns = [
            {"speaker": "user", "text": f"{person} called the {object_name} a ledger while visiting {location}."},
            {"speaker": "agent", "text": f"For {competency.replace('_', ' ')}, ledger here means an account record, not a travel schedule."},
            {"speaker": "user", "text": f"The account record was reviewed, but no owner or external relation was named."},
            {"speaker": "agent", "text": "The available turns support only the accounting sense and an abstention where details are absent."},
            {"speaker": "tool", "text": f"In another trip record, ledger denotes a travel schedule in {location}."},
            {"speaker": "agent", "text": f"{person} is listed as owner of the {object_name} account in {location}."},
        ]
    if unanswerable:
        return turns, f"For {competency.replace('_', ' ')}, who owns the {object_name} in {location}?", "", ["sense", "unanswerable", primitive], primitive, {1, 2, 3, 4}, {5, 6}
    return turns, f"For {competency.replace('_', ' ')}, which sense of {object_name} is supported in {location}?", "account record", ["synonym", "sense", primitive], primitive, {1, 2, 3, 4}, {5, 6}


def distractor_marker(primitive: str) -> str:
    return {
        "role": "receiver rather than sender",
        "polarity": "opposite truth value",
        "modality": "completed rather than requested",
        "quantity": "different exact count",
        "valid_time": "wrong validity date",
        "transaction_time": "wrong record order",
        "provenance": "wrong source status",
        "conflict": "unresolved contradiction",
        "supersession": "obsolete state retained",
        "conjunction": "one condition missing",
        "exact_set": "extra set member",
        "traversal": "wrong graph path",
        "synonym": "lexical near match",
        "sense": "wrong word sense",
        "unanswerable": "unsupported answer invented",
    }[primitive]


def _distractor_text(primitive: str, person: str, object_name: str, location: str, index: int, variant: int) -> str:
    """Return a natural assertion with one structural mutation, without gold labels."""
    date = f"2026-0{(index % 8) + 1}-1{index % 9}"
    count = index + variant
    alternatives = {
        "role": (
            f"A receiver handled the {object_name} for {person} in {location}.",
            f"The {object_name} was approved by a receiver for {person} in {location}.",
            f"In {location}, {person} assigned the {object_name} to a receiver.",
            f"The receiving party signed for the {object_name} in {location}.",
        ),
        "polarity": (
            f"The {object_name} remained active for {person} in {location}.",
            f"A status note says the {object_name} is active in {location}.",
            f"The record keeps an active state for {object_name} and {person}.",
            f"The {object_name} is listed as enabled in {location}.",
        ),
        "modality": (
            f"The clerk already approved the {object_name} for {person} in {location}.",
            f"A completed approval covers the {object_name} for {person}.",
            f"The {object_name} approval was carried out by the clerk in {location}.",
            f"The clerk recorded approval of the {object_name} for {person}.",
        ),
        "quantity": (
            f"The clerk approved {count} {object_name}s for {person} in {location}.",
            f"A receipt lists {count} {object_name}s for {person}.",
            f"The approval count for {object_name} is {count} in {location}.",
            f"{person} received {count} approved {object_name}s in {location}.",
        ),
        "valid_time": (
            f"An entry dated {date} places the {object_name} active in {location}.",
            f"The {object_name} is recorded as active after {date} in {location}.",
            f"A dated status note keeps {object_name} active in {location}.",
            f"The active {object_name} entry carries the date {date}.",
        ),
        "transaction_time": (
            f"The earlier log was recorded after the correction for {object_name} in {location}.",
            f"A later transaction entry reports the prior active state for {object_name}.",
            f"The transaction sequence places the old {object_name} status after the update.",
            f"The {object_name} record arrived after the correction in {location}.",
        ),
        "provenance": (
            f"The assistant reported the {object_name} active in {location}.",
            f"An agent note states that {object_name} remains active for {person}.",
            f"The {object_name} status comes from an assistant message in {location}.",
            f"A generated note records an active {object_name} for {person}.",
        ),
        "conflict": (
            f"The record leaves the {object_name} both active and inactive in {location}.",
            f"Two entries assign opposite statuses to the {object_name}.",
            f"The {object_name} timeline contains active and inactive reports.",
            f"A pair of status notes disagrees about {object_name} in {location}.",
        ),
        "supersession": (
            f"The earlier active entry for {object_name} remains in force after the correction.",
            f"The prior {object_name} status is still used after the update.",
            f"After the correction, the old active record remains current for {object_name}.",
            f"The {object_name} history continues to apply its earlier active entry.",
        ),
        "conjunction": (
            f"The {object_name} is linked to {location}.",
            f"A record connects {object_name} with the archive but not {location}.",
            f"The {object_name} appears beside {location} in one link.",
            f"The link record names only {object_name} and {location}.",
        ),
        "exact_set": (
            f"The set contains {object_name}, {location}, archive, and project-{index:02d}, plus another item.",
            f"An extra member is listed with {object_name}, {location}, archive, and project-{index:02d}.",
            f"The collection includes {object_name}, {location}, archive, project-{index:02d}, and one more entry.",
            f"The record expands the set beyond {object_name}, {location}, archive, and project-{index:02d}.",
        ),
        "traversal": (
            f"The archive resolves through {location} to project-{index + 30:02d}.",
            f"A path from the archive at {location} reaches project-{index + 30:02d}.",
            f"The archive link in {location} points to project-{index + 30:02d}.",
            f"A separate archive route ends at project-{index + 30:02d} via {location}.",
        ),
        "synonym": (
            f"Here ledger refers to a travel schedule in {location}.",
            f"In this note, ledger names a travel schedule near {location}.",
            f"The word ledger is used for a travel schedule in {location}.",
            f"A travel schedule is called a ledger in the {location} record.",
        ),
        "sense": (
            f"Here ledger refers to a travel schedule in {location}.",
            f"The ledger entry describes a travel schedule near {location}.",
            f"In this context, ledger means a travel schedule in {location}.",
            f"A travel schedule is the sense assigned to ledger in {location}.",
        ),
        "unanswerable": (
            f"{person} is listed as owner of the {object_name} account in {location}.",
            f"A note assigns the {object_name} account to {person} in {location}.",
            f"The {object_name} account belongs to {person} according to a record in {location}.",
            f"An entry names {person} as owner of {object_name} in {location}.",
        ),
    }
    return alternatives[primitive][variant % 4]


def ablation_field(primitive: str) -> str:
    return {
        "role": "roles",
        "polarity": "polarity",
        "modality": "modality",
        "quantity": "quantity",
        "valid_time": "valid_time",
        "transaction_time": "transaction_time",
        "provenance": "provenance_status",
        "conflict": "conflict_group",
        "supersession": "supersedes",
        "conjunction": "relations",
        "exact_set": "relations",
        "traversal": "relations",
        "synonym": "predicate",
        "sense": "predicate",
        "unanswerable": "absent_slots",
    }[primitive]


def project_oracle_answer(records: list[dict[str, Any]], plan: dict[str, Any]) -> dict[str, Any]:
    slot = plan["required_answer_slot"]
    if slot == "abstention":
        return {"kind": "unanswerable", "values": []}
    if slot == "quantity":
        return {"kind": "value", "values": [next(record["quantity"] for record in records if record["quantity"])]}
    if slot == "polarity":
        polarity = next(record["polarity"] for record in reversed(records) if record["polarity"] is not None)
        return {"kind": "value", "values": ["no" if polarity == "negative" else "yes"]}
    if slot == "project":
        for record in records:
            if "project" in record["roles"]:
                return {"kind": "value", "values": [record["roles"]["project"]]}
        for record in records:
            for relation in record["relations"]:
                if relation["predicate"] == "resolves_to":
                    return {"kind": "value", "values": [relation["target"]]}
    if slot == "sense":
        for record in records:
            if "sense" in record["roles"]:
                return {"kind": "value", "values": [record["roles"]["sense"]]}
    if slot == "owner" and any("owner" in record.get("absent_slots", []) for record in records):
        return {"kind": "unanswerable", "values": []}
    raise ValueError(f"accepted oracle evidence does not project {slot}")


def _oracle_turn_record(
    scenario_id: str,
    turn_id: str,
    text: str,
    family: str,
    person: str,
    object_name: str,
    location: str,
    local_index: int,
) -> dict[str, Any]:
    offset = int(turn_id[-2:])
    record_id = turn_id.replace("-T", "-R")
    common = {
        "record_id": record_id,
        "source_turn_ids": [turn_id],
        "surface_text": text,
        "entities": [],
        "predicate": None,
        "roles": {},
        "polarity": None,
        "modality": None,
        "quantity": None,
        "valid_time": None,
        "transaction_time": None,
        "provenance_status": "user_reported" if offset in (1, 3) else "agent_generated",
        "lifecycle_status": "supported",
        "conflict_group": None,
        "supersedes": [],
        "derived_from": [],
        "absent_slots": [],
        "relations": [],
    }
    if family == FAMILIES[0]:
        if offset == 1:
            common.update(
                entities=[person, object_name],
                predicate="open_request",
                roles={"requester": person, "object": object_name},
                polarity="positive",
                modality="asserted",
            )
        elif offset == 2:
            common.update(
                entities=["receiver", "clerk", object_name],
                predicate="approve",
                roles={"agent": "receiver", "excluded_agent": "clerk", "object": object_name},
                polarity="positive",
                modality="asserted",
                quantity=str(local_index + 2),
                lifecycle_status="rejected",
            )
        elif offset == 3:
            common.update(
                entities=["clerk", person, object_name],
                predicate="review",
                roles={"agent": "clerk", "beneficiary": person, "object": object_name},
                polarity="positive",
                modality="possible",
                quantity=str(local_index + 1),
            )
        elif offset == 4:
            common.update(
                entities=["clerk", person, object_name],
                predicate="approve",
                roles={"agent": "clerk", "beneficiary": person, "object": object_name},
                polarity="positive",
                modality="requested",
                quantity=str(local_index + 1),
                lifecycle_status="current",
            )
        else:
            common.update(
                entities=["different clerk", "another person", object_name],
                predicate="approve",
                roles={"agent": "different clerk", "beneficiary": "another person", "object": object_name},
                polarity="positive",
                modality="requested",
                quantity=str(local_index + 2),
                lifecycle_status="rejected",
            )
    elif family == FAMILIES[1]:
        lifecycle = {
            1: "historical",
            2: "historical",
            3: "current",
            4: "corroborating",
            5: "obsolete",
            6: "rejected",
        }[offset]
        common.update(
            entities=[object_name, location],
            predicate="active",
            roles={"subject": object_name, "location": location},
            polarity="negative" if offset in (3, 4) else "positive",
            valid_time="after-correction" if offset in (3, 4, 5, 6) else "before-correction",
            transaction_time=f"update-{offset}",
            provenance_status=(
                "tool_observed" if offset in (2, 5)
                else ("user_reported" if offset in (1, 3) else "agent_generated")
            ),
            lifecycle_status=lifecycle,
            conflict_group=f"{object_name}:active",
            supersedes=[f"{scenario_id}-R02"] if offset == 3 else [],
            derived_from=[f"{scenario_id}-R03"] if offset == 4 else [],
        )
    elif family == FAMILIES[2]:
        project = f"project-{local_index:02d}"
        if offset == 1:
            common.update(
                entities=[person, object_name, location, "archive"],
                predicate="linked_to",
                roles={"agent": person, "subject": object_name},
                relations=[
                    {"source": object_name, "predicate": "linked_to", "target": location},
                    {"source": object_name, "predicate": "linked_to", "target": "archive"},
                ],
            )
        elif offset == 2:
            similar_object = f"similar {object_name}"
            common.update(
                entities=[similar_object, location],
                predicate="linked_to",
                roles={"subject": similar_object},
                relations=[{"source": similar_object, "predicate": "linked_to", "target": location}],
                lifecycle_status="rejected",
            )
        elif offset == 3:
            common.update(
                entities=["archive", location, project],
                predicate="linked_to",
                roles={"subject": "archive"},
                relations=[
                    {"source": "archive", "predicate": "linked_to", "target": location},
                    {"source": "archive", "predicate": "resolves_to", "target": project},
                ],
            )
        elif offset == 4:
            common.update(
                entities=[object_name, location, "archive", project],
                predicate="exact_set",
                roles={"project": project},
                relations=[
                    {"source": "exact_set", "predicate": "contains", "target": value}
                    for value in (object_name, location, "archive", project)
                ],
                lifecycle_status="corroborating",
                derived_from=[f"{scenario_id}-R01", f"{scenario_id}-R03"],
            )
        else:
            wrong_project = f"project-{local_index + 30:02d}"
            common.update(
                entities=["unrelated archive", location, wrong_project],
                predicate="linked_to",
                roles={"subject": "unrelated archive"},
                relations=[
                    {"source": "unrelated archive", "predicate": "linked_to", "target": location},
                    {"source": "unrelated archive", "predicate": "resolves_to", "target": wrong_project},
                ],
                lifecycle_status="rejected",
            )
    else:
        common.update(entities=[object_name, location], polarity="positive")
        if offset == 1:
            common.update(
                entities=[person, object_name, "ledger", location],
                predicate="alias_of",
                roles={"term": object_name, "alias": "ledger"},
            )
        elif offset == 2:
            common.update(
                entities=[object_name, "ledger", "account record", location],
                predicate="sense_of",
                roles={"term": object_name, "sense": "account record"},
                provenance_status="agent_generated",
                derived_from=[f"{scenario_id}-R01"],
            )
        elif offset == 3:
            common.update(
                entities=[object_name, "account record", location],
                predicate="own",
                roles={"object": object_name},
                absent_slots=["owner", "external_relation"],
                derived_from=[f"{scenario_id}-R02"],
            )
        elif offset == 4:
            common.update(
                entities=[object_name, "account record", location],
                predicate="own",
                roles={"object": object_name},
                provenance_status="agent_generated",
                absent_slots=["owner", "external_relation"],
                derived_from=[f"{scenario_id}-R03"],
            )
        elif offset == 5:
            common.update(
                entities=["travel schedule", "different trip", location],
                predicate="sense_of",
                roles={"term": "ledger", "sense": "travel schedule"},
                lifecycle_status="rejected",
            )
        else:
            common.update(
                entities=[person, object_name, location],
                predicate="own",
                roles={"owner": person, "object": object_name},
                provenance_status="agent_generated",
                lifecycle_status="rejected",
            )
    return common


def _oracle_plan(family: str, competency: str, person: str, object_name: str, location: str, local_index: int) -> dict[str, Any]:
    if family == FAMILIES[0]:
        return {
            "entity_candidates": [person, object_name, "clerk"],
            "predicate": "approve",
            "role_constraints": {"agent": "clerk", "beneficiary": person, "object": object_name},
            "polarity": "positive",
            "modality": "requested",
            "required_answer_slot": "quantity",
            "declared_unresolved_slots": [],
        }
    if family == FAMILIES[1]:
        return {
            "entity_candidates": [object_name, location],
            "predicate": "active",
            "role_constraints": {"subject": object_name, "location": location},
            "time_filter": "after-correction",
            "status_filter": "current",
            "context_filter": f"{object_name}:active",
            "transaction_filter": "latest",
            "provenance_filter": "user_reported",
            "required_answer_slot": "polarity",
            "declared_unresolved_slots": [],
            "evidence_expansion": "provenance_closure",
            "require_supersession": True,
        }
    if family == FAMILIES[2]:
        return {
            "entity_candidates": [object_name, location, "archive"],
            "status_filter": "supported",
            "conjunction_groups": [[object_name, location, "archive"]],
            "traversal_steps": [
                {"source": object_name, "predicate": "linked_to", "target": "archive"},
                {"source": "archive", "predicate": "resolves_to", "target_slot": "project"},
            ],
            "required_answer_slot": "project",
            "declared_unresolved_slots": [],
            "evidence_expansion": "provenance_closure",
        }
    unanswerable = local_index % 3 == 0
    return {
        "entity_candidates": [object_name, location],
        "predicate": "own" if unanswerable else "sense_of",
        "role_constraints": {"object": object_name} if unanswerable else {"term": object_name},
        "status_filter": "supported",
        "required_answer_slot": "owner" if unanswerable else "sense",
        "declared_unresolved_slots": [],
        "evidence_expansion": "provenance_closure",
        "answer_policy": "require_explicit_absence" if unanswerable else "value_or_abstain",
    }


def _oracle_distractor_record(
    distractor: dict[str, Any],
    family: str,
    primitive: str,
    person: str,
    object_name: str,
    location: str,
    local_index: int,
) -> dict[str, Any]:
    """Create typed oracle semantics for a raw distractor without using gold answers."""
    record_id = str(distractor["record_id"])
    common: dict[str, Any] = {
        "record_id": record_id,
        "source_turn_ids": [record_id],
        "surface_text": str(distractor["text"]),
        "entities": [person, object_name, location],
        "predicate": None,
        "roles": {},
        "polarity": None,
        "modality": None,
        "quantity": None,
        "valid_time": None,
        "transaction_time": None,
        "provenance_status": "agent_generated",
        "lifecycle_status": "rejected",
        "conflict_group": None,
        "supersedes": [],
        "derived_from": [],
        "absent_slots": [],
        "relations": [],
    }
    if family == FAMILIES[0]:
        variant = int(record_id.rsplit("-", 1)[-1])
        common.update(
            predicate="approve",
            roles={
                "agent": "receiver" if primitive == "role" else "clerk",
                "beneficiary": person,
                "object": object_name,
            },
            polarity="negative" if primitive == "polarity" else "positive",
            modality="asserted" if primitive == "modality" else "requested",
            quantity=str(local_index + 1 + (variant % 3)) if primitive == "quantity" else str(local_index + 1),
        )
    elif family == FAMILIES[1]:
        common.update(
            entities=[object_name, location],
            predicate="active",
            roles={"subject": object_name, "location": location},
            polarity="positive" if primitive == "conflict" else "negative",
            valid_time="before-correction" if primitive == "valid_time" else "after-correction",
            transaction_time="update-1" if primitive == "transaction_time" else "update-5",
            provenance_status="tool_observed" if primitive == "provenance" else "agent_generated",
            lifecycle_status="obsolete",
            conflict_group=f"{object_name}:active" if primitive != "conflict" else f"{object_name}:other",
        )
    elif family == FAMILIES[2]:
        project = f"project-{local_index + 30:02d}"
        common.update(
            entities=[object_name, location, "archive", project],
            predicate="linked_to",
            roles={"subject": object_name},
            relations=[
                {"source": object_name, "predicate": "linked_to", "target": location}
            ]
            if primitive == "conjunction"
            else [
                {"source": "archive", "predicate": "resolves_to", "target": project}
            ],
        )
    else:
        common.update(
            entities=[object_name, location],
            predicate="wrong_sense" if primitive in {"sense", "synonym"} else "own",
            roles={"term": object_name, "sense": "travel schedule"},
        )
    return common


def _oracle_documents(
    source: dict[str, Any],
    gold: dict[str, Any],
    distractor_document: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    source_hash = hashlib.sha256(canonical_json_bytes(source)).hexdigest()
    representations: list[dict[str, Any]] = []
    plans: list[dict[str, Any]] = []
    distractors_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for distractor in distractor_document["records"]:
        distractors_by_key.setdefault(
            (str(distractor["scenario_id"]), str(distractor["distractor_scale"])), []
        ).append(distractor)
    for values in distractors_by_key.values():
        values.sort(key=lambda item: str(item["record_id"]))
    for scenario_number, (source_scenario, gold_scenario) in enumerate(zip(source["scenarios"], gold["scenarios"], strict=True), start=1):
        family = gold_scenario["family"]
        local_index = (scenario_number - 1) % 15 + 1
        person = PEOPLE[(scenario_number - 1) % len(PEOPLE)]
        object_name = OBJECTS[(scenario_number - 1) % len(OBJECTS)]
        location = LOCATIONS[(scenario_number - 1) % len(LOCATIONS)]
        records = [
            _oracle_turn_record(source_scenario["scenario_id"], turn["turn_id"], turn["text"], family, person, object_name, location, local_index)
            for turn in source_scenario["turns"]
        ]
        primitive = gold_scenario["ablation_primitive"]
        field = ablation_field(primitive)
        ablated_records = []
        for record in records:
            ablated = dict(record)
            ablated[field] = {} if field == "roles" else (
                [] if field in {"relations", "supersedes", "derived_from", "absent_slots"} else None
            )
            ablated_records.append(ablated)
        typed_distractors = {
            str(scale): [
                _oracle_distractor_record(
                    distractor,
                    family,
                    primitive,
                    person,
                    object_name,
                    location,
                    local_index,
                )
                for distractor in distractors_by_key[(source_scenario["scenario_id"], str(scale))]
            ]
            for scale in (50, 500)
        }
        representations.append({
            "scenario_id": source_scenario["scenario_id"],
            "records": records,
            "ablated_records": ablated_records,
            "distractor_records": typed_distractors,
        })
        plans.append({
            "scenario_id": source_scenario["scenario_id"],
            "query_plan": _oracle_plan(family, gold_scenario["competency"], person, object_name, location, local_index),
        })
    return (
        OracleRepresentationDocument(source_sha256=source_hash, scenarios=representations).model_dump(mode="json"),
        OracleQueryPlanDocument(source_sha256=source_hash, scenarios=plans).model_dump(mode="json"),
    )


def generate_experiment_documents(include_oracle: bool = False, hidden_variant: str = "v3") -> tuple[dict[str, Any], ...]:
    source_scenarios: list[dict[str, Any]] = []
    gold_scenarios: list[dict[str, Any]] = []
    distractors: list[dict[str, Any]] = []
    required_evidence_costs: list[int] = []
    scenario_number = 1
    for family_index, family in enumerate(FAMILIES):
        for local_index in range(1, 16):
            scenario_id = f"OME-S{scenario_number:03d}"
            person = PEOPLE[(scenario_number - 1) % len(PEOPLE)]
            object_name = OBJECTS[(scenario_number - 1) % len(OBJECTS)]
            location = LOCATIONS[(scenario_number - 1) % len(LOCATIONS)]
            origin, primary_system, split = _assignment(family_index, local_index)
            competency = COMPETENCIES[family][local_index - 1]
            turn_templates, question, answer, primitives, ablation_primitive, evidence_offsets, negative_offsets = _scenario_text(
                family,
                competency,
                person,
                object_name,
                location,
                local_index,
                heldout=local_index > 3,
                hidden_variant=hidden_variant,
            )
            turns = [
                {"turn_id": f"{scenario_id}-T{turn_index:02d}", **turn}
                for turn_index, turn in enumerate(turn_templates, start=1)
            ]
            source_scenarios.append({
                "scenario_id": scenario_id,
                "language": "en",
                "turns": turns,
                "question": question,
                # Filled with the shared maximum after all scenario templates
                # have been rendered below.
                "candidate_answer_budget": 1,
            })
            required_evidence_costs.append(
                sum(len(turn_templates[offset - 1]["text"].split()) for offset in evidence_offsets)
            )
            gold_scenarios.append({
                "scenario_id": scenario_id,
                "family": family,
                "origin": origin,
                "primary_system": primary_system,
                "split": split,
                "competency": competency,
                "answer": {"kind": "unanswerable" if not answer else "value", "values": [] if not answer else [answer]},
                "required_evidence_turn_ids": [f"{scenario_id}-T{offset:02d}" for offset in sorted(evidence_offsets)],
                "hard_negative_turn_ids": [f"{scenario_id}-T{offset:02d}" for offset in sorted(negative_offsets)],
                "required_primitives": primitives,
                "ablation_primitive": ablation_primitive,
                "critical_constraints": ["exact_structural_binding"],
                "architecture_claim_ids": (
                    [f"CLAIM-{primary_system.upper()}-001", f"RISK-{primary_system.upper()}-001"]
                    if primary_system else ["CLASS-ABLATION-001"]
                ),
                "proposed_ontology_remedy": "typed primitives with deterministic constraint execution",
                "falsifier": "A primitive ablation preserves the complete evidence set and answer.",
            })
            for scale in (50, 500):
                for distractor_index in range(1, scale + 1):
                    distractors.append({
                        "record_id": f"OME-D-S{scenario_number:03d}-{scale}-{distractor_index:03d}",
                        "scenario_id": scenario_id,
                        "distractor_scale": scale,
                        "text": _distractor_text(ablation_primitive, person, object_name, location, local_index, distractor_index),
                    })
            scenario_number += 1
    shared_candidate_answer_budget = max(required_evidence_costs)
    for scenario in source_scenarios:
        scenario["candidate_answer_budget"] = shared_candidate_answer_budget
    source = SourceDocument(scenarios=source_scenarios).model_dump(mode="json")
    gold = GoldDocument(scenarios=gold_scenarios).model_dump(mode="json")
    distractor_document = DistractorDocument(records=distractors).model_dump(mode="json")
    if include_oracle:
        oracle_representations, oracle_query_plans = _oracle_documents(source, gold, distractor_document)
        return source, gold, distractor_document, oracle_representations, oracle_query_plans
    return source, gold, distractor_document


def _v3_fallback_probe(
    scenario_number: int,
    *,
    split: str,
    object_name: str,
    location: str,
    person: str,
    codename: str,
    project: str,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    scenario_id = f"OME-S{scenario_number:03d}"
    turns = [
        {
            "turn_id": f"{scenario_id}-T01",
            "speaker": "user",
            "text": f"In {location}, {person} wrote that the {object_name} uses the codename {codename}.",
        },
        {
            "turn_id": f"{scenario_id}-T02",
            "speaker": "agent",
            "text": f"The {codename} note in {location} explicitly points to {project} for that {object_name}.",
        },
        {
            "turn_id": f"{scenario_id}-T03",
            "speaker": "tool",
            "text": f"A {codename} note in Zurich points to project-95 for an {object_name}.",
        },
        {
            "turn_id": f"{scenario_id}-T04",
            "speaker": "agent",
            "text": f"A {codename} note in {location} points to project-96 for an invoice.",
        },
        {
            "turn_id": f"{scenario_id}-T05",
            "speaker": "tool",
            "text": f"Another note says ledger means an account record in {location}.",
        },
    ]
    source = {
        "scenario_id": scenario_id,
        "language": "en",
        "turns": turns,
        "question": f"For fallback predicate recovery, which project does {codename} point to for the {object_name} in {location}?",
        "candidate_answer_budget": 1,
    }
    gold = {
        "scenario_id": scenario_id,
        "family": "synonymy_sense_external_unanswerable",
        "origin": "neutral",
        "primary_system": None,
        "split": split,
        "competency": (
            "fallback_probe_uncovered_predicate_dev"
            if split == "dev"
            else f"fallback_probe_uncovered_predicate_hidden_{scenario_number - 60}"
        ),
        "answer": {"kind": "value", "values": [project]},
        "required_evidence_turn_ids": [f"{scenario_id}-T01", f"{scenario_id}-T02"],
        "hard_negative_turn_ids": [f"{scenario_id}-T03", f"{scenario_id}-T04"],
        "required_primitives": ["synonym"],
        "ablation_primitive": "synonym",
        "critical_constraints": ["guarded_embedding_fallback", "entity_constraint_preservation"],
        "architecture_claim_ids": ["CLASS-ABLATION-001"],
        "proposed_ontology_remedy": "pre-declare uncovered predicate gaps and use embedding only to recover evidence candidates",
        "falsifier": "O+E either fails to trigger fallback or accepts a wrong-location or wrong-object project note.",
    }
    records = [
        {
            "record_id": f"{scenario_id}-R01",
            "source_turn_ids": [f"{scenario_id}-T01"],
            "surface_text": turns[0]["text"],
            "entities": [person, object_name, codename, location],
            "predicate": "alias_of",
            "roles": {"term": object_name, "alias": codename, "location": location},
            "polarity": "positive",
            "modality": "asserted",
            "quantity": None,
            "valid_time": None,
            "transaction_time": None,
            "provenance_status": "user_reported",
            "lifecycle_status": "supported",
            "conflict_group": None,
            "supersedes": [],
            "derived_from": [],
            "absent_slots": [],
            "relations": [],
        },
        {
            "record_id": f"{scenario_id}-R02",
            "source_turn_ids": [f"{scenario_id}-T02"],
            "surface_text": turns[1]["text"],
            "entities": [object_name, codename, location, project],
            "predicate": "points_to_project",
            "roles": {"object": object_name, "alias": codename, "location": location, "project": project},
            "polarity": "positive",
            "modality": "asserted",
            "quantity": None,
            "valid_time": None,
            "transaction_time": None,
            "provenance_status": "agent_generated",
            "lifecycle_status": "supported",
            "conflict_group": None,
            "supersedes": [],
            "derived_from": [f"{scenario_id}-R01"],
            "absent_slots": [],
            "relations": [{"source": codename, "predicate": "resolves_to", "target": project}],
        },
        {
            "record_id": f"{scenario_id}-R03",
            "source_turn_ids": [f"{scenario_id}-T03"],
            "surface_text": turns[2]["text"],
            "entities": [object_name, codename, "Zurich", "project-95"],
            "predicate": "points_to_project",
            "roles": {"object": object_name, "alias": codename, "location": "Zurich", "project": "project-95"},
            "polarity": "positive",
            "modality": "asserted",
            "quantity": None,
            "valid_time": None,
            "transaction_time": None,
            "provenance_status": "tool_observed",
            "lifecycle_status": "rejected",
            "conflict_group": None,
            "supersedes": [],
            "derived_from": [],
            "absent_slots": [],
            "relations": [{"source": codename, "predicate": "resolves_to", "target": "project-95"}],
        },
        {
            "record_id": f"{scenario_id}-R04",
            "source_turn_ids": [f"{scenario_id}-T04"],
            "surface_text": turns[3]["text"],
            "entities": ["invoice", codename, location, "project-96"],
            "predicate": "points_to_project",
            "roles": {"object": "invoice", "alias": codename, "location": location, "project": "project-96"},
            "polarity": "positive",
            "modality": "asserted",
            "quantity": None,
            "valid_time": None,
            "transaction_time": None,
            "provenance_status": "agent_generated",
            "lifecycle_status": "rejected",
            "conflict_group": None,
            "supersedes": [],
            "derived_from": [],
            "absent_slots": [],
            "relations": [{"source": codename, "predicate": "resolves_to", "target": "project-96"}],
        },
        {
            "record_id": f"{scenario_id}-R05",
            "source_turn_ids": [f"{scenario_id}-T05"],
            "surface_text": turns[4]["text"],
            "entities": ["ledger", "account record", location],
            "predicate": "sense_of",
            "roles": {"term": "ledger", "sense": "account record"},
            "polarity": "positive",
            "modality": "asserted",
            "quantity": None,
            "valid_time": None,
            "transaction_time": None,
            "provenance_status": "tool_observed",
            "lifecycle_status": "rejected",
            "conflict_group": None,
            "supersedes": [],
            "derived_from": [],
            "absent_slots": [],
            "relations": [],
        },
    ]
    ablated_records = [{**record, "predicate": None} for record in records]
    typed_distractors: dict[str, list[dict[str, Any]]] = {"50": [], "500": []}
    distractors: list[dict[str, Any]] = []
    variants = (
        (object_name, "Zurich", "project-95"),
        ("invoice", location, "project-96"),
        (object_name, "Reno", "project-97"),
        ("calendar", location, "project-98"),
    )
    for scale in (50, 500):
        for index in range(1, scale + 1):
            wrong_object, wrong_location, wrong_project = variants[index % len(variants)]
            distractor_id = f"OME-D-S{scenario_number:03d}-{scale}-{index:03d}"
            text = f"A {codename} note in {wrong_location} points to {wrong_project} for a {wrong_object}."
            distractors.append(
                {
                    "record_id": distractor_id,
                    "scenario_id": scenario_id,
                    "distractor_scale": scale,
                    "text": text,
                }
            )
            typed_distractors[str(scale)].append(
                {
                    "record_id": distractor_id,
                    "source_turn_ids": [distractor_id],
                    "surface_text": text,
                    "entities": [wrong_object, codename, wrong_location, wrong_project],
                    "predicate": "points_to_project",
                    "roles": {
                        "object": wrong_object,
                        "alias": codename,
                        "location": wrong_location,
                        "project": wrong_project,
                    },
                    "polarity": "positive",
                    "modality": "asserted",
                    "quantity": None,
                    "valid_time": None,
                    "transaction_time": None,
                    "provenance_status": "tool_observed",
                    "lifecycle_status": "rejected",
                    "conflict_group": None,
                    "supersedes": [],
                    "derived_from": [],
                    "absent_slots": [],
                    "relations": [{"source": codename, "predicate": "resolves_to", "target": wrong_project}],
                }
            )
    representation = {
        "scenario_id": scenario_id,
        "records": records,
        "ablated_records": ablated_records,
        "distractor_records": typed_distractors,
    }
    plan = {
        "scenario_id": scenario_id,
        "query_plan": {
            "entity_candidates": [object_name, location],
            "predicate": "points_to_project",
            "role_constraints": {"object": object_name, "location": location},
            "required_answer_slot": "project",
            "declared_unresolved_slots": [],
            "evidence_expansion": "provenance_closure",
        },
    }
    return source, gold, distractors, representation, plan


def _v4_fallback_probe(
    scenario_number: int,
    *,
    split: str,
    object_name: str,
    location: str,
    person: str,
    codename: str,
    project: str,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    scenario_id = f"OME-S{scenario_number:03d}"
    turns = [
        {
            "turn_id": f"{scenario_id}-T01",
            "speaker": "user",
            "text": f"In {location}, {person} noted that the {object_name} uses the codename {codename}.",
        },
        {
            "turn_id": f"{scenario_id}-T02",
            "speaker": "agent",
            "text": f"The {codename} note in {location} designates {project} for that {object_name}.",
        },
        {
            "turn_id": f"{scenario_id}-T03",
            "speaker": "tool",
            "text": f"A {codename} note in Zurich designates project-105 for an {object_name}.",
        },
        {
            "turn_id": f"{scenario_id}-T04",
            "speaker": "agent",
            "text": f"A {codename} note in {location} designates project-106 for an invoice.",
        },
        {
            "turn_id": f"{scenario_id}-T05",
            "speaker": "tool",
            "text": f"Another note says ledger means an account record in {location}.",
        },
    ]
    source = {
        "scenario_id": scenario_id,
        "language": "en",
        "turns": turns,
        "question": f"For fallback predicate recovery, which project does {codename} designate for the {object_name} in {location}?",
        "candidate_answer_budget": 1,
    }
    gold = {
        "scenario_id": scenario_id,
        "family": "synonymy_sense_external_unanswerable",
        "origin": "neutral",
        "primary_system": None,
        "split": split,
        "competency": (
            "fallback_probe_designate_dev"
            if split == "dev"
            else f"fallback_probe_designate_hidden_{scenario_number - 60}"
        ),
        "answer": {"kind": "value", "values": [project]},
        "required_evidence_turn_ids": [f"{scenario_id}-T01", f"{scenario_id}-T02"],
        "hard_negative_turn_ids": [f"{scenario_id}-T03", f"{scenario_id}-T04"],
        "required_primitives": ["synonym"],
        "ablation_primitive": "synonym",
        "critical_constraints": ["guarded_embedding_fallback", "entity_constraint_preservation"],
        "architecture_claim_ids": ["CLASS-ABLATION-001"],
        "proposed_ontology_remedy": "pre-declare uncovered predicate gaps and use embedding only to recover evidence candidates",
        "falsifier": "O+E either fails to trigger fallback or accepts a wrong-location or wrong-object project note.",
    }
    records = [
        {
            "record_id": f"{scenario_id}-R01",
            "source_turn_ids": [f"{scenario_id}-T01"],
            "surface_text": turns[0]["text"],
            "entities": [person, object_name, codename, location],
            "predicate": "alias_of",
            "roles": {"term": object_name, "alias": codename, "location": location},
            "polarity": "positive",
            "modality": "asserted",
            "quantity": None,
            "valid_time": None,
            "transaction_time": None,
            "provenance_status": "user_reported",
            "lifecycle_status": "supported",
            "conflict_group": None,
            "supersedes": [],
            "derived_from": [],
            "absent_slots": [],
            "relations": [],
        },
        {
            "record_id": f"{scenario_id}-R02",
            "source_turn_ids": [f"{scenario_id}-T02"],
            "surface_text": turns[1]["text"],
            "entities": [object_name, codename, location, project],
            "predicate": "points_to_project",
            "roles": {"object": object_name, "alias": codename, "location": location, "project": project},
            "polarity": "positive",
            "modality": "asserted",
            "quantity": None,
            "valid_time": None,
            "transaction_time": None,
            "provenance_status": "agent_generated",
            "lifecycle_status": "supported",
            "conflict_group": None,
            "supersedes": [],
            "derived_from": [f"{scenario_id}-R01"],
            "absent_slots": [],
            "relations": [{"source": codename, "predicate": "resolves_to", "target": project}],
        },
        {
            "record_id": f"{scenario_id}-R03",
            "source_turn_ids": [f"{scenario_id}-T03"],
            "surface_text": turns[2]["text"],
            "entities": [object_name, codename, "Zurich", "project-105"],
            "predicate": "points_to_project",
            "roles": {"object": object_name, "alias": codename, "location": "Zurich", "project": "project-105"},
            "polarity": "positive",
            "modality": "asserted",
            "quantity": None,
            "valid_time": None,
            "transaction_time": None,
            "provenance_status": "tool_observed",
            "lifecycle_status": "rejected",
            "conflict_group": None,
            "supersedes": [],
            "derived_from": [],
            "absent_slots": [],
            "relations": [{"source": codename, "predicate": "resolves_to", "target": "project-105"}],
        },
        {
            "record_id": f"{scenario_id}-R04",
            "source_turn_ids": [f"{scenario_id}-T04"],
            "surface_text": turns[3]["text"],
            "entities": ["invoice", codename, location, "project-106"],
            "predicate": "points_to_project",
            "roles": {"object": "invoice", "alias": codename, "location": location, "project": "project-106"},
            "polarity": "positive",
            "modality": "asserted",
            "quantity": None,
            "valid_time": None,
            "transaction_time": None,
            "provenance_status": "agent_generated",
            "lifecycle_status": "rejected",
            "conflict_group": None,
            "supersedes": [],
            "derived_from": [],
            "absent_slots": [],
            "relations": [{"source": codename, "predicate": "resolves_to", "target": "project-106"}],
        },
        {
            "record_id": f"{scenario_id}-R05",
            "source_turn_ids": [f"{scenario_id}-T05"],
            "surface_text": turns[4]["text"],
            "entities": ["ledger", "account record", location],
            "predicate": "sense_of",
            "roles": {"term": "ledger", "sense": "account record"},
            "polarity": "positive",
            "modality": "asserted",
            "quantity": None,
            "valid_time": None,
            "transaction_time": None,
            "provenance_status": "tool_observed",
            "lifecycle_status": "rejected",
            "conflict_group": None,
            "supersedes": [],
            "derived_from": [],
            "absent_slots": [],
            "relations": [],
        },
    ]
    ablated_records = [{**record, "predicate": None} for record in records]
    typed_distractors: dict[str, list[dict[str, Any]]] = {"50": [], "500": []}
    distractors: list[dict[str, Any]] = []
    variants = (
        (object_name, "Zurich", "project-205"),
        ("invoice", location, "project-206"),
        (object_name, "Reno", "project-207"),
        ("calendar", location, "project-208"),
    )
    for scale in (50, 500):
        for index in range(1, scale + 1):
            wrong_object, wrong_location, wrong_project = variants[index % len(variants)]
            distractor_id = f"OME-D-S{scenario_number:03d}-{scale}-{index:03d}"
            text = f"A {codename} note in {wrong_location} designates {wrong_project} for a {wrong_object}."
            distractors.append(
                {
                    "record_id": distractor_id,
                    "scenario_id": scenario_id,
                    "distractor_scale": scale,
                    "text": text,
                }
            )
            typed_distractors[str(scale)].append(
                {
                    "record_id": distractor_id,
                    "source_turn_ids": [distractor_id],
                    "surface_text": text,
                    "entities": [wrong_object, codename, wrong_location, wrong_project],
                    "predicate": "points_to_project",
                    "roles": {
                        "object": wrong_object,
                        "alias": codename,
                        "location": wrong_location,
                        "project": wrong_project,
                    },
                    "polarity": "positive",
                    "modality": "asserted",
                    "quantity": None,
                    "valid_time": None,
                    "transaction_time": None,
                    "provenance_status": "tool_observed",
                    "lifecycle_status": "rejected",
                    "conflict_group": None,
                    "supersedes": [],
                    "derived_from": [],
                    "absent_slots": [],
                    "relations": [{"source": codename, "predicate": "resolves_to", "target": wrong_project}],
                }
            )
    representation = {
        "scenario_id": scenario_id,
        "records": records,
        "ablated_records": ablated_records,
        "distractor_records": typed_distractors,
    }
    plan = {
        "scenario_id": scenario_id,
        "query_plan": {
            "entity_candidates": [object_name, location],
            "predicate": "points_to_project",
            "role_constraints": {"object": object_name, "location": location},
            "required_answer_slot": "project",
            "declared_unresolved_slots": ["predicate"],
            "evidence_expansion": "provenance_closure",
        },
    }
    return source, gold, distractors, representation, plan


def _v5_fallback_probe(
    scenario_number: int,
    *,
    split: str,
    object_name: str,
    location: str,
    person: str,
    codename: str,
    project: str,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    source, gold, distractors, representation, plan = _v4_fallback_probe(
        scenario_number,
        split=split,
        object_name=object_name,
        location=location,
        person=person,
        codename=codename,
        project=project,
    )
    source["question"] = (
        f"For fallback predicate recovery, which project does {codename} route for the "
        f"{object_name} in {location}?"
    )
    gold["competency"] = (
        "fallback_probe_route_dev"
        if split == "dev"
        else f"fallback_probe_route_hidden_{scenario_number - 60}"
    )
    for turn in source["turns"]:
        turn["text"] = turn["text"].replace("designates", "routes")
    for distractor in distractors:
        distractor["text"] = distractor["text"].replace("designates", "routes")
    for record in representation["records"]:
        record["surface_text"] = record["surface_text"].replace("designates", "routes")
    for records in representation["distractor_records"].values():
        for record in records:
            record["surface_text"] = record["surface_text"].replace("designates", "routes")
    return source, gold, distractors, representation, plan


def generate_v3_experiment_documents(include_oracle: bool = False) -> tuple[dict[str, Any], ...]:
    source, gold, distractors, oracle_representations, oracle_query_plans = generate_experiment_documents(include_oracle=True, hidden_variant="v3")
    probes = [
        _v3_fallback_probe(61, split="dev", object_name="archive", location="Boston", person="Avery", codename="quasar", project="project-91"),
        _v3_fallback_probe(62, split="hidden", object_name="permit", location="Dublin", person="Blair", codename="umbra", project="project-92"),
        _v3_fallback_probe(63, split="hidden", object_name="report", location="Seoul", person="Casey", codename="nova", project="project-93"),
        _v3_fallback_probe(64, split="hidden", object_name="contract", location="Taipei", person="Devon", codename="rivet", project="project-94"),
    ]
    for probe_source, probe_gold, probe_distractors, probe_representation, probe_plan in probes:
        source["scenarios"].append(probe_source)
        gold["scenarios"].append(probe_gold)
        distractors["records"].extend(probe_distractors)
        oracle_representations["scenarios"].append(probe_representation)
        oracle_query_plans["scenarios"].append(probe_plan)
    shared_candidate_answer_budget = max(
        scenario["candidate_answer_budget"] for scenario in source["scenarios"][:60]
    )
    for scenario in source["scenarios"]:
        scenario["candidate_answer_budget"] = shared_candidate_answer_budget
    source = SourceDocument.model_validate(source).model_dump(mode="json")
    gold = GoldDocument.model_validate(gold).model_dump(mode="json")
    distractors = DistractorDocument.model_validate(distractors).model_dump(mode="json")
    source_hash = hashlib.sha256(canonical_json_bytes(source)).hexdigest()
    oracle_representations["source_sha256"] = source_hash
    oracle_query_plans["source_sha256"] = source_hash
    oracle_representations = OracleRepresentationDocument.model_validate(oracle_representations).model_dump(mode="json")
    oracle_query_plans = OracleQueryPlanDocument.model_validate(oracle_query_plans).model_dump(mode="json")
    if include_oracle:
        return source, gold, distractors, oracle_representations, oracle_query_plans
    return source, gold, distractors


def generate_v4_experiment_documents(include_oracle: bool = False) -> tuple[dict[str, Any], ...]:
    source, gold, distractors, oracle_representations, oracle_query_plans = generate_experiment_documents(include_oracle=True, hidden_variant="v4")
    probes = [
        _v4_fallback_probe(61, split="dev", object_name="archive", location="Boston", person="Avery", codename="atlas", project="project-101"),
        _v4_fallback_probe(62, split="hidden", object_name="permit", location="Dublin", person="Blair", codename="beryl", project="project-102"),
        _v4_fallback_probe(63, split="hidden", object_name="report", location="Seoul", person="Casey", codename="cinder", project="project-103"),
        _v4_fallback_probe(64, split="hidden", object_name="contract", location="Taipei", person="Devon", codename="delta", project="project-104"),
    ]
    for probe_source, probe_gold, probe_distractors, probe_representation, probe_plan in probes:
        source["scenarios"].append(probe_source)
        gold["scenarios"].append(probe_gold)
        distractors["records"].extend(probe_distractors)
        oracle_representations["scenarios"].append(probe_representation)
        oracle_query_plans["scenarios"].append(probe_plan)
    shared_candidate_answer_budget = max(
        scenario["candidate_answer_budget"] for scenario in source["scenarios"][:60]
    )
    for scenario in source["scenarios"]:
        scenario["candidate_answer_budget"] = shared_candidate_answer_budget
    source = SourceDocument.model_validate(source).model_dump(mode="json")
    gold = GoldDocument.model_validate(gold).model_dump(mode="json")
    distractors = DistractorDocument.model_validate(distractors).model_dump(mode="json")
    source_hash = hashlib.sha256(canonical_json_bytes(source)).hexdigest()
    oracle_representations["source_sha256"] = source_hash
    oracle_query_plans["source_sha256"] = source_hash
    oracle_representations = OracleRepresentationDocument.model_validate(oracle_representations).model_dump(mode="json")
    oracle_query_plans = OracleQueryPlanDocument.model_validate(oracle_query_plans).model_dump(mode="json")
    if include_oracle:
        return source, gold, distractors, oracle_representations, oracle_query_plans
    return source, gold, distractors


def generate_v5_experiment_documents(include_oracle: bool = False) -> tuple[dict[str, Any], ...]:
    source, gold, distractors, oracle_representations, oracle_query_plans = generate_experiment_documents(include_oracle=True, hidden_variant="v5")
    probes = [
        _v5_fallback_probe(61, split="dev", object_name="archive", location="Boston", person="Avery", codename="orion", project="project-111"),
        _v5_fallback_probe(62, split="hidden", object_name="permit", location="Dublin", person="Blair", codename="jasper", project="project-112"),
        _v5_fallback_probe(63, split="hidden", object_name="report", location="Seoul", person="Casey", codename="kepler", project="project-113"),
        _v5_fallback_probe(64, split="hidden", object_name="contract", location="Taipei", person="Devon", codename="lumen", project="project-114"),
    ]
    for probe_source, probe_gold, probe_distractors, probe_representation, probe_plan in probes:
        source["scenarios"].append(probe_source)
        gold["scenarios"].append(probe_gold)
        distractors["records"].extend(probe_distractors)
        oracle_representations["scenarios"].append(probe_representation)
        oracle_query_plans["scenarios"].append(probe_plan)
    shared_candidate_answer_budget = max(
        scenario["candidate_answer_budget"] for scenario in source["scenarios"][:60]
    )
    for scenario in source["scenarios"]:
        scenario["candidate_answer_budget"] = shared_candidate_answer_budget
    source = SourceDocument.model_validate(source).model_dump(mode="json")
    gold = GoldDocument.model_validate(gold).model_dump(mode="json")
    distractors = DistractorDocument.model_validate(distractors).model_dump(mode="json")
    source_hash = hashlib.sha256(canonical_json_bytes(source)).hexdigest()
    oracle_representations["source_sha256"] = source_hash
    oracle_query_plans["source_sha256"] = source_hash
    oracle_representations = OracleRepresentationDocument.model_validate(oracle_representations).model_dump(mode="json")
    oracle_query_plans = OracleQueryPlanDocument.model_validate(oracle_query_plans).model_dump(mode="json")
    if include_oracle:
        return source, gold, distractors, oracle_representations, oracle_query_plans
    return source, gold, distractors


def write_frozen_gold(output_dir: Path, version: str = "v2") -> dict[str, Any]:
    if version == "v2":
        source, gold, distractors, oracle_representations, oracle_query_plans = generate_experiment_documents(include_oracle=True)
    elif version == "v3":
        source, gold, distractors, oracle_representations, oracle_query_plans = generate_v3_experiment_documents(include_oracle=True)
    elif version == "v4":
        source, gold, distractors, oracle_representations, oracle_query_plans = generate_v4_experiment_documents(include_oracle=True)
    elif version == "v5":
        source, gold, distractors, oracle_representations, oracle_query_plans = generate_v5_experiment_documents(include_oracle=True)
    else:
        raise ValueError("gold version must be v2, v3, v4, or v5")
    source_path = output_dir / "source-scenarios.json"
    gold_path = output_dir / "gold.json"
    distractor_path = output_dir / "distractors.json"
    oracle_representation_path = output_dir / "oracle-representations.json"
    oracle_query_plan_path = output_dir / "oracle-query-plans.json"
    write_json_immutable(source_path, source)
    write_json_immutable(gold_path, gold)
    write_json_immutable(distractor_path, distractors)
    write_json_immutable(oracle_representation_path, oracle_representations)
    write_json_immutable(oracle_query_plan_path, oracle_query_plans)
    return write_manifest(output_dir / "manifest.json", {
        "source": source_path,
        "gold": gold_path,
        "distractors": distractor_path,
        "oracle_representations": oracle_representation_path,
        "oracle_query_plans": oracle_query_plan_path,
    })
