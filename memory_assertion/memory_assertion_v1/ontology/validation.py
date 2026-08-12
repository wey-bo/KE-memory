"""The twelve semantic checks of the Ontology Profile, over any snapshot.

Two properties matter more than the individual rules.

**Everything is collected.** A builder asking "what is wrong with this snapshot" needs
the whole answer, so no check short-circuits and parse failures become entries in the
same result rather than exceptions. Violations sort by (code, subject, detail), so
reordering the checks cannot change the output and two runs over one snapshot are
diffable.

**Semantic validity and provisioning eligibility are independent.** A snapshot can be
perfectly well-formed and still undeliverable: a `partial` operator quarantines it,
because v1 ships no content-addressed registry of definedness predicates. Quarantine does
not skip that operator's own structural checks -- a partial operator with a malformed
`required_input_indexes` has two separate problems and must report both.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol, cast

from pydantic import BaseModel, ConfigDict

from memory_assertion_v1.ontology.profile import (
    BOOLEAN_CODEC,
    CODEC_JSON_KINDS,
    CurrencyMinorUnits,
)
from memory_assertion_v1.ontology.snapshot import ParsedOperator, ParsedSnapshot
from memory_assertion_v1.ontology.violations import (
    QuarantineReason,
    Violation,
    ViolationCode,
)

_SURFACE_RELATION_VALUES = frozenset(
    {"canonical_label", "equivalent_expression", "abbreviated_expression", "surface_variant"}
)
_MAPPING_RELATION_VALUES = frozenset({"exact", "narrow", "broad", "related"})
_PROPOSITION_KIND = "proposition"


class _DeprecatableProfile(Protocol):
    """The two fields the deprecation walk reads, shared by both profile types."""

    @property
    def deprecated(self) -> bool | None: ...

    @property
    def replaced_by(self) -> str | None: ...


class _ProfileHolder(Protocol):
    """A parsed record exposing its profile -- satisfied by both Concept and Operator."""

    @property
    def profile(self) -> _DeprecatableProfile: ...


_ProfileHolders = dict[str, _ProfileHolder]


class SnapshotValidationResult(BaseModel):
    """The single result of validating a snapshot.

    One type rather than two returns, so a caller cannot read the violations and forget to
    check whether the snapshot may be provisioned at all.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    semantic_status: Literal["valid", "invalid"]
    provisioning_status: Literal["eligible", "quarantined"]
    violations: tuple[Violation, ...]
    quarantine_reasons: tuple[QuarantineReason, ...]

    def codes(self) -> tuple[str, ...]:
        """Violation codes in report order -- the handle tests assert on."""
        return tuple(str(violation.code) for violation in self.violations)


def validate_snapshot(snapshot: ParsedSnapshot) -> SnapshotValidationResult:
    """Run every check and return one collected, deterministically ordered result."""
    violations: list[Violation] = list(snapshot.parse_violations)
    quarantine: list[QuarantineReason] = []

    ancestors = _ancestor_closures(snapshot)

    _check_identity_closure(snapshot, violations)
    _check_deprecation(snapshot, violations)
    _check_disjointness(snapshot, ancestors, violations)
    _check_literal_contracts(snapshot, violations)
    _check_operator_signatures(snapshot, violations, quarantine)
    _check_relation_enums(snapshot, violations)
    _check_source_attestations(snapshot, violations)

    ordered = tuple(sorted(violations, key=lambda item: item.sort_key()))
    ordered_quarantine = tuple(sorted(quarantine, key=lambda item: item.sort_key()))
    return SnapshotValidationResult(
        semantic_status="invalid" if ordered else "valid",
        provisioning_status="quarantined" if ordered_quarantine else "eligible",
        violations=ordered,
        quarantine_reasons=ordered_quarantine,
    )


def _ancestor_closures(snapshot: ParsedSnapshot) -> dict[str, frozenset[str]]:
    """Transitive parents per Concept, computed without trusting acyclicity.

    Cycles are a violation reported elsewhere, but this has to terminate even when one is
    present, so traversal tracks what it has already seen instead of recursing freely.
    """
    closures: dict[str, frozenset[str]] = {}
    for concept_id in snapshot.concepts:
        seen: set[str] = set()
        frontier = [concept_id]
        while frontier:
            current = frontier.pop()
            parsed = snapshot.concepts.get(current)
            if parsed is None:
                continue
            for parent in parsed.record.parents:
                if parent not in seen:
                    seen.add(parent)
                    frontier.append(parent)
        closures[concept_id] = frozenset(seen)
    return closures


def _check_identity_closure(snapshot: ParsedSnapshot, violations: list[Violation]) -> None:
    """Symbols unique per kind, references resolvable, inheritance a DAG.

    Reference closure covers snapshot-internal ids only. `ExternalMapping.target` is
    deliberately excluded: an external identifier names something outside the snapshot, so
    requiring it to resolve here would reject every legitimate mapping.
    """
    concept_symbols: dict[str, str] = {}
    for concept_id, parsed in sorted(snapshot.concepts.items()):
        owner = concept_symbols.get(parsed.symbol)
        if owner is not None:
            violations.append(
                Violation(
                    code=ViolationCode.DUPLICATE_CONCEPT_SYMBOL,
                    subject=concept_id,
                    detail=f"{parsed.symbol} also on {owner}",
                )
            )
        else:
            concept_symbols[parsed.symbol] = concept_id

    operator_symbols: dict[str, str] = {}
    for operator_id, parsed_operator in sorted(snapshot.operators.items()):
        owner = operator_symbols.get(parsed_operator.symbol)
        if owner is not None:
            violations.append(
                Violation(
                    code=ViolationCode.DUPLICATE_OPERATOR_SYMBOL,
                    subject=operator_id,
                    detail=f"{parsed_operator.symbol} also on {owner}",
                )
            )
        else:
            operator_symbols[parsed_operator.symbol] = operator_id

    for concept_id, parsed in sorted(snapshot.concepts.items()):
        for parent in parsed.record.parents:
            if parent == concept_id:
                violations.append(
                    Violation(code=ViolationCode.CONCEPT_SELF_PARENT, subject=concept_id)
                )
            elif parent not in snapshot.concepts:
                violations.append(
                    Violation(
                        code=ViolationCode.UNRESOLVED_CONCEPT_REFERENCE,
                        subject=concept_id,
                        detail=f"parents -> {parent}",
                    )
                )

    for operator_id, parsed_operator in sorted(snapshot.operators.items()):
        for position, input_id in enumerate(parsed_operator.record.input_concepts):
            if input_id not in snapshot.concepts:
                violations.append(
                    Violation(
                        code=ViolationCode.UNRESOLVED_CONCEPT_REFERENCE,
                        subject=operator_id,
                        detail=f"input_concepts[{position}] -> {input_id}",
                    )
                )
        if parsed_operator.record.output_concept not in snapshot.concepts:
            violations.append(
                Violation(
                    code=ViolationCode.UNRESOLVED_CONCEPT_REFERENCE,
                    subject=operator_id,
                    detail=f"output_concept -> {parsed_operator.record.output_concept}",
                )
            )

    for cycle_member in sorted(_cycle_members(snapshot)):
        violations.append(
            Violation(code=ViolationCode.CONCEPT_INHERITANCE_CYCLE, subject=cycle_member)
        )


