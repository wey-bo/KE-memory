from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Sequence

from .io import canonical_json_bytes, load_json
from .query_compiler_v2_assessment import (
    QueryCompilerAuthorityDocumentV1,
    QueryCompilerGoldDocumentV1,
    QueryCompilerPublicDocumentV1,
)
from .query_compiler_v2_proposal_eval import (
    QueryDraftGoldDocumentV1,
    QueryDraftProposalDocumentV1,
    evaluate_query_draft_proposals,
    validate_frozen_query_draft_proposal_run,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="query-draft-proposal-eval")
    commands = parser.add_subparsers(dest="command", required=True)

    score = commands.add_parser("score-proposals")
    score.add_argument("--public", required=True)
    score.add_argument("--authority", required=True)
    score.add_argument("--proposals", required=True)
    score.add_argument("--draft-gold", required=True)
    score.add_argument("--compiler-gold", required=True)
    score.add_argument("--output", required=True)

    validate = commands.add_parser("validate-run")
    validate.add_argument("--root", required=True)
    return parser


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _validate_existing_output(path: Path, content: bytes) -> None:
    if path.is_symlink():
        raise ValueError(f"output path is a symlink: {path}")
    if not path.is_file():
        raise FileExistsError(f"immutable artifact type differs: {path}")
    if path.read_bytes() != content:
        raise FileExistsError(f"immutable artifact differs: {path}")


def _write_json_atomic_immutable(path: Path, value: object) -> None:
    content = canonical_json_bytes(value)
    if path.is_symlink():
        raise ValueError(f"output path is a symlink: {path}")
    if path.exists():
        _validate_existing_output(path, content)
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary_path, 0o444)
        try:
            os.link(temporary_path, path)
        except FileExistsError:
            _validate_existing_output(path, content)
    finally:
        temporary_path.unlink(missing_ok=True)


def _validate_output_aliases(output: Path, inputs: list[Path]) -> None:
    if output.is_symlink():
        raise ValueError(f"output path is a symlink: {output}")
    resolved_output = output.resolve(strict=False)
    for input_path in inputs:
        if resolved_output == input_path.resolve(strict=False):
            raise ValueError(f"output aliases input: {input_path}")
        if output.exists() and input_path.exists():
            if os.path.samefile(output, input_path):
                raise ValueError(f"output aliases input: {input_path}")


def _score_proposals(args: argparse.Namespace) -> None:
    paths = {
        "public": Path(args.public),
        "authority": Path(args.authority),
        "proposals": Path(args.proposals),
        "draft_gold": Path(args.draft_gold),
        "compiler_gold": Path(args.compiler_gold),
    }
    output_path = Path(args.output)
    _validate_output_aliases(output_path, list(paths.values()))
    public = QueryCompilerPublicDocumentV1.model_validate(
        load_json(paths["public"])
    )
    authority = QueryCompilerAuthorityDocumentV1.model_validate(
        load_json(paths["authority"])
    )
    proposals = QueryDraftProposalDocumentV1.model_validate(
        load_json(paths["proposals"])
    )
    draft_gold = QueryDraftGoldDocumentV1.model_validate(
        load_json(paths["draft_gold"])
    )
    compiler_gold = QueryCompilerGoldDocumentV1.model_validate(
        load_json(paths["compiler_gold"])
    )
    evaluation = evaluate_query_draft_proposals(
        public=public,
        authority=authority,
        proposals=proposals,
        draft_gold=draft_gold,
        compiler_gold=compiler_gold,
    )
    _write_json_atomic_immutable(output_path, evaluation)
    _print(
        {
            "status": "scored",
            "dataset_id": evaluation.dataset_id,
            "gate_evaluated": evaluation.gate_evaluated,
            "combined_dev_ready": evaluation.combined_dev_ready,
        }
    )


def _validate_run(args: argparse.Namespace) -> None:
    manifest = validate_frozen_query_draft_proposal_run(Path(args.root))
    _print(
        {
            "status": "valid",
            "dataset_id": manifest.dataset_id,
            "run_id": manifest.run_id,
            "requested_model": manifest.requested_model,
            "response_model": manifest.response_model,
        }
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "score-proposals":
            _score_proposals(args)
        elif args.command == "validate-run":
            _validate_run(args)
    except (OSError, TypeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
