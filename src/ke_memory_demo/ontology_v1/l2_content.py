"""O_L2: the cross-turn and cross-session abstraction layer.

An L2 item is not a longer-lived L1 item. It is a structure that no single observation can
witness, and the evidence for admitting one is a *measured multi-observation phenomenon* in
the build corpora rather than a plausible-sounding structure:

- 10739 of 16142 SGD dialogues touch more than one service (2: 8266, 3: 2185, 4: 288), so
  an intention spanning several sub-goals is the majority case, not a special case. That
  measurement is what ``l2:abstraction.project`` rests on.
- Among multi-service dialogues, 86.4% carry a slot value shared across two services --
  ``city`` 2238, ``location`` 1711, ``destination_city`` 1672 -- so a constraint stated once
  and reused across sub-goals is attested. That is ``l2:abstraction.carried_constraint``.
- 3661 of 5110 dialogues (71.6%) revise a user slot value mid-dialogue. Reconstructing which
  value holds now requires the whole revision series: ``l2:abstraction.value_history``.
- Sequences of SGD service pairs recur (Restaurants+Movies 247, Homes+Calendar 235,
  Events+Restaurants 233+232), so a recurring co-occurrence pattern is measurable. But note
  what that is *not* evidence for: see the ``habit`` discussion below.

The layer deliberately shares no vocabulary with O_L1. ``l2:abstraction.preference_profile``
is not ``l1:preference.affinity`` with a longer life; it is a ranked set over many affinity
observations, and it can hold when no single affinity observation is decisive. The
:class:`~ke_memory_demo.ontology_v1.models.MappingFreeze` unit carries every derivation.
"""

from __future__ import annotations

from typing import Final

from .models import (
    Constraint,
    L2Freeze,
    L2Item,
    L2ItemType,
    OntologyRoleKind,
    Provenance,
    Relation,
    RelationKind,
    RoleSlot,
    SourceKind,
    OntologyItem,
)

O_L2_VERSION: Final[str] = "1.0.0"


def _l2(
    item_id: str,
    item_type: L2ItemType,
    sense: str,
    *,
    role_kind: OntologyRoleKind = OntologyRoleKind.CONCEPT,
    aliases: tuple[str, ...] = (),
    relations: tuple[Relation, ...] = (),
    roles: tuple[RoleSlot, ...] = (),
    constraints: tuple[Constraint, ...] = (),
    minimum_support: int = 1,
    spans_sessions: bool = False,
    provenance: tuple[Provenance, ...],
) -> L2Item:
    return L2Item(
        item=OntologyItem(
            id=item_id,
            sense=sense,
            aliases=aliases,
            role_kind=role_kind,
            relations=relations,
            roles=roles,
            constraints=constraints,
            provenance=provenance,
        ),
        item_type=item_type,
        minimum_support=minimum_support,
        spans_sessions=spans_sessions,
    )


def _sgd_multi(evidence: str) -> tuple[Provenance, ...]:
    return (Provenance(source=SourceKind.SGD_STATE_DYNAMICS, evidence=evidence),)


def _sgd_schema(evidence: str) -> tuple[Provenance, ...]:
    return (Provenance(source=SourceKind.SGD_SCHEMA, evidence=evidence),)


def _msc(evidence: str) -> tuple[Provenance, ...]:
    return (Provenance(source=SourceKind.MSC_PERSONAS, evidence=evidence),)


def _tau(evidence: str) -> tuple[Provenance, ...]:
    return (Provenance(source=SourceKind.TAU_BENCH_POLICY, evidence=evidence),)


def _repo(evidence: str) -> tuple[Provenance, ...]:
    return (Provenance(source=SourceKind.REPOSITORY_VOCABULARY, evidence=evidence),)


def _gap(evidence: str) -> tuple[Provenance, ...]:
    """A general gap shape from the discovery split.

    What may be cited is the shape and its count -- 225 of 227 observations were tagged
    partial_gold_overlap, 1 empty_selection, 1 gold_delivery_over_limit -- and nothing about
    any question, any label or which corpus the items came from. That is the whole of what
    the discovery rule permits, and it is enough to justify a *kind* of abstraction without
    telling us anything about a sample.
    """
    return (Provenance(source=SourceKind.DISCOVERY_GAP_SHAPE, evidence=evidence),)


