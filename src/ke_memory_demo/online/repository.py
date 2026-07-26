from __future__ import annotations

from collections.abc import Generator, Sequence
from contextlib import contextmanager
from datetime import datetime
import hashlib
from pathlib import Path
import sqlite3
from typing import Annotated, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ke_memory_demo.core.ids import content_id
from ke_memory_demo.core.json import JsonObject, JsonValue, canonical_json
from ke_memory_demo.domain import Exchange, KnowledgeEquation, Lifecycle, Message, ToolEvent

from .keol_bridge import KEOLBundle
from .models import AdmissionAssessment, MemoryNamespace


NonEmptyString = Annotated[str, Field(min_length=1)]


class IdempotencyConflict(RuntimeError):
    pass


class MemoryStateConflict(RuntimeError):
    pass


class MemoryNotFound(KeyError):
    pass


class _RepositoryRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class MemoryWrite(_RepositoryRecord):
    equation: KnowledgeEquation
    assessment: AdmissionAssessment
    bundle: KEOLBundle

    @model_validator(mode="after")
    def _validate_projection(self) -> MemoryWrite:
        self.bundle.validate_closed()
        if len(self.bundle.assertions) != 1:
            raise ValueError("an online memory bundle must contain exactly one assertion")
        assertion = self.bundle.assertions[0]
        metadata = assertion.get("metadata")
        if not isinstance(metadata, dict):
            raise ValueError("KEOL assertion metadata must be an object")
        if metadata.get("source_equation_id") != self.equation.id:
            raise ValueError("KEOL assertion does not project the supplied equation")
        if assertion.get("status") != self.equation.lifecycle.value:
            raise ValueError("KEOL assertion lifecycle does not match the equation")
        if self.assessment.extraction_confidence != self.equation.confidence:
            raise ValueError("assessment extraction confidence does not match the equation")
        return self


class AssessedEquation(_RepositoryRecord):
    equation: KnowledgeEquation
    assessment: AdmissionAssessment


class ExistingMemoryRevision(_RepositoryRecord):
    memory_id: NonEmptyString
    equation: KnowledgeEquation


class MemoryLinkWrite(_RepositoryRecord):
    source_memory_id: NonEmptyString
    target_memory_id: NonEmptyString
    relation: NonEmptyString


class TurnWriteReceipt(_RepositoryRecord):
    transaction_id: NonEmptyString
    replayed: bool = False
    memory_ids: tuple[NonEmptyString, ...] = ()


class MemoryLink(_RepositoryRecord):
    relation: NonEmptyString
    target_memory_id: NonEmptyString


class StoredMemory(_RepositoryRecord):
    namespace: MemoryNamespace
    memory_id: NonEmptyString
    assertion_id: NonEmptyString
    equation: KnowledgeEquation
    assessment: AdmissionAssessment
    bundle: KEOLBundle
    current: bool
    tombstoned: bool
    created_at: datetime
    updated_at: datetime
    links: tuple[MemoryLink, ...] = ()


