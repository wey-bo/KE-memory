from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from tools.natural_memory_benchmark.query_compiler_v2 import (
    AnswerDraftV1,
    CompiledQueryPlanV2,
    CompilerRegistryV1,
    GitMemoryViewRefV1,
    PredicateRegistryEntryV1,
    QueryAtomDraftV1,
    QueryContextV1,
    QueryDraftProducer,
    QueryDraftRequestV1,
    QueryDraftV1,
    QueryPatternGroupDraftV1,
    QueryRoleDraftV1,
    QueryTermDraftV1,
    QueryTimeConstraintV1,
    compile_natural_query,
    compile_query_draft,
    lower_to_authoritative_query_plan,
    _plan_hash,
)


def _context() -> QueryContextV1:
    return QueryContextV1(
        query_id="query-001",
        raw_query="Which project do I lead?",
        query_time="2026-07-28T10:00:00Z",
        current_user_entity_id="entity-user",
        memory_view=GitMemoryViewRefV1(
            workspace_id="workspace-main",
            repository_epoch_id="epoch-001",
            checkpoint_id="checkpoint-0007",
            git_commit="a" * 40,
            authoritative_ref="refs/heads/authoritative",
        ),
        ontology_revision="ontology-v7",
        identity_revision="identity-v4",
        compiler_policy_revision="query-policy-v1",
    )


def test_git_memory_view_accepts_sha256_object_id() -> None:
    view = GitMemoryViewRefV1(
        workspace_id="workspace-main",
        repository_epoch_id="epoch-001",
        checkpoint_id="checkpoint-0007",
        git_commit="b" * 64,
        authoritative_ref="refs/heads/authoritative",
    )

    assert view.git_commit == "b" * 64


def _registry() -> CompilerRegistryV1:
    return CompilerRegistryV1(
        ontology_revision="ontology-v7",
        identity_revision="identity-v4",
        registry_revision="registry-v1",
        entity_aliases={
            "i": ["entity-user"],
            "me": ["entity-user"],
            "archive": ["entity-archive"],
        },
        entity_types={
            "entity-user": ["Person"],
            "entity-archive": ["Archive"],
        },
        identity_status={
            "entity-user": "resolved",
            "entity-archive": "resolved",
        },
        predicate_aliases={
            "lead": [
                PredicateRegistryEntryV1(
                    sense="lead/manage",
                    canonical_operator="manage",
                    role_types={"agent": "Person", "theme": "Project"},
                )
            ],
            "linked": [
                PredicateRegistryEntryV1(
                    sense="link/connect",
                    canonical_operator="linked_to",
                    role_types={"source": "Archive", "target": "Project"},
                )
            ],
        },
    )


def _registry_with_updates(**updates: object) -> CompilerRegistryV1:
    payload = _registry().model_dump(
        mode="json",
        exclude={"registry_sha256"},
    )
    payload.update(updates)
    return CompilerRegistryV1.model_validate(payload)


def _term(kind: str, value: str, *, expected_type: str | None = None) -> QueryTermDraftV1:
    return QueryTermDraftV1(
        kind=kind,
        value=value,
        expected_type=expected_type,
    )


def _lead_atom(*, atom_id: str = "atom-lead") -> QueryAtomDraftV1:
    return QueryAtomDraftV1(
        atom_id=atom_id,
        predicate_surface="lead",
        roles=[
            QueryRoleDraftV1(
                role="agent",
                role_name="ARG0",
                term=_term("entity_surface", "i", expected_type="Person"),
            ),
            QueryRoleDraftV1(
                role="theme",
                role_name="ARG1",
                term=_term("variable", "?project", expected_type="Project"),
            ),
        ],
    )


