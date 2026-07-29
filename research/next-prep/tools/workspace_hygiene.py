from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any, Sequence


SCHEMA_VERSION = "workspace-cleanup-plan-v2"
REPORT_SCHEMA_VERSION = "workspace-cleanup-report-v2"
POLICY_ID = "conservative-regenerable-explicit-paths-v2"

EXACT_CLEANUP_NAMES = frozenset(
    {
        ".t",
        ".tmp",
        ".pytest_cache",
        "t",
        "t2",
    }
)
CLEANUP_PREFIXES = (".pytest-tmp-",)
TMP_CHILD_CLEANUP_NAMES = frozenset(
    {
        "amr-pilot-review",
        "amr-pilot-staging",
        "ontology-audit-source-check",
        "ontology-memory-audit-links-staging",
        "ontology-memory-gold-ceiling-staging",
        "ontology-memory-gold-staging",
        "ontology-memory-gold-v2-pretyped",
        "ontology-memory-gold-v2-test",
        "ontology-venv",
        "pdfs",
    }
)
PROTECTED_ROOTS = frozenset(
    {
        ".fastembed-cache",
        ".hf-cache",
        ".venv-dense",
        "archive",
        "artifacts",
        "data",
        "docs",
        "knowledge-extraction",
        "knowledge_pipeline",
        "tests",
        "tools",
    }
)


class CleanupApplyError(RuntimeError):
    def __init__(self, report: dict[str, Any]) -> None:
        super().__init__("workspace cleanup partially failed")
        self.report = report


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _write_json_immutable(path: Path, value: Any) -> None:
    content = _canonical_json_bytes(value)
    if path.exists():
        if path.read_bytes() != content:
            raise FileExistsError(f"immutable artifact differs: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _is_within(path: Path, parent: Path) -> bool:
    resolved_path = path.resolve()
    resolved_parent = parent.resolve()
    return resolved_path == resolved_parent or resolved_parent in resolved_path.parents


def _validate_audit_path(
    path: Path,
    cleanup_targets: Sequence[Path],
    *,
    label: str,
    must_not_exist: bool,
) -> None:
    if any(_is_within(path, target) for target in cleanup_targets):
        raise ValueError(f"{label} must not be inside a cleanup target: {path}")
    if must_not_exist and path.exists():
        raise ValueError(f"{label} already exists: {path}")


def _preflight_report_output(path: Path, cleanup_targets: Sequence[Path]) -> None:
    _validate_audit_path(
        path,
        cleanup_targets,
        label="report output",
        must_not_exist=True,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".preflight",
        delete=True,
    ) as stream:
        stream.write(b"workspace-hygiene-report-preflight")
        stream.flush()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("cleanup plan must be a JSON object")
    return value


def _is_allowlisted_top_level_name(name: str) -> bool:
    return name in EXACT_CLEANUP_NAMES or any(
        name.startswith(prefix) for prefix in CLEANUP_PREFIXES
    )


def _relative_target_path(root: Path, target: Path) -> str:
    try:
        relative = target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"cleanup target resolves outside workspace: {target}") from exc
    return relative.as_posix()


def _canonical_plan_target_path(value: str) -> str:
    path = Path(value)
    if path.is_absolute() or any(part in {".", ".."} for part in path.parts):
        raise ValueError(f"cleanup target path is not canonical: {value}")
    canonical = path.as_posix()
    if not canonical or canonical != value:
        raise ValueError(f"cleanup target path is not canonical: {value}")
    return canonical


def _is_allowlisted_relative_path(relative_path: str) -> bool:
    parts = Path(relative_path).parts
    if len(parts) == 1:
        return _is_allowlisted_top_level_name(parts[0])
    return (
        len(parts) == 2
        and parts[0] == "tmp"
        and parts[1] in TMP_CHILD_CLEANUP_NAMES
    )


def _is_reparse_point(path: Path) -> bool:
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(flag and attributes & flag)


def _validate_target(root: Path, target: Path) -> None:
    root = root.resolve()
    relative_path = _relative_target_path(root, target)
    if not _is_allowlisted_relative_path(relative_path):
        raise ValueError(f"cleanup target is not allowlisted: {relative_path}")
    if relative_path in PROTECTED_ROOTS:
        raise ValueError(f"cleanup target is protected: {relative_path}")
    if target.is_symlink() or _is_reparse_point(target):
        raise ValueError(f"cleanup target is a link or reparse point: {target}")
    resolved = target.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"cleanup target resolves outside workspace: {target}")


