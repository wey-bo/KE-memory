"""O_L2 v2: the cross-turn and cross-session abstraction layer.

An L2 item is not a longer-lived L1 item. It is a structure no single observation can witness,
and the bar for admitting one is a *measured multi-observation phenomenon* rather than a
plausible-sounding structure. v1's measurements still stand and are reused where they were
sound: 10739 of 16142 SGD dialogues touch more than one service, 86.4% of those carry a slot
value shared across services, 71.6% of a 5110-dialogue sample revise a value mid-dialogue.

What v2 adds is the relationship layer, which v1 recorded as "the largest known gap in O_L2" and
declined because "any inventory would be guessed rather than measured". Two things changed:

- The measurement exists. 4647 relationship mentions in the 65245 MSC persona sentences, and they
  do not scatter -- they fall into four families with three-digit or four-digit counts each
  (descent kin 3088, partnership 738, friendship 485, lateral kin 311). A professional family
  exists at 25 and is *not* admitted as a type, because 25 is where guessing starts.
- schema.org settles the shape rather than the list. ``knows`` is the generic bi-directional
  relation and ``follows`` the generic uni-directional one, so symmetry is a modelled property of
  a relationship type instead of an assumption. ``Role`` is reified with ``startDate``/``endDate``,
  which is why a relationship here can lapse without being contradicted.

The layer shares no vocabulary with O_L1. ``l2:abstraction.preference_profile`` is not
``l1:preference.affinity`` with a longer life; it is a ranked set over many affinity observations
and can hold when no single one is decisive. Every derivation lives in M_L1_to_L2.

What is still not here: no topic. v1 deferred ``l2.topic`` because nothing in the corpora says
when two observations share a topic, so no derivation rule could be written -- and none of the
three published sources supplies one either. schema.org's ``about`` has range Thing, which says a
work has a subject, not when two remarks are on the same subject. It stays deferred.
"""

from __future__ import annotations

from typing import Final

from .models import (
    Constraint,
    ExternalGrounding,
    L2Freeze,
    L2Item,
    L2ItemType,
    OntologyItem,
    OntologyRoleKind,
    Provenance,
    Relation,
    RelationKind,
    RoleSlot,
    SourceKind,
)

O_L2_VERSION: Final[str] = "2.0.0"


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
    grounding: tuple[ExternalGrounding, ...] = (),
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
            grounding=grounding,
        ),
        item_type=item_type,
        minimum_support=minimum_support,
        spans_sessions=spans_sessions,
    )


def _sgd_dyn(evidence: str) -> Provenance:
    return Provenance(source=SourceKind.SGD_STATE_DYNAMICS, evidence=evidence)


def _sgd_schema(evidence: str) -> Provenance:
    return Provenance(source=SourceKind.SGD_SCHEMA, evidence=evidence)


def _sgd_acts(evidence: str) -> Provenance:
    return Provenance(source=SourceKind.SGD_DIALOGUE_ACTS, evidence=evidence)


def _msc(evidence: str) -> Provenance:
    return Provenance(source=SourceKind.MSC_PERSONAS, evidence=evidence)


def _tau(evidence: str) -> Provenance:
    return Provenance(source=SourceKind.TAU_BENCH_POLICY, evidence=evidence)


def _repo(evidence: str) -> Provenance:
    return Provenance(source=SourceKind.REPOSITORY_VOCABULARY, evidence=evidence)


def _discovery(evidence: str) -> Provenance:
    return Provenance(source=SourceKind.DISCOVERY_GAP_SHAPE, evidence=evidence)


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


def _holds_between(target: str) -> Relation:
    return Relation(kind=RelationKind.HOLDS_BETWEEN, target_id=target)








def _is_a(target: str) -> Relation:
    return Relation(kind=RelationKind.IS_A, target_id=target)


def _slot(role_id: str, *, required: bool = False, range_id: str | None = None) -> RoleSlot:
    return RoleSlot(role_id=role_id, is_required=required, range_id=range_id)


