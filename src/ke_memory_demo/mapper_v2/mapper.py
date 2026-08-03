"""Mapper v2: candidate generation, ranking, ambiguity and a native abstain path.

Mapper v1 failed a diagnostic in a specific way worth naming: on 1500 discovery turns it abstained
on 9.8 percent and returned ``ambiguous`` on 78.8 percent, and on the authored probe it mis-mapped
all four negatives. A mapper that almost never declines cannot be measured on natural conversation,
where most turns evoke nothing at all.

The cause was not the floor being slightly too low. It was that v1 had no notion of a *decisive*
match. Every candidate scored by term overlap, so generic words carried real weight: a turn matched
``l1:attribute.place`` because it contained ``any`` and ``area``, and matched
``l1:predicate.commit_to_arrangement`` because it contained ``make`` and ``future``. Overlap of that
kind is evidence of nothing.

Four changes, all derived from discovery-split behaviour and none from the retired 18 probe cases:

- **Discriminative weighting.** A term appearing across many ontology items carries almost no
  information, so its contribution is discounted by how widely it is shared. This is the change that
  makes generic-word matches collapse.
- **Native abstain.** Declining is a first-class outcome with its own criteria — no decisive evidence,
  or only generic evidence — rather than the residue of failing a threshold.
- **Evidence requirement.** A mapping needs at least one term that is genuinely characteristic of the
  item it maps to. Breadth of weak overlap can no longer substitute for one good match.
- **Ambiguity on comparable strength.** Ambiguity is reported when two candidates are both
  well-supported and close, not whenever two weak candidates happen to be adjacent.

The blindness contract is unchanged: input is an utterance and a speaker, and there is no correction
gate.
"""

from __future__ import annotations

import ast
import hashlib
import math
import re
from collections import Counter
from collections.abc import Sequence
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ke_memory_demo.core.json import JsonObject, canonical_json
from ke_memory_demo.mapper_v1.mapper import (
    FORBIDDEN_INPUT_FIELDS,
    FrozenOntology,
    Layer,
    MapperError,
    MapperInput,
    Resolution,
)

NonEmptyString = Annotated[str, Field(min_length=1)]

MAPPER_ID = "mapper-v2-discriminative"
MAPPER_VERSION = "2.0.0"

# A term shared by at least this fraction of items in a layer is treated as generic and cannot, on
# its own, support a mapping.
GENERIC_TERM_SHARE = 0.15

# Terms that are frequent in ordinary conversation and also happen to be ontology aliases. Item
# frequency cannot detect these: a word can evoke exactly one ontology item and still be useless
# evidence because people say it constantly. Measured from discovery turns, these were the terms
# carrying v1's false mappings, so they are named rather than inferred.
CONVERSATIONAL_FILLER: frozenset[str] = frozenset(
    {
        "time", "day", "week", "month", "year", "today", "tomorrow", "yesterday",
        "thing", "things", "way", "lot", "bit", "kind", "sort", "part", "place",
        "area", "people", "person", "one", "two", "new", "old", "good", "great",
        "best", "better", "nice", "big", "small", "long", "short", "next", "last",
        "first", "own", "still", "even", "back", "right", "left", "sure", "maybe",
        "actually", "definitely", "probably", "already", "always", "never", "often",
        "usually", "recently", "soon", "now", "then", "again", "around", "away",
        "something", "anything", "everything", "nothing", "someone", "anyone",
        "let", "say", "said", "tell", "told", "ask", "asked", "give", "gave",
        "take", "took", "put", "keep", "kept", "find", "found", "use", "used",
        "try", "tried", "start", "started", "end", "ended", "work", "works",
        "check", "sounds", "seems", "feel", "felt", "hope", "wish", "guess",
        "went", "came", "gone", "coming", "getting", "doing", "having", "looking",
    }
)


