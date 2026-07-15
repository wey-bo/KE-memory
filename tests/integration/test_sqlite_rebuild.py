from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
import hashlib
import os
from pathlib import Path
import sqlite3

import pytest

from ke_memory_demo.domain import (
    AggregateNode,
    AggregateNodeKind,
    ConceptRef,
    Exchange,
    IndividualRef,
    KnowledgeEquation,
    KnowledgeLevel,
    Lifecycle,
    Message,
    MessageRole,
    MessageSpan,
    Modality,
    OntologyBinding,
    OntologyBindingStatus,
    OntologyRole,
    OperatorApplication,
    OperatorRef,
    Polarity,
    Speaker,
    TemporalMetadata,
    ToolEvent,
    ToolEventKind,
)
from ke_memory_demo.storage import (
    ArtifactStore,
    IndexBuildError,
    IndexQueryError,
    IndexStats,
    MemoryIndex,
)


JAN_1 = datetime(2026, 1, 1, tzinfo=UTC)
JAN_2 = datetime(2026, 1, 2, tzinfo=UTC)
JAN_3 = datetime(2026, 1, 3, tzinfo=UTC)
JAN_4 = datetime(2026, 1, 4, tzinfo=UTC)
JAN_5 = datetime(2026, 1, 5, tzinfo=UTC)
JAN_6 = datetime(2026, 1, 6, tzinfo=UTC)
JAN_10 = datetime(2026, 1, 10, tzinfo=UTC)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _span(message_id: str = "message-user-1", text: str = "memory") -> MessageSpan:
    return MessageSpan(
        message_id=message_id,
        start_char=0,
        end_char=len(text),
        text_hash=_sha256(text),
    )


def _exchanges() -> tuple[Exchange, ...]:
    first = Exchange(
        id="exchange-1",
        session_id="session-1",
        user=Message(
            id="message-user-1",
            role=MessageRole.USER,
            content="memory about tea",
            source_order=0,
        ),
        events=(
            ToolEvent(
                id="tool-call-1",
                kind=ToolEventKind.TOOL_CALL,
                content='{"name":"lookup"}',
                source_order=1,
            ),
            ToolEvent(
                id="tool-result-1",
                kind=ToolEventKind.TOOL_RESULT,
                content='{"found":true}',
                source_order=2,
            ),
        ),
        assistant=Message(
            id="message-assistant-1",
            role=MessageRole.ASSISTANT,
            content="tea noted",
            source_order=3,
        ),
        global_ordinal=0,
    )
    second = Exchange(
        id="exchange-2",
        session_id="session-1",
        user=Message(
            id="message-user-2",
            role=MessageRole.USER,
            content="another memory",
            source_order=4,
        ),
        assistant=Message(
            id="message-assistant-2",
            role=MessageRole.ASSISTANT,
            content="understood",
            source_order=5,
        ),
        global_ordinal=1,
    )
    return (first, second)


def _simple_ke(
    name: str,
    *,
    temporal: TemporalMetadata | None = None,
    lifecycle: Lifecycle = Lifecycle.ACTIVE,
    evidence: MessageSpan | None = None,
) -> KnowledgeEquation:
    return KnowledgeEquation.create(
        level=KnowledgeLevel.TURN,
        lhs=IndividualRef(term_id=f"person:{name}", label=name),
        rhs=ConceptRef(term_id=f"concept:{name}", label=name),
        gloss=f"{name} memory",
        modality=Modality.FACT,
        polarity=Polarity.POSITIVE,
        lifecycle=lifecycle,
        speaker=Speaker.USER,
        temporal=temporal,
        evidence_refs=(evidence or _span(),),
        produced_in_run_id="run-1",
        produced_in_stage="turn-ke-extracted",
        confidence=0.8,
    )


