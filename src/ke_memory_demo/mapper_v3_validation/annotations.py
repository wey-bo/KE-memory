"""The labels themselves, for the fresh 160-expression mapping set.

Written by reading each expression against the union of ontology v2 and the v3 additions. No
mapper, no mapper output, no previous-round gold and no benchmark plan was opened while these were
decided, and no model or judge was called: every ``sense`` field is the annotator's own reading.

Conventions applied consistently, so a reviewer can check the labels against the rule rather than
against taste:

- Qualifier *dimensions* (``l1:qualifier.*``) are not listed. They name the axis, not the value on
  it; the value items (``l1:time.*``, ``l1:polarity.*``, ``l1:modality.*``, ``l1:strength.*``,
  ``l1:frequency.*``, ``l1:source_status.*``, ``l1:standing.*``) are what an expression attests.
- ``l1:role.*`` items are not listed either. A role is a slot in a frame, and every frame that has
  one requires it, so listing roles would inflate every count by a constant and measure nothing.
- ``l1:source_status.user_reported`` is *not* attached to every user utterance, because it holds of
  the whole corpus by construction and would add one id to 160 records. It appears only where the
  provenance is the point: an assistant claim, a report of what a third party said, or mutual
  confirmation.
- Tense and polarity *are* listed when the expression fixes them, because they are what a mapper
  has to recover from the text and they distinguish "I run" from "I used to run".
- ``none`` is used for pure backchannel, pleasantry and meta-talk about the assistant, including
  the many LoCoMo turns that are entirely "that's awesome!" plus a question. A question that seeks
  no rememberable content about the asker is ``none``; a question that also attests something about
  the asker's situation is a ``concept`` naming both.
"""

from __future__ import annotations

from typing import Final

from .models import AnnotationGold, AnnotationRecord, Outcome

ANNOTATED_SET_SHA256: Final[str] = (
    "b576db052cb158364dde3261bfb6d10d150b4874ee1dd524efc91799793d42db"
)

ANNOTATED_AGAINST_ONTOLOGY: Final[str] = "ontology v2 base plus ontology v3 additions (union)"

# The kinds of thing the combined ontology still cannot hold, named once here so the report's gap
# categories are the annotator's own taxonomy rather than a post-hoc grouping of free text.
GAP_CATEGORIES: Final[tuple[str, ...]] = (
    "affective_state",
    "epistemic_gap_or_confusion",
    "loss_or_adverse_event",
    "third_party_state",
    "artefact_or_creation",
    "social_offer_or_invitation",
    "self_narrative_or_identity",
)


def _concept(
    expression_id: str, target_ids: tuple[str, ...], sense: str, *, note: str = ""
) -> AnnotationRecord:
    """A label naming every ontology item the expression attests.

    ``needs_second_opinion`` is derived from whether a note was written rather than passed
    separately, so a flagged record cannot exist without something for a reviewer to read.
    """
    return AnnotationRecord(
        expression_id=expression_id,
        outcome=Outcome.CONCEPT,
        target_ids=tuple(sorted(target_ids)),
        sense=sense,
        needs_second_opinion=bool(note),
        adjudication_note=note,
    )


def _ambiguous(  # pyright: ignore[reportUnusedFunction]
    expression_id: str, target_ids: tuple[str, ...], sense: str, *, note: str
) -> AnnotationRecord:
    """Two or more items defensible with nothing in the text to choose between them.

    Never called. The constructor is kept, and the unused-function warning suppressed rather than
    silenced by deletion, because its absence from the call graph is the static evidence that this
    round's gold contains no ambiguous record -- which is in turn why the true-ambiguity abstention
    metric has an empty denominator and must report ``unavailable``.

    Every borderline expression resolved one of two ways: as a multi-target concept naming each
    defensible item, or by withholding the unsupported label. Deleting this helper would hide that
    the outcome was available and went unused, and adding a record now to give the metric a
    denominator would be manufacturing evidence.
    """
    return AnnotationRecord(  # pyright: ignore[reportUnusedFunction]
        expression_id=expression_id,
        outcome=Outcome.AMBIGUOUS,
        target_ids=tuple(sorted(target_ids)),
        sense=sense,
        needs_second_opinion=True,
        adjudication_note=note,
    )


def _nothing(expression_id: str, sense: str, *, note: str = "") -> AnnotationRecord:
    return AnnotationRecord(
        expression_id=expression_id,
        outcome=Outcome.NONE,
        sense=sense,
        needs_second_opinion=bool(note),
        adjudication_note=note,
    )


def _gap(expression_id: str, sense: str, would_require: str, *, note: str = "") -> AnnotationRecord:
    return AnnotationRecord(
        expression_id=expression_id,
        outcome=Outcome.OUT_OF_SCOPE,
        sense=sense,
        would_require=would_require,
        needs_second_opinion=bool(note),
        adjudication_note=note,
    )


# Flagging rule, applied uniformly so the second-opinion count means something: a record is flagged
# when it names a v3 addition, names an L2 abstraction, is ambiguous, is a coverage gap, or rests
# on a reading the annotator would want a second pair of eyes on. Plain single-target concept
# labels and plain backchannel are left single-reviewed.
_BATCH_000_039: tuple[AnnotationRecord, ...] = (
    _nothing(
        "fx-000000",
        "praise, a question about a concert, and a positive gloss on an event the other party "
        "attended; nothing rememberable about the speaker herself",
        note="the advocacy event is attested as a past occurrence, but of the addressee, and the "
        "speaker is only evaluating it. Reading it as the speaker's own activity_occurrence would "
        "attribute the wrong subject",
    ),
    _concept(
        "fx-000001",
        (
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:preference.affinity",
            "l1:state.ongoing_pursuit",
            "l1:strength.strong",
            "l1:time.at_assertion",
        ),
        "a standing strong interest in synchronicity and consciousness, plus a request for "
        "research on it, which is both an information-seeking act and a continuing intellectual "
        "pursuit",
        note="ongoing_pursuit for an intellectual interest rather than a practice is the v3 item's "
        "boundary case; affinity carries the liking and pursuit carries the continuing engagement",
    ),
    _nothing(
        "fx-000002",
        "compliment on a picture plus a generic question about the other party's cooking; the "
        "speaker attests nothing about himself",
    ),
    _concept(
        "fx-000003",
        ("l1:event.information_request", "l1:modality.question", "l1:predicate.seek_information"),
        "asks the other party which part of town they want to live in; a question about the "
        "addressee's residence preference, so what is attested is the asking",
        note="the housing difficulty is attributed to the addressee, not the speaker. Only the "
        "asking is the speaker's own content",
    ),
    _concept(
        "fx-000004",
        (
            "l1:event.information_request",
            "l1:modality.question",
            "l1:preference.affinity",
            "l1:state.ongoing_pursuit",
            "l1:strength.strong",
        ),
        "a strong standing liking for a book series and its immersive world, together with a "
        "question about the name of a dog in the other party's photo",
        note="reading is a v3 ongoing_pursuit here because he is mid-series and describes what the "
        "books do for him; the affinity and the strength are separate attestations",
    ),
    _nothing(
        "fx-000005",
        "pleasantry and a well-wish about the addressee's hike; no content about the speaker",
    ),
    _concept(
        "fx-000006",
        (
            "l1:event.attempt_failed",
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:task.declared_intention",
            "l1:time.at_assertion",
        ),
        "an in-progress attempt to improve an algorithm that is currently stuck, plus a request "
        "for ideas",
        note="attempt_failed is the closest v2 item for 'stuck': the attempt is ongoing rather "
        "than concluded, so a reviewer may prefer declared_intention alone",
    ),
    _concept(
        "fx-000007",
        (
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:state.ongoing_pursuit",
            "l1:time.spanning",
        ),
        "an ongoing attempt to write jokes, which is a continuing creative practice, plus a "
        "request for tips on structuring them",
        note="joke writing as ongoing_pursuit is a v3 absorption; v2 could only have held the "
        "information request",
    ),
    _nothing(
        "fx-000008",
        "agreement with a generic claim about pets plus two questions about the addressee's "
        "mentoring programme; nothing about the speaker",
    ),
    _nothing("fx-000009", "pure agreement backchannel with no propositional content"),
    _concept(
        "fx-000010",
        ("l1:event.information_request", "l1:modality.question", "l1:predicate.seek_information"),
        "asks where the addressees plan to explore; the speaker attests only the asking",
    ),
    _concept(
        "fx-000011",
        ("l1:event.information_request", "l1:modality.question", "l1:predicate.seek_information"),
        "a general question about the benefits of learning music theory, with nothing said about "
        "the asker's own situation",
        note="tempting to read a musical pursuit into it, but the question is framed about "
        "musicians in general and never says the asker is one",
    ),
    _concept(
        "fx-000012",
        (
            "l1:predicate.hold_belief",
            "l1:state.occupation_status",
            "l1:task.declared_intention",
            "l1:time.at_assertion",
            "l2:abstraction.project",
        ),
        "finishing a business plan and looking for investors as one multi-step undertaking, "
        "driven by a stated belief that the project will succeed",
        note="v3 hold_belief carries 'belief in its success'; the passion is an affective state "
        "with no home. Flagged also for the L2 project reading, which rests on the two sub-goals "
        "advancing one aim",
    ),
    _concept(
        "fx-000013",
        ("l1:modality.directed", "l1:predicate.possess", "l1:time.at_assertion"),
        "reports having new details for a case and directs the other party to rate it",
        note="'details for this case' is possession of information at her disposal; a reviewer "
        "might read the case as an open task instead, which the text does not settle",
    ),
    _concept(
        "fx-000014",
        (
            "l1:event.activity_occurrence",
            "l1:modality.desired",
            "l1:time.before_assertion",
        ),
        "two days ago he wanted to be alone with nature and went to a canyon he found nearby, "
        "which he reports as a past occasion",
        note="the visit is a v3 activity_occurrence; the desire behind it is separately attested "
        "and the calming view is an evaluation with no ontology home",
    ),
    _concept(
        "fx-000015",
        (
            "l1:attribute.designation",
            "l1:event.activity_occurrence",
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.consume_media",
            "l1:predicate.transfer_value",
            "l1:preference.affinity",
            "l1:state.possession",
            "l1:strength.strong",
            "l1:time.before_assertion",
        ),
        "a strong current liking for indie and folk-rock, a festival attended last weekend where "
        "a named band was discovered, an EP bought there and now owned and repeatedly listened "
        "to, and a request for similar artists",
        note="the densest expression in the set: purchase, attendance, possession, listening, "
        "taste and a request all in one turn. Worth checking that nothing was dropped",
    ),
    _concept(
        "fx-000016",
        (
            "l1:event.information_request",
            "l1:modality.desired",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:state.possession",
        ),
        "wants a cosier living room and asks for lamp placement ideas; the living room is a place "
        "at the speaker's disposal and the atmosphere is what they want",
        note="possession of a living room is thin but it is the attribute bearer the desire is "
        "about; a reviewer may prefer to drop it",
    ),
    _concept(
        "fx-000017",
        (
            "l1:event.activity_occurrence",
            "l1:frequency.habitual",
            "l1:preference.affinity",
            "l1:state.ongoing_pursuit",
            "l1:strength.paramount",
            "l1:time.recurring",
            "l2:abstraction.habit",
        ),
        "an annual family camping trip with marshmallows and campfire stories, described as the "
        "recurring highlight of the speaker's summer",
        note="the clearest habit in the set: recurrence plus paramount strength plus a named set "
        "of practices. Flagged for the L2 habit reading and the v3 pursuit item",
    ),
    _concept(
        "fx-000018",
        ("l1:predicate.hold_value", "l1:task.declared_intention", "l1:time.at_assertion"),
        "holds affecting people and the world positively as what matters to him, and states an "
        "intention to find a better way to focus on it, while currently feeling stuck",
        note="v3 hold_value is what makes this expressible; the stuckness itself is an affective "
        "state the ontology has no item for, so it is carried only in the sense",
    ),
    _concept(
        "fx-000019",
        (
            "l1:event.information_request",
            "l1:modality.question",
            "l1:polarity.indeterminate",
            "l1:state.pending_arrangement",
            "l1:time.at_assertion",
        ),
        "a trip is being planned with the destination not yet settled, and suggestions are "
        "requested",
        note="pending_arrangement is defensible because a trip is in progress, but nothing is "
        "committed to yet; a reviewer may prefer declared_intention",
    ),
    _concept(
        "fx-000020",
        (
            "l1:event.activity_occurrence",
            "l1:event.objective_achieved",
            "l1:time.before_assertion",
        ),
        "last Thursday he worked with a gaming friend on a programming project and they finished "
        "a Witcher-3-inspired virtual world",
        note="a dated collaborative occasion plus a completion; the friend is a participant. The "
        "created artefact itself has no ontology home",
    ),
    _nothing(
        "fx-000021",
        "sympathetic advice and a question about how the addressee might channel their energy; "
        "nothing rememberable about the speaker",
    ),
    _nothing(
        "fx-000022",
        "thanks plus an evaluative gloss on people coming together for a cause; the cause is "
        "never named, so nothing specific is attested",
        note="'we've gotta do what we can' brushes against hold_value, but no value content is "
        "named and the cause is only a deictic reference to the previous turn",
    ),
    _concept(
        "fx-000023",
        (
            "l1:event.activity_occurrence",
            "l1:predicate.reside_at",
            "l1:state.residence",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
        ),
        "lives in Boston, will show the addressee around when he visits, and commits to attending "
        "his performance from the front row",
        note="the residence is inferred from 'show you around town' plus naming local venues, "
        "which is strong but not stated; flagged for that inference",
    ),
    _concept(
        "fx-000024",
        ("l1:predicate.hold_belief", "l1:predicate.hold_value", "l1:preference.avoidance"),
        "believes positive reinforcement is the right way to train pets and that punishment is "
        "never proper, stated as a general claim she treats as important",
        note="a v3 hold_belief with a normative edge; avoidance covers 'punishment is never the "
        "proper way'. Whether hold_value adds anything over hold_belief here is worth a check",
    ),
    _concept(
        "fx-000025",
        (
            "l1:attribute.assessment",
            "l1:attribute.kind",
            "l1:event.media_consumption",
            "l1:predicate.consume_media",
            "l1:time.before_assertion",
        ),
        "watched a classic movie recently, judged the story gripping and the acting good, and "
        "reports it stayed with her",
        note="kind covers 'classic movie' as a genre; the assessment is hers rather than a public "
        "rating, which is what attribute.assessment's attribution clause allows",
    ),
    _concept(
        "fx-000026",
        (
            "l1:event.activity_occurrence",
            "l1:event.first_encounter",
            "l1:time.before_assertion",
        ),
        "started spending time with people outside his usual circle whom he met at a tournament",
        note="first_encounter plus the tournament as an occasion he took part in; whether the new "
        "acquaintance rises to an L2 relationship on one mention is doubtful, so it is not named",
    ),
    _concept(
        "fx-000027",
        (
            "l1:frequency.habitual",
            "l1:predicate.seek_information",
            "l1:preference.affinity",
            "l1:state.ongoing_pursuit",
            "l1:time.at_assertion",
        ),
        "habitually looks for new exercise routines to vary her training, which presupposes a "
        "continuing practice",
        note="'routines' is read as exercise from the standing context of the turn; the pursuit is "
        "a v3 absorption and the habitual frequency is explicit in 'always'",
    ),
    _concept(
        "fx-000028",
        (
            "l1:preference.avoidance",
            "l1:state.capability_constraint",
            "l1:time.unspecified",
        ),
        "lactose intolerant, so requires a dairy-free recipe; a standing condition that restricts "
        "what may be offered her",
        note="the canonical standing_condition case. capability_constraint plus avoidance rather "
        "than the L2 abstraction, which would need a second support",
    ),
    _concept(
        "fx-000029",
        ("l1:event.information_request", "l1:modality.question", "l1:predicate.seek_information"),
        "asks what made the other party name their pet Tilly; only the asking is the speaker's",
    ),
    _concept(
        "fx-000030",
        (
            "l1:event.attempt_failed",
            "l1:predicate.occupy_role",
            "l1:state.occupation_status",
            "l1:state.ongoing_pursuit",
            "l1:time.before_assertion",
        ),
        "a writer whose laptop crashed last week and who lost all her work, which she describes "
        "as a major blow to her livelihood",
        note="occupation is stated ('as a writer'); the crash and data loss are an adverse event "
        "the ontology can only approximate through attempt_failed, which is a poor fit",
    ),
    _nothing("fx-000031", "shared excitement with no propositional content of its own"),
    _nothing(
        "fx-000032",
        "pleasantry plus an invitation to report back after reading; the reading is the "
        "addressee's, not the speaker's",
    ),
    _gap(
        "fx-000033",
        "reports that a third party, most likely his son or his dog, is happy and carefree in "
        "their favourite activity",
        "a frame for a third party's affective state and their favourite activity, where the "
        "subject of the memory is not the speaker; the combined ontology models the remembered "
        "subject and admits participants, but has no way to hold an attributed state of another "
        "party as its own content",
        note="the activity is a v3 pursuit but the bearer is a third party and the content is "
        "their enjoyment, so a concept label would attribute it to the wrong subject",
    ),
    _concept(
        "fx-000034",
        ("l1:event.information_request", "l1:modality.question", "l1:predicate.seek_information"),
        "asks what something the other party mentioned is about; a bare information request",
    ),
    _concept(
        "fx-000035",
        (
            "l1:modality.desired",
            "l1:polarity.denied",
            "l1:state.capability",
            "l1:time.after_assertion",
            "l1:time.before_assertion",
        ),
        "has not worked with any programming language other than his current one, and hopes to in "
        "future",
        note="a denied v3 capability plus a desire; the two time qualifiers are deliberate, one "
        "for the negated past experience and one for the hoped-for future",
    ),
    _concept(
        "fx-000036",
        ("l1:predicate.hold_belief", "l1:preference.affinity"),
        "holds a general claim that pets become friends and confidantes who listen, comfort and "
        "leave a lasting mark",
        note="a v3 hold_belief about pets in general rather than about any pet of his; the warmth "
        "toward pets is the affinity",
    ),
    _concept(
        "fx-000037",
        (
            "l1:event.information_request",
            "l1:modality.question",
            "l1:preference.affinity",
            "l1:state.ongoing_pursuit",
        ),
        "asks the addressees to confirm that they enjoy spending time together in this bar, which "
        "presupposes a recurring practice he attributes to them",
        note="a tag question attributing an affinity to the addressees; a reviewer may prefer "
        "none, since the content is about them and the speaker only seeks confirmation",
    ),
    _nothing("fx-000038", "well-wish and a hedged agreement; no rememberable content"),
    _concept(
        "fx-000039",
        (
            "l1:event.activity_occurrence",
            "l1:event.objective_achieved",
            "l1:attribute.assessment",
            "l1:time.before_assertion",
        ),
        "ran a seminar that went well with a good turnout, learned new things from it, and found "
        "sharing his knowledge fulfilling",
        note="hosting the seminar is a v3 activity_occurrence and its successful completion is "
        "the achievement; the fulfilment is affective and has no item",
    ),
)


_BATCH_040_079: tuple[AnnotationRecord, ...] = (
    _concept(
        "fx-000040",
        (
            "l1:event.objective_achieved",
            "l1:state.pending_arrangement",
            "l1:time.after_assertion",
            "l1:time.before_assertion",
        ),
        "finished building his first mobile game, which he frames as a career milestone, and it "
        "launches next month",
        note="two times on purpose: the completion is past and the launch is a scheduled future "
        "arrangement. Whether a launch date he does not control is a pending_arrangement is worth "
        "checking",
    ),
    _nothing(
        "fx-000041",
        "congratulations, a compliment on a photo and a generic remark that such moments make "
        "life wonderful; nothing about the speaker",
    ),
    _concept(
        "fx-000042",
        (
            "l1:attribute.affiliation",
            "l1:event.life_transition",
            "l1:polarity.denied",
            "l1:predicate.undergo_transition",
            "l1:state.occupation_status",
            "l1:time.before_assertion",
        ),
        "lost his job at a mechanical engineering company that went under, an unforeseen "
        "transition he is finding hard",
        note="affiliation is now denied of him, which is why polarity is named; the hardship is "
        "affective and unrepresentable, and 'never saw this coming' is a defeated expectation with "
        "no item",
    ),
    _nothing("fx-000043", "thanks and appreciation for support; no rememberable content"),
    _gap(
        "fx-000044",
        "characterises the addressee as someone who never shies from a challenge and always tries "
        "new things, and says he finds that inspiring",
        "a frame for an attributed disposition or character trait of another party, distinct from "
        "a preference or a habit of the remembered subject; the combined ontology holds habits and "
        "preferences of a subject, not one party's standing characterisation of another",
        note="frequency.invariant plus a pursuit would put the content on the wrong subject and "
        "would turn a character judgement into a behavioural record",
    ),
    _concept(
        "fx-000045",
        (
            "l1:event.information_request",
            "l1:modality.question",
            "l1:polarity.indeterminate",
            "l1:predicate.seek_information",
            "l1:state.ongoing_pursuit",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
        ),
        "planning a next trip, undecided between solo and family travel, and asking how to "
        "balance freedom against bonding time",
        note="travel as an ongoing pursuit is defensible from 'my next trip' implying a series; a "
        "reviewer may keep only the intention and the request",
    ),
    _concept(
        "fx-000046",
        ("l1:predicate.hold_value", "l1:preference.affinity"),
        "says he loves making the third party happy, which is a standing thing he cares about "
        "rather than a one-off",
        note="v3 hold_value for 'I love making him happy' as a priority of his; the affinity "
        "carries the liking. A reviewer may find hold_value too strong for a thanks-turn",
    ),
    _nothing(
        "fx-000047",
        "a teaser announcing she has something to show; the content itself is never stated",
    ),
    _concept(
        "fx-000048",
        (
            "l1:attribute.assessment",
            "l1:event.activity_occurrence",
            "l1:predicate.hold_value",
            "l1:state.ongoing_pursuit",
            "l1:time.at_assertion",
        ),
        "makes beats for young artists, is doing so in the photo, values paying it forward and "
        "working with new talent, and judges this artist to have great musical potential",
        note="dense and multi-layered: a v3 pursuit (making beats), a v3 occurrence (this "
        "session), a v3 value (paying it forward) and an assessment of a third party",
    ),
    _nothing(
        "fx-000049",
        "sign-off pleasantry with an agreement to report back later; nothing rememberable",
    ),
    _concept(
        "fx-000050",
        ("l1:predicate.hold_value", "l1:preference.affinity", "l1:strength.strong"),
        "cherishes time with family and says it is when she feels most alive and happy",
        note="the clearest v3 hold_value in the set; the affective payoff is not representable but "
        "the value and its strength are",
    ),
    _concept(
        "fx-000051",
        (
            "l1:predicate.consume_media",
            "l1:predicate.hold_belief",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
            "l1:time.before_assertion",
        ),
        "read a book that convinced him a focused, efficient business adapting to customer "
        "feedback is right, and intends to try that approach",
        note="v3 hold_belief for the general claim he took from the book; consume_media for having "
        "read it and a declared intention to act on it",
    ),
    _concept(
        "fx-000052",
        (
            "l1:event.activity_occurrence",
            "l1:state.ongoing_pursuit",
            "l1:time.before_assertion",
            "l1:time.spanning",
        ),
        "has been taking notes about local politics in her notebook over some period, alongside "
        "praise for the addressee",
        note="note-taking on local politics reads as a v3 ongoing pursuit given the progressive "
        "aspect; the praise for John is not her own content",
    ),
    _nothing(
        "fx-000053",
        "encouragement predicting that a third party's advice will help the addressee; nothing "
        "about the speaker",
    ),
    _nothing(
        "fx-000054",
        "congratulations on a marriage plus a generic remark about love; the marriage is the "
        "addressee's, not the speaker's",
        note="the addressee's marriage is memory-worthy but belongs to the addressee; a "
        "relationship label here would record the wrong subject",
    ),
    _concept(
        "fx-000055",
        (
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.consume_media",
            "l1:predicate.seek_information",
            "l1:state.ongoing_pursuit",
            "l1:time.at_assertion",
            "l2:abstraction.project",
        ),
        "working on a short film project, has watched and been thinking about the cinematography "
        "of Joker, and asks whether camera format affects a film's mood",
        note="the short film is an L2 project with a genuine second support (the ongoing "
        "filmmaking practice); flagged for that and for the pursuit reading",
    ),
    _concept(
        "fx-000056",
        (
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:role.quantity",
            "l1:state.ongoing_pursuit",
            "l1:task.outstanding_requirement",
            "l1:time.before_assertion",
            "l2:abstraction.pursuit_profile",
        ),
        "has written seventeen poems in the past two weeks as creative self-expression, has "
        "writing deadlines to stay on top of, and asks for scheduling tools",
        note="the only place a role id is named: the count of seventeen is the attestation, not a "
        "slot the frame happens to have. Flagged also for the v3 L2 pursuit_profile, which the "
        "productivity burst plus the standing practice jointly support",
    ),
    _concept(
        "fx-000057",
        (
            "l1:event.information_request",
            "l1:modality.question",
            "l1:preference.affinity",
            "l1:state.ongoing_pursuit",
            "l1:strength.strong",
        ),
        "loves games of the kind the addressee made and asks whether development was difficult",
        note="'I love those games too' is an affinity of the speaker's; whether playing them "
        "amounts to an ongoing pursuit on this evidence is the judgement to check",
    ),
    _concept(
        "fx-000058",
        (
            "l1:attribute.place",
            "l1:preference.affinity",
            "l1:state.ongoing_pursuit",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
        ),
        "knows and enjoys particular routes near the river and offers to show the addressee the "
        "best ones",
        note="the routes are a place attribute and the enjoyment is his; the offer to show them "
        "is a social offer, which is only partly captured as a declared intention",
    ),
    _concept(
        "fx-000059",
        (
            "l1:state.pending_arrangement",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
        ),
        "an imminent visit is arranged, and he intends to show the visitor the local music and "
        "food when it happens",
        note="pending_arrangement rests on 'see you soon' plus the prior arrangement being "
        "presupposed rather than made here",
    ),
    _nothing(
        "fx-000060",
        "congratulatory backchannel plus an exhortation to cherish family time; nothing about the "
        "speaker",
    ),
    _concept(
        "fx-000061",
        (
            "l1:event.information_request",
            "l1:modality.believed",
            "l1:modality.question",
            "l1:polarity.indeterminate",
            "l1:predicate.seek_information",
            "l1:state.capability_constraint",
            "l1:task.declared_intention",
        ),
        "thinks a custom phone case or personalised journal would be a good gift, does not know "
        "how to design or order one, and asks for websites or tools",
        note="capability_constraint for the admitted inability to design it; a reviewer may prefer "
        "state.capability denied instead, which is why this is flagged",
    ),
    _concept(
        "fx-000062",
        (
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.possess",
            "l1:predicate.seek_information",
            "l1:state.possession",
            "l1:task.outstanding_requirement",
            "l1:time.at_assertion",
        ),
        "owns a car whose centre console is dusty and needs cleaning, and asks for cleaning tips "
        "and a product recommendation",
        note="the dirty console is a state of a possessed thing rather than of the subject; "
        "outstanding_requirement carries the cleaning that still needs doing",
    ),
    _nothing(
        "fx-000063",
        "asks which part of an experience the addressee remembers best; the content sought is the "
        "addressee's",
        note="an information_request label is defensible for any question, but the convention "
        "applied here reserves it for requests whose content bears on the asker",
    ),
    _concept(
        "fx-000064",
        (
            "l1:attribute.assessment",
            "l1:event.activity_occurrence",
            "l1:preference.affinity",
            "l1:time.before_assertion",
        ),
        "played the game in question, judged its world immersive and its story amazing, and "
        "predicts the addressee will like it",
        note="playing it is a v3 occurrence; the recommendation to the addressee is a prediction "
        "with no ontology item",
    ),
    _concept(
        "fx-000065",
        ("l1:predicate.hold_belief",),
        "holds that nature is calming and resets the mind and body, stated as a general claim "
        "rather than about a particular occasion",
        note="a v3 hold_belief that v2 could only have forced into hold_attitude, losing that it "
        "is a general claim about the world",
    ),
    _gap(
        "fx-000066",
        "reports that things have been challenging lately and that something has been hard on his "
        "health, without saying what",
        "a health-status frame, or at minimum a way to hold an unspecified adverse condition "
        "affecting the subject; state.circumstance is the nearest v2 item but its sense is a "
        "general condition rather than a health impairment, and nothing in v3 adds health",
        note="the strongest gap in the set. state.circumstance would technically hold it, so a "
        "reviewer may downgrade this to concept; the reason it is a gap is that a memory that "
        "cannot say 'health' cannot answer a question about health",
    ),
    _concept(
        "fx-000067",
        (
            "l1:event.activity_occurrence",
            "l1:event.objective_achieved",
            "l1:predicate.transfer_value",
            "l1:time.before_assertion",
        ),
        "ran a game event that succeeded, drew a large turnout and raised money for charity",
        note="hosting is a v3 occurrence, the success is the achievement and the fundraising is a "
        "transfer of value to a third party",
    ),
    _gap(
        "fx-000068",
        "feels much more confident and excited to show off his car, and trusts the expertise of "
        "whoever worked on it",
        "an affective-state frame for confidence and excitement, plus a way to hold trust in "
        "another party's competence; v2 and v3 together model attitudes toward objects and beliefs "
        "about the world, but not a felt state of the subject nor trust placed in an agent",
        note="possession of the car is presupposed rather than asserted here, so a possession "
        "label would be reaching; the whole content is affect and trust",
    ),
    _nothing(
        "fx-000069",
        "congratulation on a wedding, a generic remark about love, and a question about the "
        "addressee's favourite memories; nothing about the speaker",
    ),
    _concept(
        "fx-000070",
        (
            "l1:modality.intended",
            "l1:state.ongoing_pursuit",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
        ),
        "is trying to treat a setback as a chance to find other ways of staying active and "
        "travelling, and may try something different",
        note="the reframing itself is a coping stance with no item; what is representable is the "
        "intention to explore other active pursuits",
    ),
    _concept(
        "fx-000071",
        (
            "l1:attribute.designation",
            "l1:event.media_consumption",
            "l1:modality.desired",
            "l1:predicate.consume_media",
            "l1:preference.affinity",
            "l1:time.before_assertion",
        ),
        "watched Unbox Therapy's review of the Google Pixel 6 and has since been considering "
        "buying that named phone",
        note="the review is named media he consumed and the phone is a named option he is drawn "
        "to; the consideration is a desire short of an intention",
    ),
    _concept(
        "fx-000072",
        (
            "l1:event.information_request",
            "l1:frequency.habitual",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
            "l2:abstraction.habit",
        ),
        "has a habitual grocery shopping routine, intends to change it, and asks how to optimise "
        "lists and reduce food waste",
        note="'my grocery shopping routine' names an existing habit explicitly, which is why the "
        "L2 item is defensible on one turn",
    ),
    _nothing("fx-000073", "thanks plus an assurance she will follow the advice; nothing to keep"),
    _nothing(
        "fx-000074",
        "admiration for a collective effort plus a question about what the addressee does there; "
        "nothing about the speaker",
    ),
    _concept(
        "fx-000075",
        (
            "l1:event.activity_occurrence",
            "l1:frequency.rare",
            "l1:predicate.hold_belief",
            "l1:preference.affinity",
            "l1:state.ongoing_pursuit",
            "l1:state.possession",
            "l1:time.before_assertion",
        ),
        "agrees that nature time is needed, has pets she normally walks outdoors and loves doing "
        "so, but life has been hectic so it has been a while since the last walk",
        note="frequency.rare is about the recent lapse rather than the settled pattern, which is "
        "the tension worth adjudicating; the dogs are a possession and the walking is a pursuit",
    ),
    _nothing(
        "fx-000076",
        "agreement plus a question about the addressee's favourite game with a third party",
    ),
    _nothing("fx-000077", "a bare question about the addressee's preferred reading genre"),
    _concept(
        "fx-000078",
        (
            "l1:event.information_request",
            "l1:modality.question",
            "l1:state.ongoing_pursuit",
            "l1:state.possession",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
        ),
        "asks where a pictured spot is because she wants to take her dogs walking there",
        note="the walking pursuit and the dogs are presupposed by 'my pups'; the intention is "
        "conditional on learning the location, which the ontology could also hold as a "
        "conditional intention",
    ),
    _concept(
        "fx-000079",
        ("l1:modality.directed", "l1:preference.affinity", "l1:task.conditional_intention"),
        "recommends the thing under discussion on condition the addressee is willing to explain "
        "it to their friends",
        note="the condition attaches to her recommendation rather than to an intention of her own, "
        "so conditional_intention is a stretch; a reviewer may drop it",
    ),
)

