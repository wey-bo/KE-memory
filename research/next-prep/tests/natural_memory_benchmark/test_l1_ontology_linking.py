from __future__ import annotations

from hashlib import sha256

import pytest
from pydantic import ValidationError

from tools.natural_memory_benchmark.authoritative_memory import EvidenceSpanV2
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
from tools.natural_memory_benchmark.l1_ontology_linking import (
    AdvisoryMapping,
    CanonicalEntityBinding,
    OntologyConcept,
    OntologyRegistry,
    PredicateRoleConstraint,
    ProvisionalConceptExtensionProposal,
    build_diagnostic_ontology_registry,
    is_subtype,
    link_l1_candidate,
)


def _candidate(
    *,
    predicate: str,
    sense: str,
    operator: str,
    entities: list[str],
    roles: list[tuple[str, str]],
) -> TypedL1Candidate:
    return TypedL1Candidate(
        kind="preference" if predicate == "prefer" else "event",
        predicate=TypedPredicate(
            surface=predicate, sense=sense, canonical_operator=operator
        ),
        local_entities=[
            TypedLocalEntity(local_entity_id=f"entity-{index:02d}", surface=surface)
            for index, surface in enumerate(entities, start=1)
        ],
        roles=[
            TypedRoleBinding(
                role=role,
                role_name=role,
                local_entity_id=f"entity-{entity_index:02d}",
            )
            for role, entity_index in roles
        ],
        modality="actual",
        polarity="positive",
        time=TypedTimeBinding(),
        derivation=TypedDerivationProvenance(
            method="explicit", evidence_ids=["evidence-01"]
        ),
        evidence_bindings=[TypedEvidenceBinding(evidence_id="evidence-01", speaker="user")],
        lifecycle=TypedLifecycleBinding(lifecycle="active"),
        operation_provenance=TypedOperationProvenance(),
    )


def _spans(candidate: TypedL1Candidate) -> list[EvidenceSpanV2]:
    return [
        EvidenceSpanV2(
            evidence_id=binding.evidence_id,
            source_revision_id="source-revision-01",
            turn_id="turn-01",
            session_id="session-01",
            char_start=0,
            char_end=12,
            text="I said this.",
            quote_sha256=sha256(b"I said this.").hexdigest(),
        )
        for binding in candidate.evidence_bindings
    ]


def _registry_payload() -> dict[str, object]:
    registry = build_diagnostic_ontology_registry()
    return registry.model_dump(mode="json")


def test_registry_rejects_duplicate_missing_and_cyclic_concepts() -> None:
    duplicate = _registry_payload()
    duplicate["concepts"] = [
        *duplicate["concepts"],
        duplicate["concepts"][0],
    ]
    with pytest.raises(ValidationError, match="duplicate concept"):
        OntologyRegistry.model_validate(duplicate)

    missing_parent = _registry_payload()
    missing_parent["concepts"][0]["parent_concept_ids"] = ["memory:missing"]
    with pytest.raises(ValidationError, match="unknown parent"):
        OntologyRegistry.model_validate(missing_parent)

    cyclic = _registry_payload()
    cyclic["concepts"][0]["parent_concept_ids"] = ["memory:Person"]
    cyclic["concepts"][1]["parent_concept_ids"] = ["memory:Entity"]
    with pytest.raises(ValidationError, match="cycle"):
        OntologyRegistry.model_validate(cyclic)


def test_registry_hash_and_external_mappings_are_strictly_validated() -> None:
    payload = _registry_payload()
    payload["revision"] = "changed-without-hash"
    with pytest.raises(ValidationError, match="registry hash"):
        OntologyRegistry.model_validate(payload)

    with pytest.raises(ValidationError):
        AdvisoryMapping(
            source="wordnet",
            source_version="3.0",
            external_id="wn:coffee.n.01",
            relation="close_match",
            may_authorize_link=True,
        )


def test_extension_proposal_has_no_canonical_concept_id_field() -> None:
    proposal = ProvisionalConceptExtensionProposal(
        proposal_id="extension-unknown-drink",
        surface="mystery tonic",
        context="drink theme",
        suggested_parent_concept_ids=["memory:Beverage"],
    )
    assert "canonical_concept_id" not in proposal.model_dump()
    with pytest.raises(ValidationError):
        ProvisionalConceptExtensionProposal(
            proposal_id="extension-unknown-drink",
            surface="mystery tonic",
            context="drink theme",
            suggested_parent_concept_ids=["memory:Beverage"],
            canonical_concept_id="memory:MysteryTonic",
        )