def _knowledge_equations() -> tuple[KnowledgeEquation, ...]:
    base = _simple_ke("base", temporal=TemporalMetadata(valid_to=JAN_1))
    point = _simple_ke(
        "point",
        temporal=TemporalMetadata(event_time=JAN_5),
        lifecycle=Lifecycle.CONTRADICTED,
    )
    nested = OperatorApplication(
        operator=OperatorRef(term_id="op:believes", label="believes"),
        arguments=(
            OperatorApplication(
                operator=OperatorRef(term_id="op:likes", label="likes"),
                arguments=(IndividualRef(term_id="person:user", label="user"),),
            ),
        ),
    )
    derived = KnowledgeEquation.create(
        level=KnowledgeLevel.SESSION,
        lhs=nested,
        rhs=ConceptRef(term_id="drink:tea", label="tea"),
        gloss="The user likes tea.",
        modality=Modality.PREFERENCE,
        polarity=Polarity.POSITIVE,
        lifecycle=Lifecycle.ACTIVE,
        speaker=Speaker.DERIVED,
        temporal=TemporalMetadata(valid_from=JAN_2, valid_to=JAN_4),
        ontology_bindings=(
            OntologyBinding(
                surface_form="tea",
                normalized_surface="tea",
                status=OntologyBindingStatus.RESOLVED,
                document_id="doc:tea",
                canonical_term="Tea",
                role=OntologyRole.CONCEPT,
            ),
            OntologyBinding(
                surface_form="Mystery",
                normalized_surface="mystery",
                status=OntologyBindingStatus.UNRESOLVED,
            ),
        ),
        evidence_refs=(_span(),),
        derived_from=(base.id,),
        contradicts=(point.id,),
        supersedes=(base.id,),
        produced_in_run_id="run-1",
        produced_in_stage="session-aggregated",
        confidence=0.9,
    )
    revised = derived.transition(Lifecycle.SUPERSEDED)
    future = _simple_ke(
        "future",
        temporal=TemporalMetadata(valid_from=JAN_10),
        lifecycle=Lifecycle.UNCERTAIN,
    )
    unbounded = _simple_ke("unbounded", lifecycle=Lifecycle.RETRACTED)
    return (future, revised, base, unbounded, derived, point)


def _aggregates(kes: tuple[KnowledgeEquation, ...]) -> tuple[AggregateNode, ...]:
    derived = next(
        ke for ke in kes if ke.gloss == "The user likes tea." and ke.lifecycle is Lifecycle.ACTIVE
    )
    first = AggregateNode(
        id="aggregate-a",
        node_kind=AggregateNodeKind.PREFERENCE,
        title="Tea preference",
        summary="The user has a tea preference.",
        assertions=(derived,),
        member_refs=(derived.id, "exchange-1"),
        derived_from=(derived.id,),
        evidence_closure=(_span(),),
        temporal_extent=TemporalMetadata(valid_from=JAN_2, valid_to=JAN_4),
        confidence=0.9,
        revision="a" * 64,
        depth=1,
    )
    second = AggregateNode(
        id="aggregate-b",
        node_kind=AggregateNodeKind.TOPIC,
        title="Preferences",
        summary="Known preferences.",
        member_refs=(derived.id,),
        derived_from=(first.id,),
        confidence=0.8,
        revision="b" * 64,
        depth=2,
    )
    return (second, first)


def _fixture() -> tuple[
    tuple[Exchange, ...],
    tuple[KnowledgeEquation, ...],
    tuple[AggregateNode, ...],
]:
    exchanges = _exchanges()
    kes = _knowledge_equations()
    return exchanges, kes, _aggregates(kes)


def _build_index(path: Path) -> tuple[MemoryIndex, IndexStats]:
    exchanges, kes, aggregates = _fixture()
    index = MemoryIndex(path)
    return index, index.rebuild(exchanges, kes, aggregates)


def test_artifacts_rebuild_an_identical_disposable_cache(tmp_path: Path) -> None:
    exchanges, kes, aggregates = _fixture()
    store = ArtifactStore(tmp_path)
    with store.stage_writer("run-1", "indexed") as writer:
        writer.write("exchanges", exchanges)
        writer.write("knowledge_equations", kes)
        writer.write("aggregates", aggregates)

    canonical_exchanges = tuple(store.read_jsonl("run-1", "indexed", "exchanges", Exchange))
    canonical_kes = tuple(
        store.read_jsonl("run-1", "indexed", "knowledge_equations", KnowledgeEquation)
    )
    canonical_aggregates = tuple(store.read_jsonl("run-1", "indexed", "aggregates", AggregateNode))
    index = MemoryIndex(store.cache_path("run-1"))
    first_stats = index.rebuild(canonical_exchanges, canonical_kes, canonical_aggregates)
    first_bytes = index.db_path.read_bytes()
    first_ids = (
        index.ordered_exchange_ids(),
        index.ordered_ke_ids(),
        index.ordered_aggregate_ids(),
    )

    index.db_path.unlink()
    second_stats = index.rebuild(canonical_exchanges, canonical_kes, canonical_aggregates)

    assert second_stats == first_stats
    assert index.db_path.read_bytes() == first_bytes
    assert (
        index.ordered_exchange_ids(),
        index.ordered_ke_ids(),
        index.ordered_aggregate_ids(),
    ) == first_ids


