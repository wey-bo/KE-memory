"""The supersession record: what v2 did with every one of v1's items.

This unit exists because "v2 supersedes v1" is otherwise an unfalsifiable sentence. The freeze
model checks the record against v1's actual id set and against v2's units, so a revision must name
an id v2 contains and a retirement must name one it does not.

The headline is that **nothing was retired**. All 107 v1 ids -- 67 L1 items, 20 L2 items and 20 map
entries -- survive under the same id, which was a constraint on the work rather than an outcome of
it: a consumer citing ``l1:preference.affinity`` against v1 still resolves it against v2. Where a
v1 decision was wrong the item was revised, not dropped, and where a v1 rejection was right it was
left rejected.

One item is carried forward byte-identically: ``l1:role.attribute_bearer``. That single number is
the honest measure of how much moved. Everything else is revised, and the reason is usually one of
three things:

- a published source now backs it, so it carries a resolvable citation where v1 could carry none;
- its ``sense`` was rewritten because v1's phrasing described a corpus slot rather than a concept;
- it gained a role slot, most often ``l1:role.beneficiary`` or ``l1:role.cause``, because v1 had no
  such position to bind.

A revision reason states what changed, measured by comparing this build against the frozen v1
artifacts rather than recalled from the editing. That is why the reasons read as inventories: an
impressionistic reason would be the thing this unit exists to prevent.
"""

from __future__ import annotations

from typing import Final

from .models import SupersessionFreeze, SupersessionOutcome, SupersessionRecord

SUPERSESSION_VERSION: Final[str] = "2.0.0"
SUPERSEDED_VERSION: Final[str] = "1.0.0"


def _revised(v1_id: str, reason: str) -> SupersessionRecord:
    """The common case: the id survives and its content changed."""
    return SupersessionRecord(
        v1_id=v1_id, outcome=SupersessionOutcome.REVISED, reason=reason, v2_id=v1_id
    )


def _carried(v1_id: str, reason: str) -> SupersessionRecord:
    return SupersessionRecord(
        v1_id=v1_id, outcome=SupersessionOutcome.CARRIED_FORWARD, reason=reason, v2_id=v1_id
    )


_RECORDS: Final[tuple[SupersessionRecord, ...]] = (
    _revised(
        "l1:attribute.assessment",
        (
            "the facet survives with its sense rewritten to describe the property rather than "
            "the Taskmaster2 annotation that evidenced it. Changed: sense rewritten; alias "
            "set 4->4; role slots 1->2; provenance 1->2; constraints 1->2; cites 1 external "
            "reference"
        ),
    ),
    _revised(
        "l1:attribute.availability",
        (
            "the facet survives with its sense rewritten to describe the property rather than "
            "the Taskmaster2 annotation that evidenced it. Changed: sense rewritten; alias "
            "set 4->4; provenance 1->2"
        ),
    ),
    _revised(
        "l1:attribute.calendar_position",
        (
            "the facet survives with its sense rewritten to describe the property rather than "
            "the Taskmaster2 annotation that evidenced it. Changed: sense rewritten; alias "
            "set 3->3; provenance 1->2"
        ),
    ),
    _revised(
        "l1:attribute.clock_position",
        (
            "the facet survives with its sense rewritten to describe the property rather than "
            "the Taskmaster2 annotation that evidenced it. Changed: sense rewritten; alias "
            "set 3->3; provenance 1->2"
        ),
    ),
    _revised(
        "l1:attribute.designation",
        (
            "the facet survives with its sense rewritten to describe the property rather than "
            "the Taskmaster2 annotation that evidenced it. Changed: sense rewritten; alias "
            "set 3->3; provenance 1->2; constraints 1->2; cites 1 external reference"
        ),
    ),
    _revised(
        "l1:attribute.kind",
        (
            "the facet survives with its sense rewritten to describe the property rather than "
            "the Taskmaster2 annotation that evidenced it. Changed: sense rewritten; alias "
            "set 4->4"
        ),
    ),
    _revised(
        "l1:attribute.magnitude",
        (
            "the facet survives with its sense rewritten to describe the property rather than "
            "the Taskmaster2 annotation that evidenced it. Changed: sense rewritten; alias "
            "set 5->5; provenance 1->3; cites 1 external reference"
        ),
    ),
    _revised(
        "l1:attribute.place",
        (
            "the facet survives with its sense rewritten to describe the property rather than "
            "the Taskmaster2 annotation that evidenced it. Changed: sense rewritten; alias "
            "set 5->4; provenance 1->3; cites 1 external reference"
        ),
    ),
    _revised(
        "l1:event.attempt_failed",
        (
            "the event section widened from five to eight, so this type was tightened to "
            "leave room for the transitions, achievements and first encounters v1 had no "
            "types for. Changed: sense rewritten; alias set 3->3; role slots 2->3; provenance "
            "1->2; cites 2 external references"
        ),
    ),
    _revised(
        "l1:event.commitment_made",
        (
            "the event section widened from five to eight, so this type was tightened to "
            "leave room for the transitions, achievements and first encounters v1 had no "
            "types for. Changed: sense rewritten; alias set 3->3; role slots 2->3; relations "
            "1->2; provenance 1->2; cites 1 external reference"
        ),
    ),
    _revised(
        "l1:event.commitment_withdrawn",
        (
            "the event section widened from five to eight, so this type was tightened to "
            "leave room for the transitions, achievements and first encounters v1 had no "
            "types for. Changed: sense rewritten; alias set 2->2; role slots 2->3; relations "
            "1->2; provenance 1->3; cites 1 external reference"
        ),
    ),
    _revised(
        "l1:event.information_request",
        (
            "the event section widened from five to eight, so this type was tightened to "
            "leave room for the transitions, achievements and first encounters v1 had no "
            "types for. Changed: sense rewritten; alias set 2->2; role slots 2->3; provenance "
            "1->2; cites 1 external reference"
        ),
    ),
    _revised(
        "l1:event.media_consumption",
        (
            "the event section widened from five to eight, so this type was tightened to "
            "leave room for the transitions, achievements and first encounters v1 had no "
            "types for. Changed: sense rewritten; alias set 3->3; role slots 2->3; relations "
            "1->2; provenance 1->2; cites 1 external reference"
        ),
    ),
    _revised(
        "l1:modality.asserted",
        (
            "a value vocabulary carried over with its sense rewritten; v1 phrased several of "
            "these as descriptions of act labels rather than of what the value means. "
            "Changed: sense rewritten; alias set 2->2"
        ),
    ),
    _revised(
        "l1:modality.believed",
        (
            "a value vocabulary carried over with its sense rewritten; v1 phrased several of "
            "these as descriptions of act labels rather than of what the value means. "
            "Changed: sense rewritten; alias set 3->3; provenance 1->2; cites 1 external "
            "reference"
        ),
    ),
    _revised(
        "l1:modality.desired",
        (
            "a value vocabulary carried over with its sense rewritten; v1 phrased several of "
            "these as descriptions of act labels rather than of what the value means. "
            "Changed: sense rewritten; alias set 3->3; provenance 1->2; cites 1 external "
            "reference"
        ),
    ),
    _revised(
        "l1:modality.directed",
        (
            "a value vocabulary carried over with its sense rewritten; v1 phrased several of "
            "these as descriptions of act labels rather than of what the value means. "
            "Changed: sense rewritten; alias set 3->3"
        ),
    ),
    _revised(
        "l1:modality.intended",
        (
            "a value vocabulary carried over with its sense rewritten; v1 phrased several of "
            "these as descriptions of act labels rather than of what the value means. "
            "Changed: sense rewritten; alias set 3->3; provenance 1->2; cites 1 external "
            "reference"
        ),
    ),
    _revised(
        "l1:polarity.affirmed",
        (
            "a value vocabulary carried over with its sense rewritten; v1 phrased several of "
            "these as descriptions of act labels rather than of what the value means. "
            "Changed: sense rewritten"
        ),
    ),
    _revised(
        "l1:polarity.denied",
        (
            "a value vocabulary carried over with its sense rewritten; v1 phrased several of "
            "these as descriptions of act labels rather than of what the value means. "
            "Changed: sense rewritten; provenance 1->2"
        ),
    ),
    _revised(
        "l1:polarity.indeterminate",
        (
            "a value vocabulary carried over with its sense rewritten; v1 phrased several of "
            "these as descriptions of act labels rather than of what the value means. "
            "Changed: sense rewritten; alias set 1->1"
        ),
    ),
    _revised(
        "l1:predicate.change_arrangement",
        (
            "v1's senses were clustered from SGD intent verbs and could claim no roleset id; "
            "this sense is now fixed by a named PropBank roleset and takes its slots from "
            "that roleset's numbered arguments. Changed: sense rewritten; alias set 5->5; "
            "role slots 2->3; provenance 1->2; cites 2 external references"
        ),
    ),
    _revised(
        "l1:predicate.commit_to_arrangement",
        (
            "v1's senses were clustered from SGD intent verbs and could claim no roleset id; "
            "this sense is now fixed by a named PropBank roleset and takes its slots from "
            "that roleset's numbered arguments. Changed: sense rewritten; alias set 4->5; "
            "role slots 3->5; relations 0->1; provenance 1->2; cites 3 external references"
        ),
    ),
    _revised(
        "l1:predicate.consume_media",
        (
            "v1's senses were clustered from SGD intent verbs and could claim no roleset id; "
            "this sense is now fixed by a named PropBank roleset and takes its slots from "
            "that roleset's numbered arguments. Changed: sense rewritten; alias set 4->4; "
            "relations 0->1; provenance 1->2; cites 2 external references"
        ),
    ),
    _revised(
        "l1:predicate.hold_attitude",
        (
            "v1's senses were clustered from SGD intent verbs and could claim no roleset id; "
            "this sense is now fixed by a named PropBank roleset and takes its slots from "
            "that roleset's numbered arguments. Changed: sense rewritten; alias set 5->5; "
            "role slots 2->3; relations 0->2; provenance 1->2; cites 2 external references"
        ),
    ),
    _revised(
        "l1:predicate.occupy_role",
        (
            "v1's senses were clustered from SGD intent verbs and could claim no roleset id; "
            "this sense is now fixed by a named PropBank roleset and takes its slots from "
            "that roleset's numbered arguments. Changed: sense rewritten; alias set 5->4; "
            "provenance 1->3; cites 3 external references"
        ),
    ),
    _revised(
        "l1:predicate.seek_information",
        (
            "v1's senses were clustered from SGD intent verbs and could claim no roleset id; "
            "this sense is now fixed by a named PropBank roleset and takes its slots from "
            "that roleset's numbered arguments. Changed: sense rewritten; alias set 5->5; "
            "role slots 3->4; provenance 1->2; cites 1 external reference"
        ),
    ),
    _revised(
        "l1:predicate.transfer_value",
        (
            "v1's senses were clustered from SGD intent verbs and could claim no roleset id; "
            "this sense is now fixed by a named PropBank roleset and takes its slots from "
            "that roleset's numbered arguments. Changed: sense rewritten; alias set 4->5; "
            "provenance 1->2; cites 3 external references"
        ),
    ),
    _revised(
        "l1:preference.affinity",
        (
            "preference types gained the beneficiary and strength machinery that closes v1's "
            "recorded gaps on preference strength and preference held for another person. "
            "Changed: sense rewritten; alias set 4->4; role slots 2->3; relations 2->3; "
            "provenance 1->2; cites 2 external references"
        ),
    ),
    _revised(
        "l1:preference.comparative",
        (
            "preference types gained the beneficiary and strength machinery that closes v1's "
            "recorded gaps on preference strength and preference held for another person. "
            "Changed: sense rewritten; alias set 3->3; role slots 3->4; provenance 1->3; "
            "cites 1 external reference"
        ),
    ),
    _revised(
        "l1:preference.threshold",
        (
            "preference types gained the beneficiary and strength machinery that closes v1's "
            "recorded gaps on preference strength and preference held for another person. "
            "Changed: sense rewritten; alias set 4->4; role slots 2->3; provenance 1->2; "
            "cites 1 external reference"
        ),
    ),
    _revised(
        "l1:qualifier.assertion_standing",
        (
            "the dimension's sense was rewritten to say what it qualifies rather than which "
            "corpus slot suggested it. Changed: sense rewritten; alias set 2->2"
        ),
    ),
    _revised(
        "l1:qualifier.modality",
        (
            "the dimension's sense was rewritten to say what it qualifies rather than which "
            "corpus slot suggested it. Changed: sense rewritten"
        ),
    ),
    _revised(
        "l1:qualifier.polarity",
        (
            "the dimension's sense was rewritten to say what it qualifies rather than which "
            "corpus slot suggested it. Changed: sense rewritten"
        ),
    ),
    _revised(
        "l1:qualifier.source_status",
        (
            "the dimension's sense was rewritten to say what it qualifies rather than which "
            "corpus slot suggested it. Changed: sense rewritten; alias set 2->2"
        ),
    ),
    _revised(
        "l1:qualifier.time",
        (
            "the dimension's sense was rewritten to say what it qualifies rather than which "
            "corpus slot suggested it. Changed: sense rewritten; alias set 2->2"
        ),
    ),
    _revised(
        "l1:role.agent",
        (
            "v1 called its roles corpus-shaped and named PropBank as what would settle them; "
            "this role is now cross-checked against PropBank's function tag distribution. "
            "Changed: provenance 1->2; cites 1 external reference"
        ),
    ),
    _carried(
        "l1:role.attribute_bearer",
        (
            "byte-identical to v1: the only item in either layer that needed no change at "
            "all. Its sense, its single alias and its Taskmaster2 provenance were still "
            "exactly right, and it is recorded so the carried-forward count is a real number"
        ),
    ),
    _revised(
        "l1:role.constraint_on",
        (
            "v1 called its roles corpus-shaped and named PropBank as what would settle them; "
            "this role is now cross-checked against PropBank's function tag distribution. "
            "Changed: provenance 1->2; cites 1 external reference"
        ),
    ),
    _revised(
        "l1:role.holder",
        (
            "v1 called its roles corpus-shaped and named PropBank as what would settle them; "
            "this role is now cross-checked against PropBank's function tag distribution. "
            "Changed: provenance 1->2; cites 1 external reference"
        ),
    ),
    _revised(
        "l1:role.instrument",
        (
            "v1 called its roles corpus-shaped and named PropBank as what would settle them; "
            "this role is now cross-checked against PropBank's function tag distribution. "
            "Changed: provenance 1->2; cites 1 external reference"
        ),
    ),
    _revised(
        "l1:role.quantity",
        (
            "v1 called its roles corpus-shaped and named PropBank as what would settle them; "
            "this role is now cross-checked against PropBank's function tag distribution. "
            "Changed: provenance 1->2; cites 1 external reference"
        ),
    ),
    _revised(
        "l1:role.recipient",
        (
            "v1 called its roles corpus-shaped and named PropBank as what would settle them; "
            "this role is now cross-checked against PropBank's function tag distribution. "
            "Changed: alias set 2->2; provenance 1->2; cites 1 external reference"
        ),
    ),
    _revised(
        "l1:role.source_location",
        (
            "v1 called its roles corpus-shaped and named PropBank as what would settle them; "
            "this role is now cross-checked against PropBank's function tag distribution. "
            "Changed: provenance 1->2; cites 1 external reference"
        ),
    ),
    _revised(
        "l1:role.target_location",
        (
            "v1 called its roles corpus-shaped and named PropBank as what would settle them; "
            "this role is now cross-checked against PropBank's function tag distribution. "
            "Changed: provenance 1->2; cites 1 external reference"
        ),
    ),
    _revised(
        "l1:role.theme",
        (
            "v1 called its roles corpus-shaped and named PropBank as what would settle them; "
            "this role is now cross-checked against PropBank's function tag distribution. "
            "Changed: provenance 1->2; cites 1 external reference"
        ),
    ),
    _revised(
        "l1:source_status.assistant_asserted",
        (
            "a value vocabulary carried over with its sense rewritten; v1 phrased several of "
            "these as descriptions of act labels rather than of what the value means. "
            "Changed: sense rewritten; alias set 2->2"
        ),
    ),
    _revised(
        "l1:source_status.confirmed_by_both",
        (
            "a value vocabulary carried over with its sense rewritten; v1 phrased several of "
            "these as descriptions of act labels rather than of what the value means. "
            "Changed: sense rewritten; alias set 2->2; provenance 1->2"
        ),
    ),
    _revised(
        "l1:source_status.derived",
        (
            "a value vocabulary carried over with its sense rewritten; v1 phrased several of "
            "these as descriptions of act labels rather than of what the value means. "
            "Changed: sense rewritten"
        ),
    ),
    _revised(
        "l1:source_status.tool_observed",
        (
            "a value vocabulary carried over with its sense rewritten; v1 phrased several of "
            "these as descriptions of act labels rather than of what the value means. "
            "Changed: sense rewritten; alias set 3->3"
        ),
    ),
    _revised(
        "l1:source_status.user_reported",
        (
            "a value vocabulary carried over with its sense rewritten; v1 phrased several of "
            "these as descriptions of act labels rather than of what the value means. "
            "Changed: sense rewritten; alias set 2->2"
        ),
    ),
    _revised(
        "l1:standing.current",
        (
            "a value vocabulary carried over with its sense rewritten; v1 phrased several of "
            "these as descriptions of act labels rather than of what the value means. "
            "Changed: sense rewritten; alias set 2->2"
        ),
    ),
    _revised(
        "l1:standing.retracted",
        (
            "a value vocabulary carried over with its sense rewritten; v1 phrased several of "
            "these as descriptions of act labels rather than of what the value means. "
            "Changed: sense rewritten; alias set 3->3; provenance 1->2"
        ),
    ),
    _revised(
        "l1:standing.superseded",
        (
            "a value vocabulary carried over with its sense rewritten; v1 phrased several of "
            "these as descriptions of act labels rather than of what the value means. "
            "Changed: sense rewritten; alias set 3->3"
        ),
    ),
    _revised(
        "l1:state.capability_constraint",
        (
            "the state section widened from four items to seven, so this type was tightened "
            "as occupation, residence and suspended commitment were split out of it. Changed: "
            "sense rewritten; alias set 4->4; role slots 2->3; relations 0->1; provenance "
            "1->2; cites 2 external references"
        ),
    ),
    _revised(
        "l1:state.circumstance",
        (
            "narrowed on purpose: v1's catch-all absorbed occupation, residence and "
            "restriction because it had nowhere else to put them, and its specializes_sense "
            "edge to the occupation predicate was dropped because occupation_status and "
            "residence now exist as their own state types. Changed: sense rewritten; alias "
            "set 3->3; role slots 2->1; relations 1->1; cites 1 external reference"
        ),
    ),
    _revised(
        "l1:state.pending_arrangement",
        (
            "the state section widened from four items to seven, so this type was tightened "
            "as occupation, residence and suspended commitment were split out of it. Changed: "
            "sense rewritten; alias set 3->3; role slots 2->3; relations 0->1; provenance "
            "1->2; cites 1 external reference"
        ),
    ),
    _revised(
        "l1:state.possession",
        (
            "the state section widened from four items to seven, so this type was tightened "
            "as occupation, residence and suspended commitment were split out of it. Changed: "
            "sense rewritten; alias set 3->3; role slots 2->3; provenance 1->2; cites 1 "
            "external reference"
        ),
    ),
    _revised(
        "l1:task.abandoned_intention",
        (
            "task types gained a beneficiary or cause position, and the conditional case "
            "moved to the new conditional-intention type. Changed: sense rewritten; alias set "
            "3->3; role slots 2->3; relations 0->1; provenance 1->3; cites 1 external "
            "reference"
        ),
    ),
    _revised(
        "l1:task.declared_intention",
        (
            "task types gained a beneficiary or cause position, and the conditional case "
            "moved to the new conditional-intention type. Changed: sense rewritten; alias set "
            "4->4; role slots 2->3; provenance 1->2; cites 2 external references"
        ),
    ),
    _revised(
        "l1:task.outstanding_requirement",
        (
            "task types gained a beneficiary or cause position, and the conditional case "
            "moved to the new conditional-intention type. Changed: sense rewritten; alias set "
            "3->3; role slots 2->3; provenance 1->2; cites 1 external reference"
        ),
    ),
    _revised(
        "l1:time.after_assertion",
        (
            "a value vocabulary carried over with its sense rewritten; v1 phrased several of "
            "these as descriptions of act labels rather than of what the value means. "
            "Changed: sense rewritten; alias set 3->3"
        ),
    ),
    _revised(
        "l1:time.at_assertion",
        (
            "a value vocabulary carried over with its sense rewritten; v1 phrased several of "
            "these as descriptions of act labels rather than of what the value means. "
            "Changed: sense rewritten; alias set 3->2"
        ),
    ),
    _revised(
        "l1:time.before_assertion",
        (
            "a value vocabulary carried over with its sense rewritten; v1 phrased several of "
            "these as descriptions of act labels rather than of what the value means. "
            "Changed: sense rewritten; alias set 2->2"
        ),
    ),
    _revised(
        "l1:time.recurring",
        (
            "a value vocabulary carried over with its sense rewritten; v1 phrased several of "
            "these as descriptions of act labels rather than of what the value means. "
            "Changed: sense rewritten; alias set 3->2; relations 1->2"
        ),
    ),
    _revised(
        "l1:time.spanning",
        (
            "a value vocabulary carried over with its sense rewritten; v1 phrased several of "
            "these as descriptions of act labels rather than of what the value means. "
            "Changed: sense rewritten; alias set 3->3; provenance 1->2"
        ),
    ),
    _revised(
        "l1:time.unspecified",
        (
            "a value vocabulary carried over with its sense rewritten; v1 phrased several of "
            "these as descriptions of act labels rather than of what the value means. "
            "Changed: sense rewritten"
        ),
    ),
    _revised(
        "l2:abstraction.carried_constraint",
        (
            "re-derived against the wider L1 and, where its v1 evidence was thin, re-measured "
            "against the build corpora. Changed: sense rewritten; alias set 3->3; relations "
            "1->0; constraints 1->0"
        ),
    ),
    _revised(
        "l2:abstraction.habit",
        (
            "re-derived against the wider L1 and, where its v1 evidence was thin, re-measured "
            "against the build corpora. Changed: sense rewritten; alias set 3->3; role slots "
            "1->2; relations 1->0; constraints 2->1; cites 2 external references"
        ),
    ),
    _revised(
        "l2:abstraction.preference_profile",
        (
            "re-derived against the wider L1 and, where its v1 evidence was thin, re-measured "
            "against the build corpora. Changed: sense rewritten; alias set 3->3; role slots "
            "1->2; relations 1->0; provenance 1->2; constraints 1->1; cites 1 external "
            "reference"
        ),
    ),
    _revised(
        "l2:abstraction.project",
        (
            "re-derived against the wider L1 and, where its v1 evidence was thin, re-measured "
            "against the build corpora. Changed: sense rewritten; alias set 3->3; role slots "
            "1->2; relations 2->0; constraints 1->0"
        ),
    ),
    _revised(
        "l2:abstraction.standing_condition",
        (
            "re-derived against the wider L1 and, where its v1 evidence was thin, re-measured "
            "against the build corpora. Changed: sense rewritten; alias set 3->3; relations "
            "1->0; constraints 1->0"
        ),
    ),
    _revised(
        "l2:abstraction.task",
        (
            "re-derived against the wider L1 and, where its v1 evidence was thin, re-measured "
            "against the build corpora. Changed: sense rewritten; alias set 3->3; relations "
            "1->0; constraints 1->0"
        ),
    ),
    _revised(
        "l2:abstraction.value_history",
        (
            "re-derived against the wider L1 and, where its v1 evidence was thin, re-measured "
            "against the build corpora. Changed: sense rewritten; alias set 3->3; relations "
            "1->0; constraints 1->0"
        ),
    ),
    _revised(
        "l2:evidence.partial_support_marked",
        (
            "restated now that a third evidence constraint forbids aggregation from improving "
            "on the source status of its supports. Changed: sense rewritten; alias set 2->1; "
            "constraints 1->0"
        ),
    ),
    _revised(
        "l2:evidence.supports_addressable",
        (
            "restated now that a third evidence constraint forbids aggregation from improving "
            "on the source status of its supports. Changed: sense rewritten; alias set 1->1; "
            "constraints 1->1"
        ),
    ),
    _revised(
        "l2:lifecycle.achieved",
        (
            "the lifecycle vocabulary grew from four values to six, so this value's "
            "boundaries were restated against dormant and condition_failed. Changed: sense "
            "rewritten; alias set 3->3; relations 1->0; provenance 1->2; cites 3 external "
            "references"
        ),
    ),
    _revised(
        "l2:lifecycle.lapsed",
        (
            "the lifecycle vocabulary grew from four values to six, so this value's "
            "boundaries were restated against dormant and condition_failed. Changed: sense "
            "rewritten; alias set 2->2; relations 1->0; constraints 1->0"
        ),
    ),
    _revised(
        "l2:lifecycle.open",
        (
            "the lifecycle vocabulary grew from four values to six, so this value's "
            "boundaries were restated against dormant and condition_failed. Changed: sense "
            "rewritten; alias set 3->3; relations 1->0"
        ),
    ),
    _revised(
        "l2:lifecycle.superseded_by_revision",
        (
            "the lifecycle vocabulary grew from four values to six, so this value's "
            "boundaries were restated against dormant and condition_failed. Changed: sense "
            "rewritten; alias set 2->2; relations 1->0"
        ),
    ),
    _revised(
        "l2:pattern.constraint_union",
        (
            "restated as a computation over the wider L1 rather than over v1's smaller "
            "qualifier set. Changed: sense rewritten; alias set 2->2; constraints 1->0"
        ),
    ),
    _revised(
        "l2:pattern.goal_decomposition",
        (
            "restated as a computation over the wider L1 rather than over v1's smaller "
            "qualifier set. Changed: sense rewritten; alias set 2->2; constraints 1->0"
        ),
    ),
    _revised(
        "l2:pattern.recurrence_count",
        (
            "restated as a computation over the wider L1 rather than over v1's smaller "
            "qualifier set. Changed: sense rewritten; alias set 3->3; provenance 1->2; "
            "constraints 1->0; cites 1 external reference"
        ),
    ),
    _revised(
        "l2:pattern.temporal_series",
        (
            "restated as a computation over the wider L1 rather than over v1's smaller "
            "qualifier set. Changed: sense rewritten; alias set 3->3; constraints 1->0"
        ),
    ),
    _revised(
        "l2:role.scope",
        (
            "v1 called its roles corpus-shaped and named PropBank as what would settle them; "
            "this role is now cross-checked against PropBank's function tag distribution. "
            "Changed: sense rewritten; alias set 2->2"
        ),
    ),
    _revised(
        "l2:role.subject",
        (
            "v1 called its roles corpus-shaped and named PropBank as what would settle them; "
            "this role is now cross-checked against PropBank's function tag distribution. "
            "Changed: sense rewritten; alias set 1->1; constraints 1->0"
        ),
    ),
    _revised(
        "l2:role.tracked_attribute",
        (
            "v1 called its roles corpus-shaped and named PropBank as what would settle them; "
            "this role is now cross-checked against PropBank's function tag distribution. "
            "Changed: sense rewritten; alias set 1->1; constraints 1->0"
        ),
    ),
    _revised(
        "m:abstraction.carried_constraint",
        (
            "the map was rebuilt against the wider L1, so this edge names the sources that "
            "now exist rather than v1's nearest approximation. Changed: derivation rule "
            "rewritten"
        ),
    ),
    _revised(
        "m:abstraction.habit",
        (
            "the map was rebuilt against the wider L1, so this edge names the sources that "
            "now exist rather than v1's nearest approximation. Changed: L1 sources 3->4; "
            "derivation rule rewritten"
        ),
    ),
    _revised(
        "m:abstraction.preference_profile",
        (
            "the map was rebuilt against the wider L1, so this edge names the sources that "
            "now exist rather than v1's nearest approximation. Changed: L1 sources 4->4; "
            "derivation rule rewritten"
        ),
    ),
    _revised(
        "m:abstraction.project",
        (
            "the map was rebuilt against the wider L1, so this edge names the sources that "
            "now exist rather than v1's nearest approximation. Changed: derivation rule "
            "rewritten"
        ),
    ),
    _revised(
        "m:abstraction.standing_condition",
        (
            "the map was rebuilt against the wider L1, so this edge names the sources that "
            "now exist rather than v1's nearest approximation. Changed: L1 sources 2->2; "
            "derivation rule rewritten"
        ),
    ),
    _revised(
        "m:abstraction.task",
        (
            "the map was rebuilt against the wider L1, so this edge names the sources that "
            "now exist rather than v1's nearest approximation. Changed: derivation kind "
            "aggregates_over->import_as; L1 sources 4->1; derivation rule rewritten; required "
            "support 2->1"
        ),
    ),
    _revised(
        "m:abstraction.value_history",
        (
            "the map was rebuilt against the wider L1, so this edge names the sources that "
            "now exist rather than v1's nearest approximation. Changed: L1 sources 4->2; "
            "derivation rule rewritten"
        ),
    ),
    _revised(
        "m:import.pattern_constraint_union",
        (
            "the map was rebuilt against the wider L1, so this edge names the sources that "
            "now exist rather than v1's nearest approximation. Changed: derivation kind "
            "import_as->abstracts_from; L1 sources 1->2; derivation rule rewritten"
        ),
    ),
    _revised(
        "m:import.pattern_goal_decomposition",
        (
            "the map was rebuilt against the wider L1, so this edge names the sources that "
            "now exist rather than v1's nearest approximation. Changed: derivation kind "
            "import_as->abstracts_from; L1 sources 1->2; derivation rule rewritten; required "
            "support 2->1"
        ),
    ),
    _revised(
        "m:import.pattern_recurrence_count",
        (
            "the map was rebuilt against the wider L1, so this edge names the sources that "
            "now exist rather than v1's nearest approximation. Changed: derivation kind "
            "import_as->abstracts_from; L1 sources 1->2; derivation rule rewritten; required "
            "support 2->1"
        ),
    ),
    _revised(
        "m:import.pattern_temporal_series",
        (
            "the map was rebuilt against the wider L1, so this edge names the sources that "
            "now exist rather than v1's nearest approximation. Changed: derivation kind "
            "import_as->abstracts_from; L1 sources 1->2; derivation rule rewritten; required "
            "support 2->1"
        ),
    ),
    _revised(
        "m:import.role_scope",
        (
            "the map was rebuilt against the wider L1, so this edge names the sources that "
            "now exist rather than v1's nearest approximation. Changed: derivation rule "
            "rewritten"
        ),
    ),
    _revised(
        "m:import.role_subject",
        (
            "the map was rebuilt against the wider L1, so this edge names the sources that "
            "now exist rather than v1's nearest approximation. Changed: derivation rule "
            "rewritten"
        ),
    ),
    _revised(
        "m:import.role_tracked_attribute",
        (
            "the map was rebuilt against the wider L1, so this edge names the sources that "
            "now exist rather than v1's nearest approximation. Changed: derivation rule "
            "rewritten"
        ),
    ),
    _revised(
        "m:lift.evidence_partial_support",
        (
            "the map was rebuilt against the wider L1, so this edge names the sources that "
            "now exist rather than v1's nearest approximation. Changed: L1 sources 2->2; "
            "derivation rule rewritten"
        ),
    ),
    _revised(
        "m:lift.evidence_supports_addressable",
        (
            "the map was rebuilt against the wider L1, so this edge names the sources that "
            "now exist rather than v1's nearest approximation. Changed: derivation kind "
            "qualifier_lift->import_as; L1 sources 1->1; derivation rule rewritten"
        ),
    ),
    _revised(
        "m:lift.lifecycle_achieved",
        (
            "the map was rebuilt against the wider L1, so this edge names the sources that "
            "now exist rather than v1's nearest approximation. Changed: L1 sources 2->2; "
            "derivation rule rewritten"
        ),
    ),
    _revised(
        "m:lift.lifecycle_lapsed",
        (
            "the map was rebuilt against the wider L1, so this edge names the sources that "
            "now exist rather than v1's nearest approximation. Changed: L1 sources 2->2; "
            "derivation rule rewritten"
        ),
    ),
    _revised(
        "m:lift.lifecycle_open",
        (
            "the map was rebuilt against the wider L1, so this edge names the sources that "
            "now exist rather than v1's nearest approximation. Changed: derivation kind "
            "qualifier_lift->import_as; L1 sources 2->1; derivation rule rewritten"
        ),
    ),
    _revised(
        "m:lift.lifecycle_superseded",
        (
            "the map was rebuilt against the wider L1, so this edge names the sources that "
            "now exist rather than v1's nearest approximation. Changed: derivation kind "
            "qualifier_lift->import_as; derivation rule rewritten"
        ),
    ),
)


def build_supersession() -> SupersessionFreeze:
    """Assemble the supersession unit, sorted by v1 id because the hash depends on the order."""
    return SupersessionFreeze(
        version=SUPERSESSION_VERSION,
        supersedes_version=SUPERSEDED_VERSION,
        records=tuple(sorted(_RECORDS, key=lambda record: record.v1_id)),
    )