class AbstainReason(StrEnum):
    """Why the mapper declined. Recorded, because "no mapping" has several causes."""

    NO_CONTENT_TERMS = "no_content_terms"
    NO_CANDIDATE_MATCHED = "no_candidate_matched"
    ONLY_GENERIC_EVIDENCE = "only_generic_evidence"
    BELOW_EVIDENCE_THRESHOLD = "below_evidence_threshold"


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CandidateV2(_Record):
    """One considered item, with the evidence that supported it and how strong that was."""

    ontology_id: NonEmptyString
    sense: str
    layer: Layer
    score: float = Field(ge=0.0)
    matched_terms: tuple[str, ...]
    discriminative_terms: tuple[str, ...]

    @property
    def has_decisive_evidence(self) -> bool:
        return bool(self.discriminative_terms)


class MappingRecordV2(_Record):
    """The raw result. Preserved as produced, with the abstain reason when it declined."""

    expression_id: NonEmptyString
    layer: Layer
    candidates: tuple[CandidateV2, ...]
    resolution: Resolution
    top_ontology_id: str = ""
    top_sense: str = ""
    ambiguity_margin: float | None = None
    abstain_reason: AbstainReason | None = None

    @model_validator(mode="after")
    def _validate(self) -> MappingRecordV2:
        if self.resolution is Resolution.UNRESOLVED:
            if self.top_ontology_id:
                raise MapperError("an unresolved mapping must not name a top candidate")
            if self.abstain_reason is None:
                raise MapperError(
                    "an unresolved mapping must record why it declined; an unexplained abstain "
                    "cannot be diagnosed"
                )
        elif not self.candidates:
            raise MapperError("a resolved mapping requires at least one candidate")
        return self


_WORD = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    {
        "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "is", "are",
        "was", "were", "be", "been", "being", "at", "by", "from", "as", "it", "its", "this",
        "that", "these", "those", "i", "my", "me", "mine", "you", "your", "yours", "we",
        "our", "they", "them", "their", "he", "she", "his", "her", "hers", "do", "does",
        "did", "have", "has", "had", "will", "would", "can", "could", "should", "may",
        "might", "must", "not", "no", "yes", "so", "if", "then", "than", "but", "or",
        "what", "when", "where", "which", "who", "whom", "how", "why", "any", "some",
        "all", "both", "each", "very", "just", "also", "too", "there", "here", "about",
        "into", "over", "under", "out", "up", "down", "such", "same", "other", "more",
        "most", "much", "many", "few", "own", "get", "got", "make", "made", "like",
        "want", "need", "know", "think", "see", "look", "go", "going", "come", "help",
        "thanks", "thank", "please", "okay", "yeah", "hmm", "well", "sure", "really",
    }
)


def terms(text: str, *, protected: frozenset[str] = frozenset()) -> set[str]:
    """Content terms, keeping any term the ontology relies on as an alias.

    A fixed stopword list cannot be applied blindly here. Removing ``like`` made "I really like jazz
    records" unmappable, because ``like`` is precisely the alias carrying
    ``l1:predicate.hold_attitude`` — the stopword list was deleting the word that expressed the
    preference. Fourteen of these collisions exist in the seed ontology, including ``than`` for the
    comparative and threshold preferences and ``please`` for directed modality.

    So a stopword is dropped unless the ontology declares it an alias. Such terms survive extraction
    and are then handled by weighting rather than exclusion: they are common, so their discriminative
    weight is low, but a genuine alias match is no longer invisible.
    """
    found = {t for t in _WORD.findall(text.lower()) if len(t) > 2}
    return {t for t in found if t not in _STOPWORDS or t in protected}


