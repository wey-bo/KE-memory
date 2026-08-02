"""Freeze models for foundation ontology v1: three units, three independent hashes.

The plan asks for O_L1, O_L2 and M_L1_to_L2 to be "versioned and hashed independently"
and for the two layers to "not share a vocabulary by default". Both are enforced
structurally here rather than checked by convention:

- Each unit is its own model and its digest is SHA-256 over that model alone. A change to
  O_L2 cannot move the O_L1 hash, because O_L1's serialization does not contain O_L2.
- Every id is namespaced (``l1:``, ``l2:``, ``m:``) and each item is scanned for the
  *foreign* namespace anywhere in its serialized content. So an L2 item cannot quietly
  reference an L1 role or predicate: the only place both namespaces may appear is
  :class:`MappingFreeze`, which is the declaration the plan requires.

Individuals and benchmark facts are excluded the same way. Rather than a denylist of
things not to write, :class:`L1Item` and :class:`L2Item` have no field that could hold an
instance -- no value, no filler, no mention -- and the ``individual`` ontology role is
rejected outright. A type-level ontology that cannot represent an instance cannot leak one.
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

# Ids are lowercase dotted paths. The shape is enforced because an id is the thing a
# mapper is scored against: an id that can carry arbitrary text can carry a surface form,
# and then "canonical id" stops meaning anything stable.
_ID_BODY = re.compile(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+")

# Corpora whose questions and gold the ontology may not be derived from. Recorded as a
# scan rather than as a rule in prose, because the discovery-split restriction is the one
# constraint an author cannot self-certify.
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

    Checked over the serialized item, not over declared reference fields. A relation
    target, a constraint expression and a free-text sense are all places an id has
    escaped a typed field before, and the point of the no-shared-vocabulary rule is that
    there is no such place.
    """
    if foreign.encode() in canonical_json(unit):
        raise OntologyFreezeError(
            f"{what} references the {foreign!r} namespace; the two layers do not share a "
            "vocabulary, so a cross-layer reference must be declared in M_L1_to_L2"
        )


class OntologyRoleKind(StrEnum):
    """What kind of ontology position an item occupies.

    ``individual`` is deliberately absent. :class:`ke_memory_demo.domain.OntologyRole` has
    it, and staying compatible with that vocabulary would mean admitting it here, which
    the plan's ``excluded: [Individuals]`` forbids. So this is a narrowing, not a copy.
    """

    CONCEPT = "concept"
    OPERATOR = "operator"
    ROLE = "role"
    VOCABULARY_VALUE = "vocabulary_value"


class L1ItemType(StrEnum):
    """The atomic-layer type taxonomy.

    ``event``/``state``/``preference``/``task``/``attribute`` are the five the plan names.
    The remaining four are the machinery those five need to be usable: a predicate sense
    without roles has no argument structure, and a temporal or modal qualifier is not an
    attribute of a subject but of an assertion.
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

    These are not longer-lived L1 items. An L2 item is only well-formed if it says how it
    is computed from lower-layer observations, which is why every one of them carries an
    :class:`AggregationPattern` and why the type names are structures (Project, Habit)
    rather than predicates.
    """

    ABSTRACTION_TYPE = "abstraction_type"
    AGGREGATION_PATTERN = "aggregation_pattern"
    LIFECYCLE_STATE = "lifecycle_state"
    EVIDENCE_CONSTRAINT = "evidence_constraint"