def _check_deprecation(snapshot: ParsedSnapshot, violations: list[Violation]) -> None:
    """`replaced_by` only under deprecation, resolving, same kind, acyclic, ending live.

    A finite chain is allowed -- one identity may be superseded twice -- but it has to end
    somewhere that is not itself deprecated, or a consumer following it never arrives at a
    usable identity. Same kind because a Concept cannot be replaced by an Operator: the two
    id spaces are separate, so a cross-kind target is an unresolved reference by
    construction.
    """
    holder_sets: tuple[tuple[str, _ProfileHolders], ...] = (
        ("concept", dict(snapshot.concepts)),
        ("operator", dict(snapshot.operators)),
    )
    for kind, entries in holder_sets:
        known = set(entries)
        chain = _replacement_chain(entries)
        for subject_id, parsed in sorted(entries.items()):
            profile = parsed.profile
            replaced_by = profile.replaced_by
            if replaced_by is None:
                continue
            if profile.deprecated is not True:
                violations.append(
                    Violation(
                        code=ViolationCode.REPLACED_BY_WITHOUT_DEPRECATION,
                        subject=subject_id,
                        detail=f"replaced_by {replaced_by}",
                    )
                )
            if replaced_by == subject_id:
                violations.append(
                    Violation(code=ViolationCode.REPLACED_BY_SELF, subject=subject_id)
                )
                continue
            if replaced_by not in known:
                violations.append(
                    Violation(
                        code=ViolationCode.REPLACED_BY_UNRESOLVED,
                        subject=subject_id,
                        detail=f"{kind} {replaced_by}",
                    )
                )
                continue
            _walk_replacement_chain(subject_id, chain, violations)


def _replacement_chain(snapshot_entries: _ProfileHolders) -> dict[str, tuple[bool, str | None]]:
    """Reduce records to just the deprecation data the chain walk needs.

    Extracted as plain data rather than walked over the models, so the traversal is typed
    rather than reaching through attributes that two different record types happen to share.
    """
    return {
        record_id: (holder.profile.deprecated is True, holder.profile.replaced_by)
        for record_id, holder in snapshot_entries.items()
    }


def _walk_replacement_chain(
    start: str,
    chain: dict[str, tuple[bool, str | None]],
    violations: list[Violation],
) -> None:
    """Follow `replaced_by` from one record to the end of its chain."""
    seen = {start}
    current = start
    while True:
        entry = chain.get(current)
        if entry is None:
            return
        deprecated, nxt = entry
        if nxt is None:
            if deprecated:
                violations.append(
                    Violation(
                        code=ViolationCode.REPLACED_BY_CHAIN_ENDS_DEPRECATED,
                        subject=start,
                        detail=f"ends at {current}",
                    )
                )
            return
        if nxt in seen:
            violations.append(
                Violation(
                    code=ViolationCode.REPLACED_BY_CYCLE,
                    subject=start,
                    detail=f"revisits {nxt}",
                )
            )
            return
        if nxt not in chain:
            return
        seen.add(nxt)
        current = nxt


def _check_disjointness(
    snapshot: ParsedSnapshot,
    ancestors: dict[str, frozenset[str]],
    violations: list[Violation],
) -> None:
    """Explicit edges must be materialised both ways; inherited conflicts are derived.

    The asymmetry between the two halves is deliberate. An explicit `disjoint_with` edge
    must appear on both sides in the snapshot, because a builder guessing the reverse edge
    is a builder inventing an assertion nobody wrote. But the *descendant* consequences of
    that edge are derived at validation time and never written back: materialising the
    closure would multiply the stored edges while adding nothing a reader could not compute.

    A Concept inheriting from both sides of a disjoint pair is unsatisfiable -- no instance
    can exist -- so it is rejected rather than reported as a hint.
    """
    for concept_id, parsed in sorted(snapshot.concepts.items()):
        for target in parsed.profile.disjoint_with:
            if target == concept_id:
                violations.append(
                    Violation(code=ViolationCode.DISJOINT_SELF, subject=concept_id)
                )
                continue
            other = snapshot.concepts.get(target)
            if other is None:
                violations.append(
                    Violation(
                        code=ViolationCode.DISJOINT_UNRESOLVED,
                        subject=concept_id,
                        detail=f"-> {target}",
                    )
                )
                continue
            if concept_id not in other.profile.disjoint_with:
                violations.append(
                    Violation(
                        code=ViolationCode.DISJOINT_ASYMMETRIC,
                        subject=concept_id,
                        detail=f"{target} does not list it back",
                    )
                )
            if target in ancestors[concept_id] or concept_id in ancestors[target]:
                violations.append(
                    Violation(
                        code=ViolationCode.DISJOINT_ANCESTOR_CONFLICT,
                        subject=concept_id,
                        detail=f"-> {target}",
                    )
                )

    pairs = _disjoint_pairs(snapshot)
    for concept_id in sorted(snapshot.concepts):
        lineage = ancestors[concept_id] | {concept_id}
        for left, right in sorted(pairs):
            if left in lineage and right in lineage:
                violations.append(
                    Violation(
                        code=ViolationCode.DISJOINT_UNSATISFIABLE_INHERITANCE,
                        subject=concept_id,
                        detail=f"inherits {left} and {right}",
                    )
                )