# --- L2 role positions -------------------------------------------------------------------
#
# The layer needs its own positions because it may not name L1's. Five, against v1's three: the
# two additions are the party positions a relationship holds between, which is the structural
# reason relation types could not exist in v1 at all.
_L2_ROLES: Final[tuple[L2Item, ...]] = (
    _l2(
        "l2:role.subject",
        L2ItemType.EVIDENCE_CONSTRAINT,
        "the party an abstraction is about, which every abstraction has exactly one of",
        role_kind=OntologyRoleKind.ROLE,
        aliases=("about whom",),
        provenance=(
            _tau(
                "both tau-bench environments authenticate one user per session and the policy "
                "forbids acting across users, so an abstraction spanning two subjects has no "
                "referent"
            ),
        ),
    ),
    _l2(
        "l2:role.scope",
        L2ItemType.EVIDENCE_CONSTRAINT,
        "what an abstraction ranges over, such as a goal, an attribute or a period",
        role_kind=OntologyRoleKind.ROLE,
        aliases=("ranges over", "extent of"),
        provenance=(
            _sgd_dyn(
                "10739 of 16142 dialogues touch more than one service (2: 8266, 3: 2185, "
                "4: 288), so what an abstraction covers must be stated rather than assumed"
            ),
        ),
    ),
    _l2(
        "l2:role.tracked_attribute",
        L2ItemType.EVIDENCE_CONSTRAINT,
        "the attribute whose successive values an abstraction follows over time",
        role_kind=OntologyRoleKind.ROLE,
        aliases=("attribute followed",),
        provenance=(
            _sgd_dyn(
                "revisions concentrate on particular slots -- city 571, departure_date 516, "
                "date 456 -- so a history is per attribute rather than per subject"
            ),
        ),
    ),
    _l2(
        "l2:role.first_party",
        L2ItemType.EVIDENCE_CONSTRAINT,
        "the party from whose side a relationship is stated, ordinarily the remembered subject",
        role_kind=OntologyRoleKind.ROLE,
        aliases=("from whose side", "relating party"),
        provenance=(
            _msc(
                "all 4647 relationship mentions are stated from the speaker's side ('my "
                "mother'), so one position is privileged by how the data is expressed"
            ),
            _so_source(
                "schema:knows has domain Person and range Person, i.e. both ends are the same "
                "kind of thing and only their positions distinguish them"
            ),
        ),
        grounding=(_so("schema:knows", "the most generic bi-directional social/work relation"),),
    ),
    _l2(
        "l2:role.second_party",
        L2ItemType.EVIDENCE_CONSTRAINT,
        "the other party to a relationship, held as a type of counterpart and never as a person",
        role_kind=OntologyRoleKind.ROLE,
        aliases=("counterpart", "the other party"),
        constraints=(
            Constraint(
                kind="exclusion",
                expression=(
                    "records that a counterpart position exists and is filled, never which "
                    "person fills it; a named individual is excluded from both layers, so this "
                    "position is what makes relationships representable without naming anybody"
                ),
            ),
        ),
        provenance=(
            _so_source(
                "schema:follows is the uni-directional counterpart to knows, which is what shows "
                "the two positions are not interchangeable in every relationship type"
            ),
        ),
        grounding=(_so("schema:follows", "the most generic uni-directional social relation"),),
    ),
)