def _draft(
    *,
    answer_kind: str = "fact",
    distinct_by: str | None = None,
    atoms: list[QueryAtomDraftV1] | None = None,
    time_constraints: list[QueryTimeConstraintV1] | None = None,
    lifecycle: str | None = None,
    evidence_policy: str = "provenance_closure",
    explicit_absence_requested: bool = False,
) -> QueryDraftV1:
    return QueryDraftV1(
        query_id="query-001",
        intent="fact_lookup",
        target_level="both",
        answer=AnswerDraftV1(
            kind=answer_kind,
            variable="?project",
            distinct_by=distinct_by,
        ),
        pattern_groups=[
            QueryPatternGroupDraftV1(
                group_id="group-1",
                atoms=atoms or [_lead_atom()],
            )
        ],
        time_constraints=time_constraints or [],
        lifecycle=lifecycle,
        source_status_constraints=["user_reported", "tool_observed"],
        conflict_policy="require_resolved",
        supersession_policy="current_only",
        evidence_policy=evidence_policy,
        explicit_absence_requested=explicit_absence_requested,
        producer_id="test-producer",
        producer_version="1",
    )


def test_compiles_closed_plan_with_version_bindings_and_deterministic_hash() -> None:
    first = compile_query_draft(_draft(), _context(), _registry())
    second = compile_query_draft(_draft(), _context(), _registry())

    assert first.status == "executable"
    assert first.plan is not None
    assert first.plan.memory_view.repository_epoch_id == "epoch-001"
    assert first.plan.memory_view.checkpoint_id == "checkpoint-0007"
    assert first.plan.memory_view.git_commit == "a" * 40
    assert first.plan.ontology_revision == "ontology-v7"
    assert first.plan.identity_revision == "identity-v4"
    assert first.plan.compiler_policy_revision == "query-policy-v1"
    assert first.plan.registry_sha256 == _registry().registry_sha256
    assert first.plan.plan_sha256 == second.plan.plan_sha256
    assert len(first.plan.plan_sha256) == 64
    assert first.plan.pattern_groups[0].atoms[0].predicate_sense == "lead/manage"
    assert first.plan.pattern_groups[0].atoms[0].roles[0].term.value == "entity-user"
    assert first.plan.model_validate(first.plan.model_dump()) == first.plan


def test_registry_content_hash_rejects_content_tampering() -> None:
    payload = _registry().model_dump(mode="json")
    payload["entity_aliases"]["i"] = ["entity-other"]

    with pytest.raises(ValidationError, match="compiler registry hash mismatch"):
        CompilerRegistryV1.model_validate(payload)


def test_compiled_plan_binds_identity_snapshot_content() -> None:
    payload = _registry().model_dump(
        mode="json",
        exclude={"registry_sha256"},
    )
    payload.update(
        {
            "identity_snapshot_id": "identity-snapshot-7",
            "identity_input_fingerprint": "b" * 64,
        }
    )
    registry = CompilerRegistryV1.model_validate(payload)

    result = compile_query_draft(_draft(), _context(), registry)

    assert result.plan is not None
    assert result.plan.identity_snapshot_id == "identity-snapshot-7"
    assert result.plan.identity_input_fingerprint == "b" * 64
    assert result.plan.registry_sha256 == registry.registry_sha256


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("ontology_revision", "ontology-other", "ontology revision"),
        ("identity_revision", "identity-other", "identity revision"),
    ],
)
def test_compiler_rejects_context_registry_revision_mismatch(
    field: str,
    value: str,
    message: str,
) -> None:
    registry = _registry_with_updates(**{field: value})

    with pytest.raises(ValueError, match=message):
        compile_query_draft(_draft(), _context(), registry)


def test_contracts_are_strict_and_reject_extra_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        QueryContextV1.model_validate({**_context().model_dump(), "unexpected": True})


def test_compiled_plan_rejects_content_tampering_with_stale_hash() -> None:
    result = compile_query_draft(_draft(), _context(), _registry())
    assert result.plan is not None
    payload = result.plan.model_dump()
    payload["ontology_revision"] = "ontology-tampered"

    with pytest.raises(ValidationError, match="compiled query plan hash mismatch"):
        type(result.plan).model_validate(payload)


def test_unresolved_predicate_allows_only_lexical_fallback() -> None:
    unknown = _lead_atom().model_copy(update={"predicate_surface": "spearhead"})
    result = compile_query_draft(_draft(atoms=[unknown]), _context(), _registry())

    assert result.status == "abstain"
    assert result.plan is None
    assert result.fallback_allowed is True
    assert result.fallback_reason == "lexical_predicate_missing_link"
    assert "predicate:atom-lead" in result.unresolved_slots


