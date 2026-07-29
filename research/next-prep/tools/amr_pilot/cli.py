"""Command-line entry points for the reproducible AMR pilot workflow."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from typing import Sequence

from tools.amr_pilot.gold import load_and_validate_gold, validate_gold_approval
from tools.amr_pilot.inputs import load_and_validate_inputs
from tools.amr_pilot.models import AttemptSidecar, SemanticChecklist
from tools.amr_pilot.payloads import build_payload, load_prompt_contracts, write_payload_manifest
from tools.amr_pilot.penman_validation import validate_penman
from tools.amr_pilot.report import build_gate_report, render_report_markdown
from tools.amr_pilot.scoring import (
    EfficiencySummary,
    make_blind_mapping,
    make_blind_review_payloads,
    score_semantics,
)


def _read_json(path: str | Path) -> object:
    source = Path(path)
    try:
        return json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"could not parse {source}: {error}") from error


def _write_json(path: str | Path, value: object) -> Path:
    output = Path(path)
    content = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if output.exists():
        if output.read_text(encoding="utf-8") == content:
            return output
        raise ValueError(f"refusing to overwrite different output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    return output


def _write_text(path: str | Path, content: str) -> Path:
    output = Path(path)
    if output.exists():
        if output.read_text(encoding="utf-8") == content:
            return output
        raise ValueError(f"refusing to overwrite different output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    return output


def _print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _add_input_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--sentences", required=True)
    parser.add_argument("--source-records", required=True)
    parser.add_argument("--ke-test", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="amr-pilot")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_inputs = subparsers.add_parser("validate-inputs")
    _add_input_arguments(validate_inputs)

    validate_gold = subparsers.add_parser("validate-gold")
    _add_input_arguments(validate_gold)
    validate_gold.add_argument("--draft", required=True)
    validate_gold.add_argument("--approval")

    prepare_payloads = subparsers.add_parser("prepare-payloads")
    _add_input_arguments(prepare_payloads)
    prepare_payloads.add_argument("--prompts", required=True)
    prepare_payloads.add_argument("--output-dir", required=True)
    prepare_payloads.add_argument("--routes", nargs="+", choices=("A", "B", "C"), required=True)
    prepare_payloads.add_argument("--atomic-dir")

    validate_attempt = subparsers.add_parser("validate-attempt")
    validate_attempt.add_argument("--raw", required=True)
    validate_attempt.add_argument("--sidecar", required=True)
    validate_attempt.add_argument("--propbank-inventory", required=True)

    blind = subparsers.add_parser("prepare-blind-review")
    blind.add_argument("--run-id", required=True)
    blind.add_argument("--candidates", required=True)
    blind.add_argument("--review-output", required=True)
    blind.add_argument("--mapping-output", required=True)

    score = subparsers.add_parser("score")
    score.add_argument("--checklist", required=True)
    score.add_argument("--review", required=True)
    score.add_argument("--output", required=True)

    report = subparsers.add_parser("report")
    report.add_argument("--input", required=True)
    report.add_argument("--json-output", required=True)
    report.add_argument("--markdown-output", required=True)
    return parser


def _inputs(args: argparse.Namespace):
    return load_and_validate_inputs(args.sentences, args.source_records, args.ke_test)


def _validate_inputs(args: argparse.Namespace) -> None:
    inputs = _inputs(args)
    _print_json(
        {
            "status": "valid",
            "sample_count": len(inputs.samples),
            "phenomenon_counts": dict(sorted(Counter(item.phenomenon for item in inputs.samples).items())),
        }
    )


def _validate_gold(args: argparse.Namespace) -> None:
    inputs = _inputs(args)
    draft = load_and_validate_gold(args.draft, inputs)
    status = draft.status
    gold_sha256 = hashlib.sha256(Path(args.draft).read_bytes()).hexdigest()
    if args.approval:
        validate_gold_approval(args.draft, args.approval, inputs)
        status = "approved"
    _print_json(
        {
            "status": status,
            "checklist_count": len(draft.checklists),
            "gold_sha256": gold_sha256,
        }
    )


def _prepare_payloads(args: argparse.Namespace) -> None:
    inputs = _inputs(args)
    contracts = load_prompt_contracts(args.prompts)
    routes = tuple(dict.fromkeys(args.routes))
    if "B" in routes and not args.atomic_dir:
        raise ValueError("route B requires --atomic-dir")
    payloads: list[dict[str, object]] = []
    for sample in inputs.samples:
        for route in routes:
            atomic = None
            if route == "B":
                atomic = _read_json(Path(args.atomic_dir) / f"{sample.sample_id}.json")
            payloads.append(build_payload(sample, route, contracts, atomic_knowledge=atomic))
    output = Path(args.output_dir)
    _write_json(
        output / "payloads.json",
        {"schema_version": "amr-pilot-payload-set-v1", "payloads": payloads},
    )
    write_payload_manifest(contracts, payloads, output / "manifest.json")
    _print_json({"status": "prepared", "payload_count": len(payloads), "routes": routes})


def _validate_attempt(args: argparse.Namespace) -> None:
    raw = Path(args.raw).read_text(encoding="utf-8")
    sidecar = AttemptSidecar.model_validate(_read_json(args.sidecar))
    raw_sha256 = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    if sidecar.raw_output_sha256 != raw_sha256:
        raise ValueError("sidecar raw_output_sha256 does not match raw output")
    inventory = _read_json(args.propbank_inventory)
    if not isinstance(inventory, list) or any(not isinstance(frame, str) for frame in inventory):
        raise ValueError("PropBank inventory must be a JSON list of strings")
    result = validate_penman(raw, propbank_inventory=set(inventory))
    expected_parse_status = "valid" if result.syntax_valid else "invalid"
    if sidecar.parse_status != expected_parse_status:
        raise ValueError("sidecar parse_status does not match the validator result")
    _print_json(
        {
            "syntax_valid": result.syntax_valid,
            "is_valid": result.is_valid,
            "graph_count": result.graph_count,
            "errors": result.errors,
            "unknown_frames": result.unknown_frames,
        }
    )


def _prepare_blind_review(args: argparse.Namespace) -> None:
    document = _read_json(args.candidates)
    if not isinstance(document, dict) or set(document) != {"candidates"}:
        raise ValueError("candidate document must contain only candidates")
    candidates = document["candidates"]
    if not isinstance(candidates, list):
        raise ValueError("candidates must be a list")
    payloads = make_blind_review_payloads(args.run_id, candidates)
    mapping = make_blind_mapping(args.run_id, candidates)
    _write_json(
        args.review_output,
        {"schema_version": "amr-pilot-blind-review-v1", "items": payloads},
    )
    _write_json(
        args.mapping_output,
        {"schema_version": "amr-pilot-blind-mapping-v1", "items": mapping},
    )
    _print_json({"status": "prepared", "candidate_count": len(payloads)})


def _score(args: argparse.Namespace) -> None:
    checklist = SemanticChecklist.model_validate(_read_json(args.checklist))
    review = _read_json(args.review)
    if not isinstance(review, dict):
        raise ValueError("review must be an object")
    result = score_semantics(checklist, review)
    _write_json(args.output, asdict(result))
    _print_json({"status": "scored", "sample_id": checklist.sample_id})


def _report(args: argparse.Namespace) -> None:
    document = _read_json(args.input)
    if not isinstance(document, dict) or set(document) != {
        "route_metrics",
        "efficiency",
        "hard_categories",
    }:
        raise ValueError("report input has unknown or missing fields")
    route_metrics = document["route_metrics"]
    efficiency_values = document["efficiency"]
    hard_categories = document["hard_categories"]
    if not isinstance(route_metrics, dict) or not isinstance(efficiency_values, dict):
        raise ValueError("report route data must be objects")
    if not isinstance(hard_categories, list) or any(not isinstance(item, str) for item in hard_categories):
        raise ValueError("hard_categories must be a list of strings")
    efficiency = {
        route: EfficiencySummary(**value)
        for route, value in efficiency_values.items()
        if isinstance(value, dict)
    }
    report = build_gate_report(
        route_metrics=route_metrics,
        efficiency=efficiency,
        hard_categories=set(hard_categories),
    )
    _write_json(args.json_output, report)
    _write_text(args.markdown_output, render_report_markdown(report))
    _print_json({"status": "reported", "decision": report["decision"]})


COMMANDS = {
    "validate-inputs": _validate_inputs,
    "validate-gold": _validate_gold,
    "prepare-payloads": _prepare_payloads,
    "validate-attempt": _validate_attempt,
    "prepare-blind-review": _prepare_blind_review,
    "score": _score,
    "report": _report,
}


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    COMMANDS[args.command](args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