# --- Relation types ----------------------------------------------------------------------
#
# The gap v1 named as its largest. Four types, one per family that the persona corpus attests at
# three digits or more. Deliberately not more: a professional family exists at 25 mentions and is
# excluded, and no type here names a specific relation like "aunt" -- the descent type covers
# parent, child, grandparent and nephew alike, because what memory needs is the direction and the
# permanence, not the kinship calculus.
#
# ``symmetric`` is expressed by which party positions the type declares as interchangeable, and
# recorded in the constraint rather than as a bare flag, because the consequence is what matters:
# a symmetric relationship stated from one side may be reported from the other, an asymmetric one
# may not.
_RELATION_TYPES: Final[tuple[L2Item, ...]] = (
    _l2(
        "l2:relation.kin_descent",
        L2ItemType.RELATION_TYPE,
        "a family relationship along a line of descent, which holds for life once it holds",
        aliases=("parent or child", "family by descent", "blood relative"),
        relations=(
            _holds_between("l2:role.first_party"),
            _holds_between("l2:role.second_party"),
        ),
        roles=(_slot("l2:role.subject", required=True),),
        spans_sessions=True,
        constraints=(
            Constraint(
                kind="asymmetry",
                expression=(
                    "not interchangeable: the parent of X is not the child of X, so a mention "
                    "from one side does not license the mirrored claim"
                ),
            ),
            Constraint(
                kind="permanence",
                expression=(
                    "may not lapse; unlike partnership and friendship a descent relation ends "
                    "only if it was mis-recorded, so a later contradiction is a correction "
                    "rather than a change"
                ),
            ),
        ),
        provenance=(
            _msc(
                "3088 mentions, the largest relationship family by a factor of four: mother 493, "
                "father 513, mom 480, dad 442, parents 698, plus children, grandparents, "
                "nephews, aunts and cousins"
            ),
            _so_source(
                "schema.org declares parent and children as separate properties both with domain "
                "and range Person, which is the asymmetry this type carries"
            ),
        ),
        grounding=(
            _so("schema:parent", "a parent of this person"),
            _wn("n#10235549", "relative, relation: a person related by blood or marriage"),
        ),
    ),
    _l2(
        "l2:relation.kin_lateral",
        L2ItemType.RELATION_TYPE,
        "a family relationship within one generation, which holds for life and reads alike "
        "from either side",
        aliases=("sibling", "brother or sister"),
        relations=(
            _holds_between("l2:role.first_party"),
            _holds_between("l2:role.second_party"),
            _is_a("l2:relation.kin_descent"),
        ),
        roles=(_slot("l2:role.subject", required=True),),
        spans_sessions=True,
        constraints=(
            Constraint(
                kind="symmetry",
                expression=(
                    "interchangeable: if X is a sibling of Y then Y is a sibling of X, so either "
                    "party's mention supports the same relationship"
                ),
            ),
        ),
        provenance=(
            _msc("311 mentions: sister 124, brother 135, plus siblings and twins"),
            _so_source(
                "schema:sibling has domain and range Person and no inverse property, unlike "
                "parent/children -- schema.org's own encoding of the symmetry"
            ),
        ),
        grounding=(
            _so("schema:sibling", "a sibling of the person"),
            _wn("n#10595164", "sibling, sib: a person's brother or sister"),
        ),
    ),
    _l2(
        "l2:relation.partnership",
        L2ItemType.RELATION_TYPE,
        "a romantic or marital relationship, symmetric while it holds and able to end",
        aliases=("spouse", "partner", "married to"),
        relations=(
            _holds_between("l2:role.first_party"),
            _holds_between("l2:role.second_party"),
        ),
        roles=(_slot("l2:role.subject", required=True),),
        spans_sessions=True,
        constraints=(
            Constraint(
                kind="symmetry",
                expression="interchangeable while it holds, in the same way as kin_lateral",
            ),
            Constraint(
                kind="termination",
                expression=(
                    "may end, and an ending is a life transition rather than a contradiction of "
                    "the earlier statement; this is why the type carries a lifecycle and "
                    "kin_descent does not"
                ),
            ),
        ),
        provenance=(
            _msc(
                "738 mentions: husband 255, wife 251, girlfriend 89, boyfriend 63, fiance 14, "
                "partner 14, plus 41 'my ex' which are the terminations"
            ),
            _msc("591 persona sentences state a marital status directly, and 47 the event"),
            _pb_source(
                "marry.01 'to take as a spouse' declares ARG1 'one half' and ARG2 'second "
                "half', which is the symmetric pair"
            ),
        ),
        grounding=(
            _so("schema:spouse", "the person's spouse"),
            _pb("marry.01", "to take as a spouse, to join spouses", "ARG1/ARG2 the two halves"),
            _wn(
                "n#10640620",
                "spouse, partner, married person, mate: a person's partner in marriage",
            ),
        ),
    ),
    _l2(
        "l2:relation.friendship",
        L2ItemType.RELATION_TYPE,
        "a voluntary personal relationship that is not kin and not romantic",
        aliases=("friend", "close friend", "knows socially"),
        relations=(
            _holds_between("l2:role.first_party"),
            _holds_between("l2:role.second_party"),
        ),
        roles=(_slot("l2:role.subject", required=True),),
        spans_sessions=True,
        constraints=(
            Constraint(
                kind="symmetry",
                expression="interchangeable, as schema:knows is declared bi-directional",
            ),
            Constraint(
                kind="gradation",
                expression=(
                    "admits degree, which is carried by the strength qualifier through the map "
                    "rather than by separate types for friend and best friend"
                ),
            ),
        ),
        provenance=(
            _msc("485 mentions: friend 163, best friend 136, plus neighbours and roommates"),
            _pb_source(
                "befriend.01 'become friends with' marks the transition into this "
                "relationship, which the first-encounter event type dates"
            ),
            _so_source("schema:knows is 'the most generic bi-directional social/work relation'"),
        ),
        grounding=(
            _so("schema:knows", "the most generic bi-directional social/work relation"),
            _pb("befriend.01", "become friends with", "ARG1 PPT new friend"),
            _wn("n#10112591", "friend: a person you know well and regard with affection and trust"),
        ),
    ),
)


