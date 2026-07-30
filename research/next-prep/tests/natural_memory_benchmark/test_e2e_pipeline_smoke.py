from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

import pytest

from tools.natural_memory_benchmark.e2e_openai_producers import (
    ModelBoundaryError,
    OpenAICompatibleL1BatchProducer,
    ProductionL1BatchResponseV1,
    allocate_support_ref,
    build_diagnostic_production_policy,
)
from tools.natural_memory_benchmark.e2e_openai_runtime import run_openai_e2e
from tools.natural_memory_benchmark.e2e_pipeline import (
    ProposedL1CandidateV1,
    ProposedL2CandidateV1,
    RawTurnV1,
    TurnExtractionInputV1,
    run_e2e_pipeline,
)
from tools.natural_memory_benchmark.l1_ontology_linking import (
    build_diagnostic_ontology_registry,
)
from tools.natural_memory_benchmark.query_compiler_v2 import (
    AnswerDraftV1,
    QueryAtomDraftV1,
    QueryDraftRequestV1,
    QueryDraftV1,
    QueryPatternGroupDraftV1,
    QueryRoleDraftV1,
    QueryTermDraftV1,
)
from tools.natural_memory_benchmark.query_compiler_v2_openai_producer import (
    QueryDraftProductionError,
)
from tools.natural_memory_benchmark.typed_extractor_l1 import (
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
from tools.natural_memory_benchmark.typed_extractor_l2 import (
    TypedL2Abstraction,
    TypedL2Candidate,
    TypedL2Closure,
    TypedL2StructuredClaim,
)


SUPPORT_PREFERENCE = "support-0000000000000001"
SUPPORT_HABIT = "support-0000000000000002"


def _typed_l1(
    value: TurnExtractionInputV1,
    *,
    predicate_surface: str,
    predicate_sense: str,
    canonical_operator: str,
    entity_surface: str = "coffee",
) -> TypedL1Candidate:
    evidence = value.user_evidence
    return TypedL1Candidate(
        kind="preference" if canonical_operator == "prefer" else "event",
        predicate=TypedPredicate(
            surface=predicate_surface,
            sense=predicate_sense,
            canonical_operator=canonical_operator,
        ),
        local_entities=[
            TypedLocalEntity(local_entity_id="entity-01", surface=entity_surface)
        ],
        roles=[
            TypedRoleBinding(
                role="theme",
                role_name="theme",
                local_entity_id="entity-01",
            )
        ],
        modality="actual",
        polarity="positive",
        time=TypedTimeBinding(),
        derivation=TypedDerivationProvenance(
            method="explicit",
            evidence_ids=[evidence.evidence_id],
        ),
        evidence_bindings=[
            TypedEvidenceBinding(evidence_id=evidence.evidence_id, speaker="user")
        ],
        lifecycle=TypedLifecycleBinding(lifecycle="active"),
        operation_provenance=TypedOperationProvenance(),
    )


class _L1Producer:
    def __init__(self, *, entity_surface: str = "coffee") -> None:
        self.entity_surface = entity_surface

    def produce(
        self, value: TurnExtractionInputV1
    ) -> list[ProposedL1CandidateV1]:
        if value.turn.turn_index == 0:
            return [
                ProposedL1CandidateV1(
                    candidate_ref=SUPPORT_PREFERENCE,
                    typed_candidate=_typed_l1(
                        value,
                        predicate_surface="prefer",
                        predicate_sense="preference_theme",
                        canonical_operator="prefer",
                        entity_surface=self.entity_surface,
                    ),
                )
            ]
        return [
            ProposedL1CandidateV1(
                candidate_ref=SUPPORT_HABIT,
                typed_candidate=_typed_l1(
                    value,
                    predicate_surface="drink",
                    predicate_sense="consume_beverage",
                    canonical_operator="drink",
                    entity_surface=self.entity_surface,
                ),
            )
        ]


class _L2Producer:
    def produce(self, admitted_l1):
        support_refs = [item.candidate_ref for item in admitted_l1]
        evidence_bindings = [
            TypedEvidenceBinding(
                evidence_id=item.revision.payload.source.evidence_spans[0].evidence_id,
                speaker="user",
            )
            for item in admitted_l1
        ]
        return [
            ProposedL2CandidateV1(
                candidate_ref="l2-preference-profile",
                typed_candidate=TypedL2Candidate(
                    kind="preference_profile",
                    summary="Coffee is the supported beverage preference.",
                    supporting_l1_refs=support_refs,
                    structured_claims=[
                        TypedL2StructuredClaim(
                            claim_ref="claim-01",
                            predicate=TypedPredicate(
                                surface="prefer",
                                sense="preference_theme",
                                canonical_operator="prefer",
                            ),
                            local_entities=[
                                TypedLocalEntity(
                                    local_entity_id="entity-01",
                                    surface="coffee",
                                )
                            ],
                            roles=[
                                TypedRoleBinding(
                                    role="theme",
                                    role_name="theme",
                                    local_entity_id="entity-01",
                                )
                            ],
                            modality="actual",
                            polarity="positive",
                            time=TypedTimeBinding(),
                            supporting_l1_refs=support_refs,
                        )
                    ],
                    abstraction=TypedL2Abstraction(
                        method="preference_aggregation",
                        basis="two admitted category facts",
                    ),
                    closure=TypedL2Closure(
                        pattern="multi_evidence_set",
                        required_support_refs=support_refs,
                    ),
                    source_turn_refs=[item.turn_id for item in admitted_l1],
                    source_session_refs=["session-0000000000000001"],
                    evidence_bindings=evidence_bindings,
                ),
            )
        ]


class _QueryProducer:
    def produce(self, request: QueryDraftRequestV1) -> QueryDraftV1:
        return QueryDraftV1(
            query_id=request.query_id,
            intent="fact_lookup",
            target_level="both",
            answer=AnswerDraftV1(kind="fact", variable="?beverage"),
            pattern_groups=[
                QueryPatternGroupDraftV1(
                    group_id="group-preference",
                    atoms=[
                        QueryAtomDraftV1(
                            atom_id="atom-preference",
                            predicate_surface="prefer",
                            roles=[
                                QueryRoleDraftV1(
                                    role="theme",
                                    role_name="theme",
                                    term=QueryTermDraftV1(
                                        kind="variable",
                                        value="?beverage",
                                        expected_type="memory:Beverage",
                                    ),
                                )
                            ],
                        )
                    ],
                )
            ],
            source_status_constraints=["user_reported"],
            conflict_policy="require_resolved",
            supersession_policy="current_only",
            evidence_policy="provenance_closure",
            producer_id="e2e-smoke-query",
            producer_version="1",
        )


def _turns() -> list[RawTurnV1]:
    return [
        RawTurnV1(
            session_id="session-0000000000000001",
            turn_id="turn-0000000000000001",
            turn_index=0,
            user_text="Coffee is preferred.",
            assistant_text="Noted.",
        ),
        RawTurnV1(
            session_id="session-0000000000000001",
            turn_id="turn-0000000000000002",
            turn_index=1,
            user_text="Coffee is drunk regularly.",
            assistant_text="Understood.",
        ),
    ]


class _BufferedResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.status = 200

    def __enter__(self) -> "_BufferedResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


class _SequencedOpener:
    def __init__(
        self,
        responses: list[bytes | Exception | _BufferedResponse],
    ) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []
        self.timeouts: list[int] = []

    def __call__(self, request: Any, *, timeout: int) -> _BufferedResponse:
        self.timeouts.append(timeout)
        self.requests.append(json.loads(request.data))
        if not self.responses:
            raise AssertionError("unexpected model request")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, _BufferedResponse):
            return response
        return _BufferedResponse(response)