def discover_cleanup_targets(root: Path) -> list[Path]:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"workspace root is not a directory: {root}")
    targets = [
        child
        for child in root.iterdir()
        if child.is_dir() and _is_allowlisted_top_level_name(child.name)
    ]
    tmp_root = root / "tmp"
    if tmp_root.exists():
        if tmp_root.is_symlink() or _is_reparse_point(tmp_root):
            raise ValueError(f"tmp root is a link or reparse point: {tmp_root}")
        if tmp_root.is_dir():
            targets.extend(
                child
                for child in tmp_root.iterdir()
                if child.is_dir() and child.name in TMP_CHILD_CLEANUP_NAMES
            )
    for target in targets:
        _validate_target(root, target)
    return sorted(targets, key=lambda path: _relative_target_path(root, path))


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _directory_stats(path: Path) -> tuple[int, int, str]:
    file_count = 0
    byte_count = 0
    tree_digest = hashlib.sha256()
    children = sorted(
        path.rglob("*"), key=lambda child: child.relative_to(path).as_posix()
    )
    for child in children:
        if child.is_symlink() or _is_reparse_point(child):
            raise ValueError(f"cleanup target contains link or reparse point: {child}")
        relative_path = child.relative_to(path).as_posix()
        if child.is_dir():
            record = {"path": relative_path, "type": "directory"}
            tree_digest.update(_canonical_json_bytes(record))
            continue
        if child.is_file():
            size = child.stat().st_size
            file_count += 1
            byte_count += size
            record = {
                "path": relative_path,
                "type": "file",
                "bytes": size,
                "sha256": _file_sha256(child),
            }
            tree_digest.update(_canonical_json_bytes(record))
            continue
        raise ValueError(f"cleanup target contains unsupported entry: {child}")
    return file_count, byte_count, tree_digest.hexdigest()