# --- Aggregation patterns ----------------------------------------------------------------
#
# These come first because every abstraction type points at one. They are items rather than
# an enum so that a pattern carries its own sense and constraints: "this abstraction is a
# temporal series" is a claim about how to compute it, and it needs to be as reviewable as
# the abstraction it computes.
_PATTERNS: Final[tuple[L2Item, ...]] = (
    _l2(
        "l2:pattern.temporal_series",
        L2ItemType.AGGREGATION_PATTERN,
        "order observations about one subject and attribute by time, keeping the whole series",
        aliases=("history", "timeline", "series over time"),
        constraints=(
            Constraint(
                kind="order_is_the_content",
                expression=(
                    "the series is not a set: reordering changes which value is current, so "
                    "an implementation that collapses to the latest value has lost the item"
                ),
            ),
        ),
        minimum_support=2,
        provenance=_sgd_multi(
            "71.6% of 5110 dialogues revise a slot value at least once, so a series of "
            "two or more values for one attribute is the normal observation"
        ),
    ),
    _l2(
        "l2:pattern.recurrence_count",
        L2ItemType.AGGREGATION_PATTERN,
        "count how many separate observations instantiate the same type, over distinct occasions",
        aliases=("frequency", "how often", "repeat count"),
        constraints=(
            Constraint(
                kind="distinct_occasions_required",
                expression=(
                    "two mentions of one occurrence are one observation, not two. Counting "
                    "mentions instead of occasions inflates every frequency claim"
                ),
            ),
        ),
        minimum_support=2,
        provenance=_sgd_multi(
            "SGD service pairs recur across dialogues (Restaurants+Movies 247, "
            "Homes+Calendar 235), so co-occurrence counts are measurable"
        ),
    ),
    _l2(
        "l2:pattern.constraint_union",
        L2ItemType.AGGREGATION_PATTERN,
        "collect every restriction stated about one target and keep them all, including conflicts",
        aliases=("accumulated constraints", "all requirements"),
        constraints=(
            Constraint(
                kind="conflicts_are_retained",
                expression=(
                    "a later restriction does not silently delete an earlier one; resolving "
                    "the conflict is a decision with evidence, not a side effect of merging"
                ),
            ),
        ),
        provenance=_sgd_multi(
            "86.4% of 4736 multi-service dialogues reuse a value across services "
            "(city 2238, location 1711), so restrictions accumulate across sub-goals"
        ),
    ),
    _l2(
        "l2:pattern.goal_decomposition",
        L2ItemType.AGGREGATION_PATTERN,
        "group observations under a shared outcome that no one of them achieves alone",
        aliases=("sub-goals", "parts of one aim"),
        constraints=(
            Constraint(
                kind="shared_outcome_required",
                expression=(
                    "temporal adjacency is not decomposition; two adjacent sub-goals must "
                    "share an outcome or the grouping is coincidence"
                ),
            ),
        ),
        minimum_support=2,
        provenance=_sgd_multi(
            "10739 of 16142 dialogues span 2-4 services, and the frequent chains "
            "(Flights+Hotels+Travel 163) share a single trip outcome"
        ),
    ),
)


def _uses(pattern: str) -> Relation:
    return Relation(kind=RelationKind.AGGREGATES, target_id=pattern)


