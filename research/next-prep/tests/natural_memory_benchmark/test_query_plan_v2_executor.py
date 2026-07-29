from __future__ import annotations

import pytest
from pydantic import ValidationError

from tools.natural_memory_benchmark import query_plan_v2_executor
from tools.natural_memory_benchmark.query_compiler_v2 import (
    AnswerDraftV1,
    CompilerRegistryV1,
    GitMemoryViewRefV1,
    PredicateRegistryEntryV1,
    QueryAtomDraftV1,
    QueryContextV1,
    QueryDraftV1,
    QueryPatternGroupDraftV1,
    QueryRoleDraftV1,
    QueryTermDraftV1,
    QueryTimeConstraintV1,
    compile_query_draft,
)
from tools.natural_memory_benchmark.query_plan_v2_executor import (
    ExecutionFactProvenanceV1,
    ExecutionRoleBindingV1,
    ExecutionTimeV1,
    QueryExecutionFactV1,
    QueryExecutionSnapshotV1,
    QuerySnapshotEvaluationV1,
    _evaluate_compiled_query_snapshot,
)


def _memory_view(commit: str = "a" * 40) -> GitMemoryViewRefV1:
    return GitMemoryViewRefV1(
        workspace_id="workspace-main",
        repository_epoch_id="epoch-001",
        checkpoint_id="checkpoint-0007",
        git_commit=commit,
        authoritative_ref="refs/heads/authoritative",
    )


def _context(*, raw_query: str = "Which project do I lead?") -> QueryContextV1:
    return QueryContextV1(
        query_id="query-001",
        raw_query=raw_query,
        query_time="2026-07-28T10:00:00Z",
        current_user_entity_id="entity-user",
        memory_view=_memory_view(),
        ontology_revision="ontology-v7",
        identity_revision="identity-v4",
        compiler_policy_revision="query-policy-v1",
    )


