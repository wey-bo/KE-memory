from __future__ import annotations

import argparse
from pathlib import Path

from .io import load_json, write_json_immutable
from .query_compiler_v2_assessment import (
    QueryCompilerAuthorityDocumentV1,
    QueryCompilerBatchResultV1,
    QueryCompilerFormalFreezeV1,
    QueryCompilerGoldDocumentV1,
    run_query_compiler_batch_file,
    score_query_compiler_batch,
)


def _path(value: str) -> Path:
    return Path(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="query-compiler-v2")
    subparsers = parser.add_subparsers(dest="command", required=True)

    compile_parser = subparsers.add_parser("compile-batch")
    compile_parser.add_argument("--public", required=True, type=_path)
    compile_parser.add_argument("--authority", required=True, type=_path)
    compile_parser.add_argument("--proposals", required=True, type=_path)
    compile_parser.add_argument("--output", required=True, type=_path)
    compile_parser.add_argument("--run-id", required=True)

    score_parser = subparsers.add_parser("score-batch")
    score_parser.add_argument("--batch", required=True, type=_path)
    score_parser.add_argument("--gold", required=True, type=_path)
    score_parser.add_argument("--output", required=True, type=_path)
    score_parser.add_argument(
        "--assessment-mode",
        choices=["dev_smoke", "formal_gate"],
        default="dev_smoke",
    )
    score_parser.add_argument("--formal-repo", type=_path)
    score_parser.add_argument("--formal-freeze", type=_path)
    score_parser.add_argument("--authority", type=_path)
    score_parser.add_argument("--memory-repo", type=_path)
    return parser


def _score_batch(args: argparse.Namespace) -> dict[str, object]:
    batch = QueryCompilerBatchResultV1.model_validate(load_json(args.batch))
    gold = QueryCompilerGoldDocumentV1.model_validate(load_json(args.gold))
    formal_values = [
        args.formal_repo,
        args.formal_freeze,
        args.authority,
        args.memory_repo,
    ]
    if any(item is not None for item in formal_values) and not all(
        item is not None for item in formal_values
    ):
        raise ValueError("formal verification arguments must be supplied together")

    freeze = None
    authority = None
    if args.formal_freeze is not None:
        freeze = QueryCompilerFormalFreezeV1.model_validate(
            load_json(args.formal_freeze)
        )
        authority = QueryCompilerAuthorityDocumentV1.model_validate(
            load_json(args.authority)
        )
    score = score_query_compiler_batch(
        batch,
        gold,
        assessment_mode=args.assessment_mode,
        formal_repo_path=args.formal_repo,
        formal_freeze=freeze,
        authority=authority,
        memory_repo_path=args.memory_repo,
    )
    payload = score.model_dump(mode="json")
    write_json_immutable(args.output, payload)
    args.output.chmod(0o444)
    return payload


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "compile-batch":
        run_query_compiler_batch_file(
            public_path=args.public,
            authority_path=args.authority,
            proposals_path=args.proposals,
            output_path=args.output,
            run_id=args.run_id,
        )
        return 0
    if args.command == "score-batch":
        _score_batch(args)
        return 0
    raise ValueError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