# --- Abstraction types -------------------------------------------------------------------
#
# Nine, against v1's seven. Every one carries a minimum support, because an abstraction resting on
# one observation is that observation under a longer name.
_ABSTRACTIONS: Final[tuple[L2Item, ...]] = (
    _l2(
        "l2:abstraction.project",
        L2ItemType.ABSTRACTION_TYPE,
        "one intention pursued through several sub-goals that are individually completable",
        aliases=("multi-step goal", "undertaking", "the whole plan"),
        roles=(
            _slot("l2:role.subject", required=True),
            _slot("l2:role.scope", required=True),
        ),
        minimum_support=2,
        spans_sessions=True,
        provenance=(
            _sgd_dyn(
                "10739 of 16142 dialogues touch more than one service, so a multi-part intention "
                "is the majority case rather than a special one"
            ),
        ),
    ),
    _l2(
        "l2:abstraction.task",
        L2ItemType.ABSTRACTION_TYPE,
        "one outstanding piece of work with a lifecycle of its own",
        aliases=("todo", "open item", "action item"),
        roles=(_slot("l2:role.subject", required=True),),
        spans_sessions=True,
        provenance=(
            _repo(
                "domain.AggregateNodeKind declares Task and Project separately, so a single "
                "item and a multi-part undertaking are distinct structures"
            ),
        ),
    ),
    _l2(
        "l2:abstraction.preference_profile",
        L2ItemType.ABSTRACTION_TYPE,
        "a subject's settled ranking over options in some area, held across many statements",
        aliases=("taste profile", "what they go for", "their preferences"),
        roles=(
            _slot("l2:role.subject", required=True),
            _slot("l2:role.scope", required=True),
        ),
        minimum_support=2,
        spans_sessions=True,
        constraints=(
            Constraint(
                kind="ordering",
                expression=(
                    "a profile is only a profile if it orders options; two unrelated likings are "
                    "two observations, and the strength qualifier is what supplies the order"
                ),
            ),
        ),
        provenance=(
            _msc(
                "16482 affect statements over 65245 sentences, and the strength bands that order "
                "them: 2963 favourite, 4102 love, 9517 like, 717 dislike, 269 hate"
            ),
            _sgd_acts(
                "USER SELECT 25869 and REQUEST_ALTS 11208 are choices that reveal a "
                "ranking without stating one"
            ),
        ),
        grounding=(
            _wn(
                "n#06200344",
                "predilection, preference, orientation: a predisposition in favor of something",
            ),
        ),
    ),
    _l2(
        "l2:abstraction.habit",
        L2ItemType.ABSTRACTION_TYPE,
        "a behaviour a subject repeats often enough that it predicts what they will do",
        aliases=("routine", "usually does", "regular practice"),
        roles=(
            _slot("l2:role.subject", required=True),
            _slot("l2:role.scope", required=True),
        ),
        minimum_support=3,
        spans_sessions=True,
        constraints=(
            Constraint(
                kind="support",
                expression=(
                    "three observations minimum, raised from v1's two: two occurrences of a "
                    "behaviour are a coincidence, and the frequency qualifier must also be "
                    "habitual or stronger for the abstraction to hold"
                ),
            ),
        ),
        provenance=(
            _msc(
                "295 explicit-frequency sentences and 926 frequency-adverb sentences. v1 rested "
                "this item on 80 of 65245 and called it the weakest evidence in either layer; "
                "this build measures the pattern an order of magnitude more widely, which is why "
                "the support threshold could be raised rather than lowered"
            ),
            _so_source(
                "schema:Schedule separates repeatFrequency from repeatCount, so a rate claim and "
                "a tally are different evidence and the abstraction needs the rate"
            ),
        ),
        grounding=(
            _so(
                "schema:Schedule",
                "a schedule defines a repeating time period used to describe a "
                "regularly occurring Event",
            ),
            _wn("n#05669034", "habit, wont: an established custom"),
        ),
    ),
    _l2(
        "l2:abstraction.carried_constraint",
        L2ItemType.ABSTRACTION_TYPE,
        "a restriction stated once and treated as applying to later sub-goals without restating",
        aliases=("standing requirement", "applies throughout", "keeps applying"),
        roles=(
            _slot("l2:role.subject", required=True),
            _slot("l2:role.scope", required=True),
        ),
        minimum_support=2,
        spans_sessions=True,
        provenance=(
            _sgd_dyn(
                "86.4% of multi-service dialogues carry a slot value across services: city 2238, "
                "location 1711, destination_city 1672"
            ),
        ),
    ),
    _l2(
        "l2:abstraction.standing_condition",
        L2ItemType.ABSTRACTION_TYPE,
        "a lasting fact about a subject that constrains what may be offered them at any time",
        aliases=("permanent condition", "always true of them", "hard constraint"),
        roles=(_slot("l2:role.subject", required=True),),
        spans_sessions=True,
        provenance=(
            _msc(
                "113 allergy and 80 dietary statements are conditions that outlive any one "
                "session and cannot be overridden by a later preference"
            ),
        ),
    ),
    _l2(
        "l2:abstraction.value_history",
        L2ItemType.ABSTRACTION_TYPE,
        "the ordered series of values an attribute has taken, from which the current one follows",
        aliases=("history of changes", "how it changed", "value series"),
        roles=(
            _slot("l2:role.subject", required=True),
            _slot("l2:role.tracked_attribute", required=True),
        ),
        minimum_support=2,
        spans_sessions=True,
        provenance=(
            _sgd_dyn(
                "3661 of 5110 dialogues (71.6%) revise a user slot value mid-dialogue, so "
                "the current value is only recoverable from the series"
            ),
        ),
    ),
    _l2(
        "l2:abstraction.relationship",
        L2ItemType.ABSTRACTION_TYPE,
        "a standing tie between the subject and another party, of one of the admitted kinds",
        aliases=("who they know", "personal tie", "connection to someone"),
        roles=(
            _slot("l2:role.subject", required=True),
            _slot("l2:role.first_party", required=True),
            _slot("l2:role.second_party", required=True),
        ),
        spans_sessions=True,
        constraints=(
            Constraint(
                kind="typing",
                expression=(
                    "must instantiate one of the four admitted relation types; an untyped tie is "
                    "not admitted, because 'knows somebody' carries no consequence a memory "
                    "system could act on"
                ),
            ),
            Constraint(
                kind="exclusion",
                expression=(
                    "the counterpart is held as a filled position and never as a person, so this "
                    "abstraction records that the subject has a spouse and never who"
                ),
            ),
        ),
        provenance=(
            _msc(
                "4647 relationship mentions over 65245 persona sentences, concentrated in four "
                "families. v1 recorded this as its largest O_L2 gap on the ground that any "
                "inventory would be guessed; four families at 3088/738/485/311 is a measurement"
            ),
            _so_source(
                "schema:knows, follows and relatedTo give the generic shapes, and Role "
                "with startDate/endDate gives the lifecycle"
            ),
        ),
        grounding=(
            _so(
                "schema:Role", "represents additional information about a relationship or property"
            ),
            _so("schema:relatedTo", "the most generic familial relation"),
        ),
    ),
    _l2(
        "l2:abstraction.conditional_commitment",
        L2ItemType.ABSTRACTION_TYPE,
        "a commitment held open across sessions, waiting on a condition that may never be met",
        aliases=("standing if-then", "waiting on a condition", "open conditional"),
        roles=(
            _slot("l2:role.subject", required=True),
            _slot("l2:role.scope", required=True),
        ),
        spans_sessions=True,
        constraints=(
            Constraint(
                kind="resolution",
                expression=(
                    "carries three outcomes and not two: the trigger may be met, may be settled "
                    "false, or may still be open. Collapsing the last two would make an "
                    "unresolved conditional indistinguishable from a declined one"
                ),
            ),
        ),
        provenance=(
            _sgd_acts(
                "472 availability-conditioned requests, 88 if/then frames, 43 'in case', 14 'as "
                "long as' or 'only if' over 329964 utterances. v1 read the act labels, which are "
                "uniformly unconditional, and concluded the corpus did not attest the construct"
            ),
            _msc("21 sentence-initial conditionals and 38 'when X i want Y' triggers"),
            _pb_source(
                "condition.01 supplies the argument structure a suspended commitment "
                "needs, which is what v1 was waiting for"
            ),
        ),
        grounding=(
            _pb("condition.01", "to make dependent on a condition", "ARG2 GOL dependent on"),
            _so("schema:PotentialActionStatus", "a description of an action that is supported"),
        ),
    ),
)