_BATCH_080_119: tuple[AnnotationRecord, ...] = (
    _concept(
        "fx-000080",
        (
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:state.possession",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
        ),
        "owns tea sets and typewriters he intends to sell, plans to approach local antique dealers "
        "who specialise in them, and asks whether that is wise and how to do it",
        note="the items are a possession he means to transfer; the sale itself has not happened, "
        "so transfer_value would be premature",
    ),
    _nothing(
        "fx-000081",
        "congratulates the addressee on finding a group where she can have an impact and invites "
        "her to say more; nothing about the speaker",
    ),
    _concept(
        "fx-000082",
        (
            "l1:event.activity_occurrence",
            "l1:event.objective_achieved",
            "l1:predicate.hold_value",
            "l1:preference.affinity",
            "l1:time.before_assertion",
        ),
        "worked with someone from the group on a project last week where their complementary "
        "strengths produced something good, and holds collaboration as valuable in general",
        note="the dated collaboration is a v3 occurrence with a participant and the general "
        "'it's great working with others' is a v3 value; whether that last clause is a value or "
        "merely an attitude is worth checking",
    ),
    _concept(
        "fx-000083",
        (
            "l1:attribute.place",
            "l1:event.information_request",
            "l1:modality.desired",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:preference.affinity",
            "l1:state.ongoing_pursuit",
        ),
        "wants to explore more local artists' work and asks for LA-based street artists and "
        "muralists to look at",
        note="following street art reads as an ongoing pursuit; the LA locality is a place "
        "attribute of what is sought rather than a stated residence",
    ),
    _concept(
        "fx-000084",
        (
            "l1:attribute.calendar_position",
            "l1:attribute.designation",
            "l1:event.activity_occurrence",
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.transfer_value",
            "l1:preference.affinity",
            "l1:time.before_assertion",
            "l2:abstraction.relationship",
            "l2:relation.friendship",
        ),
        "asks about a named watch model, and reports attending her best friend's thirtieth "
        "birthday party on 22 April, where the personalised photo album she gave was well received",
        note="the densest L2 case: best_friend is a named friendship, so both the abstraction and "
        "the relation kind are defensible from one turn. The dated party and the gift are separate "
        "attestations",
    ),
    _nothing("fx-000085", "a bare question about challenges the addressee has met"),
    _nothing(
        "fx-000086",
        "asks what something in a shared image is and says he looks forward to the story",
    ),
    _concept(
        "fx-000087",
        (
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:preference.affinity",
        ),
        "wants to know the current state of AI in medical diagnosis and asks for recent "
        "breakthroughs and notable applications",
        note="'particularly interested in' is a topical affinity; there is no evidence of a "
        "practice, so no pursuit label",
    ),
    _concept(
        "fx-000088",
        (
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.hold_belief",
            "l1:predicate.seek_information",
            "l1:state.ongoing_pursuit",
        ),
        "holds that the practice under discussion helps with challenges and gives balance and "
        "strength, and asks for tips on staying relaxed while studying",
        note="studying is the pursuit the question presupposes; the belief is about the practice's "
        "benefits rather than a report of an occasion",
    ),
    _concept(
        "fx-000089",
        (
            "l1:state.possession",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
        ),
        "accepts the advice and states he will look after his dogs first",
        note="the priority ordering ('first') brushes against hold_value but the text is an "
        "intention about a specific next action, so the intention is what is labelled",
    ),
    _gap(
        "fx-000090",
        "found the occasion meaningful because it recalled her own past struggles and her "
        "loneliness then, and she was glad to share her story and support others",
        "a frame for the subject's remembered emotional history and for the personal significance "
        "an event holds for them; v2 and v3 hold events, values and beliefs, but not a felt "
        "past state nor the meaning a subject assigns to an occasion",
        note="hold_value could be forced onto 'make a difference', but the content of the turn is "
        "the significance and the recalled feeling, which is what a concept label would drop",
    ),
    _concept(
        "fx-000091",
        (
            "l1:attribute.designation",
            "l1:modality.desired",
            "l1:predicate.hold_value",
            "l1:preference.affinity",
            "l1:preference.comparative",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
        ),
        "is considering sponsorship or collaboration with named sports brands, prefers "
        "sports-related brands while remaining open to others that align with his values",
        note="preference.comparative is defensible because sports brands are ranked above the open "
        "alternative; hold_value is explicit in 'align with my values' even though the values "
        "themselves are not named, which is the reason for the flag",
    ),
    _concept(
        "fx-000092",
        (
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:preference.threshold",
            "l1:state.ongoing_pursuit",
            "l1:task.declared_intention",
        ),
        "will try the quinoa tips, and asks for vegan protein sources for salads that are high in "
        "protein and low in carbohydrate",
        note="threshold is the right item for the high-protein low-carb constraint; whether the "
        "vegan framing is a standing avoidance or just this request's scope is not settled by the "
        "text, so no avoidance label",
    ),
    _concept(
        "fx-000093",
        (
            "l1:attribute.designation",
            "l1:preference.affinity",
            "l1:role.duration",
            "l1:state.possession",
            "l1:strength.strong",
            "l1:time.spanning",
        ),
        "has had three named pets for three years and says she could not live without them",
        note="the three-year span is the attestation rather than an incidental slot, which is why "
        "role.duration is named here as it was for the poem count",
    ),
    _concept(
        "fx-000094",
        (
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.consume_media",
            "l1:predicate.seek_information",
            "l1:state.ongoing_pursuit",
            "l1:task.declared_intention",
            "l1:time.at_assertion",
        ),
        "is taking up yoga, follows Adriene's videos on YouTube for it, and asks for apps with "
        "more variety",
        note="the yoga practice is a v3 pursuit and the videos are consumed media; the request for "
        "variety is a preference the ontology holds only as the asking",
    ),
    _nothing(
        "fx-000095",
        "asks whether the addressee's pets enjoy an object and compliments how comfy it looks",
    ),
    _concept(
        "fx-000096",
        (
            "l1:attribute.place",
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.reside_at",
            "l1:predicate.seek_information",
            "l1:state.residence",
            "l1:time.at_assertion",
        ),
        "is in Los Angeles, knows the downtown area has much street art, and asks for specific "
        "recommendations and upcoming events or festivals",
        note="'I'm in the city of Los Angeles' is ambiguous between residence and current "
        "location; residence is taken because the surrounding request is about exploring locally "
        "over time",
    ),
    _nothing("fx-000097", "thanks for support; no rememberable content"),
    _nothing(
        "fx-000098",
        "compliments a photo of a crowd and stage and asks who the headliner was",
    ),
    _concept(
        "fx-000099",
        (
            "l1:attribute.affiliation",
            "l1:attribute.designation",
            "l1:event.first_encounter",
            "l1:modality.directed",
            "l1:task.outstanding_requirement",
            "l1:time.before_assertion",
            "l2:abstraction.task",
        ),
        "met Jason, CEO of StartupX, at the TechConnect conference, owes him a follow-up about "
        "collaboration, and asks for help drafting the email",
        note="a named first encounter with affiliation, plus an explicit outstanding item ('I "
        "should follow up'); the L2 task is defensible because the follow-up has a lifecycle the "
        "tracker column is meant to hold",
    ),
    _concept(
        "fx-000100",
        (
            "l1:attribute.calendar_position",
            "l1:event.activity_occurrence",
            "l1:event.information_request",
            "l1:modality.question",
            "l1:state.ongoing_pursuit",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
            "l1:time.at_assertion",
        ),
        "started a solo camping trip to Yosemite today, is planning a further Eastern Sierra trip "
        "for July or August, and asks for scenic hiking trails there",
        note="two trips at two times, which is why both time qualifiers are named; hiking and "
        "camping are the pursuit the plan presupposes",
    ),
    _concept(
        "fx-000101",
        (
            "l1:attribute.assessment",
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:state.ongoing_pursuit",
            "l1:state.possession",
            "l1:task.declared_intention",
            "l2:abstraction.project",
        ),
        "runs a YouTube channel whose most popular video is about social media analytics, judges "
        "the direction to be working, and wants help brainstorming new content ideas",
        note="the channel is an ongoing creative pursuit and the strategy improvement is a project "
        "with sub-goals; the popularity is an assessment he draws from comment volume",
    ),
    _concept(
        "fx-000102",
        (
            "l1:event.attempt_failed",
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.possess",
            "l1:preference.avoidance",
            "l1:role.duration",
            "l1:state.possession",
            "l1:state.ongoing_pursuit",
            "l1:time.before_assertion",
        ),
        "owns a stand mixer that broke last month and took two weeks at a repair shop, baked by "
        "hand meanwhile, and now wants dessert recipes that need no stand mixer",
        note="the breakage is an adverse event that attempt_failed fits only loosely; the two-week "
        "repair duration is stated and load-bearing for why the constraint is wanted",
    ),
    _concept(
        "fx-000103",
        (
            "l1:attribute.designation",
            "l1:event.activity_occurrence",
            "l1:event.information_request",
            "l1:modality.desired",
            "l1:modality.question",
            "l1:preference.comparative",
            "l1:task.declared_intention",
            "l1:time.before_assertion",
        ),
        "attended his colleague Alex's leadership-programme graduation a few weeks ago, which "
        "prompted thoughts about his own education, and is choosing between two digital marketing "
        "certifications",
        note="preference.comparative because the choice is explicitly between two named "
        "alternatives; the attendance is a v3 occurrence with a named participant",
    ),
    _concept(
        "fx-000104",
        (
            "l1:state.ongoing_pursuit",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
        ),
        "will start preparing ingredients for the Korean Chicken Stew and will adjust the cooking "
        "time for chicken breast",
        note="cooking is the pursuit and the preparation is the immediate intention; the thanks is "
        "pleasantry that carries nothing",
    ),
    _nothing(
        "fx-000105",
        "the assistant thanking the user and asking the next survey question about Netflix genre "
        "diversity; assistant meta-talk with no user content",
        note="an assistant turn, so source_status.assistant_asserted would apply if anything were "
        "attested; nothing is, because the turn only poses a question",
    ),
    _concept(
        "fx-000106",
        (
            "l1:attribute.designation",
            "l1:event.activity_occurrence",
            "l1:event.information_request",
            "l1:modality.desired",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:time.before_assertion",
        ),
        "saw pandas eating dinner at another zoo previously, and asks how best to plan a day at "
        "the San Diego Zoo to make the most of the Nighttime Zoo event",
        note="the earlier zoo visit is a past occurrence and the planned visit is a desire; the "
        "named event is a designation of what is asked about",
    ),
    _concept(
        "fx-000107",
        (
            "l1:attribute.magnitude",
            "l1:event.activity_occurrence",
            "l1:event.objective_achieved",
            "l1:polarity.indeterminate",
            "l1:state.capability",
            "l1:state.ongoing_pursuit",
            "l1:task.declared_intention",
            "l1:time.before_assertion",
        ),
        "ran a 5K last year in 45 minutes, intends to start a base building phase, and is unsure "
        "how to pace himself",
        note="the 45-minute time is a magnitude and evidences a v3 capability; the completed run "
        "is both an occurrence and an achievement, and the uncertainty about pacing has no item",
    ),
    _concept(
        "fx-000108",
        (
            "l1:event.information_request",
            "l1:modality.desired",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:preference.threshold",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
        ),
        "intends to buy a baby gym, requires it to be high quality and safe, and asks for durable "
        "safe brands",
        note="quality and safety are a threshold on an ordered attribute; the presence of a baby "
        "is presupposed and would be memory-worthy, but the ontology has no item for it and the "
        "turn never asserts it",
    ),
    _concept(
        "fx-000109",
        (
            "l1:attribute.kind",
            "l1:event.information_request",
            "l1:modality.desired",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:preference.affinity",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
        ),
        "wants a light grey or beige throw pillow with wooden or metal accents to match the colour "
        "scheme planned for a future sectional sofa, and asks for brands",
        note="colour and material are kinds rather than magnitudes; the future sofa is a plan the "
        "ontology holds only as a declared intention",
    ),
    _nothing(
        "fx-000110",
        "the assistant opening a survey and posing its first question about recommending Netflix; "
        "meta-talk with no user content",
        note="an assistant turn like fx-000105. Nothing is attested, so assistant_asserted has "
        "nothing to qualify",
    ),
    _concept(
        "fx-000111",
        (
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:state.possession",
            "l1:task.outstanding_requirement",
        ),
        "has Instagram, Twitter and LinkedIn profiles that still need updating, and asks for "
        "platform-specific tips",
        note="the profiles are things at his disposal and the updating is outstanding work; a "
        "reviewer may find possession of a social profile too thin",
    ),
    _concept(
        "fx-000112",
        (
            "l1:attribute.affiliation",
            "l1:event.information_request",
            "l1:modality.desired",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:state.possession",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
        ),
        "wants a new coffee maker, holds accumulated loyalty points at BedBath&Beyond and intends "
        "to spend them, and asks for suggestions",
        note="the points are a possession with a named counterparty, which is why affiliation is "
        "included; a reviewer may prefer to read the store only as a designation",
    ),
    _concept(
        "fx-000113",
        (
            "l1:attribute.affiliation",
            "l1:attribute.designation",
            "l1:attribute.magnitude",
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:state.capability",
            "l1:state.ongoing_pursuit",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
        ),
        "plays for a named volleyball team currently at 5-2, feels athletically capable, intends "
        "to enter a triathlon in the fall, and asks how to train",
        note="a team membership is an affiliation, the record is a magnitude, volleyball is the "
        "pursuit and the athletic self-assessment is a v3 capability. The confidence itself is "
        "affective and unrepresentable",
    ),
    _concept(
        "fx-000114",
        (
            "l1:event.information_request",
            "l1:modality.question",
            "l1:polarity.denied",
            "l1:predicate.seek_information",
            "l1:preference.threshold",
            "l1:state.capability",
            "l1:state.ongoing_pursuit",
            "l1:time.before_assertion",
        ),
        "wants to try a Korean chicken stew recipe, has never cooked with gochujang, is concerned "
        "about spiciness and asks how spicy the recommended amount will be",
        note="the never-having-cooked-with-gochujang is a denied v3 capability; the spice concern "
        "is a threshold on an ordered attribute",
    ),
    _concept(
        "fx-000115",
        (
            "l1:attribute.calendar_position",
            "l1:state.possession",
            "l1:task.declared_intention",
            "l1:task.outstanding_requirement",
            "l1:time.after_assertion",
            "l2:abstraction.task",
        ),
        "will try on both boots at a local outdoor gear store this weekend, and must take his "
        "brown leather dress shoes to the cobbler on Saturday to be polished and conditioned",
        note="an explicit reminder-to-self with a named day, which is the cleanest L2 task in the "
        "set; two intentions on two occasions, both dated",
    ),
    _concept(
        "fx-000116",
        (
            "l1:attribute.designation",
            "l1:event.information_request",
            "l1:event.media_consumption",
            "l1:modality.question",
            "l1:predicate.consume_media",
            "l1:preference.affinity",
            "l1:strength.strong",
            "l1:time.before_assertion",
        ),
        "recently listened to Ready Player One as an audiobook and loved it, and asks about the "
        "premise and reading order of Jasper Fforde's Thursday Next series",
        note="both the consumption event and the resulting strong affinity are attested, and the "
        "audiobook format is part of the designation of what was consumed",
    ),
    _concept(
        "fx-000117",
        (
            "l1:attribute.designation",
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:preference.affinity",
            "l1:state.pending_arrangement",
            "l1:task.conditional_intention",
            "l1:time.after_assertion",
        ),
        "has a trip arranged, will visit the Yokohama Oktoberfest and Autumn Leaves Festival if "
        "they fall within it, loves trying different beers and autumn foliage, and asks about the "
        "Minato Mirai 21 illuminations",
        note="the clearest conditional intention in the set, since the trigger ('if they're "
        "happening during my trip') is explicit and unsettled",
    ),
    _concept(
        "fx-000118",
        (
            "l1:attribute.designation",
            "l1:event.activity_occurrence",
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:state.ongoing_pursuit",
            "l1:state.possession",
            "l1:strength.paramount",
            "l1:time.before_assertion",
            "l2:abstraction.pursuit_profile",
        ),
        "collects vintage watches and other collectibles, favours a 1960s Omega Seamaster, "
        "acquired a rare blue Snaggletooth figure from a thrift store a few weeks ago, and asks "
        "for display cases",
        note="collecting as a v3 pursuit with two independent supports (the watches and the "
        "figure), which is what makes the v3 L2 pursuit_profile defensible here",
    ),
    _concept(
        "fx-000119",
        (
            "l1:event.information_request",
            "l1:modality.believed",
            "l1:modality.question",
            "l1:polarity.indeterminate",
            "l1:predicate.seek_information",
            "l1:preference.threshold",
        ),
        "wants an easily digestible protein powder that tastes good, has heard whey is popular but "
        "is unsure it suits him, and asks for beginner-friendly whey powders",
        note="digestibility and taste are thresholds on the sought item; the uncertainty about "
        "suitability is indeterminate polarity rather than a denied capability",
    ),
)

