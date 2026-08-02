"""Freeze receipt for a question-blind memory build.

The first implementation recorded a timestamp with ``build_count`` hardcoded to 1 and no
link to anything that was actually built. A review called it what it was: a self-reported
claim rather than evidence.

This version cannot be written without the build having happened. :class:`MemoryBuilder`
counts its own invocations and hashes what it produced, so the receipt binds five things
together:

- the public content digest the build consumed
- the hash of the memory artifact it produced
- the builder contract identity (who built it, under what settings)
- the observed invocation count, taken from the builder rather than asserted
- the moment questions were released, which must follow the freeze

A receipt whose builder ran twice, or whose artifact hash does not match the artifact
presented for scoring, cannot be rendered.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
import hashlib
from datetime import UTC, datetime
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ke_memory_demo.core.ids import content_id
from ke_memory_demo.core.json import JsonObject, JsonValue, canonical_json

from .channels import BenchmarkQuestion, MemoryBuildInput

NonEmptyString = Annotated[str, Field(min_length=1)]

ArtifactT = TypeVar("ArtifactT")


class FreezeReceiptError(ValueError):
    """A freeze receipt is unobtainable or does not describe what actually ran."""


class BuilderContract(BaseModel):
    """Identity of the thing that built memory, hashed into the receipt."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    builder_id: NonEmptyString
    builder_version: NonEmptyString
    settings: JsonObject = Field(default_factory=dict)

    def contract_hash(self) -> str:
        return content_id(
            "builder-contract",
            {
                "builder_id": self.builder_id,
                "builder_version": self.builder_version,
                "settings": self.settings,
            },
        )


class MemoryBuilder(Generic[ArtifactT]):
    """Wraps a memory build so the receipt can observe it rather than trust it.

    The invocation count is measured here. That is the difference between evidence and a
    claim: a caller cannot assert "built once" while having called twice.
    """

    def __init__(
        self,
        contract: BuilderContract,
        build: Callable[[MemoryBuildInput], ArtifactT],
        canonicalize: Callable[[ArtifactT], JsonValue],
    ) -> None:
        self._contract = contract
        self._build = build
        self._canonicalize = canonicalize
        self._invocations = 0
        self._artifact: ArtifactT | None = None
        self._artifact_hash: str | None = None
        self._public_digest: str | None = None
        self._built_at: datetime | None = None

    @property
    def contract(self) -> BuilderContract:
        return self._contract

    @property
    def invocations(self) -> int:
        return self._invocations

    def build(self, build_input: MemoryBuildInput) -> ArtifactT:
        """Build memory from build input only. Counted, hashed and timestamped.

        The hash is computed here from canonical bytes rather than accepted from a caller.
        A previous version took a digest callable and was handed one that returned the
        entire serialized artifact, so ``memory_artifact_hash`` carried the whole payload
        instead of a hash of it.
        """
        self._invocations += 1
        artifact = self._build(build_input)
        self._artifact = artifact
        self._artifact_hash = self._hash_artifact(artifact)
        self._public_digest = build_input.content_digest()
        self._built_at = datetime.now(UTC)
        return artifact

    def _hash_artifact(self, artifact: ArtifactT) -> str:
        return hashlib.sha256(canonical_json(self._canonicalize(artifact))).hexdigest()

    def hash_artifact(self, artifact: ArtifactT) -> str:
        """Expose canonical hashing so a verifier cannot invent its own scheme."""
        return self._hash_artifact(artifact)

    def freeze(self) -> "FrozenMemory[ArtifactT]":
        """Close the build. Any later build attempt invalidates the receipt."""
        if self._artifact is None or self._artifact_hash is None:
            raise FreezeReceiptError("cannot freeze before a memory build has run")
        if self._public_digest is None or self._built_at is None:
            raise FreezeReceiptError("build did not record its inputs")
        return FrozenMemory(
            builder=self,
            artifact=self._artifact,
            artifact_hash=self._artifact_hash,
            public_digest=self._public_digest,
            frozen_at=self._built_at,
        )


class FrozenMemory(Generic[ArtifactT]):
    """A frozen build plus the receipt it can produce.

    Questions are released through :meth:`release_questions`, which is the only way to
    obtain them and which stamps the release time into the receipt.
    """

    def __init__(
        self,
        *,
        builder: MemoryBuilder[ArtifactT],
        artifact: ArtifactT,
        artifact_hash: str,
        public_digest: str,
        frozen_at: datetime,
    ) -> None:
        self._builder = builder
        self._artifact = artifact
        self._artifact_hash = artifact_hash
        self._public_digest = public_digest
        self._frozen_at = frozen_at
        self._invocations_at_freeze = builder.invocations
        self._released_at: datetime | None = None
        self._question_count = 0

    @property
    def artifact(self) -> ArtifactT:
        return self._artifact

    def release_questions(
        self,
        questions: Sequence[BenchmarkQuestion],
    ) -> tuple[BenchmarkQuestion, ...]:
        """Hand over questions, recording that this happened after the freeze."""
        if self._released_at is not None:
            raise FreezeReceiptError("questions have already been released once")
        self._released_at = datetime.now(UTC)
        self._question_count = len(questions)
        return tuple(questions)

    def receipt(self) -> "FreezeReceipt":
        # Re-verify the artifact here rather than relying on the caller having remembered
        # to call verify_artifact. A receipt that can be produced without checking the
        # artifact is not evidence about the artifact.
        if self._builder.hash_artifact(self._artifact) != self._artifact_hash:
            raise FreezeReceiptError(
                "memory artifact does not match the hash recorded at freeze time"
            )
        if self._released_at is None:
            raise FreezeReceiptError(
                "receipt requires that questions were released after the freeze"
            )
        if self._builder.invocations != self._invocations_at_freeze:
            raise FreezeReceiptError(
                "memory was rebuilt after freezing: observed "
                f"{self._builder.invocations} builds, {self._invocations_at_freeze} at freeze"
            )
        return FreezeReceipt(
            public_digest=self._public_digest,
            memory_artifact_hash=self._artifact_hash,
            builder_contract_hash=self._builder.contract.contract_hash(),
            builder_id=self._builder.contract.builder_id,
            observed_build_count=self._builder.invocations,
            frozen_at=self._frozen_at,
            questions_released_at=self._released_at,
            question_count=self._question_count,
        )

    def verify_artifact(self, artifact: ArtifactT | None = None) -> None:
        """Confirm the artifact presented for scoring is the one that was frozen."""
        candidate = self._artifact if artifact is None else artifact
        if self._builder.hash_artifact(candidate) != self._artifact_hash:
            raise FreezeReceiptError(
                "memory artifact does not match the hash recorded at freeze time"
            )


class FreezeReceipt(BaseModel):
    """Evidence, not assertion: every field is observed from a real build."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    public_digest: NonEmptyString
    memory_artifact_hash: NonEmptyString
    builder_contract_hash: NonEmptyString
    builder_id: NonEmptyString
    observed_build_count: int
    frozen_at: datetime
    questions_released_at: datetime
    question_count: int

    @model_validator(mode="after")
    def _validate_freeze_order(self) -> FreezeReceipt:
        if self.observed_build_count != 1:
            raise FreezeReceiptError(
                "memory must be built exactly once per run; observed "
                f"{self.observed_build_count}"
            )
        if self.questions_released_at < self.frozen_at:
            raise FreezeReceiptError("questions were released before the freeze")
        return self

    def artifact(self) -> JsonObject:
        verified = FreezeReceipt.model_validate(self.model_dump())
        payload: dict[str, JsonValue] = {
            "public_digest": verified.public_digest,
            "memory_artifact_hash": verified.memory_artifact_hash,
            "builder_contract_hash": verified.builder_contract_hash,
            "builder_id": verified.builder_id,
            "observed_build_count": verified.observed_build_count,
            "frozen_at": verified.frozen_at.isoformat(),
            "questions_released_at": verified.questions_released_at.isoformat(),
            "question_count": verified.question_count,
            "freeze_order_valid": verified.questions_released_at >= verified.frozen_at,
            "evidence_basis": (
                "build count observed from the builder; memory artifact hashed as SHA-256 "
                "of canonical bytes and re-verified when the receipt is produced; build "
                "input bound by content digest; release time recorded when questions were "
                "handed over. The builder receives MemoryBuildInput, which has no question "
                "field, so question-blindness is structural rather than asserted."
            ),
        }
        return payload
