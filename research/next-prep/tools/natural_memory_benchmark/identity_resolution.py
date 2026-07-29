from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from .authoritative_memory import (
    AuthoritativeQueryPlan,
    AuthoritativeQueryResult,
    ClaimClosureContext,
    ClosureEvaluationInputs,
    ClosureSlotSpec,
    L1MemoryUnitV2,
    L2MemoryUnitV2,
    L2StructuredClaim,
    MemoryRepresentationBundleV3,
    ProducerIdentity,
    SourceBindingV2,
    StrictModel,
    assess_authoritative_bundle_integrity,
    canonical_sha256,
    evaluate_closure_spec,
    execute_authoritative_query,
    make_closure_spec,
    make_evidence_span,
    make_memory_unit_revision,
    make_raw_artifact_revision,
    make_source_record_revision,
)
from .representation_contract import (
    REQUIRED_MEMORY_CAPABILITIES,
    CapabilityDeclaration,
    RepresentationProfile,
)
from .semantic_ir import LinkBinding, Predicate, RoleBinding, TimeBinding


MappingRelation = Literal["exact", "narrower", "broader", "related"]
IdentityAction = Literal["merge", "keep_distinct", "reject_merge", "split", "abstain"]
IdentityDecisionStatus = Literal["accepted", "rejected", "superseded", "candidate"]


class ExternalOntologyMapping(StrictModel):
    source: str = Field(min_length=1)
    release: str = Field(min_length=1)
    source_commit: str = Field(min_length=1)
    external_id: str = Field(min_length=1)
    relation: MappingRelation


class ConceptRegistryEntry(StrictModel):
    schema_version: Literal["memory-concept-registry-entry-v1"] = (
        "memory-concept-registry-entry-v1"
    )
    concept_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    parent_concept_ids: list[str] = Field(default_factory=list)
    external_mappings: list[ExternalOntologyMapping] = Field(default_factory=list)
    allowed_identity_properties: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    identity_authority: bool = False


class TypedIdentifier(StrictModel):
    namespace: str = Field(min_length=1)
    value: str = Field(min_length=1)


class EntityRecord(StrictModel):
    schema_version: Literal["memory-entity-record-v1"] = "memory-entity-record-v1"
    entity_id: str = Field(min_length=1)
    concept_ids: list[str] = Field(min_length=1)
    names: list[str] = Field(min_length=1)
    identifiers: list[TypedIdentifier] = Field(default_factory=list)
    external_identity_urls: list[str] = Field(default_factory=list)
    lifecycle: Literal["active", "superseded", "candidate"] = "candidate"
    source_l1_unit_ids: list[str] = Field(min_length=1)
    source_revision_ids: list[str] = Field(min_length=1)

    @property
    def semantic_hash(self) -> str:
        return canonical_sha256(self)


class IdentityDecision(StrictModel):
    schema_version: Literal["identity-decision-v1"] = "identity-decision-v1"
    decision_id: str = Field(min_length=1)
    action: IdentityAction
    status: IdentityDecisionStatus
    subject_entity_ids: list[str] = Field(min_length=1)
    canonical_entity_id: str | None = None
    reason_code: str = Field(min_length=1)
    evidence_l1_unit_ids: list[str] = Field(min_length=1)
    evidence_source_revision_ids: list[str] = Field(min_length=1)
    closure_id: str = Field(min_length=1)
    supersedes_decision_id: str | None = None
    transaction_time: str = Field(min_length=1)
    producer: ProducerIdentity

    @model_validator(mode="after")
    def validate_action_shape(self) -> "IdentityDecision":
        if self.action == "merge" and self.canonical_entity_id is None:
            raise ValueError("merge decision requires canonical_entity_id")
        if self.action != "merge" and self.canonical_entity_id is not None:
            raise ValueError(f"{self.action} decision cannot set canonical_entity_id")
        if self.action in {"keep_distinct", "reject_merge", "split", "abstain"} and len(
            self.subject_entity_ids
        ) < 2:
            raise ValueError(f"{self.action} decision requires at least two subjects")
        if self.action == "split" and self.supersedes_decision_id is None:
            raise ValueError("split decision requires supersedes_decision_id")
        return self

    @property
    def semantic_hash(self) -> str:
        return canonical_sha256(self)


class IdentityDependency(StrictModel):
    reference_id: str = Field(min_length=1)
    reference_kind: Literal["l1_unit", "source_revision", "entity_record"]
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class IdentityEvidenceClosure(StrictModel):
    schema_version: Literal["identity-evidence-closure-v1"] = "identity-evidence-closure-v1"
    closure_id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    decision_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    required_l1_unit_ids: list[str] = Field(min_length=1)
    required_source_revision_ids: list[str] = Field(min_length=1)
    dependencies: list[IdentityDependency]
    policy_version: str = Field(min_length=1)
    input_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    complete: bool
    reason_code: Literal["complete", "missing_identity_evidence"]
    result_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class CanonicalIdentityGroup(StrictModel):
    canonical_entity_id: str = Field(min_length=1)
    member_entity_ids: list[str] = Field(min_length=1)