def test_rebuild_reports_complete_counts_and_integrity(tmp_path: Path) -> None:
    index, stats = _build_index(tmp_path / "memory.sqlite3")

    assert stats == IndexStats(
        exchange_count=2,
        message_count=6,
        tool_event_count=2,
        ke_count=5,
        ke_revision_count=6,
        ontology_binding_count=4,
        expression_ref_count=16,
        operator_ref_count=4,
        ke_relation_count=6,
        source_span_count=7,
        aggregate_count=2,
        aggregate_membership_count=3,
        integrity_result="ok",
    )
    with sqlite3.connect(index.db_path) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        [lhs_json, rhs_json, record_json] = connection.execute(
            "SELECT lhs_json, rhs_json, record_json FROM ke_revisions "
            "WHERE lifecycle = 'active' AND level = 'session'"
        ).fetchone()
        assert '"op:likes"' in lhs_json
        assert '"drink:tea"' in rhs_json
        assert '"revision"' in record_json


def test_ordered_ids_include_all_revisions_but_deduplicate_logical_kes(tmp_path: Path) -> None:
    exchanges, kes, aggregates = _fixture()
    index = MemoryIndex(tmp_path / "memory.sqlite3")
    index.rebuild(reversed(exchanges), reversed(kes), reversed(aggregates))

    assert index.ordered_exchange_ids() == ("exchange-1", "exchange-2")
    assert index.ordered_ke_ids() == tuple(sorted({ke.id for ke in kes}))
    assert index.ordered_aggregate_ids() == ("aggregate-a", "aggregate-b")


def test_symbolic_lookups_are_recursive_deduplicated_and_sorted(tmp_path: Path) -> None:
    _, kes, _ = _fixture()
    derived_id = next(ke.id for ke in kes if ke.gloss == "The user likes tea.")
    base_id = next(ke.id for ke in kes if ke.gloss == "base memory")
    index, _ = _build_index(tmp_path / "memory.sqlite3")

    assert index.lookup_term_id("person:user") == (derived_id,)
    assert index.lookup_term_id("drink:tea") == (derived_id,)
    assert index.lookup_term_id("doc:tea") == (derived_id,)
    assert index.lookup_unresolved_label("mystery") == (derived_id,)
    assert index.lookup_unresolved_label("Mystery") == ()
    assert index.lookup_operator_id("op:likes") == (derived_id,)
    assert index.lookup_operator_id("op:believes") == (derived_id,)
    assert index.lookup_lifecycle(Lifecycle.ACTIVE) == tuple(sorted((base_id, derived_id)))
    assert index.lookup_lifecycle(Lifecycle.SUPERSEDED) == (derived_id,)
    assert index.lookup_term_id("missing") == ()


def test_temporal_lookup_uses_inclusive_overlap_and_open_bounds(tmp_path: Path) -> None:
    _, kes, _ = _fixture()
    by_gloss = {ke.gloss: ke.id for ke in kes}
    index, _ = _build_index(tmp_path / "memory.sqlite3")

    assert index.lookup_temporal(JAN_3, JAN_3) == tuple(
        sorted((by_gloss["The user likes tea."], by_gloss["unbounded memory"]))
    )
    assert index.lookup_temporal(JAN_5, JAN_5) == tuple(
        sorted((by_gloss["point memory"], by_gloss["unbounded memory"]))
    )
    assert index.lookup_temporal(None, JAN_1) == tuple(
        sorted((by_gloss["base memory"], by_gloss["unbounded memory"]))
    )
    assert index.lookup_temporal(JAN_4, JAN_10) == tuple(
        sorted(
            (
                by_gloss["The user likes tea."],
                by_gloss["point memory"],
                by_gloss["future memory"],
                by_gloss["unbounded memory"],
            )
        )
    )
    assert index.lookup_temporal(JAN_6, None) == tuple(
        sorted((by_gloss["future memory"], by_gloss["unbounded memory"]))
    )
    assert index.lookup_temporal(None, None) == tuple(sorted(by_gloss.values()))
    with pytest.raises(IndexQueryError, match="end precedes start"):
        index.lookup_temporal(JAN_5, JAN_4)
    with pytest.raises(IndexQueryError, match="timezone-aware"):
        index.lookup_temporal(JAN_1, datetime(2026, 1, 2))


def test_aggregate_membership_lookups_are_bidirectional_and_sorted(tmp_path: Path) -> None:
    _, kes, _ = _fixture()
    derived_id = next(ke.id for ke in kes if ke.gloss == "The user likes tea.")
    index, _ = _build_index(tmp_path / "memory.sqlite3")

    assert index.lookup_aggregate_membership(derived_id) == ("aggregate-a", "aggregate-b")
    assert index.lookup_aggregate_membership("exchange-1") == ("aggregate-a",)
    assert index.members_of_aggregate("aggregate-a") == tuple(sorted((derived_id, "exchange-1")))
    assert index.members_of_aggregate("missing") == ()