def test_ambiguous_entity_is_not_resolved_by_the_producer() -> None:
    registry = _registry_with_updates(
        entity_aliases={
            **_registry().entity_aliases,
            "i": ["entity-user", "entity-other"],
        },
        entity_types={
            **_registry().entity_types,
            "entity-other": ["Person"],
        },
        identity_status={
            **_registry().identity_status,
            "entity-other": "resolved",
        },
    )
    result = compile_query_draft(_draft(), _context(), registry)

    assert result.status == "abstain"
    assert result.fallback_allowed is True
    assert result.fallback_reason == "unresolved_entity"
    assert "entity:atom-lead:agent" in result.unresolved_slots


def test_role_type_mismatch_blocks_without_embedding_fallback() -> None:
    bad_role = QueryRoleDraftV1(
        role="agent",
        role_name="ARG0",
        term=_term("entity_surface", "archive", expected_type="Archive"),
    )
    atom = _lead_atom().model_copy(
        update={"roles": [bad_role, _lead_atom().roles[1]]}
    )
    result = compile_query_draft(_draft(atoms=[atom]), _context(), _registry())

    assert result.status == "abstain"
    assert result.fallback_allowed is False
    assert "role_type_mismatch:atom-lead:agent" in result.blocked_reasons


def test_count_requires_canonical_identity_distinctness() -> None:
    rejected = compile_query_draft(
        _draft(answer_kind="count"),
        _context(),
        _registry(),
    )
    accepted = compile_query_draft(
        _draft(answer_kind="count", distinct_by="canonical_identity"),
        _context(),
        _registry(),
    )

    assert rejected.status == "abstain"
    assert rejected.fallback_allowed is False
    assert "count_requires_canonical_identity" in rejected.blocked_reasons
    assert accepted.status == "executable"
    assert accepted.plan is not None
    assert accepted.plan.answer.distinct_by == "canonical_identity"
    assert accepted.plan.answer.identity_resolution_required is True


def test_latest_requires_valid_time_ordering_and_active_lifecycle() -> None:
    missing = compile_query_draft(
        _draft(lifecycle="active"),
        _context().model_copy(update={"raw_query": "Which project do I lead currently?"}),
        _registry(),
    )
    accepted = compile_query_draft(
        _draft(
            lifecycle="active",
            time_constraints=[
                QueryTimeConstraintV1(
                    field="valid_time",
                    operator="latest",
                )
            ],
        ),
        _context().model_copy(update={"raw_query": "Which project do I lead currently?"}),
        _registry(),
    )

    assert missing.status == "abstain"
    assert "current_query_requires_valid_time_latest" in missing.blocked_reasons
    assert accepted.status == "executable"


def test_explicit_absence_requires_explicit_absence_evidence_policy() -> None:
    rejected = compile_query_draft(
        _draft(explicit_absence_requested=True),
        _context(),
        _registry(),
    )
    closed_but_unimplemented = compile_query_draft(
        _draft(
            evidence_policy="require_explicit_absence",
            explicit_absence_requested=True,
        ),
        _context(),
        _registry(),
    )

    assert rejected.status == "abstain"
    assert rejected.fallback_allowed is False
    assert "explicit_absence_requires_closure" in rejected.blocked_reasons
    assert closed_but_unimplemented.status == "abstain"
    assert closed_but_unimplemented.fallback_allowed is False
    assert (
        "explicit_absence_execution_unsupported"
        in closed_but_unimplemented.blocked_reasons
    )


def test_literal_terms_are_blocked_until_execution_has_a_typed_literal_carrier() -> None:
    literal_theme = QueryRoleDraftV1(
        role="theme",
        role_name="ARG1",
        term=_term("literal", "Project Alpha", expected_type="Project"),
    )
    atom = _lead_atom().model_copy(
        update={"roles": [_lead_atom().roles[0], literal_theme]}
    )

    result = compile_query_draft(_draft(atoms=[atom]), _context(), _registry())

    assert result.status == "abstain"
    assert result.fallback_allowed is False
    assert "literal_execution_unsupported" in result.blocked_reasons