class RelationKind(StrEnum):
    """The relation inventory, closed on purpose.

    An open relation vocabulary makes a hash meaningless as a contract: two ontologies
    with the same items and freely-invented edge labels would be incomparable. Every
    relation an item needs must therefore already be one of these, or be recorded as an
    uncovered expression.
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


class SourceKind(StrEnum):
    """Where a candidate came from, so provenance is a field rather than a claim."""

    SGD_SCHEMA = "sgd_schema"
    SGD_DIALOGUE_ACTS = "sgd_dialogue_acts"
    SGD_STATE_DYNAMICS = "sgd_state_dynamics"
    TASKMASTER2_ANNOTATIONS = "taskmaster2_annotations"
    TAU_BENCH_TOOLS = "tau_bench_tools"
    TAU_BENCH_POLICY = "tau_bench_policy"
    MSC_PERSONAS = "msc_personas"
    REPOSITORY_VOCABULARY = "repository_vocabulary"
    DISCOVERY_GAP_SHAPE = "discovery_gap_shape"
    AUTHORED_FOR_CLOSURE = "authored_for_closure"


class Relation(_Frozen):
    """One typed edge. ``target_id`` is validated by the owning unit, not here.

    The owning unit knows which namespace is legal for its own targets; a relation on its
    own does not, and guessing would let an L2 item declare an L1 target.
    """

    kind: RelationKind
    target_id: NonEmptyString


class RoleSlot(_Frozen):
    """One argument position of a predicate sense or event type.

    ``role_id`` points at an L1 role item rather than naming the role inline, because two
    event types that share an argument position should share the position, not two strings
    that happen to match.
    """

    role_id: NonEmptyString
    is_required: bool = False
    # Why a range and not a type: SGD's schema separates categorical slots (a closed value
    # set) from free slots, and a role whose range is open is a different mapping problem
    # from one whose range is enumerable.
    range_id: NonEmptyString | None = None


class Constraint(_Frozen):
    """A checkable statement about an item, expressed so a reader can test it.

    ``expression`` is prose in a fixed shape rather than executable code. Nothing in v1
    evaluates constraints, and shipping an unevaluated DSL would be a claim of enforcement
    the freeze cannot back; ``kind`` is what an implementation would dispatch on.
    """

    kind: NonEmptyString
    expression: NonEmptyString


class Provenance(_Frozen):
    """Why this item exists, tied to something a reviewer can go and look at.

    ``evidence`` must cite an observable in the build corpora -- a slot name, an act
    label, a tool name, a measured proportion. "Seemed necessary" is what this field is
    designed to make visibly absent.
    """

    source: SourceKind
    evidence: NonEmptyString


class OntologyItem(_Frozen):
    """Fields common to both layers, including the ones deliberately not present.

    There is no ``value``, ``filler``, ``example``, ``surface_form`` or ``mention`` field
    anywhere in this hierarchy. That absence is the mechanism excluding Individuals and
    benchmark facts: an item can say what an attribute type *is*, and cannot say what any
    particular subject's value for it *was*.
    """

    id: NonEmptyString
    sense: Annotated[str, Field(min_length=12)]
    aliases: tuple[NonEmptyString, ...] = ()
    role_kind: OntologyRoleKind
    relations: tuple[Relation, ...] = ()
    roles: tuple[RoleSlot, ...] = ()
    constraints: tuple[Constraint, ...] = ()
    provenance: tuple[Provenance, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_item(self) -> OntologyItem:
        if len(set(self.aliases)) != len(self.aliases):
            raise OntologyFreezeError(f"{self.id} repeats an alias")
        # An alias equal to the id is noise that inflates alias counts without adding a
        # single surface form the mapper could not already match.
        if self.id in self.aliases:
            raise OntologyFreezeError(f"{self.id} lists its own id as an alias")
        relation_keys = [(r.kind, r.target_id) for r in self.relations]
        if len(set(relation_keys)) != len(relation_keys):
            raise OntologyFreezeError(f"{self.id} repeats a relation")
        role_ids = [slot.role_id for slot in self.roles]
        if len(set(role_ids)) != len(role_ids):
            raise OntologyFreezeError(f"{self.id} binds the same role twice")
        lowered = " ".join((self.sense, *self.aliases)).lower()
        leaked = sorted(t for t in FORBIDDEN_CORPUS_TOKENS if t in lowered)
        if leaked:
            raise OntologyFreezeError(
                f"{self.id} names an evaluation corpus ({leaked}); candidates may come from "
                "the discovery split only as general gap shapes, never as corpus-specific text"
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
        # A role slot on something that is not predicate-like means the argument structure
        # is attached to the wrong kind of item, which silently changes what a mapper is
        # expected to fill. Attribute types are included because an attribute does have one
        # argument position -- the bearer it is predicated of -- and omitting it would leave
        # the bearer implicit, which is how a value and its subject get conflated.
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
        return self


class L2Item(_Frozen):
    """One abstraction-layer type. Ids and every reference stay inside ``l2:``.

    ``derives_from_l1`` is absent by design. The derivation lives in M_L1_to_L2 so that
    changing which L1 items feed an abstraction moves the *map* hash, not the L2 hash. If
    the edge were stored here, the layers would share a vocabulary by default and the map
    would be documentation instead of a contract.
    """

    item: OntologyItem
    item_type: L2ItemType
    # Why on the item and not in the map: this says *that* the abstraction needs multiple
    # supports, which is a property of the type. *Which* supports is the map's business.
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
        if self.item_type is L2ItemType.ABSTRACTION_TYPE and self.minimum_support < 1:
            raise OntologyFreezeError(f"{self.item.id} must require at least one support")
        return self


def _validate_closure(ids: frozenset[str], items: tuple[L1Item, ...] | tuple[L2Item, ...]) -> None:
    """Every relation, role and range must resolve inside the same unit.

    A dangling target is worse than a missing item: the ontology looks like it has an
    ``is_a`` hierarchy while the parent does not exist, so a consumer walking the graph
    gets a different taxonomy than the one the hash certifies.
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


