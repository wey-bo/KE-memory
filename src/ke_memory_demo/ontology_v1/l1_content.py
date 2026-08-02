"""O_L1: the atomic layer, authored from the build corpora.

Every item here answers to something countable in a corpus that is not an evaluation
benchmark. The three that carried the weight:

- SGD ``train/schema.json``: 26 services, 131 distinct slot names, 53 intents of which 24
  are transactional. The transactional flag is what separates an event type that changes
  the world from a query that does not, and 12 of the 53 intent names begin with "Find"
  against 7 "Reserve" and 5 "Buy" -- so search and commitment are distinct senses, not one
  "do a thing" predicate.
- SGD dialogue acts over 2559 dialogues: INFORM 10647, OFFER 10569, CONFIRM 10387,
  REQUEST 5008, NEGATE 2127, AFFIRM 2070, NOTIFY_FAILURE 302. Polarity and source-status
  are not decorations on those counts; NEGATE at 2127 with AFFIRM at 2070 means a bare
  predicate with no polarity slot misreads half the corpus.
- SGD user state dynamics over 5110 dialogues: 71.6% revise at least one slot value
  mid-dialogue, most often ``city`` (571), ``departure_date`` (516), ``date`` (456). A
  superseded value is therefore the normal case, which is why ``l1:qualifier.assertion``
  exists at L1 instead of being left to the abstraction layer.

Taskmaster2 (17304 dialogues, 281 distinct annotation names) contributed the attribute
facets: ``name`` 75676, ``type`` 25958, ``amenity`` 19235, ``location`` 11461, ``date``
9651, ``time`` 9087, ``price_range`` 6978, ``rating`` 2993. tau-bench contributed the
operator/tool distinction and the confirmation constraint from its retail policy. MSC
personas (65245 sentences) contributed the preference and stable-state evidence: 13819
affect-positive against 970 affect-negative, and 14288 ongoing-state sentences.

What is not here: no domain content. ``restaurant``, ``flight`` and ``hotel`` are the most
frequent things in every corpus above and all three were rejected, because a foundation
ontology whose types are the build corpus's verticals has fitted the build corpus. The
ledger records that as one decision per rejected vertical.
"""

from __future__ import annotations

from typing import Final

from .models import (
    Constraint,
    L1Freeze,
    L1Item,
    L1ItemType,
    OntologyRoleKind,
    Provenance,
    Relation,
    RelationKind,
    RoleSlot,
    SourceKind,
    OntologyItem,
)

O_L1_VERSION: Final[str] = "1.0.0"


def _l1(
    item_id: str,
    item_type: L1ItemType,
    sense: str,
    *,
    role_kind: OntologyRoleKind = OntologyRoleKind.CONCEPT,
    aliases: tuple[str, ...] = (),
    relations: tuple[Relation, ...] = (),
    roles: tuple[RoleSlot, ...] = (),
    constraints: tuple[Constraint, ...] = (),
    provenance: tuple[Provenance, ...],
) -> L1Item:
    return L1Item(
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
    )


def _sgd_schema(evidence: str) -> tuple[Provenance, ...]:
    return (Provenance(source=SourceKind.SGD_SCHEMA, evidence=evidence),)


def _sgd_acts(evidence: str) -> tuple[Provenance, ...]:
    return (Provenance(source=SourceKind.SGD_DIALOGUE_ACTS, evidence=evidence),)


def _tm2(evidence: str) -> tuple[Provenance, ...]:
    return (Provenance(source=SourceKind.TASKMASTER2_ANNOTATIONS, evidence=evidence),)


def _tau(evidence: str) -> tuple[Provenance, ...]:
    return (Provenance(source=SourceKind.TAU_BENCH_TOOLS, evidence=evidence),)


def _msc(evidence: str) -> tuple[Provenance, ...]:
    return (Provenance(source=SourceKind.MSC_PERSONAS, evidence=evidence),)


def _repo(evidence: str) -> tuple[Provenance, ...]:
    return (Provenance(source=SourceKind.REPOSITORY_VOCABULARY, evidence=evidence),)


def _is_a(target: str) -> Relation:
    return Relation(kind=RelationKind.IS_A, target_id=target)


# --- Roles -------------------------------------------------------------------------------
#
# Ten argument positions, each one attested as a distinct slot family in SGD rather than
# invented from a linguistic inventory. PropBank would have been the principled source for
# this section and was not available offline, so these are corpus-shaped roles and are
# labelled as such: they cover the positions the build corpora fill, and they make no claim
# to be a complete role set.
_ROLES: Final[tuple[L1Item, ...]] = (
    _l1(
        "l1:role.agent",
        L1ItemType.ROLE,
        "the participant who initiates the event and whose action brings it about",
        role_kind=OntologyRoleKind.ROLE,
        aliases=("actor", "initiator"),
        provenance=_sgd_acts(
            "USER INFORM 10647 and SYSTEM OFFER 10569 are acts by distinct initiators; "
            "every intent in schema.json is performed by one of the two"
        ),
    ),
    _l1(
        "l1:role.holder",
        L1ItemType.ROLE,
        "the participant a state or preference is true of, who need not act for it to hold",
        role_kind=OntologyRoleKind.ROLE,
        aliases=("bearer", "experiencer"),
        provenance=_msc(
            "65245 persona sentences ascribe states to a subject who performs no action: "
            "14288 match an ongoing-state pattern such as 'I live/work/am'"
        ),
    ),
    _l1(
        "l1:role.theme",
        L1ItemType.ROLE,
        "the entity the predicate is about, created, changed or transferred by the event",
        role_kind=OntologyRoleKind.ROLE,
        aliases=("object", "patient"),
        provenance=_sgd_schema(
            "every transactional intent (24 of 53) names the thing acted on in its "
            "required_slots, for instance TransferMoney requires amount"
        ),
    ),
    _l1(
        "l1:role.recipient",
        L1ItemType.ROLE,
        "the participant who receives the theme, distinct from the agent who sends it",
        role_kind=OntologyRoleKind.ROLE,
        aliases=("beneficiary", "addressee"),
        provenance=_sgd_schema(
            "Banks_1 separates account_type from recipient_account_type and "
            "recipient_account_name, so sender and receiver are separate positions"
        ),
    ),
    _l1(
        "l1:role.source_location",
        L1ItemType.ROLE,
        "the place or state a movement or transition starts from",
        role_kind=OntologyRoleKind.ROLE,
        aliases=("origin", "from"),
        provenance=_sgd_schema(
            "origin/from_location/from_station/origin_airport appear as an origin family "
            "across Buses, Flights and RideSharing services"
        ),
    ),
    _l1(
        "l1:role.target_location",
        L1ItemType.ROLE,
        "the place or state a movement or transition ends at",
        role_kind=OntologyRoleKind.ROLE,
        aliases=("destination", "to"),
        relations=(Relation(kind=RelationKind.OPPOSITE_OF, target_id="l1:role.source_location"),),
        provenance=_sgd_schema(
            "destination appears in 5 services and destination_airport/to_location/"
            "to_station in others; Taskmaster2 records destination1 4018 times"
        ),
    ),
    _l1(
        "l1:role.instrument",
        L1ItemType.ROLE,
        "the means by which the agent brings the event about, including a tool or channel",
        role_kind=OntologyRoleKind.ROLE,
        aliases=("means", "via"),
        provenance=_tau(
            "retail order changes require payment_method_id and Music services require "
            "playback_device, both a means rather than a theme"
        ),
    ),
    _l1(
        "l1:role.quantity",
        L1ItemType.ROLE,
        "how many units of the theme the predicate applies to",
        role_kind=OntologyRoleKind.ROLE,
        # "amount" is not listed here even though it is idiomatic for a count, because
        # l1:attribute.magnitude owns it. An alias resolving to both a role and an attribute
        # would make normalization depend on iteration order.
        aliases=("count", "party size", "how many of them"),
        provenance=_sgd_schema(
            "a count family recurs with service-specific names: passengers, travelers, "
            "group_size, party_size, number_of_seats, number_of_tickets, number_of_rooms"
        ),
    ),
    _l1(
        "l1:role.attribute_bearer",
        L1ItemType.ROLE,
        "the entity an attribute is predicated of, as distinct from the attribute value",
        role_kind=OntologyRoleKind.ROLE,
        aliases=("subject of attribute",),
        provenance=_tm2(
            "the 3-part annotation names split frame.facet.filler, so the bearer position "
            "is separate from the facet; 'name' fills it 75676 times"
        ),
    ),
    _l1(
        "l1:role.constraint_on",
        L1ItemType.ROLE,
        "what a preference or requirement restricts, as opposed to the value it restricts it to",
        role_kind=OntologyRoleKind.ROLE,
        aliases=("restricts",),
        provenance=_sgd_schema(
            "search intents pass user restrictions as slot values, e.g. Restaurants_1 "
            "price_range over ['inexpensive'..'very expensive'] narrows a search"
        ),
    ),
)


# --- Qualifier dimensions ----------------------------------------------------------------
#
# Five dimensions, each a property of an assertion rather than of its subject. They are
# separate items rather than one "metadata" bag because they are independently valued: a
# negated preference reported by the user about a future event is a legal combination of
# four dimensions, and collapsing them would make it unrepresentable.
_QUALIFIER_DIMENSIONS: Final[tuple[L1Item, ...]] = (
    _l1(
        "l1:qualifier.time",
        L1ItemType.QUALIFIER_DIMENSION,
        "when the described situation holds, relative to the moment it was asserted",
        aliases=("tense", "temporal reference"),
        provenance=_sgd_schema(
            "date/time slots are ubiquitous (date in 4 services, time in 3) and are "
            "always about the described situation, not the utterance"
        ),
    ),
    _l1(
        "l1:qualifier.modality",
        L1ItemType.QUALIFIER_DIMENSION,
        "the attitude the assertion carries towards its content: asserted, wanted, planned",
        aliases=("attitude", "mood"),
        provenance=_sgd_acts(
            "INFORM_INTENT 3952 and AFFIRM_INTENT 680 mark a wanted situation, distinct "
            "from INFORM 10647 marking an asserted one"
        ),
    ),
    _l1(
        "l1:qualifier.polarity",
        L1ItemType.QUALIFIER_DIMENSION,
        "whether the assertion affirms or denies that its content holds",
        aliases=("negation",),
        provenance=_sgd_acts(
            "NEGATE 2127 against AFFIRM 2070 and NEGATE_INTENT 407 against "
            "AFFIRM_INTENT 680: denial is as frequent as affirmation"
        ),
    ),
    _l1(
        "l1:qualifier.source_status",
        L1ItemType.QUALIFIER_DIMENSION,
        "who or what vouches for the content: the user, the assistant, a tool, or inference",
        aliases=("evidentiality", "attribution"),
        provenance=_sgd_acts(
            "the speaker field partitions all acts into USER and SYSTEM, and "
            "NOTIFY_SUCCESS 1796 / NOTIFY_FAILURE 302 report a system-side outcome"
        ),
    ),
    _l1(
        "l1:qualifier.assertion_standing",
        L1ItemType.QUALIFIER_DIMENSION,
        "whether the assertion still stands or has been replaced by a later one",
        aliases=("currency", "supersession status"),
        provenance=(
            Provenance(
                source=SourceKind.SGD_STATE_DYNAMICS,
                evidence=(
                    "3661 of 5110 dialogues (71.6%) revise at least one user slot value "
                    "mid-dialogue; city 571, departure_date 516, date 456"
                ),
            ),
        ),
    ),
)


def _value(
    item_id: str,
    dimension: str,
    sense: str,
    *,
    aliases: tuple[str, ...] = (),
    opposite: str | None = None,
    provenance: tuple[Provenance, ...],
) -> L1Item:
    """A vocabulary value, wired to its dimension by ``qualified_by``.

    The edge points value-to-dimension rather than the reverse so that adding a value is a
    local change. A dimension listing its values would have to be edited for every new
    value, and every such edit moves the O_L1 hash for a reason unrelated to the dimension.
    """
    relations = [Relation(kind=RelationKind.QUALIFIED_BY, target_id=dimension)]
    if opposite is not None:
        relations.append(Relation(kind=RelationKind.OPPOSITE_OF, target_id=opposite))
    return _l1(
        item_id,
        L1ItemType.QUALIFIER_VALUE,
        sense,
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=aliases,
        relations=tuple(relations),
        provenance=provenance,
    )


