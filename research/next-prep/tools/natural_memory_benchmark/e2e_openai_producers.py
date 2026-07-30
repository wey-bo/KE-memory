from __future__ import annotations

import hashlib
import json
import socket
from typing import Any, Callable, Literal, Sequence
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .e2e_pipeline import (
    AdmittedL1Record,
    ProposedL1CandidateV1,
    ProposedL2CandidateV1,
    RawTurnV1,
    TurnExtractionInputV1,
)
from .l1_ontology_linking import OntologyRegistry
from .typed_extractor_l1 import L1Kind, TypedL1Candidate, TypedModality
from .typed_extractor_l2 import (
    ClosurePattern,
    L2AbstractionMethod,
    L2Kind,
    TypedL2Candidate,
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
        modality_time_policies=[
            ModalityTimePolicyV1(
                modality="actual",
                event_time_policy="optional",
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
            "response_format": {"type": "json_object"},
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
            try:
                with self._opener(request, timeout=self.timeout_seconds) as response:
                    raw = response.read()
                envelope = json.loads(raw)
                response_model = envelope["model"]
                choices = envelope["choices"]
                if not isinstance(response_model, str) or not response_model.strip():
                    raise TypeError("missing response model")
                if not isinstance(choices, list) or len(choices) != 1:
                    raise TypeError("response must contain one choice")
                content = choices[0]["message"]["content"]
                if not isinstance(content, str):
                    raise TypeError("response content must be text")
                result = json.loads(content)
                if not isinstance(result, dict):
                    raise TypeError("response content must be a JSON object")
                self.last_call = ModelCallHashV1(
                    stage=self.stage,
                    requested_model=self.model,
                    response_model=response_model,
                    request_sha256=hashlib.sha256(request_bytes).hexdigest(),
                    response_sha256=hashlib.sha256(raw).hexdigest(),
                    attempts=attempt,
                )
                return result
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                raise ModelBoundaryError(
                    f"{self.stage} model response was invalid"
                ) from None
            except Exception as exc:
                if self._retryable(exc) and attempt < self.max_attempts:
                    continue
                raise ModelBoundaryError(
                    f"{self.stage} model request failed after {attempt} attempt(s)"
                ) from None
        raise AssertionError("unreachable model retry state")


def allocate_support_ref(turn_id: str) -> str:
    return f"support-{hashlib.sha256(turn_id.encode('utf-8')).hexdigest()[:16]}"


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
    candidate_ref: str = Field(pattern=r"^support-[0-9a-f]{16}$")
    typed_candidate: TypedL1Candidate


class ProductionL1BatchResponseV1(StrictModel):
    schema_version: Literal["production-l1-batch-response-v1"] = (
        "production-l1-batch-response-v1"
    )
    proposals: list[ProductionL1ProposalV1] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_turns(self) -> "ProductionL1BatchResponseV1":
        turn_ids = [item.turn_id for item in self.proposals]
        refs = [item.candidate_ref for item in self.proposals]
        if len(turn_ids) != len(set(turn_ids)) or len(refs) != len(set(refs)):
            raise ValueError("duplicate production L1 proposal")
        return self


class ProductionL2ResponseV1(StrictModel):
    schema_version: Literal["production-l2-response-v1"] = (
        "production-l2-response-v1"
    )
    candidate_ref: str = Field(
        min_length=1,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$",
    )
    typed_candidate: TypedL2Candidate


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
    def __init__(self, proposals: Sequence[ProductionL1ProposalV1]) -> None:
        self._by_turn = {item.turn_id: item for item in proposals}
        self._consumed: set[str] = set()

    def produce(self, value: TurnExtractionInputV1) -> list[ProposedL1CandidateV1]:
        proposal = self._by_turn.get(value.turn.turn_id)
        if proposal is None or value.turn.turn_id in self._consumed:
            raise ValueError("bound L1 proposal coverage mismatch")
        expected_evidence = f"evidence-{value.turn.turn_id}-user"
        if value.user_evidence.evidence_id != expected_evidence:
            raise ValueError("runtime evidence allocation changed after L1 proposal")
        self._consumed.add(value.turn.turn_id)
        return [
            ProposedL1CandidateV1(
                candidate_ref=proposal.candidate_ref,
                typed_candidate=proposal.typed_candidate,
            )
        ]


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
        if proposal.candidate_ref != public_turn.candidate_ref:
            raise ValueError("L1 candidate ref does not match allocated ref")
        candidate = proposal.typed_candidate
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
        if (
            lifecycle.lifecycle != self.policy.lifecycle
            or lifecycle.replacement_candidate_ref is not None
            or lifecycle.replaces_candidate_refs
            or lifecycle.supersedes_candidate_refs
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
            "response_schema": ProductionL1BatchResponseV1.model_json_schema(),
        }
        raw = self.client.request(
            system_prompt=(
                "Return exactly one production-l1-batch-response-v1 JSON object. "
                "Copy only public operator, role, policy, candidate, and evidence "
                "bindings. Return JSON only."
            ),
            public_input={
                "public_contract": public_contract,
                "raw_turns": [item.model_dump(mode="json") for item in public_turns],
            },
        )
        try:
            response = ProductionL1BatchResponseV1.model_validate(raw)
            by_turn = {item.turn_id: item for item in response.proposals}
            if set(by_turn) != {item.turn_id for item in public_turns}:
                raise ValueError("L1 response turn coverage mismatch")
            public_by_turn = {item.turn_id: item for item in public_turns}
            for turn_id, proposal in by_turn.items():
                self._validate_candidate(
                    public_turn=public_by_turn[turn_id],
                    proposal=proposal,
                )
        except Exception:
            raise ModelBoundaryError("l1 model proposal failed contract validation") from None
        return BoundL1CandidateProducer(response.proposals)


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
                "Return exactly one production-l2-response-v1 JSON object. Use "
                "the exact admitted support, turn, session, and evidence closure. "
                "Return JSON only."
            ),
            public_input={
                "public_contract": {
                    "ontology_registry": self.registry.model_dump(mode="json"),
                    "policy": self.policy.model_dump(mode="json"),
                    "required_support_refs": support_refs,
                    "required_turn_refs": turn_refs,
                    "required_session_refs": session_refs,
                    "required_evidence_bindings": [
                        item.model_dump(mode="json") for item in evidence_bindings
                    ],
                    "response_schema": ProductionL2ResponseV1.model_json_schema(),
                },
                "accepted_l1": public_support,
            },
        )
        try:
            response = ProductionL2ResponseV1.model_validate(raw)
            candidate = response.typed_candidate
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
        except Exception:
            raise ModelBoundaryError("l2 model proposal failed contract validation") from None
        return [
            ProposedL2CandidateV1(
                candidate_ref=response.candidate_ref,
                typed_candidate=response.typed_candidate,
            )
        ]