# --- Abstraction types -------------------------------------------------------------------
_ABSTRACTIONS: Final[tuple[L2Item, ...]] = (
    _l2(
        "l2:abstraction.task",
        L2ItemType.ABSTRACTION_TYPE,
        "one aim tracked across turns, from the moment it is declared until it closes or lapses",
        # "in progress" belongs to l2:lifecycle.open: it names a status, not the aim that
        # holds the status.
        aliases=("what they were trying to do", "open item", "the thing they started"),
        relations=(_uses("l2:pattern.temporal_series"),),
        roles=(RoleSlot(role_id="l2:role.subject", is_required=True),),
        constraints=(
            Constraint(
                kind="requires_declaration_and_status",
                expression=(
                    "a task needs the observation that declared it and at least one later "
                    "observation bearing on whether it closed; a declaration alone is an L1 "
                    "intention and does not become an L2 task by being remembered"
                ),
            ),
        ),
        minimum_support=2,
        provenance=_sgd_multi(
            "an intent declared in one turn is satisfied several turns later via "
            "required_slots; INFORM_INTENT 3952 precedes NOTIFY_SUCCESS 1796"
        ),
    ),
    _l2(
        "l2:abstraction.project",
        L2ItemType.ABSTRACTION_TYPE,
        "several tasks pursued under one outcome, where no single task achieves that outcome",
        aliases=("the whole plan", "everything for the trip", "overall effort"),
        relations=(
            _uses("l2:pattern.goal_decomposition"),
            Relation(kind=RelationKind.IS_A, target_id="l2:abstraction.task"),
        ),
        roles=(RoleSlot(role_id="l2:role.subject", is_required=True),),
        constraints=(
            Constraint(
                kind="two_distinct_sub_aims",
                expression=(
                    "at least two sub-aims that are not the same aim restated; one aim with "
                    "two mentions is l2:task and calling it a project double-counts"
                ),
            ),
        ),
        minimum_support=2,
        spans_sessions=True,
        provenance=_sgd_multi(
            "8266 two-service, 2185 three-service and 288 four-service dialogues; the "
            "recurring Flights+Hotels+Travel chain (163) is one outcome over three aims"
        ),
    ),
    _l2(
        "l2:abstraction.preference_profile",
        L2ItemType.ABSTRACTION_TYPE,
        "the standing set of a subject's likes and dislikes in one area, with their conflicts kept",
        aliases=("their taste", "what they usually like", "known preferences"),
        relations=(_uses("l2:pattern.constraint_union"),),
        roles=(RoleSlot(role_id="l2:role.subject", is_required=True),),
        constraints=(
            Constraint(
                kind="retains_polarity_split",
                expression=(
                    "a profile holds positive and negative entries at once; collapsing to "
                    "positives loses the 970 dislike observations MSC attests"
                ),
            ),
        ),
        minimum_support=2,
        spans_sessions=True,
        provenance=_msc(
            "personas are authored as multi-sentence sets (65245 sentences overall) "
            "combining 13819 positive and 970 negative dispositions per subject"
        ),
    ),
    _l2(
        "l2:abstraction.habit",
        L2ItemType.ABSTRACTION_TYPE,
        "a behaviour a subject repeats on distinct occasions, evidenced by the repetitions",
        aliases=("usually does", "regular routine", "every time"),
        relations=(_uses("l2:pattern.recurrence_count"),),
        roles=(RoleSlot(role_id="l2:role.subject", is_required=True),),
        constraints=(
            Constraint(
                kind="three_distinct_occasions",
                expression=(
                    "at least three occasions, and a stated frequency is not one of them. "
                    "'I always cook on Sundays' is one observation of a claimed habit; two "
                    "such claims are two claims, not two occasions"
                ),
            ),
            Constraint(
                kind="thin_evidence_admitted_knowingly",
                expression=(
                    "the support for this item is the weakest in O_L2: only 80 of 65245 MSC "
                    "sentences state a frequency, and SGD recurrence is across dialogues by "
                    "different users rather than repeated behaviour by one subject. It is "
                    "admitted with a support floor of 3 because the alternative is to model "
                    "recurrence as repeated l2:task, which would report every repeated "
                    "action as a fresh unfinished aim"
                ),
            ),
        ),
        minimum_support=3,
        spans_sessions=True,
        provenance=(
            *_msc(
                "80 of 65245 persona sentences state an explicit frequency ('usually', "
                "'always', 'every day'); attested but rare, hence the support floor of 3"
            ),
            *_sgd_multi(
                "recurring service pairs across dialogues (Restaurants+Movies 247) show "
                "the co-occurrence shape, though not repetition by a single subject"
            ),
        ),
    ),
    _l2(
        "l2:abstraction.standing_condition",
        L2ItemType.ABSTRACTION_TYPE,
        "a circumstance treated as continuing to hold until something is observed to end it",
        aliases=("still the case", "as far as we know", "long-running situation"),
        relations=(_uses("l2:pattern.temporal_series"),),
        roles=(RoleSlot(role_id="l2:role.subject", is_required=True),),
        constraints=(
            Constraint(
                kind="persistence_is_an_assumption",
                expression=(
                    "continuation is inferred, not observed, so an instance must remain "
                    "distinguishable from a condition re-confirmed at the time of asking"
                ),
            ),
        ),
        spans_sessions=True,
        provenance=_msc(
            "14288 ongoing-state persona sentences are asserted once and treated as "
            "holding for the whole conversation set without restatement"
        ),
    ),
    _l2(
        "l2:abstraction.carried_constraint",
        L2ItemType.ABSTRACTION_TYPE,
        "a restriction stated once and applying to later aims that never restate it",
        aliases=("as I said before", "same as last time", "applies throughout"),
        relations=(_uses("l2:pattern.constraint_union"),),
        roles=(
            RoleSlot(role_id="l2:role.subject", is_required=True),
            RoleSlot(role_id="l2:role.scope", is_required=True),
        ),
        constraints=(
            Constraint(
                kind="scope_must_be_explicit",
                expression=(
                    "how far the restriction carries has to be recorded, because a "
                    "constraint with unbounded scope will eventually be applied where the "
                    "subject never intended it"
                ),
            ),
        ),
        minimum_support=2,
        spans_sessions=True,
        provenance=_sgd_multi(
            "4091 of 4736 multi-service dialogues (86.4%) reuse a value across services: "
            "city 2238, location 1711, destination_city 1672, appointment_date 1058"
        ),
    ),
    _l2(
        "l2:abstraction.value_history",
        L2ItemType.ABSTRACTION_TYPE,
        "the ordered series of values one attribute of one subject has taken, with the current one",
        aliases=("what it changed from", "used to be", "previous value"),
        relations=(_uses("l2:pattern.temporal_series"),),
        roles=(
            RoleSlot(role_id="l2:role.subject", is_required=True),
            RoleSlot(role_id="l2:role.tracked_attribute", is_required=True),
        ),
        constraints=(
            Constraint(
                kind="superseded_values_retained",
                expression=(
                    "the old value stays addressable: 'what did they say before' cannot be "
                    "answered from the current value, and 71.6% of dialogues change one"
                ),
            ),
        ),
        minimum_support=2,
        spans_sessions=True,
        provenance=_sgd_multi(
            "3661 of 5110 dialogues revise a user slot value; most-revised are city 571, "
            "departure_date 516, date 456, appointment_time 377"
        ),
    ),
)