# --- Time vocabulary ---------------------------------------------------------------------
#
# Coarse and relative on purpose. SGD carries absolute dates as slot values, but an
# absolute date is an Individual: "2019-03-01" is a fact about one dialogue, and admitting
# it would put benchmark facts in a type-level ontology. What survives freezing is the
# relation between event time and assertion time, which is type-level.
_TIME_VALUES: Final[tuple[L1Item, ...]] = (
    _value(
        "l1:time.before_assertion",
        "l1:qualifier.time",
        "the situation held or occurred before the moment of assertion",
        aliases=("past", "already happened"),
        opposite="l1:time.after_assertion",
        provenance=_msc(
            "1632 of 65245 persona sentences match a past-event pattern "
            "('I used to', 'I graduated', 'I moved')"
        ),
    ),
    _value(
        "l1:time.at_assertion",
        "l1:qualifier.time",
        "the situation holds at the moment of assertion",
        aliases=("present", "currently", "right now"),
        provenance=_msc("14288 persona sentences assert a state holding at utterance time"),
    ),
    _value(
        "l1:time.after_assertion",
        "l1:qualifier.time",
        "the situation is expected or scheduled to hold after the moment of assertion",
        aliases=("future", "upcoming", "planned for"),
        provenance=_sgd_schema(
            "forward-looking slots are pervasive: check_in_date, departure_date, "
            "appointment_date, pickup_date all denote a situation not yet realised"
        ),
    ),
    _value(
        "l1:time.spanning",
        "l1:qualifier.time",
        "the situation holds over an interval rather than at a point",
        aliases=("during", "over a period", "ongoing since"),
        provenance=_sgd_schema(
            "paired boundary slots define intervals: check_in_date/check_out_date, "
            "outbound_departure_time/inbound_arrival_time; Taskmaster2 date_range 2469"
        ),
    ),
    _value(
        "l1:time.recurring",
        "l1:qualifier.time",
        "the situation holds repeatedly on some cycle rather than once",
        aliases=("habitually", "every week", "regularly"),
        provenance=_msc(
            "80 of 65245 persona sentences match an explicit frequency pattern "
            "('usually', 'always', 'every day'); rare but structurally distinct"
        ),
    ),
    _value(
        "l1:time.unspecified",
        "l1:qualifier.time",
        "no temporal location is recoverable from the assertion",
        aliases=("timeless", "no time given"),
        provenance=_msc(
            "the majority of persona sentences carry no temporal marker at all, so an "
            "explicit unspecified value prevents a default of 'present' being invented"
        ),
    ),
)


# --- Modality, polarity, source-status, standing ------------------------------------------
#
# The modality values are a deliberate subset of ke_memory_demo.domain.Modality, which has
# eight. FACT/BELIEF/PREFERENCE/GOAL/PLAN/INSTRUCTION are kept; HYPOTHESIS and QUESTION are
# not, because nothing in the build corpora attests them as an assertion attitude -- SGD's
# REQUEST (3394 user, 5008 system) is a speech act asking for a slot value, not an assertion
# with question modality. Both are recorded as deferred in the ledger rather than dropped.
_MODAL_VALUES: Final[tuple[L1Item, ...]] = (
    _value(
        "l1:modality.asserted",
        "l1:qualifier.modality",
        "presented as holding in the world, independent of anyone wanting it to",
        aliases=("fact", "stated"),
        provenance=_sgd_acts("INFORM 10647 by users and 3244 by the system present slot values"),
    ),
    _value(
        "l1:modality.believed",
        "l1:qualifier.modality",
        "presented as the speaker's belief, which may be wrong without being a lie",
        aliases=("belief", "thinks", "i guess"),
        provenance=_repo(
            "ke_memory_demo.domain.Modality.BELIEF already partitions this from FACT, and "
            "keeping the distinction preserves compatibility with extracted units"
        ),
    ),
    _value(
        "l1:modality.desired",
        "l1:qualifier.modality",
        "presented as wanted by the holder, without commitment to bringing it about",
        aliases=("preference", "would like", "wants"),
        provenance=_msc(
            "13819 of 65245 persona sentences match an affect-positive pattern "
            "('I like/love/enjoy/prefer'), the single largest attested attitude"
        ),
    ),
    _value(
        "l1:modality.intended",
        "l1:qualifier.modality",
        "presented as a commitment by the agent to bring the situation about",
        aliases=("goal", "going to", "plan to"),
        provenance=_sgd_acts(
            "INFORM_INTENT 3952 and AFFIRM_INTENT 680 commit the user to an intent; "
            "1061 MSC persona sentences match 'I want/plan/hope to'"
        ),
    ),
    _value(
        "l1:modality.directed",
        "l1:qualifier.modality",
        "presented as an instruction the addressee is expected to comply with",
        aliases=("instruction", "please do", "standing order"),
        provenance=_tau(
            "retail policy requires explicit user confirmation before consequential "
            "actions, so a directive is a distinct attitude from a stated preference"
        ),
    ),
)

_POLARITY_VALUES: Final[tuple[L1Item, ...]] = (
    _value(
        "l1:polarity.affirmed",
        "l1:qualifier.polarity",
        "the assertion holds as stated",
        aliases=("positive", "yes"),
        opposite="l1:polarity.denied",
        provenance=_sgd_acts("AFFIRM 2070 and AFFIRM_INTENT 680"),
    ),
    _value(
        "l1:polarity.denied",
        "l1:qualifier.polarity",
        "the assertion is stated not to hold, which is content and not absence of content",
        aliases=("negative", "no", "not"),
        provenance=_sgd_acts(
            "NEGATE 2127 and NEGATE_INTENT 407; MSC contributes 970 affect-negative "
            "persona sentences ('I hate', \"I don't like\")"
        ),
    ),
    _value(
        "l1:polarity.indeterminate",
        "l1:qualifier.polarity",
        "the assertion's polarity cannot be recovered from what was said",
        aliases=("unknown polarity",),
        provenance=_repo(
            "ke_memory_demo.domain.Polarity.UNKNOWN exists for extracted units, and an "
            "ontology without it would force a wrong choice at mapping time"
        ),
    ),
)

