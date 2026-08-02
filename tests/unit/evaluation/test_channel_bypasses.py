"""Regressions for every bypass a review found in the channel separation.

Each test below corresponds to a demonstrated defeat of an earlier implementation. They are
written as counterexamples rather than as feature tests, because in every case the code
looked correct and the leak was only visible when someone tried to get through it.

The four bypasses, all reproduced against the code before this rework:

1. gold nested under a benign metadata key
2. gold placed in ``source_identity``, which was never checked
3. a question subclass carrying an ``answer`` field, which passed an isinstance guard
4. a memory builder holding all 32 questions before the freeze
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ke_memory_demo.core.json import JsonObject
from ke_memory_demo.evaluation.channels import (
    ALLOWED_SESSION_METADATA,
    BenchmarkQuestion,
    ChannelError,
    MemoryBuildInput,
    PublicConversation,
    PublicSession,
    PublicTurn,
    assert_is_question_only,
)


def _conversation(
    metadata: JsonObject | None = None,
    session_metadata: JsonObject | None = None,
) -> PublicConversation:
    return PublicConversation(
        conversation_handle="c0",
        sessions=(
            PublicSession(
                session_handle="c0--s0000",
                turns=(
                    PublicTurn(
                        evidence_handle="h0",
                        speaker="user",
                        text="hello",
                        approximate_tokens=1,
                    ),
                ),
                metadata=session_metadata or {"public_session_ordinal": 0},
            ),
        ),
        metadata=metadata or {},
    )


def test_bypass_one_gold_nested_under_a_benign_key_is_refused() -> None:
    """A nested container was how gold travelled past a top-level key check."""
    with pytest.raises(ValidationError, match="non-scalar|allowlist"):
        MemoryBuildInput(
            conversations=(
                _conversation(session_metadata={"safe": {"answer": "secret"}}),
            ),
        )


def test_bypass_one_variant_unlisted_scalar_key_is_refused() -> None:
    """The allowlist is positive, so an unanticipated key is dropped by default."""
    with pytest.raises(ValidationError, match="allowlist"):
        MemoryBuildInput(
            conversations=(_conversation(session_metadata={"answer": "secret"}),),
        )


def test_bypass_two_source_identity_is_not_on_the_build_input_at_all() -> None:
    """Stronger than allowlisting it: the field is gone.

    An allowlisted source_identity still shipped a stable value to the builder, and even a
    content hash or schema version can be matched offline against a known corpus. It now lives
    on LoadedBenchmark and is bound to the freeze receipt after the build.
    """
    assert "source_identity" not in MemoryBuildInput.model_fields
    leaks: tuple[JsonObject, ...] = (
        {"gold": "secret"},
        {"gold_sha256": "abc"},
        {"loader_id": "slice"},
        {"build_input_schema_version": "2"},
    )
    for leaking in leaks:
        with pytest.raises(ValidationError, match="not permitted"):
            MemoryBuildInput(
                conversations=(_conversation(),),
                source_identity=leaking,  # pyright: ignore[reportCallIssue]
            )
    # The build input carries exactly one field: conversation content.
    assert set(MemoryBuildInput.model_fields) == {"conversations"}


def test_bypass_three_a_question_subclass_cannot_reach_an_arm() -> None:
    """An isinstance guard admits a subclass; the check is now on exact type."""

    class SneakyQuestion(BenchmarkQuestion):
        answer: str = "secret"

    sneaky = SneakyQuestion(question_id="q1", conversation_handle="c0", question="q?")
    assert isinstance(sneaky, BenchmarkQuestion)  # the old guard would have passed
    with pytest.raises(ChannelError, match="exact BenchmarkQuestion"):
        assert_is_question_only(sneaky)

    plain = BenchmarkQuestion(question_id="q1", conversation_handle="c0", question="q?")
    assert assert_is_question_only(plain) is plain


def test_bypass_four_a_memory_build_cannot_receive_questions() -> None:
    """Question-blindness is structural: the input type has nowhere to put a question."""
    assert "questions" not in MemoryBuildInput.model_fields
    with pytest.raises(ValidationError):
        MemoryBuildInput(
            conversations=(_conversation(),),
            questions=("what did the user prefer?",),  # type: ignore[call-arg]
        )


def test_dataset_identifying_fields_are_refused() -> None:
    """A mapper that can see the dataset can special-case it, which the plan forbids."""
    for key in ("benchmark", "split", "question_type", "sample_id", "item_id", "category"):
        assert key not in ALLOWED_SESSION_METADATA
        with pytest.raises(ValidationError, match="allowlist"):
            MemoryBuildInput(conversations=(_conversation(session_metadata={key: "beam"}),))


def test_builder_receives_only_the_build_input() -> None:
    """The builder's own signature cannot express access to questions or gold."""
    captured: list[object] = []

    def build(build_input: MemoryBuildInput) -> JsonObject:
        captured.append(build_input)
        return {"n": 1}

    build(MemoryBuildInput(conversations=(_conversation(),)))
    [seen] = captured
    assert isinstance(seen, MemoryBuildInput)
    assert not hasattr(seen, "questions")
    assert not hasattr(seen, "gold")
    # The dataset name is gone too: knowing the benchmark permits special-casing it.
    assert "benchmark" not in MemoryBuildInput.model_fields