_BATCH_120_159: tuple[AnnotationRecord, ...] = (
    _concept(
        "fx-000120",
        (
            "l1:attribute.calendar_position",
            "l1:frequency.habitual",
            "l1:modality.desired",
            "l1:modality.question",
            "l1:preference.avoidance",
            "l1:state.ongoing_pursuit",
            "l1:state.pending_arrangement",
            "l1:strength.tolerant",
            "l1:time.recurring",
            "l2:abstraction.habit",
        ),
        "goes to the gym on Mondays, Wednesdays and Fridays, is otherwise flexible, wants the "
        "meeting kept off those days and proposes Tuesday or Thursday",
        note="modality.question without information_request: the closing 'how about' proposes a "
        "slot rather than asking for information, and treating every question mark as a request "
        "would make the request items unfalsifiable. The named days plus 'usually' are an explicit "
        "recurrence, so the L2 habit stands even though m:abstraction.habit's sources are "
        "media-flavoured -- a mismatch between the item's general sense and its v2 derivation "
        "worth recording",
    ),
    _concept(
        "fx-000121",
        (
            "l1:attribute.place",
            "l1:event.activity_occurrence",
            "l1:event.information_request",
            "l1:frequency.occasional",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:source_status.user_reported",
            "l1:time.before_assertion",
            "l2:abstraction.relationship",
        ),
        "helps his niece practise the violin whenever he can, reports she was given a "
        "student-level violin from a Pasadena shop about a month ago, and asks how to keep her "
        "engaged",
        note="the tie is named ('my niece') so abstraction.relationship is admitted, but no "
        "l2:relation.* kind fits: a niece is collateral descent, and the unit offers only "
        "kin_descent (asymmetric direct) and kin_lateral (same generation). The violin is the "
        "niece's possession, so no state.possession label -- the bearer would be wrong",
    ),
    _concept(
        "fx-000122",
        (
            "l1:attribute.designation",
            "l1:event.information_request",
            "l1:event.media_consumption",
            "l1:frequency.habitual",
            "l1:modality.question",
            "l1:predicate.consume_media",
            "l1:predicate.seek_information",
            "l1:preference.affinity",
            "l1:preference.threshold",
            "l1:state.ongoing_pursuit",
            "l1:strength.strong",
            "l1:task.declared_intention",
            "l1:time.at_assertion",
        ),
        "will check out the suggested playlists, has been listening to a named Billie Eilish album "
        "on Spotify and loves the track 'NDA', and asks for similar songs with a catchy beat and "
        "distinctive vocals",
        note="the densest label in this batch. 'a catchy beat and unique vocal style' is a "
        "threshold on what is sought, not merely an affinity; the album and track names are "
        "designations. Flagged for the pursuit reading of sustained listening",
    ),
    _concept(
        "fx-000123",
        (
            "l1:attribute.designation",
            "l1:source_status.user_reported",
            "l1:state.possession",
            "l1:time.at_assertion",
            "l2:abstraction.relationship",
            "l2:relation.kin_descent",
        ),
        "reports her mother now uses the same grocery list app, so the two can share lists, and "
        "closes by thanking the assistant for the fajita advice",
        note="the sharing arrangement is the attestation and the kin tie is explicit, so both the "
        "L2 relationship and the descent kind hold from one turn. The trailing thanks is "
        "backchannel inside a turn that still carries content, which is why this is not none",
    ),
    _concept(
        "fx-000124",
        (
            "l1:event.attempt_failed",
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:time.before_assertion",
        ),
        "has been taking over-the-counter medication that is not working as well as hoped, and asks "
        "how expectorants work",
        note="the ineffectiveness is an attempt that did not achieve its aim; the underlying "
        "illness is the health gap seen at fx-000066 and is not labelled here",
    ),
    _concept(
        "fx-000125",
        (
            "l1:attribute.affiliation",
            "l1:attribute.designation",
            "l1:event.information_request",
            "l1:modality.believed",
            "l1:modality.question",
            "l1:predicate.hold_belief",
            "l1:predicate.seek_information",
            "l1:state.ongoing_pursuit",
            "l1:time.at_assertion",
        ),
        "belongs to a named Facebook group where she has been active, holds that its members would "
        "enjoy 'Gone Girl' as a book club pick, and asks for discussion questions",
        note="membership of a named group is an affiliation; the judgement about what the members "
        "would enjoy is a belief about third parties rather than her own preference",
    ),
    _concept(
        "fx-000126",
        (
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.rank_alternatives",
            "l1:predicate.seek_information",
            "l1:task.outstanding_requirement",
            "l1:time.at_assertion",
        ),
        "has work tasks outstanding and asks for help ordering them by urgency and importance",
        note="rank_alternatives is what is requested rather than already held, which is the reason "
        "for the flag; the feeling of being overwhelmed is the affective_state gap",
    ),
    _concept(
        "fx-000127",
        (
            "l1:modality.desired",
            "l1:preference.affinity",
            "l1:state.occupation_status",
            "l1:state.ongoing_pursuit",
            "l1:strength.tolerant",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
            "l1:time.spanning",
            "l2:abstraction.project",
            "l2:abstraction.pursuit_profile",
        ),
        "has worked in marketing for five years, wants a master's degree to stay competitive, aims "
        "at a leadership role, and is open to full-time or part-time and to online or on-campus "
        "study",
        note="two L2 items on one turn: the degree and the leadership goal are one aim with "
        "separately outstanding steps, and the five-year occupation plus the continuing "
        "professional development satisfy the v3 pursuit_profile's two-source requirement. "
        "'open to either' is tolerant strength, not a comparative preference",
    ),
    _concept(
        "fx-000128",
        (
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:state.pending_arrangement",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
        ),
        "will send the email with the file link and a note, and asks whether to confirm the "
        "meeting's time and date in it",
    ),
    _concept(
        "fx-000129",
        (
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:state.possession",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
        ),
        "plans desserts for a dinner party and asks for recipes needing no stand mixer, ideally "
        "using a newly acquired coffee maker or other appliances already owned",
        note="the absent stand mixer is what shapes the request. capability_constraint would be "
        "wrong -- not owning a tool is a missing possession, not an impaired capability of the "
        "subject -- and the distinction is worth a reviewer's eye",
    ),
    _concept(
        "fx-000130",
        (
            "l1:attribute.designation",
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:preference.affinity",
        ),
        "is particularly interested in Todoist and Trello and asks how they integrate with Google "
        "Calendar",
        note="'particularly interested in' narrows two named options out of a prior list, which "
        "brushes against preference.comparative; nothing ranks the two against each other, so only "
        "the affinity is labelled",
    ),
    _nothing(
        "fx-000131",
        "asks which digital marketing certifications are well regarded; a bare information request "
        "attesting nothing about the asker",
        note="borderline against fx-000127, where the same topic came with a stated career goal. "
        "Here the turn alone carries no affinity or pursuit, and inferring one from the topic is "
        "the error this label refuses",
    ),
    _concept(
        "fx-000132",
        (
            "l1:attribute.magnitude",
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:preference.threshold",
            "l1:state.possession",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
        ),
        "owns a car returning about 28 miles per gallon in the city, intends to buy an air filter, "
        "and asks for recommendations that help fuel efficiency",
        note="the measured consumption is a magnitude attribute of the car and the efficiency "
        "requirement is a threshold on the filter, so the two ids attach to different bearers",
    ),
    _concept(
        "fx-000133",
        (
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:source_status.user_reported",
            "l1:state.possession",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
            "l2:abstraction.relationship",
            "l2:relation.kin_lateral",
        ),
        "has a rose tea her sister introduced her to, means to try it, and asks whether shortbread "
        "would pair with it",
        note="a sister is a same-generation kin tie, so kin_lateral is the right kind; the "
        "introduction is what places her in the frame rather than a dated first encounter",
    ),
    _concept(
        "fx-000134",
        (
            "l1:event.commitment_withdrawn",
            "l1:frequency.habitual",
            "l1:predicate.change_arrangement",
            "l1:state.capability_constraint",
            "l1:state.ongoing_pursuit",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
            "l2:abstraction.pursuit_profile",
        ),
        "will scale back running the league and look for a co-organiser to limit his "
        "responsibility, and will schedule his basketball games around triathlon training",
        note="a partial withdrawal: commitment_withdrawn is the nearest item but the commitment is "
        "reduced rather than dropped, and nothing in v2 or v3 grades that. Two sports plus training "
        "support the v3 pursuit_profile",
    ),
    _concept(
        "fx-000135",
        (
            "l1:attribute.designation",
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.relocate",
            "l1:predicate.seek_information",
            "l1:source_status.user_reported",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
            "l1:time.before_assertion",
            "l2:abstraction.relationship",
            "l2:relation.friendship",
        ),
        "is thinking of visiting her friend Rachel, who recently moved to a city apartment, and "
        "asks about the weather there at this time of year",
        note="the relocation is Rachel's, so predicate.relocate is attested with a third-party "
        "bearer -- admissible because the tie itself is the memory-worthy content. 'thinking of' is "
        "weaker than a declared intention but v2 offers no intermediate item between that and "
        "modality.desired",
    ),
    _nothing(
        "fx-000136",
        "asks for portable healthy snacks for afternoon energy dips; the craving is generic framing "
        "rather than a stated pattern of the asker",
        note="a reviewer could read 'those afternoon cravings when I need a boost' as a habitual "
        "recurrence. It is labelled none because the phrasing is a generic appeal rather than a "
        "report of the speaker's own schedule, and this is the thinnest none in the batch",
    ),
    _concept(
        "fx-000137",
        (
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:predicate.suspend_on_condition",
            "l1:state.possession",
            "l1:task.conditional_intention",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
            "l2:abstraction.conditional_commitment",
        ),
        "will make a house offer contingent on the inspection and attach his pre-approval letter, "
        "and asks what mistakes buyers make when offering",
        note="the clearest conditional commitment in the whole set: an explicit contingency whose "
        "trigger is unresolved at the end of the turn, which is exactly what "
        "m:abstraction.conditional_commitment requires",
    ),
    _concept(
        "fx-000138",
        (
            "l1:attribute.designation",
            "l1:event.activity_occurrence",
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.hold_value",
            "l1:predicate.seek_information",
            "l1:preference.affinity",
            "l1:time.before_assertion",
        ),
        "asks for an overview of adhesives and consolidants in art conservation, and reports being "
        "struck during a behind-the-scenes tour of a named museum's conservation lab by the "
        "dedication cultural preservation demands",
        note="hold_value is defensible because heritage preservation is endorsed as worth that "
        "dedication, not merely described; the surprise itself is the affective_state gap",
    ),
    _concept(
        "fx-000139",
        (
            "l1:attribute.designation",
            "l1:event.activity_occurrence",
            "l1:preference.threshold",
            "l1:role.beneficiary",
            "l1:state.possession",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
            "l1:time.before_assertion",
        ),
        "saw jewellery pieces at a named market that caught her eye but was unsure they suited her "
        "sister, and now means to return and find one to match the phone case",
        note="the second place a role id is named: the sister is the beneficiary the whole "
        "selection is for, so the slot is the attestation rather than incidental. The earlier "
        "uncertainty is a resolved epistemic gap and is not labelled",
    ),
    _concept(
        "fx-000140",
        (
            "l1:attribute.place",
            "l1:event.information_request",
            "l1:event.life_transition",
            "l1:modality.question",
            "l1:predicate.reside_at",
            "l1:predicate.seek_information",
            "l1:preference.affinity",
            "l1:state.residence",
            "l1:time.at_assertion",
            "l1:time.spanning",
        ),
        "has lived in a new studio flat in Harajuku, Tokyo for a month, is still adjusting but "
        "enjoys the independence and the convenient commute, and asks whether to book "
        "accommodation in Hakuba Valley or Matsumoto",
        note="the residence is dated and placed, so both the state and the transition hold. 'still "
        "getting used to' is an adjustment in progress that no item names; the closing choice is a "
        "request for a recommendation, not a preference the speaker already holds",
    ),
    _concept(
        "fx-000141",
        (
            "l1:attribute.kind",
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:preference.affinity",
            "l1:preference.threshold",
        ),
        "likes velvet pillows in rich hues and asks for more options in mustard or teal",
        note="the two named colours are a threshold on what is sought rather than a ranking, so "
        "preference.comparative is withheld",
    ),
    _concept(
        "fx-000142",
        (
            "l1:attribute.affiliation",
            "l1:attribute.designation",
            "l1:event.first_encounter",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
            "l1:time.before_assertion",
            "l2:abstraction.relationship",
            "l2:relation.friendship",
        ),
        "will add his friend David to the spreadsheet, having met him at the same WeWork startup "
        "mixer, where David introduced him to colleagues of his at Google",
        note="a named non-kin tie with a dated first encounter, which is the textbook case for "
        "m:relation.friendship. David's Google colleagues are third parties whose affiliation is "
        "attested but who are not themselves tied to the speaker",
    ),
    _concept(
        "fx-000143",
        (
            "l1:event.information_request",
            "l1:modality.desired",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:role.quantity",
            "l1:state.possession",
            "l1:time.at_assertion",
        ),
        "has a stash of seventeen skeins of worsted weight yarn found recently, wants to use them "
        "up, and asks whether they suit amigurumi toys",
        note="the third and last role id in the gold: the count of seventeen skeins is the "
        "attestation, matching how role.quantity was used for the poem count at fx-000056",
    ),
    _concept(
        "fx-000144",
        (
            "l1:event.attempt_failed",
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:state.ongoing_pursuit",
            "l1:time.at_assertion",
        ),
        "is still trying to work out how to pack clothes strategically and asks how to decide what "
        "to take and how many outfits to build from it",
        note="'still trying to figure out' is an unsuccessful continuing attempt, so both the "
        "pursuit and the failed attempt are defensible; a reviewer may find attempt_failed too "
        "strong for an unfinished effort",
    ),
    _concept(
        "fx-000145",
        (
            "l1:attribute.place",
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:preference.comparative",
            "l1:state.pending_arrangement",
            "l1:time.after_assertion",
        ),
        "is considering camping rather than a hotel for a planned trip and asks for campsites near "
        "Mount Rushmore",
        note="'camping instead of a hotel' ranks two named alternatives, which is what separates "
        "comparative from a bare affinity. The plural 'we' implies a companion no item holds",
    ),
    _nothing(
        "fx-000146",
        "asks the assistant what fashion items it splurges on; meta-talk about the addressee that "
        "attests nothing about the speaker",
        note="the Gucci handbag is presupposed of the assistant, not of the speaker, so a "
        "possession label would attach to a party the memory does not model. Contrast fx-000155, "
        "where the speaker answers the same question about herself",
    ),
    _concept(
        "fx-000147",
        (
            "l1:attribute.magnitude",
            "l1:attribute.place",
            "l1:event.commitment_made",
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:preference.threshold",
            "l1:state.pending_arrangement",
            "l1:time.after_assertion",
            "l1:time.before_assertion",
        ),
        "is planning a Maui trip, has already booked a resort there costing over $300 a night, and "
        "asks for free or affordable outdoor activities and hiking trails to offset it",
        note="the completed booking is a commitment already made while the trip itself is still "
        "pending, so the two time qualifiers are both attested and attach to different frames; the "
        "cost ceiling on activities is a threshold",
    ),
    _concept(
        "fx-000148",
        (
            "l1:attribute.designation",
            "l1:event.activity_occurrence",
            "l1:frequency.habitual",
            "l1:source_status.confirmed_by_both",
            "l1:state.ongoing_pursuit",
            "l1:time.recurring",
            "l2:abstraction.habit",
            "l2:abstraction.pursuit_profile",
            "l2:pattern.recurrence_count",
        ),
        "attends a language exchange class at a local school every Wednesday evening with a "
        "Colombian tutor named Juan, who helps with her Spanish pronunciation and grammar while she "
        "helps with his English vocabulary, and she confirms the Wednesday slot on recall",
        note="the only turn in the gold carrying three L2 items: an explicit weekly recurrence "
        "(habit and recurrence_count) plus a sustained study practice with two independent supports "
        "(pursuit_profile). The reciprocal arrangement makes the schedule mutually established "
        "rather than merely user-reported, which is why confirmed_by_both is named here",
    ),
    _concept(
        "fx-000149",
        (
            "l1:attribute.designation",
            "l1:attribute.place",
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:preference.affinity",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
            "l2:abstraction.project",
        ),
        "likes the Lakers trivia idea for an event around LA Live, plans a photo challenge at a "
        "Lakers-themed mural, and asks whether that works and where such murals are near the "
        "Staples Center",
        note="event design with several separately outstanding steps is an L2 project; the "
        "affinity is towards a proposal made by the assistant rather than a standing taste, which "
        "is the reading a reviewer should check",
    ),
    _nothing(
        "fx-000150",
        "asks the assistant's opinion on using an abrasive-sided microfiber cloth on a car's centre "
        "console; a technique question attesting nothing about the asker",
        note="the console implies car ownership, already attested at fx-000132, but nothing in "
        "this turn states it. Labelling possession here would credit a mapper for an inference "
        "across turns that a single-expression mapping cannot make",
    ),
    _concept(
        "fx-000151",
        (
            "l1:attribute.place",
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:preference.affinity",
        ),
        "wants to learn about the LA street art scene and asks for its history and how it has "
        "evolved",
        note="deliberately parallel to fx-000083, where the same topic came with a pursuit; here "
        "only topical interest is stated, so no pursuit label",
    ),
    _concept(
        "fx-000152",
        (
            "l1:attribute.calendar_position",
            "l1:attribute.designation",
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.occupy_role",
            "l1:predicate.seek_information",
            "l1:time.at_assertion",
            "l1:time.before_assertion",
        ),
        "is reviewing for ACL, whose submission date was 1 February, and asks for tips on reviewing "
        "for conferences of that kind",
        note="reviewing for a named conference is an occupied role rather than an occupation "
        "status; the past submission date is attested as a fact about the venue, not about the "
        "speaker's own timeline",
    ),
    _concept(
        "fx-000153",
        (
            "l1:attribute.affiliation",
            "l1:attribute.designation",
            "l1:attribute.place",
            "l1:event.information_request",
            "l1:frequency.occasional",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:state.pending_arrangement",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
            "l1:time.before_assertion",
            "l2:abstraction.relationship",
            "l2:pattern.recurrence_count",
            "l2:relation.friendship",
        ),
        "plans to meet his friend Alex from Germany in Berlin, having met up with him twice before, "
        "and asks for cafes or bars in Kreuzberg",
        note="'twice before' is an explicit tally of distinct occasions, which is what "
        "m:import.pattern_recurrence_count counts; two meetings is below the three "
        "m:abstraction.habit requires, so recurrence_count is named without habit -- the pair of "
        "labels here and at fx-000148 is what makes that threshold checkable",
    ),
    _nothing(
        "fx-000154",
        "asks which song on an album best shows the band's artistic growth and how it compares with "
        "their earlier work; a critical question about third-party work",
        note="the detailed comparison axes could read as topical affinity. It is none because the "
        "turn asks for the assistant's judgement and never places the speaker in the frame",
    ),
    _concept(
        "fx-000155",
        (
            "l1:frequency.occasional",
            "l1:modality.believed",
            "l1:predicate.hold_belief",
            "l1:predicate.transfer_value",
            "l1:preference.affinity",
            "l1:preference.comparative",
            "l1:state.ongoing_pursuit",
            "l1:strength.strong",
            "l1:time.at_assertion",
            "l2:abstraction.preference_profile",
        ),
        "tends to spend heavily on high-end handbags and shoes and occasionally on luxury clothing "
        "such as evening gowns, has been justifying it to herself as investment buying, and "
        "believes it is really an emotional response to an occasion or mood",
        note="accessories are ranked above occasional clothing purchases, and two graded affinities "
        "in one area is exactly m:abstraction.preference_profile's requirement. The "
        "self-diagnosis is a belief about her own motives -- self-narrative content the ontology "
        "holds only as a belief, which is the residual thinness here",
    ),
    _concept(
        "fx-000156",
        (
            "l1:attribute.designation",
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:state.circumstance",
            "l1:time.at_assertion",
        ),
        "is overwhelmed by the material on nasal saline irrigation, asks for a summary, and asks "
        "whether to discuss her sinusitis diagnosis and treatment plan with a named doctor",
        note="a named diagnosis held as state.circumstance is the compromise fx-000066 was flagged "
        "for: the item holds it but cannot say it is medical, so a question about the speaker's "
        "health cannot be answered from the label. The overwhelmed feeling is the affective_state "
        "gap and the doctor is a third party with no tie item",
    ),
    _concept(
        "fx-000157",
        (
            "l1:event.attempt_failed",
            "l1:event.information_request",
            "l1:modality.question",
            "l1:polarity.denied",
            "l1:predicate.seek_information",
            "l1:preference.affinity",
            "l1:state.ongoing_pursuit",
            "l1:task.declared_intention",
            "l1:time.before_assertion",
        ),
        "has been meaning to read more thrillers, has heard of some of the recommended authors but "
        "has not yet read them, and asks whether any would suit a book club",
        note="'haven't gotten around to it' is an intention standing unfulfilled: the denied "
        "polarity is on the reading, not on the intention. attempt_failed is the nearest item for a "
        "lapsed intention, and a reviewer may prefer to drop it and keep only the intention",
    ),
    _concept(
        "fx-000158",
        (
            "l1:attribute.designation",
            "l1:attribute.magnitude",
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:preference.comparative",
            "l1:preference.threshold",
            "l1:state.ongoing_pursuit",
            "l1:state.possession",
            "l1:time.at_assertion",
        ),
        "asks how heavy and bulky some hiking boots are, being concerned about foot weight, and "
        "notes that his old named Converse sneakers are very light",
        note="the sneakers are an explicit comparison standard, so both comparative and threshold "
        "hold; l1:role.comparison_target is the slot that carries them and is omitted under the "
        "no-roles convention. The concern itself is affective and unlabelled",
    ),
    _concept(
        "fx-000159",
        (
            "l1:attribute.designation",
            "l1:attribute.place",
            "l1:event.activity_occurrence",
            "l1:event.information_request",
            "l1:modality.question",
            "l1:predicate.seek_information",
            "l1:preference.affinity",
            "l1:strength.strong",
            "l1:time.before_assertion",
            "l2:pattern.recurrence_count",
        ),
        "rode a named rollercoaster three times in a row at Universal Studios Hollywood on 15 "
        "October and found it thrilling, and asks whether the assistant has ridden an "
        "Egyptian-tomb-themed rollercoaster",
        note="three rides in one sitting is one occasion, not three: recurrence_count is named "
        "because the tally is stated, but no habit follows, since m:abstraction.habit counts "
        "distinct occasions. The thrill is affective and rests on preference.affinity alone",
    ),
)

_RECORDS: tuple[AnnotationRecord, ...] = (
    _BATCH_000_039 + _BATCH_040_079 + _BATCH_080_119 + _BATCH_120_159
)


def build_annotation_gold() -> AnnotationGold:
    """Assemble the gold, sorted by expression id so the digest is order-independent."""
    return AnnotationGold(
        annotated_set_sha256=ANNOTATED_SET_SHA256,
        annotated_against_ontology=ANNOTATED_AGAINST_ONTOLOGY,
        records=tuple(sorted(_RECORDS, key=lambda record: record.expression_id)),
    )