_SOURCE_STATUS_VALUES: Final[tuple[L1Item, ...]] = (
    _value(
        "l1:source_status.user_reported",
        "l1:qualifier.source_status",
        "the user is the authority for the content; nothing else corroborates it",
        aliases=("said by user", "self-reported"),
        provenance=_sgd_acts("10647 USER INFORM acts are the user's own report of a value"),
    ),
    _value(
        "l1:source_status.assistant_asserted",
        "l1:qualifier.source_status",
        "the assistant produced the content, so it inherits the assistant's reliability",
        aliases=("agent generated", "said by assistant"),
        provenance=_sgd_acts("SYSTEM OFFER 10569 and SYSTEM INFORM 3244 originate system-side"),
    ),
    _value(
        "l1:source_status.tool_observed",
        "l1:qualifier.source_status",
        "a tool or backend returned the content, which is checkable independently of the dialogue",
        aliases=("tool result", "api result", "looked up"),
        provenance=_tau(
            "get_order_details, get_reservation_details and get_user_details return "
            "backend state rather than dialogue content"
        ),
    ),
    _value(
        "l1:source_status.derived",
        "l1:qualifier.source_status",
        "the content was inferred from other content and has no independent source of its own",
        aliases=("inferred", "computed"),
        provenance=_repo(
            "ke_memory_demo.online.SourceStatus.DERIVED already exists, and every L2 "
            "abstraction will carry this status, so it must be nameable at L1"
        ),
    ),
    _value(
        "l1:source_status.confirmed_by_both",
        "l1:qualifier.source_status",
        "user and assistant explicitly agreed on the content, so neither alone is the authority",
        aliases=("mutually confirmed", "read back and accepted"),
        provenance=_sgd_acts(
            "SYSTEM CONFIRM 10387 followed by USER AFFIRM 2070 is the corpus's most "
            "frequent agreement structure; tau-bench policy mandates it before writes"
        ),
    ),
)

_STANDING_VALUES: Final[tuple[L1Item, ...]] = (
    _value(
        "l1:standing.current",
        "l1:qualifier.assertion_standing",
        "no later assertion has replaced this one",
        aliases=("active", "still holds"),
        opposite="l1:standing.superseded",
        provenance=_repo("ke_memory_demo.domain.Lifecycle.ACTIVE"),
    ),
    _value(
        "l1:standing.superseded",
        "l1:qualifier.assertion_standing",
        "a later assertion about the same subject and attribute replaced this one",
        aliases=("outdated", "changed since", "replaced"),
        provenance=(
            Provenance(
                source=SourceKind.SGD_STATE_DYNAMICS,
                evidence=(
                    "71.6% of 5110 dialogues revise a slot value, so supersession is the "
                    "common case rather than an exception"
                ),
            ),
        ),
    ),
    _value(
        "l1:standing.retracted",
        "l1:qualifier.assertion_standing",
        "the asserter withdrew the content without substituting a replacement value",
        aliases=("withdrawn", "never mind", "cancelled that"),
        provenance=_sgd_acts(
            "NEGATE_INTENT 407 abandons a declared intent without providing another, "
            "which is withdrawal rather than substitution"
        ),
    ),
)


def _slot(role: str, *, required: bool = False, range_id: str | None = None) -> RoleSlot:
    return RoleSlot(role_id=role, is_required=required, range_id=range_id)