class _ReadFailingResponse(_BufferedResponse):
    def __init__(self, exc: Exception) -> None:
        super().__init__(b"sensitive-provider-response-body")
        self.exc = exc

    def read(self) -> bytes:
        raise self.exc


def _chat_response(payload: object, *, include_model: bool = True) -> bytes:
    envelope = {
        "choices": [
            {"message": {"content": json.dumps(payload, sort_keys=True)}}
        ],
    }
    if include_model:
        envelope["model"] = "test-model-response"
    return json.dumps(envelope, sort_keys=True).encode("utf-8")


@pytest.mark.parametrize(
    ("response", "reason", "forbidden_text"),
    [
        (
            b"sensitive-provider-envelope",
            "envelope_json",
            "sensitive-provider-envelope",
        ),
        (
            json.dumps(
                {
                    "model": "test-model-response",
                    "choices": [
                        {"message": {"content": "sensitive-provider-content"}}
                    ],
                },
                sort_keys=True,
            ).encode("utf-8"),
            "content_json",
            "sensitive-provider-content",
        ),
    ],
)
def test_model_boundary_error_reports_sanitized_response_fingerprint(
    tmp_path: Path,
    response: bytes,
    reason: str,
    forbidden_text: str,
) -> None:
    repository = tmp_path / f"{reason}-memory-history.git"
    result_path = tmp_path / f"{reason}-result.json"

    with pytest.raises(ModelBoundaryError) as captured:
        run_openai_e2e(
            turns=_turns(),
            question="What beverage is preferred?",
            repository_path=repository,
            result_path=result_path,
            base_url="https://model.invalid/v1",
            api_key="credential-that-must-not-leak",
            model="test-model",
            max_attempts=1,
            opener=_SequencedOpener([response]),
        )

    message = str(captured.value)
    assert f"reason={reason}" in message
    assert "http_status=200" in message
    assert f"response_sha256={hashlib.sha256(response).hexdigest()}" in message
    assert forbidden_text not in message
    assert not repository.exists()
    assert not result_path.exists()


def test_model_boundary_http_error_reports_sanitized_fingerprint(
    tmp_path: Path,
) -> None:
    error_body = b"sensitive-provider-error-body"
    http_error = HTTPError(
        url="https://model.invalid/v1/chat/completions",
        code=422,
        msg="Unprocessable Entity",
        hdrs=None,
        fp=io.BytesIO(error_body),
    )
    repository = tmp_path / "http-error-memory-history.git"
    result_path = tmp_path / "http-error-result.json"

    with pytest.raises(ModelBoundaryError) as captured:
        run_openai_e2e(
            turns=_turns(),
            question="What beverage is preferred?",
            repository_path=repository,
            result_path=result_path,
            base_url="https://model.invalid/v1",
            api_key="credential-that-must-not-leak",
            model="test-model",
            max_attempts=1,
            opener=_SequencedOpener([http_error]),
        )

    message = str(captured.value)
    assert "reason=http_error" in message
    assert "http_status=422" in message
    assert f"response_sha256={hashlib.sha256(error_body).hexdigest()}" in message
    assert "sensitive-provider-error-body" not in message
    assert not repository.exists()
    assert not result_path.exists()


def test_model_boundary_open_exception_reports_sanitized_phase_and_type(
    tmp_path: Path,
) -> None:
    credential = "credential-that-must-not-leak"
    exception_detail = "sensitive-open-exception-detail"
    repository = tmp_path / "open-error-memory-history.git"
    result_path = tmp_path / "open-error-result.json"

    with pytest.raises(ModelBoundaryError) as captured:
        run_openai_e2e(
            turns=_turns(),
            question="What beverage is preferred?",
            repository_path=repository,
            result_path=result_path,
            base_url="https://model.invalid/v1",
            api_key=credential,
            model="test-model",
            max_attempts=1,
            opener=_SequencedOpener(
                [ConnectionResetError(exception_detail)]
            ),
        )

    message = str(captured.value)
    assert "reason=request_exception" in message
    assert "request_phase=open" in message
    assert "exception_type=ConnectionResetError" in message
    assert exception_detail not in message
    assert credential not in message
    assert not repository.exists()
    assert not result_path.exists()


def test_model_boundary_read_exception_reports_sanitized_phase_and_type(
    tmp_path: Path,
) -> None:
    credential = "credential-that-must-not-leak"
    exception_detail = "sensitive-provider-response-body"
    repository = tmp_path / "read-error-memory-history.git"
    result_path = tmp_path / "read-error-result.json"

    with pytest.raises(ModelBoundaryError) as captured:
        run_openai_e2e(
            turns=_turns(),
            question="What beverage is preferred?",
            repository_path=repository,
            result_path=result_path,
            base_url="https://model.invalid/v1",
            api_key=credential,
            model="test-model",
            max_attempts=1,
            opener=_SequencedOpener(
                [_ReadFailingResponse(ConnectionAbortedError(exception_detail))]
            ),
        )

    message = str(captured.value)
    assert "reason=request_exception" in message
    assert "request_phase=read" in message
    assert "exception_type=ConnectionAbortedError" in message
    assert exception_detail not in message
    assert credential not in message
    assert not repository.exists()
    assert not result_path.exists()


def _production_l1_payload() -> dict[str, object]:
    proposals: list[dict[str, object]] = []
    values = (
        ("turn-0000000000000001", "preference", "prefer", "preference_theme", "prefer"),
        ("turn-0000000000000002", "event", "drink", "consume_beverage", "drink"),
    )
    for turn_id, kind, surface, sense, operator in values:
        evidence_id = f"evidence-{turn_id}-user"
        candidate = TypedL1Candidate(
            kind=kind,
            predicate=TypedPredicate(
                surface=surface,
                sense=sense,
                canonical_operator=operator,
            ),
            local_entities=[
                TypedLocalEntity(local_entity_id="entity-01", surface="coffee")
            ],
            roles=[
                TypedRoleBinding(
                    role="theme",
                    role_name="theme",
                    local_entity_id="entity-01",
                )
            ],
            modality="actual",
            polarity="positive",
            time=TypedTimeBinding(),
            derivation=TypedDerivationProvenance(
                method="explicit",
                evidence_ids=[evidence_id],
            ),
            evidence_bindings=[
                TypedEvidenceBinding(evidence_id=evidence_id, speaker="user")
            ],
            lifecycle=TypedLifecycleBinding(lifecycle="active"),
            operation_provenance=TypedOperationProvenance(),
        )
        proposals.append(
            {
                "turn_id": turn_id,
                "candidate_ref": allocate_support_ref(turn_id),
                "decision": "emit_l1",
                "typed_candidate": candidate.model_dump(mode="json"),
            }
        )
    return {
        "schema_version": "production-l1-batch-response-v1",
        "proposals": proposals,
    }


def _production_l2_payload() -> dict[str, object]:
    turns = _turns()
    support_refs = [allocate_support_ref(item.turn_id) for item in turns]
    evidence_bindings = [
        TypedEvidenceBinding(
            evidence_id=f"evidence-{item.turn_id}-user",
            speaker="user",
        )
        for item in turns
    ]
    candidate = TypedL2Candidate(
        kind="preference_profile",
        summary="Coffee is the supported beverage preference.",
        supporting_l1_refs=support_refs,
        structured_claims=[
            TypedL2StructuredClaim(
                claim_ref="claim-01",
                predicate=TypedPredicate(
                    surface="prefer",
                    sense="preference_theme",
                    canonical_operator="prefer",
                ),
                local_entities=[
                    TypedLocalEntity(local_entity_id="entity-01", surface="coffee")
                ],
                roles=[
                    TypedRoleBinding(
                        role="theme",
                        role_name="theme",
                        local_entity_id="entity-01",
                    )
                ],
                modality="actual",
                polarity="positive",
                time=TypedTimeBinding(),
                supporting_l1_refs=support_refs,
            )
        ],
        abstraction=TypedL2Abstraction(
            method="preference_aggregation",
            basis="two admitted category facts",
        ),
        closure=TypedL2Closure(
            pattern="multi_evidence_set",
            required_support_refs=support_refs,
        ),
        source_turn_refs=[item.turn_id for item in turns],
        source_session_refs=[turns[0].session_id],
        evidence_bindings=evidence_bindings,
    )
    return {
        "schema_version": "production-l2-response-v1",
        "candidate_ref": "l2-preference-profile-model",
        "typed_candidate": candidate.model_dump(mode="json"),
    }


def _production_query_payload() -> dict[str, object]:
    request = QueryDraftRequestV1(
        query_id="query-e2e-1",
        raw_query="What beverage is preferred?",
        query_time="2026-07-30T00:00:23Z",
        compiler_policy_revision="e2e-query-policy-v1",
    )
    return _QueryProducer().produce(request).model_dump(mode="json")


def test_l1_schema_contract_error_reports_sanitized_fingerprint(
    tmp_path: Path,
) -> None:
    credential = "credential-that-must-not-leak"
    payload = _production_l1_payload()
    del payload["proposals"][0]["typed_candidate"]["kind"]
    response = _chat_response(payload)
    repository = tmp_path / "schema-error-memory-history.git"
    result_path = tmp_path / "schema-error-result.json"

    with pytest.raises(ModelBoundaryError) as captured:
        run_openai_e2e(
            turns=_turns(),
            question="What beverage is preferred?",
            repository_path=repository,
            result_path=result_path,
            base_url="https://model.invalid/v1",
            api_key=credential,
            model="test-model",
            max_attempts=1,
            opener=_SequencedOpener([response]),
        )

    message = str(captured.value)
    assert "reason=schema" in message
    assert "validation_path=proposals.0.typed_candidate.kind" in message
    assert "validation_type=missing" in message
    assert f"response_sha256={hashlib.sha256(response).hexdigest()}" in message
    assert "Coffee is preferred." not in message
    assert credential not in message
    assert not repository.exists()
    assert not result_path.exists()


