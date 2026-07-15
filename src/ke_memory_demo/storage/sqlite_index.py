from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from datetime import UTC, datetime
import hashlib
import os
from pathlib import Path
import sqlite3
import stat
from types import MappingProxyType
from typing import Literal, TypeVar, cast
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from ke_memory_demo.core.json import canonical_json
from ke_memory_demo.domain import (
    AggregateNode,
    AssertionRef,
    ConceptRef,
    Exchange,
    Expression,
    IndividualRef,
    KnowledgeEquation,
    Lifecycle,
    Message,
    MessageSpan,
    OperatorRef,
    ToolEvent,
)

from .layout import StorageError, fsync_directory


ModelT = TypeVar("ModelT", bound=BaseModel)


class IndexBuildError(StorageError, RuntimeError):
    """A derived index could not be built without risking the prior cache."""


class IndexQueryError(StorageError, ValueError):
    """A symbolic lookup is invalid or the derived cache is unavailable."""


class IndexStats(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_count: int
    message_count: int
    tool_event_count: int
    ke_count: int
    ke_revision_count: int
    ontology_binding_count: int
    expression_ref_count: int
    operator_ref_count: int
    ke_relation_count: int
    source_span_count: int
    aggregate_count: int
    aggregate_membership_count: int
    integrity_result: Literal["ok"]

    @property
    def table_counts(self) -> Mapping[str, int]:
        return MappingProxyType(
            {
                "exchanges": self.exchange_count,
                "messages": self.message_count,
                "ke_revisions": self.ke_revision_count,
                "ontology_bindings": self.ontology_binding_count,
                "expression_refs": self.expression_ref_count,
                "ke_relations": self.ke_relation_count,
                "source_spans": self.source_span_count,
                "aggregates": self.aggregate_count,
                "aggregate_membership": self.aggregate_membership_count,
            }
        )


_replace = os.replace


class MemoryIndex:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path.expanduser().absolute()

    def rebuild(
        self,
        exchanges: Iterable[Exchange],
        knowledge_equations: Iterable[KnowledgeEquation],
        aggregates: Iterable[AggregateNode],
    ) -> IndexStats:
        materialized = _materialize_inputs(exchanges, knowledge_equations, aggregates)
        ordered_exchanges, ordered_kes, ordered_aggregates = materialized
        _validate_source_spans(ordered_exchanges, ordered_kes, ordered_aggregates)

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.db_path.parent / f".{self.db_path.name}.tmp-{uuid4().hex}"
        try:
            stats = _build_temporary_database(
                temporary,
                ordered_exchanges,
                ordered_kes,
                ordered_aggregates,
            )
            _install_cache(temporary, self.db_path)
        except BaseException:
            _remove_temporary_database(temporary)
            raise
        return stats

    def ordered_exchange_ids(self) -> tuple[str, ...]:
        return self._lookup_ids(
            "SELECT id FROM exchanges ORDER BY global_ordinal, id",
            (),
        )

    def ordered_ke_ids(self) -> tuple[str, ...]:
        return self._lookup_ids("SELECT id FROM ke_logical_ids ORDER BY id", ())

    def ordered_aggregate_ids(self) -> tuple[str, ...]:
        return self._lookup_ids("SELECT id FROM aggregates ORDER BY depth, id", ())

    def lookup_term_id(self, document_id: str) -> tuple[str, ...]:
        return self._lookup_ids(
            "SELECT ke_id FROM expression_refs WHERE term_id = ? "
            "UNION SELECT ke_id FROM ontology_bindings WHERE document_id = ? "
            "ORDER BY 1",
            (document_id, document_id),
        )

    def lookup_unresolved_label(self, normalized_surface: str) -> tuple[str, ...]:
        return self._lookup_ids(
            "SELECT DISTINCT ke_id FROM ontology_bindings "
            "WHERE normalized_surface = ? AND status <> 'resolved' ORDER BY ke_id",
            (normalized_surface,),
        )

    def lookup_operator_id(self, operator_id: str) -> tuple[str, ...]:
        return self._lookup_ids(
            "SELECT DISTINCT ke_id FROM expression_refs "
            "WHERE term_id = ? AND is_operator = 1 ORDER BY ke_id",
            (operator_id,),
        )

    def lookup_lifecycle(self, lifecycle: Lifecycle | str) -> tuple[str, ...]:
        value = lifecycle.value if isinstance(lifecycle, Lifecycle) else lifecycle
        return self._lookup_ids(
            "SELECT DISTINCT id FROM ke_revisions WHERE lifecycle = ? ORDER BY id",
            (value,),
        )

    def lookup_temporal(
        self,
        start: datetime | None,
        end: datetime | None,
    ) -> tuple[str, ...]:
        query_start = _datetime_text(start) if start is not None else None
        query_end = _datetime_text(end) if end is not None else None
        if query_start is not None and query_end is not None and query_end < query_start:
            raise IndexQueryError("temporal query end precedes start")
        return self._lookup_ids(
            "SELECT DISTINCT id FROM ke_revisions "
            "WHERE (? IS NULL OR temporal_start IS NULL OR temporal_start <= ?) "
            "AND (? IS NULL OR temporal_end IS NULL OR temporal_end >= ?) "
            "ORDER BY id",
            (query_end, query_end, query_start, query_start),
        )

    def lookup_aggregate_membership(self, member_ref: str) -> tuple[str, ...]:
        return self._lookup_ids(
            "SELECT aggregate_id FROM aggregate_membership "
            "WHERE member_ref = ? ORDER BY aggregate_id",
            (member_ref,),
        )

    def members_of_aggregate(self, aggregate_id: str) -> tuple[str, ...]:
        return self._lookup_ids(
            "SELECT member_ref FROM aggregate_membership "
            "WHERE aggregate_id = ? ORDER BY member_ref",
            (aggregate_id,),
        )

    def _lookup_ids(self, statement: str, parameters: Sequence[object]) -> tuple[str, ...]:
        if not self.db_path.is_file():
            raise IndexQueryError(f"index cache does not exist: {self.db_path}")
        try:
            uri = f"{self.db_path.as_uri()}?mode=ro"
            with sqlite3.connect(uri, uri=True) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                rows = connection.execute(statement, parameters).fetchall()
        except sqlite3.Error as error:
            raise IndexQueryError(f"index lookup failed: {error}") from error
        return tuple(cast(str, row[0]) for row in rows)


def _materialize_inputs(
    exchanges: Iterable[Exchange],
    knowledge_equations: Iterable[KnowledgeEquation],
    aggregates: Iterable[AggregateNode],
) -> tuple[tuple[Exchange, ...], tuple[KnowledgeEquation, ...], tuple[AggregateNode, ...]]:
    try:
        validated_exchanges = tuple(Exchange.model_validate(item) for item in exchanges)
        validated_kes = tuple(
            KnowledgeEquation.model_validate(item) for item in knowledge_equations
        )
        validated_aggregates = tuple(AggregateNode.model_validate(item) for item in aggregates)
    except Exception as error:
        raise IndexBuildError(f"index rebuild input validation failed: {error}") from error
    return (
        tuple(sorted(validated_exchanges, key=lambda item: (item.global_ordinal, item.id))),
        tuple(sorted(validated_kes, key=lambda item: (item.id, item.revision))),
        tuple(sorted(validated_aggregates, key=lambda item: (item.depth, item.id))),
    )


def _validate_source_spans(
    exchanges: tuple[Exchange, ...],
    knowledge_equations: tuple[KnowledgeEquation, ...],
    aggregates: tuple[AggregateNode, ...],
) -> None:
    records: dict[str, Message | ToolEvent] = {}
    for exchange in exchanges:
        for record in (exchange.user, *exchange.events, exchange.assistant):
            previous = records.get(record.id)
            if previous is not None and previous != record:
                raise IndexBuildError(
                    f"index rebuild input validation failed: duplicate record ID {record.id!r}"
                )
            records[record.id] = record
    for ke in knowledge_equations:
        for span in ke.evidence_refs:
            _validate_source_span(span, records, owner=f"KE {ke.id}/{ke.revision}")
    for aggregate in aggregates:
        for span in aggregate.evidence_closure:
            _validate_source_span(span, records, owner=f"aggregate {aggregate.id}")


def _validate_source_span(
    span: MessageSpan,
    records: Mapping[str, Message | ToolEvent],
    *,
    owner: str,
) -> None:
    record = records.get(span.message_id)
    if record is None:
        raise IndexBuildError(
            f"source span for {owner} references missing record {span.message_id}"
        )
    if span.end_char > len(record.content):
        raise IndexBuildError(f"source span for {owner} is outside record {span.message_id}")
    expected = hashlib.sha256(
        record.content[span.start_char : span.end_char].encode("utf-8")
    ).hexdigest()
    if span.text_hash != expected:
        raise IndexBuildError(f"source span hash for {owner} does not match {span.message_id}")


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE exchanges (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            global_ordinal INTEGER NOT NULL CHECK (global_ordinal >= 0),
            record_json TEXT NOT NULL
        );
        CREATE TABLE messages (
            id TEXT PRIMARY KEY,
            exchange_id TEXT NOT NULL REFERENCES exchanges(id) ON DELETE CASCADE,
            record_type TEXT NOT NULL CHECK (record_type IN ('message', 'tool_event')),
            role_or_kind TEXT NOT NULL,
            source_order INTEGER NOT NULL CHECK (source_order >= 0),
            record_json TEXT NOT NULL
        );
        CREATE TABLE ke_logical_ids (
            id TEXT PRIMARY KEY
        );
        CREATE TABLE ke_revisions (
            id TEXT NOT NULL REFERENCES ke_logical_ids(id) ON DELETE CASCADE,
            revision TEXT NOT NULL,
            level TEXT NOT NULL,
            lifecycle TEXT NOT NULL,
            temporal_start TEXT,
            temporal_end TEXT,
            lhs_json TEXT NOT NULL,
            rhs_json TEXT NOT NULL,
            record_json TEXT NOT NULL,
            PRIMARY KEY (id, revision)
        );
        CREATE TABLE expression_refs (
            ke_id TEXT NOT NULL,
            ke_revision TEXT NOT NULL,
            path TEXT NOT NULL,
            kind TEXT NOT NULL,
            term_id TEXT NOT NULL,
            label TEXT NOT NULL,
            is_operator INTEGER NOT NULL CHECK (is_operator IN (0, 1)),
            PRIMARY KEY (ke_id, ke_revision, path),
            FOREIGN KEY (ke_id, ke_revision)
                REFERENCES ke_revisions(id, revision) ON DELETE CASCADE
        );
        CREATE TABLE ontology_bindings (
            ke_id TEXT NOT NULL,
            ke_revision TEXT NOT NULL,
            binding_ordinal INTEGER NOT NULL CHECK (binding_ordinal >= 0),
            status TEXT NOT NULL,
            normalized_surface TEXT NOT NULL,
            document_id TEXT,
            role TEXT,
            record_json TEXT NOT NULL,
            PRIMARY KEY (ke_id, ke_revision, binding_ordinal),
            FOREIGN KEY (ke_id, ke_revision)
                REFERENCES ke_revisions(id, revision) ON DELETE CASCADE
        );
        CREATE TABLE ke_relations (
            ke_id TEXT NOT NULL,
            ke_revision TEXT NOT NULL,
            relation_type TEXT NOT NULL
                CHECK (relation_type IN ('derived_from', 'contradicts', 'supersedes')),
            target_id TEXT NOT NULL REFERENCES ke_logical_ids(id),
            PRIMARY KEY (ke_id, ke_revision, relation_type, target_id),
            FOREIGN KEY (ke_id, ke_revision)
                REFERENCES ke_revisions(id, revision) ON DELETE CASCADE
        );
        CREATE TABLE ke_source_spans (
            ke_id TEXT NOT NULL,
            ke_revision TEXT NOT NULL,
            span_ordinal INTEGER NOT NULL CHECK (span_ordinal >= 0),
            message_id TEXT NOT NULL REFERENCES messages(id),
            start_char INTEGER NOT NULL CHECK (start_char >= 0),
            end_char INTEGER NOT NULL CHECK (end_char > start_char),
            text_hash TEXT NOT NULL,
            PRIMARY KEY (ke_id, ke_revision, span_ordinal),
            FOREIGN KEY (ke_id, ke_revision)
                REFERENCES ke_revisions(id, revision) ON DELETE CASCADE
        );
        CREATE TABLE aggregates (
            id TEXT PRIMARY KEY,
            revision TEXT NOT NULL,
            node_kind TEXT NOT NULL,
            depth INTEGER NOT NULL CHECK (depth >= 0),
            temporal_start TEXT,
            temporal_end TEXT,
            record_json TEXT NOT NULL
        );
        CREATE TABLE aggregate_assertions (
            aggregate_id TEXT NOT NULL REFERENCES aggregates(id) ON DELETE CASCADE,
            assertion_ordinal INTEGER NOT NULL CHECK (assertion_ordinal >= 0),
            ke_id TEXT NOT NULL,
            ke_revision TEXT NOT NULL,
            PRIMARY KEY (aggregate_id, assertion_ordinal),
            FOREIGN KEY (ke_id, ke_revision) REFERENCES ke_revisions(id, revision)
        );
        CREATE TABLE aggregate_source_spans (
            aggregate_id TEXT NOT NULL REFERENCES aggregates(id) ON DELETE CASCADE,
            span_ordinal INTEGER NOT NULL CHECK (span_ordinal >= 0),
            message_id TEXT NOT NULL REFERENCES messages(id),
            start_char INTEGER NOT NULL CHECK (start_char >= 0),
            end_char INTEGER NOT NULL CHECK (end_char > start_char),
            text_hash TEXT NOT NULL,
            PRIMARY KEY (aggregate_id, span_ordinal)
        );
        CREATE TABLE indexed_objects (
            id TEXT PRIMARY KEY,
            object_kind TEXT NOT NULL CHECK (object_kind IN ('exchange', 'ke', 'aggregate'))
        );
        CREATE TABLE aggregate_membership (
            aggregate_id TEXT NOT NULL REFERENCES aggregates(id) ON DELETE CASCADE,
            member_ref TEXT NOT NULL REFERENCES indexed_objects(id),
            member_ordinal INTEGER NOT NULL CHECK (member_ordinal >= 0),
            PRIMARY KEY (aggregate_id, member_ref)
        );
        CREATE TABLE aggregate_relations (
            aggregate_id TEXT NOT NULL REFERENCES aggregates(id) ON DELETE CASCADE,
            target_ref TEXT NOT NULL REFERENCES indexed_objects(id),
            PRIMARY KEY (aggregate_id, target_ref)
        );
        """
    )


def _insert_all(
    connection: sqlite3.Connection,
    exchanges: tuple[Exchange, ...],
    knowledge_equations: tuple[KnowledgeEquation, ...],
    aggregates: tuple[AggregateNode, ...],
) -> None:
    _insert_exchanges(connection, exchanges)
    logical_ids = tuple(sorted({ke.id for ke in knowledge_equations}))
    connection.executemany(
        "INSERT INTO ke_logical_ids (id) VALUES (?)", ((item,) for item in logical_ids)
    )
    _insert_kes(connection, knowledge_equations)
    _insert_aggregates(connection, aggregates)

    indexed_objects = (
        *((exchange.id, "exchange") for exchange in exchanges),
        *((ke_id, "ke") for ke_id in logical_ids),
        *((aggregate.id, "aggregate") for aggregate in aggregates),
    )
    connection.executemany(
        "INSERT INTO indexed_objects (id, object_kind) VALUES (?, ?)",
        sorted(indexed_objects),
    )
    _insert_aggregate_links(connection, aggregates)


def _insert_exchanges(connection: sqlite3.Connection, exchanges: tuple[Exchange, ...]) -> None:
    for exchange in exchanges:
        connection.execute(
            "INSERT INTO exchanges (id, session_id, global_ordinal, record_json) "
            "VALUES (?, ?, ?, ?)",
            (
                exchange.id,
                exchange.session_id,
                exchange.global_ordinal,
                _json_text(exchange),
            ),
        )
        records: tuple[Message | ToolEvent, ...] = (
            exchange.user,
            *exchange.events,
            exchange.assistant,
        )
        for record in records:
            if isinstance(record, Message):
                record_type = "message"
                role_or_kind = record.role.value
            else:
                record_type = "tool_event"
                role_or_kind = record.kind.value
            connection.execute(
                "INSERT INTO messages "
                "(id, exchange_id, record_type, role_or_kind, source_order, record_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    record.id,
                    exchange.id,
                    record_type,
                    role_or_kind,
                    record.source_order,
                    _json_text(record),
                ),
            )


def _insert_kes(
    connection: sqlite3.Connection,
    knowledge_equations: tuple[KnowledgeEquation, ...],
) -> None:
    for ke in knowledge_equations:
        temporal_start, temporal_end = _effective_temporal_bounds(ke.temporal)
        connection.execute(
            "INSERT INTO ke_revisions "
            "(id, revision, level, lifecycle, temporal_start, temporal_end, "
            "lhs_json, rhs_json, record_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ke.id,
                ke.revision,
                ke.level.value,
                ke.lifecycle.value,
                temporal_start,
                temporal_end,
                _json_text(ke.lhs),
                _json_text(ke.rhs),
                _json_text(ke),
            ),
        )
        for path, expression in (
            *_expression_refs(ke.lhs, path="lhs"),
            *_expression_refs(ke.rhs, path="rhs"),
        ):
            connection.execute(
                "INSERT INTO expression_refs "
                "(ke_id, ke_revision, path, kind, term_id, label, is_operator) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    ke.id,
                    ke.revision,
                    path,
                    expression.kind,
                    expression.term_id,
                    expression.label,
                    int(isinstance(expression, OperatorRef)),
                ),
            )
        for ordinal, binding in enumerate(ke.ontology_bindings):
            connection.execute(
                "INSERT INTO ontology_bindings "
                "(ke_id, ke_revision, binding_ordinal, status, normalized_surface, "
                "document_id, role, record_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ke.id,
                    ke.revision,
                    ordinal,
                    binding.status.value,
                    binding.normalized_surface,
                    binding.document_id,
                    binding.role.value if binding.role is not None else None,
                    _json_text(binding),
                ),
            )
        for relation_type, targets in (
            ("derived_from", ke.derived_from),
            ("contradicts", ke.contradicts),
            ("supersedes", ke.supersedes),
        ):
            for target_id in targets:
                connection.execute(
                    "INSERT INTO ke_relations "
                    "(ke_id, ke_revision, relation_type, target_id) VALUES (?, ?, ?, ?)",
                    (ke.id, ke.revision, relation_type, target_id),
                )
        for ordinal, span in enumerate(ke.evidence_refs):
            connection.execute(
                "INSERT INTO ke_source_spans "
                "(ke_id, ke_revision, span_ordinal, message_id, start_char, end_char, text_hash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    ke.id,
                    ke.revision,
                    ordinal,
                    span.message_id,
                    span.start_char,
                    span.end_char,
                    span.text_hash,
                ),
            )


def _insert_aggregates(
    connection: sqlite3.Connection,
    aggregates: tuple[AggregateNode, ...],
) -> None:
    for aggregate in aggregates:
        temporal_start, temporal_end = _effective_temporal_bounds(aggregate.temporal_extent)
        connection.execute(
            "INSERT INTO aggregates "
            "(id, revision, node_kind, depth, temporal_start, temporal_end, record_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                aggregate.id,
                aggregate.revision,
                aggregate.node_kind.value,
                aggregate.depth,
                temporal_start,
                temporal_end,
                _json_text(aggregate),
            ),
        )
        for ordinal, assertion in enumerate(aggregate.assertions):
            connection.execute(
                "INSERT INTO aggregate_assertions "
                "(aggregate_id, assertion_ordinal, ke_id, ke_revision) VALUES (?, ?, ?, ?)",
                (aggregate.id, ordinal, assertion.id, assertion.revision),
            )
        for ordinal, span in enumerate(aggregate.evidence_closure):
            connection.execute(
                "INSERT INTO aggregate_source_spans "
                "(aggregate_id, span_ordinal, message_id, start_char, end_char, text_hash) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    aggregate.id,
                    ordinal,
                    span.message_id,
                    span.start_char,
                    span.end_char,
                    span.text_hash,
                ),
            )


def _insert_aggregate_links(
    connection: sqlite3.Connection,
    aggregates: tuple[AggregateNode, ...],
) -> None:
    for aggregate in aggregates:
        for ordinal, member_ref in enumerate(aggregate.member_refs):
            connection.execute(
                "INSERT INTO aggregate_membership "
                "(aggregate_id, member_ref, member_ordinal) VALUES (?, ?, ?)",
                (aggregate.id, member_ref, ordinal),
            )
        for target_ref in aggregate.derived_from:
            connection.execute(
                "INSERT INTO aggregate_relations (aggregate_id, target_ref) VALUES (?, ?)",
                (aggregate.id, target_ref),
            )


def _create_lookup_indexes(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE INDEX messages_exchange_idx ON messages(exchange_id, source_order, id);
        CREATE INDEX expression_term_idx ON expression_refs(term_id, ke_id);
        CREATE INDEX expression_operator_idx
            ON expression_refs(term_id, ke_id) WHERE is_operator = 1;
        CREATE INDEX ontology_document_idx ON ontology_bindings(document_id, ke_id);
        CREATE INDEX ontology_unresolved_idx
            ON ontology_bindings(normalized_surface, ke_id) WHERE status <> 'resolved';
        CREATE INDEX ke_lifecycle_idx ON ke_revisions(lifecycle, id);
        CREATE INDEX ke_temporal_start_idx ON ke_revisions(temporal_start, id);
        CREATE INDEX ke_temporal_end_idx ON ke_revisions(temporal_end, id);
        CREATE INDEX ke_relation_target_idx ON ke_relations(target_id, ke_id);
        CREATE INDEX ke_span_message_idx ON ke_source_spans(message_id, ke_id);
        CREATE INDEX aggregate_span_message_idx
            ON aggregate_source_spans(message_id, aggregate_id);
        CREATE INDEX aggregate_member_idx
            ON aggregate_membership(member_ref, aggregate_id);
        """
    )