# --- Predicate senses --------------------------------------------------------------------
#
# Seven senses, each mapping to a cluster of SGD intent verbs rather than to one verb. The
# clustering is what makes them senses: SGD's 53 intents reduce to 12 leading verbs
# (Find 12, Get 9, Search 7, Reserve 7, Buy 5, Book 4, Play 3, Lookup 2, Check/Transfer/
# Add/Schedule 1 each), and Find/Search/Lookup/Get-information collapse to one sense while
# Reserve/Book/Buy collapse to another. WordNet would have supplied the sense inventory and
# is unavailable offline, so these senses are corpus-clustered and say so.
_PREDICATE_SENSES: Final[tuple[L1Item, ...]] = (
    _l1(
        "l1:predicate.seek_information",
        L1ItemType.PREDICATE_SENSE,
        "the agent tries to obtain information about a theme without changing anything",
        role_kind=OntologyRoleKind.OPERATOR,
        aliases=("find", "search", "look up", "check", "ask about"),
        roles=(
            _slot("l1:role.agent", required=True),
            _slot("l1:role.theme", required=True),
            _slot("l1:role.constraint_on"),
        ),
        constraints=(
            Constraint(
                kind="no_world_change",
                expression=(
                    "an instance of this sense must not be recorded as changing any state; "
                    "SGD marks 29 of 53 intents non-transactional and these are those"
                ),
            ),
        ),
        provenance=_sgd_schema(
            "Find (12) + Search (7) + Lookup (2) + Check (1) = 22 of 53 intent names, and "
            "all 22 belong to intents with is_transactional false"
        ),
    ),
    _l1(
        "l1:predicate.commit_to_arrangement",
        L1ItemType.PREDICATE_SENSE,
        "the agent binds itself to a future arrangement, creating an obligation on both sides",
        role_kind=OntologyRoleKind.OPERATOR,
        aliases=("reserve", "book", "schedule", "make an appointment"),
        roles=(
            _slot("l1:role.agent", required=True),
            _slot("l1:role.theme", required=True),
            _slot("l1:role.quantity"),
        ),
        constraints=(
            Constraint(
                kind="requires_confirmation",
                expression=(
                    "a commitment is only complete when the counterparty confirms; "
                    "tau-bench retail policy requires explicit user 'yes' before any write"
                ),
            ),
            Constraint(
                kind="creates_revisable_obligation",
                expression=(
                    "an arrangement may later be modified or cancelled, so an instance is "
                    "not terminal; tau-bench exposes cancel and modify for reservations"
                ),
            ),
        ),
        provenance=_sgd_schema(
            "Reserve (7) + Book (4) + Schedule (1) = 12 intent names, and every one has "
            "is_transactional true"
        ),
    ),
    _l1(
        "l1:predicate.transfer_value",
        L1ItemType.PREDICATE_SENSE,
        "the agent gives up something of value and a recipient acquires it",
        role_kind=OntologyRoleKind.OPERATOR,
        aliases=("buy", "pay", "transfer", "purchase"),
        roles=(
            _slot("l1:role.agent", required=True),
            _slot("l1:role.theme", required=True),
            _slot("l1:role.recipient"),
            _slot("l1:role.instrument"),
            _slot("l1:role.quantity"),
        ),
        constraints=(
            Constraint(
                kind="requires_instrument",
                expression=(
                    "a value transfer names the means, because reversing it depends on the "
                    "means: tau-bench refunds a gift card immediately and a card in 5-7 days"
                ),
            ),
        ),
        provenance=_sgd_schema(
            "Buy (5) + Transfer (1) intents, all transactional; Banks_1 TransferMoney "
            "requires amount and recipient_account_name together"
        ),
    ),
    _l1(
        "l1:predicate.change_arrangement",
        L1ItemType.PREDICATE_SENSE,
        "the agent alters or withdraws an arrangement that already exists",
        role_kind=OntologyRoleKind.OPERATOR,
        aliases=("modify", "change", "cancel", "update", "reschedule"),
        roles=(
            _slot("l1:role.agent", required=True),
            _slot("l1:role.theme", required=True),
        ),
        constraints=(
            Constraint(
                kind="presupposes_prior_commitment",
                expression=(
                    "an instance is only well-formed if a prior commit_to_arrangement is "
                    "recoverable; tau-bench refuses to modify an order that is not pending"
                ),
            ),
        ),
        provenance=_tau(
            "retail exposes cancel_pending_order, modify_pending_order_address/items/payment "
            "and airline exposes cancel_reservation and three update_reservation_* tools"
        ),
    ),
    _l1(
        "l1:predicate.consume_media",
        L1ItemType.PREDICATE_SENSE,
        "the agent experiences a content item, which changes no arrangement and leaves a trace",
        role_kind=OntologyRoleKind.OPERATOR,
        aliases=("play", "watch", "listen to", "stream"),
        roles=(
            _slot("l1:role.agent", required=True),
            _slot("l1:role.theme", required=True),
            _slot("l1:role.instrument"),
        ),
        provenance=_sgd_schema(
            "Play (3) intents -- PlaySong, PlayMovie, PlayMedia -- are transactional yet "
            "create no obligation, so they are neither seek_information nor commitment"
        ),
    ),
    _l1(
        "l1:predicate.hold_attitude",
        L1ItemType.PREDICATE_SENSE,
        "a holder stands in an evaluative relation to a theme, positively or negatively",
        role_kind=OntologyRoleKind.OPERATOR,
        aliases=("like", "prefer", "dislike", "be a fan of", "hate"),
        roles=(
            _slot("l1:role.holder", required=True),
            _slot("l1:role.theme", required=True),
        ),
        constraints=(
            Constraint(
                kind="polarity_bearing",
                expression=(
                    "an instance must carry a l1:qualifier.polarity value, because the same "
                    "predicate covers 13819 like-patterns and 970 dislike-patterns in MSC"
                ),
            ),
        ),
        provenance=_msc(
            "13819 affect-positive and 970 affect-negative persona sentences share one "
            "argument frame and differ only in polarity"
        ),
    ),
    _l1(
        "l1:predicate.occupy_role",
        L1ItemType.PREDICATE_SENSE,
        "a holder stands in a durable non-evaluative relation to a place, activity or entity",
        role_kind=OntologyRoleKind.OPERATOR,
        aliases=("live in", "work as", "study", "own", "have"),
        roles=(
            _slot("l1:role.holder", required=True),
            _slot("l1:role.theme", required=True),
        ),
        provenance=_msc(
            "14288 ongoing-state and 8660 possession persona sentences describe a durable "
            "relation with no evaluative component"
        ),
    ),
)


