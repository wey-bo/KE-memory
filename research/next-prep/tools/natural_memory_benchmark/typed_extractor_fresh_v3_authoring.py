from __future__ import annotations

import ctypes
import errno
import fcntl
import hashlib
import json
import os
import stat
import unicodedata
from collections import Counter
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from .authoritative_conformance_runner import build_authoritative_conformance_bundle
from .authoritative_memory import canonical_sha256
from .io import canonical_json_bytes, load_json, sha256_file
from .typed_extractor_fresh_v3_prereg import (
    L1_FAMILIES,
    L2_FAMILIES,
    _code_paths as _preregistration_code_paths,
    _input_paths as preregistration_input_paths,
)
from .typed_extractor_l1 import (
    L1AuthorityCase,
    L1AuthorityPayload,
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


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
PREREGISTRATION_SHA256 = (
    "183cf6fc2991361e5da57b17e06a5970f651000986d50b87e8af2e6796440204"
)
PREREGISTRATION_SCHEMA = "typed-extractor-fresh-v3-preregistration-v1"
EVALUATION_ID = "typed-extractor-v3-fresh-hidden-v1"
L1_DATASET_ID = f"{EVALUATION_ID}-l1"
L2_DATASET_ID = f"{EVALUATION_ID}-l2"
OPAQUE_NAMESPACE = "typed-extractor-fresh-hidden-v3-authored:2026-07-29"
RECEIPT_NAME = "authoring-implementation-receipt.json"
CANDIDATE_QUEUE_SHA256 = (
    "518ead9de8627a9a4384df8cdd9b8728a21fcf797f6b0f3d208dfcb28ac41c0f"
)
GUARD_FINGERPRINT = (
    "e184b6caf2998acf1c8700bc84d24bbafd49ab9c8f15738d1af8cc484ee5ebcc"
)
GUARD_RESULTS_WORKSPACE_PATH = (
    "artifacts/natural-benchmark-slices/slice-v1/"
    "symbolic-fallback-answerability-v2-fastembed-results.json"
)
GUARD_RESULTS_SHA256 = (
    "f90ee6a8d9ee4a0beb993ae2055c2e7ededd013de9a70e6ce588efbbfedd2645"
)
GUARD_COUNTS = {
    "closure_evaluation_count": 6,
    "closure_spec_count": 6,
    "l1_unit_count": 13,
    "l2_unit_count": 1,
    "query_plan_count": 5,
    "raw_artifact_revision_count": 2,
    "source_record_revision_count": 13,
    "unit_revision_count": 14,
}
_AT_EMPTY_PATH = 0x1000

MATERIALIZATION_WORKSPACE_PATHS = (
    "tools/natural_memory_benchmark/typed_extractor_fresh_v3_materialization.py",
    "tests/natural_memory_benchmark/"
    "test_typed_extractor_fresh_v3_materialization.py",
)

AUTOMATIC_WRITE_COUNTS = {
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


class PriorInventory(StrictModel):
    identifiers: list[str]
    evidence_ids: list[str]
    evidence_texts: list[str]
    source_texts: list[str]
    semantic_signatures: list[str]


class L1Blueprint(StrictModel):
    family: str = Field(min_length=1)
    ordinal: int = Field(ge=1)
    blueprint_id: str = Field(min_length=1)
    private_case_id: str = Field(min_length=1)
    knowledge_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    vocabulary_operator: str = Field(min_length=1)
    vocabulary_sense: str = Field(min_length=1)
    source_turn: dict[Literal["user", "agent"], str]
    untyped_candidate: PublicUntypedCandidate
    expected_decision: Literal["emit_l1", "abstain", "no_memory"]
    expected_typed_candidate: TypedL1Candidate | None = None
    unresolved_required_fields: list[str] = Field(default_factory=list)


class L2SupportLifecycleBinding(StrictModel):
    support_ref: str = Field(pattern=r"^support-[0-9a-f]{16}$")
    relation: Literal["superseded_by", "supersedes"]
    counterpart_support_ref: str = Field(pattern=r"^support-[0-9a-f]{16}$")


class L2Blueprint(StrictModel):
    family: str = Field(min_length=1)
    ordinal: int = Field(ge=1)
    blueprint_id: str = Field(min_length=1)
    private_case_id: str = Field(min_length=1)
    knowledge_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    vocabulary_operator: str = Field(min_length=1)
    vocabulary_sense: str = Field(min_length=1)
    private_session_id: str = Field(min_length=1)
    source_session_ref: str = Field(pattern=r"^session-[0-9a-f]{16}$")
    source_turns: tuple[L2PublicTurn, ...]
    untyped_candidate: PublicUntypedCandidate
    typed_l1_support_pack: tuple[TypedL1SupportCandidate, ...]
    support_lifecycle_bindings: tuple[L2SupportLifecycleBinding, ...] = ()
    expected_decision: Literal["emit_l2", "abstain"]
    expected_typed_candidate: TypedL2Candidate | None = None
    unresolved_required_fields: list[str] = Field(default_factory=list)
class FreshV3L1Layer(StrictModel):
    blueprints: tuple[L1Blueprint, ...]
    source: L1SourceConfig
    public: L1PublicPayload
    authority: L1AuthorityPayload
    gold: L1GoldPayload
    manifest: L1Manifest


class FreshV3L2Layer(StrictModel):
    blueprints: tuple[L2Blueprint, ...]
    source: L2SourceConfig
    public: L2PublicPayload
    authority: L2AuthorityPayload
    gold: L2GoldPayload
    manifest: L2Manifest


class FreshV3AuthoringBundle(StrictModel):
    schema_version: Literal["typed-extractor-fresh-v3-authoring-bundle-v1"] = (
        "typed-extractor-fresh-v3-authoring-bundle-v1"
    )
    evaluation_id: Literal["typed-extractor-v3-fresh-hidden-v1"] = EVALUATION_ID
    preregistration_sha256: Literal[
        "183cf6fc2991361e5da57b17e06a5970f651000986d50b87e8af2e6796440204"
    ] = PREREGISTRATION_SHA256
    prior_inventory_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    l1: FreshV3L1Layer
    l2: FreshV3L2Layer


class FreshV3AuthoringReceipt(StrictModel):
    schema_version: Literal[
        "typed-extractor-fresh-v3-authoring-receipt-v1"
    ] = "typed-extractor-fresh-v3-authoring-receipt-v1"
    status: Literal["frozen"] = "frozen"
    evaluation_id: Literal["typed-extractor-v3-fresh-hidden-v1"] = EVALUATION_ID
    receipt_time: str = Field(
        pattern=r"^2026-07-29T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
    )
    receipt_time_source: Literal[
        "caller_supplied_untrusted_utc_label"
    ] = "caller_supplied_untrusted_utc_label"
    preregistration_path: str = Field(min_length=1)
    preregistration_sha256: Literal[
        "183cf6fc2991361e5da57b17e06a5970f651000986d50b87e8af2e6796440204"
    ] = PREREGISTRATION_SHA256
    preregistration_schema: Literal[
        "typed-extractor-fresh-v3-preregistration-v1"
    ] = PREREGISTRATION_SCHEMA
    preregistration_mode: Literal["0444"] = "0444"
    code_sha256: dict[str, str]
    dependency_sha256: dict[str, str]
    blueprint_manifest_sha256: dict[str, str]
    prior_input_sha256: dict[str, str]
    l1_case_count: Literal[24] = 24
    l2_case_count: Literal[18] = 18
    l1_families: dict[str, int]
    l2_families: dict[str, int]
    evaluation_root: str = Field(min_length=1)
    evaluation_root_absent: Literal[True] = True
    materialization_workspace_paths: list[str]
    materialization_implementation_absent: Literal[True] = True
    hidden_artifact_write_count: Literal[0] = 0
    model_request_count: Literal[0] = 0
    automatic_write_counts: dict[str, int]
    candidate_v3_queue_sha256: Literal[
        "518ead9de8627a9a4384df8cdd9b8728a21fcf797f6b0f3d208dfcb28ac41c0f"
    ] = CANDIDATE_QUEUE_SHA256
    guard_fingerprint: Literal[
        "e184b6caf2998acf1c8700bc84d24bbafd49ab9c8f15738d1af8cc484ee5ebcc"
    ] = GUARD_FINGERPRINT
    guard_results_path: Literal[
        "artifacts/natural-benchmark-slices/slice-v1/"
        "symbolic-fallback-answerability-v2-fastembed-results.json"
    ] = GUARD_RESULTS_WORKSPACE_PATH
    guard_results_sha256: Literal[
        "f90ee6a8d9ee4a0beb993ae2055c2e7ededd013de9a70e6ce588efbbfedd2645"
    ] = GUARD_RESULTS_SHA256
    guard_counts: dict[str, int]
    pipeline_integration_authorized: Literal[False] = False
    embedding_authority: Literal[False] = False
    manual_identity_adjudications_materialized: Literal[False] = False
    external_memory_systems_rerun: Literal[False] = False
    longmemeval_status: Literal[
        "structured_l2_identity_unresolved"
    ] = "structured_l2_identity_unresolved"

    @field_validator(
        "l1_case_count",
        "l2_case_count",
        "hidden_artifact_write_count",
        "model_request_count",
        mode="before",
    )
    @classmethod
    def validate_exact_integer(cls, value: Any) -> Any:
        if type(value) is not int:
            raise ValueError("receipt count must be an exact integer")
        return value

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
    def validate_exact_contract(self) -> "FreshV3AuthoringReceipt":
        if self.l1_families != L1_FAMILIES or self.l2_families != L2_FAMILIES:
            raise ValueError("authoring receipt family contract mismatch")
        if self.automatic_write_counts != AUTOMATIC_WRITE_COUNTS:
            raise ValueError("authoring receipt write boundary mismatch")
        if self.guard_counts != GUARD_COUNTS:
            raise ValueError("authoring receipt guard count mismatch")
        if set(self.blueprint_manifest_sha256) != {"l1", "l2"}:
            raise ValueError("authoring receipt blueprint manifest mismatch")
        for hashes in (
            self.code_sha256,
            self.dependency_sha256,
            self.blueprint_manifest_sha256,
            self.prior_input_sha256,
        ):
            if not hashes or any(not _is_sha256(value) for value in hashes.values()):
                raise ValueError("invalid authoring receipt hash")
        return self


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _hash_value(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _opaque(kind: str, value: str) -> str:
    digest = hashlib.sha256(f"{OPAQUE_NAMESPACE}:{kind}:{value}".encode()).hexdigest()
    return f"{kind}-{digest[:16]}"


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(normalized.split())


_REFERENCE_KEYS = {
    "blueprint_id",
    "candidate_id",
    "candidate_ref",
    "case_id",
    "claim_ref",
    "evidence_id",
    "evidence_ids",
    "knowledge_id",
    "local_entity_id",
    "private_case_id",
    "private_session_id",
    "replacement_candidate_ref",
    "source_session_ref",
    "source_session_refs",
    "source_turn_ref",
    "source_turn_refs",
    "support_ref",
    "supporting_l1_refs",
    "turn_ref",
}
_NON_UNIQUE_REFERENCE_KEYS = {"claim_ref", "local_entity_id"}


def _semantic_projection(value: Any, key: str | None = None) -> Any:
    if key in _REFERENCE_KEYS or (key and key.endswith("_refs")):
        if isinstance(value, list):
            return {"opaque_ref_count": len(value)}
        return "<opaque-ref>"
    if key in {"evidence", "evidence_bindings"}:
        return {"evidence_count": len(value) if isinstance(value, list) else 1}
    if isinstance(value, dict):
        return {
            child_key: _semantic_projection(child, child_key)
            for child_key, child in sorted(value.items())
        }
    if isinstance(value, list):
        return [_semantic_projection(child, key) for child in value]
    if isinstance(value, str):
        return _normalize_text(value)
    return value


def _semantic_signature(value: Any) -> str:
    return _hash_value(_semantic_projection(value))


def _candidate_semantic_signatures(value: dict[str, Any]) -> set[str]:
    signatures = {_semantic_signature(value)}
    claims = value.get("structured_claims")
    if not isinstance(claims, list):
        return signatures
    signatures.update(
        _semantic_signature(claim) for claim in claims if isinstance(claim, dict)
    )
    for component in ("abstraction", "closure"):
        payload = value.get(component)
        if isinstance(payload, dict):
            signatures.add(
                _semantic_signature(
                    {
                        "component": component,
                        component: payload,
                        "structured_claims": claims,
                    }
                )
            )
    return signatures


def _walk_prior(
    value: Any,
    *,
    key: str | None,
    identifiers: set[str],
    evidence_ids: set[str],
    evidence_texts: set[str],
    source_texts: set[str],
    semantic_signatures: set[str],
) -> None:
    if isinstance(value, dict):
        if key in {
            "expected_typed_candidate",
            "typed_candidate",
            "typed_l1_support_pack",
        }:
            semantic_signatures.update(_candidate_semantic_signatures(value))
        for child_key, child in value.items():
            _walk_prior(
                child,
                key=child_key,
                identifiers=identifiers,
                evidence_ids=evidence_ids,
                evidence_texts=evidence_texts,
                source_texts=source_texts,
                semantic_signatures=semantic_signatures,
            )
        return
    if isinstance(value, list):
        for child in value:
            _walk_prior(
                child,
                key=key,
                identifiers=identifiers,
                evidence_ids=evidence_ids,
                evidence_texts=evidence_texts,
                source_texts=source_texts,
                semantic_signatures=semantic_signatures,
            )
        return
    if not isinstance(value, str):
        return
    if key == "evidence_id":
        evidence_ids.add(value)
        identifiers.add(value)
    elif (
        key not in _NON_UNIQUE_REFERENCE_KEYS
        and (key in _REFERENCE_KEYS or (key and key.endswith(("_ref", "_refs"))))
    ):
        identifiers.add(value)
    if key == "quote":
        evidence_texts.add(_normalize_text(value))
    if key in {"user", "agent"} and value.strip():
        source_texts.add(_normalize_text(value))


def _resolve_registered_version(preregistration_sha256: str) -> str:
    """Identify which registered version these bytes are, by hash.

    The version is derived from the content rather than passed in, so a caller
    cannot ask for v2's bindings while handing over v1's bytes. An unregistered
    digest is refused outright: a preregistration nobody registered has no
    declared binding set to validate against.
    """
    from .preregistration_versions import PreregistrationVersionRegistry

    registry_path = (
        WORKSPACE_ROOT
        / "artifacts"
        / "automatic-extraction-assessment"
        / "typed-extractor-v3-fresh-hidden-prereg-v2"
        / "version-registry.json"
    )
    if registry_path.is_file():
        registry = PreregistrationVersionRegistry.model_validate(
            json.loads(registry_path.read_bytes())
        )
        for version in registry.versions:
            if version.preregistration_sha256 == preregistration_sha256:
                return version.version
    # Not a registered version. It is still accepted if it is the digest this
    # module currently pins, which is how a caller supplies a preregistration
    # under test. Such a preregistration is treated as current, not historical:
    # only the frozen v1 bytes get the historical exemption from code-binding
    # enforcement, so an unregistered one must satisfy its own bindings.
    if preregistration_sha256 == PREREGISTRATION_SHA256:
        return "current_unregistered"
    raise ValueError("fresh v3 preregistration hash drift")


def _load_preregistration(path: Path) -> dict[str, Any]:
    path = _absolute_lexical_path(path)
    preregistration_bytes, opened = _read_regular_path(
        path,
        label="fresh v3 preregistration",
    )
    if path.name != "preregistration.json":
        raise ValueError("fresh v3 preregistration filename must be preregistration.json")
    # Mode is not checked: this is a committed input, and git does not preserve
    # 0444. The filename and the hash below are the portable checks.
    digest = hashlib.sha256(preregistration_bytes).hexdigest()
    version = _resolve_registered_version(digest)
    preregistration = json.loads(preregistration_bytes)
    if preregistration.get("schema_version") != PREREGISTRATION_SCHEMA:
        raise ValueError("fresh v3 preregistration schema drift")
    if preregistration.get("evaluation_id") != EVALUATION_ID:
        raise ValueError("fresh v3 preregistration evaluation drift")
    input_paths = preregistration_input_paths(WORKSPACE_ROOT)
    if set(input_paths) != set(preregistration.get("input_sha256", {})):
        raise ValueError("fresh v3 preregistration input registry drift")
    for name, expected in preregistration["input_sha256"].items():
        path_value = input_paths[name]
        if not path_value.is_file() or sha256_file(path_value) != expected:
            raise ValueError(f"fresh v3 preregistration input drift: {name}")
    code_paths = _preregistration_code_paths(WORKSPACE_ROOT)
    code_hashes = preregistration.get("code_sha256")
    if set(code_paths) != set(code_hashes or {}):
        raise ValueError("preregistration code hash registry drift")
    # Code bindings are enforced for everything except the frozen v1 bytes. v1's
    # bindings are kept exactly as frozen -- including two that had already
    # drifted at the reorganization baseline -- so re-enforcing them would require
    # either rewriting history or reverting a verified repair. v1 stays loadable
    # for the runs already scored against it; every other preregistration,
    # registered or supplied, must satisfy its own bindings.
    if version != "v1":
        for name, path_value in code_paths.items():
            if not path_value.is_file() or sha256_file(path_value) != code_hashes[name]:
                raise ValueError(f"preregistration code hash drift: {name}")
    return preregistration


def _build_prior_inventory(preregistration_path: Path) -> PriorInventory:
    preregistration = _load_preregistration(preregistration_path)
    paths = preregistration_input_paths(WORKSPACE_ROOT)
    identifiers: set[str] = set()
    evidence_ids: set[str] = set()
    evidence_texts: set[str] = set()
    source_texts: set[str] = set()
    semantic_signatures: set[str] = set()
    for name in sorted(preregistration["input_sha256"]):
        path = paths[name]
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        _walk_prior(
            payload,
            key=None,
            identifiers=identifiers,
            evidence_ids=evidence_ids,
            evidence_texts=evidence_texts,
            source_texts=source_texts,
            semantic_signatures=semantic_signatures,
        )
    return PriorInventory(
        identifiers=sorted(identifiers),
        evidence_ids=sorted(evidence_ids),
        evidence_texts=sorted(evidence_texts),
        source_texts=sorted(source_texts),
        semantic_signatures=sorted(semantic_signatures),
    )


def _entities_and_roles(
    roles: tuple[tuple[str, str, str], ...],
) -> tuple[list[TypedLocalEntity], list[TypedRoleBinding]]:
    surfaces: list[str] = []
    for _, _, surface in roles:
        if surface not in surfaces:
            surfaces.append(surface)
    local_entities = [
        TypedLocalEntity(local_entity_id=f"entity-{index:02d}", surface=surface)
        for index, surface in enumerate(surfaces, start=1)
    ]
    surface_to_id = {
        item.surface: item.local_entity_id for item in local_entities
    }
    bindings = [
        TypedRoleBinding(
            role=role,
            role_name=role_name,
            local_entity_id=surface_to_id[surface],
        )
        for role, role_name, surface in roles
    ]
    return local_entities, bindings


def _lifecycle_candidate_refs(binding: TypedLifecycleBinding) -> list[str]:
    refs = [
        *binding.replaces_candidate_refs,
        *binding.supersedes_candidate_refs,
        *binding.conflicts_with_candidate_refs,
    ]
    if binding.replacement_candidate_ref is not None:
        refs.append(binding.replacement_candidate_ref)
    return sorted(set(refs))


def _operation_refs(provenance: TypedOperationProvenance) -> list[str]:
    return sorted(
        {
            *provenance.confirmed_by_operation_refs,
            *provenance.added_by_operation_refs,
        }
    )


def _l2_claim_time_from_supports(
    family: str,
    supports: tuple[TypedL1SupportCandidate, ...],
) -> TypedTimeBinding:
    if family != "lifecycle_case":
        return TypedTimeBinding()
    return TypedTimeBinding(
        event_time=next(
            (
                support.time.event_time
                for support in reversed(supports)
                if support.time.event_time is not None
            ),
            None,
        ),
        valid_time=next(
            (
                support.time.valid_time
                for support in reversed(supports)
                if support.time.valid_time is not None
            ),
            None,
        ),
    )


def _operation_record_shape(
    lifecycle: TypedLifecycleBinding,
    current_candidate_ref: str,
) -> tuple[str, list[str], str | None]:
    if lifecycle.replaces_candidate_refs:
        return (
            "correct",
            list(lifecycle.replaces_candidate_refs),
            current_candidate_ref,
        )
    if lifecycle.supersedes_candidate_refs:
        return "supersede", list(lifecycle.supersedes_candidate_refs), None
    if lifecycle.conflicts_with_candidate_refs:
        return (
            "conflict",
            sorted(
                [current_candidate_ref, *lifecycle.conflicts_with_candidate_refs]
            ),
            None,
        )
    return "confirm", [current_candidate_ref], None


def _binding_entity_ids(
    value: str,
    local_entities: list[TypedLocalEntity],
) -> list[str]:
    normalized_value = _normalize_text(value)
    return [
        item.local_entity_id
        for item in local_entities
        if _normalize_text(item.surface) in normalized_value
    ]


def _make_l1_blueprint(
    *,
    family: str,
    ordinal: int,
    user: str,
    agent: str,
    subject: str,
    predicate_surface: str,
    object_value: str | None,
    decision: Literal["emit_l1", "abstain", "no_memory"],
    kind: Literal["event", "state", "preference", "task", "attribute"],
    sense: str,
    operator: str,
    roles: tuple[tuple[str, str, str], ...],
    modality: Literal[
        "actual", "planned", "hypothetical", "requested", "recommended", "denied"
    ] = "actual",
    polarity: Literal["positive", "negative"] = "positive",
    event_time: str | None = None,
    valid_time: str | None = None,
    conditions: tuple[tuple[str, str], ...] = (),
    scopes: tuple[tuple[str, str], ...] = (),
    evidence_message: Literal["user", "agent"] = "user",
    evidence_speaker: Literal["user", "assistant", "tool"] = "user",
    evidence_quote: str | None = None,
    source_status: Literal[
        "user_reported", "agent_generated", "tool_observed"
    ] = "user_reported",
    derivation: Literal["explicit", "context_completed", "inferred"] = "explicit",
    inference_basis: str | None = None,
    projection_status: Literal[
        "active", "corrected", "superseded", "active_conflict"
    ] = "active",
    lifecycle: Literal["active", "superseded", "conflicted"] = "active",
    lifecycle_relation: Literal["none", "replaces", "supersedes", "conflicts"] = "none",
    unresolved_required_fields: tuple[str, ...] = (),
) -> L1Blueprint:
    private_prefix = f"fresh-v3-l1-{family}-{ordinal:02d}"
    private_case_id = f"{private_prefix}-case"
    knowledge_id = f"{private_prefix}-knowledge"
    candidate_id = f"{private_prefix}-candidate"
    evidence_id = _opaque("evidence", private_prefix)
    message = user if evidence_message == "user" else agent
    quote = evidence_quote or message
    start = message.index(quote)
    related = _opaque("candidate", f"{private_prefix}-prior")
    lifecycle_binding = TypedLifecycleBinding(
        lifecycle=lifecycle,
        replacement_candidate_ref=None,
        replaces_candidate_refs=([related] if lifecycle_relation == "replaces" else []),
        supersedes_candidate_refs=(
            [related] if lifecycle_relation == "supersedes" else []
        ),
        conflicts_with_candidate_refs=(
            [related] if lifecycle_relation == "conflicts" else []
        ),
    )
    operation = TypedOperationProvenance(
        confirmed_by_operation_refs=(
            [_opaque("operation", f"{private_prefix}-confirm")]
            if decision == "emit_l1" and lifecycle_relation == "none"
            else []
        ),
        added_by_operation_refs=(
            [_opaque("operation", f"{private_prefix}-change")]
            if decision == "emit_l1" and lifecycle_relation != "none"
            else []
        ),
    )
    evidence = PublicEvidenceSpan(
        evidence_id=evidence_id,
        speaker=evidence_speaker,
        message=evidence_message,
        quote=quote,
        occurrence_index=0,
        start=start,
        end=start + len(quote),
    )
    current_candidate_ref = _opaque("candidate", candidate_id)
    candidate_refs = _lifecycle_candidate_refs(lifecycle_binding)
    operation_refs = _operation_refs(operation)
    operation_kind, operation_targets, operation_replacement = (
        _operation_record_shape(lifecycle_binding, current_candidate_ref)
    )
    reference_registry = {
        "candidate_refs": candidate_refs,
        "operation_refs": operation_refs,
        "candidate_records": [
            {
                "candidate_ref": candidate_ref,
                "owner_candidate_ref": current_candidate_ref,
                "relation": "prior_revision",
            }
            for candidate_ref in candidate_refs
        ],
        "operation_records": [
            {
                "operation_ref": operation_ref,
                "owner_candidate_ref": current_candidate_ref,
                "operation_kind": operation_kind,
                "targets": operation_targets,
                "replacement_candidate_ref": operation_replacement,
            }
            for operation_ref in operation_refs
        ],
    }
    untyped = PublicUntypedCandidate(
        statement=quote,
        subject=subject,
        predicate=predicate_surface,
        object=object_value,
        qualifiers={
            "modality": modality,
            "polarity": polarity,
            "event_time": event_time,
            "valid_time": valid_time,
            "conditions": [value for _, value in conditions],
            "scopes": [value for _, value in scopes],
            "reference_registry": reference_registry,
        },
        source_status=source_status,
        derivation=derivation,
        inference_basis=inference_basis,
        projection_status=projection_status,
        lifecycle_links=lifecycle_binding,
        operation_provenance=operation,
        evidence=[evidence],
    )
    expected: TypedL1Candidate | None = None
    if decision == "emit_l1":
        local_entities, role_bindings = _entities_and_roles(roles)
        expected = TypedL1Candidate(
            kind=kind,
            predicate=TypedPredicate(
                surface=predicate_surface,
                sense=sense,
                canonical_operator=operator,
            ),
            local_entities=local_entities,
            roles=role_bindings,
            modality=modality,
            polarity=polarity,
            time=TypedTimeBinding(event_time=event_time, valid_time=valid_time),
            condition_bindings=[
                TypedConditionBinding(
                    operator=condition_operator,
                    value=value,
                    local_entity_ids=_binding_entity_ids(value, local_entities),
                )
                for condition_operator, value in conditions
            ],
            scope_bindings=[
                TypedScopeBinding(
                    operator=scope_operator,
                    value=value,
                    local_entity_ids=_binding_entity_ids(value, local_entities),
                )
                for scope_operator, value in scopes
            ],
            derivation=TypedDerivationProvenance(
                method=derivation,
                basis=inference_basis,
                evidence_ids=[evidence_id],
            ),
            evidence_bindings=[
                TypedEvidenceBinding(
                    evidence_id=evidence_id,
                    speaker=evidence_speaker,
                )
            ],
            lifecycle=lifecycle_binding,
            operation_provenance=operation,
        )
    return L1Blueprint(
        family=family,
        ordinal=ordinal,
        blueprint_id=f"fresh-v3-l1-blueprint-{family}-{ordinal:02d}",
        private_case_id=private_case_id,
        knowledge_id=knowledge_id,
        candidate_id=candidate_id,
        vocabulary_operator=operator,
        vocabulary_sense=sense,
        source_turn={"user": user, "agent": agent},
        untyped_candidate=untyped,
        expected_decision=decision,
        expected_typed_candidate=expected,
        unresolved_required_fields=list(unresolved_required_fields),
    )


def _l1_specs() -> tuple[L1Blueprint, ...]:
    specs: list[dict[str, Any]] = [
        dict(family="false_emission", ordinal=1, user="Which checksum algorithm is best for a lunar archive?", agent="I can compare checksum algorithms without recording a user fact.", subject="checksum algorithm", predicate_surface="asks about", object_value="lunar archive", decision="no_memory", kind="task", sense="question.checksum_algorithm", operator="answer_checksum_question", roles=(("theme", "question topic", "checksum algorithm"),)),
        dict(family="false_emission", ordinal=2, user="Explain how a mercury relay differs from a contactor.", agent="A relay switches lower-power circuits while a contactor handles larger loads.", subject="mercury relay", predicate_surface="requests explanation", object_value="contactor", decision="no_memory", kind="task", sense="explanation.relay_difference", operator="explain_relay_difference", roles=(("theme", "explanation topic", "mercury relay"),)),
        dict(family="false_emission", ordinal=3, user="If a future expedition used violet crates, it might label them twice.", agent="That is a hypothetical scenario rather than a current fact.", subject="future expedition", predicate_surface="might label", object_value="violet crates", decision="abstain", kind="state", sense="scenario.crate_labeling", operator="label_violet_crates", roles=(("actor", "hypothetical actor", "future expedition"), ("theme", "hypothetical item", "violet crates")), modality="hypothetical", unresolved_required_fields=("supported_modality",)),
        dict(family="false_abstention", ordinal=1, user="I store the signed customs form in cabinet Kestrel.", agent="Cabinet Kestrel is recorded as the storage location.", subject="signed customs form", predicate_surface="is stored in", object_value="cabinet Kestrel", decision="emit_l1", kind="state", sense="document.storage_location", operator="store_customs_form", roles=(("theme", "stored document", "signed customs form"), ("location", "storage location", "cabinet Kestrel"))),
        dict(family="false_abstention", ordinal=2, user="Please reserve microscopy bay Orion for 2026-09-14.", agent="The reservation request for bay Orion is noted.", subject="user", predicate_surface="requests reservation", object_value="microscopy bay Orion", decision="emit_l1", kind="task", sense="reservation.microscopy_bay", operator="reserve_microscopy_bay", roles=(("actor", "reservation requester", "user"), ("theme", "requested resource", "microscopy bay Orion")), modality="requested", event_time="2026-09-14"),
        dict(family="false_abstention", ordinal=3, user="Read the latest valve telemetry.", agent="Valve N7 pressure stabilized at 42 kPa.", subject="valve N7", predicate_surface="has stabilized pressure", object_value="42 kPa", decision="emit_l1", kind="state", sense="telemetry.valve_pressure", operator="observe_valve_pressure", roles=(("theme", "observed valve", "valve N7"), ("value", "pressure reading", "42 kPa")), evidence_message="agent", evidence_speaker="tool", source_status="tool_observed"),
        dict(family="role_or_local_entity", ordinal=1, user="Mina handed the cobalt ledger to Rafi at Dock Nine.", agent="The ledger handoff and its participants are recorded.", subject="Mina", predicate_surface="handed", object_value="cobalt ledger", decision="emit_l1", kind="event", sense="transfer.ledger_handoff", operator="handoff_cobalt_ledger", roles=(("giver", "handoff source", "Mina"), ("theme", "transferred item", "cobalt ledger"), ("recipient", "handoff recipient", "Rafi"), ("location", "handoff location", "Dock Nine"))),
        dict(family="role_or_local_entity", ordinal=2, user="I prepared the nebula brief for Dr. Sato with analyst Keene.", agent="The beneficiary and collaborating analyst are recorded separately.", subject="user", predicate_surface="prepared", object_value="nebula brief", decision="emit_l1", kind="event", sense="document.collaborative_preparation", operator="prepare_nebula_brief", roles=(("actor", "brief author", "user"), ("theme", "prepared document", "nebula brief"), ("beneficiary", "brief recipient", "Dr. Sato"), ("participant", "collaborating analyst", "analyst Keene"))),
        dict(family="role_or_local_entity", ordinal=3, user="Courier Ivo moved crate Helix from Atrium C to Lab Pine.", agent="Origin and destination are recorded as distinct roles.", subject="Courier Ivo", predicate_surface="moved", object_value="crate Helix", decision="emit_l1", kind="event", sense="logistics.crate_transfer", operator="move_crate_helix", roles=(("actor", "movement actor", "Courier Ivo"), ("theme", "moved item", "crate Helix"), ("origin", "movement origin", "Atrium C"), ("destination", "movement destination", "Lab Pine"))),
        dict(family="time", ordinal=1, user="The quartz inspection occurred on 2026-10-03.", agent="The inspection date is recorded as 2026-10-03.", subject="quartz inspection", predicate_surface="occurred on", object_value="2026-10-03", decision="emit_l1", kind="event", sense="inspection.quartz_event_date", operator="date_quartz_inspection", roles=(("theme", "dated inspection", "quartz inspection"),), event_time="2026-10-03"),
        dict(family="time", ordinal=2, user="My polar lab badge remains valid until 2027-01-31.", agent="The badge validity end is recorded.", subject="polar lab badge", predicate_surface="valid until", object_value="2027-01-31", decision="emit_l1", kind="state", sense="credential.badge_validity", operator="set_badge_validity", roles=(("holder", "credential holder", "user"), ("theme", "valid credential", "polar lab badge")), valid_time="2027-01-31"),
        dict(family="time", ordinal=3, user="Move the amber briefing to next moonrise.", agent="The requested time is deictic and cannot be normalized.", subject="user", predicate_surface="requests reschedule", object_value="amber briefing", decision="abstain", kind="task", sense="briefing.deictic_reschedule", operator="reschedule_amber_briefing", roles=(("actor", "request owner", "user"), ("theme", "rescheduled briefing", "amber briefing")), modality="requested", unresolved_required_fields=("event_time",)),
        dict(family="condition_or_scope", ordinal=1, user="Publish the zircon memo only if reviewer Nia approves it.", agent="The approval condition is bound to the publication request.", subject="user", predicate_surface="requests publication", object_value="zircon memo", decision="emit_l1", kind="task", sense="document.conditional_zircon_publish", operator="publish_zircon_memo", roles=(("actor", "publication requester", "user"), ("theme", "publication document", "zircon memo"), ("approver", "required reviewer", "reviewer Nia")), modality="requested", conditions=(("if", "reviewer Nia approves the zircon memo"),)),
        dict(family="condition_or_scope", ordinal=2, user="Keep the aurora dashboard visible only within Team Finch.", agent="The visibility scope is restricted to Team Finch.", subject="aurora dashboard", predicate_surface="is visible", object_value="Team Finch", decision="emit_l1", kind="state", sense="privacy.aurora_team_scope", operator="scope_aurora_dashboard", roles=(("theme", "scoped dashboard", "aurora dashboard"), ("scope", "authorized team", "Team Finch")), scopes=(("within", "Team Finch"),)),
        dict(family="condition_or_scope", ordinal=3, user="Send the orchid invoice after account Delta is verified.", agent="The verification prerequisite is attached to the send task.", subject="user", predicate_surface="requests send", object_value="orchid invoice", decision="emit_l1", kind="task", sense="billing.verified_invoice_send", operator="send_orchid_invoice", roles=(("actor", "send requester", "user"), ("theme", "invoice to send", "orchid invoice"), ("condition", "verified account", "account Delta")), modality="requested", conditions=(("after", "account Delta is verified"),)),
        dict(family="evidence", ordinal=1, user="The retired locker number was 18. The current locker code is 7412.", agent="Only the current code is selected as evidence.", subject="current locker", predicate_surface="has code", object_value="7412", decision="emit_l1", kind="attribute", sense="access.current_locker_code", operator="record_current_locker_code", roles=(("theme", "current locker", "current locker"), ("current_value", "active code", "7412")), evidence_quote="The current locker code is 7412."),
        dict(family="evidence", ordinal=2, user="Ignore the shelf-two sample label; freezer Boreal is set to -24 C.", agent="The freezer setting is isolated from the distractor label.", subject="freezer Boreal", predicate_surface="is set to", object_value="-24 C", decision="emit_l1", kind="state", sense="storage.freezer_temperature", operator="set_boreal_temperature", roles=(("theme", "configured freezer", "freezer Boreal"), ("value", "temperature setting", "-24 C")), evidence_quote="freezer Boreal is set to -24 C"),
        dict(family="evidence", ordinal=3, user="Read probe Lumen, not the neighboring dial.", agent="Probe Lumen conductivity is 6.4 mS/cm.", subject="probe Lumen", predicate_surface="has conductivity", object_value="6.4 mS/cm", decision="emit_l1", kind="state", sense="telemetry.probe_conductivity", operator="observe_lumen_conductivity", roles=(("theme", "observed probe", "probe Lumen"), ("value", "conductivity reading", "6.4 mS/cm")), evidence_message="agent", evidence_speaker="tool", source_status="tool_observed", evidence_quote="Probe Lumen conductivity is 6.4 mS/cm."),
        dict(family="derivation_or_speaker", ordinal=1, user="I prefer the north alcove for focused drafting.", agent="The user preference is recorded as user-reported.", subject="user", predicate_surface="prefers", object_value="north alcove", decision="emit_l1", kind="preference", sense="preference.focus_alcove", operator="prefer_north_alcove", roles=(("holder", "preference holder", "user"), ("theme", "preferred location", "north alcove"))),
        dict(family="derivation_or_speaker", ordinal=2, user="How should the obsidian report be archived?", agent="I recommend encrypting the obsidian report before archival.", subject="assistant", predicate_surface="recommends encryption", object_value="obsidian report", decision="emit_l1", kind="task", sense="assistant.encryption_recommendation", operator="recommend_obsidian_encryption", roles=(("actor", "recommending assistant", "assistant"), ("theme", "recommended document", "obsidian report")), modality="recommended", evidence_message="agent", evidence_speaker="assistant", source_status="agent_generated"),
        dict(family="derivation_or_speaker", ordinal=3, user="The titanium folder is in Archive M. That is where I keep the signed release.", agent="The release location is completed from the explicit coreference.", subject="signed release", predicate_surface="is kept in", object_value="Archive M", decision="emit_l1", kind="state", sense="document.context_release_location", operator="locate_signed_release", roles=(("theme", "stored release", "signed release"), ("location", "resolved archive", "Archive M")), derivation="context_completed", inference_basis="That refers to Archive M in the preceding sentence."),
        dict(family="lifecycle", ordinal=1, user="Correction: the prism review is on 2026-11-08, not 2026-11-06.", agent="The corrected date supersedes the prior date.", subject="prism review", predicate_surface="is scheduled on", object_value="2026-11-08", decision="emit_l1", kind="state", sense="review.corrected_prism_date", operator="correct_prism_review_date", roles=(("theme", "corrected review", "prism review"), ("current_time", "correct schedule", "2026-11-08"), ("prior_time", "replaced schedule", "2026-11-06")), event_time="2026-11-08", projection_status="active", lifecycle_relation="replaces"),
        dict(family="lifecycle", ordinal=2, user="I used to route coral alerts to Queue B; now route them to Queue D.", agent="Queue D supersedes Queue B for coral alerts.", subject="coral alerts", predicate_surface="route to", object_value="Queue D", decision="emit_l1", kind="state", sense="routing.coral_alert_supersession", operator="route_coral_alerts", roles=(("theme", "routed alerts", "coral alerts"), ("current_value", "current queue", "Queue D"), ("prior_value", "superseded queue", "Queue B")), projection_status="active", lifecycle_relation="supersedes"),
        dict(family="lifecycle", ordinal=3, user="Sensor Umber reports 7.2, while sensor Teal reports 8.1 for the same batch.", agent="Both conflicting readings remain active for review.", subject="same batch", predicate_surface="has conflicting reading", object_value="7.2 versus 8.1", decision="emit_l1", kind="state", sense="telemetry.batch_reading_conflict", operator="record_batch_reading_conflict", roles=(("theme", "measured batch", "same batch"), ("reading", "Umber reading", "7.2"), ("conflicting_reading", "Teal reading", "8.1")), projection_status="active_conflict", lifecycle="conflicted", lifecycle_relation="conflicts"),
    ]
    blueprints = tuple(_make_l1_blueprint(**spec) for spec in specs)
    return tuple(
        blueprint
        for family in L1_FAMILIES
        for blueprint in blueprints
        if blueprint.family == family
    )


def _make_support(
    *,
    private_prefix: str,
    index: int,
    session_ref: str,
    user: str,
    agent: str,
    subject: str,
    predicate_surface: str,
    object_value: str,
    sense: str,
    operator: str,
    kind: Literal["event", "state", "preference", "task", "attribute"] = "state",
    modality: Literal[
        "actual", "planned", "hypothetical", "requested", "recommended", "denied"
    ] = "actual",
    event_time: str | None = None,
    valid_time: str | None = None,
) -> tuple[L2PublicTurn, TypedL1SupportCandidate, PublicEvidenceSpan]:
    turn_ref = _opaque("turn", f"{private_prefix}-{index}")
    support_ref = _opaque("support", f"{private_prefix}-{index}")
    evidence_id = _opaque("evidence", f"{private_prefix}-{index}")
    entities, roles = _entities_and_roles(
        (
            ("subject", "support subject", subject),
            ("theme", "support object", object_value),
        )
    )
    turn = L2PublicTurn(
        source_turn_ref=turn_ref,
        turn_index=index - 1,
        user=user,
        agent=agent,
    )
    support = TypedL1SupportCandidate(
        support_ref=support_ref,
        source_turn_ref=turn_ref,
        source_session_ref=session_ref,
        kind=kind,
        predicate=TypedPredicate(
            surface=predicate_surface,
            sense=sense,
            canonical_operator=operator,
        ),
        local_entities=entities,
        roles=roles,
        modality=modality,
        polarity="positive",
        time=TypedTimeBinding(event_time=event_time, valid_time=valid_time),
        evidence_bindings=[
            TypedEvidenceBinding(evidence_id=evidence_id, speaker="user")
        ],
    )
    evidence = PublicEvidenceSpan(
        evidence_id=evidence_id,
        speaker="user",
        message="user",
        quote=user,
        occurrence_index=0,
        start=0,
        end=len(user),
    )
    return turn, support, evidence


def _make_l2_blueprint(
    *,
    family: str,
    ordinal: int,
    support_specs: tuple[dict[str, Any], dict[str, Any]],
    subject: str,
    predicate_surface: str,
    object_value: str,
    decision: Literal["emit_l2", "abstain"],
    kind: Literal[
        "habit", "long_running_state", "preference_profile", "project", "summary_event", "task"
    ],
    sense: str,
    operator: str,
    abstraction_method: Literal[
        "coreference_resolution",
        "task_composition",
        "preference_aggregation",
        "lifecycle_resolution",
        "state_summary",
    ],
    closure_pattern: Literal[
        "single_fact",
        "multi_evidence_set",
        "temporal_chain",
        "update_supersession",
        "causal_answerability",
    ],
    unresolved_required_fields: tuple[str, ...] = (),
) -> L2Blueprint:
    prefix = f"fresh-v3-l2-{family}-{ordinal:02d}"
    session_ref = _opaque("session", prefix)
    rendered = [
        _make_support(
            private_prefix=prefix,
            index=index,
            session_ref=session_ref,
            **spec,
        )
        for index, spec in enumerate(support_specs, start=1)
    ]
    turns = tuple(item[0] for item in rendered)
    supports = tuple(item[1] for item in rendered)
    evidence = [item[2] for item in rendered]
    support_refs = [item.support_ref for item in supports]
    support_lifecycle_bindings: tuple[L2SupportLifecycleBinding, ...] = ()
    if family == "lifecycle_case":
        support_lifecycle_bindings = (
            L2SupportLifecycleBinding(
                support_ref=supports[0].support_ref,
                relation="superseded_by",
                counterpart_support_ref=supports[1].support_ref,
            ),
            L2SupportLifecycleBinding(
                support_ref=supports[1].support_ref,
                relation="supersedes",
                counterpart_support_ref=supports[0].support_ref,
            ),
        )
    untyped = PublicUntypedCandidate(
        statement=f"{subject} {predicate_surface} {object_value}",
        subject=subject,
        predicate=predicate_surface,
        object=object_value,
        qualifiers={
            "support_count": len(supports),
        },
        source_status="user_reported",
        derivation="context_completed",
        inference_basis="The candidate combines the two public support turns.",
        projection_status="active",
        lifecycle_links=TypedLifecycleBinding(lifecycle="active"),
        operation_provenance=TypedOperationProvenance(),
        evidence=evidence,
    )
    expected: TypedL2Candidate | None = None
    if decision == "emit_l2":
        entities, roles = _entities_and_roles(
            (
                ("subject", "claim subject", subject),
                ("theme", "claim object", object_value),
            )
        )
        modalities = {support.modality for support in supports}
        if len(modalities) != 1:
            raise ValueError("L2 authored supports must share one modality")
        claim = TypedL2StructuredClaim(
            claim_ref="claim-01",
            predicate=TypedPredicate(
                surface=predicate_surface,
                sense=sense,
                canonical_operator=operator,
            ),
            local_entities=entities,
            roles=roles,
            modality=next(iter(modalities)),
            polarity="positive",
            time=_l2_claim_time_from_supports(family, supports),
            supporting_l1_refs=support_refs,
        )
        expected = TypedL2Candidate(
            kind=kind,
            summary=f"{subject} {predicate_surface} {object_value}.",
            supporting_l1_refs=support_refs,
            structured_claims=[claim],
            abstraction=TypedL2Abstraction(
                method=abstraction_method,
                basis="Both typed L1 supports jointly establish the candidate.",
            ),
            closure=TypedL2Closure(
                pattern=closure_pattern,
                required_support_refs=support_refs,
            ),
            source_turn_refs=[item.source_turn_ref for item in turns],
            source_session_refs=[session_ref],
            evidence_bindings=[
                binding for support in supports for binding in support.evidence_bindings
            ],
        )
    return L2Blueprint(
        family=family,
        ordinal=ordinal,
        blueprint_id=f"fresh-v3-l2-blueprint-{family}-{ordinal:02d}",
        private_case_id=f"{prefix}-case",
        knowledge_id=f"{prefix}-knowledge",
        candidate_id=f"{prefix}-candidate",
        vocabulary_operator=operator,
        vocabulary_sense=sense,
        private_session_id=f"{prefix}-session",
        source_session_ref=session_ref,
        source_turns=turns,
        untyped_candidate=untyped,
        typed_l1_support_pack=supports,
        support_lifecycle_bindings=support_lifecycle_bindings,
        expected_decision=decision,
        expected_typed_candidate=expected,
        unresolved_required_fields=list(unresolved_required_fields),
    )


def _support(
    user: str,
    subject: str,
    predicate: str,
    object_value: str,
    _private_token: str,
    *,
    modality: str = "actual",
    kind: str = "state",
    event_time: str | None = None,
    valid_time: str | None = None,
) -> dict[str, Any]:
    predicate_fragment = "_".join(
        "".join(
            character if character.isalnum() else " "
            for character in unicodedata.normalize("NFKC", predicate).casefold()
        ).split()
    )
    return {
        "user": user,
        "agent": (
            f"The statement about {subject} and {object_value} is recorded "
            "as supporting context."
        ),
        "subject": subject,
        "predicate_surface": predicate,
        "object_value": object_value,
        "sense": f"support.{predicate_fragment}",
        "operator": f"record_support_{predicate_fragment}",
        "modality": modality,
        "kind": kind,
        "event_time": event_time,
        "valid_time": valid_time,
    }


def _l2_specs() -> tuple[L2Blueprint, ...]:
    specs: list[dict[str, Any]] = [
        dict(family="unsupported_modality_control", ordinal=1, support_specs=(_support("I might test the indigo rotor someday.", "user", "might test", "indigo rotor", "indigo_rotor_plan", modality="hypothetical", kind="task"), _support("The rotor cabinet is currently empty.", "rotor cabinet", "is", "empty", "empty_rotor_cabinet")), subject="user", predicate_surface="operates", object_value="indigo rotor", decision="abstain", kind="task", sense="task.rotor_operation", operator="operate_indigo_rotor", abstraction_method="task_composition", closure_pattern="multi_evidence_set", unresolved_required_fields=("supported_modality",)),
        dict(family="unsupported_modality_control", ordinal=2, support_specs=(_support("I recommend that someone inspect beacon Umber.", "user", "recommends inspection", "beacon Umber", "umber_recommendation", modality="recommended", kind="task"), _support("No inspection result has been recorded.", "beacon Umber", "has", "no inspection result", "umber_no_result")), subject="beacon Umber", predicate_surface="passed inspection", object_value="true", decision="abstain", kind="summary_event", sense="inspection.beacon_result", operator="assert_beacon_passed", abstraction_method="state_summary", closure_pattern="multi_evidence_set", unresolved_required_fields=("supported_modality",)),
        dict(family="unresolved_selection_control", ordinal=1, support_specs=(_support("The maple adapter costs 31 credits.", "maple adapter", "costs", "31 credits", "maple_cost"), _support("The silver adapter weighs 120 grams.", "silver adapter", "weighs", "120 grams", "silver_weight")), subject="user", predicate_surface="selected", object_value="adapter", decision="abstain", kind="task", sense="selection.adapter_choice", operator="select_adapter", abstraction_method="coreference_resolution", closure_pattern="multi_evidence_set", unresolved_required_fields=("selected_entity",)),
        dict(family="unresolved_selection_control", ordinal=2, support_specs=(_support("Route Cedar has the shortest distance.", "Route Cedar", "has", "shortest distance", "cedar_distance"), _support("Route Opal avoids tolls.", "Route Opal", "avoids", "tolls", "opal_tolls")), subject="user", predicate_surface="chose", object_value="route", decision="abstain", kind="task", sense="selection.route_choice", operator="choose_route", abstraction_method="coreference_resolution", closure_pattern="multi_evidence_set", unresolved_required_fields=("selected_entity",)),
        dict(family="incompatible_support_control", ordinal=1, support_specs=(_support("My telescope mount is brass.", "telescope mount", "has material", "brass", "brass_mount", kind="attribute"), _support("I drink mint tea after lunch.", "user", "drinks", "mint tea", "mint_tea", kind="preference")), subject="user", predicate_surface="has unified project", object_value="brass tea workflow", decision="abstain", kind="project", sense="project.brass_tea_workflow", operator="compose_brass_tea", abstraction_method="task_composition", closure_pattern="multi_evidence_set", unresolved_required_fields=("support_compatibility",)),
        dict(family="incompatible_support_control", ordinal=2, support_specs=(_support("The cobalt scanner uses firmware 9.3.", "cobalt scanner", "uses firmware", "9.3", "scanner_firmware", kind="attribute"), _support("My preferred hiking day is Thursday.", "user", "prefers hiking day", "Thursday", "hiking_day", kind="preference")), subject="user", predicate_surface="maintains", object_value="scanner hiking plan", decision="abstain", kind="project", sense="project.scanner_hiking_workflow", operator="compose_scanner_hike", abstraction_method="task_composition", closure_pattern="multi_evidence_set", unresolved_required_fields=("support_compatibility",)),
        dict(family="incomplete_closure_control", ordinal=1, support_specs=(_support("Reviewer Sol requested a palette change.", "reviewer Sol", "requested", "palette change", "sol_palette_request", kind="event"), _support("The interface later used a teal palette.", "interface", "used", "teal palette", "teal_interface", kind="event")), subject="reviewer Sol", predicate_surface="caused", object_value="teal palette", decision="abstain", kind="summary_event", sense="causal.palette_change", operator="attribute_palette_cause", abstraction_method="state_summary", closure_pattern="causal_answerability", unresolved_required_fields=("evidence_closure",)),
        dict(family="incomplete_closure_control", ordinal=2, support_specs=(_support("Aster pump alarmed at 09:10.", "Aster pump", "alarmed at", "09:10", "aster_alarm", kind="event"), _support("A technician replaced a seal at 09:40.", "technician", "replaced", "seal", "aster_seal", kind="event")), subject="seal replacement", predicate_surface="resolved", object_value="Aster pump alarm", decision="abstain", kind="summary_event", sense="maintenance.alarm_resolution", operator="resolve_aster_alarm", abstraction_method="state_summary", closure_pattern="causal_answerability", unresolved_required_fields=("evidence_closure",)),
        dict(family="coreference_case", ordinal=1, support_specs=(_support("I unpacked spectrometer Vega in Lab Reed.", "user", "unpacked", "spectrometer Vega", "unpack_vega", kind="event"), _support("It now occupies the eastern bench.", "spectrometer Vega", "occupies", "eastern bench", "vega_eastern_bench")), subject="spectrometer Vega", predicate_surface="has current location", object_value="eastern bench", decision="emit_l2", kind="long_running_state", sense="equipment.resolved_vega_location", operator="resolve_vega_location", abstraction_method="coreference_resolution", closure_pattern="multi_evidence_set"),
        dict(family="coreference_case", ordinal=2, support_specs=(_support("The sapphire dossier was signed by Director Vale.", "sapphire dossier", "was signed by", "Director Vale", "sapphire_signature", kind="event"), _support("That dossier is now in Vault Quill.", "sapphire dossier", "is in", "Vault Quill", "sapphire_vault")), subject="sapphire dossier", predicate_surface="has archive location", object_value="Vault Quill", decision="emit_l2", kind="long_running_state", sense="document.resolved_sapphire_location", operator="resolve_sapphire_location", abstraction_method="coreference_resolution", closure_pattern="multi_evidence_set"),
        dict(family="task_composition_case", ordinal=1, support_specs=(_support("Calibrate sensor Juniper before noon.", "user", "requests calibration", "sensor Juniper", "calibrate_juniper", modality="requested", kind="task"), _support("Upload its calibration certificate to Folder Rook.", "user", "requests upload", "Juniper certificate", "upload_juniper_certificate", modality="requested", kind="task")), subject="user", predicate_surface="has composed task", object_value="calibrate Juniper and upload its certificate", decision="emit_l2", kind="task", sense="task.juniper_calibration_workflow", operator="compose_juniper_workflow", abstraction_method="task_composition", closure_pattern="multi_evidence_set"),
        dict(family="task_composition_case", ordinal=2, support_specs=(_support("Procure the amber filter for camera Lyra.", "user", "requests procurement", "amber filter", "procure_amber_filter", modality="requested", kind="task"), _support("Install it on camera Lyra after delivery.", "user", "requests installation", "amber filter", "install_amber_filter", modality="requested", kind="task")), subject="user", predicate_surface="has composed task", object_value="procure and install Lyra amber filter", decision="emit_l2", kind="task", sense="task.lyra_filter_workflow", operator="compose_lyra_filter_workflow", abstraction_method="task_composition", closure_pattern="multi_evidence_set"),
        dict(family="lifecycle_case", ordinal=1, support_specs=(_support("Send the topaz invoice to Accounts West.", "user", "requested recipient", "Accounts West", "topaz_old_recipient", modality="requested", kind="task"), _support("Correction: send the topaz invoice to Accounts North.", "user", "corrected recipient", "Accounts North", "topaz_new_recipient", modality="requested", kind="task")), subject="topaz invoice", predicate_surface="has current recipient", object_value="Accounts North", decision="emit_l2", kind="task", sense="billing.topaz_recipient_resolution", operator="resolve_topaz_recipient", abstraction_method="lifecycle_resolution", closure_pattern="update_supersession"),
        dict(family="lifecycle_case", ordinal=2, support_specs=(_support("The onyx demonstration was planned for 2026-12-02.", "onyx demonstration", "was planned for", "2026-12-02", "onyx_old_date", kind="state", event_time="2026-12-02"), _support("It was rescheduled to 2026-12-05.", "onyx demonstration", "was rescheduled to", "2026-12-05", "onyx_new_date", kind="state", event_time="2026-12-05")), subject="onyx demonstration", predicate_surface="has current date", object_value="2026-12-05", decision="emit_l2", kind="long_running_state", sense="calendar.onyx_date_resolution", operator="resolve_onyx_date", abstraction_method="lifecycle_resolution", closure_pattern="update_supersession"),
        dict(family="state_summary_case", ordinal=1, support_specs=(_support("My right wrist felt stiff after the dawn shift.", "right wrist", "felt", "stiff", "wrist_stiff_dawn", valid_time="dawn shift"), _support("The same wrist stiffness persisted after the evening shift.", "right wrist", "remained", "stiff", "wrist_stiff_evening", valid_time="evening shift")), subject="right wrist", predicate_surface="has persistent state", object_value="shift-related stiffness", decision="emit_l2", kind="long_running_state", sense="health.persistent_wrist_stiffness", operator="summarize_wrist_stiffness", abstraction_method="state_summary", closure_pattern="temporal_chain"),
        dict(family="state_summary_case", ordinal=2, support_specs=(_support("Compressor Iris vibrated above baseline on Monday.", "compressor Iris", "vibrated", "above baseline", "iris_vibration_monday", valid_time="Monday"), _support("Iris remained above the vibration baseline on Wednesday.", "compressor Iris", "remained", "above vibration baseline", "iris_vibration_wednesday", valid_time="Wednesday")), subject="compressor Iris", predicate_surface="has persistent state", object_value="elevated vibration", decision="emit_l2", kind="long_running_state", sense="maintenance.persistent_iris_vibration", operator="summarize_iris_vibration", abstraction_method="state_summary", closure_pattern="temporal_chain"),
        dict(family="preference_aggregation_case", ordinal=1, support_specs=(_support("I prefer a standing desk for morning analysis.", "user", "prefers", "standing desk", "standing_desk", kind="preference"), _support("I also prefer a dim task lamp during that work.", "user", "prefers", "dim task lamp", "dim_task_lamp", kind="preference")), subject="user", predicate_surface="has workspace preference profile", object_value="standing desk with dim task lamp", decision="emit_l2", kind="preference_profile", sense="preference.analysis_workspace_profile", operator="aggregate_analysis_workspace", abstraction_method="preference_aggregation", closure_pattern="multi_evidence_set"),
        dict(family="preference_aggregation_case", ordinal=2, support_specs=(_support("For overnight rail trips I prefer a quiet compartment.", "user", "prefers", "quiet rail compartment", "quiet_rail", kind="preference"), _support("For the same trips I require refundable lodging.", "user", "requires", "refundable lodging", "refundable_lodging", kind="preference")), subject="user", predicate_surface="has overnight travel profile", object_value="quiet rail compartment and refundable lodging", decision="emit_l2", kind="preference_profile", sense="preference.overnight_travel_profile", operator="aggregate_overnight_travel", abstraction_method="preference_aggregation", closure_pattern="multi_evidence_set"),
    ]
    blueprints = tuple(_make_l2_blueprint(**spec) for spec in specs)
    return tuple(
        blueprint
        for family in L2_FAMILIES
        for blueprint in blueprints
        if blueprint.family == family
    )


_L1_BLUEPRINTS = _l1_specs()
_L2_BLUEPRINTS = _l2_specs()


def _l1_vocabulary(blueprints: tuple[L1Blueprint, ...]) -> dict[str, list[str]]:
    return {
        "decisions": ["abstain", "emit_l1", "no_memory"],
        "kinds": ["attribute", "event", "preference", "state", "task"],
        "modalities": ["actual", "denied", "hypothetical", "planned", "recommended", "requested"],
        "polarities": ["negative", "positive"],
        "speakers": ["assistant", "tool", "user"],
        "canonical_operators": sorted(
            {item.vocabulary_operator for item in blueprints}
        ),
        "predicate_senses": sorted({item.vocabulary_sense for item in blueprints}),
        "condition_operators": ["after", "if"],
        "scope_operators": ["within"],
    }


def _render_l1(
    blueprints: tuple[L1Blueprint, ...],
    preregistration: dict[str, Any],
) -> FreshV3L1Layer:
    source_cases: list[L1SourceCase] = []
    public_cases: list[L1PublicCase] = []
    authority_cases: list[L1AuthorityCase] = []
    gold_items: list[L1GoldItem] = []
    for blueprint in blueprints:
        _validate_l1_blueprint(blueprint)
        expected = blueprint.expected_typed_candidate
        emits = expected is not None
        case_id = _opaque("case", blueprint.private_case_id)
        candidate_ref = _opaque("candidate", blueprint.candidate_id)
        event_times = [expected.time.event_time] if emits and expected.time.event_time else []
        valid_times = [expected.time.valid_time] if emits and expected.time.valid_time else []
        source_cases.append(
            L1SourceCase(
                private_case_id=blueprint.private_case_id,
                knowledge_id=blueprint.knowledge_id,
                expected_decision=blueprint.expected_decision,
                expected_typed_candidate=expected,
                emission_allowed=emits,
                allowed_modalities=[expected.modality] if emits else [],
                allowed_event_times=event_times,
                event_time_may_be_null=not event_times,
                allowed_valid_times=valid_times,
                valid_time_may_be_null=not valid_times,
                unresolved_required_fields=blueprint.unresolved_required_fields,
                time_case=("resolved" if event_times or valid_times else "unresolved" if "event_time" in blueprint.unresolved_required_fields else "none"),
            )
        )
        public_cases.append(
            L1PublicCase(
                case_id=case_id,
                candidate_ref=candidate_ref,
                source_turn=blueprint.source_turn,
                untyped_candidate=blueprint.untyped_candidate,
            )
        )
        evidence_bindings = [
            TypedEvidenceBinding(evidence_id=item.evidence_id, speaker=item.speaker)
            for item in blueprint.untyped_candidate.evidence
        ]
        derivation = expected.derivation if expected else TypedDerivationProvenance(
            method=blueprint.untyped_candidate.derivation,
            basis=blueprint.untyped_candidate.inference_basis,
            evidence_ids=[item.evidence_id for item in blueprint.untyped_candidate.evidence],
        )
        authority_cases.append(
            L1AuthorityCase(
                case_id=case_id,
                candidate_ref=candidate_ref,
                knowledge_id=blueprint.knowledge_id,
                candidate_id=blueprint.candidate_id,
                emission_allowed=emits,
                required_evidence_bindings=evidence_bindings,
                allowed_modalities=[expected.modality] if emits else [],
                allowed_polarities=[expected.polarity] if emits else ["positive"],
                allowed_event_times=event_times,
                event_time_may_be_null=not event_times,
                allowed_valid_times=valid_times,
                valid_time_may_be_null=not valid_times,
                allowed_condition_values=[item.value for item in expected.condition_bindings] if emits else [],
                allowed_scope_values=[item.value for item in expected.scope_bindings] if emits else [],
                required_derivation=derivation,
                required_lifecycle=expected.lifecycle if emits else blueprint.untyped_candidate.lifecycle_links,
                required_operation_provenance=expected.operation_provenance if emits else blueprint.untyped_candidate.operation_provenance,
                unresolved_required_fields=blueprint.unresolved_required_fields,
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
    vocabulary = _l1_vocabulary(blueprints)
    source = L1SourceConfig(dataset_id=L1_DATASET_ID, public_vocabulary=vocabulary, cases=source_cases)
    public = L1PublicPayload(dataset_id=L1_DATASET_ID, case_count=len(public_cases), allowed_vocabulary=vocabulary, cases=public_cases)
    authority = L1AuthorityPayload(dataset_id=L1_DATASET_ID, case_count=len(authority_cases), cases=authority_cases)
    gold = L1GoldPayload(dataset_id=L1_DATASET_ID, case_count=len(gold_items), items=gold_items)
    manifest = L1Manifest(
        dataset_id=L1_DATASET_ID,
        case_count=len(blueprints),
        input_sha256=preregistration["input_sha256"],
        output_sha256={
            "source-cases-l1.json": _hash_value(source),
            "public-l1.json": _hash_value(public),
            "authority-l1.json": _hash_value(authority),
            "gold-l1.json": _hash_value(gold),
        },
        distribution={"families": dict(Counter(item.family for item in blueprints)), "decisions": dict(Counter(item.expected_decision for item in blueprints))},
        claim_boundary={"pipeline_integration_authorized": False, "automatic_writes_authorized": False, "longmemeval_status": "structured_l2_identity_unresolved"},
    )
    return FreshV3L1Layer(blueprints=blueprints, source=source, public=public, authority=authority, gold=gold, manifest=manifest)


def _l2_vocabulary(blueprints: tuple[L2Blueprint, ...]) -> dict[str, list[str]]:
    return {
        "decisions": ["abstain", "emit_l2"],
        "l2_kinds": ["habit", "long_running_state", "preference_profile", "project", "summary_event", "task"],
        "abstraction_methods": ["coreference_resolution", "lifecycle_resolution", "preference_aggregation", "state_summary", "task_composition"],
        "closure_patterns": ["causal_answerability", "multi_evidence_set", "single_fact", "temporal_chain", "update_supersession"],
        "modalities": ["actual", "denied", "hypothetical", "planned", "recommended", "requested"],
        "polarities": ["negative", "positive"],
        "canonical_operators": sorted(
            {item.vocabulary_operator for item in blueprints}
        ),
        "predicate_senses": sorted({item.vocabulary_sense for item in blueprints}),
        "operator_sense_bindings": sorted(
            {
                f"{item.vocabulary_operator}|{item.vocabulary_sense}"
                for item in blueprints
            }
        ),
    }


def _render_l2(
    blueprints: tuple[L2Blueprint, ...],
    preregistration: dict[str, Any],
) -> FreshV3L2Layer:
    source_cases: list[L2SourceCase] = []
    public_cases: list[L2PublicCase] = []
    authority_cases: list[L2AuthorityCase] = []
    gold_items: list[L2GoldItem] = []
    for blueprint in blueprints:
        _validate_l2_blueprint(blueprint)
        expected = blueprint.expected_typed_candidate
        emits = expected is not None
        case_id = _opaque("case", blueprint.private_case_id)
        candidate_ref = _opaque("candidate", blueprint.candidate_id)
        support_refs = [item.support_ref for item in blueprint.typed_l1_support_pack]
        evidence_bindings = [binding for support in blueprint.typed_l1_support_pack for binding in support.evidence_bindings]
        turn_refs = [item.source_turn_ref for item in blueprint.source_turns]
        source_cases.append(
            L2SourceCase(
                private_case_id=blueprint.private_case_id,
                knowledge_id=blueprint.knowledge_id,
                expected_decision=blueprint.expected_decision,
                typed_l1_support_pack=list(blueprint.typed_l1_support_pack),
                expected_typed_candidate=expected,
                emission_allowed=emits,
                allowed_abstraction_methods=[expected.abstraction.method] if emits else [],
                allowed_closure_patterns=[expected.closure.pattern] if emits else [],
                unresolved_required_fields=blueprint.unresolved_required_fields,
            )
        )
        public_cases.append(
            L2PublicCase(
                case_id=case_id,
                candidate_ref=candidate_ref,
                source_session_ref=blueprint.source_session_ref,
                source_turns=list(blueprint.source_turns),
                untyped_candidate=blueprint.untyped_candidate,
                typed_l1_support_pack=list(blueprint.typed_l1_support_pack),
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
                required_evidence_bindings=evidence_bindings,
                required_source_turn_refs=turn_refs,
                required_source_session_refs=[blueprint.source_session_ref],
                allowed_abstraction_methods=[expected.abstraction.method] if emits else [],
                allowed_closure_patterns=[expected.closure.pattern] if emits else [],
                unresolved_required_fields=blueprint.unresolved_required_fields,
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
    vocabulary = _l2_vocabulary(blueprints)
    source = L2SourceConfig(dataset_id=L2_DATASET_ID, public_vocabulary=vocabulary, cases=source_cases)
    public = L2PublicPayload(dataset_id=L2_DATASET_ID, case_count=len(public_cases), allowed_vocabulary=vocabulary, cases=public_cases)
    authority = L2AuthorityPayload(dataset_id=L2_DATASET_ID, case_count=len(authority_cases), cases=authority_cases)
    gold = L2GoldPayload(dataset_id=L2_DATASET_ID, case_count=len(gold_items), items=gold_items)
    thresholds = {**preregistration["quality_thresholds"]["l2"], **preregistration["safety_thresholds"]}
    manifest = L2Manifest(
        dataset_id=L2_DATASET_ID,
        case_count=len(blueprints),
        input_sha256=preregistration["input_sha256"],
        l1_qualification_sha256={"qualification.json": preregistration["passing_chains"]["l1"]["artifact_sha256"]["qualification.json"]},
        output_sha256={
            "source-cases-l2.json": _hash_value(source),
            "public-l2.json": _hash_value(public),
            "authority-l2.json": _hash_value(authority),
            "gold-l2.json": _hash_value(gold),
        },
        distribution={"families": dict(Counter(item.family for item in blueprints)), "decisions": dict(Counter(item.expected_decision for item in blueprints))},
        thresholds=thresholds,
        claim_boundary={"pipeline_integration_authorized": False, "automatic_writes_authorized": False, "longmemeval_status": "structured_l2_identity_unresolved"},
    )
    return FreshV3L2Layer(blueprints=blueprints, source=source, public=public, authority=authority, gold=gold, manifest=manifest)


def _validate_l1_blueprint(blueprint: L1Blueprint) -> None:
    if (blueprint.expected_decision == "emit_l1") != (blueprint.expected_typed_candidate is not None):
        raise ValueError("L1 decision and typed candidate mismatch")
    for evidence in blueprint.untyped_candidate.evidence:
        message = blueprint.source_turn[evidence.message]
        if evidence.end <= evidence.start or message[evidence.start:evidence.end] != evidence.quote:
            raise ValueError(f"L1 evidence offset mismatch: {blueprint.blueprint_id}")
        expected_message = "user" if evidence.speaker == "user" else "agent"
        if evidence.message != expected_message:
            raise ValueError("L1 evidence speaker/message mismatch")
    if blueprint.expected_typed_candidate:
        expected = blueprint.expected_typed_candidate
        if (
            expected.predicate.canonical_operator != blueprint.vocabulary_operator
            or expected.predicate.sense != blueprint.vocabulary_sense
        ):
            raise ValueError("L1 vocabulary binding mismatch")
        expected_bindings = {
            (item.evidence_id, item.speaker) for item in expected.evidence_bindings
        }
        actual_bindings = {
            (item.evidence_id, item.speaker)
            for item in blueprint.untyped_candidate.evidence
        }
        if (
            expected_bindings != actual_bindings
            or len(expected_bindings) != len(expected.evidence_bindings)
            or len(actual_bindings) != len(blueprint.untyped_candidate.evidence)
        ):
            raise ValueError("L1 evidence binding mismatch")
        if expected.lifecycle != blueprint.untyped_candidate.lifecycle_links:
            raise ValueError("L1 lifecycle binding mismatch")
        if expected.operation_provenance != blueprint.untyped_candidate.operation_provenance:
            raise ValueError("L1 operation provenance mismatch")
        for binding in [*expected.condition_bindings, *expected.scope_bindings]:
            if binding.local_entity_ids != _binding_entity_ids(
                binding.value,
                expected.local_entities,
            ):
                raise ValueError("L1 qualifier local entity binding mismatch")
    registry = blueprint.untyped_candidate.qualifiers.get("reference_registry")
    candidate_refs = _lifecycle_candidate_refs(
        blueprint.untyped_candidate.lifecycle_links
    )
    operation_refs = _operation_refs(
        blueprint.untyped_candidate.operation_provenance
    )
    if not isinstance(registry, dict) or registry.get("candidate_refs") != candidate_refs:
        raise ValueError("L1 lifecycle reference registry mismatch")
    if set(registry) != {
        "candidate_refs",
        "operation_refs",
        "candidate_records",
        "operation_records",
    }:
        raise ValueError("L1 reference registry field mismatch")
    if registry.get("operation_refs") != operation_refs:
        raise ValueError("L1 operation reference registry mismatch")
    current_candidate_ref = _opaque("candidate", blueprint.candidate_id)
    candidate_records = registry.get("candidate_records")
    operation_records = registry.get("operation_records")
    if not isinstance(candidate_records, list) or not isinstance(operation_records, list):
        raise ValueError("L1 reference registry record closure mismatch")
    candidate_record_refs = [
        record.get("candidate_ref") for record in candidate_records if isinstance(record, dict)
    ]
    if (
        len(candidate_records) != len(candidate_refs)
        or len(candidate_record_refs) != len(candidate_records)
        or len(candidate_record_refs) != len(set(candidate_record_refs))
        or set(candidate_record_refs) != set(candidate_refs)
    ):
        raise ValueError("L1 candidate reference record closure mismatch")
    operation_record_refs = [
        record.get("operation_ref") for record in operation_records if isinstance(record, dict)
    ]
    if (
        len(operation_records) != len(operation_refs)
        or len(operation_record_refs) != len(operation_records)
        or len(operation_record_refs) != len(set(operation_record_refs))
        or set(operation_record_refs) != set(operation_refs)
    ):
        raise ValueError("L1 operation reference record closure mismatch")
    if any(
        not isinstance(record, dict)
        or record.get("owner_candidate_ref") != current_candidate_ref
        or record.get("relation") != "prior_revision"
        for record in candidate_records
    ):
        raise ValueError("L1 lifecycle reference owner mismatch")
    confirmed_refs = set(
        blueprint.untyped_candidate.operation_provenance.confirmed_by_operation_refs
    )
    added_refs = set(
        blueprint.untyped_candidate.operation_provenance.added_by_operation_refs
    )
    if confirmed_refs & added_refs:
        raise ValueError("L1 operation reference record closure mismatch")
    operation_kind, operation_targets, operation_replacement = (
        _operation_record_shape(
            blueprint.untyped_candidate.lifecycle_links,
            current_candidate_ref,
        )
    )
    if operation_kind == "confirm":
        provenance_matches = set(operation_refs) == confirmed_refs and not added_refs
    else:
        provenance_matches = set(operation_refs) == added_refs and not confirmed_refs
    expected_operation_records = [
        {
            "operation_ref": operation_ref,
            "owner_candidate_ref": current_candidate_ref,
            "operation_kind": operation_kind,
            "targets": operation_targets,
            "replacement_candidate_ref": operation_replacement,
        }
        for operation_ref in operation_refs
    ]
    if not provenance_matches or operation_records != expected_operation_records:
        raise ValueError("L1 operation reference owner mismatch")
    if blueprint.expected_decision != "emit_l1" and (
        candidate_refs or operation_refs or candidate_records or operation_records
    ):
        raise ValueError("L1 non-emission reference closure mismatch")


def _validate_l2_blueprint(blueprint: L2Blueprint) -> None:
    if (blueprint.expected_decision == "emit_l2") != (blueprint.expected_typed_candidate is not None):
        raise ValueError("L2 decision and typed candidate mismatch")
    turn_by_ref = {item.source_turn_ref: item for item in blueprint.source_turns}
    if len(turn_by_ref) != len(blueprint.source_turns):
        raise ValueError("L2 duplicate source turn reference")
    evidence_to_binding: dict[str, tuple[str, str]] = {}
    for support in blueprint.typed_l1_support_pack:
        if support.source_session_ref != blueprint.source_session_ref:
            raise ValueError("L2 support session mismatch")
        turn = turn_by_ref.get(support.source_turn_ref)
        if turn is None:
            raise ValueError("L2 support references unknown source turn")
        support_text = _normalize_text(turn.user + " " + turn.agent)
        for time_value in (support.time.event_time, support.time.valid_time):
            if time_value and _normalize_text(time_value) not in support_text:
                raise ValueError("L2 support time evidence mismatch")
        for binding in support.evidence_bindings:
            if binding.evidence_id in evidence_to_binding:
                raise ValueError("L2 duplicate support evidence reference")
            message = turn.user if binding.speaker == "user" else turn.agent
            evidence_to_binding[binding.evidence_id] = (binding.speaker, message)
    public_bindings: set[tuple[str, str]] = set()
    for evidence in blueprint.untyped_candidate.evidence:
        support_binding = evidence_to_binding.get(evidence.evidence_id)
        if support_binding is None:
            raise ValueError(f"L2 evidence offset mismatch: {blueprint.blueprint_id}")
        speaker, message = support_binding
        if evidence.speaker != speaker:
            raise ValueError("L2 evidence speaker mismatch")
        expected_message = "user" if evidence.speaker == "user" else "agent"
        if evidence.message != expected_message:
            raise ValueError("L2 evidence speaker/message mismatch")
        public_bindings.add((evidence.evidence_id, evidence.speaker))
        if evidence.end <= evidence.start or message[evidence.start:evidence.end] != evidence.quote:
            raise ValueError(f"L2 evidence offset mismatch: {blueprint.blueprint_id}")
    support_bindings = {
        (evidence_id, speaker)
        for evidence_id, (speaker, _) in evidence_to_binding.items()
    }
    if (
        public_bindings != support_bindings
        or len(public_bindings) != len(blueprint.untyped_candidate.evidence)
    ):
        raise ValueError("L2 public/support evidence closure mismatch")
    support_refs = {item.support_ref for item in blueprint.typed_l1_support_pack}
    if blueprint.family == "lifecycle_case":
        if len(blueprint.support_lifecycle_bindings) != len(support_refs):
            raise ValueError("L2 lifecycle support closure mismatch")
        bindings_by_support = {
            item.support_ref: item for item in blueprint.support_lifecycle_bindings
        }
        if set(bindings_by_support) != support_refs:
            raise ValueError("L2 lifecycle support reference mismatch")
        inverse_relations = {
            "superseded_by": "supersedes",
            "supersedes": "superseded_by",
        }
        for binding in blueprint.support_lifecycle_bindings:
            counterpart = bindings_by_support.get(binding.counterpart_support_ref)
            if (
                binding.counterpart_support_ref == binding.support_ref
                or counterpart is None
                or counterpart.counterpart_support_ref != binding.support_ref
                or counterpart.relation != inverse_relations[binding.relation]
            ):
                raise ValueError("L2 lifecycle support relation mismatch")
    elif blueprint.support_lifecycle_bindings:
        raise ValueError("L2 unexpected lifecycle support bindings")
    if blueprint.untyped_candidate.qualifiers != {
        "support_count": len(blueprint.typed_l1_support_pack)
    }:
        raise ValueError("L2 public qualifier mismatch")
    if blueprint.expected_typed_candidate is None:
        if not blueprint.unresolved_required_fields:
            raise ValueError("L2 abstention requires unresolved fields")
        return
    expected = blueprint.expected_typed_candidate
    primary = expected.structured_claims[0]
    if (
        primary.predicate.canonical_operator != blueprint.vocabulary_operator
        or primary.predicate.sense != blueprint.vocabulary_sense
    ):
        raise ValueError("L2 vocabulary binding mismatch")
    expected_evidence = {
        (item.evidence_id, item.speaker) for item in expected.evidence_bindings
    }
    if (
        expected_evidence != support_bindings
        or len(expected_evidence) != len(expected.evidence_bindings)
    ):
        raise ValueError("L2 evidence closure mismatch")
    if set(expected.supporting_l1_refs) != support_refs or set(expected.closure.required_support_refs) != support_refs:
        raise ValueError("L2 support closure mismatch")
    claim_supports = {ref for claim in expected.structured_claims for ref in claim.supporting_l1_refs}
    if claim_supports != support_refs:
        raise ValueError("L2 support closure mismatch")
    if primary.predicate.surface != blueprint.untyped_candidate.predicate:
        raise ValueError("L2 public predicate literal binding mismatch")
    support_modalities = {item.modality for item in blueprint.typed_l1_support_pack}
    if len(support_modalities) != 1 or primary.modality != next(iter(support_modalities)):
        raise ValueError("L2 support modality closure mismatch")
    if primary.time != _l2_claim_time_from_supports(
        blueprint.family,
        blueprint.typed_l1_support_pack
    ):
        raise ValueError("L2 claim time closure mismatch")
    if primary.local_entities[0].surface != blueprint.untyped_candidate.subject or primary.local_entities[1].surface != blueprint.untyped_candidate.object:
        raise ValueError("L2 public entity literal binding mismatch")
    if set(expected.source_turn_refs) != set(turn_by_ref) or expected.source_session_refs != [blueprint.source_session_ref]:
        raise ValueError("L2 source closure mismatch")


def _private_identifiers(bundle: FreshV3AuthoringBundle) -> set[str]:
    values: set[str] = set()
    for blueprint in (*bundle.l1.blueprints, *bundle.l2.blueprints):
        values.update({blueprint.blueprint_id, blueprint.private_case_id, blueprint.knowledge_id, blueprint.candidate_id})
    values.update(item.private_session_id for item in bundle.l2.blueprints)
    return values


_FORBIDDEN_PUBLIC_KEYS = {
    "authority",
    "emission_allowed",
    "expected_decision",
    "expected_typed_candidate",
    "family",
    "gold",
    "primary_family",
    "prior_inventory",
    "private_case_id",
    "private_session_id",
    "receipt",
    "secondary_family",
    "unresolved_required_fields",
}


def _contains_forbidden_public_key(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(set(value) & _FORBIDDEN_PUBLIC_KEYS) or any(
            _contains_forbidden_public_key(child) for child in value.values()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_public_key(child) for child in value)
    return False


def _new_inventory(bundle: FreshV3AuthoringBundle) -> PriorInventory:
    identifiers: set[str] = set()
    evidence_ids: set[str] = set()
    evidence_texts: set[str] = set()
    source_texts: set[str] = set()
    semantic_signatures: set[str] = set()
    _walk_prior(
        bundle.model_dump(mode="json"),
        key=None,
        identifiers=identifiers,
        evidence_ids=evidence_ids,
        evidence_texts=evidence_texts,
        source_texts=source_texts,
        semantic_signatures=semantic_signatures,
    )
    return PriorInventory(
        identifiers=sorted(identifiers),
        evidence_ids=sorted(evidence_ids),
        evidence_texts=sorted(evidence_texts),
        source_texts=sorted(source_texts),
        semantic_signatures=sorted(semantic_signatures),
    )


def _validate_family_order(blueprints: tuple[Any, ...], families: dict[str, int], layer: str) -> None:
    expected = [(family, ordinal) for family, count in families.items() for ordinal in range(1, count + 1)]
    actual = [(item.family, item.ordinal) for item in blueprints]
    if actual != expected:
        raise ValueError(f"{layer} family order mismatch")
    ids = [item.blueprint_id for item in blueprints]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate {layer} blueprint ID")


def build_fresh_v3_authoring_bundle(
    preregistration_path: Path,
) -> FreshV3AuthoringBundle:
    preregistration = _load_preregistration(preregistration_path)
    prior = _build_prior_inventory(preregistration_path)
    bundle = FreshV3AuthoringBundle(
        prior_inventory_sha256=_hash_value(prior),
        l1=_render_l1(_L1_BLUEPRINTS, preregistration),
        l2=_render_l2(_L2_BLUEPRINTS, preregistration),
    )
    validate_fresh_v3_authoring_bundle(bundle, preregistration_path)
    return bundle


def validate_fresh_v3_authoring_bundle(
    bundle: FreshV3AuthoringBundle,
    preregistration_path: Path,
) -> dict[str, Any]:
    strict_payload = bundle.model_dump(mode="python", warnings=False)
    try:
        FreshV3AuthoringBundle.model_validate(strict_payload, strict=True)
    except ValidationError as error:
        # Preserve the more specific domain errors below, but reject coercive
        # or structurally invalid values before they reach offset operations.
        if any(item["type"] != "value_error" for item in error.errors()):
            raise
    preregistration = _load_preregistration(preregistration_path)
    _validate_family_order(bundle.l1.blueprints, L1_FAMILIES, "L1")
    _validate_family_order(bundle.l2.blueprints, L2_FAMILIES, "L2")
    expected_l1 = _render_l1(bundle.l1.blueprints, preregistration)
    expected_l2 = _render_l2(bundle.l2.blueprints, preregistration)
    if bundle.l1 != expected_l1:
        raise ValueError("L1 rendered bundle drift")
    if bundle.l2 != expected_l2:
        raise ValueError("L2 rendered bundle drift")
    public_payloads = (
        bundle.l1.public.model_dump(mode="json"),
        bundle.l2.public.model_dump(mode="json"),
    )
    if any(_contains_forbidden_public_key(value) for value in public_payloads):
        raise ValueError("private family field leaked into public payload")
    public_text = (canonical_json_bytes(bundle.l1.public) + canonical_json_bytes(bundle.l2.public)).decode()
    leaked = {value for value in _private_identifiers(bundle) if value in public_text}
    if leaked:
        raise ValueError("private identifier leaked into public payload")
    if bundle.l1.blueprints != _L1_BLUEPRINTS:
        raise ValueError("authored L1 blueprint manifest drift")
    if bundle.l2.blueprints != _L2_BLUEPRINTS:
        raise ValueError("authored L2 blueprint manifest drift")
    prior = _build_prior_inventory(preregistration_path)
    current = _new_inventory(bundle)
    overlaps = {
        "identifier": set(current.identifiers) & set(prior.identifiers),
        "evidence": set(current.evidence_ids) & set(prior.evidence_ids),
        "evidence text": set(current.evidence_texts) & set(prior.evidence_texts),
        "source text": set(current.source_texts) & set(prior.source_texts),
        "semantic signature": set(current.semantic_signatures) & set(prior.semantic_signatures),
    }
    for label, values in overlaps.items():
        if values:
            raise ValueError(f"prior {label} overlap")
    if bundle.prior_inventory_sha256 != _hash_value(prior):
        raise ValueError("prior inventory hash drift")
    FreshV3AuthoringBundle.model_validate(strict_payload, strict=True)
    return {
        "status": "valid",
        "l1_case_count": len(bundle.l1.blueprints),
        "l2_case_count": len(bundle.l2.blueprints),
        "l1_family_counts": dict(Counter(item.family for item in bundle.l1.blueprints)),
        "l2_family_counts": dict(Counter(item.family for item in bundle.l2.blueprints)),
        "prior_identifier_overlap_count": 0,
        "prior_evidence_overlap_count": 0,
        "prior_source_text_overlap_count": 0,
        "prior_semantic_signature_overlap_count": 0,
        "formal_artifacts_created": False,
        "model_request_count": 0,
    }


def _code_paths(workspace_root: Path) -> dict[str, Path]:
    module_root = workspace_root / "tools/natural_memory_benchmark"
    test_root = workspace_root / "tests/natural_memory_benchmark"
    return {
        "typed_extractor_fresh_v3_authoring.py": module_root / "typed_extractor_fresh_v3_authoring.py",
        "test_typed_extractor_fresh_v3_authoring.py": test_root / "test_typed_extractor_fresh_v3_authoring.py",
    }


def _dependency_paths(workspace_root: Path) -> dict[str, Path]:
    module_root = workspace_root / "tools/natural_memory_benchmark"
    return {
        "authoritative_conformance_runner.py": module_root
        / "authoritative_conformance_runner.py",
        "authoritative_memory.py": module_root / "authoritative_memory.py",
        "io.py": module_root / "io.py",
        "typed_extractor_fresh_v3_prereg.py": module_root / "typed_extractor_fresh_v3_prereg.py",
        "typed_extractor_l1.py": module_root / "typed_extractor_l1.py",
        "typed_extractor_l2.py": module_root / "typed_extractor_l2.py",
    }


def _resolved_future_path(workspace_root: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    return _absolute_lexical_path(path if path.is_absolute() else workspace_root / path)


def _absolute_lexical_path(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _entry_exists(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _assert_path_matches_opened(
    path: Path,
    opened: os.stat_result,
    *,
    label: str,
) -> None:
    try:
        current = path.lstat()
    except FileNotFoundError as exc:
        raise ValueError(f"{label} path changed while locked") from exc
    if (
        not stat.S_ISREG(current.st_mode)
        or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino)
    ):
        raise ValueError(f"{label} path changed while locked")


def _read_regular_path(
    path: Path,
    *,
    label: str,
) -> tuple[bytes, os.stat_result]:
    try:
        initial = path.lstat()
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"{label} missing: {path}") from exc
    if not stat.S_ISREG(initial.st_mode):
        raise ValueError(f"{label} path must be a regular non-symlink file")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or (opened.st_dev, opened.st_ino) != (initial.st_dev, initial.st_ino)
        ):
            raise ValueError(f"{label} path changed during validation")
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 1024 * 1024):
            chunks.append(chunk)
        _assert_path_matches_opened(path, opened, label=label)
        return b"".join(chunks), opened
    finally:
        os.close(descriptor)


def _canonical_evaluation_root(workspace_root: Path) -> Path:
    """The official evaluation root, as the frozen receipt describes it.

    Derived here rather than imported from the relocation module, which imports
    this one -- taking it from there would be a cycle.
    """
    return (
        Path(workspace_root)
        / "artifacts"
        / "automatic-extraction-assessment"
        / f"{EVALUATION_ID}"
    )


def _require_receipt_future_absent(evaluation_root: Path, workspace_root: Path) -> None:
    """Verify both expired temporal claims against the frozen receipt.

    Two orderings were asserted at authoring time: the evaluation root did not
    exist yet, and the later materialization stage had not been implemented.
    Neither can be re-established by inspecting the filesystem now -- the
    evaluation root was committed as evidence, and the materialization module has
    existed since before the reorganization baseline. Re-running those checks
    re-discovers that time passed rather than detecting a regression.

    Both claims stay verified, against the artifact that witnesses them: the
    frozen authoring receipt records ``evaluation_root_absent``,
    ``materialization_implementation_absent``, the paths each check covered, and a
    git blob OID per file at receipt time. That is a stronger check -- a rewritten
    receipt fails it, whereas the live checks would have started passing again the
    moment someone deleted the downstream module or the evaluation root.

    The caller's own target is different: writing into a root that already exists
    would clobber it, so that check is live and stays. It applies to the root this
    call was asked to write, not to the canonical root the receipt describes.
    """
    if evaluation_root != _canonical_evaluation_root(workspace_root) and (
        _entry_exists(evaluation_root)
    ):
        raise ValueError("fresh v3 evaluation root must be absent before authoring receipt")

    from .expired_temporal_guard import (
        verify_evaluation_root_absence_was_witnessed,
        verify_materialization_absence_was_witnessed,
    )

    verify_evaluation_root_absence_was_witnessed(workspace_root)

    report = verify_materialization_absence_was_witnessed(workspace_root)
    if not report.witnessed_absent_at_receipt_time:
        raise ValueError(
            "authoring receipt does not witness materialization absence: the "
            "temporal claim was never established and cannot be treated as expired"
        )
    if set(report.witnessed_paths) != set(MATERIALIZATION_WORKSPACE_PATHS):
        raise ValueError(
            "authoring receipt witnesses a different path set than this guard "
            "declares; the witness does not cover the claim"
        )


def _validate_chronology_paths(
    *,
    preregistration: dict[str, Any],
    preregistration_path: Path,
    evaluation_root: Path,
    workspace_root: Path,
) -> None:
    chronology = preregistration.get("chronology")
    if not isinstance(chronology, dict):
        raise ValueError("fresh v3 preregistration chronology missing")
    expected_preregistration_root = _absolute_lexical_path(
        Path(chronology.get("preregistration_root", ""))
    )
    expected_evaluation_root = _absolute_lexical_path(
        Path(chronology.get("evaluation_root", ""))
    )
    if (
        preregistration_path.parent != expected_preregistration_root
        or evaluation_root != expected_evaluation_root
        or workspace_root != WORKSPACE_ROOT
    ):
        raise ValueError("fresh v3 chronology path mismatch")


def _guard_counts(bundle: Any) -> dict[str, int]:
    return {
        "closure_evaluation_count": len(bundle.closure_evaluations),
        "closure_spec_count": len(bundle.closure_specs),
        "l1_unit_count": len(bundle.l1_units),
        "l2_unit_count": len(bundle.l2_units),
        "query_plan_count": len(bundle.query_plans),
        "raw_artifact_revision_count": len(bundle.raw_artifact_revisions),
        "source_record_revision_count": len(bundle.source_record_revisions),
        "unit_revision_count": len(bundle.unit_revisions),
    }


def _protected_state(workspace_root: Path) -> dict[str, Any]:
    queue = workspace_root / "artifacts/identity-memory-experiment/candidate-generation-assessment-v3/candidate-review-queue.json"
    if sha256_file(queue) != CANDIDATE_QUEUE_SHA256:
        raise ValueError("candidate v3 queue drift")
    overall = workspace_root / "artifacts/automatic-extraction-assessment/typed-extractor-v2-fresh-hidden-v2/overall-score.json"
    if load_json(overall).get("guard_fingerprint") != GUARD_FINGERPRINT:
        raise ValueError("guard fingerprint drift")
    guard_results = workspace_root / GUARD_RESULTS_WORKSPACE_PATH
    guard_results_sha256 = sha256_file(guard_results)
    if guard_results_sha256 != GUARD_RESULTS_SHA256:
        raise ValueError("live guard results drift")
    guard_root = workspace_root / "artifacts/natural-benchmark-slices"
    bundle = build_authoritative_conformance_bundle(
        guard_root,
        "slice-v1",
        guard_results,
    )
    bundle = bundle.model_copy(
        update={
            "metadata": {
                **bundle.metadata,
                "source_results": GUARD_RESULTS_WORKSPACE_PATH,
            }
        }
    )
    fingerprint = canonical_sha256(bundle)
    if fingerprint != GUARD_FINGERPRINT:
        raise ValueError("live guard fingerprint drift")
    counts = _guard_counts(bundle)
    if counts != GUARD_COUNTS:
        raise ValueError("live guard count drift")
    return {
        "guard_results_sha256": guard_results_sha256,
        "guard_counts": counts,
    }


def _build_receipt(
    *,
    preregistration_path: Path,
    evaluation_root: Path,
    workspace_root: Path,
    receipt_time: str,
) -> FreshV3AuthoringReceipt:
    preregistration = _load_preregistration(preregistration_path)
    _validate_chronology_paths(
        preregistration=preregistration,
        preregistration_path=preregistration_path,
        evaluation_root=evaluation_root,
        workspace_root=workspace_root,
    )
    _require_receipt_future_absent(evaluation_root, workspace_root)
    protected_state = _protected_state(workspace_root)
    bundle = build_fresh_v3_authoring_bundle(preregistration_path)
    code_paths = _code_paths(workspace_root)
    dependency_paths = _dependency_paths(workspace_root)
    for name, path in {**code_paths, **dependency_paths}.items():
        if not path.is_file():
            raise FileNotFoundError(f"authoring receipt dependency missing: {name}")
    return FreshV3AuthoringReceipt(
        receipt_time=receipt_time,
        preregistration_path=str(preregistration_path),
        code_sha256={name: sha256_file(path) for name, path in code_paths.items()},
        dependency_sha256={name: sha256_file(path) for name, path in dependency_paths.items()},
        blueprint_manifest_sha256={
            "l1": _hash_value(
                [item.model_dump(mode="json") for item in bundle.l1.blueprints]
            ),
            "l2": _hash_value(
                [item.model_dump(mode="json") for item in bundle.l2.blueprints]
            ),
        },
        prior_input_sha256=preregistration["input_sha256"],
        l1_families=dict(L1_FAMILIES),
        l2_families=dict(L2_FAMILIES),
        evaluation_root=str(evaluation_root),
        materialization_workspace_paths=list(MATERIALIZATION_WORKSPACE_PATHS),
        automatic_write_counts=dict(AUTOMATIC_WRITE_COUNTS),
        guard_results_sha256=protected_state["guard_results_sha256"],
        guard_counts=protected_state["guard_counts"],
    )


@contextmanager
def fresh_v3_chronology_lock(
    preregistration_path: Path,
) -> Iterator[os.stat_result]:
    """Serialize receipt and future materializer publication."""
    preregistration_path = _absolute_lexical_path(preregistration_path)
    try:
        initial = preregistration_path.lstat()
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"fresh v3 preregistration missing: {preregistration_path}"
        ) from exc
    if not stat.S_ISREG(initial.st_mode):
        raise ValueError(
            "fresh v3 preregistration path must be a regular non-symlink file"
        )
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    descriptor = os.open(preregistration_path, flags)
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or (opened.st_dev, opened.st_ino) != (initial.st_dev, initial.st_ino)
        ):
            raise ValueError("fresh v3 preregistration path changed before lock")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        try:
            _assert_path_matches_opened(
                preregistration_path,
                opened,
                label="fresh v3 preregistration",
            )
            yield opened
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def _publish_fd_noreplace(
    descriptor: int,
    directory_descriptor: int,
    target_name: str,
) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    linkat = getattr(libc, "linkat", None)
    if linkat is None:
        raise RuntimeError("linkat is required for fd-bound receipt publication")
    linkat.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
    ]
    linkat.restype = ctypes.c_int
    result = linkat(
        descriptor,
        b"",
        directory_descriptor,
        os.fsencode(target_name),
        _AT_EMPTY_PATH,
    )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number == errno.EEXIST:
        raise FileExistsError(
            error_number,
            f"fresh v3 authoring receipt already exists: {target_name}",
            target_name,
        )
    if error_number in {
        errno.EINVAL,
        errno.ENOENT,
        errno.ENOSYS,
        errno.EOPNOTSUPP,
        errno.EPERM,
    }:
        raise RuntimeError(
            "linkat(AT_EMPTY_PATH) is unsupported for receipt publication"
        )
    raise OSError(
        error_number,
        os.strerror(error_number),
        target_name,
    )


def _open_anonymous_receipt(directory: Path) -> int:
    temporary_flag = getattr(os, "O_TMPFILE", 0)
    if temporary_flag == 0:
        raise RuntimeError("O_TMPFILE is unsupported for receipt publication")
    flags = os.O_RDWR | temporary_flag | getattr(os, "O_CLOEXEC", 0)
    try:
        return os.open(directory, flags, 0o600)
    except OSError as exc:
        raise RuntimeError(
            "O_TMPFILE is unsupported for receipt publication"
        ) from exc


def _write_all(descriptor: int, content: bytes) -> None:
    offset = 0
    while offset < len(content):
        written = os.write(descriptor, content[offset:])
        if written <= 0:
            raise OSError(errno.EIO, "receipt staging write made no progress")
        offset += written


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(
        os, "O_CLOEXEC", 0
    )
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_existing_receipt(
    receipt_path: Path,
) -> tuple[bytes, os.stat_result] | None:
    if not _entry_exists(receipt_path):
        return None
    try:
        content, opened = _read_regular_path(
            receipt_path,
            label="fresh v3 authoring receipt",
        )
    except FileNotFoundError:
        return None
    # No mode precondition: the receipt is committed, so 0444 does not survive a
    # clone. Its integrity comes from _require_matching_existing_receipt, which
    # compares the bytes and refuses a receipt that already differs.
    return content, opened


def _require_matching_existing_receipt(
    receipt_path: Path,
    content: bytes,
) -> os.stat_result | None:
    existing = _read_existing_receipt(receipt_path)
    if existing is None:
        return None
    existing_content, opened = existing
    if existing_content != content:
        raise ValueError("fresh v3 authoring receipt already differs")
    return opened


def _write_receipt_no_clobber(
    receipt_path: Path,
    receipt: FreshV3AuthoringReceipt,
    *,
    before_publish: Callable[[], None] | None = None,
) -> None:
    content = canonical_json_bytes(receipt)
    matching_receipt = _require_matching_existing_receipt(receipt_path, content)
    if matching_receipt is not None:
        if before_publish is not None:
            before_publish()
        _fsync_directory(receipt_path.parent)
        _assert_path_matches_opened(
            receipt_path,
            matching_receipt,
            label="fresh v3 authoring receipt",
        )
        return
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    directory_descriptor = os.open(receipt_path.parent, directory_flags)
    try:
        descriptor = _open_anonymous_receipt(receipt_path.parent)
        try:
            _write_all(descriptor, content)
            os.fsync(descriptor)
            os.fchmod(descriptor, 0o444)
            os.fsync(descriptor)
            if before_publish is not None:
                before_publish()
            try:
                _publish_fd_noreplace(
                    descriptor,
                    directory_descriptor,
                    receipt_path.name,
                )
            except FileExistsError:
                matching_receipt = _require_matching_existing_receipt(
                    receipt_path,
                    content,
                )
                if matching_receipt is None:
                    raise ValueError(
                        "fresh v3 authoring receipt disappeared during publication"
                    )
                os.fsync(directory_descriptor)
                _assert_path_matches_opened(
                    receipt_path,
                    matching_receipt,
                    label="fresh v3 authoring receipt",
                )
                return
            os.fsync(directory_descriptor)
            _assert_path_matches_opened(
                receipt_path,
                os.fstat(descriptor),
                label="fresh v3 authoring receipt",
            )
        finally:
            os.close(descriptor)
    finally:
        os.close(directory_descriptor)


def freeze_fresh_v3_authoring_receipt(
    preregistration_path: Path,
    evaluation_root: Path,
    workspace_root: Path,
    receipt_time: str,
) -> dict[str, Any]:
    preregistration_path = _absolute_lexical_path(preregistration_path)
    evaluation_root = _absolute_lexical_path(evaluation_root)
    workspace_root = _absolute_lexical_path(workspace_root)
    receipt_path = preregistration_path.parent / RECEIPT_NAME
    with fresh_v3_chronology_lock(preregistration_path) as locked_preregistration:
        receipt = _build_receipt(
            preregistration_path=preregistration_path,
            evaluation_root=evaluation_root,
            workspace_root=workspace_root,
            receipt_time=receipt_time,
        )

        def recheck_before_publication() -> None:
            _assert_path_matches_opened(
                preregistration_path,
                locked_preregistration,
                label="fresh v3 preregistration",
            )
            rechecked_receipt = _build_receipt(
                preregistration_path=preregistration_path,
                evaluation_root=evaluation_root,
                workspace_root=workspace_root,
                receipt_time=receipt_time,
            )
            if canonical_json_bytes(rechecked_receipt) != canonical_json_bytes(receipt):
                raise ValueError(
                    "fresh v3 authoring inputs changed during receipt freeze"
                )
            _require_receipt_future_absent(evaluation_root, workspace_root)
            _protected_state(workspace_root)
            _assert_path_matches_opened(
                preregistration_path,
                locked_preregistration,
                label="fresh v3 preregistration",
            )

        recheck_before_publication()
        _write_receipt_no_clobber(
            receipt_path,
            receipt,
            before_publish=recheck_before_publication,
        )
    return receipt.model_dump(mode="json")


def validate_fresh_v3_authoring_receipt(
    preregistration_path: Path,
    evaluation_root: Path,
    workspace_root: Path,
) -> dict[str, Any]:
    preregistration_path = _absolute_lexical_path(preregistration_path)
    evaluation_root = _absolute_lexical_path(evaluation_root)
    workspace_root = _absolute_lexical_path(workspace_root)
    receipt_path = preregistration_path.parent / RECEIPT_NAME
    existing_receipt = _read_existing_receipt(receipt_path)
    if existing_receipt is None:
        raise FileNotFoundError(f"fresh v3 authoring receipt missing: {receipt_path}")
    receipt_bytes, opened_receipt = existing_receipt
    actual = FreshV3AuthoringReceipt.model_validate(json.loads(receipt_bytes))
    if receipt_bytes != canonical_json_bytes(actual):
        raise ValueError("fresh v3 authoring receipt must use canonical JSON bytes")
    expected = _build_receipt(
        preregistration_path=preregistration_path,
        evaluation_root=evaluation_root,
        workspace_root=workspace_root,
        receipt_time=actual.receipt_time,
    )
    if actual != expected:
        raise ValueError("fresh v3 authoring receipt drift")
    _assert_path_matches_opened(
        receipt_path,
        opened_receipt,
        label="fresh v3 authoring receipt",
    )
    return {
        "status": "valid",
        "active_receipt": RECEIPT_NAME,
        "l1_case_count": actual.l1_case_count,
        "l2_case_count": actual.l2_case_count,
        "evaluation_root_absent": True,
        "materialization_implementation_absent": True,
        "hidden_artifacts_created": False,
        "model_request_count": actual.model_request_count,
        "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
    }