def _disjoint_pairs(snapshot: ParsedSnapshot) -> set[tuple[str, str]]:
    """Every declared disjoint pair, normalised so each appears once."""
    pairs: set[tuple[str, str]] = set()
    for concept_id, parsed in snapshot.concepts.items():
        for target in parsed.profile.disjoint_with:
            if target == concept_id:
                continue
            pairs.add((concept_id, target) if concept_id < target else (target, concept_id))
    return pairs


def _check_literal_contracts(snapshot: ParsedSnapshot, violations: list[Violation]) -> None:
    """A literal contract exactly when the Concept is a literal domain, and codec-consistent.

    Biconditional: `semantic_kind=literal_value` requires the contract, and any other kind
    forbids it. A contract on an entity Concept would imply entities have canonical
    literal spellings, which is what the `typed_value` term shape exists to avoid.
    """
    for concept_id, parsed in sorted(snapshot.concepts.items()):
        profile = parsed.profile
        contract = profile.literal_value_contract
        is_literal = profile.semantic_kind == "literal_value"
        if is_literal and contract is None:
            violations.append(
                Violation(code=ViolationCode.LITERAL_CONTRACT_REQUIRED, subject=concept_id)
            )
            continue
        if not is_literal:
            if contract is not None:
                violations.append(
                    Violation(
                        code=ViolationCode.LITERAL_CONTRACT_FORBIDDEN,
                        subject=concept_id,
                        detail=profile.semantic_kind,
                    )
                )
            continue
        if contract is None:
            continue

        expected_kind = CODEC_JSON_KINDS[contract.codec_id]
        if contract.canonical_json_kind != expected_kind:
            violations.append(
                Violation(
                    code=ViolationCode.LITERAL_CODEC_KIND_MISMATCH,
                    subject=concept_id,
                    detail=f"{contract.codec_id} expects {expected_kind}",
                )
            )
        if contract.codec_id == "ke-literal:money/v1":
            _check_money_contract(concept_id, contract.currency_minor_units, violations)
        elif contract.currency_minor_units is not None:
            violations.append(
                Violation(
                    code=ViolationCode.MONEY_CONTRACT_INCOMPLETE,
                    subject=concept_id,
                    detail=f"currency_minor_units on {contract.codec_id}",
                )
            )
        if contract.codec_id == "ke-literal:quantity/v1":
            if contract.canonical_unit_symbol is None:
                violations.append(
                    Violation(
                        code=ViolationCode.QUANTITY_CONTRACT_INCOMPLETE,
                        subject=concept_id,
                        detail="canonical_unit_symbol missing",
                    )
                )
        elif contract.canonical_unit_symbol is not None:
            violations.append(
                Violation(
                    code=ViolationCode.QUANTITY_CONTRACT_INCOMPLETE,
                    subject=concept_id,
                    detail=f"canonical_unit_symbol on {contract.codec_id}",
                )
            )


def _check_money_contract(
    concept_id: str,
    entries: tuple[CurrencyMinorUnits, ...] | None,
    violations: list[Violation],
) -> None:
    """Money declares its own accepted currencies, sorted and unique.

    The list is the whole authority: an implementation may not consult an external ISO 4217
    table to fill a gap, because then the same snapshot would mean different things
    depending on which table the reader had.
    """
    if entries is None:
        violations.append(
            Violation(
                code=ViolationCode.MONEY_CONTRACT_INCOMPLETE,
                subject=concept_id,
                detail="currency_minor_units missing",
            )
        )
        return
    currencies = [entry.currency for entry in entries]
    if currencies != sorted(currencies):
        violations.append(
            Violation(code=ViolationCode.CURRENCY_MINOR_UNITS_UNSORTED, subject=concept_id)
        )
    duplicates = sorted({name for name in currencies if currencies.count(name) > 1})
    for name in duplicates:
        violations.append(
            Violation(
                code=ViolationCode.CURRENCY_MINOR_UNITS_DUPLICATE,
                subject=concept_id,
                detail=name,
            )
        )


def _check_operator_signatures(
    snapshot: ParsedSnapshot,
    violations: list[Violation],
    quarantine: list[QuarantineReason],
) -> None:
    """Positional parameters, proposition operation closure, and definedness.

    The proposition rules can only be decided here, in the closure: whether an input is a
    Proposition is a property of the referenced Concept's `semantic_kind`, not of the
    Operator. An Operator read in isolation cannot be checked against them at all.

    Quarantine and validation are independent. A `partial` operator quarantines the
    snapshot *and* still has its `definedness_contract` and `required_input_indexes`
    checked -- skipping them because it is already unprovisionable would hide defects that
    matter the moment v1 gains a definedness registry.
    """
    for operator_id, parsed in sorted(snapshot.operators.items()):
        profile = parsed.profile
        record = parsed.record
        arity = len(record.input_concepts)

        parameters = profile.positional_parameters
        if len(parameters) != arity:
            violations.append(
                Violation(
                    code=ViolationCode.POSITIONAL_PARAMETER_COUNT_MISMATCH,
                    subject=operator_id,
                    detail=f"{len(parameters)} parameters for {arity} inputs",
                )
            )
        expected = list(range(len(parameters)))
        if [parameter.index for parameter in parameters] != expected:
            violations.append(
                Violation(
                    code=ViolationCode.POSITIONAL_PARAMETER_INDEX_BROKEN,
                    subject=operator_id,
                    detail="indexes must be 0..n-1 in array order",
                )
            )
        names = [parameter.name for parameter in parameters]
        for name in sorted({name for name in names if names.count(name) > 1}):
            violations.append(
                Violation(
                    code=ViolationCode.POSITIONAL_PARAMETER_NAME_DUPLICATE,
                    subject=operator_id,
                    detail=name,
                )
            )

        _check_proposition_operation(snapshot, operator_id, parsed, violations)

        semantics = profile.function_semantics
        contract = profile.definedness_contract
        if semantics.partiality == "total" and contract is not None:
            violations.append(
                Violation(
                    code=ViolationCode.DEFINEDNESS_CONTRACT_FORBIDDEN, subject=operator_id
                )
            )
        if semantics.partiality == "partial":
            if contract is None:
                violations.append(
                    Violation(
                        code=ViolationCode.DEFINEDNESS_CONTRACT_REQUIRED, subject=operator_id
                    )
                )
            else:
                _check_required_input_indexes(
                    operator_id, contract.required_input_indexes, arity, violations
                )
            quarantine.append(
                QuarantineReason(
                    code="partial_operator_unsupported",
                    subject=operator_id,
                    detail="v1 delivers no content-addressed definedness registry",
                )
            )


def _check_required_input_indexes(
    operator_id: str,
    indexes: tuple[int, ...],
    arity: int,
    violations: list[Violation],
) -> None:
    """Non-empty, unique, and within the operator's inputs."""
    if not indexes:
        violations.append(
            Violation(code=ViolationCode.REQUIRED_INPUT_INDEXES_EMPTY, subject=operator_id)
        )
    for value in sorted({value for value in indexes if indexes.count(value) > 1}):
        violations.append(
            Violation(
                code=ViolationCode.REQUIRED_INPUT_INDEXES_DUPLICATE,
                subject=operator_id,
                detail=str(value),
            )
        )
    for value in sorted({value for value in indexes if value < 0 or value >= arity}):
        violations.append(
            Violation(
                code=ViolationCode.REQUIRED_INPUT_INDEXES_OUT_OF_RANGE,
                subject=operator_id,
                detail=f"{value} outside 0..{arity - 1}",
            )
        )


