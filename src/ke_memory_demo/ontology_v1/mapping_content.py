"""M_L1_to_L2: every cross-layer derivation, stated once and versioned on its own.

This unit exists because the two layers share no vocabulary. Without it, O_L2 would either
have to repeat L1 ids inside its own items -- making the layers one vocabulary in practice
whatever the documentation said -- or leave the connection implicit, in which case an
abstraction's derivation would be whatever the implementation happened to do.

Three things are recorded per edge and none of them is decoration:

- ``kind`` distinguishes an import (one L1 sense reused under an L2 id) from a genuine
  aggregation. The validator enforces that an import names exactly one source, so an
  aggregation cannot be mislabelled as the one kind that needs no aggregation rule.
- ``rule`` is the condition under which the derivation holds. "aggregates_over three role
  items" does not say what makes the aggregate true; the rule does, and it is what an
  executable subset would implement.
- ``evidence_required`` must meet or exceed the target's ``minimum_support``, checked in
  :meth:`MappingFreeze.validate_against`. A map that required one support for an abstraction
  declaring a floor of three would quietly lower the floor.

Nine of the sixteen edges are ``import_as``, and every one is a place where a reviewer
should ask whether the L2 item earns a separate id. They are kept because the L2 side means
something different in each case: ``l2:role.subject`` is not ``l1:role.holder`` when an
abstraction is built from observations by several speakers, which is the normal case in a
multi-session corpus.
"""

from __future__ import annotations

from typing import Final

from .l1_content import O_L1_VERSION
from .l2_content import O_L2_VERSION
from .models import DerivationEntry, DerivationKind, MappingFreeze

M_VERSION: Final[str] = "1.0.0"


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
        (
            "l1:preference.threshold",
            "l1:state.capability_constraint",
            "l1:role.constraint_on",
        ),
        "l2:abstraction.carried_constraint",
        "a restriction observed once, plus a later aim in whose statement it does not recur "
        "and whose satisfaction it still bears on; the scope must be derivable from the "
        "later aim and not assumed to be unbounded",
        evidence_required=2,
    ),
    _entry(
        "m:abstraction.habit",
        DerivationKind.AGGREGATES_OVER,
        ("l1:event.media_consumption", "l1:qualifier.time", "l1:time.recurring"),
        "l2:abstraction.habit",
        "three or more event observations of one type by one subject on occasions "
        "distinguishable by their l1:qualifier.time value; an l1:time.recurring assertion is "
        "a claim about a habit and counts as one observation, never as three",
        evidence_required=3,
    ),
    _entry(
        "m:abstraction.preference_profile",
        DerivationKind.AGGREGATES_OVER,
        (
            "l1:preference.affinity",
            "l1:preference.comparative",
            "l1:preference.threshold",
            "l1:qualifier.polarity",
        ),
        "l2:abstraction.preference_profile",
        "two or more preference observations sharing a holder, retaining both polarities and "
        "any comparative ordering; a comparative may not be synthesised from two affinities, "
        "so an ordering enters the profile only if a comparative was observed",
        evidence_required=2,
    ),
    _entry(
        "m:abstraction.project",
        DerivationKind.AGGREGATES_OVER,
        ("l1:task.declared_intention", "l1:task.outstanding_requirement"),
        "l2:abstraction.project",
        "two or more declared intentions by one agent whose completions serve one outcome "
        "neither achieves alone; adjacency in time is not sufficient, since the shared "
        "outcome is what separates a project from two unrelated aims stated together",
        evidence_required=2,
    ),
    _entry(
        "m:abstraction.standing_condition",
        DerivationKind.ABSTRACTS_FROM,
        ("l1:state.circumstance", "l1:state.possession"),
        "l2:abstraction.standing_condition",
        "one circumstance observation with no later observation ending it; the continuation "
        "is inferred and the instance must stay distinguishable from a re-confirmed one",
    ),
    _entry(
        "m:abstraction.task",
        DerivationKind.AGGREGATES_OVER,
        (
            "l1:event.commitment_made",
            "l1:task.abandoned_intention",
            "l1:task.declared_intention",
            "l1:task.outstanding_requirement",
        ),
        "l2:abstraction.task",
        "a declared intention plus at least one later observation bearing on whether it "
        "closed; the closing observation may be a commitment, an abandonment, or a "
        "requirement being met, and its absence yields l2:lifecycle.lapsed rather than a "
        "guess at the outcome",
        evidence_required=2,
    ),
    _entry(
        "m:abstraction.value_history",
        DerivationKind.AGGREGATES_OVER,
        (
            "l1:qualifier.assertion_standing",
            "l1:standing.current",
            "l1:standing.superseded",
            "l1:state.circumstance",
        ),
        "l2:abstraction.value_history",
        "two or more observations of one attribute of one subject bearing different values, "
        "ordered by assertion time, with exactly one carrying l1:standing.current; the "
        "superseded values stay addressable rather than being overwritten",
        evidence_required=2,
    ),
)


