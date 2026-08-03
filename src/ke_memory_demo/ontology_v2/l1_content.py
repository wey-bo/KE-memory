"""O_L1 v2: the atomic layer, with the published sources actually consulted.

v1 authored 67 items from build corpora alone and said plainly that three named sources had
never been opened. They are open now, and each does one job:

- **PropBank 3.4.0** settles predicate senses and role sets. 11204 rolesets were indexed and
  fewer than fifty read; the whole 9087-predicate inventory is *not* here, because a memory
  ontology needs the argument structure of ``prefer.01`` and ``promise.01``, not a verb lexicon.
  The role section is now cross-checked against PropBank's own function tags -- CAU appears on
  285 roles across 278 distinct lemmas, which is what makes ``role.cause`` general rather than
  the single tau-bench attestation v1 deferred on.
- **WordNet 3.0** disambiguates senses and supplies lemmas. 117659 synsets, none imported as a
  type. Its use is: pick which sense of "habit" is meant (``n#05669034`` established custom, not
  ``n#03473966`` religious attire) and take the lemmas of that synset as aliases.
- **schema.org 30.0** supplies type and property *structure*. 1010 classes, none copied by
  name. What it settles is shape: ``knows`` is bi-directional and ``follows`` uni-directional,
  which is why relationship symmetry is a modelled distinction below rather than an assumption.

The build corpora were re-measured rather than cited from v1, so the counts here are this
build's. MSC personas (65245 sentences) is the source of most of the new breadth: 9517 like/enjoy
against 4102 love and 2963 "my favourite" is what makes a strength ordering measurable, and 4357
"I am a <role>", 1830 work-status, 1640 residence, 5307 possession sentences are what make the
state section wider than v1's four items.

What is deliberately absent, unchanged from v1: no domain verticals (restaurant is still the
single most frequent thing in Taskmaster2 at 46133 and still rejected), no speech acts, no
Individuals, no benchmark facts. Breadth here means more *general* types, and a foundation
ontology that admitted ``restaurant`` because it was frequent would have fitted its build corpus.
"""

from __future__ import annotations

from typing import Final

from .models import (
    Constraint,
    ExternalGrounding,
    L1Freeze,
    L1Item,
    L1ItemType,
    OntologyItem,
    OntologyRoleKind,
    Provenance,
    Relation,
    RelationKind,
    RoleSlot,
    SourceKind,
)

O_L1_VERSION: Final[str] = "2.0.0"


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
    grounding: tuple[ExternalGrounding, ...] = (),
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
            grounding=grounding,
        ),
        item_type=item_type,
    )


def _sgd_schema(evidence: str) -> Provenance:
    return Provenance(source=SourceKind.SGD_SCHEMA, evidence=evidence)


def _sgd_acts(evidence: str) -> Provenance:
    return Provenance(source=SourceKind.SGD_DIALOGUE_ACTS, evidence=evidence)


def _tm2(evidence: str) -> Provenance:
    return Provenance(source=SourceKind.TASKMASTER2_ANNOTATIONS, evidence=evidence)


def _tau(evidence: str) -> Provenance:
    return Provenance(source=SourceKind.TAU_BENCH_TOOLS, evidence=evidence)


def _msc(evidence: str) -> Provenance:
    return Provenance(source=SourceKind.MSC_PERSONAS, evidence=evidence)


def _repo(evidence: str) -> Provenance:
    return Provenance(source=SourceKind.REPOSITORY_VOCABULARY, evidence=evidence)


def _pb_source(evidence: str) -> Provenance:
    return Provenance(source=SourceKind.PROPBANK, evidence=evidence)


def _so_source(evidence: str) -> Provenance:
    return Provenance(source=SourceKind.SCHEMAORG, evidence=evidence)


def _pb(reference: str, gloss: str, role_hint: str | None = None) -> ExternalGrounding:
    return ExternalGrounding(
        source=SourceKind.PROPBANK, reference=reference, gloss=gloss, role_hint=role_hint
    )


def _wn(reference: str, gloss: str) -> ExternalGrounding:
    return ExternalGrounding(source=SourceKind.WORDNET, reference=reference, gloss=gloss)


def _so(reference: str, gloss: str) -> ExternalGrounding:
    return ExternalGrounding(source=SourceKind.SCHEMAORG, reference=reference, gloss=gloss)


def _is_a(target: str) -> Relation:
    return Relation(kind=RelationKind.IS_A, target_id=target)


def _qualified_by(target: str) -> Relation:
    return Relation(kind=RelationKind.QUALIFIED_BY, target_id=target)


def _opposite(target: str) -> Relation:
    return Relation(kind=RelationKind.OPPOSITE_OF, target_id=target)


def _ranks_above(target: str) -> Relation:
    return Relation(kind=RelationKind.RANKS_ABOVE, target_id=target)


def _slot(role_id: str, *, required: bool = False, range_id: str | None = None) -> RoleSlot:
    return RoleSlot(role_id=role_id, is_required=required, range_id=range_id)


# --- Roles -------------------------------------------------------------------------------
#
# v1 shipped ten corpus-shaped roles and said PropBank was what would have settled them.
# PropBank's function tags are now the cross-check: PAG 9491 and PPT 10713 confirm the
# agent/theme split, GOL 2482 the recipient, DIR 985 and LOC 617 the location pair, EXT 321 the
# quantity, CAU 285 the cause. The five tags with fewer than fifty roles (TMP 40, AXS 38, ADJ 24,
# DOM 21, ANC 19) were left alone: a role position PropBank itself barely uses is not one a
# memory ontology needs, and importing the full tag set would be exactly the bulk import the
# plan forbids.
#
# Three roles are new. role.cause and role.duration were v1's deferrals. role.beneficiary is
# the "preference held on behalf of another person" gap, and PropBank turns out to have a
# dedicated position for it in the frames that matter: want.01 ARG2 beneficiary, choose.01 ARG3
# benefactive, reserve.01 ARG2 benefactive, buy.01 ARG4 benefactive.
_ROLES: Final[tuple[L1Item, ...]] = (
    _l1(
        "l1:role.agent",
        L1ItemType.ROLE,
        "the participant who initiates the event and whose action brings it about",
        role_kind=OntologyRoleKind.ROLE,
        aliases=("actor", "initiator"),
        provenance=(
            _sgd_acts(
                "USER INFORM 92945 and SYSTEM OFFER 101159 over all 16142 dialogues are acts by "
                "distinct initiators; every intent in schema.json is performed by one of the two"
            ),
            _pb_source(
                "PAG (prototypical agent) tags 9491 of 28619 roles, the second largest tag, so "
                "the position is general rather than corpus-shaped"
            ),
        ),
        grounding=(_pb("choose.01", "choose, pick", "ARG0 PAG chooser"),),
    ),
    _l1(
        "l1:role.holder",
        L1ItemType.ROLE,
        "the participant a state or preference is true of, who need not act for it to hold",
        role_kind=OntologyRoleKind.ROLE,
        aliases=("bearer", "experiencer"),
        provenance=(
            _msc(
                "of 65245 persona sentences 4357 match 'I am a <role>', 1830 a work status and "
                "1640 a residence: states ascribed to a subject who performs no action"
            ),
            _pb_source(
                "prefer.01 ARG0 is 'chooser' with FrameNet rolelink experiencer, and like.01 "
                "ARG0 is 'liker'; the attitude holder is a distinct position from the agent"
            ),
        ),
        grounding=(_pb("like.01", "have affection towards, be fond of", "ARG0 PAG liker"),),
    ),
    _l1(
        "l1:role.theme",
        L1ItemType.ROLE,
        "the entity the predicate is about, created, changed or transferred by the event",
        role_kind=OntologyRoleKind.ROLE,
        aliases=("object", "patient"),
        provenance=(
            _sgd_schema(
                "every transactional intent (24 of 53) names the thing acted on in its "
                "required_slots, for instance TransferMoney requires amount"
            ),
            _pb_source(
                "PPT (prototypical patient) is the single most frequent tag at 10713 of 28619 roles"
            ),
        ),
        grounding=(_pb("prefer.01", "to choose as more desirable", "ARG1 PPT entity chosen"),),
    ),
    _l1(
        "l1:role.recipient",
        L1ItemType.ROLE,
        "the participant who receives the theme, distinct from the agent who sends it",
        role_kind=OntologyRoleKind.ROLE,
        # "beneficiary" was an alias in v1 and is removed: l1:role.beneficiary now owns it, and
        # the two are genuinely different positions -- promise.01 ARG1 is who is told, while
        # want.01 ARG2 is who the wanting is for.
        aliases=("addressee", "receiver"),
        provenance=(
            _sgd_schema(
                "Banks_1 separates account_type from recipient_account_type and "
                "recipient_account_name, so sender and receiver are separate positions"
            ),
            _pb_source("GOL (goal) tags 2482 roles, the third most frequent tag"),
        ),
        grounding=(_pb("promise.01", "promise (roleset name)", "ARG1 GOL person promised to"),),
    ),
    _l1(
        "l1:role.beneficiary",
        L1ItemType.ROLE,
        "the party on whose behalf the predicate holds, who need not be its holder or agent",
        role_kind=OntologyRoleKind.ROLE,
        aliases=("on behalf of", "benefactive", "for whom"),
        relations=(_opposite("l1:role.holder"),),
        provenance=(
            _pb_source(
                "a benefactive position is declared separately from the agent and the recipient "
                "in the frames a memory ontology uses: want.01 ARG2 beneficiary, choose.01 ARG3 "
                "benefactive, reserve.01 ARG2 benefactive, decide.01 ARG2 beneficiary"
            ),
            _msc(
                "39 persona sentences state another party's attitude ('my wife loves fresh "
                "fruit') and 22 an action for another ('i order bras for my daughter'), so the "
                "beneficiary is attested as content and not only as a frame position"
            ),
            _sgd_schema(
                "10 utterances request a service for a named relation ('a Doctor for my "
                "friend'); v1 saw this only as a passenger count and could not separate whose "
                "constraint it was"
            ),
        ),
        grounding=(
            _pb("want.01", "want, desire", "ARG2 GOL beneficiary"),
            _pb("reserve.01", "hold back, set aside", "ARG2 GOL benefactive"),
        ),
    ),
    _l1(
        "l1:role.source_location",
        L1ItemType.ROLE,
        "the place or state a movement or transition starts from",
        role_kind=OntologyRoleKind.ROLE,
        aliases=("origin", "from"),
        provenance=(
            _sgd_schema(
                "origin/from_location/from_station/origin_airport appear as an origin family "
                "across Buses, Flights and RideSharing services"
            ),
            _pb_source("DIR (direction) tags 985 roles, e.g. travel.01 ARG2 start point"),
        ),
        grounding=(_pb("travel.01", "travel, voyaging", "ARG2 DIR start point"),),
    ),
    _l1(
        "l1:role.target_location",
        L1ItemType.ROLE,
        "the place or state a movement or transition ends at",
        role_kind=OntologyRoleKind.ROLE,
        aliases=("destination", "to"),
        relations=(_opposite("l1:role.source_location"),),
        provenance=(
            _sgd_schema(
                "destination appears in 5 services and destination_airport/to_location/"
                "to_station in others; Taskmaster2 records destination1 4018 times"
            ),
            _pb_source("travel.01 ARG4 GOL destination is the paired position to its ARG2"),
        ),
        grounding=(_pb("travel.01", "travel, voyaging", "ARG4 GOL destination"),),
    ),
    _l1(
        "l1:role.instrument",
        L1ItemType.ROLE,
        "the means by which the agent brings the event about, including a tool or channel",
        role_kind=OntologyRoleKind.ROLE,
        aliases=("means", "via"),
        provenance=(
            _tau(
                "retail order changes require payment_method_id and Music services require "
                "playback_device, both a means rather than a theme"
            ),
            _pb_source("MNR (manner) tags 1063 roles, e.g. start.01 ARG2 instrument"),
        ),
        grounding=(_pb("play.01", "play a game", "ARG2 MNR instrument/equipment used"),),
        # schema.org confirms the shape independently: instrument has domain Action and range
        # Thing, i.e. it is a position on the event rather than an attribute of the agent.
    ),
    _l1(
        "l1:role.quantity",
        L1ItemType.ROLE,
        "how many units of the theme the predicate applies to",
        role_kind=OntologyRoleKind.ROLE,
        # "amount" stays off this list: l1:attribute.magnitude owns it, and an alias resolving to
        # both a role and an attribute would make normalization depend on iteration order.
        aliases=("count", "party size", "how many of them"),
        provenance=(
            _sgd_schema(
                "a count family recurs with service-specific names: passengers, travelers, "
                "group_size, party_size, number_of_seats, number_of_tickets, number_of_rooms"
            ),
            _pb_source("EXT (extent) tags 321 roles, the measurement position proper"),
        ),
        grounding=(_pb("postpone.01", "delay (roleset name)", "ARG2 EXT time period, how long"),),
    ),
    _l1(
        "l1:role.duration",
        L1ItemType.ROLE,
        "how long the predicate holds, as an interval length rather than a pair of endpoints",
        role_kind=OntologyRoleKind.ROLE,
        aliases=("how long", "length of time", "for how long"),
        provenance=(
            _pb_source(
                "PropBank has a predicate whose entire sense is duration: last.01 'extend for "
                "some period of time', with ARG2 'period of time' and the alias have-duration. "
                "This is what v1 deferred for want of a measurement construct"
            ),
            _sgd_schema(
                "three slots state a duration directly rather than as boundaries: "
                "approximate_ride_duration, number_of_days, wait_time. v1 saw only the "
                "check_in_date/check_out_date pair and judged duration never directly expressed"
            ),
            _msc(
                "271 persona sentences give a duration explicitly ('i have been married for 10 "
                "years'), and 1497 SGD utterances match 'for N <unit>'"
            ),
        ),
        grounding=(
            _pb("last.01", "extend for some period of time; duration", "ARG2 VSP period of time"),
            _so("schema:duration", "the duration of the item in ISO 8601 duration format"),
        ),
    ),
    _l1(
        "l1:role.cause",
        L1ItemType.ROLE,
        "the state of affairs that brings the predicate about or is given as its grounds",
        role_kind=OntologyRoleKind.ROLE,
        aliases=("because of", "reason", "grounds"),
        provenance=(
            _pb_source(
                "CAU (cause) tags 285 roles across 278 distinct lemmas, so the position is "
                "general. v1 deferred it on a single tau-bench attestation and named PropBank as "
                "what would settle it; cause.01 ARG0 is itself tagged CAU"
            ),
            _msc("69 persona sentences give a reason with 'because' and 26 with 'due to'"),
            _tau(
                "cancel_pending_order takes reason from a closed set of two, which v1 correctly "
                "judged too thin on its own"
            ),
        ),
        grounding=(
            _pb("cause.01", "impelled action", "ARG0 CAU forcer, causer"),
            _pb("plan.01", "expect (roleset name)", "ARG2 CAU grounds for planning"),
        ),
    ),
    _l1(
        "l1:role.attribute_bearer",
        L1ItemType.ROLE,
        "the entity an attribute is predicated of, as distinct from the attribute value",
        role_kind=OntologyRoleKind.ROLE,
        aliases=("subject of attribute",),
        provenance=(
            _tm2(
                "the 3-part annotation names split frame.facet.filler, so the bearer position "
                "is separate from the facet; 'name' fills it 75676 times"
            ),
        ),
    ),
    _l1(
        "l1:role.constraint_on",
        L1ItemType.ROLE,
        "what a preference or requirement restricts, as opposed to the value it restricts it to",
        role_kind=OntologyRoleKind.ROLE,
        aliases=("restricts",),
        provenance=(
            _sgd_schema(
                "search intents pass user restrictions as slot values, e.g. Restaurants_1 "
                "price_range over ['inexpensive'..'very expensive'] narrows a search"
            ),
            _pb_source("limit.01 and restrict.01 both take ARG1 'thing limited' plus ARG2 limit"),
        ),
        grounding=(_pb("restrict.01", "ensure something stays below a certain level", "ARG1 PPT"),),
    ),
    _l1(
        "l1:role.comparison_target",
        L1ItemType.ROLE,
        "the alternative a comparative preference is measured against",
        role_kind=OntologyRoleKind.ROLE,
        # "rather than" is not listed: l1:predicate.rank_alternatives owns it, because it is the
        # comparison marker and the phrase after it is what fills this position.
        aliases=("compared to", "instead of", "as against"),
        provenance=(
            _pb_source(
                "prefer.01 declares ARG2 'entity compared to' as a position distinct from ARG1 "
                "'entity chosen', and favor.01 declares ARG3 'favored over'. v1's "
                "preference.comparative had no slot for the losing alternative"
            ),
            _msc(
                "80 persona sentences name the alternative explicitly ('i like dogs more than "
                "cats') out of 162 that use 'prefer'"
            ),
        ),
        grounding=(
            _pb("prefer.01", "to choose as more desirable", "ARG2 PPT entity compared to"),
            _pb("favor.01", "like or prefer one option, usually over another", "ARG3 VSP over"),
        ),
    ),
    _l1(
        "l1:role.trigger",
        L1ItemType.ROLE,
        "the condition whose satisfaction is what makes a suspended commitment take effect",
        role_kind=OntologyRoleKind.ROLE,
        # "if" is not listed: l1:predicate.suspend_on_condition owns it, because a bare "if" marks
        # the conditioning act and the clause after it is what fills this position.
        # Neither "if" nor "provided that" is listed: l1:predicate.suspend_on_condition owns the
        # conditional markers, and the clause they introduce is what fills this position.
        aliases=("condition", "trigger condition", "the thing it depends on"),
        provenance=(
            _pb_source(
                "condition.01 'to make dependent on a condition' declares ARG2 GOL 'dependent "
                "on', which is the trigger position; depend.01 ARG1 'depended on' is the same "
                "position under a different lemma"
            ),
            _sgd_acts(
                "472 of 329964 utterances condition a request on availability ('i would like to "
                "eat tacos, if available'), 88 use a full if/then frame and 14 use 'as long as' "
                "or 'only if'. v1 read the act labels, which are all unconditional, and "
                "concluded the corpus did not attest it"
            ),
            _msc("21 persona sentences are sentence-initial conditionals"),
        ),
        grounding=(
            _pb("condition.01", "to make dependent on a condition", "ARG2 GOL dependent on"),
            _pb("depend.01", "rely (roleset name)", "ARG1 PPT depended on"),
        ),
    ),
)


