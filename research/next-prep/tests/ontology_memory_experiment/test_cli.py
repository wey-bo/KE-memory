from __future__ import annotations

import json
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

import tools.ontology_memory_experiment.cli as cli_module
from tools.ontology_memory_experiment.cli import _subset_documents, build_parser, main
from tools.ontology_memory_experiment.io import (
    load_distractor_document,
    load_gold_document,
    load_oracle_query_plan_document,
    load_oracle_representation_document,
    load_source_document,
)


ROOT = Path(__file__).resolve().parents[2]
GOLD_DIR = ROOT / "artifacts" / "ontology-memory-experiment" / "gold-v2"
EXPECTED_DEFAULT_GOLD_DIR = Path("artifacts") / "ontology-memory-experiment" / "gold-v2"
AUDIT_DIR = ROOT / "artifacts" / "ontology-memory-experiment" / "architecture-audit"


def test_cli_exposes_the_reproducible_experiment_workflow() -> None:
    parser = build_parser()
    subparsers = next(action for action in parser._actions if action.dest == "command")

    assert set(subparsers.choices) == {
        "generate",
        "validate-audit",
        "validate-gold",
        "smoke",
        "run",
        "score",
        "report",
        "verify-run",
    }


def test_dataset_defaults_point_to_explicit_gold_v2_artifacts() -> None:
    args = build_parser().parse_args(
        ["run", "--output-dir", "run", "--run-id", "run-20260725T120000Z"]
    )
    assert Path(args.source) == EXPECTED_DEFAULT_GOLD_DIR / "source-scenarios.json"
    assert Path(args.gold) == EXPECTED_DEFAULT_GOLD_DIR / "gold.json"
    assert Path(args.distractors) == EXPECTED_DEFAULT_GOLD_DIR / "distractors.json"
    assert Path(args.oracle_representations) == EXPECTED_DEFAULT_GOLD_DIR / "oracle-representations.json"
    assert Path(args.oracle_query_plans) == EXPECTED_DEFAULT_GOLD_DIR / "oracle-query-plans.json"
    validate_args = build_parser().parse_args(["validate-gold"])
    assert validate_args.manifest is None


def test_subset_documents_rebinds_oracle_source_hash_to_selected_source() -> None:
    documents = (
        load_source_document(GOLD_DIR / "source-scenarios.json"),
        load_gold_document(GOLD_DIR / "gold.json"),
        load_distractor_document(GOLD_DIR / "distractors.json"),
        load_oracle_representation_document(GOLD_DIR / "oracle-representations.json"),
        load_oracle_query_plan_document(GOLD_DIR / "oracle-query-plans.json"),
    )
    source, _, _, representations, query_plans = _subset_documents(documents, 2, split="hidden")
    canonical = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    expected_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert representations["source_sha256"] == expected_hash
    assert query_plans["source_sha256"] == expected_hash


def test_score_rejects_supplied_gold_that_does_not_match_run_manifest(
    monkeypatch, tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run"
    (run_dir / "inputs").mkdir(parents=True)
    (run_dir / "results.jsonl").write_text("", encoding="utf-8")
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": "run-score", "gold_sha256": "0" * 64}), encoding="utf-8"
    )
    monkeypatch.setattr(cli_module, "verify_run", lambda path: {})
    with pytest.raises(ValueError, match="gold.*manifest"):
        main(
            [
                "score", "--run-dir", str(run_dir), "--gold", str(GOLD_DIR / "gold.json"),
                "--output", str(tmp_path / "metrics.json"),
            ]
        )


def test_score_forwards_distractor_ids_and_bootstrap_seed(
    monkeypatch, tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run"
    (run_dir / "inputs").mkdir(parents=True)
    (run_dir / "results.jsonl").write_text("", encoding="utf-8")
    gold_bytes = (GOLD_DIR / "gold.json").read_bytes()
    distractors = {
        "schema_version": "ontology-memory-distractors-v1",
        "records": [
            {
                "record_id": "OME-D-S001-50-001",
                "scenario_id": "OME-S001",
                "distractor_scale": 50,
                "text": "A natural distractor.",
            }
        ],
    }
    (run_dir / "inputs" / "distractors.json").write_text(json.dumps(distractors), encoding="utf-8")
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": "run-score", "gold_sha256": hashlib.sha256(gold_bytes).hexdigest()}),
        encoding="utf-8",
    )
    captured: dict[str, object] = {}
    monkeypatch.setattr(cli_module, "verify_run", lambda path: {})
    monkeypatch.setattr(
        cli_module,
        "aggregate_metrics",
        lambda rows, gold, **kwargs: captured.update(kwargs) or {"arms": {}},
    )
    assert main(
        [
            "score", "--run-dir", str(run_dir), "--gold", str(GOLD_DIR / "gold.json"),
            "--output", str(tmp_path / "metrics.json"), "--bootstrap-seed", "4321",
        ]
    ) == 0
    assert captured["bootstrap_seed"] == 4321
    assert captured["critical_distractor_ids"] == {"OME-S001": ["OME-D-S001-50-001"]}


def test_main_run_requires_a_real_dense_backend() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "run",
            "--source",
            "source.json",
            "--gold",
            "gold.json",
            "--distractors",
            "distractors.json",
            "--oracle-representations",
            "oracle-representations.json",
            "--oracle-query-plans",
            "oracle-query-plans.json",
            "--output-dir",
            "run",
            "--run-id",
            "run-20260725T120000Z",
            "--dense-model",
            "BAAI/bge-small-en-v1.5",
        ]
    )

    assert args.allow_diagnostic_encoder is False


def test_only_smoke_command_can_enable_the_diagnostic_encoder() -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "smoke",
            "--source",
            "source.json",
            "--gold",
            "gold.json",
            "--distractors",
            "distractors.json",
            "--oracle-representations",
            "oracle-representations.json",
            "--oracle-query-plans",
            "oracle-query-plans.json",
            "--output-dir",
            "run",
            "--run-id",
            "run-20260725T120000Z",
            "--allow-diagnostic-encoder",
        ]
    )

    assert args.allow_diagnostic_encoder is True


def test_smoke_without_diagnostic_flag_uses_real_encoder_boundary(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    captured: dict[str, object] = {}

    class StubRealEncoder:
        model_metadata = {"backend": "fastembed", "diagnostic_only": False}

    def make_encoder(args):
        captured["allow_diagnostic_encoder"] = args.allow_diagnostic_encoder
        return StubRealEncoder()

    def capture_run(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(run_id="run-real-smoke", result_count=36, error_count=0)

    monkeypatch.setattr(cli_module, "_make_encoder", make_encoder)
    monkeypatch.setattr(cli_module, "run_experiment", capture_run)

    assert main(
        [
            "smoke",
            "--source", str(GOLD_DIR / "source-scenarios.json"),
            "--gold", str(GOLD_DIR / "gold.json"),
            "--distractors", str(GOLD_DIR / "distractors.json"),
            "--oracle-representations", str(GOLD_DIR / "oracle-representations.json"),
            "--oracle-query-plans", str(GOLD_DIR / "oracle-query-plans.json"),
            "--output-dir", str(tmp_path / "real-smoke"),
            "--run-id", "run-real-smoke",
            "--scenario-limit", "1",
        ]
    ) == 0

    assert captured["allow_diagnostic_encoder"] is False
    assert len(captured["source_document"]["scenarios"]) == 1
    assert json.loads(capsys.readouterr().out)["model"]["backend"] == "fastembed"


def test_run_commands_default_to_all_and_restrict_split_choices() -> None:
    parser = build_parser()
    required = [
        "--source", "source.json",
        "--gold", "gold.json",
        "--distractors", "distractors.json",
        "--oracle-representations", "oracle-representations.json",
        "--oracle-query-plans", "oracle-query-plans.json",
        "--output-dir", "run",
        "--run-id", "run-20260725T120000Z",
    ]

    assert parser.parse_args(["run", *required]).split == "all"
    assert parser.parse_args(["smoke", *required]).split == "all"
    assert parser.parse_args(["run", *required, "--split", "dev"]).split == "dev"
    assert parser.parse_args(["run", *required, "--split", "hidden"]).split == "hidden"
    with pytest.raises(SystemExit):
        parser.parse_args(["run", *required, "--split", "private"])


@pytest.mark.parametrize(("selected_split", "expected_count"), [("dev", 12), ("hidden", 48)])
def test_run_filters_all_documents_to_selected_split_before_execution(
    selected_split: str,
    expected_count: int,
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    captured: dict[str, object] = {}

    class StubEncoder:
        model_metadata = {"backend": "stub", "diagnostic_only": False}

    def capture_run(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(run_id="run-selected", result_count=0, error_count=0)

    monkeypatch.setattr(cli_module, "_make_encoder", lambda args: StubEncoder())
    monkeypatch.setattr(cli_module, "run_experiment", capture_run)

    assert main(
        [
            "run",
            "--source", str(GOLD_DIR / "source-scenarios.json"),
            "--gold", str(GOLD_DIR / "gold.json"),
            "--distractors", str(GOLD_DIR / "distractors.json"),
            "--oracle-representations", str(GOLD_DIR / "oracle-representations.json"),
            "--oracle-query-plans", str(GOLD_DIR / "oracle-query-plans.json"),
            "--output-dir", str(tmp_path / "run"),
            "--run-id", "run-selected",
            "--split", selected_split,
        ]
    ) == 0
    capsys.readouterr()

    source_ids = [item["scenario_id"] for item in captured["source_document"]["scenarios"]]
    gold_scenarios = captured["gold_document"]["scenarios"]
    assert len(source_ids) == expected_count
    assert [item["scenario_id"] for item in gold_scenarios] == source_ids
    assert {item["split"] for item in gold_scenarios} == {selected_split}
    assert {item["scenario_id"] for item in captured["distractor_document"]["records"]} == set(source_ids)
    assert [item["scenario_id"] for item in captured["oracle_representation_document"]["scenarios"]] == source_ids
    assert [item["scenario_id"] for item in captured["oracle_query_plan_document"]["scenarios"]] == source_ids


def test_smoke_filters_split_before_applying_source_order_limit(monkeypatch, tmp_path: Path, capsys) -> None:
    captured: dict[str, object] = {}

    class StubEncoder:
        model_metadata = {"backend": "stub", "diagnostic_only": True}

    def capture_run(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(run_id="run-smoke-hidden", result_count=0, error_count=0)

    monkeypatch.setattr(cli_module, "_make_encoder", lambda args: StubEncoder())
    monkeypatch.setattr(cli_module, "run_experiment", capture_run)

    assert main(
        [
            "smoke",
            "--source", str(GOLD_DIR / "source-scenarios.json"),
            "--gold", str(GOLD_DIR / "gold.json"),
            "--distractors", str(GOLD_DIR / "distractors.json"),
            "--oracle-representations", str(GOLD_DIR / "oracle-representations.json"),
            "--oracle-query-plans", str(GOLD_DIR / "oracle-query-plans.json"),
            "--output-dir", str(tmp_path / "smoke"),
            "--run-id", "run-smoke-hidden",
            "--allow-diagnostic-encoder",
            "--split", "hidden",
            "--scenario-limit", "2",
        ]
    ) == 0
    capsys.readouterr()

    expected_ids = ["OME-S004", "OME-S005"]
    assert [item["scenario_id"] for item in captured["source_document"]["scenarios"]] == expected_ids
    assert [item["scenario_id"] for item in captured["gold_document"]["scenarios"]] == expected_ids
    assert {item["scenario_id"] for item in captured["distractor_document"]["records"]} == set(expected_ids)
    assert [item["scenario_id"] for item in captured["oracle_representation_document"]["scenarios"]] == expected_ids
    assert [item["scenario_id"] for item in captured["oracle_query_plan_document"]["scenarios"]] == expected_ids


def test_generate_validate_and_diagnostic_smoke_workflow(tmp_path: Path, capsys) -> None:
    generated = tmp_path / "gold"
    assert main(["generate", "--output-dir", str(generated)]) == 0
    generation = json.loads(capsys.readouterr().out)
    assert generation["scenario_count"] == 60
    assert generation["distractor_count"] == 33_000
    assert {path.name for path in generated.iterdir()} == {
        "source-scenarios.json",
        "gold.json",
        "distractors.json",
        "oracle-representations.json",
        "oracle-query-plans.json",
        "manifest.json",
    }

    assert main(["validate-audit", "--audit-dir", str(AUDIT_DIR)]) == 0
    audit = json.loads(capsys.readouterr().out)
    assert audit == {"claim_count": 16, "source_count": 9, "status": "valid"}

    validate_args = [
        "validate-gold",
        "--source", str(GOLD_DIR / "source-scenarios.json"),
        "--gold", str(GOLD_DIR / "gold.json"),
        "--distractors", str(GOLD_DIR / "distractors.json"),
        "--oracle-representations", str(GOLD_DIR / "oracle-representations.json"),
        "--oracle-query-plans", str(GOLD_DIR / "oracle-query-plans.json"),
        "--manifest", str(GOLD_DIR / "manifest.json"),
    ]
    assert main(validate_args) == 0
    validated = json.loads(capsys.readouterr().out)
    assert validated["status"] == "valid"
    assert validated["scenario_count"] == 60

    run_dir = tmp_path / "diagnostic-run"
    assert main(
        [
            "smoke",
            "--source", str(generated / "source-scenarios.json"),
            "--gold", str(generated / "gold.json"),
            "--distractors", str(generated / "distractors.json"),
            "--oracle-representations", str(generated / "oracle-representations.json"),
            "--oracle-query-plans", str(generated / "oracle-query-plans.json"),
            "--output-dir", str(run_dir),
            "--run-id", "run-20260725T130000Z",
            "--allow-diagnostic-encoder",
            "--scenario-limit", "2",
        ]
    ) == 0
    smoke = json.loads(capsys.readouterr().out)
    assert smoke["result_count"] == 72
    assert smoke["error_count"] == 0
    assert main(["verify-run", "--run-dir", str(run_dir)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "valid"

    metrics = tmp_path / "metrics.json"
    assert main(["score", "--run-dir", str(run_dir), "--gold", str(run_dir / "inputs" / "gold.json"), "--output", str(metrics)]) == 0
    assert "arms" in json.loads(metrics.read_text(encoding="utf-8"))
    capsys.readouterr()

    report_json = tmp_path / "report.json"
    report_md = tmp_path / "report.md"
    assert main(
        [
            "report",
            "--metrics", str(metrics),
            "--audit-dir", str(AUDIT_DIR),
            "--json-output", str(report_json),
            "--markdown-output", str(report_md),
        ]
    ) == 0
    assert json.loads(report_json.read_text(encoding="utf-8"))["decision"] in {"pass", "fail", "undecidable"}
    assert "Ontology-Oriented Memory Gate Report" in report_md.read_text(encoding="utf-8")


def test_generate_can_write_v3_fallback_probe_dataset(tmp_path: Path, capsys) -> None:
    generated = tmp_path / "gold-v3"

    assert main(["generate", "--version", "v3", "--output-dir", str(generated)]) == 0
    generation = json.loads(capsys.readouterr().out)

    assert generation["scenario_count"] == 64
    assert generation["distractor_count"] == 35_200
    gold = json.loads((generated / "gold.json").read_text(encoding="utf-8"))
    assert sum("fallback_probe" in scenario["competency"] for scenario in gold["scenarios"]) == 4


def test_generate_can_write_v4_fresh_hidden_dataset(tmp_path: Path, capsys) -> None:
    generated = tmp_path / "gold-v4"

    assert main(["generate", "--version", "v4", "--output-dir", str(generated)]) == 0
    generation = json.loads(capsys.readouterr().out)

    assert generation["scenario_count"] == 64
    assert generation["distractor_count"] == 35_200
    gold = json.loads((generated / "gold.json").read_text(encoding="utf-8"))
    assert sum("fallback_probe_designate" in scenario["competency"] for scenario in gold["scenarios"]) == 4


def test_generate_can_write_v5_fresh_hidden_dataset(tmp_path: Path, capsys) -> None:
    generated = tmp_path / "gold-v5"

    assert main(["generate", "--version", "v5", "--output-dir", str(generated)]) == 0
    generation = json.loads(capsys.readouterr().out)

    assert generation["scenario_count"] == 64
    assert generation["distractor_count"] == 35_200
    gold = json.loads((generated / "gold.json").read_text(encoding="utf-8"))
    assert sum("fallback_probe_route" in scenario["competency"] for scenario in gold["scenarios"]) == 4


def test_validate_gold_infers_manifest_from_source_directory_for_v3(tmp_path: Path, capsys) -> None:
    generated = tmp_path / "gold-v3"
    assert main(["generate", "--version", "v3", "--output-dir", str(generated)]) == 0
    capsys.readouterr()

    assert main(
        [
            "validate-gold",
            "--source", str(generated / "source-scenarios.json"),
            "--gold", str(generated / "gold.json"),
            "--distractors", str(generated / "distractors.json"),
            "--oracle-representations", str(generated / "oracle-representations.json"),
            "--oracle-query-plans", str(generated / "oracle-query-plans.json"),
    ]
    ) == 0
    assert json.loads(capsys.readouterr().out)["scenario_count"] == 64


def test_validate_gold_infers_manifest_from_source_directory_for_v4(tmp_path: Path, capsys) -> None:
    generated = tmp_path / "gold-v4"
    assert main(["generate", "--version", "v4", "--output-dir", str(generated)]) == 0
    capsys.readouterr()

    assert main(
        [
            "validate-gold",
            "--source", str(generated / "source-scenarios.json"),
            "--gold", str(generated / "gold.json"),
            "--distractors", str(generated / "distractors.json"),
            "--oracle-representations", str(generated / "oracle-representations.json"),
            "--oracle-query-plans", str(generated / "oracle-query-plans.json"),
        ]
    ) == 0
    assert json.loads(capsys.readouterr().out)["scenario_count"] == 64