# --- Aggregation patterns ----------------------------------------------------------------
#
# How an abstraction is computed, as a named pattern rather than prose in each item. Five, against
# v1's four: the addition is trigger_watch, which is the only pattern whose output can be "still
# waiting" -- the others all resolve.
_PATTERNS: Final[tuple[L2Item, ...]] = (
    _l2(
        "l2:pattern.goal_decomposition",
        L2ItemType.AGGREGATION_PATTERN,
        "group observations under one intention when each advances a part of it",
        aliases=("break into sub-goals", "parts of one aim"),
        provenance=(
            _sgd_dyn("multi-service dialogues distribute one user aim over 2 to 4 services"),
        ),
    ),
    _l2(
        "l2:pattern.recurrence_count",
        L2ItemType.AGGREGATION_PATTERN,
        "count how often a behaviour recurs and compare the count against a threshold",
        aliases=("count repeats", "how many times", "tally"),
        provenance=(
            _msc("295 explicit-frequency statements are the countable form of a habit claim"),
            _so_source(
                "schema:repeatCount is declared separately from repeatFrequency, which is "
                "the distinction between this pattern and a rate claim"
            ),
        ),
        grounding=(
            _so(
                "schema:repeatCount",
                "defines the number of times a recurring Event will take place",
            ),
        ),
    ),
    _l2(
        "l2:pattern.temporal_series",
        L2ItemType.AGGREGATION_PATTERN,
        "order observations by assertion time and read the last one as current",
        aliases=("latest wins", "order by time", "series"),
        provenance=(
            _sgd_dyn("71.6% revision rate means recency, not frequency, decides the live value"),
        ),
    ),
    _l2(
        "l2:pattern.constraint_union",
        L2ItemType.AGGREGATION_PATTERN,
        "combine several restrictions into one that satisfies all of them at once",
        aliases=("all constraints together", "intersect requirements"),
        provenance=(
            _sgd_schema(
                "a search intent may carry several user restrictions simultaneously and "
                "must satisfy every one"
            ),
        ),
    ),
    _l2(
        "l2:pattern.trigger_watch",
        L2ItemType.AGGREGATION_PATTERN,
        "hold an item unresolved until its stated condition is observed to hold or to fail",
        aliases=("wait for the condition", "watch for it", "hold pending"),
        constraints=(
            Constraint(
                kind="non_termination",
                expression=(
                    "the only pattern here that need never resolve; a watch whose condition is "
                    "never observed stays open, and treating an open watch as a failure is what "
                    "would make a conditional commitment indistinguishable from a lapsed one"
                ),
            ),
        ),
        provenance=(
            _sgd_acts(
                "472 availability-conditioned requests await a fact the speaker does not "
                "have at the time of asking"
            ),
            _pb_source(
                "condition.01's ARG1/ARG2 split is what this pattern watches: the entity "
                "made dependent, and the thing it depends on"
            ),
        ),
        grounding=(_pb("condition.01", "to make dependent on a condition", "ARG1 and ARG2"),),
    ),
)