# --- Qualifier dimensions ----------------------------------------------------------------
#
# Seven dimensions, each a property of an assertion rather than of its subject. Separate items
# rather than one "metadata" bag because they are independently valued: a negated preference
# reported by the user about a future event is a legal combination of four dimensions, and
# collapsing them would make it unrepresentable.
#
# Two are new. qualifier.strength carries the preference ordering v1 refused; qualifier.frequency
# carries habituality, which v1 could only express as the single time.recurring value.
_DIMENSIONS: Final[tuple[L1Item, ...]] = (
    _l1(
        "l1:qualifier.time",
        L1ItemType.QUALIFIER_DIMENSION,
        "when the assertion's content holds, relative to the moment of assertion",
        aliases=("temporal position", "tense"),
        provenance=(
            _sgd_schema(
                "date and time slots appear in 20 of 26 services under 15 distinct names, and "
                "every value is relative to when the dialogue happened"
            ),
        ),
    ),
    _l1(
        "l1:qualifier.modality",
        L1ItemType.QUALIFIER_DIMENSION,
        "the attitude the speaker takes toward the content, such as asserting or intending it",
        aliases=("attitude", "mood"),
        provenance=(
            _repo(
                "domain.Modality declares 8 values (fact, belief, preference, goal, plan, "
                "instruction, hypothesis, question); v1 admitted 5 and deferred 2"
            ),
        ),
    ),
    _l1(
        "l1:qualifier.polarity",
        L1ItemType.QUALIFIER_DIMENSION,
        "whether the content is affirmed or denied of its subject",
        aliases=("negation",),
        provenance=(
            _sgd_acts(
                "USER NEGATE 11290 against USER AFFIRM 20696 over all 16142 dialogues: a "
                "predicate with no polarity position misreads a third of user turns"
            ),
        ),
    ),
    _l1(
        "l1:qualifier.source_status",
        L1ItemType.QUALIFIER_DIMENSION,
        "who or what the assertion came from, which determines how far it may be trusted",
        aliases=("provenance of claim", "attribution"),
        provenance=(
            _tau(
                "tool returns are observations while user turns are reports; the retail policy "
                "requires confirmation before a write, i.e. the two are not interchangeable"
            ),
        ),
    ),
    _l1(
        "l1:qualifier.assertion_standing",
        L1ItemType.QUALIFIER_DIMENSION,
        "whether the assertion is still the current one or has been displaced by a later turn",
        aliases=("currency", "standing"),
        provenance=(
            _sgd_schema(
                "71.6% of a 5110-dialogue sample revise at least one slot value mid-dialogue, so "
                "a superseded value is the normal case rather than an error state"
            ),
        ),
    ),
    _l1(
        "l1:qualifier.strength",
        L1ItemType.QUALIFIER_DIMENSION,
        "how strongly an attitude is held, as an ordered position rather than a number",
        aliases=("intensity", "degree"),
        provenance=(
            _msc(
                "the affect verbs partition by intensity at measurable scale: 2963 'my "
                "favourite', 4102 love/adore, 9517 like/enjoy, 717 dislike, 269 hate/can't "
                "stand. v1 refused a scale because it read only 'intensifiers are unannotated', "
                "but the verb choice itself is the annotation"
            ),
            _so_source(
                "schema.org models degree as a Rating with bestRating and worstRating bounds "
                "rather than as a bare number, which is why this is a bounded ordinal"
            ),
        ),
        grounding=(
            _so("schema:Rating", "a rating is an evaluation on a numeric scale, such as 1 to 5"),
        ),
    ),
    _l1(
        "l1:qualifier.frequency",
        L1ItemType.QUALIFIER_DIMENSION,
        "how often the content recurs, for a subject who does it more than once",
        aliases=("how often", "habituality"),
        provenance=(
            _msc(
                "295 persona sentences give an explicit frequency ('i get my nails done "
                "weekly') and 926 a frequency adverb (usually/often/always/rarely/never). v1 "
                "counted only the 80 strictest matches and called the evidence its weakest"
            ),
            _so_source(
                "Schedule declares repeatFrequency and repeatCount as separate properties, so a "
                "rate and a tally are distinct rather than one 'recurring' flag"
            ),
        ),
        grounding=(
            _so("schema:repeatFrequency", "defines the frequency at which Events will occur"),
            _wn("n#05669034", "habit, wont: an established custom"),
        ),
    ),
)


