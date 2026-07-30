from __future__ import annotations

from pathlib import Path

import pytest

from tools.natural_memory_benchmark.e2e_pipeline import (
    ProposedL1CandidateV1,
    ProposedL2CandidateV1,
    RawTurnV1,
    TurnExtractionInputV1,
    run_e2e_pipeline,
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
