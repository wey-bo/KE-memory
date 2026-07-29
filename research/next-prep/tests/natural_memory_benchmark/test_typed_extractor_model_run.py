from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools.natural_memory_benchmark.cli import main as cli_main
from tools.natural_memory_benchmark.io import load_json, sha256_file
from tools.natural_memory_benchmark.typed_extractor_l1 import prepare_l1_dev_slice
from tools.natural_memory_benchmark.typed_extractor_model_run import (
    freeze_l1_model_proposals,
    write_l1_model_dispatch,
)


SOURCE_CONFIG = Path(
    "artifacts/automatic-extraction-assessment/typed-extractor-v2-dev/"
    "source-cases-l1.json"
)
PROMPT = Path(
    "artifacts/automatic-extraction-assessment/typed-extractor-v2-dev/"
    "proposer-prompt-l1.md"
)
PROMPT_V2 = Path(
    "artifacts/automatic-extraction-assessment/typed-extractor-v2-dev/"
    "proposer-prompt-l1-v2.md"
)
PROMPT_V3 = Path(
    "artifacts/automatic-extraction-assessment/typed-extractor-v2-dev-v2/"
    "proposer-prompt-l1.md"
)
PROMPT_V4 = Path(
    "artifacts/automatic-extraction-assessment/typed-extractor-v2-dev-v3/"
    "proposer-prompt-l1.md"
)
PROMPT_V5 = Path(
    "artifacts/automatic-extraction-assessment/typed-extractor-v2-l1-dev-policies/"
    "prompt-v5/proposer-prompt-l1.md"
)
PROMPT_V6 = Path(
    "artifacts/automatic-extraction-assessment/typed-extractor-v2-l1-dev-policies/"
    "prompt-v6/proposer-prompt-l1.md"
)
BRIDGE_LEDGER = Path(
    "artifacts/automatic-extraction-assessment/bridge-v3/compatibility-ledger.json"
)
SOURCE = Path("data/gold-candidates/KE-test.json")
TURN_MANIFEST = Path("knowledge-extraction/turn-pass/validated/manifest.json")
DIALOGUE_MANIFEST = Path("knowledge-extraction/dialogue-pass/validated/manifest.json")
FINAL_KNOWLEDGE = Path("knowledge-extraction/final-knowledge.json")
RUN = Path("knowledge-extraction/run.json")
SOURCE_SEGMENTS = Path("knowledge-extraction/source-segments.json")
ISOLATION_CONTEXT = "fresh-agent-no-history-declarative"


def test_v2_prompt_exposes_the_exact_strict_proposal_contract() -> None:
    prompt = PROMPT_V2.read_text(encoding="utf-8")
    required_tokens = {
        '"confidence"',
        '"local_entities"',
        '"local_entity_id"',
        '"role_name"',
        '"time"',
        '"condition_bindings"',
        '"scope_bindings"',
        '"derivation"',
        '"evidence_bindings"',
        '"lifecycle"',
        '"operation_provenance"',
    }

    assert required_tokens.issubset(set(prompt.split()))


def test_v3_prompt_binds_canonical_and_abstention_policy() -> None:
    prompt = PROMPT_V3.read_text(encoding="utf-8")

    for required_text in (
        "canonical_operators",
        "predicate_senses",
        "role_bindings",
        "unsupported_source_modality",
        "unresolved_deictic_time",
        "ISO-8601",
    ):
        assert required_text in prompt


def test_v4_prompt_binds_operator_qualifier_and_surface_policy() -> None:
    prompt = PROMPT_V4.read_text(encoding="utf-8")

    for required_text in (
        "operator_kind_bindings",
        "operator_role_bindings",
        "condition_operators",
        "scope_operators",
        "operator_time_bindings",
        "copy local entity surfaces exactly",
    ):
        assert required_text in prompt


def test_v5_prompt_closes_observable_deictic_modality_and_qualifier_errors() -> None:
    prompt = PROMPT_V5.read_text(encoding="utf-8")

    for required_text in (
        "must not abstain merely because that time value is null",
        "likely_caused_by",
        "one scope binding for every public `qualifiers.scope` value",
        "one condition binding for every public `qualifiers.conditions` value",
    ):
        assert required_text in prompt


def test_v6_prompt_makes_remaining_dev_rules_pre_submit_invariants() -> None:
    prompt = PROMPT_V6.read_text(encoding="utf-8")

    for required_text in (
        "Never use `unsupported_source_modality` when the selected canonical operator is `likely_caused_by`",
        "participant prefix before `确认执行`",
        "Pre-submit invariant audit",
    ):
        assert required_text in prompt


def _prepare(root: Path) -> Path:
    prepare_l1_dev_slice(
        source_config_path=SOURCE_CONFIG,
        prompt_path=PROMPT,
        bridge_ledger_path=BRIDGE_LEDGER,
        source_path=SOURCE,
        turn_manifest_path=TURN_MANIFEST,
        dialogue_manifest_path=DIALOGUE_MANIFEST,
        final_knowledge_path=FINAL_KNOWLEDGE,
        run_path=RUN,
        source_segments_path=SOURCE_SEGMENTS,
        output_root=root,
    )
    return root / "public-l1.json"


