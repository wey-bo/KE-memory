"""Construction evidence: what an utterance *does*, independent of which item it maps to.

Mapper v2 failed on the frozen sample at candidate recall 0.165, and the diagnosis was specific: the
most-missed targets are categories expressed by construction rather than by word choice.
``task.declared_intention`` was missed 30 times and ``preference.affinity`` 27, because "Animals are
amazing" attests an affinity while containing no word an alias list would carry, and "I think I'll try
using roasted sweet potatoes" attests an intention through syntax.

Alias matching cannot reach those. Neither can more aliases. So this module detects **constructions** —
grammatical patterns that signal what kind of claim an utterance is making — and does so without
naming any ontology item.

That independence is the design constraint that matters. A detector written as "if the text matches
this pattern, emit ``task.declared_intention``" would be a special case for one target dressed up as a
general mechanism, and the recall improvement would be an artefact of the sample that motivated it.
Instead each detector reports a *construction*, and the ontology's own type and qualifier structure
decides which items that construction can support. Constructions and items are wired together by
declared compatibility, never by a hand-written pair.

Frequencies below are measured on the discovery split, which mapper development may read. The fresh
validation set was not consulted.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Construction(StrEnum):
    """Grammatical constructions, named for what they do rather than for what they map to.

    Deliberately not named after ontology items. A construction called ``INTENTION_DECLARATION`` is a
    claim about syntax; one called ``DECLARED_INTENTION_TARGET`` would be a special case.
    """

    # "I'll try", "I'm going to", "I plan to" — a commitment about the future by the speaker.
    INTENTION_DECLARATION = "intention_declaration"
    # "X is amazing", "that sounds great" — an evaluative predicate over a subject.
    EVALUATIVE_PREDICATION = "evaluative_predication"
    # "I have", "I own", "I bought" — a possession or acquisition claim.
    POSSESSION_CLAIM = "possession_claim"
    # "always", "every Tuesday", "usually" — a habitual or recurrent aspect marker.
    HABITUAL_ASPECT = "habitual_aspect"
    # "yesterday", "last week", "a few years ago" — a bounded past episode.
    PAST_EPISODE = "past_episode"
    # "I can", "I know how to" — an ability claim about the speaker.
    ABILITY_CLAIM = "ability_claim"
    # "is important to me", "I care about" — a priority or salience claim by the speaker.
    SALIENCE_CLAIM = "salience_claim"
    # "I believe", "I think that" — a general proposition the speaker holds.
    PROPOSITIONAL_STANCE = "propositional_stance"
    # "I don't", "never", "no longer" — negation or cessation scoped over a claim.
    NEGATED_OR_CEASED = "negated_or_ceased"
    # "?" plus request forms — an information request rather than an assertion about the speaker.
    INFORMATION_REQUEST = "information_request"


# Which ontology *types* each construction can support. Types, not item ids: an item becomes reachable
# because its type is compatible, so adding an item to the ontology needs no change here. This is the
# join that keeps the mechanism general.
CONSTRUCTION_TO_ITEM_TYPES: dict[Construction, frozenset[str]] = {
    Construction.INTENTION_DECLARATION: frozenset({"task_type", "predicate_sense", "event_type"}),
    Construction.EVALUATIVE_PREDICATION: frozenset(
        {"preference_type", "predicate_sense", "attribute_type"}
    ),
    Construction.POSSESSION_CLAIM: frozenset({"state_type", "attribute_type", "predicate_sense"}),
    Construction.HABITUAL_ASPECT: frozenset({"state_type", "qualifier_value", "qualifier_dimension"}),
    Construction.PAST_EPISODE: frozenset({"event_type", "qualifier_value"}),
    Construction.ABILITY_CLAIM: frozenset({"state_type"}),
    Construction.SALIENCE_CLAIM: frozenset({"predicate_sense", "preference_type"}),
    Construction.PROPOSITIONAL_STANCE: frozenset({"predicate_sense"}),
    Construction.NEGATED_OR_CEASED: frozenset({"qualifier_value", "state_type"}),
    Construction.INFORMATION_REQUEST: frozenset({"event_type", "predicate_sense"}),
}

# Patterns per construction. Multiple alternatives per construction because natural speech realises
# the same function several ways, and a single pattern would measure the pattern rather than the
# construction.
_PATTERNS: dict[Construction, tuple[str, ...]] = {
    Construction.INTENTION_DECLARATION: (
        r"\bi'?ll\b",
        r"\bi will\b",
        r"\bi'?m going to\b",
        r"\bi am going to\b",
        r"\bi (?:plan|want|hope|intend|mean) to\b",
        r"\bi'?m (?:planning|hoping|trying) to\b",
        r"\bi think i'?ll\b",
        r"\bmy plan is\b",
    ),
    Construction.EVALUATIVE_PREDICATION: (
        r"\b(?:is|are|was|were|sounds?|seems?|looks?)\s+(?:so|really|very|pretty|quite|super|absolutely\s+)?"
        r"(?:amazing|great|awesome|wonderful|terrible|awful|incredible|fantastic|lovely|beautiful"
        r"|excellent|brilliant|perfect|horrible|delicious|fun|interesting|impressive)\b",
        r"\bwhat a (?:great|wonderful|lovely|terrible)\b",
        r"\bi (?:love|adore|enjoy|hate|dislike|prefer)\b",
    ),
    Construction.POSSESSION_CLAIM: (
        r"\bi (?:have|own|got|bought|purchased|keep|carry)\b",
        r"\bmy (?:new|old|first|favourite|favorite)\b",
        r"\bi'?ve (?:got|had)\b",
    ),
    Construction.HABITUAL_ASPECT: (
        r"\b(?:always|usually|normally|generally|regularly|often|frequently|typically)\b",
        r"\bevery (?:day|week|month|year|morning|evening|night|monday|tuesday|wednesday"
        r"|thursday|friday|saturday|sunday|weekend)\b",
        r"\b(?:once|twice|three times) a (?:day|week|month|year)\b",
        r"\bi tend to\b",
    ),
    Construction.PAST_EPISODE: (
        r"\b(?:yesterday|today)\b",
        r"\blast (?:week|month|year|night|summer|winter)\b",
        r"\ba (?:few|couple of) (?:years|months|weeks|days) ago\b",
        r"\bback (?:in|when)\b",
        r"\bwhen i was\b",
    ),
    Construction.ABILITY_CLAIM: (
        r"\bi can (?:play|speak|cook|swim|drive|sing|dance|write|build|make|read|ride)\b",
        r"\bi (?:know how to|am able to|am good at)\b",
        r"\bi'?m good at\b",
        r"\bi (?:studied|trained|have a degree)\b",
    ),
    Construction.SALIENCE_CLAIM: (
        r"\bis (?:so |really |very |super )?important to me\b",
        r"\bi (?:care about|value|prioriti[sz]e|cherish)\b",
        r"\bmatters to me\b",
        r"\bmeans a lot to me\b",
    ),
    Construction.PROPOSITIONAL_STANCE: (
        r"\bi believe\b",
        r"\bi think that\b",
        r"\bi (?:learned|realised|realized) that\b",
        r"\bin my (?:opinion|experience)\b",
        r"\bmy philosophy\b",
    ),
    Construction.NEGATED_OR_CEASED: (
        r"\bi (?:don'?t|do not|didn'?t|never|no longer|stopped|quit|gave up)\b",
        r"\bi'?m not\b",
        r"\bnot (?:any ?more|anymore)\b",
    ),
    Construction.INFORMATION_REQUEST: (
        r"\b(?:can|could|would) you\b",
        r"\bdo you (?:know|have)\b",
        r"\bwhat (?:is|are|do|does)\b",
        r"\bany (?:recommendations|suggestions|ideas|tips)\b",
        r"\?",
    ),
}

_COMPILED: dict[Construction, tuple[re.Pattern[str], ...]] = {
    construction: tuple(re.compile(p) for p in patterns)
    for construction, patterns in _PATTERNS.items()
}


@dataclass(frozen=True)
class ConstructionHit:
    """One construction detected, with the span that triggered it."""

    construction: Construction
    trigger: str
    pattern_index: int

    def as_json(self) -> dict[str, Any]:
        return {
            "construction": str(self.construction),
            "trigger": self.trigger,
            "pattern_index": self.pattern_index,
        }


def detect(text: str) -> tuple[ConstructionHit, ...]:
    """Every construction the utterance realises.

    Zero or many: an utterance can declare an intention while also requesting information, and
    forcing a single construction would discard exactly the multi-label structure natural speech has.
    """
    lowered = text.lower()
    hits: list[ConstructionHit] = []
    for construction, patterns in _COMPILED.items():
        for index, pattern in enumerate(patterns):
            match = pattern.search(lowered)
            if match is not None:
                hits.append(
                    ConstructionHit(
                        construction=construction,
                        trigger=match.group(0).strip(),
                        pattern_index=index,
                    )
                )
                break
    return tuple(hits)


def supported_item_types(hits: Sequence[ConstructionHit]) -> frozenset[str]:
    """Item types the detected constructions can support, unioned."""
    supported: set[str] = set()
    for hit in hits:
        supported |= CONSTRUCTION_TO_ITEM_TYPES.get(hit.construction, frozenset())
    return frozenset(supported)


def is_request_only(hits: Sequence[ConstructionHit]) -> bool:
    """Whether the utterance only asks for something.

    A pure information request asserts nothing about the speaker to remember, so this is the one
    construction that argues *against* mapping. Recognising that is how a no-map becomes reasoned
    rather than a threshold artefact.
    """
    kinds = {hit.construction for hit in hits}
    if not kinds:
        return False
    return kinds == {Construction.INFORMATION_REQUEST}


def provenance() -> dict[str, Any]:
    return {
        "why_constructions": (
            "mapper v2 reached candidate recall 0.165 because the most-missed targets are expressed by "
            "construction rather than by word choice: task.declared_intention missed 30 times and "
            "preference.affinity 27. Alias matching cannot reach those and more aliases would not help."
        ),
        "generality_guarantee": (
            "a construction is named for what it does and maps to ontology item *types*, never to item "
            "ids. No detector mentions task.declared_intention, preference.affinity or any other "
            "target, so the mechanism cannot be a special case wearing a general name."
        ),
        "construction_count": len(Construction),
        "patterns_per_construction": {
            str(c): len(p) for c, p in _PATTERNS.items()
        },
        "discovery_frequencies": {
            "intention_declaration": "20.0% of 5250 discovery turns",
            "habitual_aspect": "21.0%",
            "possession_claim": "4.1%",
            "evaluative_predication": "2.2%",
            "past_episode": "1.5%",
        },
        "measured_on": "the discovery split only; the fresh validation set was not consulted",
        "zero_or_many": (
            "detect returns 0..N constructions. An utterance can declare an intention and request "
            "information at once, and collapsing to one would discard the multi-label structure the "
            "previous round measured as 35 of 76 incomplete selections."
        ),
    }
