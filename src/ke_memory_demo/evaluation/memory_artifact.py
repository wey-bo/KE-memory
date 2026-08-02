"""The memory artifact: what a build produces and what later layers consume.

The gap this closes was recorded plainly in review: the ontology arm recorded
``memory_artifact_sha256`` and no stage ever read the artifact. Recording a hash is not
consumption, so the chain was disconnected in the middle and every downstream claim rested on
raw turns instead of built memory.

Two things had to change together. The builder had to emit something extraction can use — a
handle-to-content index with per-turn digests, not a turn count — and the chain had to take that
artifact as its input rather than reaching back to the corpus.

The artifact is deliberately plain JSON. It crosses a process boundary from the sandboxed build,
so it cannot carry Python objects, and the type here is the contract for what survives that
crossing.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ke_memory_demo.core.json import JsonObject, JsonValue, canonical_json

NonEmptyString = Annotated[str, Field(min_length=1)]


class MemoryArtifactError(ValueError):
    """An artifact is malformed, or a consumer was handed something else."""


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ArtifactTurn(_Record):
    """One turn as the build recorded it.

    ``content_sha256`` lets a consumer prove it read the same bytes the build wrote, which is the
    difference between consuming an artifact and merely being handed one.
    """

    evidence_handle: NonEmptyString
    session_handle: NonEmptyString
    speaker: NonEmptyString
    text: str
    approximate_tokens: int = Field(ge=0)
    content_sha256: NonEmptyString


class ArtifactConversation(_Record):
    conversation_handle: NonEmptyString
    session_handles: tuple[str, ...]
    turns: tuple[ArtifactTurn, ...]

    @model_validator(mode="after")
    def _validate(self) -> ArtifactConversation:
        if not self.turns:
            raise MemoryArtifactError(
                f"conversation {self.conversation_handle} has no turns, so nothing was built"
            )
        unknown = sorted(
            {t.session_handle for t in self.turns} - set(self.session_handles)
        )
        if unknown:
            raise MemoryArtifactError(
                f"turns reference sessions absent from the index: {unknown[:5]}"
            )
        return self


class MemoryArtifact(_Record):
    """A built memory, addressable by handle, with the session membership downstream needs."""

    builder_id: NonEmptyString
    builder_version: NonEmptyString
    build_input_sha256: NonEmptyString
    conversations: tuple[ArtifactConversation, ...]
    session_members: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate(self) -> MemoryArtifact:
        if not self.conversations:
            raise MemoryArtifactError("an artifact must contain at least one conversation")
        handles = [c.conversation_handle for c in self.conversations]
        if len(handles) != len(set(handles)):
            raise MemoryArtifactError("conversation handles must be unique")
        return self

    def turns_for(self, conversation_handle: str) -> tuple[ArtifactTurn, ...]:
        for conversation in self.conversations:
            if conversation.conversation_handle == conversation_handle:
                return conversation.turns
        return ()

    def members_of(self, session_handle: str) -> tuple[str, ...]:
        raw = self.session_members.get(session_handle)
        if not isinstance(raw, list):
            return ()
        return tuple(str(item) for item in raw)

    def content_digest(self) -> str:
        """Digest over the whole artifact, so consumption can be proven."""
        return hashlib.sha256(canonical_json(self.as_json())).hexdigest()

    def as_json(self) -> JsonValue:
        return {
            "builder_id": self.builder_id,
            "builder_version": self.builder_version,
            "build_input_sha256": self.build_input_sha256,
            "conversations": [
                {
                    "conversation_handle": c.conversation_handle,
                    "session_handles": list(c.session_handles),
                    "turns": [
                        {
                            "evidence_handle": t.evidence_handle,
                            "session_handle": t.session_handle,
                            "speaker": t.speaker,
                            "text": t.text,
                            "approximate_tokens": t.approximate_tokens,
                            "content_sha256": t.content_sha256,
                        }
                        for t in c.turns
                    ],
                }
                for c in self.conversations
            ],
            "session_members": dict(self.session_members),
        }


def parse_memory_artifact(payload: Mapping[str, Any]) -> MemoryArtifact:
    """Rebuild the typed artifact from what crossed the process boundary.

    A consumer must go through this rather than indexing the raw dict, so a builder that changes
    its output shape fails here instead of silently producing wrong downstream results.
    """
    try:
        return MemoryArtifact.model_validate(dict(payload))
    except MemoryArtifactError:
        raise
    except Exception as error:
        raise MemoryArtifactError(
            f"the build output is not a memory artifact: {error}"
        ) from error


def assert_artifact_consumed(
    artifact: MemoryArtifact,
    consumed_digest: str,
) -> None:
    """Fail unless the consumer read the artifact it claims to have read.

    This is the check that makes consumption demonstrable. An arm that records a hash without
    reading the bytes cannot produce a matching digest.
    """
    expected = artifact.content_digest()
    if consumed_digest != expected:
        raise MemoryArtifactError(
            "the consumed digest does not match the artifact: recording a hash is not "
            f"consumption (expected {expected[:16]}, got {consumed_digest[:16]})"
        )


def turn_digest(speaker: str, text: str) -> str:
    return hashlib.sha256(f"{speaker}\x00{text}".encode()).hexdigest()


def artifact_turn_count(artifact: MemoryArtifact) -> int:
    return sum(len(c.turns) for c in artifact.conversations)


def artifact_handles(artifact: MemoryArtifact) -> Sequence[str]:
    return [t.evidence_handle for c in artifact.conversations for t in c.turns]