# --- Qualifier values --------------------------------------------------------------------
#
# Closed vocabularies, one per dimension. Closed on purpose: a mapper scored against an open
# value set can always invent a value that is not wrong, which makes the score meaningless.
_TIME_VALUES: Final[tuple[L1Item, ...]] = (
    _l1(
        "l1:time.before_assertion",
        L1ItemType.QUALIFIER_VALUE,
        "the content held at a time earlier than the assertion",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("past", "previously"),
        relations=(
            _qualified_by("l1:qualifier.time"),
            _opposite("l1:time.after_assertion"),
        ),
        provenance=(
            _msc(
                "72 'i moved', 81 'i graduated', 46 'i met': completed events dominate persona "
                "narration"
            ),
        ),
    ),
    _l1(
        "l1:time.at_assertion",
        L1ItemType.QUALIFIER_VALUE,
        "the content holds at the moment of assertion",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("present", "currently"),
        relations=(_qualified_by("l1:qualifier.time"),),
        provenance=(
            _msc(
                "1640 residence and 1830 work-status sentences are stated in present "
                "tense as things that are the case now"
            ),
        ),
    ),
    _l1(
        "l1:time.after_assertion",
        L1ItemType.QUALIFIER_VALUE,
        "the content is expected or intended to hold later than the assertion",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("future", "later", "upcoming"),
        relations=(_qualified_by("l1:qualifier.time"),),
        provenance=(
            _msc("775 'i want to', 275 'i will/am going to', 94 'someday/one day/in the future'"),
        ),
    ),
    _l1(
        "l1:time.spanning",
        L1ItemType.QUALIFIER_VALUE,
        "the content holds across an interval rather than at a point",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("interval", "ongoing", "throughout"),
        relations=(_qualified_by("l1:qualifier.time"),),
        provenance=(
            _sgd_schema(
                "check_in_date/check_out_date and available_start_time/"
                "available_end_time are boundary pairs describing one interval"
            ),
            _msc("62 'since <point>' sentences state an interval by its start alone"),
        ),
    ),
    _l1(
        "l1:time.recurring",
        L1ItemType.QUALIFIER_VALUE,
        "the content holds repeatedly rather than once",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("repeatedly", "each time"),
        relations=(_qualified_by("l1:qualifier.time"), _qualified_by("l1:qualifier.frequency")),
        provenance=(
            _msc("295 explicit-frequency sentences describe recurrence rather than one occasion"),
        ),
    ),
    _l1(
        "l1:time.unspecified",
        L1ItemType.QUALIFIER_VALUE,
        "the assertion fixes no time and none may be inferred",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("timeless", "no time given"),
        relations=(_qualified_by("l1:qualifier.time"),),
        # Present so that "no time stated" is a recorded decision rather than a missing field: an
        # absent qualifier and an explicitly timeless claim are different mapper outcomes.
        provenance=(
            _msc(
                "4357 'I am a <role>' sentences state a standing fact with no time reference at all"
            ),
        ),
    ),
)


# The modality vocabulary. v1 admitted five values and deferred hypothesis and question because
# no build corpus attested them and admitting a value on the strength of an existing enum would
# be inventing coverage. Both are admitted now, and the reason is source evidence rather than a
# change of heart about the enum: PropBank distinguishes the senses lexically, which means the
# distinction is one English marks rather than one this project needs.
_MODALITY_VALUES: Final[tuple[L1Item, ...]] = (
    _l1(
        "l1:modality.asserted",
        L1ItemType.QUALIFIER_VALUE,
        "presented as fact about the world, not as an attitude toward it",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("stated as fact", "factual"),
        relations=(_qualified_by("l1:qualifier.modality"),),
        provenance=(_sgd_acts("USER INFORM 92945 is the single most frequent user act"),),
    ),
    _l1(
        "l1:modality.believed",
        L1ItemType.QUALIFIER_VALUE,
        "held as the speaker's belief, which they present as possibly mistaken",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("thinks", "believes", "as far as they know"),
        relations=(_qualified_by("l1:qualifier.modality"),),
        provenance=(
            _msc("232 persona sentences use 'i think/believe/guess/suppose'"),
            _pb_source(
                "feel.02 'believe' and assume.02 'believe' are separate rolesets from feel.01 "
                "'experience emotion' and assume.01 'acquire', so belief is a distinct sense "
                "rather than a hedge on an assertion"
            ),
        ),
        grounding=(_pb("feel.02", "believe (roleset name)", "ARG1 PPT belief"),),
    ),
    _l1(
        "l1:modality.desired",
        L1ItemType.QUALIFIER_VALUE,
        "wanted by the holder without a commitment to bring it about",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("wants", "would like", "wishes"),
        relations=(_qualified_by("l1:qualifier.modality"),),
        provenance=(
            _msc("775 'i want to' and 126 'i hope/wish' sentences"),
            _pb_source(
                "want.01 'want, desire' and wish.01 'wish, desire' take a thing wanted, with no "
                "position for a plan; intend.01 is the roleset that adds one"
            ),
        ),
        grounding=(_pb("want.01", "want, desire", "ARG1 PPT thing wanted"),),
    ),
    _l1(
        "l1:modality.intended",
        L1ItemType.QUALIFIER_VALUE,
        "the holder has settled on bringing it about, beyond merely wanting it",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        # "is going to" is not listed: l1:task.declared_intention owns it, because the phrase
        # introduces the thing intended rather than marking the attitude taken toward it. What
        # belongs here is the bare modal reading.
        aliases=("intends", "settled on", "means to"),
        relations=(_qualified_by("l1:qualifier.modality"),),
        provenance=(
            _msc("86 'i plan/hope to' and 275 'i will / am going to' sentences"),
            _pb_source(
                "intend.01 'intend, plan, on purpose' declares ARG0 planner and ARG1 'intent, "
                "thing planned' -- a settled plan, distinct from want.01's bare desire"
            ),
        ),
        grounding=(_pb("intend.01", "intend, plan, on purpose, intent", "ARG1 PPT thing planned"),),
    ),
    _l1(
        "l1:modality.directed",
        L1ItemType.QUALIFIER_VALUE,
        "addressed to the other party as something they are to do",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("instructs", "asks them to", "directive"),
        relations=(_qualified_by("l1:qualifier.modality"),),
        provenance=(
            _sgd_acts(
                "USER REQUEST 33612: the user directs the system to act rather than "
                "reporting that it did"
            ),
        ),
    ),
    _l1(
        "l1:modality.hypothesis",
        L1ItemType.QUALIFIER_VALUE,
        "entertained as a supposition whose truth the holder does not assert",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("supposing", "what if", "hypothetically"),
        relations=(_qualified_by("l1:qualifier.modality"),),
        provenance=(
            _pb_source(
                "PropBank separates supposition from belief lexically: suppose.01 'think, "
                "assume' takes ARG1 'thing thought about', hypothesize.01 'make an educated "
                "guess' takes ARG1 'hypothesis', and imagine.01 is 'create in mental space'. v1 "
                "deferred this value because no corpus attested it; a three-way lexical "
                "distinction in the reference frame set is the attestation it was waiting for"
            ),
            _msc(
                "63 persona sentences use maybe/probably/might and 169 a would-frame ('i would "
                "love to still work'), which state a supposition rather than a belief"
            ),
            _repo(
                "domain.Modality.HYPOTHESIS exists, so admitting it restores compatibility "
                "that v1 chose to forgo rather than invent"
            ),
        ),
        grounding=(
            _pb("hypothesize.01", "make an educated guess", "ARG1 PPT hypothesis"),
            _pb("suppose.01", "think, assume", "ARG1 PPT thing thought about"),
            _wn(
                "n#05888929",
                "hypothesis, possibility, theory: a tentative insight, not yet verified",
            ),
        ),
    ),
    _l1(
        "l1:modality.question",
        L1ItemType.QUALIFIER_VALUE,
        "the content is what the holder wants to know, with its truth left open",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("open question", "wants to know", "unresolved"),
        relations=(_qualified_by("l1:qualifier.modality"),),
        provenance=(
            _pb_source(
                "wonder.01 'think about, ponder' takes ARG1 'thought' and is a separate roleset "
                "from ask.01 'ask a question', which takes ARG2 GOL hearer. The hearer position "
                "is what makes ask.01 a speech act and wonder.01 a mental state -- so an "
                "unresolved question can be content without the act being content, which is "
                "precisely the open question v1 recorded"
            ),
            _sgd_acts(
                "21 utterances express an unresolved question as content ('i wonder what my "
                "balance is', \"i'm not sure if that's really my taste\") as opposed to the "
                "33612 REQUEST acts, which v1 rightly declined to admit as modality"
            ),
            _repo("domain.Modality.QUESTION exists and was deferred, not rejected"),
        ),
        grounding=(
            _pb("wonder.01", "think about, ponder", "ARG1 PAG thought"),
            _wn("n#07193596", "question, inquiry, query: an instance of questioning"),
        ),
    ),
)


_POLARITY_VALUES: Final[tuple[L1Item, ...]] = (
    _l1(
        "l1:polarity.affirmed",
        L1ItemType.QUALIFIER_VALUE,
        "the content is asserted to hold of its subject",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("positive", "yes"),
        relations=(
            _qualified_by("l1:qualifier.polarity"),
            _opposite("l1:polarity.denied"),
        ),
        provenance=(_sgd_acts("USER AFFIRM 20696 and AFFIRM_INTENT 4358"),),
    ),
    _l1(
        "l1:polarity.denied",
        L1ItemType.QUALIFIER_VALUE,
        "the content is asserted not to hold of its subject",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("negative", "no", "not"),
        relations=(_qualified_by("l1:qualifier.polarity"),),
        provenance=(
            _sgd_acts("USER NEGATE 11290 and NEGATE_INTENT 5425"),
            _msc("717 'i do not like' and 188 'i cannot' sentences"),
        ),
    ),
    _l1(
        "l1:polarity.indeterminate",
        L1ItemType.QUALIFIER_VALUE,
        "the assertion leaves it open whether the content holds",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("unknown",),
        relations=(_qualified_by("l1:qualifier.polarity"),),
        provenance=(_repo("domain.Polarity declares exactly positive/negative/unknown"),),
    ),
)


_SOURCE_STATUS_VALUES: Final[tuple[L1Item, ...]] = (
    _l1(
        "l1:source_status.user_reported",
        L1ItemType.QUALIFIER_VALUE,
        "stated by the user about themselves or their world, with no independent check",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("user said", "self-reported"),
        relations=(_qualified_by("l1:qualifier.source_status"),),
        provenance=(_msc("all 65245 persona sentences are self-report"),),
    ),
    _l1(
        "l1:source_status.assistant_asserted",
        L1ItemType.QUALIFIER_VALUE,
        "stated by the assistant, which makes it a claim about the world and not an observation",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("assistant said", "agent claim"),
        relations=(_qualified_by("l1:qualifier.source_status"),),
        provenance=(_sgd_acts("SYSTEM INFORM 32885 and SYSTEM OFFER 101159"),),
    ),
    _l1(
        "l1:source_status.tool_observed",
        L1ItemType.QUALIFIER_VALUE,
        "returned by a tool or system of record rather than said by either party",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("tool result", "system of record", "observed"),
        relations=(_qualified_by("l1:qualifier.source_status"),),
        provenance=(
            _tau("retail 17 tools and airline 15 tools return state the user did not assert"),
        ),
    ),
    _l1(
        "l1:source_status.confirmed_by_both",
        L1ItemType.QUALIFIER_VALUE,
        "asserted by one party and explicitly acknowledged by the other",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("mutually confirmed", "agreed"),
        relations=(_qualified_by("l1:qualifier.source_status"),),
        provenance=(
            _sgd_acts(
                "SYSTEM CONFIRM 83259 followed by USER AFFIRM 20696 is the confirmation handshake"
            ),
            _tau("the retail policy requires explicit user confirmation before any write"),
        ),
    ),
    _l1(
        "l1:source_status.derived",
        L1ItemType.QUALIFIER_VALUE,
        "inferred by the system from other content rather than obtained from any party",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("inferred", "computed"),
        relations=(_qualified_by("l1:qualifier.source_status"),),
        provenance=(
            _repo(
                "domain.Speaker declares 'derived' alongside user/assistant/tool, so "
                "an inference must be distinguishable from a report"
            ),
        ),
    ),
)


_STANDING_VALUES: Final[tuple[L1Item, ...]] = (
    _l1(
        "l1:standing.current",
        L1ItemType.QUALIFIER_VALUE,
        "the latest assertion on this content and the one that holds",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("active", "in force"),
        relations=(
            _qualified_by("l1:qualifier.assertion_standing"),
            _opposite("l1:standing.superseded"),
        ),
        provenance=(_repo("domain.Lifecycle.ACTIVE"),),
    ),
    _l1(
        "l1:standing.superseded",
        L1ItemType.QUALIFIER_VALUE,
        "displaced by a later assertion about the same content",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("replaced", "outdated", "no longer current"),
        relations=(_qualified_by("l1:qualifier.assertion_standing"),),
        provenance=(
            _sgd_schema("71.6% of a 5110-dialogue sample revise a slot value mid-dialogue"),
        ),
    ),
    _l1(
        "l1:standing.retracted",
        L1ItemType.QUALIFIER_VALUE,
        "withdrawn by the party who asserted it, rather than replaced with a new value",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("withdrawn", "taken back", "never mind"),
        relations=(_qualified_by("l1:qualifier.assertion_standing"),),
        provenance=(
            _sgd_acts("USER NEGATE_INTENT 5425 abandons an intent rather than revising a slot"),
            _repo("domain.Lifecycle.RETRACTED is distinct from SUPERSEDED"),
        ),
    ),
    _l1(
        "l1:standing.contested",
        L1ItemType.QUALIFIER_VALUE,
        "two assertions conflict and neither has displaced the other",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("contradicted", "in conflict"),
        relations=(_qualified_by("l1:qualifier.assertion_standing"),),
        # New in v2. domain.Lifecycle has CONTRADICTED and v1 admitted only three of its five
        # values, which left conflict expressible at L2 but not at the layer where the two
        # conflicting assertions actually live.
        provenance=(
            _repo(
                "domain.Lifecycle.CONTRADICTED and .UNCERTAIN both exist; v1 carried neither, "
                "so an unresolved conflict had no atomic-layer standing"
            ),
            _tau(
                "cross-checking a user report against a tool return can disagree, and the "
                "retail policy has the agent stop rather than pick a side"
            ),
        ),
    ),
)


