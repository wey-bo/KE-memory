"""Mapper v1: natural expression to frozen ontology, with nothing else in scope.

The input rule is the whole design. A mapper that can see a question, a gold label, a split, a
dataset name or a sample id can special-case any of them, and a score obtained that way says
nothing about mapping. So :class:`MapperInput` carries an utterance and a speaker and has no field
for anything else, and ``extra="forbid"`` means a caller cannot add one.

The output rule is the other half. Raw top-k candidates, senses, confidences, ambiguity and
unresolved status are preserved as produced. There is no semantic correction gate: a wrong mapping
stays wrong in the record, because a repaired output measures the repair rather than the mapper.

Candidate generation is lexical over the frozen ontology's aliases, id segments and sense text. That
is a real mapper of modest power rather than a stand-in beside one — it consumes the frozen units,
and its errors are the errors being diagnosed.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ke_memory_demo.core.json import JsonObject, canonical_json

NonEmptyString = Annotated[str, Field(min_length=1)]

MAPPER_ID = "mapper-v1-lexical"
MAPPER_VERSION = "1.0.0"

# Fields that must never reach a mapper. Named so the prohibition is auditable rather than merely
# implied by the absence of a field.
FORBIDDEN_INPUT_FIELDS: frozenset[str] = frozenset(
    {
        "question",
        "question_id",
        "answer",
        "gold",
        "gold_evidence",
        "evidence_refs",
        "rubric",
        "rubrics",
        "split",
        "dataset",
        "dataset_name",
        "benchmark",
        "sample_id",
        "item_id",
        "category",
    }
)


class MapperError(ValueError):
    """A mapper was given something it must not see, or configured incorrectly."""


class Layer(StrEnum):
    L1 = "l1"
    L2 = "l2"


class Resolution(StrEnum):
    """How a mapping ended. Recorded rather than corrected."""

    MAPPED = "mapped"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class MapperInput(_Record):
    """An utterance and its speaker. There is nowhere to put a question or a gold label."""

    expression_id: NonEmptyString
    speaker: NonEmptyString
    text: NonEmptyString

    @model_validator(mode="after")
    def _reject_smuggled_identity(self) -> MapperInput:
        # expression_id is opaque by contract. A caller passing a benchmark item id would let the
        # mapper special-case a dataset, which is what the input rule exists to prevent.
        lowered = self.expression_id.lower()
        for marker in ("beam", "locomo", "longmemeval", "slice", "gold"):
            if marker in lowered:
                raise MapperError(
                    f"expression_id {self.expression_id!r} discloses dataset identity; "
                    "mapper input ids must be opaque"
                )
        return self


class Candidate(_Record):
    """One ontology item the mapper considered, with why it scored as it did."""

    ontology_id: NonEmptyString
    sense: str
    layer: Layer
    confidence: float = Field(ge=0.0, le=1.0)
    matched_terms: tuple[str, ...]


class MappingRecord(_Record):
    """The raw result for one expression at one layer. Never post-corrected."""

    expression_id: NonEmptyString
    layer: Layer
    candidates: tuple[Candidate, ...]
    resolution: Resolution
    top_ontology_id: str = ""
    top_sense: str = ""
    ambiguity_margin: float | None = None

    @model_validator(mode="after")
    def _validate(self) -> MappingRecord:
        if self.resolution is Resolution.UNRESOLVED and self.top_ontology_id:
            raise MapperError("an unresolved mapping must not name a top candidate")
        if self.resolution is not Resolution.UNRESOLVED and not self.candidates:
            raise MapperError("a resolved mapping requires at least one candidate")
        return self


class FrozenOntology(_Record):
    """The frozen units, loaded read-only with their hashes carried along."""

    o_l1_sha256: NonEmptyString
    o_l2_sha256: NonEmptyString
    l1_items: tuple[JsonObject, ...]
    l2_items: tuple[JsonObject, ...]

    def items_for(self, layer: Layer) -> tuple[JsonObject, ...]:
        return self.l1_items if layer is Layer.L1 else self.l2_items


def load_frozen_ontology(directory: Path) -> FrozenOntology:
    """Load O_L1 and O_L2 exactly as frozen, carrying their digests forward."""
    l1 = json.loads((directory / "o_l1.json").read_text(encoding="utf-8"))
    l2 = json.loads((directory / "o_l2.json").read_text(encoding="utf-8"))
    return FrozenOntology(
        o_l1_sha256=str(l1["freeze"]["sha256"]),
        o_l2_sha256=str(l2["freeze"]["sha256"]),
        l1_items=tuple(entry["item"] for entry in l1["items"]),
        l2_items=tuple(entry["item"] for entry in l2["items"]),
    )


_WORD = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    {
        "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "is", "are",
        "was", "were", "be", "been", "at", "by", "from", "as", "it", "this", "that", "i",
        "my", "me", "you", "your", "we", "they", "he", "she", "his", "her", "their",
    }
)


def terms(text: str) -> set[str]:
    return {t for t in _WORD.findall(text.lower()) if t not in _STOPWORDS and len(t) > 2}


class MapperV1:
    """Lexical mapper over the frozen ontology.

    Deliberately simple and deliberately honest: candidates come from aliases, id segments and sense
    text, ranking is by normalised term overlap, and ambiguity is reported when the top two
    candidates fall within a margin. It attempts no repair and can reach nothing but the utterance
    and the ontology.
    """

    def __init__(
        self,
        ontology: FrozenOntology,
        *,
        top_k: int = 5,
        ambiguity_margin: float = 0.15,
        minimum_confidence: float = 0.10,
    ) -> None:
        self._ontology = ontology
        self._top_k = top_k
        self._ambiguity_margin = ambiguity_margin
        self._minimum_confidence = minimum_confidence
        self._index = {
            layer: self._build_index(ontology.items_for(layer), layer) for layer in Layer
        }

    @property
    def identity(self) -> JsonObject:
        return {
            "mapper_id": MAPPER_ID,
            "mapper_version": MAPPER_VERSION,
            "top_k": self._top_k,
            "ambiguity_margin": self._ambiguity_margin,
            "minimum_confidence": self._minimum_confidence,
            "o_l1_sha256": self._ontology.o_l1_sha256,
            "o_l2_sha256": self._ontology.o_l2_sha256,
        }

    def freeze_hash(self) -> str:
        """The mapper's own digest, so a run can prove which mapper produced it."""
        return hashlib.sha256(canonical_json(self.identity)).hexdigest()

    @staticmethod
    def _build_index(
        items: Sequence[JsonObject],
        layer: Layer,
    ) -> tuple[tuple[str, str, frozenset[str]], ...]:
        """Index each item by the terms that could evoke it: aliases, id tail and sense words."""
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
                    evoking |= terms(str(alias))
            # The id tail carries meaning: l1:predicate.change_arrangement evokes both words.
            tail = ontology_id.split(":", 1)[-1].replace(".", " ").replace("_", " ")
            evoking |= terms(tail)
            evoking |= terms(sense)
            if evoking:
                index.append((ontology_id, sense, frozenset(evoking)))
        return tuple(index)

    def map_expression(self, request: MapperInput, layer: Layer) -> MappingRecord:
        """Map one utterance at one layer, preserving the raw ranking."""
        _assert_input_is_clean(request)
        observed = terms(request.text)
        if not observed:
            return MappingRecord(
                expression_id=request.expression_id,
                layer=layer,
                candidates=(),
                resolution=Resolution.UNRESOLVED,
            )

        scored: list[Candidate] = []
        for ontology_id, sense, evoking in self._index[layer]:
            overlap = observed & evoking
            if not overlap:
                continue
            # Normalising only by the item's own vocabulary punished richly aliased items: a single
            # decisive alias hit scored 1/12 and fell under the floor, so "cancel my flight" mapped
            # to nothing. Precision against the utterance is combined with recall against the item,
            # and the stronger of the two carries, so one exact alias match is decisive while a
            # broad list still cannot win on breadth alone.
            item_recall = len(overlap) / len(evoking)
            utterance_precision = len(overlap) / len(observed)
            confidence = max(item_recall, utterance_precision)
            if confidence < self._minimum_confidence:
                continue
            scored.append(
                Candidate(
                    ontology_id=ontology_id,
                    sense=sense,
                    layer=layer,
                    confidence=round(confidence, 6),
                    matched_terms=tuple(sorted(overlap)),
                )
            )

        scored.sort(key=lambda c: (-c.confidence, c.ontology_id))
        top = tuple(scored[: self._top_k])
        if not top:
            return MappingRecord(
                expression_id=request.expression_id,
                layer=layer,
                candidates=(),
                resolution=Resolution.UNRESOLVED,
            )

        best = top[0]
        margin: float | None = None
        resolution = Resolution.MAPPED
        runner_up = top[1] if len(top) > 1 else None
        if runner_up is not None:
            margin = round(best.confidence - runner_up.confidence, 6)
            if margin <= self._ambiguity_margin:
                # Reported, not broken by a tie-break: a forced choice would hide the ambiguity the
                # diagnosis needs to see.
                resolution = Resolution.AMBIGUOUS

        return MappingRecord(
            expression_id=request.expression_id,
            layer=layer,
            candidates=top,
            resolution=resolution,
            top_ontology_id=best.ontology_id,
            top_sense=best.sense,
            ambiguity_margin=margin,
        )

    def map_all(self, requests: Sequence[MapperInput]) -> tuple[MappingRecord, ...]:
        return tuple(
            self.map_expression(request, layer) for request in requests for layer in Layer
        )


