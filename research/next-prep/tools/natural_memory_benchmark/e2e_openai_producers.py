from __future__ import annotations

import hashlib
import json
import re
import socket
from typing import Any, Callable, Literal, Sequence
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .authoritative_memory import canonical_sha256
from .e2e_pipeline import (
    AdmittedL1Record,
    ProposedL1CandidateV1,
    ProposedL2CandidateV1,
    RawTurnV1,
    TurnExtractionInputV1,
)
from .l1_ontology_linking import OntologyRegistry
from .query_compiler_v2 import model_message_text
from .typed_extractor_l1 import (
    L1Kind,
    TypedDerivationProvenance,
    TypedEvidenceBinding,
    TypedL1Candidate,
    TypedLifecycleBinding,
    TypedLocalEntity,
    TypedModality,
    TypedOperationProvenance,
    TypedPolarity,
    TypedPredicate,
    TypedRoleBinding,
    TypedTimeBinding,
)
from .typed_extractor_l2 import (
    ClosurePattern,
    L2AbstractionMethod,
    L2Kind,
    TypedL2Abstraction,
    TypedL2Candidate,
    TypedL2Closure,
    TypedL2StructuredClaim,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


TimeFieldPolicy = Literal["required", "optional", "forbidden"]


class OperatorKindBindingV1(StrictModel):
    canonical_operator: str = Field(min_length=1)
    kind: L1Kind


class OperatorRoleDisplayBindingV1(StrictModel):
    canonical_operator: str = Field(min_length=1)
    machine_role: str = Field(min_length=1)
    display_role: str = Field(min_length=1)


class ModalityTimePolicyV1(StrictModel):
    modality: TypedModality
    event_time_policy: TimeFieldPolicy
    valid_time_policy: TimeFieldPolicy


class OperatorEvidenceCueV1(StrictModel):
    canonical_operator: str = Field(min_length=1)
    cues: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_cues(self) -> "OperatorEvidenceCueV1":
        normalized = [item.casefold().strip() for item in self.cues]
        if any(not item for item in normalized) or len(normalized) != len(
            set(normalized)
        ):
            raise ValueError("operator evidence cues must be non-empty and unique")
        return self


class L2OperatorPolicyV1(StrictModel):
    canonical_operator: str = Field(min_length=1)
    kind: L2Kind
    role_bindings: list[OperatorRoleDisplayBindingV1] = Field(min_length=1)
    allowed_abstraction_methods: list[L2AbstractionMethod] = Field(min_length=1)
    allowed_closure_patterns: list[ClosurePattern] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_values(self) -> "L2OperatorPolicyV1":
        roles = [
            (item.canonical_operator, item.machine_role)
            for item in self.role_bindings
        ]
        if any(item.canonical_operator != self.canonical_operator for item in self.role_bindings):
            raise ValueError("L2 role binding operator mismatch")
        if len(roles) != len(set(roles)):
            raise ValueError("duplicate L2 role binding")
        if len(self.allowed_abstraction_methods) != len(
            set(self.allowed_abstraction_methods)
        ):
            raise ValueError("duplicate L2 abstraction method")
        if len(self.allowed_closure_patterns) != len(
            set(self.allowed_closure_patterns)
        ):
            raise ValueError("duplicate L2 closure pattern")
        return self


class ProductionExtractionPolicyV1(StrictModel):
    schema_version: Literal["production-extraction-policy-v1"] = (
        "production-extraction-policy-v1"
    )
    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    l1_operator_kind_bindings: list[OperatorKindBindingV1] = Field(min_length=1)
    l1_role_display_bindings: list[OperatorRoleDisplayBindingV1] = Field(
        min_length=1
    )
    operator_evidence_cues: list[OperatorEvidenceCueV1] = Field(min_length=1)
    allowed_polarities: list[TypedPolarity] = Field(min_length=1)
    modality_time_policies: list[ModalityTimePolicyV1] = Field(min_length=1)
    l2_operator_policies: list[L2OperatorPolicyV1] = Field(min_length=1)
    source_status: Literal["user_reported"] = "user_reported"
    entity_scope: Literal["category_only"] = "category_only"
    write_action: Literal["create"] = "create"
    lifecycle: Literal["active"] = "active"
    identity_write_allowed: Literal[False] = False

    @model_validator(mode="after")
    def validate_unique_bindings(self) -> "ProductionExtractionPolicyV1":
        operators = [item.canonical_operator for item in self.l1_operator_kind_bindings]
        if len(operators) != len(set(operators)):
            raise ValueError("duplicate L1 operator kind binding")
        roles = [
            (item.canonical_operator, item.machine_role)
            for item in self.l1_role_display_bindings
        ]
        if len(roles) != len(set(roles)):
            raise ValueError("duplicate L1 role display binding")
        cue_operators = [item.canonical_operator for item in self.operator_evidence_cues]
        if len(cue_operators) != len(set(cue_operators)):
            raise ValueError("duplicate operator evidence cue binding")
        if len(self.allowed_polarities) != len(set(self.allowed_polarities)):
            raise ValueError("duplicate allowed polarity")
        modalities = [item.modality for item in self.modality_time_policies]
        if len(modalities) != len(set(modalities)):
            raise ValueError("duplicate modality time policy")
        l2_operators = [item.canonical_operator for item in self.l2_operator_policies]
        if len(l2_operators) != len(set(l2_operators)):
            raise ValueError("duplicate L2 operator policy")
        return self


def validate_production_policy(
    registry: OntologyRegistry,
    policy: ProductionExtractionPolicyV1,
) -> None:
    registry_operators = {
        item.canonical_operator for item in registry.predicate_role_constraints
    }
    policy_operators = {
        item.canonical_operator for item in policy.l1_operator_kind_bindings
    }
    if policy_operators != registry_operators:
        raise ValueError("L1 operator kind coverage does not match registry")

    registry_roles = {
        (item.canonical_operator, item.role_name)
        for item in registry.predicate_role_constraints
    }
    policy_roles = {
        (item.canonical_operator, item.machine_role)
        for item in policy.l1_role_display_bindings
    }
    if policy_roles != registry_roles:
        raise ValueError("L1 role display coverage does not match registry")

    cue_operators = {
        item.canonical_operator for item in policy.operator_evidence_cues
    }
    if cue_operators != registry_operators:
        raise ValueError("operator evidence cue coverage does not match registry")

    if not policy.modality_time_policies:
        raise ValueError("modality time policy is empty")
    l2_by_operator = {
        item.canonical_operator: item for item in policy.l2_operator_policies
    }
    for operator, l2_policy in l2_by_operator.items():
        if operator not in registry_operators:
            raise ValueError("L2 operator is absent from registry")
        expected_roles = {
            role
            for candidate_operator, role in registry_roles
            if candidate_operator == operator
        }
        actual_roles = {item.machine_role for item in l2_policy.role_bindings}
        if actual_roles != expected_roles:
            raise ValueError("L2 role coverage does not match registry")


class ExtractionProfileIdentityV1(StrictModel):
    """Which extraction profile a run used, in a form drift cannot hide from.

    A qualification result only carries over to a run using the same profile.
    The measured vocabularies of the qualification and operational chains do not
    intersect at either layer, so sharing a prompt, producer and runner removes
    engineering duplication without making one chain's qualification stand for
    the other's. Binding the identity makes that mismatch a checkable fact
    instead of something a reader has to notice.

    L1 and L2 vocabularies are recorded separately. The two layers are not
    supposed to share operators — L1 states atomic facts and L2 states
    cross-turn abstractions — so folding them into one hash would make a
    cross-layer difference indistinguishable from same-layer drift. The L2 side
    records sense, abstraction method and closure pattern as well as operator,
    because each of those changes what L2 may mean; recording only the operator
    would let the L2 contract change under an unchanged hash.

    The hash self-verifies, so editing a field cannot produce a profile that
    still looks legitimate.
    """

    schema_version: Literal["extraction-profile-identity-v1"] = (
        "extraction-profile-identity-v1"
    )
    profile_id: str = Field(min_length=1)
    #: 自称 diagnostic 而不是 production：3 个 L1 算子和 1 个 L2 算子是受控运行
    #: 诊断范围，把它读成一般生产能力会高估已验证的东西。`unbound_legacy` 用于
    #: 没有 profile 的历史 snapshot，它不得参与任何资格迁移。
    scope: Literal["diagnostic", "production", "unbound_legacy"]
    l1_operator_senses: tuple[tuple[str, str], ...] = Field(default_factory=tuple)
    l2_operator_senses: tuple[tuple[str, str], ...] = Field(default_factory=tuple)
    l2_abstraction_methods: tuple[str, ...] = Field(default_factory=tuple)
    l2_closure_patterns: tuple[str, ...] = Field(default_factory=tuple)
    l1_vocabulary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    l2_vocabulary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    ontology_registry_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    def hash_body(self) -> dict[str, object]:
        """The exact payload the profile hash covers.

        The L1 vocabulary hash is part of the body, so an L1 change moves the
        overall profile hash even when only L2 is being compared.
        """
        return {
            "profile_id": self.profile_id,
            "scope": self.scope,
            "l1_vocabulary_sha256": self.l1_vocabulary_sha256,
            "l2_vocabulary_sha256": self.l2_vocabulary_sha256,
            "ontology_registry_sha256": self.ontology_registry_sha256,
            "policy_sha256": self.policy_sha256,
        }

    @model_validator(mode="after")
    def validate_profile_hash(self) -> "ExtractionProfileIdentityV1":
        for name in (
            "l1_operator_senses",
            "l2_operator_senses",
            "l2_abstraction_methods",
            "l2_closure_patterns",
        ):
            listed = list(getattr(self, name))
            if listed != sorted(set(listed)):
                raise ValueError(f"{name} must be sorted and deduplicated")
        if self.profile_sha256 != canonical_sha256(self.hash_body()):
            raise ValueError("extraction profile hash mismatch")
        return self


def build_extraction_profile_identity(
    *,
    registry: OntologyRegistry,
    policy: ProductionExtractionPolicyV1,
    profile_id: str = "operational-diagnostic-profile-v1",
    scope: Literal["diagnostic", "production"] = "diagnostic",
    validate_policy: bool = True,
) -> ExtractionProfileIdentityV1:
    """Derive the profile identity from the registry and policy actually used.

    ``validate_policy`` exists so a deliberately shifted vocabulary can be
    hashed in a test without the registry/policy coverage invariant refusing it
    first. Real callers leave it on.
    """
    if validate_policy:
        validate_production_policy(registry, policy)
    l1_operators = {
        item.canonical_operator for item in policy.l1_operator_kind_bindings
    }
    l1_operator_senses = tuple(
        sorted(
            {
                (item.canonical_operator, item.predicate_sense)
                for item in registry.predicate_role_constraints
                if item.canonical_operator in l1_operators
            }
        )
    )
    l2_operators = {
        item.canonical_operator for item in policy.l2_operator_policies
    }
    # L2 的语义空间由 operator、sense、抽象方法与闭包模式共同决定，四者都进哈希。
    l2_operator_senses = tuple(
        sorted(
            {
                (item.canonical_operator, item.predicate_sense)
                for item in registry.predicate_role_constraints
                if item.canonical_operator in l2_operators
            }
        )
    )
    l2_abstraction_methods = tuple(
        sorted(
            {
                method
                for item in policy.l2_operator_policies
                for method in item.allowed_abstraction_methods
            }
        )
    )
    l2_closure_patterns = tuple(
        sorted(
            {
                pattern
                for item in policy.l2_operator_policies
                for pattern in item.allowed_closure_patterns
            }
        )
    )
    l1_vocabulary_sha256 = canonical_sha256(
        {"l1_operator_senses": [list(item) for item in l1_operator_senses]}
    )
    l2_vocabulary_sha256 = canonical_sha256(
        {
            "l2_operator_senses": [list(item) for item in l2_operator_senses],
            "l2_abstraction_methods": list(l2_abstraction_methods),
            "l2_closure_patterns": list(l2_closure_patterns),
        }
    )
    policy_sha256 = canonical_sha256(policy.model_dump(mode="json"))
    body = {
        "profile_id": profile_id,
        "scope": scope,
        "l1_vocabulary_sha256": l1_vocabulary_sha256,
        "l2_vocabulary_sha256": l2_vocabulary_sha256,
        "ontology_registry_sha256": registry.registry_hash,
        "policy_sha256": policy_sha256,
    }
    return ExtractionProfileIdentityV1(
        **body,
        l1_operator_senses=l1_operator_senses,
        l2_operator_senses=l2_operator_senses,
        l2_abstraction_methods=l2_abstraction_methods,
        l2_closure_patterns=l2_closure_patterns,
        profile_sha256=canonical_sha256(body),
    )


def build_producer_contract_identity(
    *,
    registry: OntologyRegistry,
    policy: ProductionExtractionPolicyV1,
    chain: Literal["production", "phase_c_qualification"],
    prompt_override: str | None = None,
) -> dict[str, str]:
    """Identify the whole producer contract, not just the vocabulary.

    ``profile_sha256`` covers the vocabulary, registry and policy. It does not
    cover the prompt, the response schema, the producer or the materializer — so
    two chains can share a profile hash while asking the model for different
    things. That is exactly the situation between Phase C and the production path:
    the qualification runner asks for a complete typed candidate, while production
    asks for semantic slots and materializes the rest itself.

    Recording those dimensions makes the difference a checkable fact instead of
    something a reader has to notice, and stops a profile hash from standing in for
    a claim it cannot support.
    """
    import inspect

    if chain == "production":
        producer_source = inspect.getsource(OpenAICompatibleL1BatchProducer)
        materializer_source = inspect.getsource(materialize_typed_l1_candidate)
        response_schema = ProductionL1SlotBatchResponseV1.model_json_schema()
        prompt = prompt_override
        if prompt is None:
            prompt = inspect.getsource(
                OpenAICompatibleL1BatchProducer.produce
            )
    else:
        from .operational_profile_fresh_runner import build_l1_system_prompt

        producer_source = "operational_profile_fresh_runner.run_layer"
        # 资格链要求模型直接返回完整 typed candidate，程序不做物化。
        materializer_source = "none: the model returns a complete typed candidate"
        response_schema = {"contract": "typed-extractor-l1-proposals-v1"}
        prompt = prompt_override or build_l1_system_prompt(
            registry=registry, policy=policy
        )

    body = {
        "chain": chain,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "response_schema_sha256": canonical_sha256(response_schema),
        "producer_sha256": hashlib.sha256(
            producer_source.encode("utf-8")
        ).hexdigest(),
        "materializer_sha256": hashlib.sha256(
            materializer_source.encode("utf-8")
        ).hexdigest(),
        "policy_sha256": canonical_sha256(policy.model_dump(mode="json")),
        "ontology_registry_sha256": registry.registry_hash,
    }
    return {**body, "producer_contract_sha256": canonical_sha256(body)}


def assert_producer_contract_transferable(
    *,
    qualified_contract: dict[str, str],
    execution_contract: dict[str, str],
) -> None:
    """Refuse to carry a qualification across differing producer contracts.

    Fails closed on the contract hash rather than the profile hash. A qualification
    earned by asking the model for one thing does not describe a run that asks for
    another, even when the vocabulary is identical.
    """
    if qualified_contract["producer_contract_sha256"] != (
        execution_contract["producer_contract_sha256"]
    ):
        raise ValueError(
            "qualified producer contract does not match the executed contract"
        )


def _unbound_legacy_profile() -> ExtractionProfileIdentityV1:
    """The explicit identity of a snapshot written before profiles existed.

    Naming the absence is safer than leaving it null: a missing profile would
    otherwise be compared as if it happened to match, and a legacy v8 snapshot
    would silently inherit a qualification it was never measured against.
    """
    empty = canonical_sha256({})
    body = {
        "profile_id": "unbound_legacy",
        "scope": "unbound_legacy",
        "l1_vocabulary_sha256": empty,
        "l2_vocabulary_sha256": empty,
        "ontology_registry_sha256": empty,
        "policy_sha256": empty,
    }
    return ExtractionProfileIdentityV1(
        **body, profile_sha256=canonical_sha256(body)
    )


UNBOUND_LEGACY_PROFILE = _unbound_legacy_profile()


def assert_qualification_transferable(
    *,
    qualified_profile: ExtractionProfileIdentityV1,
    execution_profile: ExtractionProfileIdentityV1,
) -> None:
    """Refuse to carry a qualification across differing profiles.

    Fail closed on identity rather than on vocabulary overlap: partial overlap
    would still leave part of the executed vocabulary unqualified, and treating
    that as covered is exactly the inference this guard exists to prevent.

    An unbound legacy profile never carries a qualification in either direction.
    It records that a snapshot predates profiles, which is the opposite of
    evidence that it was measured.
    """
    for label, profile in (
        ("qualified", qualified_profile),
        ("executed", execution_profile),
    ):
        if profile.scope == "unbound_legacy":
            raise ValueError(
                f"{label} profile is unbound legacy and cannot transfer "
                "qualification"
            )
        if profile.profile_sha256 != canonical_sha256(profile.hash_body()):
            raise ValueError(f"{label} profile hash does not verify")
    if qualified_profile.profile_id != execution_profile.profile_id:
        raise ValueError(
            "qualification profile id does not match the executed profile"
        )
    if qualified_profile.profile_sha256 != execution_profile.profile_sha256:
        raise ValueError(
            "qualification profile hash does not match the executed profile"
        )


def _qualification_profile_vocabularies() -> tuple[
    tuple[tuple[str, str], ...], tuple[str, ...]
]:
    """Read the fresh-v3 qualification vocabulary from its own blueprints.

    Derived rather than restated, so this cannot drift away from the chain it
    describes and quietly report an overlap that no longer holds.
    """
    from .typed_extractor_fresh_v3_authoring import (
        _L1_BLUEPRINTS,
        _L2_BLUEPRINTS,
    )

    l1 = tuple(
        sorted(
            {
                (item.vocabulary_operator, item.vocabulary_sense)
                for item in _L1_BLUEPRINTS
            }
        )
    )
    l2 = tuple(
        sorted({item.vocabulary_operator for item in _L2_BLUEPRINTS})
    )
    return l1, l2


(
    QUALIFICATION_PROFILE_L1_OPERATOR_SENSES,
    QUALIFICATION_PROFILE_L2_OPERATORS,
) = _qualification_profile_vocabularies()


def build_diagnostic_production_policy(
    registry: OntologyRegistry,
) -> ProductionExtractionPolicyV1:
    policy = ProductionExtractionPolicyV1(
        policy_id="e2e-diagnostic-category-write",
        policy_version="1",
        l1_operator_kind_bindings=[
            OperatorKindBindingV1(canonical_operator="prefer", kind="preference"),
            OperatorKindBindingV1(canonical_operator="drink", kind="event"),
            OperatorKindBindingV1(canonical_operator="add_ingredient", kind="event"),
        ],
        l1_role_display_bindings=[
            OperatorRoleDisplayBindingV1(
                canonical_operator="prefer",
                machine_role="theme",
                display_role="theme",
            ),
            OperatorRoleDisplayBindingV1(
                canonical_operator="drink",
                machine_role="theme",
                display_role="theme",
            ),
            OperatorRoleDisplayBindingV1(
                canonical_operator="add_ingredient",
                machine_role="theme",
                display_role="theme",
            ),
            OperatorRoleDisplayBindingV1(
                canonical_operator="add_ingredient",
                machine_role="destination",
                display_role="destination",
            ),
        ],
        operator_evidence_cues=[
            OperatorEvidenceCueV1(
                canonical_operator="prefer",
                cues=["prefer", "preferred", "preference"],
            ),
            OperatorEvidenceCueV1(
                canonical_operator="drink",
                cues=["drink", "drank", "drunk"],
            ),
            OperatorEvidenceCueV1(
                canonical_operator="add_ingredient",
                cues=["add", "added"],
            ),
        ],
        # 一条被否定的事实与一条不存在的事实是两回事，前者应当被记住。极性两
        # 个方向都要接受 grounding 检查，所以放开这里不等于放松校验。
        allowed_polarities=["positive", "negative"],
        modality_time_policies=[
            # 一条事实何时开始成立是它内容的一部分，所以 valid_time 可选。
            # event_time 仍然禁止：一个偏好不是发生在某一刻的事件，允许它会把
            # 两种不同的时间语义混为一谈。
            ModalityTimePolicyV1(
                modality="actual",
                event_time_policy="forbidden",
                valid_time_policy="optional",
            )
        ],
        l2_operator_policies=[
            L2OperatorPolicyV1(
                canonical_operator="prefer",
                kind="preference_profile",
                role_bindings=[
                    OperatorRoleDisplayBindingV1(
                        canonical_operator="prefer",
                        machine_role="theme",
                        display_role="theme",
                    )
                ],
                allowed_abstraction_methods=["preference_aggregation"],
                allowed_closure_patterns=["multi_evidence_set"],
            )
        ],
    )
    validate_production_policy(registry, policy)
    return policy


class ModelBoundaryError(RuntimeError):
    """Credential-safe terminal error at an OpenAI-compatible boundary."""


class ModelCallHashV1(StrictModel):
    stage: Literal["l1", "l2", "query"]
    requested_model: str = Field(min_length=1)
    response_model: str = Field(min_length=1)
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempts: int = Field(ge=1, le=2)


_CONTRACT_VALIDATION_CODES = {
    "candidate modality is not authorized": "modality_not_authorized",
    "candidate is missing required time": "required_time_missing",
    "candidate contains forbidden time": "forbidden_time",
    "L1 candidate ref does not match allocated ref": "candidate_ref_mismatch",
    "operational E2E requires emit_l1 for every turn": "emission_required",
    "L1 role slot offset does not quote the user's own words": (
        "role_slot_offset_mismatch"
    ),
    "L1 role is not published for this operator": "role_not_published",
    "L1 predicate tuple is not public": "predicate_not_public",
    "L1 kind does not match operator policy": "kind_policy_mismatch",
    "L1 local entity surface is not grounded in user evidence": (
        "local_entity_not_grounded"
    ),
    "L1 operator has no public cue in user evidence": "operator_cue_missing",
    "L1 operator cue is explicitly negated in user evidence": (
        "operator_cue_negated"
    ),
    "L1 polarity is not authorized": "polarity_not_authorized",
    "L1 polarity is not grounded in user evidence": "polarity_not_grounded",
    "L1 modality is not grounded in user evidence": "modality_not_grounded",
    "L2 polarity is not authorized": "polarity_not_authorized",
    "L1 role coverage does not match predicate contract": "role_coverage_mismatch",
    "L1 role display does not match policy": "role_display_mismatch",
    "L1 evidence binding does not match public turn": "evidence_binding_mismatch",
    "L1 derivation is not exact explicit evidence": "derivation_mismatch",
    "L1 lifecycle is outside create-active policy": "lifecycle_policy_mismatch",
    "L1 supersession target is the turn itself": "supersession_self_reference",
    "L1 supersession target is not a known turn": "supersession_target_unknown",
    "L1 proposal contains unsupported production bindings": "unsupported_bindings",
    "L2 support order or coverage mismatch": "support_coverage_mismatch",
    "L2 required closure mismatch": "required_closure_mismatch",
    "L2 optional support is not allowed": "optional_support_not_allowed",
    "L2 turn closure mismatch": "turn_closure_mismatch",
    "L2 session closure mismatch": "session_closure_mismatch",
    "L2 evidence closure mismatch": "evidence_closure_mismatch",
    "production L2 requires one structured claim": "structured_claim_count",
    "L2 claim support closure mismatch": "claim_support_closure_mismatch",
    "L2 operator kind is not public": "operator_kind_not_public",
    "L2 predicate tuple is not public": "predicate_not_public",
    "L2 claim predicate lacks admitted L1 semantic support": (
        "claim_predicate_without_support"
    ),
    "L2 role coverage mismatch": "role_coverage_mismatch",
    "L2 role display mismatch": "role_display_mismatch",
    "L2 claim roles or entities lack admitted L1 support": (
        "claim_roles_without_support"
    ),
    "L2 claim entity surface is absent from summary": "summary_entity_missing",
    "L2 summary lacks the selected operator evidence cue": (
        "summary_operator_cue_missing"
    ),
    "L2 summary explicitly negates the selected operator cue": (
        "summary_operator_cue_negated"
    ),
    "L2 abstraction method is not public": "abstraction_method_not_public",
    "L2 closure pattern is not public": "closure_pattern_not_public",
    "L2 operator is not published by policy": "operator_kind_not_public",
    "L2 kind does not match operator policy": "operator_kind_not_public",
    "L2 abstraction method is not authorized": "abstraction_method_not_public",
    "L2 policy must publish exactly one closure pattern": (
        "closure_pattern_not_public"
    ),
    "L2 role surface is not present in any L1 support": (
        "claim_roles_without_support"
    ),
    "L2 role is not published for this operator": "role_not_published",
    "L2 materialization requires admitted L1 support": (
        "support_coverage_mismatch"
    ),
}


def _safe_schema_error(exc: ValidationError) -> tuple[str, str]:
    errors = exc.errors(
        include_url=False,
        include_context=False,
        include_input=False,
    )
    if not errors:
        return "root", "unknown"
    error = errors[0]
    error_type = str(error.get("type", "unknown"))
    if not error_type.isascii() or not error_type.replace("_", "").isalnum():
        error_type = "unknown"
    location = error.get("loc", ())
    safe_parts: list[str] = []
    for index, part in enumerate(location):
        if isinstance(part, int):
            safe_parts.append(str(part))
        elif error_type == "extra_forbidden" and index == len(location) - 1:
            safe_parts.append("extra")
        elif (
            isinstance(part, str)
            and part.isascii()
            and len(part) <= 64
            and all(character.isalnum() or character == "_" for character in part)
        ):
            safe_parts.append(part)
        else:
            safe_parts.append("field")
    return ".".join(safe_parts) or "root", error_type


def _contract_validation_code(exc: Exception) -> str:
    return _CONTRACT_VALIDATION_CODES.get(
        str(exc),
        "internal_validation_error",
    )


def _has_explicit_negation(text: str) -> bool:
    tokens = re.findall(r"[a-z]+(?:'[a-z]+)?", text.casefold())
    negations = {
        "no",
        "not",
        "never",
        "neither",
        "nor",
        "nobody",
        "none",
        "nothing",
        "nowhere",
    }
    return any(token in negations or token.endswith("n't") for token in tokens)


#: 引出条件从句的标记。一个事实若被这样的从句限定，它尚未成立，因此不能以
#: actual 落库。
_CONDITIONAL_MARKERS = (
    "if",
    "unless",
    "provided",
    "providing",
    "assuming",
    "should",
    "when",
    "whenever",
    "once",
    "in case",
    "as long as",
    "so long as",
    "supposing",
)

#: 这些后续词表明条件词并不作用于所陈述的事实本身，而是附带说明。
#: 例如 "Coffee is preferred, if that matters" 里的偏好本身是无条件的。
_INCIDENTAL_CONDITIONAL_TAILS = (
    "that matters",
    "you were wondering",
    "you are wondering",
    "that helps",
    "i may say so",
    "you like",
    "you prefer",
    "anything",
)


def _conditions_the_claim(text: str) -> bool:
    """Say whether a conditional clause governs the stated fact.

    A guarded fact has not happened, so recording it as actual asserts an
    occurrence the text does not. Written as evidence grounding rather than a
    lookup for one sentence: the marker has to appear as a clause boundary, and
    an aside like "if that matters" leaves the fact itself unconditional, so
    treating every conditional word as disqualifying would manufacture false
    refusals.
    """
    lowered = text.casefold()
    for marker in _CONDITIONAL_MARKERS:
        for match in re.finditer(rf"(?<![a-z]){re.escape(marker)}(?![a-z])", lowered):
            tail = lowered[match.end() :].lstrip(" ,")
            if any(tail.startswith(item) for item in _INCIDENTAL_CONDITIONAL_TAILS):
                continue
            # 从句必须真的引出一个子句，而不是句末孤立的词。
            if tail:
                return True
    return False


class _OpenAICompatibleJSONClient:
    def __init__(
        self,
        *,
        stage: Literal["l1", "l2"],
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int,
        max_tokens: int,
        max_attempts: int,
        opener: Callable[..., Any],
    ) -> None:
        if not base_url.strip() or not api_key or not model.strip():
            raise ValueError("model endpoint, credential, and model are required")
        if timeout_seconds <= 0 or max_tokens <= 0:
            raise ValueError("model timeout and max tokens must be positive")
        if max_attempts not in {1, 2}:
            raise ValueError("model attempts must be one or two")
        self.stage = stage
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.max_attempts = max_attempts
        self._opener = opener
        self.last_call: ModelCallHashV1 | None = None

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        if isinstance(exc, (TimeoutError, socket.timeout)):
            return True
        return isinstance(exc, HTTPError) and exc.code in {
            408,
            429,
            500,
            502,
            503,
            504,
        }

    def request(self, *, system_prompt: str, public_input: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        public_input,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                },
            ],
            "temperature": 0,
            "max_tokens": self.max_tokens,
        }
        request_bytes = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode(
            "utf-8"
        )
        request = Request(
            f"{self.base_url}/chat/completions",
            data=request_bytes,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        for attempt in range(1, self.max_attempts + 1):
            request_phase: Literal["open", "read"] = "open"
            try:
                with self._opener(request, timeout=self.timeout_seconds) as response:
                    response_status = getattr(response, "status", None)
                    request_phase = "read"
                    raw = response.read()
            except Exception as exc:
                if self._retryable(exc) and attempt < self.max_attempts:
                    continue
                if isinstance(exc, HTTPError):
                    try:
                        error_body = exc.read()
                        response_sha256 = hashlib.sha256(error_body).hexdigest()
                    except OSError:
                        response_sha256 = "unavailable"
                    raise ModelBoundaryError(
                        f"{self.stage} model request failed after {attempt} "
                        f"attempt(s): reason=http_error; http_status={exc.code}; "
                        f"response_sha256={response_sha256}; "
                        f"request_phase={request_phase}; "
                        f"exception_type={type(exc).__name__}"
                    ) from None
                if isinstance(exc, (TimeoutError, socket.timeout)):
                    reason = "request_timeout"
                else:
                    reason = "request_exception"
                raise ModelBoundaryError(
                    f"{self.stage} model request failed after {attempt} "
                    f"attempt(s): reason={reason}; http_status=unavailable; "
                    "response_sha256=unavailable; "
                    f"request_phase={request_phase}; "
                    f"exception_type={type(exc).__name__}"
                ) from None

            response_sha256 = hashlib.sha256(raw).hexdigest()
            status_text = (
                str(response_status)
                if isinstance(response_status, int)
                else "unavailable"
            )

            def invalid_response(reason: str) -> ModelBoundaryError:
                return ModelBoundaryError(
                    f"{self.stage} model response was invalid: "
                    f"reason={reason}; http_status={status_text}; "
                    f"response_sha256={response_sha256}"
                )

            try:
                envelope = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise invalid_response("envelope_json") from None
            if not isinstance(envelope, dict):
                raise invalid_response("envelope_shape")
            response_model = envelope.get("model")
            if not isinstance(response_model, str) or not response_model.strip():
                raise invalid_response("response_model")
            choices = envelope.get("choices")
            if (
                not isinstance(choices, list)
                or len(choices) != 1
                or not isinstance(choices[0], dict)
            ):
                raise invalid_response("choices")
            message = choices[0].get("message")
            try:
                content = model_message_text(message)
            except TypeError:
                raise invalid_response("content") from None
            try:
                result = json.loads(content)
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise invalid_response("content_json") from None
            if not isinstance(result, dict):
                raise invalid_response("content_shape")
            self.last_call = ModelCallHashV1(
                stage=self.stage,
                requested_model=self.model,
                response_model=response_model,
                request_sha256=hashlib.sha256(request_bytes).hexdigest(),
                response_sha256=response_sha256,
                attempts=attempt,
            )
            return result
        raise AssertionError("unreachable model retry state")


def allocate_support_ref(turn_id: str) -> str:
    return f"support-{hashlib.sha256(turn_id.encode('utf-8')).hexdigest()[:16]}"


class L1RoleSlotV1(StrictModel):
    """One semantic role filled by a span of the user's own words."""

    role: str = Field(min_length=1)
    surface: str = Field(min_length=1)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_span(self) -> "L1RoleSlotV1":
        if self.char_end <= self.char_start:
            raise ValueError("role slot span must be non-empty")
        if self.char_end - self.char_start != len(self.surface):
            raise ValueError("role slot span length does not match its surface")
        return self


class L1SemanticSlotProposalV1(StrictModel):
    """The semantic judgement for one candidate, without mechanical structure.

    Identifiers, role wiring, evidence bindings, derivation, lifecycle and
    operation provenance are all derivable from the public turn, so they are
    materialized by the program rather than requested from the model.
    """

    predicate_surface: str = Field(min_length=1)
    predicate_sense: str = Field(min_length=1)
    canonical_operator: str = Field(min_length=1)
    kind: L1Kind
    modality: TypedModality
    polarity: TypedPolarity
    role_slots: list[L1RoleSlotV1] = Field(min_length=1)
    event_time: str | None = None
    valid_time: str | None = None
    #: 这一轮更正了哪几轮的事实。用轮次而非候选 ref 表达：模型看得到轮次，看
    #: 不到 ref 的分配规则，换算由程序负责。
    supersedes_turn_ids: list[str] = Field(default_factory=list)


def materialize_typed_l1_candidate(
    *,
    slots: L1SemanticSlotProposalV1,
    registry: OntologyRegistry,
    policy: ProductionExtractionPolicyV1,
    user_text: str,
    evidence_id: str,
) -> TypedL1Candidate:
    """Build a typed candidate from a semantic proposal, deterministically.

    Offsets are supplied by the model but verified against the raw text rather
    than re-derived by search, so substring matching stays a validator and the
    decision about what the span is stays with the model.
    """
    predicate_rules = [
        item
        for item in registry.predicate_role_constraints
        if item.predicate_surface == slots.predicate_surface
        and item.predicate_sense == slots.predicate_sense
        and item.canonical_operator == slots.canonical_operator
    ]
    if not predicate_rules:
        raise ValueError("L1 predicate tuple is not public")

    kind_by_operator = {
        item.canonical_operator: item.kind
        for item in policy.l1_operator_kind_bindings
    }
    expected_kind = kind_by_operator.get(slots.canonical_operator)
    if expected_kind is None or expected_kind != slots.kind:
        raise ValueError("L1 kind does not match operator policy")

    display_by_role = {
        item.machine_role: item.display_role
        for item in policy.l1_role_display_bindings
        if item.canonical_operator == slots.canonical_operator
    }

    entity_ids: dict[str, str] = {}
    local_entities: list[TypedLocalEntity] = []
    roles: list[TypedRoleBinding] = []
    for slot in slots.role_slots:
        if user_text[slot.char_start : slot.char_end] != slot.surface:
            raise ValueError(
                "L1 role slot offset does not quote the user's own words"
            )
        display_role = display_by_role.get(slot.role)
        if display_role is None:
            raise ValueError("L1 role is not published for this operator")
        entity_id = entity_ids.get(slot.surface)
        if entity_id is None:
            entity_id = f"entity-{len(local_entities) + 1:02d}"
            entity_ids[slot.surface] = entity_id
            local_entities.append(
                TypedLocalEntity(local_entity_id=entity_id, surface=slot.surface)
            )
        roles.append(
            TypedRoleBinding(
                role=slot.role,
                role_name=display_role,
                local_entity_id=entity_id,
            )
        )

    return TypedL1Candidate(
        kind=slots.kind,
        predicate=TypedPredicate(
            surface=slots.predicate_surface,
            sense=slots.predicate_sense,
            canonical_operator=slots.canonical_operator,
        ),
        local_entities=local_entities,
        roles=roles,
        modality=slots.modality,
        polarity=slots.polarity,
        time=TypedTimeBinding(
            event_time=slots.event_time,
            valid_time=slots.valid_time,
        ),
        condition_bindings=[],
        scope_bindings=[],
        derivation=TypedDerivationProvenance(
            method="explicit",
            basis=None,
            evidence_ids=[evidence_id],
        ),
        evidence_bindings=[
            TypedEvidenceBinding(evidence_id=evidence_id, speaker="user")
        ],
        # 更正本身仍然是一条 active 事实；被它取代的是别人。轮次到候选 ref 的
        # 换算在这里完成，模型不必知道 ref 怎么分配。
        lifecycle=TypedLifecycleBinding(
            lifecycle="active",
            supersedes_candidate_refs=[
                allocate_support_ref(item) for item in slots.supersedes_turn_ids
            ],
        ),
        operation_provenance=TypedOperationProvenance(),
    )


class L2RoleSlotV1(StrictModel):
    """L2 claim 的一个角色，实体来自某条 admitted L1 支撑的表面。"""

    role: str = Field(min_length=1)
    support_entity_surface: str = Field(min_length=1)


class L2AbstractionSlotProposalV1(StrictModel):
    """L2 的语义判断：哪些支撑该合并成什么抽象。

    支撑集、来源轮次/会话、evidence 绑定、closure、lifecycle、claim_ref 以及
    claim 内的局部实体与角色连线都可以从 admitted L1 确定性推导，因此不向模型
    索取。`statement` 是这条抽象的自然语言陈述，程序逐字用作 summary。
    """

    kind: L2Kind
    statement: str = Field(min_length=1)
    predicate_surface: str = Field(min_length=1)
    predicate_sense: str = Field(min_length=1)
    canonical_operator: str = Field(min_length=1)
    abstraction_method: L2AbstractionMethod
    modality: TypedModality
    polarity: TypedPolarity
    role_slots: list[L2RoleSlotV1] = Field(min_length=1)
    event_time: str | None = None
    valid_time: str | None = None


def materialize_typed_l2_candidate(
    *,
    slots: L2AbstractionSlotProposalV1,
    admitted_l1: Sequence[AdmittedL1Record],
    registry: OntologyRegistry,
    policy: ProductionExtractionPolicyV1,
) -> TypedL2Candidate:
    """从一个抽象提案确定性地物化 L2 候选。

    summary 逐字取自 `statement`，不追加标点：fresh-v3 的 gold summary 比公共
    statement 多一个句号，而 scorer 精确比较字符串，所以任何“复制后再加工”都
    会让照做的提案记零分。
    """
    if not admitted_l1:
        raise ValueError("L2 materialization requires admitted L1 support")

    operator_policy = next(
        (
            item
            for item in policy.l2_operator_policies
            if item.canonical_operator == slots.canonical_operator
        ),
        None,
    )
    if operator_policy is None:
        raise ValueError("L2 operator is not published by policy")
    if operator_policy.kind != slots.kind:
        raise ValueError("L2 kind does not match operator policy")
    if slots.abstraction_method not in operator_policy.allowed_abstraction_methods:
        raise ValueError("L2 abstraction method is not authorized")
    if slots.polarity not in policy.allowed_polarities:
        raise ValueError("L2 polarity is not authorized")
    if len(operator_policy.allowed_closure_patterns) != 1:
        raise ValueError("L2 policy must publish exactly one closure pattern")
    closure_pattern = operator_policy.allowed_closure_patterns[0]

    predicate_rules = [
        item
        for item in registry.predicate_role_constraints
        if item.predicate_surface == slots.predicate_surface
        and item.predicate_sense == slots.predicate_sense
        and item.canonical_operator == slots.canonical_operator
    ]
    if not predicate_rules:
        raise ValueError("L2 predicate tuple is not public")

    support_refs = [item.candidate_ref for item in admitted_l1]
    # 大小写不是语义区分，producer 下游的 grounding 检查也全部 casefold 比较，
    # 所以按 casefold 匹配；写入时用支撑自己的拼写，不用模型请求里的拼写。
    support_surfaces = {
        entity.surface.casefold(): entity.surface
        for item in admitted_l1
        for entity in item.linked_candidate.typed_candidate.local_entities
    }
    display_by_role = {
        item.machine_role: item.display_role
        for item in operator_policy.role_bindings
        if item.canonical_operator == slots.canonical_operator
    }

    entity_ids: dict[str, str] = {}
    local_entities: list[TypedLocalEntity] = []
    roles: list[TypedRoleBinding] = []
    for slot in slots.role_slots:
        surface_key = slot.support_entity_surface.casefold()
        support_surface = support_surfaces.get(surface_key)
        if support_surface is None:
            raise ValueError("L2 role surface is not present in any L1 support")
        display_role = display_by_role.get(slot.role)
        if display_role is None:
            raise ValueError("L2 role is not published for this operator")
        entity_id = entity_ids.get(surface_key)
        if entity_id is None:
            entity_id = f"entity-{len(local_entities) + 1:02d}"
            entity_ids[surface_key] = entity_id
            local_entities.append(
                TypedLocalEntity(
                    local_entity_id=entity_id,
                    surface=support_surface,
                )
            )
        roles.append(
            TypedRoleBinding(
                role=slot.role,
                role_name=display_role,
                local_entity_id=entity_id,
            )
        )

    evidence_bindings = [
        TypedEvidenceBinding(evidence_id=evidence_id, speaker="user")
        for evidence_id in sorted(
            {
                span.evidence_id
                for item in admitted_l1
                for span in item.revision.payload.source.evidence_spans
            }
        )
    ]
    return TypedL2Candidate(
        kind=slots.kind,
        summary=slots.statement,
        supporting_l1_refs=support_refs,
        structured_claims=[
            TypedL2StructuredClaim(
                claim_ref="claim-01",
                predicate=TypedPredicate(
                    surface=slots.predicate_surface,
                    sense=slots.predicate_sense,
                    canonical_operator=slots.canonical_operator,
                ),
                local_entities=local_entities,
                roles=roles,
                modality=slots.modality,
                polarity=slots.polarity,
                time=TypedTimeBinding(
                    event_time=slots.event_time,
                    valid_time=slots.valid_time,
                ),
                supporting_l1_refs=support_refs,
            )
        ],
        abstraction=TypedL2Abstraction(
            method=slots.abstraction_method,
            basis="Admitted L1 supports jointly establish the abstraction.",
        ),
        closure=TypedL2Closure(
            pattern=closure_pattern,
            required_support_refs=support_refs,
        ),
        # 一轮可以贡献多条 L1，所以按首次出现去重：重复引用会让合法的多事实
        # 输入撞上 producer 自己的 turn 闭包检查。
        source_turn_refs=list(dict.fromkeys(item.turn_id for item in admitted_l1)),
        source_session_refs=list(
            dict.fromkeys(item.session_id for item in admitted_l1)
        ),
        evidence_bindings=evidence_bindings,
    )


def allocate_l2_candidate_ref(support_refs: Sequence[str]) -> str:
    """Allocate L2 identity deterministically from the support it abstracts.

    L2 identity is a function of what the unit abstracts, so the same admitted
    support always yields the same ref and a replay is comparable. Order is
    preserved rather than sorted, because the support order is itself part of
    the closure the pipeline checks.
    """
    if not support_refs:
        raise ValueError("L2 candidate ref requires admitted support")
    seed = "\n".join(support_refs).encode("utf-8")
    return f"l2-{hashlib.sha256(seed).hexdigest()[:16]}"


def allocate_candidate_ref(turn_id: str, ordinal: int) -> str:
    """Allocate candidate identity deterministically, program-side.

    Ordinal 0 keeps the historical single-candidate value, so a turn with one
    memory produces exactly the ref it always did.
    """
    if ordinal < 0:
        raise ValueError("candidate ordinal must not be negative")
    if ordinal == 0:
        return allocate_support_ref(turn_id)
    seed = f"{turn_id}#{ordinal}".encode("utf-8")
    return f"support-{hashlib.sha256(seed).hexdigest()[:16]}"


class ProductionPublicTurnV1(StrictModel):
    session_id: str = Field(min_length=1)
    turn_id: str = Field(min_length=1)
    turn_index: int = Field(ge=0)
    user_text: str = Field(min_length=1)
    assistant_text: str = Field(min_length=1)
    candidate_ref: str = Field(pattern=r"^support-[0-9a-f]{16}$")
    evidence_id: str = Field(min_length=1)
    evidence_speaker: Literal["user"] = "user"
    evidence_quote: str = Field(min_length=1)


class ProductionL1ProposalV1(StrictModel):
    turn_id: str = Field(min_length=1)
    #: Optional because the program allocates candidate identity. A model that
    #: supplies one must still match its allocation, but it is not required to
    #: reproduce an identifier the program already knows.
    candidate_ref: str | None = Field(
        default=None,
        pattern=r"^support-[0-9a-f]{16}$",
    )
    decision: Literal["emit_l1", "abstain", "no_memory"]
    typed_candidate: TypedL1Candidate | None = None

    @model_validator(mode="after")
    def validate_decision_union(self) -> "ProductionL1ProposalV1":
        if self.decision == "emit_l1" and self.typed_candidate is None:
            raise ValueError("emit_l1 requires a typed candidate")
        if self.decision != "emit_l1" and self.typed_candidate is not None:
            raise ValueError("non-emission decision cannot include a typed candidate")
        return self


class ProductionL1SlotProposalV1(StrictModel):
    """One turn's decision, carrying semantics only when it emits."""

    turn_id: str = Field(min_length=1)
    decision: Literal["emit_l1", "abstain", "no_memory"]
    slots: L1SemanticSlotProposalV1 | None = None

    @model_validator(mode="after")
    def validate_decision_union(self) -> "ProductionL1SlotProposalV1":
        if self.decision == "emit_l1" and self.slots is None:
            raise ValueError("emit_l1 requires semantic slots")
        if self.decision != "emit_l1" and self.slots is not None:
            raise ValueError("non-emission decision cannot include slots")
        return self


class ProductionL1SlotBatchResponseV1(StrictModel):
    """The response contract for the semantic-slot L1 proposer."""

    schema_version: Literal["production-l1-slot-batch-response-v1"] = (
        "production-l1-slot-batch-response-v1"
    )
    proposals: list[ProductionL1SlotProposalV1] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_decisions(self) -> "ProductionL1SlotBatchResponseV1":
        non_emitting = {
            item.turn_id for item in self.proposals if item.decision != "emit_l1"
        }
        emitting = {
            item.turn_id for item in self.proposals if item.decision == "emit_l1"
        }
        if non_emitting & emitting:
            raise ValueError(
                "a turn cannot both emit and decline to emit a memory"
            )
        for turn_id in non_emitting:
            if sum(item.turn_id == turn_id for item in self.proposals) != 1:
                raise ValueError("a declining turn carries exactly one decision")
        return self


class ProductionL1BatchResponseV1(StrictModel):
    schema_version: Literal["production-l1-batch-response-v1"] = (
        "production-l1-batch-response-v1"
    )
    proposals: list[ProductionL1ProposalV1] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_candidates(self) -> "ProductionL1BatchResponseV1":
        # A turn may carry several memories, so turn ids repeat legitimately.
        # Candidate identity must still be unique, and a turn that states
        # nothing durable carries exactly one non-emission decision.
        refs = [
            item.candidate_ref
            for item in self.proposals
            if item.candidate_ref is not None
        ]
        if len(refs) != len(set(refs)):
            raise ValueError("duplicate production L1 proposal")
        non_emitting = {
            item.turn_id for item in self.proposals if item.decision != "emit_l1"
        }
        emitting = {
            item.turn_id for item in self.proposals if item.decision == "emit_l1"
        }
        if non_emitting & emitting:
            raise ValueError(
                "a turn cannot both emit and decline to emit a memory"
            )
        for turn_id in non_emitting:
            if sum(item.turn_id == turn_id for item in self.proposals) != 1:
                raise ValueError("a declining turn carries exactly one decision")
        return self


class ProductionL2SlotResponseV1(StrictModel):
    """The response contract for the abstraction-slot L2 proposer.

    `candidate_ref` is allocated by the program from the admitted support, so
    the model neither invents nor restates memory identity.
    """

    schema_version: Literal["production-l2-slot-response-v1"] = (
        "production-l2-slot-response-v1"
    )
    #: L2 也必须能够拒绝作答：没有可靠抽象时产出 abstain 而不是硬造一条。
    decision: Literal["emit_l2", "abstain"] = "emit_l2"
    slots: L2AbstractionSlotProposalV1 | None = None

    @model_validator(mode="after")
    def validate_decision_union(self) -> "ProductionL2SlotResponseV1":
        if self.decision == "emit_l2" and self.slots is None:
            raise ValueError("emit_l2 requires abstraction slots")
        if self.decision == "abstain" and self.slots is not None:
            raise ValueError("abstain cannot include abstraction slots")
        return self


def _validate_time(
    *,
    candidate: TypedL1Candidate,
    policy: ProductionExtractionPolicyV1,
) -> None:
    by_modality = {item.modality: item for item in policy.modality_time_policies}
    time_policy = by_modality.get(candidate.modality)
    if time_policy is None:
        raise ValueError("candidate modality is not authorized")
    for field, rule in (
        (candidate.time.event_time, time_policy.event_time_policy),
        (candidate.time.valid_time, time_policy.valid_time_policy),
    ):
        if rule == "required" and field is None:
            raise ValueError("candidate is missing required time")
        if rule == "forbidden" and field is not None:
            raise ValueError("candidate contains forbidden time")


class BoundL1CandidateProducer:
    """Replays frozen proposals, allowing zero, one, or several per turn."""

    def __init__(self, proposals: Sequence[ProductionL1ProposalV1]) -> None:
        self._by_turn: dict[str, list[ProductionL1ProposalV1]] = {}
        for item in proposals:
            self._by_turn.setdefault(item.turn_id, []).append(item)
        self._consumed: set[str] = set()

    def non_emission_reason(self, turn_id: str) -> str | None:
        """返回该轮的非产出结论，产出记忆的轮次返回 None。

        `abstain` 与 `no_memory` 是两种不同结论：前者表示依据不足以安全落库，
        后者表示这一轮确实没有值得留存的事实。两者都不产出候选，但下游必须
        能够分辨，否则 Phase C 的 abstention 指标无法在 production 重放。
        """
        proposals = self._by_turn.get(turn_id)
        if not proposals:
            return None
        if any(item.decision == "emit_l1" for item in proposals):
            return None
        return proposals[0].decision

    def produce(self, value: TurnExtractionInputV1) -> list[ProposedL1CandidateV1]:
        turn_id = value.turn.turn_id
        proposals = self._by_turn.get(turn_id)
        if proposals is None or turn_id in self._consumed:
            raise ValueError("bound L1 proposal coverage mismatch")
        expected_evidence = f"evidence-{turn_id}-user"
        if value.user_evidence.evidence_id != expected_evidence:
            raise ValueError("runtime evidence allocation changed after L1 proposal")
        self._consumed.add(turn_id)
        emissions = [item for item in proposals if item.decision == "emit_l1"]
        if not emissions:
            # A turn that states nothing durable is a recorded outcome, so the
            # pipeline receives no candidate rather than an error. Which
            # non-emission it was stays available via `non_emission_reason`.
            return []
        candidates: list[ProposedL1CandidateV1] = []
        for ordinal, proposal in enumerate(emissions):
            candidate = proposal.typed_candidate
            if candidate is None:
                raise ValueError("bound L1 emission is missing its candidate")
            candidates.append(
                ProposedL1CandidateV1(
                    candidate_ref=allocate_candidate_ref(turn_id, ordinal),
                    typed_candidate=candidate,
                )
            )
        return candidates


class OpenAICompatibleL1BatchProducer:
    def __init__(
        self,
        *,
        registry: OntologyRegistry,
        policy: ProductionExtractionPolicyV1,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int = 120,
        max_tokens: int = 8192,
        max_attempts: int = 2,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        validate_production_policy(registry, policy)
        self.registry = registry
        self.policy = policy
        self.client = _OpenAICompatibleJSONClient(
            stage="l1",
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
            max_tokens=max_tokens,
            max_attempts=max_attempts,
            opener=opener,
        )

    @property
    def last_call(self) -> ModelCallHashV1 | None:
        return self.client.last_call

    def _validate_candidate(
        self,
        *,
        public_turn: ProductionPublicTurnV1,
        proposal: ProductionL1ProposalV1,
    ) -> None:
        # Candidate identity is allocated program-side and checked per turn in
        # `produce`, where the emission ordinals are known.
        candidate = proposal.typed_candidate
        if proposal.decision != "emit_l1" or candidate is None:
            # A declining decision is a valid outcome; there is no typed
            # candidate to ground, so grounding checks do not apply.
            return
        rules = [
            item
            for item in self.registry.predicate_role_constraints
            if item.predicate_surface == candidate.predicate.surface
            and item.predicate_sense == candidate.predicate.sense
            and item.canonical_operator == candidate.predicate.canonical_operator
        ]
        if not rules:
            raise ValueError("L1 predicate tuple is not public")
        kind_by_operator = {
            item.canonical_operator: item.kind
            for item in self.policy.l1_operator_kind_bindings
        }
        if kind_by_operator[candidate.predicate.canonical_operator] != candidate.kind:
            raise ValueError("L1 kind does not match operator policy")
        quote = public_turn.evidence_quote.casefold()
        if any(item.surface.casefold() not in quote for item in candidate.local_entities):
            raise ValueError("L1 local entity surface is not grounded in user evidence")
        cues_by_operator = {
            item.canonical_operator: item.cues
            for item in self.policy.operator_evidence_cues
        }
        if not any(
            cue.casefold() in quote
            for cue in cues_by_operator[candidate.predicate.canonical_operator]
        ):
            raise ValueError("L1 operator has no public cue in user evidence")
        # 模态必须与原文一致：被条件从句限定的事实尚未成立，把它记成 actual
        # 就是断言原文没有说的事情。这与极性检查同类，都是证据 grounding。
        if candidate.modality == "actual" and _conditions_the_claim(quote):
            raise ValueError("L1 modality is not grounded in user evidence")
        # 极性必须与原文一致，两个方向都检查：把否定写成肯定会记下相反的事实，
        # 把肯定写成否定同样如此，两者都是 critical false emission。
        negated = _has_explicit_negation(quote)
        if candidate.polarity == "positive" and negated:
            raise ValueError(
                "L1 operator cue is explicitly negated in user evidence"
            )
        if candidate.polarity == "negative" and not negated:
            raise ValueError("L1 polarity is not grounded in user evidence")
        if candidate.polarity not in self.policy.allowed_polarities:
            raise ValueError("L1 polarity is not authorized")
        display_by_role = {
            (item.canonical_operator, item.machine_role): item.display_role
            for item in self.policy.l1_role_display_bindings
        }
        expected_roles = {item.role_name for item in rules}
        actual_roles = {item.role for item in candidate.roles}
        if actual_roles != expected_roles:
            raise ValueError("L1 role coverage does not match predicate contract")
        for role in candidate.roles:
            expected_display = display_by_role.get(
                (candidate.predicate.canonical_operator, role.role)
            )
            if expected_display != role.role_name:
                raise ValueError("L1 role display does not match policy")
        expected_evidence = public_turn.evidence_id
        evidence = [
            (item.evidence_id, item.speaker) for item in candidate.evidence_bindings
        ]
        if evidence != [(expected_evidence, "user")]:
            raise ValueError("L1 evidence binding does not match public turn")
        if (
            candidate.derivation.method != "explicit"
            or candidate.derivation.basis is not None
            or candidate.derivation.evidence_ids != [expected_evidence]
        ):
            raise ValueError("L1 derivation is not exact explicit evidence")
        lifecycle = candidate.lifecycle
        # supersession 是被支持的：一次更正必须能取代它更正的那条事实。其余
        # lifecycle 关系仍在本作用域之外。
        if (
            lifecycle.lifecycle != self.policy.lifecycle
            or lifecycle.replacement_candidate_ref is not None
            or lifecycle.replaces_candidate_refs
            or lifecycle.conflicts_with_candidate_refs
        ):
            raise ValueError("L1 lifecycle is outside create-active policy")
        if (
            candidate.operation_provenance.confirmed_by_operation_refs
            or candidate.operation_provenance.added_by_operation_refs
            or candidate.condition_bindings
            or candidate.scope_bindings
        ):
            raise ValueError("L1 proposal contains unsupported production bindings")
        _validate_time(candidate=candidate, policy=self.policy)

    def produce(self, turns: Sequence[RawTurnV1]) -> BoundL1CandidateProducer:
        public_turns = [
            ProductionPublicTurnV1(
                session_id=item.session_id,
                turn_id=item.turn_id,
                turn_index=item.turn_index,
                user_text=item.user_text,
                assistant_text=item.assistant_text,
                candidate_ref=allocate_support_ref(item.turn_id),
                evidence_id=f"evidence-{item.turn_id}-user",
                evidence_quote=item.user_text,
            )
            for item in turns
        ]
        if not public_turns or len({item.turn_id for item in public_turns}) != len(
            public_turns
        ):
            raise ValueError("production L1 turns must be non-empty and unique")
        public_contract = {
            "ontology_registry": self.registry.model_dump(mode="json"),
            "policy": self.policy.model_dump(mode="json"),
            "response_schema": (
                ProductionL1SlotBatchResponseV1.model_json_schema()
            ),
        }
        raw = self.client.request(
            system_prompt=(
                "Return exactly one production-l1-slot-batch-response-v1 JSON "
                "object. Decide, for each turn, whether it states a durable "
                "memory: emit_l1 with semantic slots, or no_memory/abstain with "
                "no slots. A turn may state several memories, so it may carry "
                "several emit_l1 proposals. For each role slot give the public "
                "role, the exact surface from the user text, and that surface's "
                "character offsets in the user text. Do not construct "
                "identifiers, evidence bindings, derivation, lifecycle or "
                "provenance.\n"
                # predicate_surface 与 role slot surface 的来源不同：前者取自
                # registry 已发布的元组，后者取自用户原文。缺了这句区分，把
                # "preferred"/"drunk" 按原文变形是合理读法，却会被边界拒绝。
                "predicate_surface, predicate_sense and canonical_operator must be "
                "copied verbatim from one published tuple in "
                "predicate_role_constraints. Do not inflect the predicate surface "
                "to match the user's wording: role slot surfaces come from the "
                "user text, but the predicate triple comes from the registry.\n"
                "Return JSON only."
            ),
            public_input={
                "public_contract": public_contract,
                "raw_turns": [item.model_dump(mode="json") for item in public_turns],
            },
        )
        call = self.client.last_call
        response_sha256 = call.response_sha256 if call is not None else "unavailable"
        try:
            response = ProductionL1SlotBatchResponseV1.model_validate(raw)
        except ValidationError as exc:
            validation_path, validation_type = _safe_schema_error(exc)
            raise ModelBoundaryError(
                "l1 model proposal failed contract validation: reason=schema; "
                f"validation_path={validation_path}; "
                f"validation_type={validation_type}; "
                f"response_sha256={response_sha256}"
            ) from None
        except Exception:
            raise ModelBoundaryError(
                "l1 model proposal failed contract validation: "
                "reason=schema_internal; "
                f"response_sha256={response_sha256}"
            ) from None
        # Every turn must be decided exactly once, but a turn may carry several
        # emissions, so group rather than collapse to one proposal per turn.
        by_turn: dict[str, list[ProductionL1SlotProposalV1]] = {}
        for item in response.proposals:
            by_turn.setdefault(item.turn_id, []).append(item)
        if set(by_turn) != {item.turn_id for item in public_turns}:
            raise ModelBoundaryError(
                "l1 model proposal failed contract validation: "
                "reason=turn_coverage; "
                f"response_sha256={response_sha256}"
            )
        materialized: list[ProductionL1ProposalV1] = []
        try:
            public_by_turn = {item.turn_id: item for item in public_turns}
            for turn_id, proposals in by_turn.items():
                public_turn = public_by_turn[turn_id]
                for proposal in proposals:
                    if proposal.decision != "emit_l1" or proposal.slots is None:
                        materialized.append(
                            ProductionL1ProposalV1(
                                turn_id=turn_id,
                                decision=proposal.decision,
                            )
                        )
                        continue
                    # 取代目标必须是本批次里真实存在的另一轮：否则模型可以凭空
                    # 声明一条取代关系，或让一轮取代自己形成自引用。
                    for target in proposal.slots.supersedes_turn_ids:
                        if target == turn_id:
                            raise ValueError(
                                "L1 supersession target is the turn itself"
                            )
                        if target not in public_by_turn:
                            raise ValueError(
                                "L1 supersession target is not a known turn"
                            )
                    candidate = materialize_typed_l1_candidate(
                        slots=proposal.slots,
                        registry=self.registry,
                        policy=self.policy,
                        user_text=public_turn.user_text,
                        evidence_id=public_turn.evidence_id,
                    )
                    typed = ProductionL1ProposalV1(
                        turn_id=turn_id,
                        decision="emit_l1",
                        typed_candidate=candidate,
                    )
                    # The materialized candidate still faces every production
                    # contract check, so program-built structure is not trusted
                    # merely because the program built it.
                    self._validate_candidate(
                        public_turn=public_turn,
                        proposal=typed,
                    )
                    materialized.append(typed)
        except Exception as exc:
            raise ModelBoundaryError(
                "l1 model proposal failed contract validation: "
                "reason=candidate_grounding; "
                f"validation_code={_contract_validation_code(exc)}; "
                f"response_sha256={response_sha256}"
            ) from None
        return BoundL1CandidateProducer(materialized)


class OpenAICompatibleL2Producer:
    def __init__(
        self,
        *,
        registry: OntologyRegistry,
        policy: ProductionExtractionPolicyV1,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int = 120,
        max_tokens: int = 8192,
        max_attempts: int = 2,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        validate_production_policy(registry, policy)
        self.registry = registry
        self.policy = policy
        self.client = _OpenAICompatibleJSONClient(
            stage="l2",
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
            max_tokens=max_tokens,
            max_attempts=max_attempts,
            opener=opener,
        )

    @property
    def last_call(self) -> ModelCallHashV1 | None:
        return self.client.last_call

    def produce(
        self, admitted_l1: Sequence[AdmittedL1Record]
    ) -> list[ProposedL2CandidateV1]:
        if not admitted_l1:
            raise ValueError("L2 production requires admitted L1 support")
        support_refs = [item.candidate_ref for item in admitted_l1]
        turn_refs = list(dict.fromkeys(item.turn_id for item in admitted_l1))
        session_refs = list(dict.fromkeys(item.session_id for item in admitted_l1))
        evidence_bindings = [
            binding
            for item in admitted_l1
            for binding in item.linked_candidate.typed_candidate.evidence_bindings
        ]
        public_support = [
            {
                "candidate_ref": item.candidate_ref,
                "turn_id": item.turn_id,
                "session_id": item.session_id,
                "typed_candidate": item.linked_candidate.typed_candidate.model_dump(
                    mode="json"
                ),
                "evidence_bindings": [
                    binding.model_dump(mode="json")
                    for binding in item.linked_candidate.typed_candidate.evidence_bindings
                ],
            }
            for item in admitted_l1
        ]
        raw = self.client.request(
            system_prompt=(
                "Return exactly one production-l2-slot-response-v1 JSON object. "
                "Decide whether the admitted L1 supports jointly establish a "
                "durable abstraction: emit_l2 with abstraction slots, or "
                "abstain with no slots. Give the predicate tuple, kind, "
                "abstraction method, modality, polarity, which support surface "
                "fills which public role, and a statement of the abstraction. "
                "Support, turn, session, evidence and closure references are "
                "derived from the admitted support, so do not restate them. "
                "Return JSON only."
            ),
            public_input={
                "public_contract": {
                    "ontology_registry": self.registry.model_dump(mode="json"),
                    "policy": self.policy.model_dump(mode="json"),
                    "response_schema": (
                        ProductionL2SlotResponseV1.model_json_schema()
                    ),
                },
                "accepted_l1": public_support,
            },
        )
        call = self.client.last_call
        response_sha256 = call.response_sha256 if call is not None else "unavailable"
        try:
            response = ProductionL2SlotResponseV1.model_validate(raw)
        except ValidationError as exc:
            validation_path, validation_type = _safe_schema_error(exc)
            raise ModelBoundaryError(
                "l2 model proposal failed contract validation: reason=schema; "
                f"validation_path={validation_path}; "
                f"validation_type={validation_type}; "
                f"response_sha256={response_sha256}"
            ) from None
        except Exception:
            raise ModelBoundaryError(
                "l2 model proposal failed contract validation: "
                "reason=schema_internal; "
                f"response_sha256={response_sha256}"
            ) from None
        if response.decision == "abstain" or response.slots is None:
            # 没有可靠抽象是一个被记录的结果，不是失败。
            return []
        try:
            candidate = materialize_typed_l2_candidate(
                slots=response.slots,
                admitted_l1=admitted_l1,
                registry=self.registry,
                policy=self.policy,
            )
            # 物化出的候选仍然要过下面每一条 production 契约检查：程序造的结构
            # 不因为出自程序就被信任。
            for claim in candidate.structured_claims:
                if claim.polarity not in self.policy.allowed_polarities:
                    raise ValueError("L2 polarity is not authorized")
            if candidate.supporting_l1_refs != support_refs:
                raise ValueError("L2 support order or coverage mismatch")
            if candidate.closure.required_support_refs != support_refs:
                raise ValueError("L2 required closure mismatch")
            if candidate.closure.optional_support_refs:
                raise ValueError("L2 optional support is not allowed")
            if candidate.source_turn_refs != turn_refs:
                raise ValueError("L2 turn closure mismatch")
            if candidate.source_session_refs != session_refs:
                raise ValueError("L2 session closure mismatch")
            expected_evidence = [
                item.model_dump(mode="json") for item in evidence_bindings
            ]
            actual_evidence = [
                item.model_dump(mode="json") for item in candidate.evidence_bindings
            ]
            if actual_evidence != expected_evidence:
                raise ValueError("L2 evidence closure mismatch")
            if len(candidate.structured_claims) != 1:
                raise ValueError("production L2 requires one structured claim")
            claim = candidate.structured_claims[0]
            if claim.supporting_l1_refs != support_refs:
                raise ValueError("L2 claim support closure mismatch")
            l2_by_operator = {
                item.canonical_operator: item
                for item in self.policy.l2_operator_policies
            }
            operator_policy = l2_by_operator.get(
                claim.predicate.canonical_operator
            )
            if operator_policy is None or candidate.kind != operator_policy.kind:
                raise ValueError("L2 operator kind is not public")
            registry_tuples = {
                (
                    item.predicate_surface,
                    item.predicate_sense,
                    item.canonical_operator,
                )
                for item in self.registry.predicate_role_constraints
            }
            if (
                claim.predicate.surface,
                claim.predicate.sense,
                claim.predicate.canonical_operator,
            ) not in registry_tuples:
                raise ValueError("L2 predicate tuple is not public")
            admitted_by_ref = {
                item.candidate_ref: item.linked_candidate.typed_candidate
                for item in admitted_l1
            }
            claim_predicate = (
                claim.predicate.surface,
                claim.predicate.sense,
                claim.predicate.canonical_operator,
            )
            semantic_support = [
                admitted_by_ref[item]
                for item in claim.supporting_l1_refs
                if (
                    admitted_by_ref[item].predicate.surface,
                    admitted_by_ref[item].predicate.sense,
                    admitted_by_ref[item].predicate.canonical_operator,
                )
                == claim_predicate
            ]
            if not semantic_support:
                raise ValueError("L2 claim predicate lacks admitted L1 semantic support")
            display_by_role = {
                item.machine_role: item.display_role
                for item in operator_policy.role_bindings
            }
            if {item.role for item in claim.roles} != set(display_by_role):
                raise ValueError("L2 role coverage mismatch")
            if any(
                item.role_name != display_by_role[item.role] for item in claim.roles
            ):
                raise ValueError("L2 role display mismatch")
            support_combinations: set[tuple[str, str, str]] = set()
            for support in semantic_support:
                support_surfaces = {
                    item.local_entity_id: item.surface.casefold()
                    for item in support.local_entities
                }
                support_combinations.update(
                    (
                        item.role,
                        item.role_name,
                        support_surfaces[item.local_entity_id],
                    )
                    for item in support.roles
                )
            claim_surfaces = {
                item.local_entity_id: item.surface.casefold()
                for item in claim.local_entities
            }
            claim_combinations = {
                (
                    item.role,
                    item.role_name,
                    claim_surfaces[item.local_entity_id],
                )
                for item in claim.roles
            }
            if not claim_combinations.issubset(support_combinations):
                raise ValueError("L2 claim roles or entities lack admitted L1 support")
            summary = candidate.summary.casefold()
            if any(surface not in summary for surface in claim_surfaces.values()):
                raise ValueError("L2 claim entity surface is absent from summary")
            operator_cues = {
                item.canonical_operator: item.cues
                for item in self.policy.operator_evidence_cues
            }
            if not any(
                cue.casefold() in summary
                for cue in operator_cues[claim.predicate.canonical_operator]
            ):
                raise ValueError("L2 summary lacks the selected operator evidence cue")
            if claim.polarity == "positive" and _has_explicit_negation(summary):
                raise ValueError(
                    "L2 summary explicitly negates the selected operator cue"
                )
            if candidate.abstraction.method not in operator_policy.allowed_abstraction_methods:
                raise ValueError("L2 abstraction method is not public")
            if candidate.closure.pattern not in operator_policy.allowed_closure_patterns:
                raise ValueError("L2 closure pattern is not public")
            synthetic_l1 = TypedL1Candidate(
                kind="event",
                predicate=claim.predicate,
                local_entities=claim.local_entities,
                roles=claim.roles,
                modality=claim.modality,
                polarity=claim.polarity,
                time=claim.time,
                derivation=admitted_l1[0].linked_candidate.typed_candidate.derivation,
                evidence_bindings=[evidence_bindings[0]],
                lifecycle=admitted_l1[0].linked_candidate.typed_candidate.lifecycle,
                operation_provenance=admitted_l1[0].linked_candidate.typed_candidate.operation_provenance,
            )
            _validate_time(candidate=synthetic_l1, policy=self.policy)
        except Exception as exc:
            raise ModelBoundaryError(
                "l2 model proposal failed contract validation: "
                "reason=candidate_grounding; "
                f"validation_code={_contract_validation_code(exc)}; "
                f"response_sha256={response_sha256}"
            ) from None
        return [
            ProposedL2CandidateV1(
                candidate_ref=allocate_l2_candidate_ref(support_refs),
                typed_candidate=candidate,
            )
        ]