def _registry() -> CompilerRegistryV1:
    return CompilerRegistryV1(
        ontology_revision="ontology-v7",
        identity_revision="identity-v4",
        registry_revision="registry-v1",
        entity_aliases={
            "i": ["entity-user"],
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


def _term(kind: str, value: str, expected_type: str) -> QueryTermDraftV1:
    return QueryTermDraftV1(
        kind=kind,
        value=value,
        expected_type=expected_type,
    )


def _lead_atom(atom_id: str = "lead") -> QueryAtomDraftV1:
    return QueryAtomDraftV1(
        atom_id=atom_id,
        predicate_surface="lead",
        roles=[
            QueryRoleDraftV1(
                role="agent",
                role_name="ARG0",
                term=_term("entity_surface", "i", "Person"),
            ),
            QueryRoleDraftV1(
                role="theme",
                role_name="ARG1",
                term=_term("variable", "?project", "Project"),
            ),
        ],
    )


def _linked_atom(atom_id: str = "linked") -> QueryAtomDraftV1:
    return QueryAtomDraftV1(
        atom_id=atom_id,
        predicate_surface="linked",
        roles=[
            QueryRoleDraftV1(
                role="source",
                role_name="ARG1",
                term=_term("entity_surface", "archive", "Archive"),
            ),
            QueryRoleDraftV1(
                role="target",
                role_name="ARG2",
                term=_term("variable", "?project", "Project"),
            ),
        ],
    )


def _plan(
    *,
    groups: list[QueryPatternGroupDraftV1] | None = None,
    answer_kind: str = "fact",
    raw_query: str = "Which project do I lead?",
    latest: bool = False,
    evidence_policy: str = "provenance_closure",
    explicit_absence_requested: bool = False,
):
    draft = QueryDraftV1(
        query_id="query-001",
        intent="temporal_latest" if latest else "fact_lookup",
        target_level="both",
        answer=AnswerDraftV1(
            kind=answer_kind,
            variable="?project",
            distinct_by="canonical_identity" if answer_kind == "count" else None,
        ),
        pattern_groups=groups
        or [QueryPatternGroupDraftV1(group_id="group-1", atoms=[_lead_atom()])],
        time_constraints=[
            QueryTimeConstraintV1(field="valid_time", operator="latest")
        ]
        if latest
        else [],
        lifecycle="active" if latest else None,
        source_status_constraints=["user_reported", "tool_observed"],
        conflict_policy="require_resolved",
        supersession_policy="current_only",
        evidence_policy=evidence_policy,
        explicit_absence_requested=explicit_absence_requested,
        producer_id="test-producer",
        producer_version="1",
    )
    result = compile_query_draft(
        draft,
        _context(raw_query=raw_query),
        _registry(),
    )
    assert result.plan is not None
    return result.plan


def _fact(
    fact_id: str,
    *,
    sense: str,
    operator: str,
    roles: list[ExecutionRoleBindingV1],
    valid_time: str | None = "2026-07-01",
    evidence_ids: list[str] | None = None,
) -> QueryExecutionFactV1:
    return QueryExecutionFactV1(
        fact_id=fact_id,
        unit_id=f"unit-{fact_id}",
        level="L1",
        predicate_sense=sense,
        canonical_operator=operator,
        roles=roles,
        modality="actual",
        polarity="positive",
        time=ExecutionTimeV1(valid_time=valid_time),
        source_status="user_reported",
        lifecycle="active",
        evidence_ids=evidence_ids if evidence_ids is not None else [f"e-{fact_id}"],
        provenance=ExecutionFactProvenanceV1(unit_revision_id=fact_id),
    )


def _lead_fact(
    fact_id: str,
    project: str,
    *,
    valid_time: str | None = "2026-07-01",
):
    return _fact(
        fact_id,
        sense="lead/manage",
        operator="manage",
        roles=[
            ExecutionRoleBindingV1(
                role="agent",
                role_name="ARG0",
                entity_id="entity-user",
            ),
            ExecutionRoleBindingV1(
                role="theme",
                role_name="ARG1",
                entity_id=project,
            ),
        ],
        valid_time=valid_time,
    )


def _linked_fact(fact_id: str, project: str):
    return _fact(
        fact_id,
        sense="link/connect",
        operator="linked_to",
        roles=[
            ExecutionRoleBindingV1(
                role="source",
                role_name="ARG1",
                entity_id="entity-archive",
            ),
            ExecutionRoleBindingV1(
                role="target",
                role_name="ARG2",
                entity_id=project,
            ),
        ],
    )


def _snapshot(
    facts: list[QueryExecutionFactV1],
    *,
    memory_view: GitMemoryViewRefV1 | None = None,
    identity_status: dict[str, str] | None = None,
    canonical_entity_ids: dict[str, str] | None = None,
    ontology_revision: str = "ontology-v7",
    identity_revision: str = "identity-v4",
    registry_revision: str = "registry-v1",
    registry_sha256: str | None = None,
) -> QueryExecutionSnapshotV1:
    return QueryExecutionSnapshotV1(
        bundle_id="bundle-query-executor-test",
        memory_view=memory_view or _memory_view(),
        ontology_revision=ontology_revision,
        identity_revision=identity_revision,
        registry_revision=registry_revision,
        registry_sha256=registry_sha256 or _registry().registry_sha256,
        facts=facts,
        identity_status=identity_status
        or {
            "project-a": "resolved",
            "project-b": "resolved",
            "project-c": "resolved",
        },
        canonical_entity_ids=canonical_entity_ids or {},
    )


def test_executor_rejects_mismatched_git_memory_view() -> None:
    result = _evaluate_compiled_query_snapshot(
        _plan(),
        _snapshot(
            [_lead_fact("lead-a", "project-a")],
            memory_view=_memory_view("b" * 40),
        ),
    )

    assert result.abstained is True
    assert result.reason == "memory_view_mismatch"
    assert result.answer_values == ()


def test_snapshot_executor_is_not_exposed_as_public_authoritative_entry() -> None:
    assert not hasattr(query_plan_v2_executor, "execute_compiled_query")


def test_low_level_snapshot_evaluation_has_no_authority_claim() -> None:
    evaluation = _evaluate_compiled_query_snapshot(
        _plan(),
        _snapshot([_lead_fact("lead-a", "project-a")]),
    )

    assert isinstance(evaluation, QuerySnapshotEvaluationV1)
    assert evaluation.closure_complete is True
    assert "memory_view" not in type(evaluation).model_fields
    assert "authority" not in type(evaluation).model_fields
    assert "authoritative_ready" not in type(evaluation).model_fields
    assert not hasattr(
        query_plan_v2_executor,
        "_execute_compiled_query_snapshot",
    )


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("ontology_revision", "ontology-other", "ontology_revision_mismatch"),
        ("identity_revision", "identity-other", "identity_revision_mismatch"),
        ("registry_revision", "registry-other", "registry_revision_mismatch"),
        ("registry_sha256", "f" * 64, "registry_hash_mismatch"),
    ],
)
def test_executor_rejects_revision_mismatch(
    field: str,
    value: str,
    reason: str,
) -> None:
    result = _evaluate_compiled_query_snapshot(
        _plan(),
        _snapshot(
            [_lead_fact("lead-a", "project-a")],
            **{field: value},
        ),
    )

    assert result.abstained is True
    assert result.reason == reason


def test_single_atom_projects_answer_and_evidence() -> None:
    result = _evaluate_compiled_query_snapshot(
        _plan(),
        _snapshot([_lead_fact("lead-a", "project-a")]),
    )

    assert result.abstained is False
    assert result.answer_values == ("project-a",)
    assert result.matched_fact_ids == ("lead-a",)
    assert result.required_evidence_ids == ("e-lead-a",)
    assert result.closure_complete is True


def test_two_atom_conjunction_joins_on_shared_variable() -> None:
    plan = _plan(
        groups=[
            QueryPatternGroupDraftV1(
                group_id="group-1",
                atoms=[_lead_atom(), _linked_atom()],
            )
        ]
    )
    result = _evaluate_compiled_query_snapshot(
        plan,
        _snapshot(
            [
                _lead_fact("lead-a", "project-a"),
                _lead_fact("lead-b", "project-b"),
                _linked_fact("linked-a", "project-a"),
            ]
        ),
    )

    assert result.abstained is False
    assert result.answer_values == ("project-a",)
    assert result.matched_fact_ids == ("lead-a", "linked-a")
    assert result.required_evidence_ids == ("e-lead-a", "e-linked-a")


def test_conjunction_can_reuse_one_fact_for_equivalent_atoms() -> None:
    plan = _plan(
        groups=[
            QueryPatternGroupDraftV1(
                group_id="group-1",
                atoms=[
                    _lead_atom(atom_id="lead-1"),
                    _lead_atom(atom_id="lead-2"),
                ],
            )
        ]
    )

    result = _evaluate_compiled_query_snapshot(
        plan,
        _snapshot([_lead_fact("lead-a", "project-a")]),
    )

    assert result.abstained is False
    assert result.answer_values == ("project-a",)
    assert result.matched_fact_ids == ("lead-a",)


def test_or_groups_union_answer_bindings_without_cross_branch_join() -> None:
    plan = _plan(
        groups=[
            QueryPatternGroupDraftV1(group_id="lead-group", atoms=[_lead_atom()]),
            QueryPatternGroupDraftV1(
                group_id="link-group",
                atoms=[_linked_atom()],
            ),
        ]
    )
    result = _evaluate_compiled_query_snapshot(
        plan,
        _snapshot(
            [
                _lead_fact("lead-a", "project-a"),
                _linked_fact("linked-b", "project-b"),
            ]
        ),
    )

    assert result.abstained is False
    assert result.answer_values == ("project-a", "project-b")
    assert result.matched_fact_ids == ("lead-a", "linked-b")


def test_count_distinct_abstains_when_any_answer_identity_is_unresolved() -> None:
    plan = _plan(answer_kind="count")
    facts = [
        _lead_fact("lead-a", "project-a"),
        _lead_fact("lead-b", "project-b"),
    ]
    blocked = _evaluate_compiled_query_snapshot(
        plan,
        _snapshot(
            facts,
            identity_status={"project-a": "resolved", "project-b": "unresolved"},
        ),
    )
    accepted = _evaluate_compiled_query_snapshot(plan, _snapshot(facts))

    assert blocked.abstained is True
    assert blocked.reason == "answer_identity_unresolved"
    assert blocked.count_value is None
    assert accepted.abstained is False
    assert accepted.count_value == 2


def test_count_distinct_uses_canonical_identity_not_raw_entity_id() -> None:
    plan = _plan(answer_kind="count")
    result = _evaluate_compiled_query_snapshot(
        plan,
        _snapshot(
            [
                _lead_fact("lead-a", "project-a-alias-1"),
                _lead_fact("lead-b", "project-a-alias-2"),
            ],
            identity_status={"project-a": "resolved"},
            canonical_entity_ids={
                "project-a-alias-1": "project-a",
                "project-a-alias-2": "project-a",
                "project-a": "project-a",
            },
        ),
    )

    assert result.abstained is False
    assert result.answer_values == ("project-a",)
    assert result.count_value == 1


def test_latest_uses_valid_time_and_abstains_on_tied_distinct_answers() -> None:
    plan = _plan(
        raw_query="Which project do I currently lead?",
        latest=True,
    )
    accepted = _evaluate_compiled_query_snapshot(
        plan,
        _snapshot(
            [
                _lead_fact("lead-a", "project-a", valid_time="2026-06-01"),
                _lead_fact("lead-b", "project-b", valid_time="2026-07-01"),
            ]
        ),
    )
    tied = _evaluate_compiled_query_snapshot(
        plan,
        _snapshot(
            [
                _lead_fact("lead-b", "project-b", valid_time="2026-07-01"),
                _lead_fact("lead-c", "project-c", valid_time="2026-07-01"),
            ]
        ),
    )

    assert accepted.abstained is False
    assert accepted.answer_values == ("project-b",)
    assert tied.abstained is True
    assert tied.reason == "latest_tie_unresolved"


def test_provenance_closure_rejects_matching_fact_without_evidence() -> None:
    fact = _lead_fact("lead-a", "project-a").model_copy(
        update={"evidence_ids": []}
    )
    result = _evaluate_compiled_query_snapshot(_plan(), _snapshot([fact]))

    assert result.abstained is True
    assert result.reason == "incomplete_evidence_closure"
    assert result.closure_complete is False


def test_conflicted_fact_causes_explicit_abstention() -> None:
    fact = _lead_fact("lead-a", "project-a").model_copy(
        update={"lifecycle": "conflicted"}
    )
    result = _evaluate_compiled_query_snapshot(_plan(), _snapshot([fact]))

    assert result.abstained is True
    assert result.reason == "conflict_unresolved"


def test_negative_query_requires_explicit_negative_fact() -> None:
    negative_atom = _lead_atom().model_copy(update={"polarity": "negative"})
    plan = _plan(
        groups=[
            QueryPatternGroupDraftV1(
                group_id="negative-group",
                atoms=[negative_atom],
            )
        ]
    )
    positive_only = _evaluate_compiled_query_snapshot(
        plan,
        _snapshot([_lead_fact("lead-a", "project-a")]),
    )
    negative_fact = _lead_fact("lead-negative", "project-a").model_copy(
        update={"polarity": "negative"}
    )
    explicit_negative = _evaluate_compiled_query_snapshot(
        plan,
        _snapshot([negative_fact]),
    )

    assert positive_only.abstained is True
    assert positive_only.reason == "no_matching_facts"
    assert explicit_negative.abstained is False
    assert explicit_negative.answer_values == ("project-a",)


def test_role_matching_uses_canonical_role_not_carrier_role_name() -> None:
    fact = _lead_fact("lead-a", "project-a")
    carrier_specific_roles = [
        fact.roles[0].model_copy(update={"role_name": "carrier-agent"}),
        fact.roles[1].model_copy(update={"role_name": "carrier-theme"}),
    ]

    result = _evaluate_compiled_query_snapshot(
        _plan(),
        _snapshot([fact.model_copy(update={"roles": carrier_specific_roles})]),
    )

    assert result.abstained is False
    assert result.answer_values == ("project-a",)


def test_execution_fact_rejects_duplicate_canonical_roles() -> None:
    fact = _lead_fact("lead-a", "project-a")
    payload = fact.model_dump(mode="json")
    payload["roles"].append(
        {
            **payload["roles"][0],
            "role_name": "carrier-agent-duplicate",
        }
    )

    with pytest.raises(ValidationError, match="roles must be unique"):
        QueryExecutionFactV1.model_validate(payload)


def test_execution_fact_requires_revision_provenance() -> None:
    payload = _lead_fact("lead-a", "project-a").model_dump(
        mode="json",
        exclude={"provenance"},
    )

    with pytest.raises(ValidationError):
        QueryExecutionFactV1.model_validate(payload)


def test_execution_snapshot_requires_authoritative_bundle_id() -> None:
    payload = _snapshot([_lead_fact("lead-a", "project-a")]).model_dump(
        mode="json",
        exclude={"bundle_id"},
    )

    with pytest.raises(ValidationError):
        QueryExecutionSnapshotV1.model_validate(payload)


def test_provenance_closure_rejects_fact_with_removed_provenance() -> None:
    fact = _lead_fact("lead-a", "project-a").model_copy(
        update={"provenance": None}
    )

    result = _evaluate_compiled_query_snapshot(_plan(), _snapshot([fact]))

    assert result.abstained is True
    assert result.reason == "unverified_fact_provenance"
    assert result.closure_complete is False


