from __future__ import annotations

from collections.abc import Collection, Sequence

from ke_memory_demo.domain import CoverageEntry, CoverageStatus, Message


class CoverageInvariantError(ValueError):
    """Raised when message coverage is incomplete or internally inconsistent."""


class CoverageValidator:
    @staticmethod
    def validate(
        message: Message,
        entries: Sequence[CoverageEntry],
        *,
        known_references: Collection[str] | None = None,
    ) -> tuple[CoverageEntry, ...]:
        entries = tuple(entries)
        if not message.content:
            if entries:
                raise CoverageInvariantError("empty message must not have coverage entries")
            return ()

        content_length = len(message.content)
        for entry in entries:
            if entry.message_id != message.id:
                raise CoverageInvariantError(
                    f"coverage entry references a different message: {entry.message_id}"
                )
            if entry.end_char > content_length:
                raise CoverageInvariantError(
                    f"coverage range [{entry.start_char}, {entry.end_char}) is outside message "
                    f"{message.id}"
                )
            if entry.status is CoverageStatus.EXTRACTION_FAILED:
                raise CoverageInvariantError(
                    "extraction_failed coverage fails the extraction stage"
                )
            if entry.status is CoverageStatus.REPRESENTED:
                if not entry.ke_ids:
                    raise CoverageInvariantError("represented coverage requires references")
                if known_references is not None:
                    unknown = sorted(set(entry.ke_ids).difference(known_references))
                    if unknown:
                        raise CoverageInvariantError(
                            f"represented coverage contains unknown reference: {unknown[0]}"
                        )
            elif entry.ke_ids:
                raise CoverageInvariantError(f"{entry.status.value} coverage forbids references")

        boundaries = sorted(
            {
                0,
                content_length,
                *(entry.start_char for entry in entries),
                *(entry.end_char for entry in entries),
            }
        )
        normalized: list[CoverageEntry] = []
        for start_char, end_char in zip(boundaries, boundaries[1:]):
            if start_char == end_char:
                continue
            active = tuple(
                entry
                for entry in entries
                if entry.start_char <= start_char and entry.end_char >= end_char
            )
            if not active:
                raise CoverageInvariantError(
                    f"coverage gap at [{start_char}, {end_char}) in message {message.id}"
                )
            statuses = {entry.status for entry in active}
            if len(statuses) != 1:
                raise CoverageInvariantError(
                    f"conflicting coverage statuses at [{start_char}, {end_char})"
                )
            status = next(iter(statuses))
            references = (
                tuple(sorted({reference for entry in active for reference in entry.ke_ids}))
                if status is CoverageStatus.REPRESENTED
                else ()
            )
            segment = CoverageEntry(
                message_id=message.id,
                start_char=start_char,
                end_char=end_char,
                status=status,
                ke_ids=references,
            )
            if (
                normalized
                and normalized[-1].end_char == segment.start_char
                and normalized[-1].status is segment.status
                and normalized[-1].ke_ids == segment.ke_ids
            ):
                previous = normalized.pop()
                segment = CoverageEntry(
                    message_id=message.id,
                    start_char=previous.start_char,
                    end_char=segment.end_char,
                    status=segment.status,
                    ke_ids=segment.ke_ids,
                )
            normalized.append(segment)

        return tuple(normalized)
