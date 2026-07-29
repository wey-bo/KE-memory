from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .git_memory_history import (
    GitMemoryHistoryError,
    GitMemoryHistoryRepository,
    HardPurgeRequest,
    HistoryArtifact,
)
from .io import canonical_json_bytes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Operate an isolated Git-backed memory history repository.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init")
    init.add_argument("--repo", required=True)
    init.add_argument("--workspace-id", required=True)
    init.add_argument("--created-at", required=True)

    commit = commands.add_parser("commit")
    commit.add_argument("--repo", required=True)
    commit.add_argument("--transaction-time", required=True)
    commit.add_argument("--artifacts", required=True)
    commit.add_argument("--expected-head", required=True)

    verify = commands.add_parser("verify")
    verify.add_argument("--repo", required=True)

    show_state = commands.add_parser("show-state")
    show_state.add_argument("--repo", required=True)

    purge = commands.add_parser("prepare-hard-purge")
    purge.add_argument("--repo", required=True)
    purge.add_argument("--destination", required=True)
    purge.add_argument("--request", required=True)
    return parser


def _load_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _emit(value: Any, *, stream: Any = None) -> None:
    target = stream or sys.stdout.buffer
    target.write(canonical_json_bytes(value))
    target.flush()


def _run_init(args: argparse.Namespace) -> dict[str, Any]:
    repository = GitMemoryHistoryRepository.initialize(
        args.repo,
        workspace_id=args.workspace_id,
        created_at=args.created_at,
    )
    metadata = repository.read_repository_metadata()
    return {
        "status": "initialized",
        "repository": metadata.model_dump(mode="json"),
        "head_commit": repository.head_commit(),
    }


def _run_commit(args: argparse.Namespace) -> Any:
    raw_artifacts = _load_json(args.artifacts)
    if not isinstance(raw_artifacts, list):
        raise ValueError("artifacts input must be a JSON array")
    artifacts = [
        HistoryArtifact.model_validate(item) for item in raw_artifacts
    ]
    repository = GitMemoryHistoryRepository(args.repo)
    manifest = repository.make_checkpoint(
        artifacts=artifacts,
        transaction_time=args.transaction_time,
    )
    return repository.commit_checkpoint(
        manifest=manifest,
        artifacts=artifacts,
        expected_head=args.expected_head,
    )


def _run_verify(args: argparse.Namespace) -> tuple[Any, int]:
    report = GitMemoryHistoryRepository(args.repo).verify()
    return report, 0 if report.status == "valid" else 1


def _run_show_state(args: argparse.Namespace) -> Any:
    return GitMemoryHistoryRepository(args.repo).read_state()


def _run_prepare_hard_purge(args: argparse.Namespace) -> Any:
    request = HardPurgeRequest.model_validate(_load_json(args.request))
    repository = GitMemoryHistoryRepository(args.repo)
    return repository.prepare_hard_purge(
        args.destination,
        request=request,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            result = _run_init(args)
            status = 0
        elif args.command == "commit":
            result = _run_commit(args)
            status = 0
        elif args.command == "verify":
            result, status = _run_verify(args)
        elif args.command == "show-state":
            result = _run_show_state(args)
            status = 0
        elif args.command == "prepare-hard-purge":
            result = _run_prepare_hard_purge(args)
            status = 0
        else:
            raise ValueError(f"unsupported command: {args.command}")
        _emit(result)
        return status
    except (
        GitMemoryHistoryError,
        ValidationError,
        ValueError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        _emit(
            {
                "status": "error",
                "error_type": type(exc).__name__,
                "message": str(exc),
            },
            stream=sys.stderr.buffer,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
