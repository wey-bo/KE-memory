"""Deterministic, non-authoritative ontology linking for Local L1 proposals.

This module deliberately wraps the frozen extractor contract instead of extending it.
It generates replayable local ontology links and never persists a memory revision.
"""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .authoritative_memory import EvidenceSpanV2, canonical_sha256
from .io import canonical_json_bytes
from .typed_extractor_l1 import TypedL1Candidate


class StrictModel(BaseModel):
    """Immutable model boundary for linking inputs and diagnostic outputs."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


_CONCEPT_ID = r"^memory:[A-Za-z][A-Za-z0-9]*$"
_SHA256 = r"^[0-9a-f]{64}$"


class AdvisoryMapping(StrictModel):
    """Versioned lexical evidence which is explicitly not an authority grant."""

    source: Literal["wordnet", "schema.org"]
    source_version: str = Field(min_length=1)
    external_id: str = Field(min_length=1)
    relation: Literal["exact", "narrow", "broad", "related"]
    may_authorize_link: Literal[False] = False
    may_authorize_identity: Literal[False] = False
    may_authorize_admission: Literal[False] = False

    @field_validator(
        "may_authorize_link",
        "may_authorize_identity",
        "may_authorize_admission",
        mode="before",
    )
    @classmethod
    def require_literal_false(cls, value: object) -> object:
        if value is not False:
            raise ValueError("authority flags must be the boolean false literal")
        return value


class OntologyConcept(StrictModel):
    concept_id: str = Field(pattern=_CONCEPT_ID)
    label: str = Field(min_length=1)
    parent_concept_ids: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    advisory_mappings: list[AdvisoryMapping] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_local_lists(self) -> "OntologyConcept":
        if len(self.parent_concept_ids) != len(set(self.parent_concept_ids)):
            raise ValueError("duplicate parent concept")
        if len(self.aliases) != len(set(_normalize(item) for item in self.aliases)):
            raise ValueError("duplicate concept alias")
        return self


class PredicateRoleConstraint(StrictModel):
    """A local predicate/operator/role type requirement, never an external mapping."""

    rule_id: str = Field(min_length=1)
    predicate_surface: str = Field(min_length=1)
    predicate_sense: str = Field(min_length=1)
    canonical_operator: str = Field(min_length=1)
    role_name: str = Field(min_length=1)
    allowed_concept_ids: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_allowed_concepts(self) -> "PredicateRoleConstraint":
        if len(self.allowed_concept_ids) != len(set(self.allowed_concept_ids)):
            raise ValueError("duplicate allowed rule concept")
        return self


def _normalize_registry_payload(payload: dict[str, object]) -> dict[str, object]:
    concepts: list[dict[str, object]] = []
    for raw_concept in payload["concepts"]:
        concept = dict(raw_concept)
        concept["parent_concept_ids"] = sorted(concept["parent_concept_ids"])
        concept["aliases"] = sorted(concept["aliases"], key=_normalize)
        concept["advisory_mappings"] = sorted(
            concept["advisory_mappings"], key=canonical_json_bytes
        )
        concepts.append(concept)
    rules: list[dict[str, object]] = []
    for raw_rule in payload["predicate_role_constraints"]:
        rule = dict(raw_rule)
        rule["allowed_concept_ids"] = sorted(rule["allowed_concept_ids"])
        rules.append(rule)
    return {
        "schema_version": payload["schema_version"],
        "registry_id": payload["registry_id"],
        "version": payload["version"],
        "revision": payload["revision"],
        "concepts": sorted(concepts, key=lambda item: str(item["concept_id"])),
        "predicate_role_constraints": sorted(
            rules, key=lambda item: str(item["rule_id"])
        ),
    }


def _registry_payload_without_hash(registry: "OntologyRegistry") -> dict[str, object]:
    payload = registry.model_dump(mode="json")
    payload.pop("registry_hash", None)
    return _normalize_registry_payload(payload)


class OntologyRegistry(StrictModel):
    """Versioned local concept registry with validated local subtype closure."""

    schema_version: Literal["l1-local-ontology-registry-v1"] = (
        "l1-local-ontology-registry-v1"
    )
    registry_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    concepts: list[OntologyConcept] = Field(min_length=1)
    predicate_role_constraints: list[PredicateRoleConstraint] = Field(min_length=1)
    registry_hash: str = Field(pattern=_SHA256)

    @model_validator(mode="after")
    def validate_registry(self) -> "OntologyRegistry":
        concept_ids = [concept.concept_id for concept in self.concepts]
        if len(concept_ids) != len(set(concept_ids)):
            raise ValueError("duplicate concept")
        concept_set = set(concept_ids)
        for concept in self.concepts:
            for parent_id in concept.parent_concept_ids:
                if parent_id not in concept_set:
                    raise ValueError("unknown parent concept")

        parents = {
            concept.concept_id: tuple(concept.parent_concept_ids)
            for concept in self.concepts
        }
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(concept_id: str) -> None:
            if concept_id in visiting:
                raise ValueError("ontology parent cycle")
            if concept_id in visited:
                return
            visiting.add(concept_id)
            for parent_id in parents[concept_id]:
                visit(parent_id)
            visiting.remove(concept_id)
            visited.add(concept_id)

        for concept_id in concept_ids:
            visit(concept_id)

        rule_keys = [
            (
                rule.predicate_surface,
                rule.predicate_sense,
                rule.canonical_operator,
                rule.role_name,
            )
            for rule in self.predicate_role_constraints
        ]
        if len(rule_keys) != len(set(rule_keys)):
            raise ValueError("duplicate predicate role rule")
        rule_ids = [rule.rule_id for rule in self.predicate_role_constraints]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("duplicate predicate rule ID")
        for rule in self.predicate_role_constraints:
            if not set(rule.allowed_concept_ids).issubset(concept_set):
                raise ValueError("predicate role rule references unknown concept")

        expected_hash = canonical_sha256(_registry_payload_without_hash(self))
        if self.registry_hash != expected_hash:
            raise ValueError("registry hash does not match registry content")
        return self


class ProvisionalConceptExtensionProposal(StrictModel):
    """A non-authoritative request to extend the local ontology.

    There intentionally is no canonical concept ID field on this record.
    """

    proposal_id: str = Field(min_length=1)
    surface: str = Field(min_length=1)
    context: str = Field(min_length=1)
    suggested_parent_concept_ids: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_parents(self) -> "ProvisionalConceptExtensionProposal":
        if len(self.suggested_parent_concept_ids) != len(
            set(self.suggested_parent_concept_ids)
        ):
            raise ValueError("duplicate suggested extension parent")
        return self


class LinkEvidence(StrictModel):
    evidence_id: str = Field(min_length=1)
    basis: Literal[
        "predicate_role_compatibility",
        "local_alias",
        "demonstrative_instance_reference",
        "external_advisory_candidate",
        "unresolved_extension",
    ]
    detail: str = Field(min_length=1)


class ConceptLinkProposal(StrictModel):
    local_entity_id: str = Field(pattern=r"^entity-[0-9]{2}$")
    surface: str = Field(min_length=1)
    role_names: list[str] = Field(default_factory=list)
    context: str = Field(min_length=1)
    candidate_concept_ids: list[str] = Field(default_factory=list)
    selected_concept_ids: list[str] = Field(default_factory=list)
    advisory_mappings: list[AdvisoryMapping] = Field(default_factory=list)
    evidence: list[LinkEvidence] = Field(min_length=1)
    extension_proposal: ProvisionalConceptExtensionProposal | None = None

    @model_validator(mode="after")
    def validate_selection(self) -> "ConceptLinkProposal":
        if len(self.candidate_concept_ids) != len(set(self.candidate_concept_ids)):
            raise ValueError("duplicate concept candidate")
        if len(self.selected_concept_ids) != len(set(self.selected_concept_ids)):
            raise ValueError("duplicate selected concept")
        if not set(self.selected_concept_ids).issubset(set(self.candidate_concept_ids)):
            raise ValueError("selected concept is not a candidate")
        if self.extension_proposal is not None and self.selected_concept_ids:
            raise ValueError("extension proposal cannot select a canonical concept")
        return self


class CanonicalEntityBinding(StrictModel):
    """An identity snapshot supplied by a caller; the linker never mints one."""

    local_entity_id: str = Field(pattern=r"^entity-[0-9]{2}$")
    canonical_entity_id: str | None = Field(default=None, min_length=1)
    identity_status: Literal["resolved", "unresolved"]
    identity_snapshot_id: str = Field(min_length=1)
    identity_snapshot_revision: str = Field(min_length=1)
    identity_snapshot_hash: str = Field(pattern=_SHA256)
    identity_registry_revision: str = Field(min_length=1)
    identity_registry_hash: str = Field(pattern=_SHA256)
    concept_type_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_identity_shape(self) -> "CanonicalEntityBinding":
        if self.identity_status == "resolved" and self.canonical_entity_id is None:
            raise ValueError("resolved identity binding requires a canonical entity ID")
        if self.identity_status == "unresolved" and self.canonical_entity_id is not None:
            raise ValueError("unresolved identity binding cannot name a canonical entity")
        if len(self.concept_type_ids) != len(set(self.concept_type_ids)):
            raise ValueError("duplicate identity concept type")
        return self


class EntityLinkProposal(StrictModel):
    local_entity_id: str = Field(pattern=r"^entity-[0-9]{2}$")
    surface: str = Field(min_length=1)
    interpretation: Literal["category", "individual", "unresolved"]
    concept: ConceptLinkProposal
    selected_concept_ids: list[str] = Field(default_factory=list)
    canonical_entity_id: str | None = None
    canonical_entity_binding: CanonicalEntityBinding | None = None

    @model_validator(mode="after")
    def validate_entity_shape(self) -> "EntityLinkProposal":
        if self.local_entity_id != self.concept.local_entity_id:
            raise ValueError("entity link and concept link local IDs differ")
        if self.selected_concept_ids != self.concept.selected_concept_ids:
            raise ValueError("entity link selection does not match concept link")
        if self.interpretation == "category":
            if self.canonical_entity_id is not None or self.canonical_entity_binding is not None:
                raise ValueError("category link cannot contain an identity binding")
        elif self.interpretation == "individual":
            if self.canonical_entity_binding is None:
                raise ValueError("individual link requires an identity binding")
            if self.canonical_entity_binding.identity_status != "resolved":
                raise ValueError("individual link requires resolved identity")
            if self.canonical_entity_id != self.canonical_entity_binding.canonical_entity_id:
                raise ValueError("individual link must copy caller canonical entity ID")
        elif self.canonical_entity_id is not None:
            raise ValueError("unresolved link cannot contain a canonical entity ID")
        return self


class PredicateLinkProposal(StrictModel):
    predicate_surface: str = Field(min_length=1)
    predicate_sense: str = Field(min_length=1)
    canonical_operator: str = Field(min_length=1)
    matched_rule_ids: list[str] = Field(default_factory=list)
    evidence: list[LinkEvidence] = Field(min_length=1)


def _linked_payload_without_hash(linked: "LinkedL1Candidate") -> dict[str, object]:
    payload = linked.model_dump(mode="json")
    payload.pop("linked_candidate_hash", None)
    return payload


class LinkedL1Candidate(StrictModel):
    """Immutable envelope binding a local proposal to link inputs and outputs."""

    schema_version: Literal["linked-l1-candidate-v1"] = "linked-l1-candidate-v1"
    typed_candidate: TypedL1Candidate
    typed_candidate_canonical_bytes: bytes = Field(min_length=1)
    source_candidate_hash: str = Field(pattern=_SHA256)
    evidence_spans: list[EvidenceSpanV2] = Field(min_length=1)
    entity_links: list[EntityLinkProposal] = Field(min_length=1)
    predicate_link: PredicateLinkProposal
    unresolved_local_entity_ids: list[str] = Field(default_factory=list)
    registry_id: str = Field(min_length=1)
    registry_version: str = Field(min_length=1)
    registry_revision: str = Field(min_length=1)
    registry_canonical_bytes: bytes = Field(min_length=1)
    registry_hash: str = Field(pattern=_SHA256)
    linked_candidate_hash: str = Field(pattern=_SHA256)

    @model_validator(mode="after")
    def validate_envelope(self) -> "LinkedL1Candidate":
        source_bytes = canonical_json_bytes(self.typed_candidate)
        if self.typed_candidate_canonical_bytes != source_bytes:
            raise ValueError("source candidate canonical bytes do not match candidate")
        if self.source_candidate_hash != hashlib.sha256(source_bytes).hexdigest():
            raise ValueError("source candidate hash does not match candidate")
        if self.registry_hash != hashlib.sha256(self.registry_canonical_bytes).hexdigest():
            raise ValueError("registry hash does not match registry bytes")
        evidence_ids = [span.evidence_id for span in self.evidence_spans]
        candidate_evidence_ids = [
            binding.evidence_id for binding in self.typed_candidate.evidence_bindings
        ]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("duplicate evidence span")
        if set(evidence_ids) != set(candidate_evidence_ids):
            raise ValueError("evidence span closure does not match source candidate")
        local_ids = [entity.local_entity_id for entity in self.typed_candidate.local_entities]
        if [link.local_entity_id for link in self.entity_links] != local_ids:
            raise ValueError("entity links do not preserve source local entity order")
        unresolved = [
            link.local_entity_id
            for link in self.entity_links
            if link.interpretation == "unresolved"
        ]
        if self.unresolved_local_entity_ids != unresolved:
            raise ValueError("unresolved local entity IDs do not match entity links")
        bound_evidence = set(evidence_ids)
        for link in [
            *(entity.concept for entity in self.entity_links),
            self.predicate_link,
        ]:
            if not {item.evidence_id for item in link.evidence}.issubset(bound_evidence):
                raise ValueError("link evidence is not bound to an evidence span")
        expected_hash = canonical_sha256(_linked_payload_without_hash(self))
        if self.linked_candidate_hash != expected_hash:
            raise ValueError("linked candidate hash does not match envelope")
        return self


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _registry_bytes(registry: OntologyRegistry) -> bytes:
    return canonical_json_bytes(_registry_payload_without_hash(registry))


def ontology_registry_canonical_bytes(registry: OntologyRegistry) -> bytes:
    """Return the order-normalized canonical registry bytes used by all hashes."""

    return _registry_bytes(registry)


def _json_compatible(value: object) -> object:
    """Recursively prepare mixed Pydantic inputs for the shared JSON encoder."""

    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_json_compatible(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_compatible(item) for key, item in value.items()}
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


def _make_registry(payload: dict[str, object]) -> OntologyRegistry:
    # canonical_json_bytes only unwraps a top-level model, so normalize this
    # factory input before hashing its nested concept and rule models.
    serialized = _json_compatible(payload)
    assert isinstance(serialized, dict)
    serialized.setdefault("schema_version", "l1-local-ontology-registry-v1")
    serialized["registry_hash"] = canonical_sha256(
        _normalize_registry_payload(serialized)
    )
    return OntologyRegistry.model_validate(serialized)


def build_diagnostic_ontology_registry() -> OntologyRegistry:
    """Return the small dev-v1 local ontology, including only advisory mappings."""

    wordnet_coffee = AdvisoryMapping(
        source="wordnet",
        source_version="3.0",
        external_id="wn:coffee.n.01",
        relation="exact",
    )
    schema_beverage = AdvisoryMapping(
        source="schema.org",
        source_version="30.0",
        external_id="schema:Drink",
        relation="broad",
    )
    concepts = [
        OntologyConcept(concept_id="memory:Entity", label="Entity"),
        OntologyConcept(
            concept_id="memory:Person",
            label="Person",
            parent_concept_ids=["memory:Entity"],
        ),
        OntologyConcept(
            concept_id="memory:Consumable",
            label="Consumable",
            parent_concept_ids=["memory:Entity"],
        ),
        OntologyConcept(
            concept_id="memory:Ingredient",
            label="Ingredient",
            parent_concept_ids=["memory:Consumable"],
        ),
        OntologyConcept(
            concept_id="memory:Beverage",
            label="Beverage",
            parent_concept_ids=["memory:Consumable"],
            aliases=["beverage", "drink"],
            advisory_mappings=[schema_beverage],
        ),
        OntologyConcept(
            concept_id="memory:TeaBeverage",
            label="Tea beverage",
            parent_concept_ids=["memory:Beverage"],
            aliases=["tea"],
        ),
        OntologyConcept(
            concept_id="memory:CoffeeBeverage",
            label="Coffee beverage",
            parent_concept_ids=["memory:Beverage"],
            aliases=["coffee"],
            advisory_mappings=[wordnet_coffee],
        ),
        OntologyConcept(
            concept_id="memory:MilkBeverage",
            label="Milk beverage",
            parent_concept_ids=["memory:Beverage"],
            aliases=["milk"],
        ),
        OntologyConcept(
            concept_id="memory:DairyIngredient",
            label="Dairy ingredient",
            parent_concept_ids=["memory:Ingredient"],
            aliases=["milk"],
        ),
    ]
    rules = [
        PredicateRoleConstraint(
            rule_id="prefer-theme-beverage-v1",
            predicate_surface="prefer",
            predicate_sense="preference_theme",
            canonical_operator="prefer",
            role_name="theme",
            allowed_concept_ids=["memory:Beverage"],
        ),
        PredicateRoleConstraint(
            rule_id="drink-theme-beverage-v1",
            predicate_surface="drink",
            predicate_sense="consume_beverage",
            canonical_operator="drink",
            role_name="theme",
            allowed_concept_ids=["memory:Beverage"],
        ),
        PredicateRoleConstraint(
            rule_id="add-theme-ingredient-v1",
            predicate_surface="add",
            predicate_sense="add_ingredient",
            canonical_operator="add_ingredient",
            role_name="theme",
            allowed_concept_ids=["memory:Ingredient"],
        ),
        PredicateRoleConstraint(
            rule_id="add-destination-beverage-v1",
            predicate_surface="add",
            predicate_sense="add_ingredient",
            canonical_operator="add_ingredient",
            role_name="destination",
            allowed_concept_ids=["memory:Beverage"],
        ),
    ]
    return _make_registry(
        {
            "registry_id": "memory:diagnostic-l1-ontology",
            "version": "dev-v1",
            "revision": "2026-07-29",
            "concepts": concepts,
            "predicate_role_constraints": rules,
        }
    )


def is_subtype(registry: OntologyRegistry, concept_id: str, parent_concept_id: str) -> bool:
    """Return local reflexive/transitive subtype membership, never external mappings."""

    parents = {
        concept.concept_id: tuple(concept.parent_concept_ids)
        for concept in registry.concepts
    }
    if concept_id not in parents or parent_concept_id not in parents:
        return False
    pending = [concept_id]
    seen: set[str] = set()
    while pending:
        current = pending.pop()
        if current == parent_concept_id:
            return True
        if current in seen:
            continue
        seen.add(current)
        pending.extend(parents[current])
    return False


def _matching_rules(
    candidate: TypedL1Candidate, registry: OntologyRegistry, role_name: str
) -> list[PredicateRoleConstraint]:
    return [
        rule
        for rule in registry.predicate_role_constraints
        if rule.predicate_surface == candidate.predicate.surface
        and rule.predicate_sense == candidate.predicate.sense
        and rule.canonical_operator == candidate.predicate.canonical_operator
        and rule.role_name == role_name
    ]


def _matching_concepts(surface: str, registry: OntologyRegistry) -> list[OntologyConcept]:
    normalized_surface = _normalize(surface)
    for prefix in ("this cup of ", "that cup of ", "the cup of "):
        if normalized_surface.startswith(prefix):
            normalized_surface = normalized_surface[len(prefix) :]
            break
    candidates = [
        concept
        for concept in registry.concepts
        if any(
            normalized_alias == normalized_surface
            for normalized_alias in (_normalize(alias) for alias in concept.aliases)
        )
    ]
    return sorted(candidates, key=lambda concept: concept.concept_id)


def _is_demonstrative_instance(surface: str) -> bool:
    normalized = _normalize(surface)
    return normalized.startswith(("this ", "that ", "the ")) or " cup" in normalized


def _extension_proposal(
    *, surface: str, context: str, parent_ids: list[str]
) -> ProvisionalConceptExtensionProposal:
    seed = canonical_json_bytes(
        {"surface": _normalize(surface), "context": context, "parents": parent_ids}
    )
    return ProvisionalConceptExtensionProposal(
        proposal_id=f"extension-{hashlib.sha256(seed).hexdigest()[:16]}",
        surface=surface,
        context=context,
        suggested_parent_concept_ids=parent_ids,
    )


def link_l1_candidate(
    candidate: TypedL1Candidate,
    registry: OntologyRegistry,
    evidence_spans: list[EvidenceSpanV2],
    canonical_entity_bindings: list[CanonicalEntityBinding] | None = None,
) -> LinkedL1Candidate:
    """Link one local L1 candidate without mutating any memory or identity state."""

    expected_evidence_ids = [binding.evidence_id for binding in candidate.evidence_bindings]
    supplied_evidence_ids = [span.evidence_id for span in evidence_spans]
    if len(supplied_evidence_ids) != len(set(supplied_evidence_ids)) or set(
        supplied_evidence_ids
    ) != set(expected_evidence_ids):
        raise ValueError("evidence spans must exactly close source candidate evidence")

    bindings = [
        binding.model_copy(
            update={"concept_type_ids": sorted(binding.concept_type_ids)}
        )
        for binding in (canonical_entity_bindings or [])
    ]
    binding_by_local_id = {binding.local_entity_id: binding for binding in bindings}
    if len(binding_by_local_id) != len(bindings):
        raise ValueError("duplicate canonical entity binding")
    source_local_ids = {entity.local_entity_id for entity in candidate.local_entities}
    if not set(binding_by_local_id).issubset(source_local_ids):
        raise ValueError("identity binding references unknown local entity")

    evidence_id = sorted(expected_evidence_ids)[0]
    entity_links: list[EntityLinkProposal] = []
    for local_entity in candidate.local_entities:
        role_names = sorted(
            role.role_name
            for role in candidate.roles
            if role.local_entity_id == local_entity.local_entity_id
        )
        rules = [
            rule
            for role_name in role_names
            for rule in _matching_rules(candidate, registry, role_name)
        ]
        allowed_ids = sorted(
            {
                concept_id
                for rule in rules
                for concept_id in rule.allowed_concept_ids
            }
        )
        local_candidates = _matching_concepts(local_entity.surface, registry)
        compatible_candidates = [
            concept
            for concept in local_candidates
            if any(
                is_subtype(registry, concept.concept_id, allowed_id)
                for allowed_id in allowed_ids
            )
        ]
        candidate_ids = [concept.concept_id for concept in compatible_candidates]
        context = (
            f"{candidate.predicate.canonical_operator}:"
            f"{','.join(role_names) or 'unbound'}"
        )
        concept_evidence = [
            LinkEvidence(
                evidence_id=evidence_id,
                basis="predicate_role_compatibility",
                detail=context,
            )
        ]
        if len(compatible_candidates) == 1:
            selected_ids = [compatible_candidates[0].concept_id]
            concept_evidence.append(
                LinkEvidence(
                    evidence_id=evidence_id,
                    basis="local_alias",
                    detail=compatible_candidates[0].concept_id,
                )
            )
            extension = None
        else:
            selected_ids = []
            extension = _extension_proposal(
                surface=local_entity.surface,
                context=context,
                parent_ids=allowed_ids or ["memory:Entity"],
            )
            concept_evidence.append(
                LinkEvidence(
                    evidence_id=evidence_id,
                    basis="unresolved_extension",
                    detail=extension.proposal_id,
                )
            )
        mappings = sorted(
            [
                mapping
                for concept in compatible_candidates
                for mapping in concept.advisory_mappings
            ],
            key=lambda mapping: canonical_json_bytes(mapping),
        )
        concept_link = ConceptLinkProposal(
            local_entity_id=local_entity.local_entity_id,
            surface=local_entity.surface,
            role_names=role_names,
            context=context,
            candidate_concept_ids=candidate_ids,
            selected_concept_ids=selected_ids,
            advisory_mappings=mappings,
            evidence=concept_evidence,
            extension_proposal=extension,
        )
        caller_binding = binding_by_local_id.get(local_entity.local_entity_id)
        if _is_demonstrative_instance(local_entity.surface):
            if caller_binding is None or caller_binding.identity_status != "resolved":
                interpretation = "unresolved"
                canonical_entity_id = None
                retained_binding = caller_binding
            elif not selected_ids or not set(selected_ids).issubset(
                set(caller_binding.concept_type_ids)
            ):
                interpretation = "unresolved"
                canonical_entity_id = None
                retained_binding = caller_binding
            else:
                interpretation = "individual"
                canonical_entity_id = caller_binding.canonical_entity_id
                retained_binding = caller_binding
        elif caller_binding is not None:
            interpretation = "unresolved"
            canonical_entity_id = None
            retained_binding = caller_binding
        elif selected_ids:
            interpretation = "category"
            canonical_entity_id = None
            retained_binding = None
        else:
            interpretation = "unresolved"
            canonical_entity_id = None
            retained_binding = None
        entity_links.append(
            EntityLinkProposal(
                local_entity_id=local_entity.local_entity_id,
                surface=local_entity.surface,
                interpretation=interpretation,
                concept=concept_link,
                selected_concept_ids=selected_ids,
                canonical_entity_id=canonical_entity_id,
                canonical_entity_binding=retained_binding,
            )
        )

    predicate_rules = [
        rule
        for role in candidate.roles
        for rule in _matching_rules(candidate, registry, role.role_name)
    ]
    predicate_link = PredicateLinkProposal(
        predicate_surface=candidate.predicate.surface,
        predicate_sense=candidate.predicate.sense,
        canonical_operator=candidate.predicate.canonical_operator,
        matched_rule_ids=sorted({rule.rule_id for rule in predicate_rules}),
        evidence=[
            LinkEvidence(
                evidence_id=evidence_id,
                basis="predicate_role_compatibility",
                detail=candidate.predicate.canonical_operator,
            )
        ],
    )
    source_bytes = canonical_json_bytes(candidate)
    registry_bytes = _registry_bytes(registry)
    envelope = {
        "schema_version": "linked-l1-candidate-v1",
        "typed_candidate": candidate,
        "typed_candidate_canonical_bytes": source_bytes,
        "source_candidate_hash": hashlib.sha256(source_bytes).hexdigest(),
        "evidence_spans": sorted(evidence_spans, key=lambda span: span.evidence_id),
        "entity_links": entity_links,
        "predicate_link": predicate_link,
        "unresolved_local_entity_ids": [
            link.local_entity_id
            for link in entity_links
            if link.interpretation == "unresolved"
        ],
        "registry_id": registry.registry_id,
        "registry_version": registry.version,
        "registry_revision": registry.revision,
        "registry_canonical_bytes": registry_bytes,
        "registry_hash": registry.registry_hash,
    }
    serialized_envelope = _json_compatible(envelope)
    assert isinstance(serialized_envelope, dict)
    envelope["linked_candidate_hash"] = canonical_sha256(serialized_envelope)
    return LinkedL1Candidate.model_validate(envelope)
