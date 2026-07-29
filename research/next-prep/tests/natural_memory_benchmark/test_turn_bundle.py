from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError

from tools.natural_memory_benchmark.authoritative_memory import (
    L1MemoryUnitV2,
    ProducerIdentity,
    SourceBindingV2,
    make_evidence_span,
    make_memory_unit_revision,
    make_source_record_revision,
)
from tools.natural_memory_benchmark.semantic_ir import Predicate, RoleBinding
from tools.natural_memory_benchmark.turn_bundle import (
    TurnBundleRevision,
    TurnSourceRevisionRef,
    make_turn_bundle_revision,
    validate_turn_bundle_closure,
)


def _source(*, name: str, speaker: str, text: str, turn_id: str = "turn-1"):
    return make_source_record_revision(
        source_record_id=f"source-{name}",
        revision_number=1,
        previous_revision_id=None,
        artifact_revision_id="artifact-revision-test",
        source_ref=f"fixture={name}",
        turn_id=turn_id,
        session_id="session-1",
        record_kind="message",
        text=text,
        resolver_id="turn-bundle-test",
        resolver_version="1",
        transaction_time="2026-07-28T00:00:00Z",
        metadata={"speaker": speaker},
    )


def _l1_revision(*, name: str, source, speaker: str):
    span = make_evidence_span(
        evidence_id=f"evidence-{name}",
        source_revision=source,
        turn_id=source.turn_id,
        session_id=source.session_id,
        char_start=0,
        char_end=len(source.text),
        text=source.text,
    )
    unit = L1MemoryUnitV2(
        unit_id=f"l1-{name}",
        kind="event",
        predicate=Predicate(surface="prefer", sense="prefer-01", canonical_operator="prefers"),
        roles=[RoleBinding(role="ARG0", entity_id="user", role_name="experiencer")],
        source=SourceBindingV2(
            speaker=speaker,
            source_status="user_reported" if speaker == "user" else "agent_generated",
            evidence_spans=[span],
        ),
    )
    return make_memory_unit_revision(
        payload=unit,
        revision_number=1,
        previous_revision_id=None,
        revision_kind="create",
        transaction_time="2026-07-28T00:00:01Z",
        source_revision_ids=[source.source_revision_id],
        derived_from_revision_ids=[],
        producer=ProducerIdentity(
            workflow_run_id="turn-bundle-test",
            producer_id="test-extractor",
            producer_version="1",
        ),
    )


def _complete_bundle(user_source, assistant_source, *l1_revisions):
    return make_turn_bundle_revision(
        turn_bundle_id="turn-bundle-1",
        revision_number=1,
        previous_revision_id=None,
        session_id="session-1",
        turn_id="turn-1",
        turn_index=0,
        source_records=[
            TurnSourceRevisionRef(
                ordinal=0,
                source_revision_id=user_source.source_revision_id,
                speaker="user",
            ),
            TurnSourceRevisionRef(
                ordinal=1,
                source_revision_id=assistant_source.source_revision_id,
                speaker="assistant",
            ),
        ],
        extraction_state="complete",
        l1_unit_revision_ids=[item.revision_id for item in l1_revisions],
        no_memory_reason=None,
        failure_reason=None,
        extractor_id="test-extractor",
        extractor_version="1",
        transaction_time="2026-07-28T00:00:02Z",
    )


def _raw_bundle(user_source, assistant_source):
    return make_turn_bundle_revision(
        turn_bundle_id="turn-bundle-raw",
        revision_number=1,
        previous_revision_id=None,
        session_id="session-1",
        turn_id="turn-1",
        turn_index=0,
        source_records=[
            TurnSourceRevisionRef(
                ordinal=0,
                source_revision_id=user_source.source_revision_id,
                speaker="user",
            ),
            TurnSourceRevisionRef(
                ordinal=1,
                source_revision_id=assistant_source.source_revision_id,
                speaker="assistant",
            ),
        ],
        extraction_state="raw_only",
        l1_unit_revision_ids=[],
        no_memory_reason=None,
        failure_reason=None,
        extractor_id=None,
        extractor_version=None,
        transaction_time="2026-07-28T00:00:02Z",
    )