# The strength ordering. This is the item v1 refused, and the reason it is admissible now is not
# that intensifiers became annotated -- they did not. It is that the *verb choice* is itself the
# annotation, and it partitions at scale: 4102 love against 9517 like against 269 hate is a
# lexical distinction the corpus makes, not an ordinal this author invented. The ranks form a
# chain over positive affect; negative affect is polarity times strength, not extra ranks, which
# is why hate maps to strength.strong with polarity.denied rather than to a negative rank.
_STRENGTH_VALUES: Final[tuple[L1Item, ...]] = (
    _l1(
        "l1:strength.paramount",
        L1ItemType.QUALIFIER_VALUE,
        "the single most strongly held option of its kind, admitting no equal",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("favourite", "favorite", "most of all", "above all"),
        relations=(_qualified_by("l1:qualifier.strength"), _ranks_above("l1:strength.strong")),
        constraints=(
            Constraint(
                kind="uniqueness",
                expression=(
                    "at most one paramount value may be current per holder and attribute; a "
                    "second one supersedes the first rather than joining it"
                ),
            ),
        ),
        provenance=(
            _msc(
                "2963 'my favourite/favorite' sentences, a superlative frame distinct from the "
                "4102 love sentences because it excludes ties"
            ),
        ),
        grounding=(
            _wn("n#07498210", "preference, penchant, predilection, taste: a strong liking"),
        ),
    ),
    _l1(
        "l1:strength.strong",
        L1ItemType.QUALIFIER_VALUE,
        "held strongly enough that the holder volunteers it without prompting",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        # "love" is not listed: l1:predicate.hold_attitude owns the affect verbs, since "I love X"
        # names the attitude. The degree markers proper are the adverbial forms.
        aliases=("really like", "can't stand", "intensely", "very much"),
        relations=(_qualified_by("l1:qualifier.strength"), _ranks_above("l1:strength.moderate")),
        provenance=(
            _msc(
                "4102 love/adore and 269 hate/can't-stand sentences, plus 104 with an "
                "intensifier on a weaker verb ('i really like football')"
            ),
            _pb_source(
                "love.01 and adore.01 are separate rolesets from like.01, so the "
                "intensity difference is lexicalized rather than adverbial"
            ),
        ),
        grounding=(
            _pb("love.01", "object of affection", "ARG1 PPT loved"),
            _wn("n#05036394", "intensity, intensiveness: high level or degree"),
        ),
    ),
    _l1(
        "l1:strength.moderate",
        L1ItemType.QUALIFIER_VALUE,
        "held as a genuine preference without being emphasised",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        # "like" and "enjoy" are not listed: l1:predicate.hold_attitude owns those verbs, because
        # "I like X" names the attitude and only implies its degree. What is unambiguously a
        # degree marker is the hedged form, so that is what this value claims.
        aliases=("quite like", "fairly keen on", "moderately"),
        relations=(_qualified_by("l1:qualifier.strength"), _ranks_above("l1:strength.tolerant")),
        provenance=(
            _msc(
                "9517 like/enjoy sentences, the largest affect band and the default reading "
                "when no intensifier is present"
            ),
        ),
        grounding=(_pb("like.01", "have affection towards, be fond of, enjoy", "ARG1 PPT object"),),
    ),
    _l1(
        "l1:strength.tolerant",
        L1ItemType.QUALIFIER_VALUE,
        "accepted without being preferred, so it may be chosen but will not be sought",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("don't mind", "acceptable", "fine either way"),
        relations=(_qualified_by("l1:qualifier.strength"),),
        provenance=(
            _pb_source(
                "tolerate.01 'put up with' and mind.01 'be bothered by' are distinct rolesets "
                "from like.01, so acceptance is a separate attitude rather than weak liking"
            ),
            _msc(
                "the weakest band in the corpus: 6 sentences match 'i don't mind' / 'it's ok'. "
                "The rank exists because SGD attests it far better -- 14 'as long as' and 472 "
                "'if available' utterances are acceptance rather than preference -- but the "
                "persona evidence alone would not have carried it"
            ),
            _sgd_acts(
                "14 utterances state tolerance directly ('any kind of movie is fine, just "
                "as long as it's fun')"
            ),
        ),
        grounding=(_pb("tolerate.01", "tolerate, put up with, the act of tolerating"),),
    ),
)


# Frequency values. v1 had one recurrence marker; schema.org's separation of repeatFrequency from
# repeatCount is what makes a rate distinguishable from a tally, and the persona adverbs give the
# bands. Deliberately coarse: 'weekly' and 'every Tuesday' are the same band here, because a
# finer scale would need a calendar model and would put literal schedules into a type ontology.
_FREQUENCY_VALUES: Final[tuple[L1Item, ...]] = (
    _l1(
        "l1:frequency.invariant",
        L1ItemType.QUALIFIER_VALUE,
        "holds on every relevant occasion, so an exception would be a contradiction",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("always", "every time", "without exception"),
        relations=(_qualified_by("l1:qualifier.frequency"), _ranks_above("l1:frequency.habitual")),
        provenance=(
            _msc(
                "'always' and 'never' occur within the 926 frequency-adverb sentences "
                "as the two poles that admit no exception"
            ),
        ),
    ),
    _l1(
        "l1:frequency.habitual",
        L1ItemType.QUALIFIER_VALUE,
        "holds on most relevant occasions, as a settled pattern the holder would confirm",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("usually", "regularly", "as a rule"),
        relations=(
            _qualified_by("l1:qualifier.frequency"),
            _ranks_above("l1:frequency.occasional"),
        ),
        provenance=(
            _msc(
                "295 explicit-frequency sentences ('daily', 'every week', 'once a week') plus "
                "the usually/often subset of the 926 adverb sentences"
            ),
            _pb_source(
                "use.02 'accustomed to' takes ARG1 'custom', and frequent.02 is "
                "'occurring often': habituality is lexicalized"
            ),
        ),
        grounding=(
            _wn("n#05669034", "habit, wont: an established custom"),
            _pb("use.02", "accustomed to", "ARG1 PPT custom"),
        ),
    ),
    _l1(
        "l1:frequency.occasional",
        L1ItemType.QUALIFIER_VALUE,
        "recurs but on a minority of relevant occasions, so it predicts little",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("sometimes", "occasionally", "now and then"),
        relations=(_qualified_by("l1:qualifier.frequency"), _ranks_above("l1:frequency.rare")),
        provenance=(
            _msc("the sometimes/occasionally subset of the 926 frequency-adverb sentences"),
        ),
    ),
    _l1(
        "l1:frequency.rare",
        L1ItemType.QUALIFIER_VALUE,
        "recurs seldom enough that the holder marks it as unusual",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("rarely", "seldom", "hardly ever"),
        relations=(_qualified_by("l1:qualifier.frequency"),),
        provenance=(
            _msc(
                "the rarely/never subset of the 926 adverb sentences; 'i have been to canada "
                "but have never lived there' is the shape"
            ),
            _pb_source(
                "usual.01 'commonly occurring' takes ARG2 'entity arg1 is unusual for', "
                "so rarity is stated relative to a reference class"
            ),
        ),
        grounding=(_pb("usual.01", "commonly occurring", "ARG2 GOL unusual for"),),
    ),
)