# --- Lifecycle states --------------------------------------------------------------------
#
# What becomes of an abstraction over time. Six, against v1's four. The two additions are what the
# new content needs: a relationship or commitment can be dormant without being over, and a
# conditional commitment can be settled false without ever having lapsed.
_LIFECYCLE: Final[tuple[L2Item, ...]] = (
    _l2(
        "l2:lifecycle.open",
        L2ItemType.LIFECYCLE_STATE,
        "still live and expected to progress",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("active", "in progress", "ongoing"),
        provenance=(_repo("domain.Lifecycle.ACTIVE"),),
    ),
    _l2(
        "l2:lifecycle.achieved",
        L2ItemType.LIFECYCLE_STATE,
        "completed as intended, so nothing further is outstanding",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("done", "completed", "finished"),
        provenance=(
            _sgd_acts("SYSTEM NOTIFY_SUCCESS 16868 is the observable that closes an intention"),
            _pb_source("achieve.01 and complete.01 are the positive counterpart to fail.01"),
        ),
        grounding=(
            _pb("achieve.01", "accomplish", "ARG1 PPT thing achieved"),
            _pb("complete.01", "bring to an end", "ARG1 PPT task coming to an end"),
            _so("schema:CompletedActionStatus", "an action that has already taken place"),
        ),
    ),
    _l2(
        "l2:lifecycle.lapsed",
        L2ItemType.LIFECYCLE_STATE,
        "neither completed nor withdrawn, and no longer progressing",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("went nowhere", "stalled"),
        provenance=(
            _discovery(
                "225 of 227 observations in the discovery split shaped partial_gold_overlap and "
                "1 was an empty selection, i.e. an intention that neither closed nor was "
                "retracted is the common residue. Read as a gap shape only: no question, gold "
                "label or dataset identity was consulted"
            ),
        ),
    ),
    _l2(
        "l2:lifecycle.superseded_by_revision",
        L2ItemType.LIFECYCLE_STATE,
        "replaced by a later version of the same abstraction",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("replaced", "revised away"),
        provenance=(_sgd_dyn("71.6% revision rate"),),
    ),
    _l2(
        "l2:lifecycle.dormant",
        L2ItemType.LIFECYCLE_STATE,
        "still holds but has produced no observation for long enough that it may be stale",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("quiet", "not mentioned lately", "possibly stale"),
        constraints=(
            Constraint(
                kind="distinction",
                expression=(
                    "dormant is not lapsed: a lapsed item has stopped progressing, a dormant one "
                    "is presumed still true but unconfirmed. Conflating them would make every "
                    "unmentioned relationship look ended"
                ),
            ),
        ),
        provenance=(
            _msc(
                "persona statements are asserted once and carried across sessions without "
                "restatement; 4647 relationship mentions are almost all single mentions of ties "
                "that plainly persist, so absence of restatement cannot mean absence"
            ),
            _so_source(
                "schema:Role carries startDate and endDate separately, so an open-ended "
                "role is representable without asserting it has ended"
            ),
        ),
        grounding=(_so("schema:endDate", "the end date and time of the item"),),
    ),
    _l2(
        "l2:lifecycle.condition_failed",
        L2ItemType.LIFECYCLE_STATE,
        "a conditional item whose trigger was settled false, so it will not take effect",
        role_kind=OntologyRoleKind.VOCABULARY_VALUE,
        aliases=("condition not met", "did not apply"),
        provenance=(
            _sgd_acts(
                "SYSTEM NOTIFY_FAILURE 2398 and the 472 availability-conditioned requests "
                "together give the case: the condition was checked and did not hold, which is "
                "neither an achievement nor a lapse"
            ),
        ),
        grounding=(_so("schema:FailedActionStatus", "an action that failed to complete"),),
    ),
)


