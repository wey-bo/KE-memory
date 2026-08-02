"""Three mutually incompatible channels for a diagnostic benchmark.

Two earlier attempts split "public" from "gold" and were both defeated, for the same
underlying reason: the split was expressed as a denylist over a permissive structure, so
anything not explicitly forbidden travelled freely. Reviews found nested gold under a
benign key, gold in ``source_identity``, a ``PublicQuestion`` subclass carrying an answer,
and a memory builder holding all 32 questions before the freeze.

The structure here makes those unrepresentable rather than forbidden:

- :class:`MemoryBuildInput` is all a memory build receives. Conversation text plus opaque
  evidence handles. It has no question field at all, so a builder cannot see questions
  even if it tries.
- :class:`QuestionChannel` is released only after the freeze.
- :class:`GoldChannel` is for the scorer and oracles only.

Metadata is filtered by a recursive positive allowlist. Only keys that are explicitly
permitted survive, at every depth, and values are restricted to scalars. A key nobody
anticipated is dropped by default instead of admitted by default.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import re
from enum import StrEnum
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ke_memory_demo.core.json import JsonObject, JsonValue, canonical_json

NonEmptyString = Annotated[str, Field(min_length=1)]

_OPAQUE_HANDLE = re.compile(r"[a-z]\d{1,8}")

# Keys a memory build legitimately needs. Everything else is dropped.
#
# Dataset-identifying fields are deliberately absent: benchmark, split, question_type,
# sample_id, item_id and category would all let a mapper special-case a dataset, which the
# plan forbids as dataset-category-specific behaviour.
ALLOWED_CONVERSATION_METADATA: Final[frozenset[str]] = frozenset({"turn_count"})
ALLOWED_SESSION_METADATA: Final[frozenset[str]] = frozenset(
    {"public_session_ordinal", "session_index"}
)
ALLOWED_MESSAGE_METADATA: Final[frozenset[str]] = frozenset(
    {"evidence_handle", "speaker_label", "source_status", "public_turn_ordinal"}
)
# Source identity is not carried on the build input at all. Even a stable hash or a schema
# version can be matched offline against a known corpus, so it lives on LoadedBenchmark and
# is bound to the freeze receipt after the build has finished.
ALLOWED_SOURCE_IDENTITY: Final[frozenset[str]] = frozenset()


class ChannelError(ValueError):
    """A channel was constructed with content it must not carry."""


class BenchmarkId(StrEnum):
    BEAM = "beam"
    LOCOMO = "locomo"
    LONGMEMEVAL = "longmemeval"
    REGRESSION_SLICE = "regression_slice"


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def allowlist_metadata(metadata: Mapping[str, object], allowed: frozenset[str]) -> JsonObject:
    """Keep only allowed keys whose values are scalars.

    Recursive containers are dropped wholesale rather than filtered. A nested dict is how
    gold reached the public channel once already, and no legitimate public metadata field
    needs one, so refusing them removes the hiding place instead of policing it.
    """
    kept: dict[str, JsonValue] = {}
    for key, value in metadata.items():
        if key not in allowed:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            kept[key] = value
    return kept


class PublicTurn(_Record):
    """One addressable piece of conversation content. No gold, by construction."""

    evidence_handle: NonEmptyString
    speaker: NonEmptyString
    text: str
    approximate_tokens: int = Field(ge=0)


class PublicSession(_Record):
    session_handle: NonEmptyString
    turns: tuple[PublicTurn, ...]
    metadata: JsonObject = Field(default_factory=dict)

    def turn_handles(self) -> tuple[str, ...]:
        return tuple(t.evidence_handle for t in self.turns)

    @model_validator(mode="after")
    def _validate_metadata(self) -> PublicSession:
        _reject_unlisted(self.metadata, ALLOWED_SESSION_METADATA, f"session {self.session_handle}")
        return self


class PublicConversation(_Record):
    conversation_handle: NonEmptyString
    sessions: tuple[PublicSession, ...]
    metadata: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_metadata(self) -> PublicConversation:
        _reject_unlisted(
            self.metadata, ALLOWED_CONVERSATION_METADATA, f"conversation {self.conversation_handle}"
        )
        return self


class MemoryBuildInput(_Record):
    """Everything a memory build receives, and it names no dataset and no question.

    A builder given this object cannot read a question, an answer, a rubric or a dataset
    identifier, because the type has nowhere to put them. The ``benchmark`` field was
    removed for the same reason handles are opaque: a mapper that can tell which benchmark
    it is processing can special-case it, which the anti-cheating contract forbids. Dataset
    identity lives on the controller side, in :class:`LoadedBenchmark`.
    """

    conversations: tuple[PublicConversation, ...]

    @model_validator(mode="after")
    def _validate(self) -> MemoryBuildInput:
        if not self.conversations:
            raise ChannelError("memory build input must contain at least one conversation")
        return self

    def content_digest(self) -> str:
        """SHA-256 over the entire canonical build input.

        An earlier version hashed only the handle structure, so replacing a turn's text left
        the digest identical and the freeze receipt bound nothing about content. Every field
        a tamper could touch is included here, and a per-field mutation test proves the
        digest moves for each one.
        """
        return hashlib.sha256(canonical_json(self.canonical_content())).hexdigest()

    def canonical_content(self) -> JsonValue:
        """Deterministic full-content view, for hashing and for cross-process transfer."""
        return {
            "build_input_schema": "memory-build-input-v3",
            "conversations": [
                {
                    "conversation_handle": c.conversation_handle,
                    "metadata": dict(sorted(c.metadata.items())),
                    "sessions": [
                        {
                            "session_handle": s.session_handle,
                            "metadata": dict(sorted(s.metadata.items())),
                            "turns": [
                                {
                                    "evidence_handle": t.evidence_handle,
                                    "speaker": t.speaker,
                                    "text": t.text,
                                    "approximate_tokens": t.approximate_tokens,
                                }
                                for t in s.turns
                            ],
                        }
                        for s in c.sessions
                    ],
                }
                for c in self.conversations
            ],
        }

    def evidence_handles(self) -> dict[str, tuple[str, ...]]:
        return {
            c.conversation_handle: tuple(
                t.evidence_handle for s in c.sessions for t in s.turns
            )
            for c in self.conversations
        }


class BenchmarkQuestion(_Record):
    """A question, released after the freeze. Exactly three fields, always."""

    question_id: NonEmptyString
    conversation_handle: NonEmptyString
    question: NonEmptyString


class QuestionChannel(_Record):
    """Questions, withheld until the memory build is frozen."""

    benchmark: BenchmarkId
    questions: tuple[BenchmarkQuestion, ...]

    @model_validator(mode="after")
    def _reject_duplicates(self) -> QuestionChannel:
        ids = [q.question_id for q in self.questions]
        if len(ids) != len(set(ids)):
            raise ChannelError("question channel contains duplicate question ids")
        return self

    def for_question(self, question_id: str) -> BenchmarkQuestion | None:
        for question in self.questions:
            if question.question_id == question_id:
                return question
        return None


class GoldLabels(_Record):
    """Scoring material for one question. Scorer and oracles only."""

    question_id: NonEmptyString
    conversation_handle: NonEmptyString
    answer: str = ""
    category: str = ""
    evidence_refs: tuple[str, ...] = ()
    rubrics: tuple[str, ...] = ()
    answer_policy: str = ""
    requires_manual_review: bool = False
    metadata: JsonObject = Field(default_factory=dict)


class GoldChannel(_Record):
    benchmark: BenchmarkId
    labels: tuple[GoldLabels, ...]

    @model_validator(mode="after")
    def _reject_duplicates(self) -> GoldChannel:
        ids = [label.question_id for label in self.labels]
        if len(ids) != len(set(ids)):
            raise ChannelError("gold channel contains duplicate question ids")
        return self

    def label_for(self, question_id: str) -> GoldLabels | None:
        for label in self.labels:
            if label.question_id == question_id:
                return label
        return None


class LoadedBenchmark(_Record):
    """A benchmark separated into its three channels.

    ``benchmark`` and ``source_identity`` both live here, on the controller side, and
    deliberately not on the build input. A mapper that knows which dataset it is processing
    can special-case it, and even a stable content hash can be matched offline against a
    known corpus. The controller binds source identity to the freeze receipt after the build.
    """

    benchmark: BenchmarkId
    build_input: MemoryBuildInput
    questions: QuestionChannel
    gold: GoldChannel
    source_identity: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_agreement(self) -> LoadedBenchmark:
        benchmarks = {self.benchmark, self.questions.benchmark, self.gold.benchmark}
        if len(benchmarks) != 1:
            raise ChannelError("channels describe different benchmarks")
        known = {c.conversation_handle for c in self.build_input.conversations}
        orphans = sorted(
            {q.conversation_handle for q in self.questions.questions} - known
        ) + sorted({label.conversation_handle for label in self.gold.labels} - known)
        if orphans:
            raise ChannelError(f"channels reference unknown conversations: {orphans[:5]}")
        question_ids = {q.question_id for q in self.questions.questions}
        gold_ids = {label.question_id for label in self.gold.labels}
        if question_ids != gold_ids:
            raise ChannelError("question channel and gold channel describe different questions")
        return self


def assert_is_question_only(candidate: object) -> BenchmarkQuestion:
    """Fail unless the object is exactly a :class:`BenchmarkQuestion`.

    Uses an exact type check rather than ``isinstance``. A subclass passes an isinstance
    test while carrying extra fields, and a review demonstrated exactly that: a
    ``PublicQuestion`` subclass with an ``answer`` field reached an arm unchallenged.
    """
    if type(candidate) is not BenchmarkQuestion:
        raise ChannelError(
            "only an exact BenchmarkQuestion may reach an arm or selector; received "
            f"{type(candidate).__name__}"
        )
    return candidate


def assert_build_input_is_blind(
    build_input: MemoryBuildInput,
    questions: QuestionChannel,
    gold: GoldChannel,
    *,
    minimum_answer_length: int = 24,
) -> None:
    """Fail if question or gold content is recoverable from the build input.

    Complements the type-level guarantee. The types make questions unrepresentable; this
    catches a loader that copied question or answer *text* into conversation content or an
    allowed metadata value.
    """
    # Only string-valued metadata is compared, and the comparison is per conversation.
    # A global pool would collide with unrelated values: slice evidence handles are bare
    # digits such as "2", which matches a session ordinal rendered as a string and would
    # report a leak that does not exist.
    metadata_strings: set[str] = set()
    per_conversation: dict[str, set[str]] = {}
    for conversation in build_input.conversations:
        local = set(_scalar_strings(conversation.metadata))
        for session in conversation.sessions:
            local.update(_scalar_strings(session.metadata))
        per_conversation[conversation.conversation_handle] = local
        metadata_strings.update(local)

    for question in questions.questions:
        if question.question in metadata_strings:
            raise ChannelError(
                f"question {question.question_id} text appears in build-input metadata"
            )

    handles: dict[str, set[str]] = build_input_handles(build_input)
    for label in gold.labels:
        if len(label.answer) >= minimum_answer_length and any(
            label.answer in value for value in metadata_strings
        ):
            raise ChannelError(
                f"answer for {label.question_id} appears in build-input metadata"
            )
        gold_refs = {ref for ref in label.evidence_refs if ref}
        if not gold_refs:
            continue
        available = handles.get(label.conversation_handle, set())
        non_gold = available - gold_refs
        local_strings = per_conversation.get(label.conversation_handle, set())
        gold_named = gold_refs & local_strings
        if gold_named and non_gold and not (non_gold & local_strings):
            raise ChannelError(
                f"build-input metadata distinguishes the gold evidence subset for "
                f"{label.question_id}"
            )


def session_membership(build_input: MemoryBuildInput) -> dict[str, tuple[str, ...]]:
    """Map each session handle to the turn handles beneath it.

    Gold in LongMemEval names sessions while selection is scored per turn. Before handles
    became opaque a turn handle carried its session as a prefix, so membership was implicit;
    now it has to be published, or a session-level gold reference resolves to nothing and
    every such question is misread as an extraction failure.
    """
    return {
        session.session_handle: session.turn_handles()
        for conversation in build_input.conversations
        for session in conversation.sessions
    }


def build_input_handles(build_input: MemoryBuildInput) -> dict[str, set[str]]:
    return {
        c.conversation_handle: {t.evidence_handle for s in c.sessions for t in s.turns}
        for c in build_input.conversations
    }


def _reject_unlisted(metadata: JsonObject, allowed: frozenset[str], where: str) -> None:
    unlisted = sorted(set(metadata) - allowed)
    if unlisted:
        raise ChannelError(
            f"{where} carries metadata outside the allowlist: {unlisted[:6]}; "
            "public metadata is allowlisted, so a new field must be permitted explicitly"
        )
    nested = sorted(
        key
        for key, value in metadata.items()
        if not (isinstance(value, (str, int, float, bool)) or value is None)
    )
    if nested:
        raise ChannelError(
            f"{where} carries non-scalar metadata values: {nested[:6]}; "
            "nested containers are refused because they can hide gold"
        )


def _scalar_strings(metadata: JsonObject) -> set[str]:
    return {value for value in metadata.values() if isinstance(value, str)}


class HandleMint:
    """Assigns opaque handles and remembers the mapping on the controller side.

    Handles such as ``slice-BEAM-100K-C001-abstention-001`` disclose the benchmark, the
    conversation and the question category. A review found a builder could read all three
    straight off the handle, which defeats the same contract the allowlist protects. So the
    build input sees ``c0000``/``s0000``/``h0000`` and the controller keeps the translation.
    """

    def __init__(self) -> None:
        self._forward: dict[str, str] = {}
        self._reverse: dict[str, str] = {}

    def mint(self, kind: str, source_id: str) -> str:
        existing = self._forward.get(source_id)
        if existing is not None:
            return existing
        prefix = {"conversation": "c", "session": "s", "turn": "h"}[kind]
        ordinal = sum(1 for key in self._forward if key.startswith(f"{kind}:"))
        handle = f"{prefix}{ordinal:05d}"
        self._forward[f"{kind}:{source_id}"] = handle
        self._forward[source_id] = handle
        self._reverse[handle] = source_id
        return handle

    def opaque_for(self, source_id: str) -> str | None:
        return self._forward.get(source_id)

    def source_for(self, handle: str) -> str | None:
        return self._reverse.get(handle)

    @property
    def mapping(self) -> dict[str, str]:
        return dict(self._reverse)


def assert_handles_are_opaque(build_input: MemoryBuildInput) -> None:
    """Fail if any handle leaks dataset, category or item semantics.

    An opaque handle is a short token of a letter and digits. Anything longer is carrying
    information, which is exactly how the previous handles disclosed the benchmark.
    """
    offenders: list[str] = []
    for conversation in build_input.conversations:
        candidates = [conversation.conversation_handle]
        for session in conversation.sessions:
            candidates.append(session.session_handle)
            candidates.extend(t.evidence_handle for t in session.turns)
        offenders.extend(h for h in candidates if not _OPAQUE_HANDLE.fullmatch(h))
    if offenders:
        raise ChannelError(
            "build-input handles must be opaque, so they cannot disclose dataset or item "
            f"identity; offending handles: {sorted(set(offenders))[:6]}"
        )


def question_ids(channel: QuestionChannel) -> tuple[str, ...]:
    return tuple(sorted(q.question_id for q in channel.questions))


def turns_of(build_input: MemoryBuildInput, conversation_handle: str) -> Sequence[PublicTurn]:
    for conversation in build_input.conversations:
        if conversation.conversation_handle == conversation_handle:
            return tuple(t for s in conversation.sessions for t in s.turns)
    return ()