# --- Attribute types ---------------------------------------------------------------------
#
# Nine facet families that recur across unrelated domains. The cross-domain test is what keeps
# this section from becoming Taskmaster2's annotation list: amenity at 19235 fails it (lodging
# only) while kind at 25958 passes it. schema.org is consulted here for structure and for nothing
# else -- Thing/Place/Person/Event/Intangible is a five-way split at the top of a 1010-class
# hierarchy, and it is the split that justifies place and designation being separate facets
# rather than one "identity" bag. No schema.org class name appears as an id.
_ATTRIBUTES: Final[tuple[L1Item, ...]] = (
    _l1(
        "l1:attribute.designation",
        L1ItemType.ATTRIBUTE_TYPE,
        "how an entity is picked out and referred to, without recording any particular name",
        aliases=("name attribute", "identifier attribute", "what it is called"),
        roles=(_slot("l1:role.attribute_bearer", required=True),),
        provenance=(
            _tm2("'name' is the most frequent facet at 75676 occurrences across all 7 domains"),
            _so_source(
                "schema:name has domain Thing, i.e. it is the one property every type "
                "carries, which is why this is a facet and not a domain slot"
            ),
        ),
        grounding=(_so("schema:name", "the name of the item"),),
        constraints=(
            Constraint(
                kind="exclusion",
                expression=(
                    "records that an entity is designated, never which designation it bears; a "
                    "particular name is an Individual and is excluded from both layers"
                ),
            ),
            Constraint(
                kind="type_level_only",
                expression=(
                    "this item says entities bear names; it holds no name. A stored name would be an "
                    "Individual, which this ontology excludes"
                ),
            ),
        ),
    ),
    _l1(
        "l1:attribute.kind",
        L1ItemType.ATTRIBUTE_TYPE,
        "which sub-category of its type an entity falls into",
        aliases=("category", "type attribute", "what sort", "genre"),
        roles=(_slot("l1:role.attribute_bearer", required=True),),
        provenance=(
            _tm2(
                "'type' is the second most frequent facet at 25958 and recurs in every domain, "
                "unlike cuisine (12981, food only) or amenity (19235, lodging only)"
            ),
        ),
    ),
    _l1(
        "l1:attribute.place",
        L1ItemType.ATTRIBUTE_TYPE,
        "where an entity is, as a property of the entity rather than a movement endpoint",
        aliases=("location attribute", "where it is", "area", "whereabouts"),
        roles=(_slot("l1:role.attribute_bearer", required=True),),
        provenance=(
            _tm2("'location' 11461 occurrences across domains"),
            _sgd_schema("city appears in 12 of 26 services under city/location/area names"),
            _so_source(
                "schema:Place is a direct subclass of Thing, parallel to Person and "
                "Event, so location is a top-level facet rather than a detail of one type"
            ),
        ),
        grounding=(_so("schema:Place", "entities that have a somewhat fixed, physical extension"),),
    ),
    _l1(
        "l1:attribute.calendar_position",
        L1ItemType.ATTRIBUTE_TYPE,
        "which day an entity or event falls on, at day granularity or coarser",
        aliases=("date attribute", "which day", "when in the calendar"),
        roles=(_slot("l1:role.attribute_bearer", required=True),),
        provenance=(
            _sgd_schema(
                "five date slots differ only in the declaring service: departure_date, "
                "check_in_date, appointment_date, pickup_date, show_date"
            ),
            _tm2("date facets total 9651 across domains"),
        ),
        relations=(_qualified_by("l1:qualifier.time"),),
    ),
    _l1(
        "l1:attribute.clock_position",
        L1ItemType.ATTRIBUTE_TYPE,
        "which time of day an entity or event falls at, finer than a calendar day",
        aliases=("time attribute", "time of day", "what time"),
        roles=(_slot("l1:role.attribute_bearer", required=True),),
        provenance=(
            _sgd_schema(
                "time slots are declared separately from date slots in every service "
                "that has both, so the two granularities are not one facet"
            ),
            _tm2("time facets total 9087, close to but independent of the 9651 date facets"),
        ),
        constraints=(
            Constraint(
                kind="separate_from_calendar_position",
                expression=(
                    "kept separate because SGD revises them independently: appointment_time 371 "
                    "revisions against appointment_date 374, on the same appointments"
                ),
            ),
        ),
        relations=(_qualified_by("l1:qualifier.time"),),
    ),
    _l1(
        "l1:attribute.magnitude",
        L1ItemType.ATTRIBUTE_TYPE,
        "an ordered quantity of an entity, where more and less are meaningful",
        aliases=("amount", "how much", "price attribute", "size", "quantity attribute"),
        roles=(_slot("l1:role.attribute_bearer", required=True),),
        provenance=(
            _tm2("price_range 6978 occurrences; hotel1_detail.price_per_night 1580"),
            _sgd_schema(
                "price_range in Restaurants_1 and seating_class in Flights_1/2 are "
                "ordered categoricals, not free values"
            ),
            _so_source(
                "schema:QuantitativeValue is a StructuredValue with a value plus bounds, "
                "which is why orderedness is part of the facet and not a note about it"
            ),
        ),
        grounding=(
            _so("schema:QuantitativeValue", "a point value or interval for characteristics"),
        ),
        constraints=(
            Constraint(
                kind="ordered",
                expression=(
                    "values are comparable, which is what l1:preference.threshold needs; an unordered "
                    "attribute cannot be the range of a bound"
                ),
            ),
        ),
    ),
    _l1(
        "l1:attribute.assessment",
        L1ItemType.ATTRIBUTE_TYPE,
        "an evaluative judgement of an entity, attributed to whoever made it",
        aliases=("rating", "review score", "how good it is", "quality judgement"),
        roles=(
            _slot("l1:role.attribute_bearer", required=True),
            _slot("l1:role.holder"),
        ),
        provenance=(
            _tm2("'rating' 2993 occurrences across restaurant, hotel and movie frames"),
            _so_source(
                "schema:Rating carries bestRating and worstRating, so an assessment is "
                "only interpretable against the scale it was made on"
            ),
        ),
        grounding=(_so("schema:Rating", "an evaluation on a numeric scale, such as 1 to 5 stars"),),
        constraints=(
            Constraint(
                kind="attribution",
                expression=(
                    "an assessment without a holder is not a fact about the entity; the holder "
                    "slot exists so a third-party rating and the user's own opinion stay distinct"
                ),
            ),
            Constraint(
                kind="not_a_preference",
                expression=(
                    "a third-party rating is a property of the entity; the holder's own attitude is "
                    "l1:preference.affinity and the two must not be merged"
                ),
            ),
        ),
        relations=(_is_a("l1:attribute.magnitude"),),
    ),
    _l1(
        "l1:attribute.availability",
        L1ItemType.ATTRIBUTE_TYPE,
        "whether an entity can be had or used at a given time",
        aliases=("in stock", "free or taken", "can be booked", "obtainable"),
        roles=(_slot("l1:role.attribute_bearer", required=True),),
        provenance=(
            _sgd_schema(
                "available_start_time/available_end_time in Calendar_1, and every search "
                "intent returns a candidate set that may be empty"
            ),
            _sgd_acts(
                "SYSTEM NOTIFY_FAILURE 2398 and INFORM_COUNT 14486 both report on "
                "availability rather than on the entity"
            ),
        ),
        relations=(_qualified_by("l1:qualifier.polarity"),),
    ),
    _l1(
        "l1:attribute.affiliation",
        L1ItemType.ATTRIBUTE_TYPE,
        "which organisation or group an entity belongs to or acts within",
        aliases=("employer", "organisation", "belongs to", "member of"),
        roles=(_slot("l1:role.attribute_bearer", required=True),),
        # New in v2. v1 had no way to say where somebody works other than through possession,
        # which conflates having a job with owning a thing.
        provenance=(
            _msc(
                "1830 persona sentences state a work affiliation ('i work as/at/for'), the "
                "second largest single pattern after 'i am a <role>' at 4357"
            ),
            _pb_source(
                "work.01 declares ARG2 GOL 'employer' as a position distinct from ARG1 "
                "'job, project', so employer and occupation are separate facets"
            ),
            _so_source(
                "schema:Organization is a direct subclass of Thing and OrganizationRole "
                "reifies membership, so affiliation is a relation to a type of entity"
            ),
        ),
        grounding=(
            _pb("work.01", "work, being employed", "ARG2 GOL employer"),
            _so("schema:Organization", "an organization such as a school, NGO, corporation"),
        ),
    ),
)