@pytest.mark.parametrize("operator", ["before", "after", "between", "as_of"])
def test_unimplemented_time_operators_are_blocked_at_compile_time(
    operator: str,
) -> None:
    result = compile_query_draft(
        _draft(
            time_constraints=[
                QueryTimeConstraintV1(
                    field="valid_time",
                    operator=operator,
                    value="2026-07-01",
                )
            ]
        ),
        _context(),
        _registry(),
    )

    assert result.status == "abstain"
    assert result.fallback_allowed is False
    assert f"time_operator_execution_unsupported:{operator}" in result.blocked_reasons


def test_multiple_latest_constraints_are_blocked_at_compile_time() -> None:
    result = compile_query_draft(
        _draft(
            time_constraints=[
                QueryTimeConstraintV1(field="event_time", operator="latest"),
                QueryTimeConstraintV1(field="valid_time", operator="latest"),
            ]
        ),
        _context(),
        _registry(),
    )

    assert result.status == "abstain"
    assert result.fallback_allowed is False
    assert "multiple_latest_constraints_unsupported" in result.blocked_reasons


@pytest.mark.parametrize("answer_kind", ["evidence_set", "polarity", "entity_list"])
def test_unimplemented_answer_kinds_are_blocked_at_compile_time(
    answer_kind: str,
) -> None:
    result = compile_query_draft(
        _draft(answer_kind=answer_kind),
        _context(),
        _registry(),
    )

    assert result.status == "abstain"
    assert result.fallback_allowed is False
    assert f"answer_kind_execution_unsupported:{answer_kind}" in result.blocked_reasons


def test_multihop_time_scope_is_blocked_until_constraints_bind_to_atoms() -> None:
    linked = QueryAtomDraftV1(
        atom_id="atom-linked",
        predicate_surface="linked",
        roles=[
            QueryRoleDraftV1(
                role="source",
                role_name="ARG1",
                term=_term("entity_surface", "archive", expected_type="Archive"),
            ),
            QueryRoleDraftV1(
                role="target",
                role_name="ARG2",
                term=_term("variable", "?project", expected_type="Project"),
            ),
        ],
    )
    result = compile_query_draft(
        _draft(
            atoms=[_lead_atom(), linked],
            time_constraints=[
                QueryTimeConstraintV1(
                    field="valid_time",
                    operator="exact",
                    value="2026-07-01",
                )
            ],
        ),
        _context(),
        _registry(),
    )

    assert result.status == "abstain"
    assert result.fallback_allowed is False
    assert "multi_atom_time_scope_unsupported" in result.blocked_reasons


def test_disconnected_multihop_variable_is_rejected() -> None:
    linked = QueryAtomDraftV1(
        atom_id="atom-linked",
        predicate_surface="linked",
        roles=[
            QueryRoleDraftV1(
                role="source",
                role_name="ARG1",
                term=_term("entity_surface", "archive", expected_type="Archive"),
            ),
            QueryRoleDraftV1(
                role="target",
                role_name="ARG2",
                term=_term("variable", "?unjoined", expected_type="Project"),
            ),
        ],
    )
    result = compile_query_draft(
        _draft(atoms=[_lead_atom(), linked]),
        _context(),
        _registry(),
    )

    assert result.status == "abstain"
    assert result.fallback_allowed is False
    assert "disconnected_variable:?unjoined" in result.blocked_reasons


def test_simple_plan_lowers_to_existing_authoritative_query_contract() -> None:
    result = compile_query_draft(_draft(), _context(), _registry())
    assert result.plan is not None

    lowered = lower_to_authoritative_query_plan(result.plan)

    assert lowered.query_id == "query-001"
    assert lowered.answer_kind == "fact"
    assert lowered.predicate_sense == "lead/manage"
    assert lowered.canonical_operator == "manage"
    assert [role.entity_id for role in lowered.role_constraints] == ["entity-user"]
    assert lowered.source_status_constraints == ["user_reported", "tool_observed"]
    assert lowered.fallback_allowed_reasons == [
        "unresolved_entity",
        "lexical_predicate_missing_link",
    ]


