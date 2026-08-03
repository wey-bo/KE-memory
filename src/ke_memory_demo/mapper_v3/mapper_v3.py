"""Mapper v3 interface: blind input, multi-label output over 0..N frames.

Blindness is inherited unchanged and remains structural: an utterance, a speaker, and an opaque id,
with no field for a question, a gold label, a split or a dataset name.

The output contract is what differs from v2. v2 returned one answer per utterance, and the previous
round measured 35 incomplete selections out of 76 multi-target cases. v3 returns every frame it found,
so a multi-target utterance produces a multi-target answer and the metric can distinguish an
incomplete selection from a wrong one.

Three outcomes, and each is reached for a stated reason rather than by a threshold:

``mapped``
    one or more frames, with the strongest clearly ahead

``ambiguous``
    frames that compete within a margin, so naming one would hide the competition

``unresolved``
    no admissible evidence — including the reasoned case where the utterance only asks for something
    and therefore asserts nothing about the speaker
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ke_memory_demo.core.json import JsonObject, canonical_json

from .constructions import detect, is_request_only
from .frames import FrameGenerator, SemanticFrame, build_entries

NonEmptyString = Annotated[str, Field(min_length=1)]

MAPPER_ID = "mapper-v3-construction"
MAPPER_VERSION = "3.0.0"

# Two frames compete when the weaker reaches this share of the stronger. Not an accuracy knob: it
# expresses when reporting one would misrepresent a genuine competition as a confident answer.
AMBIGUITY_RATIO = 0.85


class MapperV3Error(ValueError):
    """A mapper was given something it must not see, or configured incorrectly."""


class Outcome(StrEnum):
    MAPPED = "mapped"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"


class UnresolvedReason(StrEnum):
    """Why nothing was returned. An unexplained decline cannot be diagnosed."""

    NO_CONTENT = "no_content_terms"
    REQUEST_ONLY = "request_only_asserts_nothing"
    NO_ADMISSIBLE_EVIDENCE = "no_admissible_evidence"


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ExpressionInput(_Record):
    """An utterance and its speaker. There is nowhere to put anything else."""

    expression_id: NonEmptyString
    speaker: NonEmptyString
    text: NonEmptyString

    @model_validator(mode="after")
    def _reject_disclosing_id(self) -> ExpressionInput:
        lowered = self.expression_id.lower()
        for marker in ("beam", "locomo", "longmemeval", "slice", "gold", "valid"):
            if marker in lowered:
                raise MapperV3Error(
                    f"expression_id {self.expression_id!r} discloses dataset identity; ids must be "
                    "opaque so a mapper cannot special-case a corpus"
                )
        return self


class MappingResult(_Record):
    """The raw result. Every frame is preserved, so multi-label output is measurable."""

    expression_id: NonEmptyString
    outcome: Outcome
    frames: tuple[JsonObject, ...]
    target_ids: tuple[str, ...]
    competing_ids: tuple[str, ...] = ()
    unresolved_reason: UnresolvedReason | None = None
    constructions: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _validate(self) -> MappingResult:
        if self.outcome is Outcome.UNRESOLVED:
            if self.frames or self.target_ids:
                raise MapperV3Error(
                    "an unresolved result must carry no frame: it comes from finding no admissible "
                    "evidence, not from filtering a frame out afterwards"
                )
            if self.unresolved_reason is None:
                raise MapperV3Error("an unresolved result must record why it declined")
        else:
            if not self.frames:
                raise MapperV3Error("a mapped or ambiguous result requires frames")
            if not self.target_ids:
                raise MapperV3Error("a resolved result must name its targets")
        if self.outcome is Outcome.AMBIGUOUS and len(self.competing_ids) < 2:
            raise MapperV3Error("an ambiguous result must name at least two competing targets")
        # Multi-label is the point: every frame contributes a target.
        if self.outcome is not Outcome.UNRESOLVED and len(self.target_ids) != len(self.frames):
            raise MapperV3Error(
                "each frame must contribute exactly one target, or the multi-label count is wrong"
            )
        return self

    @property
    def is_multi_label(self) -> bool:
        return len(self.target_ids) > 1


class MapperV3:
    """The mapper. Reads an utterance and the frozen ontology, and nothing else."""

    def __init__(
        self,
        v2_dir: Path,
        v3_dir: Path,
        *,
        max_frames: int = 6,
        ambiguity_ratio: float = AMBIGUITY_RATIO,
    ) -> None:
        v2_l1 = cast(
            "dict[str, Any]", json.loads((v2_dir / "o_l1.json").read_text(encoding="utf-8"))
        )
        v2_l2 = cast(
            "dict[str, Any]", json.loads((v2_dir / "o_l2.json").read_text(encoding="utf-8"))
        )
        v3_l1 = cast(
            "dict[str, Any]",
            json.loads((v3_dir / "o_l1_additions.json").read_text(encoding="utf-8")),
        )
        v3_l2 = cast(
            "dict[str, Any]",
            json.loads((v3_dir / "o_l2_additions.json").read_text(encoding="utf-8")),
        )
        self._digests = {
            "o_v2_l1_sha256": str(v2_l1["freeze"]["sha256"]),
            "o_v2_l2_sha256": str(v2_l2["freeze"]["sha256"]),
            "o_v3_l1_sha256": str(v3_l1["freeze"]["sha256"]),
            "o_v3_l2_sha256": str(v3_l2["freeze"]["sha256"]),
        }
        self._ambiguity_ratio = ambiguity_ratio
        self._generator = FrameGenerator(
            build_entries(
                cast("list[JsonObject]", v2_l1["items"]),
                cast("list[JsonObject]", v2_l2["items"]),
                cast("list[JsonObject]", v3_l1["items"]),
                cast("list[JsonObject]", v3_l2["items"]),
            ),
            max_frames=max_frames,
        )

    @property
    def identity(self) -> JsonObject:
        return {
            "mapper_id": MAPPER_ID,
            "mapper_version": MAPPER_VERSION,
            "ambiguity_ratio": self._ambiguity_ratio,
            **self._digests,
        }

    def freeze_hash(self) -> str:
        return hashlib.sha256(canonical_json(self.identity)).hexdigest()

    def map_expression(self, request: ExpressionInput) -> MappingResult:
        """Map one utterance, returning every frame it attests."""
        hits = detect(request.text)
        constructions = tuple(sorted({str(h.construction) for h in hits}))

        if is_request_only(hits):
            # Reasoned rather than thresholded: a request asserts nothing about the speaker.
            return MappingResult(
                expression_id=request.expression_id,
                outcome=Outcome.UNRESOLVED,
                frames=(),
                target_ids=(),
                unresolved_reason=UnresolvedReason.REQUEST_ONLY,
                constructions=constructions,
            )

        frames = self._generator.generate(request.text)
        if not frames:
            reason = (
                UnresolvedReason.NO_CONTENT
                if not request.text.strip()
                else UnresolvedReason.NO_ADMISSIBLE_EVIDENCE
            )
            return MappingResult(
                expression_id=request.expression_id,
                outcome=Outcome.UNRESOLVED,
                frames=(),
                target_ids=(),
                unresolved_reason=reason,
                constructions=constructions,
            )

        competing = self._competing(frames)
        outcome = Outcome.AMBIGUOUS if len(competing) >= 2 else Outcome.MAPPED
        return MappingResult(
            expression_id=request.expression_id,
            outcome=outcome,
            frames=tuple(f.as_json() for f in frames),
            target_ids=tuple(f.ontology_id for f in frames),
            competing_ids=tuple(f.ontology_id for f in competing) if outcome is Outcome.AMBIGUOUS else (),
            constructions=constructions,
        )

    def _competing(self, frames: Sequence[SemanticFrame]) -> tuple[SemanticFrame, ...]:
        """Frames supported comparably to the strongest.

        Construction support is part of the comparison: a frame resting on vocabulary alone does not
        compete with one that also matches what the utterance is doing, however close the scores.
        """
        best = frames[0]
        threshold = best.score * self._ambiguity_ratio
        return tuple(
            frame
            for frame in frames
            if frame.score >= threshold
            and frame.has_construction_support == best.has_construction_support
        )

    def provenance(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "freeze_hash": self.freeze_hash(),
            "generation": self._generator.provenance(),
            "blindness": {
                "inputs": ["expression_id (opaque)", "speaker", "text"],
                "absent_by_construction": [
                    "question",
                    "gold label",
                    "split",
                    "dataset name",
                    "sample id",
                ],
            },
            "multi_label": (
                "every frame contributes a target, so a multi-target utterance yields a multi-target "
                "answer. v2 returned one answer and the previous round measured 35 incomplete "
                "selections out of 76 multi-target cases."
            ),
            "unresolved_is_reasoned": (
                "an unresolved result records why: no content, a request that asserts nothing about "
                "the speaker, or no admissible evidence. None of the three is a score cut."
            ),
        }