# Imports and lifts. Kept in a separate tuple from the abstraction derivations because they
# are reviewed differently: an abstraction derivation is judged on whether its rule is
# sound, an import on whether the L2 id is justified at all.
#
# The pattern imports carry evidence_required matching the pattern's own support floor. That
# is not bookkeeping: a temporal series with one observation is not a series, so importing
# the L1 dimension that grounds it cannot claim to be satisfied by a single observation.
_IMPORTS: Final[tuple[DerivationEntry, ...]] = (
    _entry(
        "m:import.pattern_constraint_union",
        DerivationKind.IMPORT_AS,
        ("l1:role.constraint_on",),
        "l2:pattern.constraint_union",
        "the L1 position a restriction restricts becomes the key a constraint union groups "
        "by; the pattern adds accumulation and conflict retention, which the position lacks",
    ),
    _entry(
        "m:import.pattern_goal_decomposition",
        DerivationKind.IMPORT_AS,
        ("l1:task.declared_intention",),
        "l2:pattern.goal_decomposition",
        "the L1 intention is the unit being decomposed; the pattern adds the shared-outcome "
        "requirement, which a single intention cannot state about itself",
        evidence_required=2,
    ),
    _entry(
        "m:import.pattern_recurrence_count",
        DerivationKind.IMPORT_AS,
        ("l1:time.recurring",),
        "l2:pattern.recurrence_count",
        "the L1 value asserts recurrence in one utterance; the pattern counts occasions "
        "instead, so the import is a change of evidentiary basis rather than a rename",
        evidence_required=2,
    ),
    _entry(
        "m:import.pattern_temporal_series",
        DerivationKind.IMPORT_AS,
        ("l1:qualifier.assertion_standing",),
        "l2:pattern.temporal_series",
        "the L1 dimension marks one assertion as current or superseded; the pattern keeps "
        "the whole ordered series, which no single assertion's standing expresses",
        evidence_required=2,
    ),
    _entry(
        "m:import.role_subject",
        DerivationKind.IMPORT_AS,
        ("l1:role.holder",),
        "l2:role.subject",
        "the L1 holder of one assertion becomes the L2 subject an abstraction is about; they "
        "diverge when supports come from several speakers, so the ids stay distinct",
    ),
    _entry(
        "m:import.role_tracked_attribute",
        DerivationKind.IMPORT_AS,
        ("l1:role.attribute_bearer",),
        "l2:role.tracked_attribute",
        "the L1 bearer position identifies which attribute an observation is about, and the "
        "L2 role fixes that attribute as the index of one history",
    ),
    _entry(
        "m:import.role_scope",
        DerivationKind.IMPORT_AS,
        ("l1:role.constraint_on",),
        "l2:role.scope",
        "the L1 position a restriction applies to is narrowed to one assertion; the L2 role "
        "records how much further it carries, which is not information any L1 item holds",
    ),
    _entry(
        "m:lift.evidence_partial_support",
        DerivationKind.QUALIFIER_LIFT,
        ("l1:source_status.derived", "l1:standing.current"),
        "l2:evidence.partial_support_marked",
        "an abstraction is derived rather than observed, so its source status lifts to "
        "derived and its support completeness must be stated alongside it",
    ),
    _entry(
        "m:lift.evidence_supports_addressable",
        DerivationKind.QUALIFIER_LIFT,
        ("l1:source_status.derived",),
        "l2:evidence.supports_addressable",
        "a derived assertion has no independent source of its own, so the observations it "
        "was derived from are the only thing that can stand as its evidence",
    ),
    _entry(
        "m:lift.lifecycle_achieved",
        DerivationKind.QUALIFIER_LIFT,
        ("l1:event.commitment_made", "l1:polarity.affirmed"),
        "l2:lifecycle.achieved",
        "an affirmed commitment event closes the aim it fulfils, so the L1 outcome lifts to "
        "the abstraction's status; an l1:event.attempt_failed must not lift here",
    ),
    _entry(
        "m:lift.lifecycle_lapsed",
        DerivationKind.QUALIFIER_LIFT,
        ("l1:polarity.indeterminate", "l1:time.unspecified"),
        "l2:lifecycle.lapsed",
        "when no observation bears on the outcome, the status is unknown rather than failed; "
        "this edge exists so that absence of evidence has somewhere to lift to",
    ),
    _entry(
        "m:lift.lifecycle_open",
        DerivationKind.QUALIFIER_LIFT,
        ("l1:modality.intended", "l1:task.outstanding_requirement"),
        "l2:lifecycle.open",
        "an intention with a requirement still outstanding is live, so intent modality plus "
        "an unmet requirement lift to an open status",
    ),
    _entry(
        "m:lift.lifecycle_superseded",
        DerivationKind.QUALIFIER_LIFT,
        ("l1:standing.superseded",),
        "l2:lifecycle.superseded_by_revision",
        "an assertion superseded by a revised value lifts to an abstraction replaced by a "
        "revised version of itself, which is neither achievement nor abandonment",
    ),
)


def build_m_l1_to_l2() -> MappingFreeze:
    """Assemble M_L1_to_L2, sorted by map id."""
    entries = (*_ENTRIES, *_IMPORTS)
    return MappingFreeze(
        version=M_VERSION,
        l1_version=O_L1_VERSION,
        l2_version=O_L2_VERSION,
        entries=tuple(sorted(entries, key=lambda entry: entry.map_id)),
    )
