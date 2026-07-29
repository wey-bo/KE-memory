from __future__ import annotations

import json
from pathlib import Path

from tools.natural_memory_benchmark.io import load_json
from tools.natural_memory_benchmark.typed_extractor_fresh_l1 import (
    freeze_fresh_l1_selection,
    prepare_fresh_l1_slice,
    validate_fresh_l1_slice,
    validate_fresh_l1_selection,
)


PREREG = Path(
    "artifacts/automatic-extraction-assessment/"
    "typed-extractor-v2-fresh-hidden-prereg-v1/preregistration.json"
)
BRIDGE = Path(
    "artifacts/automatic-extraction-assessment/bridge-v3/compatibility-ledger.json"
)
L1_DEV_ROOT = Path(
    "artifacts/automatic-extraction-assessment/typed-extractor-v2-dev-v3"
)
SOURCE = Path("data/gold-candidates/KE-test.json")
TURN_MANIFEST = Path("knowledge-extraction/turn-pass/validated/manifest.json")
DIALOGUE_MANIFEST = Path("knowledge-extraction/dialogue-pass/validated/manifest.json")
FINAL_KNOWLEDGE = Path("knowledge-extraction/final-knowledge.json")
RUN = Path("knowledge-extraction/run.json")
SOURCE_SEGMENTS = Path("knowledge-extraction/source-segments.json")
PROMPT = Path(
    "artifacts/automatic-extraction-assessment/typed-extractor-v2-l1-dev-policies/"
    "prompt-v6/proposer-prompt-l1.md"
)

EXPECTED_SELECTION = {
    "ordinary_explicit": [
        "K_wildchat-mgmt-cand-001-4d3900462107_002_011",
        "K_beam-cand-004-4d648a026dc4_002_016",
        "K_wildchat-mgmt-cand-002-e88f4bb1070d_002_010",
        "K_wildchat-learn-cand-002-1fa98728ac3e_002_002",
        "K_wildchat-mgmt-cand-003-f877bc2fc8f5_002_007",
        "K_tau-bench-cand-001-650fada2c0dc_001_001",
        "K_wildchat-mgmt-cand-001-4d3900462107_003_017",
        "K_tau-bench-cand-001-650fada2c0dc_001_006",
    ],
    "non_explicit_derivation": [
        "K_tau-bench-cand-001-650fada2c0dc_003_001",
        "K_wildchat-learn-cand-001-8def27ce661d_005_001",
        "K_beam-cand-004-4d648a026dc4_001_002",
        "K_beam-cand-004-4d648a026dc4_002_011",
    ],
    "condition_bearing": [
        "K_beam-cand-004-4d648a026dc4_003_013",
        "K_wildchat-learn-cand-001-8def27ce661d_003_007",
        "K_wildchat-learn-cand-001-8def27ce661d_002_003",
    ],
    "scope_bearing": [
        "K_tau-bench-cand-001-650fada2c0dc_004_003",
        "K_wildchat-mgmt-cand-001-4d3900462107_001_013",
        "K_wildchat-mgmt-cand-002-e88f4bb1070d_000_004",
    ],
    "non_active_lifecycle": [
        "K_tau-bench-cand-001-650fada2c0dc_002_003",
        "K_wildchat-mgmt-cand-001-4d3900462107_000_004",
    ],
    "time_bearing": [
        "K_wildchat-mgmt-cand-001-4d3900462107_004_010",
        "K_wildchat-mgmt-cand-001-4d3900462107_003_016",
    ],
    "negative_or_control": [
        "K_tau-bench-cand-001-650fada2c0dc_000_008",
        "K_tau-bench-cand-001-650fada2c0dc_003_009",
    ],
}


def _freeze(root: Path) -> dict:
    return freeze_fresh_l1_selection(
        preregistration_path=PREREG,
        bridge_ledger_path=BRIDGE,
        l1_dev_root=L1_DEV_ROOT,
        source_path=SOURCE,
        turn_manifest_path=TURN_MANIFEST,
        dialogue_manifest_path=DIALOGUE_MANIFEST,
        final_knowledge_path=FINAL_KNOWLEDGE,
        run_path=RUN,
        source_segments_path=SOURCE_SEGMENTS,
        output_root=root,
    )


def test_fresh_l1_selection_is_preregistered_deterministic_and_read_only(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"

    assert _freeze(first) == _freeze(second)
    source = load_json(first / "source-cases-l1.json")
    selected = {
        stratum: [
            case["knowledge_id"]
            for case in source["cases"]
            if case["stratum"] == stratum
        ]
        for stratum in EXPECTED_SELECTION
    }

    assert source["namespace"] == (
        "typed-extractor-l1-fresh-hidden-v1:2026-07-28"
    )
    assert source["case_count"] == 24
    assert selected == EXPECTED_SELECTION
    name = "source-cases-l1.json"
    assert first.joinpath(name).read_bytes() == second.joinpath(name).read_bytes()
    assert first.joinpath(name).stat().st_mode & 0o777 == 0o444


def test_fresh_l1_selection_excludes_dev_ids_and_evidence(
    tmp_path: Path,
) -> None:
    root = tmp_path / "slice"
    _freeze(root)
    source = load_json(root / "source-cases-l1.json")
    dev_source = load_json(L1_DEV_ROOT / "source-cases-l1.json")
    dev_authority = load_json(L1_DEV_ROOT / "authority-l1.json")

    selected_ids = {case["knowledge_id"] for case in source["cases"]}
    selected_evidence = {
        evidence_id
        for case in source["cases"]
        for evidence_id in case["evidence_ids"]
    }
    dev_ids = {case["knowledge_id"] for case in dev_source["cases"]}
    dev_evidence = {
        binding["evidence_id"]
        for case in dev_authority["cases"]
        for binding in case["required_evidence_bindings"]
    }

    assert selected_ids.isdisjoint(dev_ids)
    assert selected_evidence.isdisjoint(dev_evidence)


def test_validate_fresh_l1_selection_replays_exact_sources(tmp_path: Path) -> None:
    root = tmp_path / "slice"
    _freeze(root)

    result = validate_fresh_l1_selection(
        preregistration_path=PREREG,
        bridge_ledger_path=BRIDGE,
        l1_dev_root=L1_DEV_ROOT,
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
        "case_count": 24,
        "selection_phase": "frozen_before_gold",
    }


def _write_no_memory_adjudications(root: Path, path: Path) -> None:
    source = load_json(root / "source-cases-l1.json")
    payload = {
        "schema_version": "typed-extractor-l1-source-v1",
        "dataset_id": source["dataset_id"],
        "public_vocabulary": {},
        "cases": [
            {
                "private_case_id": case["private_case_id"],
                "knowledge_id": case["knowledge_id"],
                "expected_decision": "no_memory",
                "expected_typed_candidate": None,
                "emission_allowed": False,
                "allowed_modalities": [],
                "allowed_event_times": [],
                "event_time_may_be_null": True,
                "allowed_valid_times": [],
                "valid_time_may_be_null": True,
                "unresolved_required_fields": [],
                "time_case": "none",
            }
            for case in source["cases"]
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    path.chmod(0o444)


def _prepare_final(root: Path, adjudications: Path) -> dict:
    return prepare_fresh_l1_slice(
        preregistration_path=PREREG,
        prompt_path=PROMPT,
        bridge_ledger_path=BRIDGE,
        l1_dev_root=L1_DEV_ROOT,
        source_path=SOURCE,
        turn_manifest_path=TURN_MANIFEST,
        dialogue_manifest_path=DIALOGUE_MANIFEST,
        final_knowledge_path=FINAL_KNOWLEDGE,
        run_path=RUN,
        source_segments_path=SOURCE_SEGMENTS,
        selection_root=root,
        adjudication_path=adjudications,
    )


def test_prepare_fresh_l1_slice_keeps_public_gold_separate_and_replayable(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    _freeze(first)
    _freeze(second)
    first_adjudications = tmp_path / "first-adjudications.json"
    second_adjudications = tmp_path / "second-adjudications.json"
    _write_no_memory_adjudications(first, first_adjudications)
    _write_no_memory_adjudications(second, second_adjudications)

    assert _prepare_final(first, first_adjudications) == _prepare_final(
        second, second_adjudications
    )
    public = load_json(first / "public-l1.json")
    authority = load_json(first / "authority-l1.json")
    gold = load_json(first / "gold-l1.json")
    public_text = (first / "public-l1.json").read_text(encoding="utf-8")
    for private_field in (
        "knowledge_id",
        "candidate_id",
        "private_case_id",
        "selection_sha256",
        "stratum",
        "expected_decision",
        "expected_typed_candidate",
        "emission_allowed",
    ):
        assert private_field not in public_text
    case_ids = {case["case_id"] for case in public["cases"]}
    assert case_ids == {case["case_id"] for case in authority["cases"]}
    assert case_ids == {item["case_id"] for item in gold["items"]}
    assert all(item["expected_decision"] == "no_memory" for item in gold["items"])
    for name in (
        "source-cases-l1.json",
        "adjudications-l1.json",
        "public-l1.json",
        "authority-l1.json",
        "gold-l1.json",
        "manifest-l1.json",
    ):
        assert first.joinpath(name).read_bytes() == second.joinpath(name).read_bytes()
        assert first.joinpath(name).stat().st_mode & 0o777 == 0o444

    result = validate_fresh_l1_slice(
        preregistration_path=PREREG,
        prompt_path=PROMPT,
        bridge_ledger_path=BRIDGE,
        l1_dev_root=L1_DEV_ROOT,
        source_path=SOURCE,
        turn_manifest_path=TURN_MANIFEST,
        dialogue_manifest_path=DIALOGUE_MANIFEST,
        final_knowledge_path=FINAL_KNOWLEDGE,
        run_path=RUN,
        source_segments_path=SOURCE_SEGMENTS,
        root=first,
    )
    assert result == {
        "status": "valid",
        "case_count": 24,
        "raw_gold_authored_after_selection": True,
    }
