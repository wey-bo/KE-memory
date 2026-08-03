"""The four O_v3 families as ontology content, built from collected evidence.

Each item's aliases come from :mod:`ke_memory_demo.ontology_v3.evidence`, which reads independent
corpora only. Nothing here is hand-tuned toward the cases that exposed the gap.

The separations the ruling required are structural rather than documented:

``held_value`` and ``held_belief`` are distinct items with distinct predicates and senses. They are
never a single generalised entry, because a merged item would have to drop either the strength
qualifier that only values take or the modality slot that only beliefs take. Two items keep both.

``activity_or_pursuit`` splits into an event and a state. Hosting a party once and practising yoga
ongoingly are different claims about memory, and one type cannot carry both without losing whether
the thing recurs.

``positive_capability_or_skill`` is authored rather than imported. PropBank's ``can.01`` means "put
into tins", so the modal sense has no roleset and there is nothing to ground it in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .evidence import FamilyEvidence

V3_VERSION = "3.0.0"
SUPERSEDES = "2.0.0"


@dataclass(frozen=True)
class V3Role:
    """A role an item takes, and whether it must be filled."""

    role_id: str
    is_required: bool
    note: str = ""

    def as_json(self) -> dict[str, Any]:
        return {
            "role_id": self.role_id,
            "is_required": self.is_required,
            "note": self.note,
        }


@dataclass(frozen=True)
class V3Item:
    """One new ontology item, with the evidence that admitted it."""

    item_id: str
    item_type: str
    sense: str
    aliases: tuple[str, ...]
    roles: tuple[V3Role, ...]
    qualifiers: tuple[str, ...]
    admitted_on: str
    evidence_family: str
    evidence_occurrences: int
    constraints: tuple[str, ...] = ()

    def as_json(self) -> dict[str, Any]:
        return {
            "id": self.item_id,
            "item_type": self.item_type,
            "sense": self.sense,
            "aliases": list(self.aliases),
            "roles": [r.as_json() for r in self.roles],
            "qualifiers": list(self.qualifiers),
            "admitted_on": self.admitted_on,
            "evidence_family": self.evidence_family,
            "evidence_occurrences": self.evidence_occurrences,
            "constraints": list(self.constraints),
        }


# Roles the new items need. Reused from v2 where v2 already has them; the two new ones are named here
# because no v2 role expresses them.
ROLE_SUBJECT = "l1:role.attribute_bearer"
ROLE_PARTICIPANT = "l1:role.participant"
ROLE_TOPIC = "l1:role.topic"
ROLE_CONTENT = "l1:role.proposition_content"


def build_items(families: tuple[FamilyEvidence, ...]) -> tuple[V3Item, ...]:
    """The six new items across the four ruled families."""
    by_family = {family.family: family for family in families}
    activity = by_family["activity_or_pursuit"]
    capability = by_family["positive_capability_or_skill"]
    value = by_family["held_value"]
    belief = by_family["held_belief"]

    items: list[V3Item] = [
        # --- activity_or_pursuit: an occurrence and an ongoing practice are separate claims ------
        V3Item(
            item_id="l1:event.activity_occurrence",
            item_type="event_type",
            sense=(
                "a bounded occasion the subject took part in: hosting, attending, performing or "
                "making something on a particular occasion"
            ),
            aliases=activity.aliases,
            roles=(
                V3Role(ROLE_SUBJECT, True, "who took part"),
                V3Role(ROLE_PARTICIPANT, False, "others present, when stated"),
                V3Role(ROLE_TOPIC, False, "what the activity was about"),
            ),
            qualifiers=("l1:time.before_assertion", "l1:time.at_assertion"),
            admitted_on="frequency",
            evidence_family=activity.family,
            evidence_occurrences=activity.total_occurrences,
            constraints=(
                "an occurrence is a single occasion. Repeated behaviour by the same subject is "
                "l1:state.ongoing_pursuit, and conflating them loses whether the thing recurs.",
            ),
        ),
        V3Item(
            item_id="l1:state.ongoing_pursuit",
            item_type="state_type",
            sense=(
                "an activity the subject practises on a continuing basis: a hobby, a discipline or a "
                "creative practice"
            ),
            aliases=activity.aliases,
            roles=(
                V3Role(ROLE_SUBJECT, True, "who practises it"),
                V3Role(ROLE_TOPIC, False, "the domain of the practice"),
            ),
            qualifiers=("l1:qualifier.frequency", "l1:time.spanning"),
            admitted_on="frequency",
            evidence_family=activity.family,
            evidence_occurrences=activity.total_occurrences,
            constraints=(
                "a pursuit outlives any one occasion, so it is not attested by a single occurrence "
                "without a frequency or duration qualifier.",
            ),
        ),
        # --- positive_capability_or_skill: authored, because PropBank has no modal sense ---------
        V3Item(
            item_id="l1:state.capability",
            item_type="state_type",
            sense="something the subject is able to do, knows how to do, or is competent at",
            aliases=capability.aliases,
            roles=(
                V3Role(ROLE_SUBJECT, True, "who holds the capability"),
                V3Role(ROLE_TOPIC, False, "what the capability is over"),
            ),
            qualifiers=("l1:qualifier.degree",),
            admitted_on="structural_gap",
            evidence_family=capability.family,
            evidence_occurrences=capability.total_occurrences,
            constraints=(
                "the polar opposite of l1:state.capability_constraint, which types only what a "
                "subject cannot do. The two must not be merged into one signed type: a stated "
                "inability and a stated ability are separately memory-worthy.",
                "authored rather than imported: PropBank can.01 means 'put into tins' and can.02 is "
                "metaphorical throwing, so the modal sense has no roleset to ground it in.",
            ),
        ),
        # --- held_value: separate from belief, carries strength ----------------------------------
        V3Item(
            item_id="l1:predicate.hold_value",
            item_type="predicate_sense",
            sense=(
                "the subject treats something as important or as a priority: a property of the "
                "subject rather than an evaluation of the object"
            ),
            aliases=value.aliases,
            roles=(
                V3Role(ROLE_SUBJECT, True, "whose value it is"),
                V3Role(ROLE_TOPIC, True, "what is valued"),
            ),
            # Strength is attested: 18 MSC sentences carry an intensity marker.
            qualifiers=("l1:qualifier.degree", "l1:source_status.user_reported"),
            admitted_on="expressibility",
            evidence_family=value.family,
            evidence_occurrences=value.total_occurrences,
            constraints=(
                "must not be merged with l1:predicate.hold_belief. A value takes a strength "
                "qualifier and a belief takes an assertion modality; one merged item would have to "
                "drop one of them.",
                "distinct from l1:attribute.assessment, which rates how good an object is. That is a "
                "claim about the object; this is a claim about the subject.",
                "distinct from l1:preference.affinity, which is liking. Treating something as "
                "important is not the same as enjoying it.",
            ),
        ),
        # --- held_belief: separate from value, carries modality ----------------------------------
        V3Item(
            item_id="l1:predicate.hold_belief",
            item_type="predicate_sense",
            sense=(
                "the subject holds a general claim about how the world is, as distinct from a report "
                "of a particular fact"
            ),
            aliases=belief.aliases,
            roles=(
                V3Role(ROLE_SUBJECT, True, "whose belief it is"),
                V3Role(ROLE_CONTENT, True, "the proposition believed"),
            ),
            # Modality is a declared slot with no corpus support: MSC carries zero explicit markers,
            # so populating graded values would be fabricating coverage.
            qualifiers=("l1:modality.believed", "l1:source_status.user_reported"),
            admitted_on="expressibility",
            evidence_family=belief.family,
            evidence_occurrences=belief.total_occurrences,
            constraints=(
                "must not be merged with l1:predicate.hold_value, for the same reason in reverse: "
                "modality belongs to the belief and strength to the value.",
                "the content is a general claim. A report of a particular fact is an ordinary "
                "assertion and does not need this type.",
                "assertion modality is declared but unattested: MSC carries no explicit modality "
                "marker, so no graded value set is supplied.",
            ),
        ),
    ]
    return tuple(items)


def build_new_roles() -> tuple[dict[str, Any], ...]:
    """Roles v2 lacks. Kept minimal: three, each needed by an item above."""
    return (
        {
            "id": ROLE_PARTICIPANT,
            "item_type": "role",
            "sense": "another party present at or taking part in an activity",
            "needed_by": ["l1:event.activity_occurrence"],
        },
        {
            "id": ROLE_TOPIC,
            "item_type": "role",
            "sense": "what an activity, capability or value is about",
            "needed_by": [
                "l1:event.activity_occurrence",
                "l1:state.ongoing_pursuit",
                "l1:state.capability",
                "l1:predicate.hold_value",
            ],
        },
        {
            "id": ROLE_CONTENT,
            "item_type": "role",
            "sense": "the proposition a belief is about",
            "needed_by": ["l1:predicate.hold_belief"],
        },
    )


def build_l2_additions() -> tuple[dict[str, Any], ...]:
    """L2 items the new L1 content makes derivable, with their derivation rules.

    Only two, and both require several L1 sources. An abstraction that needs one source is not an
    abstraction; it is a rename.
    """
    return (
        {
            "id": "l2:abstraction.pursuit_profile",
            "item_type": "abstraction_type",
            "sense": "what the subject does with their time, across occasions and practices",
            "l1_source_ids": [
                "l1:event.activity_occurrence",
                "l1:state.ongoing_pursuit",
                "l1:qualifier.frequency",
            ],
            "evidence_required": 2,
            "kind": "abstracts_from",
        },
        {
            "id": "l2:abstraction.value_commitment",
            "item_type": "abstraction_type",
            "sense": (
                "a standing commitment the subject holds, evidenced by a stated value together with "
                "behaviour consistent with it"
            ),
            "l1_source_ids": [
                "l1:predicate.hold_value",
                "l1:predicate.hold_belief",
                "l1:state.ongoing_pursuit",
            ],
            "evidence_required": 2,
            "kind": "abstracts_from",
        },
    )
