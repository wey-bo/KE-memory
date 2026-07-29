from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.natural_memory_benchmark.io import load_json, sha256_file
from tools.natural_memory_benchmark.typed_extractor_l2 import (
    L2ProposalPayload,
    prepare_l2_dev_slice,
)
from tools.natural_memory_benchmark.typed_extractor_l2_dev_repair import (
    prepare_l2_dev_repair_slice,
)
from tools.natural_memory_benchmark.typed_extractor_l2_model_run import (
    freeze_l2_model_proposals,
    write_l2_model_dispatch,
)
from tools.natural_memory_benchmark.cli import build_parser


FORMAL_ROOT = Path(
    "artifacts/automatic-extraction-assessment/typed-extractor-v2-l2-dev"
)
SOURCE_CONFIG = FORMAL_ROOT / "source-cases-l2.json"
PROMPT = FORMAL_ROOT / "proposer-prompt-l2.md"
BRIDGE_LEDGER = Path(
    "artifacts/automatic-extraction-assessment/bridge-v3/compatibility-ledger.json"
)
SOURCE = Path("data/gold-candidates/KE-test.json")
TURN_MANIFEST = Path("knowledge-extraction/turn-pass/validated/manifest.json")
DIALOGUE_MANIFEST = Path("knowledge-extraction/dialogue-pass/validated/manifest.json")
FINAL_KNOWLEDGE = Path("knowledge-extraction/final-knowledge.json")
RUN = Path("knowledge-extraction/run.json")
SOURCE_SEGMENTS = Path("knowledge-extraction/source-segments.json")
L1_ROOT = Path(
    "artifacts/automatic-extraction-assessment/typed-extractor-v2-dev-v3"
)
ISOLATION = "fresh-agent-no-history-declarative"
RUN_ID = "run-test-typed-l2"
PROPOSER_ID = "test-proposer"
PROPOSER_VERSION = "test-proposer-v1"
DIAGNOSTIC_V3_SOURCE = Path(
    "artifacts/automatic-extraction-assessment/"
    "typed-extractor-v2-l2-dev-repair-v3/diagnostic-source-l2.json"
)
DIAGNOSTIC_V3_PROMPT = DIAGNOSTIC_V3_SOURCE.parent / "proposer-prompt-l2.md"
DIAGNOSTIC_PRIOR_ROOTS = (
    Path(
        "artifacts/automatic-extraction-assessment/"
        "typed-extractor-v2-l2-dev-v9"
    ),
    Path(
        "artifacts/automatic-extraction-assessment/"
        "typed-extractor-v2-fresh-hidden-v1/l2"
    ),
    Path(
        "artifacts/automatic-extraction-assessment/"
        "typed-extractor-v2-l1-dev-repair-v1"
    ),
)


def _prepare(root: Path) -> None:
    prepare_l2_dev_slice(
        source_config_path=SOURCE_CONFIG,
        prompt_path=PROMPT,
        bridge_ledger_path=BRIDGE_LEDGER,
        source_path=SOURCE,
        turn_manifest_path=TURN_MANIFEST,
        dialogue_manifest_path=DIALOGUE_MANIFEST,
        final_knowledge_path=FINAL_KNOWLEDGE,
        run_path=RUN,
        source_segments_path=SOURCE_SEGMENTS,
        l1_qualification_root=L1_ROOT,
        output_root=root,
    )


def _perfect_staged(root: Path, path: Path) -> None:
    gold = load_json(root / "gold-l2.json")
    payload = L2ProposalPayload(
        dataset_id=gold["dataset_id"],
        run_id=RUN_ID,
        proposer_id=PROPOSER_ID,
        proposer_version=PROPOSER_VERSION,
        case_count=gold["case_count"],
        proposals=[
            {
                "case_id": item["case_id"],
                "candidate_ref": item["candidate_ref"],
                "decision": item["expected_decision"],
                "confidence": 1.0,
                "typed_candidate": item["expected_typed_candidate"],
                "reason_code": "test_fixture",
            }
            for item in gold["items"]
        ],
    )
    path.write_text(
        json.dumps(payload.model_dump(mode="json"), ensure_ascii=False),
        encoding="utf-8",
    )