# --- Event types -------------------------------------------------------------------------
#
# An event type is a bounded occurrence. It is kept separate from the predicate sense it
# uses: the sense carries argument structure, the event type carries boundedness and the
# temporal qualifier. Mapping a surface verb needs the sense; deciding whether two mentions
# are the same occurrence needs the event type, and conflating them is why "did X happen
# twice" is unanswerable from a sense alone.
_EVENT_TYPES: Final[tuple[L1Item, ...]] = (
    _l1(
        "l1:event.information_request",
        L1ItemType.EVENT_TYPE,
        "a bounded occurrence in which one party asks another for information",
        aliases=("asked about", "enquiry"),
        relations=(
            Relation(
                kind=RelationKind.SPECIALIZES_SENSE,
                target_id="l1:predicate.seek_information",
            ),
        ),
        roles=(_slot("l1:role.agent", required=True), _slot("l1:role.theme", required=True)),
        provenance=_sgd_acts("USER REQUEST 3394 and SYSTEM REQUEST 5008 are bounded ask events"),
    ),
    _l1(
        "l1:event.commitment_made",
        L1ItemType.EVENT_TYPE,
        "a bounded occurrence in which an arrangement comes into existence",
        aliases=("booked", "reserved", "scheduled"),
        relations=(
            Relation(
                kind=RelationKind.SPECIALIZES_SENSE,
                target_id="l1:predicate.commit_to_arrangement",
            ),
        ),
        roles=(_slot("l1:role.agent", required=True), _slot("l1:role.theme", required=True)),
        constraints=(
            Constraint(
                kind="opens_a_state",
                expression=(
                    "this event begins a state that outlives it, so an instance without a "
                    "resulting l1:state.pending_arrangement is incompletely represented"
                ),
            ),
        ),
        provenance=_sgd_acts(
            "NOTIFY_SUCCESS 1796 marks the moment a transactional intent completes, "
            "against NOTIFY_FAILURE 302 where no arrangement comes into existence"
        ),
    ),
    _l1(
        "l1:event.commitment_withdrawn",
        L1ItemType.EVENT_TYPE,
        "a bounded occurrence that ends an existing arrangement without fulfilling it",
        aliases=("cancelled", "called off"),
        relations=(
            Relation(
                kind=RelationKind.SPECIALIZES_SENSE,
                target_id="l1:predicate.change_arrangement",
            ),
        ),
        roles=(_slot("l1:role.agent", required=True), _slot("l1:role.theme", required=True)),
        provenance=_tau(
            "cancel_pending_order requires a reason from a closed set ('no longer needed', "
            "'ordered by mistake'), so withdrawal is a distinct event with its own cause"
        ),
    ),
    _l1(
        "l1:event.attempt_failed",
        L1ItemType.EVENT_TYPE,
        "a bounded occurrence in which an intended action did not achieve its result",
        aliases=("failed", "did not go through", "unavailable"),
        roles=(_slot("l1:role.agent", required=True), _slot("l1:role.theme")),
        constraints=(
            Constraint(
                kind="no_resulting_state",
                expression=(
                    "a failed attempt must not be recorded as opening a state; treating "
                    "NOTIFY_FAILURE like NOTIFY_SUCCESS would assert 302 arrangements that "
                    "do not exist"
                ),
            ),
        ),
        provenance=_sgd_acts(
            "SYSTEM NOTIFY_FAILURE 302 across 2559 dialogues; a failed attempt is attested "
            "and is not the negation of a success event"
        ),
    ),
    _l1(
        "l1:event.media_consumption",
        L1ItemType.EVENT_TYPE,
        "a bounded occurrence of experiencing a content item",
        aliases=("watched", "listened to", "played"),
        relations=(
            Relation(kind=RelationKind.SPECIALIZES_SENSE, target_id="l1:predicate.consume_media"),
        ),
        roles=(_slot("l1:role.agent", required=True), _slot("l1:role.theme", required=True)),
        provenance=_tm2(
            "movie_search 45318 and music 21229 annotation instances, with "
            "streaming_service 2756 naming the instrument of consumption"
        ),
    ),
)


# --- State types -------------------------------------------------------------------------
#
# A state holds over an interval rather than occurring at a point. The distinction from an
# event is not duration but revisability: a state's value can be superseded while remaining
# the same state, which is exactly the 71.6% case in SGD, whereas a superseded event would
# be a different event.
_STATE_TYPES: Final[tuple[L1Item, ...]] = (
    _l1(
        "l1:state.pending_arrangement",
        L1ItemType.STATE_TYPE,
        "an arrangement exists and its obligations have not yet been discharged",
        aliases=("booked and upcoming", "on the calendar", "order pending"),
        roles=(_slot("l1:role.holder", required=True), _slot("l1:role.theme", required=True)),
        constraints=(
            Constraint(
                kind="terminates_on_fulfilment_or_withdrawal",
                expression=(
                    "this state ends by fulfilment or by l1:event.commitment_withdrawn, and "
                    "not by the passage of time alone"
                ),
            ),
        ),
        provenance=_tau(
            "tau-bench order status is a four-value lifecycle (pending, processed, "
            "delivered, cancelled) and only pending permits modification"
        ),
    ),
    _l1(
        "l1:state.circumstance",
        L1ItemType.STATE_TYPE,
        "a durable non-evaluative fact about a holder, such as where they live or what they do",
        # "currently" belongs to l1:time.at_assertion, not here: it locates an assertion in
        # time and does not name the state being located.
        aliases=("situation", "circumstances", "as things stand"),
        relations=(
            Relation(kind=RelationKind.SPECIALIZES_SENSE, target_id="l1:predicate.occupy_role"),
        ),
        roles=(_slot("l1:role.holder", required=True), _slot("l1:role.theme", required=True)),
        constraints=(
            Constraint(
                kind="revisable_without_identity_change",
                expression=(
                    "a new value supersedes the old while remaining the same state; SGD "
                    "revises city 571 times and departure_date 516 times in 5110 dialogues"
                ),
            ),
        ),
        provenance=_msc(
            "14288 of 65245 persona sentences assert an ongoing circumstance "
            "('I live in', 'I work as', 'I am a')"
        ),
    ),
    _l1(
        "l1:state.possession",
        L1ItemType.STATE_TYPE,
        "a holder has something at their disposal over an interval",
        aliases=("owns", "has", "keeps"),
        relations=(_is_a("l1:state.circumstance"),),
        roles=(_slot("l1:role.holder", required=True), _slot("l1:role.theme", required=True)),
        provenance=_msc("8660 of 65245 persona sentences match an 'I have/own' pattern"),
    ),
    _l1(
        "l1:state.capability_constraint",
        L1ItemType.STATE_TYPE,
        "a standing limit on what the holder can do or accept, not a matter of taste",
        aliases=("cannot", "not allowed", "restriction", "requirement"),
        roles=(_slot("l1:role.holder", required=True), _slot("l1:role.constraint_on")),
        constraints=(
            Constraint(
                kind="distinct_from_preference",
                expression=(
                    "a constraint cannot be traded off the way a preference can; conflating "
                    "them makes a hard requirement look like a rankable option"
                ),
            ),
        ),
        provenance=_tau(
            "tau-bench policy states hard limits (a gift card must cover the total; item "
            "modification cannot change product type) that are not preferences"
        ),
    ),
)