class SQLiteOnlineMemoryRepository:
    def __init__(self, database_path: str | Path) -> None:
        self._database_path = Path(database_path)
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @property
    def database_path(self) -> Path:
        return self._database_path

    def write_turn(
        self,
        *,
        namespace: MemoryNamespace,
        conversation_id: str,
        idempotency_key: str,
        exchange: Exchange,
        memories: Sequence[MemoryWrite],
        recorded_at: datetime,
        extractions: Sequence[AssessedEquation] = (),
        transitions: Sequence[ExistingMemoryRevision] = (),
        links: Sequence[MemoryLinkWrite] = (),
    ) -> TurnWriteReceipt:
        _require_non_empty(conversation_id, "conversation_id")
        _require_non_empty(idempotency_key, "idempotency_key")
        _require_aware(recorded_at)
        for memory in memories:
            memory.bundle.validate_closed()

        namespace_json = cast(JsonObject, namespace.model_dump(mode="json"))
        payload: JsonObject = {
            "namespace": namespace_json,
            "conversation_id": conversation_id,
            "exchange": cast(JsonObject, exchange.model_dump(mode="json")),
            "memories": [
                cast(JsonValue, memory.model_dump(mode="json")) for memory in memories
            ],
            "extractions": [
                cast(JsonValue, extraction.model_dump(mode="json"))
                for extraction in extractions
            ],
            "transitions": [
                cast(JsonValue, transition.model_dump(mode="json"))
                for transition in transitions
            ],
            "links": [cast(JsonValue, link.model_dump(mode="json")) for link in links],
        }
        payload_hash = _digest(payload)
        namespace_id = _namespace_id(namespace)
        transaction_id = content_id(
            "transaction",
            {
                "namespace_id": namespace_id,
                "idempotency_key": idempotency_key,
                "payload_hash": payload_hash,
            },
        )

        with self._connect() as connection, _transaction(connection):
            self._ensure_namespace(connection, namespace_id, namespace)
            existing = connection.execute(
                """
                SELECT payload_hash, receipt_json
                FROM transactions
                WHERE namespace_id = ? AND idempotency_key = ?
                """,
                (namespace_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                if cast(str, existing["payload_hash"]) != payload_hash:
                    raise IdempotencyConflict(
                        "idempotency key was already used with a different payload"
                    )
                receipt = TurnWriteReceipt.model_validate_json(
                    cast(str, existing["receipt_json"])
                )
                return receipt.model_copy(update={"replayed": True})

            connection.execute(
                """
                INSERT INTO transactions (
                    transaction_id, namespace_id, operation_type, idempotency_key,
                    payload_hash, receipt_json, created_at
                ) VALUES (?, ?, 'turn_write', ?, ?, '{}', ?)
                """,
                (
                    transaction_id,
                    namespace_id,
                    idempotency_key,
                    payload_hash,
                    recorded_at.isoformat(),
                ),
            )
            connection.execute(
                """
                INSERT INTO turns (
                    namespace_id, exchange_id, transaction_id, conversation_id,
                    session_id, global_ordinal, source_metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    namespace_id,
                    exchange.id,
                    transaction_id,
                    conversation_id,
                    exchange.session_id,
                    exchange.global_ordinal,
                    _json_text(exchange.source_metadata),
                    recorded_at.isoformat(),
                ),
            )
            for record in (exchange.user, *exchange.events, exchange.assistant):
                self._insert_raw_record(connection, namespace_id, exchange.id, record)
            for extraction in extractions:
                connection.execute(
                    """
                    INSERT INTO extracted_equations (
                        namespace_id, exchange_id, transaction_id, equation_id, revision,
                        admission_status, equation_json, assessment_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        namespace_id,
                        exchange.id,
                        transaction_id,
                        extraction.equation.id,
                        extraction.equation.revision,
                        extraction.assessment.status.value,
                        extraction.equation.model_dump_json(),
                        extraction.assessment.model_dump_json(),
                        recorded_at.isoformat(),
                    ),
                )

            memory_ids: list[str] = []
            for memory in memories:
                memory_id = _memory_id(namespace, memory.equation.id)
                if memory_id in memory_ids:
                    raise ValueError(f"duplicate memory in turn write: {memory_id}")
                self._insert_memory_revision(
                    connection,
                    namespace_id=namespace_id,
                    memory_id=memory_id,
                    memory=memory,
                    transaction_id=transaction_id,
                    source_turn_id=exchange.id,
                    recorded_at=recorded_at,
                )
                memory_ids.append(memory_id)

            for transition in transitions:
                stored = self._select_stored(
                    connection,
                    namespace,
                    transition.memory_id,
                    include_deleted=True,
                )
                if stored is None:
                    raise MemoryNotFound(transition.memory_id)
                if not stored.current or stored.tombstoned:
                    raise MemoryStateConflict(
                        "only a current non-tombstoned memory can receive a lifecycle revision"
                    )
                if stored.equation.id != transition.equation.id:
                    raise ValueError("lifecycle transition changed the logical equation ID")
                transitioned = MemoryWrite(
                    equation=transition.equation,
                    assessment=stored.assessment,
                    bundle=_transition_bundle(stored.bundle, transition.equation),
                )
                self._insert_memory_revision(
                    connection,
                    namespace_id=namespace_id,
                    memory_id=transition.memory_id,
                    memory=transitioned,
                    transaction_id=transaction_id,
                    source_turn_id=None,
                    recorded_at=recorded_at,
                )
                is_current = transition.equation.lifecycle not in {
                    Lifecycle.SUPERSEDED,
                    Lifecycle.RETRACTED,
                }
                connection.execute(
                    """
                    UPDATE memory_heads
                    SET is_current = ?, updated_at = ?
                    WHERE namespace_id = ? AND memory_id = ?
                    """,
                    (
                        int(is_current),
                        recorded_at.isoformat(),
                        namespace_id,
                        transition.memory_id,
                    ),
                )

            for link in links:
                connection.execute(
                    """
                    INSERT INTO memory_links (
                        namespace_id, source_memory_id, target_memory_id,
                        relation, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        namespace_id,
                        link.source_memory_id,
                        link.target_memory_id,
                        link.relation,
                        recorded_at.isoformat(),
                    ),
                )

            receipt = TurnWriteReceipt(
                transaction_id=transaction_id,
                replayed=False,
                memory_ids=tuple(memory_ids),
            )
            connection.execute(
                "UPDATE transactions SET receipt_json = ? WHERE transaction_id = ?",
                (receipt.model_dump_json(), transaction_id),
            )
            return receipt

    def correct_memory(
        self,
        *,
        namespace: MemoryNamespace,
        memory_id: str,
        replacement: MemoryWrite,
        recorded_at: datetime,
    ) -> StoredMemory:
        _require_aware(recorded_at)
        namespace_id = _namespace_id(namespace)
        replacement_id = _memory_id(namespace, replacement.equation.id)
        if replacement_id == memory_id:
            raise MemoryStateConflict("a correction must produce a different logical memory")

        operation_payload: JsonObject = {
            "namespace": cast(JsonObject, namespace.model_dump(mode="json")),
            "memory_id": memory_id,
            "replacement": cast(JsonObject, replacement.model_dump(mode="json")),
            "recorded_at": recorded_at.isoformat(),
        }
        transaction_id = content_id("transaction", operation_payload)

        with self._connect() as connection, _transaction(connection):
            self._ensure_namespace(connection, namespace_id, namespace)
            old = self._select_stored(
                connection,
                namespace,
                memory_id,
                include_deleted=True,
            )
            if old is None:
                raise MemoryNotFound(memory_id)
            if not old.current or old.tombstoned:
                raise MemoryStateConflict("only a current non-tombstoned memory can be corrected")

            self._insert_operation(
                connection,
                transaction_id=transaction_id,
                namespace_id=namespace_id,
                operation_type="correction",
                payload_hash=_digest(operation_payload),
                recorded_at=recorded_at,
            )
            superseded_equation = old.equation.transition(Lifecycle.SUPERSEDED)
            superseded = MemoryWrite(
                equation=superseded_equation,
                assessment=old.assessment,
                bundle=_transition_bundle(old.bundle, superseded_equation),
            )
            self._insert_memory_revision(
                connection,
                namespace_id=namespace_id,
                memory_id=memory_id,
                memory=superseded,
                transaction_id=transaction_id,
                source_turn_id=None,
                recorded_at=recorded_at,
            )
            connection.execute(
                """
                UPDATE memory_heads
                SET is_current = 0, updated_at = ?
                WHERE namespace_id = ? AND memory_id = ?
                """,
                (recorded_at.isoformat(), namespace_id, memory_id),
            )

            self._insert_memory_revision(
                connection,
                namespace_id=namespace_id,
                memory_id=replacement_id,
                memory=replacement,
                transaction_id=transaction_id,
                source_turn_id=None,
                recorded_at=recorded_at,
            )
            connection.execute(
                """
                INSERT INTO memory_links (
                    namespace_id, source_memory_id, target_memory_id, relation, created_at
                ) VALUES (?, ?, ?, 'supersedes', ?)
                """,
                (namespace_id, replacement_id, memory_id, recorded_at.isoformat()),
            )

        corrected = self.get_memory(namespace, replacement_id, include_deleted=True)
        if corrected is None:
            raise RuntimeError("committed correction could not be reloaded")
        return corrected

    def tombstone_memory(
        self,
        *,
        namespace: MemoryNamespace,
        memory_id: str,
        recorded_at: datetime,
    ) -> StoredMemory:
        _require_aware(recorded_at)
        namespace_id = _namespace_id(namespace)
        operation_payload: JsonObject = {
            "namespace": cast(JsonObject, namespace.model_dump(mode="json")),
            "memory_id": memory_id,
            "recorded_at": recorded_at.isoformat(),
        }
        transaction_id = content_id("transaction", operation_payload)

        with self._connect() as connection, _transaction(connection):
            stored = self._select_stored(
                connection,
                namespace,
                memory_id,
                include_deleted=True,
            )
            if stored is None:
                raise MemoryNotFound(memory_id)
            if not stored.current or stored.tombstoned:
                raise MemoryStateConflict("only a current non-tombstoned memory can be forgotten")

            self._insert_operation(
                connection,
                transaction_id=transaction_id,
                namespace_id=namespace_id,
                operation_type="tombstone",
                payload_hash=_digest(operation_payload),
                recorded_at=recorded_at,
            )
            retracted_equation = stored.equation.transition(Lifecycle.RETRACTED)
            retracted = MemoryWrite(
                equation=retracted_equation,
                assessment=stored.assessment,
                bundle=_transition_bundle(stored.bundle, retracted_equation),
            )
            self._insert_memory_revision(
                connection,
                namespace_id=namespace_id,
                memory_id=memory_id,
                memory=retracted,
                transaction_id=transaction_id,
                source_turn_id=None,
                recorded_at=recorded_at,
            )
            connection.execute(
                """
                UPDATE memory_heads
                SET is_current = 0, tombstoned = 1, updated_at = ?
                WHERE namespace_id = ? AND memory_id = ?
                """,
                (recorded_at.isoformat(), namespace_id, memory_id),
            )

        deleted = self.get_memory(namespace, memory_id, include_deleted=True)
        if deleted is None:
            raise RuntimeError("committed tombstone could not be reloaded")
        return deleted

    def get_memory(
        self,
        namespace: MemoryNamespace,
        memory_id: str,
        *,
        include_deleted: bool = False,
    ) -> StoredMemory | None:
        with self._connect() as connection:
            return self._select_stored(
                connection,
                namespace,
                memory_id,
                include_deleted=include_deleted,
            )

    def memory_id_for(self, namespace: MemoryNamespace, equation_id: str) -> str:
        return _memory_id(namespace, equation_id)

    def get_turn_receipt(
        self,
        namespace: MemoryNamespace,
        idempotency_key: str,
    ) -> TurnWriteReceipt | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT receipt_json
                FROM transactions
                WHERE namespace_id = ? AND idempotency_key = ?
                """,
                (_namespace_id(namespace), idempotency_key),
            ).fetchone()
        if row is None:
            return None
        receipt = TurnWriteReceipt.model_validate_json(cast(str, row["receipt_json"]))
        return receipt.model_copy(update={"replayed": True})

    def get_raw_turn(
        self,
        namespace: MemoryNamespace,
        exchange_id: str,
    ) -> tuple[JsonObject, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    record_id, record_kind, content, content_hash,
                    source_order, source_metadata_json
                FROM raw_records
                WHERE namespace_id = ? AND exchange_id = ?
                ORDER BY source_order, record_id
                """,
                (_namespace_id(namespace), exchange_id),
            ).fetchall()
        return tuple(
            {
                "record_id": cast(str, row["record_id"]),
                "record_kind": cast(str, row["record_kind"]),
                "content": cast(str, row["content"]),
                "content_hash": cast(str, row["content_hash"]),
                "source_order": cast(int, row["source_order"]),
                "source_metadata": _parse_json_object(
                    cast(str, row["source_metadata_json"])
                ),
            }
            for row in rows
        )

    def get_extractions(
        self,
        namespace: MemoryNamespace,
        exchange_id: str,
    ) -> tuple[AssessedEquation, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT equation_json, assessment_json
                FROM extracted_equations
                WHERE namespace_id = ? AND exchange_id = ?
                ORDER BY rowid
                """,
                (_namespace_id(namespace), exchange_id),
            ).fetchall()
        return tuple(
            AssessedEquation(
                equation=KnowledgeEquation.model_validate_json(
                    cast(str, row["equation_json"])
                ),
                assessment=AdmissionAssessment.model_validate_json(
                    cast(str, row["assessment_json"])
                ),
            )
            for row in rows
        )

    def list_current(self, namespace: MemoryNamespace) -> tuple[StoredMemory, ...]:
        namespace_id = _namespace_id(namespace)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT memory_id
                FROM memory_heads
                WHERE namespace_id = ? AND is_current = 1 AND tombstoned = 0
                ORDER BY created_at, memory_id
                """,
                (namespace_id,),
            ).fetchall()
            memories = [
                self._select_stored(
                    connection,
                    namespace,
                    cast(str, row["memory_id"]),
                    include_deleted=False,
                )
                for row in rows
            ]
        return tuple(memory for memory in memories if memory is not None)

    def list_revisions(
        self,
        namespace: MemoryNamespace,
        memory_id: str,
    ) -> tuple[StoredMemory, ...]:
        namespace_id = _namespace_id(namespace)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    r.*, h.assertion_id, h.is_current, h.tombstoned,
                    h.created_at AS head_created_at, h.updated_at AS head_updated_at
                FROM memory_revisions AS r
                JOIN memory_heads AS h
                  ON h.namespace_id = r.namespace_id AND h.memory_id = r.memory_id
                WHERE r.namespace_id = ? AND r.memory_id = ?
                ORDER BY r.created_at, r.revision
                """,
                (namespace_id, memory_id),
            ).fetchall()
            return tuple(
                self._stored_from_row(connection, namespace, row) for row in rows
            )

    def get_evidence(
        self,
        namespace: MemoryNamespace,
        memory_id: str,
    ) -> tuple[JsonObject, ...]:
        namespace_id = _namespace_id(namespace)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT e.evidence_json
                FROM memory_heads AS h
                JOIN memory_evidence AS e
                  ON e.namespace_id = h.namespace_id
                 AND e.memory_id = h.memory_id
                 AND e.revision = h.current_revision
                WHERE h.namespace_id = ? AND h.memory_id = ?
                ORDER BY e.evidence_id
                """,
                (namespace_id, memory_id),
            ).fetchall()
        return tuple(_parse_json_object(cast(str, row["evidence_json"])) for row in rows)

    def pragmas(self) -> dict[str, str | int]:
        with self._connect() as connection:
            journal_mode = cast(str, connection.execute("PRAGMA journal_mode").fetchone()[0])
            foreign_keys = cast(int, connection.execute("PRAGMA foreign_keys").fetchone()[0])
        return {"journal_mode": journal_mode.casefold(), "foreign_keys": foreign_keys}

    def integrity_check(self) -> tuple[str, ...]:
        with self._connect() as connection:
            rows = connection.execute("PRAGMA integrity_check").fetchall()
        return tuple(cast(str, row[0]) for row in rows)

    def foreign_key_check(self) -> tuple[tuple[object, ...], ...]:
        with self._connect() as connection:
            rows = connection.execute("PRAGMA foreign_key_check").fetchall()
        return tuple(tuple(row) for row in rows)

    def row_counts(self) -> dict[str, int]:
        tables = (
            "transactions",
            "turns",
            "raw_records",
            "extracted_equations",
            "memory_heads",
            "memory_revisions",
            "memory_evidence",
            "memory_links",
        )
        with self._connect() as connection:
            return {
                table: cast(
                    int,
                    connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0],
                )
                for table in tables
            }

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS namespaces (
                    namespace_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    UNIQUE (tenant_id, user_id, agent_id)
                );

                CREATE TABLE IF NOT EXISTS transactions (
                    transaction_id TEXT PRIMARY KEY,
                    namespace_id TEXT NOT NULL REFERENCES namespaces(namespace_id),
                    operation_type TEXT NOT NULL,
                    idempotency_key TEXT,
                    payload_hash TEXT NOT NULL,
                    receipt_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS ux_transactions_idempotency
                ON transactions(namespace_id, idempotency_key)
                WHERE idempotency_key IS NOT NULL;

                CREATE TABLE IF NOT EXISTS turns (
                    namespace_id TEXT NOT NULL REFERENCES namespaces(namespace_id),
                    exchange_id TEXT NOT NULL,
                    transaction_id TEXT NOT NULL REFERENCES transactions(transaction_id),
                    conversation_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    global_ordinal INTEGER NOT NULL CHECK (global_ordinal >= 0),
                    source_metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (namespace_id, exchange_id)
                );

                CREATE TABLE IF NOT EXISTS raw_records (
                    namespace_id TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    exchange_id TEXT NOT NULL,
                    record_kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    source_order INTEGER NOT NULL CHECK (source_order >= 0),
                    source_metadata_json TEXT NOT NULL,
                    PRIMARY KEY (namespace_id, record_id),
                    FOREIGN KEY (namespace_id, exchange_id)
                        REFERENCES turns(namespace_id, exchange_id)
                );

                CREATE TABLE IF NOT EXISTS extracted_equations (
                    namespace_id TEXT NOT NULL,
                    exchange_id TEXT NOT NULL,
                    transaction_id TEXT NOT NULL REFERENCES transactions(transaction_id),
                    equation_id TEXT NOT NULL,
                    revision TEXT NOT NULL,
                    admission_status TEXT NOT NULL,
                    equation_json TEXT NOT NULL,
                    assessment_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (namespace_id, exchange_id, revision),
                    FOREIGN KEY (namespace_id, exchange_id)
                        REFERENCES turns(namespace_id, exchange_id)
                );

                CREATE TABLE IF NOT EXISTS memory_heads (
                    namespace_id TEXT NOT NULL REFERENCES namespaces(namespace_id),
                    memory_id TEXT NOT NULL,
                    current_revision TEXT NOT NULL,
                    assertion_id TEXT NOT NULL,
                    is_current INTEGER NOT NULL CHECK (is_current IN (0, 1)),
                    tombstoned INTEGER NOT NULL CHECK (tombstoned IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (namespace_id, memory_id)
                );

                CREATE TABLE IF NOT EXISTS memory_revisions (
                    namespace_id TEXT NOT NULL,
                    memory_id TEXT NOT NULL,
                    revision TEXT NOT NULL,
                    transaction_id TEXT NOT NULL REFERENCES transactions(transaction_id),
                    source_turn_id TEXT,
                    lifecycle TEXT NOT NULL,
                    memory_kind TEXT NOT NULL,
                    source_status TEXT NOT NULL,
                    admission_status TEXT NOT NULL,
                    extraction_confidence REAL NOT NULL,
                    epistemic_trust REAL NOT NULL,
                    memory_utility REAL NOT NULL,
                    equation_json TEXT NOT NULL,
                    assessment_json TEXT NOT NULL,
                    bundle_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (namespace_id, memory_id, revision),
                    FOREIGN KEY (namespace_id, memory_id)
                        REFERENCES memory_heads(namespace_id, memory_id),
                    FOREIGN KEY (namespace_id, source_turn_id)
                        REFERENCES turns(namespace_id, exchange_id)
                );

                CREATE TABLE IF NOT EXISTS memory_evidence (
                    namespace_id TEXT NOT NULL,
                    memory_id TEXT NOT NULL,
                    revision TEXT NOT NULL,
                    evidence_id TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    PRIMARY KEY (namespace_id, memory_id, revision, evidence_id),
                    FOREIGN KEY (namespace_id, memory_id, revision)
                        REFERENCES memory_revisions(namespace_id, memory_id, revision)
                );

                CREATE TABLE IF NOT EXISTS memory_links (
                    namespace_id TEXT NOT NULL,
                    source_memory_id TEXT NOT NULL,
                    target_memory_id TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (
                        namespace_id, source_memory_id, target_memory_id, relation
                    ),
                    FOREIGN KEY (namespace_id, source_memory_id)
                        REFERENCES memory_heads(namespace_id, memory_id),
                    FOREIGN KEY (namespace_id, target_memory_id)
                        REFERENCES memory_heads(namespace_id, memory_id)
                );

                CREATE INDEX IF NOT EXISTS ix_memory_heads_current
                ON memory_heads(namespace_id, is_current, tombstoned);

                CREATE INDEX IF NOT EXISTS ix_memory_revisions_projection
                ON memory_revisions(
                    namespace_id, memory_kind, lifecycle, source_status, created_at
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    @staticmethod
    def _ensure_namespace(
        connection: sqlite3.Connection,
        namespace_id: str,
        namespace: MemoryNamespace,
    ) -> None:
        connection.execute(
            """
            INSERT OR IGNORE INTO namespaces (
                namespace_id, tenant_id, user_id, agent_id
            ) VALUES (?, ?, ?, ?)
            """,
            (
                namespace_id,
                namespace.tenant_id,
                namespace.user_id,
                namespace.agent_id,
            ),
        )

    @staticmethod
    def _insert_raw_record(
        connection: sqlite3.Connection,
        namespace_id: str,
        exchange_id: str,
        record: Message | ToolEvent,
    ) -> None:
        if isinstance(record, Message):
            record_kind = record.role.value
        else:
            record_kind = record.kind.value
        connection.execute(
            """
            INSERT INTO raw_records (
                namespace_id, record_id, exchange_id, record_kind, content,
                content_hash, source_order, source_metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                namespace_id,
                record.id,
                exchange_id,
                record_kind,
                record.content,
                record.content_hash,
                record.source_order,
                _json_text(record.source_metadata),
            ),
        )

    @staticmethod
    def _insert_operation(
        connection: sqlite3.Connection,
        *,
        transaction_id: str,
        namespace_id: str,
        operation_type: str,
        payload_hash: str,
        recorded_at: datetime,
    ) -> None:
        connection.execute(
            """
            INSERT INTO transactions (
                transaction_id, namespace_id, operation_type, idempotency_key,
                payload_hash, receipt_json, created_at
            ) VALUES (?, ?, ?, NULL, ?, '{}', ?)
            """,
            (
                transaction_id,
                namespace_id,
                operation_type,
                payload_hash,
                recorded_at.isoformat(),
            ),
        )

    @staticmethod
    def _insert_memory_revision(
        connection: sqlite3.Connection,
        *,
        namespace_id: str,
        memory_id: str,
        memory: MemoryWrite,
        transaction_id: str,
        source_turn_id: str | None,
        recorded_at: datetime,
    ) -> None:
        assertion = memory.bundle.assertions[0]
        assertion_id = assertion.get("id")
        if not isinstance(assertion_id, str) or not assertion_id:
            raise ValueError("KEOL assertion ID must be a non-empty string")
        timestamp = recorded_at.isoformat()
        connection.execute(
            """
            INSERT OR IGNORE INTO memory_heads (
                namespace_id, memory_id, current_revision, assertion_id,
                is_current, tombstoned, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 1, 0, ?, ?)
            """,
            (
                namespace_id,
                memory_id,
                memory.equation.revision,
                assertion_id,
                timestamp,
                timestamp,
            ),
        )
        connection.execute(
            """
            INSERT INTO memory_revisions (
                namespace_id, memory_id, revision, transaction_id, source_turn_id,
                lifecycle, memory_kind, source_status, admission_status,
                extraction_confidence, epistemic_trust, memory_utility,
                equation_json, assessment_json, bundle_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                namespace_id,
                memory_id,
                memory.equation.revision,
                transaction_id,
                source_turn_id,
                memory.equation.lifecycle.value,
                memory.assessment.memory_kind.value,
                memory.assessment.source_status.value,
                memory.assessment.status.value,
                memory.assessment.extraction_confidence,
                memory.assessment.epistemic_trust,
                memory.assessment.memory_utility,
                memory.equation.model_dump_json(),
                memory.assessment.model_dump_json(),
                memory.bundle.model_dump_json(),
                timestamp,
            ),
        )
        connection.execute(
            """
            UPDATE memory_heads
            SET current_revision = ?, assertion_id = ?, updated_at = ?
            WHERE namespace_id = ? AND memory_id = ?
            """,
            (
                memory.equation.revision,
                assertion_id,
                timestamp,
                namespace_id,
                memory_id,
            ),
        )
        for evidence in memory.bundle.evidence:
            evidence_id = evidence.get("id")
            if not isinstance(evidence_id, str) or not evidence_id:
                raise ValueError("KEOL evidence ID must be a non-empty string")
            connection.execute(
                """
                INSERT INTO memory_evidence (
                    namespace_id, memory_id, revision, evidence_id, evidence_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    namespace_id,
                    memory_id,
                    memory.equation.revision,
                    evidence_id,
                    _json_text(evidence),
                ),
            )

    def _select_stored(
        self,
        connection: sqlite3.Connection,
        namespace: MemoryNamespace,
        memory_id: str,
        *,
        include_deleted: bool,
    ) -> StoredMemory | None:
        namespace_id = _namespace_id(namespace)
        visibility = "" if include_deleted else "AND h.is_current = 1 AND h.tombstoned = 0"
        row = connection.execute(
            f"""
            SELECT
                r.*, h.assertion_id, h.is_current, h.tombstoned,
                h.created_at AS head_created_at, h.updated_at AS head_updated_at
            FROM memory_heads AS h
            JOIN memory_revisions AS r
              ON r.namespace_id = h.namespace_id
             AND r.memory_id = h.memory_id
             AND r.revision = h.current_revision
            WHERE h.namespace_id = ? AND h.memory_id = ? {visibility}
            """,
            (namespace_id, memory_id),
        ).fetchone()
        if row is None:
            return None
        return self._stored_from_row(connection, namespace, row)

    @staticmethod
    def _stored_from_row(
        connection: sqlite3.Connection,
        namespace: MemoryNamespace,
        row: sqlite3.Row,
    ) -> StoredMemory:
        namespace_id = _namespace_id(namespace)
        memory_id = cast(str, row["memory_id"])
        link_rows = connection.execute(
            """
            SELECT relation, target_memory_id
            FROM memory_links
            WHERE namespace_id = ? AND source_memory_id = ?
            ORDER BY relation, target_memory_id
            """,
            (namespace_id, memory_id),
        ).fetchall()
        return StoredMemory(
            namespace=namespace,
            memory_id=memory_id,
            assertion_id=cast(str, row["assertion_id"]),
            equation=KnowledgeEquation.model_validate_json(cast(str, row["equation_json"])),
            assessment=AdmissionAssessment.model_validate_json(
                cast(str, row["assessment_json"])
            ),
            bundle=KEOLBundle.model_validate_json(cast(str, row["bundle_json"])),
            current=bool(row["is_current"]),
            tombstoned=bool(row["tombstoned"]),
            created_at=datetime.fromisoformat(cast(str, row["head_created_at"])),
            updated_at=datetime.fromisoformat(cast(str, row["head_updated_at"])),
            links=tuple(
                MemoryLink(
                    relation=cast(str, link["relation"]),
                    target_memory_id=cast(str, link["target_memory_id"]),
                )
                for link in link_rows
            ),
        )


