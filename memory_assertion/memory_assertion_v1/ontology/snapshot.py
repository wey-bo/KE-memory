"""A snapshot as the validator sees it: parsed records, from any source.

This is the piece that separates a library from the conformance harness. That harness
reaches its input through a function that reads one fixture path, so its checks can only
ever describe that one snapshot. Here the input is a mapping of shard documents, so the
same checks apply to a fixture, a build in progress, or a snapshot arriving over the
wire.

Parsing is deliberately fault-tolerant. A record that fails to parse becomes a violation
carried alongside the records that did parse, because a validator that raises on the
first malformed field cannot answer the question a builder actually has: what is wrong
with this snapshot, all of it.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, cast

from pydantic import ValidationError

from memory_assertion_v1.ontology.profile import ConceptProfile, OperatorProfile
from memory_assertion_v1.ontology.records import ConceptRecord, OntologyRecord, OperatorRecord
from memory_assertion_v1.ontology.violations import Violation, ViolationCode

PROFILE_NAMESPACE = "memory_assertion"


class ParsedConcept:
    """A Concept whose upstream record and profile both parsed."""

    __slots__ = ("profile", "record")

    def __init__(self, record: ConceptRecord, profile: ConceptProfile) -> None:
        self.record = record
        self.profile = profile

    @property
    def id(self) -> str:
        return self.record.id

    @property
    def symbol(self) -> str:
        return self.record.canonical_name


class ParsedOperator:
    """An Operator whose upstream record and profile both parsed."""

    __slots__ = ("profile", "record")

    def __init__(self, record: OperatorRecord, profile: OperatorProfile) -> None:
        self.record = record
        self.profile = profile

    @property
    def id(self) -> str:
        return self.record.id

    @property
    def symbol(self) -> str:
        return self.record.canonical_name


class ParsedSnapshot:
    """Everything the semantic checks read, plus whatever failed to parse.

    Concepts and Operators are keyed by id for closure lookups. Records that could not be
    keyed -- a missing or malformed id -- are absent from both maps and represented only
    by their parse violation, since there is no identity under which to file them.
    """

    __slots__ = ("concepts", "ontology", "operators", "parse_violations")

    def __init__(
        self,
        *,
        ontology: OntologyRecord | None,
        concepts: dict[str, ParsedConcept],
        operators: dict[str, ParsedOperator],
        parse_violations: list[Violation],
    ) -> None:
        self.ontology = ontology
        self.concepts = concepts
        self.operators = operators
        self.parse_violations = parse_violations


def _profile_payload(supply: dict[str, Any]) -> Any:
    return supply.get(PROFILE_NAMESPACE)


def _first_error_location(error: ValidationError) -> str:
    details = error.errors()
    if not details:
        return ""
    return ".".join(str(part) for part in details[0]["loc"])


def _record_identity(payload: Any, index: int, kind: str) -> str:
    """A stable handle for a record that may not have parsed.

    Falls back to shard position, because a violation about a record with a malformed id
    still has to name something a builder can find.
    """
    if isinstance(payload, dict):
        candidate = cast("dict[str, Any]", payload).get("id")
        if isinstance(candidate, str) and candidate:
            return candidate
    return f"{kind}[{index}]"


def _parse_pair(
    payload: Any,
    index: int,
    kind: str,
    record_type: type[ConceptRecord] | type[OperatorRecord],
    profile_type: type[ConceptProfile] | type[OperatorProfile],
    violations: list[Violation],
) -> tuple[ConceptRecord | OperatorRecord, ConceptProfile | OperatorProfile] | None:
    """Parse one record and its profile, or file violations and return None.

    Both halves must succeed to be usable: a record without its profile cannot be checked
    against the profile's rules, and a profile without its record has no identity. Either
    failure is reported and the pair is dropped from the maps, so later checks operate
    only on records they can fully read.
    """
    subject = _record_identity(payload, index, kind)
    try:
        record = record_type.model_validate(payload)
    except ValidationError as error:
        violations.append(
            Violation(
                code=ViolationCode.RECORD_PARSE_FAILED,
                subject=subject,
                detail=_first_error_location(error),
            )
        )
        return None

    profile_payload = _profile_payload(record.supply)
    if profile_payload is None:
        violations.append(
            Violation(code=ViolationCode.PROFILE_MISSING, subject=record.id, detail=kind)
        )
        return None
    try:
        profile = profile_type.model_validate(profile_payload)
    except ValidationError as error:
        violations.append(
            Violation(
                code=ViolationCode.PROFILE_PARSE_FAILED,
                subject=record.id,
                detail=_first_error_location(error),
            )
        )
        return None
    return record, profile


def parse_snapshot(documents: Iterable[dict[str, Any]]) -> ParsedSnapshot:
    """Build a snapshot view from shard documents in any order.

    Shards are identified by their single top-level field, as upstream requires. A
    document carrying more than one of `ontology`/`concepts`/`operators` is rejected
    rather than partially read: the mutually exclusive top level is what lets a shard be
    hashed and served independently, so a mixed file is not a shard.

    Duplicate ids are detected here rather than in validation, because the maps this
    returns are keyed by id and a silent overwrite would erase the evidence.
    """
    violations: list[Violation] = []
    ontology: OntologyRecord | None = None
    concepts: dict[str, ParsedConcept] = {}
    operators: dict[str, ParsedOperator] = {}

    for position, document in enumerate(documents):
        present = [key for key in ("ontology", "concepts", "operators") if key in document]
        if len(present) != 1:
            violations.append(
                Violation(
                    code=ViolationCode.SHARD_MIXES_ARTIFACT_KINDS,
                    subject=f"document[{position}]",
                    detail=",".join(sorted(present)),
                )
            )
            continue
        kind = present[0]
        if kind == "ontology":
            try:
                ontology = OntologyRecord.model_validate(document["ontology"])
            except ValidationError as error:
                violations.append(
                    Violation(
                        code=ViolationCode.RECORD_PARSE_FAILED,
                        subject=f"ontology[{position}]",
                        detail=_first_error_location(error),
                    )
                )
            continue
        entries = cast("list[Any]", document[kind])
        for index, payload in enumerate(entries):
            if kind == "concepts":
                parsed = _parse_pair(
                    payload, index, "concept", ConceptRecord, ConceptProfile, violations
                )
                if parsed is None:
                    continue
                record, profile = parsed
                assert isinstance(record, ConceptRecord)
                assert isinstance(profile, ConceptProfile)
                if record.id in concepts:
                    violations.append(
                        Violation(code=ViolationCode.DUPLICATE_CONCEPT_ID, subject=record.id)
                    )
                    continue
                concepts[record.id] = ParsedConcept(record, profile)
            else:
                parsed = _parse_pair(
                    payload, index, "operator", OperatorRecord, OperatorProfile, violations
                )
                if parsed is None:
                    continue
                record, profile = parsed
                assert isinstance(record, OperatorRecord)
                assert isinstance(profile, OperatorProfile)
                if record.id in operators:
                    violations.append(
                        Violation(code=ViolationCode.DUPLICATE_OPERATOR_ID, subject=record.id)
                    )
                    continue
                operators[record.id] = ParsedOperator(record, profile)

    if ontology is None:
        violations.append(
            Violation(code=ViolationCode.ONTOLOGY_RECORD_MISSING, subject="snapshot")
        )

    return ParsedSnapshot(
        ontology=ontology,
        concepts=concepts,
        operators=operators,
        parse_violations=violations,
    )