# --- Preference types --------------------------------------------------------------------
#
# Three, split by what the preference ranges over, because they behave differently under
# aggregation. A liking has one theme; a comparative has two and is not recoverable from two
# separate likings; a threshold is a boundary on an attribute and can conflict with an
# instance value without contradicting any other preference.
_PREFERENCE_TYPES: Final[tuple[L1Item, ...]] = (
    _l1(
        "l1:preference.affinity",
        L1ItemType.PREFERENCE_TYPE,
        "the holder is favourably or unfavourably disposed towards a theme, taken on its own",
        aliases=("likes", "dislikes", "enjoys", "is into"),
        relations=(
            Relation(kind=RelationKind.SPECIALIZES_SENSE, target_id="l1:predicate.hold_attitude"),
            Relation(kind=RelationKind.QUALIFIED_BY, target_id="l1:qualifier.polarity"),
        ),
        roles=(_slot("l1:role.holder", required=True), _slot("l1:role.theme", required=True)),
        provenance=_msc(
            "13819 affect-positive and 970 affect-negative persona sentences; the largest "
            "single attested preference shape"
        ),
    ),
    _l1(
        "l1:preference.comparative",
        L1ItemType.PREFERENCE_TYPE,
        "the holder ranks one theme above another, which neither theme's affinity alone states",
        aliases=("prefers x to y", "rather than", "would sooner"),
        relations=(
            Relation(kind=RelationKind.SPECIALIZES_SENSE, target_id="l1:predicate.hold_attitude"),
        ),
        roles=(
            _slot("l1:role.holder", required=True),
            _slot("l1:role.theme", required=True),
            _slot("l1:role.constraint_on", required=True),
        ),
        constraints=(
            Constraint(
                kind="irreducible_to_affinities",
                expression=(
                    "two affinity items with the same polarity do not entail a ranking, so a "
                    "comparative may not be synthesised from them"
                ),
            ),
        ),
        provenance=_sgd_acts(
            "USER SELECT 2577 chooses among offered alternatives and REQUEST_ALTS 1397 "
            "rejects the current offer in favour of another, both ranking acts"
        ),
    ),
    _l1(
        "l1:preference.threshold",
        L1ItemType.PREFERENCE_TYPE,
        "the holder wants an attribute to stay within a bound, rather than favouring a theme",
        aliases=("at most", "no more than", "at least", "under budget"),
        roles=(
            _slot("l1:role.holder", required=True),
            _slot("l1:role.constraint_on", required=True, range_id="l1:attribute.magnitude"),
        ),
        provenance=_sgd_schema(
            "ordered categorical ranges support bounds: Restaurants_1 price_range "
            "['inexpensive'..'very expensive'] and Hotels_1 star_rating ['1'..'5']"
        ),
    ),
)


# --- Task types --------------------------------------------------------------------------
#
# A task at L1 is a single-turn-visible intention, not a project. The abstraction layer owns
# multi-session tasks, and that boundary is the reason O_L2 exists at all: SGD's unit of
# intention is one intent inside one dialogue, and 5403 of 16142 dialogues involve exactly
# one service, so most attested tasks genuinely are atomic.
_TASK_TYPES: Final[tuple[L1Item, ...]] = (
    _l1(
        "l1:task.declared_intention",
        L1ItemType.TASK_TYPE,
        "the agent states an aim it has not yet achieved, at a granularity resolvable in one turn",
        aliases=("wants to", "needs to", "trying to", "looking to"),
        relations=(Relation(kind=RelationKind.QUALIFIED_BY, target_id="l1:qualifier.modality"),),
        roles=(_slot("l1:role.agent", required=True), _slot("l1:role.theme", required=True)),
        constraints=(
            Constraint(
                kind="single_turn_scope",
                expression=(
                    "an L1 task is what one turn makes explicit; anything requiring evidence "
                    "from a second turn is an O_L2 abstraction and not this item"
                ),
            ),
        ),
        provenance=_sgd_acts(
            "USER INFORM_INTENT 3952 declares an aim in one turn, and SYSTEM OFFER_INTENT "
            "1087 proposes one"
        ),
    ),
    _l1(
        "l1:task.outstanding_requirement",
        L1ItemType.TASK_TYPE,
        "a specific piece of information or action still missing before an intention can complete",
        aliases=("still need", "waiting on", "to be confirmed"),
        roles=(_slot("l1:role.agent", required=True), _slot("l1:role.theme", required=True)),
        constraints=(
            Constraint(
                kind="closes_when_supplied",
                expression=(
                    "this item ends when the missing value is supplied, so it is not a "
                    "preference and must not survive its own satisfaction"
                ),
            ),
        ),
        provenance=_sgd_schema(
            "required_slots on each intent names exactly what is outstanding; SYSTEM REQUEST "
            "5008 is the act of asking for one of them"
        ),
    ),
    _l1(
        "l1:task.abandoned_intention",
        L1ItemType.TASK_TYPE,
        "an aim the agent declared and then gave up without achieving it",
        # "never mind" stays with l1:standing.retracted, which is the general withdrawal
        # marker; an abandoned intention is one thing that marker can apply to.
        aliases=("gave up on", "dropped it", "stopped trying to"),
        roles=(_slot("l1:role.agent", required=True), _slot("l1:role.theme", required=True)),
        provenance=_sgd_acts(
            "NEGATE_INTENT 407 abandons a previously declared intent, so abandonment is "
            "attested as its own outcome rather than as an absent completion"
        ),
    ),
)