class MapperV2:
    """Discriminative lexical mapper with a native abstain path."""

    def __init__(
        self,
        ontology: FrozenOntology,
        *,
        top_k: int = 5,
        minimum_score: float = 0.0,
        minimum_discriminative_terms: int = 1,
        ambiguity_ratio: float = 0.80,
        generic_term_share: float = GENERIC_TERM_SHARE,
    ) -> None:
        self._ontology = ontology
        self._top_k = top_k
        self._minimum_score = minimum_score
        self._minimum_discriminative_terms = minimum_discriminative_terms
        self._ambiguity_ratio = ambiguity_ratio
        self._generic_term_share = generic_term_share
        self._index: dict[Layer, tuple[tuple[str, str, frozenset[str]], ...]] = {}
        self._weights: dict[Layer, dict[str, float]] = {}
        self._generic: dict[Layer, frozenset[str]] = {}
        self._item_weight: dict[Layer, dict[str, float]] = {}
        self._protected: dict[Layer, frozenset[str]] = {}
        for layer in Layer:
            items = ontology.items_for(layer)
            protected = _alias_terms(items)
            self._protected[layer] = protected
            index = _build_index(items, protected)
            self._index[layer] = index
            self._weights[layer], self._generic[layer] = _term_statistics(
                index, generic_term_share
            )
            weights = self._weights[layer]
            self._item_weight[layer] = {
                ontology_id: sum(weights.get(term, 1.0) for term in evoking)
                for ontology_id, _sense, evoking in index
            }

    @property
    def identity(self) -> JsonObject:
        return {
            "mapper_id": MAPPER_ID,
            "mapper_version": MAPPER_VERSION,
            "top_k": self._top_k,
            "minimum_score": self._minimum_score,
            "minimum_discriminative_terms": self._minimum_discriminative_terms,
            "ambiguity_ratio": self._ambiguity_ratio,
            "generic_term_share": self._generic_term_share,
            "o_l1_sha256": self._ontology.o_l1_sha256,
            "o_l2_sha256": self._ontology.o_l2_sha256,
        }

    def freeze_hash(self) -> str:
        return hashlib.sha256(canonical_json(self.identity)).hexdigest()

    def generic_terms(self, layer: Layer) -> tuple[str, ...]:
        """The terms treated as uninformative, exposed so the decision is auditable."""
        return tuple(sorted(self._generic[layer]))

    def map_expression(self, request: MapperInput, layer: Layer) -> MappingRecordV2:
        _assert_input_is_clean(request)
        observed = terms(request.text, protected=self._protected[layer])
        if not observed:
            return self._abstain(request, layer, AbstainReason.NO_CONTENT_TERMS)

        weights = self._weights[layer]
        generic = self._generic[layer]
        item_weight = self._item_weight[layer]
        scored: list[CandidateV2] = []

        for ontology_id, sense, evoking in self._index[layer]:
            overlap = observed & evoking
            if not overlap:
                continue
            # Weighted by how much each term narrows the field. A term shared across the layer adds
            # almost nothing, which is what stops generic words from carrying a mapping.
            weighted = sum(weights.get(term, 1.0) for term in overlap)
            # Normalised against the evidence the utterance itself could offer. A raw IDF sum has no
            # fixed range, so an absolute threshold against it is uncalibratable: measured on
            # discovery turns the fifth percentile was already 4.51, so a 0.35 floor rejected
            # nothing at all.
            # Normalised against the evidence the *item* could draw on, not the whole utterance.
            # Dividing by every observed term made the score fall with turn length, so a long
            # natural turn could never clear any floor and 99.8 percent abstained. Recall against
            # the item is the quantity that means "this item is well attested here".
            score = weighted / item_weight[ontology_id] if item_weight[ontology_id] else 0.0
            # A protected stopword restores matchability without conferring decisiveness. Counting
            # it as discriminative let "and", "for" and "every" satisfy the evidence test, which put
            # 74 percent of turns into "ambiguous" and drove abstention to zero — the same degeneracy
            # as v1, arrived at from the other side.
            discriminative = tuple(sorted(overlap - generic - _STOPWORDS))
            scored.append(
                CandidateV2(
                    ontology_id=ontology_id,
                    sense=sense,
                    layer=layer,
                    score=round(score, 6),
                    matched_terms=tuple(sorted(overlap)),
                    discriminative_terms=discriminative,
                )
            )

        if not scored:
            return self._abstain(request, layer, AbstainReason.NO_CANDIDATE_MATCHED)

        # Rank by decisive evidence first, then by score. Score alone put "please" (one protected
        # stopword, no decisive term) above "cancel" (the actual alias), and since the abstain check
        # only inspects the top candidate, the whole mapping was then discarded as generic. A
        # candidate carrying characteristic evidence must outrank one that carries none.
        scored.sort(
            key=lambda c: (-len(c.discriminative_terms), -c.score, c.ontology_id)
        )
        top = tuple(scored[: self._top_k])
        best = top[0]

        # Abstain is a decision with its own criteria, not the residue of a threshold.
        #
        # The criterion is evidence *structure*, not a score cut, and the calibration is measured
        # rather than chosen.
        #
        # Item-recall scores on discovery turns sit between 0.085 and 0.257, so any absolute floor in
        # that band is arbitrary: 0.45 rejected 99.8 percent of turns and 0.30 still rejected 96.
        # Worse, a floor of 0.12 rejected the correct short mappings too, because "please cancel my
        # flight reservation" scores 0.103 on one decisive term.
        #
        # The signal that actually separates the two cases is the count of discriminative terms: a
        # correct short mapping has one ("cancel", "booked") while a genuine negative has zero. So a
        # single characteristic term is required and the score floor is left off, since it only
        # re-introduced a length bias.
        if len(best.discriminative_terms) < self._minimum_discriminative_terms:
            return self._abstain(
                request,
                layer,
                AbstainReason.ONLY_GENERIC_EVIDENCE
                if not best.has_decisive_evidence
                else AbstainReason.BELOW_EVIDENCE_THRESHOLD,
                candidates=top,
            )
        if best.score < self._minimum_score:
            return self._abstain(
                request, layer, AbstainReason.BELOW_EVIDENCE_THRESHOLD, candidates=top
            )

        margin: float | None = None
        resolution = Resolution.MAPPED
        runner_up = top[1] if len(top) > 1 else None
        if runner_up is not None:
            margin = round(best.score - runner_up.score, 6)
            # Ambiguity requires both readings to be well supported. Two weak neighbours are not an
            # ambiguity; they are two poor guesses.
            comparable = runner_up.score >= best.score * self._ambiguity_ratio
            if comparable and runner_up.has_decisive_evidence:
                resolution = Resolution.AMBIGUOUS

        return MappingRecordV2(
            expression_id=request.expression_id,
            layer=layer,
            candidates=top,
            resolution=resolution,
            top_ontology_id=best.ontology_id,
            top_sense=best.sense,
            ambiguity_margin=margin,
        )

    def _abstain(
        self,
        request: MapperInput,
        layer: Layer,
        reason: AbstainReason,
        candidates: tuple[CandidateV2, ...] = (),
    ) -> MappingRecordV2:
        """Decline, keeping the rejected candidates so the decision can be reviewed."""
        return MappingRecordV2(
            expression_id=request.expression_id,
            layer=layer,
            candidates=candidates,
            resolution=Resolution.UNRESOLVED,
            abstain_reason=reason,
        )

    def map_all(self, requests: Sequence[MapperInput]) -> tuple[MappingRecordV2, ...]:
        return tuple(
            self.map_expression(request, layer) for request in requests for layer in Layer
        )


