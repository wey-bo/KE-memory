from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import Field, model_validator

from .authoritative_memory import (
    L1MemoryUnitV2,
    MemoryUnitRevision,
    SourceRecordRevision,
    StrictModel,
    canonical_sha256,
)


TurnSpeaker = Literal["user", "assistant", "tool"]
ExtractionState = Literal["raw_only", "complete", "failed"]
SOURCE_STATUSES_BY_SPEAKER = {
    "user": {"user_reported", "inferred"},
    "assistant": {"agent_generated", "inferred"},
    "tool": {"tool_observed", "inferred"},
}


class TurnSourceRevisionRef(StrictModel):
    ordinal: int = Field(ge=0)
    source_revision_id: str = Field(min_length=1)
    speaker: TurnSpeaker


def _payload(
    *,
    turn_bundle_id: str,
    revision_number: int,
    previous_revision_id: str | None,
    session_id: str,
    turn_id: str,
    turn_index: int,
    source_records: list[TurnSourceRevisionRef],
    extraction_state: ExtractionState,
    l1_unit_revision_ids: list[str],
    no_memory_reason: str | None,
    failure_reason: str | None,
    extractor_id: str | None,
    extractor_version: str | None,
    transaction_time: str,
) -> dict[str, object]:
    return {
        "turn_bundle_id": turn_bundle_id,
        "revision_number": revision_number,
        "previous_revision_id": previous_revision_id,
        "session_id": session_id,
        "turn_id": turn_id,
        "turn_index": turn_index,
        "source_records": [item.model_dump(mode="json") for item in source_records],
        "extraction_state": extraction_state,
        "l1_unit_revision_ids": l1_unit_revision_ids,
        "no_memory_reason": no_memory_reason,
        "failure_reason": failure_reason,
        "extractor_id": extractor_id,
        "extractor_version": extractor_version,
        "transaction_time": transaction_time,
    }


def _revision_id(*, turn_bundle_id: str, revision_number: int, previous_revision_id: str | None, payload_sha256: str) -> str:
    identity = {
        "turn_bundle_id": turn_bundle_id,
        "revision_number": revision_number,
        "previous_revision_id": previous_revision_id,
        "payload_sha256": payload_sha256,
    }
    return f"turn-bundle-revision-{canonical_sha256(identity)[:24]}"


def _source_revision_id(source: SourceRecordRevision) -> str:
    identity = {
        "source_record_id": source.source_record_id,
        "revision_number": source.revision_number,
        "previous_revision_id": source.previous_revision_id,
        "artifact_revision_id": source.artifact_revision_id,
        "source_ref": source.source_ref,
        "turn_id": source.turn_id,
        "session_id": source.session_id,
        "record_kind": source.record_kind,
        "content_sha256": source.content_sha256,
        "resolver_id": source.resolver_id,
        "resolver_version": source.resolver_version,
    }
    return f"source-revision-{canonical_sha256(identity)[:24]}"


def _unit_revision_id(revision: MemoryUnitRevision, payload_sha256: str) -> str:
    identity = {
        "memory_unit_id": revision.memory_unit_id,
        "revision_number": revision.revision_number,
        "previous_revision_id": revision.previous_revision_id,
        "revision_kind": revision.revision_kind,
        "payload_sha256": payload_sha256,
        "source_revision_ids": sorted(revision.source_revision_ids),
        "derived_from_revision_ids": sorted(revision.derived_from_revision_ids),
        "producer": revision.producer.model_dump(mode="json"),
    }
    return f"unit-revision-{canonical_sha256(identity)[:24]}"