def test_subtype_closure_uses_only_local_registry_concepts() -> None:
    registry = build_diagnostic_ontology_registry()
    assert is_subtype(registry, "memory:CoffeeBeverage", "memory:Beverage")
    assert not is_subtype(registry, "memory:CoffeeBeverage", "schema:Drink")
    assert not is_subtype(registry, "memory:Beverage", "memory:CoffeeBeverage")


def test_preference_for_coffee_links_category_not_individual() -> None:
    candidate = _candidate(
        predicate="prefer",
        sense="preference_theme",
        operator="prefer",
        entities=["coffee"],
        roles=[("theme", 1)],
    )
    linked = link_l1_candidate(candidate, build_diagnostic_ontology_registry(), _spans(candidate))
    entity = linked.entity_links[0]
    assert entity.interpretation == "category"
    assert entity.selected_concept_ids == ["memory:CoffeeBeverage"]
    assert entity.canonical_entity_id is None


def test_specific_coffee_cup_requires_and_copies_explicit_caller_identity() -> None:
    candidate = _candidate(
        predicate="drink",
        sense="consume_beverage",
        operator="drink",
        entities=["this cup of coffee"],
        roles=[("theme", 1)],
    )
    absent = link_l1_candidate(candidate, build_diagnostic_ontology_registry(), _spans(candidate))
    assert absent.entity_links[0].interpretation == "unresolved"
    assert absent.entity_links[0].canonical_entity_id is None

    binding = CanonicalEntityBinding(
        local_entity_id="entity-01",
        canonical_entity_id="entity:coffee-cup-42",
        identity_status="resolved",
        identity_snapshot_id="identity-snapshot-01",
        identity_snapshot_hash="a" * 64,
        identity_registry_revision="identity-r1",
        concept_type_ids=["memory:CoffeeBeverage"],
    )
    linked = link_l1_candidate(
        candidate, build_diagnostic_ontology_registry(), _spans(candidate), [binding]
    )
    entity = linked.entity_links[0]
    assert entity.interpretation == "individual"
    assert entity.canonical_entity_id == binding.canonical_entity_id
    assert entity.selected_concept_ids == ["memory:CoffeeBeverage"]


def test_milk_uses_predicate_role_context_to_select_distinct_local_senses() -> None:
    drink = _candidate(
        predicate="drink",
        sense="consume_beverage",
        operator="drink",
        entities=["milk"],
        roles=[("theme", 1)],
    )
    ingredient = _candidate(
        predicate="add",
        sense="add_ingredient",
        operator="add_ingredient",
        entities=["milk", "coffee"],
        roles=[("theme", 1), ("destination", 2)],
    )
    registry = build_diagnostic_ontology_registry()
    drink_linked = link_l1_candidate(drink, registry, _spans(drink))
    ingredient_linked = link_l1_candidate(ingredient, registry, _spans(ingredient))
    assert drink_linked.entity_links[0].selected_concept_ids == ["memory:MilkBeverage"]
    assert ingredient_linked.entity_links[0].selected_concept_ids == ["memory:DairyIngredient"]
    assert ingredient_linked.entity_links[1].selected_concept_ids == ["memory:CoffeeBeverage"]


def test_unknown_surface_is_preserved_as_unresolved_extension_without_invented_id() -> None:
    candidate = _candidate(
        predicate="drink",
        sense="consume_beverage",
        operator="drink",
        entities=["mystery tonic"],
        roles=[("theme", 1)],
    )
    linked = link_l1_candidate(candidate, build_diagnostic_ontology_registry(), _spans(candidate))
    entity = linked.entity_links[0]
    assert entity.interpretation == "unresolved"
    assert entity.canonical_entity_id is None
    assert entity.concept.extension_proposal is not None
    assert "canonical_concept_id" not in entity.concept.extension_proposal.model_dump()
    assert linked.unresolved_local_entity_ids == ["entity-01"]


def test_linked_envelope_binds_source_hash_evidence_registry_and_replays_deterministically() -> None:
    candidate = _candidate(
        predicate="prefer",
        sense="preference_theme",
        operator="prefer",
        entities=["coffee"],
        roles=[("theme", 1)],
    )
    registry = build_diagnostic_ontology_registry()
    spans = _spans(candidate)
    first = link_l1_candidate(candidate, registry, spans)
    second = link_l1_candidate(candidate, registry, spans)
    assert first == second
    assert first.source_candidate_hash == sha256(
        first.typed_candidate_canonical_bytes
    ).hexdigest()
    assert first.registry_hash == registry.registry_hash
    assert first.evidence_spans == spans

    stale = first.model_dump(mode="json")
    stale["registry_hash"] = "b" * 64
    with pytest.raises(ValidationError, match="registry hash"):
        type(first).model_validate(stale)


def test_linking_rejects_incomplete_evidence_span_closure() -> None:
    candidate = _candidate(
        predicate="prefer",
        sense="preference_theme",
        operator="prefer",
        entities=["coffee"],
        roles=[("theme", 1)],
    )
    with pytest.raises(ValueError, match="evidence"):
        link_l1_candidate(candidate, build_diagnostic_ontology_registry(), [])


@pytest.mark.parametrize(
    ("predicate", "sense", "operator", "surface"),
    [
        ("prefer", "preference_theme", "prefer", "mystery coffee"),
        ("drink", "consume_beverage", "drink", "almond milk"),
        ("prefer", "preference_theme", "prefer", "not coffee"),
        ("prefer", "preference_theme", "prefer", "my coffee"),
    ],
)
def test_residual_modifiers_never_inherit_an_alias_link(
    predicate: str, sense: str, operator: str, surface: str
) -> None:
    candidate = _candidate(
        predicate=predicate,
        sense=sense,
        operator=operator,
        entities=[surface],
        roles=[("theme", 1)],
    )

    linked = link_l1_candidate(
        candidate, build_diagnostic_ontology_registry(), _spans(candidate)
    )

    assert linked.entity_links[0].interpretation == "unresolved"
    assert linked.entity_links[0].selected_concept_ids == []
    assert linked.unresolved_local_entity_ids == ["entity-01"]


def test_registry_hash_normalizes_nonsemantic_collection_order() -> None:
    registry = build_diagnostic_ontology_registry()
    payload = registry.model_dump(mode="json")
    payload["concepts"] = list(reversed(payload["concepts"]))
    payload["predicate_role_constraints"] = list(
        reversed(payload["predicate_role_constraints"])
    )
    for concept in payload["concepts"]:
        concept["aliases"] = list(reversed(concept["aliases"]))
        concept["parent_concept_ids"] = list(
            reversed(concept["parent_concept_ids"])
        )
        concept["advisory_mappings"] = list(
            reversed(concept["advisory_mappings"])
        )

    permuted = OntologyRegistry.model_validate(payload)

    assert permuted.registry_hash == registry.registry_hash


def test_registry_rejects_duplicate_rule_ids() -> None:
    payload = _registry_payload()
    payload["predicate_role_constraints"][1]["rule_id"] = payload[
        "predicate_role_constraints"
    ][0]["rule_id"]

    with pytest.raises(ValidationError, match="duplicate predicate rule ID"):
        OntologyRegistry.model_validate(payload)


def test_linked_hash_normalizes_evidence_and_identity_type_order() -> None:
    base = _candidate(
        predicate="drink",
        sense="consume_beverage",
        operator="drink",
        entities=["this cup of coffee"],
        roles=[("theme", 1)],
    )
    payload = base.model_dump(mode="json")
    payload["evidence_bindings"] = [
        {"evidence_id": "evidence-01", "speaker": "user"},
        {"evidence_id": "evidence-02", "speaker": "user"},
    ]
    payload["derivation"]["evidence_ids"] = ["evidence-01", "evidence-02"]
    candidate = TypedL1Candidate.model_validate(payload)
    spans = _spans(candidate)
    first_binding = CanonicalEntityBinding(
        local_entity_id="entity-01",
        canonical_entity_id="entity:coffee-cup-42",
        identity_status="resolved",
        identity_snapshot_id="identity-snapshot-01",
        identity_snapshot_hash="a" * 64,
        identity_registry_revision="identity-r1",
        concept_type_ids=["memory:CoffeeBeverage", "memory:Beverage"],
    )
    second_binding = first_binding.model_copy(
        update={"concept_type_ids": list(reversed(first_binding.concept_type_ids))}
    )
    registry = build_diagnostic_ontology_registry()

    first = link_l1_candidate(candidate, registry, spans, [first_binding])
    second = link_l1_candidate(
        candidate, registry, list(reversed(spans)), [second_binding]
    )

    assert first == second
    assert first.linked_candidate_hash == second.linked_candidate_hash