def test_latest_abstains_when_any_candidate_lacks_selected_time() -> None:
    plan = _plan(
        raw_query="Which project do I currently lead?",
        latest=True,
    )

    result = _evaluate_compiled_query_snapshot(
        plan,
        _snapshot(
            [
                _lead_fact("lead-a", "project-a", valid_time=None),
                _lead_fact("lead-b", "project-b", valid_time="2026-07-01"),
            ]
        ),
    )

    assert result.abstained is True
    assert result.reason == "latest_time_missing"


def test_latest_abstains_when_selected_time_is_not_iso_8601() -> None:
    plan = _plan(
        raw_query="Which project do I currently lead?",
        latest=True,
    )

    result = _evaluate_compiled_query_snapshot(
        plan,
        _snapshot(
            [
                _lead_fact("lead-a", "project-a", valid_time="not-a-time"),
                _lead_fact("lead-b", "project-b", valid_time="2026-07-01"),
            ]
        ),
    )

    assert result.abstained is True
    assert result.reason == "latest_time_invalid"


def test_explicit_absence_abstains_until_absence_closure_is_executable() -> None:
    plan = _plan().model_copy(
        update={
            "evidence_policy": "require_explicit_absence",
            "explicit_absence_requested": True,
        }
    )

    result = _evaluate_compiled_query_snapshot(
        plan,
        _snapshot([_lead_fact("lead-a", "project-a")]),
    )

    assert result.abstained is True
    assert result.reason == "explicit_absence_unsupported"


@pytest.mark.parametrize("answer_kind", ["evidence_set", "polarity", "entity_list"])
def test_snapshot_executor_fails_closed_for_unimplemented_answer_kinds(
    answer_kind: str,
) -> None:
    plan = _plan().model_copy(
        update={
            "answer": _plan().answer.model_copy(update={"kind": answer_kind}),
        }
    )

    result = _evaluate_compiled_query_snapshot(
        plan,
        _snapshot([_lead_fact("lead-a", "project-a")]),
    )

    assert result.abstained is True
    assert result.reason == "unsupported_answer_kind"


def test_snapshot_executor_fails_closed_for_literal_terms() -> None:
    plan = _plan()
    group = plan.pattern_groups[0]
    atom = group.atoms[0]
    literal_role = atom.roles[1].model_copy(
        update={
            "term": atom.roles[1].term.model_copy(
                update={"kind": "literal", "value": "Project Alpha"}
            )
        }
    )
    literal_plan = plan.model_copy(
        update={
            "pattern_groups": [
                group.model_copy(
                    update={
                        "atoms": [
                            atom.model_copy(
                                update={"roles": [atom.roles[0], literal_role]}
                            )
                        ]
                    }
                )
            ]
        }
    )

    result = _evaluate_compiled_query_snapshot(
        literal_plan,
        _snapshot([_lead_fact("lead-a", "project-a")]),
    )

    assert result.abstained is True
    assert result.reason == "literal_execution_unsupported"


def test_snapshot_executor_fails_closed_for_multihop_time_scope() -> None:
    plan = _plan(
        groups=[
            QueryPatternGroupDraftV1(
                group_id="group-1",
                atoms=[_lead_atom(), _linked_atom()],
            )
        ]
    ).model_copy(
        update={
            "time_constraints": [
                QueryTimeConstraintV1(
                    field="valid_time",
                    operator="exact",
                    value="2026-07-01",
                )
            ]
        }
    )

    result = _evaluate_compiled_query_snapshot(
        plan,
        _snapshot(
            [
                _lead_fact("lead-a", "project-a"),
                _linked_fact("linked-a", "project-a"),
            ]
        ),
    )

    assert result.abstained is True
    assert result.reason == "multi_atom_time_scope_unsupported"


def test_execution_result_is_independent_of_snapshot_fact_order() -> None:
    plan = _plan()
    facts = [
        _lead_fact("lead-b", "project-b"),
        _lead_fact("lead-a", "project-a"),
    ]

    forward = _evaluate_compiled_query_snapshot(plan, _snapshot(facts))
    reverse = _evaluate_compiled_query_snapshot(plan, _snapshot(list(reversed(facts))))

    assert forward == reverse
    assert forward.matched_fact_ids == ("lead-a", "lead-b")
    assert forward.required_evidence_ids == ("e-lead-a", "e-lead-b")