# --- Attribute types ---------------------------------------------------------------------
#
# Eight, obtained by collapsing SGD's 131 distinct slot names and Taskmaster2's 281
# annotation names onto the families that recur across domains. The collapse is the
# contribution: ``departure_date``, ``check_in_date``, ``appointment_date``, ``pickup_date``
# and ``show_date`` are five slot names and one attribute type, and an ontology that kept all
# five would have encoded the build corpus's service catalogue as ontology structure.
#
# The test of whether a family earned an entry was cross-domain recurrence, not frequency.
# ``amenity`` is Taskmaster2's third most frequent facet at 19235 and was still rejected: it
# recurs only inside lodging, so it is domain content wearing a general name.
_ATTRIBUTE_TYPES: Final[tuple[L1Item, ...]] = (
    _l1(
        "l1:attribute.designation",
        L1ItemType.ATTRIBUTE_TYPE,
        "the name by which an entity is referred to, which identifies without describing",
        aliases=("name", "title", "called"),
        roles=(_slot("l1:role.attribute_bearer", required=True),),
        constraints=(
            Constraint(
                kind="type_level_only",
                expression=(
                    "this item says entities bear names; it holds no name. A stored name "
                    "would be an Individual, which this ontology excludes"
                ),
            ),
        ),
        provenance=_tm2(
            "'name' is the most frequent facet at 75676 occurrences and appears in every "
            "one of the 7 domains"
        ),
    ),
    _l1(
        "l1:attribute.kind",
        L1ItemType.ATTRIBUTE_TYPE,
        "the sub-category an entity belongs to within its own domain",
        aliases=("type", "category", "class", "style"),
        roles=(_slot("l1:role.attribute_bearer", required=True),),
        provenance=_tm2(
            "'type' facet 25958 occurrences; SGD carries type/car_type/event_type/show_type/"
            "fare_type/ride_type as the same attribute under six service-local names"
        ),
    ),
    _l1(
        "l1:attribute.place",
        L1ItemType.ATTRIBUTE_TYPE,
        "where an entity or situation is located, at any granularity",
        aliases=("location", "address", "city", "area", "where"),
        roles=(_slot("l1:role.attribute_bearer", required=True),),
        provenance=_sgd_schema(
            "city (6 services), street_address (6), address (3), location (3) plus "
            "Taskmaster2 location 11461 and sub_location 1893"
        ),
    ),
    _l1(
        "l1:attribute.calendar_position",
        L1ItemType.ATTRIBUTE_TYPE,
        "the day a situation is located on",
        aliases=("date", "day", "when"),
        relations=(Relation(kind=RelationKind.QUALIFIED_BY, target_id="l1:qualifier.time"),),
        roles=(_slot("l1:role.attribute_bearer", required=True),),
        provenance=_sgd_schema(
            "date (4 services), departure_date (3), check_in_date (3), appointment_date (3), "
            "return_date, pickup_date, dropoff_date, leaving_date collapse to one family"
        ),
    ),
    _l1(
        "l1:attribute.clock_position",
        L1ItemType.ATTRIBUTE_TYPE,
        "the time of day a situation is located at, independent of which day",
        aliases=("time", "time of day", "hour"),
        relations=(Relation(kind=RelationKind.QUALIFIED_BY, target_id="l1:qualifier.time"),),
        roles=(_slot("l1:role.attribute_bearer", required=True),),
        constraints=(
            Constraint(
                kind="separate_from_calendar_position",
                expression=(
                    "kept separate because SGD revises them independently: appointment_time "
                    "371 revisions against appointment_date 374, on the same appointments"
                ),
            ),
        ),
        provenance=_sgd_schema(
            "time (3 services), appointment_time (3), pickup_time, leaving_time and four "
            "Flights outbound/inbound time slots; Taskmaster2 time 9087, time_of_day 3874"
        ),
    ),
    _l1(
        "l1:attribute.magnitude",
        L1ItemType.ATTRIBUTE_TYPE,
        "a quantity on an ordered scale, so two values of it can be compared",
        aliases=("amount", "price", "cost", "how much", "how many"),
        roles=(_slot("l1:role.attribute_bearer", required=True),),
        constraints=(
            Constraint(
                kind="ordered",
                expression=(
                    "values are comparable, which is what l1:preference.threshold needs; an "
                    "unordered attribute cannot be the range of a bound"
                ),
            ),
        ),
        provenance=_sgd_schema(
            "price (4 services), total_price (3), fare (2), balance, amount, ride_fare plus "
            "the count family (passengers, party_size, number_of_rooms)"
        ),
    ),
    _l1(
        "l1:attribute.assessment",
        L1ItemType.ATTRIBUTE_TYPE,
        "an evaluative score attributed to an entity by parties other than the current holder",
        aliases=("rating", "score", "stars", "reviews"),
        relations=(_is_a("l1:attribute.magnitude"),),
        roles=(_slot("l1:role.attribute_bearer", required=True),),
        constraints=(
            Constraint(
                kind="not_a_preference",
                expression=(
                    "a third-party rating is a property of the entity; the holder's own "
                    "attitude is l1:preference.affinity and the two must not be merged"
                ),
            ),
        ),
        provenance=_sgd_schema(
            "average_rating (3 services), star_rating; Taskmaster2 rating 2993, score 3262, "
            "star_rating 2083"
        ),
    ),
    _l1(
        "l1:attribute.availability",
        L1ItemType.ATTRIBUTE_TYPE,
        "whether an entity can currently be obtained or used",
        aliases=("available", "in stock", "free", "open"),
        relations=(Relation(kind=RelationKind.QUALIFIED_BY, target_id="l1:qualifier.polarity"),),
        roles=(_slot("l1:role.attribute_bearer", required=True),),
        provenance=_sgd_schema(
            "GetCarsAvailable and Calendar_1 GetAvailableTime make availability the queried "
            "attribute; SYSTEM INFORM_COUNT 1779 reports how much of it there is"
        ),
    ),
)


def build_o_l1() -> L1Freeze:
    """Assemble O_L1, sorted by id.

    Sorting happens here rather than being maintained by hand in the section tuples. The
    freeze validator requires sorted ids so that the digest is a function of content alone;
    if authors also had to keep source order sorted, the sections could not be grouped by
    kind, and grouping is what makes the provenance auditable.
    """
    items = (
        *_ROLES,
        *_QUALIFIER_DIMENSIONS,
        *_TIME_VALUES,
        *_MODAL_VALUES,
        *_POLARITY_VALUES,
        *_SOURCE_STATUS_VALUES,
        *_STANDING_VALUES,
        *_PREDICATE_SENSES,
        *_EVENT_TYPES,
        *_STATE_TYPES,
        *_PREFERENCE_TYPES,
        *_TASK_TYPES,
        *_ATTRIBUTE_TYPES,
    )
    return L1Freeze(
        version=O_L1_VERSION,
        items=tuple(sorted(items, key=lambda entry: entry.item.id)),
    )