class TurnBundleRevision(StrictModel):
    schema_version: Literal["turn-bundle-revision-v1"] = "turn-bundle-revision-v1"
    turn_bundle_id: str = Field(min_length=1)
    bundle_revision_id: str = Field(min_length=1)
    revision_number: int = Field(ge=1)
    previous_revision_id: str | None = Field(default=None, min_length=1)
    session_id: str = Field(min_length=1)
    turn_id: str = Field(min_length=1)
    turn_index: int = Field(ge=0)
    source_records: list[TurnSourceRevisionRef] = Field(min_length=2)
    extraction_state: ExtractionState
    l1_unit_revision_ids: list[str] = Field(default_factory=list)
    no_memory_reason: str | None = Field(default=None, min_length=1)
    failure_reason: str | None = Field(default=None, min_length=1)
    extractor_id: str | None = Field(default=None, min_length=1)
    extractor_version: str | None = Field(default=None, min_length=1)
    transaction_time: str = Field(min_length=1)
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_contract(self) -> "TurnBundleRevision":
        ordinals = [item.ordinal for item in self.source_records]
        if ordinals != list(range(len(self.source_records))):
            raise ValueError("source record ordinals must be contiguous and ordered from zero")
        source_ids = [item.source_revision_id for item in self.source_records]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source revision IDs must be unique within a turn bundle")
        if sum(item.speaker == "user" for item in self.source_records) != 1:
            raise ValueError("a turn bundle must contain exactly one user source record")
        if self.source_records[0].speaker != "user":
            raise ValueError("the first source record must be user")
        if not any(item.speaker == "assistant" for item in self.source_records):
            raise ValueError("a turn bundle must contain at least one assistant source record")
        if len(self.l1_unit_revision_ids) != len(set(self.l1_unit_revision_ids)):
            raise ValueError("L1 unit revision IDs must be unique within a turn bundle")
        if self.revision_number == 1 and self.previous_revision_id is not None:
            raise ValueError("revision 1 cannot have a previous revision")
        if self.revision_number > 1 and self.previous_revision_id is None:
            raise ValueError("later revisions require a previous revision")

        has_extractor = self.extractor_id is not None and self.extractor_version is not None
        if (self.extractor_id is None) != (self.extractor_version is None):
            raise ValueError("extractor_id and extractor_version must be provided together")
        if self.extraction_state == "raw_only":
            if self.l1_unit_revision_ids or self.no_memory_reason or self.failure_reason or has_extractor:
                raise ValueError("raw-only bundle cannot publish extraction output")
        elif self.extraction_state == "complete":
            if not has_extractor:
                raise ValueError("complete bundle requires extractor identity")
            if self.failure_reason is not None:
                raise ValueError("complete bundle cannot carry a failure reason")
            if not self.l1_unit_revision_ids and self.no_memory_reason is None:
                raise ValueError("complete empty extraction requires no_memory_reason")
            if self.l1_unit_revision_ids and self.no_memory_reason is not None:
                raise ValueError("no_memory_reason is allowed only when no L1 units were extracted")
        else:
            if not has_extractor:
                raise ValueError("failed bundle requires extractor identity")
            if self.l1_unit_revision_ids:
                raise ValueError("failed bundle cannot publish partial L1 membership")
            if self.failure_reason is None:
                raise ValueError("failed bundle requires failure_reason")
            if self.no_memory_reason is not None:
                raise ValueError("failed bundle cannot carry no_memory_reason")

        payload = _payload(
            turn_bundle_id=self.turn_bundle_id,
            revision_number=self.revision_number,
            previous_revision_id=self.previous_revision_id,
            session_id=self.session_id,
            turn_id=self.turn_id,
            turn_index=self.turn_index,
            source_records=self.source_records,
            extraction_state=self.extraction_state,
            l1_unit_revision_ids=self.l1_unit_revision_ids,
            no_memory_reason=self.no_memory_reason,
            failure_reason=self.failure_reason,
            extractor_id=self.extractor_id,
            extractor_version=self.extractor_version,
            transaction_time=self.transaction_time,
        )
        expected_payload_sha256 = canonical_sha256(payload)
        if self.payload_sha256 != expected_payload_sha256:
            raise ValueError("payload_sha256 does not match the canonical turn bundle payload")
        expected_revision_id = _revision_id(
            turn_bundle_id=self.turn_bundle_id,
            revision_number=self.revision_number,
            previous_revision_id=self.previous_revision_id,
            payload_sha256=self.payload_sha256,
        )
        if self.bundle_revision_id != expected_revision_id:
            raise ValueError("bundle_revision_id does not match the canonical revision identity")
        return self


def make_turn_bundle_revision(
    *,
    turn_bundle_id: str,
    revision_number: int,
    previous_revision_id: str | None,
    session_id: str,
    turn_id: str,
    turn_index: int,
    source_records: list[TurnSourceRevisionRef],
    extraction_state: ExtractionState,
    l1_unit_revision_ids: list[str],
    no_memory_reason: str | None,
    failure_reason: str | None,
    extractor_id: str | None,
    extractor_version: str | None,
    transaction_time: str,
) -> TurnBundleRevision:
    payload = _payload(
        turn_bundle_id=turn_bundle_id,
        revision_number=revision_number,
        previous_revision_id=previous_revision_id,
        session_id=session_id,
        turn_id=turn_id,
        turn_index=turn_index,
        source_records=source_records,
        extraction_state=extraction_state,
        l1_unit_revision_ids=l1_unit_revision_ids,
        no_memory_reason=no_memory_reason,
        failure_reason=failure_reason,
        extractor_id=extractor_id,
        extractor_version=extractor_version,
        transaction_time=transaction_time,
    )
    payload_sha256 = canonical_sha256(payload)
    return TurnBundleRevision(
        bundle_revision_id=_revision_id(
            turn_bundle_id=turn_bundle_id,
            revision_number=revision_number,
            previous_revision_id=previous_revision_id,
            payload_sha256=payload_sha256,
        ),
        payload_sha256=payload_sha256,
        **payload,
    )


def validate_turn_bundle_closure(
    bundle: TurnBundleRevision,
    *,
    source_revisions: dict[str, SourceRecordRevision],
    unit_revisions: dict[str, MemoryUnitRevision],
) -> None:
    errors: list[str] = []
    bundle_source_ids = {item.source_revision_id for item in bundle.source_records}
    source_ref_by_id = {item.source_revision_id: item for item in bundle.source_records}

    for reference in bundle.source_records:
        source = source_revisions.get(reference.source_revision_id)
        if source is None:
            errors.append(f"missing source revision {reference.source_revision_id}")
            continue
        if source.source_revision_id != reference.source_revision_id:
            errors.append(
                f"source revision {reference.source_revision_id} lookup key does not match revision identity"
            )
        actual_content_sha256 = hashlib.sha256(source.text.encode("utf-8")).hexdigest()
        if actual_content_sha256 != source.content_sha256:
            errors.append(f"source revision {source.source_revision_id} content hash mismatch")
        if source.source_revision_id != _source_revision_id(source):
            errors.append(f"source revision {source.source_revision_id} canonical identity mismatch")
        if source.turn_id != bundle.turn_id or source.session_id != bundle.session_id:
            errors.append(f"source revision {source.source_revision_id} is outside the turn bundle")
        if source.metadata.get("speaker") != reference.speaker:
            errors.append(f"source revision {source.source_revision_id} has a mismatched speaker binding")

    for revision_id in bundle.l1_unit_revision_ids:
        revision = unit_revisions.get(revision_id)
        if revision is None:
            errors.append(f"missing L1 unit revision {revision_id}")
            continue
        if revision.revision_id != revision_id:
            errors.append(
                f"unit revision {revision_id} lookup key does not match revision identity"
            )
        actual_payload_sha256 = canonical_sha256(revision.payload)
        if actual_payload_sha256 != revision.payload_sha256:
            errors.append(f"unit revision {revision_id} payload hash mismatch")
        if revision.revision_id != _unit_revision_id(revision, actual_payload_sha256):
            errors.append(f"unit revision {revision_id} canonical identity mismatch")
        if not isinstance(revision.payload, L1MemoryUnitV2):
            errors.append(f"unit revision {revision_id} is not an L1 memory unit")
            continue
        declared_source_ids = set(revision.source_revision_ids)
        evidence_source_ids = {
            span.source_revision_id for span in revision.payload.source.evidence_spans
        }
        if declared_source_ids != evidence_source_ids:
            errors.append(
                f"unit revision {revision_id} declared source revisions do not match evidence"
            )
        if not declared_source_ids.issubset(bundle_source_ids):
            errors.append(f"unit revision {revision_id} uses source revisions outside the turn bundle")

        evidence_speakers = {
            source_ref_by_id[source_id].speaker
            for source_id in evidence_source_ids
            if source_id in source_ref_by_id
        }
        if evidence_speakers != {revision.payload.source.speaker}:
            errors.append(
                f"unit revision {revision_id} speaker binding does not match evidence sources"
            )
        if (
            len(evidence_speakers) == 1
            and revision.payload.source.source_status
            not in SOURCE_STATUSES_BY_SPEAKER[next(iter(evidence_speakers))]
        ):
            errors.append(
                f"unit revision {revision_id} source status does not match evidence speaker"
            )
        for span in revision.payload.source.evidence_spans:
            if span.source_revision_id not in bundle_source_ids:
                errors.append(f"evidence {span.evidence_id} is outside the turn bundle")
            if span.turn_id != bundle.turn_id or span.session_id != bundle.session_id:
                errors.append(f"evidence {span.evidence_id} has a mismatched turn or session")
            source = source_revisions.get(span.source_revision_id)
            if source is None:
                errors.append(
                    f"evidence {span.evidence_id} references missing source revision "
                    f"{span.source_revision_id}"
                )
                continue
            if span.turn_id != source.turn_id or span.session_id != source.session_id:
                errors.append(
                    f"evidence {span.evidence_id} source coordinates do not match source revision"
                )
            if hashlib.sha256(span.text.encode("utf-8")).hexdigest() != span.quote_sha256:
                errors.append(f"evidence {span.evidence_id} quote hash mismatch")
            if span.char_end > len(source.text):
                errors.append(f"evidence {span.evidence_id} offset exceeds source text")
            elif source.text[span.char_start : span.char_end] != span.text:
                errors.append(f"evidence {span.evidence_id} quote slice mismatch")

    if errors:
        raise ValueError("; ".join(errors))
