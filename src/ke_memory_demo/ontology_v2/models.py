"""Freeze models for foundation ontology v2: the v1 shape plus what supersession needs.

v1's structural guarantees are kept verbatim in spirit -- three independently hashed units,
no shared vocabulary between the layers, no field anywhere that could hold an Individual --
because none of them failed. What v2 adds is the machinery its new content requires:

- :class:`SourceKind` gains ``wordnet``, ``propbank`` and ``schemaorg``. v1 could not cite
  them and said so; a v2 item that claims PropBank evidence must be able to *name* PropBank
  in a typed field rather than in prose that no validator reads.
- :class:`ExternalGrounding` is the new discipline. A predicate sense that says "PropBank
  settled this" must carry the roleset id, so a reviewer can open ``prefer.01`` and check.
  v1's ``sources_unconsulted`` note existed precisely because there was nothing to put here.
- :class:`SupersessionRecord` and :class:`SupersessionFreeze` make "v2 supersedes v1" a
  checked claim: every v1 id is accounted for exactly once, as carried / revised / retired.
- ``ranks_above`` plus :func:`_validate_total_order` are what let preference strength be an
  *ordered* vocabulary rather than four unrelated qualifier values. v1 refused a strength scale
  because an invented ordinal is worse than none; the ordering is admissible only because the
  bands are lexically attested, and the validator forces them to form a chain rather than a
  partial order -- an ordinal with two incomparable values cannot be evaluated.

The two things v2 deliberately does not relax: ``individual`` is still absent from
:class:`OntologyRoleKind`, and there is still no ``value``/``filler``/``mention`` field. A
broader ontology is a larger set of types, not a set of types that can hold instances.
"""

from __future__ import annotations

import hashlib
import re
from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ke_memory_demo.core.json import canonical_json

NonEmptyString = Annotated[str, Field(min_length=1)]
PositiveInt = Annotated[int, Field(ge=1)]
NonNegativeInt = Annotated[int, Field(ge=0)]

L1_NAMESPACE: Final[str] = "l1:"
L2_NAMESPACE: Final[str] = "l2:"
MAP_NAMESPACE: Final[str] = "m:"

