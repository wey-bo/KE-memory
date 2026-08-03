"""Mapper v2 candidate generation: structural evidence, with no-map as a native outcome.

The design follows directly from what failed. Mapper v1 asked "does this utterance contain a word
listed in an ontology alias?", which cannot distinguish attesting a preference from merely using a
word that appears in a preference alias. No threshold repairs that, because the question itself is
wrong.

So candidates are generated from four kinds of evidence, and each kind is *named on the candidate*
rather than collapsed into one score:

``PREDICATE_ROLESET``
    A PropBank roleset matched, so the utterance has a predicate with the arity that roleset
    declares. This is the strongest evidence available: it says something about structure, not
    vocabulary.

``ONTOLOGY_ALIAS``
    An ontology alias matched, optionally reached through WordNet morphology so ``cancelled`` finds
    ``cancel``. This is v1's only evidence type, kept but demoted.

``SCHEMA_TYPE``
    A schema.org type or property name matched, which suits entity-like and attribute-like mentions.

``LEXICAL_SENSE``
    A WordNet lemma matched with low polysemy. A term with one sense is far better evidence than a
    term with fifteen, and v1 treated both identically.

No-map is produced by :func:`generate`, not by a downstream filter. A gate that rejects a candidate
after the fact measures the gate; a generator that returns nothing is a mapper that declined. The
distinction matters because v1's abstain path was exactly such a filter, and it never worked.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from ke_memory_demo.core.json import JsonObject

from .source_indices import SourceIndices, content_terms


class EvidenceKind(StrEnum):
    """What kind of evidence supports a candidate. Ordered strongest to weakest."""

    PREDICATE_ROLESET = "predicate_roleset"
    ONTOLOGY_ALIAS = "ontology_alias"
    SCHEMA_TYPE = "schema_type"
    LEXICAL_SENSE = "lexical_sense"


# How much each kind counts. Structural evidence outweighs vocabulary evidence, which is the whole
# correction over v1: these are not tuned thresholds but an ordering of evidence quality, and the
# ordering is the claim being tested.
EVIDENCE_WEIGHT: dict[EvidenceKind, float] = {
    EvidenceKind.PREDICATE_ROLESET: 1.0,
    EvidenceKind.ONTOLOGY_ALIAS: 0.7,
    EvidenceKind.SCHEMA_TYPE: 0.5,
    EvidenceKind.LEXICAL_SENSE: 0.25,
}

# A WordNet lemma with more senses than this is too ambiguous to be evidence on its own. Not a tuned
# cutoff: it separates "one clear sense" from "a word that means many things".
MAX_POLYSEMY_FOR_EVIDENCE = 4

# Words that cannot support a mapping regardless of what they match. Kept small on purpose: v1's
# large stopword list deleted terms the ontology needed as aliases, so exclusion is narrow and the
# work is done by evidence kind instead.
_NON_EVIDENCE = frozenset(
    {
        "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "is", "are",
        "was", "were", "be", "am", "it", "this", "that", "i", "my", "me", "you", "your",
        "we", "they", "he", "she", "his", "her", "do", "does", "did", "have", "has", "had",
        "not", "no", "so", "if", "but", "as", "at", "by", "from",
    }
)

_ID_WORD = re.compile(r"[a-z][a-z0-9]*")

# Verbs that have PropBank rolesets but carry no lexical content: copulas, auxiliaries and light
# verbs. Their rolesets are real, which is exactly the trap — "the weather has been mild" matched
# three predicates through be.01, because a copula has argument structure while saying nothing about
# what is being asserted. Excluded from structural evidence, not from the text.
_LIGHT_VERBS = frozenset(
    {
        "be", "is", "are", "was", "were", "been", "being", "am",
        "have", "has", "had", "having",
        "do", "does", "did", "doing",
        "get", "got", "gets", "getting",
        "go", "goes", "went", "going",
        "make", "makes", "made", "making",
        "take", "takes", "took", "taking",
        "give", "gives", "gave", "giving",
        "come", "comes", "came", "coming",
        "say", "says", "said", "saying",
        "keep", "kept", "keeping",
        "seem", "seems", "seemed",
        "become", "becomes", "became",
    }
)


@dataclass(frozen=True)
class Evidence:
    """One piece of support for a candidate, with the source that produced it."""

    kind: EvidenceKind
    term: str
    detail: str

    @property
    def weight(self) -> float:
        return EVIDENCE_WEIGHT[self.kind]

    @property
    def is_standalone(self) -> bool:
        """Whether this piece of evidence could support a mapping on its own.

        A predicate roleset or a schema.org type says something about the utterance's structure. A
        single-word alias is the ontology's own claim that this word denotes the item. A term found
        inside a longer alias, or a merely low-polysemy lemma, says nothing on its own.
        """
        if self.kind in {EvidenceKind.PREDICATE_ROLESET, EvidenceKind.SCHEMA_TYPE}:
            return True
        return self.kind is EvidenceKind.ONTOLOGY_ALIAS and self.detail in {
            "single-word alias",
            "whole phrase alias",
        }


@dataclass(frozen=True)
class Candidate:
    """One ontology item, the evidence for it, and what that evidence adds up to."""

    ontology_id: str
    sense: str
    evidence: tuple[Evidence, ...]

    @property
    def score(self) -> float:
        return round(sum(item.weight for item in self.evidence), 6)

    @property
    def kinds(self) -> frozenset[EvidenceKind]:
        return frozenset(item.kind for item in self.evidence)

    @property
    def has_structural_evidence(self) -> bool:
        """Whether anything beyond vocabulary matching supports this candidate."""
        return bool(
            self.kinds & {EvidenceKind.PREDICATE_ROLESET, EvidenceKind.SCHEMA_TYPE}
        )

    @property
    def is_admissible(self) -> bool:
        """Whether this candidate may be offered at all.

        A candidate needs at least one piece of evidence that could stand alone. Measured on
        discovery turns, the residual false mappings were carried by a *phrase* alias term plus a
        low-polysemy lemma: "Mm hmm right okay then" produced two candidates because ``then`` appears
        inside some multi-word alias and has three WordNet senses. Neither fact is evidence about
        this utterance, so neither is admissible by itself.
        """
        return any(item.is_standalone for item in self.evidence)

    def as_json(self) -> JsonObject:
        return {
            "ontology_id": self.ontology_id,
            "sense": self.sense,
            "score": self.score,
            "evidence": [
                {"kind": str(item.kind), "term": item.term, "detail": item.detail}
                for item in self.evidence
            ],
            "has_structural_evidence": self.has_structural_evidence,
        }


@dataclass(frozen=True)
class OntologyEntry:
    """One ontology item, indexed by the terms that can evoke it."""

    ontology_id: str
    sense: str
    item_type: str
    alias_terms: frozenset[str]
    # Single-word aliases are the decisive ones: a stopword that *is* an alias carries meaning, while
    # the same word inside a phrase does not.
    decisive_aliases: frozenset[str]
    # Multi-word aliases kept whole. Indexing their words separately let "work" reach
    # event.attempt_failed through the alias "didn't work", and a PropBank roleset for the bare verb
    # then made that look structural. A phrase is evidence only when the phrase appears.
    phrase_aliases: frozenset[str] = frozenset()


def build_ontology_entries(items: Sequence[JsonObject]) -> tuple[OntologyEntry, ...]:
    """Index ontology items by alias and id terms."""
    entries: list[OntologyEntry] = []
    for wrapper in items:
        item = wrapper.get("item") if "item" in wrapper else wrapper
        if not isinstance(item, dict):
            continue
        ontology_id = str(item.get("id", ""))
        if not ontology_id:
            continue
        aliases = item.get("aliases")
        alias_terms: set[str] = set()
        decisive: set[str] = set()
        phrases: set[str] = set()
        if isinstance(aliases, list):
            for alias in aliases:
                words = _ID_WORD.findall(str(alias).lower())
                if len(words) == 1:
                    alias_terms.update(words)
                    decisive.update(words)
                elif words:
                    phrases.add(" ".join(words))
        tail = ontology_id.split(":", 1)[-1].replace(".", " ").replace("_", " ")
        alias_terms.update(_ID_WORD.findall(tail))
        entries.append(
            OntologyEntry(
                ontology_id=ontology_id,
                sense=str(item.get("sense", "")),
                item_type=str(wrapper.get("item_type", "")),
                alias_terms=frozenset(alias_terms),
                decisive_aliases=frozenset(decisive),
                phrase_aliases=frozenset(phrases),
            )
        )
    return tuple(entries)


class CandidateGenerator:
    """Generate candidates from structural and vocabulary evidence, or decline."""

    def __init__(
        self,
        entries: Sequence[OntologyEntry],
        indices: SourceIndices,
        *,
        top_k: int = 5,
    ) -> None:
        self._entries = tuple(entries)
        self._indices = indices
        self._top_k = top_k
        # Which ontology entries a term can reach, so generation does not scan every item per term.
        self._by_term: dict[str, tuple[OntologyEntry, ...]] = {}
        term_map: dict[str, list[OntologyEntry]] = {}
        for entry in self._entries:
            for term in entry.alias_terms:
                term_map.setdefault(term, []).append(entry)
        self._by_term = {term: tuple(items) for term, items in term_map.items()}
        # Phrase aliases are matched against the whole utterance, so they need their own index.
        self._phrase_entries = tuple(
            (phrase, entry)
            for entry in self._entries
            for phrase in entry.phrase_aliases
        )

    def generate(self, text: str) -> tuple[Candidate, ...]:
        """Candidates for one utterance, strongest first. Empty means the mapper declined."""
        raw_terms = content_terms(text)
        if not raw_terms:
            return ()

        wordnet = self._indices.wordnet
        propbank = self._indices.propbank
        schemaorg = self._indices.schemaorg

        # Base forms, so natural inflection reaches an alias without the ontology listing every form.
        normalised: list[tuple[str, str]] = []
        for term in raw_terms:
            if term in _NON_EVIDENCE or len(term) < 3:
                continue
            normalised.append((term, wordnet.base_form(term)))

        if not normalised:
            return ()

        collected: dict[str, list[Evidence]] = {}

        def add(entry: OntologyEntry, evidence: Evidence) -> None:
            collected.setdefault(entry.ontology_id, []).append(evidence)

        senses = {entry.ontology_id: entry.sense for entry in self._entries}

        # Whole-phrase aliases, checked against the utterance rather than word by word.
        lowered = " ".join(raw_terms)
        for phrase, entry in self._phrase_entries:
            if phrase in lowered:
                collected.setdefault(entry.ontology_id, []).append(
                    Evidence(
                        kind=EvidenceKind.ONTOLOGY_ALIAS,
                        term=phrase,
                        detail="whole phrase alias",
                    )
                )

        for surface, base in normalised:
            for candidate_term in {surface, base}:
                entries = self._by_term.get(candidate_term, ())
                if not entries:
                    continue

                rolesets = propbank.rolesets_for(candidate_term)
                schema_type = schemaorg.type_for(candidate_term)
                schema_property = schemaorg.property_for(candidate_term)
                polysemy = wordnet.polysemy(candidate_term)

                for entry in entries:
                    # A predicate roleset is the strongest signal: it reports argument structure
                    # rather than the presence of a word.
                    if (
                        rolesets
                        and candidate_term not in _LIGHT_VERBS
                        and entry.item_type in {"predicate_sense", "event_type"}
                    ):
                        best = rolesets[0]
                        add(
                            entry,
                            Evidence(
                                kind=EvidenceKind.PREDICATE_ROLESET,
                                term=candidate_term,
                                detail=f"{best.roleset_id} arity {best.arity}",
                            ),
                        )
                    if candidate_term in entry.decisive_aliases:
                        add(
                            entry,
                            Evidence(
                                kind=EvidenceKind.ONTOLOGY_ALIAS,
                                term=candidate_term,
                                detail="single-word alias",
                            ),
                        )
                    if (schema_type or schema_property) and entry.item_type in {
                        "attribute_type",
                        "state_type",
                    }:
                        add(
                            entry,
                            Evidence(
                                kind=EvidenceKind.SCHEMA_TYPE,
                                term=candidate_term,
                                detail=str(schema_type or schema_property),
                            ),
                        )
                    if 0 < polysemy <= MAX_POLYSEMY_FOR_EVIDENCE:
                        add(
                            entry,
                            Evidence(
                                kind=EvidenceKind.LEXICAL_SENSE,
                                term=candidate_term,
                                detail=f"{polysemy} WordNet sense(s)",
                            ),
                        )

        candidates = [
            candidate
            for candidate in (
                Candidate(
                    ontology_id=ontology_id,
                    sense=senses.get(ontology_id, ""),
                    evidence=tuple(_dedupe(evidence)),
                )
                for ontology_id, evidence in collected.items()
            )
            # Declining happens here, in generation, rather than in a filter downstream.
            if candidate.is_admissible
        ]
        # Structural evidence first, then score. A candidate resting only on vocabulary cannot
        # outrank one with argument structure behind it, which is the ordering v1 got backwards.
        candidates.sort(
            key=lambda c: (
                -int(c.has_structural_evidence),
                -c.score,
                c.ontology_id,
            )
        )
        return tuple(candidates[: self._top_k])

    def provenance(self) -> dict[str, Any]:
        return {
            "top_k": self._top_k,
            "ontology_entries": len(self._entries),
            "indexed_terms": len(self._by_term),
            "evidence_weights": {str(k): v for k, v in EVIDENCE_WEIGHT.items()},
            "max_polysemy_for_evidence": MAX_POLYSEMY_FOR_EVIDENCE,
            "no_map_is_native": (
                "generate returns an empty tuple when no evidence supports any item. There is no "
                "downstream gate, because a gate measures the gate rather than the mapper."
            ),
            "sources": self._indices.provenance(),
        }


def _dedupe(evidence: Sequence[Evidence]) -> list[Evidence]:
    """One piece of evidence per kind and term, so a repeated word cannot inflate a score."""
    seen: set[tuple[EvidenceKind, str]] = set()
    unique: list[Evidence] = []
    for item in evidence:
        key = (item.kind, item.term)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique
