from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools.natural_memory_benchmark.extraction_bridge_assessment import (
    replay_extraction_inputs,
)
from tools.natural_memory_benchmark.io import load_json
from tools.natural_memory_benchmark.typed_extractor_fresh_l2 import (
    freeze_fresh_l2_selection,
    prepare_fresh_l2_slice,
    validate_fresh_l2_slice,
    validate_fresh_l2_selection,
)


PREREG = Path(
    "artifacts/automatic-extraction-assessment/"
    "typed-extractor-v2-fresh-hidden-prereg-v1/preregistration.json"
)
BRIDGE = Path(
    "artifacts/automatic-extraction-assessment/bridge-v3/compatibility-ledger.json"
)
L2_DEV_ROOT = Path(
    "artifacts/automatic-extraction-assessment/typed-extractor-v2-l2-dev-v9"
)
SOURCE = Path("data/gold-candidates/KE-test.json")
TURN_MANIFEST = Path("knowledge-extraction/turn-pass/validated/manifest.json")
DIALOGUE_MANIFEST = Path("knowledge-extraction/dialogue-pass/validated/manifest.json")
FINAL_KNOWLEDGE = Path("knowledge-extraction/final-knowledge.json")
RUN = Path("knowledge-extraction/run.json")
SOURCE_SEGMENTS = Path("knowledge-extraction/source-segments.json")
PROMPT = Path(
    "artifacts/automatic-extraction-assessment/typed-extractor-v2-l2-dev-v9/"
    "proposer-prompt-l2.md"
)

EXPECTED_IDS = [
    "D_beam-cand-004-4d648a026dc4_002",
    "D_wildchat-learn-cand-003-b1871de6ef7c_002",
    "D_wildchat-learn-cand-001-8def27ce661d_002",
    "D_wildchat-mgmt-cand-003-f877bc2fc8f5_001",
    "D_taskmaster2-cand-001-5f5e1081bd0b_003",
    "D_wildchat-learn-cand-004-dc8956a5d265_002",
    "D_wildchat-mgmt-cand-002-e88f4bb1070d_001",
    "D_wildchat-learn-cand-004-dc8956a5d265_001",
]


def _freeze(root: Path) -> dict:
    return freeze_fresh_l2_selection(
        preregistration_path=PREREG,
        bridge_ledger_path=BRIDGE,
        l2_dev_root=L2_DEV_ROOT,
        source_path=SOURCE,
        turn_manifest_path=TURN_MANIFEST,
        dialogue_manifest_path=DIALOGUE_MANIFEST,
        final_knowledge_path=FINAL_KNOWLEDGE,
        run_path=RUN,
        source_segments_path=SOURCE_SEGMENTS,
        output_root=root,
    )


def test_fresh_l2_selection_uses_all_unused_cross_turn_records_in_hash_order(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"

    assert _freeze(first) == _freeze(second)
    source = load_json(first / "source-cases-l2.json")

    assert source["namespace"] == (
        "typed-extractor-l2-fresh-hidden-v1:2026-07-28"
    )
    assert source["selection_policy"] == "all_unused_bridge_v3_cross_turn"
    assert source["semantic_filtering_applied"] is False
    assert source["case_count"] == 8
    assert [case["knowledge_id"] for case in source["cases"]] == EXPECTED_IDS
    assert first.joinpath("source-cases-l2.json").read_bytes() == second.joinpath(
        "source-cases-l2.json"
    ).read_bytes()
    assert first.joinpath("source-cases-l2.json").stat().st_mode & 0o777 == 0o444


def test_fresh_l2_selection_is_dev_disjoint_and_cross_turn_closed(
    tmp_path: Path,
) -> None:
    root = tmp_path / "slice"
    _freeze(root)
    source = load_json(root / "source-cases-l2.json")
    dev = load_json(L2_DEV_ROOT / "source-cases-l2.json")
    dev_authority = load_json(L2_DEV_ROOT / "authority-l2.json")

    selected_ids = {case["knowledge_id"] for case in source["cases"]}
    dev_ids = {case["knowledge_id"] for case in dev["cases"]}
    selected_combinations = {
        tuple(sorted(case["evidence_ids"])) for case in source["cases"]
    }
    dev_combinations = {
        tuple(sorted(binding["evidence_id"] for binding in case["required_evidence_bindings"]))
        for case in dev_authority["cases"]
    }

    assert selected_ids.isdisjoint(dev_ids)
    assert selected_combinations.isdisjoint(dev_combinations)
    for case in source["cases"]:
        assert len(case["source_turns"]) >= 2
        assert len(case["source_turn_refs"]) == len(case["source_turns"])
        assert case["case_id"].startswith("case-")
        assert case["candidate_ref"].startswith("candidate-")
        assert case["source_session_ref"].startswith("session-")
        assert all(ref.startswith("turn-") for ref in case["source_turn_refs"])


def test_validate_fresh_l2_selection_replays_exact_sources(tmp_path: Path) -> None:
    root = tmp_path / "slice"
    _freeze(root)

    result = validate_fresh_l2_selection(
        preregistration_path=PREREG,
        bridge_ledger_path=BRIDGE,
        l2_dev_root=L2_DEV_ROOT,
        source_path=SOURCE,
        turn_manifest_path=TURN_MANIFEST,
        dialogue_manifest_path=DIALOGUE_MANIFEST,
        final_knowledge_path=FINAL_KNOWLEDGE,
        run_path=RUN,
        source_segments_path=SOURCE_SEGMENTS,
        root=root,
    )

    assert result == {
        "status": "valid",
        "case_count": 8,
        "selection_phase": "frozen_before_gold",
    }


def _support_ref(knowledge_id: str, index: int) -> str:
    namespace = "typed-extractor-l2-fresh-hidden-v1:2026-07-28"
    digest = hashlib.sha256(
        f"{namespace}|support|{knowledge_id}:{index}".encode()
    ).hexdigest()
    return f"support-{digest[:16]}"


def _write_abstain_adjudications(root: Path, path: Path) -> None:
    source = load_json(root / "source-cases-l2.json")
    replay = replay_extraction_inputs(
        source_path=SOURCE,
        turn_manifest_path=TURN_MANIFEST,
        dialogue_manifest_path=DIALOGUE_MANIFEST,
        final_knowledge_path=FINAL_KNOWLEDGE,
        run_path=RUN,
        source_segments_path=SOURCE_SEGMENTS,
    )
    cases = []
    for source_case in source["cases"]:
        record = replay.view.by_id[source_case["knowledge_id"]]
        turn_ref_by_index = {
            turn["turn_index"]: turn["source_turn_ref"]
            for turn in source_case["source_turns"]
        }
        grouped = {
            turn_index: [
                item
                for item in record.knowledge["evidence"]
                if item["turn_index"] == turn_index
            ]
            for turn_index in sorted(turn_ref_by_index)
        }
        support_pack = []
        for index, (turn_index, evidence) in enumerate(grouped.items(), 1):
            support_pack.append(
                {
                    "support_ref": _support_ref(source_case["knowledge_id"], index),
                    "source_turn_ref": turn_ref_by_index[turn_index],
                    "source_session_ref": source_case["source_session_ref"],
                    "kind": "state",
                    "predicate": {
                        "surface": source_case["untyped_candidate"]["predicate"],
                        "sense": "test.structural_support",
                        "canonical_operator": "test_structural_support",
                    },
                    "local_entities": [
                        {"local_entity_id": "entity-01", "surface": source_case["untyped_candidate"]["subject"]}
                    ],
                    "roles": [
                        {"role": "theme", "role_name": "结构测试主体", "local_entity_id": "entity-01"}
                    ],
                    "modality": "actual",
                    "polarity": source_case["untyped_candidate"]["qualifiers"]["polarity"],
                    "time": {"event_time": None, "valid_time": None},
                    "evidence_bindings": [
                        {
                            "evidence_id": item["evidence_id"],
                            "speaker": next(
                                public_item["speaker"]
                                for public_item in source_case["untyped_candidate"]["evidence"]
                                if public_item["evidence_id"] == item["evidence_id"]
                            ),
                        }
                        for item in sorted(evidence, key=lambda item: item["evidence_id"])
                    ],
                }
            )
        cases.append(
            {
                "private_case_id": source_case["private_case_id"],
                "knowledge_id": source_case["knowledge_id"],
                "expected_decision": "abstain",
                "typed_l1_support_pack": support_pack,
                "expected_typed_candidate": None,
                "emission_allowed": False,
                "allowed_abstraction_methods": [],
                "allowed_closure_patterns": [],
                "unresolved_required_fields": ["structural_test_abstention"],
            }
        )
    payload = {
        "schema_version": "typed-extractor-l2-source-v1",
        "dataset_id": source["dataset_id"],
        "public_vocabulary": {},
        "cases": cases,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    path.chmod(0o444)


def _prepare_final(root: Path, adjudications: Path) -> dict:
    return prepare_fresh_l2_slice(
        preregistration_path=PREREG,
        prompt_path=PROMPT,
        bridge_ledger_path=BRIDGE,
        l2_dev_root=L2_DEV_ROOT,
        source_path=SOURCE,
        turn_manifest_path=TURN_MANIFEST,
        dialogue_manifest_path=DIALOGUE_MANIFEST,
        final_knowledge_path=FINAL_KNOWLEDGE,
        run_path=RUN,
        source_segments_path=SOURCE_SEGMENTS,
        selection_root=root,
        adjudication_path=adjudications,
    )


def test_prepare_fresh_l2_slice_closes_support_and_separates_gold(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    _freeze(first)
    _freeze(second)
    first_adjudications = tmp_path / "first-adjudications.json"
    second_adjudications = tmp_path / "second-adjudications.json"
    _write_abstain_adjudications(first, first_adjudications)
    _write_abstain_adjudications(second, second_adjudications)

    assert _prepare_final(first, first_adjudications) == _prepare_final(
        second, second_adjudications
    )
    public = load_json(first / "public-l2.json")
    authority = load_json(first / "authority-l2.json")
    gold = load_json(first / "gold-l2.json")
    public_text = (first / "public-l2.json").read_text(encoding="utf-8")
    for private_field in (
        "knowledge_id",
        "candidate_id",
        "private_case_id",
        "selection_sha256",
        "expected_decision",
        "expected_typed_candidate",
        "emission_allowed",
    ):
        assert private_field not in public_text
    case_ids = {case["case_id"] for case in public["cases"]}
    assert case_ids == {case["case_id"] for case in authority["cases"]}
    assert case_ids == {item["case_id"] for item in gold["items"]}
    for case in public["cases"]:
        assert len(case["typed_l1_support_pack"]) >= 2
        assert {
            binding["evidence_id"]
            for support in case["typed_l1_support_pack"]
            for binding in support["evidence_bindings"]
        } == {
            item["evidence_id"] for item in case["untyped_candidate"]["evidence"]
        }
    for name in (
        "source-cases-l2.json",
        "adjudications-l2.json",
        "public-l2.json",
        "authority-l2.json",
        "gold-l2.json",
        "manifest-l2.json",
    ):
        assert first.joinpath(name).read_bytes() == second.joinpath(name).read_bytes()
        assert first.joinpath(name).stat().st_mode & 0o777 == 0o444

    assert validate_fresh_l2_slice(
        preregistration_path=PREREG,
        prompt_path=PROMPT,
        bridge_ledger_path=BRIDGE,
        l2_dev_root=L2_DEV_ROOT,
        source_path=SOURCE,
        turn_manifest_path=TURN_MANIFEST,
        dialogue_manifest_path=DIALOGUE_MANIFEST,
        final_knowledge_path=FINAL_KNOWLEDGE,
        run_path=RUN,
        source_segments_path=SOURCE_SEGMENTS,
        root=first,
    ) == {
        "status": "valid",
        "case_count": 8,
        "raw_gold_authored_after_selection": True,
    }
