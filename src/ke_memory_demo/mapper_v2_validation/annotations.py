"""The 120 labels, decided by reading each expression against frozen ontology v2.

No mapper was consulted, no model was called and no judge was invoked. Every label is a
judgement about what a *correct* mapper should return, which is deliberately not the same
question as what a mapper can find.

Two policies were applied uniformly, and both were chosen before labelling rather than to fit
the results:

1. A first-person stated intention is memory-worthy even when it is thin ("I'll try the
   modified routine"). A bare question with no self-disclosure is not, however answerable it is
   -- it is meta-conversation with the assistant, and storing it would inflate coverage with
   content no future turn could use.
2. ``out_of_scope`` is reserved for expressions whose *principal* assertion has no type in v2.
   Where the main clause is untyped but a second, independent proposition is fully typed, the
   record is a ``concept`` and the gap is recorded in its note. Labelling those out of scope
   would overstate the ceiling as badly as forcing a weak concept understates it.

The recurring gaps the labelling exposed are named in :data:`GAP_CATEGORIES`, so the breadth
review has a concrete list rather than a count.
"""

from __future__ import annotations

from typing import Final

from .models import AnnotationGold, AnnotationRecord, Outcome

# The sample digest these labels were produced against, as recorded inside the frozen sample.
# Hard-coded rather than recomputed at build time on purpose: if the sample is ever re-drawn,
# this gold must fail to bind rather than silently re-point at a different 120 expressions.
ANNOTATED_SAMPLE_SHA256: Final[str] = (
    "2a0a6813305c7a97b00ab321337dae46c7b9eb2f96d93112a5af9327ede31e33"
)

# What the out_of_scope labels have in common. Each key is cited by at least one gap record and
# several also bite as precision loss inside concept records, which is noted where it applies.
GAP_CATEGORIES: Final[dict[str, str]] = {
    "generic_activity_or_pursuit": (
        "v2 types media consumption, relocation, commitment, life transition and objective "
        "completion, but has no event or state type for an ordinary activity, hobby or creative "
        "practice: recording a podcast, hosting a party, attending a retreat, a beach outing. "
        "Would require an activity event type with a participation role, plus a pursuit state "
        "type for the ongoing-practice reading"
    ),
    "held_value_or_general_belief": (
        "a subject's priority ordering ('safety is super important to me') and their general "
        "causal beliefs about the world ('self-care makes you strong for tough times') are both "
        "memory-worthy and both untyped. attribute.assessment rates an entity's quality, which "
        "is a different claim, and modality.believed qualifies an assertion without giving the "
        "belief a subject-held type"
    ),
    "episodic_experience_and_object_significance": (
        "a specific remembered occasion and the personal meaning attached to a place or a "
        "possession: a sunset watched with someone who has died, a tattoo standing for freedom, "
        "lucky shoes where every mark has a story. state.possession records that the object is "
        "held and nothing about what it means; no type carries an occasion as an experience"
    ),
    "fictional_or_role_play_frame": (
        "role-play turns where the speaker voices a character. The propositions are real text "
        "but false of the subject, and the source_status vocabulary has no value for in-fiction "
        "content, so a mapper that extracts them pollutes memory with a persona's facts"
    ),
    "positive_capability_or_skill": (
        "state.capability_constraint types what a subject cannot do; nothing types what they "
        "can. Skill level, competence and quantified progress ('completed 4 projects since "
        "starting classes', 'my skills are making a difference') have no home"
    ),
}


def _concept(
    expression_id: str,
    targets: tuple[str, ...],
    sense: str,
    *,
    note: str = "",
) -> AnnotationRecord:
    return AnnotationRecord(
        expression_id=expression_id,
        outcome=Outcome.CONCEPT,
        target_ids=tuple(sorted(targets)),
        sense=sense,
        needs_second_opinion=bool(note),
        adjudication_note=note,
    )


def _ambiguous(
    expression_id: str, targets: tuple[str, ...], sense: str, note: str
) -> AnnotationRecord:
    return AnnotationRecord(
        expression_id=expression_id,
        outcome=Outcome.AMBIGUOUS,
        target_ids=tuple(sorted(targets)),
        sense=sense,
        needs_second_opinion=True,
        adjudication_note=note,
    )


def _none(expression_id: str, sense: str, *, note: str = "") -> AnnotationRecord:
    return AnnotationRecord(
        expression_id=expression_id,
        outcome=Outcome.NONE,
        sense=sense,
        needs_second_opinion=bool(note),
        adjudication_note=note,
    )