# --- Predicate senses --------------------------------------------------------------------
#
# This is the section v1 could not do properly. Its seven senses were "clustered from SGD intent
# verbs" and claimed no synset or roleset id, because neither source was available. Every sense
# here names the PropBank roleset that fixes it and takes its role slots from that roleset's
# numbered arguments rather than from a slot-name family.
#
# Thirteen senses, not 9087. The selection rule is: a sense earns an id if a person states it
# about themselves or their commitments in ordinary conversation, and if its argument structure
# differs from the senses already present. That excludes almost everything -- ct.01, whipple.01
# and aao.01 are real PropBank rolesets and belong to a clinical register no memory ontology
# reaches. Where PropBank splits a lemma finer than memory needs, the senses are merged and the
# merge is recorded: buy.01 and pay.01 and sell.01 are one transfer_value here, because the
# difference between them is which party the speaker is, and that is the agent slot.
_PREDICATES: Final[tuple[L1Item, ...]] = (
    _l1(
        "l1:predicate.hold_attitude",
        L1ItemType.PREDICATE_SENSE,
        "to have a standing positive or negative attitude toward something",
        role_kind=OntologyRoleKind.OPERATOR,
        aliases=("like", "love", "enjoy", "hate", "be fond of"),
        roles=(
            _slot("l1:role.holder", required=True),
            _slot("l1:role.theme", required=True),
            _slot("l1:role.beneficiary"),
        ),
        relations=(
            _qualified_by("l1:qualifier.strength"),
            _qualified_by("l1:qualifier.polarity"),
        ),
        provenance=(
            _pb_source(
                "like.01 'have affection towards, be fond of, enjoy (habitually)' with ARG0 "
                "liker and ARG1 'object of affection'. The two-argument structure is what this "
                "sense is, and hate.01 and dislike.01 share it with polarity reversed"
            ),
            _msc("9517 like/enjoy, 4102 love, 717 dislike, 269 hate sentences"),
        ),
        grounding=(
            _pb("like.01", "have affection towards, be fond of, enjoy (habitually)", "ARG0/ARG1"),
            _wn("v#01826498", "prefer: like better; value more highly"),
        ),
        constraints=(
            Constraint(
                kind="polarity_bearing",
                expression=(
                    "an instance must carry a l1:qualifier.polarity value, because the same predicate "
                    "covers 13819 like-patterns and 970 dislike-patterns in MSC"
                ),
            ),
        ),
    ),
    _l1(
        "l1:predicate.rank_alternatives",
        L1ItemType.PREDICATE_SENSE,
        "to hold one option above another named option, rather than in isolation",
        role_kind=OntologyRoleKind.OPERATOR,
        aliases=("prefer", "rather than", "favour over", "would sooner"),
        roles=(
            _slot("l1:role.holder", required=True),
            _slot("l1:role.theme", required=True),
            _slot("l1:role.comparison_target", required=True),
        ),
        relations=(
            Relation(kind=RelationKind.SPECIALIZES_SENSE, target_id="l1:predicate.hold_attitude"),
        ),
        # Split from hold_attitude on PropBank's authority, not on intuition: prefer.01 declares a
        # third argument that like.01 does not have, and a comparison whose loser is unrecoverable
        # is a different memory item from a bare liking.
        provenance=(
            _pb_source(
                "prefer.01 'to choose as more desirable' has ARG2 'entity compared to' where "
                "like.01 stops at ARG1; favor.01 goes further with ARG3 'favored over' and ARG4 "
                "'superset of things arg1 is favored amongst'"
            ),
            _msc("162 'prefer' and 80 explicit-comparison sentences"),
            _sgd_acts(
                "USER SELECT 25869 and REQUEST_ALTS 11208 are choices among presented options"
            ),
        ),
        grounding=(
            _pb("prefer.01", "to choose as more desirable", "ARG2 PPT entity compared to"),
            _wn("v#00679389", "choose, prefer, opt: select as an alternative over another"),
        ),
    ),
    _l1(
        "l1:predicate.commit_to_arrangement",
        L1ItemType.PREDICATE_SENSE,
        "to bind oneself to a future arrangement, so that failing to honour it is a lapse",
        role_kind=OntologyRoleKind.OPERATOR,
        aliases=("book", "reserve", "promise", "commit", "agree to"),
        roles=(
            _slot("l1:role.agent", required=True),
            _slot("l1:role.theme", required=True),
            _slot("l1:role.beneficiary"),
            _slot("l1:role.recipient"),
            _slot("l1:role.trigger"),
        ),
        relations=(_qualified_by("l1:qualifier.modality"),),
        provenance=(
            _pb_source(
                "reserve.01 'hold back, set aside' with ARG2 benefactive, and promise.01 with "
                "ARG1 GOL 'person promised to' plus ARG2 'promised action'. The recipient and "
                "beneficiary are separate positions in the reference frames, which is why both "
                "slots are here"
            ),
            _sgd_schema("7 of 53 intents are Reserve* and 5 are Buy*, all transactional"),
        ),
        grounding=(
            _pb("reserve.01", "hold back, set aside", "ARG0/ARG1/ARG2 benefactive"),
            _pb("promise.01", "promise (roleset name)", "ARG1 GOL person promised to"),
            _wn(
                "n#07226545",
                "promise: a verbal commitment by one person to another agreeing to "
                "do something in the future",
            ),
        ),
        constraints=(
            Constraint(
                kind="requires_confirmation",
                expression=(
                    "a commitment is only complete when the counterparty confirms; tau-bench retail "
                    "policy requires explicit user 'yes' before any write"
                ),
            ),
            Constraint(
                kind="creates_revisable_obligation",
                expression=(
                    "an arrangement may later be modified or cancelled, so an instance is not "
                    "terminal; tau-bench exposes cancel and modify for reservations"
                ),
            ),
        ),
    ),
    _l1(
        "l1:predicate.change_arrangement",
        L1ItemType.PREDICATE_SENSE,
        "to alter or cancel an arrangement already committed to",
        role_kind=OntologyRoleKind.OPERATOR,
        aliases=("change", "cancel", "reschedule", "postpone", "modify"),
        roles=(
            _slot("l1:role.agent", required=True),
            _slot("l1:role.theme", required=True),
            _slot("l1:role.cause"),
        ),
        provenance=(
            _pb_source(
                "cancel.01 'cause to be not valid' and postpone.01, whose ARG3 'original time' "
                "and ARG4 'new time' show a change presupposes a prior arrangement. The cause "
                "slot is here because cancel takes a reason in practice"
            ),
            _tau(
                "cancel_pending_order and three update_reservation_* tools all require an "
                "existing record, and cancel_pending_order requires a reason"
            ),
        ),
        grounding=(
            _pb("cancel.01", "cause to be not valid", "ARG1 PPT cancelled"),
            _pb(
                "postpone.01", "delay (roleset name)", "ARG3 DIR original time / ARG4 GOL new time"
            ),
        ),
        constraints=(
            Constraint(
                kind="presupposes_prior_commitment",
                expression=(
                    "an instance is only well-formed if a prior commit_to_arrangement is recoverable; "
                    "tau-bench refuses to modify an order that is not pending"
                ),
            ),
        ),
    ),
    _l1(
        "l1:predicate.transfer_value",
        L1ItemType.PREDICATE_SENSE,
        "to move money or goods between parties, in either direction",
        role_kind=OntologyRoleKind.OPERATOR,
        aliases=("pay", "buy", "sell", "send money", "spend"),
        roles=(
            _slot("l1:role.agent", required=True),
            _slot("l1:role.theme", required=True),
            _slot("l1:role.recipient"),
            _slot("l1:role.quantity"),
            _slot("l1:role.instrument"),
        ),
        provenance=(
            _pb_source(
                "buy.01, sell.01 and pay.01 share one skeleton with the parties swapped: buyer/"
                "seller/price/benefactive appear in all three. Merged into one sense because the "
                "difference between them is which party the speaker occupies, which the agent "
                "slot already records; keeping three would triple the section for no new "
                "argument structure"
            ),
            _sgd_schema("Banks_1/Banks_2 TransferMoney plus Payment_1, and 5 Buy* intents"),
        ),
        grounding=(
            _pb("buy.01", "purchase", "ARG0 buyer / ARG2 DIR seller / ARG3 price"),
            _pb("sell.01", "commerce: seller, giving in exchange for money", "ARG2 GOL buyer"),
            _pb("pay.01", "pay for (roleset name)", "ARG2 GOL person being paid"),
        ),
        constraints=(
            Constraint(
                kind="requires_instrument",
                expression=(
                    "a value transfer names the means, because reversing it depends on the means: "
                    "tau-bench refunds a gift card immediately and a card in 5-7 days"
                ),
            ),
        ),
    ),
    _l1(
        "l1:predicate.seek_information",
        L1ItemType.PREDICATE_SENSE,
        "to try to find out something, whether by asking or by searching",
        role_kind=OntologyRoleKind.OPERATOR,
        aliases=("ask", "look for", "search", "find out", "check"),
        roles=(
            _slot("l1:role.agent", required=True),
            _slot("l1:role.theme", required=True),
            _slot("l1:role.recipient"),
            _slot("l1:role.constraint_on"),
        ),
        provenance=(
            _pb_source("ask.01 'ask a question' with ARG1 'question' and ARG2 GOL hearer"),
            _sgd_schema("12 of 53 intents begin with Find, the largest intent family"),
        ),
        grounding=(_pb("ask.01", "ask a question", "ARG1 PPT question / ARG2 GOL hearer"),),
        constraints=(
            Constraint(
                kind="no_world_change",
                expression=(
                    "an instance of this sense must not be recorded as changing any state; SGD marks "
                    "29 of 53 intents non-transactional and these are those"
                ),
            ),
        ),
    ),
    _l1(
        "l1:predicate.consume_media",
        L1ItemType.PREDICATE_SENSE,
        "to watch, read or listen to a work, as an experience the holder may later refer back to",
        role_kind=OntologyRoleKind.OPERATOR,
        aliases=("watch", "read", "listen to", "see a film"),
        roles=(
            _slot("l1:role.agent", required=True),
            _slot("l1:role.theme", required=True),
            _slot("l1:role.instrument"),
        ),
        relations=(_qualified_by("l1:qualifier.frequency"),),
        provenance=(
            _pb_source(
                "watch.01 'look at, observe', read.01 and listen.01 'attend to a sound' "
                "share the observer/thing-observed skeleton"
            ),
            _msc("572 persona sentences report watching, reading or listening"),
        ),
        grounding=(
            _pb("watch.01", "look at, observe", "ARG0 observer / ARG1 thing looked at"),
            _pb("listen.01", "attend to a sound", "ARG1 PPT sound or speaker"),
        ),
    ),
    _l1(
        "l1:predicate.occupy_role",
        L1ItemType.PREDICATE_SENSE,
        "to hold a standing position such as a job or a course of study",
        role_kind=OntologyRoleKind.OPERATOR,
        aliases=("work as", "study", "be employed as", "serve as"),
        roles=(
            _slot("l1:role.holder", required=True),
            _slot("l1:role.theme", required=True),
        ),
        provenance=(
            _pb_source(
                "work.01 declares ARG1 'job, project' and ARG2 GOL employer separately, and "
                "study.01 mirrors it with ARG1 subject and ARG2 DIR teacher"
            ),
            _msc("4357 'i am a <role>', 1830 work-status, 354 student-status sentences"),
            _so_source(
                "schema:Occupation and schema:Role are both Intangible subclasses, so a "
                "held position is a type of thing rather than an attribute value"
            ),
        ),
        grounding=(
            _pb("work.01", "work, being employed", "ARG1 PPT job, project"),
            _so("schema:Occupation", "a profession, may involve prolonged training"),
            _wn("n#00582388", "occupation, business, job, line of work"),
        ),
    ),
    _l1(
        "l1:predicate.reside_at",
        L1ItemType.PREDICATE_SENSE,
        "to live somewhere for an extended period, as a standing fact rather than a visit",
        role_kind=OntologyRoleKind.OPERATOR,
        aliases=("live in", "reside", "be based in", "have moved to"),
        roles=(
            _slot("l1:role.holder", required=True),
            _slot("l1:role.target_location", required=True),
            _slot("l1:role.duration"),
        ),
        # New in v2. v1 folded residence into state.circumstance, which lost the location slot: it
        # could say the user's circumstances included living somewhere but not where.
        provenance=(
            _pb_source(
                "reside.01 is 'to live for an extended period' with ARG1 tagged LOC, which is a "
                "different roleset from live.01 'not be dead' -- exactly the sense confusion a "
                "corpus-clustered predicate would make"
            ),
            _msc("1640 residence sentences plus 72 'i moved' events"),
        ),
        grounding=(
            _pb("reside.01", "to live for an extended period", "ARG1 LOC location"),
            _wn(
                "v#02650552",
                "reside, shack, domicile: make one's home in a particular place or community",
            ),
        ),
    ),
    _l1(
        "l1:predicate.possess",
        L1ItemType.PREDICATE_SENSE,
        "to own or have something at one's disposal",
        role_kind=OntologyRoleKind.OPERATOR,
        aliases=("own", "have", "keep", "belong to"),
        roles=(
            _slot("l1:role.holder", required=True),
            _slot("l1:role.theme", required=True),
            _slot("l1:role.quantity"),
        ),
        provenance=(
            _pb_source(
                "own.01 'possess, own something' and have.03 'own, possess' are the same "
                "owner/possession skeleton; belong.01 inverts it"
            ),
            _msc("5307 persona sentences state a possession, including 290 dogs and 137 cats"),
        ),
        grounding=(
            _pb("own.01", "possess, own something", "ARG0 owner / ARG1 possession"),
            _pb("have.03", "own, possess"),
        ),
    ),
    _l1(
        "l1:predicate.relocate",
        L1ItemType.PREDICATE_SENSE,
        "to change where one is or lives, as a completed transition between two places",
        role_kind=OntologyRoleKind.OPERATOR,
        aliases=("move", "relocate", "travel to", "go to"),
        roles=(
            _slot("l1:role.agent", required=True),
            _slot("l1:role.source_location"),
            _slot("l1:role.target_location"),
            _slot("l1:role.cause"),
        ),
        provenance=(
            _pb_source(
                "move.01 'change location' ARG2 GOL destination, and travel.01 with ARG2 "
                "DIR start point against ARG4 GOL destination"
            ),
            _msc("72 'i moved' and 328 travel or visit sentences"),
            _sgd_schema(
                "the origin/destination slot families recur across Buses, Flights and RideSharing"
            ),
        ),
        grounding=(
            _pb("move.01", "change location", "ARG2 GOL destination"),
            _pb("travel.01", "travel, voyaging", "ARG2 DIR start / ARG4 GOL destination"),
        ),
    ),
    _l1(
        "l1:predicate.undergo_transition",
        L1ItemType.PREDICATE_SENSE,
        "to come to be in a new state, where the change itself is what is reported",
        role_kind=OntologyRoleKind.OPERATOR,
        aliases=("become", "start", "stop", "quit", "graduate"),
        roles=(
            _slot("l1:role.holder", required=True),
            _slot("l1:role.theme"),
            _slot("l1:role.cause"),
        ),
        relations=(_qualified_by("l1:qualifier.time"),),
        # New in v2. Life changes are the backbone of multi-session memory and v1 had no predicate
        # for them: it could record a state and a later different state but not the transition,
        # which is what a question about change is actually asking after.
        provenance=(
            _pb_source(
                "become.01 'change of state' takes ARG1 'entity changing' and ARG2 PRD 'new "
                "state', and change.01 adds ARG3 'start state'. The start/end pair is what makes "
                "this a transition rather than two unrelated states"
            ),
            _msc(
                "81 graduated, 75 started/began, 56 quit/stopped, 47 married, 59 retired sentences"
            ),
        ),
        grounding=(
            _pb("become.01", "change of state", "ARG2 PRD new state"),
            _pb("change.01", "transform", "ARG2 PRD end state / ARG3 VSP start state"),
        ),
    ),
    _l1(
        "l1:predicate.suspend_on_condition",
        L1ItemType.PREDICATE_SENSE,
        "to make an intention or commitment depend on a condition that has not yet been settled",
        role_kind=OntologyRoleKind.OPERATOR,
        aliases=("if", "as long as", "provided that", "depend on"),
        roles=(
            _slot("l1:role.holder", required=True),
            _slot("l1:role.theme", required=True),
            _slot("l1:role.trigger", required=True),
        ),
        # The conditional-commitment gap. v1 declined it because SGD's *act labels* are all
        # unconditional and it read the labels; the utterances underneath are not.
        provenance=(
            _pb_source(
                "condition.01 is literally 'to make dependent on a condition', with ARG1 'entity "
                "made dependent' and ARG2 GOL 'dependent on'. v1 said the construct would be "
                "authored from imagination; it is a roleset in the reference frame set"
            ),
            _sgd_acts(
                "472 utterances condition on availability, 88 use an if/then frame, 14 use 'as "
                "long as' or 'only if', 43 use 'in case'"
            ),
            _msc("21 sentence-initial conditionals and 38 'when X, i want Y' triggers"),
        ),
        grounding=(
            _pb("condition.01", "to make dependent on a condition", "ARG2 GOL dependent on"),
            _pb("depend.01", "rely (roleset name)", "ARG1 PPT depended on"),
            _wn(
                "n#06755568",
                "condition, precondition, stipulation: an assumption on which rests "
                "the validity or effect of something else",
            ),
        ),
    ),
)