def _alias_terms(items: Sequence[JsonObject], *, maximum_items: int = 2) -> frozenset[str]:
    """Stopwords worth protecting: those that *are* an alias, not those that appear inside one.

    Protecting every alias word collapsed abstention to zero, because ``the``, ``and`` and ``for``
    occur inside multi-word aliases such as "make an appointment" and would then match every turn.
    Counting items per word was not enough either: it still protected 30 terms including ``the``,
    since a common word can appear in the aliases of only one or two items and remain ambient.

    The distinction that holds is whether the stopword is the *whole* alias. ``like`` is an alias of
    ``l1:predicate.hold_attitude`` in its own right, so it carries meaning; ``the`` never stands
    alone as an alias and only ever rides inside a longer phrase.
    """
    occurrences: dict[str, set[str]] = {}
    for item in items:
        ontology_id = str(item.get("id", ""))
        aliases = item.get("aliases")
        if not isinstance(aliases, list):
            continue
        for alias in aliases:
            words = _WORD.findall(str(alias).lower())
            # Single-word aliases only: a stopword inside a phrase is not itself the evidence.
            if len(words) != 1:
                continue
            word = words[0]
            if len(word) > 2 and word in _STOPWORDS:
                occurrences.setdefault(word, set()).add(ontology_id)
    return frozenset(
        word for word, ids in occurrences.items() if len(ids) <= maximum_items
    )


