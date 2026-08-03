"""Replayable evidence collection for O_v3, from independent frozen corpora only.

The isolation rule that matters here: nothing in this module reads the 120-expression validation
sample, the mapper output or the annotation gold. Aliases are derived from independent corpora and
from the frozen published sources, so an item earns its place by what the corpora attest rather than
by what would have helped on the cases that exposed the gap.

Replayability is the other requirement. O_v2 ended up a recovered-only freeze because the generator
died before it was committed, and its content could never be regenerated. Everything here is
deterministic: the same corpora produce the same counts, so the same digests. The generator is
committed before the freeze is produced.

The four families are fixed by ruling and this module does not widen them. ``episodic_significance``
stays a residual gap and ``role_play_framing`` a provenance limitation; neither is collected.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

MSC_PATH = Path("/public/home/wwb/datasets/MSC/msc_personas_all.json")
SGD_SCHEMA = Path("/public/home/wwb/datasets/SGD/train/schema.json")

# Recorded so a replay proves it read the same bytes.
MSC_SHA256_PREFIX = "75440be006945f5e"

# Minimum corpus occurrences before a surface form becomes an alias. Low, because these families are
# attested at very different rates and a uniform high bar would silently drop held_value entirely —
# which is precisely the family admitted on expressibility rather than frequency.
MIN_ALIAS_SUPPORT = 2


@dataclass(frozen=True)
class SurfaceEvidence:
    """One attested surface form and how often the corpus carries it."""

    form: str
    count: int
    corpus: str

    def as_json(self) -> dict[str, Any]:
        return {"form": self.form, "count": self.count, "corpus": self.corpus}


@dataclass(frozen=True)
class FamilyEvidence:
    """Everything one family earned from the corpora, with nothing inferred."""

    family: str
    surface_forms: tuple[SurfaceEvidence, ...]
    total_occurrences: int
    corpus_sentences_scanned: int
    sgd_support: tuple[str, ...]
    notes: tuple[str, ...] = ()

    @property
    def aliases(self) -> tuple[str, ...]:
        """Surface forms with enough support to serve as aliases."""
        return tuple(
            evidence.form
            for evidence in self.surface_forms
            if evidence.count >= MIN_ALIAS_SUPPORT
        )

    def as_json(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "surface_forms": [e.as_json() for e in self.surface_forms],
            "total_occurrences": self.total_occurrences,
            "corpus_sentences_scanned": self.corpus_sentences_scanned,
            "sgd_support": list(self.sgd_support),
            "aliases_meeting_support_threshold": list(self.aliases),
            "notes": list(self.notes),
        }


# First-person patterns per family. Deliberately first-person: a memory ontology records what a
# subject states about themselves, and a third-person match would admit narration about others.
_ACTIVITY_VERBS = (
    "play", "host", "attend", "volunteer", "practice", "coach", "paint", "sing",
    "dance", "hike", "run", "swim", "cook", "read", "write", "collect", "garden",
    "fish", "camp", "travel", "knit", "draw",
)
_CAPABILITY_PATTERNS = (
    r"i can ([a-z]+)",
    r"i am good at",
    r"i know how to",
    r"i am able to",
    r"i have a degree",
    r"i studied",
    r"i am trained",
)
_VALUE_PATTERNS = (
    r"i value",
    r"i care about",
    r"i prioriti[sz]e",
    r"is important to me",
    r"matters to me",
    r"i cherish",
)
_BELIEF_PATTERNS = (
    r"i believe in",
    r"i believe",
    r"i think that",
    r"i learned that",
    r"i feel that",
    r"my philosophy",
)


def _flatten(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [s for item in cast("list[Any]", value) for s in _flatten(item)]
    if isinstance(value, dict):
        return [
            s for item in cast("dict[str, Any]", value).values() for s in _flatten(item)
        ]
    return []


def msc_sentences() -> tuple[tuple[str, ...], str]:
    """Persona sentences and the digest of the file they came from."""
    payload = MSC_PATH.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    sentences = tuple(
        s for s in _flatten(json.loads(payload.decode("utf-8"))) if len(s) > 12
    )
    return (sentences, digest)


def _sgd_activity_fields() -> tuple[str, ...]:
    """SGD schema fields that are activity-like.

    Only activity has SGD support; the other three families have none, and that asymmetry is recorded
    rather than smoothed over.
    """
    if not SGD_SCHEMA.is_file():
        return ()
    schema = cast("list[Any]", json.loads(SGD_SCHEMA.read_text(encoding="utf-8")))
    names: list[str] = []
    for raw in schema:
        service = cast("dict[str, Any]", raw)
        for group in ("slots", "intents"):
            for entry in cast("list[Any]", service.get(group, [])):
                name = str(cast("dict[str, Any]", entry).get("name", ""))
                if re.search(r"event|class|lesson|appointment|attend|activity", name.lower()):
                    names.append(name)
    return tuple(sorted(set(names)))


def collect_activity(sentences: tuple[str, ...]) -> FamilyEvidence:
    counts: Counter[str] = Counter()
    pattern = re.compile(r"\bi (" + "|".join(_ACTIVITY_VERBS) + r")\b")
    for sentence in sentences:
        for match in pattern.finditer(sentence.lower()):
            counts[match.group(1)] += 1
    return FamilyEvidence(
        family="activity_or_pursuit",
        surface_forms=tuple(
            SurfaceEvidence(form=form, count=count, corpus="msc_personas")
            for form, count in counts.most_common()
        ),
        total_occurrences=sum(counts.values()),
        corpus_sentences_scanned=len(sentences),
        sgd_support=_sgd_activity_fields(),
        notes=(
            "the only family with task-oriented schema support, which is why it was admitted on "
            "frequency rather than on expressibility",
        ),
    )


def collect_capability(sentences: tuple[str, ...]) -> FamilyEvidence:
    counts: Counter[str] = Counter()
    compiled = [re.compile(rf"\b{p}\b") for p in _CAPABILITY_PATTERNS]
    for sentence in sentences:
        lowered = sentence.lower()
        for pattern in compiled:
            for match in pattern.finditer(lowered):
                counts[match.group(0)] += 1
    return FamilyEvidence(
        family="positive_capability_or_skill",
        surface_forms=tuple(
            SurfaceEvidence(form=form, count=count, corpus="msc_personas")
            for form, count in counts.most_common()
        ),
        total_occurrences=sum(counts.values()),
        corpus_sentences_scanned=len(sentences),
        sgd_support=(),
        notes=(
            "PropBank can.01 means 'put into tins' and can.02 is metaphorical throwing, so the modal "
            "sense has no roleset. This family needs an authored type rather than an imported frame.",
            "v2 types only what a subject cannot do, via state.capability_constraint, so the positive "
            "case has no existing home.",
        ),
    )


def collect_value(sentences: tuple[str, ...]) -> FamilyEvidence:
    counts: Counter[str] = Counter()
    compiled = [re.compile(rf"\b{p}\b") for p in _VALUE_PATTERNS]
    strength_markers = 0
    strength = re.compile(r"\b(really|very|most|above all|deeply|super) (important|much)\b")
    for sentence in sentences:
        lowered = sentence.lower()
        for pattern in compiled:
            for match in pattern.finditer(lowered):
                counts[match.group(0)] += 1
        if strength.search(lowered):
            strength_markers += 1
    return FamilyEvidence(
        family="held_value",
        surface_forms=tuple(
            SurfaceEvidence(form=form, count=count, corpus="msc_personas")
            for form, count in counts.most_common()
        ),
        total_occurrences=sum(counts.values()),
        corpus_sentences_scanned=len(sentences),
        sgd_support=(),
        notes=(
            "admitted on expressibility, not frequency: attribute.assessment rates an object while a "
            "held value is a property of the subject, so this is unrepresentable rather than rare.",
            f"{strength_markers} sentences carry a strength marker, so preference strength is attested "
            "and is preserved as a qualifier rather than folded into the concept.",
            "kept separate from held_belief by ruling: a merged item would lose strength on this side "
            "and modality on the other.",
        ),
    )


def collect_belief(sentences: tuple[str, ...]) -> FamilyEvidence:
    counts: Counter[str] = Counter()
    compiled = [re.compile(rf"\b{p}\b") for p in _BELIEF_PATTERNS]
    modality_markers = 0
    modality = re.compile(
        r"\bi (strongly believe|firmly believe|guess|suppose|am convinced)\b"
    )
    for sentence in sentences:
        lowered = sentence.lower()
        for pattern in compiled:
            for match in pattern.finditer(lowered):
                counts[match.group(0)] += 1
        if modality.search(lowered):
            modality_markers += 1
    return FamilyEvidence(
        family="held_belief",
        surface_forms=tuple(
            SurfaceEvidence(form=form, count=count, corpus="msc_personas")
            for form, count in counts.most_common()
        ),
        total_occurrences=sum(counts.values()),
        corpus_sentences_scanned=len(sentences),
        sgd_support=(),
        notes=(
            "admitted on expressibility, not frequency: no existing type expresses a general claim "
            "about the world held by the subject.",
            f"{modality_markers} sentences carry an explicit modality marker, so assertion modality is "
            "carried as a declared slot with no corpus support rather than as an attested qualifier. "
            "Inventing graded values for it would be fabricating coverage.",
            "kept separate from held_value by ruling.",
        ),
    )


def collect_all() -> tuple[tuple[FamilyEvidence, ...], dict[str, Any]]:
    """All four families plus the provenance a replay can check."""
    sentences, digest = msc_sentences()
    if not digest.startswith(MSC_SHA256_PREFIX):
        raise RuntimeError(
            f"MSC corpus digest {digest[:16]} does not match the recorded "
            f"{MSC_SHA256_PREFIX}; evidence would be drawn from different bytes"
        )
    families = (
        collect_activity(sentences),
        collect_capability(sentences),
        collect_value(sentences),
        collect_belief(sentences),
    )
    provenance = {
        "msc_sha256": digest,
        "msc_sentences_scanned": len(sentences),
        "sgd_schema_present": SGD_SCHEMA.is_file(),
        "min_alias_support": MIN_ALIAS_SUPPORT,
        "isolation": (
            "no validation expression, mapper output or annotation label was read. Aliases come from "
            "independent corpora and the frozen published sources only."
        ),
        "families_excluded_by_ruling": [
            "episodic_significance (explicit residual gap, pending new corpora)",
            "role_play_framing (provenance and modality limitation, not a concept gap)",
        ],
        "replayable": (
            "deterministic over fixed corpora: the same bytes yield the same counts and therefore the "
            "same digests"
        ),
    }
    return (families, provenance)
