from __future__ import annotations

import ctypes
import errno
import hashlib
import os
import shutil
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .query_compiler_v2 import (
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
)
from .query_compiler_v2_assessment import (
    QueryCompilerAuthorityCaseV1,
    QueryCompilerAuthorityDocumentV1,
    QueryCompilerGoldDocumentV1,
    QueryCompilerPublicCaseV1,
    QueryCompilerPublicDocumentV1,
    memory_view_handle,
)
from .io import canonical_json_bytes, load_json
from .query_compiler_v2_proposal_eval import (
    QueryDraftGoldDocumentV1,
    QueryDraftProposalArtifactManifestV1,
    QueryDraftProposalDocumentV1,
    QueryDraftProposalEvaluationV1,
    QueryDraftProposalProvenanceV1,
    QueryDraftRawProposalV1,
    QueryDraftValidationDocumentV1,
    evaluate_query_draft_proposals,
    freeze_query_draft_proposal_run,
    materialize_typed_query_proposals,
    validate_frozen_query_draft_proposal_run,
)
from .query_compiler_v2_assessment import QueryCompilerProposalDocumentV1


DATASET_ID = "query-proposer-dev-v1"
RUN_ID = "run-query-proposer-dev-v1-deterministic-reference-v2-provenance-v3"
REFERENCE_MODEL = "deterministic-query-draft-reference-v2"
SOURCE_KIND = "newly_authored_diagnostic_text"