def _check_proposition_operation(
    snapshot: ParsedSnapshot,
    operator_id: str,
    parsed: ParsedOperator,
    violations: list[Violation],
) -> None:
    """The four closure rules, read against the referenced Concepts' semantic kinds.

    `proposition_operation` is not a descriptive label: it constrains how many Proposition
    inputs the signature may have and what the output may be. Unresolved inputs are skipped
    here -- they are already reported as unresolved references, and counting them as
    non-Propositions would produce a second, misleading violation about the same defect.
    """
    profile = parsed.profile
    record = parsed.record
    operation = profile.proposition_operation

    kinds = [
        snapshot.concepts[input_id].profile.semantic_kind
        for input_id in record.input_concepts
        if input_id in snapshot.concepts
    ]
    if len(kinds) != len(record.input_concepts):
        return
    propositions = sum(1 for kind in kinds if kind == _PROPOSITION_KIND)
    others = len(kinds) - propositions

    output = snapshot.concepts.get(record.output_concept)
    if output is None:
        return
    output_kind = output.profile.semantic_kind
    output_contract = output.profile.literal_value_contract
    output_is_boolean = (
        output_contract is not None and output_contract.codec_id == BOOLEAN_CODEC
    )

    if operation == "none":
        if propositions:
            violations.append(
                Violation(
                    code=ViolationCode.PROPOSITION_OPERATION_INPUT_INVALID,
                    subject=operator_id,
                    detail="none forbids proposition inputs",
                )
            )
        return

    if operation == "modifier":
        if propositions != 1:
            violations.append(
                Violation(
                    code=ViolationCode.PROPOSITION_OPERATION_INPUT_INVALID,
                    subject=operator_id,
                    detail=f"modifier needs exactly 1 proposition input, found {propositions}",
                )
            )
        if output_kind == _PROPOSITION_KIND:
            violations.append(
                Violation(
                    code=ViolationCode.PROPOSITION_OPERATION_OUTPUT_INVALID,
                    subject=operator_id,
                    detail="modifier output must not be a proposition",
                )
            )
        return

    if operation == "attitude":
        if propositions != 1:
            violations.append(
                Violation(
                    code=ViolationCode.PROPOSITION_OPERATION_INPUT_INVALID,
                    subject=operator_id,
                    detail=f"attitude needs exactly 1 proposition input, found {propositions}",
                )
            )
        if others < 1:
            violations.append(
                Violation(
                    code=ViolationCode.PROPOSITION_OPERATION_INPUT_INVALID,
                    subject=operator_id,
                    detail="attitude needs at least one non-proposition holder input",
                )
            )
    elif propositions < 1:
        violations.append(
            Violation(
                code=ViolationCode.PROPOSITION_OPERATION_INPUT_INVALID,
                subject=operator_id,
                detail="relation needs at least one proposition input",
            )
        )

    if not output_is_boolean:
        violations.append(
            Violation(
                code=ViolationCode.PROPOSITION_OPERATION_OUTPUT_INVALID,
                subject=operator_id,
                detail=f"{operation} must output a {BOOLEAN_CODEC} Concept",
            )
        )


