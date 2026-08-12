"""Candidate generation over the three sources.

Candidates are pairs that *might* denote the same thing. Generation is allowed to be
generous -- it only adds candidates, never decides identity -- but it must be honest about what
kind of evidence it found, because that classification is what caps how far a candidate can go.

For these three corpora the honest answer is narrow. schema.org asserts 55 `equivalentClass`
and 117 `equivalentProperty` links, but every target is a foreign vocabulary (`unece:`, `gs1:`,
`eli:`), so none of them connects two of these sources. PropBank's `lexlink`/`rolelink` reach
VerbNet and FrameNet only. That leaves shared surface forms, which are `lexical_match` and can
never promote on their own -- 78% of the WordNet/PropBank overlap is polysemous on at least one
side, so a shared lemma is weak evidence even where it is suggestive.

Hierarchy and definition entries are attached where the sources supply them, as corroboration
and as context for a reviewer. They are necessary conditions at most, never sufficient.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from memory_assertion_v1.alignment.evidence import (
    CandidatePair,
    EvidenceEntry,
    MemberKind,
    SourceRecordRef,
    lexical_evidence,
    make_candidate,
)
from memory_assertion_v1.alignment.canonical_bytes import normalize_text
from memory_assertion_v1.sources.records import (
    PropBankRolesetRecord,
    SchemaOrgTermRecord,
    WordNetSenseRecord,
)


def _wordnet_ref(record: WordNetSenseRecord) -> SourceRecordRef:
    return SourceRecordRef(
        source="wordnet",
        artifact_sha256=record.location.artifact_sha256,
        member_path=record.location.member_path,
        native_id=record.namespaced_id,
    )


def _propbank_ref(record: PropBankRolesetRecord) -> SourceRecordRef:
    return SourceRecordRef(
        source="propbank",
        artifact_sha256=record.location.artifact_sha256,
        member_path=record.location.member_path,
        native_id=record.namespaced_id,
    )


def _schemaorg_ref(record: SchemaOrgTermRecord) -> SourceRecordRef:
    return SourceRecordRef(
        source="schema_org",
        artifact_sha256=record.location.artifact_sha256,
        member_path=record.location.member_path,
        native_id=record.namespaced_id,
    )


def surface_key(text: str) -> str:
    """The comparison key for candidate generation only.

    Underscores become spaces because the sources spell multi-word entries differently, and case
    is folded *here* because this key decides whether to look at a pair at all. It is not the
    lexicalization index key -- that one applies NFC and nothing else, since folding case there
    would merge `Person` and `person`, which are different Concepts.
    """
    return normalize_text(text).replace("_", " ").casefold()


def _definition_entry(source: str, text: str) -> EvidenceEntry | None:
    if not text.strip():
        return None
    excerpt = text.strip().replace("\n", " ")[:160]
    return EvidenceEntry(
        evidence_kind="definition",
        polarity="context_only",
        detail=f"{source} definition: {excerpt}",
    )


def _hierarchy_entry(source: str, parents: tuple[str, ...]) -> EvidenceEntry | None:
    if not parents:
        return None
    return EvidenceEntry(
        evidence_kind="hierarchy",
        polarity="context_only",
        detail=f"{source} parents: {', '.join(sorted(parents)[:4])}",
    )


def _signature_entry(record: PropBankRolesetRecord) -> EvidenceEntry:
    return EvidenceEntry(
        evidence_kind="signature",
        polarity="context_only",
        detail=f"propbank arity {len(record.roles)} for {record.roleset_id}",
    )


def wordnet_propbank_candidates(
    wordnet: Iterable[WordNetSenseRecord], propbank: Iterable[PropBankRolesetRecord]
) -> Iterator[CandidatePair]:
    """Pair WordNet senses with PropBank rolesets that share a surface form.

    Every pair produced here rests on `lexical_match` plus context, so none of them can be
    promoted. They are still emitted: the quarantine record of a candidate that was considered
    and could not be established is the auditable part of this layer's output.
    """
    by_surface: dict[str, list[PropBankRolesetRecord]] = {}
    for roleset in propbank:
        by_surface.setdefault(surface_key(roleset.predicate_lemma), []).append(roleset)

    for sense in wordnet:
        key = surface_key(sense.lemma)
        for roleset in by_surface.get(key, ()):
            evidence: list[EvidenceEntry] = [lexical_evidence(sense.lemma)]
            evidence.append(_signature_entry(roleset))
            definition = _definition_entry("propbank", roleset.name)
            if definition is not None:
                evidence.append(definition)
            yield make_candidate(
                _wordnet_ref(sense), _propbank_ref(roleset), "operator", tuple(evidence)
            )


def wordnet_schemaorg_candidates(
    wordnet: Iterable[WordNetSenseRecord], schemaorg: Iterable[SchemaOrgTermRecord]
) -> Iterator[CandidatePair]:
    """Pair WordNet senses with schema.org classes that share a surface form.

    Restricted to classes: a WordNet noun sense and a schema.org property are not candidates for
    the same Concept identity, and generating those pairs would add noise a reviewer has to
    dismiss rather than evidence.
    """
    by_surface: dict[str, list[SchemaOrgTermRecord]] = {}
    for term in schemaorg:
        if term.term_kind != "class":
            continue
        by_surface.setdefault(surface_key(term.label), []).append(term)

    for sense in wordnet:
        for term in by_surface.get(surface_key(sense.lemma), ()):
            evidence: list[EvidenceEntry] = [lexical_evidence(sense.lemma)]
            hierarchy = _hierarchy_entry("schema_org", term.parents)
            if hierarchy is not None:
                evidence.append(hierarchy)
            definition = _definition_entry("schema_org", term.comment)
            if definition is not None:
                evidence.append(definition)
            yield make_candidate(
                _wordnet_ref(sense), _schemaorg_ref(term), "concept", tuple(evidence)
            )


def propbank_schemaorg_candidates(
    propbank: Iterable[PropBankRolesetRecord], schemaorg: Iterable[SchemaOrgTermRecord]
) -> Iterator[CandidatePair]:
    """Pair PropBank rolesets with schema.org properties that share a surface form."""
    by_surface: dict[str, list[SchemaOrgTermRecord]] = {}
    for term in schemaorg:
        if term.term_kind != "property":
            continue
        by_surface.setdefault(surface_key(term.label), []).append(term)

    for roleset in propbank:
        for term in by_surface.get(surface_key(roleset.predicate_lemma), ()):
            evidence: list[EvidenceEntry] = [
                lexical_evidence(roleset.predicate_lemma),
                _signature_entry(roleset),
            ]
            definition = _definition_entry("schema_org", term.comment)
            if definition is not None:
                evidence.append(definition)
            yield make_candidate(
                _propbank_ref(roleset), _schemaorg_ref(term), "operator", tuple(evidence)
            )


def foreign_equivalence_note(record: SchemaOrgTermRecord, targets: tuple[str, ...]) -> str:
    """Record a source-asserted link whose target is outside these three sources.

    Kept rather than dropped. These are genuine source-asserted equivalences and become
    `ExternalMapping` entries once a Canonical owner exists -- they simply cannot bridge two of
    these corpora, which is a fact about the corpora and not a defect in the link.
    """
    return f"{record.term_id} asserts equivalence to {', '.join(sorted(targets))}"


def candidate_kind(left: SourceRecordRef, right: SourceRecordRef) -> MemberKind:
    """Concept unless either side is a PropBank roleset, which is always an Operator."""
    return "operator" if "propbank" in {left.source, right.source} else "concept"