EXPECTED_FAMILY_COUNTS = {
    "atomic_fact_role": 2,
    "entity_predicate_linking": 3,
    "temporal_lifecycle": 2,
    "epistemic_constraint": 2,
    "boolean_and_or": 2,
    "multihop": 3,
    "l2_evidence_closure": 3,
    "identity_aggregate": 3,
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class QueryProposerDevDatasetManifestV1(StrictModel):
    schema_version: Literal["query-proposer-dev-dataset-manifest-v1"] = (
        "query-proposer-dev-dataset-manifest-v1"
    )
    dataset_id: Literal[DATASET_ID] = DATASET_ID
    case_count: Literal[20] = 20
    family_counts: dict[str, int]
    expected_executable_count: int = Field(ge=0)
    expected_abstain_count: int = Field(ge=0)
    expected_critical_count: int = Field(ge=0)
    expected_allowed_fallback_count: int = Field(ge=0)
    source_allowlist: list[str]
    case_source_mapping: dict[str, str]
    typed_extractor_hidden_read: Literal[False] = False
    semantic_model_call_count: Literal[0] = 0
    deterministic_producer_emission_count: Literal[1] = 1
    gold_semantic_outcome_compiler_call_count: Literal[0] = 0
    gold_plan_hash_binding_compiler_batch_count: Literal[1] = 1
    artifact_build_gate_scoring_compiler_batch_count: Literal[1] = 1
    semantic_run_count: Literal[1] = 1
    semantic_run_count_interpretation: Literal[
        "single_deterministic_reference_emission_not_model_call"
    ] = "single_deterministic_reference_emission_not_model_call"
    natural_language_answer_generated: Literal[False] = False
    automatic_memory_write_count: Literal[0] = 0
    automatic_identity_write_count: Literal[0] = 0
    automatic_membership_write_count: Literal[0] = 0
    automatic_closure_write_count: Literal[0] = 0
    automatic_revision_write_count: Literal[0] = 0
    automatic_snapshot_write_count: Literal[0] = 0
    automatic_aggregate_write_count: Literal[0] = 0
    reference_is_harness_qualification_only: Literal[True] = True
    gold_oracle_source: Literal[
        "query_compiler_v2_dev_oracle_v2.json"
    ] = "query_compiler_v2_dev_oracle_v2.json"
    gold_oracle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_fixture_source: Literal[
        "query_compiler_v2_dev_reference_v3.json"
    ] = "query_compiler_v2_dev_reference_v3.json"
    reference_fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_fixture_authored_after_oracle_freeze: Literal[True] = True
    compiler_gold_binding_method: Literal[
        "independent_frozen_outcomes_with_prebound_plan_hashes"
    ] = "independent_frozen_outcomes_with_prebound_plan_hashes"
    canonical_local_id_policy: Literal[
        "group-N-and-atom-N-in-document-order"
    ] = "group-N-and-atom-N-in-document-order"
    future_semantic_run_requirement: Literal[
        "freeze_canonical_ids_or_add_alpha_normalized_compiler_gate"
    ] = "freeze_canonical_ids_or_add_alpha_normalized_compiler_gate"

    @model_validator(mode="after")
    def validate_claims(self) -> "QueryProposerDevDatasetManifestV1":
        if self.family_counts != EXPECTED_FAMILY_COUNTS:
            raise ValueError("dev family counts do not match the frozen matrix")
        if self.source_allowlist != [SOURCE_KIND]:
            raise ValueError("dev source allowlist must be exact")
        if len(self.case_source_mapping) != self.case_count:
            raise ValueError("dev source mapping must cover every case")
        if set(self.case_source_mapping.values()) != {SOURCE_KIND}:
            raise ValueError("dev source mapping contains an unapproved source")
        return self


class QueryProposerDevOracleAuthorshipV1(StrictModel):
    author_id: Literal["independent-dev-gold-author-v2"]
    authoring_method: Literal[
        "public-query-and-authority-registry-semantic-authoring"
    ]
    draft_producer_id: Literal["independent-dev-gold-author-v2"]
    draft_producer_version: Literal["2"]
    outcomes_frozen_before_compiler_plan_hash_binding: Literal[True]


class QueryProposerDevOracleIsolationV2(StrictModel):
    allowed_remote_reads: list[str] = Field(min_length=1)
    forbidden_remote_reads_respected: list[str] = Field(min_length=1)
    compiler_use_after_freeze: Literal[
        "deterministic executable plan hash binding only"
    ]
    natural_language_answer_generated: Literal[False]
    automatic_memory_write_count: Literal[0]
    reference_artifacts_read_before_freeze: Literal[False]
    compiler_used_to_author_semantic_outcomes: Literal[False]
    compiler_plan_hash_binding_after_outcome_freeze: Literal[True]
    compiler_plan_hash_binding_batch_count: Literal[1]


class QueryProposerDevOracleAdjudicationChangeV1(StrictModel):
    case_id: str = Field(pattern=r"^qc-[0-9a-f]{16}$")
    reason: str = Field(min_length=1)


class QueryProposerDevOracleAdjudicationV1(StrictModel):
    reviewer_id: Literal["primary-task6-semantic-audit-v1"]
    outcomes_refrozen_before_plan_hash_binding: Literal[True]
    changes: list[QueryProposerDevOracleAdjudicationChangeV1]

    @model_validator(mode="after")
    def validate_changes(self) -> "QueryProposerDevOracleAdjudicationV1":
        if {item.case_id for item in self.changes} != {
            "qc-0610ecc4acaf6f1f",
            "qc-832ed63bfbbd466a",
        }:
            raise ValueError("oracle semantic adjudication set differs")
        return self


class QueryProposerDevOracleV2(StrictModel):
    schema_version: Literal["query-compiler-independent-dev-oracle-v2"] = (
        "query-compiler-independent-dev-oracle-v2"
    )
    dataset_id: Literal[DATASET_ID] = DATASET_ID
    authorship: QueryProposerDevOracleAuthorshipV1
    isolation: QueryProposerDevOracleIsolationV2
    semantic_adjudication: QueryProposerDevOracleAdjudicationV1
    draft_gold_document: QueryDraftGoldDocumentV1
    compiler_gold_document: QueryCompilerGoldDocumentV1

    @property
    def draft_gold(self) -> QueryDraftGoldDocumentV1:
        return self.draft_gold_document

    @property
    def compiler_gold(self) -> QueryCompilerGoldDocumentV1:
        return self.compiler_gold_document

    @model_validator(mode="after")
    def validate_case_alignment(self) -> "QueryProposerDevOracleV2":
        if self.draft_gold.dataset_id != self.dataset_id:
            raise ValueError("draft gold dataset does not match oracle")
        if self.compiler_gold.dataset_id != self.dataset_id:
            raise ValueError("compiler gold dataset does not match oracle")
        draft_ids = [item.case_id for item in self.draft_gold.cases]
        compiler_ids = [item.case_id for item in self.compiler_gold.cases]
        if draft_ids != compiler_ids:
            raise ValueError("oracle draft and compiler case order differs")
        return self


class QueryProposerDevReferenceDraftV2(StrictModel):
    case_id: str = Field(pattern=r"^qc-[0-9a-f]{16}$")
    draft: QueryDraftV1

    @model_validator(mode="after")
    def validate_producer(self) -> "QueryProposerDevReferenceDraftV2":
        if self.draft.producer_id != REFERENCE_MODEL:
            raise ValueError("reference draft producer does not match reference model")
        if self.draft.producer_version != "2":
            raise ValueError("reference draft producer version differs")
        return self


class QueryProposerDevReferenceFixtureV3(StrictModel):
    schema_version: Literal["query-proposer-dev-reference-fixture-v3"] = (
        "query-proposer-dev-reference-fixture-v3"
    )
    dataset_id: Literal[DATASET_ID] = DATASET_ID
    authoring_method: Literal["post-freeze-known-good-harness-fixture"]
    authored_after_oracle_freeze: Literal[True]
    source_oracle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    semantic_model_call_count: Literal[0]
    real_proposer_quality_claimed: Literal[False]
    drafts: list[QueryProposerDevReferenceDraftV2] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_case_ids(self) -> "QueryProposerDevReferenceFixtureV3":
        case_ids = [item.case_id for item in self.drafts]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("reference fixture has duplicate case ids")
        return self


class QueryProposerDevRootManifestV1(StrictModel):
    schema_version: Literal["query-proposer-dev-root-manifest-v1"] = (
        "query-proposer-dev-root-manifest-v1"
    )
    dataset_id: Literal[DATASET_ID] = DATASET_ID
    artifact_sha256: dict[str, str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_hashes(self) -> "QueryProposerDevRootManifestV1":
        if any(
            len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
            for value in self.artifact_sha256.values()
        ):
            raise ValueError("root artifact manifest contains invalid sha256")
        return self


@dataclass(frozen=True)
class DevCaseSpec:
    case_id: str
    query_id: str
    family: str
    raw_query: str
    current_user_surface: str | None
    draft: QueryDraftV1
    context: QueryContextV1
    registry: CompilerRegistryV1
    expected_status: Literal["executable", "abstain"]
    expected_fallback_allowed: bool
    expected_fallback_reason: str | None
    expected_unresolved_slots: tuple[str, ...]
    expected_blocked_reasons: tuple[str, ...]
    critical: bool


_PREDICATES = {
    "lead": ("lead/manage", "manage", {"agent": "Person", "theme": "Project"}),
    "manage": (
        "lead/manage",
        "manage",
        {"agent": "Person", "theme": "Project"},
    ),
    "complete": ("complete-01", "complete", {"theme": "Deployment"}),
    "active": ("active-state", "has_active_state", {"theme": "Project"}),
    "own": ("own-01", "own", {"agent": "Person", "theme": "Project"}),
    "serve": ("serve-01", "serve", {"project": "Project", "client": "Client"}),
    "include team": (
        "include-team",
        "include_team",
        {"project": "Project", "team": "Team"},
    ),
    "support": ("support-01", "support", {"team": "Team", "client": "Client"}),
    "prefer work location": (
        "prefer-work-location",
        "prefer_work_location",
        {"experiencer": "Person", "location": "Place"},
    ),
    "cancel": ("cancel-01", "cancel", {"theme": "Task"}),
}


def _opaque_id(prefix: str, kind: str, index: int) -> str:
    value = f"query-proposer-dev-{kind}-{index:02d}".encode("ascii")
    return f"{prefix}-{hashlib.sha256(value).hexdigest()[:16]}"


def _memory_view() -> GitMemoryViewRefV1:
    return GitMemoryViewRefV1(
        workspace_id="ke-memory-next-prep",
        repository_epoch_id="dev-qualification-epoch-v1",
        checkpoint_id="dev-qualification-checkpoint-v1",
        git_commit="a" * 40,
        authoritative_ref="refs/heads/authoritative",
    )


def _registry(
    *,
    predicates: list[str],
    aliases: dict[str, list[str]] | None = None,
    entities: dict[str, tuple[str, str]] | None = None,
    identity_snapshot_id: str | None = None,
    identity_input_fingerprint: str | None = None,
) -> CompilerRegistryV1:
    entity_aliases = {"i": ["entity-user"]}
    entity_aliases.update(
        {key.casefold(): list(value) for key, value in (aliases or {}).items()}
    )
    entity_types = {"entity-user": ["Person"]}
    identity_status = {"entity-user": "resolved"}
    for entity_id, (entity_type, status) in (entities or {}).items():
        entity_types[entity_id] = [entity_type]
        identity_status[entity_id] = status
    predicate_aliases: dict[str, list[PredicateRegistryEntryV1]] = {}
    for surface in predicates:
        sense, operator, role_types = _PREDICATES[surface]
        predicate_aliases[surface] = [
            PredicateRegistryEntryV1(
                sense=sense,
                canonical_operator=operator,
                role_types=role_types,
            )
        ]
    return CompilerRegistryV1(
        ontology_revision="ontology-dev-v1",
        identity_revision="identity-dev-v1",
        registry_revision="query-dev-registry-v1",
        identity_snapshot_id=identity_snapshot_id,
        identity_input_fingerprint=identity_input_fingerprint,
        entity_aliases=entity_aliases,
        entity_types=entity_types,
        identity_status=identity_status,
        predicate_aliases=predicate_aliases,
    )


RoleSpec = tuple[str, str, str, str, str | None]
AtomSpec = tuple[str, list[RoleSpec]]


def _draft(
    *,
    query_id: str,
    groups: list[list[AtomSpec]],
    intent: str = "fact_lookup",
    target_level: str = "L1",
    answer_kind: str = "fact",
    distinct_by: str | None = None,
    time_constraints: list[tuple[str, str, str | None]] | None = None,
    lifecycle: str | None = None,
    source_status_constraints: list[str] | None = None,
    conflict_policy: str = "require_resolved",
    supersession_policy: str = "current_only",
    evidence_policy: str = "single_fact",
    explicit_absence_requested: bool = False,
) -> QueryDraftV1:
    atom_index = 0
    pattern_groups: list[QueryPatternGroupDraftV1] = []
    for group_index, atom_specs in enumerate(groups):
        atoms: list[QueryAtomDraftV1] = []
        for predicate_surface, role_specs in atom_specs:
            roles = [
                QueryRoleDraftV1(
                    role=role,
                    role_name=role_name,
                    term=QueryTermDraftV1(
                        kind=kind,
                        value=value,
                        expected_type=expected_type,
                    ),
                )
                for role, role_name, kind, value, expected_type in role_specs
            ]
            atoms.append(
                QueryAtomDraftV1(
                    atom_id=f"atom-{atom_index}",
                    predicate_surface=predicate_surface,
                    roles=roles,
                )
            )
            atom_index += 1
        pattern_groups.append(
            QueryPatternGroupDraftV1(
                group_id=f"group-{group_index}",
                atoms=atoms,
            )
        )
    times = [
        QueryTimeConstraintV1(field=field, operator=operator, value=value)
        for field, operator, value in (time_constraints or [])
    ]
    return QueryDraftV1(
        query_id=query_id,
        intent=intent,
        target_level=target_level,
        answer=AnswerDraftV1(
            kind=answer_kind,
            variable="?answer",
            distinct_by=distinct_by,
        ),
        pattern_groups=pattern_groups,
        time_constraints=times,
        lifecycle=lifecycle,
        source_status_constraints=source_status_constraints or [],
        conflict_policy=conflict_policy,
        supersession_policy=supersession_policy,
        evidence_policy=evidence_policy,
        explicit_absence_requested=explicit_absence_requested,
        producer_id=REFERENCE_MODEL,
        producer_version="1",
    )


def _spec(
    index: int,
    *,
    family: str,
    raw_query: str,
    groups: list[list[AtomSpec]],
    registry: CompilerRegistryV1,
    expected_status: Literal["executable", "abstain"],
    expected_fallback_allowed: bool = False,
    expected_fallback_reason: str | None = None,
    expected_unresolved_slots: tuple[str, ...] = (),
    expected_blocked_reasons: tuple[str, ...] = (),
    critical: bool = False,
    current_user_surface: str | None = "I",
    **draft_options: object,
) -> DevCaseSpec:
    case_id = _opaque_id("qc", "case", index)
    query_id = _opaque_id("qq", "query", index)
    context = QueryContextV1(
        query_id=query_id,
        raw_query=raw_query,
        query_time="2026-07-29T00:00:00Z",
        current_user_entity_id="entity-user",
        memory_view=_memory_view(),
        ontology_revision="ontology-dev-v1",
        identity_revision="identity-dev-v1",
        compiler_policy_revision="query-policy-v2-dev-qualification",
    )
    draft = _draft(
        query_id=query_id,
        groups=groups,
        **draft_options,
    )
    return DevCaseSpec(
        case_id=case_id,
        query_id=query_id,
        family=family,
        raw_query=raw_query,
        current_user_surface=current_user_surface,
        draft=draft,
        context=context,
        registry=registry,
        expected_status=expected_status,
        expected_fallback_allowed=expected_fallback_allowed,
        expected_fallback_reason=expected_fallback_reason,
        expected_unresolved_slots=expected_unresolved_slots,
        expected_blocked_reasons=expected_blocked_reasons,
        critical=critical,
    )


def _case_specs() -> list[DevCaseSpec]:
    agent_named = lambda name: [
        ("agent", "ARG0", "entity_surface", name, "Person"),
        ("theme", "ARG1", "variable", "?answer", "Project"),
    ]
    agent_self = [
        ("agent", "ARG0", "entity_surface", "I", "Person"),
        ("theme", "ARG1", "variable", "?answer", "Project"),
    ]
    mina_registry = _registry(
        predicates=["lead"],
        aliases={"Mina": ["entity-mina"]},
        entities={"entity-mina": ("Person", "resolved")},
    )
    archive_registry = _registry(
        predicates=["lead"],
        aliases={"Archive-7": ["entity-archive-7"]},
        entities={"entity-archive-7": ("Archive", "resolved")},
    )
    priya_registry = _registry(
        predicates=["manage"],
        aliases={"Priya": ["entity-priya"]},
        entities={"entity-priya": ("Person", "resolved")},
    )
    jordan_registry = _registry(
        predicates=["lead"],
        aliases={"Jordan": ["entity-jordan-a", "entity-jordan-b"]},
        entities={
            "entity-jordan-a": ("Person", "resolved"),
            "entity-jordan-b": ("Person", "resolved"),
        },
    )
    aurora_registry = _registry(
        predicates=["lead"],
        aliases={"Aurora": ["entity-project-aurora"]},
        entities={"entity-project-aurora": ("Project", "resolved")},
    )
    riley_registry = _registry(
        predicates=["lead"],
        aliases={"Riley": ["entity-riley"]},
        entities={"entity-riley": ("Person", "unresolved")},
        identity_snapshot_id="identity-snapshot-dev-v1",
        identity_input_fingerprint="1" * 64,
    )
    identity_registry = _registry(
        predicates=["lead"],
        identity_snapshot_id="identity-snapshot-dev-v1",
        identity_input_fingerprint="1" * 64,
    )
    specs = [
        _spec(
            1,
            family="atomic_fact_role",
            raw_query="Which project does Mina lead?",
            groups=[[('lead', agent_named("Mina"))]],
            registry=mina_registry,
            expected_status="executable",
        ),
        _spec(
            2,
            family="atomic_fact_role",
            raw_query="Which project does Archive-7 lead?",
            groups=[[('lead', agent_named("Archive-7"))]],
            registry=archive_registry,
            expected_status="abstain",
            expected_blocked_reasons=("role_type_mismatch:atom-0:agent",),
            critical=True,
        ),
        _spec(
            3,
            family="entity_predicate_linking",
            raw_query="Which project does Priya manage?",
            groups=[[('manage', agent_named("Priya"))]],
            registry=priya_registry,
            expected_status="executable",
        ),
        _spec(
            4,
            family="entity_predicate_linking",
            raw_query="Which project do I spearhead?",
            groups=[[('spearhead', agent_self)]],
            registry=_registry(predicates=[]),
            expected_status="abstain",
            expected_fallback_allowed=True,
            expected_fallback_reason="lexical_predicate_missing_link",
            expected_unresolved_slots=("predicate:atom-0",),
        ),
        _spec(
            5,
            family="entity_predicate_linking",
            raw_query="Which project does Jordan lead?",
            groups=[[('lead', agent_named("Jordan"))]],
            registry=jordan_registry,
            expected_status="abstain",
            expected_fallback_allowed=True,
            expected_fallback_reason="unresolved_entity",
            expected_unresolved_slots=("entity:atom-0:agent",),
            critical=True,
        ),
        _spec(
            6,
            family="temporal_lifecycle",
            raw_query="Which project am I currently leading?",
            groups=[[('lead', agent_self)]],
            registry=_registry(predicates=["lead"]),
            expected_status="executable",
            intent="temporal_latest",
            time_constraints=[("valid_time", "latest", None)],
            lifecycle="active",
        ),
        _spec(
            7,
            family="temporal_lifecycle",
            raw_query="Who was leading Aurora as of 2026-07-01?",
            groups=[[
                (
                    "lead",
                    [
                        ("agent", "ARG0", "variable", "?answer", "Person"),
                        (
                            "theme",
                            "ARG1",
                            "entity_surface",
                            "Aurora",
                            "Project",
                        ),
                    ],
                )
            ]],
            registry=aurora_registry,
            expected_status="abstain",
            expected_blocked_reasons=("time_operator_execution_unsupported:as_of",),
            critical=True,
            intent="temporal_latest",
            time_constraints=[("valid_time", "as_of", "2026-07-01")],
        ),
        _spec(
            8,
            family="epistemic_constraint",
            raw_query="Which deployment was completed according to the tool record?",
            groups=[[('complete', [
                ("theme", "ARG1", "variable", "?answer", "Deployment")
            ])]],
            registry=_registry(predicates=["complete"]),
            expected_status="executable",
            source_status_constraints=["tool_observed"],
        ),
        _spec(
            9,
            family="epistemic_constraint",
            raw_query="Which task has no cancellation record?",
            groups=[[('cancel', [
                ("theme", "ARG1", "variable", "?answer", "Task")
            ])]],
            registry=_registry(predicates=["cancel"]),
            expected_status="abstain",
            expected_blocked_reasons=("explicit_absence_execution_unsupported",),
            critical=True,
            evidence_policy="require_explicit_absence",
            explicit_absence_requested=True,
        ),
        _spec(
            10,
            family="boolean_and_or",
            raw_query="Which project do I lead that is also active?",
            groups=[[('lead', agent_self), ('active', [
                ("theme", "ARG1", "variable", "?answer", "Project")
            ])]],
            registry=_registry(predicates=["lead", "active"]),
            expected_status="executable",
        ),
        _spec(
            11,
            family="boolean_and_or",
            raw_query="Which project do I lead or own?",
            groups=[[('lead', agent_self)], [('own', agent_self)]],
            registry=_registry(predicates=["lead", "own"]),
            expected_status="executable",
        ),
        _spec(
            12,
            family="multihop",
            raw_query="Which client is served by a project I manage?",
            groups=[[
                ('manage', [
                    ("agent", "ARG0", "entity_surface", "I", "Person"),
                    ("theme", "ARG1", "variable", "?bridge", "Project"),
                ]),
                ('serve', [
                    ("project", "ARG0", "variable", "?bridge", "Project"),
                    ("client", "ARG1", "variable", "?answer", "Client"),
                ]),
            ]],
            registry=_registry(predicates=["manage", "serve"]),
            expected_status="executable",
        ),
        _spec(
            13,
            family="multihop",
            raw_query=(
                "Which client is supported by a team attached to a project I manage?"
            ),
            groups=[[
                ('manage', [
                    ("agent", "ARG0", "entity_surface", "I", "Person"),
                    ("theme", "ARG1", "variable", "?project", "Project"),
                ]),
                ('include team', [
                    ("project", "ARG0", "variable", "?project", "Project"),
                    ("team", "ARG1", "variable", "?team", "Team"),
                ]),
                ('support', [
                    ("team", "ARG0", "variable", "?team", "Team"),
                    ("client", "ARG1", "variable", "?answer", "Client"),
                ]),
            ]],
            registry=_registry(
                predicates=["manage", "include team", "support"]
            ),
            expected_status="executable",
        ),
        _spec(
            14,
            family="multihop",
            raw_query=(
                "Which client was served on 2026-06-01 by a project I manage?"
            ),
            groups=[[
                ('manage', [
                    ("agent", "ARG0", "entity_surface", "I", "Person"),
                    ("theme", "ARG1", "variable", "?bridge", "Project"),
                ]),
                ('serve', [
                    ("project", "ARG0", "variable", "?bridge", "Project"),
                    ("client", "ARG1", "variable", "?answer", "Client"),
                ]),
            ]],
            registry=_registry(predicates=["manage", "serve"]),
            expected_status="abstain",
            expected_blocked_reasons=("multi_atom_time_scope_unsupported",),
            critical=True,
            time_constraints=[("event_time", "exact", "2026-06-01")],
        ),
        _spec(
            15,
            family="l2_evidence_closure",
            raw_query="What is my current preferred work location?",
            groups=[[('prefer work location', [
                ("experiencer", "ARG0", "entity_surface", "I", "Person"),
                ("location", "ARG1", "variable", "?answer", "Place"),
            ])]],
            registry=_registry(predicates=["prefer work location"]),
            expected_status="executable",
            intent="preference_current",
            target_level="L2",
            time_constraints=[("valid_time", "latest", None)],
            lifecycle="active",
            evidence_policy="provenance_closure",
        ),
        _spec(
            16,
            family="l2_evidence_closure",
            raw_query=(
                "What work-location preferences have I reported, including conflicts "
                "and past ones?"
            ),
            groups=[[('prefer work location', [
                ("experiencer", "ARG0", "entity_surface", "I", "Person"),
                ("location", "ARG1", "variable", "?answer", "Place"),
            ])]],
            registry=_registry(predicates=["prefer work location"]),
            expected_status="executable",
            intent="multi_evidence",
            target_level="L2",
            conflict_policy="return_all",
            supersession_policy="include_history",
            evidence_policy="provenance_closure",
            source_status_constraints=["user_reported"],
        ),
        _spec(
            17,
            family="l2_evidence_closure",
            raw_query="What complete evidence set supports my work-location preference?",
            groups=[[('prefer work location', [
                ("experiencer", "ARG0", "entity_surface", "I", "Person"),
                ("location", "ARG1", "variable", "?answer", "Place"),
            ])]],
            registry=_registry(predicates=["prefer work location"]),
            expected_status="abstain",
            expected_blocked_reasons=(
                "answer_kind_execution_unsupported:evidence_set",
            ),
            critical=True,
            intent="multi_evidence",
            target_level="L2",
            answer_kind="evidence_set",
            evidence_policy="provenance_closure",
        ),
        _spec(
            18,
            family="identity_aggregate",
            raw_query="How many projects am I currently leading?",
            groups=[[('lead', agent_self)]],
            registry=identity_registry,
            expected_status="executable",
            target_level="L2",
            answer_kind="count",
            distinct_by="canonical_identity",
            time_constraints=[("valid_time", "latest", None)],
            lifecycle="active",
        ),
        _spec(
            19,
            family="identity_aggregate",
            raw_query="How many projects have I led, counting memory units?",
            groups=[[('lead', agent_self)]],
            registry=identity_registry,
            expected_status="abstain",
            expected_blocked_reasons=("count_requires_canonical_identity",),
            critical=True,
            target_level="L2",
            answer_kind="count",
            distinct_by="unit",
        ),
        _spec(
            20,
            family="identity_aggregate",
            raw_query="Which project does Riley lead?",
            groups=[[('lead', agent_named("Riley"))]],
            registry=riley_registry,
            expected_status="abstain",
            expected_blocked_reasons=("identity_unresolved:atom-0:agent",),
            critical=True,
            target_level="L2",
        ),
    ]
    return specs


def _public_document(specs: list[DevCaseSpec]) -> QueryCompilerPublicDocumentV1:
    return QueryCompilerPublicDocumentV1(
        dataset_id=DATASET_ID,
        cases=[
            QueryCompilerPublicCaseV1(
                case_id=spec.case_id,
                query_id=spec.query_id,
                raw_query=spec.raw_query,
                query_time=spec.context.query_time,
                current_user_surface=spec.current_user_surface,
                memory_view_handle=memory_view_handle(spec.context.memory_view),
                compiler_policy_revision=spec.context.compiler_policy_revision,
            )
            for spec in specs
        ],
    )


def _authority_document(
    specs: list[DevCaseSpec],
) -> QueryCompilerAuthorityDocumentV1:
    return QueryCompilerAuthorityDocumentV1(
        dataset_id=DATASET_ID,
        cases=[
            QueryCompilerAuthorityCaseV1(
                case_id=spec.case_id,
                context=spec.context,
                registry=spec.registry,
            )
            for spec in specs
        ],
    )


_GOLD_ORACLE_PATH = Path(__file__).with_name(
    "query_compiler_v2_dev_oracle_v2.json"
)
_REFERENCE_FIXTURE_PATH = Path(__file__).with_name(
    "query_compiler_v2_dev_reference_v3.json"
)


def _load_independent_gold_oracle() -> QueryProposerDevOracleV2:
    payload = load_json(_GOLD_ORACLE_PATH)
    if _GOLD_ORACLE_PATH.read_bytes() != canonical_json_bytes(payload):
        raise ValueError("independent gold oracle is not canonical JSON")
    return QueryProposerDevOracleV2.model_validate(payload)


def _load_reference_fixture() -> QueryProposerDevReferenceFixtureV3:
    payload = load_json(_REFERENCE_FIXTURE_PATH)
    if _REFERENCE_FIXTURE_PATH.read_bytes() != canonical_json_bytes(payload):
        raise ValueError("known-good reference fixture is not canonical JSON")
    return QueryProposerDevReferenceFixtureV3.model_validate(payload)


def _compiler_gold_outcome_counts(
    compiler_gold: QueryCompilerGoldDocumentV1,
) -> dict[str, int]:
    return {
        "expected_executable_count": sum(
            item.expected_status == "executable" for item in compiler_gold.cases
        ),
        "expected_abstain_count": sum(
            item.expected_status == "abstain" for item in compiler_gold.cases
        ),
        "expected_critical_count": sum(
            item.critical for item in compiler_gold.cases
        ),
        "expected_allowed_fallback_count": sum(
            item.expected_fallback_allowed for item in compiler_gold.cases
        ),
    }


def _assert_manifest_matches_compiler_gold(
    manifest: QueryProposerDevDatasetManifestV1,
    compiler_gold: QueryCompilerGoldDocumentV1,
) -> None:
    observed = {
        field: getattr(manifest, field)
        for field in _compiler_gold_outcome_counts(compiler_gold)
    }
    expected = _compiler_gold_outcome_counts(compiler_gold)
    if observed != expected:
        raise ValueError(
            "manifest outcome counts do not match compiler gold: "
            f"expected {expected!r}, observed {observed!r}"
        )
    family_counts = dict(Counter(item.family for item in compiler_gold.cases))
    if manifest.family_counts != family_counts:
        raise ValueError("manifest family counts do not match compiler gold")
    if manifest.case_count != len(compiler_gold.cases):
        raise ValueError("manifest case count does not match compiler gold")


def _prompt_bytes() -> bytes:
    return (
        "# QueryDraftV1 deterministic dev qualification policy\n\n"
        "Input is limited to opaque public cases. Authority, registries, gold, "
        "history, and typed-extractor hidden data are unavailable.\n\n"
        "Emit one strict QueryDraftV1 JSON object per case. Use group-0 and "
        "group-1 in document order, atom-0 onward in document order, and stable "
        "variable bindings. Do not repair, answer, write memory, or treat "
        "embedding output as authority.\n\n"
        "This dev reference is emitted by a deterministic harness. It is not a "
        "semantic model run and is qualification evidence only.\n"
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


@dataclass(frozen=True)
class _DevPayload:
    specs: list[DevCaseSpec]
    public: QueryCompilerPublicDocumentV1
    authority: QueryCompilerAuthorityDocumentV1
    draft_gold: QueryDraftGoldDocumentV1
    compiler_gold: QueryCompilerGoldDocumentV1
    prompt_bytes: bytes
    dispatch: dict[str, object]
    raw_response: dict[str, object]
    proposals: QueryDraftProposalDocumentV1
    provenance: QueryDraftProposalProvenanceV1
    validation_receipt: QueryDraftValidationDocumentV1
    typed_proposals: QueryCompilerProposalDocumentV1
    evaluation: QueryDraftProposalEvaluationV1
    dataset_manifest: QueryProposerDevDatasetManifestV1


def _dev_payload() -> _DevPayload:
    specs = _case_specs()
    public = _public_document(specs)
    authority = _authority_document(specs)
    oracle = _load_independent_gold_oracle()
    reference = _load_reference_fixture()
    draft_gold = oracle.draft_gold
    compiler_gold = oracle.compiler_gold
    public_case_ids = [item.case_id for item in public.cases]
    gold_case_ids = [item.case_id for item in draft_gold.cases]
    if public_case_ids != gold_case_ids:
        raise ValueError("public cases do not match the frozen gold oracle")
    reference_case_ids = [item.case_id for item in reference.drafts]
    if public_case_ids != reference_case_ids:
        raise ValueError("public cases do not match the known-good reference fixture")
    oracle_sha256 = hashlib.sha256(_GOLD_ORACLE_PATH.read_bytes()).hexdigest()
    if reference.source_oracle_sha256 != oracle_sha256:
        raise ValueError("reference fixture is bound to a different gold oracle")
    reference_by_id = {item.case_id: item.draft for item in reference.drafts}
    prompt_bytes = _prompt_bytes()
    dispatch: dict[str, object] = {
        "schema_version": "query-proposer-deterministic-dispatch-v1",
        "dataset_id": DATASET_ID,
        "model": REFERENCE_MODEL,
        "case_count": len(specs),
        "producer_mode": "deterministic_reference_harness",
    }
    raw_response: dict[str, object] = {
        "schema_version": "query-proposer-deterministic-response-v1",
        "dataset_id": DATASET_ID,
        "model": REFERENCE_MODEL,
        "emission_count": 1,
        "outputs": [
            {
                "case_id": spec.case_id,
                "payload": reference_by_id[spec.case_id].model_dump(mode="json"),
            }
            for spec in specs
        ],
    }
    raw_response_sha256 = _sha256(raw_response)
    proposals = QueryDraftProposalDocumentV1(
        dataset_id=DATASET_ID,
        proposals=[
            QueryDraftRawProposalV1(
                case_id=spec.case_id,
                parse_status="json",
                raw_payload=reference_by_id[spec.case_id].model_dump(mode="json"),
                raw_response_sha256=raw_response_sha256,
            )
            for spec in specs
        ],
    )
    provenance = QueryDraftProposalProvenanceV1(
        dataset_id=DATASET_ID,
        run_id=RUN_ID,
        requested_model=REFERENCE_MODEL,
        response_model=REFERENCE_MODEL,
        public_sha256=_sha256(public),
        prompt_sha256=hashlib.sha256(prompt_bytes).hexdigest(),
        dispatch_sha256=_sha256(dispatch),
        raw_response_sha256=raw_response_sha256,
        proposals_sha256=_sha256(proposals),
    )
    validation_receipt, typed = materialize_typed_query_proposals(
        public,
        proposals,
    )
    if typed is None:
        raise ValueError("deterministic reference drafts failed schema validation")
    evaluation = evaluate_query_draft_proposals(
        public=public,
        authority=authority,
        proposals=proposals,
        draft_gold=draft_gold,
        compiler_gold=compiler_gold,
    )
    family_counts = dict(Counter(item.family for item in compiler_gold.cases))
    outcome_counts = _compiler_gold_outcome_counts(compiler_gold)
    dataset_manifest = QueryProposerDevDatasetManifestV1(
        family_counts=family_counts,
        **outcome_counts,
        source_allowlist=[SOURCE_KIND],
        case_source_mapping={spec.case_id: SOURCE_KIND for spec in specs},
        gold_oracle_sha256=oracle_sha256,
        reference_fixture_sha256=hashlib.sha256(
            _REFERENCE_FIXTURE_PATH.read_bytes()
        ).hexdigest(),
    )
    _assert_manifest_matches_compiler_gold(dataset_manifest, compiler_gold)
    return _DevPayload(
        specs=specs,
        public=public,
        authority=authority,
        draft_gold=draft_gold,
        compiler_gold=compiler_gold,
        prompt_bytes=prompt_bytes,
        dispatch=dispatch,
        raw_response=raw_response,
        proposals=proposals,
        provenance=provenance,
        validation_receipt=validation_receipt,
        typed_proposals=typed,
        evaluation=evaluation,
        dataset_manifest=dataset_manifest,
    )


_REFERENCE_FILE_NAMES = (
    "artifact-manifest.json",
    "dispatch.json",
    "proposals.json",
    "proposer-prompt.md",
    "provenance.json",
    "public.json",
    "raw-response.json",
    "typed-proposals.json",
    "validation-receipt.json",
)
_TOP_LEVEL_FILE_NAMES = (
    "authority.json",
    "compiler-gold.json",
    "dev-dataset-manifest.json",
    "draft-gold.json",
    "evaluation.json",
    "manifest.json",
    "proposer-prompt-and-policy.md",
    "public.json",
)
_TOP_LEVEL_ENTRIES = {*_TOP_LEVEL_FILE_NAMES, "reference-run"}
_FORBIDDEN_DATASET_MARKERS = (
    b"typed-extractor-fresh",
    b"typed_extractor_fresh",
    b"fresh-v3",
    b"longmemeval-6d550036",
)


def _top_level_bytes(payload: _DevPayload) -> dict[str, bytes]:
    return {
        "authority.json": canonical_json_bytes(payload.authority),
        "compiler-gold.json": canonical_json_bytes(payload.compiler_gold),
        "dev-dataset-manifest.json": canonical_json_bytes(
            payload.dataset_manifest
        ),
        "draft-gold.json": canonical_json_bytes(payload.draft_gold),
        "evaluation.json": canonical_json_bytes(payload.evaluation),
        "proposer-prompt-and-policy.md": payload.prompt_bytes,
        "public.json": canonical_json_bytes(payload.public),
    }


def _reference_run_bytes(payload: _DevPayload) -> dict[str, bytes]:
    files = {
        "public.json": canonical_json_bytes(payload.public),
        "proposer-prompt.md": payload.prompt_bytes,
        "dispatch.json": canonical_json_bytes(payload.dispatch),
        "raw-response.json": canonical_json_bytes(payload.raw_response),
        "proposals.json": canonical_json_bytes(payload.proposals),
        "provenance.json": canonical_json_bytes(payload.provenance),
        "validation-receipt.json": canonical_json_bytes(
            payload.validation_receipt
        ),
        "typed-proposals.json": canonical_json_bytes(payload.typed_proposals),
    }
    manifest = QueryDraftProposalArtifactManifestV1(
        dataset_id=DATASET_ID,
        run_id=RUN_ID,
        requested_model=REFERENCE_MODEL,
        response_model=REFERENCE_MODEL,
        artifact_sha256={
            name: hashlib.sha256(content).hexdigest()
            for name, content in files.items()
        },
    )
    files["artifact-manifest.json"] = canonical_json_bytes(manifest)
    return files


def _expected_leaf_bytes(payload: _DevPayload) -> dict[str, bytes]:
    top = _top_level_bytes(payload)
    reference = {
        f"reference-run/{name}": content
        for name, content in _reference_run_bytes(payload).items()
    }
    hashed = {**top, **reference}
    root_manifest = QueryProposerDevRootManifestV1(
        artifact_sha256={
            name: hashlib.sha256(content).hexdigest()
            for name, content in hashed.items()
        }
    )
    return {
        **hashed,
        "manifest.json": canonical_json_bytes(root_manifest),
    }


def _write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _make_tree_read_only(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_file():
            os.chmod(path, 0o444)
    directories = [path for path in root.rglob("*") if path.is_dir()]
    for path in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        os.chmod(path, 0o555)
    os.chmod(root, 0o555)


def _remove_staging_tree(root: Path) -> None:
    if root.is_symlink():
        root.unlink(missing_ok=True)
        return
    if not root.exists():
        return
    os.chmod(root, 0o700)
    for path in root.rglob("*"):
        if path.is_symlink():
            continue
        os.chmod(path, 0o700 if path.is_dir() else 0o600)
    shutil.rmtree(root)


def _publish_directory_noreplace(staging: Path, root: Path) -> None:
    if os.name == "nt":
        try:
            os.rename(staging, root)
        except OSError as exc:
            if root.exists() or root.is_symlink():
                raise FileExistsError(
                    errno.EEXIST,
                    f"dev artifact root already exists: {root}",
                    root,
                ) from exc
            raise
        return
    if os.name != "posix":
        raise RuntimeError("atomic no-replace directory publish is unsupported")
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise RuntimeError("renameat2 is required for atomic no-replace publish")
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        -100,
        os.fsencode(staging),
        -100,
        os.fsencode(root),
        1,
    )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(
            error_number,
            f"dev artifact root already exists: {root}",
            root,
        )
    raise OSError(error_number, os.strerror(error_number), root)


def _assert_exact_tree(root: Path, expected_files: set[str]) -> None:
    if not root.is_dir() or root.is_symlink():
        raise ValueError("dev artifact root must be a real directory")
    if {entry.name for entry in root.iterdir()} != _TOP_LEVEL_ENTRIES:
        raise ValueError("dev artifact top-level set mismatch")
    entries = list(root.rglob("*"))
    if any(path.is_symlink() for path in entries):
        raise ValueError("dev artifact tree cannot contain symlinks")
    actual_files = {
        path.relative_to(root).as_posix()
        for path in entries
        if path.is_file()
    }
    actual_directories = {
        path.relative_to(root).as_posix()
        for path in entries
        if path.is_dir()
    }
    if actual_files != expected_files:
        raise ValueError("dev artifact file set mismatch")
    if actual_directories != {"reference-run"}:
        raise ValueError("dev artifact directory set mismatch")
    if root.stat().st_mode & 0o222:
        raise ValueError("dev artifact root is writable")
    for path in entries:
        if path.stat().st_mode & 0o222:
            raise ValueError(f"dev artifact is writable: {path.relative_to(root)}")


def _assert_public_boundary(public_payload: object) -> None:
    forbidden = {
        "family",
        "status",
        "expected_status",
        "critical",
        "fallback",
        "fallback_allowed",
        "entity_id",
        "registry",
        "gold",
    }

    def visit(value: object) -> None:
        if isinstance(value, dict):
            if forbidden.intersection(value):
                raise ValueError("public artifact leaks authority or gold fields")
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(public_payload)


def validate_query_proposer_dev_v1(
    root: Path,
) -> QueryProposerDevDatasetManifestV1:
    expected_payload = _dev_payload()
    expected_bytes = _expected_leaf_bytes(expected_payload)
    _assert_exact_tree(root, set(expected_bytes))
    for relative_path, expected in expected_bytes.items():
        path = root / relative_path
        actual = path.read_bytes()
        if actual != expected:
            raise ValueError(f"dev artifact bytes differ: {relative_path}")
    root_manifest = QueryProposerDevRootManifestV1.model_validate(
        load_json(root / "manifest.json")
    )
    if (root / "manifest.json").read_bytes() != canonical_json_bytes(
        root_manifest
    ):
        raise ValueError("root artifact manifest is not canonical JSON")
    expected_hash_paths = set(expected_bytes) - {"manifest.json"}
    if set(root_manifest.artifact_sha256) != expected_hash_paths:
        raise ValueError("root artifact hash set mismatch")
    for relative_path, expected_hash in root_manifest.artifact_sha256.items():
        actual_hash = hashlib.sha256((root / relative_path).read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            raise ValueError(f"root artifact hash mismatch: {relative_path}")
    validate_frozen_query_draft_proposal_run(root / "reference-run")
    public_payload = load_json(root / "public.json")
    _assert_public_boundary(public_payload)
    joined = b"\n".join(
        (root / relative_path).read_bytes().lower()
        for relative_path in sorted(expected_bytes)
    )
    for marker in _FORBIDDEN_DATASET_MARKERS:
        if marker in joined:
            raise ValueError("dev artifact contains a forbidden hidden marker")
    actual_manifest = QueryProposerDevDatasetManifestV1.model_validate(
        load_json(root / "dev-dataset-manifest.json")
    )
    if actual_manifest != expected_payload.dataset_manifest:
        raise ValueError("dev dataset manifest does not match authored cases")
    actual_compiler_gold = QueryCompilerGoldDocumentV1.model_validate(
        load_json(root / "compiler-gold.json")
    )
    _assert_manifest_matches_compiler_gold(actual_manifest, actual_compiler_gold)
    evaluation = QueryDraftProposalEvaluationV1.model_validate(
        load_json(root / "evaluation.json")
    )
    if not evaluation.combined_dev_ready:
        raise ValueError("dev proposer/compiler double gate is not ready")
    return actual_manifest


def build_query_proposer_dev_v1(
    root: Path,
) -> QueryProposerDevDatasetManifestV1:
    if root.exists() or root.is_symlink():
        raise FileExistsError(f"dev artifact root already exists: {root}")
    root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{root.name}.author-", dir=root.parent)
    )
    try:
        payload = _dev_payload()
        top_level = _top_level_bytes(payload)
        for name, content in top_level.items():
            _write_bytes(staging / name, content)
        freeze_query_draft_proposal_run(
            root=staging / "reference-run",
            public=payload.public,
            prompt_bytes=payload.prompt_bytes,
            dispatch=payload.dispatch,
            raw_response=payload.raw_response,
            proposals=payload.proposals,
            provenance=payload.provenance,
            validation_receipt=payload.validation_receipt,
            typed_proposals=payload.typed_proposals,
        )
        expected = _expected_leaf_bytes(payload)
        _write_bytes(staging / "manifest.json", expected["manifest.json"])
        _make_tree_read_only(staging)
        validated = validate_query_proposer_dev_v1(staging)
        _publish_directory_noreplace(staging, root)
        return validated
    except Exception:
        _remove_staging_tree(staging)
        raise