def _check_relation_enums(snapshot: ParsedSnapshot, violations: list[Violation]) -> None:
    """`ExternalMapping.relation` and `Lexicalization.surface_relation` must not be confused.

    The two vocabularies are disjoint and the schema already closes each one, so what is
    checked here is the confusion the standard names explicitly: a surface-relation value
    appearing where a mapping relation belongs, or the reverse. Reaching into the raw
    profile payload is necessary because a confused value fails the model's own Literal
    and so never reaches the typed field.
    """
    for kind, entries in (("concept", snapshot.concepts), ("operator", snapshot.operators)):
        for record_id, parsed in sorted(entries.items()):
            raw = parsed.record.supply.get("memory_assertion")
            if not isinstance(raw, dict):
                continue
            payload = cast("dict[str, Any]", raw)
            for mapping in cast("list[Any]", payload.get("external_mappings") or []):
                if not isinstance(mapping, dict):
                    continue
                value = cast("dict[str, Any]", mapping).get("relation")
                if isinstance(value, str) and value in _SURFACE_RELATION_VALUES:
                    violations.append(
                        Violation(
                            code=ViolationCode.RELATION_ENUM_CONFUSED,
                            subject=record_id,
                            detail=f"{kind} external_mappings.relation={value}",
                        )
                    )
            for lexical in cast("list[Any]", payload.get("lexicalizations") or []):
                if not isinstance(lexical, dict):
                    continue
                value = cast("dict[str, Any]", lexical).get("surface_relation")
                if isinstance(value, str) and value in _MAPPING_RELATION_VALUES:
                    violations.append(
                        Violation(
                            code=ViolationCode.RELATION_ENUM_CONFUSED,
                            subject=record_id,
                            detail=f"{kind} lexicalizations.surface_relation={value}",
                        )
                    )


def _check_source_attestations(snapshot: ParsedSnapshot, violations: list[Violation]) -> None:
    """The conditional matrix of section 6.2, per source kind.

    A lemma without a precise sense or roleset may not claim WordNet or PropBank as its
    source -- it has to say `human` or `domain_corpus` instead. The point is that an
    attestation names something re-checkable, not merely something plausible.
    """
    requirements: dict[str, tuple[bool, bool]] = {
        "wordnet": (True, False),
        "propbank": (False, True),
        "schema_org": (False, False),
        "human": (False, False),
        "domain_corpus": (False, False),
    }
    for kind, entries in (("concept", snapshot.concepts), ("operator", snapshot.operators)):
        for record_id, parsed in sorted(entries.items()):
            for lexical in parsed.profile.lexicalizations:
                for attestation in lexical.source_attestations:
                    needs_sense, needs_roleset = requirements[attestation.source_kind]
                    has_sense = attestation.sense_id is not None
                    has_roleset = attestation.roleset_id is not None
                    problems: list[str] = []
                    if needs_sense != has_sense:
                        problems.append("sense_id" if needs_sense else "sense_id forbidden")
                    if needs_roleset != has_roleset:
                        problems.append(
                            "roleset_id" if needs_roleset else "roleset_id forbidden"
                        )
                    for problem in problems:
                        violations.append(
                            Violation(
                                code=ViolationCode.SOURCE_ATTESTATION_FIELDS_INVALID,
                                subject=record_id,
                                detail=f"{kind} {attestation.source_kind}: {problem}",
                            )
                        )


def _cycle_members(snapshot: ParsedSnapshot) -> set[str]:
    """Concepts that lie on an inheritance cycle.

    Reported per member rather than once per cycle: a builder fixes one edge at a time, and
    naming every participant says where those edges are. Self-parents are excluded because
    they have their own, more specific code.
    """
    unvisited = set(snapshot.concepts)
    on_cycle: set[str] = set()
    while unvisited:
        start = next(iter(unvisited))
        path: list[str] = []
        index: dict[str, int] = {}
        current: str | None = start
        while current is not None:
            if current in index:
                on_cycle.update(path[index[current] :])
                break
            if current not in unvisited:
                break
            index[current] = len(path)
            path.append(current)
            unvisited.discard(current)
            parsed = snapshot.concepts.get(current)
            parents = [
                parent
                for parent in (parsed.record.parents if parsed else ())
                if parent != current and parent in snapshot.concepts
            ]
            current = parents[0] if parents else None
        for member in path:
            unvisited.discard(member)
    return on_cycle
