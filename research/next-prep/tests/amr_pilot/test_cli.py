from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from tools.amr_pilot.cli import build_parser, main
from tools.amr_pilot.models import AttemptSidecar


ROOT = Path(__file__).resolve().parents[2]
INPUTS = ROOT / "artifacts/amr-pilot/inputs"
GOLD = ROOT / "artifacts/amr-pilot/gold/semantic-checklists.draft.json"
PROMPTS = ROOT / "artifacts/amr-pilot/prompts"
KE_TEST = ROOT / "data/gold-candidates/KE-test.json"


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_parser_exposes_all_approved_commands() -> None:
    parser = build_parser()
    subparsers = next(action for action in parser._actions if action.dest == "command")

    assert set(subparsers.choices) == {
        "validate-inputs",
        "validate-gold",
        "prepare-payloads",
        "validate-attempt",
        "prepare-blind-review",
        "score",
        "report",
    }


def test_validate_inputs_and_gold_commands_use_current_artifacts(capsys) -> None:
    common = [
        "--sentences",
        str(INPUTS / "sentences.json"),
        "--source-records",
        str(INPUTS / "source-records.json"),
        "--ke-test",
        str(KE_TEST),
    ]

    assert main(["validate-inputs", *common]) == 0
    assert json.loads(capsys.readouterr().out)["sample_count"] == 12
    assert main(["validate-gold", *common, "--draft", str(GOLD)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "draft"


def test_prepare_payloads_writes_a_and_c_without_gold(tmp_path: Path) -> None:
    output = tmp_path / "payloads"
    result = main(
        [
            "prepare-payloads",
            "--sentences",
            str(INPUTS / "sentences.json"),
            "--source-records",
            str(INPUTS / "source-records.json"),
            "--ke-test",
            str(KE_TEST),
            "--prompts",
            str(PROMPTS),
            "--output-dir",
            str(output),
            "--routes",
            "A",
            "C",
        ]
    )

    assert result == 0
    payloads = json.loads((output / "payloads.json").read_text(encoding="utf-8"))["payloads"]
    assert len(payloads) == 24
    assert {payload["route"] for payload in payloads} == {"A", "C"}
    assert (output / "manifest.json").is_file()


def test_validate_attempt_reports_structural_result(tmp_path: Path, capsys) -> None:
    raw = "(c / cancel-01)"
    raw_path = tmp_path / "raw.txt"
    sidecar_path = tmp_path / "sidecar.json"
    inventory_path = tmp_path / "frames.json"
    raw_path.write_text(raw, encoding="utf-8")
    inventory_path.write_text(json.dumps(["cancel-01"]), encoding="utf-8")
    sidecar = AttemptSidecar.model_validate(
        {
            "sample_id": "AMR-S001",
            "route": "A",
            "run_id": "run-20260724T120000Z",
            "attempt": 1,
            "previous_attempt_sha256": None,
            "model_id": "gpt-5.6-terra",
            "prompt_sha256": "1" * 64,
            "raw_output_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            "started_at": datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc),
            "finished_at": datetime(2026, 7, 24, 12, 0, 1, tzinfo=timezone.utc),
            "latency_ms": 1000,
            "usage": {"status": "unavailable", "reason": "not exposed"},
            "parse_status": "valid",
            "parse_errors": [],
            "representation_gaps": [],
        }
    )
    write_json(sidecar_path, sidecar.model_dump(mode="json"))

    assert main(
        [
            "validate-attempt",
            "--raw",
            str(raw_path),
            "--sidecar",
            str(sidecar_path),
            "--propbank-inventory",
            str(inventory_path),
        ]
    ) == 0
    assert json.loads(capsys.readouterr().out)["is_valid"] is True


def test_prepare_blind_review_writes_separate_mapping(tmp_path: Path) -> None:
    output = "(c / cancel-01)"
    candidates = tmp_path / "candidates.json"
    write_json(
        candidates,
        {
            "candidates": [
                {
                    "sample_id": "AMR-S001",
                    "route": "A",
                    "output": output,
                    "output_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
                }
            ]
        },
    )

    assert main(
        [
            "prepare-blind-review",
            "--run-id",
            "run-20260724T120000Z",
            "--candidates",
            str(candidates),
            "--review-output",
            str(tmp_path / "review.json"),
            "--mapping-output",
            str(tmp_path / "mapping.json"),
        ]
    ) == 0
    review = json.loads((tmp_path / "review.json").read_text(encoding="utf-8"))
    mapping = json.loads((tmp_path / "mapping.json").read_text(encoding="utf-8"))
    assert "route" not in review["items"][0]
    assert mapping["items"][0]["route"] == "A"


def test_score_command_writes_deterministic_semantic_metrics(tmp_path: Path) -> None:
    checklist = tmp_path / "checklist.json"
    review = tmp_path / "review.json"
    output = tmp_path / "score.json"
    write_json(
        checklist,
        {
            "sample_id": "AMR-S001",
            "source_text_sha256": "1" * 64,
            "items": [
                {
                    "item_id": "AMR-S001-G001",
                    "statement": "The cancellation is negated.",
                    "importance": "critical",
                    "weight": 2,
                    "evidence_quotes": ["did not cancel"],
                    "category": "polarity",
                }
            ],
            "forbidden_inferences": ["The cancellation occurred."],
        },
    )
    write_json(
        review,
        {
            "judgments": [{"item_id": "AMR-S001-G001", "outcome": "supported"}],
            "hallucinations": [],
        },
    )

    assert main(
        ["score", "--checklist", str(checklist), "--review", str(review), "--output", str(output)]
    ) == 0
    score = json.loads(output.read_text(encoding="utf-8"))
    assert score["recall"] == 1.0
    assert score["precision"] == 1.0


def test_report_command_writes_json_and_markdown(tmp_path: Path) -> None:
    input_path = tmp_path / "report-input.json"
    json_output = tmp_path / "report.json"
    markdown_output = tmp_path / "report.md"
    route_metrics = {
        "C": {"recall": 0.82, "precision": 0.96, "critical_error_count": 0, "net_fixes_by_category": {}},
        "A": {"recall": 0.92, "precision": 0.97, "critical_error_count": 0, "net_fixes_by_category": {"negation_modality_intent": 2}},
        "B": {"recall": 0.98, "precision": 0.98, "critical_error_count": 0, "net_fixes_by_category": {"negation_modality_intent": 3}},
    }
    efficiency = {
        route: {
            "route": route,
            "expected_samples": 12,
            "first_pass_parse_rate": 1.0,
            "final_parse_count": 12,
            "latency_ms": latency,
            "usage_status": "measured",
            "total_tokens": tokens,
            "cost_usd": 0.1,
        }
        for route, latency, tokens in (("C", 1000, 1000), ("A", 1200, 1200), ("B", 2000, 2000))
    }
    write_json(
        input_path,
        {
            "route_metrics": route_metrics,
            "efficiency": efficiency,
            "hard_categories": ["negation_modality_intent"],
        },
    )

    assert main(
        [
            "report",
            "--input",
            str(input_path),
            "--json-output",
            str(json_output),
            "--markdown-output",
            str(markdown_output),
        ]
    ) == 0
    assert json.loads(json_output.read_text(encoding="utf-8"))["decision"] == "select_B"
    assert "Decision: select_B" in markdown_output.read_text(encoding="utf-8")
