"""Command-line entry points for knowledge-pipeline preparation."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from knowledge_pipeline.dialogue_pass import prepare_dialogue_payloads, validate_dialogue_batch
from knowledge_pipeline.export import write_turn_grouped_export
from knowledge_pipeline.keyword_v3 import prepare_keyword_v3_payloads, validate_keyword_v3_batch
from knowledge_pipeline.keywords import prepare_keyword_payloads, validate_keyword_batch
from knowledge_pipeline.projector import project_and_record
from knowledge_pipeline.source import load_turn_units, write_turn_inputs
from knowledge_pipeline.turn_pass import prepare_turn_payloads, validate_turn_batch


DEFAULT_SOURCE = Path("data/gold-candidates/KE-test.json")


def _prepare_turns(args: argparse.Namespace) -> int:
    write_turn_inputs(load_turn_units(args.input), args.output_dir)
    return 0


def _prepare_turn_payloads(args: argparse.Namespace) -> int:
    prepare_turn_payloads(args.input, args.output_dir, args.prompt, args.source_segments)
    return 0


def _validate_turns(args: argparse.Namespace) -> int:
    validate_turn_batch(args.manifest, args.raw_dir, args.output_dir)
    return 0


def _prepare_dialogues(args: argparse.Namespace) -> int:
    prepare_dialogue_payloads(args.input, args.turn_manifest, args.output_dir, args.prompt)
    return 0


def _validate_dialogues(args: argparse.Namespace) -> int:
    validate_dialogue_batch(args.manifest, args.raw_dir, args.output_dir)
    return 0


def _project(args: argparse.Namespace) -> int:
    project_and_record(args.turn_manifest, args.dialogue_manifest, args.output, args.run)
    return 0


def _prepare_keywords(args: argparse.Namespace) -> int:
    prepare_keyword_payloads(args.final_knowledge, args.output_dir, args.prompt)
    return 0


def _validate_keywords(args: argparse.Namespace) -> int:
    validate_keyword_batch(args.manifest, args.raw_dir, args.output)
    return 0


def _prepare_keywords_v3(args: argparse.Namespace) -> int:
    prepare_keyword_v3_payloads(args.final_knowledge, args.output_dir, args.prompt)
    return 0


def _validate_keywords_v3(args: argparse.Namespace) -> int:
    validate_keyword_v3_batch(args.manifest, args.raw_dir, args.output, args.wordnet_dir)
    return 0


def _export_final_json(args: argparse.Namespace) -> int:
    write_turn_grouped_export(args.source, args.final_knowledge, args.keyword_pass, args.output)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="knowledge-pipeline")
    subcommands = parser.add_subparsers(dest="command", required=True)
    prepare = subcommands.add_parser("prepare-turns")
    prepare.add_argument("--input", type=Path, default=DEFAULT_SOURCE)
    prepare.add_argument("--output-dir", type=Path, required=True)
    prepare.set_defaults(handler=_prepare_turns)
    payloads = subcommands.add_parser("prepare-turn-payloads", help="write isolated turn-pass model payloads")
    payloads.add_argument("--input", type=Path, default=DEFAULT_SOURCE)
    payloads.add_argument("--output-dir", type=Path, required=True)
    payloads.add_argument("--prompt", type=Path, default=Path("knowledge-extraction/prompts/turn_knowledge_extraction.md"))
    payloads.add_argument("--source-segments", type=Path, default=Path("knowledge-extraction/source-segments.json"))
    payloads.set_defaults(handler=_prepare_turn_payloads)
    validate = subcommands.add_parser("validate-turns", help="validate a complete raw turn-pass batch atomically")
    validate.add_argument("--manifest", type=Path, required=True, help="manifest emitted by prepare-turn-payloads")
    validate.add_argument("--raw-dir", type=Path, required=True, help="raw model JSON outputs; this directory is never modified")
    validate.add_argument("--output-dir", type=Path, required=True, help="destination root for validated outputs")
    validate.set_defaults(handler=_validate_turns)
    dialogues = subcommands.add_parser("prepare-dialogues", help="write one reconciliation payload per candidate")
    dialogues.add_argument("--input", type=Path, default=DEFAULT_SOURCE)
    dialogues.add_argument("--turn-manifest", type=Path, required=True, help="validated turn-pass manifest or directory")
    dialogues.add_argument("--output-dir", type=Path, required=True)
    dialogues.add_argument("--prompt", type=Path, default=Path("knowledge-extraction/prompts/dialogue_reconciliation.md"))
    dialogues.set_defaults(handler=_prepare_dialogues)
    validate_dialogues = subcommands.add_parser("validate-dialogues", help="validate a complete raw dialogue-pass batch atomically")
    validate_dialogues.add_argument("--manifest", type=Path, required=True, help="manifest emitted by prepare-dialogues")
    validate_dialogues.add_argument("--raw-dir", type=Path, required=True, help="raw model JSON outputs; this directory is never modified")
    validate_dialogues.add_argument("--output-dir", type=Path, required=True, help="destination root for validated outputs")
    validate_dialogues.set_defaults(handler=_validate_dialogues)
    project = subcommands.add_parser("project", help="project the deterministic active knowledge ledger")
    project.add_argument(
        "--turn-manifest",
        type=Path,
        default=Path("knowledge-extraction/turn-pass/validated/manifest.json"),
    )
    project.add_argument(
        "--dialogue-manifest",
        type=Path,
        default=Path("knowledge-extraction/dialogue-pass/validated/manifest.json"),
    )
    project.add_argument("--output", type=Path, default=Path("knowledge-extraction/final-knowledge.json"))
    project.add_argument("--run", type=Path, default=Path("knowledge-extraction/run.json"))
    project.set_defaults(handler=_project)
    prepare_keywords = subcommands.add_parser("prepare-keywords", help="write active-knowledge keyword payloads")
    prepare_keywords.add_argument(
        "--final-knowledge", type=Path, default=Path("knowledge-extraction/final-knowledge.json")
    )
    prepare_keywords.add_argument(
        "--output-dir", type=Path, default=Path("knowledge-extraction/keyword-pass/prepared")
    )
    prepare_keywords.add_argument(
        "--prompt",
        type=Path,
        default=Path("knowledge-extraction/prompts/knowledge_keyword_extraction.md"),
    )
    prepare_keywords.set_defaults(handler=_prepare_keywords)
    validate_keywords = subcommands.add_parser("validate-keywords", help="validate and aggregate keyword outputs")
    validate_keywords.add_argument(
        "--manifest", type=Path, default=Path("knowledge-extraction/keyword-pass/prepared/manifest.json")
    )
    validate_keywords.add_argument(
        "--raw-dir", type=Path, default=Path("knowledge-extraction/keyword-pass/raw")
    )
    validate_keywords.add_argument(
        "--output", type=Path, default=Path("knowledge-extraction/keyword-pass.json")
    )
    validate_keywords.set_defaults(handler=_validate_keywords)
    prepare_keywords_v3 = subcommands.add_parser(
        "prepare-keywords-v3",
        help="write active-knowledge payloads for atomic WordNet-backed keywords",
    )
    prepare_keywords_v3.add_argument(
        "--final-knowledge", type=Path, default=Path("knowledge-extraction/final-knowledge.json")
    )
    prepare_keywords_v3.add_argument(
        "--output-dir", type=Path, default=Path("knowledge-extraction/keyword-pass-v3/prepared")
    )
    prepare_keywords_v3.add_argument(
        "--prompt",
        type=Path,
        default=Path("knowledge-extraction/prompts/knowledge_keyword_extraction_v3.md"),
    )
    prepare_keywords_v3.set_defaults(handler=_prepare_keywords_v3)
    validate_keywords_v3 = subcommands.add_parser(
        "validate-keywords-v3",
        help="validate WordNet mappings and aggregate atomic keyword outputs",
    )
    validate_keywords_v3.add_argument(
        "--manifest", type=Path, default=Path("knowledge-extraction/keyword-pass-v3/prepared/manifest.json")
    )
    validate_keywords_v3.add_argument(
        "--raw-dir", type=Path, default=Path("knowledge-extraction/keyword-pass-v3/raw")
    )
    validate_keywords_v3.add_argument(
        "--output", type=Path, default=Path("knowledge-extraction/keyword-pass-v3/keyword-pass.json")
    )
    validate_keywords_v3.add_argument(
        "--wordnet-dir", type=Path, default=Path("knowledge-extraction/resources/nltk_data")
    )
    validate_keywords_v3.set_defaults(handler=_validate_keywords_v3)
    export_final = subcommands.add_parser("export-final-json", help="write dialogue/turn/role knowledge and keywords JSON")
    export_final.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    export_final.add_argument(
        "--final-knowledge", type=Path, default=Path("knowledge-extraction/final-knowledge.json")
    )
    export_final.add_argument(
        "--keyword-pass",
        type=Path,
        default=Path("knowledge-extraction/keyword-pass-v3/keyword-pass.json"),
    )
    export_final.add_argument(
        "--output", type=Path, default=Path("knowledge-extraction/KE-knowledge-keywords.json")
    )
    export_final.set_defaults(handler=_export_final_json)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