def _write_raw_response(staged: Path, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "model": "resolved-test-model",
                "choices": [
                    {
                        "message": {
                            "content": staged.read_text(encoding="utf-8")
                        }
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    path.chmod(0o444)


def test_l2_dispatch_and_freeze_bind_public_only_inputs(tmp_path: Path) -> None:
    root = tmp_path / "slice"
    _prepare(root)
    run_root = tmp_path / "run"
    dispatch = run_root / "dispatch.json"
    write_l2_model_dispatch(
        root / "public-l2.json",
        PROMPT,
        dispatch,
        run_id=RUN_ID,
        proposer_id=PROPOSER_ID,
        proposer_version=PROPOSER_VERSION,
        requested_model="test-model-alias",
        isolation_context=ISOLATION,
    )
    staged = tmp_path / "staged.json"
    _perfect_staged(root, staged)
    proposals = run_root / "proposals.json"
    provenance = run_root / "provenance.json"
    raw_response = run_root / "raw-response.json"
    _write_raw_response(staged, raw_response)
    result = freeze_l2_model_proposals(
        root / "public-l2.json",
        staged,
        proposals,
        provenance,
        prompt_path=PROMPT,
        dispatch_path=dispatch,
        raw_response_path=raw_response,
        isolation_context=ISOLATION,
    )
    assert result["history_context_inherited"] is False
    assert result["authority_or_gold_read_before_freeze"] is False
    assert set(result["allowed_files"]) == {
        "proposer-prompt-l2.md",
        "public-l2.json",
    }
    assert result["proposals_sha256"] == sha256_file(proposals)
    assert result["raw_response_sha256"] == sha256_file(raw_response)
    assert result["requested_model"] == "test-model-alias"
    assert result["response_model"] == "resolved-test-model"
    assert result["proposal_source_verified"] is True
    assert dispatch.stat().st_mode & 0o222 == 0
    assert proposals.stat().st_mode & 0o222 == 0
    assert provenance.stat().st_mode & 0o222 == 0


def test_l2_freeze_rejects_unknown_support_reference(tmp_path: Path) -> None:
    root = tmp_path / "slice"
    _prepare(root)
    run_root = tmp_path / "run"
    dispatch = run_root / "dispatch.json"
    write_l2_model_dispatch(
        root / "public-l2.json",
        PROMPT,
        dispatch,
        run_id=RUN_ID,
        proposer_id=PROPOSER_ID,
        proposer_version=PROPOSER_VERSION,
        requested_model="test-model-alias",
        isolation_context=ISOLATION,
    )
    staged = tmp_path / "staged.json"
    _perfect_staged(root, staged)
    payload = load_json(staged)
    emitted = next(item for item in payload["proposals"] if item["decision"] == "emit_l2")
    emitted["typed_candidate"]["supporting_l1_refs"][0] = "support-aaaaaaaaaaaaaaaa"
    staged.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    raw_response = run_root / "raw-response.json"
    _write_raw_response(staged, raw_response)
    with pytest.raises(ValueError, match="unknown support|support refs"):
        freeze_l2_model_proposals(
            root / "public-l2.json",
            staged,
            run_root / "proposals.json",
            run_root / "provenance.json",
            prompt_path=PROMPT,
            dispatch_path=dispatch,
            raw_response_path=raw_response,
            isolation_context=ISOLATION,
        )


def test_l2_freeze_rejects_primary_predicate_surface_not_copied_from_public(
    tmp_path: Path,
) -> None:
    root = tmp_path / "slice"
    _prepare(root)
    run_root = tmp_path / "run"
    dispatch = run_root / "dispatch.json"
    write_l2_model_dispatch(
        root / "public-l2.json",
        PROMPT,
        dispatch,
        run_id=RUN_ID,
        proposer_id=PROPOSER_ID,
        proposer_version=PROPOSER_VERSION,
        requested_model="test-model-alias",
        isolation_context=ISOLATION,
    )
    staged = tmp_path / "staged.json"
    _perfect_staged(root, staged)
    payload = load_json(staged)
    emitted = next(item for item in payload["proposals"] if item["decision"] == "emit_l2")
    emitted["typed_candidate"]["structured_claims"][0]["predicate"]["surface"] = (
        "support predicate paraphrase"
    )
    staged.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    raw_response = run_root / "raw-response.json"
    _write_raw_response(staged, raw_response)

    with pytest.raises(ValueError, match="public predicate surface"):
        freeze_l2_model_proposals(
            root / "public-l2.json",
            staged,
            run_root / "proposals.json",
            run_root / "provenance.json",
            prompt_path=PROMPT,
            dispatch_path=dispatch,
            raw_response_path=raw_response,
            isolation_context=ISOLATION,
        )


def test_l2_freeze_rejects_catalog_external_operator_sense_pair(
    tmp_path: Path,
) -> None:
    root = tmp_path / "slice"
    prepare_l2_dev_repair_slice(
        DIAGNOSTIC_V3_SOURCE,
        root,
        DIAGNOSTIC_PRIOR_ROOTS,
    )
    run_root = tmp_path / "run"
    dispatch = run_root / "dispatch.json"
    write_l2_model_dispatch(
        root / "public-l2.json",
        DIAGNOSTIC_V3_PROMPT,
        dispatch,
        run_id=RUN_ID,
        proposer_id=PROPOSER_ID,
        proposer_version=PROPOSER_VERSION,
        requested_model="test-model-alias",
        isolation_context=ISOLATION,
    )
    staged = tmp_path / "staged.json"
    _perfect_staged(root, staged)
    payload = load_json(staged)
    emitted = next(item for item in payload["proposals"] if item["decision"] == "emit_l2")
    predicate = emitted["typed_candidate"]["structured_claims"][0]["predicate"]
    bindings = set(
        load_json(root / "public-l2.json")["allowed_vocabulary"][
            "operator_sense_bindings"
        ]
    )
    replacement = next(
        sense
        for sense in load_json(root / "public-l2.json")["allowed_vocabulary"][
            "predicate_senses"
        ]
        if f"{predicate['canonical_operator']}|{sense}" not in bindings
    )
    predicate["sense"] = replacement
    staged.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    raw_response = run_root / "raw-response.json"
    _write_raw_response(staged, raw_response)

    with pytest.raises(ValueError, match="operator/sense pair"):
        freeze_l2_model_proposals(
            root / "public-l2.json",
            staged,
            run_root / "proposals.json",
            run_root / "provenance.json",
            prompt_path=DIAGNOSTIC_V3_PROMPT,
            dispatch_path=dispatch,
            raw_response_path=raw_response,
            isolation_context=ISOLATION,
        )


@pytest.mark.parametrize(
    ("command", "arguments"),
    [
        (
            "prepare-typed-extractor-l2-dev",
            [
                "--source-config", "source.json", "--prompt", "prompt.md",
                "--bridge-ledger", "bridge.json", "--source", "source-data.json",
                "--turn-manifest", "turn.json", "--dialogue-manifest", "dialogue.json",
                "--final-knowledge", "final.json", "--run", "run.json",
                "--source-segments", "segments.json", "--l1-qualification-root", "l1",
                "--output-root", "output",
            ],
        ),
        (
            "prepare-typed-extractor-l2-dispatch",
            [
                "--public", "public.json", "--prompt", "prompt.md", "--output", "dispatch.json",
                "--run-id", "run", "--proposer-id", "proposer", "--proposer-version", "v1",
                "--requested-model", "model-alias",
                "--isolation-context", ISOLATION,
            ],
        ),
        (
            "freeze-typed-extractor-l2-proposals",
            [
                "--public", "public.json", "--staged-proposals", "staged.json",
                "--output", "proposals.json", "--provenance", "provenance.json",
                "--prompt", "prompt.md", "--dispatch", "dispatch.json",
                "--raw-response", "raw-response.json",
                "--isolation-context", ISOLATION,
            ],
        ),
        (
            "score-typed-extractor-l2-proposals",
            [
                "--root", "root", "--proposals", "proposals.json",
                "--provenance", "provenance.json", "--guard-root", "guard",
                "--guard-results", "results.json", "--output", "score.json",
                "--report", "report.md", "--error-analysis", "errors.json",
            ],
        ),
    ],
)
def test_cli_accepts_l2_commands(command: str, arguments: list[str]) -> None:
    args = build_parser().parse_args([command, *arguments])
    assert args.command == command