# --- Evidence constraints ----------------------------------------------------------------
#
# What must be true of the support behind an abstraction. Three, against v1's two.
_EVIDENCE: Final[tuple[L2Item, ...]] = (
    _l2(
        "l2:evidence.supports_addressable",
        L2ItemType.EVIDENCE_CONSTRAINT,
        "every abstraction must name the observations it rests on, individually",
        aliases=("supports must be listed",),
        constraints=(
            Constraint(
                kind="addressability",
                expression=(
                    "an abstraction whose supports cannot be enumerated cannot be checked or "
                    "revised, so it is not admissible however plausible it looks"
                ),
            ),
        ),
        provenance=(
            _tau(
                "the retail policy requires the agent to explain a change before making it, "
                "which is impossible if the grounds are not enumerable"
            ),
        ),
    ),
    _l2(
        "l2:evidence.partial_support_marked",
        L2ItemType.EVIDENCE_CONSTRAINT,
        "an abstraction resting on fewer supports than it requires must say so rather than hold",
        aliases=("mark thin evidence",),
        provenance=(
            _discovery(
                "225 of 227 discovery observations shaped partial_gold_overlap: partial support "
                "is the normal case, so it needs a marking rather than an exception path"
            ),
        ),
    ),
    _l2(
        "l2:evidence.source_status_preserved",
        L2ItemType.EVIDENCE_CONSTRAINT,
        "an abstraction may be no better attested than the weakest observation it rests on",
        aliases=("no laundering", "weakest link"),
        constraints=(
            Constraint(
                kind="monotonicity",
                expression=(
                    "aggregating three user reports does not produce a tool-observed fact. "
                    "Without this, abstraction becomes a way of upgrading confidence that no "
                    "single observation carried, which is the failure mode that makes a memory "
                    "system confidently wrong"
                ),
            ),
        ),
        provenance=(
            _tau(
                "both environments distinguish tool returns from user reports and the policy "
                "requires confirmation before a write; an abstraction that lost that distinction "
                "would let a report authorise an action only an observation should"
            ),
            _repo(
                "domain.Speaker separates user/assistant/tool/derived, so the distinction "
                "exists at the observation layer and must survive aggregation"
            ),
        ),
    ),
)


def build_o_l2() -> L2Freeze:
    """Assemble O_L2 v2, sorted by id because the freeze hash depends on the order."""
    items = (
        *_L2_ROLES,
        *_RELATION_TYPES,
        *_ABSTRACTIONS,
        *_PATTERNS,
        *_LIFECYCLE,
        *_EVIDENCE,
    )
    return L2Freeze(
        version=O_L2_VERSION,
        items=tuple(sorted(items, key=lambda entry: entry.item.id)),
    )