def build_cleanup_plan(root: Path, *, run_id: str) -> dict[str, Any]:
    root = root.resolve()
    if not run_id.strip():
        raise ValueError("run_id must not be empty")
    targets = []
    for target in discover_cleanup_targets(root):
        file_count, byte_count, tree_sha256 = _directory_stats(target)
        relative_path = _relative_target_path(root, target)
        targets.append(
            {
                "path": relative_path,
                "file_count": file_count,
                "bytes": byte_count,
                "tree_sha256": tree_sha256,
                "reason": "workspace-local reproducible temporary data",
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "run_id": run_id,
        "core_impact": "none",
        "workspace_root": root.as_posix(),
        "target_count": len(targets),
        "removable_file_count": sum(item["file_count"] for item in targets),
        "removable_bytes": sum(item["bytes"] for item in targets),
        "targets": targets,
        "protected_roots_present": sorted(
            name for name in PROTECTED_ROOTS if (root / name).exists()
        ),
    }


def _validate_plan(root: Path, plan: dict[str, Any]) -> list[tuple[Path, dict[str, Any]]]:
    root = root.resolve()
    if plan.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported cleanup plan schema")
    if plan.get("policy_id") != POLICY_ID:
        raise ValueError("unsupported cleanup policy")
    run_id = plan.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("cleanup plan run_id must not be empty")
    if plan.get("core_impact") != "none":
        raise ValueError("cleanup plan core_impact must be none")
    if plan.get("workspace_root") != root.as_posix():
        raise ValueError("cleanup plan workspace root mismatch")
    targets = plan.get("targets")
    if not isinstance(targets, list):
        raise ValueError("cleanup plan targets must be a list")
    if plan.get("target_count") != len(targets):
        raise ValueError("cleanup plan target count mismatch")

    validated: list[tuple[Path, dict[str, Any]]] = []
    seen: set[str] = set()
    for item in targets:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ValueError("cleanup plan target is malformed")
        relative_path = _canonical_plan_target_path(item["path"])
        if relative_path in seen:
            raise ValueError(f"duplicate cleanup target: {relative_path}")
        seen.add(relative_path)
        target = root / relative_path
        if not target.exists():
            raise ValueError(
                f"target drift: cleanup target is missing: {relative_path}"
            )
        _validate_target(root, target)
        file_count, byte_count, tree_sha256 = _directory_stats(target)
        if (
            file_count != item.get("file_count")
            or byte_count != item.get("bytes")
            or tree_sha256 != item.get("tree_sha256")
        ):
            raise ValueError(f"target drift for {relative_path}")
        validated.append((target, item))

    discovered = {
        _relative_target_path(root, target)
        for target in discover_cleanup_targets(root)
    }
    if seen != discovered:
        raise ValueError("cleanup target set drift")

    if sum(item["file_count"] for _, item in validated) != plan.get(
        "removable_file_count"
    ):
        raise ValueError("cleanup plan file count mismatch")
    if sum(item["bytes"] for _, item in validated) != plan.get("removable_bytes"):
        raise ValueError("cleanup plan byte count mismatch")
    return validated


def _build_cleanup_report(
    root: Path,
    plan: dict[str, Any],
    removed_items: Sequence[dict[str, Any]],
    *,
    status: str,
    remaining: Sequence[Path],
    failed_target: str | None = None,
    error: Exception | None = None,
    remaining_inventory_error: Exception | None = None,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "run_id": plan["run_id"],
        "core_impact": "none",
        "status": status,
        "workspace_root": root.as_posix(),
        "plan_sha256": hashlib.sha256(_canonical_json_bytes(plan)).hexdigest(),
        "removed_target_count": len(removed_items),
        "removed_file_count": sum(item["file_count"] for item in removed_items),
        "removed_bytes": sum(item["bytes"] for item in removed_items),
        "removed_targets": [item["path"] for item in removed_items],
        "remaining_target_count": len(remaining),
        "remaining_targets": [
            _relative_target_path(root, path) for path in remaining
        ],
        "protected_roots_present": sorted(
            name for name in PROTECTED_ROOTS if (root / name).exists()
        ),
    }
    if failed_target is not None:
        report["failed_target"] = failed_target
    if error is not None:
        report["error"] = {
            "type": type(error).__name__,
            "message": str(error),
        }
    if remaining_inventory_error is not None:
        report["remaining_inventory_error"] = {
            "type": type(remaining_inventory_error).__name__,
            "message": str(remaining_inventory_error),
        }
    return report


def _discover_remaining_after_failure(
    root: Path,
) -> tuple[list[Path], Exception | None]:
    try:
        return discover_cleanup_targets(root), None
    except Exception as exc:
        return [], exc


def apply_cleanup_plan(root: Path, plan: dict[str, Any]) -> dict[str, Any]:
    root = root.resolve()
    validated = _validate_plan(root, plan)
    removed_items: list[dict[str, Any]] = []
    for target, item in validated:
        try:
            _validate_target(root, target)
            file_count, byte_count, tree_sha256 = _directory_stats(target)
            if (
                file_count != item["file_count"]
                or byte_count != item["bytes"]
                or tree_sha256 != item["tree_sha256"]
            ):
                raise ValueError(f"target drift for {item['path']}")
            shutil.rmtree(target)
            removed_items.append(item)
        except Exception as exc:
            remaining, inventory_error = _discover_remaining_after_failure(root)
            report = _build_cleanup_report(
                root,
                plan,
                removed_items,
                status="partial_failed",
                remaining=remaining,
                failed_target=item["path"],
                error=exc,
                remaining_inventory_error=inventory_error,
            )
            raise CleanupApplyError(report) from exc

    try:
        remaining = discover_cleanup_targets(root)
    except Exception as exc:
        report = _build_cleanup_report(
            root,
            plan,
            removed_items,
            status="partial_failed",
            remaining=[],
            failed_target="post_cleanup_inventory",
            error=exc,
            remaining_inventory_error=exc,
        )
        raise CleanupApplyError(report) from exc
    return _build_cleanup_report(
        root,
        plan,
        removed_items,
        status="cleaned" if not remaining else "incomplete",
        remaining=remaining,
    )


def run_cleanup_file(
    root: Path,
    plan_path: Path,
    output_path: Path,
    *,
    expected_plan_sha256: str,
) -> dict[str, Any]:
    root = root.resolve()
    actual_plan_sha256 = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    if actual_plan_sha256 != expected_plan_sha256:
        raise ValueError("cleanup plan SHA-256 mismatch")
    plan = _load_json(plan_path)
    cleanup_targets = discover_cleanup_targets(root)
    _validate_audit_path(
        plan_path,
        cleanup_targets,
        label="cleanup plan file",
        must_not_exist=False,
    )
    _preflight_report_output(output_path, cleanup_targets)
    try:
        report = apply_cleanup_plan(root, plan)
    except CleanupApplyError as exc:
        report = exc.report
    _write_json_immutable(output_path, report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="workspace-hygiene")
    commands = parser.add_subparsers(dest="command", required=True)

    inventory = commands.add_parser("inventory")
    inventory.add_argument("--root", required=True)
    inventory.add_argument("--run-id", required=True)
    inventory.add_argument("--output", required=True)

    clean = commands.add_parser("clean")
    clean.add_argument("--root", required=True)
    clean.add_argument("--plan", required=True)
    clean.add_argument("--output", required=True)
    clean.add_argument("--expected-plan-sha256", required=True)
    return parser


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "inventory":
        root = Path(args.root).resolve()
        cleanup_targets = discover_cleanup_targets(root)
        output_path = Path(args.output)
        _validate_audit_path(
            output_path,
            cleanup_targets,
            label="inventory output",
            must_not_exist=False,
        )
        plan = build_cleanup_plan(root, run_id=args.run_id)
        _write_json_immutable(output_path, plan)
        _print(plan)
        return 0
    if args.command == "clean":
        report = run_cleanup_file(
            Path(args.root),
            Path(args.plan),
            Path(args.output),
            expected_plan_sha256=args.expected_plan_sha256,
        )
        _print(report)
        return 0 if report["status"] == "cleaned" else 2
    raise NotImplementedError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