def test_v1_lowering_rejects_literal_terms_instead_of_dropping_them() -> None:
    result = compile_query_draft(_draft(), _context(), _registry())
    assert result.plan is not None
    payload = result.plan.model_dump(mode="json", exclude={"plan_sha256"})
    payload["pattern_groups"][0]["atoms"][0]["roles"][1]["term"].update(
        {"kind": "literal", "value": "Project Alpha"}
    )
    literal_plan = CompiledQueryPlanV2(
        **payload,
        plan_sha256=_plan_hash(payload),
    )

    with pytest.raises(ValueError, match="literal"):
        lower_to_authoritative_query_plan(literal_plan)


def test_or_and_multihop_plans_refuse_lossy_v1_lowering() -> None:
    second_group = QueryPatternGroupDraftV1(
        group_id="group-2",
        atoms=[_lead_atom(atom_id="atom-lead-2")],
    )
    draft = _draft().model_copy(
        update={"pattern_groups": [*_draft().pattern_groups, second_group]}
    )
    result = compile_query_draft(draft, _context(), _registry())
    assert result.plan is not None

    with pytest.raises(ValueError, match="cannot lower"):
        lower_to_authoritative_query_plan(result.plan)


def test_or_requires_answer_variable_bound_in_every_branch() -> None:
    second_group = QueryPatternGroupDraftV1(
        group_id="group-2",
        atoms=[
            QueryAtomDraftV1(
                atom_id="atom-linked-only",
                predicate_surface="linked",
                roles=[
                    QueryRoleDraftV1(
                        role="source",
                        role_name="ARG1",
                        term=_term(
                            "entity_surface",
                            "archive",
                            expected_type="Archive",
                        ),
                    ),
                    QueryRoleDraftV1(
                        role="target",
                        role_name="ARG2",
                        term=_term(
                            "variable",
                            "?other",
                            expected_type="Project",
                        ),
                    ),
                ],
            )
        ],
    )
    result = compile_query_draft(
        _draft().model_copy(
            update={"pattern_groups": [*_draft().pattern_groups, second_group]}
        ),
        _context(),
        _registry(),
    )

    assert result.status == "abstain"
    assert result.fallback_allowed is False
    assert "answer_variable_unbound:group-2:?project" in result.blocked_reasons


def test_generic_count_plan_refuses_v1_aggregate_lowering() -> None:
    result = compile_query_draft(
        _draft(answer_kind="count", distinct_by="canonical_identity"),
        _context(),
        _registry(),
    )
    assert result.plan is not None

    with pytest.raises(ValueError, match="cannot lower generic count"):
        lower_to_authoritative_query_plan(result.plan)


class _Producer(QueryDraftProducer):
    received: QueryDraftRequestV1 | None = None

    def produce(self, request: QueryDraftRequestV1) -> QueryDraftV1:
        self.received = request
        return _draft()


def test_natural_query_entry_point_keeps_producer_non_authoritative() -> None:
    producer = _Producer()
    result = compile_natural_query(
        question="Which project do I lead?",
        context=_context(),
        registry=_registry(),
        producer=producer,
    )

    assert result.status == "executable"
    assert producer.received is not None
    assert producer.received.raw_query == "Which project do I lead?"
    assert producer.received.compiler_policy_revision == "query-policy-v1"
    assert "entity_aliases" not in producer.received.model_dump()
    assert result.plan is not None
    assert result.plan.pattern_groups[0].atoms[0].roles[0].term.value == "entity-user"


def test_producer_request_contract_rejects_authority_injection() -> None:
    payload: dict[str, Any] = {
        "raw_query": "Which project do I lead?",
        "query_id": "query-001",
        "query_time": "2026-07-28T10:00:00Z",
        "current_user_surface": "I",
        "compiler_policy_revision": "query-policy-v1",
        "authoritative_entity_ids": ["entity-user"],
    }

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        QueryDraftRequestV1.model_validate(payload)