def _reject_alias_collisions(aliases_by_id: dict[str, tuple[str, ...]], unit: str) -> None:
    """One alias may not resolve to two items in the same unit.

    An ambiguous alias makes normalization non-deterministic: the mapper's answer would
    depend on iteration order, and the resulting score would not be reproducible from the
    frozen artifact.
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


class DerivationKind(StrEnum):
    """How an L2 item is obtained from L1 items.

    ``import_as`` is separated from the computed kinds because it is the only one that
    reuses an L1 sense unchanged, and it is therefore the only one where a reviewer should
    ask whether the L2 item earns its own id at all.
    """

    IMPORT_AS = "import_as"
    AGGREGATES_OVER = "aggregates_over"
    ABSTRACTS_FROM = "abstracts_from"
    QUALIFIER_LIFT = "qualifier_lift"


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
        # An import that names several sources is not an import; calling it one would hide
        # a real aggregation behind the one kind that needs no aggregation rule.
        if self.kind is DerivationKind.IMPORT_AS and len(self.l1_source_ids) != 1:
            raise OntologyFreezeError(
                f"{self.map_id} imports from {len(self.l1_source_ids)} sources; an import "
                "carries exactly one, otherwise it is an aggregation"
            )
        if self.kind is DerivationKind.AGGREGATES_OVER and self.evidence_required < 1:
            raise OntologyFreezeError(f"{self.map_id} aggregates but requires no evidence")
        return self


class MappingFreeze(_Frozen):
    """Freeze unit M_L1_to_L2: every cross-layer edge, and nothing implicit.

    :meth:`validate_against` is what makes this a contract rather than a third list. It is
    called with the two layer units and checks both directions: no edge may name an id
    that does not exist, and no L2 item may exist without an edge explaining where it
    comes from. An unreachable L2 item is an abstraction with no derivation, which is the
    same defect :class:`~ke_memory_demo.evaluation.layer_gold.L2GoldAbstraction` rejects.
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
        underived = sorted(
            entry.item.id
            for entry in l2.items
            if entry.item_type is L2ItemType.ABSTRACTION_TYPE
            and entry.item.id not in self.mapped_l2_ids
        )
        if underived:
            raise OntologyFreezeError(
                f"O_L2 abstraction types with no derivation in the map: {underived[:6]}"
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

    Rejections carry the same weight as acceptances in the plan, so a rejection without a
    reason is invalid here. The pressure this puts on the author is deliberate: it is
    easier to reject a candidate than to write down why, and an unexplained rejection is
    indistinguishable from an oversight when the ontology is reviewed.
    """

    candidate: NonEmptyString
    disposition: Disposition
    reason: Annotated[str, Field(min_length=20)]
    source: SourceKind
    # Set only when accepted. Present so an auditor can go from a candidate to the item it
    # became without re-deriving the naming decision.
    accepted_as: NonEmptyString | None = None

    @model_validator(mode="after")
    def _validate(self) -> CandidateDecision:
        if self.disposition is Disposition.ACCEPTED and self.accepted_as is None:
            raise OntologyFreezeError(f"accepted candidate {self.candidate!r} names no item id")
        if self.disposition is not Disposition.ACCEPTED and self.accepted_as is not None:
            raise OntologyFreezeError(
                f"{self.disposition.value} candidate {self.candidate!r} names an item id; only "
                "an acceptance may point at one"
            )
        return self


class UncoveredExpression(_Frozen):
    """Something the corpora express that v1 cannot represent.

    Recorded rather than papered over, because the plan states a coverage gap may not be
    masked. ``why_not_covered`` distinguishes the two cases that matter: a gap deferred for
    lack of evidence, and a gap that would need a modelling construct v1 does not have.
    """

    expression: NonEmptyString
    observed_in: SourceKind
    why_not_covered: Annotated[str, Field(min_length=20)]
    would_require: NonEmptyString


class SourceSnapshot(_Frozen):
    """One source, and whether it was actually read.

    ``consulted=False`` entries are the point. WordNet, PropBank and schema.org are named
    by the plan; recording them as unconsulted with the reason is the honest alternative to
    writing plausible-looking entries and attributing them to a source never opened.
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
    sources: tuple[SourceSnapshot, ...] = Field(min_length=1)
    discovery_split_use: NonEmptyString
    judge_dependency: NonEmptyString
    model_api_calls: Literal[0] = 0
    keol_role: NonEmptyString

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


class FoundationOntology(_Frozen):
    """The three freeze units together, with the cross-unit checks the plan requires.

    Assembly is where the guarantees become joint. Individually O_L1 and O_L2 only know
    their own namespace; only here can the disjointness be asserted over both id sets at
    once, and only here can every accepted decision be checked to correspond to an item
    that really exists in one of the two layers.
    """

    l1: L1Freeze
    l2: L2Freeze
    map: MappingFreeze
    ledger: DecisionLedger
    provenance: ProvenanceSnapshot

    @model_validator(mode="after")
    def _validate(self) -> FoundationOntology:
        self.map.validate_against(self.l1, self.l2)
        overlap = sorted(self.l1.item_ids & self.l2.item_ids)
        if overlap:
            raise OntologyFreezeError(
                f"O_L1 and O_L2 share ids without going through the map: {overlap[:6]}"
            )
        declared = self.ledger.accepted_ids()
        real = self.l1.item_ids | self.l2.item_ids | self.map.mapped_l2_ids
        phantom = sorted(declared - real - {e.map_id for e in self.map.entries})
        if phantom:
            raise OntologyFreezeError(
                f"the ledger accepts candidates as items that no unit contains: {phantom[:6]}"
            )
        # An item nobody decided on is an item that entered without review, which is the
        # failure mode the decision requirement exists to prevent.
        undecided = sorted((self.l1.item_ids | self.l2.item_ids) - declared)
        if undecided:
            raise OntologyFreezeError(
                f"items present in a layer with no ledger decision: {undecided[:6]}"
            )
        if self.provenance.ontology_version != self.ledger.ontology_version:
            raise OntologyFreezeError("provenance and ledger disagree about the ontology version")
        return self

    def hashes(self) -> dict[str, str]:
        """Five independent digests. There is deliberately no combined ontology hash.

        Stage 1A rejected a single digest for the same reason: it tells an auditor that
        something moved without saying which unit moved, so re-freezing O_L1 would appear
        to invalidate a citation about the map.
        """
        return {
            "o_l1_sha256": self.l1.digest,
            "o_l2_sha256": self.l2.digest,
            "m_l1_to_l2_sha256": self.map.digest,
            "decisions_sha256": self.ledger.digest,
            "provenance_sha256": self.provenance.digest,
        }

    def item_counts(self) -> dict[str, int]:
        return {
            "o_l1_items": len(self.l1.items),
            "o_l2_items": len(self.l2.items),
            "m_l1_to_l2_entries": len(self.map.entries),
        }