def _staged_payload(root: Path, public_path: Path) -> Path:
    public = load_json(public_path)
    payload = {
        "schema_version": "typed-extractor-l1-proposals-v1",
        "dataset_id": public["dataset_id"],
        "run_id": "run-test-typed-l1",
        "proposer_id": "test-proposer",
        "proposer_version": "1",
        "case_count": public["case_count"],
        "proposals": [
            {
                "case_id": case["case_id"],
                "candidate_ref": case["candidate_ref"],
                "decision": "abstain",
                "confidence": 0.5,
                "typed_candidate": None,
                "reason_code": "insufficient_public_evidence",
            }
            for case in public["cases"]
        ],
    }
    path = root / "staged-proposals.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


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


def test_dispatch_and_freeze_bind_exact_public_only_inputs(tmp_path: Path) -> None:
    public_path = _prepare(tmp_path / "slice")
    dispatch_path = tmp_path / "run" / "dispatch.json"
    dispatch = write_l1_model_dispatch(
        public_path,
        PROMPT,
        dispatch_path,
        run_id="run-test-typed-l1",
        proposer_id="test-proposer",
        proposer_version="1",
        requested_model="test-model-alias",
        isolation_context=ISOLATION_CONTEXT,
    )

    assert dispatch["allowed_input_sha256"] == {
        "proposer-prompt-l1.md": sha256_file(PROMPT),
        "public-l1.json": sha256_file(public_path),
    }
    assert dispatch["history_context_inherited"] is False
    assert dispatch["authority_or_gold_allowed"] is False
    assert dispatch_path.stat().st_mode & 0o777 == 0o444

    staged = _staged_payload(tmp_path, public_path)
    proposals_path = tmp_path / "run" / "proposals.json"
    provenance_path = tmp_path / "run" / "provenance.json"
    raw_response_path = tmp_path / "run" / "raw-response.json"
    _write_raw_response(staged, raw_response_path)
    first = freeze_l1_model_proposals(
        public_path,
        staged,
        proposals_path,
        provenance_path,
        prompt_path=PROMPT,
        dispatch_path=dispatch_path,
        raw_response_path=raw_response_path,
        isolation_context=ISOLATION_CONTEXT,
    )
    second = freeze_l1_model_proposals(
        public_path,
        staged,
        proposals_path,
        provenance_path,
        prompt_path=PROMPT,
        dispatch_path=dispatch_path,
        raw_response_path=raw_response_path,
        isolation_context=ISOLATION_CONTEXT,
    )

    assert first == second
    assert first["authority_or_gold_read_before_freeze"] is False
    assert first["dispatch_sha256"] == sha256_file(dispatch_path)
    assert first["raw_response_sha256"] == sha256_file(raw_response_path)
    assert first["proposals_sha256"] == sha256_file(proposals_path)
    assert first["requested_model"] == "test-model-alias"
    assert first["response_model"] == "resolved-test-model"
    assert first["proposal_source_verified"] is True
    assert first["freeze_sequence"] == [
        "dispatch",
        "raw_response",
        "proposals",
        "provenance",
    ]
    assert proposals_path.stat().st_mode & 0o777 == 0o444
    assert provenance_path.stat().st_mode & 0o777 == 0o444


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing_case", "proposal case coverage mismatch"),
        ("wrong_candidate", "proposal candidate ref mismatch"),
        ("unknown_evidence", "unknown proposal evidence"),
        ("unknown_lifecycle", "unknown proposal lifecycle ref"),
        ("unknown_operation", "unknown proposal operation ref"),
    ],
)
def test_freeze_rejects_invalid_public_contract(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    public_path = _prepare(tmp_path / "slice")
    dispatch_path = tmp_path / "run" / "dispatch.json"
    write_l1_model_dispatch(
        public_path,
        PROMPT,
        dispatch_path,
        run_id="run-test-typed-l1",
        proposer_id="test-proposer",
        proposer_version="1",
        requested_model="test-model-alias",
        isolation_context=ISOLATION_CONTEXT,
    )
    staged = _staged_payload(tmp_path, public_path)
    payload = load_json(staged)
    if mutation == "missing_case":
        payload["proposals"][-1]["case_id"] = "case-0000000000000000"
    elif mutation == "wrong_candidate":
        payload["proposals"][0]["candidate_ref"] = "candidate-0000000000000000"
    else:
        gold = load_json(tmp_path / "slice" / "gold-l1.json")
        emit_index = next(
            index
            for index, item in enumerate(gold["items"])
            if item["expected_decision"] == "emit_l1"
        )
        payload["proposals"][emit_index]["decision"] = "emit_l1"
        payload["proposals"][emit_index]["typed_candidate"] = copy.deepcopy(
            gold["items"][emit_index]["expected_typed_candidate"]
        )
        typed = payload["proposals"][emit_index]["typed_candidate"]
        if mutation == "unknown_evidence":
            typed["evidence_bindings"][0]["evidence_id"] = "evidence-unknown"
            typed["derivation"]["evidence_ids"] = ["evidence-unknown"]
        elif mutation == "unknown_lifecycle":
            typed["lifecycle"]["replacement_candidate_ref"] = (
                "candidate-0000000000000000"
            )
        else:
            typed["operation_provenance"]["confirmed_by_operation_refs"] = [
                "operation-0000000000000000"
            ]
    staged.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    raw_response_path = tmp_path / "run" / "raw-response.json"
    _write_raw_response(staged, raw_response_path)

    with pytest.raises(ValueError, match=message):
        freeze_l1_model_proposals(
            public_path,
            staged,
            tmp_path / "run" / "proposals.json",
            tmp_path / "run" / "provenance.json",
            prompt_path=PROMPT,
            dispatch_path=dispatch_path,
            raw_response_path=raw_response_path,
            isolation_context=ISOLATION_CONTEXT,
        )


def test_freeze_rejects_staged_proposals_not_derived_from_raw_response(
    tmp_path: Path,
) -> None:
    public_path = _prepare(tmp_path / "slice")
    dispatch_path = tmp_path / "run" / "dispatch.json"
    write_l1_model_dispatch(
        public_path,
        PROMPT,
        dispatch_path,
        run_id="run-test-typed-l1",
        proposer_id="test-proposer",
        proposer_version="1",
        requested_model="test-model-alias",
        isolation_context=ISOLATION_CONTEXT,
    )
    staged = _staged_payload(tmp_path, public_path)
    raw_response_path = tmp_path / "run" / "raw-response.json"
    _write_raw_response(staged, raw_response_path)
    payload = load_json(staged)
    payload["proposals"][0]["reason_code"] = "mutated_after_response"
    staged.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="staged proposals do not match raw response"):
        freeze_l1_model_proposals(
            public_path,
            staged,
            tmp_path / "run" / "proposals.json",
            tmp_path / "run" / "provenance.json",
            prompt_path=PROMPT,
            dispatch_path=dispatch_path,
            raw_response_path=raw_response_path,
            isolation_context=ISOLATION_CONTEXT,
        )


def test_cli_prepares_validates_dispatches_freezes_and_scores(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "slice"
    common = [
        "--source-config",
        str(SOURCE_CONFIG),
        "--prompt",
        str(PROMPT),
        "--bridge-ledger",
        str(BRIDGE_LEDGER),
        "--source",
        str(SOURCE),
        "--turn-manifest",
        str(TURN_MANIFEST),
        "--dialogue-manifest",
        str(DIALOGUE_MANIFEST),
        "--final-knowledge",
        str(FINAL_KNOWLEDGE),
        "--run",
        str(RUN),
        "--source-segments",
        str(SOURCE_SEGMENTS),
    ]
    assert cli_main(["prepare-typed-extractor-l1-dev", *common, "--output-root", str(root)]) == 0
    assert cli_main(["validate-typed-extractor-l1-dev", *common, "--root", str(root)]) == 0

    run_root = root / "cli-run"
    assert (
        cli_main(
            [
                "prepare-typed-extractor-l1-dispatch",
                "--public",
                str(root / "public-l1.json"),
                "--prompt",
                str(PROMPT),
                "--output",
                str(run_root / "dispatch.json"),
                "--run-id",
                "run-cli-typed-l1",
                "--proposer-id",
                "test-proposer",
                "--proposer-version",
                "1",
                "--requested-model",
                "test-model-alias",
                "--isolation-context",
                ISOLATION_CONTEXT,
            ]
        )
        == 0
    )
    payload = _staged_payload(tmp_path, root / "public-l1.json")
    staged = load_json(payload)
    staged["run_id"] = "run-cli-typed-l1"
    payload.write_text(json.dumps(staged, ensure_ascii=False), encoding="utf-8")
    raw_response_path = run_root / "raw-response.json"
    _write_raw_response(payload, raw_response_path)
    assert (
        cli_main(
            [
                "freeze-typed-extractor-l1-proposals",
                "--public",
                str(root / "public-l1.json"),
                "--staged-proposals",
                str(payload),
                "--output",
                str(run_root / "proposals.json"),
                "--provenance",
                str(run_root / "provenance.json"),
                "--prompt",
                str(PROMPT),
                "--dispatch",
                str(run_root / "dispatch.json"),
                "--raw-response",
                str(raw_response_path),
                "--isolation-context",
                ISOLATION_CONTEXT,
            ]
        )
        == 0
    )
    assert (
        cli_main(
            [
                "score-typed-extractor-l1-proposals",
                "--root",
                str(root),
                "--proposals",
                str(run_root / "proposals.json"),
                "--provenance",
                str(run_root / "provenance.json"),
                "--guard-root",
                "artifacts/natural-benchmark-slices",
                "--guard-slice-id",
                "slice-v1",
                "--guard-results",
                "artifacts/natural-benchmark-slices/slice-v1/symbolic-fallback-answerability-v2-fastembed-results.json",
                "--output",
                str(run_root / "score.json"),
                "--report",
                str(run_root / "report.md"),
                "--error-analysis",
                str(run_root / "error-analysis.json"),
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert '"raw_proposer_quality_ready"' in output
    assert '"deterministic_gate_safety_ready"' in output