# --- State types -------------------------------------------------------------------------
#
# What holds of a subject without anyone acting. Seven, against v1's four. The additions are the
# ones a person states about themselves most often and that v1 could only express by flattening
# into state.circumstance: an occupation, a residence, a dietary or medical restriction.
_STATES: Final[tuple[L1Item, ...]] = (
    _l1(
        "l1:state.circumstance",
        L1ItemType.STATE_TYPE,
        "a general condition the subject is in, not covered by a more specific state type",
        aliases=("situation", "circumstances", "how things stand"),
        roles=(_slot("l1:role.holder", required=True),),
        relations=(_qualified_by("l1:qualifier.time"),),
        # Kept as the catch-all, but narrowed: v1's version absorbed residence, occupation and
        # restriction because it had nowhere else to put them, which made it the largest and least
        # informative state type. Those three now have their own ids.
        provenance=(
            _msc(
                "14288 ongoing-state sentences in v1's count; the residual after the specific "
                "types below is what this now covers"
            ),
        ),
        grounding=(
            _wn(
                "n#13920429", "condition: a mode of being or form of existence of a person or thing"
            ),
        ),
        constraints=(
            Constraint(
                kind="revisable_without_identity_change",
                expression=(
                    "a new value supersedes the old while remaining the same state; SGD revises city "
                    "571 times and departure_date 516 times in 5110 dialogues"
                ),
            ),
        ),
    ),
    _l1(
        "l1:state.possession",
        L1ItemType.STATE_TYPE,
        "the subject has something at their disposal, whether owned or merely held",
        aliases=("owns", "has", "in their possession"),
        roles=(
            _slot("l1:role.holder", required=True),
            _slot("l1:role.theme", required=True),
            _slot("l1:role.quantity"),
        ),
        provenance=(
            _msc("5307 persona sentences state a possession"),
            _pb_source("own.01 and belong.01 are inverse framings of one owner/possession state"),
        ),
        grounding=(_pb("own.01", "possess, own something", "ARG0 owner / ARG1 possession"),),
        relations=(_is_a("l1:state.circumstance"),),
    ),
    _l1(
        "l1:state.occupation_status",
        L1ItemType.STATE_TYPE,
        "the subject holds, seeks or has left a working or studying position",
        aliases=("employment status", "job status", "what they do"),
        roles=(
            _slot("l1:role.holder", required=True),
            _slot("l1:role.theme"),
        ),
        relations=(_qualified_by("l1:qualifier.time"),),
        provenance=(
            _msc(
                "4357 'i am a <role>', 1830 work-status, 354 student-status and 59 retired "
                "sentences: the largest single family of persona content"
            ),
            _pb_source(
                "quit.01 is 'leave your job' and retire.01 'stop working', so employment "
                "has its own lifecycle distinct from a generic state change"
            ),
        ),
        grounding=(
            _pb("retire.01", "stop working", "ARG1 DIR former job"),
            _so("schema:Occupation", "a profession, may involve prolonged training"),
        ),
    ),
    _l1(
        "l1:state.residence",
        L1ItemType.STATE_TYPE,
        "where the subject lives, as a standing fact with a place the memory can be asked for",
        aliases=("lives in", "home location", "where they live"),
        roles=(
            _slot("l1:role.holder", required=True),
            _slot("l1:role.target_location", required=True),
            _slot("l1:role.duration"),
        ),
        relations=(_qualified_by("l1:qualifier.time"),),
        provenance=(
            _msc(
                "1640 residence sentences, of which 59 give a duration ('i have lived there "
                "since i was 5')"
            ),
            _pb_source(
                "reside.01's ARG1 is tagged LOC, so the place is a required position "
                "rather than an optional detail"
            ),
        ),
        grounding=(
            _pb("reside.01", "to live for an extended period", "ARG1 LOC location"),
            _so("schema:Place", "entities that have a somewhat fixed, physical extension"),
        ),
    ),
    _l1(
        "l1:state.capability_constraint",
        L1ItemType.STATE_TYPE,
        "something the subject cannot do or have, which restricts what may be offered them",
        aliases=("can't", "unable to", "limitation", "restriction"),
        roles=(
            _slot("l1:role.holder", required=True),
            _slot("l1:role.constraint_on", required=True),
            _slot("l1:role.cause"),
        ),
        relations=(_qualified_by("l1:qualifier.polarity"),),
        provenance=(
            _msc(
                "188 'i cannot / am unable' sentences, 113 allergy statements and 80 "
                "vegan/vegetarian statements"
            ),
            _pb_source(
                "PropBank has dedicated rolesets for the two commonest cases: allergic.01 with "
                "ARG2 PAG 'cause of allergy' and vegan.01 'adhering to a strict no meat diet'. "
                "The cause slot is here because allergic.01 declares one"
            ),
        ),
        grounding=(
            _pb("allergic.01", "allergic", "ARG2 PAG cause of allergy"),
            _pb("able.01", "have an ability, skill, being able", "ARG2 PPT ability itself"),
        ),
        constraints=(
            Constraint(
                kind="distinct_from_preference",
                expression=(
                    "a constraint cannot be traded off the way a preference can; conflating them "
                    "makes a hard requirement look like a rankable option"
                ),
            ),
        ),
    ),
    _l1(
        "l1:state.pending_arrangement",
        L1ItemType.STATE_TYPE,
        "an arrangement is committed to and has not yet been carried out",
        aliases=("booked", "scheduled", "upcoming arrangement"),
        roles=(
            _slot("l1:role.holder", required=True),
            _slot("l1:role.theme", required=True),
            _slot("l1:role.beneficiary"),
        ),
        relations=(_qualified_by("l1:qualifier.assertion_standing"),),
        provenance=(
            _tau(
                "retail order status pending/processed/delivered: the pending case is a state "
                "between the commitment and its fulfilment"
            ),
            _sgd_acts("SYSTEM NOTIFY_SUCCESS 16868 marks the transition out of this state"),
        ),
        grounding=(
            _so("schema:Reservation", "describes a reservation for travel, dining or an event"),
        ),
        constraints=(
            Constraint(
                kind="terminates_on_fulfilment_or_withdrawal",
                expression=(
                    "this state ends by fulfilment or by l1:event.commitment_withdrawn, and not by "
                    "the passage of time alone"
                ),
            ),
        ),
    ),
    _l1(
        "l1:state.suspended_commitment",
        L1ItemType.STATE_TYPE,
        "a commitment that will take effect only if its trigger condition is met",
        aliases=("conditional booking", "if-then commitment", "standing instruction"),
        roles=(
            _slot("l1:role.holder", required=True),
            _slot("l1:role.theme", required=True),
            _slot("l1:role.trigger", required=True),
        ),
        relations=(
            Relation(kind=RelationKind.TRIGGERED_BY, target_id="l1:role.trigger"),
            _qualified_by("l1:qualifier.modality"),
        ),
        # The other half of the conditional-commitment gap: predicate.suspend_on_condition is the
        # act, this is the state it leaves behind, and the state is what a later session queries.
        provenance=(
            _pb_source(
                "condition.01 ARG1 'entity made dependent' is the thing left in this "
                "state once the conditioning act is over"
            ),
            _sgd_acts(
                "472 availability-conditioned requests and 14 'as long as' constraints "
                "describe a commitment awaiting a fact the speaker does not yet have"
            ),
        ),
        grounding=(
            _pb(
                "condition.01", "to make dependent on a condition", "ARG1 PPT entity made dependent"
            ),
            _so("schema:PotentialActionStatus", "a description of an action that is supported"),
        ),
    ),
)


# --- Event types -------------------------------------------------------------------------
#
# Things that happened, as opposed to things that hold. Eight, against v1's five. The additions
# are life transitions, achievement and first meetings -- the events a long conversation refers
# back to, which v1 had no types for.
_EVENTS: Final[tuple[L1Item, ...]] = (
    _l1(
        "l1:event.commitment_made",
        L1ItemType.EVENT_TYPE,
        "the moment a party bound itself to a future arrangement",
        aliases=("booked it", "agreed to it", "made the reservation"),
        roles=(
            _slot("l1:role.agent", required=True),
            _slot("l1:role.theme", required=True),
            _slot("l1:role.beneficiary"),
        ),
        relations=(
            _qualified_by("l1:qualifier.time"),
            Relation(
                kind=RelationKind.SPECIALIZES_SENSE, target_id="l1:predicate.commit_to_arrangement"
            ),
        ),
        provenance=(
            _sgd_acts("SYSTEM NOTIFY_SUCCESS 16868 records a commitment coming into being"),
            _pb_source("agree.01 ARG1 'proposition' and commit.01 ARG2 GOL 'committed to'"),
        ),
        grounding=(_pb("agree.01", "agree (roleset name)", "ARG1 PPT proposition"),),
        constraints=(
            Constraint(
                kind="opens_a_state",
                expression=(
                    "this event begins a state that outlives it, so an instance without a resulting "
                    "l1:state.pending_arrangement is incompletely represented"
                ),
            ),
        ),
    ),
    _l1(
        "l1:event.commitment_withdrawn",
        L1ItemType.EVENT_TYPE,
        "the moment a party undid a commitment it had made",
        aliases=("cancelled it", "backed out"),
        roles=(
            _slot("l1:role.agent", required=True),
            _slot("l1:role.theme", required=True),
            _slot("l1:role.cause"),
        ),
        relations=(
            _opposite("l1:event.commitment_made"),
            Relation(
                kind=RelationKind.SPECIALIZES_SENSE, target_id="l1:predicate.change_arrangement"
            ),
        ),
        provenance=(
            _sgd_acts("USER NEGATE_INTENT 5425"),
            _tau("cancel_pending_order and cancel_reservation, the former requiring a reason"),
            _pb_source(
                "withdraw.01 and refuse.01 are separate rolesets from cancel.01, all "
                "sharing an undoing of something previously settled"
            ),
        ),
        grounding=(_pb("withdraw.01", "withdraw, remove oneself, removal from a source"),),
    ),
    _l1(
        "l1:event.attempt_failed",
        L1ItemType.EVENT_TYPE,
        "an attempt was made and did not achieve what it aimed at",
        aliases=("didn't work", "it failed", "couldn't do it"),
        roles=(
            _slot("l1:role.agent", required=True),
            _slot("l1:role.theme"),
            _slot("l1:role.cause"),
        ),
        provenance=(
            _sgd_acts("SYSTEM NOTIFY_FAILURE 2398"),
            _pb_source(
                "fail.01 'not succeed' declares ARG2 'task' and ARG0 tagged CAU, which is "
                "why the cause slot belongs on the failure rather than on the attempt"
            ),
        ),
        grounding=(
            _pb("fail.01", "not succeed", "ARG2 PPT task"),
            _so("schema:FailedActionStatus", "an action that failed to complete"),
        ),
        constraints=(
            Constraint(
                kind="no_resulting_state",
                expression=(
                    "a failed attempt must not be recorded as opening a state; treating "
                    "NOTIFY_FAILURE like NOTIFY_SUCCESS would assert 302 arrangements that do not "
                    "exist"
                ),
            ),
        ),
    ),
    _l1(
        "l1:event.objective_achieved",
        L1ItemType.EVENT_TYPE,
        "something the subject was working toward was completed",
        aliases=("finished it", "achieved it", "got it done", "graduated"),
        roles=(
            _slot("l1:role.agent", required=True),
            _slot("l1:role.theme", required=True),
        ),
        relations=(_opposite("l1:event.attempt_failed"),),
        # New in v2. v1 had failure but not success, so a project could be recorded as lapsing and
        # never as completing -- an asymmetry that made l2:lifecycle.achieved unreachable from L1.
        provenance=(
            _pb_source(
                "achieve.01 'accomplish', complete.01 'bring to an end' with ARG1 'task, action "
                "coming to an end', and finish.01 are three rolesets for the positive outcome "
                "PropBank keeps distinct from fail.01"
            ),
            _msc("81 'i graduated' sentences plus 4 explicit finished/achieved"),
        ),
        grounding=(
            _pb("achieve.01", "accomplish", "ARG1 PPT thing achieved"),
            _so("schema:AchieveAction", "the act of accomplishing something via previous efforts"),
        ),
    ),
    _l1(
        "l1:event.life_transition",
        L1ItemType.EVENT_TYPE,
        "a change in the subject's standing situation, such as moving, marrying or changing work",
        aliases=("moved house", "changed jobs", "got married", "big change"),
        roles=(
            _slot("l1:role.holder", required=True),
            _slot("l1:role.source_location"),
            _slot("l1:role.target_location"),
            _slot("l1:role.cause"),
        ),
        relations=(_qualified_by("l1:qualifier.time"),),
        # The event backbone of cross-session memory: the reason a state recorded in session 1 is
        # no longer true in session 12. v1 could represent both states and not the transition.
        provenance=(
            _msc(
                "72 moved, 47 married, 81 graduated, 56 quit/stopped, 59 retired: 315 "
                "transition sentences in total"
            ),
            _pb_source(
                "become.01 ARG2 PRD 'new state' against change.01 ARG3 VSP 'start state' "
                "is the before/after pair a transition needs"
            ),
        ),
        grounding=(
            _pb("become.01", "change of state", "ARG2 PRD new state"),
            _pb("marry.01", "to take as a spouse, to join spouses"),
        ),
    ),
    _l1(
        "l1:event.first_encounter",
        L1ItemType.EVENT_TYPE,
        "the occasion on which the subject first came to know another party",
        aliases=("we met", "first met", "got to know"),
        roles=(
            _slot("l1:role.holder", required=True),
            _slot("l1:role.theme", required=True),
            _slot("l1:role.target_location"),
        ),
        relations=(_qualified_by("l1:qualifier.time"),),
        # Present because it is what dates a relationship. Without it, a relationship at L2 has no
        # L1 event to hang its start on, and "how long have you known her" is unanswerable.
        provenance=(
            _pb_source(
                "meet.02 is glossed 'kennenlernen -- come upon, become acquainted with "
                "initially', a separate roleset from meet.01 'arrive at, achieve', and its ARG1 "
                "is tagged COM (comitative). befriend.01 marks the same transition"
            ),
            _msc(
                "46 'i met' sentences, plus 136 'my best friend' and 163 'my friend' references "
                "that presuppose one"
            ),
        ),
        grounding=(
            _pb("meet.02", "come upon, become acquainted with initially", "ARG1 COM person met"),
            _pb("befriend.01", "become friends with", "ARG1 PPT new friend"),
        ),
    ),
    _l1(
        "l1:event.media_consumption",
        L1ItemType.EVENT_TYPE,
        "the subject watched, read or listened to a particular work on some occasion",
        aliases=("watched it", "read it", "listened to it"),
        roles=(
            _slot("l1:role.agent", required=True),
            _slot("l1:role.theme", required=True),
            _slot("l1:role.instrument"),
        ),
        relations=(
            _qualified_by("l1:qualifier.frequency"),
            Relation(kind=RelationKind.SPECIALIZES_SENSE, target_id="l1:predicate.consume_media"),
        ),
        provenance=(
            _tm2("movie_search 45318 and music annotations, generalised away from the vertical"),
            _msc("572 media-consumption sentences"),
        ),
        grounding=(_pb("watch.01", "look at, observe", "ARG1 PPT thing looked at"),),
    ),
    _l1(
        "l1:event.information_request",
        L1ItemType.EVENT_TYPE,
        "one party asked another for information on some occasion",
        aliases=("asked about it", "enquired"),
        roles=(
            _slot("l1:role.agent", required=True),
            _slot("l1:role.theme", required=True),
            _slot("l1:role.recipient"),
        ),
        provenance=(
            _sgd_acts("USER REQUEST 33612 and SYSTEM REQUEST 46082"),
            _pb_source(
                "ask.01 ARG2 GOL 'hearer' is what makes this an event between two parties "
                "rather than the wonder.01 mental state behind modality.question"
            ),
        ),
        grounding=(_pb("ask.01", "ask a question", "ARG2 GOL hearer"),),
        relations=(
            Relation(
                kind=RelationKind.SPECIALIZES_SENSE, target_id="l1:predicate.seek_information"
            ),
        ),
    ),
)