def _build_index(
    items: Sequence[JsonObject],
    protected: frozenset[str] = frozenset(),
) -> tuple[tuple[str, str, frozenset[str]], ...]:
    index: list[tuple[str, str, frozenset[str]]] = []
    for item in items:
        ontology_id = str(item.get("id", ""))
        if not ontology_id:
            continue
        sense = str(item.get("sense", ""))
        evoking: set[str] = set()
        aliases = item.get("aliases")
        if isinstance(aliases, list):
            for alias in aliases:
                evoking |= terms(str(alias), protected=protected)
        tail = ontology_id.split(":", 1)[-1].replace(".", " ").replace("_", " ")
        evoking |= terms(tail, protected=protected)
        evoking |= terms(sense, protected=protected)
        if evoking:
            index.append((ontology_id, sense, frozenset(evoking)))
    return tuple(index)


def _term_statistics(
    index: Sequence[tuple[str, str, frozenset[str]]],
    generic_term_share: float,
) -> tuple[dict[str, float], frozenset[str]]:
    """Weight each term by how much it narrows the field, and mark the generic ones.

    Inverse document frequency over ontology items. A term evoking one item is decisive; a term
    evoking a third of the layer is nearly useless, and v1 treated both identically.
    """
    if not index:
        return ({}, frozenset())
    document_frequency: Counter[str] = Counter()
    for _ontology_id, _sense, evoking in index:
        document_frequency.update(evoking)

    total = len(index)
    weights = {
        term: math.log(total / count) + 1.0 for term, count in document_frequency.items()
    }
    # Filler contributes almost nothing to a score, not merely nothing to decisiveness. Otherwise a
    # pile of filler still clears a normalised threshold.
    for term in CONVERSATIONAL_FILLER:
        if term in weights:
            weights[term] *= 0.15
    # Two sources of uninformativeness, and both are needed. Item frequency catches ontology jargon
    # shared across many items; the filler list catches words that evoke one item but appear in
    # nearly every conversational turn.
    generic = frozenset(
        term
        for term, count in document_frequency.items()
        if count / total >= generic_term_share
    ) | (CONVERSATIONAL_FILLER & set(document_frequency))
    return (weights, generic)


def _assert_input_is_clean(request: MapperInput) -> None:
    present = sorted(FORBIDDEN_INPUT_FIELDS & set(type(request).model_fields))
    if present:
        raise MapperError(
            f"mapper input declares forbidden fields: {present}; a mapper that can see these can "
            "special-case them"
        )


_CORRECTION_GATE_NAMES: frozenset[str] = frozenset(
    {"_repair", "_correct", "repair_mapping", "fix_mapping", "override_sense", "correct_sense"}
)


def assert_no_correction_gate(module_source: str) -> None:
    """Fail if a semantic correction gate is defined. Parsed, not substring-matched."""
    try:
        tree = ast.parse(module_source)
    except SyntaxError as error:
        raise MapperError(f"the mapper source does not parse: {error}") from error
    defined = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    found = sorted(defined & _CORRECTION_GATE_NAMES)
    if found:
        raise MapperError(f"a semantic correction gate is defined: {found}")
