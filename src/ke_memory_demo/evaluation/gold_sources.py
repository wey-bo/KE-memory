from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import re
from types import MappingProxyType

from ke_memory_demo.core.json import JsonObject, JsonValue
from ke_memory_demo.domain import Conversation

from .models import GoldSourceMapping, GoldSourceStatus


_EXPLICIT_SOURCE_FIELDS = frozenset({"source_chat_id", "source_chat_ids"})
_TEXT_REFERENCE = re.compile(
    r"\b(?:chat_id|Session)\s*:?\s*(\d+)\b",
    flags=re.IGNORECASE | re.ASCII,
)


class SourceMappingError(RuntimeError):
    """An explicit source number does not resolve to exactly one Exchange."""

    def __init__(self, source_number: int, match_count: int) -> None:
        self.source_number = source_number
        self.match_count = match_count
        super().__init__(f"source number {source_number} resolved to {match_count} Exchanges")


@dataclass(frozen=True)
class SourceCatalog:
    _exchange_ids_by_source_number: Mapping[int, tuple[str, ...]]

    @classmethod
    def from_conversation(cls, conversation: Conversation) -> SourceCatalog:
        exchange_ids_by_source_number: dict[int, set[str]] = {}
        for session in conversation.sessions:
            for exchange in session.exchanges:
                for record in (exchange.user, *exchange.events, exchange.assistant):
                    raw_message_id = record.source_metadata.get("raw_message_id")
                    if isinstance(raw_message_id, bool) or not isinstance(raw_message_id, int):
                        continue
                    exchange_ids_by_source_number.setdefault(raw_message_id, set()).add(exchange.id)
        frozen = {
            number: tuple(sorted(exchange_ids))
            for number, exchange_ids in sorted(exchange_ids_by_source_number.items())
        }
        return cls(MappingProxyType(frozen))

    def resolve(self, numbers: Sequence[int]) -> tuple[str, ...]:
        resolved: list[str] = []
        seen_numbers: set[int] = set()
        seen_exchange_ids: set[str] = set()
        for number in numbers:
            if type(number) is not int:
                raise TypeError("source numbers must be integers")
            if number in seen_numbers:
                continue
            seen_numbers.add(number)
            matches = self._exchange_ids_by_source_number.get(number, ())
            if len(matches) != 1:
                raise SourceMappingError(number, len(matches))
            exchange_id = matches[0]
            if exchange_id not in seen_exchange_ids:
                seen_exchange_ids.add(exchange_id)
                resolved.append(exchange_id)
        return tuple(resolved)


def build_gold_source_mapping(
    raw: JsonObject,
    catalog: SourceCatalog,
    *,
    question_id: str,
) -> GoldSourceMapping:
    references: list[tuple[int, str]] = []
    _collect_references(raw, "$", references)
    source_numbers = tuple(sorted({number for number, _path in references}))
    matched_paths = tuple(sorted({path for _number, path in references}))
    if not source_numbers:
        return GoldSourceMapping(
            question_id=question_id,
            status=GoldSourceStatus.UNMAPPABLE,
            matched_paths=matched_paths,
            exclusion_reason="no_explicit_source_reference",
        )
    try:
        source_exchange_ids = catalog.resolve(source_numbers)
    except SourceMappingError as error:
        return GoldSourceMapping(
            question_id=question_id,
            status=GoldSourceStatus.UNMAPPABLE,
            source_numbers=source_numbers,
            matched_paths=matched_paths,
            exclusion_reason=(
                f"source_number_{error.source_number}_match_count_{error.match_count}"
            ),
        )
    return GoldSourceMapping(
        question_id=question_id,
        status=GoldSourceStatus.MAPPED,
        source_numbers=source_numbers,
        source_exchange_ids=source_exchange_ids,
        matched_paths=matched_paths,
    )


def _collect_references(
    value: JsonValue,
    path: str,
    references: list[tuple[int, str]],
) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            nested_path = f"{path}.{key}"
            if key in _EXPLICIT_SOURCE_FIELDS:
                _collect_explicit_integers(nested, nested_path, references)
            _collect_references(nested, nested_path, references)
        return
    if isinstance(value, list):
        for index, nested in enumerate(value):
            _collect_references(nested, f"{path}[{index}]", references)
        return
    if isinstance(value, str):
        references.extend((int(match.group(1)), path) for match in _TEXT_REFERENCE.finditer(value))


def _collect_explicit_integers(
    value: JsonValue,
    path: str,
    references: list[tuple[int, str]],
) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, int):
        references.append((value, path))
        return
    if isinstance(value, dict):
        for key, nested in value.items():
            _collect_explicit_integers(nested, f"{path}.{key}", references)
        return
    if isinstance(value, list):
        for index, nested in enumerate(value):
            _collect_explicit_integers(nested, f"{path}[{index}]", references)
