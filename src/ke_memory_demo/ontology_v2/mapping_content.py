"""M_L1_to_L2 v2: every cross-layer derivation, stated once and versioned on its own.

This unit exists because the two layers share no vocabulary. Without it, O_L2 would either have
to repeat L1 ids inside its own items -- making the layers one vocabulary in practice whatever the
documentation said -- or leave the connection implicit, in which case an abstraction's derivation
would be whatever the implementation happened to do.

Three things are recorded per edge and none is decoration:

- ``kind`` distinguishes an import (one L1 sense reused under an L2 id) from a genuine
  aggregation, and in v2 also from ``relates_parties``. The validator enforces that an import
  names exactly one source and that a party relation names at least two, so neither can be
  mislabelled as the kind whose bookkeeping is cheapest.
- ``rule`` is the condition under which the derivation holds. "aggregates_over three items" does
  not say what makes the aggregate true; the rule does.
- ``evidence_required`` must meet or exceed the target's ``minimum_support``. A map requiring one
  support for an abstraction with a floor of three would quietly lower the floor.

The v2 map is larger than v1's twenty entries mostly because there is more L1 to draw on, but two
edges are the substance of the version: ``m:abstraction.relationship`` is the first
``relates_parties`` edge and is what makes the relationship layer derived rather than declared,
and ``m:abstraction.conditional_commitment`` is what connects the suspended-commitment machinery
at L1 to the thing that outlives a session.
"""

from __future__ import annotations

from typing import Final

from .l1_content import O_L1_VERSION
from .l2_content import O_L2_VERSION
from .models import DerivationEntry, DerivationKind, MappingFreeze

M_VERSION: Final[str] = "2.0.0"


def _entry(
    map_id: str,
    kind: DerivationKind,
    sources: tuple[str, ...],
    target: str,
    rule: str,
    *,
    evidence_required: int = 1,
) -> DerivationEntry:
    return DerivationEntry(
        map_id=map_id,
        kind=kind,
        l1_source_ids=tuple(sorted(sources)),
        l2_target_id=target,
        rule=rule,
        evidence_required=evidence_required,
    )