def _expression_refs(
    expression: Expression,
    *,
    path: str,
) -> Iterator[tuple[str, ConceptRef | IndividualRef | OperatorRef]]:
    if isinstance(expression, ConceptRef | IndividualRef | OperatorRef):
        yield path, expression
        return
    if isinstance(expression, AssertionRef):
        return
    yield f"{path}.operator", expression.operator
    for ordinal, argument in enumerate(expression.arguments):
        yield from _expression_refs(argument, path=f"{path}.arguments[{ordinal}]")


def _effective_temporal_bounds(temporal: object) -> tuple[str | None, str | None]:
    valid_from = cast(datetime | None, getattr(temporal, "valid_from"))
    valid_to = cast(datetime | None, getattr(temporal, "valid_to"))
    event_time = cast(datetime | None, getattr(temporal, "event_time"))
    if valid_from is not None or valid_to is not None:
        return (
            _datetime_text(valid_from) if valid_from is not None else None,
            _datetime_text(valid_to) if valid_to is not None else None,
        )
    if event_time is not None:
        point = _datetime_text(event_time)
        return point, point
    return None, None


def _datetime_text(value: datetime) -> str:
    if value.utcoffset() is None:
        raise IndexQueryError("temporal bounds must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _json_text(value: BaseModel) -> str:
    return canonical_json(value).decode("utf-8")


def _run_integrity_check(connection: sqlite3.Connection) -> tuple[str, ...]:
    rows = connection.execute("PRAGMA integrity_check").fetchall()
    return tuple(cast(str, row[0]) for row in rows)


def _read_stats(
    connection: sqlite3.Connection,
    *,
    integrity_result: Literal["ok"],
) -> IndexStats:
    def count(statement: str) -> int:
        row = connection.execute(statement).fetchone()
        if row is None:
            raise IndexBuildError(f"count query returned no row: {statement}")
        return cast(int, row[0])

    return IndexStats(
        exchange_count=count("SELECT COUNT(*) FROM exchanges"),
        message_count=count("SELECT COUNT(*) FROM messages"),
        tool_event_count=count("SELECT COUNT(*) FROM messages WHERE record_type = 'tool_event'"),
        ke_count=count("SELECT COUNT(*) FROM ke_logical_ids"),
        ke_revision_count=count("SELECT COUNT(*) FROM ke_revisions"),
        ontology_binding_count=count("SELECT COUNT(*) FROM ontology_bindings"),
        expression_ref_count=count("SELECT COUNT(*) FROM expression_refs"),
        operator_ref_count=count("SELECT COUNT(*) FROM expression_refs WHERE is_operator = 1"),
        ke_relation_count=count("SELECT COUNT(*) FROM ke_relations"),
        source_span_count=count(
            "SELECT (SELECT COUNT(*) FROM ke_source_spans) + "
            "(SELECT COUNT(*) FROM aggregate_source_spans)"
        ),
        aggregate_count=count("SELECT COUNT(*) FROM aggregates"),
        aggregate_membership_count=count("SELECT COUNT(*) FROM aggregate_membership"),
        integrity_result=integrity_result,
    )


def _fsync_file(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _build_temporary_database(
    path: Path,
    exchanges: tuple[Exchange, ...],
    knowledge_equations: tuple[KnowledgeEquation, ...],
    aggregates: tuple[AggregateNode, ...],
) -> IndexStats:
    try:
        connection = sqlite3.connect(path)
    except (OSError, sqlite3.Error) as error:
        raise IndexBuildError(f"index rebuild failed: {error}") from error

    try:
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = DELETE")
            connection.execute("PRAGMA synchronous = FULL")
            _create_schema(connection)
            connection.execute("BEGIN IMMEDIATE")
            try:
                _insert_all(connection, exchanges, knowledge_equations, aggregates)
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
            _create_lookup_indexes(connection)

            foreign_key_violations = connection.execute("PRAGMA foreign_key_check").fetchall()
            if foreign_key_violations:
                raise IndexBuildError(
                    f"index rebuild failed foreign-key validation: {foreign_key_violations!r}"
                )
            integrity_result = _run_integrity_check(connection)
            if integrity_result != ("ok",):
                raise IndexBuildError(
                    f"index integrity check did not return exactly 'ok': {integrity_result!r}"
                )
            return _read_stats(connection, integrity_result="ok")
        except IndexBuildError:
            raise
        except (OSError, sqlite3.Error, TypeError, ValueError) as error:
            raise IndexBuildError(f"index rebuild failed: {error}") from error
    finally:
        try:
            _close_connection(connection)
        except (OSError, sqlite3.Error) as error:
            raise IndexBuildError(f"index connection close failed: {error}") from error


def _close_connection(connection: sqlite3.Connection) -> None:
    connection.close()


def _install_cache(temporary: Path, destination: Path) -> None:
    backup = destination.parent / f".{destination.name}.backup-{uuid4().hex}"
    prior_metadata: os.stat_result | None
    try:
        prior_metadata = destination.lstat()
    except FileNotFoundError:
        prior_metadata = None
    if prior_metadata is not None and not stat.S_ISREG(prior_metadata.st_mode):
        raise IndexBuildError(f"prior cache is not a regular file: {destination}")

    had_prior = prior_metadata is not None
    replaced = False
    committed = False
    try:
        _fsync_file(temporary)
        if had_prior:
            _fsync_file(destination)
            os.link(destination, backup, follow_symlinks=False)
            fsync_directory(destination.parent)
        _replace(temporary, destination)
        replaced = True
        fsync_directory(destination.parent)
        committed = True
    except OSError as error:
        if replaced:
            _restore_prior_cache(destination, backup, had_prior=had_prior)
        _cleanup_cache_backup_best_effort(backup)
        raise IndexBuildError(f"cache replace or fsync failed: {error}") from error
    finally:
        _remove_temporary_database(temporary)

    if committed and had_prior:
        try:
            _cleanup_cache_backup(backup)
        except Exception:
            pass


def _restore_prior_cache(destination: Path, backup: Path, *, had_prior: bool) -> None:
    if had_prior:
        try:
            _replace(backup, destination)
        except OSError:
            destination.unlink(missing_ok=True)
            os.link(backup, destination, follow_symlinks=False)
        fsync_directory(destination.parent)
        return
    destination.unlink(missing_ok=True)
    fsync_directory(destination.parent)


def _cleanup_cache_backup(path: Path) -> None:
    path.unlink(missing_ok=True)
    fsync_directory(path.parent)


def _cleanup_cache_backup_best_effort(path: Path) -> None:
    try:
        _cleanup_cache_backup(path)
    except Exception:
        pass


def _remove_temporary_database(path: Path) -> None:
    for candidate in path.parent.glob(f"{path.name}*"):
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass
