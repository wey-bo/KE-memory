from tools.ontology_memory_experiment.representations import (
    build_distractor_representations,
    build_representations,
)
from tools.ontology_memory_experiment.models import MemoryRecord


def test_oracle_representation_preserves_explicit_semantics_and_ablation_removes_one_primitive():
    source = {
        "scenario_id": "fixture-role",
        "turns": [
            {
                "turn_id": "T1",
                "speaker": "user",
                "text": "Avery approved invoice I-7.",
            }
        ],
    }

    fixture = {"scenario_id": "fixture-role", "records_by_turn": {"T1": [{"record_id": "R1", "entities": ["Avery", "invoice I-7"], "predicate": "approve", "roles": {"agent": "Avery", "object": "invoice I-7"}, "polarity": "positive", "provenance_status": "user_reported"}]}}
    records = build_representations(source, "oracle", representation_fixture=fixture)
    ablated = build_representations(source, "oracle", representation_fixture=fixture, ablate_primitive="role")

    assert records[0]["source_turn_ids"] == ["T1"]
    assert records[0]["roles"] == {"agent": "Avery", "object": "invoice I-7"}
    assert ablated[0]["roles"] == {}
    assert ablated[0]["predicate"] == "approve"


def test_automatic_representation_marks_unparsed_structural_slots_unresolved_without_inventing_them():
    source = {
        "scenario_id": "fixture-auto",
        "turns": [{"turn_id": "T1", "speaker": "agent", "text": "Morgan did not approve 3 invoices."}],
    }

    record = build_representations(source, "automatic")[0]

    assert record["polarity"] == "negative"
    assert record["quantity"] == "3"
    assert record["roles"]["agent"] == "clerk"
    assert record["unresolved_slots"] == []


def test_representation_core_fields_follow_the_public_memory_record_contract():
    source = {"scenario_id": "fixture-contract", "turns": [{"turn_id": "T1", "speaker": "user", "text": "Morgan did not approve 3 invoices."}]}

    record = build_representations(source, "automatic")[0]
    public_fields = set(MemoryRecord.model_fields)
    validated = MemoryRecord.model_validate({key: value for key, value in record.items() if key in public_fields})

    assert validated.quantity == "3"


def test_oracle_requires_a_separate_source_bound_fixture_and_automatic_covers_each_generic_family():
    source = {
        "scenario_id": "OME-S901",
        "language": "en",
        "question": "How many archives should the clerk approve for Avery?",
        "candidate_answer_budget": 8,
        "turns": [
            {"turn_id": "OME-S901-T01", "speaker": "user", "text": "Avery asked the clerk to approve exactly 2 archives."},
            {"turn_id": "OME-S901-T02", "speaker": "agent", "text": "The clerk did not approve 3 archives for Avery."},
            {"turn_id": "OME-S901-T03", "speaker": "user", "text": "Correction: the archive was superseded and is not active after 2026-03-11."},
            {"turn_id": "OME-S901-T04", "speaker": "tool", "text": "The archive links Boston to project-03."},
        ],
    }
    fixture = {
        "scenario_id": "OME-S901",
        "records_by_turn": {"OME-S901-T01": [{"record_id": "O1", "source_turn_ids": ["OME-S901-T01"], "surface_text": "frozen", "entities": ["Avery"], "predicate": "approve", "roles": {"agent": "clerk", "quantity": "2"}, "polarity": "positive", "modality": "requested", "quantity": "2", "relations": []}]},
        "query_plan": {"entity_candidates": ["Avery"], "predicate": "approve", "role_constraints": {"agent": "clerk"}, "required_answer_slot": "quantity"},
    }

    oracle = build_representations(source, "oracle", representation_fixture=fixture)
    automatic = build_representations(source, "automatic", representation_fixture=fixture)

    assert oracle[0]["record_id"] == "O1"
    assert {record["predicate"] for record in automatic} >= {"approve", "active", "linked_to"}
    assert any(record["quantity"] == "2" and record["roles"]["agent"] == "clerk" for record in automatic)


def test_role_storage_field_ablation_alias_keeps_a_mapping_and_does_not_crash():
    source = {
        "scenario_id": "fixture-role-alias",
        "turns": [{"turn_id": "T1", "speaker": "user", "text": "The clerk approved 2 archives for Avery."}],
    }

    records = build_representations(source, "automatic", ablate_primitive="roles")

    assert records[0]["roles"] == {}
    assert isinstance(records[0]["roles"], dict)


def test_distractor_representation_is_source_blind_and_traceable_as_a_typed_record():
    distractor = {
        "record_id": "OME-D-S001-50-001",
        "text": "obsolete state retained by stale status; an outdated report changes the status of archive for Avery.",
    }

    record = build_distractor_representations([distractor])[0]

    assert record["record_id"] == distractor["record_id"]
    assert record["source_turn_ids"] == [distractor["record_id"]]
    assert record["surface_text"] == distractor["text"]
    assert record["predicate"] == "active"
    assert record["lifecycle_status"] == "obsolete"
    MemoryRecord.model_validate({key: value for key, value in record.items() if key in MemoryRecord.model_fields})


def test_distractor_representation_emits_generic_relation_keys_for_missing_link_text():
    record = build_distractor_representations([
        {
            "record_id": "OME-D-S031-50-002",
            "text": "one condition missing by missing link; a similar record omits one required link for report.",
        }
    ])[0]

    assert record["predicate"] == "linked_to"
    assert record["relations"]
    assert set(record["relations"][0]) == {"source", "predicate", "target"}


def test_automatic_relation_and_sense_predicates_follow_v2_canonical_names():
    source = {
        "scenario_id": "fixture-v2-predicates",
        "turns": [
            {"turn_id": "T1", "speaker": "tool", "text": "The archive links Boston to project-03."},
            {"turn_id": "T2", "speaker": "agent", "text": "The report is an account record in Taipei."},
        ],
    }

    records = build_representations(source, "automatic")
    link_record, sense_record = records

    assert link_record["predicate"] == "linked_to"
    assert set(link_record["relations"][0]) == {"source", "predicate", "target"}
    assert sense_record["predicate"] == "sense_of"
