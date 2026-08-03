"""Mapper v3 candidate generation: 0..N frames over the combined O_v2 and O_v3 namespace.

Two things changed from v2, and the second is the one that matters.

The first is evidence type. v2 had alias matching and PropBank rolesets, which reach items named by a
word the speaker used. v3 adds construction evidence, which reaches items signalled by how the
utterance is built — the categories v2 missed 30 and 27 times respectively.

The second is arity. v2 produced a ranked list and then reported one answer, so a natural utterance
attesting several things at once was scored as one selection; the previous round measured that as 35
incomplete selections out of 76 multi-target cases. v3 produces **frames**: zero or more, each a
target with its own evidence, and the result carries all of them. A multi-target utterance yields a
multi-target answer.

No detector, weight or threshold here names a specific ontology item. Constructions map to item
*types* and the ontology decides which items those types contain, so adding an item needs no change to
this module. That is what keeps this from being a special case for the two targets that motivated it.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, cast

from ke_memory_demo.core.json import JsonObject

from .constructions import (
    CONSTRUCTION_TO_ITEM_TYPES,
    Construction,
    ConstructionHit,
    detect,
    is_request_only,
)

_WORD = re.compile(r"[a-z][a-z0-9]*")

# Words that name a region of the id space rather than a meaning. Derived by measuring how many items
# each id-tail word reaches: these are the ones shared across many items, so matching one says only
# that the utterance mentioned a category name.
_NAMESPACE_WORDS = frozenset(
    {
        "role", "predicate", "attribute", "abstraction", "event", "state", "modality",
        "status", "source", "qualifier", "time", "preference", "task", "polarity",
        "frequency", "pattern", "relation", "lifecycle", "standing", "evidence",
    }
)

# Words that cannot support a mapping on their own. Kept deliberately short: v2's long stopword list
# deleted terms the ontology declared as aliases, and the work is done by evidence kind instead.
_NON_EVIDENCE = frozenset(
    {
        "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "is", "are",
        "was", "were", "be", "am", "it", "this", "that", "i", "my", "me", "you", "your",
        "we", "they", "he", "she", "his", "her", "do", "does", "did", "have", "has", "had",
        "not", "no", "so", "if", "but", "as", "at", "by", "from", "there", "here",
    }
)


class EvidenceKind(StrEnum):
    """Kinds of support, ordered by how much they constrain the reading."""

    CONSTRUCTION = "construction"
    DECISIVE_ALIAS = "decisive_alias"
    PHRASE_ALIAS = "phrase_alias"
    TYPE_COMPATIBILITY = "type_compatibility"


# Construction evidence outweighs a bare alias because it reports what the utterance does rather than
# which words it contains. Type compatibility alone is the weakest: it says an item *could* apply.
EVIDENCE_WEIGHT: dict[EvidenceKind, float] = {
    EvidenceKind.CONSTRUCTION: 1.0,
    EvidenceKind.DECISIVE_ALIAS: 0.8,
    EvidenceKind.PHRASE_ALIAS: 0.6,
    EvidenceKind.TYPE_COMPATIBILITY: 0.2,
}


@dataclass(frozen=True)
class FrameEvidence:
    kind: EvidenceKind
    detail: str
    trigger: str = ""

    @property
    def weight(self) -> float:
        return EVIDENCE_WEIGHT[self.kind]

    @property
    def is_standalone(self) -> bool:
        """Whether this evidence could carry a frame by itself.

        Type compatibility cannot: every item of a compatible type would qualify, which is how a
        mechanism turns into a rubber stamp.
        """
        return self.kind is not EvidenceKind.TYPE_COMPATIBILITY

    def as_json(self) -> JsonObject:
        return {"kind": str(self.kind), "detail": self.detail, "trigger": self.trigger}


@dataclass(frozen=True)
class SemanticFrame:
    """One target the utterance attests, with the evidence for it."""

    ontology_id: str
    sense: str
    item_type: str
    evidence: tuple[FrameEvidence, ...]

    @property
    def score(self) -> float:
        return round(sum(e.weight for e in self.evidence), 6)

    @property
    def has_construction_support(self) -> bool:
        return any(e.kind is EvidenceKind.CONSTRUCTION for e in self.evidence)

    @property
    def is_admissible(self) -> bool:
        """A frame needs at least one piece of evidence that stands alone."""
        return any(e.is_standalone for e in self.evidence)

    def as_json(self) -> JsonObject:
        return {
            "ontology_id": self.ontology_id,
            "sense": self.sense,
            "item_type": self.item_type,
            "score": self.score,
            "has_construction_support": self.has_construction_support,
            "evidence": [e.as_json() for e in self.evidence],
        }


@dataclass(frozen=True)
class OntologyEntry:
    """An ontology item indexed for generation."""

    ontology_id: str
    sense: str
    item_type: str
    decisive_aliases: frozenset[str]
    phrase_aliases: frozenset[str]


def build_entries(
    v2_l1: Sequence[JsonObject],
    v2_l2: Sequence[JsonObject],
    v3_l1: Sequence[JsonObject],
    v3_l2: Sequence[JsonObject],
) -> tuple[OntologyEntry, ...]:
    """Index the combined namespace.

    v2 wraps each item as ``{"item": ..., "item_type": ...}`` while v3 stores items flat, so both
    shapes are handled rather than assuming one.
    """
    entries: list[OntologyEntry] = []
    for group in (v2_l1, v2_l2, v3_l1, v3_l2):
        for wrapper in group:
            raw = wrapper.get("item", wrapper)
            if not isinstance(raw, dict):
                continue
            item = cast("dict[str, Any]", raw)
            ontology_id = str(item.get("id", ""))
            if not ontology_id:
                continue
            item_type = str(wrapper.get("item_type") or item.get("item_type") or "")
            decisive: set[str] = set()
            phrases: set[str] = set()
            aliases = item.get("aliases")
            if isinstance(aliases, list):
                for alias in cast("list[Any]", aliases):
                    words = _WORD.findall(str(alias).lower())
                    if len(words) == 1:
                        decisive.add(words[0])
                    elif words:
                        phrases.add(" ".join(words))
            # Only the id's final segment, and only when it is not a namespace word.
            #
            # Taking every word of the tail made the type prefix a decisive alias: "role" was shared
            # by 21 items, "predicate" by 15, "attribute" by 11, and "time" by the 7 l1:time.* items.
            # An utterance containing "time" then framed all seven, which is how 680 of 1500 discovery
            # turns hit the frame cap. A namespace word describes where an id lives, not what an
            # utterance said.
            tail = ontology_id.split(":", 1)[-1]
            leaf = tail.split(".")[-1] if "." in tail else tail
            decisive.update(
                w
                for w in _WORD.findall(leaf.replace("_", " "))
                if w not in _NON_EVIDENCE and w not in _NAMESPACE_WORDS
            )
            entries.append(
                OntologyEntry(
                    ontology_id=ontology_id,
                    sense=str(item.get("sense", "")),
                    item_type=item_type,
                    decisive_aliases=frozenset(decisive),
                    phrase_aliases=frozenset(phrases),
                )
            )
    return tuple(entries)


class FrameGenerator:
    """Generate 0..N frames per utterance, or none when nothing is attested."""

    def __init__(self, entries: Sequence[OntologyEntry], *, max_frames: int = 6) -> None:
        self._entries = tuple(entries)
        self._max_frames = max_frames
        self._by_type: dict[str, tuple[OntologyEntry, ...]] = {}
        grouped: dict[str, list[OntologyEntry]] = {}
        for entry in self._entries:
            grouped.setdefault(entry.item_type, []).append(entry)
        self._by_type = {k: tuple(v) for k, v in grouped.items()}

    def generate(self, text: str) -> tuple[SemanticFrame, ...]:
        """Frames for one utterance. Empty means nothing was attested."""
        hits = detect(text)
        # A pure information request asserts nothing about the speaker, so declining is reasoned here
        # rather than falling out of a threshold.
        if is_request_only(hits):
            return ()

        terms = {
            w for w in _WORD.findall(text.lower()) if w not in _NON_EVIDENCE and len(w) > 2
        }
        lowered = " ".join(_WORD.findall(text.lower()))
        compatible_types = self._compatible_types(hits)

        collected: dict[str, list[FrameEvidence]] = {}

        def add(entry: OntologyEntry, evidence: FrameEvidence) -> None:
            collected.setdefault(entry.ontology_id, []).append(evidence)

        for entry in self._entries:
            # Alias evidence: what the speaker said.
            matched = terms & entry.decisive_aliases
            if matched:
                add(
                    entry,
                    FrameEvidence(
                        kind=EvidenceKind.DECISIVE_ALIAS,
                        detail="single-word alias or id term",
                        trigger=sorted(matched)[0],
                    ),
                )
            for phrase in entry.phrase_aliases:
                if phrase in lowered:
                    add(
                        entry,
                        FrameEvidence(
                            kind=EvidenceKind.PHRASE_ALIAS,
                            detail="whole phrase alias",
                            trigger=phrase,
                        ),
                    )
                    break

            # Construction evidence: what the utterance does. Reaches items no word named.
            if entry.item_type in compatible_types:
                supporting = [
                    hit
                    for hit in hits
                    if entry.item_type in CONSTRUCTION_TO_ITEM_TYPES.get(
                        hit.construction, frozenset()
                    )
                ]
                if supporting:
                    # A construction says what *kind* of claim the utterance makes, never which item
                    # within that kind. Treating a narrow type as decisive made "are amazing" fire
                    # affinity, avoidance, comparative and threshold at identical scores, and pushed
                    # 872 of 1500 discovery turns to the frame cap: every member of a small type
                    # inherited the same evidence.
                    #
                    # So construction evidence is decisive only for an item the utterance already
                    # reaches through its own vocabulary. On its own it is type compatibility, which
                    # cannot carry a frame. That keeps the construction doing what it can do — telling
                    # preference from intention — without pretending it can choose among preferences.
                    already_supported = entry.ontology_id in collected
                    kind = (
                        EvidenceKind.CONSTRUCTION
                        if already_supported
                        else EvidenceKind.TYPE_COMPATIBILITY
                    )
                    add(
                        entry,
                        FrameEvidence(
                            kind=kind,
                            detail=f"{supporting[0].construction} supports {entry.item_type}",
                            trigger=supporting[0].trigger,
                        ),
                    )

        senses = {e.ontology_id: (e.sense, e.item_type) for e in self._entries}
        frames = [
            frame
            for frame in (
                SemanticFrame(
                    ontology_id=ontology_id,
                    sense=senses[ontology_id][0],
                    item_type=senses[ontology_id][1],
                    evidence=tuple(_dedupe(evidence)),
                )
                for ontology_id, evidence in collected.items()
            )
            if frame.is_admissible
        ]
        # Construction-supported frames first, then score. A frame resting on vocabulary alone cannot
        # outrank one that also matches what the utterance is doing.
        frames.sort(
            key=lambda f: (-int(f.has_construction_support), -f.score, f.ontology_id)
        )
        return tuple(frames[: self._max_frames])

    def _compatible_types(self, hits: Sequence[ConstructionHit]) -> frozenset[str]:
        supported: set[str] = set()
        for hit in hits:
            supported |= CONSTRUCTION_TO_ITEM_TYPES.get(hit.construction, frozenset())
        return frozenset(supported)

    def provenance(self) -> dict[str, Any]:
        return {
            "namespace": "combined O_v2 and O_v3",
            "entries_indexed": len(self._entries),
            "item_types": sorted(self._by_type),
            "max_frames": self._max_frames,
            "arity": (
                "0..N frames per utterance. v2 reported one answer per utterance and the previous round "
                "measured 35 incomplete selections out of 76 multi-target cases."
            ),
            "evidence_weights": {str(k): v for k, v in EVIDENCE_WEIGHT.items()},
            "no_target_special_cases": (
                "no detector, weight or threshold names an ontology item. Constructions map to item "
                "types and the ontology supplies the items, so adding an item requires no change here."
            ),
            "reasoned_no_map": (
                "a pure information request returns no frames because it asserts nothing about the "
                "speaker, rather than because a score fell below a cut"
            ),
            "construction_count": len(Construction),
        }


def _dedupe(evidence: Sequence[FrameEvidence]) -> list[FrameEvidence]:
    """One piece per kind and trigger, so a repeated word cannot inflate a score."""
    seen: set[tuple[EvidenceKind, str]] = set()
    unique: list[FrameEvidence] = []
    for item in evidence:
        key = (item.kind, item.trigger)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique
