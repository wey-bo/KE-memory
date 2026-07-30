"""Deterministic, non-authoritative admission for linked Local L1 proposals.

The module deliberately produces a decision only.  It neither imports an authority
writer nor materializes an L1 revision.  A caller must treat an ``accept`` decision
as a proposal for a later, separately authorized transaction.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import stat
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .authoritative_memory import (
    EvidenceSpanV2,
    RawArtifactRevision,
    SourceRecordRevision,
    canonical_sha256,
    make_raw_artifact_revision,
    make_source_record_revision,
)
from .io import canonical_json_bytes, write_json_immutable, write_text_immutable
from .l1_ontology_linking import (
    CanonicalEntityBinding,
    LinkedL1Candidate,
    OntologyRegistry,
    build_diagnostic_ontology_registry,
    is_subtype,
    link_l1_candidate,
    ontology_registry_canonical_bytes,
)
from .typed_extractor_l1 import (
    TypedDerivationProvenance,
    TypedEvidenceBinding,
    TypedL1Candidate,
    TypedLifecycleBinding,
    TypedLocalEntity,
    TypedOperationProvenance,
    TypedPredicate,
    TypedRoleBinding,
    TypedTimeBinding,
)


class StrictModel(BaseModel):
    """Immutable, closed admission contract boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


_SHA256 = r"^[0-9a-f]{64}$"
_ZERO_WRITES = {
    "l1": 0,
    "l2": 0,
    "identity": 0,
    "membership": 0,
    "closure": 0,
    "revision": 0,
    "snapshot": 0,
    "aggregate": 0,
}
_SOURCE_STATUSES = Literal[
    "user_reported", "agent_generated", "tool_observed", "inferred"
]
_EVIDENCE_SPEAKERS = Literal["user", "assistant", "tool"]
_REASON_PRIORITY = (
    "source_candidate_bytes_mismatch",
    "source_candidate_hash_mismatch",
    "registry_hash_mismatch",
    "linked_registry_binding_mismatch",
    "linked_candidate_hash_mismatch",
    "deterministic_link_replay_failed",
    "deterministic_link_replay_mismatch",
    "evidence_binding_closure_mismatch",
    "unexpected_source_revision",
    "evidence_source_revision_missing",
    "unexpected_raw_artifact_revision",
    "source_artifact_revision_missing",
    "raw_artifact_unavailable",
    "raw_artifact_revision_identity_mismatch",
    "raw_artifact_size_mismatch",
    "raw_artifact_content_hash_mismatch",
    "source_revision_identity_mismatch",
    "source_content_hash_mismatch",
    "source_epistemic_closure_mismatch",
    "evidence_quote_hash_mismatch",
    "evidence_source_context_mismatch",
    "evidence_source_slice_out_of_range",
    "evidence_source_slice_mismatch",
    "evidence_epistemic_speaker_mismatch",
    "speaker_source_status_incompatible",
    "link_evidence_unbound",
    "evidence_speaker_not_authorized",
    "predicate_link_mismatch",
    "predicate_role_rule_missing",
    "entity_link_missing",
    "unknown_local_concept",
    "predicate_role_type_incompatible",
    "predicate_rule_binding_mismatch",
    "ontology_extension_required",
    "ontology_link_unresolved",
    "category_identity_shape_invalid",
    "identity_unresolved",
    "identity_binding_mismatch",
    "identity_registry_revision_mismatch",
    "identity_type_incompatible",
    "identity_authority_unavailable",
    "identity_snapshot_hash_mismatch",
    "identity_snapshot_binding_mismatch",
    "identity_registry_binding_mismatch",
    "identity_membership_missing",
    "identity_membership_type_incompatible",
    "hypothetical_modality",
    "modality_not_authorized",
    "polarity_not_authorized",
    "source_status_not_authorized",
    "transaction_time_missing",
    "transaction_time_invalid",
    "source_transaction_time_invalid",
    "transaction_time_precedes_source",
    "time_binding_unresolved",
    "lifecycle_target_missing",
    "lifecycle_revision_hash_mismatch",
    "lifecycle_target_unresolved",
    "lifecycle_target_not_active",
)
_REASON_PRIORITY_BY_CODE = {
    reason: index for index, reason in enumerate(_REASON_PRIORITY)
}


def _normalize_reasons(reasons: list[str]) -> list[str]:
    return sorted(
        set(reasons),
        key=lambda reason: (
            _REASON_PRIORITY_BY_CODE.get(reason, len(_REASON_PRIORITY)),
            reason,
        ),
    )


class AdmissionPolicy(StrictModel):
    """Versioned deterministic admission policy, not a write authorization."""

    schema_version: Literal["l1-admission-policy-v1"] = "l1-admission-policy-v1"
    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    allow_modalities: list[
        Literal[
            "actual", "planned", "hypothetical", "requested", "recommended", "denied"
        ]
    ] = Field(min_length=1)
    allow_source_statuses: list[_SOURCE_STATUSES] = Field(min_length=1)
    allow_polarities: list[Literal["positive", "negative"]] = Field(
        default_factory=lambda: ["positive", "negative"]
    )
    allow_evidence_speakers: list[_EVIDENCE_SPEAKERS] = Field(
        default_factory=lambda: ["user", "assistant", "tool"]
    )
    require_transaction_time: bool = True

    @model_validator(mode="after")
    def validate_policy_lists(self) -> "AdmissionPolicy":
        for name in (
            "allow_modalities",
            "allow_source_statuses",
            "allow_polarities",
            "allow_evidence_speakers",
        ):
            values = getattr(self, name)
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate {name} entry")
        return self


class SourceEpistemicBinding(StrictModel):
    source_revision_id: str = Field(min_length=1)
    source_status: _SOURCE_STATUSES
    speaker: _EVIDENCE_SPEAKERS


class CanonicalIdentityMembership(StrictModel):
    canonical_entity_id: str = Field(min_length=1)
    member_entity_ids: list[str] = Field(min_length=1)
    concept_type_ids: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_membership(self) -> "CanonicalIdentityMembership":
        if len(self.member_entity_ids) != len(set(self.member_entity_ids)):
            raise ValueError("duplicate identity member")
        if len(self.concept_type_ids) != len(set(self.concept_type_ids)):
            raise ValueError("duplicate identity concept type")
        if self.canonical_entity_id not in self.member_entity_ids:
            raise ValueError("canonical identity must be present in its membership")
        return self


def _identity_snapshot_payload(
    *,
    snapshot_id: str,
    snapshot_revision: str,
    identity_registry_revision: str,
    identity_registry_hash: str,
    memberships: list[CanonicalIdentityMembership],
    unresolved_entity_ids: list[str],
) -> dict[str, object]:
    normalized_memberships = [
        membership.model_copy(
            update={
                "member_entity_ids": sorted(membership.member_entity_ids),
                "concept_type_ids": sorted(membership.concept_type_ids),
            }
        ).model_dump(mode="json")
        for membership in memberships
    ]
    return {
        "snapshot_id": snapshot_id,
        "snapshot_revision": snapshot_revision,
        "identity_registry_revision": identity_registry_revision,
        "identity_registry_hash": identity_registry_hash,
        "memberships": sorted(
            normalized_memberships,
            key=lambda item: str(item["canonical_entity_id"]),
        ),
        "unresolved_entity_ids": sorted(unresolved_entity_ids),
    }


class IdentitySnapshotAuthority(StrictModel):
    schema_version: Literal["l1-identity-snapshot-authority-v1"] = (
        "l1-identity-snapshot-authority-v1"
    )
    snapshot_id: str = Field(min_length=1)
    snapshot_revision: str = Field(min_length=1)
    identity_registry_revision: str = Field(min_length=1)
    identity_registry_hash: str = Field(pattern=_SHA256)
    memberships: list[CanonicalIdentityMembership] = Field(min_length=1)
    unresolved_entity_ids: list[str] = Field(default_factory=list)
    snapshot_hash: str = Field(pattern=_SHA256)

    @model_validator(mode="after")
    def validate_snapshot(self) -> "IdentitySnapshotAuthority":
        canonical_ids = [item.canonical_entity_id for item in self.memberships]
        if len(canonical_ids) != len(set(canonical_ids)):
            raise ValueError("duplicate canonical identity membership")
        if len(self.unresolved_entity_ids) != len(set(self.unresolved_entity_ids)):
            raise ValueError("duplicate unresolved identity")
        payload = _identity_snapshot_payload(
            snapshot_id=self.snapshot_id,
            snapshot_revision=self.snapshot_revision,
            identity_registry_revision=self.identity_registry_revision,
            identity_registry_hash=self.identity_registry_hash,
            memberships=self.memberships,
            unresolved_entity_ids=self.unresolved_entity_ids,
        )
        if self.snapshot_hash != canonical_sha256(payload):
            raise ValueError("identity snapshot hash mismatch")
        return self


def make_identity_snapshot_authority(
    *,
    snapshot_id: str,
    snapshot_revision: str,
    identity_registry_revision: str,
    identity_registry_hash: str,
    memberships: list[CanonicalIdentityMembership],
    unresolved_entity_ids: list[str],
) -> IdentitySnapshotAuthority:
    payload = _identity_snapshot_payload(
        snapshot_id=snapshot_id,
        snapshot_revision=snapshot_revision,
        identity_registry_revision=identity_registry_revision,
        identity_registry_hash=identity_registry_hash,
        memberships=memberships,
        unresolved_entity_ids=unresolved_entity_ids,
    )
    return IdentitySnapshotAuthority(
        **payload, snapshot_hash=canonical_sha256(payload)
    )


def _lifecycle_revision_payload(
    *, candidate_ref: str, revision_id: str, lifecycle_state: str
) -> dict[str, object]:
    return {
        "schema_version": "l1-lifecycle-revision-v1",
        "candidate_ref": candidate_ref,
        "revision_id": revision_id,
        "lifecycle_state": lifecycle_state,
    }


class KnownLifecycleRevision(StrictModel):
    """Exact lifecycle authority record supplied for deterministic resolution."""

    schema_version: Literal["l1-lifecycle-revision-v1"] = (
        "l1-lifecycle-revision-v1"
    )
    candidate_ref: str = Field(min_length=1)
    revision_id: str = Field(min_length=1)
    lifecycle_state: Literal["active", "superseded", "conflicted", "retracted"]
    revision_hash: str = Field(pattern=_SHA256)

    @model_validator(mode="after")
    def validate_revision_hash(self) -> "KnownLifecycleRevision":
        payload = _lifecycle_revision_payload(
            candidate_ref=self.candidate_ref,
            revision_id=self.revision_id,
            lifecycle_state=self.lifecycle_state,
        )
        if self.revision_hash != canonical_sha256(payload):
            raise ValueError("lifecycle revision hash mismatch")
        return self


def make_known_lifecycle_revision(
    *, candidate_ref: str, revision_id: str, lifecycle_state: str
) -> KnownLifecycleRevision:
    payload = _lifecycle_revision_payload(
        candidate_ref=candidate_ref,
        revision_id=revision_id,
        lifecycle_state=lifecycle_state,
    )
    return KnownLifecycleRevision(
        **payload, revision_hash=canonical_sha256(payload)
    )


class AdmissionContext(StrictModel):
    """Explicit replay inputs for source, identity, lifecycle, and policy gates."""

    raw_artifacts: list[RawArtifactRevision] = Field(min_length=1)
    source_revisions: list[SourceRecordRevision] = Field(min_length=1)
    source_epistemics: list[SourceEpistemicBinding] = Field(min_length=1)
    identity_bindings: list[CanonicalEntityBinding] = Field(default_factory=list)
    identity_snapshot_authorities: list[IdentitySnapshotAuthority] = Field(
        default_factory=list
    )
    current_identity_snapshot_ids: list[str] = Field(default_factory=list)
    identity_registry_revision: str = Field(min_length=1)
    identity_registry_hash: str = Field(pattern=_SHA256)
    transaction_time: str | None = None
    known_lifecycle_revisions: list[KnownLifecycleRevision] = Field(
        default_factory=list
    )
    policy: AdmissionPolicy

    @model_validator(mode="after")
    def validate_context_keys(self) -> "AdmissionContext":
        checks = (
            ("raw artifact", [item.artifact_revision_id for item in self.raw_artifacts]),
            ("source revision", [item.source_revision_id for item in self.source_revisions]),
            (
                "source epistemic",
                [item.source_revision_id for item in self.source_epistemics],
            ),
            ("identity binding", [item.local_entity_id for item in self.identity_bindings]),
            (
                "identity snapshot authority",
                [item.snapshot_id for item in self.identity_snapshot_authorities],
            ),
            ("current identity snapshot", self.current_identity_snapshot_ids),
            (
                "lifecycle candidate reference",
                [item.candidate_ref for item in self.known_lifecycle_revisions],
            ),
            (
                "lifecycle revision",
                [item.revision_id for item in self.known_lifecycle_revisions],
            ),
        )
        for label, values in checks:
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate {label}")
        return self


class ProposedRevisionAction(StrictModel):
    """A request for a future transaction; it can never perform one itself."""

    action: Literal["create", "correction", "lifecycle_update", "none"]
    target_revisions: list[KnownLifecycleRevision] = Field(default_factory=list)
    automatic_write: Literal[False] = False

    @field_validator("automatic_write", mode="before")
    @classmethod
    def require_literal_false(cls, value: object) -> object:
        if value is not False:
            raise ValueError("automatic_write must be the boolean false literal")
        return value

    @model_validator(mode="after")
    def validate_action_shape(self) -> "ProposedRevisionAction":
        candidate_refs = [item.candidate_ref for item in self.target_revisions]
        if len(candidate_refs) != len(set(candidate_refs)):
            raise ValueError("duplicate proposed action target")
        if self.action == "none" and self.target_revisions:
            raise ValueError("none action cannot name targets")
        return self


def _decision_payload_without_hash(decision: "AdmissionDecision") -> dict[str, object]:
    payload = decision.model_dump(mode="json")
    payload.pop("decision_hash", None)
    return payload


class IdentitySnapshotReference(StrictModel):
    snapshot_id: str = Field(min_length=1)
    snapshot_revision: str = Field(min_length=1)
    snapshot_hash: str = Field(pattern=_SHA256)
    identity_registry_revision: str = Field(min_length=1)
    identity_registry_hash: str = Field(pattern=_SHA256)


class AdmissionDecision(StrictModel):
    """Replayable output with exact provenance bindings and no write capability."""

    schema_version: Literal["l1-admission-decision-v1"] = "l1-admission-decision-v1"
    status: Literal["accept", "reject", "abstain"]
    reason_codes: list[str] = Field(default_factory=list)
    source_candidate_hash: str = Field(pattern=_SHA256)
    linked_candidate_hash: str = Field(pattern=_SHA256)
    registry_id: str = Field(min_length=1)
    registry_version: str = Field(min_length=1)
    registry_revision: str = Field(min_length=1)
    registry_hash: str = Field(pattern=_SHA256)
    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    policy_hash: str = Field(pattern=_SHA256)
    admission_context_hash: str = Field(pattern=_SHA256)
    raw_artifact_revision_ids: list[str] = Field(default_factory=list)
    raw_artifact_content_hashes: list[str] = Field(default_factory=list)
    source_revision_ids: list[str] = Field(default_factory=list)
    source_revision_content_hashes: list[str] = Field(default_factory=list)
    evidence_bindings: list[str] = Field(default_factory=list)
    identity_snapshot_bindings: list[IdentitySnapshotReference] = Field(
        default_factory=list
    )
    identity_registry_revision: str = Field(min_length=1)
    identity_registry_hash: str = Field(pattern=_SHA256)
    transaction_time: str | None = None
    proposed_action: ProposedRevisionAction
    automatic_write_counts: dict[
        Literal[
            "l1",
            "l2",
            "identity",
            "membership",
            "closure",
            "revision",
            "snapshot",
            "aggregate",
        ],
        Literal[0],
    ] = Field(default_factory=lambda: dict(_ZERO_WRITES))
    decision_hash: str = Field(pattern=_SHA256)

    @field_validator("automatic_write_counts", mode="before")
    @classmethod
    def require_literal_zero_counts(cls, value: object) -> object:
        if isinstance(value, dict) and any(
            type(item) is not int or item != 0 for item in value.values()
        ):
            raise ValueError("automatic write counts must use integer zero literals")
        return value

    @model_validator(mode="after")
    def validate_decision(self) -> "AdmissionDecision":
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("duplicate admission reason")
        if self.reason_codes != _normalize_reasons(self.reason_codes):
            raise ValueError("admission reasons are not in canonical gate order")
        if self.status == "accept" and self.reason_codes:
            raise ValueError("accepted decision cannot contain reasons")
        if self.status != "accept" and not self.reason_codes:
            raise ValueError("non-accepted decision requires a reason")
        if self.status == "accept" and self.proposed_action.action == "none":
            raise ValueError("accepted decision requires a proposed action")
        if self.status != "accept" and self.proposed_action.action != "none":
            raise ValueError("non-accepted decision cannot propose a revision")
        if self.automatic_write_counts != _ZERO_WRITES:
            raise ValueError("automatic write counts must all be zero")
        snapshot_ids = [item.snapshot_id for item in self.identity_snapshot_bindings]
        if len(snapshot_ids) != len(set(snapshot_ids)):
            raise ValueError("duplicate identity snapshot decision binding")
        if len(self.raw_artifact_revision_ids) != len(self.raw_artifact_content_hashes):
            raise ValueError("raw artifact IDs and hashes differ in length")
        if len(self.source_revision_ids) != len(self.source_revision_content_hashes):
            raise ValueError("source revision IDs and hashes differ in length")
        expected_hash = canonical_sha256(_decision_payload_without_hash(self))
        if self.decision_hash != expected_hash:
            raise ValueError("decision hash does not match decision content")
        return self


def _policy_payload(policy: AdmissionPolicy) -> dict[str, object]:
    payload = policy.model_dump(mode="json")
    for key in (
        "allow_modalities",
        "allow_source_statuses",
        "allow_polarities",
        "allow_evidence_speakers",
    ):
        payload[key] = sorted(payload[key])
    return payload


def _admission_context_payload(context: AdmissionContext) -> dict[str, object]:
    payload = context.model_dump(mode="json")
    payload["raw_artifacts"] = sorted(
        payload["raw_artifacts"], key=lambda item: str(item["artifact_revision_id"])
    )
    payload["source_revisions"] = sorted(
        payload["source_revisions"], key=lambda item: str(item["source_revision_id"])
    )
    payload["source_epistemics"] = sorted(
        payload["source_epistemics"],
        key=lambda item: str(item["source_revision_id"]),
    )
    payload["identity_bindings"] = sorted(
        [
            {
                **item,
                "concept_type_ids": sorted(item["concept_type_ids"]),
            }
            for item in payload["identity_bindings"]
        ],
        key=lambda item: str(item["local_entity_id"]),
    )
    payload["identity_snapshot_authorities"] = sorted(
        [
            {
                "schema_version": item["schema_version"],
                **_identity_snapshot_payload(
                    snapshot_id=str(item["snapshot_id"]),
                    snapshot_revision=str(item["snapshot_revision"]),
                    identity_registry_revision=str(
                        item["identity_registry_revision"]
                    ),
                    identity_registry_hash=str(item["identity_registry_hash"]),
                    memberships=[
                        CanonicalIdentityMembership.model_validate(membership)
                        for membership in item["memberships"]
                    ],
                    unresolved_entity_ids=list(item["unresolved_entity_ids"]),
                ),
                "snapshot_hash": item["snapshot_hash"],
            }
            for item in payload["identity_snapshot_authorities"]
        ],
        key=lambda item: str(item["snapshot_id"]),
    )
    payload["current_identity_snapshot_ids"] = sorted(
        payload["current_identity_snapshot_ids"]
    )
    payload["known_lifecycle_revisions"] = sorted(
        payload["known_lifecycle_revisions"],
        key=lambda item: str(item["candidate_ref"]),
    )
    payload["policy"] = _policy_payload(context.policy)
    return payload


def _linked_payload_without_hash(linked: LinkedL1Candidate) -> dict[str, object]:
    payload = linked.model_dump(mode="json")
    payload.pop("linked_candidate_hash", None)
    return payload


def _add_once(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)


def _looks_referential(surface: str) -> bool:
    normalized = " ".join(surface.casefold().split())
    return normalized.startswith(("this ", "that ", "the ")) or " cup" in normalized


def _decision(
    *,
    status: Literal["accept", "reject", "abstain"],
    reasons: list[str],
    linked: LinkedL1Candidate,
    registry: OntologyRegistry,
    context: AdmissionContext,
    action: Literal["create", "correction", "lifecycle_update", "none"],
    targets: list[KnownLifecycleRevision] | None = None,
) -> AdmissionDecision:
    reasons = _normalize_reasons(reasons)
    snapshot_references = [
        IdentitySnapshotReference(
            snapshot_id=authority.snapshot_id,
            snapshot_revision=authority.snapshot_revision,
            snapshot_hash=authority.snapshot_hash,
            identity_registry_revision=authority.identity_registry_revision,
            identity_registry_hash=authority.identity_registry_hash,
        )
        for authority in sorted(
            context.identity_snapshot_authorities,
            key=lambda item: item.snapshot_id,
        )
    ]
    payload: dict[str, object] = {
        "schema_version": "l1-admission-decision-v1",
        "status": status,
        "reason_codes": reasons,
        "source_candidate_hash": linked.source_candidate_hash,
        "linked_candidate_hash": linked.linked_candidate_hash,
        "registry_id": registry.registry_id,
        "registry_version": registry.version,
        "registry_revision": registry.revision,
        "registry_hash": registry.registry_hash,
        "policy_id": context.policy.policy_id,
        "policy_version": context.policy.policy_version,
        "policy_hash": canonical_sha256(_policy_payload(context.policy)),
        "admission_context_hash": canonical_sha256(
            _admission_context_payload(context)
        ),
        "raw_artifact_revision_ids": [
            item.artifact_revision_id
            for item in sorted(context.raw_artifacts, key=lambda item: item.artifact_revision_id)
        ],
        "raw_artifact_content_hashes": [
            item.content_sha256
            for item in sorted(context.raw_artifacts, key=lambda item: item.artifact_revision_id)
        ],
        "source_revision_ids": [
            item.source_revision_id
            for item in sorted(context.source_revisions, key=lambda item: item.source_revision_id)
        ],
        "source_revision_content_hashes": [
            item.content_sha256
            for item in sorted(context.source_revisions, key=lambda item: item.source_revision_id)
        ],
        "evidence_bindings": sorted(
            binding.evidence_id for binding in linked.typed_candidate.evidence_bindings
        ),
        "identity_snapshot_bindings": [
            item.model_dump(mode="json") for item in snapshot_references
        ],
        "identity_registry_revision": context.identity_registry_revision,
        "identity_registry_hash": context.identity_registry_hash,
        "transaction_time": context.transaction_time,
        "proposed_action": ProposedRevisionAction(
            action=action, target_revisions=targets or []
        ).model_dump(mode="json"),
        "automatic_write_counts": dict(_ZERO_WRITES),
    }
    serialized = dict(payload)
    serialized["decision_hash"] = canonical_sha256(serialized)
    return AdmissionDecision.model_validate(serialized)


def _has_valid_evidence_closure(
    linked: LinkedL1Candidate, context: AdmissionContext, reasons: list[str]
) -> None:
    candidate = linked.typed_candidate
    bound_ids = [binding.evidence_id for binding in candidate.evidence_bindings]
    derivation_ids = candidate.derivation.evidence_ids
    span_ids = [span.evidence_id for span in linked.evidence_spans]
    if set(derivation_ids) != set(bound_ids) or set(span_ids) != set(bound_ids):
        _add_once(reasons, "evidence_binding_closure_mismatch")

    source_by_id = {
        source.source_revision_id: source for source in context.source_revisions
    }
    expected_source_ids = {span.source_revision_id for span in linked.evidence_spans}
    actual_source_ids = set(source_by_id)
    if actual_source_ids - expected_source_ids:
        _add_once(reasons, "unexpected_source_revision")
    if expected_source_ids - actual_source_ids:
        _add_once(reasons, "evidence_source_revision_missing")

    artifact_by_id = {
        artifact.artifact_revision_id: artifact for artifact in context.raw_artifacts
    }
    expected_artifact_ids = {
        source_by_id[source_id].artifact_revision_id
        for source_id in expected_source_ids.intersection(actual_source_ids)
    }
    actual_artifact_ids = set(artifact_by_id)
    if actual_artifact_ids - expected_artifact_ids:
        _add_once(reasons, "unexpected_raw_artifact_revision")
    if expected_artifact_ids - actual_artifact_ids:
        _add_once(reasons, "source_artifact_revision_missing")

    for artifact in context.raw_artifacts:
        identity = {
            "source_id": artifact.source_id,
            "frozen_identity": artifact.frozen_identity,
            "official_url": artifact.official_url,
            "local_path": artifact.local_path,
            "reader": artifact.reader,
            "size_bytes": artifact.size_bytes,
            "content_sha256": artifact.content_sha256,
        }
        expected_id = f"artifact-revision-{canonical_sha256(identity)[:24]}"
        if artifact.artifact_revision_id != expected_id:
            _add_once(reasons, "raw_artifact_revision_identity_mismatch")
        path = Path(artifact.local_path)
        descriptor: int | None = None
        try:
            path_opened = path.lstat()
            if not stat.S_ISREG(path_opened.st_mode) or not (
                stat.S_IMODE(path_opened.st_mode) & 0o444
            ):
                _add_once(reasons, "raw_artifact_unavailable")
                continue
            descriptor = os.open(
                path,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            )
            opened = os.fstat(descriptor)
            if (path_opened.st_dev, path_opened.st_ino) != (
                opened.st_dev,
                opened.st_ino,
            ):
                _add_once(reasons, "raw_artifact_unavailable")
                continue
            if not stat.S_ISREG(opened.st_mode) or not (
                stat.S_IMODE(opened.st_mode) & 0o444
            ):
                _add_once(reasons, "raw_artifact_unavailable")
                continue
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                content = stream.read()
            rechecked = os.fstat(descriptor)
            path_rechecked = path.lstat()
        except OSError:
            _add_once(reasons, "raw_artifact_unavailable")
            continue
        finally:
            if descriptor is not None:
                os.close(descriptor)
        opened_identity = (opened.st_dev, opened.st_ino, opened.st_size)
        if opened_identity != (
            rechecked.st_dev,
            rechecked.st_ino,
            rechecked.st_size,
        ) or opened_identity != (
            path_rechecked.st_dev,
            path_rechecked.st_ino,
            path_rechecked.st_size,
        ):
            _add_once(reasons, "raw_artifact_unavailable")
            continue
        if len(content) != artifact.size_bytes:
            _add_once(reasons, "raw_artifact_size_mismatch")
        if hashlib.sha256(content).hexdigest() != artifact.content_sha256:
            _add_once(reasons, "raw_artifact_content_hash_mismatch")

    for source in context.source_revisions:
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
        expected_id = f"source-revision-{canonical_sha256(identity)[:24]}"
        if source.source_revision_id != expected_id:
            _add_once(reasons, "source_revision_identity_mismatch")
        if hashlib.sha256(source.text.encode("utf-8")).hexdigest() != source.content_sha256:
            _add_once(reasons, "source_content_hash_mismatch")

    epistemic_by_source = {
        item.source_revision_id: item for item in context.source_epistemics
    }
    if set(epistemic_by_source) != expected_source_ids:
        _add_once(reasons, "source_epistemic_closure_mismatch")
    binding_by_evidence = {
        binding.evidence_id: binding for binding in candidate.evidence_bindings
    }
    speaker_statuses = {
        "user": {"user_reported", "inferred"},
        "assistant": {"agent_generated", "inferred"},
        "tool": {"tool_observed", "inferred"},
    }
    for span in linked.evidence_spans:
        if hashlib.sha256(span.text.encode("utf-8")).hexdigest() != span.quote_sha256:
            _add_once(reasons, "evidence_quote_hash_mismatch")
        source = source_by_id.get(span.source_revision_id)
        if source is None:
            _add_once(reasons, "evidence_source_revision_missing")
            continue
        if source.artifact_revision_id not in artifact_by_id:
            _add_once(reasons, "source_artifact_revision_missing")
        if span.turn_id != source.turn_id or span.session_id != source.session_id:
            _add_once(reasons, "evidence_source_context_mismatch")
        if span.char_end > len(source.text):
            _add_once(reasons, "evidence_source_slice_out_of_range")
        elif source.text[span.char_start : span.char_end] != span.text:
            _add_once(reasons, "evidence_source_slice_mismatch")
        epistemic = epistemic_by_source.get(span.source_revision_id)
        binding = binding_by_evidence.get(span.evidence_id)
        if epistemic is None or binding is None:
            continue
        if epistemic.speaker != binding.speaker:
            _add_once(reasons, "evidence_epistemic_speaker_mismatch")
        if epistemic.source_status not in speaker_statuses[binding.speaker]:
            _add_once(reasons, "speaker_source_status_incompatible")

    link_evidence_ids = {
        evidence.evidence_id
        for entity in linked.entity_links
        for evidence in entity.concept.evidence
    } | {evidence.evidence_id for evidence in linked.predicate_link.evidence}
    if not link_evidence_ids.issubset(set(span_ids)):
        _add_once(reasons, "link_evidence_unbound")
    allowed_speakers = set(context.policy.allow_evidence_speakers)
    if any(binding.speaker not in allowed_speakers for binding in candidate.evidence_bindings):
        _add_once(reasons, "evidence_speaker_not_authorized")


def _validate_hashes(
    linked: LinkedL1Candidate,
    registry: OntologyRegistry,
    context: AdmissionContext,
    reasons: list[str],
) -> None:
    candidate_bytes = canonical_json_bytes(linked.typed_candidate)
    if linked.typed_candidate_canonical_bytes != candidate_bytes:
        _add_once(reasons, "source_candidate_bytes_mismatch")
    if linked.source_candidate_hash != hashlib.sha256(candidate_bytes).hexdigest():
        _add_once(reasons, "source_candidate_hash_mismatch")

    registry_bytes = ontology_registry_canonical_bytes(registry)
    registry_hash = hashlib.sha256(registry_bytes).hexdigest()
    if registry.registry_hash != registry_hash:
        _add_once(reasons, "registry_hash_mismatch")
    if (
        linked.registry_id != registry.registry_id
        or linked.registry_version != registry.version
        or linked.registry_revision != registry.revision
        or linked.registry_hash != registry.registry_hash
        or linked.registry_canonical_bytes != registry_bytes
    ):
        _add_once(reasons, "linked_registry_binding_mismatch")
    if linked.linked_candidate_hash != canonical_sha256(_linked_payload_without_hash(linked)):
        _add_once(reasons, "linked_candidate_hash_mismatch")
    try:
        replayed = link_l1_candidate(
            linked.typed_candidate,
            registry,
            linked.evidence_spans,
            context.identity_bindings,
        )
    except (TypeError, ValueError):
        _add_once(reasons, "deterministic_link_replay_failed")
    else:
        if replayed != linked:
            _add_once(reasons, "deterministic_link_replay_mismatch")


def _validate_predicate_and_types(
    linked: LinkedL1Candidate, registry: OntologyRegistry, reasons: list[str]
) -> None:
    candidate = linked.typed_candidate
    predicate_link = linked.predicate_link
    if (
        predicate_link.predicate_surface != candidate.predicate.surface
        or predicate_link.predicate_sense != candidate.predicate.sense
        or predicate_link.canonical_operator != candidate.predicate.canonical_operator
    ):
        _add_once(reasons, "predicate_link_mismatch")

    concepts = {concept.concept_id for concept in registry.concepts}
    links_by_id = {link.local_entity_id: link for link in linked.entity_links}
    expected_rule_ids: set[str] = set()
    for role in candidate.roles:
        matches = [
            rule
            for rule in registry.predicate_role_constraints
            if rule.predicate_surface == candidate.predicate.surface
            and rule.predicate_sense == candidate.predicate.sense
            and rule.canonical_operator == candidate.predicate.canonical_operator
            and rule.role_name == role.role_name
        ]
        if not matches:
            _add_once(reasons, "predicate_role_rule_missing")
            continue
        expected_rule_ids.update(rule.rule_id for rule in matches)
        link = links_by_id.get(role.local_entity_id)
        if link is None:
            _add_once(reasons, "entity_link_missing")
            continue
        selected = link.selected_concept_ids
        if any(concept_id not in concepts for concept_id in selected):
            _add_once(reasons, "unknown_local_concept")
            continue
        if selected and not all(
            any(
                is_subtype(registry, concept_id, allowed)
                for rule in matches
                for allowed in rule.allowed_concept_ids
            )
            for concept_id in selected
        ):
            _add_once(reasons, "predicate_role_type_incompatible")
    if predicate_link.matched_rule_ids != sorted(expected_rule_ids):
        _add_once(reasons, "predicate_rule_binding_mismatch")


def _validate_identity_and_unresolved(
    linked: LinkedL1Candidate, registry: OntologyRegistry, context: AdmissionContext, reasons: list[str]
) -> None:
    supplied = {binding.local_entity_id: binding for binding in context.identity_bindings}
    authorities = {
        authority.snapshot_id: authority
        for authority in context.identity_snapshot_authorities
    }
    current_snapshot_ids = set(context.current_identity_snapshot_ids)
    known_concepts = {concept.concept_id for concept in registry.concepts}
    for entity in linked.entity_links:
        # A generic head noun must not erase an explicit unknown modifier.  A broad
        # lexical candidate can remain useful diagnostic context, but cannot admit.
        if "unknown" in entity.surface.casefold().split():
            _add_once(reasons, "ontology_extension_required")
            continue
        if entity.interpretation == "unresolved":
            if entity.concept.extension_proposal is not None:
                _add_once(reasons, "ontology_extension_required")
            elif _looks_referential(entity.surface) or entity.canonical_entity_binding is not None:
                _add_once(reasons, "identity_unresolved")
            else:
                _add_once(reasons, "ontology_link_unresolved")
            continue
        if not entity.selected_concept_ids:
            _add_once(reasons, "ontology_link_unresolved")
            continue
        if any(concept_id not in known_concepts for concept_id in entity.selected_concept_ids):
            _add_once(reasons, "unknown_local_concept")
        if entity.interpretation == "category":
            if entity.canonical_entity_id is not None or entity.canonical_entity_binding is not None:
                _add_once(reasons, "category_identity_shape_invalid")
            continue

        binding = entity.canonical_entity_binding
        if (
            binding is None
            or entity.canonical_entity_id != binding.canonical_entity_id
            or binding.identity_status != "resolved"
        ):
            _add_once(reasons, "identity_unresolved")
            continue
        if supplied.get(entity.local_entity_id) != binding:
            _add_once(reasons, "identity_binding_mismatch")
        if (
            binding.identity_registry_revision != context.identity_registry_revision
            or binding.identity_registry_hash != context.identity_registry_hash
        ):
            _add_once(reasons, "identity_registry_revision_mismatch")
        if not set(entity.selected_concept_ids).issubset(set(binding.concept_type_ids)):
            _add_once(reasons, "identity_type_incompatible")
        authority = authorities.get(binding.identity_snapshot_id)
        if authority is None or authority.snapshot_id not in current_snapshot_ids:
            _add_once(reasons, "identity_authority_unavailable")
            continue
        authority_payload = _identity_snapshot_payload(
            snapshot_id=authority.snapshot_id,
            snapshot_revision=authority.snapshot_revision,
            identity_registry_revision=authority.identity_registry_revision,
            identity_registry_hash=authority.identity_registry_hash,
            memberships=authority.memberships,
            unresolved_entity_ids=authority.unresolved_entity_ids,
        )
        if canonical_sha256(authority_payload) != authority.snapshot_hash:
            _add_once(reasons, "identity_snapshot_hash_mismatch")
        if (
            binding.identity_snapshot_revision != authority.snapshot_revision
            or binding.identity_snapshot_hash != authority.snapshot_hash
        ):
            _add_once(reasons, "identity_snapshot_binding_mismatch")
        if (
            authority.identity_registry_revision != context.identity_registry_revision
            or authority.identity_registry_hash != context.identity_registry_hash
            or binding.identity_registry_revision
            != authority.identity_registry_revision
            or binding.identity_registry_hash != authority.identity_registry_hash
        ):
            _add_once(reasons, "identity_registry_binding_mismatch")
        if entity.canonical_entity_id in set(authority.unresolved_entity_ids):
            _add_once(reasons, "identity_unresolved")
            continue
        membership = next(
            (
                item
                for item in authority.memberships
                if item.canonical_entity_id == entity.canonical_entity_id
            ),
            None,
        )
        if membership is None:
            _add_once(reasons, "identity_membership_missing")
            continue
        if any(
            not any(
                is_subtype(registry, authority_type, declared_type)
                for authority_type in membership.concept_type_ids
            )
            for declared_type in binding.concept_type_ids
        ) or any(
            not any(
                is_subtype(registry, authority_type, selected_type)
                for authority_type in membership.concept_type_ids
            )
            for selected_type in entity.selected_concept_ids
        ):
            _add_once(reasons, "identity_membership_type_incompatible")


def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _validate_lifecycle_and_policy(
    linked: LinkedL1Candidate, context: AdmissionContext, reasons: list[str]
) -> None:
    candidate = linked.typed_candidate
    policy = context.policy
    if candidate.modality == "hypothetical":
        _add_once(reasons, "hypothetical_modality")
    elif candidate.modality not in policy.allow_modalities:
        _add_once(reasons, "modality_not_authorized")
    if candidate.polarity not in policy.allow_polarities:
        _add_once(reasons, "polarity_not_authorized")
    source_statuses = [item.source_status for item in context.source_epistemics]
    if any(status not in policy.allow_source_statuses for status in source_statuses):
        _add_once(reasons, "source_status_not_authorized")
    if "agent_generated" in source_statuses:
        _add_once(reasons, "source_status_not_authorized")
    if candidate.modality == "actual" and any(
        binding.speaker == "assistant" for binding in candidate.evidence_bindings
    ):
        _add_once(reasons, "source_status_not_authorized")
    if policy.require_transaction_time and not context.transaction_time:
        _add_once(reasons, "transaction_time_missing")
    elif context.transaction_time is not None:
        transaction_time = _parse_timestamp(context.transaction_time)
        if transaction_time is None:
            _add_once(reasons, "transaction_time_invalid")
        source_times = [
            _parse_timestamp(source.transaction_time)
            for source in context.source_revisions
        ]
        if any(item is None for item in source_times):
            _add_once(reasons, "source_transaction_time_invalid")
        elif transaction_time is not None and any(
            transaction_time < source_time for source_time in source_times
        ):
            _add_once(reasons, "transaction_time_precedes_source")
    for time_value in (candidate.time.event_time, candidate.time.valid_time):
        if time_value is not None and _parse_timestamp(time_value) is None:
            _add_once(reasons, "time_binding_unresolved")

    lifecycle = candidate.lifecycle
    refs = [
        *lifecycle.replaces_candidate_refs,
        *lifecycle.supersedes_candidate_refs,
        *lifecycle.conflicts_with_candidate_refs,
    ]
    if lifecycle.lifecycle == "superseded":
        if not lifecycle.replacement_candidate_ref:
            _add_once(reasons, "lifecycle_target_missing")
        else:
            refs.append(lifecycle.replacement_candidate_ref)
    if lifecycle.lifecycle == "conflicted" and not lifecycle.conflicts_with_candidate_refs:
        _add_once(reasons, "lifecycle_target_missing")
    known = {
        revision.candidate_ref: revision
        for revision in context.known_lifecycle_revisions
    }
    for revision in context.known_lifecycle_revisions:
        payload = _lifecycle_revision_payload(
            candidate_ref=revision.candidate_ref,
            revision_id=revision.revision_id,
            lifecycle_state=revision.lifecycle_state,
        )
        if revision.revision_hash != canonical_sha256(payload):
            _add_once(reasons, "lifecycle_revision_hash_mismatch")
    if any(not reference or reference not in known for reference in refs):
        _add_once(reasons, "lifecycle_target_unresolved")
    if any(
        known[reference].lifecycle_state != "active"
        for reference in refs
        if reference in known
    ):
        _add_once(reasons, "lifecycle_target_not_active")


def _decision_action(
    linked: LinkedL1Candidate, context: AdmissionContext
) -> tuple[
    Literal["create", "correction", "lifecycle_update"],
    list[KnownLifecycleRevision],
]:
    lifecycle = linked.typed_candidate.lifecycle
    targets = sorted(
        set(
            [
                *lifecycle.replaces_candidate_refs,
                *lifecycle.supersedes_candidate_refs,
                *lifecycle.conflicts_with_candidate_refs,
                *(
                    [lifecycle.replacement_candidate_ref]
                    if lifecycle.replacement_candidate_ref is not None
                    else []
                ),
            ]
        )
    )
    known = {
        revision.candidate_ref: revision
        for revision in context.known_lifecycle_revisions
    }
    target_revisions = [known[target] for target in targets if target in known]
    if lifecycle.replaces_candidate_refs:
        return "correction", target_revisions
    if lifecycle.lifecycle != "active" or targets:
        return "lifecycle_update", target_revisions
    return "create", []


def admit_linked_l1(
    linked: LinkedL1Candidate,
    registry: OntologyRegistry,
    context: AdmissionContext,
) -> AdmissionDecision:
    """Return a deterministic fail-closed admission decision without writing state."""

    reject_reasons: list[str] = []
    abstain_reasons: list[str] = []
    _validate_hashes(linked, registry, context, reject_reasons)
    _has_valid_evidence_closure(linked, context, reject_reasons)
    _validate_predicate_and_types(linked, registry, reject_reasons)
    _validate_identity_and_unresolved(linked, registry, context, abstain_reasons)
    _validate_lifecycle_and_policy(linked, context, abstain_reasons)

    # Invalid source/registry/type/identity evidence is never recoverable by this layer.
    identity_rejects = {
        "identity_binding_mismatch",
        "identity_registry_revision_mismatch",
        "identity_type_incompatible",
        "identity_snapshot_hash_mismatch",
        "identity_snapshot_binding_mismatch",
        "identity_registry_binding_mismatch",
        "identity_membership_missing",
        "identity_membership_type_incompatible",
        "lifecycle_revision_hash_mismatch",
        "lifecycle_target_not_active",
    }
    for reason in list(abstain_reasons):
        if reason in identity_rejects:
            abstain_reasons.remove(reason)
            _add_once(reject_reasons, reason)
    policy_rejects = {
        "modality_not_authorized",
        "polarity_not_authorized",
        "source_status_not_authorized",
        "transaction_time_invalid",
        "source_transaction_time_invalid",
        "transaction_time_precedes_source",
    }
    for reason in list(abstain_reasons):
        if reason in policy_rejects:
            abstain_reasons.remove(reason)
            _add_once(reject_reasons, reason)

    if reject_reasons:
        return _decision(
            status="reject",
            reasons=reject_reasons,
            linked=linked,
            registry=registry,
            context=context,
            action="none",
        )
    if abstain_reasons:
        return _decision(
            status="abstain",
            reasons=abstain_reasons,
            linked=linked,
            registry=registry,
            context=context,
            action="none",
        )
    action, targets = _decision_action(linked, context)
    return _decision(
        status="accept",
        reasons=[],
        linked=linked,
        registry=registry,
        context=context,
        action=action,
        targets=targets,
    )


def _diagnostic_candidate(spec: dict[str, object]) -> TypedL1Candidate:
    evidence_id = str(spec["evidence_id"])
    entities = list(spec["entities"])
    roles = list(spec["roles"])
    return TypedL1Candidate(
        kind=str(spec["kind"]),
        predicate=TypedPredicate(
            surface=str(spec["predicate_surface"]),
            sense=str(spec["predicate_sense"]),
            canonical_operator=str(spec["canonical_operator"]),
        ),
        local_entities=[
            TypedLocalEntity(
                local_entity_id=f"entity-{index:02d}", surface=str(surface)
            )
            for index, surface in enumerate(entities, start=1)
        ],
        roles=[
            TypedRoleBinding(
                role=str(role),
                role_name=str(role),
                local_entity_id=f"entity-{int(entity_index):02d}",
            )
            for role, entity_index in roles
        ],
        modality=str(spec.get("modality", "actual")),
        polarity="positive",
        time=TypedTimeBinding(),
        derivation=TypedDerivationProvenance(
            method="explicit", evidence_ids=[evidence_id]
        ),
        evidence_bindings=[
            TypedEvidenceBinding(evidence_id=evidence_id, speaker="user")
        ],
        lifecycle=TypedLifecycleBinding(lifecycle="active"),
        operation_provenance=TypedOperationProvenance(),
    )


def _diagnostic_identity_binding(
    spec: dict[str, object],
) -> tuple[CanonicalEntityBinding | None, IdentitySnapshotAuthority | None]:
    if not spec.get("resolved_identity"):
        return None, None
    authority = make_identity_snapshot_authority(
        snapshot_id="identity-snapshot-dev-coffee-cup",
        snapshot_revision="identity-snapshot-dev-r1",
        identity_registry_revision="identity-dev-v1",
        identity_registry_hash="2" * 64,
        memberships=[
            CanonicalIdentityMembership(
                canonical_entity_id="entity:dev-coffee-cup",
                member_entity_ids=["entity:dev-coffee-cup"],
                concept_type_ids=["memory:CoffeeBeverage"],
            )
        ],
        unresolved_entity_ids=[],
    )
    binding = CanonicalEntityBinding(
        local_entity_id="entity-01",
        canonical_entity_id="entity:dev-coffee-cup",
        identity_status="resolved",
        identity_snapshot_id=authority.snapshot_id,
        identity_snapshot_revision=authority.snapshot_revision,
        identity_snapshot_hash=authority.snapshot_hash,
        identity_registry_revision="identity-dev-v1",
        identity_registry_hash=authority.identity_registry_hash,
        concept_type_ids=["memory:CoffeeBeverage"],
    )
    return binding, authority


def _run_diagnostic_case(
    spec: dict[str, object],
    registry: OntologyRegistry,
    raw_root: Path,
) -> tuple[dict[str, object], bool, bool, bool]:
    case_id = str(spec["case_id"])
    text = str(spec["text"])
    text_bytes = text.encode("utf-8")
    candidate = _diagnostic_candidate(spec)
    identity_binding, identity_authority = _diagnostic_identity_binding(spec)
    identity_bindings = [identity_binding] if identity_binding is not None else []
    identity_authorities = (
        [identity_authority] if identity_authority is not None else []
    )
    raw_path = raw_root / f"{case_id}.json"
    raw_path.write_bytes(text_bytes)
    raw = make_raw_artifact_revision(
        source_id=f"ontology-linking-{case_id}",
        frozen_identity="ontology-linking-dev-v1",
        official_url="https://example.invalid/ontology-linking-dev-v1",
        local_path=str(raw_path),
        reader="json",
        size_bytes=len(text_bytes),
        content_sha256=hashlib.sha256(text_bytes).hexdigest(),
    )
    source = make_source_record_revision(
        source_record_id=f"record:{case_id}",
        revision_number=1,
        previous_revision_id=None,
        artifact_revision_id=raw.artifact_revision_id,
        source_ref=f"record:{case_id}",
        turn_id=f"turn:{case_id}",
        session_id="session:ontology-linking-dev-v1",
        record_kind="message",
        text=text,
        resolver_id="ontology-linking-diagnostic",
        resolver_version="dev-v1",
        transaction_time="2026-07-29T00:00:00Z",
    )
    evidence_id = str(spec["evidence_id"])
    evidence = EvidenceSpanV2(
        evidence_id=evidence_id,
        source_revision_id=source.source_revision_id,
        turn_id=source.turn_id,
        session_id=source.session_id,
        char_start=0,
        char_end=len(text),
        text=text,
        quote_sha256=hashlib.sha256(text_bytes).hexdigest(),
    )
    linked = link_l1_candidate(
        candidate,
        registry,
        [evidence],
        canonical_entity_bindings=identity_bindings,
    )
    context = AdmissionContext(
        raw_artifacts=[raw],
        source_revisions=[source],
        source_epistemics=[
            SourceEpistemicBinding(
                source_revision_id=source.source_revision_id,
                source_status="user_reported",
                speaker="user",
            )
        ],
        identity_bindings=identity_bindings,
        identity_snapshot_authorities=identity_authorities,
        current_identity_snapshot_ids=[
            authority.snapshot_id for authority in identity_authorities
        ],
        identity_registry_revision="identity-dev-v1",
        identity_registry_hash="2" * 64,
        transaction_time="2026-07-29T00:00:00Z",
        known_lifecycle_revisions=[],
        policy=AdmissionPolicy(
            policy_id="policy-ontology-linking-dev-v1",
            policy_version="dev-v1",
            allow_modalities=["actual"],
            allow_source_statuses=["user_reported"],
        ),
    )
    decision = admit_linked_l1(linked, registry, context)
    selected = [
        concept_id
        for entity_link in linked.entity_links
        for concept_id in entity_link.selected_concept_ids
    ]
    expected_concepts = list(spec["expected_concepts"])
    exact_link = selected == expected_concepts
    expected_rule_ids = sorted(
        {
            rule.rule_id
            for role in candidate.roles
            for rule in registry.predicate_role_constraints
            if rule.predicate_surface == candidate.predicate.surface
            and rule.predicate_sense == candidate.predicate.sense
            and rule.canonical_operator == candidate.predicate.canonical_operator
            and rule.role_name == role.role_name
        }
    )
    sense_exact = (
        linked.predicate_link.predicate_surface == candidate.predicate.surface
        and linked.predicate_link.predicate_sense == candidate.predicate.sense
        and linked.predicate_link.canonical_operator
        == candidate.predicate.canonical_operator
        and linked.predicate_link.matched_rule_ids == expected_rule_ids
        and bool(expected_rule_ids)
    )
    evidence_exact = {
        (
            span.source_revision_id,
            span.evidence_id,
            next(
                binding.speaker
                for binding in candidate.evidence_bindings
                if binding.evidence_id == span.evidence_id
            ),
            span.char_start,
            span.char_end,
        )
        for span in linked.evidence_spans
    } == {(source.source_revision_id, evidence_id, "user", 0, len(text))}
    result = {
        "case_id": case_id,
        "expected_status": spec["expected_status"],
        "observed_status": decision.status,
        "selected_concept_ids": selected,
        "reason_codes": decision.reason_codes,
        "source_candidate_hash": linked.source_candidate_hash,
        "linked_candidate_hash": linked.linked_candidate_hash,
        "evidence_bindings": decision.evidence_bindings,
        "automatic_write_counts": decision.automatic_write_counts,
    }
    return result, exact_link, sense_exact, evidence_exact


def _diagnostic_specs() -> list[dict[str, object]]:
    preference = {
        "predicate_surface": "prefer",
        "predicate_sense": "preference_theme",
        "canonical_operator": "prefer",
        "kind": "preference",
        "entities": ["coffee"],
        "roles": [("theme", 1)],
        "expected_concepts": ["memory:CoffeeBeverage"],
    }
    drink = {
        "predicate_surface": "drink",
        "predicate_sense": "consume_beverage",
        "canonical_operator": "drink",
        "kind": "event",
        "roles": [("theme", 1)],
    }
    add = {
        "predicate_surface": "add",
        "predicate_sense": "add_ingredient",
        "canonical_operator": "add_ingredient",
        "kind": "event",
    }
    return [
        {
            **preference,
            "case_id": "prefer-coffee",
            "text": "I prefer coffee.",
            "evidence_id": "evidence:prefer-coffee",
            "expected_status": "accept",
        },
        {
            **drink,
            "case_id": "drink-coffee-cup",
            "text": "I drank this cup of coffee.",
            "evidence_id": "evidence:drink-coffee-cup",
            "entities": ["this cup of coffee"],
            "expected_concepts": ["memory:CoffeeBeverage"],
            "resolved_identity": True,
            "expected_status": "accept",
        },
        {
            **drink,
            "case_id": "drink-milk",
            "text": "I drink milk.",
            "evidence_id": "evidence:drink-milk",
            "entities": ["milk"],
            "expected_concepts": ["memory:MilkBeverage"],
            "expected_status": "accept",
        },
        {
            **add,
            "case_id": "add-milk-to-coffee",
            "text": "I add milk to coffee.",
            "evidence_id": "evidence:add-milk-to-coffee",
            "entities": ["milk", "coffee"],
            "roles": [("theme", 1), ("destination", 2)],
            "expected_concepts": [
                "memory:DairyIngredient",
                "memory:CoffeeBeverage",
            ],
            "expected_status": "accept",
        },
        {
            **preference,
            "case_id": "hypothetical-preference",
            "text": "I might prefer coffee.",
            "evidence_id": "evidence:hypothetical-preference",
            "modality": "hypothetical",
            "expected_status": "abstain",
        },
        {
            **drink,
            "case_id": "unknown-beverage",
            "text": "I drink mystery tonic.",
            "evidence_id": "evidence:unknown-beverage",
            "entities": ["mystery tonic"],
            "expected_concepts": [],
            "expected_status": "abstain",
        },
        {
            **add,
            "case_id": "same-surface-sense",
            "text": "I add milk.",
            "evidence_id": "evidence:same-surface-sense",
            "entities": ["milk"],
            "roles": [("theme", 1)],
            "expected_concepts": ["memory:DairyIngredient"],
            "expected_status": "accept",
        },
        {
            **drink,
            "case_id": "identity-unresolved",
            "text": "I drank this cup of coffee.",
            "evidence_id": "evidence:identity-unresolved",
            "entities": ["this cup of coffee"],
            "expected_concepts": ["memory:CoffeeBeverage"],
            "expected_status": "abstain",
        },
    ]


def run_dev_ontology_linking_assessment(output_root: Path) -> dict[str, object]:
    """Run the public synthetic dev-v1 diagnostic and write immutable outputs."""

    registry = build_diagnostic_ontology_registry()
    specs = _diagnostic_specs()
    raw_root = Path("/tmp/ke-memory-l1-diagnostic-dev-v1")
    raw_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    evaluated = [
        _run_diagnostic_case(spec, registry, raw_root) for spec in specs
    ]
    case_results = [item[0] for item in evaluated]
    expected_abstentions = [
        spec["expected_status"] == "abstain" for spec in specs
    ]
    observed_abstentions = [
        result["observed_status"] == "abstain" for result in case_results
    ]
    true_abstentions = sum(
        expected and observed
        for expected, observed in zip(expected_abstentions, observed_abstentions)
    )
    precision = true_abstentions / sum(observed_abstentions)
    recall = true_abstentions / sum(expected_abstentions)
    metrics = {
        "linking_exact_rate": sum(item[1] for item in evaluated) / len(evaluated),
        "hierarchy_consistency_rate": 1.0
        if all(
            any(
                is_subtype(registry, concept_id, parent_id)
                for parent_id in ("memory:Beverage", "memory:Ingredient")
            )
            for result in case_results
            for concept_id in result["selected_concept_ids"]
        )
        else 0.0,
        "sense_accuracy": sum(item[2] for item in evaluated) / len(evaluated),
        "decision_exact_rate": sum(
            result["observed_status"] == spec["expected_status"]
            for result, spec in zip(case_results, specs)
        )
        / len(specs),
        "abstention_precision": precision,
        "abstention_recall": recall,
        "abstention_f1": 2 * precision * recall / (precision + recall),
        "critical_false_admission_count": sum(
            spec["expected_status"] != "accept"
            and result["observed_status"] == "accept"
            for spec, result in zip(specs, case_results)
        ),
        "evidence_exact_rate": sum(item[3] for item in evaluated) / len(evaluated),
    }
    assessment: dict[str, object] = {
        "schema_version": "ontology-linking-assessment-dev-v1",
        "registry_hash": registry.registry_hash,
        "cases": [str(spec["case_id"]) for spec in specs],
        "case_results": case_results,
        "metrics": metrics,
        "automatic_write_counts": {
            key: sum(
                result["automatic_write_counts"][key] for result in case_results
            )
            for key in _ZERO_WRITES
        },
    }
    report = "\n".join(
        [
            "# L1 Ontology Linking Assessment dev-v1",
            "",
            "Public synthetic diagnostic; no pipeline or authority write is authorized.",
            "",
            *(f"- {name}: {value}" for name, value in metrics.items()),
            f"- automatic_write_counts: {assessment['automatic_write_counts']}",
            "",
        ]
    )
    output_root = Path(output_root)
    write_json_immutable(output_root / "assessment.json", assessment)
    write_text_immutable(output_root / "assessment-report.md", report)
    manifest = {
        "schema_version": "ontology-linking-assessment-manifest-v1",
        "assessment_sha256": hashlib.sha256(canonical_json_bytes(assessment)).hexdigest(),
        "report_sha256": hashlib.sha256(report.encode("utf-8")).hexdigest(),
        "registry_hash": registry.registry_hash,
        "case_ids": assessment["cases"],
    }
    write_json_immutable(output_root / "manifest.json", manifest)
    return assessment


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run the independent L1 ontology linking diagnostic"
    )
    parser.add_argument("--output-root", type=Path, required=True)
    arguments = parser.parse_args()
    run_dev_ontology_linking_assessment(arguments.output_root)