def _gap(expression_id: str, sense: str, would_require: str, note: str) -> AnnotationRecord:
    return AnnotationRecord(
        expression_id=expression_id,
        outcome=Outcome.OUT_OF_SCOPE,
        sense=sense,
        would_require=would_require,
        needs_second_opinion=True,
        adjudication_note=note,
    )


_RECORDS: Final[tuple[AnnotationRecord, ...]] = (
    _concept(
        "expr-000000",
        ("l1:state.occupation_status", "l1:task.declared_intention", "l1:time.after_assertion"),
        "opening a dance studio that will welcome dancers of all ages, stated as a future aim",
        note="the thanks and the anticipation are pleasantry; the intention plus the studio-owner "
        "occupation is the only durable content, so a mapper returning none is not obviously wrong",
    ),
    _ambiguous(
        "expr-000001",
        ("l1:attribute.assessment", "l1:preference.affinity"),
        "animals are amazing and make incredible companions",
        "read as a standing liking of animals or as an evaluative judgement about them; the text "
        "gives no way to choose, and the two are different item types rather than co-attested",
    ),
    _none(
        "expr-000002",
        "agreement plus a generic sentiment about sharing and bonds; no proposition about anyone",
    ),
    _gap(
        "expr-000003",
        "recorded a podcast with friends yesterday discussing the rap industry",
        "an activity event type for a creative or social pursuit, with a participation role and a "
        "topic role; friendship is separately attested and typed",
        "the friendship tie and the past time are expressible, but the principal assertion is the "
        "podcast recording, and no v2 event type covers producing a creative work",
    ),
    _concept(
        "expr-000004",
        (
            "l1:event.attempt_failed",
            "l1:preference.affinity",
            "l1:state.possession",
            "l1:task.declared_intention",
        ),
        "intends to cook with roasted sweet potato and caramelised onions, likes that flavour, "
        "has a sweet potato in the pantry, and has previously failed to caramelise onions quickly",
    ),
    _none("expr-000005", "enthusiasm and anticipation addressed to the other party; no content"),
    _concept(
        "expr-000006",
        ("l1:predicate.relocate", "l1:role.source_location", "l1:role.target_location"),
        "wants to travel from Frankfurt to Speyer, so a movement with both endpoints",
    ),
    _concept(
        "expr-000007",
        (
            "l1:event.attempt_failed",
            "l1:event.objective_achieved",
            "l1:time.before_assertion",
        ),
        "got stuck on a plot twist last week, kept pushing and got the ideas flowing again",
    ),
    _gap(
        "expr-000008",
        "a tattoo got years ago that stands for freedom and reminds the subject to follow their "
        "passions",
        "a significance or symbolic-meaning relation from a possession to what it represents, and "
        "a held-value type for the commitment it reminds them of",
        "state.possession types that the tattoo is held and drops everything the turn is actually "
        "about; forcing attribute.designation would misread meaning as a way of referring to it",
    ),
    _concept(
        "expr-000009",
        (
            "l1:preference.threshold",
            "l1:predicate.transfer_value",
            "l1:task.declared_intention",
            "l1:time.before_assertion",
        ),
        "recently bought luxury boots, is budget-conscious, and intends to find similar boots "
        "at a lower price",
    ),
    _gap(
        "expr-000010",
        "cherishes a specific remembered sunset watched in silence with someone now gone, and "
        "feels peace and gratitude on every return to that spot",
        "an episodic-experience type that can hold one remembered occasion, and a place-"
        "significance relation; the recurring feeling on return needs an affective state type",
        "state.circumstance would take the feeling as a bare condition and time.recurring the "
        "revisits, but the occasion itself -- the thing being remembered -- has no type at all",
    ),
    _gap(
        "expr-000011",
        "safety is very important to the subject, and they bought something protective that "
        "looks funny but works",
        "a held-value or priority type; attribute.assessment rates how good an entity is, which "
        "is a different claim from what a subject treats as important",
        "closest existing item is attribute.assessment, and it is the wrong one: the turn ranks a "
        "concern, it does not evaluate a thing. The purchase is typed but is not the main claim",
    ),
    _concept(
        "expr-000012",
        ("l1:attribute.assessment", "l1:preference.affinity", "l1:state.circumstance"),
        "loves sharing their coding journey publicly and tracking it, and judges the experience "
        "awesome and challenging",
    ),
    _concept(
        "expr-000013",
        ("l1:predicate.consume_media", "l1:state.circumstance", "l1:time.spanning"),
        "reading a recommended book and painting to keep busy through a hard time",
        note="painting-to-keep-busy is the generic-pursuit gap; the book reading is squarely "
        "consume_media, so the record is a concept with precision loss on the second clause",
    ),
    _none("expr-000014", "thanks and an expression of appreciation for support; no content"),
    _concept(
        "expr-000015",
        (
            "l1:attribute.availability",
            "l1:preference.affinity",
            "l1:predicate.consume_media",
            "l1:task.declared_intention",
        ),
        "wants to watch Westworld and is unsure whether it is available through a subscription "
        "they already have",
    ),
    _none("expr-000016", "admiring reaction to the other party's enthusiasm; no proposition"),
    _none(
        "expr-000017",
        "resolve not to be brought down, thanks, and a question back to the other party",
        note="'I won't let this bring me down' could be read as a declared intention; it is a "
        "stance about an outcome rather than an action, and no v2 task type fits a stance",
    ),
    _concept(
        "expr-000018",
        ("l1:preference.affinity", "l1:predicate.transfer_value", "l2:relation.kin_descent"),
        "parents gave the subject a video game at age 10, which began a lasting passion for games",
        note="the kin tie to the parents is an L2 relation and the affinity is a durable "
        "preference; flagged because the L2 label is an abstraction over a single past turn",
    ),
    _concept(
        "expr-000019",
        ("l1:preference.avoidance", "l2:abstraction.habit", "l1:state.possession"),
        "carries reusable bags whenever shopping, now settled as a habit, to avoid plastic waste",
        note="an explicit self-reported habit, which is the clearest L2 habit case in the sample; "
        "flagged because it rests on one turn while the L2 item declares minimum_support 3",
    ),
    _ambiguous(
        "expr-000020",
        ("l1:attribute.assessment", "l1:preference.affinity"),
        "judges the recommended work's world and story perfect, and is excited for it",
        "the same affinity-or-assessment split as expr-000001: praise of a work's qualities reads "
        "as either a rating of the work or a taste for that kind of world and story",
    ),
    _gap(
        "expr-000021",
        "built an inventory, resource and donation tracking system that generates reports for a "
        "charity, and feels their skills are making a real difference",
        "a positive-capability or skill type, plus an activity type for building an artefact; v2 "
        "types only what a subject cannot do",
        "state.circumstance could hold the situation coarsely, but the turn is about competence "
        "applied to an artefact, and both halves of that are untyped",
    ),
    _none(
        "expr-000022",
        "two questions to the other party about their purchase; no self-disclosure",
    ),
    _none("expr-000023", "congratulation and a generic question about how a change is going"),
    _none("expr-000024", "reaction to a shared photo and a question about the flowers in it"),
    _gap(
        "expr-000025",
        "role-played NPC dialogue giving directions through coloured pipes, plus a standing "
        "instruction to the assistant to answer in the first person",
        "an in-fiction source status so a mapper can refuse the persona's propositions, and a "
        "meta-instruction type distinct from content about the subject",
        "the directive clause is expressible as modality.directed over a suspended commitment, "
        "but the bulk is a character's speech and v2 has no way to mark it as false of the user",
    ),
    _none("expr-000026", "well-wishing about the other party's trip; pure pleasantry"),
    _concept(
        "expr-000027",
        (
            "l1:preference.affinity",
            "l1:role.quantity",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
        ),
        "plans to host a BBQ and buy an outdoor patio set for a large group that is durable, "
        "comfortable and easy to clean",
    ),
    _none("expr-000028", "questions about the other party's pets and their playmates"),
    _concept(
        "expr-000029",
        (
            "l1:modality.desired",
            "l1:predicate.relocate",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
        ),
        "tour ends soon, heading to Boston, and would like to meet up there; a new professional "
        "collaboration also began after someone noticed the performance",
        note="the collaboration is a professional tie and v2's relation types are only friendship, "
        "kin and partnership, so that clause is precision loss inside an otherwise typed record",
    ),
    _none("expr-000030", "a question asking what got the other party into running"),
    _none("expr-000031", "encouragement and an expression of confidence in the other party"),
    _none("expr-000032", "thanks for support plus a statement of intent to stay positive"),
    _none("expr-000033", "offer to hear the outcome later; conversational closing"),
    _none("expr-000034", "reaction to a picture and a question about the other party's trip"),
    _concept(
        "expr-000035",
        ("l1:state.circumstance", "l1:state.possession", "l1:task.abandoned_intention"),
        "has saved money, is content and has no big plans for it, so it stays as cash on hand",
        note="'I don't have big plans anyway' is the absence of an intention rather than one "
        "given up; abandoned_intention is the nearest type and may be over-reading it",
    ),
    _none("expr-000036", "greeting and admiration for the other party's new studio"),
    _none("expr-000037", "reaction plus a question about how the other party feels"),
    _none("expr-000038", "an offer of further help if needed; conversational"),
    _gap(
        "expr-000039",
        "holds that looking after yourself is what makes you strong for hard times, learned the "
        "hard way through something that happened last year",
        "a held-belief type whose content is a general claim about the world, and an experience "
        "type for the episode it was learned from",
        "modality.believed qualifies an assertion's attitude but does not give the subject a "
        "typed belief; the past episode is referred to without being stated, so nothing anchors it",
    ),
    _none("expr-000040", "sympathy and encouragement about the other party's studio problem"),
    _none("expr-000041", "greeting plus a question about how the other party's practices help"),
    _ambiguous(
        "expr-000042",
        ("l1:task.declared_intention", "l1:task.outstanding_requirement"),
        "will check their schedule and report back before planning something for next month",
        "checking the schedule reads as an intention the subject has formed or as a step that "
        "must happen before the arrangement can proceed; both task types fit the same clause",
    ),
    _concept(
        "expr-000043",
        (
            "l1:attribute.availability",
            "l1:attribute.calendar_position",
            "l1:preference.affinity",
            "l1:role.beneficiary",
        ),
        "likes the idea of a family concert series, wants piano music, and is asking which "
        "upcoming dates would interest children",
    ),
    _concept(
        "expr-000044",
        (
            "l1:attribute.affiliation",
            "l1:attribute.calendar_position",
            "l1:state.circumstance",
            "l1:time.before_assertion",
        ),
        "rejoined their team on the 15th after a trip and feels lucky to belong to it",
        note="team membership is affiliation, but the ties to individual teammates are a "
        "professional or group relation v2's three relation types do not admit",
    ),
    _concept(
        "expr-000045",
        ("l1:state.circumstance", "l1:state.occupation_status", "l1:time.at_assertion"),
        "has been low on confidence lately, which is making running their business hard",
        note="an affective state held coarsely by state.circumstance; the confidence itself is "
        "the subject of the turn and no type carries an emotional condition as such",
    ),
    _concept(
        "expr-000046",
        ("l1:attribute.assessment", "l1:preference.affinity"),
        "loves sports and admires the determination and heart the players showed in that moment",
    ),
    _concept(
        "expr-000047",
        (
            "l1:event.commitment_made",
            "l1:state.pending_arrangement",
            "l1:time.after_assertion",
        ),
        "has just set up meetings with movie producers, so arrangements now stand upcoming",
    ),
    _gap(
        "expr-000048",
        "threw a small party inviting veterans to share their stories, and saw them make "
        "connections and new friendships",
        "an activity event type for hosting a gathering, with a participant-group role; the "
        "friendships formed between third parties also need a relation whose subject is not the user",
        "role.beneficiary is the only part that types cleanly, and an event with only a "
        "beneficiary and no event type is not a memory of the party",
    ),
    _concept(
        "expr-000049",
        (
            "l1:state.circumstance",
            "l1:state.occupation_status",
            "l1:task.declared_intention",
        ),
        "the dance studio is on tenuous ground, so they took a temp job to cover expenses while "
        "looking for investors",
    ),
    _none("expr-000050", "thanks, appreciation and a goodbye; pure closing pleasantry"),
    _concept(
        "expr-000051",
        ("l1:attribute.affiliation", "l1:preference.affinity"),
        "loves learning about different cultures and meeting people from different backgrounds, "
        "and their teammates come from all over",
    ),
    _ambiguous(
        "expr-000052",
        ("l1:predicate.occupy_role", "l1:state.occupation_status"),
        "has been taking a poetry class lately to help put feelings into words",
        "occupy_role covers studying as a predicate sense while occupation_status covers holding "
        "a studying position as a state; a leisure class fits either and the two are not "
        "jointly attested, so the text underdetermines which the mapper should return",
    ),
    _none("expr-000053", "offer to hear back, reassurance and a conversational sign-off"),
    _concept(
        "expr-000054",
        ("l1:event.first_encounter", "l1:time.at_assertion"),
        "meeting the other party for the first time on this occasion",
    ),
    _gap(
        "expr-000055",
        "went to a yoga retreat near their mother's place last week, spent time in nature and "
        "found it life-changing",
        "an activity event type for attending a retreat or course, and a pursuit type for yoga as "
        "an ongoing practice",
        "the travel and the place are incidental scaffolding that types fine; the retreat itself "
        "is the memory and has no type. 'life-changing' is emphasis, not event.life_transition",
    ),
    _concept(
        "expr-000056",
        ("l1:predicate.consume_media", "l1:task.declared_intention"),
        "will finish reading the book and report back when done",
    ),
    _none("expr-000057", "generic remark that nature leaves us speechless; no subject content"),
    _concept(
        "expr-000058",
        ("l1:preference.affinity", "l1:task.declared_intention"),
        "is interested in exploring object detection with YOLO and wants tutorials, papers and "
        "implementations",
    ),
    _concept(
        "expr-000059",
        (
            "l1:modality.desired",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
        ),
        "wants to use their platform to make a difference, possibly starting a foundation and "
        "doing charity work, to leave a meaningful legacy",
        note="the concrete plan is a declared intention, but 'leave a meaningful legacy' is a "
        "held value rather than a task, and that half is the held-value gap",
    ),
    _concept(
        "expr-000060",
        (
            "l1:attribute.assessment",
            "l1:attribute.kind",
            "l1:modality.believed",
            "l1:predicate.consume_media",
        ),
        "believes the film they watched was a standalone about animals' daily lives, serious in "
        "tone but engaging",
    ),
    _none("expr-000061", "questions about the other party's dogs' breed and what they enjoy"),
    _concept(
        "expr-000062",
        (
            "l1:attribute.place",
            "l1:modality.desired",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
        ),
        "is thinking of stopping at a waterfront cafe or restaurant to eat after their bike ride",
    ),
    _none("expr-000063", "compliment on a photo and a question about the other party's habits"),
    _concept(
        "expr-000064",
        (
            "l1:state.circumstance",
            "l1:task.declared_intention",
            "l1:time.before_assertion",
        ),
        "went to the ER last weekend with gastritis, took it as a wake-up call and intends to eat "
        "better and exercise regularly; their phone is also causing stress",
        note="a health condition and an ER visit both land on state.circumstance, the catch-all; "
        "the visit is an episode and no event type covers a medical or health event",
    ),
    _concept(
        "expr-000065",
        (
            "l1:attribute.assessment",
            "l1:predicate.consume_media",
            "l1:time.recurring",
        ),
        "watched that movie with the family repeatedly, getting comfortable with snacks and a "
        "blanket, and holds it as a special memory",
        note="the recurring family viewing is a habit in all but support count; the 'special "
        "memory' framing is the episodic-experience gap sitting on top of a typed event",
    ),
    _gap(
        "expr-000066",
        "in-character narration: thanks a voice on a walkie-talkie and sets off to follow green "
        "pipes to the security room",
        "an in-fiction source status, so a mapper can decline to record a persona's actions as "
        "the subject's own",
        "every clause has a type -- relocate, seek_information, declared_intention -- which is "
        "exactly the danger: a mapper will extract them and store fiction as fact",
    ),
    _none(
        "expr-000067",
        "generic remark that sports unite people, plus a question about the other party's book",
    ),
    _concept(
        "expr-000068",
        ("l1:role.quantity", "l1:state.possession", "l1:time.before_assertion"),
        "has three dogs and took them on a beach outing yesterday to socialise with other owners",
        note="owning three dogs is an independent typed proposition, so this is a concept; the "
        "outing itself is the generic-activity gap and a mapper cannot be faulted for missing it",
    ),
    _none("expr-000069", "encouragement and support addressed to the other party"),
    _none("expr-000070", "sympathy and an offer of help; no propositional content"),
    _gap(
        "expr-000071",
        "these basketball shoes are lucky, have been through good and bad, and every mark has a "
        "story; also adding a recommended fantasy book to a list",
        "an object-significance type carrying what a possession means to its holder, beyond the "
        "fact that it is held",
        "the book half is typed (assessment, affinity, declared_intention) but the shoes are the "
        "novel content and state.possession discards the entire point of the turn",
    ),
    _concept(
        "expr-000072",
        (
            "l2:abstraction.habit",
            "l1:attribute.affiliation",
            "l1:task.declared_intention",
            "l1:time.recurring",
        ),
        "will try Mint, and has been frequenting high-end department stores lately, which they are "
        "questioning",
        note="'I realised I've been frequenting X a lot lately' is a self-reported recurring "
        "behaviour, so the L2 habit is defensible on one turn; flagged as an L2 abstraction",
    ),
    _concept(
        "expr-000073",
        (
            "l1:attribute.designation",
            "l1:attribute.place",
            "l1:source_status.assistant_asserted",
        ),
        "assistant-supplied contact details for a tourism organisation: address, phone, email, site",
        note="the types exist but v2 excludes Individuals and values by design, so what is "
        "retained is only that an organisation has a place and a designation, not the details "
        "themselves; a mapper returning none here is arguably as correct",
    ),
    _ambiguous(
        "expr-000074",
        ("l1:preference.affinity", "l1:task.declared_intention"),
        "likes the idea of exploring abstract expression and wants tips on making a good piece",
        "'I like the idea of X' is either a stated taste for X or a soft declaration of intent to "
        "do X; the construction is systematically ambiguous and recurs across this sample",
    ),
    _concept(
        "expr-000075",
        (
            "l1:preference.affinity",
            "l1:preference.threshold",
            "l1:role.constraint_on",
        ),
        "wants a durable, comfortable orthopedic or memory-foam dog bed in the 40-to-50 dollar range",
    ),
    _concept(
        "expr-000076",
        (
            "l1:attribute.calendar_position",
            "l1:attribute.magnitude",
            "l1:predicate.transfer_value",
            "l1:state.possession",
            "l1:task.declared_intention",
        ),
        "owns an old motorcycle listed for sale at 3,500 dollars on 20 January, with interested "
        "buyers but no offer yet",
    ),
    _concept(
        "expr-000077",
        (
            "l1:role.recipient",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
        ),
        "will write a heartfelt letter to a named person including specific shared memories",
    ),
    _concept(
        "expr-000078",
        (
            "l1:preference.affinity",
            "l1:preference.threshold",
            "l1:role.trigger",
            "l1:task.conditional_intention",
        ),
        "loyal to one fuel brand but will only fill up there when its price is competitive, using "
        "comparison apps to decide",
        note="a genuine conditional intention with a price trigger; flagged because the trigger is "
        "a standing comparison rather than a one-off condition, which stretches role.trigger",
    ),
    _concept(
        "expr-000079",
        (
            "l1:predicate.consume_media",
            "l1:predicate.seek_information",
            "l1:time.before_assertion",
        ),
        "watched a documentary on a streaming service during a free trial last month and cannot "
        "now identify it",
    ),
    _concept(
        "expr-000080",
        (
            "l1:frequency.habitual",
            "l1:role.duration",
            "l1:state.circumstance",
            "l1:task.declared_intention",
        ),
        "has congestion, will try a saline nasal spray, and does nebulizer inhalation treatments "
        "twice a day",
        note="a medical treatment regimen typed as habitual frequency over a circumstance; there "
        "is no treatment or regimen type, so the therapy itself is only implied",
    ),
    _concept(
        "expr-000081",
        (
            "l1:modality.desired",
            "l1:preference.affinity",
            "l1:task.declared_intention",
        ),
        "is interested in explainable AI and fairness, thinks transparency matters, and wants to "
        "contact two named researchers",
        note="'I think it's really important' is the held-value gap again; the interest and the "
        "contact intention are typed, so the record stays a concept",
    ),
    _concept(
        "expr-000082",
        (
            "l1:preference.affinity",
            "l1:state.possession",
            "l1:time.before_assertion",
        ),
        "recently acquired a 1943 error coin and wants resources for learning about error coins",
    ),
    _concept(
        "expr-000083",
        (
            "l1:attribute.magnitude",
            "l1:state.possession",
            "l1:task.declared_intention",
            "l1:time.after_assertion",
        ),
        "planning a night out with friends this weekend and owns new designer heels bought at an "
        "outlet for 200 dollars",
    ),
    _concept(
        "expr-000084",
        (
            "l1:attribute.assessment",
            "l1:attribute.magnitude",
            "l1:attribute.place",
            "l1:task.declared_intention",
        ),
        "rates a downtown bike shop highly for a past tune-up, bought a helmet there for 120 "
        "dollars, and may return for the next one",
    ),
    _concept(
        "expr-000085",
        (
            "l1:attribute.assessment",
            "l1:preference.affinity",
            "l1:time.recurring",
        ),
        "has been experimenting with smoking woods for BBQ, recently tried apple wood and found it "
        "gave grilled chicken a fruity flavour",
    ),
    _concept(
        "expr-000086",
        ("l1:preference.affinity", "l1:predicate.seek_information"),
        "is particularly interested in language models and transformers, and asks about BERT in "
        "industry chatbot settings",
    ),
    _concept(
        "expr-000087",
        ("l1:task.declared_intention",),
        "will experiment with different techniques to find the best approach for their task",
        note="thin: an intention with an anaphoric object and nothing else. Kept as a concept "
        "under the stated-intention policy, but a mapper returning none is defensible",
    ),
    _concept(
        "expr-000088",
        ("l1:role.recipient", "l1:task.declared_intention"),
        "intends to thank the woman who helped them, specifically and sincerely",
    ),
    _concept(
        "expr-000089",
        (
            "l1:attribute.assessment",
            "l1:preference.affinity",
            "l1:state.possession",
        ),
        "wants stir-fry recipes, and owns a new kitchen mat that grips well and cleans easily",
    ),
    _concept(
        "expr-000090",
        (
            "l1:attribute.kind",
            "l1:preference.affinity",
            "l1:role.comparison_target",
        ),
        "wants games with emotional storytelling like the one discussed but in a different setting "
        "or genre",
    ),
    _concept(
        "expr-000091",
        (
            "l1:predicate.seek_information",
            "l1:role.duration",
            "l1:task.declared_intention",
        ),
        "will ask a practice about new-patient wait times and whether they run a reminder system",
    ),
    _concept(
        "expr-000092",
        ("l1:task.declared_intention",),
        "will try the modified routine and wants ways to track progress and stay motivated",
    ),
    _concept(
        "expr-000093",
        (
            "l1:attribute.availability",
            "l1:attribute.calendar_position",
            "l1:task.declared_intention",
        ),
        "is thinking of cycling a waterfront path and asks whether it is open to cyclists on "
        "weekdays or only weekends",
    ),
    _concept(
        "expr-000094",
        (
            "l1:preference.affinity",
            "l1:predicate.consume_media",
            "l1:role.duration",
            "l1:time.recurring",
        ),
        "is particularly interested in history podcasts and commutes about forty minutes each way",
        note="the commute is a recurring circumstance with a duration; there is no type for a "
        "regular routine slot, so 'each way, every day' is only partly captured",
    ),
    _concept(
        "expr-000095",
        ("l1:preference.affinity", "l1:predicate.seek_information"),
        "likes wall-mounted shelves, wants to mix them with glass display cases, and also asks for "
        "resources on film development",
    ),
    _concept(
        "expr-000096",
        (
            "l1:modality.believed",
            "l1:predicate.transfer_value",
            "l1:state.possession",
        ),
        "believes the art market is unpredictable but got lucky with a flea-market find they now own",
    ),
    _concept(
        "expr-000097",
        (
            "l1:attribute.kind",
            "l1:preference.affinity",
            "l1:role.comparison_target",
        ),
        "finds expansive exploration-led design appealing and wants similar indie games with "
        "stronger storytelling and character development",
    ),
    _concept(
        "expr-000098",
        (
            "l1:preference.affinity",
            "l1:predicate.consume_media",
            "l1:role.comparison_target",
            "l1:time.before_assertion",
        ),
        "recently finished a named open-world game and wants something similar with an engaging story",
    ),
    _concept(
        "expr-000099",
        (
            "l1:predicate.seek_information",
            "l1:state.occupation_status",
            "l1:task.outstanding_requirement",
        ),
        "is writing a Master's thesis on AI in medical diagnosis and still needs more sources",
    ),
    _concept(
        "expr-000100",
        (
            "l1:task.declared_intention",
            "l1:task.outstanding_requirement",
            "l1:time.after_assertion",
        ),
        "will serve a cake at a birthday party and must store it properly beforehand",
    ),
    _concept(
        "expr-000101",
        (
            "l1:attribute.clock_position",
            "l1:frequency.habitual",
            "l1:task.declared_intention",
            "l1:time.recurring",
        ),
        "already wakes at 8:30 on Saturdays and wants to add a thirty-minute Sunday yoga routine, "
        "breakfast and meal prep",
        note="an established weekly pattern plus an intended new one; the recurring slot is only "
        "expressible as frequency plus a clock position, which loses the day-of-week structure",
    ),
    _concept(
        "expr-000102",
        (
            "l1:modality.believed",
            "l1:polarity.denied",
            "l1:predicate.consume_media",
            "l1:task.declared_intention",
        ),
        "has not played those games but has heard good things about two of them and will try one, "
        "and wants gaming communities to discuss games in",
    ),
    _concept(
        "expr-000103",
        (
            "l1:preference.affinity",
            "l1:preference.threshold",
            "l1:role.constraint_on",
        ),
        "wants healthy snack options that are easy to prepare and do not take much time",
    ),
    _concept(
        "expr-000104",
        ("l1:state.possession", "l1:task.declared_intention"),
        "is thinking of trying the flaxseed version and asks whether a regular blender will grind them",
    ),
    _concept(
        "expr-000105",
        (
            "l1:modality.desired",
            "l1:state.possession",
            "l1:task.declared_intention",
        ),
        "has many phone apps, finds the ones they need hard to locate, and is considering tidying "
        "the home screen",
    ),
    _concept(
        "expr-000106",
        (
            "l1:attribute.place",
            "l1:predicate.relocate",
            "l1:role.duration",
            "l1:task.declared_intention",
        ),
        "on a long drive, plans to stop at a named island for lunch and a short beach walk because "
        "it adds little to the trip",
    ),
    _concept(
        "expr-000107",
        (
            "l1:attribute.assessment",
            "l1:attribute.kind",
            "l1:preference.affinity",
            "l1:predicate.seek_information",
        ),
        "is interested in a named show on a streaming service and asks whether it is comedy or "
        "drama, and about its tone, pacing and style",
    ),
    _concept(
        "expr-000108",
        (
            "l1:role.beneficiary",
            "l1:task.declared_intention",
            "l1:time.at_assertion",
        ),
        "is painting a sunset scene they think their sister will love, having completed four "
        "projects since starting classes and feeling confident",
        note="the completed-project count and the confidence are the positive-capability gap; the "
        "in-progress work and the beneficiary are typed, so the record stays a concept",
    ),
    _ambiguous(
        "expr-000109",
        ("l1:preference.affinity", "l1:preference.avoidance"),
        "wants non-fiction self-help and personal development books that are backed by scientific "
        "research rather than inspirational anecdote, for improving daily habits and productivity",
        "the 'not just inspirational stories or anecdotes' clause is either a negated affinity or "
        "a standing avoidance of that kind of book; avoidance claims more than the text supports "
        "and denied affinity claims less, and nothing here settles it",
    ),
    _concept(
        "expr-000110",
        (
            "l1:predicate.seek_information",
            "l1:task.declared_intention",
            "l2:abstraction.value_history",
        ),
        "plans a longer ride this weekend and asks the system to recall when the bike chain was "
        "last lubricated and whether it is due",
        note="a direct request to read back a maintenance series, which is what value_history is "
        "for; flagged because the L2 label is being used for a query rather than an assertion",
    ),
    _concept(
        "expr-000111",
        (
            "l1:attribute.calendar_position",
            "l1:task.declared_intention",
            "l2:relation.partnership",
        ),
        "has a partner and an anniversary on 22 July, and wants romantic getaway ideas to make it "
        "special",
        note="an explicit partnership plus a dated recurring occasion; flagged as an L2 relation "
        "asserted from a single turn",
    ),
    _none(
        "expr-000112",
        "a bare question about other maintenance tasks and whether any were done recently",
        note="in isolation the turn has no self-disclosure and its object is entirely anaphoric; "
        "with the preceding turn it would be a vehicle maintenance history, but the annotation "
        "unit is one expression and nothing here attests anything on its own",
    ),
    _concept(
        "expr-000113",
        (
            "l1:preference.affinity",
            "l1:predicate.transfer_value",
            "l1:state.possession",
            "l1:time.before_assertion",
        ),
        "wants new breakfast recipes, received an espresso machine from their sister as a gift, "
        "donated the old coffee maker and prefers the upgrade",
        note="the gift is a transfer with a kin source and the donation another; the sister tie is "
        "an L2 kin relation that a mapper could equally return here",
    ),
    _concept(
        "expr-000114",
        ("l1:predicate.seek_information", "l1:preference.affinity"),
        "asks whether diversity and inclusion programmes in an industry are effective and what "
        "data shows their impact",
        note="thin and close to none: the only durable content is a topical interest, and the "
        "substance is a question about third parties with no bearing on the subject",
    ),
    _concept(
        "expr-000115",
        ("l1:preference.affinity", "l1:predicate.seek_information"),
        "wants to explore pedestrian detection for autonomous vehicles and asks for YOLO resources",
    ),
    _none(
        "expr-000116",
        "a one-line role-play framing prompt telling the subject to recall a fictional exchange",
        note="labelled none rather than out_of_scope: unlike the other role-play turns this one "
        "asserts nothing at all, fictional or otherwise, so there is no content to be uncovered",
    ),
    _concept(
        "expr-000117",
        ("l1:task.declared_intention",),
        "will check the options offered and pick whichever fits their needs best",
        note="the same thin anaphoric intention as expr-000087 and expr-000092; labelled "
        "consistently with them rather than by how substantial the wording happens to feel",
    ),
    _concept(
        "expr-000118",
        ("l1:preference.affinity", "l1:predicate.seek_information"),
        "wants to discuss ingredients that pair with carrot cake, and which nuts would complement it",
        note="the interest in carrot cake is presupposed rather than stated; this is the weakest "
        "concept label in the set and none is a reasonable alternative",
    ),
    _concept(
        "expr-000119",
        (
            "l1:attribute.affiliation",
            "l1:task.declared_intention",
            "l1:task.outstanding_requirement",
        ),
        "plans to use their sales team for a product launch, has been working closely with them, "
        "and needs to know what training or enablement they require",
    ),
)


def build_annotation_gold() -> AnnotationGold:
    """Assemble the gold set, bound to the sample digest it was produced against."""
    return AnnotationGold(
        sample_sha256=ANNOTATED_SAMPLE_SHA256,
        annotated_against_ontology="ontology v2 (O_L1, O_L2, M_L1_to_L2)",
        records=tuple(sorted(_RECORDS, key=lambda record: record.expression_id)),
    )