_ENTRIES: Final[tuple[DerivationEntry, ...]] = (
    _entry(
        "m:abstraction.carried_constraint",
        DerivationKind.ABSTRACTS_FROM,
        ("l1:preference.threshold", "l1:role.constraint_on", "l1:state.capability_constraint"),
        "l2:abstraction.carried_constraint",
        "a restriction stated for one sub-goal is carried to a later one when the subject is the "
        "same and neither has been retracted; two occurrences are required because one is just a "
        "restriction",
        evidence_required=2,
    ),
    _entry(
        "m:abstraction.conditional_commitment",
        DerivationKind.ABSTRACTS_FROM,
        (
            "l1:role.trigger",
            "l1:state.suspended_commitment",
            "l1:task.conditional_intention",
        ),
        "l2:abstraction.conditional_commitment",
        "a suspended commitment becomes a cross-session conditional when its trigger has been "
        "neither observed to hold nor settled false by the end of the session in which it was "
        "stated; the trigger role is what the watch pattern reads",
    ),
    _entry(
        "m:abstraction.habit",
        DerivationKind.AGGREGATES_OVER,
        (
            "l1:event.media_consumption",
            "l1:predicate.consume_media",
            "l1:qualifier.frequency",
            "l1:time.recurring",
        ),
        "l2:abstraction.habit",
        "three or more occurrences of the same behaviour by the same subject, and a frequency "
        "qualifier of habitual or stronger. Both conditions, not either: three occurrences with a "
        "frequency of occasional describes something the subject does rarely and often",
        evidence_required=3,
    ),
    _entry(
        "m:abstraction.preference_profile",
        DerivationKind.AGGREGATES_OVER,
        (
            "l1:preference.affinity",
            "l1:preference.avoidance",
            "l1:preference.comparative",
            "l1:qualifier.strength",
        ),
        "l2:abstraction.preference_profile",
        "two or more affinity, avoidance or comparative observations by one subject in one area, "
        "ordered by their strength qualifiers. The ordering is what makes it a profile rather "
        "than a list, which is why the strength dimension is a source and not a decoration",
        evidence_required=2,
    ),
    _entry(
        "m:abstraction.project",
        DerivationKind.AGGREGATES_OVER,
        ("l1:task.declared_intention", "l1:task.outstanding_requirement"),
        "l2:abstraction.project",
        "two or more declared intentions or outstanding requirements that share a subject and "
        "advance one stated aim, where completing any one of them leaves the others outstanding",
        evidence_required=2,
    ),
    _entry(
        "m:abstraction.relationship",
        DerivationKind.RELATES_PARTIES,
        ("l1:event.first_encounter", "l1:role.beneficiary", "l1:role.holder"),
        "l2:abstraction.relationship",
        "a tie is admitted when an observation places another party in the beneficiary or holder "
        "position relative to the subject and the family of the tie is stated; the first-encounter "
        "event dates it when present, and its absence leaves the tie undated rather than unheld",
    ),
    _entry(
        "m:abstraction.standing_condition",
        DerivationKind.ABSTRACTS_FROM,
        ("l1:preference.avoidance", "l1:state.capability_constraint"),
        "l2:abstraction.standing_condition",
        "a capability constraint or causal avoidance becomes standing when it is stated without a "
        "time qualifier or with an unspecified one, i.e. the subject presents it as simply true "
        "of them rather than true now",
    ),
    _entry(
        "m:abstraction.task",
        DerivationKind.IMPORT_AS,
        ("l1:task.outstanding_requirement",),
        "l2:abstraction.task",
        "one outstanding requirement becomes a tracked task when it acquires a lifecycle, which "
        "is the only thing the L2 side adds; the sense is unchanged",
    ),
    _entry(
        "m:abstraction.value_history",
        DerivationKind.AGGREGATES_OVER,
        ("l1:qualifier.assertion_standing", "l1:standing.superseded"),
        "l2:abstraction.value_history",
        "two or more assertions about the same attribute of the same subject where at least one "
        "is superseded; the series is ordered by assertion time and the last unsuperseded value "
        "is the current one",
        evidence_required=2,
    ),
    _entry(
        "m:lift.evidence_partial_support",
        DerivationKind.QUALIFIER_LIFT,
        ("l1:polarity.indeterminate", "l1:qualifier.assertion_standing"),
        "l2:evidence.partial_support_marked",
        "an abstraction with fewer supports than its declared minimum is marked partial rather "
        "than withheld or asserted, which is the lift of indeterminacy from a single assertion to "
        "an aggregate",
    ),
    _entry(
        "m:evidence.source_status_preserved",
        DerivationKind.QUALIFIER_LIFT,
        (
            "l1:qualifier.source_status",
            "l1:source_status.derived",
            "l1:source_status.user_reported",
        ),
        "l2:evidence.source_status_preserved",
        "an aggregate takes the weakest source status among its supports; a set of user reports "
        "yields a user-reported or derived aggregate and never a tool-observed one, so the lift "
        "is a minimum rather than a merge",
    ),
    _entry(
        "m:lift.evidence_supports_addressable",
        DerivationKind.IMPORT_AS,
        ("l1:qualifier.source_status",),
        "l2:evidence.supports_addressable",
        "each support must retain the source status it was observed with, which is what makes it "
        "individually addressable rather than absorbed into a count",
    ),
    _entry(
        "m:lift.lifecycle_achieved",
        DerivationKind.QUALIFIER_LIFT,
        ("l1:event.objective_achieved", "l1:standing.current"),
        "l2:lifecycle.achieved",
        "an abstraction is achieved when an objective-achieved event names its aim and that event "
        "is the current standing assertion about it",
    ),
    _entry(
        "m:lift.lifecycle_condition_failed",
        DerivationKind.QUALIFIER_LIFT,
        ("l1:event.attempt_failed", "l1:polarity.denied", "l1:role.trigger"),
        "l2:lifecycle.condition_failed",
        "a conditional item fails when its trigger is observed with denied polarity, which is "
        "distinct from the item lapsing: the condition was reached and did not hold",
    ),
    _entry(
        "m:lift.lifecycle_dormant",
        DerivationKind.QUALIFIER_LIFT,
        ("l1:standing.current", "l1:time.unspecified"),
        "l2:lifecycle.dormant",
        "an abstraction whose latest assertion still stands but carries no recent observation is "
        "dormant rather than lapsed; the unspecified-time value is what marks that no restatement "
        "was expected, so silence is not evidence of ending",
    ),
    _entry(
        "m:lift.lifecycle_lapsed",
        DerivationKind.QUALIFIER_LIFT,
        ("l1:standing.superseded", "l1:task.abandoned_intention"),
        "l2:lifecycle.lapsed",
        "an abstraction lapses when its supports are superseded or abandoned without any "
        "objective-achieved event, i.e. it stopped progressing rather than closing",
    ),
    _entry(
        "m:lift.lifecycle_open",
        DerivationKind.IMPORT_AS,
        ("l1:standing.current",),
        "l2:lifecycle.open",
        "an abstraction is open while its supports are the current standing assertions about it",
    ),
    _entry(
        "m:lift.lifecycle_superseded",
        DerivationKind.IMPORT_AS,
        ("l1:standing.superseded",),
        "l2:lifecycle.superseded_by_revision",
        "an abstraction is superseded when a later abstraction over the same scope displaces it, "
        "which is the aggregate reading of the atomic standing value",
    ),
    _entry(
        "m:import.pattern_constraint_union",
        DerivationKind.ABSTRACTS_FROM,
        ("l1:preference.threshold", "l1:role.constraint_on"),
        "l2:pattern.constraint_union",
        "several restrictions on one scope combine into a single restriction satisfying all of "
        "them; an empty result means the restrictions conflict and is not a failure to compute",
    ),
    _entry(
        "m:import.pattern_goal_decomposition",
        DerivationKind.ABSTRACTS_FROM,
        ("l1:task.declared_intention", "l1:task.outstanding_requirement"),
        "l2:pattern.goal_decomposition",
        "an intention decomposes when its outstanding requirements are individually completable "
        "and jointly sufficient for it",
    ),
    _entry(
        "m:import.pattern_recurrence_count",
        DerivationKind.ABSTRACTS_FROM,
        ("l1:qualifier.frequency", "l1:time.recurring"),
        "l2:pattern.recurrence_count",
        "counts distinct occasions rather than mentions, so one behaviour described three times "
        "in one session counts once; the frequency qualifier is what distinguishes a rate claim "
        "from a tally",
    ),
    _entry(
        "m:import.pattern_temporal_series",
        DerivationKind.ABSTRACTS_FROM,
        ("l1:qualifier.time", "l1:standing.superseded"),
        "l2:pattern.temporal_series",
        "orders observations by assertion time and treats the latest unsuperseded one as current; "
        "ties are unresolved rather than broken arbitrarily",
    ),
    _entry(
        "m:import.pattern_trigger_watch",
        DerivationKind.ABSTRACTS_FROM,
        ("l1:predicate.suspend_on_condition", "l1:role.trigger"),
        "l2:pattern.trigger_watch",
        "holds an item unresolved until its trigger is observed to hold or to fail; a watch that "
        "is never resolved stays open, which is why this pattern's absence of a result is not an "
        "error condition",
    ),
    _entry(
        "m:relation.friendship",
        DerivationKind.RELATES_PARTIES,
        ("l1:event.first_encounter", "l1:role.beneficiary", "l1:role.holder"),
        "l2:relation.friendship",
        "a voluntary non-kin non-romantic tie, symmetric, so an observation from either party's "
        "side supports it; degree comes from the strength qualifier rather than from a separate "
        "close-friend type",
    ),
    _entry(
        "m:relation.kin_descent",
        DerivationKind.RELATES_PARTIES,
        ("l1:role.beneficiary", "l1:role.holder"),
        "l2:relation.kin_descent",
        "a descent tie, asymmetric, so the party positions are not interchangeable and a mention "
        "from one side does not license the mirrored claim; once held it does not lapse",
    ),
    _entry(
        "m:relation.kin_lateral",
        DerivationKind.RELATES_PARTIES,
        ("l1:role.beneficiary", "l1:role.holder"),
        "l2:relation.kin_lateral",
        "a same-generation kin tie, symmetric, so either party's mention supports the same "
        "relationship; like descent it does not lapse",
    ),
    _entry(
        "m:relation.partnership",
        DerivationKind.RELATES_PARTIES,
        ("l1:event.life_transition", "l1:role.beneficiary", "l1:role.holder"),
        "l2:relation.partnership",
        "a romantic or marital tie, symmetric while it holds; the life-transition event is what "
        "records its beginning or ending, so an ending supersedes the tie rather than "
        "contradicting the statement that made it",
    ),
    _entry(
        "m:import.role_first_party",
        DerivationKind.IMPORT_AS,
        ("l1:role.holder",),
        "l2:role.first_party",
        "the side a relationship is stated from is the holder position of the observation that "
        "stated it, which is why all persona relationship mentions have the speaker here",
    ),
    _entry(
        "m:import.role_scope",
        DerivationKind.IMPORT_AS,
        ("l1:role.constraint_on",),
        "l2:role.scope",
        "what an abstraction ranges over is the aggregate reading of what a single restriction "
        "restricts",
    ),
    _entry(
        "m:import.role_second_party",
        DerivationKind.IMPORT_AS,
        ("l1:role.beneficiary",),
        "l2:role.second_party",
        "the counterpart position is the beneficiary of the observation that named it, held as a "
        "filled position and never as the person filling it",
    ),
    _entry(
        "m:import.role_subject",
        DerivationKind.IMPORT_AS,
        ("l1:role.holder",),
        "l2:role.subject",
        "the party an abstraction is about is the holder of its supporting observations; this is "
        "a separate id because an abstraction may aggregate observations made by several "
        "speakers about one subject, which no single holder position expresses",
    ),
    _entry(
        "m:import.role_tracked_attribute",
        DerivationKind.IMPORT_AS,
        ("l1:role.attribute_bearer",),
        "l2:role.tracked_attribute",
        "the attribute a history follows is the position an atomic attribute was predicated of, "
        "lifted from one observation to the series",
    ),
)


def build_m_l1_to_l2() -> MappingFreeze:
    """Assemble M_L1_to_L2 v2, sorted by map id because the freeze hash depends on the order."""
    return MappingFreeze(
        version=M_VERSION,
        l1_version=O_L1_VERSION,
        l2_version=O_L2_VERSION,
        entries=tuple(sorted(_ENTRIES, key=lambda entry: entry.map_id)),
    )
