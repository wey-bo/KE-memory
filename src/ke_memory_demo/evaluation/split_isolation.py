"""Materialize splits as separate process inputs that cannot reach each other.

``assert_held_out_untouched`` checked only the ids a caller chose to declare, so any code could
read a held-out question or its gold without appearing in the list. That is a bookkeeping
convention, not isolation, and a review rejected it on exactly that basis.

Here each split is written to its own file, and a discovery process is handed **only** the
discovery file. The held-out gold is never in the same file, so reading it is not a matter of
restraint — the bytes are not present. The same sandbox that isolates a memory build is reused
to run analysis over a single split, which means the process cannot open a sibling split file
either.

The manifest records a hash per split, so a later run can prove which bytes it consumed.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ke_memory_demo.core.json import JsonObject, JsonValue, canonical_json

from .channels import GoldChannel, LoadedBenchmark, QuestionChannel
from .data_boundaries import Split, SplitPlan
from .sandboxed_build import (
    SandboxManifest,
    base_interpreter,
    reconcile_manifest,
    sandbox_available,
)


class SplitIsolationError(RuntimeError):
    """A split could not be materialized, or analysis crossed a split boundary."""


@dataclass(frozen=True)
class MaterializedSplit:
    """One split on disk, with the hash of exactly what it contains."""

    split: Split
    path: Path
    question_count: int
    sha256: str

    def as_json(self) -> JsonObject:
        return {
            "split": str(self.split),
            "file": self.path.name,
            "question_count": self.question_count,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class SplitAnalysisResult:
    """What an isolated analysis returned, plus proof of what it could see."""

    split: Split
    payload: Any
    consumed_split_sha256: str
    sandbox: SandboxManifest


def materialize_splits(
    loaded: LoadedBenchmark,
    plan: SplitPlan,
    destination: Path,
) -> tuple[MaterializedSplit, ...]:
    """Write one file per split, each carrying only its own questions and gold."""
    destination.mkdir(parents=True, exist_ok=True)
    turns = _turns_by_conversation(loaded)
    written: list[MaterializedSplit] = []

    for split in Split:
        ids = set(plan.ids_for(split))
        if not ids:
            continue
        questions = [q for q in loaded.questions.questions if q.question_id in ids]
        labels = [label for label in loaded.gold.labels if label.question_id in ids]
        handles = {q.conversation_handle for q in questions}

        payload: JsonValue = {
            "split": str(split),
            "questions": [q.model_dump(mode="json") for q in questions],
            # Gold for this split only. A different split's answers are not in this file.
            "gold": [label.model_dump(mode="json") for label in labels],
            "turns": {
                handle: [t.model_dump(mode="json") for t in turns.get(handle, ())]
                for handle in sorted(handles)
            },
        }
        body = canonical_json(payload)
        path = destination / f"{split}.json"
        path.write_bytes(body)
        written.append(
            MaterializedSplit(
                split=split,
                path=path,
                question_count=len(questions),
                sha256=hashlib.sha256(body).hexdigest(),
            )
        )

    _assert_no_cross_split_content(written, plan)
    return tuple(written)


def _assert_no_cross_split_content(
    written: Sequence[MaterializedSplit],
    plan: SplitPlan,
) -> None:
    """Fail if any split file contains a question id belonging to another split."""
    for materialized in written:
        payload = json.loads(materialized.path.read_text(encoding="utf-8"))
        own = set(plan.ids_for(materialized.split))
        present = {q["question_id"] for q in payload["questions"]}
        present |= {label["question_id"] for label in payload["gold"]}
        foreign = sorted(present - own)
        if foreign:
            raise SplitIsolationError(
                f"{materialized.path.name} contains question ids from another split: "
                f"{foreign[:5]}"
            )


_CHILD = r"""
import json, os, sys, importlib

try:
    os.closerange(3, 4096)
except Exception:
    pass

request = json.load(sys.stdin)

def _observed():
    mounts = []
    try:
        with open("/proc/self/mountinfo", encoding="utf-8") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) < 5:
                    continue
                sep = parts.index("-") if "-" in parts else len(parts)
                mounts.append({
                    "mount_point": parts[4],
                    "fstype": parts[sep + 1] if sep + 1 < len(parts) else "?",
                })
    except Exception as exc:
        mounts = [{"mount_point": "unreadable", "fstype": type(exc).__name__}]
    try:
        staging = sorted(os.listdir("/staging"))
    except Exception as exc:
        staging = [f"unreadable: {type(exc).__name__}"]
    try:
        fds = len(os.listdir("/proc/self/fd"))
    except Exception:
        fds = -1
    return {
        "mountinfo": mounts,
        "root_entries": sorted(os.listdir("/")),
        "staging_entries": staging,
        "fd_count": fds,
        "netns_interfaces": sorted(os.listdir("/sys/class/net"))
        if os.path.isdir("/sys/class/net")
        else [],
    }

observed = _observed()
sys.path.insert(0, "/staging")
module = importlib.import_module(request["analysis_module"])
analyse = getattr(module, request["analysis_attr"])
result = analyse(request["split_payload"])
sys.stdout.write(json.dumps({"result": result, "observed": observed}, sort_keys=True))
"""


def analyse_split_in_isolation(
    materialized: MaterializedSplit,
    *,
    analysis_source: Path,
    analysis_module: str,
    analysis_attr: str,
    timeout_seconds: int = 900,
) -> SplitAnalysisResult:
    """Run analysis over one split inside a namespace holding no other split.

    The split content travels on stdin. No split file is mounted, so the process cannot open a
    sibling file even by absolute path: the directory containing them is not in its namespace.
    """
    if not sandbox_available():
        raise SplitIsolationError(
            "namespace isolation is unavailable, so split separation cannot be shown"
        )
    if not analysis_source.is_file():
        raise SplitIsolationError(f"analysis source is not a file: {analysis_source}")

    body = materialized.path.read_bytes()
    if hashlib.sha256(body).hexdigest() != materialized.sha256:
        raise SplitIsolationError(
            f"{materialized.path.name} changed since it was materialized"
        )

    request = json.dumps(
        {
            "analysis_module": analysis_module,
            "analysis_attr": analysis_attr,
            "split_payload": json.loads(body.decode("utf-8")),
        },
        sort_keys=True,
    )

    with tempfile.TemporaryDirectory(prefix="ke-split-") as work:
        work_path = Path(work)
        newroot = work_path / "newroot"
        newroot.mkdir(parents=True)
        local_interp = work_path / "interp"
        shutil.copytree(base_interpreter().parent.parent, local_interp, symlinks=True)
        interp_relative = base_interpreter().relative_to(base_interpreter().parent.parent)
        (work_path / "child.py").write_text(_CHILD, encoding="utf-8")

        intended = ["/interp (ro, copied interpreter)", "/usr (ro)"]
        lines = [
            "set -e",
            f"mount -t tmpfs tmpfs {newroot}",
            f"mkdir -p {newroot}/interp {newroot}/proc {newroot}/staging {newroot}/dev "
            f"{newroot}/tmp {newroot}/usr",
            f"mount --bind -o ro {local_interp} {newroot}/interp",
            f"mount --bind -o ro /usr {newroot}/usr",
            f"cp {analysis_source} {newroot}/staging/{analysis_module}.py",
            f"cp {work_path / 'child.py'} {newroot}/staging/_child.py",
            f"ln -sfn usr/lib {newroot}/lib",
            f"ln -sfn usr/lib64 {newroot}/lib64",
            f"mount -t proc proc {newroot}/proc",
        ]
        for node in ("urandom", "null", "zero"):
            lines.append(f": > {newroot}/dev/{node}")
            lines.append(f"mount --bind /dev/{node} {newroot}/dev/{node}")
        intended.extend(
            [
                "/dev/{urandom,null,zero} (only these three nodes)",
                "/proc (fresh procfs in a private PID namespace)",
                "/staging (the analysis module only)",
                "/tmp (empty tmpfs)",
                "no split directory is mounted, so a sibling split cannot be opened",
            ]
        )
        lines.append(
            f"exec unshare --root={newroot} /interp/{interp_relative} -I -S "
            f"/staging/_child.py"
        )

        completed = subprocess.run(
            [
                "unshare",
                "--user",
                "--map-root-user",
                "--mount",
                "--net",
                "--pid",
                "--fork",
                "sh",
                "-c",
                "\n".join(lines),
            ],
            input=request,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            close_fds=True,
            check=False,
        )

    if completed.returncode != 0:
        raise SplitIsolationError(
            f"isolated split analysis failed with code {completed.returncode}: "
            f"{completed.stderr.strip()[:500]}"
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise SplitIsolationError("isolated split analysis returned invalid JSON") from exc

    manifest = reconcile_manifest(
        intended=tuple(intended),
        observed=payload.get("observed", {}),
        builder_module=analysis_module,
    )
    if not manifest.reconciled:
        raise SplitIsolationError(
            "the split sandbox did not match its manifest: "
            + "; ".join(manifest.reconciliation_notes)
        )

    return SplitAnalysisResult(
        split=materialized.split,
        payload=payload["result"],
        consumed_split_sha256=materialized.sha256,
        sandbox=manifest,
    )


def assert_split_file_absent(paths: Sequence[Path], forbidden: Split) -> None:
    """Fail if a forbidden split's file is among the inputs handed to a process."""
    offenders = [p.name for p in paths if p.name == f"{forbidden}.json"]
    if offenders:
        raise SplitIsolationError(
            f"the {forbidden} split file was supplied to a process that must not see it: "
            f"{offenders}"
        )


def _turns_by_conversation(loaded: LoadedBenchmark) -> dict[str, tuple[Any, ...]]:
    return {
        c.conversation_handle: tuple(t for s in c.sessions for t in s.turns)
        for c in loaded.build_input.conversations
    }


def channels_for_split(
    loaded: LoadedBenchmark,
    plan: SplitPlan,
    split: Split,
) -> tuple[QuestionChannel, GoldChannel]:
    """The question and gold channels for one split, for controller-side use."""
    ids = set(plan.ids_for(split))
    return (
        QuestionChannel(
            benchmark=loaded.questions.benchmark,
            questions=tuple(
                q for q in loaded.questions.questions if q.question_id in ids
            ),
        ),
        GoldChannel(
            benchmark=loaded.gold.benchmark,
            labels=tuple(
                label for label in loaded.gold.labels if label.question_id in ids
            ),
        ),
    )