# --- Preference types --------------------------------------------------------------------
#
# Four, and the change from v1 is not the count but the slots. Every one now carries a beneficiary
# and a strength qualifier, which is what closes two of v1's uncovered expressions.
_PREFERENCES: Final[tuple[L1Item, ...]] = (
    _l1(
        "l1:preference.affinity",
        L1ItemType.PREFERENCE_TYPE,
        "a standing liking or disliking of a thing or kind of thing",
        aliases=("likes", "is into", "dislikes", "taste for"),
        roles=(
            _slot("l1:role.holder", required=True),
            _slot("l1:role.theme", required=True),
            _slot("l1:role.beneficiary"),
        ),
        relations=(
            _qualified_by("l1:qualifier.strength"),
            _qualified_by("l1:qualifier.polarity"),
            Relation(kind=RelationKind.SPECIALIZES_SENSE, target_id="l1:predicate.hold_attitude"),
        ),
        provenance=(
            _msc(
                "13819 affect-positive against 970 affect-negative persona sentences in v1's "
                "count; this build measures 9517 like/enjoy, 4102 love, 2963 favourite"
            ),
            _pb_source(
                "like.01's two-argument structure, with strength carried separately "
                "because love.01 and adore.01 differ from it only in intensity"
            ),
        ),
        grounding=(
            _wn(
                "n#06200344",
                "predilection, preference, orientation: a predisposition in favor of something",
            ),
            _pb("like.01", "have affection towards, be fond of", "ARG1 PPT object of affection"),
        ),
    ),
    _l1(
        "l1:preference.comparative",
        L1ItemType.PREFERENCE_TYPE,
        "a preference for one option over a named alternative rather than in isolation",
        aliases=("prefers X to Y", "would rather", "over"),
        roles=(
            _slot("l1:role.holder", required=True),
            _slot("l1:role.theme", required=True),
            _slot("l1:role.comparison_target", required=True),
            _slot("l1:role.beneficiary"),
        ),
        provenance=(
            _msc("162 'prefer' and 80 'more than' sentences"),
            _sgd_acts("USER SELECT 25869 and REQUEST_ALTS 11208"),
            _pb_source(
                "prefer.01 ARG2 'entity compared to' makes the alternative a required "
                "position, which v1's version lacked"
            ),
        ),
        grounding=(_pb("prefer.01", "to choose as more desirable", "ARG2 PPT entity compared to"),),
        constraints=(
            Constraint(
                kind="irreducible_to_affinities",
                expression=(
                    "two affinity items with the same polarity do not entail a ranking, so a "
                    "comparative may not be synthesised from them"
                ),
            ),
        ),
        relations=(
            Relation(kind=RelationKind.SPECIALIZES_SENSE, target_id="l1:predicate.hold_attitude"),
        ),
    ),
    _l1(
        "l1:preference.threshold",
        L1ItemType.PREFERENCE_TYPE,
        "a preference stated as an acceptable range or limit on an ordered attribute",
        aliases=("no more than", "at least", "under budget", "within"),
        roles=(
            _slot("l1:role.holder", required=True),
            _slot("l1:role.constraint_on", required=True, range_id="l1:attribute.magnitude"),
            _slot("l1:role.beneficiary"),
        ),
        provenance=(
            _sgd_schema(
                "price_range in Restaurants_1 and seating_class in Flights_1/2 are "
                "ordered categoricals a user narrows"
            ),
            _pb_source(
                "limit.01 and restrict.01 both declare ARG2 GOL 'limit' as the bound "
                "itself, distinct from ARG1 the thing limited"
            ),
        ),
        grounding=(
            _pb("limit.01", "ensure something stays below a certain level, cap", "ARG2 GOL limit"),
        ),
    ),
    _l1(
        "l1:preference.avoidance",
        L1ItemType.PREFERENCE_TYPE,
        "a standing wish not to be offered or subjected to something, stronger than mere dislike",
        aliases=("won't", "avoid", "not for me", "never again"),
        roles=(
            _slot("l1:role.holder", required=True),
            _slot("l1:role.theme", required=True),
            _slot("l1:role.cause"),
            _slot("l1:role.beneficiary"),
        ),
        relations=(_opposite("l1:preference.affinity"),),
        # New in v2. Distinguished from a negative affinity because avoidance is actionable in a
        # way dislike is not: "I don't like flying" and "don't book me a flight" differ in what a
        # system may do next, and one negated affinity cannot express both.
        provenance=(
            _pb_source(
                "avoid.01 'stay away from' is its own roleset, and forbid.01 'disallow, "
                "prohibit' declares ARG1 'forbidden action' -- a prohibition rather than a "
                "sentiment"
            ),
            _msc(
                "113 allergy and 80 dietary statements are avoidances with a cause rather than "
                "dislikes; 269 hate/can't-stand sentences sit between the two"
            ),
        ),
        grounding=(
            _pb("avoid.01", "stay away from", "ARG1 PPT thing avoided"),
            _pb("forbid.01", "disallow, prohibit", "ARG1 PPT forbidden action"),
        ),
    ),
)


# --- Task types --------------------------------------------------------------------------
#
# What is outstanding for the subject. Four, one more than v1: a conditional intention is
# genuinely different from a declared one, because it cannot be acted on until its trigger fires.
_TASKS: Final[tuple[L1Item, ...]] = (
    _l1(
        "l1:task.declared_intention",
        L1ItemType.TASK_TYPE,
        "something the subject has said they intend to do, not yet done",
        aliases=("plans to", "is going to", "intends to", "will"),
        roles=(
            _slot("l1:role.holder", required=True),
            _slot("l1:role.theme", required=True),
            _slot("l1:role.beneficiary"),
        ),
        relations=(_qualified_by("l1:qualifier.modality"),),
        provenance=(
            _msc("775 'i want to', 86 'i plan/hope to', 275 'i will / going to' sentences"),
            _pb_source("intend.01 'intend, plan, on purpose' with ARG1 'intent, thing planned'"),
        ),
        grounding=(
            _pb("intend.01", "intend, plan, on purpose, intent", "ARG1 PPT thing planned"),
            _so(
                "schema:PlanAction",
                "the act of planning the execution of an event/task to a future date",
            ),
        ),
        constraints=(
            Constraint(
                kind="single_turn_scope",
                expression=(
                    "an L1 task is what one turn makes explicit; anything requiring evidence from a "
                    "second turn is an O_L2 abstraction and not this item"
                ),
            ),
        ),
    ),
    _l1(
        "l1:task.conditional_intention",
        L1ItemType.TASK_TYPE,
        "an intention the subject will act on only if a stated condition turns out to hold",
        aliases=("if that happens", "depending on", "only if"),
        roles=(
            _slot("l1:role.holder", required=True),
            _slot("l1:role.theme", required=True),
            _slot("l1:role.trigger", required=True),
        ),
        relations=(
            Relation(kind=RelationKind.TRIGGERED_BY, target_id="l1:role.trigger"),
            Relation(
                kind=RelationKind.SPECIALIZES_SENSE, target_id="l1:predicate.suspend_on_condition"
            ),
        ),
        provenance=(
            _sgd_acts(
                "472 availability-conditioned requests, 88 if/then frames, 14 'as long "
                "as'/'only if', 43 'in case'"
            ),
            _msc("21 sentence-initial conditionals and 38 'when X i want Y' triggers"),
            _pb_source("condition.01 ARG2 GOL 'dependent on' is the trigger this task waits on"),
        ),
        grounding=(
            _pb("condition.01", "to make dependent on a condition", "ARG2 GOL dependent on"),
        ),
    ),
    _l1(
        "l1:task.outstanding_requirement",
        L1ItemType.TASK_TYPE,
        "something that must be done or supplied before an arrangement can proceed",
        aliases=("still needs", "required", "blocked on"),
        roles=(
            _slot("l1:role.holder", required=True),
            _slot("l1:role.theme", required=True),
            _slot("l1:role.recipient"),
        ),
        provenance=(
            _sgd_schema(
                "every transactional intent declares required_slots that must be filled "
                "before it can be executed"
            ),
            _pb_source("require.01 'need, obligation' ARG1 'thing required' plus need.01"),
        ),
        grounding=(_pb("require.01", "need, obligation", "ARG1 PPT thing required"),),
        constraints=(
            Constraint(
                kind="closes_when_supplied",
                expression=(
                    "this item ends when the missing value is supplied, so it is not a preference and "
                    "must not survive its own satisfaction"
                ),
            ),
        ),
    ),
    _l1(
        "l1:task.abandoned_intention",
        L1ItemType.TASK_TYPE,
        "an intention the subject has given up rather than completed",
        aliases=("gave up on", "not doing it any more", "dropped it"),
        roles=(
            _slot("l1:role.holder", required=True),
            _slot("l1:role.theme", required=True),
            _slot("l1:role.cause"),
        ),
        relations=(_opposite("l1:task.declared_intention"),),
        provenance=(
            _sgd_acts("USER NEGATE_INTENT 5425 abandons rather than revises"),
            _msc("56 'i quit / stopped / gave up' sentences"),
            _pb_source(
                "abandon.01 'leave behind' and quit.01 'leave your job' both mark giving "
                "up rather than finishing, which achieve.01 covers"
            ),
        ),
        grounding=(_pb("abandon.01", "leave behind", "ARG1 DIR entity left behind"),),
    ),
)


def build_o_l1() -> L1Freeze:
    """Assemble O_L1 v2, sorted by id because the freeze hash depends on the order."""
    items = (
        *_ROLES,
        *_DIMENSIONS,
        *_TIME_VALUES,
        *_MODALITY_VALUES,
        *_POLARITY_VALUES,
        *_SOURCE_STATUS_VALUES,
        *_STANDING_VALUES,
        *_STRENGTH_VALUES,
        *_FREQUENCY_VALUES,
        *_ATTRIBUTES,
        *_PREDICATES,
        *_STATES,
        *_EVENTS,
        *_PREFERENCES,
        *_TASKS,
    )
    return L1Freeze(
        version=O_L1_VERSION,
        items=tuple(sorted(items, key=lambda entry: entry.item.id)),
    )
