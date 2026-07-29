"""CLI surface for generating, running, scoring, and verifying the experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence

from tools.ontology_memory_experiment.audit import validate_audit_directory
from tools.ontology_memory_experiment.dense import (
    CachingEncoder,
    DiagnosticEncoder,
    FastEmbedEncoder,
)
from tools.ontology_memory_experiment.executors import execute_arm
from tools.ontology_memory_experiment.io import (
    canonical_json_bytes,
    load_distractor_document,
    load_gold_document,
    load_oracle_query_plan_document,
    load_oracle_representation_document,
    load_source_document,
    sha256_file,
    validate_document_links,
    write_json_immutable,
)
from tools.ontology_memory_experiment.report import build_gate_report
from tools.ontology_memory_experiment.runner import verify_run
from tools.ontology_memory_experiment.runner import ExperimentRunConfig, run_experiment
from tools.ontology_memory_experiment.scenarios import write_frozen_gold
from tools.ontology_memory_experiment.scoring import aggregate_metrics


DEFAULT_DENSE_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_GOLD_DIR = Path("artifacts") / "ontology-memory-experiment" / "gold-v2"


def _add_dataset_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source", default=str(DEFAULT_GOLD_DIR / "source-scenarios.json"))
    parser.add_argument("--gold", default=str(DEFAULT_GOLD_DIR / "gold.json"))
    parser.add_argument("--distractors", default=str(DEFAULT_GOLD_DIR / "distractors.json"))
    parser.add_argument("--oracle-representations", default=str(DEFAULT_GOLD_DIR / "oracle-representations.json"))
    parser.add_argument("--oracle-query-plans", default=str(DEFAULT_GOLD_DIR / "oracle-query-plans.json"))


def _add_run_arguments(parser: argparse.ArgumentParser) -> None:
    _add_dataset_arguments(parser)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--split", choices=("dev", "hidden", "all"), default="all")
    parser.add_argument("--dense-model", default=DEFAULT_DENSE_MODEL)
    parser.add_argument("--model-cache", default="tmp/ontology-model-cache")
    parser.add_argument("--workers", type=int, default=4)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ontology-memory-experiment")
    commands = parser.add_subparsers(dest="command", required=True)

    generate = commands.add_parser("generate")
    generate.add_argument("--output-dir", required=True)
    generate.add_argument("--seed", type=int, default=20260725)
    generate.add_argument("--version", choices=("v2", "v3", "v4", "v5"), default="v2")

    validate_audit = commands.add_parser("validate-audit")
    validate_audit.add_argument("--audit-dir", required=True)

    validate_gold = commands.add_parser("validate-gold")
    _add_dataset_arguments(validate_gold)
    validate_gold.add_argument("--manifest")

    smoke = commands.add_parser("smoke")
    _add_run_arguments(smoke)
    smoke.add_argument("--allow-diagnostic-encoder", action="store_true", default=False)
    smoke.add_argument("--scenario-limit", type=int, default=2)

    run = commands.add_parser("run")
    _add_run_arguments(run)
    run.set_defaults(allow_diagnostic_encoder=False)

    score = commands.add_parser("score")
    score.add_argument("--run-dir", required=True)
    score.add_argument("--gold", required=True)
    score.add_argument("--output", required=True)
    score.add_argument("--bootstrap-seed", type=int, default=20260725)

    report = commands.add_parser("report")
    report.add_argument("--metrics", required=True)
    report.add_argument("--audit-dir", required=True)
    report.add_argument("--json-output", required=True)
    report.add_argument("--markdown-output", required=True)

    verify = commands.add_parser("verify-run")
    verify.add_argument("--run-dir", required=True)
    return parser


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _load_json(path: str | Path) -> object:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"could not read JSON {path}: {error}") from error


def _write_text_immutable(path: str | Path, content: str) -> None:
    output = Path(path)
    encoded = content.encode("utf-8")
    if output.exists():
        if output.read_bytes() != encoded:
            raise FileExistsError(f"immutable artifact differs: {output}")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(encoded)


def _validate_gold_files(args: argparse.Namespace) -> tuple[object, object, object, object, object]:
    source_path = Path(args.source)
    gold_path = Path(args.gold)
    distractor_path = Path(args.distractors)
    representation_path = Path(args.oracle_representations)
    query_plan_path = Path(args.oracle_query_plans)
    source = load_source_document(source_path)
    gold = load_gold_document(gold_path)
    distractors = load_distractor_document(distractor_path)
    representations = load_oracle_representation_document(representation_path)
    query_plans = load_oracle_query_plan_document(query_plan_path)
    validate_document_links(source, gold, distractors)
    scenario_ids = {scenario.scenario_id for scenario in source.scenarios}
    if {scenario.scenario_id for scenario in representations.scenarios} != scenario_ids:
        raise ValueError("oracle representation scenarios do not match source")
    if {scenario.scenario_id for scenario in query_plans.scenarios} != scenario_ids:
        raise ValueError("oracle query-plan scenarios do not match source")
    source_hash = sha256_file(source_path)
    if representations.source_sha256 != source_hash or query_plans.source_sha256 != source_hash:
        raise ValueError("oracle artifacts are not bound to the source hash")
    manifest_path = Path(args.manifest) if getattr(args, "manifest", None) else source_path.parent / "manifest.json"
    if manifest_path.exists():
        manifest = _load_json(manifest_path)
        if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), dict):
            raise ValueError("gold manifest is invalid")
        expected = {
            "source": source_path,
            "gold": gold_path,
            "distractors": distractor_path,
            "oracle_representations": representation_path,
            "oracle_query_plans": query_plan_path,
        }
        for name, path in expected.items():
            entry = manifest["files"].get(name)
            if not isinstance(entry, dict) or entry.get("sha256") != sha256_file(path):
                raise ValueError(f"gold manifest hash mismatch: {name}")
    elif getattr(args, "manifest", None):
        raise ValueError(f"gold manifest does not exist: {manifest_path}")
    return source, gold, distractors, representations, query_plans


def _subset_documents(
    documents: tuple[object, object, object, object, object],
    limit: int | None,
    split: str = "all",
):
    source, gold, distractors, representations, query_plans = documents
    source_data = source.model_dump(mode="json")
    gold_data = gold.model_dump(mode="json")
    split_ids = {
        item["scenario_id"]
        for item in gold_data["scenarios"]
        if split == "all" or item["split"] == split
    }
    selected = [
        item for item in source_data["scenarios"]
        if item["scenario_id"] in split_ids
    ]
    if limit is not None:
        selected = selected[:limit]
    selected_ids = {item["scenario_id"] for item in selected}
    source_data["scenarios"] = selected

    def subset(document: object, *, records: bool = False) -> dict[str, object]:
        value = document.model_dump(mode="json")
        key = "records" if records else "scenarios"
        value[key] = [item for item in value[key] if item["scenario_id"] in selected_ids]
        return value

    subset_source_sha256 = hashlib.sha256(canonical_json_bytes(source_data)).hexdigest()
    representation_data = subset(representations)
    representation_data["source_sha256"] = subset_source_sha256
    query_plan_data = subset(query_plans)
    query_plan_data["source_sha256"] = subset_source_sha256

    return (
        source_data,
        subset(gold),
        subset(distractors, records=True),
        representation_data,
        query_plan_data,
    )


def _make_encoder(args: argparse.Namespace):
    if getattr(args, "allow_diagnostic_encoder", False):
        return CachingEncoder(DiagnosticEncoder())
    encoder = CachingEncoder(
        FastEmbedEncoder(model_name=args.dense_model, cache_dir=args.model_cache)
    )
    if encoder.model_metadata.get("diagnostic_only"):
        raise ValueError("main runs require a real dense encoder")
    return encoder


def _run(args: argparse.Namespace, *, smoke: bool) -> dict[str, object]:
    documents = _validate_gold_files(args)
    documents = _subset_documents(
        documents,
        args.scenario_limit if smoke else None,
        split=args.split,
    )
    source, gold, distractors, representations, query_plans = documents
    encoder = _make_encoder(args)
    if not smoke and encoder.model_metadata.get("diagnostic_only"):
        raise ValueError("diagnostic encoder is forbidden for the main run")
    summary = run_experiment(
        source_document=source,
        gold_document=gold,
        distractor_document=distractors,
        oracle_representation_document=representations,
        oracle_query_plan_document=query_plans,
        output_dir=args.output_dir,
        encoder=encoder,
        config=ExperimentRunConfig(run_id=args.run_id, workers=args.workers),
        execute=execute_arm,
    )
    return {
        "status": "completed",
        "run_id": summary.run_id,
        "result_count": summary.result_count,
        "error_count": summary.error_count,
        "model": dict(encoder.model_metadata),
    }


def _render_report(report: dict[str, object]) -> str:
    lines = [
        "# Ontology-Oriented Memory Gate Report",
        "",
        f"Decision: {report['decision']}",
        "",
        "## Gates",
        "",
    ]
    gates = report.get("gates", [])
    if not gates:
        lines.append("No gate result is available.")
    for gate in gates:
        lines.append(f"- {gate['name']}: {gate['status']} - {gate['detail']}")
    reasons = report.get("reasons", [])
    if reasons:
        lines.extend(["", "## Reasons", ""] + [f"- {reason}" for reason in reasons])
    lines.extend(
        [
            "",
            "## Interpretation Boundary",
            "",
            "These are controlled architecture-class results. Mem0, Graphiti, Hindsight, and MemPalace were not rerun and receive no local score.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "generate":
        if args.seed != 20260725:
            raise ValueError("the frozen generator accepts only seed 20260725")
        manifest = write_frozen_gold(Path(args.output_dir), version=args.version)
        source = load_source_document(Path(args.output_dir) / "source-scenarios.json")
        distractors = load_distractor_document(Path(args.output_dir) / "distractors.json")
        _print({"status": "generated", "version": args.version, "scenario_count": len(source.scenarios), "distractor_count": len(distractors.records), "manifest": manifest})
        return 0
    if args.command == "validate-audit":
        audit = validate_audit_directory(Path(args.audit_dir))
        invalid = audit.invalid_claims + audit.unsupported_confirmed_gaps + audit.invalid_direct_comparisons + audit.invalid_source_snapshots
        if invalid:
            raise ValueError(f"audit validation failed: {invalid}")
        _print({"status": "valid", "claim_count": audit.claim_count, "source_count": audit.official_source_count})
        return 0
    if args.command == "validate-gold":
        source, _, distractors, _, _ = _validate_gold_files(args)
        _print({"status": "valid", "scenario_count": len(source.scenarios), "distractor_count": len(distractors.records)})
        return 0
    if args.command == "smoke":
        _print(_run(args, smoke=True))
        return 0
    if args.command == "run":
        _print(_run(args, smoke=False))
        return 0
    if args.command == "score":
        run_dir = Path(args.run_dir)
        verify_run(run_dir)
        rows = [json.loads(line) for line in (run_dir / "results.jsonl").read_text(encoding="utf-8").splitlines() if line]
        supplied_gold_path = Path(args.gold)
        run_manifest = _load_json(run_dir / "manifest.json")
        if not isinstance(run_manifest, dict) or not isinstance(run_manifest.get("gold_sha256"), str):
            raise ValueError("run manifest is missing gold_sha256")
        supplied_gold_sha256 = sha256_file(supplied_gold_path)
        if supplied_gold_sha256 != run_manifest["gold_sha256"]:
            raise ValueError("supplied gold hash does not match run manifest")
        gold_document = load_gold_document(supplied_gold_path)
        gold = {item.scenario_id: item.model_dump(mode="json") for item in gold_document.scenarios}
        distractor_document = load_distractor_document(run_dir / "inputs" / "distractors.json")
        critical_distractor_ids: dict[str, list[str]] = {}
        for record in distractor_document.records:
            critical_distractor_ids.setdefault(record.scenario_id, []).append(record.record_id)
        metrics = aggregate_metrics(
            rows,
            gold,
            bootstrap_seed=args.bootstrap_seed,
            critical_distractor_ids=critical_distractor_ids,
        )
        metrics["run"] = {"run_id": run_manifest["run_id"], "bootstrap_seed": args.bootstrap_seed}
        write_json_immutable(Path(args.output), metrics)
        _print({"status": "scored", "result_count": len(rows)})
        return 0
    if args.command == "report":
        metrics = _load_json(args.metrics)
        if not isinstance(metrics, dict):
            raise ValueError("metrics must be a JSON object")
        audit = validate_audit_directory(Path(args.audit_dir))
        if audit.invalid_claims or audit.invalid_source_snapshots:
            raise ValueError("audit must be valid before reporting")
        report = build_gate_report(metrics)
        report["architecture_audit"] = {
            "claim_count": audit.claim_count,
            "official_source_count": audit.official_source_count,
            "named_systems_rerun": False,
        }
        write_json_immutable(Path(args.json_output), report)
        _write_text_immutable(args.markdown_output, _render_report(report))
        _print({"status": "reported", "decision": report["decision"]})
        return 0
    if args.command == "verify-run":
        _print(verify_run(args.run_dir))
        return 0
    raise NotImplementedError(f"command integration is pending: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