# --- L2 roles ----------------------------------------------------------------------------
#
# Three, and none of them is an L1 role under another name. l2:role.subject is who the
# abstraction is about; l1:role.holder is who an individual assertion is about, and the two
# come apart when an abstraction is built from observations by several speakers. The map
# records the derivation between them precisely because they are not the same position.
_L2_ROLES: Final[tuple[L2Item, ...]] = (
    _l2(
        "l2:role.subject",
        L2ItemType.EVIDENCE_CONSTRAINT,
        "the party an abstraction is about, which every supporting observation must concern",
        role_kind=OntologyRoleKind.ROLE,
        aliases=("who it is about",),
        constraints=(
            Constraint(
                kind="single_subject",
                expression=(
                    "supports concerning different subjects do not aggregate; a profile built "
                    "across subjects would attribute one person's preferences to another"
                ),
            ),
        ),
        provenance=_tau(
            "tau-bench retail policy permits one user per conversation and requires denying "
            "requests about any other user, making subject identity a hard boundary"
        ),
    ),
    _l2(
        "l2:role.scope",
        L2ItemType.EVIDENCE_CONSTRAINT,
        "how far an abstraction's applicability extends beyond the observations supporting it",
        role_kind=OntologyRoleKind.ROLE,
        aliases=("applies to", "extent"),
        provenance=_sgd_multi(
            "a value reused across 2 services in 86.4% of multi-service dialogues has a "
            "scope wider than the service it was first stated in"
        ),
    ),
    _l2(
        "l2:role.tracked_attribute",
        L2ItemType.EVIDENCE_CONSTRAINT,
        "which single attribute a history is a history of",
        role_kind=OntologyRoleKind.ROLE,
        aliases=("attribute being tracked",),
        constraints=(
            Constraint(
                kind="one_attribute_per_history",
                expression=(
                    "two attributes revised in the same dialogue are two histories; SGD "
                    "revises appointment_date and appointment_time independently"
                ),
            ),
        ),
        provenance=_sgd_multi(
            "revision counts are per slot (city 571, departure_date 516), so a history is "
            "indexed by attribute and not by dialogue"
        ),
    ),
)


