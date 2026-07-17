from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from ke_memory_demo.core.ids import content_id
from ke_memory_demo.core.json import JsonValue
from ke_memory_demo.domain import AggregateNode, Exchange, KnowledgeEquation, MessageSpan

from .symbolic import SourceFragment, SymbolicInvariantError


class CanonicalSymbolicRecordSource:
    def __init__(
        self,
        exchanges: Sequence[Exchange],
        current_knowledge_equations: Sequence[KnowledgeEquation],
        aggregates: Sequence[AggregateNode],
    ) -> None:
        message_records = tuple(
            (record.id, exchange, record)
            for exchange in exchanges
            for record in (exchange.user, exchange.assistant)
        )
        self._messages = {
            record_id: (exchange, record) for record_id, exchange, record in message_records
        }
        if len(self._messages) != len(message_records):
            raise SymbolicInvariantError("canonical Exchanges contain duplicate message IDs")
        self._kes = {item.id: item for item in current_knowledge_equations}
        if len(self._kes) != len(current_knowledge_equations):
            raise SymbolicInvariantError("current KE records contain duplicate logical IDs")
        self._aggregates = {item.id: item for item in aggregates}
        if len(self._aggregates) != len(aggregates):
            raise SymbolicInvariantError("aggregate records contain duplicate logical IDs")
        ambiguous = sorted(set(self._kes).intersection(self._aggregates))
        if ambiguous:
            raise SymbolicInvariantError(
                f"record ID is ambiguous across KE and aggregate records: {ambiguous[0]}"
            )

    def get_knowledge_equation(self, record_id: str) -> KnowledgeEquation | None:
        return self._kes.get(record_id)

    def get_aggregate(self, record_id: str) -> AggregateNode | None:
        return self._aggregates.get(record_id)

    def resolve_span(self, span: MessageSpan) -> SourceFragment:
        record = self._messages.get(span.message_id)
        if record is None:
            raise SymbolicInvariantError(
                f"source span references an unknown canonical message: {span.message_id}"
            )
        exchange, message = record
        try:
            message.validate_span(span)
        except ValueError as error:
            raise SymbolicInvariantError(str(error)) from error
        return SourceFragment(
            fragment_id=content_id(
                "source_fragment",
                cast(JsonValue, span.model_dump(mode="json")),
            ),
            text=message.content[span.start_char : span.end_char],
            span=span,
            source_exchange_id=exchange.id,
            source_session_id=exchange.session_id,
        )