class IdentitySnapshot(StrictModel):
    schema_version: Literal["identity-snapshot-v1"] = "identity-snapshot-v1"
    snapshot_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    scoped_entity_ids: list[str] = Field(min_length=1)
    groups: list[CanonicalIdentityGroup]
    distinct_pairs: list[list[str]] = Field(default_factory=list)
    unresolved_groups: list[list[str]] = Field(default_factory=list)
    active_decision_ids: list[str] = Field(default_factory=list)
    superseded_decision_ids: list[str] = Field(default_factory=list)
    decision_closure_hashes: dict[str, str] = Field(default_factory=dict)
    input_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class IdentityAggregateClaim(StrictModel):
    schema_version: Literal["identity-aggregate-claim-v1"] = "identity-aggregate-claim-v1"
    aggregate_claim_id: str = Field(min_length=1)
    function: Literal["count_distinct"] = "count_distinct"
    query_id: str = Field(min_length=1)
    supporting_l2_claim_id: str = Field(min_length=1)
    source_role: str = Field(min_length=1)
    member_l1_unit_ids: list[str] = Field(min_length=1)
    member_entity_ids: list[str] = Field(min_length=1)
    identity_snapshot_id: str = Field(min_length=1)
    identity_decision_ids: list[str] = Field(default_factory=list)
    resolved_canonical_entity_ids: list[str] = Field(default_factory=list)
    required_evidence_ids: list[str] = Field(min_length=1)
    value: int | None = Field(default=None, ge=0)
    aggregate_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class IdentityAwareMemoryBundleV4(MemoryRepresentationBundleV3):
    schema_version: Literal["identity-aware-memory-bundle-v4"] = "identity-aware-memory-bundle-v4"
    concept_registry: list[ConceptRegistryEntry]
    entity_records: list[EntityRecord]
    identity_decisions: list[IdentityDecision]
    identity_closures: list[IdentityEvidenceClosure]
    identity_snapshots: list[IdentitySnapshot]
    aggregate_claims: list[IdentityAggregateClaim]


class IdentityAwareQueryResult(AuthoritativeQueryResult):
    schema_version: Literal["identity-aware-query-result-v1"] = "identity-aware-query-result-v1"
    aggregate_value: int | None = None
    identity_snapshot_id: str | None = None


class IdentityIntegrityReport(StrictModel):
    schema_version: Literal["identity-integrity-report-v1"] = "identity-integrity-report-v1"
    bundle_id: str
    valid: bool
    errors: list[str]
    metrics: dict[str, int]


class IdentitySourceValidationReport(StrictModel):
    schema_version: Literal["identity-source-validation-report-v1"] = (
        "identity-source-validation-report-v1"
    )
    valid: bool
    errors: list[str]
    metrics: dict[str, int]


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _content_id(prefix: str, value: Any) -> str:
    return f"{prefix}-{canonical_sha256(value)[:24]}"


def identity_native_profile() -> RepresentationProfile:
    return RepresentationProfile(
        representation_id="identity-aware-native-v4",
        family="semantic_ir",
        format_version="identity-aware-memory-bundle-v4",
        role="reference_carrier",
        capabilities=[
            CapabilityDeclaration(capability=name, support_mode="native", location="identity v4")
            for name in REQUIRED_MEMORY_CAPABILITIES
        ],
    )


def identity_extended_amr_profile() -> RepresentationProfile:
    return RepresentationProfile(
        representation_id="extended-amr-memory-graph-v3",
        family="extended_amr",
        format_version="extended-amr-memory-graph-v3",
        role="authoritative_candidate",
        capabilities=[
            CapabilityDeclaration(capability=name, support_mode="extension", location="explicit v3 graph")
            for name in REQUIRED_MEMORY_CAPABILITIES
        ],
    )


def build_schemaorg_concept_registry(reference_path: Path) -> list[ConceptRegistryEntry]:
    payload = json.loads(reference_path.read_text(encoding="utf-8"))
    source = payload["source"]

    def mapping(external_id: str, relation: MappingRelation) -> ExternalOntologyMapping:
        return ExternalOntologyMapping(
            source="schema.org",
            release=str(source["release"]),
            source_commit=str(source["commit"]),
            external_id=external_id,
            relation=relation,
        )

    return [
        ConceptRegistryEntry(
            concept_id="memory:Person",
            label="Person",
            external_mappings=[mapping("https://schema.org/Person", "exact")],
            allowed_identity_properties=["identity:strong_identifier", "identity:external_identity_url"],
            constraints=["A local person record still requires source-backed identity evidence."],
        ),
        ConceptRegistryEntry(
            concept_id="memory:Organization",
            label="Organization",
            external_mappings=[mapping("https://schema.org/Organization", "exact")],
            allowed_identity_properties=["identity:strong_identifier", "identity:external_identity_url"],
            constraints=["Organization identifiers are namespace and jurisdiction scoped."],
        ),
        ConceptRegistryEntry(
            concept_id="memory:Project",
            label="Project",
            external_mappings=[mapping("https://schema.org/Project", "related")],
            allowed_identity_properties=["identity:strong_identifier", "identity:external_identity_url"],
            constraints=[
                "The local concept also covers personal and class projects, so schema.org Project is not exact."
            ],
        ),
        ConceptRegistryEntry(
            concept_id="memory:Action",
            label="Action",
            external_mappings=[mapping("https://schema.org/Action", "related")],
            constraints=["AMR predicate sense and local role constraints remain authoritative."],
        ),
        ConceptRegistryEntry(
            concept_id="memory:Event",
            label="Event",
            external_mappings=[mapping("https://schema.org/Event", "related")],
            constraints=["Event, valid, and transaction time remain separate local fields."],
        ),
        ConceptRegistryEntry(
            concept_id="memory:Role",
            label="Role",
            external_mappings=[mapping("https://schema.org/Role", "related")],
            constraints=["Role time bounds do not replace event-role evidence."],
        ),
        ConceptRegistryEntry(
            concept_id="memory:IdentityIdentifier",
            label="Identity identifier",
            external_mappings=[mapping("https://schema.org/identifier", "narrower")],
            constraints=["Only namespace-scoped identifiers may be strong identity evidence."],
        ),
        ConceptRegistryEntry(
            concept_id="memory:IdentityReference",
            label="External identity reference",
            external_mappings=[mapping("https://schema.org/sameAs", "narrower")],
            constraints=["Only an unambiguous external URL may populate this property."],
            identity_authority=False,
        ),
    ]


def _decision_dependency_payload(
    bundle: IdentityAwareMemoryBundleV4 | MemoryRepresentationBundleV3,
    decision: IdentityDecision,
) -> tuple[list[IdentityDependency], bool]:
    l1_by_id = {item.unit_id: item for item in bundle.l1_units}
    sources = {item.source_revision_id: item for item in bundle.source_record_revisions}
    entities = {
        item.entity_id: item
        for item in getattr(bundle, "entity_records", [])
    }
    dependencies: list[IdentityDependency] = []
    complete = True
    for unit_id in sorted(set(decision.evidence_l1_unit_ids)):
        unit = l1_by_id.get(unit_id)
        if unit is None:
            complete = False
            continue
        dependencies.append(
            IdentityDependency(
                reference_id=unit_id,
                reference_kind="l1_unit",
                content_sha256=canonical_sha256(unit),
            )
        )
    for source_id in sorted(set(decision.evidence_source_revision_ids)):
        source = sources.get(source_id)
        if source is None:
            complete = False
            continue
        dependencies.append(
            IdentityDependency(
                reference_id=source_id,
                reference_kind="source_revision",
                content_sha256=canonical_sha256(source),
            )
        )
    known_canonical_ids = {
        item.canonical_entity_id
        for item in getattr(bundle, "identity_decisions", [])
        if item.canonical_entity_id
    }
    for entity_id in sorted(set(decision.subject_entity_ids)):
        entity = entities.get(entity_id)
        if entity is None:
            if entity_id not in known_canonical_ids:
                complete = False
            continue
        dependencies.append(
            IdentityDependency(
                reference_id=entity_id,
                reference_kind="entity_record",
                content_sha256=entity.semantic_hash,
            )
        )
    return sorted(dependencies, key=lambda item: (item.reference_kind, item.reference_id)), complete


def evaluate_identity_closure(
    bundle: IdentityAwareMemoryBundleV4 | MemoryRepresentationBundleV3,
    decision: IdentityDecision,
    *,
    policy_version: str = "identity-policy-v1",
) -> IdentityEvidenceClosure:
    dependencies, complete = _decision_dependency_payload(bundle, decision)
    input_payload = {
        "closure_id": decision.closure_id,
        "decision_id": decision.decision_id,
        "decision_hash": decision.semantic_hash,
        "required_l1_unit_ids": sorted(decision.evidence_l1_unit_ids),
        "required_source_revision_ids": sorted(decision.evidence_source_revision_ids),
        "dependencies": [item.model_dump(mode="json") for item in dependencies],
        "policy_version": policy_version,
    }
    result_payload = {
        "complete": complete,
        "reason_code": "complete" if complete else "missing_identity_evidence",
    }
    return IdentityEvidenceClosure(
        closure_id=decision.closure_id,
        decision_id=decision.decision_id,
        decision_hash=decision.semantic_hash,
        required_l1_unit_ids=sorted(decision.evidence_l1_unit_ids),
        required_source_revision_ids=sorted(decision.evidence_source_revision_ids),
        dependencies=dependencies,
        policy_version=policy_version,
        input_fingerprint=canonical_sha256(input_payload),
        complete=complete,
        reason_code="complete" if complete else "missing_identity_evidence",
        result_hash=canonical_sha256(result_payload),
    )


def is_identity_closure_fresh(
    bundle: IdentityAwareMemoryBundleV4,
    closure: IdentityEvidenceClosure,
) -> bool:
    decision = next(
        (item for item in bundle.identity_decisions if item.decision_id == closure.decision_id),
        None,
    )
    if decision is None:
        return False
    return closure == evaluate_identity_closure(
        bundle,
        decision,
        policy_version=closure.policy_version,
    )


class _UnionFind:
    def __init__(self, values: set[str]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        self.parent.setdefault(value, value)
        if self.parent[value] != value:
            self.parent[value] = self.find(self.parent[value])
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        first, second = sorted((left_root, right_root))
        self.parent[second] = first


def _scoped_decisions(
    decisions: list[IdentityDecision],
    scoped_entity_ids: list[str],
) -> tuple[list[IdentityDecision], list[str]]:
    active = [item for item in decisions if item.status == "accepted"]
    reachable = set(scoped_entity_ids)
    selected: list[IdentityDecision] = []
    changed = True
    while changed:
        changed = False
        for decision in active:
            if decision in selected:
                continue
            decision_ids = set(decision.subject_entity_ids)
            if decision.canonical_entity_id:
                decision_ids.add(decision.canonical_entity_id)
            if reachable.intersection(decision_ids):
                selected.append(decision)
                before = len(reachable)
                reachable.update(decision_ids)
                changed = changed or len(reachable) != before
    selected_ids = {item.decision_id for item in selected}
    superseded = sorted(
        {
            item.supersedes_decision_id
            for item in selected
            if item.supersedes_decision_id is not None
        }
        | {
            item.decision_id
            for item in decisions
            if item.status == "superseded"
            and any(
                active_item.supersedes_decision_id == item.decision_id
                for active_item in selected
            )
        }
    )
    return sorted(selected, key=lambda item: item.decision_id), superseded


def build_identity_snapshot(
    bundle: IdentityAwareMemoryBundleV4,
    *,
    scoped_entity_ids: list[str],
    policy_version: str = "identity-policy-v1",
) -> IdentitySnapshot:
    scoped = sorted(dict.fromkeys(scoped_entity_ids))
    decisions, superseded = _scoped_decisions(bundle.identity_decisions, scoped)
    closures = {item.decision_id: item for item in bundle.identity_closures}
    for decision in decisions:
        closure = closures.get(decision.decision_id)
        if closure is None or not closure.complete or not is_identity_closure_fresh(bundle, closure):
            raise ValueError(f"identity decision {decision.decision_id} lacks fresh complete closure")
        if decision.supersedes_decision_id:
            old = next(
                (
                    item
                    for item in bundle.identity_decisions
                    if item.decision_id == decision.supersedes_decision_id
                ),
                None,
            )
            if old is None or old.status != "superseded":
                raise ValueError(f"identity decision {decision.decision_id} has invalid superseded decision")

    all_ids = set(scoped)
    for decision in decisions:
        all_ids.update(decision.subject_entity_ids)
        if decision.canonical_entity_id:
            all_ids.add(decision.canonical_entity_id)
    union_find = _UnionFind(all_ids)
    canonical_targets: dict[str, str] = {}
    for decision in decisions:
        if decision.action != "merge":
            continue
        subjects = decision.subject_entity_ids
        for subject in subjects[1:]:
            union_find.union(subjects[0], subject)
        root = union_find.find(subjects[0])
        target = decision.canonical_entity_id or root
        prior = canonical_targets.get(root)
        if prior is not None and prior != target:
            raise ValueError("multiple incompatible canonical targets")
        canonical_targets[root] = target

    # Re-index targets after all unions.
    normalized_targets: dict[str, str] = {}
    for decision in decisions:
        if decision.action == "merge":
            root = union_find.find(decision.subject_entity_ids[0])
            target = decision.canonical_entity_id or root
            prior = normalized_targets.get(root)
            if prior is not None and prior != target:
                raise ValueError("multiple incompatible canonical targets")
            normalized_targets[root] = target

    def canonical(entity_id: str) -> str:
        root = union_find.find(entity_id)
        return normalized_targets.get(root, root)

    distinct_pairs: set[tuple[str, str]] = set()
    unresolved_groups: list[list[str]] = []
    for decision in decisions:
        if decision.action in {"keep_distinct", "reject_merge", "split"}:
            subjects = decision.subject_entity_ids
            for index, left in enumerate(subjects):
                for right in subjects[index + 1 :]:
                    pair = tuple(sorted((canonical(left), canonical(right))))
                    if pair[0] == pair[1]:
                        raise ValueError("identity policy marks entities as merged and distinct")
                    distinct_pairs.add(pair)
        elif decision.action == "abstain":
            unresolved_groups.append(sorted(decision.subject_entity_ids))

    groups_by_canonical: dict[str, list[str]] = {}
    for entity_id in scoped:
        groups_by_canonical.setdefault(canonical(entity_id), []).append(entity_id)
    groups = [
        CanonicalIdentityGroup(
            canonical_entity_id=canonical_id,
            member_entity_ids=sorted(members),
        )
        for canonical_id, members in sorted(groups_by_canonical.items())
    ]
    closure_hashes = {
        decision.decision_id: closures[decision.decision_id].input_fingerprint
        for decision in decisions
    }
    entity_records = {item.entity_id: item for item in bundle.entity_records}
    input_payload = {
        "policy_version": policy_version,
        "scoped_entity_ids": scoped,
        "entity_hashes": {
            entity_id: entity_records[entity_id].semantic_hash
            for entity_id in scoped
            if entity_id in entity_records
        },
        "active_decisions": [item.semantic_hash for item in decisions],
        "closure_hashes": closure_hashes,
        "superseded_decision_ids": superseded,
    }
    fingerprint = canonical_sha256(input_payload)
    return IdentitySnapshot(
        snapshot_id=f"identity-snapshot-{fingerprint[:24]}",
        policy_version=policy_version,
        scoped_entity_ids=scoped,
        groups=groups,
        distinct_pairs=[list(item) for item in sorted(distinct_pairs)],
        unresolved_groups=sorted(unresolved_groups),
        active_decision_ids=[item.decision_id for item in decisions],
        superseded_decision_ids=superseded,
        decision_closure_hashes=closure_hashes,
        input_fingerprint=fingerprint,
    )


def identity_groups_for_scope(
    snapshot: IdentitySnapshot,
    scoped_entity_ids: list[str],
) -> list[list[str]]:
    scope = set(scoped_entity_ids)
    unresolved = {
        entity_id for group in snapshot.unresolved_groups for entity_id in group
    }
    return sorted(
        [
            sorted(scope.intersection(group.member_entity_ids) - unresolved)
            for group in snapshot.groups
            if scope.intersection(group.member_entity_ids) - unresolved
        ]
    )


def rebuild_identity_snapshot(
    bundle: IdentityAwareMemoryBundleV4,
    aggregate: IdentityAggregateClaim,
) -> IdentitySnapshot:
    existing = next(
        (item for item in bundle.identity_snapshots if item.snapshot_id == aggregate.identity_snapshot_id),
        None,
    )
    policy_version = existing.policy_version if existing else "identity-policy-v1"
    return build_identity_snapshot(
        bundle,
        scoped_entity_ids=aggregate.member_entity_ids,
        policy_version=policy_version,
    )


def _aggregate_semantic_payload(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if key not in {"schema_version", "aggregate_hash"}}


def _make_aggregate_claim(
    bundle: IdentityAwareMemoryBundleV4,
    *,
    query_id: str,
    supporting_l2_claim_id: str,
    member_l1_unit_ids: list[str],
    source_role: str,
    snapshot: IdentitySnapshot,
) -> IdentityAggregateClaim:
    l1_by_id = {item.unit_id: item for item in bundle.l1_units}
    member_entity_ids: list[str] = []
    evidence_ids: list[str] = []
    for unit_id in member_l1_unit_ids:
        unit = l1_by_id[unit_id]
        role = next(item for item in unit.roles if item.role == source_role)
        member_entity_ids.append(role.entity_id)
        evidence_ids.extend(item.evidence_id for item in unit.source.evidence_spans)
    unresolved_scope = any(
        set(group).intersection(member_entity_ids) for group in snapshot.unresolved_groups
    )
    resolved = [] if unresolved_scope else sorted(
        {
            group.canonical_entity_id
            for group in snapshot.groups
            if set(group.member_entity_ids).intersection(member_entity_ids)
        }
    )
    values = {
        "aggregate_claim_id": _content_id(
            "identity-aggregate",
            {"query_id": query_id, "members": member_l1_unit_ids, "snapshot": snapshot.snapshot_id},
        ),
        "function": "count_distinct",
        "query_id": query_id,
        "supporting_l2_claim_id": supporting_l2_claim_id,
        "source_role": source_role,
        "member_l1_unit_ids": member_l1_unit_ids,
        "member_entity_ids": member_entity_ids,
        "identity_snapshot_id": snapshot.snapshot_id,
        "identity_decision_ids": snapshot.active_decision_ids,
        "resolved_canonical_entity_ids": resolved,
        "required_evidence_ids": list(dict.fromkeys(evidence_ids)),
        "value": None if unresolved_scope else len(resolved),
    }
    return IdentityAggregateClaim(
        **values,
        aggregate_hash=canonical_sha256(_aggregate_semantic_payload(values)),
    )


def _scenario_paths(experiment_root: Path) -> tuple[Path, Path, Path]:
    gold_root = experiment_root / "gold-v1"
    return (
        gold_root / "source-scenarios.json",
        gold_root / "gold.json",
        experiment_root / "schemaorg-selected-v30.json",
    )


def _scenario_payload(experiment_root: Path, scenario_id: str) -> dict[str, Any]:
    source_path, _, _ = _scenario_paths(experiment_root)
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    return next(item for item in payload["scenarios"] if item["scenario_id"] == scenario_id)


def build_identity_scenario_bundle(
    experiment_root: Path,
    scenario_id: str,
    *,
    producer: ProducerIdentity | None = None,
    transaction_time: str = "2026-07-27T08:00:00Z",
) -> IdentityAwareMemoryBundleV4:
    experiment_root = experiment_root.resolve()
    source_path, _, schemaorg_path = _scenario_paths(experiment_root)
    scenario = _scenario_payload(experiment_root, scenario_id)
    producer = producer or ProducerIdentity(
        workflow_run_id="run-identity-diagnostic-v1",
        producer_id="identity-diagnostic-builder",
        producer_version="1",
    )
    workspace_root = Path.cwd().resolve()
    try:
        relative_source = source_path.resolve().relative_to(workspace_root).as_posix()
    except ValueError:
        relative_source = source_path.resolve().as_posix()
    source_hash = _sha256_file(source_path)
    artifact = make_raw_artifact_revision(
        source_id="identity-diagnostic-v1",
        frozen_identity=source_hash,
        official_url="https://local.invalid/identity-diagnostic-v1",
        local_path=relative_source,
        reader="json",
        size_bytes=source_path.stat().st_size,
        content_sha256=source_hash,
    )
    bundle_id = _content_id(
        "identity-bundle",
        {"scenario_id": scenario_id, "source_sha256": source_hash, "builder": "1"},
    )
    source_records = []
    l1_units: list[L1MemoryUnitV2] = []
    l1_revisions = []
    mention_to_source: dict[str, Any] = {}
    mention_to_unit: dict[str, L1MemoryUnitV2] = {}
    for index, mention in enumerate(scenario["mentions"], start=1):
        source_record = make_source_record_revision(
            source_record_id=f"source-record:{scenario_id}:{mention['mention_id']}",
            revision_number=1,
            previous_revision_id=None,
            artifact_revision_id=artifact.artifact_revision_id,
            source_ref=f"scenario_id={scenario_id};mention_id={mention['mention_id']}",
            turn_id=f"turn:{scenario_id}:{index}",
            session_id=f"session:{scenario_id}:{index}",
            record_kind="normalized_session",
            text=mention["text"],
            resolver_id="identity-diagnostic-v1",
            resolver_version="1",
            transaction_time=transaction_time,
            metadata={"scenario_id": scenario_id, "mention_id": mention["mention_id"]},
        )
        source_records.append(source_record)
        mention_to_source[mention["mention_id"]] = source_record
        evidence = make_evidence_span(
            evidence_id=f"evidence:{mention['mention_id']}",
            source_revision=source_record,
            turn_id=source_record.turn_id,
            session_id=source_record.session_id,
            char_start=0,
            char_end=len(source_record.text),
            text=source_record.text,
        )
        qualifies = bool(mention["qualifies_for_count"])
        unit = L1MemoryUnitV2(
            unit_id=mention["unit_id"],
            kind="event",
            predicate=Predicate(
                surface="led" if qualifies else "mentioned",
                sense="lead/manage" if qualifies else "mention/non-member",
                canonical_operator="led_by" if qualifies else "mentioned_by",
            ),
            roles=[
                RoleBinding(
                    role="ARG0",
                    entity_id="user" if qualifies else "colleague",
                    role_name="leader" if qualifies else "speaker_subject",
                ),
                RoleBinding(
                    role="ARG1",
                    entity_id=mention["provisional_entity_id"],
                    role_name="project",
                ),
            ],
            time=TimeBinding(transaction_time=transaction_time),
            source=SourceBindingV2(
                speaker="user",
                source_status="user_reported",
                evidence_spans=[evidence],
            ),
            epistemic={
                "extraction_confidence": 1.0,
                "epistemic_trust": "high",
                "memory_utility": "useful" if qualifies else "candidate",
            },
            links=LinkBinding(),
            lifecycle="active",
        )
        l1_units.append(unit)
        mention_to_unit[mention["mention_id"]] = unit
        l1_revisions.append(
            make_memory_unit_revision(
                payload=unit,
                revision_number=1,
                previous_revision_id=None,
                revision_kind="create",
                transaction_time=transaction_time,
                source_revision_ids=[source_record.source_revision_id],
                derived_from_revision_ids=[],
                producer=producer,
            )
        )
    qualifying_mentions = [item for item in scenario["mentions"] if item["qualifies_for_count"]]
    qualifying_units = [mention_to_unit[item["mention_id"]] for item in qualifying_mentions]
    claim = L2StructuredClaim(
        claim_id=f"claim:{scenario_id}:led-projects",
        predicate=Predicate(
            surface="led projects",
            sense="lead/manage",
            canonical_operator="led_by",
        ),
        roles=[RoleBinding(role="ARG0", entity_id="user", role_name="leader")],
        supporting_l1_units=[item.unit_id for item in qualifying_units],
    )
    closure_id = f"closure:{scenario_id}:claim"
    spec = make_closure_spec(
        closure_id=closure_id,
        revision=1,
        target_id=claim.claim_id,
        pattern="multi_evidence_set",
        slots=[
            ClosureSlotSpec(
                slot_id=f"slot:{unit.unit_id}",
                role="aggregate_member",
                bound_unit_id=unit.unit_id,
            )
            for unit in qualifying_units
        ],
    )
    provisional_l2 = L2MemoryUnitV2(
        unit_id=f"l2:{scenario_id}:led-project-count",
        kind="project",
        abstracts=[item.unit_id for item in qualifying_units],
        summary="Identity-aware led project aggregate.",
        display_assertions=[],
        structured_claims=[claim],
        closure_id=closure_id,
        closure_spec_revision=1,
        closure_evaluation_id="pending",
        lifecycle="active",
        abstraction_method={"method": "rule_aggregate", "model_or_rule_version": "identity-v1"},
        source_l1_units=[item.unit_id for item in qualifying_units],
        source_turns=[item.source.evidence_spans[0].turn_id for item in qualifying_units],
        source_sessions=[item.source.evidence_spans[0].session_id for item in qualifying_units],
    )
    l1_current = {revision.memory_unit_id: revision.revision_id for revision in l1_revisions}
    provisional_bundle = MemoryRepresentationBundleV3(
        bundle_id=bundle_id,
        profile=identity_native_profile(),
        raw_artifact_revisions=[artifact],
        source_record_revisions=source_records,
        unit_revisions=l1_revisions,
        current_revision_ids=l1_current,
        l1_units=l1_units,
        l2_units=[],
        closure_specs=[],
        closure_evaluations=[],
        query_plans=[],
        metadata={
            "closure_evaluator_id": "authoritative-closure-evaluator",
            "closure_evaluator_version": "1",
            "closure_policy_version": "1",
        },
    )
    closure_inputs = ClosureEvaluationInputs(
        evaluated_bundle_id=bundle_id,
        context=ClaimClosureContext(
            l2_unit_id=provisional_l2.unit_id,
            claim_id=claim.claim_id,
            claim_hash=claim.semantic_hash,
            support_unit_ids=[item.unit_id for item in qualifying_units],
            support_scope=[item.unit_id for item in qualifying_units],
        ),
        current_revision_ids=l1_current,
        unit_revisions=l1_revisions,
        source_revisions=source_records,
        evaluator_id="authoritative-closure-evaluator",
        evaluator_version="1",
        policy_version="1",
    )
    closure_evaluation = evaluate_closure_spec(spec, closure_inputs)
    l2 = provisional_l2.model_copy(update={"closure_evaluation_id": closure_evaluation.evaluation_id})
    l2_revision = make_memory_unit_revision(
        payload=l2,
        revision_number=1,
        previous_revision_id=None,
        revision_kind="create",
        transaction_time=transaction_time,
        source_revision_ids=sorted(
            {span.source_revision_id for unit in qualifying_units for span in unit.source.evidence_spans}
        ),
        derived_from_revision_ids=[l1_current[item.unit_id] for item in qualifying_units],
        producer=producer,
    )
    query = AuthoritativeQueryPlan(
        query_id=f"query:{scenario_id}:count-led-projects",
        intent="multi_evidence",
        target_level="both",
        answer_kind="count",
        predicate_sense="lead/manage",
        canonical_operator="led_by",
        role_constraints=[RoleBinding(role="ARG0", entity_id="user", role_name="leader")],
        lifecycle="active",
    )
    current_ids = {**l1_current, l2.unit_id: l2_revision.revision_id}
    base_values = {
        "bundle_id": bundle_id,
        "profile": identity_native_profile(),
        "raw_artifact_revisions": [artifact],
        "source_record_revisions": source_records,
        "unit_revisions": [*l1_revisions, l2_revision],
        "current_revision_ids": current_ids,
        "l1_units": l1_units,
        "l2_units": [l2],
        "closure_specs": [spec],
        "closure_evaluations": [closure_evaluation],
        "query_plans": [query],
        "query_unit_scopes": {
            query.query_id: [*[item.unit_id for item in qualifying_units], l2.unit_id]
        },
        "metadata": {
            "scenario_id": scenario_id,
            "split": scenario["split"],
            "identity_policy_version": "identity-policy-v1",
            "closure_evaluator_id": "authoritative-closure-evaluator",
            "closure_evaluator_version": "1",
            "closure_policy_version": "1",
        },
    }
    entity_records: list[EntityRecord] = []
    for mention in scenario["mentions"]:
        source_record = mention_to_source[mention["mention_id"]]
        entity_records.append(
            EntityRecord(
                entity_id=mention["provisional_entity_id"],
                concept_ids=["memory:Project"],
                names=[mention["surface"]],
                identifiers=[TypedIdentifier.model_validate(item) for item in mention["identifiers"]],
                source_l1_unit_ids=[mention["unit_id"]],
                source_revision_ids=[source_record.source_revision_id],
            )
        )
    decisions: list[IdentityDecision] = []
    for item in scenario["decisions"]:
        evidence_units = [mention_to_unit[mention_id] for mention_id in item["evidence_mentions"]]
        decisions.append(
            IdentityDecision(
                decision_id=item["decision_id"],
                action=item["action"],
                status=item["status"],
                subject_entity_ids=item["subjects"],
                canonical_entity_id=item.get("canonical_entity_id"),
                reason_code=item["reason_code"],
                evidence_l1_unit_ids=[unit.unit_id for unit in evidence_units],
                evidence_source_revision_ids=sorted(
                    {
                        span.source_revision_id
                        for unit in evidence_units
                        for span in unit.source.evidence_spans
                    }
                ),
                closure_id=f"identity-closure:{item['decision_id']}",
                supersedes_decision_id=item.get("supersedes_decision_id"),
                transaction_time=transaction_time,
                producer=producer,
            )
        )
    preliminary = IdentityAwareMemoryBundleV4(
        **base_values,
        concept_registry=build_schemaorg_concept_registry(schemaorg_path),
        entity_records=entity_records,
        identity_decisions=decisions,
        identity_closures=[],
        identity_snapshots=[],
        aggregate_claims=[],
    )
    identity_closures = [evaluate_identity_closure(preliminary, item) for item in decisions]
    with_closures = preliminary.model_copy(update={"identity_closures": identity_closures})
    member_entity_ids = [
        next(role.entity_id for role in unit.roles if role.role == "ARG1")
        for unit in qualifying_units
    ]
    snapshot = build_identity_snapshot(with_closures, scoped_entity_ids=member_entity_ids)
    with_snapshot = with_closures.model_copy(update={"identity_snapshots": [snapshot]})
    aggregate = _make_aggregate_claim(
        with_snapshot,
        query_id=query.query_id,
        supporting_l2_claim_id=claim.claim_id,
        member_l1_unit_ids=[item.unit_id for item in qualifying_units],
        source_role="ARG1",
        snapshot=snapshot,
    )
    return with_snapshot.model_copy(update={"aggregate_claims": [aggregate]})


def _aggregate_errors(
    bundle: IdentityAwareMemoryBundleV4,
    aggregate: IdentityAggregateClaim,
) -> list[str]:
    errors: list[str] = []
    snapshots = {item.snapshot_id: item for item in bundle.identity_snapshots}
    snapshot = snapshots.get(aggregate.identity_snapshot_id)
    if snapshot is None:
        return [f"aggregate {aggregate.aggregate_claim_id} references missing identity snapshot"]
    l1_by_id = {item.unit_id: item for item in bundle.l1_units}
    actual_entities: list[str] = []
    actual_evidence: list[str] = []
    for unit_id in aggregate.member_l1_unit_ids:
        unit = l1_by_id.get(unit_id)
        if unit is None:
            errors.append(f"aggregate member references missing L1 unit {unit_id}")
            continue
        roles = [item for item in unit.roles if item.role == aggregate.source_role]
        if len(roles) != 1:
            errors.append(f"aggregate member {unit_id} must have exactly one {aggregate.source_role} role")
            continue
        actual_entities.append(roles[0].entity_id)
        actual_evidence.extend(item.evidence_id for item in unit.source.evidence_spans)
    if actual_entities != aggregate.member_entity_ids:
        errors.append("aggregate member entity bindings mismatch")
    if list(dict.fromkeys(actual_evidence)) != aggregate.required_evidence_ids:
        errors.append("aggregate member evidence mismatch")
    if aggregate.identity_decision_ids != snapshot.active_decision_ids:
        errors.append("aggregate identity decision set mismatch")
    try:
        rebuilt = rebuild_identity_snapshot(bundle, aggregate)
    except ValueError as exc:
        errors.append(str(exc))
        rebuilt = None
    if rebuilt is not None and rebuilt != snapshot:
        errors.append("aggregate identity snapshot is stale")
    unresolved = any(
        set(group).intersection(actual_entities) for group in snapshot.unresolved_groups
    )
    resolved = [] if unresolved else sorted(
        {
            group.canonical_entity_id
            for group in snapshot.groups
            if set(group.member_entity_ids).intersection(actual_entities)
        }
    )
    if aggregate.resolved_canonical_entity_ids != resolved:
        errors.append("aggregate resolved canonical entity set mismatch")
    expected_value = None if unresolved else len(resolved)
    if aggregate.value != expected_value:
        errors.append("aggregate value mismatch")
    if aggregate.aggregate_hash != canonical_sha256(
        _aggregate_semantic_payload(aggregate.model_dump(mode="json"))
    ):
        errors.append("aggregate hash mismatch")
    return errors


def assess_identity_bundle_integrity(
    bundle: IdentityAwareMemoryBundleV4,
) -> IdentityIntegrityReport:
    errors = list(assess_authoritative_bundle_integrity(bundle).errors)

    def duplicate_errors(kind: str, values: list[str]) -> None:
        for value in sorted({item for item in values if values.count(item) > 1}):
            errors.append(f"duplicate {kind} id {value}")

    duplicate_errors("concept", [item.concept_id for item in bundle.concept_registry])
    duplicate_errors("entity", [item.entity_id for item in bundle.entity_records])
    duplicate_errors("identity decision", [item.decision_id for item in bundle.identity_decisions])
    duplicate_errors("identity closure", [item.closure_id for item in bundle.identity_closures])
    duplicate_errors("identity snapshot", [item.snapshot_id for item in bundle.identity_snapshots])
    duplicate_errors("identity aggregate", [item.aggregate_claim_id for item in bundle.aggregate_claims])

    concept_ids = {item.concept_id for item in bundle.concept_registry}
    l1_ids = {item.unit_id for item in bundle.l1_units}
    source_ids = {item.source_revision_id for item in bundle.source_record_revisions}
    entities = {item.entity_id for item in bundle.entity_records}
    canonical_ids = {
        item.canonical_entity_id
        for item in bundle.identity_decisions
        if item.canonical_entity_id is not None
    }
    for concept in bundle.concept_registry:
        for mapping in concept.external_mappings:
            if mapping.source == "schema.org" and mapping.source_commit != "f72e60b7f67578b4af9445fa20fc8ec3fe1c9b93":
                errors.append(f"concept {concept.concept_id} uses unexpected schema.org source")
    for entity in bundle.entity_records:
        for concept_id in entity.concept_ids:
            if concept_id not in concept_ids:
                errors.append(f"entity {entity.entity_id} references missing concept {concept_id}")
        for unit_id in entity.source_l1_unit_ids:
            if unit_id not in l1_ids:
                errors.append(f"entity {entity.entity_id} references missing L1 unit {unit_id}")
        for source_id in entity.source_revision_ids:
            if source_id not in source_ids:
                errors.append(f"entity {entity.entity_id} references missing source revision {source_id}")
    decisions = {item.decision_id: item for item in bundle.identity_decisions}
    closures = {item.decision_id: item for item in bundle.identity_closures}
    for decision in bundle.identity_decisions:
        if decision.status == "accepted" and any(
            item.status == "accepted"
            and item.supersedes_decision_id == decision.decision_id
            for item in bundle.identity_decisions
        ):
            errors.append(
                f"identity superseded decision {decision.decision_id} remains active"
            )
        for entity_id in decision.subject_entity_ids:
            if entity_id not in entities and entity_id not in canonical_ids:
                errors.append(f"identity decision {decision.decision_id} references missing entity {entity_id}")
        for unit_id in decision.evidence_l1_unit_ids:
            if unit_id not in l1_ids:
                errors.append(f"identity decision {decision.decision_id} references missing evidence L1 {unit_id}")
        for source_id in decision.evidence_source_revision_ids:
            if source_id not in source_ids:
                errors.append(f"identity decision {decision.decision_id} references missing evidence source {source_id}")
        if decision.supersedes_decision_id and decision.supersedes_decision_id not in decisions:
            errors.append(f"identity decision {decision.decision_id} references missing superseded decision")
        closure = closures.get(decision.decision_id)
        if closure is None:
            errors.append(f"identity decision {decision.decision_id} has no identity closure")
        elif not is_identity_closure_fresh(bundle, closure):
            errors.append(f"identity decision {decision.decision_id} has stale identity closure")
    for snapshot in bundle.identity_snapshots:
        aggregate = next(
            (item for item in bundle.aggregate_claims if item.identity_snapshot_id == snapshot.snapshot_id),
            None,
        )
        scoped = aggregate.member_entity_ids if aggregate else snapshot.scoped_entity_ids
        try:
            rebuilt = build_identity_snapshot(
                bundle,
                scoped_entity_ids=scoped,
                policy_version=snapshot.policy_version,
            )
            if rebuilt != snapshot:
                errors.append(f"identity snapshot {snapshot.snapshot_id} is stale")
        except ValueError as exc:
            errors.append(str(exc))
    for aggregate in bundle.aggregate_claims:
        errors.extend(_aggregate_errors(bundle, aggregate))
    unique = list(dict.fromkeys(errors))
    return IdentityIntegrityReport(
        bundle_id=bundle.bundle_id,
        valid=not unique,
        errors=unique,
        metrics={
            "concept_count": len(bundle.concept_registry),
            "entity_count": len(bundle.entity_records),
            "identity_decision_count": len(bundle.identity_decisions),
            "identity_closure_count": len(bundle.identity_closures),
            "identity_snapshot_count": len(bundle.identity_snapshots),
            "aggregate_claim_count": len(bundle.aggregate_claims),
        },
    )


def execute_identity_aware_query(
    plan: AuthoritativeQueryPlan,
    bundle: IdentityAwareMemoryBundleV4,
) -> IdentityAwareQueryResult:
    base = AuthoritativeQueryResult.model_validate(execute_authoritative_query(plan, bundle))
    aggregate = next((item for item in bundle.aggregate_claims if item.query_id == plan.query_id), None)
    if plan.answer_kind != "count" or aggregate is None:
        return IdentityAwareQueryResult(
            **base.model_dump(mode="json"),
            aggregate_value=None,
            identity_snapshot_id=None,
        )
    integrity_errors = _aggregate_errors(bundle, aggregate)
    if integrity_errors:
        return IdentityAwareQueryResult(
            query_id=plan.query_id,
            matched_unit_ids=base.matched_unit_ids,
            required_evidence_ids=aggregate.required_evidence_ids,
            closure_complete=False,
            abstained=True,
            fallback_allowed=False,
            reason="identity_aggregate_invalid",
            aggregate_value=None,
            identity_snapshot_id=aggregate.identity_snapshot_id,
        )
    if aggregate.value is None:
        return IdentityAwareQueryResult(
            query_id=plan.query_id,
            matched_unit_ids=base.matched_unit_ids,
            required_evidence_ids=aggregate.required_evidence_ids,
            closure_complete=True,
            abstained=True,
            fallback_allowed=False,
            reason="identity_unresolved",
            aggregate_value=None,
            identity_snapshot_id=aggregate.identity_snapshot_id,
        )
    return IdentityAwareQueryResult(
        query_id=plan.query_id,
        matched_unit_ids=base.matched_unit_ids,
        required_evidence_ids=aggregate.required_evidence_ids,
        closure_complete=True,
        abstained=False,
        fallback_allowed=False,
        reason="identity_aggregate_complete",
        aggregate_value=aggregate.value,
        identity_snapshot_id=aggregate.identity_snapshot_id,
    )


def validate_identity_sources(
    bundle: IdentityAwareMemoryBundleV4,
    workspace_root: Path,
) -> IdentitySourceValidationReport:
    errors: list[str] = []
    replayed = 0
    workspace_root = workspace_root.resolve()
    artifacts = {item.artifact_revision_id: item for item in bundle.raw_artifact_revisions}
    source_payloads: dict[str, dict[str, Any]] = {}
    for artifact in artifacts.values():
        path = Path(artifact.local_path)
        if not path.is_absolute():
            path = workspace_root / path
        path = path.resolve()
        if workspace_root not in path.parents and path != workspace_root:
            errors.append(f"artifact path escapes workspace: {path}")
            continue
        if not path.exists():
            errors.append(f"artifact missing: {path}")
            continue
        if path.stat().st_size != artifact.size_bytes:
            errors.append(f"artifact size mismatch: {path}")
        if _sha256_file(path) != artifact.content_sha256:
            errors.append(f"artifact hash mismatch: {path}")
        try:
            source_payloads[artifact.artifact_revision_id] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"artifact parse failed: {path}: {exc}")
    for source in bundle.source_record_revisions:
        payload = source_payloads.get(source.artifact_revision_id)
        if payload is None:
            continue
        metadata = source.metadata
        scenario_id = str(metadata.get("scenario_id", ""))
        mention_id = str(metadata.get("mention_id", ""))
        scenario = next(
            (item for item in payload.get("scenarios", []) if item.get("scenario_id") == scenario_id),
            None,
        )
        mention = next(
            (item for item in (scenario or {}).get("mentions", []) if item.get("mention_id") == mention_id),
            None,
        )
        if mention is None:
            errors.append(f"source replay missing mention {scenario_id}/{mention_id}")
            continue
        if source.text != mention.get("text"):
            errors.append(f"source replay text mismatch {source.source_revision_id}")
        if source.content_sha256 != hashlib.sha256(source.text.encode("utf-8")).hexdigest():
            errors.append(f"source record content hash mismatch {source.source_revision_id}")
        replayed += 1
    unique = list(dict.fromkeys(errors))
    return IdentitySourceValidationReport(
        valid=not unique,
        errors=unique,
        metrics={
            "artifact_count": len(bundle.raw_artifact_revisions),
            "source_record_count": len(bundle.source_record_revisions),
            "source_record_replayed_count": replayed,
        },
    )
