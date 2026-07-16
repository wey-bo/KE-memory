from __future__ import annotations

import pytest

from ke_memory_demo.domain import CoverageEntry, CoverageStatus, Message, MessageRole
from ke_memory_demo.extraction.coverage import CoverageInvariantError, CoverageValidator


def _message(content: str = "abc") -> Message:
    return Message(id="message-1", role=MessageRole.USER, content=content, source_order=0)


def test_coverage_requires_every_codepoint_exactly_classified() -> None:
    with pytest.raises(CoverageInvariantError, match="gap"):
        CoverageValidator.validate(
            _message(),
            (
                CoverageEntry(
                    message_id="message-1",
                    start_char=0,
                    end_char=2,
                    status=CoverageStatus.REPRESENTED,
                    ke_ids=("ke-1",),
                ),
            ),
        )


def test_empty_message_requires_no_coverage_entries() -> None:
    assert CoverageValidator.validate(_message(""), ()) == ()

    with pytest.raises(CoverageInvariantError, match="empty message"):
        CoverageValidator.validate(
            _message(""),
            (
                CoverageEntry(
                    message_id="message-1",
                    start_char=0,
                    end_char=1,
                    status=CoverageStatus.NON_MEMORY,
                ),
            ),
        )


def test_coverage_uses_unicode_codepoint_offsets() -> None:
    entries = (
        CoverageEntry(
            message_id="message-1",
            start_char=0,
            end_char=1,
            status=CoverageStatus.NON_MEMORY,
        ),
        CoverageEntry(
            message_id="message-1",
            start_char=1,
            end_char=3,
            status=CoverageStatus.CONTEXT_ONLY,
        ),
    )

    assert CoverageValidator.validate(_message("A🙂界"), entries) == entries


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        (
            CoverageEntry(
                message_id="other-message",
                start_char=0,
                end_char=1,
                status=CoverageStatus.NON_MEMORY,
            ),
            "different message",
        ),
        (
            CoverageEntry(
                message_id="message-1",
                start_char=0,
                end_char=4,
                status=CoverageStatus.NON_MEMORY,
            ),
            "outside message",
        ),
    ],
)
def test_coverage_rejects_wrong_message_and_out_of_bounds_ranges(
    entry: CoverageEntry,
    message: str,
) -> None:
    with pytest.raises(CoverageInvariantError, match=message):
        CoverageValidator.validate(_message(), (entry,))


def test_overlapping_represented_ranges_union_references() -> None:
    normalized = CoverageValidator.validate(
        _message(),
        (
            CoverageEntry(
                message_id="message-1",
                start_char=0,
                end_char=2,
                status=CoverageStatus.REPRESENTED,
                ke_ids=("ke-b",),
            ),
            CoverageEntry(
                message_id="message-1",
                start_char=1,
                end_char=3,
                status=CoverageStatus.REPRESENTED,
                ke_ids=("ke-a",),
            ),
        ),
        known_references={"ke-a", "ke-b"},
    )

    assert normalized == (
        CoverageEntry(
            message_id="message-1",
            start_char=0,
            end_char=1,
            status=CoverageStatus.REPRESENTED,
            ke_ids=("ke-b",),
        ),
        CoverageEntry(
            message_id="message-1",
            start_char=1,
            end_char=2,
            status=CoverageStatus.REPRESENTED,
            ke_ids=("ke-a", "ke-b"),
        ),
        CoverageEntry(
            message_id="message-1",
            start_char=2,
            end_char=3,
            status=CoverageStatus.REPRESENTED,
            ke_ids=("ke-a",),
        ),
    )


def test_overlapping_ranges_reject_conflicting_statuses() -> None:
    with pytest.raises(CoverageInvariantError, match="conflicting"):
        CoverageValidator.validate(
            _message(),
            (
                CoverageEntry(
                    message_id="message-1",
                    start_char=0,
                    end_char=3,
                    status=CoverageStatus.REPRESENTED,
                    ke_ids=("ke-1",),
                ),
                CoverageEntry(
                    message_id="message-1",
                    start_char=1,
                    end_char=2,
                    status=CoverageStatus.CONTEXT_ONLY,
                ),
            ),
        )


@pytest.mark.parametrize("status", [CoverageStatus.CONTEXT_ONLY, CoverageStatus.NON_MEMORY])
def test_non_represented_coverage_forbids_references(status: CoverageStatus) -> None:
    with pytest.raises(CoverageInvariantError, match="forbids references"):
        CoverageValidator.validate(
            _message(),
            (
                CoverageEntry(
                    message_id="message-1",
                    start_char=0,
                    end_char=3,
                    status=status,
                    ke_ids=("ke-1",),
                ),
            ),
        )


def test_represented_coverage_requires_references() -> None:
    with pytest.raises(CoverageInvariantError, match="requires references"):
        CoverageValidator.validate(
            _message(),
            (
                CoverageEntry(
                    message_id="message-1",
                    start_char=0,
                    end_char=3,
                    status=CoverageStatus.REPRESENTED,
                ),
            ),
        )


def test_represented_coverage_rejects_unknown_references() -> None:
    with pytest.raises(CoverageInvariantError, match="unknown reference"):
        CoverageValidator.validate(
            _message(),
            (
                CoverageEntry(
                    message_id="message-1",
                    start_char=0,
                    end_char=3,
                    status=CoverageStatus.REPRESENTED,
                    ke_ids=("ke-missing",),
                ),
            ),
            known_references={"ke-other"},
        )


def test_extraction_failed_coverage_fails_validation() -> None:
    with pytest.raises(CoverageInvariantError, match="extraction_failed"):
        CoverageValidator.validate(
            _message(),
            (
                CoverageEntry(
                    message_id="message-1",
                    start_char=0,
                    end_char=3,
                    status=CoverageStatus.EXTRACTION_FAILED,
                ),
            ),
        )