# Ids are lowercase dotted paths. Enforced because an id is what a mapper is scored against:
# an id that can carry arbitrary text can carry a surface form, and then "canonical id"
# stops naming anything stable.
_ID_BODY = re.compile(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+")

# Corpora whose questions and gold the ontology may not be derived from. A scan rather than
# a prose rule, because the discovery-split restriction is the one constraint an author
# cannot self-certify.
FORBIDDEN_CORPUS_TOKENS: Final[frozenset[str]] = frozenset(
    {"longmemeval", "locomo", "beam", "msc_session", "regression_slice", "question_id"}
)


class OntologyFreezeError(ValueError):
    """A freeze unit was built with content it must not carry."""


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def sha256_of(unit: BaseModel) -> str:
    """SHA-256 over one unit's canonical JSON, and nothing else's."""
    return hashlib.sha256(canonical_json(unit)).hexdigest()


def _require_id(value: str, namespace: str, what: str) -> str:
    if not value.startswith(namespace):
        raise OntologyFreezeError(f"{what} id {value!r} must start with {namespace!r}")
    if not _ID_BODY.fullmatch(value[len(namespace) :]):
        raise OntologyFreezeError(
            f"{what} id {value!r} must be a dotted lowercase path after {namespace!r}, "
            "so an id cannot smuggle a surface form"
        )
    return value


def _reject_foreign_namespace(unit: BaseModel, foreign: str, what: str) -> None:
    """Fail if the other layer's namespace appears anywhere in this item.

    Checked over the serialized item rather than over declared reference fields: a relation
    target, a constraint expression and a free-text sense are all places an id has escaped a
    typed field before, and the no-shared-vocabulary rule means there is no such place.
    """
    if foreign.encode() in canonical_json(unit):
        raise OntologyFreezeError(
            f"{what} references the {foreign!r} namespace; the two layers do not share a "
            "vocabulary, so a cross-layer reference must be declared in M_L1_to_L2"
        )


class OntologyRoleKind(StrEnum):
    """What kind of ontology position an item occupies.

    ``individual`` stays absent for the same reason as in v1: ``domain.OntologyRole`` has it,
    and copying that vocabulary would admit what the plan excludes outright.
    """

    CONCEPT = "concept"
    OPERATOR = "operator"
    ROLE = "role"
    VOCABULARY_VALUE = "vocabulary_value"


class L1ItemType(StrEnum):
    """The atomic-layer type taxonomy, unchanged from v1.

    Held stable on purpose: v2 is a breadth increase, and if the type taxonomy also moved,
    no reviewer could tell whether a v1 item was revised or reclassified.
    """

    EVENT_TYPE = "event_type"
    STATE_TYPE = "state_type"
    PREFERENCE_TYPE = "preference_type"
    TASK_TYPE = "task_type"
    ATTRIBUTE_TYPE = "attribute_type"
    ROLE = "role"
    PREDICATE_SENSE = "predicate_sense"
    QUALIFIER_VALUE = "qualifier_value"
    QUALIFIER_DIMENSION = "qualifier_dimension"


class L2ItemType(StrEnum):
    """The abstraction-layer type taxonomy.

    ``RELATION_TYPE`` is the one addition. v1 recorded social relationship as its largest
    known O_L2 gap and had no type for it: a relationship is not an aggregation over
    observations of one subject, it is a typed edge between two parties, and forcing it into
    ``ABSTRACTION_TYPE`` would have made ``minimum_support`` mean something it does not.
    """

    ABSTRACTION_TYPE = "abstraction_type"
    AGGREGATION_PATTERN = "aggregation_pattern"
    LIFECYCLE_STATE = "lifecycle_state"
    EVIDENCE_CONSTRAINT = "evidence_constraint"
    RELATION_TYPE = "relation_type"


class RelationKind(StrEnum):
    """The relation inventory, closed on purpose.

    An open relation vocabulary makes a hash meaningless as a contract: two ontologies with
    the same items and freely-invented edge labels would be incomparable.

    v2 adds three, each because a v1 gap needed exactly one edge it could not draw:
    ``triggered_by`` for conditional commitment, ``ranks_above`` for the preference-strength
    ordering, and ``holds_between`` for a relationship's two party positions.
    """

    IS_A = "is_a"
    HAS_ROLE = "has_role"
    RANGE_IS = "range_is"
    QUALIFIED_BY = "qualified_by"
    OPPOSITE_OF = "opposite_of"
    SPECIALIZES_SENSE = "specializes_sense"
    AGGREGATES = "aggregates"
    LIFECYCLE_OF = "lifecycle_of"
    CONSTRAINS = "constrains"
    TRIGGERED_BY = "triggered_by"
    RANKS_ABOVE = "ranks_above"
    HOLDS_BETWEEN = "holds_between"


class SourceKind(StrEnum):
    """Where a candidate came from, so provenance is a field rather than a claim.

    The three published sources are first-class here. In v1 they could only appear in a prose
    note saying they were unavailable, which is why v1's predicate senses had to be labelled
    corpus-clustered and could claim no synset or roleset id.
    """

    WORDNET = "wordnet"
    PROPBANK = "propbank"
    SCHEMAORG = "schemaorg"
    SGD_SCHEMA = "sgd_schema"
    SGD_DIALOGUE_ACTS = "sgd_dialogue_acts"
    SGD_STATE_DYNAMICS = "sgd_state_dynamics"
    TASKMASTER2_ANNOTATIONS = "taskmaster2_annotations"
    TAU_BENCH_TOOLS = "tau_bench_tools"
    TAU_BENCH_POLICY = "tau_bench_policy"
    MSC_PERSONAS = "msc_personas"
    REPOSITORY_VOCABULARY = "repository_vocabulary"
    DISCOVERY_GAP_SHAPE = "discovery_gap_shape"
    ONTOLOGY_V1_CARRIED = "ontology_v1_carried"
    AUTHORED_FOR_CLOSURE = "authored_for_closure"


# Sources that are external published resources rather than corpora observed by this project.
# Kept as a set so :class:`ExternalGrounding` can insist a grounding cites one of exactly
# these three, and cannot be used to dress a corpus count up as a literature citation.
EXTERNAL_SOURCES: Final[frozenset[SourceKind]] = frozenset(
    {SourceKind.WORDNET, SourceKind.PROPBANK, SourceKind.SCHEMAORG}
)

# Reference shapes, so "grounded in PropBank" is checkable rather than decorative.
# WordNet:   pos#offset, exactly as ontology_sources.wordnet emits it.
# PropBank:  lemma.NN roleset id.
# schema.org: the term id, class or property, as it appears in the JSON-LD graph.
_REFERENCE_SHAPES: Final[dict[SourceKind, re.Pattern[str]]] = {
    SourceKind.WORDNET: re.compile(r"[nvasr]#\d{8}"),
    SourceKind.PROPBANK: re.compile(r"[A-Za-z0-9_'\-]+\.\d{2}"),
    SourceKind.SCHEMAORG: re.compile(r"schema:[A-Za-z][A-Za-z0-9_]*"),
}


class ExternalGrounding(_Frozen):
    """One citation into a frozen external source, at an id a reviewer can look up.

    This is the field v1 had no way to fill. ``role_hint`` is optional and only meaningful
    for PropBank: it records *which* argument position was taken, because citing
    ``prefer.01`` for a comparative role is only checkable if it also says ARG2.
    """

    source: SourceKind
    reference: NonEmptyString
    # PropBank roleset names are often a single short verb: decide.01 is named exactly "decide",
    # six characters. A min_length of 8 rejected real source data, so the floor only excludes an
    # empty or near-empty gloss rather than imposing a prose length the sources do not have.
    gloss: Annotated[str, Field(min_length=3)]
    role_hint: NonEmptyString | None = None

    @model_validator(mode="after")
    def _validate(self) -> ExternalGrounding:
        if self.source not in EXTERNAL_SOURCES:
            raise OntologyFreezeError(
                f"{self.source.value} is a build corpus, not a published source; a grounding "
                "cites WordNet, PropBank or schema.org, and corpus evidence belongs in "
                "Provenance.evidence"
            )
        shape = _REFERENCE_SHAPES[self.source]
        if not shape.fullmatch(self.reference):
            raise OntologyFreezeError(
                f"{self.reference!r} is not a {self.source.value} reference; the id shape is "
                f"{shape.pattern}, and an unresolvable citation is worse than none"
            )
        if self.role_hint is not None and self.source is not SourceKind.PROPBANK:
            raise OntologyFreezeError(
                f"{self.reference} carries a role hint but only PropBank has numbered roles"
            )
        return self


class Relation(_Frozen):
    """One typed edge. ``target_id`` is validated by the owning unit, not here.

    The owning unit knows which namespace is legal for its own targets; a relation alone does
    not, and guessing would let an L2 item declare an L1 target.
    """

    kind: RelationKind
    target_id: NonEmptyString


class RoleSlot(_Frozen):
    """One argument position of a predicate sense or event type.

    ``role_id`` points at a role item rather than naming the role inline, so two event types
    sharing an argument position share the position and not two strings that happen to match.
    """

    role_id: NonEmptyString
    is_required: bool = False
    # A range separates categorical positions (a closed value set) from open ones, which are
    # different mapping problems: SGD's schema draws the same line for its slots.
    range_id: NonEmptyString | None = None


class Constraint(_Frozen):
    """A checkable statement about an item, expressed so a reader can test it.

    ``expression`` is still prose in a fixed shape, and still does not count toward any
    executable-constraint metric. v2 does not ship a DSL either: an unevaluated DSL claims
    enforcement the freeze cannot back, and that verdict did not change because the source
    debt was paid.
    """

    kind: NonEmptyString
    expression: NonEmptyString


class Provenance(_Frozen):
    """Why this item exists, tied to something a reviewer can go and look at.

    ``evidence`` must cite an observable -- a slot name, an act label, a measured count, a
    roleset id. The field exists to make "seemed necessary" visibly absent.
    """

    source: SourceKind
    evidence: NonEmptyString


class OntologyItem(_Frozen):
    """Fields common to both layers, including the ones deliberately not present.

    There is no ``value``, ``filler``, ``example``, ``surface_form`` or ``mention`` field
    anywhere in this hierarchy, exactly as in v1. That absence is what excludes Individuals
    and benchmark facts: an item can say what an attribute type *is* and cannot say what any
    particular subject's value for it *was*. Widening the ontology does not widen this.

    ``grounding`` is new and is where the source debt is actually visible per item: an item
    that claims a published source in its provenance must cite a resolvable id here, so
    "PropBank settled the role set" can be checked instead of believed.
    """

    id: NonEmptyString
    sense: Annotated[str, Field(min_length=12)]
    aliases: tuple[NonEmptyString, ...] = ()
    role_kind: OntologyRoleKind
    relations: tuple[Relation, ...] = ()
    roles: tuple[RoleSlot, ...] = ()
    constraints: tuple[Constraint, ...] = ()
    provenance: tuple[Provenance, ...] = Field(min_length=1)
    grounding: tuple[ExternalGrounding, ...] = ()

    @model_validator(mode="after")
    def _validate_item(self) -> OntologyItem:
        if len(set(self.aliases)) != len(self.aliases):
            raise OntologyFreezeError(f"{self.id} repeats an alias")
        # An alias equal to the id inflates alias counts without adding a surface form the
        # mapper could not already match.
        if self.id in self.aliases:
            raise OntologyFreezeError(f"{self.id} lists its own id as an alias")
        relation_keys = [(r.kind, r.target_id) for r in self.relations]
        if len(set(relation_keys)) != len(relation_keys):
            raise OntologyFreezeError(f"{self.id} repeats a relation")
        role_ids = [slot.role_id for slot in self.roles]
        if len(set(role_ids)) != len(role_ids):
            raise OntologyFreezeError(f"{self.id} binds the same role twice")
        references = [g.reference for g in self.grounding]
        if len(set(references)) != len(references):
            raise OntologyFreezeError(f"{self.id} cites the same external reference twice")
        lowered = " ".join((self.sense, *self.aliases)).lower()
        leaked = sorted(t for t in FORBIDDEN_CORPUS_TOKENS if t in lowered)
        if leaked:
            raise OntologyFreezeError(
                f"{self.id} names an evaluation corpus ({leaked}); candidates may come from "
                "the discovery split only as general gap shapes, never as corpus-specific text"
            )
        # The point of the whole v2 exercise: if an item says a published source justifies it,
        # the citation must be present. Otherwise v2 would repeat v1's situation while
        # claiming to have fixed it.
        claimed = {p.source for p in self.provenance} & EXTERNAL_SOURCES
        cited = {g.source for g in self.grounding}
        missing = sorted(s.value for s in claimed - cited)
        if missing:
            raise OntologyFreezeError(
                f"{self.id} claims {missing} in its provenance but cites no resolvable "
                "reference; an unverifiable source claim is what v2 exists to stop making"
            )
        return self


class L1Item(_Frozen):
    """One atomic-layer type. Ids and every reference stay inside ``l1:``."""

    item: OntologyItem
    item_type: L1ItemType

    @model_validator(mode="after")
    def _validate(self) -> L1Item:
        _require_id(self.item.id, L1_NAMESPACE, "L1 item")
        for relation in self.item.relations:
            _require_id(relation.target_id, L1_NAMESPACE, f"{self.item.id} relation target")
        for slot in self.item.roles:
            _require_id(slot.role_id, L1_NAMESPACE, f"{self.item.id} role")
            if slot.range_id is not None:
                _require_id(slot.range_id, L1_NAMESPACE, f"{self.item.id} role range")
        _reject_foreign_namespace(self.item, L2_NAMESPACE, f"L1 item {self.item.id}")
        # Role slots on a non-predicate item attach argument structure to the wrong kind of
        # thing, which silently changes what a mapper is expected to fill. Attribute types
        # keep their one position -- the bearer -- because leaving the bearer implicit is how
        # a value and its subject get conflated.
        if self.item.roles and self.item_type not in {
            L1ItemType.EVENT_TYPE,
            L1ItemType.PREDICATE_SENSE,
            L1ItemType.STATE_TYPE,
            L1ItemType.PREFERENCE_TYPE,
            L1ItemType.TASK_TYPE,
            L1ItemType.ATTRIBUTE_TYPE,
        }:
            raise OntologyFreezeError(
                f"{self.item.id} is a {self.item_type.value} and cannot carry role slots"
            )
        if self.item_type is L1ItemType.ROLE and self.item.role_kind is not OntologyRoleKind.ROLE:
            raise OntologyFreezeError(f"{self.item.id} is a role but its role_kind is not 'role'")
        # ranks_above is the ordering edge, and an ordering over anything but a closed value
        # vocabulary is not an ordering -- it is a claim about types that have no positions.
        if any(r.kind is RelationKind.RANKS_ABOVE for r in self.item.relations) and (
            self.item_type is not L1ItemType.QUALIFIER_VALUE
        ):
            raise OntologyFreezeError(
                f"{self.item.id} ranks above another item but is not a qualifier value; only a "
                "closed value vocabulary can carry a total order"
            )
        return self


class L2Item(_Frozen):
    """One abstraction-layer type. Ids and every reference stay inside ``l2:``.

    ``derives_from_l1`` is absent by design, as in v1: the derivation lives in M_L1_to_L2 so
    that changing which L1 items feed an abstraction moves the *map* hash, not the L2 hash.
    """

    item: OntologyItem
    item_type: L2ItemType
    # On the item because it says *that* the abstraction needs multiple supports, a property
    # of the type. *Which* supports is the map's business.
    minimum_support: PositiveInt = 1
    spans_sessions: bool = False

    @model_validator(mode="after")
    def _validate(self) -> L2Item:
        _require_id(self.item.id, L2_NAMESPACE, "L2 item")
        for relation in self.item.relations:
            _require_id(relation.target_id, L2_NAMESPACE, f"{self.item.id} relation target")
        for slot in self.item.roles:
            _require_id(slot.role_id, L2_NAMESPACE, f"{self.item.id} role")
            if slot.range_id is not None:
                _require_id(slot.range_id, L2_NAMESPACE, f"{self.item.id} role range")
        _reject_foreign_namespace(self.item, L1_NAMESPACE, f"L2 item {self.item.id}")
        # A relation type is an edge between two parties, so it is only well-formed if it says
        # which two positions it holds between. Without this the new type would be an
        # abstraction with a different label.
        if self.item_type is L2ItemType.RELATION_TYPE:
            parties = [r for r in self.item.relations if r.kind is RelationKind.HOLDS_BETWEEN]
            if len(parties) != 2:
                raise OntologyFreezeError(
                    f"{self.item.id} is a relation type with {len(parties)} party positions; a "
                    "relationship holds between exactly two, or it is an aggregation"
                )
        elif any(r.kind is RelationKind.HOLDS_BETWEEN for r in self.item.relations):
            raise OntologyFreezeError(
                f"{self.item.id} declares party positions but is not a relation type"
            )
        return self


def _validate_closure(ids: frozenset[str], items: tuple[L1Item, ...] | tuple[L2Item, ...]) -> None:
    """Every relation, role and range must resolve inside the same unit.

    A dangling target is worse than a missing item: the ontology looks like it has an ``is_a``
    hierarchy while the parent does not exist, so a consumer walking the graph gets a
    different taxonomy than the one the hash certifies.
    """
    dangling: list[str] = []
    for entry in items:
        inner = entry.item
        dangling.extend(
            f"{inner.id} -{r.kind.value}-> {r.target_id}"
            for r in inner.relations
            if r.target_id not in ids
        )
        for slot in inner.roles:
            if slot.role_id not in ids:
                dangling.append(f"{inner.id} role {slot.role_id}")
            if slot.range_id is not None and slot.range_id not in ids:
                dangling.append(f"{inner.id} range {slot.range_id}")
    if dangling:
        raise OntologyFreezeError(f"unresolved references within a freeze unit: {dangling[:6]}")


def _reject_alias_collisions(aliases_by_id: dict[str, tuple[str, ...]], unit: str) -> None:
    """One alias may not resolve to two items in the same unit.

    An ambiguous alias makes normalization non-deterministic: the mapper's answer would depend
    on iteration order, and the score would not be reproducible from the frozen artifact. This
    binds harder in v2 than in v1 -- WordNet supplies many more lemmas, and the temptation is
    to attach every one of them somewhere.
    """
    owners: dict[str, list[str]] = {}
    for item_id, aliases in aliases_by_id.items():
        for alias in aliases:
            owners.setdefault(alias.lower(), []).append(item_id)
    ambiguous = {a: sorted(o) for a, o in owners.items() if len(o) > 1}
    if ambiguous:
        raise OntologyFreezeError(
            f"{unit} has aliases claimed by more than one item, which would make "
            f"normalization order-dependent: {sorted(ambiguous.items())[:4]}"
        )


def _validate_total_order(items: tuple[L1Item, ...]) -> None:
    """``ranks_above`` must form a chain within each qualifier dimension, not a partial order.

    v1 refused a preference-strength scale because an invented ordinal is worse than none.
    An ordinal is only usable if it is total: if two strength values are mutually
    incomparable, "stronger than" cannot be evaluated and the scale is decoration. So each
    dimension's ranked values must form one path -- every value but the weakest ranks above
    exactly one other, and no cycle.
    """
    ranked: dict[str, str] = {}
    for entry in items:
        for relation in entry.item.relations:
            if relation.kind is RelationKind.RANKS_ABOVE:
                if entry.item.id in ranked:
                    raise OntologyFreezeError(
                        f"{entry.item.id} ranks above two values; a total order is a chain, so "
                        "each value names exactly one immediate inferior"
                    )
                ranked[entry.item.id] = relation.target_id
    below = set(ranked.values())
    contested = sorted(t for t in below if list(ranked.values()).count(t) > 1)
    if contested:
        raise OntologyFreezeError(f"two values both rank immediately above {contested}")
    for start in ranked:
        seen = {start}
        cursor: str | None = ranked.get(start)
        while cursor is not None:
            if cursor in seen:
                raise OntologyFreezeError(f"ranks_above cycle reached through {start}")
            seen.add(cursor)
            cursor = ranked.get(cursor)


class L1Freeze(_Frozen):
    """Freeze unit O_L1, hashed over itself alone."""

    unit_id: Literal["O_L1"] = "O_L1"
    version: NonEmptyString
    items: tuple[L1Item, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate(self) -> L1Freeze:
        ids = [entry.item.id for entry in self.items]
        if len(set(ids)) != len(ids):
            raise OntologyFreezeError("O_L1 contains duplicate ids")
        if ids != sorted(ids):
            raise OntologyFreezeError("O_L1 items must be sorted by id so the hash is stable")
        _validate_closure(frozenset(ids), self.items)
        _reject_alias_collisions(
            {entry.item.id: entry.item.aliases for entry in self.items}, "O_L1"
        )
        _validate_total_order(self.items)
        return self

    @property
    def digest(self) -> str:
        return sha256_of(self)

    @property
    def item_ids(self) -> frozenset[str]:
        return frozenset(entry.item.id for entry in self.items)

    def counts_by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for entry in self.items:
            counts[entry.item_type.value] = counts.get(entry.item_type.value, 0) + 1
        return dict(sorted(counts.items()))

    def grounded_ids(self) -> frozenset[str]:
        return frozenset(e.item.id for e in self.items if e.item.grounding)


class L2Freeze(_Frozen):
    """Freeze unit O_L2, hashed over itself alone."""

    unit_id: Literal["O_L2"] = "O_L2"
    version: NonEmptyString
    items: tuple[L2Item, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate(self) -> L2Freeze:
        ids = [entry.item.id for entry in self.items]
        if len(set(ids)) != len(ids):
            raise OntologyFreezeError("O_L2 contains duplicate ids")
        if ids != sorted(ids):
            raise OntologyFreezeError("O_L2 items must be sorted by id so the hash is stable")
        _validate_closure(frozenset(ids), self.items)
        _reject_alias_collisions(
            {entry.item.id: entry.item.aliases for entry in self.items}, "O_L2"
        )
        return self

    @property
    def digest(self) -> str:
        return sha256_of(self)

    @property
    def item_ids(self) -> frozenset[str]:
        return frozenset(entry.item.id for entry in self.items)

    def counts_by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for entry in self.items:
            counts[entry.item_type.value] = counts.get(entry.item_type.value, 0) + 1
        return dict(sorted(counts.items()))

    def grounded_ids(self) -> frozenset[str]:
        return frozenset(e.item.id for e in self.items if e.item.grounding)


class DerivationKind(StrEnum):
    """How an L2 item is obtained from L1 items.

    ``import_as`` is separated from the computed kinds because it is the only one reusing an L1
    sense unchanged, and therefore the only one where a reviewer should ask whether the L2 item
    earns its own id at all. ``relates_parties`` is added for v2: a relationship is derived from
    two party positions rather than aggregated over a series, and calling that an aggregation
    would put a support count on something that needs none.
    """

    IMPORT_AS = "import_as"
    AGGREGATES_OVER = "aggregates_over"
    ABSTRACTS_FROM = "abstracts_from"
    QUALIFIER_LIFT = "qualifier_lift"
    RELATES_PARTIES = "relates_parties"


class DerivationEntry(_Frozen):
    """One explicit L1-to-L2 edge. This is the only place both namespaces may meet."""

    map_id: NonEmptyString
    kind: DerivationKind
    l1_source_ids: tuple[NonEmptyString, ...] = Field(min_length=1)
    l2_target_id: NonEmptyString
    # Why a rule string: the plan wants the derivation explicit, and "aggregates_over" plus
    # three source ids does not say what makes the aggregate hold. This is the condition a
    # future executable subset would implement.
    rule: Annotated[str, Field(min_length=12)]
    evidence_required: NonNegativeInt = 1

    @model_validator(mode="after")
    def _validate(self) -> DerivationEntry:
        _require_id(self.map_id, MAP_NAMESPACE, "derivation")
        _require_id(self.l2_target_id, L2_NAMESPACE, f"{self.map_id} target")
        for source in self.l1_source_ids:
            _require_id(source, L1_NAMESPACE, f"{self.map_id} source")
        if len(set(self.l1_source_ids)) != len(self.l1_source_ids):
            raise OntologyFreezeError(f"{self.map_id} repeats a source id")
        if self.l1_source_ids != tuple(sorted(self.l1_source_ids)):
            raise OntologyFreezeError(f"{self.map_id} source ids must be sorted")
        # An import naming several sources is not an import; calling it one hides a real
        # aggregation behind the one kind that needs no aggregation rule.
        if self.kind is DerivationKind.IMPORT_AS and len(self.l1_source_ids) != 1:
            raise OntologyFreezeError(
                f"{self.map_id} imports from {len(self.l1_source_ids)} sources; an import "
                "carries exactly one, otherwise it is an aggregation"
            )
        if self.kind is DerivationKind.AGGREGATES_OVER and self.evidence_required < 1:
            raise OntologyFreezeError(f"{self.map_id} aggregates but requires no evidence")
        # A relationship needs both parties named on the L1 side, or the map does not in fact
        # say where the second party comes from.
        if self.kind is DerivationKind.RELATES_PARTIES and len(self.l1_source_ids) < 2:
            raise OntologyFreezeError(
                f"{self.map_id} relates parties but names {len(self.l1_source_ids)} L1 source; "
                "both party positions must be derived from something"
            )
        return self


class MappingFreeze(_Frozen):
    """Freeze unit M_L1_to_L2: every cross-layer edge, and nothing implicit.

    :meth:`validate_against` is what makes this a contract rather than a third list. It checks
    both directions: no edge may name an id that does not exist, and no L2 item that needs a
    derivation may exist without one.
    """

    unit_id: Literal["M_L1_to_L2"] = "M_L1_to_L2"
    version: NonEmptyString
    l1_version: NonEmptyString
    l2_version: NonEmptyString
    entries: tuple[DerivationEntry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate(self) -> MappingFreeze:
        ids = [entry.map_id for entry in self.entries]
        if len(set(ids)) != len(ids):
            raise OntologyFreezeError("M_L1_to_L2 contains duplicate map ids")
        if ids != sorted(ids):
            raise OntologyFreezeError("M_L1_to_L2 entries must be sorted by map id")
        return self

    @property
    def digest(self) -> str:
        return sha256_of(self)

    @property
    def mapped_l1_ids(self) -> frozenset[str]:
        return frozenset(s for entry in self.entries for s in entry.l1_source_ids)

    @property
    def mapped_l2_ids(self) -> frozenset[str]:
        return frozenset(entry.l2_target_id for entry in self.entries)

    def validate_against(self, l1: L1Freeze, l2: L2Freeze) -> None:
        if self.l1_version != l1.version or self.l2_version != l2.version:
            raise OntologyFreezeError(
                f"M_L1_to_L2 was frozen against O_L1 {self.l1_version}/O_L2 {self.l2_version} "
                f"but was given {l1.version}/{l2.version}; a stale map silently re-points ids"
            )
        unknown_l1 = sorted(self.mapped_l1_ids - l1.item_ids)
        if unknown_l1:
            raise OntologyFreezeError(f"map cites L1 ids absent from O_L1: {unknown_l1[:6]}")
        unknown_l2 = sorted(self.mapped_l2_ids - l2.item_ids)
        if unknown_l2:
            raise OntologyFreezeError(f"map cites L2 ids absent from O_L2: {unknown_l2[:6]}")
        # Relation types join abstraction types in needing a derivation: a relationship whose
        # party positions come from nowhere is exactly the guessed inventory v1 refused.
        needs_derivation = {L2ItemType.ABSTRACTION_TYPE, L2ItemType.RELATION_TYPE}
        underived = sorted(
            entry.item.id
            for entry in l2.items
            if entry.item_type in needs_derivation and entry.item.id not in self.mapped_l2_ids
        )
        if underived:
            raise OntologyFreezeError(
                f"O_L2 items requiring a derivation have none in the map: {underived[:6]}"
            )
        for entry in self.entries:
            target = next(i for i in l2.items if i.item.id == entry.l2_target_id)
            if entry.evidence_required < target.minimum_support:
                raise OntologyFreezeError(
                    f"{entry.map_id} requires {entry.evidence_required} supports but "
                    f"{target.item.id} declares a minimum of {target.minimum_support}"
                )


class Disposition(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DEFERRED = "deferred"


class CandidateDecision(_Frozen):
    """One candidate and what was done with it.

    Rejections carry the same weight as acceptances, so a rejection without a reason is
    invalid. The pressure is deliberate: it is easier to reject a candidate than to write down
    why, and an unexplained rejection is indistinguishable from an oversight under review.

    ``resolves_v1_deferral`` is the v2 addition. A deferral the sources were supposed to settle
    must name which one it settles, so "the source debt is paid" is a checkable list rather
    than an assertion.
    """

    candidate: NonEmptyString
    disposition: Disposition
    reason: Annotated[str, Field(min_length=20)]
    source: SourceKind
    # Set only when accepted, so an auditor can go from candidate to item without re-deriving
    # the naming decision.
    accepted_as: NonEmptyString | None = None
    resolves_v1_deferral: NonEmptyString | None = None
    grounding: tuple[ExternalGrounding, ...] = ()

    @model_validator(mode="after")
    def _validate(self) -> CandidateDecision:
        if self.disposition is Disposition.ACCEPTED and self.accepted_as is None:
            raise OntologyFreezeError(f"accepted candidate {self.candidate!r} names no item id")
        if self.disposition is not Disposition.ACCEPTED and self.accepted_as is not None:
            raise OntologyFreezeError(
                f"{self.disposition.value} candidate {self.candidate!r} names an item id; only "
                "an acceptance may point at one"
            )
        # Resolving a v1 deferral is the claim a reader would most want to trust and least be
        # able to check, so it must carry the citation that settled it. A resolution on fresh
        # corpus counts alone would be v1's own reasoning repeated louder.
        if self.resolves_v1_deferral is not None and not self.grounding:
            raise OntologyFreezeError(
                f"{self.candidate!r} claims to resolve the v1 deferral "
                f"{self.resolves_v1_deferral!r} but cites no external reference; those deferrals "
                "were recorded as awaiting a published source"
            )
        return self


class UncoveredExpression(_Frozen):
    """Something the corpora express that v2 still cannot represent.

    Recorded rather than papered over, because a coverage gap may not be masked. v2 closes most
    of v1's list; what remains is here with what it would still require, which is the honest
    alternative to declaring the ontology broad and dropping the register.
    """

    expression: NonEmptyString
    observed_in: SourceKind
    why_not_covered: Annotated[str, Field(min_length=20)]
    would_require: NonEmptyString


class SourceSnapshot(_Frozen):
    """One source, and whether it was actually read.

    v1's ``consulted=False`` entries were the point of that artifact. Here all three published
    sources are consulted, so the field carries different weight: ``content_sha256`` is the
    digest of the pinned raw archive, which ties a claim about PropBank to the exact bytes on
    disk rather than to PropBank in general.
    """

    name: NonEmptyString
    consulted: bool
    locator: NonEmptyString
    detail: NonEmptyString
    observed_units: NonNegativeInt = 0
    content_sha256: NonEmptyString | None = None

    @model_validator(mode="after")
    def _validate(self) -> SourceSnapshot:
        if not self.consulted and self.content_sha256 is not None:
            raise OntologyFreezeError(
                f"{self.name} is marked unconsulted but carries a content hash"
            )
        if self.consulted and self.observed_units == 0 and self.content_sha256 is None:
            raise OntologyFreezeError(
                f"{self.name} is marked consulted but records neither a count nor a hash, so "
                "the claim that it was read is unverifiable"
            )
        return self


class ProvenanceSnapshot(_Frozen):
    """The provenance artifact: sources, the discovery rule, and the judge non-dependency."""

    ontology_version: NonEmptyString
    supersedes: NonEmptyString
    sources: tuple[SourceSnapshot, ...] = Field(min_length=1)
    discovery_split_use: NonEmptyString
    judge_dependency: NonEmptyString
    model_api_calls: Literal[0] = 0
    keol_role: NonEmptyString
    # What each source offered and what was left behind. Without this the no-bulk-import rule
    # is unfalsifiable: a reader cannot tell restraint from not having looked.
    declined_imports: tuple[NonEmptyString, ...] = Field(min_length=1)

    @property
    def digest(self) -> str:
        return sha256_of(self)

    def consulted_names(self) -> tuple[str, ...]:
        return tuple(sorted(s.name for s in self.sources if s.consulted))

    def unconsulted_names(self) -> tuple[str, ...]:
        return tuple(sorted(s.name for s in self.sources if not s.consulted))


class DecisionLedger(_Frozen):
    """Every candidate decision plus the honest coverage gap."""

    ontology_version: NonEmptyString
    decisions: tuple[CandidateDecision, ...] = Field(min_length=1)
    uncovered: tuple[UncoveredExpression, ...] = ()

    @model_validator(mode="after")
    def _validate(self) -> DecisionLedger:
        names = [d.candidate for d in self.decisions]
        if len(set(names)) != len(names):
            raise OntologyFreezeError("a candidate is decided twice in the ledger")
        if names != sorted(names):
            raise OntologyFreezeError("ledger decisions must be sorted by candidate")
        claimed = [d.resolves_v1_deferral for d in self.decisions if d.resolves_v1_deferral]
        if len(set(claimed)) != len(claimed):
            raise OntologyFreezeError(
                "two decisions claim the same v1 deferral, which miscounts paid deferrals in "
                "the direction that flatters this build"
            )
        return self

    @property
    def digest(self) -> str:
        return sha256_of(self)

    def count(self, disposition: Disposition) -> int:
        return sum(1 for d in self.decisions if d.disposition is disposition)

    def accepted_ids(self) -> frozenset[str]:
        return frozenset(
            d.accepted_as
            for d in self.decisions
            if d.disposition is Disposition.ACCEPTED and d.accepted_as is not None
        )

    def resolved_v1_deferrals(self) -> tuple[str, ...]:
        return tuple(
            sorted(d.resolves_v1_deferral for d in self.decisions if d.resolves_v1_deferral)
        )


class SupersessionOutcome(StrEnum):
    """What v2 did with one v1 item.

    ``carried_forward`` means byte-identical content under the same id; ``revised`` means the id
    survives with changed content; ``retired`` means the id is gone. Only three outcomes, so
    there is nowhere to put an item whose fate is unclear -- which is the state a superseding
    version usually leaves items in.
    """

    CARRIED_FORWARD = "carried_forward"
    REVISED = "revised"
    RETIRED = "retired"


class SupersessionRecord(_Frozen):
    """One v1 id and what became of it, with a reason in every case.

    A reason is required even for ``carried_forward``. That looks redundant until you consider
    what an unexplained carry means: the item was not examined. The whole point of superseding
    a seed is that every item was looked at again, and a blank reason cannot be distinguished
    from a copy-paste.
    """

    v1_id: NonEmptyString
    outcome: SupersessionOutcome
    reason: Annotated[str, Field(min_length=20)]
    # Absent exactly when retired. A revision that does not say where the content went is a
    # retirement wearing a friendlier label.
    v2_id: NonEmptyString | None = None

    @model_validator(mode="after")
    def _validate(self) -> SupersessionRecord:
        if self.outcome is SupersessionOutcome.RETIRED:
            if self.v2_id is not None:
                raise OntologyFreezeError(f"{self.v1_id} is retired but names a v2 id")
            return self
        if self.v2_id is None:
            raise OntologyFreezeError(
                f"{self.v1_id} is {self.outcome.value} but names no v2 id; only a retirement "
                "has nowhere to point"
            )
        if self.outcome is SupersessionOutcome.CARRIED_FORWARD and self.v2_id != self.v1_id:
            raise OntologyFreezeError(
                f"{self.v1_id} is carried forward as {self.v2_id}; an id change is a revision, "
                "because a consumer citing the old id would break"
            )
        return self


class SupersessionFreeze(_Frozen):
    """Freeze unit ``supersession``: every v1 item accounted for exactly once.

    :meth:`validate_against` is what stops this from being a summary written after the fact. It
    checks the record against the v1 id set it claims to cover and against the v2 units, so a
    revision must actually name an id v2 contains and a retirement must name one it does not.
    """

    unit_id: Literal["supersession"] = "supersession"
    version: NonEmptyString
    supersedes_version: NonEmptyString
    records: tuple[SupersessionRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate(self) -> SupersessionFreeze:
        ids = [record.v1_id for record in self.records]
        if len(set(ids)) != len(ids):
            raise OntologyFreezeError("a v1 id is given two supersession outcomes")
        if ids != sorted(ids):
            raise OntologyFreezeError("supersession records must be sorted by v1 id")
        return self

    @property
    def digest(self) -> str:
        return sha256_of(self)

    def counts_by_outcome(self) -> dict[str, int]:
        counts = {outcome.value: 0 for outcome in SupersessionOutcome}
        for record in self.records:
            counts[record.outcome.value] += 1
        return counts

    def validate_against(
        self, v1_ids: frozenset[str], l1: L1Freeze, l2: L2Freeze, mapping: MappingFreeze
    ) -> None:
        covered = frozenset(record.v1_id for record in self.records)
        missing = sorted(v1_ids - covered)
        if missing:
            raise OntologyFreezeError(
                f"v1 items with no supersession record: {missing[:6]}. Superseding a version "
                "means deciding about all of it, not about the parts that were easy"
            )
        invented = sorted(covered - v1_ids)
        if invented:
            raise OntologyFreezeError(f"supersession records for ids v1 never had: {invented[:6]}")

        present = l1.item_ids | l2.item_ids | frozenset(e.map_id for e in mapping.entries)
        for record in self.records:
            if record.outcome is SupersessionOutcome.RETIRED:
                if record.v1_id in present:
                    raise OntologyFreezeError(
                        f"{record.v1_id} is recorded as retired but v2 still contains that id"
                    )
                continue
            if record.v2_id is not None and record.v2_id not in present:
                raise OntologyFreezeError(
                    f"{record.v1_id} is {record.outcome.value} to {record.v2_id}, which no v2 "
                    "unit contains"
                )


class FoundationOntologyV2(_Frozen):
    """The freeze units together, with the cross-unit checks the plan requires.

    Assembly is where the guarantees are enforced rather than described, so a defective ontology
    fails at construction and never reaches disk to be cited.
    """

    l1: L1Freeze
    l2: L2Freeze
    map: MappingFreeze
    ledger: DecisionLedger
    provenance: ProvenanceSnapshot
    supersession: SupersessionFreeze

    @model_validator(mode="after")
    def _validate(self) -> FoundationOntologyV2:
        self.map.validate_against(self.l1, self.l2)
        overlap = sorted(self.l1.item_ids & self.l2.item_ids)
        if overlap:
            raise OntologyFreezeError(
                f"the two layers share ids without going through the map: {overlap[:6]}"
            )
        declared = self.ledger.accepted_ids()
        real = self.l1.item_ids | self.l2.item_ids | self.map.mapped_l2_ids
        phantom = sorted(declared - real - {e.map_id for e in self.map.entries})
        if phantom:
            raise OntologyFreezeError(
                f"the ledger accepts candidates as items that no unit contains: {phantom[:6]}"
            )
        # An item nobody decided on entered without review, which is the failure the decision
        # requirement exists to prevent. It bites harder at v2's size than at v1's.
        undecided = sorted((self.l1.item_ids | self.l2.item_ids) - declared)
        if undecided:
            raise OntologyFreezeError(
                f"items present in a layer with no ledger decision: {undecided[:6]}"
            )
        versions = {
            self.ledger.ontology_version,
            self.provenance.ontology_version,
            self.supersession.version,
        }
        if len(versions) != 1:
            raise OntologyFreezeError(f"units disagree about the ontology version: {versions}")
        if self.provenance.supersedes != self.supersession.supersedes_version:
            raise OntologyFreezeError(
                "provenance and the supersession record disagree about which version is superseded"
            )
        return self

    def hashes(self) -> dict[str, str]:
        """Six independent digests. There is deliberately no combined ontology hash.

        A single digest tells an auditor that something moved without saying which unit moved,
        so re-freezing O_L1 would appear to invalidate a citation about the map.
        """
        return {
            "o_l1_sha256": self.l1.digest,
            "o_l2_sha256": self.l2.digest,
            "m_l1_to_l2_sha256": self.map.digest,
            "decisions_sha256": self.ledger.digest,
            "provenance_sha256": self.provenance.digest,
            "supersession_sha256": self.supersession.digest,
        }

    def item_counts(self) -> dict[str, int]:
        return {
            "o_l1_items": len(self.l1.items),
            "o_l2_items": len(self.l2.items),
            "m_l1_to_l2_entries": len(self.map.entries),
        }