@contextmanager
def _transaction(connection: sqlite3.Connection) -> Generator[None]:
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        connection.rollback()
        raise
    else:
        connection.commit()


def _transition_bundle(bundle: KEOLBundle, equation: KnowledgeEquation) -> KEOLBundle:
    assertion = dict(bundle.assertions[0])
    metadata_value = assertion.get("metadata")
    if not isinstance(metadata_value, dict):
        raise ValueError("KEOL assertion metadata must be an object")
    metadata = dict(metadata_value)
    metadata["source_equation_revision"] = equation.revision
    assertion["status"] = equation.lifecycle.value
    assertion["metadata"] = metadata
    assertion.pop("hash", None)
    assertion["hash"] = _digest(assertion)
    transitioned = bundle.model_copy(update={"assertions": (assertion,)})
    transitioned.validate_closed()
    return transitioned


def _namespace_id(namespace: MemoryNamespace) -> str:
    return content_id("namespace", cast(JsonObject, namespace.model_dump(mode="json")))


def _memory_id(namespace: MemoryNamespace, equation_id: str) -> str:
    return content_id(
        "memory",
        {
            "namespace": cast(JsonObject, namespace.model_dump(mode="json")),
            "source_equation_id": equation_id,
        },
    )


def _json_text(value: JsonValue) -> str:
    return canonical_json(value).decode("utf-8")


def _digest(value: JsonObject) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _parse_json_object(value: str) -> JsonObject:
    import json

    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("stored JSON value must be an object")
    return cast(JsonObject, parsed)


def _require_non_empty(value: str, label: str) -> None:
    if not value.strip():
        raise ValueError(f"{label} must not be blank")


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("recorded_at must be timezone-aware")