def _assert_input_is_clean(request: MapperInput) -> None:
    """Fail if a forbidden field somehow reached the mapper.

    The type already makes this unrepresentable. The check remains because the prohibition should be
    verifiable at runtime rather than only inferable from a class definition.
    """
    present = sorted(FORBIDDEN_INPUT_FIELDS & set(type(request).model_fields))
    if present:
        raise MapperError(
            f"mapper input declares forbidden fields: {present}; a mapper that can see these can "
            "special-case them"
        )


# Names that would indicate a post-hoc semantic fix. Held as bare identifiers and matched against
# parsed definitions rather than raw text: a substring scan matches this very list and reports the
# checker itself as a violation.
_CORRECTION_GATE_NAMES: frozenset[str] = frozenset(
    {"_repair", "_correct", "repair_mapping", "fix_mapping", "override_sense", "correct_sense"}
)


def assert_no_correction_gate(module_source: str) -> None:
    """Fail if a semantic correction gate is defined in the mapper.

    A post-hoc fix would make the metrics describe the fix rather than the mapper, so the absence of
    one is checked instead of asserted. The check parses the module and looks at what is actually
    defined, because a substring search cannot tell a definition from a mention of its name.
    """
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


def input_from_turn(expression_id: str, speaker: str, text: str) -> MapperInput:
    """Build mapper input from a turn, dropping everything else the turn carried."""
    return MapperInput(expression_id=expression_id, speaker=speaker, text=text)


def records_as_json(records: Sequence[MappingRecord]) -> list[dict[str, Any]]:
    return [record.model_dump(mode="json") for record in records]