def _failing_input() -> Iterator[Exchange]:
    yield _exchanges()[0]
    raise RuntimeError("injected input failure")


def test_input_failure_preserves_prior_cache_and_removes_temporary_database(tmp_path: Path) -> None:
    index, _ = _build_index(tmp_path / "memory.sqlite3")
    original = index.db_path.read_bytes()
    _, kes, aggregates = _fixture()

    with pytest.raises(IndexBuildError, match="input validation"):
        index.rebuild(_failing_input(), kes, aggregates)

    assert index.db_path.read_bytes() == original
    assert not list(tmp_path.glob(".memory.sqlite3.tmp-*"))


def test_sql_failure_preserves_prior_cache_and_removes_temporary_database(tmp_path: Path) -> None:
    index, _ = _build_index(tmp_path / "memory.sqlite3")
    original = index.db_path.read_bytes()
    exchanges, kes, aggregates = _fixture()

    with pytest.raises(IndexBuildError, match="rebuild"):
        index.rebuild((*exchanges, exchanges[0]), kes, aggregates)

    assert index.db_path.read_bytes() == original
    assert not list(tmp_path.glob(".memory.sqlite3.tmp-*"))


def test_source_span_failure_preserves_prior_cache(tmp_path: Path) -> None:
    index, _ = _build_index(tmp_path / "memory.sqlite3")
    original = index.db_path.read_bytes()
    exchanges, _, aggregates = _fixture()
    invalid_span = _span(text="wrong")
    invalid_ke = _simple_ke("invalid-span", evidence=invalid_span)

    with pytest.raises(IndexBuildError, match="source span"):
        index.rebuild(exchanges, (invalid_ke,), aggregates)

    assert index.db_path.read_bytes() == original


def test_missing_aggregate_member_rejects_rebuild_and_preserves_prior_cache(
    tmp_path: Path,
) -> None:
    index, _ = _build_index(tmp_path / "memory.sqlite3")
    original = index.db_path.read_bytes()
    exchanges, kes, _ = _fixture()
    broken = AggregateNode(
        id="aggregate-broken",
        node_kind=AggregateNodeKind.TOPIC,
        title="Broken",
        summary="Missing member.",
        member_refs=("missing-object",),
        confidence=0.5,
        revision="c" * 64,
        depth=1,
    )

    with pytest.raises(IndexBuildError, match="rebuild"):
        index.rebuild(exchanges, kes, (broken,))

    assert index.db_path.read_bytes() == original


def test_integrity_failure_preserves_prior_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ke_memory_demo.storage import sqlite_index

    index, _ = _build_index(tmp_path / "memory.sqlite3")
    original = index.db_path.read_bytes()
    exchanges, kes, aggregates = _fixture()

    def fail_integrity(_connection: sqlite3.Connection) -> tuple[str, ...]:
        return ("not ok",)

    monkeypatch.setattr(sqlite_index, "_run_integrity_check", fail_integrity)

    with pytest.raises(IndexBuildError, match="integrity"):
        index.rebuild(exchanges, kes, aggregates)

    assert index.db_path.read_bytes() == original
    assert not list(tmp_path.glob(".memory.sqlite3.tmp-*"))


def test_replace_failure_preserves_prior_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ke_memory_demo.storage import sqlite_index

    index, _ = _build_index(tmp_path / "memory.sqlite3")
    original = index.db_path.read_bytes()
    exchanges, kes, aggregates = _fixture()

    def fail_replace(_source: str | Path, _destination: str | Path) -> None:
        raise OSError("injected replace failure")

    monkeypatch.setattr(sqlite_index, "_replace", fail_replace)

    with pytest.raises(IndexBuildError, match="replace"):
        index.rebuild(exchanges, kes, aggregates)

    assert index.db_path.read_bytes() == original
    assert not list(tmp_path.glob(".memory.sqlite3.tmp-*"))


def test_lookup_requires_an_existing_cache(tmp_path: Path) -> None:
    index = MemoryIndex(tmp_path / "missing.sqlite3")

    with pytest.raises(IndexQueryError, match="does not exist"):
        index.ordered_ke_ids()


def test_database_file_is_closed_after_rebuild(tmp_path: Path) -> None:
    index, _ = _build_index(tmp_path / "memory.sqlite3")

    renamed = tmp_path / "renamed.sqlite3"
    os.replace(index.db_path, renamed)

    assert renamed.is_file()
    assert renamed.stat().st_size > 0
