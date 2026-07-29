from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .io import canonical_json_bytes, load_json, sha256_file, write_json_immutable
from .typed_extractor_fresh_v2_prereg import L1_FAMILIES, L2_FAMILIES, _input_paths
from .typed_extractor_l1 import (
    L1AuthorityCase,
    L1AuthorityPayload,
    L1Decision,
    L1GoldItem,
    L1GoldPayload,
    L1Manifest,
    L1PublicCase,
    L1PublicPayload,
    L1SourceCase,
    L1SourceConfig,
    PublicEvidenceSpan,
    PublicUntypedCandidate,
    TypedConditionBinding,
    TypedDerivationProvenance,
    TypedEvidenceBinding,
    TypedL1Candidate,
    TypedLifecycleBinding,
    TypedLocalEntity,
    TypedOperationProvenance,
    TypedPredicate,
    TypedRoleBinding,
    TypedScopeBinding,
    TypedTimeBinding,
)
from .typed_extractor_l2 import (
    L2AuthorityCase,
    L2AuthorityPayload,
    L2Decision,
    L2GoldItem,
    L2GoldPayload,
    L2Manifest,
    L2PublicCase,
    L2PublicPayload,
    L2PublicTurn,
    L2SourceCase,
    L2SourceConfig,
    TypedL1SupportCandidate,
    TypedL2Abstraction,
    TypedL2Candidate,
    TypedL2Closure,
    TypedL2StructuredClaim,
)


DATASET_ID = "typed-extractor-v2-fresh-hidden-v2"
NAMESPACE = "typed-extractor-fresh-hidden-v2-authored:2026-07-28"
PREREGISTRATION_SHA256 = (
    "1455bb7d5bb35b61809c78180ebf766573c1561e39bbeddda4a80f939a893760"
)
PREREGISTRATION_SCHEMA = "typed-extractor-fresh-v2-preregistration-v2"
RECEIPT_NAME = "authoring-implementation-receipt.json"
SUPERSESSION_RECEIPT_NAME = "authoring-implementation-receipt-v2.json"
SUPERSEDED_RECEIPT_SHA256 = (
    "4bb2575d985126dfbd91d01a3111d3f4acb2ebe57c3bfd62b1d60ee847d7314d"
)
SUPERSESSION_REASON = "post_freeze_review_primary_literal_binding_repair"
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
TEST_RELATIVE_PATH = Path(
    "tests/natural_memory_benchmark/test_typed_extractor_fresh_v2_authoring.py"
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


L1Family = Literal[
    "explicit_event_roles",
    "condition_scope",
    "modality_time",
    "lifecycle_revision",
    "derivation_epistemic",
    "abstention_no_memory_controls",
]
L2Family = Literal[
    "coreference_task_composition",
    "preference_state_aggregation",
    "lifecycle_supersession",
    "multi_evidence_closure",
    "abstraction_structured_claim_boundary",
    "abstention_unresolved_controls",
]


class L1Blueprint(StrictModel):
    blueprint_id: str = Field(pattern=r"^fresh-v2-l1-[a-z0-9_-]+-[0-9]{2}$")
    family: L1Family
    ordinal: int = Field(ge=1, le=4)
    private_case_id: str = Field(min_length=1)
    knowledge_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    source_turn: dict[Literal["user", "agent"], str]
    untyped_candidate: PublicUntypedCandidate
    expected_decision: L1Decision
    expected_typed_candidate: TypedL1Candidate | None = None
    unresolved_required_fields: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_blueprint(self) -> "L1Blueprint":
        if set(self.source_turn) != {"user", "agent"}:
            raise ValueError("L1 source turn must contain user and agent")
        emits = self.expected_decision == "emit_l1"
        if emits != (self.expected_typed_candidate is not None):
            raise ValueError("L1 blueprint decision/candidate mismatch")
        if (
            self.expected_decision == "abstain"
            and not self.unresolved_required_fields
        ):
            raise ValueError("L1 abstention requires unresolved fields")
        return self


class L2BlueprintTurn(StrictModel):
    private_turn_id: str = Field(min_length=1)
    source_turn_ref: str = Field(pattern=r"^turn-[0-9a-f]{16}$")
    turn_index: int = Field(ge=0)
    user: str = Field(min_length=1)
    agent: str = Field(min_length=1)


class L2Blueprint(StrictModel):
    blueprint_id: str = Field(pattern=r"^fresh-v2-l2-[a-z0-9_-]+-[0-9]{2}$")
    family: L2Family
    ordinal: int = Field(ge=1, le=2)
    private_case_id: str = Field(min_length=1)
    knowledge_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    private_session_id: str = Field(min_length=1)
    source_session_ref: str = Field(pattern=r"^session-[0-9a-f]{16}$")
    source_turns: tuple[L2BlueprintTurn, ...] = Field(min_length=2)
    untyped_candidate: PublicUntypedCandidate
    typed_l1_support_pack: tuple[TypedL1SupportCandidate, ...] = Field(
        min_length=2
    )
    expected_decision: L2Decision
    expected_typed_candidate: TypedL2Candidate | None = None
    unresolved_required_fields: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_blueprint(self) -> "L2Blueprint":
        emits = self.expected_decision == "emit_l2"
        if emits != (self.expected_typed_candidate is not None):
            raise ValueError("L2 blueprint decision/candidate mismatch")
        if not emits and not self.unresolved_required_fields:
            raise ValueError("L2 abstention requires unresolved fields")
        indexes = [turn.turn_index for turn in self.source_turns]
        if indexes != list(range(len(indexes))):
            raise ValueError("L2 turn indexes must be contiguous and ordered")
        return self


class L2SupportSemantic(StrictModel):
    kind: Literal["event", "state", "preference", "task", "attribute"]
    predicate_surface: str = Field(min_length=1)
    sense: str = Field(min_length=1)
    operator: str = Field(min_length=1)
    roles: tuple[tuple[str, str, str], ...] = Field(min_length=1)
    modality: str = "actual"
    polarity: str = "positive"
    event_time: str | None = None
    valid_time: str | None = None


class AuthoringInventory(StrictModel):
    input_sha256: dict[str, str]
    private_or_public_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    normalized_source_texts: tuple[str, ...]
    semantic_signatures: tuple[str, ...]


class FreshV2L1Layer(StrictModel):
    blueprints: tuple[L1Blueprint, ...]
    source: L1SourceConfig
    public: L1PublicPayload
    authority: L1AuthorityPayload
    gold: L1GoldPayload
    manifest: L1Manifest


class FreshV2L2Layer(StrictModel):
    blueprints: tuple[L2Blueprint, ...]
    source: L2SourceConfig
    public: L2PublicPayload
    authority: L2AuthorityPayload
    gold: L2GoldPayload
    manifest: L2Manifest


class FreshV2AuthoringBundle(StrictModel):
    schema_version: Literal[
        "typed-extractor-fresh-v2-authoring-bundle-v1"
    ] = "typed-extractor-fresh-v2-authoring-bundle-v1"
    dataset_id: Literal[DATASET_ID] = DATASET_ID
    namespace: Literal[NAMESPACE] = NAMESPACE
    preregistration_sha256: Literal[PREREGISTRATION_SHA256] = (
        PREREGISTRATION_SHA256
    )
    l1: FreshV2L1Layer
    l2: FreshV2L2Layer
    prior_inventory: AuthoringInventory
    current_inventory: AuthoringInventory


class AuthoringReceipt(StrictModel):
    schema_version: Literal[
        "typed-extractor-fresh-v2-authoring-receipt-v1"
    ] = "typed-extractor-fresh-v2-authoring-receipt-v1"
    status: Literal["frozen"] = "frozen"
    evaluation_id: Literal[DATASET_ID] = DATASET_ID
    namespace: Literal[NAMESPACE] = NAMESPACE
    preregistration_path: str = Field(min_length=1)
    preregistration_schema: Literal[PREREGISTRATION_SCHEMA] = (
        PREREGISTRATION_SCHEMA
    )
    preregistration_sha256: Literal[PREREGISTRATION_SHA256] = (
        PREREGISTRATION_SHA256
    )
    preregistration_mode: Literal["0444"] = "0444"
    formal_evaluation_root: str = Field(min_length=1)
    receipt_time: str
    receipt_time_source: Literal["caller_supplied_untrusted_utc_label"] = (
        "caller_supplied_untrusted_utc_label"
    )
    chronology_evidence: Literal["filesystem-presence-plus-sha256"] = (
        "filesystem-presence-plus-sha256"
    )
    trusted_timestamp_authority: Literal[False] = False
    code_sha256: dict[str, str]
    dependency_sha256: dict[str, str]
    blueprint_manifest_sha256: dict[str, str]
    family_counts: dict[str, dict[str, int]]
    prior_input_sha256: dict[str, str]
    formal_evaluation_root_absent: Literal[True] = True
    hidden_artifact_count: Literal[0] = 0
    model_request_count: Literal[0] = 0
    automatic_write_counts: dict[str, int]
    pipeline_integration_authorized: Literal[False] = False
    longmemeval_status: Literal["structured_l2_identity_unresolved"] = (
        "structured_l2_identity_unresolved"
    )

    @field_validator("receipt_time")
    @classmethod
    def validate_receipt_time(cls, value: str) -> str:
        try:
            parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError as exc:
            raise ValueError("receipt_time must be a valid UTC timestamp") from exc
        if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
            raise ValueError("receipt_time must be a valid UTC timestamp")
        return value

    @model_validator(mode="after")
    def validate_exact_contract(self) -> "AuthoringReceipt":
        if self.family_counts != {"l1": L1_FAMILIES, "l2": L2_FAMILIES}:
            raise ValueError("authoring receipt family counts drift")
        expected_writes = {
            "aggregate": 0,
            "closure": 0,
            "identity": 0,
            "l1": 0,
            "l2": 0,
            "membership": 0,
            "revision": 0,
            "snapshot": 0,
            "source_revision": 0,
        }
        if self.automatic_write_counts != expected_writes:
            raise ValueError("authoring receipt write boundary drift")
        hash_sets = (
            self.code_sha256,
            self.dependency_sha256,
            self.blueprint_manifest_sha256,
            self.prior_input_sha256,
        )
        if any(
            not values
            or any(
                not re.fullmatch(r"[0-9a-f]{64}", item)
                for item in values.values()
            )
            for values in hash_sets
        ):
            raise ValueError("authoring receipt contains an invalid hash")
        return self


class AuthoringSupersessionReceipt(StrictModel):
    schema_version: Literal[
        "typed-extractor-fresh-v2-authoring-receipt-v2"
    ] = "typed-extractor-fresh-v2-authoring-receipt-v2"
    status: Literal["frozen"] = "frozen"
    evaluation_id: Literal[DATASET_ID] = DATASET_ID
    namespace: Literal[NAMESPACE] = NAMESPACE
    preregistration_path: str = Field(min_length=1)
    preregistration_schema: Literal[PREREGISTRATION_SCHEMA] = (
        PREREGISTRATION_SCHEMA
    )
    preregistration_sha256: Literal[PREREGISTRATION_SHA256] = (
        PREREGISTRATION_SHA256
    )
    preregistration_mode: Literal["0444"] = "0444"
    supersedes_receipt_path: str = Field(min_length=1)
    supersedes_receipt_schema: Literal[
        "typed-extractor-fresh-v2-authoring-receipt-v1"
    ] = "typed-extractor-fresh-v2-authoring-receipt-v1"
    supersedes_receipt_sha256: Literal[SUPERSEDED_RECEIPT_SHA256] = (
        SUPERSEDED_RECEIPT_SHA256
    )
    supersedes_receipt_mode: Literal["0444"] = "0444"
    supersession_reason: Literal[SUPERSESSION_REASON] = SUPERSESSION_REASON
    formal_evaluation_root: str = Field(min_length=1)
    receipt_time: str
    receipt_time_source: Literal["caller_supplied_untrusted_utc_label"] = (
        "caller_supplied_untrusted_utc_label"
    )
    chronology_evidence: Literal[
        "filesystem-presence-plus-sha256-plus-supersession-chain"
    ] = "filesystem-presence-plus-sha256-plus-supersession-chain"
    trusted_timestamp_authority: Literal[False] = False
    code_sha256: dict[str, str]
    dependency_sha256: dict[str, str]
    blueprint_manifest_sha256: dict[str, str]
    family_counts: dict[str, dict[str, int]]
    prior_input_sha256: dict[str, str]
    formal_evaluation_root_absent: Literal[True] = True
    hidden_artifact_count: Literal[0] = 0
    model_request_count: Literal[0] = 0
    automatic_write_counts: dict[str, int]
    pipeline_integration_authorized: Literal[False] = False
    longmemeval_status: Literal["structured_l2_identity_unresolved"] = (
        "structured_l2_identity_unresolved"
    )

    @field_validator("receipt_time")
    @classmethod
    def validate_receipt_time(cls, value: str) -> str:
        try:
            parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError as exc:
            raise ValueError("receipt_time must be a valid UTC timestamp") from exc
        if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
            raise ValueError("receipt_time must be a valid UTC timestamp")
        return value

    @model_validator(mode="after")
    def validate_exact_contract(self) -> "AuthoringSupersessionReceipt":
        if self.family_counts != {"l1": L1_FAMILIES, "l2": L2_FAMILIES}:
            raise ValueError("authoring supersession receipt family counts drift")
        expected_writes = {
            "aggregate": 0,
            "closure": 0,
            "identity": 0,
            "l1": 0,
            "l2": 0,
            "membership": 0,
            "revision": 0,
            "snapshot": 0,
            "source_revision": 0,
        }
        if self.automatic_write_counts != expected_writes:
            raise ValueError("authoring supersession receipt write boundary drift")
        hash_sets = (
            self.code_sha256,
            self.dependency_sha256,
            self.blueprint_manifest_sha256,
            self.prior_input_sha256,
        )
        if any(
            not values
            or any(
                not re.fullmatch(r"[0-9a-f]{64}", item)
                for item in values.values()
            )
            for values in hash_sets
        ):
            raise ValueError("authoring supersession receipt contains an invalid hash")
        return self


def _opaque(prefix: str, private_value: str, *, length: int = 16) -> str:
    digest = hashlib.sha256(
        f"{NAMESPACE}|{prefix}|{private_value}".encode("utf-8")
    ).hexdigest()
    return f"{prefix}-{digest[:length]}"


def _normalize_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _hash_value(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _empty_lifecycle() -> TypedLifecycleBinding:
    return TypedLifecycleBinding(
        lifecycle="active",
        replacement_candidate_ref=None,
        replaces_candidate_refs=[],
        supersedes_candidate_refs=[],
        conflicts_with_candidate_refs=[],
    )


def _operations() -> TypedOperationProvenance:
    return TypedOperationProvenance(
        confirmed_by_operation_refs=[],
        added_by_operation_refs=[],
    )


def _remap_lifecycle(value: TypedLifecycleBinding) -> TypedLifecycleBinding:
    def remap(item: str | None) -> str | None:
        return _opaque("candidate", item) if item is not None else None

    return TypedLifecycleBinding(
        lifecycle=value.lifecycle,
        replacement_candidate_ref=remap(value.replacement_candidate_ref),
        replaces_candidate_refs=[
            _opaque("candidate", item) for item in value.replaces_candidate_refs
        ],
        supersedes_candidate_refs=[
            _opaque("candidate", item)
            for item in value.supersedes_candidate_refs
        ],
        conflicts_with_candidate_refs=[
            _opaque("candidate", item)
            for item in value.conflicts_with_candidate_refs
        ],
    )


def _remap_operations(
    value: TypedOperationProvenance,
) -> TypedOperationProvenance:
    return TypedOperationProvenance(
        confirmed_by_operation_refs=[
            _opaque("operation", item)
            for item in value.confirmed_by_operation_refs
        ],
        added_by_operation_refs=[
            _opaque("operation", item) for item in value.added_by_operation_refs
        ],
    )


def _remap_untyped(value: PublicUntypedCandidate) -> PublicUntypedCandidate:
    payload = value.model_dump(mode="json")
    for evidence in payload["evidence"]:
        evidence["evidence_id"] = _opaque(
            "evidence", evidence["evidence_id"], length=64
        )
    payload["lifecycle_links"] = _remap_lifecycle(
        value.lifecycle_links
    ).model_dump(mode="json")
    payload["operation_provenance"] = _remap_operations(
        value.operation_provenance
    ).model_dump(mode="json")
    return PublicUntypedCandidate.model_validate(payload)


def _remap_l1_candidate(value: TypedL1Candidate) -> TypedL1Candidate:
    payload = value.model_dump(mode="json")
    for evidence in payload["evidence_bindings"]:
        evidence["evidence_id"] = _opaque(
            "evidence", evidence["evidence_id"], length=64
        )
    payload["derivation"]["evidence_ids"] = [
        _opaque("evidence", item, length=64)
        for item in value.derivation.evidence_ids
    ]
    payload["lifecycle"] = _remap_lifecycle(value.lifecycle).model_dump(
        mode="json"
    )
    payload["operation_provenance"] = _remap_operations(
        value.operation_provenance
    ).model_dump(mode="json")
    return TypedL1Candidate.model_validate(payload)


def _make_l1_blueprint(
    *,
    family: L1Family,
    ordinal: int,
    user: str,
    agent: str,
    statement: str,
    decision: L1Decision,
    kind: str,
    sense: str,
    operator: str,
    roles: tuple[tuple[str, str, str], ...],
    modality: str = "actual",
    polarity: str = "positive",
    object_value: str | None = None,
    qualifiers: dict[str, Any] | None = None,
    event_time: str | None = None,
    valid_time: str | None = None,
    conditions: tuple[tuple[str, str, tuple[int, ...]], ...] = (),
    scopes: tuple[tuple[str, str, tuple[int, ...]], ...] = (),
    derivation: str = "explicit",
    inference_basis: str | None = None,
    source_status: str = "user_reported",
    lifecycle: TypedLifecycleBinding | None = None,
    operations: TypedOperationProvenance | None = None,
    unresolved: tuple[str, ...] = (),
) -> L1Blueprint:
    private = f"fresh-v2-l1-{family}-{ordinal:02d}"
    evidence_id = f"{private}-evidence"
    message = (
        "agent"
        if source_status in {"agent_generated", "tool_observed"}
        else "user"
    )
    evidence_text = agent if message == "agent" else user
    speaker = (
        "assistant"
        if source_status == "agent_generated"
        else "tool"
        if source_status == "tool_observed"
        else "user"
    )
    untyped = PublicUntypedCandidate(
        statement=statement,
        subject=roles[0][2],
        predicate=operator.replace("_", " "),
        object=object_value,
        qualifiers=qualifiers or {"polarity": polarity},
        source_status=source_status,
        derivation=derivation,
        inference_basis=inference_basis,
        projection_status="active",
        lifecycle_links=lifecycle or _empty_lifecycle(),
        operation_provenance=operations or _operations(),
        evidence=[
            PublicEvidenceSpan(
                evidence_id=evidence_id,
                speaker=speaker,
                message=message,
                quote=evidence_text,
                occurrence_index=0,
                start=0,
                end=len(evidence_text),
            )
        ],
    )
    typed: TypedL1Candidate | None = None
    if decision == "emit_l1":
        typed = TypedL1Candidate(
            kind=kind,
            predicate=TypedPredicate(
                surface=operator.replace("_", " "),
                sense=sense,
                canonical_operator=operator,
            ),
            local_entities=[
                TypedLocalEntity(
                    local_entity_id=f"entity-{index:02d}",
                    surface=surface,
                )
                for index, (_, _, surface) in enumerate(roles, 1)
            ],
            roles=[
                TypedRoleBinding(
                    role=role,
                    role_name=role_name,
                    local_entity_id=f"entity-{index:02d}",
                )
                for index, (role, role_name, _) in enumerate(roles, 1)
            ],
            modality=modality,
            polarity=polarity,
            time=TypedTimeBinding(
                event_time=event_time,
                valid_time=valid_time,
            ),
            condition_bindings=[
                TypedConditionBinding(
                    operator=condition_operator,
                    value=value,
                    local_entity_ids=[
                        f"entity-{index:02d}" for index in entity_indexes
                    ],
                )
                for condition_operator, value, entity_indexes in conditions
            ],
            scope_bindings=[
                TypedScopeBinding(
                    operator=scope_operator,
                    value=value,
                    local_entity_ids=[
                        f"entity-{index:02d}" for index in entity_indexes
                    ],
                )
                for scope_operator, value, entity_indexes in scopes
            ],
            derivation=TypedDerivationProvenance(
                method=derivation,
                basis=inference_basis,
                evidence_ids=[evidence_id],
            ),
            evidence_bindings=[
                TypedEvidenceBinding(
                    evidence_id=evidence_id,
                    speaker=speaker,
                )
            ],
            lifecycle=lifecycle or _empty_lifecycle(),
            operation_provenance=operations or _operations(),
        )
    return L1Blueprint(
        blueprint_id=private,
        family=family,
        ordinal=ordinal,
        private_case_id=f"private-{private}",
        knowledge_id=f"knowledge-{private}",
        candidate_id=f"candidate-private-{private}",
        source_turn={"user": user, "agent": agent},
        untyped_candidate=untyped,
        expected_decision=decision,
        expected_typed_candidate=typed,
        unresolved_required_fields=unresolved,
    )


def _l1_specs() -> tuple[L1Blueprint, ...]:
    items: list[L1Blueprint] = []
    explicit_specs = (
        (
            "Nora handed the cobalt key to Ilya at the studio.",
            "I recorded the handoff.",
            "Nora handed the cobalt key to Ilya.",
            "transfer.handoff",
            "record_handoff",
            (
                ("giver", "handoff source", "Nora"),
                ("theme", "transferred item", "the cobalt key"),
                ("recipient", "handoff recipient", "Ilya"),
            ),
        ),
        (
            "Pavel calibrated sensor R8 with technician Mei.",
            "The calibration participants are explicit.",
            "Pavel calibrated sensor R8 with Mei.",
            "maintenance.calibration",
            "calibrate_sensor",
            (
                ("technician", "primary technician", "Pavel"),
                ("theme", "calibrated sensor", "sensor R8"),
                ("participant", "assisting technician", "Mei"),
            ),
        ),
        (
            "Lena delivered parcel Q4 from Depot Elm to Rowan.",
            "The route and recipient are recorded.",
            "Lena delivered parcel Q4 to Rowan.",
            "logistics.delivery",
            "deliver_parcel",
            (
                ("courier", "delivery actor", "Lena"),
                ("theme", "delivered parcel", "parcel Q4"),
                ("origin", "delivery origin", "Depot Elm"),
                ("recipient", "delivery recipient", "Rowan"),
            ),
        ),
        (
            "Omar reviewed the amber contract for client Suri.",
            "The review roles are explicit.",
            "Omar reviewed the amber contract for Suri.",
            "document.client_review",
            "review_contract",
            (
                ("reviewer", "contract reviewer", "Omar"),
                ("theme", "reviewed contract", "the amber contract"),
                ("beneficiary", "review client", "Suri"),
            ),
        ),
    )
    for ordinal, (user, agent, statement, sense, operator, roles) in enumerate(
        explicit_specs, 1
    ):
        items.append(
            _make_l1_blueprint(
                family="explicit_event_roles",
                ordinal=ordinal,
                user=user,
                agent=agent,
                statement=statement,
                decision="emit_l1",
                kind="event",
                sense=sense,
                operator=operator,
                roles=roles,
                object_value=roles[1][2],
            )
        )

    condition_specs = (
        (
            "If audit Delta closes, remind Keira to publish note V3.",
            "The publication request is conditional.",
            "Keira should publish note V3 if audit Delta closes.",
            "task.conditional_publish",
            "publish_note",
            "if",
            "audit Delta closes",
            "requested",
            False,
        ),
        (
            "Within workspace Juniper, keep the coral dashboard private.",
            "The privacy state is workspace-scoped.",
            "The coral dashboard is private within workspace Juniper.",
            "privacy.workspace_scope",
            "keep_dashboard_private",
            "within",
            "workspace Juniper",
            "actual",
            True,
        ),
        (
            "Only for account M17, route invoices to Dario.",
            "The routing rule has an account scope.",
            "Invoices route to Dario only for account M17.",
            "billing.account_route",
            "route_invoice",
            "only_for",
            "account M17",
            "actual",
            True,
        ),
        (
            "After checkpoint Kappa passes, schedule the bronze deployment.",
            "The schedule request depends on Kappa.",
            "Schedule the bronze deployment after checkpoint Kappa passes.",
            "release.conditional_schedule",
            "schedule_deployment",
            "after",
            "checkpoint Kappa passes",
            "requested",
            False,
        ),
    )
    condition_roles = (
        (
            ("actor", "publishing actor", "Keira"),
            ("theme", "publication note", "note V3"),
            ("condition", "publication condition", "audit Delta"),
        ),
        (
            ("theme", "private dashboard", "the coral dashboard"),
            ("scope", "workspace scope", "workspace Juniper"),
        ),
        (
            ("theme", "routed invoice", "invoices"),
            ("recipient", "invoice recipient", "Dario"),
            ("scope", "account scope", "account M17"),
        ),
        (
            ("actor", "request owner", "the user"),
            ("theme", "scheduled deployment", "the bronze deployment"),
            ("condition", "schedule condition", "checkpoint Kappa"),
        ),
    )
    condition_objects = ("note V3", "the coral dashboard", "Dario", "the bronze deployment")
    condition_binding_indexes = ((3,), (2,), (3,), (3,))
    for ordinal, (spec, roles, object_value, binding_indexes) in enumerate(
        zip(
            condition_specs,
            condition_roles,
            condition_objects,
            condition_binding_indexes,
            strict=True,
        ),
        1,
    ):
        user, agent, statement, sense, operator, qualifier, value, modality, is_scope = spec
        binding = ((qualifier, value, binding_indexes),)
        items.append(
            _make_l1_blueprint(
                family="condition_scope",
                ordinal=ordinal,
                user=user,
                agent=agent,
                statement=statement,
                decision="emit_l1",
                kind="state" if modality == "actual" else "task",
                sense=sense,
                operator=operator,
                roles=roles,
                modality=modality,
                object_value=object_value,
                qualifiers={
                    "polarity": "positive",
                    "scope" if is_scope else "condition": value,
                },
                conditions=() if is_scope else binding,
                scopes=binding if is_scope else (),
            )
        )

    modality_specs = (
        (
            "I plan to inspect vault Sigma on 2026-08-04.",
            "The inspection is planned for an explicit date.",
            "The user plans to inspect vault Sigma on 2026-08-04.",
            "inspection.planned_vault",
            "inspect_vault",
            "planned",
            "2026-08-04",
            None,
            "emit_l1",
            (),
        ),
        (
            "Please reserve lab Cinder for 2026-08-06.",
            "The reservation is a dated request.",
            "The user requests lab Cinder for 2026-08-06.",
            "reservation.request_lab",
            "reserve_lab",
            "requested",
            "2026-08-06",
            None,
            "emit_l1",
            (),
        ),
        (
            "My permit P9 remains valid through 2026-09-30.",
            "The permit has an explicit validity boundary.",
            "Permit P9 is valid through 2026-09-30.",
            "permit.validity",
            "permit_valid_until",
            "actual",
            None,
            "2026-09-30",
            "emit_l1",
            (),
        ),
        (
            "Move the slate briefing to sometime after the festival.",
            "The festival date is not available.",
            "The slate briefing occurs after the festival.",
            "briefing.unresolved_time",
            "move_briefing",
            "requested",
            None,
            None,
            "abstain",
            ("event_time",),
        ),
    )
    modality_roles = (
        (
            ("actor", "inspection actor", "the user"),
            ("theme", "inspected vault", "vault Sigma"),
        ),
        (
            ("actor", "reservation requester", "the user"),
            ("theme", "reserved lab", "lab Cinder"),
        ),
        (
            ("holder", "permit holder", "the user"),
            ("theme", "permit", "permit P9"),
        ),
        (
            ("actor", "request owner", "the user"),
            ("theme", "briefing", "the slate briefing"),
            ("temporal_anchor", "relative time anchor", "the festival"),
        ),
    )
    for ordinal, (spec, roles) in enumerate(
        zip(modality_specs, modality_roles, strict=True), 1
    ):
        (
            user,
            agent,
            statement,
            sense,
            operator,
            modality,
            event_time,
            valid_time,
            decision,
            unresolved,
        ) = spec
        time_label = event_time or valid_time or "after the festival"
        items.append(
            _make_l1_blueprint(
                family="modality_time",
                ordinal=ordinal,
                user=user,
                agent=agent,
                statement=statement,
                decision=decision,
                kind="state" if valid_time else "task",
                sense=sense,
                operator=operator,
                roles=roles,
                modality=modality,
                object_value=roles[1][2],
                qualifiers={"polarity": "positive", "time": time_label},
                event_time=event_time,
                valid_time=valid_time,
                unresolved=unresolved,
            )
        )

    lifecycle_specs = (
        (
            "I moved the launch review from Thursday to Friday.",
            "Friday replaces Thursday.",
            "The launch review is scheduled for Friday.",
            "review.rescheduled",
            "reschedule_review",
            "active",
            (),
            ("prior-launch-review",),
            (),
        ),
        (
            "Code 4821 replaces the retired access code for locker Jade.",
            "The replacement code is current.",
            "Locker Jade uses access code 4821.",
            "access.code_replacement",
            "replace_access_code",
            "active",
            ("retired-locker-code",),
            (),
            (),
        ),
        (
            "I first named folder Quartz, but the correct folder is Saffron.",
            "Saffron supersedes Quartz.",
            "The correct folder is Saffron.",
            "document.folder_correction",
            "correct_folder",
            "active",
            (),
            ("quartz-folder-claim",),
            (),
        ),
        (
            "One signed log says batch 14 passed; another signed log says it failed.",
            "Both signed observations remain in conflict.",
            "Batch 14 has conflicting signed outcomes.",
            "test.conflicting_outcomes",
            "record_batch_conflict",
            "conflicted",
            (),
            (),
            ("batch-14-passed", "batch-14-failed"),
        ),
    )
    lifecycle_roles = (
        (
            ("theme", "review", "the launch review"),
            ("prior_time", "replaced schedule", "Thursday"),
            ("current_time", "current schedule", "Friday"),
        ),
        (
            ("theme", "locker", "locker Jade"),
            ("current_value", "replacement code", "access code 4821"),
        ),
        (
            ("theme", "corrected field", "folder"),
            ("prior_value", "incorrect folder", "Quartz"),
            ("current_value", "correct folder", "Saffron"),
        ),
        (
            ("theme", "test batch", "batch 14"),
            ("outcome", "signed outcome", "passed"),
            ("conflicting_outcome", "conflicting signed outcome", "failed"),
        ),
    )
    lifecycle_objects = ("Friday", "access code 4821", "Saffron", "conflicting signed outcomes")
    lifecycle_operations = (
        TypedOperationProvenance(
            confirmed_by_operation_refs=[],
            added_by_operation_refs=["operation-reschedule-launch-review"],
        ),
        TypedOperationProvenance(
            confirmed_by_operation_refs=[],
            added_by_operation_refs=["operation-replace-locker-code"],
        ),
        TypedOperationProvenance(
            confirmed_by_operation_refs=["operation-correct-folder"],
            added_by_operation_refs=[],
        ),
        TypedOperationProvenance(
            confirmed_by_operation_refs=["operation-record-batch-conflict"],
            added_by_operation_refs=[],
        ),
    )
    for ordinal, (spec, roles, object_value, operations) in enumerate(
        zip(
            lifecycle_specs,
            lifecycle_roles,
            lifecycle_objects,
            lifecycle_operations,
            strict=True,
        ),
        1,
    ):
        user, agent, statement, sense, operator, status, replaces, supersedes, conflicts = spec
        lifecycle = TypedLifecycleBinding(
            lifecycle=status,
            replacement_candidate_ref=None,
            replaces_candidate_refs=list(replaces),
            supersedes_candidate_refs=list(supersedes),
            conflicts_with_candidate_refs=list(conflicts),
        )
        items.append(
            _make_l1_blueprint(
                family="lifecycle_revision",
                ordinal=ordinal,
                user=user,
                agent=agent,
                statement=statement,
                decision="emit_l1",
                kind="state",
                sense=sense,
                operator=operator,
                roles=roles,
                object_value=object_value,
                lifecycle=lifecycle,
                operations=operations,
            )
        )

    derivation_specs = (
        (
            "Check the gauge reading.",
            "Tool observation: gauge L6 reads 72 kPa.",
            "Gauge L6 reads 72 kPa.",
            "sensor.pressure_observation",
            "observe_pressure",
            "actual",
            "tool_observed",
            "explicit",
            None,
            "emit_l1",
            (),
        ),
        (
            "What should I do with the orchid report?",
            "I recommend archiving the orchid report after approval.",
            "The assistant recommends archiving the orchid report after approval.",
            "assistant.archive_recommendation",
            "recommend_archive",
            "recommended",
            "agent_generated",
            "explicit",
            None,
            "emit_l1",
            (),
        ),
        (
            "The cedar draft is ready; archive it with the signed appendix.",
            "The pronoun resolves locally to the cedar draft.",
            "The user requests archiving the cedar draft with the signed appendix.",
            "document.context_archive",
            "archive_draft",
            "requested",
            "user_reported",
            "context_completed",
            "The local pronoun resolves to the cedar draft.",
            "emit_l1",
            (),
        ),
        (
            "A visitor supposedly said that depot Nimbus is closed.",
            "The attributed report cannot be verified.",
            "Depot Nimbus is closed.",
            "depot.unverified_closure",
            "close_depot",
            "hypothetical",
            "user_reported",
            "inferred",
            "The only support is an unverified attributed report.",
            "abstain",
            ("epistemic_authority",),
        ),
    )
    derivation_roles = (
        (
            ("theme", "observed gauge", "gauge L6"),
            ("value", "pressure reading", "72 kPa"),
        ),
        (
            ("actor", "recommending assistant", "the assistant"),
            ("theme", "report", "the orchid report"),
            ("condition", "approval condition", "approval"),
        ),
        (
            ("actor", "requesting user", "the user"),
            ("theme", "draft", "the cedar draft"),
            ("companion", "required appendix", "the signed appendix"),
        ),
        (
            ("theme", "depot", "depot Nimbus"),
            ("source", "attributed source", "a visitor"),
        ),
    )
    for ordinal, (spec, roles) in enumerate(
        zip(derivation_specs, derivation_roles, strict=True), 1
    ):
        (
            user,
            agent,
            statement,
            sense,
            operator,
            modality,
            source_status,
            derivation,
            basis,
            decision,
            unresolved,
        ) = spec
        items.append(
            _make_l1_blueprint(
                family="derivation_epistemic",
                ordinal=ordinal,
                user=user,
                agent=agent,
                statement=statement,
                decision=decision,
                kind="state" if modality == "actual" else "task",
                sense=sense,
                operator=operator,
                roles=roles,
                modality=modality,
                object_value=roles[1][2] if len(roles) > 1 else roles[0][2],
                derivation=derivation,
                inference_basis=basis,
                source_status=source_status,
                unresolved=unresolved,
            )
        )

    control_specs = (
        (
            "Could the copper printer be offline?",
            "No status evidence was provided.",
            "The copper printer is offline.",
            "no_memory",
            (),
        ),
        (
            "Reply using exactly three bullets.",
            "I will follow that response format.",
            "The response format is three bullets.",
            "no_memory",
            (),
        ),
        (
            "Maybe someone owns the violet canoe.",
            "Neither owner nor actuality is established.",
            "Someone owns the violet canoe.",
            "abstain",
            ("owner_identity", "supported_modality"),
        ),
        (
            "Put it beside the earlier one.",
            "Neither referent is recoverable in this turn.",
            "An item is beside an earlier item.",
            "abstain",
            ("theme_identity", "reference_identity"),
        ),
    )
    for ordinal, (user, agent, statement, decision, unresolved) in enumerate(
        control_specs, 1
    ):
        items.append(
            _make_l1_blueprint(
                family="abstention_no_memory_controls",
                ordinal=ordinal,
                user=user,
                agent=agent,
                statement=statement,
                decision=decision,
                kind="state",
                sense="control.unresolved_relation",
                operator="record_unresolved_relation",
                roles=(
                    ("theme", "unresolved theme", "the unresolved subject"),
                ),
                modality="hypothetical",
                object_value="the unresolved object",
                qualifiers={
                    "polarity": "positive",
                    "modality": "uncertain",
                },
                unresolved=unresolved,
            )
        )
    return tuple(items)


def _make_l2_blueprint(
    *,
    family: L2Family,
    ordinal: int,
    turns: tuple[tuple[str, str], tuple[str, str]],
    statement: str,
    subject: str,
    predicate_surface: str,
    object_value: str,
    decision: L2Decision,
    kind: str,
    abstraction_method: str,
    closure_pattern: str,
    sense: str,
    operator: str,
    support_semantics: tuple[L2SupportSemantic, L2SupportSemantic],
    modality: str = "actual",
    unresolved: tuple[str, ...] = (),
) -> L2Blueprint:
    if len(support_semantics) != len(turns):
        raise ValueError("L2 support semantic count must match source turns")
    private = f"fresh-v2-l2-{family}-{ordinal:02d}"
    session_ref = _opaque("session", private)
    blueprint_turns: list[L2BlueprintTurn] = []
    supports: list[TypedL1SupportCandidate] = []
    evidence_spans: list[PublicEvidenceSpan] = []
    for index, (user, agent) in enumerate(turns):
        support_semantic = support_semantics[index]
        private_turn = f"{private}-turn-{index + 1}"
        turn_ref = _opaque("turn", private_turn)
        evidence_id = _opaque(
            "evidence",
            f"{private}-evidence-{index + 1}",
            length=64,
        )
        support_ref = _opaque(
            "support",
            f"{private}-support-{index + 1}",
        )
        blueprint_turns.append(
            L2BlueprintTurn(
                private_turn_id=private_turn,
                source_turn_ref=turn_ref,
                turn_index=index,
                user=user,
                agent=agent,
            )
        )
        evidence_spans.append(
            PublicEvidenceSpan(
                evidence_id=evidence_id,
                speaker="user",
                message="user",
                quote=user,
                occurrence_index=0,
                start=0,
                end=len(user),
            )
        )
        supports.append(
            TypedL1SupportCandidate(
                support_ref=support_ref,
                source_turn_ref=turn_ref,
                source_session_ref=session_ref,
                kind=support_semantic.kind,
                predicate=TypedPredicate(
                    surface=support_semantic.predicate_surface,
                    sense=support_semantic.sense,
                    canonical_operator=support_semantic.operator,
                ),
                local_entities=[
                    TypedLocalEntity(
                        local_entity_id=f"entity-{entity_index:02d}",
                        surface=surface,
                    )
                    for entity_index, (_, _, surface) in enumerate(
                        support_semantic.roles, 1
                    )
                ],
                roles=[
                    TypedRoleBinding(
                        role=role,
                        role_name=role_name,
                        local_entity_id=f"entity-{entity_index:02d}",
                    )
                    for entity_index, (role, role_name, _) in enumerate(
                        support_semantic.roles, 1
                    )
                ],
                modality=support_semantic.modality,
                polarity=support_semantic.polarity,
                time=TypedTimeBinding(
                    event_time=support_semantic.event_time,
                    valid_time=support_semantic.valid_time,
                ),
                evidence_bindings=[
                    TypedEvidenceBinding(
                        evidence_id=evidence_id,
                        speaker="user",
                    )
                ],
            )
        )
    untyped = PublicUntypedCandidate(
        statement=statement,
        subject=subject,
        predicate=predicate_surface,
        object=object_value,
        qualifiers={"polarity": "positive"},
        source_status="user_reported",
        derivation="context_completed" if decision == "emit_l2" else "inferred",
        inference_basis=(
            "Both turns contribute to the closed abstraction."
            if decision == "emit_l2"
            else (
                "The required cross-turn identity or semantic relation "
                "is unresolved."
            )
        ),
        projection_status="active",
        lifecycle_links=_empty_lifecycle(),
        operation_provenance=_operations(),
        evidence=evidence_spans,
    )
    expected: TypedL2Candidate | None = None
    if decision == "emit_l2":
        support_refs = [item.support_ref for item in supports]
        claims = [
            TypedL2StructuredClaim(
                claim_ref="claim-01",
                predicate=TypedPredicate(
                    surface=predicate_surface,
                    sense=sense,
                    canonical_operator=operator,
                ),
                local_entities=[
                    TypedLocalEntity(
                        local_entity_id="entity-01",
                        surface=subject,
                    ),
                    TypedLocalEntity(
                        local_entity_id="entity-02",
                        surface=object_value,
                    ),
                ],
                roles=[
                    TypedRoleBinding(
                        role="holder",
                        role_name="aggregate holder",
                        local_entity_id="entity-01",
                    ),
                    TypedRoleBinding(
                        role="theme",
                        role_name="aggregate theme",
                        local_entity_id="entity-02",
                    ),
                ],
                modality=modality,
                polarity="positive",
                time=TypedTimeBinding(event_time=None, valid_time=None),
                supporting_l1_refs=support_refs,
            )
        ]
        expected = TypedL2Candidate(
            kind=kind,
            summary=statement,
            supporting_l1_refs=support_refs,
            structured_claims=claims,
            abstraction=TypedL2Abstraction(
                method=abstraction_method,
                basis=(
                    "The two explicit L1 supports jointly establish "
                    "this abstraction."
                ),
            ),
            closure=TypedL2Closure(
                pattern=closure_pattern,
                required_support_refs=support_refs,
                optional_support_refs=[],
            ),
            source_turn_refs=[item.source_turn_ref for item in supports],
            source_session_refs=[session_ref],
            evidence_bindings=[
                binding for support in supports for binding in support.evidence_bindings
            ],
        )
    return L2Blueprint(
        blueprint_id=private,
        family=family,
        ordinal=ordinal,
        private_case_id=f"private-{private}",
        knowledge_id=f"knowledge-{private}",
        candidate_id=f"candidate-private-{private}",
        private_session_id=f"private-session-{private}",
        source_session_ref=session_ref,
        source_turns=tuple(blueprint_turns),
        untyped_candidate=untyped,
        typed_l1_support_pack=tuple(supports),
        expected_decision=decision,
        expected_typed_candidate=expected,
        unresolved_required_fields=unresolved,
    )


def _support(
    kind: str,
    predicate_surface: str,
    sense: str,
    operator: str,
    roles: tuple[tuple[str, str, str], ...],
    *,
    modality: str = "actual",
    polarity: str = "positive",
) -> L2SupportSemantic:
    return L2SupportSemantic(
        kind=kind,
        predicate_surface=predicate_surface,
        sense=sense,
        operator=operator,
        roles=roles,
        modality=modality,
        polarity=polarity,
    )


def _l2_support_semantics() -> dict[
    tuple[L2Family, int],
    tuple[L2SupportSemantic, L2SupportSemantic],
]:
    user = ("actor", "requesting user", "the user")
    holder = ("holder", "preference holder", "the user")
    return {
        ("coreference_task_composition", 1): (
            _support(
                "task", "inspect dossier appendix", "document.inspect_appendix", "inspect_dossier_appendix",
                (user, ("theme", "dossier", "dossier Marigold"), ("component", "appendix", "its appendix")),
                modality="requested",
            ),
            _support(
                "task", "send dossier for review", "document.send_for_review", "send_dossier_for_review",
                (user, ("theme", "resolved dossier", "dossier Marigold"), ("recipient", "review recipient", "Tessa")),
                modality="requested",
            ),
        ),
        ("coreference_task_composition", 2): (
            _support(
                "task", "prepare sample for imaging", "lab.prepare_sample", "prepare_sample",
                (user, ("theme", "sample", "sample Helix"), ("purpose", "imaging purpose", "imaging")),
                modality="requested",
            ),
            _support(
                "task", "archive resulting scan", "lab.archive_scan", "archive_scan",
                (user, ("theme", "resulting scan", "the resulting scan"), ("destination", "archive cabinet", "cabinet Opal")),
                modality="requested",
            ),
        ),
        ("preference_state_aggregation", 1): (
            _support(
                "preference", "prefer window-near desks", "preference.desk_window_proximity", "prefer_window_near_desk",
                (holder, ("theme", "preferred item", "desks"), ("proximity", "preferred location", "windows")),
            ),
            _support(
                "preference", "avoid elevator-adjacent desks", "preference.desk_elevator_distance", "avoid_elevator_adjacent_desk",
                (holder, ("theme", "avoided item", "desks"), ("proximity", "avoided location", "elevators")),
                polarity="negative",
            ),
        ),
        ("preference_state_aggregation", 2): (
            _support(
                "state", "ankle stiffness observation", "health.ankle_stiffness", "observe_ankle_stiffness",
                (("theme", "affected body part", "left ankle"), ("state", "observed symptom", "stiffness"), ("context", "observation context", "after the hike")),
            ),
            _support(
                "state", "persistent ankle stiffness", "health.ankle_stiffness_persistence", "observe_persistent_ankle_stiffness",
                (("theme", "resolved body part", "left ankle"), ("state", "persistent symptom", "stiffness"), ("time", "later observation", "the following evening")),
            ),
        ),
        ("lifecycle_supersession", 1): (
            _support(
                "task", "send invoice", "billing.send_invoice", "send_invoice",
                (user, ("theme", "invoice", "invoice Cedar"), ("recipient", "initial recipient", "Malik")),
                modality="requested",
            ),
            _support(
                "task", "correct invoice recipient", "billing.correct_invoice_recipient", "correct_invoice_recipient",
                (user, ("theme", "invoice", "invoice Cedar"), ("recipient", "corrected recipient", "Priya")),
                modality="requested",
            ),
        ),
        ("lifecycle_supersession", 2): (
            _support(
                "task", "schedule demo", "calendar.schedule_demo", "schedule_demo",
                (user, ("theme", "demo", "the cobalt demo"), ("event_time", "initial day", "Monday")),
                modality="requested",
            ),
            _support(
                "task", "reschedule demo", "calendar.reschedule_demo", "reschedule_demo",
                (user, ("theme", "demo", "the cobalt demo"), ("event_time", "corrected day", "Wednesday")),
                modality="requested",
            ),
        ),
        ("multi_evidence_closure", 1): (
            _support(
                "event", "pump stopped after valve jam", "maintenance.valve_jam_outage", "record_valve_jam_outage",
                (("cause", "jammed valve", "valve N2"), ("theme", "stopped pump", "the amber pump")),
            ),
            _support(
                "event", "valve replacement restored pump", "maintenance.valve_replacement_restore", "record_valve_replacement_restore",
                (("action", "repair action", "replacing valve N2"), ("theme", "restored pump", "the amber pump")),
            ),
        ),
        ("multi_evidence_closure", 2): (
            _support(
                "event", "complete security review", "project.security_review_complete", "complete_security_review",
                (("theme", "project", "Project Lumen"), ("milestone", "completed milestone", "security review")),
            ),
            _support(
                "event", "enter pilot phase", "project.enter_pilot", "enter_pilot_phase",
                (("theme", "project", "Project Lumen"), ("phase", "new phase", "pilot phase")),
            ),
        ),
        ("abstraction_structured_claim_boundary", 1): (
            _support(
                "preference", "prefer rail travel", "preference.rail_over_flights", "prefer_rail_travel",
                (holder, ("theme", "preferred mode", "rail"), ("alternative", "disfavored mode", "flights")),
            ),
            _support(
                "preference", "require refundable hotel rates", "preference.refundable_hotel_rate", "require_refundable_hotel_rate",
                (holder, ("theme", "lodging constraint", "refundable hotel rates")),
            ),
        ),
        ("abstraction_structured_claim_boundary", 2): (
            _support(
                "event", "repair bicycle", "maintenance.repair_bicycle", "repair_bicycle",
                (user, ("theme", "repaired bicycle", "bicycle Kestrel"), ("time", "repair time", "this morning")),
            ),
            _support(
                "state", "study field", "education.study_field", "study_field",
                (("student", "student", "the user's cousin"), ("theme", "field of study", "marine biology")),
            ),
        ),
        ("abstention_unresolved_controls", 1): (
            _support(
                "state", "option availability", "selection.option_availability", "record_option_availability",
                (("theme", "available option", "Option Topaz"), ("time", "availability day", "Thursday")),
            ),
            _support(
                "task", "select earlier option", "selection.unresolved_comparative", "select_earlier_option",
                (user, ("theme", "unresolved selected option", "an earlier option")),
                modality="requested",
            ),
        ),
        ("abstention_unresolved_controls", 2): (
            _support(
                "task", "possibly lead audit", "audit.possible_leader", "lead_audit",
                (("actor", "unresolved possible leader", "someone"), ("theme", "audit", "the quartz audit")),
                modality="hypothetical",
            ),
            _support(
                "event", "rumored audit start", "audit.rumored_start", "start_audit",
                (("actor", "unresolved pronoun", "they"), ("theme", "audit", "the quartz audit")),
                modality="hypothetical",
            ),
        ),
    }


def _l2_specs() -> tuple[L2Blueprint, ...]:
    specs = (
        (
            "coreference_task_composition",
            1,
            (
                (
                    "Open dossier Marigold and inspect its appendix.",
                    "The appendix belongs to Marigold.",
                ),
                (
                    "Then send it to Tessa for review.",
                    "The local referent remains dossier Marigold.",
                ),
            ),
            "The user requests inspecting dossier Marigold and sending it to Tessa.",
            "the user",
            "requests dossier workflow",
            "dossier Marigold",
            "emit_l2",
            "task",
            "coreference_resolution",
            "multi_evidence_set",
            "document.coreference_workflow",
            "compose_dossier_workflow",
            (),
        ),
        (
            "coreference_task_composition",
            2,
            (
                (
                    "Prepare sample Helix for imaging.",
                    "Helix is the preparation target.",
                ),
                (
                    "Archive the resulting scan in cabinet Opal.",
                    "The scan is the output of the same task.",
                ),
            ),
            "The user requests preparing sample Helix, imaging it, and archiving the scan.",
            "the user",
            "requests imaging workflow",
            "sample Helix",
            "emit_l2",
            "task",
            "task_composition",
            "temporal_chain",
            "lab.imaging_workflow",
            "compose_imaging_workflow",
            (),
        ),
        (
            "preference_state_aggregation",
            1,
            (
                (
                    "I prefer desks near windows.",
                    "Window proximity is one preference.",
                ),
                (
                    "I also avoid desks beside elevators.",
                    "Elevator distance is a compatible preference.",
                ),
            ),
            "The user prefers desks near windows and away from elevators.",
            "the user",
            "has desk preference profile",
            "window-adjacent desks away from elevators",
            "emit_l2",
            "preference_profile",
            "preference_aggregation",
            "multi_evidence_set",
            "preference.desk_profile",
            "aggregate_desk_preferences",
            (),
        ),
        (
            "preference_state_aggregation",
            2,
            (
                (
                    "My left ankle felt stiff after the hike.",
                    "The stiffness is an observed state.",
                ),
                (
                    "It was still stiff the following evening.",
                    "The second observation indicates persistence.",
                ),
            ),
            "The user's left ankle stiffness persisted across both observations.",
            "the user",
            "has persistent ankle stiffness",
            "left ankle stiffness",
            "emit_l2",
            "long_running_state",
            "state_summary",
            "temporal_chain",
            "health.persistent_ankle_stiffness",
            "summarize_ankle_state",
            (),
        ),
        (
            "lifecycle_supersession",
            1,
            (
                (
                    "Send invoice Cedar to Malik.",
                    "Malik is the initial recipient.",
                ),
                (
                    "Correction: send invoice Cedar to Priya instead.",
                    "Priya supersedes Malik.",
                ),
            ),
            "The current request is to send invoice Cedar to Priya.",
            "the user",
            "requests corrected invoice delivery",
            "invoice Cedar to Priya",
            "emit_l2",
            "task",
            "lifecycle_resolution",
            "update_supersession",
            "billing.corrected_recipient",
            "resolve_invoice_recipient",
            (),
        ),
        (
            "lifecycle_supersession",
            2,
            (
                (
                    "Schedule the cobalt demo for Monday.",
                    "Monday is the initial schedule.",
                ),
                (
                    "Move the cobalt demo to Wednesday instead.",
                    "Wednesday supersedes Monday.",
                ),
            ),
            "The cobalt demo is currently planned for Wednesday.",
            "the user",
            "plans corrected demo date",
            "cobalt demo on Wednesday",
            "emit_l2",
            "task",
            "lifecycle_resolution",
            "update_supersession",
            "calendar.corrected_demo_date",
            "resolve_demo_schedule",
            (),
        ),
        (
            "multi_evidence_closure",
            1,
            (
                (
                    "The amber pump stopped after valve N2 jammed.",
                    "The jam precedes the stop.",
                ),
                (
                    "Replacing valve N2 restored the amber pump.",
                    "The repair restored operation.",
                ),
            ),
            "Valve N2's jam caused the amber pump outage, and replacement restored it.",
            "the maintenance record",
            "summarizes pump incident",
            "amber pump incident",
            "emit_l2",
            "summary_event",
            "state_summary",
            "causal_answerability",
            "maintenance.pump_incident",
            "summarize_pump_incident",
            (),
        ),
        (
            "multi_evidence_closure",
            2,
            (
                (
                    "Project Lumen completed its security review.",
                    "The review milestone is complete.",
                ),
                (
                    "Project Lumen then entered the pilot phase.",
                    "The pilot follows the review.",
                ),
            ),
            "Project Lumen progressed from security review completion into the pilot phase.",
            "Project Lumen",
            "has milestone progression",
            "security review to pilot",
            "emit_l2",
            "project",
            "task_composition",
            "temporal_chain",
            "project.milestone_progression",
            "compose_project_progression",
            (),
        ),
        (
            "abstraction_structured_claim_boundary",
            1,
            (
                (
                    "For trips, I prefer rail over flights.",
                    "Rail is the preferred travel mode.",
                ),
                (
                    "For hotels, I require refundable rates.",
                    "Refundability is a separate lodging constraint.",
                ),
            ),
            "The user's travel profile prefers rail and requires refundable hotels.",
            "the user",
            "has travel preference profile",
            "rail travel and refundable hotels",
            "emit_l2",
            "preference_profile",
            "preference_aggregation",
            "multi_evidence_set",
            "preference.travel_profile",
            "aggregate_travel_profile",
            (),
        ),
        (
            "abstraction_structured_claim_boundary",
            2,
            (
                (
                    "I repaired bicycle Kestrel this morning.",
                    "A completed repair is reported.",
                ),
                (
                    "My cousin studies marine biology.",
                    "This is an unrelated personal fact.",
                ),
            ),
            "The two turns form one shared project.",
            "the user",
            "has shared project",
            "repair and marine biology",
            "abstain",
            "project",
            "task_composition",
            "multi_evidence_set",
            "control.unrelated_abstraction",
            "compose_unrelated_project",
            ("shared_abstraction",),
        ),
        (
            "abstention_unresolved_controls",
            1,
            (
                (
                    "Option Topaz is available on Thursday.",
                    "Only Topaz is introduced.",
                ),
                (
                    "Choose whichever available option comes earlier.",
                    "No closed option set identifies the referent.",
                ),
            ),
            "The user selected an earlier option.",
            "the user",
            "selected option",
            "an earlier option",
            "abstain",
            "task",
            "coreference_resolution",
            "multi_evidence_set",
            "selection.unresolved_comparative",
            "resolve_option_selection",
            ("selected_option_identity",),
        ),
        (
            "abstention_unresolved_controls",
            2,
            (
                (
                    "Someone may lead the quartz audit.",
                    "The possible leader is unnamed.",
                ),
                (
                    "A rumor says they already started.",
                    "The pronoun and actuality remain unsupported.",
                ),
            ),
            "A specific person leads the quartz audit.",
            "an unresolved person",
            "leads audit",
            "quartz audit",
            "abstain",
            "project",
            "coreference_resolution",
            "multi_evidence_set",
            "audit.unresolved_leader",
            "resolve_audit_leader",
            ("leader_identity", "supported_modality"),
        ),
    )
    support_semantics = _l2_support_semantics()
    return tuple(
        _make_l2_blueprint(
            family=family,
            ordinal=ordinal,
            turns=turns,
            statement=statement,
            subject=subject,
            predicate_surface=predicate,
            object_value=object_value,
            decision=decision,
            kind=kind,
            abstraction_method=method,
            closure_pattern=closure,
            sense=sense,
            operator=operator,
            support_semantics=support_semantics[(family, ordinal)],
            unresolved=unresolved,
        )
        for (
            family,
            ordinal,
            turns,
            statement,
            subject,
            predicate,
            object_value,
            decision,
            kind,
            method,
            closure,
            sense,
            operator,
            unresolved,
        ) in specs
    )


_L1_BLUEPRINTS = _l1_specs()
_L2_BLUEPRINTS = _l2_specs()


def _validate_evidence_offsets_l1(blueprint: L1Blueprint) -> None:
    for evidence in blueprint.untyped_candidate.evidence:
        message = blueprint.source_turn[evidence.message]
        if (
            evidence.end <= evidence.start
            or message[evidence.start : evidence.end] != evidence.quote
        ):
            raise ValueError(
                f"L1 evidence offset mismatch: {blueprint.blueprint_id}"
            )


def _validate_evidence_offsets_l2(blueprint: L2Blueprint) -> None:
    turns = {turn.source_turn_ref: turn for turn in blueprint.source_turns}
    evidence_messages: dict[str, str] = {}
    for support in blueprint.typed_l1_support_pack:
        turn = turns.get(support.source_turn_ref)
        if turn is None:
            raise ValueError("L2 support references unknown source turn")
        for binding in support.evidence_bindings:
            evidence_messages[binding.evidence_id] = (
                turn.user if binding.speaker == "user" else turn.agent
            )
    for evidence in blueprint.untyped_candidate.evidence:
        message = evidence_messages.get(evidence.evidence_id)
        if (
            message is None
            or evidence.end <= evidence.start
            or message[evidence.start : evidence.end] != evidence.quote
        ):
            raise ValueError(
                f"L2 evidence offset mismatch: {blueprint.blueprint_id}"
            )


_L1_CATALOG_ENTRIES = (
    ("record_handoff", "transfer.handoff", "event", (("giver", "handoff source"), ("theme", "transferred item"), ("recipient", "handoff recipient"))),
    ("calibrate_sensor", "maintenance.calibration", "event", (("technician", "primary technician"), ("theme", "calibrated sensor"), ("participant", "assisting technician"))),
    ("deliver_parcel", "logistics.delivery", "event", (("courier", "delivery actor"), ("theme", "delivered parcel"), ("origin", "delivery origin"), ("recipient", "delivery recipient"))),
    ("review_contract", "document.client_review", "event", (("reviewer", "contract reviewer"), ("theme", "reviewed contract"), ("beneficiary", "review client"))),
    ("publish_note", "task.conditional_publish", "task", (("actor", "publishing actor"), ("theme", "publication note"), ("condition", "publication condition"))),
    ("keep_dashboard_private", "privacy.workspace_scope", "state", (("theme", "private dashboard"), ("scope", "workspace scope"))),
    ("route_invoice", "billing.account_route", "state", (("theme", "routed invoice"), ("recipient", "invoice recipient"), ("scope", "account scope"))),
    ("schedule_deployment", "release.conditional_schedule", "task", (("actor", "request owner"), ("theme", "scheduled deployment"), ("condition", "schedule condition"))),
    ("inspect_vault", "inspection.planned_vault", "task", (("actor", "inspection actor"), ("theme", "inspected vault"))),
    ("reserve_lab", "reservation.request_lab", "task", (("actor", "reservation requester"), ("theme", "reserved lab"))),
    ("permit_valid_until", "permit.validity", "state", (("holder", "permit holder"), ("theme", "permit"))),
    ("move_briefing", "briefing.unresolved_time", "task", (("actor", "request owner"), ("theme", "briefing"), ("temporal_anchor", "relative time anchor"))),
    ("reschedule_review", "review.rescheduled", "state", (("theme", "review"), ("prior_time", "replaced schedule"), ("current_time", "current schedule"))),
    ("replace_access_code", "access.code_replacement", "state", (("theme", "locker"), ("current_value", "replacement code"))),
    ("correct_folder", "document.folder_correction", "state", (("theme", "corrected field"), ("prior_value", "incorrect folder"), ("current_value", "correct folder"))),
    ("record_batch_conflict", "test.conflicting_outcomes", "state", (("theme", "test batch"), ("outcome", "signed outcome"), ("conflicting_outcome", "conflicting signed outcome"))),
    ("observe_pressure", "sensor.pressure_observation", "state", (("theme", "observed gauge"), ("value", "pressure reading"))),
    ("recommend_archive", "assistant.archive_recommendation", "task", (("actor", "recommending assistant"), ("theme", "report"), ("condition", "approval condition"))),
    ("archive_draft", "document.context_archive", "task", (("actor", "requesting user"), ("theme", "draft"), ("companion", "required appendix"))),
    ("close_depot", "depot.unverified_closure", "state", (("theme", "depot"), ("source", "attributed source"))),
    ("record_unresolved_relation", "control.unresolved_relation", "state", (("theme", "unresolved theme"), ("reference", "unresolved reference"))),
)


def _l1_vocabulary() -> dict[str, list[str]]:
    return {
        "decisions": ["abstain", "emit_l1", "no_memory"],
        "kinds": ["attribute", "event", "preference", "state", "task"],
        "modalities": [
            "actual",
            "denied",
            "hypothetical",
            "planned",
            "recommended",
            "requested",
        ],
        "polarities": ["negative", "positive"],
        "speakers": ["assistant", "tool", "user"],
        "canonical_operators": sorted(
            {operator for operator, _, _, _ in _L1_CATALOG_ENTRIES}
        ),
        "predicate_senses": sorted(
            {sense for _, sense, _, _ in _L1_CATALOG_ENTRIES}
        ),
        "operator_kind_bindings": sorted(
            {
                f"{operator}|{kind}"
                for operator, _, kind, _ in _L1_CATALOG_ENTRIES
            }
        ),
        "operator_role_bindings": sorted(
            {
                f"{operator}|{role}|{role_name}"
                for operator, _, _, roles in _L1_CATALOG_ENTRIES
                for role, role_name in roles
            }
        ),
        "condition_operators": ["after", "if"],
        "scope_operators": ["only_for", "within"],
        "time_policy": [
            "explicit_iso_8601_or_null",
            "unresolved_deictic_time_requires_abstention",
        ],
        "modality_policy": [
            "explicit_supported_modality_only",
            "unverified_attribution_requires_abstention",
        ],
    }


def _render_l1(
    blueprints: tuple[L1Blueprint, ...],
    prereg: dict[str, Any],
) -> FreshV2L1Layer:
    source_cases: list[L1SourceCase] = []
    public_cases: list[L1PublicCase] = []
    authority_cases: list[L1AuthorityCase] = []
    gold_items: list[L1GoldItem] = []
    for blueprint in blueprints:
        _validate_evidence_offsets_l1(blueprint)
        untyped = _remap_untyped(blueprint.untyped_candidate)
        expected = (
            _remap_l1_candidate(blueprint.expected_typed_candidate)
            if blueprint.expected_typed_candidate is not None
            else None
        )
        evidence = [
            TypedEvidenceBinding(
                evidence_id=item.evidence_id,
                speaker=item.speaker,
            )
            for item in untyped.evidence
        ]
        case_id = _opaque("case", blueprint.private_case_id)
        candidate_ref = _opaque("candidate", blueprint.candidate_id)
        emits = expected is not None
        allowed_event = (
            [expected.time.event_time]
            if emits and expected.time.event_time
            else []
        )
        allowed_valid = (
            [expected.time.valid_time]
            if emits and expected.time.valid_time
            else []
        )
        source_cases.append(
            L1SourceCase(
                private_case_id=blueprint.private_case_id,
                knowledge_id=blueprint.knowledge_id,
                expected_decision=blueprint.expected_decision,
                expected_typed_candidate=expected,
                emission_allowed=emits,
                allowed_modalities=[expected.modality] if emits else [],
                allowed_event_times=allowed_event,
                event_time_may_be_null=not bool(allowed_event),
                allowed_valid_times=allowed_valid,
                valid_time_may_be_null=not bool(allowed_valid),
                unresolved_required_fields=list(
                    blueprint.unresolved_required_fields
                ),
                time_case=(
                    "resolved"
                    if allowed_event or allowed_valid
                    else "unresolved"
                    if "event_time" in blueprint.unresolved_required_fields
                    else "none"
                ),
            )
        )
        public_cases.append(
            L1PublicCase(
                case_id=case_id,
                candidate_ref=candidate_ref,
                source_turn=blueprint.source_turn,
                untyped_candidate=untyped,
            )
        )
        derivation = (
            expected.derivation
            if expected
            else TypedDerivationProvenance(
                method=untyped.derivation,
                basis=untyped.inference_basis,
                evidence_ids=[item.evidence_id for item in untyped.evidence],
            )
        )
        authority_cases.append(
            L1AuthorityCase(
                case_id=case_id,
                candidate_ref=candidate_ref,
                knowledge_id=blueprint.knowledge_id,
                candidate_id=blueprint.candidate_id,
                emission_allowed=emits,
                required_evidence_bindings=evidence,
                allowed_modalities=[expected.modality] if emits else [],
                allowed_polarities=(
                    [expected.polarity]
                    if emits
                    else [untyped.qualifiers.get("polarity", "positive")]
                ),
                allowed_event_times=allowed_event,
                event_time_may_be_null=not bool(allowed_event),
                allowed_valid_times=allowed_valid,
                valid_time_may_be_null=not bool(allowed_valid),
                allowed_condition_values=(
                    [binding.value for binding in expected.condition_bindings]
                    if emits
                    else []
                ),
                allowed_scope_values=(
                    [binding.value for binding in expected.scope_bindings]
                    if emits
                    else []
                ),
                required_derivation=derivation,
                required_lifecycle=(
                    expected.lifecycle if emits else untyped.lifecycle_links
                ),
                required_operation_provenance=(
                    expected.operation_provenance
                    if emits
                    else untyped.operation_provenance
                ),
                unresolved_required_fields=list(
                    blueprint.unresolved_required_fields
                ),
            )
        )
        gold_items.append(
            L1GoldItem(
                case_id=case_id,
                candidate_ref=candidate_ref,
                expected_decision=blueprint.expected_decision,
                expected_typed_candidate=expected,
            )
        )
    vocabulary = _l1_vocabulary()
    source = L1SourceConfig(
        dataset_id=DATASET_ID,
        public_vocabulary=vocabulary,
        cases=source_cases,
    )
    public = L1PublicPayload(
        dataset_id=DATASET_ID,
        case_count=len(public_cases),
        allowed_vocabulary=vocabulary,
        cases=public_cases,
    )
    authority = L1AuthorityPayload(
        dataset_id=DATASET_ID,
        case_count=len(authority_cases),
        cases=authority_cases,
    )
    gold = L1GoldPayload(
        dataset_id=DATASET_ID,
        case_count=len(gold_items),
        items=gold_items,
    )
    manifest = L1Manifest(
        dataset_id=DATASET_ID,
        case_count=len(blueprints),
        input_sha256=prereg["input_sha256"],
        output_sha256={
            "source-cases-l1.json": _hash_value(source),
            "public-l1.json": _hash_value(public),
            "authority-l1.json": _hash_value(authority),
            "gold-l1.json": _hash_value(gold),
        },
        distribution={
            "families": dict(Counter(item.family for item in blueprints)),
            "decisions": dict(
                Counter(item.expected_decision for item in blueprints)
            ),
        },
        claim_boundary={
            "pipeline_integration_authorized": False,
            "automatic_writes_authorized": False,
            "longmemeval_status": "structured_l2_identity_unresolved",
        },
    )
    return FreshV2L1Layer(
        blueprints=blueprints,
        source=source,
        public=public,
        authority=authority,
        gold=gold,
        manifest=manifest,
    )


_L2_CATALOG_ENTRIES = (
    ("compose_dossier_workflow", "document.coreference_workflow", "task"),
    ("compose_imaging_workflow", "lab.imaging_workflow", "task"),
    ("aggregate_desk_preferences", "preference.desk_profile", "preference_profile"),
    ("summarize_ankle_state", "health.persistent_ankle_stiffness", "long_running_state"),
    ("resolve_invoice_recipient", "billing.corrected_recipient", "task"),
    ("resolve_demo_schedule", "calendar.corrected_demo_date", "task"),
    ("summarize_pump_incident", "maintenance.pump_incident", "summary_event"),
    ("compose_project_progression", "project.milestone_progression", "project"),
    ("aggregate_travel_profile", "preference.travel_profile", "preference_profile"),
    ("prefer_travel_mode", "preference.travel_mode", "preference_profile"),
    ("require_refundable_lodging", "preference.refundable_lodging", "preference_profile"),
    ("compose_unrelated_project", "control.unrelated_abstraction", "project"),
    ("resolve_option_selection", "selection.unresolved_comparative", "task"),
    ("resolve_audit_leader", "audit.unresolved_leader", "project"),
)


def _l2_vocabulary() -> dict[str, list[str]]:
    return {
        "decisions": ["abstain", "emit_l2"],
        "l2_kinds": [
            "habit",
            "long_running_state",
            "preference_profile",
            "project",
            "summary_event",
            "task",
        ],
        "abstraction_methods": [
            "coreference_resolution",
            "lifecycle_resolution",
            "preference_aggregation",
            "state_summary",
            "task_composition",
        ],
        "closure_patterns": [
            "causal_answerability",
            "multi_evidence_set",
            "single_fact",
            "temporal_chain",
            "update_supersession",
        ],
        "modalities": [
            "actual",
            "denied",
            "hypothetical",
            "planned",
            "recommended",
            "requested",
        ],
        "polarities": ["negative", "positive"],
        "canonical_operators": sorted(
            {operator for operator, _, _ in _L2_CATALOG_ENTRIES}
        ),
        "predicate_senses": sorted(
            {sense for _, sense, _ in _L2_CATALOG_ENTRIES}
        ),
        "operator_sense_bindings": sorted(
            {
                f"{operator}|{sense}"
                for operator, sense, _ in _L2_CATALOG_ENTRIES
            }
        ),
        "operator_kind_bindings": sorted(
            {
                f"{operator}|{kind}"
                for operator, _, kind in _L2_CATALOG_ENTRIES
            }
        ),
    }


def _render_l2(
    blueprints: tuple[L2Blueprint, ...],
    prereg: dict[str, Any],
) -> FreshV2L2Layer:
    source_cases: list[L2SourceCase] = []
    public_cases: list[L2PublicCase] = []
    authority_cases: list[L2AuthorityCase] = []
    gold_items: list[L2GoldItem] = []
    for blueprint in blueprints:
        _validate_evidence_offsets_l2(blueprint)
        case_id = _opaque("case", blueprint.private_case_id)
        candidate_ref = _opaque("candidate", blueprint.candidate_id)
        supports = list(blueprint.typed_l1_support_pack)
        expected = blueprint.expected_typed_candidate
        support_refs = [item.support_ref for item in supports]
        evidence = [
            binding for item in supports for binding in item.evidence_bindings
        ]
        turn_refs = [item.source_turn_ref for item in supports]
        emits = expected is not None
        source_cases.append(
            L2SourceCase(
                private_case_id=blueprint.private_case_id,
                knowledge_id=blueprint.knowledge_id,
                expected_decision=blueprint.expected_decision,
                typed_l1_support_pack=supports,
                expected_typed_candidate=expected,
                emission_allowed=emits,
                allowed_abstraction_methods=(
                    [expected.abstraction.method] if emits else []
                ),
                allowed_closure_patterns=(
                    [expected.closure.pattern] if emits else []
                ),
                unresolved_required_fields=list(
                    blueprint.unresolved_required_fields
                ),
            )
        )
        public_cases.append(
            L2PublicCase(
                case_id=case_id,
                candidate_ref=candidate_ref,
                source_session_ref=blueprint.source_session_ref,
                source_turns=[
                    L2PublicTurn(
                        source_turn_ref=item.source_turn_ref,
                        turn_index=item.turn_index,
                        user=item.user,
                        agent=item.agent,
                    )
                    for item in blueprint.source_turns
                ],
                untyped_candidate=blueprint.untyped_candidate,
                typed_l1_support_pack=supports,
            )
        )
        authority_cases.append(
            L2AuthorityCase(
                case_id=case_id,
                candidate_ref=candidate_ref,
                knowledge_id=blueprint.knowledge_id,
                candidate_id=blueprint.candidate_id,
                emission_allowed=emits,
                required_support_refs=support_refs,
                required_evidence_bindings=evidence,
                required_source_turn_refs=turn_refs,
                required_source_session_refs=[blueprint.source_session_ref],
                allowed_abstraction_methods=(
                    [expected.abstraction.method] if emits else []
                ),
                allowed_closure_patterns=(
                    [expected.closure.pattern] if emits else []
                ),
                unresolved_required_fields=list(
                    blueprint.unresolved_required_fields
                ),
            )
        )
        gold_items.append(
            L2GoldItem(
                case_id=case_id,
                candidate_ref=candidate_ref,
                expected_decision=blueprint.expected_decision,
                expected_typed_candidate=expected,
            )
        )
    vocabulary = _l2_vocabulary()
    source = L2SourceConfig(
        dataset_id=DATASET_ID,
        public_vocabulary=vocabulary,
        cases=source_cases,
    )
    public = L2PublicPayload(
        dataset_id=DATASET_ID,
        case_count=len(public_cases),
        allowed_vocabulary=vocabulary,
        cases=public_cases,
    )
    authority = L2AuthorityPayload(
        dataset_id=DATASET_ID,
        case_count=len(authority_cases),
        cases=authority_cases,
    )
    gold = L2GoldPayload(
        dataset_id=DATASET_ID,
        case_count=len(gold_items),
        items=gold_items,
    )
    manifest = L2Manifest(
        dataset_id=DATASET_ID,
        case_count=len(blueprints),
        input_sha256=prereg["input_sha256"],
        l1_qualification_sha256={
            "fresh-v2-l1-blueprints": _hash_value(
                [item.model_dump(mode="json") for item in _L1_BLUEPRINTS]
            )
        },
        output_sha256={
            "source-cases-l2.json": _hash_value(source),
            "public-l2.json": _hash_value(public),
            "authority-l2.json": _hash_value(authority),
            "gold-l2.json": _hash_value(gold),
        },
        distribution={
            "families": dict(Counter(item.family for item in blueprints)),
            "decisions": dict(
                Counter(item.expected_decision for item in blueprints)
            ),
        },
        thresholds=(
            prereg["quality_thresholds"]["l2"]
            | prereg["safety_thresholds"]
        ),
        claim_boundary={
            "pipeline_integration_authorized": False,
            "automatic_writes_authorized": False,
            "longmemeval_status": "structured_l2_identity_unresolved",
        },
    )
    return FreshV2L2Layer(
        blueprints=blueprints,
        source=source,
        public=public,
        authority=authority,
        gold=gold,
        manifest=manifest,
    )


_CROSS_CASE_ID_KEYS = {
    "blueprint_id",
    "private_case_id",
    "knowledge_id",
    "candidate_id",
    "private_session_id",
    "private_turn_id",
    "case_id",
    "candidate_ref",
    "support_ref",
    "source_turn_ref",
    "source_turn_refs",
    "source_session_ref",
    "source_session_refs",
    "supporting_l1_refs",
    "required_support_refs",
    "optional_support_refs",
    "replacement_candidate_ref",
    "replaces_candidate_refs",
    "supersedes_candidate_refs",
    "conflicts_with_candidate_refs",
    "confirmed_by_operation_refs",
    "added_by_operation_refs",
}
_SEMANTIC_DROP_KEYS = {
    "evidence",
    "evidence_bindings",
    "evidence_ids",
    "candidate_ref",
    "case_id",
    "source_turn_refs",
    "source_session_refs",
    "replacement_candidate_ref",
    "replaces_candidate_refs",
    "supersedes_candidate_refs",
    "conflicts_with_candidate_refs",
    "operation_provenance",
}


def _scan_ids(
    value: Any,
    *,
    key: str = "",
) -> tuple[set[str], set[str]]:
    ids: set[str] = set()
    evidence_ids: set[str] = set()
    if isinstance(value, dict):
        for child_key, child in value.items():
            child_ids, child_evidence = _scan_ids(child, key=child_key)
            ids.update(child_ids)
            evidence_ids.update(child_evidence)
    elif isinstance(value, list):
        for child in value:
            child_ids, child_evidence = _scan_ids(child, key=key)
            ids.update(child_ids)
            evidence_ids.update(child_evidence)
    elif isinstance(value, str):
        if key in _CROSS_CASE_ID_KEYS or re.match(
            r"^(case|candidate|support|turn|session|operation)-",
            value,
        ):
            ids.add(value)
        if key == "evidence_id" or value.startswith("evidence-"):
            evidence_ids.add(value)
    return ids, evidence_ids


def _semantic_plain(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if isinstance(value, dict):
        return {
            key: _semantic_plain(child)
            for key, child in sorted(value.items())
            if key not in _SEMANTIC_DROP_KEYS
        }
    if isinstance(value, list):
        return [_semantic_plain(child) for child in value]
    if isinstance(value, str):
        return _normalize_text(value)
    return value


def _replace_semantic_refs(value: Any, mapping: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {
            key: _replace_semantic_refs(child, mapping)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_replace_semantic_refs(child, mapping) for child in value]
    if isinstance(value, str):
        return mapping.get(value, value)
    return value


def _normalize_semantic_support_refs(value: Any) -> Any:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if not isinstance(value, dict):
        return value
    refs = value.get("supporting_l1_refs")
    if not isinstance(refs, list) or not all(
        isinstance(item, str) for item in refs
    ):
        return value
    mapping = {
        item: f"support-{index:02d}"
        for index, item in enumerate(refs, start=1)
    }
    return _replace_semantic_refs(value, mapping)


def _semantic_signature(
    decision: str,
    untyped: Any,
    typed: Any,
) -> str:
    return _hash_value(
        {
            "decision": decision,
            "untyped": _semantic_plain(untyped),
            "typed": _semantic_plain(
                _normalize_semantic_support_refs(typed)
            ),
        }
    )


def _collect_source_texts(value: Any) -> set[str]:
    output: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"user", "agent"} and isinstance(child, str):
                if child.strip():
                    output.add(_normalize_text(child))
            output.update(_collect_source_texts(child))
    elif isinstance(value, list):
        for child in value:
            output.update(_collect_source_texts(child))
    return output


def _collect_semantic_signatures(value: Any) -> set[str]:
    output: set[str] = set()
    if isinstance(value, dict):
        if "expected_decision" in value and "untyped_candidate" in value:
            output.add(
                _semantic_signature(
                    value["expected_decision"],
                    value["untyped_candidate"],
                    value.get("expected_typed_candidate"),
                )
            )
        for child in value.values():
            output.update(_collect_semantic_signatures(child))
    elif isinstance(value, list):
        for child in value:
            output.update(_collect_semantic_signatures(child))
    return output


def _collect_cross_file_semantic_signatures(
    payloads: dict[str, dict[str, Any]],
) -> set[str]:
    groups: dict[str, dict[str, dict[str, Any]]] = {}
    for label, payload in payloads.items():
        group, _, filename = label.rpartition("/")
        if filename.startswith("public-"):
            groups.setdefault(group, {})["public"] = payload
        elif filename.startswith("gold-"):
            groups.setdefault(group, {})["gold"] = payload

    signatures: set[str] = set()
    for group, pair in groups.items():
        if set(pair) != {"public", "gold"}:
            continue
        public_cases = pair["public"].get("cases")
        gold_items = pair["gold"].get("items")
        if not isinstance(public_cases, list) or not isinstance(
            gold_items, list
        ):
            raise ValueError(
                f"prior semantic join payload shape drift: {group}"
            )
        public_by_id = {
            item["case_id"]: item
            for item in public_cases
            if isinstance(item, dict)
            and isinstance(item.get("case_id"), str)
        }
        gold_by_id = {
            item["case_id"]: item
            for item in gold_items
            if isinstance(item, dict)
            and isinstance(item.get("case_id"), str)
        }
        if set(public_by_id) != set(gold_by_id):
            raise ValueError(
                f"prior semantic join case parity drift: {group}"
            )
        for case_id in sorted(public_by_id):
            public_item = public_by_id[case_id]
            gold_item = gold_by_id[case_id]
            if "untyped_candidate" not in public_item or (
                "expected_decision" not in gold_item
            ):
                raise ValueError(
                    f"prior semantic join field drift: {group}/{case_id}"
                )
            signatures.add(
                _semantic_signature(
                    gold_item["expected_decision"],
                    public_item["untyped_candidate"],
                    gold_item.get("expected_typed_candidate"),
                )
            )
    return signatures


def _prior_inventory(
    preregistration: dict[str, Any],
) -> AuthoringInventory:
    paths = _input_paths(WORKSPACE_ROOT)
    if set(paths) != set(preregistration["input_sha256"]):
        raise ValueError("preregistration prior input registry drift")
    ids: set[str] = set()
    evidence_ids: set[str] = set()
    texts: set[str] = set()
    signatures: set[str] = set()
    json_payloads: dict[str, dict[str, Any]] = {}
    for label, path in paths.items():
        if sha256_file(path) != preregistration["input_sha256"][label]:
            raise ValueError(
                f"preregistration prior input hash drift: {label}"
            )
        if path.suffix != ".json":
            continue
        payload = load_json(path)
        if not isinstance(payload, dict):
            raise ValueError(f"prior JSON payload must be an object: {label}")
        json_payloads[label] = payload
        found_ids, found_evidence = _scan_ids(payload)
        ids.update(found_ids)
        evidence_ids.update(found_evidence)
        texts.update(_collect_source_texts(payload))
        signatures.update(_collect_semantic_signatures(payload))
    signatures.update(_collect_cross_file_semantic_signatures(json_payloads))
    return AuthoringInventory(
        input_sha256=preregistration["input_sha256"],
        private_or_public_ids=tuple(sorted(ids)),
        evidence_ids=tuple(sorted(evidence_ids)),
        normalized_source_texts=tuple(sorted(texts)),
        semantic_signatures=tuple(sorted(signatures)),
    )


def _current_inventory(
    l1: FreshV2L1Layer,
    l2: FreshV2L2Layer,
    input_sha256: dict[str, str],
) -> AuthoringInventory:
    payload = {
        "l1": l1.model_dump(mode="json"),
        "l2": l2.model_dump(mode="json"),
    }
    ids, evidence_ids = _scan_ids(payload)
    texts = {
        _normalize_text(text)
        for blueprint in l1.blueprints
        for text in blueprint.source_turn.values()
    }
    texts.update(
        _normalize_text(text)
        for blueprint in l2.blueprints
        for turn in blueprint.source_turns
        for text in (turn.user, turn.agent)
    )
    signatures = {
        _semantic_signature(
            item.expected_decision,
            item.untyped_candidate,
            item.expected_typed_candidate,
        )
        for item in [*l1.blueprints, *l2.blueprints]
    }
    return AuthoringInventory(
        input_sha256=input_sha256,
        private_or_public_ids=tuple(sorted(ids)),
        evidence_ids=tuple(sorted(evidence_ids)),
        normalized_source_texts=tuple(sorted(texts)),
        semantic_signatures=tuple(sorted(signatures)),
    )


def _validate_preregistration(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"preregistration missing: {path}")
    if path.stat().st_mode & 0o222:
        raise ValueError("preregistration must be read-only")
    if sha256_file(path) != PREREGISTRATION_SHA256:
        raise ValueError("preregistration hash drift")
    payload = load_json(path)
    if (
        payload.get("schema_version") != PREREGISTRATION_SCHEMA
        or payload.get("evaluation_id") != DATASET_ID
    ):
        raise ValueError("preregistration contract drift")
    return payload


def _validate_family_order(bundle: FreshV2AuthoringBundle) -> None:
    expected_l1 = [
        (family, ordinal)
        for family in L1_FAMILIES
        for ordinal in range(1, L1_FAMILIES[family] + 1)
    ]
    expected_l2 = [
        (family, ordinal)
        for family in L2_FAMILIES
        for ordinal in range(1, L2_FAMILIES[family] + 1)
    ]
    actual_l1 = [
        (item.family, item.ordinal) for item in bundle.l1.blueprints
    ]
    actual_l2 = [
        (item.family, item.ordinal) for item in bundle.l2.blueprints
    ]
    if actual_l1 != expected_l1 or actual_l2 != expected_l2:
        raise ValueError("authoring blueprint family/order contract drift")
    expected_ids = [
        f"fresh-v2-l1-{family}-{ordinal:02d}"
        for family, ordinal in expected_l1
    ] + [
        f"fresh-v2-l2-{family}-{ordinal:02d}"
        for family, ordinal in expected_l2
    ]
    blueprint_ids = [
        item.blueprint_id
        for item in [*bundle.l1.blueprints, *bundle.l2.blueprints]
    ]
    if len(blueprint_ids) != len(set(blueprint_ids)):
        raise ValueError("duplicate authoring blueprint ID")
    if blueprint_ids != expected_ids:
        raise ValueError("authoring blueprint ID contract drift")


def _validate_contamination(
    current: AuthoringInventory,
    prior: AuthoringInventory,
) -> None:
    checks = (
        (
            "identifier",
            set(current.private_or_public_ids),
            set(prior.private_or_public_ids),
        ),
        (
            "evidence",
            set(current.evidence_ids),
            set(prior.evidence_ids),
        ),
        (
            "source",
            {
                _normalize_text(item)
                for item in current.normalized_source_texts
            },
            {
                _normalize_text(item)
                for item in prior.normalized_source_texts
            },
        ),
        (
            "semantic",
            set(current.semantic_signatures),
            set(prior.semantic_signatures),
        ),
    )
    for label, current_values, prior_values in checks:
        overlap = current_values & prior_values
        if overlap:
            first = next(iter(sorted(overlap)))
            raise ValueError(f"{label} contamination detected: {first}")


def _validate_l2_primary_literal_binding(blueprint: L2Blueprint) -> None:
    expected = blueprint.expected_typed_candidate
    if expected is None:
        return
    primary = expected.structured_claims[0]
    entities = {
        entity.local_entity_id: entity.surface
        for entity in primary.local_entities
    }
    theme_surfaces = {
        entities[role.local_entity_id]
        for role in primary.roles
        if role.role == "theme"
    }
    untyped = blueprint.untyped_candidate
    if (
        primary.predicate.surface != untyped.predicate
        or primary.local_entities[0].surface != untyped.subject
        or theme_surfaces != {untyped.object}
        or primary.supporting_l1_refs != expected.supporting_l1_refs
    ):
        raise ValueError("L2 primary claim literal binding drift")


def build_fresh_v2_authoring_bundle(
    preregistration_path: Path,
) -> FreshV2AuthoringBundle:
    prereg = _validate_preregistration(preregistration_path)
    l1 = _render_l1(_L1_BLUEPRINTS, prereg)
    l2 = _render_l2(_L2_BLUEPRINTS, prereg)
    bundle = FreshV2AuthoringBundle(
        l1=l1,
        l2=l2,
        prior_inventory=_prior_inventory(prereg),
        current_inventory=_current_inventory(
            l1,
            l2,
            prereg["input_sha256"],
        ),
    )
    validate_fresh_v2_authoring_bundle(bundle, preregistration_path)
    return bundle


def validate_fresh_v2_authoring_bundle(
    bundle: FreshV2AuthoringBundle,
    preregistration_path: Path,
) -> dict[str, Any]:
    bundle = FreshV2AuthoringBundle.model_validate_json(
        bundle.model_dump_json()
    )
    prereg = _validate_preregistration(preregistration_path)
    if bundle.preregistration_sha256 != sha256_file(preregistration_path):
        raise ValueError("authoring bundle preregistration drift")
    _validate_family_order(bundle)
    for item in bundle.l1.blueprints:
        _validate_evidence_offsets_l1(item)
    for item in bundle.l2.blueprints:
        _validate_evidence_offsets_l2(item)
        if item.expected_typed_candidate is not None:
            TypedL2Candidate.model_validate(
                item.expected_typed_candidate.model_dump(mode="json")
            )
            _validate_l2_primary_literal_binding(item)
    expected_current = _current_inventory(
        bundle.l1,
        bundle.l2,
        prereg["input_sha256"],
    )
    if bundle.current_inventory != expected_current:
        raise ValueError("authoring current inventory drift")
    _validate_contamination(
        bundle.current_inventory,
        bundle.prior_inventory,
    )
    expected_prior = _prior_inventory(prereg)
    if bundle.prior_inventory != expected_prior:
        raise ValueError("authoring prior inventory drift")
    return {
        "status": "valid",
        "evaluation_id": DATASET_ID,
        "l1_case_count": len(bundle.l1.blueprints),
        "l2_case_count": len(bundle.l2.blueprints),
        "prior_input_count": len(bundle.prior_inventory.input_sha256),
    }


def _code_paths(workspace_root: Path) -> dict[str, Path]:
    return {
        "module": Path(__file__).resolve(),
        "test": (workspace_root / TEST_RELATIVE_PATH).resolve(),
    }


def _dependency_paths(workspace_root: Path) -> dict[str, Path]:
    root = workspace_root / "tools/natural_memory_benchmark"
    return {
        "io.py": root / "io.py",
        "typed_extractor_fresh_v2_prereg.py": (
            root / "typed_extractor_fresh_v2_prereg.py"
        ),
        "typed_extractor_l1.py": root / "typed_extractor_l1.py",
        "typed_extractor_l2.py": root / "typed_extractor_l2.py",
    }


def _receipt_payload(
    preregistration_path: Path,
    evaluation_root: Path,
    workspace_root: Path,
    receipt_time: str,
) -> AuthoringReceipt:
    prereg = _validate_preregistration(preregistration_path)
    if evaluation_root.exists():
        raise ValueError(
            f"formal evaluation root must be absent: {evaluation_root}"
        )
    bundle = build_fresh_v2_authoring_bundle(preregistration_path)
    code_paths = _code_paths(workspace_root)
    dependencies = _dependency_paths(workspace_root)
    for label, path in {**code_paths, **dependencies}.items():
        if not path.is_file():
            raise FileNotFoundError(
                f"authoring implementation dependency missing: {label}"
            )
    return AuthoringReceipt(
        preregistration_path=str(preregistration_path.resolve()),
        formal_evaluation_root=str(evaluation_root.resolve()),
        receipt_time=receipt_time,
        code_sha256={
            label: sha256_file(path) for label, path in code_paths.items()
        },
        dependency_sha256={
            label: sha256_file(path) for label, path in dependencies.items()
        },
        blueprint_manifest_sha256={
            "l1": _hash_value(
                [
                    item.model_dump(mode="json")
                    for item in bundle.l1.blueprints
                ]
            ),
            "l2": _hash_value(
                [
                    item.model_dump(mode="json")
                    for item in bundle.l2.blueprints
                ]
            ),
        },
        family_counts={"l1": L1_FAMILIES, "l2": L2_FAMILIES},
        prior_input_sha256=prereg["input_sha256"],
        automatic_write_counts={
            "aggregate": 0,
            "closure": 0,
            "identity": 0,
            "l1": 0,
            "l2": 0,
            "membership": 0,
            "revision": 0,
            "snapshot": 0,
            "source_revision": 0,
        },
    )


def freeze_fresh_v2_authoring_receipt(
    preregistration_path: Path,
    evaluation_root: Path,
    workspace_root: Path,
    receipt_time: str,
) -> dict[str, Any]:
    receipt = _receipt_payload(
        preregistration_path,
        evaluation_root,
        workspace_root,
        receipt_time,
    )
    path = preregistration_path.parent / RECEIPT_NAME
    content = canonical_json_bytes(receipt)
    if path.exists() and path.read_bytes() != content:
        raise ValueError(
            f"authoring receipt already exists and differs: {path}"
        )
    write_json_immutable(path, receipt)
    path.chmod(0o444)
    return receipt.model_dump(mode="json")


def validate_fresh_v2_authoring_receipt(
    preregistration_path: Path,
    evaluation_root: Path,
    workspace_root: Path,
) -> dict[str, Any]:
    path = preregistration_path.parent / RECEIPT_NAME
    if not path.is_file():
        raise FileNotFoundError(f"authoring receipt missing: {path}")
    if path.stat().st_mode & 0o222:
        raise ValueError("authoring receipt must be read-only")
    raw = load_json(path)
    if raw.get("preregistration_sha256") != PREREGISTRATION_SHA256:
        raise ValueError("authoring receipt preregistration drift")
    actual = AuthoringReceipt.model_validate(raw)
    expected = _receipt_payload(
        preregistration_path,
        evaluation_root,
        workspace_root,
        actual.receipt_time,
    )
    if canonical_json_bytes(actual) != canonical_json_bytes(expected):
        raise ValueError("authoring receipt drift")
    return actual.model_dump(mode="json")


def _validate_superseded_authoring_receipt(
    preregistration_path: Path,
) -> tuple[Path, AuthoringReceipt]:
    path = preregistration_path.parent / RECEIPT_NAME
    if not path.is_file():
        raise ValueError(f"superseded authoring receipt missing: {path}")
    if path.stat().st_mode & 0o777 != 0o444:
        raise ValueError("superseded authoring receipt must have mode 0444")
    if sha256_file(path) != SUPERSEDED_RECEIPT_SHA256:
        raise ValueError("superseded authoring receipt hash drift")
    try:
        receipt = AuthoringReceipt.model_validate(load_json(path))
    except Exception as exc:
        raise ValueError("superseded authoring receipt schema drift") from exc
    return path, receipt


def _supersession_receipt_payload(
    preregistration_path: Path,
    evaluation_root: Path,
    workspace_root: Path,
    receipt_time: str,
) -> AuthoringSupersessionReceipt:
    predecessor_path, _ = _validate_superseded_authoring_receipt(
        preregistration_path
    )
    current = _receipt_payload(
        preregistration_path,
        evaluation_root,
        workspace_root,
        receipt_time,
    )
    return AuthoringSupersessionReceipt(
        preregistration_path=current.preregistration_path,
        supersedes_receipt_path=str(predecessor_path.resolve()),
        formal_evaluation_root=current.formal_evaluation_root,
        receipt_time=current.receipt_time,
        code_sha256=current.code_sha256,
        dependency_sha256=current.dependency_sha256,
        blueprint_manifest_sha256=current.blueprint_manifest_sha256,
        family_counts=current.family_counts,
        prior_input_sha256=current.prior_input_sha256,
        automatic_write_counts=current.automatic_write_counts,
    )


def freeze_fresh_v2_authoring_supersession_receipt(
    preregistration_path: Path,
    evaluation_root: Path,
    workspace_root: Path,
    receipt_time: str,
) -> dict[str, Any]:
    receipt = _supersession_receipt_payload(
        preregistration_path,
        evaluation_root,
        workspace_root,
        receipt_time,
    )
    path = preregistration_path.parent / SUPERSESSION_RECEIPT_NAME
    content = canonical_json_bytes(receipt)
    if path.exists() and path.read_bytes() != content:
        raise ValueError(
            f"authoring supersession receipt already exists and differs: {path}"
        )
    write_json_immutable(path, receipt)
    path.chmod(0o444)
    return receipt.model_dump(mode="json")


def validate_fresh_v2_authoring_supersession_receipt(
    preregistration_path: Path,
    evaluation_root: Path,
    workspace_root: Path,
) -> dict[str, Any]:
    path = preregistration_path.parent / SUPERSESSION_RECEIPT_NAME
    if not path.is_file():
        raise FileNotFoundError(f"authoring supersession receipt missing: {path}")
    if path.stat().st_mode & 0o777 != 0o444:
        raise ValueError("authoring supersession receipt must have mode 0444")
    actual = AuthoringSupersessionReceipt.model_validate(load_json(path))
    expected = _supersession_receipt_payload(
        preregistration_path,
        evaluation_root,
        workspace_root,
        actual.receipt_time,
    )
    if canonical_json_bytes(actual) != canonical_json_bytes(expected):
        raise ValueError("authoring supersession receipt drift")
    return actual.model_dump(mode="json")


def validate_fresh_v2_active_authoring_receipt(
    preregistration_path: Path,
    evaluation_root: Path,
    workspace_root: Path,
) -> dict[str, Any]:
    supersession_path = preregistration_path.parent / SUPERSESSION_RECEIPT_NAME
    if supersession_path.exists():
        return validate_fresh_v2_authoring_supersession_receipt(
            preregistration_path,
            evaluation_root,
            workspace_root,
        )
    return validate_fresh_v2_authoring_receipt(
        preregistration_path,
        evaluation_root,
        workspace_root,
    )