# --- Lifecycle states --------------------------------------------------------------------
#
# An abstraction needs a status of its own. An L1 assertion's standing says whether that
# assertion still holds; it cannot say whether an aim built from many assertions was
# achieved, and the two were separate items rather than one shared vocabulary for exactly
# that reason.
_LIFECYCLE: Final[tuple[L2Item, ...]] = (
    _l2(
        "l2:lifecycle.open",
        L2ItemType.LIFECYCLE_STATE,
        "the abstraction is live: evidence shows it started and none shows it ended",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("in progress", "still going", "unfinished"),
        relations=(Relation(kind=RelationKind.LIFECYCLE_OF, target_id="l2:abstraction.task"),),
        provenance=_sgd_schema(
            "an intent with unfilled required_slots is live; SYSTEM REQUEST 5008 is the act "
            "of pursuing it"
        ),
    ),
    _l2(
        "l2:lifecycle.achieved",
        L2ItemType.LIFECYCLE_STATE,
        "evidence shows the abstraction's outcome was reached",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("done", "completed", "sorted"),
        relations=(Relation(kind=RelationKind.LIFECYCLE_OF, target_id="l2:abstraction.task"),),
        provenance=_sgd_schema("NOTIFY_SUCCESS 1796 confirms a transactional intent completed"),
    ),
    _l2(
        "l2:lifecycle.lapsed",
        L2ItemType.LIFECYCLE_STATE,
        "no evidence of an ending and none of progress either, so the status is genuinely unknown",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("went quiet", "no further mention"),
        relations=(Relation(kind=RelationKind.LIFECYCLE_OF, target_id="l2:abstraction.task"),),
        constraints=(
            Constraint(
                kind="not_a_synonym_for_failed",
                expression=(
                    "silence is not failure. Reporting a lapsed aim as abandoned asserts an "
                    "outcome no observation supports, which is the more damaging error"
                ),
            ),
        ),
        provenance=_gap(
            "225 of 227 discovery observations were shaped partial_gold_overlap, meaning "
            "supporting evidence was partially retrieved; a status of unknown must be "
            "representable or partial support gets reported as a definite outcome"
        ),
    ),
    _l2(
        "l2:lifecycle.superseded_by_revision",
        L2ItemType.LIFECYCLE_STATE,
        "the abstraction was replaced by a revised version of itself rather than ended",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("changed plan", "replaced by a new version"),
        relations=(Relation(kind=RelationKind.LIFECYCLE_OF, target_id="l2:abstraction.value_history"),),
        provenance=_sgd_multi(
            "71.6% of dialogues revise a value, and a revised aim is neither achieved nor "
            "abandoned; without this status one of the two would be asserted falsely"
        ),
    ),
)


# --- Evidence constraints ----------------------------------------------------------------
#
# Two constraints that apply to every abstraction, given items of their own so they can be
# cited by the map. They are the honesty requirements: an abstraction that cannot show its
# supports is indistinguishable from an invented one, and the discovery split's dominant
# shape was partial support rather than absent support.
_EVIDENCE_RULES: Final[tuple[L2Item, ...]] = (
    _l2(
        "l2:evidence.supports_addressable",
        L2ItemType.EVIDENCE_CONSTRAINT,
        "every abstraction must name the observations it rests on, individually and retrievably",
        aliases=("show your evidence",),
        constraints=(
            Constraint(
                kind="no_unsupported_abstraction",
                expression=(
                    "an abstraction with no addressable supports is rejected rather than "
                    "reported with low confidence, matching the layer-gold rule that an "
                    "abstraction with an empty derivation is malformed"
                ),
            ),
        ),
        provenance=_repo(
            "L2GoldAbstraction in evaluation/layer_gold.py rejects an abstraction whose "
            "derived_from is empty, so this ontology must state the same requirement"
        ),
    ),
    _l2(
        "l2:evidence.partial_support_marked",
        L2ItemType.EVIDENCE_CONSTRAINT,
        "an abstraction resting on some but not all of its expected supports must say so",
        aliases=("incomplete evidence", "partially supported"),
        constraints=(
            Constraint(
                kind="partial_is_not_complete",
                expression=(
                    "partial support must not be presented as complete support; this was the "
                    "dominant observed shape and is the failure most likely to go unnoticed"
                ),
            ),
        ),
        provenance=_gap(
            "225 of 227 discovery observations were shaped partial_gold_overlap, against 1 "
            "empty_selection and 1 gold_delivery_over_limit"
        ),
    ),
)


def build_o_l2() -> L2Freeze:
    """Assemble O_L2, sorted by id."""
    items = (*_PATTERNS, *_ABSTRACTIONS, *_L2_ROLES, *_LIFECYCLE, *_EVIDENCE_RULES)
    return L2Freeze(
        version=O_L2_VERSION,
        items=tuple(sorted(items, key=lambda entry: entry.item.id)),
    )