def test_l1_unexpected_schema_exception_is_sanitized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credential = "credential-that-must-not-leak"
    exception_detail = "sensitive-schema-exception-detail"
    response = _chat_response(_production_l1_payload())

    def fail_validation(_value: object) -> object:
        raise TypeError(exception_detail)

    monkeypatch.setattr(
        ProductionL1BatchResponseV1,
        "model_validate",
        fail_validation,
    )
    with pytest.raises(ModelBoundaryError) as captured:
        run_openai_e2e(
            turns=_turns(),
            question="What beverage is preferred?",
            repository_path=tmp_path / "schema-internal-memory-history.git",
            result_path=tmp_path / "schema-internal-result.json",
            base_url="https://model.invalid/v1",
            api_key=credential,
            model="test-model",
            max_attempts=1,
            opener=_SequencedOpener([response]),
        )

    message = str(captured.value)
    assert "reason=schema_internal" in message
    assert f"response_sha256={hashlib.sha256(response).hexdigest()}" in message
    assert exception_detail not in message
    assert credential not in message


def test_l1_turn_coverage_error_reports_sanitized_fingerprint(
    tmp_path: Path,
) -> None:
    payload = _production_l1_payload()
    payload["proposals"].pop()
    response = _chat_response(payload)
    repository = tmp_path / "coverage-error-memory-history.git"
    result_path = tmp_path / "coverage-error-result.json"

    with pytest.raises(ModelBoundaryError) as captured:
        run_openai_e2e(
            turns=_turns(),
            question="What beverage is preferred?",
            repository_path=repository,
            result_path=result_path,
            base_url="https://model.invalid/v1",
            api_key="credential-that-must-not-leak",
            model="test-model",
            max_attempts=1,
            opener=_SequencedOpener([response]),
        )

    message = str(captured.value)
    assert "reason=turn_coverage" in message
    assert f"response_sha256={hashlib.sha256(response).hexdigest()}" in message
    assert "Coffee is preferred." not in message
    assert "credential-that-must-not-leak" not in message
    assert not repository.exists()
    assert not result_path.exists()


def test_production_contract_and_malformed_l1_fail_before_git(tmp_path: Path) -> None:
    registry = build_diagnostic_ontology_registry()
    policy = build_diagnostic_production_policy(registry)
    incomplete = policy.model_copy(
        update={
            "l1_role_display_bindings": policy.l1_role_display_bindings[:-1]
        }
    )
    unopened = _SequencedOpener([])
    with pytest.raises(ValueError, match="role.*coverage"):
        OpenAICompatibleL1BatchProducer(
            registry=registry,
            policy=incomplete,
            base_url="https://model.invalid/v1",
            api_key="not-written-anywhere",
            model="test-model",
            opener=unopened,
        )
    assert unopened.requests == []

    malformed = _SequencedOpener([_chat_response("not a proposal object")])
    repository = tmp_path / "malformed-memory-history.git"
    with pytest.raises(ModelBoundaryError) as error:
        run_openai_e2e(
            turns=_turns(),
            question="What beverage is preferred?",
            repository_path=repository,
            result_path=tmp_path / "malformed-result.json",
            base_url="https://model.invalid/v1",
            api_key="credential-that-must-not-leak",
            model="test-model",
            opener=malformed,
        )
    assert "credential-that-must-not-leak" not in str(error.value)
    assert not repository.exists()
    assert not repository.with_name(f"{repository.name}.raw.json").exists()

    existing_result = tmp_path / "existing-result.json"
    existing_result.write_text("occupied", encoding="utf-8")
    preflight = _SequencedOpener([])
    with pytest.raises(FileExistsError, match="repository, raw artifact, and result"):
        run_openai_e2e(
            turns=_turns(),
            question="What beverage is preferred?",
            repository_path=tmp_path / "preflight-memory-history.git",
            result_path=existing_result,
            base_url="https://model.invalid/v1",
            api_key="not-used",
            model="test-model",
            opener=preflight,
        )
    assert preflight.requests == []


def test_openai_runtime_closes_model_write_query_and_evidence(tmp_path: Path) -> None:
    opener = _SequencedOpener(
        [
            TimeoutError("transient transport timeout"),
            _chat_response(_production_l1_payload()),
            _chat_response(_production_l2_payload()),
            _chat_response(_production_query_payload()),
        ]
    )
    outcome = run_openai_e2e(
        turns=_turns(),
        question="What beverage is preferred?",
        repository_path=tmp_path / "model-memory-history.git",
        result_path=tmp_path / "model-result.json",
        base_url="https://model.invalid/v1",
        api_key="credential-that-must-not-enter-public-input",
        model="test-model",
        timeout_seconds=37,
        max_attempts=2,
        opener=opener,
    )

    result = outcome.pipeline
    assert result.snapshot.verification_status == "valid"
    assert result.execution.answer_values == ("memory:CoffeeBeverage",)
    assert result.answer.fallback_triggered is False
    assert {span.text for span in result.answer.evidence_spans} == {
        "Coffee is preferred.",
        "Coffee is drunk regularly.",
    }
    assert [item.stage for item in outcome.receipt.model_calls] == [
        "l1",
        "l2",
        "query",
    ]
    assert outcome.receipt.model_calls[0].attempts == 2
    assert opener.timeouts == [37, 37, 37, 37]

    l1_public = json.loads(opener.requests[0]["messages"][1]["content"])
    serialized_public = json.dumps(l1_public, sort_keys=True).casefold()
    assert "gold" not in serialized_public
    assert "authority" not in serialized_public
    contract = l1_public["public_contract"]
    assert contract["ontology_registry"]["registry_hash"]
    assert len(contract["ontology_registry"]["concepts"]) == 9
    assert len(contract["ontology_registry"]["predicate_role_constraints"]) == 4
    assert {item["canonical_operator"] for item in contract["policy"]["l1_operator_kind_bindings"]} == {
        "prefer",
        "drink",
        "add_ingredient",
    }
    assert len(contract["policy"]["l1_role_display_bindings"]) == 4
    assert contract["policy"]["modality_time_policies"] == [
        {
            "modality": "actual",
            "event_time_policy": "forbidden",
            "valid_time_policy": "forbidden",
        }
    ]
    assert contract["policy"]["operator_evidence_cues"] == [
        {
            "canonical_operator": "prefer",
            "cues": ["prefer", "preferred", "preference"],
        },
        {
            "canonical_operator": "drink",
            "cues": ["drink", "drank", "drunk"],
        },
        {
            "canonical_operator": "add_ingredient",
            "cues": ["add", "added"],
        },
    ]
    assert contract["policy"]["allowed_polarities"] == ["positive"]


def test_l1_semantics_and_non_emission_stop_before_raw_or_git(tmp_path: Path) -> None:
    cases: list[
        tuple[str, list[RawTurnV1], dict[str, object], str]
    ] = []

    wrong_entity_turns = _turns()
    wrong_entity_turns[0] = wrong_entity_turns[0].model_copy(
        update={"user_text": "I prefer tea."}
    )
    cases.append(
        (
            "wrong-entity",
            wrong_entity_turns,
            _production_l1_payload(),
            "local_entity_not_grounded",
        )
    )

    wrong_operator = _production_l1_payload()
    wrong_operator_candidate = wrong_operator["proposals"][1]["typed_candidate"]
    wrong_operator_candidate["kind"] = "preference"
    wrong_operator_candidate["predicate"] = {
        "surface": "prefer",
        "sense": "preference_theme",
        "canonical_operator": "prefer",
    }
    cases.append(
        ("wrong-operator", _turns(), wrong_operator, "operator_cue_missing")
    )

    non_emission = _production_l1_payload()
    non_emission["proposals"][0]["decision"] = "abstain"
    non_emission["proposals"][0]["typed_candidate"] = None
    cases.append(("non-emission", _turns(), non_emission, "emission_required"))

    invented_time = _production_l1_payload()
    invented_time["proposals"][0]["typed_candidate"]["time"]["event_time"] = (
        "2099-01-01"
    )
    cases.append(("invented-time", _turns(), invented_time, "forbidden_time"))

    negated_turns = _turns()
    negated_turns[0] = negated_turns[0].model_copy(
        update={"user_text": "Coffee is not preferred."}
    )
    cases.append(
        (
            "negated-operator",
            negated_turns,
            _production_l1_payload(),
            "operator_cue_negated",
        )
    )

    for name, user_text in (
        ("negated-no-one", "Coffee is preferred by no one."),
        ("negated-not-anymore", "Coffee is preferred, but not anymore."),
    ):
        turns = _turns()
        turns[0] = turns[0].model_copy(update={"user_text": user_text})
        cases.append(
            (
                name,
                turns,
                _production_l1_payload(),
                "operator_cue_negated",
            )
        )

    for name, turns, payload, validation_code in cases:
        repository = tmp_path / f"{name}-memory-history.git"
        result_path = tmp_path / f"{name}-result.json"
        response = _chat_response(payload)
        with pytest.raises(ModelBoundaryError, match="l1") as captured:
            run_openai_e2e(
                turns=turns,
                question="What beverage is preferred?",
                repository_path=repository,
                result_path=result_path,
                base_url="https://model.invalid/v1",
                api_key="credential-that-must-not-leak",
                model="test-model",
                opener=_SequencedOpener([response]),
            )
        message = str(captured.value)
        assert "reason=candidate_grounding" in message
        assert f"validation_code={validation_code}" in message
        assert f"response_sha256={hashlib.sha256(response).hexdigest()}" in message
        assert "credential-that-must-not-leak" not in message
        assert not repository.exists()
        assert not repository.with_name(f"{repository.name}.raw.json").exists()
        assert not result_path.exists()


def test_l2_claim_requires_admitted_l1_semantic_support(tmp_path: Path) -> None:
    turns = _turns()
    turns[0] = turns[0].model_copy(
        update={"user_text": "Coffee is drunk daily."}
    )
    l1_payload = _production_l1_payload()
    first_candidate = l1_payload["proposals"][0]["typed_candidate"]
    first_candidate["kind"] = "event"
    first_candidate["predicate"] = {
        "surface": "drink",
        "sense": "consume_beverage",
        "canonical_operator": "drink",
    }
    repository = tmp_path / "unsupported-l2-memory-history.git"
    result_path = tmp_path / "unsupported-l2-result.json"
    with pytest.raises(ModelBoundaryError, match="l2") as captured:
        run_openai_e2e(
            turns=turns,
            question="What beverage is preferred?",
            repository_path=repository,
            result_path=result_path,
            base_url="https://model.invalid/v1",
            api_key="credential-that-must-not-leak",
            model="test-model",
            opener=_SequencedOpener(
                [
                    _chat_response(l1_payload),
                    _chat_response(_production_l2_payload()),
                ]
            ),
        )
    message = str(captured.value)
    assert "reason=candidate_grounding" in message
    assert "validation_code=claim_predicate_without_support" in message
    assert "credential-that-must-not-leak" not in message
    assert not repository.exists()
    assert not result_path.exists()

    unsupported_summary = _production_l2_payload()
    unsupported_summary["typed_candidate"]["summary"] = "Coffee is avoided."
    summary_repository = tmp_path / "unsupported-summary-memory-history.git"
    summary_result = tmp_path / "unsupported-summary-result.json"
    with pytest.raises(ModelBoundaryError, match="l2") as captured:
        run_openai_e2e(
            turns=_turns(),
            question="What beverage is preferred?",
            repository_path=summary_repository,
            result_path=summary_result,
            base_url="https://model.invalid/v1",
            api_key="credential-that-must-not-leak",
            model="test-model",
            opener=_SequencedOpener(
                [
                    _chat_response(_production_l1_payload()),
                    _chat_response(unsupported_summary),
                ]
            ),
        )
    message = str(captured.value)
    assert "reason=candidate_grounding" in message
    assert "validation_code=summary_operator_cue_missing" in message
    assert "credential-that-must-not-leak" not in message
    assert not summary_result.exists()

    negated_summary = _production_l2_payload()
    negated_summary["typed_candidate"]["summary"] = "Coffee is not preferred."
    negated_repository = tmp_path / "negated-summary-memory-history.git"
    negated_result = tmp_path / "negated-summary-result.json"
    with pytest.raises(ModelBoundaryError, match="l2") as captured:
        run_openai_e2e(
            turns=_turns(),
            question="What beverage is preferred?",
            repository_path=negated_repository,
            result_path=negated_result,
            base_url="https://model.invalid/v1",
            api_key="credential-that-must-not-leak",
            model="test-model",
            opener=_SequencedOpener(
                [
                    _chat_response(_production_l1_payload()),
                    _chat_response(negated_summary),
                ]
            ),
        )
    message = str(captured.value)
    assert "reason=candidate_grounding" in message
    assert "validation_code=summary_operator_cue_negated" in message
    assert "credential-that-must-not-leak" not in message
    assert not negated_result.exists()

    post_negated_summary = _production_l2_payload()
    post_negated_summary["typed_candidate"]["summary"] = (
        "Coffee is preferred, but not anymore."
    )
    post_negated_result = tmp_path / "post-negated-summary-result.json"
    with pytest.raises(ModelBoundaryError, match="l2") as captured:
        run_openai_e2e(
            turns=_turns(),
            question="What beverage is preferred?",
            repository_path=tmp_path / "post-negated-summary-memory-history.git",
            result_path=post_negated_result,
            base_url="https://model.invalid/v1",
            api_key="credential-that-must-not-leak",
            model="test-model",
            opener=_SequencedOpener(
                [
                    _chat_response(_production_l1_payload()),
                    _chat_response(post_negated_summary),
                ]
            ),
        )
    message = str(captured.value)
    assert "validation_code=summary_operator_cue_negated" in message
    assert "credential-that-must-not-leak" not in message
    assert not post_negated_result.exists()


def test_without_modifier_does_not_negate_positive_preference(
    tmp_path: Path,
) -> None:
    turns = _turns()
    turns[0] = turns[0].model_copy(
        update={"user_text": "Coffee without sugar is preferred."}
    )
    l2_payload = _production_l2_payload()
    l2_payload["typed_candidate"]["summary"] = (
        "Coffee without sugar is preferred."
    )
    outcome = run_openai_e2e(
        turns=turns,
        question="What beverage is preferred?",
        repository_path=tmp_path / "without-modifier-memory-history.git",
        result_path=tmp_path / "without-modifier-result.json",
        base_url="https://model.invalid/v1",
        api_key="credential-that-must-not-leak",
        model="test-model",
        opener=_SequencedOpener(
            [
                _chat_response(_production_l1_payload()),
                _chat_response(l2_payload),
                _chat_response(_production_query_payload()),
            ]
        ),
    )

    assert outcome.pipeline.snapshot.verification_status == "valid"
    assert outcome.pipeline.execution.answer_values == ("memory:CoffeeBeverage",)


def test_query_response_without_model_is_rejected_without_result(tmp_path: Path) -> None:
    repository = tmp_path / "missing-model-memory-history.git"
    result_path = tmp_path / "missing-model-result.json"
    with pytest.raises(QueryDraftProductionError):
        run_openai_e2e(
            turns=_turns(),
            question="What beverage is preferred?",
            repository_path=repository,
            result_path=result_path,
            base_url="https://model.invalid/v1",
            api_key="credential-that-must-not-leak",
            model="test-model",
            opener=_SequencedOpener(
                [
                    _chat_response(_production_l1_payload()),
                    _chat_response(_production_l2_payload()),
                    _chat_response(_production_query_payload(), include_model=False),
                ]
            ),
        )
    assert not result_path.exists()


def test_minimal_pipeline_closes_memory_query_and_evidence(tmp_path: Path) -> None:
    result = run_e2e_pipeline(
        turns=_turns(),
        l1_producer=_L1Producer(),
        l2_producer=_L2Producer(),
        query_producer=_QueryProducer(),
        repository_path=tmp_path / "memory-history.git",
        question="What beverage is preferred?",
    )

    assert result.snapshot.verification_status == "valid"
    assert result.execution.abstained is False
    assert result.execution.answer_values == ("memory:CoffeeBeverage",)
    assert result.execution.closure_complete is True
    assert result.answer.fallback_triggered is False
    assert {span.text for span in result.answer.evidence_spans} == {
        "Coffee is preferred.",
        "Coffee is drunk regularly.",
    }
    assert result.answer.authority_sha256 == result.execution.authority.authority_sha256
    memberships = [
        revision_id
        for bundle in result.turn_bundles
        for revision_id in bundle.l1_unit_revision_ids
    ]
    assert len(memberships) == len(set(memberships)) == 2


def test_pipeline_rejects_identity_bearing_l1_candidate(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="category-only"):
        run_e2e_pipeline(
            turns=_turns(),
            l1_producer=_L1Producer(entity_surface="this coffee cup"),
            l2_producer=_L2Producer(),
            query_producer=_QueryProducer(),
            repository_path=tmp_path / "memory-history.git",
            question="What beverage is preferred?",
        )