def test_turn_bundle_is_transaction_boundary_for_multiple_atomic_l1_units() -> None:
    user_source = _source(name="user", speaker="user", text="I prefer tea and started a report.")
    assistant_source = _source(name="assistant", speaker="assistant", text="I recorded both updates.")
    first = _l1_revision(name="preference", source=user_source, speaker="user")
    second = _l1_revision(name="task", source=user_source, speaker="user")
    bundle = _complete_bundle(user_source, assistant_source, first, second)

    validate_turn_bundle_closure(
        bundle,
        source_revisions={
            user_source.source_revision_id: user_source,
            assistant_source.source_revision_id: assistant_source,
        },
        unit_revisions={first.revision_id: first, second.revision_id: second},
    )

    assert bundle.extraction_state == "complete"
    assert bundle.l1_unit_revision_ids == [first.revision_id, second.revision_id]


def test_complete_empty_extraction_requires_explicit_no_memory_reason() -> None:
    user_source = _source(name="user", speaker="user", text="Hello.")
    assistant_source = _source(name="assistant", speaker="assistant", text="Hello.")
    refs = [
        TurnSourceRevisionRef(ordinal=0, source_revision_id=user_source.source_revision_id, speaker="user"),
        TurnSourceRevisionRef(
            ordinal=1,
            source_revision_id=assistant_source.source_revision_id,
            speaker="assistant",
        ),
    ]

    with pytest.raises(ValidationError, match="no_memory_reason"):
        make_turn_bundle_revision(
            turn_bundle_id="turn-bundle-empty",
            revision_number=1,
            previous_revision_id=None,
            session_id="session-1",
            turn_id="turn-1",
            turn_index=0,
            source_records=refs,
            extraction_state="complete",
            l1_unit_revision_ids=[],
            no_memory_reason=None,
            failure_reason=None,
            extractor_id="test-extractor",
            extractor_version="1",
            transaction_time="2026-07-28T00:00:02Z",
        )

    bundle = make_turn_bundle_revision(
        turn_bundle_id="turn-bundle-empty",
        revision_number=1,
        previous_revision_id=None,
        session_id="session-1",
        turn_id="turn-1",
        turn_index=0,
        source_records=refs,
        extraction_state="complete",
        l1_unit_revision_ids=[],
        no_memory_reason="no_admissible_memory",
        failure_reason=None,
        extractor_id="test-extractor",
        extractor_version="1",
        transaction_time="2026-07-28T00:00:02Z",
    )
    assert bundle.no_memory_reason == "no_admissible_memory"


def test_failed_bundle_cannot_publish_partial_l1_membership() -> None:
    user_source = _source(name="user", speaker="user", text="Remember this.")
    assistant_source = _source(name="assistant", speaker="assistant", text="Understood.")
    refs = [
        TurnSourceRevisionRef(ordinal=0, source_revision_id=user_source.source_revision_id, speaker="user"),
        TurnSourceRevisionRef(
            ordinal=1,
            source_revision_id=assistant_source.source_revision_id,
            speaker="assistant",
        ),
    ]

    with pytest.raises(ValidationError, match="failed bundle cannot publish"):
        make_turn_bundle_revision(
            turn_bundle_id="turn-bundle-failed",
            revision_number=1,
            previous_revision_id=None,
            session_id="session-1",
            turn_id="turn-1",
            turn_index=0,
            source_records=refs,
            extraction_state="failed",
            l1_unit_revision_ids=["unit-revision-partial"],
            no_memory_reason=None,
            failure_reason="extractor_timeout",
            extractor_id="test-extractor",
            extractor_version="1",
            transaction_time="2026-07-28T00:00:02Z",
        )


def test_turn_bundle_rejects_noncontiguous_order_and_missing_assistant() -> None:
    with pytest.raises(ValidationError, match="contiguous"):
        make_turn_bundle_revision(
            turn_bundle_id="turn-bundle-order",
            revision_number=1,
            previous_revision_id=None,
            session_id="session-1",
            turn_id="turn-1",
            turn_index=0,
            source_records=[
                TurnSourceRevisionRef(ordinal=1, source_revision_id="source-user", speaker="user"),
                TurnSourceRevisionRef(ordinal=2, source_revision_id="source-agent", speaker="assistant"),
            ],
            extraction_state="raw_only",
            l1_unit_revision_ids=[],
            no_memory_reason=None,
            failure_reason=None,
            extractor_id=None,
            extractor_version=None,
            transaction_time="2026-07-28T00:00:02Z",
        )

    with pytest.raises(ValidationError, match="assistant"):
        make_turn_bundle_revision(
            turn_bundle_id="turn-bundle-speaker",
            revision_number=1,
            previous_revision_id=None,
            session_id="session-1",
            turn_id="turn-1",
            turn_index=0,
            source_records=[
                TurnSourceRevisionRef(ordinal=0, source_revision_id="source-user", speaker="user"),
                TurnSourceRevisionRef(ordinal=1, source_revision_id="source-tool", speaker="tool"),
            ],
            extraction_state="raw_only",
            l1_unit_revision_ids=[],
            no_memory_reason=None,
            failure_reason=None,
            extractor_id=None,
            extractor_version=None,
            transaction_time="2026-07-28T00:00:02Z",
        )


def test_closure_rejects_l1_evidence_from_another_turn() -> None:
    user_source = _source(name="user", speaker="user", text="I prefer tea.")
    assistant_source = _source(name="assistant", speaker="assistant", text="Noted.")
    foreign_source = _source(
        name="foreign",
        speaker="user",
        text="I prefer coffee.",
        turn_id="turn-2",
    )
    foreign_l1 = _l1_revision(name="foreign", source=foreign_source, speaker="user")
    bundle = _complete_bundle(user_source, assistant_source, foreign_l1)

    with pytest.raises(ValueError, match="outside the turn bundle"):
        validate_turn_bundle_closure(
            bundle,
            source_revisions={
                user_source.source_revision_id: user_source,
                assistant_source.source_revision_id: assistant_source,
                foreign_source.source_revision_id: foreign_source,
            },
            unit_revisions={foreign_l1.revision_id: foreign_l1},
        )


def test_bundle_payload_hash_rejects_tampering() -> None:
    user_source = _source(name="user", speaker="user", text="I prefer tea.")
    assistant_source = _source(name="assistant", speaker="assistant", text="Noted.")
    l1_revision = _l1_revision(name="preference", source=user_source, speaker="user")
    bundle = _complete_bundle(user_source, assistant_source, l1_revision)
    payload = bundle.model_dump(mode="json")
    payload["payload_sha256"] = "0" * 64

    with pytest.raises(ValidationError, match="payload_sha256"):
        TurnBundleRevision.model_validate(payload)


def test_turn_bundle_rejects_user_source_after_assistant_output() -> None:
    with pytest.raises(ValidationError, match="first source record must be user"):
        make_turn_bundle_revision(
            turn_bundle_id="turn-bundle-order",
            revision_number=1,
            previous_revision_id=None,
            session_id="session-1",
            turn_id="turn-1",
            turn_index=0,
            source_records=[
                TurnSourceRevisionRef(
                    ordinal=0,
                    source_revision_id="source-assistant",
                    speaker="assistant",
                ),
                TurnSourceRevisionRef(
                    ordinal=1,
                    source_revision_id="source-user",
                    speaker="user",
                ),
            ],
            extraction_state="raw_only",
            l1_unit_revision_ids=[],
            no_memory_reason=None,
            failure_reason=None,
            extractor_id=None,
            extractor_version=None,
            transaction_time="2026-07-28T00:00:02Z",
        )


def test_bundle_payload_hash_commits_transaction_time() -> None:
    user_source = _source(name="user", speaker="user", text="I prefer tea.")
    assistant_source = _source(name="assistant", speaker="assistant", text="Noted.")
    l1_revision = _l1_revision(name="preference", source=user_source, speaker="user")
    bundle = _complete_bundle(user_source, assistant_source, l1_revision)
    payload = bundle.model_dump(mode="json")
    payload["transaction_time"] = "2026-07-28T00:00:03Z"

    with pytest.raises(ValidationError, match="payload_sha256"):
        TurnBundleRevision.model_validate(payload)


def test_closure_rejects_fabricated_quote_inside_the_same_turn() -> None:
    user_source = _source(name="user", speaker="user", text="I prefer tea.")
    assistant_source = _source(name="assistant", speaker="assistant", text="Noted.")
    l1_revision = _l1_revision(name="preference", source=user_source, speaker="user")
    span = l1_revision.payload.source.evidence_spans[0]
    fabricated_text = "I prefer rum."
    fabricated_span = span.model_copy(
        update={
            "char_end": len(fabricated_text),
            "text": fabricated_text,
            "quote_sha256": hashlib.sha256(fabricated_text.encode("utf-8")).hexdigest(),
        }
    )
    fabricated_source = l1_revision.payload.source.model_copy(
        update={"evidence_spans": [fabricated_span]}
    )
    fabricated_unit = l1_revision.payload.model_copy(update={"source": fabricated_source})
    fabricated_revision = l1_revision.model_copy(update={"payload": fabricated_unit})
    bundle = _complete_bundle(user_source, assistant_source, fabricated_revision)

    with pytest.raises(ValueError, match="quote slice mismatch"):
        validate_turn_bundle_closure(
            bundle,
            source_revisions={
                user_source.source_revision_id: user_source,
                assistant_source.source_revision_id: assistant_source,
            },
            unit_revisions={fabricated_revision.revision_id: fabricated_revision},
        )


def test_closure_rejects_l1_source_revision_ids_without_matching_evidence() -> None:
    user_source = _source(name="user", speaker="user", text="I prefer tea.")
    assistant_source = _source(name="assistant", speaker="assistant", text="Noted.")
    l1_revision = _l1_revision(name="preference", source=user_source, speaker="user")
    mismatched_revision = l1_revision.model_copy(
        update={"source_revision_ids": [assistant_source.source_revision_id]}
    )
    bundle = _complete_bundle(user_source, assistant_source, mismatched_revision)

    with pytest.raises(ValueError, match="declared source revisions do not match evidence"):
        validate_turn_bundle_closure(
            bundle,
            source_revisions={
                user_source.source_revision_id: user_source,
                assistant_source.source_revision_id: assistant_source,
            },
            unit_revisions={mismatched_revision.revision_id: mismatched_revision},
        )


def test_closure_rejects_l1_speaker_and_status_mismatch() -> None:
    user_source = _source(name="user", speaker="user", text="I prefer tea.")
    assistant_source = _source(name="assistant", speaker="assistant", text="Noted.")
    l1_revision = _l1_revision(name="preference", source=user_source, speaker="user")
    mismatched_source = l1_revision.payload.source.model_copy(
        update={"speaker": "assistant", "source_status": "agent_generated"}
    )
    mismatched_unit = l1_revision.payload.model_copy(update={"source": mismatched_source})
    mismatched_revision = l1_revision.model_copy(update={"payload": mismatched_unit})
    bundle = _complete_bundle(user_source, assistant_source, mismatched_revision)

    with pytest.raises(ValueError, match="speaker binding does not match evidence sources"):
        validate_turn_bundle_closure(
            bundle,
            source_revisions={
                user_source.source_revision_id: user_source,
                assistant_source.source_revision_id: assistant_source,
            },
            unit_revisions={mismatched_revision.revision_id: mismatched_revision},
        )


def test_closure_rejects_lookup_key_that_does_not_match_revision_identity() -> None:
    user_source = _source(name="user", speaker="user", text="I prefer tea.")
    assistant_source = _source(name="assistant", speaker="assistant", text="Noted.")
    l1_revision = _l1_revision(name="preference", source=user_source, speaker="user")
    mismatched_revision = l1_revision.model_copy(update={"revision_id": "unit-revision-other"})
    bundle = _complete_bundle(user_source, assistant_source, l1_revision)

    with pytest.raises(ValueError, match="lookup key does not match revision identity"):
        validate_turn_bundle_closure(
            bundle,
            source_revisions={
                user_source.source_revision_id: user_source,
                assistant_source.source_revision_id: assistant_source,
            },
            unit_revisions={l1_revision.revision_id: mismatched_revision},
        )


def test_closure_rejects_source_status_mismatch() -> None:
    user_source = _source(name="user", speaker="user", text="I prefer tea.")
    assistant_source = _source(name="assistant", speaker="assistant", text="Noted.")
    l1_revision = _l1_revision(name="preference", source=user_source, speaker="user")
    mismatched_source = l1_revision.payload.source.model_copy(
        update={"source_status": "tool_observed"}
    )
    mismatched_unit = l1_revision.payload.model_copy(update={"source": mismatched_source})
    mismatched_revision = l1_revision.model_copy(update={"payload": mismatched_unit})
    bundle = _complete_bundle(user_source, assistant_source, mismatched_revision)

    with pytest.raises(ValueError, match="source status does not match evidence speaker"):
        validate_turn_bundle_closure(
            bundle,
            source_revisions={
                user_source.source_revision_id: user_source,
                assistant_source.source_revision_id: assistant_source,
            },
            unit_revisions={mismatched_revision.revision_id: mismatched_revision},
        )


def test_closure_rejects_source_lookup_key_mismatch() -> None:
    user_source = _source(name="user", speaker="user", text="I prefer tea.")
    assistant_source = _source(name="assistant", speaker="assistant", text="Noted.")
    bundle = _raw_bundle(user_source, assistant_source)
    mismatched_source = user_source.model_copy(
        update={"source_revision_id": "source-revision-other"}
    )

    with pytest.raises(ValueError, match="lookup key does not match revision identity"):
        validate_turn_bundle_closure(
            bundle,
            source_revisions={
                user_source.source_revision_id: mismatched_source,
                assistant_source.source_revision_id: assistant_source,
            },
            unit_revisions={},
        )


def test_closure_rejects_source_content_changed_under_existing_identity() -> None:
    user_source = _source(name="user", speaker="user", text="I prefer tea.")
    assistant_source = _source(name="assistant", speaker="assistant", text="Noted.")
    bundle = _raw_bundle(user_source, assistant_source)
    replacement_text = "I prefer rum."
    mismatched_source = user_source.model_copy(
        update={
            "text": replacement_text,
            "content_sha256": hashlib.sha256(replacement_text.encode("utf-8")).hexdigest(),
        }
    )

    with pytest.raises(ValueError, match="canonical identity mismatch"):
        validate_turn_bundle_closure(
            bundle,
            source_revisions={
                user_source.source_revision_id: mismatched_source,
                assistant_source.source_revision_id: assistant_source,
            },
            unit_revisions={},
        )


def test_closure_rejects_unit_payload_changed_under_existing_identity() -> None:
    user_source = _source(name="user", speaker="user", text="I prefer tea.")
    assistant_source = _source(name="assistant", speaker="assistant", text="Noted.")
    l1_revision = _l1_revision(name="preference", source=user_source, speaker="user")
    mismatched_unit = l1_revision.payload.model_copy(update={"polarity": "negative"})
    mismatched_revision = l1_revision.model_copy(update={"payload": mismatched_unit})
    bundle = _complete_bundle(user_source, assistant_source, mismatched_revision)

    with pytest.raises(ValueError, match="payload hash mismatch"):
        validate_turn_bundle_closure(
            bundle,
            source_revisions={
                user_source.source_revision_id: user_source,
                assistant_source.source_revision_id: assistant_source,
            },
            unit_revisions={mismatched_revision.revision_id: mismatched_revision},
        )
